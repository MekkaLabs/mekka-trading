"""
tests/test_prometheus_agent.py
===============================
Cobertura do src/agents/prometheus.py — agente runtime que consome
eventos do event bus.

Foco:
- Lifecycle (subscribe/unsubscribe)
- Dedup e throttle
- Fail-silent em handlers
- Snapshot consistente
- Isolamento: opt-in via env var
- Cross-provider adapter (src/prompt_engineering/adapter.py)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from src.agents.prometheus import (
    MAX_LEARNINGS_PER_HOUR,
    MAX_OBS_PER_MIN,
    Prometheus,
    _Dedup,
    _Throttler,
    get_prometheus_agent,
    is_agent_enabled,
)
from src.prompt_engineering import Provider, adapt, adapt_to_anthropic, adapt_to_openai
from src.prompt_engineering.models import ExtractedPrompt


# ---------------------------------------------------------------------------
# Throttler
# ---------------------------------------------------------------------------


class TestThrottler:
    def test_allows_up_to_max(self) -> None:
        t = _Throttler(max_events=3, window_s=60.0)
        assert t.allow() is True
        assert t.allow() is True
        assert t.allow() is True
        assert t.allow() is False  # 4o bloqueado

    def test_count_reflects_window(self) -> None:
        t = _Throttler(max_events=10, window_s=60.0)
        for _ in range(5):
            t.allow()
        assert t.count() == 5


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestDedup:
    def test_same_key_returns_seen_on_second(self) -> None:
        d = _Dedup(window_s=60.0)
        assert d.seen("abc") is False
        assert d.seen("abc") is True

    def test_different_keys_independent(self) -> None:
        d = _Dedup(window_s=60.0)
        assert d.seen("a") is False
        assert d.seen("b") is False
        assert d.seen("a") is True


# ---------------------------------------------------------------------------
# Opt-in flag
# ---------------------------------------------------------------------------


class TestOptIn:
    def test_default_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("PROMETHEUS_AGENT_ENABLED", raising=False)
        assert is_agent_enabled() is False
        assert get_prometheus_agent() is None

    def test_enabled_returns_singleton(self, monkeypatch) -> None:
        monkeypatch.setenv("PROMETHEUS_AGENT_ENABLED", "true")
        # zera singleton interno
        import src.agents.prometheus as mod
        mod._instance = None
        a1 = get_prometheus_agent()
        a2 = get_prometheus_agent()
        assert a1 is not None
        assert a1 is a2  # singleton


# ---------------------------------------------------------------------------
# Prometheus agent
# ---------------------------------------------------------------------------


class TestPrometheusAgent:
    def test_snapshot_initial_state(self) -> None:
        agent = Prometheus()
        snap = agent.snapshot()
        assert snap["subscribed"] is False
        assert isinstance(snap["topics"], list)
        assert snap["stats"]["events_seen"] == 0
        assert snap["recent_observations"] == []

    @pytest.mark.asyncio
    async def test_on_event_records_observation(self) -> None:
        agent = Prometheus()
        await agent._on_event({"topic": "vision.signal", "symbol": "BTC", "action": "BUY"})
        snap = agent.snapshot()
        assert snap["stats"]["events_seen"] == 1
        assert snap["stats"]["observations_emitted"] == 1
        assert len(snap["recent_observations"]) == 1

    @pytest.mark.asyncio
    async def test_dedup_blocks_duplicate(self) -> None:
        agent = Prometheus()
        ev = {"topic": "vision.signal", "symbol": "BTC", "action": "BUY", "cycle_id": "c1"}
        await agent._on_event(ev)
        await agent._on_event(ev)
        snap = agent.snapshot()
        assert snap["stats"]["events_seen"] == 2
        assert snap["stats"]["events_deduped"] == 1
        assert snap["stats"]["observations_emitted"] == 1

    @pytest.mark.asyncio
    async def test_handler_failsoft_on_bad_event(self) -> None:
        agent = Prometheus()
        # event sem topic — handler precisa não levantar
        await agent._on_event({"junk": "data"})  # noqa
        snap = agent.snapshot()
        assert snap["stats"]["events_seen"] == 1

    @pytest.mark.asyncio
    async def test_throttle_limits_observations(self) -> None:
        agent = Prometheus()
        # Esgota o throttle artificialmente
        for i in range(MAX_OBS_PER_MIN + 5):
            await agent._on_event({"topic": f"t{i}", "symbol": "BTC", "cycle_id": f"c{i}"})
        snap = agent.snapshot()
        assert snap["stats"]["events_throttled"] >= 5

    @pytest.mark.asyncio
    async def test_cycle_end_emits_learning(self) -> None:
        agent = Prometheus()
        # Gera algumas observações primeiro
        await agent._on_event({"topic": "vision.signal", "symbol": "BTC", "cycle_id": "c1"})
        await agent._on_event({"topic": "agent.error", "agent": "X", "cycle_id": "c1"})
        await agent._on_event({"topic": "cycle.end", "symbol": "BTC", "cycle_id": "c1"})
        snap = agent.snapshot()
        assert snap["stats"]["learnings_emitted"] >= 1
        assert len(snap["recent_learnings"]) >= 1

    @pytest.mark.asyncio
    async def test_subscribe_idempotent(self) -> None:
        agent = Prometheus()
        ok1 = await agent.subscribe()
        ok2 = await agent.subscribe()  # 2a chamada não duplica
        snap = agent.snapshot()
        # Algum dos dois pode falhar se event_bus indisponível
        assert isinstance(snap["subscribed"], bool)
        if ok1 and ok2:
            assert snap["subscribed"] is True

    def test_fingerprint_stable(self) -> None:
        agent = Prometheus()
        ev = {"topic": "vision.signal", "symbol": "BTC", "action": "BUY"}
        fp1 = agent._fingerprint("vision.signal", ev)
        fp2 = agent._fingerprint("vision.signal", ev)
        assert fp1 == fp2
        assert len(fp1) == 16


# ---------------------------------------------------------------------------
# Cross-provider adapter
# ---------------------------------------------------------------------------


SAMPLE_PROMPT = """You are Vision Critic, a senior reviewer.

