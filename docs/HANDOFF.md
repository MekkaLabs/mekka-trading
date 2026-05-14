# Mekka Trading — Handoff para Executor Técnico

> **Para quem é este documento**: a próxima IA (Claude Code, Codex, Cursor,
> Antigravity) ou desenvolvedor humano que abrir este projeto. Lê isto
> antes de qualquer outra coisa. Tempo de leitura: 7 minutos.

Última atualização: **Stories 034–039 entregues 2026-05-11.**
41 stories + squad hardening completo. **≥ 464 testes** esperados (pytest).
Pendentes: gates humanos H1, H3, H5, H6 (ação do operador — sem code work).
H2 auto-monitorado via Deadpool + preflight. H4 ✅ entregue (032b).

> **Squad fixes**: ver `docs/HANDOFF-2026-05-08-squad-fixes.md` para
> detalhes completos das 15 melhorias (A1–A5, B1–B5, C1–C6).

> **Roadmap automatizado**: leia `docs/AUTO-CONTINUE-PLAN.md` —
> qualquer próxima IA / sessão deve seguir o plano lá em sequência
> sem perguntar. É a "automação" possível dentro da disciplina
> pedagógica do projeto.

---

## 0. Janela de trabalho atual — sessão de continuidade

> **Para a próxima IA/sessão**: este bloco resume tudo que foi
> entregue desde Story 025 (quando o pipeline Python virou
> end-to-end). Ler antes do § 1.

### Stories entregues nesta janela

| #     | Título                              | Tipo        | Fase pytest |
| ----- | ----------------------------------- | ----------- | ----------- |
| 025   | Strategic Pipeline (Vision/Batman/IronMan/NickFury/ProfX) | core   | 2 (20)      |
| 026   | Portfolio Manager                   | agent       | 3 (6)       |
| 027   | Daily PnL Writer                    | service     | 4 (7)       |
| 028   | Contract Hardening (Pydantic/enums) | infra       | 5 (17)      |
| 029   | Safety Net (cap + breakers + kill.sh) | infra     | 6 (16)      |
| 030   | Wolverine — Recovery Agent          | agent       | 7 (15)      |
| 031   | Vision Critic (toggle off)          | modalidade  | 8 (15)      |
| 032   | Audit Single Source (Python reader) | infra+ADR   | 9 (19)      |
| 033   | Flash — Momentum Scalper            | agent       | 10 (16)     |
| 035   | Telegram Alerter (push-only)        | service     | 11 (14)     |
| 035b  | Telegram Inbound (long-polling cmds)| service     | 12 (10)     |

Pendentes: **032b** TS audit shim (npm) · **034** Deadpool (precisa
≥30d histórico) · **036** Mainnet readiness.

### Documentos não-story criados

| Arquivo                                  | Função                                           |
| ---------------------------------------- | ------------------------------------------------ |
| `docs/HANDOFF.md`                        | (este) handoff vivo para próxima IA              |
| `docs/MEKKA-DEV.md`                      | regras absolutas, naming, pacing                 |
| `docs/ARCHITECTURE.md`                   | pipeline + I/O Pydantic por agente               |
| `docs/DASHBOARD.md`                      | aiohttp + websocket, endpoints, do/dont          |
| `docs/CLEANUP.md`                        | checklist do que pode ser removido com segurança |
| `docs/AUTO-CONTINUE-PLAN.md`             | "automação" persistente em forma de checklist    |
| `docs/RUNBOOK-TESTNET.md`                | cold start testnet com 11 gates humanos          |
| `docs/INCIDENT-PLAYBOOK.md`              | 8 incidentes catalogados (INC-001 a INC-008)     |
| `docs/adr/ADR-001-audit-single-source.md`| primeiro ADR — decisão Option C                  |
| `docs/stories/INDEX.md`                  | índice por milestone                             |
| `scripts/check_roster_consistency.py`    | guard CI — TS↔MD roster                          |
| `scripts/kill.sh`                        | kill switch ergonômico (touch + audit)           |

