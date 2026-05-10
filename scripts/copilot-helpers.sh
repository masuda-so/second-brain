#!/bin/bash
# copilot-helpers.sh — Local authoring helpers using Copilot CLI
#
# Prerequisites: copilot CLI installed and authenticated
# Usage:
#   source scripts/copilot-helpers.sh
#   sb-commit-msg       # generate a Conventional Commit message for staged diff
#   sb-review-pr        # review HEAD..origin/main diff for second-brain issues
#   sb-explain-harvest  # explain harvest.py + hooks.json interplay
#
# Note: These are authoring helpers only — not for use in CI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

_require_copilot() {
  if ! command -v copilot >/dev/null 2>&1; then
    echo "error: copilot CLI not found." >&2
    echo "  Install: https://docs.github.com/copilot/concepts/agents/about-copilot-cli" >&2
    return 1
  fi
}

# Generate a Conventional Commit subject for the current staged diff
sb-commit-msg() {
  _require_copilot || return 1
  local diff
  diff=$(git diff --cached 2>/dev/null)
  if [[ -z "$diff" ]]; then
    echo "Nothing staged. Run: git add <files>" >&2
    return 1
  fi
  echo "$diff" | copilot -sp \
    "Write one Conventional Commit subject line for this staged diff in second-brain. \
     Types: feat|fix|docs|refactor|test|chore. \
     Mention hooks/harvest changes if relevant. \
     Output only the commit subject, no explanation."
}

# Review the PR diff (HEAD vs origin/main) for second-brain-specific issues
sb-review-pr() {
  _require_copilot || return 1
  local base="${1:-origin/main}"
  local diff
  diff=$(git diff "$base"...HEAD 2>/dev/null)
  if [[ -z "$diff" ]]; then
    echo "No diff found against $base" >&2
    return 1
  fi
  echo "$diff" | copilot -sp \
    "Review this diff for the second-brain Claude Code plugin. \
     Check for: fail-open regressions (exit non-zero in hooks), \
     hook race conditions (parallel writers to same file), \
     Template-Vault frontmatter compatibility breaks, \
     config portability issues (hardcoded paths/secrets), \
     harvest.py queue/worker contract violations. \
     Output findings only, grouped by severity: CRITICAL / WARN / INFO."
}

# Explain harvest.py and hooks.json interplay for PR descriptions
sb-explain-harvest() {
  _require_copilot || return 1
  {
    echo "=== hooks/hooks.json ==="
    cat "$REPO_ROOT/hooks/hooks.json"
    echo ""
    echo "=== scripts/harvest.py (first 120 lines) ==="
    head -120 "$REPO_ROOT/scripts/harvest.py"
  } | copilot -sp \
    "Explain the interplay between hooks.json and harvest.py in second-brain \
     for a PR description. Cover: hook lifecycle (SessionStart→UserPromptSubmit→\
     PostToolUse→Stop→SessionEnd), the queue→worker→flush pipeline, and the \
     3-layer promotion (L1 Ideas / L2 Meta/Promotions / L3 References). \
     Output 6 concise bullets."
}
