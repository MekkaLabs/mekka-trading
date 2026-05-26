"""
src/agents/spider_man.py
=========================
Spider-Man — Anomaly Detector

Scans for market irregularities that should pause or suppress trading.

Detections
----------
1. Flash crash      — price dropped > FLASH_CRASH_PCT in one candle
2. Volume spike     — current volume > VOLUME_SPIKE_X × 20-period MA
3. Extreme funding  — |funding_rate| > EXTREME_FUNDING_THRESHOLD per hour
4. BB squeeze break — price broke far outside Bollinger Bands (> 3σ proxy)
5. Agent divergence — Superman BULLISH + Black Panther DISTRIBUTION (or vice versa)
6. Extreme RSI      — RSI < 15 or RSI > 85 (potential exhaustion / anomaly)

Output
------
Returns `AnomalyReport` with:
  - anomalies_detected : list of human-readable descriptions
  - severity           : NONE / LOW / MEDIUM / HIGH
  - should_pause       : True if HIGH severity
  - details            : structured dict per check

Hard Rules
----------
- Never places orders
- Severity HIGH → should_pause is automatically True (enforced in model)
- Does NOT raise exceptions — returns a clean report even on partial failure
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.agents.base import BaseAgent
from src.models.market_data import (
    AnomalyReport,
    AnomalySeverity,
    MarketData,
    OnchainData,
    Trend,
    WhaleSignal,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
FLASH_CRASH_PCT = 0.05          # 5% drop in one candle
VOLUME_SPIKE_MULTIPLIER = 4.0   # 4× the 20-period volume MA
EXTREME_FUNDING_THRESHOLD = 0.003  # 0.3%/hr (very aggressive funding)
RSI_OVERSOLD_EXTREME = 15.0
RSI_OVERBOUGHT_EXTREME = 85.0
BB_BREAK_MARGIN = 0.005         # price > 0.5% outside the BB band


class SpiderMan(BaseAgent[AnomalyReport]):
    """
    Anomaly Detector — surface irregularities that warrant trading halt.

    Usage:
        report = await SpiderMan().run(
            symbol="BTC",
            market_data=md,
            onchain_data=oc,   # optional
        )
    """

    def __init__(self) -> None:
        super().__init__(
            "SpiderMan",
            "Anomaly Detector — market irregularities and divergences",
            timeout_s=15.0,  # Computação local sobre candles existentes
        )

    async def _run(  # type: ignore[override]
        self,
        symbol: str,
        market_data: MarketData,
        onchain_data: Optional[OnchainData] = None,
    ) -> AnomalyReport:
        """
        Run all anomaly checks.

        Parameters
        ----------
        symbol       : Asset symbol
        market_data  : Latest MarketData from Superman
        onchain_data : Optional OnchainData from Black Panther
        """
        anomalies: list[str] = []
        details: dict[str, object] = {}
        max_severity = AnomalySeverity.NONE

        def _bump(level: AnomalySeverity) -> None:
            nonlocal max_severity
            order = [
                AnomalySeverity.NONE,
                AnomalySeverity.LOW,
                AnomalySeverity.MEDIUM,
                AnomalySeverity.HIGH,
            ]
            if order.index(level) > order.index(max_severity):
                max_severity = level

        # ------------------------------------------------------------------
        # 1. Flash Crash
        # ------------------------------------------------------------------
        price = market_data.price
        if price > 0 and market_data.ema_20 is not None:
            # Approximate: if price is > FLASH_CRASH_PCT below ema_20
            drop_from_ema = (market_data.ema_20 - price) / market_data.ema_20
            if drop_from_ema > FLASH_CRASH_PCT:
                msg = (
                    f"Flash crash detected: price {price:,.2f} is "
                    f"{drop_from_ema:.1%} below EMA-20 ({market_data.ema_20:,.2f})"
                )
                anomalies.append(msg)
                details["flash_crash"] = {
                    "price": price,
                    "ema_20": market_data.ema_20,
                    "drop_pct": round(drop_from_ema, 4),
                }
                _bump(AnomalySeverity.HIGH)

        # ------------------------------------------------------------------
        # 2. Volume Spike
        # ------------------------------------------------------------------
        if market_data.volume is not None and market_data.volume_ma is not None:
            if market_data.volume_ma > 0:
                vol_mult = market_data.volume / market_data.volume_ma
                if vol_mult > VOLUME_SPIKE_MULTIPLIER:
                    msg = (
                        f"Volume spike: current volume is {vol_mult:.1f}× the 20-period MA"
                    )
                    anomalies.append(msg)
                    details["volume_spike"] = {
                        "volume": market_data.volume,
                        "volume_ma": market_data.volume_ma,
                        "multiplier": round(vol_mult, 2),
                    }
                    # Volume spike alone is LOW — can signal opportunity OR danger
                    _bump(AnomalySeverity.LOW)

        # ------------------------------------------------------------------
        # 3. Extreme Funding Rate
        # ------------------------------------------------------------------
        if onchain_data is not None and onchain_data.funding_rate is not None:
            fr = abs(onchain_data.funding_rate)
            if fr > EXTREME_FUNDING_THRESHOLD:
                direction = "long" if onchain_data.funding_rate > 0 else "short"
                msg = (
                    f"Extreme funding rate: {onchain_data.funding_rate:.4%}/hr "
                    f"({direction}s paying shorts)"
                )
                anomalies.append(msg)
                details["extreme_funding"] = {
                    "funding_rate": onchain_data.funding_rate,
                    "threshold": EXTREME_FUNDING_THRESHOLD,
                }
                _bump(AnomalySeverity.MEDIUM)

        # ------------------------------------------------------------------
        # 4. Bollinger Band Break (price outside bands)
        # ------------------------------------------------------------------
        if (
            market_data.bb_upper is not None
            and market_data.bb_lower is not None
            and market_data.bb_mid is not None
        ):
            if price > market_data.bb_upper * (1 + BB_BREAK_MARGIN):
                pct_above = (price - market_data.bb_upper) / market_data.bb_upper
                msg = f"Price {price:,.2f} broke {pct_above:.2%} above upper Bollinger Band"
                anomalies.append(msg)
                details["bb_break"] = {"direction": "above", "pct": round(pct_above, 4)}
                _bump(AnomalySeverity.LOW)

            elif price < market_data.bb_lower * (1 - BB_BREAK_MARGIN):
                pct_below = (market_data.bb_lower - price) / market_data.bb_lower
                msg = f"Price {price:,.2f} broke {pct_below:.2%} below lower Bollinger Band"
                anomalies.append(msg)
                details["bb_break"] = {"direction": "below", "pct": round(pct_below, 4)}
                _bump(AnomalySeverity.LOW)

        # ------------------------------------------------------------------
        # 5. Agent Divergence (Superman trend vs Black Panther whale signal)
        # ------------------------------------------------------------------
        if onchain_data is not None:
            trend = market_data.trend
            whale = onchain_data.signal

            bull_diverge = (
                trend == Trend.BULLISH
                and whale == WhaleSignal.DISTRIBUTION
                and market_data.trend_strength > 0.6
            )
            bear_diverge = (
                trend == Trend.BEARISH
                and whale == WhaleSignal.ACCUMULATION
                and market_data.trend_strength > 0.6
            )

            if bull_diverge or bear_diverge:
                direction = "BULLISH" if bull_diverge else "BEARISH"
                whale_dir = "DISTRIBUTION" if bull_diverge else "ACCUMULATION"
                msg = (
                    f"Agent divergence: Superman signals {direction} "
                    f"but Black Panther sees {whale_dir} — conflicting signals"
                )
                anomalies.append(msg)
                details["agent_divergence"] = {
                    "superman_trend": trend.value,
                    "black_panther_whale": whale.value,
                    "trend_strength": market_data.trend_strength,
                }
                _bump(AnomalySeverity.MEDIUM)

        # ------------------------------------------------------------------
        # 6. Extreme RSI
        # ------------------------------------------------------------------
        if market_data.rsi_14 is not None:
            rsi = market_data.rsi_14
            if rsi < RSI_OVERSOLD_EXTREME:
                msg = f"RSI-14 critically oversold: {rsi:.1f} (< {RSI_OVERSOLD_EXTREME})"
                anomalies.append(msg)
                details["extreme_rsi"] = {"rsi": rsi, "condition": "oversold"}
                _bump(AnomalySeverity.MEDIUM)
            elif rsi > RSI_OVERBOUGHT_EXTREME:
                msg = f"RSI-14 critically overbought: {rsi:.1f} (> {RSI_OVERBOUGHT_EXTREME})"
                anomalies.append(msg)
                details["extreme_rsi"] = {"rsi": rsi, "condition": "overbought"}
                _bump(AnomalySeverity.MEDIUM)

        # ------------------------------------------------------------------
        # Summary log
        # ------------------------------------------------------------------
        self._log.info(
            f"[SpiderMan] {symbol} | severity={max_severity.value} "
            f"anomalies={len(anomalies)} "
            + (f"→ {anomalies[0][:60]}..." if anomalies else "→ clean")
        )

        return AnomalyReport(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            anomalies_detected=anomalies,
            severity=max_severity,
            # should_pause is auto-set to True by model validator when severity=HIGH
            details=details if details else None,
        )
