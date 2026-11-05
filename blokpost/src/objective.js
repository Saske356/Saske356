'use strict';
/* ---------------- режим «Подрыв»: заряд, закладка, разминирование, взрыв, HUD режима ---------------- */
// Состояние заряда: 'none' | 'carried' | 'dropped' | 'planted' | 'defused' | 'exploded'.
// Таймер заложенного заряда — это roundT (main.js показывает его вместо времени раунда и вызывает endRound по нулю).
const CHARGE = { plant: 3, defuse: 7, defuseKit: 3.5, radius: 22, dmg: 520, useDist: 1.7, pickDist: 1.3 };
const KIT_PRICE = 400;
const chargeState = { state: 'none', carrier: null, pos: new THREE.Vector3(), site: null, planter: null, plantedRound: false, beepT: 0, dropT: 0 };
const objStats = { plants: 0, defuses: 0, explosions: 0, pickups: 0, drops: 0 };

/* ---------- модели заряда ---------- */
const chargeMatBody = new THREE.MeshLambertMaterial({ color: 0x3d4630 });
const chargeMatPanel = new THREE.MeshLambertMaterial({ color: 0x1d2122 });
const chargeMatTape = new THREE.MeshLambertMaterial({ color: 0xc9a43a });
function makeChargeMesh() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.13, 0.24), chargeMatBody); body.position.y = 0.065; g.add(body);
  const panel = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.03, 0.13), chargeMatPanel); panel.position.set(-0.04, 0.14, 0); g.add(panel);
  const tape = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.135, 0.25), chargeMatTape); tape.position.set(0.11, 0.066, 0); g.add(tape);
  return g;
}
const chargeMesh = makeChargeMesh();
const chargeLed = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0xff3020, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
chargeLed.scale.set(0.22, 0.22, 0.22); chargeLed.position.set(0.06, 0.17, 0.03); chargeMesh.add(chargeLed);
chargeMesh.visible = false; scene.add(chargeMesh);
// заряд за спиной у бота-носителя
const packGeo = new THREE.BoxGeometry(0.3, 0.34, 0.14);
function setPack(u, on) {
  if (!u.mesh) return;
  if (on && !u.mesh.pack) { const m = new THREE.Mesh(packGeo, chargeMatBody); m.position.set(0, 0.3, 0.2); u.mesh.chest.add(m); u.mesh.pack = m; }
  if (u.mesh.pack) u.mesh.pack.visible = on;
}

