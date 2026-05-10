#!/usr/bin/env python3
"""
promote.py — Phase 2: promote approved Promotions/ drafts to canonical vault.

Scans Meta/Promotions/draft-*.md, checks each against promotion criteria,
and copies approved drafts to their promotion_target (References/ or Ideas/).

Safety constraints:
  - Only promotes to References/ and Ideas/ (Projects/ requires manual append)
  - Never overwrites existing canonical files
  - Only promotes action: create (not append — that is manual)
  - Marks source draft as promoted: true (never deletes)
  - reviewed_status remains false on promoted note (human review still needed)
  - Appends [[link]] to Daily ## 関連ノート with fcntl lock
  - Logs to Daily ## AI Session

Usage:
  python3 promote.py [--dry-run] [--date YYYY-MM-DD] [--limit N]

Returns JSON:
  {"promoted": [...], "skipped": [...], "errors": [...]}
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

PROMOTIONS_SUBDIR = "Meta/Promotions"
DRAFT_GLOB = "draft-*.md"

# Only auto-promote into these directories
PROMOTE_ALLOWLIST = ("References/", "Ideas/")

# Frontmatter fields to strip from promoted notes (promotion metadata)
STRIP_FM_KEYS = {"promotion_target", "promotion_action"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def warn(msg: str) -> None:
    print(f"promote: {msg}", file=sys.stderr)


def get_vault_path() -> pathlib.Path:
    env = os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip()
    if env:
        return pathlib.Path(env).expanduser()
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            m = re.match(r"^- Location: `(.+)`", line)
            if m:
                return pathlib.Path(m.group(1).strip()).expanduser()
    raise RuntimeError("vault path not found")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (flat frontmatter dict, body) from markdown text."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return {}, text
    fm: dict = {}
    current_key: str | None = None
    list_items: list[str] = []
    for line in m.group(1).splitlines():
        kv = re.match(r"^([\w_-]+)\s*:\s*(.*)", line)
        if kv:
            # Save previous list
            if current_key and list_items:
                fm[current_key] = list_items
                list_items = []
            current_key = kv.group(1)
            val = kv.group(2).strip()
            if val == "":
                # Value will be a list
                pass
            elif val.lower() == "true":
                fm[current_key] = True
            elif val.lower() == "false":
                fm[current_key] = False
            else:
                # Strip surrounding quotes
                fm[current_key] = val.strip("'\"")
                current_key = None  # scalar consumed
        elif line.startswith("  - ") and current_key:
            list_items.append(line.strip()[2:])
    if current_key and list_items:
        fm[current_key] = list_items
    return fm, text[m.end():]


def set_frontmatter_flag(text: str, key: str, value: str) -> str:
    """Update or insert a scalar frontmatter key in markdown text."""
    fm_m = re.match(r"^(---\n)(.*?)(\n---\n?)", text, re.DOTALL)
    if not fm_m:
        return text
    fm_block = fm_m.group(2)
    # Replace existing key
    new_line = f"{key}: {value}"
    if re.search(rf"^{key}\s*:", fm_block, re.MULTILINE):
        fm_block = re.sub(rf"^{key}\s*:.*$", new_line, fm_block, flags=re.MULTILINE)
    else:
        fm_block = fm_block.rstrip("\n") + f"\n{new_line}"
    return fm_m.group(1) + fm_block + fm_m.group(3) + text[fm_m.end():]


def strip_frontmatter_keys(text: str, keys: set[str]) -> str:
    """Remove specific keys from frontmatter."""
    fm_m = re.match(r"^(---\n)(.*?)(\n---\n?)", text, re.DOTALL)
    if not fm_m:
        return text
    lines = []
    for line in fm_m.group(2).splitlines():
        kv = re.match(r"^([\w_-]+)\s*:", line)
        if kv and kv.group(1) in keys:
            continue
        lines.append(line)
    return fm_m.group(1) + "\n".join(lines) + fm_m.group(3) + text[fm_m.end():]


def append_to_daily_section(daily_path: pathlib.Path, heading: str, entry: str) -> bool:
    """Append entry under a heading in Daily note using fcntl lock."""
    lock_path = daily_path.parent / f".{daily_path.name}.lock"
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
        if acquired:
            text = daily_path.read_text()
            if heading in text:
                idx = text.rindex(heading) + len(heading)
                next_h2 = text.find("\n## ", idx)
                if next_h2 == -1:
                    text = text.rstrip("\n") + entry
                else:
                    text = text[:next_h2] + entry + text[next_h2:]
            else:
                text = text.rstrip("\n") + f"\n\n{heading}{entry}"
            daily_path.write_text(text)
    finally:
        if acquired:
            fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()
    return acquired


# ── Promotion logic ───────────────────────────────────────────────────────────


def check_promotable(fm: dict, vault: pathlib.Path) -> tuple[bool, str]:
    """Return (promotable, reason). reason is empty string if promotable."""
    if fm.get("promoted") is True or str(fm.get("promoted", "")).lower() == "true":
        return False, "already promoted"
    target = str(fm.get("promotion_target", "")).strip()
    if not target:
        return False, "no promotion_target"
    if not any(target.startswith(d) for d in PROMOTE_ALLOWLIST):
        return False, f"target not in allowlist: {target}"
    action = str(fm.get("promotion_action", "create")).strip()
    if action != "create":
        return False, f"action={action} (only 'create' is auto-promoted)"
    if (vault / target).exists():
        return False, f"target already exists: {target}"
    for key in ("title", "type", "source_session"):
        if not fm.get(key):
            return False, f"missing required field: {key}"
    return True, ""


def build_promoted_content(draft_text: str) -> str:
    """Strip promotion metadata from draft for the promoted canonical note."""
    return strip_frontmatter_keys(draft_text, STRIP_FM_KEYS)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 promotion script")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--limit", type=int, default=20, help="Max promotions per run")
    args = parser.parse_args()

    try:
        vault = get_vault_path()
    except RuntimeError as exc:
        warn(str(exc))
        print(json.dumps({"promoted": [], "skipped": [], "errors": [str(exc)]}))
        return 0

    promotions_dir = vault / PROMOTIONS_SUBDIR
    if not promotions_dir.is_dir():
        print(json.dumps({"promoted": [], "skipped": [], "errors": []}))
        return 0

    daily_dir = os.environ.get("SECOND_BRAIN_DAILY_DIR", "Daily")
    daily_note = vault / daily_dir / f"{args.date}.md"
    time_label = datetime.now().strftime("%H:%M")

    drafts = sorted(promotions_dir.glob(DRAFT_GLOB))
    promoted_list: list[dict] = []
    skipped_list: list[dict] = []
    errors_list: list[str] = []

    for draft_path in drafts:
        if len(promoted_list) >= args.limit:
            break
        try:
            text = draft_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors_list.append(f"{draft_path.name}: read error: {exc}")
            continue

        fm, _ = parse_frontmatter(text)
        promotable, reason = check_promotable(fm, vault)

        if not promotable:
            skipped_list.append({"file": draft_path.name, "reason": reason})
            continue

        target = str(fm["promotion_target"]).strip()
        target_path = vault / target
        title = str(fm.get("title", draft_path.stem))

        if args.dry_run:
            promoted_list.append({
                "draft": draft_path.name,
                "target": target,
                "title": title,
                "dry_run": True,
            })
            continue

        # Write promoted note
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            promoted_content = build_promoted_content(text)
            target_path.write_text(promoted_content, encoding="utf-8")
        except OSError as exc:
            errors_list.append(f"{draft_path.name}: write error: {exc}")
            continue

        # Mark draft as promoted
        try:
            updated = set_frontmatter_flag(text, "promoted", "true")
            updated = set_frontmatter_flag(updated, "promoted_date", args.date)
            draft_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            warn(f"could not mark draft as promoted: {exc}")

        # Append link to Daily ## 関連ノート
        target_link = target.removesuffix(".md")
        if daily_note.exists():
            append_to_daily_section(
                daily_note,
                "## 関連ノート",
                f"\n- [[{target_link}]] (promoted from Promotions)\n",
            )

        promoted_list.append({
            "draft": draft_path.name,
            "target": target,
            "title": title,
        })

    # Append summary to Daily ## AI Session
    if not args.dry_run and promoted_list and daily_note.exists():
        lines = [f"  - [[{p['target'].removesuffix('.md')}]] ← {p['draft']}" for p in promoted_list]
        summary = "\n".join(lines)
        append_to_daily_section(
            daily_note,
            "## AI Session",
            f"\n- {time_label} [promote] {len(promoted_list)} drafts to vault\n{summary}\n",
        )

    print(json.dumps(
        {"promoted": promoted_list, "skipped": skipped_list, "errors": errors_list},
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
