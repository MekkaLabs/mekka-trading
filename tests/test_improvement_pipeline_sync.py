"""Tests — T2 pipeline sync: brief.md ↔ pr_tracker stay consistent (2026-05-25).

Background: briefs were written with ``status: queued`` HARDCODED in YAML
and never reflected actual progress in pr_tracker. 23 of 25 accepted
recommendations were dead letters. Sync closes the gap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services import improvement_queue, pr_tracker


@pytest.fixture
def temp_paths(tmp_path, monkeypatch):
    """Redirect all file paths to a temp dir so tests don't touch real data."""
    queue_dir = tmp_path / "docs" / "improvement-queue"
    data_dir = tmp_path / "data"
    queue_dir.mkdir(parents=True)
    data_dir.mkdir()

    monkeypatch.setattr(improvement_queue, "_QUEUE_DIR", queue_dir)
    monkeypatch.setattr(improvement_queue, "_DATA_DIR", data_dir)
    monkeypatch.setattr(improvement_queue, "_INDEX_FILE", data_dir / "improvement_queue.json")
    monkeypatch.setattr(pr_tracker, "_DATA_DIR", data_dir)
    monkeypatch.setattr(pr_tracker, "_PRS_FILE", data_dir / "improvement_prs.json")
    monkeypatch.setattr(pr_tracker, "_gh_available", lambda: False)
    return {"queue_dir": queue_dir, "data_dir": data_dir}


def _seed_brief(rec_id: str = "TEST123") -> dict:
    return {
        "id": rec_id,
        "title": "Test improvement",
        "description": "synthetic",
        "impact": "LOW",
        "area": "infra",
        "priority": "P3",
        "domain": "dev-squad",
    }


def test_enqueue_then_claim_updates_brief_yaml(temp_paths):
    """End-to-end: enqueue brief → claim → YAML reflects in_dev."""
    rec = _seed_brief("ABCDEF")
    path_str = improvement_queue.enqueue_brief(rec)
    assert path_str

    brief_path = temp_paths["queue_dir"] / "IMP-ABCDEF.md"
    assert "status: queued" in brief_path.read_text()

    r = pr_tracker.claim_brief("ABCDEF", claimer="alice")
    assert r["ok"]
    assert r["dev_state"] == "in_dev"

    # Brief YAML now reflects in_dev
    new_content = brief_path.read_text()
    assert "status: in_dev" in new_content
    assert "status: queued" not in new_content

    # Index updated
    index = json.loads((temp_paths["data_dir"] / "improvement_queue.json").read_text())
    assert index["ABCDEF"]["dev_state"] == "in_dev"
    assert index["ABCDEF"]["claimer"] == "alice"

    # PR store updated
    prs = json.loads((temp_paths["data_dir"] / "improvement_prs.json").read_text())
    assert prs["ABCDEF"]["dev_state"] == "in_dev"


def test_set_pr_updates_brief_to_pr_open(temp_paths):
    """When PR is created, brief should transition to pr_open."""
    improvement_queue.enqueue_brief(_seed_brief("PR001"))
    brief_path = temp_paths["queue_dir"] / "IMP-PR001.md"

    r = pr_tracker.set_pr(
        rec_id="PR001",
        pr_number=42,
        branch="feat/test",
        summary="test PR",
    )
    assert r["ok"]
    assert "status: pr_open" in brief_path.read_text()


def test_mark_merged_updates_brief_to_merged(temp_paths):
    """When PR is merged, brief should transition to merged."""
    improvement_queue.enqueue_brief(_seed_brief("MRG001"))
    brief_path = temp_paths["queue_dir"] / "IMP-MRG001.md"

    pr_tracker.set_pr(rec_id="MRG001", pr_number=99, branch="b", summary="s")
    pr_tracker.mark_merged("MRG001")
    assert "status: merged" in brief_path.read_text()


def test_claim_idempotent_on_advanced_states(temp_paths):
    """claim_brief should not downgrade pr_open or merged back to in_dev."""
    improvement_queue.enqueue_brief(_seed_brief("IDEMP1"))
    pr_tracker.set_pr(rec_id="IDEMP1", pr_number=7, branch="b", summary="s")
    # Now try to claim — should be no-op
    r = pr_tracker.claim_brief("IDEMP1", claimer="bob")
    assert r["ok"]
    assert r["dev_state"] == "pr_open"  # unchanged, not downgraded
    assert "note" in r


def test_update_brief_status_skips_phantom_ids(temp_paths):
    """update_brief_status for an ID without brief/entry should NOT create phantom index entry."""
    r = improvement_queue.update_brief_status("GHOST_ID", "in_dev")
    # Brief doesn't exist → not updated. Index also doesn't get a new entry.
    assert r["brief_updated"] is False
    assert r["index_updated"] is False
    # Confirm no phantom entry was written
    idx_path = temp_paths["data_dir"] / "improvement_queue.json"
    if idx_path.exists():
        index = json.loads(idx_path.read_text())
        assert "GHOST_ID" not in index


def test_update_brief_status_invalid_state_rejected(temp_paths):
    r = improvement_queue.update_brief_status("ANY", "bogus_state")
    assert r["ok"] is False
    assert "invalid status" in r["error"]


def test_invalid_id_rejected(temp_paths):
    assert improvement_queue.update_brief_status("", "in_dev")["ok"] is False
    assert pr_tracker.claim_brief("", claimer="x")["ok"] is False
