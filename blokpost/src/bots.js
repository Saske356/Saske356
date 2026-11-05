'use strict';
/* ---------------- ИИ ботов ---------------- */
// Три слоя:
//  1) NAV — анализ карты при старте матча: поля расстояний от зон появления и точек, укрытия, входы на точки,
//     позиции удержания для защиты, места сбора для атаки, «середина» между точками. Всё считается по сетке
//     (walkable, los, SITES, spawnZones), поэтому работает на любой карте с этими контрактами.
//  2) Штаб команды (aiAttack / aiDefend / aiTdm) раз в ~0.35 с раздаёт бойцам приказы: куда идти, куда смотреть,
//     что делать на месте (держать угол, закладывать, разминировать, подбирать заряд, уходить от взрыва).
//  3) Боец (updateBot): восприятие с учётом ослепления (unit.flashT) и дыма (smokeBlocks), бой, выглядывание,
//     отход в укрытие при низком HP и для перезарядки, движение по своему пути с разведением от союзников, выход из застревания.
const aiStats = { stuck: 0, hardStuck: 0, nades: 0, retreats: 0, orders: 0 };
let NAV = null;
const AI = { tickT: 0, teams: { A: null, B: null } };

/* ---------- сетка ---------- */
const AI_NB = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, 1.414], [1, -1, 1.414], [-1, 1, 1.414], [-1, -1, 1.414]];
const aiX = i => (i % MW + 0.5) * CELL;
const aiZ = i => (((i / MW) | 0) + 0.5) * CELL;
const aiCellAt = (x, z) => clamp(Math.floor(z / CELL), 0, MH - 1) * MW + clamp(Math.floor(x / CELL), 0, MW - 1);
const aiOpen = i => i >= 0 && i < MW * MH && walkable(i % MW, (i / MW) | 0);
const aiWalkAt = (x, z) => walkable(Math.floor(x / CELL), Math.floor(z / CELL));
const aiDist = (i, x, z) => Math.hypot(aiX(i) - x, aiZ(i) - z);
function aiNearestOpen(i) {
  if (aiOpen(i)) return i;
  const cx = i % MW, cz = (i / MW) | 0;
  for (let r = 1; r < 8; r++) {
    let best = -1, bd = 1e9;
    for (let dz = -r; dz <= r; dz++) for (let dx = -r; dx <= r; dx++) {
      if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue;
      const x = cx + dx, z = cz + dz;
      if (walkable(x, z)) { const d = dx * dx + dz * dz; if (d < bd) { bd = d; best = z * MW + x; } }
    }
    if (best >= 0) return best;
  }
  return openCells.length ? openCells[0][1] * MW + openCells[0][0] : 0;
}
// двоичная куча для Дейкстры и A*
function AiHeap() { this.k = []; this.v = []; }
AiHeap.prototype.push = function (key, val) {
  const k = this.k, v = this.v; let i = k.length; k.push(key); v.push(val);
  while (i > 0) { const p = (i - 1) >> 1; if (k[p] <= key) break; k[i] = k[p]; v[i] = v[p]; i = p; }
  k[i] = key; v[i] = val;
};
AiHeap.prototype.pop = function () {
  const k = this.k, v = this.v, top = v[0], tk = k[0], lk = k.pop(), lv = v.pop();
  if (k.length) {
    let i = 0; const n = k.length;
    for (;;) { let c = 2 * i + 1; if (c >= n) break; if (c + 1 < n && k[c + 1] < k[c]) c++; if (k[c] >= lk) break; k[i] = k[c]; v[i] = v[c]; i = c; }
    k[i] = lk; v[i] = lv;
  }
  this.lastKey = tk; return top;
};
function aiStepOk(cx, cz, ox, oz) {
  if (!walkable(cx + ox, cz + oz)) return false;
  return !(ox && oz && (!walkable(cx + ox, cz) || !walkable(cx, cz + oz)));
}
// поле расстояний (в клетках) от набора клеток
function aiField(seeds) {
  const N = MW * MH, d = new Float32Array(N).fill(1e9), h = new AiHeap();
  for (const s of seeds) if (aiOpen(s) && d[s] > 0) { d[s] = 0; h.push(0, s); }
  while (h.k.length) {
    const c = h.pop(), f = h.lastKey; if (f > d[c]) continue;
    const cx = c % MW, cz = (c / MW) | 0;
    for (const [ox, oz, w] of AI_NB) {
      if (!aiStepOk(cx, cz, ox, oz)) continue;
      const ni = (cz + oz) * MW + cx + ox, nd = f + w;
      if (nd < d[ni]) { d[ni] = nd; h.push(nd, ni); }
    }
  }
  return d;
}
// A* со своим «шумом» стоимости у каждого бота — бойцы одной группы идут разными линиями, а не цепочкой
function aiPath(s, t, noise) {
  s = aiNearestOpen(s); t = aiNearestOpen(t);
  if (s === t) return [];
  const N = MW * MH, g = new Float32Array(N).fill(1e9), from = new Int32Array(N).fill(-1), h = new AiHeap();
  const tx = t % MW, tz = (t / MW) | 0;
  const H = i => { const dx = Math.abs(i % MW - tx), dz = Math.abs(((i / MW) | 0) - tz); return Math.max(dx, dz) + 0.414 * Math.min(dx, dz); };
  g[s] = 0; h.push(H(s), s);
  let found = false;
  while (h.k.length) {
    const c = h.pop();
    if (c === t) { found = true; break; }
    if (h.lastKey - H(c) > g[c] + 1e-4) continue;
    const cx = c % MW, cz = (c / MW) | 0;
    for (const [ox, oz, w] of AI_NB) {
      if (!aiStepOk(cx, cz, ox, oz)) continue;
      const ni = (cz + oz) * MW + cx + ox, ng = g[c] + w * (1 + (noise ? noise[ni] : 0));
      if (ng < g[ni]) { g[ni] = ng; from[ni] = c; h.push(ng + H(ni), ni); }
    }
  }
  if (!found) return null;
  const path = []; let c = t;
  while (c !== -1 && c !== s) { path.push(c); c = from[c]; }
  return path.reverse();
}
// свободен ли прямой проход шириной с бойца (для срезания углов пути)
function aiClear(ax, az, bx, bz) {
  const dx = bx - ax, dz = bz - az, L = Math.hypot(dx, dz); if (L < 0.01) return true;
  const n = Math.ceil(L / 0.35), px = -dz / L * 0.42, pz = dx / L * 0.42;
  for (let i = 1; i <= n; i++) {
    const t = i / n, x = ax + dx * t, z = az + dz * t;
    if (!aiWalkAt(x, z) || !aiWalkAt(x + px, z + pz) || !aiWalkAt(x - px, z - pz)) return false;
  }
  return true;
}
const aiSee = (i, x, z, h) => los(aiX(i), 1.6, aiZ(i), x, h === undefined ? 1.4 : h, z);
// спуск по полю: на steps клеток в сторону уменьшения
function aiDescend(i, field, steps) {
  for (let k = 0; k < steps; k++) {
    const cx = i % MW, cz = (i / MW) | 0; let best = i;
    for (const [ox, oz] of AI_NB) { if (!aiStepOk(cx, cz, ox, oz)) continue; const ni = (cz + oz) * MW + cx + ox; if (field[ni] < field[best]) best = ni; }
    if (best === i) break; i = best;
  }
  return i;
}
// жадный выбор лучших клеток с разносом
function aiSpread(cands, score, minGap, maxN) {
  const sc = cands.map(c => [c, score(c)]).filter(e => e[1] > -1e8).sort((a, b) => b[1] - a[1]);
  const out = [];
  for (const [c] of sc) {
    if (out.some(o => Math.hypot(aiX(o) - aiX(c), aiZ(o) - aiZ(c)) < minGap * CELL)) continue;
    out.push(c); if (out.length >= maxN) break;
  }
  return out;
}

