---
title: Batman — Risk Guardian
type: risk
tags: [risco, agente, batman]
status: ativo
created: 2026-05-07
updated: 2026-05-07
---

# Batman — Risk Guardian

Agente determinístico (sem LLM) que decide: `APPROVED`, `REDUCED`, `REJECTED` ou `KILL_SWITCH`.

## Gates obrigatórios

- Kill switch
- Drawdown diário
- Máximo de posições abertas
- Máximo de trades por dia
- Confiança mínima
- R:R mínimo
- Teto de tamanho e alavancagem
- Multiplicador de Thor + penalidade de liquidez de Aquaman

## Regra de ouro

Sem aprovação do Batman, não existe execução.
