'use strict';
/* ---------------- гранаты, дым, ослепление; общий боевой тик ---------------- */
// Контракт: throwGrenade(unit, type, dirVec3[, power 0..1]) → true при броске (тратит гранату из unit.ammo[type]);
// smokeBlocks(ax, ay, az, bx, by, bz) → true, если отрезок проходит сквозь дым; buyGrenade(unit, type) → true при покупке.
// Ослепление: unit.flashT (сек) уменьшается здесь, в combatTick; unit.flashMax — исходная длительность.
const nades = [], smokes = [];
const hasGrenade = (u, t) => !!(u.ammo[t] && u.ammo[t].mag > 0);
function addGrenade(u, t, n = 1) {
  const a = u.ammo[t] || (u.ammo[t] = { mag: 0, res: '—' });
  a.mag = Math.min(WEAPONS[t].max, a.mag + n);
}
function buyGrenade(u, type) {
  const w = WEAPONS[type]; if (!w || !w.grenade) return false;
  if (u.ammo[type] && u.ammo[type].mag >= w.max) return false;
  if (mode.rounds) {
    if (u.money < w.price) return false;
    if (u.isPlayer && typeof canBuy === 'function' && !canBuy()) return false;
    u.money -= w.price;
  }
  addGrenade(u, type);
  if (u.isPlayer) beep(880, 0.06, 0.08, 'triangle');
  return true;
}
function throwGrenade(u, type, dir, power = 1) {
  if (!u || !u.alive || !WEAPONS[type] || !WEAPONS[type].grenade || !hasGrenade(u, type)) return false;
  const a = u.ammo[type]; a.mag--;
  if (a.mag <= 0) delete u.ammo[type];
  const d = dir.clone(); if (d.lengthSq() < 1e-6) d.set(-Math.sin(u.yaw), 0.2, -Math.cos(u.yaw)); d.normalize();
  const sp = 15 * clamp(power, 0.25, 1.2);
  const pos = V3(u.pos.x + d.x * 0.35, unitEyeY(u) - 0.12, u.pos.z + d.z * 0.35);
  if (chAt(pos.x, pos.z) !== '.' && TOPS[chAt(pos.x, pos.z)] > pos.y) pos.set(u.pos.x, unitEyeY(u) - 0.12, u.pos.z);
  const g = gunGroup(type, GUNS[type].full); g.position.copy(pos); scene.add(g);
  nades.push({ type, pos, vel: d.multiplyScalar(sp).add(V3(u.vx * 0.5, 0, u.vz * 0.5)), t: 0, owner: u, g, spin: V3(rand(-12, 12), rand(-8, 8), rand(-12, 12)), still: 0 });
  sfxThrow(u.isPlayer ? null : u.pos);
  if (!u.isPlayer && u.mesh) { u.mesh.anim.throwT = 0.6; u.mesh.throwKey = type; }
  if (u.cur === type && !u.ammo[type] && !u.isPlayer) equip(u, u.primary && u.ammo[u.primary] ? u.primary : 'pistol');
  return true;
}
const nadeSolid = (x, y, z) => { const ch = chAt(x, z); if (ch === '.') return false; const t = TOPS[ch]; return t === undefined ? true : y < t; };
const nadeFloor = (x, z, y) => { const ch = chAt(x, z); if (ch === '.') return 0; const t = TOPS[ch]; return t !== undefined && t <= y + 0.08 ? t : 0; };
function stepNade(n, h) {
  const R = 0.05, v = n.vel, p = n.pos;
  v.y -= 15 * h;
  let hitK = 0;
  const nx = p.x + v.x * h; if (nadeSolid(nx + Math.sign(v.x) * R, p.y, p.z)) { hitK = Math.abs(v.x); v.x *= -0.42; v.z *= 0.8; v.y *= 0.9; } else p.x = nx;
  const nz2 = p.z + v.z * h; if (nadeSolid(p.x, p.y, nz2 + Math.sign(v.z) * R)) { hitK = Math.max(hitK, Math.abs(v.z)); v.z *= -0.42; v.x *= 0.8; v.y *= 0.9; } else p.z = nz2;
  const ny = p.y + v.y * h, fl = nadeFloor(p.x, p.z, p.y);
  if (ny < fl + R) {
    p.y = fl + R;
    if (v.y < -1.8) { hitK = Math.max(hitK, -v.y); v.y *= -0.38; v.x *= 0.7; v.z *= 0.7; }
    else { v.y = 0; const f = Math.exp(-5 * h); v.x *= f; v.z *= f; }
  } else p.y = ny;
  if (hitK > 2) { sfxBounce(p, Math.min(1, hitK / 10)); n.spin.multiplyScalar(0.6); }
}
function updateNades(dt) {
  for (let i = nades.length - 1; i >= 0; i--) {
    const n = nades[i], W = WEAPONS[n.type];
    n.t += dt;
    const sp = n.vel.length(), steps = Math.max(1, Math.ceil(sp * dt / 0.08));
    for (let s = 0; s < steps; s++) stepNade(n, dt / steps);
    n.g.position.copy(n.pos);
    if (sp > 0.3) { n.g.rotation.x += n.spin.x * dt; n.g.rotation.y += n.spin.y * dt; n.g.rotation.z += n.spin.z * dt; }
    n.still = sp < 0.4 ? n.still + dt : 0;
    const boom = n.type === 'smoke' ? (n.t > W.fuse && n.still > 0.25) || n.t > 4 : n.t > W.fuse;
    if (!boom) continue;
    nades.splice(i, 1); scene.remove(n.g);
    if (n.type === 'he') explodeHE(n); else if (n.type === 'flash') explodeFlash(n); else spawnSmoke(n.pos);
  }
}
function explodeHE(n) {
  const W = WEAPONS.he, p = n.pos;
  explosionFx(p); sfxExplode(p); hearNoise(n.owner, 30);
  for (const u of units) {
    if (!u.alive) continue;
    const cy = unitChestY(u), d = Math.hypot(u.pos.x - p.x, cy - p.y - 0.3, u.pos.z - p.z);
    if (u.isPlayer) vmState.shake = Math.max(vmState.shake || 0, clamp(1.2 - d / 14, 0, 1));
    if (d > W.radius || (u.team === n.owner.team && u !== n.owner)) continue;
    if (!los(p.x, p.y + 0.3, p.z, u.pos.x, cy, u.pos.z)) continue;
    const dmg = W.dmg * Math.pow(1 - d / W.radius, 1.3);
    if (dmg > 1) hitUnit(u, n.owner, 'he', 'body', d, 1, dmg);
  }
}
const _fd = new THREE.Vector3();
function explodeFlash(n) {
  const W = WEAPONS.flash, p = n.pos;
  worldFlash(p.clone().add(V3(0, 0.2, 0)), 7, 0.12); burst(p, 0xffffff, 8, 4);
  sfxFlashBang(p); hearNoise(n.owner, 25);
  for (const u of units) {
    if (!u.alive) continue;
    const ey = unitEyeY(u), d = Math.hypot(u.pos.x - p.x, ey - p.y, u.pos.z - p.z);
    if (d > W.radius) continue;
    if (!los(p.x, p.y + 0.15, p.z, u.pos.x, ey, u.pos.z) || smokeBlocks(p.x, p.y + 0.15, p.z, u.pos.x, ey, u.pos.z)) continue;
    let fx, fy, fz;
    if (u.isPlayer) { camera.getWorldDirection(_fd); fx = _fd.x; fy = _fd.y; fz = _fd.z; }
    else { const pt = u.aimPitch || 0; fx = -Math.sin(u.yaw) * Math.cos(pt); fy = Math.sin(pt); fz = -Math.cos(u.yaw) * Math.cos(pt); }
    const dot = ((p.x - u.pos.x) * fx + (p.y - ey) * fy + (p.z - u.pos.z) * fz) / (d || 1);
    const angF = dot > 0.55 ? 1 : dot > 0 ? 0.45 + dot : 0.12 + (dot + 1) * 0.2;
    const distF = 1 - Math.pow(d / W.radius, 1.6);
    const T = 4.6 * angF * distF * (d < 2 ? 1.15 : 1);
    if (T < 0.25) continue;
    u.flashT = Math.max(u.flashT || 0, T); u.flashMax = Math.max(u.flashT, u.flashMax || 0);
    if (u.isPlayer) flashMuffle(Math.min(5, T * 0.9 + 0.8));
    else { u.targetVisible = false; u.reactT = Math.max(u.reactT || 0, 0.5); }
  }
}
/* ---------------- дым ---------------- */
const SMOKE_LIFE = 15;
function spawnSmoke(pos) {
  const W = WEAPONS.smoke, mat = new THREE.SpriteMaterial({ map: smokeTex, color: 0xbab9b3, transparent: true, depthWrite: false, opacity: 0, fog: true });
  const sm = { pos: pos.clone(), t: 0, R: W.radius, sprites: [], mat };
  sm.pos.y = nadeFloor(pos.x, pos.z, pos.y + 0.1);
  for (let i = 0; i < 18; i++) {
    let x, y, z, tries = 0;
    do { const a = rand(0, 6.28), r = Math.sqrt(Math.random()) * sm.R * 0.8; x = sm.pos.x + Math.cos(a) * r; z = sm.pos.z + Math.sin(a) * r; y = sm.pos.y + rand(0.4, 2.6); tries++; }
    while (nadeSolid(x, y, z) && tries < 8);
    const s = new THREE.Sprite(mat); s.userData = { off: V3(x - sm.pos.x, y - sm.pos.y, z - sm.pos.z), sc: rand(2.6, 3.6), rot: rand(-0.2, 0.2) };
    s.position.set(sm.pos.x, sm.pos.y + 0.3, sm.pos.z); s.scale.setScalar(0.3); scene.add(s); sm.sprites.push(s);
  }
  smokes.push(sm); sfxSmoke(sm.pos);
}
function updateSmokes(dt) {
  for (let i = smokes.length - 1; i >= 0; i--) {
    const sm = smokes[i]; sm.t += dt;
    if (sm.t > SMOKE_LIFE) { for (const s of sm.sprites) scene.remove(s); sm.mat.dispose(); smokes.splice(i, 1); continue; }
    const g = smokeGrow(sm), fade = clamp((SMOKE_LIFE - sm.t) / 2.5, 0, 1);
    sm.mat.opacity = 0.9 * Math.min(1, g * 1.4) * fade;
    for (const s of sm.sprites) {
      const o = s.userData.off;
      s.position.set(sm.pos.x + o.x * g, sm.pos.y + 0.2 + (o.y - 0.2) * Math.min(1, g * 1.2) + Math.sin(sm.t * 0.4 + o.x) * 0.08, sm.pos.z + o.z * g);
      s.scale.setScalar(s.userData.sc * (0.35 + 0.65 * g));
    }
    sm.mat.rotation += dt * 0.05;
  }
}
const smokeGrow = sm => clamp(sm.t / 1.6, 0, 1);
// расстояние до облака в «нормированных» единицах (облако — эллипсоид R × 1.6 м по высоте)
function smokeBlocks(ax, ay, az, bx, by, bz) {
  for (const sm of smokes) {
    const g = smokeGrow(sm); if (g < 0.45 || sm.t > SMOKE_LIFE - 1.2) continue;
    const r = sm.R * 0.92 * g, cy = sm.pos.y + 1.4, ky = r / 1.6;
    const px = ax - sm.pos.x, py = (ay - cy) * ky, pz = az - sm.pos.z;
    const dx = bx - ax, dy = (by - ay) * ky, dz = bz - az;
    const L2 = dx * dx + dy * dy + dz * dz || 1e-6;
    const t = clamp(-(px * dx + py * dy + pz * dz) / L2, 0, 1);
    const qx = px + dx * t, qy = py + dy * t, qz = pz + dz * t;
    if (qx * qx + qy * qy + qz * qz < r * r) return true;
  }
  return false;
}
function smokeDensityAt(x, y, z) {
  let best = 0;
  for (const sm of smokes) {
    const g = smokeGrow(sm), r = sm.R * 0.95 * g; if (r < 0.3) continue;
    const fade = clamp((SMOKE_LIFE - sm.t) / 2.5, 0, 1);
    const d = Math.hypot(x - sm.pos.x, (y - sm.pos.y - 1.3) * (r / 1.6), z - sm.pos.z) / r;
    best = Math.max(best, clamp((1.05 - d) * 2.2, 0, 1) * fade);
  }
  return best;
}
function clearNades() {
  for (const n of nades) scene.remove(n.g); nades.length = 0;
  for (const sm of smokes) { for (const s of sm.sprites) scene.remove(s); sm.mat.dispose(); } smokes.length = 0;
}

