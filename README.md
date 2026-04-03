# second-brain

`second-brain` is a Claude Code plugin repository for running an Obsidian-backed Knowledge OS: a guarded external cognition stack where notes act as long-term memory, Claude Code acts as executive function, and hooks act as a deterministic nervous system.

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
- Provides starter commands and specialist agents for operating the system

## Near-Term Extensions

- Connect the plugin to the real Obsidian vault layout and note schemas
- Add session summaries and memory compaction workflows
- Introduce durable logs for blocked actions and hook outcomes
- Add structured Bases sync and health checks

This repository is the control plane, not the vault itself. Its job is to make the AI side of the system safer, more legible, and easier to evolve.
