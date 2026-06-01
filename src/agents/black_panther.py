"""
src/agents/black_panther.py
============================
Black Panther — Onchain Intelligence

Data sources (Hyperliquid REST API — public endpoints):
  - /info  → funding rate, open interest per asset
  - /info  → recent large trades (whale detection proxy)
  - Liquidation data via clearinghouse state

Returns `OnchainData` with:
  - funding_rate         : current perp funding rate
  - open_interest        : total OI in USD
  - long/short_liquidations_24h
  - net_flow (large buys - large sells)
  - WhaleSignal (ACCUMULATION / DISTRIBUTION / NEUTRAL)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from src.agents.base import AgentError, BaseAgent
from src.config.settings import settings
from src.models.market_data import OnchainData, WhaleSignal

_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _hl_url(path: str = "") -> str:
    base = (
        "https://api.hyperliquid.xyz"
        if settings.is_mainnet
        else "https://api.hyperliquid-testnet.xyz"
    )
    return f"{base}{path}"


async def _post(session: aiohttp.ClientSession, payload: dict) -> Any:
    """POST to Hyperliquid /info endpoint."""
    url = _hl_url("/info")
    async with session.post(url, json=payload, timeout=_TIMEOUT) as resp:
        if resp.status != 200:
            raise AgentError("BlackPanther", f"Hyperliquid API HTTP {resp.status}")
        return await resp.json(content_type=None)


async def _fetch_meta_and_ctx(session: aiohttp.ClientSession) -> tuple[list, list]:
    """Fetch metaAndAssetCtxs — contains fundingRate and openInterest per asset."""
    data = await _post(session, {"type": "metaAndAssetCtxs"})
    if not isinstance(data, list) or len(data) < 2:
        return [], []
    universe: list = data[0].get("universe", [])
    ctxs: list = data[1]
    return universe, ctxs


async def _fetch_recent_trades(session: aiohttp.ClientSession, coin: str) -> list:
    """Fetch recent trades for a coin (proxy for whale detection)."""
    try:
        trades = await _post(session, {"type": "trades", "coin": coin})
        return trades if isinstance(trades, list) else []
    except Exception:
        return []


def _find_asset_ctx(universe: list, ctxs: list, coin: str) -> Optional[dict]:
    """Find the asset context dict for a given coin symbol."""
    for i, asset in enumerate(universe):
        if asset.get("name", "").upper() == coin.upper():
            if i < len(ctxs):
                return ctxs[i]
    return None


def _parse_whale_flow(trades: list, min_usd: float = 50_000) -> tuple[float, float]:
    """
    Parse recent trades to estimate large-order buy/sell flow.

    Returns (large_buys_usd, large_sells_usd).
    Hyperliquid trades have: px (price), sz (size), side ('B'/'A')
    """
    buys = 0.0
    sells = 0.0
    for t in trades:
        try:
            px = float(t.get("px", 0))
            sz = float(t.get("sz", 0))
            side = t.get("side", "")
            notional = px * sz
            if notional < min_usd:
                continue
            if side == "B":
                buys += notional
            elif side == "A":
                sells += notional
        except (TypeError, ValueError):
            continue
    return buys, sells


class BlackPanther(BaseAgent[OnchainData]):
    """
    Onchain Intelligence — tracks funding rates, OI, and whale flow on Hyperliquid.

    Usage: onchain = await BlackPanther().run(symbol="BTC")
    """

    def __init__(self) -> None:
        super().__init__(
            "BlackPanther",
            "Onchain Intelligence — Hyperliquid derivatives data",
            timeout_s=30.0,  # Funding/OI/whale flow API calls
        )

    async def _run(self, symbol: str) -> OnchainData:  # type: ignore[override]
        """
        Fetch funding rate, open interest, and whale flow for a symbol.

        Parameters
        ----------
        symbol : e.g. 'BTC'
        """
        async with aiohttp.ClientSession() as session:
            meta_task = asyncio.create_task(_fetch_meta_and_ctx(session))
            trades_task = asyncio.create_task(_fetch_recent_trades(session, symbol))
            (universe, ctxs), recent_trades = await asyncio.gather(meta_task, trades_task)

        # --- Asset context (funding, OI) ---
        ctx = _find_asset_ctx(universe, ctxs, symbol)

        funding_rate: Optional[float] = None
        open_interest: Optional[float] = None

        if ctx:
            try:
                funding_rate = float(ctx.get("funding", 0))
            except (TypeError, ValueError):
                pass
            try:
                oi_str = ctx.get("openInterest", ctx.get("oi", None))
                if oi_str is not None:
                    open_interest = float(oi_str)
            except (TypeError, ValueError):
                pass

        # --- Whale flow from recent trades ---
        large_buys, large_sells = _parse_whale_flow(recent_trades)
        net_flow = large_buys - large_sells

        # --- Derive signal ---
        if abs(large_buys) + abs(large_sells) == 0:
            signal = WhaleSignal.NEUTRAL
        elif net_flow > 0:
            signal = WhaleSignal.ACCUMULATION
        else:
            signal = WhaleSignal.DISTRIBUTION

        # Review-fix (2026-06-01): distingue 'sem dados' de 'neutro real'. Se nem
        # funding nem trades vieram, o agente não mediu nada → data_available=False
        # (ProfessorX conta como fonte ausente em vez de 'mercado calmo').
        _has_data = (funding_rate is not None) or (abs(large_buys) + abs(large_sells) > 0)

        self._log.info(
            f"[BlackPanther] {symbol} | funding={funding_rate} OI={open_interest} "
            f"buys=${large_buys:,.0f} sells=${large_sells:,.0f} signal={signal.value} "
            f"data_available={_has_data}"
        )

        return OnchainData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            large_buys_24h=large_buys,
            large_sells_24h=large_sells,
            net_flow=net_flow,
            signal=signal,
            funding_rate=funding_rate,
            open_interest=open_interest,
            long_liquidations_24h=None,   # requires premium data feed
            short_liquidations_24h=None,
            data_available=_has_data,
        )
