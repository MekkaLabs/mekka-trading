# Story 130 — Iterative Vision Reflection

**Versão:** 0.11.0-dev  
**Data:** 2026-05-15  
**Dependência:** Story 031 (VisionCritic), Story 128 (SemanticEpisodicStore)

---

## Context

O VisionCritic (Story 031) opera em modo one-shot: Vision gera um `TradingSignal`,
o crítico avalia e `apply_critique()` ajusta mecanicamente os parâmetros (size, leverage,
SL, TP). A Vision **nunca vê** o feedback do crítico — ela não tem chance de re-pensar
seu raciocínio.

Após análise do framework **AutoGen** da Microsoft (padrão Reflection), identificamos
que o loop Coder↔Reviewer iterativo é exatamente o que Vision↔VisionCritic precisam.
No AutoGen, o Coder regenera com base no feedback do Reviewer em até N rodadas — em
vez de o Reviewer apenas editar o output mecanicamente.

---

## Goal

Transformar o one-shot Vision→Critic em um loop iterativo (até
`settings.vision_reflection_max_rounds`, default 3). A cada rodada em que o Critic
retorna AMEND ou REJECT, Vision recebe o feedback no contexto e regenera o sinal
completo. O loop converge quando o Critic retorna ENDORSE ou ao atingir max_rounds.

**Backward compatibility:** quando `vision_reflection_max_rounds=1`, o comportamento é
idêntico ao Story 031 one-shot. Quando `vision_critic_enabled=False`, o loop é bypassado.

---

## Architecture

```
Vision._run(analysis)               → TradingSignal S0
  │
  └─► VisionCritic.run(analysis, S0)   → critique R1
        │
        ├── ENDORSE → return S0          ← converge round 1 ✓
        │
        ├── AMEND/REJECT + round < max →
        │     critique_context = format(critique R1)
        │     Vision.revise(analysis, critique_context, round=1) → S1
        │       │
        │       └─► VisionCritic.run(analysis, S1) → critique R2
        │             │
        │             ├── ENDORSE → return S1       ← converge round 2 ✓
        │             └── AMEND/REJECT + round=max →
        │                   apply_critique(S1, R2) → S2 (mecânico)
        │                   return S2               ← max_rounds reached
        └── AMEND/REJECT + round=max →
              apply_critique(S0, R1) → S1 (mecânico)
              return S1
```

### Super-steps e custo LLM

| Round | Chamadas LLM | Condição |
|-------|-------------|----------|
| 1     | 1 Vision + 1 Critic = 2 | Sempre |
| 2     | +1 Vision.revise + 1 Critic = +2 | Só se R1 = AMEND/REJECT |
| 3     | +1 Vision.revise + 1 Critic (mecânico) = +1 | Só se R2 = AMEND/REJECT |

Custo worst-case com max_rounds=3: **5 chamadas LLM** (vs. 2 no one-shot).
Na prática, a maioria converge em round 1 (ENDORSE) — custo esperado ≈ 2 chamadas.

---

## New Methods

### `Vision.revise(analysis, critique_context, round_num) → TradingSignal`

Idêntico ao `_run()` mas com `critique_context` appendado ao prompt de análise.
A Vision vê exatamente o que o Critic disse e pode mudar action, confidence,
sizing, raciocínio — ou ignorar o feedback se discordar.

Fail-silent: qualquer erro retorna HOLD (mesmo contrato de `_run()`).

### `NickFury._vision_reflection_loop(analysis, initial_signal, symbol) → (TradingSignal, int)`

Orquestra o loop Vision↔VisionCritic. Retorna `(final_signal, rounds_used)`.

- Faz audit de cada round via `MekkaRepository.log_event` com
  `event="REFLECTION_R{N}_{ACTION}"`.
- `rounds_used` alimenta o log de NickFury para rastreabilidade.
- Falha silenciosamente em qualquer exceção — retorna `(initial_signal, round_num)`.

