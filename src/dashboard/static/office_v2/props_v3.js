// Office decorations and props. Each function paints into the low-res canvas.
// Frame-driven animations: wall monitor charts, clock hands, coffee steam.

// ---------- BIG WALL MONITOR ----------
// Wide TV showing a live candlestick chart. Center of the back wall.
function drawWallMonitor(ctx, x, y, w, h, frame) {
  // bezel
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+2, y+2, w-4, h-4);
  // screen background — deep navy with grid
  ctx.fillStyle = "#0a1424"; ctx.fillRect(x+3, y+3, w-6, h-6);
  ctx.fillStyle = "#152238";
  for (let gx = x+3; gx < x+w-3; gx += 8) ctx.fillRect(gx, y+3, 1, h-6);
  for (let gy = y+3; gy < y+h-3; gy += 6) ctx.fillRect(x+3, gy, w-6, 1);
  // axis line at bottom
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(x+4, y+h-6, w-8, 1);
  // candles — 22 candles, scrolling
  const N = 22;
  const cw = Math.floor((w - 12) / N);
  for (let i = 0; i < N; i++) {
    const seed = (frame >> 2) + i;
    const o = ((seed * 17) % 11) - 5;
    const c = ((seed * 23) % 11) - 5;
    const high = Math.max(o, c) + ((seed * 7) % 4);
    const low = Math.min(o, c) - ((seed * 5) % 3);
    const mid = y + Math.floor(h/2);
    const cx = x + 6 + i * cw;
    const up = c >= o;
    const col = up ? "#22c55e" : "#ef4444";
    // wick
    ctx.fillStyle = col;
    ctx.fillRect(cx + Math.floor(cw/2), mid - high, 1, (high - low) || 1);
    // body
    const top = mid - Math.max(o, c);
    const bh = Math.max(1, Math.abs(c - o));
    ctx.fillRect(cx + 1, top, cw - 2, bh);
  }
  // ticker text bar at top
  ctx.fillStyle = "#0a1424"; ctx.fillRect(x+3, y+3, w-6, 7);
  ctx.fillStyle = "#fb923c"; ctx.fillRect(x+5, y+5, 2, 2);
  ctx.fillStyle = "#cfd9ec";
  // pretend "MEKKA" letters as 1x3 bars
  for (let i = 0; i < 18; i++) {
    if (((frame + i) >> 1) % 7 < 5) ctx.fillRect(x + 10 + i*3, y+6, 1, 3);
  }
  // recording dot
  if ((frame >> 2) % 2 === 0) {
    ctx.fillStyle = "#ef4444";
    ctx.fillRect(x + w - 8, y + 5, 2, 2);
  }
  // outer frame highlight
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x, y, 1, h);
  ctx.fillStyle = "#000000"; ctx.fillRect(x+w-1, y, 1, h);
}

// ---------- WHITEBOARD ----------
function drawWhiteboard(ctx, x, y, w, h, frame) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x+1, y+1, w-2, h-2);
  ctx.fillStyle = "#e8eef9"; ctx.fillRect(x+2, y+2, w-4, h-4);
  // doodle: arrow + boxes
  ctx.fillStyle = "#1c1c1c";
  // box 1
  ctx.fillRect(x+5, y+6, 12, 8);
  ctx.fillStyle = "#e8eef9"; ctx.fillRect(x+6, y+7, 10, 6);
  ctx.fillStyle = "#1e40af"; ctx.fillRect(x+7, y+9, 8, 2);
  // arrow →
  ctx.fillStyle = "#dc2626";
  ctx.fillRect(x+18, y+9, 6, 1);
  ctx.fillRect(x+22, y+8, 1, 3);
  ctx.fillRect(x+23, y+9, 1, 1);
  // box 2
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+25, y+6, 12, 8);
  ctx.fillStyle = "#e8eef9"; ctx.fillRect(x+26, y+7, 10, 6);
  ctx.fillStyle = "#15803d"; ctx.fillRect(x+27, y+9, 8, 2);
  // line chart
  ctx.fillStyle = "#fb923c";
  const xs = [4, 8, 12, 16, 20, 24, 28, 32, 36, 40];
  const ys_off = (frame >> 2) % 4;
  for (let i = 0; i < xs.length-1; i++) {
    const yA = y + 26 + ((i + ys_off) % 5);
    const yB = y + 26 + ((i + 1 + ys_off) % 5);
    ctx.fillRect(x + xs[i], yA, xs[i+1]-xs[i], 1);
    if (yB !== yA) ctx.fillRect(x + xs[i+1], Math.min(yA,yB), 1, Math.abs(yB-yA)+1);
  }
  // marker tray
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+1, y+h-3, w-2, 2);
  ctx.fillStyle = "#dc2626"; ctx.fillRect(x+4, y+h-2, 5, 1);
  ctx.fillStyle = "#1e40af"; ctx.fillRect(x+12, y+h-2, 5, 1);
  ctx.fillStyle = "#15803d"; ctx.fillRect(x+20, y+h-2, 5, 1);
}

