import * as THREE from 'three';
import * as W from '/shared/world.js';
import { buildCity, makeBeam } from './city.js';
import { makeCar, makePed, animatePed, textSprite, disposeSprite, lightMats, colorFromString, spinWheels } from './models.js';
import { Traffic } from './traffic.js';
import * as UI from './ui.js';
import { handlers, readInput, takeCamera, initPointer, initTouch, isTouch, isTyping } from './input.js';

const $ = (id) => document.getElementById(id);
const city = W.generateCity();

// ---------- Рендер ----------
const canvas = $('game');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: !isTouch });
renderer.setPixelRatio(Math.min(devicePixelRatio, isTouch ? 1.25 : 1.75));
renderer.shadowMap.enabled = !isTouch;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(65, 1, 0.1, 1200);
scene.fog = new THREE.Fog(0x9fc3e0, 140, 560);
const hemi = new THREE.HemisphereLight(0xdfefff, 0x4a5a3a, 1.6);
const sun = new THREE.DirectionalLight(0xffffff, 2.4);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -90, right: 90, top: 90, bottom: -90, near: 1, far: 500 });
sun.shadow.bias = -0.0006;
scene.add(hemi, sun, sun.target);
const world3d = buildCity(scene, city);
const traffic = new Traffic(scene, isTouch ? 18 : 28);
const jobBeam = makeBeam(0xff4040), gpsBeam = makeBeam(0x3f9bff);
scene.add(jobBeam, gpsBeam);

function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

// ---------- Состояние ----------
const S = {
  myId: -1, name: '', profile: null, job: null, online: 1,
  x: 0, y: 0, z: 0, ry: 0, anim: 0, veh: -1, car: null,
  camYaw: Math.PI, camPitch: 0.32, camDist: 6, lastDrag: 0,
  waypoint: null, time: 540, playing: false,
};
const players = new Map();   // id → { mesh, tag, tx,ty,tz,try, anim, veh, name }
const vehicles = new Map();  // id → { mesh, model, owner, driver, tx,tz,try, spd, plate }
let me = null;
let myBubble = null;

const lerpAngle = (a, b, t) => a + ((((b - a + Math.PI) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2) - Math.PI) * t;
const r2 = (v) => Math.round(v * 100) / 100;

// ---------- Сеть ----------
let ws = null;
const send = (m) => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(m)); };

function connect(name, pass) {
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => send({ t: 'login', name, pass });
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = () => {
    if (S.playing) {
      UI.openModal('Соединение потеряно', [UI.el('p', {}, 'Связь с сервером прервалась.'), UI.button('Переподключиться', () => location.reload())]);
    } else loginError('Сервер недоступен');
  };
}

function onMessage(m) {
  switch (m.t) {
    case 'error':
      if (!S.playing) { loginError(m.text); ws.close(); } else UI.toast(m.text, 'warn');
      break;
    case 'welcome': startGame(m); break;
    case 'snap': applySnap(m); break;
    case 'chat':
      UI.addChat(m.text, m.color);
      if (m.bubble != null && m.from != null) showBubble(m.from, m.bubble);
      break;
    case 'notify': UI.toast(m.text, m.kind); break;
    case 'profile': S.profile = m.profile; updateStats(); break;
    case 'job':
      S.job = m.job;
      UI.jobPanel(S.job);
      break;
    case 'entered': {
      const v = vehicles.get(m.vid);
      if (!v) return;
      S.veh = m.vid;
      S.car = { model: v.model, x: m.x, z: m.z, ry: m.ry, spd: 0, steer: 0 };
      me.visible = false;
      S.camYaw = m.ry;
      break;
    }
    case 'exited':
      S.veh = -1; S.car = null;
      S.x = m.x; S.z = m.z;
      me.visible = true;
      UI.speedo(null);
      break;
  }
}

