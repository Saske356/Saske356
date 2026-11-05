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
// Стороны в «Подрыве»: teamSide.A — сторона «Стали» ('atk' | 'def'). Меняются после половины матча.
const teamSide = { A: 'def', B: 'atk' };
const sideTeam = side => teamSide.A === side ? 'A' : 'B';
const lossStreak = { A: 0, B: 0 };
const TEAM_NAME = { A: 'Сталь', B: 'Ржавчина' };
// Журнал раундов для статистики и тестов: { n, winner, winSide, code: 'explode'|'defuse'|'elim'|'time', planted }
let roundLog = [];
// Награда за убийство в зависимости от оружия (пистолет-пулемёт и дробовик — больше, снайперская — меньше)
const KILL_REWARD = { smg: 600, shotgun: 900, sniper: 100, knife: 1500 };
const ECON = { win: 3250, winObj: 3500, loss: 1400, lossStep: 500, lossMax: 3400, plantTeam: 800, plantSelf: 300, defuseSelf: 300 };

function placeTeams() {
  for (const team of ['A', 'B']) {
    const list = units.filter(u => u.team === team);
    if (!list.length) continue;
    const side = list[0].side;
    const useZone = mode.bomb && side && spawnZones[side] && spawnZones[side].length;
    const zone = useZone ? spawnZones[side] : spawns[team];
    const other = useZone ? spawnZones[side === 'atk' ? 'def' : 'atk'] : spawns[team === 'A' ? 'B' : 'A'];
    let ox = 0, oz = 0; for (const s of other) { ox += s.x; oz += s.z; } ox /= other.length || 1; oz /= other.length || 1;
    const sp = zone.slice().sort(() => Math.random() - 0.5);
    list.forEach((u, i) => {
      const s = sp[i % sp.length];
      u.pos.set(s.x + rand(-0.3, 0.3), 0, s.z + rand(-0.3, 0.3));
      u.yaw = other.length ? yawTo(u.pos.x, u.pos.z, ox, oz) : (team === 'A' ? -Math.PI / 2 : Math.PI / 2); u.pitch = 0;
    });
  }
}
function botBuy(b) {
  if (!mode.rounds) { b.primary = b.loadout; b.armor = 100; return; }
  // командная экономика: если команда бедна — экономим на пистолетах (кроме пистолетного раунда)
  const mates = units.filter(u => u.team === b.team);
  const avg = mates.reduce((s, u) => s + u.money, 0) / Math.max(1, mates.length);
  const firstOfHalf = roundNo === 1 || (mode.half && roundNo === mode.half + 1);
  const eco = !firstOfHalf && !b.primary && avg < 2300 && b.money < 3400 && lossStreak[b.team] < 3;
  if (!b.primary && !eco) {
    const m = b.money; let p = null;
    if (m >= 4750 + 650 && Math.random() < 0.18) p = 'sniper';
    else if (m >= 3100 + 650) p = Math.random() < 0.5 ? 'carbine' : 'rifle';
    else if (m >= 2700) p = 'rifle';
    else if (m >= 1250 && Math.random() < 0.65) p = Math.random() < 0.55 ? 'smg' : 'shotgun';
    if (p) { b.money -= WEAPONS[p].price; b.primary = p; }
  }
  if (b.armor < 100 && b.money >= ARMOR_PRICE && (!eco || b.money > 1600)) { b.money -= ARMOR_PRICE; b.armor = 100; }
  if (mode.bomb && b.side === 'def' && !b.kit && b.money >= KIT_PRICE && (b.primary || Math.random() < 0.3) && Math.random() < 0.7) { b.money -= KIT_PRICE; b.kit = true; }
  // гранаты ботов — свой бюджет ИИ (бросок через throwGrenade, если «Бой» её предоставляет)
  b.aiNades = { smoke: 0, flash: 0, he: 0 };
  if (!eco) for (const [k, pr] of [['smoke', 300], ['flash', 200], ['he', 300]]) if (b.money >= pr + 200 && Math.random() < 0.75) { b.money -= pr; b.aiNades[k] = 1; }
}
function pickBotLoadout() { const r = Math.random(); return r < 0.14 ? 'sniper' : r < 0.3 ? 'smg' : r < 0.42 ? 'shotgun' : r < 0.7 ? 'rifle' : 'carbine'; }
function resetUnit(u, keep) {
  u.alive = true; u.hp = 100; u.vx = u.vz = u.vy = 0; u.onGround = true; u.protT = 0;
  u.reloading = 0; u.nextShot = 0; u.sprayN = 0; u.punch = u.punchY = 0; u.scoped = false; u.fireLatch = false;
  u.path = null; u.target = null; u.targetVisible = false; u.lastSeenT = 0; u.alertT = 0; u.burst = 0; u.deathT = 0; u.stuckT = 0; u.aimPitch = 0;
  u.hasCharge = false; u.planting = false; u.defusing = false; u.useT = 0; u.flashT = 0;
  if (!u.isPlayer) u.crouch = false;
  if (!keep) { u.primary = null; u.armor = 0; u.kit = false; }
  if (!mode.bomb || u.side !== 'def') u.kit = false;
  if (!mode.rounds && u.isPlayer) { u.primary = u.loadout; u.armor = 100; }
  if (!u.isPlayer) {
    if (!mode.rounds) u.loadout = pickBotLoadout();
    botBuy(u);
    const m = u.mesh;
    m.root.rotation.set(0, 0, 0); m.root.visible = true; m.blob.visible = true; m.chest.rotation.set(0, 0, 0);
    m.knees.forEach(k => k.rotation.x = 0);
    if (u.marker) u.marker.visible = true;
    if (typeof aiResetBot === 'function') aiResetBot(u);
  }
  giveAmmo(u, 'pistol'); if (u.primary) giveAmmo(u, u.primary);
  u.cur = u.primary || 'pistol';
  if (!u.isPlayer) setBotWeapon(u);
}
function applySides() {
  for (const u of units) u.side = mode.bomb ? teamSide[u.team] : null;
  if (player) player.side = mode.bomb ? teamSide[player.team] : null;
}

