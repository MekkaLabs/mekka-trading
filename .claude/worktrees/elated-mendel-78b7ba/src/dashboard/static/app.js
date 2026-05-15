const statusPill = document.getElementById('status-pill');
const metricsRoot = document.getElementById('metrics');
const signalsBody = document.getElementById('signals-body');
const tradesBody = document.getElementById('trades-body');
const auditLog = document.getElementById('audit-log');
const layerMap = document.getElementById('layer-map');
const timelineRoot = document.getElementById('timeline');
const riskHeatmap = document.getElementById('risk-heatmap');
const anomalyConsole = document.getElementById('anomaly-console');
const symbolTimeline = document.getElementById('symbol-timeline');
const globalAlerts = document.getElementById('global-alerts');
const heroSla = document.getElementById('hero-sla');
const filterSymbol = document.getElementById('filter-symbol');
const filterHero = document.getElementById('filter-hero');
const filterEvent = document.getElementById('filter-event');
const replayLiveBtn = document.getElementById('replay-live');
const replayPrevBtn = document.getElementById('replay-prev');
const replayPlayBtn = document.getElementById('replay-play');
const replayNextBtn = document.getElementById('replay-next');
const replaySnapshotSelect = document.getElementById('replay-snapshot');
const replayExportJsonBtn = document.getElementById('replay-export-json');
const replayExportCsvBtn = document.getElementById('replay-export-csv');
const exportStartUtc = document.getElementById('export-start-utc');
const exportEndUtc = document.getElementById('export-end-utc');
const replayStatus = document.getElementById('replay-status');
const incidentLatestBtn = document.getElementById('incident-latest');
const compareA = document.getElementById('compare-a');
const compareB = document.getElementById('compare-b');
const compareRunBtn = document.getElementById('compare-run');
const compareOutput = document.getElementById('compare-output');
const incidentDownloadBtn = document.getElementById('incident-download');
const chartsRefreshBtn = document.getElementById('charts-refresh');
const queueRefreshBtn = document.getElementById('queue-refresh');
const chartsStatus = document.getElementById('charts-status');
const incidentQueueRoot = document.getElementById('incident-queue');
const chartCanvases = {
  signals: document.getElementById('chart-signals'),
  trades: document.getElementById('chart-trades'),
  alerts: document.getElementById('chart-alerts'),
};
const riskModal = document.getElementById('risk-modal');
const riskModalBody = document.getElementById('risk-modal-body');
const riskModalTitle = document.getElementById('risk-modal-title');
const riskModalClose = document.getElementById('risk-modal-close');

const canvas = document.getElementById('office-canvas');
const ctx = canvas.getContext('2d');

let currentOverview = null;
let tick = 0;
let lastPayload = null;
let sceneAlertLevel = 'normal';
let currentRiskDrilldown = {};
let hasGlobalCriticalAlert = false;
let replayMode = 'live';
let replaySnapshots = [];
let replayIndex = -1;
let replayTimer = null;
const chartInstances = { signals: null, trades: null, alerts: null };
let chartsAutoRefreshTimer = null;
let queueAutoRefreshTimer = null;

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString('pt-BR', { hour12: false });
  } catch {
    return ts;
  }
}

