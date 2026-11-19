import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { CARS } from '/shared/world.js';

const matCache = new Map();
export function mat(color) {
  if (!matCache.has(color)) matCache.set(color, new THREE.MeshLambertMaterial({ color }));
  return matCache.get(color);
}
const box = (w, h, d, m) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);

export const lightMats = {
  head: new THREE.MeshLambertMaterial({ color: 0xfff6d5, emissive: 0xfff2b0, emissiveIntensity: 0.3 }),
  tail: new THREE.MeshLambertMaterial({ color: 0x8a1010, emissive: 0xff2020, emissiveIntensity: 0.3 }),
};

const wheelGeos = {};
function wheelGeo(r) {
  if (!wheelGeos[r]) { const g = new THREE.CylinderGeometry(r, r, 0.3, 14); g.rotateZ(Math.PI / 2); wheelGeos[r] = g; }
  return wheelGeos[r];
}

// Машина собирается из коробок; перед смотрит в +Z.
// ---------- 3D-модели машин из кэша (cache/cars/*.glb) ----------
// Если моделей нет, makeCar рисует машину из коробок.
// Какие модели показывать для каждого класса машины (первая — основная, остальные — для трафика).
export const SKINS = {
  kroha: ['granta', 'logan', 'kiar'],
  vektor: ['vesta', 'focus'],
  taiga: ['patriota', 'lexuslx', 'mercesg'],
  bars: ['bmwmkf'],
  bus: ['bus'],
};
const protos = new Map(); // имя модели → { scene, info }
const paintCache = new Map();
const lodCars = new Set();
const LOD_DIST = 70; // дальше — простая коробка вместо детальной модели

let carIndex = {}, carBase = '/cache/cars';
const loading = new Map();
const gltf = new GLTFLoader();

/** Загрузить одну модель (если ещё не загружена). Возвращает true, если модель есть. */
export function loadSkin(name) {
  if (protos.has(name)) return Promise.resolve(true);
  if (!carIndex[name]) return Promise.resolve(false);
  if (!loading.has(name)) {
    loading.set(name, gltf.loadAsync(`${carBase}/${name}.glb`).then((g) => {
      g.scene.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = true;
        const m = o.material;
        if (m.name === 'light_front') o.material = lightMats.head;
        else if (m.name === 'light_rear') o.material = lightMats.tail;
        else if (/^paint/.test(m.name)) o.userData.paint = true;
      });
      protos.set(name, { scene: g.scene, info: carIndex[name] });
      return true;
    }).catch((e) => { console.warn('Модель не загрузилась:', name, e); return false; }));
  }
  return loading.get(name);
}
export const hasSkin = (name) => protos.has(name);
/** Все модели в кэше (для админ-панели): [{ id, name }]. */
export function availableCars() {
  return Object.keys(carIndex).sort().map((id) => ({ id, name: CAR_NAMES[id] || id }));
}

export async function loadCarModels(base = '/cache/cars') {
  carBase = base;
  try {
    const r = await fetch(`${base}/cars.json`, { cache: 'no-cache' });
    if (!r.ok) return 0;
    carIndex = await r.json();
  } catch { return 0; }
  await Promise.all([...new Set(Object.values(SKINS).flat())].map(loadSkin));
  return protos.size;
}

// Подписи моделей в админ-панели (остальные показываются по имени файла).
export const CAR_NAMES = {
  granta: 'Lada Granta', grantaf: 'Lada Granta FL', vesta: 'Lada Vesta', vestasw: 'Lada Vesta SW', logan: 'Renault Logan',
  kiar: 'Kia Rio', kiakf: 'Kia K5', focus: 'Ford Focus', patriota: 'УАЗ Патриот', patriotf: 'УАЗ Патриот пикап',
  patriotp: 'УАЗ Патриот (новый)', patriot: 'ГАЗ Тигр', lexuslx: 'Lexus LX', mercesg: 'Mercedes G 63', mercescls: 'Mercedes CLS',
  mercesgls: 'Mercedes GLS', merceseqs: 'Mercedes EQS', mercesm: 'Mercedes M', bmwmkf: 'BMW M8', bmwmgc: 'BMW M8 Gran Coupe',
  bmwmli: 'BMW 7 E38', bmwxma: 'BMW X7', bmwxka: 'BMW X5 E53', supra: 'Toyota Supra', huracan: 'Lamborghini Huracán',
  cullinan: 'Rolls-Royce Cullinan', phantom: 'Rolls-Royce Phantom', bentlgt: 'Bentley GT', teslas: 'Tesla Model S',
  teslax: 'Tesla Model X', ptaycan: 'Porsche Taycan', audirs: 'Audi RS7', audiq: 'Audi Q7', cadillac: 'Cadillac Escalade',
  divo: 'Bugatti Divo', jaguarxk: 'Jaguar XK120', vwstation: 'Volkswagen T1', ambulan: 'Mercedes Sprinter', bus: 'Автобус',
};

