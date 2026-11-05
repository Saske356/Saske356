'use strict';
/* ---------------- скины: оружие и бойцы [скины] ----------------
   Всё процедурно: бесшовные canvas-текстуры (цвет + свойства: R — шероховатость, G — металличность, B — свечение)
   и трипланарная проекция по координатам объекта через onBeforeCompile — UV у моделей не нужны.
   Глобальные имена для других модулей:
     SKIN_RARITY, SKIN_WEAR, GUN_SKINS, CHAR_SKINS
     gunMaterial(weaponKey, partKind) — материал части оружия с учётом скина игрока (null → используй свой)
     applyGunSkins()                  — перекрашивает уже созданные модели (вьюмодель и оружие ботов)
     skinMaterial(id, wear, legacy, weaponKey), skinThumb(canvas, item), wearName(w)
*/

const SKIN_RARITY = {
  common:    { name: 'Обычный',     color: '#a3aeb0', w: 52 },
  uncommon:  { name: 'Необычный',   color: '#6fc27a', w: 27 },
  rare:      { name: 'Редкий',      color: '#4aa3ff', w: 14 },
  epic:      { name: 'Эпический',   color: '#c26bff', w: 5.5 },
  legendary: { name: 'Легендарный', color: '#ffb23f', w: 1.5 },
};
const SKIN_RARITY_ORDER = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
// качество: чем больше износ, тем больше потёртостей до голого металла
const SKIN_WEAR = [
  { max: 0.08, name: 'С конвейера', short: 'СК' },
  { max: 0.2,  name: 'Почти новое', short: 'ПН' },
  { max: 0.4,  name: 'После учений', short: 'ПУ' },
  { max: 0.6,  name: 'Бывалое', short: 'БВ' },
  { max: 1.01, name: 'Прошло огонь', short: 'ПО' },
];
function wearName(w) { for (const q of SKIN_WEAR) if (w < q.max) return q.name; return SKIN_WEAR[SKIN_WEAR.length - 1].name; }

/* ---- скины оружия ----
   pat — генератор узора, cols — цвета, rough/metal — отделка, only:'metal' — дерево и пластик не трогаем,
   glow — сила свечения (маска в канале B), anim — бегущая пульсация свечения, scale — повторов узора на метр */
const GUN_SKINS = {
  forest:   { name: 'Лесной покров', rarity: 'common', pat: 'camo', cols: ['#4a5a36', '#2f3b25', '#5e4a32', '#1b1f17'], freq: 3, rough: 0.78, metal: 0.04 },
  desert:   { name: 'Барханы', rarity: 'common', pat: 'camo', cols: ['#b9a074', '#9c8058', '#d1bb8e', '#7a6446'], freq: 2, rough: 0.8, metal: 0.04 },
  urban:    { name: 'Бетон', rarity: 'common', pat: 'camo', cols: ['#7d8285', '#5a5f63', '#a3a8aa', '#34383b'], freq: 3, rough: 0.74, metal: 0.05 },
  blued:    { name: 'Воронение', rarity: 'common', pat: 'solid', cols: ['#1d2633', '#2c3a4d'], rough: 0.3, metal: 0.85, only: 'metal', env: 0.9, brushed: true },
  olive:    { name: 'Полевая олива', rarity: 'common', pat: 'solid', cols: ['#56603d', '#4b5434'], rough: 0.8, metal: 0.05 },
  digital:  { name: 'Пиксель-тайга', rarity: 'uncommon', pat: 'digital', cols: ['#56664a', '#36442f', '#7a7f58', '#1f2a1f'], freq: 3, rough: 0.75, metal: 0.05 },
  digisnow: { name: 'Пиксель-наст', rarity: 'uncommon', pat: 'digital', cols: ['#d9dee2', '#9eabb5', '#6f7d8a', '#3c4652'], freq: 3, rough: 0.72, metal: 0.05 },
  tiger:    { name: 'Камышовый тигр', rarity: 'uncommon', pat: 'tiger', cols: ['#6f6a3e', '#4f5a33', '#1a1c14'], rough: 0.76, metal: 0.04 },
  carmine:  { name: 'Анод: Кармин', rarity: 'uncommon', pat: 'solid', cols: ['#a3121c', '#c4283a'], rough: 0.3, metal: 0.78, only: 'metal', env: 0.9, brushed: true },
  lagoon:   { name: 'Анод: Лагуна', rarity: 'uncommon', pat: 'solid', cols: ['#0d7480', '#18a0a8'], rough: 0.3, metal: 0.78, only: 'metal', env: 0.9, brushed: true },
  facets:   { name: 'Грани', rarity: 'uncommon', pat: 'geo', cols: ['#1d2b3a', '#2f4858', '#33658a', '#e8eeec', '#f2cb4c'], rough: 0.6, metal: 0.15 },
  carbon:   { name: 'Углепласт', rarity: 'rare', pat: 'carbon', cols: ['#121416', '#3d424a'], rough: 0.28, metal: 0.3, env: 0.8 },
  ninth:    { name: 'Девятый вал', rarity: 'rare', pat: 'waves', cols: ['#0b2340', '#134170', '#1f6aa5', '#e9f4ff'], rough: 0.45, metal: 0.2 },
  garages:  { name: 'Гаражный блок', rarity: 'rare', pat: 'graffiti', cols: ['#66696a', '#ff3d7f', '#2de2e6', '#f2cb4c', '#7cff4f', '#8f5bff'], rough: 0.62, metal: 0.05 },
  mirror:   { name: 'Зеркало', rarity: 'rare', pat: 'solid', cols: ['#e8ebee', '#cfd5da'], rough: 0.07, metal: 1, only: 'metal', env: 1.25 },
  signal:   { name: 'Сигнальная лента', rarity: 'rare', pat: 'hazard', cols: ['#f2cb4c', '#1a1f21'], rough: 0.55, metal: 0.1 },
  isolines: { name: 'Изолинии', rarity: 'rare', pat: 'topo', cols: ['#26362f', '#c9d6b8', '#f2cb4c'], rough: 0.7, metal: 0.05 },
  bulat:    { name: 'Булатная волна', rarity: 'epic', pat: 'damascus', cols: ['#24272c', '#a2a9b0'], rough: 0.3, metal: 0.92, only: 'metal', env: 1 },
  owl:      { name: 'Полночный филин', rarity: 'epic', pat: 'emblem', cols: ['#141a2e', '#232c4a', '#f2a33a', '#e8eeec'], rough: 0.5, metal: 0.2, glow: 0.9 },
  magma:    { name: 'Магма', rarity: 'epic', pat: 'magma', cols: ['#1b1512', '#ff6a12', '#ffd25a'], rough: 0.85, metal: 0.05, glow: 1.6, anim: 0.5 },
  circuit:  { name: 'Схема', rarity: 'epic', pat: 'circuit', cols: ['#0f2a1e', '#c8a24a', '#3cff9a'], rough: 0.5, metal: 0.3, glow: 1.4, anim: 0.8 },
  aurora:   { name: 'Сияние', rarity: 'epic', pat: 'aurora', cols: ['#4b1f7a', '#14a3a0', '#1c2d6b', '#d063ff'], rough: 0.25, metal: 0.82, env: 1, only: 'metal' },
  vyaz:     { name: 'Червонная вязь', rarity: 'legendary', pat: 'gold', cols: ['#d9a640', '#f5d27a', '#6b4512'], rough: 0.22, metal: 1, env: 1.3, only: 'metal' },
  prospekt: { name: 'Неоновый проспект', rarity: 'legendary', pat: 'neon', cols: ['#0b0c10', '#ff2bd6', '#22e6ff'], rough: 0.25, metal: 0.4, glow: 2.2, anim: 1, env: 0.7 },
  ballmol:  { name: 'Шаровая молния', rarity: 'legendary', pat: 'storm', cols: ['#10141c', '#8fd8ff', '#ffffff'], rough: 0.4, metal: 0.35, glow: 2.4, anim: 1 },
  zharptica: { name: 'Жар-птица', rarity: 'legendary', pat: 'phoenix', cols: ['#5e0808', '#d8340f', '#ffcc4d'], rough: 0.35, metal: 0.55, glow: 1.3, anim: 1, env: 0.9 },
};

