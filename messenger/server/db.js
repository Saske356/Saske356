'use strict';
// SQLite storage. The server never sees message contents: only ciphertext and metadata.

const { DatabaseSync } = require('node:sqlite');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT NOT NULL,
  bio           TEXT NOT NULL DEFAULT '',
  color         TEXT NOT NULL,
  avatar        TEXT,
  auth_hash     TEXT NOT NULL,
  auth_salt     TEXT NOT NULL,
  public_key    TEXT NOT NULL,
  sealed_key    TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  last_seen     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  token         TEXT PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device        TEXT NOT NULL DEFAULT '',
  created_at    INTEGER NOT NULL,
  last_active   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  type          TEXT NOT NULL CHECK (type IN ('self','direct','group')),
  title         TEXT,
  owner_id      INTEGER,
  color         TEXT,
  ttl           INTEGER NOT NULL DEFAULT 0,
  key_version   INTEGER NOT NULL DEFAULT 1,
  rotate_needed INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
  chat_id       INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at     INTEGER NOT NULL,
  last_read     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (chat_id, user_id)
);
CREATE INDEX IF NOT EXISTS members_user ON members(user_id);
CREATE TABLE IF NOT EXISTS chat_keys (
  chat_id       INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  version       INTEGER NOT NULL,
  user_id       INTEGER NOT NULL,
  wrapper_id    INTEGER NOT NULL,
  iv            TEXT NOT NULL,
  ct            TEXT NOT NULL,
  PRIMARY KEY (chat_id, version, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id       INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  sender_id     INTEGER NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('msg','service','call')),
  kv            INTEGER,
  iv            TEXT,
  ct            TEXT,
  meta          TEXT NOT NULL DEFAULT '{}',
  reply_to      INTEGER,
  pinned        INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  edited_at     INTEGER,
  expires_at    INTEGER
);
CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id, id);
CREATE INDEX IF NOT EXISTS messages_exp ON messages(expires_at) WHERE expires_at IS NOT NULL;
CREATE TABLE IF NOT EXISTS reactions (
  message_id    INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL,
  emoji         TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (message_id, user_id, emoji)
);
CREATE TABLE IF NOT EXISTS votes (
  message_id    INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL,
  option        INTEGER NOT NULL,
  PRIMARY KEY (message_id, user_id, option)
);
CREATE TABLE IF NOT EXISTS settings (
  key           TEXT PRIMARY KEY,
  value         TEXT
);
CREATE TABLE IF NOT EXISTS admin_sessions (
  token         TEXT PRIMARY KEY,
  created_at    INTEGER NOT NULL,
  last_active   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  at            INTEGER NOT NULL,
  action        TEXT NOT NULL,
  chat_id       INTEGER,
  user_id       INTEGER,
  reason        TEXT NOT NULL DEFAULT '',
  ip            TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bots (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  owner_id       INTEGER NOT NULL,
  token_hash     TEXT NOT NULL,
  private_key    TEXT NOT NULL,
  description    TEXT NOT NULL DEFAULT '',
  commands       TEXT NOT NULL DEFAULT '[]',
  privacy        INTEGER NOT NULL DEFAULT 1,
  webhook_url    TEXT,
  webhook_secret TEXT,
  webhook_error  TEXT,
  created_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS bots_owner ON bots(owner_id);
CREATE TABLE IF NOT EXISTS bot_updates (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id        INTEGER NOT NULL,
  payload       TEXT NOT NULL,
  created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS bot_updates_bot ON bot_updates(bot_id, id);
CREATE TABLE IF NOT EXISTS bot_files (
  file_id       TEXT PRIMARY KEY,
  bot_id        INTEGER NOT NULL,
  blob_id       TEXT NOT NULL,
  key           TEXT NOT NULL,
  iv            TEXT NOT NULL,
  name          TEXT NOT NULL,
  type          TEXT NOT NULL,
  size          INTEGER NOT NULL,
  created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bot_callbacks (
  id            TEXT PRIMARY KEY,
  bot_id        INTEGER NOT NULL,
  user_id       INTEGER NOT NULL,
  chat_id       INTEGER NOT NULL,
  message_id    INTEGER NOT NULL,
  created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS blobs (
  id            TEXT PRIMARY KEY,
  owner_id      INTEGER NOT NULL,
  size          INTEGER NOT NULL,
  created_at    INTEGER NOT NULL
);
`;

function open(file) {
  const db = new DatabaseSync(file);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA synchronous = NORMAL;');
  db.exec(SCHEMA);

  const cache = new Map();
  const st = sql => {
    let s = cache.get(sql);
    if (!s) { s = db.prepare(sql); cache.set(sql, s); }
    return s;
  };
  const one = (sql, ...a) => st(sql).get(...a);
  const all = (sql, ...a) => st(sql).all(...a);
  const run = (sql, ...a) => st(sql).run(...a);
  let depth = 0;
  const tx = fn => {
    if (depth) return fn();
    depth++;
    db.exec('BEGIN IMMEDIATE');
    try { const r = fn(); db.exec('COMMIT'); return r; }
    catch (e) { db.exec('ROLLBACK'); throw e; }
    finally { depth--; }
  };
  return { raw: db, one, all, run, tx };
}

module.exports = { open };
