"""
src/services/backtest_scheduler.py
=====================================
BacktestScheduler — Story 228 (Milestone 36: Backtesting Dashboard).

Serviço de background que executa backtest automaticamente uma vez por dia,
armazena o histórico em memória (últimos 30 runs) e dispara o relatório
Telegram após cada run.

Uso (injetado no startup do servidor)::

    scheduler = BacktestScheduler(symbols=["BTC", "ETH"], hour_utc=0)
    asyncio.create_task(scheduler.start())
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import ClassVar, Dict, List, Optional

from loguru import logger

from src.models.backtest import BacktestSummary
from src.services.backtest_benchmark import BacktestBenchmark, BenchmarkResult
from src.services.backtest_runner import BacktestRunner
from src.services.backtest_telegram_report import BacktestTelegramReport


class BacktestScheduler:
    """
    Executa backtest diário e mantém histórico dos últimos runs.

    Parâmetros
    ----------
    symbols    : Lista de símbolos a backtestar (default: ["BTC"]).
    days       : Janela em dias para cada run (default: 30).
    hour_utc   : Hora UTC em que o backtest deve rodar (default: 0 = meia-noite).
    max_history: Número máximo de summaries a manter em memória (default: 30).
    send_telegram: Se True, envia relatório Telegram após cada run.
    """

    # Histórico em memória: {symbol: [BacktestSummary, ...]}
    _history: ClassVar[Dict[str, List[BacktestSummary]]] = {}
    # Última execução bem-sucedida: {symbol: datetime}
    _last_run: ClassVar[Dict[str, datetime]] = {}

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        days: int = 30,
        hour_utc: int = 0,
        max_history: int = 30,
        send_telegram: bool = True,
    ) -> None:
        self._symbols      = [s.upper() for s in (symbols or ["BTC"])]
        self._days         = days
        self._hour_utc     = hour_utc
        self._max_history  = max_history
        self._send_telegram = send_telegram
        self._running      = False
        self._log          = logger.bind(service="BacktestScheduler")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Loop principal: aguarda a próxima janela diária e executa."""
        self._running = True
        self._log.info(
            f"BacktestScheduler iniciado — símbolos={self._symbols} "
            f"dias={self._days} hora_utc={self._hour_utc}h"
        )
        while self._running:
            try:
                await self._wait_until_next_run()
                await self._run_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(f"BacktestScheduler: erro no loop — {exc}")
                await asyncio.sleep(60)  # backoff antes de tentar novamente

    def stop(self) -> None:
        """Para o loop do scheduler."""
        self._running = False

    async def run_now(self) -> Dict[str, BacktestSummary]:
        """Executa todos os símbolos imediatamente (útil para trigger manual)."""
        return await self._run_all()

    # ------------------------------------------------------------------
    # History accessors
    # ------------------------------------------------------------------

    @classmethod
    def get_history(cls, symbol: str) -> List[BacktestSummary]:
        """Retorna histórico de runs para o símbolo (mais recente primeiro)."""
        sym = symbol.upper().replace("USDT", "").replace("-", "")
        return list(reversed(cls._history.get(sym, [])))

    @classmethod
    def get_latest(cls, symbol: str) -> Optional[BacktestSummary]:
        """Retorna o run mais recente para o símbolo."""
        history = cls.get_history(symbol)
        return history[0] if history else None

    @classmethod
    def all_latest(cls) -> Dict[str, Optional[BacktestSummary]]:
        """Retorna o último run de cada símbolo rastreado."""
        return {sym: cls.get_latest(sym) for sym in cls._history}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _wait_until_next_run(self) -> None:
        """Aguarda até a próxima janela de execução (hora_utc configurada)."""
        now = datetime.now(timezone.utc)
        target = now.replace(hour=self._hour_utc, minute=0, second=0, microsecond=0)
        if target <= now:
            # Próxima ocorrência é amanhã
            from datetime import timedelta
            target = target + timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        self._log.info(
            f"BacktestScheduler: próximo run às "
            f"{target.strftime('%Y-%m-%d %H:%M UTC')} "
            f"(em {wait_secs/3600:.1f}h)"
        )
        await asyncio.sleep(wait_secs)

    async def _run_all(self) -> Dict[str, BacktestSummary]:
        """Executa backtest para todos os símbolos configurados."""
        results: Dict[str, BacktestSummary] = {}
        for sym in self._symbols:
            try:
                summary = await self._run_one(sym)
                results[sym] = summary
                self.__class__._last_run[sym] = datetime.now(timezone.utc)
            except Exception as exc:
                self._log.error(f"BacktestScheduler: falha no run de {sym} — {exc}")
        return results

    async def _run_one(self, symbol: str) -> BacktestSummary:
        """Executa backtest + benchmark + Telegram para um símbolo."""
        self._log.info(f"BacktestScheduler: rodando backtest {symbol} ({self._days} dias)")

        runner = BacktestRunner(initial_equity=10_000.0, seed=42)
        summary = await runner.run(symbol=symbol, days=self._days)

        # Armazenar no histórico
        if symbol not in self.__class__._history:
            self.__class__._history[symbol] = []
        self.__class__._history[symbol].append(summary)
        # Limitar histórico
        if len(self.__class__._history[symbol]) > self._max_history:
            self.__class__._history[symbol] = self.__class__._history[symbol][-self._max_history:]

        # Benchmark buy-hold
        benchmark: Optional[BenchmarkResult] = None
        try:
            bm = BacktestBenchmark()
            benchmark = await bm.compute(
                symbol=symbol,
                start_date=summary.start_date,
                end_date=summary.end_date,
                initial_equity=10_000.0,
            )
        except Exception as exc:
            self._log.warning(f"BacktestScheduler: benchmark falhou — {exc}")

        # Relatório Telegram
        if self._send_telegram:
            try:
                reporter = BacktestTelegramReport()
                await reporter.send(summary, benchmark=benchmark)
            except Exception as exc:
                self._log.warning(f"BacktestScheduler: Telegram falhou — {exc}")

        return summary
