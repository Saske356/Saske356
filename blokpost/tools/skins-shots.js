// Скриншоты инвентаря и скинов: node tools/skins-shots.js <папка> [ширина] [высота]
// Инвентарь, превью ствола и бойца, открытие кейса, вид от первого лица со скинами на нескольких стволах.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const out = process.argv[2] || path.join(root, '.shots'), W = +(process.argv[3] || 844), H = +(process.argv[4] || 390);
const dev = path.join(root, '.dev.html');
fs.writeFileSync(dev, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + fs.readFileSync(path.join(root, 'index.html'), 'utf8') + '</body></html>');
fs.mkdirSync(out, { recursive: true });
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: W, height: H }, hasTouch: true, isMobile: true });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message + '\n' + (e.stack || '')));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await p.goto('file://' + dev);
  await p.waitForTimeout(1500);
  const shot = async n => { await p.screenshot({ path: path.join(out, n + '.png') }); };
  await shot('menu');
  // выдаём набор предметов для показа
  await p.evaluate(() => {
    INV.items = []; INV.tokens = 1200;
    const add = (t, id, w) => { const it = { uid: INV.uid++, t, id, w }; INV.items.push(it); return it; };
    for (const id of ['prospekt', 'vyaz', 'magma', 'bulat', 'carbon', 'garages', 'tiger', 'forest', 'digital', 'mirror', 'owl', 'ninth']) add('g', id, Math.random() * 0.5);
    for (const id of ['a_legion', 'a_polar', 'a_ranger', 'b_ember', 'b_dune']) add('c', id, 0);
    invSave();
    openInventory('guns');
  });
  await p.waitForTimeout(700);
  await shot('inv-guns');
  const pickCard = async name => p.evaluate(n => { const c = [...document.querySelectorAll('#inv .ivg .ivc')].find(x => x.querySelector('b').textContent === n); if (c) c.click(); }, name);
  for (const [n, w] of [['Неоновый проспект', 'carbine'], ['Червонная вязь', 'pistol'], ['Магма', 'sniper'], ['Булатная волна', 'rifle']]) {
    await p.evaluate(k => { IVU.wk = k; IVU.sel = null; ivRenderGuns(); }, w);
    await pickCard(n); await p.waitForTimeout(500); await shot('inv-' + w);
  }
  await p.evaluate(() => ivTab('chars'));
  await pickCard('Стальной легион'); await p.waitForTimeout(600); await shot('inv-char-A');
  await p.evaluate(() => { IVU.team = 'B'; IVU.sel = null; ivRenderChars(); });
  await pickCard('Уголь'); await p.waitForTimeout(600); await shot('inv-char-B');
  await p.evaluate(() => ivTab('cases'));
  await p.waitForTimeout(500); await shot('inv-cases');
  await p.evaluate(() => ivStartOpening('midnight'));
  await p.waitForTimeout(1200); await shot('case-spin');
  await p.waitForTimeout(5600); await shot('case-result');
  // экипируем разные скины и смотрим от первого лица
  await p.evaluate(() => {
    ivCloseOpening();
    const by = id => INV.items.find(i => i.id === id).uid;
    Object.assign(INV.eqGun, { pistol: by('vyaz'), rifle: by('bulat'), carbine: by('prospekt'), sniper: by('magma'), smg: by('garages'), shotgun: by('tiger') });
    INV.eqChar.A = by('a_legion');
    ivApplyEquip(); closeInventory();
  });
  await p.evaluate(() => { document.querySelector('#mode-tdm').click(); document.querySelector('#startBtn').click(); });
  await p.waitForTimeout(800);
  await p.evaluate(() => { const c = document.querySelector('#buyClose'); if (c) c.click(); });
  for (const k of ['carbine', 'pistol', 'rifle', 'sniper', 'smg', 'shotgun']) {
    await p.evaluate(k => { const g = window.__game; g.player.primary = k === 'pistol' ? g.player.primary : k; g.giveAmmo(g.player, k); g.equip(g.player, k, true); g.player.pitch = -0.05; }, k);
    await p.waitForTimeout(700); await shot('fp-' + k);
  }
  const info = await p.evaluate(() => ({ mats: skMatCount, tokens: INV.tokens, botSkins: bots.map(b => (b.skin || '-') + '/' + (b.gunSkin ? b.gunSkin.skin : '-')) }));
  console.log(JSON.stringify(info));
  console.log(errs.length ? 'ОШИБКИ:\n' + errs.join('\n') : 'ОШИБОК НЕТ');
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
