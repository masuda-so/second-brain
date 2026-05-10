#!/bin/bash
# protect-vault-rm.sh — PreToolUse hook (Bash)
# Blocks any Bash command containing rm / rmdir that targets the vault path.
# Exits 2 (block) if a match is found; exits 0 (allow) otherwise.

set -uo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked: jq is required for vault rm protection." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INPUT=$(cat)

TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // .toolName // empty' 2>/dev/null || true)

# Only act on Bash tool calls
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

if [[ -z "$COMMAND" ]]; then
  exit 0
fi

# Resolve vault path
VAULT_PATH=""
if [[ -n "${SECOND_BRAIN_VAULT_PATH:-}" ]]; then
  VAULT_PATH="${SECOND_BRAIN_VAULT_PATH%/}"
else
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
  VAULT_PATH="${VAULT_PATH%/}"
fi

if [[ -z "$VAULT_PATH" ]]; then
  exit 0
fi

# Check if command contains an rm/rmdir invocation that references the vault path
if printf '%s' "$COMMAND" | grep -qE '(^|[[:space:]|;&])(rm|rmdir)[[:space:]]' && \
   printf '%s' "$COMMAND" | grep -qF "$VAULT_PATH"; then
  echo "Blocked: rm/rmdir targeting vault path '$VAULT_PATH' is not allowed." >&2
  exit 2
fi

exit 0
