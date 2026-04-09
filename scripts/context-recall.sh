#!/bin/bash

# Context Recall Layer
# Hook: UserPromptSubmit
# Searches the vault for notes relevant to the current prompt and injects
# them into Claude's context via hookSpecificOutput.additionalContext.
# Also appends a ## Recalled Context section to the session note.
# Always exits 0 (fail-open) so it never blocks user prompts.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT="$(cat 2>/dev/null || true)"

warn() {
  echo "second-brain: context-recall: $*" >&2
}

bail() {
  warn "$*"
  exit 0
}

command -v jq      >/dev/null 2>&1 || bail "jq is required"
command -v python3 >/dev/null 2>&1 || bail "python3 is required"

VAULT_PATH=""
if [[ -n "${SECOND_BRAIN_VAULT_PATH:-}" ]]; then
  VAULT_PATH="${SECOND_BRAIN_VAULT_PATH%/}"
else
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" 2>/dev/null | head -n 1)
  VAULT_PATH="${VAULT_PATH%/}"
fi
[[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]] || bail "vault not found"

PROMPT="$(printf '%s' "$INPUT" | jq -r '.prompt // .message // .user_prompt // .userPrompt // .input // empty' 2>/dev/null || true)"
[[ -n "$PROMPT" ]] || exit 0

SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // .sessionId // empty' 2>/dev/null || true)"
[[ -z "$SESSION_ID" ]] && SESSION_ID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown-session}}"
SAFE_SESSION_ID="$(printf '%s' "$SESSION_ID" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-//; s/-$//')"
[[ -z "$SAFE_SESSION_ID" ]] && SAFE_SESSION_ID="unknown-session"

TODAY="$(date '+%Y-%m-%d')"
TIME_LABEL="$(date '+%H:%M')"
SESSION_DIR="${SECOND_BRAIN_SESSION_DIR:-Meta/AI Sessions}"
SESSION_NOTE_PATH="$VAULT_PATH/$SESSION_DIR/$TODAY/$SAFE_SESSION_ID.md"

# Delegate all search/score/output logic to Python for portability
OUTPUT="$(VAULT_PATH="$VAULT_PATH" SESSION_NOTE_PATH="$SESSION_NOTE_PATH" TIME_LABEL="$TIME_LABEL" \
  python3 - "$PROMPT" <<'PYEOF'
import os, sys, re, pathlib, json, subprocess
from datetime import datetime

prompt = sys.argv[1]
vault_path = pathlib.Path(os.environ["VAULT_PATH"])
session_note = pathlib.Path(os.environ["SESSION_NOTE_PATH"])
time_label = os.environ["TIME_LABEL"]

STOP_WORDS = set("""
the and for are this that with from what how can you your its has have was will but not all
use get set let new old run add fix see did been they them their would could should when where
into also just then here some more very only each both does than like same over any our per via
yet now too yes no
""".split())

PATH_WEIGHTS = {"Projects": 3, "References": 3, "Daily": 2, "Ideas": 2, "Meta": 2}
# AI Sessions inside Meta are weak signals — handled before generic Meta lookup
AI_SESSIONS_WEIGHT = 1

def extract_keywords(text):
    words = re.sub(r'[^a-z0-9\s]', ' ', text.lower()).split()
    freq = {}
    for w in words:
        if len(w) >= 3 and w not in STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda k: -freq[k])[:8]

def path_weight(p):
    # Check for AI Sessions before generic Meta to avoid over-weighting session logs
    p_str = str(p)
    if "AI Sessions" in p_str or "AI_Sessions" in p_str:
        return AI_SESSIONS_WEIGHT
    for part in p.parts:
        if part in PATH_WEIGHTS:
            return PATH_WEIGHTS[part]
    return 1

def recency_weight(p):
    try:
        mtime = p.stat().st_mtime
        days = (datetime.now().timestamp() - mtime) / 86400
        if days <= 7:   return 3
        if days <= 30:  return 2
        return 1
    except Exception:
        return 1

def keyword_hits(p, keywords):
    try:
        text = p.read_text(errors="ignore").lower()
        return sum(text.count(kw) for kw in keywords)
    except Exception:
        return 0

def extract_snippet(p):
    try:
        lines = p.read_text(errors="ignore").splitlines()
        in_fm = False
        out = []
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if i == 0:
                    in_fm = True; continue
                elif in_fm:
                    in_fm = False; continue
            if in_fm:
                continue
            if line.startswith("#") or (line.strip() and not line.startswith("-")):
                out.append(line.strip())
            if len(out) >= 2:
                break
        snippet = " ".join(out).strip()
        return snippet[:117] + "..." if len(snippet) > 120 else snippet or "(no preview)"
    except Exception:
        return "(no preview)"

keywords = extract_keywords(prompt)
if not keywords:
    sys.exit(0)

search_dirs = [vault_path / d for d in ("Daily", "Projects", "References", "Ideas", "Meta") if (vault_path / d).is_dir()]
if not search_dirs:
    sys.exit(0)

candidates = []
for d in search_dirs:
    for f in d.rglob("*.md"):
        if f == session_note:
            continue
        candidates.append(f)

scored = []
for f in candidates:
    hits = keyword_hits(f, keywords)
    if hits == 0:
        continue
    score = hits * recency_weight(f) * path_weight(f)
    scored.append((score, f))

scored.sort(key=lambda x: (-x[0], str(x[1])))
top = [f for _, f in scored[:5]]

if not top:
    sys.exit(0)

lines = []
for f in top:
    rel = str(f.relative_to(vault_path))
    rel_no_ext = re.sub(r'\.md$', '', rel)
    snippet = extract_snippet(f)
    lines.append(f"- [[{rel_no_ext}]] — {snippet}")

context_block = "\n".join(lines)

# Append to session note (with advisory flock — same pattern as session-memory.sh)
if session_note.exists():
    import fcntl, time as _time
    lock_path = session_note.parent / f".{session_note.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(lock_path, "w")
    acquired = False
    try:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            for _ in range(100):
                _time.sleep(0.05)
                try:
                    fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    pass
        if acquired:
            try:
                text = session_note.read_text()
                marker = "## Recalled Context"
                entry = f"\n### {time_label} Recalled Context\n\n{context_block}\n"
                if marker in text:
                    # Insert before next ## heading after marker
                    idx = text.index(marker) + len(marker)
                    next_h2 = text.find("\n## ", idx)
                    if next_h2 == -1:
                        text = text + entry
                    else:
                        text = text[:next_h2] + entry + text[next_h2:]
                else:
                    text = text.rstrip("\n") + f"\n\n{marker}{entry}"
                session_note.write_text(text)
            except Exception:
                pass
    finally:
        if acquired:
            fcntl.flock(lf, fcntl.LOCK_UN)
        lf.close()

# Emit additionalContext — hookEventName goes inside hookSpecificOutput
inject = f"Relevant vault context for this prompt:\n{context_block}"
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": inject
    }
}))
PYEOF
)" 2>/dev/null || exit 0

[[ -n "$OUTPUT" ]] && printf '%s\n' "$OUTPUT"
exit 0
