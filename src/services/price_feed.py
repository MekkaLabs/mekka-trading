"""
src/services/price_feed.py
==========================
Exchange-agnostic mark-price WebSocket pump.

Background
----------
Before this module, `src.dashboard.server.MekkaDashboard._hl_price_pump_loop`
hardcoded a connection to `wss://api.hyperliquid{,-testnet}.xyz/ws` and
subscribed to the `allMids` channel. That made the live-prices feature
unusable when ACTIVE_EXCHANGE != "hyperliquid" — the dashboard would show
empty mark prices, the live-tick broadcast carried stale data, and any
PnL-aware widget would silently lock onto the entry price.

This module introduces a tiny strategy interface (`PriceFeedProvider`) plus
two concrete implementations:

  - `HyperliquidPriceFeed`  → wss://api.hyperliquid{,-testnet}.xyz/ws (allMids)
  - `BybitPriceFeed`        → wss://stream{,-testnet}.bybit.com/v5/public/linear

A factory, `make_price_feed()`, picks the implementation by reading
`settings.active_exchange`. Callers pass in a shared `prices` dict that the
provider mutates in place — this preserves the existing zero-copy contract
that several call sites already depend on (`dict(self._mark_prices)`).

Error policy
------------
The pump loop never propagates exceptions. WebSocket errors trigger a 5s
backoff + reconnect. A cancelled task returns cleanly so the dashboard can
shut down without zombie tasks. This mirrors the original HL pump's
behaviour exactly — we are widening the interface, not changing semantics.

Symbol mapping
--------------
Mekka uses bare symbols internally (e.g. ``BTC``, ``ETH``). Each provider
is responsible for translating that to its native wire format:

  - Hyperliquid: identical (``BTC``, ``ETH``)
  - Bybit perp linear: ``BTCUSDT``, ``ETHUSDT``

The provider writes back the Mekka-native key so call sites stay simple:
``prices["BTC"] == 65000.0`` regardless of which exchange is active.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
from typing import Iterable

import aiohttp

from src.config.settings import settings

logger = logging.getLogger("mekka.price_feed")


# --------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------

class PriceFeedProvider(abc.ABC):
    """Tiny strategy interface for a streaming mark-price source.

    Subclasses implement ``run`` as a long-lived coroutine. The contract:
      - Mutate ``prices`` in place (key = Mekka-native symbol like ``BTC``).
      - Reconnect on transient failures.
      - Return cleanly on ``asyncio.CancelledError``.
      - Never raise back to the caller.
    """

    name: str = "abstract"

    @abc.abstractmethod
    async def run(self, prices: dict[str, float]) -> None:
        """Stream marks into ``prices`` until cancelled."""
        raise NotImplementedError


# --------------------------------------------------------------------------
# Hyperliquid implementation (preserves prior behaviour exactly)
# --------------------------------------------------------------------------

class HyperliquidPriceFeed(PriceFeedProvider):
    """Subscribes to Hyperliquid ``allMids`` and writes every coin's price."""

    name = "hyperliquid"

    def _ws_url(self) -> str:
        # Mirror the legacy decision: we use the explicit HL network flag
        # because Hyperliquid does not expose a sandboxMode-style env switch
        # at the WebSocket level — the URL itself is the toggle.
        return (
            "wss://api.hyperliquid.xyz/ws"
            if settings.is_mainnet
            else "wss://api.hyperliquid-testnet.xyz/ws"
        )

    async def run(self, prices: dict[str, float]) -> None:
        url = self._ws_url()
        while True:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(
                        url,
                        heartbeat=20,
                        timeout=aiohttp.ClientWSTimeout(ws_close=5.0),
                    ) as ws:
                        await ws.send_json({
                            "method": "subscribe",
                            "subscription": {"type": "allMids"},
                        })
                        logger.info("HL price pump connected: %s", url)
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    if payload.get("channel") == "allMids":
                                        mids = (payload.get("data") or {}).get("mids") or {}
                                        for coin, price in mids.items():
                                            try:
                                                prices[coin] = float(price)
                                            except (TypeError, ValueError):
                                                # Skip malformed entries — we never
                                                # want a single bad coin to drop the
                                                # whole pump.
                                                pass
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("HL price pump disconnected (%s) — reconnecting in 5s", exc)
                await asyncio.sleep(5)


# --------------------------------------------------------------------------
# Bybit implementation (V5 public linear perps)
# --------------------------------------------------------------------------

