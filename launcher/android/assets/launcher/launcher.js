// Лаунчер Новоград RP. В приложении работает через мост window.NovogradApp,
// в обычном браузере открывает игру в этой же вкладке (удобно для проверки).
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const app = window.NovogradApp || null;
  const CFG = window.LAUNCHER_CONFIG || { servers: [] };
  const NICK_RE = /^[A-Z][a-z]{1,15}_[A-Z][a-z]{1,15}$/;

  const store = {
    get(k, d) { try { const v = localStorage.getItem('nl-' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('nl-' + k, JSON.stringify(v)); } catch {} },
  };

  const settings = Object.assign({ quality: 'mid', remember: true }, store.get('settings', {}));
  let custom = store.get('servers', []);
  let selected = store.get('selected', null);
  const status = {}; // url → { ok, online, max, name, ping, news }

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function normalize(addr) {
    let a = String(addr || '').trim();
    if (!a) return null;
    if (!/^https?:\/\//i.test(a)) a = 'http://' + a;
    try {
      const u = new URL(a);
      if (!/^https?:$/.test(u.protocol) || !u.hostname) return null;
      return u.origin;
    } catch { return null; }
  }

  function allServers() {
    const list = [];
    const seen = new Set();
    for (const s of CFG.servers || []) {
      const url = normalize(s.url);
      if (url && !seen.has(url)) { seen.add(url); list.push({ url, name: s.name, builtin: true }); }
    }
    for (const s of custom) if (!seen.has(s.url)) { seen.add(s.url); list.push(s); }
    return list;
  }

  async function probe(url) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 4000);
    const t0 = performance.now();
    try {
      const r = await fetch(url + '/api/status', { signal: ctl.signal, cache: 'no-store' });
      const j = await r.json();
      status[url] = { ok: true, ping: Math.round(performance.now() - t0), online: j.online | 0, max: j.max | 0, name: j.name, news: Array.isArray(j.news) ? j.news : [], version: j.version, color: j.color };
    } catch {
      status[url] = { ok: false };
    } finally {
      clearTimeout(timer);
    }
  }

  async function refresh() {
    const list = allServers();
    for (const s of list) if (!status[s.url]) status[s.url] = { pending: true };
    render();
    await Promise.all(list.map((s) => probe(s.url).then(render)));
  }

  function render() {
    const list = allServers();
    if (!list.some((s) => s.url === selected)) selected = list[0]?.url || null;
    const box = $('servers');
    box.replaceChildren();
    if (!list.length) {
      const e = el('div', 'empty', 'Серверов пока нет. Нажмите «＋» и введите адрес, например 203.0.113.10:3000');
      e.addEventListener('click', addServer);
      box.append(e);
    }
    for (const s of list) {
      const st = status[s.url] || {};
      const b = el('button', 'srv' + (s.url === selected ? ' on' : ''));
      if (st.ok && /^#[0-9a-f]{6}$/i.test(st.color || '')) b.style.setProperty('--srv', st.color);
      b.type = 'button';
      b.append(el('span', 'dot' + (st.ok ? ' ok' : st.pending ? '' : ' bad')));
      const info = el('div', 'info');
      info.append(el('div', 'name', st.name || s.name || 'Сервер'), el('div', 'addr', s.url.replace(/^https?:\/\//, '')));
      const stat = el('div', 'stat');
      if (st.ok) {
        const on = el('b', null, `${st.online} / ${st.max}`);
        const bar = el('div', 'bar'); const fill = el('i');
        fill.style.width = Math.min(100, (st.online / Math.max(1, st.max)) * 100) + '%';
        bar.append(fill);
        stat.append(on, el('span', null, `пинг ${st.ping} мс`), bar);
      } else stat.append(el('span', null, st.pending ? 'проверка…' : 'недоступен'));
      b.append(info, stat);
      if (!s.builtin) {
        const del = el('button', 'del', '✕');
        del.type = 'button';
        del.addEventListener('click', (e) => { e.stopPropagation(); removeServer(s.url); });
        b.append(del);
      }
      b.addEventListener('click', () => { selected = s.url; store.set('selected', selected); render(); });
      box.append(b);
    }
    renderNews();
  }

  function renderNews() {
    const st = status[selected];
    const news = st?.ok && st.news.length ? st.news : [{
      title: 'Добро пожаловать!',
      text: 'Выберите сервер, введите ник в формате Имя_Фамилия и пароль. Новый персонаж создаётся автоматически при первом входе.',
    }];
    $('news').replaceChildren(...news.slice(0, 20).map((n) => {
      const c = el('div', 'card');
      if (n.date) c.append(el('div', 'date', new Date(n.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })));
      c.append(el('b', null, n.title || ''), el('p', null, n.text || ''));
      return c;
    }));
  }

  // ---------- Диалоги ----------
  let onDlgBack = null;
  function dialog(title, body, actions) {
    $('dlgtitle').textContent = title;
    $('dlgbody').replaceChildren(...body);
    $('dlgactions').replaceChildren(...actions.map(([text, fn, primary]) => {
      const b = el('button', 'btn' + (primary ? ' primary' : ''), text);
      b.type = 'button';
      b.addEventListener('click', () => { if (fn() !== false) closeDialog(); });
      return b;
    }));
    $('dlg').hidden = false;
    onDlgBack = closeDialog;
  }
  function closeDialog() { $('dlg').hidden = true; onDlgBack = null; }
  $('dlg').addEventListener('click', (e) => { if (e.target.id === 'dlg') closeDialog(); });

  function addServer() {
    const name = el('input'); name.placeholder = 'Мой сервер'; name.maxLength = 40;
    const addr = el('input'); addr.placeholder = '203.0.113.10:3000'; addr.autocapitalize = 'off'; addr.spellcheck = false;
    const err = el('p'); err.style.color = '#ffb4a8';
    const l1 = el('label', null, 'Адрес (IP или домен с портом)'); l1.append(addr);
    const l2 = el('label', null, 'Название (необязательно)'); l2.append(name);
    dialog('Добавить сервер', [l1, l2, err], [
      ['Отмена', () => {}],
      ['Добавить', () => {
        const url = normalize(addr.value);
        if (!url) { err.textContent = 'Неверный адрес'; return false; }
        if (allServers().some((s) => s.url === url)) { err.textContent = 'Такой сервер уже есть'; return false; }
        custom.push({ url, name: name.value.trim() || null });
        store.set('servers', custom);
        selected = url; store.set('selected', url);
        refresh();
      }, true],
    ]);
    setTimeout(() => addr.focus(), 50);
  }
  function removeServer(url) {
    dialog('Удалить сервер?', [el('p', null, url)], [
      ['Отмена', () => {}],
      ['Удалить', () => { custom = custom.filter((s) => s.url !== url); store.set('servers', custom); render(); }, true],
    ]);
  }
  function openSettings() {
    const seg = el('div', 'seg');
    const names = { low: 'Низкая', mid: 'Средняя', high: 'Высокая' };
    for (const q of ['low', 'mid', 'high']) {
      const b = el('button', settings.quality === q ? 'on' : '', names[q]);
      b.type = 'button';
      b.addEventListener('click', () => { settings.quality = q; [...seg.children].forEach((c) => c.classList.toggle('on', c === b)); });
      seg.append(b);
    }
    const ql = el('label', null, 'Графика'); ql.append(seg);
    const rem = el('label', 'check');
    const cb = el('input'); cb.type = 'checkbox'; cb.checked = settings.remember;
    rem.append(cb, document.createTextNode('Запоминать пароль'));
    const verify = el('button', 'btn', 'Перекачать файлы игры');
    verify.type = 'button';
    verify.hidden = !app || !selected;
    verify.addEventListener('click', () => { app.clearCache(selected); verify.textContent = 'Файлы удалены — скачаются при входе'; verify.disabled = true; });
    dialog('Настройки', [ql, el('p', null, 'Низкая — без теней и с меньшим трафиком, для слабых телефонов.'), rem, verify], [
      ['Готово', () => {
        settings.remember = cb.checked;
        store.set('settings', settings);
        if (!settings.remember) store.set('pass', '');
      }, true],
    ]);
  }

  // ---------- Игра ----------
  $('nick').value = store.get('nick', '');
  $('pass').value = settings.remember ? store.get('pass', '') : '';
  const msg = (t) => { $('msg').textContent = t || ''; };

  $('playform').addEventListener('submit', (e) => {
    e.preventDefault();
    const nick = $('nick').value.trim(), pass = $('pass').value;
    if (!selected) return msg('Добавьте сервер кнопкой «＋»');
    if (!NICK_RE.test(nick)) return msg('Ник — Имя_Фамилия латиницей, например Ivan_Petrov');
    if (pass.length < 4) return msg('Пароль — минимум 4 символа');
    const st = status[selected];
    if (st && st.ok === false) return msg('Сервер недоступен. Проверьте адрес и что сервер запущен');
    if (st?.ok && st.online >= st.max) return msg('Сервер переполнен');
    msg('');
    store.set('nick', nick);
    if (settings.remember) store.set('pass', pass);
    if (!app) { location.href = `${selected}/?q=${settings.quality}`; return; }
    prepareAndPlay(selected, nick, pass);
  });

  // ---------- Игровой кэш ----------
  const fmtSize = (b) => b >= 1048576 ? (b / 1048576).toFixed(1).replace('.', ',') + ' МБ' : Math.max(1, Math.round(b / 1024)) + ' КБ';
  let pending = null; // { url, nick, pass }

  function showLoad(title) {
    $('loadtitle').textContent = title;
    $('loadbar').style.width = '0%';
    $('loadpct').textContent = '0%';
    $('loadsize').textContent = ''; $('loadspeed').textContent = ''; $('loadfile').textContent = '';
    $('loadcancel').hidden = false;
    $('load').hidden = false;
  }
  function hideLoad() { $('load').hidden = true; }

  function prepareAndPlay(url, nick, pass) {
    pending = { url, nick, pass };
    $('play').disabled = true;
    showLoad('Проверка игровых файлов…');
    $('loadcancel').hidden = true;
    app.checkCache(url);
  }
  function launch() {
    const p = pending; pending = null;
    hideLoad();
    $('play').disabled = false;
    if (p) app.play(p.url, p.nick, p.pass, settings.quality);
  }
  function failLoad(text) {
    pending = null;
    hideLoad();
    $('play').disabled = false;
    msg(text);
  }

  window.onCacheCheck = (r) => {
    if (!pending) return;
    if (!r.ok) {
      // без связи можно играть на старых файлах, но сервер всё равно нужен для мультиплеера
      return failLoad(r.error || 'Не удалось проверить файлы игры');
    }
    if (r.files === 0) return launch();
    showLoad(r.ready ? `Обновление игры до версии ${r.version}` : 'Загрузка игровых файлов');
    $('loadsize').textContent = `0 из ${fmtSize(r.bytes)}`;
    app.downloadCache(pending.url);
  };
  window.onCacheProgress = (p) => {
    const pct = p.total ? Math.min(100, Math.floor((p.done / p.total) * 100)) : 100;
    $('loadbar').style.width = pct + '%';
    $('loadpct').textContent = pct + '%';
    $('loadsize').textContent = `${fmtSize(p.done)} из ${fmtSize(p.total)} · файлов ${p.files}/${p.totalFiles}`;
    $('loadspeed').textContent = p.speed ? fmtSize(p.speed) + '/с' : '';
    $('loadfile').textContent = p.file || '';
  };
  window.onCacheDone = (r) => {
    if (!pending) return;
    if (r.ok) { $('loadbar').style.width = '100%'; $('loadpct').textContent = '100%'; setTimeout(launch, 300); }
    else failLoad(r.error || 'Загрузка прервалась. Нажмите «Играть», чтобы продолжить');
  };
  $('loadcancel').addEventListener('click', () => {
    if (app) app.cancelDownload();
    failLoad('Загрузка остановлена. Нажмите «Играть», чтобы продолжить с того же места');
  });

  $('refresh').addEventListener('click', refresh);
  $('addsrv').addEventListener('click', addServer);
  $('settings').addEventListener('click', openSettings);
  $('ver').textContent = app ? 'Лаунчер v' + app.version() : 'Лаунчер (веб-версия)';

  window.onLauncherResume = refresh;
  window.onLauncherBack = () => {
    if (!$('load').hidden) { if (!$('loadcancel').hidden) $('loadcancel').click(); return true; }
    if (onDlgBack) { onDlgBack(); return true; }
    return false;
  };

  // Иллюстрации: если в img/ лежат bg.jpg и logo.png — показываем их вместо оформления по умолчанию.
  const bgImg = new Image();
  bgImg.onload = () => { const b = document.querySelector('.bg'); b.style.backgroundImage = 'url(img/bg.jpg)'; b.classList.add('has-art'); };
  bgImg.src = 'img/bg.jpg';
  const logo = $('logoimg');
  logo.onload = () => { logo.hidden = false; $('logotext').hidden = true; };
  logo.src = 'img/logo.png';

  refresh();
  setInterval(refresh, 15000);
})();
