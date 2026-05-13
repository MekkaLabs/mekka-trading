// Live data layer — pluggable data source for agent tasks + audit feed +
// trade events. Tries the Mekka Trading backend first; falls back to the
// embedded mocks when the endpoints are unreachable so the cena renders
// even when this HTML is opened standalone.
//
//   fetchAgentTasks()          GET /api/agents/tasks       → { [agentId]: task }
//   fetchFeedEvents()          GET /api/audit/feed?n=20    → [{ t, who, msg }]
//   subscribeTradeEvents(cb)   WS  /ws (broadcast snapshot) → derived events
//
// Each method below documents the exact wire shape expected.

// ---------- TASKS ----------
async function fetchAgentTasks() {
  try {
    const r = await fetch('/api/agents/tasks', { cache: 'no-store' });
    if (r.ok) {
      const json = await r.json();
      // Server returns { items: { agentId: task, ... } }; allow either shape.
      if (json && typeof json === 'object') {
        return json.items || json;
      }
    }
  } catch (_) { /* fall through to mock */ }
  return MOCK_TASK_POOL[Math.floor(Math.random() * MOCK_TASK_POOL.length)];
}

const MOCK_TASK_POOL = [
  {
    superman: "Parsing FOMC minutes (just dropped)",
    doctorstrange: "Tagging unusual options flow on QQQ",
    blackpanther: "Watching ASK depth on 4 symbols",
    thor: "Pre-positioning around NVDA earnings",
    aquaman: "Charting liquidity void on ETH/USDT",
    spiderman: "3 spread opps detected in last 30s",
    vision: "Scoring 12 strategy proposals",
    professorx: "Re-evaluating cross-asset correlation",
    ironman: "Executing batch — 7 limit orders pending",
    batman: "Monitoring drawdown — within band",
    portfolio: "Rebalancing book — 4 open hedges",
    nickfury: "Reviewing daily PnL with PortfolioManager",
    dailypnl: "Writing close-of-day report v07",
    nighttrader: "Asia session — JPY pairs, low size",
    hawkeye: "Sniping resting orders on level 2",
    hulk: "Stress-testing risk caps at 3× notional",
  },
  {
    superman: "Macro: ECB speech digest — dovish lean",
    doctorstrange: "Pattern: bull flag forming on SPY 4h",
    blackpanther: "Microstructure: spoofing detected on BTC",
    thor: "Earnings: META beat — repositioning",
    aquaman: "Liquidity scan complete — 3 deep pools",
    spiderman: "Cross-venue arb closed +0.12%",
    vision: "Strategy v08 ranked — sharpe 2.4",
    professorx: "Regime shift suspected — flagging L4",
    ironman: "Routing 14 child orders across 3 venues",
    batman: "Pulled position size on TSLA — vol spike",
    portfolio: "Scaling NVDA long to 4% portfolio",
    nickfury: "Approved L2 batch — 60% sizing",
    dailypnl: "PnL note v08 — +1.42% session",
    nighttrader: "London handoff — 2 carries open",
    hawkeye: "Top of book holds — adding clip",
    hulk: "Margin headroom: 38% — comfortable",
  },
];

// ---------- AUDIT FEED ----------
async function fetchFeedEvents() {
  try {
    const r = await fetch('/api/audit/feed?n=20', { cache: 'no-store' });
    if (r.ok) {
      const json = await r.json();
      const items = Array.isArray(json) ? json : (json.items || []);
      if (items.length) return items;
    }
  } catch (_) { /* fall through */ }
  return MOCK_FEED.slice(0, 20);
}

const MOCK_FEED = [
  { t: "12:04:21", who: "Superman",    msg: "FOMC minutes parsed → 3 signals routed" },
  { t: "12:04:18", who: "DocStrange",  msg: "Unusual flow on QQQ — flag raised" },
  { t: "12:04:14", who: "Vision",      msg: "Strategy v07 ranked #1 (sharpe 2.31)" },
  { t: "12:04:09", who: "IronMan",     msg: "Order batch 7/9 filled" },
  { t: "12:04:02", who: "Batman",      msg: "Drawdown 0.4% — within band" },
  { t: "12:03:58", who: "NickFury",    msg: "Approved L2 strategy, 60% sizing" },
  { t: "12:03:51", who: "DailyPnLW.",  msg: "Drafted PnL note v04" },
  { t: "12:03:44", who: "NightTrader", msg: "JPY carry opened, +0.18%" },
  { t: "12:03:39", who: "Hawkeye",     msg: "Hidden bid sniped — 1200 SOL" },
  { t: "12:03:30", who: "Hulk",        msg: "Risk cap raised — 1.5× notional" },
];

