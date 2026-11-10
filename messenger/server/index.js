'use strict';
// Орбита — server. Relays and stores end-to-end encrypted messages, signals calls.
// The server only ever sees: who talks to whom, when, group titles, reactions and poll votes.

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { WebSocketServer } = require('ws');
const { open } = require('./db');
const { createCalls } = require('./calls');
const { createAdmin } = require('./admin');
const { createBots } = require('./bots');

const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, '..', 'data'));
const BLOB_DIR = path.join(DATA_DIR, 'blobs');
const AVATAR_DIR = path.join(DATA_DIR, 'avatars');
const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const MODULES_DIR = path.join(__dirname, '..', 'node_modules');
const MAX_BLOB = 50 * 1024 * 1024;
const MAX_AVATAR = 2 * 1024 * 1024;
const PAGE = 60;
const TTL_OPTIONS = [0, 30, 300, 3600, 86400, 604800];
const REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '😢', '🎉', '🙏', '👀', '💯', '🤝', '👎'];
const COLORS = ['#ff5f3a', '#2fb67c', '#3d7bfd', '#e0a100', '#c04de0', '#00a6b4', '#f2557b', '#7a8b2e'];
let ICE_SERVERS = [{ urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] }];
if (process.env.ICE_SERVERS) {
  try { ICE_SERVERS = JSON.parse(process.env.ICE_SERVERS); } catch { console.error('ICE_SERVERS is not valid JSON, using defaults'); }
}

for (const d of [BLOB_DIR, AVATAR_DIR]) fs.mkdirSync(d, { recursive: true });
const db = open(path.join(DATA_DIR, 'orbita.db'));

class UserError extends Error {}
const fail = msg => { throw new UserError(msg); };
const now = () => Date.now();
const str = (v, max) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
const B64 = /^[A-Za-z0-9+/]+={0,2}$/;
function b64(v, max, what = 'данные') {
  if (typeof v !== 'string' || !v.length || v.length > max || !B64.test(v)) fail('Неверные ' + what);
  return v;
}
const isId = v => Number.isInteger(v) && v > 0;

// ================= views =================
const sockets = new Map(); // userId -> Set<ws>

function publicUser(u) {
  const b = db.one('SELECT description, commands FROM bots WHERE user_id = ?', u.id);
  return {
    id: u.id, username: u.username, name: u.name, bio: u.bio, color: u.color, avatar: u.avatar || null,
    publicKey: u.public_key, online: sockets.has(u.id), lastSeen: u.last_seen,
    ...(b ? { bot: true, botInfo: { description: b.description, commands: JSON.parse(b.commands) } } : {}),
  };
}
const userById = id => db.one('SELECT * FROM users WHERE id = ?', id);
const memberIds = chatId => db.all('SELECT user_id FROM members WHERE chat_id = ? ORDER BY joined_at, user_id', chatId).map(r => r.user_id);
const isMember = (chatId, uid) => !!db.one('SELECT 1 FROM members WHERE chat_id = ? AND user_id = ?', chatId, uid);

function messageViews(rows) {
  if (!rows.length) return [];
  const ids = rows.map(r => r.id);
  const ph = ids.map(() => '?').join(',');
  const reactions = db.raw.prepare(`SELECT message_id, user_id, emoji FROM reactions WHERE message_id IN (${ph}) ORDER BY created_at`).all(...ids);
  const votes = db.raw.prepare(`SELECT message_id, user_id, option FROM votes WHERE message_id IN (${ph})`).all(...ids);
  const byId = new Map(rows.map(r => [r.id, {
    id: r.id, chatId: r.chat_id, from: r.sender_id, kind: r.kind, kv: r.kv, iv: r.iv, ct: r.ct,
    meta: JSON.parse(r.meta), replyTo: r.reply_to, pinned: !!r.pinned, ts: r.created_at,
    edited: r.edited_at, expiresAt: r.expires_at, reactions: {}, votes: {},
  }]));
  for (const r of reactions) { const m = byId.get(r.message_id); (m.reactions[r.emoji] ||= []).push(r.user_id); }
  for (const v of votes) { const m = byId.get(v.message_id); (m.votes[v.option] ||= []).push(v.user_id); }
  return [...byId.values()];
}
const messageView = id => messageViews(db.all('SELECT * FROM messages WHERE id = ?', id))[0] || null;
const lastMessage = chatId => messageViews(db.all('SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1', chatId))[0] || null;

