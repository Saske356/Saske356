'use strict';
/* ---------------- рендер ---------------- */
const canvas = $('#view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: !isTouch, powerPreference: 'high-performance' });
renderer.autoClear = false;
const scene = new THREE.Scene();
const SKY = 0x93a7b0;
scene.background = new THREE.Color(SKY);
scene.fog = new THREE.Fog(SKY, 38, 115);
const BASE_FOV = 74;
const camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.05, 300);
camera.rotation.order = 'YXZ';
scene.add(new THREE.HemisphereLight(0xe4edf0, 0x4b4033, 0.95));
const sun = new THREE.DirectionalLight(0xffe0b5, 0.8); sun.position.set(30, 60, 18); scene.add(sun);

const vmScene = new THREE.Scene();
const vmCam = new THREE.PerspectiveCamera(58, 1, 0.01, 10);
vmScene.add(vmCam);
vmScene.add(new THREE.HemisphereLight(0xe4edf0, 0x50463a, 1.0));
const vmSun = new THREE.DirectionalLight(0xfff0d8, 0.7); vmSun.position.set(1, 2, 1); vmScene.add(vmSun);

function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, settings.quality));
  renderer.setSize(w, h, false);
  camera.aspect = vmCam.aspect = w / h;
  camera.updateProjectionMatrix(); vmCam.updateProjectionMatrix();
  $('#rotate').classList.toggle('need', isTouch);
}
addEventListener('resize', resize);

