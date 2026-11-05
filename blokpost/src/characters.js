'use strict';
/* ---------------- бойцы: модели ---------------- */
const STYLE = {
  A: { uni: 0x4a5c69, uni2: 0x3e4e5a, vest: 0x2c373e, pouch: 0x34414a, helm: 0x3a4851, acc: 0x6cc0d3, face: 0x24282c, glove: 0x262829, boot: 0x2a2723, pad: 0x2f363b, lens: 0x2e4a55, headgear: 'helmet' },
  B: { uni: 0x7a6a50, uni2: 0x6a5b44, vest: 0x56442f, pouch: 0x62503a, helm: 0x5b4934, acc: 0xea7440, face: 0xb09a78, glove: 0x3a3025, boot: 0x3b3024, pad: 0x4a3c2c, lens: 0x4a2f22, headgear: 'cap' },
};
const charMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0.02 });
const hitMat = new THREE.MeshBasicMaterial({ visible: false });
const charGeo = {};
function pelvisGeo(S) {
  return merge([
    P(rbox(0.34, 0.22, 0.22, 0.07), S.uni2, [0, 0, 0]),
    P(rbox(0.37, 0.06, 0.24, 0.02), 0x1f1f1c, [0, 0.08, 0]),
    P(rbox(0.05, 0.05, 0.02, 0.005), 0x8a8a80, [0, 0.08, -0.125]),
    P(rbox(0.12, 0.09, 0.06, 0.02), S.pouch, [-0.1, 0.05, 0.13]),
    P(rbox(0.1, 0.09, 0.06, 0.02), S.pouch, [0.1, 0.05, 0.13]),
    P(rbox(0.07, 0.17, 0.09, 0.02), 0x1f2021, [0.21, -0.07, 0.0]),
  ]);
}
function thighGeo(S, side) {
  return merge([
    P(limbGeo(V3(0, 0.02, 0), V3(0, -0.42, 0.0), 0.088), S.uni),
    P(rbox(0.05, 0.13, 0.13, 0.02), S.uni2, [side * 0.085, -0.22, 0]),
  ]);
}
function shinGeo(S) {
  return merge([
    P(rbox(0.12, 0.12, 0.07, 0.03), S.pad, [0, -0.01, -0.07]),
    P(limbGeo(V3(0, 0, 0), V3(0, -0.38, 0.01), 0.072), S.uni),
    P(rbox(0.13, 0.15, 0.16, 0.04), S.boot, [0, -0.43, 0.0]),
    P(rbox(0.125, 0.07, 0.27, 0.03), S.boot, [0, -0.475, -0.045]),
    P(rbox(0.13, 0.02, 0.28, 0.008), 0x141412, [0, -0.505, -0.045]),
  ]);
}
function chestGeo(S) {
  return merge([
    P(rbox(0.3, 0.22, 0.2, 0.08), S.uni, [0, 0.08, 0]),
    P(rbox(0.42, 0.36, 0.25, 0.1), S.uni, [0, 0.3, 0]),
    P(rbox(0.37, 0.33, 0.07, 0.025), S.vest, [0, 0.29, -0.12]),
    P(rbox(0.37, 0.33, 0.06, 0.025), S.vest, [0, 0.3, 0.12]),
    P(rbox(0.06, 0.05, 0.25, 0.02), S.vest, [0.15, 0.47, 0]), P(rbox(0.06, 0.05, 0.25, 0.02), S.vest, [-0.15, 0.47, 0]),
    P(rbox(0.07, 0.11, 0.055, 0.015), S.pouch, [-0.09, 0.19, -0.175]),
    P(rbox(0.07, 0.11, 0.055, 0.015), S.pouch, [0, 0.19, -0.175]),
    P(rbox(0.07, 0.11, 0.055, 0.015), S.pouch, [0.09, 0.19, -0.175]),
    P(rbox(0.1, 0.06, 0.04, 0.012), S.pouch, [0.1, 0.36, -0.165]),
    P(rbox(0.06, 0.05, 0.01, 0.004), S.acc, [-0.1, 0.38, -0.158]),
    P(rbox(0.07, 0.15, 0.05, 0.015), 0x222321, [-0.12, 0.33, 0.165]),
    P(limbGeo(V3(-0.12, 0.4, 0.17), V3(-0.12, 0.58, 0.17), 0.006, 4), 0x111111),
    P(rbox(0.16, 0.2, 0.08, 0.03), S.pouch, [0.05, 0.27, 0.17]),
    P(new THREE.SphereGeometry(0.088, 12, 10), S.uni, [0.215, 0.42, 0]),
    P(new THREE.SphereGeometry(0.088, 12, 10), S.uni, [-0.215, 0.42, 0]),
    P(new THREE.CylinderGeometry(0.055, 0.06, 0.12, 10), S.face, [0, 0.53, 0]),
    P(rbox(0.24, 0.06, 0.2, 0.025), S.vest, [0, 0.5, 0.0]),
  ]);
}
function headGeo(S) {
  const parts = [
    P(new THREE.SphereGeometry(0.105, 16, 12), S.face, [0, 0.04, 0], null, [1, 1.12, 1.06]),
    P(rbox(0.19, 0.06, 0.06, 0.025), 0x15171a, [0, 0.055, -0.088]),
    P(rbox(0.07, 0.035, 0.012, 0.01), S.lens, [-0.045, 0.057, -0.12]),
    P(rbox(0.07, 0.035, 0.012, 0.01), S.lens, [0.045, 0.057, -0.12]),
    P(rbox(0.09, 0.07, 0.06, 0.02), S.face, [0, -0.04, -0.07]),
  ];
  if (S.headgear === 'helmet') {
    parts.push(
      P(new THREE.SphereGeometry(0.135, 18, 10, 0, Math.PI * 2, 0, Math.PI * 0.52), S.helm, [0, 0.07, 0.005]),
      P(new THREE.CylinderGeometry(0.137, 0.139, 0.018, 18), S.helm, [0, 0.07, 0.005]),
      P(rbox(0.06, 0.045, 0.025, 0.008), 0x1e2022, [0, 0.15, -0.125]),
      P(rbox(0.012, 0.03, 0.12, 0.004), 0x23262a, [0.135, 0.11, 0.0]), P(rbox(0.012, 0.03, 0.12, 0.004), 0x23262a, [-0.135, 0.11, 0.0]),
      P(new THREE.CylinderGeometry(0.042, 0.042, 0.035, 12), 0x26292c, [0.12, 0.02, 0.01], [0, 0, Math.PI / 2]),
      P(new THREE.CylinderGeometry(0.042, 0.042, 0.035, 12), 0x26292c, [-0.12, 0.02, 0.01], [0, 0, Math.PI / 2]),
      P(rbox(0.055, 0.012, 0.055, 0.004), S.acc, [0, 0.205, 0.02]),
    );
  } else {
    parts.push(
      P(new THREE.CylinderGeometry(0.115, 0.122, 0.085, 16), S.helm, [0, 0.135, 0.005]),
      P(new THREE.SphereGeometry(0.116, 16, 6, 0, Math.PI * 2, 0, Math.PI * 0.35), S.helm, [0, 0.15, 0.005]),
      P(rbox(0.17, 0.014, 0.1, 0.006), S.helm, [0, 0.1, -0.135], [-0.15, 0, 0]),
      P(rbox(0.05, 0.035, 0.008, 0.004), S.acc, [0, 0.145, -0.122]),
      P(rbox(0.22, 0.1, 0.18, 0.04), S.face, [0, -0.07, 0.01]),
    );
  }
  return merge(parts);
}
// руки от плеча до кисти: плечо → локоть → кисть
function armParts(S, rs, re, rh, ls, le, lh) {
  const one = (s, e, h) => [
    P(limbGeo(s, e, 0.058), S.uni), P(limbGeo(e, h, 0.047), S.uni),
    P(limbGeo(s.clone().lerp(e, 0.35), s.clone().lerp(e, 0.5), 0.062), S.acc),
    P(limbGeo(e.clone().lerp(h, 0.72), e.clone().lerp(h, 0.86), 0.051), S.glove),
    P(rbox(0.065, 0.085, 0.1, 0.028), S.glove, [h.x, h.y, h.z]),
  ];
  return [...one(rs, re, rh), ...one(ls, le, lh)];
}
const HOLD = { rifle: V3(0.09, 0.25, -0.24), pistol: V3(0.04, 0.32, -0.44) };
function botArms(team, key) {
  const id = team + key; if (charGeo[id]) return charGeo[id];
  const S = STYLE[team], w = WEAPONS[key], G = HOLD[w.hold], fore = GUNS[key].fore;
  const rs = V3(0.215, 0.42, 0), ls = V3(-0.215, 0.42, 0);
  return charGeo[id] = w.hold === 'pistol'
    ? merge(armParts(S, rs, V3(0.2, 0.28, -0.2), G.clone().add(V3(0, -0.01, 0.02)), ls, V3(-0.15, 0.27, -0.22), G.clone().add(V3(-0.04, -0.02, 0.03))))
    : merge(armParts(S, rs, V3(0.25, 0.14, -0.04), G.clone().add(V3(0, -0.01, 0.02)), ls, V3(-0.13, 0.15, -0.28), G.clone().add(V3(0, 0.0, -fore))));
}
function makeBody(team) {
  const S = STYLE[team];
  if (!charGeo['pelvis' + team]) {
    charGeo['pelvis' + team] = pelvisGeo(S); charGeo['thighL' + team] = thighGeo(S, -1); charGeo['thighR' + team] = thighGeo(S, 1);
    charGeo['shin' + team] = shinGeo(S); charGeo['chest' + team] = chestGeo(S); charGeo['head' + team] = headGeo(S);
  }
  const root = new THREE.Group(); root.rotation.order = 'YXZ';
  const hips = new THREE.Group(); hips.position.y = 0.98; root.add(hips);
  hips.add(new THREE.Mesh(charGeo['pelvis' + team], charMat));
  const hit = [];
  const hb = (parent, w, h, d, p, part) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), hitMat); m.position.set(p[0], p[1], p[2]); m.userData.part = part; parent.add(m); hit.push(m); };
  hb(hips, 0.38, 0.28, 0.28, [0, 0, 0], 'body');
  const thighs = [], knees = [];
  for (const side of [-1, 1]) {
    const th = new THREE.Group(); th.position.set(side * 0.1, -0.06, 0); hips.add(th);
    th.add(new THREE.Mesh(charGeo[(side < 0 ? 'thighL' : 'thighR') + team], charMat));
    hb(th, 0.19, 0.46, 0.2, [0, -0.2, 0], 'legs');
    const kn = new THREE.Group(); kn.position.y = -0.44; th.add(kn);
    kn.add(new THREE.Mesh(charGeo['shin' + team], charMat));
    hb(kn, 0.16, 0.5, 0.22, [0, -0.25, -0.02], 'legs');
    thighs.push(th); knees.push(kn);
  }
  const chest = new THREE.Group(); chest.position.y = 0.1; hips.add(chest);
  chest.add(new THREE.Mesh(charGeo['chest' + team], charMat));
  hb(chest, 0.46, 0.56, 0.32, [0, 0.28, 0], 'body');
  const arms = new THREE.Mesh(botArms(team, 'pistol'), charMat); chest.add(arms);
  const gun = new THREE.Mesh(GUNS.pistol.full, gunMat); chest.add(gun);
  const muzzle = new THREE.Object3D(); gun.add(muzzle);
  const head = new THREE.Group(); head.position.y = 0.6; chest.add(head);
  head.add(new THREE.Mesh(charGeo['head' + team], charMat));
  hb(head, 0.27, 0.32, 0.29, [0, 0.06, 0], 'head');
  const blob = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }));
  blob.rotation.x = -Math.PI / 2; scene.add(blob);
  scene.add(root);
  return { root, hips, chest, head, thighs, knees, arms, gun, muzzle, hit, blob };
}
function setBotWeapon(u) {
  const m = u.mesh;
  m.arms.geometry = botArms(u.team, u.cur);
  m.gun.geometry = GUNS[u.cur].full; m.gun.position.copy(HOLD[WEAPONS[u.cur].hold]);
  m.muzzle.position.copy(GUNS[u.cur].muzzle);
}
// поза и анимация бойца по его состоянию (скорость, прицел, присед и т.д.)
function syncBotMesh(b, dt, spd) {
  const m = b.mesh;
  m.root.position.set(b.pos.x, b.pos.y, b.pos.z);
  m.root.rotation.y = b.yaw; m.root.rotation.x = 0;
  m.blob.position.set(b.pos.x, b.pos.y + 0.015, b.pos.z);
  // походка: отдельно вперёд/назад и боком
  const fwd = spd > 0.1 ? (b.vx * -Math.sin(b.yaw) + b.vz * -Math.cos(b.yaw)) / spd : 1;
  const amt = Math.min(1, spd / 4);
  b.walkPhase += dt * spd * 2.3;
  const s = Math.sin(b.walkPhase) * amt * (fwd < -0.3 ? -1 : 1);
  const fb = Math.abs(fwd) >= 0.5 ? 1 : 0.4;
  m.thighs[0].rotation.x = s * 0.6 * fb; m.thighs[1].rotation.x = -s * 0.6 * fb;
  const side = Math.abs(fwd) < 0.5 ? amt : 0;
  m.thighs[0].rotation.z = Math.max(0, Math.sin(b.walkPhase)) * -0.22 * side; m.thighs[1].rotation.z = Math.max(0, -Math.sin(b.walkPhase)) * 0.22 * side;
  m.knees[0].rotation.x = -(0.08 + Math.max(0, -Math.sin(b.walkPhase)) * 0.9) * amt;
  m.knees[1].rotation.x = -(0.08 + Math.max(0, Math.sin(b.walkPhase)) * 0.9) * amt;
  m.hips.position.y = 0.98 - Math.abs(Math.cos(b.walkPhase)) * 0.035 * amt - (b.targetVisible ? 0.04 : 0);
  const breathe = Math.sin(gt * 2 + b.pos.x) * 0.012;
  m.chest.rotation.x = b.aimPitch * 0.8 + breathe + amt * 0.08;
  m.chest.rotation.y = Math.sin(b.walkPhase) * 0.05 * amt;
  m.head.rotation.x = b.aimPitch * 0.2 - amt * 0.06;
  m.root.visible = !(b.protT > 0 && Math.floor(gt * 10) % 2 === 0);
}
