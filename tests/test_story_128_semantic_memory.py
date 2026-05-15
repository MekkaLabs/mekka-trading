"""
tests/test_story_128_semantic_memory.py
=========================================
Story 128 — Testes do SemanticEpisodicStore.

Cobre:
  - build_memory_text() e build_query_text() (sem I/O)
  - SemanticEpisodicStore.search() com embeddings mockados
  - SemanticEpisodicStore.build_context_snippet() com store populado
  - Vision._build_memory_block() usa semantic_store quando disponível
  - Vision._build_memory_block() cai para SQL quando semantic_store=None

Todos os testes de embedding usam mocks para evitar chamadas reais à OpenAI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers de texto ──────────────────────────────────────────────────────────


class TestBuildTexts:
    def test_build_memory_text_win(self):
        from src.langgraph.semantic_memory import build_memory_text

        text = build_memory_text(
            symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
            volume_elevated=True, confidence=0.82,
            outcome="WIN", pnl_usd=45.20, holding_hours=8.5,
        )
        assert "LONG BTC" in text
        assert "RSI=70" in text
        assert "BULLISH" in text
        assert "vol=HIGH" in text
        assert "outcome=WIN" in text
        assert "+$45.20" in text
        assert "8.5h" in text

    def test_build_memory_text_loss(self):
        from src.langgraph.semantic_memory import build_memory_text

        text = build_memory_text(
            symbol="ETH", action="SHORT", rsi=30.0, trend="BEARISH",
            volume_elevated=False, confidence=0.70,
            outcome="LOSS", pnl_usd=-12.50, holding_hours=3.0,
        )
        assert "SHORT ETH" in text
        assert "outcome=LOSS" in text
        assert "-$12.50" in text

    def test_build_memory_text_no_rsi(self):
        from src.langgraph.semantic_memory import build_memory_text

        text = build_memory_text(
            symbol="SOL", action="LONG", rsi=None, trend="NEUTRAL",
            volume_elevated=None, confidence=0.65,
            outcome="NEUTRAL", pnl_usd=0.0, holding_hours=None,
        )
        assert "RSI=?" in text
        assert "vol=NORMAL" in text

    def test_build_query_text(self):
        from src.langgraph.semantic_memory import build_query_text

        text = build_query_text(
            symbol="BTC", action="LONG", rsi=72.0, trend="BULLISH",
            volume_elevated=True, confidence=0.85,
        )
        assert "LONG BTC" in text
        assert "RSI=72" in text
        assert "BULLISH" in text
        # Sem outcome/pnl — é query, não memória
        assert "outcome" not in text
        assert "pnl" not in text


# ── SemanticEpisodicStore com embeddings mockados ────────────────────────────


def _fake_embedding(dim: int = 8) -> list[float]:
    """Retorna um vetor unitário simples para testes."""
    import math
    val = 1.0 / math.sqrt(dim)
    return [val] * dim


@pytest.fixture
def store():
    """Store limpo com _embed_batch mockado."""
    from src.langgraph.semantic_memory import SemanticEpisodicStore
    s = SemanticEpisodicStore(model="text-embedding-3-small")
    return s


class TestSemanticEpisodicStore:
    @pytest.mark.asyncio
    async def test_empty_store_returns_no_results(self, store):
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=_fake_embedding()):
            results = await store.search("query text", limit=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_add_and_search(self, store):
        """Adiciona uma entrada e verifica que search retorna ela."""
        emb = _fake_embedding()

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            await store.add(
                symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                volume_elevated=True, confidence=0.82,
                outcome="WIN", pnl_usd=45.20, holding_hours=8.5,
            )

        assert len(store) == 1

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            results = await store.search("LONG BTC query", limit=5)

        assert len(results) == 1
        assert results[0]["symbol"] == "BTC"
        assert results[0]["outcome"] == "WIN"
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_filter_fn_applied(self, store):
        """filter_fn deve excluir entradas que não passam no filtro."""
        emb = _fake_embedding()

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            await store.add(
                symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                volume_elevated=True, confidence=0.8,
                outcome="WIN", pnl_usd=50.0, holding_hours=5.0,
            )
            await store.add(
                symbol="BTC", action="LONG", rsi=68.0, trend="BULLISH",
                volume_elevated=False, confidence=0.75,
                outcome="PENDING", pnl_usd=None, holding_hours=None,
            )

        assert len(store) == 2

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            results = await store.search(
                "LONG BTC",
                filter_fn=lambda m: m.get("outcome") in ("WIN", "LOSS", "NEUTRAL"),
            )

        # Só WIN, não PENDING
        assert len(results) == 1
        assert results[0]["outcome"] == "WIN"

    @pytest.mark.asyncio
    async def test_build_context_snippet_non_empty(self, store):
        """build_context_snippet deve retornar texto quando há dados."""
        emb = _fake_embedding()

        # Adiciona várias entradas para ter estatísticas
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            for outcome, pnl in [("WIN", 30.0), ("WIN", 20.0), ("LOSS", -10.0)]:
                await store.add(
                    symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                    volume_elevated=True, confidence=0.8,
                    outcome=outcome, pnl_usd=pnl, holding_hours=6.0,
                )

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb):
            snippet = await store.build_context_snippet(
                symbol="BTC", action="LONG", rsi=72.0, trend="BULLISH",
                volume_elevated=True, confidence=0.85, limit=8,
            )

        assert "[SemanticMemory]" in snippet
        assert "BTC" in snippet
        assert "Win rate" in snippet

    @pytest.mark.asyncio
    async def test_build_context_snippet_empty_store(self, store):
        """Store vazio deve retornar string vazia."""
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=_fake_embedding()):
            snippet = await store.build_context_snippet(
                symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                volume_elevated=True, confidence=0.8,
            )
        assert snippet == ""

    @pytest.mark.asyncio
    async def test_warm_up_empty_db(self, store):
        """warm_up com DB vazio deve retornar 0 e não levantar exceção."""
        with patch("src.langgraph.semantic_memory.SemanticEpisodicStore._embed_batch", new_callable=AsyncMock):
            with patch("src.persistence.db.get_session") as mock_session:
                # Simula sessão com resultado vazio
                mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                    execute=AsyncMock(return_value=MagicMock(
                        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                    ))
                ))
                mock_session.return_value.__aexit__ = AsyncMock()
                n = await store.warm_up_from_db(limit=100)
        assert n == 0
        assert store.is_ready


# ── Vision._build_memory_block() routing ────────────────────────────────────


class TestVisionMemoryRouting:
    """Verifica que Vision usa semantic_store quando disponível."""

    @pytest.mark.asyncio
    async def test_uses_semantic_store_when_available(self):
        """Quando semantic_store está presente, usa build_context_snippet semântico."""
        from src.agents.vision import Vision

        mock_store = MagicMock()
        mock_store.build_context_snippet = AsyncMock(return_value="[SemanticMemory] BTC mock snippet")

        mock_analysis = MagicMock()
        mock_analysis.symbol = "BTC"
        mock_analysis.chart = MagicMock(
            rsi_14=70.0,
            trend=MagicMock(value="BULLISH"),
            volume_spike=True,
        )

        result = await Vision._build_memory_block(mock_analysis, semantic_store=mock_store)

        assert mock_store.build_context_snippet.call_count == 2  # LONG + SHORT
        assert "Semantic Search" in result
        assert "SemanticMemory" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_sql_when_no_semantic_store(self):
        """Sem semantic_store, usa AgentMemoryStore SQL."""
        from src.agents.vision import Vision
        from src.persistence.agent_memory import MemoryContext

        empty_ctx = MemoryContext(
            symbol="BTC", action="LONG", rsi_bucket=70, trend="BULLISH",
            total=0, wins=0, losses=0, neutrals=0, avg_pnl_usd=0.0,
            avg_holding_hours=None,
        )

        mock_analysis = MagicMock()
        mock_analysis.symbol = "BTC"
        mock_analysis.chart = MagicMock(
            rsi_14=70.0,
            trend=MagicMock(value="BULLISH"),
            volume_spike=False,
        )

        with patch("src.persistence.agent_memory.AgentMemoryStore.query_similar",
                   new_callable=AsyncMock, return_value=empty_ctx):
            result = await Vision._build_memory_block(mock_analysis, semantic_store=None)

        # Sem dados → string vazia
        assert result == ""

    @pytest.mark.asyncio
    async def test_semantic_store_exception_returns_empty(self):
        """Se semantic_store lança exceção, retorna string vazia (fail silent)."""
        from src.agents.vision import Vision

        mock_store = MagicMock()
        mock_store.build_context_snippet = AsyncMock(side_effect=Exception("embed fail"))

        mock_analysis = MagicMock()
        mock_analysis.symbol = "BTC"
        mock_analysis.chart = MagicMock(
            rsi_14=70.0,
            trend=MagicMock(value="BULLISH"),
            volume_spike=False,
        )

        # Não deve levantar exceção
        result = await Vision._build_memory_block(mock_analysis, semantic_store=mock_store)
        assert result == ""
