#!/bin/bash

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Validation failed: jq is required for post-edit checks." >&2
  exit 2
fi

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')
NORMALIZED_PATH="${FILE_PATH#./}"

if [[ -z "$NORMALIZED_PATH" || ! -f "$NORMALIZED_PATH" ]]; then
  exit 0
fi

case "$NORMALIZED_PATH" in
  *.json)
    if command -v jq >/dev/null 2>&1; then
      jq empty "$NORMALIZED_PATH" >/dev/null || {
        echo "Validation failed: invalid JSON in $NORMALIZED_PATH" >&2
        exit 2
      }
    fi
    ;;
  *.sh)
    bash -n "$NORMALIZED_PATH" || {
      echo "Validation failed: shell syntax error in $NORMALIZED_PATH" >&2
      exit 2
    }
    ;;
  *.py)
    if command -v python3 >/dev/null 2>&1; then
      python3 - "$NORMALIZED_PATH" <<'PY'
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
ast.parse(path.read_text())
PY
    fi
    ;;
esac

exit 0
