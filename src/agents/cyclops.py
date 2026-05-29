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
            # Story 083 — Auto-TP Ladder (3-level graduated exits)
            # ----------------------------------------------------------------
            # When tp_ladder_enabled, replaces the single Story-065 scale-out
            # with 3 graduated exits at 1/3, 2/3, and full TP of the move.
            # Each level is detected by a distinct triggered_by marker.
            if settings.tp_ladder_enabled and tp_trigger and avg_entry:
                _sym_trades = [t for t in trades if t.symbol.upper() == symbol]
                _triggered_bys = [
                    (getattr(t, "raw", {}) or {}).get("metadata", {}).get("triggered_by", "")
                    for t in _sym_trades
                ]
                _ladder_1_done = "cyclops_tp_ladder_1" in _triggered_bys
                _ladder_2_done = "cyclops_tp_ladder_2" in _triggered_bys

                # Calculate ladder trigger prices
                _r = tp_trigger - avg_entry if side == "long" else avg_entry - tp_trigger
                if side == "long":
                    _ladder_tp1 = avg_entry + (_r / 3.0) if not _ladder_1_done else None
                    _ladder_tp2 = avg_entry + (2.0 * _r / 3.0) if _ladder_1_done and not _ladder_2_done else None
                else:
                    _ladder_tp1 = avg_entry - (_r / 3.0) if not _ladder_1_done else None
                    _ladder_tp2 = avg_entry - (2.0 * _r / 3.0) if _ladder_1_done and not _ladder_2_done else None

                # Apply breakeven SL after TP1, trailing after TP2
                if _ladder_1_done and avg_entry:
                    if side == "long":
                        sl_trigger = max(sl_trigger, avg_entry) if sl_trigger else avg_entry
                    else:
                        sl_trigger = min(sl_trigger, avg_entry) if sl_trigger else avg_entry
                if _ladder_2_done and mark:
                    trail_pct = settings.trailing_stop_pct
                    if side == "long":
                        _trail_sl = round(mark * (1.0 - trail_pct), 6)
                        _trail_sl = max(avg_entry, _trail_sl)
                        sl_trigger = max(sl_trigger, _trail_sl) if sl_trigger else _trail_sl
                    else:
                        _trail_sl = round(mark * (1.0 + trail_pct), 6)
                        _trail_sl = min(avg_entry, _trail_sl)
                        sl_trigger = min(sl_trigger, _trail_sl) if sl_trigger else _trail_sl

                # TP Ladder Level 1 check
                if _ladder_tp1 is not None:
                    _ltp1_hit = (
                        (side == "long" and mark >= _ladder_tp1)
                        or (side == "short" and mark <= _ladder_tp1)
                    )
                    if _ltp1_hit:
                        _l1_qty = round(open_qty * settings.tp_ladder_tp1_pct, 8)
                        _l1_pnl = round(
                            (mark - avg_entry) * _l1_qty if side == "long"
                            else (avg_entry - mark) * _l1_qty, 4,
                        )
                        _l1_close_side = "short" if side == "long" else "long"
                        _l1_result = ExecutionResult(
                            symbol=symbol, status=ExecutionStatus.PAPER, is_paper=True,
                            side=_l1_close_side, quantity=_l1_qty,
                            avg_price=round(mark, 6),
                            notional_usd=round(_l1_qty * mark, 2),
                            order_id=f"CYCLOPS-TPL1-{uuid.uuid4().hex[:8]}",
                            metadata={
                                "triggered_by": "cyclops_tp_ladder_1",
                                "trigger_reason": f"TP Ladder L1: mark {mark:,.4f} hit {_ladder_tp1:,.4f} (1/3 of range)",
                                "avg_entry": avg_entry, "tp_ladder_trigger": _ladder_tp1,
                                "new_sl_breakeven": avg_entry, "pnl_usd": _l1_pnl,
                            },
                        )
                        try:
                            from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
                            await _Repo.save_trade(execution=_l1_result, pnl_usd=_l1_pnl)
                            await _Repo.log_event(
                                agent="Cyclops", event="TP_LADDER_L1", severity="INFO", symbol=symbol,
                                message=f"[TP-Ladder-L1] {symbol} {side.upper()} closed {settings.tp_ladder_tp1_pct*100:.0f}% @ {mark:,.4f} pnl={_l1_pnl:+.4f}",
                                payload={"symbol": symbol, "side": side, "qty": _l1_qty, "price": mark, "pnl_usd": _l1_pnl},
                            )
                            triggered += 1
                            logger.info("[Cyclops] TP-Ladder-L1 %s qty=%.6f pnl=%+.4f", symbol, _l1_qty, _l1_pnl)
                        except Exception as _exc:  # noqa: BLE001
                            logger.error("[Cyclops] TP-Ladder-L1 save failed %s: %s", symbol, _exc)
                        continue

                # TP Ladder Level 2 check
                if _ladder_tp2 is not None:
                    _ltp2_hit = (
                        (side == "long" and mark >= _ladder_tp2)
                        or (side == "short" and mark <= _ladder_tp2)
                    )
                    if _ltp2_hit:
                        _l2_qty = round(open_qty * settings.tp_ladder_tp2_pct, 8)
                        _l2_pnl = round(
                            (mark - avg_entry) * _l2_qty if side == "long"
                            else (avg_entry - mark) * _l2_qty, 4,
                        )
                        _l2_close_side = "short" if side == "long" else "long"
                        _l2_result = ExecutionResult(
                            symbol=symbol, status=ExecutionStatus.PAPER, is_paper=True,
                            side=_l2_close_side, quantity=_l2_qty,
                            avg_price=round(mark, 6),
                            notional_usd=round(_l2_qty * mark, 2),
                            order_id=f"CYCLOPS-TPL2-{uuid.uuid4().hex[:8]}",
                            metadata={
                                "triggered_by": "cyclops_tp_ladder_2",
                                "trigger_reason": f"TP Ladder L2: mark {mark:,.4f} hit {_ladder_tp2:,.4f} (2/3 of range)",
                                "avg_entry": avg_entry, "tp_ladder_trigger": _ladder_tp2,
                                "new_sl_trailing": True, "pnl_usd": _l2_pnl,
                            },
                        )
                        try:
                            from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
                            await _Repo.save_trade(execution=_l2_result, pnl_usd=_l2_pnl)
                            await _Repo.log_event(
                                agent="Cyclops", event="TP_LADDER_L2", severity="INFO", symbol=symbol,
                                message=f"[TP-Ladder-L2] {symbol} {side.upper()} closed {settings.tp_ladder_tp2_pct*100:.0f}% @ {mark:,.4f} pnl={_l2_pnl:+.4f} | SL→trailing",
                                payload={"symbol": symbol, "side": side, "qty": _l2_qty, "price": mark, "pnl_usd": _l2_pnl},
                            )
                            triggered += 1
                            logger.info("[Cyclops] TP-Ladder-L2 %s qty=%.6f pnl=%+.4f", symbol, _l2_qty, _l2_pnl)
                        except Exception as _exc:  # noqa: BLE001
                            logger.error("[Cyclops] TP-Ladder-L2 save failed %s: %s", symbol, _exc)
                        continue

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

            # ----------------------------------------------------------------
            # Story 087 — +2R profit alert (Telegram warning to close manually)
            # ----------------------------------------------------------------
            # Fires once when position unrealised profit crosses 2× the initial
            # risk (distance from entry to SL). Detected via a sentinel marker
            # in trade history so we don't spam on every cycle.
            if tp_trigger and sl_trigger and avg_entry and mark:
                try:
                    _risk = abs(avg_entry - sl_trigger)
                    _two_r_price = (
                        avg_entry + 2.0 * _risk if side == "long"
                        else avg_entry - 2.0 * _risk
                    )
                    _two_r_done = any(
                        (getattr(t, "raw", {}) or {}).get("metadata", {}).get("triggered_by")
                        == "cyclops_2r_alert"
                        for t in trades
                        if t.symbol.upper() == symbol
                    )
                    _two_r_hit = (
                        not _two_r_done
                        and (
                            (side == "long" and mark >= _two_r_price)
                            or (side == "short" and mark <= _two_r_price)
                        )
                    )
                    if _two_r_hit:
                        from src.persistence.repository import MekkaRepository as _Repo3  # noqa: WPS433
                        await _Repo3.log_event(
                            agent="Cyclops", event="TWO_R_PROFIT_ALERT", severity="INFO",
                            symbol=symbol,
                            message=f"[+2R] {symbol} {side.upper()} position hit +2R @ {mark:,.4f}",
                            payload={"symbol": symbol, "side": side, "mark": mark,
                                     "avg_entry": avg_entry, "two_r_price": _two_r_price,
                                     "sl_trigger": sl_trigger},
                        )
                        # Sentinel trade to avoid re-alerting
                        from src.models.execution import ExecutionResult as _ER, ExecutionStatus as _ES  # noqa: WPS433
                        _sentinel = _ER(
                            symbol=symbol, status=_ES.PAPER, is_paper=True,
                            side=side, quantity=0.0, avg_price=mark,
                            notional_usd=0.0,
                            order_id=f"CYCLOPS-2RALERT-{uuid.uuid4().hex[:8]}",
                            metadata={
                                "triggered_by": "cyclops_2r_alert",
                                "trigger_reason": f"+2R alert: mark {mark:,.4f} ≥ 2R target {_two_r_price:,.4f}",
                            },
                        )
                        await _Repo3.save_trade(execution=_sentinel, pnl_usd=None)
                        # Telegram alert
                        try:
                            from src.services.telegram_alerter import TelegramAlerter as _TGA  # noqa: WPS433
                            _unrealised = (
                                (mark - avg_entry) * open_qty if side == "long"
                                else (avg_entry - mark) * open_qty
                            )
                            await _TGA().send(
                                f"🎯 +2R Alert — {symbol} {side.upper()}\n"
                                f"Mark: {mark:,.4f} | Entry: {avg_entry:,.4f}\n"
                                f"Unrealised: +${_unrealised:.2f}\n"
                                f"Considere fechar parcial ou mover SL para proteger lucro.",
                                level="INFO",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        logger.info("[Cyclops] +2R alert fired for %s @ %s", symbol, mark)
                except Exception as _2r_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] +2R alert skipped: %s", _2r_exc)

            # ----------------------------------------------------------------
            # Story 098 — -0.5R danger zone alert (early SL warning)
            # ----------------------------------------------------------------
            if sl_trigger and avg_entry and mark:
                try:
                    _risk_dist = abs(avg_entry - sl_trigger)
                    _half_r_warn_price = (
                        avg_entry - 0.5 * _risk_dist if side == "long"
                        else avg_entry + 0.5 * _risk_dist
                    )
                    _warn_done = any(
                        (getattr(t, "raw", {}) or {}).get("metadata", {}).get("triggered_by")
                        == "cyclops_half_r_warn"
                        for t in trades
                        if t.symbol.upper() == symbol
                    )
                    _warn_hit = (
                        not _warn_done
                        and (
                            (side == "long" and mark <= _half_r_warn_price)
                            or (side == "short" and mark >= _half_r_warn_price)
                        )
                    )
                    if _warn_hit:
                        from src.persistence.repository import MekkaRepository as _Repo4  # noqa: WPS433
                        _warn_sentinel = ExecutionResult(
                            symbol=symbol, status=ExecutionStatus.PAPER, is_paper=True,
                            side=side, quantity=0.0, avg_price=mark,
                            notional_usd=0.0,
                            order_id=f"CYCLOPS-HALFR-{uuid.uuid4().hex[:8]}",
                            metadata={
                                "triggered_by": "cyclops_half_r_warn",
                                "trigger_reason": f"-0.5R warning: mark {mark:,.4f}",
                            },
                        )
                        await _Repo4.save_trade(execution=_warn_sentinel, pnl_usd=None)
                        try:
                            from src.services.telegram_alerter import TelegramAlerter as _TGA2  # noqa: WPS433
                            _loss_now = (
                                (avg_entry - mark) * open_qty if side == "long"
                                else (mark - avg_entry) * open_qty
                            )
                            await _TGA2().send(
                                f"⚠️ -0.5R Warning — {symbol} {side.upper()}\n"
                                f"Mark: {mark:,.4f} | Entry: {avg_entry:,.4f}\n"
                                f"SL em: {sl_trigger:,.4f} | Loss atual: -${_loss_now:.2f}\n"
                                f"Posição se aproximando do stop loss.",
                                level="WARNING",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        logger.warning("[Cyclops] -0.5R danger zone alert for %s @ %s", symbol, mark)
                except Exception as _hr_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] -0.5R warn skipped: %s", _hr_exc)

            # ----------------------------------------------------------------
            # [Story 105] Partial SL — close 50% at -0.75R
            #
            # When price crosses 75% of the distance from entry to SL, close
            # half the position to reduce maximum loss. Uses sentinel to fire
            # only once per position. Gated by settings.partial_sl_enabled.
            # ----------------------------------------------------------------
            if settings.partial_sl_enabled and sl_trigger and avg_entry and mark:
                try:
                    _partial_sl_price = (
                        avg_entry - 0.75 * abs(avg_entry - sl_trigger) if side == "long"
                        else avg_entry + 0.75 * abs(avg_entry - sl_trigger)
                    )
                    _psl_done = any(
                        (getattr(t, "raw", {}) or {}).get("metadata", {}).get("triggered_by")
                        == "cyclops_partial_sl"
                        for t in trades
                        if t.symbol.upper() == symbol
                    )
                    _psl_hit = (
                        not _psl_done
                        and open_qty > 1e-8
                        and (
                            (side == "long" and mark <= _partial_sl_price)
                            or (side == "short" and mark >= _partial_sl_price)
                        )
                    )
                    if _psl_hit:
                        _psl_qty = round(open_qty * 0.5, 8)
                        _psl_pnl = round(
                            (mark - avg_entry) * _psl_qty if side == "long"
                            else (avg_entry - mark) * _psl_qty, 4
                        )
                        _psl_close_side = "short" if side == "long" else "long"
                        _psl_exec = ExecutionResult(
                            symbol=symbol,
                            status=ExecutionStatus.PAPER,
                            is_paper=True,
                            side=_psl_close_side,
                            quantity=_psl_qty,
                            avg_price=round(mark, 6),
                            notional_usd=round(_psl_qty * mark, 2),
                            order_id=f"CYCLOPS-PSL-{uuid.uuid4().hex[:8]}",
                            metadata={
                                "triggered_by": "cyclops_partial_sl",
                                "trigger_reason": f"-0.75R partial SL: mark {mark:,.4f}",
                                "avg_entry": avg_entry,
                                "sl_trigger": sl_trigger,
                                "partial_sl_price": _partial_sl_price,
                                "pnl_usd": _psl_pnl,
                            },
                        )
                        from src.persistence.repository import MekkaRepository as _PSLRepo  # noqa: WPS433
                        await _PSLRepo.save_trade(execution=_psl_exec, pnl_usd=_psl_pnl)
                        try:
                            from src.services.telegram_alerter import TelegramAlerter as _TGPSL  # noqa: WPS433
                            await _TGPSL().send(
                                f"✂️ *Partial SL* — {symbol} {side.upper()}\n"
                                f"Fechado 50% ({_psl_qty:.6f}) @ {mark:,.4f}\n"
                                f"PnL parcial: ${_psl_pnl:+.2f}\n"
                                f"SL em: {sl_trigger:,.4f} (−0.75R atingido)",
                                level="WARNING",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        logger.warning(
                            "[Cyclops] Partial SL fired for %s — closed 50%% @ %s (pnl=%s)",
                            symbol, mark, _psl_pnl,
                        )
                except Exception as _psl_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] Partial SL gate skipped: %s", _psl_exc)

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
            # Check triggers (full close — SL, full TP, ou TIME-STOP em scalp)
            # ----------------------------------------------------------------
            trigger_reason: Optional[str] = None

            # Scalp Mode (2026-05-28) — time-stop: fecha posição que
            # ultrapassou max_position_age_minutes. Vence SL/TP normais
            # porque em scalp o objetivo é não segurar posição além do
            # horizonte planejado. Sem-op em modos swing (max_age = None).
            try:
                from src.config.runtime_mode import get_params as _get_mode_params  # noqa: WPS433
                _mp = _get_mode_params()
                _max_age_min = _mp.get("max_position_age_minutes")
            except Exception:
                _max_age_min = None

            if _max_age_min and _max_age_min > 0:
                # Idade = agora - timestamp do trade ABERTO mais antigo da side
                from datetime import datetime as _dt, timezone as _tz, timedelta as _td  # noqa: WPS433
                _now = _dt.now(_tz.utc)
                _cutoff = _now - _td(minutes=_max_age_min)
                _oldest = None
                for _t in open_trades:
                    _ts = getattr(_t, "timestamp", None)
                    if _ts is None:
                        continue
                    if _ts.tzinfo is None:
                        _ts = _ts.replace(tzinfo=_tz.utc)
                    if _oldest is None or _ts < _oldest:
                        _oldest = _ts
                if _oldest is not None and _oldest < _cutoff:
                    _age_min = (_now - _oldest).total_seconds() / 60.0
                    # P2 (2026-05-28 audit): detecta clock skew anômalo.
                    # Se age > 24h, provavelmente é timestamp em outro fuso
                    # ou relógio do servidor desincronizado — log WARNING
                    # mas mantém o close (defensivo: posição velha precisa
                    # fechar mesmo se medição estiver errada).
                    if _age_min > 1440:  # 24h
                        logger.warning(
                            f"[Cyclops] CLOCK_SKEW suspeito: position age "
                            f"{_age_min:.1f}min > 1440min (24h). "
                            f"Verifique TZ do servidor e timestamp do trade. "
                            f"Closing anyway as defensive measure."
                        )
                    trigger_reason = (
                        f"SCALP time-stop: position age {_age_min:.1f}min "
                        f"> max {_max_age_min}min"
                    )

            if trigger_reason is None and side == "long":
                if sl_trigger and mark <= sl_trigger:
                    trigger_reason = (
                        f"SL triggered: mark {mark:,.4f} ≤ sl {sl_trigger:,.4f}"
                    )
                elif tp_trigger and mark >= tp_trigger:
                    trigger_reason = (
                        f"TP triggered: mark {mark:,.4f} ≥ tp {tp_trigger:,.4f}"
                    )
            elif trigger_reason is None:  # short
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
                # Write-back loop: append linha em 60-Daily/YYYY-MM-DD-trades.md
                # Opt-in via CYCLOPS_VAULT_WRITER_ENABLED. Fail-silent.
                try:
                    from src.services import trading_vault_writer as _tvw
                    _tvw.record_cyclops_close({
                        "symbol": symbol,
                        "side": side,
                        "pnl_usd": pnl_usd,
                        "holding_hours": None,  # close_position não tem hold_h direto
                        "reason": trigger_reason,
                    })
                except Exception as exc_vault:  # noqa: BLE001
                    logger.debug(f"[Cyclops] vault writer no-op: {exc_vault}")
                # Stories 063/183/186 — resolve all memory stores via central helper.
                # AgentMemory (063), RoleWorkingMemory (183), SignalOutcomeMemory (186)
                # are all written from the same place so closes via SL/TP, manual or
                # emergency_flatten stay consistent. See project-memory-orphan-writers.
                try:
                    _holding_h: float | None = None
                    try:
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
                    from src.services.trade_outcome_resolver import (  # noqa: WPS433
                        resolve_trade_memories as _rtm,
                    )
                    await _rtm(
                        symbol=symbol,
                        pnl_usd=pnl_usd,
                        holding_hours=_holding_h,
                        trade_id=str(_op.order_id) if _op and getattr(_op, "order_id", None) else None,
                    )
                except Exception as _mem_exc:  # noqa: BLE001
                    logger.debug("[Cyclops] memory resolve skipped: %s", _mem_exc)

                # Story 111 — Auto-reset consecutive losses gate (3o).
                # When Cyclops closes a position with POSITIVE PnL (TP win),
                # the gate 3o's list_recent_closed_trades() will naturally see
                # this winning trade and break any all-losses streak. We also
                # write an explicit audit event GATE_3O_RESET for observability.
                if pnl_usd > 0:
                    try:
                        await MekkaRepository.log_event(
                            agent="Cyclops",
                            event="GATE_3O_RESET",
                            severity="INFO",
                            symbol=symbol,
                            message=(
                                f"[111] TP win on {symbol} pnl={pnl_usd:+.4f} — "
                                f"consecutive-losses streak reset."
                            ),
                            payload={
                                "symbol": symbol,
                                "pnl_usd": pnl_usd,
                                "trigger_reason": trigger_reason,
                            },
                        )
                    except Exception as _r111_exc:  # noqa: BLE001
                        logger.debug("[Cyclops] gate-3o reset audit skipped: %s", _r111_exc)

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
