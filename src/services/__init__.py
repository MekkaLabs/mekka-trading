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

__all__ = ["DailyPnLWriter", "ConsecutiveBreaker", "TelegramAlerter"]


def __getattr__(name: str):  # noqa: N807
    if name == "DailyPnLWriter":
        from src.services.daily_pnl_writer import DailyPnLWriter
        return DailyPnLWriter
    if name == "ConsecutiveBreaker":
        from src.services.breakers import ConsecutiveBreaker
        return ConsecutiveBreaker
    if name == "TelegramAlerter":
        from src.services.telegram_alerter import TelegramAlerter
        return TelegramAlerter
    raise AttributeError(f"module 'src.services' has no attribute {name!r}")
