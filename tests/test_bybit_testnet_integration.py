"""
tests/test_bybit_testnet_integration.py
=======================================
End-to-end integration tests against the real Bybit testnet.

These tests are **skipped by default** because they require real (testnet)
API keys and make real (testnet) network calls. They run only when both
``BYBIT_API_KEY`` and ``BYBIT_API_SECRET`` are present in the environment
AND the ``MEKKA_RUN_BYBIT_INTEGRATION`` flag is set to a truthy value.

Why two gates?
  1. Bybit keys may be present in a dev shell for other reasons (running
     the dashboard manually, smoke-testing a script). We do not want
     pytest to suddenly start hitting the network just because someone
     opened a terminal in the project dir.
  2. CI environments that *do* want these tests must explicitly opt in
     via ``MEKKA_RUN_BYBIT_INTEGRATION=1``.

How to run locally
------------------
    export BYBIT_API_KEY=...
    export BYBIT_API_SECRET=...
    export MEKKA_RUN_BYBIT_INTEGRATION=1
    pytest tests/test_bybit_testnet_integration.py -v

What is exercised
-----------------
  * Sandbox routing — confirms the CCXT client lands on
    api-testnet.bybit.com after set_sandbox_mode(True).
  * load_markets — confirms the perp linear market catalog is reachable.
  * fetch_time + clock-skew — confirms IronMan's pre-flight check works
    against the real server clock (the simulated check we run elsewhere
    cannot catch a misconfigured CCXT version).
  * fetch_balance — confirms credentials are accepted for read access.
  * fetch_positions — confirms the dashboard's read-path against a real
    response shape (zero positions is OK; we only check the shape).

What is NOT exercised
---------------------
  * Order placement — even on testnet, automated tests should not place
    orders without explicit reason. We trust the unit-tested code paths
    in iron_man.py for that.
  * Long-running WebSocket connections — those have their own loop and
    do not fit a pytest run.
"""

from __future__ import annotations

import asyncio
import os

import pytest


# ---------------------------------------------------------------------------
# Skip-by-default machinery
# ---------------------------------------------------------------------------

def _should_run() -> bool:
    """Two-gate opt-in check."""
    has_keys = bool(os.environ.get("BYBIT_API_KEY")) and bool(
        os.environ.get("BYBIT_API_SECRET")
    )
    has_flag = os.environ.get("MEKKA_RUN_BYBIT_INTEGRATION", "").lower() in (
        "1",
        "true",
        "yes",
    )
    return has_keys and has_flag


pytestmark = pytest.mark.skipif(
    not _should_run(),
    reason=(
        "Bybit testnet integration tests require BYBIT_API_KEY + "
        "BYBIT_API_SECRET + MEKKA_RUN_BYBIT_INTEGRATION=1. Skipping."
    ),
)


# ---------------------------------------------------------------------------
# Shared fixture: a sandbox-routed CCXT client built the same way our
# production code does it. We do NOT reuse IronMan's instance because:
#   1. IronMan's _connect_lock would serialise our concurrent test access.
#   2. Building it the same way validates that the construction sequence
#      itself is correct (sandbox_mode before load_markets).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def event_loop():
    """Module-scoped loop so multiple async tests share one CCXT session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def bybit_client():
    """Yield a sandbox-routed Bybit CCXT async client, then close it."""
    import ccxt.async_support as ccxt

    cfg = {
        "apiKey": os.environ["BYBIT_API_KEY"],
        "secret": os.environ["BYBIT_API_SECRET"],
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    }
    exchange = ccxt.bybit(cfg)
    exchange.set_sandbox_mode(True)
    await exchange.load_markets()
    try:
        yield exchange
    finally:
        await exchange.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sandbox_url_routed(bybit_client):
    """After set_sandbox_mode(True), the API URL must point at testnet."""
    url = bybit_client.urls.get("api")
    # CCXT stores URLs as a dict-of-strings keyed by API type. Accept either
    # a top-level "test" key or the unified field.
    flat = str(url).lower()
    assert "testnet" in flat, (
        f"Expected testnet URL after set_sandbox_mode, got: {url!r}"
    )


@pytest.mark.asyncio
async def test_markets_loaded(bybit_client):
    """load_markets() should return the linear perp catalog."""
    # BTC/USDT:USDT is the canonical Mekka<->Bybit perp symbol used
    # throughout the codebase via MarketRegistry.to_ccxt(..., "bybit").
    assert "BTC/USDT:USDT" in bybit_client.markets, (
        "Expected BTC/USDT:USDT in Bybit markets — check that defaultType=swap"
    )


@pytest.mark.asyncio
async def test_clock_skew_within_tolerance(bybit_client):
    """fetch_time should be within 5s of the local clock.

    This is the real-server version of the simulated check in IronMan.
    If this fails, the developer's machine has bad NTP — fix NTP, not the
    test.
    """
    import time

    server_ms = int(await bybit_client.fetch_time())
    local_ms = int(time.time() * 1000)
    skew = abs(server_ms - local_ms)
    assert skew < 5000, (
        f"Local clock is {skew}ms off Bybit server. Bybit will reject "
        "orders with code 10002. Run `sudo sntp -sS time.apple.com` (mac) "
        "or `sudo timedatectl set-ntp true` (linux)."
    )


@pytest.mark.asyncio
async def test_balance_readable(bybit_client):
    """fetch_balance() must succeed — proves the credentials are accepted."""
    bal = await bybit_client.fetch_balance()
    # We do not assert USDT > 0 because the operator might not have
    # transferred from Funding to Unified yet. Only that the API call
    # succeeded and returned the expected shape.
    assert isinstance(bal, dict), f"Expected dict balance, got {type(bal)}"
    assert "USDT" in bal or "info" in bal, (
        "Bybit balance response should contain USDT or raw info field. "
        "Got keys: " + ",".join(bal.keys())
    )


@pytest.mark.asyncio
async def test_positions_shape(bybit_client):
    """fetch_positions returns a list of dicts in CCXT unified format.

    Zero positions is fine — we are validating that
    ``dashboard.positions_provider.map_ccxt_positions`` can consume the
    real response without raising.
    """
    raw = await bybit_client.fetch_positions()
    assert isinstance(raw, list), f"Expected list, got {type(raw)}"

    # Run the dashboard mapper on the real payload. If the function
    # raises for any row we want to know — that is exactly the kind of
    # surprise integration tests exist to catch.
    from src.dashboard.positions_provider import map_ccxt_positions
    items = map_ccxt_positions(raw)
    assert isinstance(items, list)
    for item in items:
        # Sanity-check the wire contract.
        for key in ("symbol", "side", "size", "entry_price", "mark_price"):
            assert key in item, f"Missing {key} in mapped position: {item}"
