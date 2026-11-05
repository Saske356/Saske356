'use strict';
/* ---------------- вьюмодель: руки и оружие от первого лица ---------------- */
const VM = {};
for (const k in GUNS) {
  const G = GUNS[k], w = WEAPONS[k], S = STYLE.A;
  const g = new THREE.Group();
  g.add(new THREE.Mesh(G.body, gunMat));
  const mag = G.mag ? new THREE.Mesh(G.mag, gunMat) : null; if (mag) g.add(mag);
  const pump = G.pump ? new THREE.Mesh(G.pump, gunMat) : null; if (pump) g.add(pump);
  const arms = w.hold === 'pistol'
    ? armParts(S, V3(0.2, -0.38, 0.6), V3(0.12, -0.17, 0.22), V3(0, -0.005, 0.02), V3(-0.28, -0.4, 0.55), V3(-0.18, -0.2, 0.22), V3(-0.035, -0.03, 0.025))
    : armParts(S, V3(0.24, -0.38, 0.62), V3(0.14, -0.17, 0.22), V3(0, -0.005, 0.02), V3(-0.32, -0.4, 0.45), V3(-0.2, -0.17, -G.fore + 0.28), V3(0, -0.012, -G.fore));
  const right = new THREE.Mesh(merge(arms.slice(0, 5)), charMat); g.add(right);
  const left = new THREE.Mesh(merge(arms.slice(5)), charMat);
  (pump || g).add(left);
  if (pump) left.position.set(0, 0, 0);
  const flash = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  flash.position.copy(G.muzzle).add(V3(0, 0, -0.03)); flash.scale.setScalar(w.hold === 'pistol' ? 0.16 : 0.24); flash.visible = false; g.add(flash);
  g.visible = false; vmCam.add(g);
  VM[k] = { g, mag, pump, flash, flashT: 0,
    hip: w.hold === 'pistol' ? V3(0.13, -0.14, -0.38) : V3(0.16, -0.175, -0.44),
    ads: V3(0, -G.sight, w.hold === 'pistol' ? -0.34 : -0.27) };
}
