---
title: Nick Fury Runtime Cycles
type: architecture
tags: [arquitetura, runtime, agente]
owner: Nick Fury
created: 2026-05-07
updated: 2026-05-07
---

# Nick Fury Runtime Cycles

## Loops oficiais

- `run_main_cycle()` a cada ~4 horas
- `run_monitor_cycle()` a cada ~5 minutos
- `run_forever()` agenda os dois ciclos

## Sequência do Main Cycle

1. Portfolio Manager gera snapshot read-only
2. Professor X coordena Layer 1 em paralelo
3. Vision converte `MarketAnalysis` em `TradingSignal`
4. Batman aplica todos os gates de risco
5. Iron Man executa (paper por padrão)
6. Persistência SQLite por símbolo + logs

## Hard Rules

- Batman nunca pode ser bypassado
- Kill switch absoluto por env ou arquivo
- Sem estado compartilhado entre projetos
