"""
src/services/cycle_event_log.py
================================
Story 154 — CycleEventLog: Append-Only Event Sourcing do Ciclo de Trading.

Inspirado no EventLog do OpenHands (OpenHands/OpenHands):
  "The event log is append-only and the single source of truth —
   replaying it reconstructs the entire conversation, with state
   changes happening by appending events — never by mutating objects."

Arquitetura:
  NickFury._cycle_for_symbol()
       ↓
  get_cycle_event_log().emit(event_type, symbol, **payload)
       ↓
  CycleEventLog (deque imutável, max 1000 events)
       ↓
  GET /api/events → dashboard / audit / replay

Diferente do MekkaEventBus (pub/sub reativo, Story 136),
o CycleEventLog é:
- Append-only (eventos não são deletados)
- Ordenado cronologicamente (replay determinístico)
- Filtrável por symbol, type, cycle_id
- Exportável como JSONL para persistência externa

Uso típico:
    from src.services.cycle_event_log import get_cycle_event_log, CycleEventType

    log = get_cycle_event_log()
    log.emit(CycleEventType.CYCLE_START, symbol="BTC", cycle_id="abc", equity_usd=10000)
    log.emit(CycleEventType.SIGNAL_EMITTED, symbol="BTC", cycle_id="abc", action="LONG")
    log.emit(CycleEventType.CYCLE_END, symbol="BTC", cycle_id="abc", status="ok")
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Event types (canonical set — extensible via raw strings for ad-hoc events)
# ---------------------------------------------------------------------------

class CycleEventType(str, Enum):
    """Canonical event types emitted by the trading cycle pipeline."""

    # Lifecycle
    CYCLE_START = "CYCLE_START"
    CYCLE_END = "CYCLE_END"
    CYCLE_ERROR = "CYCLE_ERROR"
    CYCLE_SKIPPED = "CYCLE_SKIPPED"

    # Pipeline stages (Action-Observation pattern, inspired by OpenHands)
    ANALYSIS_DONE = "ANALYSIS_DONE"      # ProfessorX / Vision analysis complete
    SIGNAL_EMITTED = "SIGNAL_EMITTED"    # Vision emitted a TradingSignal
    RISK_VERDICT = "RISK_VERDICT"        # Batman risk gate verdict
    EXECUTION_DONE = "EXECUTION_DONE"    # Iron Man execution complete

    # Guard events
    STEP_LIMIT_HIT = "STEP_LIMIT_HIT"   # AgentStepGuard MAX_ITERATIONS hit
    STUCK_LOOP = "STUCK_LOOP"            # AgentStepGuard stuck loop detected

    # Observability
    SLOW_CYCLE = "SLOW_CYCLE"            # Pipeline benchmark slow cycle alert
    REGIME_DETECTED = "REGIME_DETECTED"  # Market regime classification
    MICROAGENT_LOADED = "MICROAGENT_LOADED"  # Microagent prompt injected


# ---------------------------------------------------------------------------
# CycleEvent — immutable dataclass (do NOT mutate after creation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleEvent:
    """
    Immutable event in the cycle event log.

    Fields mirror OpenHands Event: event_type + timestamp + payload.
    `symbol` and `cycle_id` are first-class citizens for filtering.
    """

    event_type: str
    symbol: str
    cycle_id: str
    timestamp: float = field(default_factory=time.time)
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ---------------------------------------------------------------------------
# CycleEventLog — append-only, rolling window
# ---------------------------------------------------------------------------

class CycleEventLog:
    """
    Append-only event log for the trading cycle.

    Design decisions:
    - `deque(maxlen=N)` auto-evicts oldest events when full (rolling window)
    - `frozen=True` on CycleEvent prevents post-creation mutation
    - replay() returns a stable list snapshot (safe for concurrent reads)
    - `emit()` is the single write path — no external append()

    OpenHands reference:
      ConversationState.event_log: append-only EventLog with FIFO lock
      "The only mutable thing in the system is ConversationState"
    """

    _DEFAULT_MAX_EVENTS = 1000

    def __init__(self, max_events: int = _DEFAULT_MAX_EVENTS) -> None:
        self._events: deque[CycleEvent] = deque(maxlen=max_events)
        self._max_events = max_events
        self._total_emitted: int = 0  # monotonic counter (survives eviction)

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def emit(
        self,
        event_type: str,
        symbol: str,
        cycle_id: str = "",
        **payload: Any,
    ) -> CycleEvent:
        """
        Create and append an immutable CycleEvent.

        Returns the created event for optional post-emit inspection.
        Never raises — errors are swallowed to avoid breaking the
        trading cycle (fail-silent pattern, same as PipelineBenchmark).
        """
        try:
            evt = CycleEvent(
                event_type=str(event_type),
                symbol=symbol,
                cycle_id=cycle_id,
                payload=payload,
            )
            self._events.append(evt)
            self._total_emitted += 1
            return evt
        except Exception:  # noqa: BLE001
            # Swallow silently — monitoring must never break trading
            return CycleEvent(
                event_type="EMIT_ERROR",
                symbol=symbol,
                cycle_id=cycle_id,
            )

    # ------------------------------------------------------------------
    # Read paths (all return stable list snapshots)
    # ------------------------------------------------------------------

    def replay(self) -> list[CycleEvent]:
        """Return full chronological list of current events (snapshot)."""
        return list(self._events)

    def filter_by_symbol(self, symbol: str) -> list[CycleEvent]:
        """All events for a specific trading symbol."""
        return [e for e in self._events if e.symbol == symbol]

    def filter_by_type(self, event_type: str) -> list[CycleEvent]:
        """All events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]

    def filter_by_cycle(self, cycle_id: str) -> list[CycleEvent]:
        """All events in a specific cycle (deterministic replay per cycle)."""
        return [e for e in self._events if e.cycle_id == cycle_id]

    def last_n(self, n: int) -> list[CycleEvent]:
        """Last N events (most recent first when reversed)."""
        events = list(self._events)
        return events[-n:] if n < len(events) else events

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    @property
    def total_events(self) -> int:
        """Current events in the window (≤ max_events)."""
        return len(self._events)

    @property
    def total_emitted(self) -> int:
        """Monotonic count of all events ever emitted (survives eviction)."""
        return self._total_emitted

    def summary(self) -> dict[str, Any]:
        """Summary for GET /api/events endpoint."""
        events = list(self._events)
        by_type: dict[str, int] = {}
        by_symbol: dict[str, int] = {}
        for e in events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            by_symbol[e.symbol] = by_symbol.get(e.symbol, 0) + 1

        # Top 10 symbols by event count
        top_symbols = dict(
            sorted(by_symbol.items(), key=lambda x: -x[1])[:10]
        )

        return {
            "total_events_in_window": len(events),
            "total_emitted_all_time": self._total_emitted,
            "window_capacity": self._max_events,
            "by_type": by_type,
            "top_symbols": top_symbols,
            "recent_events": [e.to_dict() for e in events[-50:]],
        }

    def to_jsonl(self) -> str:
        """Export all current events as JSONL (one JSON object per line)."""
        return "\n".join(e.to_json() for e in self._events)

    def cycle_summary(self, cycle_id: str) -> dict[str, Any]:
        """
        Reconstruct the full state of a single cycle by replaying its events.
        Equivalent to OpenHands' deterministic replay of EventLog.
        """
        events = self.filter_by_cycle(cycle_id)
        if not events:
            return {"cycle_id": cycle_id, "events": [], "found": False}

        stages = [e.event_type for e in events]
        symbol = events[0].symbol if events else ""
        start_ts = events[0].timestamp if events else 0.0
        end_ts = events[-1].timestamp if events else 0.0

        return {
            "cycle_id": cycle_id,
            "symbol": symbol,
            "found": True,
            "event_count": len(events),
            "stages_completed": stages,
            "duration_s": round(end_ts - start_ts, 3),
            "events": [e.to_dict() for e in events],
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[CycleEventLog] = None


def get_cycle_event_log(max_events: int = CycleEventLog._DEFAULT_MAX_EVENTS) -> CycleEventLog:
    """
    Return the global CycleEventLog singleton.

    `max_events` is only respected on first call (construction).
    Subsequent calls return the existing instance unchanged.
    """
    global _instance
    if _instance is None:
        _instance = CycleEventLog(max_events=max_events)
    return _instance


def reset_cycle_event_log() -> None:
    """Destroy singleton — used in tests to reset state between cases."""
    global _instance
    _instance = None
