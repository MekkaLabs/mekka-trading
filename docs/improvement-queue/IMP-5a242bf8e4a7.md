---
rec_id: "5a242bf8e4a7"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-25T21:33:03.695655+00:00"
---

# IMP-5a242bf8e4a7 — Refatorar iron_man.py (1785 linhas)

## Title

Refatorar iron_man.py (1785 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`src/agents/iron_man.py` tem 1785 linhas — acima do limite de 1500. Arquivos grandes concentram risco, dificultam revisão e testes. Quebrar em módulos coesos por responsabilidade.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/iron_man.py: 1785 linhas (limite 1500, enorme ≥4000).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (5a242bf8e4a7) para aprovação do operador.
