"""
src/strategies/mean_reversion.py
==================================
Mean Reversion — opera extremos esperando volta à média.

Princípio: vence em mercado lateral (low_vol_range) onde preço
oscila entre níveis. Compra no fundo do range, vende no topo.
Holding curto-médio (horas), R:R 1:1.5.

Filtros:
- ADX < 20 (sem tendência)
- BB Width estreita (range comprimido)
- RSI < 30 ou > 70 (extremo)
- Volume normal (não vol spike — esses geralmente quebram o range)

Sinal:
- LONG quando: preço toca BB inferior + RSI < 30
- SHORT quando: preço toca BB superior + RSI > 70
- HOLD em qualquer outra condição
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class MeanReversionStrategy(BaseStrategy):
    name = "MeanReversion"
    description = "Buy bottoms / sell tops in ranging markets, R:R 1:1.5"

    max_position_size_pct = 0.015   # 1.5%
    max_leverage = 2                 # range trading com baixo leverage
    min_confidence_to_trade = 0.6

    target_atr_multiplier = 2.0     # TP em direção à média
    stop_atr_multiplier = 1.3       # SL além do extremo (caso quebre o range)

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.95,            # ★★ amor
            low_vol_trending=0.30,         # arriscado mas possível
            high_vol_trending_up=0.05,     # péssimo (vai contra)
            high_vol_trending_down=0.05,
            high_vol_choppy=0.45,          # médio (range mas com vol)
            breakout=0.05,                 # péssimo (vai contra)
            funding_extreme=0.50,
            unclear=0.0,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data")

        rsi = self._rsi(chart)
        bb_upper = getattr(chart, "bb_upper", None)
        bb_lower = getattr(chart, "bb_lower", None)
        bb_middle = self._bb_middle(chart)
        atr = self._atr(chart)
        close = self._close(chart)
        adx = getattr(chart, "adx", None)

        if any(x is None for x in (rsi, bb_upper, bb_lower, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # Filtro: NÃO operar mean reversion em tendência forte
        if adx is not None and adx > 25:
            return self._hold(
                context.symbol,
                f"ADX {adx:.1f} > 25 (trend present, MR risky)",
            )

        # LONG: preço próximo do BB inferior + RSI oversold
        if close <= bb_lower * 1.005 and rsi < 32:
            target = bb_middle if bb_middle else close + self.target_atr_multiplier * atr
            return StrategySignal(
                strategy_name=self.name,
                symbol=context.symbol,
                action=StrategyAction.LONG,
                confidence=self._calc_confidence(rsi, close, bb_lower, "long"),
                size_pct=self.max_position_size_pct,
                leverage=self.max_leverage,
                entry_price=close,
                stop_loss=close - self.stop_atr_multiplier * atr,
                take_profit=target,
                rationale=(
                    f"MR LONG: price {close:.2f} at/below BB_lower "
                    f"{bb_lower:.2f}, RSI {rsi:.1f} oversold, ADX "
                    f"{adx if adx else 'N/A'} no trend"
                ),
                metadata={"rsi": rsi, "adx": adx, "atr": atr},
            )

        # SHORT: preço próximo do BB superior + RSI overbought
        if close >= bb_upper * 0.995 and rsi > 68:
            target = bb_middle if bb_middle else close - self.target_atr_multiplier * atr
            return StrategySignal(
                strategy_name=self.name,
                symbol=context.symbol,
                action=StrategyAction.SHORT,
                confidence=self._calc_confidence(rsi, close, bb_upper, "short"),
                size_pct=self.max_position_size_pct,
                leverage=self.max_leverage,
                entry_price=close,
                stop_loss=close + self.stop_atr_multiplier * atr,
                take_profit=target,
                rationale=(
                    f"MR SHORT: price {close:.2f} at/above BB_upper "
                    f"{bb_upper:.2f}, RSI {rsi:.1f} overbought"
                ),
                metadata={"rsi": rsi, "adx": adx, "atr": atr},
            )

        return self._hold(context.symbol, "no MR extreme reached")

    def _calc_confidence(
        self, rsi: float, close: float, bb_extreme: float, direction: str,
    ) -> float:
        """Confidence ~ quão profundo no extremo está."""
        rsi_score = (
            min(1.0, (35 - rsi) / 10) if direction == "long"
            else min(1.0, (rsi - 65) / 10)
        )
        return min(0.95, 0.6 + 0.3 * max(0.0, rsi_score))
