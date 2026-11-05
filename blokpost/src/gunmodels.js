'use strict';
/* ---------------- оружие: модели ---------------- */
// Профиль рисуется сбоку: x — вперёд к дулу, y — вверх; выдавливается по ширине (ось x модели — вбок, вправо +).
// Каждая деталь — { g, c, k }: геометрия, цвет и вид материала k: 'metal' | 'polymer' | 'wood' | 'accent'.
// Детали склеиваются по видам материала: отдельный меш на вид (mesh.userData.kind) — скин меняет материал меша.
// Хук скинов: если объявлена функция gunMaterial(weaponKey, kind), её результат (материал) используется вместо нашего.
const GC = { blk: 0x1d1f21, metal: 0x2c2f32, steel: 0x41464b, park: 0x33352f, wood: 0x4a2c18, wood2: 0x3a2214, fde: 0x7a6848, fde2: 0x64553a, od: 0x3c4632, od2: 0x323a2a, brown: 0x3e2416, lens: 0x5fa0a8, red: 0x8a2a20, brass: 0xb08a3e, poly: 0x262729, grey: 0x55595c, tan: 0x7a6e58 };
const KIND_BY_COLOR = { [GC.wood]: 'wood', [GC.wood2]: 'wood', [GC.brown]: 'wood', [GC.metal]: 'metal', [GC.steel]: 'metal', [GC.park]: 'metal', [GC.lens]: 'accent', [GC.red]: 'accent', [GC.brass]: 'accent' };
const GUN_KINDS = ['metal', 'polymer', 'wood', 'accent'];
const kindOf = pt => pt.k || KIND_BY_COLOR[pt.c] || 'polymer';
const K = (k, ...pts) => { for (const p of pts.flat()) p.k = k; return pts.length === 1 ? pts[0] : pts.flat(); };

function ex(pts, width, c, lat = 0, bevel = 0.003, hole) {
  const s = new THREE.Shape(); s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  s.closePath();
  if (hole) { const h = new THREE.Path(); h.moveTo(hole[0][0], hole[0][1]); for (let i = 1; i < hole.length; i++) h.lineTo(hole[i][0], hole[i][1]); h.closePath(); s.holes.push(h); }
  bevel = Math.min(bevel, width * 0.3);
  const depth = Math.max(0.0005, width - bevel * 2);
  const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 1, curveSegments: 4 });
  g.translate(0, 0, -depth / 2); g.rotateY(Math.PI / 2); g.translate(lat, 0, 0);
  return { g, c, wear: true };
}
function cyl(r, x0, x1, y, c, lat = 0, seg = 12, rFront) {
  const g = new THREE.CylinderGeometry(rFront || r, r, Math.abs(x1 - x0), seg);
  g.rotateX(-Math.PI / 2); g.translate(lat, y, -(x0 + x1) / 2);
  return { g, c };
}
function bx(w, h, len, x, y, c, lat = 0) {
  const g = new THREE.BoxGeometry(w, h, len); g.translate(lat, y, -x);
  return { g, c };
}
// цилиндр поперёк оружия (оси, штифты, винты)
function pinX(r, len, x, y, c, lat = 0, seg = 8) {
  const g = new THREE.CylinderGeometry(r, r, len, seg); g.rotateZ(Math.PI / 2); g.translate(lat, y, -x);
  return { g, c };
}
// вертикальный цилиндр (гранаты, рукояти)
function vcyl(r, y0, y1, c, x = 0, lat = 0, seg = 14, rTop) {
  const g = new THREE.CylinderGeometry(rTop || r, r, Math.abs(y1 - y0), seg); g.translate(lat, (y0 + y1) / 2, -x);
  return { g, c };
}
function ring(R, r, x, y, c, lat = 0, axis = 'x') {
  const g = new THREE.TorusGeometry(R, r, 5, 12);
  if (axis === 'x') g.rotateY(Math.PI / 2); else if (axis === 'y') g.rotateX(Math.PI / 2);
  g.translate(lat, y, -x); return { g, c };
}
// планка с зубцами
function rail(x0, x1, y, w = 0.024, c = GC.blk, lat = 0) {
  const out = [bx(w, 0.007, x1 - x0, (x0 + x1) / 2, y, c, lat)];
  for (let x = x0 + 0.006; x < x1 - 0.004; x += 0.0105) out.push(bx(w + 0.004, 0.005, 0.005, x, y + 0.005, c, lat));
  return K('metal', out);
}
// спусковая скоба и спуск
function trigger(x, y, c = GC.blk, w = 0.012) {
  return [
    ex([[x - 0.006, y], [x + 0.056, y], [x + 0.054, y - 0.018], [x + 0.042, y - 0.034], [x + 0.008, y - 0.034], [x - 0.004, y - 0.022]], w, c, 0, 0.002,
      [[x + 0.002, y - 0.003], [x + 0.049, y - 0.003], [x + 0.046, y - 0.016], [x + 0.038, y - 0.028], [x + 0.011, y - 0.028], [x + 0.003, y - 0.019]]),
    K('metal', ex([[x + 0.022, y], [x + 0.029, y], [x + 0.027, y - 0.014], [x + 0.021, y - 0.022], [x + 0.019, y - 0.016]], 0.006, GC.steel, 0, 0.0015)),
  ];
}
function swivel(x, y, lat = 0) { return K('metal', ring(0.011, 0.0022, x, y, GC.steel, lat, 'z')); }

