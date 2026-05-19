"""
src/services/backtest_benchmark.py
=====================================
BacktestBenchmark — Story 226 (Milestone 36: Backtesting Dashboard).

Calcula o retorno de uma estratégia buy-and-hold do BTC (ou outro símbolo)
para o mesmo período do backtest, servindo como benchmark de comparação.

Uso::

    benchmark = BacktestBenchmark()
    result = await benchmark.compute("BTC", start_date, end_date, initial_equity=10_000)
    print(result.total_return_pct)   # ex: +12.5%
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from src.persistence.repository import MekkaRepository


class BenchmarkResult(BaseModel):
    """Resultado do benchmark buy-and-hold."""

    symbol: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    initial_equity_usd: float = Field(default=10_000.0)
    final_equity_usd: float = Field(default=10_000.0)
    total_return_pct: float = Field(default=0.0)
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    note: str = Field(default="")

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "initial_equity_usd": self.initial_equity_usd,
            "final_equity_usd": round(self.final_equity_usd, 2),
            "total_return_pct": round(self.total_return_pct, 4),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "note": self.note,
        }


class BacktestBenchmark:
    """
    Computa benchmark buy-and-hold usando preços de entrada/saída dos sinais
    armazenados no DB (a melhor fonte disponível sem feed de preço externo).

    Se não há dados suficientes, retorna resultado neutro (0% retorno).
    """

    def __init__(self) -> None:
        self._log = logger.bind(service="BacktestBenchmark")

    async def compute(
        self,
        symbol: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        initial_equity: float = 10_000.0,
    ) -> BenchmarkResult:
        """
        Calcula o retorno buy-and-hold do símbolo no período informado.

        Usa o entry_price do sinal mais antigo como preço de entrada e o
        entry_price do sinal mais recente como proxy do preço de saída.
        """
        sym = symbol.upper().replace("USDT", "").replace("-PERP", "").replace("-", "")

        try:
            signals = await MekkaRepository.list_recent_signals(limit=2000)
        except Exception as exc:
            self._log.warning(f"BacktestBenchmark: erro ao carregar sinais — {exc}")
            return BenchmarkResult(
                symbol=sym,
                initial_equity_usd=initial_equity,
                final_equity_usd=initial_equity,
                note="DB indisponível",
            )

        # Filtrar pelo símbolo e período
        period_signals = [
            s for s in signals
            if (s.symbol or "").upper().startswith(sym)
            and s.entry_price
            and s.entry_price > 0
        ]

        if start_date:
            period_signals = [
                s for s in period_signals
                if s.timestamp and s.timestamp >= start_date
            ]
        if end_date:
            period_signals = [
                s for s in period_signals
                if s.timestamp and s.timestamp <= end_date
            ]

        if len(period_signals) < 2:
            self._log.info(f"BacktestBenchmark: dados insuficientes para {sym} no período")
            return BenchmarkResult(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                initial_equity_usd=initial_equity,
                final_equity_usd=initial_equity,
                note="Sinais insuficientes para calcular benchmark",
            )

        # Ordenar por timestamp
        period_signals.sort(key=lambda s: s.timestamp or datetime.min.replace(tzinfo=timezone.utc))

        entry_price = float(period_signals[0].entry_price)
        exit_price  = float(period_signals[-1].entry_price)

        if entry_price <= 0:
            return BenchmarkResult(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                initial_equity_usd=initial_equity,
                final_equity_usd=initial_equity,
                note="Preço de entrada inválido",
            )

        return_pct = (exit_price - entry_price) / entry_price * 100.0
        final_equity = initial_equity * (1 + return_pct / 100.0)

        self._log.info(
            f"BacktestBenchmark: {sym} buy-hold "
            f"entrada=${entry_price:,.2f} saída=${exit_price:,.2f} "
            f"retorno={return_pct:+.2f}%"
        )

        return BenchmarkResult(
            symbol=sym,
            start_date=period_signals[0].timestamp,
            end_date=period_signals[-1].timestamp,
            initial_equity_usd=initial_equity,
            final_equity_usd=round(final_equity, 2),
            total_return_pct=round(return_pct, 4),
            entry_price=entry_price,
            exit_price=exit_price,
            note=f"Buy-and-hold {sym} ({len(period_signals)} referências de preço)",
        )
