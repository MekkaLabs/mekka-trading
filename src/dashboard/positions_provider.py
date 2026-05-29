"""
src/dashboard/positions_provider.py
===================================
Read-only adapter that pulls open positions for the dashboard
``/api/positions`` endpoint. In live mode (paper_trading=False) it
delegates to PortfolioManager so the active-exchange source stays
consistent across the system — PortfolioManager already owns the
right CCXT client lifecycle (including sandbox routing for Bybit
testnet) and we do not want a parallel client racing it. In paper
mode it serves trades from the local DB.

Why a separate module:
  - keeps `server.py` free of exchange SDK imports
  - lets us unit-test the mapping logic with fake response objects
  - lets the runtime (Iron Man) keep its own SDK lifecycle without
    fighting the dashboard for the same instance

Exchange dispatch (Phase 2):
  - settings.paper_trading=True       → paper trades from the local DB
  - settings.active_exchange="bybit"   → CCXT fetch_positions (with sandbox routing)
  - settings.active_exchange="binance" → CCXT fetch_positions (with sandbox routing)
  - settings.active_exchange="hyperliquid" → native HL SDK info.user_state

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
    "source": "hyperliquid"|"bybit"|"binance"|"stub",
    "supported": bool,
    "message": str|None,
  }
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from src.config.settings import settings
from src.services.market_registry import to_mekka


logger = logging.getLogger("mekka.dashboard.positions")

_LIVE_POSITIONS_CACHE: tuple[float, dict[str, Any]] | None = None
_LIVE_POSITIONS_LOCK = asyncio.Lock()


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


def map_ccxt_positions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map a list of CCXT unified ``fetch_positions()`` rows to our shape.

    CCXT unified position fields used here:
      - ``symbol``         e.g. ``BTC/USDT:USDT``  → split back to ``BTC``
      - ``contracts``      position size in base currency
      - ``side``           ``"long"`` / ``"short"``
      - ``entryPrice``     average entry
      - ``markPrice``      current mark
      - ``unrealizedPnl``  USDT-quoted PnL (already includes side)
      - ``leverage``       isolated/cross leverage
      - ``liquidationPrice`` may be None for cross-margin

    Public for unit testing — call sites pass a fake list of dicts.
    """
    out: list[dict[str, Any]] = []
    for row in raw or []:
        size = _to_float(row.get("contracts"))
        if size == 0:
            continue
        # CCXT symbol → bare Mekka symbol. Delegating to MarketRegistry.to_mekka
        # gives us the union of every reasonable input format (perp, spot,
        # dash, glued) for free, and keeps the contract identical to the
        # rest of the system.
        coin = to_mekka(row.get("symbol") or "")
        side_raw = (row.get("side") or "").lower()
        side = "LONG" if side_raw == "long" else "SHORT"
        out.append({
            "symbol": coin,
            "side": side,
            "size": abs(size),
            "entry_price": _to_float(row.get("entryPrice")),
            "mark_price": _to_float(row.get("markPrice")),
            "pnl_usd": _to_float(row.get("unrealizedPnl")),
            "leverage": _to_int(row.get("leverage")),
            "liq_price": _to_float(row.get("liquidationPrice")) or None,
            "is_paper": False,
        })
    return out


