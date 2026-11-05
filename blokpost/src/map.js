'use strict';
/* ---------------- карта «Терминал»: пограничный таможенный пункт ----------------
   Запад — защита (команда A по умолчанию), восток — атака (команда B).
   Точка А — досмотровая площадка на северо-западе, Точка Б — грузовой двор на юго-западе.
   Пути атаки: северная трасса (длинная линия) и офис досмотра к А; мид с площадью и КПП;
   склад и тоннель к Б; переулок между трассой и мидом на стороне атаки.

   Символы клеток:
     .  пол (проходимо)            #  стена 4.2 м
     w  стена с проёмом-окном (сквозь проём видно и можно стрелять)
     C  контейнер 2.6 м            V  грузовик 2.5 м
     K  будка охраны 2.8 м         c  ящик 1.1 м (можно запрыгнуть)
     h  бетонный блок/мешки 0.95 м (укрытие, через него видно стоя)
     b  бочки 1.2 м
*/
const CELL = 2.5;
const MAP_NAME = 'Терминал';
const RAW = [
  '################################################',
  '##....#........b.b....................cc.......#',
  '##....#..CC..................VVV...............#',
  '##.......CC.......................h............#',
  '##...................hh...........h.......c....#',
  '##..............##ww#w##w###########..#####...##',
  '##....#......cc...........##########..#####...##',
  '##....#......c......c.....##########..#####...##',
  '##....#.b..hh...........c.##########..#####...##',
  '##....#.........#.........##########..#####...##',
  '##....####...#########..############..#####...##',
  '#c.....###...#########..############..##......c#',
  '#......###...#########..##............##.......#',
  '#..............c...h.......K.........c.........#',
  '#..................h.........####..............#',
  '#............................####..............#',
  '#........c.................K.....cc............#',
  '#......###...###########............####.......#',
  '#.....c###...###########..##############b......#',
  '##....####...###########..#################...##',
  '##....#.........#.............c...#########...##',
  '##....#.b..h........#.......#.c...#########...##',
  '##....#....h.cc.......CC..........#########...##',
  '##....#......c....c.......b.......#########...##',
  '##..............###############..##########...##',
  '##...............###########..h..........c.....#',
  '##.......CC...................h................#',
  '##....#..CC...............b........VVV.........#',
  '##....#........c......b........................#',
  '################################################',
];
const MW = 48, MH = RAW.length;
const grid = RAW.map((r, y) => {
  let row = (r + '#'.repeat(MW)).slice(0, MW).split('');
  if (y === 0 || y === MH - 1) row = row.map(() => '#');
  row[0] = '#'; row[MW - 1] = '#';
  return row;
});
// высота верха препятствия
const TOPS = { '#': 4.2, 'w': 4.2, 'C': 2.6, 'V': 2.5, 'K': 2.8, 'c': 1.1, 'h': 0.95, 'b': 1.2 };
// проём в стене 'w': от WIN.lo до WIN.hi пусто
const WIN = { lo: 1.05, hi: 2.25 };
// отступ коллизии от края клетки (визуальная модель чуть меньше клетки)
const INSET = { '#': 0, 'w': 0, 'C': 0.06, 'V': 0.1, 'K': 0.12, 'c': 0.1, 'h': 0.12, 'b': 0.14 };

const cellCh = (cx, cz) => (cx < 0 || cz < 0 || cx >= MW || cz >= MH) ? '#' : grid[cz][cx];
const chAt = (x, z) => cellCh(Math.floor(x / CELL), Math.floor(z / CELL));
const walkable = (cx, cz) => cellCh(cx, cz) === '.';
const openCells = [];
grid.forEach((row, z) => row.forEach((ch, x) => { if (ch === '.') openCells.push([x, z]); }));
// закрывает ли клетка с символом ch луч на высоте y
function cellBlocks(ch, y) {
  if (ch === '.') return false;
  if (ch === 'w') return y < WIN.lo || (y > WIN.hi && y < TOPS.w);
  return TOPS[ch] > y;
}

/* ---------------- зоны появления ---------------- */
const spawns = { A: [], B: [] };
(function () {
  const add = (team, x0, z0, x1, z1) => {
    for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++)
      if ((x + z) % 2 === 0 && walkable(x, z)) spawns[team].push({ x: (x + 0.5) * CELL, z: (z + 0.5) * CELL });
  };
  add('A', 1, 12, 5, 17);   // защита: запад
  add('B', 41, 12, 45, 17); // атака: восток
})();

