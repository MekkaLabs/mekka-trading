"""
tests/test_be_water_core.py
=============================
Cobertura do core do Be Water Framework:
- BaseStrategy contract
- RegimeDetector
- Be Water Orchestrator pipeline
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from src.services.regime_detector import (
    DetectedRegime,
    detect_regime,
)
from src.strategies.base import (
    BaseStrategy,
    MarketRegime,
    RegimeFitness,
    StrategyAction,
    StrategyContext,
    StrategySignal,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@dataclass
class _MockChart:
    """Mock minimal pra MarketAnalysis.chart."""
    atr: float = 1500.0
    close: float = 73000.0
    adx: float = 28.0
    bb_upper: float = 74500.0
    bb_lower: float = 71500.0
    bb_middle: float = 73000.0
    ema_9: float = 72900.0
    ema_21: float = 72700.0
    ema_50: float = 72500.0
    ema_200: float = 70000.0
    rsi: float = 55.0
    volume_elevated: bool = True


@dataclass
class _MockOnchain:
    funding_rate: float = 0.0001


@dataclass
class _MockAnalysis:
    chart: _MockChart
    onchain: _MockOnchain = None

    def __post_init__(self):
        if self.onchain is None:
            self.onchain = _MockOnchain()


# ---------------------------------------------------------------------------
# RegimeDetector
# ---------------------------------------------------------------------------


class TestRegimeDetector:
    def test_unclear_when_no_chart(self):
        result = detect_regime(_MockAnalysis(chart=None))
        assert result.regime == MarketRegime.UNCLEAR
        assert result.confidence == 0.0

    def test_high_vol_trending_up_with_adx(self):
        chart = _MockChart(
            atr=1500.0, close=73000.0, adx=35.0,
            ema_50=72500.0, ema_200=70000.0,  # bullish
        )
        result = detect_regime(_MockAnalysis(chart=chart))
        assert result.regime == MarketRegime.HIGH_VOL_TRENDING_UP
        assert result.confidence > 0.5

    def test_high_vol_trending_down(self):
        chart = _MockChart(
            atr=1500.0, close=73000.0, adx=35.0,
            ema_50=71000.0, ema_200=73000.0,  # bearish
        )
        result = detect_regime(_MockAnalysis(chart=chart))
        assert result.regime == MarketRegime.HIGH_VOL_TRENDING_DOWN

    def test_high_vol_choppy_low_adx(self):
        chart = _MockChart(
            atr=1500.0, close=73000.0, adx=15.0,
        )
        result = detect_regime(_MockAnalysis(chart=chart))
        assert result.regime == MarketRegime.HIGH_VOL_CHOPPY

    def test_low_vol_range(self):
        chart = _MockChart(
            atr=400.0, close=73000.0, adx=15.0,
        )
        result = detect_regime(_MockAnalysis(chart=chart))
        assert result.regime == MarketRegime.LOW_VOL_RANGE

    def test_low_vol_trending(self):
        chart = _MockChart(
            atr=400.0, close=73000.0, adx=28.0,
        )
        result = detect_regime(_MockAnalysis(chart=chart))
        assert result.regime == MarketRegime.LOW_VOL_TRENDING

    def test_funding_extreme_overrides(self):
        chart = _MockChart(atr=1500.0, close=73000.0, adx=15.0)
        analysis = _MockAnalysis(chart=chart, onchain=_MockOnchain(funding_rate=0.0008))
        result = detect_regime(analysis)
        assert result.regime == MarketRegime.FUNDING_EXTREME

    def test_features_preserved(self):
        chart = _MockChart()
        result = detect_regime(_MockAnalysis(chart=chart))
        assert "atr_pct" in result.features
        assert result.features["close"] == 73000.0

    def test_fail_silent_on_exception(self):
        # Analysis sem atributos esperados → UNCLEAR sem raise
        result = detect_regime(object())
        assert result.regime == MarketRegime.UNCLEAR
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# RegimeFitness
# ---------------------------------------------------------------------------


class TestRegimeFitness:
    def test_score_clamps_above_1(self):
        f = RegimeFitness(high_vol_choppy=1.5)
        assert f.score(MarketRegime.HIGH_VOL_CHOPPY) == 1.0

    def test_score_clamps_below_0(self):
        f = RegimeFitness(low_vol_range=-0.3)
        assert f.score(MarketRegime.LOW_VOL_RANGE) == 0.0

    def test_unknown_regime_returns_0(self):
        f = RegimeFitness(high_vol_choppy=0.8)
        # UNCLEAR sem valor declarado → 0.0
        assert f.score(MarketRegime.UNCLEAR) == 0.0


# ---------------------------------------------------------------------------
# BaseStrategy contract
# ---------------------------------------------------------------------------


class _TestStrategy(BaseStrategy):
    """Implementação minimal pra testar contract."""
    name = "TestStrategy"
    description = "Test fixture"

    def regime_fitness(self) -> RegimeFitness:
        return RegimeFitness(high_vol_choppy=0.9, low_vol_range=0.1)

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        # Sempre LONG com alta confidence pra testar caps
        return StrategySignal(
            strategy_name=self.name,
            symbol=context.symbol,
            action=StrategyAction.LONG,
            confidence=0.85,
            size_pct=0.05,  # acima do max_position_size_pct default 0.02
            leverage=10,    # acima do max_leverage default 3
            entry_price=73000,
            stop_loss=72000,
            take_profit=75000,
            rationale="test",
        )


class TestBaseStrategy:
    def test_fitness_for_smoke(self):
        s = _TestStrategy()
        assert s.fitness_for(MarketRegime.HIGH_VOL_CHOPPY) == 0.9
        assert s.fitness_for(MarketRegime.LOW_VOL_RANGE) == 0.1

    def test_fitness_for_unknown(self):
        s = _TestStrategy()
        assert s.fitness_for(MarketRegime.FUNDING_EXTREME) == 0.0

    def test_safe_signal_caps_size(self):
        s = _TestStrategy()
        ctx = StrategyContext(
            symbol="BTC", analysis=_MockAnalysis(chart=_MockChart()),
            regime=MarketRegime.HIGH_VOL_CHOPPY, regime_confidence=0.8,
            allocated_usd=1000.0, current_equity_usd=10000.0,
        )
        sig = s.safe_signal(ctx)
        # Size capped at max_position_size_pct (default 0.02)
        assert sig.size_pct == s.max_position_size_pct
        assert sig.metadata.get("size_capped") is True
        # Leverage capped at max_leverage (default 3)
        assert sig.leverage == s.max_leverage
        assert sig.metadata.get("leverage_capped") is True

    def test_safe_signal_fail_silent(self):
        class _Broken(BaseStrategy):
            name = "Broken"
            def regime_fitness(self): return RegimeFitness()
            def generate_signal(self, ctx): raise RuntimeError("boom")
        s = _Broken()
        ctx = StrategyContext(
            symbol="BTC", analysis=_MockAnalysis(chart=_MockChart()),
            regime=MarketRegime.HIGH_VOL_CHOPPY, regime_confidence=0.8,
            allocated_usd=1000.0, current_equity_usd=10000.0,
        )
        sig = s.safe_signal(ctx)
        assert sig.action == StrategyAction.HOLD
        assert "boom" in sig.rationale

    def test_low_confidence_downgrades_to_hold(self):
        class _LowConf(BaseStrategy):
            name = "LowConf"
            min_confidence_to_trade = 0.7
            def regime_fitness(self): return RegimeFitness()
            def generate_signal(self, ctx):
                return StrategySignal(
                    strategy_name=self.name, symbol=ctx.symbol,
                    action=StrategyAction.LONG, confidence=0.5,
                )
        s = _LowConf()
        ctx = StrategyContext(
            symbol="BTC", analysis=_MockAnalysis(chart=_MockChart()),
            regime=MarketRegime.HIGH_VOL_CHOPPY, regime_confidence=0.8,
            allocated_usd=1000.0, current_equity_usd=10000.0,
        )
        sig = s.safe_signal(ctx)
        assert sig.action == StrategyAction.HOLD


# ---------------------------------------------------------------------------
# Strategies smoke (import + instantiate + fitness no-crash)
# ---------------------------------------------------------------------------


class TestStrategiesSmoke:
    @pytest.mark.parametrize("strategy_cls_name", [
        ("src.strategies.scalp", "ScalpStrategy"),
        ("src.strategies.swing", "SwingStrategy"),
        ("src.strategies.mean_reversion", "MeanReversionStrategy"),
        ("src.strategies.momentum_rider", "MomentumRiderStrategy"),
    ])
    def test_strategy_instantiable_and_has_fitness(self, strategy_cls_name):
        module_name, cls_name = strategy_cls_name
        import importlib
        mod = importlib.import_module(module_name)
        cls = getattr(mod, cls_name)
        s = cls()
        assert s.name == cls_name.replace("Strategy", "")
        fitness = s.regime_fitness()
        assert isinstance(fitness, RegimeFitness)
        # Pelo menos UM regime deve ter score > 0.5
        scores = [
            fitness.score(r) for r in MarketRegime
            if r != MarketRegime.UNCLEAR
        ]
        assert max(scores) >= 0.5, (
            f"{cls_name} should have at least one regime with fitness >= 0.5"
        )

    def test_strategies_have_distinct_fitness_profiles(self):
        """Estratégias devem ter perfis DISTINTOS de regime fitness —
        senão são redundantes."""
        from src.strategies.scalp import ScalpStrategy
        from src.strategies.swing import SwingStrategy
        from src.strategies.mean_reversion import MeanReversionStrategy
        from src.strategies.momentum_rider import MomentumRiderStrategy
        instances = [
            ScalpStrategy(), SwingStrategy(),
            MeanReversionStrategy(), MomentumRiderStrategy(),
        ]
        # Pra cada par, fitness deve diferir em pelo menos 1 regime
        for i in range(len(instances)):
            for j in range(i + 1, len(instances)):
                a = instances[i].regime_fitness()
                b = instances[j].regime_fitness()
                diff = sum(
                    abs(a.score(r) - b.score(r))
                    for r in MarketRegime
                )
                assert diff > 0.5, (
                    f"{instances[i].name} and {instances[j].name} are too similar"
                )


# ---------------------------------------------------------------------------
# Be Water Orchestrator (smoke — no DB)
# ---------------------------------------------------------------------------


class TestBeWaterOrchestrator:
    @pytest.mark.asyncio
    async def test_decide_flat_when_unclear(self):
        from src.services.be_water_orchestrator import decide
        # Mock analysis sem chart → unclear
        decision = await decide(
            symbol="BTC", analysis=object(), equity_usd=10000.0,
        )
        assert decision.flat is True
        assert decision.regime.regime == MarketRegime.UNCLEAR

    @pytest.mark.asyncio
    async def test_decide_with_fallback_selection(self):
        from src.services.be_water_orchestrator import decide
        # Quando o registry/selector falham, deve usar fallback
        # Mock analysis com high vol + trend up
        chart = _MockChart(adx=35.0, ema_50=72500.0, ema_200=70000.0)
        decision = await decide(
            symbol="BTC",
            analysis=_MockAnalysis(chart=chart),
            equity_usd=10000.0,
            available_strategies=[_TestStrategy()],
        )
        # TestStrategy tem high_vol_choppy=0.9 mas HIGH_VOL_TRENDING_UP=0.0
        # → fallback não seleciona (fitness < 0.5 pra esse regime)
        # → flat
        assert decision.flat is True
