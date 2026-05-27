/* Sprites v3 Factory — 64×64 chibi factory with deep customisation.
   Produces Gen-4-quality sprites from declarative configs so we can
   author 19+ distinct characters without 150 lines of pixel code each.
   All designs are ORIGINAL; the only thing preserved from the heroes the
   traders are nicknamed after is the codename text label. */
(function () {

if (!window.PX || !window.FX) {
  console.error('pixel-engine + effects must load first');
  return;
}

const SIZE = 64;

/* ════════════════ COLOR HELPERS ════════════════ */

function shade(hex, amt) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const cl = (v) => Math.max(0, Math.min(255, Math.round(v + amt * 255)));
  return '#' + [cl(r), cl(g), cl(b)].map((v) => v.toString(16).padStart(2, '0')).join('');
}

function tones(base) {
  return {
    base,
    dark: shade(base, -0.22),
    light: shade(base, 0.18),
    deep: shade(base, -0.42),
  };
}

const LINE = '#0a0a14';

/* ════════════════ BODY PARTS ════════════════ */
/* Standard adult chibi layout in 64x64:
     y= 2-22  head (incl. helmet/hair above face)
     y=22-25  neck
     y=25-43  torso
     y=43-46  belt
     y=46-58  legs
     y=58-62  boots
     y=62-63  shadow */

/* === Shadow === */
function shadow(ctx, w, a) {
  PX.shadow(ctx, 32, 62, w || 22, a == null ? 0.4 : a);
}

/* === LEGS (slim default) === */
function legs(ctx, yo, suit, build) {
  const s = tones(suit);
  const w = build === 'bulky' ? 9 : build === 'massive' ? 10 : 8;
  const gap = build === 'massive' ? 4 : 4;
  const leftX = 32 - gap / 2 - w;
  const rightX = 32 + gap / 2;
  const y0 = 46;
  const h = 12;
  PX.r(ctx, leftX, y0 + yo, w, h, s.base);
  PX.r(ctx, rightX, y0 + yo, w, h, s.base);
  PX.r(ctx, leftX - 1, y0 + yo, 1, h, LINE);
  PX.r(ctx, leftX + w, y0 + yo, 1, h, LINE);
  PX.r(ctx, rightX - 1, y0 + yo, 1, h, LINE);
  PX.r(ctx, rightX + w, y0 + yo, 1, h, LINE);
  PX.r(ctx, leftX, y0 + yo, 1, h, s.dark);
  PX.r(ctx, leftX + w - 1, y0 + yo, 1, h, s.light);
  PX.r(ctx, rightX, y0 + yo, 1, h, s.dark);
  PX.r(ctx, rightX + w - 1, y0 + yo, 1, h, s.light);
}

/* === BOOTS === */
function boots(ctx, yo, color, cuffColor, build) {
  const c = tones(color);
  const w = build === 'bulky' ? 11 : build === 'massive' ? 12 : 10;
  const gap = build === 'massive' ? 4 : 4;
  const leftX = 32 - gap / 2 - w;
  const rightX = 32 + gap / 2;
  const y0 = 58;
  PX.r(ctx, leftX, y0 + yo, w, 4, c.base);
  PX.r(ctx, rightX, y0 + yo, w, 4, c.base);
  PX.r(ctx, leftX - 1, y0 + yo, 1, 4, LINE);
  PX.r(ctx, leftX + w, y0 + yo, 1, 4, LINE);
  PX.r(ctx, rightX - 1, y0 + yo, 1, 4, LINE);
  PX.r(ctx, rightX + w, y0 + yo, 1, 4, LINE);
  PX.r(ctx, leftX, y0 + 3 + yo, w, 1, LINE);
  PX.r(ctx, rightX, y0 + 3 + yo, w, 1, LINE);
  if (cuffColor) {
    PX.r(ctx, leftX, y0 + yo, w, 1, cuffColor);
    PX.r(ctx, rightX, y0 + yo, w, 1, cuffColor);
  }
  // Sole highlight
  PX.r(ctx, leftX, y0 + 2 + yo, w, 1, c.dark);
  PX.r(ctx, rightX, y0 + 2 + yo, w, 1, c.dark);
}

/* === TORSO === */
function torso(ctx, yo, suit, build) {
  const s = tones(suit);
  let x0 = 18, w = 28, y0 = 25, h = 18;
  if (build === 'bulky') { x0 = 16; w = 32; }
  if (build === 'massive') { x0 = 13; w = 38; h = 19; }
  PX.r(ctx, x0, y0 + yo, w, h, s.base);
  PX.r(ctx, x0 - 1, y0 + 1 + yo, 1, h - 1, LINE);
  PX.r(ctx, x0 + w, y0 + 1 + yo, 1, h - 1, LINE);
  PX.r(ctx, x0, y0 + yo, w, 1, LINE);
  PX.r(ctx, x0, y0 + h - 1 + yo, w, 1, LINE);
  // shading
  PX.r(ctx, x0, y0 + yo, 1, h, s.dark);
  PX.r(ctx, x0 + w - 1, y0 + yo, 1, h, s.light);
  // pec definition
  PX.r(ctx, x0 + 1, y0 + 1 + yo, w / 2 - 1, 5, s.light);
  PX.r(ctx, x0 + w / 2 + 1, y0 + 1 + yo, w / 2 - 2, 5, s.light);
  PX.r(ctx, x0 + w / 2 - 1, y0 + yo, 2, h, s.dark);
  return { x0, w, y0, h };
}

/* === ARMS === */
function arms(ctx, yo, suit, build, withHands, handColor) {
  const s = tones(suit);
  const armW = build === 'massive' ? 6 : build === 'bulky' ? 5 : 4;
  const leftX = build === 'massive' ? 7 : build === 'bulky' ? 11 : 13;
  const rightX = build === 'massive' ? 51 : build === 'bulky' ? 48 : 47;
  const y0 = 28;
  const h = 14;
  PX.r(ctx, leftX, y0 + yo, armW, h, s.base);
  PX.r(ctx, rightX, y0 + yo, armW, h, s.base);
  PX.r(ctx, leftX - 1, y0 + yo, 1, h, LINE);
  PX.r(ctx, leftX + armW, y0 + yo, 1, h, LINE);
  PX.r(ctx, rightX - 1, y0 + yo, 1, h, LINE);
  PX.r(ctx, rightX + armW, y0 + yo, 1, h, LINE);
  PX.r(ctx, leftX, y0 + yo, 1, h, s.dark);
  PX.r(ctx, rightX + armW - 1, y0 + yo, 1, h, s.light);
  if (withHands) {
    const hc = handColor || '#f4c896';
    const hw = armW + 2;
    PX.r(ctx, leftX - 1, 42 + yo, hw, 5, hc);
    PX.r(ctx, rightX, 42 + yo, hw, 5, hc);
    PX.r(ctx, leftX - 2, 42 + yo, 1, 5, LINE);
    PX.r(ctx, leftX + hw - 1, 42 + yo, 1, 5, LINE);
    PX.r(ctx, rightX - 1, 42 + yo, 1, 5, LINE);
    PX.r(ctx, rightX + hw, 42 + yo, 1, 5, LINE);
    PX.r(ctx, leftX - 1, 46 + yo, hw, 1, LINE);
    PX.r(ctx, rightX, 46 + yo, hw, 1, LINE);
    PX.r(ctx, leftX - 1, 42 + yo, hw, 1, shade(hc, 0.15));
    PX.r(ctx, rightX, 42 + yo, hw, 1, shade(hc, 0.15));
  }
  return { leftX, rightX, armW };
}

/* === BELT === */
function belt(ctx, yo, color, buckleColor, build) {
  const c = tones(color);
  let x0 = 17, w = 30;
  if (build === 'bulky') { x0 = 15; w = 34; }
  if (build === 'massive') { x0 = 12; w = 40; }
  PX.r(ctx, x0, 43 + yo, w, 4, c.base);
  PX.r(ctx, x0, 43 + yo, w, 1, LINE);
  PX.r(ctx, x0, 46 + yo, w, 1, LINE);
  PX.r(ctx, x0, 43 + yo, 1, 4, LINE);
  PX.r(ctx, x0 + w - 1, 43 + yo, 1, 4, LINE);
  PX.r(ctx, x0 + 1, 44 + yo, w - 2, 1, c.light);
  PX.r(ctx, x0 + 1, 45 + yo, w - 2, 1, c.dark);
  if (buckleColor) {
    PX.r(ctx, 29, 43 + yo, 6, 4, buckleColor);
    PX.r(ctx, 29, 43 + yo, 6, 1, LINE);
    PX.r(ctx, 29, 46 + yo, 6, 1, LINE);
    PX.r(ctx, 30, 44 + yo, 4, 1, shade(buckleColor, 0.3));
  }
}

/* === NECK === */
function neck(ctx, yo, skin) {
  PX.r(ctx, 28, 22 + yo, 8, 3, shade(skin, -0.2));
  PX.r(ctx, 27, 22 + yo, 1, 3, LINE);
  PX.r(ctx, 36, 22 + yo, 1, 3, LINE);
}

/* === HEAD: SKIN FACE === */
function headSkin(ctx, yo, skin) {
  const s = tones(skin);
  PX.r(ctx, 21, 4 + yo, 22, 18, s.base);
  PX.r(ctx, 20, 5 + yo, 1, 16, LINE);
  PX.r(ctx, 43, 5 + yo, 1, 16, LINE);
  PX.r(ctx, 21, 4 + yo, 22, 1, LINE);
  PX.r(ctx, 21, 21 + yo, 22, 1, LINE);
  // sides
  PX.r(ctx, 21, 5 + yo, 1, 16, s.dark);
  PX.r(ctx, 42, 5 + yo, 1, 16, s.dark);
  PX.r(ctx, 22, 20 + yo, 20, 1, s.dark);
  // cheek highlights
  PX.r(ctx, 23, 18 + yo, 2, 1, s.light);
  PX.r(ctx, 39, 18 + yo, 2, 1, s.light);
}

/* === HEAD: FULL MASK === */
function headMask(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 21, 4 + yo, 22, 18, c.base);
  PX.r(ctx, 20, 5 + yo, 1, 16, LINE);
  PX.r(ctx, 43, 5 + yo, 1, 16, LINE);
  PX.r(ctx, 21, 4 + yo, 22, 1, LINE);
  PX.r(ctx, 21, 21 + yo, 22, 1, LINE);
  // shading
  PX.r(ctx, 21, 5 + yo, 1, 16, c.dark);
  PX.r(ctx, 42, 5 + yo, 1, 16, c.dark);
  PX.r(ctx, 22, 5 + yo, 12, 2, c.light);
  PX.r(ctx, 22, 20 + yo, 20, 1, c.dark);
}

