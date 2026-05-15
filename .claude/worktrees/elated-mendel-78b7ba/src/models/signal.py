"""
src/models/signal.py
====================
Pydantic v2 models representing trading signals and market regime assessments.

Agent → Model mapping
---------------------
- Vision (GPT-4)  → TradingSignal   (the primary trade decision)
- Flash           → MomentumSignal  (intra-candle momentum / scalp window)
- Professor X     → MarketRegime    (global macro regime classification)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ==============================================================================
# Enumerations
# ==============================================================================


class TradeAction(str, Enum):
    """The three possible trade actions Vision can output."""
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class MomentumDirection(str, Enum):
    """Direction of the momentum signal detected by Flash."""
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"


class GlobalRegime(str, Enum):
    """
    Macro market regime classification used by Professor X.
    Affects position sizing multipliers and strategy selection.
    """
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"


# ==============================================================================
# Vision — Primary Trade Decision
# ==============================================================================


class TradingSignal(BaseModel):
    """
    The primary output of Vision (GPT-4) — a structured trade decision.

    This is the central artifact of the Mekka Trading system. It flows from
    Vision → Batman (validation) → Iron Man (execution).

    Attributes
    ----------
    timestamp           : When the signal was generated
    symbol              : Asset to trade (e.g. 'BTC')
    action              : LONG, SHORT, or HOLD
    confidence          : Model confidence 0.0–1.0
    entry_price         : Suggested entry price
    stop_loss           : Stop-loss price
    take_profit         : Primary take-profit price
    size_pct            : Position size as fraction of equity (e.g. 0.02 = 2%)
    leverage            : Leverage multiplier (1–50)
    reasoning           : LLM's explanation of the decision
    agent_contributions : Which agents influenced the decision and how
    metadata            : Optional extra data (e.g. model name, tokens used)
    """

    schema_version: int = Field(default=1, description="Schema version for migration safety")
    timestamp: datetime = Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    symbol: str = Field(..., description="Asset symbol, e.g. 'BTC'")
    action: TradeAction = Field(..., description="Trade direction or HOLD")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence (0–1)")
    entry_price: float = Field(..., gt=0, description="Suggested entry price")
    stop_loss: float = Field(..., gt=0, description="Stop-loss trigger price")
    take_profit: float = Field(..., gt=0, description="Primary take-profit price")
    size_pct: float = Field(
        ..., gt=0, le=1.0,
        description="Fraction of equity to allocate (e.g. 0.02 = 2%)"
    )
    leverage: int = Field(..., ge=1, le=50, description="Leverage multiplier")
    reasoning: str = Field(
        default="",
        description="LLM explanation — 2-4 sentences describing the rationale"
    )
    agent_contributions: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent_name → contribution_description"
    )
    metadata: Optional[Dict[str, object]] = Field(
        default=None,
        description="Optional: model name, token counts, latency, etc."
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("size_pct")
    @classmethod
    def cap_size_pct(cls, v: float) -> float:
        """Hard cap: never more than 10% equity in a single trade."""
        if v > 0.10:
            raise ValueError(
                f"size_pct={v:.3f} exceeds hard cap of 10%. "
                "Vision must not request more than 10% equity per trade."
            )
        return v

    @model_validator(mode="after")
    def validate_sl_tp_direction(self) -> "TradingSignal":
        """
        Ensure stop-loss and take-profit are on the correct side of the entry.

        LONG  → stop_loss < entry_price < take_profit
        SHORT → take_profit < entry_price < stop_loss
        HOLD  → no geometric constraint applied
        """
        if self.action == TradeAction.LONG:
            if self.stop_loss >= self.entry_price:
                raise ValueError(
                    f"LONG signal: stop_loss ({self.stop_loss}) must be < entry ({self.entry_price})"
                )
            if self.take_profit <= self.entry_price:
                raise ValueError(
                    f"LONG signal: take_profit ({self.take_profit}) must be > entry ({self.entry_price})"
                )
        elif self.action == TradeAction.SHORT:
            if self.stop_loss <= self.entry_price:
                raise ValueError(
                    f"SHORT signal: stop_loss ({self.stop_loss}) must be > entry ({self.entry_price})"
                )
            if self.take_profit >= self.entry_price:
                raise ValueError(
                    f"SHORT signal: take_profit ({self.take_profit}) must be < entry ({self.entry_price})"
                )
        return self

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def risk_reward_ratio(self) -> float:
        """
        Absolute risk/reward ratio.

        R:R = |take_profit - entry| / |entry - stop_loss|

        A value >= 1.5 is typically required to proceed (see settings).
        Returns 0.0 for HOLD signals or if the denominator is zero.
        """
        if self.action == TradeAction.HOLD:
            return 0.0
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk == 0:
            return 0.0
        return reward / risk

    @property
    def is_actionable(self) -> bool:
        """
        True when the signal should proceed to execution.

        Conditions:
        - action is LONG or SHORT (not HOLD)
        - confidence >= 0.60
        - risk/reward >= 1.5
        """
        if self.action == TradeAction.HOLD:
            return False
        if self.confidence < 0.60:
            return False
        if self.risk_reward_ratio < 1.5:
            return False
        return True

    @property
    def stop_loss_pct(self) -> float:
        """Stop-loss distance as a percentage of entry price."""
        return abs(self.entry_price - self.stop_loss) / self.entry_price

    @property
    def take_profit_pct(self) -> float:
        """Take-profit distance as a percentage of entry price."""
        return abs(self.take_profit - self.entry_price) / self.entry_price

    @property
    def notional_size(self) -> float:
        """Dollar notional at the entry price before leverage is applied."""
        return self.entry_price  # caller multiplies by (equity * size_pct)

    def summary(self) -> str:
        """Short one-line summary for logs and Telegram."""
        rr = self.risk_reward_ratio
        return (
            f"[{self.symbol}] {self.action.value} @ {self.entry_price:,.4f} | "
            f"SL={self.stop_loss:,.4f} TP={self.take_profit:,.4f} | "
            f"Confidence={self.confidence:.0%} | R:R={rr:.2f} | "
            f"Size={self.size_pct:.1%} {self.leverage}x | "
            f"Actionable={'YES' if self.is_actionable else 'NO'}"
        )


# ==============================================================================
# Flash — Intra-Candle Momentum Signal
# ==============================================================================


class MomentumSignal(BaseModel):
    """
    Short-term momentum signal produced by Flash.

    Flash monitors price action inside the current candle for burst moves,
    breakouts, or momentum reversals that may warrant an immediate entry
    rather than waiting for the next 4h candle.

    Attributes
    ----------
    symbol              : Asset symbol
    timestamp           : Signal generation time
    direction           : UP, DOWN, or SIDEWAYS
    strength            : Momentum strength 0.0–1.0
    entry_window_seconds: How many seconds remain for a valid momentum entry
    price_change_pct    : Price move that triggered this signal (as fraction)
    volume_multiplier   : Volume relative to rolling average (e.g. 2.5 = 2.5x avg)
    notes               : Optional human-readable description
    """

    symbol: str
    timestamp: datetime = Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    direction: MomentumDirection = Field(default=MomentumDirection.SIDEWAYS)
    strength: float = Field(..., ge=0.0, le=1.0, description="Momentum strength 0–1")
    entry_window_seconds: int = Field(
        default=300,
        ge=0,
        description="Seconds until momentum is expected to fade"
    )
    price_change_pct: float = Field(
        default=0.0,
        description="Price change that triggered this signal (e.g. 0.02 = 2%)"
    )
    volume_multiplier: float = Field(
        default=1.0,
        ge=0,
        description="Volume as multiple of rolling average"
    )
    notes: Optional[str] = None

    @property
    def is_strong(self) -> bool:
        """True when momentum strength exceeds 0.70 and volume is elevated."""
        return self.strength >= 0.70 and self.volume_multiplier >= 1.5

    @property
    def is_expired(self) -> bool:
        """True when the entry window has closed."""
        return self.entry_window_seconds <= 0

    def summary(self) -> str:
        return (
            f"[Flash] {self.symbol} {self.direction.value} | "
            f"Strength={self.strength:.0%} | "
            f"Change={self.price_change_pct:+.2%} | "
            f"Vol={self.volume_multiplier:.1f}x | "
            f"Window={self.entry_window_seconds}s"
        )


# ==============================================================================
# Professor X — Global Market Regime
# ==============================================================================


class MarketRegime(BaseModel):
    """
    Global macro regime assessment produced by Professor X.

    Professor X analyses the overall crypto market structure — BTC trend,
    correlation across assets, risk appetite — and outputs a regime label
    that modulates the aggressiveness of the entire trading system.

    Attributes
    ----------
    timestamp       : Assessment time
    global_regime   : BULL / BEAR / SIDEWAYS / VOLATILE
    btc_trend       : BTC-specific trend direction ('up', 'down', 'sideways')
    risk_on         : True when macro conditions favour risk assets
    position_size_multiplier : Suggested multiplier for all position sizes
    notes           : Free-text regime commentary
    correlated_assets: Which assets are moving together
    """

    timestamp: datetime = Field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    global_regime: GlobalRegime = Field(default=GlobalRegime.SIDEWAYS)
    btc_trend: str = Field(
        default="sideways",
        description="BTC trend: 'up', 'down', or 'sideways'"
    )
    risk_on: bool = Field(
        default=False,
        description="True = macro environment favours risk assets"
    )
    position_size_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Multiply all position sizes by this value based on regime"
    )
    notes: Optional[str] = None
    correlated_assets: List[str] = Field(
        default_factory=list,
        description="Assets currently moving in high correlation"
    )

    @model_validator(mode="after")
    def derive_multiplier(self) -> "MarketRegime":
        """
        Auto-set a sensible position_size_multiplier based on the regime
        if the caller left it at the default of 1.0.
        """
        if self.position_size_multiplier == 1.0:
            mapping = {
                GlobalRegime.BULL: 1.2,
                GlobalRegime.SIDEWAYS: 0.8,
                GlobalRegime.BEAR: 0.6,
                GlobalRegime.VOLATILE: 0.5,
            }
            self.position_size_multiplier = mapping.get(self.global_regime, 1.0)
        return self

    def to_prompt_section(self) -> str:
        lines = [
            "=== Global Market Regime (Professor X) ===",
            f"  Regime      : {self.global_regime.value}",
            f"  BTC Trend   : {self.btc_trend}",
            f"  Risk-On?    : {'YES' if self.risk_on else 'NO'}",
            f"  Size Mult.  : {self.position_size_multiplier:.2f}x",
        ]
        if self.notes:
            lines.append(f"  Notes       : {self.notes}")
        if self.correlated_assets:
            lines.append(f"  Correlated  : {', '.join(self.correlated_assets)}")
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"[Regime] {self.global_regime.value} | "
            f"BTC={self.btc_trend} | "
            f"Risk={'ON' if self.risk_on else 'OFF'} | "
            f"SizeMult={self.position_size_multiplier:.2f}x"
        )
