#!/bin/bash
# scripts/tests/guard-vault-rm.test.sh
# Tests for scripts/guard-vault-rm.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VAULT_PATH="/tmp/mock_vault"
export SECOND_BRAIN_VAULT_PATH="$VAULT_PATH"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

mkdir -p "$VAULT_PATH"

run_test() {
    local cmd="$1"
    local expected="$2" # "block" or "allow"

    echo "Running test: $cmd (expected: $expected)"
    json_input=$(jq -n --arg cmd "$cmd" '{tool_name: "Bash", tool_input: {command: $cmd}}')

    if echo "$json_input" | bash "$ROOT_DIR/scripts/guard-vault-rm.sh" > /dev/null 2>&1; then
        actual="allow"
    else
        exit_code=$?
        if [ $exit_code -eq 2 ]; then
            actual="block"
        else
            actual="error($exit_code)"
        fi
    fi

    if [ "$actual" != "$expected" ]; then
        fail "expected $expected but got $actual"
    fi
}

# Standard cases
run_test "rm -rf $VAULT_PATH" "block"
run_test "rmdir $VAULT_PATH" "block"

# Path-qualified cases (previously a bypass)
run_test "/bin/rm -rf $VAULT_PATH" "block"
run_test "/usr/bin/rmdir $VAULT_PATH" "block"

# False positive / Allow cases
run_test "rm_safe $VAULT_PATH" "allow"
run_test "echo deleting $VAULT_PATH" "allow"

# Compound commands (must be blocked if rm is present)
run_test "echo deleting; rm -rf $VAULT_PATH" "block"
run_test "rm -rf $VAULT_PATH; echo done" "block"

# Malicious bypass attempt (must be blocked)
run_test "echo rm > /dev/null; rm -rf $VAULT_PATH" "block"

echo "OK"
rm -rf "$VAULT_PATH"
