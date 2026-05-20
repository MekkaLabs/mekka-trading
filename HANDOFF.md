# 🤝 Mekka Trading — Handoff para próximo chat

> **Data**: 2026-05-20
> **Branch**: `main` @ `f898d3c` (sincronizada com `origin/main`)
> **Estado do sistema**: ✅ rodando em **Bybit testnet LIVE mode** com Vision (Anthropic Claude) ativo
> **Próximo chat**: cole este arquivo como contexto inicial.

---

## 1. Como o sistema está rodando agora

### Processo
- **PID 87136** rodando `/run.py --dashboard` há ~1h
- Working dir: `/Users/gustavovicente/Documents/Mekka-Trading`
- Python: `.venv313/bin/python` (Python 3.13)
- Dashboard: http://localhost:8787
- Log live: `/tmp/mekka_dashboard.log`

### Configuração ativa (`.env`)
```bash
ACTIVE_EXCHANGE=bybit
BYBIT_API_KEY=<presente>
BYBIT_API_SECRET=<presente>
BYBIT_TESTNET=true   # implícito via is_mainnet=False
PAPER_TRADING=false
LIVE_TRADING_CONFIRMED=true
TRADING_ASSETS=BTC
MAX_POSITION_SIZE_PCT=0.005   # 0.5%
MAX_LEVERAGE=2
ANTHROPIC_API_KEY=<presente>
OPENAI_API_KEY=(vazio)        # OK, fallback usa Anthropic
```

### Bug ambiental crítico para lembrar
> O shell tinha `ANTHROPIC_API_KEY=""` vazio sobrepondo o `.env` (vindo do Claude for Desktop). Para subir o servidor sempre use:
> ```bash
> env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY nohup .venv313/bin/python run.py --dashboard > /tmp/mekka_dashboard.log 2>&1 &
> ```

### Endpoints saudáveis (testar antes de qualquer coisa)
```bash
curl -s http://localhost:8787/api/env
# {"exchange": "bybit", "network": "testnet", "paper_trading": false, "live_confirmed": true, "mode": "testnet"}

curl -s http://localhost:8787/api/overview | python3 -m json.tool
# Mostra total_signals, total_trades, trading_mode etc.
```

---

## 2. Commits desta sessão (no `main`)

| Commit | Tema |
|---|---|
| `f898d3c` | docs(obsidian+env): vault overhaul + Beast docs + ADR Index + wikilink normalization |
| `adfa0ba` | feat(dashboard): Force Execute opt-in + Beast/Cyclops on the office roster |
| `7c0f9b9` | merge: integrate Bybit testnet readiness branch into main |
| `673e241` | codex: bybit testnet sandbox routing (snapshot codex) |
| `ad3c03d` | feat(stress-test): scenario injector + 25-case runbook for paper-on-testnet |
| `6e47109` | feat(symbols): MarketRegistry centralises symbol normalisation + Bybit integration test |
| `57e79ac` | chore: untrack runtime data (SQLite DB + dashboard snapshots) |
| `f898d3c↑` | (...e mais 5 commits intermediários) |

---

## 3. 🎯 BACKLOG PRIORIZADO (o que o operador pediu + recomendações)

### 🔴 P0 — Bugs visíveis que afetam uso imediato

#### P0.1 — Trading Mode panel "sumiu" (item d)
**Sintoma**: operador reportou que o painel desapareceu, mas o código tem ele em `data-page="overview settings"`.
**Hipóteses**:
- localStorage `mekka_widget_prefs_v1` tem `sec-trading-settings: false` (operador desligou via widget customizer).
- Cache do browser servindo `app.js` antigo (anterior ao commit `9009b34`).
- CSS ocultando após o merge.
**Como reproduzir**: abrir http://localhost:8787 em aba anônima e observar.
**Fix candidato**:
- Hard-clear localStorage no boot do dashboard (operator override).
- Adicionar botão "Reset widget prefs" visível no header.

#### P0.2 — Live trade chart não aparece (item c)
**Arquivo**: `src/dashboard/static/index.html` seção `sec-live-trading` + `src/dashboard/static/vendor/lightweight-charts.standalone.production.js`.
**Investigar**:
- Console do browser (F12 → Network tab) — chart vendor lib carrega?
- WebSocket `/ws/live` está recebendo dados?
- Função `_ensureLiveChartBooted()` em `app.js` está sendo chamada quando `pageKey === 'live'`?

