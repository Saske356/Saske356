// Клавиатура, мышь и сенсорные элементы управления.
const keys = new Set();
const joy = { x: 0, y: 0 };
let camDX = 0, camDY = 0, zoom = 0, touchHold = false;
export const handlers = { onKey: null };

export const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;

export function isTyping() {
  const a = document.activeElement;
  return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA');
}

addEventListener('keydown', (e) => {
  if (isTyping()) return;
  if (['Space', 'ArrowUp', 'ArrowDown', 'Tab'].includes(e.code)) e.preventDefault();
  keys.add(e.code);
  if (!e.repeat) handlers.onKey?.(e.code, e);
});
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());

export function readInput() {
  const k = (c) => keys.has(c);
  let x = (k('KeyD') || k('ArrowRight') ? 1 : 0) - (k('KeyA') || k('ArrowLeft') ? 1 : 0);
  let y = (k('KeyW') || k('ArrowUp') ? 1 : 0) - (k('KeyS') || k('ArrowDown') ? 1 : 0);
  if (joy.x || joy.y) { x = joy.x; y = joy.y; }
  return { x, y, sprint: k('ShiftLeft') || k('ShiftRight') || touchHold, brake: k('Space') || touchHold };
}

export function takeCamera() {
  const r = { dx: camDX, dy: camDY, zoom };
  camDX = camDY = zoom = 0;
  return r;
}

export function initPointer(canvas) {
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => {
    if (drag) return;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag || drag.id !== e.pointerId) return;
    const k = e.pointerType === 'touch' ? 1.4 : 1;
    camDX += (e.clientX - drag.x) * k; camDY += (e.clientY - drag.y) * k;
    drag.x = e.clientX; drag.y = e.clientY;
  });
  const end = (e) => { if (drag && drag.id === e.pointerId) drag = null; };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('wheel', (e) => { zoom += Math.sign(e.deltaY); e.preventDefault(); }, { passive: false });
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());
}

export function initTouch(root) {
  root.hidden = false;
  const zone = root.querySelector('#joyzone'), knob = root.querySelector('#knob'), base = root.querySelector('#joybase');
  let id = null, cx = 0, cy = 0;
  const R = 55;
  zone.addEventListener('pointerdown', (e) => {
    id = e.pointerId; zone.setPointerCapture(id);
    const r = base.getBoundingClientRect();
    cx = r.left + r.width / 2; cy = r.top + r.height / 2;
    move(e);
  });
  const move = (e) => {
    if (e.pointerId !== id) return;
    let dx = e.clientX - cx, dy = e.clientY - cy;
    const l = Math.hypot(dx, dy);
    if (l > R) { dx = (dx / l) * R; dy = (dy / l) * R; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    joy.x = dx / R; joy.y = -dy / R;
    if (Math.abs(joy.x) < 0.12) joy.x = 0;
    if (Math.abs(joy.y) < 0.12) joy.y = 0;
  };
  const end = (e) => {
    if (e.pointerId !== id) return;
    id = null; joy.x = joy.y = 0; knob.style.transform = '';
  };
  zone.addEventListener('pointermove', move);
  zone.addEventListener('pointerup', end);
  zone.addEventListener('pointercancel', end);
  for (const b of root.querySelectorAll('[data-key]')) {
    b.addEventListener('pointerdown', (e) => { e.preventDefault(); handlers.onKey?.(b.dataset.key); });
  }
  const hold = root.querySelector('#holdbtn');
  hold.addEventListener('pointerdown', (e) => { e.preventDefault(); touchHold = true; });
  for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) hold.addEventListener(ev, () => { touchHold = false; });
}
