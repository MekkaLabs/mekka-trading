// strategy_matrix.js
// ===================
// Painel "Be Water — Strategy Matrix" — auto-mount em
// <section id="sec-strategy-matrix">. Silently no-op se a section não existir.
//
// Mostra:
//   - Regime atual detectado (com confidence + tooltip de features brutas)
//   - Top 3 estratégias pro regime atual (cards com win_rate, sharpe, n_trades)
//   - Heatmap de fitness: todas estratégias × todos regimes
//
// Endpoints:
//   GET /api/strategies                 → lista completa + fitness
//   GET /api/strategies/regime?symbol=  → regime atual detectado
//   GET /api/strategies/performance     → top por regime + histórico
//
// Refresh: 60s. Pause quando aba escondida. CSP-friendly (sem inline).

(function () {
  'use strict';

  const ROOT_ID = 'sec-strategy-matrix';
  const REFRESH_MS = 60_000;
  const DEFAULT_SYMBOL = 'BTC';

  const REGIME_LABELS = {
    low_vol_range:           'Low-Vol Range',
    low_vol_trending:        'Low-Vol Trend',
    high_vol_trending_up:    'High-Vol Up',
    high_vol_trending_down:  'High-Vol Down',
    high_vol_choppy:         'High-Vol Choppy',
    breakout:                'Breakout',
    funding_extreme:         'Funding Extreme',
    unclear:                 'Unclear',
  };

  const REGIME_ORDER = [
    'low_vol_range',
    'low_vol_trending',
    'high_vol_trending_up',
    'high_vol_trending_down',
    'high_vol_choppy',
    'breakout',
    'funding_extreme',
    'unclear',
  ];

  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    if (s === undefined || s === null) return '';
    return String(s)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function fmtPct(v) {
    if (v === undefined || v === null || Number.isNaN(v)) return '—';
    return Number(v).toFixed(1) + '%';
  }

  function fmtNum(v, digits = 2) {
    if (v === undefined || v === null || Number.isNaN(v)) return '—';
    return Number(v).toFixed(digits);
  }

  function fitnessColor(score) {
    // 0 → cinza escuro, 1 → verde forte
    const s = Math.max(0, Math.min(1, Number(score) || 0));
    if (s < 0.1) return '#2a2a2a';
    // HSL: hue 100 (verde), saturation cresce com fitness
    const lightness = Math.round(20 + s * 35);
    const saturation = Math.round(40 + s * 35);
    return `hsl(110, ${saturation}%, ${lightness}%)`;
  }

  function confidenceBar(conf) {
    const pct = Math.round(Math.max(0, Math.min(1, conf || 0)) * 100);
    return `
      <div class="sm-conf-bar" title="Confidence ${pct}%">
        <div class="sm-conf-fill" style="width:${pct}%"></div>
        <span class="sm-conf-lbl">${pct}%</span>
      </div>`;
  }

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  function renderRegimeCard(regimeData, symbol) {
    if (!regimeData || regimeData.error) {
      const msg = (regimeData && regimeData.error) || 'sem dados';
      return `
        <div class="sm-card sm-regime-card">
          <h4>🌊 Regime atual (${escapeHtml(symbol)})</h4>
          <p class="sm-muted">Erro: ${escapeHtml(msg)}</p>
        </div>`;
    }
    const r = regimeData.regime || {};
    const label = REGIME_LABELS[r.regime] || r.regime || '—';
    const features = r.features || {};
    const tooltip = Object.entries(features)
      .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(4) : v}`)
      .join('\n');
    return `
      <div class="sm-card sm-regime-card" title="${escapeHtml(tooltip)}">
        <h4>🌊 Regime atual <span class="sm-muted">(${escapeHtml(symbol)})</span></h4>
        <div class="sm-regime-name">${escapeHtml(label)}</div>
        ${confidenceBar(r.confidence)}
        <div class="sm-muted sm-tiny">${escapeHtml(r.rationale || '')}</div>
        <div class="sm-muted sm-tiny">Detectado: ${escapeHtml((r.detected_at || '').slice(11, 19))}</div>
      </div>`;
  }

  function renderTopStrategies(perfData, regimeKey) {
    let tops = [];
    if (perfData && Array.isArray(perfData.top_strategies)) {
      tops = perfData.top_strategies;
    } else if (perfData && perfData.by_regime && regimeKey) {
      tops = perfData.by_regime[regimeKey] || [];
    }
    if (!tops.length) {
      return `
        <div class="sm-card sm-top-card">
          <h4>🏆 Top 3 estratégias <span class="sm-muted">(${escapeHtml(REGIME_LABELS[regimeKey] || regimeKey || '—')})</span></h4>
          <p class="sm-muted">Sem histórico de performance ainda.</p>
          ${perfData && perfData.note ? `<p class="sm-tiny sm-muted">${escapeHtml(perfData.note)}</p>` : ''}
        </div>`;
    }
    const cards = tops.slice(0, 3).map((t, i) => {
      const name = t.strategy_name || t.name || `#${i + 1}`;
      const wr = t.win_rate_pct ?? t.win_rate ?? t.win_rate_pct_real;
      const sharpe = t.sharpe_ratio ?? t.sharpe ?? t.sharpe_real;
      const n = t.total_trades ?? t.n_trades ?? t.trades ?? 0;
      const pnl = t.total_pnl_usd ?? t.pnl_usd ?? t.pnl;
      return `
        <div class="sm-top-item">
          <div class="sm-top-rank">#${i + 1}</div>
          <div class="sm-top-body">
            <div class="sm-top-name">${escapeHtml(name)}</div>
            <div class="sm-top-stats">
              <span>WR: <b>${fmtPct(wr)}</b></span>
              <span>Sharpe: <b>${fmtNum(sharpe)}</b></span>
              <span>n: <b>${Number(n) || 0}</b></span>
              ${pnl !== undefined ? `<span>P&amp;L: <b>$${fmtNum(pnl)}</b></span>` : ''}
            </div>
          </div>
        </div>`;
    }).join('');
    return `
      <div class="sm-card sm-top-card">
        <h4>🏆 Top 3 estratégias <span class="sm-muted">(${escapeHtml(REGIME_LABELS[regimeKey] || regimeKey || '—')})</span></h4>
        <div class="sm-top-list">${cards}</div>
      </div>`;
  }

  function renderHeatmap(listData, regimeKey) {
    const strategies = (listData && Array.isArray(listData.strategies)) ? listData.strategies : [];
    if (!strategies.length) {
      return `<div class="sm-card"><h4>🔥 Heatmap fitness</h4><p class="sm-muted">Nenhuma estratégia registrada.</p></div>`;
    }

    // Header: regimes
    const headerCells = REGIME_ORDER.map((r) => {
      const isCurrent = r === regimeKey;
      return `<th class="sm-heat-th ${isCurrent ? 'sm-heat-th--current' : ''}" title="${escapeHtml(r)}">${escapeHtml(REGIME_LABELS[r] || r)}</th>`;
    }).join('');

    // Rows: strategies
    const rows = strategies.map((s) => {
      const cells = REGIME_ORDER.map((r) => {
        const score = (s.regime_fitness && s.regime_fitness[r]) || 0;
        const isCurrent = r === regimeKey;
        const bg = fitnessColor(score);
        return `<td class="sm-heat-cell ${isCurrent ? 'sm-heat-cell--current' : ''}" style="background:${bg}" title="${escapeHtml(s.name)} × ${escapeHtml(REGIME_LABELS[r] || r)} = ${fmtNum(score, 2)}">${fmtNum(score, 2)}</td>`;
      }).join('');
      return `
        <tr>
          <td class="sm-heat-name" title="${escapeHtml(s.description || '')}">
            <b>${escapeHtml(s.name)}</b>
            <div class="sm-tiny sm-muted">lev ${s.max_leverage}× · size ${(s.max_position_size_pct * 100).toFixed(1)}%</div>
          </td>
          ${cells}
        </tr>`;
    }).join('');

    return `
      <div class="sm-card sm-heatmap-card">
        <h4>🔥 Heatmap fitness — todas estratégias × regimes</h4>
        <div class="sm-heat-wrap">
          <table class="sm-heat-table">
            <thead><tr><th class="sm-heat-th sm-heat-name-th">Estratégia</th>${headerCells}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <p class="sm-tiny sm-muted">Coluna destacada = regime atual. Score 0–1 declarado por cada estratégia.</p>
      </div>`;
  }

  function renderError(root, msg) {
    root.innerHTML = `
      <div class="sm-card"><h3>🌊 Be Water — Strategy Matrix</h3>
      <p class="sm-muted">Erro: ${escapeHtml(msg)}</p></div>
      ${styleBlock()}`;
  }

  function styleBlock() {
    return `
      <style>
        #${ROOT_ID} { padding: 14px; }
        #${ROOT_ID} h3 { margin: 0 0 12px 0; font-size: 1.1em; }
        #${ROOT_ID} h4 { margin: 0 0 8px 0; font-size: 0.95em; color: #c8d4e8; }
        #${ROOT_ID} .sm-muted { color: #888; font-size: 0.85em; }
        #${ROOT_ID} .sm-tiny  { font-size: 0.78em; }
        #${ROOT_ID} .sm-card {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 6px;
          padding: 12px 14px;
          margin-bottom: 14px;
        }
        #${ROOT_ID} .sm-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 14px;
          margin-bottom: 14px;
        }
        #${ROOT_ID} .sm-row .sm-card { margin-bottom: 0; }

        /* Regime card */
        #${ROOT_ID} .sm-regime-name {
          font-size: 1.3em; font-weight: 600; color: #7fd17f;
          margin: 6px 0;
        }
        #${ROOT_ID} .sm-conf-bar {
          position: relative;
          height: 12px;
          background: rgba(255,255,255,0.06);
          border-radius: 3px;
          overflow: hidden;
          margin: 6px 0 8px 0;
        }
        #${ROOT_ID} .sm-conf-fill {
          height: 100%;
          background: linear-gradient(90deg, #5a9ad6, #7fd17f);
        }
        #${ROOT_ID} .sm-conf-lbl {
          position: absolute; right: 6px; top: -1px;
          color: #fff; font-size: 0.7em; line-height: 12px;
          text-shadow: 0 0 2px rgba(0,0,0,0.7);
        }

        /* Top strategies */
        #${ROOT_ID} .sm-top-list { display: flex; flex-direction: column; gap: 8px; }
        #${ROOT_ID} .sm-top-item {
          display: flex; gap: 10px; align-items: center;
          padding: 8px; background: rgba(255,255,255,0.02);
          border-radius: 4px;
        }
        #${ROOT_ID} .sm-top-rank {
          font-size: 1.4em; font-weight: 700; color: #e5c07b; min-width: 36px;
        }
        #${ROOT_ID} .sm-top-name { font-weight: 600; margin-bottom: 4px; }
        #${ROOT_ID} .sm-top-stats { display: flex; gap: 10px; flex-wrap: wrap; font-size: 0.85em; color: #aaa; }
        #${ROOT_ID} .sm-top-stats b { color: #c8d4e8; }

        /* Heatmap */
        #${ROOT_ID} .sm-heat-wrap { overflow-x: auto; }
        #${ROOT_ID} .sm-heat-table {
          width: 100%; border-collapse: collapse; font-size: 0.82em;
        }
        #${ROOT_ID} .sm-heat-th {
          color: #888; font-weight: normal; text-align: center;
          padding: 6px 4px; border-bottom: 1px solid rgba(255,255,255,0.08);
          white-space: nowrap;
        }
        #${ROOT_ID} .sm-heat-name-th { text-align: left; }
        #${ROOT_ID} .sm-heat-th--current { color: #7fd17f; font-weight: 600; }
        #${ROOT_ID} .sm-heat-name {
          padding: 6px 8px; text-align: left;
          border-bottom: 1px dotted rgba(255,255,255,0.05);
          background: rgba(255,255,255,0.02);
          min-width: 130px;
        }
        #${ROOT_ID} .sm-heat-cell {
          padding: 6px 4px; text-align: center;
          color: #f0f0f0;
          font-variant-numeric: tabular-nums;
          border-bottom: 1px dotted rgba(255,255,255,0.05);
          border-left: 1px dotted rgba(255,255,255,0.04);
        }
        #${ROOT_ID} .sm-heat-cell--current { box-shadow: inset 0 0 0 2px rgba(127, 209, 127, 0.5); }
      </style>`;
  }

  function render(payload, root) {
    const { list, regime, perf, symbol } = payload;
    const regimeKey = (regime && regime.regime && regime.regime.regime) || null;

    root.innerHTML = `
      <div class="panel-hdr" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <h3 style="margin:0">🌊 Be Water — Strategy Matrix</h3>
        <div class="sm-muted sm-tiny">
          ${list && list.total ? `${list.total} estratégias` : ''}
          ${list && list.error ? ` · <span style="color:#d27575">err: ${escapeHtml(list.error).slice(0, 40)}</span>` : ''}
          · auto-refresh 60s
        </div>
      </div>

      <div class="sm-row">
        ${renderRegimeCard(regime, symbol)}
        ${renderTopStrategies(perf, regimeKey)}
      </div>

      ${renderHeatmap(list, regimeKey)}

      ${styleBlock()}
    `;
  }

  // -------------------------------------------------------------------------
  // Fetch + boot
  // -------------------------------------------------------------------------

  async function fetchAll(symbol) {
    const safe = async (url) => {
      try {
        const r = await fetch(url, { cache: 'no-store' });
        return await r.json();
      } catch (e) {
        return { error: e.message };
      }
    };

    const [list, regime, perf] = await Promise.all([
      safe('/api/strategies'),
      safe(`/api/strategies/regime?symbol=${encodeURIComponent(symbol)}`),
      safe('/api/strategies/performance'),
    ]);
    return { list, regime, perf, symbol };
  }

  let _timer = null;
  let _currentSymbol = DEFAULT_SYMBOL;

  async function refresh() {
    const root = $(ROOT_ID);
    if (!root) return;
    try {
      const data = await fetchAll(_currentSymbol);
      render(data, root);
    } catch (e) {
      renderError(root, e.message);
    }
  }

  function start() {
    const root = $(ROOT_ID);
    if (!root) return;  // section ainda não existe — silently no-op
    refresh();
    if (_timer) clearInterval(_timer);
    _timer = setInterval(() => {
      if (!document.hidden) refresh();
    }, REFRESH_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
