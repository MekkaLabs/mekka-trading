"""Regressão M1 (2026-06-01 audit) — kill-switch de perda absoluta exigido em mainnet.

max_daily_loss_usd default 0.0 DESLIGA o kill-switch de perda absoluta diária.
O gate de runtime (nick_fury) está correto, mas só dispara se cap > 0. O preflight
agora FALHA em mainnet+live quando o cap está em 0, forçando o operador a definir
um teto antes de operar com dinheiro real.
"""
from __future__ import annotations

import types
from unittest.mock import patch

import scripts.preflight_mainnet as pf


def _settings(*, cap: float, paper: bool, testnet: bool):
    return types.SimpleNamespace(
        max_daily_loss_usd=cap,
        paper_trading=paper,
        active_exchange="binance",
        exchange_is_testnet=lambda _ex=None: testnet,
    )


def _run_check(s):
    report = pf.PreflightReport()
    with patch.object(pf, "_get_settings", return_value=s):
        pf.check_daily_loss_cap(report)
    return report.checks[0]


def test_mainnet_live_zero_cap_fails():
    c = _run_check(_settings(cap=0.0, paper=False, testnet=False))
    assert c.level == "FAIL"
    assert "MAX_DAILY_LOSS_USD" in c.detail


def test_testnet_zero_cap_only_warns():
    c = _run_check(_settings(cap=0.0, paper=False, testnet=True))
    assert c.level == "WARN"


def test_paper_zero_cap_only_warns():
    c = _run_check(_settings(cap=0.0, paper=True, testnet=False))
    assert c.level == "WARN"


def test_positive_cap_passes():
    c = _run_check(_settings(cap=500.0, paper=False, testnet=False))
    assert c.level == "PASS"
    assert "armed" in c.detail.lower()
