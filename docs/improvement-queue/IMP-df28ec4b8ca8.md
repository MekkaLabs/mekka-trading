---
rec_id: "df28ec4b8ca8"
status: queued
domain: "dev-squad"
area: "frontend"
priority: "P2"
created_at: "2026-05-21T03:20:14.803883+00:00"
---

# IMP-df28ec4b8ca8 — Melhorar contraste e legibilidade do modo claro

## Title

Melhorar contraste e legibilidade do modo claro

## Context / Impact

- **Domain:** dev-squad
- **Area:** frontend
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Vários widgets ficam ilegíveis no tema claro.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Checar light+dark, mobile e leitores de tela.
- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

Operador reportou widgets ilegíveis no modo claro em 2 sessões.

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (df28ec4b8ca8) para aprovação do operador.
