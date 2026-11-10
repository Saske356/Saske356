'use strict';
// ================= state =================
const $ = s => document.querySelector(s);
const S = {
  token: localStorage.getItem('tg_token'),
  me: null, users: {}, chats: {}, msgs: {}, hasMore: {}, loaded: {},
  current: null, typing: {}, reply: null, edit: null, query: '', globalResults: [],
};
let ws = null, reqSeq = 0, pending = new Map(), retry = 0, lastTypingSent = 0;

const ICON = {
  saved: '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
  group: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-7 7-7s7 3 7 7M17 11a3 3 0 1 0 0-6M22 21c0-3-2-5.5-5-6"/></svg>',
  check: '<svg viewBox="0 0 24 18"><path d="M3 9.5 8 14 19 3"/></svg>',
  checks: '<svg viewBox="0 0 24 18"><path d="M1 9.5 6 14 17 3M9 12.5l1.5 1.5L22 3"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M14 3H6v18h12V7zM14 3v4h4"/></svg>',
  reply: '<svg viewBox="0 0 24 24"><path d="M10 9V5l-7 7 7 7v-4c5 0 8.5 1.5 11 5-1-5-4-10-11-11z"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4"/></svg>',
  copy: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  ok: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>',
  forward: '<svg viewBox="0 0 24 24"><path d="M14 9V5l7 7-7 7v-4c-5 0-8.5 1.5-11 5 1-5 4-10 11-11z"/></svg>',
};

// ================= utils =================
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function linkify(text) {
  return esc(text).replace(/\b(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')
                  .replace(/(^|\s)@([a-zA-Z][a-zA-Z0-9_]{2,31})\b/g, '$1<a href="#" data-mention="$2">@$2</a>');
}
function initials(name) {
  const p = String(name || '?').trim().split(/\s+/);
  return ((p[0] || '?')[0] + (p[1] ? p[1][0] : '')).toUpperCase();
}
const pad = n => String(n).padStart(2, '0');
const hm = ts => { const d = new Date(ts); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
function listTime(ts) {
  const d = new Date(ts), now = Date.now();
  if (sameDay(ts, now)) return hm(ts);
  if (now - ts < 6 * 864e5) return WD[d.getDay()];
  return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + String(d.getFullYear()).slice(2);
}
function dayLabel(ts) {
  const d = new Date(ts), now = new Date();
  if (sameDay(ts, now)) return 'Сегодня';
  if (sameDay(ts, Date.now() - 864e5)) return 'Вчера';
  return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== now.getFullYear() ? ' ' + d.getFullYear() : '');
}
function lastSeen(u) {
  if (u.online) return 'в сети';
  if (!u.lastSeen) return 'был(а) недавно';
  const diff = Date.now() - u.lastSeen;
  if (diff < 60e3) return 'был(а) только что';
  if (diff < 3600e3) return `был(а) ${Math.floor(diff / 60e3)} мин. назад`;
  if (sameDay(u.lastSeen, Date.now())) return 'был(а) в ' + hm(u.lastSeen);
  if (sameDay(u.lastSeen, Date.now() - 864e5)) return 'был(а) вчера в ' + hm(u.lastSeen);
  return 'был(а) ' + dayLabel(u.lastSeen);
}
function fmtSize(b) {
  if (b < 1024) return b + ' Б';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' КБ';
  return (b / 1048576).toFixed(1) + ' МБ';
}
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  return n + ' ' + (m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? few : many);
}
let toastTimer;
function toast(text) {
  const t = $('#toast'); t.textContent = text; t.classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), 2500);
}
function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }

// ================= chat helpers =================
function chatTitle(c) {
  if (c.type === 'saved') return 'Избранное';
  if (c.type === 'group') return c.title;
  const o = S.users[peerId(c)]; return o ? o.name : 'Пользователь';
}
function peerId(c) { return c.members.find(m => m !== S.me.id) ?? S.me.id; }
function avatarHtml(c, extraClass = '') {
  if (c.type === 'saved') return `<div class="avatar ${extraClass}" style="--c:#65aadd">${ICON.saved}</div>`;
  if (c.type === 'group') return `<div class="avatar ${extraClass}" style="--c:${c.color || '#7bc862'}">${esc(initials(c.title))}</div>`;
  const u = S.users[peerId(c)] || {};
  return userAvatar(u, extraClass);
}
function userAvatar(u, extraClass = '') {
  return `<div class="avatar ${extraClass} ${u.online ? 'online' : ''}" style="--c:${u.color || '#65aadd'}">${esc(initials(u.name))}</div>`;
}
function previewText(m) {
  if (!m) return '';
  if (m.file) {
    const kind = m.file.type.startsWith('image/') ? '🖼 Фото' : m.file.type.startsWith('video/') ? '🎬 Видео' : m.file.type.startsWith('audio/') ? '🎵 Аудио' : '📎 ' + m.file.name;
    return m.text ? kind + ', ' + m.text : kind;
  }
  return m.text;
}
function isReadByOthers(c, m) {
  return c.members.some(id => id !== S.me.id && (c.reads[id] || 0) >= m.id);
}
function typingUsers(chatId) { return Object.keys(S.typing[chatId] || {}).map(Number); }
function typingText(c) {
  const ids = typingUsers(c.id);
  if (!ids.length) return '';
  if (c.type !== 'group') return 'печатает…';
  const names = ids.map(id => (S.users[id] || {}).name || '').filter(Boolean);
  return names.length === 1 ? names[0] + ' печатает…' : plural(names.length, 'человек', 'человека', 'человек') + ' печатают…';
}
function chatStatus(c) {
  const t = typingText(c);
  if (t) return { text: t, on: true };
  if (c.type === 'saved') return { text: '' };
  if (c.type === 'group') {
    const online = c.members.filter(id => S.users[id]?.online).length;
    return { text: plural(c.members.length, 'участник', 'участника', 'участников') + (online > 1 ? `, ${online} в сети` : '') };
  }
  const u = S.users[peerId(c)];
  return { text: u ? lastSeen(u) : '', on: u?.online };
}