/* ---------------- экранные эффекты игрока ---------------- */
injectCSS('combat', `
#flashOv,#smokeOv{position:absolute;inset:0;pointer-events:none;opacity:0;z-index:4}
#flashOv{background:#fff}
#smokeOv{background:radial-gradient(circle at 50% 50%,rgba(176,176,170,.92),rgba(160,160,154,.98))}
`);
const flashOv = document.createElement('div'); flashOv.id = 'flashOv';
const smokeOv = document.createElement('div'); smokeOv.id = 'smokeOv';
{ const hud = document.getElementById('hud') || document.body; hud.prepend(smokeOv); hud.prepend(flashOv); }
let ovF = -1, ovS = -1;
function updateOverlays() {
  const p = player, f = p && p.alive ? clamp(p.flashT / 1.3, 0, 1) : 0;
  const s = p && p.alive ? smokeDensityAt(camera.position.x, camera.position.y, camera.position.z) * 0.96 : 0;
  const fr = Math.round(f * 100) / 100, sr = Math.round(s * 100) / 100;
  if (fr !== ovF) { flashOv.style.opacity = fr; ovF = fr; }
  if (sr !== ovS) { smokeOv.style.opacity = sr; ovS = sr; }
}

/* ---------------- граната в руке игрока ---------------- */
// fire: выдернуть чеку и держать, отпустить — бросок; прицел — короткий бросок под ноги
function updatePlayerGrenade(dt) {
  const p = player, w = weaponOf(p), N = vmState.nade;
  if (!w.grenade || !p.alive) { N.st = 'idle'; N.t = 0; return; }
  if (p.scoped) { p.scoped = false; if (N.st === 'idle' && state !== 'freeze') { N.st = 'pin'; N.t = 0; N.lob = true; sfxPin(); } }
  N.t += dt;
  if (N.st === 'idle') { if (input.fire && state !== 'freeze' && vmState.swap < 0.3) { N.st = 'pin'; N.t = 0; N.lob = false; sfxPin(); } }
  else if (N.st === 'pin') { if (N.t > 0.38) { N.st = 'ready'; N.t = 0; } }
  else if (N.st === 'ready') { if (!input.fire || N.lob) { N.st = 'throw'; N.t = 0; N.done = false; } }
  else if (N.st === 'throw') {
    if (!N.done && N.t > 0.12) {
      N.done = true;
      camera.getWorldDirection(_fd); _fd.y += N.lob ? 0.05 : 0.12;
      throwGrenade(p, p.cur, _fd, N.lob ? 0.42 : 1);
    }
    if (N.t > 0.5) {
      N.st = 'idle'; N.t = 0;
      if (p.ammo[p.cur]) { vmState.swap = 1; }
      else { const back = p._prevCur && p.ammo[p._prevCur] && !WEAPONS[p._prevCur].grenade ? p._prevCur : p.primary && p.ammo[p.primary] ? p.primary : 'pistol'; equip(p, back); }
    }
  }
}
// следующая граната по кругу (кнопка интерфейса action:grenade, клавиша 4)
function cycleGrenade(u) {
  if (!u.alive) return;
  const have = GRENADES.filter(t => hasGrenade(u, t)); if (!have.length) return;
  const i = have.indexOf(u.cur), next = have[(i + 1) % have.length];
  if (!WEAPONS[u.cur].grenade) u._prevCur = u.cur;
  if (next !== u.cur) { equip(u, next); vmState.nade.st = 'idle'; sfxDraw(); }
}

