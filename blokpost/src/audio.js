'use strict';
/* ---------------- звук ---------------- */
// Цепочка: источники → master → muffle (приглушение при ослеплении) → компрессор → выход; reverbIn → свёртка → master (эхо склада).
let AC = null, master = null, noiseBuf = null, muffle = null, reverbIn = null;
function makeIR(sec, decay) {
  const n = Math.floor(AC.sampleRate * sec), b = AC.createBuffer(2, n, AC.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = b.getChannelData(ch);
    for (let i = 0; i < n; i++) {
      const t = i / n, early = (i % 1700 < 40 && t < 0.25) ? 2.5 : 1;
      d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, decay) * early * (t < 0.01 ? t / 0.01 : 1);
    }
  }
  return b;
}
function initAudio() {
  if (AC) { if (AC.state === 'suspended') AC.resume(); return; }
  try {
    AC = new (window.AudioContext || window.webkitAudioContext)();
    const comp = AC.createDynamicsCompressor();
    comp.threshold.value = -12; comp.knee.value = 8; comp.ratio.value = 5; comp.attack.value = 0.002; comp.release.value = 0.2;
    comp.connect(AC.destination);
    muffle = AC.createBiquadFilter(); muffle.type = 'lowpass'; muffle.frequency.value = 20000; muffle.Q.value = 0.5; muffle.connect(comp);
    master = AC.createGain(); master.gain.value = 0.5; master.connect(muffle);
    noiseBuf = AC.createBuffer(1, AC.sampleRate * 1.2, AC.sampleRate);
    const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const verb = AC.createConvolver(); verb.buffer = makeIR(1.7, 3.2);
    reverbIn = AC.createGain(); reverbIn.gain.value = 0.55; reverbIn.connect(verb);
    const vf = AC.createBiquadFilter(); vf.type = 'lowpass'; vf.frequency.value = 2600; verb.connect(vf); vf.connect(master);
  } catch (e) { AC = null; }
}
const audioOn = () => AC && settings.sound && master;
/* --- примитивы --- */
// выход с панорамой и фильтром дальности; send — доля в эхо
function outNode(pan, cut, send) {
  const p = AC.createStereoPanner ? AC.createStereoPanner() : AC.createGain();
  if (p.pan) p.pan.value = clamp(pan || 0, -1, 1);
  let head = p;
  if (cut && cut < 18000) { const f = AC.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = cut; f.connect(p); head = f; }
  p.connect(master);
  if (send > 0.001) { const s = AC.createGain(); s.gain.value = send; p.connect(s); s.connect(reverbIn); }
  return head;
}
function nz(out, t, o) {
  const src = AC.createBufferSource(); src.buffer = noiseBuf; src.playbackRate.value = o.rate || 1;
  const f = AC.createBiquadFilter(); f.type = o.type || 'bandpass'; f.Q.value = o.q || 0.8;
  f.frequency.setValueAtTime(o.f, t); if (o.f2) f.frequency.exponentialRampToValueAtTime(Math.max(30, o.f2), t + o.dur);
  const g = AC.createGain(), a = o.att || 0.001;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(o.vol, t + a); g.gain.exponentialRampToValueAtTime(0.0005, t + a + o.dur);
  src.connect(f); f.connect(g); g.connect(out);
  src.start(t, Math.random() * 0.5); src.stop(t + a + o.dur + 0.05);
}
function tn(out, t, o) {
  const os = AC.createOscillator(); os.type = o.type || 'sine';
  os.frequency.setValueAtTime(o.f, t); if (o.f2) os.frequency.exponentialRampToValueAtTime(Math.max(20, o.f2), t + (o.sweep || o.dur));
  const g = AC.createGain(), a = o.att || 0.001;
  g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(o.vol, t + a); g.gain.exponentialRampToValueAtTime(0.0005, t + a + o.dur);
  os.connect(g); g.connect(out); os.start(t); os.stop(t + a + o.dur + 0.05);
}
// громкость, панорама и фильтр для звука в точке мира относительно слушателя
function spatial(x, z, ref = 8) {
  const L = listener(), d = Math.hypot(x - L.x, z - L.z);
  const rel = angDiff(yawTo(L.x, L.z, x, z), L.yaw);
  const behind = Math.abs(rel) > Math.PI / 2;
  return { d, vol: 1 / (1 + d / ref), pan: -Math.sin(rel) * 0.85, cut: Math.max(700, 20000 * Math.exp(-d / 28)) * (behind ? 0.45 : 1), delay: d / 343 };
}
/* --- выстрелы --- */
function gunSound(c, vol, pan, cut, delay, send, close) {
  if (!audioOn() || vol < 0.02) return;
  const t = AC.currentTime + (delay || 0), out = outNode(pan, cut, send * c.tail), v = vol * c.vol, j = rand(0.95, 1.05);
  if (c.kind === 'supp') {
    nz(out, t, { type: 'lowpass', f: c.body * 2.2 * j, f2: 200, q: 0.6, dur: c.dur, vol: v * 0.9 });
    nz(out, t, { type: 'bandpass', f: c.crack * j, q: 1.5, dur: 0.02, vol: v * 0.35 });
    tn(out, t, { f: c.thump * j, f2: 40, dur: 0.08, vol: v * 0.6 });
  } else {
    nz(out, t, { type: 'highpass', f: c.crack * j, q: 0.7, dur: 0.012 + (close ? 0.006 : 0), vol: v * (close ? 1.1 : 0.7) });
    nz(out, t, { type: 'bandpass', f: c.body * j, f2: c.body * 0.25, q: 0.7, dur: c.dur, vol: v * 1.25 });
    nz(out, t, { type: 'lowpass', f: 2400 * j, f2: 120, q: 0.5, dur: c.dur * 1.6, vol: v * 0.8 });
    tn(out, t, { f: c.thump * 1.6 * j, f2: 32, sweep: 0.14, dur: 0.18 + (c.kind === 'shotgun' || c.kind === 'sniper' ? 0.12 : 0), vol: v * (close ? 1 : 0.7) });
    // хвост: отражение от стен склада
    nz(out, t + rand(0.05, 0.09), { type: 'lowpass', f: 900, f2: 160, q: 0.4, dur: 0.25 * c.tail + 0.1, vol: v * 0.22, att: 0.02 });
  }
  if (close) tn(out, t, { type: 'square', f: c.mech * j, f2: c.mech * 0.6, dur: 0.015, vol: v * 0.05 });
}
// выстрел у игрока или в точке мира
function sfxGun(key, pos) {
  const c = (WEAPONS[key] || WEAPONS.pistol).snd; if (!c || !AC) return;
  if (!pos) return gunSound(c, 1, 0, 0, 0, 0.35, true);
  const s = spatial(pos.x, pos.z, c.kind === 'supp' ? 6 : 12);
  gunSound(c, 0.95 * s.vol, s.pan, s.cut, Math.min(0.25, s.delay), 0.35 + Math.min(0.9, s.d / 40), false);
}
function sfxShot(cfg, vol, pan) { if (cfg && cfg.kind) gunSound(cfg, vol, pan, 0, 0, 0.4, vol > 0.9); }
/* --- прочее --- */
function at(pos, ref) { if (!pos) return { vol: 1, pan: 0, cut: 0, delay: 0, d: 0 }; return spatial(pos.x, pos.z, ref || 6); }
function play(pos, ref, fn, send = 0.15) {
  if (!audioOn()) return;
  const s = at(pos, ref); if (s.vol < 0.03) return;
  fn(outNode(s.pan, s.cut, send), AC.currentTime + Math.min(0.2, s.delay), s.vol, s);
}
function beep(freq, dur, vol, type) {
  if (!audioOn()) return;
  tn(master, AC.currentTime, { f: freq, dur, vol, type: type || 'square' });
}
let hitCtx = { helmet: false, armor: false };
function sfxHit(head) {
  play(null, 0, (o, t) => {
    if (head && hitCtx.helmet) { tn(o, t, { f: 2900, f2: 2500, dur: 0.25, vol: 0.14 }); tn(o, t, { f: 4300, dur: 0.15, vol: 0.06, type: 'triangle' }); }
    else if (head) { tn(o, t, { f: 1900, dur: 0.07, vol: 0.14, type: 'triangle' }); nz(o, t, { f: 500, q: 1, dur: 0.06, vol: 0.2 }); }
    else if (hitCtx.armor) { nz(o, t, { f: 1500, q: 2, dur: 0.05, vol: 0.18 }); tn(o, t, { f: 1250, dur: 0.05, vol: 0.08, type: 'triangle' }); }
    else { tn(o, t, { f: 1300, dur: 0.05, vol: 0.1, type: 'triangle' }); nz(o, t, { f: 300, q: 0.8, dur: 0.06, vol: 0.22 }); }
  }, 0);
}
const sfxClick = () => play(null, 0, (o, t) => { tn(o, t, { f: 1800, dur: 0.015, vol: 0.12, type: 'square' }); nz(o, t, { f: 3000, q: 2, dur: 0.02, vol: 0.1 }); });
const sfxHurt = () => play(null, 0, (o, t) => { nz(o, t, { type: 'lowpass', f: 400, q: 0.7, dur: 0.12, vol: 0.5 }); tn(o, t, { f: 110, f2: 70, dur: 0.12, vol: 0.18, type: 'sawtooth' }); });
// механика оружия (pos = null — у игрока)
const sfxMagOut = pos => play(pos, 4, (o, t, v) => { tn(o, t, { f: 2300, dur: 0.012, vol: 0.12 * v, type: 'square' }); nz(o, t + 0.01, { f: 1600, f2: 700, q: 1.2, dur: 0.12, vol: 0.22 * v }); });
const sfxMagIn = pos => play(pos, 4, (o, t, v) => { nz(o, t, { f: 900, f2: 500, q: 1, dur: 0.05, vol: 0.3 * v }); tn(o, t + 0.04, { f: 1700, dur: 0.02, vol: 0.18 * v, type: 'square' }); nz(o, t + 0.04, { f: 3200, q: 2, dur: 0.02, vol: 0.2 * v }); });
const sfxBoltRack = pos => play(pos, 4, (o, t, v) => { nz(o, t, { f: 2200, f2: 900, q: 1.5, dur: 0.07, vol: 0.25 * v }); tn(o, t + 0.09, { f: 1400, dur: 0.025, vol: 0.18 * v, type: 'square' }); nz(o, t + 0.09, { f: 2800, q: 1.4, dur: 0.05, vol: 0.28 * v }); });
const sfxPump = pos => play(pos, 5, (o, t, v) => { nz(o, t, { f: 1200, f2: 600, q: 1, dur: 0.08, vol: 0.3 * v }); nz(o, t + 0.16, { f: 1700, f2: 900, q: 1, dur: 0.07, vol: 0.32 * v }); tn(o, t + 0.2, { f: 900, dur: 0.02, vol: 0.12 * v, type: 'square' }); });
const sfxShellIn = pos => play(pos, 4, (o, t, v) => { nz(o, t, { f: 1500, q: 2, dur: 0.04, vol: 0.2 * v }); tn(o, t + 0.03, { f: 2400, dur: 0.012, vol: 0.08 * v, type: 'square' }); });
const sfxSniperBolt = pos => play(pos, 4, (o, t, v) => {
  tn(o, t, { f: 1600, dur: 0.02, vol: 0.12 * v, type: 'square' }); nz(o, t + 0.08, { f: 1800, f2: 800, q: 1.3, dur: 0.1, vol: 0.25 * v });
  nz(o, t + 0.3, { f: 1100, f2: 2200, q: 1.3, dur: 0.09, vol: 0.25 * v }); tn(o, t + 0.42, { f: 1300, dur: 0.02, vol: 0.14 * v, type: 'square' });
});
const sfxReload = () => sfxMagOut(null);
const sfxDraw = () => play(null, 0, (o, t) => { nz(o, t, { f: 700, f2: 1400, q: 0.8, dur: 0.12, vol: 0.12, att: 0.03 }); tn(o, t + 0.12, { f: 1900, dur: 0.012, vol: 0.06, type: 'square' }); });
const sfxPickup = () => play(null, 0, (o, t) => { nz(o, t, { f: 900, q: 0.8, dur: 0.1, vol: 0.2 }); tn(o, t + 0.08, { f: 1500, dur: 0.02, vol: 0.12, type: 'square' }); });
// нож
const sfxSwing = (pos, heavy) => play(pos, 4, (o, t, v) => nz(o, t, { f: heavy ? 700 : 1100, f2: heavy ? 2400 : 3600, q: 1.6, dur: heavy ? 0.2 : 0.13, vol: 0.35 * v, att: 0.03 }));
const sfxStab = (pos, flesh) => play(pos, 5, (o, t, v) => {
  if (flesh) { nz(o, t, { type: 'lowpass', f: 700, f2: 200, q: 0.7, dur: 0.12, vol: 0.6 * v }); tn(o, t, { f: 160, f2: 70, dur: 0.1, vol: 0.3 * v }); }
  else { tn(o, t, { f: 3400, f2: 2900, dur: 0.14, vol: 0.14 * v, type: 'triangle' }); nz(o, t, { f: 3000, q: 2, dur: 0.04, vol: 0.3 * v }); }
});
// гранаты
const sfxPin = () => play(null, 0, (o, t) => { tn(o, t, { f: 3100, f2: 2600, dur: 0.12, vol: 0.08, type: 'triangle' }); nz(o, t, { f: 4000, q: 3, dur: 0.03, vol: 0.12 }); tn(o, t + 0.2, { f: 1900, dur: 0.02, vol: 0.06, type: 'square' }); });
const sfxThrow = pos => play(pos, 4, (o, t, v) => nz(o, t, { f: 500, f2: 1800, q: 1, dur: 0.18, vol: 0.3 * v, att: 0.05 }));
const sfxBounce = (pos, k) => play(pos, 6, (o, t, v) => { const f = rand(1600, 2600); tn(o, t, { f, f2: f * 0.8, dur: 0.06, vol: 0.12 * v * k, type: 'triangle' }); nz(o, t, { f: 2000, q: 1.5, dur: 0.03, vol: 0.18 * v * k }); });
const sfxExplode = pos => play(pos, 16, (o, t, v, s) => {
  nz(o, t, { type: 'highpass', f: 1800, q: 0.6, dur: 0.05, vol: 1.2 * v });
  nz(o, t, { type: 'lowpass', f: 3000, f2: 90, q: 0.5, dur: 1.1, vol: 1.6 * v });
  tn(o, t, { f: 90, f2: 28, sweep: 0.5, dur: 0.7, vol: 1.3 * v });
  nz(o, t + 0.25, { type: 'bandpass', f: 2500, q: 0.8, dur: 0.6, vol: 0.12 * v, att: 0.1 });
}, 1.1);
const sfxFlashBang = pos => play(pos, 16, (o, t, v) => {
  nz(o, t, { type: 'highpass', f: 1200, q: 0.5, dur: 0.08, vol: 1.6 * v });
  nz(o, t, { type: 'lowpass', f: 5000, f2: 300, q: 0.5, dur: 0.5, vol: 0.9 * v });
  tn(o, t, { f: 140, f2: 40, sweep: 0.3, dur: 0.4, vol: 0.8 * v });
}, 1);
const sfxSmoke = pos => play(pos, 6, (o, t, v) => { nz(o, t, { type: 'highpass', f: 2500, q: 0.4, dur: 3.2, vol: 0.18 * v, att: 0.3 }); nz(o, t, { f: 600, q: 0.6, dur: 2.5, vol: 0.12 * v, att: 0.4 }); }, 0.3);
// шаги
function sfxStep(pos, k) {
  play(pos, 3.5, (o, t, v) => {
    const f = rand(600, 900);
    nz(o, t, { type: 'lowpass', f: f * 2, f2: f * 0.6, q: 0.8, dur: 0.06, vol: 0.5 * v * k });
    nz(o, t + 0.015, { f: rand(1800, 2600), q: 1.5, dur: 0.03, vol: 0.12 * v * k });
    tn(o, t, { f: rand(70, 95), f2: 45, dur: 0.07, vol: 0.4 * v * k });
  }, 0.05);
}
const sfxLand = pos => play(pos, 4, (o, t, v) => { nz(o, t, { type: 'lowpass', f: 900, f2: 200, q: 0.6, dur: 0.12, vol: 0.6 * v }); tn(o, t, { f: 90, f2: 40, dur: 0.12, vol: 0.4 * v }); nz(o, t + 0.02, { f: 1600, q: 1, dur: 0.06, vol: 0.12 * v }); }, 0.05);
// оглушение от светошумовой: глушим всё, пищит в ушах
function flashMuffle(sec) {
  if (!AC || !muffle) return;
  const t = AC.currentTime, f = muffle.frequency;
  f.cancelScheduledValues(t); f.setValueAtTime(Math.min(f.value, 20000), t); f.exponentialRampToValueAtTime(320, t + 0.05);
  f.setValueAtTime(320, t + sec * 0.55); f.exponentialRampToValueAtTime(20000, t + sec);
  if (settings.sound) {
    const os = AC.createOscillator(), g = AC.createGain(); os.frequency.value = 3600;
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.05, t + 0.05); g.gain.exponentialRampToValueAtTime(0.0005, t + sec);
    os.connect(g); g.connect(AC.destination); os.start(t); os.stop(t + sec + 0.1);
  }
}
