"""
src/agents/vision_moa.py
========================
VisionMoA — Mixture of Agents Vision (Story 131)

AutoGen MoA (Mixture of Agents) pattern aplicado à geração de TradingSignal:

  1. Três LLMs geram TradingSignal independentemente, em paralelo:
       Proposal-A: GPT-4o          (alta capacidade, modelo primário)
       Proposal-B: Claude Sonnet   (arquitetura diversa, perspectiva independente)
       Proposal-C: GPT-4o-mini     (rápido, voto adicional de baixo custo)

  2. Orchestrator LLM (GPT-4o ≥ Claude) sintetiza o consenso em um sinal final.

Fail-silent rules
-----------------
- Se < 2 proposals gerarem com sucesso → fallback para Vision._run() clássico.
- Se orchestrator falhar → vote fallback (maior contagem de ação + confidence).
- Proposals individuais que falham são silenciosamente excluídas.
- Nunca lança exceção — sempre retorna um TradingSignal válido.

Ativação
--------
  VISION_MOA_ENABLED=true  (settings.vision_moa_enabled)

Toggle em NickFury._cycle_for_symbol():
  se vision_moa_enabled → VisionMoA.run(analysis)
  caso contrário → Vision._run(analysis)  [comportamento pré-Story-131]
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from src.agents.llm_client import LLMClient
from src.agents.vision import Vision, _SYSTEM_PROMPT  # reutiliza prompt padrão
from src.config.settings import settings
from src.models.market_data import MarketAnalysis
from src.models.signal import TradeAction, TradingSignal


# ---------------------------------------------------------------------------
# Orchestrator system prompt
# ---------------------------------------------------------------------------

_ORCHESTRATOR_SYSTEM = """You are the MoA Synthesis Orchestrator for the Mekka Trading System.

ROLE
----
Three independent Vision LLMs analyzed identical market data and produced
the TradingSignal proposals below. Your purpose is to synthesize one
consensus TradingSignal and emit a single strict JSON object.

OUTPUT FORMAT (JSON object only — no markdown, no fences, no commentary)
------------------------------------------------------------------------
Schema:
{
  "action": "LONG" | "SHORT" | "HOLD",
  "confidence": 0.0..1.0,
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "size_pct": 0.005..0.05,
  "leverage": integer 1..5,
  "reasoning": "2-4 sentences",
  "agent_contributions": {"model_name": "brief verdict"}
}

METHOD (apply in order)
-----------------------
Step 1: Inspect the three proposals. Count action votes.
Step 2: ACTION — majority vote: if 2 or 3 agents agree, use that action.
        If all 3 differ (no majority), output HOLD.
Step 3: CONFIDENCE — confidence-weighted average across ALL three proposals.
Step 4: ENTRY/STOP_LOSS/TAKE_PROFIT — confidence-weighted average of the
        AGREEING proposals only (those matching the majority action).
        For HOLD: entry=current_price, stop=entry×0.97, take=entry×1.03.
Step 5: SIZE_PCT/LEVERAGE — confidence-weighted average of the agreeing
        proposals only.
Step 6: REASONING — 2-4 sentences explaining the consensus and any
        notable dissent.
Step 7: AGENT_CONTRIBUTIONS — map of model name → 1-sentence verdict
        (one entry per proposal).

HARD CONSTRAINTS (same as Vision — NEVER violate)
-------------------------------------------------
- LONG:  stop_loss < entry_price < take_profit.
- SHORT: take_profit < entry_price < stop_loss.
- HOLD:  entry=current_price, stop=entry*0.97, take=entry*1.03.
- confidence ∈ [0.0, 1.0].
- size_pct ∈ [0.005, 0.05].
- leverage ∈ [1, 5] (integer).

PITFALLS — NEVER
----------------
- NEVER pick an action that NO proposal voted for.
- NEVER emit a tie-breaking action other than HOLD when there is no majority.
- NEVER include dissenting proposals in the entry/SL/TP average.
- NEVER emit confidence > max(proposals.confidence) — synthesis cannot
  invent certainty.
