import pytest
import sys
import pathlib

# Add the scripts directory to the python path to import the module
REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
scripts_dir = REPO_ROOT / "scripts"
sys.path.insert(0, str(scripts_dir))

# Import the module as validate_template_vault
import importlib.util
spec = importlib.util.spec_from_file_location("validate_template_vault", scripts_dir / "validate-template-vault.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


def test_parse_frontmatter_keys_valid():
    """Test parsing a typical valid YAML frontmatter."""
    body = """---
type: idea
status: incubating
created: 2024-05-20
tags:
  - test
---
# Some title
content goes here.
"""
    keys = validate.parse_frontmatter_keys(body)
    assert keys == {"type", "status", "created", "tags"}

def test_parse_frontmatter_keys_missing():
    """Test parsing a string without YAML frontmatter."""
    body = """# Some title
content goes here without frontmatter.
"""
    keys = validate.parse_frontmatter_keys(body)
    assert keys == set()

def test_parse_frontmatter_keys_empty():
    """Test parsing an empty YAML frontmatter."""
    body = """---
---
# Some title
content goes here.
"""
    keys = validate.parse_frontmatter_keys(body)
    assert keys == set()

def test_parse_frontmatter_keys_with_whitespace():
    """Test parsing YAML frontmatter keys with weird spacing."""
    body = """---
  type  :   project
status:review
---
# Some title
"""
    # The current regex `^(\w+)\s*:` requires no leading spaces
    # It might only pick up status based on `^` regex constraint
    keys = validate.parse_frontmatter_keys(body)
    assert keys == {"status"}

def test_parse_headings_multiple_levels():
    """Test extracting headings of various levels."""
    body = """# Main Title
Some text here.
## Subtitle 1
More text.
### Sub-subtitle
Even more text.
## Subtitle 2
Final text.
"""
    headings = validate.parse_headings(body)
    assert headings == ["Main Title", "Subtitle 1", "Sub-subtitle", "Subtitle 2"]

def test_parse_headings_ignore_text():
    """Test that normal text is ignored."""
    body = """Just some text with no headings at all.
It has multiple lines.
And some punctuation!
"""
    headings = validate.parse_headings(body)
    assert headings == []

def test_parse_headings_ignore_fake_headings():
    """Test ignoring text that looks similar to headings but isn't."""
    body = """#This is not a heading (no space)
##Also not a heading
  # Not a heading (leading spaces)
Here is a #hashtag mid-sentence.
"""
    headings = validate.parse_headings(body)
    assert headings == []