// ---------- COFFEE STATION ----------
function drawCoffeeStation(ctx, x, y, frame) {
  // Counter (60w x 12h)
  ctx.fillStyle = "#3d2817"; ctx.fillRect(x, y+12, 60, 14);
  ctx.fillStyle = "#5a3826"; ctx.fillRect(x, y+12, 60, 1);
  ctx.fillStyle = "#251509"; ctx.fillRect(x, y+25, 60, 1);
  ctx.fillStyle = "#1a0d05"; ctx.fillRect(x+58, y+12, 1, 14);
  // Backsplash
  ctx.fillStyle = "#2a3e5c"; ctx.fillRect(x, y, 60, 12);
  ctx.fillStyle = "#1c2c44"; ctx.fillRect(x, y, 60, 1);
  // tile pattern
  ctx.fillStyle = "#3a5680";
  for (let tx = x; tx < x+60; tx += 6)
    for (let ty = y+1; ty < y+11; ty += 4)
      ctx.fillRect(tx + ((ty/4)%2)*3, ty, 1, 1);

  // Coffee machine (16w x 20h)
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+4, y-8, 18, 20);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+5, y-7, 16, 18);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+6, y-6, 14, 4); // top vents
  // display (animated)
  ctx.fillStyle = "#22c55e";
  if ((frame >> 2) % 2 === 0) ctx.fillRect(x+8, y-1, 10, 2);
  // spout
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+11, y+5, 4, 3);
  // dripping coffee
  if ((frame >> 1) % 8 < 3) {
    ctx.fillStyle = "#7c2d12";
    ctx.fillRect(x+12, y+8, 2, 2);
  }
  // cup beneath
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+11, y+10, 4, 4);
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x+12, y+11, 2, 2);
  ctx.fillStyle = "#7c2d12"; ctx.fillRect(x+12, y+11, 2, 1);
  // steam
  if ((frame >> 1) % 4 < 2) {
    ctx.fillStyle = "#cbd5e1";
    ctx.fillRect(x+12, y-10, 1, 1);
    ctx.fillRect(x+13, y-12, 1, 1);
    ctx.fillRect(x+11, y-13, 1, 1);
  }

  // Mugs lined up on counter
  for (let i = 0; i < 4; i++) {
    const mx = x + 28 + i*7;
    ctx.fillStyle = "#0a0a0a"; ctx.fillRect(mx, y+8, 5, 4);
    ctx.fillStyle = ["#dc2626","#fde047","#22c55e","#38bdf8"][i];
    ctx.fillRect(mx+1, y+9, 3, 2);
  }

  // Sugar/cream jars
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+52, y+6, 4, 6);
  ctx.fillStyle = "#fde047"; ctx.fillRect(x+53, y+7, 2, 4);
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+47, y+6, 4, 6);
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x+48, y+7, 2, 4);
}

// ---------- WATER COOLER ----------
function drawWaterCooler(ctx, x, y, frame) {
  // bottle on top
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+2, y, 10, 14);
  ctx.fillStyle = "#7dd3fc"; ctx.fillRect(x+3, y+1, 8, 12);
  // bubbles
  if ((frame >> 2) % 6 < 3) {
    ctx.fillStyle = "#e0f2fe";
    ctx.fillRect(x+5, y+3 + ((frame>>1)%6), 1, 1);
    ctx.fillRect(x+8, y+5 + ((frame>>2)%5), 1, 1);
  }
  // body
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x, y+14, 14, 22);
  ctx.fillStyle = "#9ca3af"; ctx.fillRect(x, y+14, 14, 1);
  ctx.fillStyle = "#e8eef9"; ctx.fillRect(x+1, y+15, 12, 20);
  // taps
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(x+3, y+22, 2, 4);
  ctx.fillStyle = "#dc2626"; ctx.fillRect(x+3, y+21, 2, 1);
  ctx.fillStyle = "#0a0a0a";
  ctx.fillRect(x+9, y+22, 2, 4);
  ctx.fillStyle = "#1e40af"; ctx.fillRect(x+9, y+21, 2, 1);
  // drip tray
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+1, y+30, 12, 1);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x, y+35, 14, 2);
}

