"""
src/services/cycle_agent_state.py
=====================================
Story 195 — CycleAgentState: state machine formal por símbolo (OpenHands AgentState).

Inspirado no padrão OpenHands AgentController AgentState:
  "AgentState is a formal enum encoding the controller's lifecycle:
   LOADING → RUNNING → PAUSED → STOPPED → FINISHED | ERROR | REJECTED.
   The controller transitions between states as it processes events.
   should_step() returns False when not in RUNNING state."

No OpenHands:
  class AgentState(str, Enum):
      LOADING = "loading"
      RUNNING = "running"
      AWAITING_USER_INPUT = "awaiting_user_input"
      PAUSED = "paused"
      STOPPED = "stopped"
      FINISHED = "finished"
      REJECTED = "rejected"
      ERROR = "error"

No Mekka, o equivalente é:
  NickFury._cycle_for_symbol() transita por estados bem definidos por símbolo.
  O dashboard pode consultar GET /api/agent-state para saber exatamente
  o que NickFury está fazendo agora para cada símbolo.
  A state machine é fail-silent: qualquer transição inválida vira log de debug.

Arquitetura
-----------
  CycleAgentStateEnum  — enum de estados do ciclo por símbolo
  SymbolAgentState     — estado atual + histórico de transições por símbolo
  CycleAgentStateMachine
    ├── transition(symbol, new_state, cycle_id) → bool
    ├── get_state(symbol) → CycleAgentStateEnum
    ├── get_symbol_state(symbol) → SymbolAgentState
    ├── reset(symbol)
    └── summary() → dict
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# CycleAgentStateEnum
# ---------------------------------------------------------------------------

class CycleAgentStateEnum(str, Enum):
    """
    Estados formais do ciclo de trading por símbolo.

    Mapeamento com OpenHands AgentState:
      IDLE        ←→ LOADING / STOPPED (aguardando próximo ciclo)
      SCANNING    ←→ RUNNING (oportunidade sendo avaliada)
      ANALYZING   ←→ RUNNING (ProfessorX / análise profunda)
      SIGNALING   ←→ RUNNING (Vision gerando sinal)
      LINTING     ←→ RUNNING (AutoSignalLinter corrigindo sinal)
      RISK_CHECK  ←→ RUNNING (Batman avaliando risco)
      EXECUTING   ←→ RUNNING (IronMan executando ordem)
      FINISHED    ←→ FINISHED (ciclo concluído com sucesso)
      ERROR       ←→ ERROR (falha não recuperável)
      SKIPPED     ←→ REJECTED (ciclo pulado por incremental guard / budget)
    """
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    ANALYZING = "ANALYZING"
    SIGNALING = "SIGNALING"
    LINTING = "LINTING"
    RISK_CHECK = "RISK_CHECK"
    EXECUTING = "EXECUTING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


# Transições válidas (de → conjunto de estados permitidos)
_VALID_TRANSITIONS: Dict[CycleAgentStateEnum, Tuple[CycleAgentStateEnum, ...]] = {
    CycleAgentStateEnum.IDLE: (
        CycleAgentStateEnum.SCANNING,
        CycleAgentStateEnum.SKIPPED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.SCANNING: (
        CycleAgentStateEnum.ANALYZING,
        CycleAgentStateEnum.SKIPPED,
        CycleAgentStateEnum.IDLE,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.ANALYZING: (
        CycleAgentStateEnum.SIGNALING,
        CycleAgentStateEnum.SKIPPED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.SIGNALING: (
        CycleAgentStateEnum.LINTING,
        CycleAgentStateEnum.RISK_CHECK,
        CycleAgentStateEnum.FINISHED,
        CycleAgentStateEnum.SKIPPED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.LINTING: (
        CycleAgentStateEnum.RISK_CHECK,
        CycleAgentStateEnum.FINISHED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.RISK_CHECK: (
        CycleAgentStateEnum.EXECUTING,
        CycleAgentStateEnum.FINISHED,
        CycleAgentStateEnum.SKIPPED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.EXECUTING: (
        CycleAgentStateEnum.FINISHED,
        CycleAgentStateEnum.ERROR,
    ),
    CycleAgentStateEnum.FINISHED: (
        CycleAgentStateEnum.IDLE,  # próximo ciclo
    ),
    CycleAgentStateEnum.ERROR: (
        CycleAgentStateEnum.IDLE,  # recuperação
    ),
    CycleAgentStateEnum.SKIPPED: (
        CycleAgentStateEnum.IDLE,  # próximo ciclo
    ),
}

# Estados terminais do ciclo (indicam que o ciclo acabou)
_TERMINAL_STATES = frozenset({
    CycleAgentStateEnum.FINISHED,
    CycleAgentStateEnum.ERROR,
    CycleAgentStateEnum.SKIPPED,
})


# ---------------------------------------------------------------------------
# StateTransition — registro de uma transição (para histórico)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateTransition:
    """Registro imutável de uma transição de estado."""
    from_state: CycleAgentStateEnum
    to_state: CycleAgentStateEnum
    cycle_id: str
    timestamp: float = field(default_factory=time.monotonic)
    duration_in_prev_s: float = 0.0   # tempo passado no estado anterior


# ---------------------------------------------------------------------------
# SymbolAgentState — estado atual + histórico de um símbolo
# ---------------------------------------------------------------------------

@dataclass
class SymbolAgentState:
    """Estado atual e histórico de transições de um símbolo."""
    symbol: str
    current_state: CycleAgentStateEnum = CycleAgentStateEnum.IDLE
    current_cycle_id: str = ""
    state_entered_at: float = field(default_factory=time.monotonic)
    history: Deque[StateTransition] = field(
        default_factory=lambda: deque(maxlen=20)
    )

    def time_in_current_state_s(self) -> float:
        return time.monotonic() - self.state_entered_at

    def is_terminal(self) -> bool:
        return self.current_state in _TERMINAL_STATES

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "current_state": self.current_state.value,
            "current_cycle_id": self.current_cycle_id,
            "time_in_state_s": round(self.time_in_current_state_s(), 2),
            "is_terminal": self.is_terminal(),
            "last_transitions": [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "cycle_id": t.cycle_id,
                    "duration_prev_s": round(t.duration_in_prev_s, 3),
                }
                for t in list(self.history)[-5:]  # últimas 5 transições
            ],
        }


# ---------------------------------------------------------------------------
# CycleAgentStateMachine
# ---------------------------------------------------------------------------

class CycleAgentStateMachine:
    """
    State machine formal do ciclo de trading por símbolo.

    Padrão OpenHands AgentState:
    - Cada símbolo tem seu próprio estado (multi-símbolo simultâneo)
    - Transições são validadas (fail-silent se inválida)
    - Histórico de transições mantido para auditoria
    - Dashboard pode consultar estado atual de cada símbolo

    Uso:
        machine = get_cycle_agent_state_machine()
        machine.transition("BTC", CycleAgentStateEnum.SCANNING, cycle_id="abc")
        state = machine.get_state("BTC")  # → SCANNING
    """

    def __init__(self) -> None:
        self._states: Dict[str, SymbolAgentState] = {}
        self._total_transitions: int = 0
        self._invalid_transitions: int = 0

    def _get_or_create(self, symbol: str) -> SymbolAgentState:
        sym = symbol.upper()
        if sym not in self._states:
            self._states[sym] = SymbolAgentState(symbol=sym)
        return self._states[sym]

    def transition(
        self,
        symbol: str,
        new_state: CycleAgentStateEnum,
        cycle_id: str = "",
    ) -> bool:
        """
        Transita um símbolo para o novo estado.

        Args:
            symbol:    Símbolo do ativo
            new_state: Novo estado (CycleAgentStateEnum)
            cycle_id:  ID do ciclo atual

        Returns:
            True se a transição foi aplicada, False se inválida (e ignorada).
        """
        try:
            sym_state = self._get_or_create(symbol)
            current = sym_state.current_state

            # Valida transição
            valid_next = _VALID_TRANSITIONS.get(current, ())
            if new_state not in valid_next:
                self._invalid_transitions += 1
                logger.debug(
                    f"[CycleAgentState] invalid transition {symbol}: "
                    f"{current.value} → {new_state.value} (ignored)"
                )
                return False

            # Registra transição
            duration_s = sym_state.time_in_current_state_s()
            transition = StateTransition(
                from_state=current,
                to_state=new_state,
                cycle_id=cycle_id or sym_state.current_cycle_id,
                duration_in_prev_s=duration_s,
            )
            sym_state.history.append(transition)

            # Aplica novo estado
            sym_state.current_state = new_state
            sym_state.current_cycle_id = cycle_id or sym_state.current_cycle_id
            sym_state.state_entered_at = time.monotonic()
            self._total_transitions += 1

            logger.debug(
                f"[CycleAgentState] {symbol}: {current.value} → {new_state.value} "
                f"(was {duration_s:.2f}s in prev)"
            )
            return True

        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[CycleAgentState] transition failed: {exc}")
            return False

    def get_state(self, symbol: str) -> CycleAgentStateEnum:
        """Retorna o estado atual do símbolo."""
        sym = symbol.upper()
        if sym not in self._states:
            return CycleAgentStateEnum.IDLE
        return self._states[sym].current_state

    def get_symbol_state(self, symbol: str) -> Optional[SymbolAgentState]:
        """Retorna o SymbolAgentState completo ou None se não existir."""
        return self._states.get(symbol.upper())

    def reset(self, symbol: str) -> None:
        """Reseta o estado de um símbolo para IDLE."""
        sym = symbol.upper()
        if sym in self._states:
            self._states[sym].current_state = CycleAgentStateEnum.IDLE
            self._states[sym].state_entered_at = time.monotonic()

    def all_states(self) -> List[dict]:
        """Retorna todos os estados (para GET /api/agent-state)."""
        return [s.to_dict() for s in self._states.values()]

    def summary(self) -> dict:
        running = [
            s.symbol for s in self._states.values()
            if s.current_state not in _TERMINAL_STATES
            and s.current_state != CycleAgentStateEnum.IDLE
        ]
        return {
            "total_symbols": len(self._states),
            "total_transitions": self._total_transitions,
            "invalid_transitions": self._invalid_transitions,
            "active_symbols": running,
            "per_symbol": {
                sym: s.current_state.value
                for sym, s in self._states.items()
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_machine: Optional[CycleAgentStateMachine] = None


def get_cycle_agent_state_machine() -> CycleAgentStateMachine:
    """Retorna o singleton global da CycleAgentStateMachine."""
    global _machine
    if _machine is None:
        _machine = CycleAgentStateMachine()
    return _machine


def reset_cycle_agent_state_machine() -> None:
    """Reseta o singleton — para testes."""
    global _machine
    _machine = None
