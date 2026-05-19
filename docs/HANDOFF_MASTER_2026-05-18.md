# 🦸 HANDOFF MASTER — Mekka Trading
**Data:** 2026-05-18  
**Para:** Próxima sessão / próxima IA  
**Projeto:** `/Users/gustavovicente/Documents/Mekka-Trading`  
**Última story entregue:** **223** — BacktestRunner + CLI (Milestone 35 completo — Backtesting Engine)

> **Leia este arquivo inteiro antes de escrever qualquer código.**  
> Tempo estimado: 8 minutos. Vale cada segundo.

---

## 0. Como iniciar o chat com AIOX Core / squads

Cole este bloco no início do próximo chat para carregar o contexto correto:

```
@dev Projeto: Mekka Trading — sistema de trading multi-agente autônomo.
Leia OBRIGATORIAMENTE nesta ordem antes de qualquer ação:
1. docs/MEKKA-DEV.md          (regras absolutas, naming, pacing)
2. AGENTS.md                   (roster de 15 heróis + squads)
3. docs/ARCHITECTURE.md        (pipeline I/O por agente)
4. docs/stories/INDEX.md       (milestones 1–35, story mais recente: 223)
5. docs/HANDOFF_MASTER_2026-05-18.md  (este arquivo — estado completo)

Contexto: Milestone 35 (Backtesting Engine, Stories 219-223) foi entregue.
Próxima ação: continuar a partir do Milestone 36 conforme sugerido em § 8.
paper_trading=True  ·  nunca burlar Batman  ·  uma feature por story
```

---

## 1. Identidade do projeto

**Mekka Trading** é uma empresa digital autônoma de trading multi-agente baseada no **AIOX Core**, focada em **Hyperliquid**, com arquitetura:

- **Paper-trading-first** — `paper_trading=True` é o default, IronMan não toca a SDK
- **CLI-first / Risk-first / Observability-first**
- **Pedagógico e progressivo** — uma feature → uma story → uma aula

**Stack:**
- Python 3.11+ · aiohttp · SQLite (aiosqlite) · Pydantic v2 · loguru
- Dashboard: porta `8787` (aiohttp + WebSocket + SSE)
- Notificações: Telegram (push + inbound long-polling)
- Exchange: Hyperliquid (mainnet + testnet) via `hyperliquid-python-sdk`

---

## 2. Squads (squads/squads.ts)

```typescript
SQUADS = [
  {
    name: 'alpha-risk-command',
    mandate: 'Garantir controles paper-only e validações pré-trade',
    members: ['Batman', 'NickFury', 'Wolverine'],
  },
  {
    name: 'hyperliquid-mock-ops',
    mandate: 'Connectivity mock e execution rehearsal segura',
    members: ['IronMan', 'ProfessorX', 'SpiderMan'],
  },
  {
    name: 'market-intel-lab',
    mandate: 'Contexto de mercado e sinais de anomalia para R&D',
    members: ['Superman', 'DoctorStrange', 'Vision', 'Thor', 'Aquaman', 'Flash', 'BlackPanther', 'Deadpool'],
  },
]
```

### Usando squads no AIOX Core

```bash
# Delegar análise de risco
@alpha-risk-command revisar os limites de drawdown para o próximo ciclo

# Executar análise de mercado
@market-intel-lab analisar BTC/ETH/SOL com regime atual

# Operações de exchange
@hyperliquid-mock-ops rodar paper-trade do sinal atual
```

---

## 3. Roster de Heróis (15 ativos)

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
| **Professor X** | L2 | `src/agents/professor_x.py` | Swarm Coordinator — asyncio.gather L1 |
| **Batman** | L3 | `src/agents/batman.py` | Risk Guardian determinístico — APPROVED/REDUCED/REJECTED |
| **Iron Man** | L3 | `src/agents/iron_man.py` | Executor Hyperliquid (paper + live) |
| **Wolverine** | L3 | `src/agents/wolverine.py` | Recovery Agent read-only (monitor 5min) |
| **Nick Fury** | L4 | `src/agents/nick_fury.py` | Mission Commander — orquestrador principal |
| **Deadpool** | Analytics | `src/agents/deadpool.py` | Performance Analytics (Sharpe, win rate, drawdown) |
| **Cyclops** | L4 | `src/agents/cyclops.py` | Kill-switch enforcement |