---

## New Setting

```python
vision_reflection_max_rounds: int = Field(
    default=3,
    ge=1,
    le=5,
    description="Max rounds Vision↔VisionCritic. Set to 1 = Story 031 one-shot."
)
```

---

## Files Changed

### New

| Arquivo | Descrição |
|---------|-----------|
| `tests/test_story_130_vision_reflection.py` | 14 testes cobrindo Vision.revise(), reflection loop e integração |
| `docs/stories/story-130-vision-reflection.md` | Este documento |

### Modified

| Arquivo | Mudança |
|---------|---------|
| `src/config/settings.py` | Novo campo `vision_reflection_max_rounds: int = 3` |
| `src/agents/vision.py` | Novo método `revise(analysis, critique_context, round_num)` |
| `src/agents/nick_fury.py` | Novo método `_vision_reflection_loop()`; `_cycle_for_symbol()` usa o loop em vez do one-shot |
| `docs/stories/INDEX.md` | Story 130 adicionada ao Milestone 20 |

---

## Fail-Silent Design

| Cenário | Comportamento |
|---------|---------------|
| `vision_critic_enabled=False` | Loop bypassado, signal de Vision passa direto para Batman |
| VisionCritic levanta exceção no round N | `break` com `_log.warning`, sinal do round anterior é preservado |
| `Vision.revise()` retorna HOLD por LLM error | Loop continua com o HOLD como signal do round N |
| `vision_reflection_max_rounds=1` | Comportamento identical ao Story 031 one-shot |
| Todos os rounds atingidos sem ENDORSE | `apply_critique()` mecânico no último round |

---

## Audit Trail

Cada round é registrado no banco com payload completo:

```
event: REFLECTION_R1_ENDORSE   → convergiu no round 1
event: REFLECTION_R1_AMEND     → Critic pediu revisão
event: REFLECTION_R2_ENDORSE   → convergiu no round 2 após revisão
payload: { ...critique, reflection_round: N, max_rounds: 3 }
```

---

## Tests

```
tests/test_story_130_vision_reflection.py
├── TestReflectionSettings (2 testes)
│   ├── test_vision_reflection_max_rounds_default
│   └── test_vision_reflection_max_rounds_ge_1
├── TestVisionRevise (5 testes)
│   ├── test_revise_returns_trading_signal
│   ├── test_revise_appends_critique_to_prompt
│   ├── test_revise_sets_reflection_round_metadata
│   ├── test_revise_fallback_on_llm_error
│   └── test_revise_preflight_hold_when_not_safe
├── TestVisionReflectionLoop (6 testes)
│   ├── test_converges_round_1_on_endorse
│   ├── test_calls_revise_on_amend
│   ├── test_apply_critique_on_last_round
│   ├── test_fail_silent_on_critic_exception
│   ├── test_reject_leads_to_revision
│   └── test_critique_context_includes_round_info
└── TestCycleForSymbolUsesReflection (1 teste)
    └── test_reflection_loop_called_when_critic_enabled
```

---

## Definition of Done

- [x] `vision_reflection_max_rounds` adicionado ao settings (default 3)
- [x] `Vision.revise()` implementado com critique_context, fail-silent
- [x] `NickFury._vision_reflection_loop()` implementado com loop + audit
- [x] `_cycle_for_symbol()` usa o reflection loop em vez do one-shot
- [x] Backward compat: `max_rounds=1` → comportamento Story 031
- [x] Fail-silent em todos os pontos críticos
- [x] 14 testes criados (sintaxe verificada)
- [x] Story doc criado
- [x] INDEX.md atualizado

---

## What's Next (Milestone 20 — Decision Quality)

- **Story 131**: Mixture of Agents Vision — 3 LLMs em paralelo votando no TradingSignal
- **Story 132**: OpenTelemetry Tracing — span por agente, trace ID por ciclo