function applySnap(m) {
  S.time = m.time;
  S.online = m.p.length;
  const seenP = new Set();
  for (const [id, name, x, y, z, ry, anim, veh] of m.p) {
    if (id === S.myId) continue;
    seenP.add(id);
    let p = players.get(id);
    if (!p) {
      const mesh = makePed(colorFromString(name));
      mesh.position.set(x, y, z);
      const tag = textSprite(`${name} [${id}]`, { size: 26 });
      scene.add(mesh, tag);
      p = { mesh, tag, name, bubble: null };
      players.set(id, p);
    }
    Object.assign(p, { tx: x, ty: y, tz: z, tr: ry, anim, veh });
    p.mesh.visible = veh < 0;
  }
  for (const [id, p] of players) if (!seenP.has(id)) {
    scene.remove(p.mesh, p.tag); disposeSprite(p.tag);
    if (p.bubble) { scene.remove(p.bubble.sprite); disposeSprite(p.bubble.sprite); }
    players.delete(id);
  }
  const seenV = new Set();
  for (const [id, model, color, x, z, ry, spd, driver, owner, plate] of m.v) {
    seenV.add(id);
    let v = vehicles.get(id);
    if (!v) {
      const mesh = makeCar(model, color);
      mesh.position.set(x, W.groundHeight(x, z), z); mesh.rotation.y = ry;
      scene.add(mesh);
      v = { mesh, model, plate };
      vehicles.set(id, v);
    }
    Object.assign(v, { tx: x, tz: z, tr: ry, spd, driver, owner });
  }
  for (const [id, v] of vehicles) if (!seenV.has(id)) { scene.remove(v.mesh); vehicles.delete(id); }
}

function showBubble(from, text) {
  const holder = from === S.myId ? null : players.get(from);
  if (from !== S.myId && !holder) return;
  const prev = from === S.myId ? myBubble : holder.bubble;
  if (prev) { scene.remove(prev.sprite); disposeSprite(prev.sprite); }
  const sprite = textSprite(text.length > 40 ? text.slice(0, 40) + '…' : text, { size: 24, bg: 'rgba(15,18,24,0.7)', scale: 0.011 });
  scene.add(sprite);
  const b = { sprite, until: performance.now() + 6000 };
  if (from === S.myId) myBubble = b; else holder.bubble = b;
}

// ---------- Вход ----------
function loginError(text) {
  $('loginerr').textContent = text;
  $('loginbtn').disabled = false;
}
$('loginform').addEventListener('submit', (e) => {
  e.preventDefault();
  const name = $('nick').value.trim(), pass = $('pass').value;
  try { localStorage.setItem('nrp-nick', name); } catch {}
  $('loginerr').textContent = '';
  $('loginbtn').disabled = true;
  connect(name, pass);
});
try { $('nick').value = localStorage.getItem('nrp-nick') || ''; } catch {}

function startGame(m) {
  S.myId = m.id; S.name = m.name; S.profile = m.profile; S.time = m.time;
  S.x = m.x; S.z = m.z; S.ry = m.ry; S.camYaw = m.ry;
  S.playing = true;
  me = makePed(colorFromString(m.name));
  scene.add(me);
  $('login').hidden = true;
  $('hud').hidden = false;
  if (isTouch) initTouch($('touch'));
  updateStats();
  UI.addChat(`Добро пожаловать в Новоград, ${m.name}!`, '#ffd54f');
  UI.addChat('M — меню и GPS, E — взаимодействие, F — сесть в транспорт, T — чат, /help — команды', '#ffd54f');
  if (m.isNew) {
    UI.toast('Начните с автошколы: права откроют аренду, покупку машин и работу водителем', 'info');
    S.waypoint = [...W.PLACES.school.pos];
  }
}

function updateStats() {
  if (S.profile) UI.setStats(S.profile, S.time, S.online);
}

// ---------- Клавиши ----------
handlers.onKey = (code, e) => {
  if (!S.playing) return;
  if (code === 'Escape') { if (UI.isModalOpen()) UI.closeModal(); return; }
  if (code === 'KeyT' || code === 'Enter' || code === 'Slash' || code === 'Chat') {
    e?.preventDefault();
    UI.openChat();
    if (code === 'Slash') $('chatinput').value = '/';
    return;
  }
  if (code === 'KeyM') { UI.isModalOpen() ? UI.closeModal() : openMenu(); return; }
  if (UI.isModalOpen()) return;
  if (code === 'KeyF') toggleVehicle();
  if (code === 'KeyE') interact();
};

