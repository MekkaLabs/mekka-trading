"""
tests/test_story_140_degraded_mode.py
=========================================
Story 140 — DEGRADED_MODE formal state machine.

Tests for DegradedModeManager: transitions NORMAL ↔ DEGRADED,
recovery counter, trigger_count, properties, singleton.
"""

from __future__ import annotations

import pytest
from src.services.degraded_mode import (
    DegradedModeManager,
    get_degraded_mode_manager,
    reset_degraded_mode_manager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the global singleton before and after every test."""
    reset_degraded_mode_manager()
    yield
    reset_degraded_mode_manager()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_starts_normal(self):
        m = DegradedModeManager()
        assert not m.is_degraded

    def test_reason_empty_when_normal(self):
        m = DegradedModeManager()
        assert m.reason == ""

    def test_trigger_count_zero(self):
        m = DegradedModeManager()
        assert m.trigger_count == 0

    def test_recovery_progress_na_when_normal(self):
        m = DegradedModeManager()
        assert m.recovery_progress == "N/A"


# ---------------------------------------------------------------------------
# trigger()
# ---------------------------------------------------------------------------

class TestTrigger:
    def test_trigger_sets_degraded(self):
        m = DegradedModeManager()
        m.trigger("LLM error")
        assert m.is_degraded

    def test_trigger_sets_reason(self):
        m = DegradedModeManager()
        m.trigger("LLM 75%")
        assert m.reason == "LLM 75%"

    def test_trigger_returns_true_on_first_transition(self):
        m = DegradedModeManager()
        result = m.trigger("first")
        assert result is True

    def test_trigger_returns_false_when_already_degraded(self):
        m = DegradedModeManager()
        m.trigger("first")
        result = m.trigger("second")
        assert result is False

    def test_trigger_updates_reason_when_already_degraded(self):
        m = DegradedModeManager()
        m.trigger("reason_a")
        m.trigger("reason_b")
        assert m.reason == "reason_b"

    def test_trigger_increments_trigger_count_only_on_new_transition(self):
        """trigger_count only increments on NORMAL→DEGRADED transitions."""
        m = DegradedModeManager()
        m.trigger("a")
        assert m.trigger_count == 1
        m.trigger("b")  # already DEGRADED — does NOT increment trigger_count
        assert m.trigger_count == 1
        m.trigger("c")  # still degraded — still no increment
        assert m.trigger_count == 1

    def test_trigger_resets_recovery_counter(self):
        m = DegradedModeManager(recovery_cycles=5)
        m.trigger("start")
        m.observe_success()  # 1/5
        m.observe_success()  # 2/5
        m.trigger("reset!")  # resets consecutive successes
        # Should need full 5 cycles again
        for _ in range(4):
            m.observe_success()
        assert m.is_degraded  # 4 < 5, not recovered yet

    def test_entered_at_set_on_first_trigger(self):
        m = DegradedModeManager()
        m.trigger("x")
        assert m._entered_at is not None


# ---------------------------------------------------------------------------
# observe_success()
# ---------------------------------------------------------------------------

class TestObserveSuccess:
    def test_returns_false_when_not_degraded(self):
        m = DegradedModeManager()
        result = m.observe_success()
        assert result is False

    def test_returns_false_before_threshold(self):
        m = DegradedModeManager(recovery_cycles=5)
        m.trigger("x")
        for _ in range(4):
            result = m.observe_success()
            assert result is False
        assert m.is_degraded  # still degraded

    def test_returns_true_and_recovers_at_threshold(self):
        m = DegradedModeManager(recovery_cycles=3)
        m.trigger("x")
        m.observe_success()
        m.observe_success()
        result = m.observe_success()  # 3rd = threshold
        assert result is True
        assert not m.is_degraded

    def test_recovery_clears_reason(self):
        m = DegradedModeManager(recovery_cycles=2)
        m.trigger("bad llm")
        m.observe_success()
        m.observe_success()
        assert m.reason == ""

    def test_recovery_clears_entered_at(self):
        m = DegradedModeManager(recovery_cycles=2)
        m.trigger("x")
        m.observe_success()
        m.observe_success()
        assert m._entered_at is None

    def test_progress_increments(self):
        m = DegradedModeManager(recovery_cycles=5)
        m.trigger("x")
        m.observe_success()
        m.observe_success()
        assert m.recovery_progress == "2/5"


# ---------------------------------------------------------------------------
# observe_failure()
# ---------------------------------------------------------------------------

class TestObserveFailure:
    def test_resets_success_counter(self):
        m = DegradedModeManager(recovery_cycles=5)
        m.trigger("x")
        m.observe_success()
        m.observe_success()  # 2/5
        m.observe_failure("new error")  # resets
        # Need 5 full successes to recover now
        for _ in range(4):
            m.observe_success()
        assert m.is_degraded  # 4 < 5

    def test_observe_failure_noop_when_normal(self):
        m = DegradedModeManager()
        m.observe_failure("irrelevant")
        assert not m.is_degraded

    def test_observe_failure_updates_reason(self):
        m = DegradedModeManager()
        m.trigger("original")
        m.observe_failure("new reason")
        assert m.reason == "new reason"

    def test_observe_failure_no_reason_preserves_reason(self):
        m = DegradedModeManager()
        m.trigger("keep_this")
        m.observe_failure()  # empty reason
        assert m.reason == "keep_this"


# ---------------------------------------------------------------------------
# Properties & summary()
# ---------------------------------------------------------------------------

class TestPropertiesAndSummary:
    def test_summary_normal(self):
        m = DegradedModeManager()
        s = m.summary()
        assert "NORMAL" in s
        assert "triggers_lifetime=0" in s

    def test_summary_degraded(self):
        m = DegradedModeManager(recovery_cycles=5)
        m.trigger("test_reason")
        s = m.summary()
        assert "DEGRADED" in s
        assert "test_reason" in s
        assert "0/5" in s

    def test_summary_after_multiple_distinct_activations(self):
        """Each NORMAL→DEGRADED transition increments trigger_count."""
        m = DegradedModeManager(recovery_cycles=1)
        m.trigger("a")         # NORMAL→DEGRADED: trigger_count=1
        m.observe_success()    # recovered (1 cycle) → NORMAL
        m.trigger("b")         # NORMAL→DEGRADED again: trigger_count=2
        assert m.trigger_count == 2


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_same_instance_returned(self):
        m1 = get_degraded_mode_manager()
        m2 = get_degraded_mode_manager()
        assert m1 is m2

    def test_reset_creates_fresh_instance(self):
        m1 = get_degraded_mode_manager()
        m1.trigger("x")
        reset_degraded_mode_manager()
        m2 = get_degraded_mode_manager()
        assert not m2.is_degraded

    def test_recovery_cycles_respected_on_first_create(self):
        m = get_degraded_mode_manager(recovery_cycles=7)
        assert m.recovery_cycles == 7

    def test_recovery_cycles_ignored_on_second_get(self):
        m1 = get_degraded_mode_manager(recovery_cycles=7)
        m2 = get_degraded_mode_manager(recovery_cycles=3)  # ignored
        assert m2.recovery_cycles == 7  # first wins
