'use strict';
/* ---------------- HUD ---------------- */
const els = {}; ['hp', 'ar', 'mag', 'res', 'money', 'wname', 'timer', 'scA', 'scB', 'aliveA', 'aliveB', 'fps'].forEach(id => els[id] = document.getElementById(id));
const cache = {};
const setT = (id, v) => { if (cache[id] !== v) { cache[id] = v; els[id].textContent = v; } };
const setCls = (el, key, cls, on) => { if (cache[key] !== on) { cache[key] = on; el.classList.toggle(cls, on); } };
const hpBar = $('#hpBar i'), arBar = $('#arBar i'), reloadBar = $('#reloadBar'), crossEl = $('#cross'), scopeEl = $('#scope'), ammoEl = $('#ammo'), redEl = $('#reddot');
const wIconEl = $('#wicon'), hudEl = $('#hud');
let lastGap = -1;

/* ---------------- иконки оружия: рендер модели GUNS[k].full в маленький кадр ---------------- */
// Для каждого ключа один раз: цветная картинка (магазин) и белый силуэт (лента, HUD). Кадр рендерится основным рендерером
// в WebGLRenderTarget, читается в canvas и сразу освобождается.
const ICON_W = 256, ICON_H = 96, iconCache = {};
function wName(k) {
  if (typeof WEAPONS !== 'undefined' && WEAPONS[k]) return WEAPONS[k].name;
  if (typeof GRENADES !== 'undefined' && GRENADES) { const g = Array.isArray(GRENADES) ? GRENADES.find(x => x.id === k) : GRENADES[k]; if (g && g.name) return g.name; }
  return ({ knife: 'Нож', he: 'Граната', flash: 'Светошумовая', smoke: 'Дым', charge: 'Заряд' })[k] || k;
}
function renderGunIcon(geo) {
  const SS = 2, W = ICON_W * SS, H = ICON_H * SS;
  geo.computeBoundingBox();
  const bb = geo.boundingBox, cy = (bb.min.y + bb.max.y) / 2, cz = (bb.min.z + bb.max.z) / 2;
  const lenZ = bb.max.z - bb.min.z, lenY = bb.max.y - bb.min.y;
  const halfW = Math.max(lenZ / 2, lenY / 2 * W / H) * 1.06, halfH = halfW * H / W;
  const cam = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, 0.01, 20);
  cam.position.set(bb.max.x + 2, cy, cz); cam.lookAt(0, cy, cz);
  const sc = new THREE.Scene();
  sc.add(new THREE.HemisphereLight(0xeef4f6, 0x3a332a, 1.15));
  const dl = new THREE.DirectionalLight(0xffffff, 0.9); dl.position.set(3, 4, 2); sc.add(dl);
  sc.add(new THREE.Mesh(geo, typeof gunMat !== 'undefined' ? gunMat : new THREE.MeshLambertMaterial({ vertexColors: true })));
  const rt = new THREE.WebGLRenderTarget(W, H);
  const prevRT = renderer.getRenderTarget(), prevC = renderer.getClearColor(new THREE.Color()), prevA = renderer.getClearAlpha();
  const buf = new Uint8Array(W * H * 4);
  try {
    renderer.setRenderTarget(rt); renderer.setClearColor(0x000000, 0); renderer.clear();
    renderer.render(sc, cam);
    renderer.readRenderTargetPixels(rt, 0, 0, W, H, buf);
  } finally {
    renderer.setRenderTarget(prevRT); renderer.setClearColor(prevC, prevA); rt.dispose();
  }
  let any = false;
  for (let i = 3; i < buf.length; i += 16) if (buf[i]) { any = true; break; }
  if (!any) return null;
  const big = document.createElement('canvas'); big.width = W; big.height = H;
  const bg = big.getContext('2d'), img = bg.createImageData(W, H);
  for (let y = 0; y < H; y++) img.data.set(buf.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
  bg.putImageData(img, 0, 0);
  const col = document.createElement('canvas'); col.width = ICON_W; col.height = ICON_H;
  col.getContext('2d').drawImage(big, 0, 0, ICON_W, ICON_H);
  const sil = document.createElement('canvas'); sil.width = ICON_W; sil.height = ICON_H;
  const sg = sil.getContext('2d'); sg.drawImage(col, 0, 0); sg.globalCompositeOperation = 'source-in'; sg.fillStyle = '#fff'; sg.fillRect(0, 0, ICON_W, ICON_H);
  return { img: col.toDataURL(), sil: sil.toDataURL() };
}
// запасные силуэты для того, у чего нет модели (нож, гранаты)
function drawFallbackIcon(k) {
  const c = document.createElement('canvas'); c.width = ICON_W; c.height = ICON_H;
  const g = c.getContext('2d'); g.fillStyle = '#fff';
  if (k === 'knife') {
    g.beginPath(); g.moveTo(20, 52); g.lineTo(150, 40); g.quadraticCurveTo(220, 40, 240, 52); g.quadraticCurveTo(200, 66, 150, 62); g.lineTo(20, 62); g.closePath(); g.fill();
    g.fillRect(100, 34, 10, 36);
  } else if (['he', 'flash', 'smoke', 'grenade'].includes(k) || /гран|дым|свет/i.test(wName(k))) {
    g.beginPath(); g.ellipse(128, 56, 26, 32, 0, 0, Math.PI * 2); g.fill();
    g.fillRect(116, 14, 24, 14); g.fillRect(138, 16, 34, 7);
  } else {
    g.fillRect(40, 38, 170, 16); g.fillRect(200, 42, 30, 7); g.fillRect(70, 50, 20, 34); g.fillRect(130, 50, 14, 22); g.fillRect(24, 40, 22, 26);
  }
  const url = c.toDataURL(); return { img: url, sil: url, fallback: true };
}
function gunIcon(k) {
  if (iconCache[k]) return iconCache[k];
  let r = null;
  try { if (typeof GUNS !== 'undefined' && GUNS[k] && GUNS[k].full) r = renderGunIcon(GUNS[k].full); } catch (e) { r = null; }
  return iconCache[k] = r || drawFallbackIcon(k);
}

