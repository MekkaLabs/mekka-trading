"""
src/agents/thor.py
==================
Thor — Volatility Engine

Input  : `MarketData` from Superman (contains atr_14 and price)
Output : `VolatilityData` with regime classification and position size multiplier

Regime thresholds (ATR as % of price):
  < 1%   → LOW      → size multiplier 1.2x  (add size in calm markets)
  1-3%   → MEDIUM   → size multiplier 1.0x  (normal)
  3-6%   → HIGH     → size multiplier 0.6x  (reduce size)
  > 6%   → EXTREME  → size multiplier 0.3x  (very small positions)

Thor also computes 7-day realized volatility from a rolling returns window
if the full candle history is passed.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from src.agents.base import BaseAgent
from src.models.market_data import MarketData, VolatilityData, VolatilityRegime


def _compute_realized_vol(prices: list[float], window: int = 7 * 6) -> Optional[float]:
    """
    Compute annualized realized volatility from a list of close prices.

    Uses log-return standard deviation × sqrt(annualization factor).
    For 4h candles: 6 candles/day × 365 days = 2190 annualization factor.

    Parameters
    ----------
    prices : list of closing prices (chronological order)
    window : number of candles to include (default = 7 days × 6 candles/day)

    Returns
    -------
    Annualized realized vol as a float (e.g. 0.85 = 85%), or None if insufficient data.
    """
    if len(prices) < window + 1:
        return None

    recent = prices[-(window + 1):]
    log_returns = [
        math.log(recent[i] / recent[i - 1])
        for i in range(1, len(recent))
        if recent[i - 1] > 0 and recent[i] > 0
    ]

    if len(log_returns) < 2:
        return None

    n = len(log_returns)
    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
    std = math.sqrt(variance)

    # Annualize: 4h candles → 6/day × 365 days
    annualization = math.sqrt(6 * 365)
    return round(std * annualization, 4)


class Thor(BaseAgent[VolatilityData]):
    """
    Volatility Engine — classifies volatility regime and adjusts position sizing.

    Usage:
        agent = Thor()
        vol_data = await agent.run(market_data=md, price_history=[...])
    """

    def __init__(self) -> None:
        super().__init__(
            "Thor",
            "Volatility Engine — regime classification and position sizing",
            timeout_s=15.0,  # Cálculos locais sobre candles já fornecidos
        )

    async def _run(  # type: ignore[override]
        self,
        market_data: MarketData,
        price_history: Optional[list[float]] = None,
    ) -> VolatilityData:
        """
        Classify volatility and compute position size multiplier.

        Parameters
        ----------
        market_data   : Output from Superman for the same symbol/timeframe
        price_history : Optional list of recent close prices for realized vol calculation
                        (if omitted, realized_vol_7d will be None)
        """
        symbol = market_data.symbol
        price = market_data.price
        atr = market_data.atr_14

        # ATR% = ATR / price
        if atr is not None and price > 0:
            atr_pct = atr / price
        else:
            # Review-fix (2026-06-01): ATR ausente → assumir regime ALTO (não
            # MEDIUM). "Não sei a volatilidade" NÃO deve virar "posição cheia":
            # ATR costuma faltar justamente com dados ruins/poucos candles —
            # exatamente quando se quer REDUZIR o tamanho. 0.045 cai em HIGH (0.6×).
            atr_pct = 0.045
            self._log.warning(
                f"[Thor] {symbol} ATR unavailable — assumindo regime HIGH "
                "(sizing conservador 0.6×)"
            )

        # Classify regime
        if atr_pct < 0.01:
            regime = VolatilityRegime.LOW
            multiplier = 1.2
        elif atr_pct < 0.03:
            regime = VolatilityRegime.MEDIUM
            multiplier = 1.0
        elif atr_pct < 0.06:
            regime = VolatilityRegime.HIGH
            multiplier = 0.6
        else:
            regime = VolatilityRegime.EXTREME
            multiplier = 0.3

        # Realized vol (optional)
        realized_vol = _compute_realized_vol(price_history) if price_history else None

        self._log.info(
            f"[Thor] {symbol} | ATR%={atr_pct:.2%} regime={regime.value} "
            f"multiplier={multiplier:.1f}x realized_vol={realized_vol}"
        )

        return VolatilityData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            atr_pct=round(atr_pct, 6),
            volatility_regime=regime,
            suggested_position_size_multiplier=multiplier,
            realized_vol_7d=realized_vol,
            implied_vol=None,  # not available without options data
        )