/* ---------- взрыв: вспышка, огненный шар, дым, искры ---------- */
const boomParts = [];
for (let i = 0; i < 6; i++) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: i < 3 ? 0xffb060 : 0xff6a20, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  s.visible = false; s.userData = { t: 0, life: 1, v: new THREE.Vector3(), s0: 1, s1: 6 }; scene.add(s); boomParts.push(s);
}
const smokeMat = new THREE.MeshBasicMaterial({ color: 0x2c2926, transparent: true, opacity: 0, depthWrite: false });
const boomSmoke = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), smokeMat); boomSmoke.visible = false; scene.add(boomSmoke);
let boomT = -1;
function boomFx(p) {
  boomParts.forEach((s, i) => {
    s.position.set(p.x + rand(-0.6, 0.6), p.y + 0.6 + rand(0, 1.2), p.z + rand(-0.6, 0.6));
    s.userData.v.set(rand(-1.5, 1.5), rand(1, 3.5), rand(-1.5, 1.5));
    s.userData.t = 0; s.userData.life = i < 2 ? 0.35 : rand(0.6, 1.1); s.userData.s0 = i < 2 ? 4 : 1.5; s.userData.s1 = i < 2 ? 16 : rand(5, 9);
    s.material.opacity = 1; s.visible = true;
  });
  boomSmoke.position.set(p.x, p.y + 1, p.z); boomSmoke.scale.setScalar(0.5); boomSmoke.visible = true; boomT = 0;
  const q = new THREE.Vector3();
  for (let i = 0; i < 4; i++) { q.set(p.x + rand(-1, 1), p.y + 0.5 + rand(0, 1), p.z + rand(-1, 1)); burst(q, i % 2 ? 0xffd27a : 0xff7a30, 12); }
  worldFlash(q.set(p.x, p.y + 0.8, p.z));
}
function updateBoomFx(dt) {
  for (const s of boomParts) if (s.visible) {
    const d = s.userData; d.t += dt; const k = d.t / d.life;
    if (k >= 1) { s.visible = false; continue; }
    s.position.addScaledVector(d.v, dt); s.scale.setScalar(d.s0 + (d.s1 - d.s0) * Math.sqrt(k)); s.material.opacity = 1 - k * k;
  }
  if (boomT >= 0) {
    boomT += dt; const k = boomT / 3.2;
    if (k >= 1) { boomSmoke.visible = false; boomT = -1; }
    else { boomSmoke.scale.setScalar(1 + 7 * Math.sqrt(k)); boomSmoke.position.y += dt * 0.6; smokeMat.opacity = 0.55 * Math.min(1, boomT * 4) * (1 - k); }
  }
}
function sfxBoom(vol) {
  if (!AC || !settings.sound || vol < 0.02) return;
  const t = AC.currentTime;
  const src = AC.createBufferSource(); src.buffer = noiseBuf; src.loop = true;
  const f = AC.createBiquadFilter(); f.type = 'lowpass';
  f.frequency.setValueAtTime(2400, t); f.frequency.exponentialRampToValueAtTime(90, t + 1.6);
  const g = AC.createGain(); g.gain.setValueAtTime(Math.min(1.2, vol * 1.4), t); g.gain.exponentialRampToValueAtTime(0.001, t + 1.8);
  src.connect(f); f.connect(g); g.connect(master); src.start(t); src.stop(t + 1.9);
  const o = AC.createOscillator(); o.type = 'sine';
  o.frequency.setValueAtTime(90, t); o.frequency.exponentialRampToValueAtTime(28, t + 0.9);
  const og = AC.createGain(); og.gain.setValueAtTime(Math.min(1, vol), t); og.gain.exponentialRampToValueAtTime(0.001, t + 1);
  o.connect(og); og.connect(master); o.start(t); o.stop(t + 1.05);
}

