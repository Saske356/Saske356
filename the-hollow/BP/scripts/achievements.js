// "Достижение" The Survivor: пережить 10 встреч с Hollow.
// Настоящие достижения Xbox аддоны добавлять не могут, поэтому
// показываем титр, даём тег и храним счётчик в dynamic property игрока.
import { CONFIG } from "./config.js";
import { runCmd } from "./utils.js";

const KEY = "hollow:encounters";

export function getEncounters(player) {
  return Number(player.getDynamicProperty(KEY) ?? 0);
}

export function addEncounter(player) {
  const n = getEncounters(player) + 1;
  player.setDynamicProperty(KEY, n);

  const need = CONFIG.achievement.encountersNeeded;
  if (n === need && !player.hasTag(CONFIG.achievement.tag)) {
    player.addTag(CONFIG.achievement.tag);
    try {
      player.onScreenDisplay.setTitle("§l§fThe Survivor", {
        subtitle: `§7Пережито встреч с Hollow: ${need}`,
        fadeInDuration: 20,
        stayDuration: 80,
        fadeOutDuration: 30,
      });
    } catch {}
    player.sendMessage(`§6[Достижение] §fThe Survivor §7— ты пережил ${need} встреч. Оно запомнит тебя.`);
    runCmd(player, "playsound random.levelup @s ~ ~ ~ 1 0.6");
  }
  return n;
}
