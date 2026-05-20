---
title: Stories do Projeto
type: referencia
tags: [externa, stories, roadmap]
created: 2026-05-07
updated: 2026-05-19
---

# Stories do Projeto — Mekka Trading

> Todas as stories estão em `docs/stories/` no repositório.
> **Última story entregue: 140** (Degraded Mode)
> **Total: 61 stories** (numeração esparsa — alguns números reservados/saltados)

> ⚠️ Esta lista é mantida manualmente. O script
> `scripts/sync_obsidian.py` (TODO em backlog) automatizará a sincronia.

## Milestones 1–17 — Fundação + Mainnet Readiness (✅ entregues)

| Range | Tema | Status |
|---|---|---|
| 001–002 | Mekka Foundation + Megazord Runtime v1 | ✅ |
| 003–009 | Stress regime + Observability + Replay | ✅ |
| 010–017 | Alerting + DLQ + Backpressure | ✅ |
| 018–024 | Ops Governance + Suppression + Audit KPIs | ✅ |
| 025–026 | Strategic Pipeline + Portfolio Manager | ✅ |
| 027–029 | Daily PnL + Contract Hardening + Safety Net | ✅ |
| 030–032b | Wolverine + Vision Critic + Audit shim | ✅ |
| 033–035b | Flash + Deadpool + Telegram (alerter + inbound) | ✅ |
| 036–037 | Mainnet Readiness + Gate Infrastructure | ✅ |

## Milestone 18 — Dashboard + Analytics (✅)

| Story | Título |
|---|---|
| 039 | Daily Perf Writer |
| 040 | Dashboard v2 (Pages, TopBar, TradeNow) |
| 041 | Broker Adapter |
| 042 | Prefs Endpoint |
| 043 | Paper Trade Persistence |
| 044 | Trading Modes + Close Position |
| 045 | Live Trading Panel + Squad Review |
| **046** | **Dynamic Equity + Wolverine Exec + Cyclops + Bybit** |

## Milestones 19–21 — Memory Intelligence + LangGraph (✅)

| Story | Título |
|---|---|
| 125 | LLM Fallback Superman (Python 3.14 compat) |
| 126 | LangGraph Checkpointing (durable execution) |
| 127 | LangGraph Interrupt/Resume (trade approval) |
| 128 | Semantic Memory |
| 129 | Layer 1 Parallel Subgraph |
| 130 | Vision Iterative Reflection |
| 131 | Vision Mixture of Agents (MoA) |
| 132 | Composite Memory Scoring |
| 133 | Vision Pre-Reasoning |
| 134 | Memory Consolidation |
| 135 | Adaptive Layer-1 Routing |
| 136 | Mekka Event Bus (pub/sub in-process) |

## Milestone (lacuna) — Degraded Mode

| Story | Título |
|---|---|
| 140 | Degraded Mode |

> Stories 137–139 não foram entregues (numeração reservada / pulada).

## Milestone 40 — Agent Communication Upgrade (codex, ✅)

Entregue pelo codex em 2026-05-19 em sessão paralela à M22. Sete stories que reorganizam a comunicação entre agentes + adicionam capacidade de melhoria contínua e checkpointing por ciclo.

| Story | Título |
|---|---|
| 244 | Flash→Vision direct link |
| 245 | DebateVerdict→Vision |
| 247 | Batman gate 3r — Flash divergence rejection |
| 248 | **Beast — Continuous Improvement Agent** ([[Beast]]) |
| 249 | DecisionMemory |
| 250 | Vision structured output (JSON schema) |
| 251 | CycleCheckpoint |

> Story 246 reservada / não entregue.

## Milestone 22 — Bybit Testnet Readiness (em andamento)

Esta milestone **não tem story numerada** ainda — foi entregue como uma sessão pontual em 2026-05-19. Decisão técnica capturada em [[ADR-003 - Bybit Testnet Readiness]] e runbook em [[Runbook - Bybit Testnet Setup]]. Resumo dos commits:

| Commit | Tema |
|---|---|
| `b7cd04c` | Sandbox routing + conditional credential validation (settings.py + iron_man + superman) |
| `b039067` | .env.example com 3 perfis (HL paper, Bybit testnet paper, Bybit testnet live) |
| `e58c7c1` | Exchange-agnostic price feed + Bybit CCXT positions (`src/services/price_feed.py`) |
| `2d1c898` | Env badge no header (paper/testnet/mainnet) |
| `fc41821` | Clock skew pre-flight check para CCXT orders |
| `9009b34` | Painel Trading Mode no Overview + consolidação dos dois sistemas |

## Próximas Stories (backlog)

- [ ] **Bug #4 — Symbol normalization** (`MarketRegistry`) — centraliza `BTC ↔ BTCUSDT ↔ BTC-USD`
- [ ] **Bug #5 — Teste de integração Bybit testnet** (skip-by-default)
- [ ] **scripts/sync_obsidian.py** — sincroniza esta lista automaticamente
- [ ] **ADRs retroativos** para Stories 126 (LangGraph), 131 (MoA), 135 (Adaptive Routing), 136 (EventBus)
- [ ] **Refatoração**: `src/dashboard/server.py` (4.971 linhas → quebrar em routers)

## Gates Humanos Pendentes

- H1 — VisionCritic threshold dinâmico (em design)
- H2 — Auto-monitorado ✅
- H3, H5, H6 — Aguardando ação do operador
- H4 — ✅ Entregue
