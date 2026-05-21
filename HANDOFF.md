# 🤝 Mekka Trading — Handoff (sessão longa) para o próximo chat

> **Data**: 2026-05-21
> **Branch**: `main` — **~56 commits ahead** de `origin/main`, **nada pushed** (push é do @devops)
> **Estado**: ✅ rodando em **Bybit testnet LIVE mode**, dashboard saudável (todos endpoints 200)
> **Próximo foco**: construir o **Departamento de Melhoria Contínua** (design em `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md`).
> **Como retomar**: cole este arquivo + leia `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md`.

---

## 1. Como rodar (gotcha histórico — env limpa!)
O shell tem `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` **vazios** que sobrepõem o `.env`. Suba SEMPRE assim:
```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
lsof -ti tcp:8787 | xargs kill -9 2>/dev/null; sleep 1
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  nohup .venv313/bin/python run.py --dashboard > /tmp/mekka_dashboard.log 2>&1 &
until curl -s --max-time 5 http://localhost:8787/api/system/status >/dev/null; do sleep 3; done
```
- Dashboard http://localhost:8787 · Office novo http://localhost:8787/office-v4/ · Python `.venv313`.
- Boot ~25s (1º ciclo trava o event loop; `get_overview timed out` no log é **benigno**).
- **Preview MCP do ambiente é instável** → validei tudo por `curl`/código. **Verificação visual no navegador ainda pendente** (hard refresh Cmd+Shift+R).

`.env` ativo: `ACTIVE_EXCHANGE=bybit · BYBIT_TESTNET=true · PAPER_TRADING=false · LIVE_TRADING_CONFIRMED=true · TRADING_ASSETS=BTC · MAX_POSITION_SIZE_PCT=0.005 · MAX_LEVERAGE=2 · max_total_notional_usd=$100 · TELEGRAM_INBOUND_ENABLED=false`.

---

## 2. ⚠️ Flags que o operador precisa ativar (decisão dele; não mexi no .env)
1. `TELEGRAM_INBOUND_ENABLED=true` → liga os comandos inbound do Telegram (`/sistema /ligar /desligar /reboot /melhorias /aprovar /reprovar`). Código pronto; poller só inicia com a flag.
2. `MEKKA_DASHBOARD_TOKEN=...` → tranca os POSTs do dashboard (auth já existe no `_auth_middleware`).
3. `PAPER_TRADING=true` → para ver posição abrindo sem o bloqueio **KYC da Bybit** (retCode 10024).

---

## 3. ✅ Entregue nesta sessão (destaques)
**Dashboard / UX**
- **Office v4** (novo design do zip): living floor 2000×1200 em `/office-v4/` (React local + Babel unpkg, CSP estendida). Largura total na Overview + aspect-ratio (sem margens). **Nomes reais dos heróis** no floor (FLASH/IRONMAN/SUPERMAN/MEKKA via `HERO_NAME`). Roster **estático** (sem tremer).
- **Power control** no topbar (LIGADO/DESLIGADO/Reboot) via `RuntimeController`; desligar para o loop → **para gasto de tokens**; dashboard sempre vivo. `/api/system/{status,start,stop,reboot}`.
- **Tooltips "?"** 100% dos painéis (fix: CSS lia `attr(title)`, JS setava `data-tip`; agora abaixo do "?" com z-index 9999 — não some atrás do menu).
- **Configurações**: customizador com grupos por categoria, busca, presets, contador.
- **Tema claro**: sidebar/menus/chrome + contraste AA (melhoria entregue do conselho).
- **Memória em tempo real**: bloco "Memória de Trabalho", feed "Últimas Atualizações", refresh 12s, "🟢 ao vivo".
- **Grafo neural (segundo cérebro)** na Overview: force-graph do vault (`/api/jean/graph`).

**Melhorias (a área foco)**
- **Aceitar/Reprovar funcionam** (bug raiz: CSP bloqueava `onclick` inline → migrado para event delegation; idem os 10 onclicks do index.html).
- **Kanban** (Pendente→Aprovada→Em dev→Entregue→Reprovada) + **abas de status** (Novas/Em andamento/Fechadas/Todas, default Novas) + **contadores**.
- **Ciclo completo**: aceitar → enfileira brief `docs/improvement-queue/IMP-<id>.md` → desenvolvido → card de PR → **Aprovar PR** → **Entregue** (`mark_merged` local).
- **Botão "🔎 Buscar melhorias agora"** → roda o conselho na hora (`?fresh=1` bypassa cache 20s) com feedback estilo executar-trade.
- **As 2 melhorias aprovadas foram desenvolvidas e entregues**: contraste do modo claro + **server.py passo 1** (registro de rotas agrupado em 12 domínios; 107 rotas íntegras, boot OK).
- Sincronizado com **Telegram** (push de propostas + `/aprovar`/`/reprovar`).

