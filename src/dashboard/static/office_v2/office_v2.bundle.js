(function(){
"use strict";

// === agent-motion.jsx ===
// Agent motion system. Each agent maintains a position and a state machine.
// Tick the world once per animation frame; this updates positions toward
// targets, schedules new errands, and reports walking-vs-sitting state.
const POIS = [
    { id: "coffee", x: 222, y: 162, label: "COFFEE", icon: "☕", emoji: "coffee" },
    { id: "whiteboard", x: 38, y: 168, label: "WHITEBOARD", icon: "✎", emoji: "thinking" },
    { id: "cooler", x: 462, y: 168, label: "COOLER", icon: "💧", emoji: "thinking" },
    { id: "bigscreen", x: 200, y: 132, label: "WALL TV", icon: "📺", emoji: "thinking" },
    { id: "printer", x: 396, y: 162, label: "PRINTER", icon: "🖨", emoji: "thinking" },
];
// Compute the seat (sitting) position from a station id.
function seatPos(stationId) {
    const s = STATIONS.find(st => st.id === stationId);
    if (!s)
        return { x: 240, y: 150 };
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
            mode: "at-desk", // 'at-desk' | 'walking' | 'visiting' | 'returning'
            pos: Object.assign({}, home),
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
        if ((s.mode === "walking" || s.mode === "visiting") && s.poi)
            taken.add(s.poi);
    }
    const free = POIS.filter(p => !taken.has(p.id));
    if (!free.length)
        return null;
    return free[Math.floor(Math.random() * free.length)];
}
// Pick an agent that's been idle long enough to send on an errand.
function pickIdleAgent(state, frame) {
    const idle = Object.values(state).filter(s => s.mode === "at-desk" && frame >= s.waitUntil);
    if (!idle.length)
        return null;
    return idle[Math.floor(Math.random() * idle.length)];
}
// Advance world by one tick.
function tickMotion(state, frame, opts = {}) {
    var _a;
    // Schedule new errands. We try to keep ~2-3 agents away from desks.
    const walking = Object.values(state).filter(s => s.mode !== "at-desk").length;
    const maxAway = (_a = opts.maxAway) !== null && _a !== void 0 ? _a : 3;
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
        if (s.bubble && frame >= s.bubbleClearAt)
            s.bubble = null;
        if (s.mode === "walking") {
            const r = stepToward(s.pos, s.target);
            s.pos = r.pos;
            s.dir = r.dir;
            if (r.arrived) {
                s.mode = "visiting";
                s.waitUntil = frame + 30 + Math.floor(Math.random() * 30); // hang out
            }
        }
        else if (s.mode === "visiting") {
            if (frame >= s.waitUntil) {
                s.mode = "returning";
                s.target = Object.assign({}, s.home);
                s.poi = null;
            }
        }
        else if (s.mode === "returning") {
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


// === props.jsx ===
// Office decorations and props. Each function paints into the low-res canvas.
// Frame-driven animations: wall monitor charts, clock hands, coffee steam.
// ---------- BIG WALL MONITOR ----------
// Wide TV showing a live candlestick chart. Center of the back wall.
function drawWallMonitor(ctx, x, y, w, h, frame) {
    // bezel
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    // screen background — deep navy with grid
    ctx.fillStyle = "#0a1424";
    ctx.fillRect(x + 3, y + 3, w - 6, h - 6);
    ctx.fillStyle = "#152238";
    for (let gx = x + 3; gx < x + w - 3; gx += 8)
        ctx.fillRect(gx, y + 3, 1, h - 6);
    for (let gy = y + 3; gy < y + h - 3; gy += 6)
        ctx.fillRect(x + 3, gy, w - 6, 1);
    // axis line at bottom
    ctx.fillStyle = "#1c2c44";
    ctx.fillRect(x + 4, y + h - 6, w - 8, 1);
    // candles — 22 candles, scrolling
    const N = 22;
    const cw = Math.floor((w - 12) / N);
    for (let i = 0; i < N; i++) {
        const seed = (frame >> 2) + i;
        const o = ((seed * 17) % 11) - 5;
        const c = ((seed * 23) % 11) - 5;
        const high = Math.max(o, c) + ((seed * 7) % 4);
        const low = Math.min(o, c) - ((seed * 5) % 3);
        const mid = y + Math.floor(h / 2);
        const cx = x + 6 + i * cw;
        const up = c >= o;
        const col = up ? "#22c55e" : "#ef4444";
        // wick
        ctx.fillStyle = col;
        ctx.fillRect(cx + Math.floor(cw / 2), mid - high, 1, (high - low) || 1);
        // body
        const top = mid - Math.max(o, c);
        const bh = Math.max(1, Math.abs(c - o));
        ctx.fillRect(cx + 1, top, cw - 2, bh);
    }
    // ticker text bar at top
    ctx.fillStyle = "#0a1424";
    ctx.fillRect(x + 3, y + 3, w - 6, 7);
    ctx.fillStyle = "#fb923c";
    ctx.fillRect(x + 5, y + 5, 2, 2);
    ctx.fillStyle = "#cfd9ec";
    // pretend "MEKKA" letters as 1x3 bars
    for (let i = 0; i < 18; i++) {
        if (((frame + i) >> 1) % 7 < 5)
            ctx.fillRect(x + 10 + i * 3, y + 6, 1, 3);
    }
    // recording dot
    if ((frame >> 2) % 2 === 0) {
        ctx.fillStyle = "#ef4444";
        ctx.fillRect(x + w - 8, y + 5, 2, 2);
    }
    // outer frame highlight
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x, y, 1, h);
    ctx.fillStyle = "#000000";
    ctx.fillRect(x + w - 1, y, 1, h);
}
// ---------- WHITEBOARD ----------
function drawWhiteboard(ctx, x, y, w, h, frame) {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
    ctx.fillStyle = "#e8eef9";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    // doodle: arrow + boxes
    ctx.fillStyle = "#1c1c1c";
    // box 1
    ctx.fillRect(x + 5, y + 6, 12, 8);
    ctx.fillStyle = "#e8eef9";
    ctx.fillRect(x + 6, y + 7, 10, 6);
    ctx.fillStyle = "#1e40af";
    ctx.fillRect(x + 7, y + 9, 8, 2);
    // arrow →
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(x + 18, y + 9, 6, 1);
    ctx.fillRect(x + 22, y + 8, 1, 3);
    ctx.fillRect(x + 23, y + 9, 1, 1);
    // box 2
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 25, y + 6, 12, 8);
    ctx.fillStyle = "#e8eef9";
    ctx.fillRect(x + 26, y + 7, 10, 6);
    ctx.fillStyle = "#15803d";
    ctx.fillRect(x + 27, y + 9, 8, 2);
    // line chart
    ctx.fillStyle = "#fb923c";
    const xs = [4, 8, 12, 16, 20, 24, 28, 32, 36, 40];
    const ys_off = (frame >> 2) % 4;
    for (let i = 0; i < xs.length - 1; i++) {
        const yA = y + 26 + ((i + ys_off) % 5);
        const yB = y + 26 + ((i + 1 + ys_off) % 5);
        ctx.fillRect(x + xs[i], yA, xs[i + 1] - xs[i], 1);
        if (yB !== yA)
            ctx.fillRect(x + xs[i + 1], Math.min(yA, yB), 1, Math.abs(yB - yA) + 1);
    }
    // marker tray
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 1, y + h - 3, w - 2, 2);
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(x + 4, y + h - 2, 5, 1);
    ctx.fillStyle = "#1e40af";
    ctx.fillRect(x + 12, y + h - 2, 5, 1);
    ctx.fillStyle = "#15803d";
    ctx.fillRect(x + 20, y + h - 2, 5, 1);
}
// ---------- COFFEE STATION ----------
function drawCoffeeStation(ctx, x, y, frame) {
    // Counter (60w x 12h)
    ctx.fillStyle = "#3d2817";
    ctx.fillRect(x, y + 12, 60, 14);
    ctx.fillStyle = "#5a3826";
    ctx.fillRect(x, y + 12, 60, 1);
    ctx.fillStyle = "#251509";
    ctx.fillRect(x, y + 25, 60, 1);
    ctx.fillStyle = "#1a0d05";
    ctx.fillRect(x + 58, y + 12, 1, 14);
    // Backsplash
    ctx.fillStyle = "#2a3e5c";
    ctx.fillRect(x, y, 60, 12);
    ctx.fillStyle = "#1c2c44";
    ctx.fillRect(x, y, 60, 1);
    // tile pattern
    ctx.fillStyle = "#3a5680";
    for (let tx = x; tx < x + 60; tx += 6)
        for (let ty = y + 1; ty < y + 11; ty += 4)
            ctx.fillRect(tx + ((ty / 4) % 2) * 3, ty, 1, 1);
    // Coffee machine (16w x 20h)
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 4, y - 8, 18, 20);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 5, y - 7, 16, 18);
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 6, y - 6, 14, 4); // top vents
    // display (animated)
    ctx.fillStyle = "#22c55e";
    if ((frame >> 2) % 2 === 0)
        ctx.fillRect(x + 8, y - 1, 10, 2);
    // spout
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 11, y + 5, 4, 3);
    // dripping coffee
    if ((frame >> 1) % 8 < 3) {
        ctx.fillStyle = "#7c2d12";
        ctx.fillRect(x + 12, y + 8, 2, 2);
    }
    // cup beneath
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 11, y + 10, 4, 4);
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x + 12, y + 11, 2, 2);
    ctx.fillStyle = "#7c2d12";
    ctx.fillRect(x + 12, y + 11, 2, 1);
    // steam
    if ((frame >> 1) % 4 < 2) {
        ctx.fillStyle = "#cbd5e1";
        ctx.fillRect(x + 12, y - 10, 1, 1);
        ctx.fillRect(x + 13, y - 12, 1, 1);
        ctx.fillRect(x + 11, y - 13, 1, 1);
    }
    // Mugs lined up on counter
    for (let i = 0; i < 4; i++) {
        const mx = x + 28 + i * 7;
        ctx.fillStyle = "#0a0a0a";
        ctx.fillRect(mx, y + 8, 5, 4);
        ctx.fillStyle = ["#dc2626", "#fde047", "#22c55e", "#38bdf8"][i];
        ctx.fillRect(mx + 1, y + 9, 3, 2);
    }
    // Sugar/cream jars
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 52, y + 6, 4, 6);
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x + 53, y + 7, 2, 4);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 47, y + 6, 4, 6);
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x + 48, y + 7, 2, 4);
}
// ---------- WATER COOLER ----------
function drawWaterCooler(ctx, x, y, frame) {
    // bottle on top
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 2, y, 10, 14);
    ctx.fillStyle = "#7dd3fc";
    ctx.fillRect(x + 3, y + 1, 8, 12);
    // bubbles
    if ((frame >> 2) % 6 < 3) {
        ctx.fillStyle = "#e0f2fe";
        ctx.fillRect(x + 5, y + 3 + ((frame >> 1) % 6), 1, 1);
        ctx.fillRect(x + 8, y + 5 + ((frame >> 2) % 5), 1, 1);
    }
    // body
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x, y + 14, 14, 22);
    ctx.fillStyle = "#9ca3af";
    ctx.fillRect(x, y + 14, 14, 1);
    ctx.fillStyle = "#e8eef9";
    ctx.fillRect(x + 1, y + 15, 12, 20);
    // taps
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 3, y + 22, 2, 4);
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(x + 3, y + 21, 2, 1);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 9, y + 22, 2, 4);
    ctx.fillStyle = "#1e40af";
    ctx.fillRect(x + 9, y + 21, 2, 1);
    // drip tray
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 1, y + 30, 12, 1);
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x, y + 35, 14, 2);
}
// ---------- FILING CABINET ----------
function drawCabinet(ctx, x, y) {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 18, 38);
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 1, y + 1, 16, 36);
    ctx.fillStyle = "#5a5a5a";
    ctx.fillRect(x + 2, y + 2, 14, 1);
    // 3 drawers
    for (let i = 0; i < 3; i++) {
        const dy = y + 3 + i * 12;
        ctx.fillStyle = "#27272a";
        ctx.fillRect(x + 2, dy, 14, 10);
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 2, dy, 14, 1);
        ctx.fillStyle = "#5a5a5a";
        ctx.fillRect(x + 2, dy + 1, 14, 1);
        // handle
        ctx.fillStyle = "#9ca3af";
        ctx.fillRect(x + 7, dy + 5, 4, 2);
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 7, dy + 7, 4, 1);
        // label tag
        ctx.fillStyle = "#fde047";
        ctx.fillRect(x + 4, dy + 3, 5, 1);
    }
    // shadow under
    ctx.fillStyle = "#000000";
    ctx.fillRect(x - 1, y + 38, 20, 1);
}
// ---------- BOOKSHELF ----------
function drawBookshelf(ctx, x, y) {
    ctx.fillStyle = "#3d2817";
    ctx.fillRect(x, y, 30, 56);
    ctx.fillStyle = "#5a3826";
    ctx.fillRect(x + 1, y + 1, 28, 1);
    ctx.fillStyle = "#251509";
    ctx.fillRect(x + 1, y + 55, 28, 1);
    // 4 shelves
    for (let s = 0; s < 4; s++) {
        const sy = y + 4 + s * 13;
        ctx.fillStyle = "#251509";
        ctx.fillRect(x + 2, sy, 26, 1);
        // books on shelf
        const colors = ["#dc2626", "#1e40af", "#15803d", "#fde047", "#7f1d1d", "#a78bfa", "#fb923c", "#0e7490", "#27272a"];
        let bx = x + 3;
        for (let i = 0; i < 9; i++) {
            const bw = 2 + ((s * 3 + i * 5) % 3);
            const bh = 9 + ((s + i) % 3);
            const bc = colors[(s * 3 + i) % colors.length];
            if (bx + bw > x + 28)
                break;
            ctx.fillStyle = "#1c1c1c";
            ctx.fillRect(bx, sy + 13 - bh, bw, bh);
            ctx.fillStyle = bc;
            ctx.fillRect(bx, sy + 13 - bh + 1, bw, bh - 2);
            // light band
            ctx.fillStyle = "rgba(255,255,255,0.2)";
            bx += bw + 1;
        }
    }
    // top decoration: small clock or trophy
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x + 12, y - 4, 6, 4);
    ctx.fillStyle = "#a16207";
    ctx.fillRect(x + 13, y, 4, 1);
    ctx.fillStyle = "#a16207";
    ctx.fillRect(x + 14, y + 1, 2, 2);
}
// ---------- WALL CLOCK ----------
function drawWallClock(ctx, x, y, frame) {
    // outer ring
    ctx.fillStyle = "#0a0a0a";
    for (let dx = -7; dx <= 7; dx++)
        for (let dy = -7; dy <= 7; dy++) {
            if (dx * dx + dy * dy <= 49 && dx * dx + dy * dy >= 36)
                ctx.fillRect(x + 7 + dx, y + 7 + dy, 1, 1);
        }
    // face
    ctx.fillStyle = "#e8eef9";
    for (let dx = -6; dx <= 6; dx++)
        for (let dy = -6; dy <= 6; dy++) {
            if (dx * dx + dy * dy <= 36)
                ctx.fillRect(x + 7 + dx, y + 7 + dy, 1, 1);
        }
    // hour markers
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 7, y + 1, 1, 2);
    ctx.fillRect(x + 7, y + 12, 1, 2);
    ctx.fillRect(x + 1, y + 7, 2, 1);
    ctx.fillRect(x + 12, y + 7, 2, 1);
    // hour hand (slow)
    const hAng = ((frame / 600) % 1) * Math.PI * 2 - Math.PI / 2;
    for (let r = 0; r < 3; r++) {
        const px = Math.round(x + 7 + Math.cos(hAng) * r);
        const py = Math.round(y + 7 + Math.sin(hAng) * r);
        ctx.fillRect(px, py, 1, 1);
    }
    // minute hand (fast)
    ctx.fillStyle = "#dc2626";
    const mAng = ((frame / 100) % 1) * Math.PI * 2 - Math.PI / 2;
    for (let r = 0; r < 5; r++) {
        const px = Math.round(x + 7 + Math.cos(mAng) * r);
        const py = Math.round(y + 7 + Math.sin(mAng) * r);
        ctx.fillRect(px, py, 1, 1);
    }
    // center dot
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 6, y + 6, 2, 2);
}
// ---------- POSTER (framed picture) ----------
function drawPoster(ctx, x, y, w, h, opts = {}) {
    ctx.fillStyle = "#3d2817";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
    ctx.fillStyle = opts.bg || "#1e3a8a";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    // inner art: stylized M for Mekka
    if (opts.style === "M") {
        ctx.fillStyle = "#fde047";
        ctx.fillRect(x + 3, y + 4, 1, h - 8);
        ctx.fillRect(x + w - 4, y + 4, 1, h - 8);
        ctx.fillRect(x + 4, y + 5, 1, 2);
        ctx.fillRect(x + w - 5, y + 5, 1, 2);
        ctx.fillRect(x + 5, y + 7, 1, 2);
        ctx.fillRect(x + w - 6, y + 7, 1, 2);
        ctx.fillRect(x + 6, y + 9, w - 12, 1);
    }
    else if (opts.style === "chart") {
        // up-and-to-right line
        ctx.fillStyle = "#22c55e";
        for (let i = 0; i < w - 6; i++) {
            const py = y + h - 4 - Math.floor(i * (h - 8) / (w - 6));
            ctx.fillRect(x + 3 + i, py, 1, 1);
        }
    }
    else if (opts.style === "agent") {
        // tiny agent silhouette
        ctx.fillStyle = "#fde047";
        ctx.fillRect(x + w / 2 - 2, y + 3, 4, 4); // head
        ctx.fillRect(x + w / 2 - 3, y + 7, 6, h - 10); // body
    }
}
// ---------- TRASH BIN ----------
function drawTrash(ctx, x, y) {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 10, 12);
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 1, y + 1, 8, 10);
    ctx.fillStyle = "#5a5a5a";
    ctx.fillRect(x + 1, y + 1, 8, 1);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 2, y + 3, 6, 1);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 2, y + 6, 6, 1);
    // crumpled paper sticking out
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x + 3, y, 4, 2);
}
// ---------- FLOOR LAMP ----------
function drawFloorLamp(ctx, x, y, frame) {
    // pole
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 5, y + 12, 2, 28);
    // base
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 2, y + 38, 8, 3);
    ctx.fillStyle = "#3a3a3a";
    ctx.fillRect(x + 3, y + 39, 6, 1);
    // shade
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(x + 1, y + 4, 10, 2);
    ctx.fillRect(x, y + 6, 12, 6);
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x + 1, y + 7, 10, 4);
    // glow
    if ((frame >> 4) % 3 !== 0) {
        ctx.fillStyle = "rgba(253,224,71,0.15)";
        ctx.fillRect(x - 4, y + 2, 20, 16);
    }
}
// ---------- PRINTER ----------
function drawPrinter(ctx, x, y, frame) {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 22, 14);
    ctx.fillStyle = "#cfd9ec";
    ctx.fillRect(x + 1, y + 1, 20, 12);
    ctx.fillStyle = "#9ca3af";
    ctx.fillRect(x + 1, y + 5, 20, 1);
    // paper tray
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 2, y + 6, 18, 1);
    // paper coming out
    if ((frame >> 3) % 6 < 4) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(x + 4, y - 2, 14, 3);
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 5, y - 1, 12, 1);
    }
    // status light
    ctx.fillStyle = (frame >> 2) % 2 ? "#22c55e" : "#0a4d24";
    ctx.fillRect(x + 18, y + 2, 2, 2);
}
// ---------- POI MARKER (subtle floor glow under destinations) ----------
function drawPoiMarker(ctx, x, y, color, frame) {
    const pulse = ((frame >> 1) % 16) / 16;
    ctx.globalAlpha = 0.3 - pulse * 0.25;
    ctx.fillStyle = color;
    for (let r = 0; r < 6 + pulse * 8; r++) {
        ctx.fillRect(x - r, y, r * 2, 1);
    }
    ctx.globalAlpha = 1;
}
Object.assign(window, {
    drawWallMonitor, drawWhiteboard, drawCoffeeStation, drawWaterCooler,
    drawCabinet, drawBookshelf, drawWallClock, drawPoster, drawTrash,
    drawFloorLamp, drawPrinter, drawPoiMarker,
});


