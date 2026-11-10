export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }

export function richText(text) {
  let h = esc(text);
  h = h.replace(/\b(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  h = h.replace(/(^|[\s(])@([a-zA-Z][a-zA-Z0-9_]{2,31})\b/g, '$1<a href="#" class="mention" data-mention="$2">@$2</a>');
  h = h.replace(/(^|[\s(])\*\*([^*\n]+)\*\*/g, '$1<b>$2</b>');
  h = h.replace(/(^|[\s(])`([^`\n]+)`/g, '$1<code>$2</code>');
  return h;
}
// A message that is only 1–3 emoji is shown large.
export const onlyEmoji = t => t.length <= 24 && /^(\p{Extended_Pictographic}|\p{Emoji_Component}|‍|️|\s)+$/u.test(t) && !/^[\d#*\s]+$/.test(t);

export function initials(name) {
  const p = String(name || '?').trim().split(/\s+/);
  return ((p[0] || '?')[0] + (p[1] ? p[1][0] : '')).toUpperCase();
}

// ---------- time ----------
const pad = n => String(n).padStart(2, '0');
export const hm = ts => { const d = new Date(ts); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
export const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const WD_FULL = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
export function shortTime(ts) {
  const d = new Date(ts), n = Date.now();
  if (sameDay(ts, n)) return hm(ts);
  if (n - ts < 6 * 864e5) return WD[d.getDay()];
  return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + (d.getFullYear() !== new Date().getFullYear() ? '.' + String(d.getFullYear()).slice(2) : '');
}
export function dayLabel(ts) {
  const d = new Date(ts), n = new Date();
  if (sameDay(ts, n)) return 'Сегодня';
  if (sameDay(ts, Date.now() - 864e5)) return 'Вчера';
  if (Date.now() - ts < 6 * 864e5) return WD_FULL[d.getDay()];
  return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== n.getFullYear() ? ' ' + d.getFullYear() : '');
}
export function seen(u) {
  if (!u) return '';
  if (u.online) return 'на связи';
  if (!u.lastSeen) return 'давно не заходил(а)';
  const diff = Date.now() - u.lastSeen;
  if (diff < 60e3) return 'был(а) только что';
  if (diff < 3600e3) return `был(а) ${Math.floor(diff / 60e3)} мин назад`;
  if (sameDay(u.lastSeen, Date.now())) return 'был(а) в ' + hm(u.lastSeen);
  if (sameDay(u.lastSeen, Date.now() - 864e5)) return 'был(а) вчера в ' + hm(u.lastSeen);
  return 'был(а) ' + dayLabel(u.lastSeen).toLowerCase();
}
export const duration = s => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600); const m = Math.floor(s / 60) % 60; return (h ? h + ':' + pad(m) : m) + ':' + pad(s % 60); };
export function size(b) {
  if (b < 1024) return b + ' Б';
  if (b < 1048576) return (b / 1024).toFixed(0) + ' КБ';
  return (b / 1048576).toFixed(1).replace('.', ',') + ' МБ';
}
export function plural(n, one, few, many) {
  const a = Math.abs(n), m10 = a % 10, m100 = a % 100;
  return n + ' ' + (m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? few : many);
}
export function ttlLabel(s) {
  return { 0: 'Выключено', 30: '30 секунд', 300: '5 минут', 3600: '1 час', 86400: '1 день', 604800: '1 неделя' }[s] || s + ' с';
}
export const ttlShort = s => ({ 30: '30с', 300: '5м', 3600: '1ч', 86400: '1д', 604800: '7д' }[s] || '');

// ---------- toast ----------
let toastTimer;
export function toast(text, kind = '') {
  const t = $('#toast');
  t.textContent = text; t.className = 'toast show ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = 'toast'; }, 2800);
}

export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export const uid = () => crypto.randomUUID();
export const fine = () => matchMedia('(pointer: fine)').matches;

// ---------- icons (24px, stroke) ----------
const P = {
  chats: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="m16 10.5 5-3v9l-5-3z"/>',
  people: '<circle cx="9" cy="8.5" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M18 14.8c2 .7 3.2 2.4 3.5 5.2"/>',
  me: '<circle cx="12" cy="8" r="4"/><path d="M4 20.5c.8-4.2 4-6.5 8-6.5s7.2 2.3 8 6.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  send: '<path d="M4.5 12 20 4.5 15.5 20l-3.2-6.3z"/><path d="m12.3 13.7 3.4-3.4"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
  micOff: '<path d="M15 9.5V6a3 3 0 0 0-5.8-1M9 9v2a3 3 0 0 0 4.6 2.5M5.5 11a6.5 6.5 0 0 0 10.4 5.2M18.5 11a6.5 6.5 0 0 1-.6 2.7M12 17.5V21M3 3l18 18"/>',
  attach: '<path d="m20 11.5-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"/>',
  poll: '<path d="M5 20V10M12 20V4M19 20v-7"/>',
  smile: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14.2c.9 1.2 2 1.8 3.5 1.8s2.6-.6 3.5-1.8"/><path d="M9 9.8h.01M15 9.8h.01" stroke-width="2.6"/>',
  reply: '<path d="M10 8V4.5L3.5 11l6.5 6.5V14c5 0 8 1.4 10.5 5-.8-5.4-3.8-10.3-10.5-11z"/>',
  edit: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  trash: '<path d="M4.5 7h15M10 11v5.5M14 11v5.5M6.5 7l.8 11.2A2 2 0 0 0 9.3 20h5.4a2 2 0 0 0 2-1.8L17.5 7M9 7V4.5h6V7"/>',
  forward: '<path d="M14 8V4.5l6.5 6.5-6.5 6.5V14c-5 0-8 1.4-10.5 5 .8-5.4 3.8-10.3 10.5-11z"/>',
  pin: '<path d="M9 4h6l-1 5 3.5 3.5v1.5h-11v-1.5L10 9z"/><path d="M12 14v6"/>',
  more: '<path d="M5.5 12h.01M12 12h.01M18.5 12h.01" stroke-width="3"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  check: '<path d="M4 12.5 9 17.5 20 6.5"/>',
  checks: '<path d="m2 12.5 5 5L18 6.5M12 16.5l1 1L24 6.5"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
  shield: '<path d="M12 3.5 19 6v5.5c0 4.4-2.9 7.8-7 9-4.1-1.2-7-4.6-7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  timer: '<circle cx="12" cy="13" r="7.5"/><path d="M12 9v4l2.5 1.5M9.5 2.8h5"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8h.01" stroke-width="2.2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5z"/>',
  monitor: '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 16.5V20"/>',
  camOff: '<path d="M3 3l18 18M10 6h4a2.5 2.5 0 0 1 2.5 2.5v2l4.5-3v9l-2-1.3M16 16.5a2.5 2.5 0 0 1-2 1.5H5.5A2.5 2.5 0 0 1 3 15.5v-7A2.5 2.5 0 0 1 5 6"/>',
  hangup: '<path d="M3.3 13.6c-.6-.6-.6-1.6 0-2.2a12.3 12.3 0 0 1 17.4 0c.6.6.6 1.6 0 2.2l-1.9 1.9a1 1 0 0 1-1.3.1l-2.6-1.9a1 1 0 0 1-.4-.8v-2a9 9 0 0 0-5 0v2a1 1 0 0 1-.4.8l-2.6 1.9a1 1 0 0 1-1.3-.1z"/>',
  screen: '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M12 13.5V8M9.5 10.3 12 8l2.5 2.3M8.5 20h7"/>',
  minimize: '<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>',
  expand: '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
  download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
  file: '<path d="M14 3.5H7A2 2 0 0 0 5 5.5v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z"/><path d="M14 3.5v5h5"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/>',
  pause: '<path d="M8 5.5v13M16 5.5v13" stroke-width="3.2"/>',
  down: '<path d="M6 9.5l6 6 6-6"/>',
  logout: '<path d="M14.5 4.5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-3M10 16.5l-4.5-4.5L10 7.5M5.5 12H15"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m20.5 16-4.5-4.5-8.5 8"/>',
  key: '<circle cx="8" cy="15" r="4.5"/><path d="m11.2 11.8 8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2"/>',
  callIn: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1zM20 4l-5 5M15 5v4h4"/>',
  callOut: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1zM15 9l5-5M16 4h4v4"/>',
  callMissed: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1zM15 4l5 5M20 4l-5 5"/>',
  crown: '<path d="m4 8 4 3.5L12 5l4 6.5L20 8l-1.5 10h-13z"/>',
  userPlus: '<circle cx="10" cy="8" r="3.8"/><path d="M3 20c.7-3.9 3.4-6 7-6 1.6 0 3 .4 4.2 1.2M18.5 13v6M15.5 16h6"/>',
  userMinus: '<circle cx="10" cy="8" r="3.8"/><path d="M3 20c.7-3.9 3.4-6 7-6 1.6 0 3 .4 4.2 1.2M15.5 16h6"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15zM10 20.5a2.2 2.2 0 0 0 4 0"/>',
  devices: '<rect x="2.5" y="5" width="13" height="10" rx="1.5"/><path d="M6 19h6M9 15v4"/><rect x="17" y="8" width="5" height="11" rx="1.5"/>',
  sparkle: '<path d="M12 3.5c.6 4.3 2.2 5.9 6.5 6.5-4.3.6-5.9 2.2-6.5 6.5-.6-4.3-2.2-5.9-6.5-6.5 4.3-.6 5.9-2.2 6.5-6.5zM19 15.5c.3 1.9 1 2.6 2.5 3-1.5.3-2.2 1-2.5 3-.3-2-1-2.7-2.5-3 1.5-.4 2.2-1.1 2.5-3z"/>',
  hash: '<path d="M9.5 4 8 20M16 4l-1.5 16M4.5 9h15M4 15h15"/>',
};
export function icon(name, cls = '') {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || ''}</svg>`;
}
