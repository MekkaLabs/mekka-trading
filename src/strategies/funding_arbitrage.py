"""
src/strategies/funding_arbitrage.py
=====================================
FundingArbitrage — captura funding rate extremos.

Princípio: em perpétuos, funding rate transfere caixa entre longs e
shorts a cada intervalo (8h tipicamente). Quando o funding está muito
positivo (longs pagando shorts), abrir SHORT captura o funding como
yield. Quando muito negativo (shorts pagando longs), abrir LONG. O
trade NÃO depende de movimento direcional grande — o objetivo é
embolsar funding com hedge implícito pequeno.

Filtros:
- analysis.onchain.funding_rate disponível (lido do Black Panther)
- |funding_rate| >= threshold (0.06% por candle / período)
- ATR disponível pra stop dinâmico
- Spider-Man sem flash crash em curso (analysis.is_safe_to_trade)

Sinal:
- SHORT quando: funding > +0.0006 (longs estão pagando — captamos)
- LONG quando: funding < -0.0006 (shorts estão pagando — captamos)
- HOLD em qualquer outra condição

Notas:
- target = 0.5 × ATR (pequeno — não dependemos de direcional, só funding)
- stop = 1.5 × ATR (largo — aguenta volatilidade enquanto coleta funding)
- max_leverage = 3 (aumenta yield em funding sem expor demais)
- confidence baseado em |funding_rate| vs threshold
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class FundingArbitrageStrategy(BaseStrategy):
    name = "FundingArbitrage"
    description = (
        "Capture extreme perp funding rates: short positive funding / "
        "long negative funding, target small, hold for funding payment"
    )

    max_position_size_pct = 0.025   # 2.5%
    max_leverage = 3
    min_confidence_to_trade = 0.6

    # Stop / target em ATR
    target_atr_multiplier = 0.5      # TP pequeno (não é trade direcional)
    stop_atr_multiplier = 1.5        # SL razoavelmente largo

    # Thresholds de funding rate (por período de funding, tipicamente 8h)
    funding_threshold = 0.0006       # 0.06% — sinal mínimo
    funding_strong = 0.0015          # 0.15% — sinal forte (high confidence)

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.10,
            low_vol_trending=0.10,
            high_vol_trending_up=0.10,
            high_vol_trending_down=0.10,
            high_vol_choppy=0.10,
            breakout=0.10,
            funding_extreme=0.95,         # ★★ habitat exclusivo
            unclear=0.10,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis

        # Safe-to-trade check (Spider-Man anomalies bloqueiam o trade)
        is_safe = getattr(analysis, "is_safe_to_trade", True)
        if not is_safe:
            return self._hold(
                context.symbol,
                "analysis.is_safe_to_trade=False (anomaly/extreme vol)",
            )

        # Lê funding do onchain (Black Panther)
        onchain = getattr(analysis, "onchain", None)
        if onchain is None:
            return self._hold(
                context.symbol, "no onchain data (funding unavailable)",
            )

        funding_rate = getattr(onchain, "funding_rate", None)
        if funding_rate is None:
            return self._hold(
                context.symbol, "funding_rate missing from onchain data",
            )

        # Lê chart pra stop/target em ATR
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data for ATR sizing")

        atr = self._atr(chart)
        close = self._close(chart)
        if atr is None or close is None:
            return self._hold(context.symbol, "missing ATR/close for sizing")

        abs_funding = abs(funding_rate)

        # Filtro: funding precisa ser EXTREMO
        if abs_funding < self.funding_threshold:
            return self._hold(
                context.symbol,
                f"funding {funding_rate:+.4%} below threshold "
                f"±{self.funding_threshold:.2%}",
            )

        confidence = self._calc_confidence(abs_funding)

        # SHORT: funding POSITIVO (longs pagam shorts — capturamos como short)
        if funding_rate > 0:
            return StrategySignal(
                strategy_name=self.name,
                symbol=context.symbol,
                action=StrategyAction.SHORT,
                confidence=confidence,
                size_pct=self.max_position_size_pct,
                leverage=self.max_leverage,
                entry_price=close,
                stop_loss=close + self.stop_atr_multiplier * atr,
                take_profit=close - self.target_atr_multiplier * atr,
                rationale=(
                    f"FUND-ARB SHORT: funding {funding_rate:+.4%} positive "
                    f"(longs paying), capturing yield via short. "
                    f"ATR={atr:.4f}, target=-0.5×ATR, stop=+1.5×ATR, "
                    f"lev={self.max_leverage}x"
                ),
                metadata={
                    "funding_rate": funding_rate,
                    "abs_funding": abs_funding,
                    "funding_direction": "positive",
                    "atr": atr,
                    "regime": context.regime.value,
                },
            )

        # LONG: funding NEGATIVO (shorts pagam longs — capturamos como long)
        return StrategySignal(
            strategy_name=self.name,
            symbol=context.symbol,
            action=StrategyAction.LONG,
            confidence=confidence,
            size_pct=self.max_position_size_pct,
            leverage=self.max_leverage,
            entry_price=close,
            stop_loss=close - self.stop_atr_multiplier * atr,
            take_profit=close + self.target_atr_multiplier * atr,
            rationale=(
                f"FUND-ARB LONG: funding {funding_rate:+.4%} negative "
                f"(shorts paying), capturing yield via long. "
                f"ATR={atr:.4f}, target=+0.5×ATR, stop=-1.5×ATR, "
                f"lev={self.max_leverage}x"
            ),
            metadata={
                "funding_rate": funding_rate,
                "abs_funding": abs_funding,
                "funding_direction": "negative",
                "atr": atr,
                "regime": context.regime.value,
            },
        )

    def _calc_confidence(self, abs_funding: float) -> float:
        """Confidence proporcional ao |funding_rate|.

        - threshold (0.06%): confidence base ~0.60
        - strong (0.15%): confidence ~0.85
        - >> strong: cap em 0.95
        """
        if abs_funding <= self.funding_threshold:
            return 0.60
        # Linear interpolation entre threshold e strong
        if abs_funding >= self.funding_strong:
            # Extra boost além do strong, até cap
            extra = min(
                0.10,
                (abs_funding - self.funding_strong) / self.funding_strong * 0.10,
            )
            return min(0.95, 0.85 + extra)
        # Entre threshold e strong: 0.60 → 0.85
        span = self.funding_strong - self.funding_threshold
        progress = (abs_funding - self.funding_threshold) / max(span, 1e-9)
        return min(0.85, max(0.60, 0.60 + 0.25 * progress))
