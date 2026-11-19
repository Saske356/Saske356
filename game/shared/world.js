// Общие данные мира: город, места, транспорт, коллизии.
// Этот модуль используется и сервером (Node.js), и клиентом (браузер).

export const GRID = 8;          // кварталов по каждой оси
export const BLOCK = 64;        // размер квартала, м
export const ROAD = 16;         // ширина дороги, м
export const CELL = BLOCK + ROAD;
export const SIZE = GRID * CELL + ROAD; // 656 м
export const SIDEWALK = 4;
export const LANE = 4;          // смещение полосы от оси дороги
export const CURB = 0.15;       // высота тротуара

export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const roadCenter = (i) => i * CELL + ROAD / 2;

export function blockRect(bx, bz) {
  const x0 = bx * CELL + ROAD, z0 = bz * CELL + ROAD;
  return { x0, z0, x1: x0 + BLOCK, z1: z0 + BLOCK };
}

// Высота поверхности: тротуары кварталов приподняты.
export function groundHeight(x, z) {
  const inside = (v) => {
    const i = Math.floor(v / CELL);
    return i >= 0 && i < GRID && v - i * CELL >= ROAD;
  };
  return inside(x) && inside(z) ? CURB : 0;
}

// ---------- Транспорт ----------
// maxSpeed в м/с, accel в м/с²
export const CARS = {
  kroha:  { name: 'Кроха',   price: 3000,  len: 3.6, wid: 1.7,  hgt: 1.45, maxSpeed: 30, accel: 8 },
  vektor: { name: 'Вектор',  price: 9000,  len: 4.5, wid: 1.85, hgt: 1.45, maxSpeed: 40, accel: 10 },
  taiga:  { name: 'Тайга',   price: 22000, len: 4.8, wid: 2.0,  hgt: 1.95, maxSpeed: 42, accel: 11 },
  bars:   { name: 'Барс',    price: 45000, len: 4.4, wid: 1.9,  hgt: 1.2,  maxSpeed: 58, accel: 16 },
  bus:    { name: 'Автобус', price: 0,     len: 11,  wid: 2.5,  hgt: 3.1,  maxSpeed: 22, accel: 5, job: true },
};
export const CAR_COLORS = [0xd94f3d, 0x2f6fd6, 0xf2f2f2, 0x1d1d1f, 0x3aa65b, 0xf0b429, 0x8e8e93, 0x7a3fd1];

export function carCircles(x, z, ry, model) {
  const m = CARS[model] || CARS.kroha;
  const n = Math.max(2, Math.ceil(m.len / m.wid));
  const r = m.wid / 2, span = m.len - m.wid, s = Math.sin(ry), c = Math.cos(ry);
  const out = [];
  for (let i = 0; i < n; i++) {
    const t = (i / (n - 1) - 0.5) * span;
    out.push({ x: x + s * t, z: z + c * t, r });
  }
  return out;
}

// ---------- Места ----------
const SP = blockRect(3, 3), SC = blockRect(2, 3), DL = blockRect(5, 2), CR = blockRect(1, 5), BP = blockRect(6, 6);

export const PLACES = {
  spawn:   { name: 'Центральная площадь', block: [3, 3], pos: [SP.x0 + 32, SP.z0 + 46], color: '#ffffff', hidden: true },
  rent:    { name: 'Аренда транспорта', block: [3, 3], pos: [SP.x0 + 10, SP.z0 + 3], color: '#4fc3f7',
             carSpawn: [SP.x0 + 10, SP.z0 - LANE, Math.PI / 2] },
  school:  { name: 'Автошкола', block: [2, 3], pos: [SC.x0 + 32, SC.z0 + 3], color: '#ffb74d' },
  dealer:  { name: 'Автосалон', block: [5, 2], pos: [DL.x0 + 32, DL.z0 + 3], color: '#ba68c8',
             carSpawn: [DL.x0 + 32, DL.z0 - LANE, Math.PI / 2] },
  courier: { name: 'Склад «Экспресс»', block: [1, 5], pos: [CR.x0 + 32, CR.z0 + 3], color: '#81c784' },
  bus:     { name: 'Автобусный парк', block: [6, 6], pos: [BP.x1 - 3, BP.z0 + 20], color: '#ffd54f',
             carSpawn: [roadCenter(7) - LANE, BP.z0 + 20, 0] },
};

export const PRICES = { rent: 100, license: 400 };

