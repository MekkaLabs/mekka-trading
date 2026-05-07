"""
src/models/errors.py
====================
Standardized error envelope (Story 028 — Contract Hardening).

Every defensive path in any agent should — when wanting to record the
failure — emit an `AgentErrorReport` to `audit_log.payload` instead of
free-form dicts. Reads stay queryable: dashboard/Deadpool can group
errors by `agent` + `error_class` without string heuristics.

Adoption is opt-in. Existing agents continue to work without it; new
agents (Wolverine onwards) should prefer it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.utils.time import utc_now


class AgentErrorReport(BaseModel):
    """Structured error envelope written to `audit_log.payload`."""

    schema_version: int = Field(default=1, description="Schema version for forward compat")
    timestamp: datetime = Field(default_factory=utc_now)
    agent: str = Field(..., description="Hero codename (preferably HeroName.value)")
    error_class: str = Field(
        ..., description="Exception class name, e.g. 'TimeoutError'"
    )
    message: str = Field(..., description="Human-readable error description")
    fallback_taken: bool = Field(
        default=False,
        description="True when the agent recovered into a defensive path",
    )
    payload: Optional[dict] = Field(
        default=None,
        description="Optional extra context (request shape, partial result, etc.)",
    )

    def to_audit_payload(self) -> dict:
        """Serialize for use as `MekkaRepository.log_event(payload=...)`."""
        return self.model_dump(mode="json")

    def summary(self) -> str:
        tag = "FALLBACK" if self.fallback_taken else "ERROR"
        return f"[{self.agent}/{tag}] {self.error_class}: {self.message}"
