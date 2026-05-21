"""
tests/test_dashboard_auth.py
============================
Auth enforcement on the dashboard. Mutating endpoints (kill switch, trade
execute) must require credentials when a token is configured — important once
the system runs on mainnet with real money.
"""

from __future__ import annotations

import types

from src.dashboard import server as srv


def _req(headers=None, cookies=None):
    return types.SimpleNamespace(headers=headers or {}, cookies=cookies or {})


def test_auth_rejects_without_credentials(monkeypatch):
    monkeypatch.setattr(srv, "_DASHBOARD_TOKEN", "supersecret")
    assert srv._is_request_authenticated(_req()) is False


def test_auth_accepts_shared_token(monkeypatch):
    monkeypatch.setattr(srv, "_DASHBOARD_TOKEN", "supersecret")
    ok = srv._is_request_authenticated(_req(headers={"X-Mekka-Token": "supersecret"}))
    assert ok is True


def test_auth_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(srv, "_DASHBOARD_TOKEN", "supersecret")
    assert srv._is_request_authenticated(_req(headers={"X-Mekka-Token": "nope"})) is False


def test_hmac_equals():
    assert srv.hmac_equals("abc", "abc") is True
    assert srv.hmac_equals("abc", "abd") is False
