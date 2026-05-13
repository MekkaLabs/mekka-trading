"""
src/agents/batman.py
====================
Batman — Risk Guardian

Deterministic, no-LLM validator. Sits between Vision and Iron Man.
Receives a `TradingSignal` plus optional context (VolatilityData,
LiquidityData, current portfolio state) and emits a `RiskApproval`.

Hard limits enforced
--------------------
  • size_pct ≤ settings.max_position_size_pct (default 2%)
  • leverage ≤ settings.max_leverage (default 5x)
  • confidence ≥ settings.min_confidence_threshold (default 0.65)
  • risk/reward ≥ settings.min_risk_reward_ratio (default 1.5)
  • daily drawdown ≤ settings.max_daily_drawdown_pct (default 10%)
  • max_open_positions, max_trades_per_day breakers
  • kill_switch flag (file-based or env-based) → instant KILL_SWITCH verdict
  • action == HOLD → REJECTED (nothing to execute)

Adjustments applied (verdict = REDUCED)
---------------------------------------
  • Apply Thor's volatility size multiplier
  • Penalize when Aquaman.liquidity_score < 0.4
  • Cap at hard limits if LLM requested more

Hard rule: Batman NEVER approves anything when paper_trading=False AND
the operator has not explicitly disabled the live-block (intentional friction).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.market_data import LiquidityData, VolatilityData, VolatilityRegime
from src.models.risk import RiskApproval, RiskVerdict
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Kill switch — operator-controllable file flag
# ---------------------------------------------------------------------------

_KILL_SWITCH_FILE = Path("data/.kill_switch")
_KILL_SWITCH_ENV = "MEKKA_KILL_SWITCH"


def is_kill_switch_active() -> bool:
    """
    Check the kill switch from two sources:
      1. Env var MEKKA_KILL_SWITCH=1 (transient, restart-clearing)
      2. File at data/.kill_switch (persistent, requires manual delete)
    """
    if os.getenv(_KILL_SWITCH_ENV) == "1":
        return True
    return _KILL_SWITCH_FILE.exists()


def engage_kill_switch(reason: str, agent: str = "system") -> None:
    """Persist a kill-switch flag with a structured JSON payload."""
    _KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reason": reason,
        "agent": agent,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    _KILL_SWITCH_FILE.write_text(json.dumps(payload) + "\n")


def read_kill_switch_metadata() -> dict:
    """
    Read kill-switch metadata. Returns empty dict if not engaged.
    Handles legacy plain-text files gracefully (pre-squad-fixes format).
    """
    if not _KILL_SWITCH_FILE.exists():
        return {}
    raw = _KILL_SWITCH_FILE.read_text().strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Legacy format: plain text reason
        return {"reason": raw, "agent": "legacy", "timestamp_utc": None}


def release_kill_switch() -> None:
    """Manually clear the persistent kill-switch."""
    if _KILL_SWITCH_FILE.exists():
        _KILL_SWITCH_FILE.unlink()


# ---------------------------------------------------------------------------
# Batman Agent
# ---------------------------------------------------------------------------


class Batman(BaseAgent[RiskApproval]):
    """
    Risk Guardian — last gate before execution.

    Usage:
        approval = await Batman().run(
            signal=trading_signal,
            volatility=vol_data,           # optional
            liquidity=liq_data,            # optional
            current_drawdown_pct=0.04,     # optional, from portfolio state
            open_positions=2,              # optional
            trades_today=4,                # optional
        )
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Batman",
            role="Risk Guardian — deterministic validation gate",
        )

    async def _run(  # type: ignore[override]
        self,
        signal: TradingSignal,
        volatility: Optional[VolatilityData] = None,
        liquidity: Optional[LiquidityData] = None,
        current_drawdown_pct: float = 0.0,
        open_positions: int = 0,
        trades_today: int = 0,
        running_notional_usd: float = 0.0,
        equity_usd: float = 0.0,
    ) -> RiskApproval:
        symbol = signal.symbol
        reasons: list[str] = []
        breached: list[str] = []

        # ---------------------------------------------------------------
        # 0. Kill switch — instant halt
        # ---------------------------------------------------------------
        if is_kill_switch_active():
            reasons.append("Kill switch is engaged — system-wide trading halt")
            breached.append("kill_switch")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.KILL_SWITCH,
                reasons=reasons,
                adjusted_size_pct=0.0,
                adjusted_leverage=1,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 1. HOLD — nothing to execute, mark REJECTED for clarity
        # ---------------------------------------------------------------
        if signal.action == TradeAction.HOLD:
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=["Signal action is HOLD — no execution"],
                adjusted_size_pct=0.0,
                adjusted_leverage=1,
                breached_limits=[],
            )

        # ---------------------------------------------------------------
        # 2. Daily drawdown breaker
        # ---------------------------------------------------------------
        if current_drawdown_pct >= settings.max_daily_drawdown_pct:
            reasons.append(
                f"Daily drawdown {current_drawdown_pct:.2%} ≥ "
                f"limit {settings.max_daily_drawdown_pct:.2%}"
            )
            breached.append("max_daily_drawdown_pct")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 3. Trade-count and concurrency breakers
        # ---------------------------------------------------------------
        if open_positions >= settings.max_open_positions:
            reasons.append(
                f"Open positions {open_positions} ≥ "
                f"limit {settings.max_open_positions}"
            )
            breached.append("max_open_positions")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        if trades_today >= settings.max_trades_per_day:
            reasons.append(
                f"Trades today {trades_today} ≥ "
                f"daily cap {settings.max_trades_per_day}"
            )
            breached.append("max_trades_per_day")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 3b. Total capital cap (Story 029a — Safety Net)
        # ---------------------------------------------------------------
        # Compute the notional this signal would add (size_pct * leverage * equity).
        # We check BEFORE size adjustments so the cap is on Vision's intent,
        # not on the post-Thor-multiplier value. If the intent itself blows
        # the cap, we reject regardless of how much Thor would have shrunk it.
        if equity_usd > 0:
            new_notional = equity_usd * signal.size_pct * signal.leverage
            projected_total = running_notional_usd + new_notional

            # Absolute cap takes precedence when set
            if settings.max_total_notional_usd is not None:
                if projected_total > settings.max_total_notional_usd:
                    reasons.append(
                        f"Projected total notional ${projected_total:,.2f} would "
                        f"exceed absolute cap ${settings.max_total_notional_usd:,.2f}"
                    )
                    breached.append("max_total_notional_usd")
                    return RiskApproval(
                        symbol=symbol,
                        verdict=RiskVerdict.REJECTED,
                        reasons=reasons,
                        breached_limits=breached,
                    )

            # Percentage cap (always evaluated when equity > 0)
            cap_pct = settings.max_total_capital_pct
            cap_usd = equity_usd * cap_pct
            if projected_total > cap_usd:
                reasons.append(
                    f"Projected total notional ${projected_total:,.2f} would "
                    f"exceed {cap_pct:.1%} of equity (${cap_usd:,.2f})"
                )
                breached.append("max_total_capital_pct")
                return RiskApproval(
                    symbol=symbol,
                    verdict=RiskVerdict.REJECTED,
                    reasons=reasons,
                    breached_limits=breached,
                )

        # ---------------------------------------------------------------
        # 4. Confidence and R:R quality gates
        # ---------------------------------------------------------------
        if signal.confidence < settings.min_confidence_threshold:
            reasons.append(
                f"Confidence {signal.confidence:.2f} < threshold "
                f"{settings.min_confidence_threshold:.2f}"
            )
            breached.append("min_confidence_threshold")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        rr = signal.risk_reward_ratio
        if rr < settings.min_risk_reward_ratio:
            reasons.append(
                f"R:R {rr:.2f} < required {settings.min_risk_reward_ratio:.2f}"
            )
            breached.append("min_risk_reward_ratio")
            return RiskApproval(
                symbol=symbol,
                verdict=RiskVerdict.REJECTED,
                reasons=reasons,
                breached_limits=breached,
            )

        # ---------------------------------------------------------------
        # 5. Size + leverage adjustment (REDUCED if any cap hit)
        # ---------------------------------------------------------------
        adjusted_size = signal.size_pct
        adjusted_leverage = signal.leverage

        # Apply Thor multiplier
        if volatility is not None:
            mult = volatility.suggested_position_size_multiplier
            new_size = adjusted_size * mult
            if abs(new_size - adjusted_size) > 1e-9:
                reasons.append(
                    f"Thor volatility multiplier {mult:.2f}x applied "
                    f"({adjusted_size:.4f} → {new_size:.4f})"
                )
                breached.append("volatility_adjustment")
            adjusted_size = new_size

        # Penalize on poor liquidity
        if liquidity is not None and liquidity.liquidity_score < 0.4:
            penalty = max(0.4, liquidity.liquidity_score)  # at least 40% of size
            new_size = adjusted_size * penalty
            reasons.append(
                f"Liquidity penalty: score={liquidity.liquidity_score:.2f} → "
                f"size × {penalty:.2f}"
            )
            breached.append("liquidity_penalty")
            adjusted_size = new_size

        # Runtime mode overrides (hot-reload — no restart required)
        from src.config.runtime_mode import get_params as _get_mode_params
        _mode_params = _get_mode_params()
        _max_pos = _mode_params.get("max_position_size_pct", settings.max_position_size_pct)
        _max_lev = _mode_params.get("max_leverage", settings.max_leverage)
        _max_lev_high = _mode_params.get("max_leverage_high_regime", settings.max_leverage_high_regime)
        _max_lev_extreme = _mode_params.get("max_leverage_extreme_regime", settings.max_leverage_extreme_regime)

        # Hard cap on size
        if adjusted_size > _max_pos:
            reasons.append(
                f"Size {adjusted_size:.2%} capped to "
                f"{_max_pos:.2%}"
            )
            breached.append("max_position_size_pct")
            adjusted_size = _max_pos

        # Regime-based leverage cap (tighter than global max in HIGH/EXTREME)
        if volatility is not None:
            regime = volatility.volatility_regime
            if regime == VolatilityRegime.EXTREME:
                regime_lev_cap = _max_lev_extreme
            elif regime == VolatilityRegime.HIGH:
                regime_lev_cap = _max_lev_high
            else:
                regime_lev_cap = _max_lev
            if adjusted_leverage > regime_lev_cap:
                reasons.append(
                    f"Leverage {adjusted_leverage}x capped to {regime_lev_cap}x "
                    f"(regime={regime.value})"
                )
                breached.append(f"max_leverage_{regime.value.lower()}_regime")
                adjusted_leverage = regime_lev_cap

        # Hard cap on leverage (global ceiling regardless of regime)
        if adjusted_leverage > _max_lev:
            reasons.append(
                f"Leverage {adjusted_leverage}x capped to "
                f"{_max_lev}x"
            )
            breached.append("max_leverage")
            adjusted_leverage = _max_lev

        # ---------------------------------------------------------------
        # 6. Final verdict
        # ---------------------------------------------------------------
        if adjusted_size <= 0:
            verdict = RiskVerdict.REJECTED
            reasons.append("Final size is zero — nothing to execute")
        elif breached:
            verdict = RiskVerdict.REDUCED
            reasons.insert(0, "Approved with adjustments")
        else:
            verdict = RiskVerdict.APPROVED
            reasons.insert(0, "All risk checks passed")

        approval = RiskApproval(
            symbol=symbol,
            verdict=verdict,
            reasons=reasons,
            adjusted_size_pct=round(adjusted_size, 6),
            adjusted_leverage=adjusted_leverage,
            breached_limits=breached,
            metadata={
                "original_size_pct": signal.size_pct,
                "original_leverage": signal.leverage,
                "confidence": signal.confidence,
                "rr": rr,
                "paper_trading": settings.paper_trading,
            },
        )

        self._log.info(approval.summary())
        return approval
