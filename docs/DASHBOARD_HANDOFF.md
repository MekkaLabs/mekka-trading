# Mekka Trading Dashboard — Handoff (autoritativo)

> Snapshot completo do estado atual do dashboard. Para um relatório
> fotográfico com métricas e roadmap histórico ver
> `docs/DASHBOARD_REPORT.md`. Para mudanças cronológicas ver `CHANGELOG.md`.
> Substitui `dashboard_handoff.md` e `dashboard_handoff_next_chat.md`
> (mantidos como referência histórica).

---

## 1. Visão geral

Dashboard web em tempo real que dá observabilidade completa ao runtime
Mekka Trading (heróis L1–L4) e ao mercado spot (Binance). Suporta replay
forense, fila de incidentes priorizada por severidade, kill switch
operacional, PnL/equity com benchmark, posições live (Hyperliquid) e
uma cena pixel-art React (Office v2).

Stack:

- **Backend**: `aiohttp` (Python 3.11+), `SQLAlchemy 2.x` async, SQLite local.
- **Frontend**: HTML/CSS/JS sem framework, com Chart.js (séries) e
  TradingView Lightweight Charts (mercado) — ambos com fallback vendored.
- **Office v2**: app React standalone (cena pixel) com Babel-standalone OU
  bundle esbuild pré-compilado.
- **Persistência**: SQLite (`data/mekka.db`) + snapshots JSON em
  `data/dashboard_snapshots/` com rotação automática.
- **Real-time**: WebSocket `/ws` (broadcast 2s) + polling REST com
  cadência adaptativa por painel.
- **Alertas outbound**: Slack/Telegram via webhook dispatcher com dedup.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        run.py (entrypoint)                          │
│   ┌──────────────────────┐         ┌──────────────────────────┐     │
│   │  Nick Fury runtime   │  TG     │  MekkaDashboardServer    │     │
│   │  (signals → trades)  │ ◄─────►│  aiohttp + WS + REST     │     │
│   └─────────┬────────────┘         └──┬────────┬──────────────┘     │
│             │ writes                   │ reads │ outbound           │
│             ▼                          ▼       ▼                    │
│   SQLite (signals, trades,     snapshots/    Slack / Telegram       │
│   audit_log, daily_pnl)        *.json        webhooks               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layout de arquivos

```
src/dashboard/
├── __init__.py
├── server.py                 # MekkaDashboardServer + handlers (2.044 linhas)
├── auth.py                   # tokens HMAC-assinados, login/me/logout
├── severity.py               # compute_severity + percentile (puro)
├── validators.py             # is_valid_snapshot/bundle/origin (puro)
├── payload_builders.py       # HERO_LAYER + 7 build_* (puro)
├── replay_helpers.py         # compare/slice/parse_iso_utc (puro)
├── positions_provider.py     # Hyperliquid info.user_state adapter
├── office_v2_endpoints.py    # data shapers para Office v2
├── metrics.py                # descritores Prometheus + render
├── alert_dispatcher.py       # webhooks Slack/Telegram com dedup
└── static/
    ├── index.html            # sidebar + 14 sections
    ├── app.js                # WS client, charts, queue, PnL, auth, etc.
    ├── i18n.js               # strings PT/EN
    ├── style.css             # tema Marvel/Wall Street
    ├── vendor/               # tv.js + lightweight-charts vendored
    └── office_v2/            # React app standalone
        ├── index.html        # bundle-first com fallback Babel-standalone
        ├── mount.js          # entry para esbuild
        ├── office_v2.bundle.js  # gerado por `npm run build:office-v2`
        └── 7 × *.jsx         # sprites, scene, app, etc.

src/persistence/
├── repository.py             # queries (signals, trades, audit, daily_pnl)
└── models.py                 # SQLAlchemy models

run.py                        # CLI: --dashboard / --dashboard-only / --once
scripts/
├── smoke_dashboard.py        # smoke test (sobe app + bate /api/*)
├── build_office_v2.mjs       # esbuild config para Office v2
└── update_sri.sh             # recomputa SRI dos vendored
tests/test_dashboard_replay.py  # pytest + aiohttp.test_utils (~1.578 linhas)
docs/
├── DASHBOARD_HANDOFF.md      # este arquivo
└── DASHBOARD_REPORT.md       # relatório fotográfico
```

