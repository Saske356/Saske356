'use strict';
/* ---------------- закупка и арсенал ---------------- */
const buyEl = $('#buy'), itemsEl = $('#items'), catsEl = $('#cats');
const canBuy = () => mode.rounds ? player.alive && (state === 'freeze' || (state === 'live' && roundElapsed < BUY_WINDOW)) : (state === 'live' || state === 'freeze');
const ICON_SVG = {
  armor: '<svg viewBox="0 0 24 24"><path d="M12 2.8l7.5 2.8v5.6c0 4.8-3.2 8.6-7.5 10-4.3-1.4-7.5-5.2-7.5-10V5.6z"/><path d="M12 7v10M8 10.5h8"/></svg>',
  grenade: '<svg viewBox="0 0 24 24"><circle cx="11" cy="14" r="6.5"/><path d="M9 7.5V5h4v2.5M13 5.5l4-2.5 2 2"/></svg>',
  kit: '<svg viewBox="0 0 24 24"><rect x="3.5" y="7" width="17" height="12" rx="2"/><path d="M9 7V4.5h6V7M3.5 12h17"/></svg>',
};
// категории магазина; оружие раскладывается по полю cat (если есть) или по cls
const SHOP_CATS = [
  { id: 'pistol', name: 'Пистолеты' }, { id: 'smg', name: 'ПП' }, { id: 'shotgun', name: 'Дробовики' },
  { id: 'rifle', name: 'Винтовки' }, { id: 'sniper', name: 'Снайперские' }, { id: 'gear', name: 'Снаряжение' }, { id: 'nade', name: 'Гранаты' },
];
const isMelee = (k, w) => k === 'knife' || w.melee || /нож/i.test(w.cls || '');
function catOf(k, w) {
  if (w.cat) return w.cat;
  const c = (w.cls || '').toLowerCase();
  if (c.includes('пистолет-пулем')) return 'smg';
  if (c.startsWith('пистолет') || w.hold === 'pistol') return 'pistol';
  if (c.includes('дробов')) return 'shotgun';
  if (c.includes('снайпер') || w.scope) return 'sniper';
  return 'rifle';
}
const nadeList = () => {
  if (typeof GRENADES === 'undefined' || !GRENADES) return [];
  return Array.isArray(GRENADES) ? GRENADES.map(g => typeof g === 'string' ? [g, WEAPONS[g] || {}] : [g.id || g.key, g]) : Object.entries(GRENADES); // [интеграция] ключи гранат из weapons.js
};
const extraList = () => (typeof EXTRA_ITEMS !== 'undefined' && Array.isArray(EXTRA_ITEMS)) ? EXTRA_ITEMS.filter(it => !it.side || !player.side || it.side === player.side) : [];
const shopWeapons = () => Object.keys(WEAPONS).filter(k => !isMelee(k, WEAPONS[k]) && !WEAPONS[k].noBuy && !WEAPONS[k].grenade && (k === 'pistol' || PRIMARIES.includes(k) || WEAPONS[k].price > 0));
let shopCat = 'rifle';
function statBars(w) {
  const sp = w.scope ? w.scopedSpread : w.spread;
  const rows = [['Урон', Math.min(1, w.dmg * (w.pellets || 1) / 150)], ['Темп', Math.min(1, 0.075 / w.rate)], ['Точность', clamp(1 - sp / 0.07, 0.05, 1)], ['Подвижность', clamp((w.speed - 0.75) / 0.25, 0.05, 1)]];
  return rows.map(([n, v]) => `<span>${n}</span><i style="--w:${Math.round(v * 100)}%"></i>`).join('');
}
function shopItems(cat) {
  const tdm = !mode.rounds, out = [];
  if (cat === 'gear') {
    if (tdm) return out;
    out.push({ id: 'armor', name: 'Бронежилет', desc: 'Плиты поглощают половину урона', price: ARMOR_PRICE, icon: ICON_SVG.armor,
      own: player.armor >= 100, buy: () => { if (player.money < ARMOR_PRICE || player.armor >= 100) return false; player.money -= ARMOR_PRICE; player.armor = 100; return true; } });
    if (typeof buyArmor === 'function') out.push({ id: 'helmet', name: 'Бронежилет и шлем', desc: 'Шлем гасит часть урона в голову', price: (player.armor >= 100 ? 0 : ARMOR_PRICE) + HELMET_PRICE, icon: ICON_SVG.armor,
      own: player.armor >= 100 && !!player.helmet, buy: () => buyArmor(player, true) }); // [интеграция]
    for (const it of extraList()) {
      out.push({ id: it.id, name: it.name, desc: it.desc, price: it.price || 0, icon: ICON_SVG.kit,
        own: !!(it.owned && it.owned(player)), buy: () => !!(it.buy && it.buy(player) !== false) });
    }
    return out;
  }
  if (cat === 'nade') {
    if (typeof buyGrenade !== 'function') return out;
    for (const [id, g] of nadeList()) {
      const n = player.ammo && player.ammo[id] ? player.ammo[id].mag : (player.grenades && typeof player.grenades[id] === 'number' ? player.grenades[id] : 0); // [интеграция]
      out.push({ id, name: g.name || wName(id), desc: g.desc || '', price: g.price || 0, icon: g.icon || ICON_SVG.grenade, count: n,
        own: g.max != null ? n >= g.max : false, buy: () => buyGrenade(player, id) !== false });
    }
    return out;
  }
  for (const k of shopWeapons()) {
    const w = WEAPONS[k]; if (catOf(k, w) !== cat) continue;
    const base = k === 'pistol';
    const own = tdm ? (base ? true : player.loadout === k) : (base ? true : player.primary === k || player.secondary === k);
    out.push({ id: k, gun: true, name: w.name, desc: w.cls + '. ' + (w.desc || ''), price: tdm || base ? 0 : w.price, w,
      own, base, buy: () => buyWeapon(k) });
  }
  return out;
}
function buyWeapon(k) {
  const w = WEAPONS[k];
  if (!mode.rounds) {
    if (k === 'pistol') return false;
    player.loadout = k;
    if (player.alive && (player.protT > 0 || state === 'freeze')) { player.primary = k; giveAmmo(player, k); equip(player, k, true); }
    return true;
  }
  if (k === 'pistol' || player.money < w.price) return false;
  if (catOf(k, w) === 'pistol' && w.slot === 'secondary' && typeof buySecondary === 'function') return buySecondary(player, k) !== false;
  if (player.primary === k) return false;
  player.money -= w.price; player.primary = k; giveAmmo(player, k); equip(player, k, true);
  return true;
}
function renderCats() {
  const tdm = !mode.rounds;
  catsEl.innerHTML = '';
  for (const c of SHOP_CATS) {
    const items = shopItems(c.id);
    if (!items.length) continue;
    const b = document.createElement('button'); b.className = 'cat'; b.dataset.cat = c.id;
    b.setAttribute('aria-pressed', String(shopCat === c.id));
    const g = items.find(i => i.gun && !i.base) || items[0];
    b.innerHTML = (g.gun ? `<img src="${gunIcon(g.id).sil}" alt="">` : `<span class="ci">${g.icon}</span>`) + `<b>${c.name}</b>` +
      (items.some(i => i.own && !i.base) && !tdm ? '<i class="dot"></i>' : '');
    b.addEventListener('click', () => { shopCat = c.id; renderBuy(); });
    catsEl.appendChild(b);
  }
}
function renderBuy() {
  const tdm = !mode.rounds;
  if (!shopItems(shopCat).length) shopCat = SHOP_CATS.find(c => shopItems(c.id).length).id;
  renderCats();
  $('#buyTitle').textContent = tdm ? 'Арсенал' : 'Закупка';
  itemsEl.innerHTML = '';
  for (const it of shopItems(shopCat)) {
    const b = document.createElement('button'); b.className = 'item' + (it.own ? ' own' : ''); b.id = 'buy-' + it.id;
    const afford = tdm || player.money >= it.price;
    const label = it.own ? (it.base ? 'Базовый' : tdm ? 'Выбрано' : 'Есть') : tdm ? 'Выбрать' : it.price ? '$' + it.price : 'Бесплатно';
    b.innerHTML = `<div class="pic">${it.gun ? `<img src="${gunIcon(it.id).img}" alt="">` : it.icon}</div>` +
      `<div class="nm"><b>${esc(it.name)}</b>${it.count ? `<em>×${it.count}</em>` : ''}</div>` +
      (it.gun ? `<div class="st">${statBars(it.w)}</div>` : `<span class="ds">${esc(it.desc)}</span>`) +
      `<div class="p${afford ? '' : ' no'}">${label}</div>`;
    if (it.gun) b.title = it.desc;
    b.disabled = tdm ? !!it.base : (it.own || !afford || !canBuy());
    b.addEventListener('click', () => {
      if (mode.rounds && !canBuy()) return;
      if (it.buy()) { beep(880, 0.06, 0.08, 'triangle'); renderBuy(); } else sfxClick();
    });
    itemsEl.appendChild(b);
  }
  $('#buyMoney').textContent = tdm ? '' : '$' + player.money;
  cache.buyTime = null; updateBuyTime();
}
function updateBuyTime() {
  const tdm = !mode.rounds;
  let t;
  if (tdm) t = player.alive && (player.protT > 0 || state === 'freeze') ? 'Выдадим сразу' : 'Выдадим при возрождении';
  else if (!canBuy()) t = 'Время закупки вышло';
  else t = 'Ещё ' + Math.ceil(state === 'freeze' ? freezeT + BUY_WINDOW : BUY_WINDOW - roundElapsed) + ' с';
  if (cache.buyTime !== t) { cache.buyTime = t; $('#buyTime').textContent = t; }
}
// совместимость: старый вызов buy(k)
function buy(k) { if (buyWeapon(k)) { beep(880, 0.06, 0.08, 'triangle'); renderBuy(); } }
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
  if (buyBtn.hidden === (v && !isTouch)) buyBtn.hidden = !(v && !isTouch);
  if (cache.tBuy !== v) { cache.tBuy = v; tbtn.buy.classList.toggle('na', !v); }
  if (!v && !buyEl.hidden) closeBuy();
  if (!buyEl.hidden) updateBuyTime();
}

