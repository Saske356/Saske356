// Лаунчер Новоград RP.
// Поток: заставка → проверка файлов → «Доступно обновление!» → загрузка → главный экран → игра.
// В приложении работает через мост window.NovogradApp; в обычном браузере открывает игру по ссылке.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const app = window.NovogradApp || null;
  const CFG = Object.assign({ servers: [], links: {} }, window.LAUNCHER_CONFIG || {});
  const NAME_RE = /^[A-Z][a-z]{1,15}$/;

  const store = {
    get(k, d) { try { const v = localStorage.getItem('nl-' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('nl-' + k, JSON.stringify(v)); } catch {} },
  };
  const settings = Object.assign({ quality: 'mid', remember: true }, store.get('settings', {}));
  let custom = store.get('servers', []);
  let selected = store.get('selected', null);
  const status = {};

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const mb = (b) => (b / 1048576).toFixed(2);

  // ---------- серверы ----------
  function normalize(addr) {
    let a = String(addr || '').trim();
    if (!a) return null;
    if (!/^https?:\/\//i.test(a)) a = 'http://' + a;
    try { const u = new URL(a); return /^https?:$/.test(u.protocol) && u.hostname ? u.origin : null; } catch { return null; }
  }
  const OFFLINE = 'offline'; // одиночная игра: сервер работает внутри самой игры
  const isOff = (url) => url === OFFLINE;
  function allServers() {
    const list = [{ url: OFFLINE, name: 'Одиночная игра', builtin: true }], seen = new Set([OFFLINE]);
    for (const s of CFG.servers || []) {
      const url = normalize(s.url);
      if (url && !seen.has(url)) { seen.add(url); list.push({ url, name: s.name, builtin: true }); }
    }
    for (const s of custom) if (!seen.has(s.url)) { seen.add(s.url); list.push(s); }
    return list;
  }
  async function probe(url) {
    if (isOff(url)) { status[url] = { ok: true, offline: true, online: 1, max: 1, color: '#5ccf7a', news: [] }; return; }
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 4000), t0 = performance.now();
    try {
      const j = await (await fetch(url + '/api/status', { signal: ctl.signal, cache: 'no-store' })).json();
      status[url] = { ok: true, ping: Math.round(performance.now() - t0), online: j.online | 0, max: j.max | 0, name: j.name,
        color: /^#[0-9a-f]{6}$/i.test(j.color || '') ? j.color : null, news: Array.isArray(j.news) ? j.news : [], version: j.version };
    } catch { status[url] = { ok: false }; } finally { clearTimeout(timer); }
  }
  async function refresh() {
    const list = allServers();
    if (!list.some((s) => s.url === selected)) { selected = list[0]?.url || null; store.set('selected', selected); }
    renderServer();
    await Promise.all(list.map((s) => probe(s.url).then(() => { renderServer(); if (sheetKind === 'servers') openServers(); })));
    updateNewsDot();
  }
  function srvName(s) { const st = status[s.url] || {}; return isOff(s.url) ? 'Одиночная игра' : st.name || s.name || s.url.replace(/^https?:\/\//, ''); }
  const srvIcon = (s, i) => (isOff(s.url) ? '★' : String(i));
  function renderServer() {
    const list = allServers(), i = list.findIndex((s) => s.url === selected);
    const s = list[i], st = s ? status[s.url] || {} : {};
    const icon = $('srvicon');
    icon.textContent = s ? srvIcon(s, i) : '?';
    $('srvpill').style.setProperty('--srv', st.color || '#ff8a3d');
    $('srvname').textContent = s ? srvName(s) : 'Добавьте сервер';
    $('srvonline').textContent = !s ? '' : st.offline ? '● без интернета' : st.ok ? `● ${st.online}/${st.max}` : st.ok === false ? '' : '…';
    $('srvonline').style.color = st.ok ? '' : '#ef5350';
    $('pass').placeholder = s && isOff(s.url) ? 'Пароль не нужен' : 'Пароль';
    validate();
  }

  // ---------- главный экран: имя, фамилия, пароль ----------
  const saved = String(store.get('nick', '')).split('_');
  $('fname').value = saved[0] || ''; $('lname').value = saved[1] || '';
  $('pass').value = settings.remember ? store.get('pass', '') : '';
  const hint = (t) => { $('hint').textContent = t || ''; };

  function fixName(inp) {
    const v = inp.value;
    if (/[а-яё]/i.test(v)) { inp.classList.add('bad'); return 'Имя и фамилия — латиницей, например Ivan Petrov'; }
    const clean = v.replace(/[^A-Za-z]/g, '');
    const cap = clean ? clean[0].toUpperCase() + clean.slice(1).toLowerCase() : '';
    if (cap !== v) inp.value = cap;
    inp.classList.toggle('bad', cap.length === 1);
    return '';
  }
  function validate() {
    const f = $('fname').value, l = $('lname').value, p = $('pass').value;
    const ok = NAME_RE.test(f) && NAME_RE.test(l) && (isOff(selected) || p.length >= 4) && !!selected;
    $('play').disabled = !ok;
    return ok;
  }
  for (const id of ['fname', 'lname']) $(id).addEventListener('input', (e) => { hint(fixName(e.target)); validate(); });
  $('pass').addEventListener('input', validate);
  $('form').addEventListener('submit', (e) => { e.preventDefault(); if (validate()) play(); });
  $('fname').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); $('lname').focus(); } });
  $('lname').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); $('pass').focus(); } });
  $('pass').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); $('pass').blur(); if (validate()) play(); } });
  $('play').addEventListener('click', () => { if (validate()) play(); });

  let mode = null; // 'startup' | 'play'
  let pendingPlay = null;
  function play() {
    const nick = `${$('fname').value}_${$('lname').value}`, pass = $('pass').value;
    if (isOff(selected)) {
      hint('');
      store.set('nick', nick);
      if (!app) return hint('Одиночная игра доступна в приложении');
      return app.play(OFFLINE, nick, pass || 'offline', settings.quality);
    }
    if ($('pass').value.length < 4) return hint('Пароль — минимум 4 символа');
    const st = status[selected];
    if (st && st.ok === false) return hint('Сервер недоступен. Попробуйте позже или смените сервер');
    if (st?.ok && st.online >= st.max) return hint('Сервер переполнен, выберите другой');
    hint('');
    store.set('nick', nick);
    if (settings.remember) store.set('pass', pass);
    if (!app) { location.href = `${selected}/?q=${settings.quality}`; return; }
    pendingPlay = { url: selected, nick, pass };
    mode = 'play';
    showLoading('Проверка игровых файлов…');
    app.checkCache(selected);
  }
  function launch() {
    const p = pendingPlay; pendingPlay = null;
    showMain();
    if (p) app.play(p.url, p.nick, p.pass, settings.quality);
  }

  // ---------- экраны ----------
  function showMain() {
    $('loading').hidden = true; $('ask').hidden = true; $('main').hidden = false;
    if (app) app.cancelDownload();
  }
  function showLoading(text) {
    $('main').hidden = true; $('ask').hidden = true; $('loading').hidden = false;
    $('loadtext').textContent = text;
    $('loadnums').textContent = '';
    $('loadfill').style.width = '0%';
    $('loadfill').parentElement.classList.add('indef');
    $('loadcancel').hidden = true;
  }
  function ask(title, text, yes, no, onYes, onNo) {
    $('main').hidden = true; $('loading').hidden = true; $('ask').hidden = false;
    $('asktitle').textContent = title; $('asktext').textContent = text;
    $('askyes').textContent = yes; $('askno').textContent = no;
    $('askyes').onclick = onYes; $('askno').onclick = onNo;
  }
  const backToMain = (text) => { pendingPlay = null; mode = null; showMain(); hint(text || ''); };

  // ---------- игровой кэш ----------
  window.onCacheCheck = (r) => {
    if (!mode) return;
    if (!r.ok) {
      if (mode === 'play' && r.ready) return launch(); // играем на уже скачанных файлах
      return backToMain(mode === 'play' ? r.error : '');
    }
    if (r.files === 0) return mode === 'play' ? launch() : backToMain();
    const upd = r.ready;
    ask(upd ? 'Доступно обновление!' : 'Загрузка игровых данных',
      `Размер ${upd ? 'обновления' : 'игровых данных'} составляет ${mb(r.bytes)} МБ\nЖелаете загрузить сейчас?`,
      'Начать загрузку', 'Закрыть', startDownload, () => backToMain());
  };
  function startDownload() {
    showLoading('Загрузка игровых данных...');
    $('loadcancel').hidden = false;
    app.downloadCache(pendingPlay ? pendingPlay.url : selected);
  }
  window.onCacheProgress = (p) => {
    const tr = $('loadfill').parentElement;
    tr.classList.remove('indef');
    $('loadfill').style.width = (p.total ? Math.min(100, (p.done / p.total) * 100) : 100) + '%';
    $('loadnums').textContent = `${mb(p.done)} из ${mb(p.total)} МБ (${mb(p.speed)} МБ/сек)`;
  };
  window.onCacheDone = (r) => {
    if (!mode) return;
    if (r.ok) {
      $('loadfill').parentElement.classList.remove('indef');
      $('loadfill').style.width = '100%';
      $('loadtext').textContent = 'Готово!';
      return setTimeout(() => (mode === 'play' ? launch() : backToMain()), 400);
    }
    ask('Загрузка прервалась', `${r.error || 'Нет связи с сервером'}\nУже скачанное сохранено — загрузка продолжится с того же места.`,
      'Повторить', 'Закрыть', startDownload, () => backToMain());
  };
  $('loadcancel').addEventListener('click', () => backToMain('Загрузка остановлена — продолжится при следующем входе'));

  // ---------- панели ----------
  let sheetKind = null;
  function sheet(kind, title, body) {
    sheetKind = kind;
    $('sheettitle').textContent = title;
    $('sheetbody').replaceChildren(...body);
    $('sheet').hidden = false;
  }
  function closeSheet() { $('sheet').hidden = true; sheetKind = null; }
  $('sheetclose').addEventListener('click', closeSheet);
  $('sheet').addEventListener('click', (e) => { if (e.target.id === 'sheet') closeSheet(); });

  function openServers() {
    const rows = allServers().map((s, i) => {
      const st = status[s.url] || {};
      const b = el('button', 'srvrow' + (s.url === selected ? ' on' : ''));
      b.type = 'button';
      b.style.setProperty('--srv', st.color || '#ff8a3d');
      const ic = el('span', 'srvicon', srvIcon(s, i));
      const meta = el('div', 'meta');
      meta.append(el('b', null, srvName(s)), el('span', null, isOff(s.url) ? 'без интернета, прогресс на телефоне' : s.url.replace(/^https?:\/\//, '')));
      const num = el('div', 'num');
      if (st.offline) num.append(el('b', null, 'офлайн'));
      else if (st.ok) num.append(el('b', null, `${st.online} / ${st.max}`), document.createTextNode(`пинг ${st.ping} мс`));
      else num.append(el('b', st.ok === false ? 'off' : '', st.ok === false ? 'недоступен' : '…'));
      b.append(ic, meta, num);
      if (!s.builtin) {
        const d = el('button', 'del', '✕'); d.type = 'button';
        d.addEventListener('click', (e) => {
          e.stopPropagation();
          custom = custom.filter((c) => c.url !== s.url); store.set('servers', custom);
          refresh(); openServers();
        });
        b.append(d);
      }
      b.addEventListener('click', () => { selected = s.url; store.set('selected', selected); renderServer(); updateNewsDot(); closeSheet(); });
      return b;
    });
    const addr = el('input'); addr.placeholder = '203.0.113.10:3000'; addr.autocapitalize = 'off'; addr.spellcheck = false;
    const lab = el('label', 'field', 'Добавить сервер — IP или домен с портом'); lab.append(addr);
    const err = el('div', 'err');
    const add = el('button', 'btn primary', 'Добавить'); add.type = 'button';
    add.addEventListener('click', () => {
      const url = normalize(addr.value);
      if (!url) { err.textContent = 'Неверный адрес'; return; }
      if (allServers().some((s) => s.url === url)) { err.textContent = 'Такой сервер уже есть'; return; }
      custom.push({ url, name: null }); store.set('servers', custom);
      selected = url; store.set('selected', url);
      refresh(); openServers();
    });
    sheet('servers', 'Выбор сервера', [...(rows.length ? rows : [el('div', 'empty', 'Серверов пока нет.')]), lab, err, add]);
  }
  $('srvpill').addEventListener('click', openServers);
  $('swapbtn').addEventListener('click', openServers);

  function newsList() { return (status[selected]?.ok && status[selected].news) || []; }
  function updateNewsDot() {
    const n = newsList()[0];
    $('newsdot').hidden = !n || store.get('seen-news', '') === (n.title || '') + (n.date || '');
  }
  $('newsbtn').addEventListener('click', () => {
    const list = newsList();
    if (list[0]) store.set('seen-news', (list[0].title || '') + (list[0].date || ''));
    updateNewsDot();
    sheet('news', 'Новости', list.length ? list.slice(0, 30).map((n) => {
      const d = el('div', 'news');
      if (n.date) d.append(el('small', null, new Date(n.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })));
      d.append(el('b', null, n.title || ''), el('p', null, n.text || ''));
      return d;
    }) : [el('div', 'empty', 'Новостей пока нет.')]);
  });

  $('settingsbtn').addEventListener('click', () => {
    const seg = el('div', 'seg');
    const names = { low: 'Низкая', mid: 'Средняя', high: 'Высокая' };
    for (const q of ['low', 'mid', 'high']) {
      const b = el('button', settings.quality === q ? 'on' : '', names[q]); b.type = 'button';
      b.addEventListener('click', () => {
        settings.quality = q; store.set('settings', settings);
        [...seg.children].forEach((c) => c.classList.toggle('on', c === b));
      });
      seg.append(b);
    }
    const ql = el('div', 'field', 'Качество графики'); ql.append(seg);
    const rem = el('label', 'check'), cb = el('input'); cb.type = 'checkbox'; cb.checked = settings.remember;
    cb.addEventListener('change', () => { settings.remember = cb.checked; store.set('settings', settings); if (!cb.checked) store.set('pass', ''); });
    rem.append(cb, document.createTextNode('Запоминать пароль'));
    const items = [ql, el('p', 'note', 'Низкая — без теней и с меньшим трафиком, для слабых телефонов.'), rem];
    if (app && selected && !isOff(selected)) {
      const re = el('button', 'btn', 'Перекачать файлы игры'); re.type = 'button';
      re.addEventListener('click', () => { app.clearCache(selected); re.textContent = 'Файлы удалены — скачаются при входе'; re.disabled = true; });
      items.push(re);
    }
    items.push(el('p', 'note', `Лаунчер ${app ? 'v' + app.version() : '(веб-версия)'}`));
    sheet('settings', 'Настройки', items);
  });

  // ---------- соцсети и поддержка ----------
  const openLink = (url) => { if (app) app.open(url); else window.open(url, '_blank'); };
  const L = CFG.links || {};
  if (L.telegram) {
    const b = el('button', 'ic'); b.type = 'button'; b.setAttribute('aria-label', 'Telegram');
    b.innerHTML = '<svg viewBox="0 0 24 24"><path d="M21 4 3 11l6 2 2 6 3-4 5 4 2-15zM9 13l8-6-6 8"/></svg>';
    b.addEventListener('click', () => openLink(L.telegram));
    $('socials').append(b);
  }
  if (L.vk) {
    const b = el('button', 'ic social', 'VK'); b.type = 'button';
    b.addEventListener('click', () => openLink(L.vk));
    $('socials').append(b);
  }
  if (L.support) {
    $('supportbtn').hidden = false;
    $('supportbtn').addEventListener('click', () => openLink(L.support));
  }

  // ---------- иллюстрации из img/ ----------
  const probeImg = (src, ok) => { const i = new Image(); i.onload = () => ok(src); i.src = src; };
  probeImg('img/logo.png', (src) => { document.querySelectorAll('.logoimg').forEach((i) => { i.src = src; }); document.documentElement.classList.add('has-logo'); });
  probeImg('img/loading.jpg', (src) => { document.querySelector('.loadart').style.backgroundImage = `url(${src})`; });
  probeImg('img/bg.jpg', (src) => {
    const c = $('scene'); if (c) c.style.display = 'none';
    document.body.style.background = `#07090d url(${src}) center / cover no-repeat`;
  });

  // ---------- кнопка «Назад» ----------
  window.onLauncherBack = () => {
    if (!$('sheet').hidden) { closeSheet(); return true; }
    if (!$('ask').hidden) { $('askno').click(); return true; }
    if (!$('loading').hidden) { if (!$('loadcancel').hidden) $('loadcancel').click(); return true; }
    return false;
  };
  window.onLauncherResume = refresh;

  // ---------- старт ----------
  $('ver').textContent = app ? `v${app.version()}` : 'web';
  $('main').hidden = true;
  const splashStart = performance.now();
  refresh().then(() => {
    setTimeout(() => {
      $('splash').classList.add('out');
      setTimeout(() => $('splash').remove(), 700);
      if (app && selected && !isOff(selected) && status[selected]?.ok) {
        mode = 'startup';
        showLoading('Подключение к серверу…');
        app.checkCache(selected);
      } else showMain();
    }, Math.max(0, 1800 - (performance.now() - splashStart)));
  });
  setInterval(refresh, 20000);
})();
