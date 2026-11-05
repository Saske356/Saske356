'use strict';
/* ---------------- игрок ---------------- */
const vmState = { kick: 0, swap: 0, bob: 0, land: 0, ads: 0, pump: 0, sway: 0, swayY: 0, lastYaw: 0, lastPitch: 0 };
function updatePlayer(dt) {
  const p = player, w = weaponOf(p);
  if (!p.alive) { spectate(dt); return; }
  let mx = joy.x, my = joy.y;
  if (input.keys.KeyW || input.keys.ArrowUp) my += 1;
  if (input.keys.KeyS || input.keys.ArrowDown) my -= 1;
  if (input.keys.KeyD || input.keys.ArrowRight) mx += 1;
  if (input.keys.KeyA || input.keys.ArrowLeft) mx -= 1;
  const ml = Math.hypot(mx, my); if (ml > 1) { mx /= ml; my /= ml; }
  if (state === 'freeze' && mode.rounds) mx = my = 0;
  const spd = 5.6 * w.speed * (p.scoped ? 0.6 : 1);
  const fx = -Math.sin(p.yaw), fz = -Math.cos(p.yaw), rx = Math.cos(p.yaw), rz = -Math.sin(p.yaw);
  const tvx = (fx * my + rx * mx) * spd, tvz = (fz * my + rz * mx) * spd;
  const acc = p.onGround ? 12 : 2.5;
  p.vx += (tvx - p.vx) * Math.min(1, acc * dt); p.vz += (tvz - p.vz) * Math.min(1, acc * dt);
  p.pos.x += p.vx * dt; p.pos.z += p.vz * dt;
  collide(p.pos, RAD); collide(p.pos, RAD);
  if (input.jump && p.onGround && !(state === 'freeze' && mode.rounds)) { p.vy = 6.1; p.onGround = false; }
  input.jump = false;
  p.vy -= 18 * dt; p.pos.y += p.vy * dt;
  const g = groundAt(p.pos, RAD);
  if (p.pos.y <= g) { if (p.vy < -4) vmState.land = 1; p.pos.y = g; p.vy = 0; p.onGround = true; }
  else if (p.pos.y > g + 0.03) p.onGround = false;

  if (p.reloading > 0) { p.reloading -= dt; if (p.reloading <= 0) { p.reloading = 0; finishReload(p); } }
  if (!input.fire || gt > p.nextShot + 0.12) p.sprayN = Math.max(0, p.sprayN - dt * 14);
  if (input.fire && state !== 'freeze') {
    if (w.auto || !p.fireLatch) { if (playerShoot()) p.fireLatch = true; }
  } else p.fireLatch = false;
  p.punch *= Math.exp(-dt * (input.fire ? 3.5 : 9)); p.punchY *= Math.exp(-dt * 6);

  const targetFov = p.scoped ? BASE_FOV / w.zoom : BASE_FOV;
  camera.fov += (targetFov - camera.fov) * Math.min(1, dt * 18);
  camera.updateProjectionMatrix();
  camera.position.set(p.pos.x, p.pos.y + 1.62 - vmState.land * 0.08, p.pos.z);
  camera.rotation.set(p.pitch + p.punch, p.yaw + p.punchY, 0);

  // вьюмодель: покачивание, инерция, отдача, прицеливание, перезарядка с отстёгиванием магазина
  const vm = VM[p.cur], S = vmState;
  const hs = Math.hypot(p.vx, p.vz);
  if (p.onGround && hs > 0.5) S.bob += dt * hs * 1.9;
  S.kick *= Math.exp(-dt * 14); S.swap = Math.max(0, S.swap - dt * 2.6); S.land = Math.max(0, S.land - dt * 5);
  S.ads += ((p.scoped && !w.scope ? 1 : 0) - S.ads) * Math.min(1, dt * 14);
  S.pump = Math.max(0, S.pump - dt * 2.2);
  const dyaw = angDiff(p.yaw, S.lastYaw), dpit = p.pitch - S.lastPitch; S.lastYaw = p.yaw; S.lastPitch = p.pitch;
  S.sway += (clamp(dyaw * 2, -0.06, 0.06) - S.sway) * Math.min(1, dt * 10);
  S.swayY += (clamp(dpit * 2, -0.06, 0.06) - S.swayY) * Math.min(1, dt * 10);
  const amp = Math.min(1, hs / 5) * (1 - S.ads * 0.85);
  const rt = p.reloading > 0 ? 1 - p.reloading / w.reload : 0;
  const tilt = p.reloading > 0 ? Math.sin(Math.PI * rt) : 0;
  const pos = _v.copy(vm.hip).lerp(vm.ads, S.ads);
  vm.g.position.set(
    pos.x + Math.sin(S.bob) * 0.01 * amp + S.sway * 0.4,
    pos.y + Math.abs(Math.cos(S.bob)) * 0.01 * amp - S.swap * 0.3 - tilt * 0.06 - S.land * 0.03 - S.swayY * 0.3,
    pos.z + S.kick * (S.ads > 0.5 ? 0.04 : 0.065));
  vm.g.rotation.set(S.kick * 0.1 + tilt * 0.35 + S.swayY * 0.6, S.sway * 0.8 + (1 - S.ads) * 0.06, tilt * 0.5);
  if (vm.mag) {
    let my2 = 0;
    if (p.reloading > 0) { if (rt < 0.3) my2 = -rt / 0.3 * 0.3; else if (rt < 0.55) my2 = -0.3; else if (rt < 0.8) my2 = -0.3 * (1 - (rt - 0.55) / 0.25); }
    vm.mag.position.y = my2; vm.mag.visible = !(rt > 0.3 && rt < 0.55);
  }
  if (vm.pump) { const k = S.pump > 0.5 ? (1 - S.pump) * 2 : S.pump * 2; vm.pump.position.z = S.pump > 0 ? k * 0.09 : 0; }
  vm.g.visible = !(p.scoped && w.scope);
  if (vm.flashT > 0) { vm.flashT -= dt; if (vm.flashT <= 0) vm.flash.visible = false; }
}
function spectate(dt) {
  for (const g in VM) VM[g].g.visible = false;
  const mates = units.filter(u => u.alive && u.team === player.team && !u.isPlayer);
  const m = mates.length ? mates[specIndex % mates.length] : null;
  camera.fov += (BASE_FOV - camera.fov) * Math.min(1, dt * 10); camera.updateProjectionMatrix();
  if (!m) return;
  _v.set(m.pos.x + Math.sin(m.yaw) * 2.4 + Math.cos(m.yaw) * 0.5, m.pos.y + 2.2, m.pos.z + Math.cos(m.yaw) * 2.4 - Math.sin(m.yaw) * 0.5);
  camera.position.lerp(_v, Math.min(1, dt * 6));
  camera.lookAt(m.pos.x - Math.sin(m.yaw) * 4, m.pos.y + 1.4, m.pos.z - Math.cos(m.yaw) * 4);
}
function listener() {
  if (player.alive) return { x: player.pos.x, z: player.pos.z, yaw: player.yaw };
  _v.set(0, 0, -1).applyQuaternion(camera.quaternion);
  return { x: camera.position.x, z: camera.position.z, yaw: Math.atan2(-_v.x, -_v.z) };
}
