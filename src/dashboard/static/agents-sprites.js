// Pixel-art sprite engine for Mekka Trading Pixel Office.
// Each sprite is a string array; chars map to palette keys.
// '.' = transparent. Sprites are drawn into an offscreen ImageData,
// then blitted into the main canvas at integer pixel coords.
//
// P0.6 (HANDOFF 2026-05-20): this file is a plain-.js copy of
// office_v2/sprites.jsx so the main dashboard (index.html) can include
// `<script src="/static/agents-sprites.js">` and the Agents Roster
// shares the exact pixel art the Pixel Office uses. Keep this file in
// sync with office_v2/sprites.jsx until the Office v2 bundle is
// reworked to expose `window.AGENTS` to the parent page directly.

const HEX = (h) => {
  const r = parseInt(h.slice(1,3),16), g = parseInt(h.slice(3,5),16), b = parseInt(h.slice(5,7),16);
  return [r,g,b,255];
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
function pad22(arr){ const w=arr[0].length; while(arr.length<22) arr.push(".".repeat(w)); return arr; }
[CHAR_BASE, CAPE_OVERLAY, HELMET_OVERLAY, MASK_OVERLAY, EYEPATCH_OVERLAY, GLASSES_OVERLAY].forEach(pad22);

// ---------- PROP SPRITES ----------
// Desk + chair + monitor unit (32w x 28h). The character sprite stands
// behind the desk so legs are hidden.
const DESK_BACK = [ // viewed from front-ish, monitor faces away
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
      if (ch === '.' || ch === ' ') continue;
      const color = palette[ch];
      if (!color) continue;
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
    palette: { k:"#0a0a0a", h:"#1a1a1a", H:"#000000", s:"#a0826d", S:"#7a5e4d",
               e:"#000000", m:"#5a3a2a", c:"#1c1c1c", C:"#0d0d0d",
               a:"#3b3b3b", A:"#1c1c1c", p:"#0a0a0a", P:"#000000" },
    overlay: { sprite: "EYEPATCH", palette: { A:"#000000", a:"#3a3a3a" } },
  },
  {
    id: "portfolio",
    name: "PortfolioManager",
    role: "Capital Allocation",
    layer: "L4",
    color: "#22c55e",
    summary: "Sizes positions. Owns the equity curve.",
    task: "Rebalancing book — 4 open hedges",
    palette: { k:"#1a1a1a", h:"#3d2817", H:"#251509", s:"#e8b888", S:"#b88860",
               e:"#000000", m:"#7a3a2a", c:"#1e3a8a", C:"#0f1f5c",
               a:"#dc2626", A:"#7f1d1d", p:"#1c1c2c", P:"#0c0c1c" },
  },
  {
    id: "dailypnl",
    name: "DailyPnLWriter",
    role: "Reporting",
    layer: "L4",
    color: "#22c55e",
    summary: "Drafts the daily PnL note and incident summaries.",
    task: "Writing close-of-day report v07",
    palette: { k:"#1a1a1a", h:"#c0a060", H:"#806838", s:"#f0c8a0", S:"#c09870",
               e:"#000000", m:"#7a3a2a", c:"#7c2d12", C:"#451a09",
               a:"#facc15", A:"#a16207", p:"#1c1c2c", P:"#0c0c1c" },
  },
  {
    id: "vision",
    name: "Vision",
    role: "Strategy Synthesis",
    layer: "L2",
    color: "#a78bfa",
    summary: "Combines L1 signals into ranked strategy candidates.",
    task: "Scoring 12 strategy proposals",
    palette: { k:"#1a0a1a", h:"#7c2d12", H:"#451a09", s:"#fde68a", S:"#ca8a04",
               e:"#000000", m:"#9a3a2a", c:"#15803d", C:"#0a4d24",
               a:"#facc15", A:"#a16207", p:"#7c2d12", P:"#451a09" },
    overlay: { sprite: "HELMET", palette: { A:"#fde047", a:"#fbbf24", e:"#1a0a1a" } },
  },
  {
    id: "professorx",
    name: "ProfessorX",
    role: "Strategy Reasoning",
    layer: "L2",
    color: "#a78bfa",
    summary: "Long-horizon planner. Owns the macro thesis.",
    task: "Re-evaluating cross-asset correlation regime",
    palette: { k:"#1a1a1a", h:"#fce7c8", H:"#fce7c8", s:"#f5d4b3", S:"#c5a483",
               e:"#000000", m:"#7a3a2a", c:"#3f3f46", C:"#27272a",
               a:"#71717a", A:"#3f3f46", p:"#1c1c2c", P:"#0c0c1c" },
    overlay: { sprite: "GLASSES", palette: { A:"#1a1a1a", a:"#1a1a1a" } },
  },
  {
    id: "ironman",
    name: "IronMan",
    role: "Order Execution",
    layer: "L3",
    color: "#fb923c",
    summary: "Routes orders. Smart-splits across venues.",
    task: "Executing batch — 7 limit orders pending",
    palette: { k:"#1a0a0a", h:"#1a0a0a", H:"#1a0a0a", s:"#dc2626", S:"#7f1d1d",
               e:"#fde047", m:"#1a0a0a", c:"#dc2626", C:"#7f1d1d",
               a:"#facc15", A:"#a16207", p:"#dc2626", P:"#7f1d1d" },
    overlay: { sprite: "HELMET", palette: { A:"#dc2626", a:"#facc15", e:"#fde047" } },
  },
  {
    id: "batman",
    name: "Batman",
    role: "Risk Watch",
    layer: "L3",
    color: "#fb923c",
    summary: "Patrols thresholds. Pulls the kill switch.",
    task: "Monitoring drawdown — within band",
    palette: { k:"#0a0a0a", h:"#0a0a0a", H:"#0a0a0a", s:"#d4a884", S:"#a47854",
               e:"#000000", m:"#5a2a1a", c:"#27272a", C:"#0a0a0a",
               a:"#facc15", A:"#a16207", p:"#0a0a0a", P:"#000000" },
    overlay: { sprite: "MASK", palette: { A:"#0a0a0a", a:"#0a0a0a", e:"#ffffff" } },
  },
  {
    id: "superman",
    name: "Superman",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "Top-down macro feed reader.",
    task: "Parsing FOMC minutes (just dropped)",
    palette: { k:"#0a0a1a", h:"#1e3a8a", H:"#0f1f5c", s:"#fde68a", S:"#ca8a04",
               e:"#1e40af", m:"#7a3a2a", c:"#1e40af", C:"#0f1f5c",
               a:"#dc2626", A:"#7f1d1d", p:"#1e40af", P:"#0f1f5c" },
    overlay: { sprite: "CAPE", palette: { A:"#7f1d1d", a:"#dc2626" } },
  },
  {
    id: "doctorstrange",
    name: "DoctorStrange",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "Pattern + regime detection across timeframes.",
    task: "Tagging unusual options flow",
    palette: { k:"#1a0a0a", h:"#1a1a1a", H:"#0a0a0a", s:"#e8b888", S:"#b88860",
               e:"#000000", m:"#7a3a2a", c:"#1a1a1a", C:"#0a0a0a",
               a:"#7f1d1d", A:"#451209", p:"#1a1a1a", P:"#0a0a0a" },
    overlay: { sprite: "CAPE", palette: { A:"#991b1b", a:"#dc2626" } },
  },
  {
    id: "blackpanther",
    name: "BlackPanther",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "Microstructure scout — order book tells.",
    task: "Watching ASK depth on 4 symbols",
    palette: { k:"#0a0a0a", h:"#0a0a0a", H:"#0a0a0a", s:"#3a2a1a", S:"#1a0a00",
               e:"#a78bfa", m:"#0a0a0a", c:"#1a1a1a", C:"#0a0a0a",
               a:"#a78bfa", A:"#5b21b6", p:"#0a0a0a", P:"#000000" },
    overlay: { sprite: "MASK", palette: { A:"#0a0a0a", a:"#0a0a0a", e:"#a78bfa" } },
  },
  {
    id: "thor",
    name: "Thor",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "High-impact event watcher — earnings, vols, shocks.",
    task: "Pre-positioning around NVDA earnings",
    palette: { k:"#1a0a0a", h:"#fde68a", H:"#ca8a04", s:"#f5c8a0", S:"#c59870",
               e:"#1e40af", m:"#7a3a2a", c:"#3f3f46", C:"#27272a",
               a:"#7f1d1d", A:"#451209", p:"#27272a", P:"#0a0a0a" },
    overlay: { sprite: "CAPE", palette: { A:"#7f1d1d", a:"#dc2626" } },
  },
  {
    id: "aquaman",
    name: "Aquaman",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "Liquidity & depth reader.",
    task: "Charting liquidity void on ETH/USDT",
    palette: { k:"#0a1a1a", h:"#fde68a", H:"#ca8a04", s:"#f5c8a0", S:"#c59870",
               e:"#0e7490", m:"#7a3a2a", c:"#15803d", C:"#0a4d24",
               a:"#facc15", A:"#a16207", p:"#0e7490", P:"#0a4054" },
  },
  {
    id: "spiderman",
    name: "SpiderMan",
    role: "Market Analysis",
    layer: "L1",
    color: "#38bdf8",
    summary: "Cross-venue arb scanner.",
    task: "3 spread opps detected in last 30s",
    palette: { k:"#1a0a0a", h:"#0f1f5c", H:"#0a0a3a", s:"#0f1f5c", S:"#0a0a3a",
               e:"#ffffff", m:"#0a0a0a", c:"#dc2626", C:"#7f1d1d",
               a:"#0f1f5c", A:"#0a0a3a", p:"#0f1f5c", P:"#0a0a3a" },
    overlay: { sprite: "MASK", palette: { A:"#dc2626", a:"#dc2626", e:"#ffffff" } },
  },
  {
    id: "nighttrader",
    name: "NightTrader",
    role: "Asia Session",
    layer: "L3",
    color: "#fb923c",
    summary: "Owns the overnight book — Asia open through London handoff.",
    task: "JPY carry, 2 positions open",
    palette: { k:"#0a0a14", h:"#1c0a3e", H:"#0a0020", s:"#a78bfa", S:"#5b21b6",
               e:"#fde047", m:"#1a0a0a", c:"#0a0a14", C:"#000000",
               a:"#7c3aed", A:"#3b0764", p:"#0a0a14", P:"#000000" },
    overlay: { sprite: "MASK", palette: { A:"#0a0a14", a:"#0a0a14", e:"#fde047" } },
  },
  {
    id: "hawkeye",
    name: "Hawkeye",
    role: "Microstructure",
    layer: "L1",
    color: "#38bdf8",
    summary: "Picks resting orders. Surgical level-2 reader.",
    task: "Sniping hidden bids on SOL/USDT",
    palette: { k:"#1a1a0a", h:"#7c2d12", H:"#451a09", s:"#e8b888", S:"#b88860",
               e:"#0e7490", m:"#7a3a2a", c:"#5b21b6", C:"#3b0764",
               a:"#fde047", A:"#a16207", p:"#27272a", P:"#0a0a0a" },
  },
  {
    id: "hulk",
    name: "Hulk",
    role: "Risk Stress Test",
    layer: "L3",
    color: "#fb923c",
    summary: "Replays scenarios at 3-10× notional. Breaks things on purpose.",
    task: "Stress: 2008 vol regime — caps holding",
    palette: { k:"#0a1a0a", h:"#0a1a0a", H:"#000000", s:"#22c55e", S:"#15803d",
               e:"#fde047", m:"#0a0a0a", c:"#7c2d12", C:"#451a09",
               a:"#cfd9ec", A:"#9ca3af", p:"#3f3f46", P:"#27272a" },
  },
  {
    id: "flash",
    name: "Flash",
    role: "Low-Latency Execution",
    layer: "L1",
    color: "#facc15",
    summary: "Ultra-fast tape reader. Sub-ms reaction.",
    task: "Front-running latency on 3 venues",
    palette: { k:"#1a0a0a", h:"#7c2d12", H:"#451a09", s:"#f5c8a0", S:"#c59870",
               e:"#1e40af", m:"#7a3a2a", c:"#dc2626", C:"#7f1d1d",
               a:"#facc15", A:"#a16207", p:"#dc2626", P:"#7f1d1d" },
    overlay: { sprite: "MASK", palette: { A:"#dc2626", a:"#dc2626", e:"#facc15" } },
  },
  {
    id: "wolverine",
    name: "Wolverine",
    role: "Position Cutter",
    layer: "L3",
    color: "#fb923c",
    summary: "Slices losing positions fast. No mercy on stops.",
    task: "Stopped 2 longs — net -0.18%",
    palette: { k:"#1a0a0a", h:"#0f1f5c", H:"#0a0a3a", s:"#e8b888", S:"#b88860",
               e:"#000000", m:"#5a3a2a", c:"#1e40af", C:"#0f1f5c",
               a:"#fde047", A:"#a16207", p:"#1e40af", P:"#0f1f5c" },
    overlay: { sprite: "MASK", palette: { A:"#1e40af", a:"#fde047", e:"#000000" } },
  },
  {
    id: "cyclops",
    name: "Cyclops",
    role: "Order Sniper",
    layer: "L3",
    color: "#fb923c",
    summary: "Precision execution. Fires only when the line is clean.",
    task: "Aiming 4 limit orders at level 2",
    palette: { k:"#1a0a0a", h:"#5a3826", H:"#3d2817", s:"#e8b888", S:"#b88860",
               e:"#ef4444", m:"#5a2a1a", c:"#1e40af", C:"#0f1f5c",
               a:"#fde047", A:"#a16207", p:"#1e40af", P:"#0f1f5c" },
    overlay: { sprite: "VISOR", palette: { A:"#1c1c1c", a:"#ef4444", e:"#ef4444" } },
  },
  {
    id: "deadpool",
    name: "Deadpool",
    role: "Chaos Hedger",
    layer: "L2",
    color: "#a78bfa",
    summary: "Tail-risk specialist. Buys cheap insurance — loudly.",
    task: "Loading OTM puts on QQQ — laughing",
    palette: { k:"#1a0a0a", h:"#7f1d1d", H:"#451209", s:"#dc2626", S:"#7f1d1d",
               e:"#0a0a0a", m:"#0a0a0a", c:"#dc2626", C:"#7f1d1d",
               a:"#0a0a0a", A:"#1c1c1c", p:"#0a0a0a", P:"#000000" },
    overlay: { sprite: "MASK", palette: { A:"#dc2626", a:"#dc2626", e:"#f9fafb" } },
  },
  {
    // Beast — Story 248 (codex M40). Read-only continuous-improvement
    // agent. Dr. Hank McCoy: blue fur, glasses, lab coat. Never trades —
    // proposes improvements via Telegram. Placed in L4 "Analyst" tier
    // alongside Wolverine (recovery) and PortfolioManager (snapshot).
    id: "beast",
    name: "Beast",
    role: "Continuous Improvement",
    layer: "L4",
    color: "#38bdf8",  // cyan-blue — distinct from Superman blue
    summary: "Reads the audit log. Proposes weekly improvement candidates to the operator.",
    task: "Auditing last 7 days of trades — 2 proposals queued",
    // Blue fur (cyan body), white lab coat, dark glasses overlay
    palette: { k:"#0a1a2a", h:"#1e3a5f", H:"#0f1f3a", s:"#38bdf8", S:"#0284c7",
               e:"#1c1c1c", m:"#1c2a3a", c:"#f1f5f9", C:"#cbd5e1",
               a:"#38bdf8", A:"#0284c7", p:"#1c1c1c", P:"#000000" },
    overlay: { sprite: "VISOR", palette: { A:"#1c1c1c", a:"#1c1c1c", e:"#1c1c1c" } },
  },
];

