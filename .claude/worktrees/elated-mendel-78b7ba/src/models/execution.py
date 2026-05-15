"""
src/models/execution.py
=======================
Pydantic models for the execution layer (Iron Man).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Final status of an execution attempt."""

    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    PAPER = "PAPER"  # paper-trade simulation
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class ExecutionResult(BaseModel):
    """
    Output of Iron Man after attempting to place an order on Hyperliquid.

    Attributes
    ----------
    timestamp     : When execution finished
    symbol        : Asset symbol
    status        : Final status
    is_paper      : True when simulated (no real order)
    side          : 'long' or 'short' (None on REJECTED/ERROR)
    quantity      : Filled quantity in base asset
    avg_price     : Average fill price
    notional_usd  : Filled USD notional
    order_id      : Exchange order id (if any)
    sl_order_id   : Stop-loss order id
    tp_order_id   : Take-profit order id
    error         : Error message (if status ERROR)
    metadata      : Extra context
    """

    schema_version: int = Field(default=1, description="Schema version for migration safety")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    symbol: str
    status: ExecutionStatus
    is_paper: bool = True
    side: Optional[str] = None
    quantity: float = Field(default=0.0, ge=0.0)
    avg_price: float = Field(default=0.0, ge=0.0)
    notional_usd: float = Field(default=0.0, ge=0.0)
    order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None

    def summary(self) -> str:
        tag = "PAPER" if self.is_paper else "LIVE"
        if self.status in (ExecutionStatus.REJECTED, ExecutionStatus.ERROR, ExecutionStatus.SKIPPED):
            return (
                f"[IronMan/{tag}] {self.symbol} {self.status.value} | "
                f"{self.error or 'no details'}"
            )
        return (
            f"[IronMan/{tag}] {self.symbol} {self.status.value} {self.side} | "
            f"qty={self.quantity:.6f} @ {self.avg_price:,.4f} = "
            f"${self.notional_usd:,.2f} | order={self.order_id}"
        )
