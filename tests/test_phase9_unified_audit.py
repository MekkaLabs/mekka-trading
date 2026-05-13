"""
tests/test_phase9_unified_audit.py
==================================
Phase 9 — UnifiedAuditReader tests (Story 032).

Coverage:
  • _parse_iso accepts ISO-with-tz, ISO-naive, Z-suffix; rejects junk
  • _ensure_aware promotes naive to UTC, leaves aware unchanged
  • _ndjson_to_audit parses Megazord shape; returns None on garbage
  • dedup_key buckets by (minute, agent, event)
  • _merge_and_dedup prefers SQLite over NDJSON on collision
  • _read_ndjson with empty dir returns []
  • _read_ndjson skips corrupt lines, keeps reading
  • read_recent: SQLite-only path
  • read_recent: NDJSON-only path
  • read_recent: both sources, chronological order, dedup applied
  • read_recent: `since` filter excludes older events
  • read_recent: SQLite read failure does not raise

Run: pytest tests/test_phase9_unified_audit.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.observability.unified_audit_reader import (
    AuditEvent,
    AuditSource,
    UnifiedAuditReader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year=2026, month=5, day=8, hour=12, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _ndjson_line(
    *,
    actor: str,
    kind: str,
    timestamp_iso: str,
    mission_id: str = "mission-test",
    data: dict | None = None,
    prev_hash: str = "GENESIS",
) -> str:
    obj = {
        "schemaVersion": "1.0.0",
        "stream": "audits",
        "missionId": mission_id,
        "prevHash": prev_hash,
        "record": {
            "kind": kind,
            "actor": actor,
            "data": data or {"symbol": "BTC-USD"},
            "missionId": mission_id,
            "timestamp": timestamp_iso,
        },
        "hash": f"hash-of-{kind}-{actor}",
    }
    return json.dumps(obj) + "\n"


# ===========================================================================
# Static helpers
# ===========================================================================


def test_parse_iso_accepts_z_suffix():
    dt = UnifiedAuditReader._parse_iso("2026-05-08T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2026 and dt.hour == 12


def test_parse_iso_accepts_offset():
    dt = UnifiedAuditReader._parse_iso("2026-05-08T12:00:00+00:00")
    assert dt is not None and dt.tzinfo is not None


def test_parse_iso_naive_becomes_utc():
    dt = UnifiedAuditReader._parse_iso("2026-05-08T12:00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_iso_returns_none_on_garbage():
    assert UnifiedAuditReader._parse_iso("not-a-date") is None
    assert UnifiedAuditReader._parse_iso(None) is None
    assert UnifiedAuditReader._parse_iso(12345) is None


def test_ensure_aware_promotes_naive():
    naive = datetime(2026, 5, 8, 12)
    aware = UnifiedAuditReader._ensure_aware(naive)
    assert aware.tzinfo is not None


# ===========================================================================
# NDJSON parsing
# ===========================================================================


def test_ndjson_to_audit_parses_megazord_shape():
    obj = json.loads(
        _ndjson_line(
            actor="risk-engine",
            kind="trade",
            timestamp_iso="2026-05-08T12:00:00Z",
            data={"symbol": "BTC-USD", "approved": True, "reason": "Validated"},
        ).strip()
    )
    event = UnifiedAuditReader._ndjson_to_audit(obj)
    assert event is not None
    assert event.source == AuditSource.NDJSON
    assert event.agent == "risk-engine"
    assert event.event == "TRADE"  # uppercased
    assert event.symbol == "BTC-USD"
    assert "Validated" in event.message


def test_ndjson_to_audit_rejects_garbage():
    assert UnifiedAuditReader._ndjson_to_audit("not a dict") is None
    assert UnifiedAuditReader._ndjson_to_audit({}) is None  # no record
    assert UnifiedAuditReader._ndjson_to_audit({"record": "wrong"}) is None
    assert (
        UnifiedAuditReader._ndjson_to_audit({"record": {"timestamp": "junk"}})
        is None
    )


# ===========================================================================
# Dedup
# ===========================================================================


def test_dedup_key_buckets_by_minute():
    e1 = AuditEvent(
        timestamp=_utc(minute=30, second=15),
        source=AuditSource.SQLITE,
        agent="Vision",
        event="DECISION",
    )
    e2 = AuditEvent(
        timestamp=_utc(minute=30, second=45),
        source=AuditSource.NDJSON,
        agent="Vision",
        event="DECISION",
    )
    assert e1.dedup_key() == e2.dedup_key()


def test_merge_prefers_sqlite_over_ndjson():
    ts = _utc()
    sqlite_ev = AuditEvent(
        timestamp=ts,
        source=AuditSource.SQLITE,
        agent="Vision",
        event="DECISION",
        severity="INFO",
        record_id="42",
    )
    ndjson_ev = AuditEvent(
        timestamp=ts,
        source=AuditSource.NDJSON,
        agent="Vision",
        event="DECISION",
        severity="INFO",
        record_id="hash-abc",
    )
    # NDJSON first, then SQLite — final pick must be SQLite
    out = UnifiedAuditReader._merge_and_dedup([ndjson_ev, sqlite_ev])
    assert len(out) == 1
    assert out[0].source == AuditSource.SQLITE


def test_merge_keeps_distinct_events():
    e1 = AuditEvent(
        timestamp=_utc(minute=10),
        source=AuditSource.SQLITE,
        agent="Batman",
        event="RISK_APPROVED",
    )
    e2 = AuditEvent(
        timestamp=_utc(minute=12),
        source=AuditSource.NDJSON,
        agent="Batman",
        event="RISK_APPROVED",
    )
    out = UnifiedAuditReader._merge_and_dedup([e1, e2])
    assert len(out) == 2  # different minutes → not deduped


# ===========================================================================
# NDJSON dir-level reads
# ===========================================================================


def test_read_ndjson_empty_dir_returns_empty(tmp_path: Path):
    reader = UnifiedAuditReader(ndjson_dir=tmp_path / "missing")
    out = reader._read_ndjson(limit=10, since=None)
    assert out == []


def test_read_ndjson_reads_one_file(tmp_path: Path):
    fpath = tmp_path / "mission-1.audits.ndjson"
    fpath.write_text(
        _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T12:00:00Z")
        + _ndjson_line(actor="execution-engine", kind="execution", timestamp_iso="2026-05-08T12:01:00Z"),
        encoding="utf-8",
    )
    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    out = reader._read_ndjson(limit=10, since=None)
    assert len(out) == 2
    assert {e.agent for e in out} == {"risk-engine", "execution-engine"}


def test_read_ndjson_skips_corrupt_line(tmp_path: Path):
    fpath = tmp_path / "mission-2.audits.ndjson"
    fpath.write_text(
        "{not valid json}\n"
        + _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T12:00:00Z"),
        encoding="utf-8",
    )
    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    out = reader._read_ndjson(limit=10, since=None)
    assert len(out) == 1
    assert out[0].agent == "risk-engine"


def test_read_ndjson_filters_by_since(tmp_path: Path):
    fpath = tmp_path / "mission-3.audits.ndjson"
    fpath.write_text(
        _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T10:00:00Z")
        + _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T14:00:00Z"),
        encoding="utf-8",
    )
    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    out = reader._read_ndjson(limit=10, since=_utc(hour=12))
    assert len(out) == 1
    assert out[0].timestamp.hour == 14


# ===========================================================================
# read_recent — full integration
# ===========================================================================


@pytest.mark.asyncio
async def test_read_recent_sqlite_only(monkeypatch, tmp_path):
    """Empty NDJSON dir + SQLite has rows → returns SQLite events."""
    rows = [
        MagicMock(
            id=1, timestamp=_utc(minute=10), agent="Vision",
            event="DECISION", symbol="BTC", severity="INFO", message="bull", payload={"k": "v"},
        ),
        MagicMock(
            id=2, timestamp=_utc(minute=11), agent="Batman",
            event="RISK_APPROVED", symbol="BTC", severity="INFO", message="ok", payload=None,
        ),
    ]

    repo_mock = MagicMock()
    repo_mock.list_recent_audit = AsyncMock(return_value=rows)
    monkeypatch.setattr("src.persistence.repository.MekkaRepository", repo_mock)

    reader = UnifiedAuditReader(ndjson_dir=tmp_path / "empty")
    events = await reader.read_recent(limit=50)
    assert len(events) == 2
    assert all(e.source == AuditSource.SQLITE for e in events)
    assert events[0].timestamp <= events[1].timestamp  # chronological


@pytest.mark.asyncio
async def test_read_recent_ndjson_only(monkeypatch, tmp_path):
    """SQLite returns empty + NDJSON has files."""
    repo_mock = MagicMock()
    repo_mock.list_recent_audit = AsyncMock(return_value=[])
    monkeypatch.setattr("src.persistence.repository.MekkaRepository", repo_mock)

    fpath = tmp_path / "mission-4.audits.ndjson"
    fpath.write_text(
        _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T09:00:00Z"),
        encoding="utf-8",
    )

    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    events = await reader.read_recent(limit=50)
    assert len(events) == 1
    assert events[0].source == AuditSource.NDJSON


@pytest.mark.asyncio
async def test_read_recent_merges_and_dedups(monkeypatch, tmp_path):
    """SQLite + NDJSON with one collision → 1 dedup, sqlite-version kept."""
    rows = [
        MagicMock(
            id=1, timestamp=_utc(hour=12, minute=0, second=20),
            agent="Vision", event="DECISION", symbol="BTC",
            severity="INFO", message="from sqlite", payload={"src": "sqlite"},
        ),
    ]
    repo_mock = MagicMock()
    repo_mock.list_recent_audit = AsyncMock(return_value=rows)
    monkeypatch.setattr("src.persistence.repository.MekkaRepository", repo_mock)

    fpath = tmp_path / "mission-5.audits.ndjson"
    fpath.write_text(
        # Same minute as SQLite event → must dedup
        _ndjson_line(
            actor="Vision", kind="DECISION",
            timestamp_iso="2026-05-08T12:00:55Z",
        )
        # Different minute → kept
        + _ndjson_line(
            actor="risk-engine", kind="trade",
            timestamp_iso="2026-05-08T12:30:00Z",
        ),
        encoding="utf-8",
    )

    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    events = await reader.read_recent(limit=50)
    # Expect 2 distinct minutes: 12:00 (SQLite, NDJSON deduped) + 12:30 (NDJSON only)
    assert len(events) == 2
    # The 12:00 entry must be the SQLite version (preferred over NDJSON)
    twelve_zero = [e for e in events if e.timestamp.minute == 0]
    assert len(twelve_zero) == 1
    assert twelve_zero[0].source == AuditSource.SQLITE


@pytest.mark.asyncio
async def test_read_recent_since_filter(monkeypatch, tmp_path):
    rows = [
        MagicMock(
            id=1, timestamp=_utc(hour=8), agent="A", event="X",
            symbol=None, severity="INFO", message="", payload=None,
        ),
        MagicMock(
            id=2, timestamp=_utc(hour=14), agent="B", event="Y",
            symbol=None, severity="INFO", message="", payload=None,
        ),
    ]
    repo_mock = MagicMock()
    repo_mock.list_recent_audit = AsyncMock(return_value=rows)
    monkeypatch.setattr("src.persistence.repository.MekkaRepository", repo_mock)

    reader = UnifiedAuditReader(ndjson_dir=tmp_path / "empty")
    events = await reader.read_recent(limit=50, since=_utc(hour=12))
    assert len(events) == 1
    assert events[0].record_id == "2"


@pytest.mark.asyncio
async def test_read_recent_handles_sqlite_failure(monkeypatch, tmp_path):
    """SQLite raises → reader still works using NDJSON only, no propagation."""
    repo_mock = MagicMock()
    repo_mock.list_recent_audit = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr("src.persistence.repository.MekkaRepository", repo_mock)

    fpath = tmp_path / "mission-6.audits.ndjson"
    fpath.write_text(
        _ndjson_line(actor="risk-engine", kind="trade", timestamp_iso="2026-05-08T11:00:00Z"),
        encoding="utf-8",
    )

    reader = UnifiedAuditReader(ndjson_dir=tmp_path)
    events = await reader.read_recent(limit=10)
    assert len(events) == 1
    assert events[0].source == AuditSource.NDJSON
