'use strict';
// Bot platform with an HTTP API modelled on the Telegram Bot API:
//   https://<host>/bot<TOKEN>/<method>   (GET query, JSON, form-urlencoded or multipart)
//
// A bot is a regular user whose identity key is held by the server. Clients wrap chat keys for the bot
// like for any member; the server decrypts what the bot is allowed to see, hands it to the bot as plain
// JSON updates (long polling or webhook), and encrypts the bot's replies with the chat key.
// Chats with bots are therefore readable by the bot's operator — the UI says so.

const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');

const MAX_PENDING = 1000;
const C = import(pathToFileURL(path.join(__dirname, '..', 'public', 'js', 'crypto.js')).href);

function createBots(ctx) {
  const { db, fail, UserError, toUser, toChat, memberIds, chatRow, insertMessage, messageView, publicUser, userById, escrowPublic, pushChat, storeKeys, BLOB_DIR, COLORS } = ctx;

  // ---------- helpers ----------
  const sha = s => crypto.createHash('sha256').update(s).digest('hex');
  const botRow = id => db.one('SELECT * FROM bots WHERE user_id = ?', id);
  const isBot = id => !!db.one('SELECT 1 FROM bots WHERE user_id = ?', id);
  function botByToken(token) {
    const m = /^(\d+):([A-Za-z0-9_-]{30,64})$/.exec(token || '');
    if (!m) return null;
    const b = botRow(Number(m[1]));
    if (!b) return null;
    const a = Buffer.from(sha(m[2]), 'hex'), h = Buffer.from(b.token_hash, 'hex');
    return a.length === h.length && crypto.timingSafeEqual(a, h) ? b : null;
  }
  const newSecret = () => crypto.randomBytes(27).toString('base64url');
  const meta = b => ({ description: b.description, commands: JSON.parse(b.commands || '[]'), privacy: !!b.privacy, ownerId: b.owner_id });

  const identities = new Map();
  async function identity(botId) {
    if (!identities.has(botId)) {
      const p = (async () => {
        const b = botRow(botId);
        const privateKey = await crypto.webcrypto.subtle.importKey('pkcs8', Buffer.from(b.private_key, 'base64'), { name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
        return { id: botId, privateKey, publicKey: userById(botId).public_key };
      })();
      p.catch(() => identities.delete(botId));
      identities.set(botId, p);
    }
    return identities.get(botId);
  }
  const pub = u => ({ id: u.id, publicKey: u.public_key });

  const keys = new Map(); // `${bot}:${chat}:${v}` -> Promise<CryptoKey>
  async function chatKey(botId, chatId, v) {
    const k = `${botId}:${chatId}:${v}`;
    if (!keys.has(k)) {
      const p = (async () => {
        const row = db.one('SELECT * FROM chat_keys WHERE chat_id = ? AND version = ? AND user_id = ?', chatId, v, botId);
        if (!row) throw new Error('no key');
        const wrapper = userById(row.wrapper_id);
        return (await C).openChatKey(await identity(botId), pub(wrapper), v, row);
      })();
      p.catch(() => keys.delete(k));
      keys.set(k, p);
    }
    return keys.get(k);
  }
  // The bot needs the current key version. If members changed (or none exists yet) it rotates, like any client.
  async function currentKey(botId, chatId) {
    let c = chatRow(chatId);
    const have = db.one('SELECT 1 FROM chat_keys WHERE chat_id = ? AND version = ? AND user_id = ?', chatId, c.key_version, botId);
    if (c.rotate_needed || c.key_version === 0 || !have) {
      const v = c.key_version + 1;
      const members = memberIds(chatId).map(userById).map(pub);
      const esc = escrowPublic();
      if (esc) members.push({ id: 0, publicKey: esc });
      const { key, bundle } = await (await C).newChatKey(await identity(botId), members, v);
      c = chatRow(chatId);
      if (c.key_version + 1 !== v) return currentKey(botId, chatId); // someone rotated meanwhile
      db.tx(() => {
        storeKeys(chatId, v, botId, bundle);
        db.run('UPDATE chats SET key_version = ?, rotate_needed = 0 WHERE id = ?', v, chatId);
      });
      keys.set(`${botId}:${chatId}:${v}`, Promise.resolve(key));
      pushChat(chatId);
      return { v, key };
    }
    return { v: c.key_version, key: await chatKey(botId, chatId, c.key_version) };
  }
  async function decryptFor(botId, m) {
    if (m.kind !== 'msg') return null;
    try { return await (await C).decryptJson(await chatKey(botId, m.chatId, m.kv), m, `msg:${m.chatId}`); }
    catch { return null; }
  }

  // ---------- update objects (Telegram-like) ----------
  const sec = ms => Math.floor(ms / 1000);
  function apiUser(u) {
    if (!u) return { id: 0, is_bot: false, first_name: 'Удалённый' };
    const [first, ...rest] = u.name.split(' ');
    return { id: u.id, is_bot: isBot(u.id), first_name: first, ...(rest.length ? { last_name: rest.join(' ') } : {}), username: u.username, language_code: 'ru' };
  }
  function apiChat(c) {
    if (c.type === 'group') return { id: c.id, type: 'group', title: c.title };
    return { id: c.id, type: 'private' };
  }
  function fileRef(botId, f) {
    const fileId = 'F' + sha(botId + ':' + f.id).slice(0, 40);
    db.run(`INSERT OR IGNORE INTO bot_files (file_id, bot_id, blob_id, key, iv, name, type, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      fileId, botId, f.id, f.key, f.iv, f.name || 'file', f.type || 'application/octet-stream', f.size || 0, Date.now());
    return fileId;
  }
  async function apiMessage(botId, m, p, { withReply = true } = {}) {
    const c = chatRow(m.chatId);
    const out = { message_id: m.id, date: sec(m.ts), chat: apiChat(c), from: apiUser(userById(m.from)) };
    if (m.edited) out.edit_date = sec(m.edited);
    if (p) {
      const f = p.file;
      if (f && f.id) {
        const fid = fileRef(botId, f);
        if (p.voice) out.voice = { file_id: fid, file_unique_id: fid, duration: Math.round(p.voice.dur), mime_type: f.type, file_size: f.size };
        else if ((f.type || '').startsWith('image/')) out.photo = [{ file_id: fid, file_unique_id: fid, width: f.w || 0, height: f.h || 0, file_size: f.size }];
        else if ((f.type || '').startsWith('video/')) out.video = { file_id: fid, file_unique_id: fid, file_name: f.name, mime_type: f.type, file_size: f.size };
        else out.document = { file_id: fid, file_unique_id: fid, file_name: f.name, mime_type: f.type, file_size: f.size };
        if (p.t) out.caption = p.t;
      } else if (p.t) out.text = p.t;
      if (p.poll) out.poll = { id: String(m.id), question: p.poll.q, options: p.poll.opts.map(t => ({ text: t })), allows_multiple_answers: !!p.poll.multi };
      if (p.fwd) out.forward_sender_name = p.fwd;
      if (out.text?.startsWith('/')) {
        const len = out.text.split(/\s/)[0].length;
        out.entities = [{ type: 'bot_command', offset: 0, length: len }];
      }
    }
    if (withReply && m.replyTo) {
      const r = messageView(m.replyTo);
      if (r) out.reply_to_message = await apiMessage(botId, r, await decryptFor(botId, r), { withReply: false });
    }
    return out;
  }

  // ---------- queue, long polling, webhooks ----------
  const waiters = new Map(); // botId -> Set<fn>
  function enqueue(botId, update) {
    const id = Number(db.run('INSERT INTO bot_updates (bot_id, payload, created_at) VALUES (?, ?, ?)', botId, '{}', Date.now()).lastInsertRowid);
    db.run('UPDATE bot_updates SET payload = ? WHERE id = ?', JSON.stringify({ update_id: id, ...update }), id);
    db.run(`DELETE FROM bot_updates WHERE bot_id = ? AND id <= (SELECT id FROM bot_updates WHERE bot_id = ? ORDER BY id DESC LIMIT 1 OFFSET ?)`, botId, botId, MAX_PENDING);
    for (const w of waiters.get(botId) || []) w();
    const b = botRow(botId);
    if (b?.webhook_url) deliver(botId);
  }
  const delivering = new Set();
  async function deliver(botId, attempt = 0) {
    if (delivering.has(botId)) return;
    delivering.add(botId);
    try {
      for (;;) {
        const b = botRow(botId);
        if (!b?.webhook_url) return;
        const u = db.one('SELECT * FROM bot_updates WHERE bot_id = ? ORDER BY id LIMIT 1', botId);
        if (!u) return;
        const res = await fetch(b.webhook_url, {
          method: 'POST', body: u.payload, redirect: 'error', signal: AbortSignal.timeout(10_000),
          headers: { 'Content-Type': 'application/json', ...(b.webhook_secret ? { 'X-Orbita-Bot-Api-Secret-Token': b.webhook_secret } : {}) },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        db.run('DELETE FROM bot_updates WHERE id = ?', u.id);
        db.run('UPDATE bots SET webhook_error = NULL WHERE user_id = ?', botId);
        attempt = 0;
      }
    } catch (e) {
      db.run('UPDATE bots SET webhook_error = ? WHERE user_id = ?', `${new Date().toISOString()} ${e.message}`.slice(0, 200), botId);
      const delay = Math.min(60_000, 2000 * 2 ** attempt);
      setTimeout(() => deliver(botId, attempt + 1), delay).unref();
    } finally { delivering.delete(botId); }
  }
  // resume webhooks after restart
  for (const b of db.all("SELECT user_id FROM bots WHERE webhook_url IS NOT NULL AND webhook_url != ''")) setTimeout(() => deliver(b.user_id), 2000).unref();

  function checkWebhookUrl(url) {
    let u;
    try { u = new URL(url); } catch { fail('Неверный адрес вебхука'); }
    const local = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.|\[?::1\]?|\[?f[cd])/i.test(u.hostname);
    if (process.env.BOT_WEBHOOK_ALLOW_PRIVATE === '1') { if (!/^https?:$/.test(u.protocol)) fail('Нужен http(s)'); }
    else if (u.protocol !== 'https:' || local) fail('Вебхук должен быть публичным адресом https://');
    return u.href;
  }

  // ---------- hooks from the messenger ----------
  const botMembers = chatId => db.all('SELECT b.* FROM bots b JOIN members m ON m.user_id = b.user_id WHERE m.chat_id = ?', chatId);
  async function onMessage(m, kind = 'message') {
    if (m.kind !== 'msg' && !(m.kind === 'service' && m.meta?.event === 'added')) return;
    for (const b of botMembers(m.chatId)) {
      if (b.user_id === m.from) continue;
      try {
        const c = chatRow(m.chatId);
        if (m.kind === 'service') {
          if (!m.meta.users.includes(b.user_id)) continue;
          enqueue(b.user_id, { my_chat_member: { chat: apiChat(c), from: apiUser(userById(m.from)), date: sec(m.ts), new_chat_member: { user: apiUser(userById(b.user_id)), status: 'member' } } });
          continue;
        }
        const p = await decryptFor(b.user_id, m);
        if (!p) continue;
        if (c.type === 'group' && b.privacy) {
          const me = userById(b.user_id).username.toLowerCase();
          const t = (p.t || '').toLowerCase();
          const replyToBot = m.replyTo && messageView(m.replyTo)?.from === b.user_id;
          const cmd = /^\/[a-z0-9_]+(@[a-z0-9_]+)?/.exec(t);
          const commandForMe = cmd && (!cmd[1] || cmd[1] === '@' + me);
          if (!commandForMe && !t.includes('@' + me) && !replyToBot) continue;
        }
        enqueue(b.user_id, { [kind]: await apiMessage(b.user_id, m, p) });
      } catch (e) { console.error('bot update', e); }
    }
  }

  // ---------- sending as a bot ----------
  function markup(rm) {
    if (rm == null) return {};
    if (typeof rm === 'string') { try { rm = JSON.parse(rm); } catch { fail('reply_markup: неверный JSON'); } }
    if (rm.inline_keyboard) {
      const rows = rm.inline_keyboard.slice(0, 12).map(row => row.slice(0, 8).map(b => {
        const t = String(b.text ?? '').slice(0, 64);
        if (!t) fail('Кнопке нужен text');
        if (b.url) { if (!/^https?:\/\//.test(b.url)) fail('url кнопки должен начинаться с http(s)://'); return { t, u: String(b.url).slice(0, 512) }; }
        if (b.callback_data == null) fail('Кнопке нужен callback_data или url');
        const d = String(b.callback_data);
        if (Buffer.byteLength(d) > 64) fail('callback_data длиннее 64 байт');
        return { t, d };
      }));
      return { kb: rows };
    }
    if (rm.keyboard) return { rk: { rows: rm.keyboard.slice(0, 12).map(r => r.slice(0, 8).map(b => String(typeof b === 'string' ? b : b.text).slice(0, 64))), once: !!rm.one_time_keyboard, ph: rm.input_field_placeholder ? String(rm.input_field_placeholder).slice(0, 64) : undefined } };
    if (rm.remove_keyboard) return { rk: { remove: true } };
    return {};
  }
  function formatText(text, mode) {
    text = String(text ?? '');
    if (/^html$/i.test(mode || '')) {
      text = text.replace(/<\/?(b|strong)>/gi, '**').replace(/<\/?code>/gi, '`').replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]+>/g, '')
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    } else if (/^markdown/i.test(mode || '')) {
      text = text.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1**$2**').replace(/\\([_*[\]()~`>#+\-=|{}.!])/g, '$1');
    }
    return text.slice(0, 4096);
  }
  function botChat(b, chatId) {
    chatId = Number(chatId);
    const c = Number.isInteger(chatId) && chatRow(chatId);
    if (!c || !memberIds(chatId).includes(b.user_id)) apiFail(400, 'Bad Request: chat not found');
    return c;
  }
  async function sendAs(b, c, payload, { replyTo, blobs, poll } = {}) {
    const { v, key } = await currentKey(b.user_id, c.id);
    const box = await (await C).encryptJson(key, payload, `msg:${c.id}`);
    const metaObj = {};
    if (blobs?.length) metaObj.blobs = blobs;
    if (poll) metaObj.poll = poll;
    let reply = null;
    if (replyTo && db.one('SELECT 1 FROM messages WHERE id = ? AND chat_id = ?', Number(replyTo), c.id)) reply = Number(replyTo);
    const m = insertMessage(c.id, b.user_id, 'msg', { kv: v, ...box, meta: metaObj, replyTo: reply });
    return apiMessage(b.user_id, m, payload);
  }

  class ApiError extends Error { constructor(code, d) { super(d); this.code = code; } }
  const apiFail = (code, d) => { throw new ApiError(code, d); };
  const ownBotMessage = (b, c, id) => {
    const m = db.one('SELECT * FROM messages WHERE id = ? AND chat_id = ?', Number(id), c.id);
    if (!m) apiFail(400, 'Bad Request: message to edit not found');
    return m;
  };

  async function upload(b, file, fallbackName, type) {
    const buf = Buffer.from(await file.arrayBuffer());
    if (!buf.length) apiFail(400, 'Bad Request: file is empty');
    if (buf.length > 50 * 1024 * 1024) apiFail(413, 'Request Entity Too Large');
    const { data, key, iv } = await (await C).encryptFile(buf);
    const id = crypto.randomBytes(16).toString('hex');
    await fs.promises.writeFile(path.join(BLOB_DIR, id), Buffer.from(data));
    db.run('INSERT INTO blobs (id, owner_id, size, created_at) VALUES (?, ?, ?, ?)', id, b.user_id, data.byteLength, Date.now());
    return { id, key, iv, name: file.name || fallbackName, type: file.type && file.type !== 'application/octet-stream' ? file.type : type, size: buf.length };
  }
  const mediaMethod = (field, defType, defName) => async (b, p) => {
    const c = botChat(b, p.chat_id);
    const f = p[field];
    if (!f || typeof f === 'string') apiFail(400, `Bad Request: загрузите файл в поле ${field} (multipart/form-data)`);
    const file = await upload(b, f, defName, f.type || defType);
    const payload = { t: formatText(p.caption, p.parse_mode), file, ...markup(p.reply_markup) };
    if (field === 'voice') payload.voice = { dur: Number(p.duration) || 1, wave: Array.from({ length: 48 }, (_, i) => 6 + Math.round(10 * Math.abs(Math.sin(i * 1.7)))) };
    return sendAs(b, c, payload, { replyTo: p.reply_to_message_id, blobs: [file.id] });
  };

  const methods = {
    getMe: b => { const u = userById(b.user_id); return { ...apiUser(u), can_join_groups: true, can_read_all_group_messages: !b.privacy, supports_inline_queries: false }; },

    async getUpdates(b, p, req) {
      if (b.webhook_url) apiFail(409, "Conflict: can't use getUpdates method while webhook is active; use deleteWebhook to delete the webhook first");
      const offset = Number(p.offset) || 0, limit = Math.min(100, Math.max(1, Number(p.limit) || 100)), timeout = Math.min(50, Math.max(0, Number(p.timeout) || 0));
      if (offset) db.run('DELETE FROM bot_updates WHERE bot_id = ? AND id < ?', b.user_id, offset);
      const read = () => db.all('SELECT payload FROM bot_updates WHERE bot_id = ? AND id >= ? ORDER BY id LIMIT ?', b.user_id, offset, limit).map(r => JSON.parse(r.payload));
      let list = read();
      if (list.length || !timeout) return list;
      await new Promise(resolve => {
        const set = waiters.get(b.user_id) || waiters.set(b.user_id, new Set()).get(b.user_id);
        const done = () => { clearTimeout(t); set.delete(done); resolve(); };
        const t = setTimeout(done, timeout * 1000);
        set.add(done);
        req.on('close', done);
      });
      return read();
    },

    setWebhook(b, p) {
      if (!p.url) { db.run('UPDATE bots SET webhook_url = NULL, webhook_secret = NULL WHERE user_id = ?', b.user_id); return true; }
      const url = checkWebhookUrl(String(p.url));
      const secret = p.secret_token ? String(p.secret_token) : null;
      if (secret && !/^[A-Za-z0-9_-]{1,256}$/.test(secret)) apiFail(400, 'Bad Request: secret_token: только A-Z, a-z, 0-9, _ и -');
      db.run('UPDATE bots SET webhook_url = ?, webhook_secret = ?, webhook_error = NULL WHERE user_id = ?', url, secret, b.user_id);
      if (p.drop_pending_updates === true || p.drop_pending_updates === 'true') db.run('DELETE FROM bot_updates WHERE bot_id = ?', b.user_id);
      deliver(b.user_id);
      return true;
    },
    deleteWebhook(b, p) {
      db.run('UPDATE bots SET webhook_url = NULL, webhook_secret = NULL WHERE user_id = ?', b.user_id);
      if (p.drop_pending_updates === true || p.drop_pending_updates === 'true') db.run('DELETE FROM bot_updates WHERE bot_id = ?', b.user_id);
      return true;
    },
    getWebhookInfo: b => ({ url: b.webhook_url || '', has_custom_certificate: false,
      pending_update_count: db.one('SELECT COUNT(*) n FROM bot_updates WHERE bot_id = ?', b.user_id).n, ...(b.webhook_error ? { last_error_message: b.webhook_error } : {}) }),

    async sendMessage(b, p) {
      const c = botChat(b, p.chat_id);
      const t = formatText(p.text, p.parse_mode);
      if (!t.trim()) apiFail(400, 'Bad Request: message text is empty');
      return sendAs(b, c, { t, ...markup(p.reply_markup) }, { replyTo: p.reply_to_message_id ?? p.reply_parameters?.message_id });
    },
    sendPhoto: mediaMethod('photo', 'image/jpeg', 'photo.jpg'),
    sendDocument: mediaMethod('document', 'application/octet-stream', 'file'),
    sendVideo: mediaMethod('video', 'video/mp4', 'video.mp4'),
    sendAudio: mediaMethod('audio', 'audio/mpeg', 'audio.mp3'),
    sendVoice: mediaMethod('voice', 'audio/ogg', 'voice.ogg'),

    async sendPoll(b, p) {
      const c = botChat(b, p.chat_id);
      let opts = p.options;
      if (typeof opts === 'string') { try { opts = JSON.parse(opts); } catch { apiFail(400, 'Bad Request: options must be JSON array'); } }
      opts = (opts || []).map(o => String(typeof o === 'string' ? o : o.text).slice(0, 100)).filter(Boolean);
      if (!p.question || opts.length < 2 || opts.length > 10) apiFail(400, 'Bad Request: need question and 2–10 options');
      const multi = p.allows_multiple_answers === true || p.allows_multiple_answers === 'true';
      return sendAs(b, c, { poll: { q: String(p.question).slice(0, 200), opts, multi } }, { poll: { count: opts.length, multiple: multi } });
    },

    async editMessageText(b, p) {
      const c = botChat(b, p.chat_id);
      const m = ownBotMessage(b, c, p.message_id);
      if (m.sender_id !== b.user_id) apiFail(400, "Bad Request: message can't be edited");
      const old = await decryptFor(b.user_id, messageView(m.id)) || {};
      const payload = { ...old, t: formatText(p.text, p.parse_mode), ...markup(p.reply_markup) };
      if (!p.reply_markup) delete payload.kb;
      return editAs(b, c, m, payload);
    },
    async editMessageReplyMarkup(b, p) {
      const c = botChat(b, p.chat_id);
      const m = ownBotMessage(b, c, p.message_id);
      if (m.sender_id !== b.user_id) apiFail(400, "Bad Request: message can't be edited");
      const old = await decryptFor(b.user_id, messageView(m.id)) || {};
      const payload = { ...old }; delete payload.kb;
      Object.assign(payload, markup(p.reply_markup));
      return editAs(b, c, m, payload);
    },
    deleteMessage(b, p) {
      const c = botChat(b, p.chat_id);
      const m = ownBotMessage(b, c, p.message_id);
      if (m.sender_id !== b.user_id) apiFail(400, "Bad Request: message can't be deleted");
      ctx.removeMessages([m]);
      return true;
    },
    answerCallbackQuery(b, p) {
      const q = db.one('SELECT * FROM bot_callbacks WHERE id = ? AND bot_id = ?', String(p.callback_query_id || ''), b.user_id);
      if (!q) apiFail(400, 'Bad Request: query is too old or query ID is invalid');
      db.run('DELETE FROM bot_callbacks WHERE id = ?', q.id);
      if (p.text || p.url) toUser(q.user_id, { type: 'botAnswer', chatId: q.chat_id, botId: b.user_id, text: String(p.text || '').slice(0, 200), alert: p.show_alert === true || p.show_alert === 'true' });
      return true;
    },
    sendChatAction(b, p) {
      const c = botChat(b, p.chat_id);
      toChat(c.id, { type: 'typing', chatId: c.id, userId: b.user_id, kind: p.action === 'record_voice' ? 'voice' : 'text' }, b.user_id);
      return true;
    },
    setMyCommands(b, p) {
      let list = p.commands;
      if (typeof list === 'string') { try { list = JSON.parse(list); } catch { apiFail(400, 'Bad Request: commands must be JSON'); } }
      if (!Array.isArray(list) || list.length > 100) apiFail(400, 'Bad Request: commands must be an array (≤100)');
      const clean = list.map(x => ({ command: String(x.command || '').replace(/^\//, '').toLowerCase(), description: String(x.description || '').slice(0, 256) }));
      if (clean.some(x => !/^[a-z0-9_]{1,32}$/.test(x.command))) apiFail(400, 'Bad Request: command must be 1-32 chars of a-z, 0-9, _');
      db.run('UPDATE bots SET commands = ? WHERE user_id = ?', JSON.stringify(clean), b.user_id);
      announce(b.user_id);
      return true;
    },
    getMyCommands: b => JSON.parse(b.commands || '[]'),
    deleteMyCommands(b) { db.run("UPDATE bots SET commands = '[]' WHERE user_id = ?", b.user_id); announce(b.user_id); return true; },
    setMyDescription(b, p) { db.run('UPDATE bots SET description = ? WHERE user_id = ?', String(p.description || '').slice(0, 512), b.user_id); announce(b.user_id); return true; },
    getChat(b, p) {
      const c = botChat(b, p.chat_id);
      const ids = memberIds(c.id);
      return { ...apiChat(c), ...(c.type === 'direct' ? { ...apiUser(userById(ids.find(i => i !== b.user_id))), id: c.id, type: 'private' } : {}), member_count: ids.length };
    },
    getChatMemberCount: (b, p) => memberIds(botChat(b, p.chat_id).id).length,
    getFile(b, p) {
      const f = db.one('SELECT * FROM bot_files WHERE file_id = ? AND bot_id = ?', String(p.file_id || ''), b.user_id);
      if (!f) apiFail(400, 'Bad Request: invalid file_id');
      return { file_id: f.file_id, file_unique_id: f.file_id, file_size: f.size, file_path: f.file_id + '/' + encodeURIComponent(f.name) };
    },
  };
  async function editAs(b, c, m, payload) {
    const { v, key } = await currentKey(b.user_id, c.id);
    const box = await (await C).encryptJson(key, payload, `msg:${c.id}`);
    db.run('UPDATE messages SET kv = ?, iv = ?, ct = ?, edited_at = ? WHERE id = ?', v, box.iv, box.ct, Date.now(), m.id);
    const view = messageView(m.id);
    toChat(c.id, { type: 'edited', message: view });
    return apiMessage(b.user_id, view, payload);
  }
  function announce(botId) {
    const evt = { type: 'user', user: publicUser(userById(botId)) };
    for (const r of db.all('SELECT DISTINCT m2.user_id id FROM members m1 JOIN members m2 ON m1.chat_id = m2.chat_id WHERE m1.user_id = ?', botId)) toUser(r.id, evt);
  }

  // ---------- HTTP entry ----------
  async function params(req, url, readBody) {
    const p = Object.fromEntries(url.searchParams);
    if (req.method !== 'POST') return p;
    const ct = req.headers['content-type'] || '';
    const body = await readBody(req, 52 * 1024 * 1024);
    if (!body.length) return p;
    if (ct.includes('application/json')) { try { Object.assign(p, JSON.parse(body.toString())); } catch { apiFail(400, 'Bad Request: invalid JSON'); } }
    else if (ct.includes('multipart/form-data') || ct.includes('application/x-www-form-urlencoded')) {
      const fd = await new Response(body, { headers: { 'content-type': ct } }).formData();
      for (const [k, v] of fd) p[k] = v;
    }
    return p;
  }
  async function handle(req, res, url, readBody) {
    const send = (code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(obj)); };
    const file = /^\/file\/bot([^/]+)\/(F[a-f0-9]{40})(\/.*)?$/.exec(url.pathname);
    if (file) {
      const b = botByToken(decodeURIComponent(file[1]));
      const f = b && db.one('SELECT * FROM bot_files WHERE file_id = ? AND bot_id = ?', file[2], b.user_id);
      if (!f) return send(404, { ok: false, error_code: 404, description: 'Not Found' });
      try {
        const buf = await fs.promises.readFile(path.join(BLOB_DIR, f.blob_id));
        const plain = Buffer.from(await (await C).decryptFile(buf, f.key, f.iv));
        res.writeHead(200, { 'Content-Type': f.type, 'Content-Length': plain.length });
        return res.end(plain);
      } catch { return send(404, { ok: false, error_code: 404, description: 'Not Found: file was deleted' }); }
    }
    const m = /^\/bot([^/]+)\/([A-Za-z]+)$/.exec(url.pathname);
    if (!m) return send(404, { ok: false, error_code: 404, description: 'Not Found' });
    const b = botByToken(decodeURIComponent(m[1]));
    if (!b) return send(401, { ok: false, error_code: 401, description: 'Unauthorized' });
    const fn = Object.prototype.hasOwnProperty.call(methods, m[2]) ? methods[m[2]] : null;
    if (!fn) return send(404, { ok: false, error_code: 404, description: 'Not Found: method not found' });
    try {
      const result = await fn(b, await params(req, url, readBody), req);
      if (!res.writableEnded) send(200, { ok: true, result });
    } catch (e) {
      if (e instanceof ApiError) return send(e.code, { ok: false, error_code: e.code, description: e.description || e.message });
      if (e instanceof UserError) return send(400, { ok: false, error_code: 400, description: 'Bad Request: ' + e.message });
      console.error('bot api', m[2], e);
      send(500, { ok: false, error_code: 500, description: 'Internal Server Error' });
    }
  }

  // ---------- management by owners (WebSocket handlers) ----------
  const own = (uid, botId) => { const b = Number.isInteger(botId) && botRow(botId); if (!b || b.owner_id !== uid) fail('Бот не найден'); return b; };
  const view = b => { const u = userById(b.user_id); return { ...publicUser(u), ...meta(b), webhook: b.webhook_url || '', webhookError: b.webhook_error || '', pending: db.one('SELECT COUNT(*) n FROM bot_updates WHERE bot_id = ?', b.user_id).n }; };
  const handlers = {
    myBots: uid => db.all('SELECT * FROM bots WHERE owner_id = ? ORDER BY created_at', uid).map(view),

    async createBot(uid, { name, username }) {
      name = typeof name === 'string' ? name.trim().slice(0, 64) : '';
      username = typeof username === 'string' ? username.trim().replace(/^@/, '') : '';
      if (!name) fail('Назовите бота');
      if (!/^[a-zA-Z][a-zA-Z0-9_]{1,28}bot$/i.test(username)) fail('Логин бота: латиница, цифры и _, заканчивается на «bot», например weather_bot');
      if (db.one('SELECT 1 FROM users WHERE username = ?', username)) fail('Этот логин уже занят');
      if (db.one('SELECT COUNT(*) n FROM bots WHERE owner_id = ?', uid).n >= 20) fail('Не больше 20 ботов на аккаунт');
      const kp = await crypto.webcrypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
      const publicKey = Buffer.from(await crypto.webcrypto.subtle.exportKey('spki', kp.publicKey)).toString('base64');
      const privateKey = Buffer.from(await crypto.webcrypto.subtle.exportKey('pkcs8', kp.privateKey)).toString('base64');
      const secret = newSecret();
      const id = db.tx(() => {
        const id = Number(db.run(`INSERT INTO users (username, name, bio, color, auth_hash, auth_salt, public_key, sealed_key, created_at, last_seen)
                                  VALUES (?, ?, '', ?, '-', '-', ?, '{}', ?, 0)`, username, name, COLORS[crypto.randomInt(COLORS.length)], publicKey, Date.now()).lastInsertRowid);
        db.run(`INSERT INTO bots (user_id, owner_id, token_hash, private_key, description, commands, privacy, created_at) VALUES (?, ?, ?, ?, '', '[]', 1, ?)`, id, uid, sha(secret), privateKey, Date.now());
        return id;
      });
      return { bot: view(botRow(id)), token: `${id}:${secret}` };
    },

    newBotToken(uid, { botId }) {
      const b = own(uid, botId);
      const secret = newSecret();
      db.run('UPDATE bots SET token_hash = ? WHERE user_id = ?', sha(secret), b.user_id);
      return { token: `${b.user_id}:${secret}` };
    },

    updateBot(uid, { botId, name, description, about, privacy }) {
      const b = own(uid, botId);
      if (typeof name === 'string' && name.trim()) db.run('UPDATE users SET name = ? WHERE id = ?', name.trim().slice(0, 64), b.user_id);
      if (typeof about === 'string') db.run('UPDATE users SET bio = ? WHERE id = ?', about.trim().slice(0, 160), b.user_id);
      if (typeof description === 'string') db.run('UPDATE bots SET description = ? WHERE user_id = ?', description.trim().slice(0, 512), b.user_id);
      if (typeof privacy === 'boolean') db.run('UPDATE bots SET privacy = ? WHERE user_id = ?', privacy ? 1 : 0, b.user_id);
      announce(b.user_id);
      return view(botRow(b.user_id));
    },

    deleteBot(uid, { botId }) {
      const b = own(uid, botId);
      const chats = db.all('SELECT chat_id FROM members WHERE user_id = ?', b.user_id).map(r => r.chat_id);
      db.tx(() => {
        db.run('DELETE FROM bot_updates WHERE bot_id = ?', b.user_id);
        db.run('DELETE FROM bot_files WHERE bot_id = ?', b.user_id);
        db.run('DELETE FROM bot_callbacks WHERE bot_id = ?', b.user_id);
        db.run('DELETE FROM bots WHERE user_id = ?', b.user_id);
        db.run('DELETE FROM sessions WHERE user_id = ?', b.user_id);
        db.run("UPDATE users SET name = 'Удалённый бот', bio = '', avatar = NULL, username = ? WHERE id = ?", 'deleted_' + b.user_id + '_' + crypto.randomBytes(3).toString('hex'), b.user_id);
        for (const c of chats) {
          db.run('DELETE FROM members WHERE chat_id = ? AND user_id = ?', c, b.user_id);
          db.run('UPDATE chats SET rotate_needed = 1 WHERE id = ?', c);
        }
      });
      for (const c of chats) pushChat(c, [b.user_id]);
      identities.delete(b.user_id);
      return true;
    },

    botCallback(uid, { chatId, id, data }) {
      const m = Number.isInteger(id) && db.one('SELECT * FROM messages WHERE id = ? AND chat_id = ?', id, chatId);
      if (!m || !memberIds(chatId).includes(uid) || !isBot(m.sender_id) || !memberIds(chatId).includes(m.sender_id)) fail('Кнопка недоступна');
      if (typeof data !== 'string' || Buffer.byteLength(data) > 64) fail('Неверная кнопка');
      const qid = crypto.randomBytes(12).toString('hex');
      db.run('INSERT INTO bot_callbacks (id, bot_id, user_id, chat_id, message_id, created_at) VALUES (?, ?, ?, ?, ?, ?)', qid, m.sender_id, uid, chatId, id, Date.now());
      const c = chatRow(chatId);
      enqueue(m.sender_id, { callback_query: { id: qid, from: apiUser(userById(uid)), chat_instance: String(chatId), data,
        message: { message_id: m.id, date: sec(m.created_at), chat: apiChat(c), from: apiUser(userById(m.sender_id)) } } });
      return true;
    },
  };
  setInterval(() => db.run('DELETE FROM bot_callbacks WHERE created_at < ?', Date.now() - 3600e3), 600e3).unref();

  return { handle, handlers, onMessage, isBot, botInfo: id => { const b = botRow(id); return b ? meta(b) : null; } };
}

module.exports = { createBots };
