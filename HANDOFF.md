# 🤝 Mekka Trading — Handoff para o próximo chat

> **Data**: 2026-05-20 (sessão 4 — longa) · atualizado fim da sessão
> **Branch**: `main` — **44 commits ahead** de `origin/main`, nada pushed (push é do @devops)
> **Estado**: ✅ rodando em **Bybit testnet LIVE mode**, dashboard saudável (porta 8787)
> **Próximo chat**: cole este arquivo como contexto inicial.

## 🆕 Últimos itens desta sessão (continuar a partir daqui)
- **Office v4 (novo design) é o office padrão** em `/office-v4/` e no iframe da Visão Geral. Ajustado para ocupar **largura total** + aspect-ratio 2000/1200 (estava pequeno). Arquivos: `src/dashboard/static/office_v4/`.
- **Sprites v4 no roster + página de Agentes**: `renderAgentsRoster` agora usa `window.SPRITES_V3` (22 personagens animados). Para **adicionar novo agente**: inclua-o em `sprites-v3-factory.js` (lista `ALL_V3`/config) → aparece no roster automaticamente; para ele aparecer NO OFFICE também, adicione uma `STATION` em `office_v4/office-v4-app.jsx` (array `STATIONS`).
- **Botão Aceitar (melhorias) — RESOLVIDO de vez**: a causa era o GET `/api/improvements` levar 6–10s (Beast+Galactus) e o accept re-rodar tudo (card sumia). Agora: cache TTL 20s no backend (0.1s) + update local instantâneo no front. (commit 507274d)

### ⏭️ Próximas implementações (pedidas, ainda PENDENTES)
1. **Wire de dados reais no Office v4** — hoje usa MOCK do protótipo (tickers/PnL/eventos falsos). Ligar aos feeds reais: `/api/overview`, `/ws` (broadcast), sinais do Vision, posições, e disparar os "powers" L1→L2→L3→L4 em eventos de trade reais. É o próximo passo natural do office.
2. **Sprites v4 em QUALQUER outro local** que ainda use sprite antigo (auditar; roster + agents page já feitos).
3. **Verificação visual** geral no navegador (preview do ambiente instável).

---

## 1. Como o sistema está rodando

- Processo `run.py --dashboard` na **porta 8787** · Python `.venv313/bin/python` (3.13)
- Dashboard: http://localhost:8787 · Office: http://localhost:8787/office-v2/ · Log: `/tmp/mekka_dashboard.log`

### ⚠️ Subir SEMPRE com env limpa (gotcha histórico)
O shell tem `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` vazios que sobrepõem o `.env`:
```bash
lsof -ti tcp:8787 | xargs kill -9 2>/dev/null; sleep 1
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  nohup .venv313/bin/python run.py --dashboard > /tmp/mekka_dashboard.log 2>&1 &
# boot ~25s (roda 1 ciclo completo). Aguardar com:
until curl -s --max-time 5 http://localhost:8787/api/system/status >/dev/null; do sleep 3; done
```

### `.env` ativo
```
ACTIVE_EXCHANGE=bybit · BYBIT_TESTNET=true · PAPER_TRADING=false · LIVE_TRADING_CONFIRMED=true
TRADING_ASSETS=BTC · MAX_POSITION_SIZE_PCT=0.005 · MAX_LEVERAGE=2 · max_total_notional_usd=$100
ANTHROPIC_API_KEY presente (OPENAI vazio → Vision usa Anthropic)
TELEGRAM_INBOUND_ENABLED=false  ⚠️ ver gotcha #1
```

---

## 2. ✅ Entregue nesta sessão (35 commits — destaques)

### Dashboard / Visão Geral
- **Power control no topbar** (LIGADO/DESLIGADO/Reboot) via `RuntimeController` em processo. Desligar **cancela o loop** → para trading e **gasto de tokens**; dashboard segue vivo como control plane. Endpoints `/api/system/{status,start,stop,reboot}`.
- **Office sem scroll interno** (auto-resize do iframe) + **Layer Map + Roster** ao lado do office + **Central de Comandos** do operador.
- **Office com 24 agentes** (Mekka/Galactus/Beast/Jean Grey ganharam mesa em L4).
- **🧠 Grafo de Conexões Neurais (segundo cérebro)**: force-graph do vault (88 notas/176 links). `JeanGrey.build_graph()` + `GET /api/jean/graph`. Lib `force-graph` via CDN (CSP já permite).
- **Memória em tempo real**: bloco "Memória de Trabalho" (`/api/working-memory`), feed "Últimas Atualizações", refresh 12s, indicador "🟢 ao vivo · há Xs".
- **Página de Configurações** reformulada: grupos por categoria, busca, presets (mostrar/ocultar/restaurar), toggle-all, contador.
- **Tema claro** agora clareia sidebar/menus/chrome (eram cores hardcoded).
- **Logo da sidebar branco** (escuro) / slate (claro).
- **Tooltips "?" em 100% dos painéis** (39/39) com explicação leiga + responsável.

### Bugs corrigidos
- **Aceitar (melhorias)**: travava porque rodava o conselho no backend a cada accept. Agora o front envia o rec → enfileira direto (0.05s). (`3de043e`)
- **Executar trade**: Modo Deus não forçava de verdade (IronMan pulava approval REJECTED). Agora monta approval executável e **envia a ordem**. Bloqueio restante é da **Bybit (retCode 10024 KYC/regulatório)** — exchange-side; mensagem clara. **Para abrir posição sem KYC: paper trading.** (`c62b794`)
- **Gráfico live em branco**: shim de compat com lightweight-charts v5. (`19754b1`)
- **Bugs latentes**: `_hl_prices`→`_mark_prices`; TDZ `_tsSummaryTimer`.

