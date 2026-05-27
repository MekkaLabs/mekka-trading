---
rec_id: "1daa6c90a1b5"
status: in_dev
domain: "dev-squad"
area: "agents"
priority: "P2"
created_at: "2026-05-27T22:03:36.690825+00:00"
---

# IMP-1daa6c90a1b5 — Cobertura de testes: 27 agentes sem `tests/test_*.py`

## Title

Cobertura de testes: 27 agentes sem `tests/test_*.py`

## Context / Impact

- **Domain:** dev-squad
- **Area:** agents
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

27 agentes não têm arquivo de teste correspondente. Faltam: `black_panther.py`, `code_auditor.py`, `cyclops.py`, `dashboard_scanner.py`, `deadpool.py`, `doctor_strange.py`, `flash.py`, `frontend_scanner.py`, … (+19 outros). Cada agente sem teste é risco silencioso — regressão só aparece em produção.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

27 agentes em src/agents/ sem teste em tests/

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
- [ ] PR aberto e vinculado a este rec_id (1daa6c90a1b5) para aprovação do operador.
- [ ] Commit subject contém `[IMP-1daa6c90a1b5]` para reconciliação automática.
