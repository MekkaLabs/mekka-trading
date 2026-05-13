"""
src/models/critique.py
======================
Pydantic models for the Vision Critic layer (Story 031).

A `VisionCritique` is the structured output of a second-look LLM that
reviews a `TradingSignal` against the same `MarketAnalysis` Vision
saw. The critic returns one of three actions:

  • ENDORSE — the original signal stands as-is.
  • AMEND   — the original signal is mostly right, but with field
              overrides (smaller size, tighter SL, etc.).
  • REJECT  — the signal should not be executed; downgrade to HOLD.

The critic is **advisory but binding when on**: when
`settings.vision_critic_enabled=True`, Nick Fury applies the
critique before passing the signal to Batman. When off, signals
flow unchanged.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.utils.time import utc_now


class CritiqueAction(str, Enum):
    """The three possible verdicts of the second-look LLM."""

    ENDORSE = "ENDORSE"
    AMEND = "AMEND"
    REJECT = "REJECT"


class VisionCritique(BaseModel):
    """
    Structured second-look on a TradingSignal.

    Attributes
    ----------
    schema_version           : Migration safety
    timestamp                : When the critique was generated (UTC)
    symbol                   : Asset the critique applies to
    action                   : ENDORSE / AMEND / REJECT
    confidence_delta         : Critic's estimate of how much it
                               disagrees with the original signal,
                               on a 0.0–1.0 scale (0 = full agreement)
    amended_size_pct         : When action=AMEND, the suggested new
                               size_pct. None means "no change".
    amended_leverage         : When action=AMEND, the suggested new
                               leverage. None means "no change".
    amended_stop_loss        : Optional new SL for AMEND.
    amended_take_profit      : Optional new TP for AMEND.
    reasoning                : Human-readable explanation (2-4 sentences)
    fallback                 : True when the critic ran into an error
                               and emitted a defensive ENDORSE.
    """

    schema_version: int = Field(default=1)
    timestamp: datetime = Field(default_factory=utc_now)
    symbol: str
    action: CritiqueAction = Field(default=CritiqueAction.ENDORSE)
    confidence_delta: float = Field(default=0.0, ge=0.0, le=1.0)

    amended_size_pct: Optional[float] = Field(default=None, ge=0.0, le=0.10)
    amended_leverage: Optional[int] = Field(default=None, ge=1, le=50)
    amended_stop_loss: Optional[float] = Field(default=None, gt=0.0)
    amended_take_profit: Optional[float] = Field(default=None, gt=0.0)

    reasoning: str = Field(default="")
    fallback: bool = Field(default=False)

    def is_actionable(self) -> bool:
        """True when the critique should change the signal flow."""
        return self.action in (CritiqueAction.AMEND, CritiqueAction.REJECT)

    def summary(self) -> str:
        tag = "FALLBACK" if self.fallback else self.action.value
        bits = [f"[Critic/{tag}] {self.symbol} delta={self.confidence_delta:.2f}"]
        if self.amended_size_pct is not None:
            bits.append(f"size→{self.amended_size_pct:.4f}")
        if self.amended_leverage is not None:
            bits.append(f"lev→{self.amended_leverage}x")
        return " ".join(bits)

    def to_audit_payload(self) -> dict:
        return self.model_dump(mode="json")
