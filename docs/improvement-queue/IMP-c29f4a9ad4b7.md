---
rec_id: "c29f4a9ad4b7"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P1"
created_at: "2026-05-27T19:47:04.391000+00:00"
---

# IMP-c29f4a9ad4b7 — Função longa: _place_ccxt_order() em iron_man.py (448 linhas)

## Title

Função longa: _place_ccxt_order() em iron_man.py (448 linhas)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P1
- **Impact:** HIGH
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

`_place_ccxt_order` em `src/agents/iron_man.py` tem 448 linhas (limite 120). Funções longas escondem complexidade e dificultam teste — extrair em helpers.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/iron_man.py: _place_ccxt_order() = 448 linhas (limite 120).

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (c29f4a9ad4b7) para aprovação do operador.
