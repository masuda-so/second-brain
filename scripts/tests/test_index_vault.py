import pytest
import pathlib
import sys
import os
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load index-vault.py which is not a proper python module name due to the dash
spec = importlib.util.spec_from_file_location("index_vault", os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index-vault.py')))
index_vault = importlib.util.module_from_spec(spec)
sys.modules["index_vault"] = index_vault
spec.loader.exec_module(index_vault)

def test_scan_note_oserror_read_text(monkeypatch):
    """Test that scan_note gracefully handles an OSError when reading text."""
    vault = pathlib.Path("/dummy/vault")
    # Simulate a note that passes should_skip and should_index checks
    note = vault / "References" / "test.md"

    def mock_read_text(*args, **kwargs):
        raise OSError("Mocked OSError in read_text")

    monkeypatch.setattr(pathlib.Path, "read_text", mock_read_text)

    result = index_vault.scan_note(note, vault)
    assert result is None

def test_scan_note_oserror_stat(monkeypatch):
    """Test that scan_note gracefully handles an OSError when accessing stat()."""
    vault = pathlib.Path("/dummy/vault")
    # Simulate a note that passes should_skip and should_index checks
    note = vault / "References" / "test.md"

    def mock_read_text(*args, **kwargs):
        return "some text"

    def mock_stat(*args, **kwargs):
        raise OSError("Mocked OSError in stat")

    monkeypatch.setattr(pathlib.Path, "read_text", mock_read_text)
    monkeypatch.setattr(pathlib.Path, "stat", mock_stat)

    result = index_vault.scan_note(note, vault)
    assert result is None
