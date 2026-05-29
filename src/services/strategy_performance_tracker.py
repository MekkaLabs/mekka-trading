"""
src/services/strategy_performance_tracker.py
=============================================
StrategyPerformanceTracker — Be Water Framework.

Registra outcomes de cada trade fechado e agrega por
(strategy_name × regime × symbol) em ``strategy_performance``.

Exposto como funções módulo-level (não classe) para uso direto via
import:

    from src.services.strategy_performance_tracker import (
        record_trade_outcome,
        get_performance,
        get_top_strategies_for_regime,
        compute_sharpe_ratio,
    )

Princípios
----------
- IDEMPOTENT-LIKE: cada chamada *increments* — repassar o mesmo trade
  duas vezes vai contar duas vezes. Caller é responsável pela dedup
  (use trade_id como side-channel).
- FAIL-SILENT: nunca lança em I/O — log warning + retorna None/[].
- READ-PURE: getters não mutam DB. Apenas ``record_trade_outcome`` escreve.

Nota sobre nomenclatura
-----------------------
Este arquivo é DIFERENTE de ``src/services/performance_tracker.py``
(Story 229: real vs backtest comparison). Foi separado intencionalmente
para preservar imports legados.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import and_, desc, select

from src.persistence.db import get_session, init_engine
from src.persistence.models import TradeRecord
from src.persistence.strategy_performance import StrategyPerformance


_log = logger.bind(service="StrategyPerformanceTracker")


# ---------------------------------------------------------------------------
# DTO returned by getters
# ---------------------------------------------------------------------------


@dataclass
class StrategyPerformanceSummary:
    """Aggregated stats for one (strategy [× regime] [× symbol]) view.

    Returned by ``get_performance`` and ``get_top_strategies_for_regime``.
    Optional regime/symbol mean the result aggregates across them.
    """

    strategy_name: str
    regime: Optional[str] = None
    symbol: Optional[str] = None

    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0

    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    sharpe_ratio: Optional[float] = None
    last_trade_at: Optional[datetime] = None

    window_days: int = 30

    # Decomposed averages (helpful for selectors and dashboards)
    avg_win_pnl: float = 0.0
    avg_loss_pnl: float = 0.0

    extras: dict = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.n_wins / max(self.n_trades, 1)

    @property
    def avg_pnl_per_trade(self) -> float:
        return self.total_pnl_usd / max(self.n_trades, 1)

    @property
    def expectancy(self) -> float:
        p = self.win_rate
        return p * self.avg_win_pnl + (1.0 - p) * self.avg_loss_pnl

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "symbol": self.symbol,
            "n_trades": self.n_trades,
            "n_wins": self.n_wins,
            "n_losses": self.n_losses,
            "win_rate": round(self.win_rate, 4),
            "total_pnl_usd": round(self.total_pnl_usd, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": (
                round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None
            ),
            "avg_pnl_per_trade": round(self.avg_pnl_per_trade, 4),
            "avg_win_pnl": round(self.avg_win_pnl, 4),
            "avg_loss_pnl": round(self.avg_loss_pnl, 4),
            "expectancy": round(self.expectancy, 4),
            "last_trade_at": (
                self.last_trade_at.isoformat() if self.last_trade_at else None
            ),
            "window_days": self.window_days,
        }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


async def record_trade_outcome(
    strategy_name: str,
    regime: str,
    symbol: str,
    pnl_usd: float,
    pnl_pct: float,
    won: bool,
    timestamp: datetime,
) -> None:
    """Aggregate one trade outcome into the (strategy × regime × symbol) row.

    Idempotency: this method *increments* counters; calling it twice for the
    same trade double-counts. Caller is expected to dedup at the trade
    identification layer.

    Drawdown estimate: ``max_drawdown_pct`` is conservatively bumped by
    ``|pnl_pct|`` for losing trades — this is a per-trade-floor estimate,
    not a true running-equity drawdown. The StrategySelector uses Sharpe
    primarily anyway; drawdown is informational.
    """
    sym = symbol.upper().strip()
    rgm = regime.lower().strip()
    strat = strategy_name.strip()

    if not (strat and rgm and sym):
        _log.warning(
            f"record_trade_outcome: invalid keys "
            f"(strategy={strat!r} regime={rgm!r} symbol={sym!r}) — skipped"
        )
        return

    # Normalize the timestamp to tz-aware UTC. Naive datetimes are
    # assumed UTC because the rest of the persistence layer is
    # consistently UTC.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    try:
        await init_engine()
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"record_trade_outcome: engine init failed: {exc}")
        return

    try:
        async with get_session() as session:
            existing = (
                await session.execute(
                    select(StrategyPerformance).where(
                        and_(
                            StrategyPerformance.strategy_name == strat,
                            StrategyPerformance.regime == rgm,
                            StrategyPerformance.symbol == sym,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                rec = StrategyPerformance(
                    strategy_name=strat,
                    regime=rgm,
                    symbol=sym,
                    timestamp=timestamp,
                    n_trades=1,
                    n_wins=1 if won else 0,
                    n_losses=0 if won else 1,
                    total_pnl_usd=float(pnl_usd),
                    total_pnl_pct=float(pnl_pct),
                    sum_win_pnl_usd=float(pnl_usd) if won else 0.0,
                    sum_loss_pnl_usd=0.0 if won else float(pnl_usd),
                    max_drawdown_pct=abs(float(pnl_pct)) if not won else 0.0,
                    sharpe_ratio=None,  # filled later by compute_sharpe_ratio
                    last_trade_at=timestamp,
                )
                session.add(rec)
            else:
                existing.n_trades += 1
                if won:
                    existing.n_wins += 1
                    existing.sum_win_pnl_usd += float(pnl_usd)
                else:
                    existing.n_losses += 1
                    existing.sum_loss_pnl_usd += float(pnl_usd)
                    # Drawdown floor estimate: track the worst single-trade pct
                    existing.max_drawdown_pct = max(
                        existing.max_drawdown_pct or 0.0,
                        abs(float(pnl_pct)),
                    )
                existing.total_pnl_usd += float(pnl_usd)
                existing.total_pnl_pct += float(pnl_pct)
                existing.last_trade_at = timestamp

            await session.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            f"record_trade_outcome failed for "
            f"{strat}/{rgm}/{sym}: {exc}"
        )
        return

    # Best-effort: refresh Sharpe ratio in background-safe way (still inline
    # to keep call semantics simple). Failure is logged but never raised.
    try:
        sharpe = await compute_sharpe_ratio(strat, rgm, sym)
        if sharpe is not None:
            async with get_session() as session:
                row = (
                    await session.execute(
                        select(StrategyPerformance).where(
                            and_(
                                StrategyPerformance.strategy_name == strat,
                                StrategyPerformance.regime == rgm,
                                StrategyPerformance.symbol == sym,
                            )
                        )
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.sharpe_ratio = sharpe
                    await session.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            f"sharpe refresh failed for {strat}/{rgm}/{sym}: {exc}"
        )


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _row_to_summary(
    row: StrategyPerformance,
    window_days: int,
) -> StrategyPerformanceSummary:
    return StrategyPerformanceSummary(
        strategy_name=row.strategy_name,
        regime=row.regime,
        symbol=row.symbol,
        n_trades=row.n_trades,
        n_wins=row.n_wins,
        n_losses=row.n_losses,
        total_pnl_usd=row.total_pnl_usd,
        total_pnl_pct=row.total_pnl_pct,
        max_drawdown_pct=row.max_drawdown_pct,
        sharpe_ratio=row.sharpe_ratio,
        last_trade_at=row.last_trade_at,
        window_days=window_days,
        avg_win_pnl=row.avg_win_pnl,
        avg_loss_pnl=row.avg_loss_pnl,
    )


def _merge_summaries(
    parts: list[StrategyPerformance],
    strategy_name: str,
    regime: Optional[str],
    symbol: Optional[str],
    window_days: int,
) -> StrategyPerformanceSummary:
    """Reduce multiple rows into a single aggregated summary."""
    if not parts:
        return StrategyPerformanceSummary(
            strategy_name=strategy_name,
            regime=regime,
            symbol=symbol,
            window_days=window_days,
        )

    n_trades = sum(p.n_trades for p in parts)
    n_wins = sum(p.n_wins for p in parts)
    n_losses = sum(p.n_losses for p in parts)
    total_pnl_usd = sum(p.total_pnl_usd for p in parts)
    total_pnl_pct = sum(p.total_pnl_pct for p in parts)
    sum_win = sum(p.sum_win_pnl_usd for p in parts)
    sum_loss = sum(p.sum_loss_pnl_usd for p in parts)
    max_dd = max((p.max_drawdown_pct or 0.0 for p in parts), default=0.0)

    # Weighted Sharpe: ignore None, weight by n_trades. If everything is
    # None, return None.
    sharpe_parts = [(p.sharpe_ratio, p.n_trades) for p in parts if p.sharpe_ratio is not None]
    if sharpe_parts:
        wsum = sum(s * n for s, n in sharpe_parts)
        nsum = sum(n for _, n in sharpe_parts) or 1
        sharpe = wsum / nsum
    else:
        sharpe = None

    last_ts = max(
        (p.last_trade_at for p in parts if p.last_trade_at is not None),
        default=None,
    )

    avg_win_pnl = sum_win / max(n_wins, 1)
    avg_loss_pnl = sum_loss / max(n_losses, 1)

    return StrategyPerformanceSummary(
        strategy_name=strategy_name,
        regime=regime,
        symbol=symbol,
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        total_pnl_usd=total_pnl_usd,
        total_pnl_pct=total_pnl_pct,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        last_trade_at=last_ts,
        window_days=window_days,
        avg_win_pnl=avg_win_pnl,
        avg_loss_pnl=avg_loss_pnl,
    )


async def get_performance(
    strategy_name: str,
    regime: Optional[str] = None,
    symbol: Optional[str] = None,
    window_days: int = 30,
) -> StrategyPerformanceSummary:
    """Aggregate performance for a strategy. None regime/symbol = all.

    Filters by ``last_trade_at >= now - window_days``. Rows that have
    no ``last_trade_at`` (e.g. fresh inserts without an outcome window)
    are dropped from the window result.

    Returns an empty summary (n_trades=0) when nothing matches.
    """
    strat = strategy_name.strip()
    rgm = regime.lower().strip() if regime else None
    sym = symbol.upper().strip() if symbol else None

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))

    try:
        await init_engine()
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"get_performance: engine init failed: {exc}")
        return StrategyPerformanceSummary(
            strategy_name=strat, regime=rgm, symbol=sym, window_days=window_days
        )

    try:
        async with get_session() as session:
            stmt = select(StrategyPerformance).where(
                StrategyPerformance.strategy_name == strat
            )
            if rgm is not None:
                stmt = stmt.where(StrategyPerformance.regime == rgm)
            if sym is not None:
                stmt = stmt.where(StrategyPerformance.symbol == sym)
            # Window filter — drop rows whose last activity is outside the window
            stmt = stmt.where(StrategyPerformance.last_trade_at >= cutoff)
            rows = list((await session.execute(stmt)).scalars().all())
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"get_performance read failed: {exc}")
        return StrategyPerformanceSummary(
            strategy_name=strat, regime=rgm, symbol=sym, window_days=window_days
        )

    return _merge_summaries(rows, strat, rgm, sym, window_days)


async def get_top_strategies_for_regime(
    regime: str,
    limit: int = 3,
    min_trades: int = 10,
    window_days: int = 30,
) -> list[StrategyPerformanceSummary]:
    """Top N strategies for a regime, ranked by Sharpe (fallback: win_rate).

    Aggregates across all symbols per strategy. Filters by
    ``n_trades >= min_trades`` to avoid cherry-picking statistically
    insignificant samples.

    Window: only rows with ``last_trade_at`` within the last
    ``window_days`` are considered.
    """
    rgm = regime.lower().strip()
    if not rgm:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))

    try:
        await init_engine()
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"get_top_strategies_for_regime: engine init failed: {exc}")
        return []

    try:
        async with get_session() as session:
            rows = list(
                (
                    await session.execute(
                        select(StrategyPerformance)
                        .where(StrategyPerformance.regime == rgm)
                        .where(StrategyPerformance.last_trade_at >= cutoff)
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"get_top_strategies_for_regime read failed: {exc}")
        return []

    # Group by strategy_name (across symbols)
    by_strategy: dict[str, list[StrategyPerformance]] = {}
    for r in rows:
        by_strategy.setdefault(r.strategy_name, []).append(r)

    summaries: list[StrategyPerformanceSummary] = []
    for strat, parts in by_strategy.items():
        s = _merge_summaries(parts, strat, rgm, None, window_days)
        if s.n_trades >= min_trades:
            summaries.append(s)

    def _rank_key(s: StrategyPerformanceSummary) -> tuple[float, float]:
        # Sharpe primary (None => fall back to win_rate scaled); win_rate
        # tiebreaker for equal Sharpes.
        sharpe = s.sharpe_ratio if s.sharpe_ratio is not None else (s.win_rate - 0.5)
        return (sharpe, s.win_rate)

    summaries.sort(key=_rank_key, reverse=True)
    return summaries[: max(1, limit)]


async def compute_sharpe_ratio(
    strategy_name: str,
    regime: str,
    symbol: str,
    window_days: int = 30,
    min_trades: int = 10,
) -> Optional[float]:
    """Compute Sharpe from raw trade PnLs within the window.

    Reads ``trades`` table directly, filtering by symbol within the
    window. Strategy/regime are tagged via ``raw.metadata.strategy_name``
    and ``raw.metadata.regime`` (set by IronMan when executing strategy
    signals); when those tags are missing we fall back to *all* trades
    for the symbol — better than no signal at all for early backtesting.

    Returns None when fewer than ``min_trades`` matching trades exist
    or when stddev is zero.
    """
    strat = strategy_name.strip()
    rgm = regime.lower().strip()
    sym = symbol.upper().strip()

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))

    try:
        await init_engine()
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"compute_sharpe_ratio: engine init failed: {exc}")
        return None

    try:
        async with get_session() as session:
            rows = list(
                (
                    await session.execute(
                        select(TradeRecord)
                        .where(TradeRecord.symbol == sym)
                        .where(TradeRecord.timestamp >= cutoff)
                        .where(TradeRecord.pnl_usd.is_not(None))
                        .order_by(desc(TradeRecord.timestamp))
                        .limit(500)
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:  # noqa: BLE001
        _log.warning(f"compute_sharpe_ratio read failed: {exc}")
        return None

    pnls: list[float] = []
    for t in rows:
        raw = t.raw or {}
        meta = raw.get("metadata") or {}
        # Tagged trades: filter on (strategy, regime)
        meta_strat = (meta.get("strategy_name") or meta.get("strategy") or "").strip()
        meta_regime = (meta.get("regime") or "").lower().strip()
        if meta_strat or meta_regime:
            if meta_strat and meta_strat != strat:
                continue
            if meta_regime and meta_regime != rgm:
                continue
        try:
            pnl = float(t.pnl_usd)
        except (TypeError, ValueError):
            continue
        pnls.append(pnl)

    if len(pnls) < min_trades:
        return None

    n = len(pnls)
    mean = sum(pnls) / n
    variance = sum((p - mean) ** 2 for p in pnls) / max(n - 1, 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std <= 0:
        return None
    return round(mean / std, 4)
