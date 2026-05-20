// Office scene composer — futuristic pixel-art trading floor with rooms.

const SCENE_W = 560;
const SCENE_H = 300;

// Room geometry: 4 rooms separated by glass partitions.
// X bands: L1 (0-180), L2+L3-back (184-360), L4 (364-560)
// Y bands: back row (96-176), front row (180-260)
const ROOMS = [
  { id: "L1", label: "L1 · ANALYSIS",   x: 4,   y: 92,  w: 178, h: 200, color: "#38bdf8" },
  { id: "L2", label: "L2 · STRATEGY",   x: 186, y: 92,  w: 174, h: 96,  color: "#a78bfa" },
  { id: "L3", label: "L3 · RISK/EXEC",  x: 186, y: 192, w: 174, h: 100, color: "#fb923c" },
  { id: "L4", label: "L4 · COMMAND",    x: 364, y: 92,  w: 192, h: 200, color: "#22c55e" },
];

// ---------- FLOOR ----------
function paintFloor(ctx, frame) {
  // Dark futuristic tile floor — 16x16 tiles with neon seams per zone
  for (let y = 92; y < SCENE_H; y += 16) {
    for (let x = 0; x < SCENE_W; x += 16) {
      ctx.fillStyle = (x + y) % 32 === 0 ? "#101824" : "#0c1320";
      ctx.fillRect(x, y, 16, 16);
      // subtle scanline
      ctx.fillStyle = "#0a1018";
      ctx.fillRect(x, y + 15, 16, 1);
      ctx.fillRect(x + 15, y, 1, 16);
    }
  }
  // Zone tint per room
  for (const r of ROOMS) {
    ctx.globalAlpha = 0.07;
    ctx.fillStyle = r.color;
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.globalAlpha = 1;
  }
  // Neon perimeter strip glow along zone edges
  for (const r of ROOMS) {
    ctx.fillStyle = r.color;
    ctx.globalAlpha = 0.7;
    ctx.fillRect(r.x, r.y + r.h - 2, r.w, 1);
    ctx.globalAlpha = 0.3;
    ctx.fillRect(r.x, r.y + r.h - 3, r.w, 1);
    ctx.globalAlpha = 1;
  }
  // Walkway central rug (subtle blue strip)
  ctx.fillStyle = "rgba(56,189,248,0.08)";
  ctx.fillRect(0, 178, SCENE_W, 4);
  // Moving accent — small pulse traveling along the walkway
  const pulseX = (frame * 4) % (SCENE_W + 40) - 20;
  ctx.fillStyle = "rgba(56,189,248,0.6)";
  ctx.fillRect(pulseX, 178, 16, 4);
}

