[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)
[![Version: 0.2.0](https://img.shields.io/badge/version-0.2.0-lightgrey.svg)](#)

[English README](./README.md)

# second-brain

Obsidian vault を自律的な Knowledge OS に変える Claude Code ローカルプラグインです。
このリポジトリは制御レイヤーとして機能し、セッションキャプチャ、ガードレール、構造化ドラフト、昇格ワークフローを提供します。

## このプロジェクトが提供するもの

`second-brain` は Claude Code セッションの活動を取り込み、Obsidian ノートを構造化して自動生成します。
次の機能を管理します。

- Claude Code のセッションライフサイクルイベント用フック
- ワークフロー制御用のローカルプラグインコマンドとエージェント
- vault を保護するガードスクリプト
- `Ideas/`, `Meta/Promotions/`, `References/` への段階的なドラフト昇格

Obsidian vault は長期記憶として残り、このリポジトリがノートの取り込み、レビュー、昇格をオーケストレーションします。

## なぜ便利か

- Claude Code セッションからの知識キャプチャを摩擦なく実現
- AI 生成コンテンツを構造化 vault ルールに揃える
- 破壊的なシェル/ファイル操作の誤実行を防止
- 日次、週次、月次、セッション要約の自動化
- 最終保存前にドラフトのレビューを明示化

## 主要な機能

- `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd` 用のフック配線
- `scripts/session-memory.sh` によるプロンプト・ツールキャプチャ
- `scripts/harvest.py` のキュー/ワーカー/フラッシュパイプライン
- `scripts/distill.py`/`scripts/distill-draft.py` によるドラフト蒸留
- `scripts/promote.py` による昇格ワークフロー
- `scripts/` 以下の vault 保護用ガードレールスクリプト
- Claude Code 用プラグインマニフェスト、エージェントプロンプト、コマンド、スキル

## はじめに

### 前提条件

- macOS または Linux
- ローカルプラグイン対応の Claude Code
- `jq` がインストールされていること
- `python3` が `PATH` 上にあること
- 互換性のある Obsidian vault

### 1. リポジトリをクローン

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
```

### 2. vault パスを設定

次のコマンドを実行します。

```bash
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

このセットアップでは次を行います。

- `jq` と `python3` を検証
- `SECOND_BRAIN_VAULT_PATH` を `.claude/settings.local.json` に書き込み
- `CLAUDE.md` を vault パスでパッチ
- git pre-commit フックをインストール
- ローカル設定にプラグインフックを登録
- フックの配線と vault 構成を検証
- `Templates/` にスターターテンプレートを同期

### 3. Claude Code で開く

このリポジトリを Claude Code プロジェクトとして開きます。
プラグインマニフェストやフック、コマンド、スキルが自動的に検出されます。

### 4. ビルトインコマンドを使う

Claude Code 内で次のコマンドを使います。

- `/status` — プラグイン状態とセッションの健康を確認
- `/logs` — 最近のフックとスクリプト出力を確認
- `/promote` — `Meta/Promotions/` の承認済みドラフトを移動

## リポジトリ構造

| パス | 役割 |
|------|------|
| [`CLAUDE.md`](./CLAUDE.md) | 運用ルール、vault 規約、AI 振る舞い |
| [`hooks/hooks.json`](./hooks/hooks.json) | セッションフックの配線 |
| [`hooks/pre-commit`](./hooks/pre-commit) | vault 安全のための Git ガードフック |
| [`scripts/`](./scripts) | 主要なシェルおよび Python ユーティリティ |
| [`agents/`](./agents) | Claude エージェントプロンプト |
| [`commands/`](./commands) | オペレーターコマンドのドキュメント |
| [`skills/`](./skills) | Obsidian ワークフロー向けヘルパースキル |
| [`.claude-plugin/plugin.json`](./.claude-plugin/plugin.json) | Claude Code プラグインマニフェスト |
| [`settings.json.example`](./settings.json.example) | 環境設定の例 |

## 仕組み

セッションライフサイクルのフックがプロンプト、ツール、編集をキャプチャし、構造化ドラフトを生成します。

- `SessionStart` はセッションコンテキスト、日次/週次ノートを初期化し、キャプチャを開始
- `UserPromptSubmit` はプロンプトを記録し、ハーベストコンテンツをキューへ追加
- `PreToolUse` は安全でないファイル・シェル操作をブロック
- `PostToolUse` は編集を検証し、ツール出力をキャプチャ
- `Stop` はハーベストワーカーを実行
- `SessionEnd` はキューをフラッシュし、セッションノートを蒸留

## ノートライフサイクル

- `Ideas/` — 低スコアの自動スケッチ
- `Meta/Promotions/` — 人間のレビュー待ちドラフト
- `References/` — 高確度の昇格済みコンテンツ
- `Projects/` — 手動のみのプロジェクトノート

## 設定

ローカル設定は `.claude/settings.local.json` に保存します。主な環境変数:

- `SECOND_BRAIN_VAULT_PATH` — 必須の絶対 vault パス
- `SECOND_BRAIN_DAILY_DIR` — 既定は `Daily`
- `SECOND_BRAIN_SESSION_DIR` — 既定は `Meta/AI Sessions`
- `SECOND_BRAIN_CAPTURE_STRICT` — `1` にするとフック失敗がエラー扱い

## ヘルプとドキュメント

- [`CLAUDE.md`](./CLAUDE.md) — 運用ガイドと vault ルール
- [`commands/status.md`](./commands/status.md) — ステータスコマンドのリファレンス
- [`commands/logs.md`](./commands/logs.md) — ログトラブルシュートのリファレンス
- [`README.md`](./README.md) — 英語版

問題がある場合は、セットアップ手順と `./scripts/init.sh` の出力を添えて Issue を作成してください。

## メンテナーと貢献

メンテナーは **masudaso** です。
Issue と Pull Request を歓迎します。変更は次の条件を満たすようにしてください。

- 小さくて可逆的
- ユーザー vault に安全
- `CLAUDE.md` のルールに沿っている
- セットアップやオペレーター動作に影響する場合はドキュメント化されている

## ライセンス

**MIT License** です。詳細は [`LICENSE`](./LICENSE) を参照してください。
