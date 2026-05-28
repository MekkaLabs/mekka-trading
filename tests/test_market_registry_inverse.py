"""
tests/test_market_registry_inverse.py
=======================================
Cobertura da extensão de market_registry.to_ccxt para suportar market_type
(linear vs inverse). Backward-compat: callers sem o 3º arg continuam
funcionando.
"""

from __future__ import annotations

import pytest

from src.services.market_registry import to_ccxt, to_mekka, to_native


class TestBackwardCompat:
    """Sem o 3º arg, comportamento deve ser idêntico ao pré-2026-05-28."""

    def test_binance_default_linear(self):
        assert to_ccxt("BTC", "binance") == "BTC/USDT:USDT"

    def test_bybit_default_linear(self):
        assert to_ccxt("BTC", "bybit") == "BTC/USDT:USDT"

    def test_hyperliquid_unchanged(self):
        assert to_ccxt("BTC", "hyperliquid") == "BTC/USDC:USDC"

    def test_explicit_linear_same_as_default(self):
        assert to_ccxt("BTC", "binance", "linear") == to_ccxt("BTC", "binance")


class TestInverseSupport:
    def test_binance_inverse_btc(self):
        assert to_ccxt("BTC", "binance", "inverse") == "BTC/USD:BTC"

    def test_binance_inverse_eth(self):
        assert to_ccxt("ETH", "binance", "inverse") == "ETH/USD:ETH"

    def test_binance_inverse_lowercase_input(self):
        assert to_ccxt("btc", "binance", "inverse") == "BTC/USD:BTC"

    def test_binance_inverse_from_ccxt_format(self):
        # to_ccxt deve normalizar input — passa um symbol já formatado
        assert to_ccxt("BTC/USDT:USDT", "binance", "inverse") == "BTC/USD:BTC"


class TestInverseIgnoredOnNonBinance:
    """market_type=inverse só afeta binance hoje. Outros exchanges continuam linear."""

    def test_bybit_inverse_falls_back_to_linear(self):
        # Bybit COIN-M existe mas Mekka não suporta hoje — graceful fallback
        assert to_ccxt("BTC", "bybit", "inverse") == "BTC/USDT:USDT"

    def test_hyperliquid_inverse_unchanged(self):
        assert to_ccxt("BTC", "hyperliquid", "inverse") == "BTC/USDC:USDC"


class TestIdempotency:
    def test_inverse_roundtrip_preserves(self):
        s1 = to_ccxt("BTC", "binance", "inverse")
        s2 = to_ccxt(s1, "binance", "inverse")
        assert s1 == s2

    def test_to_mekka_strips_inverse_format(self):
        assert to_mekka("BTC/USD:BTC") == "BTC"


class TestEmptyInput:
    def test_empty_returns_empty(self):
        assert to_ccxt("", "binance", "inverse") == ""

    def test_whitespace_returns_empty(self):
        assert to_ccxt("   ", "binance", "inverse") == ""