$('chatinput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const text = e.target.value.trim();
    if (text) send({ t: 'chat', text });
    UI.closeChat();
    e.preventDefault();
  } else if (e.key === 'Escape') UI.closeChat();
  e.stopPropagation();
});
$('chatinput').addEventListener('blur', () => UI.closeChat());

function toggleVehicle() {
  if (S.veh >= 0) {
    if (Math.abs(S.car.spd) > 4) return UI.toast('Сначала остановитесь', 'warn');
    return send({ t: 'exit' });
  }
  let best = null, bd = Infinity;
  for (const [id, v] of vehicles) {
    if (v.driver >= 0) continue;
    for (const c of W.carCircles(v.mesh.position.x, v.mesh.position.z, v.mesh.rotation.y, v.model)) {
      const d = Math.hypot(c.x - S.x, c.z - S.z) - c.r;
      if (d < bd) { bd = d; best = { id, v }; }
    }
  }
  if (!best || bd > 3.5) return UI.toast('Рядом нет транспорта', 'warn');
  if (best.v.owner !== S.myId) return UI.toast('Транспорт закрыт — это чужая машина', 'warn');
  send({ t: 'enter', vid: best.id });
}

// ---------- Места и диалоги ----------
function nearestPlace() {
  const lim = S.veh >= 0 ? 8 : 3.5;
  for (const [id, p] of Object.entries(W.PLACES)) {
    if (p.hidden) continue;
    if (Math.hypot(S.x - p.pos[0], S.z - p.pos[1]) < lim) return id;
  }
  return null;
}

const act = (o) => { send({ t: 'act', ...o }); UI.closeModal(); };
const P = (text) => UI.el('p', {}, text);

function interact() {
  const id = nearestPlace();
  if (!id) return;
  const place = W.PLACES[id], prof = S.profile, job = S.job;
  if (id === 'rent') {
    UI.openModal(place.name, [
      P('Компактная «Кроха» на время игры. Нужны водительские права.'),
      UI.button(`Арендовать — ${UI.money(W.PRICES.rent)}`, () => act({ a: 'rent' }), 'primary'),
    ]);
  } else if (id === 'school') {
    UI.openModal(place.name, prof.license
      ? [P('У вас уже есть права категории B. Удачи на дорогах!')]
      : [P('Пройдите курс и получите права категории B — они нужны для аренды, покупки машин и работы водителем.'),
        UI.button(`Получить права — ${UI.money(W.PRICES.license)}`, () => act({ a: 'license' }), 'primary')]);
  } else if (id === 'dealer') {
    const rows = Object.entries(W.CARS).filter(([, c]) => !c.job).map(([model, c]) => {
      let color = 0;
      const sw = W.CAR_COLORS.map((col, i) => {
        const b = UI.el('span', { class: 'swatch' + (i === 0 ? ' on' : ''), style: `background:#${col.toString(16).padStart(6, '0')}` });
        b.addEventListener('click', () => { color = i; sw.forEach((s) => s.classList.remove('on')); b.classList.add('on'); });
        return b;
      });
      return UI.el('div', { class: 'carrow' },
        UI.el('div', { class: 'cname' }, c.name, UI.el('small', {}, `до ${Math.round(c.maxSpeed * 3.6)} км/ч`)),
        UI.el('div', { class: 'swatches' }, sw),
        UI.button(UI.money(c.price), () => act({ a: 'buy', model, color }), prof.money >= c.price ? 'primary' : ''));
    });
    UI.openModal(place.name, [P(`На счету: ${UI.money(prof.money)}. Выберите цвет и модель.`), ...rows]);
  } else if (id === 'courier') {
    if (job?.type === 'courier') UI.openModal(place.name, [P(`Вы работаете курьером. Доставлено всего: ${prof.stats.deliveries}.`), UI.button('Уволиться', () => act({ a: 'quitjob' }))]);
    else if (job) UI.openModal(place.name, [P('Сначала завершите текущую работу (меню M).')]);
    else UI.openModal(place.name, [
      P('Развозите посылки по адресам города — пешком или на своём транспорте. 5 посылок за рейс, $60–260 за доставку.'),
      UI.button('Начать работу', () => act({ a: 'job', job: 'courier' }), 'primary')]);
  } else if (id === 'bus') {
    if (job?.type === 'bus') UI.openModal(place.name, [P(`Смена идёт. Остановок пройдено всего: ${prof.stats.stops}.`), UI.button('Завершить смену', () => act({ a: 'quitjob' }))]);
    else if (job) UI.openModal(place.name, [P('Сначала завершите текущую работу (меню M).')]);
    else UI.openModal(place.name, [
      P(`Водите автобус по кольцевому маршруту: $70 за остановку и $350 за круг. Нужны права.`),
      UI.button('Начать смену', () => act({ a: 'job', job: 'bus' }), 'primary')]);
  }
}

