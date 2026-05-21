/* Original trader sprites — drawn pixel by pixel on a 48×48 logical canvas.
   Each definition exposes:
     { name, codename, role, palette, powerLabel,
       draw(ctx, frame, mode, t)  → renders sprite + any in-place effects }
   Sprite occupies center of canvas; feet land around y=42, head crown ~y=3.
*/
(function () {

const SPRITE_SIZE = 48;

/* ───────────────────────────────────────────────────────────────
   HELPERS — chibi body parts shared across characters
   ─────────────────────────────────────────────────────────────── */

function outlineRect(ctx, x, y, w, h, fill, dark, light) {
  PX.r(ctx, x, y, w, h, fill);
  if (dark) {
    PX.r(ctx, x, y + h - 1, w, 1, dark);
    PX.r(ctx, x + w - 1, y, 1, h, dark);
  }
  if (light) {
    PX.r(ctx, x, y, w, 1, light);
    PX.r(ctx, x, y, 1, h, light);
  }
}

/* Standard chibi head silhouette (rounded square). Returns face bounds. */
function drawHead(ctx, yo, p) {
  // Hair/helmet area drawn separately; this is just the skin face.
  // Face: y=7..18, x=16..31 (16 wide, 12 tall) with rounded corners
  PX.r(ctx, 17, 6 + yo, 14, 1, p.skin);
  PX.r(ctx, 16, 7 + yo, 16, 11, p.skin);
  PX.r(ctx, 17, 18 + yo, 14, 1, p.skin);
  // Side shading
  PX.r(ctx, 16, 8 + yo, 1, 10, p.skinShade);
  PX.r(ctx, 31, 8 + yo, 1, 10, p.skinShade);
  // Chin shadow
  PX.r(ctx, 17, 17 + yo, 14, 1, p.skinShade);
}

function drawNeck(ctx, yo, p) {
  PX.r(ctx, 22, 19 + yo, 4, 2, p.skinShade);
}

/* Standard chibi torso block. Caller draws costume detail on top. */
function drawTorso(ctx, yo, p, suit) {
  PX.r(ctx, 16, 21 + yo, 16, 13, suit);
  PX.r(ctx, 16, 21 + yo, 1, 13, p.outline);
  PX.r(ctx, 31, 21 + yo, 1, 13, p.outline);
  PX.r(ctx, 16, 33 + yo, 16, 1, p.outline);
}

function drawArms(ctx, yo, p, sleeve, withHands = true) {
  PX.r(ctx, 13, 22 + yo, 3, 8, sleeve);
  PX.r(ctx, 32, 22 + yo, 3, 8, sleeve);
  PX.r(ctx, 13, 22 + yo, 1, 8, p.outline);
  PX.r(ctx, 34, 22 + yo, 1, 8, p.outline);
  if (withHands) {
    PX.r(ctx, 13, 30 + yo, 3, 3, p.skin);
    PX.r(ctx, 32, 30 + yo, 3, 3, p.skin);
    PX.r(ctx, 13, 32 + yo, 3, 1, p.outline);
    PX.r(ctx, 32, 32 + yo, 3, 1, p.outline);
  }
}

function drawLegs(ctx, yo, p, pants, boot) {
  // standing pose, two legs side by side
  PX.r(ctx, 18, 34 + yo, 5, 7, pants);
  PX.r(ctx, 25, 34 + yo, 5, 7, pants);
  PX.r(ctx, 18, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 29, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 22, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 25, 34 + yo, 1, 7, p.outline);
  // boots
  PX.r(ctx, 17, 41 + yo, 7, 2, boot);
  PX.r(ctx, 24, 41 + yo, 7, 2, boot);
  PX.r(ctx, 17, 42 + yo, 14, 1, p.outline);
  PX.r(ctx, 17, 41 + yo, 1, 2, p.outline);
  PX.r(ctx, 23, 41 + yo, 1, 2, p.outline);
  PX.r(ctx, 24, 41 + yo, 1, 2, p.outline);
  PX.r(ctx, 30, 41 + yo, 1, 2, p.outline);
}

function drawShadow(ctx, w, opacity) {
  PX.shadow(ctx, 24, 44, w, opacity);
}

function drawEyesOpen(ctx, yo, p, lx, rx, ly, lensColor) {
  // simple oval eyes with highlight
  PX.r(ctx, lx, ly + yo, 2, 3, p.outline);
  PX.r(ctx, rx, ly + yo, 2, 3, p.outline);
  PX.r(ctx, lx, ly + yo + 1, 2, 1, lensColor || '#fff');
  PX.r(ctx, rx, ly + yo + 1, 2, 1, lensColor || '#fff');
}

function drawMouth(ctx, yo, p, x, y, w) {
  PX.r(ctx, x, y + yo, w, 1, p.outline);
}

/* ───────────────────────────────────────────────────────────────
   1. FLASH  →  codename "Velox" (speedster)
   Original design: amber running suit, ribbed cowl with side fins, chevron stripe.
   ─────────────────────────────────────────────────────────────── */

function drawFlash(ctx, frame, mode, t) {
  const p = {
    skin: '#f4c694', skinShade: '#c98a55',
    suit: '#e89a2a', suitDark: '#8c5210', suitLight: '#ffce58',
    helmet: '#b87114', helmetDark: '#5e3608',
    chev:  '#fff3c4',
    goggle: '#221708', lens: '#9ee9ff',
    boot:  '#5a3008',
    outline: '#1a0d04',
  };
  const yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;

  // Power = dash, leans forward, body tilts slightly via offset only (rotation
  // is handled at card level via afterimages).
  drawShadow(ctx, mode === 'power' ? 10 : 14, 0.35);

  // Legs — running pose during power
  if (mode === 'power') {
    // front leg forward + lifted, back leg planted
    PX.r(ctx, 19, 34 + yo, 5, 5, p.suit);  PX.r(ctx, 19, 34 + yo, 1, 5, p.outline);
    PX.r(ctx, 25, 36 + yo, 5, 5, p.suit);  PX.r(ctx, 29, 36 + yo, 1, 5, p.outline);
    PX.r(ctx, 18, 39 + yo, 7, 2, p.boot);  PX.r(ctx, 18, 40 + yo, 7, 1, p.outline);
    PX.r(ctx, 24, 41 + yo, 7, 2, p.boot);  PX.r(ctx, 24, 42 + yo, 7, 1, p.outline);
  } else {
    drawLegs(ctx, yo, p, p.suit, p.boot);
  }

  drawTorso(ctx, yo, p, p.suit);
  // chevron stripe down center
  PX.r(ctx, 23, 22 + yo, 2, 11, p.chev);
  PX.r(ctx, 22, 25 + yo, 4, 1, p.chev);
  PX.r(ctx, 21, 27 + yo, 6, 1, p.chev);
  // side shading
  PX.r(ctx, 17, 21 + yo, 1, 12, p.suitDark);
  PX.r(ctx, 30, 21 + yo, 1, 12, p.suitDark);
  // belt
  PX.r(ctx, 16, 32 + yo, 16, 2, p.helmetDark);
  PX.r(ctx, 23, 32 + yo, 2, 2, p.chev);

  drawArms(ctx, yo, p, p.suit);
  drawNeck(ctx, yo, p);
  drawHead(ctx, yo, p);

  // Cowl/helmet — top of head with side fins (winged-cap silhouette)
  PX.r(ctx, 15, 5 + yo, 18, 5, p.helmet);
  PX.r(ctx, 16, 4 + yo, 16, 1, p.helmet);
  PX.r(ctx, 15, 5 + yo, 18, 1, p.outline);
  PX.r(ctx, 16, 4 + yo, 16, 1, p.outline);
  PX.r(ctx, 15, 9 + yo, 18, 1, p.helmetDark);
  // side fins (wing-like flares)
  PX.r(ctx, 12, 8 + yo, 3, 4, p.helmet);
  PX.r(ctx, 33, 8 + yo, 3, 4, p.helmet);
  PX.r(ctx, 12, 8 + yo, 1, 4, p.outline);
  PX.r(ctx, 35, 8 + yo, 1, 4, p.outline);
  PX.r(ctx, 12, 11 + yo, 3, 1, p.outline);
  PX.r(ctx, 33, 11 + yo, 3, 1, p.outline);
  // helmet chevron accent
  PX.r(ctx, 23, 6 + yo, 2, 3, p.chev);

  // Goggles (built into cowl) — large amber lenses
  PX.r(ctx, 17, 11 + yo, 6, 4, p.goggle);
  PX.r(ctx, 25, 11 + yo, 6, 4, p.goggle);
  PX.r(ctx, 23, 12 + yo, 2, 2, p.goggle);
  PX.r(ctx, 18, 12 + yo, 4, 2, p.lens);
  PX.r(ctx, 26, 12 + yo, 4, 2, p.lens);
  PX.r(ctx, 18, 12 + yo, 1, 1, '#fff');
  PX.r(ctx, 26, 12 + yo, 1, 1, '#fff');
  // mouth
  drawMouth(ctx, yo, p, 22, 17, 4);

  // POWER effect — lightning bolt trail behind
  if (mode === 'power') {
    FX.speedLines(ctx, 0, 24, 12, 4, '#ffd84a');
    FX.bolt(ctx, 3, 28, '#ffd84a');
    FX.bolt(ctx, 8, 36, '#ffd84a');
  }
}

/* ───────────────────────────────────────────────────────────────
   2. SUPERMAN  →  codename "Nimbus" (flyer)
   Original: teal flight suit, simple white half-cape, brass belt.
   ─────────────────────────────────────────────────────────────── */

function drawSuperman(ctx, frame, mode, t) {
  const p = {
    skin: '#f7d1a3', skinShade: '#c98555',
    suit: '#1e6f8c', suitDark: '#0e3d50', suitLight: '#3a9bb8',
    cape: '#f0f2ec', capeShade: '#c4c8be',
    belt: '#c8a23a', beltDark: '#86651a',
    hair: '#2a1a0d', hairShade: '#120802',
    boot: '#0a2530',
    outline: '#06141d',
  };
  const flying = mode === 'power';
  // breathing for idle; lift offset for power
  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  if (flying) yo = -6 - Math.floor(Math.sin(t * Math.PI) * 4);

  // Shadow shrinks as he lifts
  const shadowW = flying ? Math.max(6, 14 - Math.abs(yo)) : 14;
  const shadowAlpha = flying ? 0.18 : 0.35;
  drawShadow(ctx, shadowW, shadowAlpha);

  // Cape — drawn first (behind body)
  if (flying) {
    // billowing back during flight
    PX.r(ctx, 12, 19 + yo, 6, 18, p.cape);
    PX.r(ctx, 30, 19 + yo, 6, 18, p.cape);
    PX.r(ctx, 11, 22 + yo, 1, 14, p.capeShade);
    PX.r(ctx, 36, 22 + yo, 1, 14, p.capeShade);
    PX.r(ctx, 12, 19 + yo, 6, 1, p.outline);
    PX.r(ctx, 30, 19 + yo, 6, 1, p.outline);
    PX.r(ctx, 12, 36 + yo, 6, 1, p.outline);
    PX.r(ctx, 30, 36 + yo, 6, 1, p.outline);
  } else {
    // hanging cape behind shoulders
    PX.r(ctx, 14, 21 + yo, 20, 17, p.cape);
    PX.r(ctx, 14, 21 + yo, 20, 1, p.outline);
    PX.r(ctx, 14, 37 + yo, 20, 1, p.outline);
    PX.r(ctx, 14, 21 + yo, 1, 17, p.capeShade);
    PX.r(ctx, 33, 21 + yo, 1, 17, p.capeShade);
  }

  drawLegs(ctx, yo, p, p.suit, p.boot);
  drawTorso(ctx, yo, p, p.suit);
  // Vertical chest seam (original — no logo)
  PX.r(ctx, 23, 22 + yo, 1, 10, p.suitLight);
  PX.r(ctx, 24, 22 + yo, 1, 10, p.suitDark);
  // Belt
  PX.r(ctx, 16, 31 + yo, 16, 2, p.belt);
  PX.r(ctx, 16, 32 + yo, 16, 1, p.beltDark);
  PX.r(ctx, 23, 31 + yo, 2, 2, p.beltDark);
  drawArms(ctx, yo, p, p.suit);
  // Side shading
  PX.r(ctx, 17, 21 + yo, 1, 10, p.suitDark);
  PX.r(ctx, 30, 21 + yo, 1, 10, p.suitDark);
  drawNeck(ctx, yo, p);
  drawHead(ctx, yo, p);

  // Hair — short, neat, side-parted
  PX.r(ctx, 16, 4 + yo, 16, 4, p.hair);
  PX.r(ctx, 17, 3 + yo, 14, 1, p.hair);
  PX.r(ctx, 16, 8 + yo, 4, 2, p.hair);
  PX.r(ctx, 28, 8 + yo, 4, 2, p.hair);
  PX.r(ctx, 16, 4 + yo, 16, 1, p.hairShade);
  PX.r(ctx, 19, 8 + yo, 4, 1, p.hairShade);

  // Eyes — confident gaze
  drawEyesOpen(ctx, yo, p, 19, 27, 11, '#3a9bb8');
  drawMouth(ctx, yo, p, 22, 16, 4);

  // POWER — small sparkles around body
  if (flying) {
    FX.sparkles(ctx, 24, 28 + yo, frame, '#a8e0ff');
    // wind-line under feet
    PX.r(ctx, 14, 44, 4, 1, '#a8e0ff');
    PX.r(ctx, 22, 45, 6, 1, '#a8e0ff');
    PX.r(ctx, 32, 44, 4, 1, '#a8e0ff');
  }
}

/* ───────────────────────────────────────────────────────────────
   3. SPIDERMAN  →  codename "Arachne" (wall climber)
   Original "cosmic spider" — rich violet suit, gold trim, 4 amber compound
   eyes arranged like a real spider. Slimmer build than the bruisers.
   ─────────────────────────────────────────────────────────────── */

function drawSpiderman(ctx, frame, mode, t) {
  const p = {
    suit:     '#5a2aa8', suitDark: '#28104a', suitLight: '#8a5cd8',
    panel:    '#3a1880', panelHi:  '#a878e8',
    gold:     '#f5c038', goldDark: '#a07014',
    lens:     '#ffd84a', lensDark: '#8a5a08', lensGlow: '#fff5b8',
    outline:  '#10052a',
  };

  ctx.save();
  if (mode === 'power') {
    ctx.translate(24, 24);
    ctx.rotate(-Math.PI / 2);
    ctx.translate(-24, -28);
  }
  const yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  drawShadow(ctx, mode === 'power' ? 0 : 14, mode === 'power' ? 0 : 0.32);

  /* Slimmer legs */
  PX.r(ctx, 19, 34 + yo, 4, 7, p.suit);
  PX.r(ctx, 25, 34 + yo, 4, 7, p.suit);
  PX.r(ctx, 19, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 22, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 25, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 28, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 19, 34 + yo, 1, 7, p.suitDark);
  PX.r(ctx, 26, 34 + yo, 1, 7, p.suitDark);
  /* Boots — gold cuff */
  PX.r(ctx, 18, 40 + yo, 6, 3, p.suitDark);
  PX.r(ctx, 24, 40 + yo, 6, 3, p.suitDark);
  PX.r(ctx, 18, 40 + yo, 6, 1, p.gold);
  PX.r(ctx, 24, 40 + yo, 6, 1, p.gold);
  PX.r(ctx, 18, 42 + yo, 12, 1, p.outline);

  /* Torso (slimmer than default) */
  PX.r(ctx, 17, 21 + yo, 14, 13, p.suit);
  PX.r(ctx, 17, 21 + yo, 1, 13, p.outline);
  PX.r(ctx, 30, 21 + yo, 1, 13, p.outline);
  PX.r(ctx, 17, 33 + yo, 14, 1, p.outline);
  /* Lighter chest panel */
  PX.r(ctx, 19, 22 + yo, 10, 9, p.panel);
  PX.r(ctx, 19, 22 + yo, 10, 1, p.panelHi);
  PX.r(ctx, 19, 22 + yo, 1, 9, p.panelHi);
  /* Gold spider-mark on chest — small 8-leg starburst */
  PX.r(ctx, 23, 25 + yo, 2, 3, p.gold);   // body
  PX.r(ctx, 22, 24 + yo, 1, 1, p.gold);
  PX.r(ctx, 25, 24 + yo, 1, 1, p.gold);
  PX.r(ctx, 21, 25 + yo, 1, 1, p.gold);
  PX.r(ctx, 26, 25 + yo, 1, 1, p.gold);
  PX.r(ctx, 21, 27 + yo, 1, 1, p.gold);
  PX.r(ctx, 26, 27 + yo, 1, 1, p.gold);
  PX.r(ctx, 22, 28 + yo, 1, 1, p.gold);
  PX.r(ctx, 25, 28 + yo, 1, 1, p.gold);
  /* Belt — gold band */
  PX.r(ctx, 17, 31 + yo, 14, 2, p.gold);
  PX.r(ctx, 17, 32 + yo, 14, 1, p.goldDark);

  /* Slim arms (no skin showing — full bodysuit) */
  PX.r(ctx, 14, 22 + yo, 3, 8, p.suit);
  PX.r(ctx, 31, 22 + yo, 3, 8, p.suit);
  PX.r(ctx, 14, 22 + yo, 1, 8, p.outline);
  PX.r(ctx, 33, 22 + yo, 1, 8, p.outline);
  PX.r(ctx, 14, 22 + yo, 1, 8, p.suitDark);
  PX.r(ctx, 32, 22 + yo, 1, 8, p.suitLight);
  /* Gold glove cuffs */
  PX.r(ctx, 14, 29 + yo, 3, 1, p.gold);
  PX.r(ctx, 31, 29 + yo, 3, 1, p.gold);
  /* Hands — same suit color */
  PX.r(ctx, 14, 30 + yo, 3, 3, p.suit);
  PX.r(ctx, 31, 30 + yo, 3, 3, p.suit);
  PX.r(ctx, 14, 32 + yo, 3, 1, p.outline);
  PX.r(ctx, 31, 32 + yo, 3, 1, p.outline);

  /* Full head mask */
  PX.r(ctx, 17, 6 + yo, 14, 1, p.suit);
  PX.r(ctx, 16, 7 + yo, 16, 11, p.suit);
  PX.r(ctx, 17, 18 + yo, 14, 1, p.suit);
  /* Top + side shading */
  PX.r(ctx, 17, 6 + yo, 14, 1, p.outline);
  PX.r(ctx, 16, 7 + yo, 1, 11, p.outline);
  PX.r(ctx, 31, 7 + yo, 1, 11, p.outline);
  PX.r(ctx, 17, 18 + yo, 14, 1, p.outline);
  /* Mask plate highlight (front facets) */
  PX.r(ctx, 17, 7 + yo, 14, 2, p.suitLight);
  PX.r(ctx, 17, 9 + yo, 14, 1, p.suitDark);

  /* FOUR compound eyes — 2 large up top + 2 smaller below, like a real spider.
     Gold lenses, slight glow. */
  // Upper-left big eye
  PX.r(ctx, 18, 10 + yo, 4, 3, p.lensDark);
  PX.r(ctx, 18, 11 + yo, 4, 2, p.lens);
  PX.r(ctx, 18, 11 + yo, 1, 1, p.lensGlow);
  // Upper-right big eye
  PX.r(ctx, 26, 10 + yo, 4, 3, p.lensDark);
  PX.r(ctx, 26, 11 + yo, 4, 2, p.lens);
  PX.r(ctx, 26, 11 + yo, 1, 1, p.lensGlow);
  // Lower-left small eye
  PX.r(ctx, 19, 14 + yo, 2, 2, p.lensDark);
  PX.r(ctx, 19, 14 + yo, 2, 1, p.lens);
  // Lower-right small eye
  PX.r(ctx, 27, 14 + yo, 2, 2, p.lensDark);
  PX.r(ctx, 27, 14 + yo, 2, 1, p.lens);
  /* Mouth grille seam */
  PX.r(ctx, 22, 17 + yo, 4, 1, p.outline);

  ctx.restore();

  /* POWER — silk line shooting diagonally + tiny wall texture on left edge */
  if (mode === 'power') {
    FX.webline(ctx, 4, 14, 46, 2, p.gold);
    for (let i = 0; i < 6; i++) {
      PX.r(ctx, 0, 4 + i * 7, 2, 1, '#3a2a5a');
    }
  }
}

/* ───────────────────────────────────────────────────────────────
   4. HULK  →  codename "Titan" (bruiser)
   Original: broad green-skinned brawler, brown shorts, no Marvel insignia.
   ─────────────────────────────────────────────────────────────── */

function drawHulk(ctx, frame, mode, t) {
  const p = {
    skin: '#5fa14b', skinShade: '#2f6620', skinLight: '#8ac677',
    shorts: '#3d2818', shortsDark: '#1f1208', shortsTear: '#5a3a22',
    hair: '#1a1108',
    outline: '#0a1404',
  };

  // Power: stomp — rises slightly then slams. t<0.4 lift, t>0.4 slam + shake
  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  if (mode === 'power') {
    yo = t < 0.4 ? -Math.round(t * 12) : 0;
  }
  // Screen shake offset during power slam
  let xo = 0;
  if (mode === 'power' && t >= 0.4 && t < 0.7) {
    xo = (frame % 2) ? 1 : -1;
  }

  drawShadow(ctx, 18, 0.4);

  ctx.save();
  ctx.translate(xo, 0);

  // Bulkier legs
  PX.r(ctx, 16, 34 + yo, 7, 7, p.skin);
  PX.r(ctx, 25, 34 + yo, 7, 7, p.skin);
  PX.r(ctx, 16, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 22, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 25, 34 + yo, 1, 7, p.outline);
  PX.r(ctx, 31, 34 + yo, 1, 7, p.outline);
  // Shading
  PX.r(ctx, 17, 34 + yo, 1, 7, p.skinShade);
  PX.r(ctx, 26, 34 + yo, 1, 7, p.skinShade);
  // Torn shorts
  PX.r(ctx, 15, 30 + yo, 18, 5, p.shorts);
  PX.r(ctx, 15, 30 + yo, 18, 1, p.outline);
  PX.r(ctx, 15, 34 + yo, 18, 1, p.outline);
  PX.r(ctx, 16, 35 + yo, 1, 1, p.shorts);
  PX.r(ctx, 31, 35 + yo, 1, 1, p.shorts);
  PX.r(ctx, 20, 35 + yo, 2, 1, p.shorts);
  PX.r(ctx, 26, 35 + yo, 2, 1, p.shorts);
  // shorts shading
  PX.r(ctx, 15, 33 + yo, 18, 1, p.shortsDark);
  // Feet
  PX.r(ctx, 15, 41 + yo, 8, 2, p.skin);
  PX.r(ctx, 25, 41 + yo, 8, 2, p.skin);
  PX.r(ctx, 15, 42 + yo, 17, 1, p.outline);

  // Massive torso — wider than standard
  PX.r(ctx, 13, 19 + yo, 22, 12, p.skin);
  PX.r(ctx, 13, 19 + yo, 1, 12, p.outline);
  PX.r(ctx, 34, 19 + yo, 1, 12, p.outline);
  PX.r(ctx, 13, 19 + yo, 22, 1, p.outline);
  // Pec/ab definition
  PX.r(ctx, 14, 20 + yo, 9, 4, p.skinLight);
  PX.r(ctx, 25, 20 + yo, 9, 4, p.skinLight);
  PX.r(ctx, 23, 20 + yo, 2, 10, p.skinShade);
  PX.r(ctx, 16, 25 + yo, 7, 1, p.skinShade);
  PX.r(ctx, 25, 25 + yo, 7, 1, p.skinShade);
  PX.r(ctx, 16, 28 + yo, 7, 1, p.skinShade);
  PX.r(ctx, 25, 28 + yo, 7, 1, p.skinShade);

  // Huge arms hanging at sides
  PX.r(ctx, 9, 20 + yo, 5, 11, p.skin);
  PX.r(ctx, 34, 20 + yo, 5, 11, p.skin);
  PX.r(ctx, 9, 20 + yo, 1, 11, p.outline);
  PX.r(ctx, 39, 20 + yo, 1, 11, p.outline);
  PX.r(ctx, 9, 20 + yo, 5, 1, p.outline);
  PX.r(ctx, 34, 20 + yo, 5, 1, p.outline);
  PX.r(ctx, 9, 30 + yo, 5, 1, p.outline);
  PX.r(ctx, 34, 30 + yo, 5, 1, p.outline);
  // Arm shading
  PX.r(ctx, 10, 21 + yo, 1, 9, p.skinShade);
  PX.r(ctx, 35, 21 + yo, 1, 9, p.skinShade);
  // Hands (fists)
  PX.r(ctx, 8, 31 + yo, 7, 4, p.skin);
  PX.r(ctx, 33, 31 + yo, 7, 4, p.skin);
  PX.r(ctx, 8, 31 + yo, 7, 1, p.outline);
  PX.r(ctx, 33, 31 + yo, 7, 1, p.outline);
  PX.r(ctx, 8, 34 + yo, 7, 1, p.outline);
  PX.r(ctx, 33, 34 + yo, 7, 1, p.outline);
  PX.r(ctx, 8, 32 + yo, 1, 2, p.outline);
  PX.r(ctx, 14, 32 + yo, 1, 2, p.outline);
  PX.r(ctx, 33, 32 + yo, 1, 2, p.outline);
  PX.r(ctx, 39, 32 + yo, 1, 2, p.outline);

  // Small head sunk between massive shoulders
  PX.r(ctx, 19, 9 + yo, 10, 10, p.skin);
  PX.r(ctx, 18, 10 + yo, 12, 8, p.skin);
  PX.r(ctx, 19, 9 + yo, 10, 1, p.outline);
  PX.r(ctx, 18, 10 + yo, 1, 8, p.outline);
  PX.r(ctx, 29, 10 + yo, 1, 8, p.outline);
  PX.r(ctx, 19, 18 + yo, 10, 1, p.outline);
  // Brow shadow
  PX.r(ctx, 19, 13 + yo, 10, 1, p.skinShade);
  // Hair — black, short, messy
  PX.r(ctx, 19, 9 + yo, 10, 2, p.hair);
  PX.r(ctx, 18, 10 + yo, 1, 2, p.hair);
  PX.r(ctx, 29, 10 + yo, 1, 2, p.hair);
  PX.r(ctx, 20, 8 + yo, 8, 1, p.hair);
  // Angry eyes
  PX.r(ctx, 20, 14 + yo, 3, 1, p.outline);
  PX.r(ctx, 25, 14 + yo, 3, 1, p.outline);
  PX.r(ctx, 21, 14 + yo, 1, 1, '#fff');
  PX.r(ctx, 26, 14 + yo, 1, 1, '#fff');
  // Mouth — clenched
  PX.r(ctx, 22, 17 + yo, 4, 1, p.outline);

  ctx.restore();

  // POWER — shockwave + dust clouds
  if (mode === 'power' && t >= 0.4) {
    const radius = Math.round((t - 0.4) * 50);
    if (radius > 4 && radius < 24) {
      FX.shock(ctx, 24, 44, radius, '#caa066');
      FX.shock(ctx, 24, 44, Math.max(2, radius - 3), '#e8c89c');
    }
    // dust
    PX.r(ctx, 6, 43, 3, 1, '#caa066');
    PX.r(ctx, 39, 43, 3, 1, '#caa066');
  }
}

/* ───────────────────────────────────────────────────────────────
   5. IRONMAN  →  codename "Aegis" (armored flyer)
   Original: crimson plate armor, brass trim, cyan circular core, full visor.
   ─────────────────────────────────────────────────────────────── */

function drawIronman(ctx, frame, mode, t) {
  const p = {
    armor: '#c83a2a', armorDark: '#7a1810', armorLight: '#ff6044',
    trim:  '#d8a830', trimDark: '#8e6c14',
    core:  '#5be8f5', coreGlow: '#a5f4ff',
    visor: '#2a1a08', visorLens: '#5be8f5',
    outline: '#1a0a04',
  };

  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  if (mode === 'power') yo = -5 - Math.floor(Math.sin(t * Math.PI) * 3);

  const shadowW = mode === 'power' ? Math.max(7, 14 - Math.abs(yo)) : 14;
  drawShadow(ctx, shadowW, mode === 'power' ? 0.2 : 0.35);

  // Legs / boot armor
  PX.r(ctx, 18, 33 + yo, 5, 8, p.armor);
  PX.r(ctx, 25, 33 + yo, 5, 8, p.armor);
  PX.r(ctx, 18, 33 + yo, 1, 8, p.outline);
  PX.r(ctx, 22, 33 + yo, 1, 8, p.outline);
  PX.r(ctx, 25, 33 + yo, 1, 8, p.outline);
  PX.r(ctx, 29, 33 + yo, 1, 8, p.outline);
  // Knee plate accent
  PX.r(ctx, 19, 36 + yo, 3, 1, p.trim);
  PX.r(ctx, 26, 36 + yo, 3, 1, p.trim);
  // Side shading
  PX.r(ctx, 19, 33 + yo, 1, 8, p.armorDark);
  PX.r(ctx, 26, 33 + yo, 1, 8, p.armorDark);
  // Boots
  PX.r(ctx, 17, 41 + yo, 7, 2, p.trim);
  PX.r(ctx, 24, 41 + yo, 7, 2, p.trim);
  PX.r(ctx, 17, 42 + yo, 14, 1, p.outline);

  // Chest plate
  PX.r(ctx, 15, 20 + yo, 18, 13, p.armor);
  PX.r(ctx, 15, 20 + yo, 18, 1, p.outline);
  PX.r(ctx, 15, 32 + yo, 18, 1, p.outline);
  PX.r(ctx, 15, 20 + yo, 1, 13, p.outline);
  PX.r(ctx, 32, 20 + yo, 1, 13, p.outline);
  // Pec plates
  PX.r(ctx, 16, 21 + yo, 7, 6, p.armorLight);
  PX.r(ctx, 25, 21 + yo, 7, 6, p.armorLight);
  PX.r(ctx, 23, 20 + yo, 2, 13, p.armorDark);
  // Cyan reactor core
  PX.circle(ctx, 24, 25 + yo, 3, p.trimDark);
  PX.circle(ctx, 24, 25 + yo, 2, p.core);
  PX.r(ctx, 24, 25 + yo, 1, 1, p.coreGlow);
  // Belt
  PX.r(ctx, 15, 31 + yo, 18, 1, p.trim);

  // Arms — bulkier
  PX.r(ctx, 11, 21 + yo, 4, 10, p.armor);
  PX.r(ctx, 33, 21 + yo, 4, 10, p.armor);
  PX.r(ctx, 11, 21 + yo, 1, 10, p.outline);
  PX.r(ctx, 36, 21 + yo, 1, 10, p.outline);
  PX.r(ctx, 12, 21 + yo, 3, 1, p.armorLight);
  PX.r(ctx, 33, 21 + yo, 3, 1, p.armorLight);
  PX.r(ctx, 11, 26 + yo, 4, 1, p.trim);
  PX.r(ctx, 33, 26 + yo, 4, 1, p.trim);
  // Gauntlets — emit jet on power
  PX.r(ctx, 11, 31 + yo, 4, 3, p.trim);
  PX.r(ctx, 33, 31 + yo, 4, 3, p.trim);
  PX.r(ctx, 11, 31 + yo, 4, 1, p.outline);
  PX.r(ctx, 33, 31 + yo, 4, 1, p.outline);
  PX.r(ctx, 11, 33 + yo, 4, 1, p.outline);
  PX.r(ctx, 33, 33 + yo, 4, 1, p.outline);

  // Helmet — full mask, no skin
  PX.r(ctx, 17, 5 + yo, 14, 14, p.armor);
  PX.r(ctx, 16, 7 + yo, 16, 11, p.armor);
  PX.r(ctx, 17, 5 + yo, 14, 1, p.outline);
  PX.r(ctx, 16, 7 + yo, 1, 11, p.outline);
  PX.r(ctx, 31, 7 + yo, 1, 11, p.outline);
  PX.r(ctx, 17, 18 + yo, 14, 1, p.outline);
  PX.r(ctx, 16, 7 + yo, 1, 1, p.outline);
  PX.r(ctx, 31, 7 + yo, 1, 1, p.outline);
  // Cheek/jaw highlights
  PX.r(ctx, 16, 8 + yo, 2, 8, p.armorLight);
  PX.r(ctx, 30, 8 + yo, 2, 8, p.armorLight);
  // Forehead trim
  PX.r(ctx, 17, 7 + yo, 14, 1, p.trim);
  PX.r(ctx, 23, 5 + yo, 2, 2, p.trim);
  // Horizontal visor (single bar, no Stark T-shape)
  PX.r(ctx, 17, 11 + yo, 14, 3, p.visor);
  PX.r(ctx, 18, 12 + yo, 12, 1, p.visorLens);
  PX.r(ctx, 19, 12 + yo, 2, 1, p.coreGlow);
  PX.r(ctx, 27, 12 + yo, 2, 1, p.coreGlow);
  // Mouth grille
  PX.r(ctx, 21, 16 + yo, 6, 1, p.trimDark);
  PX.r(ctx, 22, 17 + yo, 4, 1, p.trimDark);

  // POWER — jets from boots and palm thrusters
  if (mode === 'power') {
    FX.jetFlame(ctx, 19, 43, frame, '#ff8a1c', '#ffd84a', '#fff5c4');
    FX.jetFlame(ctx, 27, 43, frame, '#ff8a1c', '#ffd84a', '#fff5c4');
    // palm thrusters (smaller)
    PX.r(ctx, 12, 34 + yo, 2, 3, '#ffd84a');
    PX.r(ctx, 34, 34 + yo, 2, 3, '#ffd84a');
    PX.r(ctx, 12, 34 + yo, 2, 1, '#fff5c4');
    PX.r(ctx, 34, 34 + yo, 2, 1, '#fff5c4');
  }
}

/* ───────────────────────────────────────────────────────────────
   6. CYCLOPS  →  codename "Visor" (beam shooter)
   Original: navy tactical jumpsuit, golden chest stripe, wide red visor band.
   ─────────────────────────────────────────────────────────────── */

function drawCyclops(ctx, frame, mode, t) {
  const p = {
    skin: '#f4c896', skinShade: '#c4854a',
    suit: '#1a2848', suitDark: '#0a1428', suitLight: '#3a4e80',
    accent: '#d6a82a', accentDark: '#8a6814',
    visor: '#1c0608', visorBand: '#e83a2c', visorGlow: '#ff8a6c',
    hair: '#3a2010',
    boot: '#0a0e1a',
    outline: '#04060e',
  };
  let yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  // Power: tiny recoil shake
  let xo = 0;
  if (mode === 'power') xo = (frame % 2) ? -1 : 0;

  drawShadow(ctx, 14, 0.35);
  ctx.save();
  ctx.translate(xo, 0);

  drawLegs(ctx, yo, p, p.suit, p.boot);
  // Stripe down outer legs
  PX.r(ctx, 18, 34 + yo, 1, 7, p.accent);
  PX.r(ctx, 29, 34 + yo, 1, 7, p.accent);

  drawTorso(ctx, yo, p, p.suit);
  // Diagonal chest sash (golden, shoulder to opposite hip)
  for (let i = 0; i < 12; i++) {
    PX.r(ctx, 17 + i, 21 + i + yo, 3, 1, p.accent);
  }
  // Belt
  PX.r(ctx, 16, 32 + yo, 16, 2, p.accent);
  PX.r(ctx, 16, 33 + yo, 16, 1, p.accentDark);
  PX.r(ctx, 23, 32 + yo, 2, 2, p.suitDark);

  drawArms(ctx, yo, p, p.suit);
  // Gloves accent
  PX.r(ctx, 13, 29 + yo, 3, 1, p.accent);
  PX.r(ctx, 32, 29 + yo, 3, 1, p.accent);
  // Side shading
  PX.r(ctx, 17, 21 + yo, 1, 12, p.suitDark);
  PX.r(ctx, 30, 21 + yo, 1, 12, p.suitDark);

  drawNeck(ctx, yo, p);
  drawHead(ctx, yo, p);

  // Hair — short, swept back, no visible eyes (covered by visor)
  PX.r(ctx, 16, 4 + yo, 16, 4, p.hair);
  PX.r(ctx, 17, 3 + yo, 14, 1, p.hair);
  PX.r(ctx, 16, 8 + yo, 3, 3, p.hair);
  PX.r(ctx, 29, 8 + yo, 3, 3, p.hair);
  PX.r(ctx, 19, 4 + yo, 10, 1, p.hairShade || '#1a0e04');

  // Wide visor band — wraps around head, red glowing center
  PX.r(ctx, 14, 11 + yo, 20, 4, p.visor);
  PX.r(ctx, 14, 11 + yo, 20, 1, p.outline);
  PX.r(ctx, 14, 14 + yo, 20, 1, p.outline);
  // Glowing band slit
  PX.r(ctx, 16, 12 + yo, 16, 2, p.visorBand);
  if (mode === 'power') {
    PX.r(ctx, 16, 12 + yo, 16, 2, p.visorGlow);
    PX.r(ctx, 16, 13 + yo, 16, 1, '#fff');
  } else {
    PX.r(ctx, 17, 12 + yo, 14, 1, p.visorGlow);
  }
  // Side anchors
  PX.r(ctx, 13, 12 + yo, 1, 2, p.accent);
  PX.r(ctx, 34, 12 + yo, 1, 2, p.accent);

  // Determined mouth
  drawMouth(ctx, yo, p, 22, 17, 4);

  ctx.restore();

  // POWER — wide red beam fires forward from visor
  if (mode === 'power') {
    const beamLen = 16 + Math.round(t * 28);
    FX.beam(ctx, 34, 11 + yo, beamLen, frame, '#ff3a2c', '#ff8a6c', '#fff5e6');
    // backlight on body
    PX.r(ctx, 13, 11 + yo, 21, 1, '#ff8a6c');
  }
}

/* ───────────────────────────────────────────────────────────────
   OLD-style "v1" sprites — quick 16×16 simplified versions roughly matching
   the screenshot's blocky aesthetic, for the BEFORE column in comparison.
   Drawn centered in 48×48 canvas (so we can use same SpriteCanvas).
   ─────────────────────────────────────────────────────────────── */

function drawOld(ctx, primary, secondary, accent) {
  // Simple chunky avatar — head block, body block, no anti-aliasing
  // scaled by 2 (so each "v1 pixel" = 2x2 of new logical pixel)
  const off = (n) => n * 2;
  const baseX = 8, baseY = 8;
  function bp(x, y, c) {
    PX.r(ctx, baseX + off(x), baseY + off(y), 2, 2, c);
  }
  // Body 8x6
  for (let y = 6; y < 14; y++) for (let x = 3; x < 13; x++) bp(x, y, primary);
  // Belt
  for (let x = 3; x < 13; x++) bp(x, 11, secondary);
  // Head 6x5
  for (let y = 1; y < 6; y++) for (let x = 5; x < 11; x++) bp(x, y, primary);
  // Eyes
  bp(6, 3, '#fff'); bp(9, 3, '#fff');
  bp(6, 3, primary); bp(9, 3, primary);
  PX.r(ctx, baseX + off(6) + 1, baseY + off(3) + 1, 1, 1, '#000');
  PX.r(ctx, baseX + off(9) + 1, baseY + off(3) + 1, 1, 1, '#000');
  // Accent stripe
  for (let x = 3; x < 13; x++) bp(x, 8, accent);
  // Feet
  bp(4, 14, '#222'); bp(5, 14, '#222');
  bp(10, 14, '#222'); bp(11, 14, '#222');
  // Simple shadow
  PX.shadow(ctx, 24, 38, 12, 0.3);
}

/* ───────────────────────────────────────────────────────────────
   REGISTRY
   ─────────────────────────────────────────────────────────────── */

const TRADERS = [
  {
    id: 'flash',
    codename: 'FLASH',
    name: 'Velox',
    role: 'L1 — Analista de momentum',
    palette: ['#e89a2a', '#b87114', '#fff3c4', '#9ee9ff', '#1a0d04'],
    powerLabel: 'Super-velocidade',
    powerDesc: 'Movimento de dash com rastro de raio e linhas cinéticas.',
    oldColors: ['#c93a1a', '#7a1a0a', '#ffd640'],
    draw: drawFlash,
  },
  {
    id: 'superman',
    codename: 'SUPERMAN',
    name: 'Nimbus',
    role: 'L1 — Sinal forward',
    palette: ['#1e6f8c', '#f0f2ec', '#c8a23a', '#2a1a0d', '#06141d'],
    powerLabel: 'Voo',
    powerDesc: 'Levitação suave; partículas e linhas de vento sob os pés.',
    oldColors: ['#2a5cb8', '#1a3578', '#e83a2c'],
    draw: drawSuperman,
  },
  {
    id: 'spiderman',
    codename: 'SPIDERMAN',
    name: 'Arachne',
    role: 'L4 — Night-trader',
    palette: ['#5a2aa8', '#8a5cd8', '#f5c038', '#ffd84a', '#10052a'],
    powerLabel: 'Escalada + linha de seda',
    powerDesc: 'Rotaciona pra parede e atira uma linha-âncora dourada em diagonal.',
    oldColors: ['#a83a3a', '#5a1a1a', '#3a3a8a'],
    draw: drawSpiderman,
  },
  {
    id: 'hulk',
    codename: 'HULK',
    name: 'Titan',
    role: 'L3 — Risk/Exec',
    palette: ['#5fa14b', '#2f6620', '#3d2818', '#1a1108', '#0a1404'],
    powerLabel: 'Stomp + onda de choque',
    powerDesc: 'Levanta, baixa com força e dispara uma onda de poeira radial.',
    oldColors: ['#3a8a3a', '#1a4a1a', '#6abf6a'],
    draw: drawHulk,
  },
  {
    id: 'ironman',
    codename: 'IRONMAN',
    name: 'Aegis',
    role: 'L3 — Execução',
    palette: ['#c83a2a', '#d8a830', '#5be8f5', '#7a1810', '#1a0a04'],
    powerLabel: 'Propulsão a jato',
    powerDesc: 'Botas + repulsores acendem; eleva acima do chão.',
    oldColors: ['#c93a1a', '#7a1a0a', '#ffd640'],
    draw: drawIronman,
  },
  {
    id: 'cyclops',
    codename: 'CYCLOPS',
    name: 'Visor',
    role: 'L3 — Risk Check',
    palette: ['#1a2848', '#d6a82a', '#e83a2c', '#3a2010', '#04060e'],
    powerLabel: 'Feixe de energia',
    powerDesc: 'Disparo horizontal vermelho a partir da viseira, com recuo.',
    oldColors: ['#3a5cb8', '#1a3578', '#e8c83a'],
    draw: drawCyclops,
  },
];

/* ───────────────────────────────────────────────────────────────
   CHIBI FACTORY — generic trader drawer parameterised by config.
   Used for the 16 "supporting" agents in the office view that
   share a base body but read distinctly via palette + accessory.
   ─────────────────────────────────────────────────────────────── */

function shade(hex, amt) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v + amt * 255)));
  return '#' + [clamp(r), clamp(g), clamp(b)].map((v) => v.toString(16).padStart(2, '0')).join('');
}

