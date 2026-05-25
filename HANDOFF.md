# 🤝 Mekka Trading — Handoff para o próximo chat

> **Data**: 2026-05-25 (sessão 2 do dia, depois de `b849758`)
> **Branch**: `main` — **16 commits ahead** de `origin/main`, **nada pushed** (push é do @devops)
> **Estado**: ✅ rodando em **Binance testnet LIVE mode**, dashboard saudável,
> bug do banner kill_switch resolvido, **3 frentes maiores entregues**
> (aprendizagem real, pipeline melhorias, segurança mainnet)

> _O handoff anterior dessa data (sessão 1 — `HANDOFF.md` pré-`57bdc96`) está
> capturado no histórico git; este consolida ambas as sessões._

---

## ⚡ TL;DR

- **6 commits** novos hoje, todos locais em `main` (push fica com @devops).
- Sistema **rodando em Binance testnet** (`PAPER_TRADING=false`,
  `BINANCE_TESTNET=true`), 0 posições, mode=testnet, cycles ativos.
- **3 frentes maiores entregues** (priorizadas a partir de 3 auditorias paralelas):
  - **T0** Segurança mainnet — phantom reconciliation (`bd036b5`)
  - **T2** Pipeline melhorias — sync brief↔PR + claim (`729da36`, `29f3f80`)
  - **T1** Aprendizagem real — agente Mentor (`fde8c01`, `29f3f80`)
- Bug do banner `KILL_SWITCH_EVENT` em loop **resolvido** (`ef5da99`).
- **4 gaps de "writer órfão"** de memória **fechados** (`57bdc96`) — Vision
  finalmente tem 4 prompt-blocks alimentados com outcomes reais.
- **39 novos testes**, todos verdes. **63/63 PASS** nas suítes principais
  (zero regressão; a única falha pré-existente em `test_batman_no_clamp_on_testnet`
  passou desta vez também).

---

## 📊 Estado atual

| Item | Estado |
|---|---|
| Branch | `main` — **16 commits ahead**, sem push |
| Dashboard | http://localhost:8787 — `state=running`, mode=testnet |
| Exchange | `binance` testnet (`BINANCE_TESTNET=true`) |
| Posições | 0 abertas |
| Equity | ~$5.007 USDT testnet |
| Kill switch | OFF |
| Vault Obsidian | 95 notas · 247 links · 1 quebrado · 0 órfãs · 0 duplicatas |
| Testes | **63 passando** (39 novos hoje) |

---

## 🚢 Commits desta sessão (todos locais em `main`)

```
29f3f80 feat(improvement+mentor): fecha pendências do T2 e T1
fde8c01 feat(mentor): agente Charles Xavier — fecha loop de aprendizagem (T1)
729da36 feat(improvement): sincroniza brief.md ↔ pr_tracker + endpoint claim
bd036b5 feat(safety): phantom reconciliation — fecha drift DB→exchange
ef5da99 fix(dashboard): banner global_alerts não repete KILL_SWITCH antigo
57bdc96 feat(memory): fecha 4 gaps de writer órfão (Stories 063/183/186/249)
```

---

## 🏗️ O que foi entregue

### A. 4 gaps de memória órfã fechados (`57bdc96`)

Vision injetava 3 prompt-blocks que ninguém escrevia, mais 1 store onde o
`resolve_outcome` só rodava em auto-close (Cyclops SL/TP). Em mainnet seria
zero aprendizagem.

- **NickFury** (após signal actionable): grava `DecisionMemory.save_decision`
  (Story 249) + `RoleWorkingMemory.record` outcome=None (Story 183) +
  `record_signal` (Story 063, que já existia).
- **Helper central** `services/trade_outcome_resolver.py` chamado em **3 close paths**:
  Cyclops auto-close (`cyclops.py:701`), dashboard LIVE close (`server.py:2620`),
  dashboard PAPER close (`server.py:2700`). Resolve: `AgentMemoryStore.resolve_outcome` +
  `RoleWorkingMemory.resolve_outcome` + `SignalOutcomeMemory.record`. Recupera
  `action/regime/confidence` faltantes lendo o último `SignalRecord` actionable.
- Cada store é try/except independente — falha em um nunca bloqueia os outros
  nem o close.
- **4 testes** novos em `tests/test_trade_outcome_resolver.py` — 4/4 PASS.

Referência: `~/.claude/.../memory/project-memory-orphan-writers.md`.

### B. Bug do banner kill_switch (`ef5da99`)

Banner vermelho mostrava "NickFury reportou KILL_SWITCH_RELEASED" em loop
horas após o smoke ter terminado.

