// Искусственный интеллект Hollow.
// Состояния: idle -> watching -> stalking -> chasing -> (disappear)
//
// Само передвижение (pathfinding) делает движок через navigation.walk
// и компонент-группы в BP/entities/the_hollow.json. Скрипт только
// переключает группы событиями и следит за взглядом игрока.
import { system } from "@minecraft/server";
import { CONFIG } from "./config.js";
import { hollows } from "./state.js";
import { sfx } from "./soundController.js";
import { addEncounter } from "./achievements.js";
import {
  getEntity, getPlayer, hasLineOfSight, entityTarget, isNight, lookDot,
  rand, runCmd, vdist,
} from "./utils.js";

const AI = CONFIG.ai;
const secToTicks = (s) => Math.round(s * 20);
const now = () => system.currentTick;

/** Какая компонент-группа соответствует состоянию. */
const GROUP_EVENT = {
  idle: "hollow:set_idle",
  watch: "hollow:set_watch",
  stalk: "hollow:set_stalk",
  chase: "hollow:set_chase",
};

export function spawnParticle(dim, id, loc) {
  try {
    dim.spawnParticle(id, loc);
  } catch {}
}

function setGroup(rec, entity, group) {
  if (rec.group === group) return;
  try {
    entity.triggerEvent(GROUP_EVENT[group]);
    rec.group = group;
  } catch {}
}

function faceTarget(entity, player) {
  try {
    entity.teleport(entity.location, { facingLocation: player.getHeadLocation() });
  } catch {}
}

function enterState(rec, entity, state) {
  rec.state = state;
  rec.stateStart = now();
  rec.lookTicks = 0;
  switch (state) {
    case "idle":
      rec.stateEnd = now() + secToTicks(rand(...AI.idleSeconds));
      setGroup(rec, entity, "idle");
      break;
    case "watching":
      rec.stateEnd = now() + secToTicks(rand(...AI.watchSeconds));
      setGroup(rec, entity, "watch");
      break;
    case "stalking":
      rec.stateEnd = Infinity;
      setGroup(rec, entity, "stalk");
      break;
    case "chasing":
      rec.stateEnd = now() + secToTicks(AI.chaseMaxSeconds);
      setGroup(rec, entity, "chase");
      break;
  }
}

/** Зарегистрировать только что созданного Hollow. */
export function registerHollow(entity, player, startState = "idle") {
  const rec = {
    entityId: entity.id,
    playerId: player.id,
    state: "idle",
    group: undefined,
    stateStart: now(),
    stateEnd: 0,
    lookTicks: 0,
    trail: [],
    lastLoc: entity.location,
  };
  hollows.set(player.id, rec);
  // Компоненты сущности становятся доступны через тик.
  system.runTimeout(() => {
    const e = getEntity(rec.entityId);
    if (e) enterState(rec, e, startState);
  }, 2);
  return rec;
}

/** Исчезновение: дым, следы, звук. countEncounter — засчитать "пережитую встречу". */
export function vanish(rec, reason, countEncounter = true) {
  hollows.delete(rec.playerId);
  const entity = getEntity(rec.entityId);
  const player = getPlayer(rec.playerId);
  if (!entity) return;

  const dim = entity.dimension;
  const loc = entity.location;
  spawnParticle(dim, "hollow:black_smoke", loc);
  if (player) sfx.vanish(player, loc);

  // Следы: чёрный пепел там, где оно прошло, ещё ~8 секунд.
  const trail = [...rec.trail, { ...loc }];
  let n = 0;
  const id = system.runInterval(() => {
    for (const p of trail) spawnParticle(dim, "hollow:ash", p);
    if (++n >= 8) system.clearRun(id);
  }, 20);

  try {
    entity.remove();
  } catch {}

  if (countEncounter && player && reason !== "player_died") {
    const total = addEncounter(player);
    if (reason === "looked") player.sendMessage(`§8...оно не любит, когда на него смотрят. §7(встреч: ${total})`);
  }
}

/** Удалить Hollow игрока без эффектов (stop, выход, смерть). */
export function removeSilently(playerId) {
  const rec = hollows.get(playerId);
  if (!rec) return;
  hollows.delete(playerId);
  const e = getEntity(rec.entityId);
  try {
    e?.remove();
  } catch {}
}

