"""
tests/test_market_registry.py
=============================
Unit tests for src/services/market_registry.py.

Pure functions, no network, no fixtures needed. Each conversion direction
has its own test class. We cover the full matrix of weird inputs we have
seen in real .env files and audit logs (legacy ``BTC-USD``, lowercase
``btc``, already-formatted ``BTC/USDT:USDT``, etc.) so the registry is
truly the single source of truth and any call site that delegates to it
inherits the same robustness.
"""

from __future__ import annotations

import pytest

from src.services.market_registry import (
    to_bybit_wire,
    to_ccxt,
    to_hyperliquid,
    to_mekka,
    to_native,
)


# ---------------------------------------------------------------------------
# to_mekka — collapse anything to the bare canonical form
# ---------------------------------------------------------------------------

class TestToMekka:
    def test_bare_uppercase_passthrough(self):
        assert to_mekka("BTC") == "BTC"

    def test_lowercase_becomes_upper(self):
        assert to_mekka("btc") == "BTC"

    def test_mixed_case(self):
        assert to_mekka("Btc") == "BTC"

    def test_whitespace_trimmed(self):
        assert to_mekka("  BTC  ") == "BTC"

    def test_empty_string(self):
        assert to_mekka("") == ""

    def test_whitespace_only(self):
        assert to_mekka("   ") == ""

    def test_ccxt_perp_usdt(self):
        assert to_mekka("BTC/USDT:USDT") == "BTC"

    def test_ccxt_perp_usdc(self):
        # Hyperliquid via CCXT uses USDC margin.
        assert to_mekka("BTC/USDC:USDC") == "BTC"

    def test_ccxt_spot(self):
        # Defensive — we never trade spot but the format should still resolve.
        assert to_mekka("BTC/USDT") == "BTC"

    def test_bybit_wire_usdt(self):
        assert to_mekka("BTCUSDT") == "BTC"

    def test_bybit_wire_usdc(self):
        assert to_mekka("BTCUSDC") == "BTC"

    def test_legacy_dash_usd(self):
        # Hyperliquid mock-era and some .env typos.
        assert to_mekka("BTC-USD") == "BTC"

    def test_legacy_dash_perp(self):
        # FTX-era convention; some old configs still ship this.
        assert to_mekka("BTC-PERP") == "BTC"

    def test_lowercase_ccxt_perp(self):
        assert to_mekka("btc/usdt:usdt") == "BTC"

    def test_three_letter_quote_usd_only(self):
        # Just "USD" (no T or C) — some HL-mock rows use this.
        assert to_mekka("BTCUSD") == "BTC"

    def test_busd_suffix(self):
        # Binance legacy stablecoin.
        assert to_mekka("BTCBUSD") == "BTC"

    def test_unknown_quote_assume_bare(self):
        # Three-letter symbol that doesn't end in a known stable → bare.
        # We do NOT try to "split" because that would mangle real symbols.
        assert to_mekka("ABC") == "ABC"

    def test_idempotent(self):
        # to_mekka(to_mekka(x)) == to_mekka(x) for every valid input.
        for raw in ["BTC", "btc", "BTC/USDT:USDT", "BTCUSDT", "BTC-USD"]:
            once = to_mekka(raw)
            twice = to_mekka(once)
            assert once == twice, f"Not idempotent for {raw!r}: {once} != {twice}"


# ---------------------------------------------------------------------------
# to_ccxt — bare → CCXT unified perp
# ---------------------------------------------------------------------------

class TestToCcxt:
    def test_bybit_uses_usdt(self):
        assert to_ccxt("BTC", "bybit") == "BTC/USDT:USDT"

    def test_binance_uses_usdt(self):
        assert to_ccxt("ETH", "binance") == "ETH/USDT:USDT"

    def test_hyperliquid_uses_usdc(self):
        # Hyperliquid via CCXT is USDC-margined, not USDT.
        assert to_ccxt("BTC", "hyperliquid") == "BTC/USDC:USDC"

    def test_idempotent_when_already_ccxt(self):
        # Passing in an already-formatted symbol should not double-format.
        assert to_ccxt("BTC/USDT:USDT", "bybit") == "BTC/USDT:USDT"

    def test_lowercase_input_normalised(self):
        assert to_ccxt("btc", "bybit") == "BTC/USDT:USDT"

    def test_empty_input_returns_empty(self):
        assert to_ccxt("", "bybit") == ""

    def test_legacy_dash_input(self):
        assert to_ccxt("BTC-USD", "bybit") == "BTC/USDT:USDT"


# ---------------------------------------------------------------------------
# to_bybit_wire — bare → Bybit V5 raw
# ---------------------------------------------------------------------------

class TestToBybitWire:
    def test_basic(self):
        assert to_bybit_wire("BTC") == "BTCUSDT"

    def test_idempotent_with_already_wire(self):
        assert to_bybit_wire("BTCUSDT") == "BTCUSDT"

    def test_from_ccxt_format(self):
        assert to_bybit_wire("BTC/USDT:USDT") == "BTCUSDT"

    def test_empty(self):
        assert to_bybit_wire("") == ""

    def test_lowercase(self):
        assert to_bybit_wire("btc") == "BTCUSDT"


# ---------------------------------------------------------------------------
# to_hyperliquid — bare → HL native (still bare)
# ---------------------------------------------------------------------------

class TestToHyperliquid:
    def test_basic(self):
        assert to_hyperliquid("BTC") == "BTC"

    def test_from_ccxt(self):
        assert to_hyperliquid("BTC/USDC:USDC") == "BTC"

    def test_from_wire(self):
        assert to_hyperliquid("BTCUSDT") == "BTC"

    def test_empty(self):
        assert to_hyperliquid("") == ""


# ---------------------------------------------------------------------------
# to_native — dispatcher that picks the right format per exchange
# ---------------------------------------------------------------------------

class TestToNative:
    @pytest.mark.parametrize("exchange,expected", [
        ("hyperliquid", "BTC"),
        ("bybit", "BTCUSDT"),
        ("binance", "BTC/USDT:USDT"),
    ])
    def test_dispatches_correctly(self, exchange, expected):
        assert to_native("BTC", exchange) == expected

    def test_robust_to_input_format(self):
        # Every input should reach the same native representation.
        for raw in ["BTC", "btc", "BTC-USD", "BTC/USDT:USDT", "BTCUSDT"]:
            assert to_native(raw, "bybit") == "BTCUSDT", f"Failed for {raw!r}"
