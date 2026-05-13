"""
tests/test_phase7_wolverine.py
==============================
Phase 7 — Wolverine Recovery Agent tests (Story 030).

Coverage:
  • Wolverine — empty snapshot returns empty plan, no kill switch
  • Wolverine — long position with current_price → unrealized PnL math
  • Wolverine — emergency loss triggers EMERGENCY_CLOSE
  • Wolverine — trailing profit triggers TRAIL_STOP with new SL
  • Wolverine — tighten loss triggers TIGHTEN_STOP
  • Wolverine — scale-out profit triggers SCALE_OUT
  • Wolverine — short position math (entry - price) * size
  • Wolverine — current_price omitted falls back to position.unrealized_pnl_usd
  • Wolverine — intraday drawdown breach engages kill switch and forces
    EMERGENCY_CLOSE on every position
  • Wolverine — when kill_switch persistence fails, plan still returns
  • Nick Fury — run_monitor_cycle calls wolverine and persists plan
  • Nick Fury — run_monitor_cycle short-circuits when kill switch already on

Run: pytest tests/test_phase7_wolverine.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.wolverine import Wolverine
from src.models.portfolio import EquitySnapshot, EquitySource, PositionSummary
from src.models.recovery import RecoveryAction, RecoveryPlan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_kill_switch(tmp_path, monkeypatch):
    """Per-test kill-switch file path so every test starts clean."""
    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    monkeypatch.delenv("MEKKA_KILL_SWITCH", raising=False)
    yield
    if test_path.exists():
        test_path.unlink()


def _snapshot(positions: list[PositionSummary], equity: float = 100_000.0) -> EquitySnapshot:
    return EquitySnapshot(
        source=EquitySource.HYPERLIQUID,
        is_paper=True,
        equity_usd=equity,
        available_balance_usd=equity,
        margin_used_usd=0.0,
        open_positions_count=len(positions),
        positions=positions,
    )


# ===========================================================================
# Wolverine — pure logic
# ===========================================================================


@pytest.mark.asyncio
async def test_empty_snapshot_returns_empty_plan():
    snap = _snapshot(positions=[], equity=10_000.0)
    plan: RecoveryPlan = await Wolverine().run(snapshot=snap)

    assert plan.positions == []
    assert plan.intraday_drawdown_pct == 0.0
    assert plan.kill_switch_engaged is False
    assert "No open positions" in plan.notes


@pytest.mark.asyncio
async def test_long_unrealized_pnl_math():
    """+1% move on a long: pnl = (current - entry) * size."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos])
    plan = await Wolverine().run(
        snapshot=snap,
        current_prices={"BTC": 60_600.0},
    )
    assert len(plan.positions) == 1
    update = plan.positions[0]
    assert update.unrealized_pnl_usd == pytest.approx(600.0, abs=1e-6)


@pytest.mark.asyncio
async def test_short_unrealized_pnl_math():
    """price drop on a short: pnl = (entry - current) * size."""
    pos = PositionSummary(symbol="ETH", side="short", size=2.0, entry_price=3_500.0)
    snap = _snapshot([pos])
    plan = await Wolverine().run(snapshot=snap, current_prices={"ETH": 3_400.0})
    update = plan.positions[0]
    assert update.unrealized_pnl_usd == pytest.approx(200.0, abs=1e-6)


@pytest.mark.asyncio
async def test_no_current_price_falls_back_to_snapshot_pnl():
    """When current_prices omits a symbol, use the snapshot's own unrealized_pnl_usd."""
    pos = PositionSummary(
        symbol="BTC",
        side="long",
        size=1.0,
        entry_price=60_000.0,
        unrealized_pnl_usd=123.45,
    )
    snap = _snapshot([pos])
    plan = await Wolverine().run(snapshot=snap)  # no current_prices
    update = plan.positions[0]
    assert update.unrealized_pnl_usd == pytest.approx(123.45, abs=1e-6)


@pytest.mark.asyncio
async def test_emergency_loss_triggers_emergency_close():
    """-6% pnl ≥ -5% threshold → EMERGENCY_CLOSE."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)  # huge equity → no DD breach
    plan = await Wolverine().run(
        snapshot=snap,
        current_prices={"BTC": 56_400.0},  # -6%
    )
    assert plan.positions[0].action == RecoveryAction.EMERGENCY_CLOSE
    assert "emergency" in plan.positions[0].reason.lower()


@pytest.mark.asyncio
async def test_tighten_loss_triggers_tighten_stop():
    """-2% pnl: -1.5% < -2% < -5% → TIGHTEN_STOP."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)
    plan = await Wolverine().run(snapshot=snap, current_prices={"BTC": 58_800.0})  # -2%
    update = plan.positions[0]
    assert update.action == RecoveryAction.TIGHTEN_STOP
    assert update.new_stop_loss is not None
    # SL is 0.5% below current price for a long
    assert update.new_stop_loss == pytest.approx(58_800.0 * (1 - 0.005), abs=1e-3)


@pytest.mark.asyncio
async def test_trail_profit_triggers_trail_stop():
    """+3% pnl: +2% < +3% < +5% → TRAIL_STOP."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)
    plan = await Wolverine().run(snapshot=snap, current_prices={"BTC": 61_800.0})  # +3%
    update = plan.positions[0]
    assert update.action == RecoveryAction.TRAIL_STOP
    assert update.new_stop_loss is not None
    assert update.new_stop_loss == pytest.approx(61_800.0 * (1 - 0.005), abs=1e-3)


@pytest.mark.asyncio
async def test_scale_out_profit_triggers_scale_out():
    """+6% pnl ≥ +5% threshold → SCALE_OUT."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)
    plan = await Wolverine().run(snapshot=snap, current_prices={"BTC": 63_600.0})  # +6%
    update = plan.positions[0]
    assert update.action == RecoveryAction.SCALE_OUT


