'use strict';
/* ---------------- режимы и сложность ---------------- */
const DIFF = [
  { name: 'Новички', react: [0.6, 0.95], acc: 0.3, head: 0.07, turn: 4.5, fov: 1.0 },
  { name: 'Бойцы',   react: [0.38, 0.6], acc: 0.44, head: 0.13, turn: 6.5, fov: 1.15 },
  { name: 'Спецназ', react: [0.22, 0.38], acc: 0.58, head: 0.22, turn: 9, fov: 1.3 },
];
const MODES = {
  tdm:    { name: 'Командный бой', size: 5, rounds: false, killLimit: 40, time: 300, tag: '5×5 · до 40 убийств', desc: 'Возрождение через 3 секунды, оружие бесплатно в арсенале.' },
  comp:   { name: 'Соревновательный', size: 5, rounds: true, win: 8, roundTime: 115, freeze: 6, money: 800, tag: '5×5 · до 8 побед', desc: 'Одна жизнь на раунд, экономика и закупка.' },
  allies: { name: 'Союзники', size: 2, rounds: true, win: 6, roundTime: 75, freeze: 5, money: 1000, tag: '2×2 · до 6 побед', desc: 'Ты и напарник против двоих. Короткие раунды.' },
};
if (!MODES[settings.mode]) settings.mode = 'comp';
