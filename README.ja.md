[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Status: Early Access](https://img.shields.io/badge/status-early%20access-blue.svg)](#)

[English README](./README.md)

# second-brain

`second-brain` は、Obsidian ベースの Knowledge OS を Claude Code から安全に運用するためのローカルプラグイン用リポジトリです。ライブセッション記録、軽量なガードレール、運用向けの再利用可能なワークフローをまとめ、Claude Code の作業内容を vault に継続的に残せます。

> このリポジトリは **制御レイヤー** です。長期記憶そのものは Obsidian vault 側にあります。

## このプロジェクトでできること

- `Daily/YYYY-MM-DD.md` と `Meta/AI Sessions/YYYY-MM-DD/<session-id>.md` への**ライブ記録**
- 保護ファイルや書き込み系 SQL を防ぐ**安全ガード**
- `json` / `sh` / `py` 編集後の**軽量バリデーション**
- `Template-Vault` と相性のよい**既定フォルダ構成**
- `commands/`・`agents/`・`skills/` による**運用支援ツール**

## 使い始め方

### 前提条件

- macOS または Linux
- ローカルプラグインを使える Claude Code
- `jq` と `python3`
- Obsidian vault（`Template-Vault` 系構成を推奨）

### セットアップ

```bash
git clone https://github.com/masuda-so/second-brain.git
cd second-brain
cp settings.json.example settings.json
./scripts/init.sh "/path/to/your/Obsidian Vault"
```

`settings.json` では次の環境変数を使います。

| 変数 | 用途 | 既定値 |
| --- | --- | --- |
| `SECOND_BRAIN_VAULT_PATH` | Obsidian vault の絶対パス | 必須 |
| `SECOND_BRAIN_DAILY_DIR` | Daily ノートの保存先 | `Daily` |
| `SECOND_BRAIN_SESSION_DIR` | AI セッションログの保存先 | `Meta/AI Sessions` |
| `SECOND_BRAIN_CAPTURE_STRICT` | `1` でキャプチャ失敗を fail-open ではなくエラー扱い | `0` |

## 主なファイル

| パス | 役割 |
| --- | --- |
| [`CLAUDE.md`](./CLAUDE.md) | 運用ルールと vault 規約 |
| [`hooks/hooks.json`](./hooks/hooks.json) | フック設定 |
| [`scripts/`](./scripts) | 初期化・検証・記録用スクリプト |
| [`commands/status.md`](./commands/status.md) | 状態確認用プロンプト |
| [`commands/logs.md`](./commands/logs.md) | ログ確認用プロンプト |

## ヘルプ

まずは以下を参照してください。

- [`README.md`](./README.md)
- [`CLAUDE.md`](./CLAUDE.md)
- [`commands/status.md`](./commands/status.md)
- [`commands/logs.md`](./commands/logs.md)

## メンテナーと貢献

メンテナーは **masudaso** です。Issue と Pull Request を歓迎します。変更は小さく安全に保ち、ユーザーの vault を壊さないことを優先してください。

## ライセンス

**MIT License** — 詳細は [`LICENSE`](./LICENSE) を参照してください。
