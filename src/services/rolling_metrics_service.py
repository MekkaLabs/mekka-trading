"""
src/services/rolling_metrics_service.py
==========================================
RollingMetricsService — Story 230 (Milestone 37: Live Performance Tracking).

Calcula métricas de performance rolling (janela configurável) a partir dos
trades reais/paper no SQLite: Sharpe, win_rate, expectancy, drawdown.

Uso::

    svc = RollingMetricsService()
    result = await svc.compute(symbol="BTC", window_days=30)
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from src.persistence.repository import MekkaRepository


class RollingMetricsService:
    """
    Computa métricas rolling a partir dos trades do DB.

    Métricas retornadas
    -------------------
    - total_trades, wins, losses
    - win_rate_pct
    - total_pnl_usd, avg_pnl_usd
    - sharpe_ratio   (anualizado, Rf=0, baseado nos P&Ls diários)
    - max_drawdown_pct
    - expectancy_usd
    - window_days, symbol, computed_at
    """

    def __init__(self) -> None:
        self._log = logger.bind(service="RollingMetricsService")

    async def compute(
        self,
        symbol: Optional[str] = None,
        window_days: int = 30,
    ) -> dict:
        """
        Calcula métricas para trades encerrados na janela informada.

        Args:
            symbol     : Filtrar por símbolo (None = todos os símbolos).
            window_days: Janela retroativa em dias.

        Returns:
            Dict com todas as métricas + metadados.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        try:
            trades = await MekkaRepository.list_paper_filled_trades(limit=2000)
        except Exception as exc:
            self._log.warning(f"RollingMetricsService: erro DB — {exc}")
            return self._empty(symbol or "ALL", window_days)

        # Filtrar por símbolo e janela
        sym_upper = symbol.upper().replace("-PERP", "").replace("USDT", "") if symbol else None
        filtered = []
        for t in trades:
            if sym_upper:
                t_sym = (t.symbol or "").upper().replace("-PERP", "").replace("USDT", "")
                if not t_sym.startswith(sym_upper):
                    continue
            ts = getattr(t, "timestamp", None) or getattr(t, "created_at", None)
            if ts and ts < cutoff:
                continue
            filtered.append(t)

        if not filtered:
            return self._empty(symbol or "ALL", window_days)

        # P&L por trade
        pnls = []
        for t in filtered:
            pnl = float(getattr(t, "pnl_usd", 0) or 0)
            pnls.append(pnl)

        wins   = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        total  = len(pnls)

        win_rate   = (wins / total * 100) if total > 0 else 0.0
        total_pnl  = sum(pnls)
        avg_pnl    = total_pnl / total if total > 0 else 0.0
        expectancy = avg_pnl

        # Sharpe anualizado (P&Ls como returns diários)
        sharpe = self._sharpe(pnls)

        # Max drawdown (simples — sobre P&Ls acumulados)
        max_dd_pct = self._max_drawdown(pnls)

        return {
            "symbol":           symbol or "ALL",
            "window_days":      window_days,
            "total_trades":     total,
            "wins":             wins,
            "losses":           losses,
            "win_rate_pct":     round(win_rate, 4),
            "total_pnl_usd":    round(total_pnl, 2),
            "avg_pnl_usd":      round(avg_pnl, 4),
            "expectancy_usd":   round(expectancy, 4),
            "sharpe_ratio":     round(sharpe, 4),
            "max_drawdown_pct": round(max_dd_pct, 4),
            "computed_at":      datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(pnls: list[float]) -> float:
        """Sharpe anualizado: média / desvio padrão * sqrt(252)."""
        if len(pnls) < 2:
            return 0.0
        n    = len(pnls)
        mean = sum(pnls) / n
        var  = sum((p - mean) ** 2 for p in pnls) / (n - 1)
        std  = math.sqrt(var)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(252)

    @staticmethod
    def _max_drawdown(pnls: list[float]) -> float:
        """Máximo drawdown percentual sobre a curva de equity acumulada."""
        if not pnls:
            return 0.0
        equity = 10_000.0
        peak   = equity
        max_dd = 0.0
        for p in pnls:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def _empty(symbol: str, window_days: int) -> dict:
        return {
            "symbol":           symbol,
            "window_days":      window_days,
            "total_trades":     0,
            "wins":             0,
            "losses":           0,
            "win_rate_pct":     0.0,
            "total_pnl_usd":    0.0,
            "avg_pnl_usd":      0.0,
            "expectancy_usd":   0.0,
            "sharpe_ratio":     0.0,
            "max_drawdown_pct": 0.0,
            "computed_at":      datetime.now(timezone.utc).isoformat(),
        }
