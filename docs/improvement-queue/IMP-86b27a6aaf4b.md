---
rec_id: "86b27a6aaf4b"
status: stale
domain: "dev-squad"
area: "backend"
priority: "P2"
created_at: "2026-05-30T16:16:22.979284+00:00"
---

# IMP-86b27a6aaf4b — Backend coverage: 102 services sem teste

## Title

Backend coverage: 102 services sem teste

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND_WITH_MITIGATION
- **Rationale:** Mekka aprova condicionalmente: seguir SOMENTE com as mitigações do Galactus e validação em paper/testnet antes de produção.

## Description

102 services em `src/services/` não têm teste correspondente em `tests/`. Faltam: `agent_degradation_detector`, `agent_step_guard`, `alert_throttle_manager`, `analysis_prompt_cache`, `asset_classifier`, `auto_learning_scheduler`, `auto_signal_linter`, `backtest_benchmark`, … (+94).

## Galactus Premortem

- **Verdict:** NEEDS_HARDENING
- **Hunger:** 62.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

102 services sem tests/test_*.py

## Success KPI (P1.9 — outcome measurement)

> Bridge `improvement_memory_bridge` tirará snapshot Sage ANTES (no
> momento da aprovação) e DEPOIS (após merged), permitindo atribuir
> impacto real desta melhoria.

`_(definir KPI mensurável antes de fechar)_`

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (86b27a6aaf4b) para aprovação do operador.
- [ ] Commit subject contém `[IMP-86b27a6aaf4b]` para reconciliação automática.
