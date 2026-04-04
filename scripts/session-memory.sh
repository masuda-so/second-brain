#!/bin/bash

set -uo pipefail

ACTION="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STRICT_CAPTURE="${SECOND_BRAIN_CAPTURE_STRICT:-0}"
INPUT="$(cat 2>/dev/null || true)"

warn() {
  echo "second-brain: $*" >&2
}

finish_problem() {
  local message="$1"
  warn "$message"
  if [[ "$STRICT_CAPTURE" == "1" ]]; then
    exit 2
  fi
  exit 0
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    finish_problem "$command_name is required for session capture."
  fi
}

extract_vault_path() {
  if [[ -n "${SECOND_BRAIN_VAULT_PATH:-}" ]]; then
    printf '%s\n' "${SECOND_BRAIN_VAULT_PATH%/}"
    return
  fi

  if [[ -f "$REPO_ROOT/CLAUDE.md" ]]; then
    local path
    path=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" | head -n 1)
    if [[ -n "$path" ]]; then
      printf '%s\n' "${path%/}"
      return
    fi
  fi

  finish_problem "vault path is not configured. Set SECOND_BRAIN_VAULT_PATH."
}

extract_first_string() {
  local filter="$1"
  printf '%s' "$INPUT" | jq -r "$filter" 2>/dev/null || true
}

