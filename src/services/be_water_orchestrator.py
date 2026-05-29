"""
src/services/be_water_orchestrator.py
=======================================
Be Water Orchestrator — cola RegimeDetector + StrategySelector +
CapitalAllocator + estratégias num pipeline coerente, consumível pelo
NickFury cycle ou via API/CLI.

Pipeline:
1. detect_regime(analysis) → DetectedRegime
2. select_strategies(regime, available, symbol) → list[StrategyAllocation]
3. para cada allocation: strategy.safe_signal(context) → StrategySignal
4. agrega + retorna BeWaterDecision com TODOS os sinais ranqueados

Outputs alimentam Vision/Batman:
- Vision pode receber bloco "=== STRATEGY POOL ===" com top sinais
- Batman pode rejeitar trades não-compatíveis com regime atual

Princípios:
- READ-ONLY no analysis
- FAIL-SILENT em qualquer stage (degrada graciosamente)
- AUDIT trail completo via metadata
- INDEPENDENTE: pode rodar sem afetar Mekka cycle existente
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from src.services.regime_detector import DetectedRegime, detect_regime
from src.strategies.base import (
    BaseStrategy,
    MarketRegime,
    StrategyContext,
    StrategySignal,
)


async def _audit_decision(decision: "BeWaterDecision") -> None:
    """INV-12 (2026-05-29): emite BE_WATER_DECISION ao audit_log.

    Antes: o pipeline rodava silenciosamente — não era possível auditar
    historicamente quais regimes/estratégias o orchestrator escolheu,
    nem por que ficou flat. Agora cada decide() vira um registro com:
      - regime detectado + confidence
      - estratégias selecionadas e seus combined_scores
      - top signal (se houver)
      - rationale do flat (se aplicável)

    Fail-silent — qualquer erro de I/O é apenas logado.
    """
    try:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        top = decision.top_signal()
        payload = {
            "symbol": decision.symbol,
            "regime": decision.regime.regime.value,
            "regime_confidence": round(decision.regime.confidence, 4),
            "flat": decision.flat,
            "n_signals": len(decision.signals),
            "top_strategy": top.strategy_name if top else None,
            "top_action": top.action.value if top else None,
            "top_confidence": round(top.confidence, 4) if top else None,
            "rationale": decision.rationale[:200],
            "selected_count": decision.metadata.get("selected_count"),
            "actionable_count": decision.metadata.get("actionable_count"),
        }
        severity = "INFO" if not decision.flat else "DEBUG"
        message = (
            f"BeWater: regime={decision.regime.regime.value} "
            f"(conf={decision.regime.confidence:.2f}) — "
            f"{'FLAT' if decision.flat else f'top={top.strategy_name}/{top.action.value}' if top else 'no top'}"
        )
        await MekkaRepository.log_event(
            agent="BeWater",
            event="BE_WATER_DECISION",
            severity=severity,
            message=message,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[be_water] audit emit skipped: {exc}")


@dataclass
class BeWaterDecision:
    """Resultado final do orchestrator: regime + sinais ranqueados."""
    symbol: str
    regime: DetectedRegime
    signals: list[StrategySignal]    # ranqueados por confidence × allocation
    flat: bool = False               # True quando nenhuma estratégia ativa
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    decided_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "regime": self.regime.to_dict(),
            "signals": [s.to_dict() for s in self.signals],
            "flat": self.flat,
            "rationale": self.rationale,
            "metadata": self.metadata,
            "decided_at": self.decided_at.isoformat(),
        }

    def top_signal(self) -> Optional[StrategySignal]:
        """Retorna o sinal #1 (highest scored). None quando flat."""
        if self.flat or not self.signals:
            return None
        return self.signals[0]


