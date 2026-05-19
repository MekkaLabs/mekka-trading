"""
src/services/backtest_runner.py
================================
BacktestRunner — Story 223 (Milestone 35: Backtesting Engine).

Orquestra o pipeline completo de backtesting:

    BacktestSignalLoader
        → BacktestOutcomeSimulator
        → BacktestEquityCurve
        → BacktestMetricsEngine
        → BacktestSummary + relatório Markdown

Uso via CLI:
    python -m src.backtest run --symbol BTC --days 30
    python -m src.backtest run --symbol ETH --days 90 --initial-equity 5000
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.models.backtest import BacktestSummary
from src.services.backtest_equity_curve import BacktestEquityCurve
from src.services.backtest_metrics_engine import BacktestMetricsEngine
from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
from src.services.backtest_signal_loader import BacktestSignalLoader


class BacktestRunner:
    """
    Orquestra o pipeline completo de backtesting para um símbolo.

    Args:
        initial_equity: Capital inicial em USD (default 10_000).
        seed: Semente para reprodutibilidade da simulação (None = aleatório).
        actionable_only: Se True, carrega apenas sinais LONG/SHORT (ignora HOLD).

    Example::

        runner = BacktestRunner(initial_equity=10_000, seed=42)
        summary = await runner.run(symbol="BTC", days=30)
        print(runner.render_report(summary))
    """

    def __init__(
        self,
        initial_equity: float = 10_000.0,
        seed: Optional[int] = None,
        actionable_only: bool = True,
    ) -> None:
        self._initial_equity = initial_equity
        self._seed = seed
        self._actionable_only = actionable_only
        self._log = logger.bind(service="BacktestRunner")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run(
        self,
        symbol: str,
        days: int = 30,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestSummary:
        """
        Executa o pipeline completo e retorna BacktestSummary.

        Args:
            symbol: Símbolo a backtestar, ex: "BTC", "ETH".
            days: Janela em dias (usado se start_date/end_date não fornecidos).
            start_date: Data inicial explícita (override de days).
            end_date: Data final explícita (default = now).

        Returns:
            BacktestSummary com métricas, curva de equity e lista de trades.
        """
        sym = symbol.upper().replace("USDT", "").replace("-", "")
        self._log.info(f"BacktestRunner.run: símbolo={sym} days={days}")

        # 1. Carregar sinais históricos
        loader = BacktestSignalLoader(actionable_only=self._actionable_only)
        trades_raw = await loader.load(
            symbol=sym,
            days=days,
            start_date=start_date,
            end_date=end_date,
        )
        self._log.info(f"BacktestRunner: {len(trades_raw)} sinais carregados")

        if not trades_raw:
            self._log.warning(f"BacktestRunner: nenhum sinal para {sym} nos últimos {days} dias")
            return self._empty_summary(sym, days)

        # 2. Simular outcomes (trades sem resultado real)
        simulator = BacktestOutcomeSimulator(
            seed=self._seed,
            equity_usd=self._initial_equity,
        )
        trades_sim = simulator.simulate(trades_raw, equity_usd=self._initial_equity)

        # 3. Construir curva de equity
        equity_builder = BacktestEquityCurve()
        equity_curve = equity_builder.build(trades_sim, initial_equity=self._initial_equity)

        # 4. Computar métricas
        engine = BacktestMetricsEngine()
        metrics = engine.compute(
            trades=trades_sim,
            equity_curve=equity_curve,
            initial_equity=self._initial_equity,
        )

        self._log.info(
            f"BacktestRunner: {sym} — "
            f"WR={metrics.win_rate:.1f}% PF={metrics.profit_factor:.2f} "
            f"Sharpe={metrics.sharpe_ratio:.2f} MaxDD={metrics.max_drawdown_pct:.2f}%"
        )

        final_equity = equity_curve[-1].equity_usd if equity_curve else self._initial_equity

        return BacktestSummary(
            symbol=sym,
            start_date=metrics.first_trade_at,
            end_date=metrics.last_trade_at,
            initial_equity_usd=self._initial_equity,
            final_equity_usd=final_equity,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades_sim,
            generated_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Report rendering
    # ------------------------------------------------------------------

    @staticmethod
    def render_report(summary: BacktestSummary) -> str:
        """Gera relatório Markdown a partir de BacktestSummary."""
        m = summary.metrics
        lines = [
            f"# Backtest Report — {summary.symbol}",
            f"",
            f"**Gerado em:** {summary.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Período:** {_fmt_dt(summary.start_date)} → {_fmt_dt(summary.end_date)} ({m.days_covered:.0f} dias)",
            f"",
            f"## Capital",
            f"",
            f"| | USD |",
            f"|---|---|",
            f"| Capital inicial | ${summary.initial_equity_usd:,.2f} |",
            f"| Capital final   | ${summary.final_equity_usd:,.2f} |",
            f"| Retorno total   | {summary.total_return_pct:+.2f}% |",
            f"",
            f"## Métricas de Trades",
            f"",
            f"| Métrica | Valor |",
            f"|---|---|",
            f"| Total de trades | {m.total_trades} |",
            f"| Wins            | {m.wins} |",
            f"| Losses          | {m.losses} |",
            f"| Expirados       | {m.expired} |",
            f"| Win Rate        | {m.win_rate:.2f}% |",
            f"| Profit Factor   | {m.profit_factor:.4f} |",
            f"| Expectância     | ${m.expectancy_usd:+.2f} |",
            f"| Avg Win         | ${m.avg_win_usd:,.2f} |",
            f"| Avg Loss        | ${m.avg_loss_usd:,.2f} |",
            f"| Avg R:R         | {m.avg_risk_reward:.2f} |",
            f"| Avg Confiança   | {m.avg_confidence:.2%} |",
            f"",
            f"## Métricas de Risco",
            f"",
            f"| Métrica | Valor |",
            f"|---|---|",
            f"| Max Drawdown %  | {m.max_drawdown_pct:.4f}% |",
            f"| Max Drawdown $  | ${m.max_drawdown_usd:,.2f} |",
            f"| Sharpe Ratio    | {m.sharpe_ratio:.4f} |",
            f"| Sortino Ratio   | {m.sortino_ratio:.4f} |",
            f"",
            f"## PnL Total",
            f"",
            f"| | |",
            f"|---|---|",
            f"| PnL USD  | ${m.total_pnl_usd:+,.2f} |",
            f"| PnL %    | {m.total_pnl_pct:+.4f}% |",
        ]

        # Mini curva de equity (últimos 10 pontos)
        if summary.equity_curve and len(summary.equity_curve) > 1:
            lines += ["", "## Curva de Equity (últimos 10 pontos)", ""]
            lines += ["| Data | Equity USD | PnL Trade | Drawdown % | Símbolo | Outcome |"]
            lines += ["|---|---|---|---|---|---|"]
            sample = summary.equity_curve[-10:]
            for pt in sample:
                dt_str = pt.timestamp.strftime("%Y-%m-%d %H:%M") if pt.timestamp else "—"
                lines.append(
                    f"| {dt_str} | ${pt.equity_usd:,.2f} | ${pt.trade_pnl_usd:+,.2f} "
                    f"| {pt.drawdown_pct:.2f}% | {pt.symbol} | {pt.outcome.value} |"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _empty_summary(self, symbol: str, days: int) -> BacktestSummary:
        """Retorna summary vazio quando não há sinais."""
        from src.models.backtest import BacktestMetrics
        now = datetime.now(timezone.utc)
        return BacktestSummary(
            symbol=symbol,
            start_date=None,
            end_date=None,
            initial_equity_usd=self._initial_equity,
            final_equity_usd=self._initial_equity,
            metrics=BacktestMetrics(),
            equity_curve=[],
            trades=[],
            generated_at=now,
        )


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d")
