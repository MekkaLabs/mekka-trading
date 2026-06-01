/*
 * src/dashboard/static/learning_hub.js
 * =====================================
 * D (2026-05-30) — Learning Hub unificado.
 *
 * Consome os 4 endpoints novos:
 *   - /api/server/health          (uptime, tasks, endpoints)
 *   - /api/prometheus/snapshot    (observations, learnings emitidos)
 *   - /api/vault/activity         (writers ativos, writes 7d)
 *   - /api/implementer/status     (queue + history)
 *
 * Mostra 4 cards lado-a-lado. Refresh 30s.
 * Auto-monta em #learning-hub-panel.
 */
(function () {
  'use strict';

  const POLL_MS = 30000;
  const ENDPOINTS = {
    health: '/api/server/health',
    prometheus: '/api/prometheus/snapshot',
    vault: '/api/vault/activity',
    implementer: '/api/implementer/status',
  };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        if (k === 'className') n.className = attrs[k];
        else if (k === 'text') n.textContent = attrs[k];
        else n.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of children) {
        if (c == null) continue;
        n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      }
    }
    return n;
  }

  function row(label, value, cls) {
    const v = el('span', { className: 'lh-val' + (cls ? ' ' + cls : '') });
    v.textContent = (value == null ? '—' : String(value));
    return el('div', { className: 'lh-row' }, [
      el('span', { text: label }),
      v,
    ]);
  }

  function fmtHumanSec(s) {
    if (s == null) return '—';
    if (s < 60) return Math.round(s) + 's';
    if (s < 3600) return Math.round(s / 60) + 'min';
    if (s < 86400) return (s / 3600).toFixed(1) + 'h';
    return (s / 86400).toFixed(1) + 'd';
  }

  async function fetchJson(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) return { error: 'HTTP ' + r.status };
      return await r.json();
    } catch (e) {
      return { error: String(e) };
    }
  }

  function renderHealth(data) {
    const tasks = (data && data.tasks) || {};
    const taskCount = Object.values(tasks).filter(Boolean).length;
    const total = Object.keys(tasks).length || 1;
    const cls = taskCount === 0 ? 'lh-bad' : (taskCount < total ? 'lh-warn' : 'lh-val');
    return el('div', { className: 'lh-card' }, [
      el('h4', { text: '🖥️ Server Health' }),
      row('PID', data.pid),
      row('Uptime', data.uptime_human || fmtHumanSec(data.uptime_seconds)),
      row('Tasks vivas', taskCount + '/' + total, cls),
      row('Endpoints', data.endpoints_count),
    ]);
  }

  function renderPrometheus(data) {
    const snap = data && data.snapshot;
    const stats = (snap && snap.stats) || {};
    const audit = (data && data.audit_log) || {};
    const enabled = data && data.enabled;
    const enabledCls = enabled ? 'lh-val' : 'lh-warn';
    return el('div', { className: 'lh-card' }, [
      el('h4', { text: '🔮 Prometheus (learning)' }),
      row('Enabled', enabled ? 'YES' : 'NO', enabledCls),
      row('Observations', stats.observations_emitted || 0),
      row('Learnings', stats.learnings_emitted || 0),
      row('Audit total', audit.total_events || 0),
    ]);
  }

  function renderVault(data) {
    const writers = (data && data.writers) || {};
    const enabledCount = data.writers_enabled_count || 0;
    const total = Object.keys(writers).length || 1;
    const total7d = data.total_writes_7d || 0;
    const cls = enabledCount === 0 ? 'lh-bad' : (enabledCount < total ? 'lh-warn' : 'lh-val');
    return el('div', { className: 'lh-card' }, [
      el('h4', { text: '🧠 Vault (segundo cérebro)' }),
      row('Writers ativos', enabledCount + '/' + total, cls),
      row('Writes 7d', total7d, total7d > 0 ? 'lh-val' : 'lh-warn'),
      row('Path', (data.vault_path || '').split('/').pop() || '—'),
      row('Vault existe', data.vault_available ? 'YES' : 'NO',
          data.vault_available ? 'lh-val' : 'lh-bad'),
    ]);
  }

  function renderImplementer(data) {
    const bg = (data && data.background) || {};
    const hist = (data && data.history) || {};
    const by = hist.by_status || {};
    const enabledCls = bg.enabled ? 'lh-val' : 'lh-warn';
    const runningCls = bg.running ? 'lh-val' : 'lh-warn';
    return el('div', { className: 'lh-card' }, [
      el('h4', { text: '⚙️ Implementer Squad' }),
      row('Background', bg.enabled ? 'ENABLED' : 'DISABLED', enabledCls),
      row('Running', bg.running ? 'YES' : 'NO', runningCls),
      row('Auto-apply', bg.auto_apply ? 'YES' : 'NO (dry-run)'),
      row('History total', hist.total || 0),
      row('Successes', by.success || 0, (by.success || 0) > 0 ? 'lh-val' : 'lh-warn'),
    ]);
  }

  async function refresh(mount) {
    const [health, prometheus, vault, implementer] = await Promise.all([
      fetchJson(ENDPOINTS.health),
      fetchJson(ENDPOINTS.prometheus),
      fetchJson(ENDPOINTS.vault),
      fetchJson(ENDPOINTS.implementer),
    ]);

    const grid = el('div', { className: 'lh-grid' }, [
      renderHealth(health),
      renderPrometheus(prometheus),
      renderVault(vault),
      renderImplementer(implementer),
    ]);
    const foot = el('div', { className: 'lh-foot' });
    foot.textContent = 'Atualizado ' + new Date().toLocaleTimeString();

    mount.innerHTML = '';
    mount.appendChild(grid);
    mount.appendChild(foot);
  }

  function init() {
    const mount = document.getElementById('learning-hub-panel');
    if (!mount) return;
    mount.innerHTML = '<div class="lh-foot">Carregando…</div>';
    refresh(mount);
    setInterval(() => refresh(mount), POLL_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
