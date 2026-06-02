---
rec_id: "a62a665e8a7a"
status: stale
domain: "dev-squad"
area: "architecture"
priority: "P2"
created_at: "2026-05-28T15:39:38.298023+00:00"
---

# IMP-a62a665e8a7a — Vault: TODO em 'ADR-002 — Suporte Multi-Exchange via CCXT' (linha 59)

## Title

Vault: TODO em 'ADR-002 — Suporte Multi-Exchange via CCXT' (linha 59)

## Context / Impact

- **Domain:** dev-squad
- **Area:** architecture
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Sinal encontrado pelo VaultScanner no segundo cérebro: "TODO: s os exchanges); algumas features avançadas (HL position close-on-trigger nativo) não mapeiam 1:1 na interface unificada — por isso HL continua usando SDK nativo.".

Origem: `30 - Resources/Decisoes Tecnicas/ADR-002 - Multi-Exchange via CCXT.md:59`. Considere transformar em story (ou marcar como resolvido).

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

30 - Resources/Decisoes Tecnicas/ADR-002 - Multi-Exchange via CCXT.md:59 — TODO: s os exchanges); algumas features avançadas (HL position close-on-trigger nativo) não mapeiam 1:1 na interface uni

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
- [ ] PR aberto e vinculado a este rec_id (a62a665e8a7a) para aprovação do operador.
- [ ] Commit subject contém `[IMP-a62a665e8a7a]` para reconciliação automática.
