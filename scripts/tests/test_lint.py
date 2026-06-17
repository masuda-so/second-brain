import importlib.util
import pathlib
import sys
from pathlib import Path

# Load lint.py
script_path = Path(__file__).parent.parent / "lint.py"
spec = importlib.util.spec_from_file_location("lint", script_path)
lint = importlib.util.module_from_spec(spec)
sys.modules["lint"] = lint
spec.loader.exec_module(lint)

def test_parse_frontmatter_basic():
    text = "---\ntype: idea\nstatus: pending\n---\nBody text"
    fm = lint.parse_frontmatter(text)
    assert fm == {"type": "idea", "status": "pending"}

def test_parse_frontmatter_indented():
    # Test case mentioned in docstring: harvest.py output with leading spaces
    text = "  ---\n  type: reference\n  topic: testing\n  ---\nBody"
    fm = lint.parse_frontmatter(text)
    assert fm == {"type": "reference", "topic": "testing"}

def test_parse_frontmatter_no_fm():
    assert lint.parse_frontmatter("No frontmatter here") == {}
    assert lint.parse_frontmatter("---\nOnly one delimiter") == {}

def test_parse_frontmatter_not_at_start():
    text = "Some text before\n---\ntype: idea\n---\nBody"
    assert lint.parse_frontmatter(text) == {}

def test_parse_frontmatter_quotes_and_whitespace():
    text = "---\nkey1: \"value1\"\nkey2: 'value2'\nkey3:    value3   \n---\n"
    fm = lint.parse_frontmatter(text)
    assert fm == {"key1": "value1", "key2": "value2", "key3": "value3"}

def test_infer_type_from_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    note = ideas_dir / "note.md"

    assert lint.infer_type_from_dir(note, vault) == "idea"

    unknown_dir = vault / "Unknown"
    unknown_dir.mkdir()
    note2 = unknown_dir / "note.md"
    assert lint.infer_type_from_dir(note2, vault) is None

def test_check_frontmatter_happy_path(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ref_dir = vault / "References"
    ref_dir.mkdir()
    note = ref_dir / "ref1.md"
    content = "---\ntype: reference\ntopic: coding\n---\nBody"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)
    assert len(issues) == 0

def test_check_frontmatter_missing_type(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    note = ideas_dir / "idea1.md"
    # No frontmatter at all, but in Ideas/ so type should be inferred as 'idea'
    content = "Just some body"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)

    assert len(issues) == 1
    assert issues[0].check == "frontmatter"
    assert issues[0].severity == "medium"
    assert "type" in issues[0].message
    assert "status" in issues[0].message # 'idea' requires type and status
    assert issues[0].fixable is True # because 'type' is missing

def test_check_frontmatter_missing_required_field(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    note = ideas_dir / "idea1.md"
    # Has type, but missing 'status'
    content = "---\ntype: idea\n---\nBody"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)

    assert len(issues) == 1
    assert issues[0].check == "frontmatter"
    assert issues[0].severity == "low"
    assert "status" in issues[0].message
    assert "type" not in issues[0].message
    assert issues[0].fixable is False # 'type' is present, other field missing is not 'fixable' by lint fix

def test_check_frontmatter_empty_field(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ref_dir = vault / "References"
    ref_dir.mkdir()
    note = ref_dir / "ref1.md"
    # topic is empty
    content = "---\ntype: reference\ntopic: \n---\nBody"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)

    assert len(issues) == 1
    assert "topic" in issues[0].message

def test_check_frontmatter_skip_promotions(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    promo_dir = vault / "Meta" / "Promotions"
    promo_dir.mkdir(parents=True)
    note = promo_dir / "promo1.md"
    content = "No frontmatter"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)
    assert len(issues) == 0

def test_check_frontmatter_unknown_type(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    misc_dir = vault / "Misc"
    misc_dir.mkdir()
    note = misc_dir / "misc1.md"
    content = "No frontmatter"

    cache = {note: content}
    issues = lint.check_frontmatter([note], vault, cache)
    assert len(issues) == 0 # Cannot determine type, so skips
