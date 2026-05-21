/* Office v4 — Living futuristic top-down office:
   - 2000×1200 stage, scales to viewport
   - Agents walk between their desks, conference table, coffee bar, etc.
   - Speech and thought bubbles with contextual dialog
   - Patrolling drones, scrolling data walls, holographic floor projections
*/

const { useState, useEffect, useMemo, useRef, useCallback } = React;

/* ════════ AGENT HOME STATIONS ════════ */
const STATIONS = [
  /* Wall */
  { id: 'nimbus',   x: 110,  y: 180, zone: 'wall' },
  { id: 'sleek',    x: 1780, y: 180, zone: 'wall' },

  /* L1 ANALYSIS — left zone */
  { id: 'falcon',   x: 40,   y: 360, zone: 'l1' },
  { id: 'sage',     x: 200,  y: 360, zone: 'l1' },
  { id: 'velox',    x: 360,  y: 360, zone: 'l1' },
  { id: 'hammer',   x: 40,   y: 640, zone: 'l1' },
  { id: 'tide',     x: 200,  y: 640, zone: 'l1' },

  /* L2 STRATEGY — center top */
  { id: 'synth',    x: 580,  y: 360, zone: 'l2' },
  { id: 'mentor',   x: 740,  y: 360, zone: 'l2' },
  { id: 'joker',    x: 900,  y: 360, zone: 'l2' },

  /* L3 RISK/EXEC — center bottom */
  { id: 'aegis',    x: 580,  y: 640, zone: 'l3' },
  { id: 'sentinel', x: 740,  y: 640, zone: 'l3' },
  { id: 'claw',     x: 900,  y: 640, zone: 'l3' },
  { id: 'visor',    x: 660,  y: 870, zone: 'l3' },
  { id: 'titan',    x: 820,  y: 870, zone: 'l3' },

  /* L4 COMMAND — right zone */
  { id: 'chief',    x: 1620, y: 360, zone: 'l4' },
  { id: 'cosmic',   x: 1780, y: 360, zone: 'l4' },
  { id: 'indigo',   x: 1940, y: 360, zone: 'l4' },
  { id: 'ember',    x: 1620, y: 640, zone: 'l4' },
  { id: 'shade',    x: 1780, y: 640, zone: 'l4' },
  { id: 'arachne',  x: 1940, y: 640, zone: 'l4' },
  { id: 'scribe',   x: 1780, y: 870, zone: 'l4' },
];

const STATIONS_BY_ID = STATIONS.reduce((m, s) => { m[s.id] = s; return m; }, {});

/* ════════ ROOMS + DOORS — for pathfinding ════════ */
/* Door positions chosen so each room exits cleanly into a hallway.
   HALL_Y = main horizontal corridor below all rooms (y=970).
   Vertical corridors exist between rooms at x=500-520, x=980-1000, x=1540-1560.
   All cross-room movement routes via the main corridor to avoid crossing walls. */
const HALL_Y = 970;
const ROOMS = {
  l1:   { bounds: { x:20,   y:320, w:480, h:560 }, door: { x:500,  y:600, side:'right'  } },
  l2:   { bounds: { x:520,  y:320, w:460, h:240 }, door: { x:980,  y:440, side:'right'  } },
  l3:   { bounds: { x:520,  y:580, w:460, h:360 }, door: { x:750,  y:940, side:'bottom' } },
  conf: { bounds: { x:1000, y:320, w:540, h:620 }, door: { x:1270, y:940, side:'bottom' } },
  l4:   { bounds: { x:1560, y:320, w:440, h:620 }, door: { x:1780, y:940, side:'bottom' } },
};

function getRoom(x, y) {
  for (const id in ROOMS) {
    const b = ROOMS[id].bounds;
    if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return id;
  }
  return null;
}

/* Path planner — ALL inter-room trips go via main corridor at HALL_Y.
   Path shape: [door, corridor-anchor, target-corridor-anchor, target-door, final]
   so the moving sprite never crosses a wall edge. */
function buildPath(fromX, fromY, toX, toY) {
  const fromRoom = getRoom(fromX, fromY);
  const toRoom = getRoom(toX, toY);
  if (fromRoom === toRoom) return [{ x: toX, y: toY }];
  const path = [];
  if (fromRoom) {
    const r = ROOMS[fromRoom];
    path.push({ x: r.door.x, y: r.door.y });
    path.push({ x: r.door.x, y: HALL_Y });
  } else {
    path.push({ x: fromX, y: HALL_Y });
  }
  if (toRoom) {
    const r = ROOMS[toRoom];
    path.push({ x: r.door.x, y: HALL_Y });
    path.push({ x: r.door.x, y: r.door.y });
  } else {
    path.push({ x: toX, y: HALL_Y });
  }
  path.push({ x: toX, y: toY });
  return path;
}

/* ════════ ZONE BOXES ════════ */
const ZONES = {
  l1: { x: 20,   y: 320, w: 480, h: 560, color: '#3aaad6', accent: '#5be8f5', label: 'L1 — ANALYSIS' },
  l2: { x: 520,  y: 320, w: 460, h: 240, color: '#a878e8', accent: '#d65aff', label: 'L2 — STRATEGY' },
  l3: { x: 520,  y: 580, w: 460, h: 360, color: '#e89a3a', accent: '#ffae3a', label: 'L3 — RISK/EXEC' },
  l4: { x: 1560, y: 320, w: 440, h: 620, color: '#5fa14b', accent: '#9be8a4', label: 'L4 — COMMAND' },
  /* Conference room — center between L3 and L4 */
  conf:{ x: 1000, y: 320, w: 540, h: 620, color: '#5be8f5', accent: '#a8f4ff', label: 'CONF · BOARD ROOM' },
};

/* ════════ ACTIVITY SPOTS ════════ */
/* Conference table seats — 8 chairs around oval table at center of conf room */
const CONF_CENTER = { x: 1270, y: 630 };
const CONF_SEATS = [
  { id: 'seat1', x: 1110, y: 540 },
  { id: 'seat2', x: 1270, y: 510 },
  { id: 'seat3', x: 1430, y: 540 },
  { id: 'seat4', x: 1470, y: 630 },
  { id: 'seat5', x: 1430, y: 720 },
  { id: 'seat6', x: 1270, y: 750 },
  { id: 'seat7', x: 1110, y: 720 },
  { id: 'seat8', x: 1070, y: 630 },
];

const COFFEE_SPOTS = [
  { id: 'coffee1', x: 140, y: 1010 },
  { id: 'coffee2', x: 220, y: 1010 },
];
const COOLER_SPOTS = [
  { id: 'cooler1', x: 1820, y: 1010 },
];
const PRINTER_SPOTS = [
  { id: 'printer1', x: 1380, y: 1010 },
];
const WANDER_SPOTS = [
  { x: 480, y: 980 }, { x: 1050, y: 980 }, { x: 1530, y: 980 },
  { x: 540, y: 990 }, { x: 1500, y: 990 },
];

/* ════════ DIALOG POOLS ════════ */
const DIALOG = {
  desk: {
    speech: [
      'EURUSD 1.0842 ↑', 'comprando SPY', 'risk OK', 'vol baixo demais',
      'breakout!', 'reduz 50%', '+2.4% hoje', 'NVDA squeeze', 'fechei o lote',
      'stop em 1850', 'rolei a put', 'CL ↑ 1.2%', 'bid pesado', 'aguarda payroll',
      'execução clean', 'PnL +18bps',
    ],
    thought: [
      'fed hawkish?', 'macro confuso', 'overbought?', 'where to next',
      'liquidity thin', 'hmm…', 'fundo aqui?', 'mercado doido',
      'cuidado vol', 'aguenta segura',
    ],
  },
  conference: {
    speech: [
      'concordo', 'PnL semanal +1.2%', 'reduz exposure', 'novo setup', 'stop 1840',
      'aprovado', 'pivot agora', 'rebalance L3', 'subir tier', 'corta hedge',
      'recapitaliza', 'review amanhã', 'next!',
    ],
    thought: [
      'risk muito alto', 'precisa hedge', 'discordo', 'meeting longo',
      'café ainda?', 'foco', '...',
    ],
  },
  coffee: {
    speech: [
      'café tá forte ☕', 'pausa 5min', 'tu viu o NQ?', 'que dia bizarro',
      'preciso disso', 'qual o seu PnL?', 'já são 3h?',
    ],
    thought: ['café…', 'sleep', 'preciso descansar', '☕'],
  },
  cooler: {
    speech: ['água gelada', 'que sede', 'pausa rápida'],
    thought: ['💧', 'hot in here'],
  },
  printer: {
    speech: ['printando…', 'precisa do relatório', 'paper jam de novo?'],
    thought: ['vaaai logo', 'lento'],
  },
  walking: {
    speech: ['já volto', 'vou na confer', 'pausa rápida'],
    thought: ['…', '🚶'],
  },
};

/* ════════ ACTIVITY SCHEDULER ════════ */

function pickActivity(currentActivity, agentId, seatManager) {
  /* Strong return-to-desk bias when away from desk */
  if (currentActivity !== 'desk') {
    if (Math.random() < 0.85) return { kind: 'desk' };
  }

  /* From desk (or 15% of cases when away), pick a new activity.
     Heavy weight on "stay at desk" so the floor isn't a fairground. */
  const r = Math.random();
  if (r < 0.70) return { kind: 'desk' };               // 70% stay/return
  if (r < 0.82) {                                       // 12% informal conference
    const seat = seatManager.claim(agentId);
    if (seat) return { kind: 'conference', target: seat };
    return { kind: 'desk' };
  }
  if (r < 0.89) {                                       // 7% coffee
    const spot = COFFEE_SPOTS[Math.floor(Math.random() * COFFEE_SPOTS.length)];
    return { kind: 'coffee', target: spot };
  }
  if (r < 0.93) {                                       // 4% wander
    const spot = WANDER_SPOTS[Math.floor(Math.random() * WANDER_SPOTS.length)];
    return { kind: 'walking', target: spot };
  }
  if (r < 0.97) return { kind: 'cooler',  target: COOLER_SPOTS[0]  };  // 4%
  return { kind: 'printer', target: PRINTER_SPOTS[0] };               // 3%
}

/* Seat manager - tracks who occupies which conference seat */
class SeatManager {
  constructor(seats) {
    this.occupied = new Map(); // seatId -> agentId
    this.byAgent = new Map();  // agentId -> seatId
    this.seats = seats;
  }
  claim(agentId) {
    if (this.byAgent.has(agentId)) return null;
    for (const seat of this.seats) {
      if (!this.occupied.has(seat.id)) {
        this.occupied.set(seat.id, agentId);
        this.byAgent.set(agentId, seat.id);
        return seat;
      }
    }
    return null;
  }
  release(agentId) {
    const seatId = this.byAgent.get(agentId);
    if (seatId) {
      this.occupied.delete(seatId);
      this.byAgent.delete(agentId);
    }
  }
}

