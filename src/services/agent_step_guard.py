"""
src/services/agent_step_guard.py
=================================
Story 155 — AgentStepGuard: MAX_ITERATIONS + Stuck Loop Detection + Graceful Recovery.

Inspirado em dois mecanismos do OpenHands (OpenHands/OpenHands):

1. **MAX_ITERATIONS guard**
   "Cost ceilings include MAX_ITERATIONS (default ~100 in OpenHands),
    LLM_NUM_RETRIES (default 8), and a hard accumulated-cost cutoff
    that aborts the conversation."

2. **Stuck agent recovery (PR #5500)**
   "A recovery mechanism replaces hard errors (RuntimeError) with a
    graceful error state transition, implements recovery that allows
    new messages to be processed, and properly resets all relevant
    state variables when recovering. The changes allow users to
    continue interacting with the agent even after it gets stuck in a loop."

Problema resolvido no Mekka Trading:
- Ciclos que entram em loop (mesmo erro repetido N vezes)
- Ciclos que demoram demais sem terminar
- RuntimeError que derrubava o executor ao invés de sinalizar DEGRADED_MODE

Design:
  AgentStepGuard  — guarda um ciclo específico (reset por símbolo)
  NickFuryStepGuard — helper factory + contador global de stuck events
  StepGuardFilter  — InvocationFilter adapter (integra com Story 152)

Uso típico em NickFury._cycle_for_symbol():
    guard = NickFuryStepGuard.for_cycle(symbol, cycle_id)

    # Após cada etapa do pipeline:
    _, should_abort = guard.check("vision.analyze", result=signal)
    if should_abort:
        NickFuryStepGuard.record_stuck_event()
        get_degraded_mode_manager().trigger("agent_stuck_loop")
        return CycleReport(symbol=symbol, error="STEP_GUARD_ABORT")
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# StepRecord — immutable snapshot of one pipeline step
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepRecord:
    """
    Immutable record of one agent step.

    `result_hash` is an 8-char MD5 prefix of the result/error
    representation, used for stuck-loop detection (same hash N times
    in a row = stuck).
    """
    step_number: int
    function_name: str
    result_hash: str
    timestamp: float = field(default_factory=time.monotonic)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step_number,
            "fn": self.function_name,
            "hash": self.result_hash,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# AgentStepGuard — per-cycle guard
# ---------------------------------------------------------------------------

class AgentStepGuard:
    """
    Per-cycle step guard.

    Tracks how many steps the agent has taken, detects stuck loops,
    and signals when to abort gracefully (instead of raising RuntimeError).

    The guard is stateful and meant to be instantiated once per
    `_cycle_for_symbol()` call via `NickFuryStepGuard.for_cycle()`.

    Stuck loop detection algorithm:
      If the last `stuck_threshold` steps all have the same `result_hash`,
      the agent is producing identical outputs → stuck loop → abort.
    """

    def __init__(
        self,
        max_iterations: int = 100,
        stuck_threshold: int = 5,
        session_id: str = "",
    ) -> None:
        self._max_iterations = max_iterations
        self._stuck_threshold = stuck_threshold
        self._session_id = session_id
        self._steps: list[StepRecord] = []
        self._started_at = time.monotonic()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_result(value: Any) -> str:
        """Stable 8-char hash of any Python value."""
        try:
            raw = json.dumps(value, sort_keys=True, default=str)
        except Exception:
            raw = str(value)
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    # ------------------------------------------------------------------
    # Step recording
    # ------------------------------------------------------------------

    def record_step(
        self,
        function_name: str,
        result: Any = None,
        error: Optional[str] = None,
    ) -> StepRecord:
        """Record one pipeline step. Returns the immutable StepRecord."""
        step_num = len(self._steps) + 1
        result_hash = self._hash_result(error if error is not None else result)
        record = StepRecord(
            step_number=step_num,
            function_name=function_name,
            result_hash=result_hash,
            error=error,
        )
        self._steps.append(record)
        return record

    def check(
        self,
        function_name: str,
        result: Any = None,
        error: Optional[str] = None,
    ) -> tuple[StepRecord, bool]:
        """
        Record a step and check whether the agent should abort.

        Returns:
            (StepRecord, should_abort: bool)

        `should_abort` is True when:
        - MAX_ITERATIONS exceeded, OR
        - Stuck loop detected (same result hash `stuck_threshold` times)

        Following OpenHands' graceful recovery: the caller is responsible
        for transitioning to DEGRADED_MODE or returning an error CycleReport,
        NOT for raising an exception.
        """
        record = self.record_step(function_name, result, error)

        if self.is_max_iterations_exceeded():
            logger.warning(
                f"[AgentStepGuard] MAX_ITERATIONS ({self._max_iterations}) reached "
                f"— session={self._session_id} steps={len(self._steps)}"
            )
            return record, True

        if self.is_stuck():
            logger.warning(
                f"[AgentStepGuard] Stuck loop — same result hash "
                f"{self._stuck_threshold}× in a row "
                f"— session={self._session_id} fn={function_name} "
                f"hash={record.result_hash}"
            )
            return record, True

        return record, False

    # ------------------------------------------------------------------
    # Status checks
    # ------------------------------------------------------------------

    def is_max_iterations_exceeded(self) -> bool:
        """True when step count reached or exceeded MAX_ITERATIONS."""
        return len(self._steps) >= self._max_iterations

    def is_stuck(self) -> bool:
        """
        True when the last `stuck_threshold` steps all have identical result hashes.

        Identical hashes indicate the pipeline is producing the same
        output repeatedly — the OpenHands definition of a stuck loop.
        """
        if len(self._steps) < self._stuck_threshold:
            return False
        recent = self._steps[-self._stuck_threshold:]
        hashes = {s.result_hash for s in recent}
        return len(hashes) == 1  # all identical = stuck

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset step history (reuse guard across sub-cycles)."""
        self._steps.clear()
        self._started_at = time.monotonic()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def step_count(self) -> int:
        return len(self._steps)

    @property
    def max_iterations(self) -> int:
        return self._max_iterations

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self._started_at

    def summary(self) -> dict[str, Any]:
        """For GET /api/step-guard endpoint or logging."""
        return {
            "session_id": self._session_id,
            "step_count": self.step_count,
            "max_iterations": self._max_iterations,
            "stuck_threshold": self._stuck_threshold,
            "is_max_exceeded": self.is_max_iterations_exceeded(),
            "is_stuck": self.is_stuck(),
            "elapsed_s": round(self.elapsed_s, 3),
            "recent_steps": [s.to_dict() for s in self._steps[-20:]],
        }


