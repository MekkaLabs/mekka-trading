import React, { useEffect, useRef } from 'react';
import { AGENTS, STATIONS } from './roster.js';
import { drawAgent } from './sprites.js';

const W = 640;
const H = 360;

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function drawDesk(ctx, x, y, theme) {
  const top = theme === 'light' ? '#d6dee8' : '#2b3648';
  const edge = theme === 'light' ? '#9fb0c5' : '#172133';
  ctx.fillStyle = top;
  ctx.fillRect(x - 22, y + 26, 56, 14);
  ctx.fillStyle = edge;
  ctx.fillRect(x - 22, y + 37, 56, 3);
  ctx.fillStyle = theme === 'light' ? '#3b4a5f' : '#111827';
  ctx.fillRect(x - 10, y + 12, 28, 16);
  ctx.fillStyle = '#45d0ff';
  ctx.fillRect(x - 7, y + 15, 22, 10);
}

export default function OfficeScene({ selectedId, liveState, theme }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    let raf = 0;
    let tick = 0;

    function frame() {
      tick += 1;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;

      ctx.clearRect(0, 0, W, H);

      const bg = theme === 'light'
        ? ['#f2f7fb', '#e3edf7', '#d2deea']
        : ['#091322', '#0e1a2f', '#14253d'];
      const floor = theme === 'light' ? '#dbe8f4' : '#1f2d44';
      const grid = theme === 'light' ? 'rgba(63,86,113,0.15)' : 'rgba(113,150,196,0.12)';

      const g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, bg[0]);
      g.addColorStop(0.55, bg[1]);
      g.addColorStop(1, bg[2]);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);

      ctx.fillStyle = floor;
      ctx.fillRect(0, 66, W, H - 66);

      ctx.strokeStyle = grid;
      for (let x = 0; x < W; x += 28) {
        ctx.beginPath();
        ctx.moveTo(x, 66);
        ctx.lineTo(x, H);
        ctx.stroke();
      }
      for (let y = 66; y < H; y += 22) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }

      // wall displays
      ctx.fillStyle = theme === 'light' ? '#c6d6e7' : '#0f1b2f';
      ctx.fillRect(210, 10, 220, 46);
      ctx.fillStyle = '#45d0ff';
      for (let i = 0; i < 28; i += 1) {
        const h = 6 + Math.floor((Math.sin((tick + i) * 0.18) + 1) * 8);
        ctx.fillRect(218 + i * 7, 50 - h, 4, h);
      }

      STATIONS.forEach((st) => drawDesk(ctx, st.x, st.y, theme));

      AGENTS.forEach((agent) => {
        const st = STATIONS.find((s) => s.id === agent.id);
        if (!st) return;
        const agentState = liveState[agent.id] || {};
        const pulse = 0.6 + (Math.sin((tick + st.x) * 0.08) + 1) * 0.2;
        const bob = Math.round(Math.sin((tick + st.y) * 0.1) * 2);
        const x = st.x - 16 + (agentState.walkOffsetX || 0);
        const y = st.y - 24 + bob + (agentState.walkOffsetY || 0);
        drawAgent(ctx, agent, x, y, {
          size: 3,
          bob,
          highlight: selectedId === agent.id,
        });

        if (agentState.flashUntil && agentState.flashUntil > Date.now()) {
          ctx.strokeStyle = agentState.side === 'loss' ? '#ef4444' : '#22c55e';
          ctx.lineWidth = 2;
          ctx.strokeRect(st.x - 20, st.y + 8, 50, 36);
          ctx.fillStyle = ctx.strokeStyle;
          ctx.font = '10px monospace';
          ctx.fillText(agentState.flashLabel || '', st.x - 20, st.y + 54);
        }

        ctx.fillStyle = theme === 'light' ? '#243244' : '#dbe8ff';
        ctx.font = '9px monospace';
        ctx.fillText(agent.name.toUpperCase(), st.x - 20, st.y + 50);
      });

      raf = window.requestAnimationFrame(frame);
    }

    raf = window.requestAnimationFrame(frame);
    return () => window.cancelAnimationFrame(raf);
  }, [selectedId, liveState, theme]);

  return <canvas ref={canvasRef} width={W} height={H} className="office-v2-canvas" />;
}
