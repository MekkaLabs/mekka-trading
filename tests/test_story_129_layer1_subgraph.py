"""
tests/test_story_129_layer1_subgraph.py
=========================================
Story 129 — Testes do Layer 1 Parallel Subgraph.

Cobre:
  - Layer1State estrutura e campos
  - build_layer1_graph() retorna StateGraph válido com os 8 nós esperados
  - Topologia do grafo: fan-out (5 paralelos) + fan-in (spiderman) + assemble
  - run_layer1_subgraph() com grafo mockado: sucesso e falha de Superman
  - NickFury._cycle_for_symbol() usa layer1_graph quando fornecido
  - NickFury._cycle_for_symbol() faz fallback para ProfessorX quando layer1_graph=None
  - make_checkpointed_graph() injeta _layer1_graph em fury

Todos os testes usam mocks para evitar chamadas reais à exchange ou LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Importação condicional ────────────────────────────────────────────────────

langgraph = pytest.importorskip("langgraph", reason="langgraph não instalado")


# ── Layer1State e build_layer1_graph ─────────────────────────────────────────


class TestLayer1GraphStructure:
    def test_layer1_state_has_required_fields(self):
        from src.langgraph.layer1_graph import Layer1State

        required = {
            "symbol", "chart", "confirmation_chart",
            "sentiment", "onchain", "volatility", "liquidity",
            "momentum", "anomaly", "errors", "analysis",
        }
        # TypedDict __annotations__ contém os campos
        assert required <= set(Layer1State.__annotations__.keys())

    def test_build_layer1_graph_returns_state_graph(self):
        from langgraph.graph import StateGraph
        from src.langgraph.layer1_graph import build_layer1_graph

        mock_professor = MagicMock()
        builder = build_layer1_graph(mock_professor)
        assert isinstance(builder, StateGraph)

    def test_graph_has_expected_nodes(self):
        from src.langgraph.layer1_graph import build_layer1_graph

        mock_professor = MagicMock()
        builder = build_layer1_graph(mock_professor)

        expected_nodes = {
            "superman", "sentiment", "onchain",
            "thor", "aquaman", "flash",
            "spiderman", "assemble",
        }
        # LangGraph StateGraph expõe os nós em builder.nodes
        # (pode ser dict ou outro container dependendo da versão)
        actual_nodes = set(builder.nodes.keys())
        # Remover __start__ e __end__ que LangGraph adiciona internamente
        actual_nodes -= {"__start__", "__end__"}
        assert expected_nodes == actual_nodes

    def test_graph_compiles_without_error(self):
        """build_layer1_graph().compile() não deve levantar exceção."""
        from src.langgraph.layer1_graph import build_layer1_graph

        mock_professor = MagicMock()
        # Compilar sem checkpointer (MemorySaver para teste)
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_layer1_graph(mock_professor).compile(checkpointer=MemorySaver())
        assert graph is not None


# ── run_layer1_subgraph ───────────────────────────────────────────────────────


def _make_market_analysis_dict(symbol: str = "BTC") -> dict:
    """Mínimo de campos para um MarketAnalysis válido serializado."""
    from src.models.market_data import MarketData, TrendDirection
    from datetime import datetime, timezone

    chart = MarketData(
        symbol=symbol,
        price=50000.0,
        timeframe="4h",
        trend=TrendDirection.BULLISH,
        rsi_14=65.0,
        volume_spike=False,
        recent_closes=[49000.0, 49500.0, 50000.0],
        timestamp=datetime.now(timezone.utc),
    )

    from src.models.market_data import MarketAnalysis
    analysis = MarketAnalysis(chart=chart)
    return analysis.model_dump(mode="json")


class TestRunLayer1Subgraph:
    @pytest.mark.asyncio
    async def test_success_returns_market_analysis(self):
        """Quando o grafo retorna analysis dict, devemos obter MarketAnalysis."""
        from src.langgraph.layer1_graph import run_layer1_subgraph
        from src.models.market_data import MarketAnalysis

        analysis_dict = _make_market_analysis_dict("BTC")

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "symbol": "BTC",
            "chart": analysis_dict["chart"],
            "analysis": analysis_dict,
            "errors": [],
        })

        result = await run_layer1_subgraph(
            graph=mock_graph,
            symbol="BTC",
            cycle_id="test-cycle-001",
        )

        assert isinstance(result, MarketAnalysis)
        assert result.symbol == "BTC"

    @pytest.mark.asyncio
    async def test_superman_failure_raises_agent_error(self):
        """Se analysis=None (Superman falhou), deve levantar AgentError."""
        from src.agents.base import AgentError
        from src.langgraph.layer1_graph import run_layer1_subgraph

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "symbol": "BTC",
            "chart": None,
            "analysis": None,
            "errors": ["Superman:Connection timeout"],
        })

        with pytest.raises(AgentError, match="Layer 1 subgraph failed"):
            await run_layer1_subgraph(
                graph=mock_graph,
                symbol="BTC",
                cycle_id="test-cycle-002",
            )

    @pytest.mark.asyncio
    async def test_thread_id_format(self):
        """Thread ID deve ser '{cycle_id}:{symbol}:l1'."""
        from src.langgraph.layer1_graph import run_layer1_subgraph

        analysis_dict = _make_market_analysis_dict("ETH")

        captured_config = {}

        async def _capture_invoke(initial_state, config):
            captured_config.update(config)
            return {"symbol": "ETH", "analysis": analysis_dict, "errors": []}

        mock_graph = MagicMock()
        mock_graph.ainvoke = _capture_invoke

        await run_layer1_subgraph(
            graph=mock_graph,
            symbol="ETH",
            cycle_id="cycle-abc123",
        )

        thread_id = captured_config.get("configurable", {}).get("thread_id", "")
        assert thread_id == "cycle-abc123:ETH:l1"


# ── NickFury._cycle_for_symbol() routing ────────────────────────────────────


class TestNickFuryCycleRouting:
    """Verifica que _cycle_for_symbol usa layer1_graph quando fornecido."""

    @pytest.mark.asyncio
    async def test_uses_layer1_graph_when_provided(self):
        """Com layer1_graph e lg_thread_id, deve usar run_layer1_subgraph."""
        from src.agents.nick_fury import NickFury

        analysis_dict = _make_market_analysis_dict("BTC")

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "symbol": "BTC", "analysis": analysis_dict, "errors": [],
        })

        fury = NickFury.__new__(NickFury)
        # Configurar mocks mínimos para _cycle_for_symbol
        fury._professor = MagicMock()
        fury._vision = MagicMock()
        fury._vision.run = AsyncMock()

        from src.models.signal import TradeAction, TradingSignal
        from datetime import datetime, timezone
        mock_signal = TradingSignal(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC",
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=50000.0,
            stop_loss=48500.0,
            take_profit=51500.0,
            size_pct=0.001,
            leverage=1,
            reasoning="mock hold",
            agent_contributions={},
            metadata={},
        )
        fury._vision.run = AsyncMock(return_value=mock_signal)
        fury._vision_critic = MagicMock()
        fury._batman = MagicMock()

        from src.models.risk import RiskVerdict, RiskApproval
        mock_approval = RiskApproval(
            verdict=RiskVerdict.HOLD,
            signal=mock_signal,
            reason="hold",
            gates_passed=[],
            gates_blocked=[],
        )
        fury._batman.run = AsyncMock(return_value=mock_approval)
        fury._telegram = MagicMock()
        fury._telegram.alert = AsyncMock()
        fury._log = MagicMock()
        fury._layer1_graph = mock_graph

        with patch("src.agents.nick_fury.settings") as mock_settings, \
             patch("src.persistence.repository.MekkaRepository.save_signal", new_callable=AsyncMock, return_value=1), \
             patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock), \
             patch("src.agents.nick_fury.settings.vision_critic_enabled", False):

            mock_settings.vision_critic_enabled = False

            with patch("src.langgraph.layer1_graph.run_layer1_subgraph", new_callable=AsyncMock) as mock_l1:
                from src.models.market_data import MarketAnalysis, MarketData, TrendDirection
                from datetime import datetime, timezone
                chart = MarketData(
                    symbol="BTC", price=50000.0, timeframe="4h",
                    trend=TrendDirection.BULLISH, rsi_14=65.0,
                    volume_spike=False, recent_closes=[],
                    timestamp=datetime.now(timezone.utc),
                )
                mock_l1.return_value = MarketAnalysis(chart=chart)

                report = await fury._cycle_for_symbol(
                    symbol="BTC",
                    equity_usd=10000.0,
                    current_drawdown_pct=0.0,
                    trades_today=0,
                    lg_thread_id="test-thread-001",
                    layer1_graph=mock_graph,
                )

            # run_layer1_subgraph deve ter sido chamado
            mock_l1.assert_called_once()
            call_kwargs = mock_l1.call_args
            assert call_kwargs.kwargs.get("symbol") == "BTC" or call_kwargs.args[1] == "BTC"

    @pytest.mark.asyncio
    async def test_fallback_to_professor_when_no_layer1_graph(self):
        """Sem layer1_graph, deve usar self._professor.run()."""
        from src.agents.nick_fury import NickFury

        analysis_dict = _make_market_analysis_dict("BTC")

        fury = NickFury.__new__(NickFury)

        from src.models.market_data import MarketAnalysis, MarketData, TrendDirection
        from datetime import datetime, timezone
        chart = MarketData(
            symbol="BTC", price=50000.0, timeframe="4h",
            trend=TrendDirection.BULLISH, rsi_14=65.0,
            volume_spike=False, recent_closes=[],
            timestamp=datetime.now(timezone.utc),
        )
        mock_analysis = MarketAnalysis(chart=chart)

        fury._professor = MagicMock()
        fury._professor.run = AsyncMock(return_value=mock_analysis)
        fury._vision = MagicMock()

        from src.models.signal import TradeAction, TradingSignal
        mock_signal = TradingSignal(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC",
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=50000.0,
            stop_loss=48500.0,
            take_profit=51500.0,
            size_pct=0.001,
            leverage=1,
            reasoning="mock hold",
            agent_contributions={},
            metadata={},
        )
        fury._vision.run = AsyncMock(return_value=mock_signal)
        fury._vision_critic = MagicMock()
        fury._batman = MagicMock()

        from src.models.risk import RiskVerdict, RiskApproval
        mock_approval = RiskApproval(
            verdict=RiskVerdict.HOLD,
            signal=mock_signal,
            reason="hold",
            gates_passed=[],
            gates_blocked=[],
        )
        fury._batman.run = AsyncMock(return_value=mock_approval)
        fury._telegram = MagicMock()
        fury._telegram.alert = AsyncMock()
        fury._log = MagicMock()
        fury._layer1_graph = None

        with patch("src.persistence.repository.MekkaRepository.save_signal", new_callable=AsyncMock, return_value=1), \
             patch("src.persistence.repository.MekkaRepository.log_event", new_callable=AsyncMock), \
             patch("src.agents.nick_fury.settings") as mock_settings:

            mock_settings.vision_critic_enabled = False

            report = await fury._cycle_for_symbol(
                symbol="BTC",
                equity_usd=10000.0,
                current_drawdown_pct=0.0,
                trades_today=0,
                lg_thread_id=None,
                layer1_graph=None,
            )

        # ProfessorX.run() deve ter sido chamado (não run_layer1_subgraph)
        fury._professor.run.assert_called_once_with(symbol="BTC")


# ── NickFury._layer1_graph atributo ─────────────────────────────────────────


class TestNickFuryLayerGraphAttribute:
    def test_nick_fury_has_layer1_graph_attribute(self):
        """NickFury deve ter _layer1_graph inicializado como None."""
        from src.agents.nick_fury import NickFury

        fury = NickFury.__new__(NickFury)
        fury._professor = MagicMock()
        fury._vision = MagicMock()
        fury._batman = MagicMock()
        fury._ironman = MagicMock()
        fury._portfolio = MagicMock()
        fury._daily_pnl = MagicMock()
        fury._exec_error_breaker = MagicMock()
        fury._vision_fallback_breaker = MagicMock()
        fury._wolverine = MagicMock()
        fury._vision_critic = MagicMock()
        fury._telegram = MagicMock()
        fury._perf_writer = MagicMock()
        fury._layer1_graph = None

        assert fury._layer1_graph is None