### Bug fixes desta janela (não-story)

- `tests/test_phase4_daily_pnl.py::test_peak_is_monotonic_within_day` —
  tolerância `rel=1e-6` → `abs=1e-5` (fp precision após `round(x, 6)`).
- `tests/test_phase6_safety_net.py` × 5 — substituído `__dict__["x"] = y`
  por `monkeypatch.setattr(real_settings, ...)` (Pydantic v2 não aceita
  `__dict__` mutation em fields).
- `src/dashboard/server.py::_handle_replay_export` — filtro `start_utc`
  defensivo: timestamp inválido com filtro ativo agora **exclui** em vez
  de incluir.
- `src/agents/superman.py` — `ccxt` e `pandas_ta` viraram lazy imports
  (resolveu pytest collect quando numba falha em Python 3.14).
- `src/agents/vision.py` — `from openai import ...` em try/except
  (resolveu pytest sem `openai` instalado).

### Lições aprendidas (consulte § 11.5 antes de tocar testes)

- **Pydantic v2 BaseSettings**: nunca via `__dict__` em fields (cached_property é exceção).
- **`pytest.approx`** com produção que faz `round(x, N)` precisa `abs=10**(-(N-1))`, não `rel`.
- **Comentários `#` inline em comandos shell** quebram colagem.
- **Mock chain depth** — `run_main_cycle` exige mockar 5 boundaries.

### Estado consolidado

- **34 stories Mekka** entregues (001–033 + 035).
- **159 testes Python** + dashboard (esperados verdes).
- **ADR-001** decisão Audit Single Source.
- **Roster** `[OK] 15 heroes`. Nenhum drift TS↔MD.
- **Compatibilidade**: Python 3.14 funciona em pytest (lazy imports);
  Python 3.13 obrigatório para `python run.py --once` runtime real
  (numba/pandas-ta).
- **`paper_trading=True`** ainda é o default. Iron Man não enviou
  ordem real ao Hyperliquid em nenhum momento desta janela.

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
5. **A última story em `docs/stories/`** (numérica). Hoje:
   `story-029-safety-net.md`. Próxima planejada: `story-030`
   (Wolverine — Recovery Agent).
6. `src/config/settings.py` — todas as flags de comportamento moram aqui.

Se você for tocar em um agente: leia o arquivo Python dele e os models
em `src/models/` antes de editar.

## 2.5. Story 029 (Safety Net) — entregue

> **Histórico** (ficou aqui para referência futura). A Story 029 foi
> implementada em duas fases: o operador/linter adiantou o código
> (~80%), e a sessão seguinte fechou tests + docs + script.

### O que entrou no código

**Settings novos** (`src/config/settings.py`):
- `max_total_capital_pct: float` — cap percentual sobre soma de notional.
- `max_total_notional_usd: Optional[float]` — cap absoluto em USD (None desliga).
- `max_consecutive_exec_errors: int` — threshold para o exec breaker.
- `max_consecutive_vision_fallbacks: int` — threshold para o vision breaker.

**Batman** (`src/agents/batman.py`):
- `_run` ganhou parâmetros `equity_usd: float = 0.0` e
  `running_notional_usd: float = 0.0`.
- Nova seção "3b. Total capital cap" — rejeita signal cujo notional
  projetado (existing + new) excederia `max_total_notional_usd`
  (absoluto) OU `max_total_capital_pct * equity_usd` (relativo).
- Hard-cap: rejeita ANTES dos ajustes de Thor/Aquaman, comparando
  contra a *intenção* do Vision.

**Service ConsecutiveBreaker** (`src/services/breakers.py`):
- Counter passivo de hits booleanos. `observe(hit)` retorna `True`
  apenas no momento exato em que o streak cruza o threshold.
- Stateful no objeto; o orquestrador decide o que fazer no trip.
- 74 linhas, sem dependências de agente — fácil de testar isolado.