/* ---- скины бойцов ----
   палитра — частичная поверх STYLE[team]; headgear и extras — для characters.js (makeBody(team, skinId)) */
const CHAR_SKINS = {
  a_frost:   { team: 'A', name: 'Иней', rarity: 'common', palette: { uni: 0x8a99a3, uni2: 0x76858f, vest: 0x5d6a72, pouch: 0x6b7880, helm: 0xa9b6bd, pad: 0x55626a }, headgear: 'helmet' },
  a_patrol:  { team: 'A', name: 'Ночной патруль', rarity: 'common', palette: { uni: 0x263241, uni2: 0x1f2a37, vest: 0x1a222c, pouch: 0x222c38, helm: 0x1d2631, glove: 0x15181c, boot: 0x15171a }, headgear: 'cap' },
  a_ranger:  { team: 'A', name: 'Егерь', rarity: 'uncommon', palette: { uni: 0x4b5a3c, uni2: 0x3f4c33, vest: 0x39432f, pouch: 0x46523a, helm: 0x4b5a3c, pad: 0x39432f }, headgear: 'boonie', extras: ['backpack'] },
  a_block:   { team: 'A', name: 'Квартал', rarity: 'uncommon', palette: { uni: 0x5d6266, uni2: 0x4d5256, vest: 0x2e3236, pouch: 0x3c4145, helm: 0x45494d, pad: 0x26292c }, headgear: 'helmet', extras: ['kneepads'] },
  a_recon:   { team: 'A', name: 'Разведчик', rarity: 'rare', palette: { uni: 0x56603f, uni2: 0x4a5336, vest: 0x3a3f2c, pouch: 0x4f5838, helm: 0x3a3f2c, face: 0x1e2120 }, headgear: 'balaclava', extras: ['radio'] },
  a_polar:   { team: 'A', name: 'Полярник', rarity: 'rare', palette: { uni: 0xd5dde0, uni2: 0xbfc8cc, vest: 0x9aa6ac, pouch: 0xaab5ba, helm: 0xe4eaec, glove: 0x8d979c, boot: 0x6d767a, pad: 0xaab5ba, face: 0xc9d1d4 }, headgear: 'balaclava', extras: ['backpack'] },
  a_legion:  { team: 'A', name: 'Стальной легион', rarity: 'epic', palette: { uni: 0x2f4a5e, uni2: 0x253d4f, vest: 0x1b2a35, pouch: 0x22313c, helm: 0x5a7d93, acc: 0x7fe3ff, lens: 0x58d6ff, pad: 0x3a5568 }, headgear: 'helmet', extras: ['radio', 'backpack', 'patch'] },
  a_ghost:   { team: 'A', name: 'Призрак', rarity: 'legendary', palette: { uni: 0x15181c, uni2: 0x101317, vest: 0x0d0f12, pouch: 0x16191d, helm: 0x1a1e23, acc: 0x00e5ff, lens: 0x00e5ff, glove: 0x0b0c0e, boot: 0x0b0c0e, face: 0x101215, pad: 0x16191d }, headgear: 'balaclava', extras: ['radio', 'patch'] },
  b_sirocco: { team: 'B', name: 'Суховей', rarity: 'common', palette: { uni: 0x9a8662, uni2: 0x887453, vest: 0x6e5c40, pouch: 0x7d6a4c, helm: 0x8c7855 }, headgear: 'boonie' },
  b_brick:   { team: 'B', name: 'Кирпич', rarity: 'common', palette: { uni: 0x7c4a36, uni2: 0x6a3e2d, vest: 0x4f3022, pouch: 0x5e3a2a, helm: 0x6e4330, pad: 0x4f3022 }, headgear: 'cap' },
  b_mangrove: { team: 'B', name: 'Мангры', rarity: 'uncommon', palette: { uni: 0x4f5530, uni2: 0x434828, vest: 0x3b3a26, pouch: 0x52502f, helm: 0x5d5a34 }, headgear: 'boonie', extras: ['backpack'] },
  b_mech:    { team: 'B', name: 'Механик', rarity: 'uncommon', palette: { uni: 0x4a4f55, uni2: 0x3e4349, vest: 0x5b3a22, pouch: 0x6a4a2c, helm: 0x3e4349, glove: 0x6a2f12, pad: 0x2a2d31 }, headgear: 'cap', extras: ['kneepads'] },
  b_dune:    { team: 'B', name: 'Дюна', rarity: 'rare', palette: { uni: 0xc2a878, uni2: 0xb0966a, vest: 0x8e774f, pouch: 0x9f8659, helm: 0xb0966a, face: 0xa48d66 }, headgear: 'balaclava', extras: ['backpack'] },
  b_scrap:   { team: 'B', name: 'Старьёвщик', rarity: 'rare', palette: { uni: 0x5a4b3b, uni2: 0x4b3f32, vest: 0x6b3f26, pouch: 0x7a5a32, helm: 0x8a5a2a, pad: 0x6b3f26 }, headgear: 'helmet', extras: ['radio', 'kneepads'] },
  b_scale:   { team: 'B', name: 'Окалина', rarity: 'epic', palette: { uni: 0x3b2a22, uni2: 0x31231c, vest: 0x5e2f1c, pouch: 0x6e3a22, helm: 0x8a3b1c, acc: 0xff8a3d, lens: 0xffa040, pad: 0x5e2f1c }, headgear: 'helmet', extras: ['radio', 'backpack', 'patch'] },
  b_ember:   { team: 'B', name: 'Уголь', rarity: 'legendary', palette: { uni: 0x1a1614, uni2: 0x14110f, vest: 0x0f0d0c, pouch: 0x1c1714, helm: 0x221b17, acc: 0xff5a1a, lens: 0xff7a2a, glove: 0x0e0c0b, boot: 0x0e0c0b, face: 0x16120f, pad: 0x1c1714 }, headgear: 'balaclava', extras: ['patch'] },
};
const CHAR_PAL_KEYS = ['uni', 'uni2', 'vest', 'pouch', 'helm', 'acc', 'face', 'glove', 'boot', 'pad', 'lens'];

