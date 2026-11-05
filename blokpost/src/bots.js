'use strict';
/* ---------------- боты ---------------- */
function pickGoal(b) {
  const enemyTeam = b.team === 'A' ? 'B' : 'A';
  if (!mode.rounds || roundT < 45) {
    const foes = units.filter(e => e.alive && e.team !== b.team);
    if (foes.length && Math.random() < 0.6) { const f = pick(foes); return [Math.floor(f.pos.x / CELL), Math.floor(f.pos.z / CELL)]; }
  }
  if (Math.random() < 0.45) { const s = pick(spawns[enemyTeam]); return [Math.floor(s.x / CELL), Math.floor(s.z / CELL)]; }
  return pick(openCells);
}
function routeTo(b, tx, tz) {
  b.path = findPath(Math.floor(b.pos.x / CELL), Math.floor(b.pos.z / CELL), tx, tz); b.pathI = 0; b.goalT = 12;
}
function perceive(b) {
  const D = DIFF[settings.diff];
  let best = null, bd = 1e9;
  for (const e of units) {
    if (!e.alive || e.team === b.team) continue;
    const d = Math.hypot(e.pos.x - b.pos.x, e.pos.z - b.pos.z);
    if (d > 75) continue;
    const ang = Math.abs(angDiff(yawTo(b.pos.x, b.pos.z, e.pos.x, e.pos.z), b.yaw));
    if (ang > D.fov && b.alertT <= 0 && d > 5) continue;
    if (!los(b.pos.x, b.pos.y + 1.7, b.pos.z, e.pos.x, e.pos.y + 1.4, e.pos.z)) continue;
    const score = d * (e === b.target ? 0.7 : 1);
    if (score < bd) { bd = score; best = e; }
  }
  if (best) {
    if (best !== b.target || !b.targetVisible) { b.reactT = rand(D.react[0], D.react[1]) * (b.alertT > 0 ? 0.7 : 1); b.burst = 0; }
    b.target = best; b.targetVisible = true; b.lastSeen.copy(best.pos); b.lastSeenT = 5; best.spottedT = 1.2;
  } else b.targetVisible = false;
}
function updateBot(b, dt) {
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
  const D = DIFF[settings.diff], w = weaponOf(b);
  b.alertT -= dt; b.lastSeenT -= dt; b.goalT -= dt; b.protT = Math.max(0, b.protT - dt);
  if (b.reloading > 0) { b.reloading -= dt; if (b.reloading <= 0) { b.reloading = 0; finishReload(b); } }
  let desiredYaw = b.yaw, mvx = 0, mvz = 0, speed = 4.1 * w.speed;
  if (state === 'freeze' && mode.rounds) { syncBotMesh(b, dt, 0); return; }
  b.thinkT -= dt;
  if (b.thinkT <= 0) { b.thinkT = rand(0.12, 0.22); perceive(b); }
  const t = b.target;
  let aimPitch = 0;
  if (t && t.alive && b.targetVisible) {
    const dist = Math.hypot(t.pos.x - b.pos.x, t.pos.z - b.pos.z);
    desiredYaw = yawTo(b.pos.x, b.pos.z, t.pos.x, t.pos.z);
    aimPitch = Math.atan2((t.pos.y + 1.3) - (b.pos.y + 1.4), dist);
    b.reactT -= dt;
    b.strafeT -= dt;
    if (b.strafeT <= 0) { b.strafeT = rand(0.35, 1.1); b.strafeDir = Math.random() < (w.scope ? 0.75 : 0.3) ? 0 : (Math.random() < 0.5 ? -1 : 1); }
    if (b.strafeDir) { mvx = Math.cos(desiredYaw) * b.strafeDir; mvz = -Math.sin(desiredYaw) * b.strafeDir; speed *= 0.6; }
    if (w.pellets && dist > 9) { mvx += -Math.sin(desiredYaw) * 0.8; mvz += -Math.cos(desiredYaw) * 0.8; }
    if (b.ammo[b.cur].mag === 0 && b.reloading === 0) startReload(b);
    if (Math.abs(angDiff(desiredYaw, b.yaw)) < 0.18 && b.reactT <= 0) botShoot(b, t);
    b.path = null;
  } else {
    if (b.target && !b.target.alive) b.target = null;
    if (b.ammo[b.cur].mag < w.mag * 0.4 && b.reloading === 0) startReload(b);
    if (b.lastSeenT > 0 && !b.path) {
      routeTo(b, Math.floor(b.lastSeen.x / CELL), Math.floor(b.lastSeen.z / CELL));
      if (!b.path) b.lastSeenT = 0;
    }
    if (!b.path || b.pathI >= b.path.length || b.goalT <= 0) {
      if (b.lastSeenT > 0 && b.path && b.pathI >= b.path.length) b.lastSeenT = 0;
      const [tx, tz] = pickGoal(b); routeTo(b, tx, tz);
    }
    if (b.path && b.pathI < b.path.length) {
      const [cx, cz] = b.path[b.pathI];
      const wx = (cx + 0.5) * CELL, wz = (cz + 0.5) * CELL, dx = wx - b.pos.x, dz = wz - b.pos.z, d = Math.hypot(dx, dz);
      if (d < 0.7) b.pathI++;
      else { mvx = dx / d; mvz = dz / d; desiredYaw = yawTo(b.pos.x, b.pos.z, wx, wz); }
    }
    if (b.lastSeenT > 0 && b.alertT > 0) desiredYaw = yawTo(b.pos.x, b.pos.z, b.lastSeen.x, b.lastSeen.z);
  }
  b.aimPitch += (clamp(aimPitch, -0.6, 0.6) - b.aimPitch) * Math.min(1, dt * 8);
  const da = angDiff(desiredYaw, b.yaw), turn = D.turn * dt;
  b.yaw += clamp(da, -turn, turn);
  const ml = Math.hypot(mvx, mvz); if (ml > 1) { mvx /= ml; mvz /= ml; }
  b.vx += (mvx * speed - b.vx) * Math.min(1, dt * 10); b.vz += (mvz * speed - b.vz) * Math.min(1, dt * 10);
  b.pos.x += b.vx * dt; b.pos.z += b.vz * dt;
  collide(b.pos, RAD); collide(b.pos, RAD);
  b.stuckT += dt;
  if (b.stuckT > 1.2) {
    if (b.path && b.lastPos.distanceTo(b.pos) < 0.3) { b.path = null; b.lastSeenT = 0; }
    b.lastPos.copy(b.pos); b.stuckT = 0;
  }
  syncBotMesh(b, dt, Math.hypot(b.vx, b.vz));
}
