---
rec_id: "50c82edd99e2"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-30T16:16:25.120562+00:00"
---

# IMP-50c82edd99e2 — Backend: 14 arquivos com lazy imports excessivos

## Title

Backend: 14 arquivos com lazy imports excessivos

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** LOW
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

Lazy imports dentro de funções (`from src... import` indentado) geralmente indicam ciclo de import não-resolvido. Top offenders: `src/services/telegram_inbound.py` (26), `src/services/mekka_kernel.py` (15), `src/services/improvement_memory_bridge.py` (8), `src/services/auto_learning_scheduler.py` (6), `src/services/cycle_state_resetter.py` (6). Vale revisar dependências.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

14 arquivos com >=4 lazy imports

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`_(definir KPI mensurável antes de fechar)_`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (50c82edd99e2) para aprovação do operador.
- [ ] Commit subject contém `[IMP-50c82edd99e2]` para reconciliação automática.
