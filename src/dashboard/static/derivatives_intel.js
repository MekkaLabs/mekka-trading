/*
 * src/dashboard/static/derivatives_intel.js
 * ===========================================
 * Painel "Inteligência de Derivativos" (Cable agent).
 *
 * Mesmo padrão de second_brain_activity.js: auto-mount + polling
 * controlado + sem WebSocket inventado. Consome /api/cable/snapshot.
 *
 * Auto-monta em #derivatives-intel-panel quando o elemento existe.
 */

(function () {
  'use strict';

  const ENDPOINT = '/api/cable/snapshot';
  const DEFAULT_POLL_MS = 60000; // 60s — funding/OI mudam devagar

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) for (const k of Object.keys(attrs)) {
      if (k === 'className') n.className = attrs[k];
      else if (k === 'onclick') n.onclick = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    if (children) for (const c of [].concat(children)) {
      if (c == null) continue;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }

  function fmtPct(v) {
    if (v == null || isNaN(v)) return '—';
    return (v * 100).toFixed(3) + '%';
  }

  function fmtNum(v) {
    if (v == null || isNaN(v)) return '—';
    return Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
  }

  function renderStatus(payload) {
    const cs = payload.cable_status || {};
    const parts = [];
    parts.push(el('span', { className: 'di-badge ' + (cs.enabled ? 'di-on' : 'di-off') },
      'Cable: ' + (cs.enabled ? (cs.subscribed ? 'ativo' : 'idle') : 'off')));
    parts.push(el('span', { className: 'di-badge ' + (cs.auth_personal_trades ? 'di-on' : 'di-off') },
      'API pessoal: ' + (cs.auth_personal_trades ? 'configurada' : 'não')));
    parts.push(el('span', { className: 'di-badge' }, payload.source || '—'));
    return el('div', { className: 'di-badges' }, parts);
  }

  function renderSymbol(sym, d) {
    const f = (d && d.funding) || {};
    const oi = (d && d.open_interest) || {};
    return el('div', { className: 'di-sym' }, [
      el('div', { className: 'di-sym-head' }, el('strong', null, sym)),
      el('div', { className: 'di-sym-row' }, [
        el('span', { className: 'di-label' }, 'Funding (média 8h):'),
        el('span', { className: 'di-val' }, fmtPct(f.mean)),
      ]),
      el('div', { className: 'di-sym-row' }, [
        el('span', { className: 'di-label' }, 'Funding (atual):'),
        el('span', { className: 'di-val' }, fmtPct(f.last)),
      ]),
      el('div', { className: 'di-sym-row' }, [
        el('span', { className: 'di-label' }, 'Open Interest:'),
        el('span', { className: 'di-val' }, fmtNum(oi.value)),
      ]),
    ]);
  }

  function renderInsights(insights) {
    if (!insights || insights.length === 0) {
      return el('p', { className: 'di-empty' }, 'Sem insights nesta janela.');
    }
    const list = el('ul', { className: 'di-insights' });
    insights.forEach((i) => list.appendChild(el('li', null, i)));
    return list;
  }

  function render(container, payload, err) {
    container.innerHTML = '';
    container.appendChild(el('header', { className: 'di-header' }, [
      el('h3', null, '📈 Inteligência de Derivativos'),
      el('div', { className: 'di-controls' },
        el('button', { className: 'di-btn', onclick: () => refresh(container, true) }, '🔄 Atualizar')),
    ]));
    if (err) {
      container.appendChild(el('div', { className: 'di-error' },
        'Erro: ' + (err.message || err)));
      return;
    }
    if (!payload) {
      container.appendChild(el('div', { className: 'di-loading' }, 'Carregando...'));
      return;
    }
    container.appendChild(renderStatus(payload));

    // Snapshot: pode vir como 'snapshot' (live) ou 'latest_report.snapshot' (cable)
    const snap = (payload.snapshot) || (payload.latest_report && payload.latest_report.snapshot) || {};
    const data = snap.data || {};
    const symGrid = el('div', { className: 'di-sym-grid' });
    const syms = snap.symbols || Object.keys(data);
    if (syms.length === 0) {
      symGrid.appendChild(el('p', { className: 'di-empty' }, 'Nenhum símbolo no snapshot.'));
    } else {
      syms.forEach((s) => symGrid.appendChild(renderSymbol(s, data[s])));
    }
    container.appendChild(el('h4', { className: 'di-section-title' }, '📊 Snapshot por símbolo'));
    container.appendChild(symGrid);

    // Insights (apenas quando agente gera report)
    const insights = (payload.latest_report && payload.latest_report.insights) || null;
    if (insights) {
      container.appendChild(el('h4', { className: 'di-section-title' }, '💡 Insights'));
      container.appendChild(renderInsights(insights));
    }

    // Disclaimer obrigatório
    container.appendChild(el('p', { className: 'di-disclaimer' },
      payload.disclaimer || 'Métricas descritivas. Não constituem recomendação.'));
    container.appendChild(el('footer', { className: 'di-footer' },
      'Última atualização: ' + new Date(payload.ts * 1000).toLocaleString('pt-BR')));
  }

  let _state = { payload: null, err: null };

  async function refresh(container, manual) {
    if (manual) { _state.err = null; render(container, null); }
    try {
      const r = await fetch(ENDPOINT, { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      _state.payload = await r.json();
      _state.err = null;
    } catch (e) {
      _state.err = e;
    }
    render(container, _state.payload, _state.err);
  }

  function mount(containerId, opts) {
    const options = Object.assign({ pollMs: DEFAULT_POLL_MS }, opts || {});
    const container = document.getElementById(containerId);
    if (!container) return null;
    refresh(container, true);
    const t = setInterval(() => refresh(container, false), options.pollMs);
    return { refresh: () => refresh(container, true), stop: () => clearInterval(t) };
  }

  window.DerivativesIntel = { mount };

  // Auto-mount
  function _autoMount() {
    const el2 = document.getElementById('derivatives-intel-panel');
    if (!el2 || el2.dataset.mounted === '1') return !!el2;
    try {
      mount('derivatives-intel-panel');
      el2.dataset.mounted = '1';
      return true;
    } catch (e) {
      console.error('[DerivativesIntel] auto-mount falhou:', e);
      return false;
    }
  }

  if (!_autoMount()) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', _autoMount);
    }
    let tries = 10;
    const iv = setInterval(() => { if (_autoMount() || tries-- <= 0) clearInterval(iv); }, 200);
  }
})();
