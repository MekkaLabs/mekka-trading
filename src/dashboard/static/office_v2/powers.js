// Per-hero power animations. Each agent has a power config; the scheduler
// fires powers at random intervals while the agent is at-desk (mostly).
// Render functions paint over the agent on the canvas, behind/over as needed.

const POWERS = {
  superman:      { type: "fly",          color: "#dc2626", every: 90,  dur: 30 },
  ironman:       { type: "repulsor",     color: "#fb923c", every: 95,  dur: 24 },
  thor:          { type: "lightning",    color: "#fde047", every: 100, dur: 22 },
  flash:         { type: "speed",        color: "#facc15", every: 70,  dur: 28 },
  cyclops:       { type: "optic-blast",  color: "#ef4444", every: 90,  dur: 22 },
  wolverine:     { type: "claws",        color: "#e5e7eb", every: 110, dur: 26 },
  spiderman:     { type: "web",          color: "#f9fafb", every: 95,  dur: 22 },
  doctorstrange: { type: "portal",       color: "#fb923c", every: 110, dur: 32 },
  blackpanther:  { type: "claw-swipe",   color: "#a78bfa", every: 100, dur: 18 },
  vision:        { type: "mind-beam",    color: "#fde047", every: 100, dur: 22 },
  professorx:    { type: "telepathy",    color: "#a78bfa", every: 70,  dur: 32 },
  batman:        { type: "cape",         color: "#1f2937", every: 110, dur: 26 },
  aquaman:       { type: "trident",      color: "#22d3ee", every: 105, dur: 22 },
  deadpool:      { type: "katana",       color: "#ef4444", every: 95,  dur: 26 },
  hulk:          { type: "smash",        color: "#22c55e", every: 120, dur: 20 },
  hawkeye:       { type: "arrow",        color: "#fde047", every: 95,  dur: 22 },
  nighttrader:   { type: "moon",         color: "#a78bfa", every: 110, dur: 26 },
  nickfury:      { type: "command",      color: "#22c55e", every: 100, dur: 28 },
  portfolio:     { type: "balance",      color: "#22c55e", every: 115, dur: 24 },
  dailypnl:      { type: "scroll",       color: "#fde047", every: 120, dur: 22 },
};

function makeInitialPowers() {
  const out = {};
  for (const id in POWERS) {
    out[id] = { phase: "idle", t: 0, next: 80 + Math.floor(Math.random() * 80) };
  }
  return out;
}

// Advance per-agent power state. Pass motion so we can avoid firing while
// walking (most powers only fire when seated).
function tickPowers(state, frame, motion) {
  for (const id in state) {
    const s = state[id];
    const cfg = POWERS[id]; if (!cfg) continue;
    const m = motion[id];
    if (s.phase === "active") {
      s.t += 1;
      if (s.t >= cfg.dur) {
        s.phase = "idle";
        s.t = 0;
        s.next = frame + cfg.every + Math.floor(Math.random() * 40);
      }
    } else {
      if (frame >= s.next && m && m.mode === "at-desk") {
        s.phase = "active";
        s.t = 0;
      }
    }
  }
}