function fmtMoney(v) {
  return Number(v || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function renderMetrics(overview) {
  currentOverview = overview;
  const cards = [
    ['Mode', overview.mode],
    ['Network', overview.network],
    ['Signals (total)', overview.total_signals],
    ['Trades (total)', overview.total_trades],
    ['Trades hoje', overview.trades_today],
    ['Execuções hoje', overview.executions_today],
  ];
  metricsRoot.innerHTML = cards.map(([label, value]) => `<div class="card"><strong>${value}</strong><span>${label}</span></div>`).join('');
}

function renderSignals(rows) {
  signalsBody.innerHTML = rows.map((r) => (
    `<tr><td>${fmtTime(r.timestamp)}</td><td>${r.symbol}</td><td>${r.action}</td><td>${(r.confidence * 100).toFixed(0)}%</td></tr>`
  )).join('');
}

function renderTrades(rows) {
  tradesBody.innerHTML = rows.map((r) => (
    `<tr><td>${fmtTime(r.timestamp)}</td><td>${r.symbol}</td><td>${r.status}</td><td>${fmtMoney(r.notional_usd)}</td></tr>`
  )).join('');
}

function renderAudit(rows) {
  auditLog.innerHTML = rows.map((r) => {
    const warn = r.severity !== 'INFO' && r.severity !== 'DEBUG' ? 'warn' : '';
    return `<div class="log-row ${warn}"><span class="time">${fmtTime(r.timestamp)}</span><span class="agent">${r.agent}</span>${r.event} — ${r.message || ''}</div>`;
  }).join('');
}

function renderLayers(layers) {
  if (!layers || !layers.items) {
    layerMap.innerHTML = '';
    sceneAlertLevel = 'normal';
    return;
  }
  const entries = Object.entries(layers.items);
  let hasWarning = false;
  let hasCritical = false;
  layerMap.innerHTML = entries.map(([code, layer]) => {
    const chips = (layer.heroes || []).map((h) => {
      if (h.status === 'warning') hasWarning = true;
      if (h.status === 'critical') hasCritical = true;
      return `<span class="hero-chip ${h.status}" title="${h.event}">${h.hero}</span>`;
    }).join('');
    return `<div class="layer-box"><h3>${code} • ${layer.label}</h3>${chips}</div>`;
  }).join('');
  sceneAlertLevel = hasCritical ? 'critical' : (hasWarning ? 'warning' : 'normal');
}

function renderTimeline(rows) {
  timelineRoot.innerHTML = (rows || []).map((r) => {
    const cls = r.severity === 'WARNING' ? 'warning' : (r.severity === 'ERROR' || r.severity === 'CRITICAL' ? 'critical' : '');
    return `<div class="timeline-row ${cls}"><span>${fmtTime(r.timestamp)}</span><span class="event">${r.event}</span><span>${r.message || ''}</span></div>`;
  }).join('');
}

function renderSymbolTimeline(rows) {
  symbolTimeline.innerHTML = (rows || []).map((r) => {
    const chips = (r.steps || []).map((s) => `<span class="step-chip">${s.agent}:${s.event}</span>`).join('');
    return `<div class="symbol-row"><strong>${r.symbol}</strong> • ${r.duration_seconds}s • ${fmtTime(r.last_at)}<div>${chips}</div></div>`;
  }).join('');
}

function renderRiskHeatmap(rows) {
  riskHeatmap.innerHTML = (rows || []).map((r) => {
    return `<div class="risk-cell"><strong>${r.symbol}</strong><div class="risk-bars">
      <div class="risk-bar approved">A ${r.approved}</div>
      <div class="risk-bar reduced">R ${r.reduced}</div>
      <div class="risk-bar rejected">X ${r.rejected}</div>
      <div class="risk-bar kill">K ${r.kill_switch}</div>
    </div><button type="button" data-symbol="${r.symbol}" class="open-drill">Ver detalhes</button></div>`;
  }).join('');

  riskHeatmap.querySelectorAll('.open-drill').forEach((btn) => {
    btn.addEventListener('click', () => {
      openRiskDrilldown(btn.dataset.symbol || '');
    });
  });
}

function renderAnomalies(rows) {
  anomalyConsole.innerHTML = (rows || []).map((r) => {
    const sev = String(r.severity || '').toLowerCase();
    const sevClass = sev.includes('high') || sev.includes('critical') ? 'high' : (sev.includes('medium') ? 'medium' : '');
    const pauseClass = r.should_pause ? 'pause' : '';
    return `<div class="anomaly-row ${pauseClass}"><span>${fmtTime(r.timestamp)}</span><span class="anomaly-sev ${sevClass}">${r.severity}</span><span>${r.symbol || '-'}</span> ${r.event} ${r.should_pause ? '[PAUSE]' : ''} — ${r.message || ''}</div>`;
  }).join('');
}

function renderHeroSla(rows) {
  heroSla.innerHTML = (rows || []).map((r) => {
    const avg = r.avg_seconds == null ? '-' : r.avg_seconds;
    const p95 = r.p95_seconds == null ? '-' : r.p95_seconds;
    return `<div class="sla-row"><strong>${r.hero}</strong>AVG: ${avg}s • P95: ${p95}s • n=${r.samples}</div>`;
  }).join('');
}

function renderGlobalAlerts(rows) {
  hasGlobalCriticalAlert = false;
  if (!rows || rows.length === 0) {
    globalAlerts.innerHTML = '';
    return;
  }
  globalAlerts.innerHTML = rows.map((r) => {
    if (String(r.severity || '').toUpperCase() === 'CRITICAL') hasGlobalCriticalAlert = true;
    const cls = String(r.severity || '').toUpperCase() === 'WARNING' ? 'warning' : '';
    return `<div class="alert-banner ${cls}">${r.code}: ${r.message}</div>`;
  }).join('');
}

function openRiskDrilldown(symbol) {
  const rows = currentRiskDrilldown[symbol] || [];
  riskModalTitle.textContent = `Batman Drilldown • ${symbol}`;
  riskModalBody.innerHTML = rows.map((r) => {
    const reasons = (r.reasons || []).length ? r.reasons.join(', ') : '-';
    const breached = (r.breached_limits || []).length ? r.breached_limits.join(', ') : '-';
    return `<div class="drill-row"><span class="drill-meta">${fmtTime(r.timestamp)} ${r.event}</span>${r.message || ''}<br/>Reasons: ${reasons}<br/>Breached: ${breached}</div>`;
  }).join('') || '<div class="drill-row">Sem detalhes.</div>';
  riskModal.classList.remove('hidden');
}

function closeRiskDrilldown() {
  riskModal.classList.add('hidden');
}

function applyFilters(payload) {
  const symbol = (filterSymbol.value || '').trim().toUpperCase();
  const hero = (filterHero.value || '').trim().toLowerCase();
  const event = (filterEvent.value || '').trim().toLowerCase();

  const signals = (payload.signals || []).filter((r) => !symbol || (r.symbol || '').toUpperCase().includes(symbol));
  const trades = (payload.trades || []).filter((r) => !symbol || (r.symbol || '').toUpperCase().includes(symbol));
  const audit = (payload.audit || []).filter((r) => {
    const heroOk = !hero || (r.agent || '').toLowerCase().includes(hero);
    const eventOk = !event || (r.event || '').toLowerCase().includes(event);
    const symbolOk = !symbol || (r.symbol || '').toUpperCase().includes(symbol) || (r.message || '').toUpperCase().includes(symbol);
    return heroOk && eventOk && symbolOk;
  });
  const timeline = (payload.timeline || []).filter((r) => {
    const eventOk = !event || (r.event || '').toLowerCase().includes(event);
    const symbolOk = !symbol || (r.symbol || '').toUpperCase().includes(symbol) || (r.message || '').toUpperCase().includes(symbol);
    return eventOk && symbolOk;
  });
  const heatmap = (payload.risk_heatmap || []).filter((r) => !symbol || (r.symbol || '').toUpperCase().includes(symbol));
  const symbols = (payload.symbol_timeline || []).filter((r) => !symbol || (r.symbol || '').toUpperCase().includes(symbol));
  const anomalies = (payload.anomalies || []).filter((r) => {
    const eventOk = !event || (r.event || '').toLowerCase().includes(event);
    const symbolOk = !symbol || (r.symbol || '').toUpperCase().includes(symbol) || (r.message || '').toUpperCase().includes(symbol);
    return eventOk && symbolOk;
  });
  const sla = payload.hero_sla || [];

  renderSignals(signals);
  renderTrades(trades);
  renderAudit(audit);
  renderTimeline(timeline);
  renderSymbolTimeline(symbols);
  currentRiskDrilldown = payload.risk_drilldown || {};
  renderRiskHeatmap(heatmap);
  renderAnomalies(anomalies);
  renderHeroSla(sla);
  renderGlobalAlerts(payload.global_alerts || []);
  renderLayers(payload.layers || null);
}

function bindFilterEvents() {
  [filterSymbol, filterHero, filterEvent].forEach((el) => {
    el.addEventListener('input', () => {
      if (lastPayload) applyFilters(lastPayload);
    });
  });
}

function iso(x, y, z, scale = 18) {
  return {
    x: (x - y) * scale,
    y: (x + y) * scale * 0.5 - z * scale,
  };
}

function cube(x, y, z, w, h, d, color) {
  const p = [
    iso(x, y, z),
    iso(x + w, y, z),
    iso(x + w, y + h, z),
    iso(x, y + h, z),
    iso(x, y, z + d),
    iso(x + w, y, z + d),
    iso(x + w, y + h, z + d),
    iso(x, y + h, z + d),
  ];

  const cx = canvas.width * 0.5;
  const cy = canvas.height * 0.7;

  function drawFace(indexes, shade) {
    ctx.beginPath();
    indexes.forEach((idx, i) => {
      const pt = p[idx];
      if (i === 0) ctx.moveTo(cx + pt.x, cy + pt.y);
      else ctx.lineTo(cx + pt.x, cy + pt.y);
    });
    ctx.closePath();
    ctx.fillStyle = shade;
    ctx.fill();
    ctx.strokeStyle = 'rgba(15,22,40,0.6)';
    ctx.stroke();
  }

  drawFace([0, 1, 2, 3], color.top);
  drawFace([1, 5, 6, 2], color.right);
  drawFace([0, 4, 5, 1], color.left);
}

function renderScene() {
  tick += 1;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  let pulse = 0.65 + Math.sin(tick * 0.03) * 0.35;
  let floorTop = '#243252';
  const effectiveAlert = hasGlobalCriticalAlert ? 'critical' : sceneAlertLevel;
  if (effectiveAlert === 'warning') {
    pulse = 0.8 + Math.sin(tick * 0.05) * 0.5;
    floorTop = '#3a3022';
  }
  if (effectiveAlert === 'critical') {
    pulse = 1.0 + Math.sin(tick * 0.08) * 0.8;
    floorTop = '#4a1f24';
  }
  const screens = Math.max(1, currentOverview ? currentOverview.executions_today : 1);

  cube(-8, -8, 0, 16, 16, 0.2, { top: floorTop, right: '#17223b', left: '#1f2b47' });
  cube(-6, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });
  cube(-2.2, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });
  cube(1.6, -4, 0.2, 2.8, 1.2, 1.2, { top: '#415886', right: '#2b3f66', left: '#364d79' });

  for (let i = 0; i < Math.min(screens, 6); i += 1) {
    const x = -6 + i * 2.1;
    const glow = Math.floor(120 + 120 * pulse);
    cube(x, -2.4, 1.4, 1.6, 0.3, 1.2, {
      top: `rgb(${40 + i * 10}, ${glow}, 255)`,
      right: '#2f446d',
      left: '#24385d',
    });
  }

  const move = Math.sin(tick * 0.06) * 0.8;
  cube(-1.1 + move, 1.6, 0.2, 1.0, 1.0, 1.6, { top: '#ffbe55', right: '#c3842d', left: '#e19f3f' });
  cube(-1.1 + move, 1.6, 1.8, 1.0, 1.0, 0.7, { top: '#ffe4c5', right: '#f0cfa8', left: '#f8daba' });

  requestAnimationFrame(renderScene);
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    statusPill.textContent = 'Online';
    statusPill.style.color = '#49d17a';
  };

  ws.onclose = () => {
    statusPill.textContent = 'Reconectando...';
    statusPill.style.color = '#ff8f57';
    setTimeout(connect, 1500);
  };

  ws.onmessage = (event) => {
    if (replayMode !== 'live') return;
    const payload = JSON.parse(event.data);
    lastPayload = payload;
    renderMetrics(payload.overview);
    applyFilters(payload);
  };
}