// ================= network =================
async function http(path, body) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Ошибка сервера');
  return data;
}
function rpc(type, data = {}) {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== 1) return reject(new Error('Нет соединения'));
    const reqId = ++reqSeq;
    pending.set(reqId, { resolve, reject });
    ws.send(JSON.stringify({ type, reqId, ...data }));
    setTimeout(() => { if (pending.delete(reqId)) reject(new Error('Таймаут')); }, 15000);
  });
}
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${S.token}`);
  ws.onopen = () => { retry = 0; $('#conn').classList.add('hidden'); };
  ws.onmessage = e => handle(JSON.parse(e.data));
  ws.onclose = e => {
    for (const p of pending.values()) p.reject(new Error('Соединение потеряно'));
    pending.clear();
    if (e.code === 4001) return logout(true);
    $('#conn').classList.remove('hidden');
    setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
  };
}

function handle(evt) {
  switch (evt.type) {
    case 'reply': {
      const p = pending.get(evt.reqId); if (!p) return;
      pending.delete(evt.reqId);
      evt.ok ? p.resolve(evt.data) : p.reject(new Error(evt.error));
      return;
    }
    case 'init': {
      S.me = evt.me;
      for (const u of evt.users) S.users[u.id] = u;
      S.chats = {};
      for (const c of evt.chats) S.chats[c.id] = c;
      // reload messages for open chats after reconnect
      S.msgs = {}; S.loaded = {}; S.hasMore = {};
      showApp();
      renderList();
      if (S.current && S.chats[S.current]) openChat(S.current, true);
      else if (S.current) closeChat();
      return;
    }
    case 'chat': {
      for (const u of evt.users) S.users[u.id] = u;
      S.chats[evt.chat.id] = evt.chat;
      renderList();
      if (S.current === evt.chat.id) renderHeader();
      return;
    }
    case 'chatRemoved': {
      delete S.chats[evt.chatId]; delete S.msgs[evt.chatId];
      if (S.current === evt.chatId) closeChat();
      renderList();
      return;
    }
    case 'message': {
      const m = evt.message, c = S.chats[m.chatId];
      if (!c) return;
      if (S.msgs[m.chatId] && !S.msgs[m.chatId].some(x => x.id === m.id)) S.msgs[m.chatId].push(m);
      c.lastMessage = m;
      if (S.typing[m.chatId]) delete S.typing[m.chatId][m.from];
      const visible = S.current === m.chatId && !document.hidden;
      if (m.from !== S.me.id && !m.service) {
        if (!visible || !atBottom()) c.unread = (c.unread || 0) + 1;
        if (!visible) notify(c, m);
      }
      renderList();
      if (S.current === m.chatId) {
        const stick = atBottom() || m.from === S.me.id;
        renderMessages();
        if (stick) scrollBottom(); else updateToBottom();
        markRead();
        renderHeader();
      }
      return;
    }
    case 'edited': {
      const list = S.msgs[evt.message.chatId];
      if (list) { const i = list.findIndex(x => x.id === evt.message.id); if (i >= 0) list[i] = evt.message; }
      const c = S.chats[evt.message.chatId];
      if (c?.lastMessage?.id === evt.message.id) c.lastMessage = evt.message;
      renderList();
      if (S.current === evt.message.chatId) renderMessages(true);
      return;
    }
    case 'deleted': {
      const list = S.msgs[evt.chatId];
      if (list) S.msgs[evt.chatId] = list.filter(x => x.id !== evt.id);
      const c = S.chats[evt.chatId];
      if (c) c.lastMessage = evt.lastMessage;
      if (S.reply?.id === evt.id) setCtx(null);
      renderList();
      if (S.current === evt.chatId) renderMessages(true);
      return;
    }
    case 'read': {
      const c = S.chats[evt.chatId]; if (!c) return;
      c.reads[evt.userId] = Math.max(c.reads[evt.userId] || 0, evt.msgId);
      if (evt.userId === S.me.id) {
        const list = S.msgs[c.id];
        c.unread = list ? list.filter(m => m.id > evt.msgId && m.from !== S.me.id && !m.service).length
                        : (c.lastMessage && c.lastMessage.id > evt.msgId ? c.unread : 0);
      }
      renderList();
      if (S.current === evt.chatId) renderMessages(true);
      return;
    }
    case 'typing': {
      const t = S.typing[evt.chatId] = S.typing[evt.chatId] || {};
      clearTimeout(t[evt.userId]);
      t[evt.userId] = setTimeout(() => { delete t[evt.userId]; renderList(); if (S.current === evt.chatId) renderHeader(); }, 5000);
      renderList();
      if (S.current === evt.chatId) renderHeader();
      return;
    }
    case 'presence': {
      const u = S.users[evt.userId]; if (!u) return;
      u.online = evt.online; u.lastSeen = evt.lastSeen;
      renderList(); if (S.current) renderHeader();
      return;
    }
    case 'user': {
      S.users[evt.user.id] = evt.user;
      if (evt.user.id === S.me.id) S.me = evt.user;
      renderList(); if (S.current) { renderHeader(); renderMessages(true); }
      return;
    }
  }
}

// ================= auth =================
let authMode = 'login';
function showAuth() {
  $('#auth').classList.remove('hidden'); $('#app').classList.add('hidden');
}
function showApp() {
  $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden');
}
document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  authMode = t.dataset.tab;
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === t));
  document.querySelector('.reg-only').classList.toggle('hidden', authMode !== 'register');
  $('#authSubmit').textContent = authMode === 'login' ? 'Войти' : 'Создать аккаунт';
  $('#authHint').textContent = authMode === 'login' ? 'Войдите, чтобы продолжить' : 'Создайте новый аккаунт';
  $('#authForm').elements['password'].autocomplete = authMode === 'login' ? 'current-password' : 'new-password';
  $('#authError').textContent = '';
});
$('#authForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.target, btn = $('#authSubmit');
  btn.disabled = true; $('#authError').textContent = '';
  try {
    const data = await http('/api/' + authMode, { username: f.username.value, password: f.password.value, name: f.elements['name'].value });
    S.token = data.token; localStorage.setItem('tg_token', S.token);
    f.reset();
    connect();
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
  } catch (err) { $('#authError').textContent = err.message; }
  btn.disabled = false;
};
function logout(silent) {
  if (!silent && S.token) fetch('/api/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + S.token } });
  localStorage.removeItem('tg_token');
  S.token = null; S.me = null; S.chats = {}; S.msgs = {}; S.users = {}; S.current = null;
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  $('#app').classList.remove('in-chat');
  showAuth();
}

// ================= chat list =================
function sortedChats() {
  return Object.values(S.chats).sort((a, b) => (b.lastMessage?.ts || b.createdAt) - (a.lastMessage?.ts || a.createdAt));
}
function chatItemHtml(c) {
  const m = c.lastMessage, typing = typingText(c);
  let text;
  if (typing) text = `<span class="ci-typing">${esc(typing)}</span>`;
  else if (!m) text = c.type === 'saved' ? 'Пересылайте сюда сообщения и заметки' : 'Нет сообщений';
  else {
    let sender = '';
    if (!m.service) {
      if (m.from === S.me.id && c.type !== 'saved') sender = 'Вы: ';
      else if (c.type === 'group') sender = (S.users[m.from]?.name || '') + ': ';
    }
    text = (sender ? `<span class="ci-sender">${esc(sender)}</span>` : '') + esc(previewText(m));
  }
  let right = '';
  if (c.unread > 0) right = `<span class="badge on">${c.unread > 999 ? '999+' : c.unread}</span>`;
  const ticks = m && m.from === S.me.id && !m.service && c.type !== 'saved'
    ? `<span class="ticks">${isReadByOthers(c, m) ? '✓✓' : '✓'}</span>` : '';
  return `<div class="chat-item ${S.current === c.id ? 'active' : ''}" data-chat="${c.id}">
    ${avatarHtml(c)}
    <div class="ci-body">
      <div class="ci-row"><div class="ci-title">${esc(chatTitle(c))}</div>${ticks}<span class="ci-time">${m ? listTime(m.ts) : ''}</span></div>
      <div class="ci-row"><div class="ci-text">${text}</div>${right}</div>
    </div></div>`;
}
function renderList() {
  if (!S.me) return;
  const q = S.query.trim().toLowerCase();
  let html = '';
  let chats = sortedChats();
  if (q) chats = chats.filter(c => chatTitle(c).toLowerCase().includes(q) ||
    (c.type === 'private' && (S.users[peerId(c)]?.username || '').toLowerCase().includes(q.replace(/^@/, ''))));
  if (q && chats.length) html += '<div class="section-title">Чаты</div>';
  html += chats.map(chatItemHtml).join('');
  if (q) {
    const known = new Set(Object.values(S.chats).filter(c => c.type === 'private').map(peerId));
    const glob = S.globalResults.filter(u => !known.has(u.id));
    if (glob.length) {
      html += '<div class="section-title">Глобальный поиск</div>' + glob.map(u => `
        <div class="chat-item" data-user="${u.id}">${userAvatar(u)}
          <div class="ci-body"><div class="ci-row"><div class="ci-title">${esc(u.name)}</div></div>
          <div class="ci-row"><div class="ci-text">@${esc(u.username)}</div></div></div></div>`).join('');
    }
    if (!chats.length && !glob.length) html = '<div class="list-empty">Ничего не найдено</div>';
  } else if (!chats.length) html = '<div class="list-empty">Пока нет чатов</div>';
  $('#chatList').innerHTML = html;
  updateTitle();
}
$('#chatList').onclick = async e => {
  const item = e.target.closest('.chat-item'); if (!item) return;
  if (item.dataset.chat) return openChat(Number(item.dataset.chat));
  if (item.dataset.user) openPrivate(Number(item.dataset.user));
};
async function openPrivate(userId) {
  try {
    const id = await rpc('openPrivate', { userId });
    $('#search').value = ''; S.query = ''; S.globalResults = [];
    await waitForChat(id);
    openChat(id);
  } catch (err) { toast(err.message); }
}
function waitForChat(id) {
  return new Promise(res => {
    const t0 = Date.now();
    (function check() { if (S.chats[id] || Date.now() - t0 > 3000) res(); else setTimeout(check, 30); })();
  });
}
let searchTimer;
$('#search').oninput = e => {
  S.query = e.target.value;
  renderList();
  clearTimeout(searchTimer);
  const q = S.query.trim();
  if (!q) { S.globalResults = []; return; }
  searchTimer = setTimeout(async () => {
    try { S.globalResults = await rpc('searchUsers', { q }); if (S.query.trim() === q) renderList(); } catch {}
  }, 250);
};
$('#search').onkeydown = e => { if (e.key === 'Escape') { e.target.value = ''; S.query = ''; S.globalResults = []; renderList(); e.target.blur(); } };

// ================= menu =================
$('#menuBtn').onclick = e => {
  e.stopPropagation();
  const m = $('#menu');
  $('#menuMe').innerHTML = `${userAvatar(S.me)}<div><b>${esc(S.me.name)}</b><div class="muted">@${esc(S.me.username)}</div></div>`;
  m.classList.toggle('hidden');
};
$('#menu').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  $('#menu').classList.add('hidden');
  const act = b.dataset.act;
  if (act === 'saved') { const c = Object.values(S.chats).find(c => c.type === 'saved'); if (c) openChat(c.id); }
  if (act === 'group') groupModal();
  if (act === 'profile') profileModal();
  if (act === 'theme') toggleTheme();
  if (act === 'logout') logout();
};
$('#fab').onclick = () => groupModal();
document.addEventListener('click', e => {
  if (!e.target.closest('#menu')) $('#menu').classList.add('hidden');
  if (!e.target.closest('#ctxMenu')) $('#ctxMenu').classList.add('hidden');
});
function applyTheme(t) { document.documentElement.dataset.theme = t; document.querySelector('meta[name=theme-color]').content = t === 'dark' ? '#212121' : '#517da2'; }
function toggleTheme() {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('tg_theme', t); applyTheme(t);
}
applyTheme(localStorage.getItem('tg_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

// ================= open chat =================
async function openChat(id, force) {
  if (S.current === id && !force) return;
  if (S.current !== id) { setCtx(null); $('#input').value = drafts[id] || ''; autoGrow(); }
  S.current = id;
  $('#emptyChat').classList.add('hidden');
  $('#chatInner').classList.remove('hidden');
  $('#app').classList.add('in-chat');
  renderList(); renderHeader();
  if (!S.loaded[id]) {
    $('#messages').innerHTML = '';
    try {
      const r = await rpc('history', { chatId: id });
      S.msgs[id] = r.messages; S.hasMore[id] = r.hasMore; S.loaded[id] = true;
    } catch (err) { return toast(err.message); }
  }
  if (S.current !== id) return;
  renderMessages();
  scrollToFirstUnread();
  markRead();
  if (matchMedia('(min-width: 761px)').matches) $('#input').focus();
}
function closeChat() {
  S.current = null; setCtx(null);
  $('#chatInner').classList.add('hidden');
  $('#emptyChat').classList.remove('hidden');
  $('#app').classList.remove('in-chat');
  renderList();
}
$('#backBtn').onclick = closeChat;
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (!$('#lightbox').classList.contains('hidden')) return $('#lightbox').classList.add('hidden');
  if (!$('#modalBack').classList.contains('hidden')) return closeModal();
  if (S.reply || S.edit) return setCtx(null);
  if (S.current && document.activeElement !== $('#search')) closeChat();
});

function renderHeader() {
  const c = S.chats[S.current]; if (!c) return;
  $('#chatAvatar').outerHTML = avatarHtml(c).replace('class="avatar', 'id="chatAvatar" class="avatar');
  $('#chatTitle').textContent = chatTitle(c);
  const st = chatStatus(c);
  $('#chatStatus').textContent = st.text;
  $('#chatStatus').classList.toggle('on', !!st.on);
}
$('#chatHeadInfo').onclick = () => chatInfoModal(S.chats[S.current]);

// ================= messages =================
const box = $('#messages');
function atBottom() { return box.scrollHeight - box.scrollTop - box.clientHeight < 80; }
function scrollBottom() { box.scrollTop = box.scrollHeight; updateToBottom(); }
function scrollToFirstUnread() {
  const c = S.chats[S.current];
  const my = c.reads[S.me.id] || 0;
  const first = (S.msgs[c.id] || []).find(m => m.id > my && m.from !== S.me.id);
  const node = first && box.querySelector(`[data-id="${first.id}"]`);
  if (node) node.scrollIntoView({ block: 'center' }); else scrollBottom();
  updateToBottom();
}
function updateToBottom() {
  const c = S.chats[S.current];
  $('#toBottom').classList.toggle('hidden', atBottom());
  const b = $('#toBottomBadge');
  b.textContent = c?.unread || '';
  b.classList.toggle('hidden', !c?.unread);
}
$('#toBottom').onclick = () => { box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' }); };
box.addEventListener('scroll', () => {
  updateToBottom();
  if (atBottom()) markRead();
  if (box.scrollTop < 120) loadMore();
});

function renderMessages(keepScroll) {
  const c = S.chats[S.current]; if (!c) return;
  const list = S.msgs[c.id] || [];
  const prevBottom = box.scrollHeight - box.scrollTop;
  const group = c.type === 'group';
  let html = S.hasMore[c.id] ? '<button class="btn ghost load-more" id="loadMore">Загрузить ещё</button>' : '';
  if (!list.length) html += `<div class="empty"><div class="pill">${c.type === 'saved' ? 'Сохраняйте сюда заметки, ссылки и файлы' : 'Сообщений пока нет. Напишите первым!'}</div></div>`;
  for (let i = 0; i < list.length; i++) {
    const m = list[i], prev = list[i - 1], next = list[i + 1];
    if (!prev || !sameDay(prev.ts, m.ts)) html += `<div class="day"><span>${dayLabel(m.ts)}</span></div>`;
    if (m.service) { html += `<div class="service" data-id="${m.id}"><span>${esc(m.text)}</span></div>`; continue; }
    const out = m.from === S.me.id;
    const first = !prev || prev.from !== m.from || prev.service || !sameDay(prev.ts, m.ts) || m.ts - prev.ts > 300e3;
    const last = !next || next.from !== m.from || next.service || !sameDay(next.ts, m.ts) || next.ts - m.ts > 300e3;
    const u = S.users[m.from] || { name: 'Удалённый', color: '#999' };
    let inner = '';
    if (group && !out && first) inner += `<div class="sender" style="--c:${u.color}">${esc(u.name)}</div>`;
    if (m.replyTo) {
      const r = list.find(x => x.id === m.replyTo);
      inner += `<div class="reply" data-goto="${m.replyTo}"><div class="reply-name">${esc(r ? (S.users[r.from]?.name || '') : '')}</div>
        <div class="reply-text">${esc(r ? previewText(r) : 'Сообщение')}</div></div>`;
    }
    if (m.file) inner += fileHtml(m.file);
    if (m.text) inner += `<span class="text">${linkify(m.text)}</span>`;
    let state = '';
    if (out && c.type !== 'saved') state = m.pending ? ICON.clock : isReadByOthers(c, m) ? ICON.checks : ICON.check;
    inner += `<span class="meta">${m.edited ? 'изм. ' : ''}${hm(m.ts)}${state}</span>`;
    const av = group && !out ? (last ? userAvatar(u) : '<div class="avatar-gap"></div>') : '';
    html += `<div class="row ${out ? 'out' : 'in'} ${last ? 'last' : ''}" data-id="${m.id}">${av}<div class="msg">${inner}</div></div>`;
  }
  box.innerHTML = html;
  const lm = $('#loadMore'); if (lm) lm.onclick = loadMore;
  if (keepScroll) box.scrollTop = box.scrollHeight - prevBottom;
}
function fileHtml(f) {
  const url = esc(f.url);
  if (f.type.startsWith('image/') && !f.type.includes('svg')) return `<img class="media" src="${url}" alt="${esc(f.name)}" loading="lazy" data-zoom>`;
  if (f.type.startsWith('video/')) return `<video class="media" src="${url}" controls preload="metadata"></video>`;
  if (f.type.startsWith('audio/')) return `<audio class="media" src="${url}" controls preload="metadata"></audio>`;
  return `<a class="file" href="${url}" download="${esc(f.name)}"><div class="file-icon">${ICON.file}</div>
    <div><div class="file-name">${esc(f.name)}</div><div class="file-size">${fmtSize(f.size)}</div></div></a>`;
}
let loadingMore = false;
async function loadMore() {
  const id = S.current;
  if (!id || loadingMore || !S.hasMore[id]) return;
  loadingMore = true;
  try {
    const first = S.msgs[id][0];
    const r = await rpc('history', { chatId: id, before: first ? first.id : undefined });
    S.msgs[id] = [...r.messages, ...S.msgs[id]];
    S.hasMore[id] = r.hasMore;
    if (S.current === id) renderMessages(true);
  } catch {}
  loadingMore = false;
}
function markRead() {
  const c = S.chats[S.current];
  if (!c || document.hidden || !atBottom()) return;
  const list = S.msgs[c.id]; if (!list || !list.length) return;
  const lastId = list[list.length - 1].id;
  if ((c.reads[S.me.id] || 0) >= lastId) { if (c.unread) { c.unread = 0; renderList(); } return; }
  c.reads[S.me.id] = lastId; c.unread = 0;
  rpc('read', { chatId: c.id, msgId: lastId }).catch(() => {});
  renderList(); updateToBottom();
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) markRead(); });

box.addEventListener('click', e => {
  const a = e.target.closest('[data-mention]');
  if (a) {
    e.preventDefault();
    rpc('searchUsers', { q: a.dataset.mention }).then(r => {
      const u = r.find(x => x.username.toLowerCase() === a.dataset.mention.toLowerCase());
      if (u) userModal(u); else if (a.dataset.mention.toLowerCase() === S.me.username.toLowerCase()) profileModal(); else toast('Пользователь не найден');
    }).catch(err => toast(err.message));
    return;
  }
  const img = e.target.closest('[data-zoom]');
  if (img) { $('#lightboxImg').src = img.src; $('#lightbox').classList.remove('hidden'); return; }
  const g = e.target.closest('[data-goto]');
  if (g) { const n = box.querySelector(`.row[data-id="${g.dataset.goto}"] .msg`); if (n) { n.scrollIntoView({ block: 'center', behavior: 'smooth' }); n.classList.remove('flash'); void n.offsetWidth; n.classList.add('flash'); } return; }
  const av = e.target.closest('.row .avatar');
  if (av) { const id = Number(av.closest('.row').dataset.id); const m = S.msgs[S.current].find(x => x.id === id); if (m) userModal(S.users[m.from]); }
});
box.addEventListener('dblclick', e => { const row = e.target.closest('.row'); if (row && !e.target.closest('a,video,audio')) startReply(Number(row.dataset.id)); });
$('#lightbox').onclick = () => $('#lightbox').classList.add('hidden');

// ----- context menu -----
box.addEventListener('contextmenu', e => {
  const row = e.target.closest('.row'); if (!row) return;
  e.preventDefault();
  showMsgMenu(Number(row.dataset.id), e.clientX, e.clientY);
});
let pressTimer;
box.addEventListener('touchstart', e => {
  const row = e.target.closest('.row'); if (!row) return;
  const t = e.touches[0];
  pressTimer = setTimeout(() => showMsgMenu(Number(row.dataset.id), t.clientX, t.clientY), 500);
}, { passive: true });
['touchend', 'touchmove', 'touchcancel'].forEach(ev => box.addEventListener(ev, () => clearTimeout(pressTimer), { passive: true }));

function showMsgMenu(id, x, y) {
  const c = S.chats[S.current], m = (S.msgs[c.id] || []).find(z => z.id === id);
  if (!m || m.pending) return;
  const own = m.from === S.me.id;
  const items = [['reply', 'Ответить', ICON.reply]];
  if (own && !m.service) items.push(['edit', 'Изменить', ICON.edit]);
  if (m.text) items.push(['copy', 'Копировать текст', ICON.copy]);
  items.push(['forward', 'Переслать', ICON.forward]);
  if (own || (c.type === 'group' && c.ownerId === S.me.id)) items.push(['delete', 'Удалить', ICON.trash, 'danger']);
  const menu = $('#ctxMenu');
  menu.innerHTML = items.map(([a, t, i, cls]) => `<button data-a="${a}" class="${cls || ''}">${i}${t}</button>`).join('');
  menu.classList.remove('hidden');
  const r = menu.getBoundingClientRect();
  menu.style.left = Math.min(x, innerWidth - r.width - 8) + 'px';
  menu.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
  menu.onclick = ev => {
    const b = ev.target.closest('button'); if (!b) return;
    menu.classList.add('hidden');
    const a = b.dataset.a;
    if (a === 'reply') startReply(id);
    if (a === 'edit') startEdit(id);
    if (a === 'copy') navigator.clipboard?.writeText(m.text).then(() => toast('Текст скопирован'));
    if (a === 'forward') forwardModal(m);
    if (a === 'delete') confirmModal('Удалить сообщение?', 'Сообщение будет удалено у всех участников чата.', 'Удалить',
      () => rpc('delete', { chatId: c.id, id }).catch(err => toast(err.message)));
  };
}

// ================= composer =================
const input = $('#input');
const drafts = {};
function autoGrow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 200) + 'px'; }
input.addEventListener('input', () => {
  autoGrow();
  if (S.current) drafts[S.current] = input.value;
  if (S.current && !S.edit && Date.now() - lastTypingSent > 3000 && input.value.trim()) {
    lastTypingSent = Date.now(); rpc('typing', { chatId: S.current }).catch(() => {});
  }
});
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && matchMedia('(pointer: fine)').matches) { e.preventDefault(); submit(); }
  if (e.key === 'ArrowUp' && !input.value) {
    const list = S.msgs[S.current] || [];
    const mine = [...list].reverse().find(m => m.from === S.me.id && !m.service);
    if (mine) { e.preventDefault(); startEdit(mine.id); }
  }
});
$('#sendBtn').onclick = () => submit();

async function submit(file) {
  const chatId = S.current; if (!chatId) return;
  const text = input.value.trim();
  if (S.edit) {
    const id = S.edit.id;
    if (!text && !S.edit.file) return;
    setCtx(null); input.value = ''; drafts[chatId] = ''; autoGrow();
    return rpc('edit', { chatId, id, text }).catch(err => toast(err.message));
  }
  if (!text && !file) return;
  const replyTo = S.reply?.id;
  const temp = { id: 'tmp' + Date.now(), chatId, from: S.me.id, text, ts: Date.now(), pending: true, replyTo, file };
  S.msgs[chatId] = S.msgs[chatId] || [];
  S.msgs[chatId].push(temp);
  input.value = ''; drafts[chatId] = ''; autoGrow(); setCtx(null); lastTypingSent = 0;
  renderMessages(); scrollBottom();
  try {
    await rpc('send', { chatId, text, replyTo, file });
  } catch (err) { toast(err.message); input.value = text; autoGrow(); }
  const list = S.msgs[chatId];
  if (list) { const i = list.indexOf(temp); if (i >= 0) list.splice(i, 1); }
  if (S.current === chatId) renderMessages(true);
}

function setCtx(mode, m) {
  S.reply = mode === 'reply' ? m : null;
  S.edit = mode === 'edit' ? m : null;
  const box = $('#composeCtx');
  if (!mode) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('#ctxIcon').outerHTML = (mode === 'reply' ? ICON.reply : ICON.edit).replace('<svg', '<svg id="ctxIcon"');
  $('#ctxTitle').textContent = mode === 'reply' ? 'В ответ ' + (S.users[m.from]?.name || '') : 'Редактирование';
  $('#ctxText').textContent = previewText(m);
}
$('#ctxClose').onclick = () => { if (S.edit) { input.value = ''; autoGrow(); } setCtx(null); };
function startReply(id) {
  const m = (S.msgs[S.current] || []).find(x => x.id === id);
  if (!m || m.pending || m.service) return;
  if (S.edit) { input.value = ''; }
  setCtx('reply', m); input.focus();
}
function startEdit(id) {
  const m = (S.msgs[S.current] || []).find(x => x.id === id);
  if (!m) return;
  setCtx('edit', m); input.value = m.text; autoGrow(); input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

// ----- files -----
$('#attachBtn').onclick = () => $('#fileInput').click();
$('#fileInput').onchange = e => { const f = e.target.files[0]; e.target.value = ''; if (f) uploadAndSend(f); };
input.addEventListener('paste', e => {
  const f = [...(e.clipboardData?.files || [])][0];
  if (f) { e.preventDefault(); uploadAndSend(f); }
});
const chatEl = $('#chat');
let dragDepth = 0, dropHint = null;
chatEl.addEventListener('dragenter', e => {
  if (!S.current || !e.dataTransfer.types.includes('Files')) return;
  e.preventDefault();
  if (dragDepth++ === 0) { dropHint = el('<div class="drop-hint">Отпустите, чтобы отправить</div>'); chatEl.appendChild(dropHint); }
});
chatEl.addEventListener('dragover', e => { if (S.current) e.preventDefault(); });
chatEl.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; dropHint?.remove(); } });
chatEl.addEventListener('drop', e => {
  e.preventDefault(); dragDepth = 0; dropHint?.remove();
  const f = e.dataTransfer.files[0]; if (f && S.current) uploadAndSend(f);
});
async function uploadAndSend(file) {
  if (S.edit) setCtx(null);
  if (file.size > 20 * 1024 * 1024) return toast('Максимальный размер файла — 20 МБ');
  toast('Загрузка ' + file.name + '…');
  try {
    const res = await fetch('/api/upload', {
      method: 'POST', body: file,
      headers: { Authorization: 'Bearer ' + S.token, 'X-Filename': encodeURIComponent(file.name || 'file'), 'Content-Type': file.type || 'application/octet-stream' },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    $('#toast').classList.add('hidden');
    await submit(data);
  } catch (err) { toast(err.message || 'Не удалось загрузить файл'); }
}

// ================= notifications =================
function notify(c, m) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    const title = c.type === 'group' ? `${S.users[m.from]?.name} → ${c.title}` : chatTitle(c);
    const n = new Notification(title, { body: previewText(m), tag: 'chat' + c.id, icon: 'icon.svg' });
    n.onclick = () => { window.focus(); openChat(c.id); n.close(); };
  } catch {}
}
function updateTitle() {
  const n = Object.values(S.chats).reduce((s, c) => s + (c.unread || 0), 0);
  document.title = n ? `(${n}) Telegraph` : 'Telegraph';
}

// ================= modals =================
function openModal(html) {
  $('#modal').innerHTML = html;
  $('#modalBack').classList.remove('hidden');
  const f = $('#modal').querySelector('input,textarea'); if (f && matchMedia('(pointer: fine)').matches) f.focus();
  return $('#modal');
}
function closeModal() { $('#modalBack').classList.add('hidden'); $('#modal').innerHTML = ''; }
$('#modalBack').onclick = e => { if (e.target.id === 'modalBack') closeModal(); };
const modalHead = title => `<div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" data-close>${ICON.close}</button></div>`;
$('#modal').addEventListener('click', e => { if (e.target.closest('[data-close]')) closeModal(); });