/* ---------------- чертежи ---------------- */
// grip — точка хвата правой рукой; fore — расстояние до хвата левой; foreGrip — левая на вертикальной рукояти;
// sightY — высота линии прицела; muzzle — дульный срез; eject — окно выброса; parts: body, mag, pump, bolt (+ pivots)
const GUNDEF = {
  pistol: () => ({
    grip: [-0.025, -0.05], fore: 0, foreY: -0.08, sightY: 0.054, muzzle: [0.168, 0.022], eject: [0.06, 0.04], shell: 0.6,
    body: [
      ex([[-0.025, -0.014], [0.155, -0.014], [0.155, 0.007], [-0.025, 0.007]], 0.024, GC.poly),
      ...[0, 1, 2].map(i => bx(0.026, 0.004, 0.006, 0.105 + i * 0.014, -0.016, GC.poly)),
      ex([[-0.042, 0.004], [0.012, 0.004], [0.006, -0.02], [-0.006, -0.112], [-0.057, -0.112], [-0.064, -0.094], [-0.052, -0.02], [-0.05, 0.004]], 0.03, GC.poly),
      ex([[-0.05, 0.009], [-0.028, 0.009], [-0.036, -0.004], [-0.064, -0.008]], 0.028, GC.poly),
      ...[0, 1, 2, 3, 4, 5].map(i => bx(0.031, 0.003, 0.04, -0.03 - i * 0.0028, -0.035 - i * 0.012, 0x1a1b1c)),
      ...trigger(0.004, -0.014, GC.poly),
      K('metal', bx(0.003, 0.005, 0.03, 0.02, 0.01, GC.steel, -0.0135), pinX(0.0032, 0.027, 0.085, 0.0, GC.steel)),
      K('metal', cyl(0.0078, 0.16, 0.168, 0.022, GC.steel), cyl(0.0046, 0.165, 0.1686, 0.022, 0x050505)),
    ],
    bolt: [
      K('metal', ex([[-0.035, 0.006], [0.165, 0.006], [0.165, 0.036], [0.152, 0.046], [-0.022, 0.046], [-0.035, 0.034]], 0.026, GC.metal)),
      ...[0, 1, 2, 3, 4, 5].map(i => K('metal', bx(0.0275, 0.028, 0.0022, -0.026 + i * 0.0065, 0.024, 0x1b1d1f))),
      ...[0, 1, 2].map(i => K('metal', bx(0.0275, 0.024, 0.0022, 0.13 + i * 0.0065, 0.022, 0x1b1d1f))),
      K('metal', bx(0.004, 0.012, 0.036, 0.06, 0.037, 0x080808, 0.0118), bx(0.012, 0.004, 0.036, 0.06, 0.045, GC.steel), bx(0.003, 0.004, 0.016, 0.034, 0.031, GC.steel, 0.0134)),
      K('metal', bx(0.005, 0.008, 0.006, 0.152, 0.05, GC.blk), bx(0.022, 0.009, 0.01, -0.016, 0.05, GC.blk)),
      K('accent', bx(0.0035, 0.003, 0.002, 0.152, 0.052, 0xd8d0a0)),
    ],
    mag: [K('metal', bx(0.02, 0.1, 0.034, -0.026, -0.062, GC.steel)), bx(0.033, 0.012, 0.058, -0.031, -0.116, GC.poly)],
  }),
  smg: () => ({
    grip: [-0.03, -0.07], fore: 0.25, foreY: 0.012, foreR: 0.027, sightY: 0.076, muzzle: [0.47, 0.012], eject: [0.08, 0.025], shell: 0.7,
    body: [
      K('metal', ex([[-0.08, -0.03], [0.2, -0.03], [0.2, 0.04], [0.17, 0.048], [-0.08, 0.048]], 0.048, 0x232527)),
      ...rail(-0.06, 0.19, 0.052, 0.026),
      K('metal', bx(0.004, 0.02, 0.05, 0.08, 0.02, 0x070707, 0.0245)),
      K('metal', cyl(0.024, 0.2, 0.47, 0.012, 0x1f2122, 0, 16), cyl(0.026, 0.205, 0.218, 0.012, 0x151617, 0, 16), cyl(0.026, 0.455, 0.47, 0.012, 0x151617, 0, 16), cyl(0.008, 0.468, 0.4712, 0.012, 0x050505, 0, 10)),
      ...[0, 1, 2, 3, 4, 5].map(i => K('metal', cyl(0.0248, 0.25 + i * 0.03, 0.256 + i * 0.03, 0.012, 0x2a2c2e, 0, 16))),
      ex([[-0.04, -0.03], [0.0, -0.03], [-0.022, -0.13], [-0.062, -0.132], [-0.07, -0.115], [-0.05, -0.04]], 0.034, GC.poly),
      ...trigger(0.0, -0.03, GC.poly),
      ex([[0.03, -0.03], [0.11, -0.03], [0.1, -0.05], [0.035, -0.05]], 0.052, GC.poly),
      K('metal', bx(0.007, 0.009, 0.24, -0.2, 0.03, GC.metal, 0.016), bx(0.007, 0.009, 0.24, -0.2, 0.03, GC.metal, -0.016)),
      K('metal', bx(0.044, 0.085, 0.014, -0.32, 0.0, GC.blk), bx(0.05, 0.03, 0.02, -0.08, 0.03, GC.metal), pinX(0.007, 0.056, -0.08, 0.03, GC.steel)),
      bx(0.046, 0.09, 0.012, -0.329, -0.002, 0x141516),
      K('metal', bx(0.012, 0.022, 0.012, 0.16, 0.07, GC.blk), bx(0.026, 0.018, 0.012, -0.04, 0.068, GC.blk)),
      K('metal', bx(0.004, 0.008, 0.016, -0.01, 0.018, GC.steel, 0.026), pinX(0.004, 0.054, 0.05, 0.0, GC.steel)),
      swivel(-0.07, 0.0, -0.028),
    ],
    bolt: [K('metal', bx(0.014, 0.01, 0.022, 0.13, 0.034, GC.steel, -0.031), pinX(0.006, 0.014, 0.13, 0.034, GC.steel, -0.04))],
    mag: [K('metal', ex([[0.05, -0.03], [0.088, -0.03], [0.098, -0.215], [0.058, -0.215]], 0.026, GC.metal)), ex([[0.054, -0.212], [0.102, -0.212], [0.103, -0.224], [0.053, -0.224]], 0.03, GC.poly)],
  }),
  smg2: () => ({
    grip: [-0.03, -0.075], fore: 0.2, foreY: -0.085, foreGrip: true, sightY: 0.078, muzzle: [0.36, 0.01], eject: [0.07, 0.025], shell: 0.7,
    body: [
      ex([[-0.1, -0.035], [0.22, -0.035], [0.25, -0.012], [0.25, 0.042], [0.03, 0.05], [-0.1, 0.046]], 0.05, GC.grey),
      ex([[0.0, 0.044], [0.25, 0.044], [0.25, 0.05], [0.0, 0.05]], 0.044, GC.grey),
      ...rail(-0.07, 0.24, 0.054, 0.024),
      K('metal', bx(0.004, 0.022, 0.05, 0.07, 0.022, 0x070707, 0.0255)),
      K('metal', cyl(0.012, 0.25, 0.33, 0.01, GC.metal), cyl(0.016, 0.32, 0.36, 0.01, GC.blk, 0, 10), cyl(0.006, 0.358, 0.3605, 0.01, 0x050505, 0, 8)),
      ...[0, 1, 2].map(i => K('metal', bx(0.034, 0.004, 0.006, 0.33 + i * 0.01, 0.024, 0x101112))),
      ...[0, 1, 2, 3].map(i => bx(0.052, 0.012, 0.022, 0.12 + i * 0.03, 0.012, 0x2c2f31)),
      ex([[-0.045, -0.035], [-0.005, -0.035], [-0.024, -0.135], [-0.066, -0.137], [-0.072, -0.12], [-0.054, -0.045]], 0.034, GC.poly),
      ...trigger(-0.004, -0.035, GC.poly),
      ex([[0.15, -0.035], [0.19, -0.035], [0.183, -0.13], [0.153, -0.13], [0.149, -0.12]], 0.032, GC.poly),
      ...[0, 1, 2].map(i => bx(0.034, 0.004, 0.03, 0.168, -0.06 - i * 0.022, 0x1a1b1c)),
      ex([[-0.1, 0.035], [-0.3, 0.025], [-0.32, 0.01], [-0.32, -0.085], [-0.29, -0.085], [-0.28, -0.01], [-0.12, -0.012], [-0.1, -0.02]], 0.02, GC.poly, -0.012, 0.003, [[-0.14, 0.02], [-0.27, 0.014], [-0.27, -0.002], [-0.14, -0.002]]),
      K('metal', bx(0.012, 0.02, 0.012, 0.22, 0.068, GC.blk), bx(0.026, 0.016, 0.012, -0.05, 0.068, GC.blk)),
      K('metal', bx(0.004, 0.008, 0.014, -0.01, 0.015, GC.steel, 0.027), pinX(0.0042, 0.056, 0.045, -0.012, GC.steel)),
    ],
    bolt: [K('metal', bx(0.01, 0.01, 0.024, 0.0, 0.03, GC.steel, -0.03))],
    mag: [K('metal', ex([[0.035, -0.035], [0.07, -0.035], [0.074, -0.25], [0.04, -0.25]], 0.026, GC.metal)), ex([[0.036, -0.247], [0.078, -0.247], [0.079, -0.258], [0.035, -0.258]], 0.03, GC.poly)],
  }),
  shotgun: () => ({
    grip: [-0.035, -0.07], fore: 0.42, foreY: 0.0, foreR: 0.03, sightY: 0.054, muzzle: [0.71, 0.03], eject: [0.06, 0.02], shell: 1.6, shellK: 'shot',
    body: [
      K('metal', ex([[-0.08, -0.03], [0.18, -0.03], [0.18, 0.045], [0.16, 0.05], [-0.06, 0.05], [-0.08, 0.042]], 0.05, GC.park)),
      K('metal', bx(0.004, 0.026, 0.07, 0.06, 0.018, 0x070707, 0.0255)),
      K('metal', cyl(0.0145, 0.18, 0.71, 0.03, GC.steel), cyl(0.0105, 0.705, 0.7104, 0.03, 0x050505), cyl(0.013, 0.18, 0.62, -0.006, GC.park), cyl(0.014, 0.6, 0.63, -0.006, GC.steel)),
      K('metal', bx(0.03, 0.02, 0.04, 0.62, 0.012, GC.metal), bx(0.03, 0.008, 0.012, 0.66, 0.012, GC.metal)),
      ex([[-0.08, 0.042], [-0.08, -0.03], [-0.42, -0.095], [-0.45, -0.095], [-0.45, 0.028], [-0.38, 0.036]], 0.045, GC.poly),
      bx(0.047, 0.125, 0.016, -0.452, -0.035, 0x111213),
      ex([[-0.045, -0.03], [0.0, -0.03], [-0.03, -0.13], [-0.07, -0.13], [-0.075, -0.115]], 0.034, GC.poly),
      ...trigger(0.0, -0.03, GC.metal),
      K('accent', bx(0.006, 0.006, 0.006, 0.7, 0.048, 0xd9c27a)),
      ...[0, 1, 2, 3].map(i => K('accent', cyl(0.0085, -0.02 + i * 0.04, 0.03 + i * 0.04, 0.012, GC.red, 0.031, 8))),
      ...[0, 1, 2, 3].map(i => K('accent', cyl(0.0092, -0.028 + i * 0.04, -0.018 + i * 0.04, 0.012, GC.brass, 0.031, 8))),
      ex([[-0.03, 0.03], [0.17, 0.03], [0.17, -0.01], [-0.03, -0.01]], 0.01, GC.poly, 0.03),
      swivel(-0.4, -0.06, 0), swivel(0.6, -0.022, 0),
      K('metal', pinX(0.004, 0.054, 0.12, 0.0, GC.steel), pinX(0.004, 0.054, -0.04, 0.0, GC.steel)),
    ],
    pump: [cyl(0.027, 0.3, 0.47, 0.0, GC.poly, 0, 14), ...[0, 1, 2, 3, 4].map(i => cyl(0.029, 0.31 + i * 0.033, 0.322 + i * 0.033, 0.0, 0x151617, 0, 14))],
  }),
  rifle: () => ({
    grip: [-0.035, -0.085], fore: 0.4, foreY: 0.008, foreR: 0.042, sightY: 0.072, muzzle: [0.85, 0.0], eject: [0.12, 0.03], shell: 0.9,
    body: [
      K('metal', ex([[-0.1, -0.035], [0.27, -0.035], [0.27, 0.035], [0.05, 0.048], [-0.1, 0.044]], 0.05, GC.metal)),
      K('metal', ex([[-0.1, 0.034], [0.04, 0.034], [0.05, 0.05], [0.02, 0.058], [-0.1, 0.05]], 0.044, GC.steel)),
      ...[0, 1, 2, 3, 4].map(i => K('metal', bx(0.046, 0.003, 0.006, -0.08 + i * 0.022, 0.052, 0x24272a))),
      K('metal', bx(0.004, 0.022, 0.07, 0.12, 0.022, 0x070707, 0.0255)),
      ...[[-0.06, 0.0], [0.0, -0.02], [0.2, -0.02], [0.24, 0.02], [-0.08, -0.025]].map(([x, y]) => K('metal', pinX(0.0035, 0.054, x, y, GC.steel))),
      ex([[-0.1, 0.04], [-0.1, -0.025], [-0.44, -0.1], [-0.47, -0.1], [-0.47, 0.022], [-0.4, 0.032]], 0.042, GC.wood),
      K('metal', bx(0.044, 0.125, 0.012, -0.472, -0.035, GC.metal)),
      ex([[-0.045, -0.035], [0.0, -0.035], [-0.03, -0.145], [-0.072, -0.145], [-0.075, -0.13]], 0.035, GC.brown),
      ...trigger(0.0, -0.035, GC.metal),
      ex([[0.27, -0.035], [0.5, -0.028], [0.5, 0.02], [0.27, 0.026]], 0.058, GC.wood),
      ...[0, 1, 2].map(i => bx(0.061, 0.004, 0.004, 0.32 + i * 0.06, -0.012, GC.wood2)),
      ex([[0.27, 0.03], [0.47, 0.03], [0.47, 0.055], [0.27, 0.052]], 0.045, GC.wood),
      K('metal', cyl(0.011, 0.5, 0.79, 0.0, GC.steel), cyl(0.009, 0.47, 0.55, 0.045, GC.metal), bx(0.03, 0.05, 0.02, 0.555, 0.025, GC.metal), bx(0.05, 0.012, 0.012, 0.27, 0.0, GC.metal)),
      K('metal', ex([[0.7, -0.012], [0.745, -0.012], [0.738, 0.055], [0.728, 0.055]], 0.02, GC.metal), bx(0.004, 0.03, 0.018, 0.734, 0.045, GC.metal, 0.011), bx(0.004, 0.03, 0.018, 0.734, 0.045, GC.metal, -0.011)),
      K('metal', cyl(0.017, 0.78, 0.85, 0.0, GC.metal, 0, 12), cyl(0.007, 0.848, 0.8505, 0.0, 0x050505, 0, 8)),
      ...[0, 1].map(i => K('metal', bx(0.036, 0.008, 0.008, 0.8 + i * 0.022, 0.012, 0x0a0a0a))),
      K('metal', bx(0.032, 0.022, 0.05, 0.245, 0.056, GC.metal), bx(0.006, 0.012, 0.006, 0.26, 0.072, GC.metal), bx(0.03, 0.004, 0.06, 0.22, 0.068, GC.steel)),
      K('metal', ex([[-0.04, 0.025], [0.08, 0.02], [0.08, 0.012], [-0.04, 0.016]], 0.004, GC.steel, 0.028)),
      swivel(-0.42, -0.085, 0), swivel(0.49, -0.03, 0),
    ],
    bolt: [K('metal', bx(0.012, 0.01, 0.05, 0.16, 0.03, GC.steel, 0.032), pinX(0.007, 0.018, 0.18, 0.03, GC.steel, 0.041))],
    mag: [K('metal', ex([[0.07, -0.035], [0.13, -0.035], [0.15, -0.1], [0.185, -0.19], [0.205, -0.245], [0.15, -0.265], [0.128, -0.21], [0.095, -0.12]], 0.03, 0x4a2a16)),
      ...[0, 1, 2].map(i => K('metal', bx(0.032, 0.006, 0.02, 0.11 + i * 0.025, -0.1 - i * 0.045, 0x3c2212)))],
  }),
  carbine: () => ({
    grip: [-0.035, -0.085], fore: 0.39, foreY: 0.009, foreR: 0.042, sightY: 0.104, muzzle: [0.79, 0.015], eject: [0.1, 0.022], shell: 0.9,
    body: [
      K('metal', ex([[-0.06, 0.0], [0.22, 0.0], [0.22, 0.05], [-0.06, 0.05]], 0.044, GC.blk)),
      K('metal', ex([[-0.06, -0.036], [0.17, -0.036], [0.19, 0.0], [-0.06, 0.0]], 0.046, GC.blk)),
      K('metal', ex([[0.04, -0.036], [0.15, -0.036], [0.155, -0.05], [0.035, -0.05]], 0.05, GC.blk)),
      ...rail(-0.05, 0.47, 0.057, 0.03),
      K('metal', bx(0.004, 0.022, 0.06, 0.1, 0.024, 0x080808, 0.0225), bx(0.002, 0.024, 0.062, 0.1, 0.024, 0x202224, 0.024)),
      K('metal', cyl(0.009, 0.0, 0.04, 0.03, GC.blk, 0.026, 8), pinX(0.0035, 0.05, 0.16, -0.02, GC.steel), pinX(0.0035, 0.05, -0.03, -0.02, GC.steel)),
      ex([[0.22, -0.032], [0.48, -0.032], [0.48, 0.05], [0.22, 0.05]], 0.06, GC.fde),
      ...[0, 1, 2, 3].map(i => bx(0.064, 0.022, 0.03, 0.26 + i * 0.06, 0.012, 0x1a1a1a)),
      K('metal', cyl(0.017, -0.27, -0.06, 0.026, GC.blk), ...[0, 1, 2, 3, 4].map(i => bx(0.036, 0.004, 0.008, -0.25 + i * 0.03, 0.006, GC.blk))),
      ex([[-0.2, 0.052], [-0.37, 0.052], [-0.39, -0.078], [-0.34, -0.078], [-0.2, 0.002]], 0.045, GC.fde),
      ex([[-0.24, 0.054], [-0.34, 0.054], [-0.34, 0.066], [-0.25, 0.064]], 0.04, GC.fde2),
      bx(0.047, 0.13, 0.016, -0.392, -0.012, GC.blk),
      ex([[-0.045, -0.036], [0.0, -0.036], [-0.035, -0.142], [-0.077, -0.142], [-0.08, -0.128]], 0.034, GC.blk),
      ...trigger(0.0, -0.036, GC.blk),
      K('metal', cyl(0.0105, 0.48, 0.74, 0.015, GC.steel), cyl(0.014, 0.72, 0.79, 0.015, GC.blk, 0, 10), cyl(0.0055, 0.788, 0.7905, 0.015, 0x050505, 0, 8)),
      ...[0, 1, 2].map(i => K('metal', bx(0.03, 0.004, 0.03, 0.755, 0.015 + (i - 1) * 0.01, 0x0a0a0a))),
      K('metal', ex([[0.45, 0.05], [0.47, 0.05], [0.465, 0.1], [0.455, 0.1]], 0.012, GC.blk)),
      K('metal', bx(0.03, 0.02, 0.05, 0.08, 0.072, GC.blk), cyl(0.023, 0.045, 0.12, 0.104, GC.blk, 0, 14), cyl(0.025, 0.112, 0.122, 0.104, 0x111111, 0, 14), bx(0.014, 0.012, 0.014, 0.08, 0.13, GC.blk), pinX(0.006, 0.012, 0.08, 0.104, GC.blk, 0.028)),
      K('accent', cyl(0.019, 0.119, 0.123, 0.104, GC.lens, 0, 14)),
      K('metal', bx(0.008, 0.016, 0.03, 0.12, 0.03, GC.metal, -0.026), bx(0.004, 0.006, 0.02, -0.005, 0.004, GC.steel, -0.024)),
      swivel(-0.37, -0.07, 0),
    ],
    bolt: [K('metal', bx(0.04, 0.008, 0.03, -0.055, 0.046, GC.blk), bx(0.05, 0.008, 0.008, -0.068, 0.046, GC.blk))],
    mag: [K('metal', ex([[0.085, -0.036], [0.145, -0.036], [0.158, -0.2], [0.1, -0.206]], 0.028, GC.blk)), ex([[0.096, -0.2], [0.162, -0.195], [0.163, -0.207], [0.097, -0.213]], 0.032, GC.blk)],
  }),
  lmg: () => ({
    grip: [-0.04, -0.09], fore: 0.5, foreY: 0.01, foreR: 0.035, sightY: 0.112, muzzle: [0.93, 0.01], eject: [0.12, -0.02], shell: 0.9,
    body: [
      K('metal', ex([[-0.12, -0.04], [0.3, -0.04], [0.3, 0.062], [-0.12, 0.062]], 0.07, GC.park)),
      K('metal', ex([[-0.1, 0.062], [0.25, 0.062], [0.23, 0.088], [-0.08, 0.088]], 0.064, 0x2a2c27)),
      ...rail(-0.07, 0.22, 0.092, 0.03),
      K('metal', ex([[0.02, 0.1], [0.04, 0.14], [0.17, 0.14], [0.19, 0.1]], 0.018, GC.blk, 0, 0.003, [[0.05, 0.103], [0.06, 0.128], [0.155, 0.128], [0.165, 0.103]])),
      K('metal', bx(0.004, 0.03, 0.08, 0.12, -0.012, 0x070707, -0.036)),
      ...[[-0.08, 0.02], [0.0, -0.025], [0.26, -0.025], [0.26, 0.04]].map(([x, y]) => K('metal', pinX(0.004, 0.074, x, y, GC.steel))),
      K('metal', cyl(0.016, 0.3, 0.88, 0.01, GC.metal, 0, 12), cyl(0.021, 0.86, 0.93, 0.01, GC.blk, 0, 10), cyl(0.0075, 0.928, 0.9305, 0.01, 0x050505, 0, 8)),
      cyl(0.033, 0.3, 0.64, 0.01, 0x2b2d2a, 0, 14),
      ...Array.from({ length: 12 }, (_, i) => bx(0.068, 0.012, 0.016, 0.33 + (i >> 1) * 0.05, 0.01 + (i & 1 ? 0.024 : -0.024), 0x111211)),
      K('metal', bx(0.03, 0.05, 0.03, 0.66, 0.0, GC.park), ex([[0.85, 0.01], [0.865, 0.01], [0.862, 0.07], [0.853, 0.07]], 0.014, GC.blk)),
      K('metal', cyl(0.006, 0.4, 0.66, -0.03, GC.steel, 0.012, 6), cyl(0.006, 0.4, 0.66, -0.03, GC.steel, -0.012, 6), bx(0.034, 0.014, 0.018, 0.66, -0.03, GC.blk)),
      ex([[-0.12, 0.05], [-0.42, 0.03], [-0.44, -0.09], [-0.4, -0.1], [-0.36, -0.03], [-0.12, -0.035]], 0.044, GC.poly, 0, 0.003, [[-0.17, 0.022], [-0.36, 0.008], [-0.36, -0.01], [-0.17, -0.012]]),
      bx(0.048, 0.14, 0.016, -0.444, -0.03, 0x111213),
      ex([[-0.05, -0.04], [-0.005, -0.04], [-0.035, -0.15], [-0.078, -0.15], [-0.082, -0.134]], 0.036, GC.poly),
      ...trigger(-0.005, -0.04, GC.park),
      swivel(-0.38, -0.08, 0), swivel(0.6, -0.03, 0),
    ],
    bolt: [K('metal', bx(0.014, 0.012, 0.03, 0.2, 0.02, GC.steel, 0.04), pinX(0.008, 0.018, 0.2, 0.02, GC.steel, 0.05))],
    mag: [ex([[0.04, -0.04], [0.19, -0.04], [0.19, -0.18], [0.05, -0.18], [0.04, -0.17]], 0.075, GC.od, -0.01),
      bx(0.078, 0.012, 0.15, 0.115, -0.06, GC.od2, -0.01), K('metal', bx(0.006, 0.03, 0.06, 0.115, -0.12, GC.steel, -0.05)),
      ...[0, 1, 2, 3].map(i => K('accent', cyl(0.0045, 0.08 + i * 0.022, 0.13 + i * 0.022, -0.028, GC.brass, -0.044, 6)))],
  }),
  dmr: () => ({
    grip: [-0.035, -0.085], fore: 0.45, foreY: 0.009, foreR: 0.044, sightY: 0.118, muzzle: [0.96, 0.015], eject: [0.1, 0.022], shell: 1.1,
    body: [
      K('metal', ex([[-0.07, 0.0], [0.24, 0.0], [0.24, 0.052], [-0.07, 0.052]], 0.048, GC.tan)),
      K('metal', ex([[-0.07, -0.04], [0.18, -0.04], [0.2, 0.0], [-0.07, 0.0]], 0.05, GC.tan)),
      ...rail(-0.06, 0.6, 0.059, 0.03, GC.blk),
      K('metal', bx(0.004, 0.022, 0.06, 0.1, 0.024, 0x080808, 0.0245), pinX(0.0035, 0.054, 0.17, -0.022, GC.steel), pinX(0.0035, 0.054, -0.035, -0.022, GC.steel)),
      ex([[0.24, -0.034], [0.62, -0.034], [0.62, 0.052], [0.24, 0.052]], 0.062, 0x3d3f3a),
      ...Array.from({ length: 6 }, (_, i) => bx(0.066, 0.014, 0.04, 0.28 + i * 0.058, 0.01, 0x161716)),
      K('metal', cyl(0.012, 0.62, 0.9, 0.015, GC.steel), cyl(0.02, 0.89, 0.96, 0.015, GC.blk, 0, 10), cyl(0.0065, 0.958, 0.9605, 0.015, 0x050505, 0, 8)),
      ...[0, 1, 2].map(i => K('metal', bx(0.042, 0.006, 0.012, 0.905 + i * 0.018, 0.015, 0x0a0a0a))),
      ex([[-0.07, 0.05], [-0.42, 0.05], [-0.44, -0.09], [-0.39, -0.092], [-0.3, -0.04], [-0.07, -0.03]], 0.046, GC.poly),
      ex([[-0.2, 0.05], [-0.38, 0.05], [-0.38, 0.072], [-0.21, 0.07]], 0.04, GC.poly),
      bx(0.05, 0.145, 0.016, -0.442, -0.02, 0x111213),
      ex([[-0.045, -0.04], [0.0, -0.04], [-0.035, -0.145], [-0.077, -0.145], [-0.08, -0.13]], 0.034, GC.poly),
      ...trigger(0.0, -0.04, GC.tan),
      K('metal', cyl(0.016, -0.04, 0.24, 0.118, GC.blk, 0, 14), cyl(0.016, 0.18, 0.27, 0.118, GC.blk, 0, 16, 0.024), cyl(0.024, 0.27, 0.3, 0.118, GC.blk, 0, 16), cyl(0.021, -0.09, -0.03, 0.118, GC.blk, 0, 16)),
      K('metal', bx(0.024, 0.02, 0.024, 0.08, 0.14, GC.blk), pinX(0.012, 0.02, 0.08, 0.118, GC.blk, 0.025), bx(0.03, 0.05, 0.02, 0.0, 0.085, GC.metal), bx(0.03, 0.05, 0.02, 0.2, 0.085, GC.metal)),
      K('accent', cyl(0.021, 0.298, 0.302, 0.118, GC.lens, 0, 16), cyl(0.017, -0.091, -0.088, 0.118, 0x2a4a52, 0, 16)),
      swivel(-0.38, -0.08, 0), swivel(0.58, -0.04, 0),
    ],
    bolt: [K('metal', bx(0.04, 0.008, 0.03, -0.06, 0.048, GC.blk), bx(0.05, 0.008, 0.008, -0.072, 0.048, GC.blk))],
    mag: [K('metal', ex([[0.085, -0.04], [0.15, -0.04], [0.155, -0.15], [0.09, -0.152]], 0.03, GC.blk)), ex([[0.087, -0.148], [0.158, -0.146], [0.159, -0.158], [0.088, -0.16]], 0.034, GC.poly)],
  }),
  sniper: () => ({
    grip: [-0.09, -0.09], fore: 0.36, foreY: -0.005, foreR: 0.03, sightY: 0.1, muzzle: [1.0, 0.03], eject: [0.05, 0.05], shell: 1.4, pivots: { bolt: [0.0, 0.03] },
    body: [
      ex([[-0.5, 0.02], [-0.5, -0.095], [-0.36, -0.075], [-0.17, -0.05], [-0.13, -0.135], [-0.075, -0.135], [-0.045, -0.04], [0.47, -0.03], [0.47, 0.022]], 0.05, GC.od),
      ex([[-0.16, -0.045], [-0.14, -0.045], [-0.12, -0.115], [-0.135, -0.118]], 0.052, GC.od2),
      bx(0.052, 0.13, 0.016, -0.502, -0.035, GC.blk),
      ex([[-0.45, 0.02], [-0.22, 0.02], [-0.22, 0.05], [-0.42, 0.058]], 0.04, GC.od),
      K('metal', cyl(0.023, -0.13, 0.2, 0.03, GC.metal, 0, 16), bx(0.004, 0.022, 0.08, 0.05, 0.04, 0x070707, 0.022)),
      K('metal', cyl(0.0145, 0.2, 0.93, 0.03, GC.metal, 0, 14, 0.0125)),
      ...[0, 1, 2, 3].map(i => K('metal', bx(0.004, 0.004, 0.5, 0.6, 0.03 + Math.cos(i * Math.PI / 2) * 0.0135, 0x1a1c1f, Math.sin(i * Math.PI / 2) * 0.0135))),
      K('metal', cyl(0.021, 0.92, 1.0, 0.03, GC.blk, 0, 12), cyl(0.008, 0.998, 1.0005, 0.03, 0x050505, 0, 8)),
      ...[0, 1, 2].map(i => K('metal', bx(0.046, 0.009, 0.01, 0.935 + i * 0.02, 0.03, 0x0a0a0a))),
      ...trigger(-0.04, -0.04, GC.metal),
      K('metal', cyl(0.018, -0.08, 0.24, 0.1, GC.blk, 0, 14), cyl(0.019, 0.2, 0.28, 0.1, GC.blk, 0, 16, 0.03), cyl(0.032, 0.278, 0.3, 0.1, GC.blk, 0, 16), cyl(0.026, -0.13, -0.06, 0.1, GC.blk, 0, 16)),
      K('metal', bx(0.03, 0.03, 0.03, 0.08, 0.127, GC.blk), pinX(0.016, 0.02, 0.08, 0.127, GC.blk, 0, 12), bx(0.03, 0.03, 0.03, 0.08, 0.1, GC.blk, 0.025), pinX(0.015, 0.016, 0.08, 0.1, GC.blk, 0.04, 12)),
      K('accent', cyl(0.028, 0.298, 0.302, 0.1, GC.lens, 0, 16), cyl(0.022, -0.132, -0.129, 0.1, 0x2a4a52, 0, 16)),
      K('metal', bx(0.022, 0.045, 0.024, 0.0, 0.065, GC.metal), bx(0.022, 0.045, 0.024, 0.16, 0.065, GC.metal), ring(0.02, 0.004, 0.0, 0.1, GC.metal, 0, 'z'), ring(0.02, 0.004, 0.16, 0.1, GC.metal, 0, 'z')),
      K('metal', bx(0.012, 0.012, 0.2, 0.37, -0.045, GC.blk, 0.012), bx(0.012, 0.012, 0.2, 0.37, -0.045, GC.blk, -0.012), bx(0.04, 0.02, 0.03, 0.46, -0.04, GC.blk)),
      swivel(-0.42, -0.1, 0), swivel(0.44, -0.04, 0),
    ],
    bolt: [K('metal', cyl(0.016, -0.12, 0.02, 0.0, GC.steel, 0, 12), bx(0.008, 0.008, 0.05, -0.05, 0.0, GC.steel, 0.03)), K('metal', P(new THREE.SphereGeometry(0.014, 10, 8), GC.blk, [0.058, 0.0, 0.05]))],
    mag: [bx(0.036, 0.05, 0.085, 0.05, -0.055, GC.blk)],
  }),
  knife: () => ({
    grip: [-0.055, 0], fore: 0, sightY: 0, muzzle: [0.2, 0],
    body: [
      K('metal', ex([[0.012, 0.014], [0.15, 0.014], [0.198, 0.003], [0.21, -0.002], [0.185, -0.009], [0.11, -0.0145], [0.012, -0.0145]], 0.0055, 0x3a3e42, 0, 0.001)),
      K('metal', ex([[0.03, -0.009], [0.11, -0.0095], [0.185, -0.005], [0.205, -0.0015], [0.185, -0.0085], [0.11, -0.0145], [0.03, -0.0145]], 0.0062, 0xb9bec2, 0, 0.0006)),
      K('metal', bx(0.0064, 0.004, 0.1, 0.075, 0.006, 0x1d2023)),
      K('metal', ex([[0.0, 0.028], [0.012, 0.024], [0.012, -0.03], [0.0, -0.034], [-0.004, -0.004]], 0.022, GC.metal, 0, 0.002)),
      ex([[-0.112, 0.012], [-0.06, 0.016], [0.0, 0.016], [0.0, -0.016], [-0.03, -0.019], [-0.06, -0.014], [-0.09, -0.018], [-0.112, -0.013]], 0.024, GC.poly, 0, 0.004),
      ...[0, 1, 2, 3, 4].map(i => bx(0.0255, 0.03, 0.003, -0.015 - i * 0.017, -0.001, 0x15161a)),
      K('metal', cyl(0.014, -0.125, -0.11, 0.0, GC.steel, 0, 10), ring(0.008, 0.002, -0.13, 0.0, GC.steel, 0, 'x')),
    ],
  }),
  he: () => ({
    grip: [0, 0], fore: 0, sightY: 0, muzzle: [0, 0],
    body: [
      P(new THREE.SphereGeometry(0.031, 14, 10), GC.od, [0, 0.0, 0], null, [1, 1.22, 1]),
      ...[-0.018, 0, 0.018].map(y => K('accent', vcyl(0.0312 * Math.sqrt(1 - (y / 0.038) ** 2) + 0.0006, y - 0.0015, y + 0.0015, 0x2f3a28))),
      K('metal', vcyl(0.011, 0.034, 0.052, GC.steel), vcyl(0.008, 0.05, 0.058, GC.metal)),
      K('metal', bx(0.012, 0.064, 0.004, -0.014, 0.022, GC.steel, 0), bx(0.012, 0.004, 0.018, -0.006, 0.055, GC.steel)),
      K('metal', ring(0.011, 0.0018, 0.0, 0.05, 0xb0b4b6, 0.018, 'x')),
    ],
  }),
  flash: () => ({
    grip: [0, 0], fore: 0, sightY: 0, muzzle: [0, 0],
    body: [
      K('metal', vcyl(0.022, -0.05, 0.035, 0x7d868c, 0, 0, 16)),
      ...Array.from({ length: 8 }, (_, i) => { const a = i / 8 * Math.PI * 2; return bx(0.008, 0.016, 0.008, Math.cos(a) * 0.0205, 0.0, 0x1c1e20, Math.sin(a) * 0.0205); }),
      K('accent', vcyl(0.0225, -0.03, -0.022, 0xd8dde0, 0, 0, 16)),
      K('metal', vcyl(0.011, 0.035, 0.052, GC.steel), vcyl(0.008, 0.05, 0.058, GC.metal)),
      K('metal', bx(0.012, 0.07, 0.004, -0.025, 0.018, GC.steel, 0), bx(0.012, 0.004, 0.028, -0.011, 0.054, GC.steel)),
      K('metal', ring(0.011, 0.0018, 0.0, 0.05, 0xb0b4b6, 0.018, 'x')),
    ],
  }),
  smoke: () => ({
    grip: [0, 0], fore: 0, sightY: 0, muzzle: [0, 0],
    body: [
      K('metal', vcyl(0.024, -0.055, 0.04, 0x3e4639, 0, 0, 16)),
      K('accent', vcyl(0.0245, -0.01, 0.006, 0xc98a2a, 0, 0, 16)),
      ...Array.from({ length: 4 }, (_, i) => { const a = i / 4 * Math.PI * 2 + 0.4; return bx(0.006, 0.004, 0.006, Math.cos(a) * 0.016, 0.041, 0x111111, Math.sin(a) * 0.016); }),
      K('metal', vcyl(0.011, 0.04, 0.056, GC.steel), vcyl(0.008, 0.054, 0.062, GC.metal)),
      K('metal', bx(0.012, 0.074, 0.004, -0.027, 0.02, GC.steel, 0), bx(0.012, 0.004, 0.03, -0.012, 0.058, GC.steel)),
      K('metal', ring(0.011, 0.0018, 0.0, 0.054, 0xb0b4b6, 0.018, 'x')),
    ],
  }),
};

