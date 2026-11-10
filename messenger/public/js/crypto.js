// End-to-end encryption for Орбита. Everything here runs in the browser; the server only stores ciphertext.
//
// • Password → PBKDF2 → two independent secrets: `auth` (sent to the server to log in) and `encKey`
//   (never leaves the device; seals the identity private key so it can be restored on another device).
// • Identity: ECDH P-256 key pair per user. Pairwise key = HKDF(ECDH(my, their)).
// • Every chat has a random AES-256 key (versioned). It is wrapped for each member with the pairwise key
//   between the member who created that version and the recipient. Versions rotate when members change.
// • Every message is AES-GCM encrypted with the chat key; every file with its own random key.

const subtle = crypto.subtle;
const te = new TextEncoder();
const td = new TextDecoder();
const ITERATIONS = 250_000;

export function b64(buf) {
  const a = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000));
  return btoa(s);
}
export function unb64(s) {
  const bin = atob(s);
  const a = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return a;
}
const hex = a => Array.from(a, x => x.toString(16).padStart(2, '0')).join('');
const random = n => crypto.getRandomValues(new Uint8Array(n));
const aesKey = (raw, extractable = false) => subtle.importKey('raw', raw, 'AES-GCM', extractable, ['encrypt', 'decrypt']);
const gcm = (iv, aad) => (aad ? { name: 'AES-GCM', iv, additionalData: te.encode(aad) } : { name: 'AES-GCM', iv });

async function pbkdf2(password, salt) {
  const base = await subtle.importKey('raw', te.encode(password.normalize('NFKC')), 'PBKDF2', false, ['deriveBits']);
  return new Uint8Array(await subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: te.encode(salt), iterations: ITERATIONS }, base, 256));
}

export async function credentials(username, password) {
  const u = username.trim().toLowerCase();
  const [auth, enc] = await Promise.all([pbkdf2(password, 'orbita/auth/v1/' + u), pbkdf2(password, 'orbita/seal/v1/' + u)]);
  return { auth: hex(auth), encKey: await aesKey(enc) };
}

export async function seal(key, data, aad) {
  const iv = random(12);
  const ct = await subtle.encrypt(gcm(iv, aad), key, data);
  return { iv: b64(iv), ct: b64(ct) };
}
export async function unseal(key, { iv, ct }, aad) {
  return subtle.decrypt(gcm(unb64(iv), aad), key, unb64(ct));
}

// ---------- identity ----------
const ECDH = { name: 'ECDH', namedCurve: 'P-256' };
const importPrivate = pkcs8 => subtle.importKey('pkcs8', pkcs8, ECDH, false, ['deriveBits']);

export async function newIdentity(encKey) {
  const kp = await subtle.generateKey(ECDH, true, ['deriveBits']);
  const publicKey = b64(await subtle.exportKey('spki', kp.publicKey));
  const pkcs8 = await subtle.exportKey('pkcs8', kp.privateKey);
  const sealedKey = await seal(encKey, pkcs8, 'identity');
  return { publicKey, sealedKey, privateKey: await importPrivate(pkcs8) };
}
export async function openIdentity(encKey, sealedKey) {
  return importPrivate(await unseal(encKey, sealedKey, 'identity'));
}
export async function resealIdentity(oldEnc, newEnc, sealedKey) {
  return seal(newEnc, await unseal(oldEnc, sealedKey, 'identity'), 'identity');
}

// ---------- pairwise keys ----------
const pubCache = new Map();
const pairCache = new Map();
async function importPublic(b) {
  if (!pubCache.has(b)) pubCache.set(b, subtle.importKey('spki', unb64(b), ECDH, false, []));
  return pubCache.get(b);
}
export function pairKey(me, other) {
  // me: { id, privateKey }, other: { id, publicKey }
  const k = `${me.id}|${other.id}|${other.publicKey}`;
  if (!pairCache.has(k)) {
    pairCache.set(k, (async () => {
      const bits = await subtle.deriveBits({ name: 'ECDH', public: await importPublic(other.publicKey) }, me.privateKey, 256);
      const hk = await subtle.importKey('raw', bits, 'HKDF', false, ['deriveKey']);
      const [a, b] = [me.id, other.id].sort((x, y) => x - y);
      return subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: te.encode('orbita/pair/v1'), info: te.encode(`${a}:${b}`) },
        hk, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
    })());
    pairCache.get(k).catch(() => pairCache.delete(k));
  }
  return pairCache.get(k);
}
export function forgetKeys() { pairCache.clear(); }

