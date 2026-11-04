// =============================================================
//  The Hollow — точка входа Script API.
//  Модули:
//    config.js         — все числа и шансы
//    spawnManager.js   — когда и где появляется Hollow
//    hollowAI.js       — состояния Idle/Watching/Stalking/Chasing/Disappear
//    hallucinations.js — ложный Hollow
//    events.js         — двери, факелы, стекло, шёпот, WAKE UP, кошмар во сне
//    fog.js            — туман рядом с Hollow
//    soundController.js— звуки
//    structures.js     — тотемы
//    achievements.js   — The Survivor
// =============================================================
import { system, world } from "@minecraft/server";
import { CONFIG } from "./config.js";
import { hollows, phantoms, setEnabled, findHollowRecord, findPhantomRecord } from "./state.js";
import { tickHollows, startChase, removeSilently } from "./hollowAI.js";
import { tickSpawn, spawnHollowFor, checkConditions } from "./spawnManager.js";
import { tickPhantoms, tickHallucinations, vanishPhantom, removePhantomSilently, spawnPhantomFor } from "./hallucinations.js";
import { tickEvents, tickSleep, runRandomEvent, forceNightmareNextSleep } from "./events.js";
import { updateFog, clearFog } from "./fog.js";
import { tickTotems, trySpawnTotem } from "./structures.js";
import { addEncounter, getEncounters } from "./achievements.js";
import { getPlayer } from "./utils.js";

// ---------- уборка после перезахода в мир ----------
let cleaned = false;
function cleanupLeftovers() {
  for (const dimId of ["minecraft:overworld", "minecraft:nether", "minecraft:the_end"]) {
    try {
      const dim = world.getDimension(dimId);
      for (const type of [CONFIG.ids.hollow, CONFIG.ids.phantom])
        for (const e of dim.getEntities({ type })) e.remove();
    } catch {}
  }
  for (const p of world.getAllPlayers()) clearFog(p);
}

// ---------- основной цикл: раз в секунду ----------
system.runInterval(() => {
  if (!cleaned) {
    cleaned = true;
    cleanupLeftovers();
    return;
  }
  for (const player of world.getAllPlayers()) {
    try {
      tickSpawn(player);
      tickHallucinations(player);
      tickEvents(player);
      tickSleep(player);
      tickTotems(player);
      updateFog(player);
    } catch (e) {
      console.warn(`[Hollow] main loop error: ${e}`);
    }
  }
}, CONFIG.tick.main);

// ---------- ИИ: раз в полсекунды ----------
system.runInterval(() => {
  if (!cleaned) return;
  tickHollows();
  tickPhantoms();
}, CONFIG.tick.ai);

// ---------- события мира ----------
world.afterEvents.entityHurt.subscribe((ev) => {
  const hurt = ev.hurtEntity;
  if (hurt?.typeId !== CONFIG.ids.hollow) return;
  if (ev.damageSource?.damagingEntity?.typeId !== "minecraft:player") return;
  const rec = findHollowRecord(hurt.id);
  if (rec) startChase(rec);
});

world.afterEvents.entityHitEntity.subscribe((ev) => {
  const hit = ev.hitEntity;
  if (hit?.typeId === CONFIG.ids.phantom) {
    const rec = findPhantomRecord(hit.id);
    if (rec) vanishPhantom(rec);
    else {
      try {
        hit.remove();
      } catch {}
    }
  }
});

world.afterEvents.entityDie.subscribe((ev) => {
  const dead = ev.deadEntity;
  if (!dead) return;
  if (dead.typeId === "minecraft:player") {
    removeSilently(dead.id);
    removePhantomSilently(dead.id);
    return;
  }
  if (dead.typeId === CONFIG.ids.hollow) {
    const rec = findHollowRecord(dead.id);
    if (!rec) return;
    hollows.delete(rec.playerId);
    const p = getPlayer(rec.playerId);
    if (p) {
      const n = addEncounter(p);
      p.sendMessage(`§8Оно рассыпалось в пепел... но не исчезло навсегда. §7(встреч: ${n})`);
    }
  }
});

world.afterEvents.playerSpawn.subscribe((ev) => {
  clearFog(ev.player);
});

world.afterEvents.playerLeave.subscribe((ev) => {
  removeSilently(ev.playerId);
  removePhantomSilently(ev.playerId);
});

// ---------- команды: /function hollow:<имя> -> /scriptevent hollow:<имя> ----------
function nearestPlayer(source) {
  if (source?.typeId === "minecraft:player") return source;
  return world.getAllPlayers()[0];
}

system.afterEvents.scriptEventReceive.subscribe((ev) => {
  if (!ev.id.startsWith("hollow:")) return;
  const player = nearestPlayer(ev.sourceEntity);
  const say = (msg) => (player ? player.sendMessage(msg) : console.warn(msg));
  const cmd = ev.id.slice("hollow:".length);

  switch (cmd) {
    case "start":
      setEnabled(true);
      say("§a[Hollow] Включён. §8Не оставайся один в темноте.");
      break;

    case "stop":
      setEnabled(false);
      for (const id of [...hollows.keys()]) removeSilently(id);
      for (const id of [...phantoms.keys()]) removePhantomSilently(id);
      for (const p of world.getAllPlayers()) clearFog(p);
      say("§c[Hollow] Выключен. Все Hollow удалены.");
      break;

    case "spawn": {
      if (!player) return;
      if (hollows.has(player.id)) removeSilently(player.id);
      const e = spawnHollowFor(player, { force: true });
      say(e ? "§7[Hollow] Оно уже здесь. Оглянись." : "§c[Hollow] Не нашёл место для спавна (25–45 блоков, нужна земля и 4 блока высоты).");
      break;
    }

    case "test": {
      if (!player) return;
      const c = checkConditions(player);
      const yn = (b) => (b ? "§aда" : "§cнет");
      say("§6=== The Hollow: диагностика ===");
      say(`§7Включён: ${yn(c.enabled)} §7| Ночь: ${yn(c.night)} §7| Верхний мир: ${yn(c.overworld)}`);
      say(`§7Один: ${yn(c.alone)} §7| Свет: §f${c.light} §7(нужно < ${CONFIG.spawn.maxLight}) | Hollow уже есть: ${yn(c.hasHollow)}`);
      say(`§7Пережито встреч: §f${getEncounters(player)}/${CONFIG.achievement.encountersNeeded}`);
      const ev2 = runRandomEvent(player);
      say(`§7Случайное событие: §f${ev2}`);
      const ph = spawnPhantomFor(player);
      say(`§7Галлюцинация: ${yn(!!ph)}`);
      const totem = trySpawnTotem(player, true);
      say(`§7Тотем рядом: ${totem ? `§a${Math.floor(totem.x)} ${Math.floor(totem.y)} ${Math.floor(totem.z)}` : "§cнет места"}`);
      break;
    }

    case "nightmare":
      if (!player) return;
      forceNightmareNextSleep(player);
      say("§8[Hollow] Ляг спать... если осмелишься.");
      break;
  }
});

console.warn("[Hollow] scripts loaded");