/* ════════ AGENT COMPONENT ════════ */
function Agent({ trader, state, fireKey, bubble, onClick }) {
  const z = ZONES[STATIONS_BY_ID[trader.id]?.zone] || ZONES.l1;
  const zAccent = z.accent;
  const isMoving = !!state.isMoving;
  const flipped = state.facing === 'left';

  /* Discrete hop transition — short enough to feel like a step, not a slide */
  const transitionDuration = isMoving ? '0.24s' : '0.6s';
  /* Bob alternates per step via stepPhase so the up/down rhythm is locked to footfalls */
  const bobY = isMoving ? (state.stepPhase ? -4 : 0) : 0;

  return (
    <div
      onClick={onClick}
      style={{
        position: 'absolute',
        left: 0, top: 0,
        transform: `translate(${state.x - 36}px, ${state.y - 80}px)`,
        transition: `transform ${transitionDuration} linear`,
        cursor: 'pointer',
        zIndex: 5,
        pointerEvents: 'auto',
      }}
    >
      {/* Ground shadow */}
      <div style={{
        position: 'absolute', left: 18, top: 70,
        width: 36, height: 7,
        background: 'radial-gradient(ellipse, rgba(0,0,0,0.55), transparent 70%)',
        opacity: isMoving ? (state.stepPhase ? 0.35 : 0.55) : 0.5,
        transform: isMoving && state.stepPhase ? 'scaleX(0.88)' : 'scaleX(1)',
        transition: 'all 0.18s linear',
        pointerEvents: 'none',
      }} />

      {/* Sprite — direction flip + step-bob via inline transform synced to stepPhase */}
      <div style={{
        position: 'relative',
        width: 72, height: 72,
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
      }}>
        <div style={{
          transform: `scaleX(${flipped ? -1 : 1}) translateY(${bobY}px)`,
          transformOrigin: 'center bottom',
          transition: 'transform 0.16s ease-out',
          width: 71,
          height: 71,
        }}>
          <SpriteCanvas
            draw={trader.draw}
            scale={1.1}
            size={64}
            powerTrigger={fireKey}
          />
        </div>
      </div>

      {/* Label */}
      <div style={{
        position: 'absolute', top: 78, left: '50%', transform: 'translateX(-50%)',
        fontSize: 8, letterSpacing: 1.5,
        color: zAccent,
        background: 'rgba(2,8,18,0.85)',
        border: `1px solid ${zAccent}80`,
        padding: '1px 5px',
        fontFamily: 'JetBrains Mono, monospace',
        textTransform: 'uppercase', fontWeight: 600,
        whiteSpace: 'nowrap',
      }}>{trader.id}</div>

      {/* Speech / thought bubble */}
      {bubble && <Bubble bubble={bubble} accent={zAccent} />}
    </div>
  );
}

/* ════════ BUBBLE COMPONENT ════════ */
function Bubble({ bubble, accent }) {
  const isThought = bubble.kind === 'thought';
  return (
    <div style={{
      position: 'absolute',
      bottom: 96,
      left: '50%',
      transform: 'translateX(-50%)',
      minWidth: 80,
      maxWidth: 170,
      padding: '6px 10px',
      background: isThought ? 'rgba(255,255,255,0.92)' : 'rgba(244,248,255,0.95)',
      color: '#0a1428',
      fontSize: 11,
      fontFamily: 'JetBrains Mono, monospace',
      fontWeight: 600,
      letterSpacing: 0.5,
      borderRadius: isThought ? 14 : 4,
      border: `1.5px solid ${isThought ? '#9eb5cf' : '#1a2840'}`,
      boxShadow: '0 3px 10px rgba(0,0,0,0.45), 0 0 0 1px rgba(0,0,0,0.3)',
      textAlign: 'center',
      whiteSpace: 'nowrap',
      animation: 'bubbleIn 0.25s ease-out',
      zIndex: 10,
      pointerEvents: 'none',
    }}>
      {bubble.text}
      {/* Tail */}
      {isThought ? (
        <>
          <div style={{
            position: 'absolute', bottom: -10, left: '50%', transform: 'translateX(-2px)',
            width: 6, height: 6, background: 'rgba(255,255,255,0.92)',
            border: '1.5px solid #9eb5cf', borderRadius: '50%',
          }} />
          <div style={{
            position: 'absolute', bottom: -18, left: '50%', transform: 'translateX(-1px)',
            width: 3, height: 3, background: 'rgba(255,255,255,0.92)',
            border: '1px solid #9eb5cf', borderRadius: '50%',
          }} />
        </>
      ) : (
        <div style={{
          position: 'absolute', bottom: -7, left: '50%', transform: 'translateX(-50%)',
          width: 0, height: 0,
          borderLeft: '6px solid transparent',
          borderRight: '6px solid transparent',
          borderTop: '7px solid #1a2840',
        }} />
      )}
    </div>
  );
}

