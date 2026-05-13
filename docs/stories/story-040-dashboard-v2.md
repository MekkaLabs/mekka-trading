# Story 040 — Dashboard v2: Pages, TopBar, Widgets, TradeNow

**Status:** In Progress  
**Milestone:** 13 — Operator UX

---

## Context

The dashboard (introduced through Stories 020–039) grew organically into a
single long-scroll page with 20+ sections. Operators must scroll to find
panels, all data loads regardless of page, and there is no quick way to
open a trade without leaving the dashboard.

Four squads reviewed the project (2026-05-11) and flagged UX as the main
friction point before mainnet operations become practical.

---

## Goal

Make the dashboard:
1. **Page-based** — 8 categories, each showing only its own sections.
2. **Financially-oriented** — wallet balance, day PnL, open positions and
   agent status always visible at the top.
3. **Personalizable** — operators choose which blocks to show, order
   is persisted in `localStorage`.
4. **Trade-actionable** — a single button triggers agent analysis →
   shows recommendation → waits for explicit confirmation before executing.

---

## Scope Delivered

### 1. Page Navigation
- 8 pages: **Overview · Wallet · Performance · Agents · Trades · Risk · Logs · Settings**
- `data-page` attribute on every `<section>`; JS shows/hides by active page.
- Active page stored in `localStorage` (`mekka_current_page`); also synced
  to URL hash on change for bookmarking.
- Sidebar collapses into icon-only strip on narrow viewports.

### 2. Financial TopBar
New row below the title bar with live cards:

| Card | Source |
|---|---|
| Wallet Balance | `/api/overview` → `equity_usd` |
| Day PnL $ | `/api/pnl/summary?window=1` → `window.pnl_usd` |
| Day PnL % | `/api/pnl/summary?window=1` → `window.pnl_pct` (computed) |
| Open Positions | `/api/positions` → count |
| Risk Level | `/api/overview` → kill switch + drawdown |
| Agent Status | `/api/overview` → breaker states |
| Last Update | client-side timestamp |

Cards refresh every 30 s. Show `—` on error; never block render.

### 3. Widget Customizer (Settings page)
- Toggle checkboxes per section ID.
- Persisted in `localStorage` key `mekka_widget_prefs_v1` as `{[sectionId]: boolean}`.
- Applied on page change: sections with `false` get `display:none`.
- Architecture exposes `window._mkWidgetPrefs` for future remote sync.

### 4. TradeNow Button + Flow
Button in topbar: **⚡ Executar Trade**.

State machine: `idle → analyzing → recommending → confirming → executing → done`

**`POST /api/trade/analyze`** (new, auth required):
- Calls available NickFury / Vision snapshot if agents running.
- Returns typed `TradeRecommendation` (mock when agents unavailable).
- Guardrails evaluated server-side:
  - `wallet_ok` — equity > 0
  - `risk_ok` — current drawdown < `max_daily_drawdown_pct`
  - `kill_switch_clear` — no active kill switch
  - `data_fresh` — last snapshot < 5 min old

**`POST /api/trade/execute`** (new, auth required):
- Body: `{recommendation_id, confirmed: true}`.
- Re-evaluates guardrails server-side (no trust on client).
- Persists audit event `TRADE_NOW_EXECUTED` or `TRADE_NOW_BLOCKED`.
- Paper mode: marks execution as paper, never calls SDK.
- Returns `{status, order_id?, reason}`.

**Modal shows:**
- Asset, direction (LONG/SHORT), entry price, SL, TP, size %, confidence,
  agent justification, estimated risk USD, guardrail checklist.

**Client guardrails (block button before API call):**
- Wallet balance missing/zero → "Carteira indisponível"
- Kill switch active → "Kill switch ativo — libere antes de operar"
- No page refresh in >5 min → "Dados stale — atualize antes"

### 5. Audit Trail
Every TradeNow action creates an `audit_log` row:
- `TRADE_NOW_REQUESTED` — button click
- `TRADE_NOW_RECOMMENDED` — recommendation returned
- `TRADE_NOW_CONFIRMED` — user confirmed
- `TRADE_NOW_BLOCKED` — guardrail prevented execution
- `TRADE_NOW_EXECUTED` — paper/live order submitted

---

## Hard Rules Mantidas

- No real order without `confirmed: true` in body.
- No API secrets in frontend JS.
- `brokerExecutionAdapter` interface kept separate; mock used in paper mode.
- All new endpoints require authentication when login is enabled.
- No new external dependencies; vanilla JS only for dashboard.

---

## Acceptance Criteria

- [x] Dashboard navigation por páginas (não scroll longo).
- [x] 8 categorias claras no sidebar.
- [x] Topbar mostra wallet, day PnL, posições, risco, status agentes.
- [x] Cards financeiros atualizam a cada 30 s.
- [x] Usuário pode ocultar/exibir seções na página Settings.
- [x] Preferências de widgets persistem no localStorage.
- [x] Botão "Executar Trade" existe e está sempre visível.
- [x] Clique chama `/api/trade/analyze` (não executa diretamente).
- [x] Modal exibe ativo, direção, entrada, SL, TP, tamanho, confiança, justificativa.
- [x] Guardrails bloqueiam execução em cenários inseguros.
- [x] Execução exige `confirmed: true` explícito.
- [x] Audit log criado para cada etapa do fluxo.
- [x] Nenhum secret no frontend.
- [x] Testes cobrem endpoints + guardrails + audit.
- [x] `python -m py_compile` limpo em todos os arquivos Python.

---

## Files Changed

| File | Change |
|---|---|
| `docs/stories/story-040-dashboard-v2.md` | **NEW** — this story |
| `src/dashboard/server.py` | `POST /api/trade/analyze`, `POST /api/trade/execute`, route registration |
| `src/dashboard/static/index.html` | Page nav, financial topbar, data-page attrs, TradeNow modal, widget settings |
| `src/dashboard/static/app.js` | Page system, loadTopBarMetrics, TradeNow flow, widget customizer, boot wiring |
| `src/dashboard/static/style.css` | Page nav, topbar cards, TradeNow button, widget panel |
| `tests/test_phase19_dashboard_v2.py` | **NEW** — endpoint + guardrail + audit tests |
| `docs/stories/INDEX.md` | Entry under Milestone 13 |

---

## What's Next

- Story 041: Wire real broker adapter for live execution (replace mock).
- Story 042: Remote widget-pref persistence via `/api/prefs` endpoint.
- Story 043: Backtesting panel (CTO Architect Sprint 42 backlog).