/* ---------- анализ карты ---------- */
function aiPrepare() {
  const N = MW * MH, nav = { N, cover: new Uint8Array(N), coverList: [], sites: {}, siteIds: [] };
  for (let i = 0; i < N; i++) if (aiOpen(i)) {
    let c = 0; const cx = i % MW, cz = (i / MW) | 0;
    for (const [ox, oz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) if (!walkable(cx + ox, cz + oz)) c++;
    nav.cover[i] = c; if (c) nav.coverList.push(i);
  }
  const cellsOf = list => (list || []).map(p => aiNearestOpen(aiCellAt(p.x, p.z)));
  nav.dA = aiField(cellsOf(spawns.A)); nav.dB = aiField(cellsOf(spawns.B));
  const zAtk = typeof spawnZones !== 'undefined' && spawnZones.atk && spawnZones.atk.length ? spawnZones.atk : spawns.B;
  const zDef = typeof spawnZones !== 'undefined' && spawnZones.def && spawnZones.def.length ? spawnZones.def : spawns.A;
  nav.dAtk = aiField(cellsOf(zAtk)); nav.dDef = aiField(cellsOf(zDef));
  for (const s of (typeof SITES !== 'undefined' ? (typeof objSites === 'function' ? objSites() : SITES) : [])) {
    const cells = s.cells.map(c => c[1] * MW + c[0]).filter(aiOpen);
    if (!cells.length) continue;
    const dS = aiField(cells);
    let atkMin = 1e9; for (const c of cells) atkMin = Math.min(atkMin, nav.dAtk[c]);
    // входы: кольцо в 4–5 клетках от точки со стороны атаки, разбитое на связные куски
    const ring = new Set();
    for (let i = 0; i < N; i++) if (aiOpen(i) && dS[i] >= 3.5 && dS[i] < 5.6 && nav.dAtk[i] < atkMin + 1) ring.add(i);
    const comps = [], seen = new Set();
    for (const i of ring) {
      if (seen.has(i)) continue;
      const comp = [], st = [i]; seen.add(i);
      while (st.length) {
        const c = st.pop(); comp.push(c); const cx = c % MW, cz = (c / MW) | 0;
        for (const [ox, oz] of AI_NB) { const ni = (cz + oz) * MW + cx + ox; if (ring.has(ni) && !seen.has(ni)) { seen.add(ni); st.push(ni); } }
      }
      comps.push(comp);
    }
    let ents = comps.filter(c => c.length >= 2).map(comp => {
      let rep = comp[0]; for (const c of comp) if (nav.dAtk[c] < nav.dAtk[rep]) rep = c;
      return { rep, stage: aiDescend(rep, nav.dAtk, 3), size: comp.length };
    });
    if (!ents.length) { const c = aiDescend(cells[0], nav.dAtk, 5); ents = [{ rep: c, stage: aiDescend(c, nav.dAtk, 3), size: 1 }]; }
    ents.sort((a, b) => nav.dAtk[a.rep] - nav.dAtk[b.rep]);
    if (ents.length > 4) ents = ents.slice(0, 4);
    // позиции удержания защиты: у точки, с видом на вход, у укрытия
    const near = []; for (let i = 0; i < N; i++) if (aiOpen(i) && dS[i] <= 3.1) near.push(i);
    const holdInfo = new Map();
    for (const c of near) {
      let best = null, bd = 1e9, nVis = 0;
      for (const e of ents) {
        const d = Math.hypot(aiX(c) - aiX(e.rep), aiZ(c) - aiZ(e.rep));
        if (d < 5 || !aiSee(c, aiX(e.rep), aiZ(e.rep))) continue;
        nVis++; if (d < bd) { bd = d; best = e.rep; }
      }
      holdInfo.set(c, { watch: best, nVis, d: bd });
    }
    let holds = aiSpread(near, c => {
      const h = holdInfo.get(c); if (!h.watch) return -1e9;
      return h.nVis * 2.5 + Math.min(nav.cover[c], 2) * 1.6 + (dS[c] === 0 ? 0.8 : 0) + (h.d > 7 && h.d < 24 ? 1.5 : 0)
        + (nav.dDef[c] < nav.dDef[h.watch] ? 1 : -2) + Math.random() * 1.2;
    }, 2.2, 8).map(c => ({ c, watch: holdInfo.get(c).watch }));
    if (!holds.length) holds = aiSpread(cells, c => nav.cover[c] + Math.random(), 2, 4).map(c => ({ c, watch: ents[0].rep }));
    // позиции атаки внутри точки и места закладки
    const inner = near.filter(c => dS[c] <= 1.01);
    const inSpots = aiSpread(inner, c => Math.min(nav.cover[c], 2) * 1.5 + Math.random() * 1.5, 1.5, 8);
    const plantSpots = aiSpread(cells, c => Math.min(nav.cover[c], 2) * 2 + Math.random(), 1.2, 6);
    let cc = cells[0], cd = 1e9; for (const c of cells) { const d = aiDist(c, s.center.x, s.center.z); if (d < cd) { cd = d; cc = c; } }
    // позиции отхода защиты: рядом с точкой со своей стороны, без вида на центр точки — ждать подмогу и возвращать точку
    const fallC = [];
    for (let i = 0; i < N; i++) if (aiOpen(i) && dS[i] >= 3 && dS[i] <= 9 && nav.dDef[i] <= nav.dDef[cells[0]] + 2 && !aiSee(i, s.center.x, s.center.z)) fallC.push(i);
    const falls = aiSpread(fallC, c => Math.min(nav.cover[c], 2) - Math.abs(dS[c] - 5) * 0.3 + Math.random(), 1.8, 6);
    nav.sites[s.id] = { id: s.id, cells, dS, ents, holds, falls, inSpots: inSpots.length ? inSpots : cells.slice(0, 5), plantSpots: plantSpots.length ? plantSpots : cells.slice(0, 3), center: cc, cx: s.center.x, cz: s.center.z };
    nav.siteIds.push(s.id);
  }
  // «середина» для ротации защиты: примерно на равном пути до обеих точек, на своей половине, у укрытия
  if (nav.siteIds.length >= 2) {
    const [a, b] = nav.siteIds.map(id => nav.sites[id].dS);
    const sc = nav.coverList.filter(i => nav.dDef[i] < nav.dAtk[i] - 2).map(i => [i, Math.abs(a[i] - b[i]) + 0.35 * nav.dDef[i] - 0.2 * Math.min(a[i], b[i]) + Math.random() * 2]);
    sc.sort((p, q) => p[1] - q[1]);
    if (sc.length) { nav.mid = sc[0][0]; nav.midWatch = aiDescend(nav.mid, nav.dAtk, 6); }
  }
  // линия фронта для командного боя
  nav.front = nav.coverList.filter(i => nav.dA[i] < 1e8 && Math.abs(nav.dA[i] - nav.dB[i]) <= 6);
  NAV = nav;
  return nav;
}
function aiSiteNear(x, z, maxCells) {
  if (!NAV) return null;
  const c = aiCellAt(x, z); let best = null, bd = maxCells || 6;
  for (const id of NAV.siteIds) { const d = NAV.sites[id].dS[c]; if (d <= bd) { bd = d; best = id; } }
  return best;
}

/* ---------- состояние бойца и команды ---------- */
function aiResetBot(b) {
  b.ai = { order: null, path: null, pi: 0, pathGoal: -1, arrived: false, noise: null, progT: 0, progX: b.pos.x, progZ: b.pos.z, stuckN: 0,
    unstuckT: 0, ux: 0, uz: 0, retreat: null, retreatCd: 0, nadeCd: rand(2, 6), nadePlan: null, sweep: rand(0, 6), engCrouch: false,
    role: Math.random() < 0.35 ? 'push' : 'hold', lostT: 0, wasEngaged: false };
  b.crouch = false; b.planting = false; b.defusing = false;
  return b.ai;
}
function aiNoise() { const n = new Float32Array(MW * MH); for (let i = 0; i < n.length; i++) n[i] = Math.random() * 0.7; return n; }
function aiNewTeam(team) { return { team, plan: null, seen: new Map(), post: null, retake: null, lostT: -99, siteLoss: {}, n: 0 }; }
function aiMatchStart() { aiPrepare(); AI.teams.A = aiNewTeam('A'); AI.teams.B = aiNewTeam('B'); }
function aiRoundStart() {
  if (!NAV) aiPrepare();
  AI.teams.A = aiNewTeam('A'); AI.teams.B = aiNewTeam('B'); AI.tickT = 0;
  for (const b of bots) { if (!b.ai) aiResetBot(b); b.ai.noise = aiNoise(); }
}
function aiSpot(team, e) { const T = AI.teams[team]; if (T) T.seen.set(e, { x: e.pos.x, z: e.pos.z, t: gt }); }
function aiFresh(T, maxAge) { const out = []; for (const [e, s] of T.seen) if (e.alive && gt - s.t <= maxAge) out.push(s); return out; }
function aiOnKill(victim, attacker) {
  const T = AI.teams[victim.team]; if (!T) return;
  T.lostT = gt;
  if (attacker && attacker.alive && attacker.team !== victim.team) {
    aiSpot(victim.team, attacker);
    for (const m of bots) if (m.alive && m.team === victim.team && !m.targetVisible && m.pos.distanceTo(victim.pos) < 18) {
      m.lastSeen.copy(attacker.pos); m.lastSeenT = 3; m.alertT = 2;
    }
  }
  const site = aiSiteNear(victim.pos.x, victim.pos.z, 4);
  if (site) T.siteLoss[site] = gt;
}
// приказ: type 'hold' | 'plant' | 'defuse' | 'pickup' | 'flee' | 'hunt'; cells — путевые точки; watch — куда смотреть на месте
function aiGive(b, type, cells, watch, opt) {
  const a = b.ai || aiResetBot(b);
  cells = (Array.isArray(cells) ? cells : [cells]).filter(c => c !== undefined && c !== null).map(aiNearestOpen);
  if (!cells.length) return null;
  opt = opt || {};
  const o = a.order, last = cells[cells.length - 1];
  if (o && o.type === type && o.cells[o.cells.length - 1] === last && o.tag === (opt.tag || '')) { if (watch) o.watch = watch; return o; }
  a.order = { type, cells, k: 0, watch: watch || null, tag: opt.tag || '', crouch: !!opt.crouch, start: gt + (opt.delay || 0), until: opt.until || 0 };
  a.path = null; a.arrived = false; a.stuckN = 0;
  aiStats.orders++;
  return a.order;
}
const aiW = i => ({ x: aiX(i), z: aiZ(i) });
const aiTaken = (mates, c, self, gap) => mates.some(m => m !== self && m.ai && m.ai.order && Math.hypot(aiX(m.ai.order.cells[m.ai.order.cells.length - 1]) - aiX(c), aiZ(m.ai.order.cells[m.ai.order.cells.length - 1]) - aiZ(c)) < (gap || 1.2) * CELL);
function aiNeeds(b, tag) { const o = b.ai && b.ai.order; return !o || (o.tag !== tag && o.type !== 'pickup' && o.type !== 'defuse' && o.type !== 'flee'); }

/* ---------- штаб ---------- */
// раз в кадр (вызывается первым ботом): логика режима, затем решения команд
function aiFrame(dt) {
  if (typeof objTick === 'function') objTick(dt);
  if (state !== 'live' && state !== 'freeze') return;
  AI.tickT -= dt; if (AI.tickT > 0) return; AI.tickT = 0.35;
  if (!NAV) aiPrepare();
  for (const team of ['A', 'B']) {
    const T = AI.teams[team] || (AI.teams[team] = aiNewTeam(team));
    const mates = bots.filter(b => b.team === team && b.alive);
    if (!mates.length) continue;
    for (const [e, s] of T.seen) if (!e.alive || gt - s.t > 20) T.seen.delete(e);
    if (mode.bomb && NAV.siteIds.length) { if (teamSide[team] === 'atk') aiAttack(T, mates); else aiDefend(T, mates); }
    else aiTdm(T, mates);
  }
}
// бегство от заряда, который вот-вот сработает
function aiFleeCell(b, p) {
  const R = CHARGE.radius + 3; let best = -1, bd = 1e9;
  for (const [x, z] of openCells) {
    const i = z * MW + x, wx = aiX(i), wz = aiZ(i);
    if (Math.hypot(wx - p.x, wz - p.z) < R) continue;
    const d = Math.hypot(wx - b.pos.x, wz - b.pos.z); if (d < bd) { bd = d; best = i; }
  }
  return best;
}
function aiFleeIfNeeded(b, tLeft) {
  const p = chargeState.pos;
  if (tLeft > 0 && Math.hypot(b.pos.x - p.x, b.pos.z - p.z) < CHARGE.radius + 1) {
    const d = Math.hypot(b.pos.x - p.x, b.pos.z - p.z), runT = (CHARGE.radius + 2 - d) / 3.6;
    if (tLeft > runT + 2.5) return false;  // ещё рано уходить
    if (runT + 0.4 > tLeft) return false;  // уже не успеть — держим позицию
    const c = aiFleeCell(b, p); if (c >= 0) { aiGive(b, 'flee', c, null, { tag: 'flee' }); b.defusing = false; return true; }
  }
  return false;
}

/* ----- атака ----- */
function aiPlanAttack(T) {
  const ids = NAV.siteIds, site = pick(ids), other = ids.find(i => i !== site) || null;
  const r = Math.random();
  const style = r < 0.18 ? 'rush' : r < 0.45 ? 'split' : (r < 0.62 && other) ? 'fake' : 'default';
  const S = NAV.sites[site];
  const e0 = S.ents.length > 1 && Math.random() < 0.35 ? 1 : 0;
  const e1 = S.ents.length > 1 ? (e0 === 0 ? 1 + ((Math.random() * (S.ents.length - 1)) | 0) : 0) : e0;
  const span = Math.max(15, mode.roundTime - (mode.lateExec || 35));
  T.n++;
  T.plan = { site, style, other, phase: style === 'rush' ? 'exec' : style === 'fake' ? 'fake' : 'gather', ents: [e0, e1],
    execAt: rand(span * 0.45, span * 0.85), wait: 0, waitNeed: rand(1.5, 5), fakeWait: 0, tag: 'g' + T.n, nadesSet: false };
}
function aiGatherCells(stage, n) {
  // клетки вокруг места сбора, ближе к атаке, без вида на точку не требуем — главное разнести
  const out = [], seen = new Set([stage]), q = [[stage, 0]];
  while (q.length && out.length < n * 3) {
    const [c, d] = q.shift(); out.push([c, d]);
    if (d >= 3) continue;
    const cx = c % MW, cz = (c / MW) | 0;
    for (const [ox, oz] of AI_NB) { if (!aiStepOk(cx, cz, ox, oz)) continue; const ni = (cz + oz) * MW + cx + ox; if (!seen.has(ni)) { seen.add(ni); q.push([ni, d + 1]); } }
  }
  const sc = out.map(([c, d]) => [c, d + (NAV.cover[c] ? -0.6 : 0) + Math.random() * 0.8]).sort((a, b) => a[1] - b[1]).map(e => e[0]);
  const res = [];
  for (const c of sc) { if (res.some(o => Math.hypot(aiX(o) - aiX(c), aiZ(o) - aiZ(c)) < 1.4 * CELL)) continue; res.push(c); if (res.length >= n) break; }
  while (res.length < n) res.push(stage);
  return res;
}
function aiAttack(T, mates) {
  const cs = chargeState, D = DIFF[settings.diff];
  if (!T.plan) aiPlanAttack(T);
  const P = T.plan;
  if (state === 'freeze') return;
  if (cs.state === 'planted') { aiPostPlant(T, mates); return; }
  // упавший заряд: ближайший боец идёт подбирать
  if (cs.state === 'dropped') {
    let best = null, bd = 1e9;
    for (const b of mates) { const d = Math.hypot(b.pos.x - cs.pos.x, b.pos.z - cs.pos.z); if (d < bd) { bd = d; best = b; } }
    const playerClose = player.alive && player.side === 'atk' && Math.hypot(player.pos.x - cs.pos.x, player.pos.z - cs.pos.z) < 4;
    if (best && !(playerClose && bd > 6)) aiGive(best, 'pickup', aiCellAt(cs.pos.x, cs.pos.z), null, { tag: 'pick' });
  }
  const carrier = cs.state === 'carried' ? cs.carrier : null;
  // носитель — игрок: штаб подстраивается под выбранную им точку
  if (carrier && carrier.isPlayer) {
    const pc = aiCellAt(player.pos.x, player.pos.z); let bs = null, bd = 1e9;
    for (const id of NAV.siteIds) { const d = NAV.sites[id].dS[pc]; if (d < bd) { bd = d; bs = id; } }
    if (bs && bd < 10 && bs !== P.site) { P.site = bs; P.ents = [0, NAV.sites[bs].ents.length > 1 ? 1 : 0]; if (P.phase === 'exec') { T.n++; P.tag = 'x' + T.n; } }
    if (bs && bd < 6 && P.phase !== 'exec') aiStartExec(T, P);
  }
  const late = roundT < (mode.lateExec || 35);
  if (P.phase === 'fake') {
    const S = NAV.sites[P.other], ent = S.ents[0];
    const spots = P.fakeSpots || (P.fakeSpots = aiGatherCells(ent.stage, mates.length + 1));
    let arrived = 0;
    mates.forEach((b, i) => {
      if (aiNeeds(b, P.tag)) aiGive(b, 'hold', spots[i % spots.length], aiW(ent.rep), { tag: P.tag, delay: rand(0, 1.2) });
      if (b.ai.arrived) arrived++;
    });
    if (arrived >= Math.ceil(mates.length * 0.6)) {
      P.fakeWait += 0.35;
      if (!P.fakeNade) { P.fakeNade = true; const nb = mates.find(b => b.aiNades && (b.aiNades.he || b.aiNades.flash)); if (nb) nb.ai.nadePlan = { type: nb.aiNades.he ? 'he' : 'flash', x: S.cx, z: S.cz, y: 1, near: 30 }; }
    }
    if (P.fakeWait > rand(2.5, 5) || late || gt - T.lostT < 2) aiStartExec(T, P);
    return;
  }
  if (P.phase === 'gather') {
    const S = NAV.sites[P.site];
    if (!P.spots) {
      const split = P.style === 'split' && P.ents[1] !== P.ents[0];
      const nA = split ? Math.ceil(mates.length / 2) : mates.length;
      const sa = aiGatherCells(S.ents[P.ents[0]].stage, nA + 1), sb = split ? aiGatherCells(S.ents[P.ents[1]].stage, mates.length - nA + 1) : [];
      P.groups = new Map(); P.spots = new Map();
      // носитель — в большей группе
      const order = mates.slice().sort((x, y) => (y.hasCharge ? 1 : 0) - (x.hasCharge ? 1 : 0));
      order.forEach((b, i) => { const g = split && i >= nA ? 1 : 0; P.groups.set(b, g); P.spots.set(b, g ? sb[(i - nA) % sb.length] : sa[i % sa.length]); });
    }
    let arrived = 0;
    for (const b of mates) {
      const g = P.groups.has(b) ? P.groups.get(b) : 0, ent = S.ents[P.ents[g]];
      if (!P.spots.has(b)) P.spots.set(b, ent.stage);
      if (aiNeeds(b, P.tag)) aiGive(b, 'hold', P.spots.get(b), aiW(ent.rep), { tag: P.tag, delay: rand(0, 1.5), crouch: Math.random() < 0.3 });
      if (b.ai.arrived) arrived++;
    }
    if (arrived >= Math.ceil(mates.length * 0.7)) P.wait += 0.35;
    if (late || P.wait > P.waitNeed || roundElapsed > P.execAt || gt - T.lostT < 2.5) aiStartExec(T, P);
    return;
  }
  // выход на точку
  const S = NAV.sites[P.site];
  if (!P.groups) { P.groups = new Map(); mates.forEach((b, i) => P.groups.set(b, P.style === 'split' && i % 2 ? 1 : 0)); }
  const free = S.inSpots.slice();
  for (const b of mates) {
    const o = b.ai.order;
    if (b.hasCharge) {
      if (o && o.tag === P.tag + 'p') continue;
      const ent = S.ents[P.ents[P.groups.get(b) || 0]];
      let ps = S.plantSpots[0], pd = 1e9;
      for (const c of S.plantSpots) { const d = Math.hypot(aiX(c) - aiX(ent.rep), aiZ(c) - aiZ(ent.rep)) + Math.random() * 4; if (d < pd) { pd = d; ps = c; } }
      const via = S.dS[aiCellAt(b.pos.x, b.pos.z)] > S.dS[ent.rep] + 1 ? [ent.rep, ps] : [ps];
      aiGive(b, 'plant', via, { x: S.cx, z: S.cz }, { tag: P.tag + 'p', delay: carrierDelay(b, mates) });
      continue;
    }
    if (!aiNeeds(b, P.tag)) continue;
    const ent = S.ents[P.ents[P.groups.has(b) ? P.groups.get(b) : 0]];
    // точка внутри: свободная, ближе к своему входу
    let spot = free[0], sd = 1e9;
    for (const c of free) { if (aiTaken(mates, c, b, 1.2)) continue; const d = Math.hypot(aiX(c) - aiX(ent.rep), aiZ(c) - aiZ(ent.rep)) + Math.random() * 6; if (d < sd) { sd = d; spot = c; } }
    const hs = S.holds.filter(h => aiSee(spot, aiX(h.c), aiZ(h.c)));
    const watch = hs.length ? aiW(pick(hs).c) : { x: S.cx, z: S.cz };
    const via = S.dS[aiCellAt(b.pos.x, b.pos.z)] > S.dS[ent.rep] + 1 ? [ent.rep, spot] : [spot];
    aiGive(b, 'hold', via, watch, { tag: P.tag, delay: rand(0, 0.6) });
    // гранаты на входе: дым на самую опасную позицию защиты, вспышка в центр точки
    if (!P.nadesSet && b.aiNades && Math.random() < D.nade) {
      const danger = S.holds.find(h => aiSee(ent.rep, aiX(h.c), aiZ(h.c))) || S.holds[0];
      if (b.aiNades.smoke && danger) b.ai.nadePlan = { type: 'smoke', x: aiX(danger.c), z: aiZ(danger.c), y: 0.5, near: 16, at: ent.rep };
      else if (b.aiNades.flash) b.ai.nadePlan = { type: 'flash', x: S.cx, z: S.cz, y: 2.2, near: 16, at: ent.rep };
      if (b.ai.nadePlan) P.nadesN = (P.nadesN || 0) + 1;
      if (P.nadesN >= 2) P.nadesSet = true;
    }
  }
}
function carrierDelay(b, mates) { return mates.length > 1 ? 1.2 : 0; }
function aiStartExec(T, P) {
  if (P.phase === 'exec') return;
  T.n++; P.phase = 'exec'; P.tag = 'x' + T.n; P.groups = null;
}
function aiPostPlant(T, mates) {
  const cs = chargeState, p = cs.pos;
  if (!T.post) {
    const cands = [];
    for (const [x, z] of openCells) {
      const i = z * MW + x, d = aiDist(i, p.x, p.z);
      if (d < 4 || d > 17) continue;
      if (!los(aiX(i), 1.6, aiZ(i), p.x, 0.5, p.z)) continue;
      cands.push(i);
    }
    T.post = aiSpread(cands, c => Math.min(NAV.cover[c], 2) * 2 + (NAV.dAtk[c] < NAV.dAtk[aiCellAt(p.x, p.z)] ? 1.2 : 0) + Math.random() * 1.5, 1.6, 8);
    if (!T.post.length) T.post = [aiCellAt(p.x, p.z)];
    T.postTag = 'post' + (++T.n);
  }
  for (const b of mates) {
    if (aiFleeIfNeeded(b, roundT - 0.2) || (b.ai.order && b.ai.order.type === 'flee' && roundT < 6)) continue;
    if (!aiNeeds(b, T.postTag)) continue;
    let best = T.post[0], bd = 1e9;
    for (const c of T.post) { if (aiTaken(mates, c, b, 1.4)) continue; const d = aiDist(c, b.pos.x, b.pos.z) + Math.random() * 4; if (d < bd) { bd = d; best = c; } }
    aiGive(b, 'hold', best, { x: p.x, z: p.z }, { tag: T.postTag, crouch: Math.random() < 0.4 });
  }
}

/* ----- защита ----- */
function aiPlanDefend(T, mates) {
  const ids = NAV.siteIds.slice().sort(() => Math.random() - 0.5), n = mates.length, keys = [];
  if (ids.length < 2) for (let i = 0; i < n; i++) keys.push(ids[0]);
  else {
    const [a, b] = ids, hasMid = NAV.mid !== undefined;
    const add = (k, c) => { for (let i = 0; i < c; i++) keys.push(k); };
    if (n >= 5) { add(a, 2); add(b, 2); add(hasMid ? 'mid' : a, 1); add(a, n - 5); }
    else if (n === 4) { if (Math.random() < 0.25) { add(a, 3); add(b, 1); } else if (hasMid && Math.random() < 0.3) { add(a, 2); add(b, 1); add('mid', 1); } else { add(a, 2); add(b, 2); } }
    else if (n === 3) { if (hasMid && Math.random() < 0.5) { add(a, 1); add(b, 1); add('mid', 1); } else { add(a, 2); add(b, 1); } }
    else if (n === 2) { add(a, 1); add(b, 1); }
    else add(a, 1);
  }
  const sh = mates.slice().sort(() => Math.random() - 0.5);
  T.n++;
  T.plan = { assign: new Map(), tag: 'd' + T.n, rotated: {}, shuffleT: gt + rand(16, 26) };
  sh.forEach((b, i) => T.plan.assign.set(b, keys[i] || ids[0]));
}
function aiHoldFor(T, b, key, mates, tag) {
  if (key === 'mid') { aiGive(b, 'hold', NAV.mid, aiW(NAV.midWatch), { tag, crouch: Math.random() < 0.4, delay: rand(0, 1) }); return; }
  const S = NAV.sites[key]; if (!S) return;
  const free = S.holds.filter(h => !aiTaken(mates, h.c, b, 1.6));
  const h = free.length ? free[(Math.random() * Math.min(3, free.length)) | 0] : pick(S.holds);
  aiGive(b, 'hold', h.c, aiW(h.watch), { tag, crouch: Math.random() < 0.45, delay: rand(0, 1) });
}
function aiDefend(T, mates) {
  if (!T.plan) aiPlanDefend(T, mates);
  const P = T.plan, cs = chargeState;
  if (cs.state === 'planted') { if (state === 'live') aiRetake(T, mates); return; }
  for (const b of mates) {
    if (!P.assign.has(b)) P.assign.set(b, pick(NAV.siteIds));
    if (aiNeeds(b, P.tag)) aiHoldFor(T, b, P.assign.get(b), mates, P.tag);
  }
  if (state !== 'live') return;
  // сведения о противнике на точках → ротация
  const fresh = aiFresh(T, 5);
  for (const id of NAV.siteIds) {
    if (P.rotated[id]) continue;
    const S = NAV.sites[id];
    const n = fresh.filter(s => aiSiteNear(s.x, s.z, 4) === id).length; // только у этой точки и ближе к ней, чем к другой
    const lost = T.siteLoss[id] && gt - T.siteLoss[id] < 6;
    if (n >= 2 || (n >= 1 && lost) || (lost && Math.random() < 0.5)) {
      P.rotated[id] = true;
      const others = mates.filter(b => P.assign.get(b) !== id);
      const midB = others.filter(b => P.assign.get(b) === 'mid'), farB = others.filter(b => P.assign.get(b) !== 'mid');
      const go = midB.slice();
      if (n >= 3 || lost) go.push(...farB.slice(0, Math.max(0, farB.length - 1)));
      else if (farB.length >= 2) go.push(farB[0]);
      T.n++; const tag = 'r' + T.n;
      const own = mates.filter(b => P.assign.get(b) === id);
      for (const b of go) { P.assign.set(b, id); aiHoldFor(T, b, id, mates, tag); b.ai.order.tag = P.tag; }
      // точку давят числом: свои отходят на позиции отхода, подмога собирается там же — дальше возврат точки
      if (n >= 3 && own.length < n && S.falls.length && Math.random() < 0.75) {
        for (const b of own.concat(go)) {
          if (b.targetVisible && b.hp > 50) continue;
          const f = S.falls.filter(c => !aiTaken(mates, c, b, 1.4));
          const c = (f.length ? f : S.falls).reduce((m, c) => aiDist(c, b.pos.x, b.pos.z) < aiDist(m, b.pos.x, b.pos.z) ? c : m);
          aiGive(b, 'hold', c, { x: S.cx, z: S.cz }, { tag: P.tag, crouch: Math.random() < 0.4 });
        }
      }
    }
  }
  // иногда меняем позицию, чтобы не стоять предсказуемо
  if (gt > P.shuffleT && !fresh.length) {
    P.shuffleT = gt + rand(14, 24);
    const b = pick(mates), key = P.assign.get(b);
    if (key && key !== 'mid' && b.ai.arrived && !b.targetVisible) { b.ai.order = null; aiHoldFor(T, b, key, mates, P.tag); }
  }
}
function aiRetake(T, mates) {
  const cs = chargeState, p = cs.pos, D = DIFF[settings.diff];
  const cc = aiCellAt(p.x, p.z);
  if (!T.retake) {
    const field = aiField([aiNearestOpen(cc)]);
    const stage = [], push = [];
    for (const [x, z] of openCells) {
      const i = z * MW + x, f = field[i];
      if (f > 1e8) continue;
      const vis = los(aiX(i), 1.6, aiZ(i), p.x, 0.5, p.z);
      if (f >= 6 && f <= 11 && !vis && NAV.dDef[i] <= NAV.dDef[cc] + 3) stage.push(i);
      if (f <= 7 && vis && aiDist(i, p.x, p.z) > 3) push.push(i);
    }
    T.n++;
    T.retake = { field, phase: 'gather', tag: 'rg' + T.n, ptag: 'rp' + T.n,
      stage: aiSpread(stage, c => Math.min(NAV.cover[c], 2) + Math.random() * 1.5, 1.5, 8),
      push: aiSpread(push, c => Math.min(NAV.cover[c], 2) * 1.5 + Math.random() * 1.5, 1.6, 8) };
    if (!T.retake.stage.length) T.retake.phase = 'push';
    if (!T.retake.push.length) T.retake.push = [aiNearestOpen(cc)];
  }
  const R = T.retake, tLeft = roundT;
  const atkAlive = units.filter(u => u.alive && u.side === 'atk').length;
  const best = mates.reduce((m, b) => (!m || defuseTime(b) < defuseTime(m)) ? b : m, null);
  const need = defuseTime(best);
  // кто разминирует
  const playerOn = player.alive && player.side === 'def' && player.defusing;
  let defuser = mates.find(b => b.ai.order && b.ai.order.type === 'defuse');
  const freshNear = aiFresh(T, 2).filter(s => Math.hypot(s.x - p.x, s.z - p.z) < 18).length;
  if (R.phase === 'gather') {
    const close = mates.filter(b => R.field[aiCellAt(b.pos.x, b.pos.z)] <= 11).length;
    if (close >= Math.ceil(mates.length * 0.6) || tLeft < need + 14 || atkAlive === 0) R.phase = 'push';
  }
  if (!defuser && !playerOn && (atkAlive === 0 || (R.phase === 'push' && (freshNear === 0 || tLeft < need + 2.5)))) {
    let cand = null, cd = 1e9;
    for (const b of mates) {
      const d = R.field[aiCellAt(b.pos.x, b.pos.z)] * CELL / 4 + defuseTime(b);
      if (d < cd) { cd = d; cand = b; }
    }
    if (cand && cd < tLeft + 1) { defuser = cand; aiGive(cand, 'defuse', cc, { x: p.x, z: p.z }, { tag: 'def' }); }
  }
  for (const b of mates) {
    // не успеть — уходим из радиуса
    const left = defuseTime(b) - (b.defusing ? b.useT : 0);
    const runIn = b === defuser ? Math.max(0, Math.hypot(b.pos.x - p.x, b.pos.z - p.z) - 1.2) / 4 : 0;
    if (left + runIn > tLeft + 0.2 && Math.random() < 0.85 + D.peek * 0.15) {
      if (b.ai.order && b.ai.order.type === 'flee') continue;
      if (aiFleeIfNeeded(b, tLeft)) continue;
    }
    if (b === defuser) continue;
    if (R.phase === 'gather' && R.field[aiCellAt(b.pos.x, b.pos.z)] > 11) {
      if (aiNeeds(b, R.tag)) {
        let s = R.stage[0], sd = 1e9;
        for (const c of R.stage) { if (aiTaken(mates, c, b, 1.2)) continue; const d = aiDist(c, b.pos.x, b.pos.z); if (d < sd) { sd = d; s = c; } }
        aiGive(b, 'hold', s, { x: p.x, z: p.z }, { tag: R.tag });
      }
    } else if (aiNeeds(b, R.ptag)) {
      let s = R.push[0], sd = 1e9;
      for (const c of R.push) { if (aiTaken(mates, c, b, 1.4)) continue; const d = aiDist(c, b.pos.x, b.pos.z) + Math.random() * 3; if (d < sd) { sd = d; s = c; } }
      const fr = aiFresh(T, 6); const w = fr.length ? fr[0] : { x: p.x, z: p.z };
      aiGive(b, 'hold', s, { x: w.x, z: w.z }, { tag: R.ptag });
    }
  }
}

/* ----- командный бой: держать линию, двигаться от укрытия к укрытию ----- */
function aiPickCover(b, tx, tz, dmin, dmax, mates) {
  const L = NAV.coverList; let best = -1, bs = -1e9;
  for (let k = 0; k < 60; k++) {
    const c = L[(Math.random() * L.length) | 0], d = aiDist(c, tx, tz), db = aiDist(c, b.pos.x, b.pos.z);
    if (d < dmin || d > dmax || db > 26) continue;
    if (aiTaken(mates, c, b, 2)) continue;
    if (!aiSee(c, tx, tz)) continue;
    const s = -db * 0.12 + Math.min(NAV.cover[c], 2) + Math.random();
    if (s > bs) { bs = s; best = c; }
  }
  return best;
}
function aiTdm(T, mates) {
  if (state !== 'live' && state !== 'freeze') return;
  const enemyF = T.team === 'A' ? NAV.dB : NAV.dA, ownF = T.team === 'A' ? NAV.dA : NAV.dB;
  const fresh = aiFresh(T, 8);
  for (const b of mates) {
    const a = b.ai, o = a.order;
    if (o && !(a.arrived && o.until && gt > o.until) && !(o.type === 'hunt' && gt > o.until)) continue;
    if (b.targetVisible) continue;
    T.n++; const tag = 't' + T.n;
    let threat = null, td = 1e9;
    for (const s of fresh) { const d = Math.hypot(s.x - b.pos.x, s.z - b.pos.z); if (d < td) { td = d; threat = s; } }
    if (threat && td < 40) {
      const c = aiPickCover(b, threat.x, threat.z, 8, 24, mates);
      if (c >= 0) { aiGive(b, 'hold', c, { x: threat.x, z: threat.z }, { tag, until: gt + rand(3, 7), crouch: Math.random() < 0.35 }); continue; }
      if (a.role === 'push') { aiGive(b, 'hunt', aiCellAt(threat.x, threat.z), null, { tag, until: gt + 6 }); continue; }
    }
    const bc = aiCellAt(b.pos.x, b.pos.z);
    let cands;
    if (a.role === 'push') cands = NAV.coverList.filter(c => enemyF[c] < enemyF[bc] - 2 && enemyF[c] > enemyF[bc] - 12);
    else cands = NAV.front.filter(c => ownF[c] <= enemyF[c] + 2);
    if (!cands.length) cands = NAV.front.length ? NAV.front : NAV.coverList;
    let best = -1, bs = -1e9;
    for (let k = 0; k < 30; k++) {
      const c = cands[(Math.random() * cands.length) | 0];
      if (aiTaken(mates, c, b, 2.2)) continue;
      const s = Math.min(NAV.cover[c], 2) - aiDist(c, b.pos.x, b.pos.z) * 0.04 + Math.random() * 2;
      if (s > bs) { bs = s; best = c; }
    }
    if (best < 0) best = pick(cands);
    const w = aiDescend(best, enemyF, 6);
    aiGive(b, 'hold', best, aiW(w), { tag, until: gt + (a.role === 'push' ? rand(2.5, 5) : rand(6, 11)), crouch: Math.random() < 0.3 });
    if (Math.random() < 0.25) a.role = a.role === 'push' ? 'hold' : 'push';
  }
}

/* ---------- боец ---------- */
function perceive(b) {
  if (b.flashT > 0) { b.targetVisible = false; return; }
  const D = DIFF[settings.diff];
  const eyeY = b.pos.y + (b.crouch ? 1.2 : 1.7);
  const smoke = typeof smokeBlocks === 'function';
  let best = null, bd = 1e9;
  for (const e of units) {
    if (!e.alive || e.team === b.team) continue;
    const d = Math.hypot(e.pos.x - b.pos.x, e.pos.z - b.pos.z);
    if (d > 75) continue;
    const ang = Math.abs(angDiff(yawTo(b.pos.x, b.pos.z, e.pos.x, e.pos.z), b.yaw));
    if (ang > D.fov && b.alertT <= 0 && d > 5) continue;
    const ty = e.pos.y + (e.crouch ? 1.0 : 1.4);
    if (!los(b.pos.x, eyeY, b.pos.z, e.pos.x, ty, e.pos.z)) continue;
    if (smoke && smokeBlocks(b.pos.x, eyeY, b.pos.z, e.pos.x, ty, e.pos.z)) continue;
    const score = d * (e === b.target ? 0.7 : 1) * (e.planting || e.defusing ? 0.6 : 1);
    if (score < bd) { bd = score; best = e; }
  }
  if (best) {
    if (best !== b.target || !b.targetVisible) { b.reactT = rand(D.react[0], D.react[1]) * (b.alertT > 0 ? 0.7 : 1) * (b.ai && b.ai.arrived && Math.hypot(b.vx, b.vz) < 1 ? 0.7 : 1) * (Math.hypot(best.vx, best.vz) > 2.5 ? 1.1 : 1); b.burst = 0; } // держащий угол реагирует быстрее бегущего
    b.target = best; b.targetVisible = true; b.lastSeen.copy(best.pos); b.lastSeenT = 5; best.spottedT = 1.2;
    aiSpot(b.team, best);
  } else b.targetVisible = false;
}
// укрытие поблизости, откуда не видно точку (ex, ez)
function aiCoverFrom(b, ex, ez, maxD) {
  const c0 = aiCellAt(b.pos.x, b.pos.z), seen = new Set([c0]), q = [[c0, 0]];
  let best = -1, bs = 1e9;
  while (q.length) {
    const [c, d] = q.shift();
    if (c !== c0 && !los(aiX(c), 1.5, aiZ(c), ex, 1.4, ez)) {
      const s = d - Math.min(aiDist(c, ex, ez), 30) * 0.08 + (NAV && NAV.cover[c] ? -0.3 : 0);
      if (s < bs) { bs = s; best = c; }
    }
    if (d >= maxD) continue;
    const cx = c % MW, cz = (c / MW) | 0;
    for (const [ox, oz] of AI_NB) { if (!aiStepOk(cx, cz, ox, oz)) continue; const ni = (cz + oz) * MW + cx + ox; if (!seen.has(ni)) { seen.add(ni); q.push([ni, d + 1]); } }
  }
  return best;
}
function aiRetreat(b, t, why) {
  const a = b.ai; if (a.retreatCd > 0) return;
  const c = aiCoverFrom(b, t.pos.x, t.pos.z, 5);
  a.retreatCd = why === 'reload' ? 2.5 : 6;
  if (c < 0) return;
  a.retreat = { cell: c, until: gt + (why === 'reload' ? Math.max(1.5, weaponOf(b).reload + 0.6) : rand(4, 7)), why, path: aiPath(aiCellAt(b.pos.x, b.pos.z), c, null), pi: 0, wx: t.pos.x, wz: t.pos.z };
  aiStats.retreats++;
}
function aiThrow(b, type, x, y, z) {
  if (typeof throwGrenade !== 'function' || !b.aiNades || !b.aiNades[type]) return false;
  const dx = x - b.pos.x, dz = z - b.pos.z, d = Math.hypot(dx, dz); if (d < 3) return false;
  const el = clamp(0.18 + d / 70 + (y - 1.5) * 0.02, 0.18, 0.8);
  b.yaw = yawTo(b.pos.x, b.pos.z, x, z);
  const dir = new THREE.Vector3(dx / d * Math.cos(el), Math.sin(el), dz / d * Math.cos(el));
  const ok = throwGrenade(b, type, dir, d);
  if (ok === false) return false;
  b.aiNades[type]--; aiStats.nades++; b.ai.nadeCd = rand(5, 9);
  return true;
}
// движение к точке по пути: возвращает [mx, mz] или null
function aiSteer(b, a, path, goal, gx, gz) {
  if (a.pi < path.length) {
    let j = Math.min(path.length - 1, a.pi + 4);
    for (; j > a.pi; j--) if (aiClear(b.pos.x, b.pos.z, aiX(path[j]), aiZ(path[j]))) break;
    a.pi = j;
    const wx = aiX(path[a.pi]), wz = aiZ(path[a.pi]), dx = wx - b.pos.x, dz = wz - b.pos.z, d = Math.hypot(dx, dz);
    if (d < 0.6) { a.pi++; }
    if (d > 0.05) return [dx / d, dz / d];
  }
  const dx = gx - b.pos.x, dz = gz - b.pos.z, d = Math.hypot(dx, dz);
  return d > 0.05 ? [dx / d, dz / d] : null;
}
function updateBot(b, dt) {
  if (b === bots[0]) aiFrame(dt);
  const mesh = b.mesh;
  if (!b.alive) {
    if (b.deathT > 0 && b.deathT < 1) {
      b.deathT = Math.min(1, b.deathT + dt * 2.6);
      const e = 1 - Math.pow(1 - b.deathT, 3);
      mesh.root.rotation.x = e * Math.PI / 2 * 0.96;
      mesh.root.position.y = b.pos.y + e * 0.16;
      mesh.knees.forEach(k => k.rotation.x = -e * 0.5);
      mesh.chest.rotation.x = -e * 0.2;
      mesh.blob.visible = false;
    }
    return;
  }
  const D = DIFF[settings.diff], w = weaponOf(b), a = b.ai || aiResetBot(b);
  b.alertT -= dt; b.lastSeenT -= dt; b.goalT -= dt; b.protT = Math.max(0, b.protT - dt);
  a.retreatCd -= dt; a.nadeCd -= dt;
  // ослепление: если его никто не уменьшает (модуль «Бой»), уменьшаем сами
  if (b.flashT > 0) { if (a.flPrev === b.flashT) b.flashT = Math.max(0, b.flashT - dt); a.flPrev = b.flashT; }
  if (b.reloading > 0) { b.reloading -= dt; if (b.reloading <= 0) { b.reloading = 0; finishReload(b); } }
  if (state === 'freeze' && mode.rounds) { b.crouch = false; syncBotMesh(b, dt, 0); return; }
  b.thinkT -= dt;
  if (b.thinkT <= 0) { b.thinkT = rand(0.12, 0.22); perceive(b); }
  let desiredYaw = b.yaw, mvx = 0, mvz = 0, speed = 4.1 * w.speed, aimPitch = 0, crouch = false, moving = false, still = false;
  const t = b.target, blind = b.flashT > 0;
  const engaged = !blind && t && t.alive && b.targetVisible;
  const o = a.order && gt >= a.order.start ? a.order : null;
  const cs = chargeState;
  // действия режима
  let busy = false;
  if (o && o.type === 'plant' && a.arrived && b.hasCharge && objInSite(b.pos.x, b.pos.z)) {
    b.planting = !engaged; busy = b.planting;
  } else b.planting = false;
  if (o && o.type === 'defuse' && cs.state === 'planted' && Math.hypot(b.pos.x - cs.pos.x, b.pos.z - cs.pos.z) < CHARGE.useDist - 0.25) {
    const commit = roundT < defuseTime(b) - b.useT + 2 || b.useT > defuseTime(b) * 0.55 || !units.some(u => u.alive && u.side === 'atk');
    b.defusing = !engaged || commit; busy = b.defusing;
  } else b.defusing = false;
  if (!engaged && a.wasEngaged) a.lostT = gt;
  a.wasEngaged = !!engaged;

  if (busy) {
    still = true; crouch = true;
    desiredYaw = engaged ? yawTo(b.pos.x, b.pos.z, t.pos.x, t.pos.z) : yawTo(b.pos.x, b.pos.z, cs.state === 'planted' ? cs.pos.x : b.pos.x - Math.sin(b.yaw), cs.state === 'planted' ? cs.pos.z : b.pos.z - Math.cos(b.yaw));
    if (b.ammo[b.cur].mag < w.mag * 0.5 && b.reloading === 0) startReload(b);
  } else if (engaged) {
    const dist = Math.hypot(t.pos.x - b.pos.x, t.pos.z - b.pos.z);
    desiredYaw = yawTo(b.pos.x, b.pos.z, t.pos.x, t.pos.z);
    aimPitch = Math.atan2((t.pos.y + (t.crouch ? 0.9 : 1.3)) - (b.pos.y + 1.4), dist);
    b.reactT -= dt;
    if (b.ammo[b.cur].mag === 0 && b.reloading === 0) { startReload(b); aiRetreat(b, t, 'reload'); }
    if (b.hp < D.retreat && !a.retreat && !(o && (o.type === 'defuse' || o.type === 'plant'))) aiRetreat(b, t, 'hp');
    if (a.retreat) {
      // отход, отстреливаясь
      const r = a.retreat;
      const mv = aiSteer(b, r, r.path || [], r.cell, aiX(r.cell), aiZ(r.cell));
      if (mv && aiDist(r.cell, b.pos.x, b.pos.z) > 0.5) { mvx = mv[0]; mvz = mv[1]; moving = true; }
    } else {
      const holding = o && a.arrived;
      b.strafeT -= dt;
      if (b.strafeT <= 0) {
        // держащий позицию стреляет стоя на месте (так точнее), лишь изредка смещается
        if (holding) { b.strafeT = rand(0.4, 0.9); b.strafeDir = Math.random() < 0.8 + D.peek * 0.15 ? 0 : (Math.random() < 0.5 ? -1 : 1); }
        else { b.strafeT = rand(0.35, 1.1); b.strafeDir = Math.random() < (w.scope ? 0.75 : 0.3) ? 0 : (Math.random() < 0.5 ? -1 : 1); }
        a.engCrouch = holding && !w.scope && !w.pellets && Math.random() < 0.25 + D.peek * 0.25;
      }
      if (b.strafeDir) { mvx = Math.cos(desiredYaw) * b.strafeDir; mvz = -Math.sin(desiredYaw) * b.strafeDir; speed *= holding ? 0.45 : 0.6; }
      else crouch = a.engCrouch;
      if (w.pellets && dist > 9) { mvx += -Math.sin(desiredYaw) * 0.8; mvz += -Math.cos(desiredYaw) * 0.8; crouch = false; }
    }
    if (Math.abs(angDiff(desiredYaw, b.yaw)) < 0.18 && b.reactT <= 0) botShoot(b, t);
    b.path = null;
  } else {
    if (b.target && !b.target.alive) b.target = null;
    if (blind) { // ослеплён: пятится и не стреляет
      mvx = Math.sin(b.yaw) * 0.6; mvz = Math.cos(b.yaw) * 0.6; speed *= 0.5;
    } else if (a.retreat) {
      const r = a.retreat;
      if (b.ammo[b.cur].mag < w.mag && b.reloading === 0 && b.ammo[b.cur].res > 0) startReload(b);
      const dd = aiDist(r.cell, b.pos.x, b.pos.z);
      if (dd > 0.5) { const mv = aiSteer(b, r, r.path || [], r.cell, aiX(r.cell), aiZ(r.cell)); if (mv) { mvx = mv[0]; mvz = mv[1]; moving = true; desiredYaw = yawTo(b.pos.x, b.pos.z, b.pos.x + mvx, b.pos.z + mvz); } }
      else { still = true; crouch = r.why === 'hp'; desiredYaw = yawTo(b.pos.x, b.pos.z, r.wx, r.wz); }
      if (gt > r.until && b.reloading === 0) a.retreat = null;
    } else {
      if (b.ammo[b.cur].mag < w.mag * 0.6 && b.reloading === 0 && (!o || a.arrived || gt - a.lostT > 1.5)) startReload(b);
      if (!o && b.lastSeenT > 0 && gt - a.lostT < 6) aiGive(b, 'hunt', aiCellAt(b.lastSeen.x, b.lastSeen.z), null, { tag: 'hunt', until: gt + 5 });
      const oo = a.order && gt >= a.order.start ? a.order : null;
      if (oo) {
        const last = oo.k >= oo.cells.length - 1;
        let goal = oo.cells[oo.k], gx = aiX(goal), gz = aiZ(goal);
        if (last && (oo.type === 'defuse' || oo.type === 'pickup') && cs.state !== 'none') { gx = cs.pos.x; gz = cs.pos.z; }
        const gd = Math.hypot(gx - b.pos.x, gz - b.pos.z);
        const near = oo.type === 'defuse' ? CHARGE.useDist - 0.5 : oo.type === 'pickup' ? 0.7 : 0.55;
        if (a.arrived && gd > 1.8 && oo.type !== 'flee') a.arrived = false;
        if (!a.arrived && gd < near) {
          if (!last) { oo.k++; a.path = null; }
          else { a.arrived = true; if (oo.type === 'hunt') a.order = null; }
        }
        if (!a.arrived) {
          if (!a.path || a.pathGoal !== goal) {
            a.path = aiPath(aiCellAt(b.pos.x, b.pos.z), goal, a.noise); a.pi = 0; a.pathGoal = goal;
            if (!a.path) { a.order = null; a.path = null; }
          }
          if (a.path) {
            const mv = aiSteer(b, a, a.path, goal, gx, gz);
            if (mv) { mvx = mv[0]; mvz = mv[1]; moving = true; desiredYaw = yawTo(b.pos.x, b.pos.z, b.pos.x + mvx, b.pos.z + mvz); }
            // в конце пути — разворот туда, куда смотреть
            if (last && oo.watch && gd < 3) desiredYaw = yawTo(b.pos.x, b.pos.z, oo.watch.x, oo.watch.z);
          }
        } else {
          still = true;
          if (oo.watch) desiredYaw = yawTo(b.pos.x, b.pos.z, oo.watch.x, oo.watch.z) + Math.sin(gt * 0.7 + a.sweep) * 0.32;
          crouch = oo.crouch && !w.scope;
          if (oo.type === 'flee') crouch = false;
        }
      }
      // взгляд: недавний контакт важнее
      if (b.lastSeenT > 0 && (b.alertT > 0 || still)) desiredYaw = yawTo(b.pos.x, b.pos.z, b.lastSeen.x, b.lastSeen.z);
      else if (!moving || Math.random() < 0.02) {
        const T = AI.teams[b.team];
        if (T) for (const s of aiFresh(T, 3)) if (Math.hypot(s.x - b.pos.x, s.z - b.pos.z) < 22 && los(b.pos.x, 1.6, b.pos.z, s.x, 1.4, s.z)) { desiredYaw = yawTo(b.pos.x, b.pos.z, s.x, s.z); break; }
      }
      // гранаты: план от штаба или осколочная в укрытие, где пропал противник
      if (a.nadeCd <= 0 && b.aiNades) {
        const np = a.nadePlan;
        if (np && b.aiNades[np.type]) {
          const d = Math.hypot(np.x - b.pos.x, np.z - b.pos.z);
          const atOk = np.at === undefined || aiDist(np.at, b.pos.x, b.pos.z) < 9;
          if (d < (np.near || 20) + 6 && atOk) { aiThrow(b, np.type, np.x, np.y, np.z); a.nadePlan = null; }
        } else if (b.aiNades.he && b.lastSeenT > 1 && b.lastSeenT < 4 && gt - a.lostT > 0.8 && Math.random() < D.nade * 0.08) {
          const d = Math.hypot(b.lastSeen.x - b.pos.x, b.lastSeen.z - b.pos.z);
          if (d > 7 && d < 26) aiThrow(b, 'he', b.lastSeen.x, 0.5, b.lastSeen.z);
        }
      }
    }
  }
  // выход из застревания: короткий рывок в случайную сторону и новый путь
  if (a.unstuckT > 0) { a.unstuckT -= dt; mvx = a.ux; mvz = a.uz; still = false; moving = false; }
  if (moving) {
    a.progT += dt;
    if (a.progT > 1.1) {
      const moved = Math.hypot(b.pos.x - a.progX, b.pos.z - a.progZ);
      if (moved < 0.4) {
        a.stuckN++; aiStats.stuck++; a.path = null; if (a.retreat) a.retreat = null;
        const ang = rand(0, Math.PI * 2); a.ux = Math.cos(ang); a.uz = Math.sin(ang); a.unstuckT = 0.45;
        a.noise = aiNoise();
        if (a.stuckN >= 3) { aiStats.hardStuck++; a.stuckN = 0; a.order = null; }
      } else a.stuckN = Math.max(0, a.stuckN - 1);
      a.progT = 0; a.progX = b.pos.x; a.progZ = b.pos.z;
    }
  } else { a.progT = 0; a.progX = b.pos.x; a.progZ = b.pos.z; }
  // разведение с союзниками: не стоять и не идти вплотную друг за другом
  if (!busy) {
    let sx = 0, sz = 0;
    for (const m of units) {
      if (m === b || !m.alive || m.team !== b.team) continue;
      const dx = b.pos.x - m.pos.x, dz = b.pos.z - m.pos.z, d2 = dx * dx + dz * dz;
      if (d2 < 1.69 && d2 > 1e-6) { const d = Math.sqrt(d2); sx += dx / d * (1.3 - d); sz += dz / d * (1.3 - d); }
    }
    if (sx || sz) { mvx += sx * 1.6; mvz += sz * 1.6; if (still) speed *= 0.5; }
  }
  if (busy) { mvx = 0; mvz = 0; }
  b.crouch = crouch && !moving;
  if (b.crouch) speed *= 0.5;
  b.aimPitch += (clamp(aimPitch, -0.6, 0.6) - b.aimPitch) * Math.min(1, dt * 8);
  const da = angDiff(desiredYaw, b.yaw), turn = D.turn * dt;
  b.yaw += clamp(da, -turn, turn);
  const ml = Math.hypot(mvx, mvz); if (ml > 1) { mvx /= ml; mvz /= ml; }
  b.vx += (mvx * speed - b.vx) * Math.min(1, dt * 10); b.vz += (mvz * speed - b.vz) * Math.min(1, dt * 10);
  if (busy) { b.vx *= 0.5; b.vz *= 0.5; }
  b.pos.x += b.vx * dt; b.pos.z += b.vz * dt;
  collide(b.pos, RAD); collide(b.pos, RAD);
  syncBotMesh(b, dt, Math.hypot(b.vx, b.vz));
}
