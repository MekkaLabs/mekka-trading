// Live data layer — pluggable data source for agent tasks + audit feed +
// trade events. Mock implementation runs locally; swap any of the three
// async/subscription methods for real fetch/WebSocket calls to your backend.
//
// REPLACE THESE WHEN BACKEND IS READY:
//   fetchAgentTasks()          GET /api/agents/tasks      → { [agentId]: task }
//   fetchFeedEvents()          GET /api/audit/feed?n=20   → [{ t, who, msg }]
//   subscribeTradeEvents(cb)   WS  /api/trades/stream     → cb({ stationId, side, pnl, sym })
//
// Each method below documents the exact wire shape expected.

// ---------- TASKS ----------
async function fetchAgentTasks() {
  // Real impl:
  //   const r = await fetch('/api/agents/tasks');
  //   return r.json();
  return new Promise(res => setTimeout(() => res(MOCK_TASK_POOL[Math.floor(Math.random()*MOCK_TASK_POOL.length)]), 300));
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
  // Real impl:
  //   const r = await fetch('/api/audit/feed?n=20');
  //   return r.json();
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
  const stations = [
    "ironman", "spiderman", "portfolio", "nighttrader",
    "hawkeye", "thor", "aquaman", "blackpanther",
  ];
  const symbols = ["SPY", "QQQ", "NVDA", "BTC", "ETH", "TSLA", "META", "SOL", "AAPL", "GLD"];
  let cancelled = false;

  function tick() {
    if (cancelled) return;
    const stationId = stations[Math.floor(Math.random() * stations.length)];
    const side = Math.random() > 0.42 ? "win" : "loss";
    const sym = symbols[Math.floor(Math.random() * symbols.length)];
    const size = (5 + Math.random() * 95) | 0;
    const pnl = side === "win"
      ? +(Math.random() * 1.4 + 0.05).toFixed(2)
      : -(Math.random() * 0.9 + 0.04).toFixed(2);
    cb({ stationId, side, pnl, sym, size, ts: Date.now() });
    setTimeout(tick, 2500 + Math.random() * 4500);
  }
  setTimeout(tick, 1500);
  return () => { cancelled = true; };
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