// === sprites.jsx ===
// Pixel-art sprite engine for Mekka Trading Pixel Office.
// Each sprite is a string array; chars map to palette keys.
// '.' = transparent. Sprites are drawn into an offscreen ImageData,
// then blitted into the main canvas at integer pixel coords.
const HEX = (h) => {
    const r = parseInt(h.slice(1, 3), 16), g = parseInt(h.slice(3, 5), 16), b = parseInt(h.slice(5, 7), 16);
    return [r, g, b, 255];
};
// ---------- BASE CHARACTER TEMPLATE (16w x 22h) ----------
// k=outline, h=hair, H=hair shade, s=skin, S=skin shade, e=eye, m=mouth
// c=shirt, C=shirt shade, p=pants, P=pants shade, a=accent, A=accent2, b=boots
const CHAR_BASE = [
    "................",
    ".....kkkkkk.....",
    "....khhhhhhk....",
    "...khhHHHHhhk...",
    "...khsssssshk...",
    "...kssSSSSssk...",
    "...kseksskeak...",
    "...kssSSSSssk...",
    "...kssmmmmssk...",
    "....ksssssk.....",
    "....csssssc.....",
    "...cccCCCccc....",
    "..ccCCCCCCCcc...",
    ".cCCCCaaaaCCCc..",
    ".cCCCaaaaaaCCc..",
    ".cCCCCaAAaCCCc..",
    ".cCCCCCCCCCCCc..",
    "..cCCCCCCCCCc...",
    "..cppppppppppc..",
    "..cppPPPPPPppc..",
    "...pp......pp...",
    "...kk......kk...",
];
// Cape overlay (behind body) — drawn before character with offset 0,0
const CAPE_OVERLAY = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "..AAAAAAAAAAAA..",
    ".AAAAaaaaaaAAA..",
    ".AaaaaaaaaaaaA..",
    ".AaaaaaaaaaaaA..",
    "................",
    "................",
    "................",
    ".AaaaaaaaaaaaA..",
    ".AaaaaaaaaaaaA..",
    "..AaaaaaaaaaA...",
    "...AaaaaaaaA....",
    "....AaaaaaA.....",
    ".....AAAAA......",
];
// Helmet overlay — covers head with metallic dome (for IronMan / Vision)
const HELMET_OVERLAY = [
    "................",
    ".....AAAAAA.....",
    "....AaaaaaaA....",
    "...AaAAaaAAaA...",
    "...AaaaaaaaaA...",
    "...AaeeAAeeaA...",
    "...AaaaaAAaaA...",
    "...AaaaAAaaaA...",
    "....AaaaaaaA....",
    ".....AAAAAA.....",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
];
// Mask overlay — covers top half of face only (Batman / SpiderMan style)
const MASK_OVERLAY = [
    "................",
    ".....AAAAAA.....",
    "....AAAAAAAA....",
    "...AAAAAAAAAA...",
    "...AAAAAAAAAA...",
    "...AAeeAAeeAA...",
    "...AAAAAAAAAA...",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
];
// Eye-patch overlay — single small black patch on right eye + strap
const EYEPATCH_OVERLAY = [
    "................",
    "................",
    "................",
    "....AAAAAAAA....",
    "...AAAAAAAAAA...",
    "...AAAAAAAAAA...",
    "...AAAAAAaaAA...",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
];
// Glasses overlay
const GLASSES_OVERLAY = [
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "...AaaAAAAaaA...",
    "...AAAAAAAAAA...",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
];
// Pad overlay so it's exactly 22 rows
function pad22(arr) { const w = arr[0].length; while (arr.length < 22)
    arr.push(".".repeat(w)); return arr; }
