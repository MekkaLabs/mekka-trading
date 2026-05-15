"""
src/analytics/trend.py
======================
Higher-Timeframe (HTF) Trend Classifier — Story 072.

Fetches 4h OHLCV candles from Hyperliquid and classifies the prevailing
trend as UPTREND, DOWNTREND, or NEUTRAL using two complementary methods:

  1. EMA crossover (fast EMA 8 vs slow EMA 21 on close prices)
  2. Price-structure check: last close vs midpoint of the lookback range

When both methods agree → strong signal.
When they disagree → NEUTRAL (no confluence → Batman reduces or blocks).

Design
------
  • Same HTTP pattern as src/analytics/atr.py (aiohttp, no SDK dependency).
  • 5-minute in-memory cache to avoid hammering the API in monitor cycles.
  • Fails open: any error → returns NEUTRAL (Batman can still proceed).
  • HTF interval is configurable but defaults to 4h.

Hard rules
----------
  • NEVER raises — all exceptions are caught and logged.
  • NEVER places orders or modifies state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger("mekka.analytics.trend")

# ---------------------------------------------------------------------------
# Trend enum
# ---------------------------------------------------------------------------

class HTFTrend(str, Enum):
    UPTREND   = "UPTREND"
    DOWNTREND = "DOWNTREND"
    NEUTRAL   = "NEUTRAL"


# ---------------------------------------------------------------------------
# In-memory cache: (symbol, interval) → (HTFTrend, computed_at)
# ---------------------------------------------------------------------------
_TREND_CACHE: dict[str, tuple[HTFTrend, float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

_HL_API_URL = "https://api.hyperliquid.xyz/info"


def _normalise_symbol(symbol: str) -> str:
    return symbol.upper().split("-")[0].split("/")[0].split(":")[0]


# ---------------------------------------------------------------------------
# EMA helper
# ---------------------------------------------------------------------------

def _ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average — returns list of same length (first
    period-1 values are seeded with SMA).
    """
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    result: list[float] = []
    sma = sum(values[:period]) / period
    result.append(sma)
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def _classify(closes: list[float], fast: int = 8, slow: int = 21) -> HTFTrend:
    """Classify trend from close prices using EMA crossover + price structure."""
    if len(closes) < slow + 5:
        return HTFTrend.NEUTRAL

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    if not ema_fast or not ema_slow:
        return HTFTrend.NEUTRAL

    # EMA crossover signal: compare last 3 values of each (aligned from end)
    f_tail = ema_fast[-3:] if len(ema_fast) >= 3 else ema_fast
    s_tail = ema_slow[-3:] if len(ema_slow) >= 3 else ema_slow

    # Number of periods fast > slow (all available)
    n = min(len(f_tail), len(s_tail))
    ema_up   = sum(1 for i in range(n) if f_tail[i] > s_tail[i])
    ema_down = sum(1 for i in range(n) if f_tail[i] < s_tail[i])

    if ema_up == n:
        ema_signal = HTFTrend.UPTREND
    elif ema_down == n:
        ema_signal = HTFTrend.DOWNTREND
    else:
        ema_signal = HTFTrend.NEUTRAL

    # Price structure: last close vs midpoint of full range
    high = max(closes)
    low  = min(closes)
    mid  = (high + low) / 2.0
    last = closes[-1]

    if last > mid * 1.005:
        struct_signal = HTFTrend.UPTREND
    elif last < mid * 0.995:
        struct_signal = HTFTrend.DOWNTREND
    else:
        struct_signal = HTFTrend.NEUTRAL

    # Both agree → strong trend; one NEUTRAL → use the other; both differ → NEUTRAL
    if ema_signal == struct_signal:
        return ema_signal
    if ema_signal == HTFTrend.NEUTRAL:
        return struct_signal
    if struct_signal == HTFTrend.NEUTRAL:
        return ema_signal
    # Conflicting signals
    return HTFTrend.NEUTRAL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compute_htf_trend(
    symbol: str,
    interval: str = "4h",
    lookback: int = 30,
    force_refresh: bool = False,
) -> HTFTrend:
    """Return the prevailing trend on ``interval`` for ``symbol``.

    Args:
        symbol:        Trading pair (e.g., "BTC", "ETH", "BTC-PERP").
        interval:      Candle interval string — Hyperliquid supports
                       "1m","3m","5m","15m","30m","1h","2h","4h","8h","12h","1d".
        lookback:      Number of candles to fetch (more → longer trend window).
        force_refresh: Bypass the 5-minute cache.

    Returns:
        HTFTrend.UPTREND / DOWNTREND / NEUTRAL
        On any error returns NEUTRAL (fail-open).
    """
    coin = _normalise_symbol(symbol)
    cache_key = f"{coin}_{interval}_{lookback}"
    now = time.monotonic()

    if not force_refresh and cache_key in _TREND_CACHE:
        cached_trend, cached_at = _TREND_CACHE[cache_key]
        if now - cached_at < _CACHE_TTL_SECONDS:
            logger.debug("[Trend] cache hit %s/%s → %s", coin, interval, cached_trend.value)
            return cached_trend

    try:
        import aiohttp  # noqa: WPS433
        import time as _t  # noqa: WPS433

        # Map interval string to seconds for window calculation
        _TF_SECONDS = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "8h": 28800, "12h": 43200,
            "1d": 86400,
        }
        tf_sec = _TF_SECONDS.get(interval, 14400)  # default 4h
        end_ms = int(_t.time() * 1000)
        start_ms = end_ms - (lookback + 5) * tf_sec * 1000

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                _HL_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.warning("[Trend] HTTP %s for %s/%s", resp.status, coin, interval)
                    return HTFTrend.NEUTRAL
                data = await resp.json()

        candles: list[dict] = data if isinstance(data, list) else []
        if len(candles) < 10:
            logger.debug("[Trend] insufficient candles (%d) for %s/%s", len(candles), coin, interval)
            return HTFTrend.NEUTRAL

        closes = [float(c["c"]) for c in candles if "c" in c]
        trend = _classify(closes)

        _TREND_CACHE[cache_key] = (trend, now)
        logger.debug("[Trend] %s/%s → %s (%d candles)", coin, interval, trend.value, len(closes))
        return trend

    except asyncio.TimeoutError:
        logger.warning("[Trend] timeout for %s/%s", coin, interval)
        return HTFTrend.NEUTRAL
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Trend] unexpected error for %s/%s: %s", coin, interval, exc)
        return HTFTrend.NEUTRAL
