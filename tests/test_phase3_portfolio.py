"""
tests/test_phase3_portfolio.py
==============================
Phase 3 — Portfolio Manager tests (Story 026).

Coverage:
  • PortfolioManager — paper fallback when wallet is placeholder
  • PortfolioManager — paper fallback when network call raises
  • PortfolioManager — successful parse of clearinghouseState
  • Nick Fury       — uses Portfolio Manager equity when no override
  • Nick Fury       — CLI `equity_usd` override wins over Portfolio Manager
  • Nick Fury       — open_positions from snapshot reaches Batman

Run: pytest tests/test_phase3_portfolio.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.portfolio_manager import PortfolioManager
from src.agents.nick_fury import NickFury
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
)
from src.models.portfolio import EquitySnapshot, EquitySource
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Helpers (keep in sync with phase 2 helpers — duplicated to keep tests
# independent and avoid cross-file fixture coupling)
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


def _good_signal() -> TradingSignal:
    return TradingSignal(
        symbol="BTC",
        action=TradeAction.LONG,
        confidence=0.80,
        entry_price=65_000.0,
        stop_loss=63_000.0,
        take_profit=70_000.0,
        size_pct=0.02,
        leverage=3,
        reasoning="bullish",
        agent_contributions={"Superman": "BULLISH"},
    )


# ===========================================================================
# Portfolio Manager — paper fallback paths
# ===========================================================================


@pytest.mark.asyncio
async def test_portfolio_paper_fallback_on_placeholder_wallet():
    """conftest sets HYPERLIQUID_WALLET_ADDRESS to all-zeros — that's the placeholder."""
    from src.config.settings import settings as real_settings

    old_exchange = real_settings.active_exchange
    real_settings.__dict__["active_exchange"] = "hyperliquid"
    try:
        snapshot = await PortfolioManager().run()
    finally:
        real_settings.__dict__["active_exchange"] = old_exchange

    assert snapshot.source == EquitySource.PAPER_FALLBACK
    assert snapshot.is_paper is True
    assert snapshot.equity_usd > 0  # paper_equity_usd default is 10_000
    assert snapshot.open_positions_count == 0
    assert snapshot.error is not None and "wallet" in snapshot.error.lower()


@pytest.mark.asyncio
async def test_portfolio_paper_fallback_on_network_error(monkeypatch):
    """When fetch raises, Portfolio Manager returns paper fallback with the error."""
    # Force a non-placeholder wallet so we exit the early-return branch
    from src.config.settings import settings as real_settings
    old_exchange = real_settings.active_exchange
    real_settings.__dict__["active_exchange"] = "hyperliquid"
    real_settings.__dict__["hyperliquid_wallet_address"] = "0xdeadbeef1234567890abcdef0000000000000000"

    pm = PortfolioManager()
    pm._fetch_clearinghouse_state = AsyncMock(side_effect=RuntimeError("HTTP 500"))

    try:
        snapshot = await pm.run()
    finally:
        real_settings.__dict__["active_exchange"] = old_exchange
        # Restore the placeholder so other tests stay isolated
        real_settings.__dict__["hyperliquid_wallet_address"] = (
            "0x0000000000000000000000000000000000000000"
        )

    assert snapshot.source == EquitySource.PAPER_FALLBACK
    assert snapshot.is_paper is True
    assert snapshot.error is not None and "Hyperliquid unreachable" in snapshot.error