/* ---------------- процедурные текстуры ---------------- */
const SK_TEX = 256;
function skRng(seed) {
  let a = seed >>> 0;
  return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function skHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
// бесшовный value-noise: u,v ∈ [0,1), период решётки N
function skNoise(seed, N) {
  const r = skRng(seed), g = new Float32Array(N * N);
  for (let i = 0; i < g.length; i++) g[i] = r();
  return (u, v) => {
    const x = u * N, y = v * N, xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const x0 = ((xi % N) + N) % N, x1 = (x0 + 1) % N, y0 = ((yi % N) + N) % N, y1 = (y0 + 1) % N;
    const a = g[y0 * N + x0], b = g[y0 * N + x1], c = g[y1 * N + x0], d = g[y1 * N + x1];
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
  };
}
function skFbm(seed, base, oct) {
  const ns = []; for (let i = 0; i < oct; i++) ns.push(skNoise(seed + i * 977, base << i));
  return (u, v) => { let s = 0, a = 0.5, t = 0; for (const n of ns) { s += n(u, v) * a; t += a; a *= 0.5; } return s / t; };
}
// тайлящийся Ворлей: возвращает [F1, F2] в долях клетки
function skWorley(seed, N) {
  const r = skRng(seed), pts = new Float32Array(N * N * 2);
  for (let i = 0; i < N * N; i++) { pts[i * 2] = r(); pts[i * 2 + 1] = r(); }
  return (u, v) => {
    const x = u * N, y = v * N, xi = Math.floor(x), yi = Math.floor(y);
    let f1 = 9, f2 = 9;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const cx = xi + dx, cy = yi + dy, wx = ((cx % N) + N) % N, wy = ((cy % N) + N) % N, k = (wy * N + wx) * 2;
      const d = Math.hypot(cx + pts[k] - x, cy + pts[k + 1] - y);
      if (d < f1) { f2 = f1; f1 = d; } else if (d < f2) f2 = d;
    }
    return [f1, f2];
  };
}
const skHex = h => { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
const skMix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const skSmooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
function skCanvas(S) { const c = document.createElement('canvas'); c.width = c.height = S; return c; }
// попиксельная заливка: fn(u, v, out) пишет в out [r,g,b, rough, metal, glow] (0..255 / 0..1)
function skPixels(A, P, S, fn) {
  const ia = A.createImageData(S, S), ip = P.createImageData(S, S), da = ia.data, dp = ip.data, o = [0, 0, 0, 0, 0, 0];
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
    fn(x / S, y / S, o);
    const i = (y * S + x) * 4;
    da[i] = o[0]; da[i + 1] = o[1]; da[i + 2] = o[2]; da[i + 3] = 255;
    dp[i] = o[3] * 255; dp[i + 1] = o[4] * 255; dp[i + 2] = o[5] * 255; dp[i + 3] = 255;
  }
  A.putImageData(ia, 0, 0); P.putImageData(ip, 0, 0);
}
// рисование с заворотом краёв: фигура видна на всех 9 копиях — текстура бесшовная
function skWrap(S, fn) { for (const dy of [-S, 0, S]) for (const dx of [-S, 0, S]) fn(dx, dy); }
const skProp = (r, m, g) => `rgb(${Math.round(r * 255)},${Math.round(m * 255)},${Math.round((g || 0) * 255)})`;
function skFill(ctx, S, style) { ctx.fillStyle = style; ctx.fillRect(0, 0, S, S); }
// лёгкое зерно поверх нарисованного
function skGrain(A, S, amt, r) {
  const im = A.getImageData(0, 0, S, S), d = im.data;
  for (let i = 0; i < d.length; i += 4) { const n = (r() - 0.5) * amt; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
  A.putImageData(im, 0, 0);
}

const SK_PAT = {
  camo(d, r, A, P, S) {
    const c = d.cols.map(skHex), f = d.freq || 3, seed = r() * 1e9 | 0;
    const n1 = skFbm(seed, f, 4), n2 = skFbm(seed + 11, f, 4), n3 = skFbm(seed + 23, f + 1, 4), gn = skNoise(seed + 5, 64);
    skPixels(A, P, S, (u, v, o) => {
      let col = c[0];
      if (n1(u, v) > 0.52) col = c[1];
      if (n2(u, v) > 0.56) col = c[2];
      if (n3(u, v) > 0.6) col = c[3];
      const g = (gn(u, v) - 0.5) * 14;
      o[0] = col[0] + g; o[1] = col[1] + g; o[2] = col[2] + g; o[3] = d.rough + (gn(u, v) - 0.5) * 0.1; o[4] = d.metal; o[5] = 0;
    });
  },
  digital(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, f = d.freq || 3;
    const n1 = skFbm(seed, f, 3), n2 = skFbm(seed + 7, f, 3), n3 = skFbm(seed + 13, f + 1, 3), q = 32, jit = skNoise(seed + 3, q);
    skPixels(A, P, S, (u, v, o) => {
      // две сетки пикселей: крупная и мелкая, порог с дрожанием по клетке
      const qu = (Math.floor(u * q) + 0.5) / q, qv = (Math.floor(v * q) + 0.5) / q, j = (jit(qu, qv) - 0.5) * 0.1;
      let col = c[0];
      if (n1(qu, qv) + j > 0.52) col = c[1];
      if (n2(qu, qv) - j > 0.55) col = c[2];
      if (n3(qu, qv) + j * 0.5 > 0.6) col = c[3];
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0;
    });
  },
  tiger(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, w = skFbm(seed, 3, 4), w2 = skFbm(seed + 9, 4, 3), b = skFbm(seed + 2, 2, 3);
    skPixels(A, P, S, (u, v, o) => {
      const s = Math.sin((u * 7 + w(u, v) * 1.6 + v * 0.6) * Math.PI * 2);
      const stripe = s > 0.35 + (w2(u, v) - 0.5) * 1.4;
      let col = skMix(c[0], c[1], skSmooth(0.4, 0.6, b(u, v)));
      if (stripe) col = c[2];
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0;
    });
  },
  solid(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, n = skFbm(seed, 4, 4), row = skNoise(seed + 1, 128);
    skPixels(A, P, S, (u, v, o) => {
      // шлифовка: тонкие продольные риски вдоль ствола
      const br = d.brushed ? (row(u * 0.02, v) - 0.5) * 0.35 : 0;
      const t = clamp(n(u, v) * 1.2 - 0.1 + br, 0, 1), col = skMix(c[0], c[1], t);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough + br * 0.2; o[4] = d.metal; o[5] = 0;
    });
  },
  aurora(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, n = skFbm(seed, 2, 4), m = skFbm(seed + 4, 3, 3);
    skPixels(A, P, S, (u, v, o) => {
      const t = n(u, v), k = m(u, v);
      let col = skMix(c[2], c[0], skSmooth(0.35, 0.5, t));
      col = skMix(col, c[1], skSmooth(0.5, 0.68, t));
      col = skMix(col, c[3], skSmooth(0.62, 0.75, k) * 0.6);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0;
    });
  },
  geo(d, r, A, P, S) {
    const n = 8, cs = S / n, pal = d.cols;
    skFill(P, S, skProp(d.rough, d.metal));
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) for (let t = 0; t < 2; t++) {
      const k = r(), col = k < 0.35 ? pal[0] : k < 0.62 ? pal[1] : k < 0.84 ? pal[2] : k < 0.95 ? pal[3] : pal[4];
      const x = i * cs, y = j * cs, flip = (i + j) % 2;
      A.beginPath();
      if (!flip) { if (t) { A.moveTo(x, y); A.lineTo(x + cs, y); A.lineTo(x, y + cs); } else { A.moveTo(x + cs, y); A.lineTo(x + cs, y + cs); A.lineTo(x, y + cs); } }
      else { if (t) { A.moveTo(x, y); A.lineTo(x + cs, y); A.lineTo(x + cs, y + cs); } else { A.moveTo(x, y); A.lineTo(x + cs, y + cs); A.lineTo(x, y + cs); } }
      A.closePath(); A.fillStyle = col; A.fill();
      A.strokeStyle = 'rgba(10,14,18,.55)'; A.lineWidth = 1.5; A.stroke();
    }
    skGrain(A, S, 10, r);
  },
  carbon(d, r, A, P, S) {
    const c = d.cols.map(skHex), cs = 8;
    skPixels(A, P, S, (u, v, o) => {
      const x = u * S, y = v * S, i = Math.floor(x / cs), j = Math.floor(y / cs);
      const horiz = ((i - j) % 4 + 4) % 4 < 2;
      const f = horiz ? (y % cs) / cs : (x % cs) / cs;
      const along = horiz ? (x % (cs * 2)) / (cs * 2) : (y % (cs * 2)) / (cs * 2);
      const t = Math.sin(f * Math.PI) * (0.55 + 0.45 * Math.sin(along * Math.PI)) * (horiz ? 1 : 0.7);
      const col = skMix(c[0], c[1], t);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough + (1 - t) * 0.15; o[4] = d.metal; o[5] = 0;
    });
  },
  waves(d, r, A, P, S) {
    const c = d.cols.map(skHex), B = 6, m = 2, seed = r() * 1e9 | 0, w = skFbm(seed, 4, 3);
    skPixels(A, P, S, (u, v, o) => {
      const vv = v * B, k = Math.floor(vv), y = vv - k;
      const wl = 0.5 + 0.28 * Math.sin((u * m + k * 0.37) * Math.PI * 2) + (w(u, v) - 0.5) * 0.25;
      let col = y < wl ? c[k % 3] : c[(k + 1) % 3];
      const dd = Math.abs(y - wl);
      if (dd < 0.05) col = c[3];
      else if (y < wl && Math.abs(y - (wl - 0.17)) < 0.018) col = skMix(col, c[3], 0.55);
      else if (y < wl && Math.abs(y - (wl - 0.3)) < 0.012) col = skMix(col, c[3], 0.3);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0;
    });
  },
  graffiti(d, r, A, P, S) {
    const seed = r() * 1e9 | 0, n = skFbm(seed, 4, 4), base = skHex(d.cols[0]);
    skPixels(A, P, S, (u, v, o) => { const g = (n(u, v) - 0.5) * 60; o[0] = base[0] + g; o[1] = base[1] + g; o[2] = base[2] + g; o[3] = d.rough; o[4] = d.metal; o[5] = 0; });
    const vivid = d.cols.slice(1);
    for (let i = 0; i < 14; i++) {
      const x = r() * S, y = r() * S, rad = 18 + r() * 40, col = vivid[Math.floor(r() * vivid.length)];
      skWrap(S, (dx, dy) => {
        const gr = A.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, rad);
        gr.addColorStop(0, col); gr.addColorStop(0.55, col); gr.addColorStop(1, 'rgba(0,0,0,0)');
        A.fillStyle = gr; A.beginPath(); A.arc(x + dx, y + dy, rad, 0, Math.PI * 2); A.fill();
        // подтёки краски
        A.strokeStyle = col; A.lineWidth = 2;
        for (let k = 0; k < 3; k++) { const px = x + dx + (r() - 0.5) * rad; A.beginPath(); A.moveTo(px, y + dy + rad * 0.4); A.lineTo(px, y + dy + rad * 0.4 + 10 + r() * 30); A.stroke(); }
      });
    }
    const tags = ['БЛОК', 'ПОСТ', 'ХАОС', 'ГУЛ', 'ДЫМ', 'ЭХО'];
    for (let i = 0; i < 7; i++) {
      const x = r() * S, y = r() * S, rot = (r() - 0.5) * 0.6, size = 22 + r() * 18, t = tags[i % tags.length], col = vivid[(i * 2 + 1) % vivid.length];
      skWrap(S, (dx, dy) => {
        A.save(); A.translate(x + dx, y + dy); A.rotate(rot);
        A.font = `900 ${size}px "Russo One", "Arial Black", Impact, sans-serif`; A.textAlign = 'center'; A.textBaseline = 'middle';
        A.lineWidth = 5; A.strokeStyle = '#121416'; A.strokeText(t, 0, 0);
        A.fillStyle = col; A.fillText(t, 0, 0);
        A.lineWidth = 1.2; A.strokeStyle = 'rgba(255,255,255,.7)'; A.strokeText(t, -1, -1);
        A.restore();
      });
    }
    skFill(P, S, skProp(d.rough, d.metal));
  },
  hazard(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, n = skFbm(seed, 8, 3), per = 32;
    skPixels(A, P, S, (u, v, o) => {
      const x = u * S, y = v * S, s = ((x + y) % per) < per / 2;
      const g = (n(u, v) - 0.5) * 30, col = s ? c[0] : c[1];
      o[0] = col[0] + g; o[1] = col[1] + g; o[2] = col[2] + g; o[3] = d.rough + (s ? 0 : 0.1); o[4] = d.metal; o[5] = 0;
    });
  },
  topo(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, n = skFbm(seed, 2, 5), bg = skFbm(seed + 3, 3, 3);
    skPixels(A, P, S, (u, v, o) => {
      const h = n(u, v) * 16, f = h - Math.floor(h), idx = Math.floor(h) % 5 === 0;
      const line = f < (idx ? 0.12 : 0.06);
      let col = skMix(c[0], [c[0][0] * 1.3, c[0][1] * 1.3, c[0][2] * 1.3], bg(u, v));
      if (line) col = idx ? c[2] : c[1];
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0;
    });
  },
  damascus(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, w1 = skFbm(seed, 3, 4), w2 = skFbm(seed + 5, 2, 3);
    skPixels(A, P, S, (u, v, o) => {
      const t = v * 14 + w1(u, v) * 5 + 0.7 * Math.sin((u * 3 + w2(u, v) * 1.5) * Math.PI * 2);
      const g = Math.pow(0.5 + 0.5 * Math.sin(t * Math.PI * 2), 2.2);
      const col = skMix(c[0], c[1], g);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough + (1 - g) * 0.2; o[4] = d.metal - (1 - g) * 0.15; o[5] = 0;
    });
  },
  emblem(d, r, A, P, S) {
    // свой знак: голова филина с горящими глазами, тайлится сеткой со сдвигом рядов
    const seed = r() * 1e9 | 0, n = skFbm(seed, 4, 3), base = skHex(d.cols[0]);
    skPixels(A, P, S, (u, v, o) => { const g = (n(u, v) - 0.5) * 22; o[0] = base[0] + g; o[1] = base[1] + g; o[2] = base[2] + g; o[3] = d.rough; o[4] = d.metal; o[5] = 0; });
    const cell = S / 4;
    const owl = (ctx, x, y, s, prop) => {
      ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
      ctx.fillStyle = prop ? skProp(d.rough, d.metal) : d.cols[1];
      ctx.beginPath(); ctx.moveTo(-26, -18); ctx.lineTo(-14, -30); ctx.lineTo(-8, -18); ctx.lineTo(8, -18); ctx.lineTo(14, -30); ctx.lineTo(26, -18);
      ctx.quadraticCurveTo(34, 10, 0, 30); ctx.quadraticCurveTo(-34, 10, -26, -18); ctx.fill();
      ctx.strokeStyle = prop ? skProp(0.4, 0.6) : d.cols[3]; ctx.lineWidth = 1.6; ctx.stroke();
      for (const sx of [-1, 1]) {
        ctx.fillStyle = prop ? skProp(0.3, 0.2, 1) : d.cols[2];
        ctx.beginPath(); ctx.arc(sx * 11, -4, 8.5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = prop ? skProp(0.3, 0.2, 0) : '#0c0d10';
        ctx.beginPath(); ctx.arc(sx * 11, -4, 3.6, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = prop ? skProp(0.5, 0.3) : d.cols[3];
      ctx.beginPath(); ctx.moveTo(-4, 6); ctx.lineTo(4, 6); ctx.lineTo(0, 14); ctx.closePath(); ctx.fill();
      ctx.restore();
    };
    skFill(P, S, skProp(d.rough, d.metal));
    for (let j = 0; j < 4; j++) for (let i = 0; i < 4; i++) {
      const x = (i + 0.5 + (j % 2) * 0.5) * cell, y = (j + 0.5) * cell;
      skWrap(S, (dx, dy) => { owl(A, x + dx, y + dy, 0.82, false); owl(P, x + dx, y + dy, 0.82, true); });
    }
  },
  magma(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, wl = skWorley(seed, 6), n = skFbm(seed + 3, 4, 4);
    skPixels(A, P, S, (u, v, o) => {
      const [f1, f2] = wl(u, v), e = f2 - f1, nn = n(u, v);
      const crack = 1 - skSmooth(0.02, 0.09 + nn * 0.05, e);
      const rock = skMix(c[0], [c[0][0] * 1.8, c[0][1] * 1.6, c[0][2] * 1.5], nn);
      const hot = skMix(c[1], c[2], skSmooth(0.5, 1, crack));
      const col = skMix(rock, hot, crack);
      o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough - crack * 0.3; o[4] = d.metal; o[5] = crack;
    });
  },
  circuit(d, r, A, P, S) {
    const seed = r() * 1e9 | 0, n = skFbm(seed, 6, 3), base = skHex(d.cols[0]);
    skPixels(A, P, S, (u, v, o) => { const g = (n(u, v) - 0.5) * 18; o[0] = base[0] + g; o[1] = base[1] + g * 1.4; o[2] = base[2] + g; o[3] = d.rough; o[4] = d.metal; o[5] = 0; });
    const G = 16, step = S / G;
    A.lineCap = P.lineCap = 'round'; A.lineJoin = P.lineJoin = 'round';
    for (let k = 0; k < 26; k++) {
      let x = Math.floor(r() * G), y = Math.floor(r() * G);
      const pts = [[x, y]], len = 3 + Math.floor(r() * 7);
      let dir = Math.floor(r() * 4);
      for (let s = 0; s < len; s++) {
        if (r() < 0.35) dir = (dir + (r() < 0.5 ? 1 : 3)) % 4;
        x += [1, 0, -1, 0][dir]; y += [0, 1, 0, -1][dir]; pts.push([x, y]);
      }
      const lit = r() < 0.3;
      skWrap(S, (dx, dy) => {
        for (const [ctx, isP] of [[A, false], [P, true]]) {
          ctx.beginPath(); pts.forEach(([px, py], i) => { const X = px * step + dx, Y = py * step + dy; i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); });
          ctx.strokeStyle = isP ? skProp(0.35, 0.9, lit ? 1 : 0) : (lit ? d.cols[2] : d.cols[1]); ctx.lineWidth = lit ? 3 : 2.4; ctx.stroke();
          for (const [px, py] of [pts[0], pts[pts.length - 1]]) {
            ctx.fillStyle = isP ? skProp(0.3, 0.95, lit ? 1 : 0) : (lit ? d.cols[2] : d.cols[1]);
            ctx.beginPath(); ctx.arc(px * step + dx, py * step + dy, 4.2, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = isP ? skProp(0.6, 0.1, 0) : '#06140d';
            ctx.beginPath(); ctx.arc(px * step + dx, py * step + dy, 1.6, 0, Math.PI * 2); ctx.fill();
          }
        }
      });
    }
  },
  gold(d, r, A, P, S) {
    const c = d.cols.map(skHex), seed = r() * 1e9 | 0, n = skFbm(seed, 6, 4);
    skPixels(A, P, S, (u, v, o) => { const t = n(u, v), col = skMix(c[0], c[1], skSmooth(0.3, 0.75, t)); o[0] = col[0]; o[1] = col[1]; o[2] = col[2]; o[3] = d.rough; o[4] = d.metal; o[5] = 0; });
    // гравировка: завитки-спирали с листками
    const scroll = (ctx, x, y, s, rot, dir, prop) => {
      ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
      ctx.strokeStyle = prop ? skProp(0.6, 0.75) : d.cols[2]; ctx.lineWidth = 2.2; ctx.lineCap = 'round';
      ctx.beginPath();
      for (let a = 0; a < Math.PI * 4.2; a += 0.12) { const rr = s * Math.exp(-a * 0.22), X = Math.cos(a * dir) * rr, Y = Math.sin(a * dir) * rr; a ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }
      ctx.stroke();
      for (let k = 0; k < 4; k++) {
        const a = 0.6 + k * 1.3, rr = s * Math.exp(-a * 0.22), X = Math.cos(a * dir) * rr, Y = Math.sin(a * dir) * rr;
        ctx.save(); ctx.translate(X, Y); ctx.rotate(a * dir + 0.8);
        ctx.beginPath(); ctx.ellipse(0, -s * 0.16, s * 0.07, s * 0.17, 0, 0, Math.PI * 2);
        ctx.fillStyle = prop ? skProp(0.55, 0.8) : d.cols[2]; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
        ctx.restore();
      }
      ctx.restore();
    };
    for (let i = 0; i < 9; i++) {
      const x = r() * S, y = r() * S, s = 26 + r() * 18, rot = r() * 6.28, dir = r() < 0.5 ? 1 : -1;
      skWrap(S, (dx, dy) => { scroll(A, x + dx, y + dy, s, rot, dir, false); scroll(P, x + dx, y + dy, s, rot, dir, true); });
    }
  },
  neon(d, r, A, P, S) {
    skFill(A, S, d.cols[0]); skFill(P, S, skProp(d.rough, d.metal));
    A.lineCap = P.lineCap = 'round'; A.lineJoin = P.lineJoin = 'round';
    // ломаные линии под 0/45/90° — как вывески ночного города
    for (let k = 0; k < 11; k++) {
      let x = r() * S, y = r() * S; const pts = [[x, y]];
      for (let s = 0; s < 4; s++) { const a = Math.floor(r() * 8) * Math.PI / 4, l = 20 + r() * 50; x += Math.cos(a) * l; y += Math.sin(a) * l; pts.push([x, y]); }
      const col = k % 2 ? d.cols[1] : d.cols[2];
      skWrap(S, (dx, dy) => {
        const path = ctx => { ctx.beginPath(); pts.forEach(([px, py], i) => i ? ctx.lineTo(px + dx, py + dy) : ctx.moveTo(px + dx, py + dy)); };
        A.save(); A.shadowColor = col; A.shadowBlur = 10; path(A); A.strokeStyle = col; A.lineWidth = 3.4; A.stroke(); A.restore();
        path(A); A.strokeStyle = 'rgba(255,255,255,.75)'; A.lineWidth = 1; A.stroke();
        path(P); P.strokeStyle = skProp(0.2, 0.1, 1); P.lineWidth = 4; P.stroke();
      });
    }
    for (let k = 0; k < 30; k++) { const x = r() * S, y = r() * S; A.fillStyle = 'rgba(255,255,255,.08)'; A.fillRect(x, y, 2, 2); }
  },
  storm(d, r, A, P, S) {
    const seed = r() * 1e9 | 0, n = skFbm(seed, 3, 5), base = skHex(d.cols[0]);
    skPixels(A, P, S, (u, v, o) => { const t = n(u, v), g = t * 36; o[0] = base[0] + g * 0.6; o[1] = base[1] + g * 0.8; o[2] = base[2] + g * 1.2; o[3] = d.rough; o[4] = d.metal; o[5] = 0; });
    A.lineCap = P.lineCap = 'round'; A.lineJoin = P.lineJoin = 'round';
    const bolt = (x, y, a, len, w, depth) => {
      const pts = [[x, y]];
      for (let s = 0; s < 8; s++) { a += (r() - 0.5) * 1.1; x += Math.cos(a) * len / 8; y += Math.sin(a) * len / 8; pts.push([x, y]); if (depth < 2 && r() < 0.25) bolt(x, y, a + (r() - 0.5) * 1.6, len * 0.5, w * 0.6, depth + 1); }
      skWrap(S, (dx, dy) => {
        const path = ctx => { ctx.beginPath(); pts.forEach(([px, py], i) => i ? ctx.lineTo(px + dx, py + dy) : ctx.moveTo(px + dx, py + dy)); };
        A.save(); A.shadowColor = d.cols[1]; A.shadowBlur = 12; path(A); A.strokeStyle = d.cols[1]; A.lineWidth = w; A.stroke(); A.restore();
        path(A); A.strokeStyle = d.cols[2]; A.lineWidth = Math.max(0.8, w * 0.35); A.stroke();
        path(P); P.strokeStyle = skProp(0.2, 0.1, 1); P.lineWidth = w + 1; P.stroke();
      });
    };
    for (let k = 0; k < 5; k++) bolt(r() * S, r() * S, r() * 6.28, 120 + r() * 80, 3.2, 0);
  },
  phoenix(d, r, A, P, S) {
    // перья: ряды перекрывающихся чешуек от тёмно-красного к золоту, кромка светится
    const c = d.cols, cols = 8, rows = 8, w = S / cols, h = S / rows;
    skFill(A, S, c[0]); skFill(P, S, skProp(d.rough, d.metal));
    for (let j = rows; j >= -1; j--) for (let i = -1; i <= cols; i++) {
      const x = (i + (j % 2 ? 0.5 : 0)) * w, y = j * h;
      skWrap(S, (dx, dy) => {
        const X = x + dx, Y = y + dy;
        if (X < -w * 2 || X > S + w * 2 || Y < -h * 2 || Y > S + h * 2) return;
        const gr = A.createLinearGradient(X, Y - h * 0.2, X, Y + h * 1.1);
        gr.addColorStop(0, c[0]); gr.addColorStop(0.6, c[1]); gr.addColorStop(1, c[2]);
        A.beginPath(); A.moveTo(X - w * 0.55, Y); A.quadraticCurveTo(X - w * 0.55, Y + h * 1.2, X, Y + h * 1.25); A.quadraticCurveTo(X + w * 0.55, Y + h * 1.2, X + w * 0.55, Y); A.closePath();
        A.fillStyle = gr; A.fill();
        A.strokeStyle = 'rgba(255,220,120,.9)'; A.lineWidth = 1.4; A.stroke();
        A.beginPath(); A.moveTo(X, Y + h * 0.1); A.lineTo(X, Y + h * 1.1); A.strokeStyle = 'rgba(60,5,0,.5)'; A.lineWidth = 1; A.stroke();
        P.beginPath(); P.moveTo(X - w * 0.55, Y); P.quadraticCurveTo(X - w * 0.55, Y + h * 1.2, X, Y + h * 1.25); P.quadraticCurveTo(X + w * 0.55, Y + h * 1.2, X + w * 0.55, Y); P.closePath();
        P.fillStyle = skProp(d.rough, d.metal, 0.1); P.fill(); P.strokeStyle = skProp(0.25, 0.8, 0.9); P.lineWidth = 2; P.stroke();
      });
    }
  },
};

const _skTex = {};
// холсты скина (для превью в интерфейсе) — создаются лениво
function skinCanvases(id) {
  if (_skTex[id]) return _skTex[id];
  const d = GUN_SKINS[id], S = SK_TEX, a = skCanvas(S), p = skCanvas(S);
  const A = a.getContext('2d'), P = p.getContext('2d');
  try { (SK_PAT[d.pat] || SK_PAT.solid)(d, skRng(skHash(id)), A, P, S); } catch (e) { console.error(e); skFill(A, S, d.cols[0]); skFill(P, S, skProp(0.6, 0.2)); }
  return _skTex[id] = { a, p, alb: null, props: null };
}
function skTexture(c) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4;
  return t;
}
function skinTextures(id) {
  const s = skinCanvases(id);
  if (!s.alb) { s.alb = skTexture(s.a); s.props = skTexture(s.p); }
  return s;
}
// общая маска износа: равномерно распределённый fbm (ранговое выравнивание), 128px
let _skWearTex = null;
function skWearTexture() {
  if (_skWearTex) return _skWearTex;
  const S = 128, c = skCanvas(S), g = c.getContext('2d'), n = skFbm(4242, 4, 5), vals = new Float32Array(S * S);
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) vals[y * S + x] = n(x / S, y / S);
  const sorted = Array.from(vals).sort((a, b) => a - b), im = g.createImageData(S, S);
  const rank = v => { let lo = 0, hi = sorted.length - 1; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] < v) lo = m + 1; else hi = m; } return lo / sorted.length; };
  for (let i = 0; i < vals.length; i++) { const v = rank(vals[i]) * 255; im.data[i * 4] = im.data[i * 4 + 1] = im.data[i * 4 + 2] = v; im.data[i * 4 + 3] = 255; }
  g.putImageData(im, 0, 0);
  return _skWearTex = skTexture(c);
}
// маленькое окружение для металлов (без него хром и золото чёрные): небо, пол, пара софтбоксов
let _skEnv = null;
function skinEnv() {
  if (_skEnv) return _skEnv;
  const S = 32, faces = [];
  for (let f = 0; f < 6; f++) {
    const c = skCanvas(S), g = c.getContext('2d');
    if (f === 2) { g.fillStyle = '#e9eef0'; g.fillRect(0, 0, S, S); }            // +y небо
    else if (f === 3) { g.fillStyle = '#2a2520'; g.fillRect(0, 0, S, S); }       // -y пол
    else {
      const gr = g.createLinearGradient(0, 0, 0, S);
      gr.addColorStop(0, '#b9c6cc'); gr.addColorStop(0.5, '#7d8a8f'); gr.addColorStop(0.52, '#4a443c'); gr.addColorStop(1, '#2a2520');
      g.fillStyle = gr; g.fillRect(0, 0, S, S);
      if (f === 0 || f === 5) { g.fillStyle = '#ffffff'; g.fillRect(S * 0.3, S * 0.18, S * 0.4, S * 0.22); }
      if (f === 1) { g.fillStyle = '#ffe2b8'; g.fillRect(S * 0.15, S * 0.25, S * 0.25, S * 0.15); }
    }
    faces.push(c);
  }
  _skEnv = new THREE.CubeTexture(faces); _skEnv.needsUpdate = true;
  return _skEnv;
}