function confirmModal(title, text, okText, onOk) {
  const m = openModal(`${modalHead(title)}<div class="modal-body"><p>${esc(text)}</p></div>
    <div class="modal-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn danger" id="okBtn">${esc(okText)}</button></div>`);
  m.querySelector('#okBtn').onclick = () => { closeModal(); onOk(); };
}

function profileModal() {
  const u = S.me;
  const m = openModal(`${modalHead('Мой профиль')}<div class="modal-body">
    <div class="profile-top">${userAvatar({ ...u, online: false })}<h3>${esc(u.name)}</h3><div class="muted">@${esc(u.username)}</div></div>
    <label class="field"><span>Имя</span><input id="pName" maxlength="64" value="${esc(u.name)}"></label>
    <label class="field"><span>О себе</span><textarea id="pBio" rows="2" maxlength="140" placeholder="Пара слов о себе">${esc(u.bio)}</textarea></label>
    </div><div class="modal-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn primary" id="pSave">Сохранить</button></div>`);
  m.querySelector('#pSave').onclick = async () => {
    try { await rpc('updateProfile', { name: $('#pName').value, bio: $('#pBio').value }); closeModal(); toast('Профиль сохранён'); }
    catch (err) { toast(err.message); }
  };
}

function userModal(u) {
  if (!u) return;
  if (u.id === S.me.id) return profileModal();
  const m = openModal(`${modalHead('Информация')}<div class="modal-body">
    <div class="profile-top">${userAvatar({ ...u, online: false })}<h3>${esc(u.name)}</h3><div class="muted">${esc(lastSeen(u))}</div></div>
    <div class="info-row">@${esc(u.username)}<small>Имя пользователя</small></div>
    ${u.bio ? `<div class="info-row">${esc(u.bio)}<small>О себе</small></div>` : ''}
    </div><div class="modal-foot"><button class="btn primary wide" id="uMsg">Написать сообщение</button></div>`);
  m.querySelector('#uMsg').onclick = () => { closeModal(); openPrivate(u.id); };
}

