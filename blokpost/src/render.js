'use strict';
/* ---------------- рендер ----------------
   Цвета: линейный рабочий цвет (ColorManagement), вывод sRGB, тональная компрессия ACES.
   Уровни графики settings.gfx: 'low' | 'medium' | 'high' (по умолчанию medium на телефоне, high на ПК).
   Тени от солнца: settings.shadows === true (только medium/high).
   applyGraphics() — пересобрать уровень и перенастроить рендер после смены settings.gfx / settings.shadows. */
THREE.ColorManagement.legacyMode = false;
const canvas = $('#view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: !isTouch, powerPreference: 'high-performance' });
renderer.autoClear = false;
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.92;
const scene = new THREE.Scene();
const SKY = 0xc4cfd2;                 // цвет дымки у горизонта (sRGB)
scene.background = new THREE.Color(SKY);
scene.fog = new THREE.FogExp2(SKY, 0.0062);
const BASE_FOV = 74;
const camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.05, 900);
camera.rotation.order = 'YXZ';
const gfxLevel = () => { const g = settings.gfx; return g === 'low' || g === 'medium' || g === 'high' ? g : (isTouch ? 'medium' : 'high'); };
const GFX = {
  low: { tex: 128, normals: false, std: false, sky: 512, overlay: 24, sub: 2, bags: false },
  medium: { tex: 256, normals: true, std: true, sky: 1024, overlay: 40, sub: 3, bags: true },
  high: { tex: 512, normals: true, std: true, sky: 2048, overlay: 56, sub: 3, bags: true },
};
// направление на солнце: тёплый вечерний свет с юго-запада
const SUN_DIR = new THREE.Vector3(-0.52, 0.58, 0.63).normalize();
const hemi = new THREE.HemisphereLight(0xcfdde6, 0x6a5c48, 0.75); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffdcb0, 2.1);
sun.position.copy(SUN_DIR).multiplyScalar(90).add(new THREE.Vector3(MW * CELL / 2, 0, MH * CELL / 2));
sun.target.position.set(MW * CELL / 2, 0, MH * CELL / 2);
scene.add(sun); scene.add(sun.target);

const vmScene = new THREE.Scene();
const vmCam = new THREE.PerspectiveCamera(58, 1, 0.01, 10);
vmScene.add(vmCam);
vmScene.add(new THREE.HemisphereLight(0xdfe8ee, 0x5a4c3c, 0.9));
const vmSun = new THREE.DirectionalLight(0xffe6c4, 1.5); vmSun.position.set(1, 2, 1); vmScene.add(vmSun);

function resize() {
  const w = innerWidth, h = innerHeight;
  const cap = gfxLevel() === 'low' ? 1 : 3;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, settings.quality, cap));
  renderer.setSize(w, h, false);
  camera.aspect = vmCam.aspect = w / h;
  camera.updateProjectionMatrix(); vmCam.updateProjectionMatrix();
  $('#rotate').classList.toggle('need', isTouch);
}
addEventListener('resize', resize);