---

## 3. Endpoints REST (40 rotas)

### 3.1 Saúde / overview
- `GET /api/health` — liveness (mode, network, time_utc)
- `GET /api/overview` — resumo macro

### 3.2 Tabelas
- `GET /api/signals|trades|audit?limit=N`

### 3.3 Replay e snapshots
- `GET /api/replay?snapshot=NAME`
- `GET /api/replay/snapshots`
- `GET /api/replay/timeseries?limit=N`
- `GET /api/replay/export?start=&end=&start_utc=&end_utc=&format=json|csv`
- `GET /api/replay/compare?a=&b=`

### 3.4 Incidentes
- `GET /api/replay/incident/latest`
- `GET /api/replay/incident/latest/download`
- `GET /api/replay/incidents`
- `GET /api/replay/incident/download?name=`
- `GET /api/incidents/queue?limit=&offset=&q=&tier=`
- `GET /api/incidents/export?limit=&scan=&q=&tier=`
- `GET /api/incidents/detail?snapshot=`

### 3.5 Mercado (Binance Spot)
- `GET /api/market/candles|depth|trades|diagnostics|status`

### 3.6 PnL / Equity
- `GET /api/pnl/series?days=N`
- `GET /api/pnl/summary?days=N`
- `GET /api/pnl/benchmark?days=N&symbols=BTC,ETH` — séries normalizadas (close[i]/close[0])

### 3.7 Trades
- `GET /api/trades/timeline?hours=N` — buckets horários `{filled, paper, rejected, error, skipped, total}`

### 3.8 Posições (Hyperliquid)
- `GET /api/positions` — paper/sem credenciais devolve stub; live usa `Info.user_state`

### 3.9 Kill switch
- `GET /api/killswitch/status`
- `POST /api/killswitch/engage` — body `{confirm: "ENGAGE", reason: "..."}` (auth)
- `POST /api/killswitch/release` — body `{confirm: "RELEASE", operator: "..."}` (auth)

### 3.10 Auth
- `POST /api/auth/login` — body `{password}` → cookie `mekka_session` + token JSON
- `POST /api/auth/logout` — clear cookie
- `GET  /api/auth/me` — `{authenticated, expires_at, subject, login_enabled, shared_secret_enabled}`

### 3.11 Office v2
- `GET /office-v2`, `GET /office-v2/` — index do app React
- `GET /office-v2/*` — assets estáticos (jsx, bundle, mount)
- `GET /api/agents/tasks` — última tarefa por agente (Office v2)
- `GET /api/audit/feed?n=N` — feed formatado `[{t, who, msg}]`

### 3.12 Observabilidade
- `GET /metrics` — Prometheus text format (counters, gauges, p50/p95)

### 3.13 Real-time
- `GET /ws` — broadcast contínuo, Origin allowlist, heartbeat 20s

### Status codes
- `400` input inválido · `401` auth required · `403` origin proibida · `404` recurso ausente · `502` provider upstream falhou · `504` timeout DB/provider

---

## 4. Frontend — sections e estado

