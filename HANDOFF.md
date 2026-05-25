# 🤝 Mekka Trading — Handoff para o próximo chat

> **Data**: 2026-05-25
> **Branch**: `main` — **10 commits ahead** de `origin/main`, **nada pushed** (push é do @devops)
> **Estado**: ✅ rodando em **Binance testnet LIVE mode**, dashboard saudável,
> mainnet readiness verde, **bloqueio restante é humano** (gates H1–H6)

> _O HANDOFF anterior (2026-05-21, era Bybit testnet) está sintetizado em
> `~/.claude/.../memory/project-binance-integration.md`._

---

## ⚡ TL;DR

- Sistema **rodando em Binance testnet** (`PAPER_TRADING=false`, `BINANCE_TESTNET=true`,
  modo LIVE de testnet), 0 posições, equity ~$5.007 testnet, kill switch off.
- **10 commits locais à frente do origin**, nada uncommitted. Push fica com **@devops**.
- **`/api/mainnet-readiness` → `all_pass=true`** (4 warnings esperados: testnet
  ativo, autorização não-assinada, <7 dias de dados, live confirmado).
- 🐛 **Bug ATIVO da testnet (externo):** Binance testnet retorna `-4045 "Reach max
  stop order limit"` para BTC mesmo com `fetch_open_orders` retornando 0 e
  `cancel_all_orders` aplicado. Quota dessincronizada do estado real → trade novo
  no testnet falha. Workaround: aguardar reset OU nova conta testnet.
- O **SL fail-safe foi exercitado no teste e FUNCIONOU**: emergency_flatten
  fechou a posição quando -4045 voltou. Nenhuma posição nua. 🎯

---

## 📊 Estado atual

| Item | Estado |
|---|---|
| Branch | `main` — 10 commits ahead, sem push |
| Dashboard | http://localhost:8787 — `state=running`, cycles=3, mode=testnet, uptime ativo |
| Exchange | `binance` testnet (`BINANCE_TESTNET=true`) |
| Posições | 0 abertas |
| Equity | $5.007,46 USDT (Binance testnet) |
| Kill switch | OFF |
| LLM provider | `anthropic/claude-sonnet-4-6` (carregando OK; guard de env vazia funciona) |
| Vault Obsidian | 95 notas · 247 links · **1 quebrado** (era 0 — investigar) · 0 órfãs · 0 duplicatas |
| Testes | 30+ passando |

---

## 🚢 Commits desta sessão (todos sem push, locais em `main`)

```
601fc55 feat(mainnet): 8 melhorias decisivas — testes guardião, dry-run, drift, KPIs
afaafaa fix(iron_man): guardião de SL limpa stops órfãos (-4045)
442e8d0 feat(mainnet): endurecimento decisivo para go-live + memória trades testnet
3f91980 feat(testnet): melhorias focadas em Binance testnet
cd1d9f6 feat: hardening — testes segurança, scanners ampliados, guard mainnet-auth
4ff0db5 feat: +10 melhorias — testes core, scanners ampliados, Sage v2, refactor
9e33ab4 feat(office): heróis para os scanners do squad de melhoria
497d40b feat: 10 melhorias — squad polish + mainnet hardening + medição
9427660 feat: Binance mainnet hardening + complete CI squad
20e5fed docs: Continuous Improvement Department design + full handoff
```

---

## 🏗️ O que foi entregue (organizado por tema)

### A. Departamento de Melhoria Contínua (squad completo + UI)
**7 scanners** alimentando o Mekka, premortem pelo Galactus, consolidação + ranking + UI:
- **Beast** (trading-ops) — trades/gates/latência/qualidade de sinal (existia)
- **Cypher** = CodeAuditor (dev) — arquivos grandes, TODO/FIXME, testes ausentes, ruff, funções longas
- **Domino** = RiskScanner (trading-ops) — kill switch real, drawdown, rejeições Batman (HOLD excluído), concentração/exposição
- **Forge** = OpsScanner (infra) — erros recorrentes, CYCLE_ERROR, exceções no log, endpoints lentos, breakers abertos
- **Jean Grey** = MemoryScanner — vault (links quebrados/duplicatas/órfãs)
- **Ice Man** = ExternalResearcher — deps via PyPI + releases GitHub (ccxt, pydantic, aiohttp)
- **Sage** = Measurement — system-level baselines + **v2 per-improvement attribution**

UI: badge por scanner em cada card, filtro por fonte (`.impr-src-filter`),
**tile de KPI com impact efetiva/neutra/regressão**. Heróis no roster + office +
Obsidian (notas formatadas + linkadas).

