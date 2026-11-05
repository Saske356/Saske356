// Быстрая проверка: node tools/smoke.js [mode] [seconds] [shotsDir]
// Открывает игру в Chromium (эмуляция телефона), запускает матч, ждёт и печатает ошибки консоли.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const mode = process.argv[2] || 'comp', secs = +(process.argv[3] || 15), shots = process.argv[4] || null;
const dev = path.join(root, '.dev.html');
fs.writeFileSync(dev, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + fs.readFileSync(path.join(root, 'index.html'), 'utf8') + '</body></html>');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message + '\n' + (e.stack || '')));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await p.goto('file://' + dev);
  await p.waitForTimeout(2000);
  if (shots) { fs.mkdirSync(shots, { recursive: true }); await p.screenshot({ path: path.join(shots, 'menu.png') }); }
  await p.evaluate(m => { const b = document.querySelector('#mode-' + m); if (b) b.click(); document.querySelector('#startBtn').click(); }, mode);
  await p.waitForTimeout(600);
  await p.evaluate(() => { const c = document.querySelector('#buyClose'); if (c) c.click(); });
  await p.evaluate(() => { const g = window.__game; g.input.keys.KeyW = true; g.input.fire = true; });
  for (let t = 0; t < secs; t += 5) {
    await p.waitForTimeout(5000);
    if (shots) await p.screenshot({ path: path.join(shots, `t${t + 5}.png`) });
  }
  const info = await p.evaluate(() => { const g = window.__game; return { state: g.state, units: g.units.map(u => `${u.name}:${u.team}:${u.alive ? 'жив' : 'мёртв'}:${u.kills}/${u.deaths}:${u.cur}`) }; });
  console.log(JSON.stringify(info));
  console.log(errs.length ? 'ОШИБКИ:\n' + errs.join('\n') : 'ОШИБОК НЕТ');
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
