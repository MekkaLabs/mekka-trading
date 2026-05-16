# Story 133 — Vision Pre-Reasoning

## Context

O Vision atualmente recebe o `MarketAnalysis` prompt + bloco de memória episódica e
gera o `TradingSignal` JSON em uma única chamada LLM. Não há etapa de reflexão
estruturada — o modelo decide "on the fly" sem considerar explicitamente conflitos
entre indicadores ou riscos antes de comitar uma direção.

Inspirado pelo padrão **CrewAI Reasoning** (etapa de reflexão antes de agir),
a Story 133 introduz um passo de pré-raciocínio opcional: Vision primeiro pensa
em voz alta sobre alignment, riscos e viés preliminar — depois gera o sinal com
esse contexto injetado. A segunda chamada produz sinais mais calibrados porque
o modelo não está "descobrindo" os riscos enquanto formata o JSON.

## Goal

Antes de emitir o `TradingSignal`, Vision faz uma chamada LLM adicional com
um sistema prompt separado que pede raciocínio livre (sem JSON). O output é
injetado no prompt final como `=== Pre-Analysis Reasoning ===`, enriquecendo
o contexto da call de decisão.

## Scope Delivered

### `src/agents/vision.py`

- **`_PRE_REASONING_SYSTEM`** — novo prompt constante.  
  Pede ao modelo 3 parágrafos curtos (max 120 words):
  1. Signal Alignment — indicadores alinhados ou conflitantes?
  2. Key Risks — top 2–3 riscos se trade for executado
  3. Preliminary Bias — LONG / SHORT / HOLD + confiança LOW/MED/HIGH

- **`_pre_reason(analysis_prompt) → str`** — novo método assíncrono.  
  Usa `self._llm.chat(_PRE_REASONING_SYSTEM, prompt)`.  
  Retorna `""` se resposta < 20 chars (proteção contra respostas em branco).

- **`_run()`** — passo adicional após `_build_memory_block()`:
  ```
  if settings.vision_pre_reasoning_enabled:
      reasoning = await self._pre_reason(prompt)
      if reasoning:
          prompt += "\n\n=== Pre-Analysis Reasoning ===\n" + reasoning
                  + "\n\nNow produce the final TradingSignal JSON ..."
  ```
  Fail-silent: exceção em `_pre_reason` não interrompe o fluxo.

### `src/config/settings.py`

| Campo | Default | Descrição |
|-------|---------|-----------|
| `vision_pre_reasoning_enabled` | `False` | Liga/desliga o passo extra (default off) |

Ativação: `VISION_PRE_REASONING_ENABLED=true`

## Fluxo Atualizado

```
_run(analysis)
  │
  ├─ pre-flight (is_safe_to_trade)
  ├─ build memory block (semantic / SQL)
  │
  ├─ [NEW] if vision_pre_reasoning_enabled:
  │    └─ _pre_reason(prompt) → reasoning text (fail-silent)
  │         └─ inject into prompt as "Pre-Analysis Reasoning"
  │
  └─ _call_llm(enriched_prompt) → TradingSignal JSON
```

## Hard Rules Mantidas

- Default `False` — zero impacto para quem não ativar
- Fail-silent: qualquer erro em `_pre_reason` → prompt sem injeção, sinal normal
- Nenhuma dependência nova; usa o mesmo `_llm` client
- Pre-flight `is_safe_to_trade=False` → HOLD imediato sem nenhuma call LLM

## Acceptance

- `pytest tests/test_story_133_vision_pre_reasoning.py -v` → verde
- Com `vision_pre_reasoning_enabled=True`, `_run()` faz 2 calls LLM
- Com `vision_pre_reasoning_enabled=False`, `_run()` faz 1 call LLM
- Falha em `_pre_reason` → sinal gerado normalmente (fail-silent)
- `_PRE_REASONING_SYSTEM` contém as 3 seções (Signal Alignment, Key Risks, Preliminary Bias)

## What's Next

- Story 134 — doc apenas (código entregue em Story 132)
- Story 135 — Adaptive Layer 1 Routing (Hierarchical Process)
- Story 136 — MekkaEventBus

## Files Changed

- `src/agents/vision.py` — `_PRE_REASONING_SYSTEM`, `_pre_reason()`, `_run()` updated
- `src/config/settings.py` — `vision_pre_reasoning_enabled` field
- `tests/test_story_133_vision_pre_reasoning.py` — 13 testes
- `docs/stories/story-133-vision-pre-reasoning.md` — este documento
