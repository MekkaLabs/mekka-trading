"""
src/models/recovery.py
======================
Pydantic models for the recovery layer (Wolverine, Story 030).

Wolverine watches open positions every monitor cycle and emits a
`RecoveryPlan` describing what (if anything) should be done to each
of them. The plan is **advisory in v1** — Iron Man doesn't yet read
it. Nick Fury logs the plan to `audit_log` so the operator and the
dashboard can see what Wolverine intended.

Why "advisory"? Because actually issuing close/modify orders on
Hyperliquid requires the same SDK paths Iron Man uses, and we want
to keep that gate firmly in Iron Man's hands. Wolverine reasons,
Iron Man executes. Story 031+ will wire actual SL/TP modification
end-to-end if the v1 reasoning proves sound.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.utils.time import utc_now


class RecoveryAction(str, Enum):
    """What Wolverine recommends doing to a single position."""

    HOLD = "HOLD"                   # leave the position alone
    TIGHTEN_STOP = "TIGHTEN_STOP"   # move SL closer (lock more profit / cap loss)
    TRAIL_STOP = "TRAIL_STOP"       # ratchet SL upward following price
    SCALE_OUT = "SCALE_OUT"         # close part of the position
    CLOSE = "CLOSE"                 # close the entire position
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"  # close immediately, drawdown breach


class PositionUpdate(BaseModel):
    """One per open position monitored this cycle."""

    schema_version: int = Field(default=1)
    symbol: str
    side: str  # 'long' | 'short'
    size: float = Field(..., ge=0.0)
    entry_price: float = Field(..., gt=0.0)
    current_price: Optional[float] = Field(default=None, ge=0.0)
    unrealized_pnl_usd: float = Field(default=0.0)
    leverage: int = Field(default=1, ge=1, description="Position leverage (used to scale loss thresholds)")
    action: RecoveryAction = Field(default=RecoveryAction.HOLD)
    new_stop_loss: Optional[float] = Field(default=None, ge=0.0)
    new_take_profit: Optional[float] = Field(default=None, ge=0.0)
    reason: str = Field(default="")

    def summary(self) -> str:
        bits = [
            f"{self.symbol}/{self.side} qty={self.size:.6f}",
            f"entry={self.entry_price:,.4f}",
            f"upnl={self.unrealized_pnl_usd:+,.2f}",
            f"action={self.action.value}",
        ]
        if self.new_stop_loss is not None:
            bits.append(f"sl→{self.new_stop_loss:,.4f}")
        if self.new_take_profit is not None:
            bits.append(f"tp→{self.new_take_profit:,.4f}")
        return " ".join(bits)


class RecoveryPlan(BaseModel):
    """
    Output of `Wolverine.run(snapshot)`. Carries one PositionUpdate
    per open position, plus a top-level breaker decision.

    Attributes
    ----------
    timestamp           : When the plan was generated
    positions           : Per-position recommendations
    intraday_drawdown_pct : Aggregate unrealized loss as % of equity
    kill_switch_engaged : True when Wolverine engaged the kill switch
                          this cycle (intraday drawdown breach)
    notes               : Free-text human-readable summary
    """

    schema_version: int = Field(default=1)
    timestamp: datetime = Field(default_factory=utc_now)
    positions: List[PositionUpdate] = Field(default_factory=list)
    intraday_drawdown_pct: float = Field(default=0.0)
    kill_switch_engaged: bool = Field(default=False)
    notes: str = Field(default="")

    @property
    def total_unrealized_pnl_usd(self) -> float:
        return sum(p.unrealized_pnl_usd for p in self.positions)

    @property
    def needs_action(self) -> bool:
        """True when at least one position has a non-HOLD action."""
        return any(p.action != RecoveryAction.HOLD for p in self.positions)

    def summary(self) -> str:
        tag = "KILL" if self.kill_switch_engaged else "OK"
        return (
            f"[Wolverine/{tag}] positions={len(self.positions)} "
            f"upnl=${self.total_unrealized_pnl_usd:+,.2f} "
            f"intraday_dd={self.intraday_drawdown_pct:.2%} "
            f"actions={'yes' if self.needs_action else 'no'}"
        )

    def to_audit_payload(self) -> dict:
        return self.model_dump(mode="json")
