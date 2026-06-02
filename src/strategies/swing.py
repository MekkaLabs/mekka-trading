"""
src/strategies/swing.py
=========================
Swing — segue tendência média de dias.

Princípio: poucos trades de alta convicção, R:R 1:3 ou melhor,
holding 1-7 dias. Vence em mercado trending claro (high_vol_trending
+ low_vol_trending) onde tendência persiste.

Filtros:
- ADX > 25 (tendência presente)
- EMA50 > EMA200 (bullish) OU EMA50 < EMA200 (bearish)
- Pullback: preço retornou pra EMA21 (entrada na continuação)

Sinal:
- LONG quando: EMA50 > EMA200 + pullback bullish concluído (RSI 40-55)
- SHORT quando: EMA50 < EMA200 + rally bearish concluído (RSI 45-60)
- HOLD em range, vol baixa sem direção, ou drawdown atual aberto
"""

from __future__ import annotations

from .base import (
    BaseStrategy,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


class SwingStrategy(BaseStrategy):
    name = "Swing"
    description = "Trend-following, R:R 1:3, holding days, fewer trades"

    max_position_size_pct = 0.025   # 2.5% (poucos trades, vale mais por trade)
    max_leverage = 5
    min_confidence_to_trade = 0.65

    # Targets largos
    target_atr_multiplier = 3.0     # TP = entry ± 3 × ATR
    stop_atr_multiplier = 1.0       # SL = entry ± 1 × ATR (R:R 1:3)

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(
            low_vol_range=0.05,            # péssimo (preso no range)
            low_vol_trending=0.85,         # ★ ótimo
            high_vol_trending_up=0.95,     # ★★ amor
            high_vol_trending_down=0.95,
            high_vol_choppy=0.15,          # ruim (false trends)
            breakout=0.65,                 # bom (pegar continuação)
            funding_extreme=0.40,
            unclear=0.0,
        )

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        analysis = context.analysis
        chart = getattr(analysis, "chart", None)
        if chart is None:
            return self._hold(context.symbol, "no chart data")

        rsi = self._rsi(chart)
        ema21 = self._ema_mid(chart)
        ema50 = getattr(chart, "ema_50", None)
        ema200 = self._ema_long(chart)
        adx = getattr(chart, "adx", None)
        atr = self._atr(chart)
        close = self._close(chart)

        if any(x is None for x in (rsi, ema21, ema50, ema200, atr, close)):
            return self._hold(context.symbol, "missing indicators")

        # ADX é opcional mas preferível — sem ele degrada confidence
        adx_ok = adx is None or adx >= 22

        # Bull regime: EMA50 > EMA200
        if ema50 > ema200:
            # Pullback bullish: RSI 40-55 (não overbought)
            if 40 <= rsi <= 55:
                # Confirmation: preço perto da EMA21 (não muito acima)
                if close <= ema21 * 1.02:  # até 2% acima
                    confidence = 0.65 + (0.2 if adx_ok else 0.0)
                    return StrategySignal(
                        strategy_name=self.name,
                        symbol=context.symbol,
                        action=StrategyAction.LONG,
                        confidence=min(0.95, confidence),
                        size_pct=self.max_position_size_pct,
                        leverage=self.max_leverage,
                        entry_price=close,
                        stop_loss=close - self.stop_atr_multiplier * atr,
                        take_profit=close + self.target_atr_multiplier * atr,
                        rationale=(
                            f"SWING LONG: bull trend (EMA50 {ema50:.0f} > "
                            f"EMA200 {ema200:.0f}), pullback completo "
                            f"(RSI {rsi:.1f}), entry near EMA21 {ema21:.0f}, "
                            f"ADX {adx if adx else 'N/A'}"
                        ),
                        metadata={"adx": adx, "atr": atr},
                    )

        # Bear regime: EMA50 < EMA200
        if ema50 < ema200:
            # Rally bearish: RSI 45-60
            if 45 <= rsi <= 60:
                if close >= ema21 * 0.98:
                    confidence = 0.65 + (0.2 if adx_ok else 0.0)
                    return StrategySignal(
                        strategy_name=self.name,
                        symbol=context.symbol,
                        action=StrategyAction.SHORT,
                        confidence=min(0.95, confidence),
                        size_pct=self.max_position_size_pct,
                        leverage=self.max_leverage,
                        entry_price=close,
                        stop_loss=close + self.stop_atr_multiplier * atr,
                        take_profit=close - self.target_atr_multiplier * atr,
                        rationale=(
                            f"SWING SHORT: bear trend (EMA50 {ema50:.0f} < "
                            f"EMA200 {ema200:.0f}), rally completo "
                            f"(RSI {rsi:.1f}), entry near EMA21"
                        ),
                        metadata={"adx": adx, "atr": atr},
                    )

        return self._hold(context.symbol, "no swing setup matched")
