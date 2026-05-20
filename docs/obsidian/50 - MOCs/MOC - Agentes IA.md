---
title: MOC — Agentes IA
type: moc
tags: [moc, agente]
created: 2026-05-07
updated: 2026-05-13
---

# 🦸 MOC — Agentes IA

> Mapa vivo dos 16 agentes que compõem a operação Mekka Trading.

## Roster Completo

| Codinome | Papel | Domínio | Story |
|---|---|---|---|
| **Superman** | Chief Market Overseer | Visão geral de mercado + multi-exchange | 025 |
| **Batman** | Risk Guardian | Políticas de risco / kill switch | 025 |
| **Iron Man** | Execution Engineer | Hyperliquid / Bybit / Binance via CCXT | 025 / 046 |
| **Professor X** | Swarm Coordinator | Orquestração entre squads | 025 |
| **Doctor Strange** | Macro Probability Analyst | Probabilidades macro | 025 |
| **Flash** | Momentum Scalper | Estratégia de momentum/scalp | 033 |
| **Aquaman** | Liquidity Analyst | Análise de liquidez | 025 |
| **Spider-Man** | Anomaly Detector | Detecção de anomalias | 025 |
| **Wolverine** | Recovery Agent | Monitor + executa RecoveryPlan | 030 / **046** |
| **Black Panther** | Onchain Intelligence | Inteligência onchain | 025 |
| **Nick Fury** | Mission Commander | Orquestração geral do ciclo | 025 |
| **Vision** | Predictive Analyst | Análise preditiva + VisionCritic | 025 / 031 |
| **Thor** | Volatility Engine | Motor de volatilidade | 025 |
| **Deadpool** | Performance Analytics Agent | Backtest replay + métricas | 034 |
| **Portfolio Manager** | Equity Snapshot | Snapshot read-only de equity e posições | 026 |
| **Cyclops** | SL/TP Monitor | Fecha posições paper quando SL/TP é atingido | **046** ✅ |

## Destaques Story 046

- **Wolverine** agora **executa** o `RecoveryPlan` que gera — EMERGENCY_CLOSE, CLOSE, SCALE_OUT são acionados automaticamente
- **Cyclops** (novo agente) monitora SL/TP das posições paper a cada monitor cycle (5 min)
- **Iron Man** roteia execução para Bybit/Binance via CCXT quando `ACTIVE_EXCHANGE != hyperliquid`
- **Superman** usa `ACTIVE_EXCHANGE` como primary + fallback chain automático

## Squads Baseline

- `alpha-risk-command` — política de risco, governança do kill-switch, gates de validação
- `hyperliquid-mock-ops` — adaptador da exchange (mock), feed de mercado, ensaio de execução
- `market-intel-lab` — experimentos de sinal, contexto de anomalia e volatilidade

## Regras Duras (Hard Rules)

> ⚠️ Estas regras são **invioláveis** no projeto:
> - Nunca executar trades reais, exceto com `LIVE_TRADING_CONFIRMED=true` e Batman aprovado
> - Nunca contornar a validação de risco (Batman é obrigatório)
> - IronMan é o **único** caminho para ordens reais em qualquer exchange
> - Kill switch (`MEKKA_KILL_SWITCH=1` ou `data/.kill_switch`) é absoluto
> - Agentes nomeados com super-heróis — sem exceção

## Notas detalhadas por agente

- [[Superman]]
- [[Doctor Strange]]
- [[Black Panther]]
- [[Thor]]
- [[Aquaman]]
- [[Spider-Man]]
- [[Vision]]
- [[Professor X]]
- [[Batman]]
- [[Iron Man]]
- [[Nick Fury]]
- [[Portfolio Manager]]
- [[Wolverine]]
- [[Flash]]
- [[Deadpool]]
- [[Cyclops]]
