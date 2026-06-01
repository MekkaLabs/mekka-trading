"""
src/agents/aquaman.py
======================
Aquaman — Liquidity Analyst

Data source: Hyperliquid REST API — order book (L2 snapshot)

Endpoint: POST /info  { "type": "l2Book", "coin": "BTC" }

Analysis:
  - Bid/ask spread as % of mid price
  - Order book depth (USD) within 0.5% of mid on each side
  - Depth imbalance (buy pressure vs sell pressure)
  - Estimated slippage for a $10,000 market order
  - Composite liquidity score (0 = illiquid, 1 = very liquid)

Returns `LiquidityData`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from src.agents.base import AgentError, BaseAgent
from src.config.settings import settings
from src.models.market_data import LiquidityData

_TIMEOUT = aiohttp.ClientTimeout(total=10)
_DEPTH_BAND_PCT = 0.005   # 0.5% from mid
_SLIPPAGE_ORDER_USD = 10_000.0


def _hl_url() -> str:
    base = (
        "https://api.hyperliquid.xyz"
        if settings.is_mainnet
        else "https://api.hyperliquid-testnet.xyz"
    )
    return f"{base}/info"


async def _fetch_l2_book(session: aiohttp.ClientSession, coin: str) -> Any:
    payload = {"type": "l2Book", "coin": coin}
    async with session.post(_hl_url(), json=payload, timeout=_TIMEOUT) as resp:
        if resp.status != 200:
            raise AgentError("Aquaman", f"L2 book HTTP {resp.status} for {coin}")
        return await resp.json(content_type=None)


def _parse_levels(levels: list) -> list[tuple[float, float]]:
    """Parse Hyperliquid L2 level list → [(price, size_usd), ...]."""
    result = []
    for lvl in levels:
        try:
            px = float(lvl.get("px", 0))
            sz = float(lvl.get("sz", 0))
            if px > 0 and sz > 0:
                result.append((px, px * sz))
        except (TypeError, ValueError):
            continue
    return result


def _estimate_slippage(levels: list[tuple[float, float]], order_usd: float) -> float:
    """
    Walk the order book to estimate average slippage for a market order of `order_usd`.

    Returns slippage as a fraction of mid price (e.g. 0.002 = 0.2%).
    Returns 1.0 (100% slippage) if the book is too thin.
    """
    if not levels:
        return 1.0

    best_px = levels[0][0]
    remaining = order_usd
    weighted_sum = 0.0
    filled = 0.0

    for px, usd in levels:
        take = min(remaining, usd)
        weighted_sum += px * take
        filled += take
        remaining -= take
        if remaining <= 0:
            break

    if filled < order_usd * 0.5:
        return 1.0  # book too thin

    avg_px = weighted_sum / filled
    return abs(avg_px - best_px) / best_px if best_px > 0 else 1.0


def _compute_liquidity_score(
    spread_pct: float,
    depth_buy: float,
    depth_sell: float,
    slippage: float,
) -> float:
    """
    Heuristic liquidity score 0.0–1.0.

    Penalties:
      - Spread > 0.1% → bad
      - Depth < $100k each side → bad
      - Slippage > 0.3% → bad
    """
    score = 1.0

    # Spread penalty (max penalty at 1%)
    score -= min(spread_pct / 0.01, 1.0) * 0.30

    # Depth penalty
    min_depth = min(depth_buy, depth_sell)
    if min_depth < 100_000:
        score -= (1.0 - min_depth / 100_000) * 0.40

    # Slippage penalty
    score -= min(slippage / 0.005, 1.0) * 0.30

    return round(max(0.0, min(1.0, score)), 4)


class Aquaman(BaseAgent[LiquidityData]):
    """
    Liquidity Analyst — analyses order book depth and slippage on Hyperliquid.

    Usage: liquidity = await Aquaman().run(symbol="BTC")
    """

    def __init__(self) -> None:
        super().__init__(
            "Aquaman",
            "Liquidity Analyst — order book depth and slippage",
            timeout_s=15.0,  # 1 chamada de L2 book + cálculos locais
        )

    def _no_liquidity(self, symbol: str) -> LiquidityData:
        """Sentinela de 'sem dados de liquidez' (score 0.0, slip alto explícito)."""
        return LiquidityData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid_ask_spread_pct=0.05,    # 5% — claramente ruim, não 1% plausível
            order_book_depth_buy=0.0,
            order_book_depth_sell=0.0,
            estimated_slippage_pct=0.05,
            liquidity_score=0.0,        # 0.0 = sem liquidez (não 0.1)
        )

    async def _run(self, symbol: str) -> LiquidityData:  # type: ignore[override]
        # Review-fix (2026-06-01): degradar em vez de LANÇAR. Antes _fetch_l2_book
        # podia levantar AgentError (status≠200) e _run propagava → o orquestrador
        # transformava em liquidity=None (trade podia prosseguir sem info de
        # liquidez). Layer1 deve retornar um resultado degradado, não lançar.
        try:
            async with aiohttp.ClientSession() as session:
                book_data = await _fetch_l2_book(session, symbol)
            raw_levels = book_data.get("levels", [[], []])
            bids_raw = raw_levels[0] if len(raw_levels) > 0 else []
            asks_raw = raw_levels[1] if len(raw_levels) > 1 else []
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Aquaman] {symbol} — book indisponível ({exc}) — sem dados")
            return self._no_liquidity(symbol)

        bids = sorted(_parse_levels(bids_raw), key=lambda x: -x[0])  # high→low
        asks = sorted(_parse_levels(asks_raw), key=lambda x: x[0])   # low→high

        if not bids or not asks:
            # Review-fix: book vazio = SEM DADOS, não "liquidez razoável".
            self._log.warning(f"[Aquaman] {symbol} — order book VAZIO (sem dados)")
            return self._no_liquidity(symbol)

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid = (best_bid + best_ask) / 2.0

        spread_pct = (best_ask - best_bid) / mid if mid > 0 else 0.0

        # Depth within ±0.5% of mid
        depth_buy = sum(
            usd for px, usd in bids if abs(px - mid) / mid <= _DEPTH_BAND_PCT
        )
        depth_sell = sum(
            usd for px, usd in asks if abs(px - mid) / mid <= _DEPTH_BAND_PCT
        )

        # Review-fix: estimar slippage dos DOIS lados (asks p/ compra, bids p/
        # venda) e reportar o PIOR (conservador). Antes só o lado ask era
        # considerado — slippage errado para ordens de venda/short.
        slippage_buy = _estimate_slippage(asks, _SLIPPAGE_ORDER_USD)
        slippage_sell = _estimate_slippage(bids, _SLIPPAGE_ORDER_USD)
        slippage = max(slippage_buy, slippage_sell)

        # Composite score
        liq_score = _compute_liquidity_score(spread_pct, depth_buy, depth_sell, slippage)

        self._log.info(
            f"[Aquaman] {symbol} | spread={spread_pct:.4%} "
            f"depth_buy=${depth_buy:,.0f} depth_sell=${depth_sell:,.0f} "
            f"slippage={slippage:.4%} score={liq_score:.2f}"
        )

        return LiquidityData(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid_ask_spread_pct=round(spread_pct, 6),
            order_book_depth_buy=round(depth_buy, 2),
            order_book_depth_sell=round(depth_sell, 2),
            estimated_slippage_pct=round(slippage, 6),
            liquidity_score=liq_score,
        )