function tex(w, h, draw, rep) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (rep) t.repeat.set(rep[0], rep[1]);
  t.anisotropy = 4;
  t.encoding = THREE.sRGBEncoding;
  return t;
}
function grain(g, w, h, a) {
  const img = g.getImageData(0, 0, w, h), d = img.data;
  for (let i = 0; i < d.length; i += 4) { const n = (Math.random() - 0.5) * a; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
  g.putImageData(img, 0, 0);
}
const glowTex = tex(64, 64, (g, w, h) => {
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,250,220,1)'); gr.addColorStop(0.3, 'rgba(255,190,90,.85)'); gr.addColorStop(1, 'rgba(255,120,40,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
const blobTex = tex(64, 64, (g, w, h) => {
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(0,0,0,.5)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});

// Всё ниже до конца файла — внутренности сборки уровня в отдельном блоке, чтобы не засорять общую область видимости.
const levelMeshes = [];          // пол, стены, препятствия, пропсы — по ним работают попадания и декали
let _applyGfxImpl = null;
function applyGraphics() { _applyGfxImpl(); }
{
/* ---------------- процедурный шум (тайлящийся, предвычисленный) ---------------- */
const NOISE_N = 256;
function _hash(x, y, s) { let h = (x * 374761393 + y * 668265263 + s * 982451653) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967295; }
function _vnoise(x, y, p, s) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const x0 = ((xi % p) + p) % p, x1 = (x0 + 1) % p, y0 = ((yi % p) + p) % p, y1 = (y0 + 1) % p;
  const a = _hash(x0, y0, s), b = _hash(x1, y0, s), c = _hash(x0, y1, s), d = _hash(x1, y1, s);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function _fbmField(base, oct, seed) {
  const f = new Float32Array(NOISE_N * NOISE_N);
  for (let y = 0; y < NOISE_N; y++) for (let x = 0; x < NOISE_N; x++) {
    let a = 0.5, t = 0, n = 0;
    for (let o = 0; o < oct; o++) { const p = base << o; t += a * _vnoise(x / NOISE_N * p, y / NOISE_N * p, p, seed + o * 17); n += a; a *= 0.5; }
    f[y * NOISE_N + x] = t / n;
  }
  return f;
}
const NZ = { lo: _fbmField(4, 5, 11), mid: _fbmField(16, 4, 23), hi: _fbmField(64, 2, 37) };
// выборка шума с периодом: u, v в долях тайла, k — сколько раз шум укладывается в тайл
function nz(field, u, v, k = 1) {
  const x = ((Math.floor(u * k * NOISE_N) % NOISE_N) + NOISE_N) % NOISE_N, y = ((Math.floor(v * k * NOISE_N) % NOISE_N) + NOISE_N) % NOISE_N;
  return field[y * NOISE_N + x];
}
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const fract = x => x - Math.floor(x);

/* ---------------- процедурные PBR-материалы ----------------
   fn(u, v, o) заполняет o.r, o.g, o.b (0..1, sRGB), o.h (высота 0..1), o.ro (шероховатость 0..1). */
function pbrTextures(size, fn, normalStrength, wantMaps) {
  const cA = document.createElement('canvas'); cA.width = cA.height = size;
  const gA = cA.getContext('2d'), imA = gA.createImageData(size, size), dA = imA.data;
  const H = new Float32Array(size * size), Ro = new Uint8ClampedArray(size * size);
  const o = { r: 0, g: 0, b: 0, h: 0.5, ro: 0.8 };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    o.h = 0.5; o.ro = 0.8;
    fn(x / size, y / size, o);
    const i = y * size + x;
    dA[i * 4] = o.r * 255; dA[i * 4 + 1] = o.g * 255; dA[i * 4 + 2] = o.b * 255; dA[i * 4 + 3] = 255;
    H[i] = o.h; Ro[i] = o.ro * 255;
  }
  gA.putImageData(imA, 0, 0);
  const mk = (c, srgb) => {
    const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4;
    if (srgb) t.encoding = THREE.sRGBEncoding; return t;
  };
  const out = { map: mk(cA, true) };
  if (!wantMaps) return out;
  const cN = document.createElement('canvas'); cN.width = cN.height = size;
  const gN = cN.getContext('2d'), imN = gN.createImageData(size, size), dN = imN.data;
  const cR = document.createElement('canvas'); cR.width = cR.height = size;
  const gR = cR.getContext('2d'), imR = gR.createImageData(size, size), dR = imR.data;
  const s = normalStrength * size / 256;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = y * size + x;
    const l = H[y * size + (x + size - 1) % size], r = H[y * size + (x + 1) % size];
    const t = H[((y + size - 1) % size) * size + x], b = H[((y + 1) % size) * size + x];
    let nx = (l - r) * s, ny = (b - t) * s, nzv = 1; const L = Math.hypot(nx, ny, nzv); nx /= L; ny /= L; nzv /= L;
    dN[i * 4] = (nx * 0.5 + 0.5) * 255; dN[i * 4 + 1] = (ny * 0.5 + 0.5) * 255; dN[i * 4 + 2] = (nzv * 0.5 + 0.5) * 255; dN[i * 4 + 3] = 255;
    dR[i * 4] = dR[i * 4 + 1] = dR[i * 4 + 2] = Ro[i]; dR[i * 4 + 3] = 255;
  }
  gN.putImageData(imN, 0, 0); gR.putImageData(imR, 0, 0);
  out.normalMap = mk(cN, false); out.roughnessMap = mk(cR, false);
  return out;
}
const MATDEF = {
  // стены (тайл = 2.5 м)
  concrete: { size: 2.5, n: 3.5, metal: 0, fn(u, v, o) {
    const big = nz(NZ.lo, u, v), m = nz(NZ.mid, u, v, 2), f = nz(NZ.hi, u, v, 2);
    const streak = nz(NZ.mid, u * 4, v * 0.25);
    let c = 0.6 + (big - 0.5) * 0.18 + (m - 0.5) * 0.08 + (f - 0.5) * 0.06 - smooth(0.55, 0.8, streak) * 0.08;
    const su = Math.min(fract(u * 2), 1 - fract(u * 2)), sv = Math.min(fract(v * 4), 1 - fract(v * 4));
    const seam = Math.min(su * 2.5, sv * 5);       // швы опалубки
    const hole = Math.hypot(fract(u * 4) - 0.5, (fract(v * 4) - 0.5) * 0.5);
    o.h = 0.55 + (f - 0.5) * 0.25 + (m - 0.5) * 0.2;
    if (seam < 0.012) { c *= 0.78; o.h = 0.2; }
    if (hole < 0.03) { c *= 0.55; o.h = 0.05; }
    o.r = c * 1.0; o.g = c * 0.985; o.b = c * 0.95; o.ro = 0.88 + (f - 0.5) * 0.1;
  } },
  brick: { size: 2.5, n: 6, metal: 0, fn(u, v, o) {
    const rows = 32, row = Math.floor(v * rows), off = (row % 2) * 0.5, cols = 10;
    const bu = u * cols + off, col = Math.floor(bu);
    const fu = fract(bu), fv = fract(v * rows);
    const mortar = fu < 0.06 || fv < 0.14;
    const hb = _hash(((col % cols) + cols) % cols, row, 5), f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v);
    if (mortar) { const c = 0.62 + (f - 0.5) * 0.1; o.r = c; o.g = c * 0.97; o.b = c * 0.9; o.h = 0.15; o.ro = 0.95; }
    else {
      const k = 0.75 + hb * 0.35 + (f - 0.5) * 0.12 - smooth(0.6, 0.85, m) * 0.15;
      o.r = 0.56 * k; o.g = 0.27 * k * (0.9 + hb * 0.15); o.b = 0.19 * k; o.h = 0.7 + (f - 0.5) * 0.3; o.ro = 0.82;
    }
  } },
  metal: { size: 2.5, n: 7, metal: 0.35, fn(u, v, o) {
    const ribs = 12, w = fract(u * ribs), prof = smooth(0.0, 0.18, w) * (1 - smooth(0.5, 0.68, w));
    const m = nz(NZ.mid, u, v), f = nz(NZ.hi, u, v, 2), streak = nz(NZ.mid, u * 6, v * 0.3, 1);
    const rust = smooth(0.72, 0.86, m * 0.6 + streak * 0.5) * 0.8;
    const c = 0.66 + (f - 0.5) * 0.05 - prof * 0.04;
    o.r = c * (1 - rust) + 0.45 * rust; o.g = c * 1.02 * (1 - rust) + 0.25 * rust; o.b = c * 1.05 * (1 - rust) + 0.14 * rust;
    o.h = 0.3 + prof * 0.6; o.ro = 0.48 + rust * 0.4 + (f - 0.5) * 0.1;
  } },
  plaster: { size: 5, n: 1.5, metal: 0, fn(u, v, o) {
    const m = nz(NZ.mid, u, v), f = nz(NZ.hi, u, v, 2);
    let c = 0.8 + (m - 0.5) * 0.08 + (f - 0.5) * 0.05;
    // нижняя панель — кафель
    o.h = 0.5 + (f - 0.5) * 0.2; o.ro = 0.9;
    if (v > 0.985) { c = 0.35; o.h = 0.3; o.r = o.g = o.b = c; return; }   // плинтус
    if (v > 0.77) {
      const tu = fract(u * 20), tvv = fract(v * 40);
      if (tu < 0.05 || tvv < 0.08) { c = 0.62; o.h = 0.2; } else { c = 0.7 + _hash(Math.floor(u * 20), Math.floor(v * 40), 9) * 0.06; o.ro = 0.35; o.h = 0.6; }
      o.r = c * 0.78; o.g = c * 0.88; o.b = c * 0.86;
    } else { o.r = c; o.g = c * 0.95; o.b = c * 0.86; }
  } },
  // полы (тайл = 2.5 м)
  asphalt: { size: 2.5, n: 3, metal: 0, fn(u, v, o) {
    const f = nz(NZ.hi, u, v, 4), m = nz(NZ.mid, u, v), big = nz(NZ.lo, u, v);
    let c = 0.24 + (m - 0.5) * 0.06 + (big - 0.5) * 0.06;
    const sp = _hash((u * 512) | 0, (v * 512) | 0, 3);
    if (sp > 0.93) c += 0.12; else if (sp < 0.05) c -= 0.06;
    o.r = c; o.g = c * 1.0; o.b = c * 1.02; o.h = 0.5 + (f - 0.5) * 0.5 + (sp > 0.93 ? 0.2 : 0); o.ro = 0.92;
  } },
  pavers: { size: 2.5, n: 5, metal: 0, fn(u, v, o) {
    const rows = 10, row = Math.floor(v * rows), cols = 5, bu = u * cols + (row % 2) * 0.5, col = Math.floor(bu);
    const fu = fract(bu), fv = fract(v * rows), gap = fu < 0.04 || fv < 0.08;
    const hb = _hash(((col % cols) + cols) % cols, row, 7), f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v);
    if (gap) { o.r = o.g = o.b = 0.22; o.h = 0.1; o.ro = 1; }
    else {
      const k = 0.44 + hb * 0.12 + (f - 0.5) * 0.08 - smooth(0.6, 0.9, m) * 0.12;
      const warm = hb > 0.7 ? 1 : 0;
      o.r = k * (1 + warm * 0.12); o.g = k * (0.98 + warm * 0.02); o.b = k * (0.94 - warm * 0.06); o.h = 0.7 + (f - 0.5) * 0.2; o.ro = 0.8;
    }
  } },
  tile: { size: 2.5, n: 4, metal: 0, fn(u, v, o) {
    const tu = fract(u * 5), tv = fract(v * 5), grout = tu < 0.025 || tv < 0.025;
    const hb = _hash(Math.floor(u * 5), Math.floor(v * 5), 13), f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v);
    if (grout) { o.r = 0.4; o.g = 0.39; o.b = 0.36; o.h = 0.2; o.ro = 0.9; }
    else {
      const chk = (Math.floor(u * 5) + Math.floor(v * 5)) % 2;
      const k = (chk ? 0.58 : 0.5) + hb * 0.04 + (f - 0.5) * 0.04 - smooth(0.62, 0.9, m) * 0.1;
      o.r = k; o.g = k * 0.97; o.b = k * 0.92; o.h = 0.6; o.ro = 0.28 + smooth(0.55, 0.85, m) * 0.4;
    }
  } },
  plates: { size: 2.5, n: 3, metal: 0, fn(u, v, o) {
    const su = Math.min(fract(u * 2), 1 - fract(u * 2)), sv = Math.min(fract(v * 2), 1 - fract(v * 2));
    const f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v), big = nz(NZ.lo, u, v);
    let c = 0.43 + (big - 0.5) * 0.12 + (m - 0.5) * 0.08 + (f - 0.5) * 0.05;
    o.h = 0.55 + (f - 0.5) * 0.25; o.ro = 0.85;
    if (Math.min(su, sv) < 0.012) { c *= 0.55; o.h = 0.1; }
    o.r = c * 1.02; o.g = c; o.b = c * 0.95;
  } },
  floorc: { size: 2.5, n: 2, metal: 0, fn(u, v, o) {
    const f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v), big = nz(NZ.lo, u, v);
    let c = 0.45 + (big - 0.5) * 0.14 + (m - 0.5) * 0.06 + (f - 0.5) * 0.03;
    const su = Math.min(fract(u), 1 - fract(u)), sv = Math.min(fract(v), 1 - fract(v));
    o.h = 0.5 + (f - 0.5) * 0.12; o.ro = 0.55 + (m - 0.5) * 0.4;
    if (Math.min(su, sv) < 0.008) { c *= 0.6; o.h = 0.1; }
    o.r = c; o.g = c * 0.99; o.b = c * 0.96;
  } },
  // пропсы (тайл = 1 м, если не указано)
  wood: { size: 2.3, n: 5, metal: 0, fn(u, v, o) {
    const pl = 7, fv = fract(v * pl), plank = Math.floor(v * pl);
    const grainN = nz(NZ.mid, u * 0.25, v * 3 + plank * 0.37, 1), f = nz(NZ.hi, u, v, 2);
    const hb = _hash(plank, 1, 21);
    let c = 0.55 + (grainN - 0.5) * 0.25 + (f - 0.5) * 0.06 + hb * 0.08;
    o.h = 0.6 + (grainN - 0.5) * 0.15;
    if (fv < 0.05) { c *= 0.45; o.h = 0.1; }
    const frame = Math.min(u, 1 - u, v, 1 - v) < 0.07;
    if (frame) { c *= 0.82; o.h = 0.9; }
    o.r = c * 0.72; o.g = c * 0.52; o.b = c * 0.32; o.ro = 0.85;
  } },
  container: { size: 2.5, n: 8, metal: 0.45, fn(u, v, o) {
    const ribs = 9, w = fract(u * ribs), prof = smooth(0.05, 0.2, w) * (1 - smooth(0.55, 0.7, w));
    const m = nz(NZ.mid, u, v), f = nz(NZ.hi, u, v, 2), streak = nz(NZ.mid, u * 5, v * 0.3);
    const rust = smooth(0.66, 0.8, m * 0.55 + streak * 0.5);
    const c = 0.82 - prof * 0.05 + (f - 0.5) * 0.05;
    o.r = c * (1 - rust) + 0.42 * rust; o.g = c * (1 - rust) + 0.24 * rust; o.b = c * (1 - rust) + 0.14 * rust;
    o.h = 0.25 + prof * 0.65; o.ro = 0.5 + rust * 0.4;
  } },
  bag: { size: 1, n: 3, metal: 0, fn(u, v, o) {
    const f = nz(NZ.hi, u, v, 4), weave = (Math.sin(u * 400) * Math.sin(v * 400)) * 0.5 + 0.5, m = nz(NZ.mid, u, v);
    const c = 0.62 + (f - 0.5) * 0.08 + weave * 0.04 - smooth(0.6, 0.9, m) * 0.12;
    o.r = c * 0.86; o.g = c * 0.76; o.b = c * 0.55; o.h = 0.5 + weave * 0.2; o.ro = 1;
  } },
  paint: { size: 1.2, n: 2, metal: 0.5, fn(u, v, o) {
    const f = nz(NZ.hi, u, v, 2), m = nz(NZ.mid, u, v), scr = nz(NZ.hi, u * 0.1, v * 4);
    const rust = smooth(0.68, 0.82, m), wear = smooth(0.78, 0.9, scr);
    const c = 0.85 + (f - 0.5) * 0.06;
    o.r = c * (1 - rust) + 0.4 * rust + wear * 0.1; o.g = c * (1 - rust) + 0.22 * rust + wear * 0.1; o.b = c * (1 - rust) + 0.12 * rust + wear * 0.1;
    o.h = 0.5 - rust * 0.2; o.ro = 0.42 + rust * 0.45 + wear * 0.1;
  } },
};

