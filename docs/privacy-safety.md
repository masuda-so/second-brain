# Privacy and Safety Notes

> This document is an engineering compliance checklist, not legal advice.
> Before public release, paid distribution, user-data collection, or production operation, confirm the final position with a qualified professional.


## Scope

second-brain captures Claude Code session events, prompts, tool activity, edits, and distilled notes into an Obsidian vault. That makes it useful, but also unusually good at recording things users did not intend to publish.

## Main Risks

- Prompts may include personal information, credentials, private business plans, or third-party data.
- Tool logs may include file paths, repository names, commands, URLs, and error output.
- Generated notes may be committed to a public repository if the vault is not separated from public content.

## Required Defaults

- Keep raw session logs out of public repositories.
- Add `.gitignore` coverage for local settings, raw logs, and generated session directories unless the user intentionally opts in.
- Warn users before connecting the tool to a vault that is public or synced to a public repo.
- Never treat this tool as a compliance archive or legal record.

## Checklist

- [ ] README warns against recording secrets and personal data.
- [ ] Default setup separates private vault output from public template repositories.
- [ ] Local settings are ignored.
- [ ] Raw session logs are not committed by default.
- [ ] Redaction guidance exists for promoted notes.
