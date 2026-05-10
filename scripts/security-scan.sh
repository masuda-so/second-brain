#!/bin/bash
# security-scan.sh — PostToolUse hook
# Scans vault notes and repo files for accidentally pasted secrets.
# Exits 2 if any match is found; exits 0 otherwise.
# Always reads vault path from SECOND_BRAIN_VAULT_PATH (or CLAUDE.md fallback).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

warn() {
  echo "second-brain: security-scan: $*" >&2
}

# Resolve vault path
VAULT_PATH=""
if [[ -n "${SECOND_BRAIN_VAULT_PATH:-}" ]]; then
  VAULT_PATH="${SECOND_BRAIN_VAULT_PATH%/}"
else
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
  VAULT_PATH="${VAULT_PATH%/}"
fi

if [[ -z "$VAULT_PATH" || ! -d "$VAULT_PATH" ]]; then
  warn "vault not found — skipping scan"
  exit 0
fi

# Patterns that indicate accidentally pasted secrets
# Each entry is a grep-compatible extended regex
SECRET_PATTERNS=(
  # Generic API key / token assignments
  '[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*[:=]\s*[A-Za-z0-9+/._-]{20,}'
  '[Aa][Cc][Cc][Ee][Ss][Ss][_-]?[Tt][Oo][Kk][Ee][Nn]\s*[:=]\s*[A-Za-z0-9+/._-]{20,}'
  '[Ss][Ee][Cc][Rr][Ee][Tt][_-]?[Kk][Ee][Yy]\s*[:=]\s*[A-Za-z0-9+/._-]{20,}'
  # OpenAI / Anthropic tokens
  'sk-[A-Za-z0-9]{32,}'
  'sk-ant-[A-Za-z0-9_-]{20,}'
  # AWS credentials
  'AKIA[0-9A-Z]{16}'
  'aws_secret_access_key\s*=\s*[A-Za-z0-9+/]{40}'
  # GitHub PAT (classic and fine-grained)
  'ghp_[A-Za-z0-9]{36}'
  'github_pat_[A-Za-z0-9_]{82}'
  # Generic Bearer / Authorization header values pasted as text
  'Bearer\s+[A-Za-z0-9+/._-]{30,}'
  # Private key header
  '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
)

FOUND=0

scan_path() {
  local target="$1"
  [[ -d "$target" ]] || return 0
  for pattern in "${SECRET_PATTERNS[@]}"; do
    local matches
    matches=$(grep -rlE "$pattern" "$target" 2>/dev/null | grep -v '\.git/' || true)
    if [[ -n "$matches" ]]; then
      while IFS= read -r file; do
        warn "POTENTIAL SECRET in $file (pattern: ${pattern:0:40}...)"
        FOUND=1
      done <<< "$matches"
    fi
  done
}

# Scan vault notes
scan_path "$VAULT_PATH"

# Scan repo (exclude .git and common binary dirs)
for pattern in "${SECRET_PATTERNS[@]}"; do
  matches=$(grep -rlE "$pattern" "$REPO_ROOT" \
    --exclude-dir='.git' \
    --exclude-dir='node_modules' \
    --exclude-dir='.venv' \
    2>/dev/null || true)
  if [[ -n "$matches" ]]; then
    while IFS= read -r file; do
      warn "POTENTIAL SECRET in $file (pattern: ${pattern:0:40}...)"
      FOUND=1
    done <<< "$matches"
  fi
done

if [[ "$FOUND" -eq 1 ]]; then
  warn "Scan complete — potential secrets detected. Review the files above."
  exit 2
fi

exit 0