/* ---------------- небо и окружение ---------------- */
let skyTex = null, envRT = null;
function buildSky(W) {
  const Hh = W / 2, c = document.createElement('canvas'); c.width = W; c.height = Hh;
  const g = c.getContext('2d'), img = g.createImageData(W, Hh), d = img.data;
  const su = Math.atan2(SUN_DIR.z, SUN_DIR.x) / (2 * Math.PI) + 0.5, sv = Math.asin(SUN_DIR.y) / Math.PI + 0.5;
  const sd = new THREE.Vector3(), dir = new THREE.Vector3();
  sd.copy(SUN_DIR);
  for (let y = 0; y < Hh; y++) {
    const v = 1 - (y + 0.5) / Hh, lat = (v - 0.5) * Math.PI, el = Math.sin(lat);
    for (let x = 0; x < W; x++) {
      const u = (x + 0.5) / W, lon = (u - 0.5) * 2 * Math.PI;
      dir.set(Math.cos(lat) * Math.cos(lon), el, Math.cos(lat) * Math.sin(lon));
      const cs = dir.dot(sd);
      let r, gg, b;
      if (el >= 0) {
        const t = Math.pow(el, 0.45);
        r = 0.77 + (0.30 - 0.77) * t; gg = 0.81 + (0.50 - 0.81) * t; b = 0.82 + (0.74 - 0.82) * t;
        // облака: кучевые у горизонта, перистые выше
        const cu = u, cvv = (1 - el) * 0.9;
        const n1 = nz(NZ.lo, cu * 3, cvv * 2.2), n2 = nz(NZ.mid, cu * 3, cvv * 4);
        const dens = smooth(0.48, 0.72, n1 * 0.7 + n2 * 0.4) * smooth(0.02, 0.12, el) * (1 - smooth(0.55, 0.95, el));
        const lit = 0.88 + 0.12 * Math.max(0, cs);
        r = r * (1 - dens) + 0.93 * lit * dens; gg = gg * (1 - dens) + 0.91 * lit * dens; b = b * (1 - dens) + 0.88 * lit * dens;
        const shade = smooth(0.6, 0.95, n1) * dens * 0.18; r -= shade; gg -= shade; b -= shade * 0.8;
      } else {
        const t = Math.min(1, -el * 4);
        r = 0.77 + (0.42 - 0.77) * t; gg = 0.81 + (0.40 - 0.81) * t; b = 0.82 + (0.37 - 0.82) * t;
      }
      // ореол солнца и диск
      const halo = Math.pow(Math.max(0, cs), 8) * 0.35 + Math.pow(Math.max(0, cs), 64) * 0.5;
      r += halo * 1.0; gg += halo * 0.85; b += halo * 0.6;
      if (cs > 0.9993) { r = gg = b = 4; }
      const i = (y * W + x) * 4;
      d[i] = clamp(r, 0, 1) * 255; d[i + 1] = clamp(gg, 0, 1) * 255; d[i + 2] = clamp(b, 0, 1) * 255; d[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.mapping = THREE.EquirectangularReflectionMapping; t.encoding = THREE.sRGBEncoding;
  return t;
}

/* ---------------- построитель склеенной геометрии ---------------- */
class GB {
  constructor() { this.p = []; this.n = []; this.u = []; this.c = []; this.i = []; }
  get vc() { return this.p.length / 3; }
  v(x, y, z, nx, ny, nz_, u, v, col) { this.p.push(x, y, z); this.n.push(nx, ny, nz_); this.u.push(u, v); this.c.push(col.r, col.g, col.b); return this.vc - 1; }
  quad(a, b, c, d) { this.i.push(a, b, c, a, c, d); }
  // добавить готовую геометрию с матрицей, цветом и масштабом UV
  geo(g, m4, col, uvs = 1) {
    const base = this.vc, p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
    const nm = new THREE.Matrix3().getNormalMatrix(m4), v = new THREE.Vector3();
    for (let k = 0; k < p.count; k++) {
      v.fromBufferAttribute(p, k).applyMatrix4(m4); this.p.push(v.x, v.y, v.z);
      v.fromBufferAttribute(n, k).applyMatrix3(nm).normalize(); this.n.push(v.x, v.y, v.z);
      if (uv) this.u.push(uv.getX(k) * uvs, uv.getY(k) * uvs); else this.u.push(0, 0);
      this.c.push(col.r, col.g, col.b);
    }
    if (g.index) for (let k = 0; k < g.index.count; k++) this.i.push(g.index.getX(k) + base);
    else for (let k = 0; k < p.count; k++) this.i.push(k + base);
    g.dispose();
  }
  // коробка в мировых координатах с UV в метрах / ts
  box(x0, y0, z0, x1, y1, z1, col, ts = 1, ao) {
    const F = [
      [[1, 0, 0], [x1, y0, z1], [0, 0, -1], z1 - z0, y1 - y0],
      [[-1, 0, 0], [x0, y0, z0], [0, 0, 1], z1 - z0, y1 - y0],
      [[0, 0, 1], [x0, y0, z1], [1, 0, 0], x1 - x0, y1 - y0],
      [[0, 0, -1], [x1, y0, z0], [-1, 0, 0], x1 - x0, y1 - y0],
      [[0, 1, 0], [x0, y1, z1], [1, 0, 0], x1 - x0, z1 - z0, [0, 0, -1]],
      [[0, -1, 0], [x0, y0, z0], [1, 0, 0], x1 - x0, z1 - z0, [0, 0, 1]],
    ];
    const cb = new THREE.Color();
    for (const [nrm, o, t, w, h, up] of F) {
      const uvec = up || [0, 1, 0], idx = [];
      for (const [a, b] of [[0, 0], [w, 0], [w, h], [0, h]]) {
        const x = o[0] + t[0] * a + uvec[0] * b, y = o[1] + t[1] * a + uvec[1] * b, z = o[2] + t[2] * a + uvec[2] * b;
        cb.copy(col); if (ao && !up && b === 0) cb.multiplyScalar(ao);
        idx.push(this.v(x, y, z, nrm[0], nrm[1], nrm[2], (a + (t[0] ? x0 : z0) * 0) / ts, b / ts, cb));
      }
      this.quad(idx[0], idx[1], idx[2], idx[3]);
    }
  }
  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.u, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.setIndex(this.i);
    g.computeBoundingSphere(); g.computeBoundingBox();
    return g;
  }
}
const hexC = (h, k = 1) => new THREE.Color(h).multiplyScalar(k);

/* ---------------- сборка уровня ---------------- */
let levelGroup = null;
const _matCache = {};
function levelMat(key, extra = {}) {
  const Q = GFX[gfxLevel()], d = MATDEF[key];
  const id = key + JSON.stringify(extra) + gfxLevel();
  if (_matCache[id]) return _matCache[id];
  if (!d._t || d._q !== Q.tex) { d._t = pbrTextures(Q.tex, d.fn, d.n, Q.normals); d._q = Q.tex; }
  const opts = Object.assign({ map: d._t.map, vertexColors: true }, extra);
  let m;
  if (Q.std) {
    m = new THREE.MeshStandardMaterial(Object.assign({ roughness: 1, metalness: d.metal, normalMap: d._t.normalMap, roughnessMap: d._t.roughnessMap }, opts));
    if (d._t.normalMap) m.normalScale.set(1, -1);
  } else m = new THREE.MeshLambertMaterial(opts);
  return (_matCache[id] = m);
}
const isWall = ch => ch === '#' || ch === 'w';
const isTall = ch => ch === '#' || ch === 'w' || ch === 'C' || ch === 'V' || ch === 'K';
const WALL_H = TOPS['#'];
const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];

function roofAtPt(x, z) {
  let s = 0, n = 0;
  for (const [ox, oz] of [[-0.02, -0.02], [0.02, -0.02], [-0.02, 0.02], [0.02, 0.02]]) {
    const cx = Math.floor((x + ox) / CELL), cz = Math.floor((z + oz) / CELL);
    if (isWall(cellCh(cx, cz))) continue;
    n++; if (areaAt(cx, cz).roof) s++;
  }
  return n ? s / n : 0;
}
// затенение пола у препятствий
function floorAO(x, z) {
  let ao = 1;
  const cx = Math.floor(x / CELL), cz = Math.floor(z / CELL);
  for (let oz = -1; oz <= 1; oz++) for (let ox = -1; ox <= 1; ox++) {
    const ch = cellCh(cx + ox, cz + oz); if (ch === '.') continue;
    const ins = INSET[ch] || 0;
    const x0 = (cx + ox) * CELL + ins, x1 = (cx + ox + 1) * CELL - ins, z0 = (cz + oz) * CELL + ins, z1 = (cz + oz + 1) * CELL - ins;
    const dx = Math.max(x0 - x, 0, x - x1), dz = Math.max(z0 - z, 0, z - z1), d = Math.hypot(dx, dz);
    const tall = isTall(ch), R = tall ? 1.3 : 0.7, k = tall ? 0.5 : 0.38;
    ao = Math.min(ao, 1 - k * (1 - smooth(0, R, d)));
  }
  return ao;
}
const INDOOR = 0.55;

function buildFloor(group) {
  const Q = GFX[gfxLevel()], by = {};
  const col = new THREE.Color();
  for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
    const ch = cellCh(cx, cz); if (isWall(ch)) continue;
    const a = areaAt(cx, cz), key = a.floor === 'concrete' ? 'floorc' : a.floor;
    const gb = by[key] || (by[key] = new GB());
    const k = Q.sub, s = CELL / k, base = gb.vc;
    for (let j = 0; j <= k; j++) for (let i = 0; i <= k; i++) {
      const x = cx * CELL + i * s, z = cz * CELL + j * s;
      const ao = floorAO(x, z), roof = roofAtPt(x, z);
      col.setRGB(1, 1, 1).multiplyScalar(ao * (1 - roof * (1 - INDOOR)));
      gb.v(x, 0, z, 0, 1, 0, x / MATDEF[key].size, -z / MATDEF[key].size, col);
    }
    for (let j = 0; j < k; j++) for (let i = 0; i < k; i++) {
      const a0 = base + j * (k + 1) + i, a1 = a0 + 1, a2 = a0 + k + 1, a3 = a2 + 1;
      gb.quad(a2, a3, a1, a0);
    }
  }
  for (const key in by) {
    const m = new THREE.Mesh(by[key].build(), levelMat(key));
    m.receiveShadow = true; group.add(m); levelMeshes.push(m);
  }
}