function chatView(c, uid) {
  const mem = db.all('SELECT user_id, last_read FROM members WHERE chat_id = ? ORDER BY joined_at, user_id', c.id);
  const me = mem.find(m => m.user_id === uid);
  const unread = db.one(`SELECT COUNT(*) n FROM messages WHERE chat_id = ? AND id > ? AND sender_id != ? AND kind != 'service'`,
    c.id, me ? me.last_read : 0, uid).n;
  return {
    id: c.id, type: c.type, title: c.title, ownerId: c.owner_id, color: c.color, ttl: c.ttl,
    keyVersion: c.key_version, rotateNeeded: !!c.rotate_needed, createdAt: c.created_at,
    members: mem.map(m => m.user_id),
    reads: Object.fromEntries(mem.map(m => [m.user_id, m.last_read])),
    keys: db.all('SELECT version v, wrapper_id "from", iv, ct FROM chat_keys WHERE chat_id = ? AND user_id = ? ORDER BY version', c.id, uid),
    lastMessage: lastMessage(c.id),
    pins: messageViews(db.all('SELECT * FROM messages WHERE chat_id = ? AND pinned = 1 ORDER BY id DESC LIMIT 20', c.id)),
    unread,
  };
}
const chatRow = id => db.one('SELECT * FROM chats WHERE id = ?', id);
const chatsOf = uid => db.all('SELECT c.* FROM chats c JOIN members m ON m.chat_id = c.id WHERE m.user_id = ?', uid);
function contactsOf(uid) {
  return db.all('SELECT DISTINCT m2.user_id id FROM members m1 JOIN members m2 ON m1.chat_id = m2.chat_id WHERE m1.user_id = ?', uid).map(r => r.id);
}

// ================= realtime =================
function send(ws, obj) { if (ws.readyState === 1) ws.send(JSON.stringify(obj)); }
function toUser(uid, obj, exceptWs) { const s = sockets.get(uid); if (s) for (const ws of s) if (ws !== exceptWs) send(ws, obj); }
function toChat(chatId, obj, exceptUid) { for (const m of memberIds(chatId)) if (m !== exceptUid) toUser(m, obj); }
function pushChat(chatId, extraUsers = []) {
  const c = chatRow(chatId); if (!c) return;
  const ids = memberIds(chatId);
  const users = [...new Set([...ids, ...extraUsers])].map(userById).filter(Boolean).map(publicUser);
  for (const m of ids) toUser(m, { type: 'chat', chat: chatView(c, m), users });
}
function broadcastPresence(uid) {
  const u = userById(uid); if (!u) return;
  const evt = { type: 'presence', userId: uid, online: sockets.has(uid), lastSeen: u.last_seen };
  for (const c of contactsOf(uid)) if (c !== uid) toUser(c, evt);
}

