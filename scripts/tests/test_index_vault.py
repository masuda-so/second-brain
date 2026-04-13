import importlib.util
import sys
import pytest
from pathlib import Path
import time
import sqlite3

# Load index-vault.py
script_path = Path(__file__).parent.parent / "index-vault.py"
spec = importlib.util.spec_from_file_location("index_vault", script_path)
index_vault = importlib.util.module_from_spec(spec)
sys.modules["index_vault"] = index_vault
spec.loader.exec_module(index_vault)

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
    time.sleep(0.02) # Ensure mtime difference
    note1.write_text("---\ntitle: Ref 1 Updated\n---\nBody updated", encoding="utf-8")

    note3 = vault / "References" / "Ref3.md"
    note3.write_text("---\ntitle: Ref 3\n---\nBody", encoding="utf-8")

    note2.unlink()

    stats3 = index_vault.build_index(vault, incremental=True)
    assert stats3["upserted"] == 2 # Ref1 and Ref3
    assert stats3["skipped"] == 0
    assert stats3["removed"] == 1 # Ref2
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
    note.chmod(0o000) # Remove read permissions

    # Needs to be tested but let's avoid issues depending on how permissions work in docker
    # Skip test logic inside if running as root
    import os
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
    content = """---
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