[CHAR_BASE, CAPE_OVERLAY, HELMET_OVERLAY, MASK_OVERLAY, EYEPATCH_OVERLAY, GLASSES_OVERLAY].forEach(pad22);
// ---------- PROP SPRITES ----------
// Desk + chair + monitor unit (32w x 28h). The character sprite stands
// behind the desk so legs are hidden.
const DESK_BACK = [
    "................................",
    "................................",
    "...kkkkkkkkkk...................",
    "..kggggggggggk..................",
    "..kgsssssssgk...................", // screen
    "..kgsbbbbbsgk...................",
    "..kgssssssggk...................",
    "..kggggggggggk..................",
    "..kkkkkkkkkkk...................",
    "....kkk..kkk....................", // monitor stand
    "...wwwwwwwwwww..................", // desk top
    "..wWWWWWWWWWWWw.................",
    "..wWWWWWWWWWWWw.................",
    "..wkkkkkkkkkkkw.................",
    "..wk.........kw.................",
    "..wk.........kw.................",
    "..wk.........kw.................",
    "..wk.........kw.................",
    "..wkkkkkkkkkkkw.................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
];
// Desk facing camera (character sits behind, we see back of monitor)
const DESK_FRONT = [
    "................................",
    "................................",
    "....kkkkkkkkkkkk................",
    "...kdddddddddddk................", // back of monitor
    "...kdDDDDDDDDDdk................",
    "...kdDDDDDDDDDdk................",
    "...kdDDDDDDDDDdk................",
    "...kdddddddddddk................",
    "....kkkkkkkkkkkk................",
    "......kkk..kkk..................", // stand
    "...wwwwwwwwwwwww................", // desk top
    "..wWWWWWWWWWWWWWw...............",
    "..wWWWWWWWWWWWWWw...............",
    "..wkkkkkkkkkkkkkw...............",
    "..wk...........kw...............",
    "..wk...........kw...............",
    "..wk...........kw...............",
    "..wkkkkkkkkkkkkkw...............",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
];
// Plant in pot (12w x 16h)
const PLANT = [
    "............",
    "...gggg.....",
    "..ggggggg...",
    ".gggGGGggg..",
    "ggGgggGgggg.",
    "gggGGGgggg..",
    ".ggggGgg....",
    "..gggg......",
    "...gg.......",
    "...kk.......",
    "..ttttt.....",
    "..tTTTTt....",
    "..tTTTTt....",
    "..tTTTTt....",
    "..ttttttt...",
    "............",
];
// Coffee mug (8w x 10h)
const MUG = [
    "........",
    ".kkkkkk.",
    ".kCCCCk.",
    ".kCccCk.",
    ".kCccCkk",
    ".kCccCkk",
    ".kCccCk.",
    ".kCCCCk.",
    ".kkkkkk.",
    "........",
];
// Search-web monitor popup (24x20)
const POPUP = [
    "kkkkkkkkkkkkkkkkkkkkkkkk",
    "k1111111111111111111111k",
    "k1kkkkkkkkkkkkkkkkkkkk1k",
    "k1kbbbbbbbbbbbbbbbbbbk1k",
    "k1kkkkkkkkkkkkkkkkkkkk1k",
    "k1kkkkkkkkkkkkkkkkkkkk1k",
    "k1k..................k1k",
    "k1k..bbbb...bb..bbbb.k1k",
    "k1k.b....b.bbb.b....bk1k",
    "k1k.b....b..bb.b....bk1k",
    "k1k..bbbb...bb..bbbb.k1k",
    "k1k..................k1k",
    "k1k.bb.bb.bb.bb.bb.bbk1k",
    "k1k..................k1k",
    "k1k.bb.bb.bb.bb.bb.bbk1k",
    "k1k..................k1k",
    "k1k..................k1k",
    "k1kkkkkkkkkkkkkkkkkkkk1k",
    "k1111111111111111111111k",
    "kkkkkkkkkkkkkkkkkkkkkkkk",
];
// Server rack (16w x 28h) — for "memory session" callout
const SERVER = [
    "..kkkkkkkkkkkk..",
    "..kgggggggggggk.",
    "..kgkkkkkkkkkgk.",
    "..kgkrrrrrrrkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkrrrrrrrkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkrrrrrrrkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkggggggggkk.",
    "..kgkg......gkk.",
    "..kgkg.bbbb.gkk.",
    "..kgkg.bbbb.gkk.",
    "..kgkg......gkk.",
    "..kgkggggggggkk.",
    "..kgkkkkkkkkkkk.",
    "..kgkrrrrrrrkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkkkkkkkkkgk.",
    "..kgkrrrrrrrkgk.",
    "..kgkkkkkkkkkgk.",
    "..kggggggggggk..",
    "..kkkkkkkkkkkk..",
    "................",
    "................",
];
// Window frame (40w x 28h) decoration on back wall
const WINDOW = [
    "wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww",
    "wkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkw",
    "wkbbbbbbbbbbbbbbbbbbbkbbbbbbbbbbbbbbbbkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBccccccBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBccccccccBBBBBBBBBkBBBBBBBBccccBBBBkw",
    "wkbBccccccccBBBBBBBBBkBBBBBBccccccBBBBkw",
    "wkbBBccccccBBBBBBBBBBkBBBBBccccccccBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBccccccBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBccccBBBBBkw",
    "wkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkbBBBBBBBBBBBBBBBBBBkBBBBBBBBBBBBBBBBkw",
    "wkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkw",
    "wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
    "................................................................",
];
// ---------- DRAWING HELPERS ----------
// Render a sprite into ctx at (x,y) using the given palette map.
// `palette` is an object: { 'k': '#000000', 'h': '#aaaaaa', ... }
// Missing keys are skipped (transparent).
function drawSprite(ctx, sprite, x, y, palette, opts = {}) {
    const flip = opts.flip || false;
    for (let row = 0; row < sprite.length; row++) {
        const line = sprite[row];
        for (let col = 0; col < line.length; col++) {
            const ch = line[col];
            if (ch === '.' || ch === ' ')
                continue;
            const color = palette[ch];
            if (!color)
                continue;
            ctx.fillStyle = color;
            const px = flip ? x + (line.length - 1 - col) : x + col;
            ctx.fillRect(px, y + row, 1, 1);
        }
    }
}
// ---------- AGENT ROSTER ----------
// Each agent has a base palette and optional overlays (cape, helmet, mask, etc.)
// Position is normalized; the scene composer places them relative to desks.
const AGENTS = [
    {
        id: "nickfury",
        name: "NickFury",
        role: "Command & Control",
        layer: "L4",
        color: "#22c55e",
        summary: "Director. Routes intel, signs off on every live trade.",
        task: "Reviewing daily PnL with PortfolioManager",
        palette: { k: "#0a0a0a", h: "#1a1a1a", H: "#000000", s: "#a0826d", S: "#7a5e4d",
            e: "#000000", m: "#5a3a2a", c: "#1c1c1c", C: "#0d0d0d",
            a: "#3b3b3b", A: "#1c1c1c", p: "#0a0a0a", P: "#000000" },
        overlay: { sprite: "EYEPATCH", palette: { A: "#000000", a: "#3a3a3a" } },
    },
    {
        id: "portfolio",
        name: "PortfolioManager",
        role: "Capital Allocation",
        layer: "L4",
        color: "#22c55e",
        summary: "Sizes positions. Owns the equity curve.",
        task: "Rebalancing book — 4 open hedges",
        palette: { k: "#1a1a1a", h: "#3d2817", H: "#251509", s: "#e8b888", S: "#b88860",
            e: "#000000", m: "#7a3a2a", c: "#1e3a8a", C: "#0f1f5c",
            a: "#dc2626", A: "#7f1d1d", p: "#1c1c2c", P: "#0c0c1c" },
    },
    {
        id: "dailypnl",
        name: "DailyPnLWriter",
        role: "Reporting",
        layer: "L4",
        color: "#22c55e",
        summary: "Drafts the daily PnL note and incident summaries.",
        task: "Writing close-of-day report v07",
        palette: { k: "#1a1a1a", h: "#c0a060", H: "#806838", s: "#f0c8a0", S: "#c09870",
            e: "#000000", m: "#7a3a2a", c: "#7c2d12", C: "#451a09",
            a: "#facc15", A: "#a16207", p: "#1c1c2c", P: "#0c0c1c" },
    },
    {
        id: "vision",
        name: "Vision",
        role: "Strategy Synthesis",
        layer: "L2",
        color: "#a78bfa",
        summary: "Combines L1 signals into ranked strategy candidates.",
        task: "Scoring 12 strategy proposals",
        palette: { k: "#1a0a1a", h: "#7c2d12", H: "#451a09", s: "#fde68a", S: "#ca8a04",
            e: "#000000", m: "#9a3a2a", c: "#15803d", C: "#0a4d24",
            a: "#facc15", A: "#a16207", p: "#7c2d12", P: "#451a09" },
        overlay: { sprite: "HELMET", palette: { A: "#fde047", a: "#fbbf24", e: "#1a0a1a" } },
    },
    {
        id: "professorx",
        name: "ProfessorX",
        role: "Strategy Reasoning",
        layer: "L2",
        color: "#a78bfa",
        summary: "Long-horizon planner. Owns the macro thesis.",
        task: "Re-evaluating cross-asset correlation regime",
        palette: { k: "#1a1a1a", h: "#fce7c8", H: "#fce7c8", s: "#f5d4b3", S: "#c5a483",
            e: "#000000", m: "#7a3a2a", c: "#3f3f46", C: "#27272a",
            a: "#71717a", A: "#3f3f46", p: "#1c1c2c", P: "#0c0c1c" },
        overlay: { sprite: "GLASSES", palette: { A: "#1a1a1a", a: "#1a1a1a" } },
    },
    {
        id: "ironman",
        name: "IronMan",
        role: "Order Execution",
        layer: "L3",
        color: "#fb923c",
        summary: "Routes orders. Smart-splits across venues.",
        task: "Executing batch — 7 limit orders pending",
        palette: { k: "#1a0a0a", h: "#1a0a0a", H: "#1a0a0a", s: "#dc2626", S: "#7f1d1d",
            e: "#fde047", m: "#1a0a0a", c: "#dc2626", C: "#7f1d1d",
            a: "#facc15", A: "#a16207", p: "#dc2626", P: "#7f1d1d" },
        overlay: { sprite: "HELMET", palette: { A: "#dc2626", a: "#facc15", e: "#fde047" } },
    },
    {
        id: "batman",
        name: "Batman",
        role: "Risk Watch",
        layer: "L3",
        color: "#fb923c",
        summary: "Patrols thresholds. Pulls the kill switch.",
        task: "Monitoring drawdown — within band",
        palette: { k: "#0a0a0a", h: "#0a0a0a", H: "#0a0a0a", s: "#d4a884", S: "#a47854",
            e: "#000000", m: "#5a2a1a", c: "#27272a", C: "#0a0a0a",
            a: "#facc15", A: "#a16207", p: "#0a0a0a", P: "#000000" },
        overlay: { sprite: "MASK", palette: { A: "#0a0a0a", a: "#0a0a0a", e: "#ffffff" } },
    },
    {
        id: "superman",
        name: "Superman",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "Top-down macro feed reader.",
        task: "Parsing FOMC minutes (just dropped)",
        palette: { k: "#0a0a1a", h: "#1e3a8a", H: "#0f1f5c", s: "#fde68a", S: "#ca8a04",
            e: "#1e40af", m: "#7a3a2a", c: "#1e40af", C: "#0f1f5c",
            a: "#dc2626", A: "#7f1d1d", p: "#1e40af", P: "#0f1f5c" },
        overlay: { sprite: "CAPE", palette: { A: "#7f1d1d", a: "#dc2626" } },
    },
    {
        id: "doctorstrange",
        name: "DoctorStrange",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "Pattern + regime detection across timeframes.",
        task: "Tagging unusual options flow",
        palette: { k: "#1a0a0a", h: "#1a1a1a", H: "#0a0a0a", s: "#e8b888", S: "#b88860",
            e: "#000000", m: "#7a3a2a", c: "#1a1a1a", C: "#0a0a0a",
            a: "#7f1d1d", A: "#451209", p: "#1a1a1a", P: "#0a0a0a" },
        overlay: { sprite: "CAPE", palette: { A: "#991b1b", a: "#dc2626" } },
    },
    {
        id: "blackpanther",
        name: "BlackPanther",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "Microstructure scout — order book tells.",
        task: "Watching ASK depth on 4 symbols",
        palette: { k: "#0a0a0a", h: "#0a0a0a", H: "#0a0a0a", s: "#3a2a1a", S: "#1a0a00",
            e: "#a78bfa", m: "#0a0a0a", c: "#1a1a1a", C: "#0a0a0a",
            a: "#a78bfa", A: "#5b21b6", p: "#0a0a0a", P: "#000000" },
        overlay: { sprite: "MASK", palette: { A: "#0a0a0a", a: "#0a0a0a", e: "#a78bfa" } },
    },
    {
        id: "thor",
        name: "Thor",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "High-impact event watcher — earnings, vols, shocks.",
        task: "Pre-positioning around NVDA earnings",
        palette: { k: "#1a0a0a", h: "#fde68a", H: "#ca8a04", s: "#f5c8a0", S: "#c59870",
            e: "#1e40af", m: "#7a3a2a", c: "#3f3f46", C: "#27272a",
            a: "#7f1d1d", A: "#451209", p: "#27272a", P: "#0a0a0a" },
        overlay: { sprite: "CAPE", palette: { A: "#7f1d1d", a: "#dc2626" } },
    },
    {
        id: "aquaman",
        name: "Aquaman",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "Liquidity & depth reader.",
        task: "Charting liquidity void on ETH/USDT",
        palette: { k: "#0a1a1a", h: "#fde68a", H: "#ca8a04", s: "#f5c8a0", S: "#c59870",
            e: "#0e7490", m: "#7a3a2a", c: "#15803d", C: "#0a4d24",
            a: "#facc15", A: "#a16207", p: "#0e7490", P: "#0a4054" },
    },
    {
        id: "spiderman",
        name: "SpiderMan",
        role: "Market Analysis",
        layer: "L1",
        color: "#38bdf8",
        summary: "Cross-venue arb scanner.",
        task: "3 spread opps detected in last 30s",
        palette: { k: "#1a0a0a", h: "#0f1f5c", H: "#0a0a3a", s: "#0f1f5c", S: "#0a0a3a",
            e: "#ffffff", m: "#0a0a0a", c: "#dc2626", C: "#7f1d1d",
            a: "#0f1f5c", A: "#0a0a3a", p: "#0f1f5c", P: "#0a0a3a" },
        overlay: { sprite: "MASK", palette: { A: "#dc2626", a: "#dc2626", e: "#ffffff" } },
    },
    {
        id: "nighttrader",
        name: "NightTrader",
        role: "Asia Session",
        layer: "L3",
        color: "#fb923c",
        summary: "Owns the overnight book — Asia open through London handoff.",
        task: "JPY carry, 2 positions open",
        palette: { k: "#0a0a14", h: "#1c0a3e", H: "#0a0020", s: "#a78bfa", S: "#5b21b6",
            e: "#fde047", m: "#1a0a0a", c: "#0a0a14", C: "#000000",
            a: "#7c3aed", A: "#3b0764", p: "#0a0a14", P: "#000000" },
        overlay: { sprite: "MASK", palette: { A: "#0a0a14", a: "#0a0a14", e: "#fde047" } },
    },
    {
        id: "hawkeye",
        name: "Hawkeye",
        role: "Microstructure",
        layer: "L1",
        color: "#38bdf8",
        summary: "Picks resting orders. Surgical level-2 reader.",
        task: "Sniping hidden bids on SOL/USDT",
        palette: { k: "#1a1a0a", h: "#7c2d12", H: "#451a09", s: "#e8b888", S: "#b88860",
            e: "#0e7490", m: "#7a3a2a", c: "#5b21b6", C: "#3b0764",
            a: "#fde047", A: "#a16207", p: "#27272a", P: "#0a0a0a" },
    },
    {
        id: "hulk",
        name: "Hulk",
        role: "Risk Stress Test",
        layer: "L3",
        color: "#fb923c",
        summary: "Replays scenarios at 3-10× notional. Breaks things on purpose.",
        task: "Stress: 2008 vol regime — caps holding",
        palette: { k: "#0a1a0a", h: "#0a1a0a", H: "#000000", s: "#22c55e", S: "#15803d",
            e: "#fde047", m: "#0a0a0a", c: "#7c2d12", C: "#451a09",
            a: "#cfd9ec", A: "#9ca3af", p: "#3f3f46", P: "#27272a" },
    },
];
const OVERLAYS = {
    CAPE: CAPE_OVERLAY,
    HELMET: HELMET_OVERLAY,
    MASK: MASK_OVERLAY,
    EYEPATCH: EYEPATCH_OVERLAY,
    GLASSES: GLASSES_OVERLAY,
};
// Walking leg overlays: paint OVER rows 18-21 of the base sprite to show a
// small alternating side-step. Used when the agent is in motion.
const WALK_LEGS_A = [
    // 22 rows; only last 4 carry data
    ...Array(18).fill("................"),
    "..cppppppppppc..",
    "..cppPPPPpppPc..", // shifted shadow
    "...pp.....ppp...", // right leg one px right
    "...kk.....kkk...",
];
const WALK_LEGS_B = [
    ...Array(18).fill("................"),
    "..cppppppppppc..",
    "..cppPPPPPPppc..",
    "...ppp.....pp...", // left leg one px left
    "...kkk.....kk...",
];
// Speech-bubble overlay (small) — drawn above head when agent has a bubble
function drawBubble(ctx, x, y, icon, color = "#cfd9ec") {
    // bubble body 12x9
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 12, 9);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x + 1, y + 1, 10, 7);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 5, y + 9, 2, 1);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x + 5, y + 9, 1, 1);
    // tail dot
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 6, y + 10, 1, 1);
    // icon glyph (1-2 chars rendered as pixel art)
    ctx.fillStyle = "#1c1c1c";
    if (icon === "?") {
        ctx.fillRect(x + 4, y + 2, 4, 1);
        ctx.fillRect(x + 7, y + 3, 1, 1);
        ctx.fillRect(x + 6, y + 4, 1, 1);
        ctx.fillRect(x + 5, y + 5, 1, 1);
        ctx.fillRect(x + 5, y + 7, 1, 1);
    }
    else if (icon === "☕" || icon === "coffee") {
        ctx.fillStyle = "#7c2d12";
        ctx.fillRect(x + 3, y + 3, 5, 4);
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 8, y + 4, 1, 2);
        // steam
        ctx.fillStyle = color;
        ctx.fillRect(x + 4, y + 1, 1, 1);
        ctx.fillRect(x + 6, y + 1, 1, 1);
    }
    else if (icon === "💧" || icon === "water") {
        ctx.fillStyle = "#38bdf8";
        ctx.fillRect(x + 5, y + 2, 2, 1);
        ctx.fillRect(x + 4, y + 3, 4, 4);
        ctx.fillRect(x + 5, y + 7, 2, 1);
    }
    else if (icon === "📺" || icon === "screen") {
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 3, y + 2, 6, 5);
        ctx.fillStyle = "#22c55e";
        ctx.fillRect(x + 4, y + 3, 4, 3);
    }
    else if (icon === "🖨" || icon === "print") {
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 3, y + 3, 6, 4);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(x + 4, y + 5, 4, 2);
    }
    else if (icon === "✎" || icon === "pen") {
        ctx.fillStyle = "#fb923c";
        ctx.fillRect(x + 3, y + 5, 6, 1);
        ctx.fillStyle = "#1c1c1c";
        ctx.fillRect(x + 8, y + 4, 1, 3);
        ctx.fillStyle = "#fde047";
        ctx.fillRect(x + 4, y + 3, 1, 2);
    }
    else if (icon === "!") {
        ctx.fillStyle = "#dc2626";
        ctx.fillRect(x + 5, y + 2, 2, 4);
        ctx.fillRect(x + 5, y + 7, 2, 1);
    }
}
// Render a complete agent at (x, y) on ctx
function drawAgent(ctx, agent, x, y, opts = {}) {
    const bobAmt = (opts.bob || 0);
    const walking = !!opts.walking;
    // cape goes BEHIND character
    if (agent.overlay && agent.overlay.sprite === "CAPE") {
        drawSprite(ctx, OVERLAYS.CAPE, x, y + bobAmt, agent.overlay.palette, opts);
    }
    drawSprite(ctx, CHAR_BASE, x, y + bobAmt, agent.palette, opts);
    if (walking) {
        const legs = (opts.legFrame || 0) ? WALK_LEGS_B : WALK_LEGS_A;
        drawSprite(ctx, legs, x, y + bobAmt, agent.palette, opts);
    }
    if (agent.overlay && agent.overlay.sprite !== "CAPE") {
        drawSprite(ctx, OVERLAYS[agent.overlay.sprite], x, y + bobAmt, agent.overlay.palette, opts);
    }
    if (opts.bubble) {
        drawBubble(ctx, x + 14, y - 11, opts.bubble);
    }
}
Object.assign(window, { CHAR_BASE, CAPE_OVERLAY, OVERLAYS, AGENTS, drawSprite, drawAgent,
    DESK_BACK, DESK_FRONT, PLANT, MUG, POPUP, SERVER, WINDOW, HEX });


