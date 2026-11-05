'use strict';
/* ---------------- состояние матча ---------------- */
let state = 'menu', paused = false, gt = 0;
let roundNo = 1, scoreA = 0, scoreB = 0, freezeT = 0, roundT = 0, endT = 0, roundElapsed = 0;
const BUY_WINDOW = 15;

function spawnPoint(team) {
  // командный бой: точка возрождения подальше от живых врагов
  let best = spawns[team][0], bd = -1;
  for (const s of spawns[team]) {
    let md = 1e9;
    for (const e of units) if (e.alive && e.team !== team) md = Math.min(md, Math.hypot(e.pos.x - s.x, e.pos.z - s.z));
    md += Math.random() * 6;
    if (md > bd) { bd = md; best = s; }
  }
  return best;
}
function placeTeams() {
  for (const team of ['A', 'B']) {
    const sp = spawns[team].slice().sort(() => Math.random() - 0.5);
    units.filter(u => u.team === team).forEach((u, i) => {
      const s = sp[i % sp.length];
      u.pos.set(s.x + rand(-0.3, 0.3), 0, s.z + rand(-0.3, 0.3));
      u.yaw = team === 'A' ? -Math.PI / 2 : Math.PI / 2; u.pitch = 0;
    });
  }
}
function botBuy(b) {
  if (!mode.rounds) { b.primary = b.loadout; b.armor = 100; return; }
  if (!b.primary) {
    const m = b.money; let p = null;
    if (m >= 4750 + 650 && Math.random() < 0.18) p = 'sniper';
    else if (m >= 3100 + 650) p = Math.random() < 0.5 ? 'carbine' : 'rifle';
    else if (m >= 2700) p = 'rifle';
    else if (m >= 1250 && Math.random() < 0.65) p = Math.random() < 0.55 ? 'smg' : 'shotgun';
    if (p) { b.money -= WEAPONS[p].price; b.primary = p; }
  }
  if (b.armor < 100 && b.money >= ARMOR_PRICE) { b.money -= ARMOR_PRICE; b.armor = 100; }
}
function pickBotLoadout() { const r = Math.random(); return r < 0.14 ? 'sniper' : r < 0.3 ? 'smg' : r < 0.42 ? 'shotgun' : r < 0.7 ? 'rifle' : 'carbine'; }
function resetUnit(u, keep) {
  u.alive = true; u.hp = 100; u.vx = u.vz = u.vy = 0; u.onGround = true; u.protT = 0;
  u.reloading = 0; u.nextShot = 0; u.sprayN = 0; u.punch = u.punchY = 0; u.scoped = false; u.fireLatch = false;
  u.path = null; u.target = null; u.targetVisible = false; u.lastSeenT = 0; u.alertT = 0; u.burst = 0; u.deathT = 0; u.stuckT = 0; u.aimPitch = 0;
  if (!keep) { u.primary = null; u.armor = 0; }
  if (!mode.rounds && u.isPlayer) { u.primary = u.loadout; u.armor = 100; }
  if (!u.isPlayer) {
    if (!mode.rounds) u.loadout = pickBotLoadout();
    botBuy(u);
    const m = u.mesh;
    m.root.rotation.set(0, 0, 0); m.root.visible = true; m.blob.visible = true; m.chest.rotation.set(0, 0, 0);
    m.knees.forEach(k => k.rotation.x = 0);
    if (u.marker) u.marker.visible = true;
  }
  giveAmmo(u, 'pistol'); if (u.primary) giveAmmo(u, u.primary);
  u.cur = u.primary || 'pistol';
  if (!u.isPlayer) setBotWeapon(u);
}

