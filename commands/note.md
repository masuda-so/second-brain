---
description: vault に新しいノートを生成する。タイプ（daily/weekly/monthly/project/idea/reference/clipping）と任意のタイトルを引数に取り、適切な frontmatter・セクション構造・内容の草案を生成してから書き込む。
---

vault に新しいノートを生成する。

## 引数の解釈

`$ARGUMENTS` を次のように解析する：

```
/note <type> [title-or-slug]

例:
  /note daily                        → Daily/2026-04-08.md
  /note weekly                       → Weekly/2026-W15.md
  /note project second-brain         → Projects/second-brain.md
  /note idea "新しい機能のアイデア"   → Ideas/新しい機能のアイデア.md
  /note reference "組織化の定義"      → References/組織化の定義.md
  /note clipping                     → Clippings/YYYY-MM-DD.md
```

タイプが省略された場合は `daily` とみなす。

## 手順

1. **既存ノートを確認する**
   - 同じパスのノートが存在すれば、上書きせず「すでに存在します」と報告して終了する
   - `daily` / `weekly` / `monthly` は日付ベースのパスを自動計算する

2. **関連ノートを読む**（内容生成の文脈として）
   - `project` → 関連する既存プロジェクトノートと前週のノート
   - `daily` → 前日の Daily ノート（`## フォローアップ` セクション）と `status: active` のプロジェクト
   - `weekly` → 今週の Daily ノート群と前週の Weekly ノート
   - `idea` / `reference` / `clipping` → 関連する既存ノートを検索して重複確認

3. **草案をチャットに出力する**（書き込み前に必ず提示する）
   - CLAUDE.md の「Note Templates」セクションに定義されたフォーマットに従う
   - frontmatter（`title`・`type`・`tags` 等）を完全に記入する
   - 各セクションに文脈に即した内容を生成する
   - 空白のまま残すべきセクションは `<!-- ユーザーが記入 -->` と明示する

4. **承認を得てから書き込む**
   - ユーザーが承認したらファイルを作成する
   - 作成後、Daily ノートの `## 関連ノート` にリンクを追記する（`daily` タイプ自身を作る場合は除く）

## ノートタイプ別のルール

| タイプ | 保存先 | ファイル名形式 |
|--------|--------|---------------|
| `daily` | `Daily/` | `YYYY-MM-DD.md` |
| `weekly` | `Weekly/` | `YYYY-Www.md` |
| `monthly` | `Monthly/` | `YYYY-MM.md` |
| `project` | `Projects/` | `<slug>.md` |
| `idea` | `Ideas/` | `<slug>.md` |
| `reference` | `References/` | `<slug>.md` |
| `clipping` | `Clippings/` | `<slug-or-date>.md` |

## 制約

- 既存ノートを上書きしない
- `## AI Session` セクションには触れない
- frontmatter の `title:` は必ず含める（Obsidian Skills 規格）
- callout は `> [!warning]` / `> [!note]` / `> [!tip]` を使う（`> [!important]` は使わない）
