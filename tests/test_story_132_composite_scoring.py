"""
tests/test_story_132_composite_scoring.py
==========================================
Story 132 — Composite Scoring: semantic + recency_decay + importance (PnL).
Story 134 — Memory Consolidation: dedup semântico no add() e warm_up().

Testes isolados (sem OpenAI, sem SQLite) usando embeddings sintéticos.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.langgraph.semantic_memory import (
    SemanticEpisodicStore,
    _Entry,
    _compute_importance,
    _compute_recency_decay,
    build_memory_text,
    build_query_text,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _unit_vec(dim: int, idx: int) -> list[float]:
    """Cria vetor unitário com 1.0 na posição idx (embeddings ortogonais = sim=0)."""
    v = [0.0] * dim
    v[idx % dim] = 1.0
    return v


def _equal_vec(val: float, dim: int) -> list[float]:
    """Vetor de valor uniforme (usado para embeddings idênticos)."""
    norm = math.sqrt(dim * val * val)
    return [val / norm if norm > 0 else 0.0] * dim


def _make_store_with_entries(entries: list[_Entry]) -> SemanticEpisodicStore:
    store = SemanticEpisodicStore(model="text-embedding-3-small")
    store._entries = entries
    store._warmed_up = True
    return store


def _make_entry(
    text: str = "LONG BTC | RSI=70 | trend=BULLISH | vol=HIGH | conf=0.82 | outcome=WIN | pnl=+$45.20",
    embedding: list[float] | None = None,
    outcome: str = "WIN",
    pnl_usd: float = 45.0,
    recorded_at: datetime | None = None,
    importance: float = 0.5,
    idx: int = 0,
) -> _Entry:
    emb = embedding if embedding is not None else _unit_vec(16, idx)
    return _Entry(
        text=text,
        embedding=emb,
        metadata={"symbol": "BTC", "action": "LONG", "outcome": outcome, "pnl_usd": pnl_usd},
        recorded_at=recorded_at or datetime.now(timezone.utc),
        importance=importance,
    )


# ---------------------------------------------------------------------------
# Story 132 — _compute_importance
# ---------------------------------------------------------------------------

class TestComputeImportance:
    def test_none_pnl_returns_neutral(self):
        assert _compute_importance(None) == pytest.approx(0.5)

    def test_zero_pnl_returns_zero(self):
        assert _compute_importance(0.0) == pytest.approx(0.0)

    def test_positive_pnl_scales_correctly(self):
        # 100 USD com max_pnl=200 → 0.5
        assert _compute_importance(100.0, max_pnl=200.0) == pytest.approx(0.5)

    def test_negative_pnl_absolute_value(self):
        # |-100| com max_pnl=200 → mesma importância que +100
        assert _compute_importance(-100.0, max_pnl=200.0) == pytest.approx(
            _compute_importance(100.0, max_pnl=200.0)
        )

    def test_capped_at_1(self):
        # PnL acima do max_pnl → capped em 1.0
        assert _compute_importance(999.0, max_pnl=200.0) == pytest.approx(1.0)

    def test_max_pnl_exact(self):
        assert _compute_importance(200.0, max_pnl=200.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Story 132 — _compute_recency_decay
# ---------------------------------------------------------------------------

class TestComputeRecencyDecay:
    def test_none_returns_neutral(self):
        assert _compute_recency_decay(None) == pytest.approx(0.5)

    def test_now_returns_one(self):
        now = datetime.now(timezone.utc)
        result = _compute_recency_decay(now, half_life_days=30.0)
        assert result == pytest.approx(1.0, abs=1e-3)

    def test_half_life_returns_half(self):
        past = datetime.now(timezone.utc) - timedelta(days=30)
        result = _compute_recency_decay(past, half_life_days=30.0)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_double_half_life_returns_quarter(self):
        past = datetime.now(timezone.utc) - timedelta(days=60)
        result = _compute_recency_decay(past, half_life_days=30.0)
        assert result == pytest.approx(0.25, abs=0.02)

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime.utcnow() - timedelta(days=0)
        result = _compute_recency_decay(naive, half_life_days=30.0)
        assert result == pytest.approx(1.0, abs=0.01)

    def test_future_date_returns_one(self):
        future = datetime.now(timezone.utc) + timedelta(days=10)
        result = _compute_recency_decay(future, half_life_days=30.0)
        assert result == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Story 132 — SemanticEpisodicStore.search() composite scoring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCompositeSearch:
    async def test_composite_score_uses_all_three_factors(self):
        """Entrada muito antiga mas importância alta pode superar entrada recente mas irrelevante."""
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False

        now = datetime.now(timezone.utc)
        # Entrada A: semanticamente perfeita (idx=0, query também idx=0), mas antiga e pouco PnL
        entry_a = _make_entry(
            text="LONG BTC | RSI=70 | trend=BULLISH | vol=HIGH | conf=0.80 | outcome=WIN | pnl=+$5.00",
            embedding=_unit_vec(16, 0),  # same direction as query
            pnl_usd=5.0,
            recorded_at=now - timedelta(days=90),  # muito antigo
            importance=_compute_importance(5.0),
        )
        # Entrada B: semanticamente diferente (idx=1 ≠ idx=0), mas recente e grande PnL
        entry_b = _make_entry(
            text="SHORT BTC | RSI=30 | trend=BEARISH | vol=LOW | conf=0.60 | outcome=LOSS | pnl=-$150.00",
            embedding=_unit_vec(16, 1),  # diferente da query
            pnl_usd=-150.0,
            recorded_at=now,  # agora
            importance=_compute_importance(150.0),
        )
        store._entries = [entry_a, entry_b]

        q_emb = _unit_vec(16, 0)  # igual a entry_a
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=q_emb):
            with patch("src.config.settings.settings") as mock_settings:
                mock_settings.semantic_memory_semantic_weight = 0.5
                mock_settings.semantic_memory_recency_weight = 0.3
                mock_settings.semantic_memory_importance_weight = 0.2
                mock_settings.semantic_memory_recency_half_life_days = 30.0
                results = await store.search("query", limit=2)

        assert len(results) == 2
        # Ambos devem ter score >= 0.0
        for r in results:
            assert "score" in r
            assert "semantic_score" in r
            assert r["score"] >= 0.0

    async def test_returns_limit_results(self):
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False
        entries = [_make_entry(idx=i) for i in range(10)]
        store._entries = entries

        q_emb = _unit_vec(16, 0)
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=q_emb):
            with patch("src.config.settings.settings") as mock_settings:
                mock_settings.semantic_memory_semantic_weight = 0.5
                mock_settings.semantic_memory_recency_weight = 0.3
                mock_settings.semantic_memory_importance_weight = 0.2
                mock_settings.semantic_memory_recency_half_life_days = 30.0
                results = await store.search("query", limit=5)

        assert len(results) == 5

    async def test_empty_store_returns_empty(self):
        store = SemanticEpisodicStore()
        results = await store.search("anything")
        assert results == []

    async def test_results_sorted_by_composite_desc(self):
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False
        entries = [_make_entry(idx=i) for i in range(5)]
        store._entries = entries

        q_emb = _unit_vec(16, 2)  # mais próximo do entry idx=2
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=q_emb):
            with patch("src.config.settings.settings") as mock_settings:
                mock_settings.semantic_memory_semantic_weight = 0.5
                mock_settings.semantic_memory_recency_weight = 0.3
                mock_settings.semantic_memory_importance_weight = 0.2
                mock_settings.semantic_memory_recency_half_life_days = 30.0
                results = await store.search("query", limit=5)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_filter_fn_applied(self):
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False
        win_entry = _make_entry(outcome="WIN", idx=0)
        loss_entry = _make_entry(outcome="LOSS", idx=1)
        store._entries = [win_entry, loss_entry]

        q_emb = _unit_vec(16, 0)
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=q_emb):
            with patch("src.config.settings.settings") as mock_settings:
                mock_settings.semantic_memory_semantic_weight = 0.5
                mock_settings.semantic_memory_recency_weight = 0.3
                mock_settings.semantic_memory_importance_weight = 0.2
                mock_settings.semantic_memory_recency_half_life_days = 30.0
                results = await store.search(
                    "query", limit=5, filter_fn=lambda m: m.get("outcome") == "WIN"
                )

        assert len(results) == 1
        assert results[0]["outcome"] == "WIN"


# ---------------------------------------------------------------------------
# Story 134 — Memory Consolidation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMemoryConsolidation:
    async def test_consolidate_removes_duplicates(self):
        """Entradas com embeddings idênticos devem ser consolidadas para uma."""
        store = SemanticEpisodicStore()
        # Três entradas com embeddings muito similares (vetores idênticos)
        emb = _unit_vec(16, 0)
        entry_a = _make_entry(text="LONG BTC | WIN | pnl=+$10", embedding=emb[:], idx=0)
        # Pequena variação mas ainda acima do threshold
        entry_b = _make_entry(text="LONG BTC | WIN | pnl=+$11", embedding=emb[:], idx=0)
        entry_c = _make_entry(text="LONG BTC | WIN | pnl=+$12", embedding=emb[:], idx=0)
        # Completamente diferente
        entry_d = _make_entry(text="SHORT ETH | LOSS | pnl=-$20", embedding=_unit_vec(16, 1), idx=1)

        store._entries = [entry_a, entry_b, entry_c, entry_d]
        store._consolidation_threshold = 0.92

        removed = await store._consolidate_entries()

        assert removed == 2  # entry_b e entry_c são duplicatas de entry_a
        assert len(store._entries) == 2

    async def test_consolidate_keeps_unique_entries(self):
        """Entradas ortogonais (sim=0) não devem ser removidas."""
        store = SemanticEpisodicStore()
        entries = [_make_entry(embedding=_unit_vec(16, i), idx=i) for i in range(4)]
        store._entries = entries
        store._consolidation_threshold = 0.92

        removed = await store._consolidate_entries()
        assert removed == 0
        assert len(store._entries) == 4

    async def test_consolidate_single_entry_no_op(self):
        store = SemanticEpisodicStore()
        store._entries = [_make_entry()]
        removed = await store._consolidate_entries()
        assert removed == 0
        assert len(store._entries) == 1

    async def test_add_skips_duplicate(self):
        """add() deve ignorar entrada se max_cosine_similarity >= threshold."""
        store = SemanticEpisodicStore()
        store._consolidation_enabled = True
        store._consolidation_threshold = 0.92

        emb = _unit_vec(16, 0)
        store._entries = [_make_entry(embedding=emb[:], idx=0)]

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb[:]):
            await store.add(
                symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                volume_elevated=True, confidence=0.80, outcome="WIN",
                pnl_usd=50.0, holding_hours=8.0,
            )

        # Não deve ter sido adicionada
        assert len(store._entries) == 1

    async def test_add_allows_unique(self):
        """add() deve permitir entrada semanticamente diferente."""
        store = SemanticEpisodicStore()
        store._consolidation_enabled = True
        store._consolidation_threshold = 0.92

        existing_emb = _unit_vec(16, 0)
        new_emb = _unit_vec(16, 1)  # ortogonal
        store._entries = [_make_entry(embedding=existing_emb, idx=0)]

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=new_emb):
            await store.add(
                symbol="ETH", action="SHORT", rsi=30.0, trend="BEARISH",
                volume_elevated=False, confidence=0.70, outcome="LOSS",
                pnl_usd=-25.0, holding_hours=4.0,
            )

        assert len(store._entries) == 2

    async def test_consolidation_disabled_allows_duplicates(self):
        """Quando desabilitado, duplicatas não são removidas."""
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False

        emb = _unit_vec(16, 0)
        store._entries = [_make_entry(embedding=emb[:], idx=0)]

        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=emb[:]):
            await store.add(
                symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                volume_elevated=True, confidence=0.80, outcome="WIN",
                pnl_usd=50.0, holding_hours=8.0,
            )

        # Deve ter adicionado mesmo sendo duplicata
        assert len(store._entries) == 2


# ---------------------------------------------------------------------------
# Story 132 — build_context_snippet label
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBuildContextSnippet:
    async def test_composite_label_in_snippet(self):
        """Snippet deve conter 'Composite score range' não 'Semantic score range'."""
        store = SemanticEpisodicStore()
        store._consolidation_enabled = False
        entries = [_make_entry(idx=i) for i in range(3)]
        store._entries = entries

        q_emb = _unit_vec(16, 0)
        with patch.object(store, "_embed_single", new_callable=AsyncMock, return_value=q_emb):
            with patch("src.config.settings.settings") as mock_settings:
                mock_settings.semantic_memory_semantic_weight = 0.5
                mock_settings.semantic_memory_recency_weight = 0.3
                mock_settings.semantic_memory_importance_weight = 0.2
                mock_settings.semantic_memory_recency_half_life_days = 30.0
                snippet = await store.build_context_snippet(
                    symbol="BTC", action="LONG", rsi=70.0, trend="BULLISH",
                    volume_elevated=True, confidence=0.82, limit=3,
                )

        assert "Composite score range" in snippet
        assert "Semantic score range" not in snippet

    async def test_empty_store_returns_empty_string(self):
        store = SemanticEpisodicStore()
        snippet = await store.build_context_snippet(
            symbol="BTC", action="LONG", rsi=70.0,
            trend="BULLISH", volume_elevated=True, confidence=0.82,
        )
        assert snippet == ""


# ---------------------------------------------------------------------------
# Settings fields
# ---------------------------------------------------------------------------

class TestSettings132:
    def test_settings_have_composite_scoring_fields(self):
        from src.config.settings import settings
        assert hasattr(settings, "semantic_memory_semantic_weight")
        assert hasattr(settings, "semantic_memory_recency_weight")
        assert hasattr(settings, "semantic_memory_importance_weight")
        assert hasattr(settings, "semantic_memory_recency_half_life_days")
        assert hasattr(settings, "semantic_memory_consolidation_enabled")
        assert hasattr(settings, "semantic_memory_consolidation_threshold")

    def test_default_weights_sum_to_one(self):
        from src.config.settings import settings
        total = (
            settings.semantic_memory_semantic_weight
            + settings.semantic_memory_recency_weight
            + settings.semantic_memory_importance_weight
        )
        assert total == pytest.approx(1.0, abs=0.01)

    def test_default_consolidation_enabled(self):
        from src.config.settings import settings
        assert settings.semantic_memory_consolidation_enabled is True

    def test_default_consolidation_threshold(self):
        from src.config.settings import settings
        assert settings.semantic_memory_consolidation_threshold == pytest.approx(0.92)
