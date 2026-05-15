"""
src/agents/vision.py
====================
Vision — Predictive Analyst (Strategic Brain)

The decision-making LLM agent. Receives a consolidated `MarketAnalysis`
bundle from Nick Fury (containing the outputs of Superman, Doctor Strange,
Black Panther, Thor, Aquaman, Spider-Man) and emits a structured
`TradingSignal`.

Hard rules
----------
- Always returns a valid TradingSignal. On any failure (network, JSON parse,
  schema validation, timeout) it falls back to a safe HOLD signal.
- Never accesses the exchange directly. Never sizes positions beyond the
  Pydantic hard cap of 10% (Batman enforces the operational 2% cap later).
- Geometric SL/TP relationship is enforced by the TradingSignal validator.
- Pre-flight: if `MarketAnalysis.is_safe_to_trade` is False, Vision returns
  HOLD without calling the LLM.

Model: configured via `settings.openai_model` (default: gpt-4o).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

# `openai` is a runtime dependency, but we wrap the import so the rest of the
# package can be loaded for unit tests / type-checking even when openai is
# not installed. Tests mock `src.agents.vision.AsyncOpenAI` directly, which
# still works because the name is defined at module level.
try:
    from openai import AsyncOpenAI
    from openai import APIError, APITimeoutError, RateLimitError
except ModuleNotFoundError:  # pragma: no cover - tested via mocks
    AsyncOpenAI = None  # type: ignore[assignment]

    class _OpenAIPlaceholder(Exception):
        """Stand-in for OpenAI exceptions when the SDK isn't installed."""

    APIError = APITimeoutError = RateLimitError = _OpenAIPlaceholder  # type: ignore[misc,assignment]

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.market_data import MarketAnalysis
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Prompt skeletons
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Vision, the strategic decision-making AI of the
Mekka Trading System — a multi-agent autonomous trading platform operating on
Hyperliquid perpetual futures.

You receive consolidated market analysis from six specialized agents:
  • Superman      — multi-timeframe technical analysis
  • Doctor Strange — macro sentiment & Fear/Greed
  • Black Panther  — onchain whale flow, funding, OI
  • Thor           — volatility regime
  • Aquaman        — order book liquidity
  • Spider-Man     — anomaly detection

Your output MUST be a single JSON object matching the TradingSignal schema —
no markdown, no commentary, no code fences. Output JSON only.

Decision principles
-------------------
1. Risk-first: when in doubt, HOLD.
2. Confidence ≥ 0.65 is required for an actionable trade.
3. Risk/reward ≥ 1.5 required for an actionable trade.
4. Honor Thor's volatility multiplier when sizing.
5. Honor Aquaman's liquidity score: < 0.3 → reduce size or HOLD.
6. If Spider-Man flags should_pause, output HOLD.
7. Geometric constraint:
     LONG:  stop_loss < entry < take_profit
     SHORT: take_profit < entry < stop_loss

Schema (all fields required, valid JSON)
----------------------------------------
{
  "action": "LONG" | "SHORT" | "HOLD",
  "confidence": 0.0–1.0,
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "size_pct": 0.005–0.05,
  "leverage": integer 1–5,
  "reasoning": "2-4 sentences",
  "agent_contributions": {"AgentName": "what they contributed"}
}