function buildWalls(group) {
  const by = {}, col = new THREE.Color();
  const tintOf = { concrete: 0xd8d4cc, brick: 0xffffff, metal: 0x9fb3bd, plaster: 0xffffff };
  for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
    const ch = cellCh(cx, cz); if (!isWall(ch)) continue;
    const winAxisZ = ch === 'w' && !isWall(cellCh(cx, cz - 1)) && !isWall(cellCh(cx, cz + 1));
    for (const [dx, dz] of DIRS) {
      const nx = cx + dx, nzc = cz + dz;
      if (nx < 0 || nzc < 0 || nx >= MW || nzc >= MH) continue;
      const nch = cellCh(nx, nzc); if (isWall(nch)) continue;
      const area = areaAt(nx, nzc), key = area.wall;
      const gb = by[key] || (by[key] = new GB());
      const nrm = [dx, 0, dz], t = [dz, 0, -dx];        // t = up × n
      const ox = (cx + 0.5 + dx * 0.5) * CELL - t[0] * CELL / 2, oz = (cz + 0.5 + dz * 0.5) * CELL - t[2] * CELL / 2;
      const ts = MATDEF[key].size;
      const roofK = area.roof ? INDOOR + 0.1 : 1;
      // соседи слева/справа перед стеной: внутренний угол → затенение кромки
      const leftC = isTall(cellCh(nx - t[0], nzc - t[2])), rightC = isTall(cellCh(nx + t[0], nzc + t[2]));
      const lowFront = nch !== '.' ? 0.8 : 1;
      const tint = hexC(tintOf[key] || 0xffffff);
      const hasWin = ch === 'w' && (winAxisZ ? dz !== 0 : dx !== 0);
      const xs = [0, 0.7, CELL - 0.7, CELL], ys = [0, 0.45, 1.3, WALL_H];
      const aoAt = (a, y) => {
        let k = 0.55 + 0.45 * smooth(0, 1.3, y);
        if (a < 0.7 && leftC) k *= 0.72 + 0.28 * smooth(0, 0.7, a);
        if (a > CELL - 0.7 && rightC) k *= 0.72 + 0.28 * smooth(0, 0.7, CELL - a);
        if (y < 1.2) k *= lowFront;
        return k * roofK;
      };
      const U0 = ox * t[0] + oz * t[2];
      const quadRect = (a0, a1, y0, y1, xsplit, ysplit) => {
        const xa = [a0, ...xsplit.filter(a => a > a0 && a < a1), a1], ya = [y0, ...ysplit.filter(y => y > y0 && y < y1), y1];
        const base = gb.vc;
        for (const y of ya) for (const a of xa) {
          col.copy(tint).multiplyScalar(aoAt(a, y));
          gb.v(ox + t[0] * a, y, oz + t[2] * a, nrm[0], 0, nrm[2], (U0 + a) / ts, y / ts, col);
        }
        const W = xa.length;
        for (let j = 0; j < ya.length - 1; j++) for (let i = 0; i < W - 1; i++) {
          const p0 = base + j * W + i; gb.quad(p0, p0 + 1, p0 + W + 1, p0 + W);
        }
      };
      if (!hasWin) quadRect(0, CELL, 0, WALL_H, xs, ys);
      else {
        const J = 0.35;
        quadRect(0, CELL, 0, WIN.lo, xs, ys); quadRect(0, CELL, WIN.hi, WALL_H, xs, ys);
        quadRect(0, J, WIN.lo, WIN.hi, [], []); quadRect(CELL - J, CELL, WIN.lo, WIN.hi, [], []);
        if (dx + dz > 0) {
          // откосы проёма: подоконник, перемычка, боковины
          const ax = winAxisZ ? 0 : 1, cxw = cx * CELL, czw = cz * CELL;
          const c = tint.clone().multiplyScalar(0.8 * roofK);
          const P = (u, y, w) => ax ? [cxw + w, y, czw + u] : [cxw + u, y, czw + w]; // u — вдоль стены, w — сквозь
          const face = (pts, n) => {
            const e1 = new THREE.Vector3().fromArray(pts[1]).sub(new THREE.Vector3().fromArray(pts[0])), e2 = new THREE.Vector3().fromArray(pts[2]).sub(new THREE.Vector3().fromArray(pts[0]));
            if (e1.cross(e2).dot(new THREE.Vector3().fromArray(n)) < 0) pts.reverse();
            const b = gb.vc; for (const p of pts) gb.v(p[0], p[1], p[2], n[0], n[1], n[2], (p[0] + p[2]) / ts, p[1] / ts, c); gb.quad(b, b + 1, b + 2, b + 3);
          };
          const u0 = J, u1 = CELL - J;
          const up = [0, 1, 0], dn = [0, -1, 0];
          face([P(u0, WIN.lo, CELL), P(u1, WIN.lo, CELL), P(u1, WIN.lo, 0), P(u0, WIN.lo, 0)].map(p => p), up);
          face([P(u0, WIN.hi, 0), P(u1, WIN.hi, 0), P(u1, WIN.hi, CELL), P(u0, WIN.hi, CELL)], dn);
          const nL = ax ? [0, 0, 1] : [1, 0, 0], nR = ax ? [0, 0, -1] : [-1, 0, 0];
          face([P(u0, WIN.lo, 0), P(u0, WIN.lo, CELL), P(u0, WIN.hi, CELL), P(u0, WIN.hi, 0)], nL);
          face([P(u1, WIN.lo, CELL), P(u1, WIN.lo, 0), P(u1, WIN.hi, 0), P(u1, WIN.hi, CELL)], nR);
        }
      }
    }
  }
  for (const key in by) {
    const m = new THREE.Mesh(by[key].build(), levelMat(key));
    m.castShadow = m.receiveShadow = true; group.add(m); levelMeshes.push(m);
  }
}

// крыши помещений: потолок + светильники
function buildRoofs(group, props) {
  const gb = new GB(), col = hexC(0xffffff, 0.5);
  const lamp = hexC(0xfff1d6);
  for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
    if (isWall(cellCh(cx, cz)) || !areaAt(cx, cz).roof) continue;
    const x0 = cx * CELL, z0 = cz * CELL, x1 = x0 + CELL, z1 = z0 + CELL, y = WALL_H;
    const b = gb.vc;
    gb.v(x0, y, z0, 0, -1, 0, x0 / 2.5, z0 / 2.5, col); gb.v(x1, y, z0, 0, -1, 0, x1 / 2.5, z0 / 2.5, col);
    gb.v(x1, y, z1, 0, -1, 0, x1 / 2.5, z1 / 2.5, col); gb.v(x0, y, z1, 0, -1, 0, x0 / 2.5, z1 / 2.5, col);
    gb.quad(b, b + 1, b + 2, b + 3);
    // балки
    if (cx % 2 === 0) gb.box(x0 + 1.15, y - 0.35, z0, x0 + 1.35, y, z1, hexC(0x8a8f92, 0.5), 1);
    // светильник через клетку
    if ((cx + cz) % 2 === 0) props.emis.box(x0 + 0.55, y - 0.4, z0 + 1.05, x1 - 0.55, y - 0.37, z1 - 1.05, lamp, 1);
    // скаты кровли сверху (виден издалека с ящиков и снаружи)
    const t = gb.vc, top = hexC(0x6b6e70, 0.8);
    gb.v(x0, y + 0.02, z1, 0, 1, 0, 0, 0, top); gb.v(x1, y + 0.02, z1, 0, 1, 0, 1, 0, top);
    gb.v(x1, y + 0.02, z0, 0, 1, 0, 1, 1, top); gb.v(x0, y + 0.02, z0, 0, 1, 0, 0, 1, top);
    gb.quad(t, t + 1, t + 2, t + 3);
  }
  const m = new THREE.Mesh(gb.build(), levelMat('concrete'));
  m.castShadow = m.receiveShadow = true; group.add(m); levelMeshes.push(m);
}

/* ---------------- препятствия и пропсы ---------------- */
function comps(chSet) {
  // прямоугольные связные группы клеток одного типа
  const seen = new Uint8Array(MW * MH), out = [];
  for (let z = 0; z < MH; z++) for (let x = 0; x < MW; x++) {
    const ch = cellCh(x, z);
    if (seen[z * MW + x] || !chSet.includes(ch)) continue;
    let x1 = x; while (cellCh(x1 + 1, z) === ch && !seen[z * MW + x1 + 1]) x1++;
    let z1 = z; outer: while (true) { for (let k = x; k <= x1; k++) if (cellCh(k, z1 + 1) !== ch || seen[(z1 + 1) * MW + k]) break outer; z1++; }
    for (let zz = z; zz <= z1; zz++) for (let xx = x; xx <= x1; xx++) seen[zz * MW + xx] = 1;
    out.push({ ch, x0: x, z0: z, x1, z1 });
  }
  return out;
}
const cellTint = (cx, cz) => areaAt(cx, cz).roof ? INDOOR + 0.15 : 1;
const CONT_COLS = [0x2f5f7a, 0x9a3a25, 0x4f6d3c, 0x9b7b2f, 0x6a6f72, 0x7a2f3a];
const BARREL_COLS = [0x2d4f7c, 0x8c2f22, 0x4b5a2f, 0x9a6a1e, 0x3b3f42];

