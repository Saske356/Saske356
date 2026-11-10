// 1:1 audio/video calls over WebRTC. Media is peer-to-peer and DTLS-SRTP encrypted; the server only relays signaling.
import { S, peerId } from './state.js';
import { rpc } from './net.js';
import { $, esc, icon, toast, duration, uid, hidden, systemNotify } from './util.js';
import { avatar } from './avatar.js';
import { sounds } from './media.js';
import { App } from './bus.js';

let call = null;
const box = () => $('#call');

async function getMedia(video) {
  return navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    video: video ? { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' } : false,
  });
}

function setupPc() {
  const pc = new RTCPeerConnection({ iceServers: S.config.iceServers });
  call.pc = pc;
  pc.onicecandidate = e => {
    if (!e.candidate || !call) return;
    const cand = e.candidate.toJSON();
    if (call.dir === 'out' && !call.answered) call.pendingIce.push(cand);
    else rpc('callIce', { callId: call.id, candidate: cand }).catch(() => {});
  };
  pc.ontrack = e => {
    if (!call) return;
    const stream = e.streams[0] || new MediaStream([e.track]);
    call.remote = stream;
    $('#remoteAudio').srcObject = stream;
    const rv = $('#rv'); if (rv) rv.srcObject = stream;
    if (e.track.kind === 'video') { call.remoteVideo = true; e.track.onunmute = paint; e.track.onmute = paint; paint(); }
  };
  pc.onconnectionstatechange = () => {
    if (!call) return;
    const st = pc.connectionState;
    if (st === 'connected' && call.state !== 'active') {
      call.state = 'active'; call.startedAt = Date.now(); sounds.stop();
      call.tick = setInterval(() => { const t = $('#callTime'); if (t) t.textContent = duration((Date.now() - call.startedAt) / 1000); }, 1000);
      paint();
    }
    if (st === 'failed') { toast('Не удалось соединиться. Возможно, сети нужен TURN-сервер', 'bad'); hangup(); }
  };
  return pc;
}

export async function startCall(chatId, video) {
  if (call) return toast('Вы уже разговариваете');
  const c = S.chats[chatId];
  if (!c || c.type !== 'direct') return;
  if (!window.RTCPeerConnection || !navigator.mediaDevices) return toast('Звонки не поддерживаются этим браузером', 'bad');
  call = { id: uid(), chatId, peer: S.users[peerId(c)], video, dir: 'out', state: 'calling', pendingIce: [], muted: false, camOff: false };
  build();
  try { call.local = await getMedia(video); }
  catch (e) { toast(e.name === 'NotAllowedError' ? 'Разрешите доступ к микрофону' + (video ? ' и камере' : '') : 'Микрофон или камера недоступны', 'bad'); return cleanup(); }
  attachLocal();
  const pc = setupPc();
  for (const t of call.local.getTracks()) pc.addTrack(t, call.local);
  await pc.setLocalDescription(await pc.createOffer());
  sounds.dial();
  try {
    const me = call;
    const r = await rpc('callInvite', { callId: call.id, chatId, video, offer: pc.localDescription.sdp });
    if (call !== me) return;
    if (r.status === 'offline') finish('Собеседник сейчас не в сети');
    else if (r.status === 'busy') finish('Собеседник уже разговаривает');
    else { call.state = 'ringing'; paint(); }
  } catch (e) { toast(e.message, 'bad'); cleanup(); }
}

function incoming(evt) {
  if (call) return; // server already answers "busy" for a second call
  const c = S.chats[evt.chatId];
  call = { id: evt.callId, chatId: evt.chatId, peer: S.users[evt.from] || (c && S.users[peerId(c)]), video: evt.video, dir: 'in', state: 'incoming', offer: evt.offer, pendingIce: [], muted: false, camOff: false };
  build();
  sounds.ring();
  if (hidden()) systemNotify(call.peer?.name || 'Звонок', evt.video ? 'Входящий видеозвонок' : 'Входящий звонок', 'call');
}

