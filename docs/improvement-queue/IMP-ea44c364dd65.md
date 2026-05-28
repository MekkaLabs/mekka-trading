---
rec_id: "ea44c364dd65"
status: stale
domain: "dev-squad"
area: "memory"
priority: "P3"
created_at: "2026-05-28T15:39:38.765680+00:00"
---

# IMP-ea44c364dd65 — Vault: 7 link(s) quebrado(s) no segundo cérebro

## Title

Vault: 7 link(s) quebrado(s) no segundo cérebro

## Context / Impact

- **Domain:** dev-squad
- **Area:** memory
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Wikilinks apontando para notas inexistentes degradam a navegação e a recuperação de memória dos agentes. Corrigir os alvos ou criar as notas.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

7 links quebrados. Ex.: 20 - Areas/Agentes IA/Cable.md→[[adr-004]]; 20 - Areas/Agentes IA/Prometheus.md→[[prompt_engineering]]; 20 - Areas/Agentes IA/Prometheus.md→[[vision critic]]; 60 - Daily/2026-05-27-improvements-accepted.md→[[imp-1daa6c90a1b5]]

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`agent_memory_resolved_pct > 0.80`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (ea44c364dd65) para aprovação do operador.
- [ ] Commit subject contém `[IMP-ea44c364dd65]` para reconciliação automática.
