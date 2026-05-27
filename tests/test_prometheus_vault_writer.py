"""
tests/test_prometheus_vault_writer.py
======================================
Cobertura de src/services/prometheus_vault_writer.py.

Foco:
- Opt-in via env var
- Throttle hourly
- Atomic write (cria header + append)
- Fail-silent quando vault ausente / I/O falha
- Sanitização (não vaza chaves inesperadas)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.services.prometheus_vault_writer import (
    MAX_WRITES_PER_HOUR,
    _format_learning_block,
    _HourlyThrottle,
    get_vault_path,
    is_writer_enabled,
    record_learning,
    stats,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_vault(tmp_path: Path, monkeypatch) -> Path:
    """Vault temporário (estrutura mínima)."""
    monkeypatch.setenv("MEKKA_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("PROMETHEUS_VAULT_WRITER_ENABLED", "true")
    (tmp_path / "60 - Daily").mkdir()
    return tmp_path


@pytest.fixture
def sample_learning() -> dict:
    return {
        "ts": 1748275200.0,  # 2025-05-26 12:00
        "cycle_id": "c-abc",
        "symbol": "BTC",
        "observation_count": 12,
        "topic_counts": {"vision.signal": 3, "agent.error": 1, "cycle.end": 1},
        "stats_snapshot": {
            "events_seen": 30,
            "observations_emitted": 12,
        },
    }


# ---------------------------------------------------------------------------
# Opt-in
# ---------------------------------------------------------------------------


class TestOptIn:
    def test_default_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("PROMETHEUS_VAULT_WRITER_ENABLED", raising=False)
        assert is_writer_enabled() is False

    def test_enabled_when_env_set(self, monkeypatch) -> None:
        monkeypatch.setenv("PROMETHEUS_VAULT_WRITER_ENABLED", "true")
        assert is_writer_enabled() is True

    def test_vault_path_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MEKKA_VAULT_PATH", "/tmp/custom_vault")
        assert str(get_vault_path()) == "/tmp/custom_vault"


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


class TestThrottle:
    def test_allows_up_to_max(self) -> None:
        t = _HourlyThrottle(max_events=3)
        for _ in range(3):
            assert t.allow() is True
        assert t.allow() is False


# ---------------------------------------------------------------------------
# Write happy path
# ---------------------------------------------------------------------------


class TestRecordLearning:
    def test_writes_to_daily_subdir(
        self, tmp_vault: Path, sample_learning: dict
    ) -> None:
        path = record_learning(sample_learning)
        assert path is not None
        assert path.parent.name == "60 - Daily"
        assert path.suffix == ".md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Prometheus Learnings" in content
        assert "cycle `c-abc`" in content
        assert "BTC" in content

    def test_append_to_same_day_file(
        self, tmp_vault: Path, sample_learning: dict
    ) -> None:
        p1 = record_learning(sample_learning)
        p2 = record_learning(sample_learning)
        assert p1 == p2  # mesmo arquivo (mesmo dia)
        # Conteúdo deve ter 2 blocos
        content = p1.read_text(encoding="utf-8")
        assert content.count("Observações na janela") >= 2

    def test_no_op_when_disabled(
        self, sample_learning: dict, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("PROMETHEUS_VAULT_WRITER_ENABLED", raising=False)
        monkeypatch.setenv("MEKKA_VAULT_PATH", str(tmp_path))
        (tmp_path / "60 - Daily").mkdir()
        path = record_learning(sample_learning)
        assert path is None
        assert list((tmp_path / "60 - Daily").glob("*.md")) == []

    def test_no_op_when_vault_missing(
        self, sample_learning: dict, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PROMETHEUS_VAULT_WRITER_ENABLED", "true")
        monkeypatch.setenv("MEKKA_VAULT_PATH", str(tmp_path / "nonexistent"))
        path = record_learning(sample_learning)
        assert path is None  # vault ausente → no-op fail-silent


# ---------------------------------------------------------------------------
# Sanitização
# ---------------------------------------------------------------------------


class TestSanitization:
    def test_strips_unsafe_keys(self) -> None:
        learning = {
            "ts": 1748275200.0,
            "cycle_id": "c-1",
            "symbol": "ETH",
            "observation_count": 5,
            "topic_counts": {"x": 1},
            "stats_snapshot": {"observations_emitted": 5},
            # Chaves SUSPEITAS — não devem aparecer no output
            "api_key": "sk-DANGER-1234567890",
            "private_key": "0xDEADBEEF",
            "wallet_address": "0xLEAK",
            "_internal": "secret",
        }
        block = _format_learning_block(learning)
        assert "sk-DANGER" not in block
        assert "DEADBEEF" not in block
        assert "LEAK" not in block
        assert "api_key" not in block
        assert "private_key" not in block

    def test_includes_safe_keys(self) -> None:
        learning = {
            "ts": 1748275200.0,
            "cycle_id": "c-2",
            "symbol": "SOL",
            "observation_count": 7,
            "topic_counts": {"vision.signal": 3},
            "stats_snapshot": {"x": 1},
        }
        block = _format_learning_block(learning)
        assert "c-2" in block
        assert "SOL" in block
        assert "vision.signal" in block


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_returns_expected_keys(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PROMETHEUS_VAULT_WRITER_ENABLED", "true")
        monkeypatch.setenv("MEKKA_VAULT_PATH", str(tmp_path))
        s = stats()
        assert "enabled" in s
        assert "vault_path" in s
        assert "vault_available" in s
        assert "writes_in_window" in s
        assert "max_per_hour" in s
        assert s["enabled"] is True
        assert s["vault_available"] is True
