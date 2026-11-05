'use strict';
/* ---------------- бойцы ---------------- */
const NAMES = { A: ['Кедр', 'Сыч', 'Пила', 'Лис'], B: ['Гром', 'Шакал', 'Буран', 'Ворон', 'Клык'] };
let units = [], bots = [];
let mode = MODES[settings.mode];
const pipsA = $('#pipsA'), pipsB = $('#pipsB');
function makeUnit(team, name, isPlayer) {
  const u = {
    team, name, isPlayer, pos: new THREE.Vector3(), vx: 0, vz: 0, vy: 0, onGround: true, yaw: 0, pitch: 0,
    hp: 100, armor: 0, crouch: false, flashT: 0, alive: true, primary: null, cur: 'pistol', ammo: {}, reloading: 0, nextShot: 0, loadout: 'rifle',
    money: 800, kills: 0, deaths: 0, sprayN: 0, punch: 0, punchY: 0, scoped: false, fireLatch: false, spottedT: 0, protT: 0, respawnT: 0,
    path: null, pathI: 0, goalT: 0, target: null, targetVisible: false, reactT: 0, thinkT: 0, strafeT: 0, strafeDir: 0, aimPitch: 0,
    lastSeen: new THREE.Vector3(), lastSeenT: 0, alertT: 0, burst: 0, walkPhase: Math.random() * 6, stuckT: 0, lastPos: new THREE.Vector3(), deathT: 0,
  };
  if (!isPlayer) {
    u.mesh = makeBody(team);
    u.mesh.hit.forEach(p => p.userData.unit = u);
    if (team === 'A') {
      const m = new THREE.Sprite(new THREE.SpriteMaterial({ color: STYLE.A.acc, depthTest: false, transparent: true, opacity: 0.85 }));
      m.scale.set(0.12, 0.12, 0.12); m.position.y = 2.2; m.renderOrder = 5; u.mesh.root.add(m); u.marker = m;
    }
  }
  units.push(u); return u;
}
function disposeUnits() {
  for (const u of units) if (u.mesh) { scene.remove(u.mesh.root); scene.remove(u.mesh.blob); u.mesh.hit.forEach(h => h.geometry.dispose()); }
  units = []; bots = [];
}
let player;
function buildUnits() {
  disposeUnits();
  player = makeUnit('A', 'Ты', true);
  for (let i = 0; i < mode.size - 1; i++) makeUnit('A', NAMES.A[i], false);
  for (let i = 0; i < mode.size; i++) makeUnit('B', NAMES.B[i], false);
  bots = units.filter(u => !u.isPlayer);
  pipsA.innerHTML = '<i></i>'.repeat(mode.size);
  pipsB.innerHTML = '<i></i>'.repeat(mode.size);
}
function giveAmmo(u, key) { const w = WEAPONS[key]; u.ammo[key] = { mag: w.mag, res: w.res }; }
function weaponOf(u) { return WEAPONS[u.cur]; }
