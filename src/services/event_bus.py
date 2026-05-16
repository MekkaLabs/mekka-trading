"""
src/services/event_bus.py
==========================
Story 136 — MekkaEventBus: lightweight in-process pub/sub event bus.

Inspirado no padrão CrewAI Event Listeners — permite que agentes publiquem
eventos de ciclo (início, sinal, execução, erro) sem acoplamento direto
entre si. Subscritores recebem eventos de forma assíncrona.

Arquitetura
-----------
  • Pub/sub in-process (asyncio): sem threads, sem brokers externos.
  • Subscritores são coroutines ou callables síncronos.
  • Eventos são dicts simples com chave "event" obrigatória.
  • Erros em subscritores são logados e não propagados (fail-silent).
  • Singleton global via `get_event_bus()`.

Uso
---
    from src.services.event_bus import get_event_bus

    bus = get_event_bus()

    # Subscrever
    async def on_signal(event: dict) -> None:
        print(event["signal"].action)

    bus.subscribe("vision.signal", on_signal)

    # Publicar
    await bus.publish("vision.signal", {"signal": signal, "symbol": "BTC"})

    # Desinscrever
    bus.unsubscribe("vision.signal", on_signal)

Eventos padrão publicados pelo pipeline (convenção)
----------------------------------------------------
    cycle.start          {"cycle_id", "symbol", "timestamp"}
    cycle.end            {"cycle_id", "symbol", "duration_s", "outcome"}
    vision.signal        {"cycle_id", "symbol", "signal"}
    batman.gate          {"cycle_id", "symbol", "approved", "reason"}
    ironman.exec         {"cycle_id", "symbol", "order_id", "action"}
    agent.error          {"cycle_id", "symbol", "agent", "error"}
    layer1.routing       {"cycle_id", "symbol", "regime", "skip_set"}
"""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Callable, Coroutine

from loguru import logger


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Handler = Callable[..., Any]  # sync ou async


# ---------------------------------------------------------------------------
# MekkaEventBus
# ---------------------------------------------------------------------------

class MekkaEventBus:
    """
    In-process asyncio pub/sub event bus para observabilidade do pipeline.

    Thread-safety: asyncio single event loop — sem locks necessários.
    """

    def __init__(self) -> None:
        # topic → lista de handlers
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        # Contadores de eventos publicados por topic (para métricas)
        self._counters: dict[str, int] = defaultdict(int)
        # Wildcard "*" — recebe todos os eventos
        self._wildcards: list[Handler] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: Handler) -> None:
        """
        Registra um handler para o topic.

        Se topic == "*", o handler recebe todos os eventos (wildcard).
        Handlers podem ser sync ou async. O campo "topic" é injetado
        automaticamente no evento antes de chamar o handler.

        Registros duplicados são ignorados.
        """
        if topic == "*":
            if handler not in self._wildcards:
                self._wildcards.append(handler)
        else:
            if handler not in self._subscribers[topic]:
                self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        """Remove um handler de um topic. No-op se não registrado."""
        if topic == "*":
            self._wildcards = [h for h in self._wildcards if h is not handler]
        elif topic in self._subscribers:
            self._subscribers[topic] = [
                h for h in self._subscribers[topic] if h is not handler
            ]

    def subscriber_count(self, topic: str) -> int:
        """Número de handlers registrados para um topic."""
        if topic == "*":
            return len(self._wildcards)
        return len(self._subscribers.get(topic, []))

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, topic: str, payload: dict[str, Any] | None = None) -> int:
        """
        Publica um evento no topic.

        O payload recebe automaticamente o campo "topic" (sobrescreve se presente).
        Todos os handlers registrados para o topic (e wildcards) são chamados
        de forma assíncrona em paralelo via asyncio.gather.

        Erros em handlers individuais são logados e não propagam.

        Retorna: número de handlers notificados com sucesso.
        """
        event = dict(payload or {})
        event["topic"] = topic

        handlers = list(self._subscribers.get(topic, [])) + list(self._wildcards)
        if not handlers:
            self._counters[topic] += 1
            return 0

        tasks = [self._call_handler(h, event) for h in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success = sum(1 for r in results if not isinstance(r, Exception))
        errors = [r for r in results if isinstance(r, Exception)]
        for err in errors:
            logger.warning(f"[EventBus] handler error on '{topic}': {err}")

        self._counters[topic] += 1
        return success

    def publish_sync(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        """
        Versão síncrona de publish — usa asyncio.create_task se há loop rodando,
        ou asyncio.run como fallback. Útil em contextos não-async.
        """
        event = dict(payload or {})
        event["topic"] = topic
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(topic, payload))
        except RuntimeError:
            asyncio.run(self.publish(topic, payload))

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def event_count(self, topic: str) -> int:
        """Total de eventos publicados para o topic nesta sessão."""
        return self._counters.get(topic, 0)

    def topics(self) -> list[str]:
        """Lista de topics que tiveram ao menos 1 evento publicado."""
        return list(self._counters.keys())

    def reset_counters(self) -> None:
        """Zera contadores — útil para testes."""
        self._counters.clear()

    def clear(self) -> None:
        """Remove todos os subscribers e zera contadores — útil para testes."""
        self._subscribers.clear()
        self._wildcards.clear()
        self._counters.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    async def _call_handler(handler: Handler, event: dict[str, Any]) -> None:
        """Chama um handler (sync ou async) com o evento. Propaga exceções."""
        if inspect.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_bus: MekkaEventBus | None = None


def get_event_bus() -> MekkaEventBus:
    """
    Retorna a instância global do MekkaEventBus (singleton).

    Cria na primeira chamada. Thread-safe para asyncio single event loop.
    """
    global _bus
    if _bus is None:
        _bus = MekkaEventBus()
    return _bus


def reset_event_bus() -> None:
    """
    Reseta o singleton — útil para testes que precisam de um bus limpo.
    """
    global _bus
    if _bus is not None:
        _bus.clear()
    _bus = None
