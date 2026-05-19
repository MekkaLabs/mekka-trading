"""
src/services/performance_tracker.py
=======================================
PerformanceTracker — Story 229 (Milestone 37: Live Performance Tracking).

Compara a performance real (trades no DB) com o backtest mais recente
para o mesmo símbolo, expondo as diferenças como um snapshot estruturado.

Uso::

    tracker = PerformanceTracker()
    snapshot = await tracker.compare(symbol="BTC", backtest_summary=summary)
    print(snapshot.alpha_pnl_usd)  # Diferença real vs simulado
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from src.models.backtest import BacktestSummary
from src.services.rolling_metrics_service import RollingMetricsService


class PerformanceSnapshot(BaseModel):
    """Snapshot comparativo: real vs backtest."""

    symbol: str
    window_days: int = 30

    # Métricas reais
    real_trades:     int   = 0
    real_win_rate:   float = 0.0
    real_sharpe:     float = 0.0
    real_pnl_usd:    float = 0.0
    real_max_dd_pct: float = 0.0

    # Métricas backtest
    bt_trades:     int   = 0
    bt_win_rate:   float = 0.0
    bt_sharpe:     float = 0.0
    bt_pnl_pct:    float = 0.0
    bt_max_dd_pct: float = 0.0

    # Deltas (real − backtest)
    delta_win_rate:   float = 0.0   # pp
    delta_sharpe:     float = 0.0
    delta_max_dd_pct: float = 0.0   # pp (positivo = real tem MAIS drawdown)
    alpha_pnl_usd:    float = 0.0   # real_pnl − projeção_backtest

    # Avaliação
    status: str = "ok"  # "ok" | "warn" | "diverging"
    notes: list[str] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["generated_at"] = self.generated_at.isoformat()
        return d


class PerformanceTracker:
    """
    Compara performance real (rolling) vs backtest (simulado).

    Thresholds de divergência
    -------------------------
    - win_rate diverge >15pp → warn
    - Sharpe diverge >1.0    → warn
    - max_drawdown real > bt * 1.5 → warn
    """

    WIN_RATE_WARN_PP  = 15.0
    SHARPE_WARN_DELTA = 1.0
    DD_MULTIPLIER     = 1.5

    def __init__(self) -> None:
        self._log = logger.bind(service="PerformanceTracker")

    async def compare(
        self,
        symbol: str,
        backtest: Optional[BacktestSummary] = None,
        window_days: int = 30,
    ) -> PerformanceSnapshot:
        """
        Compara métricas reais vs backtest para o símbolo.

        Se backtest=None, retorna snapshot com apenas métricas reais.
        """
        sym = symbol.upper().replace("-PERP", "").replace("USDT", "")

        # Métricas reais
        svc  = RollingMetricsService()
        real = await svc.compute(symbol=sym, window_days=window_days)

        snap = PerformanceSnapshot(
            symbol=sym,
            window_days=window_days,
            real_trades=real["total_trades"],
            real_win_rate=real["win_rate_pct"],
            real_sharpe=real["sharpe_ratio"],
            real_pnl_usd=real["total_pnl_usd"],
            real_max_dd_pct=real["max_drawdown_pct"],
        )

        if backtest is None:
            snap.status = "ok"
            snap.notes.append("Sem backtest de referência disponível")
            return snap

        m = backtest.metrics
        snap.bt_trades    = m.total_trades
        snap.bt_win_rate  = m.win_rate
        snap.bt_sharpe    = m.sharpe_ratio
        snap.bt_pnl_pct   = m.total_pnl_pct
        snap.bt_max_dd_pct = m.max_drawdown_pct

        # Deltas
        snap.delta_win_rate   = snap.real_win_rate - snap.bt_win_rate
        snap.delta_sharpe     = snap.real_sharpe   - snap.bt_sharpe
        snap.delta_max_dd_pct = snap.real_max_dd_pct - snap.bt_max_dd_pct

        # Projeção P&L backtest → real (simples: bt_pnl_pct sobre equity inicial 10k)
        bt_pnl_projected = 10_000.0 * snap.bt_pnl_pct / 100.0
        snap.alpha_pnl_usd = round(snap.real_pnl_usd - bt_pnl_projected, 2)

        # Avaliação
        warnings = []
        if abs(snap.delta_win_rate) > self.WIN_RATE_WARN_PP:
            warnings.append(
                f"Win rate real ({snap.real_win_rate:.1f}%) diverge "
                f"{snap.delta_win_rate:+.1f}pp do backtest"
            )
        if abs(snap.delta_sharpe) > self.SHARPE_WARN_DELTA:
            warnings.append(
                f"Sharpe real ({snap.real_sharpe:.2f}) diverge "
                f"{snap.delta_sharpe:+.2f} do backtest"
            )
        if snap.bt_max_dd_pct > 0 and snap.real_max_dd_pct > snap.bt_max_dd_pct * self.DD_MULTIPLIER:
            warnings.append(
                f"MaxDrawdown real ({snap.real_max_dd_pct:.2f}%) é "
                f"{snap.real_max_dd_pct/snap.bt_max_dd_pct:.1f}× o do backtest"
            )

        snap.notes = warnings
        if len(warnings) >= 2:
            snap.status = "diverging"
        elif len(warnings) == 1:
            snap.status = "warn"
        else:
            snap.status = "ok"

        self._log.info(
            f"PerformanceTracker: {sym} status={snap.status} "
            f"Δwin_rate={snap.delta_win_rate:+.1f}pp Δsharpe={snap.delta_sharpe:+.2f}"
        )
        return snap
