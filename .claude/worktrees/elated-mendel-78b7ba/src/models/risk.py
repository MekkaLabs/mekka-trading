"""
src/models/risk.py
==================
Pydantic models for risk-layer outputs.

Batman emits a `RiskApproval` deciding whether a `TradingSignal` may flow
to Iron Man for execution. This is a separate model file so the risk
contract is not coupled to the LLM signal contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskVerdict(str, Enum):
    """The four possible verdicts Batman can emit."""

    APPROVED = "APPROVED"
    REDUCED = "REDUCED"   # approved but with reduced size/leverage
    REJECTED = "REJECTED"
    KILL_SWITCH = "KILL_SWITCH"  # entire system halted


class RiskApproval(BaseModel):
    """
    Output of Batman's validation pass on a TradingSignal.

    Attributes
    ----------
    timestamp        : When validation ran
    symbol           : Asset symbol
    verdict          : APPROVED / REDUCED / REJECTED / KILL_SWITCH
    reasons          : List of human-readable reasons for the verdict
    adjusted_size_pct: Final size% to use (≤ original, may be 0 if rejected)
    adjusted_leverage: Final leverage (≤ original)
    breached_limits  : Names of limits that were breached or adjusted
    metadata         : Optional extra data
    """

    schema_version: int = Field(default=1, description="Schema version for migration safety")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    symbol: str
    verdict: RiskVerdict
    reasons: List[str] = Field(default_factory=list)
    adjusted_size_pct: float = Field(default=0.0, ge=0.0, le=0.10)
    adjusted_leverage: int = Field(default=1, ge=1, le=50)
    breached_limits: List[str] = Field(default_factory=list)
    metadata: Optional[dict] = None

    @property
    def is_executable(self) -> bool:
        """True when the verdict allows execution."""
        return self.verdict in (RiskVerdict.APPROVED, RiskVerdict.REDUCED)

    def summary(self) -> str:
        adj = f"size={self.adjusted_size_pct:.2%} lev={self.adjusted_leverage}x"
        first_reason = self.reasons[0] if self.reasons else "no notes"
        return (
            f"[Batman] {self.symbol} {self.verdict.value} | {adj} | "
            f"breached={','.join(self.breached_limits) or 'none'} | {first_reason}"
        )