// Draw the power effect for an agent at (x, y) given its state and frame.
// Coordinate convention: agent sprite anchor is top-left, 16x22.
function drawPower(ctx, agentId, x, y, state, frame) {
  const cfg = POWERS[agentId]; if (!cfg) return;
  const s = state[agentId]; if (!s || s.phase !== "active") return;
  const p = s.t / cfg.dur;            // 0..1 normalized
  const fadeIn = Math.min(1, s.t / 4);
  const fadeOut = Math.min(1, (cfg.dur - s.t) / 4);
  const alpha = Math.min(fadeIn, fadeOut);
  ctx.save();
  ctx.globalAlpha = alpha;

  switch (cfg.type) {
    case "fly": {
      // Lift effect — wind streaks behind. The actual y-offset is applied
      // elsewhere (drawAgent reads getPowerLift).
      ctx.fillStyle = "#e0f2fe";
      for (let i = 0; i < 5; i++) {
        const sy = y + 14 + i*2;
        ctx.fillRect(x + 1, sy + 4, 3, 1);
        ctx.fillRect(x + 12, sy + 5, 3, 1);
      }
      // Cape flare swept behind
      ctx.fillStyle = cfg.color;
      ctx.fillRect(x - 2, y + 4, 2, 16);
      ctx.fillRect(x - 3, y + 8, 1, 10);
      break;
    }
    case "repulsor": {
      // Beam from palm downward + diag glow
      const bx = x + 12, by = y + 16;
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 14; i++) {
        ctx.fillRect(bx + Math.floor(i/3), by + i, 2, 1);
      }
      ctx.fillStyle = "#fde047";
      for (let i = 0; i < 14; i++) {
        ctx.fillRect(bx + Math.floor(i/3), by + i, 1, 1);
      }
      // muzzle glow at hand
      ctx.fillStyle = "rgba(251,146,60,0.6)";
      ctx.fillRect(bx - 1, by - 2, 4, 4);
      // Also: chest arc reactor pulse
      ctx.fillStyle = (frame % 4 < 2) ? "#fde047" : "#fb923c";
      ctx.fillRect(x + 7, y + 11, 2, 2);
      break;
    }
    case "lightning": {
      // Zigzag from top to head — animated
      const offsets = [-2, 0, -1, 1, -2, 0, -1];
      const baseX = x + 8;
      ctx.fillStyle = cfg.color;
      let py = y - 22;
      for (let i = 0; i < offsets.length; i++) {
        const px = baseX + offsets[(i + (frame >> 1)) % offsets.length];
        ctx.fillRect(px, py, 2, 4);
        py += 4;
      }
      // hammer raised — small grey block above
      ctx.fillStyle = "#9ca3af";
      ctx.fillRect(x + 13, y - 6, 4, 3);
      ctx.fillStyle = "#3a3a3a";
      ctx.fillRect(x + 14, y - 3, 2, 6);
      break;
    }
    case "speed": {
      // Speed lines behind + lightning crackle around feet
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 4; i++) {
        const ly = y + 6 + i*3;
        ctx.fillRect(x - 6 - (i*2), ly, 4, 1);
      }
      // feet lightning
      const t = (frame & 3);
      ctx.fillRect(x + 1 + t, y + 19, 1, 2);
      ctx.fillRect(x + 12 - t, y + 19, 1, 2);
      // glow around body
      ctx.fillStyle = "rgba(250,204,21,0.18)";
      ctx.fillRect(x - 2, y, 20, 22);
      break;
    }
    case "optic-blast": {
      // Horizontal red beam from eye
      const ey = y + 6;
      const len = Math.floor(28 * Math.min(1, p * 2));
      ctx.fillStyle = "#7f1d1d";
      ctx.fillRect(x + 16, ey, len, 4);
      ctx.fillStyle = cfg.color;
      ctx.fillRect(x + 16, ey + 1, len, 2);
      ctx.fillStyle = "#fecaca";
      ctx.fillRect(x + 16, ey + 1, len, 1);
      // visor glow
      ctx.fillStyle = cfg.color;
      ctx.fillRect(x + 5, ey, 8, 2);
      break;
    }
    case "claws": {
      // 3 metal blades from fist
      const bx = x + 13, by = y + 14;
      ctx.fillStyle = "#0a0a0a";
      for (let i = 0; i < 3; i++) {
        ctx.fillRect(bx + i*2, by - 8, 1, 8);
      }
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 3; i++) {
        ctx.fillRect(bx + i*2, by - 8 - (frame & 1), 1, 7);
      }
      // shine
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(bx, by - 6, 1, 1);
      ctx.fillRect(bx + 4, by - 5, 1, 1);
      break;
    }
    case "web": {
      // Web line from wrist diagonally
      const wx = x + 12, wy = y + 14;
      ctx.fillStyle = cfg.color;
      const len = Math.floor(20 * Math.min(1, p * 1.5));
      for (let i = 0; i < len; i++) {
        ctx.fillRect(wx + i, wy - Math.floor(i * 0.7), 1, 1);
      }
      // little web cluster at tip
      const tx = wx + len, ty = wy - Math.floor(len * 0.7);
      ctx.fillRect(tx, ty, 2, 1);
      ctx.fillRect(tx - 1, ty - 1, 1, 1);
      ctx.fillRect(tx + 1, ty + 1, 1, 1);
      break;
    }
    case "portal": {
      // Orange sparking ring near hand
      const cx = x + 18, cy = y + 8;
      const r = 6 + Math.sin(s.t / 2) * 1;
      const segs = 16;
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < segs; i++) {
        const a = (i / segs) * Math.PI * 2 + (frame / 6);
        const px = Math.round(cx + Math.cos(a) * r);
        const py = Math.round(cy + Math.sin(a) * r);
        ctx.fillRect(px, py, 1, 1);
      }
      // inner sparks
      ctx.fillStyle = "#fde047";
      for (let i = 0; i < 4; i++) {
        const a = (i / 4) * Math.PI * 2 + (frame / 3);
        const px = Math.round(cx + Math.cos(a) * (r - 3));
        const py = Math.round(cy + Math.sin(a) * (r - 3));
        ctx.fillRect(px, py, 1, 1);
      }
      // hand glow
      ctx.fillStyle = "rgba(251,146,60,0.4)";
      ctx.fillRect(x + 14, y + 12, 4, 4);
      break;
    }
    case "claw-swipe": {
      // Arcing purple slash
      ctx.fillStyle = cfg.color;
      const cy = y + 10;
      for (let i = 0; i < 3; i++) {
        const dx = 16 + i*2;
        for (let j = 0; j < 8; j++) {
          const arcY = cy - 4 + Math.round(Math.sin(j/8 * Math.PI) * 4);
          ctx.fillRect(x + dx, arcY + j*1, 1, 1);
        }
      }
      break;
    }
    case "mind-beam": {
      // Yellow beam from forehead — slight wobble
      const wob = Math.sin(s.t/2) * 1;
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 16; i++) {
        const py = y + 5 + Math.round(wob);
        ctx.fillRect(x + 16 + i, py, 1, 2);
      }
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(x + 16, y + 5 + Math.round(wob), 1, 2);
      // gem glow on forehead
      ctx.fillStyle = "#fbbf24";
      ctx.fillRect(x + 7, y + 3, 2, 2);
      break;
    }
    case "telepathy": {
      // Concentric circles from head
      const cx = x + 7, cy = y + 5;
      ctx.fillStyle = cfg.color;
      for (let ring = 0; ring < 3; ring++) {
        const r = (s.t / 2 + ring * 4) % 14;
        const segs = 24;
        for (let i = 0; i < segs; i++) {
          const a = (i / segs) * Math.PI * 2;
          const px = Math.round(cx + Math.cos(a) * r);
          const py = Math.round(cy + Math.sin(a) * r * 0.7);
          if (py > y - 4) ctx.fillRect(px, py, 1, 1);
        }
      }
      // forehead glow
      ctx.fillStyle = "rgba(167,139,250,0.4)";
      ctx.fillRect(x + 5, y + 3, 6, 2);
      break;
    }
    case "cape": {
      // Cape flap behind — three-frame animation
      const ph = (frame >> 2) % 3;
      ctx.fillStyle = "#0a0a0a";
      if (ph === 0) {
        ctx.fillRect(x - 2, y + 10, 3, 10);
        ctx.fillRect(x - 3, y + 14, 2, 6);
      } else if (ph === 1) {
        ctx.fillRect(x - 1, y + 10, 2, 10);
        ctx.fillRect(x - 2, y + 14, 2, 8);
      } else {
        ctx.fillRect(x - 3, y + 10, 4, 12);
      }
      // yellow utility belt pulse
      ctx.fillStyle = "#fde047";
      ctx.fillRect(x + 4, y + 13, 8, 1);
      break;
    }
    case "trident": {
      // Vertical trident next to agent + sparkle
      const tx = x + 18;
      ctx.fillStyle = "#fde047";
      ctx.fillRect(tx, y + 4, 1, 16);
      ctx.fillRect(tx - 2, y + 4, 1, 3);
      ctx.fillRect(tx + 2, y + 4, 1, 3);
      ctx.fillRect(tx - 1, y + 4, 1, 2);
      ctx.fillRect(tx + 1, y + 4, 1, 2);
      // water sparkles
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 3; i++) {
        const a = (frame + i * 30) / 4;
        const px = tx + Math.round(Math.cos(a) * 4);
        const py = y + 10 + Math.round(Math.sin(a) * 4);
        ctx.fillRect(px, py, 1, 1);
      }
      break;
    }
    case "katana": {
      // Two crossed red blades above head
      ctx.fillStyle = "#9ca3af";
      const rot = (frame / 4) % 4;
      const blades = [
        [-6,-8, 4,-2], [6,-8, -4,-2], // diagonal arrangement
      ];
      ctx.fillStyle = cfg.color;
      ctx.fillRect(x + 4, y - 4 + (rot%2), 8, 1);
      ctx.fillRect(x + 4 + (rot%2), y - 6, 1, 8);
      ctx.fillStyle = "#e5e7eb";
      ctx.fillRect(x + 5, y - 4 + (rot%2), 8, 1);
      // mask square pulse
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(x + 6, y + 6, 1, 1);
      ctx.fillRect(x + 9, y + 6, 1, 1);
      break;
    }
    case "smash": {
      // Green shockwave ring at feet
      const r = Math.round(p * 14);
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 18; i++) {
        const a = i / 18 * Math.PI * 2;
        const px = Math.round(x + 8 + Math.cos(a) * r);
        const py = Math.round(y + 22 + Math.sin(a) * (r * 0.4));
        ctx.fillRect(px, py, 1, 1);
      }
      // raise arms — small white pulse above head
      ctx.fillStyle = "rgba(34,197,94,0.4)";
      ctx.fillRect(x + 2, y - 2, 12, 4);
      break;
    }
    case "arrow": {
      // Bow drawn + arrow shooting right
      const ax = x + 18, ay = y + 8;
      const len = Math.floor(20 * Math.min(1, p * 2));
      ctx.fillStyle = "#7c2d12";
      ctx.fillRect(ax, ay, len, 1);
      // arrowhead
      ctx.fillStyle = cfg.color;
      ctx.fillRect(ax + len, ay - 1, 2, 3);
      // fletching
      ctx.fillStyle = "#dc2626";
      ctx.fillRect(ax, ay - 1, 1, 1);
      ctx.fillRect(ax, ay + 1, 1, 1);
      break;
    }
    case "moon": {
      // 3 small moons orbiting head
      const cx = x + 8, cy = y + 4;
      ctx.fillStyle = cfg.color;
      for (let i = 0; i < 3; i++) {
        const a = frame / 5 + (i * 2 * Math.PI / 3);
        const px = Math.round(cx + Math.cos(a) * 8);
        const py = Math.round(cy + Math.sin(a) * 4);
        ctx.fillRect(px, py, 2, 2);
      }
      // dark sky shimmer
      ctx.fillStyle = "rgba(167,139,250,0.18)";
      ctx.fillRect(x - 2, y - 4, 20, 12);
      break;
    }
    case "command": {
      // Green halo + 4 floating dots (drones / orders)
      const cx = x + 8, cy = y + 3;
      ctx.fillStyle = cfg.color;
      // halo
      const r = 6;
      const segs = 18;
      for (let i = 0; i < segs; i++) {
        const a = (i / segs) * Math.PI * 2;
        const px = Math.round(cx + Math.cos(a) * r);
        const py = Math.round(cy + Math.sin(a) * (r * 0.5));
        ctx.fillRect(px, py, 1, 1);
      }
      // 4 order-dots
      for (let i = 0; i < 4; i++) {
        const a = frame / 6 + i * Math.PI / 2;
        const px = Math.round(cx + Math.cos(a) * 10);
        const py = Math.round(cy + Math.sin(a) * 5);
        ctx.fillRect(px - 1, py, 3, 1);
        ctx.fillRect(px, py - 1, 1, 3);
      }
      break;
    }
    case "balance": {
      // Two scale platforms tilting
      const tilt = Math.sin(frame / 6) * 2;
      ctx.fillStyle = cfg.color;
      ctx.fillRect(x - 2, y + 6 + tilt, 4, 1);
      ctx.fillRect(x + 14, y + 6 - tilt, 4, 1);
      // string/connector
      ctx.fillRect(x + 8, y + 3, 1, 4);
      ctx.fillRect(x + 0, y + 3 + tilt, 1, 3);
      ctx.fillRect(x + 16, y + 3 - tilt, 1, 3);
      break;
    }
    case "scroll": {
      // Paper scroll unfurling from hands
      const len = Math.floor(p * 16);
      ctx.fillStyle = "#fef3c7";
      ctx.fillRect(x + 16, y + 10, len, 8);
      ctx.fillStyle = "#0a0a0a";
      for (let i = 1; i < len - 1; i += 3) {
        ctx.fillRect(x + 16 + i, y + 12, 2, 1);
        ctx.fillRect(x + 16 + i, y + 15, 2, 1);
      }
      break;
    }
  }
  ctx.restore();
}

// How much an agent should be lifted in y (negative = up) due to an active
// power. Used to draw flying agents off the ground.
function getPowerLift(agentId, state, frame) {
  const cfg = POWERS[agentId]; if (!cfg) return 0;
  const s = state[agentId]; if (!s || s.phase !== "active") return 0;
  if (cfg.type === "fly" || cfg.type === "repulsor") {
    const p = s.t / cfg.dur;
    // ease up to -8 px and back
    return -Math.round(Math.sin(p * Math.PI) * 8);
  }
  return 0;
}

Object.assign(window, { POWERS, makeInitialPowers, tickPowers, drawPower, getPowerLift });