/* ════════ CONFERENCE TABLE (centerpiece) ════════ */
function ConferenceTable({ x, y }) {
  return (
    <>
      {/* Glass partition walls around conf room — give it a "room" feel */}
      <div style={{
        position: 'absolute', left: x - 250, top: y - 200, width: 500, height: 380,
        border: '1.5px solid rgba(91,232,245,0.4)',
        borderRadius: 6,
        background: 'radial-gradient(ellipse at center, rgba(91,232,245,0.05) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Floor decal under table */}
      <div style={{
        position: 'absolute', left: x - 180, top: y - 90, width: 360, height: 180,
        background: 'radial-gradient(ellipse, rgba(91,232,245,0.18) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* The oval table */}
      <div style={{
        position: 'absolute',
        left: x - 150, top: y - 50,
        width: 300, height: 100,
        background: 'radial-gradient(ellipse at 30% 30%, #2a3a52 0%, #0e1828 80%)',
        border: '2px solid #5be8f5',
        borderRadius: '50%',
        boxShadow: '0 6px 24px rgba(0,0,0,0.6), 0 0 30px rgba(91,232,245,0.3), inset 0 0 18px rgba(91,232,245,0.15)',
        zIndex: 2,
      }}>
        {/* Holographic data projection on table surface */}
        <div style={{
          position: 'absolute', left: '50%', top: '50%',
          transform: 'translate(-50%,-50%)',
          width: 180, height: 60,
          background: 'rgba(91,232,245,0.12)',
          borderRadius: 6,
        }}>
          <svg viewBox="0 0 180 60" style={{ width: '100%', height: '100%' }}>
            <g opacity="0.85">
              {Array.from({ length: 20 }).map((_, i) => {
                const v = 18 + Math.sin(i * 0.8) * 14 + (i % 3) * 4;
                return <rect key={i} x={4 + i * 9} y={50 - v} width="5" height={v}
                              fill={i % 3 === 0 ? '#9be8a4' : '#5be8f5'} />;
              })}
            </g>
            <text x="6" y="14" fontSize="8" fill="#5be8f5"
                  fontFamily="JetBrains Mono">DAILY BOARD</text>
            <text x="124" y="14" fontSize="8" fill="#9be8a4"
                  fontFamily="JetBrains Mono">+2.4%</text>
          </svg>
        </div>
        {/* Table edge LED ring */}
        <div style={{
          position: 'absolute', inset: -3,
          borderRadius: '50%',
          border: '1px solid rgba(91,232,245,0.6)',
          boxShadow: '0 0 12px rgba(91,232,245,0.5)',
        }} />
      </div>

      {/* 8 chairs around table */}
      {CONF_SEATS.map((seat) => {
        const dx = seat.x - x, dy = seat.y - y;
        const angle = Math.atan2(dy, dx);
        const seatX = seat.x - 12;
        const seatY = seat.y - 12;
        return (
          <div key={seat.id} style={{
            position: 'absolute',
            left: seatX, top: seatY,
            width: 24, height: 24,
            background: 'radial-gradient(ellipse at center, #1a2438 0%, #0e1828 100%)',
            border: '1px solid #2a3a52',
            borderRadius: '50%',
            zIndex: 1,
          }}>
            {/* Chair back (small block facing inward) */}
            <div style={{
              position: 'absolute',
              left: 8 - Math.cos(angle) * 12,
              top: 8 - Math.sin(angle) * 12,
              width: 8, height: 8,
              background: '#1a2438',
              border: '1px solid #2a3a52',
              borderRadius: 2,
            }} />
          </div>
        );
      })}

      {/* CONF room label above */}
      <div style={{
        position: 'absolute', left: x - 100, top: y - 175,
        background: '#02080f', padding: '4px 12px',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11, letterSpacing: 3,
        color: '#5be8f5', fontWeight: 700,
        textShadow: '0 0 8px #5be8f5',
        border: '1px solid #5be8f580',
        width: 200, textAlign: 'center',
      }}>BOARD ROOM</div>
    </>
  );
}

/* ════════ WORKSTATION (just visual desk; agent is rendered separately) ════════ */
function StationDesk({ station }) {
  const z = ZONES[station.zone];
  const zColor = z ? z.color : '#5be8f5';
  const zAccent = z ? z.accent : '#a8f4ff';
  const seed = (station.id || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0);

  return (
    <div style={{
      position: 'absolute',
      left: station.x - 70, top: station.y - 60,
      width: 140, height: 130,
      pointerEvents: 'none',
    }}>
      {/* Holographic info panel above desk */}
      <div style={{
        position: 'absolute', top: 0, left: 10, width: 120, height: 30,
        background: 'rgba(2,8,18,0.6)',
        border: `1px solid ${zAccent}60`,
        borderRadius: 3,
        boxShadow: `0 0 8px ${zAccent}30`,
        padding: 3,
      }}>
        <div style={{
          fontSize: 7, color: zAccent, letterSpacing: 1, fontWeight: 700,
          fontFamily: 'JetBrains Mono, monospace',
        }}>{station.id}</div>
        <MiniSpark seed={seed} color={zAccent} />
      </div>

      {/* Desk surface with monitors */}
      <div style={{
        position: 'absolute', top: 35, left: 5, width: 130, height: 40,
        background: 'linear-gradient(180deg, #1a2438 0%, #0a1424 100%)',
        border: `1px solid ${zColor}80`,
        borderRadius: 2,
        boxShadow: `0 4px 10px rgba(0,0,0,0.5), inset 0 1px 0 ${zAccent}40`,
      }}>
        <div style={{ display: 'flex', height: 30, padding: 3, gap: 3 }}>
          <div style={monitorStyle(zColor)}>
            <MiniSpark seed={seed + 1} color={zAccent} />
          </div>
          <div style={monitorStyle(zColor)}>
            <MiniSpark seed={seed + 7} color={zAccent} kind="bars" />
          </div>
        </div>
        {/* Status LED */}
        <div style={{
          position: 'absolute', top: 2, right: 4,
          width: 4, height: 4, background: '#9be8a4',
          borderRadius: '50%', boxShadow: '0 0 4px #9be8a4',
        }} />
      </div>

      {/* Chair (top-down circle) */}
      <div style={{
        position: 'absolute', top: 80, left: 50, width: 40, height: 28,
        background: 'radial-gradient(ellipse at center, #1a2438 0%, #0e1828 100%)',
        border: '1px solid #2a3a52',
        borderRadius: '50%',
      }}>
        <div style={{
          position: 'absolute', top: -3, left: 5, width: 30, height: 7,
          background: '#1a2438', border: '1px solid #2a3a52',
          borderRadius: '4px 4px 0 0',
        }} />
      </div>
    </div>
  );
}

function MiniSpark({ seed, color, kind }) {
  const pts = useMemo(() => {
    const a = []; let v = 8;
    for (let i = 0; i < 14; i++) {
      const n = ((seed * 41 + i * 17) % 7) - 3;
      v = Math.max(2, Math.min(14, v + n));
      a.push(v);
    }
    return a;
  }, [seed]);
  if (kind === 'bars') {
    return (
      <svg viewBox="0 0 56 18" style={{ width: '100%', height: '100%' }}>
        {pts.map((v, i) => (
          <rect key={i} x={2 + i * 4} y={16 - v} width="3" height={v} fill={color} />
        ))}
      </svg>
    );
  }
  const path = pts.map((v, i) => `${i ? 'L' : 'M'} ${2 + i * 4} ${16 - v}`).join(' ');
  return (
    <svg viewBox="0 0 56 18" style={{ width: '100%', height: '100%' }}>
      <path d={path} fill="none" stroke={color} strokeWidth="0.8" />
    </svg>
  );
}

function monitorStyle(zColor) {
  return {
    flex: 1, height: '100%',
    background: '#020812',
    border: `1px solid ${zColor}`,
    borderRadius: 1,
    padding: 1,
    boxShadow: `0 0 4px ${zColor}40, inset 0 0 3px rgba(0,0,0,0.7)`,
  };
}

/* ════════ WALL MONITOR ════════ */
function WallMonitor({ x, w, h, color, type, label, seed, live }) {
  /* When `live=true`, render a streaming chart instead of the static SVG.
     Picks LiveCandleChart for 'candles', LiveLineChart for 'line', OrderBook for 'book'. */
  let inner;
  if (live && type === 'candles') inner = <LiveCandleChart color={color} count={32} />;
  else if (live && type === 'line') inner = <LiveLineChart color={color} count={48} />;
  else if (live && type === 'book') inner = <OrderBook />;
  else inner = <MiniSpark seed={seed || x} color={color} kind={type === 'bars' ? 'bars' : null} />;

  return (
    <div style={{
      position: 'absolute', left: x, top: 30, width: w, height: h,
      background: 'rgba(2,8,18,0.95)',
      border: `1.5px solid ${color}`,
      borderRadius: 4,
      padding: 6,
      boxShadow: `0 0 16px ${color}40, inset 0 0 10px rgba(0,0,0,0.7)`,
    }}>
      <div style={{ position: 'absolute', inset: 8, top: 18, background: '#04101a', padding: 2 }}>
        {inner}
      </div>
      {label && (
        <div style={{
          position: 'absolute', top: 4, left: 8,
          fontSize: 8, color, letterSpacing: 1,
          fontFamily: 'JetBrains Mono, monospace', zIndex: 2,
          textShadow: `0 0 4px ${color}`,
        }}>{label}</div>
      )}
      {/* Live indicator */}
      {live && (
        <div style={{
          position: 'absolute', top: 4, right: 8, display: 'flex', alignItems: 'center', gap: 4,
          fontSize: 7, color: '#9be8a4', letterSpacing: 1,
          fontFamily: 'JetBrains Mono, monospace',
        }}>
          <span style={{ width: 4, height: 4, background: '#9be8a4',
                          borderRadius: '50%', boxShadow: '0 0 4px #9be8a4',
                          animation: 'holoPulse 1.4s ease-in-out infinite' }} />
          LIVE
        </div>
      )}
    </div>
  );
}

/* ════════ FLOW ARROWS — L1→L2→L3→L4 trade pipeline ════════ */
function FlowArrows({ activeArrow }) {
  const path = (key, d, label, labelPos) => {
    const isActive = activeArrow === key;
    return (
      <g key={key}>
        <path
          d={d}
          stroke={isActive ? '#9be8a4' : '#5be8f5'}
          strokeWidth={isActive ? 3.5 : 2}
          fill="none"
          strokeDasharray="6 4"
          markerEnd={`url(#${isActive ? 'arrActive' : 'arrIdle'})`}
          style={{
            opacity: isActive ? 1 : 0.45,
            filter: isActive ? 'drop-shadow(0 0 8px #9be8a4)' : 'none',
            transition: 'opacity 0.3s, stroke-width 0.3s, filter 0.3s',
            animation: isActive ? 'flowDash 0.6s linear infinite' : 'none',
          }}
        />
        <text x={labelPos.x} y={labelPos.y}
              fill={isActive ? '#9be8a4' : '#5be8f5'}
              fontSize="10" fontFamily="JetBrains Mono"
              style={{
                opacity: isActive ? 1 : 0.6,
                textShadow: isActive ? '0 0 6px #9be8a4' : 'none',
                fontWeight: isActive ? 700 : 400,
                transition: 'opacity 0.3s, text-shadow 0.3s',
              }}>
          {label}
        </text>
      </g>
    );
  };
  return (
    <svg style={{ position: 'absolute', inset: 0, width: 2000, height: 1200, pointerEvents: 'none' }}>
      <defs>
        <marker id="arrIdle" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#5be8f5" />
        </marker>
        <marker id="arrActive" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#9be8a4" />
        </marker>
      </defs>
      {path('l1l2', 'M 500 440 L 560 420', 'FORWARD', { x: 490, y: 432 })}
      {path('l2l3', 'M 770 560 L 770 620', 'EXECUTE', { x: 778, y: 595 })}
      {path('l3l4', 'M 985 720 L 1560 640', 'WRITE PNL', { x: 1100, y: 700 })}
    </svg>
  );
}

/* ════════ ROOM WALLS — neon-bordered enclosures with door gaps ════════ */
function RoomWalls() {
  return (
    <>
      {Object.entries(ROOMS).map(([id, r]) => {
        const z = ZONES[id];
        const accent = z ? z.accent : '#5be8f5';
        const b = r.bounds;
        const d = r.door;
        const gap = 56; // door width
        return (
          <div key={id} style={{
            position: 'absolute',
            left: b.x, top: b.y,
            width: b.w, height: b.h,
            pointerEvents: 'none',
          }}>
            {/* TOP wall (with door gap if door.side==='top') */}
            <Wall side="top"    bounds={b} door={d.side === 'top'    ? d : null} gap={gap} color={accent} />
            <Wall side="bottom" bounds={b} door={d.side === 'bottom' ? d : null} gap={gap} color={accent} />
            <Wall side="left"   bounds={b} door={d.side === 'left'   ? d : null} gap={gap} color={accent} />
            <Wall side="right"  bounds={b} door={d.side === 'right'  ? d : null} gap={gap} color={accent} />
            {/* Door frame glow */}
            <DoorFrame side={d.side} door={d} bounds={b} gap={gap} color={accent} />
          </div>
        );
      })}
    </>
  );
}

function Wall({ side, bounds, door, gap, color }) {
  const T = 5;  // wall thickness
  if (side === 'top' || side === 'bottom') {
    const y = side === 'top' ? 0 : bounds.h - T;
    if (door) {
      const dx = door.x - bounds.x;
      const left = { left: 0, top: y, width: Math.max(0, dx - gap / 2), height: T };
      const right = { left: dx + gap / 2, top: y, width: Math.max(0, bounds.w - dx - gap / 2), height: T };
      return (
        <>
          <div style={{ position: 'absolute', ...left, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />
          <div style={{ position: 'absolute', ...right, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />
        </>
      );
    }
    return <div style={{ position: 'absolute', left: 0, top: y, width: bounds.w, height: T, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />;
  } else {
    const x = side === 'left' ? 0 : bounds.w - T;
    if (door) {
      const dy = door.y - bounds.y;
      const top = { left: x, top: 0, width: T, height: Math.max(0, dy - gap / 2) };
      const bot = { left: x, top: dy + gap / 2, width: T, height: Math.max(0, bounds.h - dy - gap / 2) };
      return (
        <>
          <div style={{ position: 'absolute', ...top, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />
          <div style={{ position: 'absolute', ...bot, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />
        </>
      );
    }
    return <div style={{ position: 'absolute', left: x, top: 0, width: T, height: bounds.h, background: color, opacity: 0.85, boxShadow: `0 0 6px ${color}` }} />;
  }
}

function DoorFrame({ side, door, bounds, gap, color }) {
  /* Glowing floor strip + frame pillars on either side of the doorway */
  const T = 5;
  if (side === 'top' || side === 'bottom') {
    const y = side === 'top' ? 0 : bounds.h - T;
    const dx = door.x - bounds.x;
    return (
      <>
        {/* Floor LED strip across door */}
        <div style={{
          position: 'absolute', left: dx - gap / 2, top: y - 2, width: gap, height: 9,
          background: `linear-gradient(180deg, ${color}, transparent)`,
          boxShadow: `0 0 12px ${color}`,
          opacity: 0.5,
        }} />
        {/* Frame pillars */}
        <div style={{ position: 'absolute', left: dx - gap / 2 - 2, top: y - 4, width: 4, height: 12, background: color, boxShadow: `0 0 8px ${color}` }} />
        <div style={{ position: 'absolute', left: dx + gap / 2 - 2, top: y - 4, width: 4, height: 12, background: color, boxShadow: `0 0 8px ${color}` }} />
      </>
    );
  } else {
    const x = side === 'left' ? 0 : bounds.w - T;
    const dy = door.y - bounds.y;
    return (
      <>
        <div style={{
          position: 'absolute', left: x - 2, top: dy - gap / 2, width: 9, height: gap,
          background: `linear-gradient(90deg, ${color}, transparent)`,
          boxShadow: `0 0 12px ${color}`,
          opacity: 0.5,
        }} />
        <div style={{ position: 'absolute', left: x - 4, top: dy - gap / 2 - 2, width: 12, height: 4, background: color, boxShadow: `0 0 8px ${color}` }} />
        <div style={{ position: 'absolute', left: x - 4, top: dy + gap / 2 - 2, width: 12, height: 4, background: color, boxShadow: `0 0 8px ${color}` }} />
      </>
    );
  }
}

/* ════════ PLANTS — futuristic glow pods ════════ */
function Plant({ x, y, color, kind }) {
  const c = color || '#5fa14b';
  if (kind === 'tall') {
    return (
      <div style={{ position: 'absolute', left: x, top: y, width: 36, height: 60 }}>
        {/* Pot */}
        <div style={{
          position: 'absolute', bottom: 0, left: 6, width: 24, height: 16,
          background: 'linear-gradient(180deg, #1a2438 0%, #0a1424 100%)',
          border: '1px solid #2a3a52',
          borderRadius: '3px 3px 6px 6px',
        }} />
        {/* Stem */}
        <div style={{ position: 'absolute', bottom: 14, left: 17, width: 2, height: 28, background: c, opacity: 0.6 }} />
        {/* Leaves */}
        <div style={{ position: 'absolute', bottom: 36, left: 8, width: 12, height: 14, background: c,
                      clipPath: 'polygon(50% 0%, 100% 60%, 50% 100%, 0 60%)', boxShadow: `0 0 8px ${c}` }} />
        <div style={{ position: 'absolute', bottom: 30, left: 18, width: 10, height: 12, background: c,
                      clipPath: 'polygon(50% 0%, 100% 60%, 50% 100%, 0 60%)', boxShadow: `0 0 6px ${c}` }} />
        <div style={{ position: 'absolute', bottom: 46, left: 14, width: 9, height: 11, background: c,
                      clipPath: 'polygon(50% 0%, 100% 60%, 50% 100%, 0 60%)', boxShadow: `0 0 8px ${c}` }} />
      </div>
    );
  }
  if (kind === 'bonsai') {
    return (
      <div style={{ position: 'absolute', left: x, top: y, width: 38, height: 38 }}>
        <div style={{
          position: 'absolute', bottom: 0, left: 4, width: 30, height: 12,
          background: '#3a2818', border: '1px solid #1a0d04', borderRadius: '4px 4px 8px 8px',
        }} />
        <div style={{ position: 'absolute', bottom: 10, left: 17, width: 4, height: 12, background: '#5a3a18' }} />
        <div style={{
          position: 'absolute', bottom: 20, left: 6, width: 26, height: 14,
          background: `radial-gradient(ellipse at center, ${c} 0%, ${c}80 100%)`,
          borderRadius: '50%', boxShadow: `0 0 10px ${c}`,
        }} />
      </div>
    );
  }
  /* default — pod with glowing core */
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 36, height: 46 }}>
      <div style={{
        position: 'absolute', bottom: 0, left: 8, width: 20, height: 16,
        background: 'linear-gradient(180deg, #1a2438 0%, #0a1424 100%)',
        border: '1px solid #2a3a52',
        borderRadius: '3px 3px 6px 6px',
      }} />
      <div style={{
        position: 'absolute', bottom: 14, left: 4, width: 28, height: 22,
        background: c, opacity: 0.85,
        clipPath: 'polygon(20% 100%, 0 60%, 20% 0, 50% 30%, 80% 0, 100% 60%, 80% 100%)',
        boxShadow: `0 0 12px ${c}`,
      }} />
      {/* Glow core */}
      <div style={{
        position: 'absolute', bottom: 24, left: 14, width: 8, height: 8,
        background: '#fff', borderRadius: '50%',
        boxShadow: `0 0 8px ${c}, 0 0 16px ${c}`,
        animation: 'holoPulse 3s ease-in-out infinite',
      }} />
    </div>
  );
}

/* ════════ LIVE CANDLE CHART — updates every ~700ms with new candle ════════ */
function LiveCandleChart({ color, count = 24 }) {
  const [candles, setCandles] = useState(() => {
    const arr = [];
    let v = 50;
    for (let i = 0; i < count; i++) {
      const open = v;
      v += (Math.random() - 0.5) * 10;
      const close = v;
      const high = Math.max(open, close) + Math.random() * 4;
      const low = Math.min(open, close) - Math.random() * 4;
      arr.push({ open, close, high, low });
    }
    return arr;
  });
  useEffect(() => {
    const id = setInterval(() => {
      setCandles((prev) => {
        const last = prev[prev.length - 1];
        const open = last.close;
        const close = open + (Math.random() - 0.5) * 12;
        const high = Math.max(open, close) + Math.random() * 4;
        const low = Math.min(open, close) - Math.random() * 4;
        return [...prev.slice(1), { open, close, high, low }];
      });
    }, 700);
    return () => clearInterval(id);
  }, []);
  const W = 100, H = 60;
  const allVals = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...allVals), max = Math.max(...allVals);
  const range = max - min || 1;
  const cw = (W - 4) / count;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <line key={p} x1={0} x2={W} y1={p * H} y2={p * H} stroke={color} opacity="0.08" strokeWidth="0.3" />
      ))}
      {candles.map((c, i) => {
        const up = c.close >= c.open;
        const fill = up ? '#9be8a4' : '#ff8a6c';
        const x = 2 + i * cw;
        const yHigh = ((max - c.high) / range) * (H - 4) + 2;
        const yLow = ((max - c.low) / range) * (H - 4) + 2;
        const yOpen = ((max - c.open) / range) * (H - 4) + 2;
        const yClose = ((max - c.close) / range) * (H - 4) + 2;
        const bodyTop = Math.min(yOpen, yClose);
        const bodyH = Math.max(1, Math.abs(yOpen - yClose));
        return (
          <g key={i}>
            <line x1={x + cw / 2} x2={x + cw / 2} y1={yHigh} y2={yLow}
                  stroke={fill} strokeWidth="0.5" />
            <rect x={x + cw * 0.15} y={bodyTop} width={cw * 0.7} height={bodyH} fill={fill} />
          </g>
        );
      })}
    </svg>
  );
}

/* ════════ LIVE LINE CHART — streaming ticks ════════ */
function LiveLineChart({ color, count = 32 }) {
  const [pts, setPts] = useState(() => {
    const arr = []; let v = 8;
    for (let i = 0; i < count; i++) {
      v = Math.max(2, Math.min(14, v + (Math.random() - 0.5) * 4));
      arr.push(v);
    }
    return arr;
  });
  useEffect(() => {
    const id = setInterval(() => {
      setPts((p) => {
        const v = Math.max(2, Math.min(14, p[p.length - 1] + (Math.random() - 0.5) * 4));
        return [...p.slice(1), v];
      });
    }, 500);
    return () => clearInterval(id);
  }, []);
  const path = pts.map((v, i) => `${i ? 'L' : 'M'} ${(i * (100 / count)).toFixed(1)} ${16 - v}`).join(' ');
  const area = `${path} L ${100 - (100 / count)} 17 L 0 17 Z`;
  return (
    <svg viewBox="0 0 100 18" preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
      <path d={area} fill={color} opacity="0.25" />
      <path d={path} fill="none" stroke={color} strokeWidth="0.6" />
      <circle cx={100 - (100 / count)} cy={16 - pts[pts.length - 1]} r="0.8" fill="#fff" />
    </svg>
  );
}

/* ════════ ORDER BOOK panel (visual broker feel) ════════ */
function OrderBook() {
  const [book, setBook] = useState(() => generateBook());
  useEffect(() => {
    const id = setInterval(() => setBook(generateBook()), 1200);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
      fontFamily: 'JetBrains Mono, monospace', fontSize: 7, color: '#cfe2f4',
      padding: 2,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    color: '#5be8f5', fontSize: 6, letterSpacing: 1, marginBottom: 1 }}>
        <span>BID</span><span>SIZE</span><span>ASK</span>
      </div>
      {book.map((row, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', height: 7 }}>
          <span style={{ color: '#9be8a4' }}>{row.bid}</span>
          <span style={{ color: '#cfe2f4' }}>{row.size}</span>
          <span style={{ color: '#ff8a6c' }}>{row.ask}</span>
        </div>
      ))}
    </div>
  );
}

function generateBook() {
  const arr = [];
  for (let i = 0; i < 6; i++) {
    arr.push({
      bid: (1.084 - i * 0.0001).toFixed(4),
      size: Math.floor(Math.random() * 900 + 100),
      ask: (1.0843 + i * 0.0001).toFixed(4),
    });
  }
  return arr;
}

/* ════════ DRONES ════════ */
function Drone({ pathId, color }) {
  return (
    <div style={{
      position: 'absolute',
      width: 24, height: 12,
      animation: `${pathId} 18s linear infinite`,
      pointerEvents: 'none',
      zIndex: 8,
    }}>
      <div style={{
        position: 'relative', width: 24, height: 12,
      }}>
        {/* Body */}
        <div style={{
          position: 'absolute', left: 6, top: 2, width: 12, height: 6,
          background: '#1a2840', border: `1px solid ${color}`,
          borderRadius: 2, boxShadow: `0 0 8px ${color}`,
        }} />
        {/* Propellers */}
        <div style={{
          position: 'absolute', left: 0, top: 4, width: 8, height: 2,
          background: color, opacity: 0.6,
        }} />
        <div style={{
          position: 'absolute', right: 0, top: 4, width: 8, height: 2,
          background: color, opacity: 0.6,
        }} />
        {/* LED */}
        <div style={{
          position: 'absolute', left: 11, top: 4, width: 2, height: 2,
          background: '#fff', borderRadius: '50%',
          boxShadow: `0 0 4px ${color}`,
        }} />
        {/* Shadow on floor */}
        <div style={{
          position: 'absolute', left: 4, top: 28, width: 16, height: 4,
          background: 'rgba(0,0,0,0.3)', borderRadius: '50%',
          filter: 'blur(2px)',
        }} />
      </div>
    </div>
  );
}

/* ════════ DATA WALL (scrolling tape) ════════ */
function DataTape({ y }) {
  const items = ['EURUSD 1.0842 ↑', 'SPY 511.23 +0.4%', 'BTC 67241 ↑', 'CL 78.42', 'NVDA 134.5 ↑↑', 'NQ 18420', 'GOLD 2391 ↑', 'VIX 14.2 ↓', '10Y 4.21%'];
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, top: y, height: 18,
      background: '#02080f',
      borderTop: '1px solid #1f3050',
      borderBottom: '1px solid #1f3050',
      overflow: 'hidden',
      display: 'flex',
      alignItems: 'center',
      zIndex: 3,
    }}>
      <div style={{
        display: 'flex',
        gap: 32,
        animation: 'tapeScroll 60s linear infinite',
        whiteSpace: 'nowrap',
        paddingLeft: '100%',
      }}>
        {Array.from({ length: 4 }).flatMap((_, j) =>
          items.map((item, i) => (
            <span key={`${j}-${i}`} style={{
              fontSize: 11, letterSpacing: 1,
              color: item.includes('↑') ? '#9be8a4' : item.includes('↓') ? '#ff8a6c' : '#5be8f5',
              fontFamily: 'JetBrains Mono, monospace',
              fontWeight: 600,
            }}>{item}</span>
          ))
        )}
      </div>
    </div>
  );
}

/* ════════ MAIN APP ════════ */
function OfficeV4App() {
  const traders = useMemo(() => {
    const m = {};
    (window.SPRITES_V3.list || []).forEach((t) => (m[t.id] = t));
    return m;
  }, []);

  /* Per-agent tempo — some agents change activity more often than others */
  const tempos = useMemo(() => {
    const t = {};
    STATIONS.forEach((s, i) => {
      // Tempo 0.6 — 1.4 (multiplier on activity duration; lower = restless)
      t[s.id] = 0.6 + ((s.id.charCodeAt(0) * 7 + i * 13) % 80) / 100;
    });
    return t;
  }, []);

  /* Agent state: position + waypoints + activity + facing + per-agent step timing */
  const seatMgr = useRef(new SeatManager(CONF_SEATS));
  const [agents, setAgents] = useState(() => {
    const init = {};
    STATIONS.forEach((s, i) => {
      init[s.id] = {
        x: s.x, y: s.y,
        activity: 'desk',
        activityEndsAt: Date.now() + 2000 + Math.random() * 8000,
        target: null,
        facing: Math.random() < 0.5 ? 'left' : 'right',
        isMoving: false,
        waypoints: [],
        wIdx: 0,
        stepPhase: i % 2,
        /* Per-agent walk cadence + size so the floor doesn't pulse in lockstep */
        stepInterval: 180 + Math.floor(Math.random() * 180),  // 180–360ms per step
        stepSize: 22 + Math.floor(Math.random() * 14),         // 22–35px per step
        lastStepAt: Date.now() + Math.floor(Math.random() * 400),
      };
    });
    return init;
  });

  const [bubbles, setBubbles] = useState({});
  const [fireKeys, setFireKeys] = useState({});
  const [activeId, setActiveId] = useState(null);

  /* Activity scheduler — picks new destinations and builds paths through doors.
     Caps concurrent movers at MAX_MOVERS so the floor doesn't churn. */
  useEffect(() => {
    const MAX_MOVERS = 5;
    const id = setInterval(() => {
      const now = Date.now();
      setAgents((prev) => {
        const next = { ...prev };
        let changed = false;
        /* Count agents currently in motion */
        let activeMovers = 0;
        for (const k of Object.keys(prev)) if (prev[k].isMoving) activeMovers++;

        for (const agentId of Object.keys(next)) {
          const a = next[agentId];
          if (a.isMoving) continue; // don't override mid-trip
          if (a.activityEndsAt > now) continue;

          /* Release conf seat if leaving */
          if (a.activity === 'conference') seatMgr.current.release(agentId);

          const newAct = pickActivity(a.activity, agentId, seatMgr.current);
          let tx, ty;
          if (newAct.kind === 'desk') {
            const home = STATIONS_BY_ID[agentId];
            tx = home.x; ty = home.y;
          } else if (newAct.target) {
            tx = newAct.target.x; ty = newAct.target.y;
          } else {
            tx = a.x; ty = a.y;
          }
          const path = buildPath(a.x, a.y, tx, ty);
          const moving = !(path.length === 1 && path[0].x === a.x && path[0].y === a.y);

          /* Concurrency cap — if too many are walking, defer this agent */
          if (moving && activeMovers >= MAX_MOVERS) {
            next[agentId] = { ...a, activityEndsAt: now + 1500 + Math.random() * 3000 };
            /* Give back the seat we claimed since we're not going */
            if (newAct.kind === 'conference' && newAct.target) {
              seatMgr.current.release(agentId);
            }
            changed = true;
            continue;
          }

          const tempo = tempos[agentId] || 1;
          /* Long dwell at desk so the floor stays calm; short away dwell so
             excursions don't drag on. */
          const dwell = newAct.kind === 'desk'
            ? (12000 + Math.random() * 22000) * tempo   // 12–34s at desk
            : (3500 + Math.random() * 7000)  * tempo;  // 3.5–10.5s away
          let facing = a.facing;
          if (moving) {
            const first = path[0];
            if (Math.abs(first.x - a.x) > 4) facing = first.x > a.x ? 'right' : 'left';
            activeMovers++;
          }
          next[agentId] = {
            ...a,
            activity: newAct.kind,
            activityEndsAt: now + dwell,
            target: newAct.target,
            facing,
            isMoving: moving,
            waypoints: path,
            wIdx: 0,
            /* Stagger start so multiple agents triggering at the same tick
               don't take their first step on the same frame */
            lastStepAt: now + Math.floor(Math.random() * 200),
          };
          changed = true;
        }
        return changed ? next : prev;
      });
    }, 600);
    return () => clearInterval(id);
  }, [tempos]);

  /* Movement tick — fine-grained (80ms) so each agent steps on its own
     stepInterval, NOT in lockstep with everyone else. */
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      setAgents((prev) => {
        let changed = false;
        const next = { ...prev };
        for (const agentId of Object.keys(next)) {
          const a = next[agentId];
          if (!a.isMoving) continue;
          if (now - a.lastStepAt < a.stepInterval) continue;

          const wp = a.waypoints[a.wIdx];
          if (!wp) {
            next[agentId] = { ...a, isMoving: false, lastStepAt: now };
            changed = true;
            continue;
          }
          const STEP = a.stepSize;
          const dx = wp.x - a.x;
          const dy = wp.y - a.y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          if (dist < STEP) {
            const nextIdx = a.wIdx + 1;
            if (nextIdx >= a.waypoints.length) {
              next[agentId] = { ...a, x: wp.x, y: wp.y, isMoving: false,
                                wIdx: nextIdx, lastStepAt: now };
            } else {
              const nxt = a.waypoints[nextIdx];
              let facing = a.facing;
              if (Math.abs(nxt.x - wp.x) > 4) facing = nxt.x > wp.x ? 'right' : 'left';
              next[agentId] = { ...a, x: wp.x, y: wp.y, wIdx: nextIdx, facing,
                                stepPhase: 1 - a.stepPhase, lastStepAt: now };
            }
          } else {
            const nx = a.x + (dx / dist) * STEP;
            const ny = a.y + (dy / dist) * STEP;
            let facing = a.facing;
            if (Math.abs(dx) > 4) facing = dx > 0 ? 'right' : 'left';
            next[agentId] = { ...a, x: nx, y: ny, facing,
                              stepPhase: 1 - a.stepPhase, lastStepAt: now };
          }
          changed = true;
        }
        return changed ? next : prev;
      });
    }, 80);
    return () => clearInterval(id);
  }, []);

  /* Bubble generator — every 1.8s, ~30% chance per agent to emit */
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      setBubbles((prev) => {
        const next = {};
        // Keep non-expired
        for (const [aid, b] of Object.entries(prev)) {
          if (b.until > now) next[aid] = b;
        }
        // Maybe add new ones
        for (const agentId of Object.keys(agents)) {
          if (next[agentId]) continue;
          if (Math.random() < 0.18) {
            const ag = agents[agentId];
            const pool = DIALOG[ag.activity] || DIALOG.desk;
            const isThought = Math.random() < 0.35;
            const texts = isThought ? pool.thought : pool.speech;
            if (!texts || texts.length === 0) continue;
            next[agentId] = {
              text: texts[Math.floor(Math.random() * texts.length)],
              kind: isThought ? 'thought' : 'speech',
              until: now + 4500 + Math.random() * 1500,
            };
          }
        }
        return next;
      });
    }, 1800);
    return () => clearInterval(id);
  }, [agents]);

  /* Power firing — auto-cycle one random agent per ~1.6s */
  const [autoCycle, setAutoCycle] = useState(true);
  useEffect(() => {
    if (!autoCycle) return;
    const id = setInterval(() => {
      const ids = Object.keys(agents);
      const aid = ids[Math.floor(Math.random() * ids.length)];
      setActiveId(aid);
      setFireKeys((prev) => ({ ...prev, [aid]: (prev[aid] || 0) + 1 }));
    }, 1700);
    return () => clearInterval(id);
  }, [autoCycle, agents]);

  /* TRADE FLOW EVENTS — chains L1 → L2 → L3 risk → L3 exec → L4 pnl,
     firing each agent's power + bubble in sequence, lighting up flow arrows.
     Simulates real trade lifecycle. */
  const [activeArrow, setActiveArrow] = useState(null);
  const [tradeLog, setTradeLog] = useState([]);

  const runTradeFlow = useCallback(() => {
    const L1_AGENTS = STATIONS.filter((s) => s.zone === 'l1').map((s) => s.id);
    const L2_AGENTS = STATIONS.filter((s) => s.zone === 'l2').map((s) => s.id);
    const tickers = ['EURUSD', 'SPY', 'NQ', 'BTC', 'NVDA', 'GOLD', 'CL', 'AAPL'];
    const directions = ['buy', 'sell'];
    const ticker = tickers[Math.floor(Math.random() * tickers.length)];
    const dir = directions[Math.floor(Math.random() * 2)];
    const size = (Math.floor(Math.random() * 9) + 1) * 100;
    const pnl = (Math.random() * 0.8 - 0.1).toFixed(2);
    const l1id = L1_AGENTS[Math.floor(Math.random() * L1_AGENTS.length)];
    const l2id = L2_AGENTS[Math.floor(Math.random() * L2_AGENTS.length)];

    const tradeId = `T${Math.floor(Math.random() * 9000 + 1000)}`;

    const steps = [
      { agentId: l1id,    bubble: `↑ sinal ${ticker}!`,     arrow: 'l1l2', delay: 0 },
      { agentId: l2id,    bubble: `analisar ${ticker}…`,    arrow: 'l2l3', delay: 1400 },
      { agentId: 'visor', bubble: `risk OK ✓`,              arrow: null,   delay: 2800 },
      { agentId: 'aegis', bubble: `${dir} ${ticker} ${size}`, arrow: 'l3l4', delay: 4000 },
      { agentId: 'scribe',bubble: `PnL ${pnl >= 0 ? '+' : ''}${pnl}%`, arrow: null, delay: 5400 },
    ];

    setTradeLog((prev) => [{ id: tradeId, ticker, dir, size, ts: Date.now() }, ...prev].slice(0, 6));

    steps.forEach((s) => {
      setTimeout(() => {
        // Fire power animation
        setFireKeys((p) => ({ ...p, [s.agentId]: (p[s.agentId] || 0) + 1 }));
        // Set special trade bubble
        setBubbles((p) => ({
          ...p,
          [s.agentId]: {
            text: s.bubble, kind: 'speech', until: Date.now() + 3200, trade: true,
          },
        }));
        // Activate flow arrow
        if (s.arrow) {
          setActiveArrow(s.arrow);
          setTimeout(() => setActiveArrow((cur) => (cur === s.arrow ? null : cur)), 1400);
        }
      }, s.delay);
    });
  }, []);

  useEffect(() => {
    // First flow after 2s, then every 10–18s
    const kickoff = setTimeout(runTradeFlow, 2000);
    const id = setInterval(() => {
      if (Math.random() < 0.85) runTradeFlow();
    }, 11000 + Math.random() * 4000);
    return () => { clearTimeout(kickoff); clearInterval(id); };
  }, [runTradeFlow]);

  /* ════════ BIG MEETING — periodic event that gathers 6-8 agents at the
     conference table for a long session (20-35s). Bypasses the MAX_MOVERS
     cap since it's a coordinated event. Other agents keep working. */
  const [bigMeeting, setBigMeeting] = useState(null);

  const startBigMeeting = useCallback(() => {
    /* Reset conference seat ownership so we can claim them freshly */
    seatMgr.current = new SeatManager(CONF_SEATS);

    /* Pick eligible agents (not wall-mounted, not already at conf) */
    setAgents((prev) => {
      const ids = Object.keys(prev).filter((id) => {
        const st = STATIONS_BY_ID[id];
        return st && st.zone !== 'wall';
      });
      const shuffled = [...ids].sort(() => Math.random() - 0.5);
      const pickCount = 6 + Math.floor(Math.random() * 3); // 6–8
      const chosen = shuffled.slice(0, pickCount);

      const duration = 20000 + Math.random() * 15000;     // 20–35s
      const endsAt = Date.now() + duration;
      setBigMeeting({ agentIds: chosen, until: endsAt });

      const next = { ...prev };
      chosen.forEach((id, i) => {
        const seat = seatMgr.current.claim(id);
        if (!seat) return;
        const a = prev[id];
        const path = buildPath(a.x, a.y, seat.x, seat.y);
        const moving = !(path.length === 1 && path[0].x === a.x && path[0].y === a.y);
        let facing = a.facing;
        if (moving) {
          const first = path[0];
          if (Math.abs(first.x - a.x) > 4) facing = first.x > a.x ? 'right' : 'left';
        }
        next[id] = {
          ...a,
          activity: 'conference',
          target: seat,
          activityEndsAt: endsAt,
          waypoints: path,
          wIdx: 0,
          isMoving: moving,
          facing,
          /* Stagger: ~700ms between each agent leaving so they don't all walk in lockstep */
          lastStepAt: Date.now() + i * 700,
        };
      });
      return next;
    });
  }, []);

  useEffect(() => {
    /* First meeting after 35-60s, then every 90-180s with 50% trigger chance */
    const kickoff = setTimeout(startBigMeeting, 35000 + Math.random() * 25000);
    const id = setInterval(() => {
      if (Math.random() < 0.5) startBigMeeting();
    }, 90000 + Math.random() * 90000);
    return () => { clearTimeout(kickoff); clearInterval(id); };
  }, [startBigMeeting]);

  const fire = (id) => {
    setActiveId(id);
    setFireKeys((prev) => ({ ...prev, [id]: (prev[id] || 0) + 1 }));
  };

  /* Fit-to-viewport */
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const update = () => {
      const w = window.innerWidth;
      const h = window.innerHeight - 50;
      setScale(Math.min(w / 2000, h / 1200, 1));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  return (
    <div style={appStyles.root}>
      {/* CSS keyframes injected once */}
      <style>{`
        /* Walk cycle — sway + bob to feel like footsteps, no rotation
           because it makes pixel sprites look melted. */
        @keyframes agentWalk {
          0%   { transform: translate(0, 0); }
          25%  { transform: translate(-1px, -3px); }
          50%  { transform: translate(0, 0); }
          75%  { transform: translate(1px, -3px); }
          100% { transform: translate(0, 0); }
        }
        /* Slight bouncy shadow under walking agents */
        @keyframes shadowPulse {
          0%, 100% { opacity: 0.45; transform: scaleX(1); }
          50%      { opacity: 0.25; transform: scaleX(0.85); }
        }
        @keyframes bubbleIn {
          0%   { opacity: 0; transform: translateX(-50%) translateY(6px) scale(0.85); }
          100% { opacity: 1; transform: translateX(-50%) translateY(0) scale(1); }
        }
        @keyframes tapeScroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-100%); }
        }
        @keyframes dronePath1 {
          0%   { transform: translate(60px, 220px); }
          25%  { transform: translate(900px, 280px); }
          50%  { transform: translate(1500px, 220px); }
          75%  { transform: translate(900px, 160px); }
          100% { transform: translate(60px, 220px); }
        }
        @keyframes dronePath2 {
          0%   { transform: translate(1800px, 230px); }
          25%  { transform: translate(1200px, 300px); }
          50%  { transform: translate(600px, 250px); }
          75%  { transform: translate(1200px, 180px); }
          100% { transform: translate(1800px, 230px); }
        }
        @keyframes holoPulse {
          0%, 100% { opacity: 0.18; }
          50%      { opacity: 0.32; }
        }
        /* Trade flow arrow pulse — when a stage fires, the arrow lights up */
        @keyframes arrowFlash {
          0%   { opacity: 0.3; filter: drop-shadow(0 0 0 transparent); }
          50%  { opacity: 1.0; filter: drop-shadow(0 0 8px #5be8f5); }
          100% { opacity: 0.3; filter: drop-shadow(0 0 0 transparent); }
        }
        @keyframes flowDash {
          0%   { stroke-dashoffset: 0; }
          100% { stroke-dashoffset: -28; }
        }
      `}</style>

      {/* Top toolbar */}
      <div style={appStyles.toolbar}>
        <div style={appStyles.brand}>
          <span style={appStyles.dot} />
          MEKKA TRADING · OFFICE v4 · LIVE FLOOR
        </div>
        <div style={appStyles.toolRight}>
          <span style={appStyles.muted}>{STATIONS.length} agentes</span>
          <span style={appStyles.muted}>· conf room · drones · bubbles ativos</span>
          <button
            onClick={() => setAutoCycle((v) => !v)}
            style={{ ...appStyles.btn, color: autoCycle ? '#9be8a4' : '#6e7c8c' }}
          >{autoCycle ? '◉ powers auto' : '○ powers auto'}</button>
        </div>
      </div>

      <div style={appStyles.stageWrap}>
        <div style={{ ...appStyles.stage, transform: `scale(${scale})` }}>
          {/* Layered background */}
          <div style={appStyles.wallStrip} />
          <div style={appStyles.floorGrid} />
          <div style={appStyles.floorGlow} />

          {/* Top wall — 8 monitors (mix of live and static) */}
          <WallMonitor x={30}   w={170} h={130} color="#3aaad6" type="line"    label="P&L · LIVE" live seed={1} />
          <WallMonitor x={215}  w={100} h={130} color="#3aaad6" type="book"    label="ORDER BOOK" live seed={2} />
          <WallMonitor x={330}  w={620} h={130} color="#5be8f5" type="candles" label="MAIN BOARD · BLACKPANTHER" live seed={3} />
          <WallMonitor x={965}  w={140} h={130} color="#a878e8" type="line"    label="STRAT" live seed={4} />
          <WallMonitor x={1120} w={130} h={130} color="#e89a3a" type="bars"    label="RISK" seed={5} />
          <WallMonitor x={1265} w={140} h={130} color="#5be8f5" type="line"    label="BOARD" live seed={6} />
          <WallMonitor x={1420} w={150} h={130} color="#5fa14b" type="line"    label="L4" live seed={7} />
          <WallMonitor x={1585} w={385} h={130} color="#5fa14b" type="candles" label="DAILY PNL · SCRIBE" live seed={8} />

          {/* Live data tape under wall */}
          <DataTape y={170} />

          {/* Cable trays */}
          <div style={{ ...appStyles.cableTray, top: 210 }} />
          <div style={{ ...appStyles.cableTray, top: 540 }} />

          {/* Zone boxes (not conf — conf is its own component) */}
          {['l1', 'l2', 'l3', 'l4'].map((key) => {
            const z = ZONES[key];
            return (
              <div key={key} style={{
                position: 'absolute',
                left: z.x, top: z.y, width: z.w, height: z.h,
                background: `linear-gradient(180deg, rgba(${hexToRgb(z.accent)},0.04) 0%, transparent 100%)`,
                border: `1px dashed ${z.accent}40`,
                borderRadius: 6,
                pointerEvents: 'none',
              }}>
                <div style={{
                  position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                  background: `linear-gradient(90deg, transparent, ${z.accent}, transparent)`,
                  boxShadow: `0 0 12px ${z.accent}`,
                }} />
                <div style={{
                  position: 'absolute', top: -12, left: 16,
                  background: '#02080f', padding: '2px 10px',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11, letterSpacing: 3,
                  color: z.accent, fontWeight: 700,
                  textShadow: `0 0 8px ${z.accent}`,
                  border: `1px solid ${z.accent}80`,
                }}>{z.label}</div>
              </div>
            );
          })}

          {/* Room walls + door frames */}
          <RoomWalls />

          {/* Futuristic plants scattered around */}
          <Plant x={460}  y={300} color="#5fa14b" kind="tall" />
          <Plant x={460}  y={860} color="#5fa14b" kind="tall" />
          <Plant x={990}  y={300} color="#9be8a4" kind="pod" />
          <Plant x={990}  y={900} color="#a878e8" kind="bonsai" />
          <Plant x={1540} y={300} color="#5fa14b" kind="tall" />
          <Plant x={1540} y={900} color="#5fa14b" kind="tall" />
          <Plant x={510}  y={930} color="#a878e8" kind="pod" />
          <Plant x={950}  y={930} color="#9be8a4" kind="bonsai" />
          <Plant x={1500} y={930} color="#5fa14b" kind="pod" />
          <Plant x={1960} y={300} color="#9be8a4" kind="bonsai" />
          <Plant x={50}   y={290} color="#5fa14b" kind="pod" />
          <Plant x={1960} y={900} color="#5fa14b" kind="tall" />

          {/* Flow arrows L1→L2→L3→L4 — brighten when trade flow stage fires */}
          <FlowArrows activeArrow={activeArrow} />

          {/* Holographic floor projection (between zones) */}
          <div style={{
            position: 'absolute', left: 470, top: 580, width: 60, height: 360,
            background: 'repeating-linear-gradient(45deg, rgba(91,232,245,0.18) 0 6px, transparent 6px 12px)',
            animation: 'holoPulse 3s ease-in-out infinite',
            pointerEvents: 'none',
          }} />
          <div style={{
            position: 'absolute', left: 990, top: 320, width: 22, height: 620,
            background: 'repeating-linear-gradient(0deg, rgba(91,232,245,0.18) 0 6px, transparent 6px 12px)',
            animation: 'holoPulse 4s ease-in-out infinite',
            pointerEvents: 'none',
          }} />

          {/* Conference table (centerpiece) */}
          <ConferenceTable x={CONF_CENTER.x} y={CONF_CENTER.y} />

          {/* Stations (visual desks) */}
          {STATIONS.map((s) => <StationDesk key={s.id} station={s} />)}

          {/* Patrolling drones */}
          <Drone pathId="dronePath1" color="#5be8f5" />
          <Drone pathId="dronePath2" color="#a878e8" />

          {/* Agents (positioned absolutely, CSS-animated to target) */}
          {Object.keys(agents).map((agentId) => {
            const trader = traders[agentId];
            if (!trader) return null;
            return (
              <Agent
                key={agentId}
                trader={trader}
                state={agents[agentId]}
                fireKey={fireKeys[agentId] || 0}
                bubble={bubbles[agentId]}
                onClick={() => fire(agentId)}
              />
            );
          })}

          {/* Amenities — dense bottom row (corridor below all rooms) */}
          <CoffeeBar      x={10}   y={970} />
          <VendingMachine x={290}  y={970} />
          <LockerBank     x={360}  y={974} count={4} color="#5be8f5" />
          <ServerRack     x={478}  y={980} label="SRV-01" />
          <ServerRack     x={556}  y={980} label="SRV-02" />
          <ServerTower    x={636}  y={970} label="CORE-A" />
          <ServerTower    x={702}  y={970} label="CORE-B" status="warn" />
          <Lounge         x={780}  y={970} count={3} />
          <HoloWallPanel  x={1130} y={968} color="#a878e8" label="STRAT" />
          <TrashBin       x={1210} y={1018} />
          <Printer        x={1240} y={980} />
          <HoloWallPanel  x={1340} y={968} color="#e89a3a" label="RISK" />
          <LockerBank     x={1430} y={974} count={3} color="#5fa14b" />
          <ServerTower    x={1520} y={970} label="QUANT" />
          <HoloWallPanel  x={1590} y={968} color="#5fa14b" label="L4" />
          <TrashBin       x={1690} y={1018} />
          <Cooler         x={1720} y={980} />
          <VendingMachine x={1820} y={970} />
          <TrashBin       x={1900} y={1018} />

          {/* In-room furniture */}
          {/* L1 — lockers along the bottom interior wall + whiteboard */}
          <Whiteboard     x={40}   y={760} />
          <LockerBank     x={140}  y={780} count={3} color="#5be8f5" />
          <TrashBin       x={460}  y={840} />
          {/* L2 — whiteboard + holo panel */}
          <Whiteboard     x={540}  y={480} />
          {/* L3 — server rack + lockers */}
          <ServerTower    x={930}  y={620} label="EXEC-01" />
          <LockerBank     x={540}  y={830} count={2} color="#e89a3a" />
          {/* Conf — holo briefing panel */}
          <HoloWallPanel  x={1020} y={340} color="#5be8f5" label="AGENDA" />
          <HoloWallPanel  x={1450} y={340} color="#a8f4ff" label="KPI" />
          {/* L4 — lockers along bottom + server */}
          <LockerBank     x={1580} y={830} count={3} color="#5fa14b" />
          <ServerTower    x={1940} y={830} label="L4-SRV" />
          <Whiteboard     x={1700} y={460} />

          {/* Big-meeting banner — appears during the 20-35s scheduled board meeting */}
          {bigMeeting && bigMeeting.until > Date.now() && (
            <div style={{
              position: 'absolute', top: 200, left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(91,232,245,0.12)',
              border: '2px solid #5be8f5',
              padding: '8px 28px',
              color: '#5be8f5',
              fontSize: 13, letterSpacing: 4, fontWeight: 700,
              textShadow: '0 0 8px #5be8f5',
              boxShadow: '0 0 24px rgba(91,232,245,0.45)',
              fontFamily: 'JetBrains Mono, monospace',
              zIndex: 50,
              backdropFilter: 'blur(2px)',
            }}>
              ◉ BOARD MEETING IN PROGRESS · {bigMeeting.agentIds.length} AGENTS
            </div>
          )}

          {/* Bottom status bar */}
          <div style={appStyles.statusBar}>
            <span style={{ color: '#5be8f5', fontWeight: 700 }}>L1 → L2 → L3 → L4</span>
            <span style={{ color: '#9be8a4' }}>{Object.keys(agents).length} agents · live floor</span>
            <span style={{ color: '#6e8aa8' }}>clica em qualquer agente pra acionar poder</span>
            <span style={{ color: '#ffd84a' }}>◉ SYS · OK · {new Date().toTimeString().slice(0, 5)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ════════ Furniture components ════════ */
function CoffeeBar({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 270, height: 90 }}>
      <div style={{
        width: 270, height: 60,
        background: 'linear-gradient(180deg, #1a2438 0%, #0e1828 100%)',
        border: '1px solid #d4a834',
        borderRadius: '4px 4px 0 0',
        boxShadow: '0 0 14px rgba(212,168,52,0.25)',
        position: 'relative',
      }}>
        {/* Espresso machine */}
        <div style={{ position: 'absolute', top: 8, left: 16, width: 28, height: 42,
                      background: '#3a2818', border: '1px solid #5a3a18' }}>
          <div style={{ position: 'absolute', top: 12, left: 6, width: 16, height: 8,
                        background: '#d4a834' }} />
          <div style={{ position: 'absolute', top: 24, left: 9, width: 10, height: 4,
                        background: '#1a0a04' }} />
        </div>
        {/* Cups row */}
        {[60, 78, 96, 114].map((cx) => (
          <div key={cx} style={{ position: 'absolute', top: 32, left: cx, width: 12, height: 18,
                                  background: '#f0e8d4', border: '1px solid #a8a098',
                                  borderRadius: '0 0 4px 4px' }}>
            <div style={{ width: '100%', height: 3, background: '#7a4a18' }} />
          </div>
        ))}
        {/* Glass jars */}
        <div style={{ position: 'absolute', top: 12, left: 168, width: 22, height: 38,
                      background: 'rgba(91,232,245,0.2)', border: '1px solid #5be8f580' }} />
        <div style={{ position: 'absolute', top: 12, left: 198, width: 22, height: 38,
                      background: 'rgba(155,232,164,0.2)', border: '1px solid #9be8a480' }} />
        <div style={{ position: 'absolute', top: 12, left: 228, width: 22, height: 38,
                      background: 'rgba(255,138,108,0.2)', border: '1px solid #ff8a6c80' }} />
      </div>
      <div style={{
        fontSize: 10, letterSpacing: 2, color: '#d4a834',
        textAlign: 'center', marginTop: 4,
        fontFamily: 'JetBrains Mono, monospace',
        textShadow: '0 0 4px #d4a834',
      }}>☕ COFFEE BAR</div>
    </div>
  );
}

function Lounge({ x, y, count = 5 }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: count * 112, height: 90 }}>
      <div style={{ display: 'flex', gap: 12, justifyContent: 'space-around' }}>
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} style={{
            width: 100, height: 50,
            background: 'radial-gradient(ellipse at top, #1a2438 0%, #0e1828 100%)',
            border: '1px solid #2a3a52',
            borderRadius: '6px 6px 16px 16px',
            position: 'relative',
            boxShadow: '0 4px 8px rgba(0,0,0,0.4)',
          }}>
            <div style={{ position: 'absolute', top: -3, left: 10, width: 80, height: 14,
                          background: '#1a2438', border: '1px solid #2a3a52',
                          borderRadius: '8px 8px 0 0' }} />
          </div>
        ))}
      </div>
      <div style={{
        fontSize: 10, letterSpacing: 2, color: '#9be8a4',
        textAlign: 'center', marginTop: 6,
        fontFamily: 'JetBrains Mono, monospace',
      }}>LOUNGE</div>
    </div>
  );
}

