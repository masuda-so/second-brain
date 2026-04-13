import importlib.util
import pathlib
import sys
import pytest

# Dynamically import the script since it has a hyphen in the name
spec = importlib.util.spec_from_file_location("index_vault", "scripts/index-vault.py")
index_vault = importlib.util.module_from_spec(spec)
sys.modules["index_vault"] = index_vault
spec.loader.exec_module(index_vault)

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

def test_scan_note_happy_path(tmp_path):
    vault = tmp_path
    ideas_dir = vault / "Ideas"
    ideas_dir.mkdir()
    valid_note = ideas_dir / "good_idea.md"

    valid_note.write_text("""---
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
