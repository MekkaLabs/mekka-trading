"""
src/services/sub_agent_delegator.py
=====================================
Story 193 — SubAgentDelegator: delegação de sub-análise isolada (OpenHands AgentDelegate).

Inspirado no padrão OpenHands AgentDelegateAction/AgentDelegateObservation:
  "A parent AgentController spawns a delegate agent to handle a subtask.
   The delegate operates on the same event stream but with its own state
   and iteration tracking. The parent remains passive until the delegate
   completes, then receives an AgentDelegateObservation with outputs."

No OpenHands:
  - parent.start_delegate() cria controller filho com is_delegate=True
  - delegate herda event stream mas tem estado isolado (state.start_id = latest+1)
  - parent.on_event() intercepta eventos e forwarda ao delegate quando ativo
  - delegate retorna AgentDelegateObservation(outputs=state.outputs) ao parent

No Mekka, o equivalente é:
  NickFury delega uma sub-tarefa de análise focada a um VisionDelegate.
  O delegate recebe um prompt específico (ex: "analyze only volume for BTC"),
  roda com contexto isolado (sem memória de ciclos anteriores), retorna um
  DelegateObservation(task, outputs, status, cost_estimated_usd).
  NickFury usa o output do delegate para enriquecer o prompt do Vision principal.

Arquitetura
-----------
  DelegateTask         — especificação da sub-tarefa (task, inputs, agent_type)
  DelegateObservation  — resultado: outputs dict + status + cost
  SubAgentDelegator
    ├── delegate(task, llm_caller) → DelegateObservation  — executa sub-tarefa
    ├── get_recent_observations(symbol, n) → list           — histórico
    └── summary() → dict
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# DelegateStatus
# ---------------------------------------------------------------------------

class DelegateStatus(str, Enum):
    """Estado de conclusão do delegate."""
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    REJECTED = "REJECTED"   # sub-tarefa rejeitada (input inválido)
    TIMEOUT = "TIMEOUT"


# ---------------------------------------------------------------------------
# DelegateTask — especificação (equivalente ao AgentDelegateAction)
# ---------------------------------------------------------------------------

@dataclass
class DelegateTask:
    """
    Especificação de uma sub-tarefa a ser delegada.

    Equivalente ao AgentDelegateAction do OpenHands:
    'Action that triggers delegation, specifies agent type and inputs.'

    Atributos:
        task:       Descrição da tarefa em linguagem natural
        agent_type: Tipo do agente delegado (ex: "volume_analyst", "regime_detector")
        symbol:     Símbolo do ativo
        inputs:     Dict de contexto para o agente (preço, regime, etc.)
        max_tokens: Limite de tokens do output (bounded output)
        cycle_id:   ID do ciclo pai
    """
    task: str
    agent_type: str = "vision_delegate"
    symbol: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 300
    cycle_id: str = ""

    def to_prompt(self) -> str:
        """Formata a task como prompt para o LLM delegate."""
        lines = [f"TASK: {self.task}"]
        if self.symbol:
            lines.append(f"Symbol: {self.symbol}")
        if self.inputs:
            for k, v in self.inputs.items():
                lines.append(f"{k}: {v}")
        lines.append(f"\nAnswer concisely (max {self.max_tokens} tokens).")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "agent_type": self.agent_type,
            "symbol": self.symbol,
            "inputs": self.inputs,
            "max_tokens": self.max_tokens,
            "cycle_id": self.cycle_id,
        }


# ---------------------------------------------------------------------------
# DelegateObservation — resultado (equivalente ao AgentDelegateObservation)
# ---------------------------------------------------------------------------

@dataclass
class DelegateObservation:
    """
    Resultado de uma delegação concluída.

    Equivalente ao AgentDelegateObservation do OpenHands:
    'The observation returned to the parent contains outputs dict + content.'

    Atributos:
        task:               Tarefa delegada
        status:             FINISHED | ERROR | REJECTED | TIMEOUT
        outputs:            Dict de outputs estruturados do delegate
        content:            Resposta texto do LLM delegate (raw output)
        error_msg:          Mensagem de erro se status != FINISHED
        cost_estimated_usd: Custo estimado em USD (0.002 por call)
        latency_ms:         Latência da chamada LLM
        delegate_level:     Profundidade de delegação (0=raiz, 1=primeiro delegate)
    """
    task: DelegateTask
    status: DelegateStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    content: str = ""
    error_msg: str = ""
    cost_estimated_usd: float = 0.002
    latency_ms: float = 0.0
    delegate_level: int = 1

    @property
    def success(self) -> bool:
        return self.status == DelegateStatus.FINISHED

    def to_prompt_block(self) -> str:
        """Formata o resultado para injeção no prompt do Vision principal."""
        if not self.success or not self.content:
            return ""
        return (
            f"=== Sub-Agent Analysis ({self.task.agent_type}) ===\n"
            f"Task: {self.task.task}\n"
            f"Result: {self.content[:500]}\n"  # BoundedOutput: max 500 chars
            f"=== End Sub-Agent Analysis ==="
        )

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "status": self.status.value,
            "outputs": self.outputs,
            "content": self.content[:200] if self.content else "",
            "error_msg": self.error_msg,
            "cost_estimated_usd": self.cost_estimated_usd,
            "latency_ms": round(self.latency_ms, 1),
            "delegate_level": self.delegate_level,
        }


# ---------------------------------------------------------------------------
# SubAgentDelegator
# ---------------------------------------------------------------------------

class SubAgentDelegator:
    """
    Gerencia delegação de sub-tarefas analíticas para agentes especializados.

    Padrão OpenHands AgentDelegate: o agente pai (NickFury) pode delegar
    sub-análises focadas a um delegate que roda com contexto isolado e
    retorna outputs estruturados. O pai recebe a observação e usa no
    próximo prompt.

    O delegate em Mekka é um 'Vision lite': recebe prompt compacto,
    sem memória de ciclos anteriores, retorna análise focada.
    """

    def __init__(
        self,
        max_delegate_level: int = 2,
        max_observations_per_symbol: int = 10,
        default_timeout_s: float = 30.0,
    ) -> None:
        self._max_delegate_level = max_delegate_level
        self._max_obs_per_symbol = max_observations_per_symbol
        self._default_timeout_s = default_timeout_s
        self._observations: Dict[str, deque] = {}
        self._total_delegations: int = 0
        self._total_successes: int = 0
        self._total_errors: int = 0

    def delegate(
        self,
        task: DelegateTask,
        llm_caller: Optional[Callable[[str, int], str]] = None,
        delegate_level: int = 1,
    ) -> DelegateObservation:
        """
        Executa uma sub-tarefa delegada.

        Args:
            task:           Especificação da sub-tarefa
            llm_caller:     Callable(prompt, max_tokens) → str para invocar LLM.
                            Se None, usa fallback stub (para testes).
            delegate_level: Nível de delegação (1=primeiro delegate, 2=sub-delegate)

        Returns:
            DelegateObservation com outputs e status.
        """
        self._total_delegations += 1

        # Rejeita delegação aninhada demais (evita loops infinitos)
        if delegate_level > self._max_delegate_level:
            obs = DelegateObservation(
                task=task,
                status=DelegateStatus.REJECTED,
                error_msg=f"max_delegate_level={self._max_delegate_level} exceeded",
                delegate_level=delegate_level,
            )
            self._total_errors += 1
            self._record(task.symbol, obs)
            return obs

        t0 = time.monotonic()
        prompt = task.to_prompt()

        try:
            if llm_caller is not None:
                content = llm_caller(prompt, task.max_tokens)
            else:
                # Stub para quando não há LLM disponível (testes / dry-run)
                content = f"[stub] Delegate analysis for '{task.task}' — no LLM caller provided."

            latency_ms = (time.monotonic() - t0) * 1000.0
            obs = DelegateObservation(
                task=task,
                status=DelegateStatus.FINISHED,
                outputs={"analysis": content, "agent_type": task.agent_type},
                content=content,
                cost_estimated_usd=0.001,   # delegate usa prompt menor → custo menor
                latency_ms=latency_ms,
                delegate_level=delegate_level,
            )
            self._total_successes += 1
            logger.debug(
                f"[SubAgentDelegator] {task.symbol} agent={task.agent_type} "
                f"level={delegate_level} latency={latency_ms:.0f}ms"
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.monotonic() - t0) * 1000.0
            obs = DelegateObservation(
                task=task,
                status=DelegateStatus.ERROR,
                error_msg=str(exc),
                latency_ms=latency_ms,
                delegate_level=delegate_level,
            )
            self._total_errors += 1
            logger.debug(f"[SubAgentDelegator] delegate failed: {exc}")

        self._record(task.symbol, obs)
        return obs

    def _record(self, symbol: str, obs: DelegateObservation) -> None:
        """Registra observação no histórico."""
        sym = symbol.upper() if symbol else "UNKNOWN"
        if sym not in self._observations:
            self._observations[sym] = deque(maxlen=self._max_obs_per_symbol)
        self._observations[sym].append(obs)

    def get_recent_observations(
        self,
        symbol: str,
        n: int = 3,
    ) -> List[DelegateObservation]:
        """Retorna as N observações mais recentes para o símbolo."""
        sym = symbol.upper()
        obs_deque = self._observations.get(sym, deque())
        return list(obs_deque)[-n:]

    def get_prompt_block(self, symbol: str, n: int = 2) -> str:
        """
        Gera bloco de contexto das últimas N delegações bem-sucedidas.
        Para injeção no prompt Vision principal.
        """
        recent = [o for o in self.get_recent_observations(symbol, n * 2) if o.success]
        recent = recent[-n:]
        if not recent:
            return ""
        blocks = [o.to_prompt_block() for o in recent if o.to_prompt_block()]
        return "\n\n".join(blocks)

    def summary(self) -> dict:
        return {
            "total_delegations": self._total_delegations,
            "total_successes": self._total_successes,
            "total_errors": self._total_errors,
            "symbols_with_history": len(self._observations),
            "success_rate": (
                round(self._total_successes / self._total_delegations, 3)
                if self._total_delegations > 0 else 0.0
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_delegator: Optional[SubAgentDelegator] = None


def get_sub_agent_delegator() -> SubAgentDelegator:
    """Retorna o singleton global do SubAgentDelegator."""
    global _delegator
    if _delegator is None:
        _delegator = SubAgentDelegator()
    return _delegator


def reset_sub_agent_delegator() -> None:
    """Reseta o singleton — para testes."""
    global _delegator
    _delegator = None
