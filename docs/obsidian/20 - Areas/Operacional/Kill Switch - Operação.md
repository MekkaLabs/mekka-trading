---
title: Kill Switch — Operação
type: runbook
tags: [runbook, risco, ops, kill-switch]
created: 2026-05-07
updated: 2026-05-07
---

# Kill Switch — Operação

## Triggers absolutos

- `MEKKA_KILL_SWITCH=1`
- Arquivo `data/.kill_switch`
- Spider-Man com severidade `HIGH` (`should_pause=True`)

## Verificação

1. Confirmar presença da variável ou arquivo
2. Validar que Batman retorna `KILL_SWITCH` ou `REJECTED`
3. Confirmar ausência de ordens na execução

## Retorno controlado

1. Remover trigger manual
2. Rodar ciclo monitorado em paper
3. Revisar logs e audit antes de normalizar
