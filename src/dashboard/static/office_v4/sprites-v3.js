/* Sprites v3 — 64×64 hi-res redesigns with 3-tone shading per surface,
   unique silhouettes per character, and richer accessory detail.
   Each char originale; codenames preserved as labels only. */
(function () {

const SPRITE_V3 = 64;

/* ─── helpers (kept local; we still draw via PX primitives) ──────── */

function shadowOval(ctx, cx, cy, w, alpha) {
  PX.shadow(ctx, cx, cy, w, alpha || 0.4);
}

/* ════════════════════════════════════════════════════════════════════
   1. VELOX (codename FLASH) — lean speedster, copper helmet w/ fins.
   ════════════════════════════════════════════════════════════════════ */

function drawVeloxV3(ctx, frame, mode, t) {
  const p = {
    skin:'#f5cc94', skinSh:'#c6905a', skinHi:'#ffe2b4',
    helmet:'#c47020', helmetD:'#6e3a08', helmetL:'#f4a040',
    suit:'#e89818', suitD:'#8a5208', suitL:'#ffce58',
    chrome:'#fff3c4', chromeD:'#a87808',
    goggle:'#1a0d04', lens:'#ffae3a', lensHi:'#fff5b8',
    leather:'#3a1808', leatherD:'#1a0d04',
    line:'#0e0703',
  };
  const yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  const dashX = mode === 'power' ? Math.round(Math.sin(t * Math.PI) * 2) : 0;
  ctx.save();
  ctx.translate(dashX, 0);

  shadowOval(ctx, 32, 60, 22, 0.38);

  /* HELMET — dome with backswept fins */
  // Top dome
  PX.r(ctx, 23, 2 + yo, 18, 1, p.helmet);
  PX.r(ctx, 22, 3 + yo, 20, 1, p.helmet);
  PX.r(ctx, 21, 4 + yo, 22, 1, p.helmet);
  PX.r(ctx, 20, 5 + yo, 24, 9, p.helmet);
  // Outline top
  PX.r(ctx, 23, 2 + yo, 18, 1, p.line);
  PX.r(ctx, 22, 3 + yo, 1, 1, p.line);  PX.r(ctx, 41, 3 + yo, 1, 1, p.line);
  PX.r(ctx, 21, 4 + yo, 1, 1, p.line);  PX.r(ctx, 42, 4 + yo, 1, 1, p.line);
  PX.r(ctx, 20, 5 + yo, 1, 9, p.line);  PX.r(ctx, 43, 5 + yo, 1, 9, p.line);
  // Helmet highlight
  PX.r(ctx, 23, 4 + yo, 14, 1, p.helmetL);
  PX.r(ctx, 22, 5 + yo, 16, 1, p.helmetL);
  PX.r(ctx, 21, 6 + yo, 4, 4, p.helmetL);
  // Brim shadow
  PX.r(ctx, 20, 12 + yo, 24, 1, p.helmetD);
  PX.r(ctx, 20, 13 + yo, 24, 1, p.line);
  // Crown chevron emblem
  PX.r(ctx, 30, 5 + yo, 4, 1, p.chrome);
  PX.r(ctx, 29, 6 + yo, 6, 1, p.chrome);
  PX.r(ctx, 28, 7 + yo, 8, 1, p.chrome);
  PX.r(ctx, 30, 8 + yo, 4, 1, p.chrome);

  /* SIDE FINS — backswept wing flares */
  // Left fin
  PX.r(ctx, 14, 9 + yo, 7, 6, p.helmet);
  PX.r(ctx, 14, 9 + yo, 7, 1, p.line);
  PX.r(ctx, 14, 14 + yo, 7, 1, p.line);
  PX.r(ctx, 13, 10 + yo, 1, 4, p.line);
  PX.r(ctx, 14, 10 + yo, 1, 4, p.helmetD);
  PX.r(ctx, 15, 10 + yo, 5, 1, p.helmetL);
  // notch
  PX.r(ctx, 18, 11 + yo, 2, 2, p.helmetD);
  // Right fin (mirror)
  PX.r(ctx, 43, 9 + yo, 7, 6, p.helmet);
  PX.r(ctx, 43, 9 + yo, 7, 1, p.line);
  PX.r(ctx, 43, 14 + yo, 7, 1, p.line);
  PX.r(ctx, 50, 10 + yo, 1, 4, p.line);
  PX.r(ctx, 49, 10 + yo, 1, 4, p.helmetD);
  PX.r(ctx, 44, 10 + yo, 5, 1, p.helmetL);
  PX.r(ctx, 44, 11 + yo, 2, 2, p.helmetD);

  /* FACE — skin visible below brim */
  PX.r(ctx, 21, 14 + yo, 22, 9, p.skin);
  PX.r(ctx, 20, 14 + yo, 1, 8, p.line);
  PX.r(ctx, 43, 14 + yo, 1, 8, p.line);
  PX.r(ctx, 21, 22 + yo, 22, 1, p.line);
  // Side cheek shadow
  PX.r(ctx, 21, 15 + yo, 1, 7, p.skinSh);
  PX.r(ctx, 42, 15 + yo, 1, 7, p.skinSh);
  PX.r(ctx, 22, 21 + yo, 20, 1, p.skinSh);
  // Cheek highlight
  PX.r(ctx, 23, 19 + yo, 2, 1, p.skinHi);
  PX.r(ctx, 39, 19 + yo, 2, 1, p.skinHi);

  /* GOGGLES — aviator twin lenses with bridge */
  // Left lens housing
  PX.r(ctx, 22, 14 + yo, 8, 5, p.goggle);
  PX.r(ctx, 23, 15 + yo, 6, 3, p.lens);
  PX.r(ctx, 23, 15 + yo, 6, 1, p.lensHi);
  PX.r(ctx, 24, 16 + yo, 1, 1, '#ffffff');
  // Right lens
  PX.r(ctx, 34, 14 + yo, 8, 5, p.goggle);
  PX.r(ctx, 35, 15 + yo, 6, 3, p.lens);
  PX.r(ctx, 35, 15 + yo, 6, 1, p.lensHi);
  PX.r(ctx, 36, 16 + yo, 1, 1, '#ffffff');
  // Nose bridge
  PX.r(ctx, 30, 14 + yo, 4, 5, p.goggle);
  PX.r(ctx, 31, 16 + yo, 2, 1, p.lens);

  /* MOUTH — slight smirk */
  PX.r(ctx, 28, 20 + yo, 8, 1, p.line);
  PX.r(ctx, 27, 20 + yo, 1, 1, p.skinSh);
  PX.r(ctx, 36, 20 + yo, 1, 1, p.skinSh);

  /* NECK */
  PX.r(ctx, 28, 23 + yo, 8, 2, p.skinSh);
  PX.r(ctx, 27, 23 + yo, 1, 2, p.line);
  PX.r(ctx, 36, 23 + yo, 1, 2, p.line);

  /* COLLAR — brass band across shoulders */
  PX.r(ctx, 17, 25 + yo, 30, 3, p.helmet);
  PX.r(ctx, 17, 25 + yo, 30, 1, p.line);
  PX.r(ctx, 17, 25 + yo, 1, 3, p.line);
  PX.r(ctx, 46, 25 + yo, 1, 3, p.line);
  PX.r(ctx, 18, 26 + yo, 28, 1, p.helmetL);
  PX.r(ctx, 18, 28 + yo, 28, 1, p.helmetD);

  /* TORSO */
  PX.r(ctx, 18, 28 + yo, 28, 15, p.suit);
  PX.r(ctx, 17, 29 + yo, 1, 14, p.line);
  PX.r(ctx, 46, 29 + yo, 1, 14, p.line);
  PX.r(ctx, 18, 28 + yo, 1, 15, p.suitD);
  PX.r(ctx, 45, 28 + yo, 1, 15, p.suitL);
  PX.r(ctx, 18, 42 + yo, 28, 1, p.line);

  // Reflective vertical stripes
  PX.r(ctx, 21, 28 + yo, 1, 14, p.chrome);
  PX.r(ctx, 42, 28 + yo, 1, 14, p.chrome);
  PX.r(ctx, 22, 28 + yo, 1, 14, p.chromeD);
  PX.r(ctx, 41, 28 + yo, 1, 14, p.chromeD);

  // Central chevron emblem (downward V)
  PX.r(ctx, 26, 32 + yo, 12, 1, p.chrome);
  PX.r(ctx, 27, 33 + yo, 10, 1, p.chrome);
  PX.r(ctx, 28, 34 + yo, 8, 1, p.chrome);
  PX.r(ctx, 29, 35 + yo, 6, 1, p.chrome);
  PX.r(ctx, 30, 36 + yo, 4, 1, p.chrome);
  PX.r(ctx, 31, 37 + yo, 2, 1, p.chrome);
  // Chevron inner shading
  PX.r(ctx, 28, 32 + yo, 1, 1, p.chromeD);
  PX.r(ctx, 35, 32 + yo, 1, 1, p.chromeD);

  /* BELT */
  PX.r(ctx, 17, 43 + yo, 30, 3, p.helmet);
  PX.r(ctx, 17, 43 + yo, 30, 1, p.line);
  PX.r(ctx, 17, 46 + yo, 30, 1, p.line);
  PX.r(ctx, 17, 43 + yo, 1, 3, p.line);
  PX.r(ctx, 46, 43 + yo, 1, 3, p.line);
  PX.r(ctx, 18, 44 + yo, 28, 1, p.helmetL);
  PX.r(ctx, 18, 45 + yo, 28, 1, p.helmetD);
  // Buckle
  PX.r(ctx, 29, 43 + yo, 6, 3, p.chrome);
  PX.r(ctx, 29, 43 + yo, 6, 1, p.line);
  PX.r(ctx, 29, 45 + yo, 6, 1, p.line);
  PX.r(ctx, 29, 44 + yo, 1, 1, p.line);
  PX.r(ctx, 34, 44 + yo, 1, 1, p.line);
  PX.r(ctx, 31, 44 + yo, 2, 1, p.helmet);

  /* ARMS */
  // Left
  PX.r(ctx, 13, 28 + yo, 5, 14, p.suit);
  PX.r(ctx, 12, 28 + yo, 1, 14, p.line);
  PX.r(ctx, 13, 28 + yo, 1, 14, p.suitD);
  PX.r(ctx, 17, 28 + yo, 1, 14, p.suitL);
  // Right
  PX.r(ctx, 46, 28 + yo, 5, 14, p.suit);
  PX.r(ctx, 51, 28 + yo, 1, 14, p.line);
  PX.r(ctx, 50, 28 + yo, 1, 14, p.suitD);
  PX.r(ctx, 46, 28 + yo, 1, 14, p.suitL);

  /* GLOVES — leather with brass cuff */
  // Left
  PX.r(ctx, 12, 42 + yo, 7, 5, p.leather);
  PX.r(ctx, 11, 42 + yo, 1, 5, p.line);
  PX.r(ctx, 19, 42 + yo, 1, 5, p.line);
  PX.r(ctx, 12, 42 + yo, 7, 1, p.line);
  PX.r(ctx, 12, 46 + yo, 7, 1, p.line);
  PX.r(ctx, 12, 42 + yo, 7, 1, p.helmet);
  PX.r(ctx, 13, 43 + yo, 1, 3, p.leatherD);
  // Right
  PX.r(ctx, 45, 42 + yo, 7, 5, p.leather);
  PX.r(ctx, 44, 42 + yo, 1, 5, p.line);
  PX.r(ctx, 52, 42 + yo, 1, 5, p.line);
  PX.r(ctx, 45, 42 + yo, 7, 1, p.line);
  PX.r(ctx, 45, 46 + yo, 7, 1, p.line);
  PX.r(ctx, 45, 42 + yo, 7, 1, p.helmet);
  PX.r(ctx, 50, 43 + yo, 1, 3, p.leatherD);

  /* LEGS */
  // Left
  PX.r(ctx, 22, 46 + yo, 8, 12, p.suit);
  PX.r(ctx, 21, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 30, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 22, 46 + yo, 1, 12, p.suitD);
  PX.r(ctx, 29, 46 + yo, 1, 12, p.suitL);
  // Right
  PX.r(ctx, 34, 46 + yo, 8, 12, p.suit);
  PX.r(ctx, 33, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 42, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 34, 46 + yo, 1, 12, p.suitD);
  PX.r(ctx, 41, 46 + yo, 1, 12, p.suitL);
  // Knee stripe (chrome flash)
  PX.r(ctx, 23, 51 + yo, 6, 1, p.chrome);
  PX.r(ctx, 35, 51 + yo, 6, 1, p.chrome);
  PX.r(ctx, 23, 52 + yo, 6, 1, p.chromeD);
  PX.r(ctx, 35, 52 + yo, 6, 1, p.chromeD);

  /* BOOTS */
  // Left
  PX.r(ctx, 21, 58 + yo, 10, 4, p.leather);
  PX.r(ctx, 20, 58 + yo, 1, 4, p.line);
  PX.r(ctx, 31, 58 + yo, 1, 4, p.line);
  PX.r(ctx, 21, 58 + yo, 10, 1, p.helmet);  // brass cuff
  PX.r(ctx, 21, 62 + yo, 10, 1, p.line);
  PX.r(ctx, 22, 60 + yo, 8, 1, p.leatherD);  // tread
  // Right
  PX.r(ctx, 33, 58 + yo, 10, 4, p.leather);
  PX.r(ctx, 32, 58 + yo, 1, 4, p.line);
  PX.r(ctx, 43, 58 + yo, 1, 4, p.line);
  PX.r(ctx, 33, 58 + yo, 10, 1, p.helmet);
  PX.r(ctx, 33, 62 + yo, 10, 1, p.line);
  PX.r(ctx, 34, 60 + yo, 8, 1, p.leatherD);

  ctx.restore();

  /* POWER — backward speed-streaks + after-image */
  if (mode === 'power') {
    for (let i = 0; i < 6; i++) {
      const lineY = 28 + i * 5;
      const len = 14 - i;
      PX.r(ctx, 0, lineY, len, 1, p.suitL);
      PX.r(ctx, 0, lineY + 1, Math.max(2, len - 4), 1, p.chrome);
    }
    // Lightning bolt ghost
    [[3, 32], [1, 38], [4, 44]].forEach(([x, y]) => {
      PX.r(ctx, x, y, 2, 1, p.chrome);
      PX.r(ctx, x - 1, y + 1, 2, 1, p.chrome);
      PX.r(ctx, x + 1, y + 2, 2, 1, p.chrome);
    });
  }
}

/* ════════════════════════════════════════════════════════════════════
   2. NIMBUS (codename SUPERMAN) — heroic flyer, teal suit + cream cape.
   ════════════════════════════════════════════════════════════════════ */

function drawNimbusV3(ctx, frame, mode, t) {
  const p = {
    skin:'#f5d1a3', skinSh:'#c98555', skinHi:'#ffe6c4',
    suit:'#1e7a96', suitD:'#0e3a50', suitL:'#3aaad0',
    cape:'#f0eee0', capeSh:'#b8b6a8', capeHi:'#ffffff',
    brass:'#d4a834', brassD:'#7e6014', brassL:'#ffe06a',
    hair:'#1f1208', hairSh:'#0a0402', hairHi:'#3a2818',
    boot:'#0a1e2c', bootHi:'#1e3a50',
    line:'#040c14',
  };
  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  if (mode === 'power') yo = -8 - Math.round(Math.sin(t * Math.PI) * 5);

  // Shadow shrinks during flight
  const shW = mode === 'power' ? Math.max(8, 22 - Math.abs(yo)) : 22;
  const shA = mode === 'power' ? 0.18 : 0.38;
  shadowOval(ctx, 32, 60, shW, shA);

  /* CAPE — drawn first (behind body). Short mantle style. */
  // Cape volume behind shoulders
  if (mode === 'power') {
    // Billowing flight cape — spreads outward
    PX.r(ctx, 8, 24 + yo, 12, 22, p.cape);
    PX.r(ctx, 44, 24 + yo, 12, 22, p.cape);
    PX.r(ctx, 7, 28 + yo, 1, 16, p.line);
    PX.r(ctx, 56, 28 + yo, 1, 16, p.line);
    PX.r(ctx, 8, 24 + yo, 12, 1, p.line);
    PX.r(ctx, 44, 24 + yo, 12, 1, p.line);
    PX.r(ctx, 8, 45 + yo, 12, 1, p.line);
    PX.r(ctx, 44, 45 + yo, 12, 1, p.line);
    // Cape inner fold shadow
    PX.r(ctx, 8, 24 + yo, 1, 22, p.capeSh);
    PX.r(ctx, 55, 24 + yo, 1, 22, p.capeSh);
    PX.r(ctx, 12, 26 + yo, 1, 18, p.capeSh);
    PX.r(ctx, 51, 26 + yo, 1, 18, p.capeSh);
  } else {
    // Hanging short mantle
    PX.r(ctx, 14, 25 + yo, 36, 22, p.cape);
    PX.r(ctx, 13, 26 + yo, 1, 20, p.line);
    PX.r(ctx, 50, 26 + yo, 1, 20, p.line);
    PX.r(ctx, 14, 25 + yo, 36, 1, p.line);
    PX.r(ctx, 14, 46 + yo, 36, 1, p.line);
    // Fold shading
    PX.r(ctx, 14, 25 + yo, 1, 21, p.capeSh);
    PX.r(ctx, 49, 25 + yo, 1, 21, p.capeSh);
    PX.r(ctx, 25, 26 + yo, 1, 19, p.capeSh);
    PX.r(ctx, 38, 26 + yo, 1, 19, p.capeSh);
  }

  /* LEGS */
  PX.r(ctx, 22, 46 + yo, 8, 12, p.suit);
  PX.r(ctx, 34, 46 + yo, 8, 12, p.suit);
  PX.r(ctx, 21, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 30, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 33, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 42, 46 + yo, 1, 12, p.line);
  PX.r(ctx, 22, 46 + yo, 1, 12, p.suitD);
  PX.r(ctx, 29, 46 + yo, 1, 12, p.suitL);
  PX.r(ctx, 34, 46 + yo, 1, 12, p.suitD);
  PX.r(ctx, 41, 46 + yo, 1, 12, p.suitL);

  /* BOOTS — knee-height with brass cuff */
  PX.r(ctx, 21, 54 + yo, 10, 8, p.boot);
  PX.r(ctx, 33, 54 + yo, 10, 8, p.boot);
  PX.r(ctx, 20, 54 + yo, 1, 8, p.line);
  PX.r(ctx, 31, 54 + yo, 1, 8, p.line);
  PX.r(ctx, 32, 54 + yo, 1, 8, p.line);
  PX.r(ctx, 43, 54 + yo, 1, 8, p.line);
  PX.r(ctx, 21, 54 + yo, 10, 1, p.brass);
  PX.r(ctx, 33, 54 + yo, 10, 1, p.brass);
  PX.r(ctx, 21, 62 + yo, 10, 1, p.line);
  PX.r(ctx, 33, 62 + yo, 10, 1, p.line);
  PX.r(ctx, 21, 55 + yo, 1, 7, p.bootHi);
  PX.r(ctx, 33, 55 + yo, 1, 7, p.bootHi);

  /* TORSO */
  PX.r(ctx, 18, 25 + yo, 28, 18, p.suit);
  PX.r(ctx, 17, 26 + yo, 1, 17, p.line);
  PX.r(ctx, 46, 26 + yo, 1, 17, p.line);
  PX.r(ctx, 18, 25 + yo, 28, 1, p.line);
  PX.r(ctx, 18, 42 + yo, 28, 1, p.line);
  // Pectoral shading
  PX.r(ctx, 18, 25 + yo, 1, 18, p.suitD);
  PX.r(ctx, 45, 25 + yo, 1, 18, p.suitL);
  // Pec definition
  PX.r(ctx, 19, 27 + yo, 12, 8, p.suitL);
  PX.r(ctx, 33, 27 + yo, 12, 8, p.suitL);
  PX.r(ctx, 31, 27 + yo, 2, 12, p.suitD);
  // Center chest seam
  PX.r(ctx, 31, 26 + yo, 2, 16, p.suitD);

  /* BELT — heavy brass plate */
  PX.r(ctx, 17, 43 + yo, 30, 4, p.brass);
  PX.r(ctx, 17, 43 + yo, 30, 1, p.line);
  PX.r(ctx, 17, 47 + yo, 30, 1, p.line);
  PX.r(ctx, 17, 43 + yo, 1, 4, p.line);
  PX.r(ctx, 46, 43 + yo, 1, 4, p.line);
  PX.r(ctx, 18, 44 + yo, 28, 1, p.brassL);
  PX.r(ctx, 18, 46 + yo, 28, 1, p.brassD);
  // Buckle gem
  PX.r(ctx, 29, 43 + yo, 6, 4, p.brassD);
  PX.r(ctx, 30, 44 + yo, 4, 2, p.brassL);
  PX.r(ctx, 31, 45 + yo, 2, 1, '#ffffff');

  /* ARMS */
  PX.r(ctx, 13, 28 + yo, 5, 14, p.suit);
  PX.r(ctx, 46, 28 + yo, 5, 14, p.suit);
  PX.r(ctx, 12, 28 + yo, 1, 14, p.line);
  PX.r(ctx, 51, 28 + yo, 1, 14, p.line);
  PX.r(ctx, 13, 28 + yo, 1, 14, p.suitD);
  PX.r(ctx, 50, 28 + yo, 1, 14, p.suitL);
  PX.r(ctx, 17, 28 + yo, 1, 14, p.suitL);
  PX.r(ctx, 46, 28 + yo, 1, 14, p.suitD);
  // Hands
  PX.r(ctx, 12, 42 + yo, 7, 4, p.skin);
  PX.r(ctx, 45, 42 + yo, 7, 4, p.skin);
  PX.r(ctx, 11, 42 + yo, 1, 4, p.line);
  PX.r(ctx, 19, 42 + yo, 1, 4, p.line);
  PX.r(ctx, 44, 42 + yo, 1, 4, p.line);
  PX.r(ctx, 52, 42 + yo, 1, 4, p.line);
  PX.r(ctx, 12, 45 + yo, 7, 1, p.line);
  PX.r(ctx, 45, 45 + yo, 7, 1, p.line);
  PX.r(ctx, 12, 42 + yo, 7, 1, p.skinHi);
  PX.r(ctx, 45, 42 + yo, 7, 1, p.skinHi);

  /* NECK */
  PX.r(ctx, 28, 22 + yo, 8, 3, p.skinSh);
  PX.r(ctx, 27, 22 + yo, 1, 3, p.line);
  PX.r(ctx, 36, 22 + yo, 1, 3, p.line);

  /* HEAD */
  PX.r(ctx, 21, 4 + yo, 22, 18, p.skin);
  PX.r(ctx, 20, 5 + yo, 1, 16, p.line);
  PX.r(ctx, 43, 5 + yo, 1, 16, p.line);
  PX.r(ctx, 21, 4 + yo, 22, 1, p.line);
  PX.r(ctx, 21, 21 + yo, 22, 1, p.line);
  // Face shading
  PX.r(ctx, 21, 5 + yo, 1, 16, p.skinSh);
  PX.r(ctx, 42, 5 + yo, 1, 16, p.skinSh);
  PX.r(ctx, 22, 20 + yo, 20, 1, p.skinSh);
  // Cheek highlight
  PX.r(ctx, 23, 18 + yo, 2, 1, p.skinHi);
  PX.r(ctx, 39, 18 + yo, 2, 1, p.skinHi);

  /* HAIR — short, side-parted, with iconic forelock (single front lock) */
  PX.r(ctx, 21, 4 + yo, 22, 5, p.hair);
  PX.r(ctx, 20, 5 + yo, 1, 4, p.hair);
  PX.r(ctx, 43, 5 + yo, 1, 4, p.hair);
  PX.r(ctx, 21, 4 + yo, 22, 1, p.hairSh);
  // Sideburns
  PX.r(ctx, 20, 9 + yo, 2, 3, p.hair);
  PX.r(ctx, 42, 9 + yo, 2, 3, p.hair);
  // Front spike forelock
  PX.r(ctx, 27, 9 + yo, 2, 2, p.hair);
  PX.r(ctx, 28, 11 + yo, 1, 1, p.hair);
  // Hair highlight
  PX.r(ctx, 24, 5 + yo, 10, 1, p.hairHi);
  PX.r(ctx, 27, 6 + yo, 6, 1, p.hairHi);

  /* EYES — determined, with bright iris */
  PX.r(ctx, 23, 13 + yo, 6, 3, p.line);
  PX.r(ctx, 35, 13 + yo, 6, 3, p.line);
  // Eye whites
  PX.r(ctx, 24, 14 + yo, 4, 2, '#ffffff');
  PX.r(ctx, 36, 14 + yo, 4, 2, '#ffffff');
  // Iris
  PX.r(ctx, 25, 14 + yo, 2, 2, p.suitL);
  PX.r(ctx, 37, 14 + yo, 2, 2, p.suitL);
  // Pupil
  PX.r(ctx, 26, 14 + yo, 1, 1, p.line);
  PX.r(ctx, 38, 14 + yo, 1, 1, p.line);
  // Brow line
  PX.r(ctx, 23, 12 + yo, 6, 1, p.hair);
  PX.r(ctx, 35, 12 + yo, 6, 1, p.hair);

  /* MOUTH — firm */
  PX.r(ctx, 28, 19 + yo, 8, 1, p.line);
  PX.r(ctx, 27, 19 + yo, 1, 1, p.skinSh);
  PX.r(ctx, 36, 19 + yo, 1, 1, p.skinSh);

  /* POWER — flight sparkles + wind streaks */
  if (mode === 'power') {
    const sparkles = [[8, 22], [54, 26], [4, 38], [58, 42], [10, 50], [52, 18]];
    sparkles.forEach(([sx, sy], i) => {
      if ((frame + i) % 3 === 0) return;
      PX.r(ctx, sx, sy, 1, 1, p.capeHi);
      PX.r(ctx, sx + 1, sy + 1, 1, 1, p.brassL);
      PX.r(ctx, sx - 1, sy + 1, 1, 1, p.brassL);
      PX.r(ctx, sx, sy + 2, 1, 1, p.capeHi);
    });
    // Wind streaks under feet (where the shadow used to be)
    PX.r(ctx, 16, 61, 6, 1, p.suitL);
    PX.r(ctx, 28, 62, 8, 1, p.suitL);
    PX.r(ctx, 42, 61, 6, 1, p.suitL);
  }
}

/* ════════════════════════════════════════════════════════════════════
   3. AEGIS (codename IRONMAN) — armored exoskeleton, crimson + brass.
   ════════════════════════════════════════════════════════════════════ */

function drawAegisV3(ctx, frame, mode, t) {
  const p = {
    armor:'#c4382a', armorD:'#7a1808', armorL:'#ff5e44', armorHi:'#ffae9a',
    brass:'#d4a834', brassD:'#7e6014', brassL:'#ffe06a',
    core:'#5be8f5', coreL:'#a8f4ff', coreD:'#1a8a98',
    visor:'#1a0a04', visorL:'#5be8f5',
    seal:'#3a1408',
    line:'#0a0402',
  };
  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  if (mode === 'power') yo = -6 - Math.round(Math.sin(t * Math.PI) * 4);

  const shW = mode === 'power' ? Math.max(8, 22 - Math.abs(yo)) : 22;
  const shA = mode === 'power' ? 0.2 : 0.4;
  shadowOval(ctx, 32, 60, shW, shA);

  /* HELMET — full enclosed, no skin showing */
  // Crown
  PX.r(ctx, 22, 3 + yo, 20, 1, p.armor);
  PX.r(ctx, 21, 4 + yo, 22, 1, p.armor);
  PX.r(ctx, 20, 5 + yo, 24, 18, p.armor);
  PX.r(ctx, 22, 3 + yo, 20, 1, p.line);
  PX.r(ctx, 21, 4 + yo, 1, 1, p.line);  PX.r(ctx, 42, 4 + yo, 1, 1, p.line);
  PX.r(ctx, 20, 5 + yo, 1, 18, p.line);
  PX.r(ctx, 43, 5 + yo, 1, 18, p.line);
  PX.r(ctx, 21, 22 + yo, 22, 1, p.line);
  // Top highlights
  PX.r(ctx, 22, 5 + yo, 4, 14, p.armorL);
  PX.r(ctx, 22, 4 + yo, 16, 1, p.armorHi);
  PX.r(ctx, 23, 5 + yo, 14, 1, p.armorL);
  // Right shadow
  PX.r(ctx, 41, 5 + yo, 2, 18, p.armorD);
  // Brass forehead trim
  PX.r(ctx, 21, 7 + yo, 22, 2, p.brass);
  PX.r(ctx, 21, 7 + yo, 22, 1, p.brassL);
  PX.r(ctx, 21, 8 + yo, 22, 1, p.brassD);
  // Crown decorative ridge
  PX.r(ctx, 28, 3 + yo, 8, 2, p.brass);
  PX.r(ctx, 28, 3 + yo, 8, 1, p.brassL);
  PX.r(ctx, 30, 4 + yo, 4, 1, p.brassD);

  /* VISOR — horizontal slit (not T-shape) */
  PX.r(ctx, 21, 12 + yo, 22, 5, p.visor);
  PX.r(ctx, 21, 12 + yo, 22, 1, p.line);
  PX.r(ctx, 21, 16 + yo, 22, 1, p.line);
  PX.r(ctx, 22, 13 + yo, 20, 3, p.visorL);
  // Visor inner shadow strips
  PX.r(ctx, 22, 13 + yo, 20, 1, p.coreL);
  PX.r(ctx, 22, 15 + yo, 20, 1, p.coreD);
  // Pupil-like dots inside visor for "eyes"
  PX.r(ctx, 25, 14 + yo, 3, 1, '#ffffff');
  PX.r(ctx, 36, 14 + yo, 3, 1, '#ffffff');

  /* JAW vent (grill) */
  for (let i = 0; i < 5; i++) {
    PX.r(ctx, 24 + i * 3, 18 + yo, 2, 1, p.brassD);
  }
  PX.r(ctx, 24, 19 + yo, 16, 1, p.line);
  // Chin bevel
  PX.r(ctx, 28, 20 + yo, 8, 2, p.armorD);

  /* NECK SEAL — articulated joint */
  PX.r(ctx, 27, 23 + yo, 10, 3, p.seal);
  PX.r(ctx, 26, 23 + yo, 1, 3, p.line);
  PX.r(ctx, 37, 23 + yo, 1, 3, p.line);
  PX.r(ctx, 27, 24 + yo, 10, 1, p.brassD);

  /* SHOULDER PAULDRONS — flared armor plates */
  // Left pauldron
  PX.r(ctx, 12, 25 + yo, 8, 8, p.armor);
  PX.r(ctx, 11, 26 + yo, 1, 7, p.line);
  PX.r(ctx, 12, 25 + yo, 8, 1, p.line);
  PX.r(ctx, 12, 32 + yo, 8, 1, p.line);
  PX.r(ctx, 12, 25 + yo, 1, 8, p.armorD);
  PX.r(ctx, 13, 26 + yo, 6, 1, p.armorHi);
  PX.r(ctx, 13, 26 + yo, 1, 6, p.armorL);
  // Right pauldron
  PX.r(ctx, 44, 25 + yo, 8, 8, p.armor);
  PX.r(ctx, 52, 26 + yo, 1, 7, p.line);
  PX.r(ctx, 44, 25 + yo, 8, 1, p.line);
  PX.r(ctx, 44, 32 + yo, 8, 1, p.line);
  PX.r(ctx, 51, 25 + yo, 1, 8, p.armorD);
  PX.r(ctx, 45, 26 + yo, 6, 1, p.armorHi);
  PX.r(ctx, 50, 26 + yo, 1, 6, p.armorD);

  /* TORSO PLATE */
  PX.r(ctx, 20, 26 + yo, 24, 17, p.armor);
  PX.r(ctx, 19, 27 + yo, 1, 16, p.line);
  PX.r(ctx, 44, 27 + yo, 1, 16, p.line);
  PX.r(ctx, 20, 26 + yo, 24, 1, p.line);
  PX.r(ctx, 20, 42 + yo, 24, 1, p.line);
  // Pec plate split
  PX.r(ctx, 20, 27 + yo, 11, 10, p.armorL);
  PX.r(ctx, 33, 27 + yo, 11, 10, p.armorL);
  // Center seam (dark)
  PX.r(ctx, 31, 26 + yo, 2, 17, p.armorD);
  PX.r(ctx, 30, 28 + yo, 4, 1, p.line);
  PX.r(ctx, 30, 37 + yo, 4, 1, p.line);
  // Ab plates (3 horizontal bands)
  PX.r(ctx, 21, 38 + yo, 22, 1, p.armorD);
  PX.r(ctx, 21, 40 + yo, 22, 1, p.armorD);

  /* CYAN REACTOR CORE — circular, glowing */
  // Outer brass ring
  for (let i = 0; i < 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    const x = Math.round(32 + Math.cos(a) * 5);
    const y = Math.round(33 + yo + Math.sin(a) * 5);
    PX.r(ctx, x, y, 1, 1, p.brass);
  }
  PX.circle(ctx, 32, 33 + yo, 4, p.brassD);
  PX.circle(ctx, 32, 33 + yo, 3, p.core);
  PX.circle(ctx, 32, 33 + yo, 2, p.coreL);
  PX.r(ctx, 32, 33 + yo, 1, 1, '#ffffff');

  /* PELVIS GIRDLE */
  PX.r(ctx, 19, 43 + yo, 26, 5, p.brass);
  PX.r(ctx, 19, 43 + yo, 26, 1, p.line);
  PX.r(ctx, 19, 47 + yo, 26, 1, p.line);
  PX.r(ctx, 19, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 44, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 20, 44 + yo, 24, 1, p.brassL);
  PX.r(ctx, 20, 46 + yo, 24, 1, p.brassD);
  // Buckle pad
  PX.r(ctx, 29, 43 + yo, 6, 5, p.armor);
  PX.r(ctx, 30, 44 + yo, 4, 3, p.armorL);
  PX.r(ctx, 31, 45 + yo, 2, 1, '#ffffff');

  /* ARMS — armored gauntlets */
  PX.r(ctx, 12, 33 + yo, 6, 10, p.armor);
  PX.r(ctx, 46, 33 + yo, 6, 10, p.armor);
  PX.r(ctx, 11, 33 + yo, 1, 10, p.line);
  PX.r(ctx, 52, 33 + yo, 1, 10, p.line);
  PX.r(ctx, 12, 33 + yo, 1, 10, p.armorD);
  PX.r(ctx, 17, 33 + yo, 1, 10, p.armorL);
  PX.r(ctx, 46, 33 + yo, 1, 10, p.armorL);
  PX.r(ctx, 51, 33 + yo, 1, 10, p.armorD);
  // Forearm band
  PX.r(ctx, 12, 37 + yo, 6, 2, p.brass);
  PX.r(ctx, 46, 37 + yo, 6, 2, p.brass);
  PX.r(ctx, 12, 37 + yo, 6, 1, p.brassL);

  /* HANDS — gauntlets with repulsor */
  PX.r(ctx, 11, 43 + yo, 8, 5, p.armor);
  PX.r(ctx, 45, 43 + yo, 8, 5, p.armor);
  PX.r(ctx, 10, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 19, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 44, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 53, 43 + yo, 1, 5, p.line);
  PX.r(ctx, 11, 43 + yo, 8, 1, p.line);
  PX.r(ctx, 45, 43 + yo, 8, 1, p.line);
  PX.r(ctx, 11, 47 + yo, 8, 1, p.line);
  PX.r(ctx, 45, 47 + yo, 8, 1, p.line);
  // Repulsor center
  PX.circle(ctx, 15, 45 + yo, 1, p.core);
  PX.circle(ctx, 49, 45 + yo, 1, p.core);
  PX.r(ctx, 15, 45 + yo, 1, 1, p.coreL);
  PX.r(ctx, 49, 45 + yo, 1, 1, p.coreL);

  /* LEGS — armored */
  PX.r(ctx, 22, 48 + yo, 8, 11, p.armor);
  PX.r(ctx, 34, 48 + yo, 8, 11, p.armor);
  PX.r(ctx, 21, 48 + yo, 1, 11, p.line);
  PX.r(ctx, 30, 48 + yo, 1, 11, p.line);
  PX.r(ctx, 33, 48 + yo, 1, 11, p.line);
  PX.r(ctx, 42, 48 + yo, 1, 11, p.line);
  PX.r(ctx, 22, 48 + yo, 1, 11, p.armorD);
  PX.r(ctx, 29, 48 + yo, 1, 11, p.armorL);
  PX.r(ctx, 34, 48 + yo, 1, 11, p.armorD);
  PX.r(ctx, 41, 48 + yo, 1, 11, p.armorL);
  // Knee plates (brass)
  PX.r(ctx, 23, 52 + yo, 6, 2, p.brass);
  PX.r(ctx, 35, 52 + yo, 6, 2, p.brass);
  PX.r(ctx, 23, 52 + yo, 6, 1, p.brassL);
  PX.r(ctx, 23, 53 + yo, 6, 1, p.brassD);
  PX.r(ctx, 35, 52 + yo, 6, 1, p.brassL);
  PX.r(ctx, 35, 53 + yo, 6, 1, p.brassD);

  /* BOOTS — thruster ports below */
  PX.r(ctx, 21, 59 + yo, 10, 4, p.armor);
  PX.r(ctx, 33, 59 + yo, 10, 4, p.armor);
  PX.r(ctx, 20, 59 + yo, 1, 4, p.line);
  PX.r(ctx, 31, 59 + yo, 1, 4, p.line);
  PX.r(ctx, 32, 59 + yo, 1, 4, p.line);
  PX.r(ctx, 43, 59 + yo, 1, 4, p.line);
  PX.r(ctx, 21, 59 + yo, 10, 1, p.brass);
  PX.r(ctx, 33, 59 + yo, 10, 1, p.brass);
  PX.r(ctx, 21, 63 + yo, 10, 1, p.line);
  PX.r(ctx, 33, 63 + yo, 10, 1, p.line);

  /* POWER — jet flames + repulsor glow */
  if (mode === 'power') {
    // Boot jets
    FX.jetFlame(ctx, 24, 63, frame, '#ff9020', '#ffd84a', '#fff5c4');
    FX.jetFlame(ctx, 36, 63, frame, '#ff9020', '#ffd84a', '#fff5c4');
    // Palm repulsor blast (left + right)
    PX.r(ctx, 13, 48 + yo, 4, 4, p.coreL);
    PX.r(ctx, 47, 48 + yo, 4, 4, p.coreL);
    PX.r(ctx, 14, 49 + yo, 2, 2, '#ffffff');
    PX.r(ctx, 48, 49 + yo, 2, 2, '#ffffff');
    // Core glow ring
    PX.circle(ctx, 32, 33 + yo, 6, p.core);
    PX.circle(ctx, 32, 33 + yo, 4, p.coreL);
    PX.circle(ctx, 32, 33 + yo, 2, '#ffffff');
  }
}

/* ════════════════════════════════════════════════════════════════════
   REGISTRY v3
   ════════════════════════════════════════════════════════════════════ */

const V3 = [
  {
    id:'velox', codename:'FLASH', name:'Velox',
    role:'L1 — Analista de momentum',
    palette:['#c47020','#e89818','#fff3c4','#ffae3a','#0e0703'],
    powerLabel:'Super-velocidade',
    draw: drawVeloxV3,
  },
  {
    id:'nimbus', codename:'SUPERMAN', name:'Nimbus',
    role:'L1 — Sinal forward',
    palette:['#1e7a96','#f0eee0','#d4a834','#1f1208','#040c14'],
    powerLabel:'Voo',
    draw: drawNimbusV3,
  },
  {
    id:'aegis', codename:'IRONMAN', name:'Aegis',
    role:'L3 — Execução',
    palette:['#c4382a','#d4a834','#5be8f5','#7a1808','#0a0402'],
    powerLabel:'Propulsão a jato',
    draw: drawAegisV3,
  },
];

window.SPRITES_V3 = {
  size: SPRITE_V3,
  list: V3,
};

})();
