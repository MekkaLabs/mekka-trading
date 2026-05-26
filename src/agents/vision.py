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
from src.models.vision_output import TradingSignalOutput  # Story 250

from src.agents.base import BaseAgent
from src.config.settings import settings
from src.models.market_data import MarketAnalysis
from src.models.signal import TradeAction, TradingSignal
from src.services.prompt_registry import prompt_version  # Story 143


# ---------------------------------------------------------------------------
# Prompt skeletons
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Você é o Vision, a IA estratégica de tomada de decisão do
Mekka Trading System — uma plataforma autônoma multiagente operando perpetuais
na Hyperliquid.

Você recebe análise consolidada de sete agentes especializados:
  • Superman        — análise técnica multi-timeframe
  • Doctor Strange  — sentimento macro & Fear/Greed
  • Black Panther   — fluxo onchain de whales, funding, OI
  • Thor            — regime de volatilidade
  • Aquaman         — liquidez do book de ordens
  • Spider-Man      — detecção de anomalias
  • Flash           — momentum intra-candle (sinais ultra-rápidos)

IMPORTANTE — IDIOMA:
O campo "reasoning" e quaisquer textos descritivos no JSON devem ser escritos
EM PORTUGUÊS DO BRASIL, em linguagem clara que um operador não-técnico consiga
entender. Use termos como "ALTA / BAIXA / NEUTRO" no lugar de "BULLISH / BEARISH",
"compra / venda" quando fizer sentido, e explique brevemente os porquês.

Sua saída DEVE ser um único objeto JSON conforme o schema TradingSignal —
sem markdown, sem comentários, sem code fences. Apenas JSON.

Princípios de decisão
---------------------
1. Risco primeiro: na dúvida, HOLD.
2. Confiança ≥ 0.65 é obrigatória para um trade acionável.
3. Risk/Reward ≥ 1.5 obrigatório para um trade acionável.
4. Respeite o multiplicador de volatilidade do Thor ao dimensionar.
5. Respeite o score de liquidez do Aquaman: < 0.3 → reduzir size ou HOLD.
6. Se Spider-Man sinaliza should_pause, retorne HOLD.
7. Restrição geométrica:
     LONG:  stop_loss < entry < take_profit
     SHORT: take_profit < entry < stop_loss
8. [Story 244] Guidance de momentum do Flash:
     • Flash STRONG UP   + LONG  → timing confirmado, sem ajuste forçado.
     • Flash STRONG UP   + SHORT → reduzir size_pct em 20% (divergência).
     • Flash STRONG DOWN + SHORT → timing confirmado, sem ajuste forçado.
     • Flash STRONG DOWN + LONG  → reduzir size_pct em 20% (divergência).
     • Flash SIDEWAYS            → reduzir confidence em 0.05 para qualquer direcional.
     • Flash sinal fraco         → tratar apenas como sinal de suporte leve.

Schema (todos os campos obrigatórios, JSON válido)
--------------------------------------------------
{
  "action": "LONG" | "SHORT" | "HOLD",
  "confidence": 0.0–1.0,
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "size_pct": 0.005–0.05,
  "leverage": integer 1–5,
  "reasoning": "2-4 frases EM PORTUGUÊS, linguagem clara",
  "agent_contributions": {"NomeAgente": "o que ele contribuiu (em português)"}
}

Para HOLD, defina entry_price = preço atual, stop_loss = entry × 0.97,
take_profit = entry × 1.03 (a geometria ainda precisa validar).
"""

# Story 133 — Vision Pre-Reasoning
# Prompt separado que solicita ao LLM raciocinar step-by-step antes de emitir
# o sinal. O output desta etapa é injetado no prompt final como contexto.
_PRE_REASONING_SYSTEM = """Você é o módulo de raciocínio pré-análise do Vision.
Sua tarefa NÃO é produzir um sinal de trade. Ao invés disso, produza uma
reflexão analítica estruturada sobre as condições atuais de mercado.

Responda EM PORTUGUÊS DO BRASIL, em 3 parágrafos curtos (sem JSON, sem code fences):

1. **Alinhamento de Sinais**: Os indicadores estão apontando na mesma direção?
   Aponte quaisquer conflitos (ex.: preço em alta vs. sentimento negativo).
2. **Principais Riscos**: Quais os 2–3 maiores riscos se um trade for aberto agora?
   Seja específico (ex.: funding rate elevado, liquidez fraca, anomalia recente).
