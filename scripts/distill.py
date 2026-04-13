#!/usr/bin/env python3
"""
distill.py

Deterministic dry-run helper for /distill.
Reads the current session note and today's Daily note, extracts durable
signals, classifies them into References/ or Projects/, and emits JSON only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

NOISE_RE = re.compile(
    r"^(ok|okay|yes|no|thanks?|sure|got it|understood|了解|承知|はい|いいえ|わかりました)\W*$",
    re.IGNORECASE,
)
SHELL_NOISE_RE = re.compile(
    r"^(?:\$ |❯ |>|bash\(|Running test:|Traceback|Exception:|FAIL:|OK$|error: must read the pane"
    r"|\[tmux-bridge )",
    re.IGNORECASE,
)
DECISION_RE = re.compile(
    r"(decid|decision|policy|rule|convention|adopt|going forward|方針|決定|採用|ルール)",
    re.IGNORECASE,
)
PROJECT_RE = re.compile(
    r"^(next action|next step|blocker|status|milestone|goal|review|進捗|ブロッカー|次のアクション|状態)\s*[:：-]",
    re.IGNORECASE,
)
REFERENCE_RE = re.compile(
    r"( is | means | pattern|runbook|technique|workflow|definition|principle|how to|とは|定義|手順|原則)",
    re.IGNORECASE,
)


def warn(message: str) -> None:
    print(f"distill: {message}", file=sys.stderr)


def slugify(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s-]", "", lowered)
    lowered = re.sub(r"[\s_]+", "-", lowered).strip("-")
    return lowered[:80] or "note"


def get_vault_path() -> pathlib.Path:
    env_path = os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip()
    if env_path:
        return pathlib.Path(env_path).expanduser()
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            match = re.match(r"^- Location: `(.+)`", line)
            if match:
                return pathlib.Path(match.group(1).strip()).expanduser()
    raise RuntimeError("vault path not found")


def normalize_session_id(raw: str) -> str:
    session_id = re.sub(r"[^A-Za-z0-9._-]", "-", raw).strip("-")
    return session_id or "unknown-session"


def extract_session_id() -> str:
    raw = (
        os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or "unknown-session"
    )
    return normalize_session_id(raw)


def resolve_session_note(
    vault: pathlib.Path,
    override: str | None,
    session_id: str,
    today: str,
) -> pathlib.Path:
    if override:
        return pathlib.Path(override).expanduser()
    session_dir = os.environ.get("SECOND_BRAIN_SESSION_DIR", "Meta/AI Sessions")
    return vault / session_dir / today / f"{session_id}.md"


def strip_frontmatter_and_code(text: str) -> str:
    text = re.sub(r"^---\n.*?---\n", "", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return text


def extract_daily_sections(text: str) -> list[str]:
    sections: list[str] = []
    active = None
    buffer: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if active in {"ai session", "メモ"} and buffer:
                sections.extend(buffer)
            active = heading.group(1).strip().lower()
            buffer = []
            continue
        if active in {"ai session", "メモ"}:
            buffer.append(line)
    if active in {"ai session", "メモ"} and buffer:
        sections.extend(buffer)
    return sections


def clean_signal(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[-*+]\s*", "", line)
    line = re.sub(r"^\d+\.\s*", "", line)
    line = re.sub(r"^\[[ xX]\]\s*", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def is_durable_signal(line: str) -> bool:
    if not line or len(line) < 12:
        return False
    if line.startswith("#") or line.startswith("> [!"):
        return False
    if NOISE_RE.match(line) or SHELL_NOISE_RE.match(line):
        return False
    return True


def collect_signals(session_note: pathlib.Path, daily_note: pathlib.Path) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()

    def add(lines: list[str]) -> None:
        for raw in lines:
            signal = clean_signal(raw)
            if not is_durable_signal(signal):
                continue
            normalized = re.sub(r"\s+", " ", signal).lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            signals.append(signal)

    if session_note.exists():
        add(strip_frontmatter_and_code(session_note.read_text()).splitlines())
    if daily_note.exists():
        daily_text = strip_frontmatter_and_code(daily_note.read_text())
        add(extract_daily_sections(daily_text))
    return signals


def find_active_project_slug(vault: pathlib.Path, cwd: pathlib.Path) -> str | None:
    projects_dir = vault / "Projects"
    if not projects_dir.is_dir():
        return None

    repo_name = ""
    try:
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if git_root:
            repo_name = pathlib.Path(git_root).name
    except Exception:
        repo_name = ""

    dir_name = cwd.name
    md_files = None

    for slug in (repo_name, dir_name):
        if not slug:
            continue
        exact = projects_dir / f"{slug}.md"
        if exact.exists():
            return exact.stem

        if md_files is None:
            md_files = sorted(projects_dir.glob("*.md"))

        for path in md_files:
            if path.stem.lower() == slug.lower():
                return path.stem

    best_match = None
    best_len = 0
    cwd_text = str(cwd)

    if md_files is None:
        md_files = sorted(projects_dir.glob("*.md"))

    for path in md_files:
        stem = path.stem
        if len(stem) >= 4 and stem in cwd_text and len(stem) > best_len:
            best_match = stem
            best_len = len(stem)
    return best_match


def infer_reference_slug(signal: str) -> str:
    code_match = re.search(r"`([^`\n]{3,40})`", signal)
    if code_match:
        return slugify(code_match.group(1))
    colon_match = re.match(r"^([^:]{3,60}):", signal)
    if colon_match:
        return slugify(colon_match.group(1))
    define_match = re.match(r"^([A-Za-z][A-Za-z0-9 _-]{2,40})\s+(?:is|means)\b", signal)
    if define_match:
        return slugify(define_match.group(1))
    jp_match = re.match(r"^(.{2,30})とは", signal)
    if jp_match:
        return slugify(jp_match.group(1))
    words = signal.split()[:8]
    return slugify(" ".join(words))


def classify_signal(
    signal: str,
    vault: pathlib.Path,
    active_project_slug: str | None,
    today: str,
) -> dict | None:
    project_dest = f"Projects/{active_project_slug}.md" if active_project_slug else None
    lower = signal.lower()

    if DECISION_RE.search(signal):
        if project_dest:
            return {
                "signal": signal,
                "destination": project_dest,
                "action": "append",
                "content_draft": f"- {today}: {signal}",
            }
        return {
            "signal": signal,
            "destination": f"References/decisions-{today}.md",
            "action": "append",
            "content_draft": f"- {signal}",
        }

    if PROJECT_RE.search(signal) and project_dest:
        return {
            "signal": signal,
            "destination": project_dest,
            "action": "append",
            "content_draft": f"- {today}: {signal}",
        }

    if REFERENCE_RE.search(signal) or len(lower.split()) >= 6:
        slug = infer_reference_slug(signal)
        ref_path = vault / "References" / f"{slug}.md"
        return {
            "signal": signal,
            "destination": f"References/{slug}.md",
            "action": "append" if ref_path.exists() else "create",
            "content_draft": signal,
        }

    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run distillation candidate extractor"
    )
    parser.add_argument("session_note", nargs="?", help="Optional session note path")
    parser.add_argument(
        "--session-id", help="Optional session id used to resolve Meta/AI Sessions path"
    )
    args = parser.parse_args()

    try:
        vault = get_vault_path()
    except RuntimeError as exc:
        warn(str(exc))
        print(json.dumps({"candidates": []}))
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    session_id = (
        normalize_session_id(args.session_id)
        if args.session_id
        else extract_session_id()
    )
    session_note = resolve_session_note(vault, args.session_note, session_id, today)
    daily_note = vault / "Daily" / f"{today}.md"
    cwd = pathlib.Path(os.getcwd())
    active_project_slug = find_active_project_slug(vault, cwd)

    signals = collect_signals(session_note, daily_note)
    candidates: list[dict] = []
    seen_dest_signal: set[tuple[str, str]] = set()
    for signal in signals:
        candidate = classify_signal(signal, vault, active_project_slug, today)
        if not candidate:
            continue
        key = (candidate["destination"], candidate["signal"].lower())
        if key in seen_dest_signal:
            continue
        seen_dest_signal.add(key)
        candidates.append(candidate)

    print(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
