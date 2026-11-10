// The open conversation: header, pinned bar, feed, composer and details panel.
import { S, chatTitle, peerId, userName, encryptPayload, decrypt, decryptAll, addMembersEncrypted } from './state.js';
import { rpc } from './net.js';
import { hidden } from './util.js';
import { $, $$, el, esc, icon, richText, onlyEmoji, hm, sameDay, dayLabel, seen, duration, size, plural, toast, fine, ttlLabel, ttlShort } from './util.js';
import { avatar, chatAvatar } from './avatar.js';
import { describe, serviceText, callText, isMissed, typingLine, readByOthers, refreshPanel } from './sidebar.js';
import { menu, closeMenu, confirmBox, lightbox, personCard, pickPeople, newPoll, chooseChat, safetyModal } from './modals.js';
import * as M from './media.js';
import { safetyCode } from './crypto.js';
import { App } from './bus.js';
import { inlineKb, botChip } from './botsui.js';

const feed = () => $('#feed');
const scroller = () => $('#scroller');
const input = () => $('#input');
const drafts = {};
const GAP = 5 * 60e3;

// ================= open / close =================
export async function openChat(id, { force } = {}) {
  const c = S.chats[id]; if (!c) return;
  const switching = S.current !== id;
  if (!switching && !force) return;
  if (switching) {
    if (S.current) drafts[S.current] = input().value;
    setCtx(null);
    if (M.recording()) await cancelRecording();
    S.current = id;
    S.unreadMark[id] = c.reads[S.me.id] || 0;
    input().value = drafts[id] || '';
    autoGrow(); renderCmds();
    feed().innerHTML = '';
    pinIndex = 0;
  }
  document.body.classList.add('in-chat');
  $('#void').classList.add('hidden');
  $('#convo').classList.remove('hidden');
  renderHead(); renderPins(); renderDetails(); refreshPanel(); updateSendBtn();
  if (!S.loaded[id]) {
    try {
      const r = await rpc('history', { chatId: id });
      await decryptAll(r.messages);
      S.msgs[id] = r.messages; S.hasMore[id] = r.hasMore; S.loaded[id] = true;
    } catch (e) { return toast(e.message, 'bad'); }
  }
  if (S.current !== id) return;
  renderFeed({ jump: switching || force ? 'unread' : null });
  markRead();
  renderDetails();
  if (fine()) input().focus();
}
export function closeChat() {
  if (S.current) drafts[S.current] = input().value;
  S.current = null; setCtx(null);
  document.body.classList.remove('in-chat');
  $('#convo').classList.add('hidden');
  $('#void').classList.remove('hidden');
  toggleDetails(false);
  refreshPanel();
}

// ================= header =================
export function statusOf(c) {
  const t = typingLine(c);
  if (t) return { text: t + '…', live: true };
  if (c.type === 'self') return { text: 'видны только вам' };
  if (c.type === 'group') {
    const on = c.members.filter(id => S.users[id]?.online).length;
    return { text: plural(c.members.length, 'участник', 'участника', 'участников') + (on > 1 ? ` · ${on} на связи` : '') };
  }
  const u = S.users[peerId(c)];
  if (u?.bot) return { text: 'бот' };
  return { text: seen(u), on: u?.online };
}
export function renderHead() {
  const c = S.chats[S.current]; if (!c) return;
  $('#whoAv').innerHTML = chatAvatar(c, 'md');
  const peer = c.type === 'direct' ? S.users[peerId(c)] : null;
  $('#whoName').innerHTML = esc(chatTitle(c)) + botChip(peer) + (c.ttl ? ` <span class="ttl-chip">${icon('timer')}${ttlShort(c.ttl)}</span>` : '');
  const st = statusOf(c);
  const s = $('#whoStatus');
  s.textContent = st.text;
  s.className = 'who-status' + (st.live ? ' live' : st.on ? ' on' : '');
  const direct = c.type === 'direct' && !peer?.bot;
  $('#audioCallBtn').classList.toggle('hidden', !direct);
  $('#videoCallBtn').classList.toggle('hidden', !direct);
  $('#detailsBtn').classList.toggle('on', S.details);
  input().placeholder = c.type === 'self' ? 'Заметка для себя' : 'Сообщение';
}

// ================= pinned =================
let pinIndex = 0;
export async function renderPins() {
  const c = S.chats[S.current], bar = $('#pinbar');
  if (!c || !c.pins?.length) { bar.classList.add('hidden'); return; }
  await decryptAll(c.pins);
  if (S.current !== c.id || !c.pins.length) return;
  pinIndex %= c.pins.length;
  const p = c.pins[pinIndex];
  bar.classList.remove('hidden');
  bar.innerHTML = `<span class="pin-ic">${icon('pin')}</span>
    <span class="pin-txt"><b>Закреплено${c.pins.length > 1 ? ` · ${pinIndex + 1} из ${c.pins.length}` : ''}</b><span>${esc(describe(p, c))}</span></span>
    <span class="pin-x" data-unpin="${p.id}" title="Открепить">${icon('close')}</span>`;
  bar.dataset.id = p.id;
}

// ================= feed =================
const sameGroup = (a, b) => a && b && a.kind === 'msg' && b.kind === 'msg' && a.from === b.from && sameDay(a.ts, b.ts) && Math.abs(b.ts - a.ts) < GAP;
const msgById = id => (S.msgs[S.current] || []).find(m => m.id === id);

