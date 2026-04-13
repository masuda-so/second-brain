#!/bin/bash

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked: jq is required for protected file checks." >&2
  exit 2
fi

INPUT=$(cat)

# Collect all file paths: single path fields + MultiEdit edits[].file_path array
mapfile -t FILE_PATHS < <(
  printf '%s' "$INPUT" | jq -r '
    [
      (.tool_input.file_path // empty),
      (.tool_input.path // empty),
      (.tool_input.edits[]?.file_path // empty)
    ] | .[]
  ' 2>/dev/null
)

if [[ ${#FILE_PATHS[@]} -eq 0 ]]; then
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

for FILE_PATH in "${FILE_PATHS[@]}"; do
  NORMALIZED_PATH="${FILE_PATH#./}"
  [[ -z "$NORMALIZED_PATH" ]] && continue
  for pattern in "${PROTECTED_PATTERNS[@]}"; do
    if [[ "$NORMALIZED_PATH" == *"$pattern"* ]]; then
      echo "Blocked: $NORMALIZED_PATH matches protected pattern '$pattern'" >&2
      exit 2
    fi
  done
done

exit 0
