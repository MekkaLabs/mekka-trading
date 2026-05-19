"""
src/services/cycle_parallel_branch.py
=======================================
Story 211 — CycleParallelBranch: fan-out/fan-in paralelo de análises por
símbolo, inspirado no LangGraph Send() API e parallel branches.

Inspirado no padrão LangGraph parallel branches:
(langchain-ai/langgraph):
  "LangGraph supports parallel execution via the Send API. A node can
   return Send objects to fan out to multiple branches simultaneously:
     from langgraph.constants import Send
     def expand_symbols(state):
         return [Send('analyze', {'symbol': s}) for s in state['symbols']]
     graph.add_conditional_edges('router', expand_symbols)
   All branches run concurrently and their results are collected by a
   'fan-in' node that merges the outputs (using operator.add for lists
   or custom reducers for dicts)."

No Mekka:
  CycleParallelBranch executa análises de múltiplos símbolos em paralelo
  (usando asyncio.gather ou ThreadPoolExecutor para o modo síncrono) e
  faz fan-in dos resultados de sinais numa lista consolidada.

  NickFury usa isso para analisar BTC + ETH + SOL simultaneamente e
  selecionar o sinal de maior convicção como ação do ciclo.

Arquitetura
-----------
  BranchInput     — input de uma branch (symbol + state_override)
  BranchResult    — resultado de uma branch (symbol + state + elapsed_ms)
  CycleParallelBranch
    ├── run(inputs, worker_fn) → List[BranchResult]     (sync)
    ├── run_async(inputs, worker_fn) → List[BranchResult] (async)
    └── fan_in(results, merge_fn) → dict                (consolida)
  FanInStrategy   — MAX_CONFIDENCE / MAJORITY_VOTE / ALL
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# FanInStrategy
# ---------------------------------------------------------------------------

class FanInStrategy(str, Enum):
    MAX_CONFIDENCE = "max_confidence"  # retorna o sinal de maior confiança
    MAJORITY_VOTE  = "majority_vote"   # voto majoritário LONG/SHORT/HOLD
    ALL            = "all"             # retorna todos os sinais


# ---------------------------------------------------------------------------
# BranchInput / BranchResult
# ---------------------------------------------------------------------------

@dataclass
class BranchInput:
    """Input de uma branch individual."""
    symbol: str
    state_override: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BranchResult:
    """Resultado de uma branch executada."""
    symbol: str
    state: Dict[str, Any]
    elapsed_ms: float
    success: bool = True
    error: Optional[str] = None

    @property
    def signal(self) -> Dict[str, Any]:
        return self.state.get("signal") or {}

    @property
    def confidence(self) -> float:
        return float(self.signal.get("confidence") or 0.0)

    @property
    def action(self) -> str:
        return str(self.signal.get("action") or "HOLD").upper()


# ---------------------------------------------------------------------------
# CycleParallelBranch
# ---------------------------------------------------------------------------

class CycleParallelBranch:
    """
    Executor de branches paralelas para análise multi-símbolo.

    Equivalente ao Send() API do LangGraph: distribui work em paralelo
    e recolhe resultados com fan-in.

    Uso síncrono:
        branch = CycleParallelBranch(max_workers=4, timeout_s=30)
        inputs = [BranchInput('BTC', {...}), BranchInput('ETH', {...})]
        results = branch.run(inputs, worker_fn=my_analysis_fn)
        best = branch.fan_in(results, FanInStrategy.MAX_CONFIDENCE)

    Uso assíncrono (dentro de async def):
        results = await branch.run_async(inputs, worker_fn)
    """

    def __init__(
        self,
        max_workers: int = 4,
        timeout_s: float = 30.0,
    ) -> None:
        self._max_workers = max_workers
        self._timeout_s = timeout_s

    def run(
        self,
        inputs: List[BranchInput],
        worker_fn: Callable[[BranchInput], Dict[str, Any]],
    ) -> List[BranchResult]:
        """
        Executa todas as branches em paralelo via ThreadPoolExecutor.

        worker_fn(BranchInput) → dict (estado resultante da branch)
        """
        if not inputs:
            return []

        results: List[BranchResult] = []

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(inputs))) as pool:
            futures = {
                pool.submit(_run_branch, inp, worker_fn): inp
                for inp in inputs
            }
            for future in as_completed(futures, timeout=self._timeout_s):
                inp = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[CycleParallelBranch] branch %s failed: %s", inp.symbol, exc)
                    results.append(BranchResult(
                        symbol=inp.symbol,
                        state={},
                        elapsed_ms=0.0,
                        success=False,
                        error=str(exc),
                    ))

        logger.debug(
            "[CycleParallelBranch] %d/%d branches ok",
            sum(1 for r in results if r.success), len(inputs),
        )
        return results

    async def run_async(
        self,
        inputs: List[BranchInput],
        worker_fn: Callable[[BranchInput], Dict[str, Any]],
    ) -> List[BranchResult]:
        """
        Executa todas as branches em paralelo via asyncio.gather.

        worker_fn pode ser síncrona ou assíncrona. Se síncrona, é
        executada em loop.run_in_executor para não bloquear o event loop.
        """
        if not inputs:
            return []

        loop = asyncio.get_event_loop()

        async def _run_one(inp: BranchInput) -> BranchResult:
            try:
                start = time.monotonic()
                if asyncio.iscoroutinefunction(worker_fn):
                    state = await worker_fn(inp)
                else:
                    state = await loop.run_in_executor(None, worker_fn, inp)
                elapsed = (time.monotonic() - start) * 1000
                return BranchResult(symbol=inp.symbol, state=state or {}, elapsed_ms=elapsed)
            except Exception as exc:  # noqa: BLE001
                return BranchResult(
                    symbol=inp.symbol,
                    state={},
                    elapsed_ms=0.0,
                    success=False,
                    error=str(exc),
                )

        tasks = [_run_one(inp) for inp in inputs]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    def fan_in(
        self,
        results: List[BranchResult],
        strategy: FanInStrategy = FanInStrategy.MAX_CONFIDENCE,
    ) -> Dict[str, Any]:
        """
        Consolida os resultados de múltiplas branches numa decisão.

        Estratégias:
          MAX_CONFIDENCE — retorna o sinal de maior confiança entre os
                           resultados bem-sucedidos
          MAJORITY_VOTE  — conta votos LONG/SHORT/HOLD, retorna o majoritário
                           com confidence média dos votantes
          ALL            — retorna lista com todos os sinais
        """
        successful = [r for r in results if r.success and r.signal]
        if not successful:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "source": "fan_in_empty",
                "branches": len(results),
                "successful": 0,
            }

        if strategy == FanInStrategy.MAX_CONFIDENCE:
            best = max(successful, key=lambda r: r.confidence)
            return {
                **best.signal,
                "symbol": best.symbol,
                "source": "fan_in_max_confidence",
                "branches": len(results),
                "successful": len(successful),
            }

        if strategy == FanInStrategy.MAJORITY_VOTE:
            votes: Dict[str, List[float]] = {}
            for r in successful:
                action = r.action
                votes.setdefault(action, []).append(r.confidence)

            majority_action = max(votes, key=lambda a: len(votes[a]))
            avg_confidence = sum(votes[majority_action]) / len(votes[majority_action])
            return {
                "action": majority_action,
                "confidence": round(avg_confidence, 3),
                "source": "fan_in_majority_vote",
                "vote_tally": {a: len(v) for a, v in votes.items()},
                "branches": len(results),
                "successful": len(successful),
            }

        if strategy == FanInStrategy.ALL:
            return {
                "signals": [
                    {"symbol": r.symbol, **r.signal}
                    for r in successful
                ],
                "source": "fan_in_all",
                "branches": len(results),
                "successful": len(successful),
            }

        return {"action": "HOLD", "confidence": 0.0, "source": "fan_in_unknown"}


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------

def _run_branch(inp: BranchInput, fn: Callable) -> BranchResult:
    start = time.monotonic()
    state = fn(inp)
    elapsed = (time.monotonic() - start) * 1000
    return BranchResult(symbol=inp.symbol, state=state or {}, elapsed_ms=elapsed)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_parallel_branch: Optional[CycleParallelBranch] = None


def get_cycle_parallel_branch(
    max_workers: int = 4,
    timeout_s: float = 30.0,
) -> CycleParallelBranch:
    """Retorna o singleton global do CycleParallelBranch."""
    global _parallel_branch
    if _parallel_branch is None:
        _parallel_branch = CycleParallelBranch(
            max_workers=max_workers,
            timeout_s=timeout_s,
        )
    return _parallel_branch


def reset_cycle_parallel_branch() -> None:
    """Reseta o singleton — para testes."""
    global _parallel_branch
    _parallel_branch = None
