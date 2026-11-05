'use strict';
/* ---------------- стрельба ---------------- */
const ray = new THREE.Raycaster(); ray.far = 200;
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _q = new THREE.Vector3(), _r = new THREE.Vector3(), _u = new THREE.Vector3(), _w = new THREE.Vector3();
const isGun = w => !w.melee && !w.grenade;
// высота глаз и груди бойца с учётом приседа (для ИИ и прицеливания ботов)
const unitEyeY = u => u.pos.y + (u.crouch ? 1.16 : 1.62);
const unitChestY = u => u.pos.y + (u.crouch ? 0.86 : 1.25);
const unitHeadY = u => u.pos.y + (u.crouch ? 1.2 : 1.72);

function startReload(u) {
  const w = weaponOf(u), a = u.ammo[u.cur];
  if (!isGun(w) || !a || u.reloading > 0 || a.mag >= w.mag || a.res <= 0) return;
  u.reloading = w.reload; u.scoped = false; u.sprayN = 0; u.reloadStep = 0;
  if (!u.isPlayer) sfxMagOut(u.pos);
}
function finishReload(u) {
  const w = weaponOf(u), a = u.ammo[u.cur]; if (!a || !isGun(w)) return;
  const take = Math.min(w.mag - a.mag, a.res);
  a.mag += take; a.res -= take;
  if (!u.isPlayer && u.alive) sfxMagIn(u.pos);
}
function currentSpread(u) {
  const w = weaponOf(u); if (!isGun(w)) return 0;
  let s = w.spread;
  if (w.scope) s = u.scoped && (u.scopeT === undefined || u.scopeT > 0.12) ? w.scopedSpread : w.spread;
  else if (u.scoped) s *= w.pellets ? 0.8 : 0.65;
  if (u.crouch && u.onGround) s *= 0.75;
  const sp = Math.hypot(u.vx, u.vz), full = 5.6 * (w.speed || 1);
  s += w.moveSpread * clamp((sp - 1.15) / (full - 1.15), 0, 1) * (u.crouch ? 0.8 : 1);
  if (!u.onGround) s += w.jump || 0.1;
  s += (w.spray || 0) * Math.min(u.sprayN || 0, 10);
  return s;
}
// смещение взгляда по узору отдачи для дробного номера пули
function recoilAt(w, n) {
  const p = w.pattern; if (!p || n <= 0) return [0, 0];
  const i = Math.min(p.length - 1, Math.floor(n)), j = Math.min(p.length - 1, i + 1), f = n - Math.floor(n);
  return [p[i][0] + (p[j][0] - p[i][0]) * f, p[i][1] + (p[j][1] - p[i][1]) * f];
}