// ---------- WALL ----------
function paintWall(ctx, frame) {
  ctx.fillStyle = "#070d1a"; ctx.fillRect(0, 0, SCENE_W, 92);
  // Vertical light columns
  ctx.fillStyle = "#0e1a30";
  for (let x = 0; x < SCENE_W; x += 8) ctx.fillRect(x, 0, 1, 86);
  // Ceiling LED strip — horizontal cyan glow line
  ctx.fillStyle = "#22d3ee"; ctx.fillRect(0, 2, SCENE_W, 1);
  ctx.fillStyle = "rgba(34,211,238,0.4)";
  ctx.fillRect(0, 0, SCENE_W, 2);
  ctx.fillRect(0, 3, SCENE_W, 2);
  // Traveling LED pulse
  const ledX = (frame * 6) % (SCENE_W + 60) - 30;
  ctx.fillStyle = "#ecfeff";
  ctx.fillRect(ledX, 2, 30, 1);

  // Wall trim line at bottom of wall
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(0, 84, SCENE_W, 1);
  ctx.fillStyle = "#22d3ee"; ctx.globalAlpha = 0.5; ctx.fillRect(0, 85, SCENE_W, 1); ctx.globalAlpha = 1;
  ctx.fillStyle = "#0a1424"; ctx.fillRect(0, 86, SCENE_W, 4);
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(0, 90, SCENE_W, 1);

  // Whiteboard
  drawWhiteboard(ctx, 8, 18, 46, 46, frame);

  // Window with cityscape
  function drawWindow(x, y, w, h) {
    ctx.fillStyle = "#1c2c44"; ctx.fillRect(x-1, y-1, w+2, h+2);
    ctx.fillStyle = "#1e3a5f"; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = "#2a4870"; ctx.fillRect(x, y+2, w, 1);
    ctx.fillStyle = "#3a5680"; ctx.fillRect(x, y+5, w, 1);
    // city skyline
    ctx.fillStyle = "#0a1424";
    const sky = [10, 6, 14, 8, 12, 16, 6, 10, 14, 8];
    let cx = x;
    for (const s of sky) {
      if (cx + 3 > x + w) break;
      ctx.fillRect(cx, y + h - s, 3, s);
      cx += 3;
    }
    ctx.fillStyle = "#fbbf24";
    for (let i = 0; i < 14; i++) {
      const lx = x + 1 + ((i*5)%(w-2));
      const ly = y + h - 4 - (i%3)*2;
      ctx.fillRect(lx, ly, 1, 1);
    }
    // mullions
    ctx.fillStyle = "#0a1424";
    ctx.fillRect(x + Math.floor(w/2), y, 1, h);
    ctx.fillStyle = "#22d3ee"; ctx.globalAlpha = 0.5;
    ctx.fillRect(x + Math.floor(w/2), y, 1, h);
    ctx.globalAlpha = 1;
    ctx.fillRect(x, y + Math.floor(h/2), w, 1);
  }
  drawWindow(64, 22, 30, 40);

  // Big wall monitor
  drawWallMonitor(ctx, 102, 14, 188, 56, frame);

  // Right window
  drawWindow(298, 22, 30, 40);

  // Posters / clock
  drawPoster(ctx, 336, 18, 18, 22, { bg: "#7f1d1d", style: "M" });
  drawPoster(ctx, 360, 18, 22, 22, { bg: "#0e7490", style: "chart" });
  drawWallClock(ctx, 392, 22, frame);
  drawPoster(ctx, 414, 18, 22, 22, { bg: "#1e3a8a", style: "agent" });
  drawPoster(ctx, 442, 18, 26, 22, { bg: "#15803d", style: "chart" });
  // Holographic ticker on far right wall
  drawHoloTicker(ctx, 476, 18, 80, 26, frame);
  // Server bank below ticker
  drawWallServers(ctx, 476, 50, 80, 32, frame);

  // Floor-line shadow
  ctx.fillStyle = "#040a16"; ctx.fillRect(0, 88, SCENE_W, 2);
}

// ---------- HOLOGRAPHIC TICKER ----------
function drawHoloTicker(ctx, x, y, w, h, frame) {
  // Frame
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#22d3ee"; ctx.fillRect(x, y, w, 1);
  ctx.fillStyle = "rgba(34,211,238,0.4)";
  ctx.fillRect(x, y - 1, w, 1);
  ctx.fillRect(x, y + h, w, 1);
  // Holographic price feed — scrolling bars
  for (let i = 0; i < 4; i++) {
    const row = y + 4 + i * 6;
    const offset = (frame * 2 + i * 17) % 20;
    ctx.fillStyle = i % 2 ? "#22c55e" : "#ef4444";
    for (let j = 0; j < 8; j++) {
      const bx = x + 4 + j * 9 + offset;
      if (bx < x + w - 5) ctx.fillRect(bx, row, 5, 1);
    }
  }
  // Glow
  ctx.fillStyle = "rgba(34,211,238,0.12)";
  ctx.fillRect(x, y, w, h);
}

// ---------- WALL SERVERS (back-wall mini rack) ----------
function drawWallServers(ctx, x, y, w, h, frame) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+1, y+1, w-2, h-2);
  for (let i = 0; i < 4; i++) {
    const ry = y + 3 + i * 7;
    ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+2, ry, w-4, 5);
    ctx.fillStyle = ((frame + i*3) >> 1) % 5 ? "#22c55e" : "#a3e635";
    ctx.fillRect(x+3, ry+1, 1, 1);
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x+5, ry+1, 1, 1);
    ctx.fillStyle = "#3a3a3a";
    for (let j = 0; j < Math.floor((w-12)/2); j++) ctx.fillRect(x+7+j*2, ry+2, 1, 2);
  }
}