# ---------------------------------------------------------------------------
# NickFuryStepGuard — factory + global stuck event counter
# ---------------------------------------------------------------------------

class NickFuryStepGuard:
    """
    Factory for per-cycle AgentStepGuard instances + global stuck counter.

    Usage in NickFury._cycle_for_symbol():

        guard = NickFuryStepGuard.for_cycle(symbol, cycle_id)
        ...
        _, should_abort = guard.check("vision", result=signal)
        if should_abort:
            NickFuryStepGuard.record_stuck_event()
            # trigger graceful recovery
            ...
    """

    _global_stuck_count: int = 0
    _global_max_exceeded_count: int = 0

    @classmethod
    def for_cycle(
        cls,
        symbol: str,
        cycle_id: str = "",
    ) -> AgentStepGuard:
        """Create a fresh AgentStepGuard for one cycle pass."""
        # Lazy import to avoid circular deps with settings
        try:
            from src.config.settings import settings  # noqa: WPS433
            max_iter = getattr(settings, "agent_max_step_iterations", 100)
            stuck_thr = getattr(settings, "agent_stuck_threshold", 5)
        except Exception:
            max_iter = 100
            stuck_thr = 5

        return AgentStepGuard(
            max_iterations=max_iter,
            stuck_threshold=stuck_thr,
            session_id=f"{symbol}:{cycle_id}",
        )

    @classmethod
    def record_stuck_event(cls) -> None:
        """Increment global stuck-loop counter (for monitoring)."""
        cls._global_stuck_count += 1

    @classmethod
    def record_max_exceeded(cls) -> None:
        """Increment global max-iterations counter (for monitoring)."""
        cls._global_max_exceeded_count += 1

    @classmethod
    def global_summary(cls) -> dict[str, int]:
        return {
            "global_stuck_count": cls._global_stuck_count,
            "global_max_exceeded_count": cls._global_max_exceeded_count,
        }

    @classmethod
    def reset_global(cls) -> None:
        """Reset counters — used in tests."""
        cls._global_stuck_count = 0
        cls._global_max_exceeded_count = 0


# ---------------------------------------------------------------------------
# StepGuardFilter — InvocationFilter adapter (Story 152 integration)
# ---------------------------------------------------------------------------

class StepGuardFilter:
    """
    Adapter that wraps AgentStepGuard as an InvocationFilter-compatible object.

    Instead of inheriting from InvocationFilter (to avoid circular imports),
    this class exposes the same `async invoke(ctx, next)` interface and
    can be used directly in FilterChain.

    Usage:
        from src.services.invocation_filter import FilterChain
        from src.services.agent_step_guard import StepGuardFilter, AgentStepGuard

        guard = AgentStepGuard(max_iterations=10, stuck_threshold=3)
        filter_ = StepGuardFilter(guard)
        chain = FilterChain(filters=[filter_])
    """

    def __init__(self, guard: AgentStepGuard) -> None:
        self._guard = guard

    async def invoke(self, ctx: Any, next_fn: Any) -> None:
        """
        Pre-check: if guard says abort, cancel the invocation.
        Post-check: record the step result.
        """
        # Pre: check if already over limit before calling next
        if self._guard.is_max_iterations_exceeded() or self._guard.is_stuck():
            ctx.is_cancelled = True
            ctx.metadata["cancelled_reason"] = "STEP_GUARD_PRE_CHECK"
            return

        # Execute the function
        await next_fn()

        # Post: record the outcome
        error_str = str(ctx.exception) if ctx.exception else None
        _, should_abort = self._guard.check(
            ctx.function_name,
            result=ctx.result,
            error=error_str,
        )

        if should_abort and not ctx.is_cancelled:
            ctx.is_cancelled = True
            ctx.metadata["cancelled_reason"] = (
                "STEP_GUARD_MAX_ITER"
                if self._guard.is_max_iterations_exceeded()
                else "STEP_GUARD_STUCK"
            )
