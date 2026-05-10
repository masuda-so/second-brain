#!/bin/bash
# weekly-draft.sh — SessionStart hook: auto-create Weekly draft on Mondays.
#
# Fires on SessionStart. If today is Monday AND Weekly/YYYY-Www.md does not
# yet exist, creates a draft with:
#   - frontmatter (reviewed: false, generated: true)
#   - ## 進行中プロジェクト populated from active Projects/*.md
#   - ## 関連ノート with links to this week's Daily notes found so far
#   - placeholders for sections requiring LLM synthesis (/note weekly)
# Appends a notification to Daily ## AI Session.
# Always exits 0 (fail-open). Does not overwrite existing notes.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

warn() { echo "second-brain: weekly-draft: $*" >&2; }
bail() { warn "$*"; exit 0; }

command -v python3 >/dev/null 2>&1 || bail "python3 required"

# ── Vault path ────────────────────────────────────────────────────────────────

VAULT_PATH="${SECOND_BRAIN_VAULT_PATH:-}"
if [[ -z "$VAULT_PATH" ]]; then
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
fi
VAULT_PATH="${VAULT_PATH%/}"
[[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]] || bail "vault not found"

# ── Only run on Monday ────────────────────────────────────────────────────────
# DOW: 1=Monday … 7=Sunday (ISO)
DOW="$(date '+%u')"
[[ "$DOW" == "1" ]] || exit 0

# ── Resolve week identifier ───────────────────────────────────────────────────

TODAY="$(date '+%Y-%m-%d')"
WEEK_ID="$(date '+%Y-W%V')"          # e.g. 2026-W15
WEEKLY_DIR="${VAULT_PATH}/Weekly"
WEEKLY_NOTE="${WEEKLY_DIR}/${WEEK_ID}.md"
DAILY_DIR="${VAULT_PATH}/${SECOND_BRAIN_DAILY_DIR:-Daily}"
TIME_LABEL="$(date '+%H:%M')"
DAILY_NOTE="${DAILY_DIR}/${TODAY}.md"

# ── Idempotency: skip if already exists ──────────────────────────────────────

[[ -f "$WEEKLY_NOTE" ]] && exit 0

# ── Build draft via Python ────────────────────────────────────────────────────

python3 - "$VAULT_PATH" "$WEEKLY_NOTE" "$WEEK_ID" "$TODAY" "$WEEKLY_DIR" "$DAILY_DIR" <<'PY'
import sys, pathlib, re, json
from datetime import datetime, timedelta

vault       = pathlib.Path(sys.argv[1])
note_path   = pathlib.Path(sys.argv[2])
week_id     = sys.argv[3]   # e.g. 2026-W15
today_str   = sys.argv[4]
weekly_dir  = pathlib.Path(sys.argv[5])
daily_dir   = pathlib.Path(sys.argv[6])

today = datetime.strptime(today_str, "%Y-%m-%d")

# ── Collect active projects ──────────────────────────────────────────────────
projects_dir = vault / "Projects"
active_projects = []
if projects_dir.is_dir():
    for p in sorted(projects_dir.glob("*.md")):
        try:
            text = p.read_text(errors="ignore")
            if re.search(r"status:\s*active", text, re.IGNORECASE):
                stem = p.stem
                active_projects.append(f"- [[Projects/{stem}]]")
        except Exception:
            pass

# ── Collect this week's Daily notes (Mon–today) ──────────────────────────────
daily_links = []
for i in range(7):
    d = today - timedelta(days=today.weekday() - i)
    if d > today:
        break
    label = d.strftime("%Y-%m-%d")
    dp = daily_dir / f"{label}.md"
    if dp.exists():
        daily_links.append(f"- [[Daily/{label}]]")

# ── Build frontmatter + sections ─────────────────────────────────────────────
projects_section = "\n".join(active_projects) if active_projects else "（自動取得なし — アクティブプロジェクトなし）"
daily_section    = "\n".join(daily_links) if daily_links else "（今週の Daily ノートなし）"

draft = f"""\
---
title: {week_id}
type: weekly
week: {week_id}
reviewed: {today_str}
reviewed_status: false
generated: true
tags:
  - planning
  - review
---
<!-- Auto-generated draft. Run /note weekly to synthesize content. -->

## 進行中プロジェクト

{projects_section}

## 昇格候補アイデア

<!-- /note weekly で先週の Ideas/ から候補を抽出 -->

## ブロッカー

<!-- /note weekly で先週のセッションログからブロッカーを抽出 -->

> [!tip] 週次の要約
> 重要度の高い項目だけ Projects に昇格し、残りは保留または整理する。

## 来週の重点

<!-- /note weekly で生成 -->

## 関連ノート

{daily_section}
"""

note_path.parent.mkdir(parents=True, exist_ok=True)
note_path.write_text(draft)
print("ok")
PY

rc=$?
if [[ $rc -ne 0 ]]; then
  bail "draft generation failed (exit $rc)"
fi

# ── Notify in Daily ## AI Session ────────────────────────────────────────────

if [[ -f "$DAILY_NOTE" ]]; then
  python3 - "$DAILY_NOTE" "$TIME_LABEL" "$WEEK_ID" <<'PY'
import sys, pathlib, fcntl, time

daily_path = pathlib.Path(sys.argv[1])
time_label = sys.argv[2]
week_id    = sys.argv[3]

entry = f"\n- {time_label} Weekly draft created: [[Weekly/{week_id}]] (reviewed_status: false — run /note weekly to synthesize)\n"

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
        heading = "## AI Session"
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
PY
fi

exit 0
