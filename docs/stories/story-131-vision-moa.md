# Story 131 — Mixture of Agents Vision (MoA)

**Milestone:** 20 — Decision Quality  
**Data:** 2026-05-15  
**Status:** ✅ Entregue  
**Padrão:** AutoGen Mixture of Agents (MoA)

---

## Objetivo

Implementar o padrão Mixture of Agents (MoA) na Vision: 3 LLMs diferentes geram
`TradingSignal` independentemente em paralelo, e um orchestrator LLM sintetiza o
consenso em um sinal final. Reduz viés de modelo único e melhora a qualidade da
decisão estratégica.

---

## Arquitetura MoA

```
MarketAnalysis
      │
      ├─ GPT-4o (Proposal-A)      ─┐
      ├─ Claude Sonnet (Proposal-B) ├─→ [Signal-A, Signal-B, Signal-C]
      └─ GPT-4o-mini (Proposal-C)  ─┘
                                         │
                                   Orchestrator (GPT-4o > Claude)
                                         │
                                   Consensus TradingSignal
```

### Fail-silent rules

| Situação | Comportamento |
|----------|---------------|
| < 2 proposals OK | Fallback para Vision._run() clássico |
| Orchestrator falha | _vote_fallback() mecânico (maioria + weighted avg) |
| Proposal individual falha | Silenciosamente excluída do gather |
| analysis.is_safe_to_trade=False | HOLD imediato, sem LLM calls |

---

## Implementação

### Arquivos criados/modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/agents/vision_moa.py` | **NOVO** | VisionMoA — 3 proposals + orchestrator síntese |
| `src/config/settings.py` | MODIFICADO | `vision_moa_enabled`, `vision_moa_min_proposals` |
| `src/agents/nick_fury.py` | MODIFICADO | Toggle + shutdown do VisionMoA |
| `tests/test_story_131_vision_moa.py` | **NOVO** | 14 testes |

### `src/agents/vision_moa.py`

**Classe `VisionMoA`:**
- `__init__()` — cria 4 `LLMClient` (A, B, C, orchestrator); fallback Vision clássico
- `run(analysis)` — interface idêntica a Vision; fail-silent total
- `_generate_proposals(analysis)` — asyncio.gather(A, B, C, return_exceptions=True)
- `_single_proposal(llm, prompt, analysis, slot_name)` — LLM call + parse via Vision
- `_synthesize(proposals, analysis)` — orchestrator call com proposals formatadas
- `_vote_fallback(proposals, symbol, price)` — síntese mecânica sem LLM

**Classe `_VisionParser`:**  
Stub mínimo de Vision (sem LLMClient) para reutilizar `_build_signal()` e 
`_extract_json()` estáticos.

### Lógica do vote_fallback

```
votes = Counter(p.action for p in proposals)
winner, count = votes.most_common(1)[0]

if count < 2 and len(proposals) >= 2:  # sem maioria
    winner = HOLD

agreers = [p for p in proposals if p.action == winner]
total_conf = sum(p.confidence for p in agreers)
weights = [p.confidence / total_conf for p in agreers]

avg_confidence = Σ(weight × confidence)
avg_entry = Σ(weight × entry_price)
avg_sl = Σ(weight × stop_loss)
avg_tp = Σ(weight × take_profit)
```

### Orchestrator System Prompt

O orchestrator recebe as 3 proposals formatadas (action, confidence, entry, sl, tp,
reasoning) e aplica 5 regras de síntese:
1. ACTION por maioria
2. CONFIDENCE por média ponderada
3. ENTRY/SL/TP por média ponderada dos que concordam
4. SIZE_PCT/LEVERAGE por média ponderada
5. REASONING explicando consenso + dissent

### Settings

```python
VISION_MOA_ENABLED=false          # ativa MoA (padrão off)
VISION_MOA_MIN_PROPOSALS=2        # mínimo de proposals para síntese (1-3)
```

### Toggle em NickFury

```python
# NickFury.__init__():
if settings.vision_moa_enabled:
    self._vision_moa = VisionMoA()

# NickFury._cycle_for_symbol() passo 2:
if self._vision_moa is not None:
    signal = await self._vision_moa.run(analysis=analysis)
else:
    signal = await self._vision.run(analysis=analysis)  # path pré-131
```

---

## Custo de LLM por ciclo por símbolo

| Modo | LLM calls |
|------|-----------|
| Clássico (pré-131) | 1 (Vision) |
| MoA sem reflection | 4 (A + B + C + orchestrator) |
| MoA + reflection (max_rounds=3) | 4 + até 6 (reflection rounds) |
| MoA consensus imediato (ENDORSE r1) | 4 + 2 |

---

## Testes (14)

| Teste | Cobertura |
|-------|-----------|
| T01 — imports sem error | Importação básica |
| T02 — instancia sem keys | LLMClient "none" |
| T03 — vote_fallback majority LONG | 2L+1S → LONG |
| T04 — vote_fallback no majority → HOLD | 1L+1S+1H → HOLD |
| T05 — vote_fallback empty list | Lista vazia → HOLD |
| T06 — vote_fallback 2 SHORT | Weighted avg confidence |
| T07 — format_proposals | Slot names + action presentes |
| T08 — pre-flight fail → HOLD | is_safe_to_trade=False |
| T09 — run() synthesizes when OK | Mock proposals + orchestrator |
| T10 — run() fallback quando < min | 1 proposal → Vision clássico |
| T11 — run() vote_fallback orch fails | Orchestrator RuntimeError |
| T12 — settings fields existem | vision_moa_enabled + min_proposals |
| T13 — NickFury._vision_moa None (default) | Off por padrão |
| T14 — NickFury cria VisionMoA quando enabled | On com patch |

---

## Próximas stories

- **Story 132 — OpenTelemetry Tracing:** span por agente por ciclo, trace_id ligando pipeline
- **Story 133 — Adaptive Layer 1 Routing (Swarm):** ProfessorX decide quais agentes Layer 1 ativar por regime de mercado
