---
title: Agente — Wolverine
type: agente
tags: [agente, recovery, monitor]
codename: Wolverine
role: Recovery Agent
status: ativo
layer: execution
created: 2026-05-07
updated: 2026-05-13
---

# Agente — Wolverine

> **Codinome**: Wolverine
> **Papel**: Recovery Agent — monitora posições e executa plano de recuperação
> **Squad principal**: alpha-risk-command
> **Story**: 030 (criado), 046 (execution wired ✅)
> **Arquivo**: `src/agents/nick_fury.py` (integrado ao NickFury monitor cycle)

## Missão

Monitorar posições abertas em busca de sinais de risco (drawdown excessivo, posições estagnadas, condições adversas de mercado) e **executar automaticamente** o plano de recuperação gerado.

## Responsabilidades

- Analisar posições abertas e calcular métricas de risco por posição
- Gerar um `RecoveryPlan` com ações recomendadas
- **Executar** o plano quando `plan.needs_action = True` (Story 046)

## RecoveryPlan — Ações Suportadas

| Ação | Comportamento |
|---|---|
| `EMERGENCY_CLOSE` | Fecha 100% da posição imediatamente |
| `CLOSE` | Fecha 100% da posição |
| `SCALE_OUT` | Fecha 50% da posição |
| `TIGHTEN_STOP` | Somente log (advisory) |
| `TRAIL_STOP` | Somente log (advisory) |
| `HOLD` | Somente log (advisory) |

## Paper Mode vs Live Mode

- **Paper**: insere `ExecutionResult(status=PAPER)` via `MekkaRepository.save_trade()`
- **Live**: constrói sinal de fechamento e delega ao [[Iron Man]]

## Interações

- Com [[Nick Fury]]: chamado em `run_monitor_cycle()`, execução via `_execute_recovery_plan()`
- Com [[Cyclops]]: ambos rodam no mesmo monitor cycle; Wolverine age em drawdown, Cyclops age em SL/TP price-based
- Com [[Iron Man]]: delega execução live quando `LIVE_TRADING_CONFIRMED=true`

## Histórico de mudanças

- 2026-05-07 — Criado (Story 030) — somente gerava RecoveryPlan, sem executar
- 2026-05-13 — Story 046 — `_execute_recovery_plan()` implementado no NickFury; Wolverine agora **executa** o plano gerado
