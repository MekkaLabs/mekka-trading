"""
src/agents/nick_fury.py
=======================
Nick Fury — Mission Commander

The top-level orchestrator. For each symbol in `settings.trading_assets`
he runs the full pipeline:

   ProfessorX (parallel analysis fan-out)
        ↓
   Vision (LLM strategic decision)
        ↓
   Batman (deterministic risk gate)
        ↓
   Iron Man (paper or live execution)
        ↓
   MekkaRepository (signal + trade + audit persistence)

Two loops are exposed:
  • run_main_cycle() — runs one full pass over all assets (intended for
    `settings.main_loop_interval_seconds`, default 4h)
  • run_monitor_cycle() — light-weight position monitor (intended for
    `settings.monitor_interval_seconds`, default 5m). Currently logs
    open positions; a richer monitor will land in a follow-up story.

Equity and open-positions are sourced from Portfolio Manager every
cycle (Story 026). The optional `equity_usd` argument on
`run_main_cycle` overrides Portfolio Manager when provided (used by the
CLI `--equity` flag and by tests).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.agents.base import AgentError, BaseAgent
from src.agents.batman import Batman, engage_kill_switch, is_kill_switch_active
from src.agents.iron_man import IronMan
from src.agents.portfolio_manager import PortfolioManager
from src.agents.professor_x import ProfessorX
from src.agents.vision import Vision
from src.config.settings import settings
from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.orchestration import CycleReport  # re-exported below for back-compat
from src.models.portfolio import EquitySnapshot, EquitySource
from src.models.recovery import RecoveryPlan
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal
from src.persistence.repository import MekkaRepository
from src.services.breakers import ConsecutiveBreaker
from src.services.daily_pnl_writer import DailyPnLWriter


# ---------------------------------------------------------------------------
# Default starting equity (USD) — used only when both Portfolio Manager and
# the CLI `--equity` override are unavailable. Kept for backward-compatibility
# with code that called `run_main_cycle()` with the old default.
# ---------------------------------------------------------------------------
_DEFAULT_EQUITY_USD = 10_000.0


# `CycleReport` is now a Pydantic model living in
# `src/models/orchestration.py`. It is imported above and re-exported
# here so any existing `from src.agents.nick_fury import CycleReport`
# continues to work without changes.
__all__ = ["NickFury", "CycleReport", "run_forever"]


class NickFury(BaseAgent[list[CycleReport]]):
    """Mission Commander — top-level orchestrator."""

    def __init__(self) -> None:
        super().__init__(
            codename="NickFury",
            role="Mission Commander — global pipeline orchestrator",
        )
        self._professor = ProfessorX()
        self._vision = Vision()
        self._batman = Batman()
        self._ironman = IronMan()
        self._portfolio = PortfolioManager()
        self._daily_pnl = DailyPnLWriter()
        # Story 029a — Safety Net breakers
        self._exec_error_breaker = ConsecutiveBreaker(
            name="exec_error",
            threshold=settings.max_consecutive_exec_errors,
        )
        self._vision_fallback_breaker = ConsecutiveBreaker(
            name="vision_fallback",
            threshold=settings.max_consecutive_vision_fallbacks,
        )
        # Story 030 — Wolverine recovery agent (used in monitor cycle)
        from src.agents.wolverine import Wolverine
        self._wolverine = Wolverine()
        # Story 031 — Vision Critic (off by default; used per cycle when on)
        from src.agents.vision_critic import VisionCritic
        self._vision_critic = VisionCritic()
        # Story 035 — Telegram alerter (push only). Toggle via env.
        from src.services.telegram_alerter import TelegramAlerter
        self._telegram = TelegramAlerter()
        # Story 049 — DailyPerformanceWriter: once-per-day Deadpool snapshot
        from src.services.daily_performance_writer import DailyPerformanceWriter
        self._perf_writer = DailyPerformanceWriter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Start the persistence layer and emit a boot audit event."""
        await MekkaRepository.initialize()

        # Restore peak_equity from DB so a mid-day restart does not hide
        # intra-day drawdown from Batman's daily drawdown guard (Story 057).
        try:
            persisted_peak = await MekkaRepository.get_today_peak_equity()
            if persisted_peak > 0:
                self._daily_pnl._peak_equity = persisted_peak
                self._log.info(
                    f"[NickFury] Restored peak_equity from DB: ${persisted_peak:,.2f}"
                )
        except Exception as _exc:
            self._log.warning(f"[NickFury] Could not restore peak_equity: {_exc}")

        await MekkaRepository.log_event(
            agent="NickFury",
            event="BOOT",
            severity="INFO",
            message=settings.summary(),
            payload={
                "mode": settings.mode_label,
                "network": settings.hyperliquid_network,
                "assets": settings.trading_assets,
            },
        )
        self._log.info("[NickFury] Pipeline initialized")

    def reset_breakers(self) -> None:
        """
        Reset all ConsecutiveBreakers to zero streak.
        Call after releasing the kill switch (/resume) to prevent immediate
        retrip due to residual streak from before the halt.
        """
        self._exec_error_breaker.reset()
        self._vision_fallback_breaker.reset()
        self._log.info("[NickFury] ConsecutiveBreakers reset after kill switch release")

    async def shutdown(self) -> None:
        """Close exchange connections held by sub-agents."""
        await self._professor.close()
        await self._vision.close()
        await MekkaRepository.log_event(
            agent="NickFury",
            event="SHUTDOWN",
            severity="INFO",
            message="Pipeline shutdown clean",
        )
        self._log.info("[NickFury] Pipeline shutdown clean")

    async def _run(  # type: ignore[override]
        self,
        equity_usd: Optional[float] = None,
    ) -> list[CycleReport]:
        """One full pass across all configured assets."""
        return await self.run_main_cycle(equity_usd=equity_usd)

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    async def run_main_cycle(
        self,
        equity_usd: Optional[float] = None,
    ) -> list[CycleReport]:
        """
        Run one full pass across all configured assets.

        Equity is sourced from Portfolio Manager every cycle. Pass
        `equity_usd` to override (used by CLI `--equity` and by tests).
        """
        if is_kill_switch_active():
            self._log.warning("[NickFury] Kill switch ACTIVE — main cycle skipped")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_SKIPPED",
                severity="WARNING",
                message="Kill switch active",
            )
            # Story 035 — push the kill-switch event so the operator
            # actually hears about it.
            await self._telegram.alert(
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                agent="NickFury",
                message="Kill switch active — main cycle skipped",
                payload={"source": "pre_cycle_check"},
            )
            # [A4] Best-effort equity snapshot while halted so daily_pnl
            # remains queryable and Batman's next drawdown read sees fresh data.
            try:
                ks_snapshot = await self._portfolio.run()
                ks_trades_today = await MekkaRepository.count_trades_today()
                ks_equity = (
                    equity_usd if equity_usd is not None else ks_snapshot.equity_usd
                )
                await self._daily_pnl.record_cycle(
                    equity_usd=ks_equity,
                    trades_count_today=ks_trades_today,
                    snapshot=ks_snapshot,
                )
            except Exception as exc:  # noqa: BLE001
                self._log.warning(
                    f"[NickFury] KS: daily_pnl halted-snapshot failed: {exc}"
                )
            return []

        # Read portfolio state for Batman's risk checks
        drawdown = await MekkaRepository.get_today_drawdown_pct()
        trades_today = await MekkaRepository.count_trades_today()

        # ── Story 067 — Daily PnL Auto-pause / Auto-kill ──────────────────
        # Check today's realized PnL against profit target and drawdown cap.
        try:
            today_pnl_usd = await MekkaRepository.get_today_pnl_usd()
            _equity_for_pct = equity_usd or settings.paper_initial_equity
            if _equity_for_pct and _equity_for_pct > 0:
                today_pnl_pct = today_pnl_usd / _equity_for_pct

                # Auto-pause: daily profit target reached → stop new signals
                if today_pnl_pct >= settings.daily_profit_target_pct:
                    self._log.warning(
                        f"[NickFury] Daily profit target reached "
                        f"({today_pnl_pct*100:.2f}% ≥ {settings.daily_profit_target_pct*100:.1f}%) "
                        "— pausing new signals for today"
                    )
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="DAILY_PROFIT_TARGET_REACHED",
                        severity="INFO",
                        message=(
                            f"Daily PnL +${today_pnl_usd:.2f} ({today_pnl_pct*100:.2f}%) "
                            f"≥ target {settings.daily_profit_target_pct*100:.1f}% — cycle skipped"
                        ),
                        payload={"today_pnl_usd": today_pnl_usd, "today_pnl_pct": today_pnl_pct},
                    )
                    try:
                        await self._telegram.alert(
                            event="DAILY_PROFIT_TARGET_REACHED",
                            severity="INFO",
                            agent="NickFury",
                            message=(
                                f"🎯 Meta diária atingida: +${today_pnl_usd:.2f} "
                                f"({today_pnl_pct*100:.2f}%). "
                                "Novos sinais pausados pelo restante do dia."
                            ),
                            payload={},
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    return []

                # Auto-kill: daily drawdown cap triggered → engage kill switch
                if drawdown >= settings.max_daily_drawdown_pct:
                    self._log.error(
                        f"[NickFury] Daily drawdown cap hit "
                        f"({drawdown*100:.2f}% ≥ {settings.max_daily_drawdown_pct*100:.1f}%) "
                        "— engaging kill switch"
                    )
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="DAILY_DRAWDOWN_KILL_SWITCH",
                        severity="CRITICAL",
                        message=(
                            f"Daily drawdown {drawdown*100:.2f}% ≥ cap "
                            f"{settings.max_daily_drawdown_pct*100:.1f}% — kill switch engaged"
                        ),
                        payload={"drawdown_pct": drawdown},
                    )
                    try:
                        await self._telegram.alert(
                            event="DAILY_DRAWDOWN_KILL_SWITCH",
                            severity="CRITICAL",
                            agent="NickFury",
                            message=(
                                f"🛑 DRAWDOWN DIÁRIO: {drawdown*100:.2f}% ≥ "
                                f"{settings.max_daily_drawdown_pct*100:.1f}%. "
                                "Kill switch acionado automaticamente."
                            ),
                            payload={},
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        engage_kill_switch()
                    except Exception:  # noqa: BLE001
                        pass
                    return []
        except Exception as _pnl_exc:  # noqa: BLE001
            self._log.debug(f"[NickFury] Daily PnL gate skipped: {_pnl_exc}")

        # Snapshot account equity + open positions once per cycle
        snapshot: EquitySnapshot = await self._portfolio.run()
        await MekkaRepository.log_event(
            agent="PortfolioManager",
            event=f"SNAPSHOT_{snapshot.source.value}",
            severity="INFO" if not snapshot.is_degraded else "WARNING",
            message=snapshot.summary(),
            payload={
                "equity_usd": snapshot.equity_usd,
                "open_positions": snapshot.open_positions_count,
                "is_paper": snapshot.is_paper,
                "error": snapshot.error,
            },
        )

        # CLI override wins over Portfolio Manager. Otherwise use snapshot.
        effective_equity = (
            equity_usd if equity_usd is not None else snapshot.equity_usd
        )
        open_positions = snapshot.open_positions_count

        # Story 029a — start running notional from existing positions in
        # the snapshot. Each new paper/live execution this cycle adds to it.
        running_notional_usd = sum(
            p.size * p.entry_price for p in (snapshot.positions or [])
        )

        # Runtime mode — hot-reload trading assets without restart
        from src.config.runtime_mode import get_params as _get_mode_params
        _active_assets = _get_mode_params().get("trading_assets", settings.trading_assets)

        # Story 050 — Altcoins validation: filter out symbols not available on
        # the current exchange (prevents CYCLE_ERROR spam for unknown pairs).
        try:
            _validated = await self._professor.validate_symbols(_active_assets)
            if len(_validated) < len(_active_assets):
                _skipped = [s for s in _active_assets if s not in _validated]
                self._log.warning(
                    f"[NickFury] Symbols not available on exchange — skipping: {_skipped}"
                )
                await MekkaRepository.log_event(
                    agent="NickFury",
                    event="SYMBOLS_SKIPPED",
                    severity="WARNING",
                    message=f"Not available on exchange: {_skipped}",
                    payload={"skipped": _skipped, "active": _validated},
                )
            _active_assets = _validated
        except Exception as _val_exc:  # noqa: BLE001
            self._log.warning(
                f"[NickFury] Symbol validation failed (using full list): {_val_exc}"
            )

        # [Story 057] Snapshot of current positions for Batman's correlation gate.
        # Updated intra-cycle as new positions are opened so Batman sees the
        # running state, not just the state at cycle start.
        _current_positions = list(snapshot.positions or [])

        reports: list[CycleReport] = []
        for symbol in _active_assets:
            try:
                report = await self._cycle_for_symbol(
                    symbol=symbol,
                    equity_usd=effective_equity,
                    current_drawdown_pct=drawdown,
                    trades_today=trades_today,
                    open_positions=open_positions,
                    running_notional_usd=running_notional_usd,
                    current_positions=_current_positions,  # [Story 057]
                )
                reports.append(report)
                if report.is_executed():
                    trades_today += 1
                    # A new paper/live position increases the count for the
                    # remainder of this cycle so Batman sees the running total.
                    open_positions += 1
                    if report.execution is not None:
                        running_notional_usd += report.execution.notional_usd
                    # [Story 057] Update correlation snapshot so the next symbol
                    # in this cycle sees the newly opened position.
                    try:
                        from src.models.portfolio import PositionSummary as _PS  # noqa: WPS433
                        _new_pos = _PS(
                            symbol=symbol,
                            side=report.signal.action.value.lower() if report.signal else "long",
                            size=report.execution.quantity if report.execution else 0.0,
                            entry_price=report.execution.avg_price if report.execution else 0.0,
                        )
                        _current_positions.append(_new_pos)
                    except Exception:
                        pass  # correlation gate degrades gracefully

                # Story 029a — observe safety-net breakers per cycle outcome
                await self._check_breakers(report=report)
            except Exception as exc:  # noqa: BLE001
                self._log.exception(f"[NickFury] {symbol} cycle crashed: {exc}")
                reports.append(CycleReport(symbol=symbol, error=str(exc)))
                await MekkaRepository.log_event(
                    agent="NickFury",
                    event="CYCLE_ERROR",
                    severity="ERROR",
                    symbol=symbol,
                    message=str(exc),
                )
                # Story 035 — best-effort Telegram push (filtered internally)
                await self._telegram.alert(
                    event="CYCLE_ERROR",
                    severity="ERROR",
                    agent="NickFury",
                    symbol=symbol,
                    message=str(exc),
                )

        # End-of-cycle Daily PnL upsert. Uses the *effective* equity
        # (CLI override wins over snapshot, same hierarchy used for
        # Iron Man sizing) and `trades_today` count after this cycle so
        # Batman's next read of get_today_drawdown_pct sees fresh data.
        try:
            await self._daily_pnl.record_cycle(
                equity_usd=effective_equity,
                trades_count_today=trades_today,
                snapshot=snapshot,
            )
        except Exception as exc:  # noqa: BLE001
            # Persistence failure must not break the main cycle return value.
            self._log.error(f"[NickFury] daily_pnl record_cycle failed: {exc}")

        # Story 049 — fire DailyPerformanceWriter once per UTC day (no-op if already ran)
        try:
            import asyncio as _asyncio  # noqa: WPS433
            _asyncio.create_task(self._perf_writer.maybe_run(), name="daily_perf_writer")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[NickFury] daily_perf_writer task failed to start: {exc}")

        return reports

    async def _cycle_for_symbol(
        self,
        symbol: str,
        equity_usd: float,
        current_drawdown_pct: float,
        trades_today: int,
        open_positions: int = 0,
        running_notional_usd: float = 0.0,
        current_positions: list | None = None,  # [Story 057] correlation gate
    ) -> CycleReport:
        # 1. Analysis fan-out
        try:
            analysis = await self._professor.run(symbol=symbol)
        except AgentError as exc:
            return CycleReport(symbol=symbol, error=f"Analysis failed: {exc}")

        # 2. Vision strategic decision
        signal = await self._vision.run(analysis=analysis)

        # 2b. Vision Critic — second-look (Story 031, off by default).
        # Save the post-critique signal so audit reflects what Batman
        # actually saw, but log the critique separately.
        if settings.vision_critic_enabled:
            try:
                from src.agents.vision_critic import apply_critique
                critique = await self._vision_critic.run(
                    analysis=analysis,
                    signal=signal,
                )
                await MekkaRepository.log_event(
                    agent="VisionCritic",
                    event=f"CRITIQUE_{critique.action.value}",
                    severity="INFO",
                    symbol=symbol,
                    message=critique.summary(),
                    payload=critique.to_audit_payload(),
                )
                if critique.is_actionable():
                    signal = apply_critique(signal=signal, critique=critique)
            except Exception as exc:  # noqa: BLE001
                # Critic must NEVER break the cycle. Defensive ENDORSE
                # via fallback path is already handled inside _run, but
                # any unexpected error here just logs and continues.
                self._log.warning(f"[NickFury] critic skipped: {exc}")

        signal_id = await MekkaRepository.save_signal(signal)

        # Story 063 — Episodic Memory: record actionable signals so Batman/Vision
        # can query historical win-rates for similar patterns in future cycles.
        # Only record LONG/SHORT (not HOLD). Fails silently — never breaks cycle.
        if signal.action != TradeAction.HOLD and signal.is_actionable:
            try:
                from src.persistence.agent_memory import AgentMemoryStore as _AMS  # noqa: WPS433
                _chart = analysis.chart if analysis else None
                _rsi = _chart.rsi_14 if _chart else None
                _trend = _chart.trend.value if _chart else "NEUTRAL"
                _vol_elev = bool(_chart.volume_spike) if _chart else False
                # Cache RSI + trend into signal metadata so Batman can re-read them
                if signal.metadata is None:
                    signal = signal.model_copy(update={"metadata": {}})
                _meta_update = dict(signal.metadata)
                _meta_update.update({
                    "rsi": round(_rsi, 1) if _rsi is not None else None,
                    "trend": _trend,
                })
                signal = signal.model_copy(update={"metadata": _meta_update})
                await _AMS.record_signal(
                    symbol=symbol,
                    action=signal.action.value,
                    rsi=_rsi,
                    trend=_trend,
                    volume_elevated=_vol_elev,
                    confidence=signal.confidence,
                    signal_id=signal_id,
                )
            except Exception as _mem_exc:  # noqa: BLE001
                self._log.debug(f"[NickFury] Episodic memory record skipped: {_mem_exc}")

        # 3. Batman risk gate
        approval = await self._batman.run(
            signal=signal,
            volatility=analysis.volatility,
            liquidity=analysis.liquidity,
            current_drawdown_pct=current_drawdown_pct,
            open_positions=open_positions,
            trades_today=trades_today,
            running_notional_usd=running_notional_usd,
            equity_usd=equity_usd,
            current_positions=current_positions or [],  # [Story 057] correlation gate
        )

        await MekkaRepository.log_event(
            agent="Batman",
            event=f"RISK_{approval.verdict.value}",
            severity="INFO" if approval.is_executable else "WARNING",
            symbol=symbol,
            message=approval.summary(),
            payload={
                "reasons": approval.reasons,
                "breached": approval.breached_limits,
            },
        )
        # Story 035 — only KILL_SWITCH triggers a push by default
        if approval.verdict == RiskVerdict.KILL_SWITCH:
            await self._telegram.alert(
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                agent="Batman",
                symbol=symbol,
                message=approval.summary(),
                payload={"breached": approval.breached_limits},
            )

        if not approval.is_executable:
            return CycleReport(symbol=symbol, signal=signal, approval=approval)

        # ── Story 074 — Telegram Trade Approval ─────────────────────
        # Request operator confirmation via Telegram before IronMan executes.
        # Falls open: any error in the approval flow skips and proceeds.
        if settings.telegram_trade_approval_enabled:
            try:
                import uuid as _uuid  # noqa: WPS433
                from src.services.trade_approval import request_approval as _req_approval  # noqa: WPS433
                _trade_id = f"T-{_uuid.uuid4().hex[:10].upper()}"
                _approved = await _req_approval(
                    trade_id=_trade_id,
                    signal_symbol=symbol,
                    signal_action=signal.action.value,
                    signal_confidence=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    size_pct=approval.adjusted_size_pct,
                    leverage=approval.adjusted_leverage,
                    reasons=approval.reasons,
                    timeout_s=settings.telegram_trade_approval_timeout_s,
                )
                if not _approved:
                    await MekkaRepository.log_event(
                        agent="NickFury",
                        event="TRADE_APPROVAL_REJECTED",
                        severity="INFO",
                        symbol=symbol,
                        message=f"[074] Trade {_trade_id} rejected by operator (or timeout in live mode)",
                        payload={"trade_id": _trade_id, "symbol": symbol, "action": signal.action.value},
                    )
                    return CycleReport(symbol=symbol, signal=signal, approval=approval)
            except Exception as _appr_exc:  # noqa: BLE001
                self._log.warning("[NickFury] Trade approval gate error (skipped): %s", _appr_exc)

        # 4. Iron Man execution
        execution = await self._ironman.run(
            signal=signal,
            approval=approval,
            equity_usd=equity_usd,
        )
        await MekkaRepository.save_trade(execution=execution, signal_id=signal_id)

        await MekkaRepository.log_event(
            agent="IronMan",
            event=f"EXEC_{execution.status.value}",
            severity="INFO" if execution.status in (
                ExecutionStatus.FILLED,
                ExecutionStatus.PARTIAL,
                ExecutionStatus.PAPER,
            ) else "WARNING",
            symbol=symbol,
            message=execution.summary(),
            payload={"is_paper": execution.is_paper},
        )
        # Story 035 — push on ERROR / REJECTED outcomes
        if execution.status in (ExecutionStatus.ERROR, ExecutionStatus.REJECTED):
            await self._telegram.alert(
                event=f"EXEC_{execution.status.value}",
                severity="ERROR",
                agent="IronMan",
                symbol=symbol,
                message=execution.summary(),
                payload={"error": execution.error or "", "is_paper": execution.is_paper},
            )
        # Rich trade-opened notification for every FILLED / PAPER execution
        elif execution.status in (ExecutionStatus.FILLED, ExecutionStatus.PAPER):
            await self._telegram.trade_opened(execution=execution, signal=signal)

        return CycleReport(
            symbol=symbol,
            signal=signal,
            approval=approval,
            execution=execution,
        )

    # ------------------------------------------------------------------
    # Safety net (Story 029a)
    # ------------------------------------------------------------------

    async def _check_breakers(self, report: CycleReport) -> None:
        """
        Feed cycle outcome to the safety-net breakers and engage the kill
        switch if either trips. Called once per symbol after the cycle.
        """
        # 1. Iron Man consecutive ERROR breaker
        is_exec_error = (
            report.execution is not None
            and report.execution.status == ExecutionStatus.ERROR
        )
        if self._exec_error_breaker.observe(is_exec_error):
            reason = (
                f"{self._exec_error_breaker.threshold} consecutive Iron Man "
                f"ERROR executions — kill switch engaged"
            )
            engage_kill_switch(reason)
            await MekkaRepository.log_event(
                agent="NickFury",
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                symbol=report.symbol,
                message=reason,
                payload={"breaker": "exec_error", "trips_lifetime": self._exec_error_breaker.trip_count},
            )

        # 2. Vision consecutive HOLD-fallback breaker
        is_vision_fallback = (
            report.signal is not None
            and report.signal.action == TradeAction.HOLD
            and bool((report.signal.metadata or {}).get("fallback", False))
        )
        if self._vision_fallback_breaker.observe(is_vision_fallback):
            reason = (
                f"{self._vision_fallback_breaker.threshold} consecutive Vision "
                f"HOLD-fallbacks — LLM degraded, kill switch engaged"
            )
            engage_kill_switch(reason)
            await MekkaRepository.log_event(
                agent="NickFury",
                event="RISK_KILL_SWITCH",
                severity="ERROR",
                symbol=report.symbol,
                message=reason,
                payload={"breaker": "vision_fallback", "trips_lifetime": self._vision_fallback_breaker.trip_count},
            )

    # ------------------------------------------------------------------
    # Market price helper (for Wolverine real-time drawdown)
    # ------------------------------------------------------------------

    async def _fetch_current_mids(self, symbols: list[str]) -> dict[str, float]:
        """
        Fetch last mid-prices for ``symbols`` from Hyperliquid public REST.
        Uses the ``/info`` endpoint (no auth required) so it works in both
        paper and live modes. Returns an empty dict on any failure — Wolverine
        degrades gracefully when prices are absent.
        """
        if not symbols:
            return {}
        try:
            import aiohttp  # noqa: WPS433
            url = settings.hyperliquid_base_url + "/info"
            payload = {"type": "allMids"}
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        return {}
                    data: dict = await resp.json()
            result: dict[str, float] = {}
            for sym in symbols:
                raw = data.get(sym) or data.get(f"{sym}-USD")
                if raw is not None:
                    try:
                        result[sym] = float(raw)
                    except (TypeError, ValueError):
                        pass
            return result
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                f"[NickFury] _fetch_current_mids failed (Wolverine will use entry_price): {exc}"
            )
            return {}

    # ------------------------------------------------------------------
    # Monitor cycle
    # ------------------------------------------------------------------

    async def run_monitor_cycle(self) -> dict:
        """
        Monitor cycle (Story 030). Reads current portfolio state via
        Portfolio Manager and lets Wolverine produce a RecoveryPlan.

        Wolverine is **read-only** on the exchange. The plan is logged
        to `audit_log` so the operator and the dashboard can see what
        Wolverine intended; actually modifying SL/TP on Hyperliquid is
        a future story (Iron Man integration).

        If the kill switch is already engaged, the cycle short-circuits.
        If Wolverine itself engages the kill switch (intraday drawdown
        breach), the audit event records that.
        """
        if is_kill_switch_active():
            return {"status": "halted", "reason": "kill_switch"}

        # Pull a fresh snapshot so Wolverine sees current positions.
        try:
            snapshot = await self._portfolio.run()
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[NickFury] monitor: portfolio.run failed: {exc}")
            await MekkaRepository.log_event(
                agent="NickFury",
                event="CYCLE_ERROR",
                severity="ERROR",
                message=f"monitor: portfolio.run failed: {exc}",
            )
            return {"status": "error", "reason": str(exc)}

        # [A1] Fetch real-time prices so Wolverine can compute actual
        # unrealized PnL for each open position (vs. always seeing 0).
        open_symbols = [p.symbol for p in (snapshot.positions or [])]
        current_prices = await self._fetch_current_mids(open_symbols)

        # Wolverine reasons over the snapshot with live prices.
        try:
            plan = await self._wolverine.run(
                snapshot=snapshot,
                current_prices=current_prices or None,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.exception(f"[NickFury] monitor: wolverine.run failed: {exc}")
            await MekkaRepository.log_event(
                agent="Wolverine",
                event="CYCLE_ERROR",
                severity="ERROR",
                message=f"wolverine.run failed: {exc}",
            )
            return {"status": "error", "reason": str(exc)}

        # Persist the plan as an audit event.
        await MekkaRepository.log_event(
            agent="Wolverine",
            event="MONITOR_RECOVERY_PLAN",
            severity="WARNING" if plan.kill_switch_engaged else "INFO",
            message=plan.summary(),
            payload=plan.to_audit_payload(),
        )
        # Stories 035 / 059 — rich Telegram alert when kill switch fires
        if plan.kill_switch_engaged:
            asyncio.create_task(self._telegram.wolverine_kill_switch(
                intraday_drawdown_pct=plan.intraday_drawdown_pct,
                positions_count=len(plan.positions),
                notes=plan.notes,
                is_paper=settings.paper_trading,
            ))

        # [C1] Execute actionable positions — Wolverine reasons, IronMan acts.
        actions_taken = 0
        if plan.needs_action:
            actions_taken = await self._execute_recovery_plan(plan, current_prices)

        # [C2] Run Cyclops — SL/TP monitor for paper positions
        cyclops_triggered = 0
        try:
            from src.agents.cyclops import Cyclops  # noqa: WPS433
            cyclops = Cyclops()
            cyclops_triggered = await cyclops.run(current_prices=current_prices)
        except Exception as _exc:
            self._log.warning(f"[NickFury] Cyclops skipped: {_exc}")

        return {
            "status": "halted" if plan.kill_switch_engaged else "ok",
            "positions_monitored": len(plan.positions),
            "intraday_drawdown_pct": plan.intraday_drawdown_pct,
            "kill_switch_engaged": plan.kill_switch_engaged,
            "recovery_actions_taken": actions_taken,
            "cyclops_triggered": cyclops_triggered,
        }

    async def _execute_recovery_plan(
        self,
        plan: RecoveryPlan,
        current_prices: dict[str, float],
    ) -> int:
        """[C1] Execute actionable positions from a Wolverine RecoveryPlan.

        For CLOSE / EMERGENCY_CLOSE: create an offsetting paper trade that
        nets out the position. For SCALE_OUT: close 50% of the position.
        For TIGHTEN_STOP / TRAIL_STOP (Story 058): modify the stop-loss (and
        optionally take-profit) on the exchange (live) or in the DB (paper,
        so Cyclops honours the new price on the next monitor cycle).

        Returns the count of positions where an action was taken.
        """
        from src.models.recovery import RecoveryAction  # noqa: WPS433

        _SL_MODIFY_ACTIONS = {RecoveryAction.TIGHTEN_STOP, RecoveryAction.TRAIL_STOP}
        _ACTIONABLE = {
            RecoveryAction.CLOSE,
            RecoveryAction.EMERGENCY_CLOSE,
            RecoveryAction.SCALE_OUT,
            RecoveryAction.TIGHTEN_STOP,
            RecoveryAction.TRAIL_STOP,
        }
        actions_taken = 0

        for pos_update in plan.positions:
            if pos_update.action not in _ACTIONABLE:
                continue

            symbol = pos_update.symbol.upper()
            mark = (
                current_prices.get(symbol)
                or current_prices.get(symbol.upper())
                or pos_update.entry_price
            )

            # ----------------------------------------------------------------
            # [Story 058] TIGHTEN_STOP / TRAIL_STOP — modify SL/TP in place
            # ----------------------------------------------------------------
            if pos_update.action in _SL_MODIFY_ACTIONS:
                new_sl = pos_update.new_stop_loss
                new_tp = pos_update.new_take_profit

                if new_sl is None:
                    self._log.warning(
                        f"[Wolverine/C1] {pos_update.action.value} for {symbol}: "
                        "no new_stop_loss provided — skipping"
                    )
                    continue

                try:
                    if settings.paper_trading:
                        # Paper: update raw metadata so Cyclops uses the new SL
                        updated = await MekkaRepository.update_trade_sl_tp(
                            symbol=symbol, new_sl=new_sl, new_tp=new_tp
                        )
                        status_msg = f"paper_updated_{updated}_records"
                    else:
                        # Live: cancel old bracket orders and place new ones via IronMan
                        modify_result = await self._ironman.modify_sl_tp(
                            symbol=symbol,
                            side=pos_update.side,
                            quantity=pos_update.size,
                            new_sl=new_sl,
                            new_tp=new_tp,
                        )
                        status_msg = modify_result.get("status", "unknown")

                    await MekkaRepository.log_event(
                        agent="Wolverine",
                        event="SL_MODIFIED",
                        severity="INFO",
                        symbol=symbol,
                        message=(
                            f"[C1] {pos_update.action.value}: SL→{new_sl:,.4f} "
                            f"{'TP→' + f'{new_tp:,.4f}' if new_tp else ''} "
                            f"({pos_update.reason}) [{status_msg}]"
                        ),
                        payload={
                            "action": pos_update.action.value,
                            "symbol": symbol,
                            "new_sl": new_sl,
                            "new_tp": new_tp,
                            "reason": pos_update.reason,
                            "mark_price": mark,
                            "status": status_msg,
                        },
                    )
                    actions_taken += 1
                    self._log.info(
                        f"[Wolverine/C1] {pos_update.action.value} executed — "
                        f"{symbol} SL→{new_sl:,.4f}"
                        + (f" TP→{new_tp:,.4f}" if new_tp else "")
                    )
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        new_sl=new_sl,
                        new_tp=new_tp,
                        is_paper=settings.paper_trading,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(
                        f"[Wolverine/C1] {pos_update.action.value} failed for {symbol}: {_exc}"
                    )
                continue  # don't fall through to the close/scale-out branch

            # Determine close quantity
            if pos_update.action == RecoveryAction.SCALE_OUT:
                close_qty = round(pos_update.size * 0.5, 8)  # close half
            else:
                close_qty = pos_update.size  # close all

            if close_qty < 1e-8:
                continue

            # Opposite side = close direction
            close_side = "short" if pos_update.side.lower() == "long" else "long"

            if settings.paper_trading:
                # Paper: insert offsetting trade directly
                import uuid  # noqa: WPS433
                from src.models.execution import ExecutionResult, ExecutionStatus  # noqa: WPS433

                close_result = ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.PAPER,
                    is_paper=True,
                    side=close_side,
                    quantity=close_qty,
                    avg_price=round(mark, 6),
                    notional_usd=round(close_qty * mark, 2),
                    order_id=f"WOLVERINE-CLOSE-{uuid.uuid4().hex[:10]}",
                    metadata={
                        "triggered_by": "wolverine",
                        "action": pos_update.action.value,
                        "reason": pos_update.reason,
                        "mark_price": mark,
                    },
                )
                try:
                    await MekkaRepository.save_trade(execution=close_result)
                    await MekkaRepository.log_event(
                        agent="Wolverine",
                        event="RECOVERY_ACTION_TAKEN",
                        severity="WARNING",
                        symbol=symbol,
                        message=(
                            f"[C1] {pos_update.action.value}: closed {close_qty:.6f} {symbol} "
                            f"@ {mark:,.4f} ({pos_update.reason})"
                        ),
                        payload={
                            "action": pos_update.action.value,
                            "symbol": symbol,
                            "close_qty": close_qty,
                            "close_price": mark,
                            "reason": pos_update.reason,
                        },
                    )
                    actions_taken += 1
                    self._log.warning(
                        f"[Wolverine/C1] {pos_update.action.value} executed — "
                        f"{close_qty:.6f} {symbol} @ {mark:,.4f}"
                    )
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        close_qty=close_qty,
                        is_paper=True,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(f"[Wolverine/C1] save_trade failed for {symbol}: {_exc}")
            else:
                # Live: delegate to IronMan via a synthetic close signal
                try:
                    from src.models.signal import TradeAction, TradingSignal  # noqa: WPS433
                    from src.models.risk import RiskApproval, RiskVerdict  # noqa: WPS433

                    close_action = (
                        TradeAction.SHORT if pos_update.side.lower() == "long" else TradeAction.LONG
                    )
                    close_signal = TradingSignal(
                        symbol=symbol,
                        action=close_action,
                        confidence=1.0,
                        entry_price=mark,
                        stop_loss=mark * (0.99 if close_action == TradeAction.LONG else 1.01),
                        take_profit=mark * (1.01 if close_action == TradeAction.LONG else 0.99),
                        size_pct=0.0,
                        leverage=pos_update.leverage,
                        reasoning=f"Wolverine {pos_update.action.value}: {pos_update.reason}",
                    )
                    approval = RiskApproval(
                        verdict=RiskVerdict.APPROVED,
                        adjusted_size_pct=close_qty * mark / max(float(settings.paper_equity_usd), 1),
                        adjusted_leverage=pos_update.leverage,
                        reasons=["wolverine_recovery"],
                        breached_limits=[],
                    )
                    exec_result = await self._ironman.run(
                        signal=close_signal,
                        approval=approval,
                        equity_usd=float(settings.paper_equity_usd),
                    )
                    await MekkaRepository.save_trade(execution=exec_result)
                    actions_taken += 1
                    # [Story 059] Telegram alert
                    from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
                    asyncio.create_task(TelegramAlerter().wolverine_action(
                        action=pos_update.action.value,
                        symbol=symbol,
                        side=pos_update.side,
                        entry_price=pos_update.entry_price,
                        mark_price=mark,
                        size=pos_update.size,
                        unrealized_pnl_usd=pos_update.unrealized_pnl_usd,
                        reason=pos_update.reason,
                        close_qty=close_qty,
                        is_paper=False,
                    ))
                except Exception as _exc:  # noqa: BLE001
                    self._log.error(
                        f"[Wolverine/C1] live close failed for {symbol}: {_exc}"
                    )

        return actions_taken


# ---------------------------------------------------------------------------
# Convenience: long-running scheduler loop
# ---------------------------------------------------------------------------


async def run_forever(equity_usd: Optional[float] = None) -> None:
    """
    Run main + monitor cycles forever using settings intervals.

    Wakes up every monitor_interval_seconds; runs main cycle every
    main_loop_interval_seconds (rounded to monitor ticks).

    `equity_usd` is an optional override (CLI `--equity`). When None,
    Portfolio Manager sources equity from Hyperliquid (or from the
    paper-fallback when credentials are missing).
    """
    fury = NickFury()
    await fury.initialize()

    monitor_interval = settings.monitor_interval_seconds
    main_interval = settings.main_loop_interval_seconds
    last_main_at = 0.0

    try:
        while True:
            now = asyncio.get_event_loop().time()
            if now - last_main_at >= main_interval:
                logger.info("[NickFury] Starting main cycle")
                await fury.run_main_cycle(equity_usd=equity_usd)
                last_main_at = now
            else:
                await fury.run_monitor_cycle()
            await asyncio.sleep(monitor_interval)
    except asyncio.CancelledError:
        logger.info("[NickFury] Loop cancelled — shutting down")
    finally:
        await fury.shutdown()