function ServerRack({ x, y, label }) {
  return (
    <div style={{
      position: 'absolute', left: x, top: y, width: 70, height: 90,
      background: '#06101c',
      border: '1px solid #3a5278',
      borderRadius: 2,
      padding: 4,
      boxShadow: '0 0 10px rgba(58,138,214,0.2)',
    }}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={{
          height: 12, marginBottom: 2,
          background: '#0a1828', border: '1px solid #2a3a52',
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 3,
        }}>
          <div style={{ width: 3, height: 3, background: '#9be8a4',
                        borderRadius: '50%', marginRight: 2,
                        boxShadow: '0 0 3px #9be8a4' }} />
          <div style={{ width: 3, height: 3, background: '#5be8f5',
                        borderRadius: '50%',
                        boxShadow: '0 0 3px #5be8f5' }} />
        </div>
      ))}
      <div style={{
        position: 'absolute', bottom: 2, left: 0, right: 0,
        textAlign: 'center', fontSize: 7, color: '#5be8f5',
        letterSpacing: 1, fontFamily: 'JetBrains Mono, monospace',
      }}>{label || 'SRV'}</div>
    </div>
  );
}

function Printer({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 90, height: 80 }}>
      <div style={{
        width: 80, height: 56, margin: '0 auto',
        background: '#2a3a4a', border: '1px solid #3a4a5a',
        position: 'relative',
      }}>
        <div style={{ position: 'absolute', top: 10, left: 6, width: 68, height: 4,
                      background: '#9be8a4' }} />
        <div style={{ position: 'absolute', top: 24, left: 8, width: 64, height: 16,
                      background: '#f0e8d4' }} />
        <div style={{ position: 'absolute', top: 27, left: 12, width: 36, height: 1,
                      background: '#1a1a28' }} />
        <div style={{ position: 'absolute', top: 30, left: 12, width: 28, height: 1,
                      background: '#1a1a28' }} />
        <div style={{ position: 'absolute', top: 33, left: 12, width: 32, height: 1,
                      background: '#1a1a28' }} />
      </div>
      <div style={{
        fontSize: 10, letterSpacing: 2, color: '#5fa14b',
        textAlign: 'center', marginTop: 4,
        fontFamily: 'JetBrains Mono, monospace',
      }}>PRINTER</div>
    </div>
  );
}