function startMatch() {
  mode = MODES[settings.mode];
  buildUnits();
  roundNo = 1; scoreA = 0; scoreB = 0; roundLog = []; lossStreak.A = lossStreak.B = 0;
  teamSide.A = mode.startSide || 'def'; teamSide.B = teamSide.A === 'atk' ? 'def' : 'atk';
  applySides();
  for (const u of units) { u.kills = 0; u.deaths = 0; u.money = mode.money || 0; u.primary = null; u.armor = 0; u.kit = false; u.alive = true; }
  if (typeof aiMatchStart === 'function') aiMatchStart();
  if (mode.rounds) startRound();
  else {
    clearEffects(); $('#feed').innerHTML = '';
    for (const u of units) resetUnit(u, false);
    placeTeams();
    state = 'freeze'; freezeT = 3; roundT = mode.time; roundElapsed = 0;
    equip(player, player.cur, true);
    showMsg(mode.name, 'Побеждает команда, первой набравшая ' + mode.killLimit + ' убийств');
    $('#rnd').textContent = 'До ' + mode.killLimit;
    if (typeof aiRoundStart === 'function') aiRoundStart();
  }
}
function startRound() {
  clearEffects(); $('#feed').innerHTML = '';
  applySides();
  for (const u of units) resetUnit(u, u.alive && roundNo > 1 && !u._sideSwapped);
  for (const u of units) u._sideSwapped = false;
  placeTeams();
  state = 'freeze'; freezeT = mode.freeze; roundElapsed = 0; roundT = mode.roundTime;
  equip(player, player.cur, true);
  if (mode.bomb) {
    if (typeof objRoundStart === 'function') objRoundStart();
    const atk = teamSide[player.team] === 'atk';
    showMsg('Раунд ' + roundNo + (mode.half && roundNo === mode.half + 1 ? ' · смена сторон' : ''),
      atk ? 'Атака: заложите заряд на точке А или Б' : 'Защита: не дайте заложить заряд');
  } else showMsg('Раунд ' + roundNo, 'Закупка и подготовка');
  $('#rnd').textContent = 'Раунд ' + roundNo + (mode.maxRounds ? ' / ' + mode.maxRounds : '');
  if (typeof aiRoundStart === 'function') aiRoundStart();
  if (isTouch || roundNo === 1) openBuy(); else updateBuyBtn();
  bus.emit('round:start');
}
// code: 'elim' | 'time' | 'explode' | 'defuse'. Без кода в «Подрыве» — это вышедшее время (вызов из main.js):
// тогда исход решает режим (взрыв заложенного заряда или победа защиты).
function endRound(winner, reason, code) {
  if (state !== 'live' && state !== 'freeze') return;
  if (mode.bomb && !code && typeof objTimeout === 'function') return objTimeout();
  state = 'roundEnd'; endT = 4;
  if (winner === 'A') scoreA++; else scoreB++;
  const loser = winner === 'A' ? 'B' : 'A';
  if (mode.bomb) {
    const planted = chargeState.plantedRound;
    lossStreak[loser]++; lossStreak[winner] = Math.max(0, lossStreak[winner] - 1);
    const lossPay = Math.min(ECON.lossMax, ECON.loss + ECON.lossStep * Math.max(0, lossStreak[loser] - 1));
    const winPay = code === 'explode' || code === 'defuse' ? ECON.winObj : ECON.win;
    for (const u of units) {
      let add = u.team === winner ? winPay : lossPay;
      if (u.team === loser && u.side === 'atk' && planted) add += ECON.plantTeam;
      if (u.team === loser && u.side === 'atk' && code === 'time' && u.alive) add = 0; // отсиделись до конца времени — без награды
      u.money = Math.min(MONEY_CAP, u.money + add);
    }
    roundLog.push({ n: roundNo, winner, winSide: teamSide[winner], code: code || 'time', planted });
  } else for (const u of units) u.money = Math.min(MONEY_CAP, u.money + (u.team === winner ? 3250 : 1900));
  for (const u of units) { u.planting = false; u.defusing = false; u.useT = 0; }
  showMsg(winner === 'A' ? 'Раунд за «Сталью»' : 'Раунд за «Ржавчиной»', reason, winner);
  beep(winner === player.team ? 660 : 220, 0.25, 0.1, 'triangle');
  closeBuy();
  bus.emit('round:end', winner);
}
function checkElimination() {
  if (state !== 'live' || !mode.rounds) return;
  const aAlive = units.some(u => u.team === 'A' && u.alive), bAlive = units.some(u => u.team === 'B' && u.alive);
  if (mode.bomb) {
    const atk = sideTeam('atk'), def = sideTeam('def');
    const atkAlive = atk === 'A' ? aAlive : bAlive, defAlive = def === 'A' ? aAlive : bAlive;
    if (!defAlive) endRound(atk, 'Защита «' + TEAM_NAME[def] + '» уничтожена', 'elim');
    else if (!atkAlive && chargeState.state !== 'planted') endRound(def, 'Атака «' + TEAM_NAME[atk] + '» уничтожена', 'elim');
    return;
  }
  if (!aAlive) endRound('B', 'Команда «Сталь» уничтожена', 'elim');
  else if (!bAlive) endRound('A', 'Команда «Ржавчина» уничтожена', 'elim');
}
function afterRoundEnd() {
  if (scoreA >= mode.win || scoreB >= mode.win || (mode.maxRounds && roundNo >= mode.maxRounds)) return gameOver();
  if (mode.bomb && mode.half && roundNo === mode.half) halfTime();
  roundNo++; startRound();
}
// смена сторон: деньги, оружие, броня и серия поражений сбрасываются
function halfTime() {
  teamSide.A = teamSide.A === 'atk' ? 'def' : 'atk'; teamSide.B = teamSide.A === 'atk' ? 'def' : 'atk';
  lossStreak.A = lossStreak.B = 0;
  for (const u of units) { u.money = mode.money || 800; u.primary = null; u.armor = 0; u.kit = false; u._sideSwapped = true; }
  applySides();
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
    attacker.kills++; attacker.money = Math.min(MONEY_CAP, attacker.money + (mode.rounds ? (KILL_REWARD[wKey] || 300) : 300));
    if (!mode.rounds && state === 'live') { if (attacker.team === 'A') scoreA++; else scoreB++; }
  }
  if (!mode.rounds) victim.respawnT = 3;
  victim.planting = false; victim.defusing = false; victim.useT = 0;
  if (!victim.isPlayer) victim.crouch = false;
  if (mode.bomb && typeof objOnDeath === 'function') objOnDeath(victim);
  if (typeof aiOnKill === 'function') aiOnKill(victim, attacker);
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
