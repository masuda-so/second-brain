# second-brain

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)
[![Version: 0.2.0](https://img.shields.io/badge/version-0.2.0-lightgrey.svg)](#)

[English READMEはこちら](./README.en.md)

## このプロジェクトについて

`second-brain` は、Claude Code と Obsidian vault を統合した Knowledge OS の制御レイヤーです。
Claude Code セッションの活動を自動的に取り込み、構造化された Obsidian ノートを生成します。

## できること

- Claude Code のセッションライフサイクル（開始・プロンプト・ツール実行・編集・終了）を hook で捕捉
- プロンプト・ツール・編集結果のセッションログを vault に反映
- 破壊的操作をブロックする検証スクリプト(`PreToolUse`/`PostToolUse` ガード)
- `Meta/AI Sessions` へのセッション記録と日次・週次・月次ノートの自動作成
- `Distill` によるドラフト蒸留と `Meta/Promotions` へのステージング
- `/promote` ワークフローで `References/` 等への安全な昇格
- git pre-commit フックで vault への誤操作を防止

## なぜ作ったか / メリット

- セッション中の思考や判断を log に散らばらせないで、vault に構造化して蓄積できる
- AI の出力を vault の命名規則・フォルダ構成になじませられる
- `guard-files.sh`、`guard-vault-rm.sh`、`on-edit-check.sh` により破壊的操作を防止
- 人間によるレビューを前提とした昇格フローで、edit trust を維持
- `.claude/settings.local.json` に vault パスを集約し、`.gitignore` で privacy を保護

## 使い方

### 動作要件

- macOS または Linux
- ローカルプラグイン対応の Claude Code
- `jq`
- `python3`
- Obsidian vault（対応テンプレート推奨）

### セットアップ

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

`init.sh` は以下を実行します:

- `jq` / `python3` の存在確認
- `.claude/settings.local.json` への `SECOND_BRAIN_VAULT_PATH` 書き込み
- `CLAUDE.md` の vault path patch
- git pre-commit フックのインストール
- `hooks/hooks.json` のローカル設定への登録
- フックの JSON 妥当性チェック
- テンプレートの vault への同期

### Claude Code での起動

このリポジトリを Claude Code プロジェクトとして開くと、プラグインマニフェストとフックが自動的に認識されます。

### ビルトインコマンド

- `/status` — プラグインの状態と健全性
- `/logs` — 直近の hook / スクリプト出力
- `/promote` — `Meta/Promotions/` のドラフトを昇格

## ディレクトリ構成

| パス | 役割 |
|------|-------|
| [`hooks/hooks.json`](./hooks/hooks.json) | Claude Code フックの登録 |
| [`hooks/pre-commit`](./hooks/pre-commit) | コミット前に vault の安全性を検査 |
| [`scripts/init.sh`](./scripts/init.sh) | セットアップと検証 |
| [`scripts/harvest.py`](./scripts/harvest.py) | セッション成果物の収集 |
| [`scripts/distill.py`](./scripts/distill.py) | 要約・ノートへの蒸留 |
| [`scripts/distill-draft.py`](./scripts/distill-draft.py) | ドラフト生成 |
| [`scripts/promote.py`](./scripts/promote.py) | 承認済みドラフトの昇格 |
| [`scripts/guard-files.sh`](./scripts/guard-files.sh) | ファイル操作のガード |
| [`scripts/guard-vault-rm.sh`](./scripts/guard-vault-rm.sh) | vault 削除操作の防止 |
| [`scripts/on-edit-check.sh`](./scripts/on-edit-check.sh) | 編集検証フック |
| [`commands/`](./commands) | `/status`, `/logs`, `/promote` 等のエントリポイント |
| [`agents/`](./agents) | セッション要約、セキュリティレビュー、パフォーマンステスト等 |
| [`skills/`](./skills) | ドラフト蒸留、defuddle、Markdown 変換、Bases 操作等 |
| [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) | フック・スクリプトの CI |
| [`pyproject.toml`](./pyproject.toml) | pytest 設定 |
| [`CLAUDE.md`](./CLAUDE.md) | vault 運用ルールと AI の行動規範 |

## ノートのライフサイクル

- `Ideas/` — スコア低めの自動草案
- `Meta/Promotions/` — 人間レビュー待ちのドラフト
- `References/` — 昇格済みの高信頼度ナレッジ
- `Projects/` — 手動管理のプロジェクトノート
- `Clippings/` — 未処理の取り込み素材

## テスト

```bash
# 依存の導入（必要な場合）
brew install jq

# 初期化検証
bash scripts/init.sh "/path/to/tmp/vault"

# Python ユニットテスト（pytest 使用を想定）
python3 -m pytest scripts/tests/
```

## ヘルプ

- [CLAUDE.md](./CLAUDE.md) — vault の運用ルール
- [commands/status.md](./commands/status.md) — `/status` の詳細
- [commands/logs.md](./commands/logs.md) — `/logs` の詳細
- issue — セットアップ手歴と `./scripts/init.sh` の出力を添えて

## メンテナー・貢献

メンテナー: **masudaso**

Pull Request / Issue を歓迎します。
変更は小さく可逆的に、`CLAUDE.md` に整合させ、ユーザー vault を破壊しないでください。

## ライセンス

[LICENSE](./LICENSE) を参照してください。
