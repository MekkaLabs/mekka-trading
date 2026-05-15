"""
tests/test_phase5_safety_net.py
================================
Phase 5 — Safety Net tests (Story 029a).

These tests cristalize the three new defensive layers introduced by the
Safety Net story:

  1. ConsecutiveBreaker (passive counter).
  2. Batman total-capital cap (pct + absolute usd, with precedence).
  3. Nick Fury wiring — _check_breakers engages the kill switch and emits
     an audit event when either breaker trips.

Each Nick Fury test releases the kill switch in a finally block so it
does not leak to the next test (the flag is a real file in data/.kill_switch).

Run: pytest tests/test_phase5_safety_net.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.batman import Batman, release_kill_switch
from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.orchestration import CycleReport
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal
from src.services.breakers import ConsecutiveBreaker


# ===========================================================================
# 1. ConsecutiveBreaker — passive counter
# ===========================================================================


def test_breaker_rejects_threshold_below_one():
    with pytest.raises(ValueError):
        ConsecutiveBreaker(name="bad", threshold=0)


def test_breaker_trips_on_threshold_crossing():
    b = ConsecutiveBreaker(name="exec", threshold=3)

    assert b.observe(True) is False  # streak 1
    assert b.observe(True) is False  # streak 2
    assert b.observe(True) is True   # streak 3 → trip
    assert b.trip_count == 1
    assert b.is_armed is True


def test_breaker_does_not_re_trip_until_reset():
    """A 4th hit after a trip increments streak but must not re-trip."""
    b = ConsecutiveBreaker(name="exec", threshold=3)
    for _ in range(3):
        b.observe(True)
    # already tripped once
    assert b.observe(True) is False
    assert b.trip_count == 1


def test_breaker_non_hit_resets_streak():
    b = ConsecutiveBreaker(name="exec", threshold=3)
    b.observe(True)
    b.observe(True)
    assert b.streak == 2
    b.observe(False)
    assert b.streak == 0
    assert b.is_armed is False
    # And we can climb again from zero without leftover state
    assert b.observe(True) is False
    assert b.observe(True) is False
    assert b.observe(True) is True


def test_breaker_manual_reset_clears_streak_but_keeps_lifetime_count():
    b = ConsecutiveBreaker(name="exec", threshold=2)
    b.observe(True)
    b.observe(True)  # trip
    assert b.trip_count == 1
    b.reset()
    assert b.streak == 0
    assert b.trip_count == 1  # lifetime stays
    # Next trip increments lifetime
    b.observe(True)
    b.observe(True)
    assert b.trip_count == 2


# ===========================================================================
# 2. Batman — total capital cap
# ===========================================================================


def _bull_signal(symbol: str = "BTC", size_pct: float = 0.02, leverage: int = 3) -> TradingSignal:
    return TradingSignal(
        symbol=symbol,
        action=TradeAction.LONG,
        confidence=0.80,
        entry_price=65_000.0,
        stop_loss=63_000.0,
        take_profit=70_000.0,
        size_pct=size_pct,
        leverage=leverage,
        reasoning="bullish",
    )


@pytest.mark.asyncio
async def test_batman_blocks_when_running_notional_exceeds_pct_cap():
    """
    Equity 10k, signal wants 2% × 3x = $600 notional.
    Existing running notional is $700; cap_pct default 10% → cap_usd = $1000.
    700 + 600 = 1300 > 1000 → REJECTED with breached='max_total_capital_pct'.
    """
    approval = await Batman().run(
        signal=_bull_signal(size_pct=0.02, leverage=3),
        running_notional_usd=700.0,
        equity_usd=10_000.0,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_total_capital_pct" in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_passes_when_running_notional_under_pct_cap():
    """700 + 200 = 900 < 1000 cap → not blocked by cap_pct."""
    approval = await Batman().run(
        signal=_bull_signal(size_pct=0.01, leverage=2),  # 0.01 * 2 * 10000 = 200
        running_notional_usd=700.0,
        equity_usd=10_000.0,
    )
    assert "max_total_capital_pct" not in approval.breached_limits
    # And it should be APPROVED (or REDUCED, never REJECTED for this reason).
    assert approval.verdict in (RiskVerdict.APPROVED, RiskVerdict.REDUCED)


@pytest.mark.asyncio
async def test_batman_absolute_cap_takes_precedence(monkeypatch):
    """
    With max_total_notional_usd=$500, even a tiny signal blows the absolute cap
    if running_notional already used most of the budget. Absolute cap reported
    BEFORE the percentage cap, so breached_limits should contain
    'max_total_notional_usd' (and not 'max_total_capital_pct').
    """
    from src.config.settings import settings as real_settings
    monkeypatch.setattr(real_settings, "max_total_notional_usd", 500.0)

    approval = await Batman().run(
        signal=_bull_signal(size_pct=0.02, leverage=3),  # 600 USD intent
        running_notional_usd=0.0,
        equity_usd=10_000.0,
    )
    assert approval.verdict == RiskVerdict.REJECTED
    assert "max_total_notional_usd" in approval.breached_limits
    assert "max_total_capital_pct" not in approval.breached_limits


@pytest.mark.asyncio
async def test_batman_cap_skipped_when_equity_is_zero():
    """
    Belt-and-suspenders edge case: if effective equity is 0 (snapshot
    failure + no CLI override), the cap path is skipped entirely. We do
    not want to block trades on a broken portfolio read — Batman still
    has all its other gates.
    """
    approval = await Batman().run(
        signal=_bull_signal(size_pct=0.02, leverage=3),
        running_notional_usd=999_999.0,
        equity_usd=0.0,
    )
    assert "max_total_capital_pct" not in approval.breached_limits
    assert "max_total_notional_usd" not in approval.breached_limits


# ===========================================================================
# 3. Nick Fury — _check_breakers wiring
# ===========================================================================


def _exec_error_report(symbol: str = "BTC") -> CycleReport:
    """Build a CycleReport whose execution status is ERROR."""
    signal = _bull_signal(symbol=symbol)
    approval = RiskApproval(
        symbol=symbol,
        verdict=RiskVerdict.APPROVED,
        adjusted_size_pct=0.02,
        adjusted_leverage=3,
    )
    execution = ExecutionResult(
        symbol=symbol,
        status=ExecutionStatus.ERROR,
        is_paper=True,
        error_message="boom",
    )
    return CycleReport(
        symbol=symbol, signal=signal, approval=approval, execution=execution
    )


def _exec_paper_report(symbol: str = "BTC") -> CycleReport:
    signal = _bull_signal(symbol=symbol)
    approval = RiskApproval(
        symbol=symbol,
        verdict=RiskVerdict.APPROVED,
        adjusted_size_pct=0.02,
        adjusted_leverage=3,
    )
    execution = ExecutionResult(
        symbol=symbol,
        status=ExecutionStatus.PAPER,
        is_paper=True,
        notional_usd=600.0,
    )
    return CycleReport(
        symbol=symbol, signal=signal, approval=approval, execution=execution
    )


def _hold_signal(symbol: str, price: float, fallback: bool, confidence: float = 0.0) -> TradingSignal:
    """
    Build a HOLD TradingSignal with the same geometry Vision._fallback_hold
    uses (so it passes the Pydantic validator). The `fallback` flag toggles
    the metadata bit that Nick Fury's vision_fallback breaker watches.
    """
    return TradingSignal(
        symbol=symbol,
        action=TradeAction.HOLD,
        confidence=confidence,
        entry_price=price,
        stop_loss=price * 0.97,
        take_profit=price * 1.03,
        size_pct=0.001,
        leverage=1,
        reasoning="LLM fallback HOLD" if fallback else "market is choppy, sit out",
        metadata={"fallback": fallback, "reason": "openai_timeout"} if fallback else None,
    )


def _vision_fallback_report(symbol: str = "BTC") -> CycleReport:
    """A HOLD signal carrying metadata.fallback=True (Vision degraded)."""
    return CycleReport(
        symbol=symbol,
        signal=_hold_signal(symbol=symbol, price=65_000.0, fallback=True),
    )


def _vision_normal_hold_report(symbol: str = "BTC") -> CycleReport:
    """A HOLD signal that is NOT a fallback — normal market call."""
    return CycleReport(
        symbol=symbol,
        signal=_hold_signal(symbol=symbol, price=65_000.0, fallback=False, confidence=0.55),
    )


@pytest.mark.asyncio
async def test_nick_fury_breaker_engages_kill_switch_after_consecutive_exec_errors(
    monkeypatch,
):
    """
    With max_consecutive_exec_errors=3, the third ERROR must engage the
    kill switch and emit a RISK_KILL_SWITCH audit event.
    """
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings

    # Make sure no leftover file from a previous test sneaks in
    release_kill_switch()
    monkeypatch.setattr(real_settings, "max_consecutive_exec_errors", 3)

    fury = NickFury()
    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    try:
        # First two errors arm the breaker but do not engage the kill switch.
        await fury._check_breakers(_exec_error_report())
        await fury._check_breakers(_exec_error_report())
        # File-based kill switch must still be clear at this point
        from src.agents.batman import is_kill_switch_active

        assert is_kill_switch_active() is False
        risk_kill_calls_before = sum(
            1
            for c in repo_mock.log_event.await_args_list
            if c.kwargs.get("event") == "RISK_KILL_SWITCH"
        )
        assert risk_kill_calls_before == 0

        # Third error trips it
        await fury._check_breakers(_exec_error_report())
        assert is_kill_switch_active() is True
        risk_kill_calls = [
            c
            for c in repo_mock.log_event.await_args_list
            if c.kwargs.get("event") == "RISK_KILL_SWITCH"
        ]
        assert len(risk_kill_calls) == 1
        assert risk_kill_calls[0].kwargs.get("severity") == "ERROR"
        assert risk_kill_calls[0].kwargs.get("payload", {}).get("breaker") == "exec_error"
    finally:
        release_kill_switch()


@pytest.mark.asyncio
async def test_nick_fury_exec_error_streak_resets_on_paper_fill(monkeypatch):
    """A successful (non-error) execution must reset the exec_error streak."""
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings

    release_kill_switch()
    monkeypatch.setattr(real_settings, "max_consecutive_exec_errors", 3)

    fury = NickFury()
    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    try:
        await fury._check_breakers(_exec_error_report())  # streak 1
        await fury._check_breakers(_exec_error_report())  # streak 2
        await fury._check_breakers(_exec_paper_report())  # reset

        assert fury._exec_error_breaker.streak == 0
        # Two more errors should NOT trip yet (would have, if streak hadn't reset)
        await fury._check_breakers(_exec_error_report())
        await fury._check_breakers(_exec_error_report())
        from src.agents.batman import is_kill_switch_active

        assert is_kill_switch_active() is False
    finally:
        release_kill_switch()


@pytest.mark.asyncio
async def test_nick_fury_breaker_engages_kill_switch_after_consecutive_vision_fallbacks(
    monkeypatch,
):
    """
    With max_consecutive_vision_fallbacks=2, the second fallback HOLD must
    engage the kill switch and emit a RISK_KILL_SWITCH audit event tagged
    with breaker='vision_fallback'.
    """
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings

    release_kill_switch()
    monkeypatch.setattr(real_settings, "max_consecutive_vision_fallbacks", 2)

    fury = NickFury()
    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    try:
        await fury._check_breakers(_vision_fallback_report())  # streak 1
        await fury._check_breakers(_vision_fallback_report())  # streak 2 → trip

        from src.agents.batman import is_kill_switch_active

        assert is_kill_switch_active() is True
        risk_kill_calls = [
            c
            for c in repo_mock.log_event.await_args_list
            if c.kwargs.get("event") == "RISK_KILL_SWITCH"
        ]
        assert len(risk_kill_calls) == 1
        assert (
            risk_kill_calls[0].kwargs.get("payload", {}).get("breaker")
            == "vision_fallback"
        )
    finally:
        release_kill_switch()


@pytest.mark.asyncio
async def test_nick_fury_vision_streak_resets_on_normal_hold(monkeypatch):
    """
    A non-fallback HOLD (normal market read) must reset the vision_fallback
    streak — we only count *degraded* HOLDs.
    """
    from src.agents.nick_fury import NickFury
    from src.config.settings import settings as real_settings

    release_kill_switch()
    monkeypatch.setattr(real_settings, "max_consecutive_vision_fallbacks", 2)

    fury = NickFury()
    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    try:
        await fury._check_breakers(_vision_fallback_report())   # streak 1
        await fury._check_breakers(_vision_normal_hold_report())  # reset
        assert fury._vision_fallback_breaker.streak == 0

        # One more fallback alone is not enough to trip
        await fury._check_breakers(_vision_fallback_report())
        from src.agents.batman import is_kill_switch_active

        assert is_kill_switch_active() is False
    finally:
        release_kill_switch()
