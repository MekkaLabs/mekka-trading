"""
src/models/monitoring.py
========================
Pydantic models compartilhados pelo Milestone 34 — Monitoring & Alerting.

Modelos
-------
- DrawdownAlert  — resultado de DrawdownMonitor.check()
- ConcentrationAlert — resultado de PositionConcentrationAlerter.check()
- PnLSnapshot    — snapshot horário de P&L intraday
- FundingAlert   — alerta de funding rate extremo
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DrawdownAlert(BaseModel):
    """Alerta de drawdown intraday emitido pelo DrawdownMonitor."""

    level: Literal["WARNING", "CRITICAL", "KILL"]
    drawdown_pct: float = Field(description="Drawdown atual em %")
    current_equity: float
    peak_equity: float
    loss_usd: float = Field(description="Perda absoluta em USD")
    limit_pct: float = Field(description="Limite diário configurado em %")
    threshold_pct: float = Field(description="Threshold que disparou este nível em %")
    fired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pct_of_limit(self) -> float:
        """Percentual do limite diário já consumido (0.0–1.0+)."""
        if self.limit_pct == 0:
            return 0.0
        return self.drawdown_pct / self.limit_pct


class ConcentrationAlert(BaseModel):
    """Alerta de concentração de posição única acima do limite configurado."""

    symbol: str
    position_notional_usd: float
    equity_usd: float
    concentration_pct: float = Field(description="Concentração em % da equity")
    limit_pct: float = Field(description="Limite configurado em %")
    side: str = Field(default="UNKNOWN")
    fired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PnLSnapshot(BaseModel):
    """Snapshot horário de P&L intraday para o IntradayPnLTracker."""

    hour: int = Field(description="Hora UTC (0–23) deste snapshot")
    realized_pnl_usd: float = Field(default=0.0)
    unrealized_pnl_usd: float = Field(default=0.0)
    total_pnl_usd: float = Field(default=0.0)
    equity_usd: float = Field(default=0.0)
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_pnl_pct(self) -> float:
        """P&L total como % da equity inicial (se equity > 0)."""
        base = self.equity_usd - self.total_pnl_usd
        if base <= 0:
            return 0.0
        return self.total_pnl_usd / base * 100


class FundingAlert(BaseModel):
    """Alerta de funding rate extremo emitido pelo FundingRateMonitor."""

    symbol: str
    funding_rate_pct: float = Field(description="Taxa de funding em %")
    direction: Literal["HIGH_LONG", "HIGH_SHORT"]
    severity: Literal["WARN", "BLOCK"]
    threshold_pct: float = Field(description="Threshold que disparou o alerta em %")
    fired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_long_unfavorable(self) -> bool:
        return self.direction == "HIGH_LONG"
