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
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from loguru import logger

T = TypeVar("T")


class AgentError(Exception):
    """Raised when an agent fails to produce a valid output."""

    def __init__(self, agent: str, reason: str) -> None:
        self.agent = agent
        self.reason = reason
        super().__init__(f"[{agent}] {reason}")


class BaseAgent(ABC, Generic[T]):
    """
    Abstract base for all market-analysis and strategy agents.

    Subclasses must implement `_run()`. The public `run()` method
    adds timing, logging, and error normalization on top.

    Parameters
    ----------
    codename : str
        Hero codename (e.g. 'Superman', 'Batman')
    role : str
        Human-readable role description
    """

    def __init__(self, codename: str, role: str) -> None:
        self.codename = codename
        self.role = role
        self._log = logger.bind(agent=codename)

    async def run(self, *args: Any, **kwargs: Any) -> T:
        """
        Public entry point. Wraps `_run()` with timing and logging.
        Re-raises `AgentError`; wraps any other exception.
        """
        self._log.info(f"[{self.codename}] starting — {self.role}")
        t0 = time.perf_counter()
        try:
            result = await self._run(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            self._log.success(
                f"[{self.codename}] completed in {elapsed:.0f}ms"
            )
            return result
        except AgentError:
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._log.error(
                f"[{self.codename}] failed after {elapsed:.0f}ms — {exc}"
            )
            raise AgentError(self.codename, str(exc)) from exc

    @abstractmethod
    async def _run(self, *args: Any, **kwargs: Any) -> T:
        """Core agent logic. Must be implemented by every subclass."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} codename={self.codename!r}>"
