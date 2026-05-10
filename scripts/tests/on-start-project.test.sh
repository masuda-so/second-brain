#!/bin/bash
#
# Self-contained tests for scripts/on-start-project.sh.
# Focuses on find_project_note behavior:
# - git repo root name preferred over cwd basename
# - case-insensitive exact filename match
# - fuzzy longest-match when cwd path contains filename (>=4 chars)
# Also validates emitted JSON hookSpecificOutput.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$ROOT_DIR/scripts/on-start-project.sh"

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

assert_contains_any() {
  local haystack="$1"
  local a="$2"
  local b="$3"
  [[ "$haystack" == *"$a"* || "$haystack" == *"$b"* ]] || fail "expected output to contain either: $a OR $b"
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  [[ "$haystack" != *"$needle"* ]] || fail "expected output to not contain: $needle"
}

assert_json_ok() {
  local json="$1"
  printf '%s' "$json" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' >/dev/null \
    || fail "missing/invalid hookSpecificOutput.hookEventName"
  printf '%s' "$json" | jq -e '(.hookSpecificOutput.additionalContext // "") | length > 0' >/dev/null \
    || fail "missing/empty hookSpecificOutput.additionalContext"
}

run_project_state() {
  local vault_path="$1"
  local cwd="$2"
  SECOND_BRAIN_VAULT_PATH="$vault_path" \
  bash "$SCRIPT_UNDER_TEST" <<EOF
{"cwd":"$cwd"}
EOF
}

require jq
require python3
require grep
require sed
require find
require basename
require mktemp
require git

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

vault="$tmp_root/vault"
mkdir -p "$vault/Projects"

cat >"$vault/Projects/repoA.md" <<'EOF'
---
type: project
---
# Goal
Ship repoA
# Next Actions
- [ ] do thing
EOF

cat >"$vault/Projects/subdir.md" <<'EOF'
# Goal
Ship subdir
EOF

cat >"$vault/Projects/FooBar.md" <<'EOF'
# Goal
Case-insensitive match
EOF

cat >"$vault/Projects/longname.md" <<'EOF'
# Goal
Fuzzy long match
EOF

cat >"$vault/Projects/short.md" <<'EOF'
# Goal
Fuzzy short match
EOF

# ---- Case 1: git repo root name preferred over cwd basename ----
echo "Running test: repo-name preferred..."
work="$tmp_root/work"
mkdir -p "$work/repoA/subdir"
git -C "$work/repoA" init -q

out1="$(run_project_state "$vault" "$work/repoA/subdir")"
[[ -n "$out1" ]] || fail "expected JSON output (repo-name case)"
assert_json_ok "$out1"
ctx1="$(printf '%s' "$out1" | jq -r '.hookSpecificOutput.additionalContext')"
assert_contains "$ctx1" "[[Projects/repoA]]"
assert_not_contains "$ctx1" "[[Projects/subdir]]"

# ---- Case 2: case-insensitive exact match ----
echo "Running test: case-insensitive match..."
mkdir -p "$work/foobar"
git -C "$work/foobar" init -q
out2="$(run_project_state "$vault" "$work/foobar")"
[[ -n "$out2" ]] || fail "expected JSON output (case-insensitive case)"
ctx2="$(printf '%s' "$out2" | jq -r '.hookSpecificOutput.additionalContext')"
# On case-insensitive filesystems, the script may return a lowercased
# path (Projects/foobar.md) even if the on-disk name is FooBar.md.
assert_contains_any "$ctx2" "[[Projects/FooBar]]" "[[Projects/foobar]]"

# ---- Case 3: fuzzy longest match (>=4 chars) ----
# Set cwd to include ".../longname/..." so longname.md wins over short.md
echo "Running test: fuzzy longest match..."
mkdir -p "$work/some/longname/deeper"
git -C "$work/some" init -q
out3="$(run_project_state "$vault" "$work/some/longname/deeper")"
[[ -n "$out3" ]] || fail "expected JSON output (fuzzy case)"
ctx3="$(printf '%s' "$out3" | jq -r '.hookSpecificOutput.additionalContext')"
assert_contains "$ctx3" "[[Projects/longname]]"

echo "OK"