#### P0.3 — Menu Live primeiro (item c)
**Arquivo**: `src/dashboard/static/index.html` linha ~30-87 (page-nav-btn order).
**Fix**: mover `data-page="live"` para a primeira posição do nav.

#### P0.4 — Modo claro quebrado (item d)
**Onde**: `src/dashboard/static/style.css` (variáveis `--bg`, `--text` etc.) e `app.js` `theme-toggle`.
**Investigar**: theme="light" sobrescreve apenas algumas variáveis CSS?

#### P0.5 — Tradução horrível (item d)
**Arquivo**: `src/dashboard/static/i18n.js`
**Status**: provavelmente dicionário incompleto ou strings hardcoded espalhadas.
**Fix**: auditoria completa de strings + completar dicionário pt-BR.

#### P0.6 — Sprites menu Agents ≠ Office 2 (item f)
**Onde**:
- Menu Agents: `src/dashboard/static/app.js` função `_renderAgentRoster()` (procurar por `agents-roster`).
- Office v2: `src/dashboard/static/office_v2/sprites.jsx`.
**Fix**: unificar via import compartilhado OU duplicar palette/overlay no menu Agents.

---

### 🟠 P1 — Funcionalidade nova crítica

#### P1.1 — Menu de operações manuais (item e)
**Especificação**:
- Nova aba `data-page="manual"` no nav, ao lado de "Live".
- Form com: símbolo (dropdown), side (LONG/SHORT), entry price, SL, TP, leverage, size_pct.
- Botão "Pedir parecer dos robôs" — chama `/api/trade/analyze` com os params e mostra:
  - Veredito do Batman (aprovado/rejeitado + motivos)
  - Vision sentiment sobre os params do operador
  - SL/TP que Vision sugeriria
  - Equity disponível
- Botão "Executar" — chama `/api/trade/execute` com os params do operador (não da rec).
- Reusa o Force Execute opt-in já implementado.

**Arquivos a criar/editar**:
- `index.html` — nova seção `sec-manual-trade`
- `app.js` — `_bootManualTrade()` + `_mkManualTradeRequest()`
- `style.css` — `.manual-trade-form`
- `server.py` — endpoint `/api/trade/manual-analyze` (vs `/api/trade/analyze` que usa Vision)
- Telegram: comando `/manual <side> <symbol> <entry> <sl> <tp> <leverage>` opcional

**Tempo estimado**: 4-6h.

---

### 🟡 P2 — Novos agentes (item a + b)

#### P2.1 — Jean Grey — Memory Master (item b, prioridade alta)
**Papel**: Mestre do segundo cérebro + memória de longo prazo dos agentes.

**Responsabilidades**:
1. **Vault Obsidian** — auto-organize, auto-link, sync com `docs/stories/` automaticamente.
2. **Wikilink validation** — detecta links quebrados, sugere reconexões.
3. **Note duplicates detection** — propõe consolidação de notas redundantes.
4. **Memory para outros agentes** — quando Vision/Batman/Iron Man precisam de contexto histórico, Jean Grey serve.
5. **Trabalha com Beast** — Beast propõe melhorias, Jean Grey documenta no vault (ADRs, lessons learned).
6. **DecisionMemory (Story 249)** — Jean Grey é a interface high-level sobre o DecisionMemory existente.
7. **Embeddings** — usar `text-embedding-3-small` (OpenAI) ou Anthropic equivalente para detectar notas semanticamente relacionadas.

**Arquivo a criar**: `src/agents/jean_grey.py` (~300-500 linhas)
- Lê `docs/obsidian/` recursivamente
- Mantém um índice de embeddings em `data/jean_grey_index.parquet`
- Roda diariamente (cron via NickFury monitor cycle) ou on-demand via Telegram `/jean`
- Emite eventos `MEMORY_UPDATED`, `MEMORY_SUGGESTION`, `VAULT_HEALTH_REPORT`

**Trabalho conjunto com Beast**:
```
Beast → analisa sistema → emite proposta
   ↓
Jean Grey → documenta proposta no vault como ADR draft
   ↓
operador revisa → aprova ou rejeita
   ↓
Jean Grey → marca status no ADR (proposta → aceita/rejeitada)
   ↓
Beast → re-analisa com a decisão no histórico
```

