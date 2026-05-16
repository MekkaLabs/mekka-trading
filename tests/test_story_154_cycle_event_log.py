"""
tests/test_story_154_cycle_event_log.py
=========================================
Story 154 — CycleEventLog: Append-Only Event Sourcing.

Inspirado no EventLog do OpenHands:
  "The event log is append-only and the single source of truth —
   replaying it reconstructs the entire conversation."

Testa:
- CycleEvent: frozen, to_dict, to_json
- CycleEventLog: emit, replay, filter_by_*, last_n, summary, to_jsonl
- Append-only semantics (deque rolling window)
- Singleton + reset
- cycle_summary (replay determinístico por cycle_id)
"""

from __future__ import annotations

import json
import time

import pytest


# ---------------------------------------------------------------------------
# CycleEvent
# ---------------------------------------------------------------------------

class TestCycleEvent:
    def test_immutable_frozen(self):
        from src.services.cycle_event_log import CycleEvent
        evt = CycleEvent(event_type="CYCLE_START", symbol="BTC", cycle_id="abc")
        with pytest.raises((AttributeError, TypeError)):
            evt.event_type = "MODIFIED"  # type: ignore[misc]

    def test_to_dict_keys(self):
        from src.services.cycle_event_log import CycleEvent
        evt = CycleEvent(
            event_type="SIGNAL_EMITTED", symbol="ETH", cycle_id="x1",
            payload={"action": "LONG", "confidence": 0.9},
        )
        d = evt.to_dict()
        assert d["event_type"] == "SIGNAL_EMITTED"
        assert d["symbol"] == "ETH"
        assert d["cycle_id"] == "x1"
        assert "timestamp" in d
        assert d["payload"]["action"] == "LONG"

    def test_to_json_valid(self):
        from src.services.cycle_event_log import CycleEvent
        evt = CycleEvent(event_type="CYCLE_END", symbol="SOL", cycle_id="c2")
        parsed = json.loads(evt.to_json())
        assert parsed["event_type"] == "CYCLE_END"
        assert parsed["symbol"] == "SOL"

    def test_timestamp_auto_set(self):
        from src.services.cycle_event_log import CycleEvent
        t0 = time.time()
        evt = CycleEvent(event_type="X", symbol="Y", cycle_id="z")
        assert evt.timestamp >= t0


# ---------------------------------------------------------------------------
# CycleEventType enum
# ---------------------------------------------------------------------------

class TestCycleEventType:
    def test_canonical_types_exist(self):
        from src.services.cycle_event_log import CycleEventType
        assert CycleEventType.CYCLE_START == "CYCLE_START"
        assert CycleEventType.SIGNAL_EMITTED == "SIGNAL_EMITTED"
        assert CycleEventType.RISK_VERDICT == "RISK_VERDICT"
        assert CycleEventType.EXECUTION_DONE == "EXECUTION_DONE"
        assert CycleEventType.CYCLE_END == "CYCLE_END"
        assert CycleEventType.STUCK_LOOP == "STUCK_LOOP"


# ---------------------------------------------------------------------------
# CycleEventLog — emit + read
# ---------------------------------------------------------------------------

