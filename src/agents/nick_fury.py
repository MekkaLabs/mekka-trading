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
from src.agents.batman import Batman, is_kill_switch_active
from src.agents.iron_man import IronMan
from src.agents.portfolio_manager import PortfolioManager
from src.agents.professor_x import ProfessorX
from src.agents.vision import Vision
from src.config.settings import settings
from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.orchestration import CycleReport  # re-exported below for back-compat
from src.models.portfolio import EquitySnapshot, EquitySource
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradingSignal
from src.persistence.repository import MekkaRepository
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Start the persistence layer and emit a boot audit event."""
        await MekkaRepository.initialize()
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
            return []

        # Read portfolio state for Batman's risk checks
        drawdown = await MekkaRepository.get_today_drawdown_pct()
        trades_today = await MekkaRepository.count_trades_today()

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

        reports: list[CycleReport] = []
        for symbol in settings.trading_assets:
            try:
                report = await self._cycle_for_symbol(
                    symbol=symbol,
                    equity_usd=effective_equity,
                    current_drawdown_pct=drawdown,
                    trades_today=trades_today,
                    open_positions=open_positions,
                )
                reports.append(report)
                if report.is_executed():
                    trades_today += 1
                    # A new paper/live position increases the count for the
                    # remainder of this cycle so Batman sees the running total.
                    open_positions += 1
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

        return reports

    async def _cycle_for_symbol(
        self,
        symbol: str,
        equity_usd: float,
        current_drawdown_pct: float,
        trades_today: int,
        open_positions: int = 0,
    ) -> CycleReport:
        # 1. Analysis fan-out
        try:
            analysis = await self._professor.run(symbol=symbol)
        except AgentError as exc:
            return CycleReport(symbol=symbol, error=f"Analysis failed: {exc}")

        # 2. Vision strategic decision
        signal = await self._vision.run(analysis=analysis)
        signal_id = await MekkaRepository.save_signal(signal)

        # 3. Batman risk gate
        approval = await self._batman.run(
            signal=signal,
            volatility=analysis.volatility,
            liquidity=analysis.liquidity,
            current_drawdown_pct=current_drawdown_pct,
            open_positions=open_positions,
            trades_today=trades_today,
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

        if not approval.is_executable:
            return CycleReport(symbol=symbol, signal=signal, approval=approval)

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

        return CycleReport(
            symbol=symbol,
            signal=signal,
            approval=approval,
            execution=execution,
        )

    # ------------------------------------------------------------------
    # Monitor cycle
    # ------------------------------------------------------------------

    async def run_monitor_cycle(self) -> dict:
        """Lightweight position-monitor stub. Will be expanded by Wolverine."""
        if is_kill_switch_active():
            return {"status": "halted", "reason": "kill_switch"}
        # Placeholder: no real position fetch yet — will land with portfolio
        # manager. For now we just emit a heartbeat audit event.
        await MekkaRepository.log_event(
            agent="NickFury",
            event="MONITOR_HEARTBEAT",
            severity="DEBUG",
            message="Monitor cycle ran",
            payload={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
        return {"status": "ok"}


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
