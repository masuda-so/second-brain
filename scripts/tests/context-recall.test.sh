#!/bin/bash
#
# Self-contained tests for scripts/context-recall.sh.
# Uses a temporary dummy vault and validates:
# - additionalContext JSON emission
# - session note "## Recalled Context" append/insert behavior
# - keyword/weight ordering (Projects outranks Daily)
# - stop-words prompt produces no output and no write
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$ROOT_DIR/scripts/context-recall.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required binary: $1"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: $needle"
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  [[ "$haystack" != *"$needle"* ]] || fail "expected output to not contain: $needle"
}

assert_file_contains() {
  local path="$1"
  local needle="$2"
  [[ -f "$path" ]] || fail "missing file: $path"
  grep -qF -- "$needle" "$path" || fail "expected file $path to contain: $needle"
}

assert_file_not_contains() {
  local path="$1"
  local needle="$2"
  [[ -f "$path" ]] || fail "missing file: $path"
  grep -qF -- "$needle" "$path" && fail "expected file $path to not contain: $needle" || true
}

assert_json_has_additional_context() {
  local json="$1"
  printf '%s' "$json" | jq -e '.hookSpecificOutput.hookEventName == "UserPromptSubmit"' >/dev/null \
    || fail "missing/invalid hookSpecificOutput.hookEventName"
  printf '%s' "$json" | jq -e '(.hookSpecificOutput.additionalContext // "") | length > 0' >/dev/null \
    || fail "missing/empty hookSpecificOutput.additionalContext"
}


run_context_recall() {
  local vault_path="$1"
  local prompt="$2"
  local session_id="$3"
  local session_dir="$4"
  SECOND_BRAIN_VAULT_PATH="$vault_path" \
  SECOND_BRAIN_SESSION_DIR="$session_dir" \
  bash "$SCRIPT_UNDER_TEST" <<EOF
{"prompt":"$prompt","session_id":"$session_id"}
EOF
}

require jq
require python3
require grep

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

vault="$tmp_root/vault"
mkdir -p "$vault/Daily" "$vault/Projects" "$vault/References" "$vault/Ideas" "$vault/Meta/AI Sessions"

today="$(date '+%Y-%m-%d')"
session_id="test/session id:01"
safe_session_id="$(printf '%s' "$session_id" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-//; s/-$//')"
[[ -n "$safe_session_id" ]] || safe_session_id="unknown-session"
session_dir="Meta/AI Sessions"
session_note="$vault/$session_dir/$today/$safe_session_id.md"
mkdir -p "$(dirname "$session_note")"

cat >"$vault/Projects/alpha.md" <<'EOF'
# Alpha Project
vault architecture hooks
EOF

cat >"$vault/Daily/day.md" <<'EOF'
# Daily Note
vault architecture hooks
EOF

cat >"$vault/References/ref.md" <<'EOF'
# Reference
unrelated content
EOF

echo "## AI Session" >"$session_note"

echo "Running test: emits JSON + appends recalled context..."
out="$(run_context_recall "$vault" "vault architecture hooks" "$session_id" "$session_dir")"
[[ -n "$out" ]] || fail "expected non-empty JSON output"
assert_json_has_additional_context "$out"
assert_contains "$out" "[[Projects/alpha]]"
assert_contains "$out" "[[Daily/day]]"

assert_file_contains "$session_note" "## Recalled Context"
assert_file_contains "$session_note" "[[Projects/alpha]]"

echo "Running test: Projects outranks Daily..."
first_link="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext' | grep -oE '\[\[[^]]+\]\]' | head -n 1)"
[[ "$first_link" == "[[Projects/alpha]]" ]] || fail "expected first recalled link to be [[Projects/alpha]], got: $first_link"

echo "Running test: inserts entry before next H2 when marker exists..."
cat >"$session_note" <<'EOF'
## AI Session
## Recalled Context
### 00:00 Recalled Context
- [[References/ref]] — dummy
## Next Section
EOF

out2="$(run_context_recall "$vault" "vault architecture hooks" "$session_id" "$session_dir")"
[[ -n "$out2" ]] || fail "expected non-empty JSON output (marker case)"

next_h2_line="$(grep -n '^## Next Section$' "$session_note" | head -n 1 | cut -d: -f1)"
[[ -n "$next_h2_line" ]] || fail "expected to find '## Next Section' in session note"
new_entry_line="$(grep -nE '^### .* Recalled Context$' "$session_note" | head -n 1 | cut -d: -f1)"
[[ -n "$new_entry_line" ]] || fail "expected to find a '### <time> Recalled Context' entry"
(( new_entry_line < next_h2_line )) || fail "expected new recalled context entry before '## Next Section'"

echo "Running test: stop-words prompt produces no output and no writes..."
cat >"$session_note" <<'EOF'
## AI Session
EOF
before="$(cat "$session_note")"
out3="$(run_context_recall "$vault" "the and for with you" "$session_id" "$session_dir" || true)"
[[ -z "$out3" ]] || fail "expected no output for stop-words prompt"
after="$(cat "$session_note")"
[[ "$after" == "$before" ]] || fail "expected session note unchanged for stop-words prompt"

echo "OK"
