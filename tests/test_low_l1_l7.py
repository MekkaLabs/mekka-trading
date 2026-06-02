"""Regressão L1/L7 (2026-06-01 audit) — cache de snapshot + reuso de CCXT.

L1 — cache de snapshot sem TTL: um cache arbitrariamente velho era servido como
     confiável. Agora descarta se mais velho que o TTL e anota a idade.
L7 — PortfolioManager construía+fechava um exchange CCXT a cada snapshot (pagando
     load_markets 9-18s). Agora reusa o _CCXT_SHARED do IronMan e NÃO o fecha.
"""
from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models.portfolio import EquitySnapshot, EquitySource


def _snap(ts):
    return EquitySnapshot(
        source=EquitySource.BINANCE,
        is_paper=False,
        equity_usd=1000.0,
        available_balance_usd=900.0,
        margin_used_usd=100.0,
        open_positions_count=0,
        positions=[],
        timestamp=ts,
    )


# ===========================================================================
# L1 — TTL do cache de snapshot
# ===========================================================================

def test_l1_stale_cache_rejected(tmp_path):
    from src.agents import portfolio_manager as pm_mod

    pm = pm_mod.PortfolioManager()
    cache = tmp_path / "snap.json"
    cache.write_text(_snap(datetime.now(timezone.utc) - timedelta(hours=2)).model_dump_json())

    with patch.object(pm_mod, "_SNAPSHOT_CACHE_FILE", cache), \
         patch.object(pm_mod, "settings",
                      types.SimpleNamespace(active_exchange="binance",
                                            snapshot_cache_max_age_seconds=900.0)):
        result = pm._load_cached_snapshot("degraded")

    assert result is None  # 2h > 15min TTL → descartado


def test_l1_fresh_cache_returned_and_flagged(tmp_path):
    from src.agents import portfolio_manager as pm_mod

    pm = pm_mod.PortfolioManager()
    cache = tmp_path / "snap.json"
    cache.write_text(_snap(datetime.now(timezone.utc) - timedelta(seconds=30)).model_dump_json())

    with patch.object(pm_mod, "_SNAPSHOT_CACHE_FILE", cache), \
         patch.object(pm_mod, "settings",
                      types.SimpleNamespace(active_exchange="binance",
                                            snapshot_cache_max_age_seconds=900.0)):
        result = pm._load_cached_snapshot("degraded")

    assert result is not None
    assert result.is_degraded  # error setado (com idade) → degradado
    assert "cache" in (result.error or "")


# ===========================================================================
# L7 — reuso do exchange compartilhado (sem fechar)
# ===========================================================================

@pytest.mark.asyncio
async def test_l7_reuses_shared_and_does_not_close():
    from src.agents import portfolio_manager as pm_mod

    pm = pm_mod.PortfolioManager()
    fake_ex = types.SimpleNamespace()
    fake_ex.fetch_balance = AsyncMock(return_value={})
    fake_ex.fetch_positions = AsyncMock(return_value=[])
    fake_ex.fetch_tickers = AsyncMock(return_value={})
    fake_ex.close = AsyncMock()
    sentinel = object()

    with patch("src.agents.iron_man.IronMan._get_ccxt_exchange",
               AsyncMock(return_value=fake_ex)), \
         patch.object(pm, "_parse_ccxt_snapshot", return_value=sentinel), \
         patch.object(pm_mod, "settings",
                      types.SimpleNamespace(active_exchange="binance",
                                            binance_market_type="linear",
                                            trading_assets=[])):
        result = await pm._run_ccxt_exchange("binance")

    assert result is sentinel
    fake_ex.fetch_balance.assert_awaited_once()
    fake_ex.close.assert_not_awaited()  # compartilhado → NÃO fecha


@pytest.mark.asyncio
async def test_l7_fallback_closes_own_client():
    """Se o cache compartilhado falha, usa cliente próprio E o fecha."""
    from src.agents import portfolio_manager as pm_mod

    pm = pm_mod.PortfolioManager()
    own_ex = types.SimpleNamespace()
    own_ex.fetch_balance = AsyncMock(return_value={})
    own_ex.fetch_positions = AsyncMock(return_value=[])
    own_ex.fetch_tickers = AsyncMock(return_value={})
    own_ex.close = AsyncMock()
    sentinel = object()

    with patch("src.agents.iron_man.IronMan._get_ccxt_exchange",
               AsyncMock(side_effect=Exception("cache miss"))), \
         patch.object(pm, "_connect_ccxt", AsyncMock(return_value=own_ex)), \
         patch.object(pm, "_parse_ccxt_snapshot", return_value=sentinel), \
         patch.object(pm_mod, "settings",
                      types.SimpleNamespace(active_exchange="binance",
                                            binance_market_type="linear",
                                            trading_assets=[])):
        result = await pm._run_ccxt_exchange("binance")

    assert result is sentinel
    own_ex.close.assert_awaited_once()  # cliente próprio → fecha
