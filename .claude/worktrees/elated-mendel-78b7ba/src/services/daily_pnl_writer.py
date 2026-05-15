"""
src/services/daily_pnl_writer.py
================================
Daily PnL writer service (Story 027).

Closes the semantic loop where Batman reads `get_today_drawdown_pct()`
from `daily_pnl` but no agent ever wrote to it. After Story 027, every
main cycle ends with a call to `DailyPnLWriter.record_cycle(...)` which
upserts a row keyed by UTC date.

Design notes
------------
- This is a **service**, not an agent. No Marvel codename, no LLM,
  no decision-making. It only watches and records.
- Peak equity is held in instance memory (resets on process restart).
  Drawdown is computed against that peak. If the process restarts
  mid-day, peak is rebuilt from the current equity (drawdown floor 0
  until equity drops below the new peak). Acceptable v1 trade-off;
  the stored row in SQLite is authoritative for `Batman`.
- Wins / losses for paper trades are not yet computed (paper trades
  are entry orders; closes happen later). For now both stay at 0 and
  Wolverine (Story 028) will fill them when monitoring SL/TP exits.
- `is_paper` follows `settings.paper_trading`.
- The writer is **idempotent** within the same UTC day: calling
  `record_cycle` twice updates the existing row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from src.config.settings import settings
from src.models.portfolio import EquitySnapshot
from src.persistence.repository import MekkaRepository
from src.utils.time import utc_today_iso


def _today_utc() -> str:
    """Return today's UTC date as YYYY-MM-DD.

    Kept as a thin wrapper around `utils.time.utc_today_iso` so tests
    can monkeypatch it locally without affecting the global helper.
    """
    return utc_today_iso()


@dataclass
class _DayState:
    """In-memory tracking for the current UTC day. Internal-only."""

    date_utc: str
    starting_equity: float
    peak_equity: float
    cycles_observed: int = 0


class DailyPnLSnapshot(BaseModel):
    """
    Pydantic model returned by `DailyPnLWriter.record_cycle`.

    Story 028 promoted this from `@dataclass` so it serializes uniformly
    with the rest of the contract layer.
    """

    schema_version: int = Field(default=1, description="Schema version")
    date_utc: str
    starting_equity: float
    ending_equity: float
    peak_equity: float
    pnl_usd: float
    pnl_pct: float
    drawdown_pct: float
    trades_count: int
    is_paper: bool

    def summary(self) -> str:
        return (
            f"[DailyPnL] {self.date_utc} "
            f"pnl=${self.pnl_usd:+,.2f} ({self.pnl_pct:+.2%}) "
            f"dd={self.drawdown_pct:.2%} "
            f"trades={self.trades_count} "
            f"start=${self.starting_equity:,.2f} "
            f"peak=${self.peak_equity:,.2f} "
            f"end=${self.ending_equity:,.2f}"
        )

    def to_audit_payload(self) -> dict:
        """Serialize for `audit_log.payload`."""
        return self.model_dump(mode="json")


class DailyPnLWriter:
    """
    Service that records daily PnL aggregates per UTC day.

    Usage:
        writer = DailyPnLWriter()
        # at the end of every Nick Fury cycle:
        result = await writer.record_cycle(snapshot, trades_count_today=N)
    """

    def __init__(self) -> None:
        self._state: Optional[_DayState] = None
        self._log = logger.bind(agent="DailyPnLWriter")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_cycle(
        self,
        equity_usd: float,
        trades_count_today: int,
        wins: int = 0,
        losses: int = 0,
        snapshot: Optional[EquitySnapshot] = None,
    ) -> DailyPnLSnapshot:
        """
        Persist (upsert) the day's PnL row.

        Parameters
        ----------
        equity_usd         : Effective equity (CLI override or snapshot value).
                             This is what gets recorded as ending_equity.
        trades_count_today : Count from Repository.count_trades_today()
        wins, losses       : Optional aggregate counts (default 0; Wolverine
                             will fill these in Story 028)
        snapshot           : Optional reference to the underlying EquitySnapshot
                             (kept for forward compatibility / debugging).
        """
        _ = snapshot  # currently unused; reserved for richer accounting later
        today = _today_utc()
        equity = float(equity_usd or 0.0)

        # Day rollover or first call ever — reset in-memory state
        if self._state is None or self._state.date_utc != today:
            self._state = _DayState(
                date_utc=today,
                starting_equity=equity,
                peak_equity=equity,
            )

        # Update peak (monotonic during the day)
        if equity > self._state.peak_equity:
            self._state.peak_equity = equity
        self._state.cycles_observed += 1

        starting = self._state.starting_equity
        peak = self._state.peak_equity

        pnl_usd = equity - starting
        pnl_pct = (pnl_usd / starting) if starting > 0 else 0.0
        drawdown_pct = ((peak - equity) / peak) if peak > 0 and equity < peak else 0.0

        # Persist via repository (idempotent upsert)
        try:
            await MekkaRepository.upsert_daily_pnl(
                date_utc=today,
                is_paper=settings.paper_trading,
                ending_equity=equity,
                pnl_usd=round(pnl_usd, 6),
                pnl_pct=round(pnl_pct, 6),
                drawdown_pct=round(drawdown_pct, 6),
                trades_count=int(trades_count_today),
                wins=int(wins),
                losses=int(losses),
                starting_equity=starting,
            )
        except Exception as exc:  # noqa: BLE001
            # Never let a persistence error break the main cycle. Audit
            # the failure and move on; next cycle will retry.
            self._log.error(f"upsert_daily_pnl failed: {exc}")
            try:
                await MekkaRepository.log_event(
                    agent="DailyPnLWriter",
                    event="WRITE_ERROR",
                    severity="ERROR",
                    message=f"upsert_daily_pnl failed: {exc}",
                    payload={"date_utc": today},
                )
            except Exception:
                pass  # noqa: S110

        result = DailyPnLSnapshot(
            date_utc=today,
            starting_equity=round(starting, 6),
            ending_equity=round(equity, 6),
            peak_equity=round(peak, 6),
            pnl_usd=round(pnl_usd, 6),
            pnl_pct=round(pnl_pct, 6),
            drawdown_pct=round(drawdown_pct, 6),
            trades_count=int(trades_count_today),
            is_paper=settings.paper_trading,
        )
        self._log.info(result.summary())
        return result

    # ------------------------------------------------------------------
    # Diagnostics / tests
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Drop in-memory state. Used by tests; not by runtime."""
        self._state = None

    @property
    def current_state(self) -> Optional[_DayState]:
        """Read the current in-memory day state (None before first cycle)."""
        return self._state
