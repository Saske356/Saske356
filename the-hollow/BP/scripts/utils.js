// Общие помощники: векторы, рандом, лучи видимости, освещённость, команды.
import { world } from "@minecraft/server";

// ---------- рандом ----------
export const rand = (a, b) => a + Math.random() * (b - a);
export const randInt = (a, b) => Math.floor(rand(a, b + 1));
export const chance = (p) => Math.random() < p;
export const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

// ---------- векторы ----------
export const vadd = (a, b) => ({ x: a.x + b.x, y: a.y + b.y, z: a.z + b.z });
export const vsub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
export const vscale = (a, s) => ({ x: a.x * s, y: a.y * s, z: a.z * s });
export const vlen = (a) => Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z);
export const vdot = (a, b) => a.x * b.x + a.y * b.y + a.z * b.z;
export const vdist = (a, b) => vlen(vsub(a, b));
export const vnorm = (a) => {
  const l = vlen(a) || 1;
  return { x: a.x / l, y: a.y / l, z: a.z / l };
};
export const floorV = (a) => ({ x: Math.floor(a.x), y: Math.floor(a.y), z: Math.floor(a.z) });
export const center = (b) => ({ x: b.x + 0.5, y: b.y, z: b.z + 0.5 });

// ---------- сущности ----------
export function isValid(e) {
  try {
    if (!e) return false;
    return typeof e.isValid === "function" ? e.isValid() : !!e.isValid;
  } catch {
    return false;
  }
}

export function getEntity(id) {
  try {
    const e = world.getEntity(id);
    return isValid(e) ? e : undefined;
  } catch {
    return undefined;
  }
}

export function getPlayer(id) {
  return world.getAllPlayers().find((p) => p.id === id);
}

export function isNight() {
  const t = world.getTimeOfDay();
  return t >= 13000 && t < 23000;
}

export function inOverworld(player) {
  return player.dimension.id === "minecraft:overworld";
}

/** Выполнить команду от имени сущности/измерения (совместимо с разными версиями API). */
export function runCmd(target, cmd) {
  try {
    if (typeof target.runCommand === "function") return target.runCommand(cmd);
    return target.runCommandAsync(cmd);
  } catch {
    return undefined;
  }
}

// ---------- блоки ----------
export function getBlock(dim, loc) {
  try {
    return dim.getBlock(floorV(loc));
  } catch {
    return undefined;
  }
}

const SEE_THROUGH = [
  "glass", "grass", "fern", "flower", "tulip", "dandelion", "poppy", "orchid", "allium",
  "bluet", "daisy", "cornflower", "lily", "torch", "sapling", "vine", "carpet", "rail",
  "button", "lever", "pressure_plate", "snow_layer", "dead_bush", "sugar_cane", "web",
  "fence", "bars", "lantern", "sign", "banner", "ladder", "deadbush", "short_grass",
  "tall_grass", "seagrass", "kelp", "wheat", "carrots", "potatoes", "beetroot", "pane",
];

/** Можно ли видеть сквозь блок. Незагруженный блок считаем непрозрачным. */
export function isSeeThrough(block) {
  if (!block) return false;
  try {
    if (block.isAir || block.isLiquid) return true;
    const id = block.typeId;
    return SEE_THROUGH.some((k) => id.includes(k));
  } catch {
    return false;
  }
}

/** Блок, на котором можно стоять. */
export function isSolidGround(block) {
  if (!block) return false;
  try {
    if (block.isAir || block.isLiquid) return false;
    const id = block.typeId;
    if (id.includes("leaves")) return false;
    return !isSeeThrough(block) || id.includes("glass");
  } catch {
    return false;
  }
}

export function isFree(block) {
  if (!block) return false;
  try {
    if (block.isLiquid) return false;
    return block.isAir || (isSeeThrough(block) && !block.typeId.includes("fence") && !block.typeId.includes("glass"));
  } catch {
    return false;
  }
}

/** Прямая видимость между двумя точками (шагаем по 0.4 блока). */
export function lineOfSight(dim, from, to) {
  const d = vsub(to, from);
  const len = vlen(d);
  if (len < 1) return true;
  const dir = vscale(d, 1 / len);
  for (let t = 0.6; t < len - 0.6; t += 0.4) {
    const b = getBlock(dim, vadd(from, vscale(dir, t)));
    if (!isSeeThrough(b)) return false;
  }
  return true;
}

/** Первое препятствие на пути луча (расстояние от from), или -1. */
export function firstObstacle(dim, from, to) {
  const d = vsub(to, from);
  const len = vlen(d);
  const dir = vscale(d, 1 / (len || 1));
  for (let t = 0.6; t < len - 0.6; t += 0.4) {
    const b = getBlock(dim, vadd(from, vscale(dir, t)));
    if (!isSeeThrough(b)) return t;
  }
  return -1;
}

