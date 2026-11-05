'use strict';
/* ---------------- карта ---------------- */
const CELL = 2.5;
const RAW = [
  '################################',
  '#.......#..........c....#......#',
  '#..c....#..CC...........#......#',
  '#.......#..CC.....CCc.......c..#',
  '#.................CC...........#',
  '#.......#..............#.......#',
  '###..####...c....c...####..#####',
  '#.......#..............#.......#',
  '#.AAA...#...##....##...#..BBB..#',
  '#.AAA.......##....##......BBB..#',
  '#.AAA...#..............#..BBB..#',
  '#.......#...c....c.....#.......#',
  '###..####..............####..###',
  '#..........CC.....CC...........#',
  '#..c.......CC.....CC..c....c...#',
  '#......###............###......#',
  '#........#....cc....#..........#',
  '#...c....#....cc....#.....c....#',
  '#.......c......................#',
  '################################',
];
const MW = 32, MH = RAW.length;
const grid = RAW.map((r, y) => {
  let row = (r + '#'.repeat(MW)).slice(0, MW).split('');
  if (y === 0 || y === MH - 1) row = row.map(() => '#');
  row[0] = '#'; row[MW - 1] = '#';
  return row;
});
const TOPS = { '#': 4.2, 'C': 2.3, 'c': 1.1 };
const spawns = { A: [], B: [] };
grid.forEach((row, z) => row.forEach((ch, x) => {
  if (ch === 'A' || ch === 'B') { spawns[ch].push({ x: (x + 0.5) * CELL, z: (z + 0.5) * CELL }); row[x] = '.'; }
}));
const cellCh = (cx, cz) => (cx < 0 || cz < 0 || cx >= MW || cz >= MH) ? '#' : grid[cz][cx];
const chAt = (x, z) => cellCh(Math.floor(x / CELL), Math.floor(z / CELL));
const walkable = (cx, cz) => cellCh(cx, cz) === '.';
const openCells = [];
grid.forEach((row, z) => row.forEach((ch, x) => { if (ch === '.') openCells.push([x, z]); }));

const RAD = 0.38, STEP = 0.45;
function collide(p, r) {
  const cx0 = Math.floor((p.x - r) / CELL), cx1 = Math.floor((p.x + r) / CELL);
  const cz0 = Math.floor((p.z - r) / CELL), cz1 = Math.floor((p.z + r) / CELL);
  for (let cz = cz0; cz <= cz1; cz++) for (let cx = cx0; cx <= cx1; cx++) {
    const ch = cellCh(cx, cz); if (ch === '.') continue;
    const top = TOPS[ch]; if (top <= p.y + STEP) continue;
    const ins = ch === '#' ? 0 : 0.08;
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
function groundAt(p, r) {
  let g = 0; const rr = r * 0.7;
  const cx0 = Math.floor((p.x - rr) / CELL), cx1 = Math.floor((p.x + rr) / CELL);
  const cz0 = Math.floor((p.z - rr) / CELL), cz1 = Math.floor((p.z + rr) / CELL);
  for (let cz = cz0; cz <= cz1; cz++) for (let cx = cx0; cx <= cx1; cx++) {
    const ch = cellCh(cx, cz); if (ch === '.') continue;
    const top = TOPS[ch]; if (top <= p.y + STEP && top > g) g = top;
  }
  return g;
}
function los(ax, ay, az, bx, by, bz) {
  const dx = bx - ax, dz = bz - az, dist = Math.hypot(dx, dz);
  const n = Math.ceil(dist / 0.3);
  for (let i = 1; i < n; i++) {
    const t = i / n, ch = chAt(ax + dx * t, az + dz * t);
    if (ch !== '.' && TOPS[ch] > ay + (by - ay) * t) return false;
  }
  return true;
}
function findPath(sx, sz, tx, tz) {
  if (!walkable(tx, tz)) return null;
  const N = MW * MH, g = new Float32Array(N).fill(1e9), from = new Int32Array(N).fill(-1), closed = new Uint8Array(N);
  const start = sz * MW + sx, goal = tz * MW + tx;
  const open = [start]; g[start] = 0;
  const h = i => Math.hypot((i % MW) - tx, ((i / MW) | 0) - tz);
  while (open.length) {
    let bi = 0, bf = 1e9;
    for (let k = 0; k < open.length; k++) { const f = g[open[k]] + h(open[k]); if (f < bf) { bf = f; bi = k; } }
    const cur = open[bi]; open.splice(bi, 1);
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
      if (ng < g[ni]) { g[ni] = ng; from[ni] = cur; if (!open.includes(ni)) open.push(ni); }
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
  { id: 'A', name: 'Точка А', cells: [] , center: { x: 0, z: 0 } },
  { id: 'B', name: 'Точка Б', cells: [], center: { x: 0, z: 0 } },
];
(function () {
  const rects = { A: [9, 1, 15, 4], B: [12, 14, 19, 18] }; // x0, z0, x1, z1 включительно
  for (const s of SITES) {
    const [x0, z0, x1, z1] = rects[s.id];
    for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) if (walkable(x, z)) s.cells.push([x, z]);
    s.center.x = (x0 + x1 + 1) / 2 * CELL; s.center.z = (z0 + z1 + 1) / 2 * CELL;
  }
})();
// id точки, если мировая позиция внутри неё, иначе null
function inSite(x, z) {
  const cx = Math.floor(x / CELL), cz = Math.floor(z / CELL);
  for (const s of SITES) if (s.cells.some(c => c[0] === cx && c[1] === cz)) return s.id;
  return null;
}
// Стороны: 'def' — защита (появляется у spawns.A на этой карте), 'atk' — атака (spawns.B).
const spawnZones = { def: spawns.A, atk: spawns.B };
