# 🦸 HANDOFF MASTER — Mekka Trading
**Data:** 2026-05-18 (sessão final do dia)
**Para:** Próxima sessão / próxima IA
**Projeto:** `/Users/gustavovicente/Documents/Mekka-Trading`
**Última story entregue:** **243** — DebateModerator → integração Vision pipeline (Milestone 39 completo)

> **Leia este arquivo inteiro antes de escrever qualquer código.**
> Tempo estimado: 8 minutos. Vale cada segundo.

---

## 0. Bloco de início de sessão (cole no próximo chat)

```
@dev Projeto: Mekka Trading — sistema de trading multi-agente autônomo.
Leia OBRIGATORIAMENTE nesta ordem antes de qualquer ação:
1. docs/MEKKA-DEV.md              (regras absolutas, naming, pacing)
2. AGENTS.md                       (roster de 17 heróis + squads)
3. docs/ARCHITECTURE.md            (pipeline I/O por agente)
4. docs/stories/INDEX.md           (última story entregue: 243)
5. docs/HANDOFF_MASTER_2026-05-18i.md  ← este arquivo

Contexto: Milestones 36–39 entregues. Dashboard auditado (18 bugs corrigidos).
Widget "Resultado do Dia" corrigido. Próxima ação: Milestone 40 (Live Trading Gate).
paper_trading=True · nunca burlar Batman · uma feature por story · respostas em pt-BR
```

---

## 1. Identidade do projeto

**Mekka Trading** é uma empresa digital autônoma de trading multi-agente baseada no **AIOX Core**, focada em **Hyperliquid**, com arquitetura:

- **Paper-trading-first** — `paper_trading=True` é o default, IronMan nunca toca a SDK com essa flag
- **CLI-first / Risk-first / Observability-first**
- **Pedagógico e progressivo** — uma feature → uma story → uma aula gravada

**Stack:**
- Python 3.11+ · aiohttp · SQLite (aiosqlite) · Pydantic v2 · loguru
- Dashboard: porta `8787` (aiohttp + WebSocket + SSE + Chart.js)
- Notificações: Telegram (push + inbound long-polling)
- Exchange: Hyperliquid (mainnet + testnet) via `hyperliquid-python-sdk`
- Diretório: `/Users/gustavovicente/Documents/Mekka-Trading`

---

## 2. Roster de Heróis (17 ativos)

| Herói | Layer | Arquivo | Responsabilidade |
|---|---|---|---|
| **Superman** | L1 | `src/agents/superman.py` | OHLCV + indicadores técnicos (RSI, EMA, BB, MACD, ATR) |
| **Doctor Strange** | L1 | `src/agents/doctor_strange.py` | Sentimento macro (CryptoPanic + Fear&Greed + BTC dominance) |
| **Black Panther** | L1 | `src/agents/black_panther.py` | Onchain: funding rate, OI, whale flow |
| **Thor** | L1 | `src/agents/thor.py` | Volatilidade + regime ATR% → size multiplier |
| **Aquaman** | L1 | `src/agents/aquaman.py` | Liquidez L2 + slippage estimado |
| **Spider-Man** | L1 | `src/agents/spider_man.py` | Detecção de anomalias (flash crash, volume spike) |
| **Flash** | L1.5 | `src/agents/flash.py` | Micro-momentum scalper (advisory, sem downstream) |
| **Vision** | L2 | `src/agents/vision.py` | LLM GPT-4o → TradingSignal |
| **Vision Critic** | L2 | `src/agents/vision_critic.py` | Second-look LLM (ENDORSE/AMEND/REJECT) — toggle off |
| **Vision MoA** | L2 | `src/agents/vision_moa.py` | Mixture-of-Agents (Story 131) |
| **Professor X** | L2 | `src/agents/professor_x.py` | Swarm Coordinator — asyncio.gather L1 + debate gate |
| **Batman** | L3 | `src/agents/batman.py` | Risk Guardian determinístico — APPROVED/REDUCED/REJECTED |
| **Iron Man** | L3 | `src/agents/iron_man.py` | Executor Hyperliquid (paper + live) |
| **Wolverine** | L3 | `src/agents/wolverine.py` | Recovery Agent read-only (monitor 5min) |
| **Nick Fury** | L4 | `src/agents/nick_fury.py` | Mission Commander — orquestrador principal |
| **Deadpool** | Analytics | `src/agents/deadpool.py` | Performance Analytics (Sharpe, win rate, drawdown) |
| **Cyclops** | L4 | `src/agents/cyclops.py` | Kill-switch enforcement |

