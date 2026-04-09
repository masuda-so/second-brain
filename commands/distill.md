---
description: Distill durable knowledge from the current session into the vault. Extracts facts, decisions, and patterns from the session note and today's Daily log, then routes them to References/, Projects/, or the appropriate Base. Run at the end of a working session.
---

You are performing a knowledge distillation pass for the second-brain Knowledge OS.

## Inputs

Resolve sources in this order (stop when found):

1. If `$ARGUMENTS` contains a file path, use that as the session note.
2. Otherwise look for the session note at:
   `$SECOND_BRAIN_VAULT_PATH/Meta/AI Sessions/<today>/<session-id>.md`
   where `<today>` is today's date (YYYY-MM-DD) and `<session-id>` is `$CLAUDE_SESSION_ID` or `$CLAUDE_CODE_SESSION_ID`.
3. Also read today's Daily note: `$SECOND_BRAIN_VAULT_PATH/Daily/<today>.md` (specifically the `## AI Session` and `## メモ` sections).

Read both files before doing anything else.

## What to distill

Scan both notes for content with lasting value — content that would be useful in a future session. Classify each piece:

| Signal | Destination |
|--------|-------------|
| Conceptual fact, how-something-works explanation, technique | `References/<slug>.md` |
| Decision and its rationale | append to `Projects/<slug>.md` under `## 関連ノート` or create a new `References/decisions-<date>.md` |
| Tool/library pattern or runbook step | `References/<slug>.md` |
| Project status change (goal, blockers, next actions) | update `Projects/<slug>.md` in-place |
| Unprocessed idea worth pursuing | `Ideas/<slug>.md` (status: incubating) |
| Pure ephemeral noise (shell output, error traces, temp notes) | skip — do not distill |

## Rules

- **Read before writing**: inspect the target note before modifying it. If the note already contains the substance, do not duplicate it — at most append a link or a short update.
- **Prefer append over rewrite**: for `Daily/` and `Projects/` notes, append to the relevant section. Rewrite only when the section is clearly stale.
- **Atomic notes**: one concept per References note. If a topic needs more than ~400 words, split it into two notes with a wikilink between them.
- **Wikilink everything**: any new or updated note must be linked from the source (Daily or session note) using `[[path/to/note]]` syntax (no `.md` extension).
- **Never delete vault content**: use `#archived` tag on anything superseded rather than deleting.
- **Frontmatter required**: every created note must have the correct frontmatter for its type (see CLAUDE.md Note Templates section).

## Execution steps

1. **Run the extraction helper** to get a structured candidate list:
   ```
   # Pass explicit session note path (recommended):
   python3 $CLAUDE_PLUGIN_ROOT/scripts/distill.py \
     "$SECOND_BRAIN_VAULT_PATH/Meta/AI Sessions/<today>/<session-id>.md"

   # Or pass session-id and let the script resolve the path:
   python3 $CLAUDE_PLUGIN_ROOT/scripts/distill.py \
     --session-id "$CLAUDE_SESSION_ID"
   ```
   Vault path is read from `$SECOND_BRAIN_VAULT_PATH` automatically.
   If the script is not yet available, fall back to step 2 (manual scan).
   The script outputs `{"candidates": [...]}` JSON to stdout — parse and use it as your starting candidate list.

2. **Read both source notes directly** as well. The script may miss implicit signals (tone, context, decisions embedded in prose). Merge any additional candidates you find into the list.

3. List every candidate with its proposed destination and action (`create` / `append` / `skip`). Show this list before writing anything.

4. For each candidate with action `create` or `append`:
   a. State the destination path.
   b. Check if the destination exists — read it if so.
   c. Write (create or append) only the durable content, stripped of session noise.
   d. Add a wikilink back from the daily note's `## AI Session` section.
5. Update `Projects/<slug>.md` if project status, next actions, or last decisions changed.
6. Print a summary table:

```
## Distillation Summary

| Note | Action | Content |
|------|--------|---------|
| References/foo.md | created | ... |
| Projects/bar.md | updated | Next Actions updated |
```

If no durable content is found, say so clearly and exit — do not create empty notes.
