"""
src/agents/vision_critic.py
============================
Vision Critic — second-look LLM (Story 031).

Reviews a `TradingSignal` produced by Vision against the same
`MarketAnalysis` Vision saw, and produces a `VisionCritique`
(ENDORSE / AMEND / REJECT). Defensive defaults: any failure (timeout,
parse error, schema violation, missing OpenAI lib) collapses to
ENDORSE with `fallback=True` so the original Vision signal stands.

Hard rules
----------
- **Off by default.** `settings.vision_critic_enabled=False`.
  Nick Fury bypasses the critic when the toggle is off.
- **Never strengthens a signal.** Critic can only AMEND with smaller
  size / lower leverage / tighter SL / closer TP — anything else is
  ignored. Rationale: the critic is a safety mechanism, not a
  second strategist.
- **Confidence threshold.** When `critique.confidence_delta <
  settings.vision_critic_min_disagreement`, the action is downgraded
  to ENDORSE — small disagreements aren't worth overriding the primary
  decision.
- **Never throws.** Exceptions wrap into a fallback ENDORSE.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.agents.base import BaseAgent
from src.agents.llm_client import LLMClient, make_llm_client
from src.config.settings import settings
from src.models.critique import CritiqueAction, VisionCritique
from src.models.market_data import MarketAnalysis
from src.models.signal import TradeAction, TradingSignal


_SYSTEM_PROMPT = """You are Vision Critic, a senior risk-aware reviewer of
trading decisions made by Vision (the primary strategist) of the Mekka
Trading System.

ROLE
----
You receive the same MarketAnalysis Vision saw plus Vision's TradingSignal.
Your purpose is to decide whether to ENDORSE, AMEND, or REJECT — and you
must output a single strict JSON object.

OUTPUT FORMAT (JSON object, no markdown, no fences, no commentary)
------------------------------------------------------------------
Schema:
{
  "action": "ENDORSE" | "AMEND" | "REJECT",
  "confidence_delta": 0.0..1.0,
  "amended_size_pct": null | number,
  "amended_leverage": null | integer,
  "amended_stop_loss": null | number,
  "amended_take_profit": null | number,
  "reasoning": "2-4 sentences"
}

METHOD (apply in order)
-----------------------
Step 1: Read the MarketAnalysis. Identify the 2-3 strongest signals and
        the strongest dissenting signal.
Step 2: Cross-check Vision's signal against those signals. Is the action
        coherent? Are size/leverage/SL/TP defensible?
Step 3: Decide:
        - ENDORSE if the analysis cleanly supports the trade.
        - AMEND if the action is right but risk parameters need tightening.
        - REJECT (forces HOLD) if anomalies, low liquidity, or conflict
          dominate.
Step 4: Fill confidence_delta as your honest disagreement
        (0 = none, 1 = total). Deltas < 0.30 typically deserve ENDORSE.
Step 5: When AMEND, fill ONLY the parameters you change; leave others null.

PITFALLS — NEVER
----------------
- NEVER propose larger size, higher leverage, looser stop, or further TP
  than the original. AMEND is only allowed to REDUCE risk.
- NEVER ENDORSE when Spider-Man reports anomaly severity HIGH.
- NEVER REJECT a signal just because confidence is moderate (0.4–0.7) —
  REJECT requires concrete conflicting evidence.
- NEVER output markdown, code fences, or any text outside the JSON object.
- NEVER fill amended_* fields when action is ENDORSE or REJECT.

ACCEPTANCE CRITERIA (verifiable)
--------------------------------
- Output parses as JSON.
- action ∈ {"ENDORSE", "AMEND", "REJECT"}.
- confidence_delta ∈ [0.0, 1.0].
- When action != "AMEND", all amended_* fields are null.
- When action == "AMEND" for LONG: amended_stop_loss (if set) > original SL;
  amended_take_profit (if set) < original TP; amended_size_pct (if set) ≤ original.
- When action == "AMEND" for SHORT: amended_stop_loss (if set) < original SL;
  amended_take_profit (if set) > original TP.
- reasoning has 2-4 sentences (string non-empty).

EXAMPLES
--------
<example name="endorse-clean-long">
Input summary: BULLISH trend strength 0.85, RSI 58, sentiment +0.4,
liquidity score 0.9, anomaly NONE. Vision: LONG, conf 0.78, size 0.02,
leverage 2.
Output:
```json
{"action":"ENDORSE","confidence_delta":0.05,"amended_size_pct":null,
"amended_leverage":null,"amended_stop_loss":null,"amended_take_profit":null,
"reasoning":"Clear trend and liquidity support a long. Sentiment aligns. No anomalies. Risk parameters are appropriate."}
```
</example>

<example name="amend-tighten-stop">
Input summary: BULLISH but ATR-14 elevated, anomaly LOW. Vision: LONG,
SL 4% below entry, size 0.03, leverage 3.
Output:
```json
{"action":"AMEND","confidence_delta":0.25,"amended_size_pct":0.02,
"amended_leverage":2,"amended_stop_loss":null,"amended_take_profit":null,
"reasoning":"Trend supports long but volatility is elevated. Reducing size and leverage to limit drawdown. Stop and TP remain acceptable."}
```
</example>

