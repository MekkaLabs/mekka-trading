"""
src/services/cycle_state_resetter.py
======================================
Story 202 — CycleStateResetter: reset limpo do estado entre ciclos,
inspirado no AgentController.reset() do OpenHands.

Inspirado no padrão OpenHands AgentController.reset()
(All-Hands-AI/OpenHands, openhands/controller/agent_controller.py):
  "AgentController.reset() performs a clean state reset between tasks:
     - Clears the agent's step count and iteration counter
     - Resets the delegate stack (is_delegate=False, delegate=None)
     - Flushes the retry mixin state (_num_retries, _exhausted flag)
     - Resets cost tracking (accumulated_cost back to 0)
     - Transitions AgentState to LOADING for fresh start
     - Does NOT reset the EventStream — history is preserved
   This allows the same controller to run multiple tasks sequentially
   without memory leaks from previous runs."

No OpenHands:
  reset() é chamado antes de cada nova tarefa no mesmo controller.
  Preserva o EventStream (histórico completo) mas limpa estado efêmero:
  contadores, delegates, retry state, cost accumulators.

No Mekka, o equivalente é:
  CycleStateResetter executa um reset coordenado de todos os singletons
  de estado efêmero ao final/início de cada ciclo completo:
    - CycleAgentStateMachine → transição para IDLE em todos os símbolos
    - VisionRetryMixin → reseta contadores de retry (não o histórico)
    - CycleBatchedExporter → flush pendente antes do reset
    - CycleConversationMemory → opcional: clear_symbol() por símbolo
    - CycleCondensationEngine → reseta stats do ciclo
  Preserva: CycleEventLog, CycleTrajectory, CycleArtifactStore (audit)

  Chamado em NickFury ao início de cada ciclo (pré-scan) ou após erro.

Arquitetura
-----------
  ResetScope     — enum CYCLE_START / CYCLE_END / ERROR_RECOVERY / FULL
  ResetRecord    — log de um reset executado
  CycleStateResetter
    ├── reset(scope, symbol, cycle_id) → ResetRecord
    ├── reset_all_symbols(scope) → List[ResetRecord]
    ├── get_records(limit) → List[ResetRecord]
    └── summary() → dict
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# ResetScope
# ---------------------------------------------------------------------------

class ResetScope(str, Enum):
    """
    Escopo do reset a ser executado.

    Mapeamento com OpenHands AgentController.reset():
      CYCLE_START    ←→ reset antes de iniciar nova tarefa
      CYCLE_END      ←→ flush + cleanup após ciclo completo
      ERROR_RECOVERY ←→ reset após erro crítico (state → IDLE)
      FULL           ←→ reset total (equivale a reiniciar o controller)
    """
    CYCLE_START = "CYCLE_START"
    CYCLE_END = "CYCLE_END"
    ERROR_RECOVERY = "ERROR_RECOVERY"
    FULL = "FULL"


# ---------------------------------------------------------------------------
# ResetRecord
# ---------------------------------------------------------------------------

@dataclass
class ResetRecord:
    """
    Log de um reset executado.

    Equivalente ao log interno do AgentController.reset() no OpenHands:
    registra quais componentes foram resetados e o resultado.
    """
    scope: ResetScope
    symbol: str
    cycle_id: str
    components_reset: List[str] = field(default_factory=list)
    components_failed: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return len(self.components_failed) == 0

    def to_log_line(self) -> str:
        status = "OK" if self.success else f"PARTIAL ({len(self.components_failed)} failed)"
        return (
            f"RESET:{self.scope.value} | {self.symbol} | "
            f"components={len(self.components_reset)} | status={status} | "
            f"{self.duration_ms:.1f}ms"
        )

    def to_dict(self) -> dict:
        return {
            "scope": self.scope.value,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "components_reset": self.components_reset,
            "components_failed": self.components_failed,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# CycleStateResetter
# ---------------------------------------------------------------------------

class CycleStateResetter:
    """
    Coordena o reset limpo do estado efêmero entre ciclos.

    Padrão OpenHands AgentController.reset():
    - Reset coordenado de todos os singletons de estado efêmero
    - Preserva histórico de audit (EventLog, Trajectory, ArtifactStore)
    - Fail-silent: falha em um componente não impede os outros
    - Registra ResetRecord para auditoria

    Uso:
        resetter = get_cycle_state_resetter()
        record = resetter.reset(ResetScope.CYCLE_START, symbol="BTC", cycle_id=cycle_id)
        if not record.success:
            logger.warning(f"Reset parcial: {record.components_failed}")
    """

    def __init__(self, max_records: int = 100) -> None:
        self.max_records = max_records
        self._records: List[ResetRecord] = []
        self._total_resets: int = 0
        self._total_failures: int = 0

    def reset(
        self,
        scope: ResetScope,
        symbol: str = "",
        cycle_id: str = "",
    ) -> ResetRecord:
        """
        Executa reset para o escopo e símbolo especificados.

        Args:
            scope:    Escopo do reset
            symbol:   Símbolo alvo (vazio = todos)
            cycle_id: ID do ciclo

        Returns:
            ResetRecord com resultado da operação.
        """
        t_start = time.monotonic()
        sym = symbol.upper() if symbol else ""
        record = ResetRecord(scope=scope, symbol=sym or "ALL", cycle_id=cycle_id)

        # 1. CycleAgentStateMachine → transição para IDLE
        self._try_reset_component(
            record,
            "CycleAgentStateMachine",
            lambda: self._reset_state_machine(sym, cycle_id),
        )

        # 2. VisionRetryMixin → reseta contadores
        self._try_reset_component(
            record,
            "VisionRetryMixin",
            lambda: self._reset_retry_mixin(),
        )

        # 3. CycleBatchedExporter → flush pendente
        if scope in (ResetScope.CYCLE_END, ResetScope.FULL):
            self._try_reset_component(
                record,
                "CycleBatchedExporter",
                lambda: self._flush_exporter(),
            )

        # 4. CycleConversationMemory → clear se FULL
        if scope == ResetScope.FULL:
            self._try_reset_component(
                record,
                "CycleConversationMemory",
                lambda: self._reset_conversation_memory(sym),
            )

        # 5. CycleCondensationEngine → reseta stats de sessão
        if scope in (ResetScope.CYCLE_END, ResetScope.FULL):
            self._try_reset_component(
                record,
                "CycleCondensationEngine",
                lambda: self._note_condensation_reset(),
            )

        record.duration_ms = (time.monotonic() - t_start) * 1000
        self._records.append(record)
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]

        self._total_resets += 1
        if not record.success:
            self._total_failures += 1

        logger.debug(f"[CycleStateResetter] {record.to_log_line()}")
        return record

    def _try_reset_component(
        self,
        record: ResetRecord,
        name: str,
        fn,
    ) -> None:
        """Executa fn() de forma fail-silent, registra no record."""
        try:
            fn()
            record.components_reset.append(name)
        except Exception as exc:  # noqa: BLE001
            record.components_failed.append(name)
            logger.debug(f"[CycleStateResetter] {name} reset failed: {exc}")

    def _reset_state_machine(self, symbol: str, cycle_id: str) -> None:
        from src.services.cycle_agent_state import (
            get_cycle_agent_state_machine,
            CycleAgentStateEnum,
        )
        sm = get_cycle_agent_state_machine()
        if symbol:
            current = sm.get_state(symbol)
            if current != CycleAgentStateEnum.IDLE:
                sm.transition(symbol, CycleAgentStateEnum.IDLE, cycle_id=cycle_id)
        else:
            for sym_state in sm.all_states():
                s = sym_state["symbol"]
                if sym_state["current_state"] != CycleAgentStateEnum.IDLE.value:
                    sm.transition(s, CycleAgentStateEnum.IDLE, cycle_id=cycle_id)

    def _reset_retry_mixin(self) -> None:
        from src.services.vision_retry_mixin import get_vision_retry_mixin
        mixin = get_vision_retry_mixin()
        # Reseta apenas contadores de sessão, preserva config
        mixin._total_retries = 0
        mixin._total_failures = 0
        mixin._total_successes = 0
        mixin._total_calls = 0

    def _flush_exporter(self) -> None:
        from src.services.cycle_batched_exporter import get_cycle_batched_exporter
        exporter = get_cycle_batched_exporter()
        exporter.flush()

    def _reset_conversation_memory(self, symbol: str) -> None:
        from src.services.cycle_conversation_memory import get_cycle_conversation_memory
        mem = get_cycle_conversation_memory()
        if symbol:
            mem.clear_symbol(symbol)
        else:
            mem.clear_all()

    def _note_condensation_reset(self) -> None:
        # Apenas loga — o engine não tem estado efêmero para resetar
        from src.services.cycle_condensation_engine import get_cycle_condensation_engine
        engine = get_cycle_condensation_engine()
        logger.debug(
            f"[CycleStateResetter] CondensationEngine: "
            f"{engine._total_condensations} condensations this session"
        )

    def reset_all_symbols(
        self,
        scope: ResetScope = ResetScope.CYCLE_END,
        cycle_id: str = "",
    ) -> List[ResetRecord]:
        """
        Executa reset para todos os símbolos rastreados.

        Útil ao final de um ciclo completo multi-symbol.

        Returns:
            Lista de ResetRecord, um por símbolo.
        """
        try:
            from src.services.cycle_agent_state import get_cycle_agent_state_machine
            sm = get_cycle_agent_state_machine()
            symbols = [s["symbol"] for s in sm.all_states()]
        except Exception:  # noqa: BLE001
            symbols = []

        if not symbols:
            # Reset global sem símbolo específico
            return [self.reset(scope, symbol="", cycle_id=cycle_id)]

        return [self.reset(scope, symbol=sym, cycle_id=cycle_id) for sym in symbols]

    def get_records(self, limit: int = 20) -> List[ResetRecord]:
        """Retorna registros de reset mais recentes."""
        return self._records[-limit:]

    def summary(self) -> dict:
        return {
            "total_resets": self._total_resets,
            "total_failures": self._total_failures,
            "records_stored": len(self._records),
            "last_reset_scope": self._records[-1].scope.value if self._records else None,
            "last_reset_success": self._records[-1].success if self._records else None,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_resetter: Optional[CycleStateResetter] = None


def get_cycle_state_resetter() -> CycleStateResetter:
    """Retorna o singleton global do CycleStateResetter."""
    global _resetter
    if _resetter is None:
        _resetter = CycleStateResetter()
    return _resetter


def reset_cycle_state_resetter() -> None:
    """Reseta o singleton — para testes."""
    global _resetter
    _resetter = None
