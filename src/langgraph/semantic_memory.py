"""
src/langgraph/semantic_memory.py
==================================
Story 128 — Memória Episódica Semântica com OpenAI text-embedding-3-small.

Substitui a busca por igualdade/range da Story 063 (AgentMemoryStore.query_similar)
por busca vetorial de similaridade cossenoidal no modo --langgraph.

Arquitetura
-----------
SemanticEpisodicStore mantém um índice in-memory de pares (texto, embedding).
Cada entrada corresponde a um AgentMemoryRecord resolvido (WIN/LOSS/NEUTRAL).

Ciclo de vida:
  1. make_checkpointed_graph() cria o store e chama warm_up_from_db()
     → carrega os últimos N registros resolvidos do SQLite e os embeda em batch
  2. Durante o ciclo, Vision chama search() antes de chamar o LLM
     → o snippet semântico é injetado no prompt do Vision (mais rico que RSI ±10)
  3. Quando Cyclops resolve um outcome, add() adiciona ao índice live
     → busca subsequente inclui esse trade imediatamente

Formato de texto para embedding
--------------------------------
  Memory: "LONG BTC | RSI=70 | trend=BULLISH | vol=HIGH | conf=0.82 | outcome=WIN | pnl=+$45.20 | hold=8.5h"
  Query:  "LONG BTC | RSI=72 | trend=BULLISH | vol=HIGH | conf=0.85"

Incluir símbolo e action no texto garante que o modelo de embedding dê peso
maior a padrões do mesmo ativo e direção — sem precisar de filtros separados.

Fallback:
  Se OPENAI_API_KEY não estiver configurada ou qualquer chamada falhar,
  o método retorna "" (string vazia) — Vision cai de volta para o snippet SQL.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Helpers de texto
# ---------------------------------------------------------------------------

def _vol_label(volume_elevated: Optional[bool]) -> str:
    if volume_elevated is None:
        return "NORMAL"
    return "HIGH" if volume_elevated else "NORMAL"


def build_memory_text(
    symbol: str,
    action: str,
    rsi: Optional[float],
    trend: str,
    volume_elevated: Optional[bool],
    confidence: float,
    outcome: str,
    pnl_usd: Optional[float],
    holding_hours: Optional[float],
) -> str:
    """
    Converte um registro de memória em texto compacto para embedding.

    Exemplo:
      "LONG BTC | RSI=70 | trend=BULLISH | vol=HIGH | conf=0.82 | outcome=WIN | pnl=+$45.20 | hold=8.5h"
    """
    rsi_str = f"RSI={int(round(rsi))}" if rsi is not None else "RSI=?"
    pnl_str = ""
    if pnl_usd is not None:
        sign = "+" if pnl_usd >= 0 else ""
        pnl_str = f" | pnl={sign}${pnl_usd:.2f}"
    hold_str = f" | hold={holding_hours:.1f}h" if holding_hours is not None else ""
    return (
        f"{action.upper()} {symbol.upper()} | {rsi_str} | trend={trend.upper()} | "
        f"vol={_vol_label(volume_elevated)} | conf={confidence:.2f} | "
        f"outcome={outcome.upper()}{pnl_str}{hold_str}"
    )


def build_query_text(
    symbol: str,
    action: str,
    rsi: Optional[float],
    trend: str,
    volume_elevated: Optional[bool],
    confidence: float,
) -> str:
    """
    Converte os parâmetros da query atual em texto para embedding.

    Exemplo:
      "LONG BTC | RSI=72 | trend=BULLISH | vol=HIGH | conf=0.85"
    """
    rsi_str = f"RSI={int(round(rsi))}" if rsi is not None else "RSI=?"
    return (
        f"{action.upper()} {symbol.upper()} | {rsi_str} | trend={trend.upper()} | "
        f"vol={_vol_label(volume_elevated)} | conf={confidence:.2f}"
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


class SemanticEpisodicStore:
    """
    In-memory vector store para memória episódica semântica.

    Thread-safety: asyncio single event loop — sem locks necessários.
    Não é persistido — recriado a cada startup via warm_up_from_db().
    """

    _EMBED_BATCH_SIZE = 100  # Máximo de textos por chamada à OpenAI

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self._model = model
        self._entries: list[_Entry] = []
        self._warmed_up = False

    # -----------------------------------------------------------------------
    # Startup: carregar memórias do SQLite
    # -----------------------------------------------------------------------

    async def warm_up_from_db(self, limit: int = 500) -> int:
        """
        Carrega os ``limit`` registros mais recentes de AgentMemoryRecord
        resolvidos (WIN/LOSS/NEUTRAL) do SQLite, embeda em batch e indexa.

        Retorna o número de registros carregados.
        Falha silenciosamente — store fica vazio se não houver dados ou API key.
        """
        try:
            from src.persistence.db import get_session  # noqa: WPS433
            from src.persistence.models import AgentMemoryRecord  # noqa: WPS433
            from sqlalchemy import select  # noqa: WPS433

            async with get_session() as session:
                stmt = (
                    select(AgentMemoryRecord)
                    .where(AgentMemoryRecord.outcome.in_(["WIN", "LOSS", "NEUTRAL"]))
                    .order_by(AgentMemoryRecord.timestamp.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows: list[AgentMemoryRecord] = list(result.scalars().all())

        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[SemanticMemory] warm_up DB query failed: {exc}")
            self._warmed_up = True
            return 0

        if not rows:
            logger.info("[SemanticMemory] warm_up: no resolved memories in DB yet")
            self._warmed_up = True
            return 0

        texts = [
            build_memory_text(
                symbol=r.symbol,
                action=r.action,
                rsi=r.rsi_bucket,  # bucket is close enough for embedding
                trend=r.trend,
                volume_elevated=r.volume_elevated,
                confidence=r.confidence or 0.0,
                outcome=r.outcome,
                pnl_usd=r.pnl_usd,
                holding_hours=r.holding_hours,
            )
            for r in rows
        ]
        metas = [
            {
                "symbol": r.symbol,
                "action": r.action,
                "rsi_bucket": r.rsi_bucket,
                "trend": r.trend,
                "volume_elevated": r.volume_elevated,
                "confidence": r.confidence,
                "outcome": r.outcome,
                "pnl_usd": r.pnl_usd,
                "holding_hours": r.holding_hours,
                "memory_id": r.id,
            }
            for r in rows
        ]

        try:
            embeddings = await self._embed_batch(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[SemanticMemory] warm_up embedding failed: {exc}")
            self._warmed_up = True
            return 0

        for text, emb, meta in zip(texts, embeddings, metas):
            self._entries.append(_Entry(text=text, embedding=emb, metadata=meta))

        self._warmed_up = True
        logger.info(
            f"[SemanticMemory] warm_up complete — {len(self._entries)} memories indexed "
            f"(model={self._model})"
        )
        return len(self._entries)

    # -----------------------------------------------------------------------
    # Write path: adicionar nova memória resolvida
    # -----------------------------------------------------------------------

    async def add(
        self,
        symbol: str,
        action: str,
        rsi: Optional[float],
        trend: str,
        volume_elevated: Optional[bool],
        confidence: float,
        outcome: str,
        pnl_usd: Optional[float],
        holding_hours: Optional[float],
        memory_id: Optional[int] = None,
    ) -> None:
        """
        Adiciona um trade resolvido ao índice em tempo real.
        Chamado por Cyclops/NickFury após resolver o outcome de uma posição.
        Falha silenciosamente.
        """
        text = build_memory_text(
            symbol=symbol, action=action, rsi=rsi, trend=trend,
            volume_elevated=volume_elevated, confidence=confidence,
            outcome=outcome, pnl_usd=pnl_usd, holding_hours=holding_hours,
        )
        try:
            emb = await self._embed_single(text)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[SemanticMemory] add() embed failed: {exc}")
            return

        self._entries.append(_Entry(
            text=text,
            embedding=emb,
            metadata={
                "symbol": symbol, "action": action, "rsi_bucket": rsi,
                "trend": trend, "volume_elevated": volume_elevated,
                "confidence": confidence, "outcome": outcome,
                "pnl_usd": pnl_usd, "holding_hours": holding_hours,
                "memory_id": memory_id,
            },
        ))
        logger.debug(
            f"[SemanticMemory] Added {action} {symbol} {outcome} "
            f"(total={len(self._entries)})"
        )

    # -----------------------------------------------------------------------
    # Read path: busca semântica + snippet de contexto
    # -----------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 8,
        filter_fn: Any = None,
    ) -> list[dict[str, Any]]:
        """
        Busca as ``limit`` entradas mais similares por similaridade cossenoidal.

        Parâmetros:
            query     : texto da query (usar build_query_text())
            limit     : número máximo de resultados
            filter_fn : callable(metadata) → bool para filtrar entradas

        Retorna lista de dicts com {score, text, **metadata}.
        """
        if not self._entries:
            return []

        try:
            q_emb = await self._embed_single(query)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[SemanticMemory] search embed failed: {exc}")
            return []

        # Cosine similarity: puro Python (evita import numpy aqui; numpy está disponível
        # via pandas mas importamos inline para não quebrar se ausente)
        try:
            import numpy as np  # noqa: WPS433
            all_embs = np.array([e.embedding for e in self._entries], dtype=np.float32)
            q = np.array(q_emb, dtype=np.float32)
            norms = np.linalg.norm(all_embs, axis=1)
            q_norm = float(np.linalg.norm(q))
            if q_norm < 1e-10:
                return []
            sims = (all_embs @ q) / (norms * q_norm + 1e-10)
            scores = sims.tolist()
        except ImportError:
            # Fallback puro Python (mais lento mas funciona sem numpy)
            q_norm = math.sqrt(sum(x * x for x in q_emb))
            if q_norm < 1e-10:
                return []
            scores = []
            for entry in self._entries:
                e = entry.embedding
                e_norm = math.sqrt(sum(x * x for x in e))
                dot = sum(a * b for a, b in zip(q_emb, e))
                scores.append(dot / (e_norm * q_norm + 1e-10))

        # Filtra e ordena
        candidates = [
            (float(scores[i]), self._entries[i])
            for i in range(len(self._entries))
            if filter_fn is None or filter_fn(self._entries[i].metadata)
        ]
        candidates.sort(key=lambda x: -x[0])

        return [
            {"score": score, "text": entry.text, **entry.metadata}
            for score, entry in candidates[:limit]
        ]

    async def build_context_snippet(
        self,
        symbol: str,
        action: str,
        rsi: Optional[float],
        trend: str,
        volume_elevated: Optional[bool],
        confidence: float,
        limit: int = 8,
    ) -> str:
        """
        Constrói o snippet de memória episódica para injeção no prompt do Vision.

        Formato idêntico ao AgentMemoryStore.build_context_snippet() para
        compatibilidade com o prompt existente.

        Retorna string vazia se store vazio ou embedding falhar.
        """
        query = build_query_text(
            symbol=symbol, action=action, rsi=rsi, trend=trend,
            volume_elevated=volume_elevated, confidence=confidence,
        )
        results = await self.search(
            query=query,
            limit=limit,
            filter_fn=lambda m: m.get("outcome") in ("WIN", "LOSS", "NEUTRAL"),
        )

        if not results:
            return ""

        wins = sum(1 for r in results if r["outcome"] == "WIN")
        losses = sum(1 for r in results if r["outcome"] == "LOSS")
        neutrals = sum(1 for r in results if r["outcome"] == "NEUTRAL")
        pnls = [r["pnl_usd"] for r in results if r.get("pnl_usd") is not None]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0.0
        holds = [r["holding_hours"] for r in results if r.get("holding_hours") is not None]
        avg_hold = sum(holds) / len(holds) if holds else None

        decided = wins + losses
        wr_str = f"{100.0 * wins / decided:.1f}%" if decided > 0 else "N/A"
        hold_str = f"{avg_hold:.1f}h" if avg_hold else "N/A"
        pnl_sign = "+" if avg_pnl >= 0 else ""
        rsi_str = f"RSI≈{int(round(rsi))}" if rsi is not None else "RSI=?"

        header = (
            f"[SemanticMemory] {len(results)} similar {action.upper()} {symbol.upper()} "
            f"({rsi_str}, {trend.upper()}):"
        )
        stats = (
            f"Win rate: {wr_str} ({wins}W / {losses}L / {neutrals}N) | "
            f"Avg PnL: {pnl_sign}${avg_pnl:.2f} | Avg hold: {hold_str}"
        )

        # Últimos 3 resultados no formato "WIN +$2.30, LOSS -$1.10"
        recent_parts: list[str] = []
        for r in results[:3]:
            pnl = r.get("pnl_usd")
            if pnl is not None:
                sign = "+" if pnl >= 0 else ""
                recent_parts.append(f"{r['outcome']} {sign}${pnl:.2f}")
            else:
                recent_parts.append(r["outcome"])
        recent_line = "Recent: " + ", ".join(recent_parts) if recent_parts else ""

        parts = [header, stats]
        if recent_line:
            parts.append(recent_line)
        parts.append(
            f"[Semantic score range: {results[0]['score']:.3f}–{results[-1]['score']:.3f}]"
        )
        return "\n".join(parts)

    # -----------------------------------------------------------------------
    # Embedding helpers (OpenAI direto — sem langchain)
    # -----------------------------------------------------------------------

    async def _embed_single(self, text: str) -> list[float]:
        """Embeda um único texto. Lança exceção em caso de falha."""
        return (await self._embed_batch([text]))[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embeda uma lista de textos em batch, respeitando o limite do modelo.
        Retorna lista de embeddings na mesma ordem.
        """
        from openai import AsyncOpenAI  # noqa: WPS433
        from src.config.settings import settings  # noqa: WPS433

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY não configurada — semantic memory desabilitada")

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        results: list[list[float]] = []

        # Processa em batches para respeitar limite da API
        for i in range(0, len(texts), self._EMBED_BATCH_SIZE):
            batch = texts[i: i + self._EMBED_BATCH_SIZE]
            resp = await client.embeddings.create(
                model=self._model,
                input=batch,
            )
            # Ordena pelo index para garantir consistência
            sorted_data = sorted(resp.data, key=lambda d: d.index)
            results.extend(d.embedding for d in sorted_data)

        return results

    # -----------------------------------------------------------------------
    # Utilidades
    # -----------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def is_ready(self) -> bool:
        """True se warm_up já foi executado (independente do resultado)."""
        return self._warmed_up
