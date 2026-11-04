// Атмосферные события ночью + очень редкий "кошмар" во сне.
import { system, world } from "@minecraft/server";
import { CONFIG } from "./config.js";
import { isEnabled } from "./state.js";
import { sfx } from "./soundController.js";
import { spawnPhantomFor } from "./hallucinations.js";
import { removeSilently, spawnParticle } from "./hollowAI.js";
import { spawnHollowFor } from "./spawnManager.js";
import {
  chance, findGround, getBlock, inOverworld, isNight, pick, pointBehind, rand,
  randInt, runCmd, scanBlocks, vadd,
} from "./utils.js";

const E = CONFIG.events;
const timers = new Map();

// ---------- отдельные события ----------

function isDoor(b) {
  return b.typeId.endsWith("_door") && !b.typeId.includes("trapdoor");
}

function setOpen(block, open) {
  try {
    let b = block;
    if (b.permutation.getState("upper_block_bit")) b = block.below() ?? block;
    b.setPermutation(b.permutation.withState("open_bit", open));
    return b;
  } catch {
    return undefined;
  }
}

export function eventDoor(player, radius = E.radius) {
  const doors = scanBlocks(player.dimension, player.location, radius, E.verticalRadius, (b) => {
    try {
      return isDoor(b) && !b.permutation.getState("upper_block_bit") && !b.permutation.getState("open_bit");
    } catch {
      return false;
    }
  });
  if (!doors.length) return false;
  const b = setOpen(pick(doors), true);
  if (b) runCmd(player, `playsound random.door_open @s ${b.x} ${b.y} ${b.z} 1 0.8`);
  return !!b;
}

export function eventTorch(player) {
  const torches = scanBlocks(player.dimension, player.location, E.radius, E.verticalRadius, (b) =>
    b.typeId === "minecraft:torch" || b.typeId === "minecraft:soul_torch");
  if (!torches.length) return false;
  const b = pick(torches);
  const loc = { x: b.x + 0.5, y: b.y + 0.5, z: b.z + 0.5 };
  try {
    b.setType("minecraft:air");
  } catch {
    return false;
  }
  spawnParticle(player.dimension, "minecraft:basic_smoke_particle", loc);
  runCmd(player, `playsound random.fizz @s ${b.x} ${b.y} ${b.z} 0.7 0.6`);
  return true;
}

export function eventGlass(player) {
  const glass = scanBlocks(player.dimension, player.location, E.radius, E.verticalRadius, (b) =>
    b.typeId.includes("glass") && !b.typeId.includes("tinted"));
  if (!glass.length) return false;
  const b = pick(glass);
  try {
    b.setType("minecraft:air");
  } catch {
    return false;
  }
  runCmd(player, `playsound random.glass @s ${b.x} ${b.y} ${b.z} 1 0.9`);
  return true;
}

export function eventSilhouette(player) {
  return !!spawnPhantomFor(player, { minDistance: 28, maxDistance: 40 });
}

export function eventWhisper(player) {
  sfx.whisper(player, pointBehind(player, 1.5));
  return true;
}

export function eventLaugh(player) {
  sfx.laugh(player, pointBehind(player, rand(3, 6)));
  return true;
}

function writeSign(block, text) {
  try {
    const sign = block.getComponent("minecraft:sign");
    if (!sign) return false;
    sign.setText(text);
    try {
      sign.setText(text, "Back");
    } catch {}
    return true;
  } catch {
    return false;
  }
}

/** Надпись WAKE UP: на существующей табличке или на новой — за спиной игрока. */
export function eventSign(player) {
  const signs = scanBlocks(player.dimension, player.location, E.radius, E.verticalRadius, (b) => b.typeId.includes("sign"));
  if (signs.length && writeSign(pick(signs), "WAKE UP")) return true;

  const behind = pointBehind(player, 3);
  const g = findGround(player.dimension, Math.floor(behind.x), Math.floor(behind.z), player.location.y, 2, 3, 4);
  if (!g) return false;
  const block = getBlock(player.dimension, g);
  if (!block) return false;
  try {
    block.setType("minecraft:standing_sign");
    // Повернуть табличку лицом к игроку (16 направлений).
    const yaw = Math.atan2(player.location.x - g.x, -(player.location.z - g.z));
    const dir = (Math.round((yaw / (Math.PI * 2)) * 16) + 16) % 16;
    try {
      block.setPermutation(block.permutation.withState("ground_sign_direction", dir));
    } catch {}
  } catch {
    return false;
  }
  // Блок-сущность таблички появляется через тик.
  system.runTimeout(() => {
    const b = getBlock(player.dimension, g);
    if (b && !writeSign(b, "WAKE UP")) {
      try {
        b.setType("minecraft:air");
      } catch {}
    }
  }, 2);
  return true;
}