/* ---------------- урон: броня, шлем, дальность, пробитие ---------------- */
// Урон считаем здесь, а applyDamage (match.js) вызываем с подменой параметров оружия так, чтобы итог совпал:
// броня гасит (1 - armorPen) урона по корпусу; шлем — по голове; без шлема голова и ноги не защищены.
// u.helmet — шлем куплен. extraMult — множитель (пробитие, нож). override — готовый урон до брони (гранаты).
function hitUnit(victim, attacker, key, part, dist, extraMult = 1, override) {
  if (!victim.alive || victim.protT > 0) return 0;
  const W = WEAPONS[key];
  let dmg;
  if (override !== undefined) dmg = override;
  else {
    const fall = W.falloff ? clamp(1.25 - dist / W.falloff, 0.15, 1) : W.rangeMod ? Math.pow(W.rangeMod, dist / 10) : 1;
    dmg = W.dmg * fall * (part === 'head' ? W.head * (victim.helmet ? 1 : 1.15) : part === 'legs' ? 0.75 : 1);
  }
  dmg *= extraMult;
  const prot = victim.armor > 0 && (part === 'body' || (part === 'head' && victim.helmet));
  let armorLoss = 0;
  if (prot) { const ab = Math.min(victim.armor * 2, dmg * (1 - (W.armorPen !== undefined ? W.armorPen : 0.5))); dmg -= ab; armorLoss = ab * 0.5; }
  const savedArmor = victim.armor, sd = W.dmg, sh = W.head, sf = W.falloff;
  hitCtx = { helmet: part === 'head' && prot, armor: prot };
  victim.armor = 0; W.dmg = part === 'legs' ? dmg / 0.75 : dmg; W.head = 1; W.falloff = 0;
  try { applyDamage(victim, attacker, key, part, 0); }
  finally { W.dmg = sd; W.head = sh; W.falloff = sf; victim.armor = Math.max(0, savedArmor - armorLoss); }
  if (victim.isPlayer && part === 'head' && prot) sfxHit(true);
  return dmg;
}
// материал укрытия по месту попадания: { pen: множитель урона после пробития, loss: потеря на метр, kind }
// Карта может задать свой материал: mesh.userData.pen / .matKind, или глобальный MAT_PEN = { символ клетки: {pen, loss, kind} }.
function levelMat(h, dir) {
  const ud = h.object.userData || {};
  if (ud.pen !== undefined) return { pen: ud.pen, loss: ud.loss || 0.1, kind: ud.matKind || 'wood', ch: null };
  const px = h.point.x + dir.x * 0.06, pz = h.point.z + dir.z * 0.06, ch = chAt(px, pz);
  if (h.point.y < 0.03 && Math.abs(dir.y) > 0.05) return { pen: 0, kind: 'stone', ch };
  if (typeof MAT_PEN === 'object' && MAT_PEN && MAT_PEN[ch]) return Object.assign({ ch }, MAT_PEN[ch]);
  if (ch === 'c') return { pen: 0.75, loss: 0.12, kind: 'wood', ch };
  if (ch === 'C') return { pen: 0.62, loss: 0.08, kind: 'metal', ch };
  if (ch === '#' || ch === '.' || TOPS[ch] === undefined || TOPS[ch] >= 3.5) return { pen: 0, kind: 'stone', ch };
  return { pen: 0.7, loss: 0.12, kind: 'wood', ch };
}
function solidThickness(p, dir, ch) {
  let t = 0; const top = TOPS[ch] !== undefined ? TOPS[ch] : 99;
  for (; t < 3.2; t += 0.05) {
    const x = p.x + dir.x * t, y = p.y + dir.y * t, z = p.z + dir.z * t;
    if (chAt(x, z) !== ch || y > top || y < 0) break;
  }
  return t;
}
// луч пули: урон первому врагу, пробитие тонких укрытий (не больше двух), следы. Возвращает конечную точку.
function fireRay(shooter, origin, dir, key, fx) {
  const w = WEAPONS[key];
  ray.set(origin, dir); ray.far = 200;
  const targets = levelMeshes.slice();
  for (const b of units) if (b.alive && b !== shooter && b.mesh) targets.push(...b.mesh.hit);
  const hits = ray.intersectObjects(targets, false);
  let mult = 1, pens = 0, skip = -1;
  const seen = new Set();
  for (const h of hits) {
    if (h.distance < skip) continue;
    const tu = h.object.userData.unit;
    if (tu) {
      if (seen.has(tu)) continue; seen.add(tu);
      if (tu.team !== shooter.team) { hitUnit(tu, shooter, key, h.object.userData.part, h.distance, mult); if (fx) bloodFx(h.point, dir); }
      return h.point;
    }
    const m = levelMat(h, dir);
    if (fx) impactFx(h, dir, m.kind);
    if (!m.pen || pens >= 2 || !w.pen) return h.point;
    const th = m.ch ? solidThickness(h.point, dir, m.ch) : 0.1;
    mult *= Math.pow(m.pen, 1 / w.pen) * Math.max(0, 1 - th * m.loss / w.pen);
    if (mult < 0.12) return h.point;
    pens++; skip = h.distance + th + 0.03;
    if (fx) { _w.copy(h.point).addScaledVector(dir, th + 0.02); puff(_w, m.kind === 'wood' ? 0x9a7a52 : 0x9a9a98, 0.1, 0.45, 0.45, 0.5, dir.x, 0.3, dir.z); }
  }
  return null;
}

