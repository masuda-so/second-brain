[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)

[日本語版はこちら](./README.ja.md)

# second-brain

`second-brain` is a local Claude Code plugin repository for running an Obsidian-backed Knowledge OS. It gives Claude Code a safer control plane for external memory: live session capture, lightweight guardrails, and reusable operator workflows that write useful context back into your vault.

> This repository is the **control layer**. Your Obsidian vault remains the long-term memory store.

## What the project does

`second-brain` connects three pieces into one workflow:

- **Obsidian** stores durable notes and project memory
- **Claude Code** handles planning, execution, and summarization
- **Hooks and scripts** add deterministic safety checks and session capture

The default setup is designed to work well with [`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault), especially its `Daily/` and `Meta/` structure.

## Why this project is useful

Key benefits for developers and knowledge workers:

- **Live session capture** — prompts, tool events, and closeout notes are appended while Claude Code is working
- **Guarded automation** — protected files are blocked and write-capable SQL is rejected from Bash flows
- **Lightweight validation** — edited `json`, `sh`, and `py` files are syntax-checked automatically
- **Vault-friendly defaults** — notes land in predictable places such as `Daily/` and `Meta/AI Sessions/`
- **Operator tooling included** — reusable `commands/`, `agents/`, and `skills/` help with debugging, review, and maintenance

## Repository layout

| Path | Purpose |
| --- | --- |
| [`CLAUDE.md`](./CLAUDE.md) | Operating constitution and vault rules |
| [`hooks/hooks.json`](./hooks/hooks.json) | Hook wiring for session lifecycle and safety gates |
| [`scripts/`](./scripts) | Shell and Python utilities for validation, capture, and initialization |
| [`commands/`](./commands) | Reusable operational prompts such as status and log review |
| [`agents/`](./agents) | Specialist agents for review, security, debugging, and analysis |
| [`skills/`](./skills) | Domain-specific helpers for Obsidian and note workflows |
| [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) | Local plugin manifest |
| [`settings.json`](./settings.json) | Environment configuration for your vault integration |

## Getting started

### Prerequisites

Before setup, make sure you have:

- **macOS or Linux**
- **Claude Code** with local plugin support
- **`jq`** and **`python3`** available on your `PATH`
- An **Obsidian vault** (a local clone of Template-Vault is the recommended default)

### 1. Clone the repository

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
```

### 2. Configure your vault path

If `settings.json` does not exist yet, create it from the example:

```bash
cp settings.json.example settings.json
```

Then set `SECOND_BRAIN_VAULT_PATH` to your local vault path in [`settings.json`](./settings.json), or pass the path directly to the init script.

### 3. Run the setup check

```bash
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

The init script will:

1. verify `jq` and `python3`
2. ensure scripts are executable
3. validate [`hooks/hooks.json`](./hooks/hooks.json)
4. resolve your vault path
5. check expected vault folders
6. sync starter templates into `Templates/`

## Configuration

The plugin reads these environment variables from [`settings.json`](./settings.json):

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECOND_BRAIN_VAULT_PATH` | Absolute path to your Obsidian vault | required |
| `SECOND_BRAIN_DAILY_DIR` | Folder used for daily notes | `Daily` |
| `SECOND_BRAIN_SESSION_DIR` | Folder used for detailed AI session logs | `Meta/AI Sessions` |
| `SECOND_BRAIN_CAPTURE_STRICT` | When set to `1`, capture problems fail the hook instead of failing open | `0` |

## Usage examples

### Run one-time setup

```bash
./scripts/init.sh "/Users/you/Documents/Obsidian Vault"
```

### Inspect system health from Claude Code

Use the prompt in [`commands/status.md`](./commands/status.md) to review:

- hook coverage
- config drift
- incomplete files
- operational risks

### Review recent issues or missing logs

Use [`commands/logs.md`](./commands/logs.md) to inspect recent failures or to confirm when extra logging is needed.

### Expected vault output

With the default configuration, active sessions will create or update paths like:

```text
Daily/2026-04-05.md
Meta/AI Sessions/2026-04-05/<session-id>.md
Meta/Promotions/
```

## Session flow

The default hook lifecycle is:

- **`SessionStart`** → start or reopen the daily note and session note
- **`UserPromptSubmit`** → append a concise summary to `## AI Session` and the full prompt to the session note
- **`PostToolUse`** → record file edits and queue note harvesting
- **`Stop` / `SessionEnd`** → checkpoint promotions and append closeout context

## Where to get help

If you are getting started or debugging setup, use these resources first:

- [`CLAUDE.md`](./CLAUDE.md) — operating model, vault conventions, and safety defaults
- [`commands/status.md`](./commands/status.md) — quick operational review
- [`commands/logs.md`](./commands/logs.md) — recent failures and logging guidance
- [`README.ja.md`](./README.ja.md) — Japanese overview

If something still looks wrong, open an issue in this repository with your setup steps and the output from `./scripts/init.sh`.

## Maintainers and contributions

Maintained by **masudaso**.

Contributions are welcome through issues and pull requests. Until a dedicated `CONTRIBUTING.md` is added, please keep changes:

- **small and reversible**
- aligned with the rules in [`CLAUDE.md`](./CLAUDE.md)
- safe for user vaults and secret material
- documented when they change operator behavior or setup steps

## License

Released under the **MIT License**. See [`LICENSE`](./LICENSE) for details.