/** Начать погоню (удар игрока или подошёл ближе 5 блоков). */
export function startChase(rec) {
  if (rec.state === "chasing") return;
  const entity = getEntity(rec.entityId);
  const player = getPlayer(rec.playerId);
  if (!entity || !player) return;
  enterState(rec, entity, "chasing");
  sfx.scream(player, entity.location);
  runCmd(player, "camerashake add @s 0.6 1.2 positional");
}

function applyNearEffects(player) {
  const t = CONFIG.effects.durationTicks;
  try {
    player.addEffect("slowness", t, { amplifier: 1, showParticles: false });
    player.addEffect("darkness", t, { amplifier: 0, showParticles: false });
    player.addEffect("weakness", t, { amplifier: 0, showParticles: false });
  } catch {}
}

function rememberTrail(rec, entity) {
  const l = entity.location;
  if (vdist(l, rec.lastLoc) > 1.5) {
    rec.trail.push({ x: l.x, y: l.y + 0.1, z: l.z });
    if (rec.trail.length > AI.trailLength) rec.trail.shift();
    rec.lastLoc = l;
  }
}

/** Один шаг ИИ для одного Hollow. */
function tickOne(rec) {
  const entity = getEntity(rec.entityId);
  const player = getPlayer(rec.playerId);
  if (!entity) {
    hollows.delete(rec.playerId);
    return;
  }
  if (!player || player.dimension.id !== entity.dimension.id) {
    removeSilently(rec.playerId);
    return;
  }

  const dist = vdist(entity.location, player.location);
  if (dist > AI.despawnDistance) {
    removeSilently(rec.playerId);
    return;
  }

  // Рассвет — уходит (кроме погони, она доигрывается до конца).
  if (!isNight() && rec.state !== "chasing") {
    vanish(rec, "dawn");
    return;
  }

  const visible = hasLineOfSight(player, entity);
  const dot = lookDot(player, entityTarget(entity));
  const lookingDirect = visible && dot >= AI.lookDot;
  const facing = visible && dot >= AI.viewDot;

  if (dist <= CONFIG.effects.radius) applyNearEffects(player);
  rememberTrail(rec, entity);

  // Подошёл слишком близко — погоня.
  if (rec.state !== "chasing" && dist <= AI.chaseDistance) {
    startChase(rec);
    return;
  }

  // Прямой взгляд 2 секунды — превращается в дым (кроме погони).
  if (rec.state !== "chasing") {
    rec.lookTicks = lookingDirect ? rec.lookTicks + CONFIG.tick.ai : Math.max(0, rec.lookTicks - CONFIG.tick.ai);
    if (rec.lookTicks >= secToTicks(AI.lookToVanishSeconds)) {
      vanish(rec, "looked");
      return;
    }
  }

  switch (rec.state) {
    case "idle":
      if (now() >= rec.stateEnd) enterState(rec, entity, "watching");
      break;

    case "watching":
      faceTarget(entity, player);
      if (now() >= rec.stateEnd && !facing) enterState(rec, entity, "stalking");
      break;

    case "stalking":
      // Игрок обернулся — замирает и смотрит. Отвернулся — снова идёт.
      if (facing) {
        setGroup(rec, entity, "watch");
        faceTarget(entity, player);
      } else {
        setGroup(rec, entity, "stalk");
        if (Math.random() < 0.25) sfx.step(player, entity.location);
        if (dist < 16 && Math.random() < 0.15) sfx.breathBehind(player, entity.location);
      }
      break;

    case "chasing":
      sfx.step(player, entity.location);
      runCmd(player, "camerashake add @s 0.25 0.6 positional");
      try {
        player.addEffect("darkness", 60, { amplifier: 0, showParticles: false });
      } catch {}
      if (now() >= rec.stateEnd || dist > AI.chaseLoseDistance) vanish(rec, "chase_end");
      break;
  }
}

export function tickHollows() {
  for (const rec of [...hollows.values()]) {
    try {
      tickOne(rec);
    } catch (e) {
      console.warn(`[Hollow] AI error: ${e}`);
    }
  }
}
