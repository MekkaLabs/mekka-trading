/*
 * src/dashboard/static/memory_hub.js
 * ====================================
 * Memory Hub — visão unificada das 6 camadas de memória do Mekka.
 *
 * Auto-monta em #memory-hub-panel.
 * Polling 30s, refresh manual via botão.
 * Consome /api/memory/snapshot.
 */

(function () {
  'use strict';

  const ENDPOINT = '/api/memory/snapshot';
  const POLL_MS = 30000;

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

  function fmtNum(v) {
    if (v == null) return '—';
    if (typeof v === 'number') return v.toLocaleString('pt-BR');
    return String(v);
  }

  function fmtTs(v) {
    if (!v) return '—';
    try { return new Date(v).toLocaleString('pt-BR'); } catch (_) { return v; }
  }

  function renderHeader(payload) {
    const healthy = payload.layers_healthy || 0;
    const total = payload.layers_total || 0;
    const allOk = healthy === total && total > 0;
    return el('header', { className: 'mh-header' }, [
      el('h3', null, '🧠 Memory Hub — 6 camadas'),
      el('div', { className: 'mh-controls' }, [
        el('span', { className: 'mh-badge ' + (allOk ? 'mh-on' : 'mh-warn') },
          `${healthy}/${total} camadas OK`),
        el('button', { className: 'mh-btn', onclick: () => refresh(true) }, '🔄 Atualizar'),
      ]),
    ]);
  }

  function renderLayer(name, layer) {
    const titles = {
      agent_memory: ['🧬 Agent Memory', 'episódica por fingerprint'],
      decision_memory: ['🎯 Decision Memory', 'snapshot da Vision'],
      signal_outcome_memory: ['📈 Signal Outcome', 'por regime+ação'],
      role_working_memory: ['🪟 Role Working', 'sliding window'],
      cycle_conversation_memory: ['💬 Cycle Conv', 'user/assistant turns'],
      vault_context: ['🧠 Vault Context', 'Obsidian enrichment'],
    };
    const [title, subtitle] = titles[name] || [name, ''];
    if (!layer.available) {
      return el('div', { className: 'mh-layer mh-layer-off' }, [
        el('div', { className: 'mh-layer-head' }, [
          el('strong', null, title),
          el('span', { className: 'mh-badge mh-off' }, 'OFF'),
        ]),
        el('div', { className: 'mh-layer-sub' }, layer.error || subtitle),
      ]);
    }
    // Pick top 3 metrics que existem
    const skipKeys = new Set(['available', 'error']);
    const metrics = Object.entries(layer)
      .filter(([k]) => !skipKeys.has(k))
      .slice(0, 5);
    return el('div', { className: 'mh-layer' }, [
      el('div', { className: 'mh-layer-head' }, [
        el('strong', null, title),
        el('span', { className: 'mh-badge mh-on' }, 'ON'),
      ]),
      el('div', { className: 'mh-layer-sub' }, subtitle),
      el('dl', { className: 'mh-metrics' },
        metrics.flatMap(([k, v]) => [
          el('dt', null, k),
          el('dd', null, k.endsWith('_ts') ? fmtTs(v) : fmtNum(v)),
        ])),
    ]);
  }

  function renderBridge(bridge) {
    if (!bridge) return null;
    return el('div', { className: 'mh-bridge' }, [
      el('h4', null, '🔗 Bridge Improvement ↔ Memory'),
      el('div', { className: 'mh-bridge-row' }, [
        el('div', null, [
          el('strong', null, fmtNum(bridge.improvements_tracked)),
          el('span', { className: 'mh-label' }, ' improvements rastreadas'),
        ]),
        el('div', null, [
          el('strong', null, fmtNum(bridge.improvements_with_before)),
          el('span', { className: 'mh-label' }, ' com snapshot ANTES'),
        ]),
        el('div', null, [
          el('strong', null, fmtNum(bridge.improvements_with_after)),
          el('span', { className: 'mh-label' }, ' com snapshot DEPOIS'),
        ]),
      ]),
    ]);
  }

  function render(container, payload, err) {
    container.innerHTML = '';
    container.appendChild(renderHeader(payload || {}));
    if (err) {
      container.appendChild(el('div', { className: 'mh-error' },
        'Erro: ' + (err.message || err)));
      return;
    }
    if (!payload) {
      container.appendChild(el('div', { className: 'mh-loading' }, 'Carregando...'));
      return;
    }
    const layersGrid = el('div', { className: 'mh-layers-grid' });
    Object.entries(payload.layers || {}).forEach(([name, layer]) => {
      layersGrid.appendChild(renderLayer(name, layer));
    });
    container.appendChild(layersGrid);
    const bridge = renderBridge(payload.bridge);
    if (bridge) container.appendChild(bridge);
    container.appendChild(el('footer', { className: 'mh-footer' },
      'Última atualização: ' + fmtTs(payload.ts)));
  }

  let _state = { payload: null, err: null };
  let _container = null;
  let _timer = null;

  async function refresh(manual) {
    if (!_container) return;
    if (manual) { _state.err = null; render(_container, null); }
    try {
      const r = await fetch(ENDPOINT, { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      _state.payload = await r.json();
      _state.err = null;
    } catch (e) {
      _state.err = e;
    }
    render(_container, _state.payload, _state.err);
  }

  function mount(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return null;
    refresh(true);
    _timer = setInterval(() => refresh(false), POLL_MS);
    return {
      refresh: () => refresh(true),
      stop: () => { if (_timer) clearInterval(_timer); _timer = null; },
    };
  }

  window.MemoryHub = { mount };

  function _autoMount() {
    const el2 = document.getElementById('memory-hub-panel');
    if (!el2 || el2.dataset.mounted === '1') return !!el2;
    try {
      mount('memory-hub-panel');
      el2.dataset.mounted = '1';
      return true;
    } catch (e) {
      console.error('[MemoryHub] auto-mount falhou:', e);
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
