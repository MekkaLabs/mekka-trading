"""
src/persistence/repository.py
=============================
High-level async repository wrapping the SQLAlchemy models.

Exposes ergonomic write methods used by Nick Fury (Mission Commander)
and the Telegram bot. All methods are coroutines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select

from src.models.execution import ExecutionResult
from src.models.signal import TradingSignal
from src.persistence.db import get_session, init_engine
from src.persistence.models import (
    AuditRecord,
    DailyPnLRecord,
    PerfReportRecord,
    SignalRecord,
    TradeRecord,
)


class MekkaRepository:
    """High-level async data access layer."""

    @staticmethod
    async def initialize() -> None:
        """Force engine creation + table DDL."""
        await init_engine()

    # ------------------------------------------------------------------
    # Signal writes
    # ------------------------------------------------------------------

    @staticmethod
    async def save_signal(signal: TradingSignal) -> int:
        """Persist a TradingSignal and return its DB id."""
        rec = SignalRecord(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            action=signal.action.value,
            confidence=signal.confidence,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            size_pct=signal.size_pct,
            leverage=signal.leverage,
            risk_reward=signal.risk_reward_ratio,
            reasoning=signal.reasoning,
            is_actionable=signal.is_actionable,
            fallback=bool((signal.metadata or {}).get("fallback", False)),
            raw=signal.model_dump(mode="json"),
        )
        async with get_session() as session:
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
            return rec.id

    # ------------------------------------------------------------------
    # Trade writes
    # ------------------------------------------------------------------

    @staticmethod
    async def save_trade(
        execution: ExecutionResult,
        signal_id: Optional[int] = None,
        pnl_usd: Optional[float] = None,
    ) -> int:
        """Persist an ExecutionResult and return its DB id."""
        rec = TradeRecord(
            timestamp=execution.timestamp,
            signal_id=signal_id,
            symbol=execution.symbol,
            status=execution.status.value,
            is_paper=execution.is_paper,
            side=execution.side,
            quantity=execution.quantity,
            avg_price=execution.avg_price,
            notional_usd=execution.notional_usd,
            pnl_usd=pnl_usd,
            order_id=execution.order_id,
            sl_order_id=execution.sl_order_id,
            tp_order_id=execution.tp_order_id,
            error=execution.error,
            raw=execution.model_dump(mode="json"),
        )
        async with get_session() as session:
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
            return rec.id

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    @staticmethod
    async def log_event(
        agent: str,
        event: str,
        message: str = "",
        symbol: Optional[str] = None,
        severity: str = "INFO",
        payload: Optional[dict] = None,
    ) -> int:
        rec = AuditRecord(
            agent=agent,
            event=event,
            message=message,
            symbol=symbol,
            severity=severity,
            payload=payload,
        )
        async with get_session() as session:
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
            return rec.id

    # ------------------------------------------------------------------
    # Daily PnL upsert
    # ------------------------------------------------------------------

    @staticmethod
    async def upsert_daily_pnl(
        date_utc: str,
        is_paper: bool,
        ending_equity: float,
        pnl_usd: float,
        pnl_pct: float,
        drawdown_pct: float,
        trades_count: int,
        wins: int,
        losses: int,
        starting_equity: Optional[float] = None,
    ) -> int:
        """Insert or update the row for a given UTC date."""
        async with get_session() as session:
            existing = (
                await session.execute(
                    select(DailyPnLRecord).where(DailyPnLRecord.date_utc == date_utc)
                )
            ).scalar_one_or_none()

            if existing is None:
                rec = DailyPnLRecord(
                    date_utc=date_utc,
                    is_paper=is_paper,
                    starting_equity=starting_equity or ending_equity - pnl_usd,
                    ending_equity=ending_equity,
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    drawdown_pct=drawdown_pct,
                    trades_count=trades_count,
                    wins=wins,
                    losses=losses,
                )
                session.add(rec)
                await session.commit()
                await session.refresh(rec)
                return rec.id

            existing.ending_equity = ending_equity
            existing.pnl_usd = pnl_usd
            existing.pnl_pct = pnl_pct
            existing.drawdown_pct = drawdown_pct
            existing.trades_count = trades_count
            existing.wins = wins
            existing.losses = losses
            await session.commit()
            return existing.id

    # ------------------------------------------------------------------
    # Read queries
    # ------------------------------------------------------------------

    @staticmethod
    async def get_today_drawdown_pct() -> float:
        """Read today's drawdown_pct or 0.0 if no row yet."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with get_session() as session:
            row = (
                await session.execute(
                    select(DailyPnLRecord.drawdown_pct).where(
                        DailyPnLRecord.date_utc == today
                    )
                )
            ).scalar_one_or_none()
            return float(row) if row is not None else 0.0

    @staticmethod
    async def count_trades_today() -> int:
        """Count rows in trades for today's UTC date."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with get_session() as session:
            row = (
                await session.execute(
                    select(func.count(TradeRecord.id)).where(
                        TradeRecord.timestamp >= today_start
                    )
                )
            ).scalar_one()
            return int(row or 0)

    @staticmethod
    async def list_recent_signals(limit: int = 20) -> list[SignalRecord]:
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(SignalRecord)
                    .order_by(desc(SignalRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def list_recent_trades(limit: int = 20) -> list[TradeRecord]:
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .order_by(desc(TradeRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def list_paper_filled_trades(limit: int = 200) -> list[TradeRecord]:
        """Paper trades with status FILLED or PAPER, newest first.

        Used by the positions provider to synthesize open paper positions
        from the trades table (Hyperliquid is not called in paper mode).
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(TradeRecord.is_paper == True)  # noqa: E712
                    .where(TradeRecord.status.in_(["FILLED", "PAPER"]))
                    .order_by(desc(TradeRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def list_recent_audit(limit: int = 50) -> list[AuditRecord]:
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(AuditRecord)
                    .order_by(desc(AuditRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def list_audit_by_event(event: str, limit: int = 500) -> list[AuditRecord]:
        """Audit rows filtered by a specific event code.

        Used by Deadpool to pull structured rows such as
        ``MONITOR_RECOVERY_PLAN`` (Wolverine cycle logs) without loading
        the entire audit log. Oldest-first so the caller can walk
        chronologically.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(AuditRecord)
                    .where(AuditRecord.event == event)
                    .order_by(AuditRecord.timestamp.asc())
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    # ------------------------------------------------------------------
    # Daily PnL reads (used by the Equity & PnL dashboard panel)
    # ------------------------------------------------------------------

    @staticmethod
    async def list_trades_within(hours: int) -> list[TradeRecord]:
        """Trades executed in the last ``hours`` hours, oldest-first.

        Used by the dashboard to bin executions per hour. Bounded so even
        an active book never returns more than the broadcast loop can
        process — the UI itself caps at 24h × ~60 trades/h ≈ 1500 rows.
        """
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(TradeRecord.timestamp >= since)
                    .order_by(TradeRecord.timestamp.asc())
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def list_recent_daily_pnl(limit: int = 90) -> list[DailyPnLRecord]:
        """Most recent ``limit`` daily-PnL rows, oldest-first.

        Returning oldest-first means the dashboard can plot directly without
        reversing client-side. SQLAlchemy gives us a list[DailyPnLRecord]
        which the API layer turns into a JSON-friendly dict.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(DailyPnLRecord)
                    .order_by(desc(DailyPnLRecord.date_utc))
                    .limit(limit)
                )
            ).scalars().all()
            # `desc()` gives newest-first; reverse so charts grow left→right.
            return list(reversed(rows))

    @staticmethod
    async def get_pnl_summary(window_days: int = 30) -> dict:
        """Aggregate stats over the last ``window_days`` daily rows.

        Returns total PnL, win rate, max drawdown across the window plus
        all-time totals so the UI can show "30d / all-time" side-by-side.
        Days with zero trades are excluded from win-rate to avoid bias.
        """
        async with get_session() as session:
            recent = (
                await session.execute(
                    select(DailyPnLRecord)
                    .order_by(desc(DailyPnLRecord.date_utc))
                    .limit(window_days)
                )
            ).scalars().all()
            all_time = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(DailyPnLRecord.pnl_usd), 0.0),
                        func.coalesce(func.sum(DailyPnLRecord.trades_count), 0),
                        func.coalesce(func.sum(DailyPnLRecord.wins), 0),
                        func.coalesce(func.sum(DailyPnLRecord.losses), 0),
                        func.coalesce(func.max(DailyPnLRecord.drawdown_pct), 0.0),
                        func.count(DailyPnLRecord.id),
                    )
                )
            ).one()

        recent_list = list(recent)
        window_pnl = sum(float(r.pnl_usd or 0) for r in recent_list)
        window_trades = sum(int(r.trades_count or 0) for r in recent_list)
        window_wins = sum(int(r.wins or 0) for r in recent_list)
        window_losses = sum(int(r.losses or 0) for r in recent_list)
        window_max_dd = max(
            (float(r.drawdown_pct or 0) for r in recent_list), default=0.0
        )
        latest_equity = float(recent_list[0].ending_equity) if recent_list else 0.0

        all_pnl, all_trades, all_wins, all_losses, all_max_dd, days_total = all_time
        decided = window_wins + window_losses
        win_rate_window = (window_wins / decided) if decided else None
        decided_all = int(all_wins or 0) + int(all_losses or 0)
        win_rate_all = (int(all_wins or 0) / decided_all) if decided_all else None

        return {
            "window_days": window_days,
            "window": {
                "pnl_usd": round(window_pnl, 2),
                "trades": int(window_trades),
                "wins": int(window_wins),
                "losses": int(window_losses),
                "win_rate": win_rate_window,
                "max_drawdown_pct": round(window_max_dd, 4),
                "latest_equity_usd": round(latest_equity, 2),
                "days_with_data": len(recent_list),
            },
            "all_time": {
                "pnl_usd": round(float(all_pnl or 0), 2),
                "trades": int(all_trades or 0),
                "wins": int(all_wins or 0),
                "losses": int(all_losses or 0),
                "win_rate": win_rate_all,
                "max_drawdown_pct": round(float(all_max_dd or 0), 4),
                "trading_days": int(days_total or 0),
            },
        }

    # ------------------------------------------------------------------
    # Performance report upsert / read  (Story 039)
    # ------------------------------------------------------------------

    @staticmethod
    async def save_perf_report(
        date_utc: str,
        verdict: str,
        win_rate_pct: Optional[float],
        total_pnl_usd: float,
        max_drawdown_pct: float,
        wolverine_endorse_pct: Optional[float],
        days_with_data: int,
        payload: Optional[dict] = None,
    ) -> int:
        """Upsert one ``perf_reports`` row for *date_utc* (YYYY-MM-DD).

        If a row already exists for that date it is overwritten
        (delete-then-insert) so the unique index is never violated.
        Returns the id of the saved row.
        """
        async with get_session() as session:
            existing = (
                await session.execute(
                    select(PerfReportRecord).where(
                        PerfReportRecord.date_utc == date_utc
                    )
                )
            ).scalar_one_or_none()

            if existing is not None:
                await session.delete(existing)
                await session.flush()

            rec = PerfReportRecord(
                date_utc=date_utc,
                verdict=verdict,
                win_rate_pct=win_rate_pct,
                total_pnl_usd=total_pnl_usd,
                max_drawdown_pct=max_drawdown_pct,
                wolverine_endorse_pct=wolverine_endorse_pct,
                days_with_data=days_with_data,
                payload=payload,
            )
            session.add(rec)
            await session.commit()
            await session.refresh(rec)
            return rec.id

    @staticmethod
    async def get_latest_perf_report() -> Optional[PerfReportRecord]:
        """Return the most recently written ``PerfReportRecord`` or *None*."""
        async with get_session() as session:
            row = (
                await session.execute(
                    select(PerfReportRecord)
                    .order_by(desc(PerfReportRecord.date_utc))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return row

    @staticmethod
    async def get_overview() -> dict:
        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        async with get_session() as session:
            total_signals = (
                await session.execute(select(func.count(SignalRecord.id)))
            ).scalar_one()
            total_trades = (
                await session.execute(select(func.count(TradeRecord.id)))
            ).scalar_one()
            trades_today = (
                await session.execute(
                    select(func.count(TradeRecord.id)).where(
                        TradeRecord.timestamp >= today_start
                    )
                )
            ).scalar_one()
            executions_today = (
                await session.execute(
                    select(func.count(TradeRecord.id)).where(
                        TradeRecord.timestamp >= today_start,
                        TradeRecord.status.in_(["FILLED", "PARTIAL", "PAPER"]),
                    )
                )
            ).scalar_one()

        return {
            "timestamp": now_utc.isoformat(),
            "total_signals": int(total_signals or 0),
            "total_trades": int(total_trades or 0),
            "trades_today": int(trades_today or 0),
            "executions_today": int(executions_today or 0),
        }