| Section | Painel | Cadência refresh |
|---|---|---|
| `sec-live-market` | Market Live (TradingView / Lightweight / SVG) | 3s (market WS para ticks) |
| `sec-killswitch` | Card + modal de confirmação textual + auth state | 5s |
| `sec-replay-player` | Player + compare A/B + download bundle | sob demanda |
| `sec-replay-charts` | Signals/Trades/Alerts+Severity (Chart.js line) | 30s |
| `sec-incident-queue` | Tier filter + search + drawer modal | 30s |
| `sec-pnl` | Equity, daily PnL, drawdown, **benchmark BTC overlay** | 60s |
| `sec-trades-timeline` | Stacked bar (filled/paper/skipped/rejected/error) | 30s |
| `sec-positions` | Hyperliquid live com paper badge + pulse-dot | 3s (live) / 30s (stub) |
| `sec-internals` | Sockets, broadcasts, latency p50/p95, cache, breakers | 5s |
| `sec-metrics` | Mission Metrics macro | WS |
| `sec-office` | Pixel 3D Office canvas (legacy embarcado) | rAF |
| `sec-layers` | Layer Command Map L1–L4 | WS |
| `sec-agents` | Agents Pixel Roster | static |
| `sec-risk` | Batman Risk Heatmap + drilldown | WS |
| `sec-anomalies` | Spider-Man Anomaly Console | WS |
| `sec-signals` / `sec-trades` / `sec-audit` | Tabelas | WS |
| `/office-v2/` | React app standalone (nova janela) | own loop + `/ws` bridge |

### Estado e preferências (`localStorage['mekka_dashboard_prefs_v1']`)
- `marketSymbol`, `marketTimeframe`
- `queueSeverity`, `queueSearch`
- `filterSymbol`, `filterHero`, `filterEvent`, `filterMode` (contains/exact/prefix)
- `pnlWindow`, `tradesTimelineHours`
- `lang` (pt/en), `theme`

### XSS hardening
Todo `innerHTML` passa por `escapeHtml()`. Símbolos, mensagens de audit/LLM/news/exchange tratados como dados não-confiáveis. Content-Security-Policy estrita aplicada via middleware (com `'unsafe-eval'` libertado APENAS no path `/office-v2/` para Babel-standalone).

### Auto-refresh inteligente
`document.visibilitychange` pausa todos os timers quando a aba fica em background. `pos-dot.live` pulsa quando provider Hyperliquid está respondendo; cadência muda para 3s automaticamente.

### Reconexão WS
Backoff exponencial com teto 30s: `min(30000, 1000 × 2^attempts)`.

---

## 5. Persistência

### 5.1 SQLite (`data/mekka.db`)
- `signals`, `trades`, `daily_pnl`, `audit_log` — todos com índice em `timestamp`, `agent`, `event`, `symbol`.

### 5.2 Snapshots em `data/dashboard_snapshots/`
- `latest.json` — sobrescrito 1×/2s (sempre o mais novo)
- `snapshot-YYYYMMDDTHHMM.json` — 1×/min (granularidade do replay)
- `incident-bundle-YYYYMMDDTHHMMSS-µµµµµµ.json` — apenas na **transição "sem kill → com kill"** OU 1×/min enquanto kill ativo (dedup)

### 5.3 Rotação automática
- `MEKKA_SNAPSHOT_RETENTION_MIN` (default `1440` = 24h)
- `MEKKA_INCIDENT_RETENTION` (default `200`)
- Pruning roda 1×/min em thread executor.

### 5.4 Severity score (`severity.compute_severity`)
| Driver | Peso |
|---|---|
| critical_alerts | 50 |
| kill_switch | 35 |
| anomaly_pause | 25 |
| warning_alerts | 15 |
| breached_limits | 4 |
| sla_degraded | 5 |

Cap em 100. Tier: NONE / LOW(>0) / MEDIUM(≥20) / HIGH(≥50) / CRITICAL(≥80).

---

## 6. Segurança

