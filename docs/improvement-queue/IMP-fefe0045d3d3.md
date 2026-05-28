---
rec_id: "fefe0045d3d3"
status: stale
domain: "dev-squad"
area: "frontend"
priority: "P1"
created_at: "2026-05-28T15:39:37.525353+00:00"
---

# IMP-fefe0045d3d3 — Frontend: refatorar app.js (8538 linhas)

## Title

Frontend: refatorar app.js (8538 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** frontend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/dashboard/static/app.js` tem **8538 linhas** de JS — dificulta manutenção e aumenta tempo de carregamento. Quebrar em módulos.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Checar light+dark, mobile e leitores de tela.
- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/dashboard/static/app.js: 8538 linhas

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
- [ ] PR aberto e vinculado a este rec_id (fefe0045d3d3) para aprovação do operador.
- [ ] Commit subject contém `[IMP-fefe0045d3d3]` para reconciliação automática.
