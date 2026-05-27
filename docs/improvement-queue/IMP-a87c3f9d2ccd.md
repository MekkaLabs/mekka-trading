---
rec_id: "a87c3f9d2ccd"
status: queued
domain: "dev-squad"
area: "backend"
priority: "P1"
created_at: "2026-05-26T21:22:24.781749+00:00"
---

# IMP-a87c3f9d2ccd — Refatorar server.py (7073 linhas)

## Title

Refatorar server.py (7073 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/dashboard/server.py` tem 7073 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/dashboard/server.py: 7073 linhas (limite 1500, enorme ≥4000).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (a87c3f9d2ccd) para aprovação do operador.
