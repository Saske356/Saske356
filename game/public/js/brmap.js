// Район внешней карты (cache/brmap/*.glb, делается tools/map2glb.py) вместо нашего города из коробок.
// Высота земли и препятствия — по треугольникам карты, разложенным по сетке 4×4 м.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const CELL = 4;

export async function loadMap(scene, name = 'district1', base = '/cache/brmap') {
  const meta = await (await fetch(`${base}/${name}.json`, { cache: 'no-cache' })).json();
  const gltf = await new GLTFLoader().loadAsync(`${base}/${name}.glb`);
  const root = gltf.scene;
  const tris = []; // [ax,ay,az, bx,by,bz, cx,cy,cz]
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.receiveShadow = true;
    o.castShadow = false;
    const m = o.material;
    const cutout = m.alphaTest > 0 || m.transparent;
    if (cutout) { m.alphaTest = m.alphaTest || 0.45; m.side = THREE.DoubleSide; }
    if (cutout) return; // листва и провода не мешают ходить
    const pos = o.geometry.attributes.position, idx = o.geometry.index;
    o.updateMatrixWorld();
    const v = new THREE.Vector3(), e = o.matrixWorld.elements;
    const get = (i) => { v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); return [v.x, v.y, v.z]; };
    const n = idx ? idx.count : pos.count;
    for (let k = 0; k < n; k += 3) {
      const a = get(idx ? idx.getX(k) : k), b = get(idx ? idx.getX(k + 1) : k + 1), c = get(idx ? idx.getX(k + 2) : k + 2);
      tris.push([...a, ...b, ...c]);
    }
    void e;
  });
  scene.add(root);

  // сетка: клетка → индексы треугольников, чья проекция её задевает
  const grid = new Map();
  tris.forEach((t, i) => {
    const x0 = Math.floor(Math.min(t[0], t[3], t[6]) / CELL), x1 = Math.floor(Math.max(t[0], t[3], t[6]) / CELL);
    const z0 = Math.floor(Math.min(t[2], t[5], t[8]) / CELL), z1 = Math.floor(Math.max(t[2], t[5], t[8]) / CELL);
    if ((x1 - x0 + 1) * (z1 - z0 + 1) > 4000) return; // огромные плоскости-подложки пропускаем
    for (let x = x0; x <= x1; x++) for (let z = z0; z <= z1; z++) {
      const key = x * 100003 + z;
      let list = grid.get(key);
      if (!list) grid.set(key, (list = []));
      list.push(i);
    }
  });

  // все высоты поверхностей под точкой (x, z)
  function heights(x, z) {
    const list = grid.get(Math.floor(x / CELL) * 100003 + Math.floor(z / CELL));
    const out = [];
    if (!list) return out;
    for (const i of list) {
      const t = tris[i];
      const d = (t[5] - t[8]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[2] - t[8]);
      if (Math.abs(d) < 1e-9) continue;
      const l1 = ((t[5] - t[8]) * (x - t[6]) + (t[6] - t[3]) * (z - t[8])) / d;
      const l2 = ((t[8] - t[2]) * (x - t[6]) + (t[0] - t[6]) * (z - t[8])) / d;
      const l3 = 1 - l1 - l2;
      if (l1 < -1e-4 || l2 < -1e-4 || l3 < -1e-4) continue;
      out.push(l1 * t[1] + l2 * t[4] + l3 * t[7]);
    }
    return out;
  }
  /** Высота земли под точкой: самая высокая поверхность, на которую можно шагнуть с высоты y. */
  function ground(x, z, y = 1e9, step = 1.2) {
    let best = -Infinity;
    for (const h of heights(x, z)) if (h <= y + step && h > best) best = h;
    return best === -Infinity ? 0 : best;
  }
  /** Есть ли над точкой что-то «стеной» (крыша здания выше головы, но не мост высоко над ней). */
  function blocked(x, z, y, step = 1.2) {
    for (const h of heights(x, z)) if (h > y + step && h < y + 40) return true;
    return false;
  }
  // спавн: ближайшая к центру точка на земле, где нет препятствий
  let spawn = meta.spawn;
  search: for (let r = 0; r < 200; r += 4) {
    for (let a = 0; a < Math.PI * 2; a += Math.PI / 8) {
      const x = meta.spawn[0] + Math.cos(a) * r, z = meta.spawn[1] + Math.sin(a) * r;
      const hs = heights(x, z);
      if (!hs.length) continue;
      const g = Math.min(...hs);
      if (!blocked(x, z, g)) { spawn = [x, z]; break search; }
    }
  }
  return { root, ground, blocked, spawn, meta, minimap: `${base}/${name}.png` };
}
