#!/bin/bash

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked: jq is required for protected file checks." >&2
  exit 2
fi

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
NORMALIZED_PATH="${FILE_PATH#./}"

if [[ -z "$NORMALIZED_PATH" ]]; then
  exit 0
fi

PROTECTED_PATTERNS=(
  ".git/"
  ".env"
  ".env."
  ".DS_Store"
  ".pem"
  ".key"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if [[ "$NORMALIZED_PATH" == *"$pattern"* ]]; then
    echo "Blocked: $NORMALIZED_PATH matches protected pattern '$pattern'" >&2
    exit 2
  fi
done

exit 0