**Nick Fury** (`src/agents/nick_fury.py`):
- Imports + 2 breakers instanciados em `__init__`:
  - `self._exec_error_breaker` (threshold de
    `settings.max_consecutive_exec_errors`)
  - `self._vision_fallback_breaker` (threshold de
    `settings.max_consecutive_vision_fallbacks`)
- `run_main_cycle` calcula `running_notional_usd` no início somando
  `position.size * position.entry_price` do `EquitySnapshot.positions`,
  e incrementa a cada execução do cycle.
- `_cycle_for_symbol` repassa `equity_usd` e `running_notional_usd`
  para Batman.
- Novo método `_check_breakers(report)` chamado por símbolo:
  - Observa `report.execution.status == ExecutionStatus.ERROR` no
    exec breaker; trip → `engage_kill_switch` + audit log
    `RISK_KILL_SWITCH` com `payload.breaker = "exec_error"`.
  - Observa `report.signal.action == HOLD and metadata.fallback`
    no vision breaker; trip → mesmo padrão com
    `payload.breaker = "vision_fallback"`.

### Itens fechados nesta entrega

- ✅ `tests/test_phase6_safety_net.py` — 16 testes (6 breaker + 5 Batman cap + 5 Nick Fury)
- ✅ `docs/stories/story-029-safety-net.md` — story completa
- ✅ `docs/stories/INDEX.md` — Story 029 marcada entregue, Wolverine renumerado para 030
- ✅ `scripts/kill.sh` — kill switch ergonômico, smoke-tested
- ✅ `AGENTS.md` — Pending heroes apontam para Story 030+
- ✅ Este HANDOFF — Story 029 fechada, próxima 030

### Riscos conhecidos do código já escrito

- **Batman cap de capital roda ANTES de Thor multiplier.** Comportamento
  é intencional (proteger contra a intenção do Vision, não contra a
  versão pós-ajuste), mas precisa ser documentado em story-029 e em
  ARCHITECTURE.md para próxima IA não "consertar".
- **`_check_breakers` chama `engage_kill_switch` que escreve arquivo.**
  Em testes precisa monkeypatch de `_KILL_SWITCH_FILE` (mesmo padrão
  da fase 2/3) para isolar.
- **Vision fallback breaker não distingue causa.** Anomaly halt
  (Spider-Man HIGH) e OpenAI error tropam no mesmo contador.
  Aceitável para v1, mas vale registrar como "what's next".
- **Os testes da fase 2 e 3 que rodam `run_main_cycle` provavelmente
  ainda passam** porque os novos params Batman têm default 0 e os
  mocks substituem `_check_breakers` indiretamente via `_portfolio.run`
  retornar snapshot sem positions. Precisa confirmar com pytest real.

### Renumeração de Stories

- **028** = Contract Hardening (entregue)
- **029** = Safety Net (em andamento — código sim, docs/tests não)
- **030** = Wolverine (próxima após fechar 029)
- **031** = Vision Critic
- **032** = Audit harmonization
- **033** = Flash
- **034** = Deadpool
- **035** = Telegram bot rico
- **036** = Mainnet readiness

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
| Pytest Mekka             | 77 coletados, esperados verdes pós-fix Pydantic     |
| Pytest dashboard         | 1 vermelho conhecido não-bloqueante (§ 11.2)        |
| Dashboard web            | aiohttp + websocket, em `src/dashboard/`            |
| DailyPnLWriter           | ✅ entregue (Story 027)                              |
| Contract Hardening       | ✅ entregue (Story 028)                              |
| Safety Net (cap + breakers + kill.sh) | ✅ entregue (Story 029)                |
| Wolverine monitor real   | pendente (Story 030)                                |
| Telegram bot rico        | pendente (Story 035)                                |

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

Todas as stories de código estão entregues. O que resta é operador-side
(gates humanos) e melhorias incrementais opcionais.