// Visor overlay — Cyclops style horizontal red band across eyes
const VISOR_OVERLAY = [
  "................",
  "................",
  "................",
  "................",
  "................",
  "...AAAAAAAAAA...",
  "...AaeeAAeeaA...",
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

const OVERLAYS = {
  CAPE: CAPE_OVERLAY,
  HELMET: HELMET_OVERLAY,
  MASK: MASK_OVERLAY,
  EYEPATCH: EYEPATCH_OVERLAY,
  GLASSES: GLASSES_OVERLAY,
  VISOR: VISOR_OVERLAY,
};

// Walking leg overlays: paint OVER rows 18-21 of the base sprite to show a
// small alternating side-step. Used when the agent is in motion.
const WALK_LEGS_A = [
  // 22 rows; only last 4 carry data
  ...Array(18).fill("................"),
  "..cppppppppppc..",
  "..cppPPPPpppPc..",  // shifted shadow
  "...pp.....ppp...",  // right leg one px right
  "...kk.....kkk...",
];
const WALK_LEGS_B = [
  ...Array(18).fill("................"),
  "..cppppppppppc..",
  "..cppPPPPPPppc..",
  "...ppp.....pp...",  // left leg one px left
  "...kkk.....kk...",
];

// Speech-bubble overlay (small) — drawn above head when agent has a bubble
function drawBubble(ctx, x, y, icon, color = "#cfd9ec") {
  // bubble body 12x9
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x, y, 12, 9);
  ctx.fillStyle = "#ffffff"; ctx.fillRect(x+1, y+1, 10, 7);
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+5, y+9, 2, 1);
  ctx.fillStyle = "#ffffff"; ctx.fillRect(x+5, y+9, 1, 1);
  // tail dot
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x+6, y+10, 1, 1);
  // icon glyph (1-2 chars rendered as pixel art)
  ctx.fillStyle = "#1c1c1c";
  if (icon === "?") {
    ctx.fillRect(x+4, y+2, 4, 1); ctx.fillRect(x+7, y+3, 1, 1);
    ctx.fillRect(x+6, y+4, 1, 1); ctx.fillRect(x+5, y+5, 1, 1);
    ctx.fillRect(x+5, y+7, 1, 1);
  } else if (icon === "☕" || icon === "coffee") {
    ctx.fillStyle = "#7c2d12";
    ctx.fillRect(x+3, y+3, 5, 4);
    ctx.fillStyle = "#1c1c1c";
    ctx.fillRect(x+8, y+4, 1, 2);
    // steam
    ctx.fillStyle = color;
    ctx.fillRect(x+4, y+1, 1, 1); ctx.fillRect(x+6, y+1, 1, 1);
  } else if (icon === "💧" || icon === "water") {
    ctx.fillStyle = "#38bdf8";
    ctx.fillRect(x+5, y+2, 2, 1);
    ctx.fillRect(x+4, y+3, 4, 4);
    ctx.fillRect(x+5, y+7, 2, 1);
  } else if (icon === "📺" || icon === "screen") {
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+3, y+2, 6, 5);
    ctx.fillStyle = "#22c55e"; ctx.fillRect(x+4, y+3, 4, 3);
  } else if (icon === "🖨" || icon === "print") {
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+3, y+3, 6, 4);
    ctx.fillStyle = "#ffffff"; ctx.fillRect(x+4, y+5, 4, 2);
  } else if (icon === "✎" || icon === "pen") {
    ctx.fillStyle = "#fb923c"; ctx.fillRect(x+3, y+5, 6, 1);
    ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x+8, y+4, 1, 3);
    ctx.fillStyle = "#fde047"; ctx.fillRect(x+4, y+3, 1, 2);
  } else if (icon === "!") {
    ctx.fillStyle = "#dc2626";
    ctx.fillRect(x+5, y+2, 2, 4);
    ctx.fillRect(x+5, y+7, 2, 1);
  }
}

