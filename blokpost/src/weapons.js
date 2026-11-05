'use strict';
/* ---------------- оружие: характеристики ---------------- */
const WEAPONS = {
  pistol:  { name: 'Скат-9', cls: 'Пистолет', hold: 'pistol', dmg: 26, rate: 0.16, auto: true, mag: 12, res: 48, reload: 1.6, spread: 0.01, moveSpread: 0.03, spray: 0.006, kick: 0.012, price: 0, speed: 1, head: 3.6, zoom: 1.3, snd: { f: 4200, d: 0.16, v: 0.7, th: 140 }, botAcc: 0.85, desc: 'Всегда с тобой' },
  smg:     { name: 'Шмель', cls: 'Пистолет-пулемёт', hold: 'rifle', dmg: 22, rate: 0.075, auto: true, mag: 30, res: 120, reload: 2.1, spread: 0.02, moveSpread: 0.018, spray: 0.0028, kick: 0.009, price: 1250, speed: 0.97, head: 3, zoom: 1.35, snd: { f: 1900, d: 0.1, v: 0.45, th: 110 }, botAcc: 0.9, desc: 'С глушителем, быстрый и тихий' },
  shotgun: { name: 'Буря', cls: 'Дробовик', hold: 'rifle', dmg: 19, pellets: 8, rate: 0.85, auto: false, mag: 7, res: 28, reload: 2.8, spread: 0.06, moveSpread: 0.01, spray: 0, kick: 0.05, price: 1100, speed: 0.92, head: 2.5, zoom: 1.25, falloff: 16, snd: { f: 2400, d: 0.32, v: 1, th: 80 }, botAcc: 1, desc: 'Помповый, решает в упор' },
  rifle:   { name: 'Вихрь', cls: 'Автомат', hold: 'rifle', dmg: 35, rate: 0.1, auto: true, mag: 30, res: 90, reload: 2.5, spread: 0.006, moveSpread: 0.075, spray: 0.005, kick: 0.018, price: 2700, speed: 0.9, head: 4, zoom: 1.5, snd: { f: 2600, d: 0.22, v: 0.85, th: 95 }, botAcc: 1, desc: 'Деревянное цевьё, мощный патрон' },
  carbine: { name: 'Стрела', cls: 'Карабин', hold: 'rifle', dmg: 31, rate: 0.09, auto: true, mag: 30, res: 90, reload: 2.3, spread: 0.004, moveSpread: 0.07, spray: 0.0038, kick: 0.013, price: 3100, speed: 0.92, head: 4, zoom: 1.75, reddot: true, snd: { f: 3000, d: 0.2, v: 0.8, th: 100 }, botAcc: 1.05, desc: 'Коллиматор, мягкая отдача' },
  sniper:  { name: 'Сокол', cls: 'Снайперская', hold: 'rifle', dmg: 115, rate: 1.25, auto: false, mag: 5, res: 20, reload: 3.1, spread: 0.09, scopedSpread: 0.0004, moveSpread: 0.12, spray: 0, kick: 0.05, price: 4750, speed: 0.82, head: 4, zoom: 4, scope: true, snd: { f: 1800, d: 0.45, v: 1, th: 70 }, botAcc: 1.15, desc: 'Продольный затвор, оптика ×4' },
};
const PRIMARIES = ['smg', 'shotgun', 'rifle', 'carbine', 'sniper'];
const ARMOR_PRICE = 650, MONEY_CAP = 16000;
