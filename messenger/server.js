'use strict';
// Telegraph — a small real-time messenger in the style of Telegram.
// HTTP: auth, file uploads, static files. WebSocket: everything else.

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { WebSocketServer } = require('ws');

const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, 'data');
const UPLOAD_DIR = path.join(DATA_DIR, 'uploads');
const DB_FILE = path.join(DATA_DIR, 'db.json');
const PUBLIC_DIR = path.join(__dirname, 'public');
const MAX_UPLOAD = 20 * 1024 * 1024;
const MAX_TEXT = 4096;
const PAGE = 50;

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// ---------- storage ----------
let db = { users: {}, sessions: {}, chats: {}, messages: {}, reads: {}, seq: { user: 0, chat: 0, msg: 0 } };
if (fs.existsSync(DB_FILE)) {
  try { db = Object.assign(db, JSON.parse(fs.readFileSync(DB_FILE, 'utf8'))); }
  catch (e) { console.error('Failed to read db.json:', e.message); process.exit(1); }
}
let saveTimer = null;
function save() {
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = null;
    const tmp = DB_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(db));
    fs.renameSync(tmp, DB_FILE);
  }, 300);
}
function flush() { if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; fs.writeFileSync(DB_FILE, JSON.stringify(db)); } }
process.on('SIGINT', () => { flush(); process.exit(0); });
process.on('SIGTERM', () => { flush(); process.exit(0); });

const COLORS = ['#e17076', '#7bc862', '#65aadd', '#a695e7', '#ee7aae', '#6ec9cb', '#faa774', '#5caffa'];

// ---------- helpers ----------
function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  return { salt, hash: crypto.scryptSync(password, salt, 64).toString('hex') };
}
function checkPassword(user, password) {
  const { hash } = hashPassword(password, user.salt);
  return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), Buffer.from(user.hash, 'hex'));
}
function publicUser(u) {
  return { id: u.id, username: u.username, name: u.name, bio: u.bio || '', color: u.color,
           online: sockets.has(u.id), lastSeen: u.lastSeen || 0 };
}
function findByUsername(name) {
  name = String(name || '').toLowerCase();
  return Object.values(db.users).find(u => u.username.toLowerCase() === name);
}
function str(v, max) { return typeof v === 'string' ? v.trim().slice(0, max) : ''; }

function newChat(type, members, extra = {}) {
  const id = ++db.seq.chat;
  const chat = { id, type, members, createdAt: Date.now(), ...extra };
  db.chats[id] = chat;
  db.messages[id] = [];
  db.reads[id] = {};
  save();
  return chat;
}
function chatsOf(uid) { return Object.values(db.chats).filter(c => c.members.includes(uid)); }

function chatView(chat, uid) {
  const msgs = db.messages[chat.id] || [];
  const reads = db.reads[chat.id] || {};
  const mine = reads[uid] || 0;
  let unread = 0;
  for (let i = msgs.length - 1; i >= 0 && msgs[i].id > mine; i--) if (msgs[i].from !== uid) unread++;
  return { ...chat, lastMessage: msgs[msgs.length - 1] || null, unread, reads };
}
function contactsOf(uid) {
  const set = new Set();
  for (const c of chatsOf(uid)) for (const m of c.members) set.add(m);
  return set;
}

// ---------- realtime ----------
const sockets = new Map(); // userId -> Set<ws>
function send(ws, obj) { if (ws.readyState === 1) ws.send(JSON.stringify(obj)); }
function toUser(uid, obj) { const s = sockets.get(uid); if (s) for (const ws of s) send(ws, obj); }
function toChat(chat, obj, except) { for (const m of chat.members) if (m !== except) toUser(m, obj); }
function broadcastPresence(uid) {
  const u = db.users[uid];
  const evt = { type: 'presence', userId: uid, online: sockets.has(uid), lastSeen: u.lastSeen || 0 };
  for (const c of contactsOf(uid)) if (c !== uid) toUser(c, evt);
}
function pushChat(chat) {
  // Send a fresh chat view + member profiles to every member.
  const users = chat.members.map(id => publicUser(db.users[id]));
  for (const m of chat.members) toUser(m, { type: 'chat', chat: chatView(chat, m), users });
}

