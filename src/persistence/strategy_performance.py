"""
src/persistence/strategy_performance.py
========================================
SQLAlchemy model + Pydantic summary for the Be Water Framework's
per-(strategy × regime × symbol) performance tracking.

Tabela ``strategy_performance``
-------------------------------
Cada linha agrega os outcomes (wins/losses, PnL, drawdown, Sharpe) de
UMA estratégia operando UM regime de mercado em UM símbolo. O
PerformanceTracker faz upsert nesta tabela a cada trade fechado.

A unicidade em (strategy_name, regime, symbol) é enforçada via
UniqueConstraint — assim o ``record_trade_outcome`` consegue agregar
sem race conditions (UPDATE-then-INSERT atomic).

Princípios:
- Idempotência: increments por trade, nunca substitui totals
- Read-only para Selectors (eles consomem agregados, não trades brutos)
- Window-aware: ``last_trade_at`` permite filtrar janelas temporais

Story: Be Water Framework — performance tracking foundation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.persistence.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategyPerformance(Base):
    """One row per (strategy_name × regime × symbol) tuple.

    Aggregates trade outcomes for empirical regime fitness scoring. The
    PerformanceTracker upserts increments here; the StrategySelector
    consumes ``sharpe_ratio`` / ``win_rate`` for ranking.
    """

    __tablename__ = "strategy_performance"
    __table_args__ = (
        UniqueConstraint(
            "strategy_name",
            "regime",
            "symbol",
            name="uq_strategy_perf_triple",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    regime: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    n_trades: Mapped[int] = mapped_column(Integer, default=0)
    n_wins: Mapped[int] = mapped_column(Integer, default=0)
    n_losses: Mapped[int] = mapped_column(Integer, default=0)

    total_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Acumuladores separados para wins e losses — permitem calcular
    # avg_win_pnl e avg_loss_pnl O(1) sem reler trades brutos.
    sum_win_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sum_loss_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)

    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    last_trade_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -------- derived properties --------

    @property
    def win_rate(self) -> float:
        """Wins / trades (0-1). Returns 0.0 when no trades."""
        return self.n_wins / max(self.n_trades, 1)

    @property
    def avg_pnl_per_trade(self) -> float:
        """Average PnL USD per trade. Returns 0.0 when no trades."""
        return self.total_pnl_usd / max(self.n_trades, 1)

    @property
    def avg_win_pnl(self) -> float:
        """Average PnL of winning trades (positive). 0.0 when no wins."""
        return self.sum_win_pnl_usd / max(self.n_wins, 1)

    @property
    def avg_loss_pnl(self) -> float:
        """Average PnL of losing trades (negative). 0.0 when no losses."""
        return self.sum_loss_pnl_usd / max(self.n_losses, 1)

    @property
    def expectancy(self) -> float:
        """E[PnL per trade] = p_win * avg_win + (1 - p_win) * avg_loss.

        Mathematically equivalent to ``avg_pnl_per_trade`` when there is
        no NEUTRAL bucket — the win/loss decomposition is kept anyway so
        callers can stress-test by varying win rate independently from
        the win/loss magnitudes (e.g. "what if win rate drops 10pp?").
        """
        p_win = self.win_rate
        return p_win * self.avg_win_pnl + (1.0 - p_win) * self.avg_loss_pnl

    def to_dict(self) -> dict:
        """JSON-friendly snapshot (used by dashboards / audit)."""
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "n_trades": self.n_trades,
            "n_wins": self.n_wins,
            "n_losses": self.n_losses,
            "total_pnl_usd": round(self.total_pnl_usd, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": (
                round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None
            ),
            "last_trade_at": (
                self.last_trade_at.isoformat() if self.last_trade_at else None
            ),
            "win_rate": round(self.win_rate, 4),
            "avg_pnl_per_trade": round(self.avg_pnl_per_trade, 4),
            "avg_win_pnl": round(self.avg_win_pnl, 4),
            "avg_loss_pnl": round(self.avg_loss_pnl, 4),
            "expectancy": round(self.expectancy, 4),
        }
