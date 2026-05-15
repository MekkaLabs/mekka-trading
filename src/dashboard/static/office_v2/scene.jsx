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
    ctx.fillStyle = base; ctx.fillRect(0, y, SCENE_W, 1);
    if ((y - FLOOR_TOP) % 8 === 0) {
      ctx.fillStyle = dark; ctx.fillRect(0, y, SCENE_W, 1);
    }
  }
  ctx.fillStyle = "#3a2317";
  const seamCols = [40, 110, 180, 240, 310, 380, 440];
  for (let r = 0; r < 24; r++) {
    const y = FLOOR_TOP + r * 8;
    if (y >= SCENE_H) break;
    const off = (r * 13) % 70;
    for (const c of seamCols) ctx.fillRect(c + off, y, 1, 8);
  }
  // Center aisle rug (subtle, helps separate front/back zones)
  ctx.fillStyle = "rgba(20,30,55,0.25)";
  ctx.fillRect(0, 144, SCENE_W, 12);
}

// ---------- WALL ----------
function paintWall(ctx, frame) {
  ctx.fillStyle = "#0e1a2e"; ctx.fillRect(0, 0, SCENE_W, 92);
  ctx.fillStyle = "#152238";
  for (let x = 0; x < SCENE_W; x += 6) ctx.fillRect(x, 0, 1, 86);
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(0, 86, SCENE_W, 1);
  ctx.fillStyle = "#0a1424"; ctx.fillRect(0, 87, SCENE_W, 3);
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(0, 90, SCENE_W, 1);

  // Far-left whiteboard (replaces window)
  drawWhiteboard(ctx, 8, 18, 46, 46, frame);

  // Left small window
  function drawWindow(x, y, w, h) {
    ctx.fillStyle = "#1c2c44"; ctx.fillRect(x-1, y-1, w+2, h+2);
    ctx.fillStyle = "#3a5680"; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#5377a0"; ctx.fillRect(x, y+2, w, 1);
    ctx.fillStyle = "#7a9bc4"; ctx.fillRect(x, y+5, w, 1);
    ctx.fillStyle = "#0a1424";
    ctx.fillRect(x + Math.floor(w/2), y, 1, h);
    ctx.fillRect(x, y + Math.floor(h/2), w, 1);
    ctx.fillStyle = "#fbbf24";
    for (let i = 0; i < 8; i++) {
      const lx = x + 2 + ((i*7)%(w-4));
      const ly = y + 8 + (i%3)*4;
      if (ly < y + h - 1) ctx.fillRect(lx, ly, 1, 1);
    }
    ctx.fillStyle = "#2a3e5c";
    ctx.fillRect(x-2, y-2, w+4, 1);
    ctx.fillRect(x-2, y+h+1, w+4, 1);
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
  ctx.fillStyle = "#080d18"; ctx.fillRect(0, 88, SCENE_W, 2);
}

// ---------- DESK STATION ----------
function drawStation(ctx, x, y, opts = {}) {
  const screen = opts.screen || "#1e3a8a";
  const screenAccent = opts.accent || "#38bdf8";
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+10, y, 28, 22);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+12, y+2, 24, 18);
  ctx.fillStyle = screen; ctx.fillRect(x+13, y+3, 22, 16);
  ctx.fillStyle = screenAccent;
  for (let i = 0; i < 5; i++) {
    const bh = 3 + ((i + opts.seed) % 5) * 2;
    ctx.fillRect(x + 14 + i*4, y + 17 - bh, 3, bh);
  }
  if (opts.blink) {
    ctx.fillStyle = "#22c55e"; ctx.fillRect(x + 33, y + 5, 1, 2);
  }
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+22, y+22, 4, 3);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+18, y+25, 12, 2);
  ctx.fillStyle = "#3d2817"; ctx.fillRect(x, y+27, 48, 4);
  ctx.fillStyle = "#5a3826"; ctx.fillRect(x, y+27, 48, 1);
  ctx.fillStyle = "#251509"; ctx.fillRect(x, y+30, 48, 1);
  ctx.fillStyle = "#3d2817"; ctx.fillRect(x+1, y+31, 46, 14);
  ctx.fillStyle = "#251509"; ctx.fillRect(x+1, y+31, 46, 1);
  ctx.fillStyle = "#5a3826"; ctx.fillRect(x+1, y+32, 1, 12);
  ctx.fillStyle = "#1a0d05"; ctx.fillRect(x+46, y+32, 1, 12);
}

function drawMug(ctx, x, y, color = "#facc15") {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 6, 7);
  ctx.fillStyle = color; ctx.fillRect(x+1, y+1, 4, 5);
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+6, y+2, 1, 3);
  ctx.fillStyle = "#cbd5e1"; ctx.fillRect(x+2, y-2, 1, 1); ctx.fillRect(x+3, y-4, 1, 1);
}

function drawPlant(ctx, x, y) {
  ctx.fillStyle = "#15803d"; ctx.fillRect(x+2, y, 10, 2);
  ctx.fillStyle = "#22c55e"; ctx.fillRect(x, y+1, 14, 5);
  ctx.fillStyle = "#15803d"; ctx.fillRect(x+1, y+3, 12, 1);
  ctx.fillStyle = "#16a34a"; ctx.fillRect(x+3, y+2, 2, 2);
  ctx.fillStyle = "#16a34a"; ctx.fillRect(x+9, y+3, 2, 2);
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+4, y+6, 6, 1);
  ctx.fillStyle = "#7c2d12"; ctx.fillRect(x+4, y+7, 6, 4);
  ctx.fillStyle = "#451a09"; ctx.fillRect(x+4, y+10, 6, 1);
}