| # | Story / Frente              | Status       | Impacto   | Pré-requisito                      |
| - | --------------------------- | ------------ | --------- | ---------------------------------- |
| H1 | Testnet ≥1 mês sem incidente | ☐ humano   | Crítico   | Operador monitorar INCIDENT-PLAYBOOK |
| H2 | Wolverine endorse ≥70%      | 🤖 auto     | Crítico   | Deadpool running (Story 034 ✅)    |
| H3 | Vision Critic ≥1 semana     | ☐ humano   | Crítico   | VISION_CRITIC_ENABLED=true          |
| H4 | Story 032b (TS audit shim)  | ✅ entregue | —         | —                                  |
| H5 | Wallet mainnet dedicada     | ☐ humano   | Crítico   | Operador criar wallet separada      |
| H6 | Wallet funded real transfer | ☐ humano   | Crítico   | H5 concluído                        |
| 038 | Dashboard /api/performance  | ✅ entregue | —         | —                                  |
| 039 | DailyPerformanceWriter      | ✅ entregue | —         | —                                  |
| 040 | /api/perf_history endpoint  | candidata   | Médio     | 039 ✅                             |

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

## 11. Como retomar a partir daqui (cold start)

Você (ou a próxima IA) acabou de abrir este projeto. Faça nesta ordem
**exata**:

