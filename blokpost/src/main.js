'use strict';
/* ---------------- цикл ---------------- */
let last = performance.now(), menuT = 0;
function update(dt) {
  if (msgT > 0) { msgT -= dt; if (msgT <= 0) msgEl.style.opacity = 0; }
  if (state === 'menu' || state === 'over') {
    menuT += dt * 0.15; gt += dt;
    camera.fov = 45; camera.updateProjectionMatrix();
    camera.position.set(SHOW.x - 2.5 + Math.sin(menuT) * 0.8, 1.7, SHOW.z + 9);
    camera.lookAt(SHOW.x - 2.2, 1.15, SHOW.z);
    for (const b of bots) syncBotMesh(b, dt, 0);
    return;
  }
  if (paused) return;
  gt += dt;
  if (state === 'freeze') { freezeT -= dt; if (freezeT <= 0) { state = 'live'; showMsg('В бой!', ''); beep(520, 0.12, 0.08, 'triangle'); } }
  else if (state === 'live') {
    roundT -= dt; roundElapsed += dt;
    if (roundT <= 0) {
      if (!mode.rounds) { gameOver(); return; }
      const a = units.filter(u => u.team === 'A' && u.alive).length, b = units.filter(u => u.team === 'B' && u.alive).length;
      endRound(a > b ? 'A' : 'B', a > b ? 'Время вышло, у «Стали» больше бойцов' : 'Время вышло, «Ржавчина» удержала склад');
    }
  } else if (state === 'roundEnd') { endT -= dt; if (endT <= 0) { afterRoundEnd(); return; } }
  if (!mode.rounds && state === 'live') {
    for (const u of units) if (!u.alive) { u.respawnT -= dt; if (u.respawnT <= 0) respawn(u); }
  }
  player.protT = Math.max(0, player.protT - dt);
  for (const u of units) u.spottedT -= dt;
  for (const b of bots) updateBot(b, dt);
  for (const b of bots) b.mesh.root.updateMatrixWorld(true);
  updatePlayer(dt);
  updateEffects(dt);
  vigA = Math.max(0, vigA - dt * 1.2); vig.style.opacity = vigA.toFixed(3);
  for (const d of dirs) if (d.dataset.t > 0) { d.dataset.t = Math.max(0, d.dataset.t - dt * 1.2); d.style.opacity = d.dataset.t; }
  updateHUD(); drawRadar();
  if (!boardEl.hidden && Math.floor(gt * 2) !== Math.floor((gt - dt) * 2)) renderTables($('#tables'));
}
function frame(t) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  update(dt);
  renderer.clear();
  renderer.render(scene, camera);
  if (state !== 'menu' && state !== 'over' && player.alive) { renderer.clearDepth(); renderer.render(vmScene, vmCam); }
}

resize();
resetMenuScene();
setScreen('menu');
requestAnimationFrame(frame);
window.__game = { get units() { return units; }, get player() { return player; }, get state() { return state; }, input, VM, camera, settings, equip, giveAmmo };
