/* Pixel-engine v3 — adds shading helpers needed for richer Gen-4 sprites.
   Layered on top of PX (pixel-engine.js). */
(function () {
  if (!window.PX) { console.error('pixel-engine.js must load first'); return; }

  /* Dither — alternating checkerboard fill between two colors */
  PX.dither = function (ctx, x, y, w, h, a, b) {
    for (let py = 0; py < h; py++) {
      for (let px = 0; px < w; px++) {
        ctx.fillStyle = ((px + py) % 2 === 0) ? a : b;
        ctx.fillRect(x + px, y + py, 1, 1);
      }
    }
  };

  /* Selective outline — draws outline only on rows/cols where pixels are set.
     Cheap "rim" effect by drawing 1px to the right + down of an inner color. */
  PX.rim = function (ctx, x, y, w, h, color) {
    PX.r(ctx, x + 1, y + h, w - 1, 1, color);  // bottom shadow
    PX.r(ctx, x + w, y + 1, 1, h - 1, color);  // right shadow
  };

  /* Three-tone vertical shade for a rect: top highlight strip, base, bottom shadow */
  PX.shade3 = function (ctx, x, y, w, h, light, base, dark, hStripe = 1) {
    PX.r(ctx, x, y, w, h, base);
    PX.r(ctx, x, y, w, hStripe, light);
    PX.r(ctx, x, y + h - hStripe, w, hStripe, dark);
  };

  /* Three-tone horizontal shade: left highlight, right shadow */
  PX.shade3h = function (ctx, x, y, w, h, light, base, dark, wStripe = 1) {
    PX.r(ctx, x, y, w, h, base);
    PX.r(ctx, x, y, wStripe, h, light);
    PX.r(ctx, x + w - wStripe, y, wStripe, h, dark);
  };

  /* Filled rect with subtle gradient (1px stripes) */
  PX.gradV = function (ctx, x, y, w, h, top, bottom) {
    for (let i = 0; i < h; i++) {
      const t = i / Math.max(1, h - 1);
      ctx.fillStyle = mixHex(top, bottom, t);
      ctx.fillRect(x, y + i, w, 1);
    }
  };

  function mixHex(a, b, t) {
    const ar = parseInt(a.slice(1,3), 16), ag = parseInt(a.slice(3,5), 16), ab = parseInt(a.slice(5,7), 16);
    const br = parseInt(b.slice(1,3), 16), bg = parseInt(b.slice(3,5), 16), bb = parseInt(b.slice(5,7), 16);
    const m = (x, y) => Math.round(x + (y - x) * t);
    return '#' + [m(ar,br), m(ag,bg), m(ab,bb)].map(v => v.toString(16).padStart(2,'0')).join('');
  }
  PX.mix = mixHex;
})();
