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

# Primary exchange is configured via ACTIVE_EXCHANGE env var (settings).
# Fallback chain: if primary fails, try the others in order.
_EXCHANGE_FALLBACK_CHAIN: dict[str, list[str]] = {
    "hyperliquid": ["bybit", "binance"],
    "bybit":       ["hyperliquid", "binance"],
    "binance":     ["hyperliquid", "bybit"],
}


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
        # [C2] Track which exchange is active to pick the right symbol format.
        # Hyperliquid: 'BTC/USDC:USDC'; Binance/Bybit perps: 'BTC/USDT:USDT'
        self._exchange_id: str = ""

    # ------------------------------------------------------------------
    # Exchange lifecycle
    # ------------------------------------------------------------------

    def _build_ccxt_config(self, ex_id: str) -> dict:
        """Return CCXT constructor kwargs for a given exchange id."""
        import ccxt.async_support as ccxt  # noqa: WPS433

        base_cfg: dict = {
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "recvWindow": 10_000,
                "adjustForTimeDifference": True,
            },
        }

        if ex_id == "hyperliquid":
            base_cfg["options"]["sandboxMode"] = not settings.is_mainnet
        elif ex_id == "bybit":
            if settings.bybit_api_key:
                base_cfg["apiKey"] = settings.bybit_api_key
                base_cfg["secret"] = settings.bybit_api_secret
        elif ex_id == "binance":
            if settings.binance_api_key:
                base_cfg["apiKey"] = settings.binance_api_key
                base_cfg["secret"] = settings.binance_api_secret

        return base_cfg

    async def _get_exchange(self) -> Any:
        """Lazy-init a CCXT async exchange instance.

        Respects ``settings.active_exchange`` as primary, falls back through
        ``_EXCHANGE_FALLBACK_CHAIN`` on connection failure so market data
        remains available even when the primary exchange is down.
        """
        if self._exchange is not None:
            return self._exchange

        # Lazy import — keeps module import cheap when ccxt isn't installed
        import ccxt.async_support as ccxt  # noqa: WPS433

        primary = settings.active_exchange
        fallbacks = _EXCHANGE_FALLBACK_CHAIN.get(primary, [])
        all_attempts = [primary] + fallbacks

        for ex_id in all_attempts:
            try:
                cfg = self._build_ccxt_config(ex_id)
                exchange = getattr(ccxt, ex_id)(cfg)
                try:
                    if ex_id in ("bybit", "binance") and not settings.is_mainnet:
                        set_sandbox = getattr(exchange, "set_sandbox_mode", None)
                        if callable(set_sandbox):
                            set_sandbox(True)
                    await exchange.load_markets()
                    self._exchange = exchange
                    self._exchange_id = ex_id
                    if ex_id == primary:
                        self._log.info(f"[Superman] Connected to {ex_id} via CCXT (primary)")
                    else:
                        self._log.warning(
                            f"[Superman] Primary '{primary}' failed — connected to {ex_id} (fallback)"
                        )
                    return exchange
                except Exception:
                    await exchange.close()
                    raise
            except Exception as exc:
                self._log.warning(f"[Superman] {ex_id} CCXT unavailable: {exc}")
                continue

        raise AgentError("Superman", "Could not connect to any exchange")

    async def close(self) -> None:
        """Close the underlying CCXT exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
            self._exchange_id = ""

    # ------------------------------------------------------------------
    # Story 050 — Symbol validation for Altcoins toggle
    # ------------------------------------------------------------------

    async def validate_symbols(self, symbols: list[str]) -> list[str]:
        """
        Filter ``symbols`` to only those available on the active exchange.

        Returns a list preserving the original order, dropping any symbol
        whose perpetual contract is not in the exchange's market list.
        Never raises — on any error returns the original list unchanged so
        the cycle continues with best-effort assets.
        """
        try:
            exchange = await self._get_exchange()
            markets = exchange.markets or {}
            available: list[str] = []
            for sym in symbols:
                if self._exchange_id in ("binance", "bybit"):
                    ccxt_sym = f"{sym}/USDT:USDT"
                else:
                    ccxt_sym = f"{sym}/USDC:USDC"
                if ccxt_sym in markets:
                    available.append(sym)
                else:
                    self._log.warning(
                        f"[Superman] {sym} ({ccxt_sym}) not in {self._exchange_id} markets — skipped"
                    )
            return available if available else symbols
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                f"[Superman] validate_symbols failed (using full list): {exc}"
            )
            return symbols

    # ------------------------------------------------------------------
    # Story 050 — Retry helper for OHLCV fetches
    # ------------------------------------------------------------------

    async def _fetch_ohlcv_with_retry(
        self,
        exchange: Any,
        ccxt_symbol: str,
        timeframe: str,
        limit: int,
    ) -> list:
        """
        Fetch OHLCV with exponential backoff for rate-limit and network errors.

        Retries up to ``settings.superman_max_retries`` times (default 3)
        with backoff of 1s → 2s → 4s.  Other errors propagate immediately.
        """
        import asyncio as _aio  # noqa: WPS433

        try:
            import ccxt  # noqa: WPS433
            _RateLimitExceeded = ccxt.RateLimitExceeded
            _NetworkError = ccxt.NetworkError
        except (ImportError, AttributeError):
            _RateLimitExceeded = Exception  # type: ignore[assignment,misc]
            _NetworkError = Exception  # type: ignore[assignment,misc]

        max_retries: int = getattr(settings, "superman_max_retries", 3)
        base_backoff = 1.0

        for attempt in range(max_retries + 1):
            try:
                return await exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=limit)
            except _RateLimitExceeded as exc:
                if attempt < max_retries:
                    wait = base_backoff * (2 ** attempt)
                    self._log.warning(
                        f"[Superman] RateLimitExceeded for {ccxt_symbol} — "
                        f"retry {attempt + 1}/{max_retries} in {wait:.0f}s"
                    )
                    await _aio.sleep(wait)
                else:
                    raise AgentError(
                        "Superman",
                        f"RateLimitExceeded after {max_retries} retries for {ccxt_symbol}: {exc}",
                    ) from exc
            except _NetworkError as exc:
                if attempt < max_retries:
                    wait = base_backoff
                    self._log.warning(
                        f"[Superman] NetworkError for {ccxt_symbol} — "
                        f"retry {attempt + 1}/{max_retries} in {wait:.0f}s"
                    )
                    await _aio.sleep(wait)
                else:
                    raise AgentError(
                        "Superman",
                        f"NetworkError after {max_retries} retries for {ccxt_symbol}: {exc}",
                    ) from exc
        return []  # unreachable but satisfies type-checkers

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

        # Lazy imports — pandas-ta registers the `.ta` DataFrame accessor on import
        # and pulls heavy transitive deps. Defer until we actually need to compute.
        import pandas as pd  # noqa: WPS433
        try:
            import pandas_ta as ta  # noqa: F401, WPS433  (registers DataFrame accessor)
        except (ImportError, ModuleNotFoundError):
            # pandas-ta não disponível (ex: Python 3.14 sem numba) — Superman
            # continuará sem indicadores avançados do pandas_ta, usando apenas
            # os cálculos manuais abaixo.
            ta = None  # type: ignore[assignment]

        exchange = await self._get_exchange()

        # [C2] Perpetual symbol format differs by exchange:
        #   Hyperliquid: 'BTC/USDC:USDC'  (uses USDC margin, not USDT)
        #   Binance/Bybit (swap): 'BTC/USDT:USDT'
        if self._exchange_id in ("binance", "bybit"):
            ccxt_symbol = f"{symbol}/USDT:USDT"
        else:
            ccxt_symbol = f"{symbol}/USDC:USDC"

        # --- Fetch OHLCV (Story 050 — with exponential backoff retry) ---
        try:
            raw = await self._fetch_ohlcv_with_retry(exchange, ccxt_symbol, tf, limit)
        except AgentError:
            raise
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
        # Tenta usar pandas_ta se disponível; caso contrário usa cálculos manuais.
        _use_ta = ta is not None and hasattr(df, "ta")

        if _use_ta:
            try:
                df.ta.rsi(length=14, append=True)
                df.ta.ema(length=20, append=True)
                df.ta.ema(length=50, append=True)
                df.ta.bbands(length=20, std=2, append=True)
                df.ta.macd(fast=12, slow=26, signal=9, append=True)
                df.ta.atr(length=14, append=True)
            except Exception:
                _use_ta = False

        if not _use_ta:
            # RSI manual
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, float("nan"))
            df["RSI_14"] = 100 - (100 / (1 + rs))

            # EMA manual
            df["EMA_20"] = df["close"].ewm(span=20, adjust=False).mean()
            df["EMA_50"] = df["close"].ewm(span=50, adjust=False).mean()

            # Bollinger Bands manual
            bb_mid_s = df["close"].rolling(20).mean()
            bb_std_s = df["close"].rolling(20).std()
            df["BBM_20_2.0"] = bb_mid_s
            df["BBU_20_2.0"] = bb_mid_s + 2 * bb_std_s
            df["BBL_20_2.0"] = bb_mid_s - 2 * bb_std_s

            # MACD manual
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            df["MACD_12_26_9"] = ema12 - ema26
            df["MACDs_12_26_9"] = df["MACD_12_26_9"].ewm(span=9, adjust=False).mean()
            df["MACDh_12_26_9"] = df["MACD_12_26_9"] - df["MACDs_12_26_9"]

            # ATR manual
            hl = df["high"] - df["low"]
            hc = (df["high"] - df["close"].shift()).abs()
            lc = (df["low"] - df["close"].shift()).abs()
            tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            df["ATRr_14"] = tr.ewm(span=14, adjust=False).mean()

        rsi_col = "RSI_14"

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

        # [C5] Extract last 20 closes for Flash momentum detection.
        # Use at most 20 candles to keep the list concise but informative.
        recent_closes = [float(v) for v in df["close"].iloc[-20:].tolist()]

        # --- Classify trend ---
        trend, trend_strength = _classify_trend(
            price, ema20, ema50, rsi, macd_hist
        )

        rsi_display = f"{rsi:.1f}" if rsi is not None else "N/A"
        self._log.info(
            f"[Superman] {symbol} {tf} | price={price:,.4f} "
            f"trend={trend.value}({trend_strength:.2f}) "
            f"rsi={rsi_display}"
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
            recent_closes=recent_closes,  # [C5]
        )
