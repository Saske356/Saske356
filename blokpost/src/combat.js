'use strict';
/* ---------------- стрельба ---------------- */
const ray = new THREE.Raycaster(); ray.far = 200;
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3(), _q = new THREE.Vector3(), _r = new THREE.Vector3(), _u = new THREE.Vector3();
function startReload(u) {
  const w = weaponOf(u), a = u.ammo[u.cur];
  if (u.reloading > 0 || a.mag >= w.mag || a.res <= 0) return;
  u.reloading = w.reload; u.scoped = false; u.sprayN = 0;
  if (u.isPlayer) sfxReload();
}
function finishReload(u) {
  const w = weaponOf(u), a = u.ammo[u.cur], take = Math.min(w.mag - a.mag, a.res);
  a.mag += take; a.res -= take;
}
function currentSpread(u) {
  const w = weaponOf(u); let s = w.spread;
  if (w.scope) s = u.scoped ? w.scopedSpread : w.spread; else if (u.scoped) s *= w.pellets ? 0.8 : 0.6;
  s += w.moveSpread * clamp(Math.hypot(u.vx, u.vz) / 5, 0, 1);
  if (!u.onGround) s += 0.08;
  s += w.spray * Math.min(u.sprayN, 12);
  return s;
}
function playerShoot() {
  const u = player, w = weaponOf(u), a = u.ammo[u.cur];
  if (u.reloading > 0 || gt < u.nextShot) return false;
  if (a.mag <= 0) { sfxClick(); startReload(u); u.nextShot = gt + 0.25; return false; }
  a.mag--; u.nextShot = gt + w.rate; u.protT = 0;
  const spread = currentSpread(u);
  u.sprayN++; u.punch = Math.min(0.14, u.punch + w.kick); u.punchY += (Math.random() - 0.5) * w.kick * 0.7 * Math.min(1, u.sprayN / 4);
  camera.updateMatrixWorld();
  camera.getWorldDirection(_v3);
  _r.set(1, 0, 0).applyQuaternion(camera.quaternion); _u.set(0, 1, 0).applyQuaternion(camera.quaternion);
  const targets = levelMeshes.slice();
  for (const b of bots) if (b.alive) targets.push(...b.mesh.hit);
  _q.copy(camera.position).addScaledVector(_v3, 0.6).addScaledVector(_r, 0.16).addScaledVector(_u, -0.14);
  const n = w.pellets || 1;
  for (let i = 0; i < n; i++) {
    const rr = spread * Math.sqrt(Math.random()), th = Math.random() * Math.PI * 2;
    _v.copy(_v3).addScaledVector(_r, Math.cos(th) * rr).addScaledVector(_u, Math.sin(th) * rr).normalize();
    ray.set(camera.position, _v);
    const hit = ray.intersectObjects(targets, false)[0];
    const end = hit ? hit.point : _v2.copy(camera.position).addScaledVector(_v, 120);
    if (n > 1 ? i < 3 : (Math.random() < 0.5 || w.scope)) tracer(_q, end);
    if (hit) {
      const tu = hit.object.userData.unit;
      if (tu) { if (tu.team !== u.team) { applyDamage(tu, u, u.cur, hit.object.userData.part, hit.distance); burst(hit.point, 0x8a1f16, 5); } }
      else { decal(hit); if (i < 3) burst(hit.point, 0xffd27a, 3); }
    }
  }
  const vm = VM[u.cur]; vm.flash.visible = true; vm.flashT = 0.045; vm.flash.material.rotation = Math.random() * 6;
  vmState.kick = Math.min(1, vmState.kick + (w.scope || w.pellets ? 1 : 0.55));
  if (w.pellets) vmState.pump = 1;
  sfxShot(w.snd, 1, 0);
  makeNoise(u);
  if (a.mag === 0) setTimeout(() => { if (player.alive && player.ammo[player.cur] === a) startReload(player); }, 260);
  return true;
}
function makeNoise(src) {
  for (const b of bots) {
    if (!b.alive || b.team === src.team || b.targetVisible) continue;
    if (b.pos.distanceTo(src.pos) < (src.cur === 'smg' ? 14 : 34)) { b.alertT = 2.5; b.lastSeen.copy(src.pos); b.lastSeenT = 4; b.path = null; }
  }
}
function botShoot(b, t) {
  const w = weaponOf(b), a = b.ammo[b.cur];
  if (b.reloading > 0 || gt < b.nextShot) return;
  if (a.mag <= 0) { startReload(b); return; }
  a.mag--; b.burst++; b.protT = 0;
  let delay = w.rate * rand(1, 1.35);
  if (w.auto && b.burst >= (3 + (Math.random() * 4 | 0))) { b.burst = 0; delay += rand(0.25, 0.55); }
  if (!w.auto) delay = w.rate * rand(1.1, 1.6);
  b.nextShot = gt + delay;
  const D = DIFF[settings.diff];
  const dist = Math.hypot(t.pos.x - b.pos.x, t.pos.z - b.pos.z);
  let p = D.acc * (w.botAcc || 1) * clamp(1.18 - dist / (w.scope ? 140 : 55), 0.12, 1);
  if (Math.hypot(t.vx, t.vz) > 2.5) p *= 0.75;
  if (Math.hypot(b.vx, b.vz) > 1) p *= 0.8;
  if (!t.onGround) p *= 0.7;
  if (w.scope && Math.hypot(b.vx, b.vz) > 0.5) p *= 0.3;
  b.mesh.muzzle.getWorldPosition(_q);
  const L = listener(); const d = Math.hypot(b.pos.x - L.x, b.pos.z - L.z);
  const rel = angDiff(yawTo(L.x, L.z, b.pos.x, b.pos.z), L.yaw);
  sfxShot(w.snd, 0.9 / (1 + d / 10), -Math.sin(rel) * 0.8);
  worldFlash(_q); makeNoise(b);
  const n = w.pellets || 1;
  for (let i = 0; i < n; i++) {
    const pp = w.pellets ? D.acc * 1.6 * clamp(1.2 - dist / 14, 0.03, 1) : p;
    const head = Math.random() < D.head * (w.scope ? 1.6 : 1) * (w.pellets ? 0.5 : 1);
    _v2.set(t.pos.x, t.pos.y + (head ? 1.72 : 1.25), t.pos.z);
    const hit = Math.random() < pp;
    if (!hit) { _v2.x += rand(-0.7, 0.7); _v2.y += rand(-0.4, 0.9); _v2.z += rand(-0.7, 0.7); }
    if (i < 2) tracer(_q, _v2);
    if (hit) applyDamage(t, b, b.cur, head ? 'head' : 'body', dist);
  }
}