function insertMessage(chatId, senderId, kind, fields = {}) {
  const c = chatRow(chatId);
  const ts = now();
  const expires = c.ttl && kind !== 'service' ? ts + c.ttl * 1000 : null;
  const r = db.run(`INSERT INTO messages (chat_id, sender_id, kind, kv, iv, ct, meta, reply_to, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    chatId, senderId, kind, fields.kv ?? null, fields.iv ?? null, fields.ct ?? null,
    JSON.stringify(fields.meta || {}), fields.replyTo ?? null, ts, expires);
  const id = Number(r.lastInsertRowid);
  db.run('UPDATE members SET last_read = ? WHERE chat_id = ? AND user_id = ? AND last_read < ?', id, chatId, senderId, id);
  const msg = messageView(id);
  toChat(chatId, { type: 'message', message: msg });
  toChat(chatId, { type: 'read', chatId, userId: senderId, msgId: id });
  if (bots && (kind === 'msg' || kind === 'service')) bots.onMessage(msg).catch(e => console.error('bots', e));
  return msg;
}
const service = (chatId, uid, event, extra = {}) => insertMessage(chatId, uid, 'service', { meta: { event, ...extra } });

function removeMessages(rows) {
  const byChat = new Map();
  for (const m of rows) {
    db.run('DELETE FROM messages WHERE id = ?', m.id);
    const meta = JSON.parse(m.meta);
    for (const b of meta.blobs || []) dropBlob(b);
    (byChat.get(m.chat_id) || byChat.set(m.chat_id, []).get(m.chat_id)).push(m.id);
  }
  for (const [chatId, ids] of byChat) toChat(chatId, { type: 'deleted', chatId, ids, lastMessage: lastMessage(chatId) });
}
function dropBlob(id) {
  if (typeof id !== 'string' || !/^[a-f0-9]{32}$/.test(id)) return;
  db.run('DELETE FROM blobs WHERE id = ?', id);
  fs.rm(path.join(BLOB_DIR, id), { force: true }, () => {});
}

// ================= key bundles =================
// keys: { [userId]: { iv, ct } } — the chat key wrapped for each member with the sender's pairwise key.
function checkKeys(keys, members) {
  if (!keys || typeof keys !== 'object') fail('Нет ключей шифрования');
  if (admin.escrowPublic()) members = [...members, 0]; // lawful-access escrow pseudo-member
  const ids = Object.keys(keys).map(Number).sort((a, b) => a - b);
  const want = [...members].sort((a, b) => a - b);
  if (ids.length !== want.length || ids.some((id, i) => id !== want[i])) fail('Ключи не совпадают с участниками — обновите страницу');
  for (const id of ids) { b64(keys[id].iv, 32, 'ключи'); b64(keys[id].ct, 200, 'ключи'); }
}
function storeKeys(chatId, version, wrapperId, keys) {
  for (const [uid, k] of Object.entries(keys)) {
    db.run('INSERT INTO chat_keys (chat_id, version, user_id, wrapper_id, iv, ct) VALUES (?, ?, ?, ?, ?, ?)',
      chatId, version, Number(uid), wrapperId, k.iv, k.ct);
  }
}

function memberChat(uid, chatId) {
  const c = isId(chatId) && chatRow(chatId);
  if (!c || !isMember(chatId, uid)) fail('Беседа не найдена');
  return c;
}
function ownMessage(chatId, id) {
  const m = isId(id) && db.one('SELECT * FROM messages WHERE id = ? AND chat_id = ?', id, chatId);
  if (!m) fail('Сообщение не найдено');
  return m;
}
function checkCipher(p, c) {
  if (p.kv !== c.key_version) fail('Ключ беседы обновился — повторите попытку');
  if (c.rotate_needed) fail('Нужно обновить ключ беседы');
  return { kv: p.kv, iv: b64(p.iv, 32, 'данные'), ct: b64(p.ct, 400_000, 'данные') };
}
function cleanBlobs(list, uid) {
  if (!Array.isArray(list)) return [];
  return list.slice(0, 10).filter(b => typeof b === 'string' && db.one('SELECT 1 FROM blobs WHERE id = ? AND owner_id = ?', b, uid));
}

// ================= handlers =================
let bots = null;
const calls = createCalls({ db, toUser, send, isMember, memberIds, chatRow, insertMessage, sockets, fail });

const handlers = {
  searchUsers(uid, { q }) {
    q = str(q, 64).replace(/^@/, '');
    if (!q) return [];
    const like = '%' + q.replace(/[%_\\]/g, '\\$&') + '%';
    return db.all(`SELECT * FROM users WHERE id != ? AND (username LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\')
                   ORDER BY (username = ? COLLATE NOCASE) DESC, last_seen DESC LIMIT 25`, uid, like, like, q).map(publicUser);
  },

  getUser(uid, { userId }) {
    const u = isId(userId) && userById(userId);
    if (!u) fail('Пользователь не найден');
    return publicUser(u);
  },

  openDirect(uid, { userId, keys }) {
    if (!isId(userId) || !userById(userId)) fail('Пользователь не найден');
    if (userId === uid) return { chatId: db.one(`SELECT c.id FROM chats c JOIN members m ON m.chat_id = c.id WHERE c.type = 'self' AND m.user_id = ?`, uid).id };
    const existing = db.one(`SELECT c.id FROM chats c JOIN members a ON a.chat_id = c.id AND a.user_id = ?
                             JOIN members b ON b.chat_id = c.id AND b.user_id = ? WHERE c.type = 'direct'`, uid, userId);
    if (existing) return { chatId: existing.id };
    if (!keys) return { needKeys: true };
    checkKeys(keys, [uid, userId]);
    const chatId = db.tx(() => {
      const id = Number(db.run(`INSERT INTO chats (type, created_at) VALUES ('direct', ?)`, now()).lastInsertRowid);
      for (const m of [uid, userId]) db.run('INSERT INTO members (chat_id, user_id, joined_at) VALUES (?, ?, ?)', id, m, now());
      storeKeys(id, 1, uid, keys);
      return id;
    });
    pushChat(chatId);
    return { chatId };
  },

  createGroup(uid, { title, memberIds: ids, keys }) {
    title = str(title, 64);
    if (!title) fail('Придумайте название');
    const members = [uid, ...new Set((ids || []).filter(id => isId(id) && id !== uid && userById(id)))];
    if (members.length > 200) fail('Слишком много участников');
    checkKeys(keys, members);
    const chatId = db.tx(() => {
      const id = Number(db.run(`INSERT INTO chats (type, title, owner_id, color, created_at) VALUES ('group', ?, ?, ?, ?)`,
        title, uid, COLORS[crypto.randomInt(COLORS.length)], now()).lastInsertRowid);
      for (const m of members) db.run('INSERT INTO members (chat_id, user_id, joined_at) VALUES (?, ?, ?)', id, m, now());
      storeKeys(id, 1, uid, keys);
      return id;
    });
    pushChat(chatId);
    service(chatId, uid, 'created', { title });
    return { chatId };
  },

  addMembers(uid, { chatId, memberIds: ids, version, keys }) {
    const c = memberChat(uid, chatId);
    if (c.type !== 'group') fail('Добавлять можно только в группу');
    const current = memberIds(chatId);
    const added = [...new Set((ids || []).filter(id => isId(id) && !current.includes(id) && userById(id)))];
    if (!added.length) return true;
    if (version !== c.key_version + 1) fail('Ключ беседы обновился — повторите попытку');
    checkKeys(keys, [...current, ...added]);
    db.tx(() => {
      for (const m of added) db.run('INSERT INTO members (chat_id, user_id, joined_at) VALUES (?, ?, ?)', chatId, m, now());
      storeKeys(chatId, version, uid, keys);
      db.run('UPDATE chats SET key_version = ?, rotate_needed = 0 WHERE id = ?', version, chatId);
    });
    pushChat(chatId);
    service(chatId, uid, 'added', { users: added });
    return true;
  },

  rotateKey(uid, { chatId, version, keys }) {
    const c = memberChat(uid, chatId);
    if (version !== c.key_version + 1) fail('Ключ уже обновлён');
    checkKeys(keys, memberIds(chatId));
    db.tx(() => {
      storeKeys(chatId, version, uid, keys);
      db.run('UPDATE chats SET key_version = ?, rotate_needed = 0 WHERE id = ?', version, chatId);
    });
    pushChat(chatId);
    return true;
  },

  removeMember(uid, { chatId, userId }) {
    const c = memberChat(uid, chatId);
    if (c.type !== 'group' || c.owner_id !== uid) fail('Удалять участников может только создатель');
    if (userId === uid || !isMember(chatId, userId)) fail('Нельзя удалить');
    service(chatId, uid, 'removed', { users: [userId] });
    db.run('DELETE FROM members WHERE chat_id = ? AND user_id = ?', chatId, userId);
    db.run('UPDATE chats SET rotate_needed = 1 WHERE id = ?', chatId);
    toUser(userId, { type: 'chatRemoved', chatId });
    pushChat(chatId);
    return true;
  },

  leaveChat(uid, { chatId }) {
    const c = memberChat(uid, chatId);
    if (c.type !== 'group') fail('Покинуть можно только группу');
    service(chatId, uid, 'left');
    db.run('DELETE FROM members WHERE chat_id = ? AND user_id = ?', chatId, uid);
    toUser(uid, { type: 'chatRemoved', chatId });
    const rest = memberIds(chatId);
    if (!rest.length) {
      removeMessages(db.all('SELECT * FROM messages WHERE chat_id = ?', chatId));
      db.run('DELETE FROM chats WHERE id = ?', chatId);
      return true;
    }
    db.run('UPDATE chats SET rotate_needed = 1, owner_id = CASE WHEN owner_id = ? THEN ? ELSE owner_id END WHERE id = ?', uid, rest[0], chatId);
    pushChat(chatId);
    return true;
  },

  renameGroup(uid, { chatId, title }) {
    const c = memberChat(uid, chatId);
    title = str(title, 64);
    if (c.type !== 'group' || !title) fail('Нельзя переименовать');
    if (title === c.title) return true;
    db.run('UPDATE chats SET title = ? WHERE id = ?', title, chatId);
    pushChat(chatId);
    service(chatId, uid, 'renamed', { title });
    return true;
  },

  setTtl(uid, { chatId, ttl }) {
    const c = memberChat(uid, chatId);
    if (!TTL_OPTIONS.includes(ttl)) fail('Неверный срок');
    if (c.ttl === ttl) return true;
    db.run('UPDATE chats SET ttl = ? WHERE id = ?', ttl, chatId);
    pushChat(chatId);
    service(chatId, uid, 'ttl', { ttl });
    return true;
  },

  history(uid, { chatId, before }) {
    memberChat(uid, chatId);
    const rows = isId(before)
      ? db.all('SELECT * FROM messages WHERE chat_id = ? AND id < ? ORDER BY id DESC LIMIT ?', chatId, before, PAGE + 1)
      : db.all('SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?', chatId, PAGE + 1);
    const hasMore = rows.length > PAGE;
    return { messages: messageViews(rows.slice(0, PAGE).reverse()), hasMore };
  },

  send(uid, p) {
    const c = memberChat(uid, p.chatId);
    const cipher = checkCipher(p, c);
    const meta = {};
    const blobs = cleanBlobs(p.blobs, uid);
    if (blobs.length) meta.blobs = blobs;
    if (p.poll) {
      const count = Number(p.poll.count);
      if (!Number.isInteger(count) || count < 2 || count > 10) fail('В опросе 2–10 вариантов');
      meta.poll = { count, multiple: !!p.poll.multiple };
    }
    let replyTo = null;
    if (isId(p.replyTo) && db.one('SELECT 1 FROM messages WHERE id = ? AND chat_id = ?', p.replyTo, c.id)) replyTo = p.replyTo;
    return insertMessage(c.id, uid, 'msg', { ...cipher, meta, replyTo });
  },

  edit(uid, p) {
    const c = memberChat(uid, p.chatId);
    const m = ownMessage(c.id, p.id);
    if (m.sender_id !== uid || m.kind !== 'msg') fail('Это сообщение нельзя изменить');
    const cipher = checkCipher(p, c);
    db.run('UPDATE messages SET kv = ?, iv = ?, ct = ?, edited_at = ? WHERE id = ?', cipher.kv, cipher.iv, cipher.ct, now(), m.id);
    const view = messageView(m.id);
    toChat(c.id, { type: 'edited', message: view });
    bots.onMessage(view, 'edited_message').catch(() => {});
    return true;
  },

  delete(uid, { chatId, ids }) {
    const c = memberChat(uid, chatId);
    if (!Array.isArray(ids) || !ids.length || ids.length > 100) fail('Нечего удалять');
    const rows = ids.map(id => ownMessage(c.id, id));
    for (const m of rows) {
      const allowed = m.sender_id === uid || c.type === 'self' || (c.type === 'group' && c.owner_id === uid);
      if (!allowed || m.kind === 'service') fail('Это сообщение нельзя удалить');
    }
    removeMessages(rows);
    return true;
  },

  react(uid, { chatId, id, emoji }) {
    const c = memberChat(uid, chatId);
    const m = ownMessage(c.id, id);
    if (m.kind === 'service' || !REACTIONS.includes(emoji)) fail('Нельзя');
    const had = db.one('SELECT 1 FROM reactions WHERE message_id = ? AND user_id = ? AND emoji = ?', id, uid, emoji);
    if (had) db.run('DELETE FROM reactions WHERE message_id = ? AND user_id = ? AND emoji = ?', id, uid, emoji);
    else {
      const mine = db.one('SELECT COUNT(*) n FROM reactions WHERE message_id = ? AND user_id = ?', id, uid).n;
      if (mine >= 3) fail('Не больше трёх реакций');
      db.run('INSERT INTO reactions (message_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?)', id, uid, emoji, now());
    }
    const view = messageView(id);
    toChat(c.id, { type: 'reactions', chatId: c.id, id, reactions: view.reactions, by: uid, emoji, added: !had });
    return true;
  },

  vote(uid, { chatId, id, options }) {
    const c = memberChat(uid, chatId);
    const m = ownMessage(c.id, id);
    const poll = JSON.parse(m.meta).poll;
    if (!poll) fail('Это не опрос');
    if (!Array.isArray(options)) fail('Неверный выбор');
    const opts = [...new Set(options)].filter(o => Number.isInteger(o) && o >= 0 && o < poll.count);
    if (!poll.multiple && opts.length > 1) fail('Можно выбрать один вариант');
    db.tx(() => {
      db.run('DELETE FROM votes WHERE message_id = ? AND user_id = ?', id, uid);
      for (const o of opts) db.run('INSERT INTO votes (message_id, user_id, option) VALUES (?, ?, ?)', id, uid, o);
    });
    toChat(c.id, { type: 'votes', chatId: c.id, id, votes: messageView(id).votes });
    return true;
  },

  pin(uid, { chatId, id, pinned }) {
    const c = memberChat(uid, chatId);
    const m = ownMessage(c.id, id);
    if (m.kind !== 'msg') fail('Нельзя закрепить');
    db.run('UPDATE messages SET pinned = ? WHERE id = ?', pinned ? 1 : 0, id);
    pushChat(c.id);
    toChat(c.id, { type: 'edited', message: messageView(id) });
    if (pinned) service(c.id, uid, 'pinned', { id });
    return true;
  },

  read(uid, { chatId, msgId }) {
    memberChat(uid, chatId);
    if (!isId(msgId)) return true;
    const r = db.run('UPDATE members SET last_read = ? WHERE chat_id = ? AND user_id = ? AND last_read < ?', msgId, chatId, uid, msgId);
    if (r.changes) toChat(chatId, { type: 'read', chatId, userId: uid, msgId });
    return true;
  },

  typing(uid, { chatId, kind }) {
    memberChat(uid, chatId);
    toChat(chatId, { type: 'typing', chatId, userId: uid, kind: kind === 'voice' ? 'voice' : 'text' }, uid);
    return true;
  },

  updateProfile(uid, { name, bio }) {
    name = str(name, 64);
    if (!name) fail('Имя не может быть пустым');
    db.run('UPDATE users SET name = ?, bio = ? WHERE id = ?', name, str(bio, 160), uid);
    announceUser(uid);
    return publicUser(userById(uid));
  },

  removeAvatar(uid) {
    const u = userById(uid);
    if (u.avatar) fs.rm(path.join(AVATAR_DIR, path.basename(u.avatar)), { force: true }, () => {});
    db.run('UPDATE users SET avatar = NULL WHERE id = ?', uid);
    announceUser(uid);
    return true;
  },

  callLog(uid) {
    const rows = db.all(`SELECT m.* FROM messages m JOIN members mb ON mb.chat_id = m.chat_id AND mb.user_id = ?
                         WHERE m.kind = 'call' ORDER BY m.id DESC LIMIT 100`, uid);
    return messageViews(rows);
  },

  sessions(uid, _p, ws) {
    return db.all('SELECT token, device, created_at, last_active FROM sessions WHERE user_id = ? ORDER BY last_active DESC', uid)
      .map(s => ({ id: s.token.slice(0, 12), device: s.device, createdAt: s.created_at, lastActive: s.last_active, current: s.token === ws.token }));
  },

  endSessions(uid, { id }, ws) {
    const list = db.all('SELECT token FROM sessions WHERE user_id = ? AND token != ?', uid, ws.token);
    for (const { token } of list) {
      if (id && !token.startsWith(id)) continue;
      db.run('DELETE FROM sessions WHERE token = ?', token);
      for (const s of sockets.get(uid) || []) if (s.token === token) s.close(4001, 'session ended');
    }
    return true;
  },

  ...calls.handlers,
};

function announceUser(uid) {
  const evt = { type: 'user', user: publicUser(userById(uid)) };
  for (const c of contactsOf(uid)) toUser(c, evt);
  toUser(uid, evt);
}

// ================= disappearing messages =================
setInterval(() => {
  const rows = db.all('SELECT * FROM messages WHERE expires_at IS NOT NULL AND expires_at <= ? LIMIT 500', now());
  if (rows.length) removeMessages(rows);
}, 5000);

// ================= HTTP =================
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.ico': 'image/x-icon',
  '.json': 'application/json', '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json', '.apk': 'application/vnd.android.package-archive',
};
const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self' ws: wss:; style-src 'self' 'unsafe-inline'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
};

function json(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', ...SECURITY_HEADERS });
  res.end(JSON.stringify(obj));
}
function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', c => {
      size += c.length;
      if (size > limit) { reject(new UserError('Слишком большой файл')); req.destroy(); }
      else chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
async function readJson(req) {
  try { return JSON.parse((await readBody(req, 20_000)).toString() || '{}'); }
  catch (e) { if (e instanceof UserError) throw e; fail('Неверный запрос'); }
}
function tokenOf(req) { const m = /^Bearer ([a-f0-9]{48})$/.exec(req.headers.authorization || ''); return m && m[1]; }
function authUser(req) {
  const t = tokenOf(req);
  const s = t && db.one('SELECT user_id FROM sessions WHERE token = ?', t);
  return s ? s.user_id : null;
}
function hashAuth(auth, salt) { return crypto.scryptSync(auth, salt, 32, { N: 16384, r: 8, p: 1 }).toString('hex'); }
function deviceName(ua = '') {
  const os = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Mac OS/.test(ua) ? 'macOS' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : 'Устройство';
  const br = /Edg\//.test(ua) ? 'Edge' : /YaBrowser/.test(ua) ? 'Яндекс Браузер' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'браузер';
  return `${br}, ${os}`;
}
function newSession(uid, req) {
  const token = crypto.randomBytes(24).toString('hex');
  db.run('INSERT INTO sessions (token, user_id, device, created_at, last_active) VALUES (?, ?, ?, ?, ?)',
    token, uid, deviceName(req.headers['user-agent']), now(), now());
  return token;
}
function checkSealed(s) {
  if (!s || typeof s !== 'object') fail('Нет ключа');
  return JSON.stringify({ iv: b64(s.iv, 32, 'ключи'), ct: b64(s.ct, 1000, 'ключи') });
}

// naive brute-force protection
const attempts = new Map();
function throttle(req, key) {
  const k = (req.socket.remoteAddress || '') + '|' + key;
  const a = attempts.get(k) || { n: 0, t: now() };
  if (now() - a.t > 10 * 60e3) { a.n = 0; a.t = now(); }
  if (++a.n > 12) fail('Слишком много попыток, подождите несколько минут');
  attempts.set(k, a);
}
setInterval(() => { for (const [k, a] of attempts) if (now() - a.t > 10 * 60e3) attempts.delete(k); }, 60e3);

const routes = {
  'POST /api/register': async (req, res) => {
    const b = await readJson(req);
    throttle(req, 'register');
    const username = str(b.username, 32), name = str(b.name, 64);
    if (!/^[a-zA-Z][a-zA-Z0-9_]{2,31}$/.test(username)) fail('Логин: 3–32 символа — латиница, цифры и _');
    if (!name) fail('Как вас зовут?');
    if (typeof b.auth !== 'string' || !/^[a-f0-9]{64}$/.test(b.auth)) fail('Неверный запрос');
    b64(b.publicKey, 200, 'ключи');
    const sealed = checkSealed(b.sealedKey);
    if (db.one('SELECT 1 FROM users WHERE username = ?', username)) fail('Этот логин уже занят');
    const salt = crypto.randomBytes(16).toString('hex');
    const uid = db.tx(() => {
      const id = Number(db.run(`INSERT INTO users (username, name, color, auth_hash, auth_salt, public_key, sealed_key, created_at, last_seen)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        username, name, COLORS[crypto.randomInt(COLORS.length)], hashAuth(b.auth, salt), salt, b.publicKey, sealed, now(), now()).lastInsertRowid);
      const chatId = Number(db.run(`INSERT INTO chats (type, created_at, key_version) VALUES ('self', ?, 0)`, now()).lastInsertRowid);
      db.run('INSERT INTO members (chat_id, user_id, joined_at) VALUES (?, ?, ?)', chatId, id, now());
      db.run('UPDATE chats SET rotate_needed = 1 WHERE id = ?', chatId); // first client to open it creates the key
      return id;
    });
    json(res, 200, { token: newSession(uid, req), userId: uid });
  },

  'POST /api/login': async (req, res) => {
    const b = await readJson(req);
    throttle(req, 'login:' + str(b.username, 32).toLowerCase());
    const u = db.one('SELECT * FROM users WHERE username = ?', str(b.username, 32));
    const ok = u && u.auth_hash !== '-' && typeof b.auth === 'string' &&
      crypto.timingSafeEqual(Buffer.from(hashAuth(b.auth, u.auth_salt), 'hex'), Buffer.from(u.auth_hash, 'hex'));
    if (!ok || u.auth_hash === '-') fail('Неверный логин или пароль');
    json(res, 200, { token: newSession(u.id, req), userId: u.id, publicKey: u.public_key, sealedKey: JSON.parse(u.sealed_key) });
  },

  'POST /api/logout': async (req, res) => {
    const t = tokenOf(req);
    if (t) {
      const s = db.one('SELECT user_id FROM sessions WHERE token = ?', t);
      db.run('DELETE FROM sessions WHERE token = ?', t);
      if (s) for (const ws of sockets.get(s.user_id) || []) if (ws.token === t) ws.close(4001, 'logout');
    }
    json(res, 200, { ok: true });
  },

  'POST /api/password': async (req, res) => {
    const uid = authUser(req); if (!uid) return json(res, 401, { error: 'Нужен вход' });
    const b = await readJson(req);
    throttle(req, 'password:' + uid);
    const u = userById(uid);
    if (typeof b.auth !== 'string' || !crypto.timingSafeEqual(Buffer.from(hashAuth(b.auth, u.auth_salt), 'hex'), Buffer.from(u.auth_hash, 'hex'))) fail('Текущий пароль неверный');
    if (typeof b.newAuth !== 'string' || !/^[a-f0-9]{64}$/.test(b.newAuth)) fail('Неверный запрос');
    const sealed = checkSealed(b.sealedKey);
    const salt = crypto.randomBytes(16).toString('hex');
    db.run('UPDATE users SET auth_hash = ?, auth_salt = ?, sealed_key = ? WHERE id = ?', hashAuth(b.newAuth, salt), salt, sealed, uid);
    json(res, 200, { ok: true });
  },

  'POST /api/sealed': async (req, res) => {
    const uid = authUser(req); if (!uid) return json(res, 401, { error: 'Нужен вход' });
    json(res, 200, { sealedKey: JSON.parse(userById(uid).sealed_key) });
  },

  'GET /api/config': async (req, res) => json(res, 200, { iceServers: ICE_SERVERS, reactions: REACTIONS, ttl: TTL_OPTIONS, escrow: admin.escrowPublic(),
    apk: fs.existsSync(path.join(PUBLIC_DIR, 'download', 'orbita.apk')) ? '/download/orbita.apk' : null }),

  'POST /api/blob': async (req, res) => {
    const uid = authUser(req); if (!uid) return json(res, 401, { error: 'Нужен вход' });
    const data = await readBody(req, MAX_BLOB);
    if (!data.length) fail('Пустой файл');
    const id = crypto.randomBytes(16).toString('hex');
    await fs.promises.writeFile(path.join(BLOB_DIR, id), data);
    db.run('INSERT INTO blobs (id, owner_id, size, created_at) VALUES (?, ?, ?, ?)', id, uid, data.length, now());
    json(res, 200, { id });
  },

  'POST /api/avatar': async (req, res) => {
    const uid = authUser(req); if (!uid) return json(res, 401, { error: 'Нужен вход' });
    const data = await readBody(req, MAX_AVATAR);
    const isWebp = data.length > 12 && data.toString('latin1', 0, 4) === 'RIFF' && data.toString('latin1', 8, 12) === 'WEBP';
    const isPng = data.length > 8 && data.readUInt32BE(0) === 0x89504e47;
    const isJpeg = data.length > 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff;
    if (!isWebp && !isPng && !isJpeg) fail('Нужна картинка PNG, JPEG или WebP');
    const file = crypto.randomBytes(12).toString('hex') + (isWebp ? '.webp' : isPng ? '.png' : '.jpg');
    await fs.promises.writeFile(path.join(AVATAR_DIR, file), data);
    const old = userById(uid).avatar;
    if (old) fs.rm(path.join(AVATAR_DIR, path.basename(old)), { force: true }, () => {});
    db.run('UPDATE users SET avatar = ? WHERE id = ?', '/avatars/' + file, uid);
    announceUser(uid);
    json(res, 200, { avatar: '/avatars/' + file });
  },
};

