#!/bin/bash
# copilot-helpers.sh — Local authoring helpers using Copilot CLI
#
# Prerequisites: copilot CLI installed and authenticated
# Usage:
#   source scripts/copilot-helpers.sh
#
# Vault-unaware (repo diff only):
#   sb-commit-msg                         # Conventional Commit subject for staged diff
#   sb-review-pr [base]                   # code-level review (fail-open / race / portability)
#   sb-review-pr --with-vault-context     # same + matching project brief
#   sb-explain-harvest                    # explain harvest.py + hooks.json interplay
#
# Vault-aware (uses SECOND_BRAIN_VAULT_PATH — opt-in, local only):
#   sb-pr-context                         # PR description using project + daily context
#   sb-promotions-review                  # summarise Meta/Promotions/ queue
#   sb-idea-gardener                      # classify stale Ideas/ notes
#   sb-release-notes                      # release notes from commits + vault
#   sb-weekly-review                      # auto-draft this week's Weekly note body
#   sb-monthly-review                     # draft this month's Monthly note (preview only)
#
# Design rule:
#   harvest.py  → stub scaffolding (idempotent, deterministic, SessionEnd)
#   Copilot CLI → content synthesis (vault-aware, human-in-the-loop)
#   GitHub CI   → never uses real SECOND_BRAIN_VAULT_PATH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Prerequisites ─────────────────────────────────────────────────────────────

_require_copilot() {
  if ! command -v copilot >/dev/null 2>&1; then
    echo "error: copilot CLI not found." >&2
    echo "  See: https://docs.github.com/copilot/concepts/agents/about-copilot-cli" >&2
    return 1
  fi
}