async function accept(withVideo) {
  if (!call || call.state !== 'incoming') return;
  sounds.stop();
  call.state = 'connecting'; call.video = call.video && withVideo; paint();
  try { call.local = await getMedia(call.video); }
  catch { toast('Нет доступа к микрофону', 'bad'); return hangup('declined'); }
  attachLocal();
  const pc = setupPc();
  await pc.setRemoteDescription({ type: 'offer', sdp: call.offer });
  for (const t of call.local.getTracks()) pc.addTrack(t, call.local);
  await pc.setLocalDescription(await pc.createAnswer());
  try { await rpc('callAnswer', { callId: call.id, answer: pc.localDescription.sdp }); }
  catch (e) { toast(e.message, 'bad'); cleanup(); }
}

export function hangup(reason) {
  if (!call) return;
  rpc('callHangup', { callId: call.id, reason }).catch(() => {});
  finish();
}
function finish(text) {
  if (!call) return;
  sounds.stop();
  if (call.state === 'active' || text) sounds.end();
  if (text) toast(text);
  cleanup();
}
function cleanup() {
  if (!call) return;
  clearInterval(call.tick);
  call.local?.getTracks().forEach(t => t.stop());
  call.screen?.getTracks().forEach(t => t.stop());
  try { call.pc?.close(); } catch {}
  $('#remoteAudio').srcObject = null;
  call = null;
  sounds.stop();
  box().className = 'call hidden';
  box().innerHTML = '';
  document.body.classList.remove('in-call');
}

export async function handleCallEvent(evt) {
  if (evt.type === 'call:incoming') return incoming(evt);
  if (!call || evt.callId !== call.id) return;
  if (evt.type === 'call:answer') {
    call.answered = true; call.state = 'connecting'; sounds.stop(); paint();
    await call.pc.setRemoteDescription({ type: 'answer', sdp: evt.answer });
    for (const c of call.pendingIce) rpc('callIce', { callId: call.id, candidate: c }).catch(() => {});
    call.pendingIce = [];
  } else if (evt.type === 'call:ice') {
    try { await call.pc?.addIceCandidate(evt.candidate); } catch {}
  } else if (evt.type === 'call:media') {
    call.peerCamOff = !evt.video; call.peerMuted = !evt.audio; paint();
  } else if (evt.type === 'call:taken') {
    cleanup();
  } else if (evt.type === 'call:end') {
    const text = { declined: 'Собеседник отклонил звонок', timeout: 'Никто не ответил', busy: 'Собеседник занят', offline: 'Собеседник не в сети', disconnected: 'Связь прервалась' }[evt.reason] || (call.state === 'active' ? 'Звонок завершён' : call.dir === 'in' ? 'Звонок отменён' : 'Звонок завершён');
    finish(text);
  }
}
export const inCall = () => !!call;

// ---------- controls ----------
function notifyMedia() {
  rpc('callMedia', { callId: call.id, video: !!call.video && !call.camOff, audio: !call.muted }).catch(() => {});
}
function toggleMute() {
  call.muted = !call.muted;
  call.local?.getAudioTracks().forEach(t => { t.enabled = !call.muted; });
  notifyMedia(); paint();
}
function toggleCam() {
  call.camOff = !call.camOff;
  call.local?.getVideoTracks().forEach(t => { t.enabled = !call.camOff; });
  notifyMedia(); paint();
}
async function toggleScreen() {
  const sender = call.pc?.getSenders().find(s => s.track?.kind === 'video');
  if (!sender) return;
  if (call.screen) {
    call.screen.getTracks().forEach(t => t.stop());
    call.screen = null;
    await sender.replaceTrack(call.local.getVideoTracks()[0]);
    attachLocal(); paint();
    return;
  }
  try {
    call.screen = await navigator.mediaDevices.getDisplayMedia({ video: true });
    const track = call.screen.getVideoTracks()[0];
    await sender.replaceTrack(track);
    track.onended = () => { if (call?.screen) toggleScreen(); };
    const lv = $('#lv'); if (lv) lv.srcObject = call.screen;
    paint();
  } catch {}
}

