#!/bin/bash

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked: jq is required for read-only query validation." >&2
  exit 2
fi

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [[ -z "$COMMAND" ]]; then
  exit 0
fi

# Only inspect likely database client invocations to avoid false positives on
# unrelated shell commands that happen to contain SQL keywords.
if ! echo "$COMMAND" | grep -Eiq '\b(psql|sqlite3|duckdb|mysql|bq)\b'; then
  exit 0
fi

if echo "$COMMAND" | grep -Eiq '\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE)\b'; then
  echo "Blocked: write-capable SQL detected. Use read-only queries only." >&2
  exit 2
fi

exit 0
