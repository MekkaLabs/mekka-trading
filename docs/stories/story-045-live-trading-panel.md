# Story 045 — Live Trading Panel + Squad Review

**Milestone:** 16 — Exchange-Grade Monitoring  
**Entregue em:** 2026-05-12  
**Status:** ✅ Done

---

## Context

Após Story 044 (fechar posições, Super Agressivo, Altcoins), o operador
conseguia abrir e fechar paper trades, mas não tinha visibilidade em tempo
real do resultado — tinha de atualizar a página manualmente e não havia
gráfico de preço.

Pedido do Gusta: _"preciso de um painel onde eu veja os trades abertos e
consiga acompanhar o resultado em tempo real, junto com o gráfico de
mercado ao lado. Do mesmo jeito que é feito nas corretoras e exchanges."_

Paralelamente foi solicitada uma revisão arquitetural completa usando o
framework AIOS-Core / Squads, resultando em um relatório com bugs e novos
agentes propostos.

---

## Goal

1. Painel **Live Trading** com gráfico de velas (candlestick) e posições
   abertas com PnL ao vivo, estilo exchange.
2. Preços ao vivo via WebSocket da Hyperliquid (`allMids`).
3. Relatório completo de revisão arquitetural com bugs e propostas de novos
   agentes.

---

## Scope Delivered

### Backend — `src/dashboard/server.py`

| Endpoint | Método | Função |
|----------|--------|--------|
| `/api/hl/candles` | GET | Busca OHLCV via ccxt Hyperliquid, params: `symbol`, `tf`, `limit` |
| `/ws/live` | WebSocket | Broadcast de preços + PnL em tempo real |

**Background tasks adicionados:**

- `_hl_price_pump_loop()` — conecta ao `wss://api.hyperliquid.xyz/ws`,
  subscreve `allMids`, mantém `self._hl_prices` atualizado; reconecta
  automaticamente em 5s após erro.
- `_live_price_broadcast_loop()` — a cada 1s envia `{type:"live_tick",
  prices:{...}, positions:[...], ts:"..."}` para todos os clientes
  conectados em `/ws/live`, com PnL calculado do mark price ao vivo.

### Frontend — `src/dashboard/static/`

**`index.html`** — nova página `sec-live-trading` (data-page="live"):
- Toolbar: selector de símbolo (BTC/ETH/SOL/AVAX/BNB/LINK) + timeframe
  (1m/5m/15m/1h/4h/1d) + live ticker com badge piscante.
- Layout split: gráfico à esquerda (flex-1) + sidebar de posições
  (320px).

**`app.js`** — bloco completo de Live Trading:

| Função | Responsabilidade |
|--------|-----------------|
| `_initLightweightChart()` | Cria chart dark-theme via `LightweightCharts`, série de velas + histograma de volume |
| `_liveLoadCandles(symbol, tf)` | GET `/api/hl/candles`, popula `_liveCandleSeries.setData()` |
| `_liveUpdateLastCandle(price)` | Atualiza close/high/low da última vela em tempo real |
| `_liveDrawPositionLines(positions)` | Linhas horizontais tracejadas no preço de entrada |
| `_liveRenderPositions(positions)` | Cards de posição com PnL em tempo real + botão Fechar |
| `_liveConnectWs()` | Conecta `/ws/live`, trata `live_tick`, auto-reconecta em 3s |
| `_bootLiveChart()` | Orquestra boot: init chart → load candles → connect WS |
| `_ensureLiveChartBooted()` | Lazy init (chamado de `_mkSetPage`) |

**`style.css`** — seção Live Trading:
```css
.live-split { display: grid; grid-template-columns: 1fr 320px; height: calc(100vh - 130px); }
.live-pos-card.pnl-up { border-left: 3px solid #26d07c; }
.live-pos-card.pnl-down { border-left: 3px solid #e94560; }
.live-dot-badge { animation: live-blink 1.5s ease-in-out infinite; }
```

### Squad Review — `docs/SQUAD_REVIEW.md`

Revisão completa de todos os 15 agentes do AIOS-Core. Findings:

