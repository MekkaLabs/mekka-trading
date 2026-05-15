"""
tests/test_story_126_langgraph_checkpointing.py
================================================
Story 126 — Testes do LangGraph cycle graph.

Testa a estrutura do grafo, o estado inicial e o roteamento condicional
sem precisar de LangGraph instalado (skippa com pytest.importorskip).
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── skip automático se langgraph não instalado ───────────────────────────────
langgraph = pytest.importorskip(
    "langgraph",
    reason="langgraph não instalado — execute: pip3 install langgraph langgraph-checkpoint-sqlite --break-system-packages",
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_fury():
    """NickFury mockado com os sub-agentes mais relevantes."""
    fury = MagicMock()
    fury._portfolio = MagicMock()
    fury._professor = MagicMock()
    fury._telegram = MagicMock()
    fury._daily_pnl = MagicMock()
    fury._perf_writer = MagicMock()
    fury._exec_error_breaker = MagicMock()
    fury._vision_fallback_breaker = MagicMock()

    # Portfolio Manager retorna snapshot vazio
    snapshot = MagicMock()
    snapshot.equity_usd = 10_000.0
    snapshot.open_positions_count = 0
    snapshot.positions = []
    snapshot.source = MagicMock(value="PAPER")
    snapshot.summary.return_value = "Paper snapshot OK"
    fury._portfolio.run = AsyncMock(return_value=snapshot)

    # Professor X valida símbolos sem filtrar
    fury._professor.validate_symbols = AsyncMock(side_effect=lambda s: s)

    # Telegram silencioso
    fury._telegram.alert = AsyncMock(return_value=None)

    # DailyPnLWriter silencioso
    fury._daily_pnl.record_cycle = AsyncMock(return_value=None)

    # DailyPerformanceWriter silencioso
    fury._perf_writer.maybe_run = AsyncMock(return_value=None)

    return fury


# ── Testes ────────────────────────────────────────────────────────────────────


class TestMekkaCycleState:
    def test_make_initial_state(self):
        from src.langgraph.cycle_graph import make_initial_state

        state = make_initial_state(equity_usd=15_000.0)
        assert state["equity_usd"] == 15_000.0
        assert state["symbols_remaining"] == []
        assert state["symbols_completed"] == []
        assert state["reports"] == []
        assert state["skip_reason"] is None
        assert state["open_positions"] == 0
        assert state["trades_today"] == 0
        assert state["drawdown_pct"] == 0.0
        assert state["running_notional_usd"] == 0.0
        assert state["error"] is None
        # cycle_id deve ser um UUID válido
        assert uuid.UUID(state["cycle_id"])


class TestBuildCycleGraph:
    def test_graph_builds_without_error(self, mock_fury):
        from src.langgraph.cycle_graph import build_cycle_graph
        from langgraph.checkpoint.memory import MemorySaver

        builder = build_cycle_graph(mock_fury)
        graph = builder.compile(checkpointer=MemorySaver())
        assert graph is not None

    def test_graph_has_correct_nodes(self, mock_fury):
        from src.langgraph.cycle_graph import build_cycle_graph

        builder = build_cycle_graph(mock_fury)
        # Nodes do StateGraph
        node_names = set(builder.nodes.keys())
        assert "preflight" in node_names
        assert "process_symbol" in node_names
        assert "finalize" in node_names


@pytest.mark.asyncio
class TestPreflight:
    async def test_skip_on_kill_switch(self, mock_fury):
        """Preflight deve retornar skip_reason='kill_switch' quando KS ativo."""
        from src.langgraph.cycle_graph import build_cycle_graph, make_initial_state
        from langgraph.checkpoint.memory import MemorySaver

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=True),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_today_drawdown_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.persistence.repository.MekkaRepository.count_trades_today", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_today_pnl_usd", new_callable=AsyncMock, return_value=0.0),
        ):
            builder = build_cycle_graph(mock_fury)
            graph = builder.compile(checkpointer=MemorySaver())
            state = make_initial_state(equity_usd=10_000.0)
            config = {"configurable": {"thread_id": state["cycle_id"]}}

            result = await graph.ainvoke(state, config=config)

        assert result["skip_reason"] == "kill_switch"
        # Com kill_switch, nenhum símbolo deve ser processado
        assert result["symbols_completed"] == []

    async def test_normal_cycle_processes_symbols(self, mock_fury):
        """Preflight + process_symbol deve processar símbolos mockados."""
        from src.langgraph.cycle_graph import build_cycle_graph, make_initial_state
        from langgraph.checkpoint.memory import MemorySaver
        from src.models.orchestration import CycleReport

        # CycleReport mockado — não executado (HOLD)
        mock_report = MagicMock(spec=CycleReport)
        mock_report.symbol = "BTC"
        mock_report.is_executed.return_value = False
        mock_report.execution = None
        mock_report.model_dump.return_value = {"symbol": "BTC", "error": None}

        mock_fury._cycle_for_symbol = AsyncMock(return_value=mock_report)
        mock_fury._check_breakers = AsyncMock(return_value=None)

        with (
            patch("src.agents.batman.is_kill_switch_active", return_value=False),
            patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock),
            patch("src.persistence.repository.MekkaRepository.get_today_drawdown_pct", new_callable=AsyncMock, return_value=0.0),
            patch("src.persistence.repository.MekkaRepository.count_trades_today", new_callable=AsyncMock, return_value=0),
            patch("src.persistence.repository.MekkaRepository.get_today_pnl_usd", new_callable=AsyncMock, return_value=0.0),
            patch("src.config.settings.settings") as mock_settings,
            patch("src.config.runtime_mode.get_params", return_value={"trading_assets": ["BTC"]}),
        ):
            mock_settings.max_daily_drawdown_pct = 0.10
            mock_settings.daily_profit_target_pct = 0.05
            mock_settings.paper_initial_equity = 10_000.0

            builder = build_cycle_graph(mock_fury)
            graph = builder.compile(checkpointer=MemorySaver())
            state = make_initial_state(equity_usd=10_000.0)
            config = {"configurable": {"thread_id": state["cycle_id"]}}

            result = await graph.ainvoke(state, config=config)

        assert "BTC" in result["symbols_completed"]
        assert result["skip_reason"] is None
        assert len(result["reports"]) == 1
        assert result["reports"][0]["symbol"] == "BTC"
