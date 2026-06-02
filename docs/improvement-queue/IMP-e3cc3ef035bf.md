---
rec_id: "e3cc3ef035bf"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-30T16:16:24.256337+00:00"
---

# IMP-e3cc3ef035bf — Cobertura de testes ausente em 29 agente(s)

## Title

Cobertura de testes ausente em 29 agente(s)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

Agentes sem teste unitário correspondente em tests/. Sistema com dinheiro real exige cobertura nos agentes de execução/decisão.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

Sem test_*.py: agents_scanner, aquaman, backend_scanner, beast, black_panther, code_auditor, cyclops, dashboard_scanner, deadpool, doctor_strange…

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
- [ ] PR aberto e vinculado a este rec_id (e3cc3ef035bf) para aprovação do operador.
- [ ] Commit subject contém `[IMP-e3cc3ef035bf]` para reconciliação automática.