async def _fetch_ccxt_positions(exchange_id: str) -> dict[str, Any]:
    """Fetch live positions from a CCXT-backed exchange (Bybit / Binance).

    The IronMan agent already builds its own CCXT client with
    sandbox-routing applied; we deliberately build a *separate* lightweight
    instance here because:

      - the dashboard runs in a different lifecycle (started/stopped via
        aiohttp on_shutdown) and we do not want to share an SDK handle
        across two task graphs.
      - read-only access keeps blast radius small if the dashboard process
        is compromised — even if someone hijacks the read client they
        cannot place orders.

    Returns the same wire shape as the Hyperliquid path so the frontend
    needs no change.
    """
    if exchange_id == "bybit" and not settings.bybit_api_key:
        return _stub_response("BYBIT_API_KEY not set.")
    if exchange_id == "binance" and not settings.binance_api_key:
        return _stub_response("BINANCE_API_KEY not set.")

    try:
        import ccxt.async_support as ccxt  # noqa: WPS433
    except ImportError:
        return _stub_response("ccxt not installed (pip install ccxt).")

    cfg: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": 20_000,
        "options": {
            "defaultType": "swap",
            # 60s recvWindow + time-difference adjustment so a drifted local
            # clock never triggers InvalidNonce -1021 on the read path.
            "recvWindow": 60_000,
            "adjustForTimeDifference": True,
        },
    }
    if exchange_id == "bybit":
        cfg["apiKey"] = settings.bybit_api_key
        cfg["secret"] = settings.bybit_api_secret
    elif exchange_id == "binance":
        cfg["apiKey"] = settings.binance_api_key
        cfg["secret"] = settings.binance_api_secret
        cfg["options"].update(
            {
                "defaultSubType": "linear",
                "fetchMarkets": {"types": ["linear"]},
                "disableFuturesSandboxWarning": True,
            }
        )

    exchange = getattr(ccxt, exchange_id)(cfg)
    try:
        # Apply testnet routing BEFORE any network call so the credentials
        # match the endpoint. Without this, testnet keys 401 against
        # mainnet (or — worse — live keys hit production).
        try:
            if exchange_id == "bybit" and settings.bybit_testnet:
                exchange.set_sandbox_mode(True)
            elif exchange_id == "binance" and settings.binance_testnet:
                exchange.set_sandbox_mode(True)
        except Exception as sbx_exc:
            logger.error("[positions/%s] set_sandbox_mode failed: %s", exchange_id, sbx_exc)

        try:
            raw = await asyncio.wait_for(exchange.fetch_positions(), timeout=5.0)
        except asyncio.TimeoutError:
            return _stub_response(f"{exchange_id} timed out.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s fetch_positions failed: %s", exchange_id, exc)
            return _stub_response(f"{exchange_id} error: {type(exc).__name__}")

        items = map_ccxt_positions(raw or [])
        if not items:
            return {
                "items": [],
                "count": 0,
                "source": exchange_id,
                "supported": True,
                "message": "No open positions.",
            }
        return {
            "items": items,
            "count": len(items),
            "source": exchange_id,
            "supported": True,
            "message": None,
        }
    finally:
        # Always close the ephemeral client to release the aiohttp session.
        # If close() itself raises we swallow it — we already have the data
        # we wanted to return.
        try:
            await exchange.close()
        except Exception:  # noqa: BLE001
            pass


async def _live_sltp_map() -> dict[tuple[str, str], dict[str, float | None]]:
    """Build a ``{(SYMBOL, SIDE): {"sl": float|None, "tp": float|None}}`` map
    from the SL/TP stored in recent trades' execution metadata.

    IronMan persists the bracket levels in ``trade.raw["metadata"]`` at order
    time (``stop_loss`` / ``take_profit``). The PortfolioManager snapshot does
    not carry them, so the dashboard recovers them here. The most recent trade
    per (symbol, side) wins. Fail-silent — returns ``{}`` on any error so the
    panel still renders (just without SL/TP rows).
    """
    out: dict[tuple[str, str], dict[str, float | None]] = {}
    try:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        trades = await MekkaRepository.list_recent_trades(limit=40)
    except Exception as exc:  # noqa: BLE001
        logger.warning("live SL/TP lookup failed: %s", exc)
        return out

    for t in trades or []:
        try:
            sym = (getattr(t, "symbol", "") or "").upper()
            side = (getattr(t, "side", "") or "").upper()
            if not sym or side not in ("LONG", "SHORT"):
                continue
            key = (sym, side)
            if key in out:
                continue  # list_recent_trades is newest-first → keep the first
            meta = ((t.raw or {}).get("metadata") or {}) if getattr(t, "raw", None) else {}
            sl = _to_float(meta.get("stop_loss")) or None
            tp = _to_float(meta.get("take_profit")) or None
            if sl is None and tp is None:
                continue
            out[key] = {"sl": sl, "tp": tp}
        except Exception:  # noqa: BLE001
            continue
    return out


