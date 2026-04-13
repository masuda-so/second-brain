import sys
import pathlib
import pytest

# Add the scripts directory to sys.path to allow importing distill
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from distill import clean_signal, is_durable_signal, slugify

@pytest.mark.parametrize("input_line, expected", [
    # Basic cases
    ("hello world", "hello world"),
    ("  hello world  ", "hello world"),
    ("hello    world", "hello world"),

    # Bullet points
    ("- hello world", "hello world"),
    ("* hello world", "hello world"),
    ("+ hello world", "hello world"),
    ("-hello world", "hello world"),
    ("  -  hello world", "hello world"),

    # Numbered lists
    ("1. hello world", "hello world"),
    ("123. hello world", "hello world"),
    ("1.hello world", "hello world"),
    ("  42.  hello world", "hello world"),

    # Checkboxes
    ("[ ] hello world", "hello world"),
    ("[x] hello world", "hello world"),
    ("[X] hello world", "hello world"),
    ("[ ]hello world", "hello world"),
    ("  [x]   hello world", "hello world"),

    # Combined cases (applied in order: bullet, then number, then checkbox)
    ("- [ ] hello world", "hello world"),
    ("* [x] hello world", "hello world"),
    ("1. [X] hello world", "hello world"),
    ("- 1. hello world", "hello world"),

    # Edge cases
    ("", ""),
    ("   ", ""),
    ("-", ""),
    ("1.", ""),
    ("[ ]", ""),
    ("---", "--"), # Only one - removed by bullet regex
])
def test_clean_signal(input_line, expected):
    assert clean_signal(input_line) == expected


@pytest.mark.parametrize(
    "line,expected",
    [
        # Empty
        ("", False),

        # Length < 12
        ("short", False),
        ("12345678901", False),

        # Starts with # or > [!
        ("# A heading that is long enough", False),
        ("> [!info] Some info", False),
        ("> [!warning] warning", False),

        # NOISE_RE matches
        ("ok          ", False),
        ("okay.", False),
        ("yes!", False),
        ("understood!!!", False),

        # SHELL_NOISE_RE matches
        ("$ python3 script.py", False),
        ("Running test: xyz", False),
        ("Traceback (most recent call last):", False),
        ("Exception: Something went wrong", False),
        ("FAIL: test_something", False),
        ("error: must read the pane correctly", False),
        ("[tmux-bridge error]", False),

        # Valid durable signals (Happy paths)
        ("123456789012", True),
        ("We decided to keep distill.py dry-run and let Claude own writes.", True),
        ("This is a valid durable signal that should be captured.", True),
        ("Next action: implement tests for distill.py.", True),
    ]
)
def test_is_durable_signal(line, expected):
    assert is_durable_signal(line) is expected


# slugify tests

def test_slugify_normal_text():
    assert slugify("Hello World") == "hello-world"

def test_slugify_empty_string():
    assert slugify("") == "note"

def test_slugify_only_special_chars():
    assert slugify("@#$%^&*") == "note"

def test_slugify_mixed_spacing_and_underscores():
    assert slugify("  test_ _string-  ") == "test-string"

def test_slugify_non_alphanumeric_removal():
    assert slugify("test@#$string") == "teststring"

def test_slugify_long_string():
    long_string = "a" * 100
    assert len(slugify(long_string)) == 80
    assert slugify(long_string) == "a" * 80

def test_slugify_long_string_with_hyphens():
    long_string = "a " * 50
    slug = slugify(long_string)
    assert len(slug) <= 80
    assert slug.startswith("a-a-")

def test_slugify_trims_hyphens():
    assert slugify("-hello-world-") == "hello-world"
