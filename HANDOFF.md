# 🤝 Mekka Trading — Handoff para próximo chat

> **Data**: 2026-05-20 (sessão 3 — modo automático noturno)
> **Branch**: `main` @ `cdb8cb9` — **19 commits ahead de `origin/main`**, nada pushed (push é do @devops)
> **Estado**: ✅ rodando em **Bybit testnet LIVE mode** (PID 70405, dashboard http://localhost:8787)
> **Próximo chat**: cole este arquivo como contexto inicial.

---

## 1. Como subir / health check

```bash
# SEMPRE com env limpa (o shell tem ANTHROPIC/OPENAI vazios que sobrepõem o .env)
lsof -ti tcp:8787 | xargs kill -9 2>/dev/null
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  nohup .venv313/bin/python run.py --dashboard > /tmp/mekka_dashboard.log 2>&1 &
# aguardar ~25s (o boot roda 1 ciclo completo de agentes que segura o event loop)
curl -s http://localhost:8787/api/system/status
curl -s http://localhost:8787/api/improvements/pr-status
```

`.env` ativo: `ACTIVE_EXCHANGE=bybit`, `BYBIT_TESTNET=true`, `PAPER_TRADING=false`, `LIVE_TRADING_CONFIRMED=true`, `TRADING_ASSETS=BTC`, `MAX_POSITION_SIZE_PCT=0.005`, `MAX_LEVERAGE=2`, **`MAX_TOTAL_NOTIONAL_USD=100`** (cap de risco — ver gotcha #2).

---

## 2. ✅ Entregue nesta sessão (commits após `dca7131`)

```
cdb8cb9 feat(dashboard): item e — help tooltips em todos os painéis (+responsável)
0ea9a89 feat(office): zoom da cena width+height aware (rumo ao no-scroll)
19754b1 fix(charts): gráficos Live/market em branco — shim lightweight-charts v4/v5
fa157bb fix(manual-trade): orientação acionável quando Batman bloqueia o trade
3de043e fix(improvements): botão Aceitar travava — enfileira do rec, sem re-rodar conselho
4924386 feat(dashboard): system on/off/reboot + roster do office + pipeline melhorias→PR
```

### Power on/off/reboot (control plane sempre vivo)
- `src/runtime_controller.py` — `RuntimeController` controla o loop do Nick Fury. `stop()` cancela o loop → **para trading e gasto de tokens (sem chamadas LLM)**. Dashboard nunca desliga.
- `run.py` — `--dashboard` cria o controller, `start()`, e roda o dashboard com ele injetado; `--dashboard-only` não auto-inicia.
- `server.py` — `GET /api/system/status`, `POST /api/system/{start,stop,reboot}` (stop/reboot exigem `{"confirm":"STOP"/"REBOOT"}`).
- Topbar: pill **SISTEMA LIGADO/DESLIGADO** + botões Ligar/Desligar/Reboot (poll 5s, com retry resiliente ao boot). **Verificado na UI.**

### Office (item h)
- 4 estações novas em L4 (`scene.jsx`): **mekka, galactus, beast, jeangrey** (Conselho de Melhoria). 24 agentes, 24 estações, sem sprites empilhados no centro. **Verificado.**

### Overview (itens a + b)
- `.overview-office-row` grid `2fr/1fr` → office + Trade Mode lado a lado (empilha ≤1100px).
- Central de Comandos (`.cmd-center-panel`) reusando handlers (trade manual, Modo Deus, kill switch, modo).

### Melhorias → dev → PR (itens d/#5/#6)
- Aceitar grava `docs/improvement-queue/IMP-<id>.md` (brief com premortem do Galactus + critérios). `src/services/improvement_queue.py`.
- `src/services/pr_tracker.py` + `GET /api/improvements/pr-status` + `POST /api/improvements/approve-pr` (`{rec_id, pr_number, confirm:"APPROVE", merge?}`). **Merge real só com `merge:true`** — por padrão só registra a aprovação (segurança; merge é ação do @devops).
- Painel `/Melhorias` mostra ciclo Fila→Em dev→PR aberto→Mergeado + botão Aprovar PR.

### Bugs corrigidos
- **Aceitar travava** (`3de043e`): backend rodava `Mekka().run()` (~10s) a cada accept; agora o frontend manda o `rec` e o backend enfileira direto (0.05s). **Testado.**
- **Executar trade** (`fa157bb`): não era bug — Batman rejeita pelo cap `$100` do operador (2% × lev 2 = $400 notional). Funciona via **Modo Deus** no testnet. Adicionado guia acionável + destaque do Modo Deus quando bloqueado.
- **Gráfico Live em branco** (`19754b1`): o bundle vendorizado é **lightweight-charts v5** (sem `addCandlestickSeries`); código usava API v4. Shim `_lwcAddCandle/_lwcAddHistogram/_lwcAddLine` usa `addSeries(Type,opts)` na v5. **Verificado: shim cria as 3 séries.** (afeta Live e market chart)
- **Tooltips (item e)** (`cdb8cb9`): `HELP_TIPS` 18→43 painéis, cada um com o herói **responsável**; `enhanceTitlesWithHelp()` roda também no fim do boot.
- **Fixes anteriores no commit `4924386`**: `_hl_prices`→`_mark_prices` (AttributeError no painel live) e TDZ `_tsSummaryTimer` (quebrava o widget "Resumo de Hoje" no boot).

---

## 3. 🎯 BACKLOG RESTANTE

### #10 — Memória ainda "ruim" (UX)
- O painel **funciona** (`/api/memory/stats`, `/api/working-memory`, `/api/jean/health-report` respondem), mas está quase vazio no testnet (poucos trades resolvidos), o que dá sensação de "ruim".
- **Plano**: enriquecer a página de Memória com 3 blocos claros e explicados: (1) **Memória Episódica** (já existe — win-rate por símbolo/ação + vetos do Batman), (2) **Memória de Trabalho** (`/api/working-memory` — hoje não exibida na página), (3) **Saúde do Vault / Jean Grey** (`/api/jean/health-report` — broken links, órfãs, dups). Melhorar o empty-state explicando o que cada memória é e quando se forma. Arquivos: `app.js` (`loadMemory`/`bootMemory` ~5095), `index.html` (`sec-memory`), `style.css`.

### #11 — Office completo sem scroll na Visão Geral (PARCIAL)
- **Feito**: zoom da cena agora width+height aware (`office_v2/index.html`, commit `0ea9a89`).
- **Falta (fix completo)**: o iframe embute a **página inteira** do office (header + cena + roster + audit stream), por isso ainda pode rolar. Solução recomendada: **modo embed** — `/office-v2/?embed=1` que renderiza **só a cena** (esconde roster/audit/header extra via classe no `<body>` do office, controlada por query param em `office_v2/app.jsx`), e o dashboard passa a usar `src="/office-v2/?embed=1"` no `#office-v2-frame`. Ajustar `.overview-office-row #office-v2-frame` (CSS) com `aspect-ratio` da cena. **Precisa de iteração visual.** Brief: `docs/improvement-queue/IMP-office-full-noscroll.md`.

### #12 — Backlog visual restante
- **f — UX da página de Configurações** (`sec-settings` widget customizer + `sec-filters`): hoje só checkboxes crus. Agrupar por categoria, busca, presets, preview.
- **d — Tema claro round 2 + i18n completa**: tema claro tem `body[data-theme="light"]` mas faltam regras p/ componentes novos (manual, melhorias, office, command center, sys-power). i18n: muitas strings ainda hardcoded fora do dicionário.

### 🟣 Improvement Council → Telegram (do handoff anterior, ainda aberto)
- Enviar propostas do Mekka ao Telegram para aprovar/reprovar (`telegram_alerter.py` outbound + `telegram_inbound.py` comandos `/melhorias`,`/aprovar`,`/reprovar`).

### 🔵 Consumidor do pipeline de melhorias (fecha o ciclo #6)
- Falta o **consumidor**: sessão do Claude Code (manual/headless `claude -p`/cron) que lê `docs/improvement-queue/`, roda o SDC do AIOS (@sm→@po→@dev→@qa→@devops) e registra o PR via `pr_tracker.set_pr(...)`. Aí o painel mostra o PR pronto para aprovação. **Nunca auto-merge em main; nunca tocar `settings.py`/kill switch.**

---

## 4. ⚠️ Gotchas

1. **Preview MCP instável neste ambiente**: o `Claude_Preview` cai a cada eval/navegação (largura travada ~474px, derruba conexão no resize). Verificações visuais ficaram limitadas — itens #11/#12/#10 precisam de checagem visual no navegador real do operador (hard refresh **Cmd+Shift+R** para pegar app.js/CSS novos).
2. **Cap de notional $100** (`MAX_TOTAL_NOTIONAL_USD` no `.env`) vs default 2% → Batman rejeita trades normais. É **decisão de risco do operador** (não alterado). Para executar: reduzir tamanho/lev OU usar **Modo Deus** (testnet). Janela viável é apertada (mín. Bybit 0.001 BTC ~$77 vs cap $100).
3. **lightweight-charts é v5** no vendor — qualquer código novo de chart deve usar os helpers `_lwcAddCandle/_lwcAddHistogram/_lwcAddLine` (não `addCandlestickSeries`).
4. **`PAPER_TRADING=false`** em testnet (seguro). Modo Deus tem hard-block em mainnet; kill switch nunca é ignorável.
5. **Office dev mode** (`USE_BUNDLE=false`): edita `.jsx`/index.html e reflete no reload, sem rebuild. Para produção, `npm run build:office-v2`.
6. **Servidor**: mudanças em `.py` exigem restart; mudanças em estáticos (`app.js`/css/office) refletem no reload do navegador.
7. **18 commits ahead** de origin, nada pushed.

---

## 5. 🛠️ Endpoints novos desta sessão
```
GET  /api/system/status            # {state,running,uptime_seconds,cycles,paper_trading,mode,last_error}
POST /api/system/start
POST /api/system/stop              # body {"confirm":"STOP"}
POST /api/system/reboot            # body {"confirm":"REBOOT"}
GET  /api/improvements/pr-status   # {rec_id:{dev_state,pr:{...}}}
POST /api/improvements/approve-pr  # body {rec_id,pr_number,confirm:"APPROVE",merge?}
POST /api/improvements/decision    # body {id,status,rec?}  ← agora aceita rec p/ enfileirar
```

---

## 6. 📝 Mensagem inicial sugerida para o próximo chat
> Continuando o Mekka Trading no `main` @ `cdb8cb9` (Bybit testnet LIVE). Leia `HANDOFF.md`. Bugs de aceitar/trade/gráfico-live já corrigidos. Quero terminar: **#11** office sem scroll (modo embed `?embed=1` mostrando só a cena), **#10** enriquecer a página de Memória (episódica + trabalho + vault), e **#12** UX de Configurações (f) + tema claro/i18n (d). O preview do ambiente está instável — valide visualmente no navegador. Mantenha commits entre cada implementação; nunca toque nos safety gates.

---
**Fim do handoff.** Cada item restante tem arquivos e caminho identificados.
