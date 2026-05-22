---
rec_id: "5edbf4efb6f4"
status: queued
domain: "dev-squad"
area: "backend"
priority: "P1"
created_at: "2026-05-21T19:12:51.830792+00:00"
---

# IMP-5edbf4efb6f4 — Função longa: _run() em batman.py (1239 linhas)

## Title

Função longa: _run() em batman.py (1239 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`_run` em `src/agents/batman.py` tem 1239 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/batman.py: _run() = 1239 linhas (limite 120).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (5edbf4efb6f4) para aprovação do operador.
