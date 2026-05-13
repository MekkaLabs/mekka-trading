"""
src/agents/cyclops.py
=====================
Cyclops — Order Manager (Story 048 / [C2]).

Monitors open paper positions against current market prices and triggers
automatic SL/TP closes when thresholds are breached. Runs every monitor
cycle inside Nick Fury's ``run_monitor_cycle()``.

Design
------
  • SL/TP values are read from the ``raw`` JSON field of the original
    TradeRecord (stored under ``metadata.stop_loss`` and
    ``metadata.take_profit`` by IronMan at execution time).
  • When a trigger fires, Cyclops inserts an offsetting paper trade
    directly into the DB — same pattern as the operator "Fechar" button.
  • For live (non-paper) mode Cyclops is a no-op: the real SL/TP bracket
    orders placed by IronMan on the exchange handle this natively.
  • Cyclops is idempotent: it reads the NET position per symbol (long_qty
    - short_qty) and will not double-close an already-netted position.

Hard rules
----------
  • Cyclops NEVER places real orders. Paper closes only.
  • Defensive: any DB error is logged and swallowed — never raises.
  • Idempotent trigger: if a position is already net-zero it is skipped.
"""

from __future__ import annotations

import uuid
import logging
from collections import defaultdict
from typing import Optional

from src.config.settings import settings
from src.models.execution import ExecutionResult, ExecutionStatus


logger = logging.getLogger("mekka.cyclops")

# ---------------------------------------------------------------------------
# SL/TP extraction helpers
# ---------------------------------------------------------------------------

def _extract_sl_tp(trade_record: object) -> tuple[Optional[float], Optional[float]]:
    """Pull stop_loss and take_profit from a TradeRecord's raw JSON payload."""
    try:
        raw: dict = getattr(trade_record, "raw", {}) or {}
        meta: dict = raw.get("metadata") or {}
        sl = meta.get("stop_loss")
        tp = meta.get("take_profit")
        return (
            float(sl) if sl is not None else None,
            float(tp) if tp is not None else None,
        )
    except (TypeError, ValueError, AttributeError):
        return None, None


# ---------------------------------------------------------------------------
# Cyclops Agent
# ---------------------------------------------------------------------------

