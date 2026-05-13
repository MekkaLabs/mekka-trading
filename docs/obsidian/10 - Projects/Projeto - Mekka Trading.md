---
title: "Projeto — Mekka Trading"
type: project
status: ativo
due: 2026-12-31
owner: Gustavo
sprint_focus: "Story 047 (Testes pytest Cyclops/Wolverine/equity)"
tags: [project, mekka-trading]
created: 2026-05-07
updated: 2026-05-13
---

# Projeto — Mekka Trading

## Missão

Construir um sistema autônomo de trading paper-first, modular, observável e com governança de risco rígida. Multi-exchange (Hyperliquid, Bybit, Binance).

## Estado Atual — 2026-05-13

- **Última story entregue:** `046 — Equity Dinâmica, Wolverine Execution, Cyclops & Bybit`
- **Milestone:** `17 — Bug Fixes Críticos + Multi-Exchange`
- **Modo padrão:** `PAPER_TRADING=True`
- **Dashboard:** `http://localhost:8787` (WebSocket tempo real em todas as páginas)
- **Gate absoluto:** Batman + Kill Switch
- **Exchanges:** Hyperliquid (primary), Bybit, Binance via CCXT

## Milestones Entregues

| # | Milestone | Stories |
|---|---|---|
| 1 | Foundation | 001 |
| 2 | Megazord Runtime | 002 |
| 3 | Stress + Observability | 003–009 |
| 4 | Alerting + DLQ | 010–017 |
| 5 | Ops Governance | 018–024 |
| 6 | Strategic Pipeline (Python) | 025 |
| 7 | Portfolio | 026 |
| 8 | Daily PnL + Hardening + Safety | 027–029 |
| 9 | Recovery + LLM Hardening | 030–032b |
| 10 | Tactical + Simulation | 033–035b |
| 11 | Mainnet Readiness | 036–037 |
| 12 | Dashboard + Analytics | 038–039 |
| 13 | Operator UX | 040 |
| 14 | Live Execution Pipeline | 041–043 |
| 15 | Operator Control | 044 |
| 16 | Exchange-Grade Monitoring | 045 |
| 17 | Bug Fixes Críticos + Multi-Exchange | **046** ✅ |

## Roadmap Próximo

- [ ] Story 047 — Testes pytest: equity dinâmica, Cyclops, Wolverine execution
- [ ] Story 048 — Fix [H1]: VisionCritic threshold dinâmico (via runtime_settings)
- [ ] Story 049 — Dashboard: widget de equity acumulada ao longo do tempo
- [ ] Gates humanos pendentes: H1, H3, H5, H6 (ação do operador)

## Links

- [[../50 - MOCs/MOC - Arquitetura|MOC Arquitetura]]
- [[../50 - MOCs/MOC - Agentes IA|MOC Agentes IA]]
- [[../50 - MOCs/MOC - Trading & Estratégia|MOC Trading & Estratégia]]
- [[../50 - MOCs/MOC - Risco & Compliance|MOC Risco & Compliance]]
- [[../30 - Resources/Runbooks/_Runbooks Index|Runbooks]]
- [[../30 - Resources/Referencias Externas/Stories do Projeto|Stories do Projeto]]
