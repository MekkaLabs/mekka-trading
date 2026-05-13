"""
src/services/daily_performance_writer.py
========================================
Story 039 — DailyPerformanceWriter

Runs Deadpool once per UTC calendar day, persists the result as a
``PerfReportRecord`` in the ``perf_reports`` table (upsert semantics),
and emits a ``DAILY_PERF_REPORT`` audit event so the full payload is
queryable via the audit log.

Design notes
------------
* **One run per day**: the writer tracks ``_last_run_date`` (a
  ``datetime.date`` in UTC). Calling ``maybe_run()`` from Nick Fury's
  main loop is safe — it is a no-op if today's report has already been
  written.
* **Standalone / async-safe**: can also be called directly via
  ``await writer.run_now()`` to force a fresh report regardless of
  the date gate.
* **Deadpool sentinel**: module-level ``Deadpool = None`` allows
  ``patch("src.services.daily_performance_writer.Deadpool")`` in tests
  without real-DB setup.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patchable sentinel — replaced by lazy import inside methods so tests
# can patch 'src.services.daily_performance_writer.Deadpool'.
# ---------------------------------------------------------------------------
Deadpool = None  # type: ignore[assignment]

_EVENT_NAME = "DAILY_PERF_REPORT"


class DailyPerformanceWriter:
    """Writes one Deadpool PerformanceReport to the DB per UTC day.

    Parameters
    ----------
    repo:
        A ``MekkaRepository`` class (or compatible duck-type). Defaults to
        ``MekkaRepository`` imported lazily on first use so that tests can
        avoid any DB setup when they supply their own repo.
    window_days:
        Look-back window forwarded to ``Deadpool.run()``. Default 30.
    """

    NAME = "DailyPerformanceWriter"

    def __init__(self, repo=None, *, window_days: int = 30) -> None:
        self._repo = repo
        self._window_days = window_days
        self._last_run_date: Optional[date] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def maybe_run(self) -> bool:
        """Run Deadpool and persist the report **only if not done today**.

        Returns ``True`` if a new report was written, ``False`` if today's
        report already existed (skipped).
        """
        today = datetime.now(timezone.utc).date()
        if self._last_run_date == today:
            logger.debug("[%s] already ran today (%s) — skipping", self.NAME, today)
            return False

        await self.run_now(today=today)
        return True

    async def run_now(self, *, today: Optional[date] = None) -> None:
        """Force a Deadpool run and persist the result unconditionally.

        This bypasses the date gate — useful for testing or manual triggers.
        """
        if today is None:
            today = datetime.now(timezone.utc).date()

        date_str = today.strftime("%Y-%m-%d")
        repo = self._repo_instance()

        logger.info("[%s] running Deadpool for %s (window=%dd)", self.NAME, date_str, self._window_days)

        _Deadpool = Deadpool
        if _Deadpool is None:
            from src.agents.deadpool import Deadpool as _Deadpool  # type: ignore[assignment]

        dp = _Deadpool(repo=repo)
        report = await dp.run(window_days=self._window_days)

        # Persist to perf_reports table (upsert)
        rec_id = await repo.save_perf_report(
            date_utc=date_str,
            verdict=report.verdict.value,
            win_rate_pct=report.win_rate_pct,
            total_pnl_usd=report.total_pnl_usd,
            max_drawdown_pct=report.max_drawdown_pct,
            wolverine_endorse_pct=report.wolverine_sl_endorse_rate_pct,
            days_with_data=report.days_with_data,
            payload=report.to_audit_payload(),
        )

        # Emit audit event
        await repo.log_event(
            agent=self.NAME,
            event=_EVENT_NAME,
            message=f"verdict={report.verdict.value} win_rate={report.win_rate_pct} pnl={report.total_pnl_usd}",
            severity="INFO",
            payload=report.to_audit_payload(),
        )

        self._last_run_date = today
        logger.info(
            "[%s] report persisted id=%s verdict=%s",
            self.NAME,
            rec_id,
            report.verdict.value,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _repo_instance(self):
        """Return the configured repo, lazy-importing default if needed."""
        if self._repo is not None:
            return self._repo
        from src.persistence.repository import MekkaRepository
        return MekkaRepository