function Cooler({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 80, height: 100 }}>
      <div style={{
        width: 56, height: 80, margin: '0 auto',
        background: '#0a1828',
        border: '1px solid #5be8f5',
        boxShadow: '0 0 12px rgba(91,232,245,0.3)',
        position: 'relative',
      }}>
        <div style={{ position: 'absolute', top: 4, left: 8, width: 40, height: 30,
                      background: 'rgba(91,232,245,0.3)',
                      border: '1px solid #5be8f5' }} />
        <div style={{ position: 'absolute', top: 40, left: 4, width: 48, height: 36,
                      background: '#cfe2f4' }}>
          <div style={{ position: 'absolute', top: 8, left: 18, width: 12, height: 4,
                        background: '#5be8f5' }} />
        </div>
      </div>
      <div style={{
        fontSize: 10, letterSpacing: 2, color: '#5be8f5',
        textAlign: 'center', marginTop: 4,
        fontFamily: 'JetBrains Mono, monospace',
      }}>COOLER</div>
    </div>
  );
}

/* ════════ Lockers — metal cabinets along walls ════════ */
function LockerBank({ x, y, count = 3, color }) {
  const c = color || '#5be8f5';
  return (
    <div style={{ position: 'absolute', left: x, top: y, display: 'flex', gap: 1 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          width: 26, height: 72,
          background: 'linear-gradient(180deg, #2a3a52 0%, #1a2438 100%)',
          border: '1px solid #0a1424',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -2px 0 rgba(0,0,0,0.4)',
          position: 'relative',
        }}>
          {/* LED indicator */}
          <div style={{
            position: 'absolute', top: 4, left: 4,
            width: 3, height: 3, background: c, borderRadius: '50%',
            boxShadow: `0 0 4px ${c}`,
          }} />
          {/* Numeric label */}
          <div style={{
            position: 'absolute', top: 3, right: 4,
            fontSize: 6, color: c, opacity: 0.8,
            fontFamily: 'JetBrains Mono, monospace',
          }}>{(i + 1).toString().padStart(2, '0')}</div>
          {/* Door split */}
          <div style={{
            position: 'absolute', top: 0, left: '50%', width: 1, height: '100%',
            background: '#0a1424',
          }} />
          {/* Handles */}
          <div style={{
            position: 'absolute', top: 38, left: 5, width: 6, height: 2,
            background: c, opacity: 0.7,
          }} />
          <div style={{
            position: 'absolute', top: 38, right: 5, width: 6, height: 2,
            background: c, opacity: 0.7,
          }} />
          {/* Bottom vent */}
          <div style={{
            position: 'absolute', bottom: 4, left: 4, right: 4, height: 1,
            background: '#0a1424',
          }} />
          <div style={{
            position: 'absolute', bottom: 6, left: 4, right: 4, height: 1,
            background: '#0a1424',
          }} />
        </div>
      ))}
    </div>
  );
}

