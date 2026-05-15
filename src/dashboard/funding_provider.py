"""
src/dashboard/funding_provider.py
==================================
Fetches perpetual funding rates for the dashboard Funding Rates panel.

Primary source: Hyperliquid public API (`meta_and_asset_ctxs`) —
  no authentication required; works in both paper and live mode.

Fallback: Binance USDT-M futures (`GET /fapi/v1/premiumIndex`) —
  used only if Hyperliquid fails or returns no data for a symbol.

Output contract (stable, used by GET /api/market/funding):
  {
    "items": [
      {
        "symbol":        str,        # e.g. "BTC"
        "funding_rate":  float,      # current 8h rate (e.g. 0.00041)
        "funding_pct":   float,      # = funding_rate * 100
        "annualized_pct": float,     # = funding_rate * 3 * 365 * 100
        "interval_h":    int,        # always 8 for HL/Binance perps
        "mark_price":    float|None,
        "open_interest": float|None, # USD notional
        "sentiment":     str,        # "bullish"|"bearish"|"neutral"
        "source":        str,        # "hyperliquid"|"binance"|"stub"
      }, ...
    ],
    "count":         int,
    "as_of_utc":     str,           # ISO-8601
    "source_primary": str,
    "error":         str|None,
  }

Sentiment heuristic
-------------------
  positive funding → longs pay shorts → market is LONG-biased → "bullish"
  negative funding → shorts pay longs → market is SHORT-biased → "bearish"
  |rate| < 0.005%  → "neutral"
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.config.settings import settings
from src.config.runtime_mode import get_mode, PRESETS

logger = logging.getLogger("mekka.dashboard.funding")

# Binance USDT-M futures base URL (public, no auth)
_BINANCE_FAPI = "https://fapi.binance.com"
# Hyperliquid public API
_HL_MAINNET = "https://api.hyperliquid.xyz/info"
_HL_TESTNET = "https://api.hyperliquid-testnet.xyz/info"

_NEUTRAL_THRESHOLD = 0.00005  # |rate| below this → neutral (~0.005%)


def _sentiment(rate: float) -> str:
    if abs(rate) < _NEUTRAL_THRESHOLD:
        return "neutral"
    return "bullish" if rate > 0 else "bearish"


def _build_item(
    symbol: str,
    funding_rate: float,
    mark_price: float | None = None,
    open_interest: float | None = None,
    source: str = "stub",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "funding_rate": round(funding_rate, 8),
        "funding_pct": round(funding_rate * 100, 6),
        "annualized_pct": round(funding_rate * 3 * 365 * 100, 2),
        "interval_h": 8,
        "mark_price": mark_price,
        "open_interest": open_interest,
        "sentiment": _sentiment(funding_rate),
        "source": source,
    }


def _current_assets() -> list[str]:
    """Return the asset list for the current trading mode."""
    try:
        mode = get_mode()
        return list(PRESETS[mode]["trading_assets"])
    except Exception:
        return list(settings.trading_assets)


# ---------------------------------------------------------------------------
# Hyperliquid source
# ---------------------------------------------------------------------------


async def _fetch_hyperliquid(
    symbols: list[str],
    session: Any,
) -> dict[str, dict[str, Any]]:
    """
    Calls Hyperliquid public `meta_and_asset_ctxs`.
    Returns {symbol: item_dict} for symbols we care about.
    """
    base = _HL_MAINNET if settings.is_mainnet else _HL_TESTNET
    try:
        async with session.post(
            base,
            json={"type": "metaAndAssetCtxs"},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                logger.warning("HL metaAndAssetCtxs returned HTTP %s", resp.status)
                return {}
            data = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HL funding fetch failed: %s", exc)
        return {}

    if not isinstance(data, list) or len(data) < 2:
        return {}

    meta, ctxs = data[0], data[1]
    universe = meta.get("universe", []) or []

    result: dict[str, dict[str, Any]] = {}
    for asset_meta, ctx in zip(universe, ctxs or []):
        name = str(asset_meta.get("name", "")).upper()
        if name not in symbols:
            continue
        try:
            rate = float(ctx.get("funding") or 0.0)
            mark = float(ctx.get("markPx") or 0.0) or None
            oi_raw = ctx.get("openInterest")
            oi = float(oi_raw) if oi_raw is not None else None
            # OI is in contracts (coins); convert to USD using mark price
            if oi is not None and mark:
                oi = oi * mark
            result[name] = _build_item(
                symbol=name,
                funding_rate=rate,
                mark_price=mark,
                open_interest=oi,
                source="hyperliquid",
            )
        except Exception:  # noqa: BLE001
            continue

    return result


# ---------------------------------------------------------------------------
# Binance fallback source
# ---------------------------------------------------------------------------


async def _fetch_binance(
    symbols: list[str],
    session: Any,
) -> dict[str, dict[str, Any]]:
    """
    Calls Binance USDT-M `GET /fapi/v1/premiumIndex` for each symbol.
    Returns {symbol: item_dict}.
    """
    result: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        ticker = f"{sym}USDT"
        try:
            async with session.get(
                f"{_BINANCE_FAPI}/fapi/v1/premiumIndex",
                params={"symbol": ticker},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    continue
                d = await resp.json(content_type=None)
            rate = float(d.get("lastFundingRate") or 0.0)
            mark = float(d.get("markPrice") or 0.0) or None
            result[sym] = _build_item(
                symbol=sym,
                funding_rate=rate,
                mark_price=mark,
                source="binance",
            )
        except Exception:  # noqa: BLE001
            continue
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def fetch_funding_rates(symbols: list[str] | None = None) -> dict[str, Any]:
    """
    Fetch funding rates for the given symbols (defaults to current mode assets).

    Uses Hyperliquid as primary; falls back to Binance for any symbol missing
    in the HL response.
    """
    if symbols is None:
        symbols = _current_assets()

    symbols_upper = [s.upper() for s in symbols]
    as_of = datetime.now(timezone.utc).isoformat()

    async with aiohttp.ClientSession() as session:
        hl_data = await _fetch_hyperliquid(symbols_upper, session)

        # Fill gaps with Binance
        missing = [s for s in symbols_upper if s not in hl_data]
        binance_data: dict[str, Any] = {}
        if missing:
            binance_data = await _fetch_binance(missing, session)

    merged: dict[str, dict[str, Any]] = {**hl_data, **binance_data}

    # Build items in the requested order
    items = []
    for sym in symbols_upper:
        if sym in merged:
            items.append(merged[sym])
        else:
            # Stub entry so the UI always gets all rows
            items.append(_build_item(sym, 0.0, source="stub"))

    source_primary = "hyperliquid" if hl_data else ("binance" if binance_data else "stub")

    return {
        "items": items,
        "count": len(items),
        "as_of_utc": as_of,
        "source_primary": source_primary,
        "error": None if (hl_data or binance_data) else "all sources failed",
    }
