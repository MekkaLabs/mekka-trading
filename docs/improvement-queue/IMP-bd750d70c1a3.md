---
rec_id: "bd750d70c1a3"
status: stale
domain: "dev-squad"
area: "dashboard"
priority: "P1"
created_at: "2026-05-28T15:39:37.511511+00:00"
---

# IMP-bd750d70c1a3 — Dashboard: server.py com 7148 linhas

## Title

Dashboard: server.py com 7148 linhas

## Context / Impact

- **Domain:** dev-squad
- **Area:** dashboard
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/dashboard/server.py` tem **7148 linhas** — extrair handlers para módulos por domínio. Já existe parte feita em `src/dashboard/routers/` (improvements). Continuar a extração.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Rodar CPU-bound em asyncio.to_thread.
- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/dashboard/server.py: 7148 linhas

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
- [ ] PR aberto e vinculado a este rec_id (bd750d70c1a3) para aprovação do operador.
- [ ] Commit subject contém `[IMP-bd750d70c1a3]` para reconciliação automática.
