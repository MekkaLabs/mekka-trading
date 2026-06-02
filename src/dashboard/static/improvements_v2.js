/*
 * src/dashboard/static/improvements_v2.js
 * =========================================
 * Camada de UX adicional sobre a Central de Melhorias.
 *
 * Responsabilidades (NÃO substitui o app.js existente):
 *   1. Stats bar topo (#imp2-stats) — agrega total/novas/paradas/dev/merged/blocked
 *   2. Nova tab "Paradas" → mostra IMPs queued + sugestões de match via
 *      /api/improvements/queued (Memory Bridge)
 *   3. Botão "Aplicar match" envia POST /api/improvements/reconcile-manual
 *
 * Auto-monta quando #sec-improvements existe. Polling 60s.
 */

(function () {
  'use strict';

  const STATS_API = '/api/improvements';
  const QUEUED_API = '/api/improvements/queued';
  const RECONCILE_API = '/api/improvements/reconcile-manual';
  const KPI_API = '/api/improvements/kpi';
  const POLL_MS = 60000;

  // ── helpers ────────────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function setText(id, v) { const e = $(id); if (e) e.textContent = v == null ? '—' : v; }

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

  // ── Stats: agrega contadores das recommendations existentes ─────────
  async function refreshStats() {
    try {
      const r = await fetch(STATS_API, { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      const recs = (data && data.recommendations) || [];
      const stuck = recs.filter(x => x.status === 'pending' || !x.status).length;
      const dev = recs.filter(x => (x.dev_state || '').toLowerCase() === 'in_dev').length;
      const merged = recs.filter(x => (x.dev_state || '').toLowerCase() === 'merged').length;
      const blocked = recs.filter(x =>
        (x.status || '').toLowerCase() === 'rejected'
        || (x.dev_state || '').toLowerCase() === 'blocked').length;
      const novas = recs.filter(x =>
        !x.dev_state && (x.status === 'pending' || !x.status)).length;
      setText('imp2-stat-total', recs.length);
      setText('imp2-stat-new', novas);
      setText('imp2-stat-progress', dev);
      setText('imp2-stat-done', merged);
      setText('imp2-stat-blocked', blocked);
      // 'paradas' vem do endpoint queued
    } catch (e) {
      console.debug('[improvements_v2] stats falhou:', e);
    }
  }

  // ── KPI tile: Departamento de Melhoria Contínua (Sage v1+v2) ────────
  async function refreshKpi() {
    try {
      const r = await fetch(KPI_API, { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      const kpi = (data && data.kpi) || {};
      const impact = ((data && data.impact) || {}).counts || {};
      const snap = (data && data.latest_snapshot) || {};
      // Throughput (Sage v1)
      setText('imp2-kpi-accepted', kpi.accepted != null ? kpi.accepted : 0);
      setText('imp2-kpi-rejected', kpi.rejected != null ? kpi.rejected : 0);
      setText('imp2-kpi-rate', kpi.acceptance_rate != null ? kpi.acceptance_rate + '%' : '—');
      // Impacto medido (Sage v2)
      setText('imp2-kpi-effective', impact.effective != null ? impact.effective : 0);
      setText('imp2-kpi-neutral', impact.neutral != null ? impact.neutral : 0);
      setText('imp2-kpi-regression', impact.regression != null ? impact.regression : 0);
      setText('imp2-kpi-pending', impact.pending != null ? impact.pending : 0);
      // Saúde atual (último snapshot do Sage)
      setText('imp2-kpi-winrate', snap.win_rate != null ? snap.win_rate + '%' : '—');
      setText('imp2-kpi-errors', snap.errors_24h != null ? snap.errors_24h : '—');
      const tile = $('imp2-kpi');
      if (tile) tile.dataset.empty = '0';
    } catch (e) {
      console.debug('[improvements_v2] kpi falhou:', e);
    }
  }

  // ── Tab Paradas: consume /api/improvements/queued ───────────────────
  let _queuedCache = null;

  function renderStuckCards(report) {
    const container = $('imp2-stuck-cards');
    if (!container) return;
    container.innerHTML = '';
    const candidates = (report && report.candidates) || {};
    const noMatch = (report && report.no_match) || [];

    if (Object.keys(candidates).length === 0 && noMatch.length === 0) {
      container.appendChild(el('div', { className: 'imp2-stuck-empty' },
        '🎉 Nenhuma IMP parada — todas aprovadas estão sendo processadas.'));
      return;
    }

    // Sessão: com matches (priorizar — acionáveis)
    if (Object.keys(candidates).length > 0) {
      const header = el('h4', { style: 'margin: 8px 0 4px; color:#fbbf24; font-size:0.85rem;' },
        `⚠️ ${Object.keys(candidates).length} com matches sugeridos (verificar e aplicar)`);
      container.appendChild(header);
      Object.entries(candidates).forEach(([rec_id, matches]) => {
        const card = el('div', { className: 'imp2-stuck-card' });
        card.appendChild(el('div', { className: 'imp2-stuck-head' }, [
          el('span', { className: 'imp2-stuck-id' }, 'IMP-' + rec_id),
          el('span', { className: 'imp2-stuck-meta' }, matches.length + ' candidato(s)'),
        ]));
        const matchesWrap = el('div', { className: 'imp2-stuck-matches' });
        matches.forEach(m => {
          const row = el('div', { className: 'imp2-stuck-match' }, [
            el('span', { className: 'imp2-stuck-match-score' }, 'score ' + (m.score || 0).toFixed(2)),
            el('code', null, m.short_sha),
            el('span', { style: 'flex:1;color:#c5d4e6;' }, m.subject),
          ]);
          const applyBtn = el('button', {
            className: 'imp2-stuck-match-apply',
            onclick: () => applyMatch(rec_id, m.sha, m.subject, applyBtn),
          }, 'Aplicar');
          row.appendChild(applyBtn);
          matchesWrap.appendChild(row);
        });
        card.appendChild(matchesWrap);
        container.appendChild(card);
      });
    }

    // Sessão: sem matches (operador resolve manual)
    if (noMatch.length > 0) {
      container.appendChild(el('h4',
        { style: 'margin: 14px 0 4px; color:#7c8b9d; font-size:0.85rem;' },
        `📭 ${noMatch.length} sem match automático (resolver manualmente ou aguardar trabalho)`));
      const list = el('div');
      noMatch.forEach(rec_id => {
        list.appendChild(el('div', { className: 'imp2-stuck-card', style: 'border-color:rgba(124,139,157,0.3);' }, [
          el('span', { className: 'imp2-stuck-id' }, 'IMP-' + rec_id),
        ]));
      });
      container.appendChild(list);
    }
  }

  async function refreshQueued(force) {
    try {
      const r = await fetch(QUEUED_API + (force ? '?_t=' + Date.now() : ''), { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      _queuedCache = data;
      // Atualizar contador da tab 'paradas'
      const total = data.total_queued || 0;
      const tabBadge = document.querySelector('.impr-view[data-view="paradas"] .impr-view-n');
      if (tabBadge) tabBadge.textContent = total;
      setText('imp2-stat-stuck', total);
      // Re-render se tab visível
      const stuckList = $('imp2-stuck-list');
      if (stuckList && stuckList.style.display !== 'none') {
        renderStuckCards(data);
      }
    } catch (e) {
      console.debug('[improvements_v2] queued falhou:', e);
    }
  }

  async function applyMatch(rec_id, commit_sha, subject, btn) {
    if (!confirm(`Confirmar que o commit ${commit_sha.slice(0, 7)} resolveu IMP-${rec_id}?\n\n"${subject}"`)) return;
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
    try {
      const r = await fetch(RECONCILE_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rec_id, commit_sha, summary: subject }),
      });
      const data = await r.json();
      if (data && data.ok) {
        if (btn) { btn.textContent = '✓ reconciliado'; btn.style.background = 'rgba(155,232,164,0.3)'; }
        setTimeout(() => refreshQueued(true), 800);
        setTimeout(() => refreshStats(), 1200);
      } else {
        alert('Falhou: ' + (data && data.error || 'erro desconhecido'));
        if (btn) { btn.disabled = false; btn.textContent = 'Aplicar'; }
      }
    } catch (e) {
      alert('Erro de rede: ' + e.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Aplicar'; }
    }
  }

  // ── Tab switching: intercepta clicks pra mostrar/esconder stuck list ─
  function bindTabSwitching() {
    const views = document.querySelectorAll('.impr-view');
    if (!views.length) return;
    views.forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.getAttribute('data-view');
        const stuckList = $('imp2-stuck-list');
        const mainList = $('impr-list');
        if (!stuckList || !mainList) return;
        if (view === 'paradas') {
          stuckList.style.display = '';
          mainList.style.display = 'none';
          if (_queuedCache) renderStuckCards(_queuedCache);
          else refreshQueued(true);
        } else {
          stuckList.style.display = 'none';
          mainList.style.display = '';
        }
      });
    });
  }

  // ── Boot ─────────────────────────────────────────────────────────────
  function init() {
    const root = $('sec-improvements');
    if (!root || root.dataset.v2 === '1') return;
    root.dataset.v2 = '1';
    bindTabSwitching();
    refreshStats();
    refreshQueued(true);
    refreshKpi();
    setInterval(refreshStats, POLL_MS);
    setInterval(() => refreshQueued(false), POLL_MS);
    setInterval(refreshKpi, POLL_MS);
    // Hook no botão Atualizar pra refletir queued também
    const refreshBtn = $('impr-refresh');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        refreshStats();
        refreshQueued(true);
        refreshKpi();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // Retry defensivo
  let tries = 10;
  const iv = setInterval(() => {
    const root = $('sec-improvements');
    if (root && root.dataset.v2 !== '1') init();
    if (root && root.dataset.v2 === '1' || tries-- <= 0) clearInterval(iv);
  }, 300);
})();
