"""
src/agents/wolverine.py
=======================
Wolverine — Recovery Agent (Story 030).

Wolverine runs in the **monitor cycle** (default every 5 min, between
the 4h main cycles). For each open position in the portfolio he:

  1. Computes unrealized PnL using the latest market price.
  2. Suggests an action (HOLD / TIGHTEN_STOP / TRAIL_STOP / SCALE_OUT
     / CLOSE / EMERGENCY_CLOSE).
  3. Aggregates intraday drawdown across all positions.
  4. **Engages the kill switch** if intraday drawdown breaches
     `settings.max_daily_drawdown_pct` (single defensive trip — not a
     replacement for Batman's per-signal guard, but a backstop for
     fast moves between cycles).

Hard rules
----------
  • **Read-only on the exchange.** Wolverine doesn't place, modify, or
    cancel real orders. It produces a `RecoveryPlan`. Iron Man stays
    the only path to the SDK.
  • **Defensive degradation.** Missing prices, missing snapshot
    positions, math errors → Wolverine returns an empty plan and
    audits the failure. Never raises.
  • **Idempotent.** Same snapshot in → same plan out. No internal
    counters, no streaks (those live in `ConsecutiveBreaker`).

Wire-up: `NickFury._run_monitor_cycle` calls `Wolverine.run(snapshot)`
and writes the plan to `audit_log` with event `MONITOR_RECOVERY_PLAN`.
"""

from __future__ import annotations

from typing import Optional

from src.agents.base import BaseAgent
from src.agents.batman import engage_kill_switch
from src.config.settings import settings
from src.models.portfolio import EquitySnapshot, PositionSummary
from src.models.recovery import PositionUpdate, RecoveryAction, RecoveryPlan


# ---------------------------------------------------------------------------
# Tunable thresholds (intentionally local — not in Settings yet).
# ---------------------------------------------------------------------------
# Per-position triggers expressed as PnL relative to **equity used**
# (= notional / leverage), NOT relative to raw notional.
#
# Why equity-relative?  With leverage, notional >> equity.  A -5% notional
# loss at 10x means -50% equity loss — catastrophic before the monitor fires.
# Expressing thresholds relative to equity used keeps risk constant regardless
# of leverage choice.
#
# Conversion:  pnl_pct_of_notional = pnl_pct_of_equity / leverage
# So the per-notional threshold we compare against = base_pct / leverage.
_TRAIL_PROFIT_EQUITY_PCT = 0.02      # +2% equity → start trailing the stop
_TIGHTEN_LOSS_EQUITY_PCT = -0.015    # -1.5% equity → tighten the stop
_SCALE_OUT_PROFIT_EQUITY_PCT = 0.05  # +5% equity → recommend taking partial profit
_EMERGENCY_LOSS_EQUITY_PCT = -0.05   # -5% equity → recommend immediate close


def _pnl_pct_of_notional(update: PositionUpdate) -> float:
    """Unrealized PnL as fraction of position notional (entry * size)."""
    notional = update.entry_price * update.size
    if notional <= 0:
        return 0.0
    return update.unrealized_pnl_usd / notional


def _classify_position(update: PositionUpdate) -> tuple[RecoveryAction, str]:
    """
    Pure deterministic classifier — given a PositionUpdate with PnL
    populated, choose a RecoveryAction. No side effects.

    Thresholds are expressed as % of **equity used** (= notional / leverage)
    so that risk exposure stays constant regardless of leverage.  The
    comparison is converted to % of notional by dividing by leverage.
    """
    leverage = max(update.leverage, 1)
    pnl_pct = _pnl_pct_of_notional(update)

    # Scale equity-based thresholds down to notional space for this leverage.
    emergency_thr = _EMERGENCY_LOSS_EQUITY_PCT / leverage
    tighten_thr   = _TIGHTEN_LOSS_EQUITY_PCT   / leverage
    scale_out_thr = _SCALE_OUT_PROFIT_EQUITY_PCT / leverage
    trail_thr     = _TRAIL_PROFIT_EQUITY_PCT     / leverage

    if pnl_pct <= emergency_thr:
        equity_loss_pct = pnl_pct * leverage
        return (
            RecoveryAction.EMERGENCY_CLOSE,
            f"Position down {pnl_pct:.2%} notional ({equity_loss_pct:.2%} equity @{leverage}x) "
            f"— emergency close threshold {_EMERGENCY_LOSS_EQUITY_PCT:.2%} equity",
        )
    if pnl_pct <= tighten_thr:
        return (
            RecoveryAction.TIGHTEN_STOP,
            f"Position down {pnl_pct:.2%} notional — tighten SL to cap further loss",
        )
    if pnl_pct >= scale_out_thr:
        return (
            RecoveryAction.SCALE_OUT,
            f"Position up {pnl_pct:.2%} notional — scale out partial profit",
        )
    if pnl_pct >= trail_thr:
        return (
            RecoveryAction.TRAIL_STOP,
            f"Position up {pnl_pct:.2%} notional — trail SL to lock profit",
        )
    return (RecoveryAction.HOLD, f"Position at {pnl_pct:+.2%} notional — hold")