**Squads:**
- `alpha-risk-command` → Batman + NickFury + Wolverine
- `hyperliquid-mock-ops` → IronMan + ProfessorX + SpiderMan
- `market-intel-lab` → Superman + DoctorStrange + BlackPanther + Thor + Aquaman + Flash + Vision + Deadpool

---

## 3. Pipeline principal (NickFury.run_main_cycle)

```
NickFury.run_main_cycle()
  ├── PortfolioManager.snapshot()           → EquitySnapshot
  ├── ProfessorX.analyze()                  → MarketAnalysis (L1 paralelo)
  │     ├── [se settings.debate_enabled]
  │     │   DebateModerator.run_debate()    → DebateVerdict (Stories 239-243)
  │     │   └── persiste em audit_log via DebateVerdictLogger
  │     Superman / DoctorStrange / BlackPanther / Thor / Aquaman / SpiderMan
  ├── Vision.analyze()                      → TradingSignal
  │     + ArchitectEditor, AutoLinter, ReasoningBudget, PromptCache
  │     + MarketAnalysis.debate_verdict (se disponível)
  ├── Batman.validate()                     → RiskReport (APPROVED/REDUCED/REJECTED)
  │     + MarketRegime + AssetClassifier
  ├── IronMan.execute()                     → ExecutionResult (paper)
  └── SQLite audit_log + signals + trades + Telegram alerts
```

---

## 4. Milestones entregues até hoje

| Milestone | Stories | Entregue | Descrição |
|---|---|---|---|
| 1–35 | 001–223 | ✅ | Foundation → LangGraph → Backtesting Engine |
| **36** | **224–228** | ✅ | Backtesting Dashboard (API + Panel + Benchmark + Telegram + Scheduler) |
| **37** | **229–233** | ✅ | Live Performance Tracking (RollingMetrics + DivergenceAlerter + endpoints) |
| **38** | **234–238** | ✅ | Risk Dashboard Avançado (batman-timeline + regime-heatmap + concentration) |
| **39** | **239–243** | ✅ | Multiagent Debate (DebateModerator + Debate Round + Consensus + Logger + ProfessorX) |

**Última story: 243** — integração ProfessorX + `settings.debate_enabled` + `POST /api/debate/run` + `GET /api/debate/history`

---

## 5. Dashboard — estado atual

**URL:** `http://localhost:8787`
**Arquivo servidor:** `src/dashboard/server.py`
**Frontend:** `src/dashboard/static/` (index.html + app.js + style.css)

### Páginas implementadas (nav com ícones)
| Ícone | Página | Seções principais |
|---|---|---|
| 🏠 | Overview | Resultado do Dia + Office 3D + Live Market + Métricas |
| 💼 | Wallet | Posições + equity |
| ⚡ | Performance | Rolling metrics + divergência vs backtest |
| 🤖 | Agents | Status dos agentes |
| 📋 | Trades | Histórico de trades |
| 🧠 | Memory | Audit log + memória dos agentes |
| 🛡️ | Risk | Batman timeline + Regime Heatmap + Concentration |
| 📜 | Logs | Logs em tempo real |
| ⚙️ | Settings | Configurações |
| 🏆 | Leaderboard | Ranking de performance |
| 📑 | Relatórios | P&L Diário + Por Símbolo + Histórico Backtests |
| 📊 | Backtest | Backtesting interativo |
| 🔬 | Analytics | Analytics avançado |
| 📡 | Live | Feed ao vivo |

### Endpoints API implementados
```
GET  /api/today-summary           Widget "Resultado do Dia"
GET  /api/leaderboard?days=N
GET  /api/performance/rolling
GET  /api/performance/divergence
GET  /api/risk/batman-timeline
GET  /api/risk/regime-heatmap
GET  /api/risk/concentration
POST /api/backtest/run
GET  /api/backtest/result
GET  /api/backtest/history
GET  /api/debate/history
POST /api/debate/run
GET  /api/cost
GET  /api/benchmarks
```

---

## 6. Bugs corrigidos nesta sessão (18 total)

### Backend (9 bugs)
| ID | Arquivo | Bug | Fix |
|---|---|---|---|
| BUG-001 | server.py, debate_verdict_logger.py | `list_audit_logs()` não existe | → `list_recent_audit()` |
| BUG-002 | models/backtest.py | `initial_equity`/`final_equity` mas callers usavam `_usd` | Renomeados para `*_usd` |
| BUG-003 | backtest_telegram_report.py | `TelegramAlerter.send()` não existe | → `.alert(event=..., message=...)` |
| BUG-004 | backtest_benchmark.py | `MekkaRepository.list_signals()` não existe | → `list_recent_signals()` |
| BUG-005 | server.py `_on_shutdown` | `_backtest_scheduler_task` nunca cancelado | Adicionado cancel() |
| BUG-006 | server.py `_handle_batman_timeline` | `?symbol=` não filtrava rows | Filtro adicionado |
| BUG-007 | server.py `_handle_concentration` | `list_paper_filled_trades` zerava em mainnet | → `list_recent_trades` + filter |
| BUG-008 | `_handle_debate_run` | Ignorava `settings.debate_enabled` | Documentado (intencional on-demand) |
| BUG-009 | `_handle_perf_divergence` | `?days=` não repassado | Observado — sem impacto crítico |

