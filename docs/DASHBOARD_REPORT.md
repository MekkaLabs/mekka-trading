# Mekka Dashboard — Relatório Completo

> Snapshot fotográfico do dashboard hoje, depois das passagens
> conjuntas com Codex e Claude. Para detalhes técnicos vivos
> use `docs/DASHBOARD_HANDOFF.md`.

---

## 1. Linhas de código

| Arquivo | Linhas |
|---|---:|
| `src/dashboard/server.py` | 2.033 |
| `src/dashboard/static/app.js` | 2.425 |
| `src/dashboard/static/style.css` | 1.207 |
| `src/dashboard/static/index.html` | 435 |
| `tests/test_dashboard_replay.py` | 1.194 |
| `docs/DASHBOARD_HANDOFF.md` | ~270 |
| **Total dashboard** | **~7.564** |

## 2. Endpoints atuais (31 rotas)

**Saúde / overview**
- `GET /api/health`, `GET /api/overview`

**Tabelas**
- `GET /api/signals|trades|audit?limit=N`

**Replay e snapshots**
- `GET /api/replay?snapshot=NAME`
- `GET /api/replay/snapshots`
- `GET /api/replay/timeseries?limit=N`
- `GET /api/replay/export?start=&end=&start_utc=&end_utc=&format=`
- `GET /api/replay/compare?a=&b=`

**Incidentes**
- `GET /api/replay/incident/latest`
- `GET /api/replay/incident/latest/download`
- `GET /api/replay/incidents` (lista bundles)
- `GET /api/replay/incident/download?name=`
- `GET /api/incidents/queue?limit=&offset=&q=&tier=`
- `GET /api/incidents/export?limit=&scan=&q=&tier=`
- `GET /api/incidents/detail?snapshot=`

**Mercado (Binance Spot)**
- `GET /api/market/candles|depth|trades|diagnostics|status`

**PnL**
- `GET /api/pnl/series?days=N`, `GET /api/pnl/summary?days=N`

**Kill switch**
- `GET /api/killswitch/status`
- `POST /api/killswitch/engage` (confirm=ENGAGE + reason)
- `POST /api/killswitch/release` (confirm=RELEASE + operator)

**Posições (stub, esperando provider)**
- `GET /api/positions`

**Observabilidade**
- `GET /metrics` (Prometheus text format)

**Real-time**
- `GET /ws` (origin allowlist, heartbeat 20s)

## 3. Painéis no frontend

| Section | Estado |
|---|---|
| `sec-live-market` | Market Live (TradingView → Lightweight → SVG fallback) |
| `sec-killswitch` | Card + modal de confirmação textual |
| `sec-replay-player` | Player + compare A/B + download bundle |
| `sec-replay-charts` | 3 charts (signals/trades/alerts+severity) |
| `sec-incident-queue` | Pagination + tier filter + search + drawer modal |
| `sec-pnl` | Equity + daily PnL + drawdown + cards win-rate |
| `sec-positions` | Tabela placeholder (provider Hyperliquid não conectado) |
| `sec-internals` | Cards live (sockets, broadcasts, latency, cache hits, breakers) + raw `/metrics` |
| `sec-metrics` | Mission Metrics |
| `sec-office` | Pixel 3D Office (canvas atual em `app.js`) |
| `sec-layers` | Layer Command Map L1–L4 |
| `sec-agents` | Agents Pixel Roster |
| `sec-risk` | Batman Risk Heatmap + drilldown |
| `sec-anomalies` | Spider-Man Anomaly Console |
| `sec-signals|trades|audit` | Tabelas |

## 4. Defesas em produção

| Vetor | Defesa |
|---|---|
| CSWSH | `_is_origin_allowed` rejeita Origin não-allowlist com 403 |
| Path traversal | Regex estrita antes de qualquer leitura |
| LAN exposure | bind default `127.0.0.1` |
| XSS via dados externos | `escapeHtml` em todo `innerHTML` + CSP estrita |
| WS slow consumer | timeout 2s + close 1011 |
| DB hangs | wait_for(3s) + cache TTL no payload builder |
| Mutação não-autorizada | `_auth_middleware` exige `X-Mekka-Token` se setado |
| Clickjacking/sniffing | X-Frame-Options=DENY, X-Content-Type-Options=nosniff, Referrer-Policy strict |
| Kill-switch acidental | confirm literal "ENGAGE"/"RELEASE" no body + modal textual |
| Drawdown silencioso | DRAWDOWN_WARNING ≥5% / DRAWDOWN_CRITICAL ≥10% alimentam severity score |

## 5. Cobertura de testes

`tests/test_dashboard_replay.py` cobre:

- Severity score (5 cenários)
- Validators (snapshot/bundle/origin, paramétricos)
- Percentile helper (incl. n=2)
- Replay snapshots / single / export (json/csv/UTC) / compare
- Incident endpoints (latest/download/baseline=null)
- Persist snapshot dedup + pruning
- WebSocket origin check (403)
- Replay timeseries
- Incidents queue (filtragem, ordenação, limite)
- PnL endpoints (series oldest-first, summary, clamp days, 504 timeout)
- Drawdown alert (thresholds, exclusivo, score boost)
- Security headers (presentes em GET, override por env)
- Auth middleware (GET aberto, POST 401, POST 200 com token)
- Kill-switch engage/release/status, idempotência, JSON malformado
- Metrics endpoint (formato Prometheus + counters incrementam)
- Positions stub (contrato estável)