Fix em `_build_global_alerts` (`server.py:6643+`):
- Janela temporal de **10 min** — eventos antigos não acumulam mais
- Filtra out `KILL_SWITCH_RELEASED` (semanticamente released = OFF, não é incidente)
- O `KILL_SWITCH_FILE.exists()` continua cobrindo estado atual via filesystem
- try/except externo isola erro do filtro dos demais alertas

Validado E2E: 3 rows TEST inseridas (ENGAGED recente + ENGAGED antigo +
RELEASED recente) → exatamente 1 alerta (o ENGAGED recente). 4 cenários PASS.

### C. T0 Phantom reconciliation (`bd036b5`)

Risk Scanner (Domino) detectava drift DB↔exchange mas só propunha
`ImprovementProposal` — nenhuma reconciliação ativa. Em mainnet, posição que
fechou fora-do-bot (operador manual na exchange, liquidação) ficava
fantasma no DB e Vision/Wolverine/Cyclops decidiam sobre algo que não existe.

Novo método **`IronMan.reconcile_phantom_positions()`** (~150 LOC):
- Calcula net live position por symbol a partir do DB
- Compara com `exchange.fetch_positions()`
- Para cada "DB tem, exchange não" → insere synthetic close com
  `metadata.action="phantom_reconciled"` + audit `PHANTOM_RECONCILED` +
  alerta Telegram WARNING
- Paper mode: no-op. Hyperliquid: skipped (bookkeeping diferente).
- Setting `phantom_reconciliation_enabled` (default True) — kill switch via env

Cabeado em:
- Boot (NickFury.initialize): logo após `ensure_stops_for_open_positions`
- Monitor cycle (NickFury.run_monitor_cycle): logo após SL guardian

Complementa o SL guardian existente: SL guardian cobre "exchange tem, falta
SL"; phantom recon cobre "DB tem, exchange não". **Os dois juntos**: DB e
exchange convergem.

**8 testes** em `tests/test_phantom_reconciliation.py` — 8/8 PASS.

### D. T2 Pipeline melhorias — sync brief↔PR + claim (`729da36`, `29f3f80`)

**Backend (`729da36`):**
- `improvement_queue.update_brief_status(rec_id, status, ...)` — reescreve YAML
  do `IMP-{rec_id}.md` in-place E atualiza o índice. Anti-phantom: só cria
  entrada nova no índice se brief existir.
- `pr_tracker.claim_brief(rec_id, claimer)` — operator/dev sinaliza "estou
  implementando". Idempotente: não rebaixa pr_open/merged.
- **`set_pr` / `mark_merged` / `approve_pr` agora sincronizam brief.md automaticamente** —
  antes só atualizavam o store JSON.
- Endpoint `POST /api/improvements/claim` + audit `IMPROVEMENT_CLAIMED`.

**Frontend (`29f3f80`):**
- Botão "🛠 Vou implementar" em `app.js` que aparece em recs `accepted` com
  `dev_state=queued`. Prompt do claimer → POST → refresh PR status → re-render.
- CSS `.impr-claim` (cor warn/amarelo).

**Dev workflow (`29f3f80`):**
- Script `scripts/sync_imp_commits.py` — lê últimos N commits, detecta
  pattern `[IMP-{rec_id}]`, chama `pr_tracker.set_pr()` com synthetic PR
  number (range 9XXXXXXX). Idempotente.
- Pronto para pre-push hook (`chmod +x` já feito).

**Estado pós-deploy:** 26 briefs alinhados ao estado real (24 queued + 2 merged)
— antes eram 26 queued falsos.

**7 testes** em `tests/test_improvement_pipeline_sync.py` — 7/7 PASS.

### E. T1 Mentor — Charles Xavier (`fde8c01`, `29f3f80`)

Beast propunha melhorias em inglês livre via Telegram; ninguém aplicava.
Vision/Batman liam memory blocks mas nunca ajustavam thresholds. Sistema
"self-auditing" mas não "self-improving".

Novo agente **`src/agents/mentor.py`** (~390 LOC):
- **READ-ONLY** por design: nunca muta `settings.py`.
- Produz `ParameterSuggestion` tipado: `parameter_name`, `current_value`,
  `suggested_value`, `direction` (tighten/loosen), `reason`, `evidence` (dict),
  `confidence`, **`can_auto_apply`** (True só em tightening de risco).
- **3 heurísticas iniciais:**
  - `win_rate < 35%` em ≥8 trades → tighten `min_confidence` (auto-applicable)
  - `win_rate > 65%` em ≥20 trades → loosen `min_confidence` (manual review)
  - Batman rejection rate > 80% → review gates (manual review)
  - Drawdown ≥ 70% do limite → tighten `max_daily_drawdown_pct` (auto-applicable)
