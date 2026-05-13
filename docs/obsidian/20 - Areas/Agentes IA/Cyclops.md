---
title: Agente — Cyclops
type: agente
tags: [agente, monitor, risk]
codename: Cyclops
role: SL/TP Monitor
status: ativo
layer: execution
created: 2026-05-13
updated: 2026-05-13
---

# Agente — Cyclops

> **Codinome**: Cyclops
> **Papel**: SL/TP Monitor — fecha posições paper automaticamente quando preço cruza threshold
> **Squad principal**: alpha-risk-command
> **Story**: 046 (novo)
> **Arquivo**: `src/agents/cyclops.py`

## Missão

Monitorar todas as posições paper abertas e executar fechamento automático quando o preço de mercado cruza o Stop Loss ou Take Profit definido na abertura da posição.

## Responsabilidades

- Ler todos os paper trades do banco de dados a cada monitor cycle (5 min)
- Calcular posição líquida (net LONG/SHORT) por símbolo
- Extrair SL/TP do campo `raw.metadata` de cada trade
- Comparar mark price atual com os thresholds
- Inserir trade de fechamento com `order_id = "CYCLOPS-{uuid}"` quando triggered
- Logar evento `SL_TP_TRIGGERED` no audit log

## Lógica de Trigger

```
LONG  → SL: mark ≤ sl_trigger  |  TP: mark ≥ tp_trigger
SHORT → SL: mark ≥ sl_trigger  |  TP: mark ≤ tp_trigger
```

## Inputs

- Todos os paper trades do DB (`MekkaRepository.get_all_paper_trades()`)
- Preços de mercado atuais (`current_prices: dict`)

## Outputs

- Trade de fechamento salvo no DB via `MekkaRepository.save_trade()`
- Evento `SL_TP_TRIGGERED` no audit log
- Retorna contagem de posições fechadas (`int`)

## Hard Rules

- Cyclops NUNCA coloca ordens reais — somente paper trades
- No-op quando `PAPER_TRADING=False`
- IronMan é o único caminho para ordens reais

## Interações

- Com [[Nick Fury]]: chamado em `run_monitor_cycle()` após execução do RecoveryPlan
- Com [[Wolverine]]: ambos monitoram posições, mas Cyclops foca em SL/TP price-based e Wolverine em drawdown/risk
- Com [[Iron Man]]: NÃO interage diretamente — paper only

## Histórico de mudanças

- 2026-05-13 — Criado na Story 046 (bug fix [C2] do Squad Review)
