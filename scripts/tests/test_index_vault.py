import sys
import pathlib
import pytest
from unittest.mock import MagicMock, patch
import sqlite3

# Add scripts directory to sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import importlib.util
spec = importlib.util.spec_from_file_location("index_vault", str(pathlib.Path(__file__).parent.parent / "index-vault.py"))
index_vault = importlib.util.module_from_spec(spec)
sys.modules["index_vault"] = index_vault
spec.loader.exec_module(index_vault)

query_index = index_vault.query_index

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
        expected_params = ["%test%"] * 8 + [10] # 4 for score, 4 for where, 1 for limit
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
        assert params[-1] == 42 # The limit is the last parameter

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
