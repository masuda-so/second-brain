#!/usr/bin/env python3
"""
distill-writer.py — Phase 1: deterministic draft-note generator.

Takes distill.py candidates JSON and writes template-compliant note drafts
to Meta/Promotions/. Never writes to canonical vault locations (References/,
Projects/, Ideas/). Each draft includes provenance, reviewed_status: false,
and generated: true so Phase 2 can make deterministic promotion decisions.

Usage (from session-distill.sh):
  SECOND_BRAIN_VAULT_PATH=... python3 distill-writer.py \\
      --session-id SESSION_ID --date YYYY-MM-DD

  (reads candidates JSON from stdin)

Returns JSON: {"written": [{"path": ..., "title": ...}], "skipped": N}
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

AGENT_FILE = REPO_ROOT / "agents" / "note-body-generator.md"
CLAUDE_TIMEOUT = 30  # seconds

PROMOTIONS_SUBDIR = "Meta/Promotions"
DRAFT_PREFIX = "draft"

# ── Helpers ───────────────────────────────────────────────────────────────────


def warn(msg: str) -> None:
    print(f"distill-writer: {msg}", file=sys.stderr)


def get_vault_path() -> pathlib.Path:
    env = os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip()
    if env:
        return pathlib.Path(env).expanduser()
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            m = re.match(r"^- Location: `(.+)`", line)
            if m:
                return pathlib.Path(m.group(1).strip()).expanduser()
    raise RuntimeError("vault path not found")


def slugify(text: str, max_len: int = 60) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s-]", "", lowered)
    lowered = re.sub(r"[\s_]+", "-", lowered).strip("-")
    return lowered[:max_len] or "note"


def infer_title(signal: str) -> str:
    """Generate a human-readable title from a signal string."""
    # Strip bullet/checkbox prefix
    clean = re.sub(r"^[-*+]\s*", "", signal.strip())
    clean = re.sub(r"^\d+\.\s*", "", clean)
    clean = re.sub(r"^\[[ xX]\]\s*", "", clean)
    # Strip inline code backticks content as potential title
    code_m = re.search(r"`([^`\n]{3,40})`", clean)
    if code_m:
        return code_m.group(1).strip()
    # Use text before first colon as title
    colon_m = re.match(r"^([^:]{5,50}):", clean)
    if colon_m:
        return colon_m.group(1).strip()
    # Use X is/means pattern
    define_m = re.match(r"^([A-Za-zぁ-ん一-龯][^\n]{2,40})\s+(?:is|means|とは)\b", clean)
    if define_m:
        return define_m.group(1).strip()
    # Fall back to first 50 chars
    return clean[:50].rstrip("、。 ").strip() or "メモ"


def infer_topic(signal: str, destination: str) -> str:
    """Infer a topic tag from signal and destination path."""
    dest_lower = destination.lower()
    if "decision" in dest_lower:
        return "decisions"
    if "project" in dest_lower:
        return "project-notes"
    # Simple keyword mapping
    keywords = {
        "tmux": "tmux-bridge",
        "distill": "distillation",
        "vault": "obsidian",
        "hook": "hooks",
        "session": "session-management",
        "weekly": "weekly-review",
        "daily": "daily-notes",
        "agent": "agent-coordination",
        "test": "testing",
        "claude": "claude-code",
    }
    sig_lower = signal.lower()
    for kw, topic in keywords.items():
        if kw in sig_lower:
            return topic
    return "general"


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block from agent file content."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].lstrip("\n")
    return text


def generate_body_via_claude(signal: str) -> str | None:
    """Call claude -p to generate note body. Returns body text or None on failure."""
    if not shutil.which("claude"):
        return None
    if not AGENT_FILE.exists():
        return None

    system_prompt = _strip_frontmatter(AGENT_FILE.read_text(encoding="utf-8"))
    prompt = f"以下のシグナルからノート本文を生成してください:\n\n{signal[:2000]}"

    try:
        result = subprocess.run(
            ["claude", "-p", "--system-prompt", system_prompt, prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
        if result.returncode == 0:
            body = result.stdout.strip()
            if body and "## 目的" in body:
                return body
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return None


def draft_filename(date: str, title: str) -> str:
    slug = slugify(title, max_len=50)
    return f"{DRAFT_PREFIX}-{date}-{slug}.md"


ERROR_RE = re.compile(
    r"エラー|error|exception|fail(?:ed|ure)?|バグ|bug|"
    r"fixed|resolved|(?:バグ|エラー)\s*修正",
    re.I,
)
CONFIG_RE = re.compile(r"設定|config|rule|ルール|policy|フック設定|hook\s*config", re.I)
PROC_RE = re.compile(r"手順|操作|実行|run|deploy|install|setup", re.I)


def generate_questions(signal: str) -> str:
    normalized = signal.strip()
    if ERROR_RE.search(normalized):
        questions = [
            "どの条件でこのエラーが発生するか？",
            "回避策は？",
            "再発を防ぐための確認ポイントは？",
        ]
    elif PROC_RE.search(normalized):
        questions = [
            "この手順の前提条件は何か？",
            "失敗するケースや注意点は？",
            "完了をどう確認するか？",
        ]
    elif CONFIG_RE.search(normalized):
        questions = [
            "この設定はどこで有効になるか？",
            "例外ケースは？",
            "変更時に影響を受ける箇所は？",
        ]
    else:
        questions = [
            "この知識はいつ役立つか？",
            "関連するノートは？",
        ]

    return "\n".join(f"- {question}" for question in questions)


# ── Template builders ─────────────────────────────────────────────────────────


def build_reference_draft(
    signal: str,
    title: str,
    topic: str,
    destination: str,
    action: str,
    session_id: str,
    date: str,
) -> str:
    dest_link = f"[[{destination.removesuffix('.md')}]]" if destination else ""
    related = f"\n- {dest_link}" if dest_link and action == "append" else ""

    ai_body = generate_body_via_claude(signal)
    if ai_body:
        body_section = ai_body
    else:
        questions = generate_questions(signal)
        body_section = (
            f"## 目的\n\n{signal}\n\n## 手順\n\n"
            f"<!-- AI生成の論点ヒント（/distill で編集・確定してください） -->\n"
            f"{questions}\n\n> [!tip] 再利用ルール\n\n"
            f"<!-- 上記の論点を踏まえて再利用条件を記述してください -->"
        )

    return f"""\
