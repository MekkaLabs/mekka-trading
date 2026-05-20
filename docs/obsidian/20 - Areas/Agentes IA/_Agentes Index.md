---
title: Agentes IA — Index
type: area
tags: [area, agente]
created: 2026-05-07
updated: 2026-05-20
---

# Área — Agentes IA

> Uma nota por agente. Use `Template - Agente`. Roster organizado pela camada AIOX (Command → Strategy → Execution → Monitoring → Recovery → Analytics).

## Roster (17 agentes)

### 🎖️ Command Layer
- [x] [[Nick Fury]] — Mission Commander (orquestra o ciclo completo)
- [x] [[Professor X]] — Swarm Coordinator

### 🔭 Strategy Layer
- [x] [[Superman]] — Chief Market Overseer (multi-exchange via CCXT)
- [x] [[Vision]] — Predictive Analyst (+ VisionCritic + MoA pattern)
- [x] [[Doctor Strange]] — Macro Probability Analyst
- [x] [[Aquaman]] — Liquidity Analyst
- [x] [[Black Panther]] — Onchain Intelligence
- [x] [[Thor]] — Volatility Engine
- [x] [[Flash]] — Momentum Scalper

### ⚡ Execution Layer
- [x] [[Iron Man]] — Execution Engineer (Hyperliquid / Bybit / Binance via CCXT)
- [x] [[Batman]] — Risk Guardian (gates 3o/3p/3q/3m/3n + kill switch)

### 🔍 Monitoring Layer
- [x] [[Cyclops]] — SL/TP Monitor (fecha posições paper quando trigger é atingido — Story 046)
- [x] [[Spider-Man]] — Anomaly Detector
- [x] [[Portfolio Manager]] — Equity & Open Positions Snapshot

### 🩹 Recovery Layer
- [x] [[Wolverine]] — Recovery Agent (executa RecoveryPlan: EMERGENCY_CLOSE, CLOSE, SCALE_OUT)

### 📊 Analytics Layer
- [x] [[Deadpool]] — Performance Analytics Agent (daily + weekly reports)
- [x] [[Beast]] — Continuous Improvement Analyst (Story 248, codex M40)

> Cyclops, Wolverine **e Beast** NUNCA colocam ordens reais. Cyclops e
> Wolverine fazem paper trades (close/recover); Beast é estritamente
> read-only. **Iron Man é o único caminho para ordens live** em
> qualquer exchange.

## Agentes documentados

```dataview
TABLE without ID
  file.link AS "Agente",
  role AS "Papel",
  status AS "Status"
FROM "20 - Areas/Agentes IA"
WHERE type = "agente"
SORT file.name ASC
```
