import * as THREE from 'three';
import * as W from '/shared/world.js';
import { textSprite, makeCar, mat } from './models.js';

// Текстуры фасада: стены с окнами и карта "горящих" окон для ночи.
function facadeTextures() {
  const mk = () => { const c = document.createElement('canvas'); c.width = c.height = 256; return c; };
  const wall = mk(), glow = mk(), g = wall.getContext('2d'), e = glow.getContext('2d');
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 256, 256);
  e.fillStyle = '#000000'; e.fillRect(0, 0, 256, 256);
  g.fillStyle = 'rgba(0,0,0,0.08)';
  for (let f = 0; f < 4; f++) g.fillRect(0, f * 64 + 60, 256, 4);
  for (let f = 0; f < 4; f++) for (let i = 0; i < 8; i++) {
    const x = i * 32 + 7, y = f * 64 + 14;
    g.fillStyle = '#56687c'; g.fillRect(x, y, 18, 34);
    g.fillStyle = 'rgba(255,255,255,0.25)'; g.fillRect(x, y, 18, 6);
    if (Math.random() < 0.38) { e.fillStyle = Math.random() < 0.5 ? '#ffd890' : '#fff1c9'; e.fillRect(x, y, 18, 34); }
  }
  const tw = new THREE.CanvasTexture(wall), tg = new THREE.CanvasTexture(glow);
  for (const t of [tw, tg]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4; }
  tw.colorSpace = tg.colorSpace = THREE.SRGBColorSpace;
  return { tw, tg };
}

// UV в метрах: одна плитка текстуры = 16 м × 14 м (8 окон × 4 этажа).
function buildingGeo(w, h, d) {
  const g = new THREE.BoxGeometry(w, h, d), uv = g.attributes.uv;
  const dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++) {
    const i = f * 4 + k;
    uv.setXY(i, (uv.getX(i) * dims[f][0]) / 16, (uv.getY(i) * dims[f][1]) / 14);
  }
  return g;
}

function instanced(geo, material, list, place) {
  const m = new THREE.InstancedMesh(geo, material, list.length), o = new THREE.Object3D();
  list.forEach((item, i) => { o.position.set(0, 0, 0); o.rotation.set(0, 0, 0); o.scale.set(1, 1, 1); place(o, item, i); o.updateMatrix(); m.setMatrixAt(i, o.matrix); });
  m.instanceMatrix.needsUpdate = true;
  return m;
}