**Trade / segurança**
- Modo Deus agora **executa de fato** (IronMan submetia REJECTED → skip; agora monta approval executável). Bloqueio restante = **Bybit KYC** (exchange-side; mensagem clara).
- Alertas Telegram de **kill switch** (engage/release) e **Modo Deus**.

**Bugs corrigidos de quebra**: `_hl_prices`→`_mark_prices`; TDZ `_tsSummaryTimer`; gráfico live (shim lightweight-charts v5); poll do power com retry.

---

## 4. 🧠 A ÁREA FOCO: Departamento de Melhoria Contínua
**Leia `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md`** — tem a metodologia atual, o papel da Jean Grey e o **design-alvo completo**.

**Resumo do pedido do operador:** a área deve melhorar **tudo** (agentes de trade, frontend, backend, infra, memória) e **buscar conhecimento fora** (repo/GitHub, internet, bases de trading), como um departamento de melhoria contínua de empresa, sob medida pro projeto.

**Como funciona HOJE** (ao clicar "Buscar melhorias"): Beast varre 4 fontes de runtime de trade (trades/gates/latência/qualidade de sinal) + inbox manual → Galactus faz premortem (hunger 0-100 + verdito) → Mekka consolida/ranqueia → operador decide. **Jean Grey** só audita o vault (não propõe ainda).

**Plano-alvo (próximo épico, via SDC):**
1. **CodeAuditor** (novo) — audita repo (arquivos grandes, TODO/FIXME, testes ausentes, ruff/mypy) → propostas dev **automáticas** (front/back).
2. **RiskScanner** + **OpsScanner** — kill switch/drawdown/exposição + erros/logs recorrentes.
3. **Jean Grey → MemoryScanner** — passa a **propor** (vault + padrões de decisão).
4. **ExternalResearcher** — WebSearch/WebFetch + GitHub (changelog/CVEs) + MCPs financeiros (LSEG/bigdata) para técnicas de trading.
5. **Loop de medição** (baseline antes/depois) + KPI do departamento.
6. UI: filtrar por fonte/scanner; aba "Pesquisa externa".

Guard-rails: scanners **read-only/fail-silent**; humano aprova; **nunca** auto-merge nem toca `settings.py`/kill switch (L1-L4 + deny rules).

---

## 5. Arquivos-chave
- Conselho: `src/agents/{beast,galactus,mekka,jean_grey}.py` (+ novos scanners no épico).
- Orquestração: `Mekka._beast_proposals` → generalizar para agregar todos os scanners.
- API: `src/dashboard/server.py` (rotas agrupadas em `_register_*_routes`; endpoints improvements/jean/system).
- Fila/PR: `src/services/{improvement_queue,pr_tracker}.py` (`enqueue_brief`, `set_pr`, `approve_pr`, `mark_merged`).
- UI: `src/dashboard/static/{app.js,index.html,style.css}` (`_imprLoad/_imprRender/_imprScan/_imprRenderKanban`, abas, grafo neural).
- Office novo: `src/dashboard/static/office_v4/` (servido em `/office-v4/`).
- Runtime control: `src/runtime_controller.py`. Telegram: `src/services/telegram_{alerter,inbound}.py`.

## 6. Health check
```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN
curl -s localhost:8787/api/system/status
curl -s "localhost:8787/api/improvements?fresh=1" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d.get('recommendations',[])),'recs')"
curl -s localhost:8787/api/jean/graph | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['total_notes'],'notas',d['total_links'],'links')"
```

## 7. Backlog (depois do épico de melhoria contínua)
- **Wiring de dados reais no Office v4** (hoje usa mock do protótipo: tickers/P&L/sinais/eventos).
- **server.py passo 2**: extrair handlers para módulos por domínio (mixins) — reduzir as 6,4k linhas.
- i18n EN completo (baixo valor — operador usa PT).
- Verificação visual de tudo (preview do ambiente estava quebrado).

**Fim do handoff.**
