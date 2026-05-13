"""
src/dashboard/auth.py
=====================
Lightweight session-token primitives for the Mekka dashboard.

Goal: keep ``unsafe-eval``-free, no external deps (just stdlib), but
upgrade us from a single shared-secret bearer token to a real session
flow with login/logout, expiry, and signed cookies.

Token shape:
    base64url(payload_json) "." base64url(hmac_sha256)

Where payload_json is::
    {"sub": "operator", "iat": <epoch>, "exp": <epoch>}

A token is *valid* when:
    1. signature verifies under the server-side secret
    2. exp > now
    3. (optional) sub matches a configured allowlist

The secret comes from ``MEKKA_DASHBOARD_SECRET``. If unset, we generate
a random one at import time — meaning sessions don't survive process
restart. That is the safer default for a dev environment; production
ops should set the env var to a long random string and persist it.

This module is *exclusively* for the dashboard UI. The trading runtime
must never reuse these tokens for anything load-bearing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any


logger = logging.getLogger("mekka.dashboard.auth")

# Session lifetime in seconds. Default 12h is the right sweet spot for an
# operator console — long enough to span a trading session, short enough
# that an unattended laptop doesn't stay valid indefinitely.
DEFAULT_TTL_SECONDS = int(os.environ.get("MEKKA_DASHBOARD_SESSION_TTL", "43200"))

# Operator password for `/api/auth/login`. Empty disables the login flow
# entirely (back-compat: callers fall back to MEKKA_DASHBOARD_TOKEN).
PASSWORD = os.environ.get("MEKKA_DASHBOARD_PASSWORD", "").strip()

# Server-side HMAC key. Hard-coded random fallback so we never sign with
# an empty key.  Operators who want sessions to survive restart MUST set
# MEKKA_DASHBOARD_SECRET in env.
_SECRET_RAW = os.environ.get("MEKKA_DASHBOARD_SECRET", "").strip()
if _SECRET_RAW:
    _SECRET = _SECRET_RAW.encode("utf-8")
else:
    _SECRET = secrets.token_bytes(32)
    logger.warning(
        "MEKKA_DASHBOARD_SECRET not set — sessions reset on every restart"
    )

# Cookie name used by `/api/auth/login` and consumed by the middleware.
COOKIE_NAME = "mekka_session"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(token: str) -> bytes:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad)


def issue_token(subject: str = "operator", ttl_seconds: int | None = None) -> dict[str, Any]:
    """Issue a fresh signed session token.

    Returns ``{"token": str, "expires_at": int, "subject": str}``. The
    caller is responsible for setting it as a cookie and/or returning it
    in the JSON body so the client can keep it for header-style auth.
    """
    ttl = int(ttl_seconds or DEFAULT_TTL_SECONDS)
    now = int(time.time())
    payload = {"sub": subject, "iat": now, "exp": now + ttl}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_SECRET, body, hashlib.sha256).digest()
    token = f"{_b64url_encode(body)}.{_b64url_encode(sig)}"
    return {"token": token, "expires_at": payload["exp"], "subject": subject}


def verify_token(token: str | None) -> dict[str, Any] | None:
    """Return the decoded payload if ``token`` is valid, else ``None``.

    Validation:
    - HMAC matches under the server secret
    - Token has both halves and they decode cleanly
    - exp > now
    """
    if not token or "." not in token:
        return None
    body_b64, sig_b64 = token.rsplit(".", 1)
    try:
        body = _b64url_decode(body_b64)
        sig = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        return None
    expected = hmac.new(_SECRET, body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp <= time.time():
        return None
    return payload


def check_password(presented: str | None) -> bool:
    """Constant-time compare against the configured operator password.

    Returns ``False`` when ``MEKKA_DASHBOARD_PASSWORD`` is empty so the
    login flow is firmly opt-in.
    """
    if not PASSWORD:
        return False
    if not presented:
        return False
    return hmac.compare_digest(PASSWORD, str(presented))


def is_login_enabled() -> bool:
    """True when the operator opted into the password+session flow."""
    return bool(PASSWORD)
