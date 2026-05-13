import { AGENTS, normalizeAgentId } from './roster.js';

const AGENT_NAMES = new Map(AGENTS.map((a) => [a.id, a.name]));

function nowTime() {
  return new Date().toLocaleTimeString('pt-BR', { hour12: false });
}

function toTaskMapFromAudit(rows = []) {
  const out = {};
  for (const row of rows) {
    const id = normalizeAgentId(row.agent);
    if (!AGENT_NAMES.has(id)) continue;
    if (out[id]) continue;
    const event = row.event || 'EVENT';
    const symbol = row.symbol ? ` (${row.symbol})` : '';
    out[id] = `${event}${symbol}`;
  }
  AGENTS.forEach((a) => {
    if (!out[a.id]) out[a.id] = 'Monitoring mission pipeline';
  });
  return out;
}

function toFeedFromAudit(rows = []) {
  return rows.slice(0, 40).map((row) => ({
    t: row.timestamp ? new Date(row.timestamp).toLocaleTimeString('pt-BR', { hour12: false }) : nowTime(),
    who: row.agent || 'System',
    msg: row.message || row.event || 'Update',
  }));
}

function tradeToEvent(row) {
  const sideText = String(row.side || '').toUpperCase();
  const status = String(row.status || '').toUpperCase();
  const pnlProxy = status.includes('ERROR') ? -0.2 : 0.35;
  const buyLike = sideText.includes('BUY') || sideText.includes('LONG');
  const agentHint = buyLike ? 'iron_man' : 'spider_man';
  return {
    stationId: agentHint,
    side: status.includes('ERROR') ? 'loss' : 'win',
    pnl: Number((pnlProxy * (Math.random() * 1.6)).toFixed(2)),
    sym: row.symbol || 'BTCUSDT',
    size: Number(row.quantity || 0) || Math.floor(5 + Math.random() * 45),
    ts: Date.now(),
  };
}

function fallbackTasks() {
  const out = {};
  AGENTS.forEach((a) => {
    out[a.id] = `${a.role} · standby`;
  });
  return out;
}

function fallbackFeed() {
  return AGENTS.slice(0, 12).map((a, idx) => ({
    t: nowTime(),
    who: a.name,
    msg: `Heartbeat ${idx + 1} · ${a.layer}`,
  }));
}

async function safeJson(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function createOfficeDataProvider() {
  let agentTimer = null;
  let tradeTimer = null;

  return {
    async getAgentTasks() {
      try {
        const rows = await safeJson('/api/audit?limit=120');
        return toTaskMapFromAudit(rows);
      } catch {
        return fallbackTasks();
      }
    },

    async getAuditFeed(limit = 30) {
      try {
        const rows = await safeJson(`/api/audit?limit=${encodeURIComponent(limit)}`);
        return toFeedFromAudit(rows);
      } catch {
        return fallbackFeed().slice(0, limit);
      }
    },

    subscribeTradeEvents(callback) {
      let cancelled = false;
      async function poll() {
        if (cancelled) return;
        try {
          const rows = await safeJson('/api/trades?limit=4');
          if (Array.isArray(rows) && rows.length) callback(tradeToEvent(rows[0]));
        } catch {
          callback({
            stationId: 'iron_man',
            side: Math.random() > 0.3 ? 'win' : 'loss',
            pnl: Number(((Math.random() - 0.3) * 1.2).toFixed(2)),
            sym: 'BTCUSDT',
            size: Math.floor(5 + Math.random() * 40),
            ts: Date.now(),
          });
        }
        const next = 2500 + Math.floor(Math.random() * 3000);
        tradeTimer = window.setTimeout(poll, next);
      }
      tradeTimer = window.setTimeout(poll, 1200);
      return () => {
        cancelled = true;
        if (tradeTimer) window.clearTimeout(tradeTimer);
      };
    },

    subscribeAgentUpdates(callback) {
      let cancelled = false;
      const getTasks = this.getAgentTasks.bind(this);
      async function refresh() {
        if (cancelled) return;
        try {
          const tasks = await getTasks();
          for (const [agentId, task] of Object.entries(tasks)) callback({ agentId, task });
        } catch {
          // keep loop alive even if provider temporarily fails
        }
        agentTimer = window.setTimeout(refresh, 10000);
      }
      refresh();
      return () => {
        cancelled = true;
        if (agentTimer) window.clearTimeout(agentTimer);
      };
    },
  };
}
