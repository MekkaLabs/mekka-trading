// implementer_squad.js
// =====================
// Painel "Implementer Squad" — auto-mount num <section id="sec-implementer-squad">
// se existir, senão silently no-op (memória "feedback-preview-mcp-unreliable":
// módulos JS devem auto-montar).
//
// Mostra:
//   - Cost cap LLM (hoje / mês)
//   - Status dos writers de trading (Mentor/Cyclops/Vision)
//   - Mapping area → implementer
//   - 5 últimos runs do worker
//   - Botão "Rodar 1 batch agora" (POST /api/implementer/run-once)
//
// Refresh: 30s. Pause quando aba escondida.

(function () {
  'use strict';

  const ROOT_ID = 'sec-implementer-squad';
  const REFRESH_MS = 30_000;

  function $(id) { return document.getElementById(id); }

  function fmtUsd(v) {
    if (v === undefined || v === null) return '—';
    return '$' + Number(v).toFixed(2);
  }

  function fmtStatus(s) {
    const colors = {
      success:     '#7fd17f',
      partial:     '#e5c07b',
      recipe_only: '#61afef',
      skipped:     '#888',
      blocked:     '#d27575',
      failed:      '#e06c75',
    };
    return `<span style="color:${colors[s] || '#aaa'}">${s}</span>`;
  }

  function render(data, root) {
    if (data.error) {
      root.innerHTML = `<p class="muted-line" style="padding:14px">Erro: ${data.error}</p>`;
      return;
    }
    const cost = data.cost || {};
    const llm = data.llm || {};
    const hist = data.history || {};
    const tw = data.trading_writers || {};
    const areas = data.areas || {};

    const writerStatus = (w) =>
      w && w.enabled
        ? `<span style="color:#7fd17f">ON</span> · ${w.writes_window}/${w.cap_per_hour}/h`
        : '<span style="color:#888">off</span>';

    const recentRows = (hist.recent || []).slice(-5).reverse().map((r) => `
      <tr>
        <td style="color:#888">${(r.ts || '').slice(11,19)}</td>
        <td>IMP-${(r.rec_id || '').slice(0,8)}</td>
        <td style="color:#aaa">${r.agent}</td>
        <td>${fmtStatus(r.status)}</td>
        <td style="color:#888">${r.layer_used || '—'}</td>
        <td style="text-align:right">${r.files_changed?.length || 0}</td>
        <td style="text-align:right">${fmtUsd(r.cost_usd)}</td>
      </tr>
    `).join('');

    const areaRows = Object.entries(areas).map(([a, i]) => `
      <tr><td>${a}</td><td style="color:#aaa">${i}</td></tr>
    `).join('');

    root.innerHTML = `
      <div class="panel-hdr" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <h3 style="margin:0">🛠️ Implementer Squad</h3>
        <div>
          <button id="impl-run-once" style="padding:4px 10px">▶ Rodar 1 batch (dry-run)</button>
          <span id="impl-run-out" style="margin-left:8px;color:#888;font-size:0.85em"></span>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:18px">
        <div class="impl-card">
          <h4 style="margin:0 0 6px 0">💸 Custo LLM</h4>
          <div>Hoje: <b>${fmtUsd(cost.today_usd)}</b> / ${fmtUsd(cost.daily_cap_usd)}</div>
          <div>Mês:  <b>${fmtUsd(cost.month_usd)}</b> / ${fmtUsd(cost.monthly_cap_usd)}</div>
          <div style="color:#888;font-size:0.85em">${cost.total_events || 0} eventos</div>
        </div>
        <div class="impl-card">
          <h4 style="margin:0 0 6px 0">🤖 LLM Implementer</h4>
          <div>Modelo: <code>${llm.model || '—'}</code></div>
          <div>Enabled: ${llm.enabled ? '<span style="color:#7fd17f">YES</span>' : '<span style="color:#d27575">NO</span>'}</div>
          <div>SDK: ${llm.sdk_present ? '✓' : '✗'}</div>
        </div>
        <div class="impl-card">
          <h4 style="margin:0 0 6px 0">📝 Trading writers</h4>
          <div>Mentor:  ${writerStatus(tw.mentor)}</div>
          <div>Cyclops: ${writerStatus(tw.cyclops)}</div>
          <div>Vision:  ${writerStatus(tw.vision)}</div>
        </div>
        <div class="impl-card">
          <h4 style="margin:0 0 6px 0">📊 Histórico</h4>
          <div>Total: <b>${hist.total || 0}</b></div>
          ${Object.entries(hist.by_status || {}).map(([s,c]) =>
            `<div>${fmtStatus(s)}: ${c}</div>`).join('')}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:2fr 1fr;gap:14px">
        <div>
          <h4 style="margin:0 0 6px 0">⏱️ Últimos 5 runs</h4>
          ${recentRows
            ? `<table class="impl-table"><thead><tr>
                <th>Hora</th><th>IMP</th><th>Agente</th><th>Status</th><th>Camada</th>
                <th style="text-align:right">Arq.</th><th style="text-align:right">$</th>
              </tr></thead><tbody>${recentRows}</tbody></table>`
            : '<p class="muted-line">Nenhum run ainda. Clique em "Rodar 1 batch".</p>'}
        </div>
        <div>
          <h4 style="margin:0 0 6px 0">🗺️ Roteamento area → agente</h4>
          <table class="impl-table">
            <thead><tr><th>area</th><th>agente</th></tr></thead>
            <tbody>${areaRows}</tbody>
          </table>
        </div>
      </div>

      <style>
        #${ROOT_ID} .impl-card {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 6px;
          padding: 10px 12px;
          font-size: 0.9em;
        }
        #${ROOT_ID} .impl-card h4 { font-size: 0.95em; color: #c8d4e8; }
        #${ROOT_ID} .impl-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
        #${ROOT_ID} .impl-table th { text-align: left; color: #888; font-weight: normal; padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); }
        #${ROOT_ID} .impl-table td { padding: 4px 8px; border-bottom: 1px dotted rgba(255,255,255,0.04); }
      </style>
    `;

    const btn = $('impl-run-once');
    const out = $('impl-run-out');
    if (btn) {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        out.textContent = 'Rodando…';
        try {
          const res = await fetch('/api/implementer/run-once', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({max: 3, dry_run: true}),
          });
          const j = await res.json();
          out.textContent = `${j.processed} processadas, ${j.success} success`;
          // Reload depois de 1s pra mostrar history atualizado
          setTimeout(refresh, 1000);
        } catch (e) {
          out.textContent = 'erro: ' + e.message;
        } finally {
          btn.disabled = false;
        }
      });
    }
  }

  let _timer = null;

  async function refresh() {
    const root = $(ROOT_ID);
    if (!root) return;
    try {
      const r = await fetch('/api/implementer/status', {cache: 'no-store'});
      const j = await r.json();
      render(j, root);
    } catch (e) {
      root.innerHTML = `<p class="muted-line" style="padding:14px">Erro: ${e.message}</p>`;
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