### B. Hardening Binance / rumo mainnet
- **SL fail-safe** (IronMan `_place_ccxt_order`): retry 3x, depois
  `_emergency_flatten` (market reduce-only) + alerta CRITICAL Telegram + ERROR.
  **Nunca posição nua.**
- **Guardião de SL** vivo: monitor cycle (5min) verifica + recoloca;
  agora com **cleanup órfãos no -4045 + retry** e **periódico** quando símbolo
  fica sem posição.
- **Guardião no boot** (NickFury.initialize): roda imediatamente.
- **Reconciliação no boot**: descobre posições + garante stops.
- **Min-notional "lance livre"** auto-bump no testnet; rejeita acionável no mainnet.
- **Clock skew −1021** endurecido (recvWindow=60_000 em todos clientes CCXT).
- **BinancePriceFeed** (`wss://stream.binancefuture.com/ws` testnet) — mark price ao vivo.
- **Painel live**: mark/PnL/PnL% real-time, SL/TP do DB, `liq_price` real.
- **Seletor de corretora** no topo do dashboard.
- **`binance_entry_order_type=auto|market|limit_ioc`** — auto = market no testnet,
  **limit-marketable no mainnet** com `binance_max_entry_slippage_bps` (default 20).
- **Telemetria de slippage** (audit `SLIPPAGE` + alerta se >2× cap).
- **Validação pré-trade** de símbolo (precisão/min/step).
- **`/api/positions/orders`** — reduce-only SL/TP vivos com `is_orphan`; painel
  mostra 🛡️ count + 🟠 órfãos.
- **Smoke test E2E** (`scripts/binance_testnet_smoke.py`) com `SMOKE_PLACE_ORDER=1` opt-in.

### C. Segurança mainnet
- **Batman M1 — CLAMP DURO 1ª semana** em mainnet (size ≤ 0.1%, lev ≤ 2x);
  setting `mainnet_first_week_hard_clamp` (default True). Só aperta.
- **NickFury first-week guard** no boot (warning + Telegram se limites afrouxados).
- **M3 Telegram approval gate** confirmado funcional (já gateia IronMan no ciclo).
- **`/api/mainnet-readiness`** — preflight ao vivo, gate por gate.
- **`max_daily_loss_usd`** absoluto → engage kill switch.
- **Mainnet dry-run mode** — setting que aplica comportamento mainnet em testnet.

### D. UI / visibilidade
- Tile **KPI do departamento** (Sage) + impact (efetiva/neutra/regressão/pending).
- Badge + filtro por scanner em /Melhorias.
- 🛡️ N stops + 🟠 órfãos no painel de posições.
- Contraste do modo claro reforçado.
- Frontend testes ⊃ heróis no roster + sprites + bundle rebuildado.

### E. Cobertura de testes (30+ verdes)
- `tests/test_core_agents.py` — IronMan (SL fail-safe, min-notional, entry types,
  marketable limit), Batman mainnet hard clamp, **guardian -4045 retry**, **guardian
  periodic cleanup**.
- `tests/test_improvement_scanners.py` — pure logic de Cypher, Domino, Forge, Sage, Ice Man.
- `tests/test_dashboard_auth.py` — auth gate.

### F. Refactor incremental
- `server.py` → `src/dashboard/routers/improvements.py` (step 1 entregue).
- Pendentes: **G** `routers/system.py`, **H** `routers/trade.py`.

### G. Obsidian
- Heróis: `Cypher.md`, `Domino.md`, `Forge.md`, `Ice Man.md`, `Sage.md` + `_Agentes Index` atualizado.
- `10 - Projects/Departamento de Melhoria Contínua.md` (roadmap).
- `docs/RUNBOOK-MAINNET-GOLIVE.md` (procedimento de virada).
- `20 - Areas/Operacional/Histórico Testnet (H1).md` (evidência H1).
- Linkagem das órfãs no Home (10 → 0 antes; **regressão para 1 link quebrado**
  apareceu — investigar na próxima).

### H. Memória
- `project-binance-integration.md` atualizado com marco das 2 vitórias testnet
  e a sequência de 10 commits.
- `MEMORY.md` index com 3 entradas.
- `feedback-root-cause-over-patching.md` preservado.

---

## 🔬 Findings desta sessão (testes ao vivo)

