---
title: MOC — Trading & Estratégia
type: moc
tags: [moc, estrategia, trading]
created: 2026-05-07
---

# 📈 MOC — Trading & Estratégia

> Mapa vivo das estratégias, ativos, sinais e regimes de mercado.

## Estado Atual

- **Modo**: Paper Trading (PAPER_TRADING=true)
- **Exchange**: Hyperliquid (mock-only)
- **Ativos default**: BTC, ETH, SOL
- **Limites de risco**:
  - Posição máxima: 2% do equity
  - Alavancagem máxima: 5x
  - Drawdown diário máximo: 10%

## Pilares da Estratégia

1. **Risk-First** — qualquer execução passa pelo risk-engine antes de chegar à exchange
2. **Multi-Agent** — sinais vêm de squads especializadas (momentum, liquidez, anomalia, macro)
3. **Observable** — toda decisão gera evento + log + audit
4. **Replayable** — backtesting/replay como cidadão de primeira classe

## Engines

- [[../20 - Areas/Trading/Strategy Engine|Strategy Engine]] — sinais e geração de hipóteses
- [[../20 - Areas/Trading/Execution Engine|Execution Engine]] — paper-only por enquanto
- [[../20 - Areas/Trading/Backtesting|Backtesting]] — replay e validação histórica
- [[../20 - Areas/Trading/Market Data|Market Data]] — feeds de preço e profundidade

## Regimes de Mercado

```dataview
LIST
FROM #regime
SORT file.name ASC
```

## Estratégias documentadas

```dataview
TABLE without ID
  file.link AS "Estratégia",
  status AS "Status",
  asset AS "Ativo",
  timeframe AS "Timeframe"
FROM #estrategia
SORT status ASC
```

## Próximos passos

- [ ] Documentar cada estratégia em `20 - Areas/Trading/Estratégias/`
- [ ] Mapear regimes (bull/bear/range/volatility) e respostas táticas
- [ ] Vincular cada estratégia a um agente responsável