/* ---------------- склейка с UV и износом граней ---------------- */
// UV — коробочная проекция по нормали (1 ед. UV = 1/uvScale м), чтобы скины-текстуры ложились равномерно.
// Износ: скошенные грани выдавленных деталей светлее (потёртость металла/полимера).
const _c1 = new THREE.Color();
function mergeUV(parts, o = {}) {
  const sc = o.uvScale || 6, wearK = o.wear || 0;
  let vc = 0, ic = 0;
  for (const pt of parts) {
    if (!pt.g.attributes.normal) pt.g.computeVertexNormals();
    vc += pt.g.attributes.position.count;
    ic += pt.g.index ? pt.g.index.count : pt.g.attributes.position.count;
  }
  const pos = new Float32Array(vc * 3), nor = new Float32Array(vc * 3), uv = new Float32Array(vc * 2), col = new Float32Array(vc * 3), idx = new Uint32Array(ic);
  let vo = 0, io = 0;
  for (const pt of parts) {
    const g = pt.g, cnt = g.attributes.position.count, P = g.attributes.position.array, N = g.attributes.normal.array;
    pos.set(P.subarray(0, cnt * 3), vo * 3); nor.set(N.subarray(0, cnt * 3), vo * 3);
    _c1.setHex(pt.c);
    const jit = o.jitter ? 1 + (Math.random() - 0.5) * o.jitter : 1;
    const wm = pt.wear && wearK ? (pt.k === 'metal' || KIND_BY_COLOR[pt.c] === 'metal' ? 1 + wearK * 1.6 : 1 + wearK) : 1;
    for (let i = 0; i < cnt; i++) {
      const x = P[i * 3], y = P[i * 3 + 1], z = P[i * 3 + 2], ax = Math.abs(N[i * 3]), ay = Math.abs(N[i * 3 + 1]), az = Math.abs(N[i * 3 + 2]);
      let u, v;
      if (ax >= ay && ax >= az) { u = z; v = y; } else if (ay >= az) { u = x; v = z; } else { u = x; v = y; }
      uv[(vo + i) * 2] = u * sc; uv[(vo + i) * 2 + 1] = v * sc;
      const m = (wm > 1 && ax > 0.3 && ax < 0.95) ? wm : 1;
      const add = m > 1 ? 0.035 : 0;
      col[(vo + i) * 3] = Math.min(1, _c1.r * jit * m + add); col[(vo + i) * 3 + 1] = Math.min(1, _c1.g * jit * m + add); col[(vo + i) * 3 + 2] = Math.min(1, _c1.b * jit * m + add);
    }
    if (g.index) for (let i = 0; i < g.index.count; i++) idx[io++] = g.index.array[i] + vo;
    else for (let i = 0; i < cnt; i++) idx[io++] = i + vo;
    vo += cnt; g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  out.setAttribute('color', new THREE.BufferAttribute(col, 3));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  out.computeBoundingSphere();
  return out;
}
// части по видам материала → { metal: geo, polymer: geo, ... }
function mergeKinds(parts, o) {
  const by = {};
  for (const pt of parts) (by[kindOf(pt)] || (by[kindOf(pt)] = [])).push(pt);
  const out = {};
  for (const k in by) out[k] = mergeUV(by[k], o);
  return out;
}

/* ---------------- материалы ---------------- */
const gunEnv = (function () {
  try {
    const s = new THREE.Scene();
    const geo = new THREE.SphereGeometry(10, 24, 12), c = [], p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const y = p.getY(i) / 10;
      const sky = [1.25, 1.3, 1.35], hor = [0.8, 0.76, 0.68], gnd = [0.22, 0.19, 0.16];
      const t = y > 0 ? Math.pow(y, 0.6) : -Math.pow(-y, 0.5), a = t > 0 ? hor : hor, b = t > 0 ? sky : gnd, k = Math.abs(t);
      c.push(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k);
    }
    geo.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    s.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
    const lm = new THREE.MeshBasicMaterial({ color: new THREE.Color(5, 4.8, 4.4) });
    for (const [x, y, z, w, h] of [[6, 5, 3, 3, 1.4], [-5, 6, -4, 2, 2], [0, 8, 6, 5, 0.8]]) { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.2), lm); m.position.set(x, y, z); m.lookAt(0, 0, 0); s.add(m); }
    const pm = new THREE.PMREMGenerator(renderer);
    const t = pm.fromScene(s, 0.03).texture; pm.dispose();
    return t;
  } catch (e) { return null; }
})();
const metalTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#d4d4d4'; g.fillRect(0, 0, w, h); grain(g, w, h, 46);
  for (let i = 0; i < 40; i++) { g.strokeStyle = `rgba(255,255,255,${rand(0.15, 0.4)})`; g.lineWidth = rand(0.5, 1.2); g.beginPath(); const x = rand(0, w), y = rand(0, h), a = rand(0, 6.28), l = rand(4, 22); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke(); }
});
const polyTex = tex(128, 128, (g, w, h) => { g.fillStyle = '#e8e8e8'; g.fillRect(0, 0, w, h); grain(g, w, h, 30); });
const woodTex = tex(128, 128, (g, w, h) => {
  g.fillStyle = '#d9d0c4'; g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y++) { const v = Math.sin(y * 0.55 + Math.sin(y * 0.09) * 4) * 0.5 + 0.5; g.fillStyle = `rgba(70,40,20,${0.08 + v * 0.22})`; g.fillRect(0, y, w, 1); }
  for (let i = 0; i < 6; i++) { g.fillStyle = 'rgba(60,30,10,.25)'; g.beginPath(); g.ellipse(rand(0, w), rand(0, h), rand(4, 9), rand(1, 2), 0, 0, 6.3); g.fill(); }
  grain(g, w, h, 16);
});
const GUNMATS = {
  metal: new THREE.MeshStandardMaterial({ vertexColors: true, color: 0xd0d0d0, metalness: 0.72, roughness: 0.42, map: metalTex, roughnessMap: metalTex, envMap: gunEnv, envMapIntensity: 1.1 }),
  polymer: new THREE.MeshStandardMaterial({ vertexColors: true, color: 0xa8a8a8, metalness: 0.1, roughness: 0.62, map: polyTex, envMap: gunEnv, envMapIntensity: 0.6 }),
  wood: new THREE.MeshStandardMaterial({ vertexColors: true, color: 0x9a9a9a, metalness: 0.0, roughness: 0.48, map: woodTex, envMap: gunEnv, envMapIntensity: 0.55 }),
  accent: new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.45, roughness: 0.28, envMap: gunEnv, envMapIntensity: 1 }),
};
const gunMat = GUNMATS.polymer; // совместимость со старым кодом
function gunMatFor(wkey, kind) {
  if (typeof gunMaterial === 'function') { try { const m = gunMaterial(wkey, kind); if (m) return m; } catch (e) { console.error(e); } }
  return GUNMATS[kind] || GUNMATS.polymer;
}