// Маршрут автобуса: кольцо по дорогам 1 и 7, остановки посередине кварталов.
export function busRoute() {
  const rc = roadCenter, mid = (a) => a * CELL + ROAD / 2 + CELL / 2, all = [];
  for (let a = 1; a <= 6; a++) all.push([mid(a), rc(1) + LANE]);      // +x по дороге z=1
  for (let a = 1; a <= 6; a++) all.push([rc(7) - LANE, mid(a)]);      // +z по дороге x=7
  for (let a = 6; a >= 1; a--) all.push([mid(a), rc(7) - LANE]);      // -x по дороге z=7
  for (let a = 6; a >= 1; a--) all.push([rc(1) + LANE, mid(a)]);      // -z по дороге x=1
  const stops = all.filter((_, i) => i % 2 === 0);
  return [...stops.slice(6), ...stops.slice(0, 6)]; // старт от автопарка
}

// Ближайшая точка на полосе дороги (для вызова личного авто).
export function nearestLane(x, z) {
  const clampI = (v) => Math.max(0, Math.min(GRID, Math.round((v - ROAD / 2) / CELL)));
  const ix = clampI(x), iz = clampI(z);
  const dx = Math.abs(x - roadCenter(ix)), dz = Math.abs(z - roadCenter(iz));
  const lim = (v) => Math.max(ROAD, Math.min(SIZE - ROAD, v));
  if (dx < dz) return { x: roadCenter(ix) - LANE, z: lim(z), ry: 0 };
  return { x: lim(x), z: roadCenter(iz) + LANE, ry: Math.PI / 2 };
}

// ---------- Генерация города ----------
const PALETTE = [0xc9b79c, 0xa7b1bd, 0xd6c7a1, 0x9fa8a3, 0xb98b73, 0xe0dcd2, 0x8c9aa8, 0xc4a484, 0x7d8b99, 0xd8b4a0];
export const BUILDING_COLORS = PALETTE;

