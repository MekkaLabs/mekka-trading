/*
 * src/dashboard/static/second_brain_activity.js
 * ===============================================
 * Módulo "Atividade do Segundo Cérebro" — exibe dados reais de:
 *   • Gerado (Prometheus learnings)
 *   • Acessado (Prometheus observations recentes)
 *   • Atualizado (arquivos do vault com mtime na janela)
 *   • Consumido (módulo vault_context disponível)
 *
 * Reusa padrões do dashboard existente:
 *   • fetch + JSON
 *   • polling controlado (30s) — sem WebSocket inventado
 *   • estados loading / vazio / erro / sucesso
 *   • atualização manual via botão
 *
 * Endpoint: GET /api/second-brain/activity?window=24
 *
 * Uso no index.html:
 *   <div id="second-brain-activity"></div>
 *   <script src="second_brain_activity.js"></script>
 *   <script>SecondBrainActivity.mount('second-brain-activity');</script>
 */

(function () {
  'use strict';

  const ENDPOINT = '/api/second-brain/activity';
  const DEFAULT_POLL_MS = 30000;
  const STATE = { LOADING: 'loading', READY: 'ready', EMPTY: 'empty', ERROR: 'error' };

  // ──────────────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────────────

  function fmtTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    const now = Date.now();
    const diffSec = Math.floor((now - d.getTime()) / 1000);
    if (diffSec < 60) return `${diffSec}s atrás`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}min atrás`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h atrás`;
    return d.toLocaleString('pt-BR');
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        if (k === 'className') node.className = attrs[k];
        else if (k === 'onclick') node.onclick = attrs[k];
        else node.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of [].concat(children)) {
        if (c == null) continue;
        node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
    }
    return node;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Fetcher (fail-soft)
  // ──────────────────────────────────────────────────────────────────────

  async function fetchActivity(windowHours) {
    const url = `${ENDPOINT}?window=${windowHours}`;
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    return resp.json();
  }

  // ──────────────────────────────────────────────────────────────────────
  // Renderers
  // ──────────────────────────────────────────────────────────────────────

  function renderStatusBadge(payload) {
    const prom = payload.prometheus_status || {};
    const sync = payload.sync_status || {};
    const parts = [];

    parts.push(
      el('span', { className: 'sb-badge ' + (prom.enabled ? 'sb-on' : 'sb-off') },
        `Prometheus: ${prom.enabled ? (prom.subscribed ? 'ativo' : 'idle') : 'off'}`)
    );

    if (sync.available) {
      const conflict = sync.conflict || 0;
      parts.push(
        el('span', { className: 'sb-badge ' + (conflict > 0 ? 'sb-warn' : 'sb-on') },
          `Sync: NEW=${sync.new || 0} · CONFLICT=${conflict}`)
      );
    } else {
      parts.push(el('span', { className: 'sb-badge sb-off' }, 'Sync indisponível'));
    }

    return el('div', { className: 'sb-badges' }, parts);
  }

  function renderSection(title, items, emptyText, renderItem) {
    const headerNode = el('h4', { className: 'sb-section-title' }, title);
    if (!items || items.length === 0) {
      return el('section', { className: 'sb-section' },
        [headerNode, el('p', { className: 'sb-empty' }, emptyText)]);
    }
    const list = el('ul', { className: 'sb-list' });
    items.slice(0, 8).forEach((item) => list.appendChild(renderItem(item)));
    return el('section', { className: 'sb-section' }, [headerNode, list]);
  }

  function renderGenerated(payload) {
    const learnings = (payload.generated && payload.generated.learnings) || [];
    return renderSection(
      '🧠 Gerado — Aprendizados do Prometheus',
      learnings,
      'Nenhum aprendizado consolidado nesta janela.',
      (l) => el('li', { className: 'sb-item' }, [
        el('span', { className: 'sb-time' }, fmtTime(l.ts)),
        el('span', { className: 'sb-text' },
          `cycle=${l.cycle_id || '?'} sym=${l.symbol || '?'} obs=${l.observation_count || 0}`),
      ]),
    );
  }

  function renderAccessed(payload) {
    const obs = (payload.accessed && payload.accessed.recent_observations) || [];
    return renderSection(
      '👁️  Acessado — Observações recentes',
      obs,
      'Sem observações do Prometheus (agente desligado ou idle).',
      (o) => el('li', { className: 'sb-item' }, [
        el('span', { className: 'sb-time' }, fmtTime(o.ts)),
        el('span', { className: 'sb-topic' }, o.topic),
        el('span', { className: 'sb-text' }, o.summary || ''),
      ]),
    );
  }

  function renderUpdated(payload) {
    const files = (payload.updated && payload.updated.files) || [];
    return renderSection(
      `📝 Atualizado — Vault (${payload.window_hours || 24}h)`,
      files,
      payload.vault_available
        ? 'Nenhum arquivo modificado nesta janela.'
        : 'Vault não disponível.',
      (f) => el('li', { className: 'sb-item' }, [
        el('span', { className: 'sb-time' }, fmtTime(f.mtime)),
        el('span', { className: 'sb-path' }, f.path),
        el('span', { className: 'sb-size' }, `${(f.size / 1024).toFixed(1)} KB`),
      ]),
    );
  }

  function renderConsumed(payload) {
    const consumed = payload.consumed || {};
    return el('section', { className: 'sb-section' }, [
      el('h4', { className: 'sb-section-title' }, '📥 Consumido — Vault context'),
      el('p', { className: consumed.vault_context_available ? 'sb-ok' : 'sb-empty' },
        consumed.vault_context_available
          ? 'Módulo vault_context disponível. Contadores agregados serão expostos quando vault_context expuser métricas.'
          : 'Módulo vault_context indisponível neste ambiente.'),
    ]);
  }

  function renderLimitations(payload) {
    const notes = payload.limitations || [];
    if (notes.length === 0) return null;
    return el('div', { className: 'sb-limitations' }, [
      el('strong', null, 'Limitações reais:'),
      el('ul', { className: 'sb-lim-list' },
        notes.map((n) => el('li', null, n))),
    ]);
  }

  function renderError(err) {
    return el('div', { className: 'sb-error' },
      `Falha ao carregar atividade do Segundo Cérebro: ${err.message || err}`);
  }

  // ──────────────────────────────────────────────────────────────────────
  // Component
  // ──────────────────────────────────────────────────────────────────────

  function mount(containerId, opts) {
    const options = Object.assign(
      { windowHours: 24, pollMs: DEFAULT_POLL_MS },
      opts || {},
    );
    const container = document.getElementById(containerId);
    if (!container) {
      console.warn('[SecondBrainActivity] container não encontrado:', containerId);
      return null;
    }
    let timer = null;
    let lastPayload = null;
    let lastErr = null;
    let state = STATE.LOADING;

    function render() {
      container.innerHTML = '';
      const header = el('header', { className: 'sb-header' }, [
        el('h3', null, '🧠 Atividade do Segundo Cérebro'),
        el('div', { className: 'sb-controls' }, [
          el('button', { className: 'sb-btn', onclick: () => { refresh(true); } },
            '🔄 Atualizar'),
        ]),
      ]);
      container.appendChild(header);

      if (state === STATE.LOADING && !lastPayload) {
        container.appendChild(el('div', { className: 'sb-loading' }, 'Carregando...'));
        return;
      }
      if (state === STATE.ERROR && !lastPayload) {
        container.appendChild(renderError(lastErr));
        return;
      }
      if (!lastPayload) {
        container.appendChild(el('div', { className: 'sb-empty' }, 'Sem dados disponíveis.'));
        return;
      }

      container.appendChild(renderStatusBadge(lastPayload));
      container.appendChild(renderGenerated(lastPayload));
      container.appendChild(renderAccessed(lastPayload));
      container.appendChild(renderUpdated(lastPayload));
      container.appendChild(renderConsumed(lastPayload));
      const lim = renderLimitations(lastPayload);
      if (lim) container.appendChild(lim);
      container.appendChild(
        el('footer', { className: 'sb-footer' },
          `Última atualização: ${fmtTime(lastPayload.ts)} · janela: ${lastPayload.window_hours}h · polling: ${Math.round(options.pollMs / 1000)}s`),
      );
    }

    async function refresh(manual) {
      if (manual) {
        state = STATE.LOADING;
        render();
      }
      try {
        const payload = await fetchActivity(options.windowHours);
        lastPayload = payload;
        lastErr = null;
        state = STATE.READY;
      } catch (err) {
        lastErr = err;
        state = STATE.ERROR;
        console.warn('[SecondBrainActivity] erro:', err);
      }
      render();
    }

    function start() {
      refresh(true);
      if (timer) clearInterval(timer);
      timer = setInterval(() => refresh(false), options.pollMs);
    }

    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
    }

    start();
    return { refresh, stop, start };
  }

  // Expor namespace global
  window.SecondBrainActivity = { mount };

  // ── Auto-mount ───────────────────────────────────────────────────────
  // O módulo se auto-monta se encontrar o div `#second-brain-activity`.
  // Robusto a ordem de carga: tenta no parse, depois em DOMContentLoaded,
  // depois retry curto (200ms x 10) para o caso do div ser injetado mais
  // tarde por outro script. Idempotente: marca `dataset.mounted` para não
  // duplicar.
  function _autoMount(opts) {
    const el = document.getElementById('second-brain-activity');
    if (!el) return false;
    if (el.dataset.mounted === '1') return true;
    try {
      mount('second-brain-activity', opts || { windowHours: 24, pollMs: 30000 });
      el.dataset.mounted = '1';
      return true;
    } catch (e) {
      console.error('[SecondBrainActivity] auto-mount falhou:', e);
      return false;
    }
  }

  // Tentativa imediata (caso DOM já esteja pronto, ex.: script no body)
  if (!_autoMount()) {
    // DOM ainda não pronto OU div não existe ainda — agenda fallbacks
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { _autoMount(); });
    }
    // Retry curto para casos onde o div é injetado depois (defensive)
    var _tries = 10;
    var _interval = setInterval(function () {
      if (_autoMount() || _tries-- <= 0) clearInterval(_interval);
    }, 200);
  }
})();
