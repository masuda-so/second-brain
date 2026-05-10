# CLAUDE.md

This repository is the control layer for a personal Knowledge OS built from Claude Code, deterministic hooks, and an Obsidian vault.

## Mission

Treat the user's vault as external memory, not disposable scratch space. The system should help the user think, decide, and retrieve context faster while preserving trust, provenance, and reversibility.

## Cognitive Mapping

- Long-term memory: the Obsidian vault and its durable notes, especially structures such as `Daily/`, `Weekly/`, `Monthly/`, `Projects/`, `References/`, `Clippings/`, `Ideas/`, `Meta/`, `Bases/`, `Canvases/`, and `Sandbox/`.
- Working memory: the current Claude Code context window, active task notes, and any temporary scratch buffers created during a task.
- Executive function: planning, decomposition, task execution, validation, and summarization performed by Claude Code.
- Nervous system: hooks and validation scripts that intercept risky actions before or after tools run.

## Operating Principles

1. Preserve memory before optimizing it.
2. Prefer small, reversible edits over large structural rewrites.
3. Do not invent vault structure. Discover existing conventions first and align to them.
4. Durable knowledge should be distilled, linked, and named clearly enough to be found again.
5. Temporary reasoning belongs in working memory or scratch notes, not in permanent knowledge artifacts unless it remains useful after the session.
6. Hooks must stay deterministic, fast, and easy to audit.
7. Protect secrets, system files, and repository integrity before convenience.

## Repository Roles

- `.claude-plugin/plugin.json`: plugin manifest for Claude Code.
- `hooks/hooks.json`: hook wiring for guardrails and post-edit checks.
- `scripts/`: deterministic shell utilities used by hooks.
- `commands/`: reusable operator prompts for health checks and log review.
- `agents/`: specialist agents for review, compliance, debugging, data work, and performance checks.
- `settings.json`: local Claude Code environment flags for this repo.

## Default Workflow

1. Read the user's request and identify whether the target is capture, planning, execution, or knowledge distillation.
2. Inspect the relevant note, project, or operational file before changing it.
3. Use the hook layer to guard writes and validate edited files.
4. Summarize what changed, what remains uncertain, and the next most valuable action.

## Knowledge Hygiene

- Prefer atomic notes over giant catch-all documents.
- Link new knowledge to an existing project, area, or concept whenever possible.
- Distinguish facts, interpretations, and open questions.
- Keep summaries compressed enough to reload quickly into context.

## Safety Defaults

- Never write to `.git/` or obvious secret material.
- Treat destructive database operations as disallowed unless the user explicitly sets up a separate write-capable path.
- If a hook or validation script fails, surface the problem clearly rather than silently proceeding.

---

## Vault

- Location: `/Users/masudaso/Documents/Obsidian Vault/`
- This section serves as the Knowledge OS constitution for that vault.
- Session capture: accumulate prompts and key events during the session, then leave the distilled trail in `Daily/YYYY-MM-DD.md` under the `## AI Session` heading.
- All ambient knowledge — personal preferences, project learnings, AI-generated insights — goes to the vault, not Claude auto memory.

## Vault Architecture

| Directory | Cognitive Analogy | Purpose |
|-----------|-------------------|---------|
| `Daily/` | Episodic memory | Daily log: events, thoughts, AI session notes |
| `Weekly/` | Working memory consolidation | Weekly review and intentions |
| `Monthly/` | Long-term episodic | Monthly themes and retrospectives |
| `Projects/` | Procedural memory | Active work: status, goal, next actions |
| `Bases/` | Semantic memory DB | Structured facts: books, people, meetings, etc. |
| `References/` | Semantic memory | Permanent concept and source notes |
| `Ideas/` | Association cortex | Loose, unprocessed sparks |
| `Clippings/` | Sensory buffer | Web clips awaiting processing |
| `Meta/` | Metacognition | Vault rules, system notes, templates |
| `Canvases/` | Spatial reasoning | Visual maps and concept diagrams |
| `Sandbox/` | Training environment | Obsidian onboarding and safe experimentation |

## Note Templates

**Daily** (`Daily/YYYY-MM-DD.md`):
```
---
type: daily
date: YYYY-MM-DD
tags: []
---
## Focus
## Notes
## Follow-up
## Related notes
## AI Session
```

**Weekly** (`Weekly/YYYY-Www.md`):
```
---
type: weekly
week: YYYY-Www
tags: []
---
## Intentions
## Review
## Related notes
```

**Monthly** (`Monthly/YYYY-MM.md`):
```
---
type: monthly
month: YYYY-MM
tags: []
---
## Theme
## Key Events
## Retrospective
```

**Project** (`Projects/<slug>.md`):
```
---
type: project
status: active | completed | archived
review: YYYY-MM-DD
tags: []
---
## Outcome
## Next actions
## Related notes
```

**Reference** (`References/<slug>.md`):
```
---
type: reference
topic: topic-name
tags: []
---
```

## Bases Schema

Recommended YAML frontmatter properties for notes consumed by each Base:

- **Journal.base** — `Daily/` notes: `type: daily`, `date`, `tags`
- **Projects.base** — `Projects/` notes: `type: project`, `status`, `review`
- **Meetings.base** — meeting notes: `date`, `attendees`, `decision`
- **People.base** — people notes: `name`, `context`, `last-contact`
- **Books.base** — `title`, `author`, `status` (reading/done), `rating`
- **Clippings.base** — `source`, `date`, `tags`
- **Movies.base / Shows.base** — `title`, `status` (watched/want), `rating`
- **Music.base / Podcasts.base** — `title`, `artist`, `status`, `rating`
- **Places.base / Trips.base** — `location`, `date`, `tags`
- **Recipes.base** — `title`, `cuisine`, `time`, `rating`
- **Ratings.base** — cross-domain: `title`, `type`, `rating`, `date`

## AI Behavior Rules

- Read before writing: inspect the target note before any modification.
- Discover, don't invent: search existing notes before creating new ones.
- Prefer append over rewrite for Daily and Project notes.
- Route all new captures to `Daily/YYYY-MM-DD.md ## Notes` first.
- Distill durable knowledge to `References/` or the appropriate Base after the session.
- Never delete vault content — use `#archived` until the vault defines a dedicated archive location.
- AI session learnings -> append to `Daily/YYYY-MM-DD.md ## AI Session`.
- Detailed live capture -> `Meta/AI Sessions/YYYY-MM-DD/<session-id>.md`.

## Tagging Conventions

- Status: `#active`, `#archived`, `#someday`, `#waiting`
- Type: `#fact`, `#interpretation`, `#question`, `#idea`, `#project`
- Domain: `#tech`, `#ai`, `#personal`, `#work`, `#learning`

## L4 Ambient Capture

ALL knowledge from Claude Code sessions — personal preferences, project learnings, AI-generated insights — MUST go to the vault, not Claude auto memory.

Intake point: `Daily/YYYY-MM-DD.md ## AI Session`.
Durable distillations: `References/` or the appropriate Base.

## Note Lifecycle

```
Clippings/ / Ideas/    →    Daily/ (tagged + linked)    →    References/ or Base    →    tagged as #archived when no longer active
   (capture)                     (process)                       (distill)              
```
