"""
tests/test_story_147_llm_cost_tracker.py
==========================================
Story 147 — LLM Cost Dashboard.

Testa o LLMCostTracker: agregações por sessão, por modelo, por agente,
chamada mais cara, janela deslizante, e reset.
"""

from __future__ import annotations

import pytest
from src.services.llm_cost_tracker import (
    LLMCostTracker,
    get_llm_cost_tracker,
    reset_llm_cost_tracker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset():
    reset_llm_cost_tracker()
    yield
    reset_llm_cost_tracker()


def _make_payload(
    provider="openai",
    model="gpt-4o",
    agent_id="Vision",
    tokens_in=1000,
    tokens_out=500,
    cost_usd=0.01,
    elapsed_ms=800.0,
) -> dict:
    return {
        "provider": provider,
        "model": model,
        "agent_id": agent_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_total_calls_zero(self):
        t = LLMCostTracker()
        s = t.summary()
        assert s["session"]["total_calls"] == 0

    def test_total_cost_zero(self):
        t = LLMCostTracker()
        s = t.summary()
        assert s["session"]["total_cost_usd"] == 0.0

    def test_no_most_expensive(self):
        t = LLMCostTracker()
        assert t.summary()["most_expensive_call"] is None

    def test_no_recent_calls(self):
        t = LLMCostTracker()
        assert t.summary()["recent_calls"] == []


# ---------------------------------------------------------------------------
# handle_event()
# ---------------------------------------------------------------------------

class TestHandleEvent:
    def test_increments_total_calls(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload())
        assert t.summary()["session"]["total_calls"] == 1

    def test_accumulates_cost(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(cost_usd=0.01))
        t.handle_event(_make_payload(cost_usd=0.02))
        s = t.summary()
        assert abs(s["session"]["total_cost_usd"] - 0.03) < 1e-9

    def test_accumulates_tokens(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(tokens_in=1000, tokens_out=500))
        t.handle_event(_make_payload(tokens_in=200, tokens_out=100))
        s = t.summary()["session"]
        assert s["total_tokens_in"] == 1200
        assert s["total_tokens_out"] == 600
        assert s["total_tokens"] == 1800

    def test_zero_token_call_counted_as_failed(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(tokens_in=0, tokens_out=0))
        s = t.summary()
        assert s["session"]["total_calls"] == 0
        assert s["session"]["failed_calls"] == 1

    def test_most_expensive_tracked(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(cost_usd=0.01))
        t.handle_event(_make_payload(cost_usd=0.05, model="claude-opus-4"))
        t.handle_event(_make_payload(cost_usd=0.02))
        me = t.summary()["most_expensive_call"]
        assert me is not None
        assert me["cost_usd"] == 0.05
        assert me["model"] == "claude-opus-4"

    def test_recent_calls_populated(self):
        t = LLMCostTracker()
        for i in range(5):
            t.handle_event(_make_payload(tokens_in=100 * (i + 1)))
        assert len(t.summary()["recent_calls"]) == 5

    def test_recent_calls_capped_at_20_in_summary(self):
        t = LLMCostTracker()
        for _ in range(30):
            t.handle_event(_make_payload())
        # summary() returns last 20
        assert len(t.summary()["recent_calls"]) == 20


# ---------------------------------------------------------------------------
# Aggregations by model
# ---------------------------------------------------------------------------

class TestByModel:
    def test_single_model_aggregation(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(model="gpt-4o", cost_usd=0.01))
        t.handle_event(_make_payload(model="gpt-4o", cost_usd=0.02))
        by_model = {m["model"]: m for m in t.summary()["by_model"]}
        assert by_model["gpt-4o"]["calls"] == 2
        assert abs(by_model["gpt-4o"]["cost_usd"] - 0.03) < 1e-9

    def test_multi_model_aggregation(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(model="gpt-4o", cost_usd=0.01))
        t.handle_event(_make_payload(model="claude-sonnet-4-6", cost_usd=0.005))
        by_model = {m["model"]: m for m in t.summary()["by_model"]}
        assert "gpt-4o" in by_model
        assert "claude-sonnet-4-6" in by_model

    def test_by_model_sorted_by_cost_desc(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(model="cheap-model", cost_usd=0.001))
        t.handle_event(_make_payload(model="expensive-model", cost_usd=0.10))
        by_model = t.summary()["by_model"]
        assert by_model[0]["model"] == "expensive-model"


# ---------------------------------------------------------------------------
# Aggregations by agent
# ---------------------------------------------------------------------------

class TestByAgent:
    def test_single_agent_aggregation(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(agent_id="Vision", cost_usd=0.01))
        t.handle_event(_make_payload(agent_id="Vision", cost_usd=0.01))
        by_agent = {a["agent_id"]: a for a in t.summary()["by_agent"]}
        assert by_agent["Vision"]["calls"] == 2

    def test_multi_agent_aggregation(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(agent_id="Vision"))
        t.handle_event(_make_payload(agent_id="VisionCritic"))
        by_agent = {a["agent_id"]: a for a in t.summary()["by_agent"]}
        assert "Vision" in by_agent
        assert "VisionCritic" in by_agent


# ---------------------------------------------------------------------------
# Computed metrics
# ---------------------------------------------------------------------------

class TestComputedMetrics:
    def test_avg_cost_per_call(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(cost_usd=0.02))
        t.handle_event(_make_payload(cost_usd=0.04))
        s = t.summary()["session"]
        assert abs(s["avg_cost_per_call_usd"] - 0.03) < 1e-9

    def test_avg_latency_ms(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(elapsed_ms=200.0))
        t.handle_event(_make_payload(elapsed_ms=400.0))
        s = t.summary()["session"]
        assert s["avg_latency_ms"] == 300.0


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all(self):
        t = LLMCostTracker()
        t.handle_event(_make_payload(cost_usd=0.99))
        t.reset()
        s = t.summary()["session"]
        assert s["total_calls"] == 0
        assert s["total_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_same_instance(self):
        t1 = get_llm_cost_tracker(auto_register=False)
        t2 = get_llm_cost_tracker(auto_register=False)
        assert t1 is t2

    def test_reset_creates_new(self):
        t1 = get_llm_cost_tracker(auto_register=False)
        t1.handle_event(_make_payload(cost_usd=0.01))
        reset_llm_cost_tracker()
        t2 = get_llm_cost_tracker(auto_register=False)
        assert t2.summary()["session"]["total_calls"] == 0
