"""
tests/test_story_208_212_integration.py
=========================================
Testes de integração para o Milestone 33 — LangGraph Patterns.
Stories 208-212: CycleStateGraph, CycleConditionalRouter,
CycleGraphCheckpointer, CycleParallelBranch, CycleGraphInterrupt.
"""

from __future__ import annotations

import time
import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Story 208 — CycleStateGraph
# ═══════════════════════════════════════════════════════════════════════════

class TestStory208CycleStateGraph:

    def test_cycle_state_initial(self):
        from src.services.cycle_state_graph import CycleState
        state = CycleState.initial("BTC", "cycle_001", {"price": 100000})
        assert state["symbol"] == "BTC"
        assert state["cycle_id"] == "cycle_001"
        assert state["market_data"]["price"] == 100000
        assert state["signal"] == {}
        assert state["errors"] == []

    def test_cycle_state_action_shortcut(self):
        from src.services.cycle_state_graph import CycleState
        state = CycleState.initial("BTC", "c1")
        state["signal"] = {"action": "LONG", "confidence": 0.8}
        assert state.action == "LONG"

    def test_cycle_state_add_error(self):
        from src.services.cycle_state_graph import CycleState
        state = CycleState.initial("BTC", "c1")
        state.add_error("vision", "LLM timeout")
        assert state.has_errors
        assert state["errors"][0]["node"] == "vision"

    def test_graph_add_node_and_compile(self):
        from src.services.cycle_state_graph import CycleStateGraph, END
        graph = CycleStateGraph()
        graph.add_node("vision", lambda s: {"signal": {"action": "LONG", "confidence": 0.9}})
        graph.add_edge("vision", END)
        graph.set_entry_point("vision")
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_invoke_linear(self):
        from src.services.cycle_state_graph import CycleStateGraph, CycleState, END
        graph = CycleStateGraph()
        graph.add_node("a", lambda s: {"signal": {"action": "LONG"}})
        graph.add_node("b", lambda s: {"risk_report": {"approved": True}})
        graph.add_edge("a", "b")
        graph.add_edge("b", END)
        graph.set_entry_point("a")
        compiled = graph.compile()
        state = CycleState.initial("BTC", "c1")
        result = compiled.invoke(state)
        assert result["signal"]["action"] == "LONG"
        assert result["risk_report"]["approved"] is True
        assert "a" in result["__visited"]
        assert "b" in result["__visited"]

    def test_graph_conditional_edge_hold_skips_batman(self):
        from src.services.cycle_state_graph import CycleStateGraph, CycleState, END
        visited = []
        graph = CycleStateGraph()
        graph.add_node("vision", lambda s: {"signal": {"action": "HOLD"}})
        graph.add_node("batman", lambda s: {visited.append("batman") or {}})
        graph.add_conditional_edges(
            "vision",
            lambda s: s.action if s.action in ("LONG", "SHORT") else "HOLD",
            {"LONG": "batman", "SHORT": "batman", "HOLD": END},
        )
        graph.add_edge("batman", END)
        graph.set_entry_point("vision")
        compiled = graph.compile()
        state = CycleState.initial("ETH", "c2")
        result = compiled.invoke(state)
        assert result["signal"]["action"] == "HOLD"
        assert "batman" not in visited

    def test_graph_stream_yields_per_node(self):
        from src.services.cycle_state_graph import CycleStateGraph, CycleState, END
        graph = CycleStateGraph()
        graph.add_node("a", lambda s: {})
        graph.add_node("b", lambda s: {})
        graph.add_edge("a", "b")
        graph.add_edge("b", END)
        graph.set_entry_point("a")
        compiled = graph.compile()
        states = list(compiled.stream(CycleState.initial("BTC", "c3")))
        assert len(states) == 2  # um por nó

    def test_build_default_mekka_graph(self):
        from src.services.cycle_state_graph import build_default_mekka_graph, CycleState
        compiled = build_default_mekka_graph()
        state = CycleState.initial("BTC", "c4")
        state["signal"] = {"action": "HOLD"}
        result = compiled.invoke(state)
        # HOLD → salta batman e ironman
        assert "batman" not in result["__visited"]


# ═══════════════════════════════════════════════════════════════════════════
# Story 209 — CycleConditionalRouter
# ═══════════════════════════════════════════════════════════════════════════