/** Найти землю в колонне x,z: блок под ногами твёрдый, сверху `height` свободных блоков. */
export function findGround(dim, x, z, aroundY, height = 4, up = 12, down = 16) {
  for (let y = Math.floor(aroundY) + up; y >= Math.floor(aroundY) - down; y--) {
    const below = getBlock(dim, { x, y: y - 1, z });
    if (!isSolidGround(below)) continue;
    let ok = true;
    for (let h = 0; h < height; h++) {
      if (!isFree(getBlock(dim, { x, y: y + h, z }))) {
        ok = false;
        break;
      }
    }
    if (ok) return { x: x + 0.5, y, z: z + 0.5 };
  }
  return undefined;
}

/** Перебрать блоки в кубе вокруг точки. */
export function scanBlocks(dim, c, r, ry, predicate, limit = 16) {
  const out = [];
  const base = floorV(c);
  for (let dx = -r; dx <= r; dx++)
    for (let dz = -r; dz <= r; dz++)
      for (let dy = -ry; dy <= ry; dy++) {
        const b = getBlock(dim, { x: base.x + dx, y: base.y + dy, z: base.z + dz });
        if (b && predicate(b)) {
          out.push(b);
          if (out.length >= limit) return out;
        }
      }
  return out;
}

// ---------- освещение ----------
const LIGHT_SOURCES = {
  torch: 14, lantern: 15, glowstone: 15, sea_lantern: 15, lit_pumpkin: 15, campfire: 15,
  shroomlight: 15, lava: 15, fire: 15, beacon: 15, end_rod: 14, froglight: 15,
  lit_redstone_lamp: 15, lit_furnace: 13, lit_smoker: 13, lit_blast_furnace: 13,
  crying_obsidian: 10, glow_lichen: 7, sea_pickle: 6, candle: 3, redstone_torch: 7,
  magma: 3, conduit: 15, respawn_anchor: 15, enchanting_table: 7, amethyst_cluster: 5,
};

function sourceLevel(id) {
  const name = id.replace("minecraft:", "");
  if (name.startsWith("soul_")) return 10;
  let best = 0;
  for (const k in LIGHT_SOURCES) if (name.includes(k)) best = Math.max(best, LIGHT_SOURCES[k]);
  return best;
}

/**
 * Уровень света в точке. Если в API есть getLightLevel — берём его,
 * иначе считаем приблизительно: небо + ближайшие источники света.
 */
export function lightLevel(dim, loc) {
  try {
    if (typeof dim.getLightLevel === "function") return dim.getLightLevel(floorV(loc));
  } catch {}

  const p = floorV(loc);
  // Открыто ли небо над головой?
  let sky = true;
  for (let y = p.y + 2; y < p.y + 40; y++) {
    const b = getBlock(dim, { x: p.x, y, z: p.z });
    if (b && !b.isAir && !isSeeThrough(b)) {
      sky = false;
      break;
    }
  }
  let level = isNight() ? (sky ? 4 : 0) : sky ? 15 : 2;

  const R = 6;
  for (let dx = -R; dx <= R; dx++)
    for (let dz = -R; dz <= R; dz++)
      for (let dy = -3; dy <= 3; dy++) {
        const b = getBlock(dim, { x: p.x + dx, y: p.y + dy, z: p.z + dz });
        if (!b || b.isAir) continue;
        const s = sourceLevel(b.typeId);
        if (s > 0) level = Math.max(level, s - (Math.abs(dx) + Math.abs(dy) + Math.abs(dz)));
      }
  return level;
}

// ---------- взгляд игрока ----------
/** dot между направлением взгляда игрока и направлением на точку. */
export function lookDot(player, point) {
  const eye = player.getHeadLocation();
  return vdot(player.getViewDirection(), vnorm(vsub(point, eye)));
}

/** Видит ли игрок сущность (без учёта направления взгляда). */
export function hasLineOfSight(player, entity, height = 3.6) {
  const eye = player.getHeadLocation();
  const l = entity.location;
  const dim = player.dimension;
  return (
    lineOfSight(dim, eye, { x: l.x, y: l.y + height * 0.88, z: l.z }) ||
    lineOfSight(dim, eye, { x: l.x, y: l.y + height * 0.5, z: l.z })
  );
}

export function entityTarget(entity, height = 3.6) {
  const l = entity.location;
  return { x: l.x, y: l.y + height * 0.75, z: l.z };
}

/** Точка в стороне/позади игрока относительно взгляда. */
export function pointBehind(player, distance) {
  const v = player.getViewDirection();
  const flat = vnorm({ x: v.x, y: 0, z: v.z });
  return vsub(player.location, vscale(flat, distance));
}
