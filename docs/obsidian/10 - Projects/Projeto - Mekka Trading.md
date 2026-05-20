---
title: "Projeto — Mekka Trading"
type: project
status: ativo
due: 2026-12-31
owner: Gustavo
sprint_focus: "Milestone 40 (Stories 244–251): Flash/Debate→Vision, Batman gate 3r, Beast, DecisionMemory, Vision structured output, CycleCheckpoint"
tags: [project, mekka-trading]
created: 2026-05-07
updated: 2026-05-19
---

# Projeto — Mekka Trading

## Missão

Construir um sistema autônomo de trading paper-first, modular, observável e com governança de risco rígida. Multi-exchange (Hyperliquid, Bybit, Binance).

## Estado Atual — 2026-05-19

- **Última story entregue:** `Story 251 — Cycle Checkpoint`
- **Stories entregues:** `001–251` (com lacunas; ver `docs/stories/INDEX.md` e [[Stories do Projeto]])
- **Milestone:** `40 — Agent Communication Upgrade (Stories 244–251)`
- **Mudanças do dia:** M40 (Flash→Vision, DebateVerdict→Vision, Batman gate 3r, Beast, DecisionMemory, Vision structured output, CycleCheckpoint) + M22 (Bybit testnet readiness + Force Execute) + P1.1 (painel de trading manual com parecer do Batman) + P2.1 (Jean Grey vault health)
- **Modo padrão:** `PAPER_TRADING=True`
- **Dashboard:** `http://localhost:8787` (WebSocket tempo real em todas as páginas)
- **Gate absoluto:** Batman (gates 3a–3q) + Kill Switch
- **Exchanges:** Hyperliquid (primary), Bybit, Binance via CCXT
- **Agentes ativos:** NickFury, ProfessorX, Superman, Vision (+ VisionCritic), DoctorStrange, Aquaman, BlackPanther, Thor, Flash, Batman, IronMan, Cyclops, Spider-Man, PortfolioManager, Wolverine, Deadpool, Beast, Jean Grey

## Milestones Entregues

| # | Milestone | Stories |
|---|-----------|---------|
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
| 17 | Bug Fixes Críticos + Multi-Exchange | 046 |
| 18 | Fixes: Telegram, PnL, VisionCritic | 047–050 |
| 19 | Live Trading + Indicadores + Redesign | 057–062 |
| 20 | Memory, Partial TP, Trailing, Auto-pause | 063–068 |
| 21 | Gates avançados + Live Risk | 069–077 |
| 22 | Telegram Rich Commands + Leaderboard + Export | 078–089 |
| 23 | Weekly Report, Dry-run, Heatmap, Scores, gates 3l–3n | 090–100 |
| **24** | **/weekly /equity, gates 3o/3p, partial SL, R-múltiplo** | **101–106 ✅** |
| **25** | **Calendar, /balance, hourly PnL, gate 3q, reset 3o, gates timeline** | **107–112 ✅** |
| **26** | **LLM fallback + Superman Py3.14 + Telegram pt-BR + Pixel Office** | **113–125 ✅** |
| **27** | **LangGraph durable execution + interrupt/resume + memória semântica + subgrafo L1** | **126–129 ✅** |
| **28** | **Decision quality: reflection + mixture-of-agents** | **130–131 ✅** |
| **29** | **Memory intelligence + routing adaptativo + event bus** | **132–136 ✅** |

## Arquitetura de Gates Batman (3a–3p)

| Gate | Nome | Descrição |
|------|------|-----------|
| 3a | Kill switch | Rejeita tudo se kill switch ativo |
| 3b | Paper-only guard | Bloqueia live se paper_only_mode=True |
| 3c | Max open positions | Máximo de posições simultâneas |
| 3d | Correlation guard | Rejeita símbolo correlacionado com posição aberta |
| 3e | Flash circuit breaker | Pausa após spike de volatilidade |
| 3f | Re-entry cooldown | Aguarda N horas antes de re-entrar |
| 3g | ATR position sizing | Ajusta tamanho pelo ATR |
| 3h | Symbol blacklist | Ignora símbolos com strikes consecutivos |
| 3i | Funding rate gate | Rejeita se funding > threshold |
| 3j | Trading hours gate | Opera apenas em horário configurado |
| 3k | Pyramid entry | Permite scale-in em posição lucrativa |
| 3l | Max trades/símbolo/dia | Limite diário por ativo |
| 3m | Min trade notional | Rejeita micro-posições |
| 3n | Max drawdown por símbolo/semana | Limita perda semanal por ativo |
| **3o** | **Max consecutive losses** | **Pausa após N SLs consecutivos** |
| **3p** | **Directional bias guard** | **Rejeita se últimos N trades todos na mesma direção** |
| **3q** | **Min ATR filter** | **Rejeita se ATR% < min_atr_pct (mercado parado)** |

