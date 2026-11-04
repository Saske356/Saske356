// Галлюцинации: ложный Hollow. Без хитбокса, без урона, исчезает от взгляда.
import { system } from "@minecraft/server";
import { CONFIG } from "./config.js";
import { phantoms, isEnabled } from "./state.js";
import { spawnParticle } from "./hollowAI.js";
import { sfx } from "./soundController.js";
import {
  chance, findGround, getEntity, getPlayer, hasLineOfSight, entityTarget, inOverworld,
  isNight, lookDot, rand, vdist,
} from "./utils.js";

const H = CONFIG.hallucination;
const timers = new Map();

/** Точка на краю поля зрения игрока, где его можно заметить. */
function findVisibleSpot(player, minD, maxD) {
  const v = player.getViewDirection();
  const yaw = Math.atan2(v.z, v.x);
  for (let i = 0; i < 30; i++) {
    // ±(35..75)° от взгляда — "краем глаза"
    const side = Math.random() < 0.5 ? -1 : 1;
    const a = yaw + side * rand(0.6, 1.3);
    const d = rand(minD, maxD);
    const x = Math.floor(player.location.x + Math.cos(a) * d);
    const z = Math.floor(player.location.z + Math.sin(a) * d);
    const loc = findGround(player.dimension, x, z, player.location.y, 4);
    if (loc) return loc;
  }
  return undefined;
}

export function spawnPhantomFor(player, { minDistance = H.minDistance, maxDistance = H.maxDistance } = {}) {
  if (phantoms.has(player.id)) return undefined;
  const loc = findVisibleSpot(player, minDistance, maxDistance);
  if (!loc) return undefined;
  let entity;
  try {
    entity = player.dimension.spawnEntity(CONFIG.ids.phantom, loc);
  } catch {
    return undefined;
  }
  phantoms.set(player.id, {
    entityId: entity.id,
    playerId: player.id,
    born: system.currentTick,
    lookTicks: 0,
  });
  return entity;
}

export function vanishPhantom(rec, withSound = true) {
  phantoms.delete(rec.playerId);
  const e = getEntity(rec.entityId);
  if (!e) return;
  spawnParticle(e.dimension, "hollow:black_smoke", e.location);
  const p = getPlayer(rec.playerId);
  if (p && withSound && Math.random() < 0.5) sfx.whisper(p, e.location);
  try {
    e.remove();
  } catch {}
}

/** ИИ-тик галлюцинаций. */
export function tickPhantoms() {
  for (const rec of [...phantoms.values()]) {
    const e = getEntity(rec.entityId);
    const p = getPlayer(rec.playerId);
    if (!e) {
      phantoms.delete(rec.playerId);
      continue;
    }
    if (!p || vdist(e.location, p.location) > 64 || system.currentTick - rec.born > H.lifetimeSeconds * 20) {
      vanishPhantom(rec, false);
      continue;
    }
    try {
      e.teleport(e.location, { facingLocation: p.getHeadLocation() });
    } catch {}
    const looking = hasLineOfSight(p, e) && lookDot(p, entityTarget(e)) >= CONFIG.ai.lookDot;
    rec.lookTicks = looking ? rec.lookTicks + CONFIG.tick.ai : 0;
    if (rec.lookTicks >= H.lookToVanishSeconds * 20) vanishPhantom(rec);
  }
}

/** Раз в main-тик: иногда создать галлюцинацию. */
export function tickHallucinations(player) {
  let t = timers.get(player.id) ?? H.checkIntervalSeconds;
  t -= CONFIG.tick.main / 20;
  if (t > 0) {
    timers.set(player.id, t);
    return;
  }
  timers.set(player.id, H.checkIntervalSeconds * rand(0.8, 1.2));
  if (!isEnabled() || !isNight() || !inOverworld(player)) return;
  if (chance(H.chance)) spawnPhantomFor(player);
}

export function removePhantomSilently(playerId) {
  const rec = phantoms.get(playerId);
  if (!rec) return;
  phantoms.delete(playerId);
  try {
    getEntity(rec.entityId)?.remove();
  } catch {}
}
