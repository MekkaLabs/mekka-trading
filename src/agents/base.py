"""
src/agents/base.py
==================
Abstract base class for all Mekka Trading agents.

Every agent:
  - Has a codename (maps to AGENTS.md identity)
  - Has a role description
  - Emits structured logs via loguru
  - Is async-first
  - Never raises uncaught exceptions — returns a typed result or raises AgentError
  - May declare an optional execution timeout that prevents a hung agent
    from blocking the orchestrator (issue #74 — agent integration hardening).

Telemetry
---------
On every `run()` invocation the base class publishes a best-effort event on
the global MekkaEventBus so dashboards and breakers can observe degradation:

  - agent.success  → payload: codename, role, elapsed_ms
  - agent.error    → payload: codename, role, elapsed_ms, reason, error_type
  - agent.timeout  → payload: codename, role, elapsed_ms, timeout_s

The publishing is fire-and-forget: failures in the event bus never affect
the agent return value.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from loguru import logger

T = TypeVar("T")


class AgentError(Exception):
    """Raised when an agent fails to produce a valid output."""

    def __init__(self, agent: str, reason: str) -> None:
        self.agent = agent
        self.reason = reason
        super().__init__(f"[{agent}] {reason}")


class AgentTimeoutError(AgentError):
    """Raised when an agent exceeds its declared `timeout_s` budget.

    Subclass of AgentError so existing `except AgentError` paths continue to
    work — callers that want to distinguish hung vs. failed can branch on
    `isinstance(exc, AgentTimeoutError)`.
    """

    def __init__(self, agent: str, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        super().__init__(agent, f"agent timed out after {timeout_s:.1f}s")


class BaseAgent(ABC, Generic[T]):
    """
    Abstract base for all market-analysis and strategy agents.

    Subclasses must implement `_run()`. The public `run()` method
    adds timing, logging, optional timeout enforcement, and error
    normalization on top.

    Parameters
    ----------
    codename : str
        Hero codename (e.g. 'Superman', 'Batman')
    role : str
        Human-readable role description
    timeout_s : float | None
        Optional execution budget. When set, `run()` wraps `_run()` in
        `asyncio.wait_for` and raises ``AgentTimeoutError`` on expiry.
        ``None`` (default) keeps legacy behavior — no enforcement.
    """

    # Last measured runtime in milliseconds — useful for introspection,
    # dashboards, and adaptive timeout tuning. Reset on every run() call.
    def __init__(
        self,
        codename: str,
        role: str,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.codename = codename
        self.role = role
        self.timeout_s = timeout_s
        # Review-fix (2026-06-01): instância, não atributo de classe — evita que
        # todas as instâncias compartilhem o mesmo 0.0 antes do 1º run().
        self._last_elapsed_ms: float = 0.0
        self._log = logger.bind(agent=codename)

    async def run(self, *args: Any, **kwargs: Any) -> T:
        """
        Public entry point. Wraps `_run()` with timing, logging, optional
        timeout enforcement, and best-effort telemetry events.

        Raises:
          AgentTimeoutError: when `timeout_s` is set and expires
          AgentError: for any other failure (always wrapped)
        """
        self._log.info(f"[{self.codename}] starting — {self.role}")
        t0 = time.perf_counter()
        try:
            if self.timeout_s is not None and self.timeout_s > 0:
                result = await asyncio.wait_for(
                    self._run(*args, **kwargs), timeout=self.timeout_s,
                )
            else:
                result = await self._run(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            self._last_elapsed_ms = elapsed
            self._log.success(
                f"[{self.codename}] completed in {elapsed:.0f}ms"
            )
            self._emit_event("agent.success", {"elapsed_ms": elapsed})
            return result
        except asyncio.TimeoutError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._last_elapsed_ms = elapsed
            timeout_s = float(self.timeout_s or 0.0)
            self._log.warning(
                f"[{self.codename}] TIMED OUT after {elapsed:.0f}ms "
                f"(budget {timeout_s:.1f}s)"
            )
            self._emit_event("agent.timeout", {
                "elapsed_ms": elapsed,
                "timeout_s": timeout_s,
            })
            raise AgentTimeoutError(self.codename, timeout_s) from exc
        except asyncio.CancelledError:
            # Review-fix (2026-06-01): defensivo/documental. Cancelamento de task
            # (shutdown do NickFury) NUNCA deve virar AgentError — propaga limpo.
            # (CancelledError já é BaseException e escaparia o except Exception
            # abaixo, mas explicitar evita que um futuro refactor o engula.)
            raise
        except AgentError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._last_elapsed_ms = elapsed
            self._emit_event("agent.error", {
                "elapsed_ms": elapsed,
                "reason": exc.reason,
                "error_type": type(exc).__name__,
            })
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._last_elapsed_ms = elapsed
            self._log.error(
                f"[{self.codename}] failed after {elapsed:.0f}ms — {exc}"
            )
            self._emit_event("agent.error", {
                "elapsed_ms": elapsed,
                "reason": str(exc),
                "error_type": type(exc).__name__,
            })
            raise AgentError(self.codename, str(exc)) from exc

    # ------------------------------------------------------------------
    # Diário de Aprendizado por Agente (2026-06-02)
    # Cada agente escreve e relê suas próprias lições. Só CONSULTIVO:
    # as lições viram contexto, nunca ajustam risco (isso é do Mentor).
    # Ver src/services/agent_learning_journal.py.
    # ------------------------------------------------------------------

    async def learn(
        self,
        lesson: str,
        *,
        category: str = "general",
        evidence: str = "",
        confidence: float = 0.5,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Registra uma lição deste agente (dedup/reforço; espelha no Obsidian).
        Roda em thread para não bloquear o loop. Nunca levanta."""
        try:
            from src.services.agent_learning_journal import record  # noqa: WPS433
            return await asyncio.to_thread(
                record, self.codename, lesson,
                category=category, evidence=evidence,
                confidence=confidence, tags=tags,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[{self.codename}] learn() failed (ignored): {exc}")
            return {"status": "error", "reason": str(exc)}

    async def recall_learnings(
        self,
        query: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Relê as lições mais relevantes deste agente (por reforço×confiança×
        recência). Roda em thread. Nunca levanta — retorna [] em falha."""
        try:
            from src.services.agent_learning_journal import recall  # noqa: WPS433
            return await asyncio.to_thread(
                recall, self.codename, query, limit,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[{self.codename}] recall_learnings() failed: {exc}")
            return []

    def _emit_event(self, topic: str, extra: dict[str, Any]) -> None:
        """Best-effort event publication. Never raises."""
        try:
            from src.services.event_bus import get_event_bus  # noqa: WPS433
            payload: dict[str, Any] = {
                "codename": self.codename,
                "role": self.role,
            }
            payload.update(extra)
            get_event_bus().publish_sync(topic, payload)
        except Exception:  # noqa: BLE001
            pass  # telemetry must never break the agent

    @abstractmethod
    async def _run(self, *args: Any, **kwargs: Any) -> T:
        """Core agent logic. Must be implemented by every subclass."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} codename={self.codename!r}>"
