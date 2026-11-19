// Новоград RP — игровой сервер: раздаёт клиент и ведёт мультиплеер по WebSocket.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';
import { createGame } from './shared/core.js';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = process.env.DATA_DIR || path.join(ROOT, 'data');
const DB_FILE = path.join(DATA_DIR, 'players.json');
const NEWS_FILE = path.join(ROOT, 'news.json');
const SERVER_NAME = process.env.SERVER_NAME || 'Новоград #1';
const MAX_PLAYERS = Number(process.env.MAX_PLAYERS) || 100;
const SERVER_COLOR = /^#[0-9a-f]{6}$/i.test(process.env.SERVER_COLOR || '') ? process.env.SERVER_COLOR : '#ff8a3d';
const VERSION = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8')).version;

// ---------- Статика и игровой кэш ----------
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
  '.json': 'application/json', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.bin': 'application/octet-stream',
  '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg', '.wasm': 'application/wasm',
};
const THREE_DIR = path.join(ROOT, 'node_modules', 'three', 'build');
const MOUNTS = [
  ['/shared/', path.join(ROOT, 'shared')],
  ['/vendor/', THREE_DIR],
  ['/cache/', path.join(ROOT, 'cache')],   // модели, текстуры, звуки — кладите сюда
  ['/', path.join(ROOT, 'public')],
];
// Что входит в игровой кэш, который скачивает лаунчер.
const CACHE_SOURCES = [
  ['/', path.join(ROOT, 'public')],
  ['/shared/', path.join(ROOT, 'shared')],
  ['/cache/', path.join(ROOT, 'cache')],
];
const CACHE_EXTRA = [['/vendor/three.module.js', path.join(THREE_DIR, 'three.module.js')]];

function walk(dir, prefix, out) {
  let list = [];
  try { list = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const e of list) {
    if (e.name.startsWith('.')) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walk(full, prefix + e.name + '/', out);
    else if (e.isFile()) out.push([prefix + e.name, full]);
  }
}
const hashCache = new Map(); // файл → { mtime, size, sha }
function fileSha(full) {
  const st = fs.statSync(full), c = hashCache.get(full);
  if (c && c.mtime === st.mtimeMs && c.size === st.size) return c;
  const sha = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex');
  const v = { mtime: st.mtimeMs, size: st.size, sha };
  hashCache.set(full, v);
  return v;
}
// Манифест — текст: первая строка «version X», дальше «sha256 размер путь».
let manifestMemo = { t: 0, text: '' };
function manifest() {
  if (Date.now() - manifestMemo.t < 5000) return manifestMemo.text;
  const files = [];
  for (const [prefix, dir] of CACHE_SOURCES) walk(dir, prefix, files);
  files.push(...CACHE_EXTRA);
  files.sort((a, b) => a[0].localeCompare(b[0]));
  const lines = [`version ${VERSION}`];
  for (const [p, full] of files) {
    if (/\s/.test(p)) continue; // пробелы в именах файлов не поддерживаем
    const { sha, size } = fileSha(full);
    lines.push(`${sha} ${size} ${p}`);
  }
  manifestMemo = { t: Date.now(), text: lines.join('\n') + '\n' };
  return manifestMemo.text;
}

function sendFile(req, res, file) {
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end('Not found'); }
    const headers = {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-cache', 'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*',
    };
    // Range — чтобы лаунчер мог докачивать файл после обрыва связи.
    const m = /^bytes=(\d+)-$/.exec(req.headers.range || '');
    if (m && Number(m[1]) < st.size) {
      const from = Number(m[1]);
      res.writeHead(206, { ...headers, 'Content-Length': st.size - from, 'Content-Range': `bytes ${from}-${st.size - 1}/${st.size}` });
      return fs.createReadStream(file, { start: from }).pipe(res);
    }
    res.writeHead(200, { ...headers, 'Content-Length': st.size });
    fs.createReadStream(file).pipe(res);
  });
}

const server = http.createServer((req, res) => {
  let url;
  try { url = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch { res.writeHead(400); return res.end(); }
  if (url === '/api/status') {
    let news = [];
    try { news = JSON.parse(fs.readFileSync(NEWS_FILE, 'utf8')); } catch {}
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache' });
    return res.end(JSON.stringify({ name: SERVER_NAME, color: SERVER_COLOR, online: players.size, max: MAX_PLAYERS, version: VERSION, news }));
  }
  if (url === '/api/manifest') {
    let text;
    try { text = manifest(); } catch (e) { console.error('Манифест', e); res.writeHead(500); return res.end(); }
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache' });
    return res.end(text);
  }
  if (url === '/') url = '/index.html';
  for (const [prefix, dir] of MOUNTS) {
    if (!url.startsWith(prefix)) continue;
    const file = path.join(dir, url.slice(prefix.length));
    if (!file.startsWith(dir + path.sep)) break;
    return sendFile(req, res, file);
  }
  res.writeHead(404); res.end('Not found');
});

// ---------- База игроков ----------
let db = {};
try { db = JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); } catch { db = {}; }
let saveTimer = null;
function saveSoon() { if (!saveTimer) saveTimer = setTimeout(saveNow, 2000); }
function saveNow() {
  clearTimeout(saveTimer); saveTimer = null;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(DB_FILE + '.tmp', JSON.stringify(db));
  fs.renameSync(DB_FILE + '.tmp', DB_FILE);
}
const hashPass = (pass, salt) => crypto.scryptSync(pass, salt, 32).toString('hex');

// ---------- Игра ----------
const game = createGame({
  db, saveSoon, maxPlayers: MAX_PLAYERS, log: console.log,
  auth: {
    create(pass) { const salt = crypto.randomBytes(16).toString('hex'); return { salt, hash: hashPass(pass, salt) }; },
    verify(pass, prof) {
      const a = Buffer.from(hashPass(pass, prof.salt), 'hex'), b = Buffer.from(prof.hash, 'hex');
      return a.length === b.length && crypto.timingSafeEqual(a, b);
    },
  },
});
const players = game.players;

// ---------- Сеть ----------
const wss = new WebSocketServer({ server, path: '/ws', maxPayload: 8192 });
wss.on('connection', (ws) => {
  const c = game.connect({ send: (s) => ws.send(s), isOpen: () => ws.readyState === 1 });
  ws.on('message', (raw) => c.message(raw.toString()));
  ws.on('close', () => c.close());
  ws.on('error', () => {});
});

function shutdown() {
  game.storePositions();
  saveNow();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

server.listen(PORT, () => console.log(`Новоград RP запущен: http://localhost:${PORT}`));
