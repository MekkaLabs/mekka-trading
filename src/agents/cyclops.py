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
            # Story 065 — Scale-out (Partial TP at 50% of move)
            # ----------------------------------------------------------------
            # Detect if a scale-out trade has already been recorded for this
            # symbol. If so, we activate breakeven SL for the remaining half.
            scale_out_done = any(
                (getattr(t, "raw", {}) or {}).get("metadata", {}).get("triggered_by")
                == "cyclops_scale_out"
                for t in trades
                if t.symbol.upper() == symbol
            )

            # Calculate TP1 (midpoint between entry and TP2)
            tp1_trigger: Optional[float] = None
            if tp_trigger and avg_entry and not scale_out_done:
                if side == "long":
                    tp1_trigger = avg_entry + 0.5 * (tp_trigger - avg_entry)
                else:
                    tp1_trigger = avg_entry - 0.5 * (avg_entry - tp_trigger)

            # Story 066 — Trailing Stop: after scale-out, trail instead of
            # fixed breakeven. SL = max(avg_entry, mark*(1-trail)) for LONG.
            # This rises with price but never falls below breakeven.
            if scale_out_done and avg_entry and mark:
                trail_pct = settings.trailing_stop_pct  # default 1.5%
                if side == "long":
                    trail_sl = round(mark * (1.0 - trail_pct), 6)
                    dynamic_sl = max(avg_entry, trail_sl)
                    sl_trigger = (
                        max(sl_trigger, dynamic_sl) if sl_trigger is not None
                        else dynamic_sl
                    )
                else:
                    trail_sl = round(mark * (1.0 + trail_pct), 6)
                    dynamic_sl = min(avg_entry, trail_sl)
                    sl_trigger = (
                        min(sl_trigger, dynamic_sl) if sl_trigger is not None
                        else dynamic_sl
                    )

            # Check TP1 trigger (scale-out: close 50%, keep rest risk-free)
            if tp1_trigger is not None:
                tp1_hit = (
                    (side == "long" and mark >= tp1_trigger)
                    or (side == "short" and mark <= tp1_trigger)
                )
                if tp1_hit:
                    scale_qty = round(open_qty * 0.5, 8)
                    scale_pnl = round(
                        (mark - avg_entry) * scale_qty if side == "long"
                        else (avg_entry - mark) * scale_qty,
                        4,
                    )
                    close_side_scale = "short" if side == "long" else "long"
                    scale_result = ExecutionResult(
                        symbol=symbol,
                        status=ExecutionStatus.PAPER,
                        is_paper=True,
                        side=close_side_scale,
                        quantity=scale_qty,
                        avg_price=round(mark, 6),
                        notional_usd=round(scale_qty * mark, 2),
                        order_id=f"CYCLOPS-SCALEOUT-{uuid.uuid4().hex[:10]}",
                        metadata={
                            "triggered_by": "cyclops_scale_out",
                            "trigger_reason": f"TP1 scale-out: mark {mark:,.4f} hit tp1 {tp1_trigger:,.4f}",
                            "avg_entry": avg_entry,
                            "tp1_trigger": tp1_trigger,
                            "tp2_trigger": tp_trigger,
                            "new_sl_breakeven": avg_entry,
                            "pnl_usd": scale_pnl,
                        },
                    )
                    try:
                        from src.persistence.repository import MekkaRepository  # noqa: WPS433
                        await MekkaRepository.save_trade(
                            execution=scale_result, pnl_usd=scale_pnl
                        )
                        await MekkaRepository.log_event(
                            agent="Cyclops",
                            event="SCALE_OUT_TRIGGERED",
                            severity="INFO",
                            symbol=symbol,
                            message=(
                                f"[C2][ScaleOut] TP1 hit {tp1_trigger:,.4f} — closed 50% "
                                f"({scale_qty:.6f} {symbol}) @ {mark:,.4f} "
                                f"pnl={scale_pnl:+.4f} | stop→breakeven {avg_entry:,.4f}"
                            ),
                            payload={
                                "symbol": symbol, "side": side,
                                "scale_qty": scale_qty, "close_price": mark,
                                "avg_entry": avg_entry, "tp1_trigger": tp1_trigger,
                                "tp2_trigger": tp_trigger, "pnl_usd": scale_pnl,
                            },
                        )
                        triggered += 1
                        logger.info(
                            "[Cyclops] SCALE-OUT %s — TP1=%.4f mark=%.4f qty=%.6f pnl=%+.4f",
                            symbol, tp1_trigger, mark, scale_qty, scale_pnl,
                        )
                        # Telegram — scale-out alert
                        try:
                            from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                            await TelegramAlerter().scale_out_alert(
                                symbol=symbol, side=side,
                                close_price=mark, avg_entry=avg_entry,
                                closed_qty=scale_qty,
                                remaining_qty=round(open_qty - scale_qty, 8),
                                tp1_trigger=tp1_trigger,
                                tp2_trigger=tp_trigger or mark * 1.02,
                                new_sl=avg_entry,
                                pnl_usd=scale_pnl,
                            )
                        except Exception as _tg_exc:  # noqa: BLE001
                            logger.debug("[Cyclops] scale-out telegram skipped: %s", _tg_exc)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("[Cyclops] scale-out save failed %s: %s", symbol, exc)
                    # Skip full-close this cycle — next cycle handles remaining half
                    continue

            # ----------------------------------------------------------------
            # Check triggers (full close — SL or full TP)
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
            # Compute realized PnL for this close
            # ----------------------------------------------------------------
            if side == "long":
                pnl_usd = round((mark - avg_entry) * open_qty, 4)
            else:
                pnl_usd = round((avg_entry - mark) * open_qty, 4)

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
                    "pnl_usd": pnl_usd,
                },
            )

            try:
                from src.persistence.repository import MekkaRepository  # noqa: WPS433
                await MekkaRepository.save_trade(execution=close_result, pnl_usd=pnl_usd)
                await MekkaRepository.log_event(
                    agent="Cyclops",
                    event="SL_TP_TRIGGERED",
                    severity="WARNING",
                    symbol=symbol,
                    message=(
                        f"[C2] {trigger_reason} — closed {open_qty:.6f} {symbol} "
                        f"@ {mark:,.4f} (entry {avg_entry:,.4f}) pnl={pnl_usd:+.4f}"
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
                        "pnl_usd": pnl_usd,
                    },
                )
                triggered += 1
                logger.warning(
                    "[Cyclops] %s — %s (qty=%.6f, close_price=%.4f)",
                    symbol, trigger_reason, open_qty, mark,
                )
                # Story 063 — Episodic Memory: resolve outcome for this position.
                # Compute holding_hours from opening trade timestamp.
                try:
                    from src.persistence.agent_memory import AgentMemoryStore as _AMS  # noqa: WPS433
                    _holding_h: float | None = None
                    try:
                        # Best effort: look for the opening trade to compute duration
                        _open_trades = await MekkaRepository.list_open_paper_trades()
                        _op = next(
                            (t for t in _open_trades if t.symbol == symbol),
                            None,
                        )
                        if _op and hasattr(_op, "timestamp") and _op.timestamp:
                            from datetime import datetime, timezone  # noqa: WPS433
                            _now = datetime.now(timezone.utc)
                            _delta = _now - _op.timestamp.replace(tzinfo=timezone.utc) if _op.timestamp.tzinfo is None else _now - _op.timestamp
                            _holding_h = round(_delta.total_seconds() / 3600, 2)
                    except Exception:  # noqa: BLE001
                        pass
                    await _AMS.resolve_outcome(
                        symbol=symbol,
                        pnl_usd=pnl_usd,
                        holding_hours=_holding_h,
                    )
                except Exception as _mem_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] memory resolve skipped: %s", _mem_exc)

                # Telegram — fire-and-forget, never raises
                try:
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    await TelegramAlerter().position_closed(
                        symbol=symbol,
                        side=side,
                        close_price=mark,
                        avg_entry=avg_entry,
                        qty=open_qty,
                        trigger_reason=trigger_reason,
                        sl_trigger=sl_trigger,
                        tp_trigger=tp_trigger,
                    )
                except Exception as _tg_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] telegram alert skipped: %s", _tg_exc)
            except Exception as exc:  # noqa: BLE001
                logger.error("[Cyclops] save_trade failed for %s: %s", symbol, exc)

        return triggered
