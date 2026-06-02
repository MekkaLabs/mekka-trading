"""Regressão M6/M8/M9 (2026-06-01 audit) — gates residuais de mainnet.

M6 — preflight check_min_balance: FAIL em mainnet+live quando o equity real está
     abaixo de min_equity_floor_usd; WARN quando o piso não foi definido.
M8 — staleness do feed de markPrice: um mark WS velho não deve ser tratado como
     fresco.
M9 — clamp de leverage COIN-M (contrato que o Batman passou a aplicar no loop).
"""
from __future__ import annotations

import time
import types
from unittest.mock import patch

import scripts.preflight_mainnet as pf


# ===========================================================================
# M8 — staleness do feed de markPrice
# ===========================================================================

def test_m8_fresh_then_stale():
    from src.services import price_feed as pftf

    pftf._LAST_MARK_TS["BTC"] = time.monotonic()
    assert pftf.mark_is_fresh("BTC", 15.0) is True

    pftf._LAST_MARK_TS["BTC"] = time.monotonic() - 100.0
    assert pftf.mark_is_fresh("BTC", 15.0) is False
    pftf._LAST_MARK_TS.pop("BTC", None)


def test_m8_unknown_symbol_treated_fresh():
    from src.services import price_feed as pftf

    pftf._LAST_MARK_TS.pop("ZZZ", None)
    # Sem registro WS (paper/HL) → fresco para não quebrar caminhos alheios.
    assert pftf.mark_is_fresh("ZZZ", 15.0) is True


# ===========================================================================
# M9 — clamp de leverage COIN-M
# ===========================================================================

def test_m9_clamp_linear_is_noop():
    from src.services.coin_m_leverage_caps import clamp_leverage

    assert clamp_leverage(20, "BTC", market_type="linear") == (20, None)


def test_m9_clamp_inverse_clamps_altcoin():
    from src.services.coin_m_leverage_caps import clamp_leverage

    eff, warn = clamp_leverage(100, "SOL", market_type="inverse")
    assert eff <= 50
    assert warn is not None


# ===========================================================================
# M6 — preflight check_min_balance
# ===========================================================================

def _settings(*, floor, paper, testnet):
    return types.SimpleNamespace(
        min_equity_floor_usd=floor,
        paper_trading=paper,
        active_exchange="binance",
        exchange_is_testnet=lambda _ex=None: testnet,
    )


def _run_check(s, pm_cls=None):
    report = pf.PreflightReport()
    ctx = [patch.object(pf, "_get_settings", return_value=s)]
    if pm_cls is not None:
        ctx.append(patch("src.agents.portfolio_manager.PortfolioManager", pm_cls))
    import contextlib
    with contextlib.ExitStack() as stack:
        for c in ctx:
            stack.enter_context(c)
        pf.check_min_balance(report)
    return report.checks[0]


def test_m6_no_floor_warns_in_mainnet_live():
    c = _run_check(_settings(floor=0.0, paper=False, testnet=False))
    assert c.level == "WARN"


def test_m6_no_floor_ok_in_paper():
    c = _run_check(_settings(floor=0.0, paper=True, testnet=False))
    assert c.level == "PASS"


def test_m6_equity_below_floor_fails():
    class FakePM:
        async def run(self):
            return types.SimpleNamespace(equity_usd=100.0, is_degraded=False)

    c = _run_check(_settings(floor=1000.0, paper=False, testnet=False), pm_cls=FakePM)
    assert c.level == "FAIL"


def test_m6_equity_above_floor_passes():
    class FakePM:
        async def run(self):
            return types.SimpleNamespace(equity_usd=5000.0, is_degraded=False)

    c = _run_check(_settings(floor=1000.0, paper=False, testnet=False), pm_cls=FakePM)
    assert c.level == "PASS"


def test_m6_degraded_snapshot_warns():
    class FakePM:
        async def run(self):
            return types.SimpleNamespace(equity_usd=0.0, is_degraded=True)

    c = _run_check(_settings(floor=1000.0, paper=False, testnet=False), pm_cls=FakePM)
    assert c.level == "WARN"
