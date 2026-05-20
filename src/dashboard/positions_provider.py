"""
src/dashboard/positions_provider.py
===================================
Read-only adapter that pulls open positions for the dashboard
``/api/positions`` endpoint. In live mode it delegates to PortfolioManager,
so the active exchange source stays consistent across the system.

Why a separate module:
  - keeps `server.py` free of `hyperliquid` imports
  - lets us unit-test the mapping logic with a fake `info` object
  - lets the runtime (Iron Man) keep its own SDK lifecycle without
    fighting the dashboard for the same instance

Output contract (stable):
  {
    "items": [
       {
         "symbol": "BTC", "side": "LONG"/"SHORT",
         "size": float, "entry_price": float, "mark_price": float,
         "pnl_usd": float, "leverage": int|None, "liq_price": float|None,
         "is_paper": bool,
       }, ...
    ],
    "count": int,
    "source": "hyperliquid"|"stub",
    "supported": bool,
    "message": str|None,
  }
"""

from __future__ import annotations

import logging
from typing import Any

from src.config.settings import settings


logger = logging.getLogger("mekka.dashboard.positions")


def _stub_response(message: str) -> dict[str, Any]:
    return {
        "items": [],
        "count": 0,
        "source": "stub",
        "supported": False,
        "message": message,
    }


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _to_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def map_user_state_to_positions(user_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a Hyperliquid `info.user_state(addr)` response to our wire shape.

    Public for unit testing. Hyperliquid returns `assetPositions: [{type,
    position: {coin, szi, entryPx, leverage: {value,type}, ...}}, ...]`.
    A negative `szi` means SHORT. We render `is_paper` as False here —
    callers wrap this whole module behind a paper-trading guard.
    """
    out: list[dict[str, Any]] = []
    for asset in user_state.get("assetPositions", []) or []:
        pos = asset.get("position", {}) or {}
        szi = _to_float(pos.get("szi"))
        if szi == 0:
            continue
        side = "LONG" if szi > 0 else "SHORT"
        leverage_obj = pos.get("leverage") or {}
        out.append(
            {
                "symbol": str(pos.get("coin") or "?"),
                "side": side,
                "size": abs(szi),
                "entry_price": _to_float(pos.get("entryPx")),
                "mark_price": _to_float(pos.get("markPx") or pos.get("entryPx")),
                "pnl_usd": _to_float(pos.get("unrealizedPnl")),
                "leverage": _to_int(leverage_obj.get("value")),
                "liq_price": _to_float(pos.get("liquidationPx")) or None,
                "is_paper": False,
            }
        )
    out.sort(key=lambda p: (-abs(p.get("pnl_usd") or 0.0), p["symbol"]))
    return out


async def _fetch_paper_positions(
    mark_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Synthesise open positions from paper FILLED/PAPER trades in the DB.

    [Story 099] Groups by (symbol, side), sums quantities, computes
    weighted avg entry price and estimated unrealised PnL from the
    optional ``mark_prices`` map.  Also adds ``duration_minutes`` (time
    since first opening trade) so the UI can show how long the position
    has been open.
    """
    prices: dict[str, float] = mark_prices or {}

    try:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        trades = await MekkaRepository.list_paper_filled_trades()
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper positions DB read failed: %s", exc)
        return _stub_response(f"Paper DB read error: {type(exc).__name__}")

    if not trades:
        return {
            "items": [],
            "count": 0,
            "source": "paper",
            "supported": True,
            "message": "Paper mode — sem posições abertas ainda.",
        }

    # Net LONG vs SHORT per symbol — close trades (opposite side) cancel out opens.
    from collections import defaultdict  # noqa: WPS433

    long_trades: dict[str, list] = defaultdict(list)
    short_trades: dict[str, list] = defaultdict(list)
    for t in trades:
        sym = t.symbol.upper()
        if (t.side or "long").lower() == "long":
            long_trades[sym].append(t)
        else:
            short_trades[sym].append(t)

    all_symbols = set(long_trades.keys()) | set(short_trades.keys())
    items = []
    for symbol in all_symbols:
        longs = long_trades.get(symbol, [])
        shorts = short_trades.get(symbol, [])
        long_qty = sum(t.quantity for t in longs)
        short_qty = sum(t.quantity for t in shorts)
        net = long_qty - short_qty

        if abs(net) < 1e-8:
            continue  # position fully closed — skip

        if net > 0:
            side = "LONG"
            open_qty = net
            open_trades = longs
            total_qty = long_qty
            avg_px = (
                sum(t.quantity * t.avg_price for t in longs) / long_qty
                if long_qty > 0 else 0.0
            )
        else:
            side = "SHORT"
            open_qty = abs(net)
            open_trades = shorts
            total_qty = short_qty
            avg_px = (
                sum(t.quantity * t.avg_price for t in shorts) / short_qty
                if short_qty > 0 else 0.0
            )

        # Weighted average SL/TP — read from trade.raw['metadata'] (stored at execution time)
        def _get_sl(t: Any) -> float:
            meta = (t.raw or {}).get("metadata") or {} if t.raw else {}
            return float(meta.get("stop_loss") or 0)

        def _get_tp(t: Any) -> float:
            meta = (t.raw or {}).get("metadata") or {} if t.raw else {}
            return float(meta.get("take_profit") or 0)

        avg_sl = (
            sum(t.quantity * _get_sl(t) for t in open_trades) / total_qty
            if total_qty > 0 else 0.0
        )
        avg_tp = (
            sum(t.quantity * _get_tp(t) for t in open_trades) / total_qty
            if total_qty > 0 else 0.0
        )

        # [Story 099] Mark price + estimated unrealised PnL
        mark_px = prices.get(symbol) or prices.get(symbol.upper()) or avg_px
        if mark_px > 0 and avg_px > 0:
            if side == "LONG":
                upnl = round((mark_px - avg_px) * open_qty, 2)
            else:
                upnl = round((avg_px - mark_px) * open_qty, 2)
        else:
            upnl = 0.0

        # [Story 099] Duration — time since first opening trade
        def _get_ts(t: Any) -> float:
            ts = getattr(t, "created_at", None) or getattr(t, "timestamp", None)
            if ts is None:
                return 0.0
            if hasattr(ts, "timestamp"):
                return ts.timestamp()
            try:
                return float(ts)
            except (TypeError, ValueError):
                return 0.0

        _ts_values = [_get_ts(t) for t in open_trades if _get_ts(t) > 0]
        if _ts_values:
            from datetime import datetime, timezone as _tz  # noqa: WPS433
            _oldest_ts = min(_ts_values)
            _now_ts = datetime.now(_tz.utc).timestamp()
            duration_minutes = round((_now_ts - _oldest_ts) / 60, 1)
        else:
            duration_minutes = None

        # [Story 104] R-múltiplo: (mark - entry) / |entry - sl| para LONG
        r_multiple: float | None = None
        if avg_sl > 0 and avg_px > 0:
            _risk_pts = abs(avg_px - avg_sl)
            if _risk_pts > 1e-8:
                if side == "LONG":
                    r_multiple = round((mark_px - avg_px) / _risk_pts, 2)
                else:
                    r_multiple = round((avg_px - mark_px) / _risk_pts, 2)

        items.append(
            {
                "symbol": symbol,
                "side": side,
                "size": round(open_qty, 8),
                "entry_price": round(avg_px, 4),
                "mark_price": round(mark_px, 4),
                "pnl_usd": upnl,
                "leverage": None,
                "liq_price": None,
                "is_paper": True,
                "sl_price": round(avg_sl, 4) if avg_sl > 0 else None,
                "tp_price": round(avg_tp, 4) if avg_tp > 0 else None,
                "duration_minutes": duration_minutes,
                "r_multiple": r_multiple,  # Story 104
            }
        )

    # Sort: largest notional first
    items.sort(key=lambda p: p["size"] * p["entry_price"], reverse=True)

    return {
        "items": items,
        "count": len(items),
        "source": "paper",
        "supported": True,
        "message": (
            "Posições sintéticas — paper mode." if items
            else "Paper mode — todas as posições foram fechadas."
        ),
    }


async def get_paper_equity_summary(
    mark_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute paper trading equity dynamically.

    equity = initial_capital + realized_pnl + unrealized_pnl

    realized_pnl:   P&L from fully-closed positions (matched LONG/SHORT pairs)
    unrealized_pnl: P&L from still-open positions using ``mark_prices`` when
                    provided, otherwise 0 (entry == mark assumption).

    The formula ``(avg_short_price - avg_long_price) * matched_qty`` is
    correct for both originally-LONG and originally-SHORT positions:

        LONG opened at P1, closed by SHORT at P2 → (P2 - P1) * qty ✓
        SHORT opened at P1, closed by LONG  at P2 → (P1 - P2) * qty ✓
          (because avg_short=P1, avg_long=P2 → avg_short - avg_long = P1 - P2)
    """
    from collections import defaultdict  # noqa: WPS433

    from src.config.settings import settings  # noqa: WPS433

    initial = float(settings.paper_equity_usd)
    prices = mark_prices or {}

    try:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        trades = await MekkaRepository.list_paper_filled_trades(limit=500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper equity DB read failed: %s", exc)
        return {
            "initial_capital": initial,
            "realized_pnl_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "equity_usd": initial,
            "error": str(exc),
        }

    long_trades: dict[str, list] = defaultdict(list)
    short_trades: dict[str, list] = defaultdict(list)
    for t in trades:
        sym = t.symbol.upper()
        if (t.side or "long").lower() == "long":
            long_trades[sym].append(t)
        else:
            short_trades[sym].append(t)

    realized_pnl = 0.0
    unrealized_pnl = 0.0

    all_symbols = set(long_trades.keys()) | set(short_trades.keys())
    for symbol in all_symbols:
        longs = long_trades.get(symbol, [])
        shorts = short_trades.get(symbol, [])
        long_qty = sum(t.quantity for t in longs)
        short_qty = sum(t.quantity for t in shorts)

        matched_qty = min(long_qty, short_qty)
        avg_long = (
            sum(t.quantity * t.avg_price for t in longs) / long_qty
            if long_qty > 0 else 0.0
        )
        avg_short = (
            sum(t.quantity * t.avg_price for t in shorts) / short_qty
            if short_qty > 0 else 0.0
        )

        # Realized: from closed (matched) portion
        if matched_qty > 1e-8:
            realized_pnl += (avg_short - avg_long) * matched_qty

        # Unrealized: from still-open portion using mark price if available
        net = long_qty - short_qty
        if abs(net) > 1e-8:
            mark = prices.get(symbol) or prices.get(symbol.upper())
            if mark and mark > 0:
                if net > 0:
                    # net LONG position
                    unrealized_pnl += (mark - avg_long) * net
                else:
                    # net SHORT position
                    unrealized_pnl += (avg_short - mark) * abs(net)

    equity = initial + realized_pnl + unrealized_pnl
    return {
        "initial_capital": round(initial, 2),
        "realized_pnl_usd": round(realized_pnl, 2),
        "unrealized_pnl_usd": round(unrealized_pnl, 2),
        "equity_usd": round(equity, 2),
    }


async def fetch_positions(
    mark_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Best-effort live read. Falls back to the stub shape on every
    sad path so the UI never breaks the dashboard layout.

    [Story 099] ``mark_prices`` is forwarded to ``_fetch_paper_positions``
    so estimated unrealised PnL can be shown in paper mode.
    """
    if settings.paper_trading:
        return await _fetch_paper_positions(mark_prices=mark_prices)

    try:
        from src.agents.portfolio_manager import PortfolioManager  # noqa: WPS433

        snapshot = await PortfolioManager().run()
    except Exception as exc:  # noqa: BLE001
        logger.warning("portfolio snapshot failed: %s", exc)
        return _stub_response(f"Portfolio snapshot error: {type(exc).__name__}")

    items = [
        {
            "symbol": p.symbol,
            "side": p.side.upper(),
            "size": p.size,
            "entry_price": p.entry_price,
            "mark_price": p.entry_price,
            "pnl_usd": p.unrealized_pnl_usd,
            "leverage": p.leverage,
            "liq_price": None,
            "is_paper": snapshot.is_paper,
        }
        for p in snapshot.positions
    ]
    if not items:
        return {
            "items": [],
            "count": 0,
            "source": snapshot.source.value.lower(),
            "supported": True,
            "message": "No open positions.",
        }
    return {
        "items": items,
        "count": len(items),
        "source": snapshot.source.value.lower(),
        "supported": True,
        "message": snapshot.error,
    }