/* ════════ Big Server tower (different from rack) ════════ */
function ServerTower({ x, y, label, status }) {
  const blink = status === 'warn' ? '#ffae3a' : '#9be8a4';
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 56, height: 90 }}>
      <div style={{
        width: 52, height: 78,
        background: 'linear-gradient(180deg, #1a2840 0%, #0a121e 100%)',
        border: '1px solid #3a5278',
        boxShadow: '0 0 12px rgba(58,138,214,0.3)',
        position: 'relative',
      }}>
        {/* Front mesh */}
        <div style={{
          position: 'absolute', top: 4, left: 4, right: 4, height: 28,
          background: 'repeating-linear-gradient(0deg, #04101a 0 2px, #0a1828 2px 3px)',
        }} />
        {/* Display */}
        <div style={{
          position: 'absolute', top: 36, left: 6, right: 6, height: 14,
          background: '#020812', border: `1px solid ${blink}80`,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 6, color: blink, padding: '1px 3px',
          textShadow: `0 0 3px ${blink}`,
        }}>
          {label || 'CORE-A'}<br />
          {status === 'warn' ? 'HOT' : 'OK'}
        </div>
        {/* LEDs strip */}
        <div style={{
          position: 'absolute', bottom: 8, left: 6, right: 6, height: 4,
          display: 'flex', gap: 2,
        }}>
          {[0,1,2,3,4,5].map(i => (
            <div key={i} style={{
              flex: 1, background: i % 2 === 0 ? blink : '#5be8f5',
              opacity: 0.7, boxShadow: `0 0 2px ${i % 2 === 0 ? blink : '#5be8f5'}`,
            }} />
          ))}
        </div>
      </div>
      <div style={{
        fontSize: 8, letterSpacing: 1, color: blink,
        textAlign: 'center', marginTop: 2,
        fontFamily: 'JetBrains Mono, monospace',
      }}>{label || 'SRV'}</div>
    </div>
  );
}