function paintMaterial(base, color) {
  const key = base.uuid + '|' + color;
  if (!paintCache.has(key)) {
    const m = base.clone();
    m.color.setHex(color);
    paintCache.set(key, m);
  }
  return paintCache.get(key);
}

function makeModelCar(model, color, skin) {
  const s = CARS[model] || CARS.kroha;
  const proto = protos.get(skin);
  const g = new THREE.Group();
  const hi = proto.scene.clone(true);
  const k = s.len / proto.info.len;
  hi.scale.setScalar(k);
  hi.position.y = -proto.info.bottom * k;
  const wheels = [];
  for (const node of [...hi.children]) {
    if (!/^wheel_/.test(node.name)) continue;
    // колесо крутим через отдельный узел — так ось одна и та же для левых и правых колёс
    const pivot = new THREE.Object3D();
    pivot.position.copy(node.position);
    node.position.set(0, 0, 0);
    hi.add(pivot);
    pivot.add(node);
    wheels.push(pivot);
  }
  hi.traverse((o) => { if (o.isMesh && o.userData.paint) o.material = paintMaterial(o.material, color); });
  // дальний план: одна коробка цвета кузова
  const lo = new THREE.Mesh(boxGeo, mat(color));
  lo.scale.set(s.wid * 0.92, s.hgt * 0.8, s.len * 0.97);
  lo.position.y = 0.25 + s.hgt * 0.4;
  lo.visible = false;
  g.add(hi, lo);
  g.userData = { wheels, wr: proto.info.wheel * k, hi, lo };
  lodCars.add(g);
  return g;
}
const boxGeo = new THREE.BoxGeometry(1, 1, 1);

/** Детальная модель рядом с камерой, коробка вдали. Вызывать раз в несколько кадров. */
export function updateCarLod(camera) {
  const p = camera.position, d2 = LOD_DIST * LOD_DIST, v = new THREE.Vector3();
  for (const g of lodCars) {
    if (!g.parent) { lodCars.delete(g); continue; }
    g.getWorldPosition(v);
    const far = v.distanceToSquared(p) > d2;
    g.userData.hi.visible = !far;
    g.userData.lo.visible = far;
  }
}

export function makeCar(model, color, skin) {
  const list = SKINS[model] || [];
  const name = skin && protos.has(skin) ? skin : list.find((n) => protos.has(n));
  if (name) return makeModelCar(model, color, name);
  return makeBoxCar(model, color);
}

function makeBoxCar(model, color) {
  const s = CARS[model] || CARS.kroha, g = new THREE.Group();
  const L = s.len, Wd = s.wid, H = s.hgt, paint = mat(color), glass = mat(0x1d2733), dark = mat(0x151515);
  let lightY;
  if (model === 'bus') {
    const b = box(Wd, H - 0.4, L, paint); b.position.y = 0.4 + (H - 0.4) / 2;
    const band = box(Wd + 0.04, 0.95, L - 1.4, glass); band.position.set(0, H - 0.8, -0.3);
    const ws = box(Wd - 0.3, 1.2, 0.06, glass); ws.position.set(0, H - 1.0, L / 2 + 0.01);
    const stripe = box(Wd + 0.03, 0.2, L + 0.02, mat(0xffffff)); stripe.position.y = 1.05;
    g.add(b, band, ws, stripe);
    lightY = 0.85;
  } else {
    const bodyH = H * 0.47;
    const b = box(Wd, bodyH, L, paint); b.position.y = 0.3 + bodyH / 2;
    const cabL = model === 'taiga' ? L * 0.62 : L * 0.5, cabH = H - bodyH - 0.3;
    const cz = model === 'taiga' ? -0.35 : -0.15;
    const cab = box(Wd * 0.84, cabH, cabL, paint); cab.position.set(0, 0.3 + bodyH + cabH / 2, cz);
    const win = box(Wd * 0.86, cabH * 0.62, cabL + 0.04, glass); win.position.set(0, 0.3 + bodyH + cabH * 0.42, cz);
    const bumper = box(Wd + 0.04, 0.16, L + 0.06, dark); bumper.position.y = 0.36;
    g.add(b, cab, win, bumper);
    lightY = 0.3 + bodyH * 0.65;
  }
  const wr = model === 'bus' ? 0.5 : model === 'taiga' ? 0.42 : 0.36, wz = model === 'bus' ? L / 2 - 2 : L / 2 - 0.8;
  const wheels = [];
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const w = new THREE.Mesh(wheelGeo(wr), dark);
    w.position.set(sx * (Wd / 2 - 0.12), wr, sz * wz);
    wheels.push(w); g.add(w);
  }
  for (const sx of [-1, 1]) {
    const h = box(0.36, 0.16, 0.06, lightMats.head); h.position.set(sx * (Wd / 2 - 0.3), lightY, L / 2 + 0.03);
    const t = box(0.36, 0.14, 0.06, lightMats.tail); t.position.set(sx * (Wd / 2 - 0.3), lightY, -L / 2 - 0.03);
    g.add(h, t);
  }
  g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  g.userData = { wheels, wr };
  return g;
}