function quoteHtml(c, m) {
  const r = msgById(m.replyTo);
  const name = r ? userName(r.from) : '';
  return `<button class="quote" data-goto="${m.replyTo}"><b>${esc(name || 'Сообщение')}</b><span>${esc(r ? describe(r, c) : 'недоступно')}</span></button>`;
}
function reactionsHtml(m) {
  const list = Object.entries(m.reactions || {});
  if (!list.length) return '';
  return `<div class="reacts">${list.map(([e, ids]) => `<button class="react ${ids.includes(S.me.id) ? 'mine' : ''}" data-react="${e}" title="${esc(ids.map(userName).join(', '))}">
    <span>${e}</span>${ids.length > 1 || S.chats[m.chatId]?.type === 'group' ? `<b>${ids.length}</b>` : ''}</button>`).join('')}</div>`;
}
function pollHtml(m) {
  const poll = m.p.poll;
  const votes = m.votes || {};
  const voters = new Set(Object.values(votes).flat());
  const mine = new Set(Object.entries(votes).filter(([, ids]) => ids.includes(S.me.id)).map(([o]) => Number(o)));
  const total = voters.size;
  const showResults = mine.size > 0;
  return `<div class="poll"><div class="poll-q">${esc(poll.q)}</div>
    <div class="poll-sub">${poll.multi ? 'Несколько ответов' : 'Один ответ'} · ${plural(total, 'голос', 'голоса', 'голосов')}</div>
    ${poll.opts.map((o, i) => {
      const n = (votes[i] || []).length, pct = total ? Math.round(n / total * 100) : 0;
      return `<button class="poll-opt ${mine.has(i) ? 'chosen' : ''} ${showResults ? 'res' : ''}" data-vote="${i}" style="--w:${showResults ? pct : 0}%">
        <span class="po-mark">${mine.has(i) ? icon('check') : ''}</span><span class="po-txt">${esc(o)}</span>${showResults ? `<span class="po-pct">${pct}%</span>` : ''}</button>`;
    }).join('')}</div>`;
}
function voiceHtml(m) {
  const v = m.p.voice;
  return `<div class="voice" data-voice="${m.id}" data-dur="${v.dur}">
    <button class="v-play" data-vplay>${icon('play', 'i-play')}${icon('pause', 'i-pause')}</button>
    <div class="v-body"><div class="v-wave" data-vseek>${v.wave.map(h => `<i style="--h:${h}"></i>`).join('')}</div>
    <div class="v-foot"><span class="v-time">${duration(v.dur)}</span><button class="v-speed" data-vspeed>1×</button></div></div></div>`;
}
function fileHtml(m) {
  const f = m.p.file, t = f.type || '';
  if (m.pending && f.local && t.startsWith('image/')) {
    return `<div class="media img uploading" style="aspect-ratio:${f.w}/${f.h}"><img class="ready" src="${f.local}" alt=""><span class="up">${Math.round((m.progress || 0) * 100)}%</span></div>`;
  }
  if (t.startsWith('image/') && f.id) {
    return `<button class="media img" data-open="${m.id}" style="aspect-ratio:${f.w || 4}/${f.h || 3};${f.thumb ? `background-image:url(${esc(f.thumb)})` : ''}"><img data-blob="${m.id}" alt=""></button>`;
  }
  if (t.startsWith('video/') && f.id) {
    return `<button class="media vid" data-video="${m.id}"><span class="vid-play">${icon('play')}</span><span class="vid-cap">${esc(f.name)} · ${size(f.size)}</span></button>`;
  }
  return `<button class="file" data-file="${m.id}" ${m.pending ? 'disabled' : ''}><span class="file-ic">${m.pending ? `<b>${Math.round((m.progress || 0) * 100)}%</b>` : icon('download')}</span>
    <span class="file-txt"><b>${esc(f.name)}</b><small>${size(f.size)} · зашифрован</small></span></button>`;
}

function messageHtml(c, m, prev, next) {
  if (m.kind === 'service') return `<div class="svc"><span>${esc(serviceText(m))}</span></div>`;
  if (m.kind === 'call') {
    const missed = isMissed(m), call = m.meta.call;
    return `<div class="callmsg ${m.from === S.me.id ? 'out' : 'in'} ${missed ? 'missed' : ''}"><span class="cm-ic">${icon(missed ? 'callMissed' : call.video ? 'video' : 'phone')}</span>
      <span class="cm-txt"><b>${esc(callText(m))}</b><small>${hm(m.ts)}</small></span>
      ${c.type === 'direct' ? `<button class="btn ghost sm" data-recall="${call.video ? 1 : 0}">Перезвонить</button>` : ''}</div>`;
  }
  const out = m.from === S.me.id;
  const group = c.type === 'group';
  const first = !sameGroup(prev, m), last = !sameGroup(m, next);
  const u = S.users[m.from] || { name: 'Бывший участник', color: '#999' };
  const p = m.p;
  let content = '', bare = false, emoji = false;
  if (m.err) content = `<div class="locked">${icon('lock')}<span>Не удалось расшифровать: сообщение отправлено до того, как вы присоединились</span></div>`;
  else if (!p) content = '<div class="txt muted">…</div>';
  else {
    if (p.fwd) content += `<div class="fwd">${icon('forward', 'xs')} Переслано от ${esc(p.fwd)}</div>`;
    if (m.replyTo) content += quoteHtml(c, m);
    if (p.poll) content += pollHtml(m);
    else if (p.voice) content += voiceHtml(m);
    else if (p.file) {
      content += fileHtml(m);
      bare = !p.t && !p.fwd && !m.replyTo && (p.file.type || '').startsWith('image/');
    }
    if (p.t) {
      emoji = !p.file && !m.replyTo && !p.fwd && onlyEmoji(p.t);
      content += `<div class="txt">${richText(p.t)}</div>`;
    }
  }
  let state = '';
  if (out && c.type !== 'self') state = m.pending ? icon('clock', 'st') : icon(readByOthers(c, m) ? 'checks' : 'check', 'st ' + (readByOthers(c, m) ? 'read' : ''));
  const meta = `<span class="meta">${m.expiresAt ? icon('timer', 'xs') : ''}${m.pinned ? icon('pin', 'xs') : ''}${m.edited ? 'изм. ' : ''}${hm(m.ts)}${state}</span>`;
  const tools = m.pending ? '' : `<div class="m-tools"><button data-tool="react" title="Реакция">${icon('smile')}</button><button data-tool="reply" title="Ответить">${icon('reply')}</button><button data-tool="more" title="Ещё">${icon('more')}</button></div>`;
  return `<div class="m ${out ? 'out' : 'in'} ${first ? 'first' : ''} ${last ? 'last' : ''} ${m.pending ? 'pending' : ''}" data-id="${m.id}">
    ${group && !out ? `<div class="m-av">${last ? `<button data-person="${m.from}">${avatar(u, 'sm', { ring: false })}</button>` : ''}</div>` : ''}
    <div class="m-col">
      <div class="card ${bare ? 'bare' : ''} ${emoji ? 'emoji' : ''} ${p?.poll ? 'wide' : ''}">
        ${group && !out && first ? `<button class="sender" data-person="${m.from}" style="--c:${u.color}">${esc(u.name)}</button>` : ''}
        ${content}${meta}
      </div>
      ${inlineKb(m)}${reactionsHtml(m)}
    </div>${tools}</div>`;
}

