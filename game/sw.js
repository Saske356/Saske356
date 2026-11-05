/* Свет Бездны — офлайн-кэш. Стратегия: сначала кэш (мгновенный запуск без сети),
   в фоне — тихое обновление файла из сети, чтобы новая версия пришла при следующем запуске.
   При изменении списка файлов или крупном обновлении — поднять VERSION. */
const VERSION = 'svet-bezdny-v4';
const CORE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/maskable-192.png',
  './icons/maskable-512.png',
  './icons/apple-touch-icon.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('svet-bezdny-') && k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  e.respondWith(caches.open(VERSION).then(async cache => {
    const hit = await cache.match(req, {ignoreSearch: true}) ||
      (req.mode === 'navigate' ? await cache.match('./index.html') : undefined);
    const net = fetch(req).then(res => {
      if (res && res.ok && res.type === 'basic') cache.put(req, res.clone());
      return res;
    }).catch(() => undefined);
    if (hit) { e.waitUntil(net); return hit; }
    const res = await net;
    return res || new Response('', {status: 504, statusText: 'offline'});
  }));
});
