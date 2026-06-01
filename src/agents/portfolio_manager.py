"""
src/agents/portfolio_manager.py
================================
Portfolio Manager — read-only account-state poller.

Sits in Layer 4 alongside Nick Fury. Each main cycle Nick Fury calls
Portfolio Manager once to get a fresh `EquitySnapshot`, then forwards
the equity figure to Iron Man and the open-positions count to Batman.

Hard rules
----------
  • READ-ONLY. Never sends orders, never moves money. Queries the active
    exchange only for balance/positions snapshots.
  • Defensive degradation: if credentials are missing, the exchange is
    unreachable, or parsing fails, Portfolio Manager returns a paper
    fallback `EquitySnapshot` with `source=PAPER_FALLBACK` and an
    `error` string — never raises.
  • Lazy import of any networking lib (aiohttp) inside `_run` to keep
    module import cheap, mirroring Iron Man / Vision pattern.
  • In paper-trading mode WITHOUT configured credentials, returns paper
    fallback immediately (no network call).
"""

from __future__ import annotations

import json
import asyncio
from typing import Any, Optional
from pathlib import Path

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.portfolio import (
    EquitySnapshot,
    EquitySource,
    PositionSummary,
)


_PLACEHOLDER_WALLET = "0x0000000000000000000000000000000000000000"
_SNAPSHOT_CACHE_FILE = Path("data/portfolio_snapshot_cache.json")


def _hl_info_url() -> str:
    return (
        "https://api.hyperliquid.xyz/info"
        if settings.is_mainnet
        else "https://api.hyperliquid-testnet.xyz/info"
    )


def _bybit_api_base_url() -> str:
    return (
        "https://api.bybit.com"
        if settings.is_mainnet
        else "https://api-testnet.bybit.com"
    )


