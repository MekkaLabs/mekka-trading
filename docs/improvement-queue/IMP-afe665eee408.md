---
rec_id: "afe665eee408"
status: stale
domain: "dev-squad"
area: "agents"
priority: "P2"
created_at: "2026-05-28T15:39:38.381507+00:00"
---

# IMP-afe665eee408 — Vault: TODO em 'Prometheus' (linha 56)

## Title

Vault: TODO em 'Prometheus' (linha 56)

## Context / Impact

- **Domain:** dev-squad
- **Area:** agents
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: s os prompts em src/agents/".

Origem: `20 - Areas/Agentes IA/Prometheus.md:56`. Considere transformar em story (ou marcar como resolvido).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

20 - Areas/Agentes IA/Prometheus.md:56 — TODO: s os prompts em src/agents/

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
- [ ] PR aberto e vinculado a este rec_id (afe665eee408) para aprovação do operador.
- [ ] Commit subject contém `[IMP-afe665eee408]` para reconciliação automática.
