---
rec_id: "6a2f29cc4a9f"
status: queued
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-27T19:47:05.436884+00:00"
---

# IMP-6a2f29cc4a9f — Refatorar iron_man.py (2141 linhas)

## Title

Refatorar iron_man.py (2141 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/agents/iron_man.py` tem 2141 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/iron_man.py: 2141 linhas (limite 1500, enorme ≥4000).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (6a2f29cc4a9f) para aprovação do operador.
