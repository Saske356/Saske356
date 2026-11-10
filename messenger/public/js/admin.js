// Lawful-access console. The escrow private key is unsealed in this browser tab only and kept in memory.
import * as C from './crypto.js';
import { $, $$, el, esc, icon, toast, hm, duration, size } from './util.js';

const A = { token: null, me: null, users: {}, chat: null, keys: new Map(), msgs: [], hasMore: false, reason: '', urls: new Map() };
const ESCROW = { id: 0 };

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(A.token ? { Authorization: 'Bearer ' + A.token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && A.token) { lock('Сеанс истёк — войдите снова'); throw new Error('Сеанс истёк'); }
  if (!res.ok) throw new Error(data.error || 'Ошибка сервера');
  return data;
}

// ---------- gate ----------
let setupToken = null;
async function gate() {
  const st = await api('/api/admin/status');
  const m = /setup=([a-f0-9]{32})/.exec(location.hash);
  setupToken = !st.configured && m ? m[1] : null;
  $('#gate').classList.remove('hidden');
  $('#gate').classList.toggle('setup', !!setupToken);
  if (!st.configured && !setupToken) {
    $('#gateTitle').textContent = 'Доступ не настроен';
    $('#gateSub').textContent = 'Откройте ссылку настройки из журнала запуска сервера.';
    $('#gateForm').classList.add('hidden');
    return;
  }
  $('#gateTitle').textContent = setupToken ? 'Настройка служебного доступа' : 'Служебный доступ';
  $('#gateSub').textContent = setupToken ? 'Будет создан служебный ключ. С этого момента новые ключи бесед будут депонироваться для него.' : 'Введите фразу доступа администратора.';
  $('#gateBtn').textContent = setupToken ? 'Создать ключ' : 'Войти';
  $('#gateForm').elements.pass.focus();
}
$('#gateForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.target.elements, err = $('#gateErr'), btn = $('#gateBtn');
  err.textContent = '';
  const pass = f.pass.value;
  if (setupToken) {
    if (pass.length < 12) return (err.textContent = 'Не меньше 12 символов');
    if (pass !== f.pass2.value) return (err.textContent = 'Фразы не совпадают');
  }
  btn.disabled = true;
  try {
    const { auth, encKey } = await C.credentials('orbita-admin', pass);
    let r, privateKey;
    if (setupToken) {
      const id = await C.newIdentity(encKey);
      r = await api('/api/admin/setup', { token: setupToken, auth, publicKey: id.publicKey, sealedKey: id.sealedKey });
      privateKey = id.privateKey;
      history.replaceState(null, '', '/admin');
    } else {
      r = await api('/api/admin/login', { auth });
      privateKey = await C.openIdentity(encKey, r.sealedKey);
    }
    A.token = r.token;
    Object.assign(ESCROW, { privateKey, publicKey: r.publicKey });
    e.target.reset();
    $('#gate').classList.add('hidden');
    $('#adm').classList.remove('hidden');
    loadUsers('');
  } catch (x) { err.textContent = x.message; }
  btn.disabled = false;
};
function lock(msg) {
  A.token = null; ESCROW.privateKey = null; A.keys.clear();
  $('#adm').classList.add('hidden');
  $('#admChat').innerHTML = '';
  gate();
  if (msg) toast(msg);
}
$('#admOut').onclick = async () => { await api('/api/admin/logout', {}).catch(() => {}); lock(); };
$('#admTabs').onclick = e => {
  const b = e.target.closest('[data-t]'); if (!b) return;
  $$('#admTabs button').forEach(x => x.classList.toggle('on', x === b));
  $('#admUsers').classList.toggle('hidden', b.dataset.t !== 'users');
  $('#admAudit').classList.toggle('hidden', b.dataset.t !== 'audit');
  if (b.dataset.t === 'audit') loadAudit();
};

