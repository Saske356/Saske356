// Encrypted media: upload, decrypt-on-demand, voice notes, UI sounds.
import { encryptFile, decryptFile } from './crypto.js';
import { uploadBlob, downloadBlob } from './net.js';
import { $$, duration, toast } from './util.js';

// ---------- encrypted blobs ----------
const urls = new Map(); // blob id -> Promise<objectURL>
export function blobUrl(f) {
  if (!urls.has(f.id)) {
    const p = (async () => {
      const buf = await decryptFile(await downloadBlob(f.id), f.key, f.iv);
      return URL.createObjectURL(new Blob([buf], { type: f.type || 'application/octet-stream' }));
    })();
    p.catch(() => urls.delete(f.id));
    urls.set(f.id, p);
  }
  return urls.get(f.id);
}
export async function rawBlob(f) { return downloadBlob(f.id); }
export async function reupload(f) { return uploadBlob(await downloadBlob(f.id)); }

export async function uploadEncrypted(buf, onProgress) {
  const { data, key, iv } = await encryptFile(buf);
  const id = await uploadBlob(data, onProgress);
  return { id, key, iv };
}

// Images: downscale huge photos, measure, and make a tiny blurred preview that travels inside the encrypted payload.
export async function prepareImage(file) {
  const bmp = await createImageBitmap(file);
  let { width: w, height: h } = bmp;
  let blob = file;
  const MAX = 2560;
  if (file.type !== 'image/gif' && (w > MAX || h > MAX || file.size > 3e6)) {
    const k = Math.min(1, MAX / Math.max(w, h));
    const c = new OffscreenCanvas(Math.round(w * k), Math.round(h * k));
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    blob = await c.convertToBlob({ type: 'image/jpeg', quality: 0.86 });
    w = c.width; h = c.height;
  }
  const tw = 24, th = Math.max(1, Math.round(24 * h / w));
  const tc = document.createElement('canvas'); tc.width = tw; tc.height = th;
  tc.getContext('2d').drawImage(bmp, 0, 0, tw, th);
  bmp.close?.();
  return { blob, w, h, thumb: tc.toDataURL('image/jpeg', 0.6), type: blob.type || file.type };
}

// Fill <img data-blob> placeholders after a render.
export function hydrate(root, files) {
  for (const img of $$('img[data-blob]:not([src])', root)) {
    const f = files(img.dataset.blob);
    if (!f) continue;
    blobUrl(f).then(u => { img.src = u; img.onload = () => img.classList.add('ready'); }).catch(() => img.closest('.media')?.classList.add('broken'));
  }
}

export async function saveFile(f) {
  try {
    const u = await blobUrl(f);
    const a = document.createElement('a'); a.href = u; a.download = f.name || 'file'; a.click();
  } catch { toast('Не удалось скачать файл', 'bad'); }
}

// ---------- voice recording ----------
let rec = null;
export async function startRecording(onTick) {
  if (rec) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Запись голоса недоступна в этом браузере');
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'].find(t => MediaRecorder.isTypeSupported(t)) || '';
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 40000 } : undefined);
  const ac = new AudioContext();
  const an = ac.createAnalyser(); an.fftSize = 1024;
  ac.createMediaStreamSource(stream).connect(an);
  const chunks = [], levels = [], buf = new Uint8Array(an.fftSize);
  const started = performance.now();
  mr.ondataavailable = e => e.data.size && chunks.push(e.data);
  mr.start(200);
  const timer = setInterval(() => {
    an.getByteTimeDomainData(buf);
    let sum = 0; for (const v of buf) sum += (v - 128) ** 2;
    levels.push(Math.min(1, Math.sqrt(sum / buf.length) / 40));
    onTick?.((performance.now() - started) / 1000, levels);
  }, 60);
  rec = { mr, stream, ac, timer, chunks, levels, started, mime: mr.mimeType || mime || 'audio/webm' };
}
export const recording = () => !!rec;
export function stopRecording(cancel) {
  if (!rec) return Promise.resolve(null);
  const r = rec; rec = null;
  clearInterval(r.timer);
  return new Promise(resolve => {
    r.mr.onstop = () => {
      r.stream.getTracks().forEach(t => t.stop());
      r.ac.close();
      if (cancel) return resolve(null);
      const dur = (performance.now() - r.started) / 1000;
      resolve({ blob: new Blob(r.chunks, { type: r.mime.split(';')[0] }), duration: dur, wave: waveform(r.levels, 48), type: r.mime.split(';')[0] });
    };
    r.mr.stop();
  });
}
function waveform(levels, n) {
  if (!levels.length) return Array(n).fill(2);
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = Math.floor(i * levels.length / n), b = Math.max(a + 1, Math.floor((i + 1) * levels.length / n));
    let m = 0; for (let j = a; j < b; j++) m = Math.max(m, levels[j] || 0);
    out.push(m);
  }
  const peak = Math.max(...out, 0.05);
  return out.map(v => Math.max(2, Math.round(v / peak * 31)));
}

