// Осмотр карты: node tools/mapview.js <папка> [gfx] [shadows]
// Снимает вид сверху и несколько ракурсов, проверяет связность (findPath), печатает число вызовов отрисовки.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const out = process.argv[2] || '/tmp/mapview', gfx = process.argv[3] || 'medium', shadows = process.argv[4] === '1';
fs.mkdirSync(out, { recursive: true });
const dev = path.join(root, '.dev.html');
fs.writeFileSync(dev, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + fs.readFileSync(path.join(root, 'index.html'), 'utf8') + '</body></html>');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message + '\n' + (e.stack || '')));
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push('CONSOLE ' + m.text()); });
  await p.goto('file://' + dev);
  await p.waitForTimeout(1500);
  const info = await p.evaluate(([gfx, shadows]) => {
    settings.gfx = gfx; settings.shadows = shadows;
    const t0 = performance.now(); applyGraphics(); resize();
    const buildMs = Math.round(performance.now() - t0);
    document.querySelector('#menu') && (document.querySelector('#menu').style.display = 'none');
    const orig = renderer.render.bind(renderer);
    window.__cam = null;
    renderer.render = (s, c) => orig(s, s === scene && window.__cam ? window.__cam : c);
    // связность
    const bad = [];
    const c = v => [Math.floor(v.x / CELL), Math.floor(v.z / CELL)];
    for (const zone of ['atk', 'def']) for (const sp of [spawnZones[zone][0]]) {
      const [sx, sz] = c(sp);
      for (const [x, z] of openCells) if (!findPath(sx, sz, x, z)) bad.push(zone + '->' + x + ',' + z);
      for (const s of SITES) { const [tx, tz] = s.cells[0]; const pth = findPath(sx, sz, tx, tz); if (!pth) bad.push(zone + '->site' + s.id); else window['len_' + zone + s.id] = pth.length; }
    }
    return { buildMs, bad: bad.slice(0, 10), nbad: bad.length, open: openCells.length, lens: ['atkA', 'atkB', 'defA', 'defB'].map(k => k + ':' + window['len_' + k]), spawns: [spawns.A.length, spawns.B.length] };
  }, [gfx, shadows]);
  console.log(JSON.stringify(info));
  const views = {
    top: { ortho: true },
    defspawn: [6, 1.7, 36, 25, 1.4, 12],
    siteA: [36, 1.7, 7, 14, 1.4, 14],
    siteB: [36, 1.7, 52, 14, 1.4, 64],
    mid: [95, 1.7, 36, 40, 1.6, 36],
    road: [112, 1.7, 6, 40, 1.6, 6],
    office: [62, 1.7, 21, 42, 1.4, 18],
    warehouse: [80, 1.7, 54, 42, 1.4, 56],
    tunnel: [75, 1.7, 67, 40, 1.6, 67],
    atkspawn: [112, 1.7, 36, 80, 2, 36],
    menu: 'menu',
  };
  for (const [name, v] of Object.entries(views)) {
    const stat = await p.evaluate(v => {
      let cam;
      if (v === 'menu') { window.__cam = null; return null; }
      if (v.ortho) {
        const W = MW * CELL, H = MH * CELL;
        cam = new THREE.OrthographicCamera(-W / 2 * 1.05, W / 2 * 1.05, H / 2 * 1.05 * 844 / 390 / (W / H), -H / 2 * 1.05 * 844 / 390 / (W / H), 1, 400);
        const asp = 844 / 390, half = Math.max(W / 2, H / 2 * asp) * 1.03;
        cam.left = -half; cam.right = half; cam.top = half / asp; cam.bottom = -half / asp; cam.updateProjectionMatrix();
        cam.position.set(W / 2, 200, H / 2); cam.up.set(0, 0, -1); cam.lookAt(W / 2, 0, H / 2);
        window.__fog = window.__fog || scene.fog; scene.fog = null;
      } else {
        if (window.__fog) scene.fog = window.__fog;
        cam = new THREE.PerspectiveCamera(74, 844 / 390, 0.05, 900); cam.position.set(v[0], v[1], v[2]); cam.lookAt(v[3], v[4], v[5]);
      }
      window.__cam = cam;
      const orig = Object.getPrototypeOf(renderer).render.bind(renderer);
      renderer.info.autoReset = false; renderer.info.reset(); renderer.clear(); orig(scene, cam);
      const r = renderer.info.render; const o = { calls: r.calls, tris: r.triangles }; renderer.info.autoReset = true;
      return o;
    }, v);
    await p.waitForTimeout(700);
    const ri = stat;
    await p.screenshot({ path: path.join(out, name + '.png') });
    console.log(name, JSON.stringify(ri));
  }
  console.log(errs.length ? 'ОШИБКИ:\n' + errs.join('\n') : 'ОШИБОК НЕТ');
  await b.close();
})();
