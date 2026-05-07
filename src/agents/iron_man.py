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
    Hyperliquid Execution Engineer.

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
            role=f"Hyperliquid Execution Engineer ({settings.hyperliquid_network})",
        )
        self._exchange: Optional[Any] = None  # hyperliquid Exchange instance
        self._info: Optional[Any] = None      # hyperliquid Info instance

    # ------------------------------------------------------------------
    # SDK lifecycle (lazy)
    # ------------------------------------------------------------------

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
        # Paper trading branch
        # --------------------------------------------------------------
        if settings.paper_trading:
            order_id = f"PAPER-{uuid.uuid4().hex[:12]}"
            sl_id = f"PAPER-SL-{uuid.uuid4().hex[:8]}"
            tp_id = f"PAPER-TP-{uuid.uuid4().hex[:8]}"
            result = ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.PAPER,
                is_paper=True,
                side=side,
                quantity=round(quantity, 8),
                avg_price=entry,
                notional_usd=round(notional, 2),
                order_id=order_id,
                sl_order_id=sl_id,
                tp_order_id=tp_id,
                metadata={
                    "leverage": leverage,
                    "size_pct": size_pct,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                },
            )
            self._log.info(result.summary())
            return result

        # --------------------------------------------------------------
        # Live execution branch
        # --------------------------------------------------------------
        try:
            result = await self._place_live_order(
                signal=signal,
                quantity=quantity,
                leverage=leverage,
                size_pct=size_pct,
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
        exchange, _info = self._connect()
        symbol = signal.symbol
        is_buy = signal.action == TradeAction.LONG

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

                # Stop-loss — reduce-only trigger (opposite side)
                sl_resp = await asyncio.to_thread(
                    exchange.order,
                    symbol,
                    not is_buy,
                    quantity,
                    signal.stop_loss,
                    {"trigger": {"isMarket": True, "triggerPx": signal.stop_loss, "tpsl": "sl"}},
                    True,  # reduce-only
                )

                # Take-profit — reduce-only trigger (opposite side)
                tp_resp = await asyncio.to_thread(
                    exchange.order,
                    symbol,
                    not is_buy,
                    quantity,
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
        filled_qty = self._extract_filled_size(entry_resp, fallback=quantity)
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