/* ---------- ход режима ---------- */
const objSiteName = id => { const s = SITES.find(s => s.id === id); return s ? s.name : 'Точка ' + id; };
function resetObjective() {
  chargeState.state = 'none'; chargeState.carrier = null; chargeState.site = null; chargeState.planter = null; chargeState.plantedRound = false;
  chargeMesh.visible = false; boomParts.forEach(s => s.visible = false); boomSmoke.visible = false; boomT = -1;
  if (typeof units !== 'undefined') for (const u of units) { u.hasCharge = false; setPack(u, false); }
  objHud.hide();
}
// Активные точки матча: mode.sites === 1 — одна случайная точка на матч (режим «Союзники»), иначе все
let objActive = null;
function objPickSites() { objActive = mode.bomb && mode.sites === 1 && SITES.length > 1 ? [pick(SITES).id] : null; }
const objSiteOn = id => !objActive || objActive.includes(id);
const objSites = () => SITES.filter(s => objSiteOn(s.id));
function objInSite(x, z) { const id = inSite(x, z); return id && objSiteOn(id) ? id : null; }
function objRoundStart() {
  resetObjective();
  if (!mode.bomb) return;
  const atk = units.filter(u => u.side === 'atk' && u.alive);
  if (!atk.length) return;
  giveCharge(pick(atk));
}
function giveCharge(u) {
  for (const o of units) if (o !== u && o.hasCharge) { o.hasCharge = false; setPack(o, false); }
  u.hasCharge = true; chargeState.state = 'carried'; chargeState.carrier = u; chargeMesh.visible = false;
  setPack(u, !u.isPlayer);
}
function dropCharge(u) {
  u.hasCharge = false; setPack(u, false);
  chargeState.state = 'dropped'; chargeState.carrier = null; chargeState.dropT = gt;
  chargeState.pos.set(u.pos.x, 0, u.pos.z);
  chargeMesh.position.copy(chargeState.pos); chargeMesh.rotation.set(0, rand(0, 6), 0); chargeMesh.visible = true; chargeLed.visible = false;
  objStats.drops++;
}
function objOnDeath(victim) {
  if (victim.hasCharge && state === 'live') {
    dropCharge(victim);
    if (teamSide[player.team] === 'atk') objHud.note('Заряд потерян — подберите его');
  } else if (victim.hasCharge) { victim.hasCharge = false; setPack(victim, false); }
}
function pickupCharge(u) {
  giveCharge(u); objStats.pickups++;
  if (u.isPlayer) { beep(740, 0.08, 0.08, 'triangle'); objHud.note('Заряд у тебя'); }
  else if (u.team === player.team) objHud.note(u.name + ' подобрал заряд');
}
function plantCharge(u) {
  const site = objInSite(u.pos.x, u.pos.z);
  u.hasCharge = false; u.planting = false; u.useT = 0; setPack(u, false);
  chargeState.state = 'planted'; chargeState.carrier = null; chargeState.site = site; chargeState.planter = u; chargeState.plantedRound = true; chargeState.beepT = 0;
  chargeState.pos.set(u.pos.x, 0, u.pos.z);
  chargeMesh.position.copy(chargeState.pos); chargeMesh.rotation.set(0, u.yaw, 0); chargeMesh.visible = true; chargeLed.visible = true;
  roundT = mode.chargeTime || 40;
  u.money = Math.min(MONEY_CAP, u.money + ECON.plantSelf);
  objStats.plants++;
  showMsg('Заряд заложен', objSiteName(site) + ' · ' + Math.round(roundT) + ' секунд');
  beep(980, 0.12, 0.1, 'square');
  bus.emit('charge:planted', site, u);
}
function defuseCharge(u) {
  u.defusing = false; u.useT = 0;
  chargeState.state = 'defused'; chargeLed.visible = false;
  u.money = Math.min(MONEY_CAP, u.money + ECON.defuseSelf);
  objStats.defuses++;
  if (units.some(o => o.alive && o.side === 'atk')) objStats.defusesUnderFire = (objStats.defusesUnderFire || 0) + 1;
  bus.emit('charge:defused', u);
  endRound(u.team, (u.isPlayer ? 'Ты разминировал заряд' : u.name + ' разминировал заряд'), 'defuse');
}
function explodeCharge() {
  const p = chargeState.pos;
  chargeState.state = 'exploded'; chargeMesh.visible = false;
  objStats.explosions++;
  boomFx(p);
  const L = listener(); sfxBoom(1 / (1 + Math.hypot(L.x - p.x, L.z - p.z) / 25));
  if (player.alive) { const d = player.pos.distanceTo(p); if (d < 45) { player.punch += 0.12 * (1 - d / 45); player.punchY += rand(-0.06, 0.06); } }
  for (const u of units) {
    if (!u.alive) continue;
    const d = Math.hypot(u.pos.x - p.x, u.pos.z - p.z);
    if (d >= CHARGE.radius) continue;
    let dmg = CHARGE.dmg * Math.pow(1 - d / CHARGE.radius, 1.6);
    if (u.armor > 0) { const ab = Math.min(u.armor, dmg * 0.3); u.armor -= ab; dmg -= ab; }
    u.hp -= dmg;
    if (u.hp <= 0) { // гибель от взрыва — без ленты убийств и награды
      u.hp = 0; u.alive = false; u.deaths++; u.planting = u.defusing = false;
      if (!u.isPlayer) { u.deathT = 0.001; if (u.marker) u.marker.visible = false; }
    } else if (u.isPlayer) hurtFx({ pos: p });
  }
  bus.emit('charge:exploded', chargeState.site);
}
// Вышло время раунда (или таймер заложенного заряда)
function objTimeout() {
  const atk = sideTeam('atk'), def = sideTeam('def');
  if (chargeState.state === 'planted') {
    const site = chargeState.site;
    explodeCharge();
    endRound(atk, 'Заряд сработал' + (site ? ' — ' + objSiteName(site) : ''), 'explode');
  } else endRound(def, 'Время вышло — защита удержала точки', 'time');
}
// что может сделать боец прямо сейчас: 'plant' | 'defuse' | 'pickup' | null
function objActionFor(u) {
  if (!mode.bomb || state !== 'live' || !u.alive) return null;
  const cs = chargeState;
  if (u.side === 'atk') {
    if (u.hasCharge && u.onGround && objInSite(u.pos.x, u.pos.z)) return 'plant';
    if (cs.state === 'dropped' && Math.hypot(u.pos.x - cs.pos.x, u.pos.z - cs.pos.z) < CHARGE.pickDist + 0.3) return 'pickup';
  } else if (u.side === 'def' && cs.state === 'planted' && Math.hypot(u.pos.x - cs.pos.x, u.pos.z - cs.pos.z) < CHARGE.useDist) return 'defuse';
  return null;
}
const defuseTime = u => u.kit ? CHARGE.defuseKit : CHARGE.defuse;
let objUseLatch = false, objWasBomb = true;
// Вызывается раз в кадр (из bots.js, перед ботами), только когда игра идёт
function objTick(dt) {
  updateBoomFx(dt);
  if (!mode.bomb) { if (objWasBomb) { objHud.hide(); objWasBomb = false; } return; }
  objWasBomb = true;
  const cs = chargeState;
  // игрок: доступное действие и удержание (input.use ставит интерфейс; на ПК — клавиша E)
  const act = objActionFor(player);
  const labels = { plant: 'Заложить', defuse: 'Разминировать', pickup: 'Подобрать заряд' };
  input.useAvailable = !!act; input.useLabel = act ? labels[act] : '';
  const wants = !!(input.use || (input.keys && input.keys.KeyE));
  const still = Math.hypot(player.vx, player.vz) < 0.9;
  if (act === 'pickup') { if (wants && !objUseLatch) pickupCharge(player); }
  player.planting = act === 'plant' && wants && still && !input.fire;
  player.defusing = act === 'defuse' && wants && still && !input.fire;
  objUseLatch = wants;
  if (state === 'live') {
    for (const u of units) {
      if (!u.alive) continue;
      if (u.planting) {
        if (!u.hasCharge || !objInSite(u.pos.x, u.pos.z) || Math.hypot(u.vx, u.vz) > 1.2) { u.planting = false; u.useT = 0; }
        else { u.useT += dt; if (u.useT >= CHARGE.plant) { plantCharge(u); break; } }
      } else if (u.defusing) {
        if (cs.state !== 'planted' || Math.hypot(u.pos.x - cs.pos.x, u.pos.z - cs.pos.z) > CHARGE.useDist + 0.3 || Math.hypot(u.vx, u.vz) > 1.2) { u.defusing = false; u.useT = 0; }
        else { u.useT += dt; if (u.useT >= defuseTime(u)) { defuseCharge(u); break; } }
      } else u.useT = 0;
      // боты атаки подбирают заряд, проходя рядом
      if (cs.state === 'dropped' && !u.isPlayer && u.side === 'atk' && Math.hypot(u.pos.x - cs.pos.x, u.pos.z - cs.pos.z) < CHARGE.pickDist) pickupCharge(u);
    }
    // писк заряда: чаще к концу таймера
    if (cs.state === 'planted') {
      cs.beepT -= dt;
      const k = clamp(roundT / (mode.chargeTime || 40), 0, 1);
      if (cs.beepT <= 0) {
        cs.beepT = 0.12 + 0.88 * k;
        const L = listener(), d = Math.hypot(L.x - cs.pos.x, L.z - cs.pos.z);
        beep(roundT < 3 ? 1760 : 1320, 0.07, 0.09 / (1 + d / 14), 'square');
        chargeLed.visible = true; cs.ledT = 0.08;
      }
      if (cs.ledT > 0) { cs.ledT -= dt; if (cs.ledT <= 0) chargeLed.visible = false; }
    }
  }
  objHud.update(dt);
}