def _compute_unrealized_pnl(pos: PositionSummary, current_price: Optional[float]) -> float:
    """
    USD unrealized PnL given a position and the current market price.

    long  : (price - entry) * size
    short : (entry - price) * size
    """
    if current_price is None or current_price <= 0:
        # Fallback: trust the snapshot's own unrealized_pnl_usd
        return float(pos.unrealized_pnl_usd or 0.0)
    if pos.side == "long":
        return (current_price - pos.entry_price) * pos.size
    if pos.side == "short":
        return (pos.entry_price - current_price) * pos.size
    return 0.0


def _suggested_new_stop(pos: PositionSummary, current_price: float, action: RecoveryAction) -> Optional[float]:
    """
    Recompute a SL conservatively based on the recommended action and
    current price. Returns None when no SL change is warranted.

    The SL math here is intentionally simple: a 0.5% buffer on the
    correct side of current price. Story 031+ may swap in ATR-based
    sizing once Wolverine has shipped feedback from paper.
    """
    if action not in (RecoveryAction.TIGHTEN_STOP, RecoveryAction.TRAIL_STOP):
        return None
    buffer = 0.005  # 0.5% buffer
    if pos.side == "long":
        return round(current_price * (1.0 - buffer), 6)
    if pos.side == "short":
        return round(current_price * (1.0 + buffer), 6)
    return None


class Wolverine(BaseAgent[RecoveryPlan]):
    """
    Recovery Agent. Read-only monitor over open positions.

    Usage:
        plan = await Wolverine().run(snapshot=equity_snapshot)
        # or with current prices:
        plan = await Wolverine().run(
            snapshot=equity_snapshot,
            current_prices={"BTC": 65_500.0, "ETH": 3_200.0},
        )
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Wolverine",
            role="Recovery Agent — open-position monitor and kill-switch backstop",
        )

    async def _run(  # type: ignore[override]
        self,
        snapshot: EquitySnapshot,
        current_prices: Optional[dict[str, float]] = None,
    ) -> RecoveryPlan:
        """
        Build the cycle's RecoveryPlan from the current portfolio
        snapshot. `current_prices` is an optional `{symbol: price}` dict.
        When omitted, Wolverine falls back to `position.entry_price`
        (yields zero unrealized PnL) — useful for paper-mode tests.
        """
        prices = current_prices or {}

        if not snapshot.positions:
            plan = RecoveryPlan(
                positions=[],
                intraday_drawdown_pct=0.0,
                kill_switch_engaged=False,
                notes="No open positions to monitor.",
            )
            self._log.info(plan.summary())
            return plan

        equity = max(float(snapshot.equity_usd or 0.0), 1.0)  # avoid div-by-zero
        updates: list[PositionUpdate] = []

        for pos in snapshot.positions:
            current_price = prices.get(pos.symbol)
            upnl = _compute_unrealized_pnl(pos, current_price)
            update = PositionUpdate(
                symbol=pos.symbol,
                side=pos.side,
                size=pos.size,
                entry_price=pos.entry_price,
                current_price=current_price,
                unrealized_pnl_usd=upnl,
                leverage=pos.leverage or 1,
            )
            action, reason = _classify_position(update)
            update.action = action
            update.reason = reason
            if current_price is not None:
                update.new_stop_loss = _suggested_new_stop(pos, current_price, action)
            updates.append(update)

        # Aggregate intraday drawdown: only count negative aggregate PnL.
        total_upnl = sum(u.unrealized_pnl_usd for u in updates)
        intraday_dd = max(-total_upnl / equity, 0.0)

        # Backstop kill switch — fires when intraday drawdown breaches
        # the daily limit between Daily PnL writes. Defensive only.
        kill_engaged = False
        notes = "monitor cycle ok"
        if intraday_dd >= settings.max_daily_drawdown_pct:
            reason = (
                f"[Wolverine] Intraday drawdown {intraday_dd:.2%} ≥ "
                f"limit {settings.max_daily_drawdown_pct:.2%} — kill switch engaged"
            )
            try:
                engage_kill_switch(reason)
                kill_engaged = True
                notes = reason
                # Force every position into EMERGENCY_CLOSE so the
                # plan is unambiguous if Iron Man (or human) acts on it.
                for u in updates:
                    u.action = RecoveryAction.EMERGENCY_CLOSE
                    u.reason = "Intraday drawdown breach — emergency close"
            except Exception as exc:  # noqa: BLE001
                # Persistence failure of the kill switch file is rare,
                # but never propagate from a monitor agent.
                self._log.error(f"[Wolverine] engage_kill_switch failed: {exc}")
                notes = f"intraday breach but kill_switch failed: {exc}"

        plan = RecoveryPlan(
            positions=updates,
            intraday_drawdown_pct=round(intraday_dd, 6),
            kill_switch_engaged=kill_engaged,
            notes=notes,
        )
        self._log.info(plan.summary())
        return plan
