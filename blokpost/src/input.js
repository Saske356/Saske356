'use strict';
/* ---------------- ввод ---------------- */
// Общий ввод. crouch/walk/use — удержание; use — действие (заложить, разминировать, подобрать).
// useAvailable/useLabel выставляет игровой код, интерфейс показывает кнопку действия, когда она нужна.
// Разовые действия идут через шину: bus.emit('action:knife' | 'action:grenade' | 'action:drop' | 'action:slot', ...)
const input = { fire: false, jump: false, crouch: false, walk: false, use: false, useAvailable: false, useLabel: '', keys: {} };
const joy = { id: null, ox: 0, oy: 0, x: 0, y: 0, walk: false };
const JOY_MAX = 56, JOY_DEAD = 0.1, JOY_WALK = 0.55; // радиус, мёртвая зона, порог шага (меньше — шаг, больше — бег)
const looks = new Map();
// источники огня: касание/мышь (ручной) и автоогонь; input.fire пересчитывается только при их смене,
// чтобы внешний код (тесты) мог сам ставить input.fire
const fireSrc = { touch: false, mouse: false, auto: false };
const syncFire = () => { input.fire = fireSrc.touch || fireSrc.mouse || fireSrc.auto; };
const hold = { crouchKey: false, crouchTouch: false, crouchToggle: false, walkKey: false, useKey: false, useTouch: false };

const lookSens = () => settings.sens * (player && player.scoped ? settings.adsSens : 1) * 0.0042 * (camera.fov / (settings.fov || BASE_FOV));
const canLook = () => player && player.alive && state !== 'menu' && state !== 'over' && !paused;
function look(dx, dy) {
  if (!canLook()) return;
  if (settings.invertY) dy = -dy;
  player.yaw -= dx * lookSens(); player.pitch = clamp(player.pitch - dy * lookSens(), -1.45, 1.45);
}
let specIndex = 0;