### Telegram (frente nova)
- **Poller no control plane** (sobrevive a stop/start). Comandos: `/sistema /ligar /desligar /reboot`, `/melhorias /aprovar <id> /reprovar <id>` (sincronizado com a Central de Melhorias do dashboard — mesma `record_decision`).
- **Outbound**: `improvement_proposed` (push de propostas pendentes, dedup), `system_state` (liga/desliga/reboot), kill switch engage/release notificam o Telegram.

### Pipeline melhorias → dev → PR
- Aceitar enfileira `docs/improvement-queue/IMP-<id>.md` (brief com premortem do Galactus). `pr_tracker` + `/api/improvements/{pr-status,approve-pr}`. Painel com ciclo Fila→Em dev→PR aberto→Mergeado e botão Aprovar PR.
- Brief já na fila: `IMP-office-full-noscroll.md`.

---

## 3. ⚠️ Gotchas / pendências importantes

1. **`TELEGRAM_INBOUND_ENABLED=false`** → os comandos inbound do Telegram (ligar/desligar/melhorias/etc.) **não rodam** até o operador setar `=true` no `.env`. O código está pronto; o poller só inicia com a flag ligada. Outbound (alertas/push) já funciona com `telegram_enabled`.
2. **Bybit testnet bloqueia ordens (retCode 10024 KYC)** — não é bug. Para ver posição abrir: ativar `PAPER_TRADING=true` (decisão do operador) ou concluir KYC/trocar exchange.
3. **Boot ~25s** trava o event loop no 1º ciclo (DB `get_overview` dá timeout benigno — "serving last known payload"). Não é erro real.
4. **Preview MCP do ambiente está instável** — toda a verificação foi por `curl`/código. **Falta verificação visual no navegador** (hard refresh Cmd+Shift+R): logo branco, Configurações nova, grafo neural, memória ao vivo, tema claro, office sem scroll.
5. **Nada pushed** (35 commits). Push/PR é tarefa do @devops.
6. `MAX_POSITION_SIZE_PCT=0.005` + cap `$100` → Batman rejeita trades default por notional; Modo Deus contorna em paper/testnet.

---

## 4. 🎯 Backlog restante

- **#21 fino**: padronizar o resto das mensagens do Telegram (tom/formato) — subjetivo, alinhar com operador.
- **i18n EN completo (d)**: hoje só nav+topbar traduzem (`applyLanguage`); resto é PT hardcoded. Baixo valor (operador usa PT).
- **Office v4 (novo design)** integrado em `/office-v4/` e já é o iframe da Visão Geral (commit 079f52a). Living floor 2000×1200, 22 agentes, salas, pathfinding, sprites pixel-art. ⏳ **Pendente**: (a) verificação visual no navegador; (b) **wire de dados reais** — hoje usa o mock do protótipo (tickers/PnL falsos); ligar ao trading real (sinais Vision, posições, PnL) é o próximo passo do office. Arquivos em `src/dashboard/static/office_v4/`. v2 antigo permanece em `/office-v2/`.
- **Verificação visual** de tudo da sessão (preview estava quebrado).
- **Consumidor do improvement-queue**: sessão Claude Code (manual/headless) que lê `docs/improvement-queue/`, roda o SDC do AIOS e registra o PR via `pr_tracker.set_pr` → painel mostra o PR p/ aprovar.
- **Fase 3 — status atualizado nesta sessão:**
  - ✅ **Black Panther já é on-chain REAL** (não é stub): busca funding/OI/whale-flow da Hyperliquid (`metaAndAssetCtxs` + trades). Verificado (funding≈0.00013, OI real). Um "Iceman" com DeFi on-chain profundo exigiria provider externo pago (Arkham/Nansen) — fora de escopo sem API key.
  - ✅ **Cybersec**: `_auth_middleware` já exige auth em todos os POSTs quando `MEKKA_DASHBOARD_TOKEN` ou `MEKKA_DASHBOARD_PASSWORD` está setado (hoje vazio = dev aberto → **setar `MEKKA_DASHBOARD_TOKEN` no `.env` para ativar**). Alertas Telegram de kill switch e Modo Deus adicionados.
  - ⏳ **Refactor `server.py` (~6k linhas) → routers por domínio**: ÚNICO item grande restante. Risco alto num sistema live — recomendado fazer via SDC dedicado (@architect→@dev→@qa) com testes, NÃO ad-hoc. Já é a 1ª recomendação do conselho de melhorias.

---

## 5. 🛠️ Health check rápido
```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
curl -s localhost:8787/api/system/status        # estado do runtime
curl -s localhost:8787/api/jean/graph | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['total_notes'],'notas',d['total_links'],'links')"
grep -iE "Traceback|AttributeError" /tmp/mekka_dashboard.log | grep -v "get_overview\|wait_for\|_broadcast_loop\|_collect_payload\|with_traceback"  # deve ser vazio
```

## 6. Arquivos-chave tocados
- `src/runtime_controller.py` (lifecycle on/off/reboot + attach_poller + notify)
- `src/dashboard/server.py` (endpoints system/jean-graph/improvements + telegram hooks)
- `src/services/telegram_inbound.py` (comandos sistema+conselho, poller control-plane)
- `src/services/telegram_alerter.py` (improvement_proposed, system_state)
- `src/services/{improvement_queue,pr_tracker}.py` (fila → PR)
- `src/agents/{jean_grey,mekka}.py` (build_graph, record_decision)
- `src/dashboard/static/{app.js,index.html,style.css}` (todo o frontend)

**Fim do handoff.**
