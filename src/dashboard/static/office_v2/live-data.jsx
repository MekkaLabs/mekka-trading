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
    superman:      "Parsing FOMC minutes (just dropped)",
    doctorstrange: "Tagging unusual options flow on QQQ",
    blackpanther:  "Watching ASK depth em 4 símbolos",
    thor:          "ATR% EXTREME em SOL — reduzindo sizing 0.6×",
    aquaman:       "Spread ETH/USDT dentro do limite — OK",
    spiderman:     "3 anomalias LOW detectadas em 30s",
    flash:         "Momentum UP detectado — BTC 15m confirmado",
    vision:        "Sinal LONG BTC confidence 0.82 gerado",
    professorx:    "Regime BULL confirmado — bias positivo",
    ironman:       "IOC entry BTC preenchida em $94.320",
    batman:        "Gate 3c: correlação limpa — APPROVED",
    wolverine:     "HOLD em 3 posições — SL dentro do range",
    cyclops:       "TP1 atingido SOL — 33% fechado automaticamente",
    deadpool:      "Win rate 68% / Sharpe 1.8 — READY",
    portfolio:     "Equity $25.430 — drawdown 0.8%",
    nickfury:      "Ciclo 4h completo — próximo em 03:47",
  },
  {
    superman:      "Macro: ECB dovish — fluxo entrando em cripto",
    doctorstrange: "Fear & Greed: 72 GREED — cautela moderada",
    blackpanther:  "Whale compra $4.2M BTC na Hyperliquid",
    thor:          "Volatilidade MEDIUM — sizing 1.0× normal",
    aquaman:       "Liquidez score 0.91 — profundidade excelente",
    spiderman:     "Volume spike 3.2× na média — MEDIUM anomaly",
    flash:         "SIDEWAYS confirmado — sem momentum claro",
    vision:        "HOLD emitido — regime incerto no curto prazo",
    professorx:    "Dados BTC + ETH divergentes — retry em 5min",
    ironman:       "SL/TP brackets posicionados — aguardando",
    batman:        "Gate 3i: funding rate alto — REJECTED SHORT",
    wolverine:     "TRAIL_STOP sugerido ETH — +1.8R acumulado",
    cyclops:       "Auto-TP ladder: 3 níveis configurados SOL",
    deadpool:      "Sharpe 30d: 2.1 — NOT_READY (poucos dados)",
    portfolio:     "4 posições abertas — exposure 12% equity",
    nickfury:      "Monitor cycle 5min — Cyclops+Wolverine OK",
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
    "ironman", "spiderman", "portfolio", "flash",
    "wolverine", "cyclops", "deadpool", "thor", "aquaman", "blackpanther",
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

// ---------- CYCLE EVENT STREAM (Story 173 — SSE) ----------
// Connects to GET /api/events/stream (Server-Sent Events, Story 172).
// cb receives parsed event objects: { event_type, symbol, cycle_id, ...kwargs }
// Returns an unsubscribe function — call it to close the EventSource.
//
// Supports an optional `symbol` filter forwarded as ?symbol=BTC to the server.
// Falls back to mock cycle events if the browser doesn't support EventSource
// or the server is unreachable after FALLBACK_DELAY_MS.
function subscribeCycleEvents(cb, { symbol = "", seed = 10 } = {}) {
  if (typeof EventSource === "undefined") {
    return _startCycleEventMock(cb);  // IE / restricted env
  }

  const FALLBACK_DELAY_MS = 8000;
  let cancelled = false;
  let es = null;
  let mockTimer = null;
  let receivedAny = false;

  function startMock() {
    if (cancelled || mockTimer) return;
    const MOCK_EVENTS = [
      { event_type: "CYCLE_START",   symbol: symbol || "BTCUSDT", cycle_id: "mock-001", equity_usd: 25000 },
      { event_type: "ANALYSIS_DONE", symbol: symbol || "BTCUSDT", cycle_id: "mock-001", price: 94320, volatility: 0.032 },
      { event_type: "SIGNAL_EMITTED",symbol: symbol || "BTCUSDT", cycle_id: "mock-001", action: "LONG", confidence: 0.82, entry_price: 94320 },
      { event_type: "RISK_VERDICT",  symbol: symbol || "BTCUSDT", cycle_id: "mock-001", verdict: "APPROVED", approved: true },
      { event_type: "EXECUTION_DONE",symbol: symbol || "BTCUSDT", cycle_id: "mock-001", status: "FILLED", is_paper: true },
      { event_type: "CYCLE_END",     symbol: symbol || "BTCUSDT", cycle_id: "mock-001", outcome: "EXECUTED" },
    ];
    let idx = 0;
    function tick() {
      if (cancelled) return;
      cb({ ...MOCK_EVENTS[idx % MOCK_EVENTS.length], ts: new Date().toISOString(), source: "mock" });
      idx++;
      mockTimer = setTimeout(tick, 3000 + Math.random() * 4000);
    }
    mockTimer = setTimeout(tick, 1200);
  }

  function startSSE() {
    try {
      const params = new URLSearchParams({ last: String(seed) });
      if (symbol) params.set("symbol", symbol.toUpperCase());
      es = new EventSource(`/api/events/stream?${params}`);

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          receivedAny = true;
          cb({ ...data, source: "sse" });
        } catch (_) { /* ignore malformed frame */ }
      };

      es.onerror = () => {
        if (cancelled) return;
        // SSE errors are transient (network blip, server restart).
        // EventSource auto-reconnects; we only fall back to mock if
        // we never received a real event.
        if (!receivedAny) startMock();
      };
    } catch (_) {
      startMock();
    }
  }

  startSSE();
  // Safety net: if no real events arrive within FALLBACK_DELAY_MS, kick mock
  setTimeout(() => {
    if (!cancelled && !receivedAny) startMock();
  }, FALLBACK_DELAY_MS);

  return () => {
    cancelled = true;
    if (es) try { es.close(); } catch (_) {}
    if (mockTimer) clearTimeout(mockTimer);
  };
}

// Internal helper — mock emitter when EventSource unavailable
function _startCycleEventMock(cb) {
  let cancelled = false;
  const types = ["CYCLE_START","ANALYSIS_DONE","SIGNAL_EMITTED","RISK_VERDICT","EXECUTION_DONE","CYCLE_END"];
  let i = 0;
  function tick() {
    if (cancelled) return;
    cb({ event_type: types[i % types.length], symbol: "BTCUSDT", cycle_id: "mock-fallback", source: "mock" });
    i++;
    setTimeout(tick, 4000);
  }
  setTimeout(tick, 500);
  return () => { cancelled = true; };
}

Object.assign(window, {
  fetchAgentTasks, fetchFeedEvents, subscribeTradeEvents, subscribeAgentTasks,
  subscribeCycleEvents,  // Story 173
});
