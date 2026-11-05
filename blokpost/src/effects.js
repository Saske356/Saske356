'use strict';
/* ---------------- эффекты ---------------- */
const tracers = [], sparks = [], decals = [], flashes = [], puffs = [];
for (let i = 0; i < 16; i++) {
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
  const l = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffe2a0, transparent: true, opacity: 0.8 }));
  l.visible = false; l.frustumCulled = false; l.userData.t = 0; scene.add(l); tracers.push(l);
}
const sparkGeo = new THREE.BoxGeometry(0.035, 0.035, 0.035);
for (let i = 0; i < 60; i++) {
  const m = new THREE.Mesh(sparkGeo, new THREE.MeshBasicMaterial({ color: 0xffd27a })); m.visible = false; m.userData = { v: new THREE.Vector3(), t: 0 }; scene.add(m); sparks.push(m);
}
const decalGeo = new THREE.PlaneGeometry(0.1, 0.1);
const decalTex = tex(32, 32, (g, w, h) => {
  const gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  gr.addColorStop(0, 'rgba(10,9,8,1)'); gr.addColorStop(0.35, 'rgba(25,22,18,.9)'); gr.addColorStop(0.6, 'rgba(60,55,48,.45)'); gr.addColorStop(1, 'rgba(60,55,48,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
const decalMat = new THREE.MeshBasicMaterial({ map: decalTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4 });
const scorchMat = new THREE.MeshBasicMaterial({ map: decalTex, transparent: true, opacity: 0.85, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4 });
for (let i = 0; i < 80; i++) { const m = new THREE.Mesh(decalGeo, decalMat); m.visible = false; scene.add(m); decals.push(m); }
for (let i = 0; i < 10; i++) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  s.scale.set(0.5, 0.5, 0.5); s.visible = false; s.userData.t = 0; scene.add(s); flashes.push(s);
}
// мягкий клуб дыма/пыли (используется и дымовой гранатой)
const smokeTex = tex(64, 64, (g, w, h) => {
  for (let i = 0; i < 14; i++) {
    const x = rand(18, 46), y = rand(18, 46), r = rand(10, 20), gr = g.createRadialGradient(x, y, 0, x, y, r);
    gr.addColorStop(0, 'rgba(255,255,255,.35)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, w, h);
  }
});
for (let i = 0; i < 40; i++) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: smokeTex, transparent: true, depthWrite: false, opacity: 0 }));
  s.visible = false; s.userData = { v: new THREE.Vector3(), t: 0, life: 1, s0: 0.2, s1: 1, a: 0.5 }; scene.add(s); puffs.push(s);
}
let tracerI = 0, sparkI = 0, decalI = 0, flashI = 0, puffI = 0;
function tracer(a, b) {
  const l = tracers[tracerI++ % tracers.length], p = l.geometry.attributes.position.array;
  p[0] = a.x; p[1] = a.y; p[2] = a.z; p[3] = b.x; p[4] = b.y; p[5] = b.z;
  l.geometry.attributes.position.needsUpdate = true; l.visible = true; l.userData.t = 0.06;
}
function burst(pos, color, n, sp = 2) {
  for (let i = 0; i < n; i++) {
    const s = sparks[sparkI++ % sparks.length];
    s.position.copy(pos); s.material.color.setHex(color); s.visible = true;
    s.userData.v.set(rand(-sp, sp), rand(0.5, 1.5 * sp), rand(-sp, sp)); s.userData.t = rand(0.18, 0.35);
  }
}
// клуб: цвет, размер от s0 до s1, время жизни, начальная прозрачность, скорость
function puff(pos, color, s0, s1, life, a, vx = 0, vy = 0.4, vz = 0) {
  const s = puffs[puffI++ % puffs.length], d = s.userData;
  s.position.copy(pos); s.material.color.setHex(color); s.material.rotation = rand(0, 6.3);
  d.v.set(vx, vy, vz); d.t = 0; d.life = life; d.s0 = s0; d.s1 = s1; d.a = a; s.visible = true; s.scale.setScalar(s0); s.material.opacity = a;
}
const _n = new THREE.Vector3();
function decal(hit, size) {
  if (!hit.face) return;
  const d = decals[decalI++ % decals.length];
  _n.copy(hit.face.normal).transformDirection(hit.object.matrixWorld);
  d.position.copy(hit.point).addScaledVector(_n, 0.01);
  d.lookAt(hit.point.x + _n.x, hit.point.y + _n.y, hit.point.z + _n.z);
  d.material = decalMat; d.scale.setScalar(size || 1); d.rotation.z = rand(0, 6.3);
  d.visible = true;
}
// след на полу (взрыв)
function scorch(pos, size) {
  const d = decals[decalI++ % decals.length];
  d.position.set(pos.x, pos.y + 0.012, pos.z); d.rotation.set(-Math.PI / 2, 0, rand(0, 6.3));
  d.material = scorchMat; d.scale.setScalar(size * 10); d.visible = true;
}
// след от пули с облачком пыли и искрами по материалу
function impactFx(hit, dir, mat) {
  decal(hit, mat === 'metal' ? 0.8 : 1);
  _n.copy(hit.face ? hit.face.normal : _up).transformDirection(hit.object.matrixWorld);
  const c = mat === 'wood' ? 0x9a7a52 : mat === 'metal' ? 0x9a9a98 : 0xb0a896;
  puff(hit.point, c, 0.12, 0.55, 0.5, 0.55, _n.x * 0.6, 0.3 + _n.y * 0.6, _n.z * 0.6);
  burst(hit.point, mat === 'metal' ? 0xffe0a0 : mat === 'wood' ? 0x6a4a2a : 0xd8d0b8, mat === 'metal' ? 4 : 2);
}
function bloodFx(p, dir) {
  burst(p, 0x8a1f16, 5);
  puff(p, 0x7a1810, 0.1, 0.45, 0.35, 0.6, dir ? dir.x * 0.8 : 0, 0.1, dir ? dir.z * 0.8 : 0);
}
function worldFlash(pos, size, t) { const s = flashes[flashI++ % flashes.length]; s.position.copy(pos); s.visible = true; s.userData.t = t || 0.05; s.userData.t0 = t || 0.05; s.scale.setScalar(size || 0.5); s.userData.size = size || 0.5; }
function explosionFx(pos) {
  worldFlash(pos.clone().add(V3(0, 0.4, 0)), 5, 0.18);
  for (let i = 0; i < 7; i++) puff(pos.clone().add(V3(rand(-0.4, 0.4), rand(0.1, 0.6), rand(-0.4, 0.4))), i < 3 ? 0xffa050 : 0x3a3530, 0.6, rand(2.4, 3.4), rand(0.9, 1.6), i < 3 ? 0.7 : 0.8, rand(-1, 1), rand(0.6, 1.6), rand(-1, 1));
  burst(pos.clone().add(V3(0, 0.2, 0)), 0xffc070, 14, 6);
  burst(pos.clone().add(V3(0, 0.2, 0)), 0x3a3228, 8, 4);
  scorch(pos, 1.8);
}
function clearEffects() { [...tracers, ...sparks, ...decals, ...flashes, ...puffs].forEach(o => o.visible = false); }
function updateEffects(dt) {
  for (const l of tracers) if (l.visible) { l.userData.t -= dt; if (l.userData.t <= 0) l.visible = false; }
  for (const f of flashes) if (f.visible) {
    f.userData.t -= dt; if (f.userData.t <= 0) { f.visible = false; continue; }
    if (f.userData.t0 > 0.1) f.scale.setScalar(f.userData.size * (0.6 + f.userData.t / f.userData.t0 * 0.6));
  }
  for (const s of sparks) if (s.visible) {
    s.userData.t -= dt; if (s.userData.t <= 0) { s.visible = false; continue; }
    s.userData.v.y -= 12 * dt; s.position.addScaledVector(s.userData.v, dt);
  }
  for (const s of puffs) if (s.visible) {
    const d = s.userData; d.t += dt; const k = d.t / d.life; if (k >= 1) { s.visible = false; continue; }
    s.position.addScaledVector(d.v, dt); d.v.multiplyScalar(Math.exp(-dt * 2));
    s.scale.setScalar(d.s0 + (d.s1 - d.s0) * (1 - Math.pow(1 - k, 2))); s.material.opacity = d.a * (1 - k);
  }
  if (typeof updateShells === 'function') updateShells(dt);
}
