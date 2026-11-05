'use strict';
/* ---------------- бойцы: модели ---------------- */
// Палитра команды. Скины (src/skins.js) задают CHAR_SKINS = { id: { ...частичная палитра, headgear?, extras?: [...] } };
// extras: 'backpack' | 'balaclava' | 'goggles' | 'glasses' | 'rolled' | 'beard' | 'headset' | 'cap' | 'beanie' | 'bandana'.
const STYLE = {
  A: { uni: 0x4a5c69, uni2: 0x3e4e5a, vest: 0x2c373e, pouch: 0x34414a, helm: 0x3a4851, cover: 0x4a5a62, acc: 0x6cc0d3, face: 0x24282c, glove: 0x262829, boot: 0x2a2723, pad: 0x2f363b, lens: 0x2e4a55, strap: 0x1f2528, bala: 0x25292d, hair: 0x2a221c, headgear: 'helmet', tones: [0xc99f84, 0xa77b5d, 0x7d5741] },
  B: { uni: 0x7a6a50, uni2: 0x6a5b44, vest: 0x56442f, pouch: 0x62503a, helm: 0x5b4934, cover: 0x76654a, acc: 0xea7440, face: 0xb09a78, glove: 0x3a3025, boot: 0x3b3024, pad: 0x4a3c2c, lens: 0x4a2f22, strap: 0x3c3022, bala: 0x3d362b, hair: 0x231a14, headgear: 'cap', tones: [0xd0a888, 0xb08566, 0x8a6248] },
};
// Варианты внешности внутри команды (выбираются по очереди при создании бойца)
const LOOKS = [
  { hat: 'cap', face: 'skin', eyes: 'glasses', pack: false, rolled: false, tone: 0, beard: false, cover: true },
  { hat: 'beanie', face: 'bala', eyes: 'goggles', pack: true, rolled: false, tone: 1, beard: false, cover: false },
  { hat: 'headset', face: 'skin', eyes: 'none', pack: false, rolled: true, tone: 2, beard: true, cover: true },
  { hat: 'bandana', face: 'skin', eyes: 'goggles', pack: true, rolled: false, tone: 1, beard: false, cover: false },
  { hat: 'cap', face: 'bala', eyes: 'none', pack: false, rolled: true, tone: 0, beard: false, cover: true },
];
const fabricTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#e6e6e6'; g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y += 2) { g.fillStyle = 'rgba(0,0,0,.05)'; g.fillRect(0, y, w, 1); }
  for (let x = 0; x < w; x += 2) { g.fillStyle = 'rgba(255,255,255,.04)'; g.fillRect(x, 0, 1, h); }
  grain(g, w, h, 26);
});
const charMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, metalness: 0.02, map: fabricTex });
const hitMat = new THREE.MeshBasicMaterial({ visible: false });
const charGeo = {};
const BOT_GUN_SCALE = 0.8;

function resolveStyle(team, skinId) {
  const S = Object.assign({}, STYLE[team]);
  let sk = null;
  if (skinId != null && typeof CHAR_SKINS === 'object' && CHAR_SKINS) sk = CHAR_SKINS[skinId] || null;
  if (sk) Object.assign(S, sk);
  S.extras = (sk && sk.extras) || [];
  return S;
}
function resolveLook(S, li) {
  const L = Object.assign({}, LOOKS[li % LOOKS.length]);
  const ex = S.extras;
  if (ex.includes('backpack')) L.pack = true;
  if (ex.includes('balaclava')) L.face = 'bala';
  if (ex.includes('goggles')) L.eyes = 'goggles'; else if (ex.includes('glasses')) L.eyes = 'glasses';
  if (ex.includes('rolled')) L.rolled = true;
  if (ex.includes('beard')) L.beard = true;
  for (const h of ['headset', 'cap', 'beanie', 'bandana']) if (ex.includes(h)) L.hat = h;
  return L;
}
const skinTone = (S, L) => L.face === 'bala' ? S.bala : (S.tones ? S.tones[L.tone % S.tones.length] : S.face);

