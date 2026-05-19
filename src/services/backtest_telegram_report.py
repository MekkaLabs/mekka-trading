"""
src/services/backtest_telegram_report.py
==========================================
BacktestTelegramReport — Story 227 (Milestone 36: Backtesting Dashboard).

Formata e envia um relatório de backtest compacto via Telegram após a
conclusão de um run. Usa o TelegramAlerter existente como transporte.

Uso::

    reporter = BacktestTelegramReport()
    await reporter.send(summary, benchmark=benchmark_result)
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from src.models.backtest import BacktestSummary
from src.services.backtest_benchmark import BenchmarkResult


class BacktestTelegramReport:
    """
    Envia resumo de backtest via Telegram.

    Formato do relatório (Markdown Telegram):
        📊 Backtest BTC — 30 dias
        Capital: $10.000 → $10.350 (+3.50%)
        Trades: 12 | WR: 58.3% | PF: 1.42
        Sharpe: 1.21 | MaxDD: -2.4%
        🏆 Benchmark BTC buy-hold: +5.2%
    """

    def __init__(self) -> None:
        self._log = logger.bind(service="BacktestTelegramReport")

    async def send(
        self,
        summary: BacktestSummary,
        benchmark: Optional[BenchmarkResult] = None,
    ) -> bool:
        """
        Envia o relatório via TelegramAlerter.

        Returns:
            True se enviado com sucesso, False caso contrário.
        """
        try:
            from src.services.telegram_alerter import TelegramAlerter
        except ImportError:
            self._log.warning("BacktestTelegramReport: TelegramAlerter não disponível")
            return False

        message = self._format(summary, benchmark)
        try:
            alerter = TelegramAlerter()
            # BUG-003 fix: TelegramAlerter não tem .send() — usar .alert()
            await alerter.alert(
                event="BACKTEST_REPORT",
                severity="INFO",
                agent="BacktestRunner",
                symbol=summary.symbol,
                message=message,
            )
            self._log.info(f"BacktestTelegramReport: relatório enviado para {summary.symbol}")
            return True
        except Exception as exc:
            self._log.warning(f"BacktestTelegramReport: falha no envio — {exc}")
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format(
        summary: BacktestSummary,
        benchmark: Optional[BenchmarkResult] = None,
    ) -> str:
        m = summary.metrics
        ret_sign = "+" if summary.total_return_pct >= 0 else ""

        period_str = ""
        if summary.start_date and summary.end_date:
            d0 = summary.start_date.strftime("%d/%m")
            d1 = summary.end_date.strftime("%d/%m/%Y")
            period_str = f" ({d0}→{d1})"

        lines = [
            f"📊 *Backtest {summary.symbol}*{period_str}",
            f"",
            f"💰 Capital: ${summary.initial_equity_usd:,.0f} → ${summary.final_equity_usd:,.0f} "
            f"({ret_sign}{summary.total_return_pct:.2f}%)",
            f"",
            f"📈 Trades: {m.total_trades} | WR: {m.win_rate:.1f}% | PF: {m.profit_factor:.2f}",
            f"⚡ Sharpe: {m.sharpe_ratio:.2f} | Sortino: {m.sortino_ratio:.2f}",
            f"📉 MaxDD: -{m.max_drawdown_pct:.2f}% (${m.max_drawdown_usd:,.0f})",
            f"🎯 Expectância: ${m.expectancy_usd:+.2f}/trade",
        ]

        if benchmark and benchmark.entry_price and benchmark.exit_price:
            bm_sign = "+" if benchmark.total_return_pct >= 0 else ""
            lines += [
                f"",
                f"🏆 *Benchmark {summary.symbol} buy-hold*: "
                f"{bm_sign}{benchmark.total_return_pct:.2f}%",
                f"   (${benchmark.entry_price:,.0f} → ${benchmark.exit_price:,.0f})",
            ]

            # Comparação alfa vs benchmark
            alpha = summary.total_return_pct - benchmark.total_return_pct
            alpha_sign = "+" if alpha >= 0 else ""
            verdict = "✅ Supera benchmark" if alpha >= 0 else "⚠️ Abaixo do benchmark"
            lines.append(f"   {verdict} (alfa: {alpha_sign}{alpha:.2f}%)")

        lines += [
            f"",
            f"_Gerado em {summary.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_",
        ]

        return "\n".join(lines)

    @staticmethod
    def format_message(
        summary: BacktestSummary,
        benchmark: Optional[BenchmarkResult] = None,
    ) -> str:
        """Exposição pública do formatador (útil para testes e preview)."""
        return BacktestTelegramReport._format(summary, benchmark)