// === scene.jsx ===
// Office scene composer — wall, floor, props, animated agents.
const SCENE_W = 480;
const SCENE_H = 270;
// ---------- FLOOR ----------
function paintFloor(ctx) {
    const planks = [
        ["#5a3826", "#4a2e1f"],
        ["#664030", "#553626"],
        ["#5e3a2a", "#4d2f22"],
    ];
    const FLOOR_TOP = 92;
    for (let y = FLOOR_TOP; y < SCENE_H; y++) {
        const rowIdx = Math.floor((y - FLOOR_TOP) / 8) % planks.length;
        const [base, dark] = planks[rowIdx];
        ctx.fillStyle = base;
        ctx.fillRect(0, y, SCENE_W, 1);
        if ((y - FLOOR_TOP) % 8 === 0) {
            ctx.fillStyle = dark;
            ctx.fillRect(0, y, SCENE_W, 1);
        }
    }
    ctx.fillStyle = "#3a2317";
    const seamCols = [40, 110, 180, 240, 310, 380, 440];
    for (let r = 0; r < 24; r++) {
        const y = FLOOR_TOP + r * 8;
        if (y >= SCENE_H)
            break;
        const off = (r * 13) % 70;
        for (const c of seamCols)
            ctx.fillRect(c + off, y, 1, 8);
    }
    // Center aisle rug (subtle, helps separate front/back zones)
    ctx.fillStyle = "rgba(20,30,55,0.25)";
    ctx.fillRect(0, 144, SCENE_W, 12);
}
// ---------- WALL ----------
function paintWall(ctx, frame) {
    ctx.fillStyle = "#0e1a2e";
    ctx.fillRect(0, 0, SCENE_W, 92);
    ctx.fillStyle = "#152238";
    for (let x = 0; x < SCENE_W; x += 6)
        ctx.fillRect(x, 0, 1, 86);
    ctx.fillStyle = "#1c2c44";
    ctx.fillRect(0, 86, SCENE_W, 1);
    ctx.fillStyle = "#0a1424";
    ctx.fillRect(0, 87, SCENE_W, 3);
    ctx.fillStyle = "#1c2c44";
    ctx.fillRect(0, 90, SCENE_W, 1);
    // Far-left whiteboard (replaces window)
    drawWhiteboard(ctx, 8, 18, 46, 46, frame);
    // Left small window
    function drawWindow(x, y, w, h) {
        ctx.fillStyle = "#1c2c44";
        ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
        ctx.fillStyle = "#3a5680";
        ctx.fillRect(x, y, w, h);
        ctx.fillStyle = "#5377a0";
        ctx.fillRect(x, y + 2, w, 1);
        ctx.fillStyle = "#7a9bc4";
        ctx.fillRect(x, y + 5, w, 1);
        ctx.fillStyle = "#0a1424";
        ctx.fillRect(x + Math.floor(w / 2), y, 1, h);
        ctx.fillRect(x, y + Math.floor(h / 2), w, 1);
        ctx.fillStyle = "#fbbf24";
        for (let i = 0; i < 8; i++) {
            const lx = x + 2 + ((i * 7) % (w - 4));
            const ly = y + 8 + (i % 3) * 4;
            if (ly < y + h - 1)
                ctx.fillRect(lx, ly, 1, 1);
        }
        ctx.fillStyle = "#2a3e5c";
        ctx.fillRect(x - 2, y - 2, w + 4, 1);
        ctx.fillRect(x - 2, y + h + 1, w + 4, 1);
    }
    drawWindow(64, 22, 30, 40);
    // Big wall monitor — center feature
    drawWallMonitor(ctx, 102, 14, 188, 56, frame);
    // Right small window
    drawWindow(298, 22, 30, 40);
    // Posters / clock to the right
    drawPoster(ctx, 336, 18, 18, 22, { bg: "#7f1d1d", style: "M" });
    drawPoster(ctx, 360, 18, 22, 22, { bg: "#0e7490", style: "chart" });
    drawWallClock(ctx, 392, 22, frame);
    drawPoster(ctx, 414, 18, 22, 22, { bg: "#1e3a8a", style: "agent" });
    drawPoster(ctx, 442, 18, 26, 22, { bg: "#15803d", style: "chart" });
    // Floor-line shadow
    ctx.fillStyle = "#080d18";
    ctx.fillRect(0, 88, SCENE_W, 2);
}
// ---------- DESK STATION ----------
function drawStation(ctx, x, y, opts = {}) {
    const screen = opts.screen || "#1e3a8a";
    const screenAccent = opts.accent || "#38bdf8";
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 10, y, 28, 22);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 12, y + 2, 24, 18);
    ctx.fillStyle = screen;
    ctx.fillRect(x + 13, y + 3, 22, 16);
    ctx.fillStyle = screenAccent;
    for (let i = 0; i < 5; i++) {
        const bh = 3 + ((i + opts.seed) % 5) * 2;
        ctx.fillRect(x + 14 + i * 4, y + 17 - bh, 3, bh);
    }
    if (opts.blink) {
        ctx.fillStyle = "#22c55e";
        ctx.fillRect(x + 33, y + 5, 1, 2);
    }
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 22, y + 22, 4, 3);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 18, y + 25, 12, 2);
    ctx.fillStyle = "#3d2817";
    ctx.fillRect(x, y + 27, 48, 4);
    ctx.fillStyle = "#5a3826";
    ctx.fillRect(x, y + 27, 48, 1);
    ctx.fillStyle = "#251509";
    ctx.fillRect(x, y + 30, 48, 1);
    ctx.fillStyle = "#3d2817";
    ctx.fillRect(x + 1, y + 31, 46, 14);
    ctx.fillStyle = "#251509";
    ctx.fillRect(x + 1, y + 31, 46, 1);
    ctx.fillStyle = "#5a3826";
    ctx.fillRect(x + 1, y + 32, 1, 12);
    ctx.fillStyle = "#1a0d05";
    ctx.fillRect(x + 46, y + 32, 1, 12);
}
function drawMug(ctx, x, y, color = "#facc15") {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 6, 7);
    ctx.fillStyle = color;
    ctx.fillRect(x + 1, y + 1, 4, 5);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 6, y + 2, 1, 3);
    ctx.fillStyle = "#cbd5e1";
    ctx.fillRect(x + 2, y - 2, 1, 1);
    ctx.fillRect(x + 3, y - 4, 1, 1);
}
function drawPlant(ctx, x, y) {
    ctx.fillStyle = "#15803d";
    ctx.fillRect(x + 2, y, 10, 2);
    ctx.fillStyle = "#22c55e";
    ctx.fillRect(x, y + 1, 14, 5);
    ctx.fillStyle = "#15803d";
    ctx.fillRect(x + 1, y + 3, 12, 1);
    ctx.fillStyle = "#16a34a";
    ctx.fillRect(x + 3, y + 2, 2, 2);
    ctx.fillStyle = "#16a34a";
    ctx.fillRect(x + 9, y + 3, 2, 2);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x + 4, y + 6, 6, 1);
    ctx.fillStyle = "#7c2d12";
    ctx.fillRect(x + 4, y + 7, 6, 4);
    ctx.fillStyle = "#451a09";
    ctx.fillRect(x + 4, y + 10, 6, 1);
}
function drawServer(ctx, x, y, frame) {
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(x, y, 22, 38);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x + 1, y + 1, 20, 36);
    for (let i = 0; i < 5; i++) {
        const ry = y + 3 + i * 7;
        ctx.fillStyle = "#0a0a0a";
        ctx.fillRect(x + 2, ry, 18, 5);
        ctx.fillStyle = ((frame + i * 5) >> 2) % 4 < 3 ? "#fde047" : "#a16207";
        ctx.fillRect(x + 3, ry + 1, 1, 1);
        ctx.fillStyle = "#22c55e";
        ctx.fillRect(x + 5, ry + 1, 1, 1);
        ctx.fillStyle = "#3a3a3a";
        for (let j = 0; j < 7; j++)
            ctx.fillRect(x + 7 + j * 2, ry + 2, 1, 2);
    }
}
// ---------- STATIONS ----------
const STATIONS = [
    { id: "superman", deskX: 12, deskY: 100, screen: "#1e40af", accent: "#fde047" },
    { id: "doctorstrange", deskX: 68, deskY: 100, screen: "#7f1d1d", accent: "#fbbf24" },
    { id: "blackpanther", deskX: 144, deskY: 100, screen: "#1a1a2e", accent: "#a78bfa" },
    { id: "thor", deskX: 200, deskY: 100, screen: "#0e7490", accent: "#fde047" },
    { id: "vision", deskX: 296, deskY: 100, screen: "#15803d", accent: "#fde047" },
    { id: "professorx", deskX: 352, deskY: 100, screen: "#3f3f46", accent: "#a78bfa" },
    { id: "ironman", deskX: 416, deskY: 100, screen: "#dc2626", accent: "#fde047" },
    { id: "aquaman", deskX: 18, deskY: 196, screen: "#0e7490", accent: "#22c55e" },
    { id: "spiderman", deskX: 78, deskY: 196, screen: "#dc2626", accent: "#1e40af" },
    { id: "batman", deskX: 138, deskY: 196, screen: "#1c1c1c", accent: "#fbbf24" },
    { id: "portfolio", deskX: 268, deskY: 196, screen: "#1e3a8a", accent: "#22c55e" },
    { id: "nickfury", deskX: 332, deskY: 196, screen: "#0a0a0a", accent: "#dc2626" },
    { id: "dailypnl", deskX: 396, deskY: 196, screen: "#7c2d12", accent: "#fbbf24" },
    // Newer agents
    { id: "hawkeye", deskX: 240, deskY: 100, screen: "#5b21b6", accent: "#fde047" },
    { id: "nighttrader", deskX: 198, deskY: 196, screen: "#0a0a14", accent: "#a78bfa" },
    { id: "hulk", deskX: 456, deskY: 196, screen: "#15803d", accent: "#fde047" },
];
// 3x5 pixel tiny font — supports digits, +, -, %, .
const TINY_FONT = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "100", "100"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "+": ["000", "010", "111", "010", "000"],
    "-": ["000", "000", "111", "000", "000"],
    "%": ["101", "001", "010", "100", "101"],
    ".": ["000", "000", "000", "000", "010"],
    " ": ["000", "000", "000", "000", "000"],
};
function drawTinyChar(ctx, ch, x, y) {
    const g = TINY_FONT[ch] || TINY_FONT[" "];
    for (let r = 0; r < 5; r++)
        for (let c = 0; c < 3; c++) {
            if (g[r][c] === "1")
                ctx.fillRect(x + c, y + r, 1, 1);
        }
}
function agentPosFor(station) {
    if (station.deskY < 150) {
        return { x: station.deskX + 12, y: station.deskY - 6 };
    }
    else {
        return { x: station.deskX + 12, y: station.deskY + 6 };
    }
}
// ---------- SCENE PAINTER ----------
function paintScene(ctx, frame, agents, motion, opts = {}) {
    paintWall(ctx, frame);
    paintFloor(ctx);
    // Mid-room props
    drawServer(ctx, 4, 200, frame); // server rack now front-left corner
    // Mid aisle furniture (around y=140-180, foreground of back row, behind front row)
    drawCoffeeStation(ctx, 196, 142); // matches POI 'coffee' (222,162)
    drawWaterCooler(ctx, 454, 138); // matches POI 'cooler' (462,168)
    drawPrinter(ctx, 376, 152); // matches POI 'printer'
    // Decorative plants
    drawPlant(ctx, 286, 113);
    drawPlant(ctx, 110, 209);
    drawPlant(ctx, 222, 209);
    drawFloorLamp(ctx, 446, 200, frame);
    drawTrash(ctx, 64, 230);
    drawTrash(ctx, 360, 230);
    // POI floor markers
    if (opts.showPoiMarkers !== false) {
        for (const p of POIS)
            drawPoiMarker(ctx, p.x, p.y + 4, "#38bdf8", frame);
    }
    // Desks (with optional trade-close flash overlay)
    const flashes = opts.flashes || {};
    for (const s of STATIONS) {
        const blink = ((frame + s.deskX) % 60) < 4;
        const flash = flashes[s.id];
        drawStation(ctx, s.deskX, s.deskY, { screen: s.screen, accent: s.accent, seed: s.deskX, blink });
        if (flash && flash.intensity > 0) {
            // Paint flash over the screen rect (x+13, y+3, 22, 16)
            ctx.globalAlpha = Math.min(1, flash.intensity);
            ctx.fillStyle = flash.color;
            ctx.fillRect(s.deskX + 13, s.deskY + 3, 22, 16);
            // Bezel glow
            ctx.globalAlpha = Math.min(0.6, flash.intensity * 0.6);
            ctx.fillRect(s.deskX + 10, s.deskY, 28, 22);
            ctx.globalAlpha = 1;
            // PnL text mini badge above monitor
            if (flash.intensity > 0.5 && flash.label) {
                ctx.fillStyle = "#0a0a0a";
                ctx.fillRect(s.deskX + 8, s.deskY - 8, flash.label.length * 4 + 4, 7);
                ctx.fillStyle = flash.color;
                // tiny pixel "text" — render label as thin bars; simple monospace font
                for (let i = 0; i < flash.label.length; i++) {
                    const ch = flash.label[i];
                    const cx = s.deskX + 10 + i * 4;
                    drawTinyChar(ctx, ch, cx, s.deskY - 7);
                }
            }
        }
        if ((s.deskX % 7) === 0 || s.deskY > 150) {
            drawMug(ctx, s.deskX + 2, s.deskY + 22, ["#facc15", "#dc2626", "#22c55e", "#38bdf8"][s.deskX % 4]);
        }
    }
    // Agents — sort by Y so closer agents draw on top
    const drawList = AGENTS.map(a => {
        const m = motion[a.id];
        const seated = m.mode === "at-desk";
        const pos = m.pos;
        return { agent: a, motion: m, pos, seated, y: pos.y };
    }).sort((a, b) => a.y - b.y);
    for (const item of drawList) {
        const { agent, motion: m, pos, seated } = item;
        const bob = seated
            ? (Math.sin((frame + agent.name.length) / 18) > 0.7 ? 1 : 0)
            : ((frame >> 1) % 2);
        const flip = !seated && m.dir < 0;
        const legFrame = !seated ? ((frame >> 2) % 2) : 0;
        drawAgent(ctx, agent, Math.round(pos.x), Math.round(pos.y), {
            bob, flip, walking: !seated, legFrame, bubble: m.bubble,
        });
    }
    // Optional: floor shadow under each agent (subtle)
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    for (const item of drawList) {
        if (!item.seated) {
            ctx.fillRect(Math.round(item.pos.x) + 4, Math.round(item.pos.y) + 22, 8, 1);
        }
    }
}
Object.assign(window, { SCENE_W, SCENE_H, STATIONS, paintScene, agentPosFor });


