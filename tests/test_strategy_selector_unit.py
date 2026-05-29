"""
tests/test_strategy_selector_unit.py
=====================================
Unit tests for the Be Water Framework StrategySelector — isolated from
the strategies registry and real DB.

Mocks ``get_performance`` so we can assert exact combined_score math,
allocation normalization, and resilience to upstream failures without
depending on the strategy registry composition or running trades.

Coverage
--------
- Filters strategies with fitness < FITNESS_FLOOR
- Combines fitness + historical score (weighted blend)
- Falls back to fitness * NO_HISTORY_PENALTY when no history
- Returns [] (FLAT) when no strategy beats min_combined_score
- Top N by combined_score, normalized allocations sum to 1.0
- Handles empty strategy list defensively
- Handles failing perf lookups defensively
- Handles a strategy whose regime_fitness raises
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import AsyncMock, patch as _patch

import pytest

from src.services.strategy_performance_tracker import StrategyPerformanceSummary
from src.services.strategy_selector import (
    FITNESS_WEIGHT,
    HISTORY_WEIGHT,
    NO_HISTORY_PENALTY,
    select_strategies,
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
# Fake strategies — minimal BaseStrategy subclasses for selector tests
# ---------------------------------------------------------------------------


class _FakeStrategy(BaseStrategy):
    """Strategy with configurable name + fitness map."""

    def __init__(self, name: str, fitness: RegimeFitness) -> None:
        self.name = name
        self._fitness = fitness
        super().__init__()

    def regime_fitness(self) -> RegimeFitness:
        return self._fitness

    def generate_signal(self, context: StrategyContext) -> StrategySignal:
        return StrategySignal(
            strategy_name=self.name,
            symbol=context.symbol,
            action=StrategyAction.HOLD,
            confidence=0.0,
        )


def _summary(
    n_trades: int = 0,
    sharpe: Optional[float] = None,
    win_rate_target: float = 0.5,
    strategy_name: str = "X",
) -> StrategyPerformanceSummary:
    n_wins = int(round(n_trades * win_rate_target))
    n_losses = n_trades - n_wins
    return StrategyPerformanceSummary(
        strategy_name=strategy_name,
        regime="high_vol_choppy",
        symbol="BTC",
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        sharpe_ratio=sharpe,
        total_pnl_usd=100.0 if n_trades else 0.0,
        avg_win_pnl=20.0,
        avg_loss_pnl=-10.0,
    )


# ---------------------------------------------------------------------------
# Filter / floor
# ---------------------------------------------------------------------------


class TestFitnessFloor:
    async def test_strategies_below_floor_excluded(self):
        low_fit = _FakeStrategy(
            "LowUnit", RegimeFitness(high_vol_choppy=0.2)
        )
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(return_value=_summary(strategy_name="LowUnit")),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.8,
                available_strategies=[low_fit],
                symbol="BTC",
            )
        assert result == []

    async def test_empty_strategy_list_returns_flat(self):
        result = await select_strategies(
            regime=MarketRegime.HIGH_VOL_CHOPPY,
            regime_confidence=0.9,
            available_strategies=[],
            symbol="BTC",
        )
        assert result == []


# ---------------------------------------------------------------------------
# No history → fitness penalty
# ---------------------------------------------------------------------------


class TestNoHistoryPenalty:
    async def test_no_trades_applies_no_history_penalty(self):
        strat = _FakeStrategy("FreshUnit", RegimeFitness(high_vol_choppy=0.9))
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(
                return_value=_summary(n_trades=0, strategy_name="FreshUnit")
            ),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.7,
                available_strategies=[strat],
                symbol="BTC",
                min_combined_score=0.1,
            )
        assert len(result) == 1
        a = result[0]
        assert a.has_history is False
        assert a.combined_score == pytest.approx(0.9 * NO_HISTORY_PENALTY)


# ---------------------------------------------------------------------------
# With history → weighted blend
# ---------------------------------------------------------------------------


class TestWeightedBlend:
    async def test_combined_score_uses_fitness_and_history_weights(self):
        strat = _FakeStrategy("MixedUnit", RegimeFitness(high_vol_choppy=0.8))
        # Sharpe=2 → historical_score saturates at 1.0
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(
                return_value=_summary(
                    n_trades=30, sharpe=2.0, win_rate_target=0.7,
                    strategy_name="MixedUnit",
                )
            ),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.6,
                available_strategies=[strat],
                symbol="BTC",
                min_combined_score=0.1,
            )
        assert len(result) == 1
        a = result[0]
        assert a.has_history is True
        assert a.fitness_score == pytest.approx(0.8)
        assert a.combined_score == pytest.approx(
            FITNESS_WEIGHT * 0.8 + HISTORY_WEIGHT * 1.0
        )

    async def test_negative_sharpe_lowers_historical_score(self):
        strat = _FakeStrategy("BadUnit", RegimeFitness(high_vol_choppy=0.9))
        # Sharpe=-2 → historical_score = 0.5 - 0.5 = 0.0
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(
                return_value=_summary(
                    n_trades=20, sharpe=-2.0, strategy_name="BadUnit",
                )
            ),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.5,
                available_strategies=[strat],
                symbol="BTC",
                min_combined_score=0.1,
            )
        assert len(result) == 1
        assert result[0].combined_score == pytest.approx(FITNESS_WEIGHT * 0.9)


# ---------------------------------------------------------------------------
# Threshold + Top N + normalization
# ---------------------------------------------------------------------------


class TestThresholdAndAllocation:
    async def test_below_min_combined_returns_flat(self):
        strat = _FakeStrategy("MidUnit", RegimeFitness(high_vol_choppy=0.4))
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(
                return_value=_summary(n_trades=20, sharpe=0.0, strategy_name="MidUnit")
            ),
        ):
            # combined = 0.4 * 0.4 + 0.6 * 0.5 = 0.46 < 0.5
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.6,
                available_strategies=[strat],
                symbol="BTC",
                min_combined_score=0.5,
            )
        assert result == []

    async def test_top_n_and_normalization(self):
        sa = _FakeStrategy("AUnit", RegimeFitness(high_vol_choppy=0.9))
        sb = _FakeStrategy("BUnit", RegimeFitness(high_vol_choppy=0.8))
        sc = _FakeStrategy("CUnit", RegimeFitness(high_vol_choppy=0.7))
        sd = _FakeStrategy("DUnit", RegimeFitness(high_vol_choppy=0.6))

        async def fake_perf(strategy_name, regime, symbol, window_days=30):
            mapping = {
                "AUnit": _summary(n_trades=30, sharpe=2.0, strategy_name="AUnit"),
                "BUnit": _summary(n_trades=30, sharpe=1.0, strategy_name="BUnit"),
                "CUnit": _summary(n_trades=30, sharpe=0.5, strategy_name="CUnit"),
                "DUnit": _summary(n_trades=30, sharpe=0.0, strategy_name="DUnit"),
            }
            return mapping[strategy_name]

        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(side_effect=fake_perf),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.7,
                available_strategies=[sa, sb, sc, sd],
                symbol="BTC",
                max_strategies=3,
                min_combined_score=0.1,
            )
        assert len(result) == 3
        assert [a.strategy_name for a in result] == ["AUnit", "BUnit", "CUnit"]
        total_alloc = sum(a.allocated_pct for a in result)
        assert total_alloc == pytest.approx(1.0, abs=1e-6)
        # Higher combined_score → larger allocation
        assert result[0].allocated_pct >= result[1].allocated_pct
        assert result[1].allocated_pct >= result[2].allocated_pct


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


class TestResilience:
    async def test_perf_lookup_exception_falls_back_to_fitness(self):
        strat = _FakeStrategy("BoomUnit", RegimeFitness(high_vol_choppy=0.9))
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.7,
                available_strategies=[strat],
                symbol="BTC",
                min_combined_score=0.1,
            )
        # Selector treats failure as "no history" → fitness * penalty
        assert len(result) == 1
        assert result[0].has_history is False
        assert result[0].combined_score == pytest.approx(0.9 * NO_HISTORY_PENALTY)

    async def test_fitness_lookup_exception_skips_strategy(self):
        class _BoomStrategy(_FakeStrategy):
            def regime_fitness(self) -> RegimeFitness:
                raise RuntimeError("fitness boom")

        boom = _BoomStrategy("BoomFitUnit", RegimeFitness(high_vol_choppy=0.9))
        # BaseStrategy.fitness_for swallows the exception → 0.0 → excluded
        with _patch(
            "src.services.strategy_selector.get_performance",
            new=AsyncMock(return_value=_summary()),
        ):
            result = await select_strategies(
                regime=MarketRegime.HIGH_VOL_CHOPPY,
                regime_confidence=0.7,
                available_strategies=[boom],
                symbol="BTC",
                min_combined_score=0.1,
            )
        assert result == []