// ---------- ROOM PARTITIONS ----------
// Vertical glass walls separating rooms. Translucent base + neon top trim.
function drawPartitions(ctx, frame) {
  // Vertical between L1 and L2/L3 (x=182)
  drawGlassWall(ctx, 182, 92, 4, 200, "#a78bfa");
  // Vertical between L2/L3 and L4 (x=360)
  drawGlassWall(ctx, 360, 92, 4, 200, "#22c55e");
  // Horizontal between L2 and L3 inside middle column (y=188)
  drawGlassWall(ctx, 186, 188, 174, 4, "#fb923c", true);
  // Door gaps — break the walls in two places so agents can walk through
  // We "draw" door gaps by erasing chunks of the wall and adding a glowing arch
  drawDoor(ctx, 182, 240, 8, 32, "#a78bfa", frame);  // L1 ↔ L3
  drawDoor(ctx, 360, 240, 8, 32, "#22c55e", frame);  // L3 ↔ L4
  drawDoor(ctx, 182, 130, 8, 28, "#a78bfa", frame);  // L1 ↔ L2
  drawDoor(ctx, 360, 130, 8, 28, "#22c55e", frame);  // L2 ↔ L4
  // Horizontal door between L2 and L3
  drawDoor(ctx, 264, 188, 28, 8, "#fb923c", frame, true);
}

function drawGlassWall(ctx, x, y, w, h, neon, horizontal = false) {
  // Faint glass interior
  ctx.fillStyle = "rgba(170,200,230,0.07)"; ctx.fillRect(x, y, w, h);
  // Outer frame
  ctx.fillStyle = "#0a1424"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#1c2c44";
  if (horizontal) {
    ctx.fillRect(x, y + 1, w, 1);
    ctx.fillRect(x, y + 2, w, 1);
  } else {
    ctx.fillRect(x + 1, y, 1, h);
    ctx.fillRect(x + 2, y, 1, h);
  }
  // Neon top trim (or side trim)
  ctx.fillStyle = neon;
  if (horizontal) ctx.fillRect(x, y, w, 1);
  else ctx.fillRect(x, y, w, 2);
  // Glow underneath neon
  ctx.globalAlpha = 0.3;
  if (horizontal) ctx.fillRect(x, y + 1, w, 1);
  else ctx.fillRect(x, y + 2, w, 1);
  ctx.globalAlpha = 1;
  // Glass shine vertical lines (only on vertical walls)
  if (!horizontal) {
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    ctx.fillRect(x + 1, y + 8, 1, h - 16);
  }
}

function drawDoor(ctx, x, y, w, h, neon, frame, horizontal = false) {
  // Erase a chunk by re-painting the floor pattern
  for (let yy = y; yy < y + h; yy++) {
    for (let xx = x; xx < x + w; xx++) {
      ctx.fillStyle = (xx + yy) % 32 === 0 ? "#101824" : "#0c1320";
      ctx.fillRect(xx, yy, 1, 1);
    }
  }
  // Door arch — top horizontal neon bar
  ctx.fillStyle = neon;
  if (horizontal) {
    ctx.fillRect(x, y - 1, w, 1);
    ctx.fillRect(x, y + h, w, 1);
    // pulsing center
    const pulse = (frame >> 2) % 4 < 2 ? 0.9 : 0.4;
    ctx.globalAlpha = pulse;
    ctx.fillRect(x + 4, y + 2, w - 8, h - 4);
    ctx.globalAlpha = 1;
  } else {
    ctx.fillRect(x, y, w, 1);
    ctx.fillRect(x, y + h - 1, w, 1);
    const pulse = (frame >> 2) % 4 < 2 ? 0.5 : 0.15;
    ctx.globalAlpha = pulse;
    ctx.fillRect(x + 2, y + 1, w - 4, h - 2);
    ctx.globalAlpha = 1;
  }
}

// ---------- HOLOGRAPHIC ROOM LABELS ----------
function drawRoomLabels(ctx, frame) {
  for (const r of ROOMS) {
    // Find a non-obstructing spot near the top of each room
    const labelY = r.id === "L3" ? r.y + 4 : r.y + 4;
    const cx = r.x + Math.floor(r.w / 2);
    drawHoloLabel(ctx, cx, labelY, r.label, r.color, frame);
  }
}

