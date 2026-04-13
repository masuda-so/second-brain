import importlib.util
import os
import sys
import pytest
import pathlib
from pathlib import Path
from unittest.mock import MagicMock, patch
import time
import sqlite3

# Load index-vault.py
script_path = Path(__file__).parent.parent / "index-vault.py"
spec = importlib.util.spec_from_file_location("index_vault", script_path)
index_vault = importlib.util.module_from_spec(spec)
sys.modules["index_vault"] = index_vault
spec.loader.exec_module(index_vault)

query_index = index_vault.query_index


# ── build_index tests ────────────────────────────────────────────────────────


def test_build_index_basic(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    # Create an indexed directory and note
    (vault / "Ideas").mkdir()
    note1 = vault / "Ideas" / "Idea1.md"
    note1.write_text("---\ntitle: My Idea\n---\n# My Idea\nSome text.", encoding="utf-8")

    # Create an unindexed directory
    (vault / "Sandbox").mkdir()
    note2 = vault / "Sandbox" / "Sand1.md"
    note2.write_text("Hello", encoding="utf-8")

    # Create a root note (should be skipped)
    root_note = vault / "RootNote.md"
    root_note.write_text("Root", encoding="utf-8")

    stats = index_vault.build_index(vault, incremental=False)

    assert stats["upserted"] == 1
    assert stats["skipped"] == 0
    assert stats["removed"] == 0
    assert stats["total"] == 1

    conn = index_vault.get_db(vault)
    rows = conn.execute("SELECT * FROM vault_index").fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0]["rel_path"] == "Ideas/Idea1"
    assert rows[0]["title"] == "My Idea"


def test_build_index_incremental(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "References").mkdir()

    note1 = vault / "References" / "Ref1.md"
    note1.write_text("---\ntitle: Ref 1\n---\nBody", encoding="utf-8")

    note2 = vault / "References" / "Ref2.md"
    note2.write_text("---\ntitle: Ref 2\n---\nBody", encoding="utf-8")

    stats = index_vault.build_index(vault, incremental=False)
    assert stats["upserted"] == 2

    # Run incremental build with no changes
    stats2 = index_vault.build_index(vault, incremental=True)
    assert stats2["upserted"] == 0
    assert stats2["skipped"] == 2
    assert stats2["removed"] == 0

    # Modify one note, add one note, delete one note
    time.sleep(0.02)  # Ensure mtime difference
    note1.write_text("---\ntitle: Ref 1 Updated\n---\nBody updated", encoding="utf-8")

    note3 = vault / "References" / "Ref3.md"
    note3.write_text("---\ntitle: Ref 3\n---\nBody", encoding="utf-8")

    note2.unlink()

    stats3 = index_vault.build_index(vault, incremental=True)
    assert stats3["upserted"] == 2  # Ref1 and Ref3
    assert stats3["skipped"] == 0
    assert stats3["removed"] == 1  # Ref2
    assert stats3["total"] == 2

    conn = index_vault.get_db(vault)
    rows = conn.execute("SELECT rel_path, title FROM vault_index ORDER BY rel_path").fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0]["rel_path"] == "References/Ref1"
    assert rows[0]["title"] == "Ref 1 Updated"
    assert rows[1]["rel_path"] == "References/Ref3"
    assert rows[1]["title"] == "Ref 3"


