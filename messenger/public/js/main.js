// Boot, authentication, theme, and routing of server events.
import { S, forgetAll, decrypt, decryptAll, createDirect, chatTitle } from './state.js';
import { connect, disconnect, setHandlers, api, rpc } from './net.js';
import * as C from './crypto.js';
import { $, $$, toast, fine } from './util.js';
import { App } from './bus.js';
import { initRail, setTab, refreshPanel, updateRail, describe } from './sidebar.js';
import { initConversation, openChat, closeChat, renderFeed, renderHead, renderPins, renderDetails, markRead, atBottom, setCtx, toggleDetails, msgIndex } from './conversation.js';
import { startCall, handleCallEvent, inCall, hangup } from './calls.js';
import { closeTopModal, closeMenu } from './modals.js';
import { sounds } from './media.js';

// ================= theme =================
const themeMode = () => localStorage.getItem('orbita.theme') || 'auto';
const accent = () => localStorage.getItem('orbita.accent') || '#ff5f3a';
function applyTheme() {
  const m = themeMode();
  const dark = m === 'dark' || (m === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.style.setProperty('--accent', accent());
  document.querySelector('meta[name=theme-color]').content = dark ? '#121116' : '#f4f1ea';
  if (S.me) updateRail();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
Object.assign(App, {
  themeMode, accent,
  setTheme(m) { localStorage.setItem('orbita.theme', m); applyTheme(); },
  setAccent(c) { localStorage.setItem('orbita.accent', c); applyTheme(); },
  cycleTheme() { const order = ['auto', 'light', 'dark']; App.setTheme(order[(order.indexOf(themeMode()) + 1) % 3]); if (S.tab === 'me') refreshPanel(); },
});
applyTheme();

// ================= app API for other modules =================
function waitChat(id) {
  return new Promise(res => { const t0 = Date.now(); (function poll() { if (S.chats[id] || Date.now() - t0 > 4000) res(); else setTimeout(poll, 25); })(); });
}
Object.assign(App, {
  openChat: id => { if (S.tab !== 'chats' && innerWidth > 820) setTab('chats'); return openChat(id); },
  setTab, waitChat, startCall,
  async openDirect(userId) {
    try { const id = await createDirect(userId); await waitChat(id); await App.openChat(id); return id; }
    catch (e) { toast(e.message, 'bad'); return null; }
  },
  logout,
});

// ================= auth =================
let mode = 'login';
function setMode(m) {
  mode = m;
  $('#auth').classList.toggle('register', m === 'register');
  $('#authTitle').textContent = m === 'login' ? 'С возвращением' : 'Новая орбита';
  $('#authSub').textContent = m === 'login' ? 'Войдите, чтобы продолжить разговоры.' : 'Аккаунт создаётся за минуту — без телефона и почты.';
  $('#authSubmit').textContent = m === 'login' ? 'Войти' : 'Создать аккаунт';
  $('#switchText').textContent = m === 'login' ? 'Впервые здесь?' : 'Уже есть аккаунт?';
  $('#switchMode').textContent = m === 'login' ? 'Создать аккаунт' : 'Войти';
  $('#authForm').elements.password.autocomplete = m === 'login' ? 'current-password' : 'new-password';
  $('#authError').textContent = '';
}
$('#switchMode').onclick = () => setMode(mode === 'login' ? 'register' : 'login');
$('#authForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.target.elements, err = $('#authError'), btn = $('#authSubmit');
  const username = f.username.value.trim(), password = f.password.value;
  err.textContent = '';
  if (!username || !password) return (err.textContent = 'Введите логин и пароль');
  if (mode === 'register') {
    if (!f.name.value.trim()) return (err.textContent = 'Как вас зовут?');
    if (!/^[a-zA-Z][a-zA-Z0-9_]{2,31}$/.test(username)) return (err.textContent = 'Логин: 3–32 символа, латиница, цифры и _, начинается с буквы');
    if (password.length < 8) return (err.textContent = 'Пароль — не меньше 8 символов');
    if (password !== f.password2.value) return (err.textContent = 'Пароли не совпадают');
    if (S.config.escrow && !f.consent.checked) return (err.textContent = 'Подтвердите, что ознакомились с условиями доступа');
  }
  btn.disabled = true; btn.classList.add('busy');
  try {
    const { auth, encKey } = await C.credentials(username, password);
    let token, userId, privateKey, publicKey;
    if (mode === 'register') {
      const id = await C.newIdentity(encKey);
      ({ token, userId } = await api('/api/register', { username, name: f.name.value.trim(), auth, publicKey: id.publicKey, sealedKey: id.sealedKey }));
      privateKey = id.privateKey; publicKey = id.publicKey;
    } else {
      const r = await api('/api/login', { username, auth });
      ({ token, userId, publicKey } = r);
      try { privateKey = await C.openIdentity(encKey, r.sealedKey); }
      catch { throw new Error('Не удалось открыть ключ шифрования'); }
    }
    await C.keystore.set({ userId, privateKey, publicKey });
    S.token = token; localStorage.setItem('orbita.token', token);
    S.identity = { id: userId, privateKey, publicKey };
    e.target.reset();
    connect();
  } catch (x) { err.textContent = x.message; }
  btn.disabled = false; btn.classList.remove('busy');
};
function showAuth() {
  $('#boot').classList.add('hidden'); $('#app').classList.add('hidden'); $('#auth').classList.remove('hidden');
  setMode(mode);
  if (fine()) setTimeout(() => $('#authForm').elements.username.focus(), 50);
}
function showApp() {
  $('#boot').classList.add('hidden'); $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden');
}
async function logout(silent) {
  if (inCall()) hangup();
  if (!silent) await api('/api/logout', {}).catch(() => {});
  disconnect();
  await C.keystore.clear();
  localStorage.removeItem('orbita.token');
  forgetAll();
  location.reload();
}

// ================= events =================
function notify(c, m) {
  if (!document.hidden && S.current === c.id) return;
  sounds.message();
  if (!document.hidden || !('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    const title = c.type === 'group' ? `${S.users[m.from]?.name} · ${c.title}` : chatTitle(c);
    const n = new Notification(title, { body: describe(m, c), tag: 'chat' + c.id, icon: S.users[m.from]?.avatar || '/icon.svg' });
    n.onclick = () => { window.focus(); App.openChat(c.id); n.close(); };
  } catch {}
}
const isCurrent = id => S.current === id;

async function onEvent(evt) {
  switch (evt.type) {
    case 'init': {
      S.me = evt.me;
      S.config.escrow = evt.escrow || null;
      document.body.classList.toggle('escrow', !!evt.escrow);
      S.users = {};
      for (const u of evt.users) S.users[u.id] = u;
      S.chats = {};
      for (const c of evt.chats) S.chats[c.id] = c;
      S.msgs = {}; S.loaded = {}; S.hasMore = {};
      await decryptAll(evt.chats.map(c => c.lastMessage));
      showApp();
      setTab(S.tab);
      if (S.current && S.chats[S.current]) openChat(S.current, { force: true });
      else if (S.current) closeChat();
      for (const c of evt.calls || []) handleCallEvent({ type: 'call:incoming', ...c });
      return;
    }
    case 'chat': {
      for (const u of evt.users) S.users[u.id] = { ...S.users[u.id], ...u };
      const prev = S.chats[evt.chat.id];
      S.chats[evt.chat.id] = evt.chat;
      await decrypt(evt.chat.lastMessage);
      // New key versions may unlock messages that failed earlier.
      if (prev && prev.keys.length !== evt.chat.keys.length && S.msgs[evt.chat.id]) {
        for (const m of S.msgs[evt.chat.id]) if (m.err) delete m.err;
        await decryptAll(S.msgs[evt.chat.id]);
        if (isCurrent(evt.chat.id)) renderFeed();
      }
      refreshPanel();
      if (isCurrent(evt.chat.id)) { renderHead(); renderPins(); renderDetails(); }
      return;
    }
    case 'chatRemoved': {
      delete S.chats[evt.chatId]; delete S.msgs[evt.chatId]; delete S.loaded[evt.chatId];
      if (isCurrent(evt.chatId)) { closeChat(); toast('Вы больше не участник этой беседы'); }
      refreshPanel();
      return;
    }
    case 'message': {
      const m = evt.message, c = S.chats[m.chatId];
      if (!c) return;
      await decrypt(m);
      const list = S.msgs[m.chatId];
      if (list && !list.some(x => x.id === m.id)) {
        // Swap our optimistic copy for the real message.
        const tmp = list.findIndex(x => x.pending && x.ct && x.ct === m.ct);
        if (tmp >= 0) list.splice(tmp, 1);
        const firstPending = list.findIndex(x => x.pending);
        firstPending >= 0 ? list.splice(firstPending, 0, m) : list.push(m);
      }
      c.lastMessage = m;
      if (S.typing[c.id]) { clearTimeout(S.typing[c.id][m.from]?.timer); delete S.typing[c.id][m.from]; }
      if (m.from !== S.me.id && m.kind !== 'service') {
        const seenNow = isCurrent(c.id) && !document.hidden && atBottom();
        if (!seenNow) c.unread = (c.unread || 0) + 1;
        notify(c, m);
      }
      if (m.kind === 'call' && S.callLog) S.callLog.unshift(m);
      if (isCurrent(c.id)) { renderFeed(); markRead(); renderHead(); }
      refreshPanel();
      return;
    }
    case 'edited': {
      const m = evt.message, c = S.chats[m.chatId]; if (!c) return;
      await decrypt(m);
      const list = S.msgs[m.chatId];
      if (list) { const i = list.findIndex(x => x.id === m.id); if (i >= 0) list[i] = m; }
      if (c.lastMessage?.id === m.id) c.lastMessage = m;
      if (c.pins) { const i = c.pins.findIndex(x => x.id === m.id); if (i >= 0) c.pins[i] = m; }
      if (S.edit?.id === m.id) setCtx(null);
      if (isCurrent(c.id)) { renderFeed(); renderPins(); }
      refreshPanel();
      return;
    }
    case 'deleted': {
      const c = S.chats[evt.chatId]; if (!c) return;
      const ids = new Set(evt.ids);
      if (S.msgs[c.id]) S.msgs[c.id] = S.msgs[c.id].filter(m => !ids.has(m.id));
      c.pins = (c.pins || []).filter(m => !ids.has(m.id));
      c.lastMessage = evt.lastMessage; await decrypt(c.lastMessage);
      if (S.reply && ids.has(S.reply.id)) setCtx(null);
      if (isCurrent(c.id)) { renderFeed(); renderPins(); }
      refreshPanel();
      return;
    }
    case 'reactions': case 'votes': {
      const field = evt.type;
      const apply = m => { if (m && m.id === evt.id) m[field] = evt[field]; };
      (S.msgs[evt.chatId] || []).forEach(apply);
      apply(S.chats[evt.chatId]?.lastMessage);
      if (evt.type === 'reactions' && evt.added && evt.by !== S.me.id) {
        const m = msgIndex(evt.id) || S.chats[evt.chatId]?.lastMessage;
        if (m?.from === S.me.id && (!isCurrent(evt.chatId) || document.hidden)) {
          sounds.message();
          toast(`${S.users[evt.by]?.name.split(' ')[0]} — ${evt.emoji} на ваше сообщение`);
        }
      }
      if (isCurrent(evt.chatId)) renderFeed();
      return;
    }
    case 'read': {
      const c = S.chats[evt.chatId]; if (!c) return;
      c.reads[evt.userId] = Math.max(c.reads[evt.userId] || 0, evt.msgId);
      if (evt.userId === S.me.id && c.lastMessage && evt.msgId >= c.lastMessage.id) c.unread = 0;
      if (isCurrent(c.id)) renderFeed();
      refreshPanel();
      return;
    }
    case 'typing': {
      const t = S.typing[evt.chatId] ||= {};
      clearTimeout(t[evt.userId]?.timer);
      t[evt.userId] = { kind: evt.kind, timer: setTimeout(() => { delete t[evt.userId]; refreshPanel(); if (isCurrent(evt.chatId)) renderHead(); }, 5500) };
      refreshPanel();
      if (isCurrent(evt.chatId)) renderHead();
      return;
    }
    case 'presence': {
      const u = S.users[evt.userId]; if (!u) return;
      u.online = evt.online; u.lastSeen = evt.lastSeen;
      refreshPanel();
      if (S.current) { renderHead(); renderDetails(); }
      return;
    }
    case 'user': {
      S.users[evt.user.id] = { ...S.users[evt.user.id], ...evt.user };
      if (evt.user.id === S.me.id) S.me = { ...S.me, ...evt.user };
      refreshPanel();
      if (S.current) { renderHead(); renderFeed(); renderDetails(); }
      return;
    }
    default:
      if (evt.type.startsWith('call:')) return handleCallEvent(evt);
  }
}
function onStatus(s) {
  $('#netbar').classList.toggle('hidden', s !== 'offline');
  if (s === 'unauthorized') { toast('Сеанс завершён'); logout(true); }
}
setHandlers(onEvent, onStatus);

// ================= global keys =================
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeMenu();
  if (closeTopModal()) return;
  if (S.details && innerWidth < 1280) return toggleDetails(false);
  if (document.activeElement?.closest('.search-field')) return;
  if (S.current && !inCall()) closeChat();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) markRead(); });
setInterval(() => { if (S.current) renderHead(); if (S.tab === 'people') refreshPanel(); }, 60e3);

// ================= boot =================
(async function boot() {
  initRail();
  initConversation();
  S.config = await fetch('/api/config').then(r => r.json()).catch(() => S.config);
  document.body.classList.toggle('escrow', !!S.config.escrow);
  const ident = await C.keystore.get();
  if (S.token && ident?.privateKey) {
    S.identity = { id: ident.userId, privateKey: ident.privateKey, publicKey: ident.publicKey };
    connect();
  } else {
    localStorage.removeItem('orbita.token'); S.token = null;
    showAuth();
  }
})();
