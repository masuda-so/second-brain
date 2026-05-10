# CLAUDE.md

This repository is the control layer for a personal Knowledge OS built from Claude Code, deterministic hooks, and an Obsidian vault.

## Mission

Treat the user's vault as external memory, not disposable scratch space. The system should help the user think, decide, and retrieve context faster while preserving trust, provenance, and reversibility.

## Cognitive Mapping

- Long-term memory: the Obsidian vault and its durable notes, especially structures such as `Daily/`, `Weekly/`, `Monthly/`, `Projects/`, `References/`, `Clippings/`, `Ideas/`, `Meta/`, `Bases/`, `Canvases/`, and `Sandbox/`.
- Working memory: the current Claude Code context window, active task notes, and any temporary scratch buffers created during a task.
- Executive function: planning, decomposition, task execution, validation, and summarization performed by Claude Code.
- Nervous system: hooks and validation scripts that intercept risky actions before or after tools run.

## Operating Principles

1. Preserve memory before optimizing it.
2. Prefer small, reversible edits over large structural rewrites.
3. Do not invent vault structure. Discover existing conventions first and align to them.
4. Durable knowledge should be distilled, linked, and named clearly enough to be found again.
5. Temporary reasoning belongs in working memory or scratch notes, not in permanent knowledge artifacts unless it remains useful after the session.
6. Hooks must stay deterministic, fast, and easy to audit.
7. Protect secrets, system files, and repository integrity before convenience.
8. Maintain close coordination with Codex and Gemini at all times. Before major decisions, implementation steps, or structural changes, consult the other agents via tmux-bridge. Surface disagreements to the user rather than resolving silently.

## Repository Roles

- `.claude-plugin/plugin.json`: plugin manifest for Claude Code.
- `hooks/hooks.json`: hook wiring for guardrails and post-edit checks.
- `scripts/`: deterministic shell utilities used by hooks.
- `commands/`: reusable operator prompts for health checks and log review.
- `agents/`: specialist agents for review, compliance, debugging, data work, and performance checks.
- `settings.json`: local Claude Code environment flags for this repo.

## Default Workflow

1. Read the user's request and identify whether the target is capture, planning, execution, or knowledge distillation.
2. Inspect the relevant note, project, or operational file before changing it.
3. Use the hook layer to guard writes and validate edited files.
4. Summarize what changed, what remains uncertain, and the next most valuable action.

## Knowledge Hygiene

- Prefer atomic notes over giant catch-all documents.
- Link new knowledge to an existing project, area, or concept whenever possible.
- Distinguish facts, interpretations, and open questions.
- Keep summaries compressed enough to reload quickly into context.

## Safety Defaults

- Never write to `.git/` or obvious secret material.
- Treat destructive database operations as disallowed unless the user explicitly sets up a separate write-capable path.
- If a hook or validation script fails, surface the problem clearly rather than silently proceeding.

## Branch Protection

`main` is protected by a GitHub Ruleset (`protect-main`, ID 14985776).

| Rule | Effect |
|------|--------|
| Require pull request | Direct pushes to `main` are blocked. All changes require a PR. |
| Required status checks (strict) | CI job "Validate hooks, scripts, and init" must pass. Branch must be up-to-date with `main`. |
| Required linear history | Only squash-merge or rebase allowed. No merge commits. |
| Block force pushes | `git push --force origin main` is rejected. |
| Block deletion | `main` cannot be deleted. |

- Required approvals: 0 (sole-owner repo; CI is the quality gate). Increase to 1 when a second contributor joins.
- No bypass actors configured. For emergencies, temporarily set enforcement to `disabled` via `gh api --method PUT /repos/masuda-so/second-brain/rulesets/14985776`.
- The required status check context `"Validate hooks, scripts, and init"` is coupled to the `name:` field on line 10 of `.github/workflows/ci.yml`. Renaming that job without updating the ruleset will block all merges.

---

## Vault

- Location: `/Users/masudaso/Documents/Obsidian Vault`
- This section serves as the Knowledge OS constitution for that vault.
- Session capture: accumulate prompts and key events during the session, then leave the distilled trail in `Daily/YYYY-MM-DD.md` under the `## AI Session` heading.
- All ambient knowledge — personal preferences, project learnings, AI-generated insights — goes to the vault, not Claude auto memory.