function drawServer(ctx, x, y, frame) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 22, 38);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+1, y+1, 20, 36);
  for (let i = 0; i < 5; i++) {
    const ry = y + 3 + i*7;
    ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+2, ry, 18, 5);
    ctx.fillStyle = ((frame + i*5) >> 2) % 4 < 3 ? "#fde047" : "#a16207";
    ctx.fillRect(x+3, ry+1, 1, 1);
    ctx.fillStyle = "#22c55e"; ctx.fillRect(x+5, ry+1, 1, 1);
    ctx.fillStyle = "#3a3a3a";
    for (let j = 0; j < 7; j++) ctx.fillRect(x+7+j*2, ry+2, 1, 2);
  }
}

// ---------- STATIONS ----------
// Row 1 (back wall, deskY~100): Layer-1 Market Analysis + Layer-2 Strategy + IronMan
// Row 2 (front, deskY~196): Layer-1 remaining + Layer-3 Risk/Execution + Layer-4 Command
const STATIONS = [
  // ── Row 1 — Market Analysis + Strategy ──────────────────────────────────
  { id:"superman",      deskX: 12,  deskY: 100, screen:"#1e40af", accent:"#fde047" },
  { id:"doctorstrange", deskX: 68,  deskY: 100, screen:"#7f1d1d", accent:"#fbbf24" },
  { id:"blackpanther",  deskX: 144, deskY: 100, screen:"#1a1a2e", accent:"#a78bfa" },
  { id:"thor",          deskX: 200, deskY: 100, screen:"#0e7490", accent:"#fde047" },
  { id:"flash",         deskX: 248, deskY: 100, screen:"#7f1d1d", accent:"#fbbf24" }, // L1.5 — Momentum
  { id:"vision",        deskX: 296, deskY: 100, screen:"#15803d", accent:"#fde047" },
  { id:"professorx",    deskX: 352, deskY: 100, screen:"#3f3f46", accent:"#a78bfa" },
  { id:"ironman",       deskX: 416, deskY: 100, screen:"#dc2626", accent:"#fde047" },

  // ── Row 2 — Risk / Execution / Analytics / Command ──────────────────────
  { id:"aquaman",       deskX: 18,  deskY: 196, screen:"#0e7490", accent:"#22c55e" },
  { id:"spiderman",     deskX: 78,  deskY: 196, screen:"#dc2626", accent:"#1e40af" },
  { id:"batman",        deskX: 138, deskY: 196, screen:"#1c1c1c", accent:"#fbbf24" },
  { id:"wolverine",     deskX: 198, deskY: 196, screen:"#1e40af", accent:"#fde047" }, // L3 — Recovery
  { id:"cyclops",       deskX: 258, deskY: 196, screen:"#1e40af", accent:"#dc2626" }, // L3 — Position Monitor
  { id:"deadpool",      deskX: 318, deskY: 196, screen:"#7f1d1d", accent:"#a78bfa" }, // L2 — Analytics
  { id:"portfolio",     deskX: 376, deskY: 196, screen:"#1e3a8a", accent:"#22c55e" },
  { id:"nickfury",      deskX: 432, deskY: 196, screen:"#0a0a0a", accent:"#dc2626" },
];

// 3x5 pixel tiny font — supports digits, +, -, %, .
const TINY_FONT = {
  "0":["111","101","101","101","111"],
  "1":["010","110","010","010","111"],
  "2":["111","001","111","100","111"],
  "3":["111","001","111","001","111"],
  "4":["101","101","111","001","001"],
  "5":["111","100","111","001","111"],
  "6":["111","100","111","101","111"],
  "7":["111","001","010","100","100"],
  "8":["111","101","111","101","111"],
  "9":["111","101","111","001","111"],
  "+":["000","010","111","010","000"],
  "-":["000","000","111","000","000"],
  "%":["101","001","010","100","101"],
  ".":["000","000","000","000","010"],
  " ":["000","000","000","000","000"],
};
function drawTinyChar(ctx, ch, x, y) {
  const g = TINY_FONT[ch] || TINY_FONT[" "];
  for (let r = 0; r < 5; r++) for (let c = 0; c < 3; c++) {
    if (g[r][c] === "1") ctx.fillRect(x + c, y + r, 1, 1);
  }
}

function agentPosFor(station) {
  if (station.deskY < 150) {
    return { x: station.deskX + 12, y: station.deskY - 6 };
  } else {
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
  drawCoffeeStation(ctx, 196, 142);   // matches POI 'coffee' (222,162)
  drawWaterCooler(ctx, 454, 138);     // matches POI 'cooler' (462,168)
  drawPrinter(ctx, 376, 152);         // matches POI 'printer'

  // Decorative plants
  drawPlant(ctx, 286, 113);
  drawPlant(ctx, 110, 209);
  drawPlant(ctx, 222, 209);
  drawFloorLamp(ctx, 446, 200, frame);
  drawTrash(ctx, 64, 230);
  drawTrash(ctx, 360, 230);

  // POI floor markers
  if (opts.showPoiMarkers !== false) {
    for (const p of POIS) drawPoiMarker(ctx, p.x, p.y + 4, "#38bdf8", frame);
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
      drawMug(ctx, s.deskX + 2, s.deskY + 22, ["#facc15","#dc2626","#22c55e","#38bdf8"][s.deskX % 4]);
    }
  }

  // Agents — sort by Y so closer agents draw on top
  const drawList = AGENTS.map(a => {
    const m = motion[a.id];
    const seated = m.mode === "at-desk";
    const pos = m.pos;
    return { agent: a, motion: m, pos, seated, y: pos.y };
  }).sort((a,b) => a.y - b.y);

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