**Sprite no roster**: Phoenix red + telekinetic aura (gold particles overlay).

**Tempo estimado**: 8-12h.

#### P2.2 — Iceman / Bobby Drake — On-Chain Data Specialist (item a)
**Papel**: especialista em dados direto da blockchain.

**O que faz**:
- Whale tracking (transações grandes em endereços conhecidos)
- DeFi liquidity flows (Uniswap, Curve, Aave)
- On-chain volume vs CEX volume (divergência = sinal)
- Mempool monitoring (gas price spikes = stress)
- Stablecoin movements (USDT/USDC mint/burn)
- Onchain TVL changes

**Stack proposto**:
- **Etherscan/BscScan API** — endereços + transações
- **Dune Analytics API** — queries on-chain
- **Glassnode API** — métricas agregadas (paid)
- **Alchemy/Infura** — RPC direto se precisar de dado granular

**Diferença vs Black Panther atual**:
- Black Panther = "Onchain Intelligence" mas hoje é stub. Iceman seria a implementação real OU Black Panther é renomeado para algo macro/social.

**Sprite no roster**: blue/cyan + ice overlay.

**Tempo estimado**: 6-10h (depende de quais APIs free vs paid).

#### P2.3 — Outros agentes sugeridos (priorize você)

| Codinome | Papel | Por quê |
|---|---|---|
| **Mystique** | Adversarial Testing / Red Team | Tenta quebrar o sistema com inputs maliciosos, detectar vulnerabilidades, testar gates. Complementa cybersec review. |
| **Magneto** | Macroeconomic Strategist | Fed/ECB rates, DXY, gold, equities correlation. Hoje Doctor Strange só faz probabilidades macro genéricas. |
| **Storm** | Sentiment Lead (multi-source) | Twitter, Reddit, Telegram channels, news beyond CryptoPanic. Doctor Strange hoje só consome CryptoPanic. |
| **Forge** | Indicator Lab | Custom technical indicators, backtest de indicadores próprios. Hoje Vision usa só RSI/EMA/MACD/ATR built-in. |
| **Cable** | Future Scenario Modeling | Predictive scenarios (e.g. "se Fed cortar 25bps em 30 dias, BTC tende a..."). |
| **Bishop** | Compliance & Audit | Verificações regulatórias (KYC checks, wash trading detection, tax reporting). |
| **Gambit** | Arbitrage Hunter | Detecta arbitragem entre Bybit/Binance/Hyperliquid via CCXT. |

> Recomendação: **comece com Jean Grey + Iceman**. Os outros são úteis mas dão diminishing returns. Mystique vale como projeto de cybersec (ver P3.2 abaixo).

---

### 🔵 P3 — Hardening & Polimento

#### P3.1 — Cybersecurity review completo (item a)
**Áreas a auditar**:

| Vetor | Hoje | Risco |
|---|---|---|
| **Dashboard auth** | `X-Mekka-Token` header opcional, sessions reset cada restart | Operador anônimo via LAN pode operar |
| **API key storage** | `.env` em filesystem plain | Backup de filesystem expõe tudo |
| **CSP / CORS** | `connect-src` permissivo para HL + Binance | Browser pode fazer side-channel requests |
| **Rate limit** | CCXT tem rate limit; dashboard não | DoS via /api/positions em loop |
| **WebSocket auth** | `_authorize_ws_origin` rejeita só Origin não-confiável | Token não obrigatório no WS |
| **Audit log integrity** | NDJSON append-only, HMAC verificável (Story 007) | Operador local pode editar arquivo direto |
| **Force Execute trail** | Loga WARNING com env state | OK, mas precisa alertar via Telegram em produção |
| **Kill switch file** | `data/.kill_switch` em filesystem | Operador pode deletar manualmente sem audit |
| **Secrets em logs** | Sanitizado em `summary()` | Logs do `aiohttp.ClientSession` podem vazar URLs com query strings de auth |

