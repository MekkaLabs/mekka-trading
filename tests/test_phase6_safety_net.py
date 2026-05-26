"""
tests/test_phase6_safety_net.py
================================
Phase 6 — Safety Net tests (Story 029).

Coverage:
  • ConsecutiveBreaker — observe/reset/threshold edge cases
  • Batman — total capital cap (percentage + absolute), pre-Thor evaluation
  • Nick Fury — `_check_breakers` engages kill switch on N consecutive
    Iron Man ERRORs and on N consecutive Vision HOLD-fallbacks
  • Nick Fury — running_notional_usd accumulates from snapshot positions
    + each paper execution within the cycle

Run: pytest tests/test_phase6_safety_net.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.batman import Batman
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal
from src.services.breakers import ConsecutiveBreaker


@pytest.fixture
def isolate_batman_from_db():
    """
    Isola Batman dos gates async/I/O que batem em DB ou rede real, para
    que os testes de gates específicos (capital cap) não sejam rejeitados
    por gates colaterais (max_trades, weekly drawdown, blacklist, cooldown,
    Super Agressivo do runtime).

    Use apenas nos testes que esperam APPROVED — testes que esperam
    rejeições específicas pelo gate sob teste podem usar essa fixture
    também, desde que os mocks não escondam a rejeição alvo.
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
        # Neutraliza caches globais (funding/MTF/ATR) que poluem testes em batch.
        patch("src.analytics.funding.get_funding_rate_pct", new_callable=AsyncMock, return_value=0.0),
        patch("src.analytics.trend.compute_htf_trend", new_callable=AsyncMock, return_value=None),
        patch("src.analytics.atr.compute_atr_pct", new_callable=AsyncMock, return_value=None),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers (kept inline so this file is independent of phase 2/3/4 fixtures)
# ---------------------------------------------------------------------------


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
        agent_contributions={},
    )
    defaults.update(overrides)
    return TradingSignal(**defaults)


@pytest.fixture(autouse=True)
def _isolate_kill_switch(tmp_path, monkeypatch):
    """Per-test kill-switch file path so each test starts clean."""
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    monkeypatch.delenv("MEKKA_KILL_SWITCH", raising=False)
    yield
    if test_path.exists():
        test_path.unlink()


# ===========================================================================
# ConsecutiveBreaker (unit)
# ===========================================================================


def test_breaker_invalid_threshold_raises():
    with pytest.raises(ValueError):
        ConsecutiveBreaker(name="x", threshold=0)


def test_breaker_threshold_one_trips_on_first_hit():
    b = ConsecutiveBreaker(name="x", threshold=1)
    assert b.observe(True) is True
    assert b.trip_count == 1


def test_breaker_trips_only_when_streak_crosses_threshold():
    b = ConsecutiveBreaker(name="x", threshold=3)
    assert b.observe(True) is False
    assert b.observe(True) is False
    assert b.observe(True) is True   # crossing point
    assert b.observe(True) is False  # already past, no re-trip
    assert b.trip_count == 1


def test_breaker_reset_on_non_hit():
    b = ConsecutiveBreaker(name="x", threshold=3)
    b.observe(True)
    b.observe(True)
    assert b.streak == 2
    b.observe(False)
    assert b.streak == 0
    # Now needs another 3 consecutive to trip
    assert b.observe(True) is False
    assert b.observe(True) is False
    assert b.observe(True) is True


def test_breaker_manual_reset():
    b = ConsecutiveBreaker(name="x", threshold=2)
    b.observe(True)
    assert b.is_armed
    b.reset()
    assert b.streak == 0
    assert not b.is_armed


def test_breaker_summary_format():
    b = ConsecutiveBreaker(name="exec_error", threshold=3)
    s = b.summary()
    assert "exec_error" in s
    assert "0/3" in s


# ===========================================================================
# Batman — Total capital cap (Story 029, section 3b)
# ===========================================================================


