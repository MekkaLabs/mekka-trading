"""
tests/test_ironman_execution_quality.py
=======================================
Qualidade de execução do IronMan: mede o slippage realizado (avg fill vs entry
planejado) e, em fill LIVE acima do limite, alerta + registra lição (loop
execução→aprendizado).
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from src.agents.iron_man import IronMan
from src.models.execution import ExecutionResult, ExecutionStatus


def _res(side, avg, *, paper=True, symbol="BTC", status=ExecutionStatus.PAPER):
    return ExecutionResult(
        symbol=symbol, status=status, is_paper=paper, side=side,
        avg_price=avg, quantity=1.0, notional_usd=avg,
    )


@pytest.mark.asyncio
async def test_long_slippage_worse_is_positive():
    im = IronMan()
    out = await im._annotate_execution_quality(_res("long", 100.5), NS(entry_price=100.0, symbol="BTC"))
    assert out.metadata["entry_slippage_bps"] == 50.0


@pytest.mark.asyncio
async def test_short_slippage_worse_is_positive():
    im = IronMan()
    out = await im._annotate_execution_quality(_res("short", 99.5), NS(entry_price=100.0, symbol="ETH"))
    assert out.metadata["entry_slippage_bps"] == 50.0


@pytest.mark.asyncio
async def test_favorable_fill_is_negative():
    im = IronMan()
    out = await im._annotate_execution_quality(_res("long", 99.8), NS(entry_price=100.0, symbol="SOL"))
    assert out.metadata["entry_slippage_bps"] == -20.0


@pytest.mark.asyncio
async def test_skipped_status_not_annotated():
    im = IronMan()
    res = _res("long", 0.0, status=ExecutionStatus.SKIPPED)
    out = await im._annotate_execution_quality(res, NS(entry_price=100.0, symbol="BTC"))
    assert "entry_slippage_bps" not in (out.metadata or {})


@pytest.mark.asyncio
async def test_high_live_slippage_records_lesson(monkeypatch):
    im = IronMan()
    learned = {}

    async def fake_learn(lesson, **kw):
        learned["lesson"] = lesson
        learned["kw"] = kw
        return {"status": "new"}

    monkeypatch.setattr(im, "learn", fake_learn)
    monkeypatch.setattr("src.config.settings.settings.execution_slippage_alert_bps", 30.0)

    # LIVE fill com 60bps de slippage (> 30) → registra lição
    out = await im._annotate_execution_quality(
        _res("long", 100.6, paper=False, status=ExecutionStatus.FILLED),
        NS(entry_price=100.0, symbol="BTC"),
    )
    assert out.metadata["entry_slippage_bps"] == 60.0
    assert "lesson" in learned
    assert "BTC" in learned["lesson"]
    assert learned["kw"].get("category") == "execução"


@pytest.mark.asyncio
async def test_paper_high_slippage_does_not_alert(monkeypatch):
    """Paper não dispara alerta/lição mesmo com slippage alto."""
    im = IronMan()
    called = {"n": 0}

    async def fake_learn(*a, **k):
        called["n"] += 1
        return {}

    monkeypatch.setattr(im, "learn", fake_learn)
    out = await im._annotate_execution_quality(
        _res("long", 105.0, paper=True),  # 500bps mas é paper
        NS(entry_price=100.0, symbol="BTC"),
    )
    assert out.metadata["entry_slippage_bps"] == 500.0
    assert called["n"] == 0   # paper não registra lição de execução
