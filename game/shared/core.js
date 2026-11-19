// Игровая логика Новограда: игроки, транспорт, работы, чат, экономика.
// Не зависит от сети и диска: работает и в Node.js-сервере, и прямо в браузере (офлайн-режим).
//
//   const game = createGame({ db, saveSoon, auth, maxPlayers, log });
//   const conn = game.connect({ send(text) {…}, isOpen() { return true; } });
//   conn.message(text);  …  conn.close();
import * as W from './world.js';

export function createGame({ db = {}, saveSoon = () => {}, auth, maxPlayers = 100, log = () => {} }) {
  const timers = [];
  // ---------- Мир ----------
  const city = W.generateCity();
  const ROUTE = W.busRoute();
  const START = Date.now();
  const gameTime = () => (9 * 60 + (Date.now() - START) / 2000) % 1440; // сутки = 48 минут
  const players = new Map();
  const vehicles = new Map();
  let nextVid = 1;

  const dist = (ax, az, bx, bz) => Math.hypot(ax - bx, az - bz);
  const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
  const r2 = (v) => Math.round(v * 100) / 100;
  const money = (n) => '$' + n.toLocaleString('ru-RU');

  function send(p, msg) { if (p.conn.isOpen()) p.conn.send(JSON.stringify(msg)); }
  function notify(p, text, kind = 'info') { send(p, { t: 'notify', text, kind }); }
  function pubProfile(p) {
    const { money, level, exp, license, cars, stats } = p.prof;
    return { money, level, exp, license, cars, stats };
  }
  function sendProfile(p) { send(p, { t: 'profile', profile: pubProfile(p) }); saveSoon(); }
  function sendJob(p) {
    const j = p.job;
    send(p, { t: 'job', job: j && { type: j.type, target: j.target, label: j.label, info: j.info } });
  }
  function freeId() { let i = 0; while (players.has(i)) i++; return i; }
  function addMoney(p, n) { p.prof.money = Math.max(0, Math.round(p.prof.money + n)); }

  const PLATE = 'АВЕКМНОРСТУХ';
  function makePlate() {
    const L = () => PLATE[Math.floor(Math.random() * PLATE.length)];
    return L() + String(Math.floor(Math.random() * 900) + 100) + L() + L();
  }
  function spawnVehicle(model, color, x, z, ry, owner, kind) {
    const v = { id: nextVid++, model, color, x, z, ry, spd: 0, driver: -1, owner, kind, plate: makePlate() };
    vehicles.set(v.id, v);
    return v;
  }
  function removeVehicle(v) {
    if (v.driver >= 0) {
      const d = players.get(v.driver);
      if (d) { d.veh = -1; send(d, { t: 'exited', x: v.x, z: v.z }); }
    }
    vehicles.delete(v.id);
  }
  function removeVehiclesOf(p, kind) {
    for (const v of [...vehicles.values()]) if (v.owner === p.id && (!kind || v.kind === kind)) removeVehicle(v);
  }

  // ---------- Вход / выход ----------
  function login(conn, m) {
    const fail = (text) => { conn.send(JSON.stringify({ t: 'error', text })); return null; };
    const name = String(m.name || '').trim(), pass = String(m.pass || '');
    if (!/^[A-Z][a-z]{1,15}_[A-Z][a-z]{1,15}$/.test(name))
      return fail('Ник должен быть в формате Имя_Фамилия латиницей, например Ivan_Petrov');
    if (pass.length < 4 || pass.length > 64) return fail('Пароль должен быть от 4 до 64 символов');
    if (players.size >= maxPlayers) return fail('Сервер переполнен, попробуйте позже');
    const key = name.toLowerCase();
    for (const q of players.values()) if (q.key === key) return fail('Этот персонаж уже в игре');
    let prof = db[key], isNew = false;
    if (!prof) {
      const { salt, hash } = auth.create(pass);
      prof = db[key] = {
        name, salt, hash, money: 2000, level: 1, exp: 0, license: false,
        cars: [], pos: null, created: Date.now(), stats: { deliveries: 0, stops: 0 },
      };
      isNew = true; saveSoon();
    } else {
      if (!auth.verify(pass, prof)) return fail('Неверный пароль');
    }
    const id = freeId();
    const pos = prof.pos || W.PLACES.spawn.pos;
    const p = {
      id, conn, key, name: prof.name, prof, x: pos[0], y: W.groundHeight(pos[0], pos[1]), z: pos[1], ry: Math.PI,
      anim: 0, veh: -1, job: null, online: 0, chatT: 0, cpT: 0, spawnT: 0,
    };
    players.set(id, p);
    send(p, { t: 'welcome', id, name: p.name, x: p.x, z: p.z, ry: p.ry, isNew, profile: pubProfile(p), time: gameTime() });
    broadcast({ t: 'chat', text: `${p.name} [${id}] зашёл в Новоград`, color: '#8f9aa6' }, p);
    log(`+ ${p.name} [${id}] (${players.size} онлайн)`);
    return p;
  }

  function logout(p) {
    p.prof.pos = [r2(p.x), r2(p.z)];
    removeVehiclesOf(p);
    players.delete(p.id);
    saveSoon();
    broadcast({ t: 'chat', text: `${p.name} [${p.id}] покинул сервер`, color: '#8f9aa6' });
    log(`- ${p.name} [${p.id}] (${players.size} онлайн)`);
  }

  function broadcast(msg, except) {
    const s = JSON.stringify(msg);
    for (const p of players.values()) if (p !== except && p.conn.isOpen()) p.conn.send(s);
  }
  function local(p, radius, text, color, extra = {}) {
    const s = JSON.stringify({ t: 'chat', text, color, ...extra });
    for (const q of players.values()) if (dist(p.x, p.z, q.x, q.z) <= radius && q.conn.isOpen()) q.conn.send(s);
  }

  // ---------- Чат и RP-команды ----------
  const HELP = [
    'Текст без команды — сказать вслух (20 м)',
    '/s текст — крикнуть, /w текст — шёпотом',
    '/me действие, /do описание, /try действие (удачно/неудачно)',
    '/b текст — локальный OOC, /o текст — общий OOC',
    '/pay [id] [сумма] — передать деньги, /id [ник] — найти игрока',
    '/time — время, /help — эта справка',
  ];

  function onChat(p, raw) {
    const text = String(raw || '').replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 140);
    if (!text) return;
    const now = Date.now();
    if (now - p.chatT < 700) return notify(p, 'Не так быстро', 'warn');
    p.chatT = now;
    if (text[0] !== '/') return local(p, 20, `${p.name} говорит: ${text}`, '#ffffff', { from: p.id, bubble: text });
    const [cmdRaw, ...rest] = text.slice(1).split(' ');
    const cmd = cmdRaw.toLowerCase(), arg = rest.join(' ').trim();
    const need = () => { if (!arg) { notify(p, `Использование: /${cmd} [текст]`, 'warn'); return false; } return true; };
    switch (cmd) {
      case 'me': if (need()) local(p, 25, `${p.name} ${arg}`, '#c2a2da'); break;
      case 'do': if (need()) local(p, 25, `${arg} (( ${p.name} ))`, '#c2a2da'); break;
      case 'try':
        if (need()) {
          const ok = Math.random() < 0.5;
          local(p, 25, `${p.name} ${arg} | ${ok ? 'Удачно' : 'Неудачно'}`, ok ? '#8bd48b' : '#e57373');
        }
        break;
      case 's': if (need()) local(p, 50, `${p.name} кричит: ${arg}!`, '#ffffff', { from: p.id, bubble: arg + '!' }); break;
      case 'w': if (need()) local(p, 4, `${p.name} шепчет: ${arg}`, '#9e9e9e'); break;
      case 'b': if (need()) local(p, 25, `(( ${p.name} [${p.id}]: ${arg} ))`, '#b0bec5'); break;
      case 'o': if (need()) broadcast({ t: 'chat', text: `(( OOC ${p.name} [${p.id}]: ${arg} ))`, color: '#80cbc4' }); break;
      case 'time': notify(p, `Время в Новограде: ${W.formatTime(gameTime())}`); break;
      case 'help': for (const h of HELP) send(p, { t: 'chat', text: h, color: '#ffd54f' }); break;
      case 'id': {
        const q = arg.toLowerCase();
        const found = [...players.values()].filter((o) => o.key.includes(q)).slice(0, 8);
        send(p, { t: 'chat', text: found.length ? found.map((o) => `${o.name} [${o.id}]`).join(', ') : 'Никого не найдено', color: '#ffd54f' });
        break;
      }
      case 'pay': {
        const [ids, sums] = rest, q = players.get(Number(ids)), sum = Math.floor(Number(sums));
        if (!q || q === p) return notify(p, 'Использование: /pay [id] [сумма]', 'warn');
        if (!(sum > 0) || sum > 100000) return notify(p, 'Сумма от $1 до $100 000', 'warn');
        if (sum > p.prof.money) return notify(p, 'Недостаточно денег', 'warn');
        if (dist(p.x, p.z, q.x, q.z) > 6) return notify(p, 'Игрок слишком далеко', 'warn');
        addMoney(p, -sum); addMoney(q, sum);
        sendProfile(p); sendProfile(q);
        local(p, 25, `${p.name} передал ${money(sum)} — ${q.name}`, '#c2a2da');
        break;
      }
      default: notify(p, 'Неизвестная команда. /help — список команд', 'warn');
    }
  }

  // ---------- Действия ----------
  function near(p, place, r = 5) {
    const pos = W.PLACES[place].pos;
    return dist(p.x, p.z, pos[0], pos[1]) <= r + (p.veh >= 0 ? 4 : 0);
  }
  function pickDelivery(fromX, fromZ) {
    let best = null;
    for (let i = 0; i < 30; i++) {
      const d = city.deliveries[Math.floor(Math.random() * city.deliveries.length)];
      const k = dist(fromX, fromZ, d[0], d[1]);
      best = d;
      if (k > 70 && k < 380) break;
    }
    return [best[0], best[1]];
  }
  function courierNext(p) {
    const j = p.job;
    if (j.packages > 0) {
      j.target = pickDelivery(p.x, p.z);
      j.label = 'Доставьте посылку'; j.info = `Посылок в сумке: ${j.packages}`;
    } else {
      j.target = [...W.PLACES.courier.pos];
      j.label = 'Вернитесь на склад'; j.info = 'Посылки закончились — загрузите новые';
    }
  }
  function busNext(p) {
    const j = p.job;
    j.target = ROUTE[j.idx];
    j.label = `Остановка ${j.idx + 1} из ${ROUTE.length}`; j.info = 'Довезите пассажиров по маршруту';
  }

  function onAct(p, m) {
    const P = W.PLACES, prof = p.prof;
    const err = (t) => notify(p, t, 'warn');
    switch (m.a) {
      case 'license':
        if (!near(p, 'school')) return err('Подойдите к автошколе');
        if (prof.license) return err('У вас уже есть права');
        if (prof.money < W.PRICES.license) return err('Недостаточно денег');
        addMoney(p, -W.PRICES.license); prof.license = true;
        notify(p, 'Поздравляем! Вы получили водительские права категории B', 'ok');
        return sendProfile(p);
      case 'rent': {
        if (!near(p, 'rent')) return err('Подойдите к пункту аренды');
        if (!prof.license) return err('Нужны водительские права — их выдают в автошколе');
        if (prof.money < W.PRICES.rent) return err('Недостаточно денег');
        addMoney(p, -W.PRICES.rent);
        removeVehiclesOf(p, 'rent');
        const [x, z, ry] = P.rent.carSpawn;
        spawnVehicle('kroha', W.CAR_COLORS[Math.floor(Math.random() * 6)], x, z, ry, p.id, 'rent');
        notify(p, 'Транспорт арендован. Подойдите к нему и нажмите F', 'ok');
        return sendProfile(p);
      }
      case 'buy': {
        const car = W.CARS[m.model], color = W.CAR_COLORS[m.color | 0];
        if (!near(p, 'dealer')) return err('Подойдите к автосалону');
        if (!car || car.job || color === undefined) return err('Такой модели нет');
        if (!prof.license) return err('Без прав машину не продадут — сначала в автошколу');
        if (prof.cars.length >= 5) return err('В гараже максимум 5 машин');
        if (prof.money < car.price) return err('Недостаточно денег');
        addMoney(p, -car.price);
        prof.cars.push({ model: m.model, color });
        removeVehiclesOf(p, 'own');
        const [x, z, ry] = P.dealer.carSpawn;
        spawnVehicle(m.model, color, x, z, ry, p.id, 'own');
        notify(p, `Вы купили «${car.name}» за ${money(car.price)}! Машина ждёт у салона`, 'ok');
        return sendProfile(p);
      }
      case 'spawncar': {
        const c = prof.cars[m.idx | 0];
        if (!c) return err('Нет такой машины');
        const now = Date.now();
        if (now - p.spawnT < 8000) return err('Подождите немного');
        p.spawnT = now;
        removeVehiclesOf(p, 'own');
        const l = W.nearestLane(p.x, p.z);
        spawnVehicle(c.model, c.color, l.x, l.z, l.ry, p.id, 'own');
        return notify(p, `«${W.CARS[c.model].name}» доставлен на ближайшую дорогу`, 'ok');
      }
      case 'despawn':
        removeVehiclesOf(p, 'own'); removeVehiclesOf(p, 'rent');
        return notify(p, 'Ваш транспорт убран');
      case 'job': {
        if (p.job) return err('Сначала завершите текущую работу');
        if (m.job === 'courier') {
          if (!near(p, 'courier')) return err('Подойдите к складу');
          p.job = { type: 'courier', packages: 5, from: [...P.courier.pos] };
          courierNext(p);
          notify(p, 'Вы курьер! В сумке 5 посылок — адрес отмечен на карте', 'ok');
        } else if (m.job === 'bus') {
          if (!near(p, 'bus')) return err('Подойдите к автопарку');
          if (!prof.license) return err('Нужны водительские права');
          const [x, z, ry] = P.bus.carSpawn;
          const v = spawnVehicle('bus', 0xf0b429, x, z, ry, p.id, 'job');
          p.job = { type: 'bus', vid: v.id, idx: 0 };
          busNext(p);
          notify(p, 'Автобус ждёт рядом с парком. Садитесь (F) и езжайте по остановкам', 'ok');
        } else return;
        return sendJob(p);
      }
      case 'quitjob':
        if (!p.job) return;
        p.job = null;
        removeVehiclesOf(p, 'job');
        notify(p, 'Вы завершили работу');
        return sendJob(p);
    }
  }

  function onCheckpoint(p) {
    const j = p.job;
    if (!j || !j.target) return;
    const now = Date.now();
    if (now - p.cpT < 800) return;
    p.cpT = now;
    if (dist(p.x, p.z, j.target[0], j.target[1]) > (j.type === 'bus' ? 10 : 7)) return;
    if (j.type === 'courier') {
      if (j.packages > 0) {
        const pay = Math.min(260, Math.round(60 + dist(j.from?.[0] ?? p.x, j.from?.[1] ?? p.z, p.x, p.z) * 0.5));
        j.packages--; p.prof.stats.deliveries++;
        addMoney(p, pay);
        notify(p, `Посылка доставлена: +${money(pay)}`, 'ok');
      } else {
        j.packages = 5;
        notify(p, 'Загружено 5 новых посылок', 'ok');
      }
      j.from = [p.x, p.z];
      courierNext(p);
    } else if (j.type === 'bus') {
      if (p.veh !== j.vid) return notify(p, 'Нужно быть за рулём рабочего автобуса', 'warn');
      p.prof.stats.stops++;
      addMoney(p, 70);
      j.idx++;
      if (j.idx >= ROUTE.length) {
        j.idx = 0; addMoney(p, 350);
        notify(p, 'Маршрут пройден! Премия +$350, начинаем новый круг', 'ok');
      } else notify(p, 'Остановка: +$70', 'ok');
      busNext(p);
    }
    sendJob(p); sendProfile(p);
  }

  function onEnter(p, m) {
    const v = vehicles.get(m.vid);
    if (!v || p.veh >= 0) return;
    if (v.driver >= 0) return notify(p, 'Место водителя занято', 'warn');
    if (v.owner !== p.id) return notify(p, 'Транспорт закрыт', 'warn');
    if (dist(p.x, p.z, v.x, v.z) > W.CARS[v.model].len / 2 + 4) return;
    v.driver = p.id; p.veh = v.id;
    send(p, { t: 'entered', vid: v.id, x: v.x, z: v.z, ry: v.ry });
  }
  function onExit(p) {
    const v = vehicles.get(p.veh);
    p.veh = -1;
    if (!v) return;
    v.driver = -1; v.spd = 0;
    const off = W.CARS[v.model].wid / 2 + 0.8;
    p.x = v.x + Math.cos(v.ry) * off; p.z = v.z - Math.sin(v.ry) * off;
    send(p, { t: 'exited', x: p.x, z: p.z });
  }

  function onState(p, m) {
    p.x = Math.max(0, Math.min(W.SIZE, num(m.x, p.x)));
    p.z = Math.max(0, Math.min(W.SIZE, num(m.z, p.z)));
    p.y = num(m.y, p.y);
    p.ry = num(m.ry, p.ry);
    p.anim = (m.anim | 0) & 3;
    const v = p.veh >= 0 && vehicles.get(p.veh);
    if (v && v.driver === p.id) { v.x = p.x; v.z = p.z; v.ry = num(m.vry, v.ry); v.spd = num(m.spd, 0); }
  }

  // ---------- Входящие сообщения ----------
  function handle(p, m) {
    switch (m.t) {
      case 'state': return onState(p, m);
      case 'chat': return onChat(p, m.text);
      case 'act': return onAct(p, m);
      case 'cp': return onCheckpoint(p);
      case 'enter': return onEnter(p, m);
      case 'exit': return onExit(p);
    }
  }

  // Снимок мира 15 раз в секунду.
  timers.push(setInterval(() => {
    if (!players.size) return;
    const s = JSON.stringify({
      t: 'snap', time: gameTime(), n: players.size,
      p: [...players.values()].map((p) => [p.id, p.name, r2(p.x), r2(p.y), r2(p.z), r2(p.ry), p.anim, p.veh]),
      v: [...vehicles.values()].map((v) => [v.id, v.model, v.color, r2(v.x), r2(v.z), r2(v.ry), r2(v.spd), v.driver, v.owner, v.plate]),
    });
    for (const p of players.values()) if (p.conn.isOpen()) p.conn.send(s);
  }, 66));

  // PayDay каждые 10 минут игры.
  timers.push(setInterval(() => {
    for (const p of players.values()) {
      if (++p.online % 600 !== 0) continue;
      const prof = p.prof, pay = 150 + prof.level * 50;
      addMoney(p, pay); prof.exp++;
      let text = `PayDay! Зарплата ${money(pay)}, +1 опыт`;
      if (prof.exp >= prof.level * 3) { prof.exp = 0; prof.level++; text += `. Новый уровень: ${prof.level}!`; }
      notify(p, text, 'ok');
      sendProfile(p);
    }
  }, 1000));


  return {
    players,
    /** Новое подключение. conn: { send(text), isOpen() }. */
    connect(conn) {
      let p = null;
      return {
        message(raw) {
          let m;
          try { m = typeof raw === 'string' ? JSON.parse(raw) : JSON.parse(String(raw)); } catch { return; }
          if (!m || typeof m.t !== 'string') return;
          if (!p) { if (m.t === 'login') p = login(conn, m); return; }
          try { handle(p, m); } catch (e) { log('Ошибка обработки', m.t, e); }
        },
        close() { if (p) logout(p); p = null; },
      };
    },
    /** Запомнить позиции всех, кто в игре (перед сохранением). */
    storePositions() { for (const p of players.values()) p.prof.pos = [r2(p.x), r2(p.z)]; },
    stop() { timers.forEach(clearInterval); },
  };
}