/* ---------------- материал скина: трипланар по координатам объекта ---------------- */
const SKIN_TIME = { value: 0 };
const SK_VERT_PARS = '#include <common>\nvarying vec3 vSkPos;\nvarying vec3 vSkNrm;';
const SK_VERT = '#include <begin_vertex>\nvSkPos = position;\nvSkNrm = normal;';
const SK_FRAG_PARS = `#include <common>
uniform sampler2D uSkAlb; uniform sampler2D uSkProps; uniform sampler2D uSkWear;
uniform float uSkScale; uniform float uSkWearAmt; uniform float uSkCovWood; uniform float uSkLegacy; uniform float uSkShadeMin;
uniform float uSkTime; uniform float uSkGlowAnim; uniform float uSkGlow;
varying vec3 vSkPos; varying vec3 vSkNrm;
vec4 skTri(sampler2D t, vec3 p, vec3 w) { return texture2D(t, p.zy) * w.x + texture2D(t, p.xz) * w.y + texture2D(t, p.xy) * w.z; }`;
// вместо color_fragment: узор × яркость цвета вершин; в режиме legacy (один меш на всё оружие)
// линзы и красные гильзы не трогаем, а «тёплые» цвета (дерево, песочный пластик) — по флагу uSkCovWood
const SK_FRAG_COLOR = `
vec3 skW = pow(abs(normalize(vSkNrm)), vec3(4.0)); skW /= (skW.x + skW.y + skW.z + 1e-5);
vec3 skP = vSkPos * uSkScale;
vec4 skA = skTri(uSkAlb, skP, skW);
vec4 skPr = skTri(uSkProps, skP, skW);
float skNz = skTri(uSkWear, skP * 0.73 + 0.31, skW).r;
vec3 skVc = vec3(1.0);
#ifdef USE_COLOR
  skVc = vColor;
#endif
float skLum = dot(skVc, vec3(0.3, 0.59, 0.11));
float skKeep = uSkLegacy * max(step(0.15, skVc.g - skVc.r), step(0.3, skVc.r - skVc.g));
float skWarm = uSkLegacy * smoothstep(0.1, 0.16, skVc.r - skVc.b);
float skCov = (1.0 - skKeep) * mix(1.0, uSkCovWood, skWarm);
float skShade = mix(uSkShadeMin, 1.0, smoothstep(0.1, 0.32, skLum));
float skWorn = (1.0 - smoothstep(uSkWearAmt * 0.6 - 0.03, uSkWearAmt * 0.6 + 0.03, skNz)) * step(0.01, uSkWearAmt);
vec3 skCol = skA.rgb * skShade * (1.0 - uSkWearAmt * 0.25 * (1.0 - skNz));
skCol = mix(skCol, vec3(0.52, 0.53, 0.55) * skShade, skWorn);
diffuseColor.rgb = mix(diffuseColor.rgb * skVc, skCol, skCov);
float skRough = mix(skPr.r, 0.36, skWorn);
float skMetal = mix(skPr.g, 0.92, skWorn);
float skGlowM = skPr.b * skCov * (1.0 - skWorn);
`;
const SK_FRAG_EMISSIVE = `#include <emissivemap_fragment>
float skPulse = mix(1.0, 0.3 + 0.7 * (0.5 + 0.5 * sin(uSkTime * 2.4 - vSkPos.z * 16.0 + vSkPos.y * 6.0)), uSkGlowAnim);
totalEmissiveRadiance += skA.rgb * skGlowM * uSkGlow * skPulse;`;