---

## 4. Pipeline principal (run_main_cycle)

```
NickFury.run_main_cycle()
  │
  ├── PortfolioManager.snapshot()          → EquitySnapshot
  │
  ├── [Stories 208-212 — LangGraph block]
  │     _state_graph208  = build_default_mekka_graph()
  │     _router209       = build_vision_router(fallback="batman")
  │     _checkpointer210 = get_cycle_graph_checkpointer()
  │     _parallel211     = get_cycle_parallel_branch()
  │     _interrupt212    = get_cycle_graph_interrupt()
  │     _interrupt212.auto_expire_pending()
  │
  ├── ProfessorX.analyze()                 → MarketAnalysis (L1 paralelo)
  │     Superman / DoctorStrange / BlackPanther
  │     Thor / Aquaman / SpiderMan
  │
  ├── Vision.analyze()                     → TradingSignal
  │     + backstory adaptativo (Story 207)
  │     + AnalysisPromptCache (Story 182)
  │     + DynamicReasoningBudget (Story 181)
  │     + ArchitectEditorVision (Story 178)
  │
  ├── [checkpoint Vision — Story 210]
  │     _checkpointer210.save(cycle_id, "vision", state)
  │
  ├── [router log — Story 209]
  │     _router209.route(state) → destination logado
  │
  ├── Batman.validate()                    → RiskReport (APPROVED/REDUCED/REJECTED)
  │     + MarketRegime integration (Story 148)
  │     + AssetClassifier integration (Story 149)
  │
  ├── IronMan.execute()                    → ExecutionResult (paper ou live)
  │     + AutoSignalLinter (Story 179)
  │     + MockRealism: latência + fills parciais + slippage (Story 144)
  │
  └── SQLite audit_log + signals + trades
        + CycleEventLog SSE (Story 172)
        + Telegram alerts (Story 035/176)
```

---

## 5. Serviços (src/services/) — 212 stories

### Serviços Core (Stories 025–046)
| Serviço | Story | Arquivo |
|---|---|---|
| DailyPnLWriter | 027 | `daily_pnl_writer.py` |
| ConsecutiveBreaker | 029 | `breakers.py` |
| UnifiedAuditReader | 032 | audit reader |
| TelegramAlerter | 035 | telegram |
| EventBus | 136 | `event_bus.py` |

### Padrões de AI Frameworks implementados

| Milestone | Framework | Stories | Serviços |
|---|---|---|---|
| 19 | LangGraph | 126-129 | durable execution |
| 23 | SK / MetaGPT / SWE-agent | 147-151 | kernel, chaos, benchmarks |
| 24 | Pipeline Integration | 152-156 | kernel filter, plugins, event log |
| 25 | SWE-agent Patterns | 157-159 | BoundedOutput, SignalValidator, ContextWindowTracker |
| 26 | Observability Live | 160-167 | SSE, microagent, repo map |
| 27 | Aider Patterns | 178-182 | ArchitectEditor, AutoLinter, WatchMode, ReasoningBudget, PromptCache |
| 28 | MetaGPT Patterns | 183-187 | WorkingMemory, TypedMessages, SOP, LongTermMemory, IncrementalSkip |
| 29 | SWE-agent Wave 2 | 188-192 | Trajectory, BudgetGuard, Demonstrations, ObservationFeedback, EnvSnapshot |
| 30 | OpenHands Wave 1 | 193-197 | SubAgentDelegate, RetryMixin, AgentStateMachine, EventSourceTagger, BatchedExporter |
| 31 | OpenHands Wave 2 | 198-202 | ConversationMemory, CondensationEngine, ArtifactStore, ActionRiskAnalyzer, StateResetter |
| 32 | AutoGen / CrewAI | 203-207 | GroupChat, ConversationSession, TaskDefinition, PipelineOrchestrator, AgentBackstory |
| **33** | **LangGraph** | **208-212** | **StateGraph, ConditionalRouter, Checkpointer, ParallelBranch, GraphInterrupt** |

