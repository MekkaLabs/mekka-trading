/* Pixel-art primitives — every draw call is a 1×1 rect so the result
   stays crisp when the host canvas uses `image-rendering: pixelated`. */
(function () {
  const PX = {};

  PX.r = function (ctx, x, y, w, h, c) {
    if (!c) return;
    ctx.fillStyle = c;
    ctx.fillRect(x | 0, y | 0, w | 0, h | 0);
  };

  PX.px = function (ctx, x, y, c) {
    if (!c) return;
    ctx.fillStyle = c;
    ctx.fillRect(x | 0, y | 0, 1, 1);
  };

  /* Outline-only rect (1px border) */
  PX.outline = function (ctx, x, y, w, h, c) {
    PX.r(ctx, x, y, w, 1, c);
    PX.r(ctx, x, y + h - 1, w, 1, c);
    PX.r(ctx, x, y + 1, 1, h - 2, c);
    PX.r(ctx, x + w - 1, y + 1, 1, h - 2, c);
  };

  /* Rounded rect — corner pixels removed, body filled */
  PX.round = function (ctx, x, y, w, h, c) {
    PX.r(ctx, x + 1, y, w - 2, h, c);
    PX.r(ctx, x, y + 1, 1, h - 2, c);
    PX.r(ctx, x + w - 1, y + 1, 1, h - 2, c);
  };

  /* Filled circle of given radius (pixel-art friendly). */
  PX.circle = function (ctx, cx, cy, r, c) {
    ctx.fillStyle = c;
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy <= r * r) ctx.fillRect((cx + dx) | 0, (cy + dy) | 0, 1, 1);
      }
    }
  };

  /* Diagonal line — Bresenham-ish for short pixel runs */
  PX.line = function (ctx, x0, y0, x1, y1, c) {
    ctx.fillStyle = c;
    const dx = Math.abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    const dy = -Math.abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    let err = dx + dy, e2;
    let x = x0, y = y0;
    for (let i = 0; i < 200; i++) {
      ctx.fillRect(x, y, 1, 1);
      if (x === x1 && y === y1) break;
      e2 = 2 * err;
      if (e2 >= dy) { err += dy; x += sx; }
      if (e2 <= dx) { err += dx; y += sy; }
    }
  };

  /* Draw a tile-grid character from a string array.
     palette keys: any non-space char. '.' / ' ' are transparent. */
  PX.grid = function (ctx, x, y, rows, palette) {
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      for (let c = 0; c < row.length; c++) {
        const ch = row[c];
        if (ch === ' ' || ch === '.') continue;
        const col = palette[ch];
        if (!col) continue;
        ctx.fillStyle = col;
        ctx.fillRect(x + c, y + r, 1, 1);
      }
    }
  };

  /* Pokemon-style soft shadow under feet (ellipse-ish) */
  PX.shadow = function (ctx, cx, cy, w, opacity) {
    ctx.save();
    ctx.fillStyle = `rgba(0,0,0,${opacity ?? 0.35})`;
    const h = Math.max(2, Math.floor(w / 3));
    for (let dy = 0; dy < h; dy++) {
      const t = dy / (h - 1 || 1);
      const ww = Math.round(w * (1 - Math.abs(t - 0.5) * 0.6));
      ctx.fillRect(cx - (ww >> 1), cy + dy, ww, 1);
    }
    ctx.restore();
  };

  window.PX = PX;
})();
