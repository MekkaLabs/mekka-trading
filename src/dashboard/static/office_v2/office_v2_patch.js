/**
 * office_v2_patch.js — Hero power animations + futuristic overlays
 * Loaded AFTER the bundle, props_v3.js, and powers.js.
 *
 * Strategy:
 *   1. Initialize global power state (makeInitialPowers from powers.js)
 *   2. Wrap tickMotion to also tick powers each frame
 *   3. Wrap paintScene to:
 *      a) inject power state (drawPower + getPowerLift from powers.js)
 *      b) draw flying/lift effects for airborne agents
 *      c) draw futuristic overlays (ceiling LED, holographic labels)
 *   4. Wrap drawAgent to apply flyY offset for flyers (legacy, kept for compat)
 */
(function patchOfficeV2() {
  "use strict";

  // ── Wait for dependencies ─────────────────────────────────────────────────
  // makeInitialPowers/tickPowers come from powers.js (loaded before this)
  // They're plain functions on window (no JSX), so available immediately.
  if (typeof window.makeInitialPowers !== 'function') {
    console.warn('[office-v2-patch] powers.js not yet loaded, retrying in 200ms');
    setTimeout(patchOfficeV2, 200);
    return;
  }

  // ── Global power state ────────────────────────────────────────────────────
  window._powerState = window.makeInitialPowers();

  // ── Wrap tickMotion — tick powers each frame alongside motion ─────────────
  const _origTickMotion = window.tickMotion;
  window.tickMotion = function(state, frame, opts) {
    state = _origTickMotion(state, frame, opts);
    // Tick power animations; requires motion state so powers only fire at-desk
    window.tickPowers(window._powerState, frame, state);
    return state;
  };

  // ── Futuristic overlay functions ──────────────────────────────────────────

  /**
   * Draw ceiling LED strip across the top of the scene wall.
   * Adds a horizontal neon cyan bar with a traveling bright pulse.
   */
  function drawCeilingLED(ctx, frame, sceneW) {
    sceneW = sceneW || 480;
    // Solid LED line
    ctx.fillStyle = "#22d3ee";
    ctx.fillRect(0, 2, sceneW, 1);
    // Soft glow above/below
    ctx.globalAlpha = 0.35;
    ctx.fillStyle = "#22d3ee";
    ctx.fillRect(0, 0, sceneW, 2);
    ctx.fillRect(0, 3, sceneW, 2);
    ctx.globalAlpha = 1;
    // Traveling bright pulse
    const ledX = (frame * 6) % (sceneW + 60) - 30;
    ctx.fillStyle = "#ecfeff";
    ctx.fillRect(ledX, 2, 30, 1);
  }

  /**
   * Draw holographic room-zone color strips along the floor of each zone.
   * Non-intrusive: just small colored glowing lines at zone boundaries.
   */
  function drawZoneAccents(ctx, sceneW) {
    sceneW = sceneW || 480;
    // Blue / cyan zone accent at y ≈ bottom of scene, subtle
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#38bdf8";
    ctx.fillRect(0, 0, Math.floor(sceneW * 0.38), 1); // L1 strip
    ctx.fillStyle = "#a78bfa";
    ctx.fillRect(Math.floor(sceneW * 0.38), 0, Math.floor(sceneW * 0.38), 1); // L2/L3
    ctx.fillStyle = "#22c55e";
    ctx.fillRect(Math.floor(sceneW * 0.76), 0, sceneW, 1); // L4
    ctx.globalAlpha = 1;
  }

  /**
   * Draw a minimal holographic "MEKKA TRADING OPS" label overlay on the wall area.
   * Drawn at top-right corner, low opacity so it doesn't obscure existing art.
   */
  function drawHoloWatermark(ctx, frame, sceneW) {
    sceneW = sceneW || 480;
    const pulse = 0.55 + 0.15 * Math.sin(frame * 0.04);
    ctx.globalAlpha = pulse * 0.55;
    ctx.fillStyle = "#22d3ee";
    // Small 1-pixel "MEKKA" text simulation — just bars
    const x = sceneW - 54, y = 6;
    for (let i = 0; i < 10; i++) {
      const on = ((frame + i * 3) >> 2) % 5 !== 0;
      if (on) ctx.fillRect(x + i * 5, y, 4, 1);
    }
    ctx.globalAlpha = 1;
  }

  // ── Patch: paintScene ─────────────────────────────────────────────────────
  // Intercept to inject power effects and futuristic overlays.
  const _origPaintScene = window.paintScene;
  window.paintScene = function(ctx, frame, agents, motion, optsArg) {
    // The bundle's app.jsx calls: paintScene(ctx, frame, AGENTS, motion, opts)
    // opts = { showPoiMarkers, flashes }
    // We forward as-is for the base render, then draw power effects on top.
    _origPaintScene(ctx, frame, agents, motion, optsArg);

    // ── Futuristic ceiling overlays ──────────────────────────────────────
    const sceneW = (typeof window.SCENE_W !== 'undefined') ? window.SCENE_W : 480;
    drawCeilingLED(ctx, frame, sceneW);
    drawZoneAccents(ctx, sceneW);
    drawHoloWatermark(ctx, frame, sceneW);

    // ── Power effects overlay ────────────────────────────────────────────
    if (!agents || !motion) return;
    const pState = window._powerState;

    for (const agent of agents) {
      const m = motion[agent.id];
      if (!m) continue;
      const px = Math.round(m.pos.x);
      const py = Math.round(m.pos.y);
      // Lift for flying heroes (getPowerLift from powers.js)
      const lift = window.getPowerLift ? window.getPowerLift(agent.id, pState, frame) : 0;
      const drawY = py + lift;
      // If lifted, redraw agent at new Y (cover old position)
      if (lift !== 0 && window.drawAgent) {
        // Erase at original Y by overdrawing with floor color (16x22 area)
        ctx.fillStyle = '#0c1320';
        ctx.fillRect(px, py, 16, 24);
        // Redraw agent at lifted position
        const seated = m.mode === 'at-desk';
        const bob = seated ? (Math.sin((frame + agent.name.length) / 18) > 0.7 ? 1 : 0) : ((frame >> 1) % 2);
        const flip = !seated && m.dir < 0;
        const legFrame = !seated ? ((frame >> 2) % 2) : 0;
        window.drawAgent(ctx, agent, px, drawY, {
          bob, flip, walking: !seated, legFrame, bubble: m.bubble,
          wheelchair: false, frame,
        });
        // Wind streaks under lifted agent
        if (lift < -2) {
          ctx.fillStyle = 'rgba(56,189,248,0.5)';
          ctx.fillRect(px + 4, drawY + 22 - lift, 8, 1);
          ctx.fillStyle = 'rgba(56,189,248,0.25)';
          ctx.fillRect(px + 2, drawY + 23 - lift, 12, 1);
        }
      }
      // Draw power effect (drawPower from powers.js)
      if (window.drawPower) {
        window.drawPower(ctx, agent.id, px, py + lift, pState, frame);
      }
    }
  };

  console.info('[office-v2-patch] ✓ v3 powers + futuristic overlays loaded');
})();
