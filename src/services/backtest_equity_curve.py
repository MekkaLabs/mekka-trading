"""
src/services/backtest_equity_curve.py
=======================================
BacktestEquityCurve — Story 221 (Milestone 35: Backtesting Engine).

Constrói a curva de equity cronológica a partir de uma lista ordenada de
BacktestTrades com pnl_usd preenchido. Rastreia drawdown em cada ponto.
"""
from __future__ import annotations
from typing import List
from src.models.backtest import BacktestOutcome, BacktestTrade, EquityPoint


class BacktestEquityCurve:
    """
    Constrói curva de equity e calcula drawdown ponto a ponto.

    Example::

        curve = BacktestEquityCurve()
        points = curve.build(trades=simulated_trades, initial_equity=10_000.0)
    """

    def build(
        self,
        trades: List[BacktestTrade],
        initial_equity: float = 10_000.0,
    ) -> List[EquityPoint]:
        """
        Itera os trades em ordem cronológica e acumula equity + drawdown.

        Apenas trades LONG/SHORT com outcome WIN ou LOSS contribuem para PnL.
        HOLD/EXPIRED não movem a equity.

        Returns:
            Lista de EquityPoint ordenada por timestamp (inclui ponto inicial).
        """
        from datetime import datetime, timezone
        points: List[EquityPoint] = []
        equity = initial_equity
        peak = initial_equity

        # Ponto inicial
        points.append(EquityPoint(
            timestamp=trades[0].timestamp if trades else datetime.now(timezone.utc),
            equity_usd=equity,
            trade_pnl_usd=0.0,
            drawdown_pct=0.0,
            symbol="START",
            outcome=BacktestOutcome.UNKNOWN,
        ))

        for trade in trades:
            if trade.outcome in (BacktestOutcome.WIN, BacktestOutcome.LOSS):
                equity += trade.pnl_usd
                equity = max(equity, 0.0)  # nunca negativo

            if equity > peak:
                peak = equity

            dd_pct = ((peak - equity) / peak * 100) if peak > 0 else 0.0

            points.append(EquityPoint(
                timestamp=trade.timestamp,
                equity_usd=round(equity, 2),
                trade_pnl_usd=trade.pnl_usd,
                drawdown_pct=round(dd_pct, 4),
                symbol=trade.symbol,
                outcome=trade.outcome,
            ))

        return points