function memberChat(uid, chatId) {
  const chat = db.chats[chatId];
  if (!chat || !chat.members.includes(uid)) throw new Error('Чат не найден');
  return chat;
}
function validFile(f) {
  if (!f) return null;
  if (typeof f.url !== 'string' || !/^\/uploads\/[a-f0-9]{32}(\.[a-z0-9]{1,8})?$/.test(f.url)) throw new Error('Неверный файл');
  if (!fs.existsSync(path.join(UPLOAD_DIR, path.basename(f.url)))) throw new Error('Файл не найден');
  return { url: f.url, name: str(f.name, 200) || 'file', size: Number(f.size) || 0, type: str(f.type, 100) };
}

const handlers = {
  searchUsers(uid, { q }) {
    q = str(q, 64).toLowerCase().replace(/^@/, '');
    if (!q) return [];
    return Object.values(db.users)
      .filter(u => u.id !== uid && (u.username.toLowerCase().includes(q) || u.name.toLowerCase().includes(q)))
      .slice(0, 20).map(publicUser);
  },

  openPrivate(uid, { userId }) {
    if (!db.users[userId]) throw new Error('Пользователь не найден');
    if (userId === uid) return chatsOf(uid).find(c => c.type === 'saved').id;
    let chat = Object.values(db.chats).find(c => c.type === 'private' && c.members.includes(uid) && c.members.includes(userId));
    if (!chat) { chat = newChat('private', [uid, userId]); pushChat(chat); }
    return chat.id;
  },

  createGroup(uid, { title, memberIds }) {
    title = str(title, 64);
    if (!title) throw new Error('Введите название группы');
    const members = [uid, ...new Set((memberIds || []).filter(id => db.users[id] && id !== uid))];
    const chat = newChat('group', members, { title, ownerId: uid, color: COLORS[Math.floor(Math.random() * COLORS.length)] });
    addService(chat, uid, `${db.users[uid].name} создал(а) группу «${title}»`);
    pushChat(chat);
    return chat.id;
  },

  addMembers(uid, { chatId, memberIds }) {
    const chat = memberChat(uid, chatId);
    if (chat.type !== 'group') throw new Error('Это не группа');
    const added = (memberIds || []).filter(id => db.users[id] && !chat.members.includes(id));
    if (!added.length) return true;
    chat.members.push(...added);
    addService(chat, uid, `${db.users[uid].name} добавил(а) ${added.map(id => db.users[id].name).join(', ')}`);
    pushChat(chat);
    return true;
  },

  renameGroup(uid, { chatId, title }) {
    const chat = memberChat(uid, chatId);
    title = str(title, 64);
    if (chat.type !== 'group' || !title) throw new Error('Нельзя переименовать');
    chat.title = title;
    addService(chat, uid, `${db.users[uid].name} изменил(а) название на «${title}»`);
    pushChat(chat);
    return true;
  },

  leaveChat(uid, { chatId }) {
    const chat = memberChat(uid, chatId);
    if (chat.type !== 'group') throw new Error('Покинуть можно только группу');
    addService(chat, uid, `${db.users[uid].name} покинул(а) группу`);
    chat.members = chat.members.filter(m => m !== uid);
    toUser(uid, { type: 'chatRemoved', chatId });
    if (!chat.members.length) { delete db.chats[chatId]; delete db.messages[chatId]; delete db.reads[chatId]; }
    else { if (chat.ownerId === uid) chat.ownerId = chat.members[0]; pushChat(chat); }
    save();
    return true;
  },

  history(uid, { chatId, before }) {
    memberChat(uid, chatId);
    const all = db.messages[chatId];
    let end = all.length;
    if (before) { end = all.findIndex(m => m.id >= before); if (end === -1) end = all.length; }
    const start = Math.max(0, end - PAGE);
    return { messages: all.slice(start, end), hasMore: start > 0 };
  },

  send(uid, { chatId, text, replyTo, file }) {
    const chat = memberChat(uid, chatId);
    text = typeof text === 'string' ? text.slice(0, MAX_TEXT).replace(/^\s+|\s+$/g, '') : '';
    const f = validFile(file);
    if (!text && !f) throw new Error('Пустое сообщение');
    const msg = { id: ++db.seq.msg, chatId, from: uid, text, ts: Date.now() };
    if (f) msg.file = f;
    if (replyTo && db.messages[chatId].some(m => m.id === replyTo)) msg.replyTo = replyTo;
    db.messages[chatId].push(msg);
    db.reads[chatId][uid] = msg.id;
    save();
    toChat(chat, { type: 'message', message: msg });
    toChat(chat, { type: 'read', chatId, userId: uid, msgId: msg.id });
    return msg;
  },

  edit(uid, { chatId, id, text }) {
    const chat = memberChat(uid, chatId);
    const msg = db.messages[chatId].find(m => m.id === id);
    if (!msg || msg.from !== uid || msg.service) throw new Error('Нельзя изменить');
    text = typeof text === 'string' ? text.slice(0, MAX_TEXT).trim() : '';
    if (!text && !msg.file) throw new Error('Пустое сообщение');
    msg.text = text; msg.edited = Date.now();
    save();
    toChat(chat, { type: 'edited', message: msg });
    return true;
  },

  delete(uid, { chatId, id }) {
    const chat = memberChat(uid, chatId);
    const list = db.messages[chatId];
    const i = list.findIndex(m => m.id === id);
    if (i === -1) return true;
    const msg = list[i];
    const canDelete = msg.from === uid || (chat.type === 'group' && chat.ownerId === uid);
    if (!canDelete) throw new Error('Нельзя удалить');
    list.splice(i, 1);
    save();
    toChat(chat, { type: 'deleted', chatId, id, lastMessage: list[list.length - 1] || null });
    return true;
  },

  read(uid, { chatId, msgId }) {
    const chat = memberChat(uid, chatId);
    const reads = db.reads[chatId];
    if (typeof msgId !== 'number' || msgId <= (reads[uid] || 0)) return true;
    reads[uid] = Math.min(msgId, db.seq.msg);
    save();
    toChat(chat, { type: 'read', chatId, userId: uid, msgId: reads[uid] });
    return true;
  },

  typing(uid, { chatId }) {
    const chat = memberChat(uid, chatId);
    toChat(chat, { type: 'typing', chatId, userId: uid }, uid);
    return true;
  },

  updateProfile(uid, { name, bio }) {
    const u = db.users[uid];
    name = str(name, 64);
    if (!name) throw new Error('Имя не может быть пустым');
    u.name = name; u.bio = str(bio, 140);
    save();
    const evt = { type: 'user', user: publicUser(u) };
    for (const c of contactsOf(uid)) toUser(c, evt);
    return publicUser(u);
  },
};

