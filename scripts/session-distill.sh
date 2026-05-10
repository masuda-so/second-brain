#!/bin/bash
# session-distill.sh — SessionEnd hook: auto-distill candidates into Daily note.
#
# Calls distill.py (dry-run) and appends a compact candidate summary under
# Daily/YYYY-MM-DD.md ## AI Session. Does NOT write to References/ or Projects/
# — that remains a human-approved step via /distill.
#
# Idempotent: skips if the session was already summarized in the Daily note.
# Always exits 0 (fail-open).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT="$(cat 2>/dev/null || true)"

warn() { echo "second-brain: session-distill: $*" >&2; }
bail() { warn "$*"; exit 0; }

command -v python3 >/dev/null 2>&1 || bail "python3 required"
command -v jq      >/dev/null 2>&1 || bail "jq required"

# ── Resolve vault path ────────────────────────────────────────────────────────

VAULT_PATH="${SECOND_BRAIN_VAULT_PATH:-}"
if [[ -z "$VAULT_PATH" ]]; then
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
fi
VAULT_PATH="${VAULT_PATH%/}"
[[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]] || bail "vault not found"

# ── Resolve session id ────────────────────────────────────────────────────────

SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // .sessionId // empty' 2>/dev/null || true)"
[[ -z "$SESSION_ID" ]] && SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-}}"
SAFE_SESSION_ID="$(printf '%s' "$SESSION_ID" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-//; s/-$//')"
[[ -z "$SAFE_SESSION_ID" ]] && SAFE_SESSION_ID="unknown-session"

TODAY="$(date '+%Y-%m-%d')"
TIME_LABEL="$(date '+%H:%M')"
DAILY_DIR="${SECOND_BRAIN_DAILY_DIR:-Daily}"
DAILY_NOTE="$VAULT_PATH/$DAILY_DIR/$TODAY.md"

[[ -f "$DAILY_NOTE" ]] || bail "daily note not found: $DAILY_NOTE"

# ── Idempotency check ─────────────────────────────────────────────────────────
# Skip if this session's candidates were already appended.

MARKER="Distill:$SAFE_SESSION_ID"
if grep -qF "$MARKER" "$DAILY_NOTE" 2>/dev/null; then
  exit 0
fi

# ── Run distill.py ────────────────────────────────────────────────────────────

SESSION_DIR="${SECOND_BRAIN_SESSION_DIR:-Meta/AI Sessions}"
SESSION_NOTE="$VAULT_PATH/$SESSION_DIR/$TODAY/$SAFE_SESSION_ID.md"

CANDIDATES_JSON="$(SECOND_BRAIN_VAULT_PATH="$VAULT_PATH" \
  python3 "$SCRIPT_DIR/distill.py" "${SESSION_NOTE}" 2>/dev/null)" || true

if [[ -z "$CANDIDATES_JSON" ]]; then
  exit 0
fi

CANDIDATE_COUNT="$(printf '%s' "$CANDIDATES_JSON" | jq '.candidates | length' 2>/dev/null || echo 0)"
if [[ "$CANDIDATE_COUNT" -eq 0 ]]; then
  exit 0
fi

# ── Phase 1: write template-compliant drafts to Meta/Promotions/ ─────────────

WRITER_JSON="$(printf '%s' "$CANDIDATES_JSON" | \
  SECOND_BRAIN_VAULT_PATH="$VAULT_PATH" \
  python3 "$SCRIPT_DIR/distill-writer.py" \
    --session-id "$SAFE_SESSION_ID" \
    --date "$TODAY" 2>/dev/null)" || true

DRAFT_COUNT=0
DRAFT_PATHS=""
if [[ -n "$WRITER_JSON" ]]; then
  DRAFT_COUNT="$(printf '%s' "$WRITER_JSON" | jq '.written | length' 2>/dev/null || echo 0)"
  DRAFT_PATHS="$(printf '%s' "$WRITER_JSON" | jq -r '.written[].path' 2>/dev/null || true)"
fi

# ── Format compact summary ────────────────────────────────────────────────────

SUMMARY="$(printf '%s' "$CANDIDATES_JSON" | python3 - "$DRAFT_COUNT" "$DRAFT_PATHS" <<'PY'
import json, sys

data = json.load(sys.stdin)
draft_count = int(sys.argv[1]) if len(sys.argv) > 1 else 0
draft_paths = sys.argv[2] if len(sys.argv) > 2 else ""

candidates = data.get("candidates", [])
lines = []
for c in candidates[:10]:  # cap at 10 to avoid bloat
    dest = c.get("destination", "?")
    action = c.get("action", "?")
    signal = c.get("signal", "")[:80]
    if len(c.get("signal", "")) > 80:
        signal += "..."
    lines.append(f"  - [{action}] {dest}: {signal}")
if draft_count and int(draft_count) > 0:
    lines.append(f"  → {draft_count} 件の草案を Meta/Promotions/ に書き込みました")
print("\n".join(lines))
PY
)"

[[ -n "$SUMMARY" ]] || exit 0

# ── Append to Daily ## AI Session (fcntl lock, same pattern as session-memory.sh) ──

python3 - "$DAILY_NOTE" "$MARKER" "$TIME_LABEL" "$CANDIDATE_COUNT" "$SUMMARY" <<'PY'
import sys, pathlib, fcntl, time

daily_path = pathlib.Path(sys.argv[1])
marker     = sys.argv[2]
time_label = sys.argv[3]
count      = sys.argv[4]
summary    = sys.argv[5]

entry = (
    f"\n- {time_label} Distill candidates ({count}) <!-- {marker} -->\n"
    f"{summary}\n"
)

lock_path = daily_path.parent / f".{daily_path.name}.lock"
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
    if acquired:
        text = daily_path.read_text()
        heading = "## AI Session"
        if heading in text:
            idx = text.rindex(heading) + len(heading)
            # find next ## heading after AI Session
            next_h2 = text.find("\n## ", idx)
            if next_h2 == -1:
                text = text.rstrip("\n") + entry
            else:
                text = text[:next_h2] + entry + text[next_h2:]
        else:
            text = text.rstrip("\n") + f"\n\n{heading}{entry}"
        daily_path.write_text(text)
finally:
    if acquired:
        fcntl.flock(lf, fcntl.LOCK_UN)
    lf.close()
PY

exit 0
