"""
src/models/orchestration.py
===========================
Pydantic models for orchestration outputs (Layer 4).

CycleReport was originally a plain Python class inside
`src/agents/nick_fury.py`. Story 028 (Contract Hardening) promoted it
to a Pydantic model and moved it here so that:

- It serializes to/from JSON with `.model_dump()` for the dashboard.
- It carries `schema_version` for forward-compat.
- It lives next to the other Pydantic contracts.

`nick_fury.py` re-exports `CycleReport` for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from src.models.execution import ExecutionResult, ExecutionStatus
from src.models.risk import RiskApproval
from src.models.signal import TradingSignal
from src.utils.time import utc_now


class CycleReport(BaseModel):
    """
    Per-symbol outcome of one main cycle pass.

    Returned by `NickFury.run_main_cycle` (one per symbol in
    `settings.trading_assets`). Captures the four-stage pipeline result
    (analysis → signal → approval → execution) plus a top-level
    `error` field used when the symbol crashed before producing any
    structured output.
    """

    # Pydantic v2 config: allow attribute access like the previous
    # plain-class did and forbid extra unknown fields.
    model_config = ConfigDict(arbitrary_types_allowed=False, extra="forbid")

    schema_version: int = Field(default=1, description="Schema version")
    timestamp: datetime = Field(default_factory=utc_now)
    symbol: str
    signal: Optional[TradingSignal] = None
    approval: Optional[RiskApproval] = None
    execution: Optional[ExecutionResult] = None
    error: Optional[str] = None

    def is_executed(self) -> bool:
        """True when an execution actually happened (paper or live)."""
        if self.execution is None:
            return False
        return self.execution.status in (
            ExecutionStatus.FILLED,
            ExecutionStatus.PARTIAL,
            ExecutionStatus.PAPER,
        )

    def summary(self) -> str:
        if self.error:
            return f"[CycleReport] {self.symbol} ERROR — {self.error}"
        if self.execution is not None:
            return f"[CycleReport] {self.symbol} {self.execution.summary()}"
        if self.approval is not None and not self.approval.is_executable:
            return f"[CycleReport] {self.symbol} blocked — {self.approval.summary()}"
        if self.signal is not None:
            return f"[CycleReport] {self.symbol} signal-only — {self.signal.summary()}"
        return f"[CycleReport] {self.symbol} (empty)"

    def to_audit_payload(self) -> dict:
        """Serialize for `audit_log.payload`. Used by Dashboard / Deadpool."""
        return self.model_dump(mode="json")