function drawChibi(ctx, frame, mode, t, cfg) {
  const yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;
  const skin = cfg.skin || '#f4c89a';
  const skinShade = cfg.skinShade || shade(skin, -0.18);
  const shirt = cfg.shirt;
  const shirtDark = shade(shirt, -0.22);
  const shirtLight = shade(shirt, 0.16);
  const pants = cfg.pants || '#1a1a28';
  const pantsDark = shade(pants, -0.30);
  const hair = cfg.hair || '#2a1808';
  const outline = cfg.outline || '#0a0a14';
  const boot = cfg.boot || pantsDark;

  drawShadow(ctx, 14, 0.34);

  /* Cape — behind body */
  if (cfg.cape) {
    PX.r(ctx, 14, 21 + yo, 20, 17, cfg.cape);
    PX.r(ctx, 14, 21 + yo, 20, 1, outline);
    PX.r(ctx, 14, 37 + yo, 20, 1, outline);
    PX.r(ctx, 14, 21 + yo, 1, 17, shade(cfg.cape, -0.22));
    PX.r(ctx, 33, 21 + yo, 1, 17, shade(cfg.cape, -0.22));
  }

  /* Legs / boots */
  PX.r(ctx, 18, 34 + yo, 5, 7, pants);
  PX.r(ctx, 25, 34 + yo, 5, 7, pants);
  PX.r(ctx, 18, 34 + yo, 1, 7, outline);
  PX.r(ctx, 22, 34 + yo, 1, 7, outline);
  PX.r(ctx, 25, 34 + yo, 1, 7, outline);
  PX.r(ctx, 29, 34 + yo, 1, 7, outline);
  PX.r(ctx, 19, 34 + yo, 1, 7, pantsDark);
  PX.r(ctx, 26, 34 + yo, 1, 7, pantsDark);
  PX.r(ctx, 17, 41 + yo, 7, 2, boot);
  PX.r(ctx, 24, 41 + yo, 7, 2, boot);
  PX.r(ctx, 17, 42 + yo, 14, 1, outline);

  /* Torso */
  PX.r(ctx, 16, 21 + yo, 16, 13, shirt);
  PX.r(ctx, 16, 21 + yo, 1, 13, outline);
  PX.r(ctx, 31, 21 + yo, 1, 13, outline);
  PX.r(ctx, 16, 33 + yo, 16, 1, outline);
  PX.r(ctx, 17, 21 + yo, 1, 12, shirtDark);
  PX.r(ctx, 30, 21 + yo, 1, 12, shirtLight);

  if (cfg.sash) {
    for (let i = 0; i < 12; i++) PX.r(ctx, 17 + i, 21 + i + yo, 3, 1, cfg.sash);
  }
  if (cfg.belt) {
    PX.r(ctx, 16, 31 + yo, 16, 2, cfg.belt);
    PX.r(ctx, 23, 31 + yo, 2, 2, shade(cfg.belt, -0.3));
  }
  if (cfg.emblem) {
    PX.r(ctx, 23, 24 + yo, 2, 3, cfg.emblem);
    PX.r(ctx, 22, 25 + yo, 4, 1, cfg.emblem);
  }
  if (cfg.tie) {
    PX.r(ctx, 23, 21 + yo, 2, 9, cfg.tie);
    PX.r(ctx, 22, 26 + yo, 4, 2, cfg.tie);
  }

  /* Arms */
  PX.r(ctx, 13, 22 + yo, 3, 8, shirt);
  PX.r(ctx, 32, 22 + yo, 3, 8, shirt);
  PX.r(ctx, 13, 22 + yo, 1, 8, outline);
  PX.r(ctx, 34, 22 + yo, 1, 8, outline);

  const handCol = cfg.gloves || skin;
  PX.r(ctx, 13, 30 + yo, 3, 3, handCol);
  PX.r(ctx, 32, 30 + yo, 3, 3, handCol);
  PX.r(ctx, 13, 32 + yo, 3, 1, outline);
  PX.r(ctx, 32, 32 + yo, 3, 1, outline);

  /* Neck */
  PX.r(ctx, 22, 19 + yo, 4, 2, skinShade);

  /* Head — mask vs skin */
  const headColor = cfg.mask || skin;
  PX.r(ctx, 17, 6 + yo, 14, 1, headColor);
  PX.r(ctx, 16, 7 + yo, 16, 11, headColor);
  PX.r(ctx, 17, 18 + yo, 14, 1, headColor);
  if (!cfg.mask) {
    PX.r(ctx, 16, 8 + yo, 1, 10, skinShade);
    PX.r(ctx, 31, 8 + yo, 1, 10, skinShade);
    PX.r(ctx, 17, 17 + yo, 14, 1, skinShade);
  } else {
    PX.r(ctx, 17, 6 + yo, 14, 1, outline);
    PX.r(ctx, 16, 7 + yo, 1, 11, outline);
    PX.r(ctx, 31, 7 + yo, 1, 11, outline);
    PX.r(ctx, 17, 18 + yo, 14, 1, outline);
  }

  /* Hair / helmet / hood / crown */
  const hs = cfg.hairStyle || 'short';
  if (hs === 'short') {
    PX.r(ctx, 16, 4 + yo, 16, 4, hair);
    PX.r(ctx, 17, 3 + yo, 14, 1, hair);
    PX.r(ctx, 16, 4 + yo, 16, 1, shade(hair, -0.3));
  } else if (hs === 'long') {
    PX.r(ctx, 14, 4 + yo, 20, 6, hair);
    PX.r(ctx, 15, 3 + yo, 18, 1, hair);
    PX.r(ctx, 14, 9 + yo, 2, 10, hair);
    PX.r(ctx, 32, 9 + yo, 2, 10, hair);
    PX.r(ctx, 14, 4 + yo, 20, 1, shade(hair, -0.3));
  } else if (hs === 'spiky') {
    PX.r(ctx, 16, 5 + yo, 16, 3, hair);
    PX.r(ctx, 14, 5 + yo, 2, 3, hair);
    PX.r(ctx, 18, 2 + yo, 3, 5, hair);
    PX.r(ctx, 22, 3 + yo, 4, 4, hair);
    PX.r(ctx, 27, 2 + yo, 3, 5, hair);
    PX.r(ctx, 32, 5 + yo, 2, 3, hair);
  } else if (hs === 'bald') {
    /* no hair */
  } else if (hs === 'hood') {
    const hc = cfg.hoodColor || hair;
    PX.r(ctx, 13, 3 + yo, 22, 7, hc);
    PX.r(ctx, 12, 6 + yo, 24, 9, hc);
    PX.r(ctx, 13, 3 + yo, 22, 1, outline);
    PX.r(ctx, 12, 6 + yo, 1, 12, outline);
    PX.r(ctx, 35, 6 + yo, 1, 12, outline);
    /* Face opening */
    PX.r(ctx, 17, 9 + yo, 14, 9, headColor);
    PX.r(ctx, 17, 9 + yo, 14, 1, outline);
  } else if (hs === 'helmet') {
    const hc = cfg.helmetColor || hair;
    PX.r(ctx, 14, 4 + yo, 20, 9, hc);
    PX.r(ctx, 14, 4 + yo, 20, 1, outline);
    PX.r(ctx, 14, 4 + yo, 1, 9, outline);
    PX.r(ctx, 33, 4 + yo, 1, 9, outline);
    PX.r(ctx, 14, 12 + yo, 20, 1, shade(hc, -0.3));
  } else if (hs === 'crown') {
    const hc = cfg.helmetColor || hair;
    PX.r(ctx, 14, 4 + yo, 20, 6, hc);
    PX.r(ctx, 14, 4 + yo, 20, 1, outline);
    /* Tall horns */
    PX.r(ctx, 17, 0 + yo, 3, 5, hc);
    PX.r(ctx, 28, 0 + yo, 3, 5, hc);
    PX.r(ctx, 22, -1 + yo, 4, 6, hc);
    /* Accent gem on forehead */
    if (cfg.accent) PX.r(ctx, 23, 8 + yo, 2, 2, cfg.accent);
  }

  /* Face features */
  if (!cfg.mask) {
    if (cfg.accessory === 'glasses') {
      PX.r(ctx, 17, 11 + yo, 6, 3, outline);
      PX.r(ctx, 25, 11 + yo, 6, 3, outline);
      PX.r(ctx, 23, 12 + yo, 2, 1, outline);
      PX.r(ctx, 18, 12 + yo, 4, 1, '#9fb4c8');
      PX.r(ctx, 26, 12 + yo, 4, 1, '#9fb4c8');
    } else if (cfg.accessory === 'visor') {
      PX.r(ctx, 14, 11 + yo, 20, 4, cfg.accessoryColor || '#1a2030');
      PX.r(ctx, 14, 11 + yo, 20, 1, outline);
      PX.r(ctx, 14, 14 + yo, 20, 1, outline);
      PX.r(ctx, 16, 12 + yo, 16, 2, cfg.visorLens || '#5be8f5');
      PX.r(ctx, 16, 12 + yo, 16, 1, shade(cfg.visorLens || '#5be8f5', 0.3));
    } else {
      PX.r(ctx, 19, 12 + yo, 2, 2, outline);
      PX.r(ctx, 27, 12 + yo, 2, 2, outline);
      PX.r(ctx, 19, 12 + yo, 1, 1, '#fff');
      PX.r(ctx, 27, 12 + yo, 1, 1, '#fff');
    }
    if (cfg.beard) {
      PX.r(ctx, 19, 16 + yo, 10, 3, cfg.beard);
      PX.r(ctx, 22, 17 + yo, 4, 1, outline);
    } else if (cfg.goatee) {
      PX.r(ctx, 22, 17 + yo, 4, 2, cfg.goatee);
      PX.r(ctx, 23, 19 + yo, 2, 1, cfg.goatee);
    } else {
      PX.r(ctx, 22, 17 + yo, 4, 1, outline);
    }
  } else {
    /* Mask eye slits */
    PX.r(ctx, 18, 11 + yo, 4, 2, cfg.maskEyes || '#fff');
    PX.r(ctx, 26, 11 + yo, 4, 2, cfg.maskEyes || '#fff');
  }

  if (cfg.power && mode === 'power') {
    cfg.power(ctx, frame, t, { skin, skinShade, outline, hair, shirt, accent: cfg.accent });
  }
}

