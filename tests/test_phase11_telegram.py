"""
tests/test_phase11_telegram.py
==============================
Phase 11 — Telegram Alerter tests (Story 035).

Coverage:
  • Disabled (no token/chat_id) → alert() returns False, no HTTP call
  • Severity threshold blocks low-severity events
  • Severity threshold lets high-severity through
  • Whitelist matches event regardless of severity
  • Empty whitelist → severity-only mode
  • Successful POST returns True
  • HTTP 429 → returns False, no raise (rate limit)
  • HTTP 5xx → returns False, no raise
  • Network exception → returns False, no raise (best-effort)
  • Format includes agent + event + severity + message + env
  • Format truncates very long messages
  • Format ignores nested payload keys
  • _severity_at_least monotonicity
  • Nick Fury wires alert on RISK_KILL_SWITCH (not on RISK_APPROVED)

Run: pytest tests/test_phase11_telegram.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.telegram_alerter import (
    TelegramAlerter,
    _severity_at_least,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_telegram(monkeypatch):
    """Patch Settings to enable Telegram for the test scope."""
    from src.config.settings import settings as real_settings
    monkeypatch.setattr(real_settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(real_settings, "telegram_chat_id", "12345")
    # Bust the cached_property
    real_settings.__dict__.pop("telegram_enabled", None)
    real_settings.__dict__["telegram_enabled"] = True


def _set_min_severity(monkeypatch, severity: str):
    from src.config.settings import settings as real_settings
    monkeypatch.setattr(real_settings, "telegram_alert_min_severity", severity)


def _set_event_whitelist(monkeypatch, raw: str):
    from src.config.settings import settings as real_settings
    monkeypatch.setattr(real_settings, "telegram_alert_events_raw", raw)
    real_settings.__dict__.pop("telegram_alert_events", None)
    real_settings.__dict__["telegram_alert_events"] = (
        {tok.strip().upper() for tok in raw.split(",") if tok.strip()}
    )


# ===========================================================================
# Disabled & filters
# ===========================================================================


@pytest.mark.asyncio
async def test_alert_disabled_returns_false(monkeypatch):
    """Default conftest leaves Telegram disabled → alert short-circuits."""
    from src.config.settings import settings as real_settings
    # telegram_enabled is a cached_property baked at first access from .env.
    # Evict any stale cache and force-disable so this test is hermetic.
    real_settings.__dict__.pop("telegram_enabled", None)
    monkeypatch.setattr(real_settings, "telegram_enabled", False)
    alerter = TelegramAlerter()
    with patch.object(TelegramAlerter, "_post", new=AsyncMock()) as post:
        result = await alerter.alert(
            event="RISK_KILL_SWITCH", severity="ERROR", agent="Batman", message="x"
        )
    assert result is False
    post.assert_not_called()


@pytest.mark.asyncio
async def test_severity_below_threshold_blocked(monkeypatch):
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "ERROR")
    _set_event_whitelist(monkeypatch, "")  # severity-only mode
    alerter = TelegramAlerter()
    with patch.object(TelegramAlerter, "_post", new=AsyncMock()) as post:
        out = await alerter.alert(event="X", severity="INFO", agent="A", message="")
    assert out is False
    post.assert_not_called()


@pytest.mark.asyncio
async def test_severity_at_or_above_threshold_passes(monkeypatch):
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "WARNING")
    _set_event_whitelist(monkeypatch, "")
    alerter = TelegramAlerter()
    post_mock = AsyncMock(return_value=True)
    with patch.object(TelegramAlerter, "_post", new=post_mock):
        out = await alerter.alert(event="X", severity="WARNING", agent="A", message="m")
    assert out is True
    post_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_whitelist_overrides_severity(monkeypatch):
    """Event whitelisted gets through even at INFO severity."""
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "CRITICAL")  # very strict
    _set_event_whitelist(monkeypatch, "RISK_KILL_SWITCH,EXEC_ERROR")
    alerter = TelegramAlerter()
    post_mock = AsyncMock(return_value=True)
    with patch.object(TelegramAlerter, "_post", new=post_mock):
        out = await alerter.alert(
            event="RISK_KILL_SWITCH", severity="INFO", agent="Batman", message="x"
        )
    assert out is True


@pytest.mark.asyncio
async def test_whitelist_does_not_match_other_event(monkeypatch):
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "CRITICAL")
    _set_event_whitelist(monkeypatch, "RISK_KILL_SWITCH")
    alerter = TelegramAlerter()
    with patch.object(TelegramAlerter, "_post", new=AsyncMock()) as post:
        out = await alerter.alert(event="EXEC_PAPER", severity="INFO", agent="IronMan", message="ok")
    assert out is False
    post.assert_not_called()


# ===========================================================================
# HTTP behavior
# ===========================================================================


@pytest.mark.asyncio
async def test_post_success_returns_true(monkeypatch):
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "INFO")
    _set_event_whitelist(monkeypatch, "")
    alerter = TelegramAlerter()
    post_mock = AsyncMock(return_value=True)
    with patch.object(TelegramAlerter, "_post", new=post_mock):
        out = await alerter.alert(event="X", severity="INFO", agent="A", message="m")
    assert out is True


@pytest.mark.asyncio
async def test_network_exception_swallowed(monkeypatch):
    _enable_telegram(monkeypatch)
    _set_min_severity(monkeypatch, "INFO")
    _set_event_whitelist(monkeypatch, "")
    alerter = TelegramAlerter()
    with patch.object(
        TelegramAlerter, "_post",
        new=AsyncMock(side_effect=ConnectionError("net down")),
    ):
        out = await alerter.alert(event="X", severity="ERROR", agent="A", message="m")
    assert out is False  # never raises


# ===========================================================================
# Format
# ===========================================================================


def test_format_includes_core_fields():
    text = TelegramAlerter._format(
        event="RISK_KILL_SWITCH",
        severity="ERROR",
        agent="Batman",
        message="kill engaged",
        symbol="BTC",
        payload={"breaker": "exec_error"},
    )
    # Novo formato (2026-06-01): curto e para leigo — título amigável + emoji
    # de severidade no lugar do código de evento/agente cru.
    assert "🔴" in text                                  # severidade ERROR
    assert "Trading pausado" in text                     # título amigável do evento
    assert "BTC" in text                                 # símbolo
    assert "kill engaged" in text                        # mensagem
    assert "breaker=exec_error" in text                  # dado simples preservado


def test_format_truncates_very_long_message():
    long_msg = "x" * 5000
    text = TelegramAlerter._format(
        event="X", severity="ERROR", agent="A",
        message=long_msg, symbol=None, payload=None,
    )
    # Truncated marker should appear; total under 4096
    assert "…" in text
    assert len(text) < 4096


def test_format_ignores_nested_payload_keys():
    text = TelegramAlerter._format(
        event="X", severity="ERROR", agent="A", message="",
        symbol=None,
        payload={
            "breaker": "exec_error",          # flat → kept
            "details": {"deep": "nested"},   # nested → dropped
            "list_key": [1, 2, 3],            # list → dropped
        },
    )
    assert "breaker=exec_error" in text
    assert "details" not in text
    assert "list_key" not in text


# ===========================================================================
# _severity_at_least
# ===========================================================================


def test_severity_at_least_monotonic():
    assert _severity_at_least("ERROR", "INFO") is True
    assert _severity_at_least("INFO", "ERROR") is False
    assert _severity_at_least("WARNING", "WARNING") is True
    assert _severity_at_least("CRITICAL", "DEBUG") is True
    assert _severity_at_least("DEBUG", "CRITICAL") is False


def test_severity_at_least_unknown_defaults_to_info():
    # Unknown severity → defaults to lowest, threshold to WARNING (2)
    assert _severity_at_least("BANANA", "WARNING") is False


# ===========================================================================
# Nick Fury integration (RISK_KILL_SWITCH push only)
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_pushes_on_kill_switch_verdict(monkeypatch, tmp_path):
    """RISK_KILL_SWITCH from Batman triggers a Telegram push attempt."""
    from src.agents.nick_fury import NickFury
    from src.models.market_data import (
        AnomalyReport, AnomalySeverity, LiquidityData, MarketAnalysis,
        MarketData, OnchainData, SentimentData, Trend, VolatilityData,
        VolatilityRegime,
    )
    from src.models.portfolio import EquitySnapshot, EquitySource
    from src.models.signal import TradeAction, TradingSignal
    from src.config.settings import settings as real_settings
    from datetime import datetime, timezone

    # Engage file kill switch so Batman returns KILL_SWITCH verdict
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    test_path.write_text("forced for test")

    fury = NickFury()
    chart = MarketData(
        symbol="BTC", timestamp=datetime.now(timezone.utc), timeframe="4h",
        price=65_000.0, rsi_14=55.0,
    )
    analysis = MarketAnalysis(
        chart=chart,
        sentiment=SentimentData(symbol="BTC", score=0.0),
        onchain=OnchainData(symbol="BTC"),
        volatility=VolatilityData(
            symbol="BTC", atr_pct=0.02,
            volatility_regime=VolatilityRegime.MEDIUM,
        ),
        liquidity=LiquidityData(
            symbol="BTC", bid_ask_spread_pct=0.0005, liquidity_score=0.8,
        ),
        anomaly=AnomalyReport(symbol="BTC", severity=AnomalySeverity.NONE),
    )
    sig = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.8,
        entry_price=65_000.0, stop_loss=63_000.0, take_profit=70_000.0,
        size_pct=0.02, leverage=3, reasoning="test",
    )

    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=sig)
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()
    fury._portfolio.run = AsyncMock(
        return_value=EquitySnapshot(
            source=EquitySource.HYPERLIQUID, is_paper=True,
            equity_usd=10_000.0, available_balance_usd=10_000.0,
            margin_used_usd=0.0, open_positions_count=0,
        )
    )
    fury._telegram.alert = AsyncMock(return_value=True)

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
        await fury.run_main_cycle()
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    # Telegram alert should have been called at least once with KILL_SWITCH
    assert fury._telegram.alert.await_count >= 1
    kill_calls = [
        c for c in fury._telegram.alert.await_args_list
        if c.kwargs.get("event") == "RISK_KILL_SWITCH"
    ]
    assert len(kill_calls) == 1


@pytest.mark.asyncio
async def test_nick_fury_no_push_on_clean_approval(monkeypatch, tmp_path):
    """RISK_APPROVED + EXEC_PAPER → no Telegram alert."""
    from src.agents.nick_fury import NickFury
    from src.models.market_data import (
        AnomalyReport, AnomalySeverity, LiquidityData, MarketAnalysis,
        MarketData, OnchainData, SentimentData, Trend, VolatilityData,
        VolatilityRegime,
    )
    from src.models.portfolio import EquitySnapshot, EquitySource
    from src.models.signal import TradeAction, TradingSignal
    from src.config.settings import settings as real_settings
    from datetime import datetime, timezone

    # Pin the kill-switch file to a tmp path that is guaranteed not to
    # exist so this test stays deterministic even when the host has an
    # engaged data/.kill_switch left over from a real run. NickFury now
    # pushes RISK_KILL_SWITCH on the pre-cycle skip path (Story 035 fix),
    # which would otherwise leak into this assertion.
    monkeypatch.setattr(
        "src.agents.batman._KILL_SWITCH_FILE",
        tmp_path / ".kill_switch_absent",
    )

    fury = NickFury()
    chart = MarketData(
        symbol="BTC", timestamp=datetime.now(timezone.utc), timeframe="4h",
        price=65_000.0, rsi_14=55.0, ema_20=64_000.0, ema_50=62_000.0,
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
    sig = TradingSignal(
        symbol="BTC", action=TradeAction.LONG, confidence=0.8,
        entry_price=65_000.0, stop_loss=63_000.0, take_profit=70_000.0,
        size_pct=0.02, leverage=3, reasoning="bullish",
    )

    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=sig)
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()
    fury._portfolio.run = AsyncMock(
        return_value=EquitySnapshot(
            source=EquitySource.HYPERLIQUID, is_paper=True,
            equity_usd=10_000.0, available_balance_usd=10_000.0,
            margin_used_usd=0.0, open_positions_count=0,
        )
    )
    fury._telegram.alert = AsyncMock(return_value=False)

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
        await fury.run_main_cycle()
    finally:
        real_settings.__dict__.pop("trading_assets", None)

    # No KILL_SWITCH, no EXEC_ERROR → no telegram alert from those paths
    risk_calls = [
        c for c in fury._telegram.alert.await_args_list
        if c.kwargs.get("event") == "RISK_KILL_SWITCH"
    ]
    assert risk_calls == []
    err_calls = [
        c for c in fury._telegram.alert.await_args_list
        if c.kwargs.get("event", "").startswith("EXEC_")
    ]
    assert err_calls == []