- `ParameterSuggestion.to_env_line()` produz `MEKKA_NAME=value` pronto para `.env`
- Audit `MENTOR_SUGGESTED` **só** quando há suggestion (zero spam)
- Conservative bias: loosening **sempre** exige operator review (`can_auto_apply=False`)

**Cabeado:**
- Endpoint `GET /api/mentor/suggestions`
- `NickFury.run_monitor_cycle` chama Mentor após phantom_recon (a cada 5min,
  ~260ms quando há dados)

**8 testes** em `tests/test_mentor.py` — 8/8 PASS.

**Estado ao deploy:** 0 suggestions porque `resolved_outcomes=0` (vai começar
quando o trade_outcome_resolver gerar os primeiros wins/losses, provavelmente
2-3 trades após este deploy).

---

## 🔬 Auditoria T0 — re-avaliada contra o código

O agent (c) Explore reportou 4 riscos altos. Verificação contra o código:

| Achado (c) | Realidade | Ação |
|---|---|---|
| T0.1 Cyclops live NO-OP | Coberto por `IronMan.ensure_stops_for_open_positions()` (boot + monitor cycle) | Não-blocker |
| T0.2 IronMan sem retry | Tem tenacity para `TimeoutError`/`ConnectionError`; rejeições de validação **não devem** retentar | Não-blocker |
| **T0.3 Position drift** | **GAP REAL — lado DB-órfão sem ação** | ✅ Implementado em `bd036b5` |
| T0.4 Wolverine kill auto-engage | Backstop correto em DD ≥ 10% (limite máximo) | Não-blocker |

3 de 4 eram falsos positivos. Lição persistida em
`~/.claude/.../memory/feedback-verify-audit-reports.md`.

**T3 cleanup** (Flash, Deadpool, VisionCritic, VisionMoA): também falsos positivos.
- Flash: cabeado em `professor_x.py:63,102`
- Deadpool: 4 consumers reais
- VisionCritic: `default=True` (opt-out)
- VisionMoA: opt-in por design (3 LLMs custam)
- **Nada a remover.**

---

## 📋 Tasks pendentes (próxima sessão)

### Próximos passos naturais

- **Worker automático "impl-agent"** — pega briefs `queued` e gera PR
  usando Claude Code. Design documentado no relatório do agent (b) da
  sessão anterior. **Out of scope hoje**, mas é o passo final pra
  fechar 100% o loop accept→merged.
- **Mentor scheduler diário** — hoje roda a cada monitor cycle (5min).
  Pode ser interessante ter um daily run que envia top suggestions
  por Telegram (igual o Beast).
- **Pre-push hook** — `cp` o exemplo de `scripts/sync_imp_commits.py`
  para `.git/hooks/pre-push` (1 linha de shell).
- **Operator UX** — testar fluxo completo no browser:
  accept → claim → implementar → commit `[IMP-xxx]` → push (sync_imp_commits
  roda) → status reflete no dashboard.

### Mainnet readiness (gates humanos — NÃO código)

- **H1** — ≥ 1 mês testnet sem incidente (continuar acumulando)
- **H2** — Wolverine SL ENDORSE rate ≥ 70%
- **H5/H6** — Wallet mainnet dedicada + funded
- Assinar `docs/MAINNET-AUTHORIZATION.md` com `GO MAINNET`

### Refactor (não bloqueia)

- **G** — `server.py → routers/system.py`
- **H** — `server.py → routers/trade.py`

---

## 🧠 Memória + Obsidian — inventário atual

### Memória do projeto (`~/.claude/projects/.../memory/`)

```
MEMORY.md                              (índice — 5 entradas)
project-binance-integration.md         (foco ativo; marco testnet registrado)
project-continuous-improvement-epic.md (squad completo entregue)
project-memory-orphan-writers.md       (4 gaps fechados em 57bdc96)
feedback-root-cause-over-patching.md   (lição preservada)
feedback-verify-audit-reports.md       (NOVA — relatórios automáticos generalizam)
```

### Memória runtime (`data/`)

```
agent_memories                  SQLite — 8 entries (PENDING; novos resolves a partir de agora)
improvement_decisions.json      1.9 KB  — operator accept/reject (19 accepted)
improvement_inbox.json          3 B     — vazio
improvement_prs.json            1.4 KB  — 2 PRs merged (#1001 #1002)
improvement_queue.json          3.6 KB  — 25 briefs (1 com claimer + state correto)
sage_baselines.json             4.6 KB  — métricas system-level (Sage)
sage_improvement_baselines.json 2.9 KB  — per-improvement (Sage v2)
```

### Obsidian vault (`docs/obsidian/`)