const EVENTS = [
  ["door", eventDoor],
  ["torch", eventTorch],
  ["glass", eventGlass],
  ["silhouette", eventSilhouette],
  ["whisper", eventWhisper],
  ["laugh", eventLaugh],
  ["sign", eventSign],
];

/** Запустить одно случайное событие без учёта шанса (для /function hollow:test). */
export function runRandomEvent(player) {
  const order = [...EVENTS].sort(() => Math.random() - 0.5);
  for (const [name, fn] of order) if (fn(player)) return name;
  return "none";
}

/** Раз в main-тик. */
export function tickEvents(player) {
  let t = timers.get(player.id) ?? E.intervalSeconds;
  t -= CONFIG.tick.main / 20;
  if (t > 0) {
    timers.set(player.id, t);
    return;
  }
  timers.set(player.id, E.intervalSeconds * rand(0.7, 1.3));
  if (!isEnabled() || !isNight() || !inOverworld(player)) return;

  if (chance(E.ambientChance)) sfx.ambient(player);
  for (const [name, fn] of EVENTS) {
    if (chance(E.chances[name])) {
      if (fn(player)) break; // не больше одного события за раз
    }
  }
}

// ---------- кошмар во сне (0.05%) ----------

const sleepRolled = new Set();
const forcedNightmare = new Set();

export function forceNightmareNextSleep(player) {
  forcedNightmare.add(player.id);
}

function isSleeping(player) {
  try {
    return !!player.isSleeping;
  } catch {
    return false;
  }
}

/** Проснулся в 03:00, все двери открыты, в доме стоит Hollow. */
export function nightmare(player) {
  if (!inOverworld(player)) return;
  world.setTimeOfDay(CONFIG.sleep.nightmareTime);
  // Телепорт на месте будит игрока.
  try {
    player.teleport(vadd(player.location, { x: 0, y: 0.6, z: 0 }));
  } catch {}

  // Открыть все двери вокруг.
  const r = CONFIG.sleep.doorRadius;
  const doors = scanBlocks(player.dimension, player.location, r, 4, (b) => {
    try {
      return isDoor(b) && !b.permutation.getState("upper_block_bit");
    } catch {
      return false;
    }
  }, 64);
  for (const d of doors) setOpen(d, true);
  if (doors.length) runCmd(player, "playsound random.door_open @s ~ ~ ~ 1 0.7");

  // Hollow стоит в доме, в 3–6 блоках.
  removeSilently(player.id);
  let spot;
  for (let i = 0; i < 30 && !spot; i++) {
    const a = Math.random() * Math.PI * 2;
    const d = rand(3, 6);
    spot = findGround(
      player.dimension,
      Math.floor(player.location.x + Math.cos(a) * d),
      Math.floor(player.location.z + Math.sin(a) * d),
      player.location.y, 2, 2, 3,
    );
  }
  spawnHollowFor(player, { force: true, state: "watching", location: spot ?? pointBehind(player, 4) });
  sfx.breathBehind(player, player.location);
  try {
    player.addEffect("darkness", 100, { amplifier: 0, showParticles: false });
  } catch {}
}

/** Раз в main-тик: проверка сна. */
export function tickSleep(player) {
  if (!isSleeping(player)) {
    sleepRolled.delete(player.id);
    return;
  }
  if (sleepRolled.has(player.id)) return;
  sleepRolled.add(player.id);
  if (!isEnabled()) return;

  const forced = forcedNightmare.delete(player.id);
  if (forced || chance(CONFIG.sleep.chance)) {
    // Сон пропускается примерно через 100 тиков — успеваем раньше.
    system.runTimeout(() => {
      if (isSleeping(player)) nightmare(player);
    }, randInt(30, 50));
  }
}

