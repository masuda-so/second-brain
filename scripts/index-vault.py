#!/usr/bin/env python3
"""
index-vault.py — Vault Index Builder
=====================================
Scans the Obsidian vault, extracts metadata from each note, and maintains
a vault_index table in Meta/.cache/memory.db. Also generates a lightweight
Meta/index.md for LLM context injection at SessionStart.

Subcommands:
  build   — full rebuild: scan all notes, upsert index, generate index.md
  update  — incremental: only re-index notes whose mtime changed
  query   — search the index (keywords from argv), return top-N as JSON

Uses the same memory.db as harvest.py. WAL + busy_timeout for safe parallel access.
Always exits 0 (fail-open).

Usage:
  python3 index-vault.py build
  python3 index-vault.py update
  python3 index-vault.py query "keyword1 keyword2" [--limit N]
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import sys
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

BUSY_TIMEOUT_MS = 5000

# Directories to index (knowledge notes)
INDEX_DIRS = ("References", "Ideas", "Projects", "Daily", "Weekly", "Monthly",
              "Clippings", "Bases", "Meta/Promotions", "Meta/Profile")

# Directories to skip
SKIP_DIRS = ("Sandbox", "Templates", "Meta/AI Sessions", "Meta/.cache",
             ".obsidian", ".trash")

# Max notes to include in index.md per category
INDEX_MD_LIMIT = 50

FM_DELIM_RE = re.compile(r"^\s*---\s*$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")

# Directory display order for index.md
DIR_ORDER = ["Projects", "References", "Ideas", "Daily", "Weekly",
             "Monthly", "Clippings", "Meta/Promotions", "Meta/Profile", "Bases"]

# ── Helpers ───────────────────────────────────────────────────────────────────


def warn(msg: str) -> None:
    print(f"index-vault: {msg}", file=sys.stderr)


def get_vault_path() -> pathlib.Path | None:
    env = os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip()
    if env:
        p = pathlib.Path(env).expanduser()
        return p if p.is_dir() else None
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            m = re.match(r"^- Location: `(.+)`", line)
            if m:
                p = pathlib.Path(m.group(1).strip()).expanduser()
                return p if p.is_dir() else None
    return None


def get_db(vault: pathlib.Path) -> sqlite3.Connection:
    db_dir = vault / "Meta" / ".cache"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vault_index (
            rel_path     TEXT PRIMARY KEY,
            title        TEXT,
            note_type    TEXT,
            directory    TEXT,
            summary      TEXT,
            tags         TEXT,
            body_chars   INTEGER DEFAULT 0,
            outbound     INTEGER DEFAULT 0,
            updated_at   TEXT,
            mtime        REAL
        );
    """)
    conn.commit()


def should_skip(rel: str) -> bool:
    return any(rel.startswith(s) for s in SKIP_DIRS)


def should_index(rel: str) -> bool:
    return any(rel.startswith(d) for d in INDEX_DIRS)


