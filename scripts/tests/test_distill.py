import sys
import pathlib
import pytest

# Add the scripts directory to sys.path to allow importing distill
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from distill import clean_signal

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
