"""
src/utils/time.py
=================
Canonical UTC clock for the Mekka Trading codebase.

Every timestamp in the system is UTC-aware. Use `utc_now()` instead of
`datetime.now(timezone.utc)` to keep call sites uniform and to avoid
the trap of `datetime.utcnow()` (deprecated in Python 3.12+, returns
naive datetime).
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Timezone-aware UTC `datetime.now()` — the only canonical clock."""
    return datetime.now(timezone.utc)


def utc_today_iso() -> str:
    """Today's UTC date as `YYYY-MM-DD` (used for daily_pnl row keys)."""
    return utc_now().strftime("%Y-%m-%d")