function drawHoloLabel(ctx, cx, y, text, color, frame) {
  const w = text.length * 5 + 8;
  const x = cx - Math.floor(w / 2);
  const h = 9;
  // Backing
  ctx.fillStyle = "rgba(5,11,24,0.85)"; ctx.fillRect(x, y, w, h);
  // Neon border
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, 1);
  ctx.fillRect(x, y + h - 1, w, 1);
  ctx.fillRect(x, y, 1, h);
  ctx.fillRect(x + w - 1, y, 1, h);
  // Scanline shimmer
  const sy = y + 1 + ((frame >> 2) % (h - 2));
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  ctx.fillRect(x + 1, sy, w - 2, 1);
  // Text using TINY_FONT5 (5-pixel letter font, supports A-Z, 0-9, space, ., ·)
  let cursor = x + 4;
  for (const ch of text) {
    const g = LABEL_FONT[ch] || LABEL_FONT[" "];
    for (let r = 0; r < 5; r++) for (let c = 0; c < 4; c++) {
      if (g[r][c] === "1") {
        ctx.fillStyle = color;
        ctx.fillRect(cursor + c, y + 2 + r, 1, 1);
      }
    }
    cursor += 5;
  }
}

// 4x5 pixel font for A-Z, 0-9, ., space, ·, slash
const LABEL_FONT = {
  "A":["0110","1001","1111","1001","1001"],
  "B":["1110","1001","1110","1001","1110"],
  "C":["0111","1000","1000","1000","0111"],
  "D":["1110","1001","1001","1001","1110"],
  "E":["1111","1000","1110","1000","1111"],
  "F":["1111","1000","1110","1000","1000"],
  "G":["0111","1000","1011","1001","0111"],
  "H":["1001","1001","1111","1001","1001"],
  "I":["0111","0010","0010","0010","0111"],
  "J":["0001","0001","0001","1001","0110"],
  "K":["1001","1010","1100","1010","1001"],
  "L":["1000","1000","1000","1000","1111"],
  "M":["1001","1111","1111","1001","1001"],
  "N":["1001","1101","1011","1001","1001"],
  "O":["0110","1001","1001","1001","0110"],
  "P":["1110","1001","1110","1000","1000"],
  "Q":["0110","1001","1001","1011","0111"],
  "R":["1110","1001","1110","1010","1001"],
  "S":["0111","1000","0110","0001","1110"],
  "T":["1111","0010","0010","0010","0010"],
  "U":["1001","1001","1001","1001","0110"],
  "V":["1001","1001","1001","0110","0110"],
  "W":["1001","1001","1111","1111","1001"],
  "X":["1001","1001","0110","1001","1001"],
  "Y":["1001","1001","0110","0010","0010"],
  "Z":["1111","0001","0110","1000","1111"],
  "0":["0110","1001","1001","1001","0110"],
  "1":["0010","0110","0010","0010","0111"],
  "2":["0110","1001","0010","0100","1111"],
  "3":["1110","0001","0110","0001","1110"],
  "4":["1010","1010","1111","0010","0010"],
  "5":["1111","1000","1110","0001","1110"],
  "6":["0110","1000","1110","1001","0110"],
  "7":["1111","0001","0010","0100","0100"],
  "8":["0110","1001","0110","1001","0110"],
  "9":["0110","1001","0111","0001","0110"],
  ".":["0000","0000","0000","0000","0010"],
  " ":["0000","0000","0000","0000","0000"],
  "·":["0000","0000","0110","0000","0000"],
  "/":["0001","0010","0010","0100","0100"],
};