---

## 6. Estado atual do sistema

### ✅ Entregue e funcionando
- Pipeline completo: Vision → Batman → IronMan (paper mode)
- Dashboard live em `localhost:8787` com SSE + WebSocket
- Telegram push + inbound (7 comandos: `/status /pnl /pause /resume /positions /perf /gates`)
- Multi-exchange: Hyperliquid + Bybit adapter
- Kill switch ergonômico (`scripts/kill.sh`)
- 24.774 linhas de testes (`pytest`)
- Milestone 33 — 5 serviços LangGraph-inspired entregues

### ⚠️ Pendente (gates humanos)
| Gate | Descrição | Status |
|---|---|---|
| H1 | Preencher API keys reais no `.env` | Aguarda operador |
| H3 | Validar conectividade testnet end-to-end | Aguarda operador |
| H5 | Executar primeira ordem paper com dados reais | Aguarda operador |
| H6 | Aprovar transição testnet → mainnet | Aguarda operador |

### 🐛 Bugs conhecidos (não-críticos)
- `DoctorStrange` sem deduplicação de notícias entre ciclos
- `BlackPanther` campo `long/short_liquidations_24h` pode ser zero (API HL não expõe diretamente)
- `SpiderMan` sem memória entre ciclos — crash >4h não visto como continuação
- Live chart pode congelar se WebSocket HL desconectar (workaround: fallback de preço implementado na Story 096-fix)

---

## 7. Arquivos críticos — leia antes de tocar

| Arquivo | Por quê é crítico |
|---|---|
| `src/agents/nick_fury.py` | Orquestrador — qualquer bug aqui quebra o pipeline inteiro |
| `src/agents/batman.py` | Risk gate — nunca bypassar, nunca simplificar |
| `src/config/settings.py` | Todas as flags de comportamento moram aqui |
| `src/models/signal.py` | Geometria SL/TP — não alterar sem aprovação explícita |
| `conftest.py` | Injeção de stubs de test — siga sempre este padrão |
| `scripts/kill.sh` | Kill switch — testar antes de qualquer live deploy |
| `docs/MEKKA-DEV.md` | Regras absolutas — leia PRIMEIRO |

---

## 8. Próximos milestones sugeridos (Milestone 36+)

> Milestones 34 (Monitoring & Alerting, Stories 213-218) e 35 (Backtesting Engine, Stories 219-223) já entregues.

### Opção A — Backtesting Dashboard (Impacto Alto, Visual)
Expor BacktestSummary via HTTP + painel WebSocket com curva de equity ao vivo, comparação entre períodos, relatório Telegram.
Stories sugeridas: `224-228` (5 stories)

### Opção B — Live Performance Tracking (Fundação para análise contínua)
Rastrear performance real vs. backtest, alertas de divergência entre simulado e realizado, métricas rolling.
Stories sugeridas: `224-228` (5 stories)

### Opção C — Risk Dashboard Avançado (UX do operador)
Visualizações de risco em tempo real: equity curve interativa, Batman verdicts timeline, heat map de regime, Deadpool analytics no dashboard.
Stories sugeridas: `224-228` (5 stories)

### Opção D — Multiagent Debate (Novo padrão AI)
Implementar padrão de debate entre agentes antes da decisão Vision (Society of Mind / Constitutional AI patterns).
Stories sugeridas: `224-228` (5 stories)

---

## 9. Comandos essenciais

```bash
# Ambiente
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate

# Smoke test baseline
pytest -v
python3 scripts/check_roster_consistency.py

# Rodar pipeline (paper mode)
python3 -m src.agents.nick_fury

# Rodar dashboard
python3 -m src.dashboard.server

# Kill switch
./scripts/kill.sh "motivo"
rm data/.kill_switch  # para retomar

# Validar sintaxe de qualquer arquivo novo
python3 -c "import ast; ast.parse(open('src/services/X.py').read()); print('OK')"

# Commit padrão
git add <files>
git commit -m "feat(story-NNN): título curto

Descrição do que foi implementado.
Closes Story NNN"
```

---

