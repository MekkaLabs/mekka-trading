"""
tests/test_trading_vault_writer.py
====================================
Smoke tests dos writers de agentes de trading (Mentor/Cyclops/Vision).
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "60 - Daily").mkdir(parents=True)
    (vault / "20 - Areas" / "Trading" / "Calibrações").mkdir(parents=True)
    (vault / "20 - Areas" / "Trading" / "Decisões").mkdir(parents=True)
    monkeypatch.setenv("MEKKA_VAULT_PATH", str(vault))
    monkeypatch.setenv("MENTOR_VAULT_WRITER_ENABLED", "true")
    monkeypatch.setenv("CYCLOPS_VAULT_WRITER_ENABLED", "true")
    monkeypatch.setenv("VISION_VAULT_WRITER_ENABLED", "true")
    return vault


@pytest.fixture
def writer():
    from src.services import trading_vault_writer as tvw
    # Reset throttles
    tvw._mentor_throttle._events.clear()
    tvw._cyclops_throttle._events.clear()
    tvw._vision_throttle._events.clear()
    return tvw


# ---------------------------------------------------------------------------
# Mentor writer
# ---------------------------------------------------------------------------


class TestMentorWriter:
    def test_high_conf_writes(self, temp_vault, writer):
        result = writer.record_mentor_suggestion({
            "target": "rsi_threshold",
            "current_value": 30,
            "suggested_value": 25,
            "confidence": 0.85,
            "n_samples": 50,
            "reason": "Win rate caiu",
            "can_auto_apply": True,
        })
        assert result is not None
        assert result.exists()
        text = result.read_text(encoding="utf-8")
        assert "rsi_threshold" in text
        assert "30" in text
        assert "25" in text

    def test_low_conf_skipped(self, temp_vault, writer):
        result = writer.record_mentor_suggestion({
            "target": "x", "current_value": 1, "suggested_value": 2,
            "confidence": 0.5,  # abaixo de 0.7
            "can_auto_apply": True,
        })
        assert result is None

    def test_cant_auto_apply_skipped(self, temp_vault, writer):
        result = writer.record_mentor_suggestion({
            "target": "x", "current_value": 1, "suggested_value": 2,
            "confidence": 0.9,
            "can_auto_apply": False,  # bloqueado
        })
        assert result is None

    def test_disabled_no_op(self, temp_vault, writer, monkeypatch):
        monkeypatch.delenv("MENTOR_VAULT_WRITER_ENABLED", raising=False)
        result = writer.record_mentor_suggestion({
            "target": "x", "current_value": 1, "suggested_value": 2,
            "confidence": 0.95, "can_auto_apply": True,
        })
        assert result is None


# ---------------------------------------------------------------------------
# Cyclops writer
# ---------------------------------------------------------------------------


class TestCyclopsWriter:
    def test_writes_with_pnl(self, temp_vault, writer):
        result = writer.record_cyclops_close({
            "symbol": "BTC",
            "side": "LONG",
            "pnl_usd": 42.50,
            "holding_hours": 3.5,
            "reason": "TP hit",
        })
        assert result is not None
        text = result.read_text(encoding="utf-8")
        assert "BTC" in text
        assert "LONG" in text
        assert "+42.50" in text
        assert "TP hit" in text

    def test_no_pnl_skipped(self, temp_vault, writer):
        result = writer.record_cyclops_close({
            "symbol": "ETH", "side": "SHORT", "pnl_usd": None,
        })
        assert result is None

    def test_multiple_appends(self, temp_vault, writer):
        for i in range(3):
            writer.record_cyclops_close({
                "symbol": f"SYM{i}", "side": "LONG", "pnl_usd": i * 1.0,
            })
        daily = temp_vault / "60 - Daily" / next(
            p.name for p in (temp_vault / "60 - Daily").iterdir()
            if "trades" in p.name
        )
        text = daily.read_text(encoding="utf-8")
        for i in range(3):
            assert f"SYM{i}" in text


# ---------------------------------------------------------------------------
# Vision writer
# ---------------------------------------------------------------------------


class TestVisionWriter:
    def test_high_conf_buy_writes(self, temp_vault, writer):
        result = writer.record_vision_decision({
            "symbol": "BTC",
            "action": "BUY",
            "confidence": 0.85,
            "price": 100000.0,
            "size_pct": 0.02,
            "cycle_id": "cyc123",
            "rationale": "Strong bullish setup",
        })
        assert result is not None
        text = result.read_text(encoding="utf-8")
        assert "BTC" in text
        assert "BUY" in text
        assert "0.85" in text
        assert "Strong bullish setup" in text

    def test_low_conf_skipped(self, temp_vault, writer):
        result = writer.record_vision_decision({
            "symbol": "BTC", "action": "BUY", "confidence": 0.6,
        })
        assert result is None

    def test_hold_action_skipped(self, temp_vault, writer):
        result = writer.record_vision_decision({
            "symbol": "BTC", "action": "HOLD", "confidence": 0.95,
        })
        assert result is None

    def test_per_symbol_files(self, temp_vault, writer):
        writer.record_vision_decision({
            "symbol": "BTC", "action": "BUY", "confidence": 0.9,
        })
        writer.record_vision_decision({
            "symbol": "ETH", "action": "SELL", "confidence": 0.9,
        })
        files = list((temp_vault / "20 - Areas" / "Trading" / "Decisões").iterdir())
        assert len(files) == 2
        names = sorted(p.name for p in files)
        assert any("BTC" in n for n in names)
        assert any("ETH" in n for n in names)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_returns_3_agents(self, temp_vault, writer):
        s = writer.stats()
        assert "mentor" in s
        assert "cyclops" in s
        assert "vision" in s
        for agent_stats in (s["mentor"], s["cyclops"], s["vision"]):
            assert "enabled" in agent_stats
            assert "cap_per_hour" in agent_stats