function addService(chat, uid, text) {
  const msg = { id: ++db.seq.msg, chatId: chat.id, from: uid, text, ts: Date.now(), service: true };
  db.messages[chat.id].push(msg);
  db.reads[chat.id][uid] = msg.id;
  save();
  toChat(chat, { type: 'message', message: msg });
}

// ---------- HTTP ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.ico': 'image/x-icon', '.json': 'application/json', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wav': 'audio/wav', '.m4a': 'audio/mp4', '.pdf': 'application/pdf', '.txt': 'text/plain; charset=utf-8' };
const INLINE_UPLOAD = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.mp3', '.ogg', '.wav', '.m4a']);

function json(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(obj));
}
function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', c => { size += c.length; if (size > limit) { reject(new Error('Слишком большой файл')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
function authUser(req) {
  const m = /^Bearer (\w+)$/.exec(req.headers.authorization || '');
  const uid = m && db.sessions[m[1]];
  return uid && db.users[uid] ? uid : null;
}
function issueToken(uid) {
  const token = crypto.randomBytes(24).toString('hex');
  db.sessions[token] = uid;
  save();
  return token;
}

async function api(req, res, url) {
  if (req.method === 'POST' && url.pathname === '/api/register') {
    const body = JSON.parse((await readBody(req, 10_000)).toString() || '{}');
    const username = str(body.username, 32), name = str(body.name, 64), password = String(body.password || '');
    if (!/^[a-zA-Z][a-zA-Z0-9_]{2,31}$/.test(username)) return json(res, 400, { error: 'Имя пользователя: 3–32 символа, латиница, цифры и _' });
    if (!name) return json(res, 400, { error: 'Введите имя' });
    if (password.length < 6) return json(res, 400, { error: 'Пароль — минимум 6 символов' });
    if (findByUsername(username)) return json(res, 400, { error: 'Это имя пользователя уже занято' });
    const id = ++db.seq.user;
    const { salt, hash } = hashPassword(password);
    db.users[id] = { id, username, name, salt, hash, bio: '', color: COLORS[id % COLORS.length], createdAt: Date.now(), lastSeen: Date.now() };
    newChat('saved', [id]);
    return json(res, 200, { token: issueToken(id) });
  }
  if (req.method === 'POST' && url.pathname === '/api/login') {
    const body = JSON.parse((await readBody(req, 10_000)).toString() || '{}');
    const u = findByUsername(body.username);
    if (!u || !checkPassword(u, String(body.password || ''))) return json(res, 401, { error: 'Неверное имя пользователя или пароль' });
    return json(res, 200, { token: issueToken(u.id) });
  }
  if (req.method === 'POST' && url.pathname === '/api/logout') {
    const m = /^Bearer (\w+)$/.exec(req.headers.authorization || '');
    if (m) { delete db.sessions[m[1]]; save(); }
    return json(res, 200, { ok: true });
  }
  if (req.method === 'POST' && url.pathname === '/api/upload') {
    if (!authUser(req)) return json(res, 401, { error: 'Нужна авторизация' });
    const data = await readBody(req, MAX_UPLOAD);
    if (!data.length) return json(res, 400, { error: 'Пустой файл' });
    let name = 'file';
    try { name = decodeURIComponent(req.headers['x-filename'] || 'file').slice(0, 200); } catch {}
    let ext = path.extname(name).toLowerCase();
    if (!/^\.[a-z0-9]{1,8}$/.test(ext)) ext = '';
    const file = crypto.randomBytes(16).toString('hex') + ext;
    fs.writeFileSync(path.join(UPLOAD_DIR, file), data);
    return json(res, 200, { url: '/uploads/' + file, name, size: data.length, type: str(req.headers['content-type'], 100) });
  }
  json(res, 404, { error: 'Not found' });
}

