#!/bin/bash
# init.sh — Connect Claude Code and Obsidian to the second-brain tooling.
#
# What this does:
#   1. Check required dependencies (jq, python3)
#   2. Fix script permissions (chmod +x)
#   3. Validate vault path and directory structure
#   4. Sync Templates/ to the vault (idempotent — skips existing files)
#   5. Print a status summary with pass/fail for each check

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

# ── 2. CLAUDE_PLUGIN_ROOT in settings.json ────────────────────────────────────

echo "-- CLAUDE_PLUGIN_ROOT"

SETTINGS_FILE="$REPO_ROOT/settings.json"
if [[ ! -f "$SETTINGS_FILE" ]]; then
  fail "settings.json not found — creating with CLAUDE_PLUGIN_ROOT"
  printf '{\n    "env": {\n        "CLAUDE_PLUGIN_ROOT": "%s"\n    }\n}\n' "$REPO_ROOT" > "$SETTINGS_FILE"
else
  CURRENT_ROOT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$SETTINGS_FILE'))
    print(d.get('env', {}).get('CLAUDE_PLUGIN_ROOT', ''))
except Exception:
    pass
" 2>/dev/null || true)

  if [[ "$CURRENT_ROOT" == "$REPO_ROOT" ]]; then
    ok "CLAUDE_PLUGIN_ROOT = $REPO_ROOT"
  elif [[ -z "$CURRENT_ROOT" ]]; then
    # Inject CLAUDE_PLUGIN_ROOT into existing settings.json
    python3 - "$SETTINGS_FILE" "$REPO_ROOT" <<'PY'
import json, sys
path, root = sys.argv[1], sys.argv[2]
d = json.load(open(path))
d.setdefault("env", {})["CLAUDE_PLUGIN_ROOT"] = root
with open(path, "w") as f:
    json.dump(d, f, indent=4, ensure_ascii=False)
    f.write("\n")
PY
    ok "CLAUDE_PLUGIN_ROOT injected into settings.json ($REPO_ROOT)"
  else
    warn "CLAUDE_PLUGIN_ROOT is '$CURRENT_ROOT' (expected '$REPO_ROOT') — update settings.json manually if needed"
  fi
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

# Resolve vault path: argument → env var → settings.json → CLAUDE.md
VAULT_PATH="${VAULT_PATH_ARG:-${SECOND_BRAIN_VAULT_PATH:-}}"

if [[ -z "$VAULT_PATH" ]] && [[ -f "$REPO_ROOT/settings.json" ]]; then
  VAULT_PATH=$(python3 -c "
import json, sys
try:
    d = json.load(open('$REPO_ROOT/settings.json'))
    print(d.get('env', {}).get('SECOND_BRAIN_VAULT_PATH', ''))
except Exception:
    pass
" 2>/dev/null || true)
fi

if [[ -z "$VAULT_PATH" ]] && [[ -f "$REPO_ROOT/CLAUDE.md" ]]; then
  VAULT_PATH=$(sed -n 's/^- Location: `\(.*\)`/\1/p' "$REPO_ROOT/CLAUDE.md" | head -n 1)
fi

if [[ -z "$VAULT_PATH" ]]; then
  fail "vault path not found — set SECOND_BRAIN_VAULT_PATH in settings.json"
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
