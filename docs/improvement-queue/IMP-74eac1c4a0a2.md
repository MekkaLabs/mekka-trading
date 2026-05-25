---
rec_id: "74eac1c4a0a2"
status: merged
domain: "dev-squad"
area: "backend"
priority: "P3"
created_at: "2026-05-21T11:08:25.774023+00:00"
---

# IMP-74eac1c4a0a2 — Resolver 6 marcadores TODO/FIXME em code_auditor.py

## Title

Resolver 6 marcadores TODO/FIXME em code_auditor.py

## Context / Impact

- **Domain:** dev-squad
- **Area:** backend
- **Priority:** P3
- **Impact:** LOW
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`src/agents/code_auditor.py` acumula 6 marcadores TODO/FIXME/HACK. Dívida explícita deixada no código — triagem e resolução.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

src/agents/code_auditor.py:11 • TODO / FIXME / HACK    — explicit debt markers left in code

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (74eac1c4a0a2) para aprovação do operador.
