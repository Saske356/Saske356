'use strict';
/* ---------------- инвентарь, жетоны и кейсы [скины] ----------------
   Только игровая валюта «жетоны»: начисляются за убийства, раунды и матчи. Никаких реальных денег.
   Глобальные имена: INV, CASES, openInventory(tab), closeInventory(), invGunSkin(k), invCharSkin(team), invEarn(n, why)
*/
const INV_KEY = 'blokpost-inv';
const INV = { v: 1, tokens: 600, items: [], uid: 1, eqGun: {}, eqChar: { A: null, B: null }, opened: 0, earned: 0 };
try {
  const s = JSON.parse(localStorage.getItem(INV_KEY) || 'null');
  if (s && s.v === 1) Object.assign(INV, s);
} catch (e) {}
INV.items = (Array.isArray(INV.items) ? INV.items : []).filter(it => it && (it.t === 'g' ? GUN_SKINS[it.id] : it.t === 'c' && CHAR_SKINS[it.id]));
INV.eqGun = INV.eqGun || {}; INV.eqChar = Object.assign({ A: null, B: null }, INV.eqChar);
if (!(INV.tokens >= 0)) INV.tokens = 0;
function invSave() { try { localStorage.setItem(INV_KEY, JSON.stringify(INV)); } catch (e) {} }
const invItem = uid => uid == null ? null : INV.items.find(i => i.uid === uid) || null;
function invGunSkin(k) { const it = invItem(INV.eqGun[k]); return it && it.t === 'g' ? { skin: it.id, wear: it.w || 0 } : null; }
function invCharSkin(team) { const it = invItem(INV.eqChar[team]); return it && it.t === 'c' ? it.id : null; }
const invDef = it => it.t === 'g' ? GUN_SKINS[it.id] : CHAR_SKINS[it.id];
const INV_SCRAP = { common: 15, uncommon: 40, rare: 90, epic: 200, legendary: 450 };
const INV_GUNS = () => Object.keys(typeof GUNS !== 'undefined' ? GUNS : WEAPONS).filter(k => WEAPONS[k]);

/* ---------------- кейсы ---------------- */
const CASES = {
  field:    { name: 'Полевой кейс', desc: 'Скины оружия всех редкостей', price: 200, kinds: ['g'], odds: { common: 52, uncommon: 27, rare: 14, epic: 5.5, legendary: 1.5 }, cols: ['#3f4c33', '#f2cb4c', '#1b211a'] },
  squad:    { name: 'Кейс отряда', desc: 'Формы бойцов обеих команд', price: 250, kinds: ['c'], odds: { common: 52, uncommon: 27, rare: 14, epic: 5.5, legendary: 1.5 }, cols: ['#2f3f4a', '#6cc0d3', '#141c21'] },
  midnight: { name: 'Кейс «Полночь»', desc: 'Только редкие и выше: оружие и бойцы', price: 450, kinds: ['g', 'c'], odds: { common: 0, uncommon: 0, rare: 70, epic: 23, legendary: 7 }, cols: ['#1b1733', '#c26bff', '#0d0b1a'] },
};
function casePool(c) {
  const out = [];
  if (c.kinds.includes('g')) for (const id in GUN_SKINS) out.push({ t: 'g', id });
  if (c.kinds.includes('c')) for (const id in CHAR_SKINS) out.push({ t: 'c', id });
  return out;
}
function caseRollEntry(c) {
  const pool = casePool(c), have = {};
  for (const e of pool) have[invDef(e).rarity] = true;
  const odds = {}; for (const r of SKIN_RARITY_ORDER) odds[r] = have[r] ? (c.odds[r] || 0) : 0;
  const r = skPickRarity(odds), list = pool.filter(e => invDef(e).rarity === r);
  return pick(list.length ? list : pool);
}
function rollWear() { return Math.round(Math.pow(Math.random(), 1.35) * 1000) / 1000; }
function openCase(caseId) {
  const c = CASES[caseId]; if (!c || INV.tokens < c.price) return null;
  INV.tokens -= c.price; INV.opened++;
  const e = caseRollEntry(c);
  const it = { uid: INV.uid++, t: e.t, id: e.id, w: e.t === 'g' ? rollWear() : 0, n: 1, at: Date.now() };
  INV.items.push(it); invSave();
  return it;
}

/* ---------------- начисление жетонов ---------------- */
const INV_PAY = { kill: 4, head: 2, roundWin: 12, roundLoss: 4, matchWin: 40, matchLoss: 15, matchDraw: 25 };
let invMatchEarn = 0;
const invMyTeam = () => (typeof player !== 'undefined' && player && player.team) || 'A';
const invInMatch = () => typeof state !== 'undefined' && state !== 'menu' && state !== 'over';
function invEarn(n, why) {
  if (!(n > 0)) return;
  INV.tokens += n; INV.earned += n; invMatchEarn += n; invSave();
  invToast('+' + n, why); invSyncTokens();
}
bus.on('kill', (victim, attacker, wKey, head) => {
  if (!invInMatch() || !attacker || !attacker.isPlayer || !victim || victim.team === attacker.team) return;
  invEarn(INV_PAY.kill + (head ? INV_PAY.head : 0), head ? 'в голову' : 'за устранение');
});
bus.on('round:end', winner => {
  if (typeof state !== 'undefined' && state === 'menu') return;
  const win = winner === invMyTeam();
  invEarn(win ? INV_PAY.roundWin : INV_PAY.roundLoss, win ? 'раунд выигран' : 'за раунд');
});
// конца матча нет в шине — следим за состоянием (match.js: state === 'over')
let invLastState = null;
setInterval(() => {
  if (typeof state === 'undefined') return;
  const s = state;
  if (s === invLastState) return;
  const prev = invLastState; invLastState = s;
  if ((prev === 'menu' || prev === 'over' || prev === null) && (s === 'freeze' || s === 'live')) invMatchEarn = 0;
  if (s === 'over' && prev !== null && prev !== 'menu') {
    const a = typeof scoreA !== 'undefined' ? scoreA : 0, b = typeof scoreB !== 'undefined' ? scoreB : 0;
    const my = invMyTeam() === 'A' ? a : b, their = invMyTeam() === 'A' ? b : a;
    invEarn(my > their ? INV_PAY.matchWin : my < their ? INV_PAY.matchLoss : INV_PAY.matchDraw, 'за матч');
    invOverLine();
  }
}, 300);
function invToast(text, why) {
  const hud = document.getElementById('hud'); if (!hud || !invInMatch()) return;
  let el = document.getElementById('invToast');
  if (!el) { el = document.createElement('div'); el.id = 'invToast'; hud.appendChild(el); }
  el.innerHTML = '<i class="tok"></i><b></b><span></span>';
  el.children[1].textContent = text; el.children[2].textContent = why || '';
  el.classList.remove('on'); void el.offsetWidth; el.classList.add('on');
}
function invOverLine() {
  const card = document.querySelector('#over .card'); if (!card) return;
  let el = document.getElementById('invEarn');
  if (!el) {
    el = document.createElement('div'); el.id = 'invEarn';
    el.innerHTML = '<i class="tok"></i><span></span><button class="ghost" type="button">Открыть кейс</button>';
    const row = card.querySelector('.row:last-child'); card.insertBefore(el, row || null);
    el.querySelector('button').addEventListener('click', () => openInventory('cases'));
  }
  el.children[1].innerHTML = '';
  const b = document.createElement('b'); b.textContent = '+' + invMatchEarn + ' жетонов';
  const s = document.createElement('small'); s.textContent = ' за матч · всего ' + INV.tokens;
  el.children[1].append(b, s);
}

