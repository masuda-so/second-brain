---
description: Run a vault health check. Detects orphan pages, broken wikilinks, frontmatter issues, stale notes, and low-quality Ideas. Use regularly to keep the vault healthy as it grows.
---

You are performing a vault health audit for the second-brain Knowledge OS.

## How to run

```bash
SECOND_BRAIN_VAULT_PATH="$SECOND_BRAIN_VAULT_PATH" \
  python3 "$CLAUDE_PLUGIN_ROOT/scripts/lint.py" check --format json
```

Parse the JSON output to understand the vault's current health.

## Interpreting results

The script returns:

```json
{
  "summary": {"total_notes": N, "issues": N, "fixable": N, "by_severity": {...}, "by_check": {...}},
  "issues": [{"severity": "...", "check": "...", "path": "...", "message": "...", "fixable": bool}]
}
```

### Check types

| Check | Severity | Meaning |
|-------|----------|---------|
| `orphan_pages` | medium | References/ or Ideas/ note with zero inbound wikilinks |
| `broken_links` | low | `[[wikilink]]` pointing to a non-existent note |
| `frontmatter` | medium/low | Missing required YAML fields for the note's type |
| `stale_notes` | low | Old note (>90 days) with no inbound links |
| `low_quality` | medium | Ideas/ note with near-empty body (<50 chars) |

## What to do with the results

Present the results as a prioritized summary table. Then offer these actions:

1. **Orphan pages**: Suggest adding `[[wikilinks]]` from related notes (Daily, Projects, or other References). Use keyword overlap to find candidates. Do NOT delete orphans — they may still have value.

2. **Broken links**: Check if the target was renamed or moved. If so, update the link. If the note never existed, either create a stub or remove the link.

3. **Frontmatter issues**: Run `lint.py fix` to auto-add missing `type` fields, or manually add missing fields.

4. **Stale notes**: Review whether the note is still relevant. If yes, add links to it. If not, add `#archived` tag.

5. **Low-quality Ideas**: Either flesh out the note body or archive it if the idea is no longer worth pursuing.

## Rules

- **Never delete vault content** — use `#archived` tag instead.
- **Read before writing** — inspect any note before modifying it.
- **One issue at a time** — address issues interactively with the user, don't batch-fix everything silently.
- After fixing issues, re-run the check to confirm improvement.
