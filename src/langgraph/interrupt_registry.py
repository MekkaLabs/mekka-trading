"""
src/langgraph/interrupt_registry.py
=====================================
Story 127 — Registry global de grafos LangGraph em execução.

Permite que TelegramInboundPoller localize e retome (resume) um grafo
que foi pausado via interrupt() esperando aprovação de trade.

Ciclo de vida:
  1. NickFury.run_with_checkpointing() → register(thread_id, graph, saver)
  2. interrupt() suspende o grafo; graph.ainvoke() retorna parcialmente
  3. Operador pressiona ✅/❌ no Telegram
  4. TelegramInbound._handle_callback_query() → get_graph(thread_id) →
     graph.ainvoke(Command(resume=approved), config)
  5. Grafo retoma, processa símbolos restantes, chega em finalize
  6. TelegramInbound chama unregister(thread_id) após ciclo completo

Thread-safety: asyncio single event loop — sem locks necessários.

Nota: Não é persistido — reiniciar o processo limpa o registry.
Grafos com thread_ids ativos no SQLite (estado "interrupted") podem ser
retomados manualmente via CLI se necessário (Story 128+).
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

# thread_id (UUID do ciclo) → (compiled graph, AsyncSqliteSaver)
_REGISTRY: dict[str, tuple[Any, Any]] = {}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def register(thread_id: str, graph: Any, saver: Any) -> None:
    """
    Registra um grafo compilado para o thread_id dado.

    Chamado por NickFury.run_with_checkpointing() logo após compilar o grafo.
    O saver é guardado para que o TelegramInbound possa fechar a conexão ao
    finalizar o ciclo.
    """
    _REGISTRY[thread_id] = (graph, saver)


def get_graph(thread_id: str) -> Optional[Any]:
    """
    Retorna o grafo compilado para thread_id, ou None se não encontrado.

    Chamado por TelegramInbound quando operador pressiona botão de aprovação.
    """
    entry = _REGISTRY.get(thread_id)
    return entry[0] if entry else None


def get_entry(thread_id: str) -> Optional[tuple[Any, Any]]:
    """Retorna (graph, saver) para thread_id, ou None."""
    return _REGISTRY.get(thread_id)


def unregister(thread_id: str) -> Optional[Any]:
    """
    Remove thread_id do registry e retorna o saver para que o chamador
    possa fechar a conexão.

    Retorna o saver (AsyncSqliteSaver) ou None se não encontrado.
    """
    entry = _REGISTRY.pop(thread_id, None)
    return entry[1] if entry else None


def list_active() -> list[str]:
    """
    Retorna lista de thread_ids com grafos ativos.

    Útil para /status do Telegram (Story 128+) e para debugging.
    """
    return list(_REGISTRY.keys())
