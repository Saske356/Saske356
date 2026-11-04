// Общее состояние между модулями.
import { world } from "@minecraft/server";

/** playerId -> запись о Hollow этого игрока (не больше одного на игрока). */
export const hollows = new Map();

/** playerId -> запись о ложном Hollow. */
export const phantoms = new Map();

export function isEnabled() {
  return world.getDynamicProperty("hollow:enabled") !== false;
}

export function setEnabled(v) {
  world.setDynamicProperty("hollow:enabled", v);
}

/** Найти запись по id сущности Hollow. */
export function findHollowRecord(entityId) {
  for (const rec of hollows.values()) if (rec.entityId === entityId) return rec;
  return undefined;
}

export function findPhantomRecord(entityId) {
  for (const rec of phantoms.values()) if (rec.entityId === entityId) return rec;
  return undefined;
}