function buildObstacles(group, P) {
  const Q = GFX[gfxLevel()];
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), v = new THREE.Vector3();
  for (const c of comps(['C', 'V', 'K', 'c', 'h', 'b'])) {
    const ch = c.ch, x0 = c.x0 * CELL, z0 = c.z0 * CELL, x1 = (c.x1 + 1) * CELL, z1 = (c.z1 + 1) * CELL;
    const tk = cellTint(c.x0, c.z0), ins = INSET[ch], H = TOPS[ch];
    const hseed = _hash(c.x0, c.z0, 77);
    if (ch === 'C') {
      // контейнеры: по длинной стороне, полосами шириной в клетку
      const alongX = (c.x1 - c.x0) >= (c.z1 - c.z0);
      const strips = alongX ? c.z1 - c.z0 + 1 : c.x1 - c.x0 + 1;
      for (let k = 0; k < strips; k++) {
        const col = hexC(CONT_COLS[Math.floor(_hash(c.x0 + k, c.z0, 3) * CONT_COLS.length)], tk);
        const a0 = alongX ? x0 + ins : x0 + k * CELL + ins, a1 = alongX ? x1 - ins : x0 + (k + 1) * CELL - ins;
        const b0 = alongX ? z0 + k * CELL + ins : z0 + ins, b1 = alongX ? z0 + (k + 1) * CELL - ins : z1 - ins;
        P.cont.box(a0, 0.12, b0, a1, H - 0.08, b1, col, 2.5, 0.75);
        // рама: угловые стойки, верхние и нижние балки
        const fc = hexC(0x2b2d2e, tk), e = 0.12;
        for (const [px, pz] of [[a0, b0], [a1 - e, b0], [a0, b1 - e], [a1 - e, b1 - e]]) P.paint.box(px - 0.01, 0, pz - 0.01, px + e + 0.01, H, pz + e + 0.01, fc, 1);
        P.paint.box(a0, 0, b0, a1, 0.14, b1, fc, 1);
        P.paint.box(a0 - 0.01, H - 0.1, b0 - 0.01, a1 + 0.01, H, b1 + 0.01, col.clone().multiplyScalar(0.85), 1);
        // двери с торца: запорные штанги
        const endX = alongX ? a1 + 0.02 : null, endZ = alongX ? null : b1 + 0.02;
        for (let r = 1; r <= 4; r++) {
          const f = r / 5;
          if (alongX) P.paint.box(endX - 0.04, 0.3, b0 + (b1 - b0) * f - 0.03, endX, H - 0.3, b0 + (b1 - b0) * f + 0.03, fc, 1);
          else P.paint.box(a0 + (a1 - a0) * f - 0.03, 0.3, endZ - 0.04, a0 + (a1 - a0) * f + 0.03, H - 0.3, endZ, fc, 1);
        }
      }
    } else if (ch === 'V') {
      // грузовик: кабина + фургон + колёса; ось по длинной стороне
      const alongX = (c.x1 - c.x0) >= (c.z1 - c.z0);
      const L = alongX ? x1 - x0 : z1 - z0, Wd = CELL - 2 * ins;
      const cxm = (x0 + x1) / 2, czm = (z0 + z1) / 2;
      q.setFromAxisAngle(V3(0, 1, 0), (alongX ? 0 : Math.PI / 2) + (hseed > 0.5 ? 0 : Math.PI));
      const place = (g, lx, ly, lz, col, mat) => { m4.compose(v.set(cxm, 0, czm), q, s.set(1, 1, 1)); m4.multiply(new THREE.Matrix4().makeTranslation(lx, ly, lz)); P[mat].geo(g, m4, col, 1); };
      const body = hexC([0xd9d6cf, 0x8a2b20, 0x2f4f6a][Math.floor(hseed * 3)], tk), cab = hexC([0x3a5f7a, 0xb7b2a6, 0x7a2a22][Math.floor(hseed * 3)], tk);
      const trailerL = L - 2.3;
      place(new THREE.BoxGeometry(trailerL, 2.2, Wd), -L / 2 + trailerL / 2, 0.3 + 1.1 + 0.05, 0, body, 'cont');
      place(new THREE.BoxGeometry(1.9, 1.75, Wd - 0.1), L / 2 - 1.05, 0.55 + 0.85, 0, cab, 'paint');
      place(new THREE.BoxGeometry(0.08, 0.75, Wd - 0.35), L / 2 - 0.08, 1.85, 0, hexC(0x161a1d), 'glass');
      place(new THREE.BoxGeometry(1.2, 0.08, Wd - 0.4), L / 2 - 1.2, 2.33, 0, cab.clone().multiplyScalar(0.8), 'paint');
      place(new THREE.BoxGeometry(L - 0.2, 0.25, Wd - 0.5), 0, 0.45, 0, hexC(0x222324), 'paint');
      place(new THREE.BoxGeometry(0.12, 0.3, Wd), L / 2 + 0.02, 0.6, 0, hexC(0x5a5c5e), 'paint');
      for (const wx of [L / 2 - 1.2, -L / 2 + 1.0, -L / 2 + 2.1]) for (const wz of [-1, 1]) {
        const wg = new THREE.CylinderGeometry(0.5, 0.5, 0.36, Q.std ? 16 : 10); wg.rotateX(Math.PI / 2);
        place(wg, wx, 0.5, wz * (Wd / 2 - 0.2), hexC(0x1c1c1c), 'paint');
      }
    } else if (ch === 'K') {
      // будка охраны
      const a0 = x0 + ins, a1 = x1 - ins, b0 = z0 + ins, b1 = z1 - ins;
      const wc = hexC(0xdedbd2, tk), stripe = hexC(0x2f5677, tk);
      P.paint.box(a0, 0, b0, a1, 1.0, b1, wc, 1, 0.7);
      P.paint.box(a0 - 0.005, 0.85, b0 - 0.005, a1 + 0.005, 1.0, b1 + 0.005, stripe, 1);
      P.glass.box(a0 + 0.04, 1.0, b0 + 0.04, a1 - 0.04, 2.25, b1 - 0.04, hexC(0x20292e), 1);
      for (const [px, pz] of [[a0, b0], [a1 - 0.1, b0], [a0, b1 - 0.1], [a1 - 0.1, b1 - 0.1]]) P.paint.box(px, 1.0, pz, px + 0.1, 2.25, pz + 0.1, wc, 1);
      P.paint.box(a0, 2.25, b0, a1, 2.55, b1, wc, 1);
      P.paint.box(a0 - 0.25, 2.55, b0 - 0.25, a1 + 0.25, H, b1 + 0.25, hexC(0x3d4043, tk), 1);
      P.emis.box((a0 + a1) / 2 - 0.12, H, (b0 + b1) / 2 - 0.12, (a0 + a1) / 2 + 0.12, H + 0.18, (b0 + b1) / 2 + 0.12, hexC(0xff9a3a), 1);
    } else if (ch === 'c') {
      for (let zz = c.z0; zz <= c.z1; zz++) for (let xx = c.x0; xx <= c.x1; xx++) {
        const a0 = xx * CELL + ins, b0 = zz * CELL + ins, a1 = (xx + 1) * CELL - ins, b1 = (zz + 1) * CELL - ins;
        const k = (0.85 + _hash(xx, zz, 4) * 0.25) * cellTint(xx, zz);
        P.wood.box(a0, 0, b0, a1, H, b1, hexC(0xffffff, k), CELL - 2 * ins, 0.7);
        // поддон под ящиком
        P.wood.box(a0 - 0.04, 0, b0 - 0.04, a1 + 0.04, 0.12, b1 + 0.04, hexC(0x9a8a70, k * 0.8), 1);
      }
    } else if (ch === 'h') {
      for (let zz = c.z0; zz <= c.z1; zz++) for (let xx = c.x0; xx <= c.x1; xx++) {
        const a0 = xx * CELL + ins, b0 = zz * CELL + ins, a1 = (xx + 1) * CELL - ins, b1 = (zz + 1) * CELL - ins;
        const tkk = cellTint(xx, zz), road = /road|lane/.test(areaAt(xx, zz).id);
        if (road) {
          // бетонные блоки «джерси» в три ряда + полосатая лента
          const along = !(cellCh(xx, zz - 1) === 'h' || cellCh(xx, zz + 1) === 'h');
          for (let r = 0; r < 3; r++) {
            const w = (along ? b1 - b0 : a1 - a0) / 3, o0 = (along ? b0 : a0) + r * w;
            const prof = new THREE.Shape();
            prof.moveTo(-w / 2, 0); prof.lineTo(w / 2, 0); prof.lineTo(w / 2 - 0.08, 0.22); prof.lineTo(w * 0.18, H - 0.02); prof.lineTo(-w * 0.18, H - 0.02); prof.lineTo(-w / 2 + 0.08, 0.22); prof.lineTo(-w / 2, 0);
            const len = along ? a1 - a0 : b1 - b0;
            const g = new THREE.ExtrudeGeometry(prof, { depth: len, bevelEnabled: false });
            m4.makeRotationY(along ? Math.PI / 2 : 0);
            m4.setPosition(along ? a0 : o0 + w / 2, 0, along ? o0 + w / 2 : b0);
            P.concreteP.geo(g, m4, hexC(0xd8d5cc, tkk * (0.9 + 0.1 * _hash(xx, r, 2))), 0.4);
          }
        } else if (Q.bags) {
          // мешки с песком
          const along = !(cellCh(xx, zz - 1) === 'h' || cellCh(xx, zz + 1) === 'h');
          const L = along ? a1 - a0 : b1 - b0, D = along ? b1 - b0 : a1 - a0;
          const layers = 3, nL = 4, nD = 2, bh = H / layers;
          for (let ly = 0; ly < layers; ly++) for (let i = 0; i < nL + (ly % 2 ? -1 : 0); i++) for (let j = 0; j < nD; j++) {
            const bl = L / nL, bd = D / nD;
            const li = (ly % 2 ? bl / 2 : 0) + i * bl + bl / 2, dj = j * bd + bd / 2;
            const g = rboxR(bl * 0.98, bh * 1.05, bd * 0.96, 0.12);
            const jx = (_hash(xx * 7 + i, zz * 3 + ly, j) - 0.5) * 0.05;
            m4.makeRotationY((jx) * 2);
            const px = along ? a0 + li : a0 + dj, pz = along ? b0 + dj : b0 + li;
            m4.setPosition(px, ly * bh + bh / 2, pz);
            P.bag.geo(g, m4, hexC(0xffffff, tkk * (0.85 + 0.25 * _hash(i, j, ly + xx))), 1);
          }
        } else P.bag.box(a0, 0, b0, a1, H, b1, hexC(0xffffff, tkk), 1, 0.7);
      }
    } else if (ch === 'b') {
      for (let zz = c.z0; zz <= c.z1; zz++) for (let xx = c.x0; xx <= c.x1; xx++) {
        const tkk = cellTint(xx, zz);
        for (const [ox, oz] of [[0.65, 0.65], [1.85, 0.7], [0.7, 1.85], [1.8, 1.8]]) {
          const bx = xx * CELL + ox + (_hash(xx, zz, ox * 10) - 0.5) * 0.12, bz = zz * CELL + oz + (_hash(zz, xx, oz * 10) - 0.5) * 0.12;
          const col = hexC(BARREL_COLS[Math.floor(_hash(bx * 10 | 0, bz * 10 | 0, 1) * BARREL_COLS.length)], tkk);
          const seg = Q.std ? 18 : 10;
          m4.makeTranslation(bx, H / 2, bz);
          P.paint.geo(new THREE.CylinderGeometry(0.5, 0.5, H, seg, 1), m4, col, 1);
          for (const ry of [0.25, 0.6, 0.95]) {
            m4.makeTranslation(bx, ry * H, bz);
            P.paint.geo(new THREE.CylinderGeometry(0.515, 0.515, 0.04, seg, 1, true), m4, col.clone().multiplyScalar(0.8), 1);
          }
          m4.makeTranslation(bx, H + 0.005, bz);
          P.paint.geo(new THREE.CylinderGeometry(0.47, 0.47, 0.01, seg, 1), m4, col.clone().multiplyScalar(0.7), 1);
        }
      }
    }
  }
}
// скруглённый брусок (как rbox из geometry.js, но тот подключается позже)
function rboxR(w, h, d, r) {
  r = Math.min(r, w / 2, h / 2, d / 2) * 0.999;
  const g = new THREE.BoxGeometry(w, h, d, 2, 2, 2), p = g.attributes.position, n = g.attributes.normal;
  const ix = w / 2 - r, iy = h / 2 - r, iz = d / 2 - r, v = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    c.set(clamp(v.x, -ix, ix), clamp(v.y, -iy, iy), clamp(v.z, -iz, iz));
    v.sub(c);
    if (v.lengthSq() > 1e-12) { v.normalize(); n.setXYZ(i, v.x, v.y, v.z); v.multiplyScalar(r); }
    p.setXYZ(i, c.x + v.x, c.y + v.y, c.z + v.z);
  }
  return g;
}