/* ---------------- экраны ---------------- */
let inMatch = false;
function setScreen(name) {
  for (const id of ['menu', 'over']) $('#' + id).hidden = id !== name;
  const inGame = name === null;
  inMatch = inGame;
  $('#hud').classList.toggle('off', !inGame);
  touchEl.classList.toggle('on', inGame && isTouch);
  $('#pauseBtn').hidden = !inGame || isTouch;
  if (inGame) { refreshTouchButtons(); hideDeath(); } else releaseTouches();
  if (!inGame) { buyBtn.hidden = true; closeBuy(); closeBoard(); $('#pause').hidden = true; hideDeath(); releaseWake(); }
  if (name === 'menu') { $('#invBtn').hidden = typeof openInventory !== 'function'; }
  if (name === 'over') renderOver();
}
function setPause(v) {
  paused = v; $('#pause').hidden = !v;
  input.keys = {}; releaseTouches();
  if (v) { exitLock(); syncSettingsUI(); } else { closeOverlays(); requestLock(); }
}
$('#pauseBtn').addEventListener('click', () => setPause(!paused));
$('#resumeBtn').addEventListener('click', () => setPause(false));
$('#quitBtn').addEventListener('click', () => { paused = false; toMenu(); });
$('#pauseSet').addEventListener('click', () => openSettings());
function toMenu() { state = 'menu'; exitLock(); closeOverlays(); for (const g in VM) VM[g].g.visible = false; resetMenuScene(); setScreen('menu'); }
function begin() {
  initAudio(); saveSettings(); applyRes();
  if (isTouch) {
    try { const el = document.documentElement; const r = el.requestFullscreen && el.requestFullscreen({ navigationUI: 'hide' }); if (r && r.then) r.then(() => { try { screen.orientation.lock('landscape').catch(() => {}); } catch (e) {} }).catch(() => {}); } catch (e) {}
  }
  setScreen(null); startMatch(); requestLock(); requestWake();
}
$('#startBtn').addEventListener('click', begin);
$('#againBtn').addEventListener('click', begin);
$('#menuBtn').addEventListener('click', toMenu);
$('#setBtn').addEventListener('click', () => openSettings());
$('#layBtn').addEventListener('click', () => openEditor());
$('#invBtn').addEventListener('click', () => { if (typeof openInventory === 'function') openInventory(); });
$('#helpTouch').hidden = !isTouch; $('#helpPc').hidden = isTouch;

