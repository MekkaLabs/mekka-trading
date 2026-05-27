---
rec_id: "a331a53dbf80"
status: queued
domain: "trading-ops"
area: "risk"
priority: "P2"
created_at: "2026-05-25T21:33:04.977580+00:00"
---

# IMP-a331a53dbf80 — Kill switch disparou 2× em 7d

## Title

Kill switch disparou 2× em 7d

## Context / Impact

- **Domain:** trading-ops
- **Area:** risk
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

Disparos repetidos do kill switch indicam fragilidade de risco ou thresholds mal calibrados. Revisar gatilhos e limites.

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 75.0

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

2 eventos de kill switch no período.

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (a331a53dbf80) para aprovação do operador.
