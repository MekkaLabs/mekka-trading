---
title: Arquitetura Atual
type: architecture
created: 2026-05-15
updated: 2026-05-15
---

# Arquitetura Atual

Última revisão confirmada: Story 125 (2026-05-15).

## Pipeline Python (operação viva)

1. Nick Fury inicia ciclo por símbolo.
2. Professor X orquestra Layer 1 em paralelo.
3. Vision gera `TradingSignal` (com fallback seguro).
4. Batman valida risco (gate intransponível).
5. Iron Man executa (paper por padrão, live sob condições).
6. Persistência SQLite + audit trail.

## Hardening recente (Story 125)

- `LLMClient` centraliza chamadas LLM com fallback OpenAI -> Anthropic Claude.
- Superman roda em Python 3.14 com indicadores manuais (RSI/EMA/BB/MACD/ATR) sem dependência de `pandas_ta`/`numba`.
- Funding provider corrigido para usar `aiohttp.ClientTimeout`.
- Telegram alerter em pt-BR com explicação de entrada e duração estimada.
- Dashboard Pixel Office em layout 2x2 com heróis adicionais.

## Módulos principais

- `src/agents/`
- `src/models/`
- `src/persistence/`
- `src/services/`
- `src/dashboard/`
- `workflows/` e `cli/` em TS para superfícies legadas/complementares

## Persistência

Banco principal: `data/mekka_trading.db`.

Tabelas-chave:

- `signals`
- `trades`
- `daily_pnl`
- `audit_log`