/* ---------------- стили ---------------- */
injectCSS('skins', `
.tok { display: inline-block; width: 14px; height: 14px; border-radius: 50%; flex: none; vertical-align: -2px;
  background: radial-gradient(circle at 50% 50%, #17170f 0 28%, transparent 30%), conic-gradient(from 20deg, #f2cb4c, #fff0a8, #c99a1c, #f2cb4c, #b8860b, #f2cb4c);
  box-shadow: 0 0 0 1px rgba(0,0,0,.5), 0 0 8px rgba(242,203,76,.35); }
#invToast { position: absolute; top: calc(58px + var(--st)); left: 50%; transform: translateX(-50%); display: flex; gap: 6px; align-items: center;
  background: var(--panel); border: 1px solid rgba(242,203,76,.4); border-radius: 999px; padding: 4px 12px 4px 8px; font-size: 12px; opacity: 0; white-space: nowrap; }
#invToast b { font-family: var(--f-num); color: var(--signal); } #invToast span { color: var(--dim); }
#invToast.on { animation: ivToast 1.8s ease-out; }
@keyframes ivToast { 0% { opacity: 0; transform: translate(-50%, 6px); } 12% { opacity: 1; transform: translate(-50%, 0); } 75% { opacity: 1; } 100% { opacity: 0; } }
#invEarn { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px; border-radius: 8px; background: rgba(242,203,76,.08); border: 1px solid rgba(242,203,76,.3); }
#invEarn b { font-family: var(--f-num); color: var(--signal); font-size: 15px; } #invEarn small { color: var(--dim); }
#invEarn button { margin-left: auto; padding: 7px 12px; font-size: 13px; }
#invMenuBtn { display: inline-flex; align-items: center; gap: 8px; }
#invMenuBtn .tc { font-family: var(--f-num); color: var(--signal); font-size: 13px; }

#inv { z-index: 12; overflow: hidden; background: radial-gradient(120% 90% at 22% 28%, #18232a 0%, #0c1114 62%, #080b0d 100%);
  padding-block: calc(10px + var(--st)) calc(10px + var(--sb)); }
#inv > .iv { width: 100%; max-width: 1180px; height: 100%; max-height: 720px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.ivh { display: flex; align-items: center; gap: 12px; flex: none; }
.ivt { display: flex; flex-direction: column; line-height: 1; gap: 3px; }
.ivt small { font-size: 10px; letter-spacing: .26em; text-transform: uppercase; color: var(--signal); }
.ivt b { font: 400 22px var(--f-display); letter-spacing: .02em; }
.ivtabs button { padding: 8px 14px; }
.ivtok { margin-left: auto; display: flex; align-items: center; gap: 7px; padding: 6px 12px; border-radius: 999px; background: rgba(242,203,76,.1);
  border: 1px solid rgba(242,203,76,.35); font: 700 15px var(--f-num); color: var(--signal); font-variant-numeric: tabular-nums; }
.ivtok small { font: 500 10px var(--f-body); letter-spacing: .14em; text-transform: uppercase; color: var(--dim); }
#inv .ivx { position: static; flex: none; font-size: 20px; }
.ivb { flex: 1; min-height: 0; display: flex; gap: 10px; }
.ivp { flex: 0 0 min(44%, 500px); position: relative; border-radius: 12px; border: 1px solid var(--panel-line); overflow: hidden; min-height: 0;
  background: radial-gradient(70% 55% at 50% 40%, rgba(108,192,211,.13), transparent 70%),
    repeating-linear-gradient(90deg, rgba(255,255,255,.025) 0 1px, transparent 1px 28px),
    linear-gradient(180deg, #141c20, #0b1013 70%, #0e1316); }
.ivp::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--rc, var(--panel-line)); opacity: .85; }
.ivcv { position: absolute; inset: 0; touch-action: none; cursor: grab; }
.ivcv:active { cursor: grabbing; }
.ivcv canvas { width: 100%; height: 100%; display: block; }
.ivhint { position: absolute; top: 12px; left: 12px; font-size: 10px; letter-spacing: .16em; text-transform: uppercase; color: var(--dim); pointer-events: none;
  display: flex; gap: 6px; align-items: center; }
.ivhint::before { content: ""; width: 16px; height: 10px; border: 1.5px solid currentColor; border-radius: 50%; border-left-color: transparent; }
.ivinfo { position: absolute; left: 0; right: 0; bottom: 0; padding: 34px 14px 12px; display: flex; flex-direction: column; gap: 5px; pointer-events: none;
  background: linear-gradient(to top, rgba(8,12,14,.94) 45%, rgba(8,12,14,0)); }
.ivinfo button { pointer-events: auto; }
.ivrar { font-size: 10px; letter-spacing: .2em; text-transform: uppercase; color: var(--rc, var(--dim)); font-weight: 700; display: flex; gap: 8px; align-items: center; }
.ivrar::before { content: ""; width: 8px; height: 8px; transform: rotate(45deg); background: var(--rc, var(--dim)); box-shadow: 0 0 8px var(--rc, transparent); }
.ivname { font: 400 21px var(--f-display); line-height: 1.05; text-wrap: balance; }
.ivsub { font-size: 12px; color: var(--dim); min-height: 1em; }
.ivwear { position: relative; height: 4px; border-radius: 2px; max-width: 240px; background: linear-gradient(90deg, #6fc27a, #c6d65a 25%, #f2cb4c 45%, #ea7440 70%, #ff4a3d); opacity: .9; }
.ivwear i { position: absolute; top: -3px; width: 3px; height: 10px; margin-left: -1.5px; border-radius: 1px; background: #fff; box-shadow: 0 0 0 1px rgba(0,0,0,.6); }
.ivact { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.ivact .go { font-size: 15px; padding: 9px 16px; }
.ivact .ghost { font-size: 13px; padding: 8px 12px; background: rgba(13,19,22,.6); }
.ivact button[disabled] { opacity: .45; cursor: not-allowed; }
.ivodds { display: flex; height: 6px; border-radius: 3px; overflow: hidden; max-width: 320px; }
.ivodds i { display: block; height: 100%; }
.ivoddl { display: flex; flex-wrap: wrap; gap: 2px 10px; font-size: 11px; color: var(--dim); font-family: var(--f-num); }
.ivoddl span { display: inline-flex; gap: 4px; align-items: center; }
.ivoddl span::before { content: ""; width: 7px; height: 7px; border-radius: 2px; background: var(--rc); }
.ivl { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.ivf { display: flex; gap: 6px; overflow-x: auto; flex: none; align-items: center; scrollbar-width: none; touch-action: pan-x; padding-bottom: 1px; }
.ivf::-webkit-scrollbar { display: none; }
.ivchip { flex: none; background: rgba(255,255,255,.04); color: var(--text); border: 1px solid var(--panel-line); border-radius: 999px; padding: 7px 13px;
  font: 500 13px var(--f-body); cursor: pointer; white-space: nowrap; display: inline-flex; gap: 6px; align-items: center; }
.ivchip small { font-family: var(--f-num); color: var(--signal); font-size: 11px; }
.ivchip[aria-pressed="true"] { background: var(--signal); color: #17170f; border-color: var(--signal); }
.ivchip[aria-pressed="true"] small { color: #17170f; }
.ivchip.A[aria-pressed="true"] { background: var(--steel); border-color: var(--steel); }
.ivchip.B[aria-pressed="true"] { background: var(--rust); border-color: var(--rust); }
.ivcount { margin-left: auto; flex: none; font: 500 11px var(--f-num); color: var(--dim); padding-left: 8px; white-space: nowrap; }
.ivg { flex: 1; min-height: 0; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 8px; align-content: start;
  touch-action: pan-y; overscroll-behavior: contain; padding: 1px 2px 2px 1px; scrollbar-width: thin; scrollbar-color: rgba(160,190,196,.25) transparent; }
.ivc { position: relative; text-align: left; display: flex; flex-direction: column; gap: 2px; padding: 6px 8px 9px; min-width: 0; cursor: pointer; color: var(--text);
  font-family: var(--f-body); border-radius: 8px; border: 1px solid var(--panel-line);
  background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.015)); box-shadow: inset 0 -3px 0 var(--rc); }
.ivc canvas { width: 100%; height: auto; aspect-ratio: 2 / 1; display: block; border-radius: 4px; margin-bottom: 3px;
  background: radial-gradient(ellipse at 50% 62%, color-mix(in srgb, var(--rc) 24%, transparent), transparent 72%); }
.ivc b { font-weight: 500; font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ivc span { font-size: 10.5px; color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ivc em { position: absolute; top: 6px; right: 6px; font: 700 9px var(--f-body); font-style: normal; letter-spacing: .1em; text-transform: uppercase;
  background: var(--signal); color: #17170f; padding: 2px 5px; border-radius: 3px; }
.ivc em.new { background: var(--rc); color: #0b0d0f; }
.ivc[aria-selected="true"] { border-color: var(--signal); background: linear-gradient(180deg, rgba(242,203,76,.12), rgba(242,203,76,.03)); }
.ivc.dim { opacity: .55; }
.ivc.dim.own { opacity: 1; }
.ivempty { grid-column: 1 / -1; color: var(--dim); font-size: 13px; padding: 14px; border: 1px dashed var(--panel-line); border-radius: 8px; line-height: 1.45; }

.ivopen { position: fixed; inset: 0; z-index: 13; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  background: radial-gradient(80% 70% at 50% 45%, color-mix(in srgb, var(--rc, #f2cb4c) 14%, #0a0e10), #06080a 75%);
  padding: calc(12px + var(--st)) max(16px, var(--sr)) calc(12px + var(--sb)) max(16px, var(--sl)); }
.ivo-t { text-align: center; display: flex; flex-direction: column; gap: 3px; }
.ivo-t small { font-size: 10px; letter-spacing: .26em; text-transform: uppercase; color: var(--signal); }
.ivo-t b { font: 400 22px var(--f-display); }
.ivo-win { position: relative; width: 100%; max-width: 1000px; height: 134px; overflow: hidden; flex: none;
  border-block: 1px solid var(--panel-line); background: rgba(255,255,255,.02); }
.ivo-win::after { content: ""; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(90deg, #06080a, transparent 16%, transparent 84%, #06080a); }
.ivo-strip { position: absolute; left: 0; top: 10px; display: flex; gap: 6px; will-change: transform; }
.ivo-strip .ivc { flex: 0 0 120px; pointer-events: none; }
.ivo-strip .ivc.win { border-color: var(--rc); box-shadow: inset 0 -3px 0 var(--rc), 0 0 18px color-mix(in srgb, var(--rc) 60%, transparent); }
.ivo-mark { position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--signal); box-shadow: 0 0 10px var(--signal); z-index: 2; }
.ivo-mark::before, .ivo-mark::after { content: ""; position: absolute; left: -6px; border: 7px solid transparent; }
.ivo-mark::before { top: 0; border-top-color: var(--signal); } .ivo-mark::after { bottom: 0; border-bottom-color: var(--signal); }
.ivo-res { display: flex; gap: 16px; align-items: center; padding: 12px 16px; border-radius: 12px; border: 1px solid var(--rc); max-width: 640px; width: 100%;
  background: radial-gradient(80% 120% at 0% 50%, color-mix(in srgb, var(--rc) 22%, transparent), rgba(13,19,22,.9)); animation: ivPop .45s cubic-bezier(.2,1.4,.4,1); }
.ivo-res canvas { width: 168px; height: 84px; flex: none; }
.ivo-res .ivr { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.ivo-res .row { gap: 8px; margin-top: 4px; }
.ivo-res .go { font-size: 15px; padding: 9px 16px; } .ivo-res .ghost { font-size: 13px; padding: 8px 12px; }
.ivo-skip { font-size: 12px; padding: 7px 14px; }
@keyframes ivPop { from { transform: scale(.85); opacity: 0; } to { transform: none; opacity: 1; } }
@media (max-height: 460px) {
  #inv > .iv { gap: 8px; }
  .ivt small { display: none; } .ivt b { font-size: 18px; }
  .ivtabs button { padding: 7px 10px; font-size: 12.5px; }
  .ivtok { padding: 5px 10px; font-size: 14px; } .ivtok small { display: none; }
  #inv .ivx { width: 38px; height: 38px; }
  .ivname { font-size: 18px; }
  .ivinfo { padding: 26px 12px 10px; gap: 4px; }
  .ivg { grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 6px; }
  .ivc { padding: 5px 7px 8px; } .ivc b { font-size: 11.5px; }
  .ivchip { padding: 6px 11px; font-size: 12.5px; }
  .ivo-win { height: 114px; } .ivo-strip { top: 8px; } .ivo-strip .ivc { flex-basis: 100px; }
  .ivopen { gap: 10px; } .ivo-t b { font-size: 18px; }
  .ivo-res { padding: 10px 14px; } .ivo-res canvas { width: 132px; height: 66px; }
}
@media (max-width: 600px) {
  .ivb { flex-direction: column; } .ivp { flex: 0 0 52%; }
  .ivt { display: none; }
}
@media (prefers-reduced-motion: reduce) { .ivo-res, #invToast.on { animation: none; } #invToast.on { opacity: 1; } }
`);

