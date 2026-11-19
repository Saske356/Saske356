// Нагрузочный тест: N ботов заходят и бегают по городу. Меряем CPU и память сервера, трафик.
// Запуск: node tools/bench.mjs <порт> <pid сервера> [число ботов]
import WebSocket from 'ws';
import fs from 'node:fs';
const [port, pid, N] = [process.argv[2], process.argv[3], Number(process.argv[4] || 300)];
const names = 'Ivan Oleg Anna Petr Maria Igor Olga Pavel Nina Denis Elena Artem Sofia Kirill Vera Roman'.split(' ');
const sur = 'Petrov Ivanov Smirnov Volkov Orlov Popov Kozlov Sokolov Lebedev Morozov Novikov Fedorov'.split(' ');
let bytes = 0, snaps = 0, logged = 0, t0;
const cpuParts = () => { const f = fs.readFileSync(`/proc/${pid}/stat`, 'utf8').split(') ')[1].split(' '); return [Number(f[11]) / 100, Number(f[12]) / 100]; };
const cpu = () => { const [u, s] = cpuParts(); return u + s; };
const rss = () => Number(/VmRSS:\s+(\d+)/.exec(fs.readFileSync(`/proc/${pid}/status`, 'utf8'))[1]) / 1024;
const bots = [];
const loginStart = Date.now();
for (let i = 0; i < N; i++) {
  const ws = new WebSocket(`ws://localhost:${port}/ws`);
  const b = { ws, x: 16 + Math.random() * 620, z: 16 + Math.random() * 620, a: Math.random() * 6.28, ok: false };
  bots.push(b);
  ws.on('open', () => ws.send(JSON.stringify({ t: 'login', name: `${names[i % 16]}_${sur[(i >> 4) % 12]}${String.fromCharCode(97 + (i % 26))}${String.fromCharCode(97 + ((i / 26) | 0) % 26)}`, pass: 'bench123' })));
  ws.on('message', (d) => {
    if (!b.ok) { const m = JSON.parse(d); if (m.t === 'welcome') { b.ok = true; logged++; } else if (m.t === 'error') console.log('err', m.text); return; }
    if (t0) { bytes += d.length; if (d[2] === 116 && d[6] === 115) snaps++; }
  });
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
while (logged < N && Date.now() - loginStart < 120000) await wait(100);
console.log(`вход ${logged}/${N} ботов за ${((Date.now() - loginStart) / 1000).toFixed(1)} с`);
setInterval(() => {
  for (const b of bots) {
    if (!b.ok) continue;
    b.a += (Math.random() - 0.5) * 0.3; b.x = Math.min(640, Math.max(16, b.x + Math.sin(b.a) * 0.4)); b.z = Math.min(640, Math.max(16, b.z + Math.cos(b.a) * 0.4));
    b.ws.send(JSON.stringify({ t: 'state', x: b.x, y: 0, z: b.z, ry: b.a, anim: 1, vry: 0, spd: 0 }));
  }
}, 66);
await wait(3000);
const c0 = cpu(), p0 = cpuParts(); t0 = Date.now();
await wait(20000);
const sec = (Date.now() - t0) / 1000, used = cpu() - c0;
const p1 = cpuParts(); console.log(`  из них код: ${((p1[0]-p0[0])/sec*100).toFixed(1)}%, ядро ОС (сеть): ${((p1[1]-p0[1])/sec*100).toFixed(1)}%`);
console.log(`CPU сервера: ${(used / sec * 100).toFixed(1)}% одного ядра | память: ${rss().toFixed(0)} МБ`);
console.log(`трафик к игрокам: ${(bytes / sec / 1048576).toFixed(1)} МБ/с всего, ${(bytes / sec / logged / 1024).toFixed(1)} КБ/с на игрока | снимков/с на игрока: ${(snaps / sec / logged).toFixed(1)}`);
process.exit(0);
