---
title: Agente — Nick Fury
type: agente
tags: [agente, orchestrator, command]
codename: Nick Fury
role: Mission Commander
status: ativo
layer: command
created: 2026-05-07
updated: 2026-05-13
---

# Agente — Nick Fury

> **Codinome**: Nick Fury
> **Papel**: Mission Commander — orquestra o ciclo completo de trading
> **Squad principal**: alpha-risk-command
> **Arquivo**: `src/agents/nick_fury.py`

## Missão

Coordenar todos os agentes no ciclo de trading: análise de mercado → sinal → risco → execução → monitoramento → recuperação.

## Ciclo Principal (`run_main_cycle`)

1. **Superman** — coleta dados de mercado (multi-exchange)
2. **Vision** — gera sinal de trading
3. **Batman** — valida risco
4. **Iron Man** — executa (paper ou live)
5. Salva `MissionReport` no DB

## Monitor Cycle (`run_monitor_cycle`) — Story 046

1. **Wolverine** — analisa posições e gera `RecoveryPlan`
2. **`_execute_recovery_plan()`** — executa ações do plano (EMERGENCY_CLOSE, CLOSE, SCALE_OUT)
3. **Cyclops** — monitora SL/TP price-based e fecha posições triggered
4. Retorna `{recovery_actions_taken, cyclops_triggered}`

## Interações

- Com [[Superman]]: delega coleta de mercado
- Com [[Vision]]: delega geração de sinal
- Com [[Batman]]: submete sinal para validação de risco
- Com [[Iron Man]]: delega execução
- Com [[Wolverine]]: roda monitor cycle + executa RecoveryPlan
- Com [[Cyclops]]: roda monitor cycle SL/TP

## Histórico de mudanças

- 2026-05-07 — Criado (Story 025)
- 2026-05-13 — Story 046: `_execute_recovery_plan()` + chamada ao Cyclops no monitor cycle