// ---------- voice playback (one at a time) ----------
const audio = new Audio();
let playing = null; // { id, file, dur }
let speed = 1;
export const voiceState = id => (playing && playing.id === id ? { playing: !audio.paused, speed } : { playing: false, speed });
export async function toggleVoice(id, file, dur, at) {
  if (playing?.id === id) {
    if (at != null) { audio.currentTime = at * (audio.duration || dur); if (audio.paused) audio.play(); return; }
    audio.paused ? audio.play() : audio.pause();
    return;
  }
  audio.pause();
  playing = { id, file, dur };
  paint();
  try {
    audio.src = await blobUrl(file);
    if (playing?.id !== id) return;
    audio.playbackRate = speed;
    if (at != null) audio.currentTime = at * dur;
    await audio.play();
  } catch { toast('Не удалось воспроизвести', 'bad'); playing = null; paint(); }
}
export function cycleSpeed() {
  speed = speed === 1 ? 1.5 : speed === 1.5 ? 2 : 1;
  audio.playbackRate = speed;
  paint();
}
function paint() {
  for (const node of $$('[data-voice]')) {
    const me = playing && node.dataset.voice === String(playing.id);
    node.classList.toggle('playing', !!me && !audio.paused);
    const sp = node.querySelector('.v-speed'); if (sp) sp.textContent = speed + '×';
    const total = Number(node.dataset.dur);
    const t = me ? audio.currentTime : 0;
    const p = me && (audio.duration || total) ? t / (audio.duration && isFinite(audio.duration) ? audio.duration : total) : 0;
    node.style.setProperty('--p', p);
    const bars = node.querySelectorAll('.v-wave i');
    bars.forEach((b, i) => b.classList.toggle('on', (i + 0.5) / bars.length <= p));
    const label = node.querySelector('.v-time');
    if (label) label.textContent = me && t > 0 ? duration(t) : duration(total);
  }
}
audio.addEventListener('timeupdate', paint);
audio.addEventListener('play', paint);
audio.addEventListener('pause', paint);
audio.addEventListener('ended', () => { const id = playing?.id; playing = null; paint(); document.dispatchEvent(new CustomEvent('voice-ended', { detail: id })); });
export const repaintVoice = paint;

// ---------- sounds (synthesised, no assets) ----------
let ctx;
function tone(freqs, dur, gain = 0.08, type = 'sine') {
  try {
    ctx ||= new AudioContext();
    const t0 = ctx.currentTime;
    const g = ctx.createGain(); g.connect(ctx.destination);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    for (const f of freqs) { const o = ctx.createOscillator(); o.type = type; o.frequency.value = f; o.connect(g); o.start(t0); o.stop(t0 + dur); }
  } catch {}
}
export const sounds = {
  enabled: () => localStorage.getItem('orbita.sounds') !== 'off',
  message() { if (this.enabled()) { tone([880], 0.12, 0.05); setTimeout(() => tone([1320], 0.16, 0.04), 90); } },
  sent() { if (this.enabled()) tone([660], 0.08, 0.025, 'triangle'); },
  _loop: null,
  ring() { this.stop(); const play = () => { tone([523, 659], 0.35, 0.07); setTimeout(() => tone([587, 784], 0.45, 0.07), 380); }; play(); this._loop = setInterval(play, 2200); },
  dial() { this.stop(); const play = () => tone([425], 1.0, 0.04); play(); this._loop = setInterval(play, 3500); },
  stop() { clearInterval(this._loop); this._loop = null; },
  end() { tone([480], 0.18, 0.05); setTimeout(() => tone([360], 0.25, 0.05), 180); },
};