async def fetch_open_orders() -> dict[str, Any]:
    """Read the live reduce-only SL/TP orders sitting on the venue.

    Lets the operator SEE that each open position is actually protected by a
    stop on the exchange (not just in the bot's memory) — the key reassurance
    for testnet validation before mainnet. Read-only, fail-silent: returns the
    stub shape on any sad path so the panel never breaks.
    """
    if settings.paper_trading:
        return {"items": [], "count": 0, "source": "paper", "supported": False,
                "message": "Paper mode — ordens são simuladas (sem ordens reais na corretora)."}
    exchange_id = settings.active_exchange
    if exchange_id == "hyperliquid":
        return _stub_response("Open-orders view: Hyperliquid usa SDK nativo (não-CCXT).")
    if exchange_id == "binance" and not settings.binance_api_key:
        return _stub_response("BINANCE_API_KEY not set.")
    if exchange_id == "bybit" and not settings.bybit_api_key:
        return _stub_response("BYBIT_API_KEY not set.")
    try:
        import ccxt.async_support as ccxt  # noqa: WPS433
    except ImportError:
        return _stub_response("ccxt not installed.")

    cfg: dict[str, Any] = {
        "enableRateLimit": True, "timeout": 20_000,
        "options": {"defaultType": "swap", "recvWindow": 60_000, "adjustForTimeDifference": True},
    }
    if exchange_id == "bybit":
        cfg["apiKey"] = settings.bybit_api_key
        cfg["secret"] = settings.bybit_api_secret
    elif exchange_id == "binance":
        cfg["apiKey"] = settings.binance_api_key
        cfg["secret"] = settings.binance_api_secret
        cfg["options"].update({"defaultSubType": "linear", "fetchMarkets": {"types": ["linear"]},
                               "disableFuturesSandboxWarning": True})
    exchange = getattr(ccxt, exchange_id)(cfg)
    try:
        try:
            if exchange_id == "bybit" and settings.bybit_testnet:
                exchange.set_sandbox_mode(True)
            elif exchange_id == "binance" and settings.binance_testnet:
                exchange.set_sandbox_mode(True)
        except Exception as sbx_exc:  # noqa: BLE001
            logger.error("[orders/%s] set_sandbox_mode failed: %s", exchange_id, sbx_exc)
        # Binance USDM requires a symbol for fetch_open_orders; try the bare
        # call first, then fall back to per-symbol over the configured assets.
        from src.services.market_registry import to_ccxt  # noqa: WPS433
        raw: list = []
        try:
            raw = await asyncio.wait_for(exchange.fetch_open_orders(), timeout=8.0)
        except asyncio.TimeoutError:
            return _stub_response(f"{exchange_id} open-orders timed out.")
        except Exception:  # noqa: BLE001
            try:
                await exchange.load_markets()
                for _sym in list(settings.trading_assets):
                    try:
                        # P0-3 fix: passar market_type para Binance COIN-M
                        _mt = (
                            getattr(settings, "binance_market_type", "linear")
                            if exchange_id == "binance" else "linear"
                        )
                        ccxt_sym = to_ccxt(_sym, exchange_id, market_type=_mt)  # type: ignore[arg-type]
                        part = await asyncio.wait_for(
                            exchange.fetch_open_orders(ccxt_sym), timeout=8.0)
                        raw.extend(part or [])
                    except Exception:  # noqa: BLE001
                        continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s fetch_open_orders failed: %s", exchange_id, exc)
                return _stub_response(f"{exchange_id} error: {type(exc).__name__}")
        # Build the set of symbols with an OPEN position so we can tag each
        # reduce-only order with is_orphan=True when no position matches —
        # the operator sees orphans (the leftover leg of a SL/TP that fired)
        # before the guardian's cleanup runs.
        active_symbols: set[str] = set()
        try:
            pos = await asyncio.wait_for(exchange.fetch_positions(), timeout=5.0)
            for p in pos or []:
                if abs(float(p.get("contracts") or 0)) > 0:
                    active_symbols.add(to_mekka(p.get("symbol") or "").upper())
        except Exception:  # noqa: BLE001
            pass

        items = []
        orphan_count = 0
        for o in raw or []:
            info = o.get("info") or {}
            otype = str(o.get("type") or info.get("type") or "").lower()
            stop_px = _to_float(o.get("stopPrice") or info.get("stopPrice") or info.get("triggerPrice"))
            reduce_only = bool(o.get("reduceOnly") or info.get("reduceOnly") or info.get("reduce_only"))
            kind = "SL" if ("stop" in otype and "profit" not in otype) else (
                "TP" if ("take_profit" in otype or "takeprofit" in otype) else otype.upper() or "ORDER")
            sym = to_mekka(o.get("symbol") or "")
            # An order is "orphan" when it's reduce-only (i.e., a closing leg)
            # for a symbol that no longer has an open position.
            is_orphan = bool(reduce_only) and sym.upper() not in active_symbols
            if is_orphan:
                orphan_count += 1
            items.append({
                "symbol": sym,
                "kind": kind, "side": (o.get("side") or "").upper(),
                "trigger_price": stop_px or None,
                "price": _to_float(o.get("price")) or None,
                "amount": _to_float(o.get("amount")),
                "reduce_only": reduce_only,
                "is_orphan": is_orphan,
                "order_id": str(o.get("id") or ""),
            })
        msg = (
            f"{orphan_count} órfão(s) detectado(s) — guardião limpa no próximo ciclo."
            if orphan_count > 0
            else (None if items else "Sem ordens abertas na corretora.")
        )
        return {"items": items, "count": len(items), "orphan_count": orphan_count,
                "source": exchange_id, "supported": True, "message": msg}
    finally:
        try:
            await exchange.close()
        except Exception:  # noqa: BLE001
            pass


