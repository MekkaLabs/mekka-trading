# Mekka Trading — Handoff para Executor Técnico

> **Para quem é este documento**: a próxima IA (Claude Code, Codex, Cursor,
> Antigravity) ou desenvolvedor humano que abrir este projeto. Lê isto
> antes de qualquer outra coisa. Tempo de leitura: 7 minutos.

Última atualização: Story 028 (Contract Hardening). 28 stories entregues,
61 testes coletados (14 fase 1 + 20 fase 2 + 6 fase 3 + 7 fase 4 + 14 fase 5).

---

## 1. O que este projeto é (uma frase)

Mekka Trading é uma plataforma de trading multi-agente baseada em AIOX
Core, focada em Hyperliquid, paper-trading-first, construída de forma
incremental e pedagógica (uma feature → uma story → uma aula gravada).

## 2. Ordem obrigatória de leitura

1. **Este arquivo.**
2. `docs/MEKKA-DEV.md` — regras absolutas, naming, pacing pedagógico.
3. `AGENTS.md` — roster dos 15 heróis em 4 camadas.
4. `docs/ARCHITECTURE.md` — pipeline, I/O Pydantic por agente, ponte TS↔Python.
5. **A última story em `docs/stories/`** (numérica). Hoje: `story-026`.
6. `src/config/settings.py` — todas as flags de comportamento moram aqui.

Se você for tocar em um agente: leia o arquivo Python dele e os models
em `src/models/` antes de editar.

## 3. Estado atual em 30 segundos

| Camada     | Heróis (status)                                                        |
| ---------- | ---------------------------------------------------------------------- |
| Layer 1    | Superman ✅ · Doctor Strange ✅ · Black Panther ✅ · Thor ✅ · Aquaman ✅ · Spider-Man ✅ |
| Layer 2    | Vision ✅ · Professor X ✅                                              |
| Layer 3    | Batman ✅ · Iron Man ✅ (paper)                                          |
| Layer 4    | Nick Fury ✅ · Portfolio Manager ✅                                      |
| Pendentes  | Wolverine · Flash · Deadpool                                            |

| Componente               | Status                                                |
| ------------------------ | ----------------------------------------------------- |
| Pipeline Python (NickFury) | end-to-end paper-trading funcional                  |
| Pipeline TS (Megazord)   | 24 stories de observability/ops alerts entregues    |
| Persistência SQLite      | signals, trades, daily_pnl, audit_log               |
| Pytest                   | 34 verdes (phase1+phase2+phase3)                    |
| Dashboard web            | aiohttp + websocket, em `src/dashboard/`            |
| Telegram bot rico        | pendente                                            |
| Wolverine monitor real   | pendente (cycle ainda é heartbeat)                  |
| Daily PnL writer         | pendente (`get_today_drawdown_pct` lê do nada)      |

## 4. Pipeline canônico

```
NickFury.run_main_cycle(equity_usd?: Optional[float])
    ↓ PortfolioManager.run() → EquitySnapshot (real ou paper fallback)
    ↓ for each symbol in settings.trading_assets:
        ProfessorX.run(symbol)
            ↓ Superman (required) + parallel(DoctorStrange, BlackPanther, Thor, Aquaman)
            ↓ SpiderMan(chart, onchain)
            → MarketAnalysis
        Vision.run(analysis) → TradingSignal      (or fallback HOLD)
        save_signal(signal) → signal_id
        Batman.run(signal, vol, liq, drawdown, open_positions, trades_today)
            → RiskApproval (APPROVED/REDUCED/REJECTED/KILL_SWITCH)
        if approval.is_executable:
            IronMan.run(signal, approval, equity)
                → ExecutionResult (PAPER em paper_trading=True)
            save_trade(execution, signal_id)
        log_event(...)
```

Detalhes em `docs/ARCHITECTURE.md` seção 3 (diagrama mermaid).

## 5. Como rodar local

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pip install -r requirements.txt        # se ainda não fez

# Ciclo único (paper)
python run.py --once

# Loop infinito (paper)
python run.py

# Loop + dashboard
python run.py --dashboard

