// Rail + the left panel (chats / calls / people / me).
import { S, chatTitle, peerId, userName, totalUnread } from './state.js';
import { rpc, api } from './net.js';
import { native } from './util.js';
import { $, $$, esc, icon, shortTime, seen, duration, toast, debounce, ttlShort, ttlLabel } from './util.js';
import { avatar, chatAvatar } from './avatar.js';
import { menu, newGroup, personCard, safetyModal, passwordModal, sessionsModal, confirmBox } from './modals.js';
import { sounds } from './media.js';
import { App } from './bus.js';
import { botsModal, botChip } from './botsui.js';

const body = () => $('#panelBody');

// ---------- message descriptions (shared with the conversation) ----------
export function serviceText(m) {
  const who = userName(m.from), e = m.meta || {};
  const names = (e.users || []).map(userName).join(', ');
  switch (e.event) {
    case 'created': return `${who} — создал(а) группу «${e.title}»`;
    case 'added': return `${who} — пригласил(а): ${names}`;
    case 'removed': return `${who} — исключил(а): ${names}`;
    case 'left': return `${who} — покинул(а) группу`;
    case 'renamed': return `${who} — новое название «${e.title}»`;
    case 'ttl': return e.ttl ? `${who} — сообщения исчезают через ${ttlLabel(e.ttl).toLowerCase()}` : `${who} — исчезающие сообщения выключены`;
    case 'pinned': return `${who} — закрепил(а) сообщение`;
    default: return '';
  }
}
export function callText(m) {
  const c = m.meta.call, mine = m.from === S.me.id, kind = c.video ? 'видеозвонок' : 'звонок';
  if (c.status === 'ended') return `${mine ? 'Исходящий' : 'Входящий'} ${kind} · ${duration(c.duration)}`;
  if (c.status === 'declined') return mine ? `${cap(kind)} отклонён` : `Вы отклонили ${kind}`;
  if (c.status === 'busy') return mine ? 'Абонент был занят' : `Пропущенный ${kind}`;
  return mine ? `${cap(kind)} без ответа` : `Пропущенный ${kind}`;
}
const cap = s => s[0].toUpperCase() + s.slice(1);
export function describe(m, c) {
  if (!m) return c?.type === 'self' ? 'Заметки, ссылки и файлы — только для вас' : 'Пока ни слова';
  if (m.kind === 'service') return serviceText(m);
  if (m.kind === 'call') return callText(m);
  if (m.err) return '🔒 Не удалось расшифровать';
  const p = m.p;
  if (!p) return '…';
  if (p.poll) return '📊 ' + p.poll.q;
  if (p.voice) return '🎙 Голосовое · ' + duration(p.voice.dur);
  if (p.file) {
    const t = p.file.type || '';
    const k = t.startsWith('image/') ? '🖼 Фото' : t.startsWith('video/') ? '🎬 Видео' : t.startsWith('audio/') ? '🎵 ' + p.file.name : '📎 ' + p.file.name;
    return p.t ? k + ' · ' + plain(p.t) : k;
  }
  return plain(p.t || '');
}
const plain = t => t.replace(/\*\*([^*\n]+)\*\*/g, '$1').replace(/`([^`\n]+)`/g, '$1');
export const isMissed = m => m.kind === 'call' && m.from !== S.me.id && m.meta.call.status !== 'ended' && m.meta.call.status !== 'declined';

// ---------- rail ----------
const RAIL = { chats: 'chats', calls: 'phone', people: 'people', me: 'me' };
export function initRail() {
  for (const b of $$('.rail-btn')) {
    b.querySelector('.ic').innerHTML = icon(RAIL[b.dataset.tab]);
    b.onclick = () => setTab(b.dataset.tab);
  }
  $('#themeBtn').onclick = () => App.cycleTheme();
}
export function updateRail() {
  const n = totalUnread();
  const chatsDot = $('.rail-btn[data-tab=chats] .dot');
  chatsDot.textContent = n > 99 ? '99+' : n;
  chatsDot.classList.toggle('hidden', !n);
  const missed = missedCalls();
  const callsDot = $('.rail-btn[data-tab=calls] .dot');
  callsDot.textContent = missed;
  callsDot.classList.toggle('hidden', !missed);
  document.title = n ? `(${n}) Орбита` : 'Орбита';
  $('#themeBtn').innerHTML = icon({ light: 'sun', dark: 'moon', auto: 'monitor' }[App.themeMode()]);
}
function missedCalls() {
  const since = Number(localStorage.getItem('orbita.callsSeen') || 0);
  return Object.values(S.chats).filter(c => c.lastMessage && c.lastMessage.ts > since && isMissed(c.lastMessage)).length;
}

export function setTab(tab) {
  S.tab = tab;
  for (const b of $$('.rail-btn')) b.classList.toggle('active', b.dataset.tab === tab);
  document.body.dataset.tab = tab;
  if (tab === 'calls') localStorage.setItem('orbita.callsSeen', Date.now());
  ({ chats: chatsSkeleton, calls: callsSkeleton, people: peopleSkeleton, me: meSkeleton })[tab]();
  refreshPanel();
  updateRail();
}

export function refreshPanel() {
  if (!S.me) return;
  if (S.tab === 'chats') drawChats();
  else if (S.tab === 'calls') drawCalls();
  else if (S.tab === 'people') drawPeople();
  else if (S.tab === 'me') drawMe();
  updateRail();
}

// ================= chats =================
function chatsSkeleton() {
  body().innerHTML = `
    <header class="p-head"><h1>Беседы</h1><button class="icon-btn solid" id="newBtn" title="Новая беседа">${icon('plus')}</button></header>
    <label class="search-field">${icon('search')}<input id="chatSearch" placeholder="Поиск по беседам" autocomplete="off" value="${esc(S.query)}"></label>
    <div class="filters" id="filters">
      ${[['all', 'Все'], ['unread', 'Непрочитанные'], ['direct', 'Личные'], ['group', 'Группы']].map(([k, l]) => `<button data-f="${k}" class="${S.filter === k ? 'on' : ''}">${l}</button>`).join('')}
    </div>
    <div class="list" id="chatList"></div>`;
  $('#newBtn').onclick = e => menu(e.currentTarget, [
    { icon: 'chats', label: 'Написать человеку', run: () => { setTab('people'); setTimeout(() => $('#peopleSearch')?.focus(), 30); } },
    { icon: 'people', label: 'Создать группу', run: newGroup },
    { icon: 'sparkle', label: 'Мои заметки', run: () => { const c = Object.values(S.chats).find(c => c.type === 'self'); if (c) App.openChat(c.id); } },
  ]);
  $('#chatSearch').oninput = e => { S.query = e.target.value; drawChats(); };
  $('#filters').onclick = e => {
    const b = e.target.closest('[data-f]'); if (!b) return;
    S.filter = b.dataset.f;
    $$('#filters button').forEach(x => x.classList.toggle('on', x === b));
    drawChats();
  };
  $('#chatList').onclick = e => { const r = e.target.closest('[data-chat]'); if (r) App.openChat(Number(r.dataset.chat)); };
}

export function sortedChats() {
  return Object.values(S.chats).sort((a, b) => (b.lastMessage?.ts || b.createdAt) - (a.lastMessage?.ts || a.createdAt));
}
function typingLine(c) {
  const t = S.typing[c.id]; if (!t) return '';
  const ids = Object.keys(t).map(Number); if (!ids.length) return '';
  const voice = ids.some(id => t[id].kind === 'voice');
  const what = voice ? 'записывает голосовое' : 'печатает';
  if (c.type !== 'group') return what;
  return ids.length === 1 ? `${S.users[ids[0]]?.name.split(' ')[0]} ${what}` : `${ids.length} чел. ${voice ? 'записывают' : 'печатают'}`;
}
export { typingLine };

function chatRowHtml(c) {
  const m = c.lastMessage;
  const typing = typingLine(c);
  let prev;
  if (typing) prev = `<span class="typing-txt">${esc(typing)}<i class="dots"><b></b><b></b><b></b></i></span>`;
  else {
    let who = '';
    if (m && m.kind === 'msg') {
      if (m.from === S.me.id && c.type !== 'self') who = 'Вы: ';
      else if (c.type === 'group') who = (S.users[m.from]?.name.split(' ')[0] || '') + ': ';
    }
    const missed = m && isMissed(m);
    prev = (who ? `<span class="cr-who">${esc(who)}</span>` : '') + `<span class="${missed ? 'missed' : ''}">${esc(describe(m, c))}</span>`;
  }
  const ticks = m && m.kind === 'msg' && m.from === S.me.id && c.type !== 'self'
    ? `<span class="ticks ${readByOthers(c, m) ? 'read' : ''}">${icon(readByOthers(c, m) ? 'checks' : 'check')}</span>` : '';
  const badge = c.unread ? `<span class="pill">${c.unread > 99 ? '99+' : c.unread}</span>` : '';
  return `<button class="chat-row ${S.current === c.id ? 'active' : ''}" data-chat="${c.id}">
    ${chatAvatar(c, 'lg')}
    <span class="cr-main">
      <span class="cr-top"><b class="cr-name">${esc(chatTitle(c))}${c.type === 'direct' ? botChip(S.users[peerId(c)]) : ''}</b>${c.ttl ? `<span class="ttl-chip">${icon('timer')}${ttlShort(c.ttl)}</span>` : ''}<span class="cr-time">${ticks}${m ? shortTime(m.ts) : ''}</span></span>
      <span class="cr-bot"><span class="cr-prev">${prev}</span>${badge}</span>
    </span></button>`;
}
export const readByOthers = (c, m) => c.members.some(id => id !== S.me.id && (c.reads[id] || 0) >= m.id);

function drawChats() {
  const list = $('#chatList'); if (!list) return;
  const q = S.query.trim().toLowerCase();
  let chats = sortedChats();
  if (S.filter === 'unread') chats = chats.filter(c => c.unread);
  if (S.filter === 'direct') chats = chats.filter(c => c.type !== 'group');
  if (S.filter === 'group') chats = chats.filter(c => c.type === 'group');
  if (q) chats = chats.filter(c => chatTitle(c).toLowerCase().includes(q) || (c.type === 'direct' && S.users[peerId(c)]?.username.toLowerCase().includes(q.replace(/^@/, ''))));
  list.innerHTML = chats.length ? chats.map(chatRowHtml).join('') : `<div class="empty-state">${icon('chats')}<p>${
    q ? 'Ничего не нашлось' : S.filter === 'unread' ? 'Всё прочитано' : 'Здесь пока пусто. Найдите людей во вкладке «Люди»'}</p></div>`;
}

// ================= calls =================
function callsSkeleton() {
  body().innerHTML = `<header class="p-head"><h1>Звонки</h1></header>
    <p class="p-note">${icon('lock')} Звонки идут напрямую между устройствами и шифруются.</p>
    <div class="list" id="callList"><div class="empty-note">Загружаем…</div></div>`;
  rpc('callLog').then(list => { S.callLog = list; drawCalls(); }).catch(() => {});
  $('#callList').onclick = async e => {
    const b = e.target.closest('[data-recall]');
    if (b) { e.stopPropagation(); return App.startCall(Number(b.dataset.recall), b.dataset.video === '1'); }
    const r = e.target.closest('[data-chat]'); if (r) App.openChat(Number(r.dataset.chat));
  };
}
function drawCalls() {
  const list = $('#callList'); if (!list || !S.callLog) return;
  const items = S.callLog.filter(m => S.chats[m.chatId]);
  if (!items.length) { list.innerHTML = `<div class="empty-state">${icon('phone')}<p>Звонков пока не было. Позвонить можно из любой личной беседы.</p></div>`; return; }
  list.innerHTML = items.map(m => {
    const c = S.chats[m.chatId], u = S.users[peerId(c)], call = m.meta.call;
    const mine = m.from === S.me.id, missed = isMissed(m);
    const ic = missed ? 'callMissed' : mine ? 'callOut' : 'callIn';
    return `<div class="call-row" data-chat="${c.id}" role="button" tabindex="0">${avatar(u, 'md')}
      <span class="cr-main"><b class="${missed ? 'missed' : ''}">${esc(u?.name)}</b>
      <small class="${missed ? 'missed' : ''}">${icon(ic, 'xs')} ${esc(callText(m))}</small></span>
      <span class="cl-time">${shortTime(m.ts)}</span>
      <button class="icon-btn" data-recall="${c.id}" data-video="${call.video ? 1 : 0}" title="Позвонить">${icon(call.video ? 'video' : 'phone')}</button></div>`;
  }).join('');
}

// ================= people =================
let peopleResults = null;
function peopleSkeleton() {
  peopleResults = null;
  body().innerHTML = `<header class="p-head"><h1>Люди</h1><button class="icon-btn solid" id="grpBtn" title="Создать группу">${icon('people')}</button></header>
    <label class="search-field">${icon('search')}<input id="peopleSearch" placeholder="Найти по имени или @логину" autocomplete="off"></label>
    <div class="list" id="peopleList"></div>`;
  $('#grpBtn').onclick = newGroup;
  const search = debounce(async q => {
    peopleResults = q ? await rpc('searchUsers', { q }).catch(() => []) : null;
    if (peopleResults) for (const u of peopleResults) S.users[u.id] = { ...S.users[u.id], ...u };
    drawPeople();
  }, 220);
  $('#peopleSearch').oninput = e => search(e.target.value.trim());
  $('#peopleList').onclick = async e => {
    const msg = e.target.closest('[data-msg]');
    if (msg) { e.stopPropagation(); return App.openDirect(Number(msg.dataset.msg)); }
    const r = e.target.closest('[data-user]'); if (r) personCard(S.users[r.dataset.user]);
  };
}
function personRow(u) {
  return `<div class="person-row" data-user="${u.id}" role="button" tabindex="0">${avatar(u, 'md')}
    <span class="cr-main"><b>${esc(u.name)}${botChip(u)}</b><small class="${u.online ? 'online' : ''}">@${esc(u.username)} · ${esc(seen(u))}</small></span>
    <button class="icon-btn" data-msg="${u.id}" title="Написать">${icon('chats')}</button></div>`;
}
function drawPeople() {
  const list = $('#peopleList'); if (!list) return;
  if (peopleResults) {
    list.innerHTML = peopleResults.length ? `<h3 class="sect">Найдены</h3>` + peopleResults.map(personRow).join('') : `<div class="empty-state">${icon('search')}<p>Никого с таким именем</p></div>`;
    return;
  }
  const all = Object.values(S.users).filter(u => u.id !== S.me.id && !u.username.startsWith('deleted_'));
  const on = all.filter(u => u.online).sort((a, b) => a.name.localeCompare(b.name));
  const off = all.filter(u => !u.online).sort((a, b) => b.lastSeen - a.lastSeen);
  list.innerHTML = !all.length
    ? `<div class="empty-state">${icon('people')}<p>Найдите друзей по логину — например, <b>@${esc(S.me.username)}</b> найдут вас так же.</p></div>`
    : (on.length ? `<h3 class="sect">На связи · ${on.length}</h3>` + on.map(personRow).join('') : '') +
      (off.length ? `<h3 class="sect">Недавние</h3>` + off.map(personRow).join('') : '');
}

// ================= me =================
const ACCENTS = ['#ff5d7a', '#ff7a45', '#f5b301', '#22c55e', '#06b6d4', '#4f7dff', '#a855f7'];
function meSkeleton() {
  body().innerHTML = `<header class="p-head"><h1>Профиль</h1></header><div class="me" id="meBox"></div>`;
  const box = $('#meBox');
  box.onclick = async e => {
    const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
    if (a === 'avatar') $('#avatarFile').click();
    if (a === 'rmAvatar') { await rpc('removeAvatar'); }
    if (a === 'save') {
      try { await rpc('updateProfile', { name: $('#meName').value, bio: $('#meBio').value }); toast('Сохранено'); }
      catch (x) { toast(x.message, 'bad'); }
    }
    if (a === 'key') safetyModal(null);
    if (a === 'password') passwordModal();
    if (a === 'sessions') sessionsModal();
    if (a === 'bots') botsModal();
    if (a === 'server') { if (await confirmBox('Сменить сервер?', 'Приложение отключится от этого сервера. Ключ шифрования на устройстве сохранится.', 'Сменить', { danger: false })) native()?.resetServer(); return; }
    if (a === 'notify' && native()) return toast('Уведомления настраиваются в настройках Android');
    if (a === 'notify') {
      if (!('Notification' in window)) return toast('Браузер не поддерживает уведомления');
      const r = await Notification.requestPermission();
      toast(r === 'granted' ? 'Уведомления включены' : 'Разрешите уведомления в настройках браузера');
      drawMe();
    }
    if (a === 'sounds') { localStorage.setItem('orbita.sounds', sounds.enabled() ? 'off' : 'on'); drawMe(); }
    if (a === 'logout') { if (await confirmBox('Выйти из аккаунта?', 'Ключ этого устройства будет удалён. Чтобы вернуться, понадобится пароль.', 'Выйти')) App.logout(); }
  };
  box.addEventListener('change', async e => {
    if (e.target.id === 'avatarFile') {
      const f = e.target.files[0]; e.target.value = '';
      if (f) uploadAvatar(f);
    }
  });
  box.addEventListener('click', e => {
    const t = e.target.closest('[data-theme-set]');
    if (t) { App.setTheme(t.dataset.themeSet); drawMe(); }
    const ac = e.target.closest('[data-accent]');
    if (ac) { App.setAccent(ac.dataset.accent); drawMe(); }
  });
}
async function uploadAvatar(file) {
  try {
    const bmp = await createImageBitmap(file);
    const s = Math.min(bmp.width, bmp.height);
    const c = new OffscreenCanvas(320, 320);
    c.getContext('2d').drawImage(bmp, (bmp.width - s) / 2, (bmp.height - s) / 2, s, s, 0, 0, 320, 320);
    const blob = await c.convertToBlob({ type: 'image/webp', quality: 0.85 });
    await api('/api/avatar', undefined, { raw: blob, headers: { 'Content-Type': 'image/webp' } });
    toast('Фото обновлено');
  } catch (e) { toast(e.message || 'Не получилось загрузить фото', 'bad'); }
}
function drawMe() {
  const box = $('#meBox'); if (!box) return;
  const focused = document.activeElement?.id;
  if (focused === 'meName' || focused === 'meBio') return; // don't clobber typing
  const u = S.me, theme = App.themeMode(), accent = App.accent();
  const notif = native() ? 'granted' : 'Notification' in window ? Notification.permission : 'denied';
  box.innerHTML = `
    <section class="me-card">
      <button class="me-av" data-a="avatar" title="Сменить фото">${avatar({ ...u, online: false }, 'xl')}<span class="me-av-edit">${icon('image')}</span></button>
      <input type="file" id="avatarFile" accept="image/*" hidden>
      ${u.avatar ? '<button class="link sm" data-a="rmAvatar">Убрать фото</button>' : ''}
      <label class="field"><span>Имя</span><input id="meName" maxlength="64" value="${esc(u.name)}"></label>
      <label class="field"><span>О себе</span><textarea id="meBio" rows="2" maxlength="160" placeholder="Пара слов — увидят ваши собеседники">${esc(u.bio)}</textarea></label>
      <div class="me-row"><span class="muted">@${esc(u.username)}</span><button class="btn primary sm" data-a="save">Сохранить</button></div>
    </section>
    <section class="me-sect"><h3 class="sect">Оформление</h3>
      <div class="seg">${[['auto', 'Как в системе', 'monitor'], ['light', 'Светлая', 'sun'], ['dark', 'Тёмная', 'moon']].map(([k, l, i]) =>
        `<button data-theme-set="${k}" class="${theme === k ? 'on' : ''}">${icon(i)}<span>${l}</span></button>`).join('')}</div>
      <div class="swatches">${ACCENTS.map(c => `<button data-accent="${c}" class="${accent === c ? 'on' : ''}" style="--c:${c}" title="Акцент"></button>`).join('')}</div>
    </section>
    <section class="me-sect"><h3 class="sect">Безопасность</h3>
      <button class="me-item" data-a="key">${icon('shield')}<span><b>Мой ключ шифрования</b><small>Отпечаток для сверки с собеседниками</small></span></button>
      <button class="me-item" data-a="sessions">${icon('devices')}<span><b>Устройства</b><small>Где выполнен вход</small></span></button>
      <button class="me-item" data-a="password">${icon('key')}<span><b>Сменить пароль</b><small>Ключи переписки не изменятся</small></span></button>
    </section>
    <section class="me-sect"><h3 class="sect">Для разработчиков</h3>
      <button class="me-item" data-a="bots">${icon('sparkle')}<span><b>Мои боты</b><small>Создать бота, получить токен, настроить</small></span></button>
    </section>
    <section class="me-sect"><h3 class="sect">Уведомления</h3>
      <button class="me-item" data-a="notify">${icon('bell')}<span><b>Уведомления браузера</b><small>${notif === 'granted' ? 'Включены' : notif === 'denied' ? 'Запрещены в браузере' : 'Нажмите, чтобы включить'}</small></span></button>
      <button class="me-item" data-a="sounds">${icon(sounds.enabled() ? 'bell' : 'micOff')}<span><b>Звуки</b><small>${sounds.enabled() ? 'Включены' : 'Выключены'}</small></span></button>
    </section>
    ${native() ? `<button class="me-item" data-a="server">${icon('monitor')}<span><b>Сервер</b><small>${esc(location.host)} — сменить</small></span></button>` : ''}
    <button class="me-item danger" data-a="logout">${icon('logout')}<span><b>Выйти</b></span></button>
    <p class="fine-print">Орбита · P-256 + AES-256-GCM${S.config.escrow ? ' · служебный доступ по законному запросу' : ' · сквозное шифрование'}</p>`;
}
