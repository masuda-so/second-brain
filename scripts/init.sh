#!/bin/bash
# init.sh — Connect Claude Code and Obsidian to the second-brain tooling.
#
# What this does:
#   1. Check required dependencies (jq, python3)
#   2. Create settings.json from example if missing (SECOND_BRAIN_VAULT_PATH only)
#   3. Fix script permissions (chmod +x)
#   4. Validate hooks config
#   5. Validate vault path and directory structure
#   6. Sync Templates/ to the vault (idempotent — skips existing files)
#   7. Print a status summary with pass/fail for each check
#
# Note: CLAUDE_PLUGIN_ROOT is auto-provided by the Claude Code plugin system.
# Only SECOND_BRAIN_VAULT_PATH needs user configuration.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Optional: vault path override from first argument
VAULT_PATH_ARG="${1:-}"

PASS="[ok]"
FAIL="[fail]"
SKIP="[skip]"
WARN="[warn]"

errors=0

log()  { printf '%s %s\n' "$1" "$2"; }
ok()   { log "$PASS" "$1"; }
fail() { log "$FAIL" "$1"; errors=$((errors + 1)); }
warn() { log "$WARN" "$1"; }
skip() { log "$SKIP" "$1"; }

echo ""
echo "=== second-brain init ==="
echo ""

# ── 1. Dependencies ────────────────────────────────────────────────────────────

echo "-- Dependencies"

if command -v jq >/dev/null 2>&1; then
  ok "jq $(jq --version)"
else
  fail "jq not found — install via: brew install jq"
fi

if command -v python3 >/dev/null 2>&1; then
  ok "python3 $(python3 --version 2>&1)"
else
  fail "python3 not found"
fi

echo ""

# ── 2. .claude/settings.local.json — canonical vault path config ──────────────
#
# Canonical location for SECOND_BRAIN_VAULT_PATH is .claude/settings.local.json
# (machine-specific / user-local, never committed).
# repo-root settings.json is kept as a legacy fallback for now.

echo "-- .claude/settings.local.json"

LOCAL_SETTINGS="$REPO_ROOT/.claude/settings.local.json"
PLACEHOLDER="/path/to/your/obsidian/vault"

_set_vault_path_in_settings() {
  local path="$1" vault="$2"
  python3 - "$path" "$vault" <<'PY'
import json, sys, pathlib
path, vault = sys.argv[1], sys.argv[2]
p = pathlib.Path(path)
try:
    d = json.loads(p.read_text()) if p.exists() else {}
except Exception:
    d = {}
d.setdefault("env", {})["SECOND_BRAIN_VAULT_PATH"] = vault
p.parent.mkdir(parents=True, exist_ok=True)
with open(path, "w") as f:
    json.dump(d, f, indent=4, ensure_ascii=False)
    f.write("\n")
PY
}

_read_vault_path_from_settings() {
  local path="$1"
  python3 -c "
import json, sys
try:
    d = json.load(open('$path'))
    print(d.get('env', {}).get('SECOND_BRAIN_VAULT_PATH', ''))
except Exception:
    pass
" 2>/dev/null || true
}

CURRENT_VAULT=$(_read_vault_path_from_settings "$LOCAL_SETTINGS")

if [[ -z "$CURRENT_VAULT" || "$CURRENT_VAULT" == "$PLACEHOLDER" ]]; then
  if [[ -n "$VAULT_PATH_ARG" ]]; then
    _set_vault_path_in_settings "$LOCAL_SETTINGS" "$VAULT_PATH_ARG"
    ok "SECOND_BRAIN_VAULT_PATH set to: $VAULT_PATH_ARG"
  else
    fail "SECOND_BRAIN_VAULT_PATH not configured — run: second-brain:init /your/vault/path"
  fi
else
  ok "SECOND_BRAIN_VAULT_PATH = $CURRENT_VAULT"
fi

echo ""

# ── 3. Script permissions ──────────────────────────────────────────────────────

echo "-- Script permissions"

