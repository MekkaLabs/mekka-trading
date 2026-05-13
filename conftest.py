# conftest.py — root pytest configuration for Mekka Trading
"""
Provides test environment variables so that pydantic-settings can
instantiate Settings() without a real .env file during unit tests.
"""

import os

import pytest


def pytest_configure(config):
    """Inject minimal env vars required by Settings before any module loads."""
    config.addinivalue_line("markers", "asyncio: mark test as async")

    # Provide stub values for required fields — paper_trading=true means
    # these are never used for real orders, just needed for validation.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-00000000000000000000000000000000")
    os.environ.setdefault("HYPERLIQUID_PRIVATE_KEY", "0" * 64)
    os.environ.setdefault("HYPERLIQUID_WALLET_ADDRESS", "0x0000000000000000000000000000000000000000")
    os.environ.setdefault("HYPERLIQUID_NETWORK", "testnet")
    os.environ.setdefault("PAPER_TRADING", "true")
    os.environ.setdefault("CRYPTOPANIC_API_KEY", "")
    # Force Telegram disabled by default so the suite never leaks into a
    # real bot when developers leave placeholder `.env` values in place
    # (TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here is truthy and would
    # otherwise enable the alerter — see test_alert_disabled_returns_false).
    # Tests that need it on use monkeypatch to flip the flag for their scope.
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "")
    # Origin allowlist for the dashboard WS — kept empty in tests so the
    # extra-origins test exercises the in-memory monkeypatch path only.
    os.environ.setdefault("DASHBOARD_ALLOWED_ORIGINS", "")


@pytest.fixture(autouse=True)
def _clear_kill_switch():
    """
    Ensure the real data/.kill_switch file is absent before and after every
    test so kill-switch-agnostic tests are never accidentally affected by a
    file left behind by a previous run or a test that forgot to clean up.

    Tests that need the kill switch active must either:
      - monkeypatch `batman._KILL_SWITCH_FILE` to a tmp_path location, OR
      - set the env var MEKKA_KILL_SWITCH=1 via monkeypatch.
    """
    import pathlib

    ks = pathlib.Path("data/.kill_switch")
    ks.unlink(missing_ok=True)
    yield
    ks.unlink(missing_ok=True)