### Passo 1 — Validar baseline

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pytest -v
```

Esperado: **119 ou 120 passed**. Se for 119/120, o único vermelho
deve ser `tests/test_dashboard_replay.py::TestReplayExport::test_utc_filter_excludes_out_of_range`
— veja § 11.2.

Se houver QUALQUER outro vermelho, **pare** e investigue antes de
seguir. Provável causa: novo código em `batman.py` / `nick_fury.py`
que entrou após este HANDOFF e quebrou contrato.

### Passo 2 — Validar guards de qualidade

```bash
python3 scripts/check_roster_consistency.py
python3 -m py_compile $(find src -name "*.py") tests/*.py
./scripts/kill.sh "smoke"
rm data/.kill_switch
```

Esperado: roster `[OK] 15 heroes`, compile sem output, kill switch
criado e removido sem erro.

### 11.1 Aviso ergonômico

Nunca cole comandos shell com comentários inline (`pytest -v # nota`).
O shell interpreta `#` como argumento literal e o `pytest` procura
um arquivo chamado `#`. Os blocos acima já estão limpos — se você
modificá-los, mantenha sem comentários inline.

### 11.2 Falha conhecida não-bloqueante

`tests/test_dashboard_replay.py::TestReplayExport::test_utc_filter_excludes_out_of_range`
está vermelho com `assert 2 == 1`. Esse teste **não pertence a
nenhuma Story Mekka 001–029** — apareceu junto com a expansão do
dashboard (não tem story doc associada).

- **Não bloqueia testnet.** Dashboard é read-only e desacoplado do pipeline.
- **Não tocar sem entender.** O teste assume que `_handle_replay_export`
  filtra rows fora do range UTC. Pode ser bug de dashboard novo OU
  expectativa desatualizada.
- **Próxima ação recomendada**: criar Story 029a — Dashboard Replay
  Filter Fix antes de Wolverine, OU isolar o teste com
  `@pytest.mark.skip(reason="dashboard, not Mekka pipeline")` e
  endereçar em uma story dedicada de dashboard.

### 11.3 Próximas frentes para destravar testnet

Em ordem de impacto:

1. **Resolver `test_dashboard_replay`** (1h) — escolher entre fix
   ou skip explícito. Sem isso, CI/pre-commit hooks que rodam
   `pytest` falham ruidosamente.
2. **Story 030 — Wolverine** (Recovery Agent + monitor cycle real,
   ~6h). Lê `EquitySnapshot.positions[]` que Portfolio Manager já
   entrega, recalcula SL/TP dinâmicos por ATR atual, aciona kill
   switch em drawdown intraday explosivo, preenche `wins`/`losses`
   em `DailyPnLWriter` quando posição fecha. **Última peça grande
   de runtime antes de testnet real.**
3. **Smoke test manual da Iron Man SDK** (1h, [B2] do diagnóstico
   testnet). Uma ordem $10 na testnet via Python REPL para confirmar
   shape de resposta da SDK antes de Vision decidir e Iron Man
   enviar. Hoje só o caminho paper foi exercitado em testes.
4. **Recriar venv em Python 3.13** (15 min, [B3]). Destrava
   `pandas-ta` runtime real. Lazy imports salvam pytest mas não
   salvam Superman.run() em produção.
5. **`docs/RUNBOOK-TESTNET.md`** (1h, [D1]). Checklist de cold start
   com gates humanos: criar wallet → faucet → preencher .env →
   smoke test → flip para live → primeira meia hora vigiada.

### 11.4 O que fazer NESTA ordem

```
[ ] 1. pytest -v → confirmar 119/120 (apenas dashboard vermelho)
[ ] 2. Decidir destino do test_dashboard_replay (fix ou skip)
[ ] 3. Story 030 — Wolverine (recovery + monitor real)
[ ] 4. Recriar venv Python 3.13
[ ] 5. Smoke test Iron Man SDK na testnet
[ ] 6. docs/RUNBOOK-TESTNET.md
[ ] 7. Operador executa runbook → primeira ordem testnet real
```

Story 030 é a última peça grande de **runtime** antes de virar
`PAPER_TRADING=false` no `.env`.

## 11.5 Lições aprendidas (não repita)

Bugs reais que cometi escrevendo testes — anote para não cair de novo:

**Pydantic v2 BaseSettings — nunca mexa em `__dict__`.**
Setar `instance.__dict__["field"] = value` em Pydantic v2 field
**corrompe o state interno** e quebra GETs subsequentes do mesmo
field em todo o processo. `__dict__.pop()` é ainda pior.
- ✅ Use `monkeypatch.setattr(real_settings, "field", value)` —
  Pydantic respeita setattr e o monkeypatch faz cleanup automático.
- ✅ EXCEÇÃO: `cached_property` USA `__dict__` para cache. Setar
  `instance.__dict__["cached_prop"] = X` é o padrão correto e não
  corrompe nada (`trading_assets` é cached_property, por isso o
  pattern continua sendo aceitável apenas para essa categoria).

**Tolerância em `pytest.approx`.**
Quando o código de produção faz `round(x, N)`, a diferença pode
ficar ~10×N maior que `rel=1e-N`. Use `abs=10**(-(N-1))` para ser
seguro. Exemplo: `round(x, 6)` → `pytest.approx(..., abs=1e-5)`,
não `rel=1e-6`.

**Comentários inline em comandos shell de docs.**
Markdown rendering preserva `# nota`, mas o terminal trata `#`
como argumento literal quando se cola o bloco. Sempre escreva
docs com comandos limpos e mova as notas para texto fora do bloco
de código.

**Mock chain depth.**
Os testes que rodam `NickFury.run_main_cycle` precisam mockar TUDO
abaixo: `_professor.run`, `_vision.run`, `_portfolio.run`,
`_daily_pnl.record_cycle` e `MekkaRepository`. Esquecer um deles
faz o teste tentar tocar SQLite real, OpenAI real ou Hyperliquid
real.

## 12. Travar e perguntar quando

- O escopo da story crescer durante a implementação.
- Houver duplicação iminente entre TS e Python.
- A mudança tocar em `risk-engine/` ou Batman.
- O pedido violar uma regra absoluta da seção 9 ou seção 6.
- Ambíguo entre dois agentes/camadas.

É mais barato perguntar agora que reverter depois.

---

**Fim do HANDOFF.** Próxima leitura obrigatória: `docs/MEKKA-DEV.md`.