// ---------- users ----------
let qt;
$('#admQ').oninput = e => { clearTimeout(qt); qt = setTimeout(() => loadUsers(e.target.value), 200); };
async function loadUsers(q) {
  const list = await api('/api/admin/users', { q });
  for (const u of list) A.users[u.id] = u;
  $('#admUserList').innerHTML = list.map(u => `<button class="adm-user" data-u="${u.id}"><b>${esc(u.name)}</b><small>@${esc(u.username)} · бесед: ${u.chats} · сообщений: ${u.sent}</small></button>`).join('') || '<div class="empty-note">Никого</div>';
}
$('#admUserList').onclick = async e => {
  const b = e.target.closest('[data-u]'); if (!b) return;
  $$('.adm-user').forEach(x => x.classList.toggle('on', x === b));
  const r = await api('/api/admin/user', { userId: Number(b.dataset.u) });
  const u = r.user;
  $('#admUser').innerHTML = `<div class="adm-card"><h2>${esc(u.name)}</h2><p class="muted">@${esc(u.username)} · id ${u.id}</p>
    <p class="muted small">Зарегистрирован ${new Date(u.createdAt).toLocaleString('ru-RU')}<br>${u.online ? 'Сейчас в сети' : 'Был в сети ' + new Date(u.lastSeen).toLocaleString('ru-RU')}</p></div>
    <h3 class="sect">Беседы</h3>
    ${r.chats.map(c => `<button class="adm-chat" data-c="${c.id}"><b>${esc(c.type === 'self' ? 'Заметки' : c.type === 'group' ? c.title : c.members.map(m => m.name).join(' ↔ '))}</b>
      <small>${c.type === 'group' ? 'группа · ' + c.members.length + ' участн. · ' : c.type === 'direct' ? 'личная · ' : ''}сообщений: ${c.total}${c.lastAt ? ' · ' + new Date(c.lastAt).toLocaleDateString('ru-RU') : ''}</small>
      ${c.escrowVersions ? '' : '<small class="missed">служебного ключа ещё нет — появится, когда участник откроет беседу</small>'}</button>`).join('') || '<div class="empty-note">Бесед нет</div>'}`;
};
$('#admUser').onclick = e => { const b = e.target.closest('[data-c]'); if (b) askReason(Number(b.dataset.c)); };

function askReason(chatId) {
  const back = el(`<div class="modal-back in"><div class="modal small"><div class="m-head"><div><h2>Основание доступа</h2><p class="muted">Будет записано в журнал вместе со временем и адресом</p></div></div>
    <div class="m-body"><label class="field"><span>Основание</span><textarea id="reason" rows="3" maxlength="300" placeholder="Например: запрос ГУ МВД № 12/345 от 01.11.2026"></textarea></label></div>
    <div class="m-foot"><button class="btn ghost" data-x>Отмена</button><button class="btn primary" data-ok>Открыть беседу</button></div></div></div>`);
  $('#layer').appendChild(back);
  back.querySelector('textarea').focus();
  back.onclick = async e => {
    if (e.target.closest('[data-x]') || e.target === back) return back.remove();
    if (!e.target.closest('[data-ok]')) return;
    const reason = $('#reason', back).value.trim();
    if (reason.length < 5) return toast('Укажите основание');
    back.remove();
    openChat(chatId, reason).catch(x => toast(x.message, 'bad'));
  };
}