class PortfolioManager(BaseAgent[EquitySnapshot]):
    """
    Read-only account-state poller.

    Usage:
        snapshot = await PortfolioManager().run()
    """

    def __init__(self) -> None:
        super().__init__(
            codename="PortfolioManager",
            role="Portfolio Manager — read-only equity & positions snapshot",
        )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(self) -> EquitySnapshot:  # type: ignore[override]
        try:
            if settings.active_exchange == "hyperliquid":
                snapshot = await self._run_hyperliquid()
            else:
                snapshot = await self._run_ccxt_exchange(settings.active_exchange)
        except Exception as exc:  # noqa: BLE001
            reason = f"{settings.active_exchange.title()} snapshot failed: {type(exc).__name__}: {exc}"
            cached = self._load_cached_snapshot(reason=reason)
            if cached is not None:
                self._log.warning(f"{cached.summary()} (cached)")
                return cached
            return self._paper_fallback(reason=reason)

        self._save_cached_snapshot(snapshot)
        self._log.info(snapshot.summary())
        return snapshot

    async def _run_hyperliquid(self) -> EquitySnapshot:
        wallet = (settings.hyperliquid_wallet_address or "").lower()

        if not wallet or wallet == _PLACEHOLDER_WALLET:
            return self._paper_fallback(reason="No Hyperliquid wallet configured")

        try:
            raw = await self._fetch_clearinghouse_state(wallet)
        except Exception as exc:  # noqa: BLE001
            return self._paper_fallback(
                reason=f"Hyperliquid unreachable: {type(exc).__name__}: {exc}"
            )

        try:
            return self._parse_clearinghouse_state(raw)
        except Exception as exc:  # noqa: BLE001
            return self._paper_fallback(
                reason=f"Parse failed: {type(exc).__name__}: {exc}"
            )

    async def _run_ccxt_exchange(self, exchange_id: str) -> EquitySnapshot:
        if exchange_id == "bybit":
            raw_balance, raw_positions = await self._fetch_bybit_account_snapshot()
            return self._parse_bybit_rest_snapshot(raw_balance, raw_positions)

        exchange = await self._connect_ccxt(exchange_id)
        try:
            balance = await exchange.fetch_balance()
            positions = await exchange.fetch_positions()
            # P0-5: em COIN-M precisa mark prices pra converter saldo coin→USD.
            # Best-effort fetch_tickers; injeta no balance dict via chave
            # privada que parse_ccxt_snapshot extrai.
            if (exchange_id == "binance"
                    and str(getattr(settings, "binance_market_type", "linear")) == "inverse"):
                try:
                    assets = list(getattr(settings, "trading_assets", []) or [])
                    if assets:
                        ccxt_syms = [f"{a.upper()}/USD:{a.upper()}" for a in assets]
                        tickers = await exchange.fetch_tickers(ccxt_syms)
                        mp = {}
                        for sym, ticker in (tickers or {}).items():
                            coin = sym.split("/")[0].upper() if "/" in sym else sym
                            last = ticker.get("last") or ticker.get("mark")
                            if last:
                                mp[coin] = float(last)
                        balance["_mekka_mark_prices"] = mp
                except Exception as exc:  # noqa: BLE001
                    self._log.warning(
                        f"[PortfolioManager/COIN-M] fetch_tickers failed: {exc}"
                    )
            return self._parse_ccxt_snapshot(exchange_id, balance, positions)
        finally:
            close_fn = getattr(exchange, "close", None)
            if close_fn is not None:
                maybe_awaitable = close_fn()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable

    async def _connect_ccxt(self, exchange_id: str) -> Any:
        import ccxt.async_support as ccxt  # noqa: WPS433

        cls = getattr(ccxt, exchange_id, None)
        if cls is None:
            raise RuntimeError(f"Unsupported CCXT exchange: {exchange_id}")

        cfg: dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": 20_000,
            "options": {
                "defaultType": "swap",
                # 60s is Binance's max recvWindow. A wide window makes the
                # InvalidNonce -1021 ("timestamp outside recvWindow") effectively
                # impossible from clock drift, which we saw intermittently.
                "recvWindow": 60_000,
                "adjustForTimeDifference": True,
            },
        }
        if exchange_id == "bybit":
            if not settings.bybit_api_key or not settings.bybit_api_secret:
                raise RuntimeError("Bybit API credentials missing")
            cfg["apiKey"] = settings.bybit_api_key
            cfg["secret"] = settings.bybit_api_secret
        elif exchange_id == "binance":
            if not settings.binance_api_key or not settings.binance_api_secret:
                raise RuntimeError("Binance API credentials missing")
            cfg["apiKey"] = settings.binance_api_key
            cfg["secret"] = settings.binance_api_secret
            cfg["options"].update(
                {
                    "defaultSubType": "linear",
                    "fetchMarkets": {"types": ["linear"]},
                    "disableFuturesSandboxWarning": True,
                }
            )

        exchange = cls(cfg)
        try:
            # H5 fix (2026-06-01 audit): rotear sandbox POR exchange, não por
            # settings.is_mainnet (que só olha hyperliquid_network). Antes, um
            # operador em Binance mainnet com hyperliquid_network=testnet lia
            # saldo/posições da Binance TESTNET → equity fictício inflando sizing.
            if exchange_id in ("bybit", "binance") and settings.exchange_is_testnet(exchange_id):
                set_sandbox_mode = getattr(exchange, "set_sandbox_mode", None)
                if callable(set_sandbox_mode):
                    set_sandbox_mode(True)
            for attempt in range(1, 4):
                try:
                    await exchange.load_markets()
                    break
                except Exception:
                    if attempt >= 3:
                        raise
                    await asyncio.sleep(float(attempt))
            return exchange
        except Exception:
            close_fn = getattr(exchange, "close", None)
            if close_fn is not None:
                maybe_awaitable = close_fn()
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable
            raise

    # ------------------------------------------------------------------
    # Bybit V5 fetch
    # ------------------------------------------------------------------

    async def _fetch_bybit_account_snapshot(self) -> tuple[dict[str, Any], dict[str, Any]]:
        import aiohttp  # noqa: WPS433
        import asyncio  # noqa: WPS433

        if not settings.bybit_api_key or not settings.bybit_api_secret:
            raise RuntimeError("Bybit API credentials missing")

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            timeout = aiohttp.ClientTimeout(total=20)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    balance = await self._bybit_signed_get(
                        session,
                        "/v5/account/wallet-balance",
                        {"accountType": "UNIFIED"},
                    )
                    positions = await self._bybit_signed_get(
                        session,
                        "/v5/position/list",
                        {"category": "linear", "settleCoin": "USDT", "limit": "200"},
                    )
                return balance, positions
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < 3:
                    await asyncio.sleep(1.0 * attempt)
        raise RuntimeError(f"Bybit snapshot retries exhausted: {last_exc}") from last_exc

    async def _fetch_bybit_server_time(self, session: Any) -> int:
        async with session.get(f"{_bybit_api_base_url()}/v5/market/time") as resp:
            if resp.status != 200:
                raise RuntimeError(f"Bybit server time HTTP {resp.status}")
            data = await resp.json(content_type=None)
        try:
            return int((data.get("result") or {}).get("timeNano", "0")[:13]) or int(
                (data.get("result") or {}).get("timeSecond", "0")
            ) * 1000
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Invalid Bybit server time payload: {exc}") from exc

    async def _bybit_signed_get(
        self,
        session: Any,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        import hashlib  # noqa: WPS433
        import hmac  # noqa: WPS433
        from urllib.parse import urlencode  # noqa: WPS433

        server_time_ms = await self._fetch_bybit_server_time(session)
        recv_window = "15000"
        query = urlencode(params)
        payload = f"{server_time_ms}{settings.bybit_api_key}{recv_window}{query}"
        signature = hmac.new(
            settings.bybit_api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-BAPI-API-KEY": settings.bybit_api_key,
            "X-BAPI-TIMESTAMP": str(server_time_ms),
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
        }
        url = f"{_bybit_api_base_url()}{path}"
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Bybit {path} HTTP {resp.status}")
            data = await resp.json(content_type=None)
        if str(data.get("retCode")) != "0":
            raise RuntimeError(
                f"Bybit {path} retCode={data.get('retCode')} retMsg={data.get('retMsg')}"
            )
        return data

    # ------------------------------------------------------------------
    # HL Info fetch
    # ------------------------------------------------------------------

    async def _fetch_clearinghouse_state(self, wallet: str) -> dict[str, Any]:
        """POST /info with type=clearinghouseState."""
        # Lazy import — keeps module import cheap and isolates network deps
        import aiohttp  # noqa: WPS433

        payload = {"type": "clearinghouseState", "user": wallet}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _hl_info_url(), json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} from Hyperliquid /info")
                data = await resp.json(content_type=None)
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Unexpected clearinghouseState shape: {type(data).__name__}"
            )
        return data

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    def _parse_clearinghouse_state(self, raw: dict[str, Any]) -> EquitySnapshot:
        """
        Parse Hyperliquid clearinghouseState into an EquitySnapshot.

        Expected shape (relevant subset):
          {
            "marginSummary": { "accountValue": "12345.67", "totalMarginUsed": "234.56" },
            "withdrawable": "12000.0",
            "assetPositions": [
              {
                "type": "oneWay",
                "position": {
                  "coin": "BTC",
                  "szi": "0.5",            # signed size (negative = short)
                  "entryPx": "65000.0",
                  "unrealizedPnl": "12.34",
                  "leverage": { "value": 3 } | { "type": "cross" }
                }
              },
              ...
            ]
          }
        """
        margin = raw.get("marginSummary", {}) or {}
        equity = float(margin.get("accountValue", 0.0) or 0.0)
        margin_used = float(margin.get("totalMarginUsed", 0.0) or 0.0)
        withdrawable_raw = raw.get("withdrawable", None)
        if withdrawable_raw is not None:
            available = float(withdrawable_raw)
        else:
            available = max(equity - margin_used, 0.0)

        raw_positions = raw.get("assetPositions", []) or []
        positions: list[PositionSummary] = []
        for entry in raw_positions:
            try:
                pos = (entry or {}).get("position", {}) or {}
                szi = float(pos.get("szi", 0.0) or 0.0)
                if szi == 0.0:
                    continue
                entry_px = float(pos.get("entryPx", 0.0) or 0.0)
                if entry_px <= 0:
                    continue
                lev_raw = pos.get("leverage", {}) or {}
                lev_val: Optional[int] = None
                try:
                    raw_v = lev_raw.get("value")
                    lev_val = int(raw_v) if raw_v is not None else None
                except (TypeError, ValueError):
                    lev_val = None
                positions.append(
                    PositionSummary(
                        symbol=str(pos.get("coin", "?")).upper(),
                        side="long" if szi > 0 else "short",
                        size=abs(szi),
                        entry_price=entry_px,
                        unrealized_pnl_usd=float(pos.get("unrealizedPnl", 0.0) or 0.0),
                        leverage=lev_val,
                    )
                )
            except (TypeError, ValueError, KeyError):
                # Skip malformed entries; do not crash the snapshot
                continue

        return EquitySnapshot(
            source=EquitySource.HYPERLIQUID,
            is_paper=settings.paper_trading,
            equity_usd=equity,
            available_balance_usd=available,
            margin_used_usd=margin_used,
            open_positions_count=len(positions),
            positions=positions,
            error=None,
        )

    def _parse_ccxt_snapshot(
        self,
        exchange_id: str,
        balance: dict[str, Any],
        positions: list[dict[str, Any]],
    ) -> EquitySnapshot:
        source = (
            EquitySource.BYBIT
            if exchange_id == "bybit"
            else EquitySource.BINANCE
        )

        # P0-5 fix: mark_prices injetados pelo caller async em inverse mode.
        # `balance` dict pode ter chave `_mekka_mark_prices` pré-populada
        # pelo _run_ccxt_exchange. Sync method não pode fazer fetch.
        mark_prices_for_balance = balance.pop("_mekka_mark_prices", {}) or {}
        equity, available = self._extract_balance_totals(
            exchange_id, balance, mark_prices=mark_prices_for_balance,
        )
        parsed_positions: list[PositionSummary] = []
        margin_used = max(equity - available, 0.0)

        for pos in positions or []:
            contracts = self._safe_float(
                pos.get("contracts"),
                self._safe_float((pos.get("info") or {}).get("size"), 0.0),
            )
            if abs(contracts) <= 1e-12:
                continue

            side_raw = str(pos.get("side") or (pos.get("info") or {}).get("side") or "").lower()
            if side_raw not in ("long", "short"):
                side_raw = "long" if contracts > 0 else "short"

            entry_price = self._safe_float(
                pos.get("entryPrice"),
                self._safe_float((pos.get("info") or {}).get("avgPrice"), 0.0),
            )
            if entry_price <= 0:
                continue

            symbol = self._normalize_symbol(
                str(pos.get("symbol") or (pos.get("info") or {}).get("symbol") or "?")
            )
            unrealized = self._safe_float(
                pos.get("unrealizedPnl"),
                self._safe_float((pos.get("info") or {}).get("unrealisedPnl"), 0.0),
            )
            leverage = self._safe_int(
                pos.get("leverage"),
                self._safe_int((pos.get("info") or {}).get("leverage"), None),
            )
            mark_price = self._safe_float(
                pos.get("markPrice"),
                self._safe_float((pos.get("info") or {}).get("markPrice"), 0.0),
            ) or None
            liq_price = self._safe_float(
                pos.get("liquidationPrice"),
                self._safe_float((pos.get("info") or {}).get("liquidationPrice"), 0.0),
            ) or None

            parsed_positions.append(
                PositionSummary(
                    symbol=symbol,
                    side=side_raw,
                    size=abs(contracts),
                    entry_price=entry_price,
                    unrealized_pnl_usd=unrealized,
                    leverage=leverage,
                    mark_price=mark_price,
                    liquidation_price=liq_price,
                )
            )

        return EquitySnapshot(
            source=source,
            is_paper=settings.paper_trading,
            equity_usd=equity,
            available_balance_usd=available,
            margin_used_usd=margin_used,
            open_positions_count=len(parsed_positions),
            positions=parsed_positions,
            error=None,
        )

    def _parse_bybit_rest_snapshot(
        self,
        balance: dict[str, Any],
        positions: dict[str, Any],
    ) -> EquitySnapshot:
        account = (((balance.get("result") or {}).get("list") or [{}])[0]) or {}
        equity = self._safe_float(account.get("totalEquity"), 0.0)
        available = self._safe_float(account.get("totalAvailableBalance"), equity)
        margin_used = max(equity - available, 0.0)

        parsed_positions: list[PositionSummary] = []
        raw_positions = ((positions.get("result") or {}).get("list") or [])
        for pos in raw_positions:
            side_raw = str(pos.get("side") or "").strip()
            size = self._safe_float(pos.get("size"), 0.0)
            entry_price = self._safe_float(pos.get("avgPrice"), 0.0)
            if not side_raw or size <= 0 or entry_price <= 0:
                continue
            parsed_positions.append(
                PositionSummary(
                    symbol=self._normalize_symbol(str(pos.get("symbol") or "?")),
                    side="long" if side_raw.lower() == "buy" else "short",
                    size=size,
                    entry_price=entry_price,
                    unrealized_pnl_usd=self._safe_float(pos.get("unrealisedPnl"), 0.0),
                    leverage=self._safe_int(pos.get("leverage"), None),
                )
            )

        return EquitySnapshot(
            source=EquitySource.BYBIT,
            is_paper=settings.paper_trading,
            equity_usd=equity,
            available_balance_usd=available,
            margin_used_usd=margin_used,
            open_positions_count=len(parsed_positions),
            positions=parsed_positions,
            error=None,
        )

    def _extract_balance_totals(
        self,
        exchange_id: str,
        balance: dict[str, Any],
        mark_prices: Optional[dict[str, float]] = None,
    ) -> tuple[float, float]:
        info = balance.get("info", {}) or {}
        if exchange_id == "bybit":
            account = (((info.get("result") or {}).get("list") or [{}])[0]) or {}
            equity = self._safe_float(
                account.get("totalEquity"),
                self._safe_float((balance.get("total") or {}).get("USDT"), 0.0),
            )
            available = self._safe_float(
                account.get("totalAvailableBalance"),
                self._safe_float((balance.get("free") or {}).get("USDT"), equity),
            )
            return equity, available

        total_map = balance.get("total", {}) or {}
        free_map = balance.get("free", {}) or {}

        # P0-5 fix (2026-05-28 audit): Binance COIN-M (inverse) settles em
        # BTC/ETH, NÃO em USDT. Buscar só USDT/USDC retornava 0 → equity_usd=0
        # → Batman/IronMan achavam conta vazia → não colocava ordens.
        # Em inverse, somar saldos das trading_assets convertidos para USD
        # via mark_prices do feed (se disponível).
        binance_market_type = (
            str(getattr(settings, "binance_market_type", "linear"))
            if exchange_id == "binance" else "linear"
        )
        if binance_market_type == "inverse":
            equity_usd = 0.0
            available_usd = 0.0
            mark_prices = mark_prices or {}
            assets = list(getattr(settings, "trading_assets", []) or [])
            for coin in assets:
                coin_u = str(coin).upper().strip()
                total_coin = self._safe_float(total_map.get(coin_u), 0.0)
                free_coin = self._safe_float(free_map.get(coin_u), 0.0)
                mark = float(mark_prices.get(coin_u, 0.0) or 0.0)
                if mark > 0:
                    equity_usd += total_coin * mark
                    available_usd += free_coin * mark
                else:
                    # Sem cotação ao vivo: log mas não força equity=0
                    # (operador pode rodar com 1 ativo principal)
                    self._log.warning(
                        f"[PortfolioManager/COIN-M] no mark price for {coin_u}, "
                        f"{total_coin:.6f} {coin_u} excluded from equity_usd"
                    )
            if equity_usd <= 0:
                # Fallback final: tenta USDT mesmo em inverse (algumas contas
                # mistas têm USDT residual)
                equity_usd = self._safe_float(total_map.get("USDT"), 0.0)
                available_usd = self._safe_float(free_map.get("USDT"), equity_usd)
            return equity_usd, max(available_usd, 0.0)

        # Linear path (default)
        equity = self._safe_float(total_map.get("USDT"), 0.0)
        if equity <= 0:
            equity = self._safe_float(total_map.get("USDC"), 0.0)
        available = self._safe_float(free_map.get("USDT"), equity)
        if available <= 0 and equity > 0:
            available = self._safe_float(free_map.get("USDC"), equity)
        return equity, available

    @staticmethod
    def _normalize_symbol(raw_symbol: str) -> str:
        symbol = raw_symbol.upper()
        if "/" in symbol:
            return symbol.split("/", 1)[0]
        if symbol.endswith("USDT"):
            return symbol[:-4]
        if symbol.endswith("USDC"):
            return symbol[:-4]
        return symbol

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: Optional[int] = 0) -> Optional[int]:
        try:
            if value in (None, ""):
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _save_cached_snapshot(self, snapshot: EquitySnapshot) -> None:
        # Atomic write: portfolio cache lê de boot path, corrupção do
        # arquivo durante crash mid-write fazia o sistema cair em fallback
        # PAPER mesmo com dados válidos em memória.
        try:
            from src.services.atomic_json import atomic_write_json  # noqa: WPS433
            atomic_write_json(
                _SNAPSHOT_CACHE_FILE,
                json.loads(snapshot.model_dump_json()),
            )
        except Exception:  # noqa: BLE001
            pass

    def _load_cached_snapshot(self, reason: str) -> Optional[EquitySnapshot]:
        try:
            if not _SNAPSHOT_CACHE_FILE.exists():
                return None
            raw = json.loads(_SNAPSHOT_CACHE_FILE.read_text())
            snap = EquitySnapshot.model_validate(raw)
            if snap.source.value != settings.active_exchange.upper():
                return None
            snap.error = reason
            return snap
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _paper_fallback(self, reason: str) -> EquitySnapshot:
        """
        Synthetic snapshot used whenever a real reading is impossible.

        Equity = settings.paper_equity_usd.
        Open positions = 0 (Batman will only block on max_open_positions
        when there are real positions on the books).
        """
        snap = EquitySnapshot(
            source=EquitySource.PAPER_FALLBACK,
            is_paper=True,
            equity_usd=settings.paper_equity_usd,
            available_balance_usd=settings.paper_equity_usd,
            margin_used_usd=0.0,
            open_positions_count=0,
            positions=[],
            error=reason,
        )
        self._log.warning(snap.summary())
        return snap
