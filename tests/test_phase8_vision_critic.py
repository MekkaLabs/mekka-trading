"""
tests/test_phase8_vision_critic.py
==================================
Phase 8 — Vision Critic tests (Story 031).

Coverage:
  • VisionCritic — HOLD signal bypassed (returns ENDORSE)
  • VisionCritic — LLM ENDORSE preserved
  • VisionCritic — LLM REJECT honored when delta ≥ threshold
  • VisionCritic — LLM AMEND honored when delta ≥ threshold
  • VisionCritic — small delta downgrades AMEND/REJECT to ENDORSE
  • VisionCritic — fallback ENDORSE on LLM error
  • VisionCritic — fallback ENDORSE on JSON parse failure
  • VisionCritic — never accepts riskier amend (size_pct > original)
  • VisionCritic — never accepts riskier amend (leverage > original)
  • VisionCritic — never accepts wider SL (further from entry)
  • apply_critique — ENDORSE returns identical signal
  • apply_critique — REJECT returns HOLD with critic metadata
  • apply_critique — AMEND applies size/leverage/SL/TP overrides
  • Nick Fury — critic bypassed when enabled=False
  • Nick Fury — critic invoked when enabled=True; REJECT downgrades

Run: pytest tests/test_phase8_vision_critic.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.vision_critic import VisionCritic, apply_critique
from src.models.critique import CritiqueAction, VisionCritique
from src.models.market_data import (
    AnomalyReport,
    AnomalySeverity,
    LiquidityData,
    MarketAnalysis,
    MarketData,
    OnchainData,
    SentimentData,
    Trend,
    VolatilityData,
    VolatilityRegime,
)
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _btc_market_data() -> MarketData:
    return MarketData(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=65_000.0,
        rsi_14=55.0,
        ema_20=64_000.0,
        ema_50=62_000.0,
        bb_upper=68_000.0,
        bb_lower=60_000.0,
        bb_mid=64_000.0,
        macd=150.0,
        macd_signal=100.0,
        macd_hist=50.0,
        atr_14=1_500.0,
        volume=5_000.0,
        volume_ma=4_000.0,
        trend=Trend.BULLISH,
        trend_strength=0.7,
    )


def _btc_analysis() -> MarketAnalysis:
    return MarketAnalysis(
        chart=_btc_market_data(),
        sentiment=SentimentData(symbol="BTC", score=0.2, fear_greed_index=55, btc_dominance=52.0),
        onchain=OnchainData(symbol="BTC", large_buys_24h=500_000.0, large_sells_24h=300_000.0),
        volatility=VolatilityData(
            symbol="BTC",
            atr_pct=0.023,
            volatility_regime=VolatilityRegime.MEDIUM,
            suggested_position_size_multiplier=1.0,
        ),
        liquidity=LiquidityData(
            symbol="BTC",
            bid_ask_spread_pct=0.0005,
            order_book_depth_buy=500_000.0,
            order_book_depth_sell=500_000.0,
            estimated_slippage_pct=0.0005,
            liquidity_score=0.85,
        ),
        anomaly=AnomalyReport(symbol="BTC", anomalies_detected=[], severity=AnomalySeverity.NONE),
    )


def _good_signal(**overrides) -> TradingSignal:
    defaults = dict(
        symbol="BTC",
        action=TradeAction.LONG,
        confidence=0.80,
        entry_price=65_000.0,
        stop_loss=63_000.0,
        take_profit=70_000.0,
        size_pct=0.02,
        leverage=3,
        reasoning="bullish",
    )
    defaults.update(overrides)
    return TradingSignal(**defaults)


def _llm_response(payload: dict) -> MagicMock:
    fake = MagicMock()
    fake.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return fake


# ===========================================================================
# VisionCritic — pure logic
# ===========================================================================


@pytest.mark.asyncio
async def test_critic_bypasses_hold_signal():
    """HOLD signals never get reviewed — critic returns ENDORSE without LLM call."""
    hold = _good_signal(action=TradeAction.HOLD, stop_loss=63_000.0, take_profit=67_000.0)
    with patch("src.agents.vision_critic.AsyncOpenAI") as mock_openai:
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=hold)
    assert critique.action == CritiqueAction.ENDORSE
    assert critique.fallback is False
    mock_openai.assert_not_called()


@pytest.mark.asyncio
async def test_critic_endorses_when_llm_endorses():
    payload = {
        "action": "ENDORSE",
        "confidence_delta": 0.10,
        "amended_size_pct": None,
        "amended_leverage": None,
        "amended_stop_loss": None,
        "amended_take_profit": None,
        "reasoning": "Looks good.",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.ENDORSE
    assert critique.fallback is False


@pytest.mark.asyncio
async def test_critic_honors_reject_when_delta_above_threshold():
    payload = {
        "action": "REJECT",
        "confidence_delta": 0.55,
        "amended_size_pct": None,
        "amended_leverage": None,
        "amended_stop_loss": None,
        "amended_take_profit": None,
        "reasoning": "Liquidity too thin and macro headwind.",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.REJECT
    assert critique.confidence_delta == pytest.approx(0.55)


@pytest.mark.asyncio
async def test_critic_honors_amend_when_delta_above_threshold():
    payload = {
        "action": "AMEND",
        "confidence_delta": 0.40,
        "amended_size_pct": 0.01,            # smaller than 0.02 → ok
        "amended_leverage": 2,               # smaller than 3 → ok
        "amended_stop_loss": 64_000.0,       # tighter (closer to entry 65k)
        "amended_take_profit": 68_000.0,     # closer to entry than original 70k
        "reasoning": "Trend is OK but size feels aggressive.",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.AMEND
    assert critique.amended_size_pct == 0.01
    assert critique.amended_leverage == 2
    assert critique.amended_stop_loss == 64_000.0
    assert critique.amended_take_profit == 68_000.0


@pytest.mark.asyncio
async def test_critic_downgrades_small_delta_to_endorse(monkeypatch):
    """delta < min_disagreement → action collapses to ENDORSE."""
    from src.config.settings import settings as real_settings
    monkeypatch.setattr(real_settings, "vision_critic_min_disagreement", 0.30)

    payload = {
        "action": "AMEND",
        "confidence_delta": 0.10,  # below threshold
        "amended_size_pct": 0.015,
        "amended_leverage": None,
        "amended_stop_loss": None,
        "amended_take_profit": None,
        "reasoning": "minor nit.",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.ENDORSE
    assert critique.amended_size_pct is None  # cleared on downgrade


@pytest.mark.asyncio
async def test_critic_fallback_on_llm_error():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.ENDORSE
    assert critique.fallback is True
    assert "FALLBACK" in critique.reasoning


@pytest.mark.asyncio
async def test_critic_fallback_on_invalid_json():
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="not json at all"))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.ENDORSE
    assert critique.fallback is True


@pytest.mark.asyncio
async def test_critic_rejects_riskier_amended_size():
    """AMEND with size_pct > original → coerced to None (no override)."""
    payload = {
        "action": "AMEND",
        "confidence_delta": 0.40,
        "amended_size_pct": 0.05,  # bigger than 0.02 → REJECTED
        "amended_leverage": None,
        "amended_stop_loss": None,
        "amended_take_profit": None,
        "reasoning": "trying to scale up",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.action == CritiqueAction.AMEND
    assert critique.amended_size_pct is None  # safer-only filter discarded


@pytest.mark.asyncio
async def test_critic_rejects_riskier_amended_leverage():
    payload = {
        "action": "AMEND",
        "confidence_delta": 0.40,
        "amended_size_pct": None,
        "amended_leverage": 10,  # > original 3 → REJECTED
        "amended_stop_loss": None,
        "amended_take_profit": None,
        "reasoning": "go bigger",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.amended_leverage is None


@pytest.mark.asyncio
async def test_critic_rejects_wider_stop_loss():
    """SL further from entry (looser) is unsafe → coerced to None."""
    payload = {
        "action": "AMEND",
        "confidence_delta": 0.40,
        "amended_size_pct": None,
        "amended_leverage": None,
        "amended_stop_loss": 60_000.0,  # original 63k; this is wider on a LONG → UNSAFE
        "amended_take_profit": None,
        "reasoning": "give it room",
    }
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_llm_response(payload))
    fake_client.close = AsyncMock()
    with patch("src.agents.vision_critic.AsyncOpenAI", return_value=fake_client):
        critique = await VisionCritic().run(analysis=_btc_analysis(), signal=_good_signal())
    assert critique.amended_stop_loss is None


# ===========================================================================
# apply_critique
# ===========================================================================


def test_apply_endorse_returns_identical_signal():
    sig = _good_signal()
    crit = VisionCritique(symbol="BTC", action=CritiqueAction.ENDORSE)
    out = apply_critique(signal=sig, critique=crit)
    assert out is sig


def test_apply_reject_returns_hold_with_metadata():
    sig = _good_signal()
    crit = VisionCritique(
        symbol="BTC", action=CritiqueAction.REJECT, confidence_delta=0.6,
        reasoning="liquidity collapse",
    )
    out = apply_critique(signal=sig, critique=crit)
    assert out.action == TradeAction.HOLD
    assert out.confidence == 0.0
    assert (out.metadata or {}).get("critic_rejected") is True
    assert "liquidity collapse" in (out.metadata or {}).get("critic_reason", "")


def test_apply_amend_overrides_safer_fields():
    sig = _good_signal()
    crit = VisionCritique(
        symbol="BTC",
        action=CritiqueAction.AMEND,
        confidence_delta=0.45,
        amended_size_pct=0.01,
        amended_leverage=2,
        amended_stop_loss=64_000.0,
        amended_take_profit=68_000.0,
        reasoning="trim",
    )
    out = apply_critique(signal=sig, critique=crit)
    assert out.action == TradeAction.LONG
    assert out.size_pct == 0.01
    assert out.leverage == 2
    assert out.stop_loss == 64_000.0
    assert out.take_profit == 68_000.0
    assert (out.metadata or {}).get("critic_amended") is True


# ===========================================================================
# Nick Fury wiring
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_skips_critic_when_disabled(monkeypatch):
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings
    from src.models.execution import ExecutionResult, ExecutionStatus
    from src.models.portfolio import EquitySnapshot, EquitySource

    monkeypatch.setattr(real_settings, "vision_critic_enabled", False)

    fury = NickFury()
    fury._professor.run = AsyncMock(return_value=_btc_analysis())
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=_good_signal())
    fury._vision.close = AsyncMock()
    fury._vision_critic.run = AsyncMock()  # should NOT be called
    fury._daily_pnl.record_cycle = AsyncMock()
    fury._portfolio.run = AsyncMock(
        return_value=EquitySnapshot(
            source=EquitySource.HYPERLIQUID,
            is_paper=True,
            equity_usd=10_000.0,
            available_balance_usd=10_000.0,
            margin_used_usd=0.0,
            open_positions_count=0,
        )
    )

    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(return_value=1)
    repo_mock.save_trade = AsyncMock(return_value=2)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.0)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    real_settings.__dict__["trading_assets"] = ["BTC"]
    try:
        reports = await fury.run_main_cycle()
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    assert len(reports) == 1
    fury._vision_critic.run.assert_not_called()


@pytest.mark.asyncio
async def test_nick_fury_invokes_critic_when_enabled(monkeypatch):
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings
    from src.models.portfolio import EquitySnapshot, EquitySource

    monkeypatch.setattr(real_settings, "vision_critic_enabled", True)

    fury = NickFury()
    fury._professor.run = AsyncMock(return_value=_btc_analysis())
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=_good_signal())
    fury._vision.close = AsyncMock()
    fury._vision_critic.run = AsyncMock(
        return_value=VisionCritique(
            symbol="BTC",
            action=CritiqueAction.REJECT,
            confidence_delta=0.6,
            reasoning="anomaly heavy",
        )
    )
    fury._daily_pnl.record_cycle = AsyncMock()
    fury._portfolio.run = AsyncMock(
        return_value=EquitySnapshot(
            source=EquitySource.HYPERLIQUID,
            is_paper=True,
            equity_usd=10_000.0,
            available_balance_usd=10_000.0,
            margin_used_usd=0.0,
            open_positions_count=0,
        )
    )

    captured_signals: list[TradingSignal] = []
    real_save = AsyncMock(return_value=1)

    async def _spy_save(signal):
        captured_signals.append(signal)
        return await real_save(signal)

    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(side_effect=_spy_save)
    repo_mock.save_trade = AsyncMock(return_value=2)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.0)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    real_settings.__dict__["trading_assets"] = ["BTC"]
    try:
        reports = await fury.run_main_cycle()
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    assert len(reports) == 1
    fury._vision_critic.run.assert_awaited_once()
    # save_signal saw a HOLD (REJECT was applied)
    assert len(captured_signals) == 1
    assert captured_signals[0].action == TradeAction.HOLD
    assert (captured_signals[0].metadata or {}).get("critic_rejected") is True
    # Audit recorded a CRITIQUE_REJECT event
    crit_events = [
        c for c in repo_mock.log_event.await_args_list
        if c.kwargs.get("event") == "CRITIQUE_REJECT"
    ]
    assert len(crit_events) == 1
