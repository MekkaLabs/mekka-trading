"""
src/strategies/range_trader.py
================================
RangeTrader — fade nos extremos de range consolidado.

Princípio: similar a MeanReversion mas MAIS conservador. Só opera
quando ADX confirma ausência de tendência (< 18) E a BB width está
estreita há vários candles (range estável). Toca extremos sem rompê-los
e visa o BB middle (não o extremo oposto). Holding curto, R:R ~1:1.

Filtros:
- ADX < 18 (sem tendência — mais rigoroso que MR padrão)
- BB width estreita persistente (consolidação real)
- Preço TOCANDO mas não rompendo a banda
- RSI em zona moderada de fade (25-40 long / 60-75 short)
- Volume NÃO elevado (vol elevado em range geralmente quebra)

Sinal:
- LONG quando: preço toca BB_lower sem fechar abaixo + RSI 25-40
- SHORT quando: preço toca BB_upper sem fechar acima + RSI 60-75
- HOLD em qualquer outra condição

Notas:
- target = bb_middle (volta à média)
- stop = 1.5 × ATR (dá espaço pra ruído mas não pra ruptura)
- max_leverage = 2 (range trading conservador)
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class RangeTraderStrategy(BaseStrategy):
    name = "RangeTrader"
    description = (
        "Conservative range fade: tap-not-break extremes back to mid, "
        "R:R ~1:1, low leverage"
    )

    max_position_size_pct = 0.015   # 1.5%
    max_leverage = 2                 # range trading com baixo leverage
    min_confidence_to_trade = 0.60

    target_atr_multiplier = 2.0     # fallback se bb_middle indisponível
    stop_atr_multiplier = 1.5       # SL razoável (1.5×ATR)

    # Thresholds
    adx_max = 18.0                   # ADX abaixo disso = sem trend
    bb_width_max = 0.05              # BB width "estreita" (5% do mid)
    # Tolerância de toque: preço entre [band, band±tolerance×ATR]
    touch_tolerance_atr = 0.25

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.92,            # ★★ habitat natural
            low_vol_trending=0.15,         # ruim (vai contra trend leve)
            high_vol_trending_up=0.05,     # péssimo
            high_vol_trending_down=0.05,
            high_vol_choppy=0.40,          # médio (vol pode quebrar range)
            breakout=0.05,                 # péssimo (vai contra a ruptura)
            funding_extreme=0.20,
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
        bb_middle = (
            self._bb_middle(chart)
            or getattr(chart, "bb_mid", None)
        )
        atr = self._atr(chart)
        close = self._close(chart)
        high = getattr(chart, "high", None)
        low = getattr(chart, "low", None)
        adx = getattr(chart, "adx", None)
        bb_width = getattr(chart, "bb_width", None)
        volume_elevated = self._volume_elevated(chart)

        if any(x is None for x in (rsi, bb_upper, bb_lower, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # Filtro crítico: SÓ opera sem trend
        if adx is None:
            return self._hold(context.symbol, "ADX missing — range needs no-trend confirmation")
        if adx >= self.adx_max:
            return self._hold(
                context.symbol,
                f"ADX {adx:.1f} >= {self.adx_max} (trend present)",
            )

        # Filtro: BB width estreita (range comprimido)
        # Calcula bb_width se não vier explícito
        if bb_width is None and bb_middle and bb_middle > 0:
            bb_width = (bb_upper - bb_lower) / bb_middle
        if bb_width is None:
            return self._hold(context.symbol, "bb_width unavailable")
        if bb_width > self.bb_width_max:
            return self._hold(
                context.symbol,
                f"BB width {bb_width:.4f} > {self.bb_width_max} "
                f"(range not tight enough)",
            )

        # Filtro: volume elevado em range é red flag (geralmente quebra)
        if volume_elevated:
            return self._hold(
                context.symbol,
                "volume elevated — range likely to break, not fade",
            )

        tolerance = self.touch_tolerance_atr * atr

        # LONG: preço TOCOU a banda inferior mas não fechou ABAIXO
        # Tap: low <= bb_lower OU close <= bb_lower + tolerance
        # No break: close > bb_lower (fechou dentro da banda)
        touched_lower = (
            (low is not None and low <= bb_lower)
            or close <= bb_lower + tolerance
        )
        not_broken_lower = close >= bb_lower  # não fechou abaixo

        if touched_lower and not_broken_lower and 25 <= rsi <= 40:
            target = (
                bb_middle if bb_middle
                else close + self.target_atr_multiplier * atr
            )
            confidence = self._calc_confidence(rsi, adx, bb_width, "long")
            return StrategySignal(
                strategy_name=self.name,
                symbol=context.symbol,
                action=StrategyAction.LONG,
                confidence=confidence,
                size_pct=self.max_position_size_pct,
                leverage=self.max_leverage,
                entry_price=close,
                stop_loss=close - self.stop_atr_multiplier * atr,
                take_profit=target,
                rationale=(
                    f"RANGE LONG: tap BB_lower {bb_lower:.2f} (close "
                    f"{close:.2f}), RSI {rsi:.1f} oversold-moderate, "
                    f"ADX {adx:.1f} < {self.adx_max}, BB width "
                    f"{bb_width:.4f} tight, target=mid {target:.2f}"
                ),
                metadata={
                    "rsi": rsi, "adx": adx, "atr": atr,
                    "bb_width": bb_width,
                    "bb_middle": bb_middle,
                    "touch": "lower",
                },
            )

        # SHORT: preço TOCOU a banda superior mas não fechou ACIMA
        touched_upper = (
            (high is not None and high >= bb_upper)
            or close >= bb_upper - tolerance
        )
        not_broken_upper = close <= bb_upper

        if touched_upper and not_broken_upper and 60 <= rsi <= 75:
            target = (
                bb_middle if bb_middle
                else close - self.target_atr_multiplier * atr
            )
            confidence = self._calc_confidence(rsi, adx, bb_width, "short")
            return StrategySignal(
                strategy_name=self.name,
                symbol=context.symbol,
                action=StrategyAction.SHORT,
                confidence=confidence,
                size_pct=self.max_position_size_pct,
                leverage=self.max_leverage,
                entry_price=close,
                stop_loss=close + self.stop_atr_multiplier * atr,
                take_profit=target,
                rationale=(
                    f"RANGE SHORT: tap BB_upper {bb_upper:.2f} (close "
                    f"{close:.2f}), RSI {rsi:.1f} overbought-moderate, "
                    f"ADX {adx:.1f} < {self.adx_max}, BB width "
                    f"{bb_width:.4f} tight, target=mid {target:.2f}"
                ),
                metadata={
                    "rsi": rsi, "adx": adx, "atr": atr,
                    "bb_width": bb_width,
                    "bb_middle": bb_middle,
                    "touch": "upper",
                },
            )

        return self._hold(context.symbol, "no range fade setup matched")

    def _calc_confidence(
        self, rsi: float, adx: float, bb_width: float, direction: str,
    ) -> float:
        """Confidence ~ quão limpo está o range + posição do RSI.

        - ADX mais baixo (mais longe de 18) = range mais estável
        - BB width mais estreita = consolidação mais clara
        - RSI no centro da zona de fade = sinal mais confiável
        """
        adx_score = min(1.0, max(0.0, (self.adx_max - adx) / self.adx_max))
        width_score = min(
            1.0, max(0.0, (self.bb_width_max - bb_width) / self.bb_width_max),
        )
        if direction == "long":
            # 25 → 1.0, 40 → 0.0 (preferir mais oversold)
            rsi_score = min(1.0, max(0.0, (40 - rsi) / 15))
        else:
            # 75 → 1.0, 60 → 0.0
            rsi_score = min(1.0, max(0.0, (rsi - 60) / 15))
        confidence = 0.60 + 0.15 * adx_score + 0.10 * width_score + 0.15 * rsi_score
        return min(0.95, max(0.60, confidence))
