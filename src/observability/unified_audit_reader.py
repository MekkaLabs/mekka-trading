"""
src/observability/unified_audit_reader.py
=========================================
Unified audit reader — Story 032.

Returns a single chronological timeline of audit events drawn from:
  • SQLite `audit_log` table (Python pipeline, Stories 025–031)
  • NDJSON files under `memory/audit-log/` (TS Megazord runtime,
    Stories 002–024)

Goals
-----
- One endpoint for forensics and replay.
- Schema unification via `AuditEvent` Pydantic envelope.
- Defensive deduplication (close-in-time entries that look identical
  by `(timestamp_minute, agent, event)` are collapsed).
- Pure-read: never modifies either store.

Non-goals (deferred)
--------------------
- Writes to either store (handled by existing layers).
- Hash-chain verification of NDJSON (TS already does it).
- Pagination over millions of rows (linear scan acceptable for v1).

See `docs/adr/ADR-001-audit-single-source.md`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

from src.utils.time import utc_now


_NDJSON_DIR_DEFAULT = Path("memory/audit-log")


class AuditSource(str, Enum):
    """Where the unified record came from."""

    SQLITE = "SQLITE"
    NDJSON = "NDJSON"


class AuditEvent(BaseModel):
    """
    Common envelope across SQLite + NDJSON. Lossy — original payload
    preserved in `payload.raw` for forensic forensic depth.
    """

    schema_version: int = Field(default=1)
    timestamp: datetime
    source: AuditSource
    agent: str = Field(..., description="Producer codename or service label")
    event: str = Field(..., description="Event code (e.g. RISK_APPROVED, EXEC_PAPER)")
    severity: str = Field(default="INFO")
    symbol: Optional[str] = Field(default=None)
    message: str = Field(default="")
    payload: dict = Field(default_factory=dict)
    record_id: Optional[str] = Field(default=None, description="DB id or ndjson hash")

    def dedup_key(self) -> tuple[str, str, str]:
        """`(timestamp_minute, agent, event)` — used for cross-source dedup."""
        ts_minute = self.timestamp.replace(second=0, microsecond=0).isoformat()
        return (ts_minute, self.agent.lower(), self.event.upper())


class UnifiedAuditReader:
    """
    Read-only, async-friendly, no-state observer over both audit
    stores.

    Usage
    -----
        reader = UnifiedAuditReader()
        events = await reader.read_recent(limit=100)
        for e in events:
            print(e.timestamp, e.source.value, e.agent, e.event)
    """

    def __init__(
        self,
        ndjson_dir: Optional[Path] = None,
    ) -> None:
        self._ndjson_dir = ndjson_dir or _NDJSON_DIR_DEFAULT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def read_recent(
        self,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> list[AuditEvent]:
        """
        Return up to `limit` most recent events from both sources,
        chronologically ascending. Optional `since` filter (UTC-aware).
        """
        sqlite_events = await self._read_sqlite(limit=limit, since=since)
        ndjson_events = self._read_ndjson(limit=limit, since=since)

        merged = self._merge_and_dedup(sqlite_events + ndjson_events)
        merged.sort(key=lambda e: e.timestamp)

        # Apply `since` again post-merge (safety net) and cap to `limit`
        if since is not None:
            since_aware = self._ensure_aware(since)
            merged = [e for e in merged if e.timestamp >= since_aware]
        return merged[-limit:] if limit else merged

    # ------------------------------------------------------------------
    # SQLite path
    # ------------------------------------------------------------------

    async def _read_sqlite(
        self,
        limit: int,
        since: Optional[datetime],
    ) -> list[AuditEvent]:
        """Read SQLite via the existing Repository. Defensive: never raises."""
        try:
            from src.persistence.repository import MekkaRepository
            rows = await MekkaRepository.list_recent_audit(limit=limit)
        except Exception:  # noqa: BLE001
            return []

        events: list[AuditEvent] = []
        for r in rows:
            try:
                ts = self._ensure_aware(r.timestamp)
                if since is not None and ts < self._ensure_aware(since):
                    continue
                events.append(
                    AuditEvent(
                        timestamp=ts,
                        source=AuditSource.SQLITE,
                        agent=str(r.agent or "?"),
                        event=str(r.event or "?"),
                        severity=str(r.severity or "INFO"),
                        symbol=r.symbol,
                        message=str(r.message or ""),
                        payload=dict(r.payload or {}),
                        record_id=str(r.id),
                    )
                )
            except Exception:  # noqa: BLE001
                continue  # skip malformed rows, never crash the reader
        return events

    # ------------------------------------------------------------------
    # NDJSON path
    # ------------------------------------------------------------------

    def _read_ndjson(
        self,
        limit: int,
        since: Optional[datetime],
    ) -> list[AuditEvent]:
        """
        Scan `memory/audit-log/*.ndjson` files. NDJSON shape (Megazord):
            {
              "schemaVersion": "1.0.0",
              "stream": "audits" | "events",
              "missionId": "...",
              "record": { "kind": "...", "actor": "...", "data": {...},
                          "missionId": "...", "timestamp": "ISO" },
              "hash": "..."
            }
        """
        if not self._ndjson_dir.exists():
            return []

        events: list[AuditEvent] = []
        for path in sorted(self._ndjson_dir.glob("*.ndjson")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            event = self._ndjson_to_audit(obj)
                            if event is None:
                                continue
                            if since is not None and event.timestamp < self._ensure_aware(since):
                                continue
                            events.append(event)
                        except (json.JSONDecodeError, ValueError):
                            continue  # skip corrupt line, keep reading
            except OSError:
                continue  # file disappeared / permission — skip silently

        # Cap each source at `limit` to keep dedup cheap; final sort
        # in `read_recent` chooses the global recent N.
        return events[-(limit * 2):] if limit else events

    @staticmethod
    def _ndjson_to_audit(obj: Any) -> Optional[AuditEvent]:
        if not isinstance(obj, dict):
            return None
        record = obj.get("record")
        if not isinstance(record, dict):
            return None
        ts_raw = record.get("timestamp")
        ts = UnifiedAuditReader._parse_iso(ts_raw)
        if ts is None:
            return None
        return AuditEvent(
            timestamp=ts,
            source=AuditSource.NDJSON,
            agent=str(record.get("actor", "?")),
            event=str(record.get("kind", "?")).upper(),
            severity="INFO",
            symbol=(record.get("data", {}) or {}).get("symbol"),
            message=str((record.get("data", {}) or {}).get("reason", "")),
            payload={"raw": record, "missionId": obj.get("missionId")},
            record_id=str(obj.get("hash") or ""),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_iso(raw: Any) -> Optional[datetime]:
        if not raw or not isinstance(raw, str):
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _merge_and_dedup(events: Iterable[AuditEvent]) -> list[AuditEvent]:
        """
        Drop entries whose `dedup_key` already appears, preferring the
        SQLite-sourced version (richer fields) over NDJSON when there's
        a collision.
        """
        seen: dict[tuple[str, str, str], AuditEvent] = {}
        for ev in events:
            key = ev.dedup_key()
            existing = seen.get(key)
            if existing is None:
                seen[key] = ev
                continue
            # Prefer SQLite over NDJSON
            if existing.source == AuditSource.NDJSON and ev.source == AuditSource.SQLITE:
                seen[key] = ev
        return list(seen.values())