def test_build_index_removal_non_incremental(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Projects").mkdir()

    note1 = vault / "Projects" / "Proj1.md"
    note1.write_text("Test", encoding="utf-8")

    index_vault.build_index(vault, incremental=False)

    note1.unlink()

    stats = index_vault.build_index(vault, incremental=False)
    assert stats["upserted"] == 0
    assert stats["skipped"] == 0
    assert stats["removed"] == 1
    assert stats["total"] == 0

    conn = index_vault.get_db(vault)
    count = conn.execute("SELECT COUNT(*) FROM vault_index").fetchone()[0]
    conn.close()
    assert count == 0


def test_build_index_skip_unreadable(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Ideas").mkdir()

    note = vault / "Ideas" / "Unreadable.md"
    note.write_text("test", encoding="utf-8")
    note.chmod(0o000)  # Remove read permissions

    # Skip test if running as root
    if os.geteuid() != 0:
        stats = index_vault.build_index(vault, incremental=False)
        assert stats["upserted"] == 0
        assert stats["total"] == 1

        note.chmod(0o644)


def test_build_index_various_extraction(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Meta").mkdir()
    (vault / "Meta" / "Promotions").mkdir()

    note = vault / "Meta" / "Promotions" / "Promo1.md"
    content = """\
---
title: My Promo
tags: [tag1, tag2]
type: promo_type
---
# Ignored Title
> callout summary!
# Ignored Header
Some body text with [[Link1]] and [[Link2|Alias]]
"""
    note.write_text(content, encoding="utf-8")

    stats = index_vault.build_index(vault, incremental=False)
    assert stats["upserted"] == 1

    conn = index_vault.get_db(vault)
    row = conn.execute("SELECT * FROM vault_index WHERE rel_path = 'Meta/Promotions/Promo1'").fetchone()
    conn.close()

    assert row["title"] == "My Promo"
    assert row["note_type"] == "promo_type"
    assert row["directory"] == "Meta/Promotions"
    assert row["summary"] == "callout summary!"
    assert row["tags"] == "[tag1, tag2]"
    assert row["outbound"] == 2
    assert row["body_chars"] > 0


# ── query_index tests ────────────────────────────────────────────────────────


def test_query_index_empty_keywords():
    """Test that passing an empty list of keywords returns immediately and closes the connection."""
    vault = pathlib.Path("dummy")
    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        result = query_index(vault, [])

        assert result == []
        mock_conn.close.assert_called_once()
        mock_conn.execute.assert_not_called()


def test_query_index_single_keyword():
    """Test that a single keyword properly formats the SQL score and where clauses."""
    vault = pathlib.Path("dummy")
    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"rel_path": "a.md", "title": "A", "note_type": "note"}
        ]

        result = query_index(vault, ["test"])

        assert len(result) == 1
        assert result[0]["title"] == "A"

        mock_conn.execute.assert_called_once()
        args, _ = mock_conn.execute.call_args
        sql, params = args[0], args[1]

        # Verify specific parts of the SQL
        assert "WHERE (title LIKE ? OR summary LIKE ? OR tags LIKE ? OR rel_path LIKE ?)" in sql
        assert "ORDER BY score DESC, body_chars DESC" in sql
        assert "LIMIT ?" in sql

        # Verify the parameter binding
        expected_params = ["%test%"] * 8 + [10]  # 4 for score, 4 for where, 1 for limit
        assert params == expected_params
        mock_conn.close.assert_called_once()


def test_query_index_multiple_keywords():
    """Test that multiple keywords use OR between the where clauses and sum the score parts."""
    vault = pathlib.Path("dummy")
    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        query_index(vault, ["foo", "bar"], limit=5)

        mock_conn.execute.assert_called_once()
        args, _ = mock_conn.execute.call_args
        sql, params = args[0], args[1]

        # Two score parts joined by '+'
        assert " + " in sql.split("AS score")[0]
        # Two where parts joined by 'OR'
        assert "WHERE (title LIKE ? OR summary LIKE ? OR tags LIKE ? OR rel_path LIKE ?) OR (title LIKE ? OR summary LIKE ? OR tags LIKE ? OR rel_path LIKE ?)" in sql

        expected_params = ["%foo%"] * 8 + ["%bar%"] * 8 + [5]
        assert params == expected_params


def test_query_index_respects_limit():
    """Test that the limit parameter correctly affects the SQL limits."""
    vault = pathlib.Path("dummy")
    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        query_index(vault, ["test"], limit=42)

        args, _ = mock_conn.execute.call_args
        params = args[1]
        assert params[-1] == 42  # The limit is the last parameter


def test_query_index_special_characters():
    """Test that special characters in keywords are properly bound using parameters to prevent SQL injection."""
    vault = pathlib.Path("dummy")
    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        # keyword with special SQL characters
        keyword = "test'; DROP TABLE vault_index;--"
        query_index(vault, [keyword], limit=10)

        args, _ = mock_conn.execute.call_args
        sql, params = args[0], args[1]

        # Check that the keyword itself does not appear raw in the SQL query
        assert keyword not in sql

        # Check that it appears in parameters with % wrapped
        expected_bound_value = f"%{keyword}%"
        assert all(p == expected_bound_value for p in params[:-1])


def test_query_index_row_to_dict():
    """Test that the rows returned are correctly mapped into dictionaries."""
    vault = pathlib.Path("dummy")

    # We create a dummy sqlite3 database in memory just to test the Row factory correctly.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE dummy (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO dummy VALUES (1, 'Alice')")
    row = conn.execute("SELECT * FROM dummy").fetchone()

    with patch.object(index_vault, "get_db") as mock_get_db:
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.execute.return_value = mock_cursor

        # Use our real sqlite3.Row
        mock_cursor.fetchall.return_value = [row]

        result = query_index(vault, ["test"])

        assert len(result) == 1
        # The function should convert sqlite3.Row to dict
        assert isinstance(result[0], dict)
        assert result[0] == {"id": 1, "name": "Alice"}

    conn.close()


# ── scan_note tests ──────────────────────────────────────────────────────────


def test_scan_note_skip(tmp_path):
    vault = tmp_path

    # Create a note in a skipped directory
    trash_dir = vault / ".trash"
    trash_dir.mkdir()
    skipped_note = trash_dir / "skipped.md"
    skipped_note.write_text("Hello")

    assert index_vault.scan_note(skipped_note, vault) is None

    # Create a note in an unindexed directory
    unindexed_dir = vault / "Unindexed"
    unindexed_dir.mkdir()
    unindexed_note = unindexed_dir / "unindexed.md"
    unindexed_note.write_text("Hello")

    assert index_vault.scan_note(unindexed_note, vault) is None


def test_scan_note_oserror(tmp_path):
    vault = tmp_path

    # Note in a valid indexed directory but file is missing (raises OSError)
    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    missing_note = ideas_dir / "missing.md"

    assert index_vault.scan_note(missing_note, vault) is None


def test_scan_note_oserror_read_text(monkeypatch):
    """Test that scan_note gracefully handles an OSError when reading text."""
    vault = pathlib.Path("/dummy/vault")
    note = vault / "References" / "test.md"

    def mock_read_text(*args, **kwargs):
        raise OSError("Mocked OSError in read_text")

    monkeypatch.setattr(pathlib.Path, "read_text", mock_read_text)

    result = index_vault.scan_note(note, vault)
    assert result is None


def test_scan_note_oserror_stat(monkeypatch):
    """Test that scan_note gracefully handles an OSError when accessing stat()."""
    vault = pathlib.Path("/dummy/vault")
    note = vault / "References" / "test.md"

    def mock_read_text(*args, **kwargs):
        return "some text"

    def mock_stat(*args, **kwargs):
        raise OSError("Mocked OSError in stat")

    monkeypatch.setattr(pathlib.Path, "read_text", mock_read_text)
    monkeypatch.setattr(pathlib.Path, "stat", mock_stat)

    result = index_vault.scan_note(note, vault)
    assert result is None


def test_scan_note_happy_path(tmp_path):
    vault = tmp_path
    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    valid_note = ideas_dir / "good_idea.md"

    valid_note.write_text("""\
---
title: My Good Idea
type: idea
tags: test, idea
---
# Welcome to my idea

This is a very good idea that will change the world.
It has a [[Link to another note]] and [[Another link]].
""")

    res = index_vault.scan_note(valid_note, vault)

    assert res is not None
    assert res["rel_path"] == "Ideas/good_idea"
    assert res["title"] == "My Good Idea"
    assert res["note_type"] == "idea"
    assert res["directory"] == "Ideas"
    assert "very good idea" in res["summary"]
    assert "test, idea" in res["tags"]
    assert "body_chars" in res
    assert res["body_chars"] == 107
    assert res["outbound"] == 2
    assert "updated_at" in res
    assert "mtime" in res