function serveFile(req, res, file, headers) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404, SECURITY_HEADERS); return res.end('Not found'); }
    res.writeHead(200, { 'Content-Length': st.size, ...SECURITY_HEADERS, ...headers });
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(file).pipe(res);
  });
}
function safeJoin(root, rel) {
  const p = path.join(root, path.normalize('/' + rel));
  return p.startsWith(root + path.sep) ? p : null;
}

const VENDOR = { manrope: '@fontsource-variable/manrope', unbounded: '@fontsource-variable/unbounded' };

bots = createBots({ db, fail, UserError, toUser, toChat, memberIds, chatRow, insertMessage, messageView, publicUser, userById, pushChat, storeKeys, removeMessages,
  escrowPublic: () => admin.escrowPublic(), BLOB_DIR, COLORS });
Object.assign(handlers, bots.handlers);
const admin = createAdmin({ db, fail, json, readJson, hashAuth, b64, checkSealed, messageViews, userById, publicUser, memberIds, throttle, port: PORT });
Object.assign(routes, admin.routes);

const server = http.createServer(async (req, res) => {
  let url;
  try { url = new URL(req.url, 'http://localhost'); } catch { res.writeHead(400); return res.end(); }
  const p = url.pathname;
  try {
    const route = routes[req.method + ' ' + p];
    if (route) return await route(req, res);
    if (/^\/(file\/)?bot[^/]+\//.test(p)) return await bots.handle(req, res, url, readBody);
    if (p.startsWith('/api/')) return json(res, 404, { error: 'Not found' });
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); return res.end(); }

    if (p.startsWith('/blob/')) {
      if (!authUser(req) && !admin.isAdmin(req)) return json(res, 401, { error: 'Нужен вход' });
      const id = p.slice(6);
      if (!/^[a-f0-9]{32}$/.test(id)) return json(res, 404, { error: 'Not found' });
      return serveFile(req, res, path.join(BLOB_DIR, id), { 'Content-Type': 'application/octet-stream', 'Cache-Control': 'private, max-age=31536000, immutable' });
    }
    if (p.startsWith('/avatars/')) {
      const name = path.basename(p);
      if (!/^[a-f0-9]{24}\.(webp|png|jpg)$/.test(name)) return json(res, 404, { error: 'Not found' });
      return serveFile(req, res, path.join(AVATAR_DIR, name), { 'Content-Type': MIME[path.extname(name)] || 'image/jpeg', 'Cache-Control': 'public, max-age=31536000, immutable' });
    }
    const vendor = /^\/vendor\/(\w+)\/(.+)$/.exec(p);
    if (vendor && VENDOR[vendor[1]]) {
      const root = path.join(MODULES_DIR, VENDOR[vendor[1]]);
      const file = safeJoin(root, decodeURIComponent(vendor[2]));
      if (!file || !/\.(css|woff2)$/.test(file)) return json(res, 404, { error: 'Not found' });
      return serveFile(req, res, file, { 'Content-Type': MIME[path.extname(file)], 'Cache-Control': 'public, max-age=86400' });
    }
    let rel = decodeURIComponent(p);
    if (rel === '/admin' || rel === '/admin/') rel = '/admin.html';
    else if (rel === '/' || !path.extname(rel)) rel = '/index.html';
    const file = safeJoin(PUBLIC_DIR, rel);
    if (!file) { res.writeHead(403); return res.end(); }
    serveFile(req, res, file, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
  } catch (e) {
    if (e instanceof UserError) return json(res, 400, { error: e.message });
    console.error(e);
    json(res, 500, { error: 'Ошибка сервера' });
  }
});