class BybitPriceFeed(PriceFeedProvider):
    """Subscribes to Bybit V5 ``tickers.{symbol}USDT`` for each Mekka asset.

    Bybit doesn't have an "all symbols" channel like Hyperliquid's allMids,
    so we subscribe explicitly to ``settings.trading_assets``. If the
    operator adds an asset at runtime, the pump must be restarted — same
    constraint that already exists for Superman's candle subscriptions.
    """

    name = "bybit"

    def _ws_url(self) -> str:
        return (
            "wss://stream-testnet.bybit.com/v5/public/linear"
            if settings.bybit_testnet
            else "wss://stream.bybit.com/v5/public/linear"
        )

    def _topics_for(self, symbols: Iterable[str]) -> list[str]:
        # Bybit V5 perp linear uses ``{COIN}USDT`` (no slash, no colon).
        # Internal Mekka format is the bare coin (``BTC``).
        return [f"tickers.{sym.upper()}USDT" for sym in symbols if sym]

    async def run(self, prices: dict[str, float]) -> None:
        url = self._ws_url()
        # Snapshot at start; the constraint above means a restart is needed
        # if assets change. trading_assets is a cached_property so cheap.
        symbols = list(settings.trading_assets)
        topics = self._topics_for(symbols)
        if not topics:
            logger.warning(
                "BybitPriceFeed: TRADING_ASSETS is empty — pump will idle. "
                "Configure TRADING_ASSETS in .env."
            )
        while True:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(
                        url,
                        heartbeat=20,
                        timeout=aiohttp.ClientWSTimeout(ws_close=5.0),
                    ) as ws:
                        # Bybit V5 op="subscribe" with up to 10 args per frame.
                        # Chunking is paranoid future-proofing; today's
                        # TRADING_ASSETS list is always well under the cap.
                        for chunk_start in range(0, len(topics), 10):
                            chunk = topics[chunk_start:chunk_start + 10]
                            await ws.send_json({"op": "subscribe", "args": chunk})
                        logger.info(
                            "Bybit price pump connected: %s (topics=%d, testnet=%s)",
                            url, len(topics), settings.bybit_testnet,
                        )
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = json.loads(msg.data)
                                    topic = payload.get("topic") or ""
                                    if not topic.startswith("tickers."):
                                        # Server housekeeping frames (ack,
                                        # pong, error) — ignore quietly.
                                        continue
                                    data = payload.get("data") or {}
                                    # Bybit ticker frames carry the symbol
                                    # explicitly; trust that over parsing the
                                    # topic suffix.
                                    raw_sym = (data.get("symbol") or "").upper()
                                    if not raw_sym.endswith("USDT"):
                                        continue
                                    coin = raw_sym[:-4]  # BTCUSDT → BTC
                                    last = data.get("lastPrice") or data.get("markPrice")
                                    if last is None:
                                        continue
                                    try:
                                        prices[coin] = float(last)
                                    except (TypeError, ValueError):
                                        pass
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Bybit price pump disconnected (%s) — reconnecting in 5s", exc)
                await asyncio.sleep(5)


# --------------------------------------------------------------------------
# Binance — intentionally not implemented yet
# --------------------------------------------------------------------------

class _NullPriceFeed(PriceFeedProvider):
    """No-op feed used for exchanges without a Mekka WS implementation yet.

    Logs once and parks the coroutine indefinitely. The dashboard stays
    functional — REST-based widgets keep working, only the streaming
    mark-price cache stays empty. ``positions_provider.fetch_positions``
    falls back to entry price for PnL when ``mark_price`` is absent, so
    no widget crashes.
    """

    def __init__(self, reason: str) -> None:
        self.name = "null"
        self._reason = reason

    async def run(self, prices: dict[str, float]) -> None:
        logger.warning("PriceFeed disabled: %s", self._reason)
        try:
            # Sleep forever; the parent task is cancelled on shutdown.
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

def make_price_feed() -> PriceFeedProvider:
    """Return the right price-feed provider for the current ACTIVE_EXCHANGE.

    Centralising the dispatch here keeps the dashboard wiring trivial:
    ``asyncio.create_task(make_price_feed().run(self._mark_prices))``.
    """
    ex = settings.active_exchange
    if ex == "hyperliquid":
        return HyperliquidPriceFeed()
    if ex == "bybit":
        return BybitPriceFeed()
    if ex == "binance":
        # TODO(price_feed): implement Binance USDM futures WS. Until then,
        # the dashboard still boots — only the live-tick stream is empty.
        return _NullPriceFeed("Binance WS price feed not yet implemented")
    # Defensive default — Literal narrowing makes this unreachable, but a
    # future enum addition must not silently break the dashboard.
    return _NullPriceFeed(f"Unknown ACTIVE_EXCHANGE={ex!r}")
