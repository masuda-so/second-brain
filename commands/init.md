---
description: Connect Claude Code and Obsidian to the second-brain tooling. Run once after cloning, or any time the setup may have drifted. Accepts an optional vault path argument to override the configured path.
---

Run `scripts/init.sh $ARGUMENTS` from the repository root and report the output.

If `$ARGUMENTS` contains a path, it is passed as the vault path override.

The script performs these checks in order:
1. Dependencies — jq, python3
2. Script permissions — chmod +x any missing executable bits
3. Hooks — validates hooks/hooks.json is well-formed
4. Vault path — resolves from SECOND_BRAIN_VAULT_PATH → settings.json → CLAUDE.md
5. Vault structure — confirms required directories exist
6. Templates sync — writes template files to vault's Templates/ (idempotent, skips existing)

After running, report:
- which checks passed and which failed
- any manual steps required (Obsidian plugin settings)
- whether the system is ready to use