export function renderFeed({ jump, keep } = {}) {
  const c = S.chats[S.current]; if (!c) return;
  const sc = scroller();
  const wasBottom = atBottom();
  const fromBottom = sc.scrollHeight - sc.scrollTop;
  const list = S.msgs[c.id] || [];
  const mark = S.unreadMark[c.id] ?? Infinity;
  const items = [];
  if (S.hasMore[c.id]) items.push({ key: 'more', html: '<div class="loading-more"><i class="spinner"></i></div>' });
  else items.push({ key: 'intro', html: introHtml(c) });
  let sepShown = false;
  for (let i = 0; i < list.length; i++) {
    const m = list[i], prev = list[i - 1], next = list[i + 1];
    if (!prev || !sameDay(prev.ts, m.ts)) items.push({ key: 'd' + new Date(m.ts).toDateString(), html: `<div class="day"><span>${dayLabel(m.ts)}</span></div>` });
    if (!sepShown && typeof m.id === 'number' && m.id > mark && m.from !== S.me.id && m.kind !== 'service') {
      sepShown = true;
      items.push({ key: 'unread', html: '<div class="unread-sep"><span>Новые сообщения</span></div>' });
    }
    items.push({ key: 'm' + m.id, html: messageHtml(c, m, prev, next) });
  }
  const fresh = patch(feed(), items);
  for (const n of fresh) M.hydrate(n, id => msgById(Number(id))?.p?.file);
  M.repaintVoice();
  renderReplyKb();
  if (jump === 'unread') {
    const sep = $('.unread-sep', feed());
    if (sep) sc.scrollTop = sep.offsetTop - 80; else sc.scrollTop = sc.scrollHeight;
  } else if (jump === 'bottom' || (wasBottom && !keep)) sc.scrollTop = sc.scrollHeight;
  else sc.scrollTop = sc.scrollHeight - fromBottom;
  updateJump();
}
function introHtml(c) {
  const bot = c.type === 'direct' && S.users[peerId(c)]?.bot ? S.users[peerId(c)] : null;
  if (bot) return `<div class="intro bot">${avatar(bot, 'lg', { ring: false })}<b>${esc(bot.name)}</b>
    <p>${esc(bot.botInfo?.description || 'Это бот. Отправьте команду, чтобы начать.')}</p>
    <p class="small">${icon('info', 'xs')} Сообщения в этой беседе получает сервер владельца бота.</p>
    ${(S.msgs[c.id] || []).length ? '' : '<button class="btn primary" data-start>Начать</button>'}</div>`;
  if (c.type === 'self') return `<div class="intro">${icon('sparkle')}<b>Заметки</b><p>Сохраняйте сюда мысли, ссылки, голосовые и файлы. Всё шифруется так же, как переписка.</p></div>`;
  if (S.config.escrow) return `<div class="intro warn">${icon('shield')}<b>Шифрование со служебным доступом</b><p>Сообщения и файлы шифруются на ваших устройствах. Кроме ${c.type === 'group' ? 'участников' : 'вас двоих'}, их может расшифровать администрация сервиса — только по законному запросу и с записью в журнал. Звонки не записываются.</p></div>`;
  return `<div class="intro">${icon('lock')}<b>Сквозное шифрование</b><p>Сообщения, файлы и звонки в этой беседе шифруются на ваших устройствах. Ключей нет ни у кого, кроме ${c.type === 'group' ? 'участников' : 'вас двоих'}.</p></div>`;
}

// Keyed DOM reconciliation: untouched messages keep their nodes (and playing audio, loaded images…).
function patch(container, items) {
  const existing = new Map();
  for (const n of container.children) existing.set(n.dataset.key, n);
  let ref = container.firstChild;
  const fresh = [];
  for (const it of items) {
    let n = existing.get(it.key);
    if (n) existing.delete(it.key);
    if (!n || n._html !== it.html) {
      if (n) { if (n === ref) ref = n.nextSibling; n.remove(); }
      n = el(it.html); n.dataset.key = it.key; n._html = it.html; fresh.push(n);
    }
    if (n === ref) ref = n.nextSibling;
    else container.insertBefore(n, ref);
  }
  for (const n of existing.values()) n.remove();
  return fresh;
}

export function atBottom() { const sc = scroller(); return sc.scrollHeight - sc.scrollTop - sc.clientHeight < 60; }
function updateJump() {
  const c = S.chats[S.current];
  $('#jump').classList.toggle('hidden', atBottom());
  const b = $('#jumpCount');
  b.textContent = c?.unread || '';
  b.classList.toggle('hidden', !c?.unread);
}

let loadingMore = false;
async function loadMore() {
  const id = S.current;
  if (!id || loadingMore || !S.hasMore[id]) return;
  loadingMore = true;
  try {
    const first = S.msgs[id].find(m => typeof m.id === 'number');
    const r = await rpc('history', { chatId: id, before: first?.id });
    await decryptAll(r.messages);
    S.msgs[id] = [...r.messages, ...S.msgs[id]];
    S.hasMore[id] = r.hasMore;
    if (S.current === id) renderFeed({ keep: true });
  } catch {}
  loadingMore = false;
}

export function markRead() {
  const c = S.chats[S.current];
  if (!c || hidden() || !atBottom()) return;
  const list = (S.msgs[c.id] || []).filter(m => typeof m.id === 'number');
  const last = list[list.length - 1]; if (!last) return;
  if ((c.reads[S.me.id] || 0) < last.id) {
    c.reads[S.me.id] = last.id;
    rpc('read', { chatId: c.id, msgId: last.id }).catch(() => {});
  }
  if (c.unread) { c.unread = 0; refreshPanel(); }
  updateJump();
}

async function jumpTo(id) {
  let node = $(`.m[data-id="${id}"]`, feed());
  let guard = 0;
  while (!node && S.hasMore[S.current] && guard++ < 20) { await loadMore(); node = $(`.m[data-id="${id}"]`, feed()); }
  if (!node) return toast('Сообщение слишком далеко или удалено');
  node.scrollIntoView({ block: 'center', behavior: 'smooth' });
  node.classList.remove('flash'); void node.offsetWidth; node.classList.add('flash');
}

