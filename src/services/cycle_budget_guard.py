"""
src/services/cycle_budget_guard.py
========================================
Story 189 — CycleBudgetGuard: limite de custo LLM por sessão de trading.

Inspirado no padrão SWE-agent max_cost + done_status:
  "Setting token and cost budgets per agent run prevents runaway spending.
   The Agent tracks total_cost, checks it against max_cost, and sets
   done_status='exit_cost' when the limit is exceeded — exiting the loop
   gracefully rather than crashing."

No SWE-agent, o agente sai do loop quando `total_cost > max_cost` ou
`steps > max_steps`, emitindo `done_status="exit_cost"` ou `"exit_iterations"`.

No Mekka, o equivalente é: se o custo acumulado de LLM calls (Vision) exceder
o budget configurado por sessão, o NickFury força HOLD ao invés de chamar
Vision — economizando custo sem parar o sistema. O ciclo continua mas o
Vision fica em "modo econômico" até o reset do budget (diário ou manual).

Analogia financeira:
  Budget LLM = stop-loss do custo operacional. Assim como o Batman protege
  o capital com gates de risco, o CycleBudgetGuard protege o custo de API.

Arquitetura
-----------
  BudgetSession — sessão com custo acumulado, início e status
  CycleBudgetGuard
    ├── record_cost(symbol, estimated_cost_usd, cycle_id)
    ├── should_skip_vision(symbol) → (bool, str)
    ├── reset(symbol) — reset manual do budget
    ├── reset_all() — reset geral (ex: diário)
    └── summary() → dict

Uso em NickFury (antes de Vision)
----------------------------------
    from src.services.cycle_budget_guard import get_cycle_budget_guard

    _bgd = get_cycle_budget_guard()
    _skip_v, _skip_reason_v = _bgd.should_skip_vision(symbol)
    if _skip_v:
        signal = _make_hold_signal(symbol)
    else:
        signal = await self._vision.run(analysis=analysis)
        _bgd.record_cost(symbol, estimated_cost_usd=0.002)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# BudgetSession
# ---------------------------------------------------------------------------

@dataclass
class BudgetSession:
    """
    Sessão de budget LLM por símbolo.
    Equivale ao `total_cost` + `done_status` do SWE-agent Agent.
    """
    symbol: str
    total_cost_usd: float = 0.0
    total_calls: int = 0
    session_start: float = field(default_factory=time.monotonic)
    budget_exceeded_at: Optional[float] = None

    @property
    def age_hours(self) -> float:
        return (time.monotonic() - self.session_start) / 3600.0

    @property
    def is_exceeded(self) -> bool:
        return self.budget_exceeded_at is not None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_calls": self.total_calls,
            "age_hours": round(self.age_hours, 2),
            "is_exceeded": self.is_exceeded,
        }


# ---------------------------------------------------------------------------
# CycleBudgetGuard
# ---------------------------------------------------------------------------

class CycleBudgetGuard:
    """
    Guarda de custo LLM — força HOLD quando budget da sessão é excedido.

    Padrão SWE-agent max_cost: o agente rastreia custo acumulado e sai do
    loop graciosamente ao invés de crashar. Aqui: ao invés de "sair", o
    NickFury emite HOLD sem chamar Vision.
    """

    def __init__(
        self,
        max_cost_usd_per_session: float = 1.0,    # USD por sessão
        max_calls_per_session: int = 500,           # chamadas Vision por sessão
        auto_reset_hours: float = 24.0,             # reset automático após N horas
    ) -> None:
        self._sessions: Dict[str, BudgetSession] = {}
        self._global_session: BudgetSession = BudgetSession(symbol="__global__")
        self._max_cost_usd = max_cost_usd_per_session
        self._max_calls = max_calls_per_session
        self._auto_reset_hours = auto_reset_hours
        self._total_skipped: int = 0

    def _get_or_create(self, symbol: str) -> BudgetSession:
        sym = symbol.upper()
        if sym not in self._sessions:
            self._sessions[sym] = BudgetSession(symbol=sym)
        session = self._sessions[sym]
        # Auto-reset se sessão muito antiga
        if session.age_hours >= self._auto_reset_hours:
            logger.debug(f"[CycleBudgetGuard] auto-reset session for {sym} after {session.age_hours:.1f}h")
            self._sessions[sym] = BudgetSession(symbol=sym)
        return self._sessions[sym]

    def record_cost(
        self,
        symbol: str,
        estimated_cost_usd: float = 0.002,
        cycle_id: str = "",
    ) -> BudgetSession:
        """
        Registra custo de uma chamada Vision para o símbolo.

        Args:
            symbol: símbolo do ativo
            estimated_cost_usd: custo estimado em USD (default 0.002 = ~0.2¢ por call GPT-4o-mini)
            cycle_id: ID do ciclo (para log)

        Returns:
            BudgetSession atualizada.
        """
        sym = symbol.upper()
        session = self._get_or_create(sym)
        session.total_cost_usd += estimated_cost_usd
        session.total_calls += 1

        self._global_session.total_cost_usd += estimated_cost_usd
        self._global_session.total_calls += 1

        # Verifica se excedeu algum limite
        cost_exceeded = session.total_cost_usd > self._max_cost_usd
        calls_exceeded = session.total_calls > self._max_calls

        if (cost_exceeded or calls_exceeded) and not session.is_exceeded:
            session.budget_exceeded_at = time.monotonic()
            reason = (
                f"cost={session.total_cost_usd:.4f}>{self._max_cost_usd}"
                if cost_exceeded
                else f"calls={session.total_calls}>{self._max_calls}"
            )
            logger.warning(
                f"[CycleBudgetGuard] {sym} budget exceeded: {reason} "
                f"(cycle={cycle_id})"
            )

        logger.debug(
            f"[CycleBudgetGuard] {sym} cost={session.total_cost_usd:.4f} "
            f"calls={session.total_calls}"
        )
        return session

    def should_skip_vision(self, symbol: str) -> Tuple[bool, str]:
        """
        Decide se Vision deve ser pulado por excesso de custo.

        Equivale ao `done_status = 'exit_cost'` do SWE-agent.
        Aqui: ao invés de sair, retorna skip=True para forçar HOLD.

        Returns:
            (should_skip: bool, reason: str)
        """
        sym = symbol.upper()
        session = self._get_or_create(sym)

        if not session.is_exceeded:
            return False, "budget_ok"

        self._total_skipped += 1
        return True, (
            f"budget_exceeded("
            f"cost={session.total_cost_usd:.4f}>{self._max_cost_usd}, "
            f"calls={session.total_calls})"
        )

    def reset(self, symbol: str) -> bool:
        """Reset manual do budget de um símbolo. Retorna True se existia."""
        sym = symbol.upper()
        existed = sym in self._sessions
        if existed:
            self._sessions[sym] = BudgetSession(symbol=sym)
            logger.info(f"[CycleBudgetGuard] reset budget for {sym}")
        return existed

    def reset_all(self) -> int:
        """Reset global de todos os budgets (ex: chamada diária). Retorna número de resets."""
        count = len(self._sessions)
        self._sessions.clear()
        self._global_session = BudgetSession(symbol="__global__")
        logger.info(f"[CycleBudgetGuard] reset all {count} sessions")
        return count

    def summary(self) -> dict:
        return {
            "total_symbols": len(self._sessions),
            "total_skipped": self._total_skipped,
            "max_cost_usd": self._max_cost_usd,
            "max_calls": self._max_calls,
            "auto_reset_hours": self._auto_reset_hours,
            "global": self._global_session.to_dict(),
            "sessions": {sym: s.to_dict() for sym, s in self._sessions.items()},
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_guard: Optional[CycleBudgetGuard] = None


def get_cycle_budget_guard() -> CycleBudgetGuard:
    """Retorna o singleton global do CycleBudgetGuard."""
    global _guard
    if _guard is None:
        try:
            from src.config.settings import settings
            max_cost = float(getattr(settings, "llm_budget_max_cost_usd", 1.0))
            max_calls = int(getattr(settings, "llm_budget_max_calls", 500))
            reset_h = float(getattr(settings, "llm_budget_reset_hours", 24.0))
        except Exception:  # noqa: BLE001
            max_cost, max_calls, reset_h = 1.0, 500, 24.0
        _guard = CycleBudgetGuard(
            max_cost_usd_per_session=max_cost,
            max_calls_per_session=max_calls,
            auto_reset_hours=reset_h,
        )
    return _guard


def reset_cycle_budget_guard() -> None:
    """Reseta o singleton — para testes."""
    global _guard
    _guard = None
