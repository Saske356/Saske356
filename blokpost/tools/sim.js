// Ускоренная проверка режима «Подрыв» и ИИ: node tools/sim.js [mode=comp] [матчей=2] [сложность=1]
// Все бойцы — боты (window.__simAllBots), игра обновляется напрямую update(0.05) без отрисовки.
// Печатает: победы по командам и сторонам, как заканчивались раунды, закладки/разминирования, застревания, ошибки.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const mode = process.argv[2] || 'comp', matches = +(process.argv[3] || 2), diff = +(process.argv[4] || 1);
const dev = path.join(root, '.dev.html');
fs.writeFileSync(dev, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>' + fs.readFileSync(path.join(root, 'index.html'), 'utf8') + '</body></html>');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 844, height: 390 } });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message + '\n' + (e.stack || '')));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await p.addInitScript(() => { window.__simAllBots = true; });
  await p.goto('file://' + dev);
  await p.waitForTimeout(1500);
  const t0 = Date.now();
  const all = { rounds: [], matches: [], stuckSim: 0, simTime: 0 };
  for (let m = 0; m < matches; m++) {
    await p.evaluate(([md, df]) => {
      settings.mode = md; settings.diff = df; settings.sound = 0;
      setScreen(null); startMatch(); closeBuy();
      window.__sim = { steps: 0, stuck: 0, last: new Map(), nades: 0 };
      // без модуля гранат — заглушка, чтобы проверить, что боты решают бросать
      if (typeof throwGrenade !== 'function') window.throwGrenade = () => { window.__sim.nades++; return true; };
    }, [mode, diff]);
    for (;;) {
      const r = await p.evaluate(() => {
        const S = window.__sim;
        for (let i = 0; i < 600; i++) {
          update(0.05); S.steps++;
          if (state === 'over') break;
          // своя проверка застревания: живой бот с невыполненным приказом не сдвинулся за 10 с
          if (S.steps % 200 === 0) for (const b of bots) {
            const lp = S.last.get(b);
            if (state === 'live' && b.alive && lp && b.ai && b.ai.order && !b.ai.arrived && !b.planting && !b.defusing && !b.targetVisible && !b.ai.retreat && b.lastSeenT < -2 && gt > b.ai.order.start + 10 && b.pos.distanceTo(lp) < 1) { S.stuck++; (S.types = S.types || {})[b.ai.order.type + ':' + b.ai.order.tag.replace(/[0-9]+/g, '')] = ((S.types || {})[b.ai.order.type + ':' + b.ai.order.tag.replace(/[0-9]+/g, '')] || 0) + 1; }
            S.last.set(b, b.pos.clone());
          }
        }
        return { over: state === 'over', steps: S.steps, scoreA, scoreB };
      });
      if (r.over || r.steps > 60000) {
        const res = await p.evaluate(() => ({ log: roundLog, scoreA, scoreB, stuck: window.__sim.stuck, types: window.__sim.types, steps: window.__sim.steps, obj: objStats, ai: aiStats }));
        all.rounds.push(...res.log); all.matches.push(res.scoreA + ':' + res.scoreB); all.stuckSim += res.stuck; for (const k in res.types || {}) (all.types = all.types || {})[k] = (all.types[k] || 0) + res.types[k]; all.simTime += res.steps * 0.05;
        all.obj = res.obj; all.ai = res.ai;
        console.log(`матч ${m + 1}: ${res.scoreA}:${res.scoreB}, раундов ${res.log.length}`);
        break;
      }
    }
  }
  const cnt = (f) => all.rounds.filter(f).length;
  const codes = {}; for (const r of all.rounds) codes[r.code] = (codes[r.code] || 0) + 1;
  console.log('Режим', mode, 'сложность', diff, '· игрового времени', Math.round(all.simTime), 'с · реального', Math.round((Date.now() - t0) / 1000), 'с');
  console.log('Матчи:', all.matches.join(', '));
  const avgT = all.rounds.reduce((s, r) => s + r.t, 0) / Math.max(1, all.rounds.length);
  console.log('Средняя длина раунда', avgT.toFixed(1), 'с');
  console.log('Раунды: всего', all.rounds.length, '· «Сталь»', cnt(r => r.winner === 'A'), '· «Ржавчина»', cnt(r => r.winner === 'B'));
  console.log('По сторонам: атака', cnt(r => r.winSide === 'atk'), '· защита', cnt(r => r.winSide === 'def'));
  console.log('Исходы:', JSON.stringify(codes), '· раундов с закладкой', cnt(r => r.planted));
  console.log('Заряд:', JSON.stringify(all.obj));
  console.log('ИИ:', JSON.stringify(all.ai), '· застреваний >10 с (проверка теста):', all.stuckSim, JSON.stringify(all.types || {}));
  console.log(errs.length ? 'ОШИБКИ:\n' + errs.slice(0, 10).join('\n') : 'ОШИБОК НЕТ');
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
