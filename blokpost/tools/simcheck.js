// Быстрая проверка без рендера: node tools/simcheck.js [секунд игрового времени]
// Гоняет update() с фиксированным шагом и печатает убийства — видно, что боты ходят по карте и находят друг друга.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..'), secs = +(process.argv[2] || 90);
const dev = path.join(root, '.dev.html');
fs.writeFileSync(dev, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + fs.readFileSync(path.join(root, 'index.html'), 'utf8') + '</body></html>');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  for (const m of ['tdm', 'comp']) {
    await p.goto('file://' + dev); await p.waitForTimeout(1500);
    const r = await p.evaluate(([m, secs]) => {
      document.querySelector('#mode-' + m).click(); document.querySelector('#startBtn').click();
      const c = document.querySelector('#buyClose'); if (c) c.click();
      renderer.render = () => {};
      for (let i = 0; i < 30 * secs; i++) update(1 / 30);
      return units.map(u => u.name + ':' + u.kills + '/' + u.deaths).join(' ') + ' | счёт ' + scoreA + ':' + scoreB + ' | ' + state;
    }, [m, secs]);
    console.log(m, r);
  }
  console.log(errs.length ? 'ОШИБКИ: ' + errs.join('\n') : 'ОШИБОК НЕТ');
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
