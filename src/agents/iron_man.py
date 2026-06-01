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
            # Force-Execute (modo deus) e ordens completas envolvem múltiplas
            # round-trips: market-order + SL + TP + reconciliação. Em
            # condições normais soma 5-10s; com latência variável da Binance
            # testnet (já vi spikes >18s em single call) o ideal é deixar
            # margem confortável acima do CCXT timeout interno (15s).
            # Pre-2026-05-28: timeout_s=20s competia com CCXT 20s → race
            # condition matava o agente antes do CCXT dar erro decente.
            timeout_s=45.0,
        )
        self._exchange: Optional[Any] = None  # hyperliquid Exchange instance
        self._info: Optional[Any] = None      # hyperliquid Info instance
        self._ccxt_exchange: Optional[Any] = None  # CCXT exchange (Bybit/Binance)
        # [B3] Lock prevents double-init when two coroutines race into _connect_async
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        # P1-3 (2026-05-28): swap guard — detecta troca de binance_market_type
        # entre boots; loga WARNING se há posições abertas detectadas.
        # Fail-silent: nunca bloqueia boot do agente.
        try:
            from src.services.market_type_swap_guard import log_boot_swap_warning
            log_boot_swap_warning()
        except Exception as _swap_exc:  # noqa: BLE001
            logger.debug(f"[IronMan] swap guard boot check no-op: {_swap_exc}")

    # ------------------------------------------------------------------
    # COIN-M helpers (2026-05-28 audit fix P0-3/P0-4)
    # ------------------------------------------------------------------

    @staticmethod
    def _binance_market_type_for(exchange_id: str) -> str:
        """Resolve market_type pro to_ccxt — só relevante para Binance.

        Outras exchanges sempre recebem 'linear' (default seguro).
        Hyperliquid usa USDC-margined que market_registry trata especialmente.
        """
        if exchange_id == "binance":
            return str(getattr(settings, "binance_market_type", "linear"))
        return "linear"

    @classmethod
    def _is_inverse_for(cls, exchange_id: str) -> bool:
        """True quando exchange está em COIN-M (inverse). Bybit pode ter
        ambos no futuro mas hoje só Binance suporta inverse."""
        return cls._binance_market_type_for(exchange_id) == "inverse"

    @classmethod
    def _balance_currency_for(cls, exchange_id: str, mekka_symbol: str) -> str:
        """Chave do balance dict pra checar margem disponível.

        - linear (USDT-M): sempre 'USDT' (todos pares cotados em USDT)
        - inverse (COIN-M): coin do par (BTC, ETH) — Binance separa balance
          por moeda settlement
        - bybit: USDT (sem suporte inverse ainda)
        - hyperliquid: USDC (USDC-margined)
        """
        if exchange_id == "hyperliquid":
            return "USDC"
        if cls._is_inverse_for(exchange_id):
            return mekka_symbol.upper().strip()  # 'BTC', 'ETH'
        return "USDT"

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
                # [Bybit/Binance] CCXT unified execution path.
                # ``force_execute`` (Modo Deus) flows in via approval.metadata
                # — IronMan honors it by forcing a market order in testnet
                # so the IOC limit doesn't silently fill 0 (book is thin).
                _force_execute = bool((approval.metadata or {}).get("force_execute", False))
                # C1 fix (2026-06-01 audit): cycle_id precisa existir no escopo de
                # _place_ccxt_order — sem isso o emergency_flatten lançava NameError
                # justamente quando o SL falhava (posição ficava NUA). Propagado do
                # approval.metadata quando disponível (NickFury injeta o cycle id).
                _cycle_id = (approval.metadata or {}).get("cycle_id") or (
                    getattr(signal, "snapshot_id", None)
                )
                result = await self._place_ccxt_order(
                    signal=signal,
                    quantity=quantity,
                    leverage=leverage,
                    size_pct=size_pct,
                    exchange_id=active,
                    force_market_in_testnet=_force_execute,
                    cycle_id=_cycle_id,
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
        # COIN-M support (2026-05-28): cache key inclui market_type para
        # invalidar quando operador troca de USDT-M (linear) ↔ COIN-M (inverse).
        # Sem isso, swap não pegaria o novo CCXT client.
        _mt = ""
        # P1-2 fix (2026-05-28 audit): snapshot atômico de binance_market_type
        # numa variável local — settings poderia mudar entre a leitura do
        # cache_key (linha abaixo) e a leitura no cfg["options"] (linha 605).
        # Sem isto, sob hot-swap simultâneo, cliente retornado tinha cache_key
        # de um market_type mas cfg do outro.
        _binance_mt_snapshot = (
            str(getattr(settings, "binance_market_type", "linear"))
            if exchange_id == "binance" else "linear"
        )
        if exchange_id == "binance":
            _mt = f":mt={_binance_mt_snapshot}"
        cache_key = f"{exchange_id}:{'testnet' if _testnet else 'mainnet'}{_mt}"
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
                # 15s por request CCXT — abaixo do timeout_s=45s do agente.
                # Se um único request travar >15s, CCXT dá NetworkError
                # específico ANTES do BaseAgent matar com TimeoutError
                # genérico. Melhor diagnóstico + retry logic do CCXT funciona.
                "timeout": 15_000,
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
                # COIN-M Futures support (2026-05-28) — usa snapshot atômico
                # tomado no início do método (P1-2 fix). NUNCA re-ler settings
                # aqui: o cache_key foi gerado com _binance_mt_snapshot e o
                # cfg precisa usar O MESMO valor pra evitar client com config
                # inconsistente com sua chave de cache.
                _binance_mt = _binance_mt_snapshot
                self._log.info(
                    f"[IronMan/{exchange_id}] CCXT init: defaultSubType={_binance_mt} "
                    f"(testnet={_testnet}, cache_key={cache_key})"
                )
                cfg["options"].update(
                    {
                        "defaultSubType": _binance_mt,  # "linear" (USDT-M) ou "inverse" (COIN-M)
                        "fetchMarkets": {"types": [_binance_mt]},
                        "disableFuturesSandboxWarning": True,
                    }
                )
                # cache_key já inclui :mt=... acima — não duplicar aqui

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
        force_market_in_testnet: bool = False,
        cycle_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Place a live order via CCXT unified API (Bybit / Binance perps).

        Uses the standard CCXT perp symbol format ``BTC/USDT:USDT`` and
        the create_order unified API. SL/TP are placed as separate reduce-only
        stop orders after the entry fills.

        Args:
            force_market_in_testnet: when True AND running in testnet, use a
                market order regardless of ``binance_entry_order_type``. This
                is the Modo Deus path — testnet books are too thin for a
                limit-IOC to fill reliably (observed 2026-05-26: IOC filled
                0 units, Modo Deus appeared broken to the operator).
                Ignored in mainnet — slippage protection still applies there.
        """
        exchange = await self._get_ccxt_exchange(exchange_id)
        # Normalise the incoming symbol before composing the CCXT format.
        # signal.symbol *should* be bare (``BTC``), but defensive normalisation
        # via MarketRegistry means any legacy format (``BTC-USD``, ``BTCUSDT``)
        # still routes correctly.
        symbol = to_mekka(signal.symbol)
        is_buy = signal.action.value.upper() == "LONG"
        # P0-3 fix (2026-05-28 audit): em modo Binance COIN-M (inverse), o
        # to_ccxt precisa retornar "BTC/USD:BTC" em vez de "BTC/USDT:USDT".
        # Sem isso, CCXT rejeitava com "Unknown symbol" silenciosamente.
        _market_type = self._binance_market_type_for(exchange_id)
        ccxt_symbol = to_ccxt(symbol, exchange_id, market_type=_market_type)  # type: ignore[arg-type]
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

        # Pre-flight margin check via CCXT balance.
        # P0-4 fix (2026-05-28 audit): em COIN-M (inverse), saldo está em
        # BTC/ETH (settlement coin), NÃO em USDT. Hardcoded "USDT" antes
        # retornava 0 → todas ordens rejeitadas como "insufficient margin".
        # Helper resolve a chave certa baseada em market_type + symbol.
        # H2 fix (2026-06-01 audit): fail-CLOSED em live. Antes, qualquer exceção
        # no fetch_balance (ex.: InvalidNonce -1021 conhecido) só logava warning e
        # a ordem seguia SEM verificar saldo — com dinheiro real isso pode liquidar
        # prematuro / rejeitar em loop. Agora: 2 tentativas com backoff; se ainda
        # falhar e estivermos em LIVE, a ordem é REJEITADA (testnet segue tolerante
        # para não travar os testes do operador).
        _bal: Any = None
        _bal_exc: Optional[Exception] = None
        for _bal_attempt in range(1, 3):
            try:
                _bal = await exchange.fetch_balance()
                _bal_exc = None
                break
            except Exception as _exc:  # noqa: BLE001
                _bal_exc = _exc
                self._log.warning(
                    f"[IronMan/{exchange_id}] balance check attempt {_bal_attempt}/2 failed: {_exc}"
                )
                if _bal_attempt < 2:
                    await asyncio.sleep(float(_bal_attempt))

        if _bal_exc is not None or _bal is None:
            if not settings.paper_trading:
                # LIVE: nunca enviar ordem sem confirmar margem.
                try:
                    from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                    asyncio.create_task(_TA().alert(
                        event="MARGIN_CHECK_FAILED",
                        severity="CRITICAL",
                        agent="IronMan",
                        symbol=symbol,
                        message=(
                            f"⛔ Checagem de margem falhou em {symbol} "
                            f"({_bal_exc}) — ordem REJEITADA (fail-closed)."
                        ),
                    ))
                except Exception:  # noqa: BLE001
                    pass
                return ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.REJECTED,
                    is_paper=False,
                    side="long" if is_buy else "short",
                    error=(
                        f"Margin check failed in live ({_bal_exc}) — "
                        "fail-closed, order rejected."
                    ),
                )
            self._log.warning(
                f"[IronMan/{exchange_id}] balance check failed in testnet — proceeding (tolerant)"
            )
        else:
            balance_currency = self._balance_currency_for(exchange_id, symbol)
            free_balance = float(_bal.get(balance_currency, {}).get("free", 0) or 0)
            if self._is_inverse_for(exchange_id):
                # Em inverse: margem requerida em coin (notional_usd / mark_price / leverage)
                mark = signal.entry_price
                if mark and mark > 0:
                    required_margin = (quantity * 100 / mark) / max(leverage, 1)  # 100 = contract size
                else:
                    required_margin = 0  # fallback: skip se sem preço
            else:
                required_margin = (quantity * signal.entry_price) / max(leverage, 1)
            if free_balance < required_margin:
                return ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.REJECTED,
                    is_paper=False,
                    side="long" if is_buy else "short",
                    error=(
                        f"Insufficient {balance_currency} margin: need ~{required_margin:.6f}, "
                        f"available {free_balance:.6f}"
                    ),
                )

        # ── Entry order ──
        # Order type is configurable. 'auto' → market on testnet (reliable fills
        # so the operator can exercise the full pipeline), limit-IOC on mainnet
        # (slippage control). A limit-IOC that doesn't cross the book fills 0,
        # which was the common "trade didn't work" on testnet.
        _is_testnet = (
            (exchange_id == "binance" and bool(getattr(settings, "binance_testnet", False)))
            or (exchange_id == "bybit" and bool(getattr(settings, "bybit_testnet", False)))
        )
        _etype = str(getattr(settings, "binance_entry_order_type", "auto") or "auto").lower()
        if _etype == "auto":
            # In mainnet dry-run mode, behave like mainnet even on testnet so
            # the operator can rehearse the marketable-limit path with real
            # ticks (no surprise behavior change at go-live).
            _dry_run = bool(getattr(settings, "mainnet_dry_run", False))
            _etype = "market" if (_is_testnet and not _dry_run) else "limit_ioc"
        # Modo Deus override (force_execute): testnet IOC is unreliable (book
        # thin, 0 fills). Force a market order so the operator's "execute
        # anyway" intent actually executes. Mainnet untouched — slippage cap
        # still active there.
        if force_market_in_testnet and _is_testnet and _etype != "market":
            self._log.warning(
                f"[IronMan/{exchange_id}] Modo Deus + testnet → overriding "
                f"{_etype} → market to avoid IOC zero-fill (book is thin)"
            )
            _etype = "market"
        use_market = _etype == "market"
        self._log.info(f"[IronMan/{exchange_id}] entry order type={_etype} (testnet={_is_testnet})")

        # Marketable limit price: a plain limit-IOC at signal.entry_price often
        # fills 0 if it doesn't cross the book. Price it to CROSS by up to
        # binance_max_entry_slippage_bps so it fills reliably with a slippage cap.
        limit_price = float(signal.entry_price)
        if not use_market:
            try:
                _bps = float(getattr(settings, "binance_max_entry_slippage_bps", 20.0) or 0.0)
                ticker = await exchange.fetch_ticker(ccxt_symbol)
                ask = float(ticker.get("ask") or 0.0)
                bid = float(ticker.get("bid") or 0.0)
                if is_buy and ask > 0:
                    limit_price = ask * (1.0 + _bps / 10_000.0)
                elif (not is_buy) and bid > 0:
                    limit_price = bid * (1.0 - _bps / 10_000.0)
                try:
                    limit_price = float(exchange.price_to_precision(ccxt_symbol, limit_price))
                except Exception:  # noqa: BLE001
                    pass
                self._log.info(
                    f"[IronMan/{exchange_id}] marketable limit price {limit_price} "
                    f"(entry {signal.entry_price}, cap {_bps:.0f}bps)"
                )
            except Exception as _tk_exc:  # noqa: BLE001
                self._log.warning(f"[IronMan/{exchange_id}] ticker for marketable price failed: {_tk_exc}")
                limit_price = float(signal.entry_price)

        order: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.0, min=1, max=8),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
            reraise=True,
        ):
            with attempt:
                if use_market:
                    order = await exchange.create_order(
                        symbol=ccxt_symbol,
                        type="market",
                        side=ccxt_side,
                        amount=quantity,
                        params={"reduceOnly": False},
                    )
                else:
                    order = await exchange.create_order(
                        symbol=ccxt_symbol,
                        type="limit",
                        side=ccxt_side,
                        amount=quantity,
                        price=limit_price,
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

        # Slippage telemetry: how much the fill drifted from signal.entry_price.
        # Validates the marketable-limit cap (M2) in production. Alert when the
        # actual slippage exceeds 2× the configured cap — that means either the
        # book moved between ticker and order, or the cap isn't holding.
        try:
            _slip_bps = 0.0
            if filled > 0 and signal.entry_price > 0:
                raw_bps = (avg_px - signal.entry_price) / signal.entry_price * 10_000.0
                # Adverse direction depends on side: a LONG paying more is bad;
                # a SHORT receiving less (avg < entry) is bad. Sign so positive
                # bps == adverse slippage.
                _slip_bps = raw_bps if is_buy else -raw_bps
            _cap_bps = float(getattr(settings, "binance_max_entry_slippage_bps", 20.0) or 0.0)
            from src.persistence.repository import MekkaRepository as _Repo  # noqa: WPS433
            _adverse = _slip_bps > 0 and _cap_bps > 0 and _slip_bps > _cap_bps * 2.0
            asyncio.create_task(_Repo.log_event(
                agent="IronMan",
                event="SLIPPAGE",
                severity="WARNING" if _adverse else "INFO",
                message=(
                    f"slippage {_slip_bps:+.1f}bps em {symbol} {('buy' if is_buy else 'sell')} "
                    f"(entry {signal.entry_price} → fill {avg_px}, cap {_cap_bps:.0f}bps)"
                ),
                payload={
                    "symbol": symbol, "side": "long" if is_buy else "short",
                    "entry_price": signal.entry_price, "avg_fill": avg_px,
                    "slippage_bps": round(_slip_bps, 2), "cap_bps": _cap_bps,
                    "adverse_over_2x_cap": _adverse, "order_type": _etype,
                },
            ))
        except Exception:  # noqa: BLE001
            _slip_bps = 0.0  # telemetry must never break execution

        if filled <= 0:
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.REJECTED,
                is_paper=False,
                side="long" if is_buy else "short",
                error=f"{_etype} order filled 0 units",
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

        # C2 fix (2026-06-01 audit): quantizar stopPrice de SL/TP ao tickSize da
        # corretora ANTES de enviar. Vision gera SL/TP como floats arbitrários
        # (ex: entry*0.97); sem price_to_precision a Binance rejeita por
        # PRICE_FILTER (-1111/-4014) — e essa rejeição é justamente o gatilho que
        # leva ao fail-safe. Espelha o padrão já usado no SL Guardian.
        # M2: quantizar também a quantidade (reduceOnly precisa casar o LOT_SIZE
        # do fill; partial fill com `filled` bruto pode rejeitar por LOT_SIZE).
        _sl_px: float = float(signal.stop_loss)
        _tp_px: float = float(signal.take_profit)
        _qty: float = float(filled)
        try:
            _sl_px = float(exchange.price_to_precision(ccxt_symbol, signal.stop_loss))
        except Exception:  # noqa: BLE001
            pass
        try:
            _tp_px = float(exchange.price_to_precision(ccxt_symbol, signal.take_profit))
        except Exception:  # noqa: BLE001
            pass
        try:
            _qty = float(exchange.amount_to_precision(ccxt_symbol, filled))
        except Exception:  # noqa: BLE001
            pass

        sl_error: Optional[Exception] = None
        for _sl_attempt in range(1, 4):
            try:
                sl_order = await exchange.create_order(
                    symbol=ccxt_symbol,
                    type="stop_market",
                    side=sl_side,
                    amount=_qty,
                    params={
                        "stopPrice": _sl_px,
                        "reduceOnly": True,
                    },
                )
                sl_id = str(sl_order.get("id") or "")
                sl_error = None
                break
            except Exception as _exc:  # noqa: BLE001
                sl_error = _exc
                _err_str = str(_exc)
                # Binance -4045 ("Reach max stop order limit") — quota cheia
                # por órfãos acumulados. Limpar e retry imediato no próximo
                # loop, sem esperar o sleep escalonado (a falha foi de quota,
                # não de rede). Mesmo padrão usado no guardian loop abaixo.
                if "-4045" in _err_str or "max stop order" in _err_str.lower():
                    try:
                        # Binance Futures: limite -4045 é GLOBAL POR CONTA,
                        # não por símbolo. Passamos ccxt_symbol=None para
                        # varrer todos os pares (helper preserva stops de
                        # posições ativas em outros símbolos).
                        _cleaned = await self._cleanup_orphan_reduce_only_stops(
                            exchange, ccxt_symbol=None
                        )

                        # ESCALATION: se cleanup convencional cancelou 0
                        # (fantasmas que fetch_open_orders não enxerga —
                        # bug recorrente da Testnet), escalar para
                        # mass-cancel via cancel_all_orders por símbolo.
                        # Só roda na 2ª/3ª tentativa para não ser agressivo
                        # demais no caso comum.
                        _mass = 0
                        if _cleaned == 0 and _sl_attempt >= 2:
                            _mass = await self._mass_cancel_orphan_symbols(
                                exchange, ccxt_symbol_in_use=ccxt_symbol
                            )

                        self._log.warning(
                            f"[IronMan/{exchange_id}] SL placement attempt "
                            f"{_sl_attempt}/3 hit -4045; cleaned {_cleaned} "
                            f"orphan stops + mass-cancelled {_mass} via "
                            "symbol-scoped cancel_all_orders, retrying immediately"
                        )
                        # Imediato — sem sleep — quota acabou de ser liberada.
                        continue
                    except Exception as _cleanup_exc:  # noqa: BLE001
                        self._log.warning(
                            f"[IronMan/{exchange_id}] orphan cleanup failed: "
                            f"{_cleanup_exc}"
                        )
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
                exchange, ccxt_symbol, is_buy, _qty, exchange_id,
                mekka_symbol=symbol, cycle_id=cycle_id,
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
                amount=_qty,
                params={
                    "stopPrice": _tp_px,
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
        *,
        mekka_symbol: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """Close a just-opened position with a reduce-only MARKET order.

        Fail-safe used when the stop-loss could not be placed — we never hold
        an unprotected position. Retries a few times; returns ``(ok, error)``.
        A market order is intentional: we want OUT now, slippage is acceptable
        versus the unbounded risk of a naked position.

        IMPORTANT: this path was NOT instrumented for memory resolution until
        2026-05-27. Without `resolve_trade_memories` here, every -4045-induced
        flatten left AgentMemory rows PENDING, biasing Beast/Mentor learning
        toward the rare Cyclops happy-path. We now call the resolver with
        pnl_usd=0.0 (immediate flatten = no realized P&L; the trade was
        cancelled before holding period).
        """
        close_side = "sell" if is_buy else "buy"
        last_err: Optional[str] = None
        ok = False
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
                ok = True
                break
            except Exception as _exc:  # noqa: BLE001
                last_err = str(_exc)
                self._log.error(
                    f"[IronMan/{exchange_id}] emergency flatten attempt {_attempt}/3 failed: {_exc}"
                )
                if _attempt < 3:
                    await asyncio.sleep(float(_attempt))

        # Resolver memórias (fail-silent — não afeta o retorno do flatten).
        if mekka_symbol:
            try:
                from src.services.trade_outcome_resolver import resolve_trade_memories
                await resolve_trade_memories(
                    symbol=mekka_symbol,
                    pnl_usd=0.0,
                    holding_hours=0.0,
                    cycle_id=cycle_id,
                )
            except Exception as _rtm_exc:  # noqa: BLE001
                self._log.debug(
                    f"[IronMan/_emergency_flatten] resolve_trade_memories no-op: {_rtm_exc}"
                )

        if ok:
            return True, None
        return False, last_err or "flatten failed after 3 attempts"

    # ------------------------------------------------------------------
    # Helper: free Binance per-symbol stop-order quota by cancelling
    # reduce-only orphan stops/TPs. Reusable from placement + guardian.
    # ------------------------------------------------------------------

    # Símbolos comuns para mass-cancel preventivo (último recurso contra
    # fantasmas do testnet). Mantém lista curta para não esgotar rate limit.
    _MASS_CANCEL_SYMBOLS = (
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
        "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT",
    )

    async def _mass_cancel_orphan_symbols(
        self, exchange: Any, ccxt_symbol_in_use: str,
    ) -> int:
        """
        Último recurso contra `-4045` na Binance Testnet: chama
        `cancel_all_orders(symbol)` em símbolos comuns SEM posição ativa,
        pegando stops "fantasma" que `fetch_open_orders` não enxerga.

        NÃO toca no símbolo da posição que está sendo aberta agora
        (ccxt_symbol_in_use) — preserva eventuais stops já colocados nesse
        ciclo.

        Conservador: pula símbolos com posição ativa (preserva SL legítimo
        que esteja invisível ao fetch). Fail-tolerante.
        """
        # Descobrir símbolos com posição (para preservá-los)
        active: set[str] = set()
        try:
            positions = await exchange.fetch_positions()
            for p in positions or []:
                try:
                    if abs(float(p.get("contracts") or 0)) > 0:
                        sym = str(p.get("symbol") or "")
                        if sym:
                            active.add(sym)
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                f"[IronMan/mass-cancel] fetch_positions failed: {exc} — "
                "aborting (conservador)"
            )
            return 0

        cancelled = 0
        for sym in self._MASS_CANCEL_SYMBOLS:
            # Preserva: símbolo da posição atual + símbolos com qualquer posição
            if sym == ccxt_symbol_in_use or sym in active:
                continue
            try:
                result = await exchange.cancel_all_orders(sym)
                n = len(result) if isinstance(result, list) else 1
                cancelled += n
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                # -2011 / "Unknown order" = nada para cancelar nesse símbolo (OK)
                if "-2011" in msg or "unknown order" in msg.lower():
                    continue
                self._log.debug(
                    f"[IronMan/mass-cancel] {sym} cancel_all_orders error: {exc}"
                )
        return cancelled

    async def _cleanup_orphan_reduce_only_stops(
        self, exchange: Any, ccxt_symbol: Optional[str] = None
    ) -> int:
        """
        Cancela reduce-only stop/take_profit orders ÓRFÃOS (em símbolos sem
        posição aberta). Retorna quantos foram cancelados.

        Usado para liberar a quota Binance ("max stop order limit" -4045),
        que é **global por conta** em Binance Futures (não por símbolo).
        Por isso varremos TODOS os símbolos por padrão, não só o que está
        tentando colocar SL.

        Parâmetros
        ----------
        exchange : CCXT exchange instance
        ccxt_symbol : str, opcional
            Quando dado, restringe a busca a esse símbolo (modo legacy
            usado pelo guardian). Quando None, varre toda a conta.

        Conservador: só cancela ordens marcadas reduce-only E em símbolos
        SEM posição aberta. Jamais toca em entradas, jamais remove o stop
        de uma posição ativa.

        Fail-tolerant: se uma cancel falhar, segue para a próxima.
        """
        # 1) descobrir símbolos com posição aberta (para preservar seus stops)
        active_symbols: set[str] = set()
        try:
            positions = await exchange.fetch_positions()
            for p in positions or []:
                try:
                    contracts = float(p.get("contracts") or 0)
                    if abs(contracts) > 0:
                        sym = str(p.get("symbol") or "")
                        if sym:
                            active_symbols.add(sym)
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            # Se não conseguir buscar posições, sermos CONSERVADORES:
            # só limpamos o símbolo passado (legacy) ou nada se for None.
            self._log.warning(
                f"[IronMan/cleanup] fetch_positions failed: {exc}; "
                "falling back to per-symbol-only mode"
            )
            if ccxt_symbol is None:
                return 0
            active_symbols = set()  # tudo no símbolo é candidato a cancelar

        # 2) buscar ordens abertas (global se ccxt_symbol=None)
        # NOTE: CCXT emite warning como exceção em fetch_open_orders() sem
        # símbolo na Binance. Reconhecemos a opção antes de chamar.
        try:
            opts = getattr(exchange, "options", None)
            if isinstance(opts, dict):
                opts["warnOnFetchOpenOrdersWithoutSymbol"] = False
        except Exception:  # noqa: BLE001
            pass

        try:
            if ccxt_symbol is None:
                open_orders = await exchange.fetch_open_orders()
            else:
                open_orders = await exchange.fetch_open_orders(ccxt_symbol)
        except Exception as exc:  # noqa: BLE001
            # Se a chamada global falhar (mesmo após ack), tentamos por
            # símbolos conhecidos a partir das posições ativas — pelo
            # menos liberamos algum stop órfão.
            self._log.warning(
                f"[IronMan/cleanup] fetch_open_orders global failed: {exc}; "
                "falling back to per-active-symbol cleanup"
            )
            open_orders = []
            seed_symbols = list(active_symbols) if ccxt_symbol is None else [ccxt_symbol]
            for s in seed_symbols:
                try:
                    chunk = await exchange.fetch_open_orders(s)
                    if chunk:
                        open_orders.extend(chunk)
                except Exception:  # noqa: BLE001
                    continue
            if not open_orders:
                return 0

        cancelled = 0
        for o in open_orders or []:
            try:
                typ = str(o.get("type") or "").lower()
                info = o.get("info") or {}
                itype = str(info.get("type") or "").lower()
                is_algo = (
                    "stop" in typ or "stop" in itype
                    or "take_profit" in typ or "take_profit" in itype
                )
                if not is_algo:
                    continue
                ro = o.get("reduceOnly")
                if ro is None:
                    ro = info.get("reduceOnly") or info.get("reduce_only")
                if not bool(ro):
                    continue

                order_sym = str(o.get("symbol") or "")
                # PROTEÇÃO: não cancelar stops de posições ATIVAS de outros
                # símbolos. Excecão: se ccxt_symbol foi passado, esse símbolo
                # específico tem prioridade (caller sabe que precisa limpar).
                if order_sym in active_symbols and order_sym != ccxt_symbol:
                    continue

                oid = o.get("id")
                if not oid:
                    continue
                await exchange.cancel_order(oid, order_sym or ccxt_symbol)
                cancelled += 1
            except Exception:  # noqa: BLE001 — best-effort
                continue
        return cancelled

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
                    err_str = str(exc)
                    # Binance error -4045 ("Reach max stop order limit") happens
                    # when accumulated orphan stops (residue from SL/TP whose
                    # sibling closed the position) consume the per-symbol quota.
                    # Free quota by cancelling reduce-only orphan stops/TPs for
                    # this symbol, then RETRY placement once.
                    if "-4045" in err_str or "max stop order" in err_str.lower():
                        cancelled = 0
                        for _o in open_orders or []:
                            try:
                                _typ = str(_o.get("type") or "").lower()
                                _info = _o.get("info") or {}
                                _itype = str(_info.get("type") or "").lower()
                                _is_algo = (
                                    "stop" in _typ or "stop" in _itype
                                    or "take_profit" in _typ or "take_profit" in _itype
                                )
                                _ro = _o.get("reduceOnly")
                                if _ro is None:
                                    _ro = _info.get("reduceOnly") or _info.get("reduce_only")
                                if _is_algo and bool(_ro):
                                    await exchange.cancel_order(_o.get("id"), ccxt_symbol)
                                    cancelled += 1
                            except Exception:  # noqa: BLE001
                                continue
                        self._log.warning(
                            f"[IronMan/guardian] -4045 hit on {mekka}; cancelled {cancelled} "
                            "orphan reduce-only orders, retrying SL placement"
                        )
                        try:
                            await exchange.create_order(
                                symbol=ccxt_symbol, type="stop_market", side=sl_side,
                                amount=size,
                                params={"stopPrice": sl_price, "reduceOnly": True},
                            )
                            summary["replaced"].append({
                                "symbol": mekka, "sl": sl_price, "emergency": emergency,
                                "cleanup_cancelled": cancelled, "after_4045": True,
                            })
                            self._log.warning(
                                "[IronMan/guardian] re-placed SL for %s after cleaning %d orphans",
                                mekka, cancelled,
                            )
                            try:
                                from src.services.telegram_alerter import TelegramAlerter as _TA  # noqa: WPS433
                                asyncio.create_task(_TA().alert(
                                    event="SL_GUARDIAN_REPLACED",
                                    severity="WARNING", agent="IronMan", symbol=mekka,
                                    message=(
                                        f"🛡️ SL recolocado em {mekka} @ {sl_price:.4f} "
                                        f"após limpar {cancelled} stops órfãos (-4045)."
                                    ),
                                ))
                            except Exception:  # noqa: BLE001
                                pass
                            continue
                        except Exception as retry_exc:  # noqa: BLE001
                            exc = RuntimeError(
                                f"after cleanup ({cancelled} orphans): {retry_exc}"
                            )
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

        # ── Cleanup pass: cancel orphan reduce-only stops/TPs for symbols WITHOUT
        # an open position. When one bracket leg fires (SL or TP) and closes the
        # position, the sibling leg remains orphan and consumes the per-symbol
        # quota; over time this trips Binance -4045 ("max stop order limit").
        # Running this every guardian cycle keeps the quota clean automatically.
        try:
            open_syms = {
                to_mekka(p.get("symbol") or "").upper()
                for p in (positions or [])
                if abs(float(p.get("contracts") or 0)) > 0
            }
            cancelled_total = 0
            for _sym in list(getattr(settings, "trading_assets", []) or []):
                _sym_u = str(_sym).upper()
                if _sym_u in open_syms:
                    continue  # has a position; do not touch its stops
                try:
                    _ccxt_s = to_ccxt(_sym_u, exchange_id, market_type=self._binance_market_type_for(exchange_id))  # type: ignore[arg-type]
                    _oo = await exchange.fetch_open_orders(_ccxt_s)
                except Exception:  # noqa: BLE001
                    continue
                for _o in _oo or []:
                    try:
                        _typ = str(_o.get("type") or "").lower()
                        _info = _o.get("info") or {}
                        _itype = str(_info.get("type") or "").lower()
                        _is_algo = (
                            "stop" in _typ or "stop" in _itype
                            or "take_profit" in _typ or "take_profit" in _itype
                        )
                        _ro = _o.get("reduceOnly")
                        if _ro is None:
                            _ro = _info.get("reduceOnly") or _info.get("reduce_only")
                        if _is_algo and bool(_ro):
                            await exchange.cancel_order(_o.get("id"), _ccxt_s)
                            cancelled_total += 1
                    except Exception:  # noqa: BLE001
                        continue
            if cancelled_total > 0:
                summary["orphans_cancelled"] = cancelled_total
                self._log.info(
                    "[IronMan/guardian] cleanup: cancelled %d orphan reduce-only orders "
                    "(symbols without positions)", cancelled_total,
                )
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"orphan cleanup: {exc}")

        return summary

    async def reconcile_phantom_positions(self) -> dict[str, Any]:
        """Phantom reconciliation — detect positions the DB thinks are open
        but the exchange does not have, then insert a synthetic close so the
        rest of the system (Vision, Wolverine, Cyclops, Risk Scanner) stops
        treating a ghost position as real.

        Background — Risk Scanner (Domino) already detects this drift as an
        ImprovementProposal, but it never acted on it. In mainnet, a phantom
        position is silent risk: any agent reading the DB believes it still
        exists and can add to it, hedge against it, or trigger emergency
        flows that target nothing.

        Paper mode is a no-op. Hyperliquid is skipped (uses different
        bookkeeping; reconciliation there should follow a separate path).

        Returns ``{checked, phantom_closed, errors}``. Read-mostly: only
        writes when a phantom is found. Fail-silent — never raises.
        """
        summary: dict[str, Any] = {"checked": 0, "phantom_closed": [], "errors": []}
        if settings.paper_trading:
            return summary
        if not bool(getattr(settings, "phantom_reconciliation_enabled", True)):
            return summary
        exchange_id = settings.active_exchange
        if exchange_id not in ("bybit", "binance"):
            return summary

        # ── Step 1: build NET live position per symbol from DB ─────────
        from collections import defaultdict  # noqa: WPS433
        from src.persistence.repository import MekkaRepository  # noqa: WPS433

        try:
            trades = await MekkaRepository.list_recent_trades(limit=200)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"db read: {exc}")
            return summary

        # Defensive: detect symbols with a VERY recent trade (< 60s) to skip
        # phantom recon for them. Binance fetch_positions can lag a few seconds
        # behind a fill; if we reconcile during that window we'd see DB=open,
        # exchange=empty and insert a synthetic close that is incorrect (the
        # exchange DOES have the position, just hasn't reported it yet).
        # Premortem 2026-05-25 flagged this as risk #3.
        from datetime import datetime as _dt_ph, timezone as _tz_ph, timedelta as _td_ph
        _now_ph = _dt_ph.now(_tz_ph.utc)
        _fresh_window = _td_ph(seconds=60)
        recent_trade_symbols: set[str] = set()
        for t in trades or []:
            ts = getattr(t, "timestamp", None)
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz_ph.utc)
            if (_now_ph - ts) <= _fresh_window:
                sym_recent = (getattr(t, "symbol", "") or "").upper()
                if sym_recent:
                    recent_trade_symbols.add(sym_recent)

        db_net: dict[str, float] = defaultdict(float)
        for t in trades or []:
            if getattr(t, "is_paper", True):
                continue
            status = (getattr(t, "status", "") or "").upper()
            if status not in ("FILLED", "PARTIAL"):
                continue
            sym = (getattr(t, "symbol", "") or "").upper()
            side = (getattr(t, "side", "") or "").lower()
            qty = float(getattr(t, "quantity", 0) or 0)
            if not sym or qty <= 0:
                continue
            db_net[sym] += qty if side == "long" else -qty

        db_open = {s for s, q in db_net.items() if abs(q) > 1e-8}
        summary["checked"] = len(db_open)
        if not db_open:
            return summary

        # Skip symbols with very fresh trades — exchange may still be syncing.
        fresh_skipped = db_open & recent_trade_symbols
        if fresh_skipped:
            self._log.info(
                f"[IronMan/phantom] skipping {sorted(fresh_skipped)} "
                f"— trade(s) <60s old, exchange may be syncing"
            )
            summary["fresh_skipped"] = sorted(fresh_skipped)
            db_open = db_open - fresh_skipped
        if not db_open:
            return summary

        # ── Step 2: fetch live exchange positions ──────────────────────
        try:
            exchange = await self._get_ccxt_exchange(exchange_id)
            positions = await exchange.fetch_positions()
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"fetch_positions: {exc}")
            return summary

        ex_open: set[str] = set()
        for p in positions or []:
            try:
                if abs(float(p.get("contracts") or 0)) > 0:
                    ex_open.add(to_mekka(p.get("symbol") or "").upper())
            except Exception:  # noqa: BLE001
                continue

        # ── Step 3: synthetic close + audit + alert for each phantom ──
        phantoms = sorted(db_open - ex_open)
        if not phantoms:
            return summary

        for sym in phantoms:
            try:
                net_qty = db_net[sym]
                is_phantom_long = net_qty > 0
                offset_side = "short" if is_phantom_long else "long"
                close_qty = abs(net_qty)

                close_result = ExecutionResult(
                    symbol=sym,
                    status=ExecutionStatus.FILLED,
                    is_paper=False,
                    side=offset_side,
                    quantity=close_qty,
                    avg_price=0.0,
                    notional_usd=0.0,
                    order_id=f"PHANTOM-{sym}-{uuid.uuid4().hex[:8]}",
                    metadata={
                        "action": "phantom_reconciled",
                        "exchange": exchange_id,
                        "reason": "DB had open position, exchange did not.",
                        "original_net_qty": round(net_qty, 8),
                        "original_side": "LONG" if is_phantom_long else "SHORT",
                    },
                )
                await MekkaRepository.save_trade(close_result)
                await MekkaRepository.log_event(
                    agent="IronMan",
                    event="PHANTOM_RECONCILED",
                    severity="WARNING",
                    symbol=sym,
                    message=(
                        f"Phantom reconciliation: DB acha {sym} aberto "
                        f"qty={close_qty:.6f} {'LONG' if is_phantom_long else 'SHORT'}, "
                        f"corretora não tem. Synthetic close inserido."
                    ),
                    payload={
                        "db_net_qty": round(net_qty, 8),
                        "offset_side": offset_side,
                        "exchange": exchange_id,
                    },
                )
                summary["phantom_closed"].append(
                    {
                        "symbol": sym,
                        "qty": round(close_qty, 8),
                        "side": "LONG" if is_phantom_long else "SHORT",
                    }
                )
                # Resolver memórias para o phantom fechado (fail-silent).
                # PnL desconhecido (já foi processado pela corretora em outra sessão),
                # passamos 0.0 — marca como NEUTRAL no AgentMemory.
                try:
                    from src.services.trade_outcome_resolver import resolve_trade_memories
                    await resolve_trade_memories(
                        symbol=sym,
                        pnl_usd=0.0,
                        holding_hours=None,
                    )
                except Exception as _rtm_exc:  # noqa: BLE001
                    self._log.debug(
                        f"[IronMan/reconcile_phantom] resolve_trade_memories no-op: {_rtm_exc}"
                    )
                try:
                    from src.services.telegram_alerter import (  # noqa: WPS433
                        TelegramAlerter as _TA,
                    )

                    asyncio.create_task(
                        _TA().alert(
                            event="PHANTOM_RECONCILED",
                            severity="WARNING",
                            agent="IronMan",
                            symbol=sym,
                            message=(
                                f"⚠️ Phantom reconciliado em {sym} "
                                f"({'LONG' if is_phantom_long else 'SHORT'} qty={close_qty:.6f}) — "
                                f"DB achava aberto, corretora não tem. Synthetic close inserido."
                            ),
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"{sym} phantom close: {exc}")
                self._log.error(f"[IronMan/phantom] {sym}: {exc}")

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
        ccxt_symbol = to_ccxt(to_mekka(symbol), exchange_id, market_type=self._binance_market_type_for(exchange_id))  # type: ignore[arg-type]

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

        # Detectar position mode (one-way vs hedge). Em one-way mode, qty
        # MARKET sem reduceOnly fecha a posição automaticamente — essa é
        # a rota MAIS CONFIÁVEL (validada empiricamente em 2026-05-27 após
        # bug do Testnet com -2022 em reduceOnly).
        is_one_way = True
        if exchange_id == "binance":
            try:
                mode = await exchange.fapiPrivateGetPositionSideDual()
                is_one_way = not bool(mode.get("dualSidePosition", False))
            except Exception:  # noqa: BLE001
                pass

        order = None
        errs: list[str] = []

        # Calcular qty truncada ao step (necessário para MARKET_LOT_SIZE)
        try:
            market = exchange.market(ccxt_symbol)
            step = float(
                (market.get("limits", {}).get("amount", {}) or {}).get("min", 0)
                or (market.get("precision", {}) or {}).get("amount", 0)
                or 0.001
            )
            truncated = (int(size / step)) * step if step > 0 else size
        except Exception:  # noqa: BLE001
            step = 0.0
            truncated = size

        # Estratégia 1 — One-way mode + Binance: MARKET sem reduceOnly.
        # Funciona mesmo quando reduceOnly está bugado no Testnet (-2022).
        # Em one-way, a Binance auto-fecha a posição. Se qty > position,
        # abre dust no lado oposto — por isso truncamos pra baixo no step.
        if exchange_id == "binance" and is_one_way and truncated > 0:
            try:
                order = await exchange.create_order(
                    symbol=ccxt_symbol, type="market", side=close_side,
                    amount=truncated, params={},
                )
                self._log.info(
                    f"[IronMan/{exchange_id}] manual close via MARKET (one-way "
                    f"auto-close, no reduceOnly) qty={truncated} OK"
                )
            except Exception as exc:  # noqa: BLE001
                errs.append(f"MARKET one-way no-reduceOnly: {exc}")

        # Estratégia 2 — STOP_MARKET closePosition (cobre dust restante e
        # hedge mode). Funciona se quota -4045 livre.
        if order is None and exchange_id == "binance":
            try:
                ticker = await exchange.fetch_ticker(ccxt_symbol)
                last_px = float(ticker.get("last") or ticker.get("close") or 0.0)
                if last_px > 0:
                    stop_px = round(last_px * (0.9995 if is_long else 1.0005), 2)
                    order = await exchange.create_order(
                        symbol=ccxt_symbol, type="STOP_MARKET", side=close_side,
                        amount=size,
                        params={
                            "closePosition": True, "stopPrice": stop_px,
                            "workingType": "MARK_PRICE", "priceProtect": False,
                        },
                    )
                    self._log.info(
                        f"[IronMan/{exchange_id}] manual close via STOP_MARKET "
                        f"closePosition OK"
                    )
            except Exception as exc:  # noqa: BLE001
                errs.append(f"STOP_MARKET closePosition: {exc}")

        # Estratégia 3 — MARKET reduceOnly (path histórico, fallback).
        if order is None:
            try:
                order = await exchange.create_order(
                    symbol=ccxt_symbol, type="market", side=close_side,
                    amount=truncated or size, params={"reduceOnly": True},
                )
                self._log.info(
                    f"[IronMan/{exchange_id}] manual close via reduceOnly OK"
                )
            except Exception as exc:  # noqa: BLE001
                errs.append(f"MARKET reduceOnly: {exc}")
                raise type(exc)("; ".join(errs)) from exc
        # Cancel resting SL/TP so they don't fire on a now-flat position.
        try:
            await exchange.cancel_all_orders(ccxt_symbol)
        except Exception as _exc:  # noqa: BLE001
            self._log.warning(f"[IronMan/{exchange_id}] cancel_all_orders after close failed: {_exc}")

        avg = float(order.get("average") or 0) or 0.0
        self._log.warning(
            f"[IronMan/{exchange_id}] manual close {symbol} {side} qty={size} @ {avg}"
        )

        # Resolver memórias (fail-silent). PnL é desconhecido em close manual
        # programático — passamos 0.0 (NEUTRAL). Cyclops/dashboard chamam
        # resolve_trade_memories diretamente quando têm PnL real.
        try:
            from src.services.trade_outcome_resolver import resolve_trade_memories
            await resolve_trade_memories(
                symbol=symbol,
                pnl_usd=0.0,
                holding_hours=None,
            )
        except Exception as _rtm_exc:  # noqa: BLE001
            self._log.debug(
                f"[IronMan/close_position] resolve_trade_memories no-op: {_rtm_exc}"
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
        ccxt_symbol = to_ccxt(to_mekka(symbol), exchange_id, market_type=self._binance_market_type_for(exchange_id))  # type: ignore[arg-type]
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
