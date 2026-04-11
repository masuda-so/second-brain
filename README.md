[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)

[日本語版はこちら](./README.ja.md)

# second-brain

`second-brain` is a local Claude Code plugin that turns your Obsidian vault into an autonomous Knowledge OS. Working with Claude Code is enough — notes accumulate on their own, structured to template conventions, without any manual capture effort.

> This repository is the **control layer**. Your Obsidian vault is the long-term memory store.

## Design principles

| Principle | Meaning |
|-----------|---------|
| **Zero-friction Capture** | No explicit note-taking. Working in Claude Code is enough for the vault to grow. |
| **Schema Enforcement** | AI output follows [`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault) and [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) structure — not free-form text. |
| **Human as a Filter** | AI writes; humans curate. Your only job is approve or delete drafts in `Meta/Promotions/`. |

## How it works

Three pipelines run automatically around your Claude Code session:

```
Working in Claude Code
      │
      ├─ session-memory.sh (always on) ──→ Meta/AI Sessions/  (raw log)
      │
      ├─ harvest.py (hook-driven)
      │    ├─ queue  [UserPromptSubmit / PostToolUse]
      │    ├─ worker [Stop] ────────────→ Ideas/  or  Meta/Promotions/
      │    └─ flush  [SessionEnd] ──────→ References/ auto-draft (L3) + Daily link
      │
      └─ [SessionEnd] session-distill.sh
           ├─ distill.py + distill-writer.py
           │    └─ claude -p ───────────→ Meta/Promotions/  (structured draft)
           └─ session-summarizer
                └─ claude -p ───────────→ Daily note  ### 要約 (AI)

Meta/Promotions/ → [human review] → /promote → References/  or  Ideas/
                                                (Projects/ is manual-only)
```

**Promotion levels** (harvest.py):

| Level | Score | Auto-target |
|-------|-------|-------------|
| L1 | ≥ 3 (≥ 2 in short sessions ≤ 5 prompts) | `Ideas/` |
| L2 | ≥ 6 | `Meta/Promotions/` |
| L3 | ≥ 9 | `References/` auto-draft + Daily link |

## Repository layout

| Path | Purpose |
|------|---------|
| [`CLAUDE.md`](./CLAUDE.md) | Operating constitution, vault rules, AI behaviour |
| [`hooks/hooks.json`](./hooks/hooks.json) | Hook wiring for the session lifecycle |
| [`hooks/pre-commit`](./hooks/pre-commit) | Pre-commit guard (blocks vault artifacts and debug files) |
| [`scripts/`](./scripts) | Shell and Python utilities — harvest, distill, session capture, validation |
| [`agents/`](./agents) | System-prompt files for `claude -p` sub-processes |
| [`commands/`](./commands) | Slash commands: `/status`, `/logs`, `/distill`, `/promote`, `/note` |
| [`skills/`](./skills) | Domain helpers for Obsidian workflows |
| [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) | Plugin manifest |
| [`settings.json.example`](./settings.json.example) | Environment variable template |

## Getting started

### Prerequisites

- macOS or Linux
- Claude Code with local plugin support
- `jq` and `python3` on your `PATH`
- An Obsidian vault ([`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault) structure recommended)

### 1. Clone

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
```

### 2. Run init

```bash
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

`init.sh` will:

1. Verify `jq` and `python3`
2. Write `SECOND_BRAIN_VAULT_PATH` to `.claude/settings.local.json` and patch `CLAUDE.md`
3. Fix script permissions (`chmod +x`)
4. Install the pre-commit hook symlink (`.git/hooks/pre-commit → hooks/pre-commit`)
5. Register hooks and `CLAUDE_PLUGIN_ROOT` into `.claude/settings.local.json` (Plugin hooks install)
6. Validate `hooks/hooks.json`
7. Check expected vault folders and structure
8. Sync starter templates into `Templates/`

### 3. Open in Claude Code

Open this directory as your Claude Code project. The hooks fire automatically from the first session.

## Configuration

Environment variables are read from `.claude/settings.local.json` (machine-local, never committed):

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECOND_BRAIN_VAULT_PATH` | Absolute path to your Obsidian vault | required |
| `SECOND_BRAIN_DAILY_DIR` | Daily notes folder | `Daily` |
| `SECOND_BRAIN_SESSION_DIR` | AI session log folder | `Meta/AI Sessions` |
| `SECOND_BRAIN_CAPTURE_STRICT` | `1` = hook failures are hard errors instead of fail-open | `0` |

## Note lifecycle

```
Ideas/           — auto-sketches, harvest_promoted: false  (low score, unreviewed)
Meta/Promotions/ — staged drafts waiting for human review  (reviewed_status: false)
References/      — promoted, gate-cleared concept notes
Projects/        — manual only, no auto-write
```

Run `/promote` inside Claude Code to move approved drafts from `Meta/Promotions/` to their target.

## Vault output (defaults)

```
Daily/YYYY-MM-DD.md           — session summary appended under ## AI Session
Meta/AI Sessions/YYYY-MM-DD/  — raw session log per session-id
Meta/Promotions/draft-*.md    — auto-generated note drafts awaiting review
Ideas/                        — low-threshold auto-promoted ideas
References/                   — high-confidence concept stubs
Weekly/YYYY-Www.md            — created automatically at SessionEnd
Monthly/YYYY-MM.md            — created automatically at SessionEnd
```

## Where to get help

- [`CLAUDE.md`](./CLAUDE.md) — vault conventions, AI rules, safety defaults
- [`commands/status.md`](./commands/status.md) — quick operational review from inside Claude Code
- [`commands/logs.md`](./commands/logs.md) — recent failures and log guidance
- [`README.ja.md`](./README.ja.md) — Japanese overview

If something looks wrong, open an issue with your setup steps and the output of `./scripts/init.sh`.

## Maintainers and contributions

Maintained by **masudaso**.

Contributions are welcome through issues and pull requests. Please keep changes:

- small and reversible
- aligned with the rules in [`CLAUDE.md`](./CLAUDE.md)
- safe for user vaults and secret material
- documented when they change operator behaviour or setup steps

## License

Released under the **MIT License**. See [`LICENSE`](./LICENSE) for details.