/* ---------------- игрок ---------------- */
function playerShoot() {
  const u = player, w = weaponOf(u), a = u.ammo[u.cur];
  if (w.melee) return meleeAttack(u, false);
  if (w.grenade || !a) return false;
  if (u.reloading > 0 || gt < u.nextShot || u.boltT > 0) return false;
  if (a.mag <= 0) { sfxClick(); startReload(u); u.nextShot = gt + 0.25; return false; }
  a.mag--; u.nextShot = gt + w.rate; u.protT = 0;
  const spread = currentSpread(u);
  camera.updateMatrixWorld();
  camera.getWorldDirection(_v3);
  _r.set(1, 0, 0).applyQuaternion(camera.quaternion); _u.set(0, 1, 0).applyQuaternion(camera.quaternion);
  _q.copy(camera.position).addScaledVector(_v3, 0.6).addScaledVector(_r, 0.16).addScaledVector(_u, -0.14);
  const n = w.pellets || 1;
  for (let i = 0; i < n; i++) {
    const rr = spread * Math.sqrt(Math.random()), th = Math.random() * Math.PI * 2;
    _v.copy(_v3).addScaledVector(_r, Math.cos(th) * rr).addScaledVector(_u, Math.sin(th) * rr).normalize();
    const end = fireRay(u, camera.position, _v, u.cur, i < 3) || _v2.copy(camera.position).addScaledVector(_v, 120);
    if (n > 1 ? i < 3 : (Math.random() < 0.5 || w.scope)) tracer(_q, end);
  }
  u.sprayN = Math.min((w.pattern ? w.pattern.length - 1 : 12), (u.sprayN || 0) + 1);
  const vm = VM[u.cur];
  if (vm.flash.parent) { vm.flash.visible = true; vm.flashT = 0.045; vm.flash.material.rotation = Math.random() * 6; }
  vmState.kick = Math.min(1, vmState.kick + (w.scope || w.pellets ? 1 : 0.55));
  vmState.shotT = 1;
  if (w.pellets) { vmState.pump = 1; setTimeout(() => { sfxPump(null); ejectShell(u.cur); }, 260); }
  else if (w.bolt) { u.boltT = w.rate * 0.95; vmState.bolt = 1; u.rescope = u.scoped; u.scoped = false; setTimeout(() => { sfxSniperBolt(null); }, 200); setTimeout(() => { if (player.cur === 'sniper') ejectShell('sniper'); }, 520); }
  else ejectShell(u.cur);
  sfxGun(u.cur, null);
  makeNoise(u);
  if (a.mag === 0) setTimeout(() => { if (player.alive && player.ammo[player.cur] === a) startReload(player); }, 260);
  return true;
}
// звук выстрела: боты рядом настораживаются
function makeNoise(src) {
  const w = weaponOf(src);
  hearNoise(src, w && w.snd && w.snd.kind === 'supp' ? 14 : 34);
}
// шум в точке бойца (шаги, приземление, выстрелы): враги в радиусе узнают, где он
function hearNoise(src, radius) {
  for (const b of bots) {
    if (!b.alive || b.team === src.team || b.targetVisible) continue;
    if (Math.hypot(b.pos.x - src.pos.x, b.pos.z - src.pos.z) < radius) { b.alertT = 2.5; b.lastSeen.copy(src.pos); b.lastSeenT = 4; b.path = null; }
  }
}

