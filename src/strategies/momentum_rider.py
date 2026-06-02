"""
src/strategies/momentum_rider.py
==================================
Momentum Rider — segue trends fortes com trailing stop.

Princípio: vence em mercado trending FORTE (ADX > 30) onde o momentum
persiste. Entra no momentum, sai com trailing stop que segue preço.
Holding horas-dias, R:R 1:5+ (deixa correr).

Filtros:
- ADX > 30 (tendência forte)
- ATR alto (movimento real, não micro-tendência)
- EMA9 > EMA21 > EMA50 (LONG) ou inverso (SHORT) — alinhamento total
- Volume crescente (acumulação/distribuição confirmada)

Sinal:
- LONG quando: alinhamento bullish + momentum building (RSI 55-70)
- SHORT quando: alinhamento bearish + momentum building (RSI 30-45)
- HOLD em range ou exaustão (RSI > 80 ou < 20)
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class MomentumRiderStrategy(BaseStrategy):
    name = "MomentumRider"
    description = "Ride strong trends with trailing stop, R:R 1:5+"

    max_position_size_pct = 0.03    # 3% — alta convicção
    max_leverage = 5
    min_confidence_to_trade = 0.7

    target_atr_multiplier = 5.0     # TP muito largo (deixa correr)
    stop_atr_multiplier = 1.5       # SL razoável

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.0,             # nunca
            low_vol_trending=0.40,         # ok mas vol baixa limita
            high_vol_trending_up=0.95,     # ★★ amor
            high_vol_trending_down=0.95,
            high_vol_choppy=0.10,          # péssimo (false trends)
            breakout=0.85,                 # ★ ótimo (entra na continuação)
            funding_extreme=0.55,
            unclear=0.0,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data")

        rsi = self._rsi(chart)
        ema9 = self._ema_short(chart)
        ema21 = self._ema_mid(chart)
        ema50 = getattr(chart, "ema_50", None)
        adx = getattr(chart, "adx", None)
        atr = self._atr(chart)
        close = self._close(chart)
        volume_elevated = self._volume_elevated(chart)

        if any(x is None for x in (rsi, ema9, ema21, ema50, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # FILTRO CRÍTICO: só opera com ADX claro
        if adx is None or adx < 28:
            return self._hold(
                context.symbol,
                f"ADX {adx if adx else 'N/A'} below 28 (trend not strong enough)",
            )

        # FILTRO: precisa de volume confirmando
        if not volume_elevated:
            return self._hold(context.symbol, "volume not elevated")

        # LONG: alinhamento bullish + momentum building (não exausto)
        if ema9 > ema21 > ema50 and 55 < rsi < 72:
            confidence = self._calc_confidence(rsi, adx, "long")
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
                    f"MOMENTUM LONG: full bullish alignment "
                    f"(EMA9 {ema9:.0f} > EMA21 {ema21:.0f} > EMA50 {ema50:.0f}), "
                    f"ADX {adx:.1f} strong, RSI {rsi:.1f} building, volume up"
                ),
                metadata={
                    "rsi": rsi, "adx": adx, "atr": atr,
                    "alignment": "bullish_full",
                },
            )

        # SHORT: alinhamento bearish + momentum building
        if ema9 < ema21 < ema50 and 28 < rsi < 45:
            confidence = self._calc_confidence(rsi, adx, "short")
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
                    f"MOMENTUM SHORT: full bearish alignment, "
                    f"ADX {adx:.1f} strong, RSI {rsi:.1f} building down"
                ),
                metadata={
                    "rsi": rsi, "adx": adx, "atr": atr,
                    "alignment": "bearish_full",
                },
            )

        return self._hold(context.symbol, "no momentum setup matched")

    def _calc_confidence(self, rsi: float, adx: float, direction: str) -> float:
        """Confidence ~ ADX + posição do RSI no range ideal."""
        adx_score = min(1.0, (adx - 28) / 22)  # 28→0, 50→1
        if direction == "long":
            rsi_score = min(1.0, (rsi - 55) / 12)  # 55→0, 67→1
        else:
            rsi_score = min(1.0, (45 - rsi) / 12)
        return min(0.95, 0.7 + 0.15 * adx_score + 0.15 * rsi_score)
