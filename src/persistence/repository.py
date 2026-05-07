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
