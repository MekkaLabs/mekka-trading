"""
src/services/cycle_trajectory.py
========================================
Story 188 — CycleTrajectory: registro imutável de steps por ciclo.

Inspirado no padrão SWE-agent Trajectory/StepOutput:
  "The Agent (DefaultAgent) owns the 'while not done' loop, holds the chat
   history, a list of StepOutputs called the _trajectory, and a reference
   to the model and environment. Each trajectory step contains: the LM response,
   parsed thoughts and actions, execution output (observation), extracted state
   information, and all messages shown to the LM (query)."

No SWE-agent, cada turn da ferramenta gera um StepOutput com:
  thought (raciocínio livre do LLM), action (comando executado),
  observation (output do comando), query (mensagens exibidas ao LLM).

No Mekka, o equivalente é cada estágio do ciclo de trading:
  stage (ex: "VISION_SIGNAL"), input_summary (análise recebida),
  output_summary (sinal emitido), observation (resultado do lint/validação),
  latency_ms (tempo do estágio).

A trajetória é append-only e serializável — usada para:
  - Auditoria post-mortem de ciclos que geraram ordens
  - Replay de ciclos problemáticos para debug
  - Dashboard "what happened in this cycle?"
  - Métricas de latência por estágio

Arquitetura
-----------
  StepRecord — um step da trajetória (stage, input, output, observation, latency, ok)
  CycleTrajectory — sequência de StepRecords para um ciclo
  TrajectoryStore — mantém as últimas N trajetórias por símbolo
    ├── start_cycle(symbol, cycle_id) → CycleTrajectory
    ├── record_step(cycle_id, stage, ...) → StepRecord
    ├── finish_cycle(cycle_id, success, final_action)
    ├── get(cycle_id) → CycleTrajectory | None
    └── summary() → dict

Uso em NickFury
---------------
    from src.services.cycle_trajectory import get_trajectory_store

    traj = get_trajectory_store().start_cycle(symbol, cycle_id=str(_cycle_id))
    # ... após Vision:
    get_trajectory_store().record_step(str(_cycle_id), stage="VISION_SIGNAL",
        input_summary=f"price={analysis.price}",
        output_summary=f"action={signal.action} conf={signal.confidence}",
        latency_ms=elapsed_ms)
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# StepRecord
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    """
    Um step da trajetória — equivalente ao StepOutput do SWE-agent.

    Campos espelham SWE-agent:
      stage         ↔  action (qual Action/ferramenta foi executada)
      input_summary ↔  query  (contexto recebido pelo agente)
      output_summary ↔ thought + action (raciocínio + comando executado)
      observation    ↔ observation (output da execução)
    """
    stage: str                    # ex: "VISION_SIGNAL", "SIGNAL_LINT", "RISK_ASSESSMENT"
    input_summary: str            # resumo do input recebido
    output_summary: str           # resumo do output produzido
    observation: str = ""         # feedback do estágio (lint erros, validator msg, etc.)
    latency_ms: float = 0.0       # tempo do estágio em ms
    ok: bool = True               # True = sucesso, False = erro/skip
    timestamp: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "observation": self.observation,
            "latency_ms": round(self.latency_ms, 1),
            "ok": self.ok,
        }


# ---------------------------------------------------------------------------
# CycleTrajectory
# ---------------------------------------------------------------------------

@dataclass
class CycleTrajectory:
    """
    Trajetória imutável de um ciclo de trading — equivalente ao _trajectory do SWE-agent.

    Append-only: steps são adicionados via record_step(), nunca removidos.
    Serializável: to_jsonl() / to_dict() para auditoria e replay.
    """
    cycle_id: str
    symbol: str
    started_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None
    success: Optional[bool] = None
    final_action: str = ""            # "LONG", "SHORT", "HOLD", "BLOCKED"
    _steps: List[StepRecord] = field(default_factory=list)

    def record(
        self,
        stage: str,
        input_summary: str,
        output_summary: str,
        observation: str = "",
        latency_ms: float = 0.0,
        ok: bool = True,
    ) -> StepRecord:
        """Adiciona um step à trajetória."""
        step = StepRecord(
            stage=stage,
            input_summary=input_summary,
            output_summary=output_summary,
            observation=observation,
            latency_ms=latency_ms,
            ok=ok,
        )
        self._steps.append(step)
        return step

    @property
    def steps(self) -> List[StepRecord]:
        return list(self._steps)

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self._steps)

    @property
    def slowest_stage(self) -> Optional[str]:
        if not self._steps:
            return None
        return max(self._steps, key=lambda s: s.latency_ms).stage

    @property
    def error_count(self) -> int:
        return sum(1 for s in self._steps if not s.ok)

    @property
    def duration_s(self) -> float:
        end = self.finished_at or time.monotonic()
        return end - self.started_at

    def finish(self, success: bool, final_action: str = "") -> None:
        self.finished_at = time.monotonic()
        self.success = success
        self.final_action = final_action.upper()

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "duration_s": round(self.duration_s, 3),
            "total_latency_ms": round(self.total_latency_ms, 1),
            "slowest_stage": self.slowest_stage,
            "error_count": self.error_count,
            "success": self.success,
            "final_action": self.final_action,
            "steps": [s.to_dict() for s in self._steps],
        }

    def to_jsonl(self) -> str:
        """Serializa como JSONL — uma linha por step (formato SWE-agent .traj)."""
        lines = []
        for step in self._steps:
            lines.append(json.dumps({
                "cycle_id": self.cycle_id,
                "symbol": self.symbol,
                **step.to_dict(),
            }, default=str))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TrajectoryStore
# ---------------------------------------------------------------------------

class TrajectoryStore:
    """
    Mantém as últimas N trajetórias em memória por símbolo.

    Padrão SWE-agent: o Agent guarda toda a trajetória para auditoria,
    replay e métricas de custo. Aqui usamos deque rotativo para evitar
    crescimento ilimitado.
    """

    def __init__(self, max_per_symbol: int = 20, max_total: int = 200) -> None:
        self._by_id: Dict[str, CycleTrajectory] = {}
        self._by_symbol: Dict[str, Deque[str]] = {}   # symbol → [cycle_id]
        self._max_per_symbol = max_per_symbol
        self._max_total = max_total
        self._total_started: int = 0

    def start_cycle(self, symbol: str, cycle_id: str) -> CycleTrajectory:
        """Inicia uma nova trajetória para o ciclo."""
        sym = symbol.upper()
        traj = CycleTrajectory(cycle_id=cycle_id, symbol=sym)
        self._by_id[cycle_id] = traj
        self._total_started += 1

        if sym not in self._by_symbol:
            self._by_symbol[sym] = deque(maxlen=self._max_per_symbol)
        self._by_symbol[sym].append(cycle_id)

        # Evita crescimento ilimitado do dict global
        if len(self._by_id) > self._max_total:
            oldest = next(iter(self._by_id))
            del self._by_id[oldest]

        logger.debug(f"[CycleTrajectory] started {cycle_id} for {sym}")
        return traj

    def record_step(
        self,
        cycle_id: str,
        stage: str,
        input_summary: str,
        output_summary: str,
        observation: str = "",
        latency_ms: float = 0.0,
        ok: bool = True,
    ) -> Optional[StepRecord]:
        """Registra um step em uma trajetória existente."""
        traj = self._by_id.get(cycle_id)
        if traj is None:
            logger.debug(f"[CycleTrajectory] cycle_id {cycle_id} not found — step skipped")
            return None
        return traj.record(stage, input_summary, output_summary, observation, latency_ms, ok)

    def finish_cycle(self, cycle_id: str, success: bool, final_action: str = "") -> bool:
        """Finaliza uma trajetória. Retorna True se encontrou o ciclo."""
        traj = self._by_id.get(cycle_id)
        if traj is None:
            return False
        traj.finish(success=success, final_action=final_action)
        logger.debug(
            f"[CycleTrajectory] finished {cycle_id} success={success} "
            f"action={final_action} steps={len(traj.steps)}"
        )
        return True

    def get(self, cycle_id: str) -> Optional[CycleTrajectory]:
        return self._by_id.get(cycle_id)

    def get_recent(self, symbol: str, limit: int = 5) -> List[CycleTrajectory]:
        """Retorna as trajetórias mais recentes de um símbolo."""
        sym = symbol.upper()
        ids = list(self._by_symbol.get(sym, []))[-limit:]
        return [self._by_id[cid] for cid in ids if cid in self._by_id]

    def summary(self) -> dict:
        finished = [t for t in self._by_id.values() if t.success is not None]
        avg_latency = (
            sum(t.total_latency_ms for t in finished) / len(finished) if finished else 0.0
        )
        return {
            "total_started": self._total_started,
            "total_in_memory": len(self._by_id),
            "symbols_tracked": len(self._by_symbol),
            "finished_cycles": len(finished),
            "avg_total_latency_ms": round(avg_latency, 1),
            "max_per_symbol": self._max_per_symbol,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[TrajectoryStore] = None


def get_trajectory_store(max_per_symbol: int = 20) -> TrajectoryStore:
    """Retorna o singleton global do TrajectoryStore."""
    global _store
    if _store is None:
        try:
            from src.config.settings import settings
            max_n = int(getattr(settings, "trajectory_max_per_symbol", max_per_symbol))
        except Exception:  # noqa: BLE001
            max_n = max_per_symbol
        _store = TrajectoryStore(max_per_symbol=max_n)
    return _store


def reset_trajectory_store() -> None:
    """Reseta o singleton — para testes."""
    global _store
    _store = None
