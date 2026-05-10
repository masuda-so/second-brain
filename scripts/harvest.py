#!/usr/bin/env python3
"""
Harvest — Autonomous Note Promotion Pipeline
============================================
Subcommands:
  extract    — UserPromptSubmit / PostToolUse: extract candidates, score, L1-promote.
  checkpoint — Stop (per-response): run L1+L2 promotion for accumulated candidates.
  flush      — SessionEnd: final promotion, L3 flag list in Daily note.

Hook event mapping:
  UserPromptSubmit         → extract
  PostToolUse              → extract
  Stop (per-response turn) → checkpoint
  SessionEnd               → flush

All ops fail-open: always exit 0. SQLite uses WAL + busy_timeout to handle
parallel hook execution safely.

Promotion levels:
  L1 (auto, immediate):   Ideas/         importance >= 3
  L2 (auto, checkpoint):  Meta/Promotions/ importance >= 6
  L3 (flag for user):     References/    importance >= 9  → checklist in Daily

DB location: $VAULT_PATH/Meta/.cache/memory.db
(hidden from normal vault sync / git)
"""

import sys
import os
import re
import json
import sqlite3
import pathlib
import hashlib
import textwrap
import fcntl
import contextlib
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).parent.parent

L1_THRESHOLD = 3
L2_THRESHOLD = 6
L3_THRESHOLD = 9
CHECKPOINT_EVERY = 5   # prompts between L2 sweeps
MAX_CONTENT_LEN = 1200
BUSY_TIMEOUT_MS = 5000  # SQLite busy_timeout for parallel hook safety

IMPORTANCE_RULES: list[tuple[int, str]] = [
    (3, r"覚えて|重要|ポイント|必ず|絶対|大事|remember|important|key\s*point|"
        r"note\s*that|don.t\s*forget|must|critical|crucial"),
    (2, r"決定|決めた|採用|方針|ルール|rule|decided|decision|policy|"
        r"we\s*will|use\s*this|going\s*forward|from\s*now\s*on|convention"),
    (2, r"エラー修正|バグ修正|fix|fixed|resolved|workaround|root\s*cause|原因|解決"),
    (2, r"判明|わかった|発見|気づき|insight|learned|found\s*that|turns\s*out|discovered"),
]

# Bash commands that are pure noise — never candidate-ify their output
BASH_NOISE_RE = re.compile(
    r"^(ls|ll|pwd|echo|cat|head|tail|grep|rg|awk|sed|wc|diff|git\s+(log|status|diff|show|"
    r"branch|fetch)|npm\s+(list|ls)|pip\s+list|find\s+\.|tmux-bridge|which|type|"
    r"command\s+-v)",
    re.IGNORECASE,
)

# Bash commands whose output IS worth capturing
BASH_SIGNAL_RE = re.compile(
    r"(error|exception|traceback|fail|fatal|curl|wget|pip\s+install|npm\s+install|"
    r"brew\s+install|cargo\s+build|go\s+build|make|cmake|docker|kubectl|psql|sqlite3)",
    re.IGNORECASE,
)

NOISE_RE = re.compile(
    r"^(ok|okay|yes|no|はい|いいえ|わかりました|了解|ありがとう|thanks?|sure|got\s*it)\W*$"
    r"|必ず.{0,20}(enter|送り|押し|実行|confirm)"  # tmux操作指示
    r"|tmux.bridge\s+(read|type|keys|send)"          # tmux-bridge操作コマンド
    r"|\[tmux-bridge\s+from:"                        # tmux-bridge relay header
    r"|【claude\s*[→→]\s*(codex|gemini)】"           # エージェント間通信ヘッダー
    r"|【(codex|gemini)\s*[→→]\s*claude】"
    r"|<task-notification>",                          # Claude Code internal task XML
    re.IGNORECASE,
)

# Prompts that are instructions to AI rather than knowledge to capture.
# Filtered unless the prompt starts with an explicit importance marker.
PROMPT_INSTRUCTION_RE = re.compile(
    r"(してください|して下さい|してほしい|しますか[?？]|ですか[?？]|"
    r"を(確認|教え|説明|見せ|チェック|実装|作成|生成|修正|改善|追加|削除)し?"
    r"|(please\s+)?(explain|implement|create|generate|fix|add|remove|"
    r"check|verify|review|show|describe|list|summarize))",
    re.IGNORECASE,
)