For HOLD, set entry_price = current price, stop_loss = entry × 0.97,
take_profit = entry × 1.03 (geometry must still validate).
"""


# ---------------------------------------------------------------------------
# Vision Agent
# ---------------------------------------------------------------------------


class Vision(BaseAgent[TradingSignal]):
    """
    Strategic decision-making agent powered by GPT-4o.

    Usage
    -----
        analysis = MarketAnalysis(chart=md, sentiment=sd, ...)
        signal: TradingSignal = await Vision().run(analysis=analysis)
    """

    def __init__(self) -> None:
        super().__init__(
            codename="Vision",
            role=f"Predictive Analyst — strategic LLM ({settings.openai_model})",
        )
        self._client: Optional[AsyncOpenAI] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    async def _run(  # type: ignore[override]
        self,
        analysis: MarketAnalysis,
    ) -> TradingSignal:
        """
        Generate a trading decision from a consolidated MarketAnalysis bundle.
        """
        symbol = analysis.symbol
        price = analysis.price

        # Pre-flight: anomaly halt or extreme volatility → instant HOLD
        if not analysis.is_safe_to_trade:
            self._log.warning(
                f"[Vision] {symbol} pre-flight failed — returning HOLD"
            )
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason="Pre-flight check failed: anomaly or extreme volatility",
            )

        prompt = analysis.to_prompt()

        try:
            raw = await self._call_llm(prompt)
        except (APITimeoutError, RateLimitError, APIError) as exc:
            self._log.error(f"[Vision] OpenAI API error: {exc}")
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"OpenAI API error: {type(exc).__name__}",
            )
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Vision] Unexpected LLM error: {exc}")
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"Unexpected LLM error: {exc}",
            )

        # Parse and validate
        try:
            payload = self._extract_json(raw)
            signal = self._build_signal(payload, symbol=symbol, fallback_price=price)
        except Exception as exc:  # noqa: BLE001
            self._log.error(
                f"[Vision] Failed to parse/validate LLM output: {exc} | raw={raw[:300]}"
            )
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"Output parse/validate error: {exc}",
            )

        self._log.info(f"[Vision] {signal.summary()}")
        return signal

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, user_prompt: str) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return content

    # ------------------------------------------------------------------
    # Parsing & validation
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        """
        Extract a JSON object from the LLM response.

        With response_format=json_object the response is already JSON,
        but we still strip any accidental code fences for resilience.
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # remove leading fence (with or without language tag)
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
        return json.loads(cleaned)

    def _build_signal(
        self,
        payload: dict[str, Any],
        symbol: str,
        fallback_price: float,
    ) -> TradingSignal:
        """
        Construct a TradingSignal from the parsed LLM output, applying
        defensive coercion for fields the LLM may have shaped slightly off.
        """
        action_str = str(payload.get("action", "HOLD")).upper()
        try:
            action = TradeAction(action_str)
        except ValueError:
            action = TradeAction.HOLD

        confidence = float(payload.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        entry_price = float(payload.get("entry_price", fallback_price) or fallback_price)
        if entry_price <= 0:
            entry_price = fallback_price

        # SL / TP — coerce away from invalid geometry for HOLD
        stop_loss = float(payload.get("stop_loss", 0) or 0)
        take_profit = float(payload.get("take_profit", 0) or 0)

        if action == TradeAction.HOLD:
            # For HOLD we fabricate a passing geometry — TradingSignal model
            # only enforces SL/TP relationships for LONG/SHORT.
            stop_loss = stop_loss or entry_price * 0.97
            take_profit = take_profit or entry_price * 1.03

        size_pct = float(payload.get("size_pct", 0.0))
        size_pct = max(0.0, min(0.10, size_pct))  # hard cap at Pydantic limit

        leverage_raw = payload.get("leverage", 1)
        try:
            leverage = max(1, min(settings.max_leverage, int(leverage_raw)))
        except (TypeError, ValueError):
            leverage = 1

        reasoning = str(payload.get("reasoning", "")).strip()
        contributions = payload.get("agent_contributions", {})
        if not isinstance(contributions, dict):
            contributions = {}
        contributions = {str(k): str(v) for k, v in contributions.items()}

        return TradingSignal(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_pct=size_pct if action != TradeAction.HOLD else 0.001,
            leverage=leverage,
            reasoning=reasoning,
            agent_contributions=contributions,
            metadata={
                "model": settings.openai_model,
                "fallback": False,
            },
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_hold(symbol: str, price: float, reason: str) -> TradingSignal:
        """
        Return a defensive HOLD signal when anything goes wrong.

        The geometry is fabricated to pass the Pydantic validator while
        making it crystal-clear to downstream agents that this is a HOLD.
        """
        return TradingSignal(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=price,
            stop_loss=price * 0.97,
            take_profit=price * 1.03,
            size_pct=0.001,  # non-zero to satisfy gt=0 constraint
            leverage=1,
            reasoning=f"FALLBACK HOLD: {reason}",
            agent_contributions={"Vision": "Fallback path — no actionable signal generated"},
            metadata={"model": settings.openai_model, "fallback": True, "fallback_reason": reason},
        )
