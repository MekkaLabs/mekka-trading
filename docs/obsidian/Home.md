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
| **Mudanças do dia** | M40 entregue pelo codex (Flash→Vision, DebateVerdict, Batman gate 3r, **Beast**, DecisionMemory, Vision structured output, CycleCheckpoint) + M22 Bybit Testnet (sandbox routing, MarketRegistry, env badge, clock skew, stress_inject) |
| **Modo padrão** | `PAPER_TRADING=True` |
| **Exchange recomendada para validação** | **Bybit testnet** (via CCXT, `set_sandbox_mode(True)`) |
| **Exchanges suportadas** | Hyperliquid (testnet/mainnet), Bybit (testnet/mainnet), Binance (placeholder) |
| **Dashboard** | `http://localhost:8787` com WebSocket em tempo real + env badge multi-exchange |
| **Agentes ativos (16)** | Nick Fury, Superman, Vision (+ VisionCritic), Batman, Iron Man, Cyclops, Wolverine, Doctor Strange, Professor X, Flash, Aquaman, Spider-Man, Black Panther, Thor, Deadpool, Portfolio Manager |

### Marcos recentes

- **Stories 126–140**: LangGraph durability, MoA Vision, Adaptive Routing, EventBus, Memory Consolidation, Degraded Mode.
- **Stories 244–251 (codex M40)**: Agent Communication Upgrade — Beast joins the roster, Vision gains structured output, Flash→Vision direct link, Batman gate 3r.
- **Sessão 2026-05-19**: prontidão para Bybit testnet — sandbox routing, exchange-agnostic price feed, env badge, clock skew check, painel Trading Mode no Overview. Veja [[2026-05-19]] e [[ADR-003 - Bybit Testnet Readiness]].

---

## 🚀 Navegação Rápida

### Mapas de Conteúdo (MOCs) — comece aqui
- [[50 - MOCs/MOC - Arquitetura|🏗️ MOC Arquitetura]]
- [[50 - MOCs/MOC - Agentes IA|🦸 MOC Agentes IA]]
- [[50 - MOCs/MOC - Trading & Estratégia|📈 MOC Trading & Estratégia]]
- [[50 - MOCs/MOC - Risco & Compliance|🛡️ MOC Risco & Compliance]]
- [[50 - MOCs/MOC - Operações & Observability|🔭 MOC Operações]]
- [[50 - MOCs/MOC - Aprendizados|📚 MOC Aprendizados]]

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

<<<<<<< HEAD
- Repositório: https://github.com/labsmekka/mekka-trading
- Stories entregues: 001–251
=======
- Repositório: https://github.com/MekkaLabs/mekka-trading
- Stories entregues: 001–140 (61 stories totais — veja [[Stories do Projeto]])
>>>>>>> origin/claude/quirky-ritchie-5352c4
- Squads baseline: `alpha-risk-command`, `hyperliquid-mock-ops`, `market-intel-lab`
- Projeto ativo: [[Projeto - Mekka Trading]]
- Runbook para subir Bybit testnet: [[Runbook - Bybit Testnet Setup]]