/* === HEAD: HELMET (full enclosed) === */
function headHelmet(ctx, yo, color, trimColor) {
  headMask(ctx, yo, color);
  if (trimColor) {
    // forehead trim band
    PX.r(ctx, 21, 7 + yo, 22, 2, trimColor);
    PX.r(ctx, 21, 7 + yo, 22, 1, shade(trimColor, 0.25));
    PX.r(ctx, 21, 8 + yo, 22, 1, shade(trimColor, -0.3));
  }
  // ridge across top
  PX.r(ctx, 28, 3 + yo, 8, 2, shade(color, -0.3));
  PX.r(ctx, 28, 3 + yo, 8, 1, LINE);
}

/* === HAIR === */
function hairShort(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 21, 4 + yo, 22, 5, c.base);
  PX.r(ctx, 20, 5 + yo, 1, 4, c.base);
  PX.r(ctx, 43, 5 + yo, 1, 4, c.base);
  PX.r(ctx, 21, 4 + yo, 22, 1, c.dark);
  // sideburns
  PX.r(ctx, 20, 9 + yo, 2, 2, c.base);
  PX.r(ctx, 42, 9 + yo, 2, 2, c.base);
  // highlight
  PX.r(ctx, 24, 5 + yo, 10, 1, c.light);
}

function hairLong(ctx, yo, color) {
  const c = tones(color);
  // top
  PX.r(ctx, 19, 3 + yo, 26, 7, c.base);
  PX.r(ctx, 19, 3 + yo, 26, 1, c.dark);
  // sides flowing down
  PX.r(ctx, 19, 10 + yo, 3, 14, c.base);
  PX.r(ctx, 42, 10 + yo, 3, 14, c.base);
  PX.r(ctx, 19, 10 + yo, 1, 14, c.dark);
  PX.r(ctx, 44, 10 + yo, 1, 14, c.dark);
  PX.r(ctx, 19, 3 + yo, 1, 21, LINE);
  PX.r(ctx, 44, 3 + yo, 1, 21, LINE);
  // highlight
  PX.r(ctx, 22, 4 + yo, 14, 1, c.light);
  PX.r(ctx, 21, 12 + yo, 1, 10, c.light);
  PX.r(ctx, 42, 12 + yo, 1, 10, c.light);
}

function hairSpiky(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 21, 5 + yo, 22, 5, c.base);
  // spikes pointing up
  PX.r(ctx, 19, 4 + yo, 3, 6, c.base);
  PX.r(ctx, 23, 1 + yo, 3, 8, c.base);
  PX.r(ctx, 27, 2 + yo, 4, 7, c.base);
  PX.r(ctx, 32, 0 + yo, 3, 9, c.base);
  PX.r(ctx, 36, 2 + yo, 4, 7, c.base);
  PX.r(ctx, 41, 1 + yo, 3, 8, c.base);
  // sideburns
  PX.r(ctx, 20, 10 + yo, 2, 3, c.base);
  PX.r(ctx, 42, 10 + yo, 2, 3, c.base);
  PX.r(ctx, 20, 13 + yo, 2, 4, c.base); // chops
  PX.r(ctx, 42, 13 + yo, 2, 4, c.base);
  // highlight on spikes
  PX.r(ctx, 24, 3 + yo, 1, 5, c.light);
  PX.r(ctx, 33, 2 + yo, 1, 6, c.light);
  PX.r(ctx, 37, 4 + yo, 1, 4, c.light);
}