- NEVER output markdown, code fences, comments, or any text outside the
  JSON object.
- NEVER omit agent_contributions; include all three proposing models.

ACCEPTANCE CRITERIA (verifiable)
--------------------------------
- Output parses as JSON.
- action ∈ {"LONG", "SHORT", "HOLD"}.
- For LONG: stop_loss < entry_price < take_profit (strict).
- For SHORT: take_profit < entry_price < stop_loss (strict).
- confidence ∈ [0, 1]; size_pct ∈ [0.005, 0.05]; leverage ∈ {1,2,3,4,5}.
- len(agent_contributions) == 3.
- reasoning has 2-4 sentences (string non-empty).

EXAMPLES
--------
<example name="majority-long-with-dissent">
Proposals: GPT-4o=LONG conf 0.80, Claude-Sonnet=LONG conf 0.65, GPT-4o-mini=HOLD conf 0.50.
Output:
```json
{"action":"LONG","confidence":0.74,"entry_price":68500.0,
"stop_loss":67100.0,"take_profit":71000.0,"size_pct":0.018,"leverage":2,
"reasoning":"Two of three models agree on LONG with strong confidence. Mini dissents to HOLD but its lower conviction is outweighed. Entry/SL/TP are confidence-weighted averages of the two LONG proposals.",
"agent_contributions":{"GPT-4o":"LONG 0.80, momentum confirmed","Claude-Sonnet":"LONG 0.65, trend with caveat","GPT-4o-mini":"HOLD 0.50, sees mixed signals"}}
```
</example>

