---
rec_id: "8b6bf57f5bc3"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P1"
created_at: "2026-05-25T21:33:08.044350+00:00"
---

# IMP-8b6bf57f5bc3 — Função longa: run() em cyclops.py (700 linhas)

## Title

Função longa: run() em cyclops.py (700 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`run` em `src/agents/cyclops.py` tem 700 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/cyclops.py: run() = 700 linhas (limite 120).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (8b6bf57f5bc3) para aprovação do operador.
