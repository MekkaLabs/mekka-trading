"""
tests/test_improvement_memory_bridge.py
=========================================
Cobertura do service improvement_memory_bridge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.improvement_memory_bridge import (
    _IMP_TAG_RE,
    _score_match,
    find_match_candidates,
    memory_snapshot,
)


class TestImpTagRegex:
    def test_matches_valid_tag(self) -> None:
        assert _IMP_TAG_RE.findall("feat(x): hello [IMP-abc123def456]") == ["abc123def456"]

    def test_multiple_tags(self) -> None:
        text = "feat: [IMP-aaa111bbb222] and [IMP-ccc333ddd444]"
        assert len(_IMP_TAG_RE.findall(text)) == 2

    def test_no_match_short(self) -> None:
        # 12 hex chars exatos — 11 não conta
        assert _IMP_TAG_RE.findall("[IMP-abc123def45]") == []


class TestScoreMatch:
    def test_no_keywords_zero(self) -> None:
        commit = {"subject": "foo", "body": "bar", "files": []}
        assert _score_match(commit, [], "") == 0.0

    def test_high_keyword_coverage(self) -> None:
        commit = {
            "subject": "feat: implement memory hub panel",
            "body": "",
            "files": ["src/dashboard/static/memory_hub.js"],
        }
        score = _score_match(commit, ["memory", "hub", "panel"], "")
        assert score >= 0.5

    def test_file_path_bonus(self) -> None:
        brief = "Should touch `src/agents/foo.py`"
        commit = {
            "subject": "fix: foo",
            "body": "",
            "files": ["src/agents/foo.py"],
        }
        score = _score_match(commit, ["foo"], brief)
        # Coverage + file bonus = should be higher than coverage alone
        assert score > 0.7


class TestMemorySnapshot:
    def test_returns_required_keys(self) -> None:
        snap = memory_snapshot()
        assert "ts" in snap
        assert "layers" in snap
        assert "layers_healthy" in snap
        assert "layers_total" in snap
        assert "bridge" in snap

    def test_all_6_layers_present(self) -> None:
        snap = memory_snapshot()
        expected = {
            "agent_memory", "decision_memory", "signal_outcome_memory",
            "role_working_memory", "cycle_conversation_memory", "vault_context",
        }
        assert set(snap["layers"].keys()) == expected

    def test_each_layer_has_available_field(self) -> None:
        snap = memory_snapshot()
        for name, layer in snap["layers"].items():
            assert "available" in layer, f"{name} sem 'available'"

    def test_bridge_metadata_shape(self) -> None:
        snap = memory_snapshot()
        b = snap["bridge"]
        for k in ("improvements_with_before", "improvements_with_after", "improvements_tracked"):
            assert k in b
            assert isinstance(b[k], int)


class TestFindMatchCandidates:
    def test_returns_list(self, tmp_path: Path) -> None:
        # rec_id inválido → vazio (não lança)
        result = find_match_candidates("nonexistent_id_zzz", top_n=5)
        assert isinstance(result, list)

    def test_top_n_respected(self) -> None:
        # mesmo se houver muitos matches, respeita top_n
        # (testando com rec_id real do queue se possível)
        import json
        try:
            queue = json.loads(Path("data/improvement_queue.json").read_text())
            if queue:
                rec_id = next(iter(queue.keys()))
                result = find_match_candidates(rec_id, top_n=2, days=60)
                assert len(result) <= 2
        except (FileNotFoundError, json.JSONDecodeError):
            pytest.skip("improvement_queue.json não disponível")
