/* Effect helpers — reusable bits for power animations. */
(function () {
  const FX = {};

  /* Motion blur — draws shifted ghosts of the sprite using a draw callback */
  FX.afterimages = function (ctx, draw, count, dx, dy, alphaStart) {
    for (let i = count; i >= 1; i--) {
      const a = (alphaStart || 0.35) * (i / count);
      ctx.save();
      ctx.globalAlpha = a;
      ctx.translate(-dx * i, -dy * i);
      draw();
      ctx.restore();
    }
  };

  /* Horizontal speed lines */
  FX.speedLines = function (ctx, x, y, w, count, color) {
    PX.r(ctx, x, y, w, 1, color);
    for (let i = 0; i < count; i++) {
      const ly = y + 4 + i * 3;
      PX.r(ctx, x, ly, Math.max(2, w - i * 3), 1, color);
    }
  };

  /* Lightning bolt zigzag */
  FX.bolt = function (ctx, x, y, color) {
    const pts = [[0,0],[2,0],[1,2],[3,2],[2,4],[4,4],[2,6]];
    for (const [dx, dy] of pts) PX.px(ctx, x + dx, y + dy, color);
  };

  /* Jet flame (multiple frames) */
  FX.jetFlame = function (ctx, x, y, frame, outer, inner, core) {
    const flick = frame % 2 === 0;
    const h = flick ? 8 : 10;
    // outer flame
    PX.r(ctx, x - 2, y, 6, h - 4, outer);
    PX.r(ctx, x - 1, y + h - 4, 4, 2, outer);
    PX.r(ctx, x,     y + h - 2, 2, 2, outer);
    // inner flame
    PX.r(ctx, x - 1, y, 4, h - 5, inner);
    PX.r(ctx, x,     y + h - 5, 2, 2, inner);
    // core white-hot
    PX.r(ctx, x,     y, 2, h - 7, core);
  };

  /* Energy beam (horizontal) */
  FX.beam = function (ctx, x, y, len, frame, outer, inner, core) {
    const wobble = (frame % 2) - 0.5;
    PX.r(ctx, x, y + wobble, len, 5, outer);
    PX.r(ctx, x, y + 1 + wobble, len, 3, inner);
    PX.r(ctx, x, y + 2 + wobble, len, 1, core);
    // tip glow
    PX.circle(ctx, x + len, y + 2 + wobble, 3, outer);
    PX.circle(ctx, x + len, y + 2 + wobble, 2, inner);
  };

  /* Web line — diagonal dashed */
  FX.webline = function (ctx, x0, y0, x1, y1, color) {
    const dx = x1 - x0, dy = y1 - y0;
    const len = Math.max(Math.abs(dx), Math.abs(dy));
    for (let i = 0; i <= len; i += 2) {
      const t = i / len;
      PX.px(ctx, Math.round(x0 + dx * t), Math.round(y0 + dy * t), color);
    }
  };

  /* Impact / shockwave ring */
  FX.shock = function (ctx, cx, cy, radius, color) {
    for (let a = 0; a < 360; a += 18) {
      const rad = (a * Math.PI) / 180;
      PX.px(ctx, Math.round(cx + Math.cos(rad) * radius), Math.round(cy + Math.sin(rad) * radius * 0.4), color);
    }
  };

  /* Sparkles around point */
  FX.sparkles = function (ctx, cx, cy, frame, color) {
    const pts = [[-6,-4],[7,-3],[-5,5],[6,4],[0,-7]];
    for (let i = 0; i < pts.length; i++) {
      if ((i + frame) % 3 === 0) continue;
      const [dx, dy] = pts[i];
      PX.px(ctx, cx + dx,     cy + dy, color);
      PX.px(ctx, cx + dx + 1, cy + dy, color);
      PX.px(ctx, cx + dx,     cy + dy + 1, color);
    }
  };

  window.FX = FX;
})();