# Explicit importance markers — keep the prompt even if it also looks instructional
PROMPT_IMPORTANCE_MARKER_RE = re.compile(
    r"^(重要|ポイント|覚えて|remember|note[:\s]|important[:\s]|key[:\s]|"
    r"決定|決めた|採用)",
    re.IGNORECASE,
)

# Minimum character count for a prompt to be worth harvesting as a note
PROMPT_MIN_CHARS = 25

# Vault directories that are ephemeral/session artifacts — never harvest writes from these
VAULT_EPHEMERAL_DIRS = (
    "Daily/", "Weekly/", "Monthly/",
    "Meta/AI Sessions/", "Meta/Promotions/", "Meta/.cache/",
)

SKIP_TITLES = {"", "untitled", "note", "notes", "misc", "todo"}

# Generic / too-short entity names that should not become Reference stubs
REFERENCE_SKIP = {
    "main", "readme", "index", "src", "lib", "test", "tests", "init", "utils", "util",
    "config", "app", "api", "data", "type", "types", "base", "core", "true", "false",
    "none", "null", "undefined", "new", "old", "tmp", "temp", "todo", "fixme",
    "error", "output", "result", "value", "item", "file", "path", "name", "text",
    # Common words that slip through but aren't useful concepts
    "status", "note", "state", "mode", "flag", "list", "set", "map", "key", "val",
    "str", "int", "bool", "dict", "obj", "cls", "self", "args", "kwargs", "env",
    "log", "msg", "buf", "ctx", "req", "res", "err", "ret",
}