function openMenu() {
  const p = S.profile, j = S.job;
  const row = (k, v) => UI.el('div', { class: 'kv' }, UI.el('span', {}, k), UI.el('b', {}, v));
  const cars = p.cars.length
    ? p.cars.map((c, idx) => UI.el('div', { class: 'carrow' },
      UI.el('span', { class: 'swatch on', style: `background:#${c.color.toString(16).padStart(6, '0')}` }),
      UI.el('div', { class: 'cname' }, W.CARS[c.model].name),
      UI.button('Вызвать', () => act({ a: 'spawncar', idx }))))
    : [P('Личного транспорта нет — загляните в автосалон.')];
  const gps = Object.entries(W.PLACES).map(([id, pl]) => UI.button(pl.name, () => {
    S.waypoint = [...pl.pos]; UI.closeModal(); UI.toast(`Метка: ${pl.name}`);
  }));
  UI.openModal('Меню', [
    UI.el('h3', {}, 'Персонаж'),
    row('Имя', `${S.name} [${S.myId}]`),
    row('Уровень', `${p.level} (опыт ${p.exp}/${p.level * 3})`),
    row('Деньги', UI.money(p.money)),
    row('Права', p.license ? 'Категория B' : 'Нет'),
    row('Работа', j ? (j.type === 'bus' ? 'Водитель автобуса' : 'Курьер') : 'Безработный'),
    j && UI.button('Уволиться с работы', () => act({ a: 'quitjob' })),
    UI.el('h3', {}, 'Мой транспорт'),
    ...cars,
    UI.button('Убрать мой транспорт', () => act({ a: 'despawn' })),
    UI.el('h3', {}, 'GPS'),
    UI.el('div', { class: 'grid' }, gps, S.waypoint && UI.button('Сбросить метку', () => { S.waypoint = null; UI.closeModal(); })),
    UI.el('h3', {}, 'Управление'),
    P(isTouch
      ? 'Джойстик — движение, свайп справа — камера. F — транспорт, E — действие, ⇧ — бег/ручник.'
      : 'WASD — движение/вождение, Shift — бег, Пробел — ручник, мышь (зажать) — камера, колесо — зум. F — сесть/выйти, E — действие, T — чат, M — меню.'),
    P('Чат: /me, /do, /try, /s, /w, /b, /o, /pay [id] [сумма], /id, /help'),
  ]);
}

// ---------- Физика ----------
function obstacleCircles() {
  const out = [];
  for (const c of traffic.cars) out.push(...W.carCircles(c.x, c.z, c.ry, c.model));
  for (const [id, v] of vehicles) if (id !== S.veh) out.push(...W.carCircles(v.mesh.position.x, v.mesh.position.z, v.mesh.rotation.y, v.model));
  return out;
}
function pushFrom(x, z, r, circles) {
  let hit = false;
  for (const c of circles) {
    const dx = x - c.x, dz = z - c.z, d = Math.hypot(dx, dz), m = r + c.r;
    if (d < m && d > 1e-4) { x = c.x + (dx / d) * m; z = c.z + (dz / d) * m; hit = true; }
  }
  return { x, z, hit };
}
const clampWorld = (v) => Math.max(1, Math.min(W.SIZE - 1, v));

