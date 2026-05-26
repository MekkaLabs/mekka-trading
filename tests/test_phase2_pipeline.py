"""
tests/test_phase2_pipeline.py
=============================
Phase 2 — Strategic Pipeline tests (Story 025).

Coverage targets:
  • Vision      — fallback HOLD on anomaly halt, on OpenAI error, on schema error
  • Batman      — kill switch, drawdown, open-positions cap, trades-today cap,
                  confidence/RR gates, size+leverage capping, HOLD bypass
  • Iron Man    — paper-trading branch never touches the SDK
  • Nick Fury   — full cycle in paper mode with all sub-agents mocked

All external boundaries are mocked:
  • OpenAI AsyncOpenAI.chat.completions.create
  • Layer-1 agents (Superman, Doctor Strange, Black Panther, Thor, Aquaman, Spider-Man)
  • MekkaRepository (in-memory mock so SQLite isn't required)

Run: pytest tests/test_phase2_pipeline.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.batman import Batman, _KILL_SWITCH_FILE, engage_kill_switch, release_kill_switch
from src.agents.iron_man import IronMan
from src.agents.nick_fury import NickFury
from src.agents.vision import Vision
from src.models.execution import ExecutionStatus
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
    WhaleSignal,
)
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _btc_market_data(**overrides) -> MarketData:
    defaults = dict(
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
    defaults.update(overrides)
    return MarketData(**defaults)


def _btc_analysis(**overrides) -> MarketAnalysis:
    chart = overrides.pop("chart", _btc_market_data())
    sentiment = overrides.pop(
        "sentiment",
        SentimentData(symbol="BTC", score=0.2, fear_greed_index=55, btc_dominance=52.0),
    )
    onchain = overrides.pop(
        "onchain",
        OnchainData(
            symbol="BTC",
            large_buys_24h=500_000.0,
            large_sells_24h=300_000.0,
            funding_rate=0.0001,
            open_interest=1_000_000_000.0,
        ),
    )
    volatility = overrides.pop(
        "volatility",
        VolatilityData(
            symbol="BTC",
            atr_pct=0.023,
            volatility_regime=VolatilityRegime.MEDIUM,
            suggested_position_size_multiplier=1.0,
        ),
    )
    liquidity = overrides.pop(
        "liquidity",
        LiquidityData(
            symbol="BTC",
            bid_ask_spread_pct=0.0005,
            order_book_depth_buy=500_000.0,
            order_book_depth_sell=500_000.0,
            estimated_slippage_pct=0.0005,
            liquidity_score=0.85,
        ),
    )
    anomaly = overrides.pop(
        "anomaly",
        AnomalyReport(symbol="BTC", anomalies_detected=[], severity=AnomalySeverity.NONE),
    )
    return MarketAnalysis(
        chart=chart,
        sentiment=sentiment,
        onchain=onchain,
        volatility=volatility,
        liquidity=liquidity,
        anomaly=anomaly,
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
        reasoning="Bullish setup",
        agent_contributions={"Superman": "BULLISH"},
    )
    defaults.update(overrides)
    return TradingSignal(**defaults)


@pytest.fixture(autouse=True)
def _ensure_no_kill_switch(tmp_path, monkeypatch):
    """Make the kill-switch file path test-isolated and clear by default."""
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    monkeypatch.delenv("MEKKA_KILL_SWITCH", raising=False)
    yield
    if test_path.exists():
        test_path.unlink()


# ===========================================================================
# Vision
# ===========================================================================


@pytest.mark.asyncio
async def test_vision_fallback_hold_on_anomaly_halt():
    """Anomaly should_pause=True → Vision returns HOLD without calling OpenAI."""
    bad_anomaly = AnomalyReport(
        symbol="BTC",
        anomalies_detected=["Flash crash detected"],
        severity=AnomalySeverity.HIGH,  # auto-sets should_pause=True
    )
    analysis = _btc_analysis(anomaly=bad_anomaly)
    assert analysis.is_safe_to_trade is False

    with patch("src.agents.vision.AsyncOpenAI") as mock_openai:
        signal = await Vision().run(analysis=analysis)

    assert signal.action == TradeAction.HOLD
    assert signal.confidence == 0.0
    assert (signal.metadata or {}).get("fallback") is True
    # OpenAI should never have been instantiated
    mock_openai.assert_not_called()


@pytest.mark.asyncio
async def test_vision_fallback_hold_on_extreme_volatility():
    """Volatility EXTREME → not safe to trade → HOLD without LLM."""
    extreme = VolatilityData(
        symbol="BTC",
        atr_pct=0.08,
        volatility_regime=VolatilityRegime.EXTREME,
        suggested_position_size_multiplier=0.3,
    )
    analysis = _btc_analysis(volatility=extreme)
    assert analysis.is_safe_to_trade is False

    with patch("src.agents.vision.AsyncOpenAI") as mock_openai:
        signal = await Vision().run(analysis=analysis)

    assert signal.action == TradeAction.HOLD
    mock_openai.assert_not_called()


@pytest.mark.asyncio
async def test_vision_fallback_hold_on_openai_error():
    """OpenAI raises → Vision returns HOLD with fallback=True."""
    analysis = _btc_analysis()

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    fake_client.close = AsyncMock()

    with patch("src.agents.vision.AsyncOpenAI", return_value=fake_client):
        signal = await Vision().run(analysis=analysis)

    assert signal.action == TradeAction.HOLD
    assert (signal.metadata or {}).get("fallback") is True


@pytest.mark.asyncio
async def test_vision_parses_valid_long_signal():
    """LLM returns a well-formed LONG decision → Vision builds the TradingSignal."""
    analysis = _btc_analysis()

    payload = {
        "action": "LONG",
        "confidence": 0.78,
        "entry_price": 65_000.0,
        "stop_loss": 63_500.0,
        "take_profit": 69_000.0,
        "size_pct": 0.02,
        "leverage": 3,
        "reasoning": "Bullish trend confirmed by EMA cross and macro tailwind.",
        "agent_contributions": {"Superman": "BULLISH", "DoctorStrange": "Neutral-positive"},
    }
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    fake_client.close = AsyncMock()

    with patch("src.agents.vision.AsyncOpenAI", return_value=fake_client):
        signal = await Vision().run(analysis=analysis)

    assert signal.action == TradeAction.LONG
    assert signal.confidence == 0.78
    assert signal.size_pct == 0.02
    assert signal.leverage == 3
    assert signal.is_actionable is True
    assert (signal.metadata or {}).get("fallback") is False


@pytest.mark.asyncio
async def test_vision_caps_oversized_request():
    """LLM returns size_pct > hard cap → coerced to ≤10%."""
    analysis = _btc_analysis()
    payload = {
        "action": "LONG",
        "confidence": 0.95,
        "entry_price": 65_000.0,
        "stop_loss": 60_000.0,
        "take_profit": 80_000.0,
        "size_pct": 0.50,   # 50% — well over the 10% cap
        "leverage": 99,     # over the configured cap
        "reasoning": "test",
        "agent_contributions": {},
    }
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    fake_client.close = AsyncMock()

    with patch("src.agents.vision.AsyncOpenAI", return_value=fake_client):
        signal = await Vision().run(analysis=analysis)

    assert signal.size_pct <= 0.10  # Pydantic hard cap
    assert signal.leverage <= 5     # capped to settings.max_leverage


# ===========================================================================
# Batman
# ===========================================================================


@pytest.mark.asyncio
async def test_batman_blocks_when_kill_switch_engaged(tmp_path, monkeypatch):
    """Kill-switch file present → KILL_SWITCH verdict, no further checks."""
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    test_path.write_text("test halt")

    approval = await Batman().run(signal=_good_signal())

    assert approval.verdict == RiskVerdict.KILL_SWITCH
    assert approval.adjusted_size_pct == 0.0
    assert "kill_switch" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_rejects_hold_action():
    signal = _good_signal(
        action=TradeAction.HOLD,
        stop_loss=63_000.0,  # geometry only validated for LONG/SHORT
    )
    approval = await Batman().run(signal=signal)
    assert approval.verdict == RiskVerdict.REJECTED
    assert "HOLD" in approval.reasons[0]


@pytest.mark.asyncio
async def test_batman_rejects_on_drawdown_breach():
    approval = await Batman().run(
        signal=_good_signal(),
        current_drawdown_pct=0.15,  # over 10% default
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_daily_drawdown_pct" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_rejects_on_open_positions_cap():
    approval = await Batman().run(
        signal=_good_signal(),
        open_positions=10,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_open_positions" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_rejects_on_trades_today_cap():
    approval = await Batman().run(
        signal=_good_signal(),
        trades_today=99,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_trades_per_day" in approval.breached_limits


@pytest.fixture
def _batman_db_isolated():
    """
    Isola Batman dos gates async que batem em DB/exchange real e dos modos
    runtime (conservative/balanced/aggressive + super_aggressive overrides).
    Força o modo "balanced" — que tem max_pos=2%, max_lev=5x — para que os
    testes que esperam REDUCED em 5%/10x → 2%/5x funcionem deterministicamente.
    """
    from src.config.runtime_mode import PRESETS
    balanced_params = PRESETS.get("balanced", {})
    with (
        patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
        patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
        patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
        patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
        patch("src.config.runtime_overrides.get_runtime_overrides", return_value={}),
        patch("src.config.runtime_mode.get_params", return_value=balanced_params),
        # Neutraliza caches globais (funding/MTF/ATR) que poluem batch.
        patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
        patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
        patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
    ):
        yield


@pytest.mark.asyncio
async def test_batman_rejects_low_confidence(_batman_db_isolated):
    approval = await Batman().run(signal=_good_signal(confidence=0.40))
    assert approval.verdict == RiskVerdict.REJECTED
    assert "min_confidence_threshold" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_rejects_low_rr(_batman_db_isolated):
    # tight TP makes R:R < 1.5
    bad = _good_signal(stop_loss=63_000.0, take_profit=65_500.0)
    approval = await Batman().run(signal=bad)
    assert approval.verdict == RiskVerdict.REJECTED
    assert "min_risk_reward_ratio" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_caps_oversized_signal(_batman_db_isolated):
    """Signal asks 5% size, 10x leverage → capped to 2% / 5x → REDUCED."""
    big = _good_signal(size_pct=0.05, leverage=10)
    approval = await Batman().run(signal=big)

    assert approval.verdict == RiskVerdict.REDUCED
    assert approval.adjusted_size_pct == 0.02
    assert approval.adjusted_leverage == 5
    assert "max_position_size_pct" in approval.breached_limits
    assert "max_leverage" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_applies_thor_volatility_multiplier(_batman_db_isolated):
    """High-vol regime → 0.6x multiplier applied → REDUCED."""
    vol = VolatilityData(
        symbol="BTC",
        atr_pct=0.05,
        volatility_regime=VolatilityRegime.HIGH,
        suggested_position_size_multiplier=0.6,
    )
    approval = await Batman().run(signal=_good_signal(size_pct=0.02), volatility=vol)
    assert approval.verdict == RiskVerdict.REDUCED
    assert approval.adjusted_size_pct == pytest.approx(0.012, rel=1e-3)
    assert "volatility_adjustment" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_approves_clean_signal(_batman_db_isolated):
    """All checks pass → APPROVED with original parameters."""
    approval = await Batman().run(signal=_good_signal())
    assert approval.verdict == RiskVerdict.APPROVED
    assert approval.adjusted_size_pct == 0.02
    assert approval.adjusted_leverage == 3
    assert approval.is_executable is True


# ===========================================================================
# Iron Man — paper path
# ===========================================================================


@pytest.mark.asyncio
async def test_ironman_paper_path_does_not_touch_sdk():
    """paper_trading=True → no Hyperliquid SDK calls, returns PAPER status."""
    signal = _good_signal()
    approval = RiskApproval(
        symbol="BTC",
        verdict=RiskVerdict.APPROVED,
        adjusted_size_pct=0.02,
        adjusted_leverage=3,
    )
    iron = IronMan()

    # Sanity: settings.paper_trading must be True for this test (conftest sets it)
    from src.config.settings import settings
    assert settings.paper_trading is True

    # If the SDK got loaded, _connect would fail with a fake private key.
    # We assert it was never invoked by checking the result type.
    result = await iron.run(signal=signal, approval=approval, equity_usd=10_000.0)

    assert result.is_paper is True
    assert result.status == ExecutionStatus.PAPER
    assert result.symbol == "BTC"
    assert result.side == "long"
    assert result.order_id is not None and result.order_id.startswith("PAPER-")
    assert result.sl_order_id is not None and result.sl_order_id.startswith("PAPER-SL-")
    assert result.tp_order_id is not None and result.tp_order_id.startswith("PAPER-TP-")
    # Notional sanity: 10000 * 0.02 * 3 = 600 (±0.5% absorbs B5 3bps slippage)
    assert result.notional_usd == pytest.approx(600.0, rel=0.005)


@pytest.mark.asyncio
async def test_ironman_skips_when_approval_not_executable():
    rejected = RiskApproval(
        symbol="BTC",
        verdict=RiskVerdict.REJECTED,
        adjusted_size_pct=0.0,
        adjusted_leverage=1,
        reasons=["test"],
    )
    result = await IronMan().run(
        signal=_good_signal(),
        approval=rejected,
        equity_usd=10_000.0,
    )
    assert result.status == ExecutionStatus.SKIPPED


@pytest.mark.asyncio
async def test_ironman_skips_on_hold_action():
    """HOLD action with an approved verdict (defensive) → still SKIPPED."""
    hold = _good_signal(action=TradeAction.HOLD, stop_loss=63_000.0)
    approval = RiskApproval(
        symbol="BTC",
        verdict=RiskVerdict.APPROVED,
        adjusted_size_pct=0.001,
        adjusted_leverage=1,
    )
    result = await IronMan().run(
        signal=hold,
        approval=approval,
        equity_usd=10_000.0,
    )
    assert result.status == ExecutionStatus.SKIPPED


# ===========================================================================
# Nick Fury — full cycle (paper, all sub-agents mocked)
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_full_paper_cycle(monkeypatch):
    """
    Nick Fury runs one full pipeline pass with everything mocked:
      • ProfessorX returns a canned MarketAnalysis
      • Vision returns a canned TradingSignal (LONG, actionable)
      • Batman is real (deterministic) — should APPROVE
      • Iron Man runs the real paper path → PAPER status
      • MekkaRepository is mocked (no SQLite needed)
      • settings.trading_assets restricted to ["BTC"] for determinism
    """
    from src.config.settings import settings as real_settings

    fury = NickFury()
    analysis = _btc_analysis()
    signal = _good_signal()

    # Patch sub-agent boundaries (instance methods)
    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=signal)
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()  # Story 027 wiring
    # Batman stays REAL — exercises the deterministic gate.
    # Iron Man stays REAL — exercises the paper path (no SDK required).

    # Repository mock so no SQLite touches happen
    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(return_value=42)
    repo_mock.save_trade = AsyncMock(return_value=99)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.01)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    # Restrict trading_assets to BTC for determinism. The real Settings
    # exposes trading_assets as a cached_property — patch via __dict__.
    real_settings.__dict__["trading_assets"] = ["BTC"]

    try:
        reports = await fury.run_main_cycle(equity_usd=10_000.0)
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    assert len(reports) == 1
    report = reports[0]
    assert report.symbol == "BTC"
    assert report.signal is not None and report.signal.action == TradeAction.LONG
    assert report.approval is not None and report.approval.is_executable
    assert report.execution is not None and report.execution.is_paper
    assert report.execution.status == ExecutionStatus.PAPER
    assert report.is_executed() is True

    # Side-effects we expect Nick Fury to record
    repo_mock.save_signal.assert_awaited_once()
    repo_mock.save_trade.assert_awaited_once()
    assert repo_mock.log_event.await_count >= 2  # at least RISK + EXEC events


@pytest.mark.asyncio
async def test_nick_fury_kill_switch_skips_cycle(tmp_path, monkeypatch):
    """When kill-switch is engaged, run_main_cycle returns [] and never calls sub-agents."""
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    test_path.write_text("halted by test")

    fury = NickFury()
    fury._professor.run = AsyncMock()
    fury._vision.run = AsyncMock()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.0)
    repo_mock.count_trades_today = AsyncMock(return_value=0)

    with patch("src.agents.nick_fury.MekkaRepository", repo_mock):
        reports = await fury.run_main_cycle(equity_usd=10_000.0)

    assert reports == []
    fury._professor.run.assert_not_called()
    fury._vision.run.assert_not_called()
    # CYCLE_SKIPPED audit event must have fired
    assert any(
        call_args.kwargs.get("event") == "CYCLE_SKIPPED"
        for call_args in repo_mock.log_event.await_args_list
    )
