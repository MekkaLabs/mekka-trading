"""
tests/test_phase4_daily_pnl.py
==============================
Phase 4 — Daily PnL Writer service tests (Story 027).

Coverage:
  • DailyPnLWriter — first cycle creates baseline (starting_equity = current)
  • DailyPnLWriter — subsequent cycles update peak monotonically
  • DailyPnLWriter — drawdown computed against in-memory peak
  • DailyPnLWriter — day rollover resets baseline
  • DailyPnLWriter — repository.upsert_daily_pnl is called with the right shape
  • Nick Fury    — end of run_main_cycle calls DailyPnLWriter.record_cycle
  • Nick Fury    — uses effective_equity (CLI override) over snapshot

Run: pytest tests/test_phase4_daily_pnl.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.daily_pnl_writer import (
    DailyPnLSnapshot,
    DailyPnLWriter,
    _today_utc,
)


# ===========================================================================
# DailyPnLWriter unit tests
# ===========================================================================


@pytest.fixture
def fake_repo():
    """Patch MekkaRepository inside the writer's module."""
    repo_mock = MagicMock()
    repo_mock.upsert_daily_pnl = AsyncMock(return_value=1)
    repo_mock.log_event = AsyncMock(return_value=1)
    with patch("src.services.daily_pnl_writer.MekkaRepository", repo_mock):
        yield repo_mock


@pytest.mark.asyncio
async def test_first_cycle_creates_baseline(fake_repo):
    """First call sets starting_equity = current and pnl = 0."""
    writer = DailyPnLWriter()
    snap: DailyPnLSnapshot = await writer.record_cycle(
        equity_usd=10_000.0,
        trades_count_today=0,
    )

    assert snap.starting_equity == 10_000.0
    assert snap.peak_equity == 10_000.0
    assert snap.ending_equity == 10_000.0
    assert snap.pnl_usd == 0.0
    assert snap.pnl_pct == 0.0
    assert snap.drawdown_pct == 0.0
    assert snap.date_utc == _today_utc()
    fake_repo.upsert_daily_pnl.assert_awaited_once()


@pytest.mark.asyncio
async def test_peak_is_monotonic_within_day(fake_repo):
    """Peak only goes up as equity grows; pnl tracks gains."""
    writer = DailyPnLWriter()
    await writer.record_cycle(equity_usd=10_000.0, trades_count_today=0)
    s2 = await writer.record_cycle(equity_usd=11_000.0, trades_count_today=1)
    s3 = await writer.record_cycle(equity_usd=10_500.0, trades_count_today=2)

    assert s2.peak_equity == 11_000.0
    assert s2.pnl_usd == 1_000.0
    assert s2.pnl_pct == pytest.approx(0.10, rel=1e-6)
    assert s2.drawdown_pct == 0.0  # still at peak

    # equity dropped from peak — drawdown shows up
    assert s3.peak_equity == 11_000.0  # peak preserved
    assert s3.pnl_usd == 500.0
    assert s3.drawdown_pct == pytest.approx(500 / 11_000.0, rel=1e-6)


@pytest.mark.asyncio
async def test_day_rollover_resets_baseline(fake_repo, monkeypatch):
    """When UTC date changes, starting_equity resets to current."""
    writer = DailyPnLWriter()
    # Day 1
    monkeypatch.setattr(
        "src.services.daily_pnl_writer._today_utc", lambda: "2026-05-07"
    )
    await writer.record_cycle(equity_usd=10_000.0, trades_count_today=0)
    s_day1_end = await writer.record_cycle(
        equity_usd=12_000.0, trades_count_today=3
    )
    assert s_day1_end.peak_equity == 12_000.0
    assert s_day1_end.pnl_usd == 2_000.0

    # Day 2 — rollover
    monkeypatch.setattr(
        "src.services.daily_pnl_writer._today_utc", lambda: "2026-05-08"
    )
    s_day2 = await writer.record_cycle(equity_usd=12_000.0, trades_count_today=0)
    assert s_day2.date_utc == "2026-05-08"
    assert s_day2.starting_equity == 12_000.0  # reset
    assert s_day2.peak_equity == 12_000.0
    assert s_day2.pnl_usd == 0.0


@pytest.mark.asyncio
async def test_upsert_payload_shape(fake_repo):
    """The repository call carries the exact arguments we expect."""
    writer = DailyPnLWriter()
    await writer.record_cycle(
        equity_usd=10_000.0,
        trades_count_today=0,
    )
    await writer.record_cycle(
        equity_usd=9_500.0,
        trades_count_today=2,
        wins=1,
        losses=1,
    )

    # Two awaited calls; check the second one
    second_call = fake_repo.upsert_daily_pnl.await_args_list[1]
    kwargs = second_call.kwargs
    assert kwargs["date_utc"] == _today_utc()
    assert kwargs["ending_equity"] == 9_500.0
    assert kwargs["pnl_usd"] == -500.0
    assert kwargs["drawdown_pct"] == pytest.approx(500 / 10_000.0, rel=1e-6)
    assert kwargs["trades_count"] == 2
    assert kwargs["wins"] == 1
    assert kwargs["losses"] == 1
    assert kwargs["starting_equity"] == 10_000.0


@pytest.mark.asyncio
async def test_repository_failure_does_not_raise(monkeypatch):
    """If upsert_daily_pnl explodes, record_cycle still returns and logs error."""
    repo_mock = MagicMock()
    repo_mock.upsert_daily_pnl = AsyncMock(side_effect=RuntimeError("db locked"))
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.services.daily_pnl_writer.MekkaRepository", repo_mock)

    writer = DailyPnLWriter()
    snap = await writer.record_cycle(equity_usd=10_000.0, trades_count_today=0)

    assert snap.ending_equity == 10_000.0  # we still get a result
    repo_mock.log_event.assert_awaited()  # error path emitted an audit