// ---------- DESK STATION (futuristic with underglow) ----------
function drawStation(ctx, x, y, opts = {}) {
  const screen = opts.screen || "#1e3a8a";
  const screenAccent = opts.accent || "#38bdf8";
  const accent = opts.deskAccent || "#22d3ee";
  // Monitor (sleeker — thinner bezel + glass top)
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+10, y, 28, 22);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+11, y+1, 26, 20);
  ctx.fillStyle = screen; ctx.fillRect(x+12, y+2, 24, 18);
  ctx.fillStyle = screenAccent;
  for (let i = 0; i < 6; i++) {
    const bh = 3 + ((i + opts.seed) % 5) * 2;
    ctx.fillRect(x + 13 + i*4, y + 18 - bh, 3, bh);
  }
  // tiny scanlines
  ctx.fillStyle = "rgba(255,255,255,0.04)";
  for (let i = 0; i < 18; i += 2) ctx.fillRect(x+12, y+2+i, 24, 1);
  if (opts.blink) {
    ctx.fillStyle = "#22c55e"; ctx.fillRect(x + 34, y + 4, 1, 2);
  }
  // Stand
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+22, y+22, 4, 3);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+18, y+25, 12, 2);
  // Glass + metal desk top
  ctx.fillStyle = "#1a2332"; ctx.fillRect(x, y+27, 48, 4);
  ctx.fillStyle = "#2a3a52"; ctx.fillRect(x, y+27, 48, 1);
  ctx.fillStyle = "#0a1018"; ctx.fillRect(x, y+30, 48, 1);
  // Front panel
  ctx.fillStyle = "#0e1626"; ctx.fillRect(x+1, y+31, 46, 14);
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(x+1, y+31, 46, 1);
  // NEON UNDERGLOW
  ctx.fillStyle = accent;
  ctx.fillRect(x+2, y+44, 44, 1);
  ctx.globalAlpha = 0.4;
  ctx.fillRect(x+2, y+45, 44, 1);
  ctx.globalAlpha = 0.2;
  ctx.fillRect(x+1, y+46, 46, 1);
  ctx.globalAlpha = 1;
  // small vertical accent bars on desk front
  ctx.fillStyle = accent;
  ctx.fillRect(x+4, y+33, 1, 8);
  ctx.fillRect(x+43, y+33, 1, 8);
  // Desk side caps
  ctx.fillStyle = "#2a3a52"; ctx.fillRect(x+1, y+32, 1, 12);
  ctx.fillStyle = "#070a14"; ctx.fillRect(x+46, y+32, 1, 12);
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
  // neon side trim
  ctx.fillStyle = "#22d3ee";
  ctx.fillRect(x - 1, y + 2, 1, 34);
  ctx.fillRect(x + 22, y + 2, 1, 34);
}