/* ---------------- урон: кто сколько нанёс (экран смерти, помощь, MVP) ---------------- */
// Оборачиваем applyDamage (match.js) снаружи, не меняя её: считаем разницу hp+броня до и после.
let life = { dealt: new Map(), taken: new Map() }, deathInfo = null, deathShown = false, wasAlive = true;
const addLog = (m, u, d) => { const r = m.get(u) || { dmg: 0, hits: 0 }; r.dmg += d; r.hits++; m.set(u, r); };
if (typeof applyDamage === 'function') {
  const _applyDamage = applyDamage;
  applyDamage = function (victim, attacker) { // [UX] обёртка для статистики урона
    const before = victim && victim.alive ? Math.max(0, victim.hp) + (victim.armor || 0) : 0;
    const r = _applyDamage.apply(this, arguments);
    if (victim && attacker && before > 0) {
      const d = Math.round(before - Math.max(0, victim.hp) - (victim.armor || 0));
      if (d > 0) {
        if (attacker.team !== victim.team) attacker._dmg = (attacker._dmg || 0) + d;
        if (victim.alive) { const m = victim._dmgBy || (victim._dmgBy = new Map()); m.set(attacker, (m.get(attacker) || 0) + d); }
        if (attacker.isPlayer) addLog(life.dealt, victim, d);
        if (victim.isPlayer) addLog(life.taken, attacker, d);
      }
    }
    return r;
  };
}
const assistsOf = u => u.assists != null ? u.assists : (u._ast || 0);
const scoreOf = u => u.score != null ? u.score : u.kills * 2 + assistsOf(u);
bus.on('kill', (victim, attacker, wKey, head) => {
  if (victim && victim._dmgBy) {
    for (const [a, d] of victim._dmgBy) if (a !== attacker && a.team !== victim.team && d >= 40) a._ast = (a._ast || 0) + 1;
    victim._dmgBy = new Map();
  }
  if (victim && victim.isPlayer) { deathInfo = { attacker, wKey, head }; deathShown = false; }
});
bus.on('round:start', () => {
  for (const u of units) u._dmgBy = new Map();
  life = { dealt: new Map(), taken: new Map() }; deathInfo = null; hideDeath();
});
const deathEl = $('#death');
function hideDeath() { if (!deathEl.hidden) deathEl.hidden = true; deathShown = false; }
function showDeath() {
  const di = deathInfo; if (!di) return;
  const a = di.attacker, self = !a || a === player;
  const dealt = a && life.dealt.get(a), taken = a && life.taken.get(a);
  const ic = gunIcon(di.wKey);
  deathEl.innerHTML = `<div class="dh">${self ? 'Ты погиб' : 'Тебя устранил'}</div>` +
    (self ? '' : `<div class="dk"><b class="${esc(a.team)}">${esc(a.name)}</b><img src="${ic.sil}" alt=""><span>${esc(wName(di.wKey))}</span>${di.head ? '<em>в голову</em>' : ''}` +
      (a.alive ? `<small>у него ${Math.max(1, Math.ceil(a.hp))} HP</small>` : '') + '</div>' +
      `<div class="dd"><div><small>Ты нанёс</small><b>${dealt ? dealt.dmg : 0}</b><span>${dealt ? dealt.hits + ' попад.' : 'нет попаданий'}</span></div>` +
      `<div><small>Получил</small><b>${taken ? taken.dmg : 0}</b><span>${taken ? taken.hits + ' попад.' : '—'}</span></div></div>`) +
    `<div class="df" id="deathFoot"></div>`;
  deathEl.hidden = false; deathShown = true;
}

