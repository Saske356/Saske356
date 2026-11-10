'use strict';
// WebRTC call signaling for 1:1 calls. Media flows peer-to-peer (DTLS-SRTP), never through the server.

const RING_TIMEOUT = 45_000;

function createCalls({ toUser, send, isMember, memberIds, chatRow, insertMessage, sockets, fail }) {
  const calls = new Map();    // callId -> call
  const userCall = new Map(); // userId -> callId

  const validId = id => typeof id === 'string' && /^[a-zA-Z0-9-]{8,64}$/.test(id);
  function own(uid, callId) {
    const c = validId(callId) && calls.get(callId);
    if (!c || (c.caller !== uid && c.callee !== uid)) fail('Звонок уже завершён');
    return c;
  }
  const sdp = s => { if (typeof s !== 'string' || s.length > 20000) fail('Неверные данные звонка'); return s; };

  function end(call, byUid, reason = 'hangup') {
    if (!calls.has(call.id)) return;
    clearTimeout(call.timer);
    calls.delete(call.id);
    if (userCall.get(call.caller) === call.id) userCall.delete(call.caller);
    if (userCall.get(call.callee) === call.id) userCall.delete(call.callee);

    const evt = { type: 'call:end', callId: call.id, reason };
    if (call.callerWs && byUid !== call.caller) send(call.callerWs, evt);
    if (call.calleeWs) { if (byUid !== call.callee) send(call.calleeWs, evt); }
    else toUser(call.callee, evt);
    // Other devices of the user who hung up should also stop ringing / showing the call.
    if (byUid === call.callee) toUser(call.callee, evt, call.calleeWs);

    let status;
    if (call.answeredAt) status = 'ended';
    else if (reason === 'declined') status = 'declined';
    else if (reason === 'busy') status = 'busy';
    else status = 'missed';
    const duration = call.answeredAt ? Math.round((Date.now() - call.answeredAt) / 1000) : 0;
    if (chatRow(call.chatId)) {
      insertMessage(call.chatId, call.caller, 'call', { meta: { call: { video: call.video, status, duration } } });
    }
  }

  const handlers = {
    callInvite(uid, { callId, chatId, video, offer }, ws) {
      if (!validId(callId) || calls.has(callId)) fail('Неверный звонок');
      const chat = Number.isInteger(chatId) && chatRow(chatId);
      if (!chat || chat.type !== 'direct' || !isMember(chatId, uid)) fail('Звонить можно только в личной беседе');
      if (userCall.has(uid)) fail('Вы уже в звонке');
      const callee = memberIds(chatId).find(m => m !== uid);
      const call = { id: callId, chatId, caller: uid, callee, video: !!video, callerWs: ws, calleeWs: null, createdAt: Date.now(), answeredAt: 0, offer: sdp(offer) };
      calls.set(callId, call);
      userCall.set(uid, callId);
      if (!sockets.has(callee)) { end(call, uid, 'offline'); return { status: 'offline' }; }
      if (userCall.has(callee)) { end(call, callee, 'busy'); return { status: 'busy' }; }
      userCall.set(callee, callId);
      toUser(callee, { type: 'call:incoming', callId, chatId, from: uid, video: !!video, offer: call.offer });
      call.timer = setTimeout(() => end(call, null, 'timeout'), RING_TIMEOUT);
      return { status: 'ringing' };
    },

    callAnswer(uid, { callId, answer }, ws) {
      const call = own(uid, callId);
      if (call.callee !== uid || call.answeredAt) fail('Звонок уже принят');
      clearTimeout(call.timer);
      call.answeredAt = Date.now();
      call.calleeWs = ws;
      send(call.callerWs, { type: 'call:answer', callId, answer: sdp(answer) });
      toUser(uid, { type: 'call:taken', callId }, ws);
      return true;
    },

    callIce(uid, { callId, candidate }, ws) {
      const call = own(uid, callId);
      if (typeof candidate !== 'object' || JSON.stringify(candidate).length > 4000) return true;
      const target = uid === call.caller ? call.calleeWs : call.callerWs;
      if (target && (uid === call.caller ? ws === call.callerWs : ws === call.calleeWs)) send(target, { type: 'call:ice', callId, candidate });
      return true;
    },

    callMedia(uid, { callId, video, audio }) {
      const call = own(uid, callId);
      const target = uid === call.caller ? call.calleeWs : call.callerWs;
      if (target) send(target, { type: 'call:media', callId, video: !!video, audio: !!audio });
      return true;
    },

    callHangup(uid, { callId, reason }) {
      const c = validId(callId) && calls.get(callId);
      if (!c || (c.caller !== uid && c.callee !== uid)) return true;
      end(c, uid, reason === 'declined' && uid === c.callee && !c.answeredAt ? 'declined' : 'hangup');
      return true;
    },
  };

  return {
    handlers,
    socketClosed(ws) {
      for (const c of [...calls.values()]) {
        if (c.callerWs === ws) end(c, c.caller, 'disconnected');
        else if (c.calleeWs === ws) end(c, c.callee, 'disconnected');
      }
    },
    // Calls still ringing for this user (e.g. they opened a new tab while the phone rings).
    activeFor(uid) {
      return [...calls.values()].filter(c => c.callee === uid && !c.answeredAt).map(c => ({ callId: c.id, chatId: c.chatId, from: c.caller, video: c.video, offer: c.offer }));
    },
  };
}

module.exports = { createCalls };