class TestStory209CycleConditionalRouter:

    def test_router_basic_route(self):
        from src.services.cycle_conditional_router import (
            CycleConditionalRouter, RouterCondition, RouterConditionOp
        )
        router = CycleConditionalRouter(fallback="batman")
        router.add_rule(
            conditions=[RouterCondition("signal.action", RouterConditionOp.EQ, "HOLD")],
            destination="__END__",
            priority=10,
        )
        result = router.route({"signal": {"action": "HOLD"}})
        assert result == "__END__"

    def test_router_fallback_when_no_match(self):
        from src.services.cycle_conditional_router import CycleConditionalRouter
        router = CycleConditionalRouter(fallback="batman")
        result = router.route({"signal": {"action": "LONG"}})
        assert result == "batman"

    def test_router_priority_order(self):
        from src.services.cycle_conditional_router import (
            CycleConditionalRouter, RouterCondition, RouterConditionOp
        )
        router = CycleConditionalRouter(fallback="default")
        router.add_rule(
            conditions=[RouterCondition("signal.confidence", RouterConditionOp.LT, 0.4)],
            destination="low_confidence_end",
            priority=15,
        )
        router.add_rule(
            conditions=[RouterCondition("signal.action", RouterConditionOp.EQ, "HOLD")],
            destination="hold_end",
            priority=10,
        )
        # confidence < 0.4 → high priority wins
        result = router.route({"signal": {"action": "LONG", "confidence": 0.3}})
        assert result == "low_confidence_end"

    def test_router_any_mode(self):
        from src.services.cycle_conditional_router import (
            CycleConditionalRouter, RouterCondition, RouterConditionOp
        )
        router = CycleConditionalRouter(fallback="end")
        router.add_rule(
            conditions=[
                RouterCondition("signal.action", RouterConditionOp.EQ, "LONG"),
                RouterCondition("signal.action", RouterConditionOp.EQ, "SHORT"),
            ],
            destination="batman",
            priority=5,
            mode="ANY",  # OR
        )
        assert router.route({"signal": {"action": "LONG"}}) == "batman"
        assert router.route({"signal": {"action": "SHORT"}}) == "batman"

    def test_build_vision_router(self):
        from src.services.cycle_conditional_router import build_vision_router
        router = build_vision_router()
        assert router.route({"signal": {"action": "HOLD", "confidence": 0.9}}) == "__END__"
        assert router.route({"signal": {"action": "LONG", "confidence": 0.8}}) == "batman"
        assert router.route({"signal": {"action": "LONG", "confidence": 0.3}}) == "__END__"

    def test_build_batman_router(self):
        from src.services.cycle_conditional_router import build_batman_router
        router = build_batman_router()
        assert router.route({"risk_report": {"approved": True}}) == "ironman"
        assert router.route({"risk_report": {"approved": False}}) == "__END__"

    def test_router_as_fn(self):
        from src.services.cycle_conditional_router import (
            CycleConditionalRouter, RouterCondition, RouterConditionOp
        )
        router = CycleConditionalRouter(fallback="default")
        router.add_rule(
            conditions=[RouterCondition("x", RouterConditionOp.EQ, 1)],
            destination="yes",
            priority=1,
        )
        fn = router.as_fn()
        assert fn({"x": 1}) == "yes"
        assert fn({"x": 2}) == "default"


# ═══════════════════════════════════════════════════════════════════════════
# Story 210 — CycleGraphCheckpointer
# ═══════════════════════════════════════════════════════════════════════════

