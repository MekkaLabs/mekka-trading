"""
tests/test_nick_fury_stale_price_guard.py
=========================================
Guard de decisão obsoleta (stale-price): se o mercado andou demais entre a
decisão do Vision e a execução, a entrada é cancelada (tese/SL/TP obsoletos).
Testa o helper de drift _entry_drift_pct.
"""

from __future__ import annotations

import pytest

from src.agents.nick_fury import NickFury


def test_drift_zero_when_same_price():
    assert NickFury._entry_drift_pct(100.0, 100.0) == 0.0


def test_drift_one_percent():
    assert NickFury._entry_drift_pct(100.0, 101.0) == pytest.approx(0.01)


def test_drift_symmetric_down():
    assert NickFury._entry_drift_pct(100.0, 99.0) == pytest.approx(0.01)


def test_drift_invalid_entry_is_zero():
    assert NickFury._entry_drift_pct(0.0, 100.0) == 0.0
    assert NickFury._entry_drift_pct(100.0, 0.0) == 0.0


def test_threshold_comparison():
    # entry 100, mercado 101.5 → 1.5% drift; limite 1% → excede (cancela)
    drift = NickFury._entry_drift_pct(100.0, 101.5)
    assert drift > 0.01
    # mercado 100.5 → 0.5% < 1% → não cancela
    assert NickFury._entry_drift_pct(100.0, 100.5) < 0.01
