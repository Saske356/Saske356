// WebSocket RPC + HTTP helpers. Incoming events are processed strictly in order (decryption is async).
import { S } from './state.js';

let ws = null, seq = 0, retry = 0, onEvent = null, onStatus = null, queue = Promise.resolve(), closedByUs = false;
const pending = new Map();

export function setHandlers(eventFn, statusFn) { onEvent = eventFn; onStatus = statusFn; }

export function connect() {
  closedByUs = false;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const sock = new WebSocket(`${proto}://${location.host}/ws?token=${S.token}`);
  ws = sock;
  sock.onopen = () => { retry = 0; onStatus?.('online'); };
  sock.onmessage = e => {
    let evt; try { evt = JSON.parse(e.data); } catch { return; }
    if (evt.type === 'reply') {
      const p = pending.get(evt.reqId); if (!p) return;
      pending.delete(evt.reqId); clearTimeout(p.timer);
      return evt.ok ? p.resolve(evt.data) : p.reject(new Error(evt.error));
    }
    queue = queue.then(() => onEvent?.(evt)).catch(err => console.error('event', evt.type, err));
  };
  sock.onclose = e => {
    if (ws !== sock) return;
    for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('Нет связи с сервером')); }
    pending.clear();
    ws = null;
    if (e.code === 4001) return onStatus?.('unauthorized');
    if (closedByUs) return;
    onStatus?.('offline');
    setTimeout(connect, Math.min(800 * 2 ** retry++, 12000));
  };
}
export function disconnect() { closedByUs = true; if (ws) { const w = ws; ws = null; w.close(); } }
export const connected = () => ws && ws.readyState === 1;

export function rpc(type, data = {}, timeout = 20000) {
  return new Promise((resolve, reject) => {
    if (!connected()) return reject(new Error('Нет связи с сервером'));
    const reqId = ++seq;
    const timer = setTimeout(() => { if (pending.delete(reqId)) reject(new Error('Сервер не ответил')); }, timeout);
    pending.set(reqId, { resolve, reject, timer });
    ws.send(JSON.stringify({ ...data, type, reqId }));
  });
}

export async function api(path, body, { method = 'POST', raw, headers = {} } = {}) {
  const h = { ...headers };
  if (S.token) h.Authorization = 'Bearer ' + S.token;
  if (!raw && body !== undefined) h['Content-Type'] = 'application/json';
  const res = await fetch(path, { method, headers: h, body: raw ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Ошибка сервера');
  return data;
}

export async function uploadBlob(data, onProgress) {
  // XHR for upload progress.
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', '/api/blob');
    x.setRequestHeader('Authorization', 'Bearer ' + S.token);
    x.setRequestHeader('Content-Type', 'application/octet-stream');
    x.upload.onprogress = e => e.lengthComputable && onProgress?.(e.loaded / e.total);
    x.onload = () => {
      let d = {}; try { d = JSON.parse(x.responseText); } catch {}
      x.status === 200 ? resolve(d.id) : reject(new Error(d.error || 'Не удалось загрузить файл'));
    };
    x.onerror = () => reject(new Error('Не удалось загрузить файл'));
    x.send(data);
  });
}

export async function downloadBlob(id) {
  const res = await fetch('/blob/' + id, { headers: { Authorization: 'Bearer ' + S.token } });
  if (!res.ok) throw new Error('Файл недоступен');
  return res.arrayBuffer();
}