// ---------- FILING CABINET ----------
function drawCabinet(ctx, x, y) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 18, 38);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+1, y+1, 16, 36);
  ctx.fillStyle = "#5a5a5a"; ctx.fillRect(x+2, y+2, 14, 1);
  // 3 drawers
  for (let i = 0; i < 3; i++) {
    const dy = y + 3 + i*12;
    ctx.fillStyle = "#27272a"; ctx.fillRect(x+2, dy, 14, 10);
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+2, dy, 14, 1);
    ctx.fillStyle = "#5a5a5a"; ctx.fillRect(x+2, dy+1, 14, 1);
    // handle
    ctx.fillStyle = "#9ca3af"; ctx.fillRect(x+7, dy+5, 4, 2);
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+7, dy+7, 4, 1);
    // label tag
    ctx.fillStyle = "#fde047"; ctx.fillRect(x+4, dy+3, 5, 1);
  }
  // shadow under
  ctx.fillStyle = "#000000"; ctx.fillRect(x-1, y+38, 20, 1);
}

// ---------- BOOKSHELF ----------
function drawBookshelf(ctx, x, y) {
  ctx.fillStyle = "#3d2817"; ctx.fillRect(x, y, 30, 56);
  ctx.fillStyle = "#5a3826"; ctx.fillRect(x+1, y+1, 28, 1);
  ctx.fillStyle = "#251509"; ctx.fillRect(x+1, y+55, 28, 1);
  // 4 shelves
  for (let s = 0; s < 4; s++) {
    const sy = y + 4 + s*13;
    ctx.fillStyle = "#251509"; ctx.fillRect(x+2, sy, 26, 1);
    // books on shelf
    const colors = ["#dc2626","#1e40af","#15803d","#fde047","#7f1d1d","#a78bfa","#fb923c","#0e7490","#27272a"];
    let bx = x + 3;
    for (let i = 0; i < 9; i++) {
      const bw = 2 + ((s*3 + i*5) % 3);
      const bh = 9 + ((s + i) % 3);
      const bc = colors[(s*3 + i) % colors.length];
      if (bx + bw > x + 28) break;
      ctx.fillStyle = "#1c1c1c"; ctx.fillRect(bx, sy + 13 - bh, bw, bh);
      ctx.fillStyle = bc; ctx.fillRect(bx, sy + 13 - bh + 1, bw, bh - 2);
      // light band
      ctx.fillStyle = "rgba(255,255,255,0.2)";
      bx += bw + 1;
    }
  }
  // top decoration: small clock or trophy
  ctx.fillStyle = "#fde047"; ctx.fillRect(x+12, y-4, 6, 4);
  ctx.fillStyle = "#a16207"; ctx.fillRect(x+13, y, 4, 1);
  ctx.fillStyle = "#a16207"; ctx.fillRect(x+14, y+1, 2, 2);
}

// ---------- WALL CLOCK ----------
function drawWallClock(ctx, x, y, frame) {
  // outer ring
  ctx.fillStyle = "#0a0a0a";
  for (let dx = -7; dx <= 7; dx++) for (let dy = -7; dy <= 7; dy++) {
    if (dx*dx + dy*dy <= 49 && dx*dx + dy*dy >= 36) ctx.fillRect(x+7+dx, y+7+dy, 1, 1);
  }
  // face
  ctx.fillStyle = "#e8eef9";
  for (let dx = -6; dx <= 6; dx++) for (let dy = -6; dy <= 6; dy++) {
    if (dx*dx + dy*dy <= 36) ctx.fillRect(x+7+dx, y+7+dy, 1, 1);
  }
  // hour markers
  ctx.fillStyle = "#1c1c1c";
  ctx.fillRect(x+7, y+1, 1, 2);
  ctx.fillRect(x+7, y+12, 1, 2);
  ctx.fillRect(x+1, y+7, 2, 1);
  ctx.fillRect(x+12, y+7, 2, 1);
  // hour hand (slow)
  const hAng = ((frame / 600) % 1) * Math.PI * 2 - Math.PI/2;
  for (let r = 0; r < 3; r++) {
    const px = Math.round(x+7 + Math.cos(hAng)*r);
    const py = Math.round(y+7 + Math.sin(hAng)*r);
    ctx.fillRect(px, py, 1, 1);
  }
  // minute hand (fast)
  ctx.fillStyle = "#dc2626";
  const mAng = ((frame / 100) % 1) * Math.PI * 2 - Math.PI/2;
  for (let r = 0; r < 5; r++) {
    const px = Math.round(x+7 + Math.cos(mAng)*r);
    const py = Math.round(y+7 + Math.sin(mAng)*r);
    ctx.fillRect(px, py, 1, 1);
  }
  // center dot
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+6, y+6, 2, 2);
}