---
title: {title}
type: reference
topic: {topic}
generated: true
reviewed_status: false
source_session: {session_id}
source_date: {date}
promotion_target: {destination}
promotion_action: {action}
tags: []
---
{body_section}

## 関連資料
{related}
"""


def build_idea_draft(
    signal: str,
    title: str,
    session_id: str,
    date: str,
    destination: str,
    action: str,
) -> str:
    return f"""\
---
title: {title}
type: idea
status: incubating
created: {date}
generated: true
reviewed_status: false
source_session: {session_id}
source_date: {date}
promotion_target: {destination}
promotion_action: {action}
tags: []
---
## プロジェクト化の条件

<!-- /distill で補完 -->

> [!note] 次の扱い

## 下書き素材

{signal}
"""


def build_project_append_draft(
    signal: str,
    title: str,
    destination: str,
    session_id: str,
    date: str,
) -> str:
    project_name = pathlib.Path(destination).stem
    return f"""\
---
title: {project_name} への追記候補
type: staged
generated: true
reviewed_status: false
source_session: {session_id}
source_date: {date}
promotion_target: {destination}
promotion_action: append
tags:
  - staged
---
## 追記候補

- {date}: {signal}

<!-- [[{destination.removesuffix('.md')}]] に手動で追記してください -->
"""


def build_draft(candidate: dict, session_id: str, date: str) -> tuple[str, str]:
    """Return (title, draft_content) for a candidate."""
    signal = candidate.get("signal", "")
    destination = candidate.get("destination", "")
    action = candidate.get("action", "create")

    title = infer_title(signal)
    topic = infer_topic(signal, destination)

    dest_lower = destination.lower()
    if "projects/" in dest_lower:
        content = build_project_append_draft(signal, title, destination, session_id, date)
    elif "ideas/" in dest_lower:
        content = build_idea_draft(signal, title, session_id, date, destination, action)
    else:
        # Default: reference
        content = build_reference_draft(signal, title, topic, destination, action, session_id, date)

    return title, content


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 draft-note generator")
    parser.add_argument("--session-id", default="unknown-session")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    try:
        vault = get_vault_path()
    except RuntimeError as exc:
        warn(str(exc))
        print(json.dumps({"written": [], "skipped": 0}))
        return 0

    promotions_dir = vault / PROMOTIONS_SUBDIR
    promotions_dir.mkdir(parents=True, exist_ok=True)

    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"written": [], "skipped": 0}))
        return 0

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        warn(f"invalid JSON: {exc}")
        print(json.dumps({"written": [], "skipped": 0}))
        return 0

    candidates = data.get("candidates", [])
    written: list[dict] = []
    skipped = 0
    seen_signals: set[str] = set()

    for candidate in candidates:
        signal = candidate.get("signal", "").strip()
        if not signal:
            skipped += 1
            continue

        # Deduplicate by signal
        sig_key = re.sub(r"\s+", " ", signal).lower()
        if sig_key in seen_signals:
            skipped += 1
            continue
        seen_signals.add(sig_key)

        title, content = build_draft(candidate, args.session_id, args.date)
        filename = draft_filename(args.date, title)
        dest_path = promotions_dir / filename

        # Skip if already exists (idempotency)
        if dest_path.exists():
            skipped += 1
            continue

        try:
            dest_path.write_text(content, encoding="utf-8")
            written.append({"path": str(dest_path.relative_to(vault)), "title": title})
        except OSError as exc:
            warn(f"write failed for {dest_path}: {exc}")
            skipped += 1

    print(json.dumps({"written": written, "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
