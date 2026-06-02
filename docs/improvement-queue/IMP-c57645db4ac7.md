---
rec_id: "c57645db4ac7"
status: stale
domain: "dev-squad"
area: "architecture"
priority: "P2"
created_at: "2026-05-28T15:39:38.337280+00:00"
---

# IMP-c57645db4ac7 — Vault: TODO em 'ADR-003 — Bybit Testnet Readiness' (linha 84)

## Title

Vault: TODO em 'ADR-003 — Bybit Testnet Readiness' (linha 84)

## Context / Impact

- **Domain:** dev-squad
- **Area:** architecture
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: no código e no backlog.".

Origem: `30 - Resources/Decisoes Tecnicas/ADR-003 - Bybit Testnet Readiness.md:84`. Considere transformar em story (ou marcar como resolvido).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

30 - Resources/Decisoes Tecnicas/ADR-003 - Bybit Testnet Readiness.md:84 — TODO: no código e no backlog.

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`_(manual reviewer confirmation in PR)_`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (c57645db4ac7) para aprovação do operador.
- [ ] Commit subject contém `[IMP-c57645db4ac7]` para reconciliação automática.
