#!/bin/bash
#
# Self-contained tests for scripts/distill.py.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$ROOT_DIR/scripts/distill.py"

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

require jq
require python3
require git

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

vault="$tmp_root/vault"
today="$(date '+%Y-%m-%d')"
session_id="distill-test"
session_dir="Meta/AI Sessions"
session_note="$vault/$session_dir/$today/$session_id.md"
daily_note="$vault/Daily/$today.md"

mkdir -p "$vault/Projects" "$(dirname "$session_note")" "$(dirname "$daily_note")" "$vault/References"

cat >"$vault/Projects/repoA.md" <<'EOF'
# Goal
Ship repoA
EOF

cat >"$vault/References/organizing.md" <<'EOF'
# 目的
existing organizing note
EOF

cat >"$session_note" <<'EOF'
## AI Session
- We decided to keep distill.py dry-run and let Claude own writes.
- Organizing is the practice of linking resources to activities so all work needed for a goal is assigned.
- Traceback: this is transient noise
EOF

cat >"$daily_note" <<'EOF'
## 今日のフォーカス
## メモ
- Organizing is the practice of linking resources to activities so all work needed for a goal is assigned.
- Next action: implement tests for distill.py.
## AI Session
- We decided to keep distill.py dry-run and let Claude own writes.
- Pattern: Use Daily ## AI Session plus Meta/AI Sessions union with dedupe.
EOF

work="$tmp_root/work/repoA/subdir"
mkdir -p "$work"
git -C "$tmp_root/work/repoA" init -q

echo "Running test: dry-run JSON with deduped candidates..."
out="$(cd "$work" && SECOND_BRAIN_VAULT_PATH="$vault" CLAUDE_SESSION_ID="$session_id" python3 "$SCRIPT_UNDER_TEST")"
printf '%s' "$out" | jq -e '.candidates | length >= 3' >/dev/null || fail "expected at least 3 candidates"

decision_count="$(printf '%s' "$out" | jq '[.candidates[] | select(.destination=="Projects/repoA.md") | select(.signal | test("decided"; "i"))] | length')"
[[ "$decision_count" == "1" ]] || fail "expected deduped project decision candidate"

pattern_count="$(printf '%s' "$out" | jq '[.candidates[] | select(.signal | test("Pattern: Use Daily"; "i"))] | length')"
[[ "$pattern_count" == "1" ]] || fail "expected daily AI Session signal to be included"

organizing_action="$(printf '%s' "$out" | jq -r '.candidates[] | select(.destination=="References/organizing.md") | .action' | head -n 1)"
[[ "$organizing_action" == "append" ]] || fail "expected existing reference destination to append"

assert_contains "$out" "\"destination\": \"Projects/repoA.md\""
assert_contains "$out" "\"destination\": \"References/organizing.md\""

echo "Running test: --session-id interface..."
out2="$(cd "$work" && SECOND_BRAIN_VAULT_PATH="$vault" python3 "$SCRIPT_UNDER_TEST" --session-id "$session_id")"
printf '%s' "$out2" | jq -e '.candidates | length >= 3' >/dev/null || fail "expected candidates via --session-id"

echo "OK"
