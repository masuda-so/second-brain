#!/bin/bash
#
# Self-contained tests for scripts/daily-note.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$ROOT_DIR/scripts/daily-note.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required binary: $1"
}

assert_file_contains() {
  local path="$1"
  local needle="$2"
  [[ -f "$path" ]] || fail "missing file: $path"
  grep -qF -- "$needle" "$path" || fail "expected file $path to contain: $needle"
}

require grep
require mktemp

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

vault="$tmp_root/vault"
mkdir -p "$vault"
today="$(date '+%Y-%m-%d')"
daily_note="$vault/Daily/$today.md"

echo "Running test: creates Daily note from template..."
SECOND_BRAIN_VAULT_PATH="$vault" bash "$SCRIPT_UNDER_TEST"
[[ -f "$daily_note" ]] || fail "expected Daily note to be created"
assert_file_contains "$daily_note" "type: daily"
assert_file_contains "$daily_note" "## AI Session"
assert_file_contains "$daily_note" "## 今日のフォーカス"

echo "Running test: idempotent when note already exists..."
printf '\nmanual line\n' >>"$daily_note"
before="$(cat "$daily_note")"
SECOND_BRAIN_VAULT_PATH="$vault" bash "$SCRIPT_UNDER_TEST"
after="$(cat "$daily_note")"
[[ "$after" == "$before" ]] || fail "expected existing Daily note to remain unchanged"

echo "OK"
