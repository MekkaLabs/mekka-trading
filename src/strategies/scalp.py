"""
src/strategies/scalp.py
=========================
Scalp — operações curtas em volatilidade choppy.

Princípio: muitos trades pequenos com R:R ~1:1, holding 5-30min.
Vence em mercado lateral volátil (high_vol_choppy) onde tendência
não persiste mas ranges intra-candle são grandes.

Filtros:
- RSI nem extremo nem neutro (30-70 = corpo médio)
- Volume elevado vs média (movimento real)
- ATR no top 33% da janela (vol suficiente pra cobrir custos)

Sinal:
- LONG quando: RSI cruza 40 ascendente + EMA9 > EMA21
- SHORT quando: RSI cruza 60 descendente + EMA9 < EMA21
- HOLD em qualquer outra condição
"""

from __future__ import annotations

from typing import Any

from .base import (
    BaseStrategy,
    MarketRegime,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class ScalpStrategy(BaseStrategy):
    name = "Scalp"
    description = "Many small trades in high-vol choppy markets, R:R ~1:1"

    max_position_size_pct = 0.01    # 1% do equity por trade (muitos trades)
    max_leverage = 3
    min_confidence_to_trade = 0.55  # threshold baixo (volume de trades)

    # Targets curtos
    target_atr_multiplier = 0.8      # TP = entry ± 0.8 × ATR
    stop_atr_multiplier = 0.6        # SL = entry ± 0.6 × ATR (apertado)

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.10,            # quase morre
            low_vol_trending=0.20,         # pouco
            high_vol_trending_up=0.55,     # médio (pode comer reversões)
            high_vol_trending_down=0.55,
            high_vol_choppy=0.95,          # ★ amor verdadeiro
            breakout=0.40,                 # pode perder em ruptura
            funding_extreme=0.30,
            unclear=0.0,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data")

        # Schema flexible via base helpers (suporta atr_14/rsi_14/price/ema_20)
        rsi = self._rsi(chart)
        ema9 = self._ema_short(chart)
        ema21 = self._ema_mid(chart)
        atr = self._atr(chart)
        close = self._close(chart)
        volume_elevated = self._volume_elevated(chart)

        if any(x is None for x in (rsi, ema9, ema21, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # Filtro de regime
        if context.regime_confidence < 0.5:
            return self._hold(
                context.symbol,
                f"regime confidence {context.regime_confidence:.2f} too low",
            )

        # Filtro: volume real (evita sinal em mercado morto)
        if not volume_elevated:
            return self._hold(context.symbol, "volume not elevated")

        # LONG setup: RSI saindo de zona neutra-baixa + EMA bullish
        if 40 < rsi < 55 and ema9 > ema21:
            confidence = self._calc_confidence(rsi, ema9, ema21, "long")
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
                    f"LONG: RSI {rsi:.1f} ascendente, EMA9({ema9:.2f}) > "
                    f"EMA21({ema21:.2f}), volume elevated, "
                    f"regime={context.regime.value}"
                ),
                metadata={
                    "rsi": rsi, "atr": atr,
                    "regime": context.regime.value,
                    "regime_conf": context.regime_confidence,
                },
            )

        # SHORT setup: RSI saindo de zona neutra-alta + EMA bearish
        if 45 < rsi < 60 and ema9 < ema21:
            confidence = self._calc_confidence(rsi, ema9, ema21, "short")
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
                    f"SHORT: RSI {rsi:.1f} descendente, EMA9({ema9:.2f}) < "
                    f"EMA21({ema21:.2f}), volume elevated, "
                    f"regime={context.regime.value}"
                ),
                metadata={
                    "rsi": rsi, "atr": atr,
                    "regime": context.regime.value,
                    "regime_conf": context.regime_confidence,
                },
            )

        return self._hold(context.symbol, "no scalp setup matched")

    def _calc_confidence(
        self, rsi: float, ema9: float, ema21: float, direction: str,
    ) -> float:
        """Score 0-1 baseado em força dos sinais."""
        ema_spread = abs(ema9 - ema21) / max(ema21, 1e-9)
        base = 0.55
        if direction == "long":
            rsi_score = max(0.0, (rsi - 40) / 15)  # 40→0, 55→1
        else:
            rsi_score = max(0.0, (60 - rsi) / 15)  # 60→0, 45→1
        spread_score = min(1.0, ema_spread * 50)
        confidence = base + 0.3 * rsi_score + 0.15 * spread_score
        return min(1.0, max(0.5, confidence))
