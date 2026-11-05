'use strict';
const $ = s => document.querySelector(s);
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = arr => arr[Math.random() * arr.length | 0];
const angDiff = (a, b) => { let d = a - b; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return d; };
const yawTo = (ax, az, bx, bz) => Math.atan2(-(bx - ax), -(bz - az));
const isTouch = matchMedia('(pointer: coarse)').matches || ('ontouchstart' in window && navigator.maxTouchPoints > 0);

/* ---------------- хранилище (localStorage может быть недоступен) ---------------- */
const store = {
  get(key, def) { try { const v = localStorage.getItem(key); return v == null ? def : JSON.parse(v); } catch (e) { return def; } },
  set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} },
  del(key) { try { localStorage.removeItem(key); } catch (e) {} },
};

/* ---------------- настройки ---------------- */
// gfx: 'low' | 'medium' | 'high' — общий уровень графики (читает карта/рендер; после смены — bus.emit('settings:gfx', gfx)).
// shadows — тени (читает карта). quality — потолок pixelRatio. dynRes — динамическое разрешение. fpsCap — 30 | 60 | 0 (без ограничения).
const GFX_PRESETS = {
  low:    { quality: 0.75, shadows: false },
  medium: { quality: 1,    shadows: false },
  high:   { quality: 1.5,  shadows: true },
};
const SETTINGS_DEFAULT = {
  sens: 1, adsSens: 0.7, accel: 0, fov: 74, invertY: false,
  sound: 1, volume: 0.7,
  gfx: isTouch ? 'medium' : 'high', quality: isTouch ? 1 : 1.5, shadows: !isTouch, dynRes: true, fpsCap: 60, showFps: false,
  autoFire: false, lefty: false, crouchHold: false, radarRotate: true,
  diff: 1, mode: 'comp',
};
const settings = Object.assign({}, SETTINGS_DEFAULT);
Object.assign(settings, store.get('blokpost-settings', {}) || {});
if (!GFX_PRESETS[settings.gfx]) settings.gfx = SETTINGS_DEFAULT.gfx;
const saveSettings = () => store.set('blokpost-settings', settings);


/* ---------------- общая шина событий и утилиты для модулей ---------------- */
// bus.on('action:knife', fn); bus.emit('action:knife'). Так модули общаются без прямых зависимостей.
const bus = {
  _h: {},
  on(name, fn) { (this._h[name] || (this._h[name] = [])).push(fn); },
  off(name, fn) { const l = this._h[name]; if (l) { const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); } },
  has(name) { const l = this._h[name]; return !!(l && l.length); },
  emit(name, ...args) { const l = this._h[name]; if (l) for (const f of l.slice()) { try { f(...args); } catch (e) { console.error(e); } } },
};
// Каждый модуль добавляет свои стили сам, не трогая index.html
function injectCSS(id, css) {
  let el = document.getElementById('css-' + id);
  if (!el) { el = document.createElement('style'); el.id = 'css-' + id; document.head.appendChild(el); }
  el.textContent = css;
}
// Экранирование текста для HTML-шаблонов
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
