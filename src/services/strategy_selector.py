"""
src/services/strategy_selector.py
==================================
StrategySelector — combina fitness DECLARADO (estratégias declaram
``regime_fitness``) com performance EMPÍRICA (PerformanceTracker) para
alocar capital entre estratégias num dado regime de mercado.

Filosofia: "Be water" — adaptar-se ao mercado, não impor crenças.

Pesos
-----
``combined_score = w_fitness * fitness_score + w_history * historical_score``

Default: ``(0.4, 0.6)`` — preferimos empírico, mas honramos a declaração
da estratégia (que carrega contexto humano/de pesquisa que o tracker não
captura). Quando não há histórico, usamos ``fitness_score * 0.7``
(penalty para privilegiar estratégias com track record).

Alocação
--------
Estratégias selecionadas têm capital alocado proporcionalmente ao
combined_score, normalizado para somar 1.0. Se nenhuma supera
``min_combined_score``, retornamos lista vazia → mode FLAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from src.services.strategy_performance_tracker import (
    StrategyPerformanceSummary,
    get_performance,
)
from src.strategies.base import BaseStrategy, MarketRegime


_log = logger.bind(service="StrategySelector")


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

FITNESS_WEIGHT = 0.4
HISTORY_WEIGHT = 0.6
NO_HISTORY_PENALTY = 0.7  # penalize strategies with no track record
FITNESS_FLOOR = 0.3       # strategies below this fitness are excluded


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass
class StrategyAllocation:
    """One row per chosen strategy with its score breakdown and capital share.

    ``allocated_pct`` is the fraction of TOTAL capital (across the
    selected basket) that should go to this strategy. Sum across the
    returned list is 1.0.
    """

    strategy_name: str
    fitness_score: float           # 0-1, from BaseStrategy.regime_fitness
    historical_score: float        # 0-1, derived from PerformanceTracker
    combined_score: float          # weighted blend in [0, 1]
    allocated_pct: float           # 0-1, share of total capital

    # Optional context for dashboard / audit
    has_history: bool = False
    n_trades: int = 0
    sharpe_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    rationale: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "fitness_score": round(self.fitness_score, 4),
            "historical_score": round(self.historical_score, 4),
            "combined_score": round(self.combined_score, 4),
            "allocated_pct": round(self.allocated_pct, 4),
            "has_history": self.has_history,
            "n_trades": self.n_trades,
            "sharpe_ratio": (
                round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None
            ),
            "win_rate": (
                round(self.win_rate, 4) if self.win_rate is not None else None
            ),
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _historical_from_summary(s: StrategyPerformanceSummary) -> tuple[float, bool]:
    """Map a performance summary to a 0-1 historical_score.

    Sharpe is preferred (mapped via tanh-ish curve so Sharpe>=2.0 → ~1.0).
    Falls back to win_rate when Sharpe is None. Returns (score, has_history).
    """
    if s.n_trades <= 0:
        return 0.0, False

    if s.sharpe_ratio is not None:
        # Linear mapping: Sharpe 0 → 0.5, Sharpe 2 → 1.0, Sharpe -2 → 0.0
        # Clamp to [0, 1]. This is intentionally gentle — selectors that
        # want a sharper rank can post-process combined_score.
        score = max(0.0, min(1.0, 0.5 + (s.sharpe_ratio / 4.0)))
        return score, True

    # Fallback to win_rate (already in 0-1)
    return max(0.0, min(1.0, s.win_rate)), True


def _normalize_allocations(allocs: list[StrategyAllocation]) -> list[StrategyAllocation]:
    """Normalize allocated_pct so the basket sums to 1.0 (when non-empty)."""
    total = sum(a.combined_score for a in allocs)
    if total <= 0:
        # Fallback: equal-weight when scores are degenerate
        n = len(allocs)
        if n == 0:
            return []
        share = 1.0 / n
        for a in allocs:
            a.allocated_pct = share
        return allocs

    for a in allocs:
        a.allocated_pct = round(a.combined_score / total, 6)

    # Correct rounding drift on the last one so the sum is exactly 1.0
    drift = 1.0 - sum(a.allocated_pct for a in allocs)
    if abs(drift) > 1e-9 and allocs:
        allocs[-1].allocated_pct = round(allocs[-1].allocated_pct + drift, 6)

    return allocs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def select_strategies(
    regime: MarketRegime,
    regime_confidence: float,
    available_strategies: list[BaseStrategy],
    symbol: str,
    max_strategies: int = 3,
    min_combined_score: float = 0.5,
    window_days: int = 30,
) -> list[StrategyAllocation]:
    """Select and allocate capital among strategies for the current regime.

    Steps
    -----
    1. Filter by declared ``regime_fitness > FITNESS_FLOOR``.
    2. For each eligible strategy, fetch historical performance for
       (strategy, regime, symbol).
    3. Combine: ``combined = w_f * fitness + w_h * history`` (or apply
       ``NO_HISTORY_PENALTY`` when ``n_trades < min_trades_for_history``).
    4. Keep only strategies with ``combined >= min_combined_score``.
    5. Top N by combined_score, then normalize ``allocated_pct`` to 1.0.

    Returns ``[]`` (FLAT) when nothing qualifies — caller should stand
    aside instead of forcing a trade.

    ``regime_confidence`` is not directly used in the math today but is
    attached to ``extras["regime_confidence"]`` of each allocation so
    downstream (Batman / Vision) can use it as a global volume cap.
    """
    if not available_strategies:
        _log.warning("select_strategies: empty strategy list — returning FLAT")
        return []

    sym = symbol.upper().strip()

    # Step 1+2: build candidate list with scores
    candidates: list[StrategyAllocation] = []
    for strat in available_strategies:
        try:
            fitness = strat.fitness_for(regime)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                f"select_strategies: {strat.name} fitness lookup failed: {exc}"
            )
            continue

        if fitness <= FITNESS_FLOOR:
            continue

        try:
            summary = await get_performance(
                strategy_name=strat.name,
                regime=regime.value,
                symbol=sym,
                window_days=window_days,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                f"select_strategies: {strat.name} perf lookup failed: {exc}"
            )
            summary = StrategyPerformanceSummary(
                strategy_name=strat.name,
                regime=regime.value,
                symbol=sym,
                window_days=window_days,
            )

        hist_score, has_history = _historical_from_summary(summary)

        if has_history:
            combined = FITNESS_WEIGHT * fitness + HISTORY_WEIGHT * hist_score
            rationale = (
                f"fitness={fitness:.2f} × {FITNESS_WEIGHT} + "
                f"history={hist_score:.2f} × {HISTORY_WEIGHT}"
            )
        else:
            # No history → use fitness alone, but penalize so tracked
            # strategies win ties.
            hist_score = 0.0
            combined = fitness * NO_HISTORY_PENALTY
            rationale = (
                f"fitness={fitness:.2f} × {NO_HISTORY_PENALTY} (no history)"
            )

        candidates.append(
            StrategyAllocation(
                strategy_name=strat.name,
                fitness_score=fitness,
                historical_score=hist_score,
                combined_score=round(combined, 6),
                allocated_pct=0.0,  # filled after pruning
                has_history=has_history,
                n_trades=summary.n_trades,
                sharpe_ratio=summary.sharpe_ratio,
                win_rate=summary.win_rate if summary.n_trades > 0 else None,
                rationale=rationale,
                extras={
                    "regime": regime.value,
                    "regime_confidence": regime_confidence,
                    "symbol": sym,
                },
            )
        )

    if not candidates:
        _log.info(
            f"select_strategies: no fitness>{FITNESS_FLOOR} candidates for "
            f"{regime.value} on {sym} — FLAT"
        )
        return []

    # Step 4: threshold
    qualified = [c for c in candidates if c.combined_score >= min_combined_score]
    if not qualified:
        _log.info(
            f"select_strategies: no candidates >= min_combined_score="
            f"{min_combined_score:.2f} for {regime.value} on {sym} — FLAT"
        )
        return []

    # Step 5: top N + normalize
    qualified.sort(key=lambda a: a.combined_score, reverse=True)
    top = qualified[: max(1, max_strategies)]
    return _normalize_allocations(top)
