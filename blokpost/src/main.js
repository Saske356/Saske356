'use strict';
/* ---------------- производительность: разрешение, ограничение FPS, счётчик ---------------- */
// resize() из render.js задаёт базовый pixelRatio; здесь поверх него — динамический множитель dynScale.
const perf = { fps: 60, dynScale: 1, minScale: 0.6, frames: 0, acc: 0, lowT: 0, highT: 0, lastRender: 0 };
const basePR = () => Math.min(devicePixelRatio || 1, settings.quality);
function applyRes() {
  resize();
  if (!settings.dynRes) perf.dynScale = 1;
  const pr = Math.max(0.5, basePR() * perf.dynScale);
  if (Math.abs(renderer.getPixelRatio() - pr) > 0.001) { renderer.setPixelRatio(pr); renderer.setSize(innerWidth, innerHeight, false); }
}
addEventListener('resize', () => { applyRes(); applyLayout(); });
function perfTick(dtMs) {
  perf.frames++; perf.acc += dtMs;
  if (perf.acc < 1000) return;
  perf.fps = perf.frames * 1000 / perf.acc; perf.frames = 0; perf.acc = 0;
  if (settings.showFps) els.fps.textContent = Math.round(perf.fps) + ' FPS' + (perf.dynScale < 1 ? ' · ' + Math.round(perf.dynScale * 100) + '%' : '');
  // динамическое разрешение: держим целевую частоту, меняя плотность пикселей с запасом (гистерезис)
  if (!settings.dynRes || state === 'menu' || state === 'over' || paused) return;
  const target = settings.fpsCap || 60;
  if (perf.fps < target * 0.86) { perf.highT = 0; if (++perf.lowT >= 2 && perf.dynScale > perf.minScale) { perf.dynScale = Math.max(perf.minScale, perf.dynScale - 0.1); perf.lowT = 0; applyRes(); } }
  else if (perf.fps > target * 0.97) { perf.lowT = 0; if (++perf.highT >= 4 && perf.dynScale < 1) { perf.dynScale = Math.min(1, perf.dynScale + 0.05); perf.highT = 0; applyRes(); } }
  else { perf.lowT = 0; perf.highT = 0; }
}

/* ---------------- цикл ---------------- */
let last = performance.now(), menuT = 0;
function update(dt) {
  if (msgT > 0) { msgT -= dt; if (msgT <= 0) msgEl.style.opacity = 0; }
  if (state === 'menu' || state === 'over') {
    menuT += dt * 0.15; gt += dt;
    camera.fov = 45; camera.updateProjectionMatrix();
    camera.position.set(SHOW.camX + Math.sin(menuT) * 0.8, 1.7, SHOW.camZ);
    camera.lookAt(SHOW.x, 1.15, SHOW.z);
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
  autoFireTick(dt);
  // поле зрения из настроек: player.js ведёт камеру в «логических» градусах (BASE_FOV), здесь масштабируем
  const fk = (settings.fov || BASE_FOV) / BASE_FOV;
  if (fk !== 1) camera.fov /= fk;
  updatePlayer(dt);
  if (fk !== 1) { camera.fov *= fk; camera.updateProjectionMatrix(); }
  updateEffects(dt);
  vigA = Math.max(0, vigA - dt * 1.2); vig.style.opacity = vigA.toFixed(3);
  for (const d of dirs) if (d.dataset.t > 0) { d.dataset.t = Math.max(0, d.dataset.t - dt * 1.2); d.style.opacity = d.dataset.t; }
  updateHUD(); drawRadar(dt);
  if (!boardEl.hidden && Math.floor(gt * 2) !== Math.floor((gt - dt) * 2)) renderTables($('#tables'));
}
function frame(t) {
  requestAnimationFrame(frame);
  // ограничение FPS: пропускаем кадры, пока не пройдёт интервал (с допуском на дрожание vsync)
  const cap = settings.fpsCap;
  if (cap && t - perf.lastRender < 1000 / cap - 2.5) return;
  perf.lastRender = t;
  const rawMs = t - last;
  const dt = Math.min(0.05, rawMs / 1000); last = t;
  perfTick(rawMs);
  if (master && master._vol !== settings.volume) { master._vol = settings.volume; master.gain.value = 0.72 * settings.volume; }
  update(dt);
  renderer.clear();
  renderer.render(scene, camera);
  if (state !== 'menu' && state !== 'over' && player.alive) { renderer.clearDepth(); renderer.render(vmScene, vmCam); }
}

applyRes();
resetMenuScene();
setScreen('menu');
els.fps.hidden = !settings.showFps;
bus.on('settings:changed', () => { els.fps.hidden = !settings.showFps; });
requestAnimationFrame(frame);
window.__game = {
  get units() { return units; }, get player() { return player; }, get state() { return state; }, get paused() { return paused; },
  input, joy, VM, camera, settings, equip, giveAmmo, perf, layout: () => layout, TOUCH_BTNS,
  openSettings, closeSettings, openEditor, closeEditor, openBuy, closeBuy, openBoard, gunIcon, applyRes, setPause,
};
