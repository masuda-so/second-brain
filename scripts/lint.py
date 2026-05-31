#!/usr/bin/env python3
"""
lint.py — Vault Health Check
=============================
Scans the Obsidian vault for structural issues and reports findings.

Subcommands:
  check   — full audit, JSON report to stdout
  quick   — lightweight subset (frontmatter + broken links only), for SessionStart
  fix     — auto-fix safe issues (add missing frontmatter fields)

Checks:
  1. orphan_pages     — References/Ideas notes with zero inbound wikilinks
  2. broken_links     — [[wikilinks]] pointing to non-existent notes
  3. frontmatter      — missing required YAML fields per note type
  4. stale_notes      — old notes (>90d) with no inbound links
  5. low_quality      — Ideas/ notes with near-empty body (<50 chars)

Deterministic and fast — no claude -p call, no network. Always exits 0 (fail-open).

Usage:
  python3 lint.py check [--format json|text]
  python3 lint.py quick
  python3 lint.py fix [--dry-run]
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass, field

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Directories to scan for knowledge notes
SCAN_DIRS = (
    "References",
    "Ideas",
    "Projects",
    "Daily",
    "Weekly",
    "Monthly",
    "Meta/Promotions",
    "Clippings",
    "Bases",
)

# Directories to include in wikilink source scanning (broader)
LINK_SOURCE_DIRS = (
    "References",
    "Ideas",
    "Projects",
    "Daily",
    "Weekly",
    "Monthly",
    "Meta/Promotions",
    "Meta/Profile",
    "Clippings",
    "Bases",
)

# Directories to skip entirely
SKIP_DIRS = (
    "Sandbox",
    "Templates",
    "Meta/AI Sessions",
    "Meta/.cache",
    ".obsidian",
    ".trash",
)

# Required frontmatter fields per note type (directory-based fallback)
REQUIRED_FM: dict[str, list[str]] = {
    "daily": ["type", "date"],
    "weekly": ["type", "week"],
    "monthly": ["type", "period"],
    "project": ["type", "status"],
    "reference": ["type", "topic"],
    "idea": ["type", "status"],
    "clipping": ["type", "source"],
}

# Map directory to expected type
DIR_TYPE_MAP: dict[str, str] = {
    "Daily": "daily",
    "Weekly": "weekly",
    "Monthly": "monthly",
    "Projects": "project",
    "References": "reference",
    "Ideas": "idea",
    "Clippings": "clipping",
}

STALE_DAYS = 90
LOW_QUALITY_CHARS = 50

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*?)?\]\]")


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Issue:
    severity: str  # high, medium, low
    check: str  # orphan_pages, broken_links, etc.
    path: str  # relative vault path
    message: str
    fixable: bool = False  # whether this issue can be auto-repaired by lint fix

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "check": self.check,
            "path": self.path,
            "message": self.message,
            "fixable": self.fixable,
        }


@dataclass
class LintReport:
    total_notes: int = 0
    issues: list[Issue] = field(default_factory=list)
    scanned_dirs: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        by_check: dict[str, int] = {}
        for issue in self.issues:
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
            by_check[issue.check] = by_check.get(issue.check, 0) + 1
        return {
            "summary": {
                "total_notes": self.total_notes,
                "issues": len(self.issues),
                "fixable": sum(1 for i in self.issues if i.fixable),
                "by_severity": by_severity,
                "by_check": by_check,
                "elapsed_ms": self.elapsed_ms,
            },
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_text(self) -> str:
        lines: list[str] = []
        d = self.to_dict()
        s = d["summary"]
        lines.append(
            f"Vault Lint: {s['total_notes']} notes scanned, "
            f"{s['issues']} issues found ({s['fixable']} fixable) "
            f"in {s['elapsed_ms']}ms"
        )
        if s["by_severity"]["high"]:
            lines.append(f"  HIGH: {s['by_severity']['high']}")
        if s["by_severity"]["medium"]:
            lines.append(f"  MEDIUM: {s['by_severity']['medium']}")
        if s["by_severity"]["low"]:
            lines.append(f"  LOW: {s['by_severity']['low']}")
        lines.append("")
        for issue in self.issues:
            marker = {"high": "!!!", "medium": " ! ", "low": " . "}[issue.severity]
            fix = " [fixable]" if issue.fixable else ""
            lines.append(
                f"  {marker} [{issue.check}] {issue.path}: {issue.message}{fix}"
            )
        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────


def warn(msg: str) -> None:
    print(f"lint: {msg}", file=sys.stderr)


def get_vault_path() -> pathlib.Path | None:
    env = os.environ.get("SECOND_BRAIN_VAULT_PATH", "").strip()
    if env:
        p = pathlib.Path(env).expanduser()
        return p if p.is_dir() else None
    claude_md = REPO_ROOT / "CLAUDE.md"
    if claude_md.exists():
        for line in claude_md.read_text().splitlines():
            m = re.match(r"^- Location: `(.+)`", line)
            if m:
                p = pathlib.Path(m.group(1).strip()).expanduser()
                return p if p.is_dir() else None
    return None


def should_skip(rel: str) -> bool:
    return any(rel.startswith(skip) for skip in SKIP_DIRS)


def get_rel_path(path: pathlib.Path, vault_str: str) -> str:
    """Fast alternative to Path.relative_to(vault)."""
    return str(path)[len(vault_str) :].lstrip(os.sep)


FM_DELIM_RE = re.compile(r"^\s*---\s*$", re.MULTILINE)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter as flat key-value pairs (values as strings).

    Handles indented frontmatter (e.g. harvest.py output with leading spaces
    on both delimiters and field lines).
    """
    matches = list(FM_DELIM_RE.finditer(text))
    if len(matches) < 2:
        return {}
    # First delimiter must be at or near the start (only whitespace before it)
    if text[: matches[0].start()].strip():
        return {}
    fm_text = text[matches[0].end() : matches[1].start()]
    result: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m:
            result[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return result


def note_body_length(text: str) -> int:
    """Return character count of body text (after frontmatter, excluding headings)."""
    delims = list(FM_DELIM_RE.finditer(text))
    if len(delims) >= 2:
        text = text[delims[1].end() :]
    body_lines = [
        line
        for line in text.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("---")
    ]
    return sum(len(line.strip()) for line in body_lines)


def infer_type_from_dir(path: pathlib.Path, vault: pathlib.Path) -> str | None:
    rel = path.relative_to(vault)
    first_part = rel.parts[0] if rel.parts else ""
    return DIR_TYPE_MAP.get(first_part)


def _read_note(note: pathlib.Path, cache: dict[pathlib.Path, str]) -> str | None:
    """Read a note from cache or disk."""
    if note in cache:
        return cache[note]
    try:
        text = note.read_text(encoding="utf-8", errors="ignore")
        cache[note] = text
        return text
    except OSError:
        return None


# ── Checks ────────────────────────────────────────────────────────────────────


def scan_vault(
    vault: pathlib.Path,
) -> tuple[list[pathlib.Path], dict[str, str], dict[str, set[str]]]:
    """Single pass over vault to collect notes, stems, and init inbound map."""
    vault_str = str(vault)
    # Sort for determinism in stem_index (first match wins)
    all_md = sorted(list(vault.rglob("*.md")))

    scan_set: list[pathlib.Path] = []
    stem_index: dict[str, str] = {}
    inbound: dict[str, set[str]] = {}

    for md in all_md:
        rel = get_rel_path(md, vault_str)
        # Skip truly non-content dirs
        if any(rel.startswith(s) for s in (".obsidian", ".trash", "Templates")):
            continue

        # Skip vault root files (README.md, etc.)
        if "/" not in rel and "\\" not in rel:
            continue

        rel_no_ext = rel.removesuffix(".md")
        stem = md.stem
        inbound.setdefault(rel_no_ext, set())

        # First match wins (prefer shorter paths)
        if stem not in stem_index:
            stem_index[stem] = rel_no_ext

        if not should_skip(rel):
            scan_set.append(md)

    return scan_set, stem_index, inbound


def build_link_graph(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    stem_index: dict[str, str],
    inbound: dict[str, set[str]],
    content_cache: dict[pathlib.Path, str],
) -> dict[str, list[tuple[str, str]]]:
    """Build inbound link map and broken link map.

    Returns:
        broken:  {source_rel: [(wikilink_text, ...)]}
    """
    vault_str = str(vault)
    broken: dict[str, list[tuple[str, str]]] = {}

    # Only scan outgoing links from the scan-set notes
    for note in notes:
        rel = get_rel_path(note, vault_str)
        rel_no_ext = rel.removesuffix(".md")
        text = _read_note(note, content_cache)
        if text is None:
            continue

        for m in WIKILINK_RE.finditer(text):
            target = m.group(1).strip()
            if not target:
                continue

            # Resolve: try exact path, then stem lookup
            target_no_ext = target.removesuffix(".md")
            resolved = None
            if target_no_ext in inbound:
                resolved = target_no_ext
            else:
                target_stem = pathlib.PurePosixPath(target_no_ext).name
                resolved = stem_index.get(target_stem)

            if resolved:
                if resolved != rel_no_ext:  # don't count self-links
                    inbound[resolved].add(rel_no_ext)
            else:
                broken.setdefault(rel, []).append((target, m.group(0)))

    return broken


def check_orphan_pages(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    inbound: dict[str, set[str]],
) -> list[Issue]:
    """Find References/ and Ideas/ notes with zero inbound wikilinks."""
    vault_str = str(vault)
    issues: list[Issue] = []
    for note in notes:
        rel = get_rel_path(note, vault_str)
        rel_no_ext = rel.removesuffix(".md")
        if not (rel.startswith("References/") or rel.startswith("Ideas/")):
            continue
        links_in = inbound.get(rel_no_ext, set())
        if not links_in:
            issues.append(
                Issue(
                    severity="medium",
                    check="orphan_pages",
                    path=rel,
                    message="no inbound wikilinks from other notes",
                )
            )
    return issues


def check_broken_links(
    broken: dict[str, list[tuple[str, str]]],
) -> list[Issue]:
    """Report wikilinks pointing to non-existent notes."""
    issues: list[Issue] = []
    for source_rel, targets in broken.items():
        for target_text, raw in targets:
            issues.append(
                Issue(
                    severity="low",
                    check="broken_links",
                    path=source_rel,
                    message=f"broken wikilink {raw} — no matching note for '{target_text}'",
                )
            )
    return issues


def check_frontmatter(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    content_cache: dict[pathlib.Path, str],
) -> list[Issue]:
    """Check required YAML frontmatter fields based on note type/directory."""
    vault_str = str(vault)
    issues: list[Issue] = []
    for note in notes:
        rel = get_rel_path(note, vault_str)
        # Skip Promotions drafts — they have their own schema
        if rel.startswith("Meta/Promotions/"):
            continue
        text = _read_note(note, content_cache)
        if text is None:
            continue

        fm = parse_frontmatter(text)
        note_type = fm.get("type") or infer_type_from_dir(note, vault)
        if not note_type:
            continue

        required = REQUIRED_FM.get(note_type, [])
        missing = [f for f in required if f not in fm or not fm[f]]
        if missing:
            issues.append(
                Issue(
                    severity="medium" if "type" in missing else "low",
                    check="frontmatter",
                    path=rel,
                    message=f"missing frontmatter: {', '.join(missing)}",
                    fixable="type" in missing,
                )
            )
    return issues


def check_stale_notes(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    inbound: dict[str, set[str]],
) -> list[Issue]:
    """Flag old notes with no inbound links and no recent modification."""
    vault_str = str(vault)
    issues: list[Issue] = []
    now = time.time()
    cutoff = now - (STALE_DAYS * 86400)
    for note in notes:
        rel = get_rel_path(note, vault_str)
        # Only check knowledge notes (References, Ideas)
        if not (rel.startswith("References/") or rel.startswith("Ideas/")):
            continue
        rel_no_ext = rel.removesuffix(".md")
        links_in = inbound.get(rel_no_ext, set())
        if links_in:
            continue
        try:
            mtime = note.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            days_old = int((now - mtime) / 86400)
            issues.append(
                Issue(
                    severity="low",
                    check="stale_notes",
                    path=rel,
                    message=f"no inbound links, last modified {days_old} days ago",
                )
            )
    return issues


def check_low_quality(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    content_cache: dict[pathlib.Path, str],
) -> list[Issue]:
    """Flag Ideas/ notes with near-empty body."""
    vault_str = str(vault)
    issues: list[Issue] = []
    for note in notes:
        rel = get_rel_path(note, vault_str)
        if not rel.startswith("Ideas/"):
            continue
        text = _read_note(note, content_cache)
        if text is None:
            continue
        body_len = note_body_length(text)
        if body_len < LOW_QUALITY_CHARS:
            issues.append(
                Issue(
                    severity="medium",
                    check="low_quality",
                    path=rel,
                    message=f"Ideas/ note with only {body_len} chars of body text",
                )
            )
    return issues


# ── Fix ───────────────────────────────────────────────────────────────────────


def fix_frontmatter(
    notes: list[pathlib.Path],
    vault: pathlib.Path,
    content_cache: dict[pathlib.Path, str],
    dry_run: bool = False,
) -> list[dict]:
    """Add missing 'type' field to notes based on directory."""
    vault_str = str(vault)
    fixed: list[dict] = []
    for note in notes:
        rel = get_rel_path(note, vault_str)
        if rel.startswith("Meta/Promotions/"):
            continue
        text = _read_note(note, content_cache)
        if text is None:
            continue

        fm = parse_frontmatter(text)
        expected_type = infer_type_from_dir(note, vault)
        if not expected_type:
            continue
        if fm.get("type"):
            continue

        # Add type field to frontmatter
        delims = list(FM_DELIM_RE.finditer(text))
        if len(delims) >= 2:
            # Insert before closing delimiter
            new_text = (
                text[: delims[1].start()]
                + f"\ntype: {expected_type}"
                + text[delims[1].start() :]
            )
        else:
            new_text = f"---\ntype: {expected_type}\n---\n{text}"

        if not dry_run:
            try:
                note.write_text(new_text, encoding="utf-8")
            except OSError:
                continue

        fixed.append({"path": rel, "added": f"type: {expected_type}"})

    return fixed


# ── Main ──────────────────────────────────────────────────────────────────────


def run_check(vault: pathlib.Path, quick: bool = False) -> LintReport:
    t0 = time.monotonic()
    notes, stem_index, inbound = scan_vault(vault)

    report = LintReport(total_notes=len(notes))
    report.scanned_dirs = [d for d in SCAN_DIRS if (vault / d).is_dir()]
    content_cache: dict[pathlib.Path, str] = {}

    # Always run: frontmatter + broken links (fast)
    broken = build_link_graph(notes, vault, stem_index, inbound, content_cache)
    report.issues.extend(check_frontmatter(notes, vault, content_cache))
    report.issues.extend(check_broken_links(broken))

    if not quick:
        # Full audit adds: orphans, stale, low quality
        report.issues.extend(check_orphan_pages(notes, vault, inbound))
        report.issues.extend(check_stale_notes(notes, vault, inbound))
        report.issues.extend(check_low_quality(notes, vault, content_cache))

    # Sort: high first, then medium, then low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    report.issues.sort(key=lambda i: (severity_order.get(i.severity, 9), i.path))
    report.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return report


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: lint.py {check|quick|fix} [--format json|text] [--dry-run]",
            file=sys.stderr,
        )
        return 0

    subcmd = sys.argv[1]
    vault = get_vault_path()
    if vault is None:
        warn("vault not found — skipping")
        return 0

    if subcmd == "check":
        fmt = "text"
        if "--format" in sys.argv:
            idx = sys.argv.index("--format")
            if idx + 1 < len(sys.argv):
                fmt = sys.argv[idx + 1]
        report = run_check(vault, quick=False)
        if fmt == "json":
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(report.to_text())

    elif subcmd == "quick":
        report = run_check(vault, quick=True)
        # Quick mode: only output if issues found, compact format
        if report.issues:
            print(report.to_text())

    elif subcmd == "fix":
        dry_run = "--dry-run" in sys.argv
        notes, _, _ = scan_vault(vault)
        content_cache: dict[pathlib.Path, str] = {}
        fixed = fix_frontmatter(notes, vault, content_cache, dry_run=dry_run)
        result = {"fixed": fixed, "dry_run": dry_run}
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        warn(f"unknown subcommand: {subcmd}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
