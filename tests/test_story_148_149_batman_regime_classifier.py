"""
tests/test_story_148_149_batman_regime_classifier.py
========================================================
Story 148 — MarketRegime Integration no Batman.
Story 149 — Asset Classifier Integration no Batman.

Testa os novos gates 5b (market regime) e 5c (asset classifier)
injetados no Batman._run() via signal.metadata.

Nota: Batman é síncrono-first via gate lógica, então usamos pytest-asyncio
para _run() async. Mostramos que:
  - BEAR regime capa leverage e rejeita LONGs com RSI alto
  - VOLATILE regime reduz size
  - SMALL_CAP/MID_CAP capam leverage por tier
  - LARGE_CAP não é restrito além do limite global
  - Gates falham open quando metadata ausente ou inválida
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.agents.batman import BatmanAgent
from src.models.risk import RiskVerdict
from src.models.signal import TradeAction, TradingSignal


@pytest.fixture(autouse=True)
def _isolate_from_db_and_runtime():
    """
    Isola o Batman do estado real (DB + runtime overrides) para que os
    gates 3l/3n/3o/3f/3g/3p/3q e o modo super_aggressive não interfiram
    nos testes específicos de gates 5b/5c.
    """
    with (
        patch("src.agents.batman.is_kill_switch_active", return_value=False),
        patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
        patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
        patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
        patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
        patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(
    action: str = "LONG",
    symbol: str = "BTC",
    confidence: float = 0.80,
    size_pct: float = 0.01,
    leverage: int = 5,
    risk_reward: float = 2.0,
    metadata: dict | None = None,
) -> TradingSignal:
    trade_action = TradeAction(action)
    entry_price = 50000.0
    if trade_action == TradeAction.SHORT:
        stop_loss = 52000.0
        take_profit = 46000.0
    else:
        stop_loss = 48000.0
        take_profit = 54000.0

    return TradingSignal(
        symbol=symbol,
        action=trade_action,
        confidence=confidence,
        size_pct=size_pct,
        leverage=leverage,
        risk_reward_ratio=risk_reward,
        timeframe="1h",
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reasoning="test",
        metadata=metadata or {},
    )


async def _run(signal: TradingSignal, **kwargs):
    agent = BatmanAgent()
    return await agent._run(signal=signal, **kwargs)


# ---------------------------------------------------------------------------
# Story 148 — BEAR regime
# ---------------------------------------------------------------------------

class TestBearRegimeLeverageCap:
    @pytest.mark.asyncio
    async def test_bear_caps_leverage_to_2x(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_max_leverage", 2)
        sig = _signal(leverage=5, metadata={"market_regime": "BEAR"})
        result = await _run(sig)
        assert result.adjusted_leverage <= 2

    @pytest.mark.asyncio
    async def test_bear_keeps_low_leverage(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_max_leverage", 2)
        sig = _signal(leverage=1, metadata={"market_regime": "BEAR"})
        result = await _run(sig)
        assert result.adjusted_leverage == 1  # already within limit

    @pytest.mark.asyncio
    async def test_bear_long_rejected_when_rsi_too_high(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_long_max_rsi", 40.0)
        sig = _signal(
            action="LONG",
            leverage=1,
            metadata={"market_regime": "BEAR", "rsi": 55.0},
        )
        result = await _run(sig)
        assert result.verdict == RiskVerdict.REJECTED
        assert any("BEAR" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_bear_long_approved_when_rsi_oversold(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_max_leverage", 2)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_long_max_rsi", 40.0)
        sig = _signal(
            action="LONG",
            leverage=2,
            metadata={"market_regime": "BEAR", "rsi": 28.0},
        )
        result = await _run(sig)
        # RSI 28 < 40 = approved (not rejected by bear gate)
        assert result.verdict != RiskVerdict.REJECTED or not any(
            "BEAR regime: LONG rejected" in r for r in result.reasons
        )

    @pytest.mark.asyncio
    async def test_bear_short_not_restricted_by_rsi_gate(self, monkeypatch):
        """SHORT signals in BEAR regime don't hit the RSI gate (only LONGs do)."""
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.bear_regime_long_max_rsi", 40.0)
        sig = _signal(
            action="SHORT",
            leverage=1,
            metadata={"market_regime": "BEAR", "rsi": 70.0},
        )
        result = await _run(sig)
        # Should NOT be rejected by bear RSI gate (only LONG gate hits)
        assert not any("BEAR regime: LONG rejected" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_regime_gate_disabled_skips_checks(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", False)
        sig = _signal(leverage=5, metadata={"market_regime": "BEAR", "rsi": 70.0})
        result = await _run(sig)
        # With gate disabled, should not reject for BEAR RSI reason
        assert not any("BEAR" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Story 148 — VOLATILE regime
# ---------------------------------------------------------------------------

class TestVolatileRegimeSizeReduction:
    @pytest.mark.asyncio
    async def test_volatile_reduces_size(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.volatile_regime_size_multiplier", 0.7)
        sig = _signal(size_pct=0.02, metadata={"market_regime": "VOLATILE"})
        result = await _run(sig)
        # Size should be ≤ 0.02 (reduced by volatile gate)
        assert result.adjusted_size_pct <= 0.02
        assert any("VOLATILE" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_bull_no_restriction(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.market_regime_gate_enabled", True)
        sig = _signal(leverage=5, size_pct=0.02, metadata={"market_regime": "BULL"})
        result = await _run(sig)
        # BULL regime has no gate restriction
        assert not any("BULL regime" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Story 149 — Asset Classifier leverage caps
# ---------------------------------------------------------------------------

class TestAssetClassifierGate:
    @pytest.mark.asyncio
    async def test_small_cap_caps_leverage(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.asset_classifier_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.small_cap_max_leverage", 2)
        sig = _signal(symbol="PEPE", leverage=5, metadata={"cap_tier": "SMALL_CAP"})
        result = await _run(sig)
        assert result.adjusted_leverage <= 2

    @pytest.mark.asyncio
    async def test_mid_cap_caps_leverage(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.asset_classifier_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.mid_cap_max_leverage", 3)
        sig = _signal(symbol="SOL", leverage=5, metadata={"cap_tier": "MID_CAP"})
        result = await _run(sig)
        assert result.adjusted_leverage <= 3

    @pytest.mark.asyncio
    async def test_large_cap_not_restricted(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.asset_classifier_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.max_leverage", 5)
        sig = _signal(symbol="BTC", leverage=5, metadata={"cap_tier": "LARGE_CAP"})
        result = await _run(sig)
        # Large cap gate reason should NOT appear
        assert not any("LARGE_CAP" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_classifier_resolves_from_symbol_when_no_metadata(self, monkeypatch):
        """Without cap_tier in metadata, Batman calls AssetClassifier.cap_tier(symbol)."""
        monkeypatch.setattr("src.config.settings.settings.asset_classifier_gate_enabled", True)
        monkeypatch.setattr("src.config.settings.settings.small_cap_max_leverage", 2)
        # SHIB is not in LARGE or MID → SMALL_CAP → should cap leverage
        sig = _signal(symbol="SHIB", leverage=5, metadata={})
        result = await _run(sig)
        assert result.adjusted_leverage <= 2

    @pytest.mark.asyncio
    async def test_classifier_gate_disabled(self, monkeypatch):
        monkeypatch.setattr("src.config.settings.settings.asset_classifier_gate_enabled", False)
        sig = _signal(symbol="SHIB", leverage=5, metadata={"cap_tier": "SMALL_CAP"})
        result = await _run(sig)
        # Gate disabled → SHIB not restricted
        assert not any("SMALL_CAP" in r for r in result.reasons)
