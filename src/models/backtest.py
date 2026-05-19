"""
src/models/backtest.py
=======================
Pydantic models para o Milestone 35 — Backtesting Engine.

Modelos
-------
- BacktestOutcome  — WIN / LOSS / EXPIRED / UNKNOWN
- BacktestTrade    — unifica sinal + resultado real/simulado
- EquityPoint      — ponto na curva de equity (timestamp + equity)
- BacktestMetrics  — métricas computadas (Sharpe, drawdown, win rate, etc.)
- BacktestSummary  — resultado completo de um backtest
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BacktestOutcome(str, Enum):
    WIN     = "WIN"      # TP atingido
    LOSS    = "LOSS"     # SL atingido
    EXPIRED = "EXPIRED"  # Expirou sem atingir SL/TP (baseado em heurística)
    UNKNOWN = "UNKNOWN"  # Sem dados suficientes para determinar


class BacktestTrade(BaseModel):
    """
    Representa um sinal histórico + seu resultado (real ou simulado).

    Campos de sinal
    ---------------
    timestamp, symbol, action, entry_price, stop_loss, take_profit,
    size_pct, leverage, confidence, risk_reward

    Campos de resultado
    -------------------
    outcome        — WIN/LOSS/EXPIRED/UNKNOWN (preenchido pelo OutcomeSimulator)
    pnl_usd        — P&L realizado em USD (positivo = ganho)
    pnl_pct        — P&L em % do capital alocado
    real_pnl_usd   — P&L real da tabela trades (None se sem trade correspondente)
    is_real        — True se o resultado veio de um trade real no DB
    signal_id      — ID do SignalRecord no SQLite (para rastreabilidade)
    trade_id       — ID do TradeRecord no SQLite (None se sem trade correspondente)
    """

    # Dados do sinal
    timestamp: datetime
    symbol: str
    action: Literal["LONG", "SHORT", "HOLD"]
    entry_price: float
    stop_loss: float
    take_profit: float
    size_pct: float = Field(default=0.02)
    leverage: int = Field(default=1)
    confidence: float = Field(default=0.0)
    risk_reward: float = Field(default=0.0)
    reasoning: str = Field(default="")
    signal_id: Optional[int] = None

    # Dados de resultado (preenchidos pelos serviços downstream)
    outcome: BacktestOutcome = BacktestOutcome.UNKNOWN
    pnl_usd: float = Field(default=0.0)
    pnl_pct: float = Field(default=0.0)
    real_pnl_usd: Optional[float] = None   # da tabela trades
    is_real: bool = False                   # True = resultado veio do DB
    trade_id: Optional[int] = None

    @property
    def is_actionable(self) -> bool:
        return self.action in ("LONG", "SHORT")

    @property
    def sl_distance_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return abs(self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def tp_distance_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return abs(self.take_profit - self.entry_price) / self.entry_price * 100

    @property
    def allocated_usd(self, equity: float = 10_000.0) -> float:
        """Capital alocado estimado (size_pct × equity padrão)."""
        return self.size_pct * equity


class EquityPoint(BaseModel):
    """Ponto na curva de equity."""
    timestamp: datetime
    equity_usd: float
    trade_pnl_usd: float = Field(default=0.0, description="PnL do trade que gerou este ponto")
    drawdown_pct: float = Field(default=0.0, description="Drawdown desde o pico em %")
    symbol: str = Field(default="")
    outcome: BacktestOutcome = BacktestOutcome.UNKNOWN


class BacktestMetrics(BaseModel):
    """Métricas computadas sobre uma sequência de BacktestTrades."""

    # Contagens básicas
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    expired: int = 0

    # Retorno
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0

    # Taxas
    win_rate: float = Field(default=0.0, description="% de trades vencedores (0-100)")
    profit_factor: float = Field(default=0.0, description="Gross profit / gross loss")
    expectancy_usd: float = Field(default=0.0, description="Ganho esperado por trade em USD")

    # Risco
    max_drawdown_pct: float = Field(default=0.0, description="Máximo drawdown em %")
    max_drawdown_usd: float = Field(default=0.0, description="Máximo drawdown em USD")

    # Risco/retorno
    avg_risk_reward: float = Field(default=0.0, description="R:R médio dos sinais")
    avg_confidence: float = Field(default=0.0, description="Confiança média da Vision (0-1)")

    # Ratios (requerem ≥2 trades para ser significativos)
    sharpe_ratio: float = Field(default=0.0, description="Sharpe ratio anualizado")
    sortino_ratio: float = Field(default=0.0, description="Sortino ratio anualizado")

    # Série temporal
    first_trade_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None
    days_covered: float = Field(default=0.0, description="Dias cobertos pelo backtest")


class BacktestSummary(BaseModel):
    """Resultado completo de uma execução de backtest."""

    symbol: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # BUG-002 fix: renomeados para _usd para consistência com BacktestRunner e server.py
    initial_equity_usd: float = Field(default=10_000.0)
    final_equity_usd: float = Field(default=10_000.0)
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    equity_curve: List[EquityPoint] = Field(default_factory=list)
    trades: List[BacktestTrade] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_return_pct(self) -> float:
        if self.initial_equity_usd <= 0:
            return 0.0
        return (self.final_equity_usd - self.initial_equity_usd) / self.initial_equity_usd * 100
