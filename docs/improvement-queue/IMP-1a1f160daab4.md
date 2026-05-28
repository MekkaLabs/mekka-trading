---
rec_id: "1a1f160daab4"
status: stale
domain: "dev-squad"
area: "agents"
priority: "P3"
created_at: "2026-05-28T15:39:38.932470+00:00"
---

# IMP-1a1f160daab4 — Reduzir captura genérica de exceção em iron_man.py

## Title

Reduzir captura genérica de exceção em iron_man.py

## Context / Impact

- **Domain:** dev-squad
- **Area:** agents
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`src/agents/iron_man.py` tem **6 `except Exception`** (sendo 0 truly-bare). Captura genérica dificulta diagnóstico — substituir por tipos específicos onde possível, marcar `# noqa: BLE001` onde o try-broad é intencional.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/iron_man.py: 0 bare + 6 broad except = 6

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
- [ ] PR aberto e vinculado a este rec_id (1a1f160daab4) para aprovação do operador.
- [ ] Commit subject contém `[IMP-1a1f160daab4]` para reconciliação automática.