@pytest.mark.asyncio
async def test_portfolio_parses_clearinghouse_state(monkeypatch):
    """Successful clearinghouseState response → HYPERLIQUID source with parsed positions."""
    from src.config.settings import settings as real_settings
    old_exchange = real_settings.active_exchange
    real_settings.__dict__["active_exchange"] = "hyperliquid"
    real_settings.__dict__["hyperliquid_wallet_address"] = "0xdeadbeef1234567890abcdef0000000000000000"

    raw_response: dict[str, Any] = {
        "marginSummary": {
            "accountValue": "12345.67",
            "totalMarginUsed": "234.56",
        },
        "withdrawable": "12000.0",
        "assetPositions": [
            {
                "type": "oneWay",
                "position": {
                    "coin": "BTC",
                    "szi": "0.5",
                    "entryPx": "65000.0",
                    "unrealizedPnl": "12.34",
                    "leverage": {"value": 3, "type": "cross"},
                },
            },
            {
                "type": "oneWay",
                "position": {
                    "coin": "ETH",
                    "szi": "-2.0",   # short
                    "entryPx": "3500.0",
                    "unrealizedPnl": "-5.0",
                    "leverage": {"value": 2},
                },
            },
            {
                # zero-size position should be ignored
                "position": {
                    "coin": "SOL",
                    "szi": "0",
                    "entryPx": "150.0",
                },
            },
        ],
    }

    pm = PortfolioManager()
    pm._fetch_clearinghouse_state = AsyncMock(return_value=raw_response)

    try:
        snapshot = await pm.run()
    finally:
        real_settings.__dict__["active_exchange"] = old_exchange
        real_settings.__dict__["hyperliquid_wallet_address"] = (
            "0x0000000000000000000000000000000000000000"
        )

    assert snapshot.source == EquitySource.HYPERLIQUID
    assert snapshot.equity_usd == pytest.approx(12345.67, rel=1e-6)
    assert snapshot.margin_used_usd == pytest.approx(234.56, rel=1e-6)
    assert snapshot.available_balance_usd == pytest.approx(12000.0, rel=1e-6)
    assert snapshot.open_positions_count == 2  # BTC + ETH; SOL skipped
    sides = {p.symbol: p.side for p in snapshot.positions}
    assert sides == {"BTC": "long", "ETH": "short"}


def test_portfolio_parses_bybit_ccxt_snapshot():
    pm = PortfolioManager()
    balance = {
        "info": {
            "result": {
                "list": [
                    {
                        "totalEquity": "9991.45",
                        "totalAvailableBalance": "9991.45",
                    }
                ]
            }
        },
        "free": {"USDT": 10000.0},
        "total": {"USDT": 10000.0},
    }
    positions = [
        {
            "symbol": "BTC/USDT:USDT",
            "side": "short",
            "contracts": 0.015,
            "entryPrice": 76500.5,
            "unrealizedPnl": 12.34,
            "leverage": 2,
            "info": {"size": "0.015", "symbol": "BTCUSDT"},
        },
        {
            "symbol": "ETH/USDT:USDT",
            "side": None,
            "contracts": 0.0,
            "entryPrice": None,
            "unrealizedPnl": None,
            "leverage": 10,
            "info": {"size": "0", "symbol": "ETHUSDT"},
        },
    ]

    snapshot = pm._parse_ccxt_snapshot("bybit", balance, positions)

    assert snapshot.source == EquitySource.BYBIT
    assert snapshot.equity_usd == pytest.approx(9991.45, rel=1e-6)
    assert snapshot.available_balance_usd == pytest.approx(9991.45, rel=1e-6)
    assert snapshot.margin_used_usd == pytest.approx(0.0, rel=1e-6)
    assert snapshot.open_positions_count == 1
    assert snapshot.positions[0].symbol == "BTC"
    assert snapshot.positions[0].side == "short"
    assert snapshot.positions[0].size == pytest.approx(0.015, rel=1e-6)
    assert snapshot.positions[0].entry_price == pytest.approx(76500.5, rel=1e-6)


