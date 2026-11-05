'use strict';
/* ---------------- геометрия: заготовки ---------------- */
// Скруглённый брусок: вершины коробки притягиваются к ядру и выталкиваются на радиус скругления
function rbox(w, h, d, r, s = 3) {
  r = Math.min(r, w / 2, h / 2, d / 2) * 0.999;
  const g = new THREE.BoxGeometry(w, h, d, s, s, s), p = g.attributes.position, n = g.attributes.normal;
  const ix = w / 2 - r, iy = h / 2 - r, iz = d / 2 - r, v = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    c.set(clamp(v.x, -ix, ix), clamp(v.y, -iy, iy), clamp(v.z, -iz, iz));
    v.sub(c);
    if (v.lengthSq() > 1e-12) { v.normalize(); n.setXYZ(i, v.x, v.y, v.z); v.multiplyScalar(r); }
    p.setXYZ(i, c.x + v.x, c.y + v.y, c.z + v.z);
  }
  return g;
}
const _up = V3(0, 1, 0);
function limbGeo(a, b, r, seg = 8) {
  const len = Math.max(0.001, a.distanceTo(b));
  const g = new THREE.CapsuleGeometry(r, len, 3, seg);
  const q = new THREE.Quaternion().setFromUnitVectors(_up, b.clone().sub(a).normalize());
  g.applyQuaternion(q); g.translate((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
  return g;
}
function P(g, c, p, r, s) {
  if (s) g.scale(s[0], s[1], s[2]);
  if (r) g.applyQuaternion(new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0], r[1], r[2], 'YXZ')));
  if (p) g.translate(p[0], p[1], p[2]);
  return { g, c };
}
const _col = new THREE.Color();
// склейка частей в одну геометрию с цветами вершин: один вызов отрисовки на кость
function merge(parts) {
  let vc = 0, ic = 0;
  for (const pt of parts) {
    if (!pt.g.attributes.normal) pt.g.computeVertexNormals();
    vc += pt.g.attributes.position.count;
    ic += pt.g.index ? pt.g.index.count : pt.g.attributes.position.count;
  }
  const pos = new Float32Array(vc * 3), nor = new Float32Array(vc * 3), col = new Float32Array(vc * 3), idx = new Uint32Array(ic);
  let vo = 0, io = 0;
  for (const pt of parts) {
    const g = pt.g, cnt = g.attributes.position.count;
    pos.set(g.attributes.position.array.subarray(0, cnt * 3), vo * 3);
    nor.set(g.attributes.normal.array.subarray(0, cnt * 3), vo * 3);
    _col.setHex(pt.c);
    for (let i = 0; i < cnt; i++) { col[(vo + i) * 3] = _col.r; col[(vo + i) * 3 + 1] = _col.g; col[(vo + i) * 3 + 2] = _col.b; }
    if (g.index) for (let i = 0; i < g.index.count; i++) idx[io++] = g.index.array[i] + vo;
    else for (let i = 0; i < cnt; i++) idx[io++] = i + vo;
    vo += cnt; g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  out.setAttribute('color', new THREE.BufferAttribute(col, 3));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  out.computeBoundingSphere();
  return out;
}
