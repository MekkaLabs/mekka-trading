---
rec_id: "ea324fca3e06"
status: stale
domain: "dev-squad"
area: "research"
priority: "P2"
created_at: "2026-05-27T19:47:07.286767+00:00"
---

# IMP-ea324fca3e06 — Atualizar ccxt 4.5.54 → 4.5.56 (API de exchange)

## Title

Atualizar ccxt 4.5.54 → 4.5.56 (API de exchange)

## Context / Impact

- **Domain:** dev-squad
- **Area:** research
- **Priority:** P2
- **Impact:** MEDIUM
- **Council decision:** RECOMMEND
- **Rationale:** Sobreviveu ao premortem do Galactus. Mekka recomenda seguir com o cuidado padrão de revisão/teste.

## Description

`ccxt` está em 4.5.54; a última no PyPI é 4.5.56. Para um bot que opera ao vivo, um ccxt desatualizado pode ter suporte velho a endpoints/símbolos das exchanges (Binance/Bybit). Revisar changelog por breaking changes e atualizar com teste em testnet.

## Galactus Premortem

- **Verdict:** SURVIVES
- **Hunger:** 37.5

**Failure modes:**

- _(nenhum registrado)_

**Mitigations:**

- Definir plano de rollback e feature flag antes de aplicar.
- Anexar métrica/baseline antes/depois e critério de sucesso mensurável.

## Evidence

PyPI: ccxt instalado 4.5.54, latest 4.5.56.

## Acceptance Criteria

- [ ] Mudança implementada conforme a descrição acima.
- [ ] Mitigações do Galactus endereçadas no código/testes.
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam.
- [ ] Validado em paper/testnet antes de qualquer impacto em produção.
- [ ] PR aberto e vinculado a este rec_id (ea324fca3e06) para aprovação do operador.
