# AUTO-CONTINUE-PLAN

> **Esta é a automação do projeto.** Qualquer IA (Claude, Codex,
> Antigravity, etc.) que abrir o projeto e for instruída a "continuar"
> deve ler este arquivo, escolher a primeira tarefa não concluída, e
> executar. Não pause para perguntar entre sub-tasks da MESMA story —
> só pause se um pré-requisito do plano travar (testes vermelhos
> inesperados, ambiguidade de runtime crítico, ou hitting de uma
> regra absoluta de `MEKKA-DEV.md`).

> **O que esta automação NÃO é:** um daemon. Não há processo rodando
> entre sessões. A persistência é o próprio repositório git mais este
> documento. A "continuação" é o disciplina de ler-marcar-executar.

Última atualização: pós Story 032 (Python reader). 032b TS shim
agendada para quando operador validar `npm install better-sqlite3`.
Próxima ação automatizada: **§ 4 — Pre-testnet hardening** (operador) →
depois **§ 5 — Story 033 (Flash)**.

---

## Como usar

1. **No início de toda sessão**: rode `pytest -v` e
   `python3 scripts/check_roster_consistency.py` para confirmar
   baseline. Se vermelho, vá para § 99 (recuperação).
2. **Marque tarefas concluídas** com `[x]` neste arquivo, commit
   com mensagem `docs: AUTO-CONTINUE checkpoint <story-N>`.
3. **Não saltar etapas** sem registrar motivo em `## Histórico de
   desvios` no final.
4. **Não acelerar**: cada story tem que ter Scope/Tests/Acceptance
   antes de fechar. Nada de "depois eu volto e termino".

---