class TestCycleEventLog:
    def setup_method(self):
        from src.services.cycle_event_log import reset_cycle_event_log
        reset_cycle_event_log()

    def teardown_method(self):
        from src.services.cycle_event_log import reset_cycle_event_log
        reset_cycle_event_log()

    def _make_log(self):
        from src.services.cycle_event_log import CycleEventLog
        return CycleEventLog(max_events=100)

    def test_empty_on_creation(self):
        log = self._make_log()
        assert log.total_events == 0
        assert log.total_emitted == 0
        assert log.replay() == []

    def test_emit_returns_event(self):
        from src.services.cycle_event_log import CycleEventLog
        log = CycleEventLog()
        evt = log.emit("CYCLE_START", symbol="BTC", cycle_id="abc", equity=10000)
        assert evt.event_type == "CYCLE_START"
        assert evt.symbol == "BTC"
        assert evt.payload["equity"] == 10000

    def test_emit_increments_counters(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("SIGNAL_EMITTED", symbol="BTC", cycle_id="c1")
        assert log.total_events == 2
        assert log.total_emitted == 2

    def test_replay_chronological(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("SIGNAL_EMITTED", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1")
        events = log.replay()
        types = [e.event_type for e in events]
        assert types == ["CYCLE_START", "SIGNAL_EMITTED", "CYCLE_END"]

    def test_replay_returns_stable_snapshot(self):
        log = self._make_log()
        log.emit("A", symbol="BTC", cycle_id="c1")
        snap1 = log.replay()
        log.emit("B", symbol="BTC", cycle_id="c2")
        # snap1 is not affected by later emit
        assert len(snap1) == 1

    def test_filter_by_symbol(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_START", symbol="ETH", cycle_id="c2")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1")
        btc = log.filter_by_symbol("BTC")
        assert len(btc) == 2
        assert all(e.symbol == "BTC" for e in btc)

    def test_filter_by_type(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("SIGNAL_EMITTED", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_START", symbol="ETH", cycle_id="c2")
        starts = log.filter_by_type("CYCLE_START")
        assert len(starts) == 2

    def test_filter_by_cycle(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_START", symbol="ETH", cycle_id="c2")
        c1 = log.filter_by_cycle("c1")
        assert len(c1) == 2
        assert all(e.cycle_id == "c1" for e in c1)

    def test_last_n(self):
        log = self._make_log()
        for i in range(10):
            log.emit(f"EVT_{i}", symbol="BTC", cycle_id="c")
        last5 = log.last_n(5)
        assert len(last5) == 5
        assert last5[-1].event_type == "EVT_9"

    def test_last_n_larger_than_total(self):
        log = self._make_log()
        log.emit("A", symbol="BTC", cycle_id="c")
        last100 = log.last_n(100)
        assert len(last100) == 1

    def test_rolling_window_evicts_oldest(self):
        from src.services.cycle_event_log import CycleEventLog
        log = CycleEventLog(max_events=5)
        for i in range(8):
            log.emit(f"EVT_{i}", symbol="BTC", cycle_id="c")
        assert log.total_events == 5
        assert log.total_emitted == 8  # monotonic counter survives eviction
        events = log.replay()
        assert events[0].event_type == "EVT_3"  # oldest surviving

    def test_emit_fail_silent(self):
        """emit() should never raise — even with weird payload."""
        log = self._make_log()
        # Should not raise even with un-serializable payload
        evt = log.emit("X", symbol="BTC", cycle_id="c", data=object())
        assert evt is not None

    def test_summary_structure(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_START", symbol="ETH", cycle_id="c2")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1")
        s = log.summary()
        assert s["total_events_in_window"] == 3
        assert s["total_emitted_all_time"] == 3
        assert "CYCLE_START" in s["by_type"]
        assert s["by_type"]["CYCLE_START"] == 2
        assert "BTC" in s["top_symbols"]
        assert "recent_events" in s

    def test_to_jsonl(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1")
        jsonl = log.to_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert "event_type" in obj
            assert "symbol" in obj

    def test_cycle_summary_found(self):
        log = self._make_log()
        log.emit("CYCLE_START", symbol="BTC", cycle_id="c1", equity=10000)
        log.emit("SIGNAL_EMITTED", symbol="BTC", cycle_id="c1", action="LONG")
        log.emit("RISK_VERDICT", symbol="BTC", cycle_id="c1", verdict="APPROVED")
        log.emit("CYCLE_END", symbol="BTC", cycle_id="c1", status="ok")
        summary = log.cycle_summary("c1")
        assert summary["found"] is True
        assert summary["symbol"] == "BTC"
        assert summary["event_count"] == 4
        assert "CYCLE_START" in summary["stages_completed"]
        assert "CYCLE_END" in summary["stages_completed"]
        assert summary["duration_s"] >= 0.0

    def test_cycle_summary_not_found(self):
        log = self._make_log()
        summary = log.cycle_summary("nonexistent")
        assert summary["found"] is False
        assert summary["events"] == []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestCycleEventLogSingleton:
    def setup_method(self):
        from src.services.cycle_event_log import reset_cycle_event_log
        reset_cycle_event_log()

    def teardown_method(self):
        from src.services.cycle_event_log import reset_cycle_event_log
        reset_cycle_event_log()

    def test_singleton_same_instance(self):
        from src.services.cycle_event_log import get_cycle_event_log
        log1 = get_cycle_event_log()
        log2 = get_cycle_event_log()
        assert log1 is log2

    def test_reset_creates_fresh_instance(self):
        from src.services.cycle_event_log import get_cycle_event_log, reset_cycle_event_log
        log1 = get_cycle_event_log()
        log1.emit("X", symbol="BTC", cycle_id="c")
        reset_cycle_event_log()
        log2 = get_cycle_event_log()
        assert log2 is not log1
        assert log2.total_events == 0

    def test_emit_across_references(self):
        from src.services.cycle_event_log import get_cycle_event_log
        log_a = get_cycle_event_log()
        log_b = get_cycle_event_log()
        log_a.emit("CYCLE_START", symbol="BTC", cycle_id="c1")
        assert log_b.total_events == 1