<example name="reject-anomaly">
Input summary: anomaly HIGH (flash crash detected), should_pause=true.
Vision: LONG (called before anomaly merged).
Output:
```json
{"action":"REJECT","confidence_delta":0.85,"amended_size_pct":null,
"amended_leverage":null,"amended_stop_loss":null,"amended_take_profit":null,
"reasoning":"Spider-Man flags HIGH severity anomaly with should_pause=true. Entering on this state would breach risk policy. Decline to trade until anomaly clears."}
```
</example>
"""


class VisionCritic(BaseAgent[VisionCritique]):
    """
    Second-look LLM. Off by default; turned on via
    `settings.vision_critic_enabled=True`.

    Usage:
        critique = await VisionCritic().run(
            analysis=market_analysis,
            signal=trading_signal,
        )
    """

    def __init__(self) -> None:
        self._llm = make_llm_client()
        super().__init__(
            codename="VisionCritic",
            role=f"Second-look reviewer ({self._llm.active_provider})",
            timeout_s=30.0,  # LLM call (reflection é mais curta que Vision)
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._llm.close()

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(  # type: ignore[override]
        self,
        analysis: MarketAnalysis,
        signal: TradingSignal,
    ) -> VisionCritique:
        symbol = signal.symbol

        # HOLD signals don't need second-look — nothing to override.
        if signal.action == TradeAction.HOLD:
            return VisionCritique(
                symbol=symbol,
                action=CritiqueAction.ENDORSE,
                confidence_delta=0.0,
                reasoning="Original signal is HOLD — critic bypassed.",
                fallback=False,
            )

        prompt = self._build_prompt(analysis=analysis, signal=signal)

        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"Critic LLM error: {exc}")
            return self._fallback_endorse(symbol, reason=f"LLM error: {type(exc).__name__}")

        try:
            payload = self._extract_json(raw)
            critique = self._build_critique(
                payload=payload,
                signal=signal,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"Critic parse/validate failed: {exc} | raw={raw[:200]}")
            return self._fallback_endorse(symbol, reason=f"Parse error: {exc}")

        # Disagreement floor: small deltas downgrade to ENDORSE.
        # Story 050 — threshold is now mode-aware: conservative=0.20,
        # balanced=0.30, aggressive=0.45. Falls back to settings value.
        try:
            from src.config.runtime_mode import get_params as _get_mode_params  # noqa: WPS433
            _min_disagreement = _get_mode_params().get(
                "vision_critic_min_disagreement",
                settings.vision_critic_min_disagreement,
            )
        except Exception:  # noqa: BLE001
            _min_disagreement = settings.vision_critic_min_disagreement

        if (
            critique.action != CritiqueAction.ENDORSE
            and critique.confidence_delta < _min_disagreement
        ):
            critique.action = CritiqueAction.ENDORSE
            critique.amended_size_pct = None
            critique.amended_leverage = None
            critique.amended_stop_loss = None
            critique.amended_take_profit = None
            critique.reasoning = (
                f"{critique.reasoning} (downgraded to ENDORSE: delta "
                f"{critique.confidence_delta:.2f} < threshold "
                f"{_min_disagreement:.2f} [{_get_mode_params().get('label', '?')}])"
            )

        self._log.info(critique.summary())
        return critique

    # ------------------------------------------------------------------
    # Prompt + LLM
    # ------------------------------------------------------------------

    def _build_prompt(self, analysis: MarketAnalysis, signal: TradingSignal) -> str:
        analysis_block = analysis.to_prompt()
        signal_block = (
            f"=== Original Vision Signal ===\n"
            f"  Action      : {signal.action.value}\n"
            f"  Confidence  : {signal.confidence:.2f}\n"
            f"  Entry       : {signal.entry_price:,.4f}\n"
            f"  Stop Loss   : {signal.stop_loss:,.4f}\n"
            f"  Take Profit : {signal.take_profit:,.4f}\n"
            f"  Size %      : {signal.size_pct:.4f}\n"
            f"  Leverage    : {signal.leverage}x\n"
            f"  R:R         : {signal.risk_reward_ratio:.2f}\n"
            f"  Reasoning   : {signal.reasoning}\n"
        )
        return f"{analysis_block}\n\n{signal_block}\n\n=== Decision ===\nReview the signal above. Output JSON only."

    async def _call_llm(self, user_prompt: str) -> str:
        return await self._llm.chat(_SYSTEM_PROMPT, user_prompt)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
        return json.loads(cleaned)

    def _build_critique(
        self,
        payload: dict[str, Any],
        signal: TradingSignal,
    ) -> VisionCritique:
        # Coerce action
        action_str = str(payload.get("action", "ENDORSE")).upper()
        try:
            action = CritiqueAction(action_str)
        except ValueError:
            action = CritiqueAction.ENDORSE

        confidence_delta = float(payload.get("confidence_delta", 0.0))
        confidence_delta = max(0.0, min(1.0, confidence_delta))

        # Amended fields — only honored when AMEND, and only if SAFER
        # than the original. The critic is a safety mechanism — never
        # let it scale UP risk.
        amended_size = self._coerce_amended_size(payload.get("amended_size_pct"), signal)
        amended_lev = self._coerce_amended_leverage(payload.get("amended_leverage"), signal)
        amended_sl = self._coerce_amended_stop_loss(payload.get("amended_stop_loss"), signal)
        amended_tp = self._coerce_amended_take_profit(payload.get("amended_take_profit"), signal)

        return VisionCritique(
            symbol=signal.symbol,
            action=action,
            confidence_delta=confidence_delta,
            amended_size_pct=amended_size if action == CritiqueAction.AMEND else None,
            amended_leverage=amended_lev if action == CritiqueAction.AMEND else None,
            amended_stop_loss=amended_sl if action == CritiqueAction.AMEND else None,
            amended_take_profit=amended_tp if action == CritiqueAction.AMEND else None,
            reasoning=str(payload.get("reasoning", "")).strip(),
            fallback=False,
        )

    @staticmethod
    def _coerce_amended_size(raw: Any, signal: TradingSignal) -> Optional[float]:
        if raw is None:
            return None
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        # Must be smaller than original (safer)
        if v <= 0 or v > signal.size_pct:
            return None
        return v

    @staticmethod
    def _coerce_amended_leverage(raw: Any, signal: TradingSignal) -> Optional[int]:
        if raw is None:
            return None
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return None
        if v < 1 or v > signal.leverage:
            return None
        return v

    @staticmethod
    def _coerce_amended_stop_loss(raw: Any, signal: TradingSignal) -> Optional[float]:
        if raw is None:
            return None
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v <= 0:
            return None
        # "Tighter" SL means closer to entry — for LONG the SL must be
        # ABOVE the original SL (closer to entry from below); for SHORT
        # the SL must be BELOW the original SL (closer from above).
        if signal.action == TradeAction.LONG:
            if v > signal.stop_loss and v < signal.entry_price:
                return v
        elif signal.action == TradeAction.SHORT:
            if v < signal.stop_loss and v > signal.entry_price:
                return v
        return None

    @staticmethod
    def _coerce_amended_take_profit(raw: Any, signal: TradingSignal) -> Optional[float]:
        if raw is None:
            return None
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return None
        if v <= 0:
            return None
        # "Closer" TP means closer to entry — for LONG the TP must be
        # BELOW the original TP (closer from above); for SHORT the TP
        # must be ABOVE the original TP (closer from below).
        if signal.action == TradeAction.LONG:
            if v < signal.take_profit and v > signal.entry_price:
                return v
        elif signal.action == TradeAction.SHORT:
            if v > signal.take_profit and v < signal.entry_price:
                return v
        return None

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_endorse(symbol: str, reason: str) -> VisionCritique:
        return VisionCritique(
            symbol=symbol,
            action=CritiqueAction.ENDORSE,
            confidence_delta=0.0,
            reasoning=f"FALLBACK ENDORSE: {reason}",
            fallback=True,
        )


def apply_critique(signal: TradingSignal, critique: VisionCritique) -> TradingSignal:
    """
    Apply a critique to a signal, returning a new TradingSignal.

    - ENDORSE → return original unchanged
    - AMEND   → apply each amended_* override if present (already
                validated as safer in `_build_critique`)
    - REJECT  → return a defensive HOLD signal preserving symbol +
                geometry-friendly SL/TP, with `metadata.critic_rejected=True`

    Pure function — no side effects.
    """
    if critique.action == CritiqueAction.ENDORSE:
        return signal

    if critique.action == CritiqueAction.REJECT:
        # Build HOLD with geometry that satisfies the TradingSignal
        # validator. Mirrors Vision._fallback_hold conventions.
        meta = dict(signal.metadata or {})
        meta["critic_rejected"] = True
        meta["critic_reason"] = critique.reasoning
        return TradingSignal(
            symbol=signal.symbol,
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=signal.entry_price,
            stop_loss=signal.entry_price * 0.97,
            take_profit=signal.entry_price * 1.03,
            size_pct=0.001,
            leverage=1,
            reasoning=f"Vision Critic REJECT: {critique.reasoning}",
            agent_contributions=signal.agent_contributions,
            metadata=meta,
        )

    # AMEND
    new_meta = dict(signal.metadata or {})
    new_meta["critic_amended"] = True
    new_meta["critic_reason"] = critique.reasoning

    return TradingSignal(
        symbol=signal.symbol,
        action=signal.action,
        confidence=signal.confidence,
        entry_price=signal.entry_price,
        stop_loss=critique.amended_stop_loss or signal.stop_loss,
        take_profit=critique.amended_take_profit or signal.take_profit,
        size_pct=critique.amended_size_pct or signal.size_pct,
        leverage=critique.amended_leverage or signal.leverage,
        reasoning=signal.reasoning,
        agent_contributions=signal.agent_contributions,
        metadata=new_meta,
    )
