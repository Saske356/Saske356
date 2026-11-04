// Туман: когда Hollow рядом — серый туман и меньше дальность видимости.
// Туманы описаны в RP/fogs/*.json и включаются командой /fog.
import { CONFIG } from "./config.js";
import { hollows } from "./state.js";
import { getEntity, runCmd, vdist } from "./utils.js";

const FOG = {
  near: { fog: "hollow:fog_near", id: "hollow_near" },
  chase: { fog: "hollow:fog_chase", id: "hollow_chase" },
};

/** playerId -> "none" | "near" | "chase" */
const current = new Map();

function apply(player, level) {
  const prev = current.get(player.id) ?? "none";
  if (prev === level) return;
  if (prev !== "none") runCmd(player, `fog @s remove ${FOG[prev].id}`);
  if (level !== "none") runCmd(player, `fog @s push ${FOG[level].fog} ${FOG[level].id}`);
  current.set(player.id, level);
}

/** Вызывается раз в main-тик для каждого игрока. */
export function updateFog(player) {
  const rec = hollows.get(player.id);
  let level = "none";
  if (rec) {
    const e = getEntity(rec.entityId);
    if (e) {
      if (rec.state === "chasing") level = "chase";
      else if (vdist(e.location, player.location) <= CONFIG.fog.nearRadius) level = "near";
    }
  }
  apply(player, level);
}

/** Убрать наш туман (при входе в мир, /function hollow:stop). */
export function clearFog(player) {
  runCmd(player, `fog @s remove ${FOG.near.id}`);
  runCmd(player, `fog @s remove ${FOG.chase.id}`);
  current.set(player.id, "none");
}

/** Временно включить туман (например, для спавна "в тумане"). */
export function forceNearFog(player) {
  apply(player, "near");
}