function updateWalk(dt, inp) {
  const speed = inp.sprint ? 8.5 : 4.5;
  const fx = Math.sin(S.camYaw), fz = Math.cos(S.camYaw);
  let dx = fx * inp.y - fz * inp.x, dz = fz * inp.y + fx * inp.x;
  const len = Math.hypot(dx, dz);
  if (len > 0.05) {
    const k = Math.min(len, 1) / len;
    dx *= k; dz *= k;
    S.x += dx * speed * dt; S.z += dz * speed * dt;
    S.ry = lerpAngle(S.ry, Math.atan2(dx, dz), 1 - Math.exp(-dt * 12));
    S.anim = inp.sprint && len > 0.5 ? 2 : 1;
  } else S.anim = 0;
  let r = W.collideCircle(S.x, S.z, 0.35, city.boxes);
  r = pushFrom(r.x, r.z, 0.35, obstacleCircles());
  S.x = clampWorld(r.x); S.z = clampWorld(r.z);
  S.y = W.groundHeight(S.x, S.z);
  me.position.set(S.x, me.position.y + (S.y - me.position.y) * Math.min(1, dt * 15), S.z);
  me.rotation.y = S.ry;
  animatePed(me, S.anim, dt);
}

function updateCar(dt, inp) {
  const c = S.car, m = W.CARS[c.model];
  const v = vehicles.get(S.veh);
  if (inp.y > 0) {
    if (c.spd < -0.5) c.spd += 22 * dt;
    else c.spd += m.accel * inp.y * dt * Math.max(0, 1 - c.spd / m.maxSpeed);
  } else if (inp.y < 0) {
    if (c.spd > 0.5) c.spd -= 22 * dt * -inp.y;
    else c.spd = Math.max(-8, c.spd - m.accel * 0.6 * dt);
  } else c.spd -= Math.sign(c.spd) * Math.min(Math.abs(c.spd), 2.5 * dt);
  if (inp.brake) c.spd *= Math.max(0, 1 - 3 * dt);
  c.steer += (inp.x - c.steer) * Math.min(1, dt * 7);
  const ang = -c.steer * 0.55 * (1 - Math.min(Math.abs(c.spd) / (m.maxSpeed * 1.3), 0.65));
  c.ry += (c.spd * Math.tan(ang)) / (m.len * 0.6) * dt;
  c.x += Math.sin(c.ry) * c.spd * dt;
  c.z += Math.cos(c.ry) * c.spd * dt;

  // столкновения: машина — набор окружностей
  const others = obstacleCircles();
  let hit = false;
  for (const circ of W.carCircles(c.x, c.z, c.ry, c.model)) {
    let r = W.collideCircle(circ.x, circ.z, circ.r, city.boxes);
    r = pushFrom(r.x, r.z, circ.r, others);
    if (r.x !== circ.x || r.z !== circ.z) { c.x += r.x - circ.x; c.z += r.z - circ.z; hit = true; }
  }
  if (hit) c.spd = Math.abs(c.spd) > 5 ? c.spd * -0.25 : c.spd * 0.6;
  c.x = clampWorld(c.x); c.z = clampWorld(c.z);
  S.x = c.x; S.z = c.z; S.ry = c.ry; S.y = W.groundHeight(c.x, c.z); S.anim = 0;
  if (v) {
    v.mesh.position.set(c.x, v.mesh.position.y + (S.y - v.mesh.position.y) * Math.min(1, dt * 10), c.z);
    v.mesh.rotation.y = c.ry;
    spinWheels(v.mesh, c.spd, dt);
  }
  UI.speedo(Math.abs(c.spd) * 3.6, `${m.name}${v ? ' · ' + v.plate : ''}`);
}