// ================= bot keyboards & commands =================
const rkHidden = {}; // chatId -> message id whose one-time keyboard was used
function renderReplyKb() {
  const box = $('#replyKb'), c = S.chats[S.current];
  const list = S.msgs[c?.id] || [];
  const last = [...list].reverse().find(m => m.p?.rk && S.users[m.from]?.bot);
  if (!last || last.p.rk.remove || rkHidden[c.id] === last.id) { box.classList.add('hidden'); box.innerHTML = ''; input().placeholder = c?.type === 'self' ? 'Заметка для себя' : 'Сообщение'; return; }
  box.classList.remove('hidden');
  box.dataset.msg = last.id;
  box.innerHTML = last.p.rk.rows.map(r => `<div class="kb-row">${r.map(t => `<button class="kb-btn" data-rk="${esc(t)}">${esc(t)}</button>`).join('')}</div>`).join('');
  if (last.p.rk.ph) input().placeholder = last.p.rk.ph;
}
function botCommands() {
  const c = S.chats[S.current]; if (!c) return [];
  const out = [];
  for (const id of c.members) {
    const u = S.users[id];
    if (u?.bot) for (const cmd of u.botInfo?.commands || []) out.push({ ...cmd, bot: u, suffix: c.type === 'group' ? '@' + u.username : '' });
  }
  return out;
}
function renderCmds() {
  const box = $('#cmdList'), v = input().value;
  const m = /^\/([a-z0-9_]*)$/i.exec(v);
  const list = m ? botCommands().filter(x => x.command.startsWith(m[1].toLowerCase())).slice(0, 8) : [];
  box.classList.toggle('hidden', !list.length);
  box.innerHTML = list.map(x => `<button data-cmd="/${esc(x.command + x.suffix)}"><b>/${esc(x.command)}</b><span>${esc(x.description)}</span>${S.chats[S.current].type === 'group' ? `<small>${esc(x.bot.name)}</small>` : ''}</button>`).join('');
}
async function sendText(text) {
  const c = S.chats[S.current]; if (!c) return;
  await sendPayload(c, { t: text }, {});
}

// ================= composer =================
function autoGrow() { const t = input(); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 180) + 'px'; }
let lastTyping = 0;
function updateSendBtn() {
  const has = !!input().value.trim() || !!S.edit;
  const b = $('#sendBtn');
  b.innerHTML = icon(has ? (S.edit ? 'check' : 'send') : 'mic');
  b.classList.toggle('on', has);
  b.title = has ? 'Отправить' : 'Записать голосовое';
}
function typingPing(kind = 'text') {
  if (!S.current || Date.now() - lastTyping < 3000) return;
  lastTyping = Date.now();
  rpc('typing', { chatId: S.current, kind }).catch(() => {});
}

export function setCtx(mode, m) {
  S.reply = mode === 'reply' ? m : null;
  S.edit = mode === 'edit' ? m : null;
  const box = $('#composeCtx');
  if (!mode) { box.classList.add('hidden'); updateSendBtn(); return; }
  const c = S.chats[S.current];
  box.classList.remove('hidden');
  $('#ctxIc').innerHTML = icon(mode === 'reply' ? 'reply' : 'edit');
  $('#ctxTitle').textContent = mode === 'reply' ? 'Ответ ' + (m.from === S.me.id ? 'себе' : S.users[m.from]?.name || '') : 'Редактирование';
  $('#ctxText').textContent = describe(m, c);
  updateSendBtn();
}

async function submit() {
  const c = S.chats[S.current]; if (!c) return;
  const text = input().value.replace(/^\s+|\s+$/g, '');
  if (S.edit) {
    const m = S.edit;
    if (!text && !m.p.file) return;
    setCtx(null); input().value = ''; autoGrow(); updateSendBtn();
    if (text === m.p.t) return;
    try {
      const box = await encryptPayload(c, { ...m.p, t: text });
      await rpc('edit', { chatId: c.id, id: m.id, ...box });
    } catch (e) { toast(e.message, 'bad'); }
    return;
  }
  if (!text) return startRecording();
  input().value = ''; drafts[c.id] = ''; autoGrow(); renderCmds();
  const replyTo = S.reply?.id; setCtx(null);
  lastTyping = 0;
  await sendPayload(c, { t: text }, { replyTo });
}

async function sendPayload(c, payload, { replyTo, blobs, poll, temp } = {}) {
  const list = S.msgs[c.id] ||= [];
  if (!temp) {
    temp = { id: 't' + Math.random().toString(36).slice(2), chatId: c.id, from: S.me.id, kind: 'msg', p: payload, ts: Date.now(), pending: true, reactions: {}, votes: {}, replyTo };
    list.push(temp);
    if (S.current === c.id) renderFeed({ jump: 'bottom' });
  }
  try {
    const box = await encryptPayload(c, payload);
    temp.ct = box.ct;
    await rpc('send', { chatId: c.id, ...box, replyTo, blobs, poll });
    M.sounds.sent();
  } catch (e) {
    toast(e.message, 'bad');
    if (payload.t && !payload.file && S.current === c.id && !input().value) { input().value = payload.t; autoGrow(); updateSendBtn(); }
  }
  const i = list.indexOf(temp); if (i >= 0) list.splice(i, 1);
  if (S.current === c.id) renderFeed();
}

async function sendFiles(files) {
  const c = S.chats[S.current]; if (!c) return;
  let caption = input().value.trim();
  if (caption) { input().value = ''; autoGrow(); updateSendBtn(); }
  const replyTo = S.reply?.id; setCtx(null);
  for (const file of files) {
    if (file.size > 50 * 1024 * 1024) { toast(`«${file.name}» больше 50 МБ`, 'bad'); continue; }
    const temp = { id: 't' + Math.random().toString(36).slice(2), chatId: c.id, from: S.me.id, kind: 'msg', ts: Date.now(), pending: true, reactions: {}, votes: {}, replyTo, progress: 0 };
    const list = S.msgs[c.id] ||= [];
    try {
      let blob = file, meta = { name: file.name || 'файл', type: file.type || 'application/octet-stream' };
      if (/^image\/(png|jpeg|webp|gif|avif|bmp)$/.test(file.type)) {
        const img = await M.prepareImage(file).catch(() => null); // undecodable images go as plain files
        if (img) { blob = img.blob; Object.assign(meta, { w: img.w, h: img.h, thumb: img.thumb, type: img.type }); }
        else meta.type = 'application/octet-stream';
      }
      temp.p = { t: caption, file: { ...meta, size: blob.size, local: URL.createObjectURL(blob) } };
      list.push(temp);
      if (S.current === c.id) renderFeed({ jump: 'bottom' });
      const up = await M.uploadEncrypted(await blob.arrayBuffer(), p => {
        temp.progress = p;
        const label = $(`.m[data-id="${temp.id}"] .up, .m[data-id="${temp.id}"] .file-ic b`, feed());
        if (label) label.textContent = Math.round(p * 100) + '%';
      });
      const payload = { t: caption, file: { ...meta, size: blob.size, ...up } };
      caption = '';
      await sendPayload(c, payload, { replyTo, blobs: [up.id], temp });
    } catch (e) {
      toast(e.message || 'Не удалось отправить файл', 'bad');
      const i = list.indexOf(temp); if (i >= 0) list.splice(i, 1);
      if (S.current === c.id) renderFeed();
    }
  }
}