class Cyclops:
    """Order Manager — SL/TP monitor for paper positions.

    Usage (called from NickFury.run_monitor_cycle):
        cyclops = Cyclops()
        triggered = await cyclops.run(current_prices={"BTC": 104_000.0, ...})
    """

    async def run(self, current_prices: dict[str, float] | None = None) -> int:
        """Check all open paper positions against SL/TP and close if triggered.

        Returns the number of positions closed this cycle.
        """
        if not settings.paper_trading:
            # Live mode: real bracket orders on the exchange handle SL/TP.
            return 0

        prices = current_prices or {}
        if not prices:
            return 0

        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            trades = await MekkaRepository.list_paper_filled_trades(limit=500)
        except Exception as exc:
            logger.warning("[Cyclops] DB read failed: %s", exc)
            return 0

        if not trades:
            return 0

        # ----------------------------------------------------------------
        # Build net positions per symbol (same logic as positions_provider)
        # ----------------------------------------------------------------
        long_trades: dict[str, list] = defaultdict(list)
        short_trades: dict[str, list] = defaultdict(list)
        for t in trades:
            sym = t.symbol.upper()
            if (t.side or "long").lower() == "long":
                long_trades[sym].append(t)
            else:
                short_trades[sym].append(t)

        triggered = 0

        all_symbols = set(long_trades.keys()) | set(short_trades.keys())
        for symbol in all_symbols:
            longs = long_trades.get(symbol, [])
            shorts = short_trades.get(symbol, [])
            long_qty = sum(t.quantity for t in longs)
            short_qty = sum(t.quantity for t in shorts)
            net = long_qty - short_qty

            if abs(net) < 1e-8:
                continue  # fully closed — skip

            mark = (
                prices.get(symbol)
                or prices.get(symbol.upper())
                or prices.get(f"{symbol}-PERP")
            )
            if not mark or mark <= 0:
                continue  # no price available

            # ----------------------------------------------------------------
            # Determine the net open position and its SL/TP
            # Use the SL/TP from the oldest open trade on the prevailing side.
            # ----------------------------------------------------------------
            if net > 0:
                side = "long"
                open_qty = net
                open_trades = longs
                avg_entry = (
                    sum(t.quantity * t.avg_price for t in longs) / long_qty
                    if long_qty > 0 else 0.0
                )
            else:
                side = "short"
                open_qty = abs(net)
                open_trades = shorts
                avg_entry = (
                    sum(t.quantity * t.avg_price for t in shorts) / short_qty
                    if short_qty > 0 else 0.0
                )

            # Aggregate SL/TP: use the most conservative SL and most
            # conservative TP across all open trades on this side.
            sl_values = []
            tp_values = []
            for t in open_trades:
                sl, tp = _extract_sl_tp(t)
                if sl is not None:
                    sl_values.append(sl)
                if tp is not None:
                    tp_values.append(tp)

            if not sl_values and not tp_values:
                continue  # no SL/TP defined for this position — skip

            # For LONG: SL = highest of the sl values (most conservative = closest to entry)
            #           TP = lowest of the tp values (most conservative = first to trigger)
            # For SHORT: SL = lowest of the sl values; TP = highest
            if side == "long":
                sl_trigger = max(sl_values) if sl_values else None
                tp_trigger = min(tp_values) if tp_values else None
            else:
                sl_trigger = min(sl_values) if sl_values else None
                tp_trigger = max(tp_values) if tp_values else None

            # ----------------------------------------------------------------
            # Check triggers
            # ----------------------------------------------------------------
            trigger_reason: Optional[str] = None

            if side == "long":
                if sl_trigger and mark <= sl_trigger:
                    trigger_reason = (
                        f"SL triggered: mark {mark:,.4f} ≤ sl {sl_trigger:,.4f}"
                    )
                elif tp_trigger and mark >= tp_trigger:
                    trigger_reason = (
                        f"TP triggered: mark {mark:,.4f} ≥ tp {tp_trigger:,.4f}"
                    )
            else:  # short
                if sl_trigger and mark >= sl_trigger:
                    trigger_reason = (
                        f"SL triggered: mark {mark:,.4f} ≥ sl {sl_trigger:,.4f}"
                    )
                elif tp_trigger and mark <= tp_trigger:
                    trigger_reason = (
                        f"TP triggered: mark {mark:,.4f} ≤ tp {tp_trigger:,.4f}"
                    )

            if trigger_reason is None:
                continue

            # ----------------------------------------------------------------
            # Insert offsetting paper close trade
            # ----------------------------------------------------------------
            close_side = "short" if side == "long" else "long"
            close_result = ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.PAPER,
                is_paper=True,
                side=close_side,
                quantity=round(open_qty, 8),
                avg_price=round(mark, 6),
                notional_usd=round(open_qty * mark, 2),
                order_id=f"CYCLOPS-{uuid.uuid4().hex[:10]}",
                metadata={
                    "triggered_by": "cyclops",
                    "trigger_reason": trigger_reason,
                    "avg_entry": avg_entry,
                    "sl_trigger": sl_trigger,
                    "tp_trigger": tp_trigger,
                },
            )

            try:
                from src.persistence.repository import MekkaRepository  # noqa: WPS433
                await MekkaRepository.save_trade(execution=close_result)
                await MekkaRepository.log_event(
                    agent="Cyclops",
                    event="SL_TP_TRIGGERED",
                    severity="WARNING",
                    symbol=symbol,
                    message=(
                        f"[C2] {trigger_reason} — closed {open_qty:.6f} {symbol} "
                        f"@ {mark:,.4f} (entry {avg_entry:,.4f})"
                    ),
                    payload={
                        "symbol": symbol,
                        "side": side,
                        "close_qty": open_qty,
                        "close_price": mark,
                        "avg_entry": avg_entry,
                        "trigger_reason": trigger_reason,
                        "sl_trigger": sl_trigger,
                        "tp_trigger": tp_trigger,
                    },
                )
                triggered += 1
                logger.warning(
                    "[Cyclops] %s — %s (qty=%.6f, close_price=%.4f)",
                    symbol, trigger_reason, open_qty, mark,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("[Cyclops] save_trade failed for %s: %s", symbol, exc)

        return triggered
