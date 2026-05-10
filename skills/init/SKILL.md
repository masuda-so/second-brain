# second-brain:init

Connect Claude Code and Obsidian to the second-brain tooling. Run once after cloning, or any time the setup may have drifted.

## Usage

```
/second-brain:init [vault-path]
```

`vault-path` is optional. When provided it overrides the path in `settings.json` and `CLAUDE.md`.

## What it does

Run `scripts/init.sh [vault-path]` from the repository root and report the output.

The script performs these checks in order:

1. **Dependencies** — verifies `jq` and `python3` are installed
2. **Script permissions** — `chmod +x` any scripts missing executable bits
3. **Hooks** — validates `hooks/hooks.json` is well-formed JSON
4. **Vault path** — resolves from `SECOND_BRAIN_VAULT_PATH` env → `settings.json` → `CLAUDE.md`
5. **Vault structure** — confirms required directories exist (`Daily/`, `Ideas/`, `References/`, etc.)
6. **Templates sync** — writes template files to vault's `Templates/` directory (idempotent — skips existing files)

## After running

If all checks pass, complete the Obsidian side manually:

1. Open Obsidian → Settings → Core plugins → enable **Templates**, **Daily notes**, **Bases**
2. Templates plugin: set folder location to `Templates`
3. Daily notes plugin: set date format to `YYYY-MM-DD`, folder to `Daily`
4. Start a new Claude Code session — hooks fire automatically from that point on