// ---------- voice ----------
async function startRecording() {
  if (!S.current) return;
  try {
    await M.startRecording((t, levels) => {
      $('#recTime').textContent = duration(t);
      const bars = levels.slice(-60);
      $('#recWave').innerHTML = bars.map(v => `<i style="--h:${Math.max(2, Math.round(v * 28))}"></i>`).join('');
      if (t > 600) stopAndSend();
      typingPing('voice');
    });
  } catch (e) {
    return toast(e.name === 'NotAllowedError' ? 'Разрешите доступ к микрофону' : e.message, 'bad');
  }
  $('#composeRow').classList.add('hidden');
  $('#recRow').classList.remove('hidden');
}
async function cancelRecording() {
  await M.stopRecording(true);
  $('#recRow').classList.add('hidden');
  $('#composeRow').classList.remove('hidden');
}
async function stopAndSend() {
  const c = S.chats[S.current];
  const r = await M.stopRecording(false);
  $('#recRow').classList.add('hidden');
  $('#composeRow').classList.remove('hidden');
  if (!r || !c) return;
  if (r.duration < 0.7) return toast('Слишком коротко — держите запись подольше');
  const replyTo = S.reply?.id; setCtx(null);
  const temp = { id: 't' + Math.random().toString(36).slice(2), chatId: c.id, from: S.me.id, kind: 'msg', ts: Date.now(), pending: true, reactions: {}, votes: {}, replyTo,
    p: { voice: { dur: r.duration, wave: r.wave }, file: { name: 'voice', type: r.type, size: r.blob.size } } };
  (S.msgs[c.id] ||= []).push(temp);
  renderFeed({ jump: 'bottom' });
  try {
    const up = await M.uploadEncrypted(await r.blob.arrayBuffer());
    await sendPayload(c, { voice: { dur: Math.round(r.duration * 10) / 10, wave: r.wave }, file: { name: 'voice', type: r.type, size: r.blob.size, ...up } }, { replyTo, blobs: [up.id], temp });
  } catch (e) {
    toast(e.message, 'bad');
    const l = S.msgs[c.id]; const i = l.indexOf(temp); if (i >= 0) l.splice(i, 1); renderFeed();
  }
}

// ================= message actions =================
function reactBar(m) {
  return `<div class="quick-reacts">${S.config.reactions.map(e => `<button data-qr="${e}" class="${(m.reactions?.[e] || []).includes(S.me.id) ? 'mine' : ''}">${e}</button>`).join('')}</div>`;
}
async function react(m, emoji) {
  try { await rpc('react', { chatId: m.chatId, id: m.id, emoji }); } catch (e) { toast(e.message); }
}
function reactPicker(m, at) {
  const box = menu(at, [], { top: reactBar(m) });
  box.classList.add('react-menu');
  box.addEventListener('click', e => { const b = e.target.closest('[data-qr]'); if (b) { closeMenu(); react(m, b.dataset.qr); } });
}
function messageMenu(m, at) {
  const c = S.chats[m.chatId];
  const own = m.from === S.me.id;
  const canDelete = own || c.type === 'self' || (c.type === 'group' && c.ownerId === S.me.id);
  const box = menu(at, [
    { icon: 'reply', label: 'Ответить', run: () => startReply(m) },
    own && m.p && !m.p.poll && !m.p.voice ? { icon: 'edit', label: 'Изменить', run: () => startEdit(m) } : null,
    m.p?.t ? { icon: 'copy', label: 'Скопировать текст', run: () => navigator.clipboard?.writeText(m.p.t).then(() => toast('Скопировано')) } : null,
    m.p ? { icon: 'forward', label: 'Переслать', run: () => forward(m) } : null,
    { icon: 'pin', label: m.pinned ? 'Открепить' : 'Закрепить', run: () => rpc('pin', { chatId: c.id, id: m.id, pinned: !m.pinned }).catch(e => toast(e.message)) },
    m.p?.file && !m.p.voice ? { icon: 'download', label: 'Сохранить файл', run: () => M.saveFile(m.p.file) } : null,
    canDelete ? '-' : null,
    canDelete ? { icon: 'trash', label: 'Удалить у всех', danger: true, run: () => removeMsg(m) } : null,
  ], { top: m.p ? reactBar(m) : '' });
  box.addEventListener('click', e => { const b = e.target.closest('[data-qr]'); if (b) { closeMenu(); react(m, b.dataset.qr); } });
}
async function removeMsg(m) {
  if (!await confirmBox('Удалить сообщение?', 'Оно исчезнет у всех участников беседы.', 'Удалить')) return;
  rpc('delete', { chatId: m.chatId, ids: [m.id] }).catch(e => toast(e.message, 'bad'));
}
function startReply(m) {
  if (S.edit) { input().value = ''; autoGrow(); }
  setCtx('reply', m); input().focus();
}
function startEdit(m) {
  setCtx('edit', m);
  input().value = m.p.t || ''; autoGrow(); updateSendBtn(); input().focus();
  input().setSelectionRange(input().value.length, input().value.length);
}
async function forward(m) {
  const target = await chooseChat('Переслать в…');
  const c = S.chats[target]; if (!c) return;
  try {
    const payload = { ...m.p, fwd: m.p.fwd || (m.from === S.me.id ? S.me.name : S.users[m.from]?.name || 'неизвестно') };
    let blobs;
    if (payload.file?.id) { const id = await M.reupload(payload.file); payload.file = { ...payload.file, id }; blobs = [id]; }
    const poll = payload.poll ? { count: payload.poll.opts.length, multiple: payload.poll.multi } : undefined;
    const box = await encryptPayload(c, payload);
    await rpc('send', { chatId: c.id, ...box, blobs, poll });
    toast('Переслано в «' + chatTitle(c) + '»');
  } catch (e) { toast(e.message, 'bad'); }
}
async function vote(m, i) {
  const poll = m.p.poll;
  const mine = new Set(Object.entries(m.votes || {}).filter(([, ids]) => ids.includes(S.me.id)).map(([o]) => Number(o)));
  let next;
  if (poll.multi) { mine.has(i) ? mine.delete(i) : mine.add(i); next = [...mine]; }
  else next = mine.has(i) ? [] : [i];
  try { await rpc('vote', { chatId: m.chatId, id: m.id, options: next }); } catch (e) { toast(e.message); }
}