function startMatch() {
  mode = MODES[settings.mode];
  buildUnits();
  roundNo = 1; scoreA = 0; scoreB = 0;
  for (const u of units) { u.kills = 0; u.deaths = 0; u.money = mode.money || 0; u.primary = null; u.armor = 0; u.alive = true; }
  if (mode.rounds) startRound();
  else {
    clearEffects(); $('#feed').innerHTML = '';
    for (const u of units) resetUnit(u, false);
    placeTeams();
    state = 'freeze'; freezeT = 3; roundT = mode.time; roundElapsed = 0;
    equip(player, player.cur, true);
    showMsg(mode.name, 'Побеждает команда, первой набравшая ' + mode.killLimit + ' убийств');
    $('#rnd').textContent = 'До ' + mode.killLimit;
  }
}
function startRound() {
  clearEffects(); $('#feed').innerHTML = '';
  for (const u of units) resetUnit(u, u.alive && roundNo > 1);
  placeTeams();
  state = 'freeze'; freezeT = mode.freeze; roundElapsed = 0; roundT = mode.roundTime;
  equip(player, player.cur, true);
  showMsg('Раунд ' + roundNo, 'Закупка и подготовка');
  $('#rnd').textContent = 'Раунд ' + roundNo;
  if (isTouch || roundNo === 1) openBuy(); else updateBuyBtn();
  bus.emit('round:start');
}
function endRound(winner, reason) {
  if (state !== 'live' && state !== 'freeze') return;
  state = 'roundEnd'; endT = 4;
  if (winner === 'A') scoreA++; else scoreB++;
  for (const u of units) u.money = Math.min(MONEY_CAP, u.money + (u.team === winner ? 3250 : 1900));
  showMsg(winner === 'A' ? 'Раунд за «Сталью»' : 'Раунд за «Ржавчиной»', reason, winner);
  beep(winner === player.team ? 660 : 220, 0.25, 0.1, 'triangle');
  closeBuy();
  bus.emit('round:end', winner);
}
function checkElimination() {
  if (state !== 'live' || !mode.rounds) return;
  const aAlive = units.some(u => u.team === 'A' && u.alive), bAlive = units.some(u => u.team === 'B' && u.alive);
  if (!aAlive) endRound('B', 'Команда «Сталь» уничтожена');
  else if (!bAlive) endRound('A', 'Команда «Ржавчина» уничтожена');
}
function afterRoundEnd() {
  if (scoreA >= mode.win || scoreB >= mode.win) return gameOver();
  roundNo++; startRound();
}
function gameOver() {
  state = 'over'; exitLock();
  const win = scoreA > scoreB, draw = scoreA === scoreB;
  $('#overRes').textContent = draw ? 'Ничья' : win ? 'Победа' : 'Поражение';
  $('#overRes').className = 'res ' + (win ? 'win' : 'lose');
  $('#overSub').textContent = mode.name + ' · ' + DIFF[settings.diff].name;
  $('#ovScore').textContent = scoreA + ':' + scoreB;
  $('#ovK').textContent = player.kills; $('#ovD').textContent = player.deaths;
  renderTables($('#ovTables'));
  setScreen('over');
}

/* ---------------- урон ---------------- */
function applyDamage(victim, attacker, wKey, part, dist) {
  if (!victim.alive || victim.protT > 0) return;
  const w = WEAPONS[wKey];
  const fall = w.falloff ? clamp(1.25 - dist / w.falloff, 0.15, 1) : (1 - Math.min(dist, 60) / 60 * 0.22);
  let dmg = w.dmg * (part === 'head' ? w.head : part === 'legs' ? 0.75 : 1) * fall;
  if (victim.armor > 0) { const ab = Math.min(victim.armor, dmg * 0.5); victim.armor -= ab; dmg -= ab; }
  victim.hp -= dmg;
  if (victim.isPlayer) hurtFx(attacker);
  else if (!victim.targetVisible) { victim.alertT = 3; victim.lastSeen.copy(attacker.pos); victim.lastSeenT = 4; victim.path = null; }
  const killed = victim.hp <= 0;
  if (attacker.isPlayer) { hitMarker(part === 'head', killed); sfxHit(part === 'head'); }
  if (killed) kill(victim, attacker, wKey, part === 'head');
}
function kill(victim, attacker, wKey, head) {
  victim.alive = false; victim.hp = 0; victim.deaths++;
  if (attacker.team !== victim.team) {
    attacker.kills++; attacker.money = Math.min(MONEY_CAP, attacker.money + 300);
    if (!mode.rounds && state === 'live') { if (attacker.team === 'A') scoreA++; else scoreB++; }
  }
  if (!mode.rounds) victim.respawnT = 3;
  if (victim.isPlayer) {
    if (mode.rounds) victim.primary = null;
    victim.scoped = false;
    showMsg('Ты выбыл', mode.rounds ? 'Наблюдение за командой' : 'Возрождение через 3 секунды');
  } else {
    victim.deathT = 0.001;
    if (victim.marker) victim.marker.visible = false;
  }
  feed(attacker, victim, wKey, head);
  bus.emit('kill', victim, attacker, wKey, head);
  checkElimination();
  if (!mode.rounds && (scoreA >= mode.killLimit || scoreB >= mode.killLimit)) setTimeout(() => { if (state === 'live') gameOver(); }, 900);
}
function respawn(u) {
  resetUnit(u, false);
  const s = spawnPoint(u.team);
  u.pos.set(s.x + rand(-0.4, 0.4), 0, s.z + rand(-0.4, 0.4));
  u.yaw = u.team === 'A' ? -Math.PI / 2 : Math.PI / 2; u.pitch = 0; u.protT = 2;
  if (u.isPlayer) { equip(player, player.cur, true); showMsg('', ''); }
}