_require_vault() {
  VAULT_PATH="${SECOND_BRAIN_VAULT_PATH:-}"
  if [[ -z "$VAULT_PATH" ]]; then
    VAULT_PATH=$(python3 -c "
import json, pathlib
try:
    d = json.load(open('$REPO_ROOT/settings.json'))
    print(d.get('env', {}).get('SECOND_BRAIN_VAULT_PATH', ''))
except Exception:
    pass
" 2>/dev/null)
  fi
  if [[ -z "$VAULT_PATH" || ! -d "$VAULT_PATH" ]]; then
    echo "error: vault not found. Set SECOND_BRAIN_VAULT_PATH in settings.json." >&2
    return 1
  fi
}

# Extract goal + next actions from the most relevant Projects/ note
_sb_project_brief() {
  [[ -d "$VAULT_PATH/Projects" ]] || return 0
  local repo_name best_note
  repo_name=$(basename "$REPO_ROOT")
  for f in "$VAULT_PATH/Projects/"*.md; do
    [[ -f "$f" ]] || continue
    if grep -qi "$repo_name" "$f" 2>/dev/null || \
       [[ "$(basename "$f" .md)" == *"$repo_name"* ]]; then
      best_note="$f"; break
    fi
  done
  [[ -z "${best_note:-}" ]] && best_note=$(ls -t "$VAULT_PATH/Projects/"*.md 2>/dev/null | head -1)
  [[ -z "${best_note:-}" ]] && return 0
  python3 - "$best_note" <<'PY'
import re, sys, pathlib
text = pathlib.Path(sys.argv[1]).read_text()
print(f"Project: {pathlib.Path(sys.argv[1]).stem}")
for h in ["ゴール", "次のアクション"]:
    m = re.search(rf"## {h}\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if m:
        print(f"\n## {h}\n{m.group(1).strip()[:300]}")
PY
}

# Extract today's AI Session section from the Daily note
_sb_daily_brief() {
  local today daily
  today=$(date +%Y-%m-%d)
  daily="${VAULT_PATH}/Daily/${today}.md"
  [[ -f "$daily" ]] || return 0
  python3 - "$daily" <<'PY'
import re, sys, pathlib
text = pathlib.Path(sys.argv[1]).read_text()
m = re.search(r"## AI Session\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
if m:
    print(f"Today's AI Session:\n{m.group(1).strip()[:400]}")
PY
}

# ── Vault-unaware helpers ─────────────────────────────────────────────────────

sb-commit-msg() {
  _require_copilot || return 1
  local diff
  diff=$(git diff --cached 2>/dev/null)
  if [[ -z "$diff" ]]; then
    echo "Nothing staged. Run: git add <files>" >&2; return 1
  fi
  echo "$diff" | copilot -sp \
    "Write one Conventional Commit subject line for this staged diff in second-brain. \
     Types: feat|fix|docs|refactor|test|chore. \
     Mention hooks/harvest changes if relevant. \
     Output only the commit subject, no explanation."
}

# Usage: sb-review-pr [--with-vault-context] [base-branch]
sb-review-pr() {
  _require_copilot || return 1
  local with_vault=false
  [[ "${1:-}" == "--with-vault-context" ]] && { with_vault=true; shift; }
  local base="${1:-origin/main}"
  local diff
  diff=$(git diff "$base"...HEAD 2>/dev/null)
  [[ -z "$diff" ]] && { echo "No diff found against $base" >&2; return 1; }

  local context=""
  if $with_vault; then
    _require_vault || return 1
    local brief; brief=$(_sb_project_brief)
    [[ -n "$brief" ]] && context="\n\n---\n${brief}"
  fi

  printf '%s%s' "$diff" "$context" | copilot -sp \
    "Review this diff for the second-brain Claude Code plugin. \
     Check for: fail-open regressions (exit non-zero in hooks), \
     hook race conditions (parallel writers to same file), \
     Template-Vault frontmatter compatibility breaks, \
     config portability issues (hardcoded paths/secrets), \
     harvest.py queue/worker contract violations. \
     Output findings only, grouped by severity: CRITICAL / WARN / INFO."
}

sb-explain-harvest() {
  _require_copilot || return 1
  {
    echo "=== hooks/hooks.json ==="
    cat "$REPO_ROOT/hooks/hooks.json"
    echo ""
    echo "=== scripts/harvest.py (first 120 lines) ==="
    head -120 "$REPO_ROOT/scripts/harvest.py"
  } | copilot -sp \
    "Explain the interplay between hooks.json and harvest.py in second-brain \
     for a PR description. Cover: hook lifecycle (SessionStart→UserPromptSubmit→\
     PostToolUse→Stop→SessionEnd), the queue→worker→flush pipeline, and the \
     3-layer promotion (L1 Ideas / L2 Meta/Promotions / L3 References). \
     Output 6 concise bullets."
}

# ── Vault-aware helpers ───────────────────────────────────────────────────────

sb-pr-context() {
  _require_copilot || return 1; _require_vault || return 1
  local diff
  diff=$(git diff origin/main...HEAD 2>/dev/null)
  [[ -z "$diff" ]] && { echo "No diff found against origin/main" >&2; return 1; }
  local context=""
  local brief; brief=$(_sb_project_brief)
  local daily; daily=$(_sb_daily_brief)
  [[ -n "$brief" ]] && context+="\n\n---\n${brief}"
  [[ -n "$daily" ]] && context+="\n\n---\n${daily}"
  printf '%s%s' "$diff" "$context" | copilot -sp \
    "Write a GitHub PR description for this diff in second-brain. \
     Use the project context to explain motivation. \
     Format: Summary (3 bullets), Motivation (1 sentence), Test plan (checklist)."
}

sb-promotions-review() {
  _require_copilot || return 1; _require_vault || return 1
  local promo_dir="${VAULT_PATH}/Meta/Promotions"
  [[ -d "$promo_dir" ]] || { echo "Meta/Promotions/ not found." >&2; return 0; }
  local notes
  notes=$(find "$promo_dir" -name "*.md" | head -20 | xargs -I{} head -30 {} 2>/dev/null)
  [[ -z "$notes" ]] && { echo "No notes in Meta/Promotions/" >&2; return 0; }
  echo "$notes" | copilot -sp \
    "These are staged notes in Meta/Promotions/ of a personal knowledge vault. \
     Cluster them by theme, then for each suggest: \
     'promote to References/', 'promote to Projects/', or 'discard'. \
     Output a numbered review queue, one line per note with action recommendation."
}

sb-idea-gardener() {
  _require_copilot || return 1; _require_vault || return 1
  local ideas_dir="${VAULT_PATH}/Ideas"
  [[ -d "$ideas_dir" ]] || { echo "Ideas/ not found." >&2; return 0; }
  local stale
  stale=$(find "$ideas_dir" -name "*.md" -mtime +30 | head -20 \
    | xargs -I{} head -20 {} 2>/dev/null)
  [[ -z "$stale" ]] && { echo "No stale ideas (30+ days) found." >&2; return 0; }
  echo "$stale" | copilot -sp \
    "These are idea notes not updated in 30+ days in a personal vault. \
     Classify each as: 'projectable', 'incubate', or 'archive'. \
     Output a table: filename | classification | one-line reason."
}

sb-release-notes() {
  _require_copilot || return 1
  local vault_context=""
  if _require_vault 2>/dev/null; then
    vault_context=$(_sb_project_brief)
  fi
  {
    echo "=== Recent commits ==="
    git log --oneline -20 2>/dev/null
    if [[ -f "$REPO_ROOT/CHANGELOG.md" ]]; then
      echo ""; echo "=== CHANGELOG (last 60 lines) ==="; tail -60 "$REPO_ROOT/CHANGELOG.md"
    fi
    if [[ -n "$vault_context" ]]; then
      echo ""; echo "=== Project context ==="; echo "$vault_context"
    fi
  } | copilot -sp \
    "Write human-readable release notes for second-brain based on these commits. \
     Group by: New features, Fixes, Breaking changes. Be concise and user-facing."
}

# Auto-draft this week's Weekly note body from vault context.
# Reads: Daily (7 days) + recently updated Projects + this week's Ideas + Meta/Promotions
# Writes: fills empty ## sections in the existing Weekly stub
sb-weekly-review() {
  _require_copilot || return 1; _require_vault || return 1

  local week_str today
  week_str=$(date +%G-W%V)
  today=$(date +%Y-%m-%d)
  local weekly_note="${VAULT_PATH}/Weekly/${week_str}.md"

  if [[ ! -f "$weekly_note" ]]; then
    echo "Weekly note not found: $weekly_note" >&2
    echo "Run a Claude Code session to trigger harvest.py flush, which creates the stub." >&2
    return 1
  fi

  # Collect this week's Daily notes (last 7 days)
  local daily_context=""
  for i in 0 1 2 3 4 5 6; do
    local d
    d=$(date -v-${i}d +%Y-%m-%d 2>/dev/null || date -d "$i days ago" +%Y-%m-%d 2>/dev/null)
    local f="${VAULT_PATH}/Daily/${d}.md"
    if [[ -f "$f" ]]; then
      daily_context+="### Daily ${d}\n"
      daily_context+=$(python3 -c "
import re, pathlib
text = pathlib.Path('$f').read_text()
# Skip frontmatter, grab メモ and AI Session sections
for h in ['今日のフォーカス', 'メモ', 'AI Session']:
    m = re.search(rf'## {h}\n(.*?)(?=\n##|\Z)', text, re.DOTALL)
    if m:
        body = m.group(1).strip()[:200]
        if body: print(f'## {h}\n{body}\n')
" 2>/dev/null)
      daily_context+="\n"
    fi
  done

  # Collect active Projects (recently modified)
  local projects_context=""
  projects_context=$(find "${VAULT_PATH}/Projects" -name "*.md" -mtime -14 2>/dev/null \
    | head -5 | xargs -I{} python3 -c "
import re, sys, pathlib
text = pathlib.Path('{}').read_text()
name = pathlib.Path('{}').stem
print(f'### {name}')
for h in ['ゴール', '次のアクション']:
    m = re.search(rf'## {h}\n(.*?)(?=\n##|\Z)', text, re.DOTALL)
    if m: print(f'{m.group(1).strip()[:150]}')
print()
" 2>/dev/null)

  # Collect this week's new Ideas
  local ideas_context=""
  ideas_context=$(find "${VAULT_PATH}/Ideas" -name "*.md" -mtime -7 2>/dev/null \
    | head -10 | xargs -I{} head -8 {} 2>/dev/null)

  # Collect Meta/Promotions (staged, not yet reviewed)
  local promotions_context=""
  promotions_context=$(find "${VAULT_PATH}/Meta/Promotions" -name "*.md" 2>/dev/null \
    | head -10 | xargs -I{} head -5 {} 2>/dev/null)

  local stub
  stub=$(cat "$weekly_note")

  {
    echo "=== Weekly stub to fill (${week_str}) ==="
    echo "$stub"
    echo ""
    [[ -n "$daily_context" ]]     && { echo "=== This week's Daily notes ==="; printf '%s\n' "$daily_context"; }
    [[ -n "$projects_context" ]]  && { echo "=== Active Projects ==="; echo "$projects_context"; }
    [[ -n "$ideas_context" ]]     && { echo "=== New Ideas this week ==="; echo "$ideas_context"; }
    [[ -n "$promotions_context" ]] && { echo "=== Meta/Promotions (staged) ==="; echo "$promotions_context"; }
  } | copilot -sp \
    "Fill in the empty sections of this Weekly note stub using the provided vault context. \
     Sections to fill: 進行中プロジェクト, 昇格候補アイデア, ブロッカー, 来週の重点. \
     Keep each section brief (3-5 bullets max). \
     Output only the complete filled Weekly note in Markdown, ready to save. \
     Preserve the existing frontmatter exactly." \
  | tee /tmp/sb-weekly-draft.md

  echo ""
  echo "Draft saved to /tmp/sb-weekly-draft.md"
  echo "Review, then apply with:"
  echo "  cp /tmp/sb-weekly-draft.md \"$weekly_note\""
}

# Draft this month's Monthly note using Weekly summaries (hierarchical summarization).
# Weekly notes are read first to compress the month, then Monthly sections are drafted.
# Output is preview only — human review required before applying.
sb-monthly-review() {
  _require_copilot || return 1; _require_vault || return 1

  local month_str
  month_str=$(date +%Y-%m)
  local monthly_note="${VAULT_PATH}/Monthly/${month_str}.md"

  if [[ ! -f "$monthly_note" ]]; then
    echo "Monthly note not found: $monthly_note" >&2
    echo "Run a Claude Code session to trigger harvest.py flush, which creates the stub." >&2
    return 1
  fi

  # Step 1: collect this month's Weekly notes and compress them
  local weekly_summaries=""
  for f in "${VAULT_PATH}/Weekly/${month_str%-*}-W"*.md; do
    [[ -f "$f" ]] || continue
    local wname
    wname=$(basename "$f" .md)
    weekly_summaries+="### ${wname}\n"
    weekly_summaries+=$(python3 -c "
import re, pathlib
text = pathlib.Path('$f').read_text()
for h in ['進行中プロジェクト', '昇格候補アイデア', 'ブロッカー', '来週の重点']:
    m = re.search(rf'## {h}\n(.*?)(?=\n##|\Z)', text, re.DOTALL)
    if m:
        body = m.group(1).strip()[:200]
        if body: print(f'## {h}\n{body}\n')
" 2>/dev/null)
    weekly_summaries+="\n"
  done

  local stub
  stub=$(cat "$monthly_note")

  {
    echo "=== Monthly stub to fill (${month_str}) ==="
    echo "$stub"
    echo ""
    if [[ -n "$weekly_summaries" ]]; then
      echo "=== This month's Weekly notes (source of truth) ==="
      printf '%s\n' "$weekly_summaries"
    else
      # Fall back to recent Daily if no Weekly notes exist
      echo "=== Recent Daily notes (last 30 days) ==="
      find "${VAULT_PATH}/Daily" -name "${month_str}-*.md" 2>/dev/null \
        | sort | tail -10 | xargs -I{} head -15 {} 2>/dev/null
    fi
  } | copilot -sp \
    "Fill in the empty sections of this Monthly note stub using the provided weekly summaries. \
     Sections to fill: 優先事項, うまくいったこと, 改善点, 来月の焦点. \
     Synthesise across weeks — identify patterns, not just list items. \
     Keep each section to 3-5 sentences or bullets. \
     Output only the complete filled Monthly note in Markdown. \
     Preserve the existing frontmatter exactly. \
     NOTE: This is a DRAFT for human review — mark it with a > [!warning] Draft banner at the top." \
  | tee /tmp/sb-monthly-draft.md

  echo ""
  echo "Draft saved to /tmp/sb-monthly-draft.md"
  echo "Review carefully, then apply with:"
  echo "  cp /tmp/sb-monthly-draft.md \"$monthly_note\""
}