/* ---------------- декор: лампы, мачты, заборы, шлагбаумы, трубы ---------------- */
// проходимая клетка → грань стены в направлении (dx, dz)
function wallFace(cx, cz, dx, dz) {
  if (!walkable(cx, cz) && !'chb'.includes(cellCh(cx, cz))) return null;
  if (!isWall(cellCh(cx + dx, cz + dz))) return null;
  return { x: (cx + 0.5 + dx * 0.5) * CELL, z: (cz + 0.5 + dz * 0.5) * CELL, nx: -dx, nz: -dz };
}
const LAMP_SPOTS = [];
function buildDecor(group, P) {
  const Q = GFX[gfxLevel()];
  const m4 = new THREE.Matrix4(), dark = hexC(0x2a2d2f), steel = hexC(0x7d8386), lampC = hexC(0xffe7bf);
  // настенные фонари на открытых участках
  for (let cz = 1; cz < MH - 1; cz++) for (let cx = 1; cx < MW - 1; cx++) {
    if (!walkable(cx, cz) || areaAt(cx, cz).roof) continue;
    for (const [dx, dz] of DIRS) {
      const f = wallFace(cx, cz, dx, dz); if (!f) continue;
      if (_hash(cx, cz, dx * 3 + dz + 9) > 0.16) continue;
      if (LAMP_SPOTS.some(l => Math.hypot(l.x - f.x, l.z - f.z) < 9)) continue;
      // корпус: along — вдоль стены, out — от стены
      const wb = (gbx, out0, out1, along, y0, y1, col) => {
        const a = f.x + f.nx * out0, b = f.z + f.nz * out0, a2 = f.x + f.nx * out1, b2 = f.z + f.nz * out1;
        if (f.nx) gbx.box(Math.min(a, a2), y0, f.z - along, Math.max(a, a2), y1, f.z + along, col, 1);
        else gbx.box(f.x - along, y0, Math.min(b, b2), f.x + along, y1, Math.max(b, b2), col, 1);
      };
      wb(P.paint, 0, 0.5, 0.05, 3.55, 3.62, dark);
      wb(P.paint, 0.3, 0.8, 0.24, 3.45, 3.6, dark);
      wb(P.emis, 0.34, 0.76, 0.2, 3.43, 3.45, lampC);
      const px = f.x, pz = f.z;
      LAMP_SPOTS.push({ x: px + f.nx * 1.4, z: pz + f.nz * 1.4, x0: f.x, z0: f.z });
    }
  }
  // забор-сетка с колючкой поверх внешних стен
  const fence = new GB(), wire = hexC(0x55595b);
  for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
    if (!isWall(cellCh(cx, cz))) continue;
    const outer = cx <= 1 || cz === 0 || cx >= MW - 2 || cz === MH - 1;
    if (!outer) continue;
    for (const [dx, dz] of DIRS) {
      const nx = cx + dx, nzc = cz + dz;
      if (nx < 0 || nzc < 0 || nx >= MW || nzc >= MH || isWall(cellCh(nx, nzc))) continue;
      const t = [dz, 0, -dx], back = 0.25;
      const ox = (cx + 0.5 + dx * (0.5 - back)) * CELL - t[0] * CELL / 2, oz = (cz + 0.5 + dz * (0.5 - back)) * CELL - t[2] * CELL / 2;
      const y0 = WALL_H, y1 = WALL_H + 1.7, b = fence.vc, w = hexC(0xffffff);
      fence.v(ox, y0, oz, dx, 0, dz, 0, 0, w); fence.v(ox + t[0] * CELL, y0, oz + t[2] * CELL, dx, 0, dz, 2.5, 0, w);
      fence.v(ox + t[0] * CELL, y1, oz + t[2] * CELL, dx, 0, dz, 2.5, 1.7, w); fence.v(ox, y1, oz, dx, 0, dz, 0, 1.7, w);
      fence.quad(b, b + 1, b + 2, b + 3);
      P.paint.box(ox - 0.04, y0, oz - 0.04, ox + 0.04, y1 + 0.35, oz + 0.04, wire, 1);
      for (const wy of [y1 + 0.12, y1 + 0.3]) {
        const xa = Math.min(ox, ox + t[0] * CELL), xb = Math.max(ox, ox + t[0] * CELL), za = Math.min(oz, oz + t[2] * CELL), zb = Math.max(oz, oz + t[2] * CELL);
        P.paint.box(xa - 0.01, wy, za - 0.01, xb + 0.01, wy + 0.02, zb + 0.01, wire, 1);
      }
    }
  }
  const fenceTex = tex(64, 64, (g, w, h) => {
    g.clearRect(0, 0, w, h); g.strokeStyle = 'rgba(150,156,158,1)'; g.lineWidth = 3;
    g.beginPath(); for (let i = -64; i < 128; i += 16) { g.moveTo(i, 0); g.lineTo(i + 64, 64); g.moveTo(i + 64, 0); g.lineTo(i, 64); } g.stroke();
  }, null);
  fenceTex.repeat.set(1 / 0.5, 1 / 0.5);
  const fm = Q.std ? new THREE.MeshStandardMaterial({ map: fenceTex, alphaTest: 0.5, side: THREE.DoubleSide, metalness: 0.6, roughness: 0.5 })
    : new THREE.MeshLambertMaterial({ map: fenceTex, alphaTest: 0.5, side: THREE.DoubleSide });
  const fmesh = new THREE.Mesh(fence.build(), fm); fmesh.castShadow = true; group.add(fmesh);

  // прожекторные мачты по углам и у трассы
  for (const [cx, cz] of [[1, 0], [MW - 2, 0], [1, MH - 1], [MW - 2, MH - 1], [26, 0], [26, MH - 1], [0, 15], [MW - 1, 14]]) {
    const x = (cx + 0.5) * CELL, z = (cz + 0.5) * CELL, Hm = 13;
    m4.makeTranslation(x, Hm / 2, z);
    P.paint.geo(new THREE.CylinderGeometry(0.12, 0.22, Hm, 8), m4, steel, 1);
    P.paint.box(x - 1.2, Hm, z - 0.08, x + 1.2, Hm + 0.12, z + 0.08, steel, 1);
    for (const ox of [-1, -0.35, 0.35, 1]) {
      P.paint.box(x + ox - 0.25, Hm + 0.12, z - 0.2, x + ox + 0.25, Hm + 0.6, z + 0.2, dark, 1);
      const dz = cz === 0 ? 1 : cz === MH - 1 ? -1 : 0, dx = cx === 0 ? 1 : cx === MW - 1 ? -1 : 0;
      P.emis.box(x + ox - 0.2 + dx * 0.26, Hm + 0.17, z - 0.15 + dz * 0.21, x + ox + 0.2 + dx * 0.26, Hm + 0.55, z + 0.15 + dz * 0.21, lampC, 1);
    }
  }
  // шлагбаумы (подняты): стойка у стены, стрела в красно-белую полоску
  for (const [x, z, ang] of [[16 * CELL + 0.3, 5 * CELL - 0.3, 0], [16 * CELL + 0.3, 25 * CELL + 0.3, Math.PI], [27.5 * CELL, 14 * CELL, -Math.PI / 2]]) {
    P.paint.box(x - 0.18, 0, z - 0.18, x + 0.18, 1.05, z + 0.18, hexC(0xd9d3c4), 1);
    P.paint.box(x - 0.22, 0.95, z - 0.22, x + 0.22, 1.1, z + 0.22, hexC(0xb3261e), 1);
    const th = 1.3, arm = new THREE.Vector3(Math.cos(th), Math.sin(th), 0).applyAxisAngle(V3(0, 1, 0), ang);
    const qa = new THREE.Quaternion().setFromUnitVectors(V3(0, 1, 0), arm);
    for (let i = 0; i < 6; i++) {
      const r = 0.4 + i * 0.8;
      m4.makeRotationFromQuaternion(qa); m4.setPosition(x + arm.x * r, 1.05 + arm.y * r, z + arm.z * r);
      P.paint.geo(new THREE.BoxGeometry(0.1, 0.8, 0.1), m4, hexC(i % 2 ? 0xe8e4dc : 0xc4261c), 1);
    }
  }
  // трубы и кабель-каналы вдоль стен склада
  for (let cz = 1; cz < MH - 1; cz++) for (let cx = 1; cx < MW - 1; cx++) {
    if (areaAt(cx, cz).id !== 'warehouse' || !walkable(cx, cz)) continue;
    for (const [dx, dz] of DIRS) {
      const f = wallFace(cx, cz, dx, dz); if (!f) continue;
      const ax = Math.abs(f.nx) > 0, o = 0.18;
      const px = f.x + f.nx * o, pz = f.z + f.nz * o;
      const g = new THREE.CylinderGeometry(0.09, 0.09, CELL, 8); g.rotateZ(Math.PI / 2); if (ax) g.rotateY(Math.PI / 2);
      m4.makeTranslation(px, 3.65, pz);
      P.paint.geo(g, m4, hexC(0x6f7a5a, INDOOR + 0.2), 1);
      const g2 = new THREE.BoxGeometry(ax ? 0.12 : CELL, 0.12, ax ? CELL : 0.12);
      m4.makeTranslation(f.x + f.nx * 0.08, 3.35, f.z + f.nz * 0.08);
      P.paint.geo(g2, m4, hexC(0x3a3d40, INDOOR + 0.2), 1);
    }
  }
  // поддоны и мелочь у стен (без столкновений, низкие)
  for (let cz = 1; cz < MH - 1; cz++) for (let cx = 1; cx < MW - 1; cx++) {
    if (!walkable(cx, cz) || _hash(cx, cz, 55) > 0.07) continue;
    let face = null; for (const [dx, dz] of DIRS) { face = wallFace(cx, cz, dx, dz); if (face) break; }
    if (!face) continue;
    const px = face.x + face.nx * 0.65, pz = face.z + face.nz * 0.65, tk = cellTint(cx, cz);
    const n = 1 + Math.floor(_hash(cx, cz, 56) * 3);
    for (let i = 0; i < n; i++) {
      const y = i * 0.14;
      P.wood.box(px - 0.6, y, pz - 0.5, px + 0.6, y + 0.03, pz + 0.5, hexC(0xb49a72, tk), 1);
      for (const o of [-0.45, 0, 0.45]) P.wood.box(px - 0.6, y + 0.03, pz + o - 0.05, px + 0.6, y + 0.11, pz + o + 0.05, hexC(0x8a7350, tk), 1);
      P.wood.box(px - 0.6, y + 0.11, pz - 0.5, px + 0.6, y + 0.14, pz + 0.5, hexC(0xb49a72, tk), 1);
    }
  }
  // рамы окон
  for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
    if (cellCh(cx, cz) !== 'w') continue;
    const x0 = cx * CELL, z0 = cz * CELL, J = 0.35, mid = z0 + CELL / 2;
    P.paint.box(x0 + J, WIN.lo, mid - 0.04, x0 + CELL - J, WIN.lo + 0.06, mid + 0.04, dark, 1);
    P.paint.box(x0 + J, WIN.hi - 0.06, mid - 0.04, x0 + CELL - J, WIN.hi, mid + 0.04, dark, 1);
    P.paint.box(x0 + CELL / 2 - 0.03, WIN.lo, mid - 0.04, x0 + CELL / 2 + 0.03, WIN.hi, mid + 0.04, dark, 1);
  }
}