## Vault Architecture

| Directory | Cognitive Analogy | Purpose |
|-----------|-------------------|---------|
| `Daily/` | Episodic memory | Daily log: events, thoughts, AI session notes |
| `Weekly/` | Working memory consolidation | Weekly review and intentions |
| `Monthly/` | Long-term episodic | Monthly themes and retrospectives |
| `Projects/` | Procedural memory | Active work: status, goal, next actions |
| `Bases/` | Semantic memory DB | Structured facts: books, people, meetings, etc. |
| `References/` | Semantic memory | Permanent concept and source notes |
| `Ideas/` | Association cortex | Loose, unprocessed sparks |
| `Clippings/` | Sensory buffer | Web clips awaiting processing |
| `Meta/` | Metacognition | Vault rules, system notes, templates |
| `Canvases/` | Spatial reasoning | Visual maps and concept diagrams |
| `Sandbox/` | Training environment | Obsidian onboarding and safe experimentation |

### second-brain Internal Directories (not Template-Vault canonical)

| Directory | Purpose |
|-----------|---------|
| `Meta/Promotions/` | Harvest L2 staging queue — notes automatically promoted from candidates but not yet reviewed. `type: staged`. These are second-brain control-plane artifacts, not canonical vault notes. Manually promote to `References/` or `Projects/` after review. |
| `Meta/AI Sessions/` | Live session capture (prompts, tool events, closeout). One file per session. Not meant for long-term curation — archive or delete after distillation. |
| `Meta/.cache/` | SQLite sidecar (`memory.db`). Ephemeral — safe to delete; will be recreated. |

## LLM Wiki 運用モデル

この vault は、永続的に蓄積される「コンパイル済み wiki」パターンを実装する。質問のたびに raw source から知識を再発見し直すのではなく、耐久性のある source を一度 vault に統合し、統合済みの synthesis を更新し続け、以後の質問ではまずコンパイル済みノートを読む。

| LLM Wiki レイヤー | second-brain 上の場所 | ルール |
|-------------------|------------------------|--------|
| Raw sources | `Clippings/`, imported files, `Meta/AI Sessions/` | provenance を保存する。raw material は source of truth として扱い、軽い metadata や backlink 以外では原則として書き換えない。 |
| Compiled wiki | `References/`, `Bases/`, `Projects/`, review 済み `Ideas/` | agent が維持する synthesis。重複ノートを作る前に既存ノートを更新し、cross-link を明示する。 |
| Schema | `CLAUDE.md`, `commands/`, `skills/`, scripts, hooks | 運用契約。workflow が変わったら schema を進化させ、deterministic な guardrail と整合させる。 |

### Source Ingestion

1. まず source の provenance を記録する。URL、判明している author、capture date、利用可能な local asset path を残す。
2. 新規ノートを作る前に、既存の `References/`, `Projects/`, `Bases/`, `Ideas/`, 関連する Daily note を検索する。
3. `References/` または適切な Base に atomic note を作成または更新する。`Projects/` は active work のみに使い、`Ideas/` は未確定の可能性に使う。
4. contradictions、superseded claims、open questions は、どれか一つを黙って選ぶのではなく destination note に記録する。
5. source clipping/session note から、それによって変更された durable note へリンクし、durable note 側からも source へ backlink する。
6. ingest によって wiki が実質的に変わった場合は、`Daily/YYYY-MM-DD.md ## AI Session` に短い trace を残す。

### Query and Synthesis

- まず compiled note を読み、compiled layer が missing、stale、または contested な場合にだけ raw source へ戻る。
- query から再利用可能な synthesis が生まれた場合は、chat history だけに残さず、`References/`、Base、または active な `Projects/` note へ保存する。
- 回答では使用した note への wikilink を示し、fact、interpretation、open question を区別する。

### Wiki Lint

定期的に vault を health-check し、duplicate concept note、orphan page、stale claim、未解決の contradiction、missing backlink、分割すべき oversized note、review が必要な `Meta/Promotions/` draft を探す。