fixed=0
for f in "$REPO_ROOT/scripts/"*.sh "$REPO_ROOT/scripts/"*.py; do
  [[ -f "$f" ]] || continue
  if [[ ! -x "$f" ]]; then
    chmod +x "$f"
    ok "chmod +x $(basename "$f")"
    fixed=$((fixed + 1))
  fi
done

if [[ $fixed -eq 0 ]]; then
  ok "all scripts already executable"
fi

echo ""

# ── 3. Hooks config ────────────────────────────────────────────────────────────

echo "-- Hooks"

HOOKS_FILE="$REPO_ROOT/hooks/hooks.json"
if [[ -f "$HOOKS_FILE" ]]; then
  if jq empty "$HOOKS_FILE" 2>/dev/null; then
    hook_count=$(jq '[.hooks | to_entries[] | .value[] | .hooks[]] | length' "$HOOKS_FILE" 2>/dev/null || echo "?")
    ok "hooks/hooks.json valid ($hook_count hooks)"
  else
    fail "hooks/hooks.json is not valid JSON"
  fi
else
  fail "hooks/hooks.json not found"
fi

echo ""

# ── 4. Vault path ──────────────────────────────────────────────────────────────

echo "-- Vault"

# Resolve vault path: argument → env var → .claude/settings.local.json → settings.json (legacy) → CLAUDE.md
VAULT_PATH="${VAULT_PATH_ARG:-${SECOND_BRAIN_VAULT_PATH:-}}"

if [[ -z "$VAULT_PATH" ]] && [[ -f "$LOCAL_SETTINGS" ]]; then
  VAULT_PATH=$(_read_vault_path_from_settings "$LOCAL_SETTINGS")
fi

if [[ -z "$VAULT_PATH" ]] && [[ -f "$REPO_ROOT/settings.json" ]]; then
  VAULT_PATH=$(_read_vault_path_from_settings "$REPO_ROOT/settings.json")
fi

if [[ -z "$VAULT_PATH" ]] && [[ -f "$REPO_ROOT/CLAUDE.md" ]]; then
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" | head -n 1)
fi

if [[ -z "$VAULT_PATH" ]]; then
  fail "vault path not found — set SECOND_BRAIN_VAULT_PATH in .claude/settings.local.json"
  echo ""
  echo "=== Result: $errors error(s) ==="
  exit 1
fi

VAULT_PATH="${VAULT_PATH%/}"

if [[ -d "$VAULT_PATH" ]]; then
  ok "vault found: $VAULT_PATH"
else
  fail "vault directory does not exist: $VAULT_PATH"
  echo ""
  echo "=== Result: $errors error(s) ==="
  exit 1
fi

echo ""

# ── 5. Vault directory structure ───────────────────────────────────────────────

echo "-- Vault structure"

REQUIRED_DIRS=(Daily Weekly Monthly Projects Ideas References Clippings Meta Bases)

for d in "${REQUIRED_DIRS[@]}"; do
  if [[ -d "$VAULT_PATH/$d" ]]; then
    ok "$d/"
  else
    warn "$d/ missing — will be created on first use by hooks"
  fi
done

echo ""

# ── 6. Sync Templates/ to vault ────────────────────────────────────────────────

echo "-- Templates sync"

VAULT_TEMPLATES="$VAULT_PATH/Templates"
mkdir -p "$VAULT_TEMPLATES"

synced=0
skipped=0

sync_template() {
  local fname="$1"
  local target="$VAULT_TEMPLATES/$fname"
  if [[ -f "$target" ]]; then
    skip "$fname (already exists)"
    skipped=$((skipped + 1))
  else
    # Content is passed via stdin
    cat > "$target"
    ok "created Templates/$fname"
    synced=$((synced + 1))
  fi
}

sync_template "daily.md" <<'TMPL'
---
type: daily
date: {{date:YYYY-MM-DD}}
tags:
  - journal
---
## 今日のフォーカス

## メモ

> [!note] 振り返り

## フォローアップ

- [ ]

## 関連ノート

## AI Session
TMPL

