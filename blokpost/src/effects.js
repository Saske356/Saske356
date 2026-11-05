'use strict';
/* ---------------- эффекты ---------------- */
const tracers = [], sparks = [], decals = [], flashes = [];
for (let i = 0; i < 16; i++) {
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
  const l = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffe2a0, transparent: true, opacity: 0.8 }));
  l.visible = false; l.frustumCulled = false; l.userData.t = 0; scene.add(l); tracers.push(l);
}
const sparkGeo = new THREE.BoxGeometry(0.04, 0.04, 0.04);
for (let i = 0; i < 50; i++) {
  const m = new THREE.Mesh(sparkGeo, new THREE.MeshBasicMaterial({ color: 0xffd27a })); m.visible = false; m.userData = { v: new THREE.Vector3(), t: 0 }; scene.add(m); sparks.push(m);
}
const decalGeo = new THREE.PlaneGeometry(0.1, 0.1), decalMat = new THREE.MeshBasicMaterial({ color: 0x1b1a17, transparent: true, opacity: 0.8, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4 });
for (let i = 0; i < 80; i++) { const m = new THREE.Mesh(decalGeo, decalMat); m.visible = false; scene.add(m); decals.push(m); }
for (let i = 0; i < 10; i++) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  s.scale.set(0.5, 0.5, 0.5); s.visible = false; s.userData.t = 0; scene.add(s); flashes.push(s);
}
let tracerI = 0, sparkI = 0, decalI = 0, flashI = 0;
function tracer(a, b) {
  const l = tracers[tracerI++ % tracers.length], p = l.geometry.attributes.position.array;
  p[0] = a.x; p[1] = a.y; p[2] = a.z; p[3] = b.x; p[4] = b.y; p[5] = b.z;
  l.geometry.attributes.position.needsUpdate = true; l.visible = true; l.userData.t = 0.06;
}
function burst(pos, color, n) {
  for (let i = 0; i < n; i++) {
    const s = sparks[sparkI++ % sparks.length];
    s.position.copy(pos); s.material.color.setHex(color); s.visible = true;
    s.userData.v.set(rand(-2, 2), rand(0.5, 3), rand(-2, 2)); s.userData.t = rand(0.18, 0.35);
  }
}
const _n = new THREE.Vector3();
function decal(hit) {
  if (!hit.face) return;
  const d = decals[decalI++ % decals.length];
  _n.copy(hit.face.normal).transformDirection(hit.object.matrixWorld);
  d.position.copy(hit.point).addScaledVector(_n, 0.01);
  d.lookAt(hit.point.x + _n.x, hit.point.y + _n.y, hit.point.z + _n.z);
  d.visible = true;
}
function worldFlash(pos) { const s = flashes[flashI++ % flashes.length]; s.position.copy(pos); s.visible = true; s.userData.t = 0.05; }
function clearEffects() { [...tracers, ...sparks, ...decals, ...flashes].forEach(o => o.visible = false); }
function updateEffects(dt) {
  for (const l of tracers) if (l.visible) { l.userData.t -= dt; if (l.userData.t <= 0) l.visible = false; }
  for (const f of flashes) if (f.visible) { f.userData.t -= dt; if (f.userData.t <= 0) f.visible = false; }
  for (const s of sparks) if (s.visible) {
    s.userData.t -= dt; if (s.userData.t <= 0) { s.visible = false; continue; }
    s.userData.v.y -= 12 * dt; s.position.addScaledVector(s.userData.v, dt);
  }
}
