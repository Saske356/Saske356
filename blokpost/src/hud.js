'use strict';
/* ---------------- HUD ---------------- */
const els = {}; ['hp', 'ar', 'mag', 'res', 'money', 'wname', 'timer', 'scA', 'scB'].forEach(id => els[id] = document.getElementById(id));
const cache = {};
const setT = (id, v) => { if (cache[id] !== v) { cache[id] = v; els[id].textContent = v; } };
const hpBar = $('#hpBar i'), arBar = $('#arBar i'), reloadBar = $('#reloadBar'), crossEl = $('#cross'), scopeEl = $('#scope'), ammoEl = $('#ammo'), redEl = $('#reddot');
let lastGap = -1;
function updateHUD() {
  const p = player, w = weaponOf(p), a = p.ammo[p.cur] || { mag: 0, res: 0 };
  setT('hp', String(Math.max(0, Math.ceil(p.hp)))); setT('ar', String(Math.ceil(p.armor)));
  els.hp.classList.toggle('low', p.hp <= 25);
  hpBar.style.transform = `scaleX(${Math.max(0, p.hp) / 100})`; arBar.style.transform = `scaleX(${p.armor / 100})`;
  setT('mag', String(a.mag)); setT('res', String(a.res)); setT('wname', w.cls + ' · ' + w.name);
  ammoEl.classList.toggle('empty', a.mag === 0);
  setT('money', mode.rounds ? '$' + p.money : (p.alive ? '' : 'Возрождение через ' + Math.max(1, Math.ceil(p.respawnT))));
  const tLeft = state === 'freeze' ? freezeT : (state === 'live' ? roundT : 0);
  const s = Math.max(0, Math.ceil(tLeft));
  setT('timer', (state === 'freeze' && mode.rounds ? 'ЗАКУП ' : '') + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'));
  els.timer.classList.toggle('hot', state === 'live' && roundT < 15);
  setT('scA', String(scoreA)); setT('scB', String(scoreB));
  let ia = 0, ib = 0;
  for (const u of units) { const el = u.team === 'A' ? pipsA.children[ia++] : pipsB.children[ib++]; if (el) el.classList.toggle('dead', !u.alive); }
  reloadBar.style.visibility = p.reloading > 0 ? 'visible' : 'hidden';
  if (p.reloading > 0) reloadBar.firstElementChild.style.transform = `scaleX(${1 - p.reloading / w.reload})`;
  const sc = p.alive && p.scoped && w.scope;
  scopeEl.classList.toggle('on', sc);
  redEl.classList.toggle('on', !!(p.alive && w.reddot && vmState.ads > 0.85));
  crossEl.classList.toggle('hide', sc || !p.alive || (vmState.ads > 0.6 && !w.pellets));
  const gap = Math.round(clamp(currentSpread(p) * innerHeight / 2 / Math.tan(camera.fov * Math.PI / 360), 3, 60));
  if (gap !== lastGap) { crossEl.style.setProperty('--gap', gap + 'px'); lastGap = gap; }
  $('#tScope').classList.toggle('on', p.scoped);
  updateBuyBtn();
}
const radar = $('#radar'), rg = radar.getContext('2d');
const radarBase = document.createElement('canvas'); radarBase.width = 300; radarBase.height = 188;
(function () {
  const g = radarBase.getContext('2d'), sx = 300 / MW, sz = 188 / MH;
  grid.forEach((row, z) => row.forEach((ch, x) => {
    if (ch === '.') return;
    g.fillStyle = ch === '#' ? 'rgba(200,214,212,.55)' : ch === 'C' ? 'rgba(200,214,212,.32)' : 'rgba(200,214,212,.18)';
    g.fillRect(x * sx, z * sz, sx + 0.5, sz + 0.5);
  }));
})();
function drawRadar() {
  const sx = 300 / (MW * CELL), sz = 188 / (MH * CELL);
  rg.clearRect(0, 0, 300, 188); rg.drawImage(radarBase, 0, 0);
  for (const u of units) {
    if (!u.alive) continue;
    if (u.team !== player.team && u.spottedT <= 0) continue;
    const x = u.pos.x * sx, y = u.pos.z * sz;
    rg.fillStyle = u.isPlayer ? '#f2cb4c' : u.team === 'A' ? '#6cc0d3' : '#ea7440';
    if (u.isPlayer) {
      rg.save(); rg.translate(x, y); rg.rotate(-u.yaw);
      rg.beginPath(); rg.moveTo(0, -9); rg.lineTo(6, 6); rg.lineTo(0, 3); rg.lineTo(-6, 6); rg.closePath(); rg.fill(); rg.restore();
    } else { rg.beginPath(); rg.arc(x, y, 5, 0, Math.PI * 2); rg.fill(); }
  }
}
const msgEl = $('#msg'); let msgT = 0;
function showMsg(big, small, team) {
  msgEl.innerHTML = '';
  if (!big) { msgEl.style.opacity = 0; return; }
  const b = document.createElement('div'); b.className = 'big' + (team ? ' ' + team : ''); b.textContent = big; msgEl.appendChild(b);
  if (small) { const s = document.createElement('div'); s.className = 'small'; s.textContent = small; msgEl.appendChild(s); }
  msgEl.style.opacity = 1; msgT = 2.6;
}
function feed(att, vic, wKey, head) {
  const d = document.createElement('div');
  if (att.isPlayer || vic.isPlayer) d.className = 'me';
  const a = document.createElement('span'); a.className = att.team; a.textContent = att.name;
  const w = document.createElement('span'); w.className = 'w'; w.textContent = WEAPONS[wKey].name;
  const v = document.createElement('span'); v.className = vic.team; v.textContent = vic.name;
  d.append(a, w);
  if (head) { const h = document.createElement('span'); h.className = 'hs'; h.textContent = 'В ГОЛОВУ'; d.append(h); }
  d.append(v);
  const f = $('#feed'); f.prepend(d); while (f.children.length > 5) f.lastChild.remove();
  setTimeout(() => d.remove(), 6000);
}
const hitEl = $('#hitmark'); let hitTO = 0;
function hitMarker(head, killed) {
  hitEl.className = 'on' + (killed ? ' kill' : head ? ' head' : '');
  clearTimeout(hitTO); hitTO = setTimeout(() => hitEl.className = '', 110);
}
const vig = $('#vignette'); let vigA = 0; const dirs = [...document.querySelectorAll('#dmgdirs div')]; let dirI = 0;
function hurtFx(att) {
  vigA = Math.min(1, vigA + 0.55); sfxHurt();
  const rel = angDiff(yawTo(player.pos.x, player.pos.z, att.pos.x, att.pos.z), player.yaw);
  const d = dirs[dirI++ % dirs.length]; d.style.transform = `rotate(${-rel}rad)`; d.style.opacity = 1; d.dataset.t = '1';
}

/* ---------------- таблица счёта ---------------- */
function renderTables(el) {
  el.innerHTML = '';
  for (const team of ['A', 'B']) {
    const box = document.createElement('div'); box.className = team;
    const h = document.createElement('h3'); h.textContent = team === 'A' ? 'Сталь' : 'Ржавчина'; box.appendChild(h);
    const t = document.createElement('table');
    t.innerHTML = '<thead><tr><th>Боец</th><th class="n">Убийства</th><th class="n">Смерти</th>' + (mode.rounds ? '<th class="n">$</th>' : '') + '</tr></thead>';
    const tb = document.createElement('tbody');
    units.filter(u => u.team === team).sort((a, b) => b.kills - a.kills || a.deaths - b.deaths).forEach(u => {
      const tr = document.createElement('tr'); tr.className = team + (u.isPlayer ? ' me' : '') + (u.alive ? '' : ' dead');
      const cells = [u.name, u.kills, u.deaths]; if (mode.rounds) cells.push(team === player.team ? u.money : '—');
      cells.forEach((c, i) => { const td = document.createElement('td'); if (i) td.className = 'n'; td.textContent = c; tr.appendChild(td); });
      tb.appendChild(tr);
    });
    t.appendChild(tb); box.appendChild(t); el.appendChild(box);
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