- 95 notas · 247 wikilinks · 1 quebrado (investigar) · 0 órfãs · 0 duplicatas
- **PRÓXIMO**: criar nota para Mentor (`20 - Areas/Agentes IA/Mentor.md`)

---

## 🚀 Quick-start

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading

# Estado do sistema
curl -s http://localhost:8787/api/system/status        | python3 -m json.tool
curl -s http://localhost:8787/api/positions            | python3 -m json.tool
curl -s http://localhost:8787/api/mainnet-readiness    | python3 -m json.tool
curl -s http://localhost:8787/api/mentor/suggestions   | python3 -m json.tool

# Reiniciar dashboard
pkill -f "run.py --dashboard" 2>/dev/null; sleep 2
nohup .venv313/bin/python run.py --dashboard </dev/null >logs/dashboard_runtime.log 2>&1 &

# Testes (env -u remove a ANTHROPIC_API_KEY="" injetada pelo Claude Code)
env -u ANTHROPIC_API_KEY .venv313/bin/python -m pytest \
  tests/test_mentor.py \
  tests/test_improvement_pipeline_sync.py \
  tests/test_phantom_reconciliation.py \
  tests/test_trade_outcome_resolver.py \
  tests/test_core_agents.py tests/test_improvement_scanners.py \
  tests/test_dashboard_auth.py -q

# Sync IMP commits manualmente (ou via pre-push hook)
.venv313/bin/python scripts/sync_imp_commits.py --limit 50

# Inspecionar Mentor suggestions ao vivo
.venv313/bin/python -c "
import asyncio
from src.agents.mentor import Mentor
async def m():
    r = await Mentor().run()
    print(f'obs: {r.observation_summary}')
    for s in r.suggestions:
        print(s.to_dict())
asyncio.run(m())
"

# Manual claim via API
curl -X POST http://localhost:8787/api/improvements/claim \
  -H 'Content-Type: application/json' \
  -d '{"id":"00589e51a312","claimer":"meu-nome"}'
```

---

## 🎯 Onde retomar na próxima sessão

1. **Testar o fluxo completo no browser** (recarregar dashboard, acceptar
   uma rec, clicar "🛠 Vou implementar")
2. **Decidir sobre worker "impl-agent" automático** (design pronto, alto custo)
3. **Tirar primeiros wins/losses** em testnet pra Mentor começar a sugerir
4. **Pre-push hook**: `cp scripts/sync_imp_commits.py.example .git/hooks/pre-push`
   (ou inline com 1 linha shell)
5. **Continuar acumulando dados** para gates H1/H2 da mainnet authorization
6. **Push/deploy** (delegado a **@devops** — operador autoriza)

---

## 🛡️ Regras imutáveis (não esquecer)

- **NUNCA** desabilitar `live_trading_double_gate` em `settings.py`
- **NUNCA** alterar defaults `paper_trading=True` / `live_trading_confirmed=False`
- **NUNCA** burlar Batman/kill switch sem `force_execute` E ambiente seguro
- **APENAS @devops** faz `git push`, `gh pr merge`, deploy, MCP config
- **IronMan é o ÚNICO** caminho para ordens reais; agentes Layer 1 são read-only
- **L1 paths** protegidos por deny rules (`.aios-core/core/`, `bin/aios.js`)
- **Verificar relatórios automáticos antes de patchar** — generalizam
  (`feedback-verify-audit-reports`)

---

## 🔗 Referências rápidas

| O quê | Onde |
|---|---|
| Doc principal do projeto | `CLAUDE.md` |
| Memória de aprendizagem (gaps fechados) | `~/.claude/.../memory/project-memory-orphan-writers.md` |
| Lição sobre relatórios automáticos | `~/.claude/.../memory/feedback-verify-audit-reports.md` |
| Design do squad de melhoria | `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md` |
| Procedimento de virada mainnet | `docs/RUNBOOK-MAINNET-GOLIVE.md` |
| Autorização mainnet (assinar) | `docs/MAINNET-AUTHORIZATION.md` |
| Phantom reconciliation | `src/agents/iron_man.py:1352` (`reconcile_phantom_positions`) |
| Trade outcome resolver | `src/services/trade_outcome_resolver.py` |
| Mentor (aprendizagem real) | `src/agents/mentor.py` |
| Pipeline sync brief↔PR | `src/services/improvement_queue.py` (`update_brief_status`) |
| Commit hook | `scripts/sync_imp_commits.py` |

---

*Handoff arquivado em 2026-05-25 (sessão 2). Próxima sessão: testar fluxo
completo no browser e começar a juntar dados (wins/losses + claims) para
Mentor produzir as primeiras suggestions concretas. Sistema agora aprende,
implementação flui, mainnet está mais protegida.* ✨