// если у геометрии нет цветов вершин — добавляем белые, чтобы vertexColors не дал чёрный цвет
function skEnsureColor(renderer, scene, camera, geometry) {
  if (!geometry || geometry.attributes.color || !geometry.attributes.position) return;
  const n = geometry.attributes.position.count, a = new Float32Array(n * 3).fill(1);
  geometry.setAttribute('color', new THREE.BufferAttribute(a, 3));
}
const _skMats = {};
let skMatCount = 0;
// legacy=true: материал на весь меш оружия (старые модели с цветами вершин); false — на отдельную часть
function skinMaterial(id, wear, legacy, weaponKey) {
  const d = GUN_SKINS[id]; if (!d) return null;
  const q = Math.round(clamp(wear || 0, 0, 1) * 20) / 20, small = weaponKey === 'pistol';
  const key = id + '|' + q + '|' + (legacy ? 1 : 0) + '|' + (small ? 1 : 0);
  if (_skMats[key]) return _skMats[key];
  const tx = skinTextures(id);
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0.3, envMap: skinEnv(), envMapIntensity: d.env != null ? d.env : 0.55 });
  const u = {
    uSkAlb: { value: tx.alb }, uSkProps: { value: tx.props }, uSkWear: { value: skWearTexture() },
    uSkScale: { value: (d.scale || 3.4) * (small ? 1.6 : 1) }, uSkWearAmt: { value: q },
    uSkCovWood: { value: d.only === 'metal' ? 0 : 1 }, uSkLegacy: { value: legacy ? 1 : 0 }, uSkShadeMin: { value: legacy ? 0.5 : 0.8 },
    uSkTime: SKIN_TIME, uSkGlowAnim: { value: d.anim || 0 }, uSkGlow: { value: d.glow || 0 },
  };
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', SK_VERT_PARS).replace('#include <begin_vertex>', SK_VERT);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', SK_FRAG_PARS)
      .replace('#include <map_fragment>', '')
      .replace('#include <color_fragment>', SK_FRAG_COLOR)
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = mix(roughness, skRough, skCov);')
      .replace('#include <metalnessmap_fragment>', 'float metalnessFactor = mix(metalness, skMetal, skCov);')
      .replace('#include <emissivemap_fragment>', SK_FRAG_EMISSIVE);
  };
  m.customProgramCacheKey = () => 'bp-skin-1';
  m.onBeforeRender = skEnsureColor;
  m.userData.isSkin = true; m.userData.skin = id;
  skMatCount++;
  return _skMats[key] = m;
}
// какие части оружия красит скин (partKind из моделей агента «Бой»)
const SK_NOSKIN = { lens: 1, glass: 1, optic: 1, emissive: 1, flash: 1, bore: 1, light: 1, laser: 1 };
const SK_SOFT = { wood: 1, polymer: 1, grip: 1, stock: 1, furniture: 1, handguard: 1, rubber: 1 };
function skinCovers(id, kind) {
  const d = GUN_SKINS[id]; if (!d || !kind) return !!d;
  if (SK_NOSKIN[kind]) return false;
  if (kind === 'accent') return false;
  if (d.only === 'metal' && SK_SOFT[kind]) return false;
  return true;
}

