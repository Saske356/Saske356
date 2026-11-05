'use strict';
/* ---------------- игрок ---------------- */
const vmState = { kick: 0, swap: 0, bob: 0, land: 0, ads: 0, pump: 0, sway: 0, swayY: 0, lastYaw: 0, lastPitch: 0, shotT: 0, bolt: 0, melee: 0, meleeT: 0, slashSide: 1,
  inspect: 0, shake: 0, crouch: 0, stepPh: 0, lastCur: null, strafe: 0, nade: { st: 'idle', t: 0, lob: false, done: false } };

/* ---------------- клавиши ПК (сенсорные кнопки шлют то же через шину) ---------------- */
function toggleKnife() {
  const p = player; if (!p || !p.alive) return;
  if (!p.ammo.knife) p.ammo.knife = { mag: '—', res: '—' };
  if (p.cur === 'knife') { const back = p._prevCur && p.ammo[p._prevCur] && p._prevCur !== 'knife' ? p._prevCur : p.primary && p.ammo[p.primary] ? p.primary : 'pistol'; equip(p, back); }
  else { p._prevCur = p.cur; equip(p, 'knife'); }
}
bus.on('action:knife', toggleKnife);
bus.on('action:grenade', () => { if (player) cycleGrenade(player); });
bus.on('action:drop', () => { if (player && player.alive && state !== 'menu') dropWeapon(player, null, true); });
bus.on('action:inspect', () => { if (player && player.alive && player.reloading <= 0) vmState.inspect = 2.4; });
addEventListener('keydown', e => {
  if (state === 'menu' || state === 'over' || !player) return;
  const k = e.code;
  if (k === 'KeyC' || k === 'ControlLeft' || k === 'ControlRight') { input.crouch = true; if (k !== 'KeyC') e.preventDefault(); }
  if (k === 'ShiftLeft' || k === 'ShiftRight') input.walk = true;
  if (k === 'KeyE') keyUse = true;
  if (e.repeat) return;
  if (k === 'Digit3') bus.emit('action:knife');
  if (k === 'Digit4') bus.emit('action:grenade');
  if (k === 'KeyG') bus.emit('action:drop');
  if (k === 'KeyF') bus.emit('action:inspect');
});
addEventListener('keyup', e => {
  const k = e.code;
  if (k === 'KeyC' || k === 'ControlLeft' || k === 'ControlRight') input.crouch = false;
  if (k === 'ShiftLeft' || k === 'ShiftRight') input.walk = false;
  if (k === 'KeyE') keyUse = false;
});
addEventListener('blur', () => { keyUse = false; });

/* ---------------- перезарядка по шагам: звук и анимация ---------------- */
function reloadSteps(p, w, rt) {
  const steps = w.pellets ? [[0.15, 'shell'], [0.35, 'shell'], [0.55, 'shell'], [0.75, 'shell'], [0.9, 'pump']]
    : [[0.16, 'out'], [0.6, 'in'], [w.bolt ? 0.8 : 0.84, w.bolt ? 'sbolt' : 'bolt']];
  while ((p.reloadStep || 0) < steps.length && rt >= steps[p.reloadStep || 0][0]) {
    const s = steps[p.reloadStep || 0][1]; p.reloadStep = (p.reloadStep || 0) + 1;
    if (s === 'out') sfxMagOut(null); else if (s === 'in') sfxMagIn(null); else if (s === 'bolt') sfxBoltRack(null);
    else if (s === 'sbolt') sfxSniperBolt(null); else if (s === 'shell') sfxShellIn(null); else if (s === 'pump') sfxPump(null);
  }
}

