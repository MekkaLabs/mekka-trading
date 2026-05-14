"""
src/models/performance.py
=========================
Pydantic models for Deadpool — the performance analytics agent (Story 034).

Deadpool reads from the SQLite database and computes a PerformanceReport
that summarises how the system has been behaving over a rolling window.
The report drives gate H2 (minimum win-rate / drawdown), H3 (signal
actionability) and surfaces Wolverine SL endorsement data for H1.

PerformanceVerdict tells the operator at a glance whether the system is
performing within the thresholds required before mainnet authorisation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.utils.time import utc_now


class PerformanceVerdict(str, Enum):
    """Top-level assessment returned by Deadpool."""

    READY = "READY"                        # all thresholds met
    NOT_READY = "NOT_READY"                # one or more thresholds failed
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # fewer than MIN_DAYS days of data


class SymbolStats(BaseModel):
    """Per-symbol breakdown included in the report."""

    symbol: str
    trades: int = Field(..., ge=0)
    wins: int = Field(default=0, ge=0)
    losses: int = Field(default=0, ge=0)
    win_rate_pct: Optional[float] = Field(default=None)  # None when no decided trades
    total_pnl_usd: float = Field(default=0.0)

    @property
    def decided(self) -> int:
        return self.wins + self.losses


class PerformanceReport(BaseModel):
    """
    Full performance summary produced by Deadpool.

    All rate fields are expressed as percentages (0–100), not fractions.
    """

    # ---- Window info --------------------------------------------------
    window_days: int = Field(..., ge=1)
    days_with_data: int = Field(..., ge=0)   # days that have ≥1 trade

    # ---- Trade metrics ------------------------------------------------
    total_trades: int = Field(..., ge=0)
    wins: int = Field(default=0, ge=0)
    losses: int = Field(default=0, ge=0)
    win_rate_pct: Optional[float] = Field(default=None)   # None = no decided trades

    # ---- P&L metrics --------------------------------------------------
    total_pnl_usd: float = Field(default=0.0)
    avg_daily_pnl_usd: float = Field(default=0.0)
    max_drawdown_pct: float = Field(default=0.0, ge=0.0)
    sharpe_estimate: Optional[float] = Field(default=None)  # None = insufficient data

    # ---- Story 062 — advanced metrics ---------------------------------
    # Sortino ratio: like Sharpe but penalises only downside volatility.
    sortino_estimate: Optional[float] = Field(default=None)

    # Trade-level consecutive streaks (positive wins / negative = losses).
    max_winning_streak: int = Field(default=0, ge=0)
    max_losing_streak: int = Field(default=0, ge=0)
    # current_streak > 0 = N consecutive wins; < 0 = N consecutive losses.
    current_streak: int = Field(default=0)

    # Expectancy = win_rate × avg_win − loss_rate × avg_loss (USD per trade).
    expectancy_usd: Optional[float] = Field(default=None)
    avg_win_usd: Optional[float] = Field(default=None)
    avg_loss_usd: Optional[float] = Field(default=None)  # stored as positive number

    # ---- Agent-quality metrics ----------------------------------------
    # Wolverine: proportion of MONITOR_RECOVERY_PLAN cycles where action == HOLD
    # (proxy for "Wolverine agrees the position is healthy and doesn't need rescue").
    wolverine_sl_endorse_rate_pct: Optional[float] = Field(default=None)

    # Vision: proportion of signals where is_actionable=True
    signal_actionable_rate_pct: Optional[float] = Field(default=None)

    # Batman: proportion of signals that Batman approved (confidence >= threshold)
    batman_approval_rate_pct: Optional[float] = Field(default=None)

    # ---- Per-symbol breakdown ----------------------------------------
    top_symbols: List[SymbolStats] = Field(default_factory=list)
    bottom_symbols: List[SymbolStats] = Field(default_factory=list)

    # ---- Verdict ------------------------------------------------------
    verdict: PerformanceVerdict = Field(default=PerformanceVerdict.INSUFFICIENT_DATA)
    notes: List[str] = Field(default_factory=list)

    # ---- Metadata -----------------------------------------------------
    generated_at: datetime = Field(default_factory=utc_now)

    def to_audit_payload(self) -> dict:
        return self.model_dump(mode="json")