sync_template "weekly.md" <<'TMPL'
---
type: weekly
week: {{date:YYYY-[W]WW}}
reviewed: {{date:YYYY-MM-DD}}
tags:
  - planning
  - review
---
## 進行中プロジェクト

## 昇格候補アイデア

## ブロッカー

> [!tip] 週次の要約
> 重要度の高い項目だけ Projects に昇格し、残りは保留または整理する。

## 来週の重点

## 関連ノート
TMPL

sync_template "monthly.md" <<'TMPL'
---
type: monthly
period: {{date:YYYY-MM}}
tags:
  - monthly
  - strategy
---
## 優先事項

## うまくいったこと

## 改善点

> [!important] 月次判断
> 実行可能な項目は Projects に移し、原則は References に残す。

## 来月の焦点

## 関連ノート
TMPL

sync_template "project.md" <<'TMPL'
---
type: project
status: active
review: {{date:YYYY-MM-DD}}
tags: []
---
## ゴール

## 次のアクション

- [ ]

## 添付

## 関連ノート
TMPL

sync_template "idea.md" <<'TMPL'
---
type: idea
status: incubating
created: {{date:YYYY-MM-DD}}
tags: []
---
## プロジェクト化の条件

- 今月実装したい
- 複数ステップが必要
- 他フォルダへ影響がある

> [!note] 次の扱い

## 下書き素材
TMPL

sync_template "reference.md" <<'TMPL'
---
type: reference
topic:
---
## 目的

## 手順

> [!important] 再利用ルール

## 関連資料
TMPL

sync_template "clipping.md" <<'TMPL'
---
type: clipping
source:
captured: {{date:YYYY-MM-DD}}
---
## メモ

-
TMPL

echo ""
echo "-- Summary"
echo "   Templates synced: $synced, skipped: $skipped"
echo ""

# ── 7. Vault CI (opt-in only: set SECOND_BRAIN_INSTALL_VAULT_CI=1 or pass --install-vault-ci) ──

echo "-- Vault CI"

INSTALL_VAULT_CI="${SECOND_BRAIN_INSTALL_VAULT_CI:-0}"
for _arg in "$@"; do
  [[ "$_arg" == "--install-vault-ci" ]] && INSTALL_VAULT_CI=1
done

VAULT_WORKFLOWS="$VAULT_PATH/.github/workflows"
EXAMPLE_CI="$REPO_ROOT/docs/examples/vault-ci.yml"
VAULT_CI_TARGET="$VAULT_WORKFLOWS/vault-ci.yml"

if [[ "$INSTALL_VAULT_CI" != "1" ]]; then
  skip "vault CI not requested — pass --install-vault-ci or set SECOND_BRAIN_INSTALL_VAULT_CI=1 to opt in"
elif ! git -C "$VAULT_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  skip "vault is not a git repo — skipping vault CI setup"
elif [[ ! -f "$EXAMPLE_CI" ]]; then
  warn "docs/examples/vault-ci.yml not found — skipping vault CI setup"
elif [[ -f "$VAULT_CI_TARGET" ]]; then
  skip "vault-ci.yml already exists in vault repo"
else
  mkdir -p "$VAULT_WORKFLOWS"
  cp "$EXAMPLE_CI" "$VAULT_CI_TARGET"
  ok "created .github/workflows/vault-ci.yml in vault repo"
  warn "Review $VAULT_CI_TARGET before committing to your vault repo"
fi

echo ""

# ── Result ─────────────────────────────────────────────────────────────────────

if [[ $errors -eq 0 ]]; then
  echo "=== Result: all checks passed ==="
  echo ""
  echo "Next steps:"
  echo "  1. Open Obsidian → Settings → Core plugins → enable Templates, Daily notes, Bases"
  echo "  2. Templates plugin: set folder location to 'Templates'"
  echo "  3. Daily notes plugin: set date format to 'YYYY-MM-DD', folder to 'Daily'"
  echo "  4. Start a new Claude Code session in this directory — hooks will fire automatically"
else
  echo "=== Result: $errors error(s) — fix the above before using second-brain ==="
  exit 1
fi