/* ---------------- хук для моделей оружия ---------------- */
let _skSuppress = 0;  // пока строятся модели ботов — не отдаём им скин игрока
// Возвращает материал части оружия с учётом скина, выбранного игроком для этого ствола; null — используй штатный.
function gunMaterial(weaponKey, partKind) {
  if (_skSuppress > 0 || typeof invGunSkin !== 'function') return null;
  const eq = invGunSkin(weaponKey);
  if (!eq || !skinCovers(eq.skin, partKind)) return null;
  return skinMaterial(eq.skin, eq.wear, !partKind, weaponKey);
}
const skGunMat = () => typeof gunMat !== 'undefined' ? gunMat : null;
const skCharMat = () => typeof charMat !== 'undefined' ? charMat : null;
// исходные материалы/геометрии — в WeakMap (userData копируется через JSON при clone)
const _skOrigMat = new WeakMap(), _skGeo = new WeakMap();
// eq = { skin, wear } | null; меши оружия — с userData.kind или со штатным gunMat; руки (charMat) пропускаем
function skinGunObject(root, eq, weaponKey) {
  if (!root) return;
  const gm = skGunMat(), cm = skCharMat();
  root.traverse(o => {
    if (!o.isMesh || (cm && o.material === cm)) return;
    const ud = o.userData;
    if (!_skOrigMat.has(o)) {
      const isSk = o.material && o.material.userData && o.material.userData.isSkin;
      if (!ud.kind && o.material !== gm && !isSk) return;
      _skOrigMat.set(o, isSk ? (gm || o.material) : o.material);
    }
    let m = null;
    if (eq && GUN_SKINS[eq.skin]) m = ud.kind ? (skinCovers(eq.skin, ud.kind) ? skinMaterial(eq.skin, eq.wear, false, weaponKey) : null) : skinMaterial(eq.skin, eq.wear, true, weaponKey);
    o.material = m || _skOrigMat.get(o);
  });
}

