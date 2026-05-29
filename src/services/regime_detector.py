"""
src/services/regime_detector.py
=================================
RegimeDetector — "sente" o regime atual do mercado.

Analisa indicadores do MarketAnalysis (ATR, ADX, BB width, EMAs) e
mapeia para um dos 7 regimes canônicos definidos em
``src/strategies/base.py:MarketRegime``.

Output: ``DetectedRegime`` com label + confidence (0-1) + features
brutas pra audit.

Princípios:
- READ-ONLY do MarketAnalysis
- DETERMINÍSTICO: dado o mesmo input, mesmo output
- FAIL-SILENT: dados ausentes → UNCLEAR com confidence=0
- EXPLICÁVEL: features brutas guardadas no output

Heurísticas (calibrar com backtests):
- ATR alto    = ATR / close > 0.015  (1.5% intra-candle)
- ATR baixo   = ATR / close < 0.008
- ADX alto    = > 25
- BB squeeze  = BB width / close < 0.02
- Funding ext = abs(funding) > 0.0005 (0.05%)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from src.strategies.base import MarketRegime


@dataclass
class DetectedRegime:
    """Output do RegimeDetector."""
    regime: MarketRegime
    confidence: float           # 0-1
    rationale: str
    features: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "features": self.features,
            "detected_at": self.detected_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Thresholds (mutáveis para backtest tuning)
# ---------------------------------------------------------------------------

THRESHOLD_ATR_HIGH_PCT = 0.015          # 1.5% intra-candle = high vol
THRESHOLD_ATR_LOW_PCT = 0.008           # 0.8% intra-candle = low vol
THRESHOLD_ADX_TRENDING = 25.0
THRESHOLD_ADX_STRONG_TRENDING = 30.0
THRESHOLD_BB_SQUEEZE_PCT = 0.020        # BB width < 2% do close = squeeze
THRESHOLD_FUNDING_EXTREME = 0.0005      # 0.05% por 8h = funding extreme


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def detect_regime(analysis: Any) -> DetectedRegime:
    """
    Analisa MarketAnalysis e retorna DetectedRegime.

    Args:
        analysis: MarketAnalysis (ou dict-like). Lê: chart.atr, chart.close,
            chart.adx, chart.bb_upper/lower, chart.ema_50/200, onchain.funding_rate.

    Returns:
        DetectedRegime. Em caso de dados insuficientes, regime=UNCLEAR
        com confidence=0.
    """
    try:
        chart = getattr(analysis, "chart", None) or {}
        if not chart:
            return DetectedRegime(
                regime=MarketRegime.UNCLEAR,
                confidence=0.0,
                rationale="no chart data",
            )

        # Schema flexible: real MarketData uses atr_14/rsi_14/price/ema_20
        # but our mock tests use atr/rsi/close/ema_21. Suportar ambos.
        atr = _g(chart, "atr") or _g(chart, "atr_14")
        close = _g(chart, "close") or _g(chart, "price")
        adx = _g(chart, "adx")
        bb_upper = _g(chart, "bb_upper")
        bb_lower = _g(chart, "bb_lower")
        ema50 = _g(chart, "ema_50")
        ema200 = _g(chart, "ema_200")
        # Fallback: se não tem ema_200, usa ema_50 + trend_strength sinaliza direção
        trend = _g_str(chart, "trend")  # "BULLISH"/"BEARISH"/"NEUTRAL"

        # Funding rate via onchain (optional)
        funding = None
        onchain = getattr(analysis, "onchain", None)
        if onchain is not None:
            funding = _g(onchain, "funding_rate")

        # Compute derived
        atr_pct = _safe_div(atr, close)
        bb_width_pct = (
            _safe_div(
                (bb_upper - bb_lower) if (bb_upper is not None and bb_lower is not None) else None,
                close,
            )
        )

        features = {
            "atr": atr, "close": close, "adx": adx,
            "atr_pct": atr_pct, "bb_width_pct": bb_width_pct,
            "ema50": ema50, "ema200": ema200,
            "funding_rate": funding,
        }

        # Quick fallback if too much missing
        if atr_pct is None and adx is None:
            return DetectedRegime(
                regime=MarketRegime.UNCLEAR,
                confidence=0.0,
                rationale="missing atr+adx",
                features=features,
            )

        # 1. Funding extreme — overrides outros porque é trade independente
        if funding is not None and abs(funding) > THRESHOLD_FUNDING_EXTREME:
            return DetectedRegime(
                regime=MarketRegime.FUNDING_EXTREME,
                confidence=min(1.0, abs(funding) / (THRESHOLD_FUNDING_EXTREME * 4)),
                rationale=f"funding rate {funding:+.5f} > threshold",
                features=features,
            )

        # 2. Breakout — BB squeeze ainda + ATR começou a crescer
        # (simplification: detect via low BB width but rising ATR — TODO real)
        if bb_width_pct is not None and bb_width_pct < THRESHOLD_BB_SQUEEZE_PCT \
                and atr_pct is not None and atr_pct > THRESHOLD_ATR_HIGH_PCT:
            return DetectedRegime(
                regime=MarketRegime.BREAKOUT,
                confidence=0.7,
                rationale=(
                    f"BB squeeze ({bb_width_pct:.3%}) with rising ATR "
                    f"({atr_pct:.3%})"
                ),
                features=features,
            )

        # Determine trend direction:
        # - prefer ema50 vs ema200 if both present
        # - fallback to chart.trend (BULLISH/BEARISH/NEUTRAL) from Superman
        trend_dir = "NEUTRAL"
        if ema50 and ema200:
            trend_dir = "BULLISH" if ema50 > ema200 else "BEARISH"
        elif trend:
            if "BULL" in trend or "UP" in trend:
                trend_dir = "BULLISH"
            elif "BEAR" in trend or "DOWN" in trend:
                trend_dir = "BEARISH"
        features["trend_direction"] = trend_dir

        # ADX é opcional. Quando ausente, usamos trend_strength como proxy.
        trend_strength = _g(chart, "trend_strength")  # Superman: 0-1
        if adx is None and trend_strength is not None:
            # trend_strength 0.7 → ADX 25 equivalent; 0.9 → 35
            adx = trend_strength * 35  # cheap mapping
            features["adx_inferred"] = True

        # 3. High vol categorização
        if atr_pct is not None and atr_pct >= THRESHOLD_ATR_HIGH_PCT:
            # High vol → trending up/down/choppy
            if adx is not None and adx >= THRESHOLD_ADX_STRONG_TRENDING \
                    and trend_dir != "NEUTRAL":
                regime_label = (
                    MarketRegime.HIGH_VOL_TRENDING_UP if trend_dir == "BULLISH"
                    else MarketRegime.HIGH_VOL_TRENDING_DOWN
                )
                return DetectedRegime(
                    regime=regime_label,
                    confidence=_normalize_conf(adx, atr_pct),
                    rationale=(
                        f"high vol ({atr_pct:.3%}) + ADX {adx:.1f} + "
                        f"{trend_dir}"
                    ),
                    features=features,
                )
            # High vol mas sem trend claro = choppy
            return DetectedRegime(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                confidence=0.75,
                rationale=f"high vol ({atr_pct:.3%}) without strong ADX",
                features=features,
            )

        # 4. Low vol
        if atr_pct is not None and atr_pct <= THRESHOLD_ATR_LOW_PCT:
            if adx is not None and adx >= THRESHOLD_ADX_TRENDING \
                    and trend_dir != "NEUTRAL":
                return DetectedRegime(
                    regime=MarketRegime.LOW_VOL_TRENDING,
                    confidence=0.7,
                    rationale=f"low vol ({atr_pct:.3%}) + ADX {adx:.1f} + {trend_dir}",
                    features=features,
                )
            return DetectedRegime(
                regime=MarketRegime.LOW_VOL_RANGE,
                confidence=0.8,
                rationale=f"low vol ({atr_pct:.3%}), no trend",
                features=features,
            )

        # 5. Mid vol — uncategorized but tradeable. Treat as mild choppy.
        if atr_pct is not None:
            return DetectedRegime(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                confidence=0.4,
                rationale=f"mid vol ({atr_pct:.3%}) — defaulting to choppy",
                features=features,
            )

        return DetectedRegime(
            regime=MarketRegime.UNCLEAR,
            confidence=0.0,
            rationale="insufficient signal",
            features=features,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[regime_detector] fail: {exc}")
        return DetectedRegime(
            regime=MarketRegime.UNCLEAR,
            confidence=0.0,
            rationale=f"detector exception: {exc}",
        )


def _g(obj: Any, attr: str) -> Optional[float]:
    """Get attr or dict key as float. None se ausente/inválido."""
    val = None
    if hasattr(obj, attr):
        val = getattr(obj, attr)
    elif isinstance(obj, dict):
        val = obj.get(attr)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _g_str(obj: Any, attr: str) -> Optional[str]:
    """Get attr/dict key as string. Handles Enum."""
    val = None
    if hasattr(obj, attr):
        val = getattr(obj, attr)
    elif isinstance(obj, dict):
        val = obj.get(attr)
    if val is None:
        return None
    if hasattr(val, "value"):  # Enum
        val = val.value
    return str(val).upper()


def _normalize_conf(adx: float, atr_pct: float) -> float:
    """Quanto mais forte ADX + maior ATR, mais confidence."""
    adx_n = min(1.0, max(0.0, (adx - 25) / 25))    # 25→0, 50→1
    atr_n = min(1.0, max(0.0, (atr_pct - 0.01) / 0.02))  # 1%→0, 3%→1
    return round(min(0.95, 0.6 + 0.2 * adx_n + 0.15 * atr_n), 3)
