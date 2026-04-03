---
description: Distill today's session notes into a concise Daily summary
---

# Distill Session Notes

Read today's accumulated session notes and synthesize a concise summary into the Daily note.

## Steps

1. Get today's date by running `date +%Y-%m-%d`.

2. Determine the vault path from the `SECOND_BRAIN_VAULT_PATH` environment variable.
   If not set, read `CLAUDE.md` in the current repository and extract the path from the
   `## Vault` section (`- Location: \`...\``).

3. Find all session notes for today:
   - Glob `<vault>/Meta/AI Sessions/<today>/*.md`
   - If no files exist, report "No session notes found for today." and stop.

4. Read each session note. Focus on:
   - `## Captures` — what the user worked on (user prompts, verbatim)
   - `## Tool Events` — which files were modified

5. Synthesize a summary of 3–5 bullet points covering:
   - What was accomplished or explored
   - Key decisions or insights reached
   - Files modified (list only if relevant, omit noise like session-memory reads)
   - Open questions or next actions (only if clearly present)

6. Append the summary to `<vault>/Daily/<today>.md` under the `## AI Session` heading.
   Use the sub-heading format below. Do NOT duplicate individual session links that
   the hook already added — only add the `#### Summary` block.

## Output format (written into Daily note)

```
#### Summary (HH:MM)
- ...
- ...
- ...
```

Use the current time (HH:MM) in the heading.
Keep each bullet under 120 characters.
Write in the same language the user used during the session.
