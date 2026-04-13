#!/bin/bash

# Project State Memory
# Hook: SessionStart
# Finds the Projects/<slug>.md matching the current working directory (or git root)
# and injects goal, status, and next actions into Claude's context via
# hookSpecificOutput.additionalContext.
# Always exits 0 (fail-open).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT="$(cat 2>/dev/null || true)"

warn() {
  echo "second-brain: on-start-project: $*" >&2
}

bail() {
  warn "$*"
  exit 0
}

extract_field() {
  local filter="$1"
  printf '%s' "$INPUT" | jq -r "$filter" 2>/dev/null || true
}

extract_vault_path() {
  if [[ -n "${SECOND_BRAIN_VAULT_PATH:-}" ]]; then
    printf '%s\n' "${SECOND_BRAIN_VAULT_PATH%/}"
    return
  fi
  local path
  path=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
  if [[ -n "$path" ]]; then
    printf '%s\n' "${path%/}"
    return
  fi
  return 1
}

# Find a Projects note matching a directory name or git repo name.
find_project_note() {
  local vault_path="$1"
  local cwd="$2"
  local projects_dir="$vault_path/Projects"
  [[ -d "$projects_dir" ]] || return 1

  # Try git root name first
  local git_root=""
  git_root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
  local repo_name=""
  [[ -n "$git_root" ]] && repo_name="$(basename "$git_root")"

  # Try: exact match on repo name, then cwd basename, then fuzzy (contains)
  local dir_name
  dir_name="$(basename "$cwd")"

  local candidate
  for slug in "$repo_name" "$dir_name"; do
    [[ -z "$slug" ]] && continue
    candidate="$projects_dir/$slug.md"
    [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
    # case-insensitive fallback
    candidate=$(find "$projects_dir" -maxdepth 1 -iname "${slug}.md" 2>/dev/null | head -1)
    [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
  done

  # Fuzzy: find notes whose filename appears in cwd path. Sort by name for determinism.
  # Require at least 4 chars to avoid false positives on short names.
  local best_match="" best_len=0
  while IFS= read -r f; do
    local fname
    fname="$(basename "${f%.md}")"
    if [[ ${#fname} -ge 4 ]] && [[ "$cwd" == *"$fname"* ]]; then
      if [[ ${#fname} -gt $best_len ]]; then
        best_match="$f"
        best_len=${#fname}
      fi
    fi
  done < <(find "$projects_dir" -maxdepth 1 -name '*.md' 2>/dev/null | sort)

  if [[ -n "$best_match" ]]; then
    printf '%s\n' "$best_match"
    return 0
  fi

  return 1
}

# Extract a concise project brief from a Projects note (max ~20 lines).
extract_project_brief() {
  local filepath="$1"
  python3 - "$filepath" <<'PY'
import sys, pathlib, re

path = pathlib.Path(sys.argv[1])
text = path.read_text()

# Strip YAML frontmatter
text = re.sub(r'^---\n.*?---\n', '', text, flags=re.DOTALL)

lines = text.splitlines()
sections = {}
current = None
buf = []

for line in lines:
    m = re.match(r'^#{1,3}\s+(.*)', line)
    if m:
        if current and buf:
            sections[current] = '\n'.join(buf).strip()
        current = m.group(1).strip().lower()
        buf = []
    elif current is not None:
        buf.append(line)
if current and buf:
    sections[current] = '\n'.join(buf).strip()

wanted = ['outcome', 'goal', 'status', 'next actions', 'next action', 'decisions', 'last decision']
parts = []
seen_sections = set()
for key in wanted:
    for sec, content in sections.items():
        if sec in seen_sections:
            continue
        if key in sec and content:
            snippet = '\n'.join(content.splitlines()[:5]).strip()
            if snippet:
                parts.append(f"**{sec.title()}**: {snippet}")
                seen_sections.add(sec)
            break

# Fallback: first 10 non-empty lines
if not parts:
    parts = [l for l in lines if l.strip()][:10]

result = '\n'.join(parts[:8])
if len(result) > 800:
    result = result[:797] + '...'
print(result)
PY
}

# ── main ─────────────────────────────────────────────────────────────────────

command -v jq      >/dev/null 2>&1 || bail "jq is required"
command -v python3 >/dev/null 2>&1 || bail "python3 is required"

VAULT_PATH="$(extract_vault_path)" || bail "vault path not configured"
[[ -d "$VAULT_PATH" ]] || bail "vault not found at $VAULT_PATH"

CWD="$(extract_field '.cwd // empty')"
[[ -z "$CWD" ]] && CWD="${PWD}"
[[ -d "$CWD" ]] || CWD="${PWD}"

PROJECT_NOTE="$(find_project_note "$VAULT_PATH" "$CWD")" || exit 0
[[ -f "$PROJECT_NOTE" ]] || exit 0

BRIEF="$(extract_project_brief "$PROJECT_NOTE" 2>/dev/null)" || exit 0
[[ -n "$BRIEF" ]] || exit 0

REL_PATH="${PROJECT_NOTE#$VAULT_PATH/}"
INJECT_TEXT="Active project context from [[${REL_PATH%.md}]]:
$BRIEF"

printf '%s' "$INJECT_TEXT" \
  | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: .}}' 2>/dev/null \
  || exit 0

exit 0
