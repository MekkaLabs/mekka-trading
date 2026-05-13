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
        # --------------------------------------------------------------
        if settings.paper_trading:
            order_id = f"PAPER-{uuid.uuid4().hex[:12]}"
            sl_id = f"PAPER-SL-{uuid.uuid4().hex[:8]}"
            tp_id = f"PAPER-TP-{uuid.uuid4().hex[:8]}"
            # [B5] Apply synthetic slippage so paper metrics reflect real-world
            # fill costs. LONG fills at slightly higher price, SHORT at lower.
            slip_pct = settings.paper_slippage_bps / 10_000.0
            is_long = signal.action == TradeAction.LONG
            avg_price = round(entry * (1.0 + slip_pct if is_long else 1.0 - slip_pct), 6)
            paper_notional = round(quantity * avg_price, 2)
            result = ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.PAPER,
                is_paper=True,
                side=side,
                quantity=round(quantity, 8),
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
        """Lazy-init a CCXT async exchange instance for Bybit or Binance."""
        if self._ccxt_exchange is not None:
            return self._ccxt_exchange

        async with self._connect_lock:
            if self._ccxt_exchange is not None:
                return self._ccxt_exchange

            import ccxt.async_support as ccxt  # noqa: WPS433

            cfg: dict = {
                "enableRateLimit": True,
                "options": {"defaultType": "swap"},
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

            exchange = getattr(ccxt, exchange_id)(cfg)
            await exchange.load_markets()
            self._ccxt_exchange = exchange
            self._log.info(f"[IronMan] Connected to {exchange_id} via CCXT")
            return exchange

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
        symbol = signal.symbol
        is_buy = signal.action.value.upper() == "LONG"
        ccxt_symbol = f"{symbol}/USDT:USDT"
        ccxt_side = "buy" if is_buy else "sell"

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
        sl_id: Optional[str] = None
        tp_id: Optional[str] = None
        sl_side = "sell" if is_buy else "buy"

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
        except Exception as _exc:
            self._log.warning(f"[IronMan/{exchange_id}] SL placement failed: {_exc}")

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
