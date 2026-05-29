"""
src/strategies/breakout.py
============================
Breakout — opera ruptura de range com confirmação de volume.

Princípio: ranges comprimidos (BB squeeze) acumulam energia. Quando
o preço rompe o BB superior/inferior COM volume e ATR subindo, há
alta probabilidade de continuação direcional. R:R 1:4 (target 4×ATR,
stop 1×ATR) — premia poucos winners grandes.

Filtros:
- BB squeeze recente: BB width estreita em candles anteriores
- ATR atual >= ATR anterior (volatilidade expandindo)
- Volume elevado vs média (rompimento real, não wick falso)
- Preço fechando acima/abaixo da banda (não só tocando)

Sinal:
- LONG quando: close > bb_upper + volume_elevated + ATR expandindo
- SHORT quando: close < bb_lower + volume_elevated + ATR expandindo
- HOLD em qualquer outra condição

Notas:
- target 4×ATR / stop 1×ATR — R:R 1:4
- max_leverage = 4 (rupturas têm whipsaw risk)
- Lê chart.atr_prev (se disponível) para confirmar expansão; fail-silent
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class BreakoutStrategy(BaseStrategy):
    name = "Breakout"
    description = (
        "Range breakout with volume + ATR confirmation, R:R 1:4, "
        "fewer trades but high payoff"
    )

    max_position_size_pct = 0.02    # 2%
    max_leverage = 4
    min_confidence_to_trade = 0.65

    # Targets largos (R:R 1:4)
    target_atr_multiplier = 4.0     # TP = entry ± 4 × ATR
    stop_atr_multiplier = 1.0       # SL = entry ± 1 × ATR

    # Heurística pra detectar squeeze prévio (BB width abaixo deste % do mid)
    squeeze_bb_width_pct = 0.04     # 4% — band tight
    # Margem mínima do close em relação à banda rompida (em % do close)
    breakout_margin_pct = 0.001     # 0.1%

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.30,            # ok (esperando squeeze quebrar)
            low_vol_trending=0.30,
            high_vol_trending_up=0.70,     # bom (continuação de trend)
            high_vol_trending_down=0.70,
            high_vol_choppy=0.20,          # ruim (false breakouts)
            breakout=0.95,                 # ★★ habitat natural
            funding_extreme=0.30,
            unclear=0.0,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data")

        bb_upper = getattr(chart, "bb_upper", None)
        bb_lower = getattr(chart, "bb_lower", None)
        bb_middle = (
            self._bb_middle(chart)
            or getattr(chart, "bb_mid", None)
        )
        atr = self._atr(chart)
        atr_prev = getattr(chart, "atr_prev", None)   # opcional
        close = self._close(chart)
        volume_elevated = self._volume_elevated(chart)
        # bb_width_prev é opcional — se disponível, valida squeeze prévio
        bb_width_prev = getattr(chart, "bb_width_prev", None)

        if any(x is None for x in (bb_upper, bb_lower, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # Filtro: volume real (rupturas falsas raramente vêm com volume)
        if not volume_elevated:
            return self._hold(context.symbol, "volume not elevated")

        # Filtro: ATR expandindo (se atr_prev disponível)
        if atr_prev is not None and atr < atr_prev:
            return self._hold(
                context.symbol,
                f"ATR not expanding ({atr:.4f} < prev {atr_prev:.4f})",
            )

        # Filtro: squeeze prévio (se bb_width_prev disponível)
        squeeze_confirmed = True
        if bb_width_prev is not None and bb_middle:
            squeeze_confirmed = bb_width_prev <= self.squeeze_bb_width_pct
            if not squeeze_confirmed:
                return self._hold(
                    context.symbol,
                    f"no prior BB squeeze (bb_width_prev "
                    f"{bb_width_prev:.4f} > threshold "
                    f"{self.squeeze_bb_width_pct})",
                )

        margin = close * self.breakout_margin_pct

        # LONG: close acima da banda superior (com margem mínima)
        if close > bb_upper + margin:
            confidence = self._calc_confidence(
                close, bb_upper, atr, atr_prev, "long",
            )
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
                    f"BREAKOUT LONG: close {close:.2f} > BB_upper "
                    f"{bb_upper:.2f}, ATR {atr:.4f}"
                    + (f" (prev {atr_prev:.4f})" if atr_prev else "")
                    + f", volume elevated, "
                    f"squeeze={'confirmed' if squeeze_confirmed else 'unknown'}"
                ),
                metadata={
                    "bb_upper": bb_upper, "atr": atr, "atr_prev": atr_prev,
                    "bb_width_prev": bb_width_prev,
                    "squeeze_confirmed": squeeze_confirmed,
                    "direction": "upper_break",
                },
            )

        # SHORT: close abaixo da banda inferior
        if close < bb_lower - margin:
            confidence = self._calc_confidence(
                close, bb_lower, atr, atr_prev, "short",
            )
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
                    f"BREAKOUT SHORT: close {close:.2f} < BB_lower "
                    f"{bb_lower:.2f}, ATR {atr:.4f}"
                    + (f" (prev {atr_prev:.4f})" if atr_prev else "")
                    + f", volume elevated, "
                    f"squeeze={'confirmed' if squeeze_confirmed else 'unknown'}"
                ),
                metadata={
                    "bb_lower": bb_lower, "atr": atr, "atr_prev": atr_prev,
                    "bb_width_prev": bb_width_prev,
                    "squeeze_confirmed": squeeze_confirmed,
                    "direction": "lower_break",
                },
            )

        return self._hold(context.symbol, "no breakout setup matched")

    def _calc_confidence(
        self,
        close: float,
        bb_extreme: float,
        atr: float,
        atr_prev: float | None,
        direction: str,
    ) -> float:
        """Confidence ~ distância do rompimento + expansão do ATR.

        - Quão longe rompeu a banda (em ATRs) — sinal mais forte se rompeu mais.
        - Quão rápido o ATR está expandindo vs anterior.
        - Squeeze confirmado adiciona base.
        """
        # Distância em ATR
        if direction == "long":
            distance = close - bb_extreme
        else:
            distance = bb_extreme - close
        dist_score = min(1.0, max(0.0, distance / max(atr, 1e-9)))

        # Expansão do ATR
        if atr_prev and atr_prev > 0:
            expansion = (atr - atr_prev) / atr_prev
            expansion_score = min(1.0, max(0.0, expansion * 4))  # 25% → 1.0
        else:
            expansion_score = 0.5  # neutro se sem dado

        base = 0.65
        confidence = base + 0.20 * dist_score + 0.10 * expansion_score
        return min(0.95, max(0.65, confidence))
