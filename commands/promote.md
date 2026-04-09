---
description: Meta/Promotions/ の draft-*.md を審査し、条件を満たすものを References/ または Ideas/ へ自動昇格する。昇格前に dry-run で候補を提示し、承認を得てから実行する。
---

vault の `Meta/Promotions/` に積み上がった草案を正規の場所へ昇格する。

## 手順

1. **dry-run で候補を確認する**

   ```bash
   python3 $CLAUDE_PLUGIN_ROOT/scripts/promote.py --dry-run
   ```

   出力 JSON の `promoted` 配列に昇格予定のファイルが表示される。
   `skipped` 配列に除外理由が表示される。

2. **候補をチャットに提示する**

   各候補について以下を表示する：
   - `draft` ファイル名
   - `target` 昇格先パス
   - `title` ノートタイトル

   昇格しない方が良いと判断したものがあればユーザーに確認する。

3. **承認後に昇格を実行する**

   ユーザーが承認したら：

   ```bash
   python3 $CLAUDE_PLUGIN_ROOT/scripts/promote.py
   ```

   実行後の `promoted` 配列で昇格されたファイルを確認する。

4. **結果を報告する**

   - 昇格されたノートのリスト（vault リンク形式）
   - Daily `## 関連ノート` への追記確認
   - `skipped` の理由（すでに存在・Projects/ ターゲット等）

## 昇格ルール（自動チェック）

- 昇格先が `References/` または `Ideas/` のみ（`Projects/` は手動 append）
- `promotion_action: create` のみ（`append` は手動）
- 昇格先ファイルが未存在の場合のみ（上書きなし）
- `promoted: true` のものはスキップ（冪等）
- 必須 frontmatter 確認（`title`, `type`, `source_session`）

## 注意

- 昇格後も草案は `Meta/Promotions/` に残る（`promoted: true` に更新）
- 昇格されたノートの `reviewed_status` は `false` のまま — Obsidian で確認が必要
- `Projects/` への追記は手動で行う（`## 追記候補` セクションを参照）
