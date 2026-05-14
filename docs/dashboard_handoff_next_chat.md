# Mekka Dashboard — Handoff for Next Chat

## Current Status
Dashboard is running at `http://127.0.0.1:8787` with:
- Sidebar navigation + scrollspy
- Replay + incident workflows
- Market Live with TradingView (local vendor first) + fallback charts
- Order book heatmap, trade tape, websocket tick updates
- Incident queue severity filter + baseline compare action + consolidated CSV export
- Incident queue textual search + pagination + quick detail panel

## What was improved in this step
1. **Vendor-first scripts (resilience)**
- `src/dashboard/static/vendor/tv.js`
- `src/dashboard/static/vendor/lightweight-charts.standalone.production.js`
- `index.html` now loads local scripts first and falls back to CDN on error.

2. **Market API hardening**
- Added bounded concurrency (`Semaphore(4)`) for external market fetches.
- Added in-memory TTL cache for market endpoints.
- Added retry with exponential-ish backoff in `_market_get_json`.
- Added diagnostics endpoint:
  - `GET /api/market/diagnostics`
  - returns calls, cache hits, error count, last error, last/avg latency, cache size.

3. **UI preference persistence**
- Persists and reapplies:
  - market symbol
  - market timeframe
  - incident queue severity
  - filters (symbol/hero/event)
- Uses `localStorage` key: `mekka_dashboard_prefs_v1`.

4. **Diagnostics panel in UI**
- Added `Market Diagnostics` panel in Market Live section.
- Auto-refreshes with market cycle and manual refresh flow.

5. **Incident Queue UX upgrade**
- Backend `GET /api/incidents/queue` now supports:
  - `q` for free-text search (snapshot, tier, drivers, alert code/message)
  - `offset` + `limit` for pagination
- Backend `GET /api/incidents/export` now also supports `q`.
- Frontend queue toolbar now includes:
  - search input
  - Prev/Next pagination buttons
  - page/status indicator
- Added quick `Incident Detail` card that updates on row click.

## Key Files touched
- `src/dashboard/server.py`
- `src/dashboard/static/index.html`
- `src/dashboard/static/app.js`
- `src/dashboard/static/vendor/tv.js`
- `src/dashboard/static/vendor/lightweight-charts.standalone.production.js`
- `docs/dashboard_handoff.md`
- `docs/dashboard_handoff_next_chat.md`

## API Summary
- Health: `/api/health`
- Replay: `/api/replay*`
- Incidents:
  - `/api/incidents/queue`
  - `/api/incidents/export`
- Market:
  - `/api/market/candles`
  - `/api/market/depth`
  - `/api/market/trades`
  - `/api/market/diagnostics`
- Websocket internal ops stream: `/ws`

## Suggested Next Work (priority)
1. Add circuit breaker mode when provider failures spike (temporarily serve cached/stale data).
2. Add incident detail drawer with structured baseline diff (instead of text block).
3. Expand contract tests to cover `q` on `/api/incidents/export` and pagination edge-cases.
4. Optional: split `app.js` into modules (`market.js`, `replay.js`, `ops.js`) for maintainability.

## Run
```bash
cd /Users/gustavovicente/Documents/Mekka-Trading
.venv/bin/python run.py --dashboard-only
```