/* ---------------- надписи «А», «Б», стрелки ---------------- */
const SIGNS = [
  // cx, cz — проходимая клетка, dx, dz — где стена, kind — слот атласа, s — размер
  [8, 9, 0, 1, 0, 2.0], [12, 1, 0, -1, 0, 2.2], [16, 9, 0, 0, 0, 0], [3, 10, 0, 0, 0, 0],
  [8, 20, 0, -1, 1, 2.0], [12, 28, 0, 1, 1, 2.2],
  [44, 5, 0, 0, 0, 0],
  [42, 4, 0, 1, 2, 1.4], [38, 12, 1, 0, 2, 1.3], [38, 17, 1, 0, 5, 1.3], [42, 19, 1, 0, 5, 1.3],
  [21, 12, -1, 0, 2, 1.2], [24, 18, -1, 0, 5, 1.2], [15, 12, 0, -1, 2, 1.2], [15, 17, 0, 1, 5, 1.2],
  [33, 24, 1, 0, 5, 1.2], [28, 25, 0, -1, 5, 1.2], [6, 12, 0, -1, 3, 1.2], [6, 17, 0, 1, 4, 1.2],
  [30, 1, 0, -1, 6, 2.6], [20, 9, 0, 1, 7, 2.4], [29, 20, 0, -1, 7, 2.4],
];
function signAtlas() {
  return tex(512, 512, (g) => {
    const slot = (i, draw) => { g.save(); g.translate((i % 4) * 128, Math.floor(i / 4) * 128); draw(); g.restore(); };
    const letter = (L, arrow) => () => {
      g.fillStyle = '#1d3b33'; g.fillRect(6, 6, 116, 116);
      g.strokeStyle = '#e9e4d6'; g.lineWidth = 5; g.strokeRect(12, 12, 104, 104);
      g.fillStyle = '#f2cb4c'; g.font = 'bold ' + (arrow ? 64 : 88) + 'px "Russo One", Arial Black, sans-serif';
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(L, 64, arrow ? 50 : 68);
      if (arrow) {
        g.fillStyle = '#e9e4d6'; g.save(); g.translate(64, 98); if (arrow < 0) g.scale(-1, 1);
        g.beginPath(); g.moveTo(-34, -6); g.lineTo(14, -6); g.lineTo(14, -16); g.lineTo(36, 0); g.lineTo(14, 16); g.lineTo(14, 6); g.lineTo(-34, 6); g.closePath(); g.fill(); g.restore();
      }
    };
    slot(0, letter('А', 0)); slot(1, letter('Б', 0));
    slot(2, letter('А', -1)); slot(3, letter('А', 1)); slot(4, letter('Б', -1)); slot(5, letter('Б', 1));
    // широкие таблички: строка 2 и 3 целиком
    const plate = (row, text, bg, fg) => {
      g.save(); g.translate(0, row * 128);
      g.fillStyle = bg; g.fillRect(4, 20, 504, 88); g.strokeStyle = fg; g.lineWidth = 4; g.strokeRect(12, 28, 488, 72);
      g.fillStyle = fg; g.font = 'bold 46px "Russo One", Arial Black, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, 256, 66);
      g.restore();
    };
    plate(2, 'ТАМОЖЕННЫЙ ПОСТ', '#24426a', '#eef0ea');
    plate(3, 'ДОСМОТР · СКЛАД', '#6a2a1f', '#f1e6cf');
  });
}
function buildSigns(group) {
  const gb = new GB(), w = hexC(0xffffff);
  for (const [cx, cz, dx, dz, kind, s] of SIGNS) {
    if (!s) continue;
    const f = wallFace(cx, cz, dx, dz); if (!f) continue;
    const wide = kind >= 6, hw = wide ? s : s / 2, hh = wide ? s * 88 / 504 / 1 : s / 2;
    let u0, v0, u1, v1;
    if (!wide) { u0 = (kind % 4) / 4; u1 = u0 + 0.25; v1 = 1 - Math.floor(kind / 4) / 4; v0 = v1 - 0.25; }
    else { const row = kind === 6 ? 2 : 3; u0 = 0; u1 = 1; v1 = 1 - (row * 128 + 20) / 512; v0 = 1 - (row * 128 + 108) / 512; }
    const t = [f.nz, 0, -f.nx];                 // вправо, если смотреть на стену
    const tt = t;
    const cy = wide ? 3.3 : 2.4, px = f.x + f.nx * 0.03, pz = f.z + f.nz * 0.03;
    const b = gb.vc;
    gb.v(px - tt[0] * hw, cy - hh, pz - tt[2] * hw, f.nx, 0, f.nz, u0, v0, w);
    gb.v(px + tt[0] * hw, cy - hh, pz + tt[2] * hw, f.nx, 0, f.nz, u1, v0, w);
    gb.v(px + tt[0] * hw, cy + hh, pz + tt[2] * hw, f.nx, 0, f.nz, u1, v1, w);
    gb.v(px - tt[0] * hw, cy + hh, pz - tt[2] * hw, f.nx, 0, f.nz, u0, v1, w);
    gb.quad(b, b + 1, b + 2, b + 3);
  }
  const t = signAtlas(); t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  const m = new THREE.Mesh(gb.build(), new THREE.MeshStandardMaterial({ map: t, roughness: 0.7, metalness: 0, polygonOffset: true, polygonOffsetFactor: -2 }));
  group.add(m);
}

