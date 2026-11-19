import * as W from '/shared/world.js';
import { makeCar, spinWheels } from './models.js';

// Направления: 0:+x 1:+z 2:-x 3:-z. Правостороннее движение.
const DIRS = [[1, 0], [0, 1], [-1, 0], [0, -1]];
const YAW = [Math.PI / 2, 0, -Math.PI / 2, Math.PI];
const rc = W.roadCenter, L = W.LANE, G = W.GRID;
const step = (d) => (d < 2 ? 1 : -1);
const alongX = (d) => d % 2 === 0;

// Координата полосы направления d на дороге road (по поперечной оси).
function laneCoord(d, road) {
  return d === 0 ? rc(road) + L : d === 2 ? rc(road) - L : d === 1 ? rc(road) - L : rc(road) + L;
}
function lerpAngle(a, b, t) {
  let d = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
  return a + d * t;
}

const MODELS = ['kroha', 'kroha', 'vektor', 'vektor', 'taiga'];

export class Traffic {
  constructor(scene, count = 28) {
    this.cars = [];
    for (let n = 0; n < count; n++) {
      const d = Math.floor(Math.random() * 4), road = Math.floor(Math.random() * (G + 1));
      const seg = Math.floor(Math.random() * G), along = seg * W.CELL + W.ROAD + 10 + Math.random() * 44;
      const model = MODELS[Math.floor(Math.random() * MODELS.length)];
      const c = {
        d, road, model, spd: 0, max: 9 + Math.random() * 5, skip: -1, stuck: 0, ghost: 0,
        x: alongX(d) ? along : laneCoord(d, road), z: alongX(d) ? laneCoord(d, road) : along,
        mesh: makeCar(model, W.CAR_COLORS[Math.floor(Math.random() * W.CAR_COLORS.length)]),
      };
      c.ry = YAW[d];
      this.plan(c);
      scene.add(c.mesh);
      this.cars.push(c);
    }
  }

  nextK(c) {
    const a = alongX(c.d) ? c.x : c.z, s = step(c.d);
    let k = s > 0 ? Math.floor((a + 0.5 - W.ROAD / 2) / W.CELL) + 1 : Math.ceil((a - 0.5 - W.ROAD / 2) / W.CELL) - 1;
    if (k === c.skip) k += s;
    return k;
  }

  plan(c) {
    const k = this.nextK(c), s = step(c.d);
    if (k < 0 || k > G) { c.d = (c.d + 2) % 4; c.skip = -1; return this.plan(c); }
    const opts = [];
    if (k + s >= 0 && k + s <= G) opts.push(c.d, c.d);
    for (const pd of [(c.d + 1) % 4, (c.d + 3) % 4]) {
      const nr = c.road + step(pd);
      if (nr >= 0 && nr <= G) opts.push(pd);
    }
    const nd = opts[Math.floor(Math.random() * opts.length)];
    c.k = k; c.nd = nd;
    c.tc = nd === c.d ? rc(k) : laneCoord(nd, k);
  }

  update(dt, obstacles) {
    for (const c of this.cars) {
      const [fx, fz] = DIRS[c.d];
      // тормозим, если впереди кто-то есть
      let blocked = false;
      const check = (ox, oz, isTraffic) => {
        if (isTraffic && c.ghost > 0) return;
        const rx = ox - c.x, rz = oz - c.z, f = rx * fx + rz * fz;
        if (f > 0.5 && f < 9 && Math.abs(rx * fz - rz * fx) < 2.3) blocked = true;
      };
      for (const o of obstacles) check(o.x, o.z, false);
      for (const o of this.cars) if (o !== c) check(o.x, o.z, true);
      c.ghost = Math.max(0, c.ghost - dt);
      if (blocked) {
        c.spd = Math.max(0, c.spd - 25 * dt);
        c.stuck += dt;
        if (c.stuck > 4) { c.ghost = 2; c.stuck = 0; }
      } else {
        c.stuck = 0;
        c.spd = Math.min(c.max, c.spd + 4 * dt);
      }
      // движение и повороты
      const move = c.spd * dt, s = step(c.d);
      if (alongX(c.d)) c.x += fx * move; else c.z += fz * move;
      const a = alongX(c.d) ? c.x : c.z;
      if (s > 0 ? a >= c.tc : a <= c.tc) {
        if (alongX(c.d)) c.x = c.tc; else c.z = c.tc;
        c.skip = c.k;
        if (c.nd !== c.d) { c.d = c.nd; c.road = c.k; }
        this.plan(c);
      }
      c.ry = lerpAngle(c.ry, YAW[c.d], 1 - Math.exp(-dt * 7));
      c.mesh.position.set(c.x, 0, c.z);
      c.mesh.rotation.y = c.ry;
      spinWheels(c.mesh, c.spd, dt);
    }
  }
}
