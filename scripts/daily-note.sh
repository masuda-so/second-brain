#!/bin/bash
# daily-note.sh — SessionStart hook: auto-create Daily note if not exists.
#
# Fires on SessionStart. If Daily/YYYY-MM-DD.md does not exist, creates it with:
#   - frontmatter (type: daily, date, tags)
#   - ## 今日のフォーカス with active Projects list
#   - ## メモ with 振り返り callout
#   - ## フォローアップ with unchecked items carried over from yesterday
#   - ## 関連ノート (empty)
#   - ## AI Session (empty, ready for session entries)
# Always exits 0 (fail-open). Does not overwrite existing notes.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

warn() { echo "second-brain: daily-note: $*" >&2; }
bail() { warn "$*"; exit 0; }

command -v python3 >/dev/null 2>&1 || bail "python3 required"

# ── Vault path ────────────────────────────────────────────────────────────────

VAULT_PATH="${SECOND_BRAIN_VAULT_PATH:-}"
if [[ -z "$VAULT_PATH" ]]; then
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
fi
VAULT_PATH="${VAULT_PATH%/}"
[[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]] || bail "vault not found"

# ── Resolve paths ─────────────────────────────────────────────────────────────

TODAY="$(date '+%Y-%m-%d')"
DAILY_DIR="${VAULT_PATH}/${SECOND_BRAIN_DAILY_DIR:-Daily}"
DAILY_NOTE="${DAILY_DIR}/${TODAY}.md"

# ── Idempotency: skip if already exists ──────────────────────────────────────

[[ -f "$DAILY_NOTE" ]] && exit 0

# ── Build note via Python ─────────────────────────────────────────────────────

python3 - "$VAULT_PATH" "$DAILY_NOTE" "$TODAY" "$DAILY_DIR" <<'PY'
import sys, pathlib, re
from datetime import datetime, timedelta

vault      = pathlib.Path(sys.argv[1])
note_path  = pathlib.Path(sys.argv[2])
today_str  = sys.argv[3]
daily_dir  = pathlib.Path(sys.argv[4])

today     = datetime.strptime(today_str, "%Y-%m-%d")
yesterday = today - timedelta(days=1)
yesterday_str = yesterday.strftime("%Y-%m-%d")

# ── Collect active projects ──────────────────────────────────────────────────
projects_dir = vault / "Projects"
active_projects = []
if projects_dir.is_dir():
    for p in sorted(projects_dir.glob("*.md")):
        try:
            text = p.read_text(errors="ignore")
            if re.search(r"status:\s*active", text, re.IGNORECASE):
                active_projects.append(f"- [[Projects/{p.stem}]]")
        except Exception:
            pass

# ── Carry over unchecked フォローアップ from yesterday ───────────────────────
followup_items = []
yesterday_note = daily_dir / f"{yesterday_str}.md"
if yesterday_note.exists():
    try:
        text = yesterday_note.read_text(errors="ignore")
        in_followup = False
        for line in text.splitlines():
            if re.match(r"^## フォローアップ", line):
                in_followup = True
                continue
            if in_followup:
                if re.match(r"^## ", line):
                    break
                if re.match(r"^- \[ \]", line):
                    followup_items.append(line)
    except Exception:
        pass

# ── Build note ────────────────────────────────────────────────────────────────
focus_section    = "\n".join(active_projects) if active_projects else ""
followup_section = "\n".join(followup_items) if followup_items else "- [ ] "

draft = f"""\
---
type: daily
date: {today_str}
tags:
  - journal
---
## 今日のフォーカス

{focus_section}

## メモ

> [!note] 振り返り

## フォローアップ

{followup_section}

## 関連ノート

## AI Session
"""

note_path.parent.mkdir(parents=True, exist_ok=True)
note_path.write_text(draft)
print("ok")
PY

rc=$?
[[ $rc -ne 0 ]] && bail "draft generation failed (exit $rc)"

exit 0