// ---------- UI ----------
function attachLocal() {
  const lv = $('#lv'); if (lv && call?.local) lv.srcObject = call.local;
}
function build() {
  const u = call.peer || { name: 'Собеседник', color: '#888' };
  box().className = 'call';
  document.body.classList.add('in-call');
  box().innerHTML = `
    <div class="call-bg" style="--c:${esc(u.color)}"></div>
    <video id="rv" class="rv" autoplay playsinline muted></video>
    <div class="call-top">
      <span class="call-lock">${icon('lock', 'xs')} Защищённый звонок</span>
      <button class="call-btn ghost sm" data-c="mini" title="Свернуть">${icon('minimize')}</button>
    </div>
    <div class="call-center">
      <div class="call-orbit"><i></i><i></i><i></i>${avatar({ ...u, online: false }, 'xxl')}</div>
      <h2>${esc(u.name)}</h2>
      <p class="call-status" id="callStatus"></p>
    </div>
    <video id="lv" class="lv" autoplay playsinline muted></video>
    <div class="call-ctrls" id="callCtrls"></div>
    <button class="call-pill" data-c="expand">${avatar({ ...u, online: false }, 'sm')}<span><b>${esc(u.name)}</b><small id="pillStatus"></small></span><span class="call-btn red sm" data-c="hangup">${icon('hangup')}</span></button>`;
  box().onclick = e => {
    const a = e.target.closest('[data-c]')?.dataset.c; if (!a) return;
    e.stopPropagation();
    if (a === 'accept') accept(false);
    if (a === 'acceptVideo') accept(true);
    if (a === 'decline') hangup('declined');
    if (a === 'hangup') hangup();
    if (a === 'mute') toggleMute();
    if (a === 'cam') toggleCam();
    if (a === 'screen') toggleScreen();
    if (a === 'mini') { box().classList.add('mini'); }
    if (a === 'expand') { box().classList.remove('mini'); }
    if (a === 'chat') { box().classList.add('mini'); App.openChat(call.chatId); }
  };
  paint();
}
function paint() {
  if (!call) return;
  const b = box();
  const showRemoteVideo = call.state === 'active' && call.remoteVideo && !call.peerCamOff;
  const showLocal = call.video && call.local && !call.camOff;
  b.classList.toggle('has-video', !!showRemoteVideo);
  b.classList.toggle('has-local', !!showLocal || !!call.screen);
  b.classList.toggle('ringing', ['calling', 'ringing', 'incoming'].includes(call.state));
  const status = {
    calling: 'Подключаемся…', ringing: 'Вызываем…', incoming: call.video ? 'Входящий видеозвонок' : 'Входящий звонок',
    connecting: 'Устанавливаем защищённое соединение…', active: '',
  }[call.state];
  const st = $('#callStatus');
  st.innerHTML = call.state === 'active'
    ? `<span id="callTime">${duration((Date.now() - call.startedAt) / 1000)}</span>${call.peerMuted ? ` · ${icon('micOff', 'xs')} микрофон выключен` : ''}${call.video && call.peerCamOff ? ' · камера выключена' : ''}`
    : esc(status);
  $('#pillStatus').textContent = call.state === 'active' ? 'идёт звонок' : status;
  const btn = (a, ic, label, cls = '') => `<button class="call-btn ${cls}" data-c="${a}" title="${label}">${icon(ic)}<span>${label}</span></button>`;
  $('#callCtrls').innerHTML = call.state === 'incoming'
    ? btn('decline', 'hangup', 'Отклонить', 'red') + (call.video ? btn('acceptVideo', 'video', 'С видео', 'green') : '') + btn('accept', 'phone', call.video ? 'Без видео' : 'Ответить', 'green')
    : btn('mute', call.muted ? 'micOff' : 'mic', call.muted ? 'Включить' : 'Микрофон', call.muted ? 'off' : '') +
      (call.video ? btn('cam', call.camOff ? 'camOff' : 'video', 'Камера', call.camOff ? 'off' : '') : '') +
      (call.video && navigator.mediaDevices.getDisplayMedia ? btn('screen', 'screen', call.screen ? 'Стоп' : 'Экран', call.screen ? 'on' : '') : '') +
      btn('chat', 'chats', 'Беседа') +
      btn('hangup', 'hangup', 'Завершить', 'red');
  const rv = $('#rv'); if (rv && call.remote && rv.srcObject !== call.remote) rv.srcObject = call.remote;
  const lv = $('#lv'); const src = call.screen || call.local; if (lv && src && lv.srcObject !== src) lv.srcObject = src;
}
