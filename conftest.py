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

