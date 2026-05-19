---
title: Home — Mekka Trading Second Brain
type: dashboard
tags: [dashboard, home, mekka-trading]
project: mekka-trading
created: 2026-05-07
updated: 2026-05-16
---

# 🧠 Mekka Trading — Segundo Cérebro

> **Projeto:** `mekka-trading`
> **Repositório:** https://github.com/labsmekka/mekka-trading
> **Cópia espelhada no vault Obsidian:** `~/Documents/Obsidian Vault/mekka-trading/`

Sistema de Trading Autônomo orquestrado por IA, baseado em AIOX Core + Hyperliquid (multi-exchange).
Este é o vault de conhecimento do projeto: arquitetura, decisões, agentes, runbooks e aprendizados.

---

## 🚀 Estado Atual — 2026-05-16

| Item | Status |
|---|---|
| **Última story entregue** | `136 — MekkaEventBus: pub/sub in-process` |
| **Milestone atual** | `21 — Memory Intelligence + Adaptive Routing + Observability` |
| **Mudanças do dia** | `Sem novas stories (apenas refresh de dashboard snapshot)` |
| **Modo padrão** | `PAPER_TRADING=True` |
| **Exchanges suportadas** | Hyperliquid (primary), Bybit, Binance (via CCXT) |
| **Dashboard** | `http://localhost:8787` com WebSocket em tempo real |
| **Agentes ativos** | NickFury, Batman, Wolverine, IronMan, Vision (+ VisionCritic), Deadpool, ProfessorX, Superman, DoctorStrange, BlackPanther, Thor, Aquaman, Spider-Man, Flash, PortfolioManager |

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

- Repositório: https://github.com/labsmekka/mekka-trading
- Stories entregues: 001–136
- Squads baseline: `alpha-risk-command`, `hyperliquid-mock-ops`, `market-intel-lab`
- Projeto ativo: [[10 - Projects/Projeto - Mekka Trading|Projeto — Mekka Trading]]