/* ════════ Vending machine ════════ */
function VendingMachine({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 60, height: 100 }}>
      <div style={{
        width: 56, height: 82,
        background: 'linear-gradient(180deg, #5fa14b 0%, #2a5a18 100%)',
        border: '1px solid #1a3008',
        position: 'relative',
        boxShadow: '0 0 10px rgba(95,161,75,0.3)',
      }}>
        {/* Display window */}
        <div style={{
          position: 'absolute', top: 4, left: 4, right: 4, height: 48,
          background: '#0a121e', border: '1px solid #02080f',
          padding: 3, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1,
        }}>
          {['#ff8a6c','#5be8f5','#ffd84a','#9be8a4','#a878e8','#ff8a6c'].map((c, i) => (
            <div key={i} style={{
              background: c, opacity: 0.8,
              borderRadius: 1,
            }} />
          ))}
        </div>
        {/* Keypad */}
        <div style={{
          position: 'absolute', top: 56, left: 6, width: 20, height: 18,
          background: '#02080f', border: '1px solid #02080f',
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, padding: 1,
        }}>
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} style={{ background: '#5fa14b', opacity: 0.5 }} />
          ))}
        </div>
        {/* Slot */}
        <div style={{
          position: 'absolute', bottom: 4, left: 28, right: 4, height: 12,
          background: '#02080f', border: '1px solid #02080f',
        }} />
      </div>
      <div style={{
        fontSize: 8, letterSpacing: 1, color: '#9be8a4',
        textAlign: 'center', marginTop: 2,
        fontFamily: 'JetBrains Mono, monospace',
      }}>SNACKS</div>
    </div>
  );
}

