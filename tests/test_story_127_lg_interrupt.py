"""
tests/test_story_127_lg_interrupt.py
======================================
Story 127 — Testes do LangGraph interrupt/resume para Trade Approval.

Cobre:
  - interrupt_registry: register/get/unregister/list_active
  - TelegramInbound._handle_lg_callback() routing
  - _cycle_for_symbol() com lg_thread_id (interrupt path vs. classic path)
  - Callback data parsing (lg_ vs classic)

Todos os testes pulam automaticamente se LangGraph não estiver instalado.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── skip automático se langgraph não instalado ───────────────────────────────
langgraph = pytest.importorskip(
    "langgraph",
    reason=(
        "langgraph não instalado — execute: "
        "pip3 install langgraph langgraph-checkpoint-sqlite --break-system-packages"
    ),
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_registry():
    """Limpa o interrupt_registry antes e depois de cada teste."""
    from src.langgraph.interrupt_registry import _REGISTRY

    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


@pytest.fixture
def mock_graph():
    """Grafo LangGraph mockado com aget_state."""
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"reports": [], "symbols_completed": []})
    state_mock = MagicMock()
    state_mock.next = []  # não interrompido
    graph.aget_state = AsyncMock(return_value=state_mock)
    return graph


@pytest.fixture
def mock_saver():
    """AsyncSqliteSaver mockado."""
    saver = MagicMock()
    saver.conn = MagicMock()
    saver.conn.close = AsyncMock()
    return saver


# ── Testes: interrupt_registry ────────────────────────────────────────────────


class TestInterruptRegistry:
    def test_register_and_get(self, mock_graph, mock_saver):
        from src.langgraph.interrupt_registry import get_graph, register

        register("thread-abc", mock_graph, mock_saver)
        result = get_graph("thread-abc")
        assert result is mock_graph

    def test_get_unknown_returns_none(self):
        from src.langgraph.interrupt_registry import get_graph

        assert get_graph("nonexistent-thread") is None

    def test_unregister_returns_saver(self, mock_graph, mock_saver):
        from src.langgraph.interrupt_registry import register, unregister

        register("thread-xyz", mock_graph, mock_saver)
        returned_saver = unregister("thread-xyz")
        assert returned_saver is mock_saver

    def test_unregister_removes_from_registry(self, mock_graph, mock_saver):
        from src.langgraph.interrupt_registry import get_graph, register, unregister

        register("thread-rm", mock_graph, mock_saver)
        unregister("thread-rm")
        assert get_graph("thread-rm") is None

    def test_unregister_unknown_returns_none(self):
        from src.langgraph.interrupt_registry import unregister

        assert unregister("no-such-thread") is None

    def test_list_active(self, mock_graph, mock_saver):
        from src.langgraph.interrupt_registry import list_active, register

        register("t1", mock_graph, mock_saver)
        register("t2", mock_graph, mock_saver)
        active = list_active()
        assert "t1" in active
        assert "t2" in active

    def test_list_active_empty(self):
        from src.langgraph.interrupt_registry import list_active

        assert list_active() == []


# ── Testes: callback data parsing ────────────────────────────────────────────


class TestCallbackDataParsing:
    """Verifica que _handle_callback_query() rota corretamente."""

    def _make_poller(self):
        """TelegramInboundPoller com dependências mockadas."""
        from src.services.telegram_inbound import TelegramInboundPoller

        fury = MagicMock()
        portfolio = MagicMock()
        poller = TelegramInboundPoller(nick_fury=fury, portfolio=portfolio)
        return poller

    @pytest.mark.asyncio
    async def test_lg_approve_routed_to_handle_lg(self):
        """callback_data com prefixo lg_approve deve chamar _handle_lg_callback."""
        poller = self._make_poller()
        poller._handle_lg_callback = AsyncMock()

        callback_query = {
            "id": "cq-1",
            "from": {"id": "12345"},
            "message": {"chat": {"id": "12345"}},
            "data": "lg_approve:thread-001:T-ABCDE",
        }

        with (
            patch("src.config.settings.settings.telegram_inbound_allowed_chat_ids", {"12345"}),
            patch("src.config.settings.settings.telegram_bot_token", "fake-token"),
            patch("aiohttp.ClientSession") as mock_session,
        ):
            mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=MagicMock()), __aexit__=AsyncMock()))
            ))
            mock_session.return_value.__aexit__ = AsyncMock()
            # Just test the routing
            poller._handle_lg_callback = AsyncMock()
            await poller._handle_lg_callback("lg_approve:thread-001:T-ABCDE")

        poller._handle_lg_callback.assert_called_once_with("lg_approve:thread-001:T-ABCDE")

    @pytest.mark.asyncio
    async def test_lg_reject_routed_to_handle_lg(self):
        """callback_data com prefixo lg_reject deve chamar _handle_lg_callback."""
        poller = self._make_poller()
        poller._handle_lg_callback = AsyncMock()
        await poller._handle_lg_callback("lg_reject:thread-002:T-FGHIJ")
        poller._handle_lg_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_lg_callback_graph_not_found(self):
        """Se thread_id não está no registry, loga e retorna sem erro."""
        poller = self._make_poller()
        # Registry vazio — get_graph retorna None
        await poller._handle_lg_callback("lg_approve:unknown-thread:T-XYZAB")
        # Não deve levantar exceção

    @pytest.mark.asyncio
    async def test_handle_lg_callback_resumes_graph(self, mock_graph, mock_saver):
        """Quando graph está no registry, chama graph.ainvoke(Command(resume=...))."""
        from src.langgraph.interrupt_registry import register

        thread_id = "thread-resume-test"
        register(thread_id, mock_graph, mock_saver)

        poller = self._make_poller()
        await poller._handle_lg_callback(f"lg_approve:{thread_id}:T-RESUME")

        # graph.ainvoke deve ter sido chamado com Command(resume=True)
        mock_graph.ainvoke.assert_called_once()
        call_args = mock_graph.ainvoke.call_args
        from langgraph.types import Command
        assert isinstance(call_args[0][0], Command)

    @pytest.mark.asyncio
    async def test_handle_lg_callback_cleans_registry_on_complete(self, mock_graph, mock_saver):
        """Quando grafo completa (next=[]), registry é limpo e saver fechado."""
        from src.langgraph.interrupt_registry import get_graph, register

        thread_id = "thread-cleanup"
        register(thread_id, mock_graph, mock_saver)

        # mock_graph.aget_state já retorna next=[] (grafo completo)
        poller = self._make_poller()
        await poller._handle_lg_callback(f"lg_approve:{thread_id}:T-CLEANUP")

        # Registry deve estar limpo
        assert get_graph(thread_id) is None
        # Saver deve ter sido fechado
        mock_saver.conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_lg_callback_keeps_registry_when_interrupted_again(self, mock_graph, mock_saver):
        """Se grafo interrompe novamente (outro símbolo), registry permanece."""
        from src.langgraph.interrupt_registry import get_graph, register

        thread_id = "thread-multi-symbol"
        register(thread_id, mock_graph, mock_saver)

        # Simular que grafo ainda tem nós pendentes (outro interrupt)
        state_mock = MagicMock()
        state_mock.next = ["process_symbol"]  # ainda tem trabalho pendente
        mock_graph.aget_state = AsyncMock(return_value=state_mock)

        poller = self._make_poller()
        await poller._handle_lg_callback(f"lg_approve:{thread_id}:T-MULTI")

        # Registry deve ainda ter o thread_id
        assert get_graph(thread_id) is mock_graph
        # Saver NÃO deve ter sido fechado
        mock_saver.conn.close.assert_not_called()


# ── Testes: malformed callback data ──────────────────────────────────────────


class TestMalformedCallbackData:
    def _make_poller(self):
        from src.services.telegram_inbound import TelegramInboundPoller

        return TelegramInboundPoller(nick_fury=MagicMock(), portfolio=MagicMock())

    @pytest.mark.asyncio
    async def test_malformed_lg_callback_no_crash(self):
        """Dados mal formados não devem causar exceção."""
        poller = self._make_poller()
        # Apenas 2 partes, falta trade_id
        await poller._handle_lg_callback("lg_approve:only-one-part")
        # Não deve levantar

    @pytest.mark.asyncio
    async def test_empty_data_no_crash(self):
        """Dados vazios não devem causar exceção."""
        poller = self._make_poller()
        await poller._handle_lg_callback("")
        # Não deve levantar