// итоги матча: личная статистика и лучший игрок
function renderOver() {
  const p = player;
  $('#ovA').textContent = assistsOf(p);
  $('#ovDmg').textContent = p._dmg || 0;
  const best = units.slice().sort((a, b) => (scoreOf(b) + (b._dmg || 0) / 1000) - (scoreOf(a) + (a._dmg || 0) / 1000))[0];
  const el = $('#ovMvp');
  if (!best) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<div class="star">MVP</div><div><b class="${esc(best.team)}">${esc(best.isPlayer ? 'Ты' : best.name)}</b>` +
    `<span>${best.kills} уб · ${assistsOf(best)} пом · ${best.deaths} см · урон ${best._dmg || 0}</span></div>`;
}

/* ---------------- главное меню ---------------- */
const modesEl = $('#modes');
const modeOrder = () => (typeof MODE_ORDER !== 'undefined' && Array.isArray(MODE_ORDER) ? MODE_ORDER : Object.keys(MODES)).filter(k => MODES[k]);
function renderModes() {
  modesEl.innerHTML = '';
  for (const k of modeOrder()) {
    const m = MODES[k], b = document.createElement('button');
    b.className = 'mode'; b.id = 'mode-' + k; b.setAttribute('aria-pressed', String(settings.mode === k));
    b.innerHTML = `<b>${esc(m.name)}</b><span class="tag">${esc(m.tag || '')}</span>`;
    b.addEventListener('click', () => { if (settings.mode === k) return; settings.mode = k; saveSettings(); renderModes(); resetMenuScene(); });
    modesEl.appendChild(b);
  }
  const m = MODES[settings.mode]; $('#modeDesc').textContent = m ? m.desc || '' : '';
}
renderModes();
function segInit(id, key, parse, onChange) {
  const seg = $(id);
  const sync = () => seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(parse(b.dataset.v) === settings[key])));
  seg.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; settings[key] = parse(b.dataset.v); sync(); saveSettings(); onChange && onChange(); });
  sync(); return sync;
}
const syncDiff = segInit('#diffSeg', 'diff', v => +v);
function bindSens(inp, out) {
  const el = $(inp), o = $(out);
  el.addEventListener('input', () => { settings.sens = +el.value; o.textContent = settings.sens.toFixed(2); saveSettings(); });
}
bindSens('#sens2', '#sensVal2');
function syncSettingsUI() {
  $('#sens2').value = settings.sens; $('#sensVal2').textContent = (+settings.sens).toFixed(2);
  syncDiff();
}
syncSettingsUI();

/* ---------------- настройки ---------------- */
const pct = v => Math.round(v * 100) + '%';
function applyGfx(preset) {
  const p = GFX_PRESETS[settings.gfx];
  if (preset && p) { settings.quality = p.quality; settings.shadows = p.shadows; }
  applyRes();
  bus.emit('settings:gfx', settings.gfx);
}
const SET_TABS = [
  { id: 'ctrl', name: 'Управление', rows: [
    { k: 'sens', t: 'range', name: 'Чувствительность', min: 0.2, max: 3, step: 0.05, fmt: v => (+v).toFixed(2) },
    { k: 'adsSens', t: 'range', name: 'В прицеле', hint: 'Множитель при прицеливании', min: 0.2, max: 2, step: 0.05, fmt: v => '×' + (+v).toFixed(2) },
    { k: 'accel', t: 'range', name: 'Ускорение обзора', hint: 'Быстрый свайп поворачивает сильнее', min: 0, max: 1, step: 0.05, fmt: v => +v ? pct(v) : 'Выкл' },
    { k: 'autoFire', t: 'toggle', name: 'Автоогонь', hint: 'Стрельба, когда враг под прицелом', touch: true },
    { k: 'crouchHold', t: 'seg', name: 'Присед', opts: [[false, 'Нажатие'], [true, 'Удержание']] },
    { k: 'lefty', t: 'toggle', name: 'Левша', hint: 'Зеркальная раскладка кнопок', on: () => applyLayout() },
    { k: 'invertY', t: 'toggle', name: 'Инверсия по вертикали' },
    { t: 'button', name: 'Раскладка кнопок', hint: 'Положение, размер, прозрачность', label: 'Настроить', fn: () => openEditor() },
  ] },
  { id: 'gfx', name: 'Графика', rows: [
    { k: 'gfx', t: 'seg', name: 'Качество', opts: [['low', 'Низкое'], ['medium', 'Среднее'], ['high', 'Высокое']], on: () => { applyGfx(true); renderSettings(); } },
    { k: 'quality', t: 'seg', name: 'Чёткость', hint: 'Плотность пикселей', opts: [[0.6, '0.6×'], [0.75, '0.75×'], [1, '1×'], [1.5, '1.5×'], [2, '2×']], on: () => applyRes() },
    { k: 'dynRes', t: 'toggle', name: 'Динамическое разрешение', hint: 'Снижает чёткость, если не хватает кадров', on: () => applyRes() },
    { k: 'shadows', t: 'toggle', name: 'Тени', on: () => bus.emit('settings:shadows', settings.shadows) },
    { k: 'fpsCap', t: 'seg', name: 'Ограничение FPS', opts: [[30, '30'], [60, '60'], [0, 'Нет']] },
    { k: 'fov', t: 'range', name: 'Поле зрения', min: 60, max: 95, step: 1, fmt: v => v + '°' },
    { k: 'showFps', t: 'toggle', name: 'Показывать FPS' },
  ] },
  { id: 'snd', name: 'Звук', rows: [
    { k: 'sound', t: 'toggle', name: 'Звук', num: true },
    { k: 'volume', t: 'range', name: 'Громкость', min: 0, max: 1, step: 0.05, fmt: pct },
  ] },
  { id: 'hud', name: 'Интерфейс', rows: [
    { k: 'radarRotate', t: 'toggle', name: 'Радар вращается', hint: 'Иначе север всегда сверху' },
    { k: 'diff', t: 'seg', name: 'Противник', opts: DIFF.map((d, i) => [i, d.name]), on: () => syncDiff() },
  ] },
];
let setTab = 'ctrl';
const setEl = $('#settings'), setPane = $('#setPane');
function renderSettings() {
  const tabs = $('#setTabs'); tabs.innerHTML = '';
  for (const t of SET_TABS) {
    const b = document.createElement('button'); b.textContent = t.name; b.setAttribute('aria-pressed', String(t.id === setTab));
    b.addEventListener('click', () => { setTab = t.id; renderSettings(); }); tabs.appendChild(b);
  }
  setPane.innerHTML = '';
  for (const r of SET_TABS.find(t => t.id === setTab).rows) {
    if (r.touch && !isTouch) continue;
    const row = document.createElement('div'); row.className = 'srow';
    row.innerHTML = `<div class="sl"><b>${esc(r.name)}</b>${r.hint ? `<small>${esc(r.hint)}</small>` : ''}</div><div class="sc"></div>`;
    const c = row.lastElementChild;
    const set = v => { settings[r.k] = v; saveSettings(); r.on && r.on(v); bus.emit('settings:changed', r.k, v); };
    if (r.t === 'range') {
      c.innerHTML = `<input type="range" min="${r.min}" max="${r.max}" step="${r.step}" aria-label="${esc(r.name)}"><span class="val"></span>`;
      const inp = c.firstElementChild, val = c.lastElementChild;
      inp.value = settings[r.k]; val.textContent = r.fmt(settings[r.k]);
      inp.addEventListener('input', () => { set(+inp.value); val.textContent = r.fmt(+inp.value); });
    } else if (r.t === 'toggle') {
      const b = document.createElement('button'); b.className = 'tog'; b.setAttribute('role', 'switch'); b.setAttribute('aria-label', r.name);
      const sync = () => { const on = !!settings[r.k]; b.setAttribute('aria-checked', String(on)); };
      b.innerHTML = '<i></i>'; sync();
      b.addEventListener('click', () => { const on = !settings[r.k]; set(r.num ? (on ? 1 : 0) : on); sync(); });
      c.appendChild(b);
    } else if (r.t === 'seg') {
      const s = document.createElement('div'); s.className = 'seg';
      for (const [v, n] of r.opts) {
        const b = document.createElement('button'); b.textContent = n; b.setAttribute('aria-pressed', String(settings[r.k] === v));
        b.addEventListener('click', () => { set(v); s.querySelectorAll('button').forEach((x, i) => x.setAttribute('aria-pressed', String(r.opts[i][0] === v))); });
        s.appendChild(b);
      }
      c.appendChild(s);
    } else if (r.t === 'button') {
      const b = document.createElement('button'); b.className = 'ghost sm'; b.textContent = r.label; b.addEventListener('click', r.fn); c.appendChild(b);
    }
    setPane.appendChild(row);
  }
}
function openSettings(tab) { if (tab) setTab = tab; renderSettings(); setEl.hidden = false; exitLock(); }
function closeSettings() { setEl.hidden = true; syncSettingsUI(); }
$('#setClose').addEventListener('click', closeSettings);
setEl.addEventListener('pointerdown', e => { if (e.target === setEl) closeSettings(); });
function closeOverlays() { if (!setEl.hidden) closeSettings(); if (!edEl.hidden) closeEditor(false); }

/* ---------------- редактор раскладки ---------------- */
const edEl = $('#layoutEd'), edBtns = $('#edBtns'), edBar = $('#edBar');
const edBtn = {};
let edSel = null, edBackup = null, edDrag = null;
for (const def of TOUCH_BTNS) {
  const el = makeTouchButton(def, edBtns); el.id = 'ed-' + def.id; el.classList.add('show');
  el.removeAttribute('data-btn'); edBtn[def.id] = el;
}
function safeInsets() {
  const cs = getComputedStyle($('#safeProbe'));
  return { l: parseFloat(cs.paddingLeft) || 0, r: parseFloat(cs.paddingRight) || 0, t: parseFloat(cs.paddingTop) || 0, b: parseFloat(cs.paddingBottom) || 0 };
}
function edRefresh() {
  for (const def of TOUCH_BTNS) { placeBtn(edBtn[def.id], def); edBtn[def.id].classList.toggle('sel', edSel === def.id); }
  const def = TOUCH_BTNS.find(d => d.id === edSel);
  edBar.classList.toggle('has', !!def);
  if (def) {
    const p = btnPos(def);
    $('#edName').textContent = def.name;
    $('#edSize').value = p.sc; $('#edSizeV').textContent = pct(p.sc);
    $('#edOp').value = p.o; $('#edOpV').textContent = pct(p.o);
  } else $('#edName').textContent = 'Выбери кнопку';
}
function edEntry(id) {
  const def = TOUCH_BTNS.find(d => d.id === id), p = btnPos(def);
  const h = settings.lefty ? (p.h === 'l' ? 'r' : 'l') : p.h; // в хранилище — без зеркала
  return layout[id] = Object.assign({ h, v: p.v, x: p.x, y: p.y, sc: p.sc, o: p.o }, layout[id] || {});
}
function openEditor() {
  edBackup = JSON.parse(JSON.stringify(layout)); edSel = null;
  edEl.classList.toggle('lefty', !!settings.lefty);
  edEl.hidden = false; document.body.classList.add('editing'); exitLock(); edRefresh();
}
function closeEditor(save) {
  if (save) saveLayout(); else if (edBackup) layout = edBackup;
  edBackup = null; edEl.hidden = true; document.body.classList.remove('editing'); applyLayout();
}
edBtns.addEventListener('pointerdown', e => {
  const b = e.target.closest('.tb'); if (!b) { edSel = null; edRefresh(); return; }
  e.preventDefault();
  edSel = b.dataset.id; edRefresh();
  const r = b.getBoundingClientRect();
  edDrag = { id: edSel, pid: e.pointerId, dx: e.clientX - (r.left + r.width / 2), dy: e.clientY - (r.top + r.height / 2) };
  try { edBtns.setPointerCapture(e.pointerId); } catch (err) {}
  edEl.classList.add('dragging');
});
edBtns.addEventListener('pointermove', e => {
  if (!edDrag || e.pointerId !== edDrag.pid) return;
  const S = safeInsets(), W = innerWidth, H = innerHeight;
  const cx = clamp(e.clientX - edDrag.dx, S.l + 16, W - S.r - 16), cy = clamp(e.clientY - edDrag.dy, S.t + 16, H - S.b - 16);
  const ent = edEntry(edDrag.id);
  const hd = cx < W / 2 ? 'l' : 'r';
  ent.h = settings.lefty ? (hd === 'l' ? 'r' : 'l') : hd;
  ent.x = Math.round(hd === 'l' ? cx - S.l : W - S.r - cx);
  ent.v = cy < H / 2 ? 't' : 'b';
  ent.y = Math.round(ent.v === 't' ? cy - S.t : H - S.b - cy);
  placeBtn(edBtn[edDrag.id], TOUCH_BTNS.find(d => d.id === edDrag.id));
});
const edEnd = e => { if (edDrag && e.pointerId === edDrag.pid) { edDrag = null; edEl.classList.remove('dragging'); } };
edBtns.addEventListener('pointerup', edEnd); edBtns.addEventListener('pointercancel', edEnd);
$('#edSize').addEventListener('input', e => { if (!edSel) return; edEntry(edSel).sc = +e.target.value; edRefresh(); });
$('#edOp').addEventListener('input', e => { if (!edSel) return; edEntry(edSel).o = +e.target.value; edRefresh(); });
$('#edReset').addEventListener('click', () => { layout = {}; edRefresh(); });
$('#edCancel').addEventListener('click', () => closeEditor(false));
$('#edSave').addEventListener('click', () => closeEditor(true));

/* ---------------- блокировка сна и скрытие вкладки ---------------- */
let wakeLock = null;
async function requestWake() {
  if (!('wakeLock' in navigator) || wakeLock) return;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
    wakeLock.addEventListener('release', () => { wakeLock = null; });
  } catch (e) { wakeLock = null; } // отказ (нет жеста, энергосбережение) — просто играем без него
}
function releaseWake() { if (wakeLock) { try { wakeLock.release(); } catch (e) {} wakeLock = null; } }
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (inMatch && !paused && state !== 'over') setPause(true);
    releaseTouches();
    try { if (AC && AC.state === 'running') AC.suspend(); } catch (e) {}
  } else {
    try { if (AC && AC.state === 'suspended') AC.resume(); } catch (e) {}
    if (inMatch) requestWake();
  }
});

// витрина в меню: бойцы обеих команд стоят в проходе склада
const SHOW = typeof MENU_SPOT !== 'undefined' ? MENU_SPOT : { x: 40, z: 30, camX: 37.5, camZ: 39 };
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
