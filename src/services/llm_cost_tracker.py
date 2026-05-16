"""
src/services/llm_cost_tracker.py
==================================
Story 147 — LLM Cost Dashboard.

Subscriber do evento `llm.call.completed` (publicado pelo LLMClient a cada
chamada de LLM) que mantém agregações em memória para monitoramento de custo
e uso de tokens em tempo real.

Expõe:
  - `get_llm_cost_tracker()` — singleton global
  - `LLMCostTracker.summary()` — dict com todas as métricas
  - `LLMCostTracker.reset()` — zera contadores (para testes)

Integração
----------
O tracker se registra automaticamente no EventBus quando criado.
O endpoint GET /api/cost no dashboard chama `get_llm_cost_tracker().summary()`.

Métricas mantidas
-----------------
  - Por sessão: total_calls, total_cost_usd, total_tokens_in, total_tokens_out
  - Por modelo: calls, cost_usd, tokens_in, tokens_out
  - Por agente: calls, cost_usd
  - Últimas N chamadas (rolling window): para análise de tendência
  - Custo médio por chamada, custo/hora (estimado)
  - Chamada mais cara da sessão
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# LLMCostTracker
# ---------------------------------------------------------------------------

_ROLLING_WINDOW = 200  # últimas N chamadas na janela deslizante


class LLMCostTracker:
    """
    Agrega métricas de custo de LLM a partir de eventos llm.call.completed.

    Thread-safe para asyncio single event loop.
    """

    def __init__(self) -> None:
        self._started_at: datetime = datetime.now(timezone.utc)
        self._total_calls: int = 0
        self._total_cost_usd: float = 0.0
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._total_elapsed_ms: float = 0.0

        # Agregações por modelo
        self._by_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "elapsed_ms": 0.0}
        )

        # Agregações por agente
        self._by_agent: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}
        )

        # Agregações por provedor
        self._by_provider: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "cost_usd": 0.0}
        )

        # Rolling window das últimas N chamadas
        self._recent_calls: deque[dict[str, Any]] = deque(maxlen=_ROLLING_WINDOW)

        # Chamada mais cara
        self._most_expensive: Optional[dict[str, Any]] = None

        # Falhas (chamadas que não geraram custo — indica erro LLM)
        self._failed_calls: int = 0

        self._subscribed = False

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def handle_event(self, payload: dict[str, Any]) -> None:
        """
        Handler síncrono chamado pelo EventBus quando llm.call.completed é publicado.
        payload = {provider, model, agent_id, tokens_in, tokens_out, cost_usd, elapsed_ms}
        """
        try:
            provider = payload.get("provider", "unknown")
            model = payload.get("model", "unknown")
            agent_id = payload.get("agent_id", "") or "unknown"
            tokens_in = int(payload.get("tokens_in", 0))
            tokens_out = int(payload.get("tokens_out", 0))
            cost_usd = float(payload.get("cost_usd", 0.0))
            elapsed_ms = float(payload.get("elapsed_ms", 0.0))

            if tokens_in == 0 and tokens_out == 0:
                self._failed_calls += 1
                return

            # Session totals
            self._total_calls += 1
            self._total_cost_usd += cost_usd
            self._total_tokens_in += tokens_in
            self._total_tokens_out += tokens_out
            self._total_elapsed_ms += elapsed_ms

            # By model
            m = self._by_model[model]
            m["calls"] += 1
            m["cost_usd"] = round(m["cost_usd"] + cost_usd, 8)
            m["tokens_in"] += tokens_in
            m["tokens_out"] += tokens_out
            m["elapsed_ms"] = round(m["elapsed_ms"] + elapsed_ms, 1)

            # By agent
            a = self._by_agent[agent_id]
            a["calls"] += 1
            a["cost_usd"] = round(a["cost_usd"] + cost_usd, 8)
            a["tokens_in"] += tokens_in
            a["tokens_out"] += tokens_out

            # By provider
            p = self._by_provider[provider]
            p["calls"] += 1
            p["cost_usd"] = round(p["cost_usd"] + cost_usd, 8)

            # Recent calls
            call_record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "model": model,
                "agent_id": agent_id,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "elapsed_ms": elapsed_ms,
            }
            self._recent_calls.append(call_record)

            # Most expensive call
            if (
                self._most_expensive is None
                or cost_usd > self._most_expensive["cost_usd"]
            ):
                self._most_expensive = call_record

        except Exception as exc:  # noqa: BLE001
            logger.debug("[LLMCostTracker] Error handling event: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Retorna dict com todas as métricas para /api/cost.
        """
        now = datetime.now(timezone.utc)
        elapsed_s = max(1.0, (now - self._started_at).total_seconds())
        elapsed_hours = elapsed_s / 3600.0

        avg_cost = (
            round(self._total_cost_usd / self._total_calls, 8)
            if self._total_calls > 0
            else 0.0
        )
        cost_per_hour = round(self._total_cost_usd / elapsed_hours, 6)
        avg_latency_ms = (
            round(self._total_elapsed_ms / self._total_calls, 1)
            if self._total_calls > 0
            else 0.0
        )

        # Top 5 modelos por custo
        top_models = sorted(
            [{"model": k, **v} for k, v in self._by_model.items()],
            key=lambda x: x["cost_usd"],
            reverse=True,
        )[:5]

        # Top 5 agentes por custo
        top_agents = sorted(
            [{"agent_id": k, **v} for k, v in self._by_agent.items()],
            key=lambda x: x["cost_usd"],
            reverse=True,
        )[:5]

        return {
            "session": {
                "started_at": self._started_at.isoformat(),
                "uptime_s": round(elapsed_s, 1),
                "total_calls": self._total_calls,
                "failed_calls": self._failed_calls,
                "total_cost_usd": round(self._total_cost_usd, 6),
                "total_tokens_in": self._total_tokens_in,
                "total_tokens_out": self._total_tokens_out,
                "total_tokens": self._total_tokens_in + self._total_tokens_out,
                "avg_cost_per_call_usd": avg_cost,
                "cost_per_hour_usd": cost_per_hour,
                "avg_latency_ms": avg_latency_ms,
            },
            "by_model": top_models,
            "by_agent": top_agents,
            "by_provider": [
                {"provider": k, **v} for k, v in self._by_provider.items()
            ],
            "most_expensive_call": self._most_expensive,
            "recent_calls": list(self._recent_calls)[-20:],  # últimas 20
        }

    def reset(self) -> None:
        """Zera todos os contadores — útil para testes."""
        self.__init__()

    def register(self) -> None:
        """
        Registra no EventBus global como subscriber de llm.call.completed.
        Idempotente — chama no máximo uma vez.
        """
        if self._subscribed:
            return
        try:
            from src.services.event_bus import get_event_bus
            bus = get_event_bus()
            bus.subscribe("llm.call.completed", self.handle_event)
            self._subscribed = True
            logger.info("[LLMCostTracker] Subscribed to llm.call.completed")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLMCostTracker] Could not subscribe to EventBus: %s", exc)

    def unregister(self) -> None:
        """Remove a subscrição do EventBus."""
        if not self._subscribed:
            return
        try:
            from src.services.event_bus import get_event_bus
            bus = get_event_bus()
            bus.unsubscribe("llm.call.completed", self.handle_event)
            self._subscribed = False
        except Exception as exc:  # noqa: BLE001
            logger.debug("[LLMCostTracker] Could not unsubscribe: %s", exc)

    @property
    def is_subscribed(self) -> bool:
        return self._subscribed


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_tracker: Optional[LLMCostTracker] = None


def get_llm_cost_tracker(auto_register: bool = True) -> LLMCostTracker:
    """
    Retorna o singleton global do LLMCostTracker.
    Se `auto_register=True`, registra automaticamente no EventBus.
    """
    global _tracker
    if _tracker is None:
        _tracker = LLMCostTracker()
        if auto_register:
            _tracker.register()
    return _tracker


def reset_llm_cost_tracker() -> None:
    """Reseta o singleton — para testes."""
    global _tracker
    if _tracker is not None:
        _tracker.unregister()
    _tracker = None