function hairHooded(ctx, yo, hoodColor, faceColor) {
  // Hood wraps around head, leaving an oval face cutout
  const h = tones(hoodColor);
  PX.r(ctx, 16, 3 + yo, 32, 7, h.base);
  PX.r(ctx, 14, 6 + yo, 36, 18, h.base);
  PX.r(ctx, 16, 3 + yo, 32, 1, LINE);
  PX.r(ctx, 14, 6 + yo, 1, 18, LINE);
  PX.r(ctx, 49, 6 + yo, 1, 18, LINE);
  PX.r(ctx, 15, 6 + yo, 1, 18, h.dark);
  PX.r(ctx, 48, 6 + yo, 1, 18, h.light);
  PX.r(ctx, 17, 4 + yo, 30, 1, h.light);
  // Face cutout
  const fc = tones(faceColor);
  PX.r(ctx, 21, 9 + yo, 22, 13, fc.base);
  PX.r(ctx, 20, 10 + yo, 1, 11, LINE);
  PX.r(ctx, 43, 10 + yo, 1, 11, LINE);
  PX.r(ctx, 21, 9 + yo, 22, 1, LINE);
  PX.r(ctx, 21, 21 + yo, 22, 1, LINE);
  PX.r(ctx, 21, 10 + yo, 1, 11, fc.dark);
  PX.r(ctx, 42, 10 + yo, 1, 11, fc.dark);
}

function hairBald() { /* no-op */ }

function hairCrown(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 21, 6 + yo, 22, 4, c.base);
  PX.r(ctx, 21, 6 + yo, 22, 1, c.dark);
  // Tall horns/points
  PX.r(ctx, 17, 0 + yo, 4, 9, c.base);
  PX.r(ctx, 43, 0 + yo, 4, 9, c.base);
  PX.r(ctx, 24, -2 + yo, 4, 11, c.base);
  PX.r(ctx, 36, -2 + yo, 4, 11, c.base);
  PX.r(ctx, 30, -3 + yo, 4, 12, c.base);
  // Highlights on horns
  PX.r(ctx, 18, 1 + yo, 1, 8, c.light);
  PX.r(ctx, 25, -1 + yo, 1, 10, c.light);
  PX.r(ctx, 31, -2 + yo, 1, 11, c.light);
  PX.r(ctx, 37, -1 + yo, 1, 10, c.light);
  PX.r(ctx, 44, 1 + yo, 1, 8, c.light);
}

function hairCowl(ctx, yo, color) {
  // Hooded cowl with pointed top edges (no bat-ears — flat with bevels)
  const c = tones(color);
  PX.r(ctx, 18, 3 + yo, 28, 11, c.base);
  PX.r(ctx, 17, 4 + yo, 1, 14, LINE);
  PX.r(ctx, 46, 4 + yo, 1, 14, LINE);
  PX.r(ctx, 18, 3 + yo, 28, 1, LINE);
  PX.r(ctx, 18, 4 + yo, 28, 1, c.dark);
  PX.r(ctx, 18, 14 + yo, 28, 4, c.base);
  // Face cutout (open chin area)
  PX.r(ctx, 22, 14 + yo, 20, 8, '#f0c89a');
  PX.r(ctx, 22, 14 + yo, 20, 1, LINE);
  PX.r(ctx, 21, 15 + yo, 1, 7, LINE);
  PX.r(ctx, 42, 15 + yo, 1, 7, LINE);
}

/* === EYES === */
function eyesNormal(ctx, yo, irisColor) {
  PX.r(ctx, 23, 13 + yo, 6, 3, LINE);
  PX.r(ctx, 35, 13 + yo, 6, 3, LINE);
  PX.r(ctx, 24, 14 + yo, 4, 2, '#ffffff');
  PX.r(ctx, 36, 14 + yo, 4, 2, '#ffffff');
  PX.r(ctx, 25, 14 + yo, 2, 2, irisColor);
  PX.r(ctx, 37, 14 + yo, 2, 2, irisColor);
  PX.r(ctx, 26, 14 + yo, 1, 1, LINE);
  PX.r(ctx, 38, 14 + yo, 1, 1, LINE);
  // bright catchlight
  PX.r(ctx, 25, 14 + yo, 1, 1, '#ffffff');
  PX.r(ctx, 37, 14 + yo, 1, 1, '#ffffff');
}

function eyesMaskSlits(ctx, yo, lensColor) {
  PX.r(ctx, 22, 12 + yo, 8, 4, LINE);
  PX.r(ctx, 34, 12 + yo, 8, 4, LINE);
  PX.r(ctx, 23, 13 + yo, 6, 2, lensColor);
  PX.r(ctx, 35, 13 + yo, 6, 2, lensColor);
  PX.r(ctx, 23, 13 + yo, 6, 1, shade(lensColor, 0.3));
  PX.r(ctx, 35, 13 + yo, 6, 1, shade(lensColor, 0.3));
  PX.r(ctx, 24, 13 + yo, 1, 1, '#ffffff');
  PX.r(ctx, 36, 13 + yo, 1, 1, '#ffffff');
}

function eyesVisorBand(ctx, yo, bandColor, lensColor) {
  PX.r(ctx, 18, 11 + yo, 28, 5, bandColor);
  PX.r(ctx, 18, 11 + yo, 28, 1, LINE);
  PX.r(ctx, 18, 15 + yo, 28, 1, LINE);
  PX.r(ctx, 17, 12 + yo, 1, 3, LINE);
  PX.r(ctx, 46, 12 + yo, 1, 3, LINE);
  PX.r(ctx, 19, 12 + yo, 26, 2, lensColor);
  PX.r(ctx, 19, 12 + yo, 26, 1, shade(lensColor, 0.3));
}

function eyesGlasses(ctx, yo, frameColor) {
  PX.r(ctx, 21, 12 + yo, 9, 4, frameColor || LINE);
  PX.r(ctx, 34, 12 + yo, 9, 4, frameColor || LINE);
  PX.r(ctx, 30, 13 + yo, 4, 1, frameColor || LINE);
  // lens fill
  PX.r(ctx, 22, 13 + yo, 7, 2, '#9eb5cf');
  PX.r(ctx, 35, 13 + yo, 7, 2, '#9eb5cf');
  // pupil shine
  PX.r(ctx, 23, 13 + yo, 1, 1, '#ffffff');
  PX.r(ctx, 36, 13 + yo, 1, 1, '#ffffff');
  PX.r(ctx, 26, 14 + yo, 1, 1, LINE);
  PX.r(ctx, 38, 14 + yo, 1, 1, LINE);
}

/* === FACIAL DETAIL === */
function mouthLine(ctx, yo) {
  PX.r(ctx, 28, 19 + yo, 8, 1, LINE);
  PX.r(ctx, 27, 19 + yo, 1, 1, '#c4885a');
  PX.r(ctx, 36, 19 + yo, 1, 1, '#c4885a');
}

function goatee(ctx, yo, color) {
  PX.r(ctx, 27, 19 + yo, 10, 3, color);
  PX.r(ctx, 28, 22 + yo, 8, 1, color);
  PX.r(ctx, 27, 19 + yo, 10, 1, shade(color, -0.3));
}

function beard(ctx, yo, color) {
  PX.r(ctx, 20, 16 + yo, 24, 6, color);
  PX.r(ctx, 20, 22 + yo, 24, 2, color);
  // mustache split
  PX.r(ctx, 31, 18 + yo, 2, 2, shade(color, -0.4));
  PX.r(ctx, 20, 16 + yo, 24, 1, shade(color, -0.4));
}

/* === CAPE === */
function capeShort(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 14, 25 + yo, 36, 22, c.base);
  PX.r(ctx, 13, 26 + yo, 1, 20, LINE);
  PX.r(ctx, 50, 26 + yo, 1, 20, LINE);
  PX.r(ctx, 14, 25 + yo, 36, 1, LINE);
  PX.r(ctx, 14, 46 + yo, 36, 1, LINE);
  // folds
  PX.r(ctx, 14, 25 + yo, 1, 21, c.dark);
  PX.r(ctx, 49, 25 + yo, 1, 21, c.dark);
  PX.r(ctx, 24, 26 + yo, 1, 19, c.dark);
  PX.r(ctx, 39, 26 + yo, 1, 19, c.dark);
  PX.r(ctx, 17, 28 + yo, 3, 14, c.light);
  PX.r(ctx, 44, 28 + yo, 3, 14, c.light);
}