// === tweaks-panel.jsx ===
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// ─────────────────────────────────────────────────────────────────────────────
const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;width:100%;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;
// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
    const [values, setValues] = React.useState(defaults);
    // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
    // useState-style call doesn't write a "[object Object]" key into the persisted
    // JSON block.
    const setTweak = React.useCallback((keyOrEdits, val) => {
        const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null
            ? keyOrEdits : { [keyOrEdits]: val };
        setValues((prev) => (Object.assign(Object.assign({}, prev), edits)));
        window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, '*');
        // Same-window signal so in-page listeners (deck-stage rail thumbnails)
        // can react — the parent message only reaches the host, not peers.
        window.dispatchEvent(new CustomEvent('tweakchange', { detail: edits }));
    }, []);
    return [values, setTweak];
}
// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({ title = 'Tweaks', noDeckControls = false, children }) {
    const [open, setOpen] = React.useState(false);
    const dragRef = React.useRef(null);
    // Auto-inject a rail toggle when a <deck-stage> is on the page. The
    // toggle drives the deck's per-viewer _railVisible via window message;
    // state is mirrored from the same localStorage key the deck reads so
    // the control reflects reality across reloads. The mechanism is the
    // message — authors who want custom placement can post it directly
    // and pass noDeckControls to suppress this one.
    const hasDeckStage = React.useMemo(() => typeof document !== 'undefined' && !!document.querySelector('deck-stage'), []);
    // Hide the toggle until the host has actually enabled the rail (the
    // __omelette_rail_enabled window message, posted only when the
    // omelette_deck_rail_enabled flag is on for this user). The initial read
    // covers TweaksPanel mounting after the message already arrived; the
    // listener covers the common case of mounting first.
    const [railEnabled, setRailEnabled] = React.useState(() => { var _a; return hasDeckStage && !!((_a = document.querySelector('deck-stage')) === null || _a === void 0 ? void 0 : _a._railEnabled); });
    React.useEffect(() => {
        if (!hasDeckStage || railEnabled)
            return undefined;
        const onMsg = (e) => {
            if (e.data && e.data.type === '__omelette_rail_enabled')
                setRailEnabled(true);
        };
        window.addEventListener('message', onMsg);
        return () => window.removeEventListener('message', onMsg);
    }, [hasDeckStage, railEnabled]);
    const [railVisible, setRailVisible] = React.useState(() => {
        try {
            return localStorage.getItem('deck-stage.railVisible') !== '0';
        }
        catch (e) {
            return true;
        }
    });
    const toggleRail = (on) => {
        setRailVisible(on);
        window.postMessage({ type: '__deck_rail_visible', on }, '*');
    };
    const offsetRef = React.useRef({ x: 16, y: 16 });
    const PAD = 16;
    const clampToViewport = React.useCallback(() => {
        const panel = dragRef.current;
        if (!panel)
            return;
        const w = panel.offsetWidth, h = panel.offsetHeight;
        const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
        const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
        offsetRef.current = {
            x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
            y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y)),
        };
        panel.style.right = offsetRef.current.x + 'px';
        panel.style.bottom = offsetRef.current.y + 'px';
    }, []);
    React.useEffect(() => {
        if (!open)
            return;
        clampToViewport();
        if (typeof ResizeObserver === 'undefined') {
            window.addEventListener('resize', clampToViewport);
            return () => window.removeEventListener('resize', clampToViewport);
        }
        const ro = new ResizeObserver(clampToViewport);
        ro.observe(document.documentElement);
        return () => ro.disconnect();
    }, [open, clampToViewport]);
    React.useEffect(() => {
        const onMsg = (e) => {
            var _a;
            const t = (_a = e === null || e === void 0 ? void 0 : e.data) === null || _a === void 0 ? void 0 : _a.type;
            if (t === '__activate_edit_mode')
                setOpen(true);
            else if (t === '__deactivate_edit_mode')
                setOpen(false);
        };
        window.addEventListener('message', onMsg);
        window.parent.postMessage({ type: '__edit_mode_available' }, '*');
        return () => window.removeEventListener('message', onMsg);
    }, []);
    const dismiss = () => {
        setOpen(false);
        window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*');
    };
    const onDragStart = (e) => {
        const panel = dragRef.current;
        if (!panel)
            return;
        const r = panel.getBoundingClientRect();
        const sx = e.clientX, sy = e.clientY;
        const startRight = window.innerWidth - r.right;
        const startBottom = window.innerHeight - r.bottom;
        const move = (ev) => {
            offsetRef.current = {
                x: startRight - (ev.clientX - sx),
                y: startBottom - (ev.clientY - sy),
            };
            clampToViewport();
        };
        const up = () => {
            window.removeEventListener('mousemove', move);
            window.removeEventListener('mouseup', up);
        };
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
    };
    if (!open)
        return null;
    return (React.createElement(React.Fragment, null,
        React.createElement("style", null, __TWEAKS_STYLE),
        React.createElement("div", { ref: dragRef, className: "twk-panel", "data-noncommentable": "", style: { right: offsetRef.current.x, bottom: offsetRef.current.y } },
            React.createElement("div", { className: "twk-hd", onMouseDown: onDragStart },
                React.createElement("b", null, title),
                React.createElement("button", { className: "twk-x", "aria-label": "Close tweaks", onMouseDown: (e) => e.stopPropagation(), onClick: dismiss }, "\u2715")),
            React.createElement("div", { className: "twk-body" },
                children,
                hasDeckStage && railEnabled && !noDeckControls && (React.createElement(TweakSection, { label: "Deck" },
                    React.createElement(TweakToggle, { label: "Thumbnail rail", value: railVisible, onChange: toggleRail })))))));
}
// ── Layout helpers ──────────────────────────────────────────────────────────
function TweakSection({ label, children }) {
    return (React.createElement(React.Fragment, null,
        React.createElement("div", { className: "twk-sect" }, label),
        children));
}
function TweakRow({ label, value, children, inline = false }) {
    return (React.createElement("div", { className: inline ? 'twk-row twk-row-h' : 'twk-row' },
        React.createElement("div", { className: "twk-lbl" },
            React.createElement("span", null, label),
            value != null && React.createElement("span", { className: "twk-val" }, value)),
        children));
}
// ── Controls ────────────────────────────────────────────────────────────────
function TweakSlider({ label, value, min = 0, max = 100, step = 1, unit = '', onChange }) {
    return (React.createElement(TweakRow, { label: label, value: `${value}${unit}` },
        React.createElement("input", { type: "range", className: "twk-slider", min: min, max: max, step: step, value: value, onChange: (e) => onChange(Number(e.target.value)) })));
}
function TweakToggle({ label, value, onChange }) {
    return (React.createElement("div", { className: "twk-row twk-row-h" },
        React.createElement("div", { className: "twk-lbl" },
            React.createElement("span", null, label)),
        React.createElement("button", { type: "button", className: "twk-toggle", "data-on": value ? '1' : '0', role: "switch", "aria-checked": !!value, onClick: () => onChange(!value) },
            React.createElement("i", null))));
}
function TweakRadio({ label, value, options, onChange }) {
    var _a;
    const trackRef = React.useRef(null);
    const [dragging, setDragging] = React.useState(false);
    // The active value is read by pointer-move handlers attached for the lifetime
    // of a drag — ref it so a stale closure doesn't fire onChange for every move.
    const valueRef = React.useRef(value);
    valueRef.current = value;
    // Segments wrap mid-word once per-segment width runs out. The track is
    // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
    // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
    // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
    // back to a dropdown rather than wrap.
    const labelLen = (o) => String(typeof o === 'object' ? o.label : o).length;
    const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
    const fitsAsSegments = maxLen <= ((_a = { 2: 16, 3: 10 }[options.length]) !== null && _a !== void 0 ? _a : 0);
    if (!fitsAsSegments) {
        // <select> emits strings — map back to the original option value so the
        // fallback stays type-preserving (numbers, booleans) like the segment path.
        const resolve = (s) => {
            const m = options.find((o) => String(typeof o === 'object' ? o.value : o) === s);
            return m === undefined ? s : typeof m === 'object' ? m.value : m;
        };
        return React.createElement(TweakSelect, { label: label, value: value, options: options, onChange: (s) => onChange(resolve(s)) });
    }
    const opts = options.map((o) => (typeof o === 'object' ? o : { value: o, label: o }));
    const idx = Math.max(0, opts.findIndex((o) => o.value === value));
    const n = opts.length;
    const segAt = (clientX) => {
        const r = trackRef.current.getBoundingClientRect();
        const inner = r.width - 4;
        const i = Math.floor(((clientX - r.left - 2) / inner) * n);
        return opts[Math.max(0, Math.min(n - 1, i))].value;
    };
    const onPointerDown = (e) => {
        setDragging(true);
        const v0 = segAt(e.clientX);
        if (v0 !== valueRef.current)
            onChange(v0);
        const move = (ev) => {
            if (!trackRef.current)
                return;
            const v = segAt(ev.clientX);
            if (v !== valueRef.current)
                onChange(v);
        };
        const up = () => {
            setDragging(false);
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
    };
    return (React.createElement(TweakRow, { label: label },
        React.createElement("div", { ref: trackRef, role: "radiogroup", onPointerDown: onPointerDown, className: dragging ? 'twk-seg dragging' : 'twk-seg' },
            React.createElement("div", { className: "twk-seg-thumb", style: { left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
                    width: `calc((100% - 4px) / ${n})` } }),
            opts.map((o) => (React.createElement("button", { key: o.value, type: "button", role: "radio", "aria-checked": o.value === value }, o.label))))));
}
function TweakSelect({ label, value, options, onChange }) {
    return (React.createElement(TweakRow, { label: label },
        React.createElement("select", { className: "twk-field", value: value, onChange: (e) => onChange(e.target.value) }, options.map((o) => {
            const v = typeof o === 'object' ? o.value : o;
            const l = typeof o === 'object' ? o.label : o;
            return React.createElement("option", { key: v, value: v }, l);
        }))));
}
function TweakText({ label, value, placeholder, onChange }) {
    return (React.createElement(TweakRow, { label: label },
        React.createElement("input", { className: "twk-field", type: "text", value: value, placeholder: placeholder, onChange: (e) => onChange(e.target.value) })));
}
function TweakNumber({ label, value, min, max, step = 1, unit = '', onChange }) {
    const clamp = (n) => {
        if (min != null && n < min)
            return min;
        if (max != null && n > max)
            return max;
        return n;
    };
    const startRef = React.useRef({ x: 0, val: 0 });
    const onScrubStart = (e) => {
        e.preventDefault();
        startRef.current = { x: e.clientX, val: value };
        const decimals = (String(step).split('.')[1] || '').length;
        const move = (ev) => {
            const dx = ev.clientX - startRef.current.x;
            const raw = startRef.current.val + dx * step;
            const snapped = Math.round(raw / step) * step;
            onChange(clamp(Number(snapped.toFixed(decimals))));
        };
        const up = () => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
    };
    return (React.createElement("div", { className: "twk-num" },
        React.createElement("span", { className: "twk-num-lbl", onPointerDown: onScrubStart }, label),
        React.createElement("input", { type: "number", value: value, min: min, max: max, step: step, onChange: (e) => onChange(clamp(Number(e.target.value))) }),
        unit && React.createElement("span", { className: "twk-num-unit" }, unit)));
}
// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
    const h = String(hex).replace('#', '');
    const x = h.length === 3 ? h.replace(/./g, (c) => c + c) : h.padEnd(6, '0');
    const n = parseInt(x.slice(0, 6), 16);
    if (Number.isNaN(n))
        return true;
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    return r * 299 + g * 587 + b * 114 > 148000;
}
const __TwkCheck = ({ light }) => (React.createElement("svg", { viewBox: "0 0 14 14", "aria-hidden": "true" },
    React.createElement("path", { d: "M3 7.2 5.8 10 11 4.2", fill: "none", strokeWidth: "2.2", strokeLinecap: "round", strokeLinejoin: "round", stroke: light ? 'rgba(0,0,0,.78)' : '#fff' })));
// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({ label, value, options, onChange }) {
    if (!options || !options.length) {
        return (React.createElement("div", { className: "twk-row twk-row-h" },
            React.createElement("div", { className: "twk-lbl" },
                React.createElement("span", null, label)),
            React.createElement("input", { type: "color", className: "twk-swatch", value: value, onChange: (e) => onChange(e.target.value) })));
    }
    // Native <input type=color> emits lowercase hex per the HTML spec, so
    // compare case-insensitively. String() guards JSON.stringify(undefined),
    // which returns the primitive undefined (no .toLowerCase).
    const key = (o) => String(JSON.stringify(o)).toLowerCase();
    const cur = key(value);
    return (React.createElement(TweakRow, { label: label },
        React.createElement("div", { className: "twk-chips", role: "radiogroup" }, options.map((o, i) => {
            const colors = Array.isArray(o) ? o : [o];
            const [hero, ...rest] = colors;
            const sup = rest.slice(0, 4);
            const on = key(o) === cur;
            return (React.createElement("button", { key: i, type: "button", className: "twk-chip", role: "radio", "aria-checked": on, "data-on": on ? '1' : '0', "aria-label": colors.join(', '), title: colors.join(' · '), style: { background: hero }, onClick: () => onChange(o) },
                sup.length > 0 && (React.createElement("span", null, sup.map((c, j) => React.createElement("i", { key: j, style: { background: c } })))),
                on && React.createElement(__TwkCheck, { light: __twkIsLight(hero) })));
        }))));
}
function TweakButton({ label, onClick, secondary = false }) {
    return (React.createElement("button", { type: "button", className: secondary ? 'twk-btn secondary' : 'twk-btn', onClick: onClick }, label));
}
Object.assign(window, {
    useTweaks, TweaksPanel, TweakSection, TweakRow,
    TweakSlider, TweakToggle, TweakRadio, TweakSelect,
    TweakText, TweakNumber, TweakColor, TweakButton,
});


