"""
src/dashboard/validators.py
===========================
Filename + origin validators for the Mekka dashboard.

These helpers are pure functions with zero state, extracted from
``server.py`` so they can be exercised in tight unit tests and reused by
future modules without dragging the whole aiohttp app along.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit


# `latest.json` is the rolling pointer; `snapshot-YYYYMMDDTHHMM.json` is the
# minute-grain replay file. Anything else gets a 400 long before the OS
# layer ever sees the path.
SNAPSHOT_NAME_RE = re.compile(r"^(snapshot-\d{8}T\d{4}|latest)\.json$")
# Filename emitted by `_persist_snapshot` is
# `incident-bundle-YYYYMMDDTHHMMSS.json` — date (8) + T + time (6).
# The optional `-NNNNNN` suffix is the microsecond disambiguator added when
# two bundle-worthy transitions land inside the same wall-clock second
# (kill → clear → kill in tests, or rapid breaker churn in prod). Both forms
# are accepted so legacy bundle URLs and existing fixtures keep resolving.
BUNDLE_NAME_RE = re.compile(r"^incident-bundle-\d{8}T\d{6}(?:-\d{6})?\.json$")

# Default WS Origin allowlist. Covers the common local-dev cases; production
# deployments extend via DASHBOARD_ALLOWED_ORIGINS (CSV).
DEFAULT_WS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1",
    "http://localhost",
    "https://127.0.0.1",
    "https://localhost",
)
EXTRA_WS_ORIGINS: tuple[str, ...] = tuple(
    o.strip().rstrip("/")
    for o in os.environ.get("DASHBOARD_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
)


def is_valid_snapshot_name(name: str) -> bool:
    """Defence-in-depth filename validator (called before any disk read)."""
    return bool(name) and bool(SNAPSHOT_NAME_RE.match(name))


def is_valid_bundle_name(name: str) -> bool:
    return bool(name) and bool(BUNDLE_NAME_RE.match(name))


def is_origin_allowed(origin: str | None) -> bool:
    """Match against the WS origin allowlist. Empty/missing origin is rejected.

    We compare scheme+host (port-agnostic) so listening on a non-standard
    port still works without users needing to enumerate every variant.
    """
    if not origin:
        return False
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if not parts.hostname:
        return False
    base = f"{parts.scheme}://{parts.hostname}"
    return base in DEFAULT_WS_ORIGINS or base in EXTRA_WS_ORIGINS