/* ---------------- нож ---------------- */
// быстрый удар (heavy = false) и сильный (heavy = true). Удар в спину — почти смертелен.
function meleeAttack(u, heavy) {
  const w = WEAPONS.knife;
  if (gt < u.nextShot) return false;
  u.nextShot = gt + (heavy ? w.heavyRate : w.rate); u.protT = 0;
  const range = heavy ? w.heavyRange : w.range;
  let dirX, dirZ, eyeY = unitEyeY(u), pitch = u.isPlayer ? u.pitch : (u.aimPitch || 0);
  if (u.isPlayer) { camera.getWorldDirection(_v3); dirX = _v3.x; dirZ = _v3.z; const l = Math.hypot(dirX, dirZ) || 1; dirX /= l; dirZ /= l; }
  else { dirX = -Math.sin(u.yaw); dirZ = -Math.cos(u.yaw); }
  let best = null, bd = 1e9;
  for (const e of units) {
    if (!e.alive || e === u || e.team === u.team) continue;
    const dx = e.pos.x - u.pos.x, dz = e.pos.z - u.pos.z, d = Math.hypot(dx, dz);
    if (d > range + 0.35 || Math.abs(e.pos.y - u.pos.y) > 1.2) continue;
    const dot = (dx * dirX + dz * dirZ) / (d || 1);
    if (d > 0.5 && dot < 0.78) continue;
    if (d < bd) { bd = d; best = e; }
  }
  if (u.isPlayer) { vmState.melee = heavy ? -1 : 1; vmState.meleeT = heavy ? 0.7 : 0.42; vmState.slashSide = -vmState.slashSide || 1; }
  else if (u.mesh) u.mesh.anim.meleeT = 0.4;
  sfxSwing(u.isPlayer ? null : u.pos, heavy);
  const delay = heavy ? 220 : 90;
  setTimeout(() => {
    if (!u.alive) return;
    if (best && best.alive) {
      const behind = Math.abs(angDiff(best.yaw, yawTo(u.pos.x, u.pos.z, best.pos.x, best.pos.z))) < 1.0;
      const dmg = (heavy ? w.heavy : w.dmg) * (behind ? (heavy ? w.back * 1.1 : 1.6) : 1);
      hitUnit(best, u, 'knife', 'body', bd, 1, dmg);
      bloodFx(_w.set(best.pos.x, unitChestY(best), best.pos.z), null);
      sfxStab(u.isPlayer ? null : u.pos, true);
      if (!u.isPlayer) hearNoise(u, 6);
    } else if (u.isPlayer) {
      _v.set(dirX, Math.sin(pitch), dirZ).normalize();
      ray.set(camera.position, _v); ray.far = range;
      const h = ray.intersectObjects(levelMeshes, false)[0]; ray.far = 200;
      if (h) { decal(h, 0.6); burst(h.point, 0xffe0a0, 3); sfxStab(null, false); }
    }
  }, delay);
  return true;
}

/* ---------------- боты ---------------- */
function botShoot(b, t) {
  const w = weaponOf(b), a = b.ammo[b.cur];
  if (b.flashT > 0) return;
  const dist = Math.hypot(t.pos.x - b.pos.x, t.pos.z - b.pos.z);
  if (w.melee) { if (dist < w.range + 0.2) meleeAttack(b, Math.random() < 0.3); return; }
  if (w.grenade || !a) return;
  if (b.reloading > 0 || gt < b.nextShot) return;
  if (a.mag <= 0) { startReload(b); return; }
  a.mag--; b.burst++; b.protT = 0;
  let delay = w.rate * rand(1, 1.35);
  if (w.auto && b.burst >= (3 + (Math.random() * 4 | 0))) { b.burst = 0; delay += rand(0.25, 0.55); }
  if (!w.auto) delay = w.rate * rand(1.1, 1.6);
  b.nextShot = gt + delay;
  const D = DIFF[settings.diff];
  let p = D.acc * (w.botAcc || 1) * clamp(1.18 - dist / (w.scope ? 140 : 55), 0.12, 1);
  if (Math.hypot(t.vx, t.vz) > 2.5) p *= 0.75;
  if (Math.hypot(b.vx, b.vz) > 1) p *= 0.8;
  if (!t.onGround) p *= 0.7;
  if (t.crouch) p *= 0.85;
  if (b.crouch) p *= 1.12;
  if (w.scope && Math.hypot(b.vx, b.vz) > 0.5) p *= 0.3;
  const sm = typeof smokeBlocks === 'function' && smokeBlocks(b.pos.x, unitEyeY(b), b.pos.z, t.pos.x, unitChestY(t), t.pos.z);
  if (sm) p *= 0.25;
  b.mesh.muzzle.getWorldPosition(_q);
  sfxGun(b.cur, b.pos);
  worldFlash(_q); makeNoise(b);
  if (b.mesh) b.mesh.anim.recoil = 1;
  const n = w.pellets || 1;
  for (let i = 0; i < n; i++) {
    const pp = w.pellets ? D.acc * 1.6 * clamp(1.2 - dist / 14, 0.03, 1) : p;
    const head = Math.random() < D.head * (w.scope ? 1.6 : 1) * (w.pellets ? 0.5 : 1);
    _v2.set(t.pos.x, head ? unitHeadY(t) : unitChestY(t), t.pos.z);
    const hit = Math.random() < pp;
    if (!hit) { _v2.x += rand(-0.7, 0.7); _v2.y += rand(-0.4, 0.9); _v2.z += rand(-0.7, 0.7); }
    if (i < 2) tracer(_q, _v2);
    if (hit) hitUnit(t, b, b.cur, head ? 'head' : (Math.random() < 0.15 ? 'legs' : 'body'), dist);
  }
}

