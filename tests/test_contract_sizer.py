"""
tests/test_contract_sizer.py
==============================
Cobertura de compute_size, get_contract_size, pnl_quote_to_usd.
"""

from __future__ import annotations

import pytest

from src.services.contract_sizer import (
    DEFAULT_CONTRACT_SIZES_USD,
    SizeComputation,
    compute_size,
    get_contract_size,
    pnl_quote_to_usd,
)


class TestGetContractSize:
    def test_btc_default(self):
        assert get_contract_size("BTC") == 100.0

    def test_eth_default(self):
        assert get_contract_size("ETH") == 10.0

    def test_case_insensitive(self):
        assert get_contract_size("btc") == 100.0

    def test_unknown_coin_returns_default_10(self):
        assert get_contract_size("UNKNOWN_COIN") == 10.0

    def test_override(self):
        assert get_contract_size("BTC", override=50.0) == 50.0

    def test_override_zero_raises(self):
        with pytest.raises(ValueError):
            get_contract_size("BTC", override=0)


class TestComputeSizeLinear:
    def test_simple_linear(self):
        # $1000 a $50000 = 0.02 BTC
        s = compute_size(1000.0, 50000.0, "linear")
        assert s.market_type == "linear"
        assert s.quantity == pytest.approx(0.02)
        assert s.notional_usd == pytest.approx(1000.0)
        assert s.contract_size is None

    def test_rounded_down(self):
        # $100 a $50000 = 0.002 BTC, step=0.001 → 0.002 (sem rounding)
        # $101 a $50000 = 0.00202 → 0.002 (rounded)
        s = compute_size(101.0, 50000.0, "linear", step_size=0.001)
        assert s.quantity == pytest.approx(0.002)
        assert s.rounded is True

    def test_no_rounding_when_exact(self):
        s = compute_size(100.0, 50000.0, "linear", step_size=0.001)
        # 100/50000 = 0.002 exato
        assert s.rounded is False

    def test_negative_notional_raises(self):
        with pytest.raises(ValueError):
            compute_size(-100, 50000, "linear")

    def test_zero_price_raises(self):
        with pytest.raises(ValueError):
            compute_size(100, 0, "linear")


class TestComputeSizeInverse:
    def test_btc_inverse(self):
        # $1000 / $100 contract = 10 contracts
        s = compute_size(1000.0, 50000.0, "inverse", coin="BTC")
        assert s.market_type == "inverse"
        assert s.quantity == 10
        assert s.contract_size == 100.0
        assert s.notional_usd == 1000.0
        assert s.rounded is False

    def test_eth_inverse(self):
        # $200 / $10 contract = 20 contracts
        s = compute_size(200.0, 2500.0, "inverse", coin="ETH")
        assert s.quantity == 20
        assert s.contract_size == 10.0

    def test_fractional_rounds_down(self):
        # $250 / $100 = 2.5 contracts → 2 contracts (round down)
        s = compute_size(250.0, 50000.0, "inverse", coin="BTC")
        assert s.quantity == 2
        assert s.notional_usd == 200.0
        assert s.rounded is True

    def test_too_small_notional_zero_contracts(self):
        # $50 / $100 = 0.5 → 0 contracts (impossível executar)
        s = compute_size(50.0, 50000.0, "inverse", coin="BTC")
        assert s.quantity == 0
        assert s.notional_usd == 0.0

    def test_invalid_market_type_raises(self):
        with pytest.raises(ValueError):
            compute_size(1000, 50000, "spot")  # type: ignore


class TestPnlQuoteToUsd:
    def test_usdt_no_conversion(self):
        assert pnl_quote_to_usd(42.50, "USDT", 0) == 42.50

    def test_usd_no_conversion(self):
        assert pnl_quote_to_usd(-10.0, "USD", 0) == -10.0

    def test_btc_to_usd(self):
        # 0.001 BTC × $50000 = $50
        assert pnl_quote_to_usd(0.001, "BTC", 50000.0) == pytest.approx(50.0)

    def test_btc_negative_pnl(self):
        assert pnl_quote_to_usd(-0.0002, "BTC", 50000.0) == pytest.approx(-10.0)

    def test_zero_mark_price_returns_zero(self):
        # Defensive: sem mark price, não pode converter
        assert pnl_quote_to_usd(0.001, "BTC", 0.0) == 0.0


class TestSizeComputationDataclass:
    def test_linear_no_contract_size(self):
        s = SizeComputation(
            quantity=0.02, notional_usd=1000.0, market_type="linear",
            contract_size=None, rounded=False,
        )
        assert s.contract_size is None

    def test_inverse_has_contract_size(self):
        s = SizeComputation(
            quantity=10, notional_usd=1000.0, market_type="inverse",
            contract_size=100.0, rounded=False,
        )
        assert s.contract_size == 100.0