| Vetor | Defesa |
|---|---|
| CSWSH (Cross-Site WebSocket Hijacking) | `_is_origin_allowed` rejeita Origin não-allowlist com 403 |
| Path traversal | Regex estrita `_SNAPSHOT_NAME_RE`, `_BUNDLE_NAME_RE` antes de qualquer leitura |
| Bind exposto na LAN | `--dashboard-host` default `127.0.0.1` |
| XSS via dados externos | `escapeHtml` em todo `innerHTML` + CSP estrita |
| WS slow consumer | `wait_for(send_str, timeout=2)` + close 1011 |
| DB hangs | `wait_for(query, timeout=3)` + cache TTL no payload |
| Mutação não-autorizada | `_auth_middleware`: cookie `mekka_session` (HMAC) OU `X-Mekka-Token` |
| Clickjacking/sniffing | X-Frame-Options=DENY, X-Content-Type-Options=nosniff, Referrer-Policy strict, Permissions-Policy sem camera/mic/geo |
| Kill-switch acidental | confirm literal `"ENGAGE"`/`"RELEASE"` no body + modal textual |
| Drawdown silencioso | `DRAWDOWN_WARNING` ≥5% / `DRAWDOWN_CRITICAL` ≥10% no severity score + webhook |
| Sessão exposta | Cookie HttpOnly + SameSite=Lax + Secure quando HTTPS |
| CDN comprometida | Vendored fallback com SRI no path do fallback CDN |
| Alertas externos | Dispatcher dedup 5min por código (Slack/Telegram) — não spamma canais |

HSTS é emitido só em HTTPS. SRI completa nas CDNs principais (`tv.js`, `lightweight-charts.standalone.production.js`).

---

## 7. Configuração via env

### Operação geral
| Var | Default | Função |
|---|---|---|
| `MEKKA_SNAPSHOT_RETENTION_MIN` | `1440` | Retenção de snapshots por minuto |
| `MEKKA_INCIDENT_RETENTION` | `200` | Retenção de incident-bundles |
| `DASHBOARD_ALLOWED_ORIGINS` | `""` | Origens extra permitidas no WS |
| `MEKKA_DASHBOARD_CSP` | (default seguro) | Sobrescreve CSP |
| `MEKKA_DRAWDOWN_WARN_PCT` | `0.05` | Threshold drawdown WARNING |
| `MEKKA_DRAWDOWN_CRIT_PCT` | `0.10` | Threshold drawdown CRITICAL |

### Auth
| Var | Default | Função |
|---|---|---|
| `MEKKA_DASHBOARD_TOKEN` | `""` | (Legacy) shared-secret em `X-Mekka-Token` |
| `MEKKA_DASHBOARD_PASSWORD` | `""` | Habilita login por senha em `/api/auth/login` |
| `MEKKA_DASHBOARD_SECRET` | random | Chave HMAC do servidor (sessões resetam ao restart se vazia) |
| `MEKKA_DASHBOARD_SESSION_TTL` | `43200` | Duração da sessão em segundos (default 12h) |

### Webhooks
| Var | Default | Função |
|---|---|---|
| `MEKKA_WEBHOOK_SLACK` | `""` | Slack incoming-webhook URL |
| `MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN` | `""` | Bot token (`123:ABC...`) |
| `MEKKA_WEBHOOK_TELEGRAM_CHAT_ID` | `""` | Chat id alvo |
| `MEKKA_WEBHOOK_DEDUP_S` | `300` | Janela de dedup do dispatcher (s) |

### Trading
| Var | Default | Função |
|---|---|---|
| `OPENAI_API_KEY`, `HYPERLIQUID_PRIVATE_KEY`, `HYPERLIQUID_WALLET_ADDRESS`, `HYPERLIQUID_NETWORK`, `PAPER_TRADING`, `CRYPTOPANIC_API_KEY` | — | Vide `.env.example` |

---

## 8. Como rodar

### Dev local (sem auth, sem webhooks)
```bash
cd ~/Documents/Mekka-Trading
.venv/bin/python run.py --dashboard-only
open http://127.0.0.1:8787
```

### Produção paper (auth + webhooks)
```bash
export MEKKA_DASHBOARD_PASSWORD="$(openssl rand -base64 18)"
export MEKKA_DASHBOARD_SECRET="$(openssl rand -hex 32)"
export MEKKA_WEBHOOK_SLACK="https://hooks.slack.com/services/..."
export MEKKA_WEBHOOK_TELEGRAM_BOT_TOKEN="123:ABC..."
export MEKKA_WEBHOOK_TELEGRAM_CHAT_ID="-100..."
.venv/bin/python run.py --dashboard
```

