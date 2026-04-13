import pytest
from scripts.distill import is_durable_signal

@pytest.mark.parametrize(
    "line,expected",
    [
        # Empty
        ("", False),

        # Length < 12
        ("short", False),
        ("12345678901", False),

        # Starts with # or > [!
        ("# A heading", False),
        ("> [!info] Some info", False),
        ("> [!warning] warning", False),

        # NOISE_RE matches
        ("ok          ", False),
        ("okay.", False),
        ("yes!", False),
        ("understood!!!", False),
        ("わかりました   ", False),

        # SHELL_NOISE_RE matches
        ("$ python3 script.py", False),
        ("❯ git status --short", False),
        ("> cd dir --some-long-flag", False),
        ("bash(5.1)$ echo hello world", False),
        ("Running test: xyz", False),
        ("Traceback (most recent call last):", False),
        ("Exception: Something went wrong", False),
        ("FAIL: test_something", False),
        # OK matches "OK$" in regex so it strictly has to be OK at end, actually OK$ is line-level OK but len(OK) is 2 < 12 so we can't test it passing SHELL_NOISE_RE with length >= 12 easily. I will omit padding OK.
        ("error: must read the pane correctly", False),
        ("[tmux-bridge error]", False),

        # Valid durable signals (Happy paths)
        ("123456789012", True), # exactly 12 chars
        ("We decided to keep distill.py dry-run and let Claude own writes.", True),
        ("Organizing is the practice of linking resources to activities so all work needed for a goal is assigned.", True),
        ("This is a valid durable signal that should be captured.", True),
        ("Next action: implement tests for distill.py.", True),
    ]
)
def test_is_durable_signal(line, expected):
    assert is_durable_signal(line) is expected
