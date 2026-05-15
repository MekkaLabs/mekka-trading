"""
src/analytics/funding.py
========================
Funding Rate fetcher with in-memory cache — Story 075.

Wraps the existing ``src.dashboard.funding_provider.fetch_funding_rates``
so Batman can query funding rates without hammering the API on every
monitor cycle. Cache TTL = 5 minutes (funding updates every 8 hours so
any cache under 8h is fine).

Returned value: funding rate as percentage per 8-hour interval.
  e.g. 0.05 → 0.05% → market is paying longs at high cost → CROWDED LONG
  e.g. -0.05 → market is paying shorts at high cost → CROWDED SHORT

Hard rules
----------
  • NEVER raises — returns None on any error (Batman gate fails open).
  • Normalises symbol to coin format before querying.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("mekka.analytics.funding")

_FUNDING_CACHE: dict[str, tuple[float, float]] = {}  # symbol → (pct, ts)
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _normalise(symbol: str) -> str:
    return symbol.upper().split("-")[0].split("/")[0].split(":")[0]


async def get_funding_rate_pct(symbol: str, force_refresh: bool = False) -> Optional[float]:
    """Return the current 8h funding rate in percent for ``symbol``.

    Positive → longs pay shorts (LONG crowded / bullish sentiment).
    Negative → shorts pay longs (SHORT crowded / bearish sentiment).
    None     → could not determine (gate fails open).
    """
    coin = _normalise(symbol)
    now = time.monotonic()

    if not force_refresh and coin in _FUNDING_CACHE:
        cached_pct, cached_at = _FUNDING_CACHE[coin]
        if now - cached_at < _CACHE_TTL_SECONDS:
            logger.debug("[Funding] cache hit %s → %.5f%%", coin, cached_pct)
            return cached_pct

    try:
        from src.dashboard.funding_provider import fetch_funding_rates  # noqa: WPS433
        data = await asyncio.wait_for(fetch_funding_rates([coin]), timeout=8.0)
        items = data.get("items") or []
        for item in items:
            if _normalise(item.get("symbol", "")) == coin:
                pct = float(item.get("funding_pct", 0.0))
                _FUNDING_CACHE[coin] = (pct, now)
                logger.debug("[Funding] %s → %.5f%%/8h", coin, pct)
                return round(pct, 6)
        logger.debug("[Funding] symbol %s not found in funding data", coin)
        return None
    except asyncio.TimeoutError:
        logger.warning("[Funding] timeout fetching %s", coin)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Funding] error for %s: %s", coin, exc)
        return None
