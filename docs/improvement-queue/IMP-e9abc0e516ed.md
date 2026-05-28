---
rec_id: "e9abc0e516ed"
status: stale
domain: "dev-squad"
area: "agents"
priority: "P2"
created_at: "2026-05-28T15:39:38.436822+00:00"
---

# IMP-e9abc0e516ed — Vault: TODO em 'Agente — Ice Man' (linha 57)

## Title

Vault: TODO em 'Agente — Ice Man' (linha 57)

## Context / Impact

- **Domain:** dev-squad
- **Area:** agents
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: ⏳ Pesquisa via GitHub/MCPs financeiros — futuro".

Origem: `20 - Areas/Agentes IA/Ice Man.md:57`. Considere transformar em story (ou marcar como resolvido).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

20 - Areas/Agentes IA/Ice Man.md:57 — TODO: ⏳ Pesquisa via GitHub/MCPs financeiros — futuro

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
- [ ] PR aberto e vinculado a este rec_id (e9abc0e516ed) para aprovação do operador.
- [ ] Commit subject contém `[IMP-e9abc0e516ed]` para reconciliação automática.