/* ---------------- сборка ---------------- */
const GUNS = {};
for (const k in GUNDEF) {
  const d = GUNDEF[k](), gx = d.grip[0], gy = d.grip[1];
  const shift = list => (list || []).flat(4).map(pt => { pt.g.translate(0, -gy, gx); return pt; });
  const piv = (d.pivots && d.pivots.bolt) || [gx, gy];
  const pivot = V3(0, piv[1] - gy, -(piv[0] - gx));
  const body = shift(d.body), mag = shift(d.mag), pump = shift(d.pump), bolt = shift(d.bolt);
  const cl = list => list.map(pt => ({ g: pt.g.clone(), c: pt.c, k: pt.k, wear: pt.wear }));
  const full = [...cl(body), ...cl(mag), ...cl(pump), ...cl(bolt)];
  let magC = V3(0, -0.1, -0.08);
  if (mag.length) { const bb = new THREE.Box3(); for (const pt of mag) { pt.g.computeBoundingBox(); bb.union(pt.g.boundingBox); } magC = bb.getCenter(new THREE.Vector3()); }
  for (const pt of bolt) pt.g.translate(-pivot.x, -pivot.y, -pivot.z);
  const O = { wear: 0.5 };
  GUNS[k] = {
    full: mergeKinds(full, O),
    parts: { body: mergeKinds(body, O), mag: mag.length ? mergeKinds(mag, O) : null, pump: pump.length ? mergeKinds(pump, O) : null, bolt: bolt.length ? mergeKinds(bolt, O) : null },
    pivot, magC, fore: d.fore, foreY: (d.foreY || 0) - gy, foreR: d.foreR || 0.03, foreGrip: !!d.foreGrip, sight: d.sightY - gy,
    muzzle: V3(0, d.muzzle[1] - gy, -(d.muzzle[0] - gx)),
    eject: d.eject ? V3(0.03, d.eject[1] - gy, -(d.eject[0] - gx)) : null, shell: d.shell || 0.8, shellK: d.shellK || 'rifle',
  };
}
// группа мешей оружия по видам материала (вьюмодель, выпавшее оружие)
function gunGroup(wkey, kinds) {
  const g = new THREE.Group();
  for (const kind in kinds) {
    const m = new THREE.Mesh(kinds[kind], gunMatFor(wkey, kind));
    m.userData.kind = kind; m.userData.wkey = wkey; g.add(m);
  }
  return g;
}
// фиксированный набор мешей у бойца: меняем только геометрию и материал
function makeGunSlots(parent) {
  const slots = {};
  for (const kind of GUN_KINDS) { const m = new THREE.Mesh(undefined, GUNMATS[kind]); m.userData.kind = kind; m.visible = false; parent.add(m); slots[kind] = m; }
  return slots;
}
function setGunSlots(slots, wkey) {
  const f = GUNS[wkey].full;
  for (const kind of GUN_KINDS) {
    const m = slots[kind];
    if (f[kind]) { m.geometry = f[kind]; m.material = gunMatFor(wkey, kind); m.userData.wkey = wkey; m.visible = true; } else m.visible = false;
  }
}
// Для скинов: заново назначить материалы во всех мешах оружия (вьюмодель, бойцы, выпавшее оружие)
function refreshGunMaterials() {
  const fix = o => o.traverse(m => { if (m.isMesh && m.userData.kind && m.userData.wkey) m.material = gunMatFor(m.userData.wkey, m.userData.kind); });
  fix(vmScene); fix(scene);
}
