'use strict';
const $ = s => document.querySelector(s);
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = arr => arr[Math.random() * arr.length | 0];
const angDiff = (a, b) => { let d = a - b; while (d > Math.PI) d -= Math.PI * 2; while (d < -Math.PI) d += Math.PI * 2; return d; };
const yawTo = (ax, az, bx, bz) => Math.atan2(-(bx - ax), -(bz - az));
const isTouch = matchMedia('(pointer: coarse)').matches || ('ontouchstart' in window && navigator.maxTouchPoints > 0);

/* ---------------- настройки ---------------- */
const settings = { sens: 1, sound: 1, quality: isTouch ? 1 : 1.5, diff: 1, mode: 'comp' };
try { Object.assign(settings, JSON.parse(localStorage.getItem('blokpost-settings') || '{}')); } catch (e) {}
const saveSettings = () => { try { localStorage.setItem('blokpost-settings', JSON.stringify(settings)); } catch (e) {} };


/* ---------------- общая шина событий и утилиты для модулей ---------------- */
// bus.on('action:knife', fn); bus.emit('action:knife'). Так модули общаются без прямых зависимостей.
const bus = {
  _h: {},
  on(name, fn) { (this._h[name] || (this._h[name] = [])).push(fn); },
  emit(name, ...args) { const l = this._h[name]; if (l) for (const f of l) { try { f(...args); } catch (e) { console.error(e); } } },
};
// Каждый модуль добавляет свои стили сам, не трогая index.html
function injectCSS(id, css) {
  let el = document.getElementById('css-' + id);
  if (!el) { el = document.createElement('style'); el.id = 'css-' + id; document.head.appendChild(el); }
  el.textContent = css;
}