## Comandos Telegram Disponíveis

| Comando | Função |
|---------|--------|
| `/status` | Visão geral do sistema |
| `/pnl [N]` | PnL dos últimos N dias |
| `/pause` / `/resume` | Kill switch |
| `/positions` | Posições abertas |
| `/perf [N]` | Relatório Deadpool N dias |
| `/gates` | Status gates H1–H6 |
| `/mode [X]` | Ver/mudar modo operacional |
| `/report` | Relatório diário agora |
| `/weekly` | Relatório semanal Deadpool agora |
| `/equity` | Equity breakdown (inicial + realizado + não realizado) |
| `/ping` | Teste de conexão |
| `/risk` | Painel de risco ao vivo |
| `/leaderboard [N]` | Top N símbolos por PnL |
| `/stats [N]` | Estatísticas globais N dias |
| `/unblacklist [SYM]` | Remove símbolo da blacklist |
| `/dryrun [on\|off]` | Modo dry-run sem execução |
| `/balance` | Saldo live Hyperliquid (equity, margin, withdrawable) |

## Features do Cyclops (Monitor SL/TP)

- SL/TP automático em posições paper
- Scale-out parcial (50%) ao atingir 1R de lucro
- TP Ladder: 3 saídas graduais (1/3R, 2/3R, TP completo)
- Trailing stop dinâmico pós scale-out
- Alerta Telegram quando posição cruza +2R
- Alerta Telegram quando posição cruza -0.5R (zona de risco)
- **Partial SL (Story 105):** fecha 50% ao cruzar -0.75R

## Features do Wolverine (Recovery Agent)

- TIGHTEN_STOP / TRAIL_STOP quando posição em risco
- SCALE_OUT ao atingir lucro target
- EMERGENCY_CLOSE se drawdown intraday ultrapassa limite
- **SL agressivo em +2R (Story 095):** move SL para +1R lock-in de lucro

## Dashboard — Páginas e Endpoints

| Endpoint | Função |
|----------|--------|
| `/api/overview` | Estado geral do sistema |
| `/api/positions` | Posições com mark price, uPnL, duration, R-múltiplo |
| `/api/trades` | Histórico de trades |
| `/api/signals` | Sinais gerados |
| `/api/leaderboard?days=90` | Ranking de símbolos |
| `/api/trades/export?format=csv` | Export CSV/JSON |
| `/api/signals/export?format=csv` | Export de sinais |
| `/api/pnl/heatmap` | Heatmap PnL hora×dia |
| `/api/session/stats` | Stats da sessão atual |
| `/api/report/daily?force=1` | Dispara relatório diário |
| `/api/report/weekly?force=1` | Dispara relatório semanal |
| `/api/trades/calendar?year=YYYY&month=MM` | Calendar heatmap mensal de trades |
| `/api/pnl/hourly?days=30` | PnL médio por hora UTC (0-23) |
| `/api/gates/timeline?limit=50` | Timeline de gate rejections do Batman |
| `/api/settings` | Configurações de runtime |
| `/ws` | WebSocket tempo real |

## Roadmap Próximo (Stories 113+)

- [x] Stories 113–223 — Milestones 26–35 ✅ (ver `docs/stories/INDEX.md`)
- [x] Stories 244–251 — Milestone 40 ✅ (Agent Communication Upgrade)
- [ ] Milestone 36 — Dashboard de Backtesting (Stories 224–228): endpoint JSON, painel, scheduler, comparison, Telegram report
- [ ] Milestone 37 — Live Performance Tracking (Stories 229–233): performance real vs backtest + alertas de divergência

## Configurações-Chave (.env)

```env
# Modo
PAPER_TRADING=True
DRY_RUN_MODE=False

# Risco
MAX_CONSECUTIVE_LOSSES=3       # gate 3o
MAX_SAME_DIRECTION_STREAK=4    # gate 3p
MIN_ATR_PCT=0.0                # gate 3q (0.0 = desabilitado)
PARTIAL_SL_ENABLED=False       # Cyclops partial SL em -0.75R
MIN_ALERT_NOTIONAL_USD=50.0    # filtro de alertas Telegram

# Weekly report
MEKKA_DAILY_REPORT_HOUR_UTC=23
MEKKA_DAILY_REPORT_MINUTE_UTC=55
```

## Links

- [[MOC - Arquitetura|MOC Arquitetura]]
- [[MOC - Agentes IA|MOC Agentes IA]]
- [[MOC - Trading & Estratégia|MOC Trading & Estratégia]]
- [[MOC - Risco & Compliance|MOC Risco & Compliance]]
- [[_Runbooks Index|Runbooks]]
