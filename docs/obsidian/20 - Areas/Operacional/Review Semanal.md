---
title: "Review Semanal — Operacional"
type: area_note
tags: [ops, review, weekly, mekka-trading]
created: 2026-05-15
updated: 2026-05-15
---

# Review Semanal — Operacional

## Semana (encerramento) — 2026-05-15

### ✅ Entregas (high-signal)

- Stories **107–112**: calendar, `/balance`, hourly PnL, gate 3q, gates timeline.
- Stories **113–125** (rollup 125): LLM fallback OpenAI→Claude, Superman compatível Py3.14, Telegram pt-BR, Pixel Office 2×2.
- Stories **126–129**: LangGraph checkpointing + interrupt/resume (aprovação durável) + memória semântica + subgrafo Layer 1.
- Stories **130–131**: Decision quality (reflection + mixture-of-agents).
- Stories **132–136**: Memory intelligence + routing adaptativo Layer 1 + **MekkaEventBus**.

### 🧱 Riscos / Dívidas observadas

- EventBus é in-process (não distribuído): não serve para múltiplas instâncias.
- Fail-silent em handlers exige disciplina de testes + counters/alertas.
- `data/dashboard_snapshots/*` tende a sujar o `git status` (avaliar ignore/retention).

### 🎯 Foco da próxima semana (ordem sugerida)

1. **Story 137** — Teste do Milhão (checklist pré-capital real).
2. **Story 138** — Circuit breakers (rate window, stale price, spread).
3. **Story 139** — Degradation matrix + chaos tests.
4. **Story 140** — `DEGRADED_MODE` formal (state machine).
5. **Story 142** — Métricas de custo LLM via EventBus.

### 🔗 Referências

- `docs/stories/INDEX.md` (estado do roadmap)
- `docs/adr/ADR-002-mekka-event-bus.md` (decisão EventBus)

