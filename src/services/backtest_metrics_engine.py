"""
src/services/backtest_metrics_engine.py
=========================================
BacktestMetricsEngine — Story 222 (Milestone 35: Backtesting Engine).

Computa métricas financeiras a partir de trades e curva de equity.

Métricas
--------
  win_rate       % de trades vencedores
  profit_factor  Gross profit / Gross loss
  expectancy_usd Ganho esperado por trade em USD
  sharpe_ratio   Retorno ajustado ao risco (anualizado, Rf=0)
  sortino_ratio  Sharpe usando apenas desvio negativo
  max_drawdown_pct  Máximo drawdown em %
  max_drawdown_usd  Máximo drawdown em USD absoluto
"""
from __future__ import annotations

import math
from typing import List

from src.models.backtest import BacktestMetrics, BacktestOutcome, BacktestTrade, EquityPoint


class BacktestMetricsEngine:

    def compute(
        self,
        trades: List[BacktestTrade],
        equity_curve: List[EquityPoint],
        initial_equity: float = 10_000.0,
    ) -> BacktestMetrics:
        """Computa todas as métricas e retorna BacktestMetrics."""
        actionable = [t for t in trades if t.outcome in (BacktestOutcome.WIN, BacktestOutcome.LOSS)]
        wins  = [t for t in actionable if t.outcome == BacktestOutcome.WIN]
        losses= [t for t in actionable if t.outcome == BacktestOutcome.LOSS]

        total = len(actionable)
        win_rate = (len(wins) / total * 100) if total > 0 else 0.0

        gross_profit = sum(t.pnl_usd for t in wins)
        gross_loss   = abs(sum(t.pnl_usd for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        total_pnl = sum(t.pnl_usd for t in actionable)
        avg_win  = (gross_profit / len(wins))  if wins  else 0.0
        avg_loss = (gross_loss   / len(losses)) if losses else 0.0
        expectancy = (total_pnl / total) if total > 0 else 0.0
        total_pnl_pct = (total_pnl / initial_equity * 100) if initial_equity > 0 else 0.0

        # Drawdown
        max_dd_pct = max((p.drawdown_pct for p in equity_curve), default=0.0)
        peak = initial_equity
        max_dd_usd = 0.0
        for p in equity_curve:
            if p.equity_usd > peak:
                peak = p.equity_usd
            dd = peak - p.equity_usd
            if dd > max_dd_usd:
                max_dd_usd = dd

        # Sharpe & Sortino (usando retornos por trade)
        returns = [t.pnl_usd for t in actionable]
        sharpe  = self._sharpe(returns)
        sortino = self._sortino(returns)

        # Datas
        ts_list = [t.timestamp for t in trades if t.timestamp]
        first_ts = min(ts_list) if ts_list else None
        last_ts  = max(ts_list) if ts_list else None
        days = ((last_ts - first_ts).total_seconds() / 86400) if (first_ts and last_ts) else 0.0

        return BacktestMetrics(
            total_trades=total,
            wins=len(wins),
            losses=len(losses),
            expired=len([t for t in trades if t.outcome == BacktestOutcome.EXPIRED]),
            total_pnl_usd=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 4),
            avg_win_usd=round(avg_win, 2),
            avg_loss_usd=round(avg_loss, 2),
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 4),
            expectancy_usd=round(expectancy, 2),
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_usd=round(max_dd_usd, 2),
            avg_risk_reward=round(sum(t.risk_reward for t in actionable) / total, 4) if total > 0 else 0.0,
            avg_confidence=round(sum(t.confidence for t in actionable) / total, 4) if total > 0 else 0.0,
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            first_trade_at=first_ts,
            last_trade_at=last_ts,
            days_covered=round(days, 1),
        )

    @staticmethod
    def _sharpe(returns: List[float], periods_per_year: float = 252.0) -> float:
        if len(returns) < 2:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        var  = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std  = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(periods_per_year)

    @staticmethod
    def _sortino(returns: List[float], periods_per_year: float = 252.0) -> float:
        if len(returns) < 2:
            return 0.0
        n = len(returns)
        mean = sum(returns) / n
        neg  = [r for r in returns if r < 0]
        if not neg:
            return 999.0  # sem perdas → Sortino infinito (cap em 999)
        downside_var = sum(r ** 2 for r in neg) / n
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return (mean / downside_std) * math.sqrt(periods_per_year)
