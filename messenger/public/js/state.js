// App state + everything that needs both state and crypto (chat keys, message encryption).
import * as C from './crypto.js';
import { rpc } from './net.js';

export const S = {
  token: localStorage.getItem('orbita.token'),
  identity: null,           // { id, privateKey, publicKey }
  me: null,
  users: {},                // id -> public user
  chats: {},                // id -> chat view
  msgs: {},                 // chatId -> [message]
  hasMore: {},
  loaded: {},
  unreadMark: {},           // chatId -> last_read at the moment the chat was opened
  current: null,
  typing: {},               // chatId -> { userId: { kind, timer } }
  reply: null, edit: null,
  tab: 'chats', filter: 'all', query: '',
  config: { iceServers: [], reactions: [], ttl: [] },
  callLog: null,
  details: false,
};

// ---------- chat keys ----------
const keyCache = new Map(); // `${chatId}:${v}` -> Promise<CryptoKey>
export function forgetAll() { keyCache.clear(); C.forgetKeys(); }

export function chatKey(chat, v) {
  const k = `${chat.id}:${v}`;
  if (!keyCache.has(k)) {
    const entry = chat.keys.find(x => x.v === v);
    if (!entry) return Promise.reject(new Error('no key'));
    const p = (async () => {
      // The member who wrapped this version may have left since — fetch their public key.
      const wrapper = S.users[entry.from]?.publicKey ? S.users[entry.from] : (S.users[entry.from] = await rpc('getUser', { userId: entry.from }));
      return C.openChatKey(S.identity, wrapper, v, entry);
    })();
    p.catch(() => keyCache.delete(k));
    keyCache.set(k, p);
  }
  return keyCache.get(k);
}

async function membersWithKeys(ids) {
  const out = [];
  for (const id of ids) {
    let u = S.users[id];
    if (!u || !u.publicKey) { u = await rpc('getUser', { userId: id }); S.users[id] = u; }
    out.push(u);
  }
  return out;
}

// Creates a fresh key version for the chat, wrapped for `memberIds` (defaults to the current members).
export async function makeKeyBundle(version, memberIds) {
  const members = await membersWithKeys(memberIds);
  // Lawful-access escrow: the chat key is also wrapped for the service's escrow key (pseudo-member 0).
  // Its private half exists only sealed under the administrator's passphrase. Users are told about this.
  if (S.config.escrow) members.push({ id: 0, publicKey: S.config.escrow });
  const { key, bundle } = await C.newChatKey(S.identity, members, version);
  return { key, bundle };
}
function remember(chatId, v, key) { keyCache.set(`${chatId}:${v}`, Promise.resolve(key)); }

let rotating = new Map();
export async function ensureKey(chat) {
  if (!chat.rotateNeeded && chat.keyVersion > 0) return;
  if (rotating.has(chat.id)) return rotating.get(chat.id);
  const p = (async () => {
    const v = chat.keyVersion + 1;
    const { key, bundle } = await makeKeyBundle(v, chat.members);
    try {
      await rpc('rotateKey', { chatId: chat.id, version: v, keys: bundle });
      remember(chat.id, v, key);
      chat.keyVersion = v; chat.rotateNeeded = false;
      chat.keys = [...chat.keys.filter(k => k.v !== v), { v, from: S.me.id, iv: bundle[S.me.id].iv, ct: bundle[S.me.id].ct }];
    } catch (e) {
      // Somebody else rotated first — their `chat` event will bring the new key.
      await new Promise(r => setTimeout(r, 400));
    }
  })().finally(() => rotating.delete(chat.id));
  rotating.set(chat.id, p);
  return p;
}

export async function addMembersEncrypted(chat, newIds) {
  const v = chat.keyVersion + 1;
  const { key, bundle } = await makeKeyBundle(v, [...chat.members, ...newIds]);
  await rpc('addMembers', { chatId: chat.id, memberIds: newIds, version: v, keys: bundle });
  remember(chat.id, v, key);
}

export async function createDirect(userId) {
  let r = await rpc('openDirect', { userId });
  if (r.needKeys) {
    const { key, bundle } = await makeKeyBundle(1, [S.me.id, userId]);
    r = await rpc('openDirect', { userId, keys: bundle });
    remember(r.chatId, 1, key);
  }
  return r.chatId;
}
export async function createGroup(title, memberIds) {
  const { key, bundle } = await makeKeyBundle(1, [S.me.id, ...memberIds]);
  const r = await rpc('createGroup', { title, memberIds, keys: bundle });
  remember(r.chatId, 1, key);
  return r.chatId;
}

// ---------- messages ----------
export async function encryptPayload(chat, payload) {
  await ensureKey(chat);
  const kv = chat.keyVersion;
  const key = await chatKey(chat, kv);
  const box = await C.encryptJson(key, payload, `msg:${chat.id}`);
  return { kv, ...box };
}

export async function decrypt(m) {
  if (!m || m.kind !== 'msg' || m.p || m.err) return m;
  const chat = S.chats[m.chatId];
  if (!chat) return m;
  try {
    const key = await chatKey(chat, m.kv);
    m.p = await C.decryptJson(key, m, `msg:${m.chatId}`);
  } catch {
    m.err = true;
  }
  return m;
}
export const decryptAll = list => Promise.all(list.filter(Boolean).map(decrypt));

// ---------- helpers ----------
export const peerId = c => c.members.find(m => m !== S.me.id) ?? S.me.id;
export function chatTitle(c) {
  if (!c) return '';
  if (c.type === 'self') return 'Заметки';
  if (c.type === 'group') return c.title;
  return S.users[peerId(c)]?.name || 'Собеседник';
}
export const userName = id => (id === S.me?.id ? 'Вы' : S.users[id]?.name || 'Кто-то');
export function totalUnread() { return Object.values(S.chats).reduce((s, c) => s + (c.unread || 0), 0); }
