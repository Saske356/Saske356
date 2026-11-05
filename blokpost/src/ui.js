'use strict';
/* ---------------- закупка и арсенал ---------------- */
const buyEl = $('#buy'), itemsEl = $('#items');
const canBuy = () => mode.rounds ? player.alive && (state === 'freeze' || (state === 'live' && roundElapsed < BUY_WINDOW)) : (state === 'live' || state === 'freeze');
function statBars(w) {
  const rows = [['Урон', Math.min(1, w.dmg * (w.pellets || 1) / 150)], ['Темп', Math.min(1, 0.08 / w.rate)], ['Точность', clamp(1 - (w.scope ? w.scopedSpread : w.spread) / 0.07, 0.05, 1)]];
  return rows.map(([n, v]) => `<span>${n}</span><i style="--w:${Math.round(v * 100)}%"></i>`).join('');
}
function renderBuy() {
  itemsEl.innerHTML = '';
  const tdm = !mode.rounds;
  $('#buyTitle').textContent = tdm ? 'Арсенал' : 'Закупка';
  const list = tdm ? PRIMARIES : [...PRIMARIES, 'armor'];
  for (const k of list) {
    const isArmor = k === 'armor', w = WEAPONS[k];
    const price = isArmor ? ARMOR_PRICE : w.price;
    const own = tdm ? player.loadout === k : (isArmor ? player.armor >= 100 : player.primary === k);
    const b = document.createElement('button'); b.className = 'item' + (own ? ' own' : ''); b.id = 'buy-' + k;
    b.innerHTML = `<b></b><span></span><div class="st"></div><div class="p"></div>`;
    b.children[0].textContent = isArmor ? 'Бронежилет' : w.name;
    b.children[1].textContent = isArmor ? 'Плиты поглощают половину урона' : w.cls + '. ' + w.desc;
    if (!isArmor) b.children[2].innerHTML = statBars(w);
    b.children[3].textContent = own ? (tdm ? 'Выбрано' : 'Есть') : tdm ? 'Выбрать' : '$' + price;
    b.disabled = tdm ? false : (own || player.money < price || !canBuy());
    b.addEventListener('click', () => buy(k));
    itemsEl.appendChild(b);
  }
  $('#buyMoney').textContent = tdm ? '' : '$' + player.money;
  $('#buyTime').textContent = tdm ? (player.alive && (player.protT > 0 || state === 'freeze') ? 'Выдадим сразу' : 'Выдадим при возрождении') : (canBuy() ? '' : 'Время закупки вышло');
}
function buy(k) {
  if (!mode.rounds) {
    player.loadout = k;
    if (player.alive && (player.protT > 0 || state === 'freeze')) { player.primary = k; giveAmmo(player, k); equip(player, k, true); }
    beep(880, 0.06, 0.08, 'triangle'); renderBuy(); return;
  }
  if (!canBuy()) return;
  if (k === 'armor') { if (player.money < ARMOR_PRICE || player.armor >= 100) return; player.money -= ARMOR_PRICE; player.armor = 100; }
  else {
    const w = WEAPONS[k]; if (player.money < w.price || player.primary === k) return;
    player.money -= w.price; player.primary = k; giveAmmo(player, k); equip(player, k, true);
  }
  beep(880, 0.06, 0.08, 'triangle');
  renderBuy();
}
function openBuy() { if (!canBuy()) return; renderBuy(); buyEl.hidden = false; exitLock(); }
function closeBuy() { buyEl.hidden = true; }
$('#buyClose').addEventListener('click', () => { closeBuy(); requestLock(); });
buyEl.addEventListener('pointerdown', e => { if (e.target === buyEl) closeBuy(); });
const buyBtn = $('#buyBtn');
buyBtn.addEventListener('click', () => { initAudio(); buyEl.hidden ? openBuy() : closeBuy(); });
function updateBuyBtn() {
  const v = canBuy() && state !== 'menu' && state !== 'over';
  const label = mode.rounds ? 'ЗАКУПКА' : 'АРСЕНАЛ';
  if (buyBtn.textContent !== label) buyBtn.textContent = label;
  if (buyBtn.hidden === v) buyBtn.hidden = !v;
  if (!v && !buyEl.hidden) closeBuy();
}