function capeLong(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 12, 25 + yo, 40, 33, c.base);
  PX.r(ctx, 11, 26 + yo, 1, 32, LINE);
  PX.r(ctx, 52, 26 + yo, 1, 32, LINE);
  PX.r(ctx, 12, 25 + yo, 40, 1, LINE);
  PX.r(ctx, 12, 57 + yo, 40, 1, LINE);
  // folds
  PX.r(ctx, 12, 25 + yo, 1, 32, c.dark);
  PX.r(ctx, 51, 25 + yo, 1, 32, c.dark);
  PX.r(ctx, 22, 26 + yo, 1, 30, c.dark);
  PX.r(ctx, 41, 26 + yo, 1, 30, c.dark);
  PX.r(ctx, 14, 28 + yo, 4, 26, c.light);
  PX.r(ctx, 46, 28 + yo, 4, 26, c.light);
}

/* === EMBLEM / CHEST DETAIL === */
function emblem(ctx, yo, color) {
  // Simple chest dot (override per character if needed)
  PX.r(ctx, 30, 32 + yo, 4, 4, color);
  PX.r(ctx, 30, 32 + yo, 4, 1, shade(color, 0.3));
  PX.r(ctx, 30, 35 + yo, 4, 1, shade(color, -0.3));
}

function sash(ctx, yo, color) {
  const c = tones(color);
  // Diagonal sash from left shoulder to right hip
  for (let i = 0; i < 16; i++) {
    PX.r(ctx, 18 + i, 26 + i + yo, 4, 1, c.base);
  }
  for (let i = 0; i < 16; i++) {
    PX.r(ctx, 18 + i, 26 + i + yo, 4, 1, c.base);
    PX.r(ctx, 18 + i, 26 + i + yo, 1, 1, c.light);
    PX.r(ctx, 21 + i, 26 + i + yo, 1, 1, c.dark);
  }
}

function chestStripe(ctx, yo, color) {
  PX.r(ctx, 31, 25 + yo, 2, 17, color);
  PX.r(ctx, 31, 25 + yo, 2, 1, shade(color, 0.3));
}

function pauldrons(ctx, yo, color) {
  const c = tones(color);
  PX.r(ctx, 14, 25 + yo, 6, 6, c.base);
  PX.r(ctx, 44, 25 + yo, 6, 6, c.base);
  PX.r(ctx, 13, 26 + yo, 1, 5, LINE);
  PX.r(ctx, 50, 26 + yo, 1, 5, LINE);
  PX.r(ctx, 14, 25 + yo, 6, 1, LINE);
  PX.r(ctx, 44, 25 + yo, 6, 1, LINE);
  PX.r(ctx, 14, 30 + yo, 6, 1, LINE);
  PX.r(ctx, 44, 30 + yo, 6, 1, LINE);
  PX.r(ctx, 14, 26 + yo, 1, 4, c.dark);
  PX.r(ctx, 49, 26 + yo, 1, 4, c.light);
  PX.r(ctx, 15, 26 + yo, 4, 1, c.light);
  PX.r(ctx, 45, 26 + yo, 4, 1, c.light);
}

/* ════════════════ FACTORY ════════════════ */

function buildSprite(cfg) {
  return function (ctx, frame, mode, t) {
    const yo = (mode === 'idle' && frame % 2 === 1) ? -1 : 0;

    /* Allow per-character power offset (e.g., flyers lift) */
    let yOff = yo;
    if (mode === 'power' && cfg.powerLift) {
      yOff = yo - cfg.powerLift - Math.round(Math.sin(t * Math.PI) * 3);
    }

    shadow(ctx, mode === 'power' && cfg.powerLift ? Math.max(8, 22 - cfg.powerLift) : 22,
                mode === 'power' && cfg.powerLift ? 0.2 : 0.4);

    /* CAPE behind body */
    if (cfg.cape) {
      if (cfg.cape.long) capeLong(ctx, yOff, cfg.cape.color);
      else capeShort(ctx, yOff, cfg.cape.color);
    }

    /* BODY */
    const build = cfg.build || 'regular';
    legs(ctx, yOff, cfg.pants || cfg.suit, build);
    boots(ctx, yOff, cfg.boot || cfg.pants || cfg.suit, cfg.bootCuff, build);
    torso(ctx, yOff, cfg.suit, build);
    if (cfg.belt) belt(ctx, yOff, cfg.belt, cfg.beltBuckle, build);

    /* Chest detail */
    if (cfg.chestStripe) chestStripe(ctx, yOff, cfg.chestStripe);
    if (cfg.sash) sash(ctx, yOff, cfg.sash);
    if (cfg.emblem) emblem(ctx, yOff, cfg.emblem);
    if (cfg.pauldrons) pauldrons(ctx, yOff, cfg.pauldrons);

    /* ARMS — drawn over torso */
    const handCol = cfg.glove || (cfg.mask ? cfg.suit : (cfg.skin || '#f4c896'));
    arms(ctx, yOff, cfg.armSuit || cfg.suit, build, !cfg.skipHands, handCol);

    /* NECK */
    if (!cfg.mask) neck(ctx, yOff, cfg.skin || '#f4c896');

    /* HEAD */
    if (cfg.mask) {
      headMask(ctx, yOff, cfg.mask);
    } else if (cfg.helmet) {
      headHelmet(ctx, yOff, cfg.helmet, cfg.helmetTrim);
    } else if (cfg.hair === 'hooded') {
      hairHooded(ctx, yOff, cfg.hoodColor || cfg.hairColor || '#1a1a28', cfg.skin || '#f4c896');
    } else if (cfg.hair === 'cowl') {
      hairCowl(ctx, yOff, cfg.cowlColor || cfg.suit);
    } else {
      headSkin(ctx, yOff, cfg.skin || '#f4c896');
      if (cfg.hair === 'short') hairShort(ctx, yOff, cfg.hairColor || '#2a1808');
      else if (cfg.hair === 'long') hairLong(ctx, yOff, cfg.hairColor || '#2a1808');
      else if (cfg.hair === 'spiky') hairSpiky(ctx, yOff, cfg.hairColor || '#2a1808');
      else if (cfg.hair === 'crown') hairCrown(ctx, yOff, cfg.helmetColor || '#5a2aa8');
      else if (cfg.hair === 'bald') hairBald();
    }

    /* EYES & FACE */
    if (cfg.mask || cfg.helmet) {
      if (cfg.eyes === 'visor') eyesVisorBand(ctx, yOff, cfg.visorColor || LINE, cfg.lensColor || '#5be8f5');
      else eyesMaskSlits(ctx, yOff, cfg.lensColor || '#ffffff');
    } else if (cfg.hair === 'cowl') {
      eyesMaskSlits(ctx, yOff, cfg.lensColor || '#ffffff');
    } else if (cfg.eyes === 'glasses') {
      eyesGlasses(ctx, yOff, cfg.glassesColor);
    } else if (cfg.eyes === 'visor') {
      eyesVisorBand(ctx, yOff, cfg.visorColor || LINE, cfg.lensColor || '#5be8f5');
    } else {
      eyesNormal(ctx, yOff, cfg.iris || '#3a5a8a');
    }

    /* MOUTH detail */
    if (!cfg.mask && !cfg.helmet && cfg.hair !== 'cowl') {
      if (cfg.beard) beard(ctx, yOff, cfg.beard);
      else if (cfg.goatee) goatee(ctx, yOff, cfg.goatee);
      else mouthLine(ctx, yOff);
    }

    /* POWER EFFECT (custom) */
    if (mode === 'power' && cfg.power) {
      cfg.power(ctx, frame, t, yOff);
    }
  };
}

