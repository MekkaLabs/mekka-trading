---
rec_id: "5d2ee61a4dc8"
status: queued
domain: "dev-squad"
area: "calibration"
priority: "P3"
created_at: "2026-06-02T01:10:40.755618+00:00"
---

# IMP-5d2ee61a4dc8 — Mentor: max_daily_drawdown_pct 0.1 → 0.05

## Title

Mentor: max_daily_drawdown_pct 0.1 → 0.05

## Context / Impact

- **Domain:** dev-squad
- **Area:** calibration
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Drawdown hoje 8.00% está em 80% do limite (10.00%). Apertar o cap diário evita que uma sequência ruim consuma todo o teto antes do operador notar.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

n=None, period=None, mentor_conf=0.70

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`param_change_did_not_regress_win_rate_7d`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (5d2ee61a4dc8) para aprovação do operador.
- [ ] Commit subject contém `[IMP-5d2ee61a4dc8]` para reconciliação automática.
