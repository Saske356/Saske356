// Живой фон лаунчера: ночной Новоград с машинами, облёт камеры по кругу.
// Использует те же модули города, что и игра (копируются в APK при сборке).
import * as THREE from 'three';
import * as W from '/shared/world.js';
import { buildCity } from '/js/city.js';
import { lightMats } from '/js/models.js';
import { Traffic } from '/js/traffic.js';

const canvas = document.getElementById('scene');
// Если в лаунчер положен арт img/bg.jpg — 3D-сцену не запускаем (экономим батарею).
const hasArt = await new Promise((ok) => { const i = new Image(); i.onload = () => ok(true); i.onerror = () => ok(false); i.src = 'img/bg.jpg'; });
if (hasArt) { canvas.remove(); throw new Error('art background'); }
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'low-power' });
} catch (e) {
  canvas.remove();
  throw e; // без WebGL остаётся CSS-фон
}
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));

const scene = new THREE.Scene();
const sky = new THREE.Color(0x0b1326);
scene.background = sky;
scene.fog = new THREE.Fog(0x1a2238, 160, 720);
scene.add(new THREE.HemisphereLight(0x8fa6d8, 0x1c1a24, 0.55));
const moon = new THREE.DirectionalLight(0xaec4ff, 0.45);
moon.position.set(-200, 300, -120);
scene.add(moon);
// тёплая подсветка снизу — как от уличных фонарей
const glow = new THREE.PointLight(0xffb15c, 2.5, 900, 0.6);
glow.position.set(W.SIZE / 2, 20, W.SIZE / 2);
scene.add(glow);

const city = W.generateCity();
const world = buildCity(scene, city);
for (const m of world.windowMats) m.emissiveIntensity = 0.95;
world.lampMat.emissiveIntensity = 2.8;
lightMats.head.emissiveIntensity = 2.4;
lightMats.tail.emissiveIntensity = 1.6;
for (const mk of world.markers) mk.group.visible = false;
scene.traverse((o) => { if (o.isSprite) o.visible = false; }); // вывески и подписи не нужны на фоне
const traffic = new Traffic(scene, 22);

const camera = new THREE.PerspectiveCamera(50, 1, 1, 1500);
function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

const C = W.SIZE / 2;
let lastRender = performance.now(), running = true;
function frame(now) {
  requestAnimationFrame(frame);
  if (!running) { lastRender = now; return; }
  if (now - lastRender < 33) return; // ~30 кадров в секунду — бережём батарею
  const dt = Math.min(0.1, (now - lastRender) / 1000);
  lastRender = now;
  const a = (now / 120000) * Math.PI * 2; // круг за 2 минуты
  camera.position.set(C + Math.cos(a) * 300, 34 + Math.sin(a * 2) * 6, C + Math.sin(a) * 300);
  camera.lookAt(C + Math.cos(a + 0.9) * 70, 6, C + Math.sin(a + 0.9) * 70);
  traffic.update(dt, []);
  renderer.render(scene, camera);
}
requestAnimationFrame(frame);
document.addEventListener('visibilitychange', () => { running = !document.hidden; });
document.documentElement.classList.add('has-scene');