/* ---------- HUD режима ---------- */
injectCSS('objective', `
  #objBar { position: absolute; left: 50%; top: 60%; transform: translateX(-50%); display: none; flex-direction: column; align-items: center; gap: 4px; }
  #objBar.on { display: flex; }
  #objBar b { font: 700 12px var(--f-body); letter-spacing: .14em; text-transform: uppercase; text-shadow: 0 1px 4px rgba(0,0,0,.8); }
  #objBar .tr { width: 200px; height: 6px; border-radius: 3px; background: rgba(255,255,255,.14); overflow: hidden; }
  #objBar .tr i { display: block; height: 100%; background: var(--signal); transform-origin: left; transform: scaleX(0); }
  #objBar.def .tr i { background: var(--steel); }
  #objBar small { font-size: 11px; color: var(--dim); letter-spacing: .1em; }
  #objHint { position: absolute; left: 50%; top: 60%; transform: translateX(-50%); font: 600 12px var(--f-body); letter-spacing: .12em; text-transform: uppercase;
             color: var(--text); background: var(--panel); border: 1px solid var(--panel-line); border-radius: 6px; padding: 4px 10px; display: none; }
  #objHint.on { display: block; }
  #objCarry { position: absolute; left: max(14px, var(--sl)); bottom: calc(66px + var(--sb)); display: none; align-items: center; gap: 6px;
              font: 700 11px var(--f-body); letter-spacing: .16em; text-transform: uppercase; color: var(--signal);
              background: var(--panel); border: 1px solid var(--panel-line); border-radius: 6px; padding: 4px 8px; }
  #objCarry.on { display: flex; }
  #objCarry .ic { width: 16px; height: 11px; border-radius: 2px; background: #59633f; border: 1px solid #c9a43a; position: relative; }
  #objCarry .ic::after { content: ""; position: absolute; right: 2px; top: 2px; width: 4px; height: 4px; border-radius: 50%; background: #ff4a3d; }
  #objCarry.kit { color: var(--steel); } #objCarry.kit .ic { background: #2b4b55; border-color: var(--steel); } #objCarry.kit .ic::after { background: var(--steel); }
  #objTimer { position: absolute; top: calc(62px + var(--st)); left: 50%; transform: translateX(-50%); display: none; align-items: center; gap: 8px;
              background: rgba(90, 18, 12, .78); border: 1px solid rgba(255, 90, 70, .55); border-radius: 6px; padding: 3px 10px;
              font: 700 12px var(--f-body); letter-spacing: .12em; text-transform: uppercase; white-space: nowrap; }
  #objTimer.on { display: flex; }
  #objTimer i { width: 8px; height: 8px; border-radius: 50%; background: #ff4a3d; box-shadow: 0 0 8px #ff4a3d; }
  #objTimer.blink i { opacity: .25; }
  #objTimer b { font-family: var(--f-num); font-size: 14px; }
  #objNote { position: absolute; left: 50%; top: calc(92px + var(--st)); transform: translateX(-50%); font: 600 12px var(--f-body); letter-spacing: .1em;
             color: var(--signal); text-shadow: 0 1px 6px rgba(0,0,0,.9); white-space: nowrap; opacity: 0; transition: opacity .3s; }
  #objNote.on { opacity: 1; }
  .objMark { position: absolute; left: 0; top: 0; display: none; flex-direction: column; align-items: center; gap: 1px; will-change: transform; }
  .objMark.on { display: flex; }
  .objMark b { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font: 400 13px var(--f-display);
               background: rgba(13,19,22,.6); border: 2px solid rgba(242,203,76,.75); color: var(--signal); }
  .objMark small { font: 600 10px var(--f-num); color: var(--text); text-shadow: 0 1px 3px #000; }
  .objMark.ch b { border-color: #ff4a3d; color: #ff8a7a; font-size: 10px; }
  .objMark.ch.drop b { border-color: var(--signal); color: var(--signal); }
  #objRadar { position: absolute; pointer-events: none; }
`);
const objHud = (() => {
  const hud = $('#hud');
  const mk = (tag, id, cls, html) => { const e = document.createElement(tag); if (id) e.id = id; if (cls) e.className = cls; if (html) e.innerHTML = html; hud.appendChild(e); return e; };
  const bar = mk('div', 'objBar', '', '<b></b><div class="tr"><i></i></div><small></small>');
  const hint = mk('div', 'objHint');
  const carry = mk('div', 'objCarry', '', '<span class="ic"></span><span></span>');
  const timer = mk('div', 'objTimer', '', '<i></i><span></span><b></b>');
  const note = mk('div', 'objNote');
  const marks = {};
  for (const s of SITES) { const m = mk('div', null, 'objMark', '<b></b><small></small>'); m.firstChild.textContent = s.id === 'B' ? 'Б' : s.id; marks[s.id] = m; }
  const chM = mk('div', null, 'objMark ch', '<b>З</b><small></small>');
  let noteTO = 0, radarC = null, radarG = null, layoutN = 0;
  const cache = new WeakMap();
  const txt = (el, v) => { if (cache.get(el) !== v) { cache.set(el, v); el.textContent = v; } };
  const tog = (el, cls, v) => { if (el.classList.contains(cls) !== v) el.classList.toggle(cls, v); };
  const pv = new THREE.Vector3(), objV = new THREE.Vector3();
  function place(el, x, y, z, label) {
    pv.set(x, y, z).project(camera);
    const vis = pv.z < 1 && pv.z > -1;
    tog(el, 'on', vis);
    if (!vis) return;
    const sx = clamp((pv.x + 1) / 2 * innerWidth, 16, innerWidth - 16), sy = clamp((1 - pv.y) / 2 * innerHeight, 40, innerHeight - 30);
    el.style.transform = `translate(${(sx - 11) | 0}px, ${(sy - 11) | 0}px)`;
    txt(el.lastChild, label);
  }
  function radar() {
    const base = document.getElementById('radar'); if (!base) return;
    if (!radarC) { radarC = document.createElement('canvas'); radarC.id = 'objRadar'; base.parentNode.appendChild(radarC); radarG = radarC.getContext('2d'); layoutN = 0; }
    if (layoutN-- <= 0) {
      layoutN = 30;
      radarC.width = base.width; radarC.height = base.height;
      Object.assign(radarC.style, { left: base.offsetLeft + 'px', top: base.offsetTop + 'px', width: base.offsetWidth + 'px', height: base.offsetHeight + 'px' });
    }
    // та же проекция, что у drawRadar в hud.js: центр — игрок (или камера наблюдения), радиус RAD_R м, поворот по взгляду
    const W = radarC.width, H = radarC.height, c = W / 2, R = typeof RAD_R !== 'undefined' ? RAD_R : 30, k = c / R;
    const cx = player.alive ? player.pos.x : camera.position.x, cz = player.alive ? player.pos.z : camera.position.z;
    const rot = settings.radarRotate !== false;
    let yaw = player.yaw;
    if (!player.alive) { objV.set(0, 0, -1).applyQuaternion(camera.quaternion); yaw = Math.atan2(-objV.x, -objV.z); }
    const cr = rot ? Math.cos(yaw) : 1, sr = rot ? Math.sin(yaw) : 0;
    // мировая точка → экран радара; дальние прижимаются к краю круга
    const toScr = (x, z, edge) => {
      const dx = x - cx, dz = z - cz; let sx = c + (dx * cr - dz * sr) * k, sy = c + (dx * sr + dz * cr) * k;
      const ex = sx - c, ey = sy - c, d = Math.hypot(ex, ey), m = c - edge;
      if (d > m) { sx = c + ex / d * m; sy = c + ey / d * m; }
      return [sx, sy];
    };
    radarG.setTransform(1, 0, 0, 1, 0, 0);
    radarG.clearRect(0, 0, W, H);
    radarG.save();
    radarG.beginPath(); radarG.arc(c, c, c - 1, 0, Math.PI * 2); radarG.clip();
    radarG.translate(c, c); if (rot) radarG.rotate(yaw); radarG.scale(k, k); radarG.translate(-cx, -cz);
    radarG.fillStyle = 'rgba(242,203,76,.16)';
    for (const s of objSites()) for (const q of s.cells) radarG.fillRect(q[0] * CELL, q[1] * CELL, CELL + 0.05, CELL + 0.05);
    radarG.restore();
    radarG.font = '700 14px Rubik, sans-serif'; radarG.textAlign = 'center'; radarG.textBaseline = 'middle';
    for (const s of objSites()) {
      const [sx, sy] = toScr(s.center.x, s.center.z, 12);
      radarG.fillStyle = 'rgba(8,13,15,.72)'; radarG.beginPath(); radarG.arc(sx, sy, 9, 0, Math.PI * 2); radarG.fill();
      radarG.fillStyle = 'rgba(242,203,76,.95)'; radarG.fillText(s.id === 'B' ? 'Б' : s.id, sx, sy + 1);
    }
    const cs = chargeState, mineAtk = teamSide[player.team] === 'atk';
    let p = null;
    if (cs.state === 'planted') p = cs.pos;
    else if (mineAtk && cs.state === 'dropped') p = cs.pos;
    else if (mineAtk && cs.state === 'carried' && cs.carrier && !cs.carrier.isPlayer) p = cs.carrier.pos;
    if (p) {
      const [px, py] = toScr(p.x, p.z, 8);
      radarG.fillStyle = cs.state === 'planted' ? (Math.floor(gt * 4) % 2 ? '#ff4a3d' : '#ffb0a0') : '#f2cb4c';
      radarG.fillRect(px - 5, py - 4, 10, 8);
      radarG.strokeStyle = '#11171a'; radarG.lineWidth = 1.5; radarG.strokeRect(px - 5, py - 4, 10, 8);
    }
  }
  return {
    hide() {
      for (const el of [bar, hint, carry, timer, chM, ...Object.values(marks)]) tog(el, 'on', false);
      if (radarC) radarG.clearRect(0, 0, radarC.width, radarC.height);
      if (typeof input !== 'undefined') { input.useAvailable = false; input.useLabel = ''; }
    },
    note(t) { txt(note, t); tog(note, 'on', true); clearTimeout(noteTO); noteTO = setTimeout(() => tog(note, 'on', false), 2600); },
    update() {
      const p = player, cs = chargeState, mineAtk = teamSide[p.team] === 'atk';
      // полоса закладки/разминирования (своя или, в наблюдении, союзника)
      let actor = p.alive ? p : null;
      if (!actor) actor = units.find(u => u.team === p.team && u.alive && (u.planting || u.defusing));
      const busy = actor && (actor.planting || actor.defusing);
      tog(bar, 'on', !!busy);
      if (busy) {
        const need = actor.planting ? CHARGE.plant : defuseTime(actor);
        txt(bar.children[0], (actor.planting ? 'Закладка' : 'Разминирование') + (actor.isPlayer ? '' : ' · ' + actor.name));
        bar.children[1].firstChild.style.transform = `scaleX(${clamp(actor.useT / need, 0, 1).toFixed(3)})`;
        txt(bar.children[2], Math.max(0, need - actor.useT).toFixed(1) + ' с' + (actor.defusing && actor.kit ? ' · набор сапёра' : ''));
        tog(bar, 'def', !!actor.defusing);
      }
      const showHint = p.alive && input.useAvailable && !busy && !isTouch;
      tog(hint, 'on', showHint);
      if (showHint) txt(hint, 'E — ' + input.useLabel.toLowerCase());
      // носитель заряда / набор сапёра
      const carryOn = p.alive && (p.hasCharge || (p.side === 'def' && p.kit));
      tog(carry, 'on', !!carryOn);
      if (carryOn) { tog(carry, 'kit', !p.hasCharge); txt(carry.lastChild, p.hasCharge ? 'Заряд' : 'Набор сапёра'); }
      // таймер заряда
      const planted = cs.state === 'planted' && state === 'live';
      tog(timer, 'on', planted);
      if (planted) {
        txt(timer.children[1], 'Заряд · ' + (cs.site === 'B' ? 'Б' : cs.site || ''));
        txt(timer.children[2], Math.max(0, roundT).toFixed(roundT < 10 ? 1 : 0) + ' с');
        tog(timer, 'blink', !chargeLed.visible);
      }
      // метки точек и заряда на экране
      const live = state === 'live' || state === 'freeze';
      const camX = camera.position.x, camZ = camera.position.z;
      for (const s of SITES) { if (!objSiteOn(s.id)) { tog(marks[s.id], 'on', false); continue; }
        const m = marks[s.id];
        if (!live) { tog(m, 'on', false); continue; }
        const d = Math.hypot(s.center.x - camX, s.center.z - camZ);
        if (d < 7) { tog(m, 'on', false); continue; }
        place(m, s.center.x, 2.6, s.center.z, Math.round(d) + ' м');
      }
      let cp = null;
      if (cs.state === 'planted') cp = cs.pos;
      else if (mineAtk && cs.state === 'dropped') cp = cs.pos;
      if (live && cp) { tog(chM, 'drop', cs.state === 'dropped'); place(chM, cp.x, 0.9, cp.z, Math.round(Math.hypot(cp.x - camX, cp.z - camZ)) + ' м'); }
      else tog(chM, 'on', false);
      radar();
    },
  };
})();