/* ---- перекраска бойцов по палитре (запасной путь, пока нет makeBody(team, skinId)) ---- */
const _skRecolor = {};
function skHexKey(r, g, b) { return (Math.round(r * 255) << 16) | (Math.round(g * 255) << 8) | Math.round(b * 255); }
function recolorGeo(geo, team, skinId) {
  const sk = CHAR_SKINS[skinId], S = STYLE[team];
  if (!geo || !sk || !S || !geo.attributes.color) return geo;
  const key = geo.uuid + '|' + skinId;
  if (_skRecolor[key]) return _skRecolor[key];
  const map = {};
  for (const k of CHAR_PAL_KEYS) if (sk.palette[k] != null && S[k] != null) map[S[k]] = new THREE.Color(sk.palette[k]);
  const g = geo.clone(), col = g.attributes.color;
  for (let i = 0; i < col.count; i++) {
    const to = map[skHexKey(col.getX(i), col.getY(i), col.getZ(i))];
    if (to) col.setXYZ(i, to.r, to.g, to.b);
  }
  col.needsUpdate = true;
  return _skRecolor[key] = g;
}
// меши с charMat в объекте: подменяем геометрию на перекрашенную копию (оригинал помним)
function recolorObject(root, team, skinId) {
  const cm = skCharMat(); if (!root || !cm) return;
  root.traverse(o => {
    if (!o.isMesh || o.material !== cm) return;
    let st = _skGeo.get(o);
    if (!st) { st = { base: o.geometry, cur: o.geometry }; _skGeo.set(o, st); }
    if (o.geometry !== st.cur) st.base = o.geometry;   // геометрию заменили снаружи (смена оружия)
    const g = skinId ? recolorGeo(st.base, team, skinId) : st.base;
    o.geometry = st.cur = g;
  });
}
const skHasRebuild = () => typeof rebuildBody === 'function';

/* ---- случайные скины ботам ---- */
function skPickRarity(odds) {
  const o = odds || SKIN_RARITY, tot = SKIN_RARITY_ORDER.reduce((s, k) => s + (typeof o[k] === 'number' ? o[k] : o[k].w), 0);
  let x = Math.random() * tot;
  for (const k of SKIN_RARITY_ORDER) { x -= typeof o[k] === 'number' ? o[k] : o[k].w; if (x <= 0) return k; }
  return 'common';
}
function skRandomOf(pool, odds) {
  for (let t = 0; t < 6; t++) {
    const r = skPickRarity(odds), list = pool.filter(id => (GUN_SKINS[id] || CHAR_SKINS[id]).rarity === r);
    if (list.length) return pick(list);
  }
  return pick(pool);
}
const BOT_SKIN_ODDS = { common: 40, uncommon: 28, rare: 18, epic: 10, legendary: 4 };
function pickBotCharSkin(team) {
  if (Math.random() < 0.3) return null;
  const pool = Object.keys(CHAR_SKINS).filter(id => CHAR_SKINS[id].team === team || CHAR_SKINS[id].team === 'any');
  return pool.length ? skRandomOf(pool, BOT_SKIN_ODDS) : null;
}
function pickBotGunSkin() {
  if (Math.random() < 0.35) return null;
  return { skin: skRandomOf(Object.keys(GUN_SKINS), BOT_SKIN_ODDS), wear: Math.pow(Math.random(), 1.5) };
}
function skinBot(u) {
  if (!u || !u.mesh) return;
  if (!skHasRebuild()) recolorObject(u.mesh.root, u.team, u.skin);
  skinGunObject(u.mesh.gun, u.gunSkin, u.cur);
}
// руки во вьюмодели — по палитре выбранного скина бойца игрока
function skinViewArms() {
  if (typeof VM === 'undefined') return;
  const team = (typeof player !== 'undefined' && player && player.team) || 'A';
  const id = typeof invCharSkin === 'function' ? invCharSkin(team) : null;
  for (const k in VM) recolorObject(VM[k].g, 'A', id && CHAR_SKINS[id] && CHAR_SKINS[id].team !== 'B' ? id : null);
}
// перекрашивает уже созданные модели: вьюмодель игрока и оружие ботов
function applyGunSkins() {
  try {
    if (typeof VM !== 'undefined') for (const k in VM) skinGunObject(VM[k].g, typeof invGunSkin === 'function' ? invGunSkin(k) : null, k);
    if (typeof bots !== 'undefined') for (const b of bots) skinBot(b);
    skinViewArms();
  } catch (e) { console.error(e); }
}

