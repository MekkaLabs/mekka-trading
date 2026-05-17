"""
src/services/analysis_prompt_cache.py
========================================
Story 182 — AnalysisPromptCache: prompt caching + cache warming.

Inspirado no padrão Aider Prompt Caching:
  "Aider enables caching of prompts and includes a number of times to
   ping at 5-minute intervals to keep prompt cache warm."

No Aider, o cache warm reduz a latência da primeira call de ~3s para ~300ms
mantendo o contexto de sistema quente no provider LLM.

No Mekka, o equivalente é pré-computar o bloco de análise de macro context
(BTC dominance, regime summary, fear & greed, open interest, funding rates)
e mantê-lo em cache por TTL configurável.

Vision lê do cache ao invés de refazer o fetch de dados de mercado, economizando
~800ms por ciclo em condições normais.

Arquitetura
-----------
  AnalysisPromptCache — cache em memória com TTL e background refresh
    ├── store(key, content, ttl_seconds) — salva no cache
    ├── get(key) → str | None             — lê do cache se não-expirado
    ├── get_or_build(key, builder_fn)     — lê cache ou chama builder async
    ├── warm(keys, builders)              — pre-aquece múltiplas entradas
    └── summary()                         — estatísticas do cache

Keys padrão usadas no pipeline:
  "macro_context"       — BTC dominance + fear & greed + funding rates
  "regime_summary"      — MarketRegimeDetector último resultado
  "open_interest_{SYM}" — OI snapshot por símbolo
  "analyst_hints"       — TradeAnnotationWatcher.get_all_active() formatado

Uso em Vision.run()
-------------------
    from src.services.analysis_prompt_cache import get_analysis_prompt_cache

    cache = get_analysis_prompt_cache()
    macro_block = await cache.get_or_build(
        "macro_context",
        builder=_build_macro_context,
        ttl=600,  # 10 minutos
    )
    if macro_block:
        prompt = prompt + "\n\n" + macro_block
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """
    Entrada individual no cache de prompt.
    """
    key: str
    content: str
    created_at: float
    ttl_seconds: float
    hit_count: int = 0
    last_accessed: float = field(default_factory=time.monotonic)

    @property
    def is_expired(self) -> bool:
        """True se a entrada expirou."""
        if self.ttl_seconds <= 0:
            return False  # TTL 0 = nunca expira
        return (time.monotonic() - self.created_at) > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def remaining_ttl(self) -> float:
        if self.ttl_seconds <= 0:
            return float("inf")
        remaining = self.ttl_seconds - self.age_seconds
        return max(0.0, remaining)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "content_len": len(self.content),
            "age_seconds": round(self.age_seconds, 1),
            "remaining_ttl": round(self.remaining_ttl, 1),
            "hit_count": self.hit_count,
            "is_expired": self.is_expired,
        }


# ---------------------------------------------------------------------------
# AnalysisPromptCache
# ---------------------------------------------------------------------------

class AnalysisPromptCache:
    """
    Cache em memória para blocos de prompt pré-computados.

    Padrão Aider Prompt Caching: mantém contexto quente para reduzir
    latência de ciclos consecutivos e custo de LLM calls.
    """

    def __init__(self, default_ttl: float = 600.0) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits: int = 0
        self._misses: int = 0
        self._builds: int = 0
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    def store(self, key: str, content: str, ttl_seconds: float | None = None) -> CacheEntry:
        """
        Armazena um bloco de prompt no cache.

        Args:
            key: chave de identificação (ex: "macro_context", "regime_summary")
            content: texto a cachear (bloco de prompt formatado)
            ttl_seconds: tempo de vida; None usa default_ttl

        Returns:
            CacheEntry criada.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        entry = CacheEntry(
            key=key,
            content=content,
            created_at=time.monotonic(),
            ttl_seconds=ttl,
        )
        self._cache[key] = entry
        logger.debug(
            f"[AnalysisPromptCache] stored '{key}' "
            f"({len(content)} chars, TTL={ttl}s)"
        )
        return entry

    def get(self, key: str) -> Optional[str]:
        """
        Lê do cache se a entrada existe e não expirou.

        Returns:
            O conteúdo cacheado ou None se cache miss/expirado.
        """
        entry = self._cache.get(key)
        if entry is None or entry.is_expired:
            self._misses += 1
            if entry and entry.is_expired:
                del self._cache[key]
                logger.debug(f"[AnalysisPromptCache] expired '{key}'")
            return None

        entry.hit_count += 1
        entry.last_accessed = time.monotonic()
        self._hits += 1
        logger.debug(
            f"[AnalysisPromptCache] HIT '{key}' "
            f"(age={entry.age_seconds:.1f}s, hits={entry.hit_count})"
        )
        return entry.content

    async def get_or_build(
        self,
        key: str,
        builder: Callable[[], Awaitable[str] | str],
        ttl_seconds: float | None = None,
    ) -> Optional[str]:
        """
        Lê do cache ou constrói o conteúdo via builder async/sync.

        Args:
            key: chave do cache
            builder: coroutine ou função que retorna o conteúdo
            ttl_seconds: TTL para a nova entrada

        Returns:
            Conteúdo (do cache ou recém-construído), ou None se builder falhar.
        """
        # Cache hit
        cached = self.get(key)
        if cached is not None:
            return cached

        # Cache miss — constrói
        self._builds += 1
        try:
            result = builder()
            if asyncio.iscoroutine(result):
                content = await result
            else:
                content = result

            if content:
                self.store(key, str(content), ttl_seconds)
                return str(content)
            return None

        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[AnalysisPromptCache] builder for '{key}' failed: {exc}")
            return None

    async def warm(
        self,
        builders: dict[str, Callable[[], Awaitable[str] | str]],
        ttl_seconds: float | None = None,
    ) -> dict[str, bool]:
        """
        Pre-aquece múltiplas entradas do cache em paralelo.

        Args:
            builders: {key: builder_fn, ...}
            ttl_seconds: TTL para todas as entradas aquecidas

        Returns:
            {key: bool} — True se cache warm bem-sucedido
        """
        async def _warm_one(key: str, builder: Any) -> tuple[str, bool]:
            try:
                result = await self.get_or_build(key, builder, ttl_seconds)
                return key, result is not None
            except Exception:  # noqa: BLE001
                return key, False

        tasks = [_warm_one(k, b) for k, b in builders.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        status = {}
        for res in results:
            if isinstance(res, tuple):
                k, ok = res
                status[k] = ok
            elif isinstance(res, Exception):
                status["unknown"] = False
        return status

    def invalidate(self, key: str) -> bool:
        """Remove uma entrada do cache. Retorna True se existia."""
        existed = key in self._cache
        self._cache.pop(key, None)
        return existed

    def invalidate_all(self) -> int:
        """Remove todas as entradas. Retorna número de entradas removidas."""
        count = len(self._cache)
        self._cache.clear()
        return count

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def summary(self) -> dict:
        """Estatísticas do cache."""
        entries = []
        for entry in self._cache.values():
            entries.append(entry.to_dict())

        return {
            "total_entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "builds": self._builds,
            "hit_rate": round(self.hit_rate, 3),
            "default_ttl": self._default_ttl,
            "entries": entries,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_cache: Optional[AnalysisPromptCache] = None


def get_analysis_prompt_cache(default_ttl: float = 600.0) -> AnalysisPromptCache:
    """
    Retorna o singleton global do AnalysisPromptCache.

    Args:
        default_ttl: TTL em segundos (default 600 = 10 minutos).
                     Só usado na criação — chamadas subsequentes ignoram.
    """
    global _cache
    if _cache is None:
        try:
            from src.config.settings import settings
            ttl = float(getattr(settings, "analysis_cache_ttl_seconds", default_ttl))
        except Exception:  # noqa: BLE001
            ttl = default_ttl
        _cache = AnalysisPromptCache(default_ttl=ttl)
    return _cache


def reset_analysis_prompt_cache() -> None:
    """Reseta o singleton — para testes."""
    global _cache
    _cache = None
