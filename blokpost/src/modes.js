'use strict';
/* ---------------- режимы и сложность ---------------- */
// react — задержка реакции, acc — меткость, head — доля попаданий в голову, turn — скорость поворота, fov — полуугол обзора.
// nade — склонность бросать гранаты, retreat — порог HP для отхода в укрытие, peek — насколько аккуратно выглядывают (0..1).
const DIFF = [
  { name: 'Новички', react: [0.6, 0.95], acc: 0.3, head: 0.07, turn: 4.5, fov: 1.0, nade: 0.25, retreat: 22, peek: 0.3 },
  { name: 'Бойцы',   react: [0.38, 0.6], acc: 0.44, head: 0.13, turn: 6.5, fov: 1.15, nade: 0.55, retreat: 32, peek: 0.6 },
  { name: 'Спецназ', react: [0.22, 0.38], acc: 0.58, head: 0.22, turn: 9, fov: 1.3, nade: 0.85, retreat: 40, peek: 0.9 },
];
// bomb — режим «Подрыв»: атака закладывает заряд на точке А или Б, защита не даёт или разминирует.
// win — побед до конца матча, maxRounds — всего раундов (ничья при равенстве), half — смена сторон после этого раунда.
// chargeTime — таймер заряда, lateExec — за сколько секунд до конца раунда атака идёт на точку в любом случае.
// startSide — сторона команды «Сталь» (игрока) в первой половине.
const MODES = {
  tdm:    { name: 'Командный бой', size: 5, rounds: false, killLimit: 40, time: 300, tag: '5×5 · до 40 убийств', desc: 'Возрождение через 3 секунды, оружие бесплатно в арсенале. Держите линию и давите вместе.' },
  comp:   { name: 'Подрыв', size: 5, rounds: true, bomb: true, win: 7, maxRounds: 12, half: 6, roundTime: 105, freeze: 8, money: 800, chargeTime: 40, lateExec: 38,
            startSide: 'def', tag: '5×5 · до 7 побед · смена сторон', desc: 'Атака закладывает заряд на точке А или Б, защита держит точки и разминирует. Одна жизнь, экономика.' },
  allies: { name: 'Союзники', size: 2, rounds: true, bomb: true, win: 5, maxRounds: 8, half: 4, roundTime: 70, freeze: 6, money: 1000, chargeTime: 30, lateExec: 28,
            startSide: 'atk', tag: '2×2 · до 5 побед · заряд', desc: 'Ты и напарник против двоих. Короткие раунды с зарядом на двух точках.' },
};
// Порядок кнопок режимов в меню
const MODE_ORDER = ['tdm', 'comp', 'allies'];
if (!MODES[settings.mode]) settings.mode = 'comp';