/* ---- обёртки создания бойцов (чужие файлы не правим: переопределяем глобальные функции) ---- */
let _skPendingSkin = null;
try {
  if (typeof makeBody === 'function') {
    const orig = makeBody;
    makeBody = function (team, skinId) {
      if (skinId === undefined) skinId = _skPendingSkin;
      _skSuppress++;
      try { return orig.call(this, team, skinId || undefined); } finally { _skSuppress--; }
    };
    makeBody._skOrig = orig;
  }
  if (typeof setBotWeapon === 'function') {
    const orig = setBotWeapon;
    setBotWeapon = function (u) {
      _skSuppress++;
      try { orig.call(this, u); } finally { _skSuppress--; }
      try { skinBot(u); } catch (e) { console.error(e); }
    };
    setBotWeapon._skOrig = orig;
  }
  if (typeof makeUnit === 'function') {
    const orig = makeUnit;
    makeUnit = function (team, name, isPlayer) {
      _skPendingSkin = isPlayer ? null : pickBotCharSkin(team);
      const skin = _skPendingSkin;
      let u;
      try { u = orig.apply(this, arguments); } finally { _skPendingSkin = null; }
      try {
        u.skin = isPlayer ? (typeof invCharSkin === 'function' ? invCharSkin(team) : null) : skin;
        if (!isPlayer) { u.gunSkin = pickBotGunSkin(); skinBot(u); }
      } catch (e) { console.error(e); }
      return u;
    };
  }
} catch (e) { console.error(e); }

// время для анимированного свечения — один дешёвый uniform на все материалы
(function skTick(t) { SKIN_TIME.value = (t || 0) / 1000; requestAnimationFrame(skTick); })();

/* ---------------- 2D-миниатюры для интерфейса ---------------- */
const SK_GUN_SIL = [[0.04, 0.42], [0.3, 0.38], [0.34, 0.3], [0.62, 0.3], [0.64, 0.36], [0.96, 0.37], [0.96, 0.45], [0.66, 0.47], [0.6, 0.56], [0.5, 0.56],
  [0.47, 0.82], [0.4, 0.84], [0.42, 0.56], [0.36, 0.56], [0.3, 0.75], [0.22, 0.74], [0.26, 0.56], [0.1, 0.62], [0.04, 0.6]];
function skinThumb(cv, item) {
  const g = cv.getContext('2d'), W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  if (!item) { return; }
  if (item.t === 'c') return charThumb(cv, item.id);
  const def = GUN_SKINS[item.id];
  const gr = g.createRadialGradient(W / 2, H / 2, 4, W / 2, H / 2, W * 0.7);
  gr.addColorStop(0, 'rgba(255,255,255,.07)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, W, H);
  if (!def) {   // штатный
    skSilPath(g, W, H); g.fillStyle = '#2c2f32'; g.fill(); g.strokeStyle = 'rgba(255,255,255,.18)'; g.lineWidth = 1; g.stroke(); return;
  }
  const c = skinCanvases(item.id);
  skSilPath(g, W, H);
  g.save(); g.clip();
  const pat = g.createPattern(c.a, 'repeat'), sc = W / 340;
  if (pat.setTransform) pat.setTransform(new DOMMatrix([sc, 0, 0, sc, 0, 0]));
  g.fillStyle = pat; g.fillRect(0, 0, W, H);
  const sh = g.createLinearGradient(0, H * 0.3, 0, H * 0.85);
  sh.addColorStop(0, 'rgba(255,255,255,.16)'); sh.addColorStop(0.4, 'rgba(255,255,255,0)'); sh.addColorStop(1, 'rgba(0,0,0,.35)');
  g.fillStyle = sh; g.fillRect(0, 0, W, H);
  g.restore();
  skSilPath(g, W, H); g.strokeStyle = 'rgba(0,0,0,.6)'; g.lineWidth = 1; g.stroke();
}
function skSilPath(g, W, H) {
  g.beginPath();
  SK_GUN_SIL.forEach(([x, y], i) => { const X = W * (0.06 + x * 0.88), Y = H * (0.04 + y * 0.92); i ? g.lineTo(X, Y) : g.moveTo(X, Y); });
  g.closePath();
}
const skCss = n => '#' + (n >>> 0).toString(16).padStart(6, '0');
function charThumb(cv, id) {
  const g = cv.getContext('2d'), W = cv.width, H = cv.height, sk = CHAR_SKINS[id];
  const team = sk ? sk.team === 'any' ? 'A' : sk.team : (id === '_defB' ? 'B' : 'A');
  const S = Object.assign({}, STYLE[team], sk ? sk.palette : {}), c = k => skCss(S[k]);
  const hg = sk && sk.headgear || S.headgear || 'helmet', ex = sk && sk.extras || [];
  g.clearRect(0, 0, W, H);
  const cx = W / 2, s = H / 100;
  const R = (x, y, w, h, col, r = 2) => { g.fillStyle = col; g.beginPath(); g.roundRect ? g.roundRect(cx + x * s, y * s, w * s, h * s, r * s) : g.rect(cx + x * s, y * s, w * s, h * s); g.fill(); };
  if (ex.includes('backpack')) R(-15, 26, 30, 30, skCss(STYLE[team].pouch), 4);
  R(-11, 58, 9, 30, c('uni')); R(2, 58, 9, 30, c('uni'));                      // ноги
  R(-11.5, 70, 10, ex.includes('kneepads') ? 7 : 5, c('pad')); R(1.5, 70, 10, ex.includes('kneepads') ? 7 : 5, c('pad'));
  R(-12, 86, 11, 8, c('boot')); R(1, 86, 11, 8, c('boot'));
  R(-13, 52, 26, 10, c('uni2'), 3);                                            // пояс
  R(-15, 24, 30, 31, c('uni'), 6);                                             // торс
  R(-13, 27, 26, 25, c('vest'), 4);
  R(-11, 41, 6, 9, c('pouch')); R(-3, 41, 6, 9, c('pouch')); R(5, 41, 6, 9, c('pouch'));
  R(-10, 30, 5, 4, c('acc'), 1);
  R(-22, 26, 8, 26, c('uni'), 4); R(14, 26, 8, 26, c('uni'), 4);              // руки
  R(-22, 31, 8, 4, c('acc'), 1); R(14, 31, 8, 4, c('acc'), 1);
  R(-21.5, 50, 7, 6, c('glove')); R(14.5, 50, 7, 6, c('glove'));
  if (ex.includes('radio')) { R(9, 18, 2, 10, '#111'); R(7, 26, 6, 8, '#222321'); }
  R(-8, 6, 16, 18, c('face'), 6);                                              // голова
  R(-7, 12, 14, 4, c('lens'), 2);
  if (hg === 'helmet') { R(-10, 2, 20, 9, c('helm'), 7); R(-11, 9, 22, 3, c('helm'), 1); }
  else if (hg === 'cap') { R(-9, 3, 18, 7, c('helm'), 5); R(-1, 9, 14, 2.5, c('helm'), 1); }
  else if (hg === 'boonie') { R(-8, 2, 16, 8, c('helm'), 4); R(-13, 8.5, 26, 3, c('helm'), 1.5); }
  else if (hg === 'balaclava') { R(-8.5, 4, 17, 19, c('face'), 6); R(-6, 12, 12, 4, c('lens'), 2); }
  if (ex.includes('patch')) R(-21, 38, 6, 5, c('acc'), 1);
}
