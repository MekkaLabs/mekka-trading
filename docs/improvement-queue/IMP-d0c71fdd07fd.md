---
rec_id: "d0c71fdd07fd"
status: stale
domain: "dev-squad"
area: "vault"
priority: "P2"
created_at: "2026-05-28T15:39:37.713885+00:00"
---

# IMP-d0c71fdd07fd — Vault: TODO em 'Departamento de Melhoria Contínua' (linha 35)

## Title

Vault: TODO em 'Departamento de Melhoria Contínua' (linha 35)

## Context / Impact

- **Domain:** dev-squad
- **Area:** vault
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: scanner é read-only + fail-silent; nada executa sozinho; humano aprova;".

Origem: `10 - Projects/Departamento de Melhoria Contínua.md:35`. Considere transformar em story (ou marcar como resolvido).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

10 - Projects/Departamento de Melhoria Contínua.md:35 — TODO: scanner é read-only + fail-silent; nada executa sozinho; humano aprova;

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`vault_broken_links_after < vault_broken_links_before`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (d0c71fdd07fd) para aprovação do operador.
- [ ] Commit subject contém `[IMP-d0c71fdd07fd]` para reconciliação automática.