/* ───────────────────────────────────────────────────────────────
   EXTRA TRADERS — original chibi configs for the 16 supporting agents.
   ─────────────────────────────────────────────────────────────── */

const EXTRA = [
  /* === L1 ANALYSIS === */
  {
    id: 'hawkeye', codename: 'HAWKEYE', name: 'Falcon', role: 'L1 — Sniper de momentum',
    cfg: {
      skin: '#f0c89a', hair: '#3a1f10', hairStyle: 'short',
      shirt: '#3a1f4a', pants: '#1a0a28', accent: '#d6a82a',
      accessory: 'visor', accessoryColor: '#1a0a28', visorLens: '#d6a82a',
      belt: '#5a3a18',
    },
    powerLabel: 'Tiro certeiro',
  },
  {
    id: 'doctorstrange', codename: 'DOCTORSTRANGE', name: 'Sage', role: 'L1 — Padrões ocultos',
    cfg: {
      skin: '#e8b888', hair: '#1a1010', hairStyle: 'short',
      shirt: '#6a2424', pants: '#3a1818', cape: '#a83a2a',
      goatee: '#1a1010', accent: '#d6a82a', emblem: '#d6a82a',
    },
    powerLabel: 'Leitura mística',
  },
  {
    id: 'thor', codename: 'THOR', name: 'Hammer', role: 'L1 — Macro forte',
    cfg: {
      skin: '#f4d4a8', hair: '#d4a85a', hairStyle: 'long',
      shirt: '#2a5a7a', pants: '#5a3a18', cape: '#5a1a1a',
      accent: '#d6a82a', belt: '#5a3a18', beard: '#a07840',
    },
    powerLabel: 'Quebra de resistência',
  },
  {
    id: 'aquaman', codename: 'AQUAMAN', name: 'Tide', role: 'L1 — Fluxos & liquidez',
    cfg: {
      skin: '#f4d4a8', hair: '#d4a85a', hairStyle: 'long',
      shirt: '#d68a18', pants: '#2a6a48', accent: '#9be8a4', belt: '#5a3a18',
    },
    powerLabel: 'Maré',
  },
  /* === L2 STRATEGY === */
  {
    id: 'vision', codename: 'VISION', name: 'Synth', role: 'L2 — Estratégia sintética',
    cfg: {
      skin: '#d65a3a', skinShade: '#8a2818', hair: '#a83a1a', hairStyle: 'short',
      shirt: '#2a3a78', pants: '#1a2a58', cape: '#d6a82a',
      emblem: '#5be8f5', accent: '#5be8f5',
    },
    powerLabel: 'Síntese de dados',
  },
  {
    id: 'professorx', codename: 'PROFESSORX', name: 'Mentor', role: 'L2 — Portfolio Manager',
    cfg: {
      skin: '#f0c89a', hair: '#000', hairStyle: 'bald',
      shirt: '#2a3a4a', pants: '#1a1a2a', accent: '#d6a82a',
      accessory: 'glasses', tie: '#7a1818',
    },
    powerLabel: 'Coordenação mental',
  },
  {
    id: 'deadpool', codename: 'DEADPOOL', name: 'Joker', role: 'L2 — Trades não-convencionais',
    cfg: {
      mask: '#a8281c', maskEyes: '#f5e8c8',
      shirt: '#a8281c', pants: '#3a1010', accent: '#1a1010', belt: '#1a1010',
    },
    powerLabel: 'Caos calculado',
  },
  /* === L3 RISK/EXEC === */
  {
    id: 'batman', codename: 'BATMAN', name: 'Sentinel', role: 'L3 — Risk officer',
    cfg: {
      mask: '#1a1a28', maskEyes: '#a8b0c0', hairStyle: 'hood', hoodColor: '#1a1a28',
      shirt: '#1a1a28', pants: '#0a0a18', cape: '#0a0a18',
      accent: '#d6a82a', belt: '#5a3a18', emblem: '#3a3a5a',
    },
    powerLabel: 'Vigília noturna',
  },
  {
    id: 'wolverine', codename: 'WOLVERINE', name: 'Claw', role: 'L3 — Execução agressiva',
    cfg: {
      skin: '#f0c89a', hair: '#1a1010', hairStyle: 'spiky',
      shirt: '#b88a18', pants: '#5a2a18', accent: '#5a2a18', belt: '#3a1808',
      beard: '#1a1010',
    },
    powerLabel: 'Múltiplas execuções',
  },
  /* === L4 COMMAND === */
  {
    id: 'mekka', codename: 'MEKKA', name: 'Chief', role: 'L4 — Command lead',
    cfg: {
      skin: '#f0c89a', hair: '#1a1010', hairStyle: 'short',
      shirt: '#0a1428', pants: '#06101c', accent: '#d6a82a',
      accessory: 'visor', accessoryColor: '#06101c', visorLens: '#5be8f5',
      tie: '#d6a82a',
    },
    powerLabel: 'Override central',
  },
  {
    id: 'galactus', codename: 'GALACTUS', name: 'Cosmic', role: 'L4 — Macro hunter',
    cfg: {
      skin: '#f0c89a', hair: '#3a1f6a', hairStyle: 'crown', helmetColor: '#5a2aa8',
      shirt: '#4a2a8c', pants: '#2a1860', cape: '#1a0a40',
      accent: '#ffd84a', emblem: '#ffd84a', belt: '#ffd84a',
    },
    powerLabel: 'Devorador',
  },
  {
    id: 'beast', codename: 'BEAST', name: 'Indigo', role: 'L4 — Quant',
    cfg: {
      skin: '#3a5aa8', skinShade: '#1a2a68',
      hair: '#1a2848', hairStyle: 'long',
      shirt: '#1a2840', pants: '#0a1828', accent: '#d6a82a',
      accessory: 'glasses', beard: '#1a2848',
    },
    powerLabel: 'Cálculo selvagem',
  },
  {
    id: 'jeangrey', codename: 'JEANGREY', name: 'Ember', role: 'L4 — Senior trader',
    cfg: {
      skin: '#f4d4a8', hair: '#c64628', hairStyle: 'long',
      shirt: '#2a6a48', pants: '#1a4828', accent: '#d6a82a', belt: '#d6a82a',
    },
    powerLabel: 'Telecinese',
  },
  {
    id: 'nighttrader', codename: 'NIGHTTRADER', name: 'Shade', role: 'L4 — Plantão noturno',
    cfg: {
      skin: '#e8b888', hair: '#1a1a3a', hairStyle: 'hood', hoodColor: '#1a1a3a',
      shirt: '#1a1a3a', pants: '#0a0a1a',
      accent: '#5be8f5', emblem: '#5be8f5', belt: '#5be8f5',
    },
    powerLabel: 'Visão noturna',
  },
  {
    id: 'dailypnlwriter', codename: 'DAILYPNLWRITER', name: 'Scribe', role: 'L4 — Reporter',
    cfg: {
      skin: '#f0c89a', hair: '#3a2818', hairStyle: 'short',
      shirt: '#5a3a28', pants: '#3a2818', accent: '#f0e4c8',
      accessory: 'glasses', beard: '#3a1f08', tie: '#a83a2a',
    },
    powerLabel: 'PnL diário',
  },
  {
    id: 'blackpanther', codename: 'BLACKPANTHER', name: 'Sleek', role: 'Top — Strategy lead',
    cfg: {
      mask: '#0a0a12', maskEyes: '#a8b0c0', hairStyle: 'hood', hoodColor: '#0a0a12',
      shirt: '#0a0a12', pants: '#06060c',
      accent: '#b8c0c8', emblem: '#b8c0c8', belt: '#b8c0c8',
    },
    powerLabel: 'Stealth',
  },
];

/* Build full registry — wrap each extra config in a draw fn */
const ALL_TRADERS = TRADERS.concat(
  EXTRA.map((e) => ({
    id: e.id,
    codename: e.codename,
    name: e.name,
    role: e.role,
    palette: [e.cfg.shirt, e.cfg.pants, e.cfg.accent || '#888', e.cfg.hair || e.cfg.helmetColor || '#222', '#0a0a14'],
    powerLabel: e.powerLabel,
    powerDesc: '',
    oldColors: [e.cfg.shirt, e.cfg.pants, e.cfg.accent || '#888'],
    draw: (ctx, frame, mode, t) => drawChibi(ctx, frame, mode, t, e.cfg),
  }))
);

window.SPRITES = {
  size: SPRITE_SIZE,
  traders: TRADERS,
  allTraders: ALL_TRADERS,
  drawOld: drawOld,
  drawChibi: drawChibi,
};

})();