@pytest.mark.asyncio
async def test_hold_when_pnl_in_no_action_band():
    """+1% pnl: between thresholds → HOLD."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)
    plan = await Wolverine().run(snapshot=snap, current_prices={"BTC": 60_600.0})  # +1%
    update = plan.positions[0]
    assert update.action == RecoveryAction.HOLD
    assert update.new_stop_loss is None  # no SL change for HOLD


# ===========================================================================
# Wolverine — kill switch backstop
# ===========================================================================


@pytest.mark.asyncio
async def test_intraday_drawdown_breach_engages_kill_switch():
    """
    Aggregate unrealized loss ≥ max_daily_drawdown_pct of equity →
    Wolverine engages kill switch + forces EMERGENCY_CLOSE on every
    position.
    """
    # equity 10k; default max_daily_drawdown_pct = 0.10 → breach at -1000 USD
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=10_000.0)
    plan = await Wolverine().run(
        snapshot=snap,
        current_prices={"BTC": 58_500.0},  # -1500 USD upnl → 15% > 10%
    )
    assert plan.kill_switch_engaged is True
    assert plan.intraday_drawdown_pct >= 0.10
    # Every position forced to EMERGENCY_CLOSE
    for u in plan.positions:
        assert u.action == RecoveryAction.EMERGENCY_CLOSE
        assert "intraday drawdown" in u.reason.lower()


@pytest.mark.asyncio
async def test_kill_switch_persistence_failure_does_not_raise(monkeypatch):
    """If engage_kill_switch raises (file system error), Wolverine still returns a plan."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=10_000.0)

    monkeypatch.setattr(
        "src.agents.wolverine.engage_kill_switch",
        lambda reason: (_ for _ in ()).throw(OSError("disk full")),
    )

    plan = await Wolverine().run(
        snapshot=snap,
        current_prices={"BTC": 58_500.0},  # would breach
    )
    assert plan.kill_switch_engaged is False  # failed to persist, but no raise
    assert "kill_switch failed" in plan.notes.lower() or "kill" in plan.notes.lower()


@pytest.mark.asyncio
async def test_no_kill_switch_when_drawdown_within_limit():
    """Aggregate drawdown < limit → kill switch not engaged."""
    pos = PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)
    snap = _snapshot([pos], equity=1_000_000.0)
    plan = await Wolverine().run(snapshot=snap, current_prices={"BTC": 59_000.0})
    assert plan.kill_switch_engaged is False


# ===========================================================================
# Nick Fury — monitor cycle wired with Wolverine
# ===========================================================================


@pytest.mark.asyncio
async def test_nick_fury_monitor_cycle_calls_wolverine(monkeypatch):
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    snapshot = _snapshot(
        [PositionSummary(symbol="BTC", side="long", size=1.0, entry_price=60_000.0)],
        equity=100_000.0,
    )
    fury._portfolio.run = AsyncMock(return_value=snapshot)
    fury._wolverine.run = AsyncMock(
        return_value=RecoveryPlan(positions=[], intraday_drawdown_pct=0.0, kill_switch_engaged=False)
    )

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    result = await fury.run_monitor_cycle()
    assert result["status"] == "ok"
    fury._portfolio.run.assert_awaited_once()
    fury._wolverine.run.assert_awaited_once()
    # Audit event was logged with the recovery plan
    assert any(
        c.kwargs.get("event") == "MONITOR_RECOVERY_PLAN"
        for c in repo_mock.log_event.await_args_list
    )


@pytest.mark.asyncio
async def test_nick_fury_monitor_cycle_short_circuits_when_kill_switch_active(
    tmp_path, monkeypatch
):
    """If the kill switch is already engaged, monitor cycle returns immediately."""
    from src.agents.nick_fury import NickFury

    test_path = tmp_path / ".kill_switch"
    monkeypatch.setattr("src.agents.batman._KILL_SWITCH_FILE", test_path)
    test_path.write_text("halted")

    fury = NickFury()
    fury._portfolio.run = AsyncMock()
    fury._wolverine.run = AsyncMock()

    result = await fury.run_monitor_cycle()
    assert result["status"] == "halted"
    assert result["reason"] == "kill_switch"
    fury._portfolio.run.assert_not_called()
    fury._wolverine.run.assert_not_called()


@pytest.mark.asyncio
async def test_nick_fury_monitor_cycle_handles_wolverine_failure(monkeypatch):
    """When Wolverine raises, monitor cycle returns error and does not propagate."""
    from src.agents.nick_fury import NickFury

    fury = NickFury()
    snapshot = _snapshot(positions=[], equity=10_000.0)
    fury._portfolio.run = AsyncMock(return_value=snapshot)
    fury._wolverine.run = AsyncMock(side_effect=RuntimeError("classifier exploded"))

    repo_mock = MagicMock()
    repo_mock.log_event = AsyncMock(return_value=1)
    monkeypatch.setattr("src.agents.nick_fury.MekkaRepository", repo_mock)

    result = await fury.run_monitor_cycle()
    assert result["status"] == "error"
    assert "classifier exploded" in result["reason"]
