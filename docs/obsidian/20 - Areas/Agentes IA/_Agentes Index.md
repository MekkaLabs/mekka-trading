---
title: Agentes IA — Index
type: area
tags: [area, agente]
created: 2026-05-07
updated: 2026-05-20
---

# Área — Agentes IA

> Uma nota por agente. Use `Template - Agente`. Roster organizado pela camada AIOX (Command → Strategy → Execution → Monitoring → Recovery → Analytics).

## Roster (20 agentes)

### 🎖️ Command Layer
- [x] [[Nick Fury]] — Mission Commander (orquestra o ciclo completo)
- [x] [[Professor X]] — Swarm Coordinator
- [x] [[Jean Grey]] — Memory Master (health scan do vault + manutenção do segundo cérebro)

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

### 🛠️ Continuous-Improvement Council
> Departamento de Melhoria Contínua — 7 scanners read-only por domínio →
> premortem → consolidação → operador. Atua nos heróis de trading/ops **e** nos
> squads de dev, memória e pesquisa externa.
- [x] [[Mekka]] — 👑 Commander & consolidador (lidera o conselho; `/Melhorias`)
- [x] [[Galactus]] — 🪐 Premortem / devorador de ideias (hunger score + failure modes)
- [x] [[Beast]] — 🐺 Scanner trading-ops (trades, gates, latência, qualidade de sinal)
- [x] CodeAuditor — 🔍 Scanner dev (`src/agents/code_auditor.py`: arquivos grandes, TODO/FIXME, testes ausentes, ruff)
- [x] RiskScanner — ⚠️ Scanner trading-ops (`src/agents/risk_scanner.py`: kill switch, drawdown, rejeições Batman)
- [x] OpsScanner — 🛠️ Scanner infra (`src/agents/ops_scanner.py`: erros recorrentes, CYCLE_ERROR, exceções no log)
- [x] [[Jean Grey]] — 🧠 MemoryScanner (vault: links quebrados/duplicatas/órfãs → propostas) + memória/vault
- [x] [[Ice Man]] — 🧊 ExternalResearcher (deps/CVEs via PyPI; pesquisa fora do sistema)
- [x] [[Sage]] — 📐 Measurement loop (baseline antes/depois + KPI do departamento)

> Cyclops, Wolverine **e todo o Improvement Council** (Mekka, Beast, Jean Grey,
> Galactus) NUNCA colocam ordens reais. Cyclops e Wolverine fazem paper trades
> (close/recover); o council é estritamente read-only (só escreve decisões de
> melhoria). **Iron Man é o único caminho para ordens live** em qualquer exchange.

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