// ---------- Камера и небо ----------
const skyDay = new THREE.Color(0x8fc1ea), skyNight = new THREE.Color(0x0a1224), skyDusk = new THREE.Color(0xe08a5a), skyTmp = new THREE.Color();

function updateSky() {
  const t = S.time / 1440, ang = (t - 0.25) * Math.PI * 2, elev = Math.sin(ang);
  const day = THREE.MathUtils.smoothstep(elev, -0.12, 0.3);
  const dusk = Math.max(0, 1 - Math.abs(elev) / 0.25) * 0.6;
  skyTmp.copy(skyNight).lerp(skyDay, day).lerp(skyDusk, dusk * day);
  scene.background = skyTmp;
  scene.fog.color.copy(skyTmp);
  sun.intensity = 0.15 + 2.3 * day;
  hemi.intensity = 0.45 + 1.2 * day;
  sun.color.setRGB(1, 0.85 + 0.15 * day, 0.7 + 0.3 * day);
  sun.position.set(S.x + Math.cos(ang) * 150, Math.max(0.25, elev) * 220, S.z + 70);
  sun.target.position.set(S.x, 0, S.z);
  const night = 1 - day;
  for (const m of world3d.windowMats) m.emissiveIntensity = night * 0.9;
  world3d.lampMat.emissiveIntensity = night * 2.5;
  lightMats.head.emissiveIntensity = 0.25 + night * 2;
  lightMats.tail.emissiveIntensity = 0.3 + night * 1.2;
}

function updateCamera(dt) {
  const c = takeCamera();
  if (c.dx || c.dy) S.lastDrag = performance.now();
  S.camYaw -= c.dx * 0.006;
  S.camPitch = THREE.MathUtils.clamp(S.camPitch + c.dy * 0.004, -0.05, 1.25);
  S.camDist = THREE.MathUtils.clamp(S.camDist + c.zoom * 0.8, 3, 18);
  let tx = S.x, ty = S.y + 1.6, tz = S.z, dist = S.camDist;
  if (S.car) {
    const m = W.CARS[S.car.model];
    ty = S.y + m.hgt + 0.4;
    dist = S.camDist + m.len * 0.9;
    if (performance.now() - S.lastDrag > 1500 && Math.abs(S.car.spd) > 1)
      S.camYaw = lerpAngle(S.camYaw, S.car.ry, 1 - Math.exp(-dt * 2.5));
  }
  const cp = Math.cos(S.camPitch), sp = Math.sin(S.camPitch);
  camera.position.set(tx - Math.sin(S.camYaw) * dist * cp, Math.max(0.6, ty + dist * sp), tz - Math.cos(S.camYaw) * dist * cp);
  camera.lookAt(tx, ty, tz);
}

