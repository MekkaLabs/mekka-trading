"""
tests/test_story_155_agent_step_guard.py
==========================================
Story 155 — AgentStepGuard: MAX_ITERATIONS + Stuck Loop Detection.

Inspirado no recovery mechanism do OpenHands (PR #5500):
  "A recovery mechanism replaces hard errors (RuntimeError) with a
   graceful error state transition... The changes allow users to
   continue interacting with the agent even after it gets stuck in a loop."

Testa:
- StepRecord: frozen, to_dict
- AgentStepGuard: record_step, check, is_max_iterations_exceeded, is_stuck
- Stuck loop detection (identical hashes)
- Graceful abort (returns flag, does NOT raise)
- NickFuryStepGuard: factory, global counters, reset
- StepGuardFilter: InvocationFilter adapter
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# StepRecord
# ---------------------------------------------------------------------------

class TestStepRecord:
    def test_immutable_frozen(self):
        from src.services.agent_step_guard import StepRecord
        record = StepRecord(step_number=1, function_name="test", result_hash="abc12345")
        with pytest.raises((AttributeError, TypeError)):
            record.step_number = 99  # type: ignore[misc]

    def test_to_dict_structure(self):
        from src.services.agent_step_guard import StepRecord
        record = StepRecord(step_number=3, function_name="vision.analyze", result_hash="ff00aa11", error="timeout")
        d = record.to_dict()
        assert d["step"] == 3
        assert d["fn"] == "vision.analyze"
        assert d["hash"] == "ff00aa11"
        assert d["error"] == "timeout"


# ---------------------------------------------------------------------------
# AgentStepGuard — basic
# ---------------------------------------------------------------------------

class TestAgentStepGuard:
    def _make_guard(self, max_iterations=10, stuck_threshold=3):
        from src.services.agent_step_guard import AgentStepGuard
        return AgentStepGuard(max_iterations=max_iterations, stuck_threshold=stuck_threshold, session_id="test")

    def test_empty_on_creation(self):
        guard = self._make_guard()
        assert guard.step_count == 0
        assert not guard.is_max_iterations_exceeded()
        assert not guard.is_stuck()

    def test_record_step_increments_count(self):
        guard = self._make_guard()
        guard.record_step("fn1", result={"ok": True})
        guard.record_step("fn2", result="string_result")
        assert guard.step_count == 2

    def test_different_results_no_stuck(self):
        guard = self._make_guard(stuck_threshold=3)
        guard.record_step("fn", result={"a": 1})
        guard.record_step("fn", result={"b": 2})
        guard.record_step("fn", result={"c": 3})
        assert not guard.is_stuck()

    def test_identical_results_triggers_stuck(self):
        guard = self._make_guard(stuck_threshold=3)
        same_result = {"error": "timeout", "code": 500}
        for _ in range(3):
            guard.record_step("fn", result=same_result)
        assert guard.is_stuck()

    def test_stuck_requires_consecutive(self):
        """Stuck detection only looks at last N steps — not all steps."""
        guard = self._make_guard(stuck_threshold=3)
        # Different results followed by same
        guard.record_step("fn", result="a")
        guard.record_step("fn", result="b")
        guard.record_step("fn", result="c")
        # Now 2 identical (not enough for threshold=3)
        guard.record_step("fn", result="same")
        guard.record_step("fn", result="same")
        assert not guard.is_stuck()
        # Now 3 identical → stuck
        guard.record_step("fn", result="same")
        assert guard.is_stuck()

    def test_max_iterations_exceeded(self):
        guard = self._make_guard(max_iterations=3)
        guard.record_step("fn", result="ok")
        guard.record_step("fn", result="ok")
        assert not guard.is_max_iterations_exceeded()
        guard.record_step("fn", result="ok")
        assert guard.is_max_iterations_exceeded()

    def test_check_returns_record_and_flag(self):
        guard = self._make_guard()
        record, should_abort = guard.check("fn", result="ok")
        assert record.step_number == 1
        assert should_abort is False

    def test_check_aborts_on_max_iterations(self):
        guard = self._make_guard(max_iterations=2)
        guard.check("fn", result="ok")
        guard.check("fn", result="ok")  # hits max
        _, should_abort = guard.check("fn", result="ok")
        # After hitting max, should abort
        assert should_abort is True

    def test_check_aborts_on_stuck(self):
        guard = self._make_guard(max_iterations=100, stuck_threshold=3)
        same = {"status": "error"}
        guard.check("fn", result=same)
        guard.check("fn", result=same)
        _, should_abort = guard.check("fn", result=same)
        assert should_abort is True

    def test_check_does_not_raise(self):
        """OpenHands graceful recovery: no RuntimeError, just a flag."""
        guard = self._make_guard(max_iterations=1)
        guard.check("fn", result="ok")
        # Even past max, check() must not raise
        try:
            _, should_abort = guard.check("fn", result="ok")
            assert should_abort is True
        except Exception as exc:
            pytest.fail(f"check() raised unexpectedly: {exc}")

    def test_error_string_hashed_differently(self):
        guard = self._make_guard(stuck_threshold=3)
        # Error strings hash differently from success results
        guard.record_step("fn", error="timeout")
        guard.record_step("fn", result={"data": 1})
        guard.record_step("fn", error="rate_limit")
        assert not guard.is_stuck()

    def test_reset_clears_steps(self):
        guard = self._make_guard()
        for _ in range(5):
            guard.record_step("fn", result="ok")
        assert guard.step_count == 5
        guard.reset()
        assert guard.step_count == 0
        assert not guard.is_max_iterations_exceeded()

    def test_summary_structure(self):
        guard = self._make_guard()
        guard.check("fn1", result="ok")
        guard.check("fn2", result="ok")
        s = guard.summary()
        assert s["step_count"] == 2
        assert s["session_id"] == "test"
        assert "elapsed_s" in s
        assert "recent_steps" in s

    def test_elapsed_s_positive(self):
        import time
        guard = self._make_guard()
        time.sleep(0.01)
        assert guard.elapsed_s >= 0.005


# ---------------------------------------------------------------------------
# NickFuryStepGuard
# ---------------------------------------------------------------------------

class TestNickFuryStepGuard:
    def setup_method(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        NickFuryStepGuard.reset_global()

    def teardown_method(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        NickFuryStepGuard.reset_global()

    def test_for_cycle_returns_guard(self):
        from src.services.agent_step_guard import NickFuryStepGuard, AgentStepGuard
        guard = NickFuryStepGuard.for_cycle("BTC", "c1")
        assert isinstance(guard, AgentStepGuard)
        assert guard.step_count == 0

    def test_for_cycle_includes_symbol_in_session_id(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        guard = NickFuryStepGuard.for_cycle("ETH", "cycle_123")
        assert "ETH" in guard.summary()["session_id"]
        assert "cycle_123" in guard.summary()["session_id"]

    def test_global_stuck_counter(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        assert NickFuryStepGuard.global_summary()["global_stuck_count"] == 0
        NickFuryStepGuard.record_stuck_event()
        NickFuryStepGuard.record_stuck_event()
        assert NickFuryStepGuard.global_summary()["global_stuck_count"] == 2

    def test_global_max_exceeded_counter(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        NickFuryStepGuard.record_max_exceeded()
        assert NickFuryStepGuard.global_summary()["global_max_exceeded_count"] == 1

    def test_reset_global(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        NickFuryStepGuard.record_stuck_event()
        NickFuryStepGuard.record_max_exceeded()
        NickFuryStepGuard.reset_global()
        s = NickFuryStepGuard.global_summary()
        assert s["global_stuck_count"] == 0
        assert s["global_max_exceeded_count"] == 0

    def test_each_cycle_gets_fresh_guard(self):
        from src.services.agent_step_guard import NickFuryStepGuard
        g1 = NickFuryStepGuard.for_cycle("BTC", "c1")
        g2 = NickFuryStepGuard.for_cycle("BTC", "c2")
        g1.record_step("fn", result="ok")
        assert g1.step_count == 1
        assert g2.step_count == 0  # independent instance


# ---------------------------------------------------------------------------
# StepGuardFilter — InvocationFilter adapter
# ---------------------------------------------------------------------------

class TestStepGuardFilter:
    @pytest.mark.asyncio
    async def test_allows_normal_execution(self):
        from src.services.agent_step_guard import AgentStepGuard, StepGuardFilter
        from src.services.invocation_filter import FilterChain, InvocationContext

        guard = AgentStepGuard(max_iterations=10, stuck_threshold=5)
        # We use StepGuardFilter directly as a duck-typed filter
        # (has same invoke(ctx, next) interface as InvocationFilter)
        filter_ = StepGuardFilter(guard)

        executed = []

        async def fn():
            executed.append(True)
            return "ok"

        ctx = InvocationContext(function_name="vision.analyze", arguments={})

        async def next_fn():
            ctx.result = await fn()

        await filter_.invoke(ctx, next_fn)
        assert len(executed) == 1
        assert not ctx.is_cancelled

    @pytest.mark.asyncio
    async def test_cancels_when_max_exceeded(self):
        from src.services.agent_step_guard import AgentStepGuard, StepGuardFilter
        from src.services.invocation_filter import InvocationContext

        guard = AgentStepGuard(max_iterations=1, stuck_threshold=5)
        # Fill up iterations
        guard.record_step("pre", result="ok")  # now at max
        filter_ = StepGuardFilter(guard)

        executed = []

        async def fn():
            executed.append(True)
            return "ok"

        ctx = InvocationContext(function_name="fn", arguments={})

        async def next_fn():
            ctx.result = await fn()

        await filter_.invoke(ctx, next_fn)
        assert ctx.is_cancelled
        assert len(executed) == 0  # pre-check cancelled before execution

    @pytest.mark.asyncio
    async def test_records_step_after_execution(self):
        from src.services.agent_step_guard import AgentStepGuard, StepGuardFilter
        from src.services.invocation_filter import InvocationContext

        guard = AgentStepGuard(max_iterations=100, stuck_threshold=5)
        filter_ = StepGuardFilter(guard)

        ctx = InvocationContext(function_name="batman.evaluate", arguments={})
        ctx.result = {"verdict": "APPROVED"}

        async def next_fn():
            pass  # result already set

        await filter_.invoke(ctx, next_fn)
        assert guard.step_count == 1
