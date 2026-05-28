---
rec_id: "ec93e1bea26e"
status: stale
domain: "dev-squad"
area: "frontend"
priority: "P3"
created_at: "2026-05-28T15:39:38.978115+00:00"
---

# IMP-ec93e1bea26e — Frontend: refatorar style.css (4827 linhas)

## Title

Frontend: refatorar style.css (4827 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** frontend
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`src/dashboard/static/style.css` tem 4827 linhas de CSS. Considere modularizar por componente ou usar BEM/utility classes.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Checar light+dark, mobile e leitores de tela.
- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/dashboard/static/style.css: 4827 linhas

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
- [ ] PR aberto e vinculado a este rec_id (ec93e1bea26e) para aprovação do operador.
- [ ] Commit subject contém `[IMP-ec93e1bea26e]` para reconciliação automática.
