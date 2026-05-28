---
rec_id: "0aba01fc3fdc"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P3"
created_at: "2026-05-28T15:39:38.665267+00:00"
---

# IMP-0aba01fc3fdc — Refatorar src/models/market_data.py (861 linhas)

## Title

Refatorar src/models/market_data.py (861 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`src/models/market_data.py` tem 861 linhas. Monitorar crescimento.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/models/market_data.py: 861 linhas (limite 600)

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
- [ ] PR aberto e vinculado a este rec_id (0aba01fc3fdc) para aprovação do operador.
- [ ] Commit subject contém `[IMP-0aba01fc3fdc]` para reconciliação automática.
