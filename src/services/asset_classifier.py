"""
src/services/asset_classifier.py
===================================
Story 146 — Asset Classifier + Market Regime Detection.

Dois componentes:

1. `AssetClassifier` — classifica ativos por capitalização e comportamento:
   - LARGE_CAP:  BTC, ETH (>$100B market cap tier)
   - MID_CAP:    SOL, BNB, AVAX, ADA, DOT, LINK, UNI, MATIC (>$5B tier)
   - SMALL_CAP:  tudo mais
   - TRENDING:   tendência clara (EMA slope > threshold)
   - RANGING:    consolidação / baixa volatilidade

2. `MarketRegimeDetector` — detecta o regime global de mercado:
   - BULL:        BTC em uptrend, RSI médio > 60
   - BEAR:        BTC em downtrend, RSI médio < 40
   - SIDEWAYS:    BTC range-bound
   - VOLATILE:    ATR% acima do threshold (qualquer tendência)

Ambos são stateless — aceitam dados básicos e retornam classificações.
Sem I/O adicional — dados já disponíveis no MarketData.

Integração
----------
NickFury pode injetar a classificação no payload do audit log:
    classifier = AssetClassifier()
    cls = classifier.classify(symbol="SOL", price=150, ema20=140, atr_pct=0.04)
    regime = MarketRegimeDetector().detect(btc_trend="BULLISH", btc_rsi=65, btc_atr_pct=0.02)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CapTier(str, Enum):
    LARGE_CAP = "LARGE_CAP"
    MID_CAP = "MID_CAP"
    SMALL_CAP = "SMALL_CAP"


class TrendBehavior(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    UNKNOWN = "UNKNOWN"


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------

# Static tier lists — update as market caps evolve
_LARGE_CAP = frozenset({"BTC", "ETH"})
_MID_CAP = frozenset({
    "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "MATIC", "LINK",
    "UNI", "LTC", "BCH", "ATOM", "FIL", "APT", "ARB", "OP",
})


@dataclass
class AssetClassification:
    symbol: str
    cap_tier: CapTier
    trend_behavior: TrendBehavior
    momentum_pct: float       # abs(price - ema20) / ema20
    atr_pct: float            # ATR / price
    notes: list[str]

    def summary(self) -> str:
        return (
            f"[AssetClassifier] {self.symbol}: {self.cap_tier.value} / "
            f"{self.trend_behavior.value} "
            f"(momentum={self.momentum_pct:.2%} atr={self.atr_pct:.2%})"
        )

    def to_audit_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "cap_tier": self.cap_tier.value,
            "trend_behavior": self.trend_behavior.value,
            "momentum_pct": round(self.momentum_pct, 4),
            "atr_pct": round(self.atr_pct, 4),
        }


class AssetClassifier:
    """
    Classifica ativos por capitalização e comportamento de preço.

    Thresholds (configuráveis via parâmetros):
      trending_momentum_pct : distância mínima ao EMA20 para ser TRENDING (padrão 2%)
      ranging_atr_pct       : ATR% máximo para ser RANGING (padrão 1.5%)
    """

    def __init__(
        self,
        trending_momentum_pct: float = 0.02,   # 2% away from EMA20
        ranging_atr_max_pct: float = 0.015,    # ATR% < 1.5% = ranging
    ) -> None:
        self._trending_momentum_pct = trending_momentum_pct
        self._ranging_atr_max_pct = ranging_atr_max_pct

    def cap_tier(self, symbol: str) -> CapTier:
        """Classifica o ativo por capitalização de mercado."""
        sym = symbol.upper().replace("-USD", "").replace("/USD", "")
        if sym in _LARGE_CAP:
            return CapTier.LARGE_CAP
        if sym in _MID_CAP:
            return CapTier.MID_CAP
        return CapTier.SMALL_CAP

    def classify(
        self,
        symbol: str,
        price: float = 0.0,
        ema20: Optional[float] = None,
        atr_pct: Optional[float] = None,
    ) -> AssetClassification:
        """
        Classifica um ativo por capitalização e comportamento de preço.

        Parâmetros
        ----------
        symbol  : símbolo do ativo
        price   : preço atual
        ema20   : EMA 20 períodos (opcional)
        atr_pct : ATR% = ATR/price (opcional)
        """
        notes: list[str] = []
        atr = atr_pct or 0.0

        # EMA momentum
        momentum_pct = 0.0
        if price > 0 and ema20 is not None and ema20 > 0:
            momentum_pct = abs(price - ema20) / ema20

        # Trend behavior
        if atr_pct is not None and atr_pct < self._ranging_atr_max_pct:
            trend_behavior = TrendBehavior.RANGING
            notes.append(f"low_atr={atr_pct:.2%}<{self._ranging_atr_max_pct:.2%}")
        elif momentum_pct >= self._trending_momentum_pct:
            trend_behavior = TrendBehavior.TRENDING
            notes.append(f"ema_gap={momentum_pct:.2%}>={self._trending_momentum_pct:.2%}")
        elif ema20 is not None:
            trend_behavior = TrendBehavior.RANGING
            notes.append(f"weak_momentum={momentum_pct:.2%}")
        else:
            trend_behavior = TrendBehavior.UNKNOWN
            notes.append("no_ema_data")

        return AssetClassification(
            symbol=symbol.upper(),
            cap_tier=self.cap_tier(symbol),
            trend_behavior=trend_behavior,
            momentum_pct=round(momentum_pct, 4),
            atr_pct=round(atr, 4),
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Market Regime Detection
# ---------------------------------------------------------------------------

@dataclass
class RegimeReport:
    regime: MarketRegime
    btc_trend: str          # "BULLISH", "BEARISH", "NEUTRAL"
    btc_rsi: Optional[float]
    btc_atr_pct: Optional[float]
    confidence: float       # 0.0–1.0
    notes: list[str]

    def summary(self) -> str:
        return (
            f"[MarketRegime] {self.regime.value} "
            f"(btc_trend={self.btc_trend} rsi={self.btc_rsi or 'N/A':.1f} "
            f"atr={self.btc_atr_pct:.2%} confidence={self.confidence:.0%})"
            if self.btc_atr_pct is not None else
            f"[MarketRegime] {self.regime.value} (btc_trend={self.btc_trend})"
        )

    def to_audit_payload(self) -> dict:
        return {
            "regime": self.regime.value,
            "btc_trend": self.btc_trend,
            "btc_rsi": self.btc_rsi,
            "btc_atr_pct": round(self.btc_atr_pct, 4) if self.btc_atr_pct else None,
            "confidence": round(self.confidence, 2),
        }


class MarketRegimeDetector:
    """
    Detecta o regime global de mercado usando dados do BTC como proxy.

    BTC é usado como proxy do mercado cripto porque:
    - Correlação > 0.8 com a maioria das altcoins
    - Dados sempre disponíveis
    - Moves do BTC explicam 60-80% das moves das altcoins em mercados normais

    Lógica de detecção:
    1. Se ATR% > volatile_atr_threshold → VOLATILE (independente da tendência)
    2. Else se trend BULLISH e RSI > bull_rsi_min → BULL
    3. Else se trend BEARISH e RSI < bear_rsi_max → BEAR
    4. Else → SIDEWAYS
    """

    def __init__(
        self,
        volatile_atr_threshold: float = 0.04,   # ATR% > 4% = VOLATILE
        bull_rsi_min: float = 55.0,              # RSI > 55 confirma BULL
        bear_rsi_max: float = 45.0,              # RSI < 45 confirma BEAR
    ) -> None:
        self._volatile_atr = volatile_atr_threshold
        self._bull_rsi_min = bull_rsi_min
        self._bear_rsi_max = bear_rsi_max

    def detect(
        self,
        btc_trend: str = "NEUTRAL",
        btc_rsi: Optional[float] = None,
        btc_atr_pct: Optional[float] = None,
    ) -> RegimeReport:
        """
        Detecta o regime de mercado.

        Parâmetros
        ----------
        btc_trend   : "BULLISH", "BEARISH", ou "NEUTRAL"
        btc_rsi     : RSI 14 do BTC (0–100)
        btc_atr_pct : ATR% do BTC (ATR/price)
        """
        notes: list[str] = []
        trend = (btc_trend or "NEUTRAL").upper()

        # Rule 1: Extreme volatility overrides trend direction
        if btc_atr_pct is not None and btc_atr_pct > self._volatile_atr:
            notes.append(f"high_atr={btc_atr_pct:.2%}>{self._volatile_atr:.2%}")
            return RegimeReport(
                regime=MarketRegime.VOLATILE,
                btc_trend=trend,
                btc_rsi=btc_rsi,
                btc_atr_pct=btc_atr_pct,
                confidence=min((btc_atr_pct - self._volatile_atr) / 0.04 + 0.5, 1.0),
                notes=notes,
            )

        # Rule 2: BULL
        if trend == "BULLISH":
            rsi_confirms = btc_rsi is None or btc_rsi > self._bull_rsi_min
            confidence = 0.7 if btc_rsi is None else min((btc_rsi - 50) / 30 + 0.5, 1.0)
            if rsi_confirms:
                notes.append(f"bullish_trend rsi={btc_rsi or 'N/A'}")
                return RegimeReport(
                    regime=MarketRegime.BULL,
                    btc_trend=trend,
                    btc_rsi=btc_rsi,
                    btc_atr_pct=btc_atr_pct,
                    confidence=round(confidence, 2),
                    notes=notes,
                )

        # Rule 3: BEAR
        if trend == "BEARISH":
            rsi_confirms = btc_rsi is None or btc_rsi < self._bear_rsi_max
            confidence = 0.7 if btc_rsi is None else min((50 - btc_rsi) / 30 + 0.5, 1.0)
            if rsi_confirms:
                notes.append(f"bearish_trend rsi={btc_rsi or 'N/A'}")
                return RegimeReport(
                    regime=MarketRegime.BEAR,
                    btc_trend=trend,
                    btc_rsi=btc_rsi,
                    btc_atr_pct=btc_atr_pct,
                    confidence=round(confidence, 2),
                    notes=notes,
                )

        # Rule 4: SIDEWAYS (default)
        notes.append(f"no_strong_signal trend={trend} rsi={btc_rsi or 'N/A'}")
        return RegimeReport(
            regime=MarketRegime.SIDEWAYS,
            btc_trend=trend,
            btc_rsi=btc_rsi,
            btc_atr_pct=btc_atr_pct,
            confidence=0.5,
            notes=notes,
        )
