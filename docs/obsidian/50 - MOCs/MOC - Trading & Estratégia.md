---
title: MOC — Trading & Estratégia
type: moc
tags: [moc, trading, estrategia]
created: 2026-05-07
updated: 2026-05-13
---

# 📈 MOC — Trading & Estratégia

## Exchanges Suportadas (Story 046)

| Exchange | Status | Config |
|---|---|---|
| **Hyperliquid** | ✅ Primary (default) | `ACTIVE_EXCHANGE=hyperliquid` |
| **Bybit** | ✅ Via CCXT | `ACTIVE_EXCHANGE=bybit` + `BYBIT_API_KEY` |
| **Binance** | ✅ Via CCXT | `ACTIVE_EXCHANGE=binance` + `BINANCE_API_KEY` |

> Superman usa o primary com fallback automático. IronMan roteia execução live conforme `ACTIVE_EXCHANGE`.

## Pipeline de Sinal

```
Superman (mercado) → Vision (sinal) → Batman (risco) → Iron Man (execução)
```

## Timeframes

- **Primary**: `4h` (configurável via `PRIMARY_TIMEFRAME`)
- **Confirmation**: `1h`

## Indicadores (Superman)

RSI-14 · EMA-20/50 · Bollinger Bands · MACD · ATR-14 · Volume MA-20

## Equity (Paper Mode)

```
equity = initial_capital + realized_pnl + unrealized_pnl
```

- **Realized**: pares LONG/SHORT netados por símbolo
- **Unrealized**: mark prices do WebSocket Hyperliquid

## Gestão de Posições

- **Abertura**: IronMan via Vision → Batman aprovado
- **Fechamento manual**: botão no dashboard (paper mode)
- **SL/TP automático**: Cyclops (a cada 5 min, paper mode)
- **Recovery automático**: Wolverine → NickFury executa

## Notas relacionadas

- [[../20 - Areas/Agentes IA/Superman]]
- [[../20 - Areas/Agentes IA/Vision]]
- [[../20 - Areas/Agentes IA/Batman]]
- [[../20 - Areas/Agentes IA/Iron Man]]
- [[../20 - Areas/Agentes IA/Cyclops]]
- [[../20 - Areas/Trading/Market Data]]