// ================= details panel =================
export function toggleDetails(on = !S.details) {
  S.details = on;
  document.body.classList.toggle('details-open', on);
  $('#detailsBtn')?.classList.toggle('on', on);
  if (on) renderDetails();
}
export async function renderDetails() {
  const d = $('#details');
  const c = S.chats[S.current];
  if (!S.details || !c) return;
  const st = statusOf(c);
  const direct = c.type === 'direct', group = c.type === 'group';
  const peer = direct ? S.users[peerId(c)] : null;
  const owner = group && c.ownerId === S.me.id;
  const media = (S.msgs[c.id] || []).filter(m => m.p?.file?.id && (m.p.file.type || '').startsWith('image/')).slice(-9).reverse();
  const focused = document.activeElement?.id === 'grpTitle';
  if (focused) return;
  d.innerHTML = `
    <header class="d-head"><b>${direct ? 'Профиль' : group ? 'Группа' : 'Заметки'}</b><button class="icon-btn" data-d="close" title="Закрыть">${icon('close')}</button></header>
    <div class="d-scroll">
      <div class="d-hero">${chatAvatar(c, 'xl')}<h2>${esc(chatTitle(c))}${botChip(peer)}</h2><p class="${st.on ? 'online' : ''}">${esc(direct ? '@' + peer.username + ' · ' + st.text : st.text)}</p>
        ${peer?.bio ? `<p class="bio">${esc(peer.bio)}</p>` : ''}</div>
      ${direct && peer?.bot ? `<section class="d-card"><div class="d-title">${icon('sparkle')}<b>Бот</b></div>
        <p class="muted small">${esc(peer.botInfo?.description || 'Описание не задано.')}</p>
        ${peer.botInfo?.commands?.length ? `<div class="d-cmds">${peer.botInfo.commands.map(x => `<button data-dcmd="/${esc(x.command)}"><b>/${esc(x.command)}</b> ${esc(x.description)}</button>`).join('')}</div>` : ''}
        <p class="muted small">Сообщения в этой беседе получает сервер владельца бота.</p></section>` : ''}
      ${direct && !peer?.bot ? `<div class="d-actions">
        <button class="act" data-d="call">${icon('phone')}<span>Звонок</span></button>
        <button class="act" data-d="video">${icon('video')}<span>Видео</span></button>
        <button class="act" data-d="person">${icon('me')}<span>Профиль</span></button></div>` : ''}
      ${group ? `<div class="d-actions">
        <button class="act" data-d="add">${icon('userPlus')}<span>Пригласить</span></button>
        <button class="act danger" data-d="leave">${icon('logout')}<span>Покинуть</span></button></div>` : ''}
      <section class="d-card secure">
        <div class="d-title">${icon('shield')}<b>${S.config.escrow ? 'Шифрование' : 'Сквозное шифрование'}</b></div>
        ${S.config.escrow ? '<p class="muted small">У администрации сервиса есть служебный ключ: по законному запросу содержимое может быть раскрыто. Каждый доступ записывается в журнал.</p>' : ''}
        ${direct ? `<div class="mini-code" id="miniCode"><span class="muted">…</span></div><button class="link" data-d="safety">Сверить код безопасности</button>`
          : `<p class="muted">${group ? `Ключ группы — версия ${c.keyVersion}. Он обновляется при каждом изменении состава.` : (S.config.escrow ? 'Заметки зашифрованы так же, как переписка.' : 'Заметки зашифрованы ключом, который есть только на ваших устройствах.')}</p>`}
      </section>
      ${c.type !== 'self' ? `<section class="d-card">
        <div class="d-title">${icon('timer')}<b>Исчезающие сообщения</b></div>
        <div class="ttl-opts">${S.config.ttl.map(t => `<button data-ttl="${t}" class="${c.ttl === t ? 'on' : ''}">${t ? ttlShort(t) : 'Выкл'}</button>`).join('')}</div>
        <p class="muted small">${c.ttl ? `Новые сообщения удаляются через ${ttlLabel(c.ttl).toLowerCase()} — у всех и с сервера.` : 'Сообщения хранятся, пока их не удалят.'}</p>
      </section>` : ''}
      ${group ? `<section class="d-card">
        <div class="d-title">${icon('hash')}<b>Название</b></div>
        <div class="inline-edit"><input id="grpTitle" maxlength="64" value="${esc(c.title)}"><button class="btn ghost sm" data-d="rename">Сохранить</button></div>
      </section>
      <section class="d-card">
        <div class="d-title">${icon('people')}<b>${plural(c.members.length, 'участник', 'участника', 'участников')}</b></div>
        <div class="d-members">${c.members.map(id => S.users[id]).filter(Boolean).sort((a, b) => (b.id === c.ownerId) - (a.id === c.ownerId) || b.online - a.online)
          .map(u => `<div class="d-member" data-person="${u.id}">${avatar(u, 'sm')}<span class="grow"><b>${esc(u.name)}${u.id === S.me.id ? ' (вы)' : ''}</b><small class="${u.online ? 'online' : ''}">${esc(seen(u))}</small></span>
            ${u.id === c.ownerId ? `<span class="owner" title="Создатель">${icon('crown')}</span>` : owner ? `<button class="icon-btn sm" data-kick="${u.id}" title="Исключить">${icon('userMinus')}</button>` : ''}</div>`).join('')}</div>
      </section>` : ''}
      ${c.pins?.length ? `<section class="d-card"><div class="d-title">${icon('pin')}<b>Закреплённые</b></div>
        ${c.pins.map(p => `<button class="d-pin" data-goto="${p.id}"><b>${esc(userName(p.from))}</b><span>${esc(describe(p, c))}</span></button>`).join('')}</section>` : ''}
      ${media.length ? `<section class="d-card"><div class="d-title">${icon('image')}<b>Фото</b></div>
        <div class="d-media">${media.map(m => `<button data-open="${m.id}" style="${m.p.file.thumb ? `background-image:url(${esc(m.p.file.thumb)})` : ''}"><img data-blob="${m.id}" alt=""></button>`).join('')}</div></section>` : ''}
    </div>`;
  M.hydrate(d, id => msgById(Number(id))?.p?.file);
  if (direct && peer) {
    const code = await safetyCode(S.me, peer);
    const box = $('#miniCode', d);
    if (box) box.innerHTML = code.emoji.map(e => `<span>${e}</span>`).join('');
  }
}