/* ---------------- броня ---------------- */
// покупка брони (и шлема): возвращает true при успехе. Цена: ARMOR_PRICE, шлем + HELMET_PRICE.
function buyArmor(u, withHelmet) {
  const needA = u.armor < 100, needH = withHelmet && !u.helmet;
  const price = (needA ? ARMOR_PRICE : 0) + (needH ? HELMET_PRICE : 0);
  if (!price || u.money < price) return false;
  if (mode.rounds && u.isPlayer && typeof canBuy === 'function' && !canBuy()) return false;
  u.money -= price; if (needA) u.armor = 100; if (needH) u.helmet = true;
  if (u.isPlayer) beep(880, 0.06, 0.08, 'triangle');
  return true;
}

/* ---------------- выпавшее оружие ---------------- */
const drops = [];
function spawnDrop(key, ammo, pos, vel) {
  if (!GUNS[key] || !isGun(WEAPONS[key])) return null;
  while (drops.length >= 14) removeDrop(drops[0]);
  const g = gunGroup(key, GUNS[key].full); g.scale.setScalar(BOT_GUN_SCALE);
  const d = { key, ammo: { mag: ammo ? ammo.mag : WEAPONS[key].mag, res: ammo ? ammo.res : WEAPONS[key].res }, g, pos: pos.clone(), vel: vel ? vel.clone() : V3(0, 0, 0), spin: rand(-6, 6), yaw: rand(0, 6.3), rest: false, t: 0 };
  d.pos.y = Math.max(d.pos.y, 0.9);
  g.position.copy(d.pos); scene.add(g); drops.push(d);
  return d;
}
function removeDrop(d) { const i = drops.indexOf(d); if (i >= 0) drops.splice(i, 1); scene.remove(d.g); }
function clearDrops() { while (drops.length) removeDrop(drops[0]); }
function updateDrops(dt) {
  for (let i = drops.length - 1; i >= 0; i--) {
    const d = drops[i]; d.t += dt;
    if (!mode.rounds && d.t > 40) { removeDrop(d); continue; }
    if (!d.rest) {
      d.vel.y -= 16 * dt; d.pos.addScaledVector(d.vel, dt); d.yaw += d.spin * dt;
      collide(d.pos, 0.2);
      const gnd = groundAt(d.pos, 0.2);
      if (d.pos.y <= gnd + 0.03) { d.pos.y = gnd + 0.03; if (Math.abs(d.vel.y) > 2.5) { d.vel.y *= -0.25; d.vel.x *= 0.5; d.vel.z *= 0.5; d.spin *= 0.4; } else { d.rest = true; d.vel.set(0, 0, 0); } }
    }
    d.g.position.copy(d.pos);
    d.g.rotation.set(0, d.yaw, d.rest ? Math.PI / 2 : d.t * 7);
  }
}
const slotOf = key => PRIMARIES.includes(key) ? 'primary' : 'pistol';
// бросить текущее оружие (основное или пистолет)
function dropWeapon(u, key, toss) {
  key = key || u.cur;
  const w = WEAPONS[key]; if (!w || !isGun(w) || !u.ammo[key]) return false;
  const fx = -Math.sin(u.yaw), fz = -Math.cos(u.yaw), sp = toss ? 4 : 1;
  spawnDrop(key, u.ammo[key], V3(u.pos.x + fx * 0.4, u.pos.y + (toss ? 1.4 : 1.0), u.pos.z + fz * 0.4), V3(fx * sp + u.vx * 0.5, toss ? 2 : 0.5, fz * sp + u.vz * 0.5));
  delete u.ammo[key];
  if (slotOf(key) === 'primary') u.primary = null;
  if (u.cur === key) {
    const next = u.primary && u.ammo[u.primary] ? u.primary : u.ammo.pistol ? 'pistol' : 'knife';
    if (!u.ammo[next]) u.ammo[next] = { mag: '—', res: '—' };
    equip(u, next);
  }
  return true;
}
function pickupDrop(u, d) {
  const slot = slotOf(d.key);
  const cur = slot === 'primary' ? u.primary : (u.ammo.pistol ? 'pistol' : null);
  if (cur && cur === d.key && u.ammo[cur]) {
    // такое же оружие — только забрать патроны
    const a = u.ammo[cur]; a.res = Math.min(WEAPONS[cur].res * 2, a.res + d.ammo.mag + d.ammo.res); removeDrop(d);
    if (u.isPlayer) sfxPickup(); return true;
  }
  if (cur && u.ammo[cur]) dropWeapon(u, cur, false);
  removeDrop(d);
  u.ammo[d.key] = d.ammo;
  if (slot === 'primary') u.primary = d.key;
  equip(u, d.key);
  if (u.isPlayer) sfxPickup();
  return true;
}
const weaponValue = k => k ? (WEAPONS[k].price || 200) + (PRIMARIES.includes(k) ? 1000 : 0) : 0;
function nearestDrop(u, r, better) {
  let best = null, bd = r;
  for (const d of drops) {
    const dd = Math.hypot(d.pos.x - u.pos.x, d.pos.z - u.pos.z);
    if (dd > bd || Math.abs(d.pos.y - u.pos.y) > 1.3) continue;
    if (better && !(slotOf(d.key) === 'primary' && weaponValue(d.key) > weaponValue(u.primary))) continue;
    bd = dd; best = d;
  }
  return best;
}
// боты подбирают оружие лучше своего: сворачивают к нему, если оно рядом и врагов не видно
function botPickups(dt) {
  if (!drops.length) return;
  for (const b of bots) {
    if (!b.alive || b.planting || b.defusing) continue;
    b._pickT = (b._pickT || 0) - dt; if (b._pickT > 0) continue; b._pickT = 0.4;
    const near = nearestDrop(b, 1.4, true);
    if (near) { pickupDrop(b, near); continue; }
    if (b.targetVisible || b.lastSeenT > 0 || b.hasCharge) continue;
    const far = nearestDrop(b, 9, true);
    if (far && los(b.pos.x, b.pos.y + 1, b.pos.z, far.pos.x, far.pos.y + 0.2, far.pos.z)) {
      const p = findPath(Math.floor(b.pos.x / CELL), Math.floor(b.pos.z / CELL), Math.floor(far.pos.x / CELL), Math.floor(far.pos.z / CELL));
      if (p) { b.path = p; b.pathI = 0; b.goalT = 6; b._pickT = 2; }
    }
  }
}
// кнопка «Подобрать»: делим input.useAvailable с режимом «Подрыв» — занимаем, только если кнопка свободна или наша
let useMine = false, usePrev = false, keyUse = false;
function updatePlayerPickup() {
  const p = player;
  if (useMine && input.useLabel && !input.useLabel.startsWith('Подобрать')) useMine = false;
  const near = p.alive && state !== 'roundEnd' ? nearestDrop(p, 1.7, false) : null;
  if (near && (!input.useAvailable || useMine)) { input.useAvailable = true; input.useLabel = 'Подобрать ' + WEAPONS[near.key].name; useMine = true; }
  else if (!near && useMine) { input.useAvailable = false; input.useLabel = ''; useMine = false; }
  const down = !!(input.use || keyUse), press = down && !usePrev; usePrev = down;
  if (near && press && (useMine || keyUse)) pickupDrop(p, near);
  else if (near && !p.primary && slotOf(near.key) === 'primary' && Math.hypot(near.pos.x - p.pos.x, near.pos.z - p.pos.z) < 0.9) pickupDrop(p, near);
}
// смерть: основное оружие падает на землю
bus.on('kill', victim => {
  const key = victim.primary || victim._lastPrimary;
  if (key && victim.ammo[key] && isGun(WEAPONS[key])) {
    spawnDrop(key, victim.ammo[key], V3(victim.pos.x, victim.pos.y + 1.1, victim.pos.z), V3(rand(-1, 1), 1.2, rand(-1, 1)));
  }
  victim._lastPrimary = null; victim.helmet = false; victim.flashT = 0;
  for (const g of GRENADES) delete victim.ammo[g];
});