**Plano sugerido**:
1. **Token obrigatório em todos os POST /api/** (não opcional).
2. **`MEKKA_DASHBOARD_SECRET`** no `.env` para session signing (hoje "not set").
3. **Audit log assinado HMAC** com chave rotativa.
4. **Telegram alert** quando Force Execute é usado.
5. **`scripts/cybersec_audit.py`** — varre código procurando padrões inseguros.

**Tempo estimado**: 8-12h. Pode virar uma série de ADRs.

#### P3.2 — Mystique como agente Red Team (item a, complemento)
Agente que **automatiza** testes de cybersec:
- Tenta XSS via campos do dashboard
- Tenta SQL injection nos params de API
- Tenta auth bypass no WebSocket
- Tenta race condition em `/api/trade/execute` (duplo POST)
- Tenta forçar Force Execute em mainnet (deve falhar)
- Reporta vulnerabilidades encontradas

#### P3.3 — Sync automático stories ↔ vault (`scripts/sync_obsidian.py`)
- Lê `docs/stories/*.md`
- Atualiza `Stories do Projeto.md` automaticamente
- Detecta stories órfãs (sem nota no vault)
- Detecta notas que referenciam stories inexistentes

#### P3.4 — Refactor `server.py` (4.971 linhas → routers por domínio)
- `routes/trading.py` — Trade Now, execute, positions, close
- `routes/risk.py` — kill switch, gates, drawdown
- `routes/reports.py` — daily, weekly, monthly
- `routes/ws.py` — WebSocket handlers
- `routes/admin.py` — settings, env, mode

#### P3.5 — Refactor `nick_fury.py` (2.225 linhas)
- Separar `run_main_cycle` e `run_monitor_cycle` em módulos
- Extract `_execute_recovery_plan` para `wolverine_executor.py`

#### P3.6 — ADRs retroativos
Decisões grandes sem ADR formal:
- LangGraph adoption (Story 126)
- MoA Vision (Story 131)
- Adaptive Layer-1 Routing (Story 135)
- DecisionMemory (Story 249, codex M40)
- CycleCheckpoint (Story 251, codex M40)
- Beast Continuous Improvement (Story 248, codex M40)
- Force Execute escape hatch (M22.1, esta sessão)

---

## 4. 📚 Documentação relevante

| Doc | Quando consultar |
|---|---|
| `docs/obsidian/Home.md` | Estado consolidado do projeto |
| `docs/obsidian/30 - Resources/Decisoes Tecnicas/ADR Index.md` | Mapa de todos os ADRs |
| `docs/obsidian/30 - Resources/Runbooks/Runbook - Bybit Testnet Setup.md` | Como subir Bybit testnet do zero |
| `docs/obsidian/30 - Resources/Runbooks/Runbook - Stress Test Cenarios Papernet.md` | 25 cenários para testar empiricamente |
| `docs/obsidian/60 - Daily/2026-05-20.md` | Log da última sessão |
| `docs/obsidian/20 - Areas/Agentes IA/_Agentes Index.md` | Roster atual (17 agentes) |
| `docs/obsidian/30 - Resources/Referencias Externas/Stories do Projeto.md` | 79 stories, organização por milestone |

---

## 5. 🛠️ Ferramentas operacionais

### `scripts/stress_inject.py` — Stress test injector
```bash
python3 scripts/stress_inject.py --list

# Cenários disponíveis:
python3 scripts/stress_inject.py kill-switch-engage --reason "test"
python3 scripts/stress_inject.py fake-signal --side long --symbol BTC --entry 76000
python3 scripts/stress_inject.py close-all-paper
python3 scripts/stress_inject.py mode-switch aggressive
python3 scripts/stress_inject.py skew-check
python3 scripts/stress_inject.py telegram-flood --count 10
python3 scripts/stress_inject.py drawdown-alert --pct 15
python3 scripts/stress_inject.py market-event-marker --label whatever
```

### `scripts/obsidian_normalize.py` — Vault normalizer
```bash
python3 scripts/obsidian_normalize.py --dry-run   # preview
python3 scripts/obsidian_normalize.py             # apply
```

### `scripts/build_office_v2.mjs` — Office v2 bundle
```bash
npm run build:office-v2   # gera office_v2/office_v2.bundle.js
```

---

## 6. ⚠️ Gotchas conhecidos (NÃO esquecer)

1. **Não suba o servidor com `python run.py --dashboard` direto** se `ANTHROPIC_API_KEY=""` ou `OPENAI_API_KEY=""` estão na env do shell. Use `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY ...`.

2. **Bybit testnet bloqueia geo (Brasil)**. Operador resolveu uma vez, pode bloquear de novo. Plano B = Hyperliquid testnet.

3. **`PAPER_TRADING=false` está ativo**. Em testnet é seguro, mas se trocar `ACTIVE_EXCHANGE=hyperliquid` SEM trocar `HYPERLIQUID_NETWORK=testnet`, vai pra HL mainnet.

4. **Universo restrito a BTC**. `TRADING_ASSETS=BTC` no `.env`. Se quiser ETH/SOL, edite e reinicie.

5. **AVAX não tem perp linear em Bybit testnet**. Se incluir AVAX em `TRADING_ASSETS`, vai aparecer `SYMBOLS_SKIPPED` no audit.

6. **12 BOOTs em 58h** — instabilidade percebida (codex testou muito). Investigar se há crash silencioso em produção.

7. **`MEKKA_DASHBOARD_SECRET` not set** — log warn no boot. Sessions resetam cada restart.

8. **Telegram dedup window** — se um alerta cair, esperar 5 min antes de testar de novo.

9. **`/api/env` retorna 404 se servidor for de antes do commit `2d1c898`**. Garante que estamos no `main` atual.

10. **Cyclops monitora SL/TP em loop de 5 min** — não reage instantaneamente. Para fechar rápido, use `close-all-paper` ou o botão "Fechar" no painel positions.

---

## 7. 🎬 Sequência recomendada para o próximo chat

**Fase 1 — Validação visual (10 min)**:
1. Abrir http://localhost:8787 em aba anônima do browser
2. Verificar badge BYBIT · TESTNET no header
3. Identificar quais dos bugs (P0.1–P0.6) reproduzem
4. Capture screenshots dos defeitos

**Fase 2 — P0 cleanup (4-6h)**:
- Fixes diretos nos 6 bugs P0
- Cada fix em commit separado para review granular

**Fase 3 — P1.1 Manual Trading (4-6h)**:
- Implementar menu de operações manuais
- Reusa Force Execute já implementado
- Validar com 1-2 trades reais em testnet

**Fase 4 — P2.1 Jean Grey (8-12h)**:
- Implementar agente memory master
- Integrar com Beast (proposal → ADR draft pipeline)

**Fase 5 — P2.2 Iceman + P3.1 Cybersec (12-15h)**:
- Pode rodar em paralelo
- Cybersec primeiro se houver suspeita de exposição

---

## 8. 📞 Sinais de saúde a verificar SEMPRE no início

```bash
# 1. Processo está rodando?
lsof -nP -iTCP:8787 -sTCP:LISTEN

# 2. Env ok?
curl -s http://localhost:8787/api/env

# 3. Overview ok?
curl -s http://localhost:8787/api/overview

# 4. Vision não está em fallback?
curl -s 'http://localhost:8787/api/signals?limit=3' | python3 -c "
import json, sys; d=json.load(sys.stdin)
for s in d[:3]: print(f'{s[\"timestamp\"][:19]} {s[\"action\"]} fallback={s.get(\"fallback\",False)}')
"
# Se 'fallback=True' em todos → Vision quebrado, debugar LLM

# 5. Posições reais batem com Bybit?
curl -s http://localhost:8787/api/positions
```

---

## 9. ⚠️ Restart do servidor (caso precise)

```bash
# 1. Achar PID
lsof -nP -iTCP:8787 -sTCP:LISTEN

# 2. Stop graceful (substitua PID)
kill -TERM <PID>; sleep 4; kill -9 <PID> 2>/dev/null

# 3. Subir com env limpa (CRUCIAL)
cd /Users/gustavovicente/Documents/Mekka-Trading
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  nohup .venv313/bin/python run.py --dashboard \
  > /tmp/mekka_dashboard.log 2>&1 &

# 4. Aguardar 10s e validar
sleep 10
curl -s http://localhost:8787/api/env
tail -5 /tmp/mekka_dashboard.log
```

---

## 10. 📝 Texto-mensagem inicial para o próximo chat

> Estou continuando o desenvolvimento do Mekka Trading. O sistema está rodando em Bybit testnet LIVE mode no `main` @ `f898d3c`. Leia `HANDOFF.md` na raiz do repo para contexto completo. Quero atacar os bugs P0 (Trading Mode sumiu, live chart não aparece, sprites do menu agents) primeiro, depois o menu de operações manuais (P1.1), e depois Jean Grey (memory master). Estado atual + checklist saudável no doc.

---

**Fim do handoff.**

Boa sorte na próxima sessão. Cada item do backlog tem caminho claro e arquivos identificados — não tem mistério no que falta.