**Bugs críticos (C):**
- [C1] Wolverine `RecoveryPlan` gerado mas não executado — módulo órfão.
- [C2] SL/TP bracket orders não monitorados após IronMan executar — sem Cyclops.
- [C3] Paper equity estática — equity não acumula P&L; drawdown Batman
  baseado em número incorreto.

**Bugs altos (H):**
- [H1] VisionCritic threshold hardcoded (70%) — ignora modo Super Agressivo.
- [H2] Nick Fury não valida `altcoins_enabled` antes de incluir alts.
- [H3] Deadpool Sharpe ratio com período fixo (30d), sem ajuste de regime.
- [H4] Flash sub-loop sem circuit breaker próprio.
- [H5] Superman CCXT sem retry em erro 429.

**Novos agentes propostos:**

| Agente | Papel |
|--------|-------|
| **Cyclops** | Order Manager — monitora SL/TP e cancela ordens órfãs |
| **Gamora** | Correlation Risk — detecta concentração em alts correlacionadas |
| **Scarlet Witch** | Macro Regime — analisa funding rate + open interest |
| **War Machine** | Backup Executor — failover quando IronMan falha |
| **Captain Marvel** | Signal Aggregator — consenso ponderado entre Vision + Flash |
| **Nick Fury Jr.** | Sub-ciclo 15min — coordena Flash dentro do loop maior |

---

## Hard Rules Mantidas

- Nenhum trade real executado (paper mode ativo).
- Sem chaves de API no front-end.
- Preços lidos da Hyperliquid em modo público (sem auth).
- Shutdown limpo: sockets e tasks cancelados em `_on_shutdown`.
- Agentes nomeados com super-heróis (sem ratos).

---

## Pipeline End-to-End

```
Hyperliquid WS (allMids)
    └─► _hl_price_pump_loop()  [servidor]
            └─► self._hl_prices{symbol: price}
                    └─► _live_price_broadcast_loop()  [1s tick]
                            └─► /ws/live  [WebSocket]
                                    └─► _liveConnectWs()  [browser]
                                            ├─► _liveUpdateLastCandle()  →  chart vela
                                            └─► _liveRenderPositions()  →  PnL cards

Operator clica símbolo/tf
    └─► _liveLoadCandles(symbol, tf)
            └─► GET /api/hl/candles
                    └─► ccxt.hyperliquid.fetch_ohlcv()
                            └─► _liveCandleSeries.setData()  [chart]
```

---

## Acceptance

- [x] Gráfico candlestick renderiza com dados históricos da Hyperliquid.
- [x] Preço ao vivo atualiza a última vela em tempo real.
- [x] Posições abertas aparecem na sidebar com PnL verde/vermelho.
- [x] Linhas de entry price desenhadas no chart.
- [x] Botão "Fechar" na sidebar fecha a posição (offsetting trade).
- [x] Selector de símbolo e timeframe funciona.
- [x] Badge "🔴 LIVE" pisca quando conectado.
- [x] `python -m py_compile src/dashboard/server.py` → OK
- [x] `node --check src/dashboard/static/app.js` → OK
- [x] `docs/SQUAD_REVIEW.md` entregue com 3C + 5H bugs + 6 novos agentes.

---

## What's Next

- **Story 046** — Fix [C3]: Equity dinâmica no paper mode (acumula P&L).
- **Story 047** — Fix [C1]: Wolverine RecoveryPlan execução real.
- **Story 048** — Implementar agente Cyclops (monitor de ordens SL/TP).
- **Story 049** — Fix [H1]: VisionCritic threshold dinâmico (via runtime_settings).

---

## Files Changed

```
src/dashboard/server.py            + _hl_price_pump_loop, _live_price_broadcast_loop,
                                     _handle_ws_live, _handle_hl_candles
src/dashboard/static/index.html   + sec-live-trading (chart + positions sidebar)
src/dashboard/static/app.js       + Live Trading block (~300 linhas)
src/dashboard/static/style.css    + Live Trading styles
docs/SQUAD_REVIEW.md              NEW — revisão arquitetural completa
docs/stories/story-045-live-trading-panel.md  NEW (este arquivo)
docs/stories/INDEX.md             + Milestone 16, story-045
```
