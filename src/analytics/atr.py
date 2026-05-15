"""
src/analytics/atr.py
====================
ATR (Average True Range) calculator — Story 070.

Fetches 1h OHLCV candles from Hyperliquid (via the same candleSnapshot API
used by the dashboard) and computes the 14-period ATR as a percentage of the
current price.

Design
------
  • Pure async, no SDK dependency — uses aiohttp directly.
  • LRU-style in-memory cache with a 5-minute TTL so consecutive Batman calls
    within the same monitor cycle share the same ATR computation.
  • Falls back gracefully: if the network call fails or candles are insufficient,
    returns None so Batman proceeds without the ATR adjustment (fail-open).
  • Normalises symbol names to the Hyperliquid coin format (e.g. "BTC-PERP" → "BTC").

Hard rules
----------
  • NEVER modifies global state beyond the module-level cache dict.
  • NEVER raises — all exceptions are caught and logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("mekka.analytics.atr")

# ---------------------------------------------------------------------------
# In-memory cache: symbol → (atr_pct, computed_at_epoch)
# ---------------------------------------------------------------------------
_ATR_CACHE: dict[str, tuple[float, float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# Hyperliquid candleSnapshot endpoint (same as dashboard server)
_HL_API_URL = "https://api.hyperliquid.xyz/info"


def _normalise_symbol(symbol: str) -> str:
    """Strip exchange suffixes so 'BTC-PERP' → 'BTC', 'ETH/USDC:USDC' → 'ETH'."""
    sym = symbol.upper().split("-")[0].split("/")[0].split(":")[0]
    return sym


def _compute_atr(candles: list[dict], lookback: int) -> Optional[float]:
    """Compute ATR from a list of OHLCV dicts.

    Each candle must have keys: ``o`` (open), ``h`` (high), ``l`` (low),
    ``c`` (close) — Hyperliquid candleSnapshot format.

    Returns the ATR value in price units, or None if insufficient data.
    """
    if len(candles) < lookback + 1:
        return None

    # Use only the last (lookback + 1) candles
    recent = candles[-(lookback + 1):]

    true_ranges: list[float] = []
    for i in range(1, len(recent)):
        try:
            high = float(recent[i]["h"])
            low = float(recent[i]["l"])
            prev_close = float(recent[i - 1]["c"])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        except (KeyError, TypeError, ValueError):
            continue

    if not true_ranges:
        return None

    # Simple average (SMA ATR) — Wilder's smoothed ATR needs more history
    return sum(true_ranges) / len(true_ranges)


async def compute_atr_pct(
    symbol: str,
    lookback: int = 14,
    force_refresh: bool = False,
) -> Optional[float]:
    """Return the ATR% (ATR / close_price × 100) for ``symbol`` over ``lookback`` 1h candles.

    Returns None if the computation is not possible (network error, bad data, etc.).
    The result is cached for 5 minutes.

    Example: BTC ATR = $1,500, close = $100,000 → ATR% = 1.5
    """
    coin = _normalise_symbol(symbol)
    cache_key = f"{coin}_{lookback}"
    now = time.monotonic()

    # Return cached value if fresh
    if not force_refresh and cache_key in _ATR_CACHE:
        cached_atr_pct, cached_at = _ATR_CACHE[cache_key]
        if now - cached_at < _CACHE_TTL_SECONDS:
            logger.debug("[ATR] cache hit %s → %.4f%%", coin, cached_atr_pct)
            return cached_atr_pct

    try:
        import aiohttp  # noqa: WPS433

        # Need lookback + 2 candles to guarantee lookback TRs after the first diff
        limit = lookback + 10
        # Use epoch-ms window: last (limit * 3600) seconds
        import time as _t
        end_ms = int(_t.time() * 1000)
        start_ms = end_ms - limit * 3_600_000  # limit hours in ms

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1h",
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                _HL_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status != 200:
                    logger.warning("[ATR] HTTP %s for %s", resp.status, coin)
                    return None
                data = await resp.json()

        candles: list[dict] = data if isinstance(data, list) else []
        if len(candles) < lookback + 1:
            logger.debug("[ATR] insufficient candles (%d) for %s", len(candles), coin)
            return None

        atr_value = _compute_atr(candles, lookback)
        if atr_value is None:
            return None

        try:
            close_price = float(candles[-1]["c"])
        except (KeyError, TypeError, ValueError):
            return None

        if close_price <= 0:
            return None

        atr_pct = (atr_value / close_price) * 100.0

        # Cache the result
        _ATR_CACHE[cache_key] = (round(atr_pct, 6), now)
        logger.debug("[ATR] computed %s atr=%.4f close=%.2f atr_pct=%.4f%%", coin, atr_value, close_price, atr_pct)
        return round(atr_pct, 6)

    except asyncio.TimeoutError:
        logger.warning("[ATR] timeout fetching candles for %s", coin)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ATR] unexpected error for %s: %s", coin, exc)
        return None