**Total**: ~50 cenários, todos pareados com mocks de DB ou tmpdir.

## 6. Configuração via env

| Var | Default | Função |
|---|---|---|
| `MEKKA_SNAPSHOT_RETENTION_MIN` | `1440` | Retenção de snapshots por minuto. |
| `MEKKA_INCIDENT_RETENTION` | `200` | Retenção de incident-bundles. |
| `DASHBOARD_ALLOWED_ORIGINS` | `""` | Origens extras permitidas no WS. |
| `MEKKA_DASHBOARD_TOKEN` | `""` | Token compartilhado para mutações. |
| `MEKKA_DASHBOARD_CSP` | (default seguro) | Sobrescreve CSP. |
| `MEKKA_DRAWDOWN_WARN_PCT` | `0.05` | Threshold drawdown WARNING. |
| `MEKKA_DRAWDOWN_CRIT_PCT` | `0.10` | Threshold drawdown CRITICAL. |

## 7. Decisões arquiteturais (resumo)

1. Snapshot 1×/min em vez de 1×/2s (granularidade suficiente, 30× menos arquivos).
2. Incident bundle dedup por transição (evita spam de bundles idênticos durante kill ativo).
3. ClientSession reutilizada (evita exhaustion de FDs em polling).
4. Origin allowlist por prefixo scheme://host (sem porta).
5. Cache TTL em `_collect_payload` (1.5s/0.5s) compartilhado entre WS e REST.
6. TaskGroup no `run.py` para cancelamento mútuo runtime↔dashboard.
7. Vendored libs (TradingView, Lightweight Charts) com fallback CDN.
8. Bind default `127.0.0.1` — operador opt-in para LAN.

## 8. Roadmap (priorizado)

| # | Item | Status |
|---|---|---|
| 1 | Equity & PnL panel | DONE |
| 2 | Kill-switch UI | DONE |
| 3 | Drawdown alert | DONE |
| 4 | Security middleware | DONE |
| 5 | Auth via X-Mekka-Token | DONE |
| 6 | Métricas Prometheus + Internals | DONE |
| 7 | Filtros exato/contém/prefixo | DONE |
| 8 | Open positions stub | DONE |
| 9 | **Office v2 (cena pixel React via Babel-standalone)** | **EM ANDAMENTO** |
| 10 | Open positions provider (Hyperliquid live) | TODO |
| 11 | Refator: dividir `server.py` em módulos | TODO |
| 12 | SRI nos scripts de CDN | TODO |
| 13 | Auth via JWT/sessão (acima do shared-secret atual) | TODO |
| 14 | Drawdown chart com benchmarks | TODO |
| 15 | Hyperliquid funding rates panel | TODO |

## 9. Office v2 — diagnóstico de por que não rodava

Os 8 arquivos do Claude design são uma **app React standalone** que usa
**Babel-standalone** para transpilar JSX no browser. O HTML carrega:

```
<script src="…/react@18.3.1"></script>
<script src="…/react-dom@18.3.1"></script>
<script src="…/@babel/standalone@7.29.0"></script>
<script type="text/babel" src="tweaks-panel.jsx"></script>
<script type="text/babel" src="sprites.jsx"></script>
<script type="text/babel" src="props.jsx"></script>
<script type="text/babel" src="scene.jsx"></script>
<script type="text/babel" src="agent-motion.jsx"></script>
<script type="text/babel" src="live-data.jsx"></script>
<script type="text/babel" src="app.jsx"></script>
```

Para funcionar precisa de **dois requisitos**:

1. **Os 7 jsx têm que estar no mesmo diretório que o HTML** (paths relativos).
2. **Servidos por HTTP** (não `file://` — Babel-standalone não consegue
   buscar `.jsx` cross-origin com `file://`).

A versão entregue ao usuário caía nos dois pontos: faltava colocar os arquivos
juntos numa pasta servida pelo aiohttp existente. Na entrega abaixo a Office v2
roda em `http://127.0.0.1:8787/office-v2/`.

## 10. Limitações ainda abertas

- `server.py` ~2k linhas em monolito — refator vale uma sessão.
- Sem SRI nos `<script>` de CDN (Chart.js, TradingView).
- Auth atual é shared-secret. Para produção real com múltiplos operadores
  precisa de algo melhor (JWT, sessão, OIDC).
- Office v2 ainda usa Babel-standalone (transpila no browser, ~700KB extra).
  Para produção vale fazer build estático com esbuild/vite.
- Open positions é stub — esperando integração Hyperliquid SDK.
- Não há throttling/rate-limit — se exposto na rede, pode ser martelado.

## 11. Como rodar agora

```bash
cd ~/Documents/Mekka-Trading
.venv/bin/python run.py --dashboard-only
# Dashboard principal:
open http://127.0.0.1:8787
# Office v2:
open http://127.0.0.1:8787/office-v2/
# Métricas Prometheus:
curl http://127.0.0.1:8787/metrics
```
