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
    r"^(ok|okay|yes|no|はい|いいえ|わかりました|了解|ありがとう|thanks?|sure|got\s*it)\W*$",
    re.IGNORECASE,
)

SKIP_TITLES = {"", "untitled", "note", "notes", "misc", "todo"}


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


def get_session_id() -> str:
    raw = (
        os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or "unknown-session"
    )
    return re.sub(r"[^A-Za-z0-9._-]", "-", raw).strip("-") or "unknown-session"


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
    found.update(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text))
    found.update(re.findall(r"`([^`\n]{3,40})`", text))
    return list(found)[:20]


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

    tag_str = ", ".join(f'"{t}"' for t in (tags or []))
    note_type = "idea" if target_dir == "Ideas" else "staged"
    front = textwrap.dedent(f"""\
        ---
        title: "{title}"
        type: {note_type}
        created: {today}
        source: "{source}"
        tags: [{tag_str}]
        promoted: false
        ---
    """)
    try:
        with _file_lock(path):
            path.write_text(front + "\n" + content + "\n")
    except RuntimeError as e:
        warn(f"skipping note creation {path.name}: {e}")
        raise  # propagate so caller can skip DB update
    return path


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

def promote_l1(vault: pathlib.Path, conn: sqlite3.Connection) -> int:
    """Auto-promote to Ideas/ immediately."""
    rows = conn.execute("""
        SELECT * FROM candidates
        WHERE status='pending' AND importance >= ? AND target_dir='Ideas'
        ORDER BY importance DESC LIMIT 20
    """, (L1_THRESHOLD,)).fetchall()
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
        conn.execute("""
            INSERT INTO prompt_counter (session_id, count) VALUES (?, 1)
            ON CONFLICT(session_id) DO UPDATE SET count = count + 1
        """, (session_id,))
        conn.commit()
        if not NOISE_RE.match(prompt.strip()):
            pieces.append(("prompt", prompt))

    # Tool events
    tool_name = event.get("tool_name", event.get("toolName", ""))
    tool_input = event.get("tool_input") or {}
    tool_resp = str(event.get("tool_response", event.get("tool_output", "")) or "")

    if tool_name in ("Write", "Edit", "MultiEdit"):
        fp = tool_input.get("file_path", "")
        body = tool_input.get("content", tool_input.get("new_string", ""))
        if body and len(body) > 40:
            pieces.append((f"write:{fp}", body[:MAX_CONTENT_LEN]))

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Skip pure noise commands
        if not BASH_NOISE_RE.match(cmd.strip()):
            out = tool_resp[:MAX_CONTENT_LEN]
            # Capture if command or output has signal
            if BASH_SIGNAL_RE.search(cmd) or BASH_SIGNAL_RE.search(out):
                if len(out) > 30:
                    pieces.append((f"bash:{cmd[:60]}", out))

    if tool_name in ("WebFetch", "WebSearch"):
        if len(tool_resp) > 60:
            pieces.append(("web", tool_resp[:MAX_CONTENT_LEN]))

    for source_label, text in pieces:
        entities = extract_entities(text)
        bonus = sum(upsert_entity(conn, e) for e in entities)
        enqueue_candidate(conn, session_id, source_label, text, bonus)

    # L1 always runs after extract
    promote_l1(vault, conn)


def cmd_checkpoint(vault: pathlib.Path, conn: sqlite3.Connection,
                   session_id: str) -> None:
    """Per-response (Stop hook): L1 always; L2 only every CHECKPOINT_EVERY prompts."""
    n1 = promote_l1(vault, conn)

    row = conn.execute(
        "SELECT count FROM prompt_counter WHERE session_id=?", (session_id,)
    ).fetchone()
    prompt_count = row["count"] if row else 0

    n2 = 0
    if prompt_count > 0 and prompt_count % CHECKPOINT_EVERY == 0:
        n2 = promote_l2(vault, conn)

    if n1 or n2:
        warn(f"checkpoint (prompt #{prompt_count}): +{n1} Ideas, +{n2} staged")


def cmd_flush(vault: pathlib.Path, conn: sqlite3.Connection,
              session_id: str) -> None:
    """SessionEnd: final sweep + L3 checklist in Daily note."""
    n1 = promote_l1(vault, conn)
    n2 = promote_l2(vault, conn)

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

    lines = [f"- {time_label} Harvest: +{promoted} Ideas, +{staged} staged to Meta/Promotions"]
    if l3_rows:
        lines.append(f"- {time_label} Needs manual review (→ References/):")
        for r in l3_rows:
            title = r["title"] or "untitled"
            vp = r["vault_path"] or "(not yet saved)"
            lines.append(f"  - [ ] **{title}** (score {r['importance']}) — {vp}")

    try:
        append_under_heading(daily_note, "AI Session", "\n".join(lines))
    except Exception as e:
        warn(f"flush: daily note update failed: {e}")

    warn(f"flush: promoted={promoted} staged={staged} l3_pending={len(l3_rows)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    subcmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    data = sys.stdin.read() if not sys.stdin.isatty() else ""

    try:
        vault = get_vault_path()
    except Exception as e:
        warn(f"vault not found: {e}")
        sys.exit(0)

    try:
        conn = get_db(vault)
    except Exception as e:
        warn(f"db init failed: {e}")
        sys.exit(0)

    session_id = get_session_id()

    try:
        if subcmd == "extract":
            cmd_extract(data, vault, conn, session_id)
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
