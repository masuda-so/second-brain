# CLAUDE.md

This repository is the control layer for a personal Knowledge OS built from Claude Code, deterministic hooks, and an Obsidian vault.

## Mission

Treat the user's vault as external memory, not disposable scratch space. The system should help the user think, decide, and retrieve context faster while preserving trust, provenance, and reversibility.

## Cognitive Mapping

- Long-term memory: the Obsidian vault and its durable notes, especially structures such as `Daily/`, `Projects/`, `Bases/`, `Areas/`, `Resources/`, and `Archive/`.
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