### Expor na LAN (cuidado!)
```bash
.venv/bin/python run.py --dashboard-only --dashboard-host 0.0.0.0
DASHBOARD_ALLOWED_ORIGINS=http://192.168.1.10:8787 \
  .venv/bin/python run.py --dashboard --dashboard-host 0.0.0.0
```

### Office v2 bundle
```bash
npm install   # esbuild + react já no package.json
npm run build:office-v2
open http://127.0.0.1:8787/office-v2/
```

### Testes / smoke
```bash
.venv/bin/pytest tests/test_dashboard_replay.py -v
.venv/bin/python scripts/smoke_dashboard.py
```

### Atualizar SRI dos vendored
```bash
bash scripts/update_sri.sh
```

---

## 9. Cobertura de testes (~1.578 linhas, ~60 cenários)

**Severity & helpers puros**
- `TestComputeSeverity` (5 casos)
- `TestSnapshotNameValidator` / `TestBundleNameValidator` (paramétricos)
- `TestOriginAllowlist` / `TestPercentileHelper`

**Replay**
- `TestReplaySnapshots`, `TestReplaySingle`, `TestReplayExport` (JSON/CSV/UTC)
- `TestReplayCompare` (válido / 400 / 404)

**Incidentes**
- `TestIncidentEndpoints` (latest / download / fallback / baseline=null)
- `TestIncidentLatestBaselineFallback`
- `TestPersistSnapshotDedup` (1 bundle por transição + 1 por minuto)
- `TestSnapshotPruning`

**WebSocket**
- `TestWebSocketOriginCheck` (Origin missing/foreign rejeitados)

**Replay timeseries / queue**
- `TestReplayTimeseries`, `TestIncidentsQueue`

**PnL**
- `TestPnLEndpoints` (series, summary, clamp, 504)
- `TestBenchmarkEndpoint` (normalização close[0]=1.0)

**Trades**
- `TestTradesTimelineEndpoint` (buckets horários, clamp)

**Drawdown alerts**
- `TestDrawdownAlert` (thresholds, exclusivo, score boost)

**Security**
- `TestSecurityHeaders` (headers presentes + override por env)
- `TestAuthMiddleware` (GET aberto, POST 401, POST 200 com token)

**Kill switch**
- `TestKillSwitchEndpoints` (engage/release/status, idempotência, JSON malformado)

**Auth**
- `TestAuthTokens` (issue/verify, garbage, expired, tampered, password constant-time)
- `TestAuthEndpoints` (login, /me anon→authed, wrong password, logout, legacy shared-secret)

**Metrics / Positions / Dispatcher**
- `TestMetricsEndpoint` (formato Prometheus + counter incrementa)
- `TestPositionsStub` + `TestPositionsProvider` (mapping, paper short-circuit, missing addr)
- `TestAlertDispatcher` (dedup window, no targets, only dispatched codes)

---

## 10. Decisões arquiteturais importantes

1. **Snapshot 1×/min**, não 1×/2s — 30× menos arquivos sem perder fidelidade de replay.
2. **Incident bundle dedup por transição** — antes era gerado a cada broadcast (1800/h durante kill ativo); agora 1 na borda + 1/min.
3. **Cache TTL no `_collect_payload`** — 1.5s/0.5s compartilhado entre WS e REST.
4. **TaskGroup no `run.py`** — runtime↔dashboard se cancelam mutuamente.
5. **ClientSession reutilizada** — evita exhaustion de FDs em polling Binance.
6. **Bind default `127.0.0.1`** — operador opt-in para LAN com origin allowlist obrigatória.
7. **Origin allowlist por prefixo scheme://host** — sem porta, facilita dev.
8. **Vendored libs com fallback CDN + SRI** — funciona offline, CDN é safety net com bytes verificados.
9. **Office v2 bundle-first com fallback Babel** — produção corta ~700KB do load.
10. **Webhook dispatcher dedup 5min** — kill switch sustentado não spamma canais.
11. **Auth com cookie HMAC + back-compat token** — múltiplos operadores via login, CI continua via header.
12. **Adaptive refresh por painel** — visibilitychange pausa tudo; provider live (Hyperliquid) muda cadência de 30s→3s automaticamente.