## § 1 — Smoke test (operador, ~5 min)

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
source .venv/bin/activate
pytest -v
python3 scripts/check_roster_consistency.py
./scripts/kill.sh "smoke"
rm data/.kill_switch
```

Esperado: ~135 verdes, roster `[OK] 15 heroes`, kill switch
criado e removido.

- [ ] Confirmado por: ____  (data: ____)

---

## § 2 — Story 031: Vision Critic ✅ ENTREGUE

**Goal**: adicionar second-look LLM opcional que revisa decisões do
Vision e endossa/amenda/rejeita. Toggle off por default.

### Sub-tasks (em ordem)

- [x] **2.1** Settings `vision_critic_enabled: bool = False` +
      `vision_critic_min_disagreement: float = 0.30`.
- [x] **2.2** `src/models/critique.py` com `CritiqueAction` enum
      (ENDORSE/AMEND/REJECT) e `VisionCritique` Pydantic.
- [x] **2.3** `src/agents/vision_critic.py` — GPT-4o second-look,
      fallback ENDORSE, safer-only filter, disagreement floor.
- [x] **2.4** Wire em `nick_fury._cycle_for_symbol` step 2b.
- [x] **2.5** `agents/__init__.py` — VisionCritic registrado em Layer 2.
- [x] **2.6** `tests/test_phase8_vision_critic.py` — 15 testes.
- [x] **2.7** `docs/stories/story-031-vision-critic.md`.
- [x] **2.8** INDEX, AGENTS, HANDOFF, este arquivo atualizados.

**Decisão arquitetural**: Vision Critic é **modalidade do Vision**, não
herói novo. Roster permanece 15 (registry.ts e HeroName enum não mudam).
Documentado em AGENTS.md como sub-bullet do Vision.

---

## § 3 — Story 032: Audit Single Source of Truth ✅ ENTREGUE (Python parte)

**Goal**: harmonizar `memory/*.ndjson` (TS) e `audit_log` SQLite
(Python) — único lado é fonte de verdade.

### Sub-tasks

- [x] **3.1** Decisão arquitetural documentada em
      `docs/adr/ADR-001-audit-single-source.md`. Adotada **Option C**
      (reader unificado primeiro, shim TS depois) por reversibilidade
      e por ambiente de IA não ter `npm install` confiável.
- [x] **3.2 (Python parte)** Criado
      `src/observability/unified_audit_reader.py` com
      `UnifiedAuditReader.read_recent` que lê SQLite + NDJSON,
      deduplica e ordena.
- [x] **3.5** `docs/stories/story-032-audit-single-source.md`.
- [x] **3.6** INDEX, AGENTS (sem mudança), HANDOFF, este arquivo
      atualizados.

### Story 032b futura (TS shim) — agendada

- [ ] **3.7** Operador roda `npm install better-sqlite3` e
      `npm test` em ambiente de desenvolvimento — se ambos verdes,
      destrava a story.
- [ ] **3.8** Criar `observability/sqlite-mirror.ts` duplicando
      events do TS event-pipeline em SQLite via `better-sqlite3`.
- [ ] **3.9** Marcar `memory/*.ndjson` como deprecated em
      `docs/ARCHITECTURE.md` § 7, manter writes por 1 milestone.
- [ ] **3.10** Tests TS + Python confirmando paridade durante grace
      period.
- [ ] **3.11** Atualizar INDEX/HANDOFF/este arquivo, fechar Story 032b.

---

## § 4 — Pre-testnet hardening (humano + IA)

Não é uma story formal — é checklist operacional antes de virar
`PAPER_TRADING=false`.

- [ ] **4.1** Recriar venv em **Python 3.13** (B3 do diagnóstico
      testnet original). Lazy imports salvam pytest mas não salvam
      Superman.run em produção.
      ```bash
      brew install python@3.13
      deactivate && rm -rf .venv
      /opt/homebrew/bin/python3.13 -m venv .venv
      source .venv/bin/activate
      pip install --upgrade pip && pip install -r requirements.txt
      pytest -v
      ```
- [ ] **4.2** **Smoke test manual da Iron Man SDK** (B2). Ordem
      $10 na testnet via Python REPL para confirmar shape de
      resposta da SDK. Documentar em `docs/RUNBOOK-TESTNET.md`.
- [x] **4.3** `docs/RUNBOOK-TESTNET.md` entregue — 11 passos com
      gates humanos explícitos do Python 3.13 venv até promoção
      após 1 semana verde.
- [x] **4.4** `docs/INCIDENT-PLAYBOOK.md` entregue — 8 incidentes
      catalogados (INC-001 a INC-008) com sintomas/ação imediata/
      diagnóstico/recovery por categoria.
- [ ] **4.5** Confirmar que `MAX_POSITION_SIZE_PCT=0.005`,
      `MAX_LEVERAGE=2`, `MAX_TRADES_PER_DAY=3` no `.env` para
      primeira semana testnet (mais conservador que default).
- [ ] **4.6** Operador cria wallet testnet dedicada (não pessoal).
- [ ] **4.7** Operador funded wallet via faucet Hyperliquid testnet.
- [ ] **4.8** Operador preenche `.env` com chaves reais.

---

## § 5 — Stories 033–034 (Tactical + Simulation)

Só fazer DEPOIS de § 4.1–4.8 e ≥ 1 semana de testnet estável.

- [x] **5.1** Story 033 — Flash (Momentum Scalper) entregue. Read-only
      e advisory; classifier determinístico (UP/DOWN/SIDEWAYS) +
      strength 0–1 + VOLUME-CONFIRMED tag. 16 testes na fase 10.
- [ ] **5.2** Story 034 — Deadpool (Chaos Simulator). Backtest +
      stress test. Pré-requisito: ≥ 30 dias de signals/trades
      históricos persistidos.

---

## § 6 — Story 035: Telegram Alerter ✅ ENTREGUE (push-only)

- [x] **6.1** ✅ Story 035b entregue 2026-05-08. `TelegramInboundPoller`
      com long-polling, allowlist por chat_id, comandos `/status /pnl
      /pause /resume /positions /help`. 10 testes fase 12 (276 total).
- [x] **6.2** Push automático em `RISK_KILL_SWITCH`, `EXEC_ERROR`,
      `EXEC_REJECTED`, `CYCLE_ERROR`, `MONITOR_RECOVERY_PLAN`
      (apenas quando kill_switch_engaged).
- [ ] **6.3** Daily report formatado — Story 035b futura.
- [x] **6.4** Settings: `telegram_alert_min_severity` (default
      WARNING) + `telegram_alert_events_raw` whitelist +
      `telegram_alert_timeout_seconds`.

---

## § 6b — Squad Fixes (pré-Story 036) ✅ ENTREGUE

15 melhorias estruturais implementadas antes de Story 036 como resultado da
avaliação dos três squads. Detalhes completos em
`docs/HANDOFF-2026-05-08-squad-fixes.md`.

- [x] **A1** Wolverine recebe `current_prices` reais via `/info` REST do HL.
- [x] **A2** Kill switch persiste JSON `{reason, agent, timestamp_utc}`; `/status` Telegram mostra metadados.
- [x] **A3** `NickFury.reset_breakers()` + `/resume` reseta ConsecutiveBreakers.
- [x] **A4** Snapshot de `daily_pnl` gravado quando kill switch aborta o ciclo.
- [x] **A5** Caps de leverage por regime de volatilidade (`HIGH=3x`, `EXTREME=2x`).
- [x] **B1/B2** IronMan extrai `filled_qty` real; zero-fill aborta sem SL/TP; SL/TP usam `filled_qty`.
- [x] **B3** `asyncio.Lock` + `_connect_async()` previne double-init do SDK HL.
- [x] **B4** Pre-flight margin check antes de qualquer ordem live.
- [x] **B5** Paper slippage sintético configurável via `paper_slippage_bps`.
- [x] **C1** `MarketAnalysis.confirmation_chart` (1h); ProfessorX chama Superman 2× (4h + 1h).
- [x] **C2** Superman rastreia `_exchange_id`; Binance/Bybit usa `BTC/USDT:USDT` + `defaultType=swap`.
- [x] **C3** CryptoPanic filtra posts por `published_after = now − 8h`.
- [x] **C4** Anomalias HIGH aparecem antes do chart no prompt Vision.
- [x] **C5** Flash wired no fan-out ProfessorX; `MarketAnalysis.momentum` + seção no prompt.
- [x] **C6** `VisionCritic` usa `vision_critic_model` e `vision_critic_temperature` independentes.
- [x] `tests/test_phase13_squad_fixes.py` — 35+ testes cobrindo todos os itens acima.

---

## § 7 — Story 036: Mainnet Readiness ✅ ENTREGUE (infra técnica)

Story 036 entregue 2026-05-08. Detalhes em
`docs/HANDOFF-2026-05-08-036-done.md`.

**Infraestrutura técnica entregue:**
- [x] **7.0a** `settings.live_trading_confirmed` + `live_trading_double_gate` validator.
- [x] **7.0b** `settings.is_live` property + `mode_label` atualizado.
- [x] **7.0c** IronMan runtime double-gate (belt-and-suspenders).
- [x] **7.0d** `scripts/preflight_mainnet.py` — 8 verificações automáticas + 6 lembretes humanos.
- [x] **7.0e** `docs/MAINNET-AUTHORIZATION.md` template.
- [x] **7.0f** `tests/test_phase14_mainnet_readiness.py` — 36 testes.

**Gates humanos (operador — H1–H6):**

- [ ] **7.1** ≥ 1 mês testnet sem incidente crítico.
      Rodar `python3 scripts/preflight_mainnet.py` periodicamente.
- [ ] **7.2** Wolverine SL ENDORSE rate ≥ 70% nos últimos 30 dias.
- [ ] **7.3** Vision Critic ON por ≥ 1 semana sem regressão de sinal.
- [ ] **7.4** Story 032b (TS audit shim) entregue ou waiver documentado.
- [ ] **7.5** Wallet mainnet dedicada criada (não pessoal).
- [ ] **7.6** Wallet funded via transferência real.
- [ ] **7.7** Operador preenche `docs/MAINNET-AUTHORIZATION.md` com
      "GO MAINNET" + assinatura. Preflight automaticamente detecta.
- [ ] **7.8** Primeira ordem mainnet com `MAX_POSITION_SIZE_PCT=0.001`
      (0.1%) por uma semana, depois aumenta gradualmente.

---

## § 99 — Recuperação (testes vermelhos inesperados)

Se `pytest -v` voltar com vermelho que não está documentado:

1. Não toque em runtime ainda.
2. Cole o output do pytest no chat.
3. Diagnose: bug em código de produção OU bug em teste OU
   contaminação de state.
4. Aplique fix mínimo no lugar correto (production fix em src/,
   test fix em tests/).
5. Atualize `docs/HANDOFF.md § 11.5` (Lições aprendidas) se for
   um novo padrão de bug.

---

## Histórico de desvios

(Anote aqui sempre que você sair do plano — por que, e o impacto.)

- 2026-05-08 — Story 029 entregue em duas fases (código por
  operador/linter, testes+docs por IA). Sem desvio de plano,
  só timing.
- 2026-05-08 — Story 030 entregue em sessão única após pedido
  "faça todas". Aplicado imediatamente após dashboard fix.
  Sem desvio.
- 2026-05-08 — Story 031 (Vision Critic) entregue na sequência
  imediata após pedido "siga para o próximo" do AUTO-CONTINUE.
  **Mini-desvio aplicado**: VisionCritic foi inicialmente
  registrado como herói novo no roster (16 heroes); reverti para
  modalidade do Vision (15 heroes mantidos) porque o tema Marvel
  não comporta nome composto e adicionar ao registry.ts/HeroName
  enum criaria fricção desnecessária. Documentado em AGENTS.md
  como sub-bullet do Vision.
- 2026-05-08 — Story 032 entregue dividida em duas. **Decisão
  arquitetural via ADR-001** adotou Option C (reader Python +
  shim TS depois) em vez de Option A (SQLite-wins direto). Razão:
  ambiente de IA não tem garantia de rodar `npm install
  better-sqlite3` + `npm test` confiavelmente. Story 032 entrega
  o lado Python (UnifiedAuditReader); Story 032b ficou agendada
  como sub-task §3.7-3.11 do plano, com pré-requisito explícito
  de ambiente npm validado pelo operador. **Não é desvio do
  plano; é refinamento da granularidade da § 3.**
- 2026-05-08 — Squad Fixes (15 melhorias pré-036) entregues em sessão
  única por solicitação "quero fazer todas as melhorias antes de ir para
  36". Sem desvio de plano. Adicionada § 6b ao AUTO-CONTINUE-PLAN para
  registrar. Detalhes: `docs/HANDOFF-2026-05-08-squad-fixes.md`.
  Nota: testes da fase 13 escritos; pytest via `.venv/python3.14` não
  pode rodar no sandbox Linux (Python 3.14 é macOS-only) — operador
  deve rodar `pytest tests/test_phase13_squad_fixes.py -v` localmente.
