# second-brain

`second-brain` is a Claude Code plugin repository for running an Obsidian-backed Knowledge OS: a guarded external cognition stack where notes act as long-term memory, Claude Code acts as executive function, and hooks act as a deterministic nervous system.

This version adds live session capture so notes keep accumulating while Claude Code is working, not only after the session ends.

The current defaults are designed to fit [`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault): `Daily/` already exists for journal capture, and `Meta/` is the natural place for detailed AI session logs.

## Core Model

- Obsidian vault: durable long-term memory
- Claude Code: planning, execution, and summarization
- Context window and scratch buffers: working memory
- Hooks and scripts: reflexes, safety gates, and post-action checks

## Repository Layout

- [`CLAUDE.md`](./CLAUDE.md): operating constitution for the Knowledge OS
- [`hooks/hooks.json`](./hooks/hooks.json): Claude Code hook wiring
- [`scripts/`](./scripts): guardrail and validation scripts used by hooks
- [`commands/`](./commands): reusable operational commands
- [`agents/`](./agents): specialist agents for review, security, debugging, and analysis
- [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json): local plugin manifest
- [`settings.json`](./settings.json): Claude Code environment flags

## What Works Today

- Blocks edits to protected files such as `.git/` and common secret files
- Rejects write-capable SQL commands when database tools are invoked from Bash
- Runs lightweight syntax validation after editing `json`, `sh`, and `py` files
- Creates or reuses `Daily/YYYY-MM-DD.md` and appends a live `## AI Session` trail during the session
- Creates `Meta/AI Sessions/YYYY-MM-DD/<session-id>.md` for detailed per-session capture
- Aligns with the folder model used by `Template-Vault`
- Provides starter commands and specialist agents for operating the system

## Session Flow

- `SessionStart`: create the daily note if needed and open a session note
- `UserPromptSubmit`: append a concise line to `Daily/... ## AI Session` and the full prompt to the session note
- `PostToolUse` for `Write|Edit|MultiEdit`: append edited file activity to the session note
- `Stop`: append a closing line to the daily note and session note

## Configuration

The plugin reads these environment variables from [`settings.json`](./settings.json):

- `SECOND_BRAIN_VAULT_PATH`
- `SECOND_BRAIN_DAILY_DIR`
- `SECOND_BRAIN_SESSION_DIR`
- `SECOND_BRAIN_CAPTURE_STRICT`

With the current defaults, session notes accumulate in the Obsidian vault at:

- `Daily/YYYY-MM-DD.md`
- `Meta/AI Sessions/YYYY-MM-DD/<session-id>.md`

## Template-Vault

If your actual vault is a local clone of [`Template-Vault`](https://github.com/masuda-so/Template-Vault), point `SECOND_BRAIN_VAULT_PATH` at that clone and the plugin will append into the existing `Daily/` and `Meta/` structure without needing extra folders up front.

This repository is the control plane, not the vault itself. Its job is to make the AI side of the system safer, more legible, and easier to evolve.
