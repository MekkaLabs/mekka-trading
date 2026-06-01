"""Regressão do backlog da revisão de agentes (2026-06-01, rodada 2).

- Aquaman: book vazio → score 0.0 (sem dados), não 0.1; slippage dos 2 lados.
- Spider-Man: flash crash usa queda close-a-close (não desvio da EMA-20).
- Batman: floor/teto de distância de stop-loss rejeita geometria patológica.
"""
from __future__ import annotations

import pytest


# ===========================================================================
# Aquaman — sem dados → score 0.0
# ===========================================================================

def test_aquaman_no_liquidity_sentinel():
    from src.agents.aquaman import Aquaman
    out = Aquaman()._no_liquidity("BTC")
    assert out.liquidity_score == 0.0          # não 0.1
    assert out.estimated_slippage_pct >= 0.05  # alto/explícito, não 1% plausível
    assert out.order_book_depth_buy == 0.0


def test_aquaman_slippage_uses_both_sides():
    import inspect
    from src.agents import aquaman as aq
    src = inspect.getsource(aq)
    # Estima slippage de asks (compra) E bids (venda) e usa o pior.
    assert "_estimate_slippage(asks" in src
    assert "_estimate_slippage(bids" in src
    assert "max(slippage_buy, slippage_sell)" in src


# ===========================================================================
# Spider-Man — flash crash close-a-close
# ===========================================================================

@pytest.mark.asyncio
async def test_spiderman_flash_crash_on_candle_drop():
    from src.agents.spider_man import SpiderMan
    from src.models.market_data import MarketData, Trend, AnomalySeverity

    # Último close caiu ~8% vs o anterior → flash crash real.
    md = MarketData(
        symbol="BTC", timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        timeframe="4h", price=92.0, trend=Trend.BEARISH, trend_strength=0.9,
        ema_20=100.0, recent_closes=[100.0, 100.0, 92.0],
    )
    rep = await SpiderMan().run(symbol="BTC", market_data=md)
    assert rep.should_pause is True
    assert rep.severity == AnomalySeverity.HIGH


@pytest.mark.asyncio
async def test_spiderman_no_flash_crash_in_steady_downtrend():
    """Downtrend suave (preço abaixo da EMA-20 mas sem queda brusca de candle)
    NÃO dispara flash crash — antes disparava falso positivo por desvio da EMA."""
    from src.agents.spider_man import SpiderMan
    from src.models.market_data import MarketData, Trend

    md = MarketData(
        symbol="BTC", timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        timeframe="4h", price=90.0, trend=Trend.BEARISH, trend_strength=0.8,
        ema_20=100.0,  # preço 10% abaixo da EMA (antes → falso flash crash)
        recent_closes=[93.0, 91.5, 90.0],  # quedas suaves (<5%/candle)
    )
    rep = await SpiderMan().run(symbol="BTC", market_data=md)
    assert "flash_crash" not in (rep.details or {})


# ===========================================================================
# Batman — floor/teto de distância de stop-loss
# ===========================================================================

def test_batman_has_stop_distance_gate():
    import inspect
    from src.agents import batman as b
    src = inspect.getsource(b)
    assert "min_stop_distance_pct" in src
    assert "max_stop_distance_pct" in src
    assert "Stop muito apertado" in src
    assert "Stop muito largo" in src