export function buildCity(scene, city) {
  const out = { windowMats: [], lampMat: null, markers: [], water: null };
  const S = W.SIZE;

  const grass = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.MeshLambertMaterial({ color: 0x4d7238 }));
  grass.rotation.x = -Math.PI / 2; grass.position.set(S / 2, -0.06, S / 2); grass.receiveShadow = true;
  const asphalt = new THREE.Mesh(new THREE.PlaneGeometry(S, S), new THREE.MeshLambertMaterial({ color: 0x3a3d43 }));
  asphalt.rotation.x = -Math.PI / 2; asphalt.position.set(S / 2, 0, S / 2); asphalt.receiveShadow = true;
  scene.add(grass, asphalt);

  // тротуары
  const blocks = [];
  for (let bz = 0; bz < W.GRID; bz++) for (let bx = 0; bx < W.GRID; bx++) blocks.push(W.blockRect(bx, bz));
  const walk = instanced(new THREE.BoxGeometry(W.BLOCK, W.CURB, W.BLOCK), new THREE.MeshLambertMaterial({ color: 0x9a9c9e }), blocks,
    (o, b) => o.position.set(b.x0 + W.BLOCK / 2, W.CURB / 2, b.z0 + W.BLOCK / 2));
  walk.receiveShadow = true; scene.add(walk);
  const inner = instanced(new THREE.PlaneGeometry(W.BLOCK - 3, W.BLOCK - 3), new THREE.MeshLambertMaterial({ color: 0x7d8084 }), blocks,
    (o, b) => { o.rotation.x = -Math.PI / 2; o.position.set(b.x0 + W.BLOCK / 2, W.CURB + 0.01, b.z0 + W.BLOCK / 2); });
  inner.receiveShadow = true; scene.add(inner);
  const parks = instanced(new THREE.PlaneGeometry(W.BLOCK - 8, W.BLOCK - 8), new THREE.MeshLambertMaterial({ color: 0x5b8a3f }), city.parks,
    (o, b) => { o.rotation.x = -Math.PI / 2; o.position.set(b.x0 + W.BLOCK / 2, W.CURB + 0.02, b.z0 + W.BLOCK / 2); });
  parks.receiveShadow = true; scene.add(parks);

  // разметка: прерывистая осевая
  const dashes = [];
  for (let i = 0; i <= W.GRID; i++) for (let a = 0; a < W.GRID; a++) for (let k = 0; k < 10; k++) {
    const along = a * W.CELL + W.ROAD + 3 + k * 6.2;
    dashes.push([W.roadCenter(i), along, 0], [along, W.roadCenter(i), 1]);
  }
  const dg = new THREE.PlaneGeometry(0.22, 3); dg.rotateX(-Math.PI / 2);
  scene.add(instanced(dg, new THREE.MeshLambertMaterial({ color: 0xd9d9d9 }), dashes,
    (o, [x, z, rot]) => { o.position.set(x, 0.02, z); o.rotation.y = rot ? Math.PI / 2 : 0; }));
  // пешеходные переходы у перекрёстков
  const zebra = [];
  for (let i = 0; i <= W.GRID; i++) for (let j = 0; j <= W.GRID; j++) {
    const cx = W.roadCenter(i), cz = W.roadCenter(j);
    for (let s = -5; s <= 5; s += 2) {
      if (j > 0) zebra.push([cx + s, cz - W.ROAD / 2 - 1.6, 0]);
      if (i > 0) zebra.push([cx - W.ROAD / 2 - 1.6, cz + s, 1]);
    }
  }
  const zg = new THREE.PlaneGeometry(1, 2.6); zg.rotateX(-Math.PI / 2);
  scene.add(instanced(zg, new THREE.MeshLambertMaterial({ color: 0xcfcfcf }), zebra,
    (o, [x, z, rot]) => { o.position.set(x, 0.021, z); o.rotation.y = rot ? Math.PI / 2 : 0; }));

  // здания
  const { tw, tg } = facadeTextures();
  const sideMats = new Map(), roofMats = new Map();
  const getMats = (color) => {
    if (!sideMats.has(color)) {
      const m = new THREE.MeshLambertMaterial({ color, map: tw, emissiveMap: tg, emissive: 0xffffff, emissiveIntensity: 0 });
      sideMats.set(color, m); out.windowMats.push(m);
      roofMats.set(color, new THREE.MeshLambertMaterial({ color: new THREE.Color(color).multiplyScalar(0.55) }));
    }
    const s = sideMats.get(color), r = roofMats.get(color);
    return [s, s, r, r, s, s];
  };
  for (const b of city.buildings) {
    const w = b.x1 - b.x0, d = b.z1 - b.z0;
    const mesh = new THREE.Mesh(buildingGeo(w, b.h, d), getMats(b.color));
    mesh.position.set(b.x0 + w / 2, W.CURB + b.h / 2, b.z0 + d / 2);
    mesh.castShadow = mesh.receiveShadow = true;
    scene.add(mesh);
    if (b.h > 20 && Math.random() < 0.5) {
      const top = new THREE.Mesh(new THREE.BoxGeometry(w * 0.3, 2.5, d * 0.3), mat(0x6d7178));
      top.position.set(b.x0 + w / 2, W.CURB + b.h + 1.25, b.z0 + d / 2); top.castShadow = true;
      scene.add(top);
    }
    if (b.sign) {
      const s = textSprite(b.sign, { size: 46, color: '#ffe08a', scale: 0.035 });
      s.position.set(b.x0 + w / 2, W.CURB + b.h + 1.8, b.z0);
      scene.add(s);
    }
  }

  // фонтан на площади
  for (const f of city.boxes.filter((b) => b.fountain)) {
    const cx = (f.x0 + f.x1) / 2, cz = (f.z0 + f.z1) / 2;
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(4.6, 4.8, 0.9, 28), mat(0xb7b2a8));
    rim.position.set(cx, W.CURB + 0.45, cz); rim.castShadow = rim.receiveShadow = true;
    const water = new THREE.Mesh(new THREE.CircleGeometry(4.2, 28), new THREE.MeshLambertMaterial({ color: 0x3f8fc7, emissive: 0x0a2440 }));
    water.rotation.x = -Math.PI / 2; water.position.set(cx, W.CURB + 0.8, cz);
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.6, 3, 10), mat(0xb7b2a8));
    col.position.set(cx, W.CURB + 1.5, cz); col.castShadow = true;
    scene.add(rim, water, col);
    out.water = water;
  }

  // деревья
  const trunk = new THREE.CylinderGeometry(0.15, 0.22, 2.2, 6); trunk.translate(0, 1.1, 0);
  const crown = new THREE.IcosahedronGeometry(1.5, 0); crown.translate(0, 3.1, 0);
  const tScale = city.trees.map(() => 0.8 + Math.random() * 0.5);
  const tm = instanced(trunk, mat(0x6b4a2f), city.trees, (o, [x, z], i) => { o.position.set(x, W.groundHeight(x, z), z); o.scale.setScalar(tScale[i]); });
  const cm = instanced(crown, mat(0x3f7d34), city.trees, (o, [x, z], i) => { o.position.set(x, W.groundHeight(x, z), z); o.scale.setScalar(tScale[i]); o.rotation.y = i; });
  tm.castShadow = cm.castShadow = true;
  scene.add(tm, cm);

  // фонари по углам кварталов
  const lamps = [];
  for (const b of blocks) lamps.push([b.x0 + 1, b.z0 + 1], [b.x1 - 1, b.z0 + 1], [b.x0 + 1, b.z1 - 1], [b.x1 - 1, b.z1 - 1]);
  const pole = new THREE.CylinderGeometry(0.07, 0.1, 5.5, 6); pole.translate(0, 2.75, 0);
  const bulb = new THREE.BoxGeometry(0.5, 0.18, 0.5); bulb.translate(0, 5.5, 0);
  out.lampMat = new THREE.MeshLambertMaterial({ color: 0xfff3d0, emissive: 0xffe2a0, emissiveIntensity: 0 });
  scene.add(instanced(pole, mat(0x3c3f44), lamps, (o, [x, z]) => o.position.set(x, W.CURB, z)));
  scene.add(instanced(bulb, out.lampMat, lamps, (o, [x, z]) => o.position.set(x, W.CURB, z)));

  // декоративные машины (автосалон, автопарк)
  for (const d of city.decor) {
    const car = makeCar(d.model, d.color);
    car.position.set(d.x, W.groundHeight(d.x, d.z), d.z); car.rotation.y = d.ry;
    scene.add(car);
  }

  // маркеры мест
  for (const [id, p] of Object.entries(W.PLACES)) {
    if (p.hidden) continue;
    const g = new THREE.Group(), color = new THREE.Color(p.color);
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, 1.4, 24, 1, true),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
    ring.position.y = 0.7;
    const disc = new THREE.Mesh(new THREE.CircleGeometry(1.2, 24), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, depthWrite: false }));
    disc.rotation.x = -Math.PI / 2; disc.position.y = 0.03;
    const label = textSprite(p.name, { size: 30, color: p.color });
    label.position.y = 2.6;
    g.add(ring, disc, label);
    g.position.set(p.pos[0], W.groundHeight(p.pos[0], p.pos[1]), p.pos[1]);
    scene.add(g);
    out.markers.push({ id, group: g, ring });
  }
  return out;
}

// Столб света для чекпоинтов и GPS-меток.
export function makeBeam(color) {
  const g = new THREE.Group();
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 40, 20, 1, true),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false, fog: false }));
  beam.position.y = 20;
  const disc = new THREE.Mesh(new THREE.RingGeometry(1.3, 1.9, 28), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
  disc.rotation.x = -Math.PI / 2; disc.position.y = 0.05;
  g.add(beam, disc);
  g.visible = false;
  return g;
}