// ================= wiring =================
export function initConversation() {
  $('#backBtn').innerHTML = icon('back');
  $('#audioCallBtn').innerHTML = icon('phone');
  $('#videoCallBtn').innerHTML = icon('video');
  $('#detailsBtn').innerHTML = icon('info');
  $('#attachBtn').innerHTML = icon('attach');
  $('#ctxClose').innerHTML = icon('close');
  $('#recCancel').innerHTML = icon('trash');
  $('#recSend').innerHTML = icon('send');
  $('#jump .ic').innerHTML = icon('down');
  updateSendBtn();

  $('#backBtn').onclick = closeChat;
  $('#who').onclick = () => toggleDetails(true);
  $('#detailsBtn').onclick = () => toggleDetails();
  $('#audioCallBtn').onclick = () => App.startCall(S.current, false);
  $('#videoCallBtn').onclick = () => App.startCall(S.current, true);
  $('#jump').onclick = () => {
    const c = S.chats[S.current];
    if (c?.unread && $('.unread-sep', feed())) { S.unreadMark[c.id] = c.reads[S.me.id] || 0; }
    scroller().scrollTo({ top: scroller().scrollHeight, behavior: 'smooth' });
  };
  $('#pinbar').onclick = e => {
    const c = S.chats[S.current];
    const x = e.target.closest('[data-unpin]');
    if (x) return rpc('pin', { chatId: c.id, id: Number(x.dataset.unpin), pinned: false }).catch(er => toast(er.message));
    jumpTo(Number($('#pinbar').dataset.id));
    pinIndex++; renderPins();
  };
  scroller().addEventListener('scroll', () => {
    updateJump();
    if (atBottom()) markRead();
    if (scroller().scrollTop < 400) loadMore();
  }, { passive: true });

  // composer
  const t = input();
  t.addEventListener('input', () => {
    autoGrow(); updateSendBtn();
    if (S.current) drafts[S.current] = t.value;
    if (t.value.trim() && !S.edit) typingPing();
    renderCmds();
  });
  t.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && fine()) { e.preventDefault(); if (t.value.trim() || S.edit) submit(); }
    if (e.key === 'ArrowUp' && !t.value) {
      const mine = [...(S.msgs[S.current] || [])].reverse().find(m => m.from === S.me.id && m.kind === 'msg' && m.p && !m.p.poll && !m.p.voice && !m.pending);
      if (mine) { e.preventDefault(); startEdit(mine); }
    }
    if (e.key === 'Escape' && (S.reply || S.edit)) { e.stopPropagation(); if (S.edit) { t.value = ''; autoGrow(); } setCtx(null); }
  });
  t.addEventListener('paste', e => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); sendFiles(files); }
  });
  $('#sendBtn').onclick = () => submit();
  $('#cmdList').onclick = e => { const b = e.target.closest('[data-cmd]'); if (b) { t.value = ''; autoGrow(); renderCmds(); updateSendBtn(); sendText(b.dataset.cmd); } };
  $('#replyKb').onclick = e => {
    const b = e.target.closest('[data-rk]'); if (!b) return;
    const c = S.chats[S.current], mid = Number($('#replyKb').dataset.msg);
    const m = msgById(mid);
    if (m?.p?.rk?.once) rkHidden[c.id] = mid;
    sendText(b.dataset.rk);
  };
  $('#ctxClose').onclick = () => { if (S.edit) { t.value = ''; autoGrow(); } setCtx(null); };
  $('#recCancel').onclick = cancelRecording;
  $('#recSend').onclick = stopAndSend;
  $('#attachBtn').onclick = e => menu(e.currentTarget, [
    { icon: 'image', label: 'Фото, видео или файл', run: () => $('#fileInput').click() },
    S.chats[S.current]?.type !== 'self' || true ? { icon: 'poll', label: 'Опрос', run: async () => {
      const c = S.chats[S.current]; const p = await newPoll(); if (!p || !c) return;
      sendPayload(c, { poll: p }, { poll: { count: p.opts.length, multiple: p.multi } });
    } } : null,
  ]);
  $('#fileInput').onchange = e => { const f = [...e.target.files]; e.target.value = ''; if (f.length) sendFiles(f); };

  // drag & drop
  const stage = $('#stage');
  let depth = 0;
  stage.addEventListener('dragenter', e => { if (S.current && e.dataTransfer.types.includes('Files')) { e.preventDefault(); if (depth++ === 0) stage.classList.add('dropping'); } });
  stage.addEventListener('dragover', e => { if (S.current) e.preventDefault(); });
  stage.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; stage.classList.remove('dropping'); } });
  stage.addEventListener('drop', e => { e.preventDefault(); depth = 0; stage.classList.remove('dropping'); const f = [...e.dataTransfer.files]; if (f.length && S.current) sendFiles(f); });

  // feed interactions
  const f = feed();
  f.addEventListener('click', async e => {
    const node = e.target.closest('.m');
    const m = node && msgById(isNaN(node.dataset.id) ? node.dataset.id : Number(node.dataset.id));
    const tgt = e.target;
    if (tgt.closest('.mention')) {
      e.preventDefault();
      const name = tgt.closest('.mention').dataset.mention.toLowerCase();
      if (name === S.me.username.toLowerCase()) return App.setTab('me');
      const r = await rpc('searchUsers', { q: name }).catch(() => []);
      const u = r.find(x => x.username.toLowerCase() === name);
      return u ? personCard(u) : toast('Пользователь не найден');
    }
    const person = tgt.closest('[data-person]');
    if (person) return personCard(S.users[person.dataset.person]);
    if (tgt.closest('[data-start]')) return sendText('/start');
    const recall = tgt.closest('[data-recall]');
    if (recall) return App.startCall(S.current, recall.dataset.recall === '1');
    if (!m || m.pending) return;
    const tool = tgt.closest('[data-tool]')?.dataset.tool;
    if (tool === 'react') return reactPicker(m, tgt.closest('button'));
    if (tool === 'reply') return startReply(m);
    if (tool === 'more') return messageMenu(m, tgt.closest('button'));
    const r = tgt.closest('[data-react]'); if (r) return react(m, r.dataset.react);
    const cb = tgt.closest('[data-cb]');
    if (cb) {
      const [ri, ci] = cb.dataset.cb.split(':').map(Number);
      const data = m.p?.kb?.[ri]?.[ci]?.d;
      cb.classList.add('busy');
      try { await rpc('botCallback', { chatId: m.chatId, id: m.id, data }); } catch (x) { toast(x.message, 'bad'); }
      setTimeout(() => cb.classList.remove('busy'), 600);
      return;
    }
    const q = tgt.closest('[data-goto]'); if (q) return jumpTo(Number(q.dataset.goto));
    const v = tgt.closest('[data-vote]'); if (v) return vote(m, Number(v.dataset.vote));
    if (tgt.closest('[data-vspeed]')) return M.cycleSpeed();
    if (tgt.closest('[data-vplay]')) return M.toggleVoice(m.id, m.p.file, m.p.voice.dur);
    const seek = tgt.closest('[data-vseek]');
    if (seek) { const rc = seek.getBoundingClientRect(); return M.toggleVoice(m.id, m.p.file, m.p.voice.dur, Math.max(0, Math.min(1, (e.clientX - rc.left) / rc.width))); }
    if (tgt.closest('[data-open]')) { const img = $('img', tgt.closest('[data-open]')); if (img?.src) lightbox(img.src, m.p.t || ''); return; }
    const vid = tgt.closest('[data-video]');
    if (vid) {
      vid.classList.add('loading');
      try { const u = await M.blobUrl(m.p.file); vid.replaceWith(el(`<video class="media vid-el" src="${u}" controls autoplay playsinline></video>`)); }
      catch { toast('Не удалось открыть видео', 'bad'); vid.classList.remove('loading'); }
      return;
    }
    if (tgt.closest('[data-file]')) return M.saveFile(m.p.file);
  });
  f.addEventListener('dblclick', e => {
    const node = e.target.closest('.m');
    if (!node || e.target.closest('a,button,video,.voice,.poll')) return;
    const m = msgById(Number(node.dataset.id));
    if (m && !m.pending) react(m, S.config.reactions[0] || '👍');
  });
  f.addEventListener('contextmenu', e => {
    const node = e.target.closest('.m'); if (!node || e.target.closest('a,video')) return;
    const m = msgById(Number(node.dataset.id)); if (!m || m.pending) return;
    e.preventDefault();
    messageMenu(m, { x: e.clientX, y: e.clientY });
  });
  let press;
  f.addEventListener('touchstart', e => {
    const node = e.target.closest('.m'); if (!node || e.target.closest('button,a,video')) return;
    const t0 = e.touches[0];
    press = setTimeout(() => {
      const m = msgById(Number(node.dataset.id));
      if (m && !m.pending) { navigator.vibrate?.(12); messageMenu(m, { x: t0.clientX, y: t0.clientY }); }
    }, 450);
  }, { passive: true });
  for (const ev of ['touchend', 'touchmove', 'touchcancel']) f.addEventListener(ev, () => clearTimeout(press), { passive: true });
  // swipe-to-reply on touch
  let sx = null, sy = 0, snode = null;
  f.addEventListener('touchstart', e => { const n = e.target.closest('.m'); if (n) { sx = e.touches[0].clientX; sy = e.touches[0].clientY; snode = n; } }, { passive: true });
  f.addEventListener('touchmove', e => {
    if (sx == null) return;
    const dx = e.touches[0].clientX - sx, dy = Math.abs(e.touches[0].clientY - sy);
    if (dy > 30) { sx = null; snode.style.transform = ''; return; }
    if (dx < 0) snode.style.transform = `translateX(${Math.max(dx, -70)}px)`;
  }, { passive: true });
  f.addEventListener('touchend', e => {
    if (sx == null) return;
    const dx = e.changedTouches[0].clientX - sx;
    snode.style.transform = '';
    if (dx < -55) { const m = msgById(Number(snode.dataset.id)); if (m && !m.pending) startReply(m); }
    sx = null;
  });

  // details panel
  $('#details').addEventListener('click', async e => {
    const c = S.chats[S.current]; if (!c) return;
    const a = e.target.closest('[data-d]')?.dataset.d;
    if (a === 'close') return toggleDetails(false);
    const dc = e.target.closest('[data-dcmd]'); if (dc) return sendText(dc.dataset.dcmd);
    if (a === 'call' || a === 'video') return App.startCall(c.id, a === 'video');
    if (a === 'person') return personCard(S.users[peerId(c)]);
    if (a === 'safety') return safetyModal(S.users[peerId(c)]);
    if (a === 'rename') { try { await rpc('renameGroup', { chatId: c.id, title: $('#grpTitle').value }); toast('Название сохранено'); $('#grpTitle').blur(); } catch (x) { toast(x.message, 'bad'); } return; }
    if (a === 'add') {
      const r = await pickPeople({ title: 'Пригласить в группу', sub: 'Для группы будет создан новый ключ', ok: 'Пригласить', exclude: c.members });
      if (r?.ids.length) { try { await addMembersEncrypted(c, r.ids); } catch (x) { toast(x.message, 'bad'); } }
      return;
    }
    if (a === 'leave') {
      if (await confirmBox('Покинуть группу?', `Вы больше не будете получать сообщения «${c.title}».`, 'Покинуть')) rpc('leaveChat', { chatId: c.id }).catch(x => toast(x.message, 'bad'));
      return;
    }
    const kick = e.target.closest('[data-kick]');
    if (kick) {
      const u = S.users[kick.dataset.kick];
      if (await confirmBox('Исключить участника?', `${u.name} больше не увидит новые сообщения группы.`, 'Исключить')) rpc('removeMember', { chatId: c.id, userId: u.id }).catch(x => toast(x.message, 'bad'));
      return;
    }
    const ttl = e.target.closest('[data-ttl]');
    if (ttl) return rpc('setTtl', { chatId: c.id, ttl: Number(ttl.dataset.ttl) }).catch(x => toast(x.message, 'bad'));
    const person = e.target.closest('[data-person]'); if (person) return personCard(S.users[person.dataset.person]);
    const g = e.target.closest('[data-goto]'); if (g) { if (innerWidth < 1100) toggleDetails(false); return jumpTo(Number(g.dataset.goto)); }
    const o = e.target.closest('[data-open]');
    if (o) { const img = $('img', o); if (img?.src) lightbox(img.src); }
  });
  document.addEventListener('voice-ended', e => {
    // autoplay the next voice message in the same chat
    const list = S.msgs[S.current] || [];
    const i = list.findIndex(m => m.id === e.detail);
    const next = list.slice(i + 1).find(m => m.p?.voice);
    if (i >= 0 && next && next === list.slice(i + 1).find(m => m.kind === 'msg')) M.toggleVoice(next.id, next.p.file, next.p.voice.dur);
  });
}

export const msgIndex = msgById;