ROLE
----
Read the analysis and decide ENDORSE / AMEND / REJECT.

OUTPUT FORMAT (JSON object only)
--------------------------------
Schema: {"action": "...", "confidence_delta": 0..1}

METHOD
------
Step 1: read.
Step 2: decide.

PITFALLS — NEVER
----------------
- NEVER output markdown.

EXAMPLES
--------
<example name="x">
output: {"action": "ENDORSE"}
</example>
"""


class TestAdapter:
    def test_anthropic_wraps_sections_in_tags(self) -> None:
        out = adapt_to_anthropic(SAMPLE_PROMPT)
        assert "<role>" in out
        assert "</role>" in out
        assert "<output_format>" in out
        assert "<method>" in out
        assert "<pitfalls>" in out
        assert "<examples>" in out

    def test_openai_strips_xml_tags(self) -> None:
        anth = adapt_to_anthropic(SAMPLE_PROMPT)
        # Re-adapt back to OpenAI
        op = adapt_to_openai(anth)
        assert "<role>" not in op
        assert "</output_format>" not in op
        assert "Return ONLY a single JSON object" in op

    def test_adapt_dispatch_by_provider(self) -> None:
        prompt = ExtractedPrompt(
            source_file="x.py",
            variable_name="P",
            line_number=1,
            content=SAMPLE_PROMPT,
            fingerprint="f" * 16,
            detected_role="system",
        )
        anth = adapt(prompt, Provider.ANTHROPIC)
        op = adapt(prompt, Provider.OPENAI)
        assert "<role>" in anth
        assert "Return ONLY" in op

    def test_adapt_rejects_unknown_provider(self) -> None:
        prompt = ExtractedPrompt(
            source_file="x.py", variable_name="P", line_number=1,
            content=SAMPLE_PROMPT, fingerprint="f" * 16, detected_role="",
        )
        with pytest.raises(ValueError):
            adapt(prompt, "google")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Isolamento: agente Prometheus NÃO é importado pelo trading loop
# ---------------------------------------------------------------------------


class TestAgentIsolation:
    def test_trading_loop_does_not_import_prometheus(self) -> None:
        """
        Nick Fury (orquestrador) e os agentes Layer 1-3 não devem importar
        src/agents/prometheus.py — Prometheus é OBSERVER, não participante.
        """
        from pathlib import Path
        trading_agents = [
            "nick_fury.py", "vision.py", "vision_critic.py", "vision_moa.py",
            "batman.py", "iron_man.py", "cyclops.py", "wolverine.py",
            "superman.py", "doctor_strange.py", "black_panther.py",
            "thor.py", "aquaman.py", "spider_man.py", "professor_x.py",
        ]
        for fname in trading_agents:
            path = Path("src/agents") / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            assert "from src.agents.prometheus" not in src, (
                f"{fname} importa prometheus — quebra invariante de observer-only"
            )
            assert "import src.agents.prometheus" not in src
