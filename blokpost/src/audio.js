'use strict';
/* ---------------- звук ---------------- */
let AC = null, master = null, noiseBuf = null;
function initAudio() {
  if (AC) { if (AC.state === 'suspended') AC.resume(); return; }
  try {
    AC = new (window.AudioContext || window.webkitAudioContext)();
    master = AC.createGain(); master.gain.value = 0.5; master.connect(AC.destination);
    noiseBuf = AC.createBuffer(1, AC.sampleRate * 0.6, AC.sampleRate);
    const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  } catch (e) { AC = null; }
}
function sfxShot(cfg, vol, pan) {
  if (!AC || !settings.sound || vol < 0.03) return;
  const t = AC.currentTime;
  const out = AC.createStereoPanner ? AC.createStereoPanner() : AC.createGain();
  if (out.pan) out.pan.value = clamp(pan || 0, -1, 1);
  out.connect(master);
  const src = AC.createBufferSource(); src.buffer = noiseBuf;
  const f = AC.createBiquadFilter(); f.type = 'lowpass';
  const fq = cfg.f * (0.4 + 0.6 * vol);
  f.frequency.setValueAtTime(fq, t); f.frequency.exponentialRampToValueAtTime(Math.max(80, fq * 0.12), t + cfg.d);
  const g = AC.createGain(); g.gain.setValueAtTime(vol * cfg.v, t); g.gain.exponentialRampToValueAtTime(0.001, t + cfg.d);
  src.connect(f); f.connect(g); g.connect(out); src.start(t); src.stop(t + cfg.d + 0.05);
  const o = AC.createOscillator(); o.type = 'sine';
  o.frequency.setValueAtTime(cfg.th, t); o.frequency.exponentialRampToValueAtTime(38, t + 0.14);
  const og = AC.createGain(); og.gain.setValueAtTime(Math.max(0.002, vol * 0.7 * cfg.v), t); og.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
  o.connect(og); og.connect(out); o.start(t); o.stop(t + 0.18);
}
function beep(freq, dur, vol, type) {
  if (!AC || !settings.sound) return;
  const t = AC.currentTime, o = AC.createOscillator(), g = AC.createGain();
  o.type = type || 'square'; o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.001, t + dur);
  o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + 0.02);
}
const sfxHit = head => beep(head ? 1900 : 1300, 0.06, 0.12, 'triangle');
const sfxClick = () => beep(420, 0.04, 0.08);
const sfxReload = () => { beep(260, 0.05, 0.07); setTimeout(() => beep(520, 0.05, 0.07), 160); };
const sfxHurt = () => beep(110, 0.12, 0.2, 'sawtooth');