## 10. Regras absolutas (não negociáveis)

1. **`paper_trading=True`** — IronMan não toca a SDK enquanto esta flag estiver on
2. **Nunca burlar Batman** — toda execução passa pelo gate de risco
3. **Somente super-heróis** — zero referências a "rat/RatarIA/rodent"
4. **Uma feature → uma story** — sem acelerar, sem juntar 3 em 1
5. **Nunca modificar** `batman.py`, `kill_switch`, geometria SL/TP sem aprovação do operador
6. **Nunca usar API keys reais em código** — conftest.py injeta stubs
7. **Sempre validar sintaxe** antes de fechar uma story
8. **Testes primeiro** — não fechar story sem pytest verde

---

## 11. MCP / AIOX Core — regras de governança

| Operação | Quem faz | Comando |
|---|---|---|
| Search MCP catalog | @devops / Gage | `*search-mcp` |
| Add MCP server | @devops / Gage | `*add-mcp` |
| List MCPs | @devops / Gage | `*list-mcps` |
| Setup Docker MCP | @devops / Gage | `*setup-mcp-docker` |

**Prioridade de ferramentas:**
- Read/Write/Edit tools > docker-gateway
- Bash tool > docker-gateway para comandos locais
- docker-gateway APENAS para EXA, Context7, Apify (dentro do Docker)

**MCPs ativos:**
- `playwright` — browser automation (direto no Claude Code)
- `desktop-commander` → `docker-gateway` — ops Docker
- `EXA` (via docker-gateway) — web search
- `Context7` (via docker-gateway) — docs de bibliotecas
- `Apify` (via docker-gateway) — web scraping

---

## 12. Handoffs anteriores (referência histórica)

| Arquivo | Cobertura |
|---|---|
| `docs/HANDOFF.md` | Stories 025-041, bugs críticos C1-C3 |
| `docs/HANDOFF_2026-05-15.md` | Milestone 24-25 (Stories 152-162) |
| `docs/HANDOFF_2026-05-15f.md` | Milestone 25 (Stories 157-162) |
| `docs/HANDOFF_2026-05-16a.md` | Milestone 26 (Stories 163-167) |
| `docs/HANDOFF_2026-05-16b.md` | Milestone 27 (Stories 178-182) |
| `docs/HANDOFF_2026-05-16c.md` | Milestone 28 (Stories 183-187) |
| `docs/HANDOFF_2026-05-17.md` | Milestones 29-30 (Stories 188-202) |
| `docs/HANDOFF_2026-05-17b.md` | Milestone 32 (Stories 203-207) |
| `docs/HANDOFF_2026-05-17c.md` | Milestone 33 (Stories 208-212) |
| **`docs/HANDOFF_MASTER_2026-05-18.md`** | **Este arquivo — estado completo** |

---

## 13. Quick start para @dev (próxima IA)

```bash
# 1. Confirmar baseline
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pytest -q  # esperado: ~500+ testes verdes
python3 scripts/check_roster_consistency.py  # esperado: [OK] 15 heroes

# 2. Ver última story entregue
tail -30 docs/stories/story-223-backtest-runner-cli.md

# 3. Ver índice completo
cat docs/stories/INDEX.md | grep "^## Milestone" 

# 4. Confirmar integridade dos serviços Milestone 35
python3 -c "
from src.services.backtest_runner import BacktestRunner
from src.services.backtest_signal_loader import BacktestSignalLoader
from src.services.backtest_outcome_simulator import BacktestOutcomeSimulator
from src.services.backtest_equity_curve import BacktestEquityCurve
from src.services.backtest_metrics_engine import BacktestMetricsEngine
from src.models.backtest import BacktestSummary, BacktestMetrics, BacktestTrade, EquityPoint
print('Milestone 35 — OK')
"

# 5. Rodar backtest rápido (após ter dados no DB)
python -m src.backtest run --symbol BTC --days 30

# 6. Iniciar próxima story
# Escolha uma das opções em § 8 e implemente seguindo MEKKA-DEV.md § 5
```

---

*Documento gerado em 2026-05-18 · Milestones 34+35 completos · Story 223 é a última entregue*