normalize_excerpt() {
  local raw="$1"
  local normalized
  normalized=$(printf '%s' "$raw" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')
  if [[ ${#normalized} -gt 160 ]]; then
    normalized="${normalized:0:157}..."
  fi
  printf '%s\n' "$normalized"
}

append_under_heading() {
  local path="$1"
  local heading="$2"
  local content="$3"

  if command -v python3 >/dev/null 2>&1; then
    APPEND_CONTENT="$content" python3 - "$path" "$heading" <<'PY'
import pathlib, os, sys, fcntl, time

path = pathlib.Path(sys.argv[1])
heading = sys.argv[2]
content = os.environ["APPEND_CONTENT"]
marker = f"## {heading}"

# Advisory file lock — same lockfile convention as harvest.py
lock_path = path.parent / f".{path.name}.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)
lf = open(lock_path, "w")
acquired = False
try:
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
    except OSError:
        for _ in range(100):
            time.sleep(0.05)
            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                pass
    if not acquired:
        print(f"second-brain: lock timeout for {path.name}, skipping write", file=sys.stderr)
        sys.exit(0)

    text = path.read_text() if path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"

    lines = text.splitlines(keepends=True)
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == marker:
            start = idx
            break

    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(marker + "\n")
        start = len(lines) - 1

    insert_at = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            insert_at = idx
            break

    block = content
    if not block.endswith("\n"):
        block += "\n"

    is_multiline = "\n" in block.rstrip("\n")

    if is_multiline and insert_at > start + 1 and lines[insert_at - 1].strip():
        block = "\n" + block

    if is_multiline and insert_at < len(lines) and not block.endswith("\n\n"):
        block += "\n"

    lines.insert(insert_at, block)
    path.write_text("".join(lines))
finally:
    if acquired:
        fcntl.flock(lf, fcntl.LOCK_UN)
    lf.close()
PY
    return $?
  fi

  printf '\n%s\n' "$content" >> "$path"
}

ensure_daily_note() {
  if [[ -f "$DAILY_NOTE_PATH" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$DAILY_NOTE_PATH")" || return 1

  cat >"$DAILY_NOTE_PATH" <<EOF
---
date: $TODAY
tags: [daily]
---
## Focus
## Wins
## Blockers
## Notes
## AI Session

EOF
}

ensure_session_note() {
  if [[ -f "$SESSION_NOTE_PATH" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$SESSION_NOTE_PATH")" || return 1

  cat >"$SESSION_NOTE_PATH" <<EOF
---
session_id: $SAFE_SESSION_ID
date: $TODAY
started_at: "$TIMESTAMP"
cwd: "$WORKDIR"
tags: [ai-session]
---
# AI Session $SAFE_SESSION_ID

## Context
- Started: $TIMESTAMP
- Working directory: $WORKDIR
- Daily note: [[${DAILY_DIR}/$TODAY]]

## Captures

## Tool Events

## Closeout

EOF
}

capture_start() {
  ensure_daily_note || finish_problem "could not create daily note at $DAILY_NOTE_PATH"
  ensure_session_note || finish_problem "could not create session note at $SESSION_NOTE_PATH"

  append_under_heading \
    "$DAILY_NOTE_PATH" \
    "AI Session" \
    "- $TIME_LABEL Session started: $SESSION_LINK" || finish_problem "could not append session start to $DAILY_NOTE_PATH"
}

capture_prompt() {
  local prompt_raw prompt_excerpt session_block daily_block
  prompt_raw=$(extract_first_string '
    [
      .prompt,
      .message,
      .text,
      .user_prompt,
      .userPrompt,
      .input,
      .tool_input.prompt,
      .tool_input.message,
      .tool_input.user_prompt,
      .tool_input.userPrompt
    ] | map(select(type == "string" and length > 0)) | .[0] // empty
  ')

  if [[ -z "$prompt_raw" ]]; then
    exit 0
  fi

  ensure_daily_note || finish_problem "could not create daily note at $DAILY_NOTE_PATH"
  ensure_session_note || finish_problem "could not create session note at $SESSION_NOTE_PATH"

  prompt_excerpt=$(normalize_excerpt "$prompt_raw")
  session_block="### $TIME_LABEL User Prompt

$prompt_raw"
  daily_block="- $TIME_LABEL User: $prompt_excerpt"

  append_under_heading "$SESSION_NOTE_PATH" "Captures" "$session_block" || finish_problem "could not append prompt to $SESSION_NOTE_PATH"
  append_under_heading "$DAILY_NOTE_PATH" "AI Session" "$daily_block" || finish_problem "could not append prompt to $DAILY_NOTE_PATH"
}

capture_tool() {
  local tool_name file_path session_block
  tool_name=$(extract_first_string '
    [
      .tool_name,
      .toolName,
      .tool.name,
      .tool,
      .matcher
    ] | map(select(type == "string" and length > 0)) | .[0] // empty
  ')
  file_path=$(extract_first_string '
    [
      .tool_input.file_path,
      .tool_input.path,
      .tool_input.target_file,
      .file_path,
      .path
    ] | map(select(type == "string" and length > 0)) | .[0] // empty
  ')

  if [[ -z "$tool_name" && -z "$file_path" ]]; then
    exit 0
  fi

  ensure_session_note || finish_problem "could not create session note at $SESSION_NOTE_PATH"

  if [[ -z "$tool_name" ]]; then
    tool_name="tool"
  fi

  if [[ -n "$file_path" ]]; then
    session_block="- $TIME_LABEL $tool_name -> $file_path"
  else
    session_block="- $TIME_LABEL $tool_name"
  fi

  append_under_heading "$SESSION_NOTE_PATH" "Tool Events" "$session_block" || finish_problem "could not append tool event to $SESSION_NOTE_PATH"
}

capture_stop() {
  ensure_daily_note || finish_problem "could not create daily note at $DAILY_NOTE_PATH"
  ensure_session_note || finish_problem "could not create session note at $SESSION_NOTE_PATH"

  append_under_heading "$SESSION_NOTE_PATH" "Closeout" "- Ended: $TIMESTAMP" || finish_problem "could not append closeout to $SESSION_NOTE_PATH"
  append_under_heading "$DAILY_NOTE_PATH" "AI Session" "- $TIME_LABEL Session ended: $SESSION_LINK" || finish_problem "could not append session end to $DAILY_NOTE_PATH"
}

require_command jq

VAULT_PATH="$(extract_vault_path)"
DAILY_DIR="${SECOND_BRAIN_DAILY_DIR:-Daily}"
SESSION_DIR="${SECOND_BRAIN_SESSION_DIR:-Meta/AI Sessions}"
TODAY="$(date '+%Y-%m-%d')"
TIME_LABEL="$(date '+%H:%M')"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %z')"
WORKDIR="${PWD}"

SESSION_ID="$(extract_first_string '
  [
    .session_id,
    .sessionId,
    .session.id,
    .conversation_id,
    .conversationId,
    .hook_event.session_id,
    .hook_event.sessionId,
    .tool_input.session_id,
    .tool_input.sessionId
  ] | map(select(type == "string" and length > 0)) | .[0] // empty
')"

if [[ -z "$SESSION_ID" ]]; then
  SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown-session}}"
fi

SAFE_SESSION_ID="$(printf '%s' "$SESSION_ID" | tr -cs 'A-Za-z0-9._-' '-')"
SAFE_SESSION_ID="${SAFE_SESSION_ID#-}"
SAFE_SESSION_ID="${SAFE_SESSION_ID%-}"

if [[ -z "$SAFE_SESSION_ID" ]]; then
  SAFE_SESSION_ID="unknown-session"
fi

DAILY_NOTE_PATH="$VAULT_PATH/$DAILY_DIR/$TODAY.md"
SESSION_NOTE_REL_PATH="$SESSION_DIR/$TODAY/$SAFE_SESSION_ID.md"
SESSION_NOTE_PATH="$VAULT_PATH/$SESSION_NOTE_REL_PATH"
SESSION_LINK="[[${SESSION_NOTE_REL_PATH%.md}|$SAFE_SESSION_ID]]"

case "$ACTION" in
  start)
    capture_start
    ;;
  capture-prompt)
    capture_prompt
    ;;
  capture-tool)
    capture_tool
    ;;
  stop)
    capture_stop
    ;;
  *)
    finish_problem "unknown action '$ACTION'"
    ;;
esac

exit 0
