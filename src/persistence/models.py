"""
src/persistence/models.py
=========================
SQLAlchemy 2.x ORM models for the Mekka Trading SQLite store.

Tables
------
  signals      — every TradingSignal Vision produced (whether traded or not)
  trades       — every ExecutionResult Iron Man produced
  daily_pnl    — daily aggregate PnL/drawdown (one row per UTC day)
  audit_log    — append-only events from any agent (for replay/forensics)
  perf_reports — daily Deadpool PerformanceReport snapshots (one per UTC day)

All columns use UTC timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all Mekka ORM models."""


class SignalRecord(Base):
    """One row per TradingSignal emitted by Vision."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    size_pct: Mapped[float] = mapped_column(Float)
    leverage: Mapped[int] = mapped_column(Integer)
    risk_reward: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class TradeRecord(Base):
    """One row per ExecutionResult emitted by Iron Man."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    signal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16))
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    side: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    notional_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sl_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tp_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DailyPnLRecord(Base):
    """One row per UTC day per environment (paper vs live).

    The unique constraint is on (date_utc, is_paper) so that paper and live
    trading can both have records on the same day.  The previous single-column
    unique=True on date_utc would cause an IntegrityError when switching from
    paper to live mid-day.

    Migration note: if upgrading an existing DB, run:
      ALTER TABLE daily_pnl DROP CONSTRAINT IF EXISTS uq_daily_pnl_date;
      CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_pnl_date_paper
          ON daily_pnl (date_utc, is_paper);
    """

    __tablename__ = "daily_pnl"
    __table_args__ = (
        UniqueConstraint("date_utc", "is_paper", name="uq_daily_pnl_date_paper"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date_utc: Mapped[str] = mapped_column(String(10), index=True)  # 'YYYY-MM-DD'
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    starting_equity: Mapped[float] = mapped_column(Float, default=0.0)
    ending_equity: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)


class AuditRecord(Base):
    """Append-only audit log for any agent event of interest."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    agent: Mapped[str] = mapped_column(String(32), index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="INFO")
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class PerfReportRecord(Base):
    """
    Daily Deadpool PerformanceReport snapshot (one row per UTC day).

    Written by DailyPerformanceWriter (Story 039). The ``date_utc`` column
    is the write date; if two writes happen on the same day the second
    overwrites the first (upsert semantics in DailyPerformanceWriter).
    ``payload`` stores the full ``PerformanceReport.to_audit_payload()`` dict.
    """

    __tablename__ = "perf_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date_utc: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # YYYY-MM-DD
    verdict: Mapped[str] = mapped_column(String(24))
    win_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    wolverine_endorse_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    days_with_data: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
