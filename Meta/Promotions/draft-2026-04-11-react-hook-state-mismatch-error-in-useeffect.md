---
title: React hook state mismatch error in useEffect
type: reference
topic: hooks
generated: true
reviewed_status: false
source_session: test-ai
source_date: 2026-04-11
promotion_target: References/react-hook-error.md
promotion_action: create
tags: []
---
## 目的

`useEffect` 内で React フックの state が期待値と一致しないエラーが発生した際の原因特定と修正に使う。クロージャの古い参照や依存配列の設定ミスが原因であることが多く、デバッグ時の最初の手がかりとして参照する。

## 手順

- **原因の確認**: `useEffect` 内の state 参照がクロージャにキャプチャされた古い値を参照している可能性がある。`console.log` でエフェクト実行時の実際の値を出力して確認する
- **依存配列の見直し**: `useEffect` の第2引数に参照している state・props・関数をすべて列挙する。ESLint の `exhaustive-deps` ルールを有効にすると漏れを自動検出できる
- **関数を依存配列に含める場合**: エフェクト内で呼び出す関数は `useCallback` でメモ化し、その関数を依存配列に追加する。そうしないと毎レンダーで関数が再生成されエフェクトが無限ループする
- **非同期処理との組み合わせ**: `useEffect` 内の非同期関数がアンマウント後に state を更新しようとすると "Can't perform a state update on an unmounted component" が発生する。クリーンアップ関数でフラグ変数 (`let isMounted = true`) を管理し、更新前に確認する
- **完了確認**: 修正後に React DevTools の Profiler でエフェクトの発火タイミングを確認し、想定外の再実行がないことを検証する

## 関連資料