const RAD = 0.38, STEP = 0.45;
function collide(p, r) {
  const cx0 = Math.floor((p.x - r) / CELL), cx1 = Math.floor((p.x + r) / CELL);
  const cz0 = Math.floor((p.z - r) / CELL), cz1 = Math.floor((p.z + r) / CELL);
  for (let cz = cz0; cz <= cz1; cz++) for (let cx = cx0; cx <= cx1; cx++) {
    const ch = cellCh(cx, cz); if (ch === '.') continue;
    const top = TOPS[ch]; if (top <= p.y + STEP) continue;
    const ins = INSET[ch] || 0;
    const minX = cx * CELL + ins, maxX = (cx + 1) * CELL - ins, minZ = cz * CELL + ins, maxZ = (cz + 1) * CELL - ins;
    const nx = clamp(p.x, minX, maxX), nz = clamp(p.z, minZ, maxZ);
    const dx = p.x - nx, dz = p.z - nz, d2 = dx * dx + dz * dz;
    if (d2 >= r * r) continue;
    if (d2 > 1e-9) { const d = Math.sqrt(d2); p.x += dx / d * (r - d); p.z += dz / d * (r - d); }
    else {
      const pl = p.x - minX, pr = maxX - p.x, pt = p.z - minZ, pb = maxZ - p.z, m = Math.min(pl, pr, pt, pb);
      if (m === pl) p.x = minX - r; else if (m === pr) p.x = maxX + r; else if (m === pt) p.z = minZ - r; else p.z = maxZ + r;
    }
  }
}
// высота опоры под бойцом: верх препятствия, на которое он стоит/запрыгнул (пол проходимых клеток плоский, y = 0)
function groundAt(p, r) {
  let g = 0; const rr = r * 0.7;
  const cx0 = Math.floor((p.x - rr) / CELL), cx1 = Math.floor((p.x + rr) / CELL);
  const cz0 = Math.floor((p.z - rr) / CELL), cz1 = Math.floor((p.z + rr) / CELL);
  for (let cz = cz0; cz <= cz1; cz++) for (let cx = cx0; cx <= cx1; cx++) {
    const ch = cellCh(cx, cz); if (ch === '.') continue;
    const ins = INSET[ch] || 0;
    if (p.x < cx * CELL + ins - rr || p.x > (cx + 1) * CELL - ins + rr || p.z < cz * CELL + ins - rr || p.z > (cz + 1) * CELL - ins + rr) continue;
    const top = TOPS[ch]; if (top <= p.y + STEP && top > g) g = top;
  }
  return g;
}
function los(ax, ay, az, bx, by, bz) {
  const dx = bx - ax, dz = bz - az, dist = Math.hypot(dx, dz);
  const n = Math.ceil(dist / 0.3);
  for (let i = 1; i < n; i++) {
    const t = i / n;
    if (cellBlocks(chAt(ax + dx * t, az + dz * t), ay + (by - ay) * t)) return false;
  }
  return true;
}
// A* по клеткам с двоичной кучей
const _pf = { g: new Float32Array(MW * MH), from: new Int32Array(MW * MH), closed: new Uint8Array(MW * MH), heap: [], f: new Float32Array(MW * MH) };
function findPath(sx, sz, tx, tz) {
  if (!walkable(tx, tz)) return null;
  const { g, from, closed, f } = _pf, heap = _pf.heap;
  g.fill(1e9); from.fill(-1); closed.fill(0); heap.length = 0;
  const start = sz * MW + sx, goal = tz * MW + tx;
  if (start < 0 || start >= MW * MH) return null;
  const h = i => { const ax = Math.abs((i % MW) - tx), az = Math.abs(((i / MW) | 0) - tz); return Math.max(ax, az) + 0.414 * Math.min(ax, az); };
  const push = i => {
    heap.push(i); let k = heap.length - 1;
    while (k > 0) { const p = (k - 1) >> 1; if (f[heap[p]] <= f[i]) break; heap[k] = heap[p]; k = p; }
    heap[k] = i;
  };
  const pop = () => {
    const top = heap[0], last = heap.pop();
    if (heap.length) {
      let k = 0; const n = heap.length;
      for (;;) {
        let c = 2 * k + 1; if (c >= n) break;
        if (c + 1 < n && f[heap[c + 1]] < f[heap[c]]) c++;
        if (f[heap[c]] >= f[last]) break;
        heap[k] = heap[c]; k = c;
      }
      heap[k] = last;
    }
    return top;
  };
  g[start] = 0; f[start] = h(start); push(start);
  while (heap.length) {
    const cur = pop();
    if (closed[cur]) continue;
    if (cur === goal) break;
    closed[cur] = 1;
    const cx = cur % MW, cz = (cur / MW) | 0;
    for (let oz = -1; oz <= 1; oz++) for (let ox = -1; ox <= 1; ox++) {
      if (!ox && !oz) continue;
      const nx = cx + ox, nz = cz + oz;
      if (!walkable(nx, nz)) continue;
      if (ox && oz && (!walkable(cx + ox, cz) || !walkable(cx, cz + oz))) continue;
      const ni = nz * MW + nx; if (closed[ni]) continue;
      const ng = g[cur] + (ox && oz ? 1.414 : 1);
      if (ng < g[ni]) { g[ni] = ng; from[ni] = cur; f[ni] = ng + h(ni); push(ni); }
    }
  }
  if (from[goal] === -1 && goal !== start) return null;
  const path = []; let c = goal;
  while (c !== -1 && c !== start) { path.push([c % MW, (c / MW) | 0]); c = from[c]; }
  return path.reverse();
}

