---
rec_id: "e1a3fc5f2eff"
status: stale
domain: "dev-squad"
area: "memory"
priority: "P2"
created_at: "2026-05-30T16:16:25.857002+00:00"
---

# IMP-e1a3fc5f2eff — Vault: 24 link(s) quebrado(s) no segundo cérebro

## Title

Vault: 24 link(s) quebrado(s) no segundo cérebro

## Context / Impact

- **Domain:** dev-squad
- **Area:** memory
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Wikilinks apontando para notas inexistentes degradam a navegação e a recuperação de memória dos agentes. Corrigir os alvos ou criar as notas.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

24 links quebrados. Ex.: 40 - Archive/legacy-roots/Bem-vindo (Obsidian default 2026-05-29).md→[[crie um link]]; 60 - Daily/2026-05-27-improvements-accepted.md→[[imp-1daa6c90a1b5]]; 60 - Daily/2026-05-27-improvements-accepted.md→[[imp-72474e56d6f0]]; 60 - Daily/2026-05-27-improvements-accepted.md→[[imp-c6069c689b96]]

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
- [ ] PR aberto e vinculado a este rec_id (e1a3fc5f2eff) para aprovação do operador.
- [ ] Commit subject contém `[IMP-e1a3fc5f2eff]` para reconciliação automática.