## Note Templates

Source: [masuda-so/Template-Vault](https://github.com/masuda-so/Template-Vault)

Insertable template files live in `Templates/` at the vault root (core Templates plugin: folder = `Templates`). The headings below are the canonical structure; `## AI Session` is a second-brain addition not present in Template-Vault's files.

**Daily** (`Daily/YYYY-MM-DD.md`):
```
---
type: daily
date: YYYY-MM-DD
tags:
  - journal
---
## 今日のフォーカス
## メモ
> [!note] 振り返り
## フォローアップ
- [ ] items
## 関連ノート
## AI Session
```

**Weekly** (`Weekly/YYYY-Www.md`):
```
---
type: weekly
week: YYYY-Www
reviewed: YYYY-MM-DD
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
```

**Monthly** (`Monthly/YYYY-MM.md`):
```
---
type: monthly
period: YYYY-MM
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
```

**Project** (`Projects/<slug>.md`):
```
---
type: project
status: active
review: YYYY-MM-DD
tags: []
---
## ゴール
## 次のアクション
- [ ] items
## 添付
## 関連ノート
```

**Reference** (`References/<slug>.md`):
```
---
type: reference
topic: topic-name
---
## 目的
## 手順
> [!important] 再利用ルール
## 関連資料
```

**Idea** (`Ideas/<slug>.md`):
```
---
type: idea
status: incubating
created: YYYY-MM-DD
tags: []
---
## プロジェクト化の条件
- 今月実装したい
- 複数ステップが必要
- 他フォルダへ影響がある
> [!note] 次の扱い
## 下書き素材
```

**Clipping** (`Clippings/<slug>.md`):
```
---
type: clipping
source: https://...
captured: YYYY-MM-DD
---
## メモ
- 引用
```

## Bases Schema

Recommended YAML frontmatter properties for notes consumed by each Base:

- **Journal.base** — `Daily/` notes: `type: daily`, `date`, `tags`
- **Projects.base** — `Projects/` notes: `type: project`, `status`, `review`
- **Meetings.base** — meeting notes: `date`, `attendees`, `decision`
- **People.base** — people notes: `name`, `context`, `last-contact`
- **Books.base** — `title`, `author`, `status` (reading/done), `rating`
- **Clippings.base** — `source`, `date`, `tags`
- **Movies.base / Shows.base** — `title`, `status` (watched/want), `rating`
- **Music.base / Podcasts.base** — `title`, `artist`, `status`, `rating`
- **Places.base / Trips.base** — `location`, `date`, `tags`
- **Recipes.base** — `title`, `cuisine`, `time`, `rating`
- **Ratings.base** — cross-domain: `title`, `type`, `rating`, `date`

## AI Behavior Rules

- Read before writing: inspect the target note before any modification.
- Discover, don't invent: search existing notes before creating new ones.
- Prefer append over rewrite for Daily and Project notes.
- Route all new captures to `Daily/YYYY-MM-DD.md ## メモ` first.
- Distill durable knowledge to `References/` or the appropriate Base after the session.
- Never delete vault content — use `#archived` until the vault defines a dedicated archive location.
- AI session learnings -> append to `Daily/YYYY-MM-DD.md ## AI Session`.
- Detailed live capture -> `Meta/AI Sessions/YYYY-MM-DD/<session-id>.md`.

## Tagging Conventions

- Status: `#active`, `#archived`, `#someday`, `#waiting`
- Type: `#fact`, `#interpretation`, `#question`, `#idea`, `#project`
- Domain: `#tech`, `#ai`, `#personal`, `#work`, `#learning`

## L4 Ambient Capture

ALL knowledge from Claude Code sessions — personal preferences, project learnings, AI-generated insights — MUST go to the vault, not Claude auto memory.

Intake point: `Daily/YYYY-MM-DD.md ## AI Session`.
Durable distillations: `References/` or the appropriate Base.

## Note Lifecycle

```
Clippings/ / Ideas/    →    Daily/ (tagged + linked)    →    References/ or Base    →    tagged as #archived when no longer active
   (capture)                     (process)                       (distill)              
```