// ---------- conversation ----------
async function keyFor(v) {
  if (!A.keys.has(v)) {
    const k = A.chatKeys.find(x => x.v === v);
    if (!k) return null;
    const wrapper = A.users[k.from];
    A.keys.set(v, C.openChatKey(ESCROW, wrapper, v, k).catch(() => null));
  }
  return A.keys.get(v);
}
async function decryptAll(list) {
  for (const m of list) {
    if (m.kind !== 'msg' || m.p || m.err) continue;
    const key = await keyFor(m.kv);
    if (!key) { m.err = 'nokey'; continue; }
    try { m.p = await C.decryptJson(key, m, `msg:${m.chatId}`); } catch { m.err = 'bad'; }
  }
}
async function openChat(chatId, reason) {
  A.keys.clear(); A.reason = reason;
  const r = await api('/api/admin/chat', { chatId, reason });
  A.chat = r.chat; A.chatKeys = r.keys;
  for (const u of r.users) A.users[u.id] = { ...A.users[u.id], ...u };
  await decryptAll(r.messages);
  A.msgs = r.messages; A.hasMore = r.hasMore;
  drawChat();
}
async function loadEarlier() {
  const r = await api('/api/admin/chat', { chatId: A.chat.id, reason: A.reason, before: A.msgs[0]?.id });
  for (const u of r.users) A.users[u.id] = { ...A.users[u.id], ...u };
  await decryptAll(r.messages);
  A.msgs = [...r.messages, ...A.msgs]; A.hasMore = r.hasMore;
  drawChat();
}
const uname = id => A.users[id] ? `${A.users[id].name} (@${A.users[id].username})` : `id ${id}`;
function serviceText(m) {
  const e = m.meta || {};
  return { created: `создал(а) группу «${e.title}»`, added: 'пригласил(а): ' + (e.users || []).map(uname).join(', '), removed: 'исключил(а): ' + (e.users || []).map(uname).join(', '),
    left: 'покинул(а) группу', renamed: `переименовал(а) в «${e.title}»`, ttl: e.ttl ? `включил(а) исчезающие сообщения (${e.ttl} с)` : 'выключил(а) исчезающие сообщения', pinned: 'закрепил(а) сообщение' }[e.event] || e.event;
}
function callText(m) {
  const c = m.meta.call;
  return `${c.video ? 'Видеозвонок' : 'Звонок'} от ${uname(m.from)} — ${{ ended: 'состоялся, ' + duration(c.duration), declined: 'отклонён', busy: 'абонент занят', missed: 'без ответа' }[c.status]} (содержимое не записывается)`;
}
function contentHtml(m) {
  if (m.kind === 'service') return `<i class="muted">${esc(serviceText(m))}</i>`;
  if (m.kind === 'call') return `<i class="muted">${esc(callText(m))}</i>`;
  if (m.err === 'nokey') return '<i class="missed">нет служебного ключа для этой версии — сообщение отправлено до включения доступа</i>';
  if (m.err) return '<i class="missed">не удалось расшифровать</i>';
  const p = m.p; let h = '';
  if (p.fwd) h += `<div class="muted small">переслано от ${esc(p.fwd)}</div>`;
  if (m.replyTo) h += `<div class="muted small">ответ на #${m.replyTo}</div>`;
  if (p.poll) h += `<div><b>Опрос:</b> ${esc(p.poll.q)}<ul>${p.poll.opts.map((o, i) => `<li>${esc(o)} — ${(m.votes?.[i] || []).map(uname).join(', ') || 'нет голосов'}</li>`).join('')}</ul></div>`;
  if (p.file) {
    const t = p.file.type || '';
    if (p.voice) h += `<div class="adm-file">Голосовое ${duration(p.voice.dur)} <button class="btn ghost sm" data-play="${m.id}">Прослушать</button></div>`;
    else if (t.startsWith('image/')) h += `<button class="adm-img" data-img="${m.id}">${p.file.thumb ? `<img src="${esc(p.file.thumb)}" alt="">` : ''}<span>Показать фото</span></button>`;
    else h += `<div class="adm-file">${esc(p.file.name)} · ${size(p.file.size)} <button class="btn ghost sm" data-dl="${m.id}">Скачать</button></div>`;
  }
  if (p.t) h += `<div class="txt">${esc(p.t)}</div>`;
  return h;
}
function drawChat() {
  const c = A.chat;
  const title = c.type === 'group' ? c.title : c.type === 'self' ? 'Заметки ' + uname(c.members[0]) : c.members.map(uname).join(' ↔ ');
  $('#admChat').innerHTML = `<div class="adm-card"><h2>${esc(title)}</h2>
    <p class="muted small">Беседа #${c.id} · создана ${new Date(c.createdAt).toLocaleString('ru-RU')} · участники: ${c.members.map(uname).map(esc).join(', ')}</p>
    <p class="muted small">Основание: ${esc(A.reason)}</p>
    <div class="adm-actions"><button class="btn primary sm" data-exp="html">Выгрузить HTML</button><button class="btn ghost sm" data-exp="json">Выгрузить JSON</button></div></div>
    ${A.hasMore ? '<button class="btn ghost sm wide" data-more>Загрузить более ранние</button>' : ''}
    <div class="adm-transcript">${A.msgs.map(m => `<div class="adm-msg k-${m.kind}"><span class="adm-ts">${new Date(m.ts).toLocaleString('ru-RU')}</span>
      <span class="adm-from">${m.kind === 'msg' ? esc(uname(m.from)) : ''}</span><div class="adm-content">${contentHtml(m)}${m.edited ? ' <span class="muted small">(изм.)</span>' : ''}</div></div>`).join('') || '<div class="empty-note">Сообщений нет</div>'}</div>`;
}
async function fileUrl(f) {
  if (!A.urls.has(f.id)) {
    const res = await fetch('/blob/' + f.id, { headers: { Authorization: 'Bearer ' + A.token } });
    if (!res.ok) throw new Error('Файл недоступен (удалён?)');
    const buf = await C.decryptFile(await res.arrayBuffer(), f.key, f.iv);
    A.urls.set(f.id, URL.createObjectURL(new Blob([buf], { type: f.type })));
  }
  return A.urls.get(f.id);
}
$('#admChat').onclick = async e => {
  const t = e.target;
  const find = id => A.msgs.find(m => m.id === Number(id));
  try {
    if (t.closest('[data-more]')) return loadEarlier();
    const img = t.closest('[data-img]');
    if (img) { const u = await fileUrl(find(img.dataset.img).p.file); img.outerHTML = `<a href="${u}" target="_blank"><img class="adm-full" src="${u}" alt=""></a>`; return; }
    const pl = t.closest('[data-play]');
    if (pl) { const u = await fileUrl(find(pl.dataset.play).p.file); pl.outerHTML = `<audio src="${u}" controls autoplay></audio>`; return; }
    const dl = t.closest('[data-dl]');
    if (dl) { const f = find(dl.dataset.dl).p.file; const a = document.createElement('a'); a.href = await fileUrl(f); a.download = f.name; a.click(); return; }
    const ex = t.closest('[data-exp]');
    if (ex) return exportChat(ex.dataset.exp);
  } catch (x) { toast(x.message, 'bad'); }
};

