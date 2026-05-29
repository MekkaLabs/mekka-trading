"""
src/strategies/scalp_aggressive.py
====================================
ScalpAggressive — variante turbinada do Scalp para vol choppy extrema.

Princípio: mesma família do Scalp (muitos trades, holding muito curto),
mas leverage maior (5-8x), targets mais apertados (0.5×ATR) e stops
mais curtos (0.4×ATR). Mantém R:R ~1.25:1 mas com tickets MENORES por
trade (max_position_size_pct=0.005). Vence quando high_vol_choppy é o
regime dominante e a confiança do RegimeDetector está muito alta.

Filtros:
- RSI em zona de gatilho (40-55 long / 45-60 short) — saída de neutro
- Volume elevado vs média (movimento real)
- Regime confidence > 0.6 (mais exigente que Scalp normal)
- EMA9/EMA21 com alinhamento claro

Sinal:
- LONG quando: RSI 40-55 ascendente + EMA9 > EMA21 + volume confirmando
- SHORT quando: RSI 45-60 descendente + EMA9 < EMA21 + volume confirmando
- HOLD em qualquer outra condição

Notas:
- min_confidence_to_trade=0.65 (vs 0.55 do Scalp) — só atira em sinal forte
- Em breakout pode sofrer mais, mas regime_fitness reflete isso
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class ScalpAggressiveStrategy(BaseStrategy):
    name = "ScalpAggressive"
    description = (
        "High-leverage scalp variant for extreme high-vol choppy regimes, "
        "tighter targets/stops, smaller tickets"
    )

    max_position_size_pct = 0.005   # 0.5% por trade (menor — leverage compensa)
    max_leverage = 8                 # 5-8x
    min_confidence_to_trade = 0.65  # mais exigente que Scalp

    # Targets MAIS curtos que o Scalp
    target_atr_multiplier = 0.5      # TP = entry ± 0.5 × ATR
    stop_atr_multiplier = 0.4        # SL = entry ± 0.4 × ATR (R:R ~1.25:1)

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.05,            # péssimo (sem range pra capturar)
            low_vol_trending=0.10,
            high_vol_trending_up=0.40,     # médio-baixo (preferimos Swing)
            high_vol_trending_down=0.40,
            high_vol_choppy=0.98,          # ★★ habitat natural
            breakout=0.50,                 # razoável mas arriscado
            funding_extreme=0.20,
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
        atr = self._atr(chart)
        close = self._close(chart)
        volume_elevated = self._volume_elevated(chart)

        if any(x is None for x in (rsi, ema9, ema21, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # Filtro de regime — mais rigoroso que Scalp (0.6 vs 0.5)
        if context.regime_confidence < 0.6:
            return self._hold(
                context.symbol,
                f"regime confidence {context.regime_confidence:.2f} too low "
                f"for aggressive scalp",
            )

        # Filtro: volume real
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
                    f"AGG-SCALP LONG: RSI {rsi:.1f} ascendente, "
                    f"EMA9({ema9:.2f}) > EMA21({ema21:.2f}), volume elevated, "
                    f"regime={context.regime.value} "
                    f"(conf={context.regime_confidence:.2f}), "
                    f"lev={self.max_leverage}x"
                ),
                metadata={
                    "rsi": rsi, "atr": atr,
                    "regime": context.regime.value,
                    "regime_conf": context.regime_confidence,
                    "variant": "aggressive",
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
                    f"AGG-SCALP SHORT: RSI {rsi:.1f} descendente, "
                    f"EMA9({ema9:.2f}) < EMA21({ema21:.2f}), volume elevated, "
                    f"regime={context.regime.value} "
                    f"(conf={context.regime_confidence:.2f}), "
                    f"lev={self.max_leverage}x"
                ),
                metadata={
                    "rsi": rsi, "atr": atr,
                    "regime": context.regime.value,
                    "regime_conf": context.regime_confidence,
                    "variant": "aggressive",
                },
            )

        return self._hold(context.symbol, "no aggressive scalp setup matched")

    def _calc_confidence(
        self, rsi: float, ema9: float, ema21: float, direction: str,
    ) -> float:
        """Score 0-1 baseado em força dos sinais.

        Base mais alta que o Scalp normal (0.65) porque min_confidence_to_trade
        também subiu. Spread EMA tem peso maior — sinal alavancado precisa
        de alinhamento mais forte.
        """
        ema_spread = abs(ema9 - ema21) / max(ema21, 1e-9)
        base = 0.65
        if direction == "long":
            rsi_score = max(0.0, (rsi - 40) / 15)   # 40→0, 55→1
        else:
            rsi_score = max(0.0, (60 - rsi) / 15)   # 60→0, 45→1
        spread_score = min(1.0, ema_spread * 50)
        confidence = base + 0.20 * rsi_score + 0.15 * spread_score
        return min(1.0, max(0.65, confidence))