// ---------- POSTER (framed picture) ----------
function drawPoster(ctx, x, y, w, h, opts = {}) {
  ctx.fillStyle = "#3d2817"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+1, y+1, w-2, h-2);
  ctx.fillStyle = opts.bg || "#1e3a8a"; ctx.fillRect(x+2, y+2, w-4, h-4);
  // inner art: stylized M for Mekka
  if (opts.style === "M") {
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x+3, y+4, 1, h-8);
    ctx.fillRect(x+w-4, y+4, 1, h-8);
    ctx.fillRect(x+4, y+5, 1, 2);
    ctx.fillRect(x+w-5, y+5, 1, 2);
    ctx.fillRect(x+5, y+7, 1, 2);
    ctx.fillRect(x+w-6, y+7, 1, 2);
    ctx.fillRect(x+6, y+9, w-12, 1);
  } else if (opts.style === "chart") {
    // up-and-to-right line
    ctx.fillStyle = "#22c55e";
    for (let i = 0; i < w-6; i++) {
      const py = y + h - 4 - Math.floor(i * (h-8) / (w-6));
      ctx.fillRect(x+3+i, py, 1, 1);
    }
  } else if (opts.style === "agent") {
    // tiny agent silhouette
    ctx.fillStyle = "#fde047";
    ctx.fillRect(x+w/2-2, y+3, 4, 4);  // head
    ctx.fillRect(x+w/2-3, y+7, 6, h-10);  // body
  }
}

// ---------- TRASH BIN ----------
function drawTrash(ctx, x, y) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 10, 12);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+1, y+1, 8, 10);
  ctx.fillStyle = "#5a5a5a"; ctx.fillRect(x+1, y+1, 8, 1);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+2, y+3, 6, 1);
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+2, y+6, 6, 1);
  // crumpled paper sticking out
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x+3, y, 4, 2);
}

// ---------- FLOOR LAMP ----------
function drawFloorLamp(ctx, x, y, frame) {
  // pole
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+5, y+12, 2, 28);
  // base
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+2, y+38, 8, 3);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x+3, y+39, 6, 1);
  // shade
  ctx.fillStyle = "#fbbf24";
  ctx.fillRect(x+1, y+4, 10, 2);
  ctx.fillRect(x, y+6, 12, 6);
  ctx.fillStyle = "#fde047"; ctx.fillRect(x+1, y+7, 10, 4);
  // glow
  if ((frame >> 4) % 3 !== 0) {
    ctx.fillStyle = "rgba(253,224,71,0.15)";
    ctx.fillRect(x-4, y+2, 20, 16);
  }
}

// ---------- PRINTER ----------
function drawPrinter(ctx, x, y, frame) {
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 22, 14);
  ctx.fillStyle = "#cfd9ec"; ctx.fillRect(x+1, y+1, 20, 12);
  ctx.fillStyle = "#9ca3af"; ctx.fillRect(x+1, y+5, 20, 1);
  // paper tray
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+2, y+6, 18, 1);
  // paper coming out
  if ((frame >> 3) % 6 < 4) {
    ctx.fillStyle = "#ffffff"; ctx.fillRect(x+4, y-2, 14, 3);
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+5, y-1, 12, 1);
  }
  // status light
  ctx.fillStyle = (frame >> 2) % 2 ? "#22c55e" : "#0a4d24";
  ctx.fillRect(x+18, y+2, 2, 2);
}

// ---------- POI MARKER (subtle floor glow under destinations) ----------
function drawPoiMarker(ctx, x, y, color, frame) {
  const pulse = ((frame >> 1) % 16) / 16;
  ctx.globalAlpha = 0.3 - pulse * 0.25;
  ctx.fillStyle = color;
  for (let r = 0; r < 6 + pulse * 8; r++) {
    ctx.fillRect(x - r, y, r*2, 1);
  }
  ctx.globalAlpha = 1;
}

Object.assign(window, {
  drawWallMonitor, drawWhiteboard, drawCoffeeStation, drawWaterCooler,
  drawCabinet, drawBookshelf, drawWallClock, drawPoster, drawTrash,
  drawFloorLamp, drawPrinter, drawPoiMarker,
});
