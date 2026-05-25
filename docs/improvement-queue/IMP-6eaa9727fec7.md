---
rec_id: "6eaa9727fec7"
status: merged
domain: "dev-squad"
area: "backend"
priority: "P1"
created_at: "2026-05-21T19:12:51.165185+00:00"
---

# IMP-6eaa9727fec7 — Função longa: run() em cyclops.py (696 linhas)

## Title

Função longa: run() em cyclops.py (696 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`run` em `src/agents/cyclops.py` tem 696 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/cyclops.py: run() = 696 linhas (limite 120).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (6eaa9727fec7) para aprovação do operador.
