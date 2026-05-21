"""
src/agents/iron_man.py
======================
Iron Man — Hyperliquid Execution Engineer

The only agent allowed to place orders. Receives a `RiskApproval` (from
Batman) plus the original `TradingSignal` and the operator's current
equity, and emits an `ExecutionResult`.

Hard rules
----------
  • Iron Man NEVER places real orders when settings.paper_trading=True.
  • Iron Man NEVER bypasses Batman — if the approval is not executable
    it returns SKIPPED.
  • All real-order paths are wrapped in tenacity retry with exponential
    backoff to handle transient Hyperliquid timeouts.
  • Stop-loss and take-profit orders are placed alongside the entry as
    reduce-only triggers (TP/SL bracket).

Modes
-----
  paper_trading=True  → simulated fill at signal.entry_price (default)
  paper_trading=False → real order via hyperliquid-python-sdk

The hyperliquid-python-sdk import is lazy so the rest of the system can
import this module even when the SDK is not installed.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from typing import Any, Optional

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal
from src.services.market_registry import to_ccxt, to_mekka


# ---------------------------------------------------------------------------
# Process-wide CCXT exchange cache
# ---------------------------------------------------------------------------
# Building a CCXT exchange + load_markets costs 9-18s on Binance testnet.
# Doing it per IronMan() instance meant every dashboard "Executar Trade" click
# paid that cost from scratch (and leaked the aiohttp session). We cache the
# warmed exchange per (exchange_id, network) and reuse it across instances on
# the same event loop. Loop identity is recorded so a cached aiohttp session is
# never reused from a different loop (which would raise "attached to a
# different loop"). Across a process restart the module state resets, so the
# cache is naturally per-process.
_CCXT_SHARED: dict[str, Any] = {}
_CCXT_SHARED_LOOP: dict[str, Any] = {}
_CCXT_SHARED_LOCK: asyncio.Lock = asyncio.Lock()


async def aclose_ccxt_cache() -> None:
    """Close all cached CCXT exchanges (call on process shutdown)."""
    async with _CCXT_SHARED_LOCK:
        for key, exchange in list(_CCXT_SHARED.items()):
            try:
                await exchange.close()
            except Exception:  # noqa: BLE001
                pass
            _CCXT_SHARED.pop(key, None)
            _CCXT_SHARED_LOOP.pop(key, None)


class IronMan(BaseAgent[ExecutionResult]):
    """
    Multi-Exchange Execution Engineer.

    Supports Hyperliquid (native SDK), Bybit, and Binance (CCXT unified API).
    The active exchange is controlled by ``settings.active_exchange``.

    Usage:
        result = await IronMan().run(
            signal=trading_signal,
            approval=batman_approval,
            equity_usd=10_000.0,
        )
    """

    def __init__(self) -> None:
        super().__init__(
            codename="IronMan",
            role=f"Execution Engineer ({settings.active_exchange} / {settings.hyperliquid_network})",
        )
        self._exchange: Optional[Any] = None  # hyperliquid Exchange instance
        self._info: Optional[Any] = None      # hyperliquid Info instance
        self._ccxt_exchange: Optional[Any] = None  # CCXT exchange (Bybit/Binance)
        # [B3] Lock prevents double-init when two coroutines race into _connect_async
        self._connect_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # SDK lifecycle (lazy)
    # ------------------------------------------------------------------

    async def _connect_async(self) -> tuple[Any, Any]:
        """[B3] Async wrapper with Lock to prevent concurrent SDK double-init."""
        async with self._connect_lock:
            return self._connect()

    def _connect(self) -> tuple[Any, Any]:
        """
        Lazy-init Hyperliquid SDK. Raises ImportError or RuntimeError if
        the SDK is missing or credentials are not configured.

        Returns (exchange, info).
        """
        if self._exchange is not None and self._info is not None:
            return self._exchange, self._info

        try:
            from eth_account import Account  # noqa: WPS433
            from hyperliquid.exchange import Exchange  # noqa: WPS433
            from hyperliquid.info import Info  # noqa: WPS433
            from hyperliquid.utils import constants  # noqa: WPS433
        except ImportError as exc:
            raise ImportError(
                "hyperliquid-python-sdk and eth-account are required for live "
                "execution. Install them or keep paper_trading=True."
            ) from exc

        base_url = (
            constants.MAINNET_API_URL
            if settings.is_mainnet
            else constants.TESTNET_API_URL
        )

        # Normalize private key (strip 0x if present)
        pk = settings.hyperliquid_private_key
        if pk.startswith("0x"):
            pk = pk[2:]
        wallet = Account.from_key(bytes.fromhex(pk))

        self._info = Info(base_url, skip_ws=True)
        self._exchange = Exchange(
            wallet=wallet,
            base_url=base_url,
            account_address=settings.hyperliquid_wallet_address,
        )
        self._log.info(
            f"Iron Man connected to Hyperliquid {settings.hyperliquid_network}"
        )
        return self._exchange, self._info

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(  # type: ignore[override]
        self,
        signal: TradingSignal,
        approval: RiskApproval,
        equity_usd: float,
    ) -> ExecutionResult:
        symbol = signal.symbol

        # --------------------------------------------------------------
        # Pre-flight: only execute APPROVED or REDUCED
        # --------------------------------------------------------------
        if not approval.is_executable or signal.action == TradeAction.HOLD:
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.SKIPPED,
                is_paper=settings.paper_trading,
                error=f"Skipped: verdict={approval.verdict.value}, action={signal.action.value}",
            )

        # --------------------------------------------------------------
        # Compute final order parameters
        # --------------------------------------------------------------
        size_pct = approval.adjusted_size_pct
        leverage = approval.adjusted_leverage
        entry = signal.entry_price
        side = "long" if signal.action == TradeAction.LONG else "short"

        if entry <= 0 or size_pct <= 0:
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=settings.paper_trading,
                error="Invalid entry or size after adjustment",
            )

        notional = equity_usd * size_pct * leverage
        quantity = notional / entry

        # --------------------------------------------------------------
        # [036] Live-execution double-gate
        # If paper_trading=False but live_trading_confirmed=False the
        # settings validator already blocks startup — this is a defensive
        # belt-and-suspenders in case settings are mutated after init.
        # --------------------------------------------------------------
        if not settings.paper_trading and not settings.live_trading_confirmed:
            self._log.error(
                "[IronMan] BLOCKED: paper_trading=False but live_trading_confirmed=False. "
                "Set LIVE_TRADING_CONFIRMED=true after operator sign-off."
            )
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=False,
                side=side,
                error="Live execution blocked: LIVE_TRADING_CONFIRMED not set. "
                      "See docs/MAINNET-AUTHORIZATION.md.",
            )

        # --------------------------------------------------------------
        # Paper trading branch
        # Story 144 — Mock Realism: when enabled, simulate realistic friction:
        #   • Random network latency (50-500ms)
        #   • Partial fills (50-100% of requested quantity)
        #   • Extra randomized slippage (0-10 bps on top of paper_slippage_bps)
        # --------------------------------------------------------------
        if settings.paper_trading:
            order_id = f"PAPER-{uuid.uuid4().hex[:12]}"
            sl_id = f"PAPER-SL-{uuid.uuid4().hex[:8]}"
            tp_id = f"PAPER-TP-{uuid.uuid4().hex[:8]}"

            # [B5] Base synthetic slippage
            slip_pct = settings.paper_slippage_bps / 10_000.0
            is_long = signal.action == TradeAction.LONG
            filled_quantity = quantity  # default: full fill
            _realism_meta: dict = {}

            # Story 144 — Mock Realism friction
            if settings.mock_realism_enabled:
                # 1. Simulate exchange latency
                latency_ms = random.uniform(
                    settings.mock_realism_latency_min_ms,
                    settings.mock_realism_latency_max_ms,
                )
                await asyncio.sleep(latency_ms / 1000.0)

                # 2. Partial fill simulation
                fill_ratio = random.uniform(
                    settings.mock_realism_partial_fill_min_pct, 1.0
                )
                filled_quantity = quantity * fill_ratio

                # 3. Extra randomized slippage
                extra_bps = random.uniform(0.0, settings.mock_realism_extra_slippage_max_bps)
                slip_pct += extra_bps / 10_000.0

                _realism_meta = {
                    "mock_realism": True,
                    "simulated_latency_ms": round(latency_ms, 1),
                    "fill_ratio": round(fill_ratio, 4),
                    "extra_slippage_bps": round(extra_bps, 2),
                }
                self._log.debug(
                    f"[IronMan:MockRealism] {symbol} latency={latency_ms:.0f}ms "
                    f"fill={fill_ratio:.1%} extra_slip={extra_bps:.1f}bps"
                )

            avg_price = round(entry * (1.0 + slip_pct if is_long else 1.0 - slip_pct), 6)
            paper_notional = round(filled_quantity * avg_price, 2)
            _exec_status = (
                ExecutionStatus.PARTIAL
                if settings.mock_realism_enabled and filled_quantity < quantity * 0.999
                else ExecutionStatus.PAPER
            )

            result = ExecutionResult(
                symbol=symbol,
                status=_exec_status,
                is_paper=True,
                side=side,
                quantity=round(filled_quantity, 8),
                avg_price=avg_price,
                notional_usd=paper_notional,
                order_id=order_id,
                sl_order_id=sl_id,
                tp_order_id=tp_id,
                metadata={
                    "leverage": leverage,
                    "size_pct": size_pct,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "slippage_bps": settings.paper_slippage_bps,
                    **_realism_meta,
                },
            )
            self._log.info(result.summary())
            return result

        # --------------------------------------------------------------
        # Live execution branch — route to correct exchange adapter
        # --------------------------------------------------------------
        try:
            active = settings.active_exchange
            if active == "hyperliquid":
                result = await self._place_live_order(
                    signal=signal,
                    quantity=quantity,
                    leverage=leverage,
                    size_pct=size_pct,
                )
            else:
                # [Bybit/Binance] CCXT unified execution path
                result = await self._place_ccxt_order(
                    signal=signal,
                    quantity=quantity,
                    leverage=leverage,
                    size_pct=size_pct,
                    exchange_id=active,
                )
            self._log.info(result.summary())
            return result
        except RetryError as exc:
            self._log.error(f"[IronMan] Retries exhausted: {exc.last_attempt}")
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.ERROR,
                is_paper=False,
                side=side,
                error=f"Retries exhausted: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[IronMan] Live execution failed: {exc}")
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.ERROR,
                is_paper=False,
                side=side,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Live execution (with retry)
    # ------------------------------------------------------------------

    async def _place_live_order(
        self,
        signal: TradingSignal,
        quantity: float,
        leverage: int,
        size_pct: float,
    ) -> ExecutionResult:
        # [B3] Use async-safe connect to avoid double-init under concurrency
        exchange, info = await self._connect_async()
        symbol = signal.symbol
        is_buy = signal.action == TradeAction.LONG

        # [B4] Pre-flight margin check — reject early if account cannot cover
        # the required initial margin (notional / leverage) rather than burning
        # a retry attempt on a predictable rejection.
        try:
            state = await asyncio.to_thread(
                info.user_state, settings.hyperliquid_wallet_address
            )
            withdrawable_str = (
                state.get("withdrawable")
                or state.get("crossMarginSummary", {}).get("accountValue", "0")
            )
            withdrawable = float(withdrawable_str or 0)
            required_margin = (quantity * signal.entry_price) / max(leverage, 1)
            if withdrawable < required_margin:
                return ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.REJECTED,
                    is_paper=False,
                    side="long" if is_buy else "short",
                    error=(
                        f"Insufficient margin: need ~${required_margin:,.2f}, "
                        f"available ${withdrawable:,.2f}"
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            # Balance check failure is non-fatal — log and proceed.
            self._log.warning(f"[IronMan] balance check failed (proceeding): {exc}")

        entry_resp: Any = None
        sl_resp: Any = None
        tp_resp: Any = None

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.0, min=1, max=8),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            reraise=True,
        ):
            with attempt:
                # Set leverage on the asset (Hyperliquid SDK is sync — wrap)
                await asyncio.to_thread(
                    exchange.update_leverage, leverage, symbol, True  # cross
                )

                # Main entry order — IOC limit at entry_price
                entry_resp = await asyncio.to_thread(
                    exchange.order,
                    symbol,
                    is_buy,
                    quantity,
                    signal.entry_price,
                    {"limit": {"tif": "Ioc"}},  # immediate-or-cancel
                    False,  # not reduce-only
                )

                # [B1/B2] Extract filled quantity BEFORE placing SL/TP.
                # Use 0 as fallback (not quantity) so that a zero fill is
                # detected and SL/TP are NOT placed.
                filled_qty = self._extract_filled_size(entry_resp, fallback=0.0)

                if filled_qty <= 0:
                    # IOC order filled nothing — abort, no stops needed.
                    return ExecutionResult(
                        symbol=symbol,
                        status=ExecutionStatus.REJECTED,
                        is_paper=False,
                        side="long" if is_buy else "short",
                        error="IOC entry filled 0 units — SL/TP not placed",
                        metadata={"raw_entry_resp": entry_resp},
                    )

                # SL and TP use filled_qty (not planned quantity) so they
                # are correctly sized to the actual position.
                sl_resp = await asyncio.to_thread(
                    exchange.order,
                    symbol,
                    not is_buy,
                    filled_qty,
                    signal.stop_loss,
                    {"trigger": {"isMarket": True, "triggerPx": signal.stop_loss, "tpsl": "sl"}},
                    True,  # reduce-only
                )

                # Take-profit — reduce-only trigger (opposite side)
                tp_resp = await asyncio.to_thread(
                    exchange.order,
                    symbol,
                    not is_buy,
                    filled_qty,
                    signal.take_profit,
                    {"trigger": {"isMarket": True, "triggerPx": signal.take_profit, "tpsl": "tp"}},
                    True,  # reduce-only
                )

        # Parse responses (Hyperliquid SDK shapes)
        order_id = self._extract_oid(entry_resp)
        sl_id = self._extract_oid(sl_resp)
        tp_id = self._extract_oid(tp_resp)

        # Estimate avg fill — fallback to entry if not parseable
        avg_price = self._extract_avg_px(entry_resp, fallback=signal.entry_price)
        notional = filled_qty * avg_price
        status = (
            ExecutionStatus.FILLED
            if abs(filled_qty - quantity) / quantity < 0.05
            else ExecutionStatus.PARTIAL
        )

        return ExecutionResult(
            symbol=symbol,
            status=status,
            is_paper=False,
            side="long" if is_buy else "short",
            quantity=round(filled_qty, 8),
            avg_price=round(avg_price, 6),
            notional_usd=round(notional, 2),
            order_id=order_id,
            sl_order_id=sl_id,
            tp_order_id=tp_id,
            metadata={
                "leverage": leverage,
                "size_pct": size_pct,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "raw_entry_resp": entry_resp,
            },
        )

    # ------------------------------------------------------------------
    # CCXT unified execution (Bybit / Binance)
    # ------------------------------------------------------------------

    async def _get_ccxt_exchange(self, exchange_id: str) -> Any:
        """Lazy-init a CCXT async exchange, reusing a process-wide warmed
        instance when possible so we don't pay load_markets (9-18s) per call.
        """
        if self._ccxt_exchange is not None:
            return self._ccxt_exchange

        _testnet = (
            (exchange_id == "binance" and bool(getattr(settings, "binance_testnet", False)))
            or (exchange_id == "bybit" and bool(getattr(settings, "bybit_testnet", False)))
        )
        cache_key = f"{exchange_id}:{'testnet' if _testnet else 'mainnet'}"
        loop = asyncio.get_event_loop()

        async with _CCXT_SHARED_LOCK:
            # Reuse the shared warmed exchange if present and on the same loop.
            _cached = _CCXT_SHARED.get(cache_key)
            if _cached is not None and _CCXT_SHARED_LOOP.get(cache_key) is loop:
                self._ccxt_exchange = _cached
                return _cached

            import ccxt.async_support as ccxt  # noqa: WPS433

            cfg: dict = {
                "enableRateLimit": True,
                "timeout": 20_000,
                "options": {
                    "defaultType": "swap",
                    # 60s = Binance max recvWindow. Wide window prevents the
                    # InvalidNonce -1021 timestamp rejection from clock drift.
                    "recvWindow": 60_000,
                    "adjustForTimeDifference": True,
                },
            }
            if exchange_id == "bybit":
                if not settings.bybit_api_key:
                    raise RuntimeError(
                        "BYBIT_API_KEY not set. Add it to .env to use Bybit live execution."
                    )
                cfg["apiKey"] = settings.bybit_api_key
                cfg["secret"] = settings.bybit_api_secret
            elif exchange_id == "binance":
                if not settings.binance_api_key:
                    raise RuntimeError(
                        "BINANCE_API_KEY not set. Add it to .env to use Binance live execution."
                    )
                cfg["apiKey"] = settings.binance_api_key
                cfg["secret"] = settings.binance_api_secret
                cfg["options"].update(
                    {
                        "defaultSubType": "linear",
                        "fetchMarkets": {"types": ["linear"]},
                        "disableFuturesSandboxWarning": True,
                    }
                )

            exchange = getattr(ccxt, exchange_id)(cfg)

            # Route to testnet/sandbox BEFORE load_markets so the symbol list
            # comes from the right environment. Without this, Bybit testnet
            # keys would 401 against the mainnet endpoint (or — worse — live
            # keys would hit production). Default is True in settings so the
            # safe path is also the path of least surprise. The whole block
            # is wrapped in try/except (codex) so a failure during sandbox
            # routing or load_markets does not leak the underlying aiohttp
            # session — the half-initialised exchange is closed cleanly.
            try:
                try:
                    if exchange_id == "bybit" and settings.bybit_testnet:
                        exchange.set_sandbox_mode(True)
                        self._log.warning("[IronMan/bybit] SANDBOX (testnet) mode ENABLED")
                    elif exchange_id == "binance" and settings.binance_testnet:
                        exchange.set_sandbox_mode(True)
                        self._log.warning("[IronMan/binance] SANDBOX (testnet) mode ENABLED")
                except Exception as _sbx_exc:
                    # set_sandbox_mode is best-effort: log and continue. CCXT
                    # raises for exchanges that don't support it, but bybit
                    # and binance both do.
                    self._log.error(
                        f"[IronMan/{exchange_id}] set_sandbox_mode failed: {_sbx_exc}"
                    )

                for attempt in range(1, 4):
                    try:
                        await exchange.load_markets()
                        break
                    except Exception as exc:
                        if attempt >= 3:
                            raise
                        self._log.warning(
                            f"[IronMan/{exchange_id}] load_markets retry {attempt}/3 after error: {exc}"
                        )
                        await asyncio.sleep(float(attempt))
                self._ccxt_exchange = exchange
                _CCXT_SHARED[cache_key] = exchange
                _CCXT_SHARED_LOOP[cache_key] = loop
                self._log.info(f"[IronMan] Connected to {exchange_id} via CCXT (cached)")
                return exchange
            except Exception:
                await exchange.close()
                raise

    async def _check_clock_skew(
        self,
        exchange: Any,
        exchange_id: str,
        max_skew_ms: int = 5000,
    ) -> tuple[bool, int, str]:
        """Compare the system clock to the exchange server clock.

        Bybit V5 rejects orders whose recv_window-relative timestamp drifts
        more than ~5 seconds from server time (error code 10002). The
        symptom is opaque from CCXT's side ("invalid request") and the
        operator usually loses minutes debugging keys before noticing the
        machine clock is off. This check runs at most once per CCXT order
        and emits a clear human-readable rejection instead.

        Returns (ok, skew_ms, message). ``ok`` is True when the absolute
        skew is below ``max_skew_ms``. A network failure in fetch_time
        does NOT count as a fail — we degrade open (returning ok=True
        with skew_ms=0 and a "could not measure" message) because we
        would rather risk a 10002 from Bybit than block trading on a
        transient connectivity blip.
        """
        import time
        try:
            # fetch_time returns milliseconds since epoch on every CCXT
            # exchange that supports it (bybit, binance both do).
            server_ms = int(await exchange.fetch_time())
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                "[IronMan/%s] clock-skew probe failed (%s) — degrading open",
                exchange_id, exc,
            )
            return True, 0, f"could not measure ({type(exc).__name__})"

        local_ms = int(time.time() * 1000)
        skew_ms = local_ms - server_ms
        if abs(skew_ms) > max_skew_ms:
            return (
                False,
                skew_ms,
                (
                    f"local clock is {skew_ms:+d}ms vs {exchange_id} server "
                    f"(limit ±{max_skew_ms}ms). Bybit will reject orders with "
                    f"code 10002. Fix: run `sudo sntp -sS time.apple.com` (mac) "
                    f"or `sudo timedatectl set-ntp true` (linux)."
                ),
            )
        return True, skew_ms, "ok"

    async def _place_ccxt_order(
        self,
        signal: Any,
        quantity: float,
        leverage: int,
        size_pct: float,
        exchange_id: str,
    ) -> ExecutionResult:
        """Place a live order via CCXT unified API (Bybit / Binance perps).

        Uses the standard CCXT perp symbol format ``BTC/USDT:USDT`` and
        the create_order unified API. SL/TP are placed as separate reduce-only
        stop orders after the entry fills.
        """
        exchange = await self._get_ccxt_exchange(exchange_id)
        # Normalise the incoming symbol before composing the CCXT format.
        # signal.symbol *should* be bare (``BTC``), but defensive normalisation
        # via MarketRegistry means any legacy format (``BTC-USD``, ``BTCUSDT``)
        # still routes correctly.
        symbol = to_mekka(signal.symbol)
        is_buy = signal.action.value.upper() == "LONG"
        ccxt_symbol = to_ccxt(symbol, exchange_id)  # type: ignore[arg-type]
        ccxt_side = "buy" if is_buy else "sell"

        # ── Min-notional "lance livre" preflight ──────────────────────────
        # Venues enforce a minimum order size (amount.min) and minimum notional
        # (cost.min). A risk-sized order below that floor would be rejected by
        # the venue with a cryptic code. On a testnet we bump the quantity up to
        # the venue minimum so the operator can freely test execution ("lance
        # livre"). On mainnet/live we NEVER silently inflate position size — we
        # reject with an actionable message and let the operator size up.
        try:
            _market = exchange.market(ccxt_symbol)
            _limits = (_market or {}).get("limits", {}) or {}
            _min_amount = (_limits.get("amount", {}) or {}).get("min")
            _min_cost = (_limits.get("cost", {}) or {}).get("min")
            _req_notional = quantity * float(signal.entry_price)

            _needs_bump = False
            _floor_qty = quantity
            if _min_amount and quantity < float(_min_amount):
                _needs_bump = True
                _floor_qty = max(_floor_qty, float(_min_amount))
            if _min_cost and _req_notional < float(_min_cost):
                _needs_bump = True
                _floor_qty = max(_floor_qty, float(_min_cost) / float(signal.entry_price))

            if _needs_bump:
                _is_testnet = (
                    (exchange_id == "binance" and bool(getattr(settings, "binance_testnet", False)))
                    or (exchange_id == "bybit" and bool(getattr(settings, "bybit_testnet", False)))
                )
                if _is_testnet:
                    self._log.warning(
                        "[IronMan/%s] order below venue minimum "
                        "(qty=%.8f notional=$%.2f, min_amount=%s min_cost=%s) — "
                        "bumping to venue minimum for testnet (lance livre)",
                        exchange_id, quantity, _req_notional, _min_amount, _min_cost,
                    )
                    quantity = _floor_qty
                else:
                    return ExecutionResult(
                        symbol=symbol,
                        status=ExecutionStatus.REJECTED,
                        is_paper=False,
                        side="long" if is_buy else "short",
                        error=(
                            f"Ordem abaixo do mínimo da {exchange_id}: notional "
                            f"${_req_notional:,.2f} < mín ${float(_min_cost or 0):,.2f} "
                            f"(qty {quantity:.6f} < mín {float(_min_amount or 0):.6f}). "
                            f"Aumente o tamanho da posição (size_pct/leverage) para operar live."
                        ),
                    )

            # Round to venue step size so create_order isn't rejected on precision.
            try:
                quantity = float(exchange.amount_to_precision(ccxt_symbol, quantity))
            except Exception:  # noqa: BLE001
                pass
        except Exception as _lim_exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] min-notional preflight skipped: {_lim_exc}")

        # Clock-skew pre-flight — Bybit rejects ordered with code 10002 when
        # the local clock drifts more than ~5s from server time, and the
        # CCXT error surface for that case is unhelpful. Catch it here so
        # the operator gets an actionable message instead of a mystery
        # "invalid request".
        ok, skew_ms, msg = await self._check_clock_skew(exchange, exchange_id)
        if not ok:
            self._log.error(
                "[IronMan/%s] aborting order: clock skew %+dms (%s)",
                exchange_id, skew_ms, msg,
            )
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=False,
                side="long" if is_buy else "short",
                error=f"Clock skew {skew_ms:+d}ms: {msg}",
            )
        elif abs(skew_ms) > 1000:
            # Below the hard limit but worth surfacing — operators usually
            # want to fix NTP before drift grows further.
            self._log.warning(
                "[IronMan/%s] clock skew %+dms (within tolerance, but consider syncing NTP)",
                exchange_id, skew_ms,
            )

        # Set leverage
        try:
            await exchange.set_leverage(leverage, ccxt_symbol)
        except Exception as _exc:
            self._log.warning(f"[IronMan/{exchange_id}] set_leverage failed (proceeding): {_exc}")

        # Pre-flight margin check via CCXT balance
        try:
            bal = await exchange.fetch_balance()
            free_usdt = float(bal.get("USDT", {}).get("free", 0) or 0)
            required_margin = (quantity * signal.entry_price) / max(leverage, 1)
            if free_usdt < required_margin:
                return ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.REJECTED,
                    is_paper=False,
                    side="long" if is_buy else "short",
                    error=(
                        f"Insufficient USDT margin: need ~${required_margin:,.2f}, "
                        f"available ${free_usdt:,.2f}"
                    ),
                )
        except Exception as _exc:
            self._log.warning(f"[IronMan/{exchange_id}] balance check failed: {_exc}")

        # ── Entry order (limit IOC) ──
        order: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.0, min=1, max=8),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            reraise=True,
        ):
            with attempt:
                order = await exchange.create_order(
                    symbol=ccxt_symbol,
                    type="limit",
                    side=ccxt_side,
                    amount=quantity,
                    price=signal.entry_price,
                    params={"timeInForce": "IOC", "reduceOnly": False},
                )

        if order is None:
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=False,
                side="long" if is_buy else "short",
                error="CCXT order returned None",
            )

        filled = float(order.get("filled") or 0)
        avg_px = float(order.get("average") or signal.entry_price)
        order_id = str(order.get("id") or "")

        if filled <= 0:
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=False,
                side="long" if is_buy else "short",
                error="IOC order filled 0 units",
                metadata={"raw_order": order},
            )

        # ── SL / TP reduce-only ──
        # The stop-loss is SAFETY-CRITICAL: a filled position with no stop can
        # run unbounded to liquidation. We retry SL placement and, if it still
        # fails, FLATTEN the just-opened position immediately rather than hold
        # it unprotected. TP failure is non-critical (the SL still covers the
        # downside) so it only logs.
        sl_id: Optional[str] = None
        tp_id: Optional[str] = None
        sl_side = "sell" if is_buy else "buy"

        sl_error: Optional[Exception] = None
        for _sl_attempt in range(1, 4):
            try:
                sl_order = await exchange.create_order(
                    symbol=ccxt_symbol,
                    type="stop_market",
                    side=sl_side,
                    amount=filled,
                    params={
                        "stopPrice": signal.stop_loss,
                        "reduceOnly": True,
                    },
                )
                sl_id = str(sl_order.get("id") or "")
                sl_error = None
                break
            except Exception as _exc:  # noqa: BLE001
                sl_error = _exc
                self._log.warning(
                    f"[IronMan/{exchange_id}] SL placement attempt {_sl_attempt}/3 failed: {_exc}"
                )
                if _sl_attempt < 3:
                    await asyncio.sleep(float(_sl_attempt))

        if sl_id is None:
            # SAFETY FAIL-SAFE: we could not protect the position. Never hold a
            # naked position — flatten it now and report the failure loudly.
            self._log.error(
                f"[IronMan/{exchange_id}] SL placement FAILED after retries — "
                f"flattening unprotected {symbol} position ({filled} units)"
            )
            close_ok, close_err = await self._emergency_flatten(
                exchange, ccxt_symbol, is_buy, filled, exchange_id
            )
            try:
                from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                _msg = (
                    f"🚨 SL FALHOU em {symbol} — posição "
                    + ("FECHADA por segurança (sem stop = inaceitável)."
                       if close_ok else
                       "NÃO PÔDE SER FECHADA — INTERVENÇÃO MANUAL URGENTE.")
                )
                asyncio.create_task(_TA().alert(
                    event="SL_PLACEMENT_FAILED",
                    severity="CRITICAL",
                    agent="IronMan",
                    symbol=symbol,
                    message=_msg,
                ))
            except Exception:  # noqa: BLE001
                pass

            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.ERROR,
                is_paper=False,
                side="long" if is_buy else "short",
                quantity=round(filled, 8),
                avg_price=round(avg_px, 6),
                notional_usd=round(filled * avg_px, 2),
                order_id=order_id,
                error=(
                    f"SL não pôde ser colocado ({sl_error}). "
                    + ("Posição fechada por segurança."
                       if close_ok else
                       f"FALHA AO FECHAR posição desprotegida ({close_err}) — "
                       "INTERVENÇÃO MANUAL URGENTE.")
                ),
                metadata={
                    "exchange": exchange_id,
                    "sl_failed": True,
                    "flattened": close_ok,
                    "stop_loss": signal.stop_loss,
                    "raw_order": order,
                },
            )

        try:
            tp_order = await exchange.create_order(
                symbol=ccxt_symbol,
                type="take_profit_market",
                side=sl_side,
                amount=filled,
                params={
                    "stopPrice": signal.take_profit,
                    "reduceOnly": True,
                },
            )
            tp_id = str(tp_order.get("id") or "")
        except Exception as _exc:
            self._log.warning(f"[IronMan/{exchange_id}] TP placement failed: {_exc}")

        notional = filled * avg_px
        status = (
            ExecutionStatus.FILLED
            if abs(filled - quantity) / max(quantity, 1e-8) < 0.05
            else ExecutionStatus.PARTIAL
        )

        return ExecutionResult(
            symbol=symbol,
            status=status,
            is_paper=False,
            side="long" if is_buy else "short",
            quantity=round(filled, 8),
            avg_price=round(avg_px, 6),
            notional_usd=round(notional, 2),
            order_id=order_id,
            sl_order_id=sl_id,
            tp_order_id=tp_id,
            metadata={
                "exchange": exchange_id,
                "leverage": leverage,
                "size_pct": size_pct,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "raw_order": order,
            },
        )

    async def _emergency_flatten(
        self,
        exchange: Any,
        ccxt_symbol: str,
        is_buy: bool,
        amount: float,
        exchange_id: str,
    ) -> tuple[bool, Optional[str]]:
        """Close a just-opened position with a reduce-only MARKET order.

        Fail-safe used when the stop-loss could not be placed — we never hold
        an unprotected position. Retries a few times; returns ``(ok, error)``.
        A market order is intentional: we want OUT now, slippage is acceptable
        versus the unbounded risk of a naked position.
        """
        close_side = "sell" if is_buy else "buy"
        last_err: Optional[str] = None
        for _attempt in range(1, 4):
            try:
                await exchange.create_order(
                    symbol=ccxt_symbol,
                    type="market",
                    side=close_side,
                    amount=amount,
                    params={"reduceOnly": True},
                )
                self._log.warning(
                    f"[IronMan/{exchange_id}] emergency flatten OK ({amount} units)"
                )
                return True, None
            except Exception as _exc:  # noqa: BLE001
                last_err = str(_exc)
                self._log.error(
                    f"[IronMan/{exchange_id}] emergency flatten attempt {_attempt}/3 failed: {_exc}"
                )
                if _attempt < 3:
                    await asyncio.sleep(float(_attempt))
        return False, last_err or "flatten failed after 3 attempts"

    # ------------------------------------------------------------------
    # Live SL Guardian — ensure every open position keeps a live stop
    # ------------------------------------------------------------------

    # Last-resort emergency stop distance used ONLY when a position has no
    # known SL (no resting order, no DB metadata). Loud-alerted when used.
    _GUARDIAN_DEFAULT_SL_PCT = 0.02

    @staticmethod
    def _has_protective_stop(open_orders: list, is_long: bool) -> bool:
        """True if a reduce-only STOP order on the protective side exists.

        A long is protected by a SELL stop, a short by a BUY stop. Binance/
        Bybit expose the stop type as ``stop_market`` / ``STOP_MARKET`` and a
        ``reduceOnly`` flag (sometimes only under ``info``). Take-profit orders
        (``take_profit_market``) are intentionally excluded — they don't cap
        the loss.
        """
        want_side = "sell" if is_long else "buy"
        for o in open_orders or []:
            typ = str(o.get("type") or "").lower()
            info = o.get("info") or {}
            info_type = str(info.get("type") or "").lower()
            is_stop = ("stop" in typ or "stop" in info_type) and "take_profit" not in typ and "take_profit" not in info_type
            ro = o.get("reduceOnly")
            if ro is None:
                ro = info.get("reduceOnly") or info.get("reduce_only") or info.get("closePosition")
            reduce_only = ro in (True, "true", "True", "TRUE", 1, "1")
            oside = str(o.get("side") or "").lower()
            if is_stop and reduce_only and oside == want_side:
                return True
        return False

    @staticmethod
    async def _recent_sl_map() -> dict[tuple[str, str], float]:
        """``{(SYMBOL, SIDE): sl_price}`` from recent trades' execution
        metadata (newest wins). Fail-silent — returns ``{}`` on any error."""
        out: dict[tuple[str, str], float] = {}
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433
            trades = await MekkaRepository.list_recent_trades(limit=40)
        except Exception:  # noqa: BLE001
            return out
        for t in trades or []:
            try:
                sym = (getattr(t, "symbol", "") or "").upper()
                side = (getattr(t, "side", "") or "").upper()
                if not sym or side not in ("LONG", "SHORT") or (sym, side) in out:
                    continue
                meta = ((t.raw or {}).get("metadata") or {}) if getattr(t, "raw", None) else {}
                sl = float(meta.get("stop_loss") or 0)
                if sl > 0:
                    out[(sym, side)] = sl
            except Exception:  # noqa: BLE001
                continue
        return out

    async def ensure_stops_for_open_positions(self) -> dict[str, Any]:
        """Live SL guardian — guarantee every open position has a live
        reduce-only stop-loss on the venue. Re-places a missing stop from the
        last known SL (DB metadata) or, as a last resort, a conservative
        emergency stop, and alerts. Paper mode is a no-op; Hyperliquid is
        handled by its own bracket path and skipped here.

        Read-mostly: it only writes when a stop is actually missing. Returns a
        summary ``{checked, protected, replaced, errors}``.
        """
        summary: dict[str, Any] = {"checked": 0, "protected": 0, "replaced": [], "errors": []}
        if settings.paper_trading:
            return summary
        exchange_id = settings.active_exchange
        if exchange_id not in ("bybit", "binance"):
            return summary

        try:
            exchange = await self._get_ccxt_exchange(exchange_id)
            positions = await exchange.fetch_positions()
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"connect/positions: {exc}")
            self._log.warning(f"[IronMan/guardian] could not read positions: {exc}")
            return summary

        sl_map = await self._recent_sl_map()

        for p in positions or []:
            try:
                size = abs(float(p.get("contracts") or 0))
                if size <= 0:
                    continue
                summary["checked"] += 1
                ccxt_symbol = p.get("symbol") or ""
                mekka = to_mekka(ccxt_symbol)
                is_long = str(p.get("side") or "").lower() == "long"
                entry = float(p.get("entryPrice") or 0)

                try:
                    open_orders = await exchange.fetch_open_orders(ccxt_symbol)
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"{mekka} fetch_open_orders: {exc}")
                    continue

                if self._has_protective_stop(open_orders, is_long):
                    summary["protected"] += 1
                    continue

                # Missing stop → determine SL price (known SL, else emergency %).
                sl_price = sl_map.get((mekka.upper(), "LONG" if is_long else "SHORT"), 0.0)
                emergency = False
                if not sl_price or sl_price <= 0:
                    emergency = True
                    sl_price = (
                        entry * (1 - self._GUARDIAN_DEFAULT_SL_PCT) if is_long
                        else entry * (1 + self._GUARDIAN_DEFAULT_SL_PCT)
                    )

                sl_side = "sell" if is_long else "buy"
                try:
                    try:
                        sl_price = float(exchange.price_to_precision(ccxt_symbol, sl_price))
                    except Exception:  # noqa: BLE001
                        pass
                    await exchange.create_order(
                        symbol=ccxt_symbol,
                        type="stop_market",
                        side=sl_side,
                        amount=size,
                        params={"stopPrice": sl_price, "reduceOnly": True},
                    )
                    summary["replaced"].append(
                        {"symbol": mekka, "sl": sl_price, "emergency": emergency}
                    )
                    self._log.warning(
                        "[IronMan/guardian] re-placed missing SL for %s @ %.4f (emergency=%s)",
                        mekka, sl_price, emergency,
                    )
                    try:
                        from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                        asyncio.create_task(_TA().alert(
                            event="SL_GUARDIAN_REPLACED",
                            severity="CRITICAL" if emergency else "WARNING",
                            agent="IronMan",
                            symbol=mekka,
                            message=(
                                f"🛡️ SL ausente em {mekka} — recolocado @ {sl_price:.4f}"
                                + (" (EMERGÊNCIA: SL desconhecido, usei stop padrão de "
                                   f"{self._GUARDIAN_DEFAULT_SL_PCT*100:.0f}%)" if emergency else "")
                            ),
                        ))
                    except Exception:  # noqa: BLE001
                        pass
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"{mekka} replace SL: {exc}")
                    self._log.error(
                        f"[IronMan/guardian] FAILED to re-place SL for {mekka}: {exc}"
                    )
                    try:
                        from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                        asyncio.create_task(_TA().alert(
                            event="SL_GUARDIAN_FAILED",
                            severity="CRITICAL",
                            agent="IronMan",
                            symbol=mekka,
                            message=(
                                f"🚨 Posição {mekka} SEM STOP e falha ao recolocar: {exc} "
                                "— INTERVENÇÃO MANUAL URGENTE."
                            ),
                        ))
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"guardian loop: {exc}")
                continue

        return summary

    async def close_position(self, symbol: str, side: str) -> ExecutionResult:
        """Close an open LIVE position with a reduce-only MARKET order and
        cancel its resting SL/TP orders. ``side`` is the OPEN position's side
        ('LONG'/'SHORT'). Used by the dashboard 'Fechar' button for live
        (Bybit/Binance) positions. Hyperliquid is not handled here.
        """
        exchange_id = settings.active_exchange
        if exchange_id == "hyperliquid":
            return ExecutionResult(
                symbol=symbol, status=ExecutionStatus.ERROR, is_paper=False,
                error="Fechamento manual via dashboard suportado em Bybit/Binance.",
            )

        exchange = await self._get_ccxt_exchange(exchange_id)
        ccxt_symbol = to_ccxt(to_mekka(symbol), exchange_id)  # type: ignore[arg-type]

        # Confirm the live size on the venue (don't trust the caller).
        size = 0.0
        try:
            positions = await exchange.fetch_positions([ccxt_symbol])
            for p in positions or []:
                if to_mekka(p.get("symbol") or "") == to_mekka(symbol):
                    size = abs(float(p.get("contracts") or 0))
                    break
        except Exception as _exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] fetch size for close failed: {_exc}")

        if size <= 0:
            return ExecutionResult(
                symbol=symbol, status=ExecutionStatus.SKIPPED, is_paper=False,
                error=f"Nenhuma posição aberta em {symbol} na {exchange_id}.",
            )

        is_long = side.upper() == "LONG"
        close_side = "sell" if is_long else "buy"
        order = await exchange.create_order(
            symbol=ccxt_symbol,
            type="market",
            side=close_side,
            amount=size,
            params={"reduceOnly": True},
        )
        # Cancel resting SL/TP so they don't fire on a now-flat position.
        try:
            await exchange.cancel_all_orders(ccxt_symbol)
        except Exception as _exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] cancel_all_orders after close failed: {_exc}")

        avg = float(order.get("average") or 0) or 0.0
        self._log.warning(
            f"[IronMan/{exchange_id}] manual close {symbol} {side} qty={size} @ {avg}"
        )
        return ExecutionResult(
            symbol=symbol,
            status=ExecutionStatus.FILLED,
            is_paper=False,
            side="long" if is_long else "short",
            quantity=round(size, 8),
            avg_price=round(avg, 6),
            notional_usd=round(size * avg, 2),
            order_id=str(order.get("id") or ""),
            metadata={"action": "manual_close", "exchange": exchange_id},
        )

    # ------------------------------------------------------------------
    # Story 058 — SL/TP modification (TIGHTEN_STOP / TRAIL_STOP)
    # ------------------------------------------------------------------

    async def modify_sl_tp(
        self,
        symbol: str,
        side: str,          # 'long' or 'short'
        quantity: float,
        new_sl: float,
        new_tp: Optional[float] = None,
    ) -> dict:
        """Cancel the existing bracket orders and place new SL (and optionally TP).

        In paper mode this is a no-op at the exchange level — the caller must
        update the DB record so Cyclops picks up the new stop price.
        In live mode the method cancels all open reduce-only orders for the
        symbol and re-submits fresh bracket orders at the new prices.

        Returns a dict with at minimum ``{"status": ..., "symbol": ...}``.
        """
        if settings.paper_trading:
            return {"status": "paper_noop", "symbol": symbol, "new_sl": new_sl, "new_tp": new_tp}

        # Live-trading guard (mirrors _run)
        if not settings.live_trading_confirmed:
            self._log.error("[IronMan/modify_sl_tp] BLOCKED: live_trading_confirmed=False")
            return {"status": "blocked", "symbol": symbol, "error": "live_trading_confirmed=False"}

        try:
            active = settings.active_exchange
            if active == "hyperliquid":
                return await self._modify_sl_tp_hyperliquid(symbol, side, quantity, new_sl, new_tp)
            else:
                return await self._modify_sl_tp_ccxt(symbol, side, quantity, new_sl, new_tp, active)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[IronMan/modify_sl_tp] {symbol} failed: {exc}")
            return {"status": "error", "symbol": symbol, "error": str(exc)}

    async def _modify_sl_tp_hyperliquid(
        self,
        symbol: str,
        side: str,
        quantity: float,
        new_sl: float,
        new_tp: Optional[float],
    ) -> dict:
        """Hyperliquid: cancel open reduce-only orders for symbol, place new bracket."""
        exchange, info = await self._connect_async()
        is_buy = side.lower() == "long"

        # 1. Cancel existing bracket orders (all open reduce-only orders for symbol)
        try:
            open_orders = await asyncio.to_thread(
                info.open_orders, settings.hyperliquid_wallet_address
            )
            for order in open_orders:
                if order.get("coin") == symbol:
                    try:
                        await asyncio.to_thread(exchange.cancel, symbol, order["oid"])
                    except Exception as _ce:  # noqa: BLE001
                        self._log.debug(f"[IronMan/HL] cancel oid={order.get('oid')} failed: {_ce}")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/HL] open_orders query failed (proceeding): {exc}")

        # 2. Place new SL (reduce-only)
        sl_resp: Any = await asyncio.to_thread(
            exchange.order,
            symbol,
            not is_buy,     # opposite side closes the position
            quantity,
            new_sl,
            {"trigger": {"isMarket": True, "triggerPx": new_sl, "tpsl": "sl"}},
            True,           # reduce-only
        )
        sl_id = self._extract_oid(sl_resp)

        # 3. Place new TP (reduce-only) if provided
        tp_id: Optional[str] = None
        if new_tp is not None:
            tp_resp: Any = await asyncio.to_thread(
                exchange.order,
                symbol,
                not is_buy,
                quantity,
                new_tp,
                {"trigger": {"isMarket": True, "triggerPx": new_tp, "tpsl": "tp"}},
                True,
            )
            tp_id = self._extract_oid(tp_resp)

        self._log.info(
            f"[IronMan/HL] modify_sl_tp {symbol} SL→{new_sl} TP→{new_tp} "
            f"sl_oid={sl_id} tp_oid={tp_id}"
        )
        return {
            "status": "modified",
            "exchange": "hyperliquid",
            "symbol": symbol,
            "new_sl": new_sl,
            "new_tp": new_tp,
            "sl_order_id": sl_id,
            "tp_order_id": tp_id,
        }

    async def _modify_sl_tp_ccxt(
        self,
        symbol: str,
        side: str,
        quantity: float,
        new_sl: float,
        new_tp: Optional[float],
        exchange_id: str,
    ) -> dict:
        """CCXT (Bybit/Binance): cancel open reduce-only orders, place new bracket."""
        exchange = await self._get_ccxt_exchange(exchange_id)
        # Same defensive normalisation as the entry path — keeps the two
        # places in sync if the caller eventually passes a non-bare symbol.
        ccxt_symbol = to_ccxt(to_mekka(symbol), exchange_id)  # type: ignore[arg-type]
        is_buy = side.lower() == "long"
        sl_side = "sell" if is_buy else "buy"

        # 1. Cancel existing reduce-only (SL/TP) orders for this symbol
        try:
            open_orders = await exchange.fetch_open_orders(ccxt_symbol)
            for order in open_orders:
                if order.get("reduceOnly"):
                    try:
                        await exchange.cancel_order(order["id"], ccxt_symbol)
                    except Exception as _ce:  # noqa: BLE001
                        self._log.debug(
                            f"[IronMan/{exchange_id}] cancel order={order.get('id')} failed: {_ce}"
                        )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] fetch_open_orders failed (proceeding): {exc}")

        # 2. Place new SL
        sl_id: Optional[str] = None
        try:
            sl_order = await exchange.create_order(
                symbol=ccxt_symbol,
                type="stop_market",
                side=sl_side,
                amount=quantity,
                params={"stopPrice": new_sl, "reduceOnly": True},
            )
            sl_id = str(sl_order.get("id") or "")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] new SL placement failed: {exc}")

        # 3. Place new TP if provided
        tp_id: Optional[str] = None
        if new_tp is not None:
            try:
                tp_order = await exchange.create_order(
                    symbol=ccxt_symbol,
                    type="take_profit_market",
                    side=sl_side,
                    amount=quantity,
                    params={"stopPrice": new_tp, "reduceOnly": True},
                )
                tp_id = str(tp_order.get("id") or "")
            except Exception as exc:  # noqa: BLE001
                self._log.warning(f"[IronMan/{exchange_id}] new TP placement failed: {exc}")

        self._log.info(
            f"[IronMan/{exchange_id}] modify_sl_tp {symbol} SL→{new_sl} TP→{new_tp} "
            f"sl_id={sl_id} tp_id={tp_id}"
        )
        return {
            "status": "modified",
            "exchange": exchange_id,
            "symbol": symbol,
            "new_sl": new_sl,
            "new_tp": new_tp,
            "sl_order_id": sl_id,
            "tp_order_id": tp_id,
        }

    # ------------------------------------------------------------------
    # Response parsers (best-effort)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_oid(resp: Any) -> Optional[str]:
        try:
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            if not statuses:
                return None
            first = statuses[0]
            if "filled" in first:
                return str(first["filled"].get("oid", "")) or None
            if "resting" in first:
                return str(first["resting"].get("oid", "")) or None
            return None
        except (AttributeError, KeyError, TypeError):
            return None

    @staticmethod
    def _extract_avg_px(resp: Any, fallback: float) -> float:
        try:
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            for st in statuses:
                if "filled" in st:
                    return float(st["filled"].get("avgPx", fallback))
            return fallback
        except (AttributeError, KeyError, TypeError, ValueError):
            return fallback

    @staticmethod
    def _extract_filled_size(resp: Any, fallback: float) -> float:
        try:
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
            for st in statuses:
                if "filled" in st:
                    return float(st["filled"].get("totalSz", fallback))
            return fallback
        except (AttributeError, KeyError, TypeError, ValueError):
            return fallback
