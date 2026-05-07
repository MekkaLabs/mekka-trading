"""
src/agents/superman.py
======================
Superman — Chief Market Overseer

Responsibilities
----------------
- Fetches OHLCV candles from Hyperliquid (via CCXT) for each asset
- Computes: RSI-14, EMA-20/50, Bollinger Bands, MACD, ATR-14, Volume MA
- Runs on two timeframes: primary (4h) and confirmation (1h)
- Classifies trend direction and strength
- Returns a `MarketData` Pydantic model

Hard Rules
----------
- Never places orders
- Falls back to None indicators if data is insufficient (< 50 candles)
- Always emits a structured log per symbol
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from src.agents.base import AgentError, BaseAgent
from src.config.settings import settings
from src.models.market_data import MarketData, Trend

# NOTE: ccxt and pandas_ta are imported lazily inside methods. Both pull heavy
# transitive dependencies (e.g. numba via pandas_ta) that may not build on
# every Python version. Lazy import keeps `import src.agents.superman` cheap
# and lets the rest of the test suite collect even when those libs are
# unavailable. Same pattern Iron Man uses for the Hyperliquid SDK.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXCHANGE_ID = "hyperliquid"  # CCXT exchange id
_FALLBACK_EXCHANGE_IDS = ["binance", "bybit"]  # fallbacks if HL unavailable


def _classify_trend(
    price: float,
    ema20: Optional[float],
    ema50: Optional[float],
    rsi: Optional[float],
    macd_hist: Optional[float],
) -> tuple[Trend, float]:
    """
    Heuristic trend classification based on EMA relationship + RSI + MACD.

    Returns (Trend, strength: 0.0–1.0)
    """
    if ema20 is None or ema50 is None:
        return Trend.NEUTRAL, 0.0

    votes_bull = 0
    votes_bear = 0
    total = 0

    # EMA cross
    if ema20 > ema50:
        votes_bull += 2
    else:
        votes_bear += 2
    total += 2

    # Price vs EMA50
    if price > ema50:
        votes_bull += 1
    else:
        votes_bear += 1
    total += 1

    # RSI
    if rsi is not None:
        total += 1
        if rsi > 55:
            votes_bull += 1
        elif rsi < 45:
            votes_bear += 1

    # MACD histogram
    if macd_hist is not None:
        total += 1
        if macd_hist > 0:
            votes_bull += 1
        elif macd_hist < 0:
            votes_bear += 1

    net = (votes_bull - votes_bear) / total  # -1.0 to +1.0
    strength = abs(net)

    if net > 0.2:
        return Trend.BULLISH, min(strength, 1.0)
    elif net < -0.2:
        return Trend.BEARISH, min(strength, 1.0)
    return Trend.NEUTRAL, min(strength, 1.0)


def _safe_float(series: pd.Series, idx: int = -1) -> Optional[float]:
    """Return the last valid float from a pandas Series, or None."""
    try:
        val = float(series.iloc[idx])
        return None if np.isnan(val) else val
    except (IndexError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Superman Agent
# ---------------------------------------------------------------------------


class Superman(BaseAgent[MarketData]):
    """
    Chief Market Overseer — computes full technical analysis for one symbol.

    Usage
    -----
        agent = Superman()
        market_data = await agent.run(symbol="BTC", timeframe="4h")
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Superman",
            role="Chief Market Overseer — multi-asset technical analysis",
        )
        self._exchange: Optional[Any] = None  # CCXT exchange instance, set lazily

    # ------------------------------------------------------------------
    # Exchange lifecycle
    # ------------------------------------------------------------------

    async def _get_exchange(self) -> Any:
        """Lazy-init a CCXT async exchange instance."""
        if self._exchange is not None:
            return self._exchange

        # Lazy import — keeps module import cheap when ccxt isn't installed
        import ccxt.async_support as ccxt  # noqa: WPS433

        # Try Hyperliquid first (testnet / mainnet)
        try:
            exchange = ccxt.hyperliquid(
                {
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "swap",
                        "sandboxMode": not settings.is_mainnet,
                    },
                }
            )
            # Quick connectivity check
            await exchange.load_markets()
            self._exchange = exchange
            self._log.info("Connected to Hyperliquid via CCXT")
            return exchange
        except Exception as exc:
            self._log.warning(
                f"Hyperliquid CCXT unavailable ({exc}), trying fallbacks"
            )

        # Fallback to Binance (public endpoints, no auth needed)
        for ex_id in _FALLBACK_EXCHANGE_IDS:
            try:
                exchange = getattr(ccxt, ex_id)({"enableRateLimit": True})
                await exchange.load_markets()
                self._exchange = exchange
                self._log.info(f"Connected to {ex_id} via CCXT (fallback)")
                return exchange
            except Exception:
                continue

        raise AgentError("Superman", "Could not connect to any exchange")

    async def close(self) -> None:
        """Close the underlying CCXT exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(  # type: ignore[override]
        self,
        symbol: str,
        timeframe: Optional[str] = None,
    ) -> MarketData:
        """
        Fetch OHLCV data and compute all technical indicators.

        Parameters
        ----------
        symbol    : Asset symbol, e.g. 'BTC'
        timeframe : OHLCV timeframe, defaults to settings.primary_timeframe
        """
        tf = timeframe or settings.primary_timeframe
        limit = settings.candles_lookback
        ccxt_symbol = f"{symbol}/USDT"

        # Lazy imports — pandas-ta registers the `.ta` DataFrame accessor on import
        # and pulls heavy transitive deps. Defer until we actually need to compute.
        import pandas as pd  # noqa: WPS433
        import pandas_ta as ta  # noqa: F401, WPS433  (registers DataFrame accessor)

        exchange = await self._get_exchange()

        # --- Fetch OHLCV ---
        try:
            raw = await exchange.fetch_ohlcv(ccxt_symbol, tf, limit=limit)
        except Exception as exc:
            raise AgentError(
                "Superman",
                f"OHLCV fetch failed for {symbol}/{tf}: {exc}",
            ) from exc

        if not raw or len(raw) < 2:
            raise AgentError("Superman", f"No OHLCV data returned for {symbol}")

        # --- Build DataFrame ---
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").astype(float)

        # --- Compute indicators ---
        # RSI
        df.ta.rsi(length=14, append=True)
        rsi_col = "RSI_14"

        # EMA
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)

        # Bollinger Bands
        df.ta.bbands(length=20, std=2, append=True)

        # MACD
        df.ta.macd(fast=12, slow=26, signal=9, append=True)

        # ATR
        df.ta.atr(length=14, append=True)

        # Volume MA
        df["VOLUME_MA_20"] = df["volume"].rolling(20).mean()

        # --- Extract last values ---
        price = float(df["close"].iloc[-1])
        ts = df.index[-1].to_pydatetime().replace(tzinfo=timezone.utc)

        rsi = _safe_float(df.get(rsi_col, pd.Series(dtype=float)))
        ema20 = _safe_float(df.get("EMA_20", pd.Series(dtype=float)))
        ema50 = _safe_float(df.get("EMA_50", pd.Series(dtype=float)))

        # Bollinger
        bb_upper = _safe_float(df.get("BBU_20_2.0", pd.Series(dtype=float)))
        bb_lower = _safe_float(df.get("BBL_20_2.0", pd.Series(dtype=float)))
        bb_mid = _safe_float(df.get("BBM_20_2.0", pd.Series(dtype=float)))

        # MACD
        macd = _safe_float(df.get("MACD_12_26_9", pd.Series(dtype=float)))
        macd_signal = _safe_float(df.get("MACDs_12_26_9", pd.Series(dtype=float)))
        macd_hist = _safe_float(df.get("MACDh_12_26_9", pd.Series(dtype=float)))

        # ATR
        atr = _safe_float(df.get("ATRr_14", pd.Series(dtype=float)))

        # Volume
        volume = float(df["volume"].iloc[-1])
        volume_ma = _safe_float(df.get("VOLUME_MA_20", pd.Series(dtype=float)))

        # --- Classify trend ---
        trend, trend_strength = _classify_trend(
            price, ema20, ema50, rsi, macd_hist
        )

        self._log.info(
            f"[Superman] {symbol} {tf} | price={price:,.4f} "
            f"trend={trend.value}({trend_strength:.2f}) "
            f"rsi={rsi:.1f if rsi else 'N/A'}"
        )

        return MarketData(
            symbol=symbol,
            timestamp=ts,
            timeframe=tf,
            price=price,
            rsi_14=rsi,
            ema_20=ema20,
            ema_50=ema50,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_mid=bb_mid,
            macd=macd,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
            atr_14=atr,
            volume=volume,
            volume_ma=volume_ma,
            trend=trend,
            trend_strength=trend_strength,
        )
