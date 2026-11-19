// Офлайн-режим: игровая логика (shared/core.js) работает прямо в игре, без сервера.
// Возвращает объект с интерфейсом WebSocket, поэтому остальной код не знает разницы.
// Прогресс (деньги, машины, права) хранится в localStorage устройства.
import { createGame } from '/shared/core.js';

const KEY = 'nrp-offline-db';

export function offlineSocket() {
  let db = {};
  try { db = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch { db = {}; }
  let timer = null;
  const save = () => {
    timer = null;
    try { game.storePositions(); localStorage.setItem(KEY, JSON.stringify(db)); } catch {}
  };
  const saveSoon = () => { if (!timer) timer = setTimeout(save, 2000); };
  const game = createGame({
    db, saveSoon, maxPlayers: 1, ownerAll: true, // офлайн-сервер: вы главный админ
    auth: { create: () => ({ salt: '', hash: '' }), verify: () => true }, // пароль офлайн не нужен
  });

  const sock = {
    readyState: 0, onopen: null, onmessage: null, onclose: null,
    send(text) { if (sock.readyState === 1) queueMicrotask(() => conn.message(text)); },
    close() {
      if (sock.readyState > 1) return;
      sock.readyState = 3;
      conn.close(); save(); game.stop();
    },
  };
  const conn = game.connect({
    send: (s) => queueMicrotask(() => sock.onmessage?.({ data: s })),
    isOpen: () => sock.readyState === 1,
  });
  setTimeout(() => { sock.readyState = 1; sock.onopen?.(); }, 0);
  addEventListener('pagehide', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });
  return sock;
}
