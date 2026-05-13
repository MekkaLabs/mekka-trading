"""
src/observability/__init__.py
=============================
Mekka Trading — Python-side observability helpers (Story 032).

This package is **separate** from the TypeScript `observability/`
folder at the repo root, which owns the Megazord runtime's NDJSON
event-pipeline and ops alerting (Stories 002–024).

The Python-side helpers here are read-mostly utilities that bridge
both worlds — most notably `UnifiedAuditReader`, which presents a
single chronological timeline of audit events from SQLite (Python
pipeline) + NDJSON (TS runtime).

See `docs/adr/ADR-001-audit-single-source.md` for the architectural
decision.
"""

from __future__ import annotations

__all__ = ["UnifiedAuditReader", "AuditEvent", "AuditSource"]


def __getattr__(name: str):  # noqa: N807
    if name in ("UnifiedAuditReader", "AuditEvent", "AuditSource"):
        from src.observability.unified_audit_reader import (
            AuditEvent,
            AuditSource,
            UnifiedAuditReader,
        )
        return locals()[name]
    raise AttributeError(f"module 'src.observability' has no attribute {name!r}")