/* ---------------- 3D-превью: свой маленький рендерер, освобождается при закрытии ---------------- */
const PV = { r: null, host: null, cv: null, scene: null, cam: null, pivot: null, obj: null, disp: [], yaw: 0, pitch: 0.12, zoom: 1, auto: true, idle: 0, raf: 0, last: 0, ro: null, kind: '', fit: { r: 0.5, y: 0 } };
function pvInit(host) {
  if (PV.r) return true;
  const cv = document.createElement('canvas');
  let r;
  try { r = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true, powerPreference: 'low-power' }); }
  catch (e) { return false; }
  host.appendChild(cv);
  r.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); r.setClearColor(0x000000, 0);
  const sc = new THREE.Scene();
  sc.add(new THREE.HemisphereLight(0xe4edf0, 0x3a332b, 1.05));
  const key = new THREE.DirectionalLight(0xfff0d8, 0.95); key.position.set(2, 3, 2.5); sc.add(key);
  const rim = new THREE.DirectionalLight(0x8fd8ea, 0.55); rim.position.set(-3, 1.5, -2); sc.add(rim);
  const pivot = new THREE.Group(); sc.add(pivot);
  Object.assign(PV, { r, host, cv, scene: sc, cam: new THREE.PerspectiveCamera(28, 1, 0.01, 60), pivot, last: performance.now() });
  // пальцем — вращение, колесом — приближение
  let drag = null;
  cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, id: e.pointerId }; try { cv.setPointerCapture(e.pointerId); } catch (er) {} PV.auto = false; PV.idle = 0; });
  cv.addEventListener('pointermove', e => {
    if (!drag || e.pointerId !== drag.id) return;
    PV.yaw += (e.clientX - drag.x) * 0.012; PV.pitch = clamp(PV.pitch + (e.clientY - drag.y) * 0.006, -0.5, 0.7);
    drag.x = e.clientX; drag.y = e.clientY; PV.idle = 0;
  });
  const up = () => { drag = null; };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('wheel', e => { e.preventDefault(); PV.zoom = clamp(PV.zoom * (e.deltaY > 0 ? 1.1 : 0.9), 0.55, 1.6); }, { passive: false });
  if (window.ResizeObserver) { PV.ro = new ResizeObserver(pvResize); PV.ro.observe(host); }
  pvResize();
  PV.raf = requestAnimationFrame(pvFrame);
  return true;
}
function pvResize() {
  if (!PV.r) return;
  const w = Math.max(1, PV.host.clientWidth), h = Math.max(1, PV.host.clientHeight);
  PV.r.setSize(w, h, false); PV.cam.aspect = w / h; PV.cam.updateProjectionMatrix();
}
function pvFrame(t) {
  if (!PV.r) return;
  PV.raf = requestAnimationFrame(pvFrame);
  const dt = Math.min(0.05, (t - PV.last) / 1000); PV.last = t;
  if (!PV.auto) { PV.idle += dt; if (PV.idle > 3) PV.auto = true; }
  if (PV.auto) PV.yaw += dt * 0.45;
  PV.pivot.rotation.set(0, PV.yaw, 0);
    // камера: вписываем объект по радиусу, смотрим чуть сверху; выше — место под подпись внизу
  // объект занимает долю k полувысоты кадра и сдвинут вверх: внизу панели подпись и кнопки
  const f = PV.fit, tn = Math.tan(PV.cam.fov * Math.PI / 360), asp = PV.cam.aspect;
  const H = f.r / f.k * PV.zoom * Math.max(1, f.wide / asp, 1 / asp);
  const d = H / tn, ty = f.y - H * 0.26;
  PV.cam.position.set(0, ty + Math.sin(PV.pitch) * d, Math.cos(PV.pitch) * d);
  PV.cam.lookAt(0, ty, 0);
  PV.r.render(PV.scene, PV.cam);
}
function pvClear() {
  if (PV.obj) PV.pivot.remove(PV.obj);
  for (const x of PV.disp) try { x.dispose(); } catch (e) {}
  PV.obj = null; PV.disp = [];
}
function pvDestroy() {
  if (!PV.r) return;
  cancelAnimationFrame(PV.raf); pvClear();
  if (PV.ro) PV.ro.disconnect();
  try { PV.r.dispose(); PV.r.forceContextLoss(); } catch (e) {}
  PV.cv.remove();
  Object.assign(PV, { r: null, cv: null, scene: null, cam: null, pivot: null, ro: null });
}
function pvSet(obj, kind, fitR, fitY, k, wide) {
  if (PV.obj) PV.pivot.remove(PV.obj);
  if (PV.kind !== kind) { PV.yaw = { char: Math.PI + 0.55, gun: 0.35, case: 0.45 }[kind] || 0; PV.pitch = 0.12; PV.zoom = 1; }
  PV.obj = obj; PV.kind = kind; PV.fit = { r: fitR, y: fitY, k: k || 0.7, wide: wide || 1 };
  PV.pivot.add(obj);
}
// модель оружия: копия вьюмодели без рук и вспышки (работает и со старыми, и с новыми моделями «Боя»)
function pvGunModel(k) {
  const src = typeof VM !== 'undefined' && VM[k] && VM[k].g, g = new THREE.Group();
  if (src) {
    const c = src.clone(true), a = [], b = [];
    src.traverse(o => a.push(o)); c.traverse(o => b.push(o));
    const cm = skCharMat(), drop = [];
    b.forEach((o, i) => {
      const s = a[i];
      if (o.isSprite || (o.isMesh && cm && o.material === cm) || o.isLight) { drop.push(o); return; }
      o.visible = true;
      if (s && _skOrigMat.has(s)) _skOrigMat.set(o, _skOrigMat.get(s));
    });
    drop.forEach(o => o.parent && o.parent.remove(o));
    c.position.set(0, 0, 0); c.rotation.set(0, 0, 0); c.scale.set(1, 1, 1);
    g.add(c);
  } else if (typeof GUNS !== 'undefined' && GUNS[k]) g.add(new THREE.Mesh(GUNS[k].full, skGunMat()));
  return g;
}
function pvShowGun(k, eq) {
  if (!PV.r) return;
  pvClear();
  const gun = pvGunModel(k);
  skinGunObject(gun, eq, k);
  const holder = new THREE.Group(), box = new THREE.Box3().setFromObject(gun), ctr = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  gun.position.sub(ctr);
  holder.add(gun); holder.rotation.set(0.1, -Math.PI / 2, 0);  // ствол вправо, лёгкий наклон
  const wrap = new THREE.Group(); wrap.add(holder);
  pvSet(wrap, 'gun', Math.max(size.x, size.y, size.z) / 2, 0, 0.62, 1.2);
}
function pvShowChar(team, skinId, k) {
  if (!PV.r) return;
  pvClear();
  const mb = makeBody._skOrig || makeBody;
  let body;
  _skSuppress++;
  try { body = mb(team, skinHasDef(skinId) ? skinId : undefined); } catch (e) { console.error(e); } finally { _skSuppress--; }
  if (!body || !body.root) return;
  for (const o of [body.root, body.blob]) if (o && o.parent) o.parent.remove(o);
  if (body.hit) body.hit.forEach(h => PV.disp.push(h.geometry));
  if (body.blob) { PV.disp.push(body.blob.geometry, body.blob.material); }
  const sbw = setBotWeapon._skOrig || setBotWeapon, fake = { mesh: body, team, cur: k, pos: V3(0, 0, 0) };
  _skSuppress++;
  try { sbw(fake); } catch (e) { console.error(e); } finally { _skSuppress--; }
  if (!skHasRebuild()) recolorObject(body.root, team, skinHasDef(skinId) ? skinId : null);
  skinGunObject(body.gun, invGunSkin(k), k);
  body.root.position.set(0, 0, 0); body.root.rotation.set(0, 0, 0);
  pvSet(body.root, 'char', 0.98, 0.95, 0.7);
  // тень-пятно под ногами
  const blob = new THREE.Mesh(new THREE.CircleGeometry(0.55, 24), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.35, depthWrite: false }));
  blob.rotation.x = -Math.PI / 2; blob.position.y = 0.005; body.root.add(blob); PV.disp.push(blob.geometry, blob.material);
}
const skinHasDef = id => !!(id && CHAR_SKINS[id]);
// кейс: ящик со скруглёнными гранями, наклейкой и ручкой
function pvShowCase(caseId) {
  if (!PV.r) return;
  pvClear();
  const c = CASES[caseId], cv = document.createElement('canvas'); cv.width = 512; cv.height = 256;
  const g = cv.getContext('2d');
  const gr = g.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, c.cols[0]); gr.addColorStop(1, c.cols[2]);
  g.fillStyle = gr; g.fillRect(0, 0, 512, 256);
  for (let i = 0; i < 900; i++) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.04})`; g.fillRect(Math.random() * 512, Math.random() * 256, 2, 2); }
  g.fillStyle = c.cols[1];
  for (let x = -40; x < 560; x += 36) { g.beginPath(); g.moveTo(x, 206); g.lineTo(x + 18, 206); g.lineTo(x + 6, 230); g.lineTo(x - 12, 230); g.fill(); }
  g.fillStyle = 'rgba(0,0,0,.35)'; g.fillRect(40, 54, 432, 116);
  g.strokeStyle = c.cols[1]; g.lineWidth = 3; g.strokeRect(40, 54, 432, 116);
  g.fillStyle = c.cols[1]; g.font = '400 44px "Russo One", "Arial Black", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(c.name.toUpperCase().replace(/[«»]/g, ''), 256, 100, 400);
  g.fillStyle = 'rgba(232,238,236,.7)'; g.font = '500 20px "JetBrains Mono", monospace'; g.fillText('БЛОКПОСТ · ' + c.price + ' ЖЕТОНОВ', 256, 145);
  const tFront = new THREE.CanvasTexture(cv); tFront.anisotropy = 4;
  const side = new THREE.MeshStandardMaterial({ color: new THREE.Color(c.cols[0]), roughness: 0.6, metalness: 0.25 });
  const front = new THREE.MeshStandardMaterial({ map: tFront, roughness: 0.55, metalness: 0.2 });
  const geo = rbox(0.9, 0.46, 0.34, 0.05);
  const box = new THREE.Mesh(geo, [side, side, side, side, front, side]);
  const grp = new THREE.Group(); grp.add(box);
  const metal = new THREE.MeshStandardMaterial({ color: 0x9aa3a8, roughness: 0.35, metalness: 0.9, envMap: skinEnv(), envMapIntensity: 0.8 });
  const handle = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.016, 8, 20, Math.PI), metal); handle.position.y = 0.23; grp.add(handle);
  const latchG = new THREE.BoxGeometry(0.07, 0.05, 0.02);
  for (const x of [-0.3, 0.3]) { const l = new THREE.Mesh(latchG, metal); l.position.set(x, 0.17, 0.175); grp.add(l); }
  const rib = new THREE.BoxGeometry(0.92, 0.02, 0.36), ribM = new THREE.MeshStandardMaterial({ color: 0x15191c, roughness: 0.7 });
  const r1 = new THREE.Mesh(rib, ribM); r1.position.y = 0.12; grp.add(r1);
  pvSet(grp, 'case', 0.5, 0.02, 0.72, 1.1);
  PV.disp.push(geo, side, front, tFront, metal, handle.geometry, latchG, rib, ribM);
}

/* ---------------- экран инвентаря ---------------- */
const IVU = { tab: 'guns', wk: 'rifle', team: 'A', sel: null, caseId: 'field', el: null, opening: false };
function ivEl(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function ivBuild() {
  if (IVU.el) return IVU.el;
  const root = ivEl('div', 'screen'); root.id = 'inv'; root.hidden = true;
  root.innerHTML = `<div class="iv">
    <div class="ivh">
      <div class="ivt"><small>Склад бойца</small><b>Инвентарь</b></div>
      <div class="seg ivtabs" role="tablist"><button data-tab="guns">Оружие</button><button data-tab="chars">Бойцы</button><button data-tab="cases">Кейсы</button></div>
      <div class="ivtok" title="Жетоны — игровая валюта за матчи"><i class="tok"></i><b id="ivTok">0</b><small>жетонов</small></div>
      <button class="tbtn ivx" aria-label="Закрыть" type="button">×</button>
    </div>
    <div class="ivb">
      <div class="ivp"><div class="ivcv"></div><div class="ivhint">Крути пальцем</div>
        <div class="ivinfo"><div class="ivrar"></div><div class="ivname"></div><div class="ivsub"></div><div class="ivwear"><i></i></div><div class="ivx2"></div><div class="ivact"></div></div>
      </div>
      <div class="ivl"><div class="ivf"></div><div class="ivg"></div></div>
    </div>
  </div>`;
  document.body.appendChild(root);
  IVU.el = root;
  root.querySelector('.ivx').addEventListener('click', closeInventory);
  root.querySelector('.ivtabs').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; ivTab(b.dataset.tab); });
  return root;
}
const ivQ = s => IVU.el.querySelector(s);
function invSyncTokens() {
  if (IVU.el) ivQ('#ivTok').textContent = INV.tokens;
  const mb = document.querySelector('#invMenuBtn .tc'); if (mb) mb.textContent = INV.tokens;
}
function openInventory(tab) {
  ivBuild();
  try { initAudio(); } catch (e) {}
  IVU.el.hidden = false;
  if (typeof exitLock === 'function') try { exitLock(); } catch (e) {}
  const pvOk = pvInit(ivQ('.ivcv'));
  ivQ('.ivhint').hidden = !pvOk;
  if (typeof player !== 'undefined' && player && player.primary) IVU.wk = player.primary;
  ivTab(tab && ['guns', 'chars', 'cases'].includes(tab) ? tab : IVU.tab);
  invSyncTokens();
}
function closeInventory() {
  if (!IVU.el) return;
  ivCloseOpening();
  IVU.el.hidden = true;
  pvDestroy();
  invSave();
}
addEventListener('keydown', e => {
  if (e.code !== 'Escape' || !IVU.el || IVU.el.hidden) return;
  if (IVU.opening) ivFinishSpin(); else if (document.querySelector('.ivopen')) ivCloseOpening(); else closeInventory();
});
function ivTab(t) {
  IVU.tab = t;
  IVU.el.querySelectorAll('.ivtabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === t)));
  IVU.sel = null;
  ivRender();
}
function ivSorted(list) {
  const ri = r => SKIN_RARITY_ORDER.indexOf(r);
  return list.slice().sort((a, b) => ri(invDef(b).rarity) - ri(invDef(a).rarity) || invDef(a).name.localeCompare(invDef(b).name, 'ru') || a.w - b.w);
}
function ivCard(item, opts) {
  const def = item.id ? invDef(item) : null, rar = def ? SKIN_RARITY[def.rarity] : null;
  const b = ivEl('button', 'ivc'); b.type = 'button';
  b.style.setProperty('--rc', rar ? rar.color : '#5b666a');
  const cv = document.createElement('canvas'); cv.width = 160; cv.height = 80; b.appendChild(cv);
  if (item.t === 'c') charThumb(cv, item.id || (item.team === 'B' ? '_defB' : '_defA')); else skinThumb(cv, item.id ? item : { t: 'g' });
  b.appendChild(ivEl('b', '', opts.name || (def ? def.name : '')));
  b.appendChild(ivEl('span', '', opts.sub || ''));
  if (opts.badge) b.appendChild(ivEl('em', opts.badgeCls || '', opts.badge));
  return b;
}
function ivFilterChips(list, cur, onPick, cls) {
  const f = ivQ('.ivf'); f.innerHTML = '';
  for (const [v, label, extra] of list) {
    const c = ivEl('button', 'ivchip' + (cls ? ' ' + cls(v) : '')); c.type = 'button';
    c.textContent = label; if (extra) c.appendChild(ivEl('small', '', extra));
    c.setAttribute('aria-pressed', String(v === cur));
    c.addEventListener('click', () => onPick(v));
    f.appendChild(c);
  }
  return f;
}
function ivRender() {
  if (IVU.tab === 'guns') ivRenderGuns(); else if (IVU.tab === 'chars') ivRenderChars(); else ivRenderCases();
}
function ivInfo(rarKey, name, sub, wear) {
  const r = rarKey ? SKIN_RARITY[rarKey] : null;
  ivQ('.ivp').style.setProperty('--rc', r ? r.color : 'var(--panel-line)');
  ivQ('.ivrar').textContent = r ? r.name : 'Штатное';
  ivQ('.ivname').textContent = name; ivQ('.ivsub').textContent = sub || '';
  const w = ivQ('.ivwear'); w.hidden = wear == null;
  if (wear != null) w.firstElementChild.style.left = (wear * 100).toFixed(1) + '%';
  ivQ('.ivx2').innerHTML = '';
  ivQ('.ivact').innerHTML = '';
}
function ivBtn(cls, text, fn, disabled) {
  const b = ivEl('button', cls, text); b.type = 'button'; b.disabled = !!disabled;
  b.addEventListener('click', () => { fn(); try { beep(880, 0.05, 0.06, 'triangle'); } catch (e) {} });
  ivQ('.ivact').appendChild(b); return b;
}
function ivApplyEquip() {
  invSave(); applyGunSkins();
  if (typeof player !== 'undefined' && player) player.skin = invCharSkin(player.team);
}
function ivScrap(it) {
  const v = INV_SCRAP[invDef(it).rarity] || 10;
  for (const k in INV.eqGun) if (INV.eqGun[k] === it.uid) INV.eqGun[k] = null;
  for (const k in INV.eqChar) if (INV.eqChar[k] === it.uid) INV.eqChar[k] = null;
  INV.items = INV.items.filter(x => x !== it);
  INV.tokens += v; IVU.sel = null;
  ivApplyEquip(); invSyncTokens(); ivRender();
}
function ivWeaponsUsing(uid) { return INV_GUNS().filter(k => INV.eqGun[k] === uid).map(k => WEAPONS[k].name); }

function ivRenderGuns() {
  const guns = INV_GUNS();
  if (!guns.includes(IVU.wk)) IVU.wk = guns.includes('rifle') ? 'rifle' : guns[0];
  ivFilterChips(guns.map(k => [k, WEAPONS[k].name]), IVU.wk, k => { IVU.wk = k; IVU.sel = null; ivRenderGuns(); });
  const own = ivSorted(INV.items.filter(i => i.t === 'g'));
  const uniq = new Set(own.map(i => i.id)).size;
  ivQ('.ivf').appendChild(ivEl('span', 'ivcount', 'Собрано ' + uniq + '/' + Object.keys(GUN_SKINS).length));
  const grid = ivQ('.ivg'); grid.innerHTML = '';
  const eqUid = INV.eqGun[IVU.wk] || null;
  if (IVU.sel === null) IVU.sel = eqUid || 'def';
  const def = ivCard({ t: 'g' }, { name: 'Штатная окраска', sub: WEAPONS[IVU.wk].cls, badge: eqUid ? null : 'Надет' });
  def.setAttribute('aria-selected', String(IVU.sel === 'def'));
  def.addEventListener('click', () => { IVU.sel = 'def'; ivRenderGuns(); });
  grid.appendChild(def);
  for (const it of own) {
    const onThis = it.uid === eqUid, used = ivWeaponsUsing(it.uid).length;
    const c = ivCard(it, { sub: wearName(it.w) + (used && !onThis ? ' · на ' + used : ''), badge: onThis ? 'Надет' : it.n ? 'Новый' : null, badgeCls: onThis ? '' : 'new' });
    c.setAttribute('aria-selected', String(IVU.sel === it.uid));
    c.addEventListener('click', () => { IVU.sel = it.uid; if (it.n) { delete it.n; invSave(); } ivRenderGuns(); });
    grid.appendChild(c);
  }
  if (!own.length) {
    const e = ivEl('div', 'ivempty', 'Скинов пока нет. Жетоны дают за устранения, раунды и матчи — открой «Полевой кейс» на вкладке «Кейсы».');
    grid.appendChild(e);
  }
  // витрина и действия
  const it = invItem(IVU.sel), w = WEAPONS[IVU.wk];
  if (it) {
    const d = invDef(it), using = ivWeaponsUsing(it.uid);
    ivInfo(d.rarity, d.name, w.name + ' · ' + wearName(it.w) + ' (' + it.w.toFixed(3) + ')' + (using.length ? ' · надет: ' + using.join(', ') : ''), it.w);
    pvShowGun(IVU.wk, { skin: it.id, wear: it.w });
    const on = INV.eqGun[IVU.wk] === it.uid;
    ivBtn('go', on ? 'Снять' : 'Надеть', () => { INV.eqGun[IVU.wk] = on ? null : it.uid; ivApplyEquip(); ivRenderGuns(); });
    ivBtn('ghost', 'На все стволы', () => { for (const k of INV_GUNS()) INV.eqGun[k] = it.uid; ivApplyEquip(); ivRenderGuns(); }, using.length === INV_GUNS().length);
    ivBtn('ghost', 'Разобрать +' + INV_SCRAP[d.rarity], () => ivScrap(it));
  } else {
    ivInfo(null, w.name, w.cls + ' · штатная окраска', null);
    pvShowGun(IVU.wk, null);
    ivBtn('go', eqUid ? 'Надеть штатную' : 'Надета', () => { INV.eqGun[IVU.wk] = null; ivApplyEquip(); ivRenderGuns(); }, !eqUid);
    ivBtn('ghost', 'Штатная на все', () => { for (const k of INV_GUNS()) INV.eqGun[k] = null; ivApplyEquip(); ivRenderGuns(); }, !INV_GUNS().some(k => INV.eqGun[k]));
  }
}
const TEAM_NAME = { A: '«Сталь»', B: '«Ржавчина»' };
function ivRenderChars() {
  ivFilterChips([['A', 'Сталь'], ['B', 'Ржавчина']], IVU.team, t => { IVU.team = t; IVU.sel = null; ivRenderChars(); }, v => v);
  const team = IVU.team;
  const own = ivSorted(INV.items.filter(i => i.t === 'c' && (CHAR_SKINS[i.id].team === team || CHAR_SKINS[i.id].team === 'any')));
  const total = Object.keys(CHAR_SKINS).filter(id => CHAR_SKINS[id].team === team || CHAR_SKINS[id].team === 'any').length;
  ivQ('.ivf').appendChild(ivEl('span', 'ivcount', 'Собрано ' + new Set(own.map(i => i.id)).size + '/' + total));
  const grid = ivQ('.ivg'); grid.innerHTML = '';
  const eqUid = INV.eqChar[team] || null;
  if (IVU.sel === null) IVU.sel = eqUid || 'def';
  const def = ivCard({ t: 'c', team }, { name: 'Штатная форма', sub: 'Команда ' + TEAM_NAME[team], badge: eqUid ? null : 'Надета' });
  def.setAttribute('aria-selected', String(IVU.sel === 'def'));
  def.addEventListener('click', () => { IVU.sel = 'def'; ivRenderChars(); });
  grid.appendChild(def);
  for (const it of own) {
    const on = it.uid === eqUid, d = CHAR_SKINS[it.id];
    const c = ivCard(it, { sub: SKIN_RARITY[d.rarity].name, badge: on ? 'Надета' : it.n ? 'Новый' : null, badgeCls: on ? '' : 'new' });
    c.setAttribute('aria-selected', String(IVU.sel === it.uid));
    c.addEventListener('click', () => { IVU.sel = it.uid; if (it.n) { delete it.n; invSave(); } ivRenderChars(); });
    grid.appendChild(c);
  }
  if (!own.length) grid.appendChild(ivEl('div', 'ivempty', 'Формы бойцов выпадают из «Кейса отряда» и кейса «Полночь».'));
  const it = invItem(IVU.sel), gk = (typeof player !== 'undefined' && player && player.primary) || 'rifle';
  if (it) {
    const d = CHAR_SKINS[it.id], on = eqUid === it.uid;
    const extra = [d.headgear && { helmet: 'шлем', cap: 'кепка', boonie: 'панама', balaclava: 'балаклава' }[d.headgear], ...(d.extras || []).map(x => ({ backpack: 'рюкзак', radio: 'рация', kneepads: 'наколенники', patch: 'нашивка' }[x] || x))].filter(Boolean);
    ivInfo(d.rarity, d.name, 'Команда ' + TEAM_NAME[team] + (extra.length ? ' · ' + extra.join(', ') : ''), null);
    pvShowChar(team, it.id, gk);
    ivBtn('go', on ? 'Снять' : 'Надеть', () => { INV.eqChar[team] = on ? null : it.uid; ivApplyEquip(); ivRenderChars(); });
    ivBtn('ghost', 'Разобрать +' + INV_SCRAP[d.rarity], () => ivScrap(it));
  } else {
    ivInfo(null, 'Штатная форма', 'Команда ' + TEAM_NAME[team], null);
    pvShowChar(team, null, gk);
    ivBtn('go', eqUid ? 'Надеть штатную' : 'Надета', () => { INV.eqChar[team] = null; ivApplyEquip(); ivRenderChars(); }, !eqUid);
  }
}
function ivRenderCases() {
  ivFilterChips(Object.keys(CASES).map(k => [k, CASES[k].name, String(CASES[k].price)]), IVU.caseId, k => { IVU.caseId = k; ivRenderCases(); });
  const c = CASES[IVU.caseId], pool = casePool(c);
  const grid = ivQ('.ivg'); grid.innerHTML = '';
  const ownIds = new Set(INV.items.map(i => i.t + i.id));
  const ri = r => SKIN_RARITY_ORDER.indexOf(r);
  pool.sort((a, b) => ri(invDef(b).rarity) - ri(invDef(a).rarity));
  for (const e of pool) {
    const d = invDef(e), own = ownIds.has(e.t + e.id);
    if (!(c.odds[d.rarity] > 0)) continue;
    const card = ivCard(e, { sub: (e.t === 'g' ? 'Оружие' : 'Боец ' + (d.team === 'B' ? '«Ржавчина»' : '«Сталь»')), badge: own ? 'Есть' : null });
    card.classList.add('dim'); if (own) card.classList.add('own');
    card.tabIndex = -1;
    grid.appendChild(card);
  }
  ivInfo(null, c.name, c.desc, null);
  ivQ('.ivrar').textContent = 'Кейс';
  ivQ('.ivp').style.setProperty('--rc', c.cols[1]);
  const tot = SKIN_RARITY_ORDER.reduce((s, r) => s + (c.odds[r] || 0), 0);
  const bar = ivEl('div', 'ivodds'), leg = ivEl('div', 'ivoddl');
  for (const r of SKIN_RARITY_ORDER) {
    if (!(c.odds[r] > 0)) continue;
    const p = c.odds[r] / tot * 100, i = ivEl('i'); i.style.width = p + '%'; i.style.background = SKIN_RARITY[r].color; bar.appendChild(i);
    const s = ivEl('span', '', SKIN_RARITY[r].name + ' ' + (p < 10 ? p.toFixed(1) : Math.round(p)) + '%'); s.style.setProperty('--rc', SKIN_RARITY[r].color); leg.appendChild(s);
  }
  ivQ('.ivx2').append(bar, leg);
  pvShowCase(IVU.caseId);
  const lack = c.price - INV.tokens;
  ivBtn('go', 'Открыть · ' + c.price, () => ivStartOpening(IVU.caseId), lack > 0);
  if (lack > 0) ivQ('.ivact').appendChild(ivEl('span', 'ivsub', 'Не хватает ' + lack + ' — играй матчи'));
}

/* ---------------- открытие кейса: лента с прокруткой ---------------- */
const IVO = { el: null, strip: null, raf: 0, t0: 0, dur: 5600, x1: 0, step: 0, half: 0, last: -1, item: null, winIdx: 0 };
function ivStartOpening(caseId) {
  if (IVU.opening) return;
  const item = openCase(caseId); if (!item) return;
  invSyncTokens();
  const c = CASES[caseId], rar = SKIN_RARITY[invDef(item).rarity];
  const ov = ivEl('div', 'ivopen'); ov.style.setProperty('--rc', rar.color);
  ov.innerHTML = '<div class="ivo-t"><small>Открываем</small><b></b></div><div class="ivo-win"><div class="ivo-strip"></div><i class="ivo-mark"></i></div><div class="ivo-slot"></div><button class="ghost ivo-skip" type="button">Пропустить</button>';
  ov.querySelector('.ivo-t b').textContent = c.name;
  IVU.el.appendChild(ov);
  const strip = ov.querySelector('.ivo-strip'), N = 46, W = 37;
  const entries = [];
  for (let i = 0; i < N; i++) entries.push(i === W ? item : caseRollEntry(c));
  // интрига: рядом с выпавшим — что-нибудь из редкого
  const tease = casePool(c).filter(e => ['epic', 'legendary'].includes(invDef(e).rarity));
  if (tease.length) { entries[W + 1] = pick(tease); if (Math.random() < 0.5) entries[W - 2] = pick(tease); }
  entries.forEach((e, i) => {
    const d = invDef(e), card = ivCard(e, { sub: SKIN_RARITY[d.rarity].name });
    if (i === W) card.dataset.win = '1';
    strip.appendChild(card);
  });
  Object.assign(IVO, { el: ov, strip, item, winIdx: W, last: -1 });
  ov.querySelector('.ivo-skip').addEventListener('click', ivFinishSpin);
  requestAnimationFrame(() => {
    const first = strip.children[0], win = ov.querySelector('.ivo-win');
    const cw = first.getBoundingClientRect().width, step = cw + 6, half = win.clientWidth / 2;
    IVO.step = step; IVO.half = half;
    IVO.x1 = W * step + cw / 2 - half + (Math.random() - 0.5) * cw * 0.7;
    IVO.t0 = performance.now(); IVU.opening = true;
    IVO.raf = requestAnimationFrame(ivSpin);
  });
}
function ivSpin(t) {
  if (!IVU.opening) return;
  const k = clamp((t - IVO.t0) / IVO.dur, 0, 1), e = 1 - Math.pow(1 - k, 4), x = IVO.x1 * e;
  IVO.strip.style.transform = `translate3d(${-x}px,0,0)`;
  const idx = Math.floor((x + IVO.half) / IVO.step);
  if (idx !== IVO.last) { IVO.last = idx; try { beep(1500 + (idx % 3) * 90, 0.025, 0.035, 'square'); } catch (er) {} }
  if (k >= 1) ivFinishSpin(); else IVO.raf = requestAnimationFrame(ivSpin);
}
function ivFinishSpin() {
  if (!IVO.el) return;
  cancelAnimationFrame(IVO.raf);
  const was = IVU.opening; IVU.opening = false;
  IVO.strip.style.transform = `translate3d(${-IVO.x1}px,0,0)`;
  const wc = IVO.strip.querySelector('[data-win]'); if (wc) wc.classList.add('win');
  const skip = IVO.el.querySelector('.ivo-skip'); if (skip) skip.remove();
  if (!was && IVO.el.querySelector('.ivo-res')) return;
  const it = IVO.item, d = invDef(it), rar = SKIN_RARITY[d.rarity];
  try { const f = [440, 520, 660, 780, 990][SKIN_RARITY_ORDER.indexOf(d.rarity)]; beep(f, 0.18, 0.09, 'triangle'); setTimeout(() => beep(f * 1.5, 0.3, 0.08, 'triangle'), 120); } catch (e) {}
  const res = ivEl('div', 'ivo-res'); res.style.setProperty('--rc', rar.color);
  const cv = document.createElement('canvas'); cv.width = 336; cv.height = 168;
  if (it.t === 'c') charThumb(cv, it.id); else skinThumb(cv, it);
  const info = ivEl('div', 'ivr');
  const rr = ivEl('div', 'ivrar', rar.name); rr.style.setProperty('--rc', rar.color);
  info.append(rr, ivEl('div', 'ivname', d.name), ivEl('div', 'ivsub', it.t === 'g' ? 'Скин оружия · ' + wearName(it.w) : 'Форма бойца · команда ' + TEAM_NAME[d.team === 'B' ? 'B' : 'A']));
  const row = ivEl('div', 'row');
  const mk = (cls, text, fn, dis) => { const b = ivEl('button', cls, text); b.type = 'button'; b.disabled = !!dis; b.addEventListener('click', fn); row.appendChild(b); return b; };
  mk('go', 'Забрать', () => { ivCloseOpening(); ivShowItem(it); });
  const c = CASES[IVU.caseId];
  mk('ghost', 'Ещё · ' + c.price, () => { ivCloseOpening(); ivStartOpening(IVU.caseId); }, INV.tokens < c.price);
  mk('ghost', it.t === 'g' ? 'Надеть на ' + WEAPONS[IVU.wk].name : 'Надеть', () => {
    if (it.t === 'g') INV.eqGun[IVU.wk] = it.uid; else INV.eqChar[d.team === 'B' ? 'B' : 'A'] = it.uid;
    ivApplyEquip(); ivCloseOpening(); ivShowItem(it);
  });
  info.appendChild(row);
  res.append(cv, info);
  IVO.el.querySelector('.ivo-slot').appendChild(res);
}
function ivCloseOpening() {
  cancelAnimationFrame(IVO.raf); IVU.opening = false;
  if (IVO.el) IVO.el.remove();
  IVO.el = null;
  if (IVU.el && !IVU.el.hidden && IVU.tab === 'cases') ivRenderCases();
}
function ivShowItem(it) {
  if (it.t === 'g') { IVU.tab = 'guns'; } else { IVU.tab = 'chars'; IVU.team = CHAR_SKINS[it.id].team === 'B' ? 'B' : 'A'; }
  IVU.el.querySelectorAll('.ivtabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === IVU.tab)));
  delete it.n; invSave();
  IVU.sel = it.uid; ivRender();
}

/* ---------------- кнопка в меню (временная, если UX не добавил свою) ---------------- */
function invMenuButton() {
  if (document.getElementById('invBtn') || document.querySelector('[data-open="inventory"]') || document.getElementById('invMenuBtn')) return;
  const start = document.getElementById('startBtn'); if (!start || !start.parentElement) return;
  const b = ivEl('button', 'ghost'); b.id = 'invMenuBtn'; b.type = 'button';
  b.innerHTML = 'Инвентарь <i class="tok"></i><span class="tc"></span>';
  b.addEventListener('click', () => openInventory());
  start.parentElement.appendChild(b);
  invSyncTokens();
}
addEventListener('load', invMenuButton);
// модели к этому моменту уже созданы — красим их по сохранённому выбору
applyGunSkins();
