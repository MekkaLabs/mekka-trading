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
        pnl_quote: Optional[float] = None,
        quote_currency: Optional[str] = None,
    ) -> int:
        """Persist an ExecutionResult and return its DB id.

        P0-6 (2026-05-28 audit): quote_currency e pnl_quote agora populados.
        Em COIN-M (inverse), pnl_quote vem em BTC/ETH e pnl_usd é a
        conversão via mark price. Em USDT-M (linear), pnl_quote == pnl_usd
        e quote_currency == 'USDT'. Default detector usa active_exchange
        + binance_market_type quando o caller não passa explícito.
        """
        # Derive quote_currency from current settings se não passado pelo caller
        if quote_currency is None:
            try:
                from src.config.settings import settings  # noqa: WPS433
                if settings.active_exchange == "hyperliquid":
                    quote_currency = "USDC"
                elif (settings.active_exchange == "binance"
                      and str(getattr(settings, "binance_market_type", "linear")) == "inverse"):
                    # Em inverse, quote_currency é o coin do par (BTC, ETH)
                    quote_currency = str(execution.symbol).upper().strip()
                else:
                    quote_currency = "USDT"
            except Exception:  # noqa: BLE001
                quote_currency = "USDT"  # safe default

        # Em linear, pnl_quote == pnl_usd se não foi explicitamente passado
        # (mantém histórico consistente sem caller precisar duplicar).
        if pnl_quote is None and pnl_usd is not None and quote_currency in ("USDT", "USDC"):
            pnl_quote = pnl_usd

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
            pnl_quote=pnl_quote,
            quote_currency=quote_currency,
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
        peak_equity_usd: Optional[float] = None,
    ) -> int:
        """Insert or update the row for a given UTC date.

        ``peak_equity_usd`` is the highest equity seen during the day.
        Persisting it ensures that a process restart does not reset the
        drawdown calculation and hide intra-day losses from Batman.
        """
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
                    peak_equity_usd=peak_equity_usd or ending_equity,
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
            # Only update peak if the new value is higher — never lower.
            if peak_equity_usd and peak_equity_usd > (existing.peak_equity_usd or 0.0):
                existing.peak_equity_usd = peak_equity_usd
            await session.commit()
            return existing.id

    @staticmethod
    async def get_today_peak_equity() -> float:
        """Read today's persisted peak_equity_usd, or 0.0 if no row yet.

        Called at NickFury startup to restore the drawdown baseline after a
        process restart mid-day, preventing Batman from reading drawdown_pct=0
        when real intra-day losses have already occurred.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with get_session() as session:
            row = (
                await session.execute(
                    select(DailyPnLRecord.peak_equity_usd).where(
                        DailyPnLRecord.date_utc == today
                    )
                )
            ).scalar_one_or_none()
            return float(row) if row else 0.0

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
    async def get_today_pnl_usd() -> float:
        """Return today's cumulative realized PnL in USD. Story 067."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with get_session() as session:
            row = (
                await session.execute(
                    select(DailyPnLRecord.pnl_usd).where(
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
    async def update_trade_sl_tp(
        symbol: str,
        new_sl: float,
        new_tp: Optional[float] = None,
    ) -> int:
        """Update SL/TP in the raw metadata of open paper trades for a symbol.

        Cyclops reads SL/TP from ``raw["metadata"]["stop_loss"]`` and
        ``raw["metadata"]["take_profit"]``. Calling this method causes the new
        stop price to be honoured on the next Cyclops monitor cycle without any
        other changes to the position.

        Returns the count of trade records updated.
        """
        updated = 0
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(TradeRecord.symbol == symbol)
                    .where(TradeRecord.is_paper == True)  # noqa: E712
                    .where(TradeRecord.status.in_(["FILLED", "PAPER"]))
                )
            ).scalars().all()
            for row in rows:
                raw: dict = dict(row.raw or {})
                meta: dict = dict(raw.get("metadata") or {})
                meta["stop_loss"] = new_sl
                if new_tp is not None:
                    meta["take_profit"] = new_tp
                raw["metadata"] = meta
                row.raw = raw
                updated += 1
            if updated:
                await session.commit()
        return updated

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

    @staticmethod
    async def list_audit_events(
        agent: str,
        event: str,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Story 249 — Decision Memory: retorna eventos de auditoria filtrados.

        Filtra AuditRecord por agent + event (e opcionalmente symbol),
        mais recentes primeiro. Retorna lista de dicts com chaves:
        ``id``, ``agent``, ``event``, ``message``, ``symbol``, ``payload``, ``timestamp``.
        """
        async with get_session() as session:
            stmt = (
                select(AuditRecord)
                .where(AuditRecord.agent == agent)
                .where(AuditRecord.event == event)
            )
            if symbol is not None:
                stmt = stmt.where(AuditRecord.symbol == symbol)
            stmt = stmt.order_by(desc(AuditRecord.timestamp)).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

        result: list[dict] = []
        for row in rows:
            payload = row.payload
            if isinstance(payload, str):
                try:
                    import json as _json  # noqa: WPS433
                    payload = _json.loads(payload)
                except Exception:  # noqa: BLE001
                    payload = {}
            result.append(
                {
                    "id": row.id,
                    "agent": row.agent,
                    "event": row.event,
                    "message": row.message,
                    "symbol": row.symbol,
                    "payload": payload,
                    "timestamp": row.timestamp,
                }
            )
        return result

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
    async def get_closed_trades_since(since: datetime) -> list[TradeRecord]:
        """Trades with pnl_usd realized (closed) since ``since``, oldest-first.

        Used by Beast for self-improvement analysis (win rate, profit factor,
        per-symbol breakdown). Treats a row as "closed" when pnl_usd is
        populated (set by Cyclops at SL/TP trigger or dashboard manual close).
        Before this method existed, Beast silently swallowed the AttributeError
        and produced 0 proposals — the agente of "self-improvement" was inerte.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(TradeRecord.timestamp >= since)
                    .where(TradeRecord.pnl_usd.is_not(None))
                    .order_by(TradeRecord.timestamp.asc())
                )
            ).scalars().all()
            return list(rows)

    @staticmethod
    async def get_events_since(
        agent: Optional[str] = None,
        event: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> list[AuditRecord]:
        """Audit events filtered by agent/event/since, oldest-first.

        Used by Beast (Batman gate counts, ProfessorX cycle latency) and
        any future analyst that needs raw audit rows scoped by agent +
        event + time window. All filters are optional; passing none returns
        the full audit_log (be careful in prod — table grows fast).
        """
        async with get_session() as session:
            stmt = select(AuditRecord)
            if agent:
                stmt = stmt.where(AuditRecord.agent == agent)
            if event:
                stmt = stmt.where(AuditRecord.event == event)
            if since is not None:
                stmt = stmt.where(AuditRecord.timestamp >= since)
            stmt = stmt.order_by(AuditRecord.timestamp.asc())
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)

    # ------------------------------------------------------------------
    # Story 069 — Re-entry cooldown: last Cyclops SL close for symbol
    # ------------------------------------------------------------------

    @staticmethod
    async def get_last_sl_close_time(symbol: str, lookback_minutes: int = 120) -> Optional[datetime]:
        """Return the timestamp of the most recent Cyclops SL-triggered close
        for ``symbol`` within ``lookback_minutes``, or None if no such close exists.

        A Cyclops close is identified by ``raw.metadata.triggered_by == 'cyclops'``
        AND ``raw.metadata.trigger_reason`` containing 'SL'.
        """
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(
                        TradeRecord.symbol == symbol.upper(),
                        TradeRecord.timestamp >= since,
                    )
                    .order_by(desc(TradeRecord.timestamp))
                    .limit(20)
                )
            ).scalars().all()

        for row in rows:
            try:
                raw: dict = row.raw or {}
                meta: dict = raw.get("metadata") or {}
                if meta.get("triggered_by") == "cyclops":
                    reason: str = meta.get("trigger_reason", "")
                    if "SL" in reason or "sl" in reason.lower():
                        return row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                continue
        return None

    # ------------------------------------------------------------------
    # Story 071 — Consecutive SL strike counter per symbol
    # ------------------------------------------------------------------

    @staticmethod
    async def count_consecutive_sl_hits(symbol: str, lookback_trades: int = 20) -> int:
        """Return the number of consecutive Cyclops SL closes at the tail of
        the recent trade history for ``symbol``.

        Walks backwards through the last ``lookback_trades`` Cyclops-tagged
        paper trades for the symbol. Stops as soon as it encounters a trade
        that is NOT an SL close (e.g. TP close, manual close, scale-out).

        Returns 0 if no recent SL closes are found.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(TradeRecord.symbol == symbol.upper())
                    .order_by(desc(TradeRecord.timestamp))
                    .limit(lookback_trades)
                )
            ).scalars().all()

        consecutive = 0
        for row in rows:
            try:
                raw: dict = row.raw or {}
                meta: dict = raw.get("metadata") or {}
                triggered_by = meta.get("triggered_by", "")
                trigger_reason: str = meta.get("trigger_reason", "")
                # Only count closes made by Cyclops via SL (not TP or scale-out)
                if triggered_by == "cyclops" and (
                    "SL" in trigger_reason or "sl" in trigger_reason.lower()
                ):
                    consecutive += 1
                elif triggered_by in ("cyclops", "cyclops_scale_out"):
                    # A TP or scale-out close breaks the SL streak
                    break
                # Non-Cyclops trades (manual, IronMan opens) are ignored and
                # do NOT break the streak — only Cyclops closes count.
            except Exception:  # noqa: BLE001
                continue
        return consecutive

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
    async def count_trades_today_for_symbol(symbol: str) -> int:
        """
        Story 086 — Count FILLED/PAPER trades for symbol in current UTC day.
        Used by Batman gate 3l (max trades per symbol per day).
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with get_session() as session:
            row = (
                await session.execute(
                    select(func.count(TradeRecord.id)).where(
                        TradeRecord.symbol == symbol.upper(),
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.timestamp >= today_start,
                    )
                )
            ).scalar_one()
            return int(row or 0)

    @staticmethod
    async def get_symbol_week_pnl(symbol: str) -> float:
        """
        Story 100 — Sum of realized PnL for symbol in current UTC week (Mon-Sun).
        Returns 0.0 when no trades exist.
        """
        import math as _m  # noqa: WPS433
        from datetime import timedelta  # noqa: WPS433
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord).where(
                        TradeRecord.symbol == symbol.upper(),
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.timestamp >= week_start,
                    )
                )
            ).scalars().all()
        total = 0.0
        for t in rows:
            meta = (t.raw or {}).get("metadata") or {}
            pnl = meta.get("realized_pnl_usd") or meta.get("pnl_usd")
            if pnl is not None:
                try:
                    v = float(pnl)
                    if not _m.isnan(v):
                        total += v
                except (TypeError, ValueError):
                    pass
        return round(total, 4)

    @staticmethod
    async def list_recent_closed_trades(limit: int = 10) -> list[TradeRecord]:
        """
        Stories 102 & 106 — Return the last `limit` FILLED/PAPER trades that
        are "closed" (have a realized_pnl_usd in metadata), newest first.
        Used by Batman gates 3o (consecutive losses) and 3p (directional bias).
        Excludes zero-quantity sentinel trades (quantity > 0).
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.quantity > 0,
                    )
                    .order_by(desc(TradeRecord.timestamp))
                    .limit(limit * 3)  # oversample, then filter for closed
                )
            ).scalars().all()

        # Keep only rows that have a realized_pnl_usd in metadata (= closed trade)
        closed: list[TradeRecord] = []
        for t in rows:
            raw: dict = getattr(t, "raw", {}) or {}
            meta: dict = raw.get("metadata") or {}
            if meta.get("realized_pnl_usd") is not None or meta.get("pnl_usd") is not None:
                closed.append(t)
            if len(closed) >= limit:
                break

        # Attach realized_pnl_usd as an ad-hoc attribute for convenience
        for t in closed:
            raw = getattr(t, "raw", {}) or {}
            meta = raw.get("metadata") or {}
            pnl_val = meta.get("realized_pnl_usd") or meta.get("pnl_usd")
            try:
                object.__setattr__(t, "realized_pnl_usd", float(pnl_val) if pnl_val is not None else None)
            except (TypeError, ValueError, AttributeError):
                pass

        return closed

    @staticmethod
    async def get_monthly_trade_calendar(year: int, month: int) -> list[dict]:
        """
        Story 107 — Returns PnL and trade count grouped by calendar day
        for the given UTC year/month.

        Returns a list of dicts sorted by day:
          [{day, count, pnl_usd, win_count, loss_count}, ...]
        Only days with at least one trade are included.
        """
        import calendar as _cal
        from datetime import datetime, timezone

        _, days_in_month = _cal.monthrange(year, month)
        start_ts = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        end_ts = datetime(year, month, days_in_month, 23, 59, 59, tzinfo=timezone.utc).timestamp()

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.quantity > 0,
                        TradeRecord.timestamp >= start_ts,
                        TradeRecord.timestamp <= end_ts,
                    )
                    .order_by(TradeRecord.timestamp)
                )
            ).scalars().all()

        day_data: dict[int, dict] = {}
        for t in rows:
            ts = getattr(t, "timestamp", None)
            if ts is None:
                continue
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except (ValueError, OSError):
                continue
            day = dt.day
            if day not in day_data:
                day_data[day] = {
                    "day": day,
                    "count": 0,
                    "pnl_usd": 0.0,
                    "win_count": 0,
                    "loss_count": 0,
                }
            day_data[day]["count"] += 1
            pnl_raw = getattr(t, "pnl_usd", None)
            try:
                pnl_val = float(pnl_raw) if pnl_raw is not None else 0.0
            except (TypeError, ValueError):
                pnl_val = 0.0
            day_data[day]["pnl_usd"] = round(day_data[day]["pnl_usd"] + pnl_val, 4)
            if pnl_val > 0:
                day_data[day]["win_count"] += 1
            elif pnl_val < 0:
                day_data[day]["loss_count"] += 1

        return [day_data[d] for d in sorted(day_data.keys())]

    @staticmethod
    async def get_pnl_by_hour(days: int = 30) -> dict:
        """
        Story 109 — Returns PnL statistics grouped by UTC hour (0-23)
        for the last N days.

        Returns a dict keyed by hour string "0".."23":
          {"9": {hour, avg_pnl, total_pnl, count, win_count, loss_count}, ...}
        Only hours with at least one trade are included.
        """
        from datetime import datetime, timezone, timedelta

        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.quantity > 0,
                        TradeRecord.timestamp >= cutoff_ts,
                        TradeRecord.pnl_usd.isnot(None),
                    )
                    .order_by(TradeRecord.timestamp)
                )
            ).scalars().all()

        hour_buckets: dict[int, list[float]] = {h: [] for h in range(24)}
        for t in rows:
            ts = getattr(t, "timestamp", None)
            pnl_raw = getattr(t, "pnl_usd", None)
            if ts is None or pnl_raw is None:
                continue
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                pnl_val = float(pnl_raw)
            except (TypeError, ValueError, OSError):
                continue
            hour_buckets[dt.hour].append(pnl_val)

        result: dict = {}
        for hour, pnls in hour_buckets.items():
            if not pnls:
                continue
            result[str(hour)] = {
                "hour": hour,
                "avg_pnl": round(sum(pnls) / len(pnls), 4),
                "total_pnl": round(sum(pnls), 4),
                "count": len(pnls),
                "win_count": sum(1 for p in pnls if p > 0),
                "loss_count": sum(1 for p in pnls if p < 0),
            }
        return result

    @staticmethod
    async def get_gate_rejections(limit: int = 50) -> list[dict]:
        """
        Story 112 — Returns the last `limit` gate rejection audit events
        logged by Batman under event='GATE_REJECTED'.

        Returns list of:
          [{timestamp_utc, symbol, gate_id, reason, breached}, ...]
        """
        from datetime import datetime, timezone

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(AuditRecord)
                    .where(AuditRecord.event == "GATE_REJECTED")
                    .order_by(desc(AuditRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()

        result: list[dict] = []
        for r in rows:
            payload: dict = getattr(r, "payload", {}) or {}
            ts = getattr(r, "timestamp", None)
            ts_str: str | None = None
            if ts is not None:
                try:
                    if isinstance(ts, (int, float)):
                        ts_str = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
                    else:
                        ts_str = str(ts)
                except Exception:
                    ts_str = str(ts)
            result.append({
                "timestamp_utc": ts_str,
                "symbol": getattr(r, "symbol", None) or payload.get("symbol"),
                "gate_id": payload.get("gate_id", "?"),
                "reason": payload.get("reason") or getattr(r, "message", ""),
                "breached": payload.get("breached", []),
            })
        return result

    @staticmethod
    async def export_signals(limit: int = 5000) -> list[dict]:
        """
        Story 093 — Export all signals as flat dicts for CSV/JSON download.
        """
        async with get_session() as session:
            rows = (
                await session.execute(
                    select(SignalRecord)
                    .order_by(desc(SignalRecord.timestamp))
                    .limit(limit)
                )
            ).scalars().all()
        result: list[dict] = []
        for s in rows:
            raw: dict = s.raw or {}
            result.append({
                "id": s.id,
                "timestamp_utc": s.timestamp.isoformat() if s.timestamp else None,
                "symbol": s.symbol,
                "action": s.action,
                "confidence": s.confidence,
                "entry_price": s.entry_price,
                "stop_loss": raw.get("stop_loss") or (s.raw or {}).get("metadata", {}).get("stop_loss"),
                "take_profit": raw.get("take_profit") or (s.raw or {}).get("metadata", {}).get("take_profit"),
                "risk_reward_ratio": raw.get("risk_reward_ratio"),
                "size_pct": raw.get("size_pct"),
                "leverage": raw.get("leverage"),
                "risk_verdict": raw.get("risk_verdict"),
                "signal_quality_score": raw.get("signal_quality_score"),
            })
        return result

    @staticmethod
    async def export_trades(
        limit: int = 5000,
        status_filter: list[str] | None = None,
    ) -> list[dict]:
        """
        Story 082 — Trade Export.

        Returns all trades as a list of flat dicts ready for CSV/JSON export.
        Fields include everything in TradeRecord plus common metadata keys
        extracted from the raw JSON blob.

        Parameters
        ----------
        limit:
            Maximum rows to return (default 5 000 — safety cap).
        status_filter:
            Optional list of status strings to include (e.g. ["FILLED", "PAPER"]).
            None → all statuses.
        """
        async with get_session() as session:
            q = select(TradeRecord).order_by(desc(TradeRecord.timestamp)).limit(limit)
            if status_filter:
                q = q.where(TradeRecord.status.in_(status_filter))
            rows = (await session.execute(q)).scalars().all()

        result: list[dict] = []
        for t in rows:
            raw: dict = t.raw or {}
            meta: dict = raw.get("metadata") or {}
            result.append({
                "id": t.id,
                "timestamp_utc": t.timestamp.isoformat() if t.timestamp else None,
                "symbol": t.symbol,
                "status": t.status,
                "side": t.side,
                "quantity": t.quantity,
                "avg_price": t.avg_price,
                "is_paper": getattr(t, "is_paper", None),
                "stop_loss": meta.get("stop_loss"),
                "take_profit": meta.get("take_profit"),
                "realized_pnl_usd": meta.get("realized_pnl_usd") or meta.get("pnl_usd"),
                "triggered_by": meta.get("triggered_by"),
                "trigger_reason": meta.get("trigger_reason"),
                "signal_confidence": meta.get("signal_confidence"),
                "signal_action": meta.get("signal_action"),
                "risk_verdict": meta.get("risk_verdict"),
                "notional_usd": round(float(t.quantity or 0) * float(t.avg_price or 0), 4),
            })
        return result

    @staticmethod
    async def list_symbol_stats(lookback_days: int = 90) -> list[dict]:
        """
        Story 079 — Symbol Leaderboard.

        Aggregates closed/filled trades per symbol over the last
        ``lookback_days`` and returns a list of dicts sorted by total_pnl
        descending:

        [
          {
            "symbol": "BTC",
            "trades": 12,
            "wins": 8,
            "losses": 4,
            "win_rate": 0.667,
            "total_pnl_usd": 540.0,
            "avg_pnl_usd": 45.0,
            "best_trade_usd": 210.0,
            "worst_trade_usd": -85.0,
            "sharpe": 1.23,          // None when < 3 trades
          },
          ...
        ]

        Only FILLED / PAPER statuses are counted.  Trades without a
        pnl_usd value are excluded from monetary calculations but still
        count toward the trade total.
        """
        import math as _math  # noqa: WPS433
        from datetime import timedelta  # noqa: WPS433

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(TradeRecord)
                    .where(
                        TradeRecord.status.in_(["FILLED", "PAPER"]),
                        TradeRecord.timestamp >= cutoff,
                    )
                    .order_by(TradeRecord.timestamp)
                )
            ).scalars().all()

        # Group by symbol
        from collections import defaultdict  # noqa: WPS433
        by_sym: dict[str, list[float]] = defaultdict(list)  # symbol → [pnl values]
        for t in rows:
            sym = (t.symbol or "?").upper()
            raw = t.raw or {}
            meta = raw.get("metadata") or {}
            pnl = meta.get("realized_pnl_usd") or meta.get("pnl_usd")
            if pnl is not None:
                try:
                    by_sym[sym].append(float(pnl))
                except (TypeError, ValueError):
                    pass
            else:
                # Record trade with no pnl so trade count is accurate
                if sym not in by_sym:
                    by_sym[sym] = []

        results: list[dict] = []
        for sym, pnls in by_sym.items():
            n = len(pnls)
            wins = sum(1 for p in pnls if p > 0)
            losses = sum(1 for p in pnls if p < 0)
            total_pnl = sum(pnls)
            avg_pnl = total_pnl / n if n > 0 else 0.0
            win_rate = wins / (wins + losses) if (wins + losses) > 0 else None
            best = max(pnls) if pnls else 0.0
            worst = min(pnls) if pnls else 0.0

            # Sharpe: mean/std of trade PnLs (dimensionless, needs ≥3 trades)
            sharpe: Optional[float] = None
            if n >= 3 and avg_pnl != 0:
                variance = sum((p - avg_pnl) ** 2 for p in pnls) / (n - 1)
                std = _math.sqrt(variance) if variance > 0 else 0.0
                sharpe = round(avg_pnl / std, 2) if std > 0 else None

            results.append({
                "symbol": sym,
                "trades": n,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 3) if win_rate is not None else None,
                "total_pnl_usd": round(total_pnl, 2),
                "avg_pnl_usd": round(avg_pnl, 2),
                "best_trade_usd": round(best, 2),
                "worst_trade_usd": round(worst, 2),
                "sharpe": sharpe,
            })

        # Sort by total PnL descending
        results.sort(key=lambda x: x["total_pnl_usd"], reverse=True)
        return results

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
