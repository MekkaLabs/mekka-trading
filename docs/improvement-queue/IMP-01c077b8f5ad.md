---
rec_id: "01c077b8f5ad"
status: merged
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-21T11:08:17.021953+00:00"
---

# IMP-01c077b8f5ad — Refatorar nick_fury.py (2682 linhas)

## Title

Refatorar nick_fury.py (2682 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/agents/nick_fury.py` tem 2682 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/nick_fury.py: 2682 linhas (limite 1500, enorme ≥4000).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (01c077b8f5ad) para aprovação do operador.
