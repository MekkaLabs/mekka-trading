"""
tests/test_story_193_197_integration.py
=========================================
Milestone 30 — OpenHands Patterns Wave 2

Stories:
  193 — SubAgentDelegator (OpenHands AgentDelegateAction/AgentDelegateObservation)
  194 — VisionRetryMixin (OpenHands RetryMixin exponential backoff)
  195 — CycleAgentState (OpenHands AgentState formal state machine)
  196 — CycleEventSource (OpenHands EventSource tagging)
  197 — CycleBatchedExporter (OpenHands BatchedWebHook)
"""

from __future__ import annotations

import time
import pytest


# ---------------------------------------------------------------------------
# Story 193 — SubAgentDelegator
# ---------------------------------------------------------------------------

class TestStory193SubAgentDelegator:
    """Tests for SubAgentDelegator (OpenHands AgentDelegateAction pattern)."""

    def setup_method(self) -> None:
        from src.services.sub_agent_delegator import reset_sub_agent_delegator
        reset_sub_agent_delegator()

    def test_delegate_with_stub(self) -> None:
        """Delegate without LLM caller returns stub result with FINISHED status."""
        from src.services.sub_agent_delegator import (
            SubAgentDelegator,
            DelegateTask,
            DelegateStatus,
        )
        delegator = SubAgentDelegator()
        task = DelegateTask(
            task="Analyze volume profile for BTC",
            agent_type="volume_analyst",
            symbol="BTC",
            inputs={"price": 50000.0, "volume": 1000.0},
        )
        obs = delegator.delegate(task)
        assert obs.status == DelegateStatus.FINISHED
        assert obs.success is True
        assert "stub" in obs.content.lower()
        assert obs.delegate_level == 1

    def test_delegate_with_llm_caller(self) -> None:
        """Delegate with real caller returns the caller's output."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask, DelegateStatus

        def mock_llm(prompt: str, max_tokens: int) -> str:
            return f"Mock analysis: volume is bullish. Prompt chars: {len(prompt)}"

        delegator = SubAgentDelegator()
        task = DelegateTask(task="Check volume", symbol="ETH", agent_type="volume")
        obs = delegator.delegate(task, llm_caller=mock_llm)
        assert obs.status == DelegateStatus.FINISHED
        assert "Mock analysis" in obs.content
        assert obs.outputs["agent_type"] == "volume"

    def test_delegate_max_level_exceeded(self) -> None:
        """Delegation rejected when max_delegate_level is exceeded."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask, DelegateStatus

        delegator = SubAgentDelegator(max_delegate_level=1)
        task = DelegateTask(task="Nested task", symbol="BTC")
        obs = delegator.delegate(task, delegate_level=2)
        assert obs.status == DelegateStatus.REJECTED
        assert "max_delegate_level" in obs.error_msg

    def test_delegate_error_handling(self) -> None:
        """LLM caller raising exception produces ERROR status (fail-silent)."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask, DelegateStatus

        def failing_llm(prompt: str, max_tokens: int) -> str:
            raise ConnectionError("LLM unavailable")

        delegator = SubAgentDelegator()
        task = DelegateTask(task="Failing task", symbol="BTC")
        obs = delegator.delegate(task, llm_caller=failing_llm)
        assert obs.status == DelegateStatus.ERROR
        assert "LLM unavailable" in obs.error_msg

    def test_get_recent_observations(self) -> None:
        """Recent observations are returned in order."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask

        delegator = SubAgentDelegator()
        for i in range(5):
            task = DelegateTask(task=f"Task {i}", symbol="BTC")
            delegator.delegate(task)
        recent = delegator.get_recent_observations("BTC", n=3)
        assert len(recent) == 3

    def test_get_prompt_block_no_observations(self) -> None:
        """Empty prompt block when no observations exist."""
        from src.services.sub_agent_delegator import SubAgentDelegator
        delegator = SubAgentDelegator()
        block = delegator.get_prompt_block("BTC")
        assert block == ""

    def test_summary(self) -> None:
        """Summary contains correct counts."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask
        delegator = SubAgentDelegator()
        task = DelegateTask(task="T", symbol="BTC")
        delegator.delegate(task)
        s = delegator.summary()
        assert s["total_delegations"] == 1
        assert s["total_successes"] == 1
        assert s["total_errors"] == 0

    def test_singleton(self) -> None:
        """Singleton returns same instance."""
        from src.services.sub_agent_delegator import get_sub_agent_delegator
        a = get_sub_agent_delegator()
        b = get_sub_agent_delegator()
        assert a is b


# ---------------------------------------------------------------------------
# Story 194 — VisionRetryMixin
# ---------------------------------------------------------------------------

class TestStory194VisionRetryMixin:
    """Tests for VisionRetryMixin (OpenHands RetryMixin pattern)."""

    def setup_method(self) -> None:
        from src.services.vision_retry_mixin import reset_vision_retry_mixin
        reset_vision_retry_mixin()

    def test_successful_call(self) -> None:
        """Successful call returns result without retry."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig

        retry = VisionRetryMixin(RetryConfig(max_retries=3))

        def success_fn() -> str:
            return "ok"

        result = retry.call_with_retry(success_fn)
        assert result == "ok"
        assert retry._total_successes == 1
        assert retry._total_retries == 0

    def test_retry_on_transient_error(self) -> None:
        """Retryable error triggers retry with exponential backoff."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig
        import time

        retry = VisionRetryMixin(RetryConfig(
            max_retries=2,
            retry_min_wait_s=0.01,  # very fast for tests
            retry_max_wait_s=0.05,
        ))

        call_count = {"n": 0}

        def flaky_fn() -> str:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("transient")
            return "recovered"

        result = retry.call_with_retry(flaky_fn)
        assert result == "recovered"
        assert retry._total_retries == 1
        assert retry._total_successes == 1

    def test_non_retryable_error_returns_none(self) -> None:
        """Non-retryable error (ValueError) returns None immediately."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig

        retry = VisionRetryMixin(RetryConfig(max_retries=3))

        def bad_fn() -> str:
            raise ValueError("invalid data")

        result = retry.call_with_retry(bad_fn)
        assert result is None
        assert retry._total_retries == 0
        assert retry._total_failures == 1

    def test_exhausted_retries_returns_none(self) -> None:
        """All retries exhausted returns None (fail-silent)."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig

        retry = VisionRetryMixin(RetryConfig(
            max_retries=2,
            retry_min_wait_s=0.001,
            retry_max_wait_s=0.01,
        ))

        def always_fail() -> str:
            raise ConnectionError("always fails")

        result = retry.call_with_retry(always_fail)
        assert result is None
        assert retry._total_failures == 1
        assert retry._total_retries == 2

    def test_wait_time_exponential(self) -> None:
        """Wait time follows exponential backoff formula."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig

        retry = VisionRetryMixin(RetryConfig(
            retry_multiplier=2.0,
            retry_min_wait_s=1.0,
            retry_max_wait_s=16.0,
        ))
        # attempt 1: min(16, max(1, 2*2^0)) = min(16, max(1, 2)) = 2
        assert retry._wait_time(1) == 2.0
        # attempt 2: min(16, max(1, 2*2^1)) = 4
        assert retry._wait_time(2) == 4.0
        # attempt 4: min(16, max(1, 2*2^3)) = min(16, 16) = 16
        assert retry._wait_time(4) == 16.0
        # clamped at max
        assert retry._wait_time(10) == 16.0

    def test_retry_listener_called(self) -> None:
        """retry_listener callback is invoked on retry."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig, RetryAttempt

        events = []

        def listener(attempt: RetryAttempt) -> None:
            events.append(attempt.attempt_number)

        retry = VisionRetryMixin(
            RetryConfig(max_retries=2, retry_min_wait_s=0.001, retry_max_wait_s=0.01),
            retry_listener=listener,
        )

        call_count = {"n": 0}

        def fn() -> str:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("x")
            return "ok"

        retry.call_with_retry(fn)
        assert len(events) == 1
        assert events[0] == 1

    def test_singleton(self) -> None:
        """Singleton returns same instance."""
        from src.services.vision_retry_mixin import get_vision_retry_mixin
        a = get_vision_retry_mixin()
        b = get_vision_retry_mixin()
        assert a is b


# ---------------------------------------------------------------------------
# Story 195 — CycleAgentState
# ---------------------------------------------------------------------------

class TestStory195CycleAgentState:
    """Tests for CycleAgentStateMachine (OpenHands AgentState pattern)."""

    def setup_method(self) -> None:
        from src.services.cycle_agent_state import reset_cycle_agent_state_machine
        reset_cycle_agent_state_machine()

    def test_initial_state_idle(self) -> None:
        """New symbol starts in IDLE state."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum,
        )
        machine = CycleAgentStateMachine()
        assert machine.get_state("BTC") == CycleAgentStateEnum.IDLE

    def test_valid_transition(self) -> None:
        """Valid transitions are accepted and applied."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum,
        )
        machine = CycleAgentStateMachine()
        ok = machine.transition("BTC", CycleAgentStateEnum.SCANNING, cycle_id="c1")
        assert ok is True
        assert machine.get_state("BTC") == CycleAgentStateEnum.SCANNING

    def test_invalid_transition_rejected(self) -> None:
        """Invalid transitions are silently ignored."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum,
        )
        machine = CycleAgentStateMachine()
        # IDLE → EXECUTING is invalid
        ok = machine.transition("BTC", CycleAgentStateEnum.EXECUTING, cycle_id="c1")
        assert ok is False
        assert machine.get_state("BTC") == CycleAgentStateEnum.IDLE

    def test_full_cycle_transitions(self) -> None:
        """Full cycle transitions complete without error."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )
        machine = CycleAgentStateMachine()
        sequence = [
            S.SCANNING, S.ANALYZING, S.SIGNALING,
            S.LINTING, S.RISK_CHECK, S.EXECUTING, S.FINISHED, S.IDLE,
        ]
        for state in sequence:
            machine.transition("BTC", state, cycle_id="c1")
        assert machine.get_state("BTC") == S.IDLE

    def test_terminal_states(self) -> None:
        """FINISHED, ERROR, SKIPPED are terminal."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )
        machine = CycleAgentStateMachine()
        machine.transition("BTC", S.SCANNING)
        machine.transition("BTC", S.ANALYZING)
        machine.transition("BTC", S.SKIPPED)
        ss = machine.get_symbol_state("BTC")
        assert ss is not None
        assert ss.is_terminal() is True

    def test_time_in_current_state(self) -> None:
        """time_in_current_state_s is non-negative."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )
        machine = CycleAgentStateMachine()
        machine.transition("BTC", S.SCANNING)
        ss = machine.get_symbol_state("BTC")
        assert ss is not None
        assert ss.time_in_current_state_s() >= 0.0

    def test_all_states_returns_list(self) -> None:
        """all_states returns list of dicts for dashboard."""
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )
        machine = CycleAgentStateMachine()
        machine.transition("BTC", S.SCANNING)
        machine.transition("ETH", S.ANALYZING)
        states = machine.all_states()
        assert len(states) == 2
        symbols = {s["symbol"] for s in states}
        assert "BTC" in symbols and "ETH" in symbols

    def test_singleton(self) -> None:
        """Singleton returns same instance."""
        from src.services.cycle_agent_state import get_cycle_agent_state_machine
        a = get_cycle_agent_state_machine()
        b = get_cycle_agent_state_machine()
        assert a is b


# ---------------------------------------------------------------------------
# Story 196 — CycleEventSource
# ---------------------------------------------------------------------------

class TestStory196CycleEventSource:
    """Tests for CycleEventSourceTagger (OpenHands EventSource pattern)."""

    def setup_method(self) -> None:
        from src.services.cycle_event_source import reset_event_source_tagger
        reset_event_source_tagger()

    def test_tag_event(self) -> None:
        """Tag creates SourcedEvent with correct fields."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        sourced = tagger.tag(
            event_type="CYCLE_START",
            symbol="BTC",
            cycle_id="c1",
            source=CycleEventSource.NICKFURY,
            payload={"equity_usd": 10000},
        )
        assert sourced.event_type == "CYCLE_START"
        assert sourced.symbol == "BTC"
        assert sourced.source == CycleEventSource.NICKFURY
        assert sourced.payload["equity_usd"] == 10000

    def test_source_categories(self) -> None:
        """EventSource.category returns correct category."""
        from src.services.cycle_event_source import CycleEventSource
        assert CycleEventSource.NICKFURY.category == "AGENT"
        assert CycleEventSource.VISION.category == "AGENT"
        assert CycleEventSource.SYSTEM.category == "ENVIRONMENT"
        assert CycleEventSource.USER.category == "USER"

    def test_filter_by_source(self) -> None:
        """filter_by_source returns only events from that source."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        tagger.tag("CYCLE_START", "BTC", "c1", CycleEventSource.NICKFURY)
        tagger.tag("SIGNAL_EMITTED", "BTC", "c1", CycleEventSource.VISION)
        tagger.tag("RISK_VERDICT", "BTC", "c1", CycleEventSource.BATMAN)

        vision_events = tagger.filter_by_source(CycleEventSource.VISION)
        assert len(vision_events) == 1
        assert vision_events[0].event_type == "SIGNAL_EMITTED"

    def test_filter_by_source_and_symbol(self) -> None:
        """filter_by_source with symbol filters correctly."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        tagger.tag("S1", "BTC", "c1", CycleEventSource.VISION)
        tagger.tag("S2", "ETH", "c2", CycleEventSource.VISION)

        btc_events = tagger.filter_by_source(CycleEventSource.VISION, symbol="BTC")
        assert len(btc_events) == 1
        assert btc_events[0].symbol == "BTC"

    def test_emit_sourced_without_log(self) -> None:
        """emit_sourced works without a real CycleEventLog."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        result = tagger.emit_sourced(
            log=None,
            event_type="CYCLE_END",
            source=CycleEventSource.IRONMAN,
            symbol="BTC",
            cycle_id="c1",
            outcome="FILLED",
        )
        assert result is not None
        assert result.source == CycleEventSource.IRONMAN

    def test_to_log_line(self) -> None:
        """to_log_line returns expected format."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        sourced = tagger.tag("CYCLE_START", "BTC", "cycle-abc-123", CycleEventSource.NICKFURY)
        line = sourced.to_log_line()
        assert "CYCLE_START" in line
        assert "BTC" in line
        assert "NICKFURY" in line

    def test_summary_by_source(self) -> None:
        """Summary counts events by source."""
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        tagger = CycleEventSourceTagger()
        tagger.tag("E1", "BTC", "c1", CycleEventSource.NICKFURY)
        tagger.tag("E2", "BTC", "c1", CycleEventSource.VISION)
        tagger.tag("E3", "BTC", "c1", CycleEventSource.VISION)

        s = tagger.summary()
        assert s["total_tagged"] == 3
        assert s["by_source"].get("VISION") == 2
        assert s["by_source"].get("NICKFURY") == 1

    def test_singleton(self) -> None:
        """Singleton returns same instance."""
        from src.services.cycle_event_source import get_event_source_tagger
        a = get_event_source_tagger()
        b = get_event_source_tagger()
        assert a is b


