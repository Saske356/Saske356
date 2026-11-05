'use strict';
/* ---------------- ввод ---------------- */
// Общий ввод. crouch/walk/use — удержание; use — действие (заложить, разминировать, подобрать).
// useAvailable/useLabel выставляет игровой код, интерфейс показывает кнопку действия, когда она нужна.
// Разовые действия идут через шину: bus.emit('action:knife' | 'action:grenade' | 'action:drop' | 'action:slot', ...)
const input = { fire: false, jump: false, crouch: false, walk: false, use: false, useAvailable: false, useLabel: '', keys: {} };
const joy = { id: null, ox: 0, oy: 0, x: 0, y: 0 };
const looks = new Map();
const lookSens = () => settings.sens * 0.0042 * (camera.fov / BASE_FOV);
function look(dx, dy) {
  if (!player || !player.alive || state === 'menu' || state === 'over' || paused) return;
  player.yaw -= dx * lookSens(); player.pitch = clamp(player.pitch - dy * lookSens(), -1.45, 1.45);
}
let specIndex = 0;
const touchEl = $('#touch'), joyEl = $('#joy');
touchEl.addEventListener('pointerdown', e => {
  e.preventDefault(); initAudio();
  const btn = e.target.closest('[data-btn]');
  if (player && !player.alive && !btn) specIndex++;
  const role = btn ? btn.dataset.btn : (e.clientX < innerWidth * 0.42 ? 'joy' : 'look');
  if (btn) btn.classList.add('on');
  try { touchEl.setPointerCapture(e.pointerId); } catch (err) {}
  if (role === 'joy') {
    if (joy.id !== null) return;
    joy.id = e.pointerId; joy.ox = e.clientX; joy.oy = e.clientY; joy.x = joy.y = 0;
    joyEl.style.display = 'block'; joyEl.style.left = e.clientX + 'px'; joyEl.style.top = e.clientY + 'px';
    joyEl.firstElementChild.style.transform = '';
    return;
  }
  looks.set(e.pointerId, { role, x: e.clientX, y: e.clientY, btn });
  if (role === 'fire') input.fire = true;
  else if (role === 'jump') input.jump = true;
  else if (role === 'reload') { if (player.alive) startReload(player); }
  else if (role === 'swap') swapWeapon();
  else if (role === 'scope') toggleScope();
}, { passive: false });
touchEl.addEventListener('pointermove', e => {
  if (e.pointerId === joy.id) {
    let dx = e.clientX - joy.ox, dy = e.clientY - joy.oy; const d = Math.hypot(dx, dy), max = 55;
    if (d > max) { dx *= max / d; dy *= max / d; }
    joy.x = dx / max; joy.y = -dy / max;
    joyEl.firstElementChild.style.transform = `translate(${dx}px, ${dy}px)`;
    return;
  }
  const l = looks.get(e.pointerId); if (!l) return;
  if (l.role === 'look' || l.role === 'fire') look(e.clientX - l.x, e.clientY - l.y);
  l.x = e.clientX; l.y = e.clientY;
});
function endPointer(e) {
  if (e.pointerId === joy.id) { joy.id = null; joy.x = joy.y = 0; joyEl.style.display = 'none'; return; }
  const l = looks.get(e.pointerId); if (!l) return;
  if (l.btn) l.btn.classList.remove('on');
  looks.delete(e.pointerId);
  if (l.role === 'fire') input.fire = [...looks.values()].some(v => v.role === 'fire');
}
touchEl.addEventListener('pointerup', endPointer);
touchEl.addEventListener('pointercancel', endPointer);

const locked = () => document.pointerLockElement === canvas;
function requestLock() {
  if (isTouch) return;
  try { const p = canvas.requestPointerLock(); if (p && p.catch) p.catch(() => {}); } catch (e) {}
}
function exitLock() { try { if (locked()) document.exitPointerLock(); } catch (e) {} }
canvas.addEventListener('mousedown', e => {
  if (isTouch || state === 'menu' || state === 'over' || paused) return;
  initAudio();
  if (!player.alive) { specIndex++; return; }
  if (!locked()) requestLock();
  if (e.button === 0) input.fire = true;
  if (e.button === 2) toggleScope();
});
addEventListener('mouseup', e => { if (e.button === 0 && !isTouch) input.fire = false; });
addEventListener('mousemove', e => {
  if (isTouch) return;
  if (locked() || (e.buttons & 1)) look(e.movementX || 0, e.movementY || 0);
});
canvas.addEventListener('contextmenu', e => e.preventDefault());
let wasLocked = false;
document.addEventListener('pointerlockchange', () => {
  if (wasLocked && !locked() && (state === 'live' || state === 'freeze' || state === 'roundEnd') && $('#buy').hidden && $('#board').hidden) setPause(true);
  wasLocked = locked();
});
addEventListener('keydown', e => {
  const k = e.code;
  if (k === 'Tab') { e.preventDefault(); if (!e.repeat && state !== 'menu' && state !== 'over') openBoard(); return; }
  if (e.repeat) return;
  input.keys[k] = true;
  if (state === 'menu' || state === 'over') return;
  if (k === 'Space') { input.jump = true; e.preventDefault(); }
  if (k === 'KeyR' && player.alive) startReload(player);
  if (k === 'KeyQ') swapWeapon();
  if (k === 'Digit1' && player.primary) equip(player, player.primary);
  if (k === 'Digit2') equip(player, 'pistol');
  if (k === 'KeyB') { $('#buy').hidden ? openBuy() : closeBuy(); }
  if (k === 'Escape' && !locked()) { if (!$('#buy').hidden) closeBuy(); else if (!$('#board').hidden) closeBoard(); else setPause(!paused); }
});
addEventListener('keyup', e => { input.keys[e.code] = false; if (e.code === 'Tab') closeBoard(); });
addEventListener('blur', () => { input.keys = {}; input.fire = false; });

function equip(u, key, instant) {
  if (!u.ammo[key]) return;
  if (u.cur === key && !instant) return;
  u.cur = key; u.reloading = 0; u.scoped = false; u.sprayN = 0;
  u.nextShot = Math.max(u.nextShot, gt + (instant ? 0 : 0.45));
  if (u.isPlayer) { for (const g in VM) VM[g].g.visible = g === key; vmState.swap = instant ? 0 : 1; }
  else setBotWeapon(u);
}
function swapWeapon() {
  if (!player.alive) return;
  if (player.cur === 'pistol' && player.primary) equip(player, player.primary); else equip(player, 'pistol');
}
function toggleScope() { if (!player.alive || player.reloading > 0) return; player.scoped = !player.scoped; }
