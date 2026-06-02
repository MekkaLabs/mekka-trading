---
rec_id: "c6fe17ff9544"
status: stale
domain: "dev-squad"
area: "agents"
priority: "P3"
created_at: "2026-05-28T15:39:38.877985+00:00"
---

# IMP-c6fe17ff9544 — Refatorar batman.py (1798 linhas)

## Title

Refatorar batman.py (1798 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** agents
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`src/agents/batman.py` tem 1798 linhas (acima do warn 1500). Monitorar crescimento.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/batman.py: 1798 linhas (limite 1500, enorme ≥4000).

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`agent_p95_latency_ms_after < agent_p95_latency_ms_before`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (c6fe17ff9544) para aprovação do operador.
- [ ] Commit subject contém `[IMP-c6fe17ff9544]` para reconciliação automática.