### Frontend (9 bugs)
| ID | Bug | Fix |
|---|---|---|
| C1 | `bootMemory()` — `setInterval` sem variável (memory leak) | Criado `_memoryTimer` |
| C2 | `_btBootPage` — símbolo hardcoded `'BTC'` | → `getElementById('bt-symbol')?.value \|\| 'BTC'` |
| H1 | 5 timers ausentes do `visibilitychange` hidden branch | Todos adicionados |
| H2 | `_bootNewPages` disparava fetches duplicados | Flags `_btPageBooted` + `_analyticsPageBooted` |
| M1 | Leaderboard: `.contains('hidden')` em vez de `page-section-hidden` | Corrigido |
| TS | `loadTodaySummary()` — `null` pnl_usd → `$0.00`, today vazio → lista vazia | Reescrita completa |

### Resultado do Dia — fix específico
**Problema:** Credenciais Hyperliquid são placeholder → `self._hl_prices` vazio → widget exibia `$0.00` nos P&Ls e lista vazia quando não há trades hoje.

**Solução implementada:**
- Banner amarelo `⚠️ Sem cotação de mercado` quando `has_prices = false`
- Posições mostram "Aguardando cotação" ao invés de `$0.00`
- Quando `today_trades` vazio → exibe `recent_trades` (últimos 20 de qualquer data) com data visível
- "Resultado Líquido" sem cotação → mostra só realizado
- `ts-trades-header` dinâmico: "Trades de Hoje" vs "Últimos trades (sem trades hoje)"

---

## 7. Estado do .env (variáveis críticas)

| Variável | Valor atual | Status |
|---|---|---|
| `HYPERLIQUID_PRIVATE_KEY` | `0x111...1` (placeholder) | 🔴 Precisa trocar para mainnet |
| `HYPERLIQUID_WALLET_ADDRESS` | `0x111...1` (placeholder) | 🔴 Precisa trocar para mainnet |
| `HYPERLIQUID_NETWORK` | `testnet` | ✅ Correto por enquanto |
| `PAPER_TRADING` | `true` | ✅ Correto |
| `LIVE_TRADING_CONFIRMED` | **ausente** | 🔴 Necessário para ativar live |
| `MAX_POSITION_SIZE_PCT` | `0.02` (2%) | ⚠️ Reduzir para `0.001` na semana 1 mainnet |
| `MAX_DAILY_DRAWDOWN_PCT` | `0.10` (10%) | ⚠️ Reduzir para `0.05` na semana 1 mainnet |
| `TRADING_ASSETS` | `BTC,ETH,SOL` | ✅ |
| `PAPER_EQUITY_USD` | `10000.0` | ✅ |
| `TELEGRAM_CHAT_ID` | configurado | ✅ |

---

## 8. Checklist Mainnet (Gates H1–H6)

Todos os 6 gates em `docs/MAINNET-AUTHORIZATION.md` estão **abertos**.

### 🔴 Bloqueadores críticos
1. **API keys reais** — `HYPERLIQUID_PRIVATE_KEY` e `HYPERLIQUID_WALLET_ADDRESS` no `.env`
2. **Wallet mainnet dedicada e funded** — separada de wallet pessoal
3. **`LIVE_TRADING_CONFIRMED=true`** no `.env` — ausente atualmente
4. **Assinar `docs/MAINNET-AUTHORIZATION.md`** — todos os `[ ]` → `[x]` + string `GO MAINNET`
5. **Preflight verde** — `python3 scripts/preflight_mainnet.py` deve retornar `🟢 ALL AUTOMATED CHECKS PASSED`

### ⚠️ Importantes
6. Parâmetros conservadores semana 1: `MAX_POSITION_SIZE_PCT=0.001`, `MAX_LEVERAGE=2`, `MAX_DAILY_DRAWDOWN_PCT=0.05`
7. `HYPERLIQUID_NETWORK=mainnet` (só mudar quando H1–H6 completos)
8. Telegram testado end-to-end com bot real
9. Histórico testnet mínimo de 1 mês sem incidente (Gate H1)
10. Wolverine ENDORSE rate ≥ 70% nos últimos 30 dias (Gate H2)