function tex(w, h, draw, rep) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (rep) t.repeat.set(rep[0], rep[1]);
  t.anisotropy = 4;
  return t;
}
function grain(g, w, h, a) {
  const img = g.getImageData(0, 0, w, h), d = img.data;
  for (let i = 0; i < d.length; i += 4) { const n = (Math.random() - 0.5) * a; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
  g.putImageData(img, 0, 0);
}
const wallTex = tex(128, 216, (g, w, h) => {
  g.fillStyle = '#8a8d86'; g.fillRect(0, 0, w, h);
  grain(g, w, h, 22);
  g.fillStyle = 'rgba(0,0,0,.16)'; g.fillRect(0, h * 0.5 - 2, w, 3); g.fillRect(0, 0, 2, h);
  g.fillStyle = 'rgba(40,32,22,.35)'; g.fillRect(0, h * 0.86, w, h * 0.14);
  g.fillStyle = 'rgba(255,255,255,.06)'; g.fillRect(0, h * 0.5 + 1, w, 2);
  for (let i = 0; i < 5; i++) { g.fillStyle = 'rgba(30,28,24,.12)'; g.fillRect(rand(0, w), rand(h * 0.55, h * 0.85), rand(1, 3), rand(10, 40)); }
});
const floorTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#7d7768'; g.fillRect(0, 0, w, h);
  grain(g, w, h, 20);
  g.strokeStyle = 'rgba(30,26,20,.35)'; g.lineWidth = 2; g.strokeRect(1, 1, w - 2, h - 2);
  g.strokeStyle = 'rgba(30,26,20,.15)'; g.lineWidth = 1; g.beginPath(); g.moveTo(w / 2, 0); g.lineTo(w / 2, h); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
}, [MW, MH]);
const crateTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#9b6e3f'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 6; i++) { g.fillStyle = i % 2 ? 'rgba(0,0,0,.08)' : 'rgba(255,255,255,.05)'; g.fillRect(0, i * h / 6, w, h / 6); }
  grain(g, w, h, 18);
  g.strokeStyle = '#5b3d20'; g.lineWidth = 12; g.strokeRect(6, 6, w - 12, h - 12);
  g.lineWidth = 10; g.beginPath(); g.moveTo(10, 10); g.lineTo(w - 10, h - 10); g.stroke();
});
const contTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#d8d8d8'; g.fillRect(0, 0, w, h);
  for (let x = 0; x < w; x += 10) { g.fillStyle = 'rgba(0,0,0,.14)'; g.fillRect(x, 0, 4, h); g.fillStyle = 'rgba(255,255,255,.12)'; g.fillRect(x + 5, 0, 2, h); }
  g.fillStyle = 'rgba(0,0,0,.25)'; g.fillRect(0, 0, w, 6); g.fillRect(0, h - 6, w, 6);
  grain(g, w, h, 16);
});
const glowTex = tex(64, 64, (g, w, h) => {
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,250,220,1)'); gr.addColorStop(0.3, 'rgba(255,190,90,.85)'); gr.addColorStop(1, 'rgba(255,120,40,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
const blobTex = tex(64, 64, (g, w, h) => {
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(0,0,0,.5)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});

const levelMeshes = [];
(function buildLevel() {
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(MW * CELL, MH * CELL), new THREE.MeshLambertMaterial({ map: floorTex }));
  floor.rotation.x = -Math.PI / 2; floor.position.set(MW * CELL / 2, 0, MH * CELL / 2);
  scene.add(floor); levelMeshes.push(floor);
  const outer = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.MeshLambertMaterial({ color: 0x5f5a4d }));
  outer.rotation.x = -Math.PI / 2; outer.position.set(MW * CELL / 2, -0.02, MH * CELL / 2); scene.add(outer);
  const count = { '#': 0, C: 0, c: 0 };
  grid.forEach(r => r.forEach(ch => { if (ch in count) count[ch]++; }));
  const mk = (ch, mat, size) => {
    const m = new THREE.InstancedMesh(new THREE.BoxGeometry(size, TOPS[ch], size), mat, count[ch]);
    m.frustumCulled = false; scene.add(m); levelMeshes.push(m); return m;
  };
  const walls = mk('#', new THREE.MeshLambertMaterial({ map: wallTex }), CELL);
  const conts = mk('C', new THREE.MeshLambertMaterial({ map: contTex }), CELL - 0.16);
  const crates = mk('c', new THREE.MeshLambertMaterial({ map: crateTex }), CELL - 0.16);
  const idx = { '#': 0, C: 0, c: 0 }, m4 = new THREE.Matrix4(), col = new THREE.Color();
  const contCols = [0x3f6f86, 0x9c3f2c, 0x5c7a45, 0x8a7a3a];
  grid.forEach((row, z) => row.forEach((ch, x) => {
    if (!(ch in idx)) return;
    m4.makeTranslation((x + 0.5) * CELL, TOPS[ch] / 2, (z + 0.5) * CELL);
    const target = ch === '#' ? walls : ch === 'C' ? conts : crates;
    target.setMatrixAt(idx[ch], m4);
    if (ch === 'C') { col.setHex(contCols[(x * 7 + z * 3) % contCols.length]); target.setColorAt(idx[ch], col); }
    idx[ch]++;
  }));
  if (conts.instanceColor) conts.instanceColor.needsUpdate = true;
  const tape = tex(64, 64, (g, w, h) => { g.fillStyle = '#f2cb4c'; g.fillRect(0, 0, w, h); g.fillStyle = '#1b1d1c'; for (let i = -64; i < 128; i += 22) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i + 11, 0); g.lineTo(i + 11 - 64, 64); g.lineTo(i - 64, 64); g.fill(); } }, [6, 1]);
  for (const team of ['A', 'B']) {
    const xs = spawns[team].map(s => s.x), zs = spawns[team].map(s => s.z);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cz = (Math.min(...zs) + Math.max(...zs)) / 2;
    const w = Math.max(...xs) - Math.min(...xs) + CELL, d = Math.max(...zs) - Math.min(...zs) + CELL;
    for (const [px, pz, sw, sd] of [[cx, cz - d / 2, w, 0.25], [cx, cz + d / 2, w, 0.25], [cx - w / 2, cz, 0.25, d], [cx + w / 2, cz, 0.25, d]]) {
      const s = new THREE.Mesh(new THREE.PlaneGeometry(sw, sd), new THREE.MeshLambertMaterial({ map: tape }));
      s.rotation.x = -Math.PI / 2; s.position.set(px, 0.01, pz); scene.add(s);
    }
  }
})();
