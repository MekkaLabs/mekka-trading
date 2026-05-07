"""
src/services/__init__.py
========================
Mekka Trading — Service layer.

Services are stateful utilities that don't fit the "agent" persona model
(no Marvel/DC codename, no decision-making, no analysis). They live
alongside agents but are invoked by them. The first inhabitant is the
DailyPnLWriter introduced in Story 027.
"""

from __future__ import annotations

__all__ = ["DailyPnLWriter"]


def __getattr__(name: str):  # noqa: N807
    if name == "DailyPnLWriter":
        from src.services.daily_pnl_writer import DailyPnLWriter
        return DailyPnLWriter
    raise AttributeError(f"module 'src.services' has no attribute {name!r}")
