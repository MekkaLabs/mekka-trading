"""
src/persistence/__init__.py
===========================
Mekka Trading — SQLite persistence layer.

Exposes lazy accessors so importing the package never triggers an actual
SQLAlchemy connection during unit tests that don't touch persistence.
"""

from __future__ import annotations

__all__ = [
    "Base",
    "SignalRecord",
    "TradeRecord",
    "DailyPnLRecord",
    "AuditRecord",
    "init_engine",
    "get_session",
    "MekkaRepository",
]


def __getattr__(name: str):  # noqa: N807
    if name in ("Base", "SignalRecord", "TradeRecord", "DailyPnLRecord", "AuditRecord"):
        from src.persistence.models import (
            AuditRecord,
            Base,
            DailyPnLRecord,
            SignalRecord,
            TradeRecord,
        )
        return locals()[name]
    if name in ("init_engine", "get_session"):
        from src.persistence.db import get_session, init_engine
        return locals()[name]
    if name == "MekkaRepository":
        from src.persistence.repository import MekkaRepository
        return MekkaRepository
    raise AttributeError(f"module 'src.persistence' has no attribute {name!r}")