// ---------- STATIONS (24 desks across 4 rooms) ----------
// Room L1 (Analysis): 8 desks, back + mid + front rows
// Room L2 (Strategy): 3 desks, back
// Room L3 (Risk/Exec): 5 desks, two rows
// Room L4 (Command): 8 desks, three rows — Nick Fury + data stations +
//   the Improvement Council (Mekka, Galactus, Beast, Jean Grey)
const STATIONS = [
  // ---- L1 ANALYSIS (back row left)
  { id:"superman",      deskX: 8,   deskY: 104, screen:"#1e40af", accent:"#fde047", deskAccent:"#38bdf8" },
  { id:"doctorstrange", deskX: 60,  deskY: 104, screen:"#7f1d1d", accent:"#fbbf24", deskAccent:"#38bdf8" },
  { id:"blackpanther",  deskX: 112, deskY: 104, screen:"#1a1a2e", accent:"#a78bfa", deskAccent:"#38bdf8" },
  // ---- L1 ANALYSIS (front row)
  { id:"thor",          deskX: 8,   deskY: 208, screen:"#0e7490", accent:"#fde047", deskAccent:"#38bdf8" },
  { id:"aquaman",       deskX: 60,  deskY: 208, screen:"#0e7490", accent:"#22c55e", deskAccent:"#38bdf8" },
  { id:"spiderman",     deskX: 112, deskY: 208, screen:"#dc2626", accent:"#1e40af", deskAccent:"#38bdf8" },
  // hawkeye optional — in L1 if exists
  { id:"hawkeye",       deskX: 8,   deskY: 152, screen:"#5b21b6", accent:"#fde047", deskAccent:"#38bdf8" },
  { id:"flash",         deskX: 112, deskY: 152, screen:"#dc2626", accent:"#facc15", deskAccent:"#38bdf8" },
  // ---- L2 STRATEGY (middle back, 3 desks)
  { id:"vision",        deskX: 194, deskY: 116, screen:"#15803d", accent:"#fde047", deskAccent:"#a78bfa" },
  { id:"professorx",    deskX: 246, deskY: 116, screen:"#3f3f46", accent:"#a78bfa", deskAccent:"#a78bfa" },
  { id:"deadpool",      deskX: 298, deskY: 116, screen:"#7f1d1d", accent:"#facc15", deskAccent:"#a78bfa" },
  // ---- L3 RISK/EXEC (middle front, 4 desks)
  { id:"ironman",       deskX: 194, deskY: 220, screen:"#dc2626", accent:"#fde047", deskAccent:"#fb923c" },
  { id:"batman",        deskX: 246, deskY: 220, screen:"#1c1c1c", accent:"#fbbf24", deskAccent:"#fb923c" },
  { id:"wolverine",     deskX: 298, deskY: 220, screen:"#1e40af", accent:"#fde047", deskAccent:"#fb923c" },
  { id:"cyclops",       deskX: 194, deskY: 256, screen:"#1e40af", accent:"#ef4444", deskAccent:"#fb923c" },
  { id:"hulk",          deskX: 298, deskY: 256, screen:"#15803d", accent:"#fde047", deskAccent:"#fb923c" },
  // ---- L4 COMMAND (right, 8 desks across 3 rows)
  // back row — orchestration + data stations
  { id:"nickfury",      deskX: 372, deskY: 116, screen:"#0a0a0a", accent:"#dc2626", deskAccent:"#22c55e" },
  { id:"portfolio",     deskX: 432, deskY: 116, screen:"#1e3a8a", accent:"#22c55e", deskAccent:"#22c55e" },
  { id:"dailypnl",      deskX: 492, deskY: 116, screen:"#7c2d12", accent:"#fbbf24", deskAccent:"#22c55e" },
  // mid row — Improvement Council (Mekka commands, Galactus premortem, Beast proposes)
  { id:"mekka",         deskX: 372, deskY: 168, screen:"#14532d", accent:"#a3e635", deskAccent:"#22c55e" },
  { id:"galactus",      deskX: 432, deskY: 168, screen:"#4c1d95", accent:"#c084fc", deskAccent:"#22c55e" },
  { id:"beast",         deskX: 492, deskY: 168, screen:"#1e3a8a", accent:"#60a5fa", deskAccent:"#22c55e" },
  // front row — memory + night ops
  { id:"jeangrey",      deskX: 372, deskY: 224, screen:"#7f1d1d", accent:"#fb923c", deskAccent:"#22c55e" },
  { id:"nighttrader",   deskX: 432, deskY: 224, screen:"#0a0a14", accent:"#a78bfa", deskAccent:"#22c55e" },
];

// Wheelchair agents render with a chair instead of legs.
const WHEELCHAIR_IDS = new Set(["professorx"]);

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
  // Two rows + a mid row are possible now. We treat any station y < 200 as
  // "back" (agent stands behind desk, head above monitor) and y >= 200 as
  // "front" (agent in front of desk).
  if (station.deskY < 200) {
    return { x: station.deskX + 12, y: station.deskY - 6 };
  } else {
    return { x: station.deskX + 12, y: station.deskY + 6 };
  }
}