// ---------- Цикл ----------
let last = performance.now(), sendT = 0, uiT = 0, cpT = 0;

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (!S.playing) {
    // заставка: облёт города
    const a = now / 20000;
    camera.position.set(W.SIZE / 2 + Math.cos(a) * 260, 120, W.SIZE / 2 + Math.sin(a) * 260);
    camera.lookAt(W.SIZE / 2, 0, W.SIZE / 2);
    S.x = W.SIZE / 2; S.z = W.SIZE / 2;
    traffic.update(dt, []);
    updateSky();
    renderer.render(scene, camera);
    return;
  }
  const blocked = isTyping() || UI.isModalOpen();
  const inp = blocked ? { x: 0, y: 0, sprint: false, brake: true } : readInput();
  if (S.car) updateCar(dt, inp); else updateWalk(dt, inp);

  // интерполяция других игроков и машин
  const k = 1 - Math.exp(-dt * 12);
  const obstacles = [{ x: S.x, z: S.z }];
  for (const p of players.values()) {
    if (p.tx == null) continue;
    p.mesh.position.x += (p.tx - p.mesh.position.x) * k;
    p.mesh.position.y += (p.ty - p.mesh.position.y) * k;
    p.mesh.position.z += (p.tz - p.mesh.position.z) * k;
    p.mesh.rotation.y = lerpAngle(p.mesh.rotation.y, p.tr, k);
    animatePed(p.mesh, p.anim, dt);
    const near = Math.hypot(p.mesh.position.x - S.x, p.mesh.position.z - S.z) < 35;
    p.tag.visible = near;
    p.tag.position.set(p.mesh.position.x, p.mesh.position.y + (p.veh >= 0 ? 3.2 : 2.25), p.mesh.position.z);
    if (p.bubble) p.bubble.sprite.position.set(p.tag.position.x, p.tag.position.y + 0.5, p.tag.position.z);
    if (p.veh < 0) obstacles.push({ x: p.mesh.position.x, z: p.mesh.position.z });
  }
  for (const [id, v] of vehicles) {
    if (id === S.veh || v.tx == null) continue;
    v.mesh.position.x += (v.tx - v.mesh.position.x) * k;
    v.mesh.position.z += (v.tz - v.mesh.position.z) * k;
    v.mesh.position.y = W.groundHeight(v.mesh.position.x, v.mesh.position.z);
    v.mesh.rotation.y = lerpAngle(v.mesh.rotation.y, v.tr, k);
    if (v.driver >= 0) spinWheels(v.mesh, v.spd, dt);
    obstacles.push({ x: v.mesh.position.x, z: v.mesh.position.z });
  }
  if (myBubble) myBubble.sprite.position.set(S.x, S.y + (S.car ? W.CARS[S.car.model].hgt + 1.2 : 2.5), S.z);
  for (const b of [myBubble, ...[...players.values()].map((p) => p.bubble)]) {
    if (b && now > b.until) {
      scene.remove(b.sprite); disposeSprite(b.sprite);
      if (b === myBubble) myBubble = null;
      else for (const p of players.values()) if (p.bubble === b) p.bubble = null;
    }
  }
  traffic.update(dt, obstacles);

  // маркеры, чекпоинты
  for (const mk of world3d.markers) { mk.ring.rotation.y += dt; mk.ring.position.y = 0.7 + Math.sin(now / 400) * 0.08; }
  const target = S.job?.target;
  jobBeam.visible = !!target;
  if (target) {
    jobBeam.position.set(target[0], W.groundHeight(target[0], target[1]), target[1]);
    const d = Math.hypot(S.x - target[0], S.z - target[1]);
    if (now - uiT < 20) UI.jobDistance(d);
    if (d < (S.job.type === 'bus' ? 8 : 5) && now - cpT > 1000) { cpT = now; send({ t: 'cp' }); }
  }
  gpsBeam.visible = !!S.waypoint;
  if (S.waypoint) {
    gpsBeam.position.set(S.waypoint[0], W.groundHeight(S.waypoint[0], S.waypoint[1]), S.waypoint[1]);
    if (Math.hypot(S.x - S.waypoint[0], S.z - S.waypoint[1]) < 6) { S.waypoint = null; UI.toast('Вы прибыли на место'); }
  }

  const place = nearestPlace();
  UI.hint(blocked ? null : place ? `${isTouch ? 'Кнопка' : 'Клавиша'} E — ${W.PLACES[place].name}` : null);

  if (now - sendT > 66) {
    sendT = now;
    send({ t: 'state', x: r2(S.x), y: r2(S.y), z: r2(S.z), ry: r2(S.ry), anim: S.anim, vry: S.car ? r2(S.car.ry) : 0, spd: S.car ? r2(S.car.spd) : 0 });
  }
  if (now - uiT > 250) {
    uiT = now;
    updateStats();
  }
  updateSky();
  updateCamera(dt);
  UI.drawMinimap({
    x: S.x, z: S.z, yaw: S.camYaw, ry: S.ry, waypoint: S.waypoint, target,
    others: [...players.values()].map((p) => ({ x: p.mesh.position.x, z: p.mesh.position.z })),
  });
  renderer.render(scene, camera);
}

initPointer(canvas);
UI.initMinimap(city);
requestAnimationFrame(frame);
window.__game = { S, players, vehicles, traffic };