# ---------------------------------------------------------------------------
# Story 197 — CycleBatchedExporter
# ---------------------------------------------------------------------------

class TestStory197CycleBatchedExporter:
    """Tests for CycleBatchedExporter (OpenHands BatchedWebHook pattern)."""

    def setup_method(self) -> None:
        from src.services.cycle_batched_exporter import reset_cycle_batched_exporter
        reset_cycle_batched_exporter()

    def test_add_events_to_buffer(self) -> None:
        """Events are added to the buffer."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://localhost:9999/webhook",
            batch_size=10,
            enabled=True,
        )
        exporter.add({"event_type": "CYCLE_START", "symbol": "BTC"})
        exporter.add({"event_type": "SIGNAL_EMITTED", "symbol": "BTC"})
        assert exporter.buffer_size() == 2

    def test_disabled_exporter_ignores_add(self) -> None:
        """Disabled exporter ignores add() calls."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(webhook_url=None, enabled=False)
        exporter.add({"event": "X"})
        assert exporter.buffer_size() == 0

    def test_maybe_flush_below_batch_size(self) -> None:
        """maybe_flush does not flush if below batch_size."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://localhost:9999/webhook",
            batch_size=5,
            enabled=True,
        )
        exporter.add({"e": 1})
        exporter.add({"e": 2})
        count = exporter.maybe_flush()
        assert count == 0
        assert exporter.buffer_size() == 2

    def test_maybe_flush_at_batch_size_clears_buffer(self) -> None:
        """maybe_flush fires when batch_size reached. Since no real server, count=0 but buffer cleared."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://localhost:9999/noserver",
            batch_size=3,
            enabled=True,
        )
        for i in range(3):
            exporter.add({"e": i})
        # Will try to flush (no server → error), but buffer should be cleared
        exporter.maybe_flush()
        assert exporter.buffer_size() == 0  # cleared even on failure

    def test_flush_clears_buffer(self) -> None:
        """flush() clears the buffer regardless of HTTP result."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://localhost:9999/noserver",
            batch_size=100,
            enabled=True,
        )
        exporter.add({"e": 1})
        exporter.flush()
        assert exporter.buffer_size() == 0

    def test_no_webhook_url_disabled(self) -> None:
        """Exporter without URL does not attempt HTTP."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(webhook_url=None, enabled=True)
        assert exporter.enabled is False  # URL required for enabled
        assert exporter.is_configured() is False

    def test_buffer_overflow_drops_oldest(self) -> None:
        """Buffer overflow drops oldest events, not newest."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://localhost:9999/webhook",
            max_buffer_size=3,
            enabled=True,
        )
        for i in range(5):
            exporter.add({"seq": i})
        # After overflow: only last 3 remain
        assert exporter.buffer_size() == 3

    def test_summary(self) -> None:
        """Summary contains correct fields."""
        from src.services.cycle_batched_exporter import CycleBatchedExporter
        exporter = CycleBatchedExporter(
            webhook_url="http://x.com/wh",
            batch_size=20,
        )
        s = exporter.summary()
        assert "webhook_url" in s
        assert "batch_size" in s
        assert "buffer_size" in s
        assert "total_exported" in s


# ---------------------------------------------------------------------------
# Cross-story integration tests
# ---------------------------------------------------------------------------

class TestMilestone30CrossStoryIntegration:
    """Integration tests verifying Stories 193-197 work together."""

    def setup_method(self) -> None:
        from src.services.sub_agent_delegator import reset_sub_agent_delegator
        from src.services.vision_retry_mixin import reset_vision_retry_mixin
        from src.services.cycle_agent_state import reset_cycle_agent_state_machine
        from src.services.cycle_event_source import reset_event_source_tagger
        from src.services.cycle_batched_exporter import reset_cycle_batched_exporter
        reset_sub_agent_delegator()
        reset_vision_retry_mixin()
        reset_cycle_agent_state_machine()
        reset_event_source_tagger()
        reset_cycle_batched_exporter()

    def test_full_cycle_with_all_services(self) -> None:
        """Simulates a full trading cycle using all 5 new services."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )
        from src.services.cycle_batched_exporter import CycleBatchedExporter

        # State machine transitions
        machine = CycleAgentStateMachine()
        machine.transition("BTC", S.SCANNING, "c1")
        machine.transition("BTC", S.ANALYZING, "c1")

        # Sub-agent delegation
        delegator = SubAgentDelegator()
        obs = delegator.delegate(DelegateTask(
            task="Analyze RSI divergence",
            symbol="BTC",
            agent_type="rsi_analyst",
        ))
        assert obs.success

        machine.transition("BTC", S.SIGNALING, "c1")

        # Retry mixin
        retry = VisionRetryMixin(RetryConfig(max_retries=2))
        result = retry.call_with_retry(lambda: "signal: LONG 0.75")
        assert result is not None

        # Source tagging
        tagger = CycleEventSourceTagger()
        tagger.tag("SIGNAL_EMITTED", "BTC", "c1", CycleEventSource.VISION,
                   payload={"action": "LONG"})

        machine.transition("BTC", S.LINTING, "c1")
        machine.transition("BTC", S.RISK_CHECK, "c1")
        machine.transition("BTC", S.EXECUTING, "c1")
        machine.transition("BTC", S.FINISHED, "c1")

        # Exporter
        exporter = CycleBatchedExporter(webhook_url="http://noserver/wh", batch_size=100)
        exporter.add({"event": "CYCLE_END", "symbol": "BTC", "cycle_id": "c1"})
        assert exporter.buffer_size() == 1

        assert machine.get_state("BTC") == S.FINISHED

    def test_retry_mixin_with_state_machine_integration(self) -> None:
        """State machine tracks retry events as part of SIGNALING state."""
        from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig, RetryAttempt
        from src.services.cycle_agent_state import (
            CycleAgentStateMachine,
            CycleAgentStateEnum as S,
        )

        retry_events = []
        machine = CycleAgentStateMachine()
        machine.transition("BTC", S.SCANNING)
        machine.transition("BTC", S.ANALYZING)
        machine.transition("BTC", S.SIGNALING)

        def on_retry(attempt: RetryAttempt) -> None:
            retry_events.append(attempt.attempt_number)

        retry = VisionRetryMixin(
            RetryConfig(max_retries=2, retry_min_wait_s=0.001, retry_max_wait_s=0.01),
            retry_listener=on_retry,
        )

        call_n = {"n": 0}

        def flaky():
            call_n["n"] += 1
            if call_n["n"] < 2:
                raise ConnectionError("flaky")
            return "ok"

        result = retry.call_with_retry(flaky)
        assert result == "ok"
        assert len(retry_events) >= 1
        assert machine.get_state("BTC") == S.SIGNALING  # state unchanged

    def test_delegate_result_in_event_source(self) -> None:
        """Delegate observation can be tagged with EventSource."""
        from src.services.sub_agent_delegator import SubAgentDelegator, DelegateTask
        from src.services.cycle_event_source import (
            CycleEventSourceTagger,
            CycleEventSource,
        )

        delegator = SubAgentDelegator()
        tagger = CycleEventSourceTagger()

        task = DelegateTask(task="Analyze trend", symbol="ETH", agent_type="trend_analyst")
        obs = delegator.delegate(task)
        assert obs.success

        tagger.tag(
            event_type="DELEGATE_RESULT",
            symbol="ETH",
            cycle_id="c2",
            source=CycleEventSource.VISION,
            payload={"agent_type": task.agent_type, "status": obs.status.value},
        )

        events = tagger.filter_by_source(CycleEventSource.VISION, symbol="ETH")
        assert len(events) == 1
        assert events[0].payload["agent_type"] == "trend_analyst"

    def test_all_singletons_independent(self) -> None:
        """All 5 singletons are independent instances."""
        from src.services.sub_agent_delegator import get_sub_agent_delegator
        from src.services.vision_retry_mixin import get_vision_retry_mixin
        from src.services.cycle_agent_state import get_cycle_agent_state_machine
        from src.services.cycle_event_source import get_event_source_tagger
        from src.services.cycle_batched_exporter import get_cycle_batched_exporter

        a = get_sub_agent_delegator()
        b = get_vision_retry_mixin()
        c = get_cycle_agent_state_machine()
        d = get_event_source_tagger()
        e = get_cycle_batched_exporter()

        # All are distinct
        assert a is not b
        assert b is not c
        assert c is not d
        assert d is not e