/* ---------------- раскладка сенсорных кнопок ---------------- */
// h: 'l'|'r' — от какого края считать x; v: 't'|'b' — от какого края y. x, y — центр кнопки в px от края безопасной зоны.
// s — диаметр, sc — масштаб (редактор), o — непрозрачность. Левша зеркалит h.
const IC = {
  fire: '<circle cx="12" cy="12" r="6.5"/><path d="M12 2.5v4.5M12 17v4.5M2.5 12h4.5M17 12h4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
  scope: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/>',
  jump: '<path d="M5 14l7-7 7 7"/><path d="M5 19.5h14"/>',
  crouch: '<path d="M5 9l7 7 7-7"/><path d="M5 4.5h14"/>',
  reload: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 3.5v4.5H15"/>',
  swap: '<path d="M4 8h15l-3.5-3.5M20 16H5l3.5 3.5"/>',
  knife: '<path d="M3 19.5L14.5 8l2 2L5 21.5z"/><path d="M14.5 8l3-3.5c1.3-1.3 3.2-.4 3 1.4L16.5 10"/>',
  grenade: '<circle cx="11" cy="14" r="6.5"/><path d="M9 7.5V5h4v2.5M13 5.5l4-2.5 2 2"/>',
  drop: '<path d="M12 3v12M7 10.5l5 5 5-5"/><path d="M4.5 20.5h15"/>',
  use: '<path d="M12 3.5v6M8.5 6.5L12 3l3.5 3.5"/><rect x="5" y="12" width="14" height="8.5" rx="1.8"/>',
  buy: '<path d="M3 4h2.5l2.2 10.5h10.6L20.5 7H7"/><circle cx="9.5" cy="19" r="1.4"/><circle cx="16.5" cy="19" r="1.4"/>',
  board: '<path d="M4 6h16M4 12h16M4 18h16"/><path d="M9 4v16"/>',
  pause: '<path d="M9 5.5v13M15 5.5v13"/>',
};
const TOUCH_BTNS = [
  { id: 'fire',    role: 'fire',    name: 'Огонь',            s: 88, h: 'r', v: 'b', x: 142, y: 118, cls: 'red' },
  { id: 'fireL',   role: 'fire',    name: 'Огонь слева',      s: 58, h: 'l', v: 'b', x: 62,  y: 214, cls: 'red' },
  { id: 'scope',   role: 'scope',   name: 'Прицел',           s: 56, h: 'r', v: 'b', x: 230, y: 184 },
  { id: 'jump',    role: 'jump',    name: 'Прыжок',           s: 56, h: 'r', v: 'b', x: 48,  y: 54 },
  { id: 'crouch',  role: 'crouch',  name: 'Присед',           s: 48, h: 'r', v: 'b', x: 142, y: 38 },
  { id: 'reload',  role: 'reload',  name: 'Перезарядка',      s: 48, h: 'r', v: 'b', x: 48,  y: 120 },
  { id: 'swap',    role: 'swap',    name: 'Смена оружия',     s: 46, h: 'r', v: 'b', x: 48,  y: 178 },
  { id: 'knife',   role: 'knife',   name: 'Нож',              s: 40, h: 'r', v: 'b', x: 104, y: 202, action: 'action:knife' },
  { id: 'grenade', role: 'grenade', name: 'Граната',          s: 46, h: 'r', v: 'b', x: 232, y: 102, action: 'action:grenade' },
  { id: 'drop',    role: 'drop',    name: 'Выбросить',        s: 38, h: 'r', v: 'b', x: 290, y: 52, action: 'action:drop' },
  { id: 'use',     role: 'use',     name: 'Действие',         s: 62, h: 'r', v: 'b', x: 330, y: 150, cls: 'act' },
  { id: 'buy',     role: 'buy',     name: 'Закупка',          s: 44, h: 'l', v: 't', x: 156, y: 30, cls: 'sig' },
  { id: 'board',   role: 'board',   name: 'Счёт',             s: 40, h: 'r', v: 't', x: 94,  y: 28 },
  { id: 'pause',   role: 'pause',   name: 'Пауза',            s: 40, h: 'r', v: 't', x: 44,  y: 28 },
];
const LAYOUT_KEY = 'blokpost-layout';
let layout = {};
function loadLayout() { const l = store.get(LAYOUT_KEY, null); layout = l && typeof l === 'object' ? l : {}; }
function saveLayout() { store.set(LAYOUT_KEY, layout); }
function resetLayout() { layout = {}; store.del(LAYOUT_KEY); applyLayout(); }
// итоговое положение кнопки с учётом сохранённой раскладки и левши
function btnPos(def) {
  const l = layout[def.id] || {};
  const p = { h: l.h || def.h, v: l.v || def.v, x: l.x != null ? l.x : def.x, y: l.y != null ? l.y : def.y, sc: l.sc || 1, o: l.o != null ? l.o : 1 };
  if (settings.lefty) p.h = p.h === 'l' ? 'r' : 'l';
  p.size = Math.round(def.s * p.sc);
  return p;
}
function placeBtn(el, def) {
  const p = btnPos(def), half = p.size / 2;
  el.style.width = el.style.height = p.size + 'px';
  el.style.left = el.style.right = el.style.top = el.style.bottom = '';
  el.style[p.h === 'l' ? 'left' : 'right'] = `calc(var(--s${p.h}) + ${(p.x - half).toFixed(1)}px)`;
  el.style[p.v === 't' ? 'top' : 'bottom'] = `calc(var(--s${p.v}) + ${(p.y - half).toFixed(1)}px)`;
  el.style.setProperty('--o', p.o);
}
const touchEl = $('#touch'), joyEl = $('#joy');
const tbtn = {};
function makeTouchButton(def, parent) {
  const el = document.createElement('div');
  el.className = 'tb' + (def.cls ? ' ' + def.cls : '');
  el.id = 't' + def.id[0].toUpperCase() + def.id.slice(1);
  el.dataset.btn = def.role; el.dataset.id = def.id;
  el.setAttribute('aria-label', def.name);
  el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${IC[def.role] || IC[def.id]}</svg>` + (def.role === 'use' ? '<span class="tl"></span>' : '');
  parent.appendChild(el); placeBtn(el, def);
  return el;
}
for (const def of TOUCH_BTNS) tbtn[def.id] = makeTouchButton(def, touchEl);
function applyLayout() {
  for (const def of TOUCH_BTNS) placeBtn(tbtn[def.id], def);
  touchEl.classList.toggle('lefty', !!settings.lefty);
}
loadLayout(); applyLayout();
// кнопки, которые показываются только если кто-то обрабатывает действие (нож/граната/выброс — модуль боя)
function refreshTouchButtons() {
  for (const def of TOUCH_BTNS) if (def.action) tbtn[def.id].classList.toggle('na', !bus.has(def.action));
}
const touchUI = { use: null, useLabel: null, crouch: null };
// вызывается каждый кадр из HUD: кнопка действия и состояние приседа
function updateTouchUI() {
  const ua = !!input.useAvailable;
  if (touchUI.use !== ua) { touchUI.use = ua; tbtn.use.classList.toggle('show', ua); if (!ua) { hold.useTouch = false; syncHolds(); } }
  const lbl = input.useLabel || 'Действие';
  if (touchUI.useLabel !== lbl) { touchUI.useLabel = lbl; tbtn.use.lastElementChild.textContent = lbl; tbtn.use.setAttribute('aria-label', lbl); }
  if (touchUI.crouch !== input.crouch) { touchUI.crouch = input.crouch; tbtn.crouch.classList.toggle('lit', input.crouch); }
}
function syncHolds() {
  input.crouch = settings.crouchHold ? (hold.crouchKey || hold.crouchTouch) : hold.crouchToggle;
  input.walk = hold.walkKey || joy.walk;
  input.use = hold.useKey || hold.useTouch;
}
function crouchPress(down) {
  if (settings.crouchHold) hold.crouchTouch = down;
  else if (down) hold.crouchToggle = !hold.crouchToggle;
  syncHolds();
}
function resetHolds() {
  for (const k in hold) hold[k] = false;
  joy.walk = false; syncHolds();
}
bus.on('round:start', resetHolds);
bus.on('kill', v => { if (v && v.isPlayer) resetHolds(); });

function joyStart(e) {
  joy.id = e.pointerId; joy.ox = e.clientX; joy.oy = e.clientY; joy.x = joy.y = 0; joy.walk = false;
  joyEl.classList.add('on'); joyEl.style.left = e.clientX + 'px'; joyEl.style.top = e.clientY + 'px';
  joyEl.firstElementChild.style.transform = '';
}
function joyMove(e) {
  let dx = e.clientX - joy.ox, dy = e.clientY - joy.oy; const d = Math.hypot(dx, dy);
  if (d > JOY_MAX) { // плавающий джойстик: основание тянется за пальцем
    const k = (d - JOY_MAX) / d; joy.ox += dx * k; joy.oy += dy * k; dx *= JOY_MAX / d; dy *= JOY_MAX / d;
    joyEl.style.left = joy.ox + 'px'; joyEl.style.top = joy.oy + 'px';
  }
  let m = Math.min(1, Math.hypot(dx, dy) / JOY_MAX);
  const ang = Math.atan2(-dy, dx);
  if (m < JOY_DEAD) { joy.x = joy.y = 0; joy.walk = false; }
  else {
    joy.walk = m < JOY_WALK;
    const out = joy.walk ? 0.3 + (m - JOY_DEAD) / (JOY_WALK - JOY_DEAD) * 0.25 : 1;
    joy.x = Math.cos(ang) * out; joy.y = Math.sin(ang) * out;
  }
  joyEl.classList.toggle('walk', joy.walk);
  joyEl.firstElementChild.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
  syncHolds();
}
function joyEnd() { joy.id = null; joy.x = joy.y = 0; joy.walk = false; joyEl.classList.remove('on', 'walk'); syncHolds(); }
function inJoyZone(x) { return settings.lefty ? x > innerWidth * 0.58 : x < innerWidth * 0.42; }

touchEl.addEventListener('pointerdown', e => {
  e.preventDefault(); initAudio();
  const btn = e.target.closest('[data-btn]');
  if (player && !player.alive && !btn) specIndex++;
  const role = btn ? btn.dataset.btn : (inJoyZone(e.clientX) ? 'joy' : 'look');
  try { touchEl.setPointerCapture(e.pointerId); } catch (err) {}
  if (role === 'joy') { if (joy.id === null) joyStart(e); return; }
  if (btn) btn.classList.add('on');
  looks.set(e.pointerId, { role, x: e.clientX, y: e.clientY, t: e.timeStamp, btn });
  if (!player) return;
  switch (role) {
    case 'fire': fireSrc.touch = true; syncFire(); break;
    case 'jump': input.jump = true; break;
    case 'reload': if (player.alive) startReload(player); break;
    case 'swap': swapWeapon(); break;
    case 'scope': toggleScope(); break;
    case 'crouch': crouchPress(true); break;
    case 'use': hold.useTouch = true; syncHolds(); break;
    case 'knife': case 'grenade': case 'drop': if (player.alive) bus.emit('action:' + role); break;
    case 'buy': if (typeof openBuy === 'function') buyEl.hidden ? openBuy() : closeBuy(); break;
    case 'board': if (typeof openBoard === 'function') boardEl.hidden ? openBoard() : closeBoard(); break;
    case 'pause': setPause(!paused); break;
  }
}, { passive: false });
touchEl.addEventListener('pointermove', e => {
  if (e.pointerId === joy.id) { joyMove(e); return; }
  const l = looks.get(e.pointerId); if (!l) return;
  if (l.role === 'look' || l.role === 'fire') {
    let dx = e.clientX - l.x, dy = e.clientY - l.y;
    if (settings.accel > 0) {
      const dt = Math.max(1, e.timeStamp - l.t), sp = Math.hypot(dx, dy) / dt; // px/мс
      const f = 1 + settings.accel * clamp((sp - 0.25) / 1.2, 0, 1.6);
      dx *= f; dy *= f;
    }
    look(dx, dy);
  }
  l.x = e.clientX; l.y = e.clientY; l.t = e.timeStamp;
});
function endPointer(e) {
  if (e.pointerId === joy.id) { joyEnd(); return; }
  const l = looks.get(e.pointerId); if (!l) return;
  if (l.btn) l.btn.classList.remove('on');
  looks.delete(e.pointerId);
  const still = r => [...looks.values()].some(v => v.role === r);
  if (l.role === 'fire') { fireSrc.touch = still('fire'); syncFire(); }
  if (l.role === 'crouch' && !still('crouch')) crouchPress(false);
  if (l.role === 'use' && !still('use')) { hold.useTouch = false; syncHolds(); }
}
touchEl.addEventListener('pointerup', endPointer);
touchEl.addEventListener('pointercancel', endPointer);
function releaseTouches() {
  for (const l of looks.values()) if (l.btn) l.btn.classList.remove('on');
  looks.clear(); joyEnd(); fireSrc.touch = fireSrc.mouse = fireSrc.auto = false; syncFire(); resetHolds();
}

/* ---------------- автоогонь: враг под прицелом ---------------- */
const aimRay = new THREE.Raycaster(); aimRay.far = 90;
const _aimDir = new THREE.Vector3(), aimTargets = [];
let autoT = 0;
function autoFireTick(dt) {
  const want = settings.autoFire && isTouch;
  if (!want || !player || !player.alive || state !== 'live' || paused) { if (fireSrc.auto) { fireSrc.auto = false; syncFire(); } return; }
  autoT -= dt; if (autoT > 0) return;
  autoT = 0.05; // ~20 проверок в секунду
  const w = weaponOf(player);
  let on = false;
  if (!(w.scope && !player.scoped) && player.reloading <= 0) {
    aimTargets.length = 0;
    for (const m of levelMeshes) aimTargets.push(m);
    let any = false;
    for (const b of bots) if (b.alive && b.team !== player.team) { any = true; for (const h of b.mesh.hit) aimTargets.push(h); }
    if (any) {
      camera.updateMatrixWorld(); camera.getWorldDirection(_aimDir);
      aimRay.set(camera.position, _aimDir);
      const hit = aimRay.intersectObjects(aimTargets, false)[0];
      const u = hit && hit.object.userData.unit;
      on = !!(u && u.alive && u.team !== player.team && !(typeof smokeBlocks === 'function' &&
        smokeBlocks(camera.position.x, camera.position.y, camera.position.z, hit.point.x, hit.point.y, hit.point.z)));
    }
  }
  if (on !== fireSrc.auto) { fireSrc.auto = on; syncFire(); }
}

/* ---------------- мышь и клавиатура ---------------- */
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
  if (e.button === 0) { fireSrc.mouse = true; syncFire(); }
  if (e.button === 2) toggleScope();
});
addEventListener('mouseup', e => { if (e.button === 0 && !isTouch) { fireSrc.mouse = false; syncFire(); } });
addEventListener('mousemove', e => {
  if (isTouch) return;
  if (locked() || (e.buttons & 1 && state !== 'menu')) look(e.movementX || 0, e.movementY || 0);
});
canvas.addEventListener('contextmenu', e => e.preventDefault());
let wasLocked = false;
document.addEventListener('pointerlockchange', () => {
  if (wasLocked && !locked() && (state === 'live' || state === 'freeze' || state === 'roundEnd') && $('#buy').hidden && $('#board').hidden && !overlayOpen()) setPause(true);
  wasLocked = locked();
});
const overlayOpen = () => !$('#settings').hidden || !$('#layoutEd').hidden;
addEventListener('keydown', e => {
  const k = e.code;
  if (k === 'Tab') { e.preventDefault(); if (!e.repeat && state !== 'menu' && state !== 'over') openBoard(); return; }
  if (e.repeat) return;
  input.keys[k] = true;
  if (k === 'Escape' && overlayOpen()) { closeOverlays(); return; }
  if (state === 'menu' || state === 'over') return;
  if (k === 'Space') { input.jump = true; e.preventDefault(); }
  if (k === 'KeyR' && player.alive) startReload(player);
  if (k === 'KeyQ') swapWeapon();
  if (k === 'Digit1' && player.primary) equip(player, player.primary);
  if (k === 'Digit2') equip(player, 'pistol');
  if ((k === 'Digit3' || k === 'KeyV') && player.alive) bus.emit('action:knife');
  if ((k === 'Digit4' || k === 'KeyF') && player.alive) bus.emit('action:grenade');
  if (k === 'KeyG' && player.alive) bus.emit('action:drop');
  if (k === 'KeyE') { hold.useKey = true; syncHolds(); }
  if (k === 'ShiftLeft' || k === 'ShiftRight') { hold.walkKey = true; syncHolds(); }
  if (k === 'ControlLeft' || k === 'KeyC') { e.preventDefault(); hold.crouchKey = true; if (!settings.crouchHold) hold.crouchToggle = !hold.crouchToggle; syncHolds(); }
  if (k === 'KeyB') { $('#buy').hidden ? openBuy() : closeBuy(); }
  if (k === 'Escape' && !locked()) { if (!$('#buy').hidden) closeBuy(); else if (!$('#board').hidden) closeBoard(); else setPause(!paused); }
});
addEventListener('keyup', e => {
  const k = e.code; input.keys[k] = false;
  if (k === 'Tab') closeBoard();
  if (k === 'KeyE') hold.useKey = false;
  if (k === 'ShiftLeft' || k === 'ShiftRight') hold.walkKey = false;
  if (k === 'ControlLeft' || k === 'KeyC') hold.crouchKey = false;
  syncHolds();
});
addEventListener('blur', () => { input.keys = {}; fireSrc.mouse = false; syncFire(); hold.walkKey = hold.useKey = hold.crouchKey = false; syncHolds(); });

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
