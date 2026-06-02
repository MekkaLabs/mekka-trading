---
rec_id: "ed58af6d6ed9"
status: queued
domain: "dev-squad"
area: "research"
priority: "P3"
created_at: "2026-06-02T01:11:05.560066+00:00"
---

# IMP-ed58af6d6ed9 — Dependências desatualizadas (3)

## Title

Dependências desatualizadas (3)

## Context / Impact

- **Domain:** dev-squad
- **Area:** research
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Bibliotecas do stack atrás da última versão do PyPI. Atualizar em lote (com teste) reduz dívida e captura correções de segurança/bugs.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 25.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

aiohttp 3.13.5→3.14.0; openai 2.36.0→2.40.0; anthropic 0.104.1→0.105.2

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`_(definir KPI mensurável antes de fechar)_`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (ed58af6d6ed9) para aprovação do operador.
- [ ] Commit subject contém `[IMP-ed58af6d6ed9]` para reconciliação automática.
