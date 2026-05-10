import importlib.util
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

# Load harvest.py
script_path = Path(__file__).parent.parent / "harvest.py"
spec = importlib.util.spec_from_file_location("harvest", script_path)
harvest = importlib.util.module_from_spec(spec)
sys.modules["harvest"] = harvest
spec.loader.exec_module(harvest)

def test_extract_session_id_from_event_session_id():
    event = {"session_id": "test-session"}
    assert harvest.extract_session_id(event) == "test-session"

def test_extract_session_id_from_event_sessionId_fallback():
    event = {"sessionId": "test-session-camel"}
    assert harvest.extract_session_id(event) == "test-session-camel"

def test_extract_session_id_from_env_claude_session_id():
    with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "env-session"}):
        # Ensure other env vars don't interfere
        if "CLAUDE_CODE_SESSION_ID" in os.environ:
            del os.environ["CLAUDE_CODE_SESSION_ID"]
        assert harvest.extract_session_id({}) == "env-session"

def test_extract_session_id_from_env_claude_code_session_id_fallback():
    with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "code-env-session"}):
        # Ensure CLAUDE_SESSION_ID is not present
        with patch.dict(os.environ, {}):
            if "CLAUDE_SESSION_ID" in os.environ:
                del os.environ["CLAUDE_SESSION_ID"]
            assert harvest.extract_session_id({}) == "code-env-session"

def test_extract_session_id_default_unknown():
    with patch.dict(os.environ, {}, clear=True):
        assert harvest.extract_session_id({}) == "unknown-session"

def test_extract_session_id_normalization():
    event = {"session_id": "session/with/slashes and spaces!!!"}
    # Expected: "session-with-slashes-and-spaces"
    # Logic: re.sub(r"[^A-Za-z0-9._-]", "-", str(raw)).strip("-")
    assert harvest.extract_session_id(event) == "session-with-slashes-and-spaces"

def test_extract_session_id_priority():
    event = {"session_id": "event-session"}
    with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "env-session"}):
        assert harvest.extract_session_id(event) == "event-session"

def test_extract_session_id_empty_after_normalization():
    event = {"session_id": "!!!"}
    assert harvest.extract_session_id(event) == "unknown-session"

def test_extract_session_id_non_string_input():
    event = {"session_id": 12345}
    assert harvest.extract_session_id(event) == "12345"