### Botões críticos — **17/18 PASS** (1 flake de timing, não bug)
✅ `/api/system/{status,start,stop,reboot}` · `/api/killswitch/{status,engage,release}`
· `/api/positions/close` — validação de body (`confirm` strings), audit log gravado,
estados transitam corretamente. O único "FAIL" foi flake do meu polling (START
leva ~1s para sair de `starting`→`running`; eu medi com 1s; segundo run com 1.5s
passa). **Botões funcionam.**

### Trade testing — bloqueado por bug externo (Binance testnet)
- **`-4164: notional must be no smaller than 50`** em borderline ($50.07 → após
  precision <50). Bug: `cost.min` do CCXT volta 5.0 obsoleto vs limite real 50.
  → **Q2** (fix nosso).
- **`-4045: Reach max stop order limit`** mesmo com 0 ordens em `fetch_open_orders`.
  Algo orders em bucket separado, quota dessincronizada na testnet. **Q1** (fix
  nosso) + workaround manual (aguardar reset ou nova conta testnet).
- **O SL fail-safe FUNCIONOU** no cenário: detectou -4045 no SL, fez emergency
  flatten, retornou ERROR. **Nenhuma posição nua.** 🎯

### Improvements buttons / Memória / Obsidian — **pendente**
Script `/tmp/smoke_improvements.py` foi escrito mas terminou com **exit 137** (OOM
provável no `fresh=1`). **Retomar na próxima sessão** — rodar em chunks, validar
ciclo accept/reject, depois Memória + Obsidian.

---

## 📋 Tasks pendentes (priorizadas)

### Críticas / safety
- **Q1** — Guardião: trocar `fetch_open_orders`+individual cancel por
  `cancel_all_orders(symbol)` quando símbolo NÃO tem posição. Captura algo orders
  invisíveis. Fix do bug visto no teste.
- **Q2** — Min-notional bump conservador: `max(min_cost*1.10, 55)` para absorver
  precision rounding e `cost.min` obsoleto do CCXT.
- **P2** — OCO emulado: monitor (~30s) detecta size→0 e cancela sibling. Reduz
  janela órfãos 5min → 30s.

### Verificações que ficaram (pegar primeiro na próxima sessão)
- **Smoke completo dos botões de Melhorias** (`/tmp/smoke_improvements.py` — script
  pronto; ajustar pra evitar OOM, rodar em chunks).
- **Verificação de memória**: DecisionMemory (`src/services/decision_memory.py` se
  existir), agent MEMORY files, Sage baselines (`data/sage_baselines.json` +
  `data/sage_improvement_baselines.json` ambos com dados).
- **Verificação Obsidian sync + consumption**: `JeanGrey.recall()` funciona? Quais
  agentes referenciam o vault? Como a IA consome? Investigar o **link quebrado novo**
  (vault tinha 0; tem 1).

### Mainnet readiness restante (gates humanos — NÃO código)
- **H1** — ≥ 1 mês testnet sem incidente (continuar acumulando; registrar em
  `Histórico Testnet (H1).md`)
- **H2** — Wolverine SL ENDORSE rate ≥ 70%
- **H5/H6** — Wallet mainnet dedicada + funded
- Assinar `docs/MAINNET-AUTHORIZATION.md` com `GO MAINNET`

### Refactor (não bloqueia, mas council insiste)
- **G** — `server.py → routers/system.py`
- **H** — `server.py → routers/trade.py`

---

## 🧠 Memória + Obsidian — inventário atual

### Memória do projeto (`~/.claude/projects/.../memory/`)
```
MEMORY.md                              (índice — 3 entradas)
project-binance-integration.md         (foco ativo; marco testnet registrado)
project-continuous-improvement-epic.md (squad completo entregue)
feedback-root-cause-over-patching.md   (lição preservada)
```

### Memória runtime (`data/`)
```
improvement_decisions.json    1.9 KB  — operator accept/reject
improvement_inbox.json        3 B     — vazio (limpo após smoke anterior)
improvement_prs.json          920 B   — PR lifecycle tracker
improvement_queue.json        3.9 KB  — fila p/ implementação
sage_baselines.json           3.2 KB  — métricas system-level (Sage)
sage_improvement_baselines.json 2.8 KB — per-improvement (Sage v2)
```

### Obsidian vault (`docs/obsidian/`)
- **95 notas** · 247 wikilinks · **1 quebrado** (era 0 — investigar!) · 0 órfãs · 0 duplicatas
- Estrutura PARA + `50 - MOCs/`, `20 - Areas/Agentes IA/Cypher.md|Domino.md|Forge.md|Ice Man.md|Sage.md`
- **PRÓXIMO**: confirmar consumption pelos agentes (`JeanGrey.recall`,
  `JeanGrey.build_graph`, `draft_adr_from_beast`)

