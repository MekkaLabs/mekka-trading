import { AGENTS } from './roster.js';

const BASE_PATTERN = [
  '...1111...',
  '..122221..',
  '..122221..',
  '..133331..',
  '..144441..',
  '..144441..',
  '..155551..',
  '..155551..',
  '..166661..',
  '..166661..',
  '.11....11.',
];

const OUTFIT_PALETTES = {
  blue_red: { 1: '#0f172a', 2: '#f6d0a8', 3: '#2563eb', 4: '#dc2626', 5: '#2563eb', 6: '#dc2626' },
  purple_red: { 1: '#1f102b', 2: '#f6d0a8', 3: '#7c3aed', 4: '#b91c1c', 5: '#6d28d9', 6: '#b91c1c' },
  black_vibranium: { 1: '#020617', 2: '#7c8599', 3: '#0f172a', 4: '#4338ca', 5: '#111827', 6: '#020617' },
  steel_blue: { 1: '#1e293b', 2: '#f6d0a8', 3: '#1d4ed8', 4: '#64748b', 5: '#1e40af', 6: '#475569' },
  green_gold: { 1: '#0b3b2d', 2: '#f6d0a8', 3: '#059669', 4: '#d97706', 5: '#10b981', 6: '#d97706' },
  red_blue: { 1: '#450a0a', 2: '#f6d0a8', 3: '#dc2626', 4: '#1d4ed8', 5: '#ef4444', 6: '#1e3a8a' },
  navy_gray: { 1: '#0f172a', 2: '#f6d0a8', 3: '#334155', 4: '#475569', 5: '#1e293b', 6: '#0f172a' },
  dark_yellow: { 1: '#111827', 2: '#f6d0a8', 3: '#1f2937', 4: '#a16207', 5: '#1f2937', 6: '#111827' },
  red_gold: { 1: '#7f1d1d', 2: '#f6d0a8', 3: '#dc2626', 4: '#d97706', 5: '#ef4444', 6: '#f59e0b' },
  black_trench: { 1: '#111827', 2: '#9f7d68', 3: '#1f2937', 4: '#374151', 5: '#1f2937', 6: '#111827' },
  blue_formal: { 1: '#1e293b', 2: '#f6d0a8', 3: '#1d4ed8', 4: '#0ea5e9', 5: '#2563eb', 6: '#1e3a8a' },
  yellow_blue: { 1: '#1e293b', 2: '#f6d0a8', 3: '#eab308', 4: '#1d4ed8', 5: '#facc15', 6: '#1e40af' },
  red_lightning: { 1: '#7f1d1d', 2: '#f6d0a8', 3: '#ef4444', 4: '#f59e0b', 5: '#dc2626', 6: '#facc15' },
  red_black: { 1: '#1f2937', 2: '#f6d0a8', 3: '#dc2626', 4: '#111827', 5: '#ef4444', 6: '#1f2937' },
};

function drawPattern(ctx, x, y, pattern, palette, size = 4) {
  for (let py = 0; py < pattern.length; py += 1) {
    const row = pattern[py];
    for (let px = 0; px < row.length; px += 1) {
      const token = row[px];
      if (token === '.') continue;
      ctx.fillStyle = palette[token] || '#94a3b8';
      ctx.fillRect(x + px * size, y + py * size, size, size);
    }
  }
}

export function drawAgent(ctx, agent, x, y, opts = {}) {
  const size = opts.size || 4;
  const bob = opts.bob || 0;
  const palette = OUTFIT_PALETTES[agent.outfit] || OUTFIT_PALETTES.blue_red;
  drawPattern(ctx, x, y + bob, BASE_PATTERN, palette, size);

  if (agent.id === 'deadpool') {
    ctx.fillStyle = '#111827';
    ctx.fillRect(x + size * 4, y + size * 2 + bob, size, size);
    ctx.fillRect(x + size * 6, y + size * 2 + bob, size, size);
  }

  if (opts.highlight) {
    ctx.strokeStyle = agent.color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 2, y - 2 + bob, BASE_PATTERN[0].length * size + 4, BASE_PATTERN.length * size + 4);
  }
}

export function drawRosterIcon(ctx, agent) {
  ctx.clearRect(0, 0, 44, 52);
  drawAgent(ctx, agent, 4, 2, { size: 4 });
}

export const AGENT_BY_ID = Object.fromEntries(AGENTS.map((agent) => [agent.id, agent]));
