// Agent motion system. Each agent maintains a position and a state machine.
// Tick the world once per animation frame; this updates positions toward
// targets, schedules new errands, and reports walking-vs-sitting state.

const POIS = [
  { id: "coffee",      x: 56,  y: 198, label: "COFFEE",     icon: "☕", emoji: "coffee" },
  { id: "whiteboard",  x: 38,  y: 168, label: "WHITEBOARD", icon: "✎", emoji: "thinking" },
  { id: "cooler",      x: 542, y: 220, label: "COOLER",     icon: "💧", emoji: "thinking" },
  { id: "bigscreen",   x: 196, y: 154, label: "WALL TV",    icon: "📺", emoji: "thinking" },
  { id: "printer",     x: 384, y: 198, label: "PRINTER",    icon: "🖨", emoji: "thinking" },
];

// Compute the seat (sitting) position from a station id.
function seatPos(stationId) {
  const s = STATIONS.find(st => st.id === stationId);
  if (!s) return { x: 240, y: 150 };
  const p = agentPosFor(s);
  return { x: p.x, y: p.y };
}

// Build initial state for every agent (everyone seated at their home desk).
function makeInitialMotion() {
  const state = {};
  for (const a of AGENTS) {
    const home = seatPos(a.id);
    state[a.id] = {
      id: a.id,
      mode: "at-desk",      // 'at-desk' | 'walking' | 'visiting' | 'returning'
      pos: { ...home },
      target: null,
      poi: null,
      bubble: null,
      waitUntil: 0,
      home,
    };
  }
  return state;
}

// Manhattan-ish stepping: move toward target at fixed speed.
const WALK_SPEED = 0.7; // pixels per tick (tick ~80ms)

function stepToward(pos, target, speed = WALK_SPEED) {
  const dx = target.x - pos.x;
  const dy = target.y - pos.y;
  const dist = Math.hypot(dx, dy);
  if (dist <= speed) {
    return { pos: { x: target.x, y: target.y }, arrived: true, dir: dx >= 0 ? 1 : -1 };
  }
  const nx = pos.x + (dx / dist) * speed;
  const ny = pos.y + (dy / dist) * speed;
  return { pos: { x: nx, y: ny }, arrived: false, dir: dx >= 0 ? 1 : -1 };
}

// Pick a free POI (not already targeted by another agent in 'walking' or 'visiting').
function pickFreePoi(state) {
  const taken = new Set();
  for (const k in state) {
    const s = state[k];
    if ((s.mode === "walking" || s.mode === "visiting") && s.poi) taken.add(s.poi);
  }
  const free = POIS.filter(p => !taken.has(p.id));
  if (!free.length) return null;
  return free[Math.floor(Math.random() * free.length)];
}

// Pick an agent that's been idle long enough to send on an errand.
function pickIdleAgent(state, frame) {
  const idle = Object.values(state).filter(s =>
    s.mode === "at-desk" && frame >= s.waitUntil
  );
  if (!idle.length) return null;
  return idle[Math.floor(Math.random() * idle.length)];
}

// Advance world by one tick.
function tickMotion(state, frame, opts = {}) {
  // Schedule new errands. We try to keep ~2-3 agents away from desks.
  const walking = Object.values(state).filter(s => s.mode !== "at-desk").length;
  const maxAway = opts.maxAway ?? 3;
  if (walking < maxAway && frame % 18 === 0) {
    const agent = pickIdleAgent(state, frame);
    const poi = pickFreePoi(state);
    if (agent && poi) {
      // Walk to a path point near the POI (offset Y so they stand in front)
      agent.mode = "walking";
      agent.target = { x: poi.x, y: poi.y };
      agent.poi = poi.id;
      agent.bubble = poi.icon;
      agent.bubbleClearAt = frame + 14;
    }
  }

  // Per-agent step
  for (const k in state) {
    const s = state[k];
    if (s.bubble && frame >= s.bubbleClearAt) s.bubble = null;

    if (s.mode === "walking") {
      const r = stepToward(s.pos, s.target);
      s.pos = r.pos;
      s.dir = r.dir;
      if (r.arrived) {
        s.mode = "visiting";
        s.waitUntil = frame + 30 + Math.floor(Math.random() * 30); // hang out
      }
    } else if (s.mode === "visiting") {
      if (frame >= s.waitUntil) {
        s.mode = "returning";
        s.target = { ...s.home };
        s.poi = null;
      }
    } else if (s.mode === "returning") {
      const r = stepToward(s.pos, s.target);
      s.pos = r.pos;
      s.dir = r.dir;
      if (r.arrived) {
        s.mode = "at-desk";
        s.waitUntil = frame + 60 + Math.floor(Math.random() * 100);
      }
    }
  }
  return state;
}

Object.assign(window, { POIS, makeInitialMotion, tickMotion, seatPos });