// === live-data.jsx ===
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
    }
    catch (_) { /* fall through to mock */ }
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
            if (items.length)
                return items;
        }
    }
    catch (_) { /* fall through */ }
    return MOCK_FEED.slice(0, 20);
}
const MOCK_FEED = [
    { t: "12:04:21", who: "Superman", msg: "FOMC minutes parsed → 3 signals routed" },
    { t: "12:04:18", who: "DocStrange", msg: "Unusual flow on QQQ — flag raised" },
    { t: "12:04:14", who: "Vision", msg: "Strategy v07 ranked #1 (sharpe 2.31)" },
    { t: "12:04:09", who: "IronMan", msg: "Order batch 7/9 filled" },
    { t: "12:04:02", who: "Batman", msg: "Drawdown 0.4% — within band" },
    { t: "12:03:58", who: "NickFury", msg: "Approved L2 strategy, 60% sizing" },
    { t: "12:03:51", who: "DailyPnLW.", msg: "Drafted PnL note v04" },
    { t: "12:03:44", who: "NightTrader", msg: "JPY carry opened, +0.18%" },
    { t: "12:03:39", who: "Hawkeye", msg: "Hidden bid sniped — 1200 SOL" },
    { t: "12:03:30", who: "Hulk", msg: "Risk cap raised — 1.5× notional" },
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
        if (cancelled || mockTimer)
            return;
        function tick() {
            if (cancelled)
                return;
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
        if (status === "SKIPPED" || status === "PENDING")
            return null;
        if (status === "ERROR" || status === "REJECTED" || status === "FAILED")
            return "loss";
        return "win";
    }
    function deriveFromPayload(payload) {
        var _a;
        const trades = Array.isArray(payload === null || payload === void 0 ? void 0 : payload.trades) ? payload.trades : [];
        for (const t of trades) {
            const side = classifyTrade(t);
            if (!side)
                continue;
            const key = [
                t.timestamp || "", t.symbol || "", t.side || "",
                t.status || "",
                (_a = t.notional_usd) !== null && _a !== void 0 ? _a : 0,
            ].join("|");
            if (seenKeys.has(key))
                continue;
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
                }
                catch (_) { /* ignore */ }
            };
            ws.onerror = () => { };
            ws.onclose = () => {
                if (cancelled)
                    return;
                // If we never received a real trade, fall back to the mock
                // emitter so the office never feels frozen during standalone
                // preview / dev mode.
                if (!receivedAnyTrade)
                    startMock();
            };
        }
        catch (_) {
            startMock();
        }
    }
    startWs();
    // Safety net — if /ws hasn't produced a trade after 8s, start the
    // synthetic emitter so the cena keeps moving.
    setTimeout(() => {
        if (!cancelled && !receivedAnyTrade)
            startMock();
    }, 8000);
    return () => {
        cancelled = true;
        if (mockTimer)
            clearTimeout(mockTimer);
        if (ws && ws.readyState <= 1)
            try {
                ws.close();
            }
            catch (_a) { }
    };
}
// ---------- AGENT STATUS PUSH (mock) ----------
// In production, emit "task changed" events from your orchestrator and
// push them through this channel so the side panel updates in real time.
function subscribeAgentTasks(cb) {
    let cancelled = false;
    function tick() {
        if (cancelled)
            return;
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


// === app.jsx ===
// App shell — header, scene canvas with motion + hit overlays, side panel,
// floating action callouts, activity ticker, tweaks panel.
const { useState, useEffect, useRef, useMemo } = React;
// ---------------------------------------------------------------------------
// Trading Mode Panel
// ---------------------------------------------------------------------------
const MODE_META = {
    conservative: { label: "🛡️ Conservador", color: "#22c55e", desc: "Posições pequenas · BTC only · 0.5% · 2x" },
    balanced: { label: "⚖️ Balanceado", color: "#38bdf8", desc: "Configuração padrão · 2% · 5x · BTC/ETH/SOL" },
    aggressive: { label: "⚡ Agressivo", color: "#fb923c", desc: "Máximo desempenho · 5% · 10x · 4 ativos" },
};
function TradingModePanel() {
    const [mode, setMode] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [offline, setOffline] = useState(false);
    function loadMode() {
        fetch('/api/mode?t=' + Date.now())
            .then(r => {
            if (!r.ok)
                throw new Error('HTTP ' + r.status);
            return r.json();
        })
            .then(d => { setMode(d.mode); setOffline(false); setError(null); })
            .catch(e => { setOffline(true); setError('API offline: ' + e.message); });
    }
    useEffect(() => { loadMode(); }, []);
    async function changeMode(newMode) {
        if (loading || newMode === mode)
            return;
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode }),
            });
            const text = await res.text();
            if (!res.ok)
                throw new Error('HTTP ' + res.status + ': ' + text);
            setMode(newMode);
            setOffline(false);
        }
        catch (e) {
            setError(e.message);
        }
        finally {
            setLoading(false);
        }
    }
    const activeMeta = (!offline && mode) ? MODE_META[mode] : null;
    return (React.createElement("div", { style: {
            background: 'var(--panel)',
            border: '1px solid var(--line)',
            borderTop: offline ? '3px solid #ef4444' : (activeMeta ? `3px solid ${activeMeta.color}` : '3px solid var(--line)'),
            borderRadius: 6,
            padding: 18,
            marginBottom: 16,
        } },
        React.createElement("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 } },
            React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', color: offline ? '#ef4444' : 'var(--orange)' } }, offline ? '✖ TRADING MODE — OFFLINE' : '⚙ Trading Mode'),
            offline && (React.createElement("button", { onClick: loadMode, style: { fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim)', background: 'none', border: '1px solid var(--line)', borderRadius: 3, padding: '2px 6px', cursor: 'pointer' } }, "\u21BB retry"))),
        offline ? (React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 10, color: '#ef4444', lineHeight: 1.6 } },
            React.createElement("div", null, error),
            React.createElement("div", { style: { color: 'var(--text-dim)', marginTop: 6 } },
                "Reinicie o servidor: ",
                React.createElement("span", { style: { color: 'var(--text)' } }, "pkill -f \"python run.py\" && python run.py --dashboard")))) : (React.createElement("div", { style: { display: 'flex', flexDirection: 'column', gap: 8 } }, Object.entries(MODE_META).map(([id, meta]) => {
            const active = mode === id;
            return (React.createElement("button", { key: id, onClick: () => changeMode(id), disabled: loading, style: {
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px',
                    background: active ? `rgba(${hexToRgb(meta.color)},0.12)` : 'rgba(5,11,24,0.6)',
                    border: `1px solid ${active ? meta.color : 'var(--line)'}`,
                    borderRadius: 4,
                    cursor: loading ? 'wait' : 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                } },
                React.createElement("div", { style: { width: 8, height: 8, borderRadius: '50%', background: active ? meta.color : 'var(--text-mute)', flexShrink: 0, boxShadow: active ? `0 0 6px ${meta.color}` : 'none' } }),
                React.createElement("div", null,
                    React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600, color: active ? meta.color : 'var(--text)' } }, meta.label),
                    React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)', marginTop: 2 } }, meta.desc)),
                active && React.createElement("div", { style: { marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 9, color: meta.color, letterSpacing: '0.1em' } }, "ATIVO")));
        }))),
        error && !offline && React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 11, color: '#ef4444', marginTop: 8 } }, error),
        loading && React.createElement("div", { style: { fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)', marginTop: 8 } }, "Aplicando...")));
}
function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r},${g},${b}`;
}
const ACTIONS = [
    { id: "fanout", from: "nickfury", to: "portfolio", label: "ASSIGN BOOK", color: "#22c55e" },
    { id: "synth", from: "superman", to: "vision", label: "FORWARD SIGNAL", color: "#38bdf8" },
    { id: "exec", from: "vision", to: "ironman", label: "EXECUTE PLAN", color: "#fb923c" },
    { id: "watch", from: "ironman", to: "batman", label: "RISK CHECK", color: "#facc15" },
    { id: "report", from: "portfolio", to: "dailypnl", label: "WRITE PNL", color: "#a78bfa" },
    { id: "search", from: "doctorstrange", to: "__search", label: "SEARCH WEB", color: "#38bdf8" },
];
const ANCHORS = {
    __search: { x: 471, y: 110 },
};
function getAnchor(id) {
    if (ANCHORS[id])
        return ANCHORS[id];
    const station = STATIONS.find(s => s.id === id);
    if (!station)
        return { x: SCENE_W / 2, y: SCENE_H / 2 };
    const pos = agentPosFor(station);
    return { x: pos.x + 8, y: pos.y - 2 };
}
function App() {
    var _a, _b, _c, _d;
    const canvasRef = useRef(null);
    const motionRef = useRef(makeInitialMotion());
    const flashesRef = useRef({}); // stationId → { color, label, until }
    const [frame, setFrame] = useState(0);
    const [selected, setSelected] = useState("nickfury");
    const [feedEvents, setFeedEvents] = useState([]);
    const [agentTasks, setAgentTasks] = useState({});
    const [tweaks, setTweaks] = useTweaks(/*EDITMODE-BEGIN*/ {
        "scale": 3,
        "showLabels": true,
        "showActions": true,
        "showMotion": true,
        "maxAway": 3,
        "showPoiMarkers": true,
        "mode": "active"
    } /*EDITMODE-END*/);
    // Initial data load + subscriptions to live data layer
    useEffect(() => {
        fetchFeedEvents().then(setFeedEvents);
        fetchAgentTasks().then(setAgentTasks);
        const unsubTrade = subscribeTradeEvents((ev) => {
            // Flash this station's monitor
            flashesRef.current[ev.stationId] = {
                color: ev.side === "win" ? "#22c55e" : "#ef4444",
                label: (ev.pnl >= 0 ? "+" : "") + ev.pnl + "%",
                until: 18, // ~1.4s
                max: 18,
            };
            // Push to feed
            const agent = AGENTS.find(a => a.id === ev.stationId);
            const time = new Date().toTimeString().slice(0, 8);
            const msg = `${ev.side === "win" ? "CLOSED +" : "CLOSED "}${ev.pnl}% on ${ev.sym} (${ev.size} clip)`;
            setFeedEvents(prev => [{ t: time, who: (agent === null || agent === void 0 ? void 0 : agent.name) || ev.stationId, msg }, ...prev].slice(0, 24));
        });
        const unsubTask = subscribeAgentTasks((ev) => {
            setAgentTasks(prev => (Object.assign(Object.assign({}, prev), { [ev.agentId]: ev.task })));
        });
        return () => { unsubTrade(); unsubTask(); };
    }, []);
    useEffect(() => {
        let raf, last = 0, tick = 0;
        function loop(t) {
            if (t - last > 80) {
                tick++;
                last = t;
                if (tweaks.showMotion) {
                    tickMotion(motionRef.current, tick, { maxAway: Number(tweaks.maxAway) });
                }
                // Decay flashes
                const fl = flashesRef.current;
                for (const k in fl) {
                    fl[k].until -= 1;
                    if (fl[k].until <= 0)
                        delete fl[k];
                }
                setFrame(tick);
            }
            raf = requestAnimationFrame(loop);
        }
        raf = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(raf);
    }, [tweaks.showMotion, tweaks.maxAway]);
    // Render to canvas every frame
    useEffect(() => {
        const cvs = canvasRef.current;
        if (!cvs)
            return;
        const ctx = cvs.getContext("2d");
        ctx.imageSmoothingEnabled = false;
        // Build flash snapshot with normalized intensity
        const flashSnap = {};
        for (const k in flashesRef.current) {
            const f = flashesRef.current[k];
            flashSnap[k] = { color: f.color, label: f.label, intensity: f.until / f.max };
        }
        paintScene(ctx, frame, AGENTS, motionRef.current, {
            showPoiMarkers: tweaks.showPoiMarkers,
            flashes: flashSnap,
        });
    }, [frame, tweaks.showPoiMarkers]);
    const selectedAgent = AGENTS.find(a => a.id === selected) || AGENTS[0];
    const liveTask = agentTasks[selectedAgent.id] || selectedAgent.task;
    const scale = Number(tweaks.scale) || 3;
    const feedEventsLegacy = useMemo(() => [], []);
    // Build a snapshot of motion to drive the React-side overlays (labels, hits)
    // We re-read motionRef on every frame.
    const motion = motionRef.current;
    return (React.createElement("div", { className: "page" },
        React.createElement("header", { className: "hdr" },
            React.createElement("div", { className: "hdr-l" },
                React.createElement("div", { className: "hdr-eyebrow" }, "MEKKA OPS \u00B7 L4 COMMAND"),
                React.createElement("h1", null, "Mekka Pixel Office"),
                React.createElement("div", { className: "hdr-sub" },
                    "Self-growing AI trading floor \u00B7 ",
                    AGENTS.length,
                    " agents on duty")),
            React.createElement("div", { className: "hdr-r" },
                React.createElement("div", { className: `pill ${tweaks.mode === 'active' ? 'pill-on' : 'pill-off'}` },
                    React.createElement("span", { className: "dot" }),
                    tweaks.mode === 'active' ? 'MARKET LIVE' : 'STAND-DOWN'),
                React.createElement("div", { className: "pill pill-muted" }, "PAPER \u00B7 testnet"),
                React.createElement("div", { className: "pill pill-muted" }, "UPTIME 04:12:38"))),
        React.createElement("div", { className: "main" },
            React.createElement("div", { className: "scene-col" },
                React.createElement("div", { className: "scene-frame" },
                    React.createElement("div", { className: "scene-frame-hdr" },
                        React.createElement("div", { className: "frame-tabs" },
                            React.createElement("span", { className: "tab active" }, "Pixel Office"),
                            React.createElement("span", { className: "tab" }, "Layer Map"),
                            React.createElement("span", { className: "tab" }, "Roster")),
                        React.createElement("div", { className: "frame-legend" },
                            React.createElement("span", null,
                                React.createElement("i", { style: { background: "#38bdf8" } }),
                                " L1 Analysis"),
                            React.createElement("span", null,
                                React.createElement("i", { style: { background: "#a78bfa" } }),
                                " L2 Strategy"),
                            React.createElement("span", null,
                                React.createElement("i", { style: { background: "#fb923c" } }),
                                " L3 Risk/Exec"),
                            React.createElement("span", null,
                                React.createElement("i", { style: { background: "#22c55e" } }),
                                " L4 Command"))),
                    React.createElement("div", { className: "scene-wrap", style: {
                            width: SCENE_W * scale, height: SCENE_H * scale,
                        } },
                        React.createElement("canvas", { ref: canvasRef, width: SCENE_W, height: SCENE_H, style: { width: SCENE_W * scale, height: SCENE_H * scale } }),
                        tweaks.showActions && (React.createElement("svg", { className: "action-svg", viewBox: `0 0 ${SCENE_W} ${SCENE_H}`, preserveAspectRatio: "none", style: { width: SCENE_W * scale, height: SCENE_H * scale } },
                            React.createElement("defs", null, ACTIONS.map(a => (React.createElement("marker", { key: a.id, id: `arr-${a.id}`, viewBox: "0 0 8 8", refX: "6", refY: "4", markerWidth: "6", markerHeight: "6", orient: "auto" },
                                React.createElement("path", { d: "M0,0 L8,4 L0,8 L2,4 Z", fill: a.color }))))),
                            ACTIONS.map(a => {
                                const f = getAnchor(a.from), t = getAnchor(a.to);
                                const dash = (frame * 2) % 12;
                                return (React.createElement("line", { key: a.id, x1: f.x, y1: f.y, x2: t.x, y2: t.y, stroke: a.color, strokeWidth: "1.5", strokeDasharray: "4 3", strokeDashoffset: -dash, markerEnd: `url(#arr-${a.id})`, opacity: "0.85" }));
                            }))),
                        tweaks.showLabels && AGENTS.map(a => {
                            const m = motion[a.id];
                            if (!m)
                                return null;
                            const isSel = a.id === selected;
                            return (React.createElement("button", { key: a.id, className: `agent-label ${isSel ? 'sel' : ''} ${m.mode !== 'at-desk' ? 'walking' : ''}`, style: {
                                    left: (m.pos.x + 6) * scale,
                                    top: (m.pos.y - 14) * scale,
                                    borderColor: a.color,
                                    color: a.color,
                                }, onClick: () => setSelected(a.id) }, a.name.toUpperCase()));
                        }),
                        tweaks.showActions && ACTIONS.map(a => {
                            const f = getAnchor(a.from), t = getAnchor(a.to);
                            const mx = (f.x + t.x) / 2, my = (f.y + t.y) / 2;
                            return (React.createElement("div", { key: `lbl-${a.id}`, className: "action-lbl", style: { left: mx * scale, top: my * scale,
                                    color: a.color, borderColor: a.color } }, a.label));
                        }),
                        tweaks.showPoiMarkers && POIS.map(p => (React.createElement("div", { key: p.id, className: "poi-lbl", style: { left: p.x * scale, top: (p.y + 22) * scale } }, p.label))),
                        AGENTS.map(a => {
                            const m = motion[a.id];
                            if (!m)
                                return null;
                            return (React.createElement("div", { key: `hit-${a.id}`, className: "agent-hit", onClick: () => setSelected(a.id), style: {
                                    left: m.pos.x * scale, top: m.pos.y * scale,
                                    width: 16 * scale, height: 22 * scale,
                                } }));
                        })),
                    React.createElement("div", { className: "scene-caption" },
                        React.createElement("span", { className: "cap-key" }, "L1 \u2192 L2 \u2192 L3 \u2192 L4"),
                        React.createElement("span", { className: "cap-sep" }, "\u00B7"),
                        React.createElement("span", null, "Agents leave their desks for coffee, the wall TV, or the whiteboard. Click anyone for detail."))),
                React.createElement("div", { className: "ticker" },
                    React.createElement("div", { className: "ticker-hdr" },
                        React.createElement("span", { className: "ticker-dot" }),
                        React.createElement("span", null, "HERO AUDIT STREAM"),
                        React.createElement("span", { className: "ticker-spacer" }),
                        React.createElement("span", { className: "ticker-meta" },
                            feedEvents.length,
                            " events \u00B7 5s window")),
                    React.createElement("div", { className: "ticker-body" }, feedEvents.map((e, i) => (React.createElement("div", { key: i, className: "ticker-row" },
                        React.createElement("span", { className: "t-time" }, e.t),
                        React.createElement("span", { className: "t-who" }, e.who),
                        React.createElement("span", { className: "t-msg" }, e.msg))))))),
            React.createElement("aside", { className: "side" },
                React.createElement("div", { className: "agent-card", style: { borderColor: selectedAgent.color } },
                    React.createElement("div", { className: "agent-card-top" },
                        React.createElement("div", { className: "agent-portrait" },
                            React.createElement(AgentPortrait, { agent: selectedAgent })),
                        React.createElement("div", null,
                            React.createElement("div", { className: "agent-layer", style: { color: selectedAgent.color } },
                                selectedAgent.layer,
                                " \u00B7 ",
                                selectedAgent.role),
                            React.createElement("div", { className: "agent-name" }, selectedAgent.name),
                            React.createElement("div", { className: "agent-status" },
                                React.createElement("span", { className: "status-dot", style: { background: selectedAgent.color } }),
                                ((_a = motion[selectedAgent.id]) === null || _a === void 0 ? void 0 : _a.mode) === 'at-desk' ? 'AT DESK' :
                                    ((_b = motion[selectedAgent.id]) === null || _b === void 0 ? void 0 : _b.mode) === 'walking' ? 'WALKING' :
                                        ((_c = motion[selectedAgent.id]) === null || _c === void 0 ? void 0 : _c.mode) === 'visiting' ? 'VISITING ' + (((_d = motion[selectedAgent.id]) === null || _d === void 0 ? void 0 : _d.poi) || '').toUpperCase() :
                                            'RETURNING'))),
                    React.createElement("p", { className: "agent-summary" }, selectedAgent.summary),
                    React.createElement("div", { className: "agent-task" },
                        React.createElement("div", { className: "task-lbl" }, "CURRENT TASK"),
                        React.createElement("div", { className: "task-val" }, liveTask)),
                    React.createElement("div", { className: "agent-stats" },
                        React.createElement("div", { className: "stat" },
                            React.createElement("div", { className: "stat-val" }, 42 + (selectedAgent.name.length * 3) % 50),
                            React.createElement("div", { className: "stat-lbl" }, "tasks today")),
                        React.createElement("div", { className: "stat" },
                            React.createElement("div", { className: "stat-val" },
                                93 + (selectedAgent.name.length) % 6,
                                "%"),
                            React.createElement("div", { className: "stat-lbl" }, "success")),
                        React.createElement("div", { className: "stat" },
                            React.createElement("div", { className: "stat-val" },
                                120 + (selectedAgent.name.length * 11) % 80,
                                "ms"),
                            React.createElement("div", { className: "stat-lbl" }, "p50 latency"))),
                    React.createElement("div", { className: "agent-actions" },
                        React.createElement("button", { className: "btn btn-primary" }, "Open transcript"),
                        React.createElement("button", { className: "btn" }, "Pause"),
                        React.createElement("button", { className: "btn btn-danger" }, "Kill"))),
                React.createElement(TradingModePanel, null),
                React.createElement("div", { className: "roster" },
                    React.createElement("div", { className: "roster-hdr" },
                        "ROSTER \u00B7 ",
                        AGENTS.length,
                        " agents"),
                    React.createElement("div", { className: "roster-grid" }, AGENTS.map(a => {
                        var _a;
                        return (React.createElement("button", { key: a.id, className: `roster-cell ${a.id === selected ? 'sel' : ''}`, onClick: () => setSelected(a.id), style: { borderColor: a.id === selected ? a.color : "transparent" } },
                            React.createElement("div", { className: "rc-portrait" },
                                React.createElement(AgentPortrait, { agent: a, small: true })),
                            React.createElement("div", { className: "rc-meta" },
                                React.createElement("div", { className: "rc-name" }, a.name),
                                React.createElement("div", { className: "rc-layer", style: { color: a.color } },
                                    a.layer,
                                    " \u00B7 ",
                                    (((_a = motion[a.id]) === null || _a === void 0 ? void 0 : _a.mode) || 'at-desk')))));
                    }))))),
        React.createElement(TweaksPanel, { title: "Tweaks" },
            React.createElement(TweakSection, { title: "Display" },
                React.createElement(TweakRadio, { label: "Scale", value: String(tweaks.scale), options: [{ value: "2", label: "2×" }, { value: "3", label: "3×" }, { value: "4", label: "4×" }], onChange: (v) => setTweaks({ scale: Number(v) }) }),
                React.createElement(TweakToggle, { label: "Show labels", value: tweaks.showLabels, onChange: (v) => setTweaks({ showLabels: v }) }),
                React.createElement(TweakToggle, { label: "Show action arrows", value: tweaks.showActions, onChange: (v) => setTweaks({ showActions: v }) }),
                React.createElement(TweakToggle, { label: "POI floor markers", value: tweaks.showPoiMarkers, onChange: (v) => setTweaks({ showPoiMarkers: v }) })),
            React.createElement(TweakSection, { title: "Agent activity" },
                React.createElement(TweakToggle, { label: "Agents wander", value: tweaks.showMotion, onChange: (v) => setTweaks({ showMotion: v }) }),
                React.createElement(TweakSlider, { label: "Max away from desk", value: Number(tweaks.maxAway), min: 0, max: 6, step: 1, onChange: (v) => setTweaks({ maxAway: v }) }),
                React.createElement(TweakRadio, { label: "Mode", value: tweaks.mode, options: [{ value: "active", label: "Live" }, { value: "standby", label: "Stand-down" }], onChange: (v) => setTweaks({ mode: v }) })))));
}
function AgentPortrait({ agent, small }) {
    const ref = useRef(null);
    useEffect(() => {
        const c = ref.current;
        if (!c)
            return;
        const ctx = c.getContext("2d");
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, 16, 22);
        drawAgent(ctx, agent, 0, 0);
    }, [agent]);
    const px = small ? 3 : 5;
    return React.createElement("canvas", { ref: ref, width: 16, height: 22, style: { width: 16 * px, height: 22 * px, imageRendering: "pixelated" } });
}
ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(App, null));

})();