/* ════════════════ 19 CHARACTER CONFIGS ════════════════ */

function powerSpiderWeb(ctx, frame, t) {
  // Diagonal silk line + small spider mark
  FX.webline(ctx, 4, 16, 60, 6, '#ffd84a');
  PX.r(ctx, 1, 26, 3, 1, '#3a2a5a');
  PX.r(ctx, 0, 30, 3, 1, '#3a2a5a');
}

function powerShockwave(ctx, frame, t) {
  const r = Math.round(t * 28);
  if (r > 4 && r < 28) {
    FX.shock(ctx, 32, 60, r, '#caa066');
    FX.shock(ctx, 32, 60, Math.max(2, r - 3), '#e8c89c');
  }
}

function powerBeam(ctx, frame, t, yo) {
  const len = 18 + Math.round(t * 26);
  FX.beam(ctx, 46, 11 + yo, len, frame, '#ff3a2c', '#ff8a6c', '#fff5e6');
  PX.r(ctx, 18, 11 + yo, 28, 1, '#ff8a6c');
}

function powerSparkles(ctx, frame, t, yo, color) {
  const c = color || '#a8e0ff';
  const pts = [[8, 22], [54, 26], [4, 38], [58, 42], [10, 50], [52, 18]];
  pts.forEach(([sx, sy], i) => {
    if ((frame + i) % 3 === 0) return;
    PX.r(ctx, sx, sy + yo, 1, 1, c);
    PX.r(ctx, sx + 1, sy + 1 + yo, 1, 1, c);
    PX.r(ctx, sx - 1, sy + 1 + yo, 1, 1, c);
  });
}

function powerArrow(ctx, frame, t, yo) {
  // Arrow streaking right
  const ax = Math.round(8 + t * 50);
  PX.r(ctx, ax - 6, 30 + yo, 6, 1, '#d4a834');
  PX.r(ctx, ax - 2, 28 + yo, 2, 5, '#d4a834');
  PX.r(ctx, ax, 30 + yo, 1, 1, '#fff5b8');
}

function powerArcane(ctx, frame, t, yo) {
  // Mystic circle in hand
  const r = 6 + (frame % 3);
  for (let a = 0; a < 360; a += 30) {
    const rad = (a * Math.PI) / 180;
    const x = Math.round(12 + Math.cos(rad) * r);
    const y = Math.round(40 + yo + Math.sin(rad) * r);
    PX.r(ctx, x, y, 1, 1, '#d65aff');
  }
  PX.circle(ctx, 12, 40 + yo, 2, '#a83af5');
  PX.r(ctx, 12, 40 + yo, 1, 1, '#fff5ff');
}

function powerHammer(ctx, frame, t, yo) {
  // Hammer swing arc + spark
  PX.r(ctx, 50, 20 + yo, 8, 8, '#a8a8b8');
  PX.r(ctx, 50, 20 + yo, 8, 1, LINE);
  PX.r(ctx, 50, 27 + yo, 8, 1, LINE);
  PX.r(ctx, 50, 20 + yo, 1, 8, LINE);
  PX.r(ctx, 57, 20 + yo, 1, 8, LINE);
  PX.r(ctx, 51, 21 + yo, 6, 1, '#e0e0f0');
  // Lightning
  PX.r(ctx, 48, 18 + yo, 2, 2, '#ffd84a');
  PX.r(ctx, 54, 16 + yo, 2, 3, '#ffd84a');
}

function powerTrident(ctx, frame, t, yo) {
  // Trident held to side
  PX.r(ctx, 52, 18 + yo, 2, 26, '#d4a834');
  PX.r(ctx, 50, 14 + yo, 2, 6, '#a8e0ff');
  PX.r(ctx, 54, 14 + yo, 2, 6, '#a8e0ff');
  PX.r(ctx, 52, 12 + yo, 2, 5, '#a8e0ff');
  PX.r(ctx, 50, 14 + yo, 6, 1, LINE);
}

function powerSynth(ctx, frame, t, yo) {
  // Forehead gem glows + data ribbons
  PX.r(ctx, 30, 6 + yo, 4, 3, '#5be8f5');
  PX.r(ctx, 31, 5 + yo, 2, 5, '#a8f4ff');
  PX.r(ctx, 31, 6 + yo, 2, 1, '#ffffff');
  // Data streams
  for (let i = 0; i < 4; i++) {
    PX.r(ctx, 4 + i * 14, 30 - (frame * 2) % 8, 1, 2, '#5be8f5');
  }
}

function powerMental(ctx, frame, t, yo) {
  // Concentric rings around head
  for (let i = 1; i <= 3; i++) {
    if ((frame + i) % 3 !== 0) continue;
    const r = 14 + i * 3;
    FX.shock(ctx, 32, 14 + yo, r, '#d65aff');
  }
}

function powerDualBlade(ctx, frame, t, yo) {
  // Two katanas crossed behind
  PX.r(ctx, 10, 18 + yo, 1, 22, '#e0e0f0');
  PX.r(ctx, 53, 18 + yo, 1, 22, '#e0e0f0');
  PX.r(ctx, 11, 18 + yo, 1, 22, '#a0a0b0');
  PX.r(ctx, 52, 18 + yo, 1, 22, '#a0a0b0');
  PX.r(ctx, 9, 38 + yo, 3, 3, '#3a1808');
  PX.r(ctx, 52, 38 + yo, 3, 3, '#3a1808');
}

function powerClaws(ctx, frame, t, yo) {
  // 3 claws extending from each hand
  for (let i = 0; i < 3; i++) {
    PX.r(ctx, 12 - i * 2, 46 + yo, 2, 6, '#e0e0f0');
    PX.r(ctx, 52 + i * 2, 46 + yo, 2, 6, '#e0e0f0');
  }
}

function powerCosmic(ctx, frame, t, yo) {
  // Stars + cosmic energy around
  const pts = [[6, 8], [56, 12], [4, 30], [58, 36], [8, 50], [54, 50]];
  pts.forEach(([x, y], i) => {
    if ((frame + i) % 2 === 0) return;
    PX.r(ctx, x, y + yo, 1, 3, '#ffd84a');
    PX.r(ctx, x - 1, y + 1 + yo, 3, 1, '#ffd84a');
    PX.r(ctx, x, y + 1 + yo, 1, 1, '#ffffff');
  });
}

function powerQuant(ctx, frame, t, yo) {
  // Floating equations / digits
  const chars = '01';
  for (let i = 0; i < 6; i++) {
    const x = 4 + ((i * 11 + frame * 3) % 56);
    const y = 14 + ((i * 7) % 32);
    PX.r(ctx, x, y + yo, 2, 3, '#5be8f5');
  }
}

function powerTelekinesis(ctx, frame, t, yo) {
  // Glowing aura around extended hand + floating object
  PX.circle(ctx, 12, 44 + yo, 4, '#d65aff');
  PX.circle(ctx, 12, 44 + yo, 2, '#fff5ff');
  PX.r(ctx, 52, 30 + yo, 3, 3, '#d65aff');
  PX.r(ctx, 56, 24 + yo, 2, 2, '#d65aff');
}

