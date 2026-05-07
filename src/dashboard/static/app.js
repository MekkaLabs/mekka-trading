const statusPill = document.getElementById('status-pill');
const metricsRoot = document.getElementById('metrics');
const signalsBody = document.getElementById('signals-body');
const tradesBody = document.getElementById('trades-body');
const auditLog = document.getElementById('audit-log');

const canvas = document.getElementById('office-canvas');
const ctx = canvas.getContext('2d');

let currentOverview = null;
let tick = 0;

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

  const pulse = 0.65 + Math.sin(tick * 0.03) * 0.35;
  const screens = Math.max(1, currentOverview ? currentOverview.executions_today : 1);

  cube(-8, -8, 0, 16, 16, 0.2, { top: '#243252', right: '#17223b', left: '#1f2b47' });
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
    const payload = JSON.parse(event.data);
    renderMetrics(payload.overview);
    renderSignals(payload.signals || []);
    renderTrades(payload.trades || []);
    renderAudit(payload.audit || []);
  };
}

connect();
renderScene();