/* ---------------- появление и раунды ---------------- */
function onSpawn(u) {
  u.flashT = 0; u.flashMax = 0; u.boltT = 0; u.rescope = false;
  if (!u.ammo.knife) u.ammo.knife = { mag: '—', res: '—' };
  if (!mode.rounds) { u.helmet = true; addGrenade(u, 'he'); addGrenade(u, 'flash'); if (Math.random() < 0.5) addGrenade(u, 'smoke'); }
  else if (u.armor <= 0) u.helmet = false;
  if (u.mesh) { u.mesh.anim.die = 0; u.mesh.anim.throwT = 0; }
}
bus.on('round:start', () => {
  clearDrops(); clearNades();
  for (const u of units) {
    if (u.armor <= 0) u.helmet = false;
    u.flashT = 0;
    if (u.isPlayer) continue;
    if (u.armor > 0 && !u.helmet && u.money >= HELMET_PRICE && Math.random() < 0.75) { u.money -= HELMET_PRICE; u.helmet = true; }
    for (const [t, pr] of [['flash', 0.55], ['he', 0.45], ['smoke', 0.35], ['flash', 0.25]]) if (Math.random() < pr) buyGrenade(u, t);
  }
});
// шаги ботов: слышно и сзади (панорама, приглушение)
function botSteps() {
  for (const b of bots) {
    if (!b.alive) continue;
    const sp = Math.hypot(b.vx, b.vz), ph = Math.floor(b.walkPhase / Math.PI);
    if (ph !== b._stepPh) {
      b._stepPh = ph;
      if (sp > 2.7 && !b.crouch && !b.walk) sfxStep(b.pos, b.team === player.team ? 0.45 : 0.9);
    }
  }
}
// общий тик боя: вызывается из updatePlayer каждый кадр (после логики ботов)
let _tickUnits = null;
function combatTick(dt) {
  if (_tickUnits !== units) { _tickUnits = units; clearDrops(); clearNades(); for (const u of units) u._alive = false; }
  for (const u of units) {
    if (u.alive && !u._alive) onSpawn(u);
    u._alive = u.alive;
    if (u.alive) { if (u.primary) u._lastPrimary = u.primary; if (!u.ammo.knife) u.ammo.knife = { mag: '—', res: '—' }; }
    if (u.flashT > 0) u.flashT = Math.max(0, u.flashT - dt);
    if (!u.alive && u.mesh && u.deathT > 0) deathPose(u, dt);
  }
  updateDrops(dt); botPickups(dt);
  updateNades(dt); updateSmokes(dt);
  botSteps(); updatePlayerPickup(); updateOverlays();
}