/* ---------------- экраны ---------------- */
function setScreen(name) {
  for (const id of ['menu', 'over']) $('#' + id).hidden = id !== name;
  const inGame = name === null;
  $('#hud').classList.toggle('off', !inGame);
  touchEl.classList.toggle('on', inGame && isTouch);
  $('#pauseBtn').hidden = !inGame;
  if (!inGame) { buyBtn.hidden = true; closeBuy(); closeBoard(); $('#pause').hidden = true; }
}
function setPause(v) {
  paused = v; $('#pause').hidden = !v;
  input.fire = false; input.keys = {};
  if (v) { exitLock(); syncSettingsUI(); } else requestLock();
}
$('#pauseBtn').addEventListener('click', () => setPause(!paused));
$('#resumeBtn').addEventListener('click', () => setPause(false));
$('#quitBtn').addEventListener('click', () => { paused = false; toMenu(); });
function toMenu() { state = 'menu'; exitLock(); for (const g in VM) VM[g].g.visible = false; resetMenuScene(); setScreen('menu'); }
function begin() {
  initAudio(); saveSettings(); resize();
  if (isTouch) {
    try { const el = document.documentElement; const r = el.requestFullscreen && el.requestFullscreen({ navigationUI: 'hide' }); if (r && r.then) r.then(() => { try { screen.orientation.lock('landscape').catch(() => {}); } catch (e) {} }).catch(() => {}); } catch (e) {}
  }
  setScreen(null); startMatch(); requestLock();
}
$('#startBtn').addEventListener('click', begin);
$('#againBtn').addEventListener('click', begin);
$('#menuBtn').addEventListener('click', toMenu);
$('#helpTouch').hidden = !isTouch; $('#helpPc').hidden = isTouch;

const modesEl = $('#modes');
function renderModes() {
  modesEl.innerHTML = '';
  for (const k of ['tdm', 'comp', 'allies']) {
    const m = MODES[k], b = document.createElement('button');
    b.className = 'mode'; b.id = 'mode-' + k; b.setAttribute('aria-pressed', String(settings.mode === k));
    b.innerHTML = '<b></b><div class="tag"></div><span></span>';
    b.children[0].textContent = m.name; b.children[1].textContent = m.tag; b.children[2].textContent = m.desc;
    b.addEventListener('click', () => { settings.mode = k; saveSettings(); renderModes(); resetMenuScene(); });
    modesEl.appendChild(b);
  }
}
renderModes();
function segInit(id, key, parse, onChange) {
  const seg = $(id);
  const sync = () => seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(parse(b.dataset.v) === settings[key])));
  seg.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; settings[key] = parse(b.dataset.v); sync(); saveSettings(); onChange && onChange(); });
  sync(); return sync;
}
const syncDiff = segInit('#diffSeg', 'diff', v => +v);
const syncQ = segInit('#qSeg', 'quality', v => +v, resize);
const syncSnd = segInit('#sndSeg', 'sound', v => +v);
function bindSens(inp, out) {
  const el = $(inp), o = $(out);
  el.addEventListener('input', () => { settings.sens = +el.value; o.textContent = settings.sens.toFixed(2); saveSettings(); });
}
bindSens('#sens', '#sensVal'); bindSens('#sens2', '#sensVal2');
function syncSettingsUI() {
  for (const [i, o] of [['#sens', '#sensVal'], ['#sens2', '#sensVal2']]) { $(i).value = settings.sens; $(o).textContent = (+settings.sens).toFixed(2); }
  syncDiff(); syncQ(); syncSnd();
}
syncSettingsUI();

// витрина в меню: бойцы обеих команд стоят в проходе склада
const SHOW = { x: 40, z: 30 };
function resetMenuScene() {
  mode = MODES[settings.mode];
  buildUnits();
  roundNo = 1;
  for (const u of units) { u.primary = pick(PRIMARIES); u.armor = 100; u.money = 0; resetUnit(u, true); }
  placeTeams();
  const n = bots.length;
  bots.forEach((b, i) => {
    const t = n > 1 ? i / (n - 1) - 0.5 : 0;
    b.pos.set(SHOW.x + t * Math.min(7, n * 0.9), 0, SHOW.z + Math.abs(t) * 1.6 + (i % 2) * 0.6);
    b.yaw = yawTo(b.pos.x, b.pos.z, SHOW.x - 2, SHOW.z + 12) + (i % 2 ? 0.25 : -0.15);
    syncBotMesh(b, 0, 0);
  });
}