// ---------- TRADE STREAM (subscriptions) ----------
// Real impl with WebSocket:
//   const ws = new WebSocket('wss://your-backend/api/trades/stream');
//   ws.onmessage = e => cb(JSON.parse(e.data));
//   return () => ws.close();
//
// Mock: emits a synthetic trade every ~3-7 seconds with a random
// station/side/pnl. The app uses these to flash the desk monitor and
// push to the audit feed.
function subscribeTradeEvents(cb) {
  // Real bridge to the Mekka /ws broadcast. We watch `payload.trades`
  // (the most recent N executions persisted by Iron Man) and emit a
  // flash whenever a new trade row appears that we haven't seen yet.
  // Falls back to a synthetic emitter if /ws never produces data
  // (HTML opened over file://, server down, or empty book).
  const stations = [
    "ironman", "spiderman", "portfolio", "nighttrader",
    "hawkeye", "thor", "aquaman", "blackpanther",
  ];
  const symbols = ["SPY", "QQQ", "NVDA", "BTC", "ETH", "TSLA", "META", "SOL", "AAPL", "GLD"];
  let cancelled = false;
  let ws = null;
  let mockTimer = null;
  let receivedAnyTrade = false;
  // Trade rows are unique by (timestamp, symbol, side, status, notional).
  // Keep a small set of recently-seen keys so we don't refire flashes
  // for rows that just stay in the broadcast window for several ticks.
  const seenKeys = new Set();
  const SEEN_LIMIT = 256;
  function rememberKey(k) {
    seenKeys.add(k);
    if (seenKeys.size > SEEN_LIMIT) {
      // Drop oldest by recreating from an array slice.
      const arr = Array.from(seenKeys).slice(-Math.floor(SEEN_LIMIT * 0.7));
      seenKeys.clear();
      arr.forEach((x) => seenKeys.add(x));
    }
  }

  function startMock() {
    if (cancelled || mockTimer) return;
    function tick() {
      if (cancelled) return;
      const stationId = stations[Math.floor(Math.random() * stations.length)];
      const side = Math.random() > 0.42 ? "win" : "loss";
      const sym = symbols[Math.floor(Math.random() * symbols.length)];
      const size = (5 + Math.random() * 95) | 0;
      const pnl = side === "win"
        ? +(Math.random() * 1.4 + 0.05).toFixed(2)
        : -(Math.random() * 0.9 + 0.04).toFixed(2);
      cb({ stationId, side, pnl, sym, size, ts: Date.now(), source: "mock" });
      mockTimer = setTimeout(tick, 2500 + Math.random() * 4500);
    }
    mockTimer = setTimeout(tick, 1500);
  }

  function classifyTrade(trade) {
    // Map Iron Man's status enum into win/loss for the flash colour. Errors
    // and rejections are losses; SKIPPED isn't a real trade so we drop it.
    const status = String(trade.status || "").toUpperCase();
    if (status === "SKIPPED" || status === "PENDING") return null;
    if (status === "ERROR" || status === "REJECTED" || status === "FAILED") return "loss";
    return "win";
  }

  function deriveFromPayload(payload) {
    const trades = Array.isArray(payload?.trades) ? payload.trades : [];
    for (const t of trades) {
      const side = classifyTrade(t);
      if (!side) continue;
      const key = [
        t.timestamp || "", t.symbol || "", t.side || "",
        t.status || "", t.notional_usd ?? 0,
      ].join("|");
      if (seenKeys.has(key)) continue;
      rememberKey(key);
      receivedAnyTrade = true;
      // Iron Man's `notional_usd` is the trade size in $. We surface it as
      // the size figure (rounded) and keep `pnl` as a sentinel — Office v2
      // shows the PnL flash badge ("+0.5%"); without realised PnL on the
      // wire we send a small win/loss tick that conveys the direction.
      const notional = Number(t.notional_usd || 0);
      const sym = t.symbol || "—";
      cb({
        stationId: "ironman",
        side,
        pnl: side === "win" ? 0.5 : -0.4,
        sym,
        size: Math.max(1, Math.round(notional)),
        is_paper: !!t.is_paper,
        ts: Date.parse(t.timestamp || "") || Date.now(),
        source: "ws",
      });
    }
  }

  function startWs() {
    try {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          deriveFromPayload(payload);
        } catch (_) { /* ignore */ }
      };
      ws.onerror = () => { /* close handler below kicks in */ };
      ws.onclose = () => {
        if (cancelled) return;
        // If we never received a real trade, fall back to the mock
        // emitter so the office never feels frozen during standalone
        // preview / dev mode.
        if (!receivedAnyTrade) startMock();
      };
    } catch (_) {
      startMock();
    }
  }

  startWs();
  // Safety net — if /ws hasn't produced a trade after 8s, start the
  // synthetic emitter so the cena keeps moving.
  setTimeout(() => {
    if (!cancelled && !receivedAnyTrade) startMock();
  }, 8000);

  return () => {
    cancelled = true;
    if (mockTimer) clearTimeout(mockTimer);
    if (ws && ws.readyState <= 1) try { ws.close(); } catch {}
  };
}

// ---------- AGENT STATUS PUSH (mock) ----------
// In production, emit "task changed" events from your orchestrator and
// push them through this channel so the side panel updates in real time.
function subscribeAgentTasks(cb) {
  let cancelled = false;
  function tick() {
    if (cancelled) return;
    const all = MOCK_TASK_POOL[Math.floor(Math.random() * MOCK_TASK_POOL.length)];
    const ids = Object.keys(all);
    const id = ids[Math.floor(Math.random() * ids.length)];
    cb({ agentId: id, task: all[id] });
    setTimeout(tick, 4000 + Math.random() * 5000);
  }
  setTimeout(tick, 2000);
  return () => { cancelled = true; };
}

Object.assign(window, {
  fetchAgentTasks, fetchFeedEvents, subscribeTradeEvents, subscribeAgentTasks,
});