class TestStory210CycleGraphCheckpointer:

    def setup_method(self):
        from src.services.cycle_graph_checkpointer import reset_cycle_graph_checkpointer
        reset_cycle_graph_checkpointer()

    def test_save_and_load_latest(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer()
        state = {"symbol": "BTC", "signal": {"action": "LONG"}}
        cp.save("thread_001", "vision", state)
        loaded = cp.load_latest("thread_001")
        assert loaded is not None
        assert loaded["signal"]["action"] == "LONG"

    def test_load_by_id(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer()
        state1 = {"step": 1}
        state2 = {"step": 2}
        cp_id1 = cp.save("t1", "node_a", state1)
        cp.save("t1", "node_b", state2)
        loaded = cp.load("t1", cp_id1)
        assert loaded["step"] == 1

    def test_list_checkpoints(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer()
        cp.save("t2", "vision", {"a": 1})
        cp.save("t2", "batman", {"b": 2})
        metas = cp.list_checkpoints("t2")
        assert len(metas) == 2
        assert metas[0].node_name == "vision"
        assert metas[1].node_name == "batman"

    def test_max_checkpoints_eviction(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer(max_checkpoints_per_thread=3)
        for i in range(5):
            cp.save("t3", f"node_{i}", {"step": i})
        metas = cp.list_checkpoints("t3")
        assert len(metas) == 3  # evicção FIFO

    def test_replay_from(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer()
        cp.save("t4", "a", {"step": 0})
        cp_id = cp.save("t4", "b", {"step": 1})
        cp.save("t4", "c", {"step": 2})
        replayed = list(cp.replay_from("t4", cp_id))
        assert len(replayed) == 2
        assert replayed[0]["step"] == 1

    def test_delete_thread(self):
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer
        cp = CycleGraphCheckpointer()
        cp.save("t5", "n", {"x": 1})
        assert cp.delete_thread("t5") is True
        assert cp.load_latest("t5") is None

    def test_singleton(self):
        from src.services.cycle_graph_checkpointer import get_cycle_graph_checkpointer
        a = get_cycle_graph_checkpointer()
        b = get_cycle_graph_checkpointer()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════
# Story 211 — CycleParallelBranch
# ═══════════════════════════════════════════════════════════════════════════

class TestStory211CycleParallelBranch:

    def setup_method(self):
        from src.services.cycle_parallel_branch import reset_cycle_parallel_branch
        reset_cycle_parallel_branch()

    def test_run_parallel_basic(self):
        from src.services.cycle_parallel_branch import CycleParallelBranch, BranchInput
        branch = CycleParallelBranch(max_workers=3)
        inputs = [BranchInput("BTC"), BranchInput("ETH"), BranchInput("SOL")]

        def worker(inp: BranchInput):
            return {"signal": {"action": "LONG", "confidence": 0.7, "symbol": inp.symbol}}

        results = branch.run(inputs, worker)
        assert len(results) == 3
        assert all(r.success for r in results)
        symbols = {r.symbol for r in results}
        assert symbols == {"BTC", "ETH", "SOL"}

    def test_run_handles_worker_exception(self):
        from src.services.cycle_parallel_branch import CycleParallelBranch, BranchInput
        branch = CycleParallelBranch(max_workers=2)
        inputs = [BranchInput("BTC"), BranchInput("FAIL")]

        def worker(inp: BranchInput):
            if inp.symbol == "FAIL":
                raise RuntimeError("simulated error")
            return {"signal": {"action": "LONG", "confidence": 0.8}}

        results = branch.run(inputs, worker)
        assert len(results) == 2
        btc = next(r for r in results if r.symbol == "BTC")
        fail = next(r for r in results if r.symbol == "FAIL")
        assert btc.success is True
        assert fail.success is False

    def test_fan_in_max_confidence(self):
        from src.services.cycle_parallel_branch import (
            CycleParallelBranch, BranchResult, FanInStrategy
        )
        branch = CycleParallelBranch()
        results = [
            BranchResult("BTC", {"signal": {"action": "LONG", "confidence": 0.9}}, 10.0),
            BranchResult("ETH", {"signal": {"action": "LONG", "confidence": 0.6}}, 12.0),
            BranchResult("SOL", {"signal": {"action": "SHORT", "confidence": 0.5}}, 8.0),
        ]
        merged = branch.fan_in(results, FanInStrategy.MAX_CONFIDENCE)
        assert merged["confidence"] == 0.9
        assert merged["symbol"] == "BTC"

    def test_fan_in_majority_vote(self):
        from src.services.cycle_parallel_branch import (
            CycleParallelBranch, BranchResult, FanInStrategy
        )
        branch = CycleParallelBranch()
        results = [
            BranchResult("BTC", {"signal": {"action": "LONG", "confidence": 0.8}}, 10.0),
            BranchResult("ETH", {"signal": {"action": "LONG", "confidence": 0.7}}, 10.0),
            BranchResult("SOL", {"signal": {"action": "SHORT", "confidence": 0.9}}, 10.0),
        ]
        merged = branch.fan_in(results, FanInStrategy.MAJORITY_VOTE)
        assert merged["action"] == "LONG"  # 2 vs 1
        assert "vote_tally" in merged

    def test_fan_in_all(self):
        from src.services.cycle_parallel_branch import (
            CycleParallelBranch, BranchResult, FanInStrategy
        )
        branch = CycleParallelBranch()
        results = [
            BranchResult("BTC", {"signal": {"action": "LONG", "confidence": 0.8}}, 5.0),
            BranchResult("ETH", {"signal": {"action": "SHORT", "confidence": 0.6}}, 5.0),
        ]
        merged = branch.fan_in(results, FanInStrategy.ALL)
        assert len(merged["signals"]) == 2

    def test_fan_in_empty_returns_hold(self):
        from src.services.cycle_parallel_branch import (
            CycleParallelBranch, FanInStrategy
        )
        branch = CycleParallelBranch()
        merged = branch.fan_in([], FanInStrategy.MAX_CONFIDENCE)
        assert merged["action"] == "HOLD"

    def test_branch_result_properties(self):
        from src.services.cycle_parallel_branch import BranchResult
        r = BranchResult("BTC", {"signal": {"action": "SHORT", "confidence": 0.75}}, 20.0)
        assert r.action == "SHORT"
        assert r.confidence == 0.75


# ═══════════════════════════════════════════════════════════════════════════
# Story 212 — CycleGraphInterrupt
# ═══════════════════════════════════════════════════════════════════════════

class TestStory212CycleGraphInterrupt:

    def setup_method(self):
        from src.services.cycle_graph_interrupt import reset_cycle_graph_interrupt
        reset_cycle_graph_interrupt()

    def test_create_and_check_pending(self):
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=60)
        iid = mgr.request("cycle_001", "ironman", {"action": "LONG"})
        assert mgr.check(iid) == InterruptStatus.PENDING

    def test_resolve_approved(self):
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=60)
        iid = mgr.request("cycle_002", "ironman", {"action": "LONG"})
        result = mgr.resolve(iid, "approved", "manual ok")
        assert result is True
        assert mgr.check(iid) == InterruptStatus.APPROVED

    def test_resolve_rejected(self):
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=60)
        iid = mgr.request("cycle_003", "ironman", {"action": "SHORT"})
        mgr.resolve(iid, "rejected", "regime desfavorável")
        assert mgr.check(iid) == InterruptStatus.REJECTED

    def test_timeout_applies_reject_by_default(self):
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=0.01)
        iid = mgr.request("cycle_004", "ironman", {"action": "LONG"}, timeout_s=0.01)
        time.sleep(0.05)
        status = mgr.check(iid)
        assert status == InterruptStatus.TIMEOUT

    def test_timeout_auto_approve(self):
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=0.01)
        iid = mgr.request(
            "cycle_005", "ironman", {"action": "LONG"},
            timeout_s=0.01, on_timeout="approve"
        )
        time.sleep(0.05)
        assert mgr.check(iid) == InterruptStatus.APPROVED

    def test_list_pending(self):
        from src.services.cycle_graph_interrupt import CycleGraphInterrupt
        mgr = CycleGraphInterrupt(default_timeout_s=60)
        mgr.request("c1", "ironman", {"action": "LONG"})
        mgr.request("c2", "ironman", {"action": "SHORT"})
        pending = mgr.list_pending()
        assert len(pending) == 2

    def test_auto_expire_pending(self):
        from src.services.cycle_graph_interrupt import CycleGraphInterrupt
        mgr = CycleGraphInterrupt(default_timeout_s=0.01)
        mgr.request("c6", "ironman", {"action": "LONG"}, timeout_s=0.01)
        time.sleep(0.05)
        expired = mgr.auto_expire_pending()
        assert expired == 1

    def test_get_record(self):
        from src.services.cycle_graph_interrupt import CycleGraphInterrupt
        mgr = CycleGraphInterrupt()
        iid = mgr.request("cx", "ironman", {"action": "LONG", "confidence": 0.85})
        rec = mgr.get(iid)
        assert rec is not None
        assert rec.signal["action"] == "LONG"

    def test_double_resolve_returns_false(self):
        from src.services.cycle_graph_interrupt import CycleGraphInterrupt
        mgr = CycleGraphInterrupt()
        iid = mgr.request("cy", "ironman", {"action": "LONG"})
        mgr.resolve(iid, "approved")
        result = mgr.resolve(iid, "rejected")
        assert result is False  # já resolvido

    def test_singleton(self):
        from src.services.cycle_graph_interrupt import get_cycle_graph_interrupt
        a = get_cycle_graph_interrupt()
        b = get_cycle_graph_interrupt()
        assert a is b


