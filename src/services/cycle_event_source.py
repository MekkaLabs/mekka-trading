"""
src/services/cycle_event_source.py
=====================================
Story 196 — CycleEventSource: tagging de origem para eventos do CycleEventLog.

Inspirado no padrão OpenHands EventSource:
  "Events are tagged with an EventSource indicating their origin:
   EventSource.USER   — user-initiated actions (MessageAction, ChangeAgentStateAction)
   EventSource.AGENT  — agent-generated actions (all action types, agent messages)
   EventSource.ENVIRONMENT — runtime/system feedback (all observation types)

   This allows filtering and routing based on who produced the event."

No OpenHands:
  class EventSource(str, Enum):
      USER = "user"
      AGENT = "agent"
      ENVIRONMENT = "environment"

No Mekka, o equivalente é:
  CycleEventSource mapeia os agentes e componentes do pipeline:
    NICKFURY   — orquestrador principal (ciclo, scheduling, roteamento)
    VISION     — geração de sinal (LLM call, pre-reasoning, MoA)
    BATMAN     — risk gate (validação de risco, position sizing)
    IRONMAN    — execução (orders, fills, position updates)
    SYSTEM     — serviços internos (linter, budget guard, incremental skip)
    USER       — input externo (trade hints, annotations, manual override)
    MONITOR    — observabilidade (dashboard, SSE, metrics)

  CycleEventSourceTagger adiciona o campo `source` a eventos do CycleEventLog
  sem quebrar a interface existente. É usado em NickFury para enriquecer
  os eventos antes de emitir.

  Formato no log:
    "SIGNAL_EMITTED | BTC | source=VISION | cycle=abc123"

Arquitetura
-----------
  CycleEventSource     — enum dos agentes/componentes fonte
  SourcedEvent         — wrapper de CycleEvent com campo source
  CycleEventSourceTagger
    ├── tag(event, source) → SourcedEvent
    ├── emit_sourced(log, event_type, source, symbol, **payload)
    └── filter_by_source(events, source) → list[SourcedEvent]
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# CycleEventSource
# ---------------------------------------------------------------------------

class CycleEventSource(str, Enum):
    """
    Fonte/origem de um evento no pipeline Mekka.

    Mapeamento com OpenHands EventSource:
      NICKFURY  ←→ AGENT (orquestrador — inicia ciclos, roteia eventos)
      VISION    ←→ AGENT (agente LLM — gera sinais, pre-reasoning)
      BATMAN    ←→ AGENT (agente risk gate — valida e filtra sinais)
      IRONMAN   ←→ AGENT (agente executor — places orders)
      SYSTEM    ←→ ENVIRONMENT (serviços internos: linter, guards, cache)
      USER      ←→ USER (input externo: hints, annotations, manual)
      MONITOR   ←→ ENVIRONMENT (observabilidade: dashboard, SSE, metrics)
    """
    NICKFURY = "NICKFURY"
    VISION = "VISION"
    BATMAN = "BATMAN"
    IRONMAN = "IRONMAN"
    SYSTEM = "SYSTEM"
    USER = "USER"
    MONITOR = "MONITOR"

    @property
    def category(self) -> str:
        """Categoria de alto nível (AGENT / ENVIRONMENT / USER)."""
        if self in (CycleEventSource.NICKFURY, CycleEventSource.VISION,
                    CycleEventSource.BATMAN, CycleEventSource.IRONMAN):
            return "AGENT"
        if self in (CycleEventSource.SYSTEM, CycleEventSource.MONITOR):
            return "ENVIRONMENT"
        return "USER"


# ---------------------------------------------------------------------------
# SourcedEvent — CycleEvent enriquecido com campo source
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourcedEvent:
    """
    Wrapper de um evento com campo source explícito.

    Pode ser criado a partir de qualquer objeto com campos básicos de evento,
    ou construído diretamente com os campos necessários.
    """
    event_type: str
    symbol: str
    cycle_id: str
    source: CycleEventSource
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
    event_id: str = ""

    def to_log_line(self) -> str:
        """Linha de log compacta."""
        return (
            f"{self.event_type} | {self.symbol} | "
            f"source={self.source.value} | cycle={self.cycle_id[:8]}"
        )

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "source": self.source.value,
            "source_category": self.source.category,
            "payload": self.payload,
            "event_id": self.event_id,
        }


# ---------------------------------------------------------------------------
# CycleEventSourceTagger
# ---------------------------------------------------------------------------

class CycleEventSourceTagger:
    """
    Adiciona campo `source` a eventos do CycleEventLog.

    Padrão OpenHands EventSource: eventos são taggeados com a origem
    para permitir filtragem, roteamento e auditoria por componente.

    Uso:
        tagger = get_event_source_tagger()
        sourced = tagger.emit_sourced(
            log=get_cycle_event_log(),
            event_type=CycleEventType.SIGNAL_EMITTED,
            source=CycleEventSource.VISION,
            symbol="BTC",
            cycle_id="abc",
            action="LONG",
            confidence=0.85,
        )
    """

    def __init__(self) -> None:
        self._sourced_events: List[SourcedEvent] = []
        self._max_events: int = 500
        self._total_tagged: int = 0
        self._by_source: Dict[str, int] = {}

    def tag(
        self,
        event_type: str,
        symbol: str,
        cycle_id: str,
        source: CycleEventSource,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
    ) -> SourcedEvent:
        """
        Cria um SourcedEvent com a fonte especificada.

        Args:
            event_type: Tipo do evento (string ou CycleEventType)
            symbol:     Símbolo do ativo
            cycle_id:   ID do ciclo
            source:     Fonte do evento (CycleEventSource)
            payload:    Payload adicional
            event_id:   ID do evento original (se disponível)

        Returns:
            SourcedEvent criado.
        """
        sourced = SourcedEvent(
            event_type=str(event_type),
            symbol=symbol.upper() if symbol else "",
            cycle_id=cycle_id,
            source=source,
            payload=payload or {},
            event_id=event_id,
        )
        self._sourced_events.append(sourced)
        if len(self._sourced_events) > self._max_events:
            self._sourced_events = self._sourced_events[-self._max_events:]

        self._total_tagged += 1
        self._by_source[source.value] = self._by_source.get(source.value, 0) + 1
        logger.debug(f"[EventSourceTagger] {sourced.to_log_line()}")
        return sourced

    def emit_sourced(
        self,
        log: Any,
        event_type: Any,
        source: CycleEventSource,
        symbol: str,
        cycle_id: str = "",
        **payload: Any,
    ) -> Optional[SourcedEvent]:
        """
        Emite um evento no CycleEventLog E cria o SourcedEvent correspondente.

        Args:
            log:        Instância do CycleEventLog
            event_type: CycleEventType ou string
            source:     Fonte do evento
            symbol:     Símbolo
            cycle_id:   ID do ciclo
            **payload:  Campos extras para o evento

        Returns:
            SourcedEvent criado, ou None em caso de erro (fail-silent).
        """
        try:
            # Emite no CycleEventLog padrão
            if log is not None:
                log.emit(event_type, symbol=symbol, cycle_id=cycle_id, **payload)

            # Cria SourcedEvent taggeado
            return self.tag(
                event_type=str(event_type),
                symbol=symbol,
                cycle_id=cycle_id,
                source=source,
                payload=dict(payload),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[EventSourceTagger] emit_sourced failed: {exc}")
            return None

    def filter_by_source(
        self,
        source: CycleEventSource,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[SourcedEvent]:
        """
        Filtra eventos por fonte e opcionalmente por símbolo.

        Args:
            source: Fonte a filtrar
            symbol: Se fornecido, filtra também por símbolo
            limit:  Máximo de eventos retornados (mais recentes)

        Returns:
            Lista de SourcedEvent filtrados.
        """
        events = [e for e in self._sourced_events if e.source == source]
        if symbol:
            sym = symbol.upper()
            events = [e for e in events if e.symbol == sym]
        return events[-limit:]

    def filter_by_category(
        self,
        category: str,
        limit: int = 50,
    ) -> List[SourcedEvent]:
        """Filtra eventos por categoria (AGENT / ENVIRONMENT / USER)."""
        events = [
            e for e in self._sourced_events
            if e.source.category == category.upper()
        ]
        return events[-limit:]

    def get_recent(self, limit: int = 20) -> List[SourcedEvent]:
        """Retorna os N eventos mais recentes."""
        return self._sourced_events[-limit:]

    def summary(self) -> dict:
        return {
            "total_tagged": self._total_tagged,
            "total_stored": len(self._sourced_events),
            "by_source": self._by_source,
            "by_category": {
                cat: sum(
                    v for k, v in self._by_source.items()
                    if CycleEventSource(k).category == cat
                )
                for cat in ("AGENT", "ENVIRONMENT", "USER")
                if any(
                    CycleEventSource(k).category == cat
                    for k in self._by_source
                )
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tagger: Optional[CycleEventSourceTagger] = None


def get_event_source_tagger() -> CycleEventSourceTagger:
    """Retorna o singleton global do CycleEventSourceTagger."""
    global _tagger
    if _tagger is None:
        _tagger = CycleEventSourceTagger()
    return _tagger


def reset_event_source_tagger() -> None:
    """Reseta o singleton — para testes."""
    global _tagger
    _tagger = None
