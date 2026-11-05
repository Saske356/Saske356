'use strict';
/* ---------------- вьюмодель: руки и оружие от первого лица ---------------- */
// VM[key] = { g — корень (позиция у бедра/в прицеле), gun — шарнир анимаций, body/mag/pump/bolt — группы деталей по видам материала,
//             right/left — руки, flash — вспышка, hip/ads — позиции, type: 'gun' | 'knife' | 'nade' }
const VM = {};
function vmStyle() {
  const u = typeof player !== 'undefined' && player ? player : null;
  const S = resolveStyle(u ? u.team : 'A', u ? u.skin : null);
  return { S, L: resolveLook(S, 0) };
}
function vmArmsGeo(k) {
  const G = GUNS[k], w = WEAPONS[k], { S, L } = vmStyle();
  const o = { seg: 10, l1: 0.44, l2: 0.31 }, ho = { seg: 6 };
  const rs = V3(0.24, -0.36, 0.6), ls = V3(-0.32, -0.38, 0.5);
  let R, Lh, rp = V3(0.5, -0.6, 0.3), lp = V3(-0.6, -0.6, 0.1);
  if (w.hold === 'knife') {
    R = handParts(S, V3(0, 0, 0), V3(0, 0, -1), V3(1, 0, 0), 1, { ...ho, rx: 0.012, rz: 0.016 });
    Lh = null;
  } else if (w.hold === 'grenade') {
    R = handParts(S, V3(0, -0.01, 0), V3(0, 1, 0), V3(1, 0, 0.3), 1, { ...ho, rx: 0.028, rz: 0.028 });
    Lh = handParts(S, V3(-0.1, -0.02, 0.02), V3(0.3, 1, -0.2), V3(-1, 0, 0.3), -1, { ...ho, open: 0.45 });
  } else if (w.hold === 'pistol') {
    R = handParts(S, V3(0, -0.005, 0.0), V3(0, 0.97, -0.24), V3(1, 0, 0), 1, ho);
    Lh = handParts(S, V3(-0.006, -0.045, 0.0), V3(0, 0.97, -0.24), V3(-1, -0.15, 0), -1, { ...ho, rx: 0.03, rz: 0.035 });
    lp = V3(-0.6, -0.8, 0.2);
  } else {
    R = handParts(S, V3(0, -0.005, 0.0), V3(0, 0.97, -0.24), V3(1, 0, 0), 1, ho);
    const fH = V3(0, G.foreY, -G.fore);
    Lh = G.foreGrip ? handParts(S, fH, V3(0, 1, 0.2), V3(-1, 0, 0.2), -1, ho)
      : handParts(S, fH, V3(0, 0, -1), V3(-0.65, -0.76, 0), -1, { ...ho, rx: G.foreR, rz: G.foreR });
    lp = V3(-0.7, -0.7, -0.1);
  }
  return {
    r: mergeUV(armParts(S, L, rs, R, rp, { ...o, side: 1 }), { uvScale: 4 }),
    l: Lh ? mergeUV(armParts(S, L, ls, Lh, lp, { ...o, side: -1, watch: true }), { uvScale: 4 }) : null,
  };
}
function buildVM(k) {
  const G = GUNS[k], w = WEAPONS[k];
  const g = new THREE.Group(), gun = new THREE.Group(); g.add(gun);
  const body = gunGroup(k, G.parts.body); gun.add(body);
  const mag = G.parts.mag ? gunGroup(k, G.parts.mag) : null; if (mag) gun.add(mag);
  const pump = G.parts.pump ? gunGroup(k, G.parts.pump) : null; if (pump) gun.add(pump);
  const bolt = G.parts.bolt ? gunGroup(k, G.parts.bolt) : null; if (bolt) { bolt.position.copy(G.pivot); gun.add(bolt); }
  const a = vmArmsGeo(k);
  const right = new THREE.Mesh(a.r, charMat); gun.add(right);
  const left = new THREE.Mesh(a.l || new THREE.BufferGeometry(), charMat); left.visible = !!a.l;
  (pump || gun).add(left);
  const flash = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  flash.position.copy(G.muzzle).add(V3(0, 0, -0.035)); flash.scale.setScalar(w.hold === 'pistol' ? 0.16 : 0.24); flash.visible = false;
  if (!w.melee && !w.grenade && k !== 'smg') gun.add(flash); else flash.visible = false;
  const type = w.melee ? 'knife' : w.grenade ? 'nade' : 'gun';
  if (type === 'knife') { body.rotation.set(0, 0, 0); }
  g.visible = false; vmCam.add(g);
  const hip = type === 'knife' ? V3(0.2, -0.2, -0.36) : type === 'nade' ? V3(0.17, -0.16, -0.34) : w.hold === 'pistol' ? V3(0.13, -0.14, -0.38) : V3(0.16, -0.175, -0.44);
  VM[k] = { g, gun, body, mag, pump, bolt, right, left, flash, flashT: 0, type, hip,
    ads: V3(0, -G.sight, w.hold === 'pistol' ? -0.34 : -0.27),
    magHome: V3(0, 0, 0), leftHome: V3(0, 0, 0) };
}
for (const k in GUNS) buildVM(k);
// пересобрать руки (после смены скина игрока) и материалы оружия
function refreshViewmodel() {
  for (const k in VM) {
    const v = VM[k], a = vmArmsGeo(k);
    v.right.geometry.dispose(); v.right.geometry = a.r;
    if (a.l) { v.left.geometry.dispose(); v.left.geometry = a.l; }
  }
  refreshGunMaterials();
}
// гильзы: вылетают из окна выброса вправо-вверх
const vmShells = [];
(function () {
  const mat = new THREE.MeshStandardMaterial({ color: 0xc9a24e, metalness: 0.85, roughness: 0.3, envMap: gunEnv });
  const matS = new THREE.MeshStandardMaterial({ color: 0xa2261c, metalness: 0.1, roughness: 0.5, envMap: gunEnv });
  const geo = new THREE.CylinderGeometry(0.0045, 0.0045, 0.022, 7); geo.rotateX(Math.PI / 2);
  const geoS = new THREE.CylinderGeometry(0.009, 0.009, 0.05, 8); geoS.rotateX(Math.PI / 2);
  for (let i = 0; i < 10; i++) {
    const m = new THREE.Mesh(geo, mat); m.visible = false; m.userData = { v: new THREE.Vector3(), r: new THREE.Vector3(), t: 0, geo, geoS, mat, matS };
    vmCam.add(m); vmShells.push(m);
  }
})();
let shellI = 0;
const _sv = new THREE.Vector3();
function ejectShell(k) {
  const v = VM[k], G = GUNS[k]; if (!v || !G.eject) return;
  const s = vmShells[shellI++ % vmShells.length], d = s.userData, shot = G.shellK === 'shot';
  s.geometry = shot ? d.geoS : d.geo; s.material = shot ? d.matS : d.mat;
  v.g.updateMatrixWorld(true);
  _sv.copy(G.eject); v.gun.localToWorld(_sv); vmCam.worldToLocal(_sv);
  s.position.copy(_sv); s.rotation.set(rand(0, 3), rand(0, 3), 0);
  d.v.set(rand(0.9, 1.4), rand(0.9, 1.5), rand(-0.1, 0.25)).multiplyScalar(G.shell > 1.2 ? 0.8 : 1);
  d.r.set(rand(-20, 20), rand(-30, 30), rand(-10, 10)); d.t = 0.55; s.visible = true;
}
function updateShells(dt) {
  for (const s of vmShells) if (s.visible) {
    const d = s.userData; d.t -= dt; if (d.t <= 0) { s.visible = false; continue; }
    d.v.y -= 6 * dt; s.position.addScaledVector(d.v, dt);
    s.rotation.x += d.r.x * dt; s.rotation.y += d.r.y * dt; s.rotation.z += d.r.z * dt;
  }
}