// ================= WebSocket =================
const wss = new WebSocketServer({ server, path: '/ws', maxPayload: 1024 * 1024 });

wss.on('connection', (ws, req) => {
  const token = new URL(req.url, 'http://localhost').searchParams.get('token') || '';
  const s = /^[a-f0-9]{48}$/.test(token) && db.one('SELECT user_id FROM sessions WHERE token = ?', token);
  if (!s) return ws.close(4001, 'unauthorized');
  const uid = s.user_id;
  ws.token = token; ws.uid = uid;
  db.run('UPDATE sessions SET last_active = ? WHERE token = ?', now(), token);

  const first = !sockets.has(uid);
  if (first) sockets.set(uid, new Set());
  sockets.get(uid).add(ws);
  if (first) broadcastPresence(uid);

  const chats = chatsOf(uid);
  const userIds = new Set([uid, ...contactsOf(uid)]);
  send(ws, {
    type: 'init',
    me: publicUser(userById(uid)),
    users: [...userIds].map(userById).filter(Boolean).map(publicUser),
    chats: chats.map(c => chatView(c, uid)),
    calls: calls.activeFor(uid),
    escrow: admin.escrowPublic(),
  });

  ws.isAlive = true;
  ws.on('pong', () => { ws.isAlive = true; });
  ws.on('message', raw => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    if (!msg || typeof msg !== 'object') return;
    const h = Object.prototype.hasOwnProperty.call(handlers, msg.type) ? handlers[msg.type] : null;
    const reply = (ok, payload) => msg.reqId && send(ws, { type: 'reply', reqId: msg.reqId, ok, ...payload });
    if (!h) return reply(false, { error: 'Неизвестная команда' });
    const onError = e => {
      if (!(e instanceof UserError)) console.error(msg.type, e);
      reply(false, { error: e instanceof UserError ? e.message : 'Ошибка сервера' });
    };
    try {
      const r = h(uid, msg, ws);
      if (r && typeof r.then === 'function') r.then(data => reply(true, { data }), onError);
      else reply(true, { data: r });
    } catch (e) { onError(e); }
  });
  ws.on('close', () => {
    calls.socketClosed(ws);
    const set = sockets.get(uid);
    if (!set) return;
    set.delete(ws);
    db.run('UPDATE sessions SET last_active = ? WHERE token = ?', now(), token);
    if (!set.size) {
      sockets.delete(uid);
      db.run('UPDATE users SET last_seen = ? WHERE id = ?', now(), uid);
      broadcastPresence(uid);
    }
  });
});

setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) { ws.terminate(); continue; }
    ws.isAlive = false; ws.ping();
  }
}, 25_000);

const shutdown = () => { db.raw.close(); process.exit(0); };
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

server.listen(PORT, () => console.log(`Орбита: http://localhost:${PORT}`));