async function loadReplaySnapshots() {
  try {
    const res = await fetch('/api/replay/snapshots');
    const data = await res.json();
    replaySnapshots = data.snapshots || [];
    replaySnapshotSelect.innerHTML = replaySnapshots.map((s, idx) => `<option value="${idx}">${s}</option>`).join('');
    compareA.innerHTML = replaySnapshots.map((s) => `<option value="${s}">${s}</option>`).join('');
    compareB.innerHTML = replaySnapshots.map((s) => `<option value="${s}">${s}</option>`).join('');
    if (replaySnapshots.length > 0) {
      replayIndex = 0;
      replaySnapshotSelect.value = '0';
      compareA.value = replaySnapshots[0];
      compareB.value = replaySnapshots[Math.min(1, replaySnapshots.length - 1)];
    }
  } catch {
    replaySnapshots = [];
    replaySnapshotSelect.innerHTML = '';
    compareA.innerHTML = '';
    compareB.innerHTML = '';
  }
}

async function loadReplayByIndex(index) {
  if (index < 0 || index >= replaySnapshots.length) return;
  replayMode = 'replay';
  replayIndex = index;
  replaySnapshotSelect.value = String(index);
  const name = replaySnapshots[index];
  const res = await fetch(`/api/replay?snapshot=${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const payload = await res.json();
  lastPayload = payload;
  replayStatus.textContent = `Replay: ${name}`;
  renderMetrics(payload.overview);
  applyFilters(payload);
}

function setLiveMode() {
  replayMode = 'live';
  replayStatus.textContent = 'Live stream ativo';
  if (replayTimer) {
    clearInterval(replayTimer);
    replayTimer = null;
    replayPlayBtn.textContent = 'Play';
  }
}

function toggleReplayPlay() {
  if (replayMode === 'live') return;
  if (replayTimer) {
    clearInterval(replayTimer);
    replayTimer = null;
    replayPlayBtn.textContent = 'Play';
    return;
  }
  replayPlayBtn.textContent = 'Pause';
  replayTimer = setInterval(() => {
    if (replayIndex + 1 >= replaySnapshots.length) {
      clearInterval(replayTimer);
      replayTimer = null;
      replayPlayBtn.textContent = 'Play';
      return;
    }
    loadReplayByIndex(replayIndex + 1);
  }, 1200);
}

function currentExportRange() {
  if (replaySnapshots.length === 0) return { start: null, end: null };
  const start = replaySnapshots[replaySnapshots.length - 1];
  const end = replaySnapshots[0];
  return { start, end };
}

function exportReplay(format) {
  const { start, end } = currentExportRange();
  if (!start || !end) return;
  const startUtc = (exportStartUtc.value || '').trim();
  const endUtc = (exportEndUtc.value || '').trim();
  let url = `/api/replay/export?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=${encodeURIComponent(format)}`;
  if (startUtc) url += `&start_utc=${encodeURIComponent(startUtc)}`;
  if (endUtc) url += `&end_utc=${encodeURIComponent(endUtc)}`;
  window.open(url, '_blank');
}

async function runCompare() {
  const a = compareA.value;
  const b = compareB.value;
  if (!a || !b) return;
  const res = await fetch(`/api/replay/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (!res.ok) {
    compareOutput.textContent = 'Falha na comparação.';
    return;
  }
  const d = await res.json();
  const ov = d.overview_delta || {};
  const riskRows = (d.risk_delta || []).map((r) => `<tr><td>${r.symbol}</td><td>${r.approved}</td><td>${r.reduced}</td><td>${r.rejected}</td><td>${r.kill_switch}</td></tr>`).join('');
  const slaRows = (d.sla_delta || []).map((s) => `<tr><td>${s.hero}</td><td>${s.avg_seconds_delta}</td><td>${s.samples_delta}</td></tr>`).join('');
  const alertsAdded = (d.alerts_added || []).map((x) => `<div>+ ${x}</div>`).join('') || '<div>-</div>';
  const alertsRemoved = (d.alerts_removed || []).map((x) => `<div>- ${x}</div>`).join('') || '<div>-</div>';
  compareOutput.innerHTML = `
    <div><strong>${d.snapshot_a}</strong> vs <strong>${d.snapshot_b}</strong></div>
    <div>Overview Δ: signals ${ov.total_signals}, trades ${ov.total_trades}, trades_today ${ov.trades_today}, exec_today ${ov.executions_today}</div>
    <div>Alerts Added</div>${alertsAdded}
    <div>Alerts Removed</div>${alertsRemoved}
    <table class="compare-table"><thead><tr><th>Symbol</th><th>ΔApproved</th><th>ΔReduced</th><th>ΔRejected</th><th>ΔKill</th></tr></thead><tbody>${riskRows}</tbody></table>
    <table class="compare-table"><thead><tr><th>Hero</th><th>ΔAvg(s)</th><th>ΔSamples</th></tr></thead><tbody>${slaRows}</tbody></table>
  `;
}

function downloadIncidentBundle() {
  // Triggers /api/replay/incident/latest/download which returns the JSON
  // bundle with Content-Disposition: attachment, so the browser saves it.
  window.location.href = '/api/replay/incident/latest/download';
}

function severityClass(tier) {
  const t = String(tier || '').toUpperCase();
  if (t === 'CRITICAL') return 'sev-critical';
  if (t === 'HIGH') return 'sev-high';
  if (t === 'MEDIUM') return 'sev-medium';
  if (t === 'LOW') return 'sev-low';
  return 'sev-none';
}

function fmtSnapshotLabel(name) {
  const m = String(name || '').match(/snapshot-(\d{8})T(\d{4})\.json/);
  if (!m) return name;
  const d = m[1];
  const t = m[2];
  return `${d.slice(4, 6)}/${d.slice(6, 8)} ${t.slice(0, 2)}:${t.slice(2, 4)}`;
}

function ensureLineChart(key, label, color) {
  if (!chartCanvases[key]) return null;
  if (typeof Chart === 'undefined') return null;
  if (chartInstances[key]) return chartInstances[key];
  chartInstances[key] = new Chart(chartCanvases[key], {
    type: 'line',
    data: { labels: [], datasets: [{
      label,
      data: [],
      borderColor: color,
      backgroundColor: color.replace('1)', '0.18)'),
      borderWidth: 2,
      tension: 0.25,
      pointRadius: 0,
      fill: true,
    }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#95a3c4', maxTicksLimit: 8 }, grid: { color: 'rgba(72,151,255,0.06)' } },
        y: { ticks: { color: '#95a3c4' }, grid: { color: 'rgba(72,151,255,0.08)' }, beginAtZero: true },
      },
    },
  });
  return chartInstances[key];
}

function ensureMultiLineChart(key, datasets) {
  if (!chartCanvases[key]) return null;
  if (typeof Chart === 'undefined') return null;
  if (chartInstances[key]) return chartInstances[key];
  chartInstances[key] = new Chart(chartCanvases[key], {
    type: 'line',
    data: { labels: [], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { labels: { color: '#cfe4ff', boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#95a3c4', maxTicksLimit: 8 }, grid: { color: 'rgba(72,151,255,0.06)' } },
        y: { ticks: { color: '#95a3c4' }, grid: { color: 'rgba(72,151,255,0.08)' }, beginAtZero: true },
      },
    },
  });
  return chartInstances[key];
}

async function loadReplayCharts() {
  if (typeof Chart === 'undefined') {
    chartsStatus.textContent = 'Chart.js indisponivel (offline?). Charts desativados.';
    return;
  }
  try {
    const res = await fetch('/api/replay/timeseries?limit=180');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      chartsStatus.textContent = 'Sem snapshots persistidos ainda.';
      return;
    }
    const labels = items.map((it) => fmtSnapshotLabel(it.snapshot));
    const signalsData = items.map((it) => it.signals_total || 0);
    const tradesData = items.map((it) => it.trades_total || 0);
    const alertsData = items.map((it) => it.alerts_count || 0);
    const severityData = items.map((it) => it.severity_score || 0);

    const signalsChart = ensureLineChart('signals', 'Signals', 'rgba(69, 208, 255, 1)');
    const tradesChart = ensureLineChart('trades', 'Trades', 'rgba(73, 209, 122, 1)');
    const alertsChart = ensureMultiLineChart('alerts', [
      {
        label: 'Alerts',
        data: [],
        borderColor: 'rgba(255, 143, 87, 1)',
        backgroundColor: 'rgba(255, 143, 87, 0.18)',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 0,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Severity score',
        data: [],
        borderColor: 'rgba(255, 110, 110, 1)',
        backgroundColor: 'rgba(255, 110, 110, 0.12)',
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 0,
        fill: false,
        borderDash: [5, 4],
        yAxisID: 'y',
      },
    ]);

    if (signalsChart) {
      signalsChart.data.labels = labels;
      signalsChart.data.datasets[0].data = signalsData;
      signalsChart.update();
    }
    if (tradesChart) {
      tradesChart.data.labels = labels;
      tradesChart.data.datasets[0].data = tradesData;
      tradesChart.update();
    }
    if (alertsChart) {
      alertsChart.data.labels = labels;
      alertsChart.data.datasets[0].data = alertsData;
      alertsChart.data.datasets[1].data = severityData;
      alertsChart.update();
    }

    const last = items[items.length - 1];
    chartsStatus.textContent = `${items.length} pontos | ultimo: ${fmtSnapshotLabel(last.snapshot)} | severidade ${last.severity_tier}`;
  } catch (err) {
    chartsStatus.textContent = 'Falha ao carregar charts: ' + err.message;
  }
}

async function loadIncidentQueue() {
  try {
    const res = await fetch('/api/incidents/queue?limit=15');
    if (!res.ok) throw new Error('http ' + res.status);
    const data = await res.json();
    const items = data.items || [];
    if (!items.length) {
      incidentQueueRoot.innerHTML = '<div class="muted-line">Sem incidentes ativos.</div>';
      return;
    }
    incidentQueueRoot.innerHTML = items.map((it, idx) => {
      const drivers = it.drivers || {};
      const driverChips = [
        drivers.kill_switch ? `<span class="driver kill">kill x${drivers.kill_switch}</span>` : '',
        drivers.critical_alerts ? `<span class="driver crit">crit x${drivers.critical_alerts}</span>` : '',
        drivers.warning_alerts ? `<span class="driver warn">warn x${drivers.warning_alerts}</span>` : '',
        drivers.anomaly_pause ? `<span class="driver anom">pause x${drivers.anomaly_pause}</span>` : '',
        drivers.breached_limits ? `<span class="driver breach">breach x${drivers.breached_limits}</span>` : '',
        drivers.sla_degraded ? `<span class="driver sla">sla x${drivers.sla_degraded}</span>` : '',
      ].filter(Boolean).join(' ');
      const sevClass = severityClass(it.tier);
      return `
        <div class="incident-row ${sevClass}">
          <div class="incident-head">
            <span class="rank">#${idx + 1}</span>
            <span class="badge ${sevClass}">${it.tier} ${it.score}</span>
            <strong>${fmtSnapshotLabel(it.snapshot)}</strong>
            <span class="muted-line">${it.snapshot}</span>
            <button type="button" data-snapshot="${it.snapshot}" class="open-incident-replay">Replay</button>
          </div>
          <div class="incident-drivers">${driverChips || '<span class="muted-line">sem drivers</span>'}</div>
        </div>`;
    }).join('');
    incidentQueueRoot.querySelectorAll('.open-incident-replay').forEach((btn) => {
      btn.addEventListener('click', () => {
        const name = btn.dataset.snapshot;
        const idx = replaySnapshots.indexOf(name);
        if (idx >= 0) loadReplayByIndex(idx);
      });
    });
  } catch (err) {
    incidentQueueRoot.innerHTML = `<div class="muted-line">Falha ao carregar fila: ${err.message}</div>`;
  }
}

async function loadIncidentLatest() {
  const res = await fetch('/api/replay/incident/latest');
  if (!res.ok) {
    compareOutput.textContent = 'Nenhum incident bundle de kill switch encontrado.';
    return;
  }
  const d = await res.json();
  const alerts = (d.alerts || []).map((a) => `<div>${a.code}: ${a.message}</div>`).join('');
  const sev = d.severity || {};
  const sevClass = severityClass(sev.tier);
  compareOutput.innerHTML = `
    <div><strong>Incident Bundle</strong> <span class="badge ${sevClass}">${sev.tier || 'NONE'} ${sev.score ?? 0}</span></div>
    <div>Snapshot incidente: ${d.incident_snapshot}</div>
    <div>Snapshot baseline: ${d.baseline_snapshot}</div>
    <div>${alerts}</div>
    <div>Overview: signals=${d.overview.total_signals ?? '-'} trades=${d.overview.total_trades ?? '-'}</div>
  `;
}

connect();
bindFilterEvents();
loadReplaySnapshots();
riskModalClose.addEventListener('click', closeRiskDrilldown);
riskModal.addEventListener('click', (e) => {
  if (e.target === riskModal) closeRiskDrilldown();
});
replayLiveBtn.addEventListener('click', setLiveMode);
replayPrevBtn.addEventListener('click', () => {
  if (replayMode === 'live') return;
  loadReplayByIndex(Math.max(0, replayIndex - 1));
});
replayNextBtn.addEventListener('click', () => {
  if (replayMode === 'live') return;
  loadReplayByIndex(Math.min(replaySnapshots.length - 1, replayIndex + 1));
});
replayPlayBtn.addEventListener('click', toggleReplayPlay);
replaySnapshotSelect.addEventListener('change', (e) => {
  const idx = Number(e.target.value);
  if (!Number.isFinite(idx)) return;
  loadReplayByIndex(idx);
});
replayExportJsonBtn.addEventListener('click', () => exportReplay('json'));
replayExportCsvBtn.addEventListener('click', () => exportReplay('csv'));
compareRunBtn.addEventListener('click', runCompare);
incidentLatestBtn.addEventListener('click', loadIncidentLatest);
if (incidentDownloadBtn) incidentDownloadBtn.addEventListener('click', downloadIncidentBundle);
if (chartsRefreshBtn) chartsRefreshBtn.addEventListener('click', loadReplayCharts);
if (queueRefreshBtn) queueRefreshBtn.addEventListener('click', loadIncidentQueue);

function bootCharts() {
  loadReplayCharts();
  if (chartsAutoRefreshTimer) clearInterval(chartsAutoRefreshTimer);
  chartsAutoRefreshTimer = setInterval(loadReplayCharts, 30000);
}
function bootQueue() {
  loadIncidentQueue();
  if (queueAutoRefreshTimer) clearInterval(queueAutoRefreshTimer);
  queueAutoRefreshTimer = setInterval(loadIncidentQueue, 30000);
}
// Chart.js is loaded with `defer`, so wait for DOMContentLoaded once.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { bootCharts(); bootQueue(); });
} else {
  bootCharts();
  bootQueue();
}
renderScene();
