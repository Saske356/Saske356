// Маленькие тотемы из костей, чёрной шерсти и черепов.
// Ставятся скриптом редко, вдали от игрока и там, где он их не видит.
import { CONFIG } from "./config.js";
import { isEnabled } from "./state.js";
import {
  chance, findGround, getBlock, inOverworld, lineOfSight, rand,
} from "./utils.js";

const T = CONFIG.totems;
const timers = new Map();

function place(dim, loc, type) {
  const b = getBlock(dim, loc);
  if (!b) return false;
  try {
    b.setType(type);
    return true;
  } catch {
    return false;
  }
}

function placeSkull(dim, loc) {
  // В новых версиях — skeleton_skull, в старых — skull.
  return place(dim, loc, "minecraft:skeleton_skull") || place(dim, loc, "minecraft:skull");
}

/**
 *      [череп]
 *  [шерсть][шерсть][шерсть]
 *      [кость]
 *      [кость]
 *  (+ пара костей вокруг)
 */
export function buildTotem(dim, base) {
  const { x, y, z } = { x: Math.floor(base.x), y: Math.floor(base.y), z: Math.floor(base.z) };
  place(dim, { x, y, z }, "minecraft:bone_block");
  place(dim, { x, y: y + 1, z }, "minecraft:bone_block");
  place(dim, { x, y: y + 2, z }, "minecraft:black_wool");
  if (Math.random() < 0.5) {
    place(dim, { x: x - 1, y: y + 2, z }, "minecraft:black_wool");
    place(dim, { x: x + 1, y: y + 2, z }, "minecraft:black_wool");
  } else {
    place(dim, { x, y: y + 2, z: z - 1 }, "minecraft:black_wool");
    place(dim, { x, y: y + 2, z: z + 1 }, "minecraft:black_wool");
  }
  placeSkull(dim, { x, y: y + 3, z });

  for (let i = 0; i < 3; i++) {
    const dx = Math.round(rand(-2, 2));
    const dz = Math.round(rand(-2, 2));
    if (dx === 0 && dz === 0) continue;
    const g = findGround(dim, x + dx, z + dz, y, 1, 2, 2);
    if (g) place(dim, g, Math.random() < 0.6 ? "minecraft:bone_block" : "minecraft:black_wool");
  }
}

export function trySpawnTotem(player, force = false) {
  const dim = player.dimension;
  const eye = player.getHeadLocation();
  for (let i = 0; i < 25; i++) {
    const a = Math.random() * Math.PI * 2;
    const d = force ? rand(8, 14) : rand(T.minDistance, T.maxDistance);
    const x = Math.floor(player.location.x + Math.cos(a) * d);
    const z = Math.floor(player.location.z + Math.sin(a) * d);
    const g = findGround(dim, x, z, player.location.y, 4, 10, 10);
    if (!g) continue;
    const below = getBlock(dim, { x: g.x, y: g.y - 1, z: g.z });
    if (!below || below.typeId.includes("water")) continue;
    if (!force && lineOfSight(dim, eye, { x: g.x, y: g.y + 1.5, z: g.z })) continue;
    buildTotem(dim, g);
    return g;
  }
  return undefined;
}

export function tickTotems(player) {
  let t = timers.get(player.id) ?? T.checkIntervalSeconds;
  t -= CONFIG.tick.main / 20;
  if (t > 0) {
    timers.set(player.id, t);
    return;
  }
  timers.set(player.id, T.checkIntervalSeconds * rand(0.8, 1.2));
  if (!isEnabled() || !inOverworld(player)) return;
  if (chance(T.chance)) trySpawnTotem(player);
}
