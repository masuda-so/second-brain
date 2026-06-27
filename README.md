# second-brain

[日本語版](README.ja.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)
[![Version: 0.2.0](https://img.shields.io/badge/version-0.2.0-lightgrey.svg)](#)

[Japanese README is here](./README.md)

## Overview

`second-brain` is a control layer for a Knowledge OS that integrates Claude Code with an Obsidian vault.
It automatically captures Claude Code session activity and produces structured Obsidian notes.

## Key capabilities

- Hook-based capture of the Claude Code session lifecycle (start, prompt submit, tool use, edit, stop, end)
- Session logging: prompts, tool outputs, and edits are reflected into the vault
- Guard scripts that block destructive operations (`PreToolUse` / `PostToolUse` guards)
- Automatic session logs in `Meta/AI Sessions` plus daily, weekly, and monthly note creation
- Draft distillation via `Distill` into `Meta/Promotions`
- Safe promotion workflow via `/promote` to `References/` and other durable areas
- Git pre-commit hook to prevent unsafe vault changes

## Why it's useful

- Keeps thoughts and decisions organized in the vault during sessions, instead of leaving them scattered in logs
- Aligns AI outputs to your vault naming and folder conventions
- Prevents destructive operations through guard scripts (`guard-files.sh`, `guard-vault-rm.sh`, `on-edit-check.sh`)
- Review-gated promotion flow maintains edit trust between humans and AI
- `.claude/settings.local.json` centralizes vault configuration while `.gitignore` preserves privacy

## Quickstart

### Requirements

- macOS or Linux
- Claude Code with local plugin support
- `jq`
- `python3`
- An Obsidian vault (with the expected folder structure is recommended)

### Setup

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

`init.sh` verifies:

- `jq` and `python3` are installed
- writes `SECOND_BRAIN_VAULT_PATH` to `.claude/settings.local.json`
- patches `CLAUDE.md` with the active vault path
- installs the git pre-commit hook
- registers `hooks/hooks.json` into local settings
- validates hook JSON
- syncs templates into the vault

### Running in Claude Code

Open this repo as a Claude Code project. The plugin manifest and hooks are discovered automatically.

### Built-in commands

- `/status` — plugin health and status
- `/logs` — recent hook / script output
- `/promote` — promote staged drafts from `Meta/Promotions`

## Repository layout

| Path | Role |
|------|------|
| [`hooks/hooks.json`](./hooks/hooks.json) | Claude Code hook registrations |
| [`hooks/pre-commit`](./hooks/pre-commit) | Pre-commit guard for vault safety |
| [`scripts/init.sh`](./scripts/init.sh) | Bootstrap and validation |
| [`scripts/harvest.py`](./scripts/harvest.py) | Session artifact collection |
| [`scripts/distill.py`](./scripts/distill.py) | Summarization and note distillation |
| [`scripts/distill-draft.py`](./scripts/distill-draft.py) | Draft generation |
| [`scripts/promote.py`](./scripts/promote.py) | Approved draft promotion |
| [`scripts/guard-files.sh`](./scripts/guard-files.sh) | File-operation guards |
| [`scripts/guard-vault-rm.sh`](./scripts/guard-vault-rm.sh) | Prevents vault deletion operations |
| [`scripts/on-edit-check.sh`](./scripts/on-edit-check.sh) | Edit validation hook |
| [`commands/`](./commands) | Entry points for `/status`, `/logs`, `/promote`, etc. |
| [`agents/`](./agents) | Session summarizer, security reviewer, performance tester, and others |
| [`skills/`](./skills) | Distillation, defuddling, Markdown conversion, Bases operations, and more |
| [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) | CI for hooks, scripts, and init |
| [`pyproject.toml`](./pyproject.toml) | pytest configuration |
| [`CLAUDE.md`](./CLAUDE.md) | Vault operating rules and AI behavior |

## Note lifecycle

- `Ideas/` — low-score auto-sketches
- `Meta/Promotions/` — drafts awaiting human review
- `References/` — promoted, high-confidence knowledge
- `Projects/` — manually curated project notes
- `Clippings/` — unprocessed source material

## Status

Early access control layer for Claude Code sessions and Obsidian vault integration.

## Quickstart

## Development

## Testing

```bash
brew install jq

# init validation
bash scripts/init.sh "/path/to/tmp/vault"

# Python unit tests
python3 -m pytest scripts/tests/
```

## Support

## Help

- [CLAUDE.md](./CLAUDE.md) — vault operating conventions
- [commands/status.md](./commands/status.md) — `/status` reference
- [commands/logs.md](./commands/logs.md) — `/logs` reference
- issues — include setup steps and `./scripts/init.sh` output

## Maintainers and contributing

Maintainer: **masudaso**

Issues and pull requests are welcome. Prefer small, reversible changes that keep user vaults safe and align with [`CLAUDE.md`](./CLAUDE.md). Update docs when changes affect setup or operator workflows.

## License

MIT License. See [LICENSE](./LICENSE).
