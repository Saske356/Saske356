// Dialogs, popover menus, lightbox.
import { S, chatTitle, createGroup, peerId } from './state.js';
import { rpc, api } from './net.js';
import { $, $$, el, esc, icon, toast, seen, fine } from './util.js';
import { avatar, chatAvatar } from './avatar.js';
import * as C from './crypto.js';
import { App } from './bus.js';

const layer = () => $('#layer');

// ---------- modal ----------
let modalStack = [];
export function modal(html, { cls = '', onClose } = {}) {
  const back = el(`<div class="modal-back"><div class="modal ${cls}" role="dialog" aria-modal="true">${html}</div></div>`);
  layer().appendChild(back);
  const m = back.firstElementChild;
  const close = () => { back.remove(); modalStack = modalStack.filter(x => x !== close); onClose?.(); };
  back.addEventListener('mousedown', e => { if (e.target === back) close(); });
  m.addEventListener('click', e => { if (e.target.closest('[data-close]')) close(); });
  modalStack.push(close);
  requestAnimationFrame(() => back.classList.add('in'));
  if (fine()) setTimeout(() => m.querySelector('input:not([type=checkbox]),textarea')?.focus(), 30);
  return { m, close };
}
export const closeTopModal = () => { const c = modalStack[modalStack.length - 1]; if (c) { c(); return true; } return false; };
export const head = (title, sub = '') => `<div class="m-head"><div><h2>${esc(title)}</h2>${sub ? `<p class="muted">${esc(sub)}</p>` : ''}</div><button class="icon-btn" data-close title="Закрыть">${icon('close')}</button></div>`;

export function confirmBox(title, text, ok, { danger = true } = {}) {
  return new Promise(resolve => {
    let done = false;
    const { m, close } = modal(`${head(title)}<div class="m-body"><p>${esc(text)}</p></div>
      <div class="m-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${esc(ok)}</button></div>`,
      { cls: 'small', onClose: () => { if (!done) resolve(false); } });
    m.querySelector('[data-ok]').onclick = () => { done = true; close(); resolve(true); };
  });
}

// ---------- popover menu ----------
let menuEl = null;
export function closeMenu() { menuEl?.remove(); menuEl = null; }
export function menu(at, items, { top } = {}) {
  closeMenu();
  const m = el(`<div class="menu" role="menu">${top || ''}${items.filter(Boolean).map((it, i) =>
    it === '-' ? '<hr>' : `<button data-i="${i}" class="${it.danger ? 'danger' : ''}">${icon(it.icon)}<span>${esc(it.label)}</span></button>`).join('')}</div>`);
  layer().appendChild(m);
  menuEl = m;
  const list = items.filter(Boolean);
  m.addEventListener('click', e => {
    const b = e.target.closest('button[data-i]');
    if (b) { closeMenu(); list[b.dataset.i].run(); }
  });
  let x, y;
  if (at instanceof Element) { const r = at.getBoundingClientRect(); x = r.left; y = r.bottom + 6; if (x + 240 > innerWidth) x = r.right - m.offsetWidth; }
  else ({ x, y } = at);
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px';
  m.style.top = Math.max(8, Math.min(y, innerHeight - r.height - 8)) + 'px';
  requestAnimationFrame(() => m.classList.add('in'));
  return m;
}
document.addEventListener('mousedown', e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }, true);
document.addEventListener('touchstart', e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }, { capture: true, passive: true });
window.addEventListener('resize', closeMenu);

// ---------- lightbox ----------
export function lightbox(src, caption = '') {
  const box = el(`<div class="lightbox"><img src="${src}" alt=""><div class="lb-bar"><span>${esc(caption)}</span><button class="icon-btn" title="Закрыть">${icon('close')}</button></div></div>`);
  layer().appendChild(box);
  const close = () => { box.remove(); modalStack = modalStack.filter(x => x !== close); };
  box.onclick = close;
  modalStack.push(close);
  requestAnimationFrame(() => box.classList.add('in'));
}

