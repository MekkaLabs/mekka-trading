"""
src/models/portfolio.py
=======================
Pydantic models for the portfolio / account-state layer.

Produced by Portfolio Manager. Consumed by Nick Fury (to size cycles)
and Batman (to validate against `max_open_positions`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EquitySource(str, Enum):
    """Where the equity figure originated."""

    HYPERLIQUID = "HYPERLIQUID"           # live read from clearinghouseState
    BYBIT = "BYBIT"                       # live read from Bybit via CCXT
    BINANCE = "BINANCE"                   # live read from Binance via CCXT
    PAPER_FALLBACK = "PAPER_FALLBACK"     # synthetic, taken from settings.paper_equity_usd
    OVERRIDE = "OVERRIDE"                  # caller-supplied (CLI flag, test fixture)


class PositionSummary(BaseModel):
    """A single open position summary as Portfolio Manager sees it."""

    symbol: str
    side: str = Field(..., description="'long' or 'short'")
    size: float = Field(..., description="Position size in base asset")
    entry_price: float = Field(..., gt=0)
    unrealized_pnl_usd: float = Field(default=0.0)
    leverage: Optional[int] = Field(default=None, ge=1)


class EquitySnapshot(BaseModel):
    """
    Output produced by Portfolio Manager after polling the active exchange
    for the operator's account state — or after falling back to a synthetic
    paper-trading equity figure.

    Attributes
    ----------
    timestamp                : When the snapshot was taken (UTC)
    source                   : HYPERLIQUID / BYBIT / BINANCE / PAPER_FALLBACK / OVERRIDE
    is_paper                 : True when the snapshot is paper-only data
    equity_usd               : Total equity in USD (account value)
    available_balance_usd    : Free margin in USD (equity - margin_used)
    margin_used_usd          : Margin currently locked by open positions
    open_positions_count     : Number of open positions
    positions                : Per-position summaries (may be empty)
    error                    : Human-readable error if snapshot is degraded
    """

    schema_version: int = Field(default=1, description="Schema version for migration safety")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: EquitySource
    is_paper: bool = True
    equity_usd: float = Field(..., ge=0.0)
    available_balance_usd: float = Field(default=0.0, ge=0.0)
    margin_used_usd: float = Field(default=0.0, ge=0.0)
    open_positions_count: int = Field(default=0, ge=0)
    positions: List[PositionSummary] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_degraded(self) -> bool:
        """True when the snapshot is a fallback or carries an error."""
        return self.source == EquitySource.PAPER_FALLBACK or self.error is not None

    def summary(self) -> str:
        tag = "PAPER" if self.is_paper else "LIVE"
        return (
            f"[Portfolio/{tag}] equity=${self.equity_usd:,.2f} "
            f"avail=${self.available_balance_usd:,.2f} "
            f"positions={self.open_positions_count} "
            f"src={self.source.value}"
            + (f" err={self.error}" if self.error else "")
        )
