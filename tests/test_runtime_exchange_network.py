"""
tests/test_runtime_exchange_network.py
======================================
Toggle de rede (testnet ↔ mainnet) em runtime. SENSÍVEL: só muda dados/
roteamento; o double-gate continua sendo o gate real de dinheiro.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.config.runtime_exchange as rx
from src.config.settings import settings


@pytest.fixture(autouse=True)
def _isolate_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(rx, "_FILE", tmp_path / "rx.json")
    # restaura redes ao final para não vazar entre testes (singleton de settings)
    orig_binance = settings.binance_testnet
    orig_hl = settings.hyperliquid_network
    yield
    settings.binance_testnet = orig_binance
    settings.hyperliquid_network = orig_hl
    settings.__dict__.pop("is_mainnet", None)


def test_set_network_binance_to_mainnet():
    rx.set_network("binance", "mainnet")
    assert settings.binance_testnet is False
    assert settings.exchange_is_testnet("binance") is False
    assert rx.network_for("binance") == "mainnet"


def test_set_network_back_to_testnet():
    rx.set_network("binance", "mainnet")
    rx.set_network("binance", "testnet")
    assert settings.binance_testnet is True
    assert rx.network_for("binance") == "testnet"


def test_hyperliquid_invalidates_is_mainnet_cache():
    settings.hyperliquid_network = "testnet"
    settings.__dict__.pop("is_mainnet", None)
    _ = settings.is_mainnet  # cacheia False
    rx.set_network("hyperliquid", "mainnet")
    assert settings.is_mainnet is True          # cache foi invalidado
    assert rx.network_for("hyperliquid") == "mainnet"


def test_invalid_network_rejected():
    with pytest.raises(ValueError):
        rx.set_network("binance", "prod")


def test_invalid_exchange_rejected():
    with pytest.raises(ValueError):
        rx.set_network("ftx", "mainnet")


def test_persists_networks_and_preserves_active():
    rx.set_network("binance", "mainnet")
    import json
    st = json.loads(rx._FILE.read_text())
    assert st["networks"]["binance"] == "mainnet"


def test_double_gate_untouched_by_network_switch():
    """Trocar a rede NÃO mexe no double-gate (paper_trading/live_confirmed)."""
    before = (settings.paper_trading, settings.live_trading_confirmed)
    rx.set_network("binance", "mainnet")
    after = (settings.paper_trading, settings.live_trading_confirmed)
    assert before == after