export function generateCity(seed = 20261119) {
  const r = mulberry32(seed);
  const buildings = [], parks = [], trees = [], deliveries = [], decor = [], boxes = [];
  const special = {};
  for (const [id, p] of Object.entries(PLACES)) special[p.block.join(',')] ??= id;

  const addB = (b) => { buildings.push(b); boxes.push(b); return b; };
  const addTree = (x, z) => { trees.push([x, z]); boxes.push({ x0: x - 0.35, z0: z - 0.35, x1: x + 0.35, z1: z + 0.35, tree: true }); };
  const addDecorCar = (model, color, x, z, ry) => {
    decor.push({ model, color, x, z, ry });
    const m = CARS[model], h = Math.max(m.len, m.wid) * 0.45;
    const along = Math.abs(Math.sin(ry)) > 0.7;
    const hx = along ? m.len / 2 : m.wid / 2, hz = along ? m.wid / 2 : m.len / 2;
    boxes.push({ x0: x - Math.min(h, hx + 0.2), z0: z - Math.min(h, hz + 0.2), x1: x + Math.min(h, hx + 0.2), z1: z + Math.min(h, hz + 0.2) });
  };
  const pick = () => PALETTE[Math.floor(r() * PALETTE.length)];

  for (let bz = 0; bz < GRID; bz++) for (let bx = 0; bx < GRID; bx++) {
    const B = blockRect(bx, bz), sp = special[bx + ',' + bz];
    if (sp) { buildSpecial(sp, B); continue; }
    const center = 1 - Math.min(1, Math.hypot(bx - 3.5, bz - 3.5) / 5);
    const roll = r();
    const local = [];
    if (roll < 0.1) {
      parks.push(B);
      for (let i = 0; i < 10; i++) addTree(B.x0 + 8 + r() * 48, B.z0 + 8 + r() * 48);
    } else if (roll < 0.32) {
      const ins = 8 + r() * 6;
      local.push(addB({ x0: B.x0 + ins, z0: B.z0 + ins, x1: B.x1 - ins, z1: B.z1 - ins, h: 14 + r() * 16 + center * 45, color: pick() }));
    } else {
      for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
        const lx = B.x0 + SIDEWALK + i * 28, lz = B.z0 + SIDEWALK + j * 28;
        if (r() < 0.1) { addTree(lx + 14, lz + 14); continue; }
        const ins = 1 + r() * 3;
        local.push(addB({ x0: lx + ins, z0: lz + ins, x1: lx + 28 - ins, z1: lz + 28 - ins, h: 6 + r() * 12 + center * r() * 35, color: pick() }));
      }
    }
    // деревья вдоль тротуаров
    for (const t of [10, 26, 38, 54]) {
      if (r() < 0.3) addTree(B.x0 + t, B.z0 + 1.6);
      if (r() < 0.3) addTree(B.x0 + t, B.z1 - 1.6);
      if (r() < 0.3) addTree(B.x0 + 1.6, B.z0 + t);
      if (r() < 0.3) addTree(B.x1 - 1.6, B.z0 + t);
    }
    // адреса доставки — у входа в каждое здание
    for (const b of local) {
      const cx = (b.x0 + b.x1) / 2, cz = (b.z0 + b.z1) / 2;
      const d = [cx - B.x0, B.x1 - cx, cz - B.z0, B.z1 - cz], m = Math.min(...d);
      if (m === d[0]) deliveries.push([B.x0 + 2.5, cz]);
      else if (m === d[1]) deliveries.push([B.x1 - 2.5, cz]);
      else if (m === d[2]) deliveries.push([cx, B.z0 + 2.5]);
      else deliveries.push([cx, B.z1 - 2.5]);
    }
  }

  function buildSpecial(id, B) {
    if (id === 'spawn') {
      parks.push(B);
      boxes.push({ x0: B.x0 + 27.5, z0: B.z0 + 27.5, x1: B.x0 + 36.5, z1: B.z0 + 36.5, fountain: true });
      for (let a = 0; a < 12; a++) {
        const ang = (a / 12) * Math.PI * 2;
        addTree(B.x0 + 32 + Math.cos(ang) * 22, B.z0 + 32 + Math.sin(ang) * 22);
      }
    } else if (id === 'school') {
      addB({ x0: B.x0 + 10, z0: B.z0 + 26, x1: B.x1 - 10, z1: B.z1 - 8, h: 12, color: 0xe8d7a8, sign: 'АВТОШКОЛА' });
      addDecorCar('kroha', 0xf0b429, B.x0 + 14, B.z0 + 16, 0.3);
    } else if (id === 'dealer') {
      addB({ x0: B.x0 + 6, z0: B.z0 + 32, x1: B.x1 - 6, z1: B.z1 - 6, h: 9, color: 0xdfe6ee, sign: 'АВТОСАЛОН' });
      addDecorCar('vektor', 0x2f6fd6, B.x0 + 14, B.z0 + 20, 0.6);
      addDecorCar('bars', 0xd94f3d, B.x0 + 32, B.z0 + 21, 0);
      addDecorCar('taiga', 0x3aa65b, B.x0 + 50, B.z0 + 20, -0.6);
    } else if (id === 'courier') {
      addB({ x0: B.x0 + 8, z0: B.z0 + 22, x1: B.x1 - 8, z1: B.z1 - 6, h: 10, color: 0xb98b73, sign: 'СКЛАД «ЭКСПРЕСС»' });
    } else if (id === 'bus') {
      addB({ x0: B.x0 + 4, z0: B.z0 + 6, x1: B.x0 + 26, z1: B.z1 - 6, h: 9, color: 0x9fa8a3, sign: 'АВТОПАРК' });
      addDecorCar('bus', 0xf0b429, B.x0 + 36, B.z0 + 34, 0);
      addDecorCar('bus', 0xf0b429, B.x0 + 46, B.z0 + 34, 0);
    }
  }

  return { buildings, parks, trees, deliveries, decor, boxes };
}

// Выталкивание окружности из прямоугольников (AABB).
export function collideCircle(x, z, r, boxes) {
  let hit = false;
  for (const b of boxes) {
    if (x < b.x0 - r || x > b.x1 + r || z < b.z0 - r || z > b.z1 + r) continue;
    const cx = Math.max(b.x0, Math.min(x, b.x1)), cz = Math.max(b.z0, Math.min(z, b.z1));
    const dx = x - cx, dz = z - cz, d2 = dx * dx + dz * dz;
    if (d2 >= r * r) continue;
    hit = true;
    if (d2 > 1e-8) {
      const d = Math.sqrt(d2);
      x = cx + (dx / d) * r; z = cz + (dz / d) * r;
    } else {
      const l = x - b.x0, rr = b.x1 - x, t = z - b.z0, bb = b.z1 - z, m = Math.min(l, rr, t, bb);
      if (m === l) x = b.x0 - r; else if (m === rr) x = b.x1 + r; else if (m === t) z = b.z0 - r; else z = b.z1 + r;
    }
  }
  return { x, z, hit };
}

export function formatTime(min) {
  const h = Math.floor(min / 60) % 24, m = Math.floor(min % 60);
  return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
}
