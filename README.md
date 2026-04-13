[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)
[![Version: 0.2.0](https://img.shields.io/badge/version-0.2.0-lightgrey.svg)](#)

[日本語版はこちら](./README.ja.md)

# second-brain

A local Claude Code plugin that turns an Obsidian vault into an autonomous Knowledge OS.
This repository is the control layer: session capture, guardrails, structured note drafts, and promotion workflows.

## What the project does

`second-brain` captures Claude Code session activity and uses it to generate structured Obsidian notes automatically.
It manages:

- Claude Code hooks for session lifecycle events
- local plugin commands and agents for workflow control
- guard scripts that protect your vault from unsafe edits
- staged drafting and promotion into `Ideas/`, `Meta/Promotions/`, and `References/`

The Obsidian vault is the long-term memory store, while this repo orchestrates how notes are captured, reviewed, and promoted.

## Why this project is useful

- Enables friction-free knowledge capture from Claude Code sessions
- Keeps AI-generated output aligned to structured vault conventions
- Prevents accidental destructive shell or file operations
- Automates daily, weekly, monthly, and session summaries
- Makes review explicit by staging draft content before final promotion

## Key features

- Hook wiring for `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, and `SessionEnd`
- Prompt and tool capture via `scripts/session-memory.sh`
- Harvest queue, worker, and flush pipeline in `scripts/harvest.py`
- Draft distillation with `scripts/distill.py` and `scripts/distill-draft.py`
- Promotion workflow with `scripts/promote.py`
- Observable vault guardrail scripts under `scripts/`
- Plugin manifest, agent prompts, commands, and skills for Claude Code

## Getting started

### Prerequisites

- macOS or Linux
- Claude Code with local plugin support
- `jq` installed
- `python3` available on `PATH`
- An Obsidian vault with a compatible note structure

### 1. Clone the repository

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
```

### 2. Configure your vault path

Run the init helper with your vault location:

```bash
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

This setup step:

- validates `jq` and `python3`
- writes `SECOND_BRAIN_VAULT_PATH` to `.claude/settings.local.json`
- patches `CLAUDE.md` for the vault path
- installs the git pre-commit hook
- registers plugin hooks into local settings
- validates hook wiring and vault structure
- syncs starter templates into `Templates/`

### 3. Open in Claude Code

Open this repo as a Claude Code project. The plugin manifest, hooks, commands, and skills will be discovered automatically.

### 4. Use built-in commands

In Claude Code, use commands such as:

- `/status` — view plugin status and session health
- `/logs` — inspect recent hook and script output
- `/promote` — move approved drafts from `Meta/Promotions/`

## Repository structure

| Path | Purpose |
|------|---------|
| [`CLAUDE.md`](./CLAUDE.md) | Operating rules, vault conventions, AI behaviour |
| [`hooks/hooks.json`](./hooks/hooks.json) | Session hook wiring |
| [`hooks/pre-commit`](./hooks/pre-commit) | Git guard hook for vault safety |
| [`scripts/`](./scripts) | Core shell and Python utilities |
| [`agents/`](./agents) | Claude agent prompts |
| [`commands/`](./commands) | Operator command documentation |
| [`skills/`](./skills) | Obsidian workflow helper skills |
| [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) | Claude Code plugin manifest |
| [`settings.json.example`](./settings.json.example) | Example environment settings |

## How it works

Session lifecycle hooks capture prompts, tools, and edits, then surface structured drafts for review:

- `SessionStart` initializes session context, daily/weekly notes, and starts capture
- `UserPromptSubmit` logs prompts and queues harvested content
- `PreToolUse` blocks unsafe file or shell operations
- `PostToolUse` validates edits and captures tool outputs
- `Stop` runs the harvest worker
- `SessionEnd` flushes queued content and distills session notes

## Note lifecycle

- `Ideas/` — low-score auto-sketches
- `Meta/Promotions/` — staged drafts awaiting human review
- `References/` — high-confidence promoted content
- `Projects/` — manual-only project notes

## Configuration

Local configuration belongs in `.claude/settings.local.json`. Key environment variables:

- `SECOND_BRAIN_VAULT_PATH` — required absolute vault path
- `SECOND_BRAIN_DAILY_DIR` — default `Daily`
- `SECOND_BRAIN_SESSION_DIR` — default `Meta/AI Sessions`
- `SECOND_BRAIN_CAPTURE_STRICT` — `1` makes hook failures fatal instead of fail-open

## Help and documentation

- [`CLAUDE.md`](./CLAUDE.md) — main operating guide and vault rules
- [`commands/status.md`](./commands/status.md) — status command reference
- [`commands/logs.md`](./commands/logs.md) — log troubleshooting reference
- [`README.ja.md`](./README.ja.md) — Japanese README

If you need help, open an issue with your setup details and the output from `./scripts/init.sh`.

## Maintainers and contributions

Maintained by **masudaso**.

Contributions are welcome via issues and pull requests. Prefer changes that are:

- small and reversible
- safe for user vaults
- aligned with `CLAUDE.md` rules
- documented when they affect setup or operator workflow

## License

Released under the **MIT License**. See [`LICENSE`](./LICENSE) for details.