/* ---------------- заготовки ---------------- */
// конус-конечность от a (радиус r0) к b (r1) с шаром в суставе a
function tlimb(a, b, r0, r1, seg = 8, joint = true) {
  const len = Math.max(0.001, a.distanceTo(b));
  const g = new THREE.CylinderGeometry(r1, r0, len, seg, 1, true);
  const q = new THREE.Quaternion().setFromUnitVectors(_up, b.clone().sub(a).normalize());
  g.applyQuaternion(q); g.translate((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
  const out = [g];
  if (joint) { const s = new THREE.SphereGeometry(r0, seg, Math.max(4, seg >> 1)); s.translate(a.x, a.y, a.z); out.push(s); }
  return out;
}
const PL = (gs, c) => gs.map(g => ({ g, c }));
// двухзвенная ИК: локоть по направлению pole
function ik(S, H, l1, l2, pole) {
  const d = H.clone().sub(S); const L = Math.min(d.length(), l1 + l2 - 1e-3); const dir = d.normalize();
  const a = (l1 * l1 - l2 * l2 + L * L) / (2 * L), h = Math.sqrt(Math.max(0, l1 * l1 - a * a));
  const p = pole.clone().sub(S); p.addScaledVector(dir, -p.dot(dir)); if (p.lengthSq() < 1e-8) p.set(0, -1, 0); p.normalize();
  return S.clone().addScaledVector(dir, a).addScaledVector(p, h);
}
const _m4 = new THREE.Matrix4();
// кисть, обхватывающая цилиндр: H — центр хвата, Y — ось хвата (указательный ближе к +Y), X — сторона ладони, side: 1 правая, -1 левая
function handParts(S, H, Y, X, side, o = {}) {
  Y = Y.clone().normalize(); X = X.clone().addScaledVector(Y, -X.dot(Y)).normalize();
  const Z = new THREE.Vector3().crossVectors(X, Y).multiplyScalar(side);
  const rx = o.rx || 0.017, rz = o.rz || 0.026, fr = o.fr || 0.0098, seg = o.seg || 5, c = o.c || S.glove;
  const L = (x, y, z) => H.clone().addScaledVector(X, x).addScaledVector(Y, y).addScaledVector(Z, z);
  const parts = [];
  const palm = rbox(0.028, 0.088, 0.075, 0.013, 2);
  _m4.makeBasis(X, Y, new THREE.Vector3().crossVectors(X, Y)); palm.applyMatrix4(_m4);
  const pc = L(rx + 0.013, -0.004, rz * 0.45 + 0.006); palm.translate(pc.x, pc.y, pc.z);
  parts.push({ g: palm, c });
  const open = o.open || 0;
  for (let j = 0; j < 4; j++) {
    const y = 0.031 - j * 0.0205, rr = fr * (j === 3 ? 0.82 : 1), curl = 1 - open;
    const angs = [-0.2, 0.55 * curl + 0.1, 1.3 * curl + 0.1, (2.15 - j * 0.06) * curl + 0.15];
    const pts = angs.map((a, i) => L((rx + rr) * Math.cos(a) + (i ? 0 : 0.012), y, -(rz + rr) * Math.sin(a) + (i ? 0 : rz * 0.2)));
    for (let k = 0; k < 3; k++) parts.push({ g: limbGeo(pts[k], pts[k + 1], rr * (1 - k * 0.08), seg), c });
  }
  const th = [L(rx + 0.008, 0.042, rz * 0.7), L(rx * 0.3, 0.056, rz * 0.15), L(-rx - 0.002, 0.05, -rz * 0.45), L(-rx - 0.004, 0.044, -rz * 0.95)];
  for (let k = 0; k < 3; k++) parts.push({ g: limbGeo(th[k], th[k + 1], fr * 1.08, seg), c });
  return { parts, wrist: L(rx * 0.7 + 0.01, -0.052, rz * 0.6 + 0.02) };
}
// рука: плечо → (ИК) локоть → запястье + кисть; rolled — закатанный рукав
function armParts(S, L, sh, hand, pole, o = {}) {
  const seg = o.seg || 8, out = [...hand.parts];
  const w = hand.wrist, el = ik(sh, w, o.l1 || 0.3, o.l2 || 0.27, pole);
  const skin = skinTone(S, { face: 'skin', tone: L.tone });
  out.push(...PL(tlimb(sh, el, 0.062, 0.05, seg), S.uni));
  out.push(...PL(tlimb(sh.clone().lerp(el, 0.32), sh.clone().lerp(el, 0.58), 0.066, 0.06, seg, false), S.uni2));
  { const pp = sh.clone().lerp(el, 0.42).add(sideOff(el.clone().sub(sh), o.side || 1, 0.06)); out.push(P(rbox(0.016, 0.055, 0.05, 0.006), S.acc, [pp.x, pp.y, pp.z])); }
  if (L.rolled) {
    out.push(...PL(tlimb(el, el.clone().lerp(w, 0.22), 0.058, 0.055, seg, true), S.uni2));
    out.push(...PL(tlimb(el.clone().lerp(w, 0.2), w, 0.043, 0.035, seg, false), skin));
  } else {
    out.push(...PL(tlimb(el, w, 0.05, 0.042, seg), S.uni));
    out.push(...PL(tlimb(el.clone().lerp(w, 0.12), el.clone().lerp(w, 0.3), 0.054, 0.052, seg, false), S.uni2));
  }
  out.push(...PL(tlimb(el.clone().lerp(w, 0.78), w.clone().lerp(el, -0.05), 0.046, 0.044, seg, false), S.glove));
  if (o.watch) out.push({ g: P(rbox(0.03, 0.012, 0.03, 0.004), 0x111111).g.translate(...w.clone().lerp(el, 0.12).add(V3(0, 0.04, 0)).toArray()), c: 0x111111 });
  return out;
}
function sideOff(dir, side, r) { const Y = dir.clone().normalize(); return new THREE.Vector3(side, 0, 0).addScaledVector(Y, -Y.x * side).normalize().multiplyScalar(r); }

/* ---------------- тело ---------------- */
function pelvisGeo(S) {
  return mergeUV([
    P(rbox(0.34, 0.22, 0.22, 0.07), S.uni2, [0, 0, 0]),
    P(rbox(0.36, 0.055, 0.235, 0.02), S.strap, [0, 0.08, 0]),
    P(rbox(0.05, 0.045, 0.02, 0.005), 0x8a8a80, [0, 0.08, -0.125]),
    P(rbox(0.11, 0.09, 0.06, 0.02), S.pouch, [-0.1, 0.05, 0.135]), P(rbox(0.1, 0.09, 0.06, 0.02), S.pouch, [0.1, 0.05, 0.135]),
    P(rbox(0.06, 0.1, 0.07, 0.02), S.pouch, [-0.185, 0.04, -0.04]),
    P(rbox(0.04, 0.02, 0.012, 0.004), S.pouch, [0.14, 0.11, -0.12]), P(rbox(0.04, 0.02, 0.012, 0.004), S.pouch, [-0.14, 0.11, -0.12]),
  ], { uvScale: 3 });
}
function thighGeo(S, side) {
  return mergeUV([
    ...PL(tlimb(V3(0, 0.03, 0), V3(0, -0.42, 0.0), 0.098, 0.072, 10), S.uni),
    P(rbox(0.05, 0.14, 0.13, 0.022), S.uni2, [side * 0.088, -0.22, 0.0]),
    P(rbox(0.054, 0.02, 0.13, 0.006), S.uni2, [side * 0.09, -0.15, 0.0]),
    ...(side > 0 ? [P(rbox(0.07, 0.17, 0.09, 0.02), S.strap, [0.1, -0.12, 0.0]), P(rbox(0.04, 0.06, 0.05, 0.01), 0x1a1a1a, [0.1, -0.01, 0.0]),
      P(rbox(0.012, 0.025, 0.2, 0.004), S.strap, [0.0, -0.19, 0.0], [0, Math.PI / 2, 0])] : []),
  ], { uvScale: 3 });
}
function shinGeo(S) {
  return mergeUV([
    P(rbox(0.12, 0.13, 0.075, 0.03), S.pad, [0, -0.01, -0.07]),
    P(rbox(0.13, 0.03, 0.02, 0.008), S.strap, [0, -0.01, -0.03]),
    ...PL(tlimb(V3(0, 0.0, 0), V3(0, -0.34, 0.01), 0.072, 0.058, 10), S.uni),
    P(rbox(0.13, 0.07, 0.13, 0.04), S.uni2, [0, -0.33, 0.005]),
    P(rbox(0.12, 0.15, 0.14, 0.04), S.boot, [0, -0.42, 0.0]),
    P(rbox(0.12, 0.07, 0.27, 0.03), S.boot, [0, -0.47, -0.045]),
    P(rbox(0.125, 0.025, 0.285, 0.01), 0x141412, [0, -0.505, -0.047]),
    ...[0, 1, 2].map(i => P(rbox(0.09, 0.008, 0.01, 0.003), 0x16140f, [0, -0.37 - i * 0.03, -0.072 - i * 0.012])),
  ], { uvScale: 3 });
}
function chestGeo(S, L, vest) {
  const p = [
    P(rbox(0.3, 0.22, 0.19, 0.08), S.uni, [0, 0.08, 0]),
    P(rbox(0.4, 0.3, 0.23, 0.1), S.uni, [0, 0.3, 0]),
    P(new THREE.SphereGeometry(0.088, 10, 8), S.uni, [0.205, 0.42, 0]), P(new THREE.SphereGeometry(0.088, 10, 8), S.uni, [-0.205, 0.42, 0]),
    P(new THREE.CylinderGeometry(0.052, 0.06, 0.12, 10), skinTone(S, L), [0, 0.53, 0]),
    P(rbox(0.2, 0.05, 0.16, 0.025), S.uni2, [0, 0.5, 0.0]),
  ];
  if (vest) {
    p.push(
      P(rbox(0.35, 0.3, 0.065, 0.025), S.vest, [0, 0.29, -0.12]), P(rbox(0.35, 0.31, 0.06, 0.025), S.vest, [0, 0.3, 0.12]),
      P(rbox(0.06, 0.2, 0.2, 0.02), S.vest, [0.185, 0.24, 0]), P(rbox(0.06, 0.2, 0.2, 0.02), S.vest, [-0.185, 0.24, 0]),
      P(rbox(0.06, 0.05, 0.25, 0.02), S.vest, [0.13, 0.46, 0]), P(rbox(0.06, 0.05, 0.25, 0.02), S.vest, [-0.13, 0.46, 0]),
      ...[0, 1, 2].map(i => P(rbox(0.36, 0.008, 0.07, 0.003), S.strap, [0, 0.2 + i * 0.05, -0.12])),
      ...[-0.09, 0, 0.09].map(x => P(rbox(0.075, 0.11, 0.055, 0.015), S.pouch, [x, 0.17, -0.175])),
      ...[-0.09, 0, 0.09].map(x => P(rbox(0.078, 0.03, 0.058, 0.01), S.strap, [x, 0.225, -0.176])),
      P(rbox(0.12, 0.07, 0.04, 0.012), S.pouch, [0.08, 0.35, -0.168]),
      P(rbox(0.06, 0.04, 0.008, 0.003), S.acc, [-0.1, 0.38, -0.155]),
      P(rbox(0.07, 0.15, 0.05, 0.015), 0x222321, [-0.13, 0.32, 0.168]),
      P(limbGeo(V3(-0.13, 0.4, 0.17), V3(-0.13, 0.6, 0.17), 0.005, 4), 0x111111),
      P(rbox(0.11, 0.17, 0.06, 0.02), S.pouch, [0.07, 0.28, 0.172]),
      P(rbox(0.05, 0.05, 0.03, 0.01), S.pouch, [-0.19, 0.3, -0.06]),
    );
  } else {
    p.push(
      P(rbox(0.11, 0.1, 0.03, 0.012), S.uni2, [0.09, 0.33, -0.12]), P(rbox(0.11, 0.1, 0.03, 0.012), S.uni2, [-0.09, 0.33, -0.12]),
      P(rbox(0.115, 0.03, 0.034, 0.008), S.uni2, [0.09, 0.385, -0.122]), P(rbox(0.115, 0.03, 0.034, 0.008), S.uni2, [-0.09, 0.385, -0.122]),
      P(rbox(0.07, 0.32, 0.012, 0.004), S.strap, [0.1, 0.3, -0.118], [0, 0, 0.35]), P(rbox(0.07, 0.32, 0.012, 0.004), S.strap, [-0.1, 0.3, -0.118], [0, 0, -0.35]),
      P(rbox(0.32, 0.1, 0.06, 0.02), S.pouch, [0, 0.12, -0.13]),
    );
  }
  if (L.pack) p.push(
    P(rbox(0.3, 0.36, 0.15, 0.05), S.pouch, [0, 0.3, 0.22]), P(rbox(0.28, 0.08, 0.16, 0.03), S.strap, [0, 0.47, 0.22]),
    P(rbox(0.2, 0.12, 0.04, 0.015), S.vest, [0, 0.2, 0.305]), P(rbox(0.035, 0.3, 0.02, 0.006), S.strap, [0.12, 0.3, 0.3]), P(rbox(0.035, 0.3, 0.02, 0.006), S.strap, [-0.12, 0.3, 0.3]),
  );
  return mergeUV(p, { uvScale: 3 });
}
function headGeo(S, L, helmet) {
  const face = skinTone(S, L), bala = L.face === 'bala';
  const parts = [
    P(new THREE.SphereGeometry(0.102, 16, 12), face, [0, 0.04, 0], null, [0.95, 1.13, 1.04]),
    P(rbox(0.12, 0.08, 0.09, 0.035), face, [0, -0.035, -0.045]),
    P(rbox(0.026, 0.045, 0.03, 0.01), face, [0, 0.025, -0.11]),
    P(rbox(0.15, 0.018, 0.03, 0.008), bala ? S.bala : S.hair, [0, 0.072, -0.095]),
    P(new THREE.SphereGeometry(0.024, 6, 5), face, [0.098, 0.035, 0.0], null, [0.5, 1, 0.8]), P(new THREE.SphereGeometry(0.024, 6, 5), face, [-0.098, 0.035, 0.0], null, [0.5, 1, 0.8]),
  ];
  if (bala) parts.push(P(rbox(0.16, 0.03, 0.035, 0.012), STYLE.A.tones[L.tone % 3], [0, 0.05, -0.096]));
  else {
    parts.push(P(rbox(0.024, 0.012, 0.012, 0.005), 0x1a1612, [0.033, 0.05, -0.1]), P(rbox(0.024, 0.012, 0.012, 0.005), 0x1a1612, [-0.033, 0.05, -0.1]));
    if (L.beard) parts.push(P(rbox(0.125, 0.07, 0.09, 0.03), S.hair, [0, -0.05, -0.05]));
    parts.push(P(rbox(0.04, 0.008, 0.01, 0.003), 0x6a3a30, [0, -0.025, -0.106]));
  }
  if (L.eyes === 'goggles') parts.push(P(rbox(0.16, 0.045, 0.03, 0.015), 0x15171a, [0, 0.055, -0.098]), P(rbox(0.14, 0.032, 0.012, 0.01), S.lens, [0, 0.055, -0.113]));
  else if (L.eyes === 'glasses') parts.push(P(rbox(0.065, 0.026, 0.01, 0.008), 0x101214, [-0.036, 0.052, -0.108]), P(rbox(0.065, 0.026, 0.01, 0.008), 0x101214, [0.036, 0.052, -0.108]), P(rbox(0.005, 0.006, 0.1, 0.002), 0x101214, [0.088, 0.055, -0.06]), P(rbox(0.005, 0.006, 0.1, 0.002), 0x101214, [-0.088, 0.055, -0.06]));
  const cups = () => [P(new THREE.CylinderGeometry(0.04, 0.044, 0.04, 12), 0x26292c, [0.11, 0.03, 0.005], [0, 0, Math.PI / 2]), P(new THREE.CylinderGeometry(0.04, 0.044, 0.04, 12), 0x26292c, [-0.11, 0.03, 0.005], [0, 0, Math.PI / 2]),
    P(limbGeo(V3(0.12, 0.0, -0.02), V3(0.05, -0.05, -0.1), 0.004, 4), 0x111111)];
  if (helmet) {
    const hc = L.cover ? S.cover : S.helm;
    parts.push(
      P(new THREE.SphereGeometry(0.132, 18, 9, 0, Math.PI * 2, 0, Math.PI * 0.52), hc, [0, 0.07, 0.005], null, [1, 0.95, 1.06]),
      P(new THREE.CylinderGeometry(0.134, 0.137, 0.022, 18), S.helm, [0, 0.068, 0.005], null, [1, 1, 1.06]),
      P(new THREE.CylinderGeometry(0.128, 0.131, 0.012, 18), S.strap, [0, 0.12, 0.005], null, [1, 1, 1.06]),
      P(rbox(0.058, 0.04, 0.025, 0.008), 0x1e2022, [0, 0.15, -0.128]),
      P(rbox(0.012, 0.028, 0.12, 0.004), 0x23262a, [0.133, 0.1, 0.0]), P(rbox(0.012, 0.028, 0.12, 0.004), 0x23262a, [-0.133, 0.1, 0.0]),
      P(rbox(0.07, 0.05, 0.03, 0.01), S.pouch, [0, 0.11, 0.135]),
      P(rbox(0.052, 0.012, 0.052, 0.004), S.acc, [0, 0.198, 0.02]),
      ...cups(),
    );
  } else if (L.hat === 'cap') {
    parts.push(
      P(new THREE.CylinderGeometry(0.11, 0.115, 0.075, 16), S.helm, [0, 0.13, 0.005]),
      P(new THREE.SphereGeometry(0.111, 16, 6, 0, Math.PI * 2, 0, Math.PI * 0.35), S.helm, [0, 0.145, 0.005]),
      P(rbox(0.17, 0.012, 0.1, 0.005), S.helm, [0, 0.1, -0.132], [-0.12, 0, 0]),
      P(rbox(0.05, 0.03, 0.008, 0.004), S.acc, [0, 0.14, -0.112]),
      ...cups(), P(rbox(0.23, 0.012, 0.02, 0.005), 0x26292c, [0, 0.19, 0.0]),
    );
  } else if (L.hat === 'beanie') {
    parts.push(P(new THREE.SphereGeometry(0.112, 16, 8, 0, Math.PI * 2, 0, Math.PI * 0.55), S.helm, [0, 0.07, 0.005], null, [1, 1.12, 1.06]),
      P(new THREE.CylinderGeometry(0.114, 0.117, 0.04, 16), S.uni2, [0, 0.085, 0.005], null, [1, 1, 1.06]));
  } else if (L.hat === 'bandana') {
    parts.push(P(new THREE.SphereGeometry(0.108, 16, 8, 0, Math.PI * 2, 0, Math.PI * 0.45), S.uni2, [0, 0.07, 0.005], null, [1, 1.12, 1.06]),
      P(rbox(0.05, 0.04, 0.05, 0.015), S.uni2, [0, 0.06, 0.12]), P(rbox(0.03, 0.08, 0.012, 0.005), S.uni2, [0.01, 0.0, 0.13], [0.2, 0, 0.2]));
  } else {
    parts.push(P(new THREE.SphereGeometry(0.106, 16, 8, 0, Math.PI * 2, 0, Math.PI * 0.42), S.hair, [0, 0.07, 0.005], null, [1, 1.12, 1.06]), ...cups(),
      P(rbox(0.23, 0.014, 0.022, 0.006), 0x26292c, [0, 0.19, 0.0]));
  }
  return mergeUV(parts, { uvScale: 3 });
}
// где правая кисть держит оружие (в координатах плечевого шарнира)
const ARM_PIVOT = V3(0, 0.42, 0);
const HOLD = { rifle: V3(0.1, -0.02, -0.4), pistol: V3(0.03, 0.0, -0.46), knife: V3(0.22, -0.18, -0.3), grenade: V3(0.22, -0.1, -0.26) };
const holdOf = key => HOLD[(WEAPONS[key] || WEAPONS.pistol).hold] || HOLD.rifle;
function armsGeo(S, L, key, cacheKey) {
  const id = cacheKey + '|' + key; if (charGeo[id]) return charGeo[id];
  const w = WEAPONS[key], G = GUNS[key], s = BOT_GUN_SCALE, H = holdOf(key);
  const rs = V3(0.205, 0.0, 0), ls = V3(-0.205, 0.0, 0), o = { seg: 6 };
  const gripAxis = V3(0, 0.97, -0.24);
  let right, left, lp, rp;
  if (w.hold === 'pistol' || w.hold === 'grenade') {
    right = handParts(S, H.clone().add(V3(0, -0.02 * s, 0)), gripAxis, V3(1, 0, 0), 1, { seg: 4 });
    left = w.hold === 'pistol' ? handParts(S, H.clone().add(V3(-0.018, -0.035, 0.01)), V3(0, 1, -0.3), V3(-1, -0.3, 0), -1, { seg: 4 })
      : handParts(S, V3(-0.12, -0.12, -0.2), V3(0.2, 1, -0.3), V3(-1, 0, 0), -1, { seg: 4, open: 0.3 });
    rp = V3(0.4, -0.4, 0.1); lp = V3(-0.4, -0.4, 0.1);
  } else if (w.hold === 'knife') {
    right = handParts(S, H, V3(0, 0.25, -1), V3(1, 0, 0), 1, { seg: 4, rx: 0.012, rz: 0.016 });
    left = handParts(S, V3(-0.14, -0.2, -0.22), V3(0.2, 1, -0.4), V3(-1, 0, 0), -1, { seg: 4, open: 0.4 });
    rp = V3(0.5, -0.4, 0.2); lp = V3(-0.5, -0.4, 0.1);
  } else {
    right = handParts(S, H, gripAxis, V3(1, 0, 0), 1, { seg: 4 });
    const fH = H.clone().add(V3(0, G.foreY * s, -G.fore * s));
    left = G.foreGrip ? handParts(S, fH, V3(0, 1, 0.2), V3(-1, 0, 0), -1, { seg: 4 })
      : handParts(S, fH, V3(0, 0, -1), V3(-0.6, -0.8, 0), -1, { seg: 4, rx: G.foreR * s, rz: G.foreR * s });
    rp = V3(0.6, -0.5, 0.25); lp = V3(-0.3, -0.9, -0.2);
  }
  const r = mergeUV(armParts(S, L, rs, right, rp, { ...o, side: 1 }), { uvScale: 3 });
  const l = mergeUV(armParts(S, L, ls, left, lp, { ...o, side: -1 }), { uvScale: 3 });
  return charGeo[id] = { r, l };
}
let lookCounter = { A: 0, B: 0 };
function makeBody(team, skinId, lookIdx) {
  const S = resolveStyle(team, skinId);
  const li = lookIdx != null ? lookIdx : (lookCounter[team] = (lookCounter[team] || 0) + 1) - 1;
  const L = resolveLook(S, li), ck = team + '|' + (skinId == null ? '' : skinId) + '|' + (li % LOOKS.length);
  if (!charGeo['pelvis' + ck]) {
    charGeo['pelvis' + ck] = pelvisGeo(S); charGeo['thighL' + ck] = thighGeo(S, -1); charGeo['thighR' + ck] = thighGeo(S, 1);
    charGeo['shin' + ck] = shinGeo(S);
  }
  const root = new THREE.Group(); root.rotation.order = 'YXZ';
  const hips = new THREE.Group(); hips.position.y = 0.98; root.add(hips);
  hips.add(new THREE.Mesh(charGeo['pelvis' + ck], charMat));
  const hit = [];
  const hb = (parent, w, h, d, p, part) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), hitMat); m.position.set(p[0], p[1], p[2]); m.userData.part = part; parent.add(m); hit.push(m); };
  hb(hips, 0.38, 0.28, 0.28, [0, 0, 0], 'body');
  const thighs = [], knees = [];
  for (const side of [-1, 1]) {
    const th = new THREE.Group(); th.position.set(side * 0.1, -0.06, 0); hips.add(th);
    th.add(new THREE.Mesh(charGeo[(side < 0 ? 'thighL' : 'thighR') + ck], charMat));
    hb(th, 0.19, 0.46, 0.2, [0, -0.2, 0], 'legs');
    const kn = new THREE.Group(); kn.position.y = -0.44; th.add(kn);
    kn.add(new THREE.Mesh(charGeo['shin' + ck], charMat));
    hb(kn, 0.16, 0.5, 0.22, [0, -0.25, -0.02], 'legs');
    thighs.push(th); knees.push(kn);
  }
  const chest = new THREE.Group(); chest.position.y = 0.1; hips.add(chest);
  const chestMesh = new THREE.Mesh(undefined, charMat); chest.add(chestMesh);
  hb(chest, 0.46, 0.56, 0.32, [0, 0.28, 0], 'body');
  const armPivot = new THREE.Group(); armPivot.position.copy(ARM_PIVOT); chest.add(armPivot);
  const armR = new THREE.Mesh(undefined, charMat), armL = new THREE.Mesh(undefined, charMat); armPivot.add(armR, armL);
  const gun = new THREE.Group(); gun.scale.setScalar(BOT_GUN_SCALE); armPivot.add(gun);
  const slots = makeGunSlots(gun);
  const muzzle = new THREE.Object3D(); gun.add(muzzle);
  const head = new THREE.Group(); head.position.y = 0.6; chest.add(head);
  const headMesh = new THREE.Mesh(undefined, charMat); head.add(headMesh);
  hb(head, 0.27, 0.32, 0.29, [0, 0.06, 0], 'head');
  const blob = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }));
  blob.rotation.x = -Math.PI / 2; scene.add(blob);
  scene.add(root);
  const m = { root, hips, chest, head, thighs, knees, arms: armR, armR, armL, armPivot, gun, slots, muzzle, hit, blob, chestMesh, headMesh,
    S, L, ck, team, skin: skinId, look: li, wkey: null, flags: '',
    anim: { crouch: 0, kneel: 0, run: 0, aim: 0, recoil: 0, throwT: 0, meleeT: 0, reload: 0, die: 0, dieDir: 1 } };
  setBodyFlags(m, team === 'A', true);
  setBodyWeapon(m, 'pistol');
  return m;
}
// шлем и бронежилет видны на модели
function setBodyFlags(m, helmet, vest) {
  const f = (helmet ? 'H' : 'h') + (vest ? 'V' : 'v'); if (m.flags === f) return; m.flags = f;
  const hk = 'head' + m.ck + (helmet ? 'H' : 'h'), ck = 'chest' + m.ck + (vest ? 'V' : 'v');
  if (!charGeo[hk]) charGeo[hk] = headGeo(m.S, m.L, helmet);
  if (!charGeo[ck]) charGeo[ck] = chestGeo(m.S, m.L, vest);
  m.headMesh.geometry = charGeo[hk]; m.chestMesh.geometry = charGeo[ck];
}
function setBodyWeapon(m, key) {
  if (!GUNS[key]) key = 'pistol';
  m.wkey = key;
  const a = armsGeo(m.S, m.L, key, m.ck);
  m.armR.geometry = a.r; m.armL.geometry = a.l; m.armL.position.set(0, 0, 0);
  setGunSlots(m.slots, key);
  m.gun.position.copy(holdOf(key)); m.gun.rotation.set(0, 0, 0);
  m.muzzle.position.copy(GUNS[key].muzzle);
}
function setBotWeapon(u) { if (u.mesh) setBodyWeapon(u.mesh, u.cur); }
// пересоздать модель бойца (например, после смены u.skin)
function rebuildBody(u) {
  const old = u.mesh; if (!old) return;
  scene.remove(old.root); scene.remove(old.blob); old.hit.forEach(h => h.geometry.dispose());
  const m = makeBody(u.team, u.skin, old.look);
  m.hit.forEach(p => p.userData.unit = u);
  if (u.marker) m.root.add(u.marker);
  u.mesh = m; setBotWeapon(u);
  m.root.visible = old.root.visible; m.blob.visible = old.blob.visible;
  syncBotMesh(u, 0, 0);
}
// поза и анимация бойца по его состоянию (скорость, прицел, присед, закладка, бросок, отдача, перезарядка)
const _e = new THREE.Vector3();
function syncBotMesh(b, dt, spd) {
  const m = b.mesh; if (!m) return;
  const w = WEAPONS[b.cur] || WEAPONS.pistol;
  const A = m.anim, k = 1 - Math.exp(-dt * 9);
  const want = A.throwT > 0.15 && m.throwKey ? m.throwKey : b.cur;
  if (m.wkey !== want && GUNS[want]) setBodyWeapon(m, want);
  setBodyFlags(m, b.helmet !== undefined ? !!b.helmet : m.S.headgear === 'helmet', b.armor > 0);
  m.root.position.set(b.pos.x, b.pos.y, b.pos.z);
  m.root.rotation.set(0, b.yaw, 0);
  m.blob.position.set(b.pos.x, b.pos.y + 0.015, b.pos.z);
  A.crouch += ((b.crouch ? 1 : 0) - A.crouch) * k;
  A.kneel += ((b.planting || b.defusing ? 1 : 0) - A.kneel) * k;
  A.aim += ((b.targetVisible ? 1 : 0) - A.aim) * k;
  A.recoil = Math.max(0, A.recoil - dt * 8);
  A.throwT = Math.max(0, A.throwT - dt); A.meleeT = Math.max(0, A.meleeT - dt);
  const rl = b.reloading > 0 && w.reload ? clamp(1 - b.reloading / w.reload, 0, 1) : 0;
  A.reload += ((b.reloading > 0 ? 1 : 0) - A.reload) * k;
  // походка: отдельно вперёд/назад и боком
  const fwd = spd > 0.1 ? (b.vx * -Math.sin(b.yaw) + b.vz * -Math.cos(b.yaw)) / spd : 1;
  const amt = Math.min(1, spd / 4) * (1 - A.kneel);
  A.run += (clamp((spd - 2.5) / 2, 0, 1) - A.run) * k;
  b.walkPhase += dt * spd * (2.3 + A.crouch * 0.8);
  const ph = b.walkPhase, sn = Math.sin(ph), cr = A.crouch * (1 - A.kneel), kn = A.kneel;
  const s = sn * amt * (fwd < -0.3 ? -1 : 1) * (1 - cr * 0.45);
  const fb = Math.abs(fwd) >= 0.5 ? 1 : 0.4;
  const side = Math.abs(fwd) < 0.5 ? amt : 0;
  m.thighs[0].rotation.set(s * (0.6 + A.run * 0.25) * fb + cr * 1.0 + kn * 1.5, 0, Math.max(0, sn) * -0.22 * side - cr * 0.12);
  m.thighs[1].rotation.set(-s * (0.6 + A.run * 0.25) * fb + cr * 1.0 + kn * 0.05, 0, Math.max(0, -sn) * 0.22 * side + cr * 0.12);
  m.knees[0].rotation.x = -(0.08 + Math.max(0, -sn) * (0.9 + A.run * 0.5)) * amt - cr * 1.85 - kn * 1.5;
  m.knees[1].rotation.x = -(0.08 + Math.max(0, sn) * (0.9 + A.run * 0.5)) * amt - cr * 1.85 - kn * 1.62;
  m.hips.position.y = 0.98 - Math.abs(Math.cos(ph)) * (0.035 + A.run * 0.03) * amt - (b.targetVisible ? 0.03 : 0) * (1 - cr) - cr * 0.31 - kn * 0.4;
  m.hips.position.z = cr * 0.06;
  m.hips.rotation.y = Math.sin(ph) * 0.08 * amt;
  const breathe = Math.sin(gt * 2 + b.pos.x) * 0.012;
  const lean = amt * 0.08 + A.run * 0.12 * (1 - A.aim) + cr * 0.18 + kn * 0.35;
  m.chest.rotation.set(b.aimPitch * 0.8 * (1 - kn) + breathe + lean - A.recoil * 0.06, -Math.sin(ph) * 0.1 * amt, 0);
  m.head.rotation.set(b.aimPitch * 0.2 - lean * 0.7 + kn * 0.25, 0, 0);
  // руки и оружие
  const low = A.run * (1 - A.aim);
  let ax = -low * 0.45 - kn * 0.85 + A.recoil * 0.14 + Math.sin(ph * 2) * 0.03 * amt, ay = low * 0.25, az = 0;
  if (A.throwT > 0) { const t = 1 - A.throwT / 0.6; ax = t < 0.45 ? t / 0.45 * 1.9 : 1.9 - Math.min(1, (t - 0.45) / 0.25) * 2.4; ay = -0.2; }
  if (A.meleeT > 0) { const t = 1 - A.meleeT / 0.4; ay = 0.9 - t * 1.8; ax = 0.25 * Math.sin(t * Math.PI); }
  m.armPivot.rotation.set(ax, ay, az);
  m.armPivot.position.set(ARM_PIVOT.x, ARM_PIVOT.y, ARM_PIVOT.z + A.recoil * 0.05);
  const H = holdOf(b.cur);
  m.gun.position.copy(H); m.gun.rotation.set(0, 0, 0);
  if (A.reload > 0.01) {
    // перезарядка: оружие наклоняется, левая рука уходит к магазину и обратно
    const r = Math.sin(Math.PI * clamp(rl * 1.1, 0, 1));
    m.gun.rotation.set(r * 0.25 * A.reload, 0, r * 0.4 * A.reload);
    const G = GUNS[b.cur]; _e.copy(G.magC).multiplyScalar(BOT_GUN_SCALE).add(H);
    const lh = _e.sub(H.clone().add(V3(0, G.foreY * BOT_GUN_SCALE, -G.fore * BOT_GUN_SCALE))).multiplyScalar(clamp(Math.sin(rl * Math.PI * 1.5), 0, 1));
    lh.y -= Math.max(0, Math.sin(rl * Math.PI * 2.2)) * 0.12;
    m.armL.position.copy(lh).multiplyScalar(A.reload);
  } else m.armL.position.set(0, 0, 0);
  m.root.visible = !(b.protT > 0 && Math.floor(gt * 10) % 2 === 0);
}
// плавное падение при смерти (вызывается из combat-тика после логики ботов)
function deathPose(b, dt) {
  const m = b.mesh; if (!m) return;
  const A = m.anim;
  if (A.die === 0) { A.dieDir = Math.random() < 0.65 ? 1 : -1; A.dieTw = rand(-0.5, 0.5); }
  A.die = Math.min(1.6, A.die + dt);
  const t = A.die, k1 = clamp(t / 0.35, 0, 1), k2 = clamp((t - 0.18) / 0.62, 0, 1);
  const e1 = 1 - Math.pow(1 - k1, 2), e2 = k2 * k2 * (3 - 2 * k2);
  const bounce = t > 0.8 ? Math.sin(clamp((t - 0.8) / 0.25, 0, 1) * Math.PI) * 0.04 : 0;
  m.root.position.set(b.pos.x, b.pos.y + e2 * 0.14 + bounce, b.pos.z);
  m.root.rotation.set(A.dieDir * e2 * 1.5, b.yaw + A.dieTw * e2, A.dieTw * 0.3 * e2);
  m.hips.position.y = 0.98 - e1 * 0.3 * (1 - e2 * 0.7);
  m.thighs[0].rotation.set(e1 * 0.9 * (1 - e2 * 0.6), 0, -0.15 * e2); m.thighs[1].rotation.set(e1 * 0.4 * (1 - e2 * 0.5), 0, 0.2 * e2);
  m.knees[0].rotation.x = -e1 * 1.3 * (1 - e2 * 0.6); m.knees[1].rotation.x = -e1 * 0.8 * (1 - e2 * 0.4);
  m.chest.rotation.set(-A.dieDir * 0.25 * e2 + e1 * 0.3 * (1 - e2), 0, 0);
  m.head.rotation.set(-A.dieDir * 0.3 * e2, A.dieTw * e2, 0);
  m.armPivot.rotation.set(-0.6 * e1 - A.dieDir * 0.8 * e2, 0.3 * e2, 0);
  m.blob.visible = false;
}
