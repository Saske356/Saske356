// Все звуки аддона. Имена совпадают с RP/sounds/sound_definitions.json.
import { runCmd } from "./utils.js";

export const SOUNDS = {
  ambient1: "hollow.ambient1", // низкий гул (появление)
  ambient2: "hollow.ambient2", // далёкий ветер/вой
  breath: "hollow.breath",
  step: "hollow.step",
  scream: "hollow.scream",
  laugh: "hollow.laugh",
  whisper: "hollow.whisper",
};

/** Звук слышит только этот игрок. location — откуда звучит (по умолчанию — от игрока). */
export function playTo(player, sound, { location, volume = 1, pitch = 1 } = {}) {
  try {
    player.playSound(sound, { location: location ?? player.location, volume, pitch });
  } catch {
    runCmd(player, `playsound ${sound} @s ~ ~ ~ ${volume} ${pitch}`);
  }
}

/** Звук в мире — слышат все рядом. */
export function playAt(dimension, sound, location, { volume = 1, pitch = 1 } = {}) {
  try {
    if (typeof dimension.playSound === "function") {
      dimension.playSound(sound, location, { volume, pitch });
      return;
    }
  } catch {}
  const { x, y, z } = location;
  runCmd(dimension, `playsound ${sound} @a ${x.toFixed(1)} ${y.toFixed(1)} ${z.toFixed(1)} ${volume} ${pitch}`);
}

export const sfx = {
  appear(player, loc) {
    playTo(player, SOUNDS.ambient1, { location: loc, volume: 1.4, pitch: 0.8 });
  },
  vanish(player, loc) {
    playTo(player, SOUNDS.breath, { location: loc, volume: 0.9, pitch: 0.6 });
  },
  step(player, loc) {
    playTo(player, SOUNDS.step, { location: loc, volume: 1.2, pitch: 0.8 + Math.random() * 0.15 });
  },
  scream(player, loc) {
    playTo(player, SOUNDS.scream, { location: loc, volume: 1.5, pitch: 0.9 });
  },
  breathBehind(player, loc) {
    playTo(player, SOUNDS.breath, { location: loc, volume: 0.8, pitch: 0.9 });
  },
  whisper(player, loc) {
    playTo(player, SOUNDS.whisper, { location: loc, volume: 0.9, pitch: 1 });
  },
  laugh(player, loc) {
    playTo(player, SOUNDS.laugh, { location: loc, volume: 1, pitch: 0.85 });
  },
  ambient(player) {
    const s = Math.random() < 0.5 ? SOUNDS.ambient1 : SOUNDS.ambient2;
    playTo(player, s, { volume: 0.6, pitch: 0.9 + Math.random() * 0.2 });
  },
};