function powerNightVision(ctx, frame, t, yo) {
  // Cyan glow eyes + sonar pulse
  PX.r(ctx, 22, 12 + yo, 8, 4, '#5be8f5');
  PX.r(ctx, 34, 12 + yo, 8, 4, '#5be8f5');
  const r = Math.round(t * 30);
  if (r > 8 && r < 30) {
    FX.shock(ctx, 32, 32 + yo, r, '#5be8f5');
  }
}

function powerPenStroke(ctx, frame, t, yo) {
  // Floating pen + paper sheets
  PX.r(ctx, 50, 30 + yo, 1, 8, '#0a0a14');
  PX.r(ctx, 49, 38 + yo, 3, 1, '#d6a82a');
  PX.r(ctx, 54, 26 + yo, 6, 8, '#f0e8d4');
  PX.r(ctx, 54, 26 + yo, 6, 1, LINE);
  PX.r(ctx, 55, 28 + yo, 4, 1, LINE);
  PX.r(ctx, 55, 30 + yo, 4, 1, LINE);
  PX.r(ctx, 55, 32 + yo, 3, 1, LINE);
}

function powerStealth(ctx, frame, t, yo) {
  // Smoke wisps around body
  const ys = [22, 32, 42];
  ys.forEach((y, i) => {
    if ((frame + i) % 2 === 0) return;
    PX.r(ctx, 4, y + yo, 4, 1, '#3a3a52');
    PX.r(ctx, 56, y + 2 + yo, 4, 1, '#3a3a52');
    PX.r(ctx, 6, y + 1 + yo, 2, 1, '#5a5a72');
  });
}

/* === Character config list (19 to author) === */

