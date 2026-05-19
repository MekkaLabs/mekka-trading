"""
src/services/cycle_graph_interrupt.py
=======================================
Story 212 — CycleGraphInterrupt: mecanismo de pause/resume do pipeline
Mekka, inspirado no LangGraph interrupt / Human-in-the-Loop.

Inspirado no padrão LangGraph Human-in-the-Loop:
(langchain-ai/langgraph):
  "Human-in-the-loop enables pausing graph execution before or after
   specific nodes to allow human review and approval.
   interrupt() raises an Interrupt exception that pauses the graph.
   The graph can be resumed via Command(resume=value).
   Example:
     from langgraph.types import interrupt, Command
     def review_node(state):
         approval = interrupt({'signal': state['signal']})
         if approval != 'yes':
             return {'signal': {**state['signal'], 'action': 'HOLD'}}
         return state
     # Resume:
     graph.invoke(Command(resume='yes'), config={'thread_id': 'x'})"

No Mekka:
  CycleGraphInterrupt implementa o padrão interrupt/resume para o pipeline.
  Antes de o IronMan executar uma ordem real, o sistema pode pausar e
  aguardar aprovação manual (via Telegram, dashboard, ou timeout automático).

  Estados possíveis de um interrupt:
  PENDING  — aguardando decisão humana
  APPROVED — aprovado → continua execução
  REJECTED — rejeitado → força HOLD
  TIMEOUT  — expirou → comportamento configurável (auto-approve ou force-HOLD)
  SKIPPED  — interrupt não aplicável (paper trading, confidence < threshold)

Arquitetura
-----------
  InterruptStatus     — enum de estados
  InterruptRecord     — registro de um interrupt pendente/resolvido
  CycleGraphInterrupt
    ├── request(cycle_id, node_name, signal, timeout_s) → interrupt_id
    ├── resolve(interrupt_id, decision, reason) → bool
    ├── check(interrupt_id) → InterruptStatus
    ├── get(interrupt_id) → InterruptRecord | None
    ├── auto_expire_pending() → int   (expira pendentes vencidos)
    └── summary() → dict
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# InterruptStatus
# ---------------------------------------------------------------------------

class InterruptStatus(str, Enum):
    PENDING  = "pending"   # aguardando decisão humana
    APPROVED = "approved"  # aprovado → executa
    REJECTED = "rejected"  # rejeitado → força HOLD
    TIMEOUT  = "timeout"   # expirou sem decisão
    SKIPPED  = "skipped"   # interrupt não aplicável


# ---------------------------------------------------------------------------
# InterruptRecord
# ---------------------------------------------------------------------------

@dataclass
class InterruptRecord:
    """
    Registro completo de um interrupt de execução.

    interrupt_id: UUID do interrupt
    cycle_id:     ciclo que gerou o interrupt
    node_name:    nó onde o pipeline pausou (geralmente "ironman")
    signal:       sinal pendente de aprovação
    status:       estado atual do interrupt
    timeout_at:   timestamp monotonic de expiração
    resolved_at:  quando foi resolvido (None se ainda pendente)
    decision:     "approved" | "rejected" (None se não resolvido)
    reason:       motivo da decisão (opcional)
    on_timeout:   "approve" ou "reject" — comportamento padrão ao expirar
    """
    interrupt_id: str
    cycle_id: str
    node_name: str
    signal: Dict[str, Any]
    timeout_at: float
    on_timeout: str = "reject"  # "approve" | "reject"
    status: InterruptStatus = InterruptStatus.PENDING
    created_at: float = field(default_factory=time.monotonic)
    resolved_at: Optional[float] = None
    decision: Optional[str] = None
    reason: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return (
            self.status == InterruptStatus.PENDING
            and time.monotonic() > self.timeout_at
        )

    @property
    def remaining_s(self) -> float:
        """Segundos restantes até expirar (negativo se já expirou)."""
        return self.timeout_at - time.monotonic()

    def to_dict(self) -> dict:
        return {
            "interrupt_id": self.interrupt_id,
            "cycle_id": self.cycle_id,
            "node_name": self.node_name,
            "signal": self.signal,
            "status": self.status.value,
            "created_at": self.created_at,
            "timeout_at": self.timeout_at,
            "remaining_s": round(self.remaining_s, 1),
            "resolved_at": self.resolved_at,
            "decision": self.decision,
            "reason": self.reason,
            "on_timeout": self.on_timeout,
        }


# ---------------------------------------------------------------------------
# CycleGraphInterrupt
# ---------------------------------------------------------------------------

class CycleGraphInterrupt:
    """
    Gerenciador de interrupts Human-in-the-Loop para o pipeline Mekka.

    Equivalente ao interrupt() + Command(resume=...) do LangGraph.

    Uso típico no NickFury (modo live, não paper):
        interrupt_mgr = get_cycle_graph_interrupt()

        # Antes do IronMan executar:
        interrupt_id = interrupt_mgr.request(
            cycle_id=cycle_id,
            node_name='ironman',
            signal=signal,
            timeout_s=60,
            on_timeout='reject',
        )

        # Aguarda resolução ou timeout (polling):
        final_status = interrupt_mgr.wait_for_resolution(interrupt_id, poll_interval=1.0)
        if final_status == InterruptStatus.APPROVED:
            # executa a ordem
        else:
            signal['action'] = 'HOLD'  # cancela execução

    Resolução via dashboard/Telegram:
        interrupt_mgr.resolve(interrupt_id, decision='approved', reason='manual ok')
    """

    def __init__(self, default_timeout_s: float = 120.0) -> None:
        self._default_timeout_s = default_timeout_s
        self._records: Dict[str, InterruptRecord] = {}

    def request(
        self,
        cycle_id: str,
        node_name: str,
        signal: Dict[str, Any],
        timeout_s: Optional[float] = None,
        on_timeout: str = "reject",
    ) -> str:
        """
        Cria um interrupt pendente e retorna o interrupt_id.

        Args:
            cycle_id:   ciclo atual
            node_name:  nó que está pausando (ex: "ironman")
            signal:     sinal pendente de aprovação
            timeout_s:  segundos até expirar (usa default se None)
            on_timeout: "approve" ou "reject" quando expirar

        Returns:
            interrupt_id — ID único do interrupt criado
        """
        interrupt_id = str(uuid.uuid4())[:12]
        timeout = time.monotonic() + (timeout_s or self._default_timeout_s)

        record = InterruptRecord(
            interrupt_id=interrupt_id,
            cycle_id=cycle_id,
            node_name=node_name,
            signal=dict(signal),
            timeout_at=timeout,
            on_timeout=on_timeout,
        )
        self._records[interrupt_id] = record
        logger.info(
            "[CycleGraphInterrupt] interrupt created %s — cycle=%s node=%s action=%s timeout=%.0fs",
            interrupt_id, cycle_id[:8], node_name,
            signal.get("action", "?"), timeout_s or self._default_timeout_s,
        )
        return interrupt_id

    def resolve(
        self,
        interrupt_id: str,
        decision: str,
        reason: str = "",
    ) -> bool:
        """
        Resolve um interrupt com a decisão humana.

        Args:
            interrupt_id: ID do interrupt
            decision:     "approved" ou "rejected"
            reason:       motivo da decisão (log/audit)

        Returns:
            True se resolvido com sucesso, False se não encontrado ou
            já resolvido.
        """
        record = self._records.get(interrupt_id)
        if record is None:
            logger.debug("[CycleGraphInterrupt] interrupt not found: %s", interrupt_id)
            return False
        if record.status != InterruptStatus.PENDING:
            logger.debug(
                "[CycleGraphInterrupt] interrupt %s already resolved: %s",
                interrupt_id, record.status,
            )
            return False

        record.decision = decision
        record.reason = reason
        record.resolved_at = time.monotonic()
        record.status = (
            InterruptStatus.APPROVED
            if decision == "approved"
            else InterruptStatus.REJECTED
        )
        logger.info(
            "[CycleGraphInterrupt] interrupt %s resolved → %s (%s)",
            interrupt_id, record.status.value, reason or "—",
        )
        return True

    def check(self, interrupt_id: str) -> InterruptStatus:
        """
        Verifica o status atual de um interrupt.

        Aplica timeout automaticamente se já expirou.
        """
        record = self._records.get(interrupt_id)
        if record is None:
            return InterruptStatus.SKIPPED
        if record.status == InterruptStatus.PENDING and record.is_expired:
            self._apply_timeout(record)
        return record.status

    def get(self, interrupt_id: str) -> Optional[InterruptRecord]:
        """Retorna o registro completo de um interrupt."""
        return self._records.get(interrupt_id)

    def list_pending(self) -> List[InterruptRecord]:
        """Lista todos os interrupts pendentes (não expirados)."""
        now = time.monotonic()
        return [
            r for r in self._records.values()
            if r.status == InterruptStatus.PENDING and now <= r.timeout_at
        ]

    def auto_expire_pending(self) -> int:
        """
        Expira todos os interrupts PENDING vencidos.

        Retorna o número de interrupts expirados.
        """
        expired = 0
        for record in list(self._records.values()):
            if record.status == InterruptStatus.PENDING and record.is_expired:
                self._apply_timeout(record)
                expired += 1
        if expired:
            logger.info("[CycleGraphInterrupt] auto-expired %d interrupts", expired)
        return expired

    def wait_for_resolution(
        self,
        interrupt_id: str,
        poll_interval: float = 1.0,
        max_wait_s: Optional[float] = None,
    ) -> InterruptStatus:
        """
        Bloqueia até o interrupt ser resolvido, aprovado, rejeitado ou expirado.

        Versão síncrona (usa time.sleep — não usar dentro de async).
        Para uso assíncrono veja wait_for_resolution_async().
        """
        import time as _time  # noqa: WPS433
        deadline = _time.monotonic() + (max_wait_s or self._default_timeout_s + 10)
        while _time.monotonic() < deadline:
            status = self.check(interrupt_id)
            if status != InterruptStatus.PENDING:
                return status
            _time.sleep(poll_interval)
        return self.check(interrupt_id)

    async def wait_for_resolution_async(
        self,
        interrupt_id: str,
        poll_interval: float = 1.0,
    ) -> InterruptStatus:
        """
        Aguarda resolução do interrupt de forma assíncrona (asyncio).
        """
        import asyncio as _asyncio  # noqa: WPS433
        while True:
            status = self.check(interrupt_id)
            if status != InterruptStatus.PENDING:
                return status
            await _asyncio.sleep(poll_interval)

    def summary(self) -> dict:
        counts = {s.value: 0 for s in InterruptStatus}
        for r in self._records.values():
            counts[r.status.value] += 1
        return {
            "total_interrupts": len(self._records),
            "by_status": counts,
            "pending_count": counts["pending"],
        }

    def _apply_timeout(self, record: InterruptRecord) -> None:
        """Aplica o comportamento de timeout configurado."""
        record.resolved_at = time.monotonic()
        if record.on_timeout == "approve":
            record.status = InterruptStatus.APPROVED
            record.decision = "approved"
            record.reason = "auto-approved on timeout"
        else:
            record.status = InterruptStatus.TIMEOUT
            record.decision = "rejected"
            record.reason = "timeout — auto-rejected"
        logger.warning(
            "[CycleGraphInterrupt] timeout %s → %s",
            record.interrupt_id, record.status.value,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_interrupt_mgr: Optional[CycleGraphInterrupt] = None


def get_cycle_graph_interrupt(default_timeout_s: float = 120.0) -> CycleGraphInterrupt:
    """Retorna o singleton global do CycleGraphInterrupt."""
    global _interrupt_mgr
    if _interrupt_mgr is None:
        _interrupt_mgr = CycleGraphInterrupt(default_timeout_s=default_timeout_s)
    return _interrupt_mgr


def reset_cycle_graph_interrupt() -> None:
    """Reseta o singleton — para testes."""
    global _interrupt_mgr
    _interrupt_mgr = None