async def decide(
    symbol: str,
    analysis: Any,
    equity_usd: float,
    open_positions_count: int = 0,
    max_strategies: int = 3,
    min_combined_score: float = 0.5,
    available_strategies: Optional[list[BaseStrategy]] = None,
) -> BeWaterDecision:
    """
    Pipeline completo: regime → selection → signals.

    Args:
        symbol: ativo (BTC, ETH, etc)
        analysis: MarketAnalysis ou similar
        equity_usd: equity total atual pra dimensionar alocação
        open_positions_count: número de posições já abertas (rate-limit)
        max_strategies: máx estratégias ativas simultaneamente
        min_combined_score: threshold pra estratégia ser elegível
        available_strategies: lista override (default = registry.get_all)

    Returns:
        BeWaterDecision. Quando flat=True, signals está vazio e rationale
        explica o porquê.
    """
    # 1. Detect regime
    try:
        regime = detect_regime(analysis)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[be_water] regime detection failed: {exc}")
        return BeWaterDecision(
            symbol=symbol,
            regime=DetectedRegime(
                regime=MarketRegime.UNCLEAR,
                confidence=0.0,
                rationale=f"detection error: {exc}",
            ),
            signals=[],
            flat=True,
            rationale="regime detection failed",
        )

    if regime.regime == MarketRegime.UNCLEAR or regime.confidence < 0.3:
        decision = BeWaterDecision(
            symbol=symbol,
            regime=regime,
            signals=[],
            flat=True,
            rationale=f"regime unclear (conf={regime.confidence:.2f}) — staying flat",
        )
        await _audit_decision(decision)
        return decision

    # 2. Load strategies + select
    if available_strategies is None:
        try:
            from src.strategies.registry import get_all_strategies
            available_strategies = get_all_strategies()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[be_water] registry load failed: {exc}")
            available_strategies = []

    if not available_strategies:
        decision = BeWaterDecision(
            symbol=symbol, regime=regime, signals=[], flat=True,
            rationale="no strategies available",
        )
        await _audit_decision(decision)
        return decision

    try:
        from src.services.strategy_selector import select_strategies
        allocations = await select_strategies(
            regime=regime.regime,
            regime_confidence=regime.confidence,
            available_strategies=available_strategies,
            symbol=symbol,
            max_strategies=max_strategies,
            min_combined_score=min_combined_score,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[be_water] selector failed: {exc}")
        # Fallback: usa só fitness declarado sem histórico
        allocations = _fallback_selection(
            available_strategies, regime.regime, max_strategies,
        )

    if not allocations:
        decision = BeWaterDecision(
            symbol=symbol, regime=regime, signals=[], flat=True,
            rationale="no strategy met min_combined_score",
        )
        await _audit_decision(decision)
        return decision

    # 3. Generate signals per selected strategy
    strategy_by_name = {s.name: s for s in available_strategies}
    signals: list[StrategySignal] = []
    for alloc in allocations:
        strat = strategy_by_name.get(alloc.strategy_name)
        if strat is None:
            continue
        context = StrategyContext(
            symbol=symbol,
            analysis=analysis,
            regime=regime.regime,
            regime_confidence=regime.confidence,
            allocated_usd=equity_usd * alloc.allocated_pct,
            current_equity_usd=equity_usd,
            open_positions_count=open_positions_count,
        )
        sig = strat.safe_signal(context)
        # Append metadata da alocação
        sig.metadata.update({
            "fitness_score": alloc.fitness_score,
            "historical_score": alloc.historical_score,
            "combined_score": alloc.combined_score,
            "allocated_pct": alloc.allocated_pct,
            "allocated_usd": equity_usd * alloc.allocated_pct,
        })
        signals.append(sig)

    # Filtra apenas signals com ação concreta (LONG/SHORT)
    actionable = [s for s in signals if s.action.value in ("LONG", "SHORT")]
    # Ranqueia por confidence × allocated_pct
    actionable.sort(
        key=lambda s: s.confidence * (s.metadata.get("allocated_pct") or 0.0),
        reverse=True,
    )

    if not actionable:
        decision = BeWaterDecision(
            symbol=symbol, regime=regime, signals=[], flat=True,
            rationale=(
                f"all selected strategies returned HOLD/FLAT "
                f"({len(allocations)} selected, 0 actionable)"
            ),
            metadata={
                "selected_count": len(allocations),
                "actionable_count": 0,
                "all_signals_count": len(signals),
            },
        )
        await _audit_decision(decision)
        return decision

    decision = BeWaterDecision(
        symbol=symbol, regime=regime, signals=actionable,
        rationale=(
            f"{len(actionable)} actionable signals from "
            f"{len(allocations)} selected strategies"
        ),
        metadata={
            "selected_count": len(allocations),
            "actionable_count": len(actionable),
            "all_signals_count": len(signals),
        },
    )
    await _audit_decision(decision)
    return decision


def _fallback_selection(
    available: list[BaseStrategy],
    regime: MarketRegime,
    max_strategies: int,
) -> list[Any]:
    """Fallback quando StrategySelector/PerformanceTracker indisponíveis.
    Usa só fitness declarado."""

    @dataclass
    class _FallbackAlloc:
        strategy_name: str
        fitness_score: float
        historical_score: float = 0.0
        combined_score: float = 0.0
        allocated_pct: float = 0.0

    candidates = []
    for s in available:
        try:
            fitness = s.fitness_for(regime)
            if fitness >= 0.5:
                candidates.append((s.name, fitness))
        except Exception:  # noqa: BLE001
            continue
    candidates.sort(key=lambda x: -x[1])
    top = candidates[:max_strategies]
    if not top:
        return []
    total_fitness = sum(c[1] for c in top) or 1.0
    return [
        _FallbackAlloc(
            strategy_name=name,
            fitness_score=fitness,
            combined_score=fitness,
            allocated_pct=fitness / total_fitness,
        )
        for name, fitness in top
    ]