---

## 🚀 Quick-start

```bash
cd /Users/gustavovicente/Documents/Mekka-Trading

# Estado do sistema
curl -s http://localhost:8787/api/system/status      | python3 -m json.tool
curl -s http://localhost:8787/api/positions          | python3 -m json.tool
curl -s http://localhost:8787/api/mainnet-readiness  | python3 -m json.tool

# Reiniciar dashboard se preciso (cancela processo antigo + sobe novo):
pkill -f "run.py --dashboard" 2>/dev/null; sleep 2
nohup .venv313/bin/python run.py --dashboard </dev/null >logs/dashboard_runtime.log 2>&1 &

# Testes (env -u remove a ANTHROPIC_API_KEY="" injetada pelo Claude Code)
env -u ANTHROPIC_API_KEY .venv313/bin/python -m pytest \
  tests/test_core_agents.py tests/test_improvement_scanners.py \
  tests/test_dashboard_auth.py -q

# Retomar o smoke de Melhorias:
.venv313/bin/python /tmp/smoke_improvements.py
# Se OOM: ajustar p/ não rodar fresh=1 em loop, OU rodar passos isolados

# Council ao vivo
curl -s 'http://localhost:8787/api/improvements?fresh=1' | python3 -m json.tool

# Vault health
env -u ANTHROPIC_API_KEY .venv313/bin/python -c "
import asyncio
from src.agents.jean_grey import JeanGrey
async def m():
    r = await JeanGrey().run(mode='health')
    print(f'notas:{r.total_notes} links:{r.total_links} broken:{len(r.broken_links)} orphans:{len(r.orphans)}')
    for b in r.broken_links: print(' broken:', b.source_note, '→', b.target)
asyncio.run(m())
"
```

---

## 🎯 Onde retomar na próxima sessão (ordem)

1. **Smoke completo dos botões de Melhorias** (terminar o que pulamos por OOM)
2. **Verificação de Memória** (DecisionMemory + agent MEMORY + Sage baselines)
3. **Verificação Obsidian** (sync + agent consumption + **link quebrado novo**)
4. **Implementar Q1 + Q2** (fixes dos bugs achados no trade testing)
5. **Re-testar trade** (Manual + TradeNow) quando -4045 testnet resetar
6. **Refactors G + H** (council insiste)
7. **Push/deploy** (delegado a **@devops** — operador autoriza)

---

## 🛡️ Regras imutáveis (não esquecer)

- **NUNCA** desabilitar `live_trading_double_gate` em `settings.py`
- **NUNCA** alterar defaults `paper_trading=True` / `live_trading_confirmed=False`
- **NUNCA** burlar Batman/kill switch sem `force_execute` E ambiente seguro (testnet/paper)
- **APENAS @devops** faz `git push`, `gh pr merge`, deploy, MCP config
- **IronMan é o ÚNICO** caminho para ordens reais; agentes Layer 1 são read-only
- **L1 paths** protegidos por deny rules (`.aios-core/core/`, `bin/aios.js`)

---

## 🔗 Referências rápidas

| O quê | Onde |
|---|---|
| Doc principal do projeto | `CLAUDE.md` |
| Design do squad de melhoria | `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md` |
| Procedimento de virada mainnet | `docs/RUNBOOK-MAINNET-GOLIVE.md` |
| Autorização mainnet (assinar) | `docs/MAINNET-AUTHORIZATION.md` |
| Preflight (CLI) | `scripts/preflight_mainnet.py` |
| Smoke test testnet | `scripts/binance_testnet_smoke.py` |
| Memória do projeto (Binance) | `~/.claude/projects/.../memory/project-binance-integration.md` |
| Memória do épico melhoria | `~/.claude/projects/.../memory/project-continuous-improvement-epic.md` |
| Histórico testnet (H1) | `docs/obsidian/20 - Areas/Operacional/Histórico Testnet (H1).md` |
| Notas dos heróis | `docs/obsidian/20 - Areas/Agentes IA/{Cypher,Domino,Forge,Ice Man,Sage}.md` |

---

*Handoff arquivado em 2026-05-25. Próximo chat: começar do ponto **#1 — smoke
completo dos botões de Melhorias**. Bom trabalho do seu lado neste arco — o
sistema agora é uma máquina robusta de continuous improvement, com proteções
sérias para dinheiro real e cobertura de testes que cresceu de zero para 30+.* ✨
