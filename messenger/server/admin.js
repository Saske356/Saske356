'use strict';
// Lawful-access administration.
//
// The escrow key pair is generated in the administrator's browser. Its private half is stored here
// only sealed under a key derived from the admin passphrase, so the server alone still cannot read
// conversations. Clients wrap every chat key for the escrow public key as pseudo-member 0.
// Every opening of a conversation requires a stated legal basis and is written to an audit log.

const crypto = require('crypto');

const SESSION_IDLE = 2 * 3600e3;

function createAdmin({ db, fail, json, readJson, hashAuth, b64, checkSealed, messageViews, userById, publicUser, memberIds, throttle, port }) {
  const get = k => db.one('SELECT value FROM settings WHERE key = ?', k)?.value ?? null;
  const set = (k, v) => db.run('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', k, v);

  let setupToken = get('admin_auth') ? null : crypto.randomBytes(16).toString('hex');
  if (setupToken) {
    console.log('────────────────────────────────────────────────────────────');
    console.log(' Служебный доступ ещё не настроен. Откройте один раз:');
    console.log(` http://localhost:${port}/admin#setup=${setupToken}`);
    console.log(' (ссылка действует до перезапуска сервера)');
    console.log('────────────────────────────────────────────────────────────');
  }

  const ip = req => req.headers['x-forwarded-for']?.split(',')[0].trim() || req.socket.remoteAddress || '';
  function audit(req, action, { chatId = null, userId = null, reason = '' } = {}) {
    db.run('INSERT INTO admin_audit (at, action, chat_id, user_id, reason, ip) VALUES (?, ?, ?, ?, ?, ?)',
      Date.now(), action, chatId, userId, reason, ip(req));
  }
  function tokenOf(req) { const m = /^Bearer ([a-f0-9]{48})$/.exec(req.headers.authorization || ''); return m && m[1]; }
  function isAdmin(req) {
    const t = tokenOf(req);
    const s = t && db.one('SELECT * FROM admin_sessions WHERE token = ?', t);
    if (!s) return false;
    if (Date.now() - s.last_active > SESSION_IDLE) { db.run('DELETE FROM admin_sessions WHERE token = ?', t); return false; }
    db.run('UPDATE admin_sessions SET last_active = ? WHERE token = ?', Date.now(), t);
    return true;
  }
  function requireAdmin(req) { if (!isAdmin(req)) { const e = new Error('Нужен вход администратора'); e.status = 401; throw e; } }
  function newSession() {
    const t = crypto.randomBytes(24).toString('hex');
    db.run('INSERT INTO admin_sessions (token, created_at, last_active) VALUES (?, ?, ?)', t, Date.now(), Date.now());
    return t;
  }
  const verify = auth => {
    const a = JSON.parse(get('admin_auth') || 'null');
    return a && typeof auth === 'string' && /^[a-f0-9]{64}$/.test(auth) &&
      crypto.timingSafeEqual(Buffer.from(hashAuth(auth, a.salt), 'hex'), Buffer.from(a.hash, 'hex'));
  };
  const wrap = fn => async (req, res) => {
    try { await fn(req, res); }
    catch (e) { if (e.status === 401) return json(res, 401, { error: e.message }); throw e; }
  };

  const routes = {
    'GET /api/admin/status': async (req, res) => json(res, 200, { configured: !!get('admin_auth'), session: isAdmin(req) }),

    'POST /api/admin/setup': async (req, res) => {
      const b = await readJson(req);
      throttle(req, 'admin-setup');
      if (!setupToken || typeof b.token !== 'string' || b.token.length !== setupToken.length ||
          !crypto.timingSafeEqual(Buffer.from(b.token), Buffer.from(setupToken))) fail('Ссылка настройки недействительна — перезапустите сервер');
      if (typeof b.auth !== 'string' || !/^[a-f0-9]{64}$/.test(b.auth)) fail('Неверный запрос');
      b64(b.publicKey, 200, 'ключи');
      const sealed = checkSealed(b.sealedKey);
      const salt = crypto.randomBytes(16).toString('hex');
      db.tx(() => {
        set('admin_auth', JSON.stringify({ hash: hashAuth(b.auth, salt), salt }));
        set('escrow_public', b.publicKey);
        set('escrow_sealed', sealed);
        // Existing chats get a new key version that includes the escrow wrap the next time a member opens them.
        db.run('UPDATE chats SET rotate_needed = 1');
      });
      setupToken = null;
      audit(req, 'setup');
      json(res, 200, { token: newSession(), sealedKey: JSON.parse(sealed), publicKey: b.publicKey });
    },

    'POST /api/admin/login': async (req, res) => {
      const b = await readJson(req);
      throttle(req, 'admin-login');
      if (!verify(b.auth)) { audit(req, 'login_failed'); fail('Неверная фраза доступа'); }
      audit(req, 'login');
      json(res, 200, { token: newSession(), sealedKey: JSON.parse(get('escrow_sealed')), publicKey: get('escrow_public') });
    },

    'POST /api/admin/logout': async (req, res) => {
      const t = tokenOf(req); if (t) db.run('DELETE FROM admin_sessions WHERE token = ?', t);
      json(res, 200, { ok: true });
    },

    'POST /api/admin/users': wrap(async (req, res) => {
      requireAdmin(req);
      const b = await readJson(req);
      const q = typeof b.q === 'string' ? b.q.trim().replace(/^@/, '').slice(0, 64) : '';
      const like = '%' + q.replace(/[%_\\]/g, '\\$&') + '%';
      const rows = db.all(`SELECT u.*, (SELECT COUNT(*) FROM members m WHERE m.user_id = u.id) chats,
                                  (SELECT COUNT(*) FROM messages x WHERE x.sender_id = u.id AND x.kind = 'msg') sent
                           FROM users u WHERE (? = '' OR u.username LIKE ? ESCAPE '\\' OR u.name LIKE ? ESCAPE '\\')
                           ORDER BY u.last_seen DESC LIMIT 200`, q, like, like);
      json(res, 200, rows.map(u => ({ ...publicUser(u), createdAt: u.created_at, chats: u.chats, sent: u.sent })));
    }),

    'POST /api/admin/user': wrap(async (req, res) => {
      requireAdmin(req);
      const b = await readJson(req);
      const u = Number.isInteger(b.userId) && userById(b.userId);
      if (!u) fail('Пользователь не найден');
      const chats = db.all(`SELECT c.*, (SELECT COUNT(*) FROM messages x WHERE x.chat_id = c.id) total,
                                    (SELECT MAX(created_at) FROM messages x WHERE x.chat_id = c.id) last_at,
                                    (SELECT COUNT(*) FROM chat_keys k WHERE k.chat_id = c.id AND k.user_id = 0) escrow_versions
                             FROM chats c JOIN members m ON m.chat_id = c.id WHERE m.user_id = ? ORDER BY last_at DESC`, u.id);
      json(res, 200, {
        user: { ...publicUser(u), createdAt: u.created_at },
        chats: chats.map(c => ({
          id: c.id, type: c.type, title: c.title, total: c.total, lastAt: c.last_at, escrowVersions: c.escrow_versions, keyVersion: c.key_version,
          members: memberIds(c.id).map(id => { const m = userById(id); return { id, name: m.name, username: m.username }; }),
        })),
      });
    }),

    'POST /api/admin/chat': wrap(async (req, res) => {
      requireAdmin(req);
      const b = await readJson(req);
      const reason = typeof b.reason === 'string' ? b.reason.trim().slice(0, 300) : '';
      if (reason.length < 5) fail('Укажите основание доступа (например, номер и дата запроса)');
      const c = Number.isInteger(b.chatId) && db.one('SELECT * FROM chats WHERE id = ?', b.chatId);
      if (!c) fail('Беседа не найдена');
      const before = Number.isInteger(b.before) ? b.before : null;
      if (!before) audit(req, 'open_chat', { chatId: c.id, reason });
      const rows = before
        ? db.all('SELECT * FROM messages WHERE chat_id = ? AND id < ? ORDER BY id DESC LIMIT 201', c.id, before)
        : db.all('SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 201', c.id);
      const keys = db.all('SELECT version v, wrapper_id "from", iv, ct FROM chat_keys WHERE chat_id = ? AND user_id = 0 ORDER BY version', c.id);
      const userIds = new Set([...memberIds(c.id), ...keys.map(k => k.from), ...rows.map(r => r.sender_id)]);
      json(res, 200, {
        chat: { id: c.id, type: c.type, title: c.title, createdAt: c.created_at, ttl: c.ttl, members: memberIds(c.id), keyVersion: c.key_version },
        users: [...userIds].map(userById).filter(Boolean).map(publicUser),
        keys,
        messages: messageViews(rows.slice(0, 200).reverse()),
        hasMore: rows.length > 200,
      });
    }),

    'POST /api/admin/export-log': wrap(async (req, res) => {
      requireAdmin(req);
      const b = await readJson(req);
      if (!Number.isInteger(b.chatId)) fail('Неверный запрос');
      audit(req, 'export_chat', { chatId: b.chatId, reason: typeof b.reason === 'string' ? b.reason.slice(0, 300) : '' });
      json(res, 200, { ok: true });
    }),

    'POST /api/admin/audit': wrap(async (req, res) => {
      requireAdmin(req);
      json(res, 200, db.all('SELECT * FROM admin_audit ORDER BY id DESC LIMIT 500'));
    }),
  };

  return { routes, isAdmin, escrowPublic: () => get('escrow_public') };
}

module.exports = { createAdmin };