# Só dashboard (lê SQLite alimentado por outro processo)
python run.py --dashboard-only
```

Quality gates:

```bash
pytest -v                              # 34 testes Python
npm run lint && npm run typecheck && npm test && npm run build
```

## 6. Pontos quentes (atenção redobrada)

Estes são os pontos onde a próxima IA mais facilmente quebra algo:

- **`src/agents/batman.py`** — gate de risco determinístico. Não mexer
  em limites sem aprovação humana explícita.
- **`src/agents/iron_man.py`** — única classe autorizada a tocar a
  Hyperliquid SDK. `paper_trading=True` é o gate; preserve-o.
- **`risk-engine/` (TS)** — limites operacionais legados. Não conflitar
  com Batman; ambos coexistem (Batman é o gate de runtime Python,
  risk-engine TS é catálogo de policy).
- **Geometria SL/TP em `TradingSignal`** — o validator Pydantic é a
  única defesa contra LONG com stop_loss > entry. Não relaxar.
- **Kill switch** — env `MEKKA_KILL_SWITCH=1` ou arquivo
  `data/.kill_switch`. Absoluto. Tudo para.
- **Lazy imports em Superman/Vision/IronMan** — necessários para
  pytest coletar mesmo com deps científicas quebradas (numba/Python 3.14
  conflict). Não voltar a imports top-level sem entender o porquê.

## 7. Decisões em aberto

Documentadas mas não resolvidas — a próxima Story precisa escolher.

- **Audit log dual.** TS escreve em `memory/*.audits.ndjson`, Python
  escreve em SQLite `audit_log`. Single source of truth pendente.
- **Python version.** README diz 3.12; venv atual é 3.14.4; recomendado
  voltar para 3.13 para destravar pandas-ta + numba completos. Hoje os
  lazy imports + pinning permitem 3.14 sem quebrar pytest, mas Superman
  runtime real não funciona.
- **Equity sizing source.** CLI `--equity` flag (default 10000) e
  PortfolioManager coexistem. CLI vence se passado. Quando o sistema
  for live, isso precisa de uma decisão formal.
- **Dashboard scope.** `src/dashboard/` foi adicionado como camada
  nova. Não tem testes nem aparece em `MEKKA-DEV.md` ainda.

## 8. Próximas Stories candidatas (ordem recomendada)

| # | Story                | Impacto | Risco | Pré-requisito                |
| - | -------------------- | ------- | ----- | ---------------------------- |
| 029 | Wolverine          | Alto    | Baixo | 027 (drawdown), 028 (clean contracts) |
| 030 | Vision Critic      | Médio   | Baixo | (nenhum)                    |
| 031 | Audit harmonization | Médio  | Médio | (nenhum)                    |
| 032 | Flash              | Médio   | Médio | 029 (monitor cycle real)    |
| 033 | Deadpool           | Baixo   | Baixo | ≥ 30 dias de signals/trades históricos |
| 034 | Telegram bot rico  | Cosmético | Baixo | 027                       |
| 035 | Mainnet readiness  | Crítico | Crítico | 027, 029, 030 + checklist humano |

## 9. O que NÃO fazer (mesmo se parecer boa ideia)

- Migrar SQLite para Postgres.
- Adicionar Redis, Kafka, RabbitMQ.
- Substituir Pydantic v2 ou loguru.
- Mexer em `aiox-core/` interno.
- Implementar 5 stories em paralelo.
- Subir para mainnet sem checklist formal.
- Voltar nomes "rato/Rat/RatarIA". O tema é **só super-heróis**.
- Adicionar dependência pesada nova sem justificativa em uma Story.

## 10. Onde encontrar o quê

| Você quer...                                  | Vá para                                    |
| --------------------------------------------- | ------------------------------------------ |
| Adicionar/editar comportamento de runtime    | `src/config/settings.py` primeiro          |
| Criar novo agente Python                     | `src/agents/`, `src/models/` + nova story  |
| Adicionar nova CLI                            | `cli/` (TS) ou `run.py` (Python)           |
| Estender o dashboard                         | `src/dashboard/server.py`                  |
| Ver o que mudou recentemente                 | `git log --oneline` ou `CHANGELOG.md`      |
| Vault Obsidian (segundo cérebro)              | `docs/obsidian/` (PARA + MOC)              |
| Roster vivo dos 15 heróis                    | `AGENTS.md` (humano) + `agents/registry.ts` (TS code) |
| Schema de dados                              | `src/models/*.py` (Pydantic) + `src/persistence/models.py` (SQLAlchemy) |
| Tabela completa de env vars                  | `docs/ARCHITECTURE.md` seção 10            |

## 11. Travar e perguntar quando

- O escopo da story crescer durante a implementação.
- Houver duplicação iminente entre TS e Python.
- A mudança tocar em `risk-engine/` ou Batman.
- O pedido violar uma regra absoluta da seção 9 ou seção 6.
- Ambíguo entre dois agentes/camadas.

É mais barato perguntar agora que reverter depois.

---

**Fim do HANDOFF.** Próxima leitura obrigatória: `docs/MEKKA-DEV.md`.