/* ---------------- слой разметки и грязи на полу (одна текстура на всю карту) ---------------- */
function buildOverlay(group) {
  const Q = GFX[gfxLevel()], pc = Q.overlay, W = MW * pc, H = MH * pc, mpp = pc / CELL;
  const t = tex(W, H, (g) => {
    g.clearRect(0, 0, W, H);
    const X = x => x * mpp, Z = z => z * mpp;
    const r = (a, b) => a + Math.random() * (b - a);
    // грязь у стен и пятна
    for (let cz = 0; cz < MH; cz++) for (let cx = 0; cx < MW; cx++) {
      if (isWall(cellCh(cx, cz))) continue;
      if (Math.random() < 0.22) {
        const x = (cx + Math.random()) * pc, y = (cz + Math.random()) * pc, rr = r(0.3, 1.4) * pc;
        const gr = g.createRadialGradient(x, y, 0, x, y, rr);
        const oil = Math.random() < 0.4;
        gr.addColorStop(0, oil ? 'rgba(12,10,8,.35)' : 'rgba(60,48,32,.22)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
        g.fillStyle = gr; g.fillRect(x - rr, y - rr, rr * 2, rr * 2);
      }
      for (const [dx, dz] of DIRS) {
        if (!isWall(cellCh(cx + dx, cz + dz))) continue;
        const ex = dx > 0 ? (cx + 1) * pc : cx * pc, ez = dz > 0 ? (cz + 1) * pc : cz * pc;
        const d = pc * 0.28;
        let gr;
        if (dx) gr = g.createLinearGradient(ex, 0, ex - dx * d, 0); else gr = g.createLinearGradient(0, ez, 0, ez - dz * d);
        gr.addColorStop(0, 'rgba(48,40,28,.32)'); gr.addColorStop(1, 'rgba(48,40,28,0)');
        g.fillStyle = gr;
        if (dx) g.fillRect(Math.min(ex, ex - dx * d), cz * pc, d, pc); else g.fillRect(cx * pc, Math.min(ez, ez - dz * d), pc, d);
      }
    }
    // трещины
    g.strokeStyle = 'rgba(15,13,10,.28)'; g.lineWidth = Math.max(1, pc / 64);
    for (let i = 0; i < MW * MH / 10; i++) {
      const [cx, cz] = openCells[Math.floor(Math.random() * openCells.length)];
      let x = (cx + Math.random()) * pc, y = (cz + Math.random()) * pc, a = Math.random() * 6.28;
      g.beginPath(); g.moveTo(x, y);
      for (let k = 0; k < 6; k++) { a += r(-0.7, 0.7); x += Math.cos(a) * pc * 0.18; y += Math.sin(a) * pc * 0.18; g.lineTo(x, y); }
      g.stroke();
    }
    // разметка трасс: осевая и края
    const dash = (x0, z0, x1, z1, col, w, d) => { g.strokeStyle = col; g.lineWidth = w * mpp; g.setLineDash(d ? d.map(v => v * mpp) : []); g.beginPath(); g.moveTo(X(x0), Z(z0)); g.lineTo(X(x1), Z(z1)); g.stroke(); g.setLineDash([]); };
    dash(16.5 * CELL, 2.5 * CELL, 46 * CELL, 2.5 * CELL, 'rgba(236,200,80,.75)', 0.14, [3, 2.5]);
    dash(17 * CELL, 1 * CELL + 0.4, 46 * CELL, 1 * CELL + 0.4, 'rgba(235,235,228,.6)', 0.12);
    dash(16.5 * CELL, 27 * CELL, 46 * CELL, 27 * CELL, 'rgba(236,200,80,.7)', 0.14, [3, 2.5]);
    // стоп-линии и «зебра» у КПП
    dash(17 * CELL, 1 * CELL, 17 * CELL, 5 * CELL, 'rgba(240,240,232,.7)', 0.4);
    for (let i = 0; i < 8; i++) g.fillStyle = 'rgba(238,236,226,.62)', g.fillRect(X(24.6 * CELL), Z(13 * CELL + 0.3 + i * 1.25), X(1.8), Z(0.62));
    for (const zc of [14, 15]) { g.fillStyle = 'rgba(236,200,80,.7)'; g.fillRect(X(26 * CELL), Z(zc * CELL + CELL / 2 - 0.06), X(3.2 * CELL), Z(0.12)); }
    // зоны точек: штрихованная граница и большая буква
    for (const s of SITES) {
      const inS = (x, z) => s.cells.some(c => c[0] === x && c[1] === z);
      g.fillStyle = 'rgba(214,82,46,.75)';
      for (const [x, z] of s.cells) {
        for (const [dx, dz] of DIRS) {
          if (inS(x + dx, z + dz) || isWall(cellCh(x + dx, z + dz))) continue;
          const bw = pc * 0.1;
          if (dx) g.fillRect(dx > 0 ? (x + 1) * pc - bw : x * pc, z * pc, bw, pc);
          else g.fillRect(x * pc, dz > 0 ? (z + 1) * pc - bw : z * pc, pc, bw);
        }
      }
      // круг закладки и буква
      const cx = s.center.x, cz = s.center.z;
      g.strokeStyle = 'rgba(214,82,46,.8)'; g.lineWidth = 0.2 * mpp;
      g.beginPath(); g.arc(X(cx), Z(cz), 3.2 * mpp, 0, Math.PI * 2); g.stroke();
      g.fillStyle = 'rgba(232,96,52,.7)'; g.font = 'bold ' + (4.2 * mpp | 0) + 'px "Russo One", Arial Black, sans-serif';
      g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(s.id === 'A' ? 'А' : 'Б', X(cx), Z(cz) + 0.2 * mpp);
    }
    // зоны появления: жёлто-чёрная рамка
    for (const team of ['A', 'B']) {
      const xs = spawns[team].map(p => p.x), zs = spawns[team].map(p => p.z);
      const x0 = Math.min(...xs) - CELL / 2, x1 = Math.max(...xs) + CELL / 2, z0 = Math.min(...zs) - CELL / 2, z1 = Math.max(...zs) + CELL / 2;
      g.strokeStyle = 'rgba(242,203,76,.75)'; g.lineWidth = 0.3 * mpp; g.setLineDash([0.6 * mpp, 0.6 * mpp]);
      g.strokeRect(X(x0), Z(z0), X(x1 - x0), Z(z1 - z0)); g.setLineDash([]);
    }
    // световые пятна под фонарями
    for (const l of LAMP_SPOTS) {
      const rr = 3.2 * mpp, gr = g.createRadialGradient(X(l.x), Z(l.z), 0, X(l.x), Z(l.z), rr);
      gr.addColorStop(0, 'rgba(255,226,170,.16)'); gr.addColorStop(1, 'rgba(255,226,170,0)');
      g.fillStyle = gr; g.fillRect(X(l.x) - rr, Z(l.z) - rr, rr * 2, rr * 2);
    }
  });
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping; t.anisotropy = 8;
  const geo = new THREE.PlaneGeometry(MW * CELL, MH * CELL);
  const mat = new (GFX[gfxLevel()].std ? THREE.MeshStandardMaterial : THREE.MeshLambertMaterial)(Object.assign({ map: t, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }, GFX[gfxLevel()].std ? { roughness: 0.9 } : {}));
  const m = new THREE.Mesh(geo, mat);
  m.rotation.x = -Math.PI / 2; m.position.set(MW * CELL / 2, 0.005, MH * CELL / 2); m.renderOrder = 1; m.receiveShadow = true;
  group.add(m);
}

/* ---------------- дальний план: краны, ангары, холмы ---------------- */
function buildFar(group) {
  const gb = new GB(), cx0 = MW * CELL / 2, cz0 = MH * CELL / 2;
  const haze = new THREE.Color(SKY), c = new THREE.Color();
  const add = (x0, y0, z0, x1, y1, z1, hex, light = 1) => {
    const d = Math.hypot((x0 + x1) / 2 - cx0, (z0 + z1) / 2 - cz0), k = clamp(1 - Math.exp(-d / 210), 0, 0.92);
    c.setHex(hex).multiplyScalar(light).lerp(haze, k);
    gb.box(x0, y0, z0, x1, y1, z1, c, 1);
  };
  const rnd = (a, b, s) => a + _hash(s, 3, 91) * (b - a);
  // ангары и склады по кругу
  for (let i = 0; i < 26; i++) {
    const a = i / 26 * Math.PI * 2 + rnd(-0.08, 0.08, i), R = rnd(115, 190, i + 50);
    const x = cx0 + Math.cos(a) * R, z = cz0 + Math.sin(a) * R * 0.85;
    const w = rnd(14, 34, i + 7), d = rnd(12, 26, i + 9), h = rnd(9, 22, i + 11);
    add(x - w / 2, 0, z - d / 2, x + w / 2, h, z + d / 2, [0x8c9393, 0x9b8f80, 0x7b8a8f, 0xa09a8a][i % 4], 0.9);
    if (i % 3 === 0) add(x - 1, h, z - 1, x + 1, h + rnd(6, 14, i + 2), z + 1, 0x7a7a74, 0.8);
  }
  // портальные краны
  for (const [x, z, rot] of [[cx0 - 150, cz0 - 70, 0], [cx0 + 120, cz0 - 110, 1], [cx0 + 165, cz0 + 40, 0]]) {
    const L = 26, H = 34;
    const p = (u, w) => rot ? [x + w, z + u] : [x + u, z + w];
    for (const [u, w] of [[-L / 2, -6], [L / 2, -6], [-L / 2, 6], [L / 2, 6]]) { const [px, pz] = p(u, w); add(px - 0.7, 0, pz - 0.7, px + 0.7, H, pz + 0.7, 0xb2462e, 0.95); }
    const [a0, b0] = p(-L / 2 - 10, -1.2), [a1, b1] = p(L / 2 + 22, 1.2);
    add(Math.min(a0, a1), H, Math.min(b0, b1), Math.max(a0, a1), H + 2.2, Math.max(b0, b1), 0xb2462e, 1);
    const [c0, d0] = p(-4, -4), [c1, d1] = p(4, 4);
    add(Math.min(c0, c1), H + 2.2, Math.min(d0, d1), Math.max(c0, c1), H + 6, Math.max(d0, d1), 0xd8d2c0, 1);
  }
  // водонапорная башня
  { const x = cx0 + 40, z = cz0 + 140; add(x - 0.6, 0, z - 0.6, x + 0.6, 28, z + 0.6, 0x77736a); const m4 = new THREE.Matrix4().makeTranslation(x, 31, z); c.setHex(0x8f8a7c).lerp(haze, 0.5); gb.geo(new THREE.CylinderGeometry(5, 4, 7, 12), m4, c); }
  // холмы
  const segs = 72, Rh = 330;
  for (let i = 0; i < segs; i++) {
    const a0 = i / segs * Math.PI * 2, a1 = (i + 1) / segs * Math.PI * 2;
    const h0 = 28 + 40 * nz(NZ.lo, i / segs, 0.3) + 14 * nz(NZ.mid, i / segs, 0.6), h1 = 28 + 40 * nz(NZ.lo, (i + 1) / segs, 0.3) + 14 * nz(NZ.mid, (i + 1) / segs, 0.6);
    const b = gb.vc; c.setHex(0x7d8a7a).lerp(haze, 0.7); const ct = c.clone().lerp(haze, 0.15);
    gb.v(cx0 + Math.cos(a0) * Rh, -2, cz0 + Math.sin(a0) * Rh, -Math.cos(a0), 0, -Math.sin(a0), 0, 0, c);
    gb.v(cx0 + Math.cos(a1) * Rh, -2, cz0 + Math.sin(a1) * Rh, -Math.cos(a1), 0, -Math.sin(a1), 0, 0, c);
    gb.v(cx0 + Math.cos(a1) * Rh, h1, cz0 + Math.sin(a1) * Rh, -Math.cos(a1), 0, -Math.sin(a1), 0, 0, ct);
    gb.v(cx0 + Math.cos(a0) * Rh, h0, cz0 + Math.sin(a0) * Rh, -Math.cos(a0), 0, -Math.sin(a0), 0, 0, ct);
    gb.quad(b, b + 3, b + 2, b + 1);
  }
  const m = new THREE.Mesh(gb.build(), new THREE.MeshBasicMaterial({ vertexColors: true, fog: false, side: THREE.DoubleSide }));
  group.add(m);
  // земля за пределами карты
  const out = new THREE.Mesh(new THREE.PlaneGeometry(900, 900), new THREE.MeshLambertMaterial({ color: 0x6d675b }));
  out.rotation.x = -Math.PI / 2; out.position.set(cx0, -0.03, cz0); group.add(out);
}

/* ---------------- применение настроек графики ---------------- */
let _shadowTick = 0;
_applyGfxImpl = function () {
  const Q = GFX[gfxLevel()];
  if (levelGroup) {
    scene.remove(levelGroup);
    levelGroup.traverse(o => { if (o.geometry) o.geometry.dispose(); });
  }
  levelMeshes.length = 0; LAMP_SPOTS.length = 0;
  for (const k in _matCache) delete _matCache[k];
  levelGroup = new THREE.Group(); levelGroup.name = 'level';
  // окружение и небо
  if (skyTex) skyTex.dispose();
  if (envRT) envRT.dispose();
  skyTex = buildSky(Q.sky);
  scene.background = skyTex;
  if (Q.std) {
    const pm = new THREE.PMREMGenerator(renderer);
    envRT = pm.fromEquirectangular(skyTex); pm.dispose();
    scene.environment = envRT.texture; vmScene.environment = envRT.texture;
    hemi.intensity = 0.4; sun.intensity = 1.9;
  } else {
    envRT = null; scene.environment = null; vmScene.environment = null;
    hemi.intensity = 0.95; sun.intensity = 1.9;
  }
  const P = {
    cont: new GB(), paint: new GB(), wood: new GB(), bag: new GB(), concreteP: new GB(), glass: new GB(), emis: new GB(),
  };
  buildFloor(levelGroup);
  buildWalls(levelGroup);
  buildRoofs(levelGroup, P);
  buildObstacles(levelGroup, P);
  buildDecor(levelGroup, P);
  buildSigns(levelGroup);
  buildOverlay(levelGroup);
  buildFar(levelGroup);
  const mats = {
    cont: levelMat('container'), paint: levelMat('paint'), wood: levelMat('wood'), bag: levelMat('bag'), concreteP: levelMat('concrete'),
    glass: Q.std ? new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.08, metalness: 0.9 }) : new THREE.MeshLambertMaterial({ vertexColors: true }),
    emis: new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false }),
  };
  for (const k in P) {
    if (!P[k].i.length) continue;
    const m = new THREE.Mesh(P[k].build(), mats[k]);
    if (k !== 'emis') { m.castShadow = m.receiveShadow = true; }
    // по пропсам работают попадания (декали, искры)
    if (k !== 'emis' && k !== 'glass') levelMeshes.push(m);
    else if (k === 'glass') levelMeshes.push(m);
    levelGroup.add(m);
  }
  scene.add(levelGroup);
  // тени от солнца
  const sh = settings.shadows === true && Q.std;
  renderer.shadowMap.enabled = sh;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  sun.castShadow = sh;
  if (sh) {
    const S = sun.shadow, ext = Math.hypot(MW * CELL, MH * CELL) / 2 + 4;
    S.mapSize.set(gfxLevel() === 'high' ? 4096 : 2048, gfxLevel() === 'high' ? 4096 : 2048);
    S.camera.left = -ext; S.camera.right = ext; S.camera.top = ext; S.camera.bottom = -ext;
    S.camera.near = 1; S.camera.far = 260; S.bias = -0.0004; S.normalBias = 0.03;
    S.camera.updateProjectionMatrix();
    if (S.map) { S.map.dispose(); S.map = null; }
  }
  // материалы сцены меняют набор шейдеров при включении теней
  scene.traverse(o => { if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.needsUpdate = true); } });
  _shadowTick = 0;
};
// бойцы и прочие динамические меши отбрасывают тень, когда тени включены
scene.onBeforeRender = () => {
  if (!renderer.shadowMap.enabled || (_shadowTick++ % 30)) return;
  scene.traverse(o => {
    if (!o.isMesh || o.castShadow || o.userData.noShadow) return;
    const m = o.material;
    if (!m || m.transparent || m.visible === false || m.isMeshBasicMaterial || m.isSpriteMaterial) { o.userData.noShadow = true; return; }
    if (levelGroup && o.parent === levelGroup) { o.userData.noShadow = true; return; }
    o.castShadow = true;
  });
};
}
applyGraphics();

// [интеграция] переключатели графики из настроек пересобирают уровень
bus.on('settings:gfx', () => { applyGraphics(); resize(); });
bus.on('settings:shadows', () => { applyGraphics(); resize(); });