# Entities matching these patterns are technical artifacts, not knowledge concepts
ENTITY_NOISE_RE = re.compile(
    r"[/\\*?]"        # path or glob/regex metacharacters
    r"|^#!"           # shebangs (#!/bin/bash)
    r"|^\d+$"         # pure numbers
    r"|^[A-Z_]{2,}$", # ALL_CAPS constants (env vars: PATH, VAULT_PATH)
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def warn(msg: str) -> None:
    print(f"harvest: {msg}", file=sys.stderr)


def get_vault_path() -> pathlib.Path:
    if v := os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip():
        p = pathlib.Path(v)
        if p.is_dir():
            return p
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            m = re.match(r"^- Location: `(.+)`", line)
            if m:
                p = pathlib.Path(m.group(1).strip())
                if p.is_dir():
                    return p
    raise RuntimeError("vault path not found")


def get_db(vault: pathlib.Path) -> sqlite3.Connection:
    db_dir = vault / "Meta" / ".cache"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    # WAL mode: safe for concurrent writers (parallel hooks)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT    NOT NULL,
            created_at   TEXT    NOT NULL,
            source       TEXT    NOT NULL,
            content      TEXT    NOT NULL,
            title        TEXT,
            importance   INTEGER NOT NULL DEFAULT 0,
            target_dir   TEXT    NOT NULL DEFAULT 'Ideas',
            status       TEXT    NOT NULL DEFAULT 'pending',
            vault_path   TEXT,
            content_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS entities (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    UNIQUE NOT NULL,
            appearances      INTEGER NOT NULL DEFAULT 1,
            last_seen        TEXT    NOT NULL,
            importance_bonus INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS prompt_counter (
            session_id  TEXT PRIMARY KEY,
            count       INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()


def parse_event(data: str) -> dict:
    """Tolerant JSON parse of hook stdin. Returns {} on failure."""
    if not data.strip():
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {}


def extract_session_id(event: dict) -> str:
    """Extract session_id from parsed hook event, with env var fallback."""
    raw = (
        event.get("session_id")
        or event.get("sessionId")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or "unknown-session"
    )
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(raw)).strip("-") or "unknown-session"


def score_content(text: str) -> int:
    lower = text.lower()
    return sum(pts for pts, pat in IMPORTANCE_RULES if re.search(pat, lower))


def extract_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            t = re.sub(r"^#+\s*", "", line).strip()
            if t and t.lower() not in SKIP_TITLES:
                return t[:80]
        t = re.sub(r"[*`_\[\]]", "", line)[:80].strip()
        if len(t) > 12:
            return t
    return ""


def content_hash(text: str) -> str:
    return hashlib.sha1(text.strip().encode()).hexdigest()[:12]


def slugify(s: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", s.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:60] or "note"


def upsert_entity(conn: sqlite3.Connection, name: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("""
        INSERT INTO entities (name, appearances, last_seen, importance_bonus)
        VALUES (?, 1, ?, 0)
        ON CONFLICT(name) DO UPDATE SET
            appearances = appearances + 1,
            last_seen = excluded.last_seen,
            importance_bonus = CASE
                WHEN appearances + 1 >= 3 THEN 2
                ELSE importance_bonus
            END
    """, (name, now))
    conn.commit()
    row = conn.execute(
        "SELECT importance_bonus FROM entities WHERE name=?", (name,)
    ).fetchone()
    return int(row["importance_bonus"]) if row else 0


def extract_entities(text: str) -> list:
    found: set = set()
    # CamelCase identifiers
    found.update(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    # Backtick-quoted tokens
    found.update(re.findall(r"`([^`\n]{3,40})`", text))
    # Source file names (harvest.py, package.json, etc.)
    found.update(re.findall(
        r"\b([\w-]+\.(?:py|js|ts|sh|json|yaml|yml|go|rs|rb|java|md))\b", text
    ))
    # URL domains
    for url in re.findall(r"https?://([^/\s'\"<>()]+)", text)[:5]:
        domain = url.split("/")[0]
        if "." in domain and len(domain) > 4:
            found.add(domain)
    return list(found)[:25]


@contextlib.contextmanager
def _file_lock(path: pathlib.Path):
    """Advisory exclusive lock on a per-file lockfile (POSIX flock).
    Raises RuntimeError if lock cannot be acquired within ~5 seconds.
    Callers must catch this to skip the write safely.
    """
    import time
    lock_path = path.parent / f".{path.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(lock_path, "w")
    acquired = False
    try:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            for _ in range(100):
                time.sleep(0.05)
                try:
                    fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    pass
        if not acquired:
            raise RuntimeError(f"lock timeout for {path.name}")
        yield
    finally:
        if acquired:
            fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()


def append_under_heading(path: pathlib.Path, heading: str, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _file_lock(path):
            text = path.read_text() if path.exists() else ""
            if text and not text.endswith("\n"):
                text += "\n"
            marker = f"## {heading}"
            if marker in text:
                idx = text.index(marker) + len(marker)
                next_h2 = text.find("\n## ", idx)
                entry = f"\n{content}\n"
                text = text + entry if next_h2 == -1 else text[:next_h2] + entry + text[next_h2:]
            else:
                text = text.rstrip("\n") + f"\n\n{marker}\n{content}\n"
            path.write_text(text)
    except RuntimeError as e:
        warn(f"skipping write to {path.name}: {e}")


def create_reference_stub(vault: pathlib.Path, entity: str) -> bool:
    """Create a References/ stub for a recurring entity if it doesn't exist.
    Returns True if a new file was created."""
    # Skip technical artifacts: shebangs, paths, regex patterns, ALL_CAPS constants
    if ENTITY_NOISE_RE.search(entity):
        return False
    slug = slugify(entity)
    if not slug or len(entity) < 4 or slug in REFERENCE_SKIP:
        return False
    ref_dir = vault / "References"
    ref_path = ref_dir / f"{slug}.md"
    if ref_path.exists():
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    content = textwrap.dedent(f"""\
        ---
        title: {entity}
        type: reference
        topic: {entity}
        created: {today}
        ---
        ## 目的

        ## 手順

        > [!warning] 再利用ルール

        ## 関連資料
    """)
    ref_dir.mkdir(parents=True, exist_ok=True)
    try:
        with _file_lock(ref_path):
            if ref_path.exists():
                return False
            ref_path.write_text(content)
        warn(f"reference stub: References/{slug}.md")
        return True
    except Exception as e:
        warn(f"reference stub failed for {entity}: {e}")
        return False


def _maybe_create_periodic_notes(vault: pathlib.Path) -> None:
    """Create Weekly and Monthly note stubs for the current period if they don't exist.
    Called at SessionEnd — safe to call every session (idempotent)."""
    today = datetime.now()

    # Weekly — ISO 8601: YYYY-Www  (e.g. 2026-W14)
    week_str = today.strftime("%G-W%V")
    weekly_path = vault / "Weekly" / f"{week_str}.md"
    if not weekly_path.exists():
        reviewed = today.strftime("%Y-%m-%d")
        body = textwrap.dedent(f"""\
            ---
            title: {week_str}
            type: weekly
            week: {week_str}
            reviewed: {reviewed}
            tags:
              - planning
              - review
            ---
            ## 進行中プロジェクト

            ## 昇格候補アイデア

            ## ブロッカー

            > [!tip] 週次の要約
            > 重要度の高い項目だけ Projects に昇格し、残りは保留または整理する。

            ## 来週の重点

            ## 関連ノート
        """)
        weekly_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with _file_lock(weekly_path):
                if not weekly_path.exists():
                    weekly_path.write_text(body)
            warn(f"periodic: created Weekly/{week_str}.md")
        except Exception as e:
            warn(f"periodic: weekly note failed: {e}")

    # Monthly — YYYY-MM
    month_str = today.strftime("%Y-%m")
    monthly_path = vault / "Monthly" / f"{month_str}.md"
    if not monthly_path.exists():
        body = textwrap.dedent(f"""\
            ---
            title: {month_str}
            type: monthly
            period: {month_str}
            tags:
              - monthly
              - strategy
            ---
            ## 優先事項

            ## うまくいったこと

            ## 改善点

            > [!warning] 月次判断
            > 実行可能な項目は Projects に移し、原則は References に残す。

            ## 来月の焦点

            ## 関連ノート
        """)
        monthly_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with _file_lock(monthly_path):
                if not monthly_path.exists():
                    monthly_path.write_text(body)
            warn(f"periodic: created Monthly/{month_str}.md")
        except Exception as e:
            warn(f"periodic: monthly note failed: {e}")


def create_note(vault: pathlib.Path, target_dir: str, title: str, content: str,
                tags: list | None = None, source: str = "") -> pathlib.Path:
    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(title) or slugify(content[:40])
    note_dir = vault / target_dir
    note_dir.mkdir(parents=True, exist_ok=True)
    # Collision-safe naming: slug.md → slug-YYYY-MM-DD.md → slug-YYYY-MM-DD-2.md …
    path = note_dir / f"{slug}.md"
    counter = 0
    while path.exists():
        counter += 1
        suffix = today if counter == 1 else f"{today}-{counter}"
        path = note_dir / f"{slug}-{suffix}.md"

    is_idea = (target_dir == "Ideas")

    if is_idea:
        # Template-Vault canonical format for Ideas/
        bare_tags = [t.lstrip("#") for t in (tags or [])]
        tag_lines = "".join(f"\n  - {t}" for t in bare_tags)
        front = textwrap.dedent(f"""\
            ---
            title: {title}
            type: idea
            status: incubating
            created: {today}
            tags:{tag_lines if bare_tags else " []"}
            harvest_source: "{source}"
            harvest_promoted: false
            ---
        """)
        body = f"## プロジェクト化の条件\n\n## 下書き素材\n\n{content}\n"
    else:
        # Custom staging format for Meta/Promotions/ (second-brain internal)
        bare_tags = [t.lstrip("#") for t in (tags or [])]
        tag_lines = "".join(f"\n  - {t}" for t in bare_tags)
        front = textwrap.dedent(f"""\
            ---
            type: staged
            created: {today}
            tags:{tag_lines if bare_tags else " []"}
            harvest_source: "{source}"
            harvest_promoted: false
            ---
        """)
        body = content + "\n"

    try:
        with _file_lock(path):
            path.write_text(front + "\n" + body)
    except RuntimeError as e:
        warn(f"skipping note creation {path.name}: {e}")
        raise  # propagate so caller can skip DB update
    return path


def create_reference_from_candidate(vault: pathlib.Path,
                                     row: sqlite3.Row) -> pathlib.Path | None:
    """Auto-draft a References/ note from a high-importance (L3) candidate.
    Populates ## 目的 with the candidate content. Returns path or None on failure."""
    today = datetime.now().strftime("%Y-%m-%d")
    title = row["title"] or extract_title(row["content"]) or "Untitled Reference"
    slug = slugify(title)
    ref_dir = vault / "References"
    ref_path = ref_dir / f"{slug}.md"
    if ref_path.exists():
        return ref_path
    purpose = row["content"][:400].strip()
    body = textwrap.dedent(f"""\
        ---
        title: {title}
        type: reference
        topic: {title}
        created: {today}
        harvest_source: "{row['source']}"
        importance: {row['importance']}
        ---
        ## 目的

        {purpose}

        ## 手順

        > [!warning] 再利用ルール

        ## 関連資料
    """)
    ref_dir.mkdir(parents=True, exist_ok=True)
    try:
        with _file_lock(ref_path):
            if ref_path.exists():
                return ref_path
            ref_path.write_text(body)
        warn(f"L3 auto-draft: References/{slug}.md")
        return ref_path
    except Exception as e:
        warn(f"L3 auto-draft failed for {title}: {e}")
        return None


def _drain_queue(vault: pathlib.Path, conn: sqlite3.Connection,
                 session_id: str) -> int:
    """Drain session-scoped queue file and process each event via cmd_extract.
    Returns number of events processed."""
    queue_dir = vault / "Meta" / ".cache" / "harvest-queue"
    queue_file = queue_dir / f"{session_id}.jsonl"
    if not queue_file.exists():
        return 0
    try:
        raw_lines = queue_file.read_text().strip().splitlines()
        queue_file.unlink()
    except Exception as e:
        warn(f"queue: drain read failed: {e}")
        return 0
    processed = 0
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            data = entry.get("data", "")
            entry_session_id = entry.get("session_id", session_id)
            if data:
                cmd_extract(data, vault, conn, entry_session_id)
                processed += 1
        except Exception as e:
            warn(f"queue: error processing event: {e}")
    warn(f"queue: drained {processed} events for session={session_id[:16]}")
    return processed


# ── Candidate management ─────────────────────────────────────────────────────

def enqueue_candidate(conn: sqlite3.Connection, session_id: str, source: str,
                      text: str, entity_bonus: int) -> None:
    base = score_content(text)
    total = base + entity_bonus
    if total <= 0:
        return

    chash = content_hash(text)
    existing = conn.execute(
        "SELECT id FROM candidates WHERE content_hash=? AND status='pending'",
        (chash,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE candidates SET importance=importance+1 WHERE id=?",
            (existing["id"],),
        )
        conn.commit()
        return

    title = extract_title(text)
    target = _choose_target(total, source)
    now = datetime.now().isoformat(timespec="seconds")

    conn.execute("""
        INSERT INTO candidates
            (session_id, created_at, source, content, title, importance, target_dir, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, now, source, text[:MAX_CONTENT_LEN], title, total, target, chash))
    conn.commit()


def _choose_target(score: int, source: str) -> str:
    if score >= L3_THRESHOLD:
        return "References"
    if score >= L2_THRESHOLD:
        return "Meta/Promotions"
    # L1: web/prompt → Ideas; tool output → staging
    if source.startswith(("web", "prompt")):
        return "Ideas"
    return "Meta/Promotions"


# ── Promotion sweeps ─────────────────────────────────────────────────────────

def promote_l1(vault: pathlib.Path, conn: sqlite3.Connection,
               threshold: int = L1_THRESHOLD) -> int:
    """Auto-promote to Ideas/ immediately."""
    rows = conn.execute("""
        SELECT * FROM candidates
        WHERE status='pending' AND importance >= ? AND target_dir='Ideas'
        ORDER BY importance DESC LIMIT 20
    """, (threshold,)).fetchall()
    count = 0
    for row in rows:
        try:
            title = row["title"] or extract_title(row["content"]) or "Untitled Idea"
            path = create_note(vault, "Ideas", title, row["content"],
                               tags=["#idea", "#auto"], source=row["source"])
            conn.execute(
                "UPDATE candidates SET status='promoted', vault_path=? WHERE id=?",
                (str(path), row["id"]),
            )
            conn.commit()
            count += 1
        except Exception as e:
            warn(f"L1 promote error: {e}")
    return count


def promote_l2(vault: pathlib.Path, conn: sqlite3.Connection) -> int:
    """Stage to Meta/Promotions/ at checkpoint."""
    rows = conn.execute("""
        SELECT * FROM candidates
        WHERE status='pending' AND importance >= ?
          AND target_dir IN ('Meta/Promotions', 'References')
        ORDER BY importance DESC LIMIT 10
    """, (L2_THRESHOLD,)).fetchall()
    count = 0
    for row in rows:
        try:
            title = row["title"] or extract_title(row["content"]) or "Staged Note"
            path = create_note(vault, "Meta/Promotions", title, row["content"],
                               tags=["#staged", "#auto"], source=row["source"])
            conn.execute(
                "UPDATE candidates SET status='staged', vault_path=? WHERE id=?",
                (str(path), row["id"]),
            )
            conn.commit()
            count += 1
        except Exception as e:
            warn(f"L2 promote error: {e}")
    return count


# ── Subcommands ───────────────────────────────────────────────────────────────

def _is_harvestable_write(fp: str, vault: pathlib.Path) -> bool:
    """Return True if a write event to file_path should be harvested.

    Rules:
    - Vault writes: only canonical knowledge directories with .md extension.
      Skip ephemeral dirs (Daily/, Meta/AI Sessions/, Meta/Promotions/, etc.)
    - Repo writes: only .md files (docs, READMEs). Skip .py/.sh/.json/.yaml — code
      is the artifact, not a knowledge note.
    """
    if not fp:
        return False
    vault_str = str(vault).rstrip("/") + "/"
    if fp.startswith(vault_str):
        rel = fp[len(vault_str):]
        if not fp.endswith(".md"):
            return False
        return not any(rel.startswith(d) for d in VAULT_EPHEMERAL_DIRS)
    # Repo file: only markdown
    return fp.endswith(".md")


def cmd_extract(data: str, vault: pathlib.Path, conn: sqlite3.Connection,
                session_id: str) -> None:
    try:
        event = json.loads(data) if data.strip() else {}
    except json.JSONDecodeError:
        event = {}

    pieces: list[tuple[str, str]] = []  # (source_label, text)

    # Prompt text — also increments the prompt counter (tool events do not)
    prompt = (event.get("prompt") or event.get("message") or
              event.get("user_prompt") or "")
    if prompt:
        prompt_stripped = prompt.strip()
        if not NOISE_RE.match(prompt_stripped):
            # Count all substantive prompts for checkpoint frequency tracking
            conn.execute("""
                INSERT INTO prompt_counter (session_id, count) VALUES (?, 1)
                ON CONFLICT(session_id) DO UPDATE SET count = count + 1
            """, (session_id,))
            conn.commit()
            # Additional prompt filters: skip AI directives and very short messages.
            # Short messages (< PROMPT_MIN_CHARS) are conversational, not knowledge.
            # Instruction-type prompts ("〜してください") are AI task directives, not
            # standalone knowledge — unless the user has flagged them with an explicit
            # importance marker ("重要:", "決定:", "remember:", etc.).
            is_instruction = PROMPT_INSTRUCTION_RE.search(prompt_stripped)
            has_marker = PROMPT_IMPORTANCE_MARKER_RE.match(prompt_stripped)
            if (len(prompt_stripped) >= PROMPT_MIN_CHARS and
                    not (is_instruction and not has_marker)):
                pieces.append(("prompt", prompt))

    # Tool events
    tool_name = event.get("tool_name", event.get("toolName", ""))
    tool_input = event.get("tool_input") or {}
    tool_resp = str(event.get("tool_response", event.get("tool_output", "")) or "")

    if tool_name in ("Write", "Edit"):
        fp = tool_input.get("file_path", "")
        body = tool_input.get("content", tool_input.get("new_string", ""))
        if body and len(body) > 40 and _is_harvestable_write(fp, vault):
            pieces.append((f"write:{fp}", body[:MAX_CONTENT_LEN]))
    elif tool_name == "MultiEdit":
        fp = tool_input.get("file_path", "")
        for edit in tool_input.get("edits", []):
            body = edit.get("new_string", "")
            if body and len(body) > 40 and _is_harvestable_write(fp, vault):
                pieces.append((f"write:{fp}", body[:MAX_CONTENT_LEN]))

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Git commit: extract message from tool response (e.g. "[main abc1234] feat: ...")
        if re.match(r"git\s+commit", cmd.strip(), re.IGNORECASE):
            commit_match = re.search(r"\[[^\]]+\]\s+(.+)", tool_resp)
            if commit_match:
                commit_msg = commit_match.group(1).strip()
                if len(commit_msg) > 5:
                    pieces.append(("git:commit", commit_msg))
        # Skip pure noise commands
        elif not BASH_NOISE_RE.match(cmd.strip()):
            out = tool_resp[:MAX_CONTENT_LEN]
            # Capture if command or output has signal
            if BASH_SIGNAL_RE.search(cmd) or BASH_SIGNAL_RE.search(out):
                if len(out) > 30:
                    pieces.append((f"bash:{cmd[:60]}", out))

    if tool_name in ("WebFetch", "WebSearch"):
        if len(tool_resp) > 60:
            pieces.append(("web", tool_resp[:MAX_CONTENT_LEN]))

    total_entities = 0
    for source_label, text in pieces:
        entities = extract_entities(text)
        bonus = sum(upsert_entity(conn, e) for e in entities)
        total_entities += len(entities)
        enqueue_candidate(conn, session_id, source_label, text, bonus)

    if pieces:
        warn(f"extract: pieces={len(pieces)} entities={total_entities} "
             f"source={pieces[0][0]} session={session_id[:16]}")

    # L1 always runs after extract
    promote_l1(vault, conn)


def _get_prompt_count(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute(
        "SELECT count FROM prompt_counter WHERE session_id=?", (session_id,)
    ).fetchone()
    return row["count"] if row else 0


def _effective_l1_threshold(prompt_count: int) -> int:
    """C: Lower the L1 threshold for short sessions (≤5 meaningful prompts)."""
    return 2 if prompt_count <= 5 else L1_THRESHOLD


def cmd_checkpoint(vault: pathlib.Path, conn: sqlite3.Connection,
                   session_id: str) -> None:
    """Per-response (Stop hook): L1 always; L2 only every CHECKPOINT_EVERY prompts."""
    prompt_count = _get_prompt_count(conn, session_id)
    threshold = _effective_l1_threshold(prompt_count)
    n1 = promote_l1(vault, conn, threshold=threshold)

    n2 = 0
    if prompt_count > 0 and prompt_count % CHECKPOINT_EVERY == 0:
        n2 = promote_l2(vault, conn)

    if n1 or n2:
        warn(f"checkpoint (prompt #{prompt_count}, L1≥{threshold}): +{n1} Ideas, +{n2} staged")


def cmd_queue(data: str, vault: pathlib.Path, session_id: str, event: dict) -> None:
    """Append event to session-scoped queue file (fast, non-blocking).
    Called by hooks instead of extract — actual processing happens at worker/flush."""
    if not data.strip():
        return
    queue_dir = vault / "Meta" / ".cache" / "harvest-queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queue_file = queue_dir / f"{session_id}.jsonl"
    now = datetime.now().isoformat(timespec="seconds")
    hook_name = event.get("hook_event_name", event.get("hookEventName", ""))
    try:
        with open(queue_file, "a") as f:
            f.write(json.dumps({
                "queued_at": now,
                "session_id": session_id,
                "hook_event_name": hook_name,
                "data": data,
            }) + "\n")
        warn(f"queue: wrote event session={session_id[:16]} hook={hook_name}")
    except Exception as e:
        warn(f"queue: write failed: {e}")


def cmd_worker(vault: pathlib.Path, conn: sqlite3.Connection,
               session_id: str) -> None:
    """Drain the queue file, process all events, then run checkpoint.
    Called by Stop hook — replaces the old synchronous checkpoint."""
    _drain_queue(vault, conn, session_id)
    cmd_checkpoint(vault, conn, session_id)


def cmd_flush(vault: pathlib.Path, conn: sqlite3.Connection,
              session_id: str) -> None:
    """SessionEnd: drain queue + final sweep + L3 auto-draft + periodic notes + Reference stubs."""
    # Drain any remaining queued events before final processing
    _drain_queue(vault, conn, session_id)

    prompt_count = _get_prompt_count(conn, session_id)
    threshold = _effective_l1_threshold(prompt_count)
    n1 = promote_l1(vault, conn, threshold=threshold)
    n2 = promote_l2(vault, conn)

    # A: Weekly / Monthly stubs for current period (idempotent)
    _maybe_create_periodic_notes(vault)

    # B: Reference stubs for entities with 5+ cumulative appearances
    ref_rows = conn.execute("""
        SELECT name FROM entities
        WHERE appearances >= 5
        ORDER BY appearances DESC LIMIT 20
    """).fetchall()
    ref_count = sum(1 for r in ref_rows if create_reference_stub(vault, r["name"]))
    if ref_count:
        warn(f"flush: created {ref_count} References/ stubs")

    today = datetime.now().strftime("%Y-%m-%d")
    time_label = datetime.now().strftime("%H:%M")
    daily_dir = os.environ.get("SECOND_BRAIN_DAILY_DIR", "Daily")
    daily_note = vault / daily_dir / f"{today}.md"

    # Tally
    stats = {r["status"]: r["n"] for r in conn.execute("""
        SELECT status, COUNT(*) AS n FROM candidates
        WHERE session_id=? GROUP BY status
    """, (session_id,)).fetchall()}
    promoted = stats.get("promoted", 0)
    staged = stats.get("staged", 0)

    # L3: high-importance items that should eventually go to References/
    l3_rows = conn.execute("""
        SELECT * FROM candidates
        WHERE session_id=? AND importance >= ? AND target_dir='References'
          AND status IN ('pending','staged')
        ORDER BY importance DESC LIMIT 10
    """, (session_id, L3_THRESHOLD)).fetchall()

    # L3: auto-draft Reference notes instead of just flagging
    l3_drafted = 0
    l3_lines = []
    for r in l3_rows:
        ref_path = create_reference_from_candidate(vault, r)
        title = r["title"] or "untitled"
        if ref_path:
            conn.execute(
                "UPDATE candidates SET status='promoted', vault_path=? WHERE id=?",
                (str(ref_path), r["id"]),
            )
            conn.commit()
            l3_drafted += 1
            l3_lines.append(f"  - [[References/{ref_path.stem}]] (score {r['importance']})")
        else:
            l3_lines.append(f"  - [ ] **{title}** (score {r['importance']}) — draft manually")

    lines = [f"- {time_label} Harvest: +{promoted} Ideas, +{staged} staged, +{l3_drafted} References drafted"]
    if l3_lines:
        lines.append(f"- {time_label} References:")
        lines.extend(l3_lines)

    try:
        append_under_heading(daily_note, "AI Session", "\n".join(lines))
    except Exception as e:
        warn(f"flush: daily note update failed: {e}")

    warn(f"flush: promoted={promoted} staged={staged} l3_pending={len(l3_rows)} "
         f"refs={ref_count} prompts={prompt_count} L1≥{threshold}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    subcmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    data = sys.stdin.read() if not sys.stdin.isatty() else ""

    # Parse event once — session_id is extracted here and passed to all subcommands.
    # cmd_queue receives the parsed event too so it can embed session_id in each entry.
    event = parse_event(data)
    session_id = extract_session_id(event)

    try:
        vault = get_vault_path()
    except Exception as e:
        warn(f"vault not found: {e}")
        sys.exit(0)

    # cmd_queue is fast-path: no DB needed, write and exit
    if subcmd == "queue":
        cmd_queue(data, vault, session_id, event)
        sys.exit(0)

    try:
        conn = get_db(vault)
    except Exception as e:
        warn(f"db init failed: {e}")
        sys.exit(0)

    try:
        if subcmd == "extract":
            cmd_extract(data, vault, conn, session_id)
        elif subcmd == "worker":
            cmd_worker(vault, conn, session_id)
        elif subcmd == "checkpoint":
            cmd_checkpoint(vault, conn, session_id)
        elif subcmd == "flush":
            cmd_flush(vault, conn, session_id)
        else:
            warn(f"unknown subcommand: {subcmd}")
    except Exception as e:
        warn(f"unhandled error in {subcmd}: {e}")
    finally:
        conn.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