/* ════════ Holo wall panel (mountable on a wall) ════════ */
function HoloWallPanel({ x, y, color, label }) {
  const c = color || '#5be8f5';
  return (
    <div style={{
      position: 'absolute', left: x, top: y, width: 70, height: 50,
      background: 'rgba(2,8,18,0.85)',
      border: `1px solid ${c}`,
      boxShadow: `0 0 10px ${c}60, inset 0 0 8px rgba(0,0,0,0.6)`,
      padding: 3,
    }}>
      <div style={{
        fontSize: 7, color: c, letterSpacing: 1,
        fontFamily: 'JetBrains Mono, monospace',
        textShadow: `0 0 3px ${c}`,
      }}>{label || 'STATUS'}</div>
      <div style={{ height: 30, marginTop: 2 }}>
        <LiveLineChart color={c} count={20} />
      </div>
    </div>
  );
}

/* ════════ Whiteboard ════════ */
function Whiteboard({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 80, height: 60 }}>
      <div style={{
        width: '100%', height: 48,
        background: '#f0e8d4',
        border: '2px solid #5a3a18',
        position: 'relative',
        padding: 4,
        boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
      }}>
        {/* Mock chart */}
        <svg viewBox="0 0 72 40" style={{ width: '100%', height: '100%' }}>
          <path d="M 2 30 L 12 22 L 24 26 L 36 12 L 48 18 L 60 8 L 70 14"
                fill="none" stroke="#3aaad6" strokeWidth="1.5" />
          <line x1="2" y1="35" x2="70" y2="35" stroke="#666" strokeWidth="0.5" />
          <line x1="2" y1="2" x2="2" y2="35" stroke="#666" strokeWidth="0.5" />
          <text x="20" y="6" fontSize="4" fill="#d6431a" fontFamily="JetBrains Mono">Q4 TARGET</text>
        </svg>
        {/* Marker tray */}
        <div style={{
          position: 'absolute', bottom: -3, left: 4, right: 4, height: 4,
          background: '#5a3a18',
        }} />
        <div style={{ position: 'absolute', bottom: 0, left: 6, width: 6, height: 2, background: '#d6431a' }} />
        <div style={{ position: 'absolute', bottom: 0, left: 18, width: 6, height: 2, background: '#3aaad6' }} />
        <div style={{ position: 'absolute', bottom: 0, left: 30, width: 6, height: 2, background: '#5fa14b' }} />
      </div>
      <div style={{
        fontSize: 8, letterSpacing: 1, color: '#9eb5cf',
        textAlign: 'center', marginTop: 6,
        fontFamily: 'JetBrains Mono, monospace',
      }}>BOARD</div>
    </div>
  );
}

/* ════════ Trash bin ════════ */
function TrashBin({ x, y }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: 22, height: 28 }}>
      <div style={{
        width: 18, height: 22, margin: '0 auto',
        background: '#3a4a5a', border: '1px solid #1a2030',
        clipPath: 'polygon(10% 0, 90% 0, 100% 100%, 0% 100%)',
        position: 'relative',
      }}>
        <div style={{ position: 'absolute', top: 4, left: 0, right: 0, height: 1,
                      background: '#5a6a7a' }} />
        <div style={{ position: 'absolute', top: 10, left: 0, right: 0, height: 1,
                      background: '#5a6a7a' }} />
      </div>
      <div style={{
        position: 'absolute', top: -3, left: 1, width: 20, height: 3,
        background: '#5a6a7a', borderRadius: '50%',
      }} />
    </div>
  );
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

const appStyles = {
  root: {
    background: '#020812',
    minHeight: '100vh',
    color: '#cfe2f4',
    fontFamily: 'JetBrains Mono, ui-monospace, monospace',
    overflow: 'hidden',
  },
  toolbar: {
    height: 50,
    background: '#04101e',
    borderBottom: '1px solid #1f2f48',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px',
  },
  brand: {
    fontSize: 12, letterSpacing: 2,
    color: '#e7f0fb', fontWeight: 600,
    display: 'flex', alignItems: 'center', gap: 10,
  },
  dot: {
    width: 8, height: 8, background: '#9be8a4',
    borderRadius: '50%', boxShadow: '0 0 8px #9be8a4',
  },
  toolRight: { display: 'flex', alignItems: 'center', gap: 12 },
  muted: { fontSize: 10, color: '#6e8aa8', letterSpacing: 1 },
  btn: {
    background: '#0a1525', border: '1px solid #2a3a52',
    color: '#9fd5ff', padding: '6px 12px',
    fontFamily: 'inherit', fontSize: 10, letterSpacing: 1,
    cursor: 'pointer', textTransform: 'uppercase', borderRadius: 2,
  },
  stageWrap: {
    width: '100vw',
    height: 'calc(100vh - 50px)',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    background: 'radial-gradient(ellipse at center top, #0a1828 0%, #020812 70%)',
  },
  stage: {
    width: 2000, height: 1200,
    position: 'relative',
    transformOrigin: 'top center',
    background: '#04101a',
    border: '1px solid #1f3050',
    flexShrink: 0,
  },
  floorGrid: {
    position: 'absolute',
    left: 0, right: 0, top: 200, bottom: 80,
    background:
      'repeating-linear-gradient(0deg, transparent 0 39px, rgba(91,232,245,0.05) 39px 40px),' +
      'repeating-linear-gradient(90deg, transparent 0 39px, rgba(91,232,245,0.05) 39px 40px)',
    pointerEvents: 'none',
  },
  floorGlow: {
    position: 'absolute',
    left: 0, right: 0, top: 200, bottom: 80,
    background: 'radial-gradient(ellipse at 50% 30%, rgba(91,232,245,0.05) 0%, transparent 60%)',
    pointerEvents: 'none',
  },
  wallStrip: {
    position: 'absolute',
    left: 0, right: 0, top: 0, height: 170,
    background: 'linear-gradient(180deg, #04101e 0%, #0a1828 100%)',
    borderBottom: '2px solid #5be8f5',
    boxShadow: '0 2px 24px rgba(91,232,245,0.2)',
  },
  cableTray: {
    position: 'absolute',
    left: 30, right: 30, height: 2,
    background: 'repeating-linear-gradient(90deg, #5be8f5 0 4px, transparent 4px 8px)',
    opacity: 0.3,
    pointerEvents: 'none',
  },
  statusBar: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0, height: 30,
    background: '#04101e',
    borderTop: '1px solid #1f2f48',
    display: 'flex',
    alignItems: 'center',
    gap: 18,
    padding: '0 20px',
    fontSize: 10, letterSpacing: 1,
    zIndex: 20,
  },
};

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<OfficeV4App />);