async def fetch_positions(
    mark_prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Best-effort live read. Falls back to the stub shape on every
    sad path so the UI never breaks the dashboard layout.

    [Story 099] ``mark_prices`` is forwarded to ``_fetch_paper_positions``
    so estimated unrealised PnL can be shown in paper mode.

    [Phase 2] Dispatch by ``settings.active_exchange`` so the dashboard
    works against Bybit/Binance, not just Hyperliquid.
    """
    if settings.paper_trading:
        return await _fetch_paper_positions(mark_prices=mark_prices)

    global _LIVE_POSITIONS_CACHE
    now = time.monotonic()
    cached = _LIVE_POSITIONS_CACHE
    if cached and cached[0] > now:
        return cached[1]

    # In live mode, delegate to PortfolioManager regardless of exchange
    # (codex). PortfolioManager already implements per-exchange dispatch
    # (CCXT for Bybit/Binance, native SDK for Hyperliquid) and reuses a
    # long-lived client with the correct sandbox routing. Building a
    # second ephemeral client here would race PortfolioManager's session
    # and could double-count rate-limit budget on Bybit testnet.
    async with _LIVE_POSITIONS_LOCK:
        now = time.monotonic()
        cached = _LIVE_POSITIONS_CACHE
        if cached and cached[0] > now:
            return cached[1]

        try:
            from src.agents.portfolio_manager import PortfolioManager  # noqa: WPS433

            snapshot = await PortfolioManager().run()
        except Exception as exc:  # noqa: BLE001
            logger.warning("portfolio snapshot failed: %s", exc)
            data = _stub_response(f"Portfolio snapshot error: {type(exc).__name__}")
            _LIVE_POSITIONS_CACHE = (time.monotonic() + 1.0, data)
            return data

        # SL/TP for live positions are not carried by the PortfolioManager
        # snapshot (PositionSummary has no SL/TP fields). Recover them from the
        # SL/TP stored in each trade's execution metadata at order time.
        sltp_map = await _live_sltp_map()

        prices = mark_prices or {}
        items = []
        for p in snapshot.positions:
            sym = p.symbol
            side = p.side.upper()
            entry = _to_float(p.entry_price)
            size = _to_float(p.size)
            # Live mark: prefer the streaming price feed, then the venue mark
            # from the snapshot, then entry (so PnL reads 0 rather than crash).
            snap_mark = _to_float(getattr(p, "mark_price", None))
            mark = (
                _to_float(prices.get(sym) or prices.get(sym.upper()))
                or snap_mark
                or entry
            )

            # Prefer a live-recomputed PnL from the streaming mark so the panel
            # updates in real time. Fall back to the snapshot's uPnL when we
            # have no live mark (mark == entry → recompute is 0 anyway).
            if mark > 0 and entry > 0 and abs(mark - entry) > 1e-9:
                if side == "LONG":
                    pnl_usd = round((mark - entry) * size, 2)
                else:
                    pnl_usd = round((entry - mark) * size, 2)
            else:
                pnl_usd = round(_to_float(p.unrealized_pnl_usd), 2)

            # Position return on notional (price move %, sign follows side).
            if entry > 0:
                move_pct = (mark - entry) / entry * 100.0
                pnl_pct = round(move_pct if side == "LONG" else -move_pct, 2)
            else:
                pnl_pct = 0.0

            sltp = sltp_map.get((sym.upper(), side), {})
            items.append({
                "symbol": sym,
                "side": side,
                "size": size,
                "entry_price": entry,
                "mark_price": round(mark, 4),
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "leverage": p.leverage,
                "liq_price": _to_float(getattr(p, "liquidation_price", None)) or None,
                "sl_price": sltp.get("sl"),
                "tp_price": sltp.get("tp"),
                "is_paper": snapshot.is_paper,
            })
        if not items:
            data = {
                "items": [],
                "count": 0,
                "source": snapshot.source.value.lower(),
                "supported": True,
                "message": "No open positions.",
            }
        else:
            data = {
                "items": items,
                "count": len(items),
                "source": snapshot.source.value.lower(),
                "supported": True,
                "message": snapshot.error,
            }
        _LIVE_POSITIONS_CACHE = (time.monotonic() + 2.0, data)
        return data