function updatePlayer(dt) {
  combatTick(dt);
  const p = player, w = weaponOf(p), S = vmState;
  if (!p.alive) { spectate(dt); return; }
  if (S.lastCur !== p.cur) {
    if (S.lastCur) sfxDraw();
    S.lastCur = p.cur; S.nade.st = 'idle'; S.melee = 0; S.meleeT = 0; S.inspect = 0; S.bolt = 0; p.boltT = 0; p.reloadStep = 0;
  }
  const frozen = state === 'freeze' && mode.rounds;
  let mx = joy.x, my = joy.y;
  if (input.keys.KeyW || input.keys.ArrowUp) my += 1;
  if (input.keys.KeyS || input.keys.ArrowDown) my -= 1;
  if (input.keys.KeyD || input.keys.ArrowRight) mx += 1;
  if (input.keys.KeyA || input.keys.ArrowLeft) mx -= 1;
  const ml = Math.hypot(mx, my); if (ml > 1) { mx /= ml; my /= ml; }
  if (frozen) mx = my = 0;
  p.crouch = !!input.crouch; p.walk = !!input.walk && !p.crouch;
  const spd = 5.6 * w.speed * (p.scoped ? 0.6 : 1) * (p.crouch ? 0.42 : p.walk ? 0.52 : 1);
  const fx = -Math.sin(p.yaw), fz = -Math.cos(p.yaw), rx = Math.cos(p.yaw), rz = -Math.sin(p.yaw);
  const tvx = (fx * my + rx * mx) * spd, tvz = (fz * my + rz * mx) * spd;
  // инерция: разгон мягче торможения, контр-стрейф гасит скорость быстро
  let acc = 2.2;
  if (p.onGround) acc = (tvx * p.vx + tvz * p.vz < 0 || Math.hypot(tvx, tvz) < Math.hypot(p.vx, p.vz)) ? 15 : 8.5;
  p.vx += (tvx - p.vx) * Math.min(1, acc * dt); p.vz += (tvz - p.vz) * Math.min(1, acc * dt);
  p.pos.x += p.vx * dt; p.pos.z += p.vz * dt;
  collide(p.pos, RAD); collide(p.pos, RAD);
  if (input.jump && p.onGround && !frozen) { p.vy = 6.1; p.onGround = false; }
  input.jump = false;
  p.vy -= 18 * dt; p.pos.y += p.vy * dt;
  const g = groundAt(p.pos, RAD);
  if (p.pos.y <= g) {
    if (p.vy < -4) { S.land = clamp(-p.vy / 9, 0.4, 1); sfxLand(null); if (!p.walk && !p.crouch) hearNoise(p, 10); }
    p.pos.y = g; p.vy = 0; p.onGround = true;
  } else if (p.pos.y > g + 0.03) p.onGround = false;
  const hs = Math.hypot(p.vx, p.vz);
  // шаги: бег слышен врагам, тихий шаг и присед — нет
  if (p.onGround && hs > 0.5) {
    S.bob += dt * hs * 1.9;
    const ph = Math.floor(S.bob / Math.PI);
    if (ph !== S.stepPh) { S.stepPh = ph; if (hs > 2.9 && !p.walk && !p.crouch) { sfxStep(null, 0.3); hearNoise(p, 11); } }
  }

  // оружие: перезарядка, затвор, прицел, отдача
  if (p.reloading > 0) { p.reloading -= dt; reloadSteps(p, w, 1 - p.reloading / w.reload); if (p.reloading <= 0) { p.reloading = 0; finishReload(p); } }
  if (p.boltT > 0) { p.boltT -= dt; if (p.boltT <= 0) { p.boltT = 0; if (p.rescope && w.scope && p.reloading <= 0) p.scoped = true; p.rescope = false; } }
  if (!isGun(w)) { if (w.melee && p.scoped) { p.scoped = false; if (state !== 'freeze') meleeAttack(p, true); } }
  p.scopeT = p.scoped ? (p.scopeT || 0) + dt : 0;
  if (!input.fire || gt > p.nextShot + 0.05) p.sprayN = Math.max(0, (p.sprayN || 0) - dt * (w.recover || 10));
  if (w.grenade) updatePlayerGrenade(dt);
  else if (input.fire && state !== 'freeze') {
    if (w.melee) meleeAttack(p, false);
    else if (w.auto || !p.fireLatch) { if (playerShoot()) p.fireLatch = true; }
  } else p.fireLatch = false;
  const rc = isGun(w) ? recoilAt(w, p.sprayN) : [0, 0];
  const kr = Math.min(1, dt * 24);
  p.punch += (rc[1] - p.punch) * kr; p.punchY += (-rc[0] - p.punchY) * kr;

  const targetFov = p.scoped && isGun(w) ? BASE_FOV / w.zoom : BASE_FOV;
  camera.fov += (targetFov - camera.fov) * Math.min(1, dt * 18);
  camera.updateProjectionMatrix();
  S.crouch += ((p.crouch ? 1 : 0) - S.crouch) * Math.min(1, dt * 12);
  S.shake = Math.max(0, S.shake - dt * 1.6);
  const shk = S.shake * S.shake * 0.03;
  S.strafe += ((p.vx * rx + p.vz * rz) / 5.6 - S.strafe) * Math.min(1, dt * 6);
  camera.position.set(p.pos.x, p.pos.y + 1.62 - S.crouch * 0.46 - S.land * 0.09, p.pos.z);
  camera.rotation.set(p.pitch + p.punch + rand(-shk, shk), p.yaw + p.punchY + rand(-shk, shk), -S.strafe * 0.012 * (1 - S.ads));
  animateViewmodel(p, w, dt, hs);
}

