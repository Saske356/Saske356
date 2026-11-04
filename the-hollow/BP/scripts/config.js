// =============================================================
//  The Hollow — все настройки в одном месте.
//  Время указано в секундах, если не сказано иное.
// =============================================================

export const CONFIG = {
  ids: {
    hollow: "hollow:the_hollow",
    phantom: "hollow:hollow_phantom",
  },

  // Как часто работают циклы (в тиках, 20 тиков = 1 секунда)
  tick: {
    main: 20, // спавн, события, туман, эффекты
    ai: 10,   // состояния Hollow и галлюцинаций
  },

  spawn: {
    checkIntervalSeconds: 150, // "каждые несколько минут"
    chance: 0.15,              // 15%
    minDistance: 25,
    maxDistance: 45,
    maxLight: 8,               // спавн только если свет < 8
    aloneRadius: 64,           // рядом не должно быть других игроков
    attempts: 48,              // попыток найти укрытие
    fogFallbackMinDistance: 35 // если укрытия нет — спавн "в тумане" на этой дистанции+
  },

  ai: {
    idleSeconds: [3, 6],
    watchSeconds: [8, 15],
    lookToVanishSeconds: 2,   // смотришь прямо 2 сек — исчезает
    lookDot: 0.965,           // насколько "прямо" надо смотреть (~15°)
    viewDot: 0.55,            // "игрок обернулся" (~57°)
    chaseDistance: 5,
    chaseMaxSeconds: 35,
    chaseLoseDistance: 48,
    despawnDistance: 96,
    trailLength: 8,           // сколько последних точек пути помнить для следов
  },

  effects: {
    radius: 8,
    durationTicks: 80,
  },

  fog: {
    nearRadius: 32,
  },

  events: {
    intervalSeconds: 45,
    radius: 10,
    verticalRadius: 4,
    chances: {
      door: 0.05,
      torch: 0.03,
      glass: 0.02,
      silhouette: 0.01,
      whisper: 0.01,
      laugh: 0.005,
      sign: 0.002,
    },
    ambientChance: 0.2,
  },

  hallucination: {
    checkIntervalSeconds: 90,
    chance: 0.05,
    minDistance: 18,
    maxDistance: 32,
    lifetimeSeconds: 25,
    lookToVanishSeconds: 0.5,
  },

  sleep: {
    chance: 0.0005, // 0.05%
    nightmareTime: 21000, // 03:00
    doorRadius: 10,
  },

  totems: {
    checkIntervalSeconds: 300,
    chance: 0.08,
    minDistance: 35,
    maxDistance: 60,
  },

  achievement: {
    encountersNeeded: 10,
    tag: "hollow_survivor",
  },
};