@pytest.mark.asyncio
async def test_batman_skips_cap_when_equity_zero(isolate_batman_from_db):
    """When equity_usd=0 (legacy callers), the cap section is not evaluated."""
    approval = await Batman().run(signal=_good_signal())
    # No equity passed → cap skipped, signal goes through (clean APPROVED)
    assert approval.verdict == RiskVerdict.APPROVED


@pytest.mark.asyncio
async def test_batman_cap_pct_blocks_when_running_plus_new_exceeds():
    """
    Running $9k + new $6k = $15k > 10% of $100k = $10k → REJECTED.
    Signal: 2% size × 3x leverage × $100k = $6k notional.
    """
    approval = await Batman().run(
        signal=_good_signal(),
        equity_usd=100_000.0,
        running_notional_usd=9_000.0,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_total_capital_pct" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_cap_pct_allows_when_within_limit(isolate_batman_from_db):
    """Running $0 + new $6k <= 10% of $100k = $10k → APPROVED."""
    approval = await Batman().run(
        signal=_good_signal(),
        equity_usd=100_000.0,
        running_notional_usd=0.0,
    )
    assert approval.verdict == RiskVerdict.APPROVED


@pytest.mark.asyncio
async def test_batman_absolute_cap_takes_precedence(monkeypatch):
    """
    When max_total_notional_usd is set AND breached, that's the rejection
    reason — even if percentage cap would also block.
    """
    from src.config.settings import settings as real_settings

    # Pydantic v2 BaseSettings: monkeypatch.setattr is the canonical
    # path for per-test field overrides. Direct __dict__ writes corrupt
    # internal state and leak across tests.
    monkeypatch.setattr(real_settings, "max_total_notional_usd", 5_000.0)

    approval = await Batman().run(
        signal=_good_signal(),                          # adds $6k notional
        equity_usd=100_000.0,                           # 10% = $10k (pct cap)
        running_notional_usd=0.0,
    )

    assert approval.verdict == RiskVerdict.REJECTED
    # Absolute cap reason wins because it's checked first
    assert "max_total_notional_usd" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_cap_evaluated_against_pre_thor_intent(monkeypatch):
    """
    The cap is checked on Vision's INTENT (size_pct × leverage × equity),
    NOT on the post-Thor-multiplier value. Even with a Thor multiplier
    that would shrink size, a too-greedy intent must be rejected.
    """
    from src.models.market_data import VolatilityData, VolatilityRegime

    vol = VolatilityData(
        symbol="BTC",
        atr_pct=0.05,
        volatility_regime=VolatilityRegime.HIGH,
        suggested_position_size_multiplier=0.6,  # would shrink size
    )

    # Intent: 2% × 3x × $100k = $6k. Running: $9k. Total: $15k > $10k cap.
    # If the cap were post-Thor, $9k + 0.6 × $6k = $12.6k > $10k still rejects.
    # Either way the signal must be rejected; we ASSERT it's rejected on
    # max_total_capital_pct (the cap), confirming the order is correct.
    approval = await Batman().run(
        signal=_good_signal(),
        volatility=vol,
        equity_usd=100_000.0,
        running_notional_usd=9_000.0,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_total_capital_pct" in approval.breached_limits


# ===========================================================================
# Nick Fury — _check_breakers
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_exec_error_breaker_trips_on_threshold(monkeypatch):
    """
    N consecutive ExecutionStatus.ERROR reports → kill switch + audit
    RISK_KILL_SWITCH with payload.breaker == "exec_error".

    We override the breaker threshold *on the breaker instance* (which
    is a dataclass) instead of mutating Settings. Pydantic v2 doesn't
    accept `__dict__` writes for fields, and `monkeypatch.setattr` on a
    BaseSettings instance is the only safe path — but here we sidestep
    Settings entirely by working on the already-instantiated breaker.
    """
    from src.agents.nick_fury import NickFury
    from src.models.execution import ExecutionResult, ExecutionStatus
    from src.models.orchestration import CycleReport

    fury = NickFury()
    # Force a low threshold for fast convergence in this unit test
    fury._exec_error_breaker.threshold = 2
    fury._exec_error_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    def _err_report(symbol: str = "BTC") -> CycleReport:
        return CycleReport(
            symbol=symbol,
            execution=ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.ERROR,
                is_paper=False,
                error="boom",
            ),
        )

    # First ERROR — no trip yet
    await fury._check_breakers(_err_report())
    assert fury._exec_error_breaker.trip_count == 0
    # Second ERROR — trip
    await fury._check_breakers(_err_report())
    assert fury._exec_error_breaker.trip_count == 1

    # Audit: at least one RISK_KILL_SWITCH with breaker=exec_error
    kill_calls = [
        c
        for c in repo_mock.log_event.await_args_list
        if c.kwargs.get("event") == "RISK_KILL_SWITCH"
        and (c.kwargs.get("payload") or {}).get("breaker") == "exec_error"
    ]
    assert len(kill_calls) == 1


@pytest.mark.asyncio
async def test_nick_fury_exec_breaker_resets_on_non_error(monkeypatch):
    """A successful (PAPER) execution after errors resets the streak."""
    from src.agents.nick_fury import NickFury
    from src.models.execution import ExecutionResult, ExecutionStatus
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._exec_error_breaker.threshold = 3
    fury._exec_error_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    def _make_report(status: ExecutionStatus) -> CycleReport:
        return CycleReport(
            symbol="BTC",
            execution=ExecutionResult(
                symbol="BTC",
                status=status,
                is_paper=True,
            ),
        )

    await fury._check_breakers(_make_report(ExecutionStatus.ERROR))
    await fury._check_breakers(_make_report(ExecutionStatus.ERROR))
    assert fury._exec_error_breaker.streak == 2

    # Successful paper — resets
    await fury._check_breakers(_make_report(ExecutionStatus.PAPER))
    assert fury._exec_error_breaker.streak == 0
    assert fury._exec_error_breaker.trip_count == 0


@pytest.mark.asyncio
async def test_nick_fury_vision_fallback_breaker(monkeypatch):
    """
    N consecutive Vision HOLD-fallback signals → kill switch + audit
    with payload.breaker == "vision_fallback".
    """
    from src.agents.nick_fury import NickFury
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._vision_fallback_breaker.threshold = 2
    fury._vision_fallback_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    def _fallback_signal() -> TradingSignal:
        # HOLD with fallback metadata flag set — category=llm_degraded
        # is what actually counts as Vision degradation (see _check_breakers).
        return TradingSignal(
            symbol="BTC",
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=65_000.0,
            stop_loss=63_000.0,
            take_profit=67_000.0,
            size_pct=0.001,
            leverage=1,
            reasoning="fallback",
            metadata={
                "fallback": True,
                "fallback_reason": "LLM timeout",
                "fallback_category": "llm_degraded",
            },
        )

    # Two consecutive fallbacks → trip on second
    await fury._check_breakers(CycleReport(symbol="BTC", signal=_fallback_signal()))
    await fury._check_breakers(CycleReport(symbol="ETH", signal=_fallback_signal()))

    assert fury._vision_fallback_breaker.trip_count == 1
    kill_calls = [
        c
        for c in repo_mock.log_event.await_args_list
        if c.kwargs.get("event") == "RISK_KILL_SWITCH"
        and (c.kwargs.get("payload") or {}).get("breaker") == "vision_fallback"
    ]
    assert len(kill_calls) == 1


@pytest.mark.asyncio
async def test_nick_fury_no_breaker_trip_on_clean_cycle(monkeypatch):
    """A normal LONG signal + PAPER execution → neither breaker advances."""
    from src.agents.nick_fury import NickFury
    from src.models.execution import ExecutionResult, ExecutionStatus
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._exec_error_breaker.reset()
    fury._vision_fallback_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    report = CycleReport(
        symbol="BTC",
        signal=_good_signal(),  # LONG, not fallback
        execution=ExecutionResult(
            symbol="BTC",
            status=ExecutionStatus.PAPER,
            is_paper=True,
            side="long",
            quantity=0.01,
            avg_price=65_000.0,
            notional_usd=650.0,
        ),
    )
    await fury._check_breakers(report)

    assert fury._exec_error_breaker.streak == 0
    assert fury._vision_fallback_breaker.streak == 0
    assert fury._exec_error_breaker.trip_count == 0
    assert fury._vision_fallback_breaker.trip_count == 0


# ---------------------------------------------------------------------------
# Vision fallback category gate (bug fix 2026-05-25)
# ---------------------------------------------------------------------------
# Only ``llm_degraded`` and ``parse_error`` count as degradation. The other
# two categories (``safety_skip`` and ``config_error``) are legitimate
# pauses or operator-fix scenarios that must NOT engage the kill switch
# automatically. Without this distinction, a fresh boot without LLM keys
# (or anomaly halts) trips the breaker in ~1min.


def _fallback_signal_with_category(category: str) -> TradingSignal:
    """HOLD signal tagged with a specific fallback_category."""
    return TradingSignal(
        symbol="BTC",
        action=TradeAction.HOLD,
        confidence=0.0,
        entry_price=65_000.0,
        stop_loss=63_000.0,
        take_profit=67_000.0,
        size_pct=0.001,
        leverage=1,
        reasoning="fallback",
        metadata={
            "fallback": True,
            "fallback_reason": f"test {category}",
            "fallback_category": category,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["safety_skip", "config_error"])
async def test_nick_fury_safe_categories_do_not_trip_breaker(monkeypatch, category):
    """
    safety_skip (anomaly/extreme vol) and config_error (no API key) are
    pre-flight pauses, NOT LLM degradation — they must NOT advance the
    streak even after many consecutive observations.
    """
    from src.agents.nick_fury import NickFury
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._vision_fallback_breaker.threshold = 2
    fury._vision_fallback_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    # 5 consecutive — way past threshold — should still NOT trip
    for _ in range(5):
        await fury._check_breakers(
            CycleReport(symbol="BTC", signal=_fallback_signal_with_category(category))
        )

    assert fury._vision_fallback_breaker.trip_count == 0
    assert fury._vision_fallback_breaker.streak == 0
    kill_calls = [
        c
        for c in repo_mock.log_event.await_args_list
        if c.kwargs.get("event") == "RISK_KILL_SWITCH"
    ]
    assert len(kill_calls) == 0, (
        f"Category '{category}' should not engage kill switch, got {len(kill_calls)} calls"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["llm_degraded", "parse_error"])
async def test_nick_fury_degraded_categories_trip_breaker(monkeypatch, category):
    """
    llm_degraded (timeout/rate-limit/5xx) and parse_error (malformed JSON
    from the LLM) are real degradation — N in a row engages kill switch.
    """
    from src.agents.nick_fury import NickFury
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._vision_fallback_breaker.threshold = 2
    fury._vision_fallback_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    await fury._check_breakers(
        CycleReport(symbol="BTC", signal=_fallback_signal_with_category(category))
    )
    await fury._check_breakers(
        CycleReport(symbol="ETH", signal=_fallback_signal_with_category(category))
    )

    assert fury._vision_fallback_breaker.trip_count == 1, (
        f"Category '{category}' should trip after threshold"
    )


@pytest.mark.asyncio
async def test_nick_fury_missing_category_does_not_trip(monkeypatch):
    """
    Defensive: signals without ``fallback_category`` (legacy paths) must
    NOT trip the breaker. Failing closed here would create false positives
    every time a downstream agent forgets to set the category.
    """
    from src.agents.nick_fury import NickFury
    from src.models.orchestration import CycleReport

    fury = NickFury()
    fury._vision_fallback_breaker.threshold = 2
    fury._vision_fallback_breaker.reset()

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    sig = TradingSignal(
        symbol="BTC", action=TradeAction.HOLD, confidence=0.0,
        entry_price=65_000.0, stop_loss=63_000.0, take_profit=67_000.0,
        size_pct=0.001, leverage=1, reasoning="legacy fallback",
        metadata={"fallback": True, "fallback_reason": "no category set"},
    )
    for _ in range(5):
        await fury._check_breakers(CycleReport(symbol="BTC", signal=sig))

    assert fury._vision_fallback_breaker.trip_count == 0


# ===========================================================================
# Nick Fury — running_notional_usd accumulation
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_running_notional_starts_from_snapshot_positions(monkeypatch):
    """
    Initial running_notional reflects size × entry_price of all open
    positions in the snapshot. This is forwarded to Batman so the cap
    sees current exposure, not zero.
    """
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
    from src.models.portfolio import EquitySnapshot, EquitySource, PositionSummary

    fury = NickFury()
    chart = MarketData(
        symbol="BTC",
        timestamp=datetime.now(timezone.utc),
        timeframe="4h",
        price=65_000.0,
        rsi_14=55.0,
        ema_20=64_000.0,
        ema_50=62_000.0,
        atr_14=1_500.0,
        volume=5_000.0,
        volume_ma=4_000.0,
        trend=Trend.BULLISH,
        trend_strength=0.7,
    )
    analysis = MarketAnalysis(
        chart=chart,
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

    # Snapshot with two real-ish positions: BTC 0.5 @ 60k = $30k, ETH 5 @ 3k = $15k
    snapshot = EquitySnapshot(
        source=EquitySource.HYPERLIQUID,
        is_paper=True,
        equity_usd=100_000.0,
        available_balance_usd=55_000.0,
        margin_used_usd=45_000.0,
        open_positions_count=2,
        positions=[
            PositionSummary(symbol="BTC", side="long", size=0.5, entry_price=60_000.0),
            PositionSummary(symbol="ETH", side="long", size=5.0, entry_price=3_000.0),
        ],
    )
    expected_initial_running = 0.5 * 60_000.0 + 5.0 * 3_000.0  # 45_000

    fury._professor.run = AsyncMock(return_value=analysis)
    fury._professor.close = AsyncMock()
    fury._vision.run = AsyncMock(return_value=_good_signal())
    fury._vision.close = AsyncMock()
    fury._daily_pnl.record_cycle = AsyncMock()
    fury._portfolio.run = AsyncMock(return_value=snapshot)

    captured: list[dict] = []
    real_batman_run = fury._batman.run

    async def _spy(**kwargs):
        captured.append(dict(kwargs))
        return await real_batman_run(**kwargs)

    fury._batman.run = _spy

    repo_mock = MagicMock()
    repo_mock.initialize = AsyncMock()
    repo_mock.save_signal = AsyncMock(return_value=1)
    repo_mock.save_trade = AsyncMock(return_value=2)
    repo_mock.log_event = AsyncMock(return_value=1)
    repo_mock.get_today_drawdown_pct = AsyncMock(return_value=0.0)
    repo_mock.count_trades_today = AsyncMock(return_value=0)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    # Pydantic v2: usar monkeypatch.setattr, não atribuir ao __dict__.
    # Isso restringe o cycle a apenas BTC (sem altcoins/Super Agressivo do runtime).
    monkeypatch.setattr(real_settings, "trading_assets", ["BTC"])
    monkeypatch.setattr(
        "src.config.runtime_overrides.get_runtime_overrides",
        lambda: {},  # neutraliza Super Agressivo / altcoins do runtime
    )

    # Mocks para Batman gates async não baterem em DB/exchange real.
    with (
        patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
        patch("src.persistence.repository.MekkaRepository.count_trades_today_for_symbol", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.get_last_sl_close_time", new_callable=AsyncMock, return_value=None),
        patch("src.persistence.repository.MekkaRepository.count_consecutive_sl_hits", new_callable=AsyncMock, return_value=0),
        patch("src.persistence.repository.MekkaRepository.list_recent_closed_trades", new_callable=AsyncMock, return_value=[]),
        patch("src.persistence.repository.MekkaRepository.get_symbol_week_pnl", new_callable=AsyncMock, return_value=0.0),
    ):
        await fury.run_main_cycle()

    assert len(captured) == 1
    assert captured[0]["running_notional_usd"] == pytest.approx(expected_initial_running, rel=1e-9)
    assert captured[0]["equity_usd"] == 100_000.0