def parse_frontmatter(text: str) -> dict[str, str]:
    matches = list(FM_DELIM_RE.finditer(text))
    if len(matches) < 2:
        return {}
    if text[:matches[0].start()].strip():
        return {}
    fm_text = text[matches[0].end():matches[1].start()]
    result: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m:
            result[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return result


def extract_title(text: str, fm: dict[str, str], stem: str) -> str:
    """Extract title: frontmatter title > first H1 > filename stem."""
    if fm.get("title"):
        return fm["title"]
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return stem


def extract_summary(text: str) -> str:
    """Extract first meaningful body line as one-line summary."""
    delims = list(FM_DELIM_RE.finditer(text))
    body = text[delims[1].end():] if len(delims) >= 2 else text

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue
        if stripped.startswith(">"):
            # Callout/blockquote — use content after marker
            stripped = re.sub(r"^>\s*(\[![^\]]*\]\s*)?", "", stripped).strip()
            if not stripped:
                continue
        # Truncate to 120 chars
        return stripped[:117] + "..." if len(stripped) > 120 else stripped
    return ""


def extract_tags(fm: dict[str, str], text: str) -> str:
    """Extract tags from frontmatter or inline #tags."""
    tags: list[str] = []
    # Frontmatter tags (may be empty if YAML list)
    fm_tags = fm.get("tags", "")
    if fm_tags:
        tags.extend(t.strip() for t in fm_tags.split(",") if t.strip())

    # Also pick up YAML list items right after tags: key
    tag_section = re.search(r"^\s*tags:\s*$\n((?:\s*-\s*.+\n?)+)", text, re.MULTILINE)
    if tag_section:
        for m in re.finditer(r"-\s*(.+)", tag_section.group(1)):
            tag = m.group(1).strip()
            if tag and tag not in tags:
                tags.append(tag)

    return ", ".join(tags)


def count_outbound_links(text: str) -> int:
    return len(WIKILINK_RE.findall(text))


def body_char_count(text: str) -> int:
    delims = list(FM_DELIM_RE.finditer(text))
    body = text[delims[1].end():] if len(delims) >= 2 else text
    body_lines = [
        line for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return sum(len(line.strip()) for line in body_lines)


def infer_directory(rel: str) -> str:
    """Return the top-level directory from a relative path."""
    parts = pathlib.PurePosixPath(rel).parts
    if len(parts) >= 2 and parts[0] == "Meta":
        return f"Meta/{parts[1]}"
    return parts[0] if parts else ""


# ── Core ──────────────────────────────────────────────────────────────────────


def scan_note(note: pathlib.Path, vault: pathlib.Path) -> dict | None:
    """Extract index metadata from a single note."""
    rel = str(note.relative_to(vault))
    rel_no_ext = re.sub(r"\.md$", "", rel)

    if should_skip(rel) or not should_index(rel):
        return None

    try:
        text = note.read_text(encoding="utf-8", errors="ignore")
        mtime = note.stat().st_mtime
    except OSError:
        return None

    fm = parse_frontmatter(text)
    return {
        "rel_path": rel_no_ext,
        "title": extract_title(text, fm, note.stem),
        "note_type": fm.get("type", ""),
        "directory": infer_directory(rel),
        "summary": extract_summary(text),
        "tags": extract_tags(fm, text),
        "body_chars": body_char_count(text),
        "outbound": count_outbound_links(text),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mtime": mtime,
    }


def build_index(vault: pathlib.Path, incremental: bool = False) -> dict:
    """Scan vault and upsert into vault_index. Returns stats."""
    t0 = time.monotonic()
    conn = get_db(vault)

    # Get existing mtimes for incremental mode
    existing: dict[str, float] = {}
    if incremental:
        for row in conn.execute("SELECT rel_path, mtime FROM vault_index"):
            existing[row["rel_path"]] = row["mtime"]

    # Collect current notes
    current_paths: set[str] = set()
    upserted = 0
    skipped = 0

    for md in sorted(vault.rglob("*.md")):
        rel = str(md.relative_to(vault))
        if should_skip(rel) or not should_index(rel):
            continue
        # Skip vault root files
        if len(md.relative_to(vault).parts) < 2:
            continue

        rel_no_ext = re.sub(r"\.md$", "", rel)
        current_paths.add(rel_no_ext)

        # Incremental: skip if mtime unchanged
        if incremental and rel_no_ext in existing:
            try:
                current_mtime = md.stat().st_mtime
            except OSError:
                continue
            if abs(current_mtime - existing[rel_no_ext]) < 0.01:
                skipped += 1
                continue

        row = scan_note(md, vault)
        if row is None:
            continue

        conn.execute("""
            INSERT INTO vault_index
                (rel_path, title, note_type, directory, summary, tags,
                 body_chars, outbound, updated_at, mtime)
            VALUES
                (:rel_path, :title, :note_type, :directory, :summary, :tags,
                 :body_chars, :outbound, :updated_at, :mtime)
            ON CONFLICT(rel_path) DO UPDATE SET
                title=excluded.title, note_type=excluded.note_type,
                directory=excluded.directory, summary=excluded.summary,
                tags=excluded.tags, body_chars=excluded.body_chars,
                outbound=excluded.outbound, updated_at=excluded.updated_at,
                mtime=excluded.mtime
        """, row)
        upserted += 1

    # Remove deleted notes from index
    removed = 0
    if not incremental:
        # Full build: remove anything not in current_paths
        for row in conn.execute("SELECT rel_path FROM vault_index"):
            if row["rel_path"] not in current_paths:
                conn.execute("DELETE FROM vault_index WHERE rel_path = ?",
                             (row["rel_path"],))
                removed += 1
    else:
        # Incremental: check existing entries that weren't visited
        for rel_path in existing:
            if rel_path not in current_paths:
                conn.execute("DELETE FROM vault_index WHERE rel_path = ?",
                             (rel_path,))
                removed += 1

    conn.commit()
    conn.close()

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "upserted": upserted,
        "skipped": skipped,
        "removed": removed,
        "total": len(current_paths),
        "elapsed_ms": elapsed,
    }


def generate_index_md(vault: pathlib.Path) -> str:
    """Generate Meta/index.md from the vault_index table."""
    conn = get_db(vault)

    rows = conn.execute("""
        SELECT rel_path, title, note_type, directory, summary, tags
        FROM vault_index
        ORDER BY directory, title
    """).fetchall()
    conn.close()

    # Group by directory
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        d = row["directory"]
        groups.setdefault(d, []).append(row)

    now = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = [
        "---",
        "type: meta",
        f"generated: {now}",
        f"total_notes: {len(rows)}",
        "---",
        "",
    ]

    for dir_name in DIR_ORDER:
        notes = groups.pop(dir_name, [])
        if not notes:
            continue
        lines.append(f"## {dir_name} ({len(notes)})")
        lines.append("")
        for note in notes[:INDEX_MD_LIMIT]:
            path = note["rel_path"]
            title = note["title"] or path.split("/")[-1]
            summary = note["summary"]
            type_tag = note["note_type"]
            parts: list[str] = [f"- [[{path}]]"]
            if type_tag:
                parts.append(f"*{type_tag}*")
            if summary:
                parts.append(f"— {summary}")
            lines.append(" ".join(parts))
        lines.append("")

    # Any remaining directories not in DIR_ORDER
    for dir_name, notes in sorted(groups.items()):
        if not notes:
            continue
        lines.append(f"## {dir_name} ({len(notes)})")
        lines.append("")
        for note in notes[:INDEX_MD_LIMIT]:
            path = note["rel_path"]
            title = note["title"] or path.split("/")[-1]
            summary = note["summary"]
            parts = [f"- [[{path}]]"]
            if summary:
                parts.append(f"— {summary}")
            lines.append(" ".join(parts))
        lines.append("")

    return "\n".join(lines)


def query_index(vault: pathlib.Path, keywords: list[str], limit: int = 10) -> list[dict]:
    """Search the index by keywords (OR), score by match count, return top-N."""
    conn = get_db(vault)

    if not keywords:
        conn.close()
        return []

    # Score each keyword match: title(3) + summary(2) + tags(2) + rel_path(1)
    score_parts: list[str] = []
    params: list[str] = []
    where_parts: list[str] = []
    for kw in keywords:
        like = f"%{kw}%"
        score_parts.append(
            "(CASE WHEN title LIKE ? THEN 3 ELSE 0 END"
            " + CASE WHEN summary LIKE ? THEN 2 ELSE 0 END"
            " + CASE WHEN tags LIKE ? THEN 2 ELSE 0 END"
            " + CASE WHEN rel_path LIKE ? THEN 1 ELSE 0 END)"
        )
        params.extend([like, like, like, like])
        where_parts.append(
            "(title LIKE ? OR summary LIKE ? OR tags LIKE ? OR rel_path LIKE ?)"
        )
        params.extend([like, like, like, like])

    score_expr = " + ".join(score_parts)
    where_expr = " OR ".join(where_parts)

    rows = conn.execute(f"""
        SELECT rel_path, title, note_type, directory, summary, tags,
               body_chars, outbound, mtime,
               ({score_expr}) AS score
        FROM vault_index
        WHERE {where_expr}
        ORDER BY score DESC, body_chars DESC
        LIMIT ?
    """, [*params, limit]).fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: index-vault.py {build|update|query} [args]", file=sys.stderr)
        return 0

    subcmd = sys.argv[1]
    vault = get_vault_path()
    if vault is None:
        warn("vault not found — skipping")
        return 0

    if subcmd == "build":
        stats = build_index(vault, incremental=False)
        # Generate index.md
        index_md = generate_index_md(vault)
        index_path = vault / "Meta" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(index_md, encoding="utf-8")
        stats["index_md"] = str(index_path)
        print(json.dumps(stats, ensure_ascii=False))

    elif subcmd == "update":
        stats = build_index(vault, incremental=True)
        # Regenerate index.md
        index_md = generate_index_md(vault)
        index_path = vault / "Meta" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(index_md, encoding="utf-8")
        stats["index_md"] = str(index_path)
        print(json.dumps(stats, ensure_ascii=False))

    elif subcmd == "query":
        kw_str = sys.argv[2] if len(sys.argv) > 2 else ""
        limit = 10
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        keywords = [w for w in kw_str.lower().split() if len(w) >= 2]
        results = query_index(vault, keywords, limit=limit)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    else:
        warn(f"unknown subcommand: {subcmd}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