function chatInfoModal(c) {
  if (!c) return;
  if (c.type === 'private') return userModal(S.users[peerId(c)]);
  if (c.type === 'saved') return toast('Избранное видно только вам');
  const members = c.members.map(id => S.users[id]).filter(Boolean)
    .sort((a, b) => (b.id === c.ownerId) - (a.id === c.ownerId) || b.online - a.online);
  const m = openModal(`${modalHead('Группа')}<div class="modal-body">
    <div class="profile-top">${avatarHtml(c)}<h3 id="gTitle">${esc(c.title)}</h3><div class="muted">${esc(chatStatus(c).text)}</div></div>
    <label class="field"><span>Название</span><input id="gName" maxlength="64" value="${esc(c.title)}"></label>
    <div class="section-title" style="padding-left:0">Участники</div>
    <div class="pick-list">${members.map(u => `<div class="pick" data-uid="${u.id}">${userAvatar(u)}
      <div class="ci-body"><div>${esc(u.name)}${u.id === S.me.id ? ' (вы)' : ''}</div><small>${u.id === c.ownerId ? 'владелец · ' : ''}${esc(lastSeen(u))}</small></div></div>`).join('')}</div>
    </div><div class="modal-foot">
      <button class="btn danger" id="gLeave">Покинуть</button><span style="flex:1"></span>
      <button class="btn ghost" id="gAdd">Добавить</button><button class="btn primary" id="gSave">Сохранить</button></div>`);
  m.querySelector('.pick-list').onclick = e => { const p = e.target.closest('.pick'); if (p) userModal(S.users[p.dataset.uid]); };
  m.querySelector('#gSave').onclick = async () => {
    const t = $('#gName').value.trim();
    if (t === c.title) return closeModal();
    try { await rpc('renameGroup', { chatId: c.id, title: t }); closeModal(); } catch (err) { toast(err.message); }
  };
  m.querySelector('#gAdd').onclick = () => pickUsersModal('Добавить участников', 'Добавить', c.members, async ids => {
    await rpc('addMembers', { chatId: c.id, memberIds: ids });
  });
  m.querySelector('#gLeave').onclick = () => confirmModal('Покинуть группу?', `Вы покинете «${c.title}».`, 'Покинуть',
    () => rpc('leaveChat', { chatId: c.id }).catch(err => toast(err.message)));
}