// ---------- SCENE PAINTER ----------
function paintScene(ctx, frame, agents, motion, powerState, opts = {}) {
  // Clear
  ctx.fillStyle = "#050b18"; ctx.fillRect(0, 0, SCENE_W, SCENE_H);

  paintWall(ctx, frame);
  paintFloor(ctx, frame);
  drawPartitions(ctx, frame);

  // L1 server rack (corner)
  drawServer(ctx, 156, 96, frame);
  // L4 server rack (corner) — futuristic dual rack
  drawServer(ctx, 537, 96, frame);

  // Mid-aisle furniture — coffee station near L1/L2 door, cooler near L4/L3 door
  drawCoffeeStation(ctx, 30, 178);
  drawWaterCooler(ctx, 540, 200);
  drawPrinter(ctx, 372, 184);

  // Decorative
  drawFloorLamp(ctx, 538, 252, frame);
  drawTrash(ctx, 165, 270);
  drawTrash(ctx, 370, 270);
  drawPlant(ctx, 158, 248);
  drawPlant(ctx, 368, 248);

  // POI floor markers
  if (opts.showPoiMarkers !== false) {
    for (const p of POIS) drawPoiMarker(ctx, p.x, p.y + 4, "#38bdf8", frame);
  }

  // Desks (with optional trade-close flash overlay)
  const flashes = opts.flashes || {};
  for (const s of STATIONS) {
    const blink = ((frame + s.deskX) % 60) < 4;
    const flash = flashes[s.id];
    drawStation(ctx, s.deskX, s.deskY, {
      screen: s.screen, accent: s.accent, deskAccent: s.deskAccent,
      seed: s.deskX, blink
    });
    if (flash && flash.intensity > 0) {
      ctx.globalAlpha = Math.min(1, flash.intensity);
      ctx.fillStyle = flash.color;
      ctx.fillRect(s.deskX + 12, s.deskY + 2, 24, 18);
      ctx.globalAlpha = Math.min(0.6, flash.intensity * 0.6);
      ctx.fillRect(s.deskX + 10, s.deskY, 28, 22);
      ctx.globalAlpha = 1;
      if (flash.intensity > 0.5 && flash.label) {
        ctx.fillStyle = "#0a0a0a";
        ctx.fillRect(s.deskX + 8, s.deskY - 8, flash.label.length * 4 + 4, 7);
        ctx.fillStyle = flash.color;
        for (let i = 0; i < flash.label.length; i++) {
          drawTinyChar(ctx, flash.label[i], s.deskX + 10 + i * 4, s.deskY - 7);
        }
      }
    }
    if ((s.deskX % 7) === 0 || s.deskY > 180) {
      drawMug(ctx, s.deskX + 2, s.deskY + 22, ["#facc15","#dc2626","#22c55e","#38bdf8"][s.deskX % 4]);
    }
  }

  // Holographic room labels (over the scene, just below ceiling)
  drawRoomLabels(ctx, frame);

  // Agents — sort by Y so closer agents draw on top
  const drawList = AGENTS.map(a => {
    const m = motion[a.id]; if (!m) return null;
    const seated = m.mode === "at-desk";
    let pos = { x: m.pos.x, y: m.pos.y };
    // Apply power-driven y lift (e.g. flying)
    const lift = (powerState && typeof getPowerLift === 'function') ? getPowerLift(a.id, powerState, frame) : 0;
    pos.y += lift;
    return { agent: a, motion: m, pos, seated, lift, y: pos.y };
  }).filter(Boolean).sort((a,b) => a.y - b.y);

  for (const item of drawList) {
    const { agent, motion: m, pos, seated, lift } = item;
    const wheelchair = WHEELCHAIR_IDS.has(agent.id);
    const bob = seated
      ? (Math.sin((frame + agent.name.length) / 18) > 0.7 ? 1 : 0)
      : ((frame >> 1) % 2);
    const flip = !seated && m.dir < 0;
    const legFrame = !seated ? ((frame >> 2) % 2) : 0;
    drawAgent(ctx, agent, Math.round(pos.x), Math.round(pos.y), {
      bob, flip, walking: !seated, legFrame, bubble: m.bubble,
      wheelchair, frame,
    });
    // Lift wind-streaks under the floating agent
    if (lift < -2) {
      ctx.fillStyle = "rgba(56,189,248,0.5)";
      ctx.fillRect(Math.round(pos.x) + 4, Math.round(pos.y) + 22 - lift, 8, 1);
      ctx.fillStyle = "rgba(56,189,248,0.25)";
      ctx.fillRect(Math.round(pos.x) + 2, Math.round(pos.y) + 23 - lift, 12, 1);
    }
    // Power effect overlay
    if (powerState && typeof drawPower === 'function') {
      drawPower(ctx, agent.id, Math.round(pos.x), Math.round(pos.y), powerState, frame);
    }
  }

  // Optional: floor shadow under each agent (subtle)
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  for (const item of drawList) {
    if (!item.seated) {
      const sx = Math.round(item.motion.pos.x);
      const sy = Math.round(item.motion.pos.y);
      ctx.fillRect(sx + 4, sy + 22, 8, 1);
    }
  }
}

Object.assign(window, { SCENE_W, SCENE_H, STATIONS, ROOMS, paintScene, agentPosFor, WHEELCHAIR_IDS });
