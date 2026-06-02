"""
tests/test_ironman_maker_entry.py
=================================
Entrada MAKER (post-only) com fallback para taker: _try_maker_entry posta no
touch e espera encher; se não encher, cancela e retorna None (caller cai para
limit_ioc). Nunca perde a entrada.
"""

from __future__ import annotations

import pytest

from src.agents.iron_man import IronMan


class _FakeExchange:
    """Mock CCXT async exchange para o caminho maker."""

    def __init__(self, *, fill_on_poll=False, reject=False, immediate_fill=False):
        self._fill_on_poll = fill_on_poll
        self._reject = reject
        self._immediate = immediate_fill
        self._polls = 0
        self.cancelled = []
        self.created = []

    async def fetch_ticker(self, sym):
        return {"bid": 100.0, "ask": 100.2}

    def price_to_precision(self, sym, px):
        return round(px, 2)

    async def create_order(self, **kw):
        if self._reject:
            raise Exception("post-only would cross (rejected)")
        self.created.append(kw)
        return {"id": "MK1", "filled": (kw["amount"] if self._immediate else 0.0)}

    async def fetch_order(self, oid, sym):
        self._polls += 1
        # enche na 1ª consulta se configurado
        return {"id": oid, "filled": (1.0 if self._fill_on_poll else 0.0)}

    async def cancel_order(self, oid, sym):
        self.cancelled.append(oid)
        return {"id": oid, "status": "canceled"}


@pytest.mark.asyncio
async def test_maker_fills_immediately_returns_order():
    ex = _FakeExchange(immediate_fill=True)
    im = IronMan()
    out = await im._try_maker_entry(ex, "BTC/USDT", "buy", True, 1.0, wait_seconds=2)
    assert out is not None
    assert float(out.get("filled")) == 1.0
    assert ex.cancelled == ["MK1"]          # cancela resto (no-op se cheio)


@pytest.mark.asyncio
async def test_maker_fills_on_poll():
    ex = _FakeExchange(fill_on_poll=True)
    im = IronMan()
    out = await im._try_maker_entry(ex, "BTC/USDT", "buy", True, 1.0, wait_seconds=2)
    assert out is not None
    assert float(out.get("filled")) == 1.0


@pytest.mark.asyncio
async def test_maker_no_fill_returns_none_and_cancels():
    ex = _FakeExchange(fill_on_poll=False)
    im = IronMan()
    out = await im._try_maker_entry(ex, "BTC/USDT", "buy", True, 1.0, wait_seconds=2)
    assert out is None                      # não encheu → fallback taker
    assert ex.cancelled == ["MK1"]          # ordem cancelada


@pytest.mark.asyncio
async def test_maker_rejected_returns_none():
    ex = _FakeExchange(reject=True)
    im = IronMan()
    out = await im._try_maker_entry(ex, "BTC/USDT", "sell", False, 1.0, wait_seconds=2)
    assert out is None                      # rejeitado (cruzaria) → fallback
    assert ex.cancelled == []               # nada para cancelar
