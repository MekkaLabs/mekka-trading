"""
tests/test_story_188_192_integration.py
========================================
Testes de integração — Milestone 29: SWE-agent Patterns Wave 2 (Stories 188–192).

Cobertura:
  Story 188 — CycleTrajectory        (SWE-agent Trajectory/StepOutput)
  Story 189 — CycleBudgetGuard       (SWE-agent max_cost + done_status)
  Story 190 — SignalDemonstrationStore (SWE-agent Demonstrations / few-shot)
  Story 191 — ObservationFeedbackLoop (SWE-agent ACI guardrails + linter observation)
  Story 192 — MarketEnvironmentSnapshot (SWE-agent environment state capture)
  Cross-story — integração end-to-end
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ===========================================================================
# Story 188 — CycleTrajectory
# ===========================================================================

class TestStory188CycleTrajectory:
    """CycleTrajectory: registro imutável de steps por ciclo."""

    def test_import(self):
        from src.services.cycle_trajectory import (
            CycleTrajectory, StepRecord, TrajectoryStore,
            get_trajectory_store, reset_trajectory_store,
        )
        assert CycleTrajectory and StepRecord and TrajectoryStore
        reset_trajectory_store()

    def test_start_and_record(self):
        from src.services.cycle_trajectory import TrajectoryStore

        store = TrajectoryStore()
        traj = store.start_cycle("BTC", cycle_id="c001")
        traj.record("VISION_SIGNAL", input_summary="price=50000", output_summary="LONG 75%", latency_ms=350.0)
        traj.record("SIGNAL_LINT", input_summary="LONG raw", output_summary="LONG linted", latency_ms=5.0)

        assert len(traj.steps) == 2
        assert traj.steps[0].stage == "VISION_SIGNAL"
        assert traj.steps[1].latency_ms == 5.0

    def test_finish_cycle(self):
        from src.services.cycle_trajectory import TrajectoryStore

        store = TrajectoryStore()
        store.start_cycle("ETH", cycle_id="c002")
        store.record_step("c002", "VISION_SIGNAL", "in", "out", latency_ms=200.0)
        ok = store.finish_cycle("c002", success=True, final_action="LONG")

        assert ok is True
        traj = store.get("c002")
        assert traj.success is True
        assert traj.final_action == "LONG"

    def test_total_latency(self):
        from src.services.cycle_trajectory import CycleTrajectory

        traj = CycleTrajectory(cycle_id="c003", symbol="BTC")
        traj.record("A", "", "", latency_ms=100.0)
        traj.record("B", "", "", latency_ms=200.0)
        assert traj.total_latency_ms == 300.0

    def test_slowest_stage(self):
        from src.services.cycle_trajectory import CycleTrajectory

        traj = CycleTrajectory(cycle_id="c004", symbol="BTC")
        traj.record("FAST", "", "", latency_ms=10.0)
        traj.record("SLOW", "", "", latency_ms=500.0)
        assert traj.slowest_stage == "SLOW"

    def test_to_jsonl(self):
        from src.services.cycle_trajectory import CycleTrajectory
        import json

        traj = CycleTrajectory(cycle_id="c005", symbol="SOL")
        traj.record("VISION_SIGNAL", "in", "out", latency_ms=300.0)
        jsonl = traj.to_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["stage"] == "VISION_SIGNAL"
        assert data["cycle_id"] == "c005"

    def test_get_recent(self):
        from src.services.cycle_trajectory import TrajectoryStore

        store = TrajectoryStore(max_per_symbol=5)
        for i in range(3):
            store.start_cycle("BTC", cycle_id=f"c{i:03d}")
        recent = store.get_recent("BTC", limit=2)
        assert len(recent) == 2

    def test_nick_fury_block_present(self):
        src = open("src/agents/nick_fury.py").read()
        assert "Story 188" in src
        assert "CycleTrajectory" in src


# ===========================================================================
# Story 189 — CycleBudgetGuard
# ===========================================================================

class TestStory189CycleBudgetGuard:
    """CycleBudgetGuard: limite de custo LLM por sessão."""

    def test_import(self):
        from src.services.cycle_budget_guard import (
            CycleBudgetGuard, BudgetSession,
            get_cycle_budget_guard, reset_cycle_budget_guard,
        )
        assert CycleBudgetGuard and BudgetSession
        reset_cycle_budget_guard()

    def test_no_skip_when_under_budget(self):
        from src.services.cycle_budget_guard import CycleBudgetGuard

        guard = CycleBudgetGuard(max_cost_usd_per_session=1.0, max_calls_per_session=100)
        guard.record_cost("BTC", estimated_cost_usd=0.01)
        skip, reason = guard.should_skip_vision("BTC")
        assert skip is False
        assert "budget_ok" in reason

    def test_skip_when_cost_exceeded(self):
        from src.services.cycle_budget_guard import CycleBudgetGuard

        guard = CycleBudgetGuard(max_cost_usd_per_session=0.005, max_calls_per_session=1000)
        guard.record_cost("BTC", estimated_cost_usd=0.01)  # excede 0.005

        skip, reason = guard.should_skip_vision("BTC")
        assert skip is True
        assert "budget_exceeded" in reason

    def test_skip_when_calls_exceeded(self):
        from src.services.cycle_budget_guard import CycleBudgetGuard

        guard = CycleBudgetGuard(max_cost_usd_per_session=100.0, max_calls_per_session=2)
        guard.record_cost("BTC", estimated_cost_usd=0.001)
        guard.record_cost("BTC", estimated_cost_usd=0.001)
        guard.record_cost("BTC", estimated_cost_usd=0.001)  # 3 > 2

        skip, _ = guard.should_skip_vision("BTC")
        assert skip is True

    def test_reset_clears_budget(self):
        from src.services.cycle_budget_guard import CycleBudgetGuard

        guard = CycleBudgetGuard(max_cost_usd_per_session=0.001)
        guard.record_cost("ETH", estimated_cost_usd=0.01)
        guard.reset("ETH")

        skip, _ = guard.should_skip_vision("ETH")
        assert skip is False

    def test_summary(self):
        from src.services.cycle_budget_guard import CycleBudgetGuard

        guard = CycleBudgetGuard()
        guard.record_cost("BTC", estimated_cost_usd=0.002)
        s = guard.summary()
        assert "global" in s
        assert "sessions" in s

    def test_nick_fury_budget_skip_block(self):
        src = open("src/agents/nick_fury.py").read()
        assert "Story 189" in src
        assert "CycleBudgetGuard" in src
        assert "budget_skipped" in src


# ===========================================================================
# Story 190 — SignalDemonstrationStore
# ===========================================================================

class TestStory190SignalDemonstrationStore:
    """SignalDemonstrationStore: few-shot demonstrations para Vision."""

    def test_import(self):
        from src.services.signal_demonstration_store import (
            SignalDemonstrationStore, Demonstration,
            get_demonstration_store, reset_demonstration_store,
        )
        assert SignalDemonstrationStore and Demonstration
        reset_demonstration_store()

    def test_add_and_get_similar(self):
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        store = SignalDemonstrationStore()
        store.add("BTC", "VOLATILE", '{"action":"LONG"}', outcome_label="WIN", confidence=0.85)
        store.add("BTC", "BULL", '{"action":"LONG"}', outcome_label="WIN", confidence=0.80)

        similar = store.get_similar("BTC", "VOLATILE", top_n=2)
        assert len(similar) >= 1
        assert similar[0].regime == "VOLATILE"

    def test_prompt_block_format(self):
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        store = SignalDemonstrationStore()
        store.add("BTC", "VOLATILE", '{"action":"LONG","confidence":0.80}',
                  reasoning="Strong momentum", outcome_label="WIN", confidence=0.80)

        block = store.get_prompt_block("BTC", regime="VOLATILE")
        assert "Signal Demonstrations" in block
        assert "VOLATILE" in block
        assert "Example Signal" in block

    def test_empty_block_no_demos(self):
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        store = SignalDemonstrationStore()
        assert store.get_prompt_block("UNKNOWN") == ""

    def test_win_demos_prioritized(self):
        """WIN outcomes devem ser retornados antes de LOSS."""
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        store = SignalDemonstrationStore()
        store.add("BTC", "BULL", '{}', outcome_label="LOSS", confidence=0.90)
        store.add("BTC", "BULL", '{}', outcome_label="WIN", confidence=0.70)

        similar = store.get_similar("BTC", "BULL", top_n=2)
        assert similar[0].outcome_label == "WIN"

    def test_demo_to_prompt_block(self):
        from src.services.signal_demonstration_store import Demonstration

        demo = Demonstration(
            symbol="BTC", regime="VOLATILE",
            signal_json='{"action":"LONG","confidence":0.80,"entry_price":50000}',
            reasoning="Breakout above resistance",
            outcome_label="WIN",
        )
        block = demo.to_prompt_block()
        assert "LONG" in block
        assert "✅" in block  # WIN emoji

    def test_summary(self):
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        store = SignalDemonstrationStore()
        store.add("BTC", "VOLATILE", '{}', outcome_label="WIN")
        s = store.summary()
        assert s["total_demos"] == 1
        assert s["wins"] == 1

    def test_vision_block_present(self):
        src = open("src/agents/vision.py").read()
        assert "Story 190" in src
        assert "SignalDemonstrationStore" in src


# ===========================================================================
# Story 191 — ObservationFeedbackLoop
# ===========================================================================

class TestStory191ObservationFeedbackLoop:
    """ObservationFeedbackLoop: feedback de lint re-injetado no Vision."""

    def test_import(self):
        from src.services.observation_feedback_loop import (
            ObservationFeedbackLoop, LintObservation,
            get_observation_feedback_loop, reset_observation_feedback_loop,
        )
        assert ObservationFeedbackLoop and LintObservation
        reset_observation_feedback_loop()

    def test_record_and_get_block(self):
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        loop = ObservationFeedbackLoop()
        loop.record_observation("BTC", rule="confidence_clamp", field_name="confidence",
                                before_value="1.5", after_value="1.0",
                                description="clamped to max 1.0")

        block = loop.get_feedback_block("BTC")
        assert "Lint Observations" in block
        assert "confidence_clamp" in block
        assert "1.5" in block

    def test_empty_block_no_observations(self):
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        loop = ObservationFeedbackLoop()
        assert loop.get_feedback_block("NOOBS") == ""

    def test_consume_clears_pending(self):
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        loop = ObservationFeedbackLoop()
        loop.record_observation("ETH", "rule", "field", "1.5", "1.0")
        block = loop.get_feedback_block("ETH", consume=True)
        assert block  # bloco gerado
        assert loop.get_feedback_block("ETH") == ""  # limpo após consume

    def test_max_observations_sliding(self):
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        loop = ObservationFeedbackLoop(max_observations_per_symbol=3)
        for i in range(5):
            loop.record_observation("BTC", f"rule_{i}", "field", "before", "after")
        # Deve manter apenas 3
        assert len(loop._pending.get("BTC", [])) == 3

    def test_has_pending(self):
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        loop = ObservationFeedbackLoop()
        assert not loop.has_pending("BTC")
        loop.record_observation("BTC", "rule", "field", "1", "0")
        assert loop.has_pending("BTC")

    def test_nick_fury_block_present(self):
        src = open("src/agents/nick_fury.py").read()
        assert "Story 191" in src
        assert "ObservationFeedbackLoop" in src

    def test_vision_block_present(self):
        src = open("src/agents/vision.py").read()
        assert "Story 191" in src
        assert "ObservationFeedbackLoop" in src


# ===========================================================================
# Story 192 — MarketEnvironmentSnapshot
# ===========================================================================

class TestStory192MarketEnvironmentSnapshot:
    """MarketEnvironmentSnapshot: captura de estado do ambiente."""

    def test_import(self):
        from src.services.market_environment_snapshot import (
            MarketEnvironmentSnapshotStore, EnvironmentSnapshot, EnvironmentDiff,
            get_env_snapshot_store, reset_env_snapshot_store,
        )
        assert MarketEnvironmentSnapshotStore and EnvironmentSnapshot and EnvironmentDiff
        reset_env_snapshot_store()

    def test_capture_without_analysis(self):
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore

        store = MarketEnvironmentSnapshotStore()
        snap = store.capture("BTC", analysis=None, cycle_id="c001")
        assert snap.symbol == "BTC"
        assert snap.price == 0.0

    def test_capture_with_mock_analysis(self):
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore

        class FakeAnalysis:
            price = 50000.0
            chart = None
            signal_metadata = {"market_regime": "VOLATILE", "cap_tier": "LARGE_CAP"}

        store = MarketEnvironmentSnapshotStore()
        snap = store.capture("BTC", analysis=FakeAnalysis(), cycle_id="c002")
        assert snap.price == 50000.0
        assert snap.regime == "VOLATILE"
        assert snap.cap_tier == "LARGE_CAP"

    def test_diff_no_previous(self):
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore

        class FakeAnalysis:
            price = 50000.0
            chart = None
            signal_metadata = {}

        store = MarketEnvironmentSnapshotStore()
        store.capture("BTC", analysis=FakeAnalysis())
        diff = store.diff("BTC")
        assert diff.has_prev_snapshot is False

    def test_diff_price_change(self):
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore

        class FakeAnalysis:
            def __init__(self, price, regime="BULL"):
                self.price = price
                self.chart = None
                self.signal_metadata = {"market_regime": regime}

        store = MarketEnvironmentSnapshotStore()
        store.capture("BTC", analysis=FakeAnalysis(50000.0))
        store.capture("BTC", analysis=FakeAnalysis(51000.0))  # +2%

        diff = store.diff("BTC")
        assert diff.has_prev_snapshot is True
        assert abs(diff.price_delta_pct - 0.02) < 0.001

    def test_diff_regime_change(self):
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore

        class FakeAnalysis:
            def __init__(self, regime):
                self.price = 50000.0
                self.chart = None
                self.signal_metadata = {"market_regime": regime}

        store = MarketEnvironmentSnapshotStore()
        store.capture("BTC", analysis=FakeAnalysis("BULL"))
        store.capture("BTC", analysis=FakeAnalysis("VOLATILE"))

        diff = store.diff("BTC")
        assert diff.regime_changed is True
        assert diff.is_material_change is True

    def test_prompt_block(self):
        from src.services.market_environment_snapshot import EnvironmentSnapshot

        snap = EnvironmentSnapshot(
            symbol="BTC", price=50000.0, regime="VOLATILE",
            rsi=65.0, trend="UP", fear_greed_index=30,
        )
        block = snap.to_prompt_block()
        assert "Market Environment" in block
        assert "50000" in block
        assert "VOLATILE" in block
        assert "Fear" in block

    def test_nick_fury_block_present(self):
        src = open("src/agents/nick_fury.py").read()
        assert "Story 192" in src
        assert "MarketEnvironmentSnapshot" in src


# ===========================================================================
# Cross-Story Integration — Milestone 29
# ===========================================================================

class TestMilestone29CrossStoryIntegration:
    """Testes de integração cross-story para o Milestone 29."""

    def test_all_services_importable(self):
        from src.services.cycle_trajectory import get_trajectory_store
        from src.services.cycle_budget_guard import get_cycle_budget_guard
        from src.services.signal_demonstration_store import get_demonstration_store
        from src.services.observation_feedback_loop import get_observation_feedback_loop
        from src.services.market_environment_snapshot import get_env_snapshot_store
        assert all([
            get_trajectory_store, get_cycle_budget_guard,
            get_demonstration_store, get_observation_feedback_loop,
            get_env_snapshot_store,
        ])

    def test_vision_has_stories_190_191(self):
        src = open("src/agents/vision.py").read()
        for s in ["190", "191"]:
            assert f"Story {s}" in src, f"Story {s} ausente em vision.py"

    def test_nick_fury_has_stories_188_189_191_192(self):
        src = open("src/agents/nick_fury.py").read()
        for s in ["188", "189", "191", "192"]:
            assert f"Story {s}" in src, f"Story {s} ausente em nick_fury.py"

    def test_trajectory_and_budget_work_together(self):
        """CycleTrajectory registra passo mesmo quando budget foi excedido."""
        from src.services.cycle_trajectory import TrajectoryStore
        from src.services.cycle_budget_guard import CycleBudgetGuard

        store = TrajectoryStore()
        guard = CycleBudgetGuard(max_cost_usd_per_session=0.001)
        guard.record_cost("BTC", 0.005)  # excede

        skip, _ = guard.should_skip_vision("BTC")
        assert skip is True

        # Trajetória ainda pode registrar o step (budget skip)
        store.start_cycle("BTC", "cx001")
        step = store.record_step("cx001", "VISION_SIGNAL", "in", "HOLD(budget)", ok=False)
        assert step is not None
        assert step.ok is False

    def test_env_snapshot_and_demonstration_interact(self):
        """EnvSnapshot captura regime que é usado pelo DemoStore."""
        from src.services.market_environment_snapshot import MarketEnvironmentSnapshotStore
        from src.services.signal_demonstration_store import SignalDemonstrationStore

        class FakeAnalysis:
            price = 50000.0
            chart = None
            signal_metadata = {"market_regime": "VOLATILE"}

        snap_store = MarketEnvironmentSnapshotStore()
        snap = snap_store.capture("BTC", analysis=FakeAnalysis())

        demo_store = SignalDemonstrationStore()
        demo_store.add("BTC", snap.regime, '{"action":"LONG"}', outcome_label="WIN", confidence=0.85)

        similar = demo_store.get_similar("BTC", snap.regime, top_n=1)
        assert len(similar) == 1
        assert similar[0].regime == "VOLATILE"

    def test_observation_feedback_and_auto_linter_types(self):
        """ObservationFeedbackLoop usa campos corretos do LintFix (before/after, não original_value)."""
        from src.services.auto_signal_linter import LintFix
        from src.services.observation_feedback_loop import ObservationFeedbackLoop

        # LintFix usa before/after
        fix = LintFix(field="confidence", before=1.5, after=1.0, rule="confidence_clamp")
        assert hasattr(fix, "before")
        assert hasattr(fix, "after")

        loop = ObservationFeedbackLoop()
        # Simula record_from_lint_result manualmente
        loop.record_observation("BTC", fix.rule, fix.field, str(fix.before), str(fix.after))
        block = loop.get_feedback_block("BTC")
        assert "confidence_clamp" in block
