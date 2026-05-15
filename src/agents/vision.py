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
from typing import TYPE_CHECKING, Any, Optional

from src.agents.llm_client import LLMClient, make_llm_client

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
        self._llm = make_llm_client()
        super().__init__(
            codename="Vision",
            role=f"Predictive Analyst — strategic LLM ({self._llm.active_provider})",
        )
        # Story 128 — SemanticEpisodicStore injetado pelo LangGraph quando disponível.
        # None = fallback para AgentMemoryStore SQL (Story 063).
        # Definido por make_checkpointed_graph() via fury._vision._semantic_store = store.
        self._semantic_store: Any = None  # SemanticEpisodicStore | None

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

        # Story 063 / Story 128 — Episodic Memory: enrich prompt with historical
        # pattern context. Story 128 uses semantic search when _semantic_store is
        # available (LangGraph mode); falls back to SQL equality search otherwise.
        # Fails silently — Vision always gets a prompt either way.
        try:
            memory_block = await self._build_memory_block(
                analysis, semantic_store=self._semantic_store
            )
            if memory_block:
                prompt = prompt + "\n\n" + memory_block
        except Exception as _mem_exc:  # noqa: BLE001
            self._log.debug(f"[Vision] Episodic memory fetch skipped: {_mem_exc}")

        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Vision] LLM error: {exc}")
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"LLM error: {type(exc).__name__}: {exc}",
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
    # Story 063 — Episodic Memory helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _build_memory_block(
        analysis: "MarketAnalysis",  # type: ignore[name-defined]
        semantic_store: Optional[Any] = None,
    ) -> str:
        """
        Story 063 / Story 128 — Episodic memory block for Vision's prompt.

        Routing:
          • semantic_store is not None (LangGraph mode, Story 128):
            Uses SemanticEpisodicStore.build_context_snippet() — cosine similarity
            on OpenAI text-embedding-3-small. Richer than RSI ±10 bucket matching.

          • semantic_store is None (classic mode, Story 063):
            Falls back to AgentMemoryStore.query_similar() — SQL equality/range.

        Returns an empty string on any failure — Vision always gets a prompt.
        """
        chart = analysis.chart
        symbol = analysis.symbol
        rsi = chart.rsi_14 if chart else None
        trend = chart.trend.value if chart else "NEUTRAL"
        vol_elevated = bool(chart.volume_spike) if chart else False

        # ── Story 128 — Semantic path ──────────────────────────────────────
        if semantic_store is not None:
            snippets: list[str] = []
            for action in ("LONG", "SHORT"):
                try:
                    snippet = await semantic_store.build_context_snippet(
                        symbol=symbol,
                        action=action,
                        rsi=rsi,
                        trend=trend,
                        volume_elevated=vol_elevated,
                        confidence=0.75,  # neutral confidence para query aberta
                        limit=8,
                    )
                    if snippet:
                        snippets.append(snippet)
                except Exception as _exc:  # noqa: BLE001
                    pass  # individual direction fails silently

            if not snippets:
                return ""

            return (
                "=== Historical Pattern Memory (Semantic Search) ===\n"
                + "\n\n".join(snippets)
                + "\n\nUse this historical context to calibrate your confidence. "
                "Low win-rate patterns warrant higher conservatism or HOLD."
            )

        # ── Story 063 — SQL fallback path ──────────────────────────────────
        from src.persistence.agent_memory import AgentMemoryStore  # noqa: WPS433

        long_ctx = await AgentMemoryStore.query_similar(
            symbol=symbol, action="LONG", rsi=rsi, trend=trend, limit=12
        )
        short_ctx = await AgentMemoryStore.query_similar(
            symbol=symbol, action="SHORT", rsi=rsi, trend=trend, limit=12
        )

        sql_snippets: list[str] = []
        if long_ctx.has_data:
            sql_snippets.append(AgentMemoryStore.build_context_snippet(long_ctx))
        if short_ctx.has_data:
            sql_snippets.append(AgentMemoryStore.build_context_snippet(short_ctx))

        if not sql_snippets:
            return ""

        return (
            "=== Historical Pattern Memory ===\n"
            + "\n\n".join(sql_snippets)
            + "\n\nUse this historical context to calibrate your confidence. "
            "Low win-rate patterns warrant higher conservatism or HOLD."
        )

    # ------------------------------------------------------------------
    # Story 130 — Iterative Reflection: Vision revises with critic feedback
    # ------------------------------------------------------------------

    async def revise(
        self,
        analysis: MarketAnalysis,
        critique_context: str,
        round_num: int,
    ) -> TradingSignal:
        """
        Re-generate a TradingSignal with VisionCritic feedback appended.

        Called by NickFury's reflection loop when VisionCritic returns AMEND
        or REJECT. Vision sees the original analysis + the critic's reasoning
        and may revise its decision. The `critique_context` block is appended
        to the standard analysis prompt so Vision knows what specifically
        needs to be reconsidered.

        On any failure, returns a defensive HOLD (same as _run()).
        Never throws — fail-silent is critical because this runs mid-cycle.
        """
        symbol = analysis.symbol
        price = analysis.price

        if not analysis.is_safe_to_trade:
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason="Pre-flight failed (revise)",
            )

        prompt = analysis.to_prompt()

        # Episodic memory enrichment (same path as _run)
        try:
            memory_block = await self._build_memory_block(
                analysis, semantic_store=self._semantic_store
            )
            if memory_block:
                prompt = prompt + "\n\n" + memory_block
        except Exception as _mem_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:revise] Memory fetch skipped: {_mem_exc}")

        # Append critic feedback block — the key addition vs _run()
        prompt = prompt + "\n\n" + critique_context

        self._log.info(f"[Vision:Reflection] {symbol} revising — round {round_num}")

        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Vision:revise] LLM error: {exc}")
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"LLM error (revise r{round_num}): {type(exc).__name__}: {exc}",
            )

        try:
            payload = self._extract_json(raw)
            signal = self._build_signal(payload, symbol=symbol, fallback_price=price)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Vision:revise] Parse error r{round_num}: {exc}")
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"Parse error (revise r{round_num}): {exc}",
            )

        # Tag the signal with reflection metadata
        new_meta = dict(signal.metadata or {})
        new_meta["reflection_round"] = round_num
        signal = signal.model_copy(update={"metadata": new_meta})

        self._log.info(
            f"[Vision:Reflection] {symbol} R{round_num} → {signal.summary()}"
        )
        return signal

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, user_prompt: str) -> str:
        return await self._llm.chat(_SYSTEM_PROMPT, user_prompt)

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