/* ---------------- анимация вьюмодели ---------------- */
const _vp = new THREE.Vector3(), _ml = new THREE.Vector3();
function animateViewmodel(p, w, dt, hs) {
  const vm = VM[p.cur], S = vmState; if (!vm) return;
  S.kick *= Math.exp(-dt * 14); S.swap = Math.max(0, S.swap - dt * 2.6); S.land = Math.max(0, S.land - dt * 4);
  S.shotT = Math.max(0, S.shotT - dt * 16);
  S.ads += ((p.scoped && isGun(w) && !w.scope ? 1 : 0) - S.ads) * Math.min(1, dt * 14);
  S.pump = Math.max(0, S.pump - dt * 2.2);
  S.inspect = Math.max(0, S.inspect - dt); if (p.reloading > 0 || input.fire) S.inspect = 0;
  const dyaw = angDiff(p.yaw, S.lastYaw), dpit = p.pitch - S.lastPitch; S.lastYaw = p.yaw; S.lastPitch = p.pitch;
  S.sway += (clamp(dyaw * 2, -0.06, 0.06) - S.sway) * Math.min(1, dt * 10);
  S.swayY += (clamp(dpit * 2, -0.06, 0.06) - S.swayY) * Math.min(1, dt * 10);
  const amp = Math.min(1, hs / 5) * (1 - S.ads * 0.85) * (p.onGround ? 1 : 0.3);
  const rt = p.reloading > 0 ? 1 - p.reloading / w.reload : 0;
  const tilt = p.reloading > 0 ? Math.sin(Math.PI * clamp(rt * 1.15, 0, 1)) : 0;
  const breathe = Math.sin(gt * 1.6) * 0.002;
  const pos = _vp.copy(vm.hip).lerp(vm.ads, S.ads);
  const ins = S.inspect > 0 ? Math.sin(Math.PI * clamp(1 - S.inspect / 2.4, 0, 1)) : 0;
  let gx = pos.x + Math.sin(S.bob) * 0.011 * amp + S.sway * 0.4 + S.strafe * 0.01 - ins * 0.05,
    gy = pos.y + Math.abs(Math.cos(S.bob)) * 0.011 * amp - S.swap * 0.32 - tilt * 0.05 - S.land * 0.035 - S.swayY * 0.3 + breathe - S.crouch * 0.008,
    gz = pos.z + S.kick * (S.ads > 0.5 ? 0.04 : 0.065) + ins * 0.03;
  let rx = S.kick * 0.1 + tilt * 0.3 + S.swayY * 0.6 - S.swap * 0.7 + ins * 0.15,
    ry = S.sway * 0.8 + (1 - S.ads) * 0.06 + ins * 0.9, rz = tilt * 0.55 + S.strafe * 0.04 + ins * 0.45;
  vm.gun.position.set(0, 0, 0); vm.gun.rotation.set(0, 0, 0);
  if (vm.type === 'knife') {
    rx += 0.3; ry += 0.3; rz += -0.2;
    if (S.meleeT > 0) {
      S.meleeT = Math.max(0, S.meleeT - dt);
      if (S.melee > 0) { // быстрый удар: взмах наискось, поочерёдно с разных сторон
        const t = 1 - S.meleeT / 0.42, e = t < 0.55 ? Math.sin(t / 0.55 * Math.PI / 2) : 1 - (t - 0.55) / 0.45, sd = S.slashSide;
        vm.gun.rotation.set(-0.3 * e, (sd > 0 ? 1 : -0.6) * (0.9 - e * 2.0), sd * 0.6 * e);
        vm.gun.position.set(-0.16 * e * sd, 0.05 * e, -0.1 * e);
      } else { // сильный: замах и укол вперёд
        const t = 1 - S.meleeT / 0.7, back = t < 0.3 ? t / 0.3 : t < 0.42 ? 1 - (t - 0.3) / 0.12 : 0, stab = t < 0.3 ? 0 : t < 0.45 ? (t - 0.3) / 0.15 : Math.max(0, 1 - (t - 0.45) / 0.4);
        vm.gun.rotation.set(-0.7 * back - 0.3 * stab, -0.6 * stab, 0.5 * back);
        vm.gun.position.set(-0.08 * stab, 0.06 * back, 0.1 * back - 0.22 * stab);
      }
    }
    if (ins > 0) { vm.gun.rotation.z += ins * 2.2; vm.gun.rotation.y -= ins * 0.6; }
  } else if (vm.type === 'nade') {
    const N = S.nade, L = vm.left;
    L.position.set(0, 0, 0); vm.g.visible = true; vm.body.visible = true;
    if (N.st === 'pin') { const t = clamp(N.t / 0.38, 0, 1); L.position.set(0.06 * Math.sin(t * Math.PI), 0.07 * Math.sin(t * Math.PI) + (t > 0.6 ? (t - 0.6) * 0.15 : 0), -0.02); rx -= 0.2 * t; }
    else if (N.st === 'ready') { gy += 0.05; gz += 0.09; rx -= 0.5; L.position.set(-0.05, -0.1, 0.06); }
    else if (N.st === 'throw') {
      const t = clamp(N.t / 0.3, 0, 1);
      gy += 0.05 + Math.sin(t * Math.PI) * 0.12 - t * 0.35; gz += 0.09 - t * 0.35; rx -= 0.5 - t * 1.6;
      vm.body.visible = !N.done; L.position.set(-0.05, -0.1 - t * 0.2, 0.06);
    }
  } else {
    // пистолет: затвор отходит при выстреле; снайперка: цикл затвора; ПП/автоматы: рукоять затвора в конце перезарядки
    if (vm.bolt) {
      vm.bolt.position.copy(GUNS[p.cur].pivot); vm.bolt.rotation.set(0, 0, 0);
      if (w.hold === 'pistol') vm.bolt.position.z += Math.max(S.shotT, a0(p) ? 0.9 : 0) * 0.028;
      else if (w.bolt) {
        const bt = p.boltT > 0 ? 1 - p.boltT / (w.rate * 0.95) : (p.reloading > 0 && rt > 0.78 ? (rt - 0.78) / 0.2 * 0.8 + 0.2 : 0);
        if (bt > 0.2) {
          const up = bt < 0.32 ? (bt - 0.2) / 0.12 : bt < 0.8 ? 1 : Math.max(0, 1 - (bt - 0.8) / 0.12);
          const back = bt < 0.32 ? 0 : bt < 0.5 ? (bt - 0.32) / 0.18 : bt < 0.68 ? 1 : Math.max(0, 1 - (bt - 0.68) / 0.12);
          vm.bolt.rotation.z = up * 1.1; vm.bolt.position.z += back * 0.075;
          rz -= up * 0.12; rx += back * 0.04;
        }
      } else if (p.reloading > 0 && rt > 0.82 && rt < 0.97) vm.bolt.position.z += Math.sin((rt - 0.82) / 0.15 * Math.PI) * 0.06;
    }
    if (vm.mag) {
      // магазин: отстегнуть → убрать → новый → вставить; левая рука сопровождает магазин
      let my2 = 0, mz = 0, vis = true, lk = 0;
      if (p.reloading > 0 && !w.pellets) {
        if (rt < 0.12) lk = rt / 0.12;
        else if (rt < 0.3) { const k = (rt - 0.12) / 0.18; my2 = -k * 0.28; mz = k * 0.04; lk = 1; }
        else if (rt < 0.46) { vis = false; lk = 1; my2 = -0.28; }
        else if (rt < 0.72) { const k = (rt - 0.46) / 0.26; my2 = -0.22 * (1 - k) - (k > 0.85 ? 0 : 0.01); mz = 0.03 * (1 - k); lk = 1; }
        else if (rt < 0.84) lk = 1 - (rt - 0.72) / 0.12;
      }
      vm.mag.position.set(0, my2, mz); vm.mag.visible = vis;
      if (vm.left && !vm.pump) {
        const G = GUNS[p.cur]; _ml.copy(G.magC).sub(V3(0, G.foreY, -G.fore)).add(V3(-0.02, -0.03, 0));
        vm.left.position.copy(_ml).multiplyScalar(lk); vm.left.position.y += my2 * (lk > 0.5 ? 1 : 0) - (rt > 0.3 && rt < 0.46 ? 0.1 : 0); vm.left.position.z += mz;
      }
    } else if (vm.left && !vm.pump) vm.left.position.set(0, 0, 0);
    if (vm.pump) {
      const k = S.pump > 0.5 ? (1 - S.pump) * 2 : S.pump * 2;
      vm.pump.position.z = S.pump > 0 ? k * 0.09 : 0;
      if (p.reloading > 0) { // дробовик: патроны по одному в окно снизу
        const cyc = (rt * 4.2) % 1, G = GUNS[p.cur];
        vm.pump.position.z = 0;
        vm.left.position.set(0.0, -0.04 - Math.sin(cyc * Math.PI) * 0.05, G.fore - 0.12 + Math.sin(cyc * Math.PI) * 0.02);
        rz += 0.25;
      } else vm.left.position.set(0, 0, 0);
    }
  }
  vm.g.position.set(gx, gy, gz);
  vm.g.rotation.set(rx, ry, rz);
  vm.g.visible = !(p.scoped && w.scope);
  if (vm.flashT > 0) { vm.flashT -= dt; if (vm.flashT <= 0) vm.flash.visible = false; }
}
const a0 = p => { const a = p.ammo[p.cur]; return a && a.mag === 0 && p.reloading <= 0; };
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
  if (player && player.alive) return { x: player.pos.x, z: player.pos.z, yaw: player.yaw };
  _v.set(0, 0, -1).applyQuaternion(camera.quaternion);
  return { x: camera.position.x, z: camera.position.z, yaw: Math.atan2(-_v.x, -_v.z) };
}