// ---------- person card ----------
export function personCard(u) {
  if (!u) return;
  if (u.id === S.me.id) { App.setTab('me'); return; }
  const { m, close } = modal(`
    <div class="person">
      <button class="icon-btn m-x" data-close>${icon('close')}</button>
      <div class="person-cover" style="--c:${u.color}"></div>
      ${avatar(u, 'xl')}
      <h2>${esc(u.name)}</h2>
      <p class="muted">@${esc(u.username)} · ${esc(seen(u))}</p>
      ${u.bio ? `<p class="bio">${esc(u.bio)}</p>` : ''}
      <div class="person-actions">
        <button class="act" data-a="msg">${icon('chats')}<span>Написать</span></button>
        <button class="act" data-a="call">${icon('phone')}<span>Позвонить</span></button>
        <button class="act" data-a="video">${icon('video')}<span>Видео</span></button>
      </div>
    </div>`, { cls: 'person-modal' });
  m.querySelector('.person-actions').onclick = async e => {
    const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
    close();
    const chatId = await App.openDirect(u.id);
    if (chatId && a !== 'msg') App.startCall(chatId, a === 'video');
  };
}

// ---------- pick people ----------
export function pickPeople({ title, sub, ok, exclude = [], withTitle = false, min = 1 }) {
  return new Promise(resolve => {
    const chosen = new Map();
    let results = null, done = false;
    const { m, close } = modal(`${head(title, sub)}<div class="m-body">
      ${withTitle ? `<div class="group-name"><div class="gn-av" id="gnAv">${icon('people')}</div><label class="field grow"><span>Название группы</span><input id="gTitle" maxlength="64" placeholder="Например, «Поход в горы»"></label></div>` : ''}
      <div class="chips" id="chips"></div>
      <label class="search-field">${icon('search')}<input id="pq" placeholder="Найти по имени или @логину" autocomplete="off"></label>
      <div class="pick-list" id="plist"></div></div>
      <div class="m-foot"><span class="muted grow" id="pCount"></span><button class="btn ghost" data-close>Отмена</button><button class="btn primary" id="pOk">${esc(ok)}</button></div>`,
      { onClose: () => { if (!done) resolve(null); } });
    const known = () => Object.values(S.users).filter(u => u.id !== S.me.id && !exclude.includes(u.id)).sort((a, b) => b.online - a.online || a.name.localeCompare(b.name));
    const draw = () => {
      const list = (results ?? known()).filter(u => !exclude.includes(u.id) && u.id !== S.me.id);
      $('#plist', m).innerHTML = list.length ? list.map(u => `
        <button class="pick ${chosen.has(u.id) ? 'on' : ''}" data-uid="${u.id}">${avatar(u, 'md')}
          <span class="pick-txt"><b>${esc(u.name)}</b><small>@${esc(u.username)} · ${esc(seen(u))}</small></span>
          <span class="tick">${icon('check')}</span></button>`).join('')
        : `<div class="empty-note">${results ? 'Никого не нашли' : 'Найдите людей по логину — их можно будет добавить сразу'}</div>`;
      $('#chips', m).innerHTML = [...chosen.values()].map(u => `<button class="chip" data-uid="${u.id}">${avatar(u, 'xs')}${esc(u.name.split(' ')[0])}${icon('close')}</button>`).join('');
      $('#pCount', m).textContent = chosen.size ? `Выбрано: ${chosen.size}` : '';
    };
    let t;
    $('#pq', m).oninput = e => {
      clearTimeout(t);
      const q = e.target.value.trim();
      if (!q) { results = null; return draw(); }
      t = setTimeout(async () => {
        results = await rpc('searchUsers', { q }).catch(() => []);
        for (const u of results) if (!S.users[u.id]) S.users[u.id] = u;
        draw();
      }, 200);
    };
    m.addEventListener('click', e => {
      const p = e.target.closest('[data-uid]'); if (!p) return;
      const id = Number(p.dataset.uid);
      chosen.has(id) ? chosen.delete(id) : chosen.set(id, S.users[id]);
      draw();
    });
    $('#pOk', m).onclick = () => {
      const t = withTitle ? $('#gTitle', m).value.trim() : '';
      if (withTitle && !t) return toast('Придумайте название группы');
      if (chosen.size < min) return toast('Выберите хотя бы одного человека');
      done = true; close(); resolve({ ids: [...chosen.keys()], title: t });
    };
    draw();
  });
}

