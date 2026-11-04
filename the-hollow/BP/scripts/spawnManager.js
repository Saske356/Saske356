// Появление Hollow: ночь, игрок один, темно, 15% раз в несколько минут.
// Всегда 25–45 блоков от игрока и за укрытием (дерево, камень, стена) или в тумане.
import { world } from "@minecraft/server";
import { CONFIG } from "./config.js";
import { hollows, isEnabled } from "./state.js";
import { registerHollow, spawnParticle } from "./hollowAI.js";
import { forceNearFog } from "./fog.js";
import { sfx } from "./soundController.js";
import {
  chance, findGround, firstObstacle, inOverworld, isNight, lightLevel,
  lineOfSight, rand, vdist,
} from "./utils.js";

const S = CONFIG.spawn;
const HEIGHT = 3.6;

/** playerId -> сколько секунд осталось до следующей проверки */
const timers = new Map();

export function isAlone(player) {
  return !world
    .getAllPlayers()
    .some((p) => p.id !== player.id && p.dimension.id === player.dimension.id && vdist(p.location, player.location) < S.aloneRadius);
}

export function checkConditions(player) {
  return {
    enabled: isEnabled(),
    night: isNight(),
    overworld: inOverworld(player),
    alone: isAlone(player),
    light: lightLevel(player.dimension, player.location),
    hasHollow: hollows.has(player.id),
  };
}

/**
 * Ищет точку спавна. Возвращает { loc, cover } где cover:
 *  "cover" — сразу за деревом/камнем/стеной (лучший вариант),
 *  "hidden" — игрок не видит точку,
 *  "fog" — видно, но далеко (включим туман).
 */
export function findSpawnLocation(player, { minDistance = S.minDistance, maxDistance = S.maxDistance } = {}) {
  const dim = player.dimension;
  const eye = player.getHeadLocation();
  let hidden, fog;

  for (let i = 0; i < S.attempts; i++) {
    const a = Math.random() * Math.PI * 2;
    const d = rand(minDistance, maxDistance);
    const x = Math.floor(player.location.x + Math.cos(a) * d);
    const z = Math.floor(player.location.z + Math.sin(a) * d);
    const loc = findGround(dim, x, z, player.location.y, 4);
    if (!loc) continue;
    if (vdist(loc, player.location) < minDistance) continue;

    const head = { x: loc.x, y: loc.y + HEIGHT * 0.88, z: loc.z };
    const mid = { x: loc.x, y: loc.y + HEIGHT * 0.5, z: loc.z };
    const seen = lineOfSight(dim, eye, head) || lineOfSight(dim, eye, mid);

    if (!seen) {
      // Укрытие рядом с Hollow? (луч от Hollow к игроку упирается в блок в пределах 4 блоков)
      const t = firstObstacle(dim, head, eye);
      if (t >= 0 && t <= 4) return { loc, cover: "cover" };
      hidden ??= loc;
    } else if (vdist(loc, player.location) >= S.fogFallbackMinDistance) {
      fog ??= loc;
    }
  }
  if (hidden) return { loc: hidden, cover: "hidden" };
  if (fog) return { loc: fog, cover: "fog" };
  return undefined;
}

/** Создать Hollow рядом с игроком. force — игнорировать условия (для команд). */
export function spawnHollowFor(player, { force = false, state = "idle", location } = {}) {
  if (hollows.has(player.id)) return undefined; // не больше 1 на игрока

  let loc = location;
  let cover = "manual";
  if (!loc) {
    const found = findSpawnLocation(player);
    if (!found) return undefined;
    loc = found.loc;
    cover = found.cover;
  }
  if (cover === "fog") forceNearFog(player);

  let entity;
  try {
    entity = player.dimension.spawnEntity(CONFIG.ids.hollow, loc);
  } catch (e) {
    if (force) player.sendMessage(`§c[Hollow] Не удалось создать: ${e}`);
    return undefined;
  }

  spawnParticle(player.dimension, "hollow:black_smoke", loc);
  sfx.appear(player, loc);
  registerHollow(entity, player, state);
  return entity;
}

/** Раз в main-тик (1 сек). */
export function tickSpawn(player) {
  let t = timers.get(player.id) ?? S.checkIntervalSeconds * rand(0.5, 1);
  t -= CONFIG.tick.main / 20;
  if (t > 0) {
    timers.set(player.id, t);
    return;
  }
  timers.set(player.id, S.checkIntervalSeconds * rand(0.8, 1.2));

  if (!isEnabled() || !isNight() || !inOverworld(player)) return;
  if (hollows.has(player.id) || !isAlone(player)) return;
  if (lightLevel(player.dimension, player.location) >= S.maxLight) return;
  if (!chance(S.chance)) return;

  spawnHollowFor(player);
}