---

## 9. Próximos milestones sugeridos

### Milestone 40 — Live Trading Gate (Próxima ação recomendada)
Automatizar o fluxo de verificação H1–H6 + preflight interativo + validação de conectividade testnet end-to-end + primeira ordem paper com dados reais.
Stories sugeridas: `244-248`

### Milestone 41 — Debate Enhancement
Substituir heurísticas do `_agent_vote()` por chamadas reais aos agentes L1.
Expor `debate_verdict` no prompt do Vision de forma estruturada.
Stories sugeridas: `249-253`

### Milestone 42 — Mainnet Soft Launch
Primeiro trade real com capital mínimo, monitoramento intensivo semana 1.
**Só iniciar após Milestone 40 completo e H1–H6 satisfeitos.**

---

## 10. Comandos essenciais

```bash
# Setup
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate

# Verificação de saúde
pytest -q                                          # ~500+ testes
python3 scripts/check_roster_consistency.py       # [OK] 17 heroes

# Rodar pipeline (paper mode)
python3 -m src.agents.nick_fury

# Rodar dashboard
python3 -m src.dashboard.server
# Acesse: http://localhost:8787

# Preflight mainnet
python3 scripts/preflight_mainnet.py

# Kill switch
./scripts/kill.sh "motivo"
rm data/.kill_switch  # para retomar

# Backtest via CLI
python -m src.backtest run --symbol BTC --days 30

# Commit padrão
git commit -m "feat(story-NNN): título curto"
```

---

## 11. Arquivos críticos — não tocar sem leitura prévia

| Arquivo | Por quê |
|---|---|
| `src/agents/nick_fury.py` | Orquestrador — bug aqui quebra o pipeline inteiro |
| `src/agents/batman.py` | Risk gate — nunca bypassar |
| `src/config/settings.py` | Todas as flags de comportamento |
| `src/models/signal.py` | Geometria SL/TP — não alterar sem aprovação |
| `src/dashboard/server.py` | ~2000 linhas — ler antes de adicionar endpoints |
| `src/dashboard/static/app.js` | ~5500 linhas — ler seção antes de editar |
| `conftest.py` | Injeção de stubs de test — siga sempre este padrão |
| `docs/MEKKA-DEV.md` | Regras absolutas — leia PRIMEIRO |
| `docs/MAINNET-AUTHORIZATION.md` | Gates H1–H6 — não editar até verificação real |

---

## 12. Regras absolutas (não negociáveis)

1. **`paper_trading=True`** — IronMan não toca a SDK enquanto esta flag estiver on
2. **Nunca burlar Batman** — toda execução passa pelo gate de risco
3. **Somente super-heróis** — zero referências a "rat/RatarIA/rodent/squad dos ratos"
4. **Uma feature → uma story** — sem acelerar, sem juntar 3 em 1
5. **Nunca modificar** `batman.py`, `kill_switch`, geometria SL/TP sem aprovação do operador
6. **Nunca usar API keys reais em código** — conftest.py injeta stubs
7. **Sempre validar sintaxe** antes de fechar uma story
8. **Testes primeiro** — não fechar story sem pytest verde
9. **Respostas sempre em português pt-BR**

---

## 13. Histórico de handoffs (referência)

| Arquivo | Cobertura |
|---|---|
| `docs/HANDOFF_MASTER_2026-05-18.md` | Estado até Story 223 (Milestone 35) |
| `docs/HANDOFF_2026-05-18b.md` | Overview simplificado + fix memória |
| `docs/HANDOFF_2026-05-18c.md` | Widget "Resultado do Dia" v1 |
| `docs/HANDOFF_2026-05-18d.md` | Milestones 36-39 (Stories 224-243) |
| `docs/HANDOFF_2026-05-18e.md` | Auditoria completa — 18 bugs identificados |
| `docs/HANDOFF_2026-05-18f.md` | Diagnóstico "Resultado do Dia" + mainnet bloqueadores |
| `docs/HANDOFF_2026-05-18g.md` | 18 bugs corrigidos + ícones + página Relatórios |
| `docs/HANDOFF_2026-05-18h.md` | Widget "Resultado do Dia" corrigido + checklist mainnet |
| **`docs/HANDOFF_MASTER_2026-05-18i.md`** | **Este arquivo — estado completo final do dia** |

---

*Gerado em 2026-05-18 · Milestones 36–39 completos · Story 243 é a última entregue · 18 bugs corrigidos · Dashboard auditado e funcional*