---

## 11. Limitações / dívida técnica

- `server.py` ainda tem ~2.044 linhas — vale dividir handlers em módulos (replay/incidents/market/pnl/killswitch/auth).
- Auth de sessão é single-user (1 senha). Multi-operador real precisa de OIDC/JWT.
- Sem rate-limit; se exposto à internet, recomendável pôr atrás de nginx/caddy.
- Office v2 PnL flash ainda é direção (win/loss) — espera IronMan adicionar `pnl_usd` ao audit `payload`.
- Hyperliquid positions via polling (3s); WebSocket nativo seria mais responsivo.
- Sem backup automático do `data/dashboard_snapshots/` — pruning protege contra crescimento, não contra corrupção.
- `_handle_replay_export` sem range pode ler todos os snapshots em memória (limite implícito é a retenção, ~1440 arquivos).

---

## 12. Roadmap

### Entregue
| # | Item |
|---|---|
| 1 | Severity score + investigation queue + filtros |
| 2 | Replay charts (signals/trades/alerts+severity) |
| 3 | Incident bundle download UI |
| 4 | Equity & PnL panel com cards + drawdown + benchmark BTC |
| 5 | Open Positions provider (Hyperliquid live + adaptive refresh) |
| 6 | Kill-switch UI control com confirmação textual + auth |
| 7 | Drawdown alert no `_build_global_alerts` |
| 8 | Security middleware (CSP/HSTS/X-Frame/Referrer/Permissions) |
| 9 | Métricas Prometheus + painel Internals com p50/p95 |
| 10 | Filtros exato/contém/prefixo |
| 11 | Refator parcial: severity, validators, payload_builders, replay_helpers, positions_provider, office_v2_endpoints, metrics, alert_dispatcher, auth |
| 12 | Office v2 React app instalada + WS bridge + esbuild bundle |
| 13 | SRI nos CDNs principais + script de manutenção |
| 14 | Auth com senha + cookie HMAC-assinado |
| 15 | Webhook outbound (Slack/Telegram) com dedup |
| 16 | Trades execution timeline (fill/reject/error por hora) |
| 17 | Benchmark BTC normalizado overlay |

### Próximo
| # | Item |
|---|---|
| 18 | Hyperliquid funding rates panel |
| 19 | Office v2 PnL realizado no flash (depende IronMan) |
| 20 | Open positions via Hyperliquid WebSocket nativo |
| 21 | Reports schedulados (daily PnL → Slack às 23:55 UTC) |
| 22 | Configurações via UI (CSP, retention, thresholds) em `data/dashboard_config.json` |
| 23 | Refator final: handlers/ por domínio |
| 24 | Rate limiting (token bucket por IP) |
| 25 | Multi-operador real (OIDC ou tabela de usuários local) |

---

## 13. Quem fez o quê (high-level)

- **Codex**: esqueleto inicial, market data live (candles/depth/tape/diagnostics), sidebar com scrollspy, agents pixel roster, mini manual, paginação/busca/filtros da incident queue, vendored libs, market/status endpoint, breaker pill, /api/positions stub inicial, metrics counters middleware.
- **Claude (este chat)**: severity score + queue, gráficos temporais, download bundle, hardening completo (XSS, CSWSH, path regex, dedup bundle, rotação, backpressure, cache, ClientSession, TaskGroup, baseline=None, p95, paths absolutos, backoff WS, pause em background, escape de erros), painel Equity & PnL, kill-switch UI, drawdown alert, security middleware, auth via X-Mekka-Token, Prometheus /metrics + painel Internals, filter exato/contém, Hyperliquid positions provider, Office v2 install + WS bridge + esbuild, SRI script, refator em 8 módulos puros, login com cookie HMAC, webhook dispatcher (Slack/Telegram), trades timeline, benchmark BTC overlay.

Histórico cronológico detalhado: `CHANGELOG.md`.