export async function newGroup() {
  const r = await pickPeople({ title: 'Новая группа', sub: 'Ключ группы создаётся на вашем устройстве', ok: 'Создать', withTitle: true, min: 0 });
  if (!r) return;
  try { const id = await createGroup(r.title, r.ids); await App.waitChat(id); App.openChat(id); }
  catch (e) { toast(e.message, 'bad'); }
}

// ---------- poll ----------
export function newPoll() {
  return new Promise(resolve => {
    let done = false;
    const { m, close } = modal(`${head('Опрос')}<div class="m-body">
      <label class="field"><span>Вопрос</span><input id="pollQ" maxlength="200" placeholder="О чём спросим?"></label>
      <div class="field"><span>Варианты</span><div id="pollOpts" class="poll-opts"></div></div>
      <label class="toggle"><input type="checkbox" id="pollMulti"><i></i><span>Можно выбрать несколько</span></label>
      </div><div class="m-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn primary" id="pollOk">Отправить</button></div>`,
      { onClose: () => { if (!done) resolve(null); } });
    const box = $('#pollOpts', m);
    const add = (focus) => {
      if (box.children.length >= 10) return;
      const row = el(`<div class="poll-opt"><input maxlength="100" placeholder="Вариант ${box.children.length + 1}"><button class="icon-btn sm" title="Убрать">${icon('close')}</button></div>`);
      row.querySelector('button').onclick = () => { if (box.children.length > 2) row.remove(); };
      row.querySelector('input').addEventListener('input', () => { if (box.lastElementChild.querySelector('input').value) add(); });
      box.appendChild(row);
      if (focus) row.querySelector('input').focus();
    };
    add(); add();
    $('#pollOk', m).onclick = () => {
      const q = $('#pollQ', m).value.trim();
      const opts = $$('input', box).map(i => i.value.trim()).filter(Boolean);
      if (!q) return toast('Напишите вопрос');
      if (opts.length < 2) return toast('Нужно хотя бы два варианта');
      done = true; close(); resolve({ q, opts, multi: $('#pollMulti', m).checked });
    };
  });
}

// ---------- forward ----------
export function chooseChat(title) {
  return new Promise(resolve => {
    let done = false;
    const chats = Object.values(S.chats).sort((a, b) => (b.lastMessage?.ts || b.createdAt) - (a.lastMessage?.ts || a.createdAt));
    const { m, close } = modal(`${head(title)}<div class="m-body">
      <label class="search-field">${icon('search')}<input id="fq" placeholder="Поиск" autocomplete="off"></label>
      <div class="pick-list" id="flist"></div></div>`, { onClose: () => { if (!done) resolve(null); } });
    const draw = q => {
      $('#flist', m).innerHTML = chats.filter(c => chatTitle(c).toLowerCase().includes(q)).map(c => `
        <button class="pick" data-cid="${c.id}">${chatAvatar(c, 'md')}<span class="pick-txt"><b>${esc(chatTitle(c))}</b>
        <small>${c.type === 'group' ? c.members.length + ' участн.' : c.type === 'self' ? 'только вы' : esc(seen(S.users[peerId(c)]))}</small></span></button>`).join('');
    };
    $('#fq', m).oninput = e => draw(e.target.value.trim().toLowerCase());
    m.addEventListener('click', e => { const p = e.target.closest('[data-cid]'); if (p) { done = true; close(); resolve(Number(p.dataset.cid)); } });
    draw('');
  });
}