/* ---------------- основной HUD ---------------- */
function updateHUD() {
  const p = player, w = weaponOf(p), a = p.ammo[p.cur] || { mag: 0, res: 0 };
  setT('hp', String(Math.max(0, Math.ceil(p.hp)))); setT('ar', String(Math.ceil(p.armor)));
  setCls(els.hp.parentElement, 'hpLow', 'low', p.hp <= 25);
  const hpS = (Math.max(0, p.hp) / 100).toFixed(3), arS = (p.armor / 100).toFixed(3);
  if (cache.hpS !== hpS) { cache.hpS = hpS; hpBar.style.transform = `scaleX(${hpS})`; }
  if (cache.arS !== arS) { cache.arS = arS; arBar.style.transform = `scaleX(${arS})`; }
  setT('mag', String(a.mag)); setT('res', String(a.res)); setT('wname', w.name);
  if (cache.wicon !== p.cur) { cache.wicon = p.cur; wIconEl.src = gunIcon(p.cur).sil; }
  setCls(ammoEl, 'ammoEmpty', 'empty', a.mag === 0);
  setCls(ammoEl, 'ammoLow', 'low', a.mag > 0 && a.mag <= Math.ceil(w.mag * 0.25));
  setT('money', mode.rounds ? '$' + p.money : (p.alive ? '' : 'Возрождение через ' + Math.max(1, Math.ceil(p.respawnT))));
  const tLeft = state === 'freeze' ? freezeT : (state === 'live' ? roundT : 0);
  const s = Math.max(0, Math.ceil(tLeft));
  setT('timer', (state === 'freeze' && mode.rounds ? 'ЗАКУП ' : '') + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'));
  setCls(els.timer, 'timerHot', 'hot', state === 'live' && roundT < 15);
  setT('scA', String(scoreA)); setT('scB', String(scoreB));
  let ia = 0, ib = 0, la = 0, lb = 0;
  for (const u of units) {
    const el = u.team === 'A' ? pipsA.children[ia++] : pipsB.children[ib++];
    if (el && el._d !== !u.alive) { el._d = !u.alive; el.classList.toggle('dead', !u.alive); }
    if (u.alive) { if (u.team === 'A') la++; else lb++; }
  }
  setT('aliveA', String(la)); setT('aliveB', String(lb));
  const rl = p.reloading > 0;
  if (cache.rl !== rl) { cache.rl = rl; reloadBar.style.visibility = rl ? 'visible' : 'hidden'; }
  if (rl) reloadBar.firstElementChild.style.transform = `scaleX(${(1 - p.reloading / w.reload).toFixed(3)})`;
  const sc = !!(p.alive && p.scoped && w.scope);
  setCls(scopeEl, 'scope', 'on', sc);
  setCls(redEl, 'red', 'on', !!(p.alive && w.reddot && vmState.ads > 0.85));
  setCls(crossEl, 'cross', 'hide', sc || !p.alive || (vmState.ads > 0.6 && !w.pellets));
  const gap = Math.round(clamp(currentSpread(p) * innerHeight / 2 / Math.tan(camera.fov * Math.PI / 360), 3, 60));
  if (gap !== lastGap) { crossEl.style.setProperty('--gap', gap + 'px'); lastGap = gap; }
  setCls(crossEl, 'crossAuto', 'auto', !!(settings.autoFire && isTouch && fireSrc.auto));
  setCls(tbtn.scope, 'scopeLit', 'lit', !!p.scoped);
  updateTouchUI();
  updateBuyBtn();
  setCls(hudEl, 'hudDead', 'dead', !p.alive);
  // экран смерти
  if (p.alive) { if (!wasAlive) { life = { dealt: new Map(), taken: new Map() }; deathInfo = null; } if (!deathEl.hidden) hideDeath(); }
  else if (deathInfo && !deathShown && state !== 'over') showDeath();
  wasAlive = p.alive;
  if (deathShown) {
    const f = $('#deathFoot');
    if (f) {
      const mates = units.filter(u => u.alive && u.team === p.team && !u.isPlayer);
      const t = !mode.rounds ? 'Возрождение через ' + Math.max(1, Math.ceil(p.respawnT)) :
        mates.length ? 'Наблюдение: ' + mates[specIndex % mates.length].name + (mates.length > 1 ? ' · коснись, чтобы сменить' : '') : 'Ждём конца раунда';
      if (f.textContent !== t) f.textContent = t;
    }
  }
}

/* ---------------- радар ---------------- */
const radar = $('#radar'), rg = radar.getContext('2d');
const RAD_PX = radar.width, RAD_R = 30; // размер холста и радиус обзора, м
let radarBase = null, radarGrid = null, radarT = 0;
function buildRadarBase() {
  radarGrid = grid;
  radarBase = document.createElement('canvas'); radarBase.width = MW * 8; radarBase.height = MH * 8;
  const g = radarBase.getContext('2d');
  g.fillStyle = 'rgba(150,170,168,.13)'; g.fillRect(0, 0, MW * 8, MH * 8);
  grid.forEach((row, z) => row.forEach((ch, x) => {
    if (ch === '.') return;
    g.fillStyle = ch === '#' ? 'rgba(206,220,216,.62)' : ch === 'C' ? 'rgba(206,220,216,.38)' : 'rgba(206,220,216,.24)';
    g.fillRect(x * 8, z * 8, 8.5, 8.5);
  }));
}
function drawRadar(dt) {
  radarT -= dt || 0.016; if (radarT > 0) return; radarT = 1 / 30;
  if (radarGrid !== grid || !radarBase) buildRadarBase();
  const W = RAD_PX, c = W / 2, k = c / RAD_R; // px на метр
  const cx = player.alive ? player.pos.x : camera.position.x, cz = player.alive ? player.pos.z : camera.position.z;
  const rot = settings.radarRotate;
  const yaw = player.alive ? player.yaw : (_v.set(0, 0, -1).applyQuaternion(camera.quaternion), Math.atan2(-_v.x, -_v.z));
  rg.setTransform(1, 0, 0, 1, 0, 0);
  rg.clearRect(0, 0, W, W);
  rg.save();
  rg.beginPath(); rg.arc(c, c, c - 1, 0, Math.PI * 2); rg.clip();
  rg.fillStyle = 'rgba(8,13,15,.72)'; rg.fillRect(0, 0, W, W);
  rg.translate(c, c); if (rot) rg.rotate(yaw); rg.scale(k, k); rg.translate(-cx, -cz);
  rg.drawImage(radarBase, 0, 0, MW * CELL, MH * CELL);
  const dotR = 3.6 / k;
  for (const u of units) {
    if (!u.alive || u.isPlayer) continue;
    if (u.team !== player.team && u.spottedT <= 0) continue;
    rg.fillStyle = u.team === player.team ? '#6cc0d3' : '#ff6a3a';
    rg.beginPath(); rg.arc(u.pos.x, u.pos.z, dotR, 0, Math.PI * 2); rg.fill();
    if (u.hasCharge) { rg.strokeStyle = '#f2cb4c'; rg.lineWidth = 1.5 / k; rg.stroke(); }
  }
  rg.restore();
  // игрок в центре + конус обзора
  rg.save(); rg.translate(c, c); if (!rot) rg.rotate(-yaw);
  const fovH = Math.atan(Math.tan(camera.fov * Math.PI / 360) * camera.aspect);
  const cone = rg.createRadialGradient(0, 0, 0, 0, 0, c * 0.7);
  cone.addColorStop(0, 'rgba(242,203,76,.28)'); cone.addColorStop(1, 'rgba(242,203,76,0)');
  rg.fillStyle = cone; rg.beginPath(); rg.moveTo(0, 0); rg.arc(0, 0, c * 0.7, -Math.PI / 2 - fovH, -Math.PI / 2 + fovH); rg.closePath(); rg.fill();
  if (player.alive) {
    rg.fillStyle = '#f2cb4c'; rg.beginPath(); rg.moveTo(0, -9); rg.lineTo(6.5, 6.5); rg.lineTo(0, 3.5); rg.lineTo(-6.5, 6.5); rg.closePath(); rg.fill();
  }
  rg.restore();
  rg.strokeStyle = 'rgba(160,190,196,.35)'; rg.lineWidth = 2; rg.beginPath(); rg.arc(c, c, c - 1.5, 0, Math.PI * 2); rg.stroke();
  // сторона света «С» по краю
  const na = rot ? yaw : 0;
  rg.fillStyle = 'rgba(232,238,236,.75)'; rg.font = '700 15px Rubik, sans-serif'; rg.textAlign = 'center'; rg.textBaseline = 'middle';
  rg.fillText('С', c + Math.sin(na) * (c - 13), c - Math.cos(na) * (c - 13));
}

/* ---------------- сообщения, лента, попадания ---------------- */
const msgEl = $('#msg'); let msgT = 0;
function showMsg(big, small, team) {
  msgEl.innerHTML = '';
  if (!big) { msgEl.style.opacity = 0; return; }
  const b = document.createElement('div'); b.className = 'big' + (team ? ' ' + team : ''); b.textContent = big; msgEl.appendChild(b);
  if (small) { const s = document.createElement('div'); s.className = 'small'; s.textContent = small; msgEl.appendChild(s); }
  msgEl.style.opacity = 1; msgT = 2.6;
}
const HEAD_SVG = '<svg viewBox="0 0 24 24" class="hs" aria-label="в голову"><circle cx="12" cy="10" r="6.5"/><path d="M8.5 16.5v3.5h7v-3.5"/><circle cx="9.5" cy="10" r="1.4" fill="currentColor"/><circle cx="14.5" cy="10" r="1.4" fill="currentColor"/></svg>';
function feed(att, vic, wKey, head) {
  const d = document.createElement('div');
  if (att.isPlayer || vic.isPlayer) d.className = att.isPlayer ? 'me' : 'meV';
  const ic = gunIcon(wKey);
  const self = att === vic;
  d.innerHTML = (self ? '' : `<span class="${esc(att.team)}">${esc(att.name)}</span>`) +
    `<img src="${ic.sil}" alt="${esc(wName(wKey))}" title="${esc(wName(wKey))}">` + (head ? HEAD_SVG : '') +
    `<span class="${esc(vic.team)}">${esc(vic.name)}</span>`;
  const f = $('#feed'); f.prepend(d); while (f.children.length > 4) f.lastChild.remove();
  setTimeout(() => d.remove(), 6000);
}
const hitEl = $('#hitmark'); let hitTO = 0;
function hitMarker(head, killed) {
  hitEl.className = 'on' + (killed ? ' kill' : head ? ' head' : '');
  clearTimeout(hitTO); hitTO = setTimeout(() => hitEl.className = '', killed ? 220 : 110);
}
const vig = $('#vignette'); let vigA = 0; const dirs = [...document.querySelectorAll('#dmgdirs div')]; let dirI = 0;
function hurtFx(att) {
  vigA = Math.min(1, vigA + 0.55); sfxHurt();
  if (!att || !att.pos) return;
  const rel = angDiff(yawTo(player.pos.x, player.pos.z, att.pos.x, att.pos.z), player.yaw);
  const d = dirs[dirI++ % dirs.length]; d.style.transform = `rotate(${-rel}rad)`; d.style.opacity = 1; d.dataset.t = '1';
}

/* ---------------- таблица счёта ---------------- */
function renderTables(el) {
  el.innerHTML = '';
  for (const team of ['A', 'B']) {
    const box = document.createElement('div'); box.className = team;
    const list = units.filter(u => u.team === team).sort((a, b) => scoreOf(b) - scoreOf(a) || b.kills - a.kills || a.deaths - b.deaths);
    const k = list.reduce((s, u) => s + u.kills, 0);
    const money = mode.rounds && team === player.team;
    let h = `<h3><span>${team === 'A' ? 'Сталь' : 'Ржавчина'}</span><small>${team === 'A' ? scoreA : scoreB} · убийств ${k}</small></h3>` +
      `<table><thead><tr><th>Боец</th><th class="n" title="Убийства">Уб</th><th class="n" title="Помощь">Пом</th><th class="n" title="Смерти">См</th><th class="n" title="Очки">Очки</th>${money ? '<th class="n">$</th>' : ''}</tr></thead><tbody>`;
    for (const u of list) {
      h += `<tr class="${team}${u.isPlayer ? ' me' : ''}${u.alive ? '' : ' dead'}"><td>${esc(u.name)}${u.hasCharge ? ' <i class="chg" title="Заряд"></i>' : ''}</td><td class="n">${u.kills}</td><td class="n">${assistsOf(u)}</td><td class="n">${u.deaths}</td><td class="n">${scoreOf(u)}</td>${money ? `<td class="n">${u.money}</td>` : ''}</tr>`;
    }
    box.innerHTML = h + '</tbody></table>';
    el.appendChild(box);
  }
}
const boardEl = $('#board');
function openBoard() {
  $('#boardTitle').textContent = mode.name;
  $('#boardSub').textContent = mode.rounds ? `Раунд ${roundNo} · до ${mode.win} побед` : `До ${mode.killLimit} убийств`;
  renderTables($('#tables')); boardEl.hidden = false;
}
function closeBoard() { boardEl.hidden = true; }
$('#scoreBox').addEventListener('click', () => boardEl.hidden ? openBoard() : closeBoard());
$('#boardClose').addEventListener('click', () => { closeBoard(); requestLock(); });
boardEl.addEventListener('pointerdown', e => { if (e.target === boardEl) closeBoard(); });