# ═══════════════════════════════════════════════════════════════════════════
# Milestone 33 — Cross-Story Integration
# ═══════════════════════════════════════════════════════════════════════════

class TestMilestone33Cross:

    def test_state_graph_with_conditional_router(self):
        """StateGraph + ConditionalRouter: HOLD bypassa batman via router."""
        from src.services.cycle_state_graph import CycleStateGraph, CycleState, END
        from src.services.cycle_conditional_router import build_vision_router

        router = build_vision_router()
        batman_called = []

        graph = CycleStateGraph()
        graph.add_node("vision", lambda s: {"signal": {"action": "HOLD", "confidence": 0.9}})
        graph.add_node("batman", lambda s: {batman_called.append(True) or {}})
        graph.add_conditional_edges("vision", router.as_fn(), {
            "batman": "batman", "__END__": END, "default": "batman"
        })
        graph.add_edge("batman", END)
        graph.set_entry_point("vision")

        result = graph.compile().invoke(CycleState.initial("BTC", "cross_1"))
        assert result["signal"]["action"] == "HOLD"
        assert len(batman_called) == 0

    def test_graph_with_checkpointer_saves_per_node(self):
        """StateGraph + Checkpointer: um checkpoint por nó executado."""
        from src.services.cycle_state_graph import CycleStateGraph, CycleState, END
        from src.services.cycle_graph_checkpointer import CycleGraphCheckpointer

        cp = CycleGraphCheckpointer()
        graph = CycleStateGraph()
        graph.add_node("vision", lambda s: {"signal": {"action": "LONG"}})
        graph.add_node("batman", lambda s: {"risk_report": {"approved": True}})
        graph.add_edge("vision", "batman")
        graph.add_edge("batman", END)
        graph.set_entry_point("vision")
        compiled = graph.compile()

        state = CycleState.initial("BTC", "cross_2")
        result = compiled.invoke(state)

        # Salva manualmente checkpoints (simulando wrap_with_checkpointer)
        cp.save("cross_2", "vision", result)
        cp.save("cross_2", "batman", result)
        metas = cp.list_checkpoints("cross_2")
        assert len(metas) == 2

    def test_parallel_branch_fan_in_feeds_state_graph(self):
        """ParallelBranch fan-in MAX_CONFIDENCE alimenta o StateGraph como sinal."""
        from src.services.cycle_state_graph import CycleState
        from src.services.cycle_parallel_branch import (
            CycleParallelBranch, BranchInput, FanInStrategy
        )
        branch = CycleParallelBranch(max_workers=2)
        inputs = [BranchInput("BTC"), BranchInput("ETH")]

        def worker(inp):
            conf = 0.9 if inp.symbol == "BTC" else 0.6
            return {"signal": {"action": "LONG", "confidence": conf}}

        results = branch.run(inputs, worker)
        merged = branch.fan_in(results, FanInStrategy.MAX_CONFIDENCE)

        state = CycleState.initial("BTC", "cross_3")
        state["signal"] = merged
        assert state["signal"]["confidence"] == 0.9

    def test_interrupt_gate_before_execution(self):
        """Interrupt gate: sinal LONG em modo live requer aprovação manual."""
        from src.services.cycle_graph_interrupt import (
            CycleGraphInterrupt, InterruptStatus
        )
        mgr = CycleGraphInterrupt(default_timeout_s=60)
        signal = {"action": "LONG", "confidence": 0.85}

        # Antes do IronMan: cria interrupt
        iid = mgr.request("cross_4", "ironman", signal, timeout_s=60)
        assert mgr.check(iid) == InterruptStatus.PENDING

        # Dashboard/Telegram aprova
        mgr.resolve(iid, "approved", "operador confirmou")
        assert mgr.check(iid) == InterruptStatus.APPROVED

        # IronMan executa
        execution_allowed = (mgr.check(iid) == InterruptStatus.APPROVED)
        assert execution_allowed is True
