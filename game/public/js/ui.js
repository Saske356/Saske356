import * as W from '/shared/world.js';

const $ = (id) => document.getElementById(id);

export function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

export const money = (n) => '$' + Math.round(n).toLocaleString('ru-RU');

// ---------- Чат ----------
export function addChat(text, color = '#fff') {
  const log = $('chatlog');
  const d = el('div', { class: 'msg' }, text);
  d.style.color = color;
  log.append(d);
  while (log.children.length > 60) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}
export function openChat() {
  const i = $('chatinput');
  i.hidden = false; i.value = ''; i.focus();
}
export function closeChat() {
  const i = $('chatinput');
  i.blur(); i.hidden = true;
}

// ---------- Уведомления ----------
export function toast(text, kind = 'info') {
  const t = el('div', { class: 'toast ' + kind }, text);
  $('toasts').append(t);
  setTimeout(() => t.classList.add('out'), 4200);
  setTimeout(() => t.remove(), 4700);
}

// ---------- HUD ----------
export function setStats(profile, time, online) {
  $('clock').textContent = W.formatTime(time);
  $('money').textContent = money(profile.money);
  $('lvl').textContent = `Ур. ${profile.level}`;
  $('online').textContent = `Онлайн: ${online}`;
}
export function hint(text) {
  const h = $('hint');
  if (!text) { h.hidden = true; return; }
  h.hidden = false;
  if (h.textContent !== text) h.textContent = text;
}
export function speedo(kmh, name) {
  const s = $('speedo');
  if (kmh == null) { s.hidden = true; return; }
  s.hidden = false;
  $('spd').textContent = Math.round(kmh);
  $('carname').textContent = name;
}
export function jobPanel(job) {
  const p = $('jobpanel');
  if (!job) { p.hidden = true; return; }
  p.hidden = false;
  p.replaceChildren(
    el('div', { class: 'jt' }, job.type === 'bus' ? 'Водитель автобуса' : 'Курьер'),
    el('div', { class: 'jl' }, job.label),
    el('div', { class: 'ji' }, job.info || ''),
  );
}
export function jobDistance(d) {
  const p = $('jobpanel'), last = p.querySelector('.jd') || p.appendChild(el('div', { class: 'jd' }));
  last.textContent = d == null ? '' : `До цели: ${Math.round(d)} м`;
}

// ---------- Модальные окна ----------
let modalOpen = false;
export function openModal(title, body) {
  $('mtitle').textContent = title;
  $('mbody').replaceChildren(...[body].flat().filter(Boolean));
  $('modal').hidden = false;
  modalOpen = true;
}
export function closeModal() { $('modal').hidden = true; modalOpen = false; }
export const isModalOpen = () => modalOpen;
$('mclose').addEventListener('click', closeModal);
$('modal').addEventListener('pointerdown', (e) => { if (e.target.id === 'modal') closeModal(); });

export const button = (text, onclick, cls = '') => el('button', { class: 'btn ' + cls, onclick }, text);

// ---------- Миникарта ----------
let mapImg = null;
const MM = 200, SCALE = 0.75;
export function initMinimap(city) {
  const c = document.createElement('canvas');
  c.width = c.height = W.SIZE;
  const g = c.getContext('2d');
  g.fillStyle = '#5b6068'; g.fillRect(0, 0, W.SIZE, W.SIZE);
  g.fillStyle = '#262a31';
  for (let bz = 0; bz < W.GRID; bz++) for (let bx = 0; bx < W.GRID; bx++) {
    const b = W.blockRect(bx, bz); g.fillRect(b.x0, b.z0, W.BLOCK, W.BLOCK);
  }
  g.fillStyle = '#2f5a36';
  for (const b of city.parks) g.fillRect(b.x0 + 3, b.z0 + 3, W.BLOCK - 6, W.BLOCK - 6);
  g.fillStyle = '#414a5a';
  for (const b of city.buildings) g.fillRect(b.x0, b.z0, b.x1 - b.x0, b.z1 - b.z0);
  mapImg = c;
}

export function drawMinimap(s) {
  const cv = $('minimap'), ctx = cv.getContext('2d');
  const th = -Math.PI / 2 - Math.atan2(Math.cos(s.yaw), Math.sin(s.yaw));
  const cs = Math.cos(th), sn = Math.sin(th);
  const toScreen = (px, pz) => {
    const dx = (px - s.x) * SCALE, dz = (pz - s.z) * SCALE;
    return [MM / 2 + dx * cs - dz * sn, MM / 2 + dx * sn + dz * cs];
  };
  ctx.save();
  ctx.clearRect(0, 0, MM, MM);
  ctx.beginPath(); ctx.arc(MM / 2, MM / 2, MM / 2 - 2, 0, Math.PI * 2); ctx.clip();
  ctx.fillStyle = '#2d4a26'; ctx.fillRect(0, 0, MM, MM);
  ctx.save();
  ctx.translate(MM / 2, MM / 2); ctx.rotate(th); ctx.scale(SCALE, SCALE); ctx.translate(-s.x, -s.z);
  ctx.drawImage(mapImg, 0, 0);
  ctx.restore();

  const dot = (px, pz, color, r = 4, clamp = false) => {
    let [x, y] = toScreen(px, pz);
    const dx = x - MM / 2, dy = y - MM / 2, l = Math.hypot(dx, dy), lim = MM / 2 - 9;
    if (l > lim) { if (!clamp) return; x = MM / 2 + (dx / l) * lim; y = MM / 2 + (dy / l) * lim; }
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.fill();
    ctx.lineWidth = 1.5; ctx.strokeStyle = '#000'; ctx.stroke();
  };
  for (const p of Object.values(W.PLACES)) if (!p.hidden) dot(p.pos[0], p.pos[1], p.color, 4.5, true);
  for (const o of s.others) dot(o.x, o.z, '#e8eef5', 3);
  if (s.waypoint) dot(s.waypoint[0], s.waypoint[1], '#4fa3ff', 6, true);
  if (s.target) dot(s.target[0], s.target[1], '#ff4d4d', 6, true);

  // стрелка игрока
  const a = Math.atan2(Math.cos(s.ry), Math.sin(s.ry)) + th;
  ctx.translate(MM / 2, MM / 2); ctx.rotate(a);
  ctx.beginPath(); ctx.moveTo(9, 0); ctx.lineTo(-6, -6); ctx.lineTo(-3, 0); ctx.lineTo(-6, 6); ctx.closePath();
  ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.strokeStyle = '#000'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.restore();
  ctx.beginPath(); ctx.arc(MM / 2, MM / 2, MM / 2 - 2, 0, Math.PI * 2);
  ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.stroke();
}