/* ---------- закупка: набор сапёра (добавляется в список магазина ui.js без правки ui.js) ---------- */
function objKitButton() {
  if (typeof itemsEl === 'undefined' || !mode.bomb || !player || player.side !== 'def' || itemsEl.querySelector('#buy-kit')) return;
  const own = player.kit;
  const b = document.createElement('button'); b.className = 'item' + (own ? ' own' : ''); b.id = 'buy-kit';
  b.innerHTML = '<b></b><span></span><div class="st"></div><div class="p"></div>';
  b.children[0].textContent = 'Набор сапёра';
  b.children[1].textContent = 'Разминирование за ' + String(CHARGE.defuseKit).replace('.', ',') + ' с вместо ' + CHARGE.defuse;
  b.children[3].textContent = own ? 'Есть' : '$' + KIT_PRICE;
  b.disabled = own || player.money < KIT_PRICE || !canBuy();
  b.addEventListener('click', () => {
    if (!canBuy() || player.kit || player.money < KIT_PRICE) return;
    player.money -= KIT_PRICE; player.kit = true; beep(880, 0.06, 0.08, 'triangle'); renderBuy();
  });
  itemsEl.appendChild(b);
}
(function () {
  const el = document.getElementById('items');
  if (el && window.MutationObserver) new MutationObserver(() => objKitButton()).observe(el, { childList: true });
})();