# ===========================================================================
# Nick Fury wiring
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_calls_daily_pnl_at_end_of_cycle(monkeypatch):
    """run_main_cycle invokes _daily_pnl.record_cycle once, after the symbol loop."""
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings
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
    from src.models.portfolio import EquitySnapshot, EquitySource
    from src.models.signal import TradeAction, TradingSignal

    fury = NickFury()

    # Fixtures inline (kept independent of phase2/phase3 helpers)
    chart = MarketData(
        symbol="BTC", timestamp=datetime.now(timezone.utc), timeframe="4h",
        price=65_000.0, rsi_14=55.0, ema_20=64_000.0, ema_50=62_000.0,
        bb_upper=68_000.0, bb_lower=60_000.0, bb_mid=64_000.0,
        macd=150.0, macd_signal=100.0, macd_hist=50.0,
        atr_14=1_500.0, volume=5_000.0, volume_ma=4_000.0,
        trend=Trend.BULLISH, trend_strength=0.7,
    )
    analysis = MarketAnalysis(
        chart=chart,
        sentiment=SentimentData(symbol="BTC", score=0.2, fear_greed_index=55, btc_dominance=52.0),
        onchain=OnchainData(symbol="BTC", large_buys_24h=500_000.0, large_sells_24h=300_000.0),
        volatility=VolatilityData(
            symbol="BTC", atr_pct=0.023,
            volatility_regime=VolatilityRegime.MEDIUM,
            suggested_position_size_multiplier=1.0,
        ),
        liquidity=LiquidityData(
            symbol="BTC", bid_ask_spread_pct=0.0005,
            order_book_depth_buy=500_000.0, order_book_depth_sell=500_000.0,
            estimated_slippage_pct=0.0005, liquidity_score=0.85,
        ),
        anomaly=AnomalyReport(symbol="BTC", anomalies_detected=[], severity=AnomalySeverity.NONE),
    )
    signal = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.80,
        entry_price=65_000.0, stop_loss=63_000.0, take_profit=70_000.0,
        size_pct=0.02, leverage=3, reasoning="bullish",
    )
    snapshot = EquitySnapshot(
        source=EquitySource.HYPERLIQUID, is_paper=True,
        equity_usd=15_000.0, available_balance_usd=15_000.0,
        margin_used_usd=0.0, open_positions_count=0,
    )

    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=signal)
    fury._vision.close = AsyncMock()
    fury._portfolio.run = AsyncMock(return_value=snapshot)
    fury._daily_pnl.record_cycle = AsyncMock()

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
        reports = await fury.run_main_cycle()  # no override
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    assert len(reports) == 1
    fury._daily_pnl.record_cycle.assert_awaited_once()
    kwargs = fury._daily_pnl.record_cycle.await_args.kwargs
    # Effective equity comes from snapshot when no override
    assert kwargs["equity_usd"] == 15_000.0


@pytest.mark.asyncio
async def test_nick_fury_daily_pnl_uses_cli_override(monkeypatch):
    """When equity_usd CLI override is passed, DailyPnLWriter receives that value."""
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings
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
    from src.models.portfolio import EquitySnapshot, EquitySource
    from src.models.signal import TradeAction, TradingSignal

    fury = NickFury()

    chart = MarketData(
        symbol="BTC", timestamp=datetime.now(timezone.utc), timeframe="4h",
        price=65_000.0, rsi_14=55.0, ema_20=64_000.0, ema_50=62_000.0,
        bb_upper=68_000.0, bb_lower=60_000.0, bb_mid=64_000.0,
        macd=150.0, macd_signal=100.0, macd_hist=50.0,
        atr_14=1_500.0, volume=5_000.0, volume_ma=4_000.0,
        trend=Trend.BULLISH, trend_strength=0.7,
    )
    analysis = MarketAnalysis(
        chart=chart,
        sentiment=SentimentData(symbol="BTC", score=0.2, fear_greed_index=55, btc_dominance=52.0),
        onchain=OnchainData(symbol="BTC", large_buys_24h=500_000.0, large_sells_24h=300_000.0),
        volatility=VolatilityData(
            symbol="BTC", atr_pct=0.023,
            volatility_regime=VolatilityRegime.MEDIUM,
            suggested_position_size_multiplier=1.0,
        ),
        liquidity=LiquidityData(
            symbol="BTC", bid_ask_spread_pct=0.0005,
            order_book_depth_buy=500_000.0, order_book_depth_sell=500_000.0,
            estimated_slippage_pct=0.0005, liquidity_score=0.85,
        ),
        anomaly=AnomalyReport(symbol="BTC", anomalies_detected=[], severity=AnomalySeverity.NONE),
    )
    signal = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.80,
        entry_price=65_000.0, stop_loss=63_000.0, take_profit=70_000.0,
        size_pct=0.02, leverage=3, reasoning="bullish",
    )
    snapshot = EquitySnapshot(
        source=EquitySource.HYPERLIQUID, is_paper=True,
        equity_usd=15_000.0, available_balance_usd=15_000.0,
        margin_used_usd=0.0, open_positions_count=0,
    )

    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=signal)
    fury._vision.close = AsyncMock()
    fury._portfolio.run = AsyncMock(return_value=snapshot)
    fury._daily_pnl.record_cycle = AsyncMock()

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
        await fury.run_main_cycle(equity_usd=5_000.0)  # CLI override
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    fury._daily_pnl.record_cycle.assert_awaited_once()
    kwargs = fury._daily_pnl.record_cycle.await_args.kwargs
    # CLI override wins
    assert kwargs["equity_usd"] == 5_000.0