/* ---------------- точки закладки и зоны появления (контракт для режима «Подрыв») ---------------- */
// SITES: зоны, где атака закладывает заряд. cells — клетки сетки [x, z], center — мировые координаты.
const SITES = [
  { id: 'A', name: 'Точка А', cells: [], center: { x: 0, z: 0 }, rect: [7, 1, 15, 9] },
  { id: 'B', name: 'Точка Б', cells: [], center: { x: 0, z: 0 }, rect: [7, 20, 15, 28] },
];
const _siteAt = new Array(MW * MH).fill(null);
(function () {
  for (const s of SITES) {
    const [x0, z0, x1, z1] = s.rect;
    for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) if (walkable(x, z)) { s.cells.push([x, z]); _siteAt[z * MW + x] = s.id; }
    s.center.x = (x0 + x1 + 1) / 2 * CELL; s.center.z = (z0 + z1 + 1) / 2 * CELL;
  }
})();
// id точки, если мировая позиция внутри неё, иначе null
function inSite(x, z) {
  const cx = Math.floor(x / CELL), cz = Math.floor(z / CELL);
  if (cx < 0 || cz < 0 || cx >= MW || cz >= MH) return null;
  return _siteAt[cz * MW + cx];
}
// Стороны: 'def' — защита (команда A по умолчанию, запад), 'atk' — атака (команда B, восток).
const spawnZones = { def: spawns.A, atk: spawns.B };

// Открытое место для витрины меню: бойцы стоят у (x, z), камера в (camX, camZ) смотрит на них.
const MENU_SPOT = { x: 10, z: 30, camX: 7.5, camZ: 39 };

/* ---------------- зоны оформления (для render.js) ----------------
   Каждая проходимая клетка берёт первую подходящую зону: пол и материал стен, обращённых в эту клетку.
   roof — крытое помещение (потолок, приглушённый свет). */
const MAP_AREAS = [
  { id: 'office', rect: [16, 6, 25, 12], floor: 'tile', wall: 'plaster', roof: true },
  { id: 'warehouse', rect: [16, 17, 33, 24], floor: 'concrete', wall: 'metal', roof: true },
  { id: 'tunnel', rect: [17, 26, 27, 28], floor: 'concrete', wall: 'concrete', roof: true },
  { id: 'siteA', rect: [6, 1, 15, 9], floor: 'concrete', wall: 'brick' },
  { id: 'siteB', rect: [6, 20, 15, 28], floor: 'plates', wall: 'brick' },
  { id: 'plaza', rect: [24, 12, 37, 17], floor: 'pavers', wall: 'concrete' },
  { id: 'defbase', rect: [1, 1, 6, 28], floor: 'concrete', wall: 'concrete' },
  { id: 'road', rect: [16, 1, 46, 4], floor: 'asphalt', wall: 'concrete' },
  { id: 'lane', rect: [16, 25, 46, 28], floor: 'asphalt', wall: 'concrete' },
  { id: 'atkbase', rect: [38, 5, 46, 24], floor: 'asphalt', wall: 'metal' },
  { id: 'mid', rect: [0, 0, MW - 1, MH - 1], floor: 'pavers', wall: 'concrete' },
];
const _areaAt = new Array(MW * MH);
for (let z = 0; z < MH; z++) for (let x = 0; x < MW; x++)
  _areaAt[z * MW + x] = MAP_AREAS.find(a => x >= a.rect[0] && x <= a.rect[2] && z >= a.rect[1] && z <= a.rect[3]);
const areaAt = (cx, cz) => _areaAt[clamp(cz, 0, MH - 1) * MW + clamp(cx, 0, MW - 1)];