function serveFile(res, file, headers = {}) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end('Not found'); }
    res.writeHead(200, { 'Content-Length': st.size, ...headers });
    fs.createReadStream(file).pipe(res);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    if (url.pathname.startsWith('/api/')) return await api(req, res, url);
    if (url.pathname.startsWith('/uploads/')) {
      const name = path.basename(url.pathname);
      const ext = path.extname(name).toLowerCase();
      const headers = { 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public, max-age=31536000, immutable' };
      if (INLINE_UPLOAD.has(ext)) headers['Content-Type'] = MIME[ext];
      else { headers['Content-Type'] = 'application/octet-stream'; headers['Content-Disposition'] = 'attachment'; }
      return serveFile(res, path.join(UPLOAD_DIR, name), headers);
    }
    let p = path.normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '');
    if (!p || p === '.') p = 'index.html';
    const file = path.join(PUBLIC_DIR, p);
    if (!file.startsWith(PUBLIC_DIR + path.sep)) { res.writeHead(403); return res.end(); }
    serveFile(res, file, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' });
  } catch (e) {
    json(res, 400, { error: e.message || 'Ошибка' });
  }
});

// ---------- WebSocket ----------
const wss = new WebSocketServer({ server, path: '/ws', maxPayload: 64 * 1024 });

wss.on('connection', (ws, req) => {
  const token = new URL(req.url, 'http://localhost').searchParams.get('token');
  const uid = db.sessions[token];
  if (!uid || !db.users[uid]) return ws.close(4001, 'unauthorized');

  const wasOnline = sockets.has(uid);
  if (!wasOnline) sockets.set(uid, new Set());
  sockets.get(uid).add(ws);
  if (!wasOnline) broadcastPresence(uid);

  const chats = chatsOf(uid);
  const users = {};
  for (const c of chats) for (const m of c.members) users[m] = publicUser(db.users[m]);
  users[uid] = publicUser(db.users[uid]);
  send(ws, { type: 'init', me: publicUser(db.users[uid]), users: Object.values(users), chats: chats.map(c => chatView(c, uid)) });

  ws.isAlive = true;
  ws.on('pong', () => { ws.isAlive = true; });

  ws.on('message', raw => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    const h = Object.prototype.hasOwnProperty.call(handlers, msg.type) && handlers[msg.type];
    if (!h) return send(ws, { type: 'reply', reqId: msg.reqId, ok: false, error: 'Неизвестная команда' });
    try {
      const data = h(uid, msg);
      if (msg.reqId) send(ws, { type: 'reply', reqId: msg.reqId, ok: true, data });
    } catch (e) {
      if (msg.reqId) send(ws, { type: 'reply', reqId: msg.reqId, ok: false, error: e.message });
    }
  });

  ws.on('close', () => {
    const set = sockets.get(uid);
    if (!set) return;
    set.delete(ws);
    if (!set.size) {
      sockets.delete(uid);
      if (db.users[uid]) { db.users[uid].lastSeen = Date.now(); save(); broadcastPresence(uid); }
    }
  });
});

setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) { ws.terminate(); continue; }
    ws.isAlive = false; ws.ping();
  }
}, 30_000);

server.listen(PORT, () => console.log(`Telegraph running on http://localhost:${PORT}`));
