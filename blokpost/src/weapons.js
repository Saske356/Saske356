'use strict';
/* ---------------- оружие: характеристики ---------------- */
// Узор отдачи: опорные точки [номер_пули, вправо, вверх] в радианах (накопленное смещение взгляда).
// Узор фиксированный и повторяемый: его можно выучить и компенсировать, уводя прицел в обратную сторону.
function recoilPat(pts, n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    let k = 0; while (k < pts.length - 2 && pts[k + 1][0] < i) k++;
    const a = pts[k], b = pts[Math.min(k + 1, pts.length - 1)];
    const t = b[0] === a[0] ? 0 : clamp((i - a[0]) / (b[0] - a[0]), 0, 1);
    out.push([a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]);
  }
  return out;
}
// Поля: dmg — урон, head — множитель в голову, armorPen — доля урона, проходящая сквозь броню, rangeMod — множитель урона на каждые 10 м,
// pen — сила пробития укрытий, spread — разброс первого выстрела (рад), moveSpread — добавка на полном бегу, jump — в прыжке,
// spray — случайная добавка за пулю очереди, pattern — узор отдачи, recover — сколько «пуль» отдачи гасится в секунду.
// snd — профиль синтезированного выстрела (см. audio.js).
const WEAPONS = {
  pistol:  { name: 'Скат-9', cls: 'Пистолет', hold: 'pistol', dmg: 27, rate: 0.15, auto: false, mag: 12, res: 48, reload: 1.8, spread: 0.006, moveSpread: 0.026, jump: 0.09, spray: 0.0016, kick: 0.012, price: 0, speed: 1, head: 4, armorPen: 0.5, rangeMod: 0.86, pen: 0.55, zoom: 1.3,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.014], [3, 0.003, 0.036], [6, -0.004, 0.054], [9, 0.005, 0.064], [11, -0.002, 0.068]], 12), recover: 9,
    snd: { kind: 'pistol', body: 1500, crack: 5200, thump: 150, dur: 0.12, vol: 0.8, tail: 0.5, mech: 2600 }, botAcc: 0.85, desc: 'Всегда с тобой' },
  smg:     { name: 'Шмель', cls: 'Пистолет-пулемёт', hold: 'rifle', dmg: 23, rate: 0.078, auto: true, mag: 30, res: 120, reload: 2.2, spread: 0.009, moveSpread: 0.02, jump: 0.08, spray: 0.0011, kick: 0.009, price: 1250, speed: 0.97, head: 3.2, armorPen: 0.6, rangeMod: 0.84, pen: 0.45, zoom: 1.35,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.006], [4, 0.003, 0.021], [8, 0.008, 0.035], [12, -0.006, 0.041], [16, -0.015, 0.044], [20, 0.002, 0.046], [24, 0.013, 0.047], [29, 0.004, 0.048]], 30), recover: 22,
    snd: { kind: 'supp', body: 900, crack: 2400, thump: 95, dur: 0.07, vol: 0.4, tail: 0.15, mech: 3100 }, botAcc: 0.9, desc: 'С глушителем, быстрый и тихий' },
  smg2:    { name: 'Оса', cls: 'Пистолет-пулемёт', hold: 'rifle', dmg: 20, rate: 0.064, auto: true, mag: 32, res: 128, reload: 2.0, spread: 0.011, moveSpread: 0.018, jump: 0.08, spray: 0.0014, kick: 0.008, price: 1050, speed: 0.99, head: 3, armorPen: 0.55, rangeMod: 0.82, pen: 0.4, zoom: 1.35,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.007], [5, -0.004, 0.026], [9, -0.012, 0.038], [13, 0.002, 0.044], [18, 0.016, 0.048], [23, 0.004, 0.05], [27, -0.01, 0.051], [31, 0.0, 0.052]], 32), recover: 24,
    snd: { kind: 'smg', body: 1700, crack: 4600, thump: 120, dur: 0.08, vol: 0.62, tail: 0.45, mech: 3400 }, botAcc: 0.88, desc: 'Компактный, бешеный темп, передняя рукоять' },
  shotgun: { name: 'Буря', cls: 'Дробовик', hold: 'rifle', dmg: 20, pellets: 8, rate: 0.85, auto: false, mag: 7, res: 28, reload: 2.8, spread: 0.055, moveSpread: 0.012, jump: 0.04, spray: 0, kick: 0.05, price: 1100, speed: 0.92, head: 2.5, armorPen: 0.5, falloff: 16, pen: 0.18, zoom: 1.25,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.034], [6, 0, 0.06]], 8), recover: 3.5,
    snd: { kind: 'shotgun', body: 700, crack: 3000, thump: 70, dur: 0.3, vol: 1, tail: 1.1, mech: 1800 }, botAcc: 1, desc: 'Помповый, решает в упор' },
  rifle:   { name: 'Вихрь', cls: 'Автомат', hold: 'rifle', dmg: 36, rate: 0.1, auto: true, mag: 30, res: 90, reload: 2.5, spread: 0.0035, moveSpread: 0.09, jump: 0.16, spray: 0.0012, kick: 0.018, price: 2700, speed: 0.88, head: 4, armorPen: 0.775, rangeMod: 0.98, pen: 1, zoom: 1.5,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.011], [3, 0.002, 0.033], [6, -0.003, 0.062], [9, 0.004, 0.085], [11, 0.018, 0.093], [14, 0.034, 0.097], [17, 0.02, 0.1], [19, -0.01, 0.101], [22, -0.035, 0.103], [25, -0.02, 0.104], [27, 0.01, 0.106], [29, 0.025, 0.107]], 30), recover: 20,
    snd: { kind: 'rifle', body: 1050, crack: 4200, thump: 85, dur: 0.18, vol: 0.92, tail: 0.95, mech: 2200 }, botAcc: 1, desc: 'Деревянное цевьё, мощный патрон' },
  carbine: { name: 'Стрела', cls: 'Карабин', hold: 'rifle', dmg: 32, rate: 0.09, auto: true, mag: 30, res: 90, reload: 2.3, spread: 0.003, moveSpread: 0.08, jump: 0.15, spray: 0.0009, kick: 0.013, price: 3100, speed: 0.9, head: 4, armorPen: 0.7, rangeMod: 0.97, pen: 0.9, zoom: 1.75, reddot: true,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.008], [4, -0.002, 0.031], [8, 0.004, 0.056], [11, -0.012, 0.064], [15, -0.026, 0.068], [19, -0.008, 0.07], [23, 0.016, 0.072], [27, 0.026, 0.073], [29, 0.018, 0.074]], 30), recover: 22,
    snd: { kind: 'rifle', body: 1350, crack: 5000, thump: 100, dur: 0.15, vol: 0.86, tail: 0.85, mech: 2700 }, botAcc: 1.05, desc: 'Коллиматор, мягкая отдача' },
  lmg:     { name: 'Молот', cls: 'Ручной пулемёт', hold: 'rifle', dmg: 32, rate: 0.088, auto: true, mag: 100, res: 200, reload: 5.4, spread: 0.007, moveSpread: 0.12, jump: 0.2, spray: 0.0009, kick: 0.014, price: 5200, speed: 0.78, head: 3.8, armorPen: 0.75, rangeMod: 0.97, pen: 1, zoom: 1.45,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.012], [4, 0.004, 0.04], [8, 0.012, 0.062], [12, 0.002, 0.07], [18, -0.014, 0.074], [26, 0.01, 0.077], [40, -0.008, 0.08], [60, 0.012, 0.082], [99, 0.0, 0.084]], 100), recover: 18,
    snd: { kind: 'rifle', body: 900, crack: 3800, thump: 75, dur: 0.2, vol: 0.98, tail: 1.05, mech: 1900 }, botAcc: 0.95, desc: 'Короб на сотню, сошки, держит проход' },
  dmr:     { name: 'Сова', cls: 'Марксманская', hold: 'rifle', dmg: 80, rate: 0.32, auto: false, mag: 10, res: 30, reload: 2.9, spread: 0.035, scopedSpread: 0.0012, moveSpread: 0.1, jump: 0.18, spray: 0.002, kick: 0.035, price: 3900, speed: 0.84, head: 4, armorPen: 0.82, rangeMod: 0.99, pen: 1.15, zoom: 2.8, scope: true,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.022], [3, 0.006, 0.05], [6, -0.004, 0.066], [9, 0.004, 0.072]], 10), recover: 6,
    snd: { kind: 'sniper', body: 820, crack: 4600, thump: 68, dur: 0.26, vol: 1, tail: 1.2, mech: 2100 }, botAcc: 1.08, desc: 'Полуавтомат с оптикой ×2.8' },
  sniper:  { name: 'Сокол', cls: 'Снайперская', hold: 'rifle', dmg: 115, rate: 1.3, auto: false, mag: 5, res: 20, reload: 3.1, spread: 0.085, scopedSpread: 0.0003, moveSpread: 0.14, jump: 0.25, spray: 0, kick: 0.05, price: 4750, speed: 0.8, head: 4, armorPen: 0.97, rangeMod: 0.995, pen: 1.5, zoom: 4, scope: true, bolt: true,
    pattern: recoilPat([[0, 0, 0], [1, 0, 0.05], [4, 0, 0.06]], 5), recover: 2.2,
    snd: { kind: 'sniper', body: 650, crack: 4000, thump: 55, dur: 0.38, vol: 1, tail: 1.6, mech: 1600 }, botAcc: 1.15, desc: 'Продольный затвор, оптика ×4' },

  // ближний бой: быстрый удар (огонь) и сильный (прицел). Сзади — смертельно.
  knife:   { name: 'Коготь', cls: 'Нож', hold: 'knife', melee: true, dmg: 34, heavy: 65, back: 2.6, range: 1.75, heavyRange: 1.45, rate: 0.42, heavyRate: 1.05, auto: true, mag: 1, res: 0, reload: 1, spread: 0, moveSpread: 0, jump: 0, spray: 0, kick: 0, price: 0, speed: 1.1, head: 1, armorPen: 0.85, zoom: 1, botAcc: 1, desc: 'Быстрый бег, тихий удар' },
  // гранаты: count — сколько можно нести, fuse — запал после броска (дым — после остановки)
  he:      { name: 'Осколочная', cls: 'Граната', hold: 'grenade', grenade: true, dmg: 98, radius: 7.5, fuse: 1.6, max: 1, price: 300, auto: false, mag: 1, res: 0, reload: 1, spread: 0, moveSpread: 0, jump: 0, spray: 0, kick: 0, speed: 1, head: 1, armorPen: 0.55, zoom: 1, botAcc: 1, desc: 'Урон по площади, не проходит сквозь стены' },
  flash:   { name: 'Светошумовая', cls: 'Граната', hold: 'grenade', grenade: true, dmg: 0, radius: 26, fuse: 1.45, max: 2, price: 200, auto: false, mag: 1, res: 0, reload: 1, spread: 0, moveSpread: 0, jump: 0, spray: 0, kick: 0, speed: 1, head: 1, armorPen: 1, zoom: 1, botAcc: 1, desc: 'Ослепляет всех, кто смотрит на вспышку' },
  smoke:   { name: 'Дымовая', cls: 'Граната', hold: 'grenade', grenade: true, dmg: 0, radius: 3.4, fuse: 1.2, max: 1, price: 300, auto: false, mag: 1, res: 0, reload: 1, spread: 0, moveSpread: 0, jump: 0, spray: 0, kick: 0, speed: 1, head: 1, armorPen: 1, zoom: 1, botAcc: 1, desc: 'Облако на 15 секунд закрывает обзор' },
};
const PRIMARIES = ['smg2', 'smg', 'shotgun', 'rifle', 'carbine', 'lmg', 'dmr', 'sniper'];
const GRENADES = ['he', 'flash', 'smoke'];
const ARMOR_PRICE = 650, HELMET_PRICE = 350, MONEY_CAP = 16000;
// Список товаров для магазина (интегратор добавляет в ui.js): ключ, цена, лимит
const SHOP_EXTRA = [
  { key: 'armor', name: 'Бронежилет', price: ARMOR_PRICE },
  { key: 'helmet', name: 'Бронежилет и шлем', price: ARMOR_PRICE + HELMET_PRICE },
  ...GRENADES.map(k => ({ key: k, name: WEAPONS[k].name, price: WEAPONS[k].price, max: WEAPONS[k].max })),
];
