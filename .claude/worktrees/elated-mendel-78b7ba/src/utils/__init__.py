"""
src/utils/__init__.py
=====================
Mekka Trading — small cross-cutting utilities.

Today only contains the canonical UTC clock. Add new modules here only
when the helper is used by ≥3 call sites and has no clear "owner"
package.
"""

from __future__ import annotations

__all__ = ["utc_now"]


def __getattr__(name: str):  # noqa: N807
    if name == "utc_now":
        from src.utils.time import utc_now
        return utc_now
    raise AttributeError(f"module 'src.utils' has no attribute {name!r}")
