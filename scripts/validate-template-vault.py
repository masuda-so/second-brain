#!/usr/bin/env python3
"""
validate-template-vault.py
===========================
Checks that harvest.py-generated note schemas are consistent with the
canonical Template-Vault structure defined in CLAUDE.md.

Validates two things:
  1. The template definitions inside init.sh (Templates/ sync section)
     have correct YAML frontmatter keys and required headings.
  2. The note-creation code in harvest.py produces frontmatter fields
     that match the canonical schema.

Exits 0 if all checks pass, 1 if any fail.
"""

import re
import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent

# ── Canonical schema (from CLAUDE.md) ────────────────────────────────────────

SCHEMA: dict[str, dict] = {
    "daily": {
        "required_frontmatter": ["type", "date", "tags"],
        "required_headings": [
            "今日のフォーカス", "メモ", "フォローアップ", "関連ノート", "AI Session"
        ],
    },
    "weekly": {
        "required_frontmatter": ["type", "week", "reviewed", "tags"],
        "required_headings": [
            "進行中プロジェクト", "昇格候補アイデア", "ブロッカー", "来週の重点", "関連ノート"
        ],
    },
    "monthly": {
        "required_frontmatter": ["type", "period", "tags"],
        "required_headings": [
            "優先事項", "うまくいったこと", "改善点", "来月の焦点", "関連ノート"
        ],
    },
    "idea": {
        "required_frontmatter": ["type", "status", "created", "tags"],
        "required_headings": ["プロジェクト化の条件", "下書き素材"],
    },
    "reference": {
        "required_frontmatter": ["type", "topic"],
        "required_headings": ["目的", "手順", "関連資料"],
    },
    "project": {
        "required_frontmatter": ["type", "status", "review", "tags"],
        "required_headings": ["ゴール", "次のアクション", "添付", "関連ノート"],
    },
    "clipping": {
        "required_frontmatter": ["type", "source", "captured"],
        "required_headings": ["メモ"],
    },
}

errors: list[str] = []
checks: int = 0


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    global checks
    checks += 1
    print(f"  ok    {msg}")


# ── 1. Validate init.sh template sync section ────────────────────────────────

def extract_templates_from_init() -> dict[str, str]:
    """Extract template bodies from init.sh heredocs."""
    init_sh = REPO_ROOT / "scripts" / "init.sh"
    if not init_sh.exists():
        fail("scripts/init.sh not found")
        return {}

    text = init_sh.read_text()
    # Match: sync_template "NAME.md" <<'TMPL'\n...\nTMPL
    pattern = re.compile(
        r'sync_template\s+"([^"]+\.md)"\s+<<\'TMPL\'\n(.*?)\nTMPL',
        re.DOTALL,
    )
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}


def parse_frontmatter_keys(body: str) -> set[str]:
    """Extract YAML frontmatter keys from a markdown string."""
    fm_match = re.match(r"^---\n(.*?)\n---", body, re.DOTALL)
    if not fm_match:
        return set()
    keys = set()
    for line in fm_match.group(1).splitlines():
        key_match = re.match(r"^(\w+)\s*:", line)
        if key_match:
            keys.add(key_match.group(1))
    return keys


def parse_headings(body: str) -> list[str]:
    """Extract ## heading text from a markdown string."""
    return [
        re.sub(r"^#+\s*", "", line).strip()
        for line in body.splitlines()
        if re.match(r"^#{1,3}\s+", line)
    ]


def check_template(name: str, body: str, note_type: str) -> None:
    schema = SCHEMA.get(note_type)
    if not schema:
        return  # no schema defined for this type, skip

    keys = parse_frontmatter_keys(body)
    headings = parse_headings(body)
    headings_flat = " ".join(headings)

    print(f"\n  [{name}]")
    for key in schema["required_frontmatter"]:
        if key in keys:
            ok(f"frontmatter has '{key}'")
        else:
            fail(f"frontmatter missing '{key}' (template: {name})")

    for heading in schema["required_headings"]:
        if heading in headings_flat:
            ok(f"heading '## {heading}' present")
        else:
            fail(f"heading '## {heading}' missing (template: {name})")


print("=== Template-Vault Compatibility Check ===\n")
print("-- init.sh template definitions")

templates = extract_templates_from_init()
if templates:
    # Map filename → type
    type_map = {
        "daily.md": "daily", "weekly.md": "weekly", "monthly.md": "monthly",
        "project.md": "project", "idea.md": "idea",
        "reference.md": "reference", "clipping.md": "clipping",
    }
    for fname, body in templates.items():
        note_type = type_map.get(fname)
        if note_type:
            check_template(fname, body, note_type)
else:
    fail("No sync_template definitions found in init.sh")


# ── 2. Validate harvest.py note creation schemas ─────────────────────────────

print("\n-- harvest.py note schemas")

harvest_py = REPO_ROOT / "scripts" / "harvest.py"
if not harvest_py.exists():
    fail("scripts/harvest.py not found")
else:
    text = harvest_py.read_text()

    # Ideas/ format: must have type, status, created, tags, harvest_source
    idea_fields = ["type: idea", "status: incubating", "created:", "tags:", "harvest_source:"]
    print("\n  [Ideas/ format in harvest.py]")
    for field in idea_fields:
        if field in text:
            ok(f"'{field}' present in create_note()")
        else:
            fail(f"'{field}' missing from create_note() — Ideas/ notes will be non-compliant")

    # Ideas/ headings
    idea_headings = ["プロジェクト化の条件", "下書き素材"]
    for heading in idea_headings:
        if heading in text:
            ok(f"'## {heading}' present in create_note()")
        else:
            fail(f"'## {heading}' missing from create_note()")

    # Reference stubs: must have type, topic, created
    ref_fields = ["type: reference", "topic:", "created:"]
    print("\n  [References/ stub format in harvest.py]")
    for field in ref_fields:
        if field in text:
            ok(f"'{field}' present in reference stub")
        else:
            fail(f"'{field}' missing from reference stub")

    # Reference headings
    ref_headings = ["目的", "手順", "関連資料"]
    for heading in ref_headings:
        if heading in text:
            ok(f"'## {heading}' present in reference stub")
        else:
            fail(f"'## {heading}' missing from reference stub")

    # Weekly/Monthly: check _maybe_create_periodic_notes
    print("\n  [Weekly/Monthly format in harvest.py]")
    weekly_fields = ["type: weekly", "week:", "reviewed:", "planning"]
    for field in weekly_fields:
        if field in text:
            ok(f"'{field}' present in periodic notes")
        else:
            fail(f"'{field}' missing from periodic notes")

    monthly_fields = ["type: monthly", "period:", "monthly"]
    for field in monthly_fields:
        if field in text:
            ok(f"'{field}' present in periodic notes")
        else:
            fail(f"'{field}' missing from periodic notes")


# ── Result ────────────────────────────────────────────────────────────────────

print(f"\n=== Result: {checks} passed, {len(errors)} failed ===\n")
if errors:
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
