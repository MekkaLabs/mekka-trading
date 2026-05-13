"""
src/agents/deadpool.py
======================
Deadpool — Performance Analytics Agent (Story 034)

Deadpool reads from the SQLite database and computes a PerformanceReport
that summarises trading behaviour over a rolling window (default 30 days).

Unlike the LLM-powered agents, Deadpool is deterministic and purely
computational — it never calls an LLM. Think of it as the "quant desk"
that evaluates whether the AI squad is actually performing.

Metrics computed
----------------
- Trade win-rate, total PnL, avg daily PnL, max drawdown
- Sharpe estimate (daily returns / std-dev × √252)
- Wolverine SL endorsement rate — proportion of MONITOR_RECOVERY_PLAN
  audit rows where every position recommendation is HOLD (i.e., Wolverine
  found nothing to rescue). This is a proxy for "positions are healthy".
- Signal actionable rate — proportion of signals where is_actionable=True
- Batman approval rate — proportion of signals where confidence ≥ threshold
  (approximated via is_actionable AND NOT fallback)
- Per-symbol breakdown (top 3 and bottom 3 by PnL)

Verdict logic
-------------
INSUFFICIENT_DATA  — fewer than MIN_DAYS_REQUIRED days with trades
NOT_READY          — any of:
                       win_rate < 45%
                       max_drawdown > 15%
                       signal_actionable_rate < 50%
READY              — all thresholds passed

Usage
-----
    from src.agents.deadpool import Deadpool
    from src.persistence.repository import MekkaRepository

    repo = MekkaRepository()
    report = await Deadpool(repo).run(window_days=30)
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger

from src.models.performance import (
    PerformanceReport,
    PerformanceVerdict,
    SymbolStats,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MIN_DAYS_REQUIRED: int = 7          # minimum trading days before READY/NOT_READY
MIN_WIN_RATE_PCT: float = 45.0      # below this → NOT_READY
MAX_DRAWDOWN_PCT: float = 15.0      # above this → NOT_READY
MIN_ACTIONABLE_RATE_PCT: float = 50.0  # below this → NOT_READY


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Deadpool:
    """
    Deadpool — deterministic performance analyser.

    Parameters
    ----------
    repo :
        A ``MekkaRepository`` instance (or duck-typed object with the same
        async static methods). Injected so tests can pass a fake.
    """

    NAME = "Deadpool"

    def __init__(self, repo) -> None:  # type: ignore[annotation]
        self._repo = repo

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, window_days: int = 30) -> PerformanceReport:
        """Compute and return a PerformanceReport for the given window."""
        logger.info(f"[{self.NAME}] Computing performance report (window={window_days}d)")

        daily_rows = await self._repo.list_recent_daily_pnl(limit=window_days)
        trade_rows = await self._repo.list_recent_trades(limit=5000)
        signal_rows = await self._repo.list_recent_signals(limit=5000)
        audit_rows = await self._repo.list_audit_by_event(
            "MONITOR_RECOVERY_PLAN", limit=2000
        )

        report = self._compute(
            window_days=window_days,
            daily_rows=daily_rows,
            trade_rows=trade_rows,
            signal_rows=signal_rows,
            audit_rows=audit_rows,
        )

        logger.info(
            f"[{self.NAME}] Report generated: verdict={report.verdict} "
            f"days={report.days_with_data} trades={report.total_trades} "
            f"win_rate={report.win_rate_pct}"
        )
        return report

    # ------------------------------------------------------------------
    # Core computation (sync, easily unit-testable)
    # ------------------------------------------------------------------

    def _compute(
        self,
        *,
        window_days: int,
        daily_rows: list,
        trade_rows: list,
        signal_rows: list,
        audit_rows: list,
    ) -> PerformanceReport:
        notes: List[str] = []

        # ---- Daily-level aggregates ----------------------------------
        days_with_data = len(daily_rows)
        total_pnl = sum(float(r.pnl_usd or 0) for r in daily_rows)
        avg_daily_pnl = total_pnl / days_with_data if days_with_data else 0.0
        max_drawdown = max(
            (float(r.drawdown_pct or 0) for r in daily_rows), default=0.0
        )
        total_wins = sum(int(r.wins or 0) for r in daily_rows)
        total_losses = sum(int(r.losses or 0) for r in daily_rows)
        total_trades = sum(int(r.trades_count or 0) for r in daily_rows)

        decided = total_wins + total_losses
        win_rate_pct: Optional[float] = (
            round(100.0 * total_wins / decided, 2) if decided else None
        )

        # ---- Sharpe estimate -----------------------------------------
        # Use pnl_pct (daily return as fraction of equity) — scale-invariant
        # and comparable across account sizes.  pnl_usd would give different
        # Sharpe values for the same strategy run at different equity levels.
        # Annualised with sqrt(252) trading-day convention.
        sharpe_estimate: Optional[float] = None
        if days_with_data >= 5:
            daily_returns = [float(r.pnl_pct or 0) for r in daily_rows]
            mean_r = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
            std_r = math.sqrt(variance)
            if std_r > 0:
                sharpe_estimate = round((mean_r / std_r) * math.sqrt(252), 4)

        # ---- Wolverine SL endorsement rate ---------------------------
        wolverine_sl_endorse_rate_pct = self._wolverine_endorse_rate(audit_rows, notes)

        # ---- Signal actionable rate ----------------------------------
        signal_actionable_rate_pct: Optional[float] = None
        if signal_rows:
            actionable = sum(1 for s in signal_rows if s.is_actionable)
            signal_actionable_rate_pct = round(
                100.0 * actionable / len(signal_rows), 2
            )

        # ---- Batman approval rate ------------------------------------
        # Approximation: non-fallback actionable signals were batman-approved.
        batman_approval_rate_pct: Optional[float] = None
        if signal_rows:
            approved = sum(
                1 for s in signal_rows
                if s.is_actionable and not s.fallback
            )
            batman_approval_rate_pct = round(
                100.0 * approved / len(signal_rows), 2
            )

        # ---- Per-symbol breakdown ------------------------------------
        top_symbols, bottom_symbols = self._symbol_breakdown(trade_rows)

        # ---- Verdict -------------------------------------------------
        verdict, verdict_notes = self._decide_verdict(
            days_with_data=days_with_data,
            win_rate_pct=win_rate_pct,
            max_drawdown_pct=max_drawdown,
            signal_actionable_rate_pct=signal_actionable_rate_pct,
        )
        notes.extend(verdict_notes)

        return PerformanceReport(
            window_days=window_days,
            days_with_data=days_with_data,
            total_trades=total_trades,
            wins=total_wins,
            losses=total_losses,
            win_rate_pct=win_rate_pct,
            total_pnl_usd=round(total_pnl, 4),
            avg_daily_pnl_usd=round(avg_daily_pnl, 4),
            max_drawdown_pct=round(max_drawdown, 4),
            sharpe_estimate=sharpe_estimate,
            wolverine_sl_endorse_rate_pct=wolverine_sl_endorse_rate_pct,
            signal_actionable_rate_pct=signal_actionable_rate_pct,
            batman_approval_rate_pct=batman_approval_rate_pct,
            top_symbols=top_symbols,
            bottom_symbols=bottom_symbols,
            verdict=verdict,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wolverine_endorse_rate(
        audit_rows: list,
        notes: List[str],
    ) -> Optional[float]:
        """
        Parse MONITOR_RECOVERY_PLAN audit payloads and compute the
        fraction of cycles where every position was recommended HOLD.

        A "full endorsement" cycle = all PositionUpdate.action == HOLD.
        Returns None if no recovery-plan audit rows exist.
        """
        if not audit_rows:
            notes.append("No MONITOR_RECOVERY_PLAN audit rows found — Wolverine not run yet.")
            return None

        endorsed = 0
        total_cycles = 0

        for row in audit_rows:
            try:
                payload_raw = row.payload
                if payload_raw is None:
                    continue
                if isinstance(payload_raw, str):
                    payload = json.loads(payload_raw)
                else:
                    payload = payload_raw

                positions = payload.get("positions", [])
                if not positions:
                    # Empty positions list → nothing to rescue → counts as endorsement
                    endorsed += 1
                    total_cycles += 1
                    continue

                all_hold = all(
                    p.get("action", "HOLD") == "HOLD" for p in positions
                )
                if all_hold:
                    endorsed += 1
                total_cycles += 1

            except (json.JSONDecodeError, AttributeError, TypeError):
                continue

        if total_cycles == 0:
            notes.append("MONITOR_RECOVERY_PLAN payloads present but could not be parsed.")
            return None

        return round(100.0 * endorsed / total_cycles, 2)

    @staticmethod
    def _symbol_breakdown(
        trade_rows: list,
    ) -> tuple[List[SymbolStats], List[SymbolStats]]:
        """Return top-3 and bottom-3 symbols by total PnL."""
        sym_pnl: dict[str, float] = defaultdict(float)
        sym_trades: dict[str, int] = defaultdict(int)
        sym_wins: dict[str, int] = defaultdict(int)
        sym_losses: dict[str, int] = defaultdict(int)

        for row in trade_rows:
            sym = getattr(row, "symbol", None) or "UNKNOWN"
            pnl = float(getattr(row, "pnl_usd", 0) or 0)
            status = (getattr(row, "status", "") or "").upper()
            sym_pnl[sym] += pnl
            sym_trades[sym] += 1
            if status in ("FILLED", "PAPER"):
                if pnl > 0:
                    sym_wins[sym] += 1
                elif pnl < 0:
                    sym_losses[sym] += 1

        all_stats: List[SymbolStats] = []
        for sym in sym_pnl:
            wins = sym_wins[sym]
            losses = sym_losses[sym]
            decided = wins + losses
            wr = round(100.0 * wins / decided, 2) if decided else None
            all_stats.append(
                SymbolStats(
                    symbol=sym,
                    trades=sym_trades[sym],
                    wins=wins,
                    losses=losses,
                    win_rate_pct=wr,
                    total_pnl_usd=round(sym_pnl[sym], 4),
                )
            )

        sorted_by_pnl = sorted(all_stats, key=lambda s: s.total_pnl_usd, reverse=True)
        top = sorted_by_pnl[:3]
        bottom = sorted_by_pnl[-3:] if len(sorted_by_pnl) > 3 else []
        return top, bottom

    @staticmethod
    def _decide_verdict(
        *,
        days_with_data: int,
        win_rate_pct: Optional[float],
        max_drawdown_pct: float,
        signal_actionable_rate_pct: Optional[float],
    ) -> tuple[PerformanceVerdict, List[str]]:
        notes: List[str] = []

        if days_with_data < MIN_DAYS_REQUIRED:
            notes.append(
                f"Only {days_with_data} trading day(s) of data — "
                f"need ≥{MIN_DAYS_REQUIRED} for a reliable verdict."
            )
            return PerformanceVerdict.INSUFFICIENT_DATA, notes

        failures: List[str] = []

        if win_rate_pct is None:
            notes.append("No decided trades (wins+losses=0); win-rate unknown.")
        elif win_rate_pct < MIN_WIN_RATE_PCT:
            failures.append(
                f"Win rate {win_rate_pct:.1f}% < required {MIN_WIN_RATE_PCT:.1f}%"
            )

        if max_drawdown_pct > MAX_DRAWDOWN_PCT:
            failures.append(
                f"Max drawdown {max_drawdown_pct:.2f}% > allowed {MAX_DRAWDOWN_PCT:.2f}%"
            )

        if signal_actionable_rate_pct is not None:
            if signal_actionable_rate_pct < MIN_ACTIONABLE_RATE_PCT:
                failures.append(
                    f"Signal actionable rate {signal_actionable_rate_pct:.1f}% "
                    f"< required {MIN_ACTIONABLE_RATE_PCT:.1f}%"
                )

        if failures:
            notes.extend(failures)
            return PerformanceVerdict.NOT_READY, notes

        notes.append("All performance thresholds met.")
        return PerformanceVerdict.READY, notes