<example name="no-majority-hold">
Proposals: GPT-4o=LONG conf 0.60, Claude-Sonnet=SHORT conf 0.55, GPT-4o-mini=HOLD conf 0.62.
Output:
```json
{"action":"HOLD","confidence":0.59,"entry_price":68500.0,
"stop_loss":66445.0,"take_profit":70555.0,"size_pct":0.005,"leverage":1,
"reasoning":"All three agents disagree, with no majority. Defaulting to HOLD per synthesis rule. Stop/TP set to the HOLD 3% envelope.",
"agent_contributions":{"GPT-4o":"LONG 0.60","Claude-Sonnet":"SHORT 0.55","GPT-4o-mini":"HOLD 0.62"}}
```
</example>
"""


# ---------------------------------------------------------------------------
# VisionMoA
# ---------------------------------------------------------------------------


class VisionMoA:
    """
    Mixture of Agents Vision — 3 LLMs em paralelo + orchestrator síntese.

    Interface idêntica a Vision: await vison_moa.run(analysis=analysis) → TradingSignal.
    Substitui Vision em NickFury._cycle_for_symbol() quando vision_moa_enabled=True.
    """

    # Nomes dos modelos por slot — usados no audit log e agent_contributions
    _SLOT_NAMES = ["GPT-4o", "Claude-Sonnet", "GPT-4o-mini"]

    def __init__(self) -> None:
        self._log = logger.bind(agent="VisionMoA")

        openai_key = getattr(settings, "openai_api_key", "")
        anthropic_key = getattr(settings, "anthropic_api_key", "")
        anthropic_model = getattr(settings, "anthropic_model", "claude-sonnet-4-6")
        temperature = getattr(settings, "openai_temperature", 0.2)
        max_tokens = getattr(settings, "openai_max_tokens", 2048)

        # ── Proposal-A: GPT-4o ────────────────────────────────────────────
        self._llm_a = LLMClient(
            openai_key=openai_key,
            openai_model="gpt-4o",
            anthropic_key="",      # GPT-4o only — sem fallback Claude aqui
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # ── Proposal-B: Claude Sonnet (force Anthropic; zero OpenAI key) ──
        self._llm_b = LLMClient(
            openai_key="",         # desabilita OpenAI → força rota Claude
            anthropic_key=anthropic_key,
            anthropic_model=anthropic_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # ── Proposal-C: GPT-4o-mini ───────────────────────────────────────
        self._llm_c = LLMClient(
            openai_key=openai_key,
            openai_model="gpt-4o-mini",
            anthropic_key="",
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # ── Orchestrator: GPT-4o → Claude fallback ────────────────────────
        self._llm_orch = LLMClient(
            openai_key=openai_key,
            openai_model="gpt-4o",
            anthropic_key=anthropic_key,
            anthropic_model=anthropic_model,
            temperature=0.1,       # mais determinista para síntese
            max_tokens=max_tokens,
        )

        # Vision clássico — usado como fallback quando < 2 proposals OK
        self._vision_fallback = Vision()

        self._log.info(
            "[VisionMoA] Initialized — "
            f"A={self._llm_a.active_provider} | "
            f"B={self._llm_b.active_provider} | "
            f"C={self._llm_c.active_provider} | "
            f"Orch={self._llm_orch.active_provider}"
        )

    # ------------------------------------------------------------------
    # Public API — mesma interface que Vision
    # ------------------------------------------------------------------

    async def run(self, analysis: MarketAnalysis) -> TradingSignal:
        """
        Gera um TradingSignal por consenso de 3 LLMs + orchestrator.

        Never raises — retorna HOLD fallback em qualquer falha crítica.
        """
        symbol = analysis.symbol
        price = analysis.price

        # Pre-flight idêntico ao Vision (anomalia / volatilidade extrema)
        if not analysis.is_safe_to_trade:
            self._log.warning(f"[VisionMoA] {symbol} pre-flight failed → HOLD")
            return Vision._fallback_hold(
                symbol=symbol,
                price=price,
                reason="Pre-flight failed (MoA)",
            )

        try:
            proposals = await self._generate_proposals(analysis)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[VisionMoA] proposals generation crashed: {exc}")
            proposals = []

        # Fallback para Vision clássico se proposals insuficientes
        if len(proposals) < settings.vision_moa_min_proposals:
            self._log.warning(
                f"[VisionMoA] {symbol} only {len(proposals)} proposals — "
                "falling back to single Vision"
            )
            return await self._vision_fallback.run(analysis=analysis)

        # Tentar síntese via orchestrator
        try:
            final = await self._synthesize(
                proposals=proposals,
                analysis=analysis,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"[VisionMoA] orchestrator failed: {exc} — using vote fallback")
            # Review-fix (2026-06-01): _vote_fallback constrói TradingSignal de
            # médias ponderadas que podem violar a geometria (ValidationError) e
            # propagar para fora de run() — quebrando o contrato "never raises" e
            # derrubando o ciclo. Envolver → HOLD seguro.
            try:
                final = self._vote_fallback(proposals=proposals, symbol=symbol, price=price)
            except Exception as _vf_exc:  # noqa: BLE001
                self._log.error(f"[VisionMoA] vote fallback crashou: {_vf_exc} → HOLD")
                return Vision._fallback_hold(
                    symbol=symbol, price=price, reason=f"MoA vote fallback failed: {_vf_exc}",
                )

        # Review-fix (2026-06-01): o MoA pulava os clamps determinísticos do Vision
        # (corte de size em análise degradada + flash scalp hard-block), contornando
        # proteções de segurança. Aplicá-los aqui também, usando a instância Vision.
        try:
            final = self._vision_fallback._apply_degraded_quality_clamp(final, analysis)
            final = self._vision_fallback._apply_flash_scalp_hard_block(final, analysis, price)
        except Exception as _clamp_exc:  # noqa: BLE001
            self._log.warning(f"[VisionMoA] clamps de segurança falharam (mantendo final): {_clamp_exc}")

        self._log.info(
            f"[VisionMoA] {symbol} consensus → {final.summary()} "
            f"(from {len(proposals)} proposals)"
        )
        return final

    async def close(self) -> None:
        """Fecha todos os clientes HTTP."""
        for client in (self._llm_a, self._llm_b, self._llm_c, self._llm_orch):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
        await self._vision_fallback.close()

    # ------------------------------------------------------------------
    # Step 1 — Proposals generation (parallel)
    # ------------------------------------------------------------------

    async def _generate_proposals(
        self, analysis: MarketAnalysis
    ) -> list[TradingSignal]:
        """
        Chama os 3 LLMs em paralelo com o mesmo prompt Vision.
        Proposals que falham são silenciosamente excluídas.
        """
        prompt = analysis.to_prompt()

        results = await asyncio.gather(
            self._single_proposal(self._llm_a, prompt, analysis, slot_name="GPT-4o"),
            self._single_proposal(self._llm_b, prompt, analysis, slot_name="Claude-Sonnet"),
            self._single_proposal(self._llm_c, prompt, analysis, slot_name="GPT-4o-mini"),
            return_exceptions=True,
        )

        proposals: list[TradingSignal] = []
        for i, result in enumerate(results):
            if isinstance(result, TradingSignal):
                proposals.append(result)
            else:
                self._log.debug(
                    f"[VisionMoA] Proposal {self._SLOT_NAMES[i]} skipped: {result}"
                )
        return proposals

    async def _single_proposal(
        self,
        llm: LLMClient,
        prompt: str,
        analysis: MarketAnalysis,
        slot_name: str,
    ) -> TradingSignal:
        """
        Gera um único TradingSignal usando o LLMClient fornecido.
        Lança exceção em caso de falha — asyncio.gather captura via return_exceptions=True.
        """
        raw = await llm.chat(_SYSTEM_PROMPT, prompt)

        # Reutiliza Vision's parsing + validation
        # _VisionParser é um stub mínimo que expõe _build_signal sem LLMClient
        payload = Vision._extract_json(raw)
        _v = _VisionParser()
        sig = _v._build_signal(
            payload=payload,
            symbol=analysis.symbol,
            fallback_price=analysis.price,
        )

        # Tag com modelo que gerou
        new_meta = dict(sig.metadata or {})
        new_meta["moa_slot"] = slot_name
        sig = sig.model_copy(update={"metadata": new_meta})

        self._log.debug(f"[VisionMoA] {slot_name} → {sig.action.value} conf={sig.confidence:.2f}")
        return sig

    # ------------------------------------------------------------------
    # Step 2 — Orchestrator synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self,
        proposals: list[TradingSignal],
        analysis: MarketAnalysis,
    ) -> TradingSignal:
        """
        Passa as proposals ao orchestrator LLM para síntese de consenso.
        Lança exceção se orchestrator falhar — caller usa _vote_fallback.
        """
        proposals_block = self._format_proposals(proposals)
        user_prompt = (
            f"Symbol: {analysis.symbol}\n"
            f"Current price: {analysis.price:.4f}\n\n"
            f"=== INDEPENDENT PROPOSALS ===\n{proposals_block}\n\n"
            "Synthesize the consensus TradingSignal now."
        )

        raw = await self._llm_orch.chat(_ORCHESTRATOR_SYSTEM, user_prompt)

        payload = Vision._extract_json(raw)
        _v = _VisionParser()
        signal = _v._build_signal(
            payload=payload,
            symbol=analysis.symbol,
            fallback_price=analysis.price,
        )

        # Tag MoA metadata
        new_meta = dict(signal.metadata or {})
        new_meta["moa_mode"] = "synthesized"
        new_meta["moa_proposals"] = len(proposals)
        new_meta["moa_orchestrator"] = self._llm_orch.active_provider
        signal = signal.model_copy(update={"metadata": new_meta})
        return signal

    # ------------------------------------------------------------------
    # Fallback — weighted vote quando orchestrator falha
    # ------------------------------------------------------------------

    def _vote_fallback(
        self,
        proposals: list[TradingSignal],
        symbol: str,
        price: float,
    ) -> TradingSignal:
        """
        Síntese mecânica sem LLM:
          1. Voto por ação (maioria simples)
          2. Confidence = média ponderada das proposals
          3. entry/sl/tp = média ponderada das proposals com mesma ação
          4. Se empate ou todos diferentes → HOLD

        Nunca lança exceção.
        """
        if not proposals:
            return Vision._fallback_hold(symbol=symbol, price=price, reason="No proposals (vote fallback)")

        # Contagem de votos por ação
        action_votes: Counter[str] = Counter(p.action.value for p in proposals)
        winning_action_str, top_count = action_votes.most_common(1)[0]

        # Sem maioria (ex: LONG=1, SHORT=1, HOLD=1) → HOLD
        if top_count < 2 and len(proposals) >= 2:
            winning_action_str = "HOLD"

        try:
            winning_action = TradeAction(winning_action_str)
        except ValueError:
            winning_action = TradeAction.HOLD

        # Filtra proposals com a ação vencedora
        agreers = [p for p in proposals if p.action == winning_action]
        if not agreers:
            agreers = proposals  # fallback: usa todos

        total_conf = sum(p.confidence for p in agreers) or 1.0
        weights = [p.confidence / total_conf for p in agreers]

        avg_conf = sum(w * p.confidence for w, p in zip(weights, agreers))
        avg_entry = sum(w * p.entry_price for w, p in zip(weights, agreers))
        avg_sl = sum(w * p.stop_loss for w, p in zip(weights, agreers))
        avg_tp = sum(w * p.take_profit for w, p in zip(weights, agreers))
        avg_size = sum(w * p.size_pct for w, p in zip(weights, agreers))
        avg_lev = round(sum(w * p.leverage for w, p in zip(weights, agreers)))

        # Para HOLD, garante geometria passante
        if winning_action == TradeAction.HOLD:
            avg_entry = price
            avg_sl = price * 0.97
            avg_tp = price * 1.03

        reasoning = (
            f"MoA vote fallback: {action_votes.most_common()} — "
            f"consensus={winning_action_str} from {len(agreers)}/{len(proposals)} proposals."
        )

        return TradingSignal(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            action=winning_action,
            confidence=avg_conf,
            entry_price=avg_entry,
            stop_loss=avg_sl,
            take_profit=avg_tp,
            size_pct=avg_size if winning_action != TradeAction.HOLD else 0.001,
            leverage=max(1, min(5, avg_lev)),
            reasoning=reasoning,
            agent_contributions={
                p.metadata.get("moa_slot", f"Proposal-{i}"): p.action.value
                for i, p in enumerate(proposals)
                if p.metadata
            },
            metadata={
                "moa_mode": "vote_fallback",
                "moa_proposals": len(proposals),
                "model": "vote",
                "fallback": False,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_proposals(proposals: list[TradingSignal]) -> str:
        """
        Formata as proposals como bloco de texto para o orchestrator.
        """
        lines: list[str] = []
        for i, p in enumerate(proposals, start=1):
            slot = (p.metadata or {}).get("moa_slot", f"Proposal-{i}")
            lines.append(
                f"[{slot}]\n"
                f"  action={p.action.value} confidence={p.confidence:.2f}\n"
                f"  entry={p.entry_price:.4f} sl={p.stop_loss:.4f} tp={p.take_profit:.4f}\n"
                f"  size_pct={p.size_pct:.4f} leverage={p.leverage}\n"
                f"  reasoning={p.reasoning[:200]}"
            )
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# _VisionParser — helper interno para reutilizar Vision._build_signal
# sem instanciar um Vision completo (evita criação desnecessária de LLMClient)
# ---------------------------------------------------------------------------


class _VisionParser(Vision):
    """Subclasse mínima de Vision que pula a criação do LLMClient."""

    def __init__(self) -> None:  # type: ignore[override]
        # Não chama super().__init__() pois não precisamos do LLMClient
        from loguru import logger as _logger
        self._log = _logger.bind(agent="VisionParser")
        self._semantic_store: Any = None
        self._llm = None  # type: ignore[assignment]
        # Forçamos o codename sem passar pelo BaseAgent.__init__ completo
        self.codename = "VisionParser"