export function randomSkin(model) {
  const list = (SKINS[model] || []).filter((n) => protos.has(n));
  return list.length ? list[Math.floor(Math.random() * list.length)] : undefined;
}

export function spinWheels(car, spd, dt) {
  for (const w of car.userData.wheels) w.rotation.x += (spd * dt) / car.userData.wr;
}

// Персонаж
export function colorFromString(s) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return new THREE.Color().setHSL((h % 360) / 360, 0.55, 0.5).getHex();
}

export function makePed(shirt, pants = 0x2b3a55, skin = 0xe0b48c) {
  const g = new THREE.Group();
  const legGeo = new THREE.BoxGeometry(0.22, 0.86, 0.24); legGeo.translate(0, -0.43, 0);
  const armGeo = new THREE.BoxGeometry(0.16, 0.64, 0.18); armGeo.translate(0, -0.32, 0);
  const lL = new THREE.Mesh(legGeo, mat(pants)), lR = new THREE.Mesh(legGeo, mat(pants));
  lL.position.set(-0.13, 0.9, 0); lR.position.set(0.13, 0.9, 0);
  const torso = box(0.56, 0.66, 0.3, mat(shirt)); torso.position.y = 1.23;
  const aL = new THREE.Mesh(armGeo, mat(shirt)), aR = new THREE.Mesh(armGeo, mat(shirt));
  aL.position.set(-0.37, 1.52, 0); aR.position.set(0.37, 1.52, 0);
  const head = box(0.3, 0.32, 0.3, mat(skin)); head.position.y = 1.75;
  const hair = box(0.32, 0.1, 0.32, mat(0x2a1c12)); hair.position.y = 1.93;
  g.add(lL, lR, torso, aL, aR, head, hair);
  g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  g.userData = { lL, lR, aL, aR, phase: 0 };
  return g;
}

export function animatePed(g, anim, dt) {
  const u = g.userData;
  let a = 0;
  if (anim) {
    u.phase += dt * (anim === 2 ? 12 : 8);
    a = Math.sin(u.phase) * (anim === 2 ? 0.9 : 0.55);
  } else {
    u.phase = 0;
  }
  const k = 1 - Math.exp(-dt * 15);
  u.lL.rotation.x += (a - u.lL.rotation.x) * k;
  u.lR.rotation.x += (-a - u.lR.rotation.x) * k;
  u.aL.rotation.x += (-a * 0.8 - u.aL.rotation.x) * k;
  u.aR.rotation.x += (a * 0.8 - u.aR.rotation.x) * k;
}

// Текст над головой / табличка
export function textSprite(text, { color = '#ffffff', size = 28, bg = null, scale = 0.012 } = {}) {
  const c = document.createElement('canvas'), g = c.getContext('2d');
  const font = `bold ${size}px "Segoe UI", Arial, sans-serif`;
  g.font = font;
  const w = Math.ceil(g.measureText(text).width) + 24;
  c.width = w; c.height = size + 18;
  g.font = font;
  if (bg) {
    g.fillStyle = bg;
    g.beginPath(); g.roundRect(0, 0, w, c.height, 10); g.fill();
  }
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineWidth = 5; g.strokeStyle = 'rgba(0,0,0,0.75)';
  g.strokeText(text, w / 2, c.height / 2 + 1);
  g.fillStyle = color;
  g.fillText(text, w / 2, c.height / 2 + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthWrite: false, transparent: true }));
  sp.scale.set(c.width * scale, c.height * scale, 1);
  return sp;
}

export function disposeSprite(sp) {
  sp.material.map.dispose();
  sp.material.dispose();
}
