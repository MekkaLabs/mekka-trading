"""
src/services/degraded_mode.py
==============================
Story 140 — DEGRADED_MODE formal.

Quando dependências críticas (LLM, exchange) ficam instáveis, o sistema entra
em modo degradado: zero novas entradas, apenas gestão de saídas determinísticas
(SL/TP de posições existentes via Cyclops/Wolverine).

Arquitetura
-----------
`DegradedModeManager` é um singleton stateful com as seguintes transições:

    NORMAL ─── trigger(reason) ──→ DEGRADED
    DEGRADED ─ observe(success) ─→ NORMAL  (após `recovery_cycles` consecutivos)
    DEGRADED ─ trigger(reason)  ──→ DEGRADED (resets recovery counter)

NickFury verifica `is_degraded` no início de cada `_cycle_for_symbol()`.
Em DEGRADED_MODE: retorna CycleReport.error imediatamente, sem chamar Vision/Batman/IronMan.
Posições existentes continuam sendo monitoradas pelo ciclo de monitor (Cyclops/Wolverine).

Eventos publicados
------------------
  - `system.degraded`  → quando entra em modo degradado
  - `system.recovered` → quando sai do modo degradado
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from loguru import logger


@dataclass
class DegradedModeManager:
    """
    Gerencia o estado NORMAL ↔ DEGRADED do sistema.

    Thread-safe para asyncio single event loop.
    """

    # Número de ciclos consecutivos SEM erro necessários para recovery
    recovery_cycles: int = 5

    # Estado interno
    _degraded: bool = field(default=False, init=False)
    _reason: str = field(default="", init=False)
    _entered_at: Optional[datetime] = field(default=None, init=False)
    _consecutive_successes: int = field(default=0, init=False)
    _trigger_count: int = field(default=0, init=False)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def trigger(self, reason: str) -> bool:
        """
        Entra em DEGRADED_MODE. Retorna True se foi transição NORMAL → DEGRADED
        (False se já estava degradado — apenas atualiza o reason).
        """
        was_normal = not self._degraded
        self._degraded = True
        self._reason = reason
        self._consecutive_successes = 0  # reset recovery counter
        if was_normal:
            # Only count on actual NORMAL → DEGRADED transitions.
            # Re-triggering while already DEGRADED updates the reason and
            # resets the recovery counter — it is NOT a new activation.
            self._trigger_count += 1
            self._entered_at = datetime.now(timezone.utc)
            logger.warning(
                f"[DegradedMode] ENTERING DEGRADED_MODE: {reason}"
            )
        return was_normal

    def observe_success(self) -> bool:
        """
        Registra um ciclo bem-sucedido. Retorna True se esta observação
        completou o recovery (transição DEGRADED → NORMAL).
        """
        if not self._degraded:
            return False
        self._consecutive_successes += 1
        if self._consecutive_successes >= self.recovery_cycles:
            self._degraded = False
            elapsed = ""
            if self._entered_at:
                delta = datetime.now(timezone.utc) - self._entered_at
                elapsed = f" (after {delta.total_seconds():.0f}s)"
            logger.info(
                f"[DegradedMode] RECOVERED from DEGRADED_MODE{elapsed} "
                f"after {self._consecutive_successes} successful cycles"
            )
            self._entered_at = None
            self._reason = ""
            self._consecutive_successes = 0
            return True
        logger.debug(
            f"[DegradedMode] Recovery progress: "
            f"{self._consecutive_successes}/{self.recovery_cycles}"
        )
        return False

    def observe_failure(self, reason: str = "") -> None:
        """Registra falha — reseta contador de recovery."""
        if self._degraded:
            self._consecutive_successes = 0
            if reason:
                self._reason = reason

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_degraded(self) -> bool:
        """True quando o sistema está em DEGRADED_MODE."""
        return self._degraded

    @property
    def reason(self) -> str:
        """Motivo da degradação atual (string vazia se NORMAL)."""
        return self._reason

    @property
    def recovery_progress(self) -> str:
        """Progresso de recovery: '2/5' ou 'N/A'."""
        if not self._degraded:
            return "N/A"
        return f"{self._consecutive_successes}/{self.recovery_cycles}"

    @property
    def trigger_count(self) -> int:
        """Total de vezes que o modo degradado foi ativado nesta sessão."""
        return self._trigger_count

    def summary(self) -> str:
        if self._degraded:
            return (
                f"[DegradedMode] DEGRADED — reason={self._reason!r} "
                f"recovery={self.recovery_progress} "
                f"triggers={self._trigger_count}"
            )
        return f"[DegradedMode] NORMAL (triggers_lifetime={self._trigger_count})"


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_manager: Optional[DegradedModeManager] = None


def get_degraded_mode_manager(recovery_cycles: int = 5) -> DegradedModeManager:
    """
    Retorna o singleton global do DegradedModeManager.
    `recovery_cycles` é usado apenas na primeira criação.
    """
    global _manager
    if _manager is None:
        _manager = DegradedModeManager(recovery_cycles=recovery_cycles)
    return _manager


def reset_degraded_mode_manager() -> None:
    """Reseta o singleton — para testes."""
    global _manager
    _manager = None