3. **Viés Preliminar**: Baseado puramente nessa reflexão, qual é a inclinação
   inicial — LONG, SHORT ou HOLD — e nível de confiança (BAIXO/MÉDIO/ALTO)?

Seja conciso. Sem enrolação. Máximo 120 palavras.
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
            timeout_s=45.0,  # LLM call (já tem fallback streak para HOLD)
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
                category="safety_skip",
            )

        prompt = analysis.to_prompt()

        # Story 169 — BoundedOutput: limit analysis prompt to avoid context overflow.
        # Applies truncate_str to the raw analysis prompt (max 12k chars ≈ ~3k tokens).
        # Fails silently — original prompt used if BoundedOutput unavailable.
        try:
            from src.services.bounded_output import BoundedOutput as _BO  # noqa: WPS433
            _prompt_len_before = len(prompt)
            prompt = _BO.truncate_str(prompt, max_chars=12_000)
            if len(prompt) < _prompt_len_before:
                self._log.debug(
                    f"[Vision:169] analysis prompt bounded "
                    f"{_prompt_len_before}→{len(prompt)} chars"
                )
        except Exception as _bo169_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:169] BoundedOutput skipped: {_bo169_exc}")

        # Story 063 / Story 128 — Episodic Memory: enrich prompt with historical
        # pattern context. Story 128 uses semantic search when _semantic_store is
        # available (LangGraph mode); falls back to SQL equality search otherwise.
        # Fails silently — Vision always gets a prompt either way.
        try:
            memory_block = await self._build_memory_block(
                analysis, semantic_store=self._semantic_store
            )
            if memory_block:
                # Story 169 — Bound the memory block before injection (max 3k chars)
                try:
                    from src.services.bounded_output import BoundedOutput as _BO2  # noqa: WPS433
                    memory_block = _BO2.bound_prompt_section(
                        "Episodic Memory", memory_block, max_chars=3_000
                    )
                except Exception:  # noqa: BLE001
                    pass
                prompt = prompt + "\n\n" + memory_block
        except Exception as _mem_exc:  # noqa: BLE001
            self._log.debug(f"[Vision] Episodic memory fetch skipped: {_mem_exc}")

        # Story #72 — Vault enrichment (Second-brain / Neural-graph).
        # Read-only: appends curated notes from the Obsidian vault when the
        # operator enabled VAULT_ENRICHMENT_ENABLED. Fail-silent + bounded
        # latency (1.5s) + cached. Never changes Vision's decision path —
        # worst case the prompt stays unchanged.
        try:
            from src.services.vault_context import vault_context_for  # noqa: WPS433
            vault_block = await vault_context_for(
                symbol=analysis.symbol,
                topic=(analysis.chart.trend.value if analysis.chart else None),
            )
            if vault_block:
                prompt = prompt + "\n\n" + vault_block
        except Exception as _vault_exc:  # noqa: BLE001
            self._log.debug(f"[Vision] Vault enrichment skipped: {_vault_exc}")

        # Story 164 — MicroagentRegistry regime-aware prompt injection.
        # Detects the current market regime from the analysis chart data and
        # appends the matching Markdown microagent prompt to Vision's context.
        # Fails silently — Vision always proceeds without the context if unavailable.
        try:
            from src.services.microagent_registry import get_microagent_registry  # noqa: WPS433
            _chart164 = analysis.chart if analysis else None
            _regime164 = "UNKNOWN"
            if _chart164 and hasattr(_chart164, "trend"):
                _t164 = _chart164.trend.value if hasattr(_chart164.trend, "value") else str(_chart164.trend)
                _r164 = float(_chart164.rsi_14) if _chart164.rsi_14 is not None else 50.0
                _atr164 = float(_chart164.atr_pct) if (hasattr(_chart164, "atr_pct") and _chart164.atr_pct is not None) else 0.0
                if _atr164 > 0.05:
                    _regime164 = "VOLATILE"
                elif _t164 in ("BULLISH", "STRONG_BULL") and _r164 > 55:
                    _regime164 = "BULL"
                elif _t164 in ("BEARISH", "STRONG_BEAR") and _r164 < 45:
                    _regime164 = "BEAR"
                else:
                    _regime164 = "SIDEWAYS"
            _regime_prompt = get_microagent_registry().get_regime_prompt(_regime164)
            if _regime_prompt:
                prompt = (
                    prompt
                    + f"\n\n=== Market Context ({_regime164} regime) ===\n"
                    + _regime_prompt
                )
                self._log.debug(
                    f"[Vision:164] Regime prompt injected ({_regime164}, {len(_regime_prompt)} chars)"
                )
        except Exception as _mic164_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:164] Microagent injection skipped: {_mic164_exc}")

        # Story 164 — MekkaRepoMap: inject compact agent symbol index.
        # Lets Vision know which agents exist when formulating reasoning.
        # Bounded at 800 chars to avoid context bloat. Fails silently.
        try:
            from src.services.repo_map import get_repo_map  # noqa: WPS433
            _rmap_section = get_repo_map().to_prompt_section(max_chars=800, dirs=["src/agents"])
            if _rmap_section:
                prompt = prompt + "\n\n" + _rmap_section
                self._log.debug(f"[Vision:164] RepoMap injected ({len(_rmap_section)} chars)")
        except Exception as _rmap164_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:164] RepoMap injection skipped: {_rmap164_exc}")

        # Story 190 — SignalDemonstrationStore: inject few-shot demonstrations.
        # SWE-agent Demonstrations pattern: trajectories converted to demos and
        # injected as few-shot examples in the system prompt to guide behavior.
        # Here: past high-confidence WIN signals in similar (regime, symbol) are
        # shown as format+reasoning templates — "this is what a good signal looks like".
        # Lazy-loads data/signal_demonstrations.json on first call.
        # Fails silently — no demo block if empty store or error.
        try:
            from src.services.signal_demonstration_store import get_demonstration_store  # noqa: WPS433
            _sym190 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _meta190 = getattr(analysis, "signal_metadata", None) or {}
            _regime190 = _meta190.get("market_regime", "UNKNOWN")
            _demo_block = get_demonstration_store().get_prompt_block(_sym190, regime=_regime190)
            if _demo_block:
                prompt = prompt + "\n\n" + _demo_block
                self._log.debug(f"[Vision:190] DemonstrationStore block injected for {_sym190}")
        except Exception as _demo190_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:190] SignalDemonstrationStore skipped: {_demo190_exc}")

        # Story 191 — ObservationFeedbackLoop: inject lint corrections from previous cycle.
        # SWE-agent ACI guardrails: linter output is fed back as "observation" context
        # so the agent corrects geometry errors in the next turn. Here: if the last cycle's
        # signal was auto-corrected by AutoSignalLinter (Story 179), those corrections are
        # shown to Vision so it avoids the same geometry mistakes.
        # Fails silently.
        try:
            from src.services.observation_feedback_loop import get_observation_feedback_loop  # noqa: WPS433
            _sym191 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _obs_block = get_observation_feedback_loop().get_feedback_block(_sym191, consume=True)
            if _obs_block:
                prompt = prompt + "\n\n" + _obs_block
                self._log.debug(f"[Vision:191] ObservationFeedbackLoop block injected for {_sym191}")
        except Exception as _obs191_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:191] ObservationFeedbackLoop skipped: {_obs191_exc}")

        # Story 183 — RoleWorkingMemory: inject recent trade history for this symbol.
        # MetaGPT RoleContext.rc.memory pattern: each Role maintains a working memory
        # of observed messages. Here: last N cycle results (action, confidence, regime,
        # outcome_pnl) injected as "recent trade history" so Vision can avoid repeating
        # recent mistakes and recognize recurring patterns.
        # Fails silently — no history block if memory empty or error.
        try:
            from src.services.role_working_memory import get_role_working_memory  # noqa: WPS433
            _sym183 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _wm_block = get_role_working_memory().get_prompt_block(_sym183, limit=5)
            if _wm_block:
                prompt = prompt + "\n\n" + _wm_block
                self._log.debug(f"[Vision:183] RoleWorkingMemory block injected for {_sym183}")
        except Exception as _wm183_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:183] RoleWorkingMemory skipped: {_wm183_exc}")

        # Story 186 — SignalOutcomeMemory: inject past performance for similar conditions.
        # MetaGPT LongTermMemory pattern: similarity search (regime + action) retrieves
        # top-N historical outcomes as "past performance context" for the LLM.
        # Helps Vision calibrate confidence based on how similar signals performed before.
        # Fails silently — no block if no similar history or error.
        try:
            from src.services.signal_outcome_memory import get_signal_outcome_memory  # noqa: WPS433
            _sym186 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _meta186 = getattr(analysis, "signal_metadata", None) or {}
            _regime186 = _meta186.get("market_regime", "UNKNOWN")
            _past_block = get_signal_outcome_memory().get_prompt_block(
                _sym186, regime=_regime186, action="LONG", top_n=3
            )
            if _past_block:
                prompt = prompt + "\n\n" + _past_block
                self._log.debug(f"[Vision:186] SignalOutcomeMemory block injected for {_sym186}")
        except Exception as _som186_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:186] SignalOutcomeMemory skipped: {_som186_exc}")

        # Story 249 — Decision Memory: inject reflection block from past decisions.
        # TradingAgents (TauricResearch) pattern: decision log with outcome feedback.
        # Recupera últimas N decisões com resultados reais e injeta bloco de reflexão
        # para que a Vision calibre confiança baseada em performance histórica.
        # Falha silenciosamente — sem bloco se sem histórico ou erro.
        try:
            from src.services.decision_memory import get_decision_memory  # noqa: WPS433
            _sym249 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _dm249 = get_decision_memory()
            # Tenta busca async com outcomes (DB); fallback via closed trades síncronos
            import asyncio as _asyncio249  # noqa: WPS433
            try:
                _decisions249 = await _dm249.get_recent_with_outcomes(_sym249, limit=5)
            except Exception:  # noqa: BLE001
                _decisions249 = []
            if not _decisions249:
                # Fallback: usa closed trades para construir reflexão sem await
                try:
                    from src.persistence.repository import MekkaRepository as _MR249  # noqa: WPS433
                    _trades249 = await _MR249.list_recent_closed_trades(limit=5)
                    _trades249_sym = [t for t in _trades249 if getattr(t, "symbol", "") == _sym249]
                    if _trades249_sym:
                        _refl_block249 = _dm249.build_reflection_block_from_closed_trades(
                            _trades249_sym, _sym249
                        )
                    else:
                        _refl_block249 = ""
                except Exception:  # noqa: BLE001
                    _refl_block249 = ""
            else:
                _refl_block249 = _dm249.build_reflection_block(_decisions249, _sym249)
            if _refl_block249:
                prompt = prompt + "\n\n" + _refl_block249
                self._log.debug(f"[Vision:249] DecisionMemory block injected for {_sym249}")
        except Exception as _dm249_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:249] DecisionMemory skipped: {_dm249_exc}")

        # Story 180 — TradeAnnotationWatcher: inject analyst hints (Aider Watch Mode pattern).
        # Reads data/trade_hints.json lazily (only if mtime changed).
        # Analyst drops {"symbol": "BTC", "bias": "LONG", "note": "FOMC amanhã"} in the file
        # and Vision picks it up in the next cycle — zero pipeline disruption.
        # Fails silently — no hint block if file absent or error.
        try:
            from src.services.trade_annotation_watcher import get_trade_annotation_watcher  # noqa: WPS433
            _sym180 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _hint_block = get_trade_annotation_watcher().get_prompt_block(_sym180)
            if _hint_block:
                prompt = prompt + "\n\n" + _hint_block
                self._log.debug(f"[Vision:180] analyst hints injected for {_sym180}")
        except Exception as _watcher180_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:180] TradeAnnotationWatcher skipped: {_watcher180_exc}")

        # Story 182 — AnalysisPromptCache: inject cached macro context block.
        # Reads from in-memory cache (TTL 600s by default) — avoids redundant
        # market data fetches when multiple symbols run in the same cycle.
        # Fails silently — no cache block if cold cache or error.
        try:
            from src.services.analysis_prompt_cache import get_analysis_prompt_cache  # noqa: WPS433
            _cache182 = get_analysis_prompt_cache()
            _cached_macro = _cache182.get("macro_context")
            if _cached_macro:
                prompt = prompt + "\n\n" + _cached_macro
                self._log.debug(f"[Vision:182] cached macro_context injected ({len(_cached_macro)} chars)")
        except Exception as _cache182_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:182] AnalysisPromptCache skipped: {_cache182_exc}")

        # Story 181 — DynamicReasoningBudget: adjust max_tokens based on regime+cap_tier.
        # Reads market_regime and cap_tier from analysis.chart metadata (injected by Story 163).
        # Fails silently — uses model default if budget unavailable.
        _vision_max_tokens: int | None = None
        try:
            from src.services.dynamic_reasoning_budget import get_reasoning_budget  # noqa: WPS433
            _chart181 = analysis.chart if analysis else None
            _regime181 = "UNKNOWN"
            _cap181 = "MID_CAP"
            if _chart181:
                # Try signal metadata first (set by Story 163)
                _meta181 = getattr(analysis, "signal_metadata", None) or {}
                _regime181 = _meta181.get("market_regime", "UNKNOWN")
                _cap181 = _meta181.get("cap_tier", "MID_CAP")
                # Fallback: derive from trend+RSI+ATR
                if _regime181 == "UNKNOWN" and _chart181:
                    _t181 = getattr(_chart181, "trend", None)
                    _t181v = _t181.value if _t181 else "NEUTRAL"
                    _r181 = float(getattr(_chart181, "rsi_14", 50) or 50)
                    _a181 = float(getattr(_chart181, "atr_pct", 0.02) or 0.02)
                    if _a181 > 0.05:
                        _regime181 = "VOLATILE"
                    elif _t181v in ("BULLISH", "STRONG_BULL") and _r181 > 55:
                        _regime181 = "BULL"
                    elif _t181v in ("BEARISH", "STRONG_BEAR") and _r181 < 45:
                        _regime181 = "BEAR"
                    else:
                        _regime181 = "SIDEWAYS"
            _budget181 = get_reasoning_budget()
            _vision_max_tokens = _budget181.get_max_tokens(regime=_regime181, cap_tier=_cap181)
            self._log.debug(
                f"[Vision:181] DynamicReasoningBudget: {_regime181}/{_cap181} "
                f"→ max_tokens={_vision_max_tokens}"
            )
        except Exception as _budget181_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:181] DynamicReasoningBudget skipped: {_budget181_exc}")

        # Story 133 — Vision Pre-Reasoning: reflect before generating signal.
        # Adds ~1 extra LLM call when enabled. Fails silently.
        if settings.vision_pre_reasoning_enabled:
            try:
                reasoning = await self._pre_reason(prompt)
                if reasoning:
                    prompt = (
                        prompt
                        + "\n\n=== Pre-Analysis Reasoning (internal reflection) ===\n"
                        + reasoning
                        + "\n\nNow produce the final TradingSignal JSON based on the above."
                    )
                    self._log.debug(f"[Vision] Pre-reasoning injected ({len(reasoning)} chars)")
            except Exception as _pr_exc:  # noqa: BLE001
                self._log.debug(f"[Vision] Pre-reasoning skipped: {_pr_exc}")

        # Story 170 — ChatHistoryCompressor: compress prompt if approaching context limit.
        # Treats the current prompt as a single-turn "history" and compresses it
        # when it's too long (>80% of model token limit). Deterministic, zero LLM cost.
        # Fails silently — original prompt used if compressor unavailable.
        try:
            from src.services.chat_history_compressor import get_chat_compressor  # noqa: WPS433
            from src.services.context_window_tracker import get_context_window_tracker  # noqa: WPS433
            _symbol170 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _cwt170 = get_context_window_tracker()
            # Use cycle_id from symbol if available, else derive from symbol
            _cid170 = f"vision:{_symbol170}"
            _cwt170.start_cycle(_cid170, _symbol170, settings.openai_model)
            _cwt170.record_stage(_cid170, "pre_llm_prompt", prompt, settings.openai_model, _symbol170)
            if _cwt170.check_limit(_cid170):
                _fake_history = [{"role": "user", "content": prompt}]
                _comp_result = get_chat_compressor(keep_last=1).compress(
                    _fake_history, keep_last=1
                )
                if _comp_result.tokens_saved > 0 and _comp_result.turns:
                    prompt = _comp_result.turns[-1].get("content", prompt)
                    self._log.debug(
                        f"[Vision:170] prompt compressed "
                        f"{_comp_result.tokens_before}→{_comp_result.tokens_after} tokens "
                        f"(saved {_comp_result.tokens_saved})"
                    )
        except Exception as _comp170_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:170] ChatHistoryCompressor skipped: {_comp170_exc}")

        # Story 199 — CycleCondensationEngine: condensa histórico se context window cheia.
        # OpenHands Condenser/CondensationAction: emite CondensationRecord e descarta metade antiga.
        # Integra com CycleConversationMemory (Story 198) e ContextWindowTracker (Story 159).
        # Fails silently.
        try:
            from src.services.cycle_condensation_engine import get_cycle_condensation_engine  # noqa: WPS433
            from src.services.cycle_conversation_memory import get_cycle_conversation_memory  # noqa: WPS433
            _cond199 = get_cycle_condensation_engine()
            _mem199 = get_cycle_conversation_memory()
            _sym199 = getattr(analysis, "symbol", symbol) if analysis else symbol
            _prompt_tokens_199 = len(prompt) // 4
            _max_tokens_199 = _mem199.max_tokens_budget
            _cond199.maybe_condense(
                memory=_mem199,
                symbol=_sym199,
                current_tokens=_prompt_tokens_199,
                max_tokens=_max_tokens_199,
                cycle_id=f"vision:{_sym199}",
            )
        except Exception as _cond199_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:199] CondensationEngine skipped: {_cond199_exc}")

        # Story 178 — ArchitectEditorVision: two-model workflow (Aider architect/editor pattern).
        # If settings.vision_architect_editor_enabled=True:
        #   Call 1 (architect): free-form trade thesis from current model
        #   Call 2 (editor): format thesis into precise TradingSignal JSON
        # Falls back to single-call if architect mode disabled or fails.
        _architect_thesis: str = ""
        if getattr(settings, "vision_architect_editor_enabled", False):
            try:
                _architect_thesis = await self._call_llm(
                    prompt
                    + "\n\nProvide a free-form trade thesis (1-3 paragraphs). "
                    "Focus on direction, key drivers, risks. Do NOT output JSON yet."
                )
                self._log.debug(
                    f"[Vision:178] architect thesis generated "
                    f"({len(_architect_thesis)} chars)"
                )
                # Inject thesis as context for the editor call
                prompt = (
                    prompt
                    + "\n\n=== Architect Thesis (your preliminary analysis) ===\n"
                    + _architect_thesis
                    + "\n\nNow convert the above thesis into the TradingSignal JSON schema exactly."
                )
            except Exception as _arch178_exc:  # noqa: BLE001
                self._log.debug(f"[Vision:178] architect call skipped: {_arch178_exc}")

        # Story 250 — Structured Output path (primary); fallback to raw JSON.
        # Tenta primeiro via chat_structured() (OpenAI schema garantido).
        # Se falhar por qualquer razão, cai no path clássico _call_llm() + _extract_json().
        _structured250: "TradingSignalOutput | None" = None
        try:
            _structured250 = await self._call_llm_structured(prompt)
        except Exception as _s250_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:250] structured path error: {_s250_exc}")

        if _structured250 is not None:
            # Caminho feliz — constrói TradingSignal a partir do modelo Pydantic
            try:
                payload250 = _structured250.model_dump()
                signal = self._build_signal(payload250, symbol=symbol, fallback_price=price)
                signal = self._apply_degraded_quality_clamp(signal, analysis)
                self._log.info(f"[Vision:250] structured ✓ {signal.summary()}")
                return signal
            except Exception as _b250_exc:  # noqa: BLE001
                self._log.debug(
                    f"[Vision:250] build_signal from structured failed: {_b250_exc} — "
                    "falling back to raw JSON path"
                )

        # Fallback — path clássico (raw JSON)
        try:
            raw = await self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            self._log.error(f"[Vision] LLM error: {exc}")
            # Distinguish config errors (missing API key) from real LLM
            # degradation (timeout, rate limit, server 5xx). Only the latter
            # should engage the kill switch after N in a row.
            _msg = str(exc).lower()
            _is_config = (
                "no llm provider configured" in _msg
                or "openai_api_key" in _msg
                or "anthropic_api_key" in _msg
                or "api key" in _msg and ("missing" in _msg or "not set" in _msg)
            )
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"LLM error: {type(exc).__name__}: {exc}",
                category="config_error" if _is_config else "llm_degraded",
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
                category="parse_error",
            )

        signal = self._apply_degraded_quality_clamp(signal, analysis)
        self._log.info(f"[Vision] {signal.summary()}")
        return signal

    def _apply_degraded_quality_clamp(
        self,
        signal: TradingSignal,
        analysis: MarketAnalysis,
    ) -> TradingSignal:
        """
        Fase 2.4 — Postura conservadora quando análise é degradada.

        Se ProfessorX flaggou `analysis.quality["degraded"]=True` (poucas
        fontes Layer 1 responderam), aplicamos clamps determinísticos sobre
        a decisão do LLM:

          - confidence × 0.7 (cap em 0.6) — para reduzir o tamanho de aposta
          - size_pct × 0.5 — corta posição pela metade

        Cumulativamente isso resulta em ~30% do tamanho original em condições
        degradadas. Determinístico — não depende do LLM ler a instrução.

        HOLD não sofre clamp (já é "não opera").
        """
        try:
            quality = getattr(analysis, "quality", None) or {}
            if not quality.get("degraded", False):
                return signal
            if signal.action == TradeAction.HOLD:
                return signal

            _orig_conf = signal.confidence
            _orig_size = signal.size_pct
            _new_conf = min(_orig_conf * 0.7, 0.6)
            _new_size = _orig_size * 0.5

            missing = quality.get("missing_sources") or []
            _new_meta = dict(signal.metadata or {})
            _new_meta["quality_degraded"] = True
            _new_meta["quality_missing"] = missing
            _new_meta["confidence_pre_clamp"] = round(_orig_conf, 4)
            _new_meta["size_pct_pre_clamp"] = round(_orig_size, 6)

            signal = signal.model_copy(update={
                "confidence": round(_new_conf, 4),
                "size_pct": round(_new_size, 6),
                "metadata": _new_meta,
            })
            self._log.warning(
                f"[Vision] análise DEGRADADA — clamp aplicado: "
                f"conf {_orig_conf:.2f}→{_new_conf:.2f}, "
                f"size {_orig_size:.4f}→{_new_size:.4f} "
                f"(faltando: {', '.join(missing) if missing else '?'})"
            )
        except Exception as _clamp_exc:  # noqa: BLE001
            self._log.debug(f"[Vision] degraded clamp skipped: {_clamp_exc}")
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
                category="safety_skip",
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
            _msg = str(exc).lower()
            _is_config = (
                "no llm provider configured" in _msg
                or "openai_api_key" in _msg
                or "anthropic_api_key" in _msg
                or "api key" in _msg and ("missing" in _msg or "not set" in _msg)
            )
            return self._fallback_hold(
                symbol=symbol,
                price=price,
                reason=f"LLM error (revise r{round_num}): {type(exc).__name__}: {exc}",
                category="config_error" if _is_config else "llm_degraded",
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
                category="parse_error",
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
        # Story 194 — VisionRetryMixin: exponential backoff para LLM calls.
        # OpenHands RetryMixin pattern: retenta erros transientes (rate limit,
        # timeout, server error) com backoff 1→2→4→8s.
        # Temperature jitter na última tentativa se resposta vazia (Gemini fix).
        # Fail-silent: se todas as tentativas falharem, deixa a exceção propagar
        # para o handler externo (que retorna HOLD). Não usa tenacity — puro Python.
        try:
            from src.services.vision_retry_mixin import get_vision_retry_mixin  # noqa: WPS433
            _retry194 = get_vision_retry_mixin()

            async def _llm_call_wrapper(**_kwargs: Any) -> str:
                return await self._llm.chat(_SYSTEM_PROMPT, user_prompt)

            # call_with_retry é síncrono — wrapa a coroutine num asyncio.run not needed
            # porque estamos dentro de async context. Usamos diretamente a coroutine:
            import asyncio as _asyncio194  # noqa: WPS433
            _result = None
            _last_exc_194 = None
            # Story 207 — MekkaAgentBackstory: enriquece _SYSTEM_PROMPT com backstory+performance.
            # CrewAI Agent.backstory: persona + goal + performance notes → injetado no LLM.
            # Fails silently: se indisponível, usa _SYSTEM_PROMPT original.
            _effective_system_prompt = _SYSTEM_PROMPT
            try:
                from src.services.mekka_agent_backstory import get_mekka_agent_backstory  # noqa: WPS433
                _backstory207 = get_mekka_agent_backstory()
                _extra_ctx207 = f"User prompt context: {user_prompt[:200]}"
                _enriched207 = _backstory207.build_system_prompt("VISION", _extra_ctx207)
                if len(_enriched207) > 100:  # sanity check
                    _effective_system_prompt = _enriched207 + "\n\n---\n\n" + _SYSTEM_PROMPT
            except Exception as _bs207_exc:  # noqa: BLE001
                self._log.debug(f"[Vision:207] AgentBackstory skipped: {_bs207_exc}")

            for _attempt194 in range(1, _retry194.config.max_retries + 2):
                try:
                    _result = await self._llm.chat(_effective_system_prompt, user_prompt)
                    _retry194._total_successes += 1
                    _retry194._total_calls += 1
                    return _result
                except Exception as _exc194:  # noqa: BLE001
                    _last_exc_194 = _exc194
                    if _attempt194 > _retry194.config.max_retries:
                        _retry194._total_failures += 1
                        raise  # re-raise para o handler externo (→ HOLD)
                    _wait194 = _retry194._wait_time(_attempt194)
                    _retry194._total_retries += 1
                    self._log.debug(
                        f"[Vision:194] LLM retry #{_attempt194} in {_wait194:.1f}s: "
                        f"{type(_exc194).__name__}"
                    )
                    await _asyncio194.sleep(_wait194)
            # Nunca chega aqui
            raise RuntimeError("VisionRetryMixin: exhausted") from _last_exc_194

        except ImportError:
            # VisionRetryMixin não disponível — fallback direto
            return await self._llm.chat(_SYSTEM_PROMPT, user_prompt)
        # (fim do try ImportError — nunca atingido diretamente)

    async def _call_llm_structured(
        self, user_prompt: str
    ) -> "TradingSignalOutput | None":
        """Story 250 — Structured Output path.

        Chama chat_structured() com TradingSignalOutput como response_model.
        OpenAI: client.beta.chat.completions.parse() — schema garantido.
        Anthropic: JSON mode + model_validate() como fallback.

        Reutiliza a mesma lógica de AgentBackstory (207) do _call_llm().
        Retorna None em qualquer erro — caller cai no path raw JSON.
        """
        _effective_system_prompt = _SYSTEM_PROMPT
        try:
            from src.services.mekka_agent_backstory import get_mekka_agent_backstory  # noqa: WPS433
            _backstory207 = get_mekka_agent_backstory()
            _extra_ctx207 = f"User prompt context: {user_prompt[:200]}"
            _enriched207 = _backstory207.build_system_prompt("VISION", _extra_ctx207)
            if len(_enriched207) > 100:
                _effective_system_prompt = _enriched207 + "\n\n---\n\n" + _SYSTEM_PROMPT
        except Exception as _bs_exc:  # noqa: BLE001
            self._log.debug(f"[Vision:250] AgentBackstory skipped: {_bs_exc}")

        try:
            result = await self._llm.chat_structured(
                _effective_system_prompt,
                user_prompt,
                TradingSignalOutput,
                agent_id="VISION",
            )
            return result  # TradingSignalOutput instance or None
        except Exception as exc:  # noqa: BLE001
            self._log.debug(f"[Vision:250] chat_structured error: {exc}")
            return None

    async def _pre_reason(self, analysis_prompt: str) -> str:
        """
        Story 133 — Vision Pre-Reasoning step (CrewAI Reasoning pattern).

        Calls the LLM once with _PRE_REASONING_SYSTEM to produce a free-text
        analytical reflection. The returned text is injected into the final
        TradingSignal prompt as a "Pre-Analysis Reasoning" block, enriching
        the context before the structured JSON call.

        - Uses the same LLM client (_llm) but a different system prompt.
        - Fails silently: caller catches exceptions and skips injection.
        - Returns empty string if response is blank or very short (< 20 chars).
        """
        raw = await self._llm.chat(_PRE_REASONING_SYSTEM, analysis_prompt)
        text = raw.strip()
        if len(text) < 20:
            return ""
        return text

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
                # Story 143 — prompt version fingerprint for audit trail
                "prompt_version": prompt_version(_SYSTEM_PROMPT),
            },
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    # Fallback categories — feed the NickFury safety-net breakers.
    # Only ``llm_degraded`` and ``parse_error`` count as "Vision degraded"
    # (i.e. will engage the kill switch after N in a row). The other two
    # are legitimate safety skips that must NOT auto-engage the kill switch:
    #   - ``safety_skip``: pre-flight (Spider-Man anomaly, EXTREME volatility)
    #   - ``config_error``: missing API key / bad credentials (operator fix)
    FALLBACK_CATEGORIES = ("llm_degraded", "parse_error", "safety_skip", "config_error")

    @staticmethod
    def _fallback_hold(
        symbol: str,
        price: float,
        reason: str,
        category: str = "llm_degraded",
    ) -> TradingSignal:
        """
        Return a defensive HOLD signal when anything goes wrong.

        ``category`` classifies the failure for the safety-net breaker
        (see FALLBACK_CATEGORIES). Default is the conservative
        ``llm_degraded`` so unclassified call-sites still trip the breaker.
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
            metadata={
                "model": settings.openai_model,
                "fallback": True,
                "fallback_reason": reason,
                "fallback_category": category,
            },
        )
