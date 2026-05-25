---
rec_id: "e9854bad0a39"
status: merged
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-21T19:12:46.248741+00:00"
---

# IMP-e9854bad0a39 — Cobertura de testes ausente em 28 agente(s)

## Title

Cobertura de testes ausente em 28 agente(s)

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

Agentes sem teste unitário correspondente em tests/. Sistema com dinheiro real exige cobertura nos agentes de execução/decisão.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 50.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

Sem test_*.py: aquaman, batman, beast, black_panther, code_auditor, cyclops, deadpool, doctor_strange, flash, galactus…

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (e9854bad0a39) para aprovação do operador.