# ===========================================================================
# Nick Fury — Portfolio Manager wiring
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_uses_portfolio_manager_equity(monkeypatch):
    """
    When Nick Fury runs without an explicit equity override, it sources
    equity from Portfolio Manager and forwards open_positions to Batman.
    """
    from src.config.settings import settings as real_settings

    fury = NickFury()
    analysis = _btc_analysis()
    signal = _good_signal()

    # Mock the analysis & decision side
    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=signal)
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()  # Story 027 wiring

    # Portfolio Manager returns a known synthetic snapshot
    snapshot = EquitySnapshot(
        source=EquitySource.HYPERLIQUID,
        is_paper=True,
        equity_usd=25_000.0,
        available_balance_usd=24_000.0,
        margin_used_usd=1_000.0,
        open_positions_count=2,  # already 2 open — Batman should see this
        positions=[],
    )
    fury._portfolio.run = AsyncMock(return_value=snapshot)

    # Capture what Batman receives
    real_batman_run = fury._batman.run
    captured: dict = {}

    async def _spy_batman_run(**kwargs):
        captured.update(kwargs)
        return await real_batman_run(**kwargs)

    fury._batman.run = _spy_batman_run

    # Repository mock
    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(return_value=42)
    repo_mock.save_trade = AsyncMock(return_value=99)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.01)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    # Restrict trading_assets to BTC for determinism
    real_settings.__dict__["trading_assets"] = ["BTC"]

    try:
        reports = await fury.run_main_cycle()  # NO equity_usd override
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    # Equity from Portfolio Manager (25_000), not the legacy default (10_000)
    # We check by computing the expected notional from the executed report
    assert len(reports) == 1
    report = reports[0]
    assert report.execution is not None
    # notional = equity * size_pct * leverage = 25_000 * 0.02 * 3 = 1500 (±0.5% for B5 slippage)
    assert report.execution.notional_usd == pytest.approx(1500.0, rel=0.005)

    # Batman saw open_positions=2 from the snapshot
    assert captured.get("open_positions") == 2

    # Snapshot was logged
    assert any(
        call_args.kwargs.get("event", "").startswith("SNAPSHOT_")
        for call_args in repo_mock.log_event.await_args_list
    )


@pytest.mark.asyncio
async def test_nick_fury_equity_override_wins(monkeypatch):
    """CLI `equity_usd` override beats Portfolio Manager."""
    from src.config.settings import settings as real_settings

    fury = NickFury()
    fury._professor.run = AsyncMock(return_value=_btc_analysis())
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=_good_signal())
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()  # Story 027 wiring
    fury._portfolio.run = AsyncMock(
        return_value=EquitySnapshot(
            source=EquitySource.HYPERLIQUID,
            is_paper=True,
            equity_usd=99_999.0,
            available_balance_usd=99_999.0,
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
        reports = await fury.run_main_cycle(equity_usd=5_000.0)  # explicit override
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    # notional uses 5_000 (override), not 99_999 (snapshot)
    # 5000 * 0.02 * 3 = 300 (±0.5% for B5 slippage)
    assert reports[0].execution.notional_usd == pytest.approx(300.0, rel=0.005)


@pytest.mark.asyncio
async def test_nick_fury_open_positions_increment_during_cycle(monkeypatch):
    """
    When the cycle executes a paper trade, the running open_positions
    count must increment for the next symbol so Batman sees the rolling total.
    """
    from src.config.settings import settings as real_settings

    fury = NickFury()
    fury._professor.run = AsyncMock(return_value=_btc_analysis())
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=_good_signal())
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()  # Story 027 wiring
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

    captured_open: list[int] = []
    real_batman_run = fury._batman.run

    async def _spy_batman_run(**kwargs):
        captured_open.append(kwargs.get("open_positions", -1))
        return await real_batman_run(**kwargs)

    fury._batman.run = _spy_batman_run

    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(return_value=1)
    repo_mock.save_trade = AsyncMock(return_value=2)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.0)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    # Two assets so we can check the increment between iterations
    real_settings.__dict__["trading_assets"] = ["BTC", "ETH"]
    try:
        await fury.run_main_cycle()
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    assert captured_open == [0, 1]  # second symbol sees the just-opened paper position
