---
rec_id: "edfae3dd5deb"
status: queued
domain: "dev-squad"
area: "memory"
priority: "P2"
created_at: "2026-05-27T19:06:13.967149+00:00"
---

# IMP-edfae3dd5deb — Vault: 10 link(s) quebrado(s) no segundo cérebro

## Title

Vault: 10 link(s) quebrado(s) no segundo cérebro

## Context / Impact

- **Domain:** dev-squad
- **Area:** memory
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

Wikilinks apontando para notas inexistentes degradam a navegação e a recuperação de memória dos agentes. Corrigir os alvos ou criar as notas.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

10 links quebrados. Ex.: 20 - Areas/Agentes IA/Cable.md→[[adr-004]]; 20 - Areas/Agentes IA/Prometheus.md→[[event_bus]]; 20 - Areas/Agentes IA/Prometheus.md→[[prompt_engineering]]; 20 - Areas/Agentes IA/Prometheus.md→[[vision critic]]

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (edfae3dd5deb) para aprovação do operador.
