---
title: Home — Mekka Trading Second Brain
type: dashboard
tags: [dashboard, home, mekka-trading]
project: mekka-trading
created: 2026-05-07
updated: 2026-05-19
---

# 🧠 Mekka Trading — Segundo Cérebro

> **Projeto:** `mekka-trading`
> **Repositório:** https://github.com/MekkaLabs/mekka-trading

Sistema de Trading Autônomo orquestrado por IA, baseado em AIOX Core + multi-exchange (Hyperliquid / Bybit / Binance via CCXT).
Este é o vault de conhecimento do projeto: arquitetura, decisões, agentes, runbooks e aprendizados.

---

## 🚀 Estado Atual — 2026-05-19

| Item | Status |
|---|---|
| **Última story entregue** | `251 — Cycle Checkpoint` (codex / milestone 40) |
| **Milestone atual** | `40 — Agent Communication Upgrade (244–251)` + `22 — Bybit Testnet Readiness` (integrado nesta sessão) |
| **Mudanças do dia** | M40 (Flash→Vision, DebateVerdict, Batman gate 3r, Beast, DecisionMemory, Vision structured output, CycleCheckpoint) + M22 (Bybit testnet: sandbox routing, MarketRegistry, env badge, clock skew, stress_inject) + **painel de trading manual com parecer do Batman (P1.1)** + **Jean Grey (P2.1) — health scan do vault** |
| **Modo padrão** | `PAPER_TRADING=True` |
| **Exchange recomendada para validação** | **Bybit testnet** (via CCXT, `set_sandbox_mode(True)`) |
| **Exchanges suportadas** | Hyperliquid (testnet/mainnet), Bybit (testnet/mainnet), Binance (placeholder) |
| **Dashboard** | `http://localhost:8787` com WebSocket em tempo real + env badge multi-exchange |
| **Agentes ativos (20)** | Nick Fury, Professor X, Superman, Vision (+ VisionCritic), Doctor Strange, Aquaman, Black Panther, Thor, Flash, Batman, Iron Man, Cyclops, Spider-Man, Portfolio Manager, Wolverine, Deadpool, Beast, **Jean Grey**, **Mekka** 👑, **Galactus** 🪐 |
| **Improvement Council** | **Mekka** (líder/consolida) + **Beast** (propõe) + **Jean Grey** (memória) + **Galactus** (premortem) → operador aprova em `/Melhorias` |

### Marcos recentes

- **Stories 126–140**: LangGraph durability, MoA Vision, Adaptive Routing, EventBus, Memory Consolidation, Degraded Mode.
- **Stories 244–251 (codex M40)**: Agent Communication Upgrade — Beast joins the roster, Vision gains structured output, Flash→Vision direct link, Batman gate 3r.
- **Sessão 2026-05-19**: prontidão para Bybit testnet — sandbox routing, exchange-agnostic price feed, env badge, clock skew check, painel Trading Mode no Overview. Veja [[2026-05-19]] e [[ADR-003 - Bybit Testnet Readiness]].

---

## 🚀 Navegação Rápida

### Mapas de Conteúdo (MOCs) — comece aqui
- [[MOC - Arquitetura|🏗️ MOC Arquitetura]]
- [[MOC - Agentes IA|🦸 MOC Agentes IA]]
- [[MOC - Trading & Estratégia|📈 MOC Trading & Estratégia]]
- [[MOC - Risco & Compliance|🛡️ MOC Risco & Compliance]]
- [[MOC - Operações & Observability|🔭 MOC Operações]]
- [[MOC - Aprendizados|📚 MOC Aprendizados]]

### 🗂️ Notas-chave por área
> Atalhos diretos para notas operacionais e de área (mantém o grafo conectado).
- **Projetos:** [[Departamento de Melhoria Contínua]]
- **Arquitetura:** [[Nick Fury Runtime Cycles]]
- **Operacional:** [[Kill Switch - Operação]] · [[Paper Trading vs Live]] · [[Review Semanal]]
- **Risco:** [[Batman - Risk Guardian]]
- **Trading:** [[Backtesting]]
- **Recursos:** [[Glossário]] · [[Runbook - Iniciar dashboard web]] · [[Runbook - Iniciar runtime do Megazord]]

### Estrutura PARA
| Pasta | Propósito |
|---|---|
| [[00 - Inbox]] | Captura rápida — onde toda nota nova nasce |
| [[10 - Projects]] | Iniciativas com prazo e entregável claro |
| [[20 - Areas]] | Áreas de responsabilidade contínua |
| [[30 - Resources]] | Referências, decisões, runbooks |
| [[40 - Archive]] | Concluído ou desativado |
| [[50 - MOCs]] | Mapas de Conteúdo (índices vivos) |
| [[60 - Daily]] | Notas diárias / log de trabalho |
| [[70 - Templates]] | Templates reutilizáveis |

---

## 🎯 Sprint Atual

```dataview
TABLE without ID
  file.link AS "Projeto",
  status AS "Status",
  due AS "Prazo"
FROM "10 - Projects"
WHERE status != "done" AND status != "archived"
SORT due ASC
```

---

## 🆕 Últimas notas modificadas

```dataview
LIST
FROM ""
WHERE !contains(file.path, "70 - Templates") AND !contains(file.path, ".obsidian")
SORT file.mtime DESC
LIMIT 10
```

---

## 🏷️ Tags principais

- `#arquitetura` — decisões e diagramas de arquitetura
- `#agente` — qualquer agente IA do sistema
- `#squad` — composições de squads
- `#estrategia` — estratégias de trading
- `#risco` — controles de risco e compliance
- `#runbook` — procedimentos operacionais
- `#decisao` — Architecture Decision Records (ADRs)
- `#aprendizado` — lições aprendidas
- `#bug` — bugs encontrados e soluções
- `#externa` — referências externas (papers, links, artigos)

---

## 🔗 Recursos do Projeto

- Repositório: https://github.com/MekkaLabs/mekka-trading
- Stories entregues: 001–251 (com lacunas; ver [[Stories do Projeto]])
- Squads baseline: `alpha-risk-command`, `hyperliquid-mock-ops`, `market-intel-lab`
- Projeto ativo: [[Projeto - Mekka Trading]]
- Runbook para subir Bybit testnet: [[Runbook - Bybit Testnet Setup]]