// ---------- export ----------
async function exportChat(kind) {
  while (A.hasMore) await loadEarlier();
  await api('/api/admin/export-log', { chatId: A.chat.id, reason: A.reason });
  const c = A.chat;
  const record = {
    exportedAt: new Date().toISOString(), basis: A.reason, service: location.host,
    chat: { id: c.id, type: c.type, title: c.title, createdAt: new Date(c.createdAt).toISOString(), members: c.members.map(id => ({ id, username: A.users[id]?.username, name: A.users[id]?.name })) },
    messages: A.msgs.map(m => ({
      id: m.id, at: new Date(m.ts).toISOString(), from: { id: m.from, username: A.users[m.from]?.username, name: A.users[m.from]?.name }, kind: m.kind,
      editedAt: m.edited ? new Date(m.edited).toISOString() : null, replyTo: m.replyTo,
      ...(m.kind === 'msg' ? (m.p ? { text: m.p.t || '', forwardedFrom: m.p.fwd || null, file: m.p.file ? { name: m.p.file.name, type: m.p.file.type, size: m.p.file.size } : null,
        voiceSeconds: m.p.voice?.dur ?? null, poll: m.p.poll ? { question: m.p.poll.q, options: m.p.poll.opts, votes: m.votes } : null } : { undecryptable: m.err }) : {}),
      ...(m.kind === 'service' ? { event: serviceText(m) } : {}), ...(m.kind === 'call' ? { call: m.meta.call } : {}),
    })),
  };
  const body = JSON.stringify(record, null, 2);
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body)))].map(b => b.toString(16).padStart(2, '0')).join('');
  let blob, name = `orbita-chat-${c.id}-${new Date().toISOString().slice(0, 10)}`;
  if (kind === 'json') blob = new Blob([JSON.stringify({ sha256OfRecord: digest, record }, null, 2)], { type: 'application/json' });
  else {
    const rows = record.messages.map(m => `<tr><td>${esc(m.at)}</td><td>${esc(m.from.name || '')} (@${esc(m.from.username || '')})</td><td>${
      m.kind === 'msg' ? (m.undecryptable ? '<i>не расшифровано</i>' : esc(m.text) + (m.file ? `<br><small>вложение: ${esc(m.file.name)}, ${m.file.size} Б</small>` : '') + (m.poll ? `<br><small>опрос: ${esc(m.poll.question)}</small>` : ''))
      : `<i>${esc(m.event || JSON.stringify(m.call))}</i>`}</td></tr>`).join('');
    blob = new Blob([`<!doctype html><meta charset="utf-8"><title>Выгрузка беседы #${c.id}</title>
      <style>body{font:14px/1.45 sans-serif;margin:32px;color:#111}table{border-collapse:collapse;width:100%}td{border:1px solid #ccc;padding:6px 8px;vertical-align:top}td:first-child{white-space:nowrap}</style>
      <h1>Выгрузка беседы #${c.id}</h1><p>Сервис: ${esc(record.service)}<br>Дата выгрузки: ${esc(record.exportedAt)}<br>Основание: ${esc(record.basis)}<br>
      Участники: ${record.chat.members.map(m => `${esc(m.name)} (@${esc(m.username)}, id ${m.id})`).join('; ')}<br>Сообщений: ${record.messages.length}<br>SHA-256 записи (JSON): <code>${digest}</code></p>
      <table><tr><th>Время (UTC)</th><th>Отправитель</th><th>Содержимое</th></tr>${rows}</table>`], { type: 'text/html' });
  }
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name + '.' + kind; a.click();
  toast('Выгрузка сохранена и записана в журнал');
}

// ---------- audit ----------
async function loadAudit() {
  const list = await api('/api/admin/audit', {});
  const label = { setup: 'Настройка ключа', login: 'Вход', login_failed: 'Неудачный вход', open_chat: 'Открыта беседа', export_chat: 'Выгрузка беседы' };
  $('#admAudit').innerHTML = `<table class="adm-table"><tr><th>Время</th><th>Действие</th><th>Беседа</th><th>Основание</th><th>Адрес</th></tr>${list.map(a =>
    `<tr class="${a.action === 'login_failed' ? 'missed' : ''}"><td>${new Date(a.at).toLocaleString('ru-RU')}</td><td>${esc(label[a.action] || a.action)}</td><td>${a.chat_id ? '#' + a.chat_id : ''}</td><td>${esc(a.reason)}</td><td>${esc(a.ip)}</td></tr>`).join('')}</table>`;
}

gate().catch(e => toast(e.message, 'bad'));