const CONFIGS = [
  /* ---- SPIDERMAN (main 6) ---- */
  {
    id: 'arachne', codename: 'SPIDERMAN', name: 'Arachne',
    role: 'L4 — Night-trader', powerLabel: 'Linha de seda',
    cfg: {
      suit: '#5a2aa8', mask: '#5a2aa8',
      pants: '#3a1880', boot: '#28104a', bootCuff: '#f5c038',
      belt: '#f5c038', glove: '#3a1880',
      lensColor: '#ffd84a', emblem: '#f5c038',
      power: powerSpiderWeb,
    },
  },
  /* ---- HULK (main 6) ---- */
  {
    id: 'titan', codename: 'HULK', name: 'Titan',
    role: 'L3 — Risk/Exec', powerLabel: 'Stomp',
    cfg: {
      build: 'massive', skin: '#5fa14b', skinSh: '#2f6620',
      suit: '#5fa14b', armSuit: '#5fa14b', pants: '#3d2818',
      boot: '#1f1208', glove: '#5fa14b',
      hair: 'short', hairColor: '#1a1108',
      iris: '#2a3a18', skipHands: false,
      power: powerShockwave,
    },
  },
  /* ---- CYCLOPS (main 6) ---- */
  {
    id: 'visor', codename: 'CYCLOPS', name: 'Visor',
    role: 'L3 — Risk Check', powerLabel: 'Feixe',
    cfg: {
      suit: '#1a2848', pants: '#0a1428', boot: '#06101c',
      belt: '#d6a82a', beltBuckle: '#7a5810', chestStripe: '#d6a82a',
      hair: 'short', hairColor: '#3a2010',
      skin: '#f4c896',
      eyes: 'visor', visorColor: '#1a0608', lensColor: '#e83a2c',
      power: powerBeam,
    },
  },
  /* ---- L1: HAWKEYE ---- */
  {
    id: 'falcon', codename: 'HAWKEYE', name: 'Falcon',
    role: 'L1 — Sniper de momentum', powerLabel: 'Tiro certeiro',
    cfg: {
      suit: '#3a1f4a', pants: '#1a0a28', boot: '#0a0418',
      belt: '#5a3a18', glove: '#5a3a18',
      skin: '#f0c89a', hair: 'short', hairColor: '#3a1f10',
      eyes: 'visor', visorColor: '#1a0a28', lensColor: '#d6a82a',
      chestStripe: '#d6a82a',
      power: powerArrow,
    },
  },
  /* ---- L1: DOCTORSTRANGE ---- */
  {
    id: 'sage', codename: 'DOCTORSTRANGE', name: 'Sage',
    role: 'L1 — Padrões ocultos', powerLabel: 'Leitura mística',
    cfg: {
      suit: '#5a1818', pants: '#3a1010', boot: '#1a0808',
      belt: '#d6a82a', beltBuckle: '#7a5810',
      cape: { color: '#7a1a1a' },
      skin: '#e8b888', hair: 'short', hairColor: '#1a0d04',
      goatee: '#1a0d04', emblem: '#d6a82a',
      iris: '#3a5a78',
      power: powerArcane,
    },
  },
  /* ---- L1: THOR ---- */
  {
    id: 'hammer', codename: 'THOR', name: 'Hammer',
    role: 'L1 — Macro forte', powerLabel: 'Quebra-resistência',
    cfg: {
      build: 'bulky',
      suit: '#1a4a6a', pants: '#5a3a18', boot: '#3a2010', bootCuff: '#d6a82a',
      belt: '#5a3a18', beltBuckle: '#d6a82a',
      cape: { color: '#7a1818' },
      pauldrons: '#a8a8b8',
      skin: '#f4d4a8', hair: 'long', hairColor: '#d4a85a',
      beard: '#a07840', iris: '#3a8ad6',
      chestStripe: '#a8a8b8',
      power: powerHammer,
    },
  },
  /* ---- L1: AQUAMAN ---- */
  {
    id: 'tide', codename: 'AQUAMAN', name: 'Tide',
    role: 'L1 — Fluxos & liquidez', powerLabel: 'Maré',
    cfg: {
      suit: '#d6831a', pants: '#1a5a3a', boot: '#0a3a1a', bootCuff: '#9be8a4',
      belt: '#5a3a18', beltBuckle: '#d6a82a',
      skin: '#f4d4a8', hair: 'long', hairColor: '#d4a85a',
      iris: '#5be8f5', emblem: '#9be8a4',
      power: powerTrident,
    },
  },
  /* ---- L2: VISION ---- */
  {
    id: 'synth', codename: 'VISION', name: 'Synth',
    role: 'L2 — Estratégia sintética', powerLabel: 'Síntese de dados',
    cfg: {
      suit: '#1a3a78', pants: '#0a1a48', boot: '#020812', bootCuff: '#d6a82a',
      belt: '#d6a82a', beltBuckle: '#7a5810',
      cape: { color: '#d6a82a' },
      skin: '#d65a3a', hair: 'short', hairColor: '#8a2818',
      iris: '#5be8f5', emblem: '#5be8f5',
      power: powerSynth,
    },
  },
  /* ---- L2: PROFESSORX ---- */
  {
    id: 'mentor', codename: 'PROFESSORX', name: 'Mentor',
    role: 'L2 — Portfolio Manager', powerLabel: 'Coord. mental',
    cfg: {
      suit: '#2a3a4a', pants: '#1a1a2a', boot: '#0a0a14',
      belt: '#1a1010', chestStripe: '#7a1818',
      skin: '#f0c89a', hair: 'bald', hairColor: '#000',
      eyes: 'glasses',
      power: powerMental,
    },
  },
  /* ---- L2: DEADPOOL ---- */
  {
    id: 'joker', codename: 'DEADPOOL', name: 'Joker',
    role: 'L2 — Trades não-convencionais', powerLabel: 'Caos calculado',
    cfg: {
      suit: '#a8281c', mask: '#a8281c',
      pants: '#5a1410', boot: '#1a0808', bootCuff: '#1a1010',
      belt: '#1a1010', glove: '#1a1010',
      lensColor: '#f5e8c8', emblem: '#1a1010',
      power: powerDualBlade,
    },
  },
  /* ---- L3: BATMAN ---- */
  {
    id: 'sentinel', codename: 'BATMAN', name: 'Sentinel',
    role: 'L3 — Risk officer', powerLabel: 'Vigília',
    cfg: {
      suit: '#1a1a28', pants: '#0a0a18', boot: '#04040c', bootCuff: '#d6a82a',
      belt: '#d6a82a', beltBuckle: '#7a5810',
      cape: { color: '#0a0a18', long: true },
      hair: 'cowl', cowlColor: '#1a1a28',
      lensColor: '#fff', emblem: '#1a1a28',
      chestStripe: '#3a3a4a',
      power: powerStealth,
    },
  },
  /* ---- L3: WOLVERINE ---- */
  {
    id: 'claw', codename: 'WOLVERINE', name: 'Claw',
    role: 'L3 — Execução agressiva', powerLabel: 'Garras',
    cfg: {
      build: 'bulky',
      suit: '#d6a82a', pants: '#5a2a18', boot: '#3a1808', bootCuff: '#1a0808',
      belt: '#3a1808', beltBuckle: '#d6a82a',
      skin: '#f0c89a', hair: 'spiky', hairColor: '#1a1010',
      beard: '#1a1010', iris: '#3a3a18',
      chestStripe: '#3a1808',
      power: powerClaws,
    },
  },
  /* ---- L4: MEKKA ---- */
  {
    id: 'chief', codename: 'MEKKA', name: 'Chief',
    role: 'L4 — Command lead', powerLabel: 'Override',
    cfg: {
      suit: '#06141d', pants: '#02080f', boot: '#04101c',
      belt: '#d6a82a', beltBuckle: '#7a5810',
      chestStripe: '#d6a82a',
      skin: '#f0c89a', hair: 'short', hairColor: '#1a1010',
      eyes: 'visor', visorColor: '#02080f', lensColor: '#5be8f5',
      pauldrons: '#1a2840',
      power: function (ctx, frame, t, yo) {
        // Concentric command rings
        for (let i = 1; i <= 4; i++) {
          if ((frame + i) % 4 !== 0) continue;
          FX.shock(ctx, 32, 32 + yo, 10 + i * 3, '#5be8f5');
        }
      },
    },
  },
  /* ---- L4: GALACTUS ---- */
  {
    id: 'cosmic', codename: 'GALACTUS', name: 'Cosmic',
    role: 'L4 — Macro hunter', powerLabel: 'Devorador',
    cfg: {
      build: 'bulky',
      suit: '#4a2a8c', pants: '#2a1860', boot: '#1a0840', bootCuff: '#ffd84a',
      belt: '#ffd84a', beltBuckle: '#a8780a',
      cape: { color: '#1a0a40', long: true },
      pauldrons: '#7a4ad0',
      skin: '#f0c89a', hair: 'crown', helmetColor: '#5a2aa8',
      eyes: 'visor', visorColor: '#28104a', lensColor: '#ffd84a',
      emblem: '#ffd84a',
      power: powerCosmic,
    },
  },
  /* ---- L4: BEAST ---- */
  {
    id: 'indigo', codename: 'BEAST', name: 'Indigo',
    role: 'L4 — Quant', powerLabel: 'Cálculo selvagem',
    cfg: {
      build: 'bulky',
      suit: '#1a2840', pants: '#0a1828', boot: '#020812',
      belt: '#d6a82a',
      skin: '#3a5aa8',
      hair: 'long', hairColor: '#1a2848',
      eyes: 'glasses', glassesColor: '#d6a82a',
      beard: '#1a2848', emblem: '#d6a82a',
      power: powerQuant,
    },
  },
  /* ---- L4: JEANGREY ---- */
  {
    id: 'ember', codename: 'JEANGREY', name: 'Ember',
    role: 'L4 — Senior trader', powerLabel: 'Telecinese',
    cfg: {
      suit: '#1a5a3a', pants: '#0a3a1a', boot: '#021808',
      belt: '#d6a82a', beltBuckle: '#7a5810',
      skin: '#f4d4a8', hair: 'long', hairColor: '#c64628',
      iris: '#5fa14b', chestStripe: '#d6a82a',
      power: powerTelekinesis,
    },
  },
  /* ---- L4: NIGHTTRADER ---- */
  {
    id: 'shade', codename: 'NIGHTTRADER', name: 'Shade',
    role: 'L4 — Plantão noturno', powerLabel: 'Visão noturna',
    cfg: {
      suit: '#1a1a3a', pants: '#0a0a1a', boot: '#020208', bootCuff: '#5be8f5',
      belt: '#5be8f5', beltBuckle: '#1a4a78',
      hair: 'hooded', hoodColor: '#0a0a18',
      skin: '#e8b888',
      iris: '#5be8f5', emblem: '#5be8f5',
      power: powerNightVision,
    },
  },
  /* ---- L4: DAILYPNLWRITER ---- */
  {
    id: 'scribe', codename: 'DAILYPNLWRITER', name: 'Scribe',
    role: 'L4 — Reporter', powerLabel: 'Daily PnL',
    cfg: {
      suit: '#5a3a28', pants: '#3a2818', boot: '#1a0808',
      belt: '#a83a2a', chestStripe: '#f0e8d4',
      skin: '#f0c89a', hair: 'short', hairColor: '#3a2818',
      eyes: 'glasses', beard: '#3a1f08',
      power: powerPenStroke,
    },
  },
  /* ---- TOP: BLACKPANTHER ---- */
  {
    id: 'sleek', codename: 'BLACKPANTHER', name: 'Sleek',
    role: 'Top — Strategy lead', powerLabel: 'Stealth',
    cfg: {
      suit: '#0a0a12', mask: '#0a0a12',
      pants: '#06060c', boot: '#020208', bootCuff: '#b8c0c8',
      belt: '#b8c0c8', glove: '#0a0a12',
      lensColor: '#a8b0c0', emblem: '#b8c0c8',
      chestStripe: '#1a1a22',
      power: powerStealth,
    },
  },
  /* ---- DEV/QA: PROMETHEUS ----
   * Prompt auditor & runtime observer. NOT a trader.
   * Visual: orange-flame outfit (orange suit + amber belt + flame emblem),
   * sky-blue eye glow (data lens), cowl head (focused/observing).
   * Reuses powerSynth (no new power renderer needed for v1).
   */
  {
    id: 'oracle', codename: 'PROMETHEUS', name: 'Oracle',
    role: 'Dev/QA — Prompt auditor & observer', powerLabel: 'Audit / Learn',
    cfg: {
      suit: '#f97316', pants: '#7c2d12', boot: '#431407', bootCuff: '#fde68a',
      belt: '#fbbf24', beltBuckle: '#7c2d12',
      skin: '#f5d4b0', hair: 'cowl', hairColor: '#fdba74',
      iris: '#bae6fd', emblem: '#fde68a',
      chestStripe: '#fdba74',
      power: powerSynth,
    },
  },
  /* ────────────────────────────────────────────────────────────────
   * ESCRITÓRIO ESTENDIDO — 8 agentes Python que estavam sem sprite.
   * Adicionados em 2026-05-26. Cada um com identidade visual distinta.
   * ──────────────────────────────────────────────────────────────── */

  /* ICEMAN — External Research (src/agents/ice_man.py) */
  {
    id: 'frost', codename: 'ICEMAN', name: 'Frost',
    role: 'L4 — External Research', powerLabel: 'Cold Recon',
    cfg: {
      suit: '#7dd3fc', pants: '#0c4a6e', boot: '#082f49', bootCuff: '#e0f2fe',
      belt: '#bae6fd', beltBuckle: '#0369a1',
      skin: '#f5d4b0', hair: 'short', hairColor: '#e0f2fe',
      iris: '#bae6fd', emblem: '#bae6fd',
      chestStripe: '#bae6fd',
      power: powerSynth,
    },
  },

  /* MENTOR — Charles Xavier — Self-Improvement loop (src/agents/mentor.py) */
  {
    id: 'xavier', codename: 'MENTOR', name: 'Xavier',
    role: 'L4 — Self-Improvement Loop', powerLabel: 'Telepath',
    cfg: {
      suit: '#a3a3a3', pants: '#525252', boot: '#262626', bootCuff: '#d4d4d4',
      belt: '#d4d4d4', beltBuckle: '#a16207',
      skin: '#f5d4b0', hair: 'bald', hairColor: '#525252',
      iris: '#facc15', emblem: '#a3a3a3',
      chestStripe: '#d4d4d4',
      power: powerSynth,
    },
  },

  /* KPISAGE — Measurement / KPI (src/agents/sage.py) */
  {
    id: 'kpi', codename: 'KPISAGE', name: 'Compass',
    role: 'L4 — Measurement / KPI', powerLabel: 'Track / Score',
    cfg: {
      suit: '#06b6d4', pants: '#155e75', boot: '#083344', bootCuff: '#a5f3fc',
      belt: '#67e8f9', beltBuckle: '#0891b2',
      skin: '#f5d4b0', hair: 'short', hairColor: '#0e7490',
      iris: '#22d3ee', emblem: '#67e8f9',
      chestStripe: '#67e8f9',
      power: powerSynth,
    },
  },

  /* CYPHER — Code Auditor (src/agents/code_auditor.py) */
  {
    id: 'cypher', codename: 'CYPHER', name: 'Cypher',
    role: 'L4 — Code Auditor', powerLabel: 'Decode',
    cfg: {
      suit: '#10b981', pants: '#064e3b', boot: '#022c22', bootCuff: '#a7f3d0',
      belt: '#34d399', beltBuckle: '#065f46',
      skin: '#f5d4b0', hair: 'short', hairColor: '#065f46',
      iris: '#10b981', emblem: '#a7f3d0',
      chestStripe: '#34d399',
      power: powerSynth,
    },
  },

  /* FORGE — Ops Scanner (src/agents/ops_scanner.py) */
  {
    id: 'anvil', codename: 'FORGE', name: 'Anvil',
    role: 'L4 — Ops Scanner', powerLabel: 'Tech / Build',
    cfg: {
      suit: '#fb923c', pants: '#7c2d12', boot: '#431407', bootCuff: '#fed7aa',
      belt: '#fdba74', beltBuckle: '#9a3412',
      skin: '#f5d4b0', hair: 'short', hairColor: '#1c1917',
      iris: '#facc15', emblem: '#fed7aa',
      chestStripe: '#fdba74',
      power: powerSynth,
    },
  },

  /* DOMINO — Risk Scanner (src/agents/risk_scanner.py) */
  {
    id: 'mark', codename: 'DOMINO', name: 'Mark',
    role: 'L4 — Risk Scanner', powerLabel: 'Probability',
    cfg: {
      suit: '#1c1917', pants: '#0c0a09', boot: '#000000', bootCuff: '#f5f5f4',
      belt: '#f5f5f4', beltBuckle: '#a8a29e',
      skin: '#f5d4b0', hair: 'short', hairColor: '#f5f5f4',
      iris: '#fbbf24', emblem: '#f5f5f4',
      chestStripe: '#f5f5f4',
      power: powerSynth,
    },
  },

  /* NICKFURY — Mission Commander (src/agents/nick_fury.py) */
  {
    id: 'patch', codename: 'NICKFURY', name: 'Patch',
    role: 'L4 — Mission Commander', powerLabel: 'Command',
    cfg: {
      suit: '#0a0a14', pants: '#0a0a14', boot: '#000000', bootCuff: '#3f3f46',
      belt: '#3f3f46', beltBuckle: '#71717a',
      skin: '#8b5a3c', hair: 'bald', hairColor: '#0a0a14',
      iris: '#22c55e', emblem: '#22c55e',
      chestStripe: '#1c1917',
      power: powerSynth,
    },
  },

  /* PORTFOLIO — Read-only equity & open-positions snapshot
   * (src/agents/portfolio_manager.py) */
  {
    id: 'ledger', codename: 'PORTFOLIO', name: 'Ledger',
    role: 'L4 — Snapshot Service', powerLabel: 'Snapshot',
    cfg: {
      suit: '#1e40af', pants: '#172554', boot: '#0c0a09', bootCuff: '#dbeafe',
      belt: '#93c5fd', beltBuckle: '#1e3a8a',
      skin: '#f5d4b0', hair: 'short', hairColor: '#1e3a8a',
      iris: '#3b82f6', emblem: '#dbeafe',
      chestStripe: '#93c5fd',
      power: powerSynth,
    },
  },

  /* CABLE (Nathan Summers) — Derivatives Intelligence Analyst
   * (src/agents/cable.py). Read-only, sem trade, sem LLM. Soldado
   * cyber-tech do futuro: suit cinza militar + braço biônico (chest
   * stripe metálico), eyes glow ciano (visão de padrões), cowl curta. */
  {
    id: 'soldier', codename: 'CABLE', name: 'Soldier',
    role: 'L4 — Derivatives Intel Analyst', powerLabel: 'Pattern Recon',
    cfg: {
      suit: '#3f3f46', pants: '#1c1917', boot: '#0c0a09', bootCuff: '#71717a',
      belt: '#a8a29e', beltBuckle: '#404040',
      skin: '#d4a574', hair: 'short', hairColor: '#e7e5e4',
      iris: '#22d3ee', emblem: '#a8a29e',
      chestStripe: '#71717a',
      power: powerSynth,
    },
  },
];

/* Build all sprite functions and registry */
const ALL_V3 = CONFIGS.map((c) => ({
  id: c.id,
  codename: c.codename,
  name: c.name,
  role: c.role,
  powerLabel: c.powerLabel,
  palette: [
    c.cfg.suit, c.cfg.pants || c.cfg.suit, c.cfg.belt || c.cfg.bootCuff || c.cfg.emblem || '#888',
    c.cfg.hairColor || c.cfg.helmetColor || c.cfg.mask || '#222', LINE,
  ],
  draw: buildSprite(c.cfg),
}));

/* Merge with the 3 hand-drawn v3 sprites that live in sprites-v3.js */
const HAND_DRAWN = (window.SPRITES_V3 && window.SPRITES_V3.list) || [];

window.SPRITES_V3 = {
  size: SIZE,
  list: HAND_DRAWN.concat(ALL_V3),
  hand: HAND_DRAWN,
  factory: ALL_V3,
};

})();