// Wheelchair (drawn UNDER an agent whose legs are hidden). The chair is
// 16w x 12h, drawn at (x, y+12) so the seat overlaps the agent's hips and
// the wheels sit on the floor at y+22.
function drawWheelchair(ctx, x, y, frame, opts = {}) {
  const dir = opts.dir || 0; // 0 idle, > 0 wheels spin forward, < 0 reverse
  // Erase the pants section of the base sprite — paint chair seat over it.
  // Seat
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x + 2, y + 16, 12, 4);
  ctx.fillStyle = "#3a3a3a"; ctx.fillRect(x + 2, y + 16, 12, 1);
  // Armrests
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x + 1, y + 12, 1, 6);
  ctx.fillStyle = "#0a0a0a"; ctx.fillRect(x + 14, y + 12, 1, 6);
  // Backrest hint
  ctx.fillStyle = "#1c1c1c"; ctx.fillRect(x + 2, y + 11, 12, 2);
  // Wheels — large left + small right (motorized chair); spokes animate
  // Left wheel (8w, 8h at floor)
  function drawWheel(cx, cy, r, spinFrame) {
    // outer ring
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        const d2 = dx*dx + dy*dy;
        if (d2 <= r*r && d2 >= (r-1)*(r-1)) {
          ctx.fillStyle = "#0a0a0a"; ctx.fillRect(cx+dx, cy+dy, 1, 1);
        }
      }
    }
    // hub
    ctx.fillStyle = "#cfd9ec"; ctx.fillRect(cx-1, cy-1, 2, 2);
    // 4 spokes rotating
    ctx.fillStyle = "#3a3a3a";
    const spokes = [0, Math.PI/4, Math.PI/2, 3*Math.PI/4];
    for (const base of spokes) {
      const a = base + spinFrame * 0.15;
      for (let i = 1; i < r-1; i++) {
        const px = Math.round(cx + Math.cos(a) * i);
        const py = Math.round(cy + Math.sin(a) * i);
        ctx.fillRect(px, py, 1, 1);
      }
    }
  }
  // Big back wheel left side
  drawWheel(x + 2, y + 19, 4, dir !== 0 ? frame : 0);
  // Big back wheel right side
  drawWheel(x + 14, y + 19, 4, dir !== 0 ? frame : 0);
  // Floor shadow
  ctx.fillStyle = "rgba(0,0,0,0.4)";
  ctx.fillRect(x + 1, y + 23, 14, 1);
}

// Render a complete agent at (x, y) on ctx
function drawAgent(ctx, agent, x, y, opts = {}) {
  const bobAmt = (opts.bob || 0);
  const walking = !!opts.walking;
  const wheelchair = !!opts.wheelchair;
  // cape goes BEHIND character
  if (agent.overlay && agent.overlay.sprite === "CAPE") {
    drawSprite(ctx, OVERLAYS.CAPE, x, y + bobAmt, agent.overlay.palette, opts);
  }
  drawSprite(ctx, CHAR_BASE, x, y + bobAmt, agent.palette, opts);
  if (wheelchair) {
    drawWheelchair(ctx, x, y + bobAmt, opts.frame || 0, { dir: walking ? (opts.flip ? -1 : 1) : 0 });
  } else if (walking) {
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

Object.assign(window, { CHAR_BASE, CAPE_OVERLAY, OVERLAYS, AGENTS, drawSprite, drawAgent, drawWheelchair,
  DESK_BACK, DESK_FRONT, PLANT, MUG, POPUP, SERVER, WINDOW, HEX });