function groupModal() {
  pickUsersModal('Новая группа', 'Создать', [S.me.id], async (ids, title) => {
    const id = await rpc('createGroup', { title, memberIds: ids });
    await waitForChat(id); openChat(id);
  }, true);
}

function pickUsersModal(title, okText, exclude, onOk, withTitle) {
  const selected = new Map();
  let results = [];
  const knownUsers = () => Object.values(S.users).filter(u => !exclude.includes(u.id) && u.id !== S.me.id);
  const m = openModal(`${modalHead(title)}<div class="modal-body">
    ${withTitle ? '<label class="field"><span>Название группы</span><input id="gtitle" maxlength="64"></label>' : ''}
    <div class="chips" id="chips"></div>
    <label class="field"><span>Поиск людей</span><input id="pq" placeholder="Имя или @username" autocomplete="off"></label>
    <div class="pick-list" id="plist"></div></div>
    <div class="modal-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn primary" id="pOk">${esc(okText)}</button></div>`);
  const draw = () => {
    const list = $('#pq').value.trim() ? results.filter(u => !exclude.includes(u.id)) : knownUsers();
    $('#plist').innerHTML = list.length ? list.map(u => `<div class="pick ${selected.has(u.id) ? 'on' : ''}" data-uid="${u.id}">${userAvatar(u)}
      <div class="ci-body"><div>${esc(u.name)}</div><small>@${esc(u.username)}</small></div><div class="check">${selected.has(u.id) ? ICON.ok : ''}</div></div>`).join('')
      : '<div class="list-empty">Найдите людей по имени пользователя</div>';
    $('#chips').innerHTML = [...selected.values()].map(u => `<span class="chip" data-uid="${u.id}">${esc(u.name)} ✕</span>`).join('');
    results.forEach(u => { if (!S.users[u.id]) S.users[u.id] = u; });
  };
  let t;
  $('#pq').oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => { const q = $('#pq').value.trim(); results = q ? await rpc('searchUsers', { q }).catch(() => []) : []; draw(); }, 200);
  };
  m.querySelector('#plist').onclick = e => {
    const p = e.target.closest('.pick'); if (!p) return;
    const id = Number(p.dataset.uid), u = S.users[id] || results.find(x => x.id === id);
    selected.has(id) ? selected.delete(id) : selected.set(id, u); draw();
  };
  m.querySelector('#chips').onclick = e => { const c = e.target.closest('.chip'); if (c) { selected.delete(Number(c.dataset.uid)); draw(); } };
  m.querySelector('#pOk').onclick = async () => {
    const titleVal = withTitle ? $('#gtitle').value.trim() : '';
    if (withTitle && !titleVal) return toast('Введите название группы');
    if (!withTitle && !selected.size) return toast('Выберите хотя бы одного человека');
    try { await onOk([...selected.keys()], titleVal); closeModal(); } catch (err) { toast(err.message); }
  };
  draw();
}

function forwardModal(msg) {
  const chats = sortedChats();
  const m = openModal(`${modalHead('Переслать в…')}<div class="modal-body"><div class="pick-list">
    ${chats.map(c => `<div class="pick" data-cid="${c.id}">${avatarHtml(c)}<div class="ci-body"><div>${esc(chatTitle(c))}</div></div></div>`).join('')}
    </div></div>`);
  m.querySelector('.pick-list').onclick = async e => {
    const p = e.target.closest('.pick'); if (!p) return;
    const chatId = Number(p.dataset.cid);
    const from = S.users[msg.from]?.name;
    const text = msg.from !== S.me.id && from ? `↪ Переслано от ${from}\n${msg.text}` : msg.text;
    try { await rpc('send', { chatId, text: text.trim(), file: msg.file }); closeModal(); toast('Сообщение переслано'); }
    catch (err) { toast(err.message); }
  };
}

// refresh "last seen" labels every minute
setInterval(() => { if (S.current) renderHeader(); }, 60e3);

// ================= start =================
if (S.token) connect(); else showAuth();
