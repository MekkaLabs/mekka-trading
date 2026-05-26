---
rec_id: "4f32cc28e7bf"
status: resolved
domain: "trading-ops"
area: "risk"
priority: "P1"
created_at: "2026-05-26T01:13:08.528901+00:00"
resolved_at: "2026-05-26T01:55:00+00:00"
resolution: |
  Causa raiz identificada e corrigida na sessão de 2026-05-25:
  - O kill switch foi engatado pelo _vision_fallback_breaker quando
    o Vision retornou 5 HOLD-fallbacks consecutivos em ~1min, todos
    causados por "No LLM provider configured" (config error, não
    degradação real).
  - Causa raiz: anthropic package ausente no venv + OPENAI_API_KEY
    vazio no .env. Corrigido em commits b4a3404 (deps + diagnóstico)
    e 8744a42 (load_dotenv defensivo no run.py).
  - Falso positivo do breaker eliminado em commit cfb005e
    (categorização fallback_category: só llm_degraded/parse_error
    contam, safety_skip/config_error não).
  - Kill switch foi liberado e desde então não voltou a engatar.
---

# IMP-4f32cc28e7bf — Kill switch ATIVO — investigar causa raiz

## Title

Kill switch ATIVO — investigar causa raiz

## Context / Impact

- **Domain:** trading-ops
- **Area:** risk
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

O kill switch está engatado agora. Trading está halted. Investigar o gatilho (drawdown/erro) antes de liberar.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 75.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

is_kill_switch_active()=True; 4 eventos de kill no período.

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (4f32cc28e7bf) para aprovação do operador.
