[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)

[English README](./README.md)

# second-brain

`second-brain` は、Obsidian vault を自律的な Knowledge OS に変える Claude Code ローカルプラグインです。Claude Code で作業するだけでノートが蓄積されます。テンプレート規約に沿った構造化コンテンツが、手動キャプチャなしで自動生成されます。

> このリポジトリは **制御レイヤー** です。長期記憶は Obsidian vault 側にあります。

## 設計原則

| 原則 | 意味 |
|------|------|
| **Zero-friction Capture** | 明示的なメモ取り不要。Claude Code で仕事するだけで vault が育つ |
| **Schema Enforcement** | AI 出力は [`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault) と [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) のテンプレートに沿った内容のみ生成する |
| **Human as a Filter** | 書くのは AI、人間の役割は `Meta/Promotions/` のドラフトを承認・削除するだけ |

## 仕組み

3つのパイプラインが Claude Code セッションの前後で自動的に動きます。

```
Claude Code で作業
      │
      ├─ session-memory.sh (常時稼働) ─→ Meta/AI Sessions/  (生ログ)
      │
      ├─ harvest.py (hook 駆動)
      │    ├─ queue  [UserPromptSubmit / PostToolUse]
      │    ├─ worker [Stop] ──────────→ Ideas/  または  Meta/Promotions/
      │    └─ flush  [SessionEnd] ────→ References/ 自動ドラフト (L3) + Daily リンク
      │
      └─ [SessionEnd] on-end-distill.sh
           ├─ distill.py + distill-draft.py
           │    └─ claude -p ─────────→ Meta/Promotions/  (構造化ドラフト)
           └─ session-summarizer
                └─ claude -p ─────────→ Daily note  ### 要約 (AI)

Meta/Promotions/ → [人間がレビュー] → /promote → References/  または  Ideas/
                                                   (Projects/ は手動のみ)
```

**昇格レベル** (harvest.py):

| レベル | スコア | 自動昇格先 |
|--------|--------|-----------|
| L1 | ≥ 3（短いセッション ≤5 プロンプトは ≥ 2） | `Ideas/` |
| L2 | ≥ 6 | `Meta/Promotions/` |
| L3 | ≥ 9 | `References/` 自動ドラフト + Daily リンク |

## リポジトリ構成

| パス | 役割 |
|------|------|
| [`CLAUDE.md`](./CLAUDE.md) | 運用ルール・vault 規約・AI 動作指針 |
| [`hooks/hooks.json`](./hooks/hooks.json) | セッションライフサイクルのフック設定 |
| [`hooks/pre-commit`](./hooks/pre-commit) | pre-commit ガード（vault アーティファクトやデバッグファイルをブロック） |
| [`scripts/`](./scripts) | harvest・distill・セッション記録・バリデーション用スクリプト群 |
| [`agents/`](./agents) | `claude -p` サブプロセス向けシステムプロンプト定義 |
| [`commands/`](./commands) | スラッシュコマンド: `/status` `/logs` `/distill` `/promote` `/note` |
| [`skills/`](./skills) | Obsidian ワークフロー向けドメインヘルパー |
| [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) | プラグインマニフェスト |
| [`settings.json.example`](./settings.json.example) | 環境変数テンプレート |

## セットアップ

### 前提条件

- macOS または Linux
- ローカルプラグインを使える Claude Code
- `jq` と `python3`
- Obsidian vault（[`masuda-so/Template-Vault`](https://github.com/masuda-so/Template-Vault) 構成を推奨）

### 1. クローン

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
```

### 2. init を実行

```bash
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

`init.sh` が行うこと:

1. `jq` と `python3` の確認
2. `SECOND_BRAIN_VAULT_PATH` を `.claude/settings.local.json` に書き込み、`CLAUDE.md` もパッチ
3. スクリプトに `chmod +x`
4. pre-commit フックのシンリンクを設置（`.git/hooks/pre-commit → hooks/pre-commit`）
5. フックと `CLAUDE_PLUGIN_ROOT` を `.claude/settings.local.json` に登録（Plugin hooks install）
6. `hooks/hooks.json` の検証
7. vault フォルダ構成の確認
8. `Templates/` へのスターターテンプレート同期

### 3. Claude Code で開く

このディレクトリを Claude Code プロジェクトとして開きます。初回セッションからフックが自動で動作します。

## 設定

環境変数は `.claude/settings.local.json`（マシンローカル・非コミット）で管理します。

| 変数 | 用途 | 既定値 |
|------|------|--------|
| `SECOND_BRAIN_VAULT_PATH` | Obsidian vault の絶対パス | 必須 |
| `SECOND_BRAIN_DAILY_DIR` | Daily ノートの保存先 | `Daily` |
| `SECOND_BRAIN_SESSION_DIR` | AI セッションログの保存先 | `Meta/AI Sessions` |
| `SECOND_BRAIN_CAPTURE_STRICT` | `1` でキャプチャ失敗をエラー扱い（既定は fail-open） | `0` |

## ノートのライフサイクル

```
Ideas/           — 自動スケッチ、harvest_promoted: false（低スコア・未レビュー）
Meta/Promotions/ — 人間のレビュー待ちドラフト（reviewed_status: false）
References/      — 承認済みコンセプトノート
Projects/        — 手動のみ（自動書き込み禁止）
```

`Meta/Promotions/` のドラフトを昇格するには Claude Code 内で `/promote` を実行します。

## vault の出力先（既定）

```
Daily/YYYY-MM-DD.md           — ## AI Session にセッション要約が追記される
Meta/AI Sessions/YYYY-MM-DD/  — セッション ID ごとの生ログ
Meta/Promotions/draft-*.md    — レビュー待ちの自動生成ドラフト
Ideas/                        — 低閾値で自動昇格されたアイデア
References/                   — 高確度のコンセプトスタブ
Weekly/YYYY-Www.md            — SessionEnd で自動作成
Monthly/YYYY-MM.md            — SessionEnd で自動作成
```

## ヘルプ

- [`CLAUDE.md`](./CLAUDE.md) — vault 規約・AI ルール・安全デフォルト
- [`commands/status.md`](./commands/status.md) — Claude Code 内からシステム状態を確認
- [`commands/logs.md`](./commands/logs.md) — 最近のエラーとログ確認
- [`README.md`](./README.md) — 英語版

問題が解決しない場合は、セットアップ手順と `./scripts/init.sh` の出力を添えて Issue を作成してください。

## メンテナーと貢献

メンテナーは **masudaso** です。Issue と Pull Request を歓迎します。変更は小さく安全に保ち、ユーザーの vault を壊さないことを優先してください。

## ライセンス

**MIT License** — 詳細は [`LICENSE`](./LICENSE) を参照してください。