// ---------- safety code ----------
export async function safetyModal(other) {
  const code = other ? await C.safetyCode(S.me, other) : await C.fingerprint(S.me);
  modal(`${head(other ? 'Код безопасности' : 'Ваш ключ')}<div class="m-body">
    <div class="safety">
      <div class="safety-emoji">${code.emoji.map(e => `<span>${e}</span>`).join('')}</div>
      <div class="safety-digits">${code.groups.map(g => `<span>${g}</span>`).join('')}</div>
    </div>
    <p class="muted">${other
      ? `Сравните этот код с ${esc(other.name)} при встрече или во время звонка. Если он совпадает, никто не подменил ваши ключи и переписку не может прочитать никто, кроме вас двоих.`
      : 'Это отпечаток вашего публичного ключа. Он одинаков на всех ваших устройствах и меняется только при создании нового аккаунта.'}</p>
    </div><div class="m-foot"><button class="btn primary" data-close>Готово</button></div>`, { cls: 'small' });
}

// ---------- password ----------
export function passwordModal() {
  const { m, close } = modal(`${head('Сменить пароль', 'Ключи переписки останутся прежними')}<div class="m-body">
    <label class="field"><span>Текущий пароль</span><input type="password" id="pw0" autocomplete="current-password"></label>
    <label class="field"><span>Новый пароль</span><input type="password" id="pw1" autocomplete="new-password"></label>
    <label class="field"><span>Ещё раз</span><input type="password" id="pw2" autocomplete="new-password"></label>
    <div class="form-error" id="pwErr"></div></div>
    <div class="m-foot"><button class="btn ghost" data-close>Отмена</button><button class="btn primary" id="pwOk">Сменить</button></div>`, { cls: 'small' });
  $('#pwOk', m).onclick = async e => {
    const [a, b, c] = ['#pw0', '#pw1', '#pw2'].map(s => $(s, m).value);
    const err = $('#pwErr', m);
    if (b.length < 8) return (err.textContent = 'Новый пароль — не меньше 8 символов');
    if (b !== c) return (err.textContent = 'Пароли не совпадают');
    e.target.disabled = true; err.textContent = '';
    try {
      const [oldC, newC] = await Promise.all([C.credentials(S.me.username, a), C.credentials(S.me.username, b)]);
      const { sealedKey } = await api('/api/sealed', {});
      let resealed;
      try { resealed = await C.resealIdentity(oldC.encKey, newC.encKey, sealedKey); } catch { throw new Error('Текущий пароль неверный'); }
      await api('/api/password', { auth: oldC.auth, newAuth: newC.auth, sealedKey: resealed });
      close(); toast('Пароль изменён');
    } catch (x) { err.textContent = x.message; e.target.disabled = false; }
  };
}

// ---------- sessions ----------
export async function sessionsModal() {
  const { m, close } = modal(`${head('Устройства', 'Где выполнен вход в аккаунт')}<div class="m-body"><div id="sess" class="sess"><div class="empty-note">Загружаем…</div></div></div>
    <div class="m-foot"><button class="btn danger" id="endAll">Выйти на остальных</button><button class="btn primary" data-close>Готово</button></div>`);
  const draw = async () => {
    const list = await rpc('sessions');
    $('#sess', m).innerHTML = list.map(s => `<div class="sess-row">${icon('devices')}<div class="grow"><b>${esc(s.device)}</b>
      <small class="muted">${s.current ? 'это устройство' : 'активность ' + new Date(s.lastActive).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</small></div>
      ${s.current ? '<span class="badge-soft">сейчас</span>' : `<button class="btn ghost sm" data-end="${s.id}">Выйти</button>`}</div>`).join('');
    $('#endAll', m).classList.toggle('hidden', list.length < 2);
  };
  m.addEventListener('click', async e => {
    const b = e.target.closest('[data-end]');
    if (b) { await rpc('endSessions', { id: b.dataset.end }); draw(); }
  });
  $('#endAll', m).onclick = async () => { await rpc('endSessions', {}); toast('Остальные устройства отключены'); close(); };
  draw().catch(e => toast(e.message, 'bad'));
}
