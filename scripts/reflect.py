#!/usr/bin/env python3
"""
reflect.py — lightweight post-pass: inject related References/ wikilinks into drafts.

Reads distill-writer.py JSON output from stdin ({"written": [{"path": ..., "title": ...}]}).
For each written draft, scans existing References/ notes, scores relevance by
keyword overlap, and appends up to MAX_LINKS [[wikilinks]] to ## 関連資料.

Deterministic and fast — no claude -p call, no network. Always exits 0 (fail-open).

Usage (from session-distill.sh):
  echo "$WRITER_JSON" | SECOND_BRAIN_VAULT_PATH=... python3 reflect.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

MAX_LINKS = 5
REFERENCES_DIR = "References"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def warn(msg: str) -> None:
    print(f"reflect: {msg}", file=sys.stderr)


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


def tokenize(text: str) -> set[str]:
    """Extract lowercase words (>= 3 chars) from mixed Japanese/ASCII text."""
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}|[ぁ-ん一-龯]{2,}", text)}


def load_references(vault: pathlib.Path) -> list[dict]:
    """Load all References/ notes with stem, title, and topic for matching."""
    refs_dir = vault / REFERENCES_DIR
    if not refs_dir.exists():
        return []

    refs = []
    for path in sorted(refs_dir.glob("*.md")):
        stem = path.stem
        title = stem
        topic = ""
        try:
            text = path.read_text(encoding="utf-8")
            m_title = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
            m_topic = re.search(r"^topic:\s*(.+)$", text, re.MULTILINE)
            if m_title:
                title = m_title.group(1).strip()
            if m_topic:
                topic = m_topic.group(1).strip()
        except OSError:
            pass
        refs.append({"stem": stem, "title": title, "topic": topic})
    return refs


def score_relevance(draft_tokens: set[str], ref: dict) -> int:
    ref_tokens = tokenize(f"{ref['stem']} {ref['title']} {ref['topic']}")
    return len(draft_tokens & ref_tokens)


def find_related(draft_path: pathlib.Path, vault: pathlib.Path, refs: list[dict]) -> list[str]:
    """Return up to MAX_LINKS wikilink strings for the most relevant references."""
    if not refs:
        return []

    try:
        text = draft_path.read_text(encoding="utf-8")
    except OSError:
        return []

    m_title = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    m_topic = re.search(r"^topic:\s*(.+)$", text, re.MULTILINE)
    title = m_title.group(1).strip() if m_title else ""
    topic = m_topic.group(1).strip() if m_topic else ""

    # Include body sections (## 目的, ## 手順) for better recall
    body_sections = re.findall(r"^##\s+(?:目的|手順|Purpose|Steps)\s*\n(.*?)(?=\n##|\Z)", text, re.MULTILINE | re.DOTALL)
    body_text = " ".join(s.strip() for s in body_sections)

    draft_tokens = tokenize(f"{title} {topic} {body_text}")
    if not draft_tokens:
        return []

    scored = sorted(
        ((score_relevance(draft_tokens, ref), ref) for ref in refs),
        key=lambda x: x[0],
        reverse=True,
    )
    return [
        f"[[References/{r['stem']}]]"
        for score, r in scored[:MAX_LINKS]
        if score > 0
    ]


def inject_links(draft_path: pathlib.Path, links: list[str]) -> bool:
    """Append wikilinks to ## 関連資料 section. Returns True on success."""
    if not links:
        return False

    try:
        text = draft_path.read_text(encoding="utf-8")
    except OSError:
        return False

    # Filter out links already present; add only new ones
    links = [link for link in links if link not in text]
    if not links:
        return False

    link_block = "\n".join(f"- {link}" for link in links)
    section = "## 関連資料"

    if section in text:
        idx = text.rindex(section) + len(section)
        next_h2 = text.find("\n## ", idx)
        insert_at = next_h2 if next_h2 != -1 else len(text)
        text = text[:insert_at].rstrip("\n") + f"\n{link_block}\n" + text[insert_at:]
    else:
        text = text.rstrip("\n") + f"\n\n{section}\n{link_block}\n"

    try:
        draft_path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def main() -> int:
    vault = get_vault_path()
    if vault is None:
        warn("vault not found — skipping")
        return 0

    raw = sys.stdin.read().strip()
    if not raw:
        return 0

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    written = data.get("written", [])
    if not written:
        return 0

    refs = load_references(vault)
    if not refs:
        return 0

    injected = 0
    for entry in written:
        rel_path = entry.get("path", "")
        if not rel_path:
            continue
        draft_path = vault / rel_path
        if not draft_path.exists():
            continue

        links = find_related(draft_path, vault, refs)
        if inject_links(draft_path, links):
            injected += 1

    if injected:
        print(f"reflect: injected links into {injected} draft(s)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
