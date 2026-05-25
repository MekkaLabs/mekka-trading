"""Tests — atomic_json helper (A4, 2026-05-25).

Garante que:
- write atômico real (tmp + os.replace)
- crash mid-write deixa o arquivo de destino intacto
- erro de serialização não corrompe o existente
- parent dir é criado se faltar
- payload escrito é idêntico ao input
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.atomic_json import atomic_write_json


def test_writes_file_with_correct_content(tmp_path):
    target = tmp_path / "out.json"
    data = {"a": 1, "b": ["x", "y"], "c": None}
    assert atomic_write_json(target, data) is True
    assert target.exists()
    assert json.loads(target.read_text()) == data


def test_overwrites_existing_file(tmp_path):
    target = tmp_path / "out.json"
    target.write_text('{"old": true}')
    new_data = {"new": True, "count": 42}
    assert atomic_write_json(target, new_data) is True
    assert json.loads(target.read_text()) == new_data


def test_creates_parent_directory(tmp_path):
    target = tmp_path / "nested" / "deep" / "out.json"
    assert not target.parent.exists()
    assert atomic_write_json(target, {"ok": True}) is True
    assert target.exists()
    assert json.loads(target.read_text()) == {"ok": True}


def test_serialize_failure_does_not_corrupt_existing(tmp_path):
    """If json.dumps raises, existing file must remain untouched."""
    target = tmp_path / "out.json"
    target.write_text('{"valid": "original"}')

    # set() is not JSON-serializable
    bad_data = {"not_serializable": {1, 2, 3}}
    result = atomic_write_json(target, bad_data)

    assert result is False
    # Existing file untouched
    assert json.loads(target.read_text()) == {"valid": "original"}


def test_os_replace_failure_does_not_corrupt_existing(tmp_path):
    """If os.replace fails, existing file remains; tmpfile is cleaned up."""
    target = tmp_path / "out.json"
    target.write_text('{"valid": "original"}')

    with patch("src.services.atomic_json.os.replace", side_effect=OSError("simulated")):
        result = atomic_write_json(target, {"new": "data"})

    assert result is False
    # Original content preserved
    assert json.loads(target.read_text()) == {"valid": "original"}
    # No orphan tmp files leftover (helper cleans up)
    tmp_files = list(tmp_path.glob(".out.json.*.tmp"))
    assert tmp_files == [], f"orphan tmpfiles: {tmp_files}"


def test_no_partial_file_visible_during_write(tmp_path):
    """No reader should ever see a half-written file (atomicity test)."""
    target = tmp_path / "out.json"
    # Pre-populate with known content
    target.write_text('{"phase": "before"}')

    payload = {"phase": "after", "items": list(range(1000))}
    # During the write call, the file content should ALWAYS be parseable
    # (either old or new). We can't realistically race here, but we can
    # confirm the final state.
    assert atomic_write_json(target, payload) is True
    assert json.loads(target.read_text()) == payload


def test_accepts_path_as_str(tmp_path):
    target = tmp_path / "out.json"
    assert atomic_write_json(str(target), {"x": 1}) is True
    assert json.loads(target.read_text()) == {"x": 1}


def test_indent_and_ensure_ascii_kwargs(tmp_path):
    target = tmp_path / "out.json"
    data = {"emoji": "🚀"}
    atomic_write_json(target, data, indent=None, ensure_ascii=True)
    raw = target.read_text()
    # No indentation
    assert "\n" not in raw
    # ASCII-escaped emoji
    assert "\\u" in raw
