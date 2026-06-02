"""
tests/test_strategy_selector.py
=================================
Cobertura do StrategySelector e PerformanceTracker.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from src.strategies.base import MarketRegime


# ---------------------------------------------------------------------------
# StrategySelector (uses available_strategies from registry)
# ---------------------------------------------------------------------------


class TestStrategySelector:
    @pytest.mark.asyncio
    async def test_selects_scalp_for_high_vol_choppy(self):
        from src.services.strategy_selector import select_strategies
        from src.strategies.registry import get_all_strategies
        strats = get_all_strategies()
        allocs = await select_strategies(
            regime=MarketRegime.HIGH_VOL_CHOPPY,
            regime_confidence=0.85,
            available_strategies=strats,
            symbol="BTC",
            max_strategies=3,
        )
        names = [a.strategy_name for a in allocs]
        assert "Scalp" in names or "ScalpAggressive" in names

    @pytest.mark.asyncio
    async def test_selects_mr_for_low_vol_range(self):
        from src.services.strategy_selector import select_strategies
        from src.strategies.registry import get_all_strategies
        strats = get_all_strategies()
        allocs = await select_strategies(
            regime=MarketRegime.LOW_VOL_RANGE,
            regime_confidence=0.85,
            available_strategies=strats,
            symbol="BTC",
            max_strategies=3,
        )
        names = [a.strategy_name for a in allocs]
        assert "MeanReversion" in names or "RangeTrader" in names

    @pytest.mark.asyncio
    async def test_selects_funding_arb_for_funding_extreme(self):
        from src.services.strategy_selector import select_strategies
        from src.strategies.registry import get_all_strategies
        strats = get_all_strategies()
        allocs = await select_strategies(
            regime=MarketRegime.FUNDING_EXTREME,
            regime_confidence=0.85,
            available_strategies=strats,
            symbol="BTC",
            max_strategies=3,
        )
        # FundingArbitrage tem fitness 0.95 pra esse regime; outras 0.10
        names = [a.strategy_name for a in allocs]
        assert "FundingArbitrage" in names

    @pytest.mark.asyncio
    async def test_allocations_sum_to_1(self):
        from src.services.strategy_selector import select_strategies
        from src.strategies.registry import get_all_strategies
        strats = get_all_strategies()
        allocs = await select_strategies(
            regime=MarketRegime.HIGH_VOL_TRENDING_UP,
            regime_confidence=0.85,
            available_strategies=strats,
            symbol="BTC",
            max_strategies=3,
        )
        if allocs:
            total = sum(a.allocated_pct for a in allocs)
            assert abs(total - 1.0) < 0.01, f"sum = {total}"

    @pytest.mark.asyncio
    async def test_empty_for_unclear(self):
        from src.services.strategy_selector import select_strategies
        from src.strategies.registry import get_all_strategies
        strats = get_all_strategies()
        allocs = await select_strategies(
            regime=MarketRegime.UNCLEAR,
            regime_confidence=0.0,
            available_strategies=strats,
            symbol="BTC",
            max_strategies=3,
        )
        # Nenhuma estratégia tem fitness > 0 pra UNCLEAR
        assert allocs == []


# ---------------------------------------------------------------------------
# StrategyPerformanceTracker (uses real DB)
# ---------------------------------------------------------------------------


class TestPerformanceTracker:
    @pytest.mark.asyncio
    async def test_record_trade_aggregates(self):
        from src.services.strategy_performance_tracker import (
            record_trade_outcome, get_performance,
        )
        # Usa nome único pra não conflitar com outros tests
        strat = "TestStratAgg"
        now = datetime.now(timezone.utc)
        await record_trade_outcome(
            strategy_name=strat, regime="high_vol_choppy",
            symbol="TEST", pnl_usd=10.0, pnl_pct=0.01,
            won=True, timestamp=now,
        )
        await record_trade_outcome(
            strategy_name=strat, regime="high_vol_choppy",
            symbol="TEST", pnl_usd=-5.0, pnl_pct=-0.005,
            won=False, timestamp=now,
        )
        perf = await get_performance(strat, regime="high_vol_choppy", symbol="TEST")
        assert perf is not None
        assert perf.n_trades == 2
        assert perf.n_wins == 1
        assert abs(perf.total_pnl_usd - 5.0) < 0.01

    @pytest.mark.asyncio
    async def test_get_performance_none_for_missing(self):
        from src.services.strategy_performance_tracker import get_performance
        perf = await get_performance(
            "NonExistentStrategy_XYZ", regime="unclear", symbol="ZZZ"
        )
        # Pode retornar None ou empty agg
        assert perf is None or perf.n_trades == 0


# ---------------------------------------------------------------------------
# Be Water Orchestrator integration
# ---------------------------------------------------------------------------


class TestBeWaterE2E:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_mock_analysis(self):
        """E2E: regime → selector → strategy → signal"""
        from src.services.be_water_orchestrator import decide
        from dataclasses import dataclass

        @dataclass
        class _Chart:
            atr = 1500.0
            close = 73000.0
            adx = 32.0
            ema_50 = 72500.0
            ema_200 = 70000.0
            rsi = 60.0
            ema_9 = 73100.0
            ema_21 = 72900.0
            volume_elevated = True
            bb_upper = 74500.0
            bb_lower = 71500.0
            bb_middle = 73000.0

        @dataclass
        class _Onchain:
            funding_rate = 0.0001

        @dataclass
        class _Analysis:
            chart: object = None
            onchain: object = None

        analysis = _Analysis(chart=_Chart(), onchain=_Onchain())

        decision = await decide(
            symbol="BTC", analysis=analysis, equity_usd=10000.0,
        )

        # Mostra que pipeline rodou completo
        assert decision.regime.regime != MarketRegime.UNCLEAR
        assert decision.regime.regime in (
            MarketRegime.HIGH_VOL_TRENDING_UP,
        )
        # Vai ter Swing ou Momentum atuando nesse regime
        if not decision.flat:
            assert len(decision.signals) > 0
            top = decision.top_signal()
            assert top is not None
            assert top.action.value in ("LONG", "SHORT")