// ---------- chat keys ----------
// Returns { raw, key, bundle } where bundle = { [userId]: { iv, ct } } ready for the server.
export async function newChatKey(me, members, version) {
  const raw = random(32);
  const bundle = {};
  for (const m of members) {
    bundle[m.id] = await seal(await pairKey(me, m), raw, `chatkey/v${version}/to/${m.id}`);
  }
  return { key: await aesKey(raw), bundle };
}
export async function openChatKey(me, wrapper, version, wrapped) {
  const raw = await unseal(await pairKey(me, wrapper), wrapped, `chatkey/v${version}/to/${me.id}`);
  return aesKey(raw);
}

// ---------- payloads ----------
export async function encryptJson(key, obj, aad) {
  return seal(key, te.encode(JSON.stringify(obj)), aad);
}
export async function decryptJson(key, box, aad) {
  return JSON.parse(td.decode(await unseal(key, box, aad)));
}

// ---------- files ----------
export async function encryptFile(buf) {
  const raw = random(32);
  const iv = random(12);
  const data = await subtle.encrypt({ name: 'AES-GCM', iv }, await aesKey(raw), buf);
  return { data, key: b64(raw), iv: b64(iv) };
}
export async function decryptFile(buf, key, iv) {
  return subtle.decrypt({ name: 'AES-GCM', iv: unb64(iv) }, await aesKey(unb64(key)), buf);
}

// ---------- verification ----------
const EMOJI = ['🦊', '🐙', '🦉', '🐳', '🦋', '🌵', '🍄', '🌙', '⭐', '🔥', '🌊', '🍋', '🍒', '🥝', '🎈', '🎲',
  '🎧', '🚲', '⛵', '🚀', '🪐', '🗝️', '⚓', '🧭', '🔔', '🎁', '📚', '🖋️', '🧩', '🪁', '🛸', '🏔️',
  '🌻', '🌈', '❄️', '☂️', '🍩', '🧁', '🫖', '🥨', '🐝', '🦔', '🐢', '🦜', '🐧', '🦒', '🐌', '🦀',
  '🎻', '🥁', '🎺', '🪕', '🏹', '🛶', '🗿', '🏮', '🧲', '🔭', '💎', '🪴', '🍀', '🌋', '🦄', '🐉'];

async function stretch(text) {
  let h = te.encode(text);
  for (let i = 0; i < 400; i++) h = new Uint8Array(await subtle.digest('SHA-512', h));
  return h;
}
function render(h) {
  const groups = [];
  for (let i = 0; i < 12; i++) {
    let n = 0;
    for (let j = 0; j < 5; j++) n = n * 256 + h[i * 5 + j];
    groups.push(String(n % 100000).padStart(5, '0'));
  }
  const emoji = Array.from(h.slice(0, 6), b => EMOJI[b % 64]);
  return { groups, emoji };
}
// Same code on both sides — compare it in person or over a call to rule out a man-in-the-middle.
export async function safetyCode(a, b) {
  const [x, y] = [a, b].sort((p, q) => p.id - q.id);
  return render(await stretch(`orbita/safety/v1|${x.id}:${x.publicKey}|${y.id}:${y.publicKey}`));
}
export async function fingerprint(user) {
  return render(await stretch(`orbita/fp/v1|${user.id}:${user.publicKey}`));
}

// ---------- device key store (IndexedDB keeps non-extractable CryptoKeys) ----------
function idb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open('orbita', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('kv');
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function idbDo(mode, fn) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('kv', mode);
    const req = fn(tx.objectStore('kv'));
    tx.oncomplete = () => { db.close(); resolve(req && req.result); };
    tx.onerror = () => { db.close(); reject(tx.error); };
  });
}
export const keystore = {
  get: () => idbDo('readonly', s => s.get('identity')).catch(() => null),
  set: v => idbDo('readwrite', s => s.put(v, 'identity')),
  clear: () => idbDo('readwrite', s => s.delete('identity')).catch(() => {}),
};
