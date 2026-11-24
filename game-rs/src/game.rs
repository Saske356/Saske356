//! Состояние и симуляция забега (перенос systems из веб-версии один к одному).
#![allow(clippy::too_many_arguments)]
use crate::data::{self, c, cfg, u, K, PI, TAU};
use crate::i18n::{self, t, tf};
use crate::save::Save;

// ---------- случайные числа (xorshift) ----------
pub struct Rng(u64);
impl Rng {
    pub fn new(seed: u64) -> Self { Rng(seed | 1) }
    #[inline] pub fn next(&mut self) -> f32 { self.0 ^= self.0 << 13; self.0 ^= self.0 >> 7; self.0 ^= self.0 << 17; ((self.0 >> 40) as f32) / ((1u64 << 24) as f32) }
    #[inline] pub fn range(&mut self, a: f32, b: f32) -> f32 { a + (b - a) * self.next() }
    #[inline] pub fn int(&mut self, a: i32, b: i32) -> i32 { a + (self.next() * (b - a + 1) as f32) as i32 }
}
#[inline] pub fn ang_diff(a: f32, b: f32) -> f32 { let mut d = (b - a) % TAU; if d > PI { d -= TAU; } if d < -PI { d += TAU; } d }
#[inline] pub fn clamp(v: f32, a: f32, b: f32) -> f32 { v.max(a).min(b) }
#[inline] pub fn hypot(x: f32, y: f32) -> f32 { (x * x + y * y).sqrt() }

// ---------- звуки и события для остальных подсистем ----------
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Sfx { Shoot, Hit, Kill(u32), Hurt, Dash, Nova, Flare, Pick(f32), Pearl, Level, Boom(bool), Warn, Shot2, Graze, Clink, Ach, Beat, PickCard, Click }
#[derive(Clone, Debug)]
pub struct Banner { pub t: f32, pub dur: f32, pub text: String, pub sub: String, pub col: u32 }
#[derive(Clone, Debug)]
pub struct Toast { pub title: String, pub sub: String, pub t: f32 }

// ---------- сущности ----------
/// Массив фиксированной длины с Default (стандартный есть только до 32 элементов)
#[derive(Clone, Copy)] pub struct Arr<T: Copy + Default, const N: usize>(pub [T; N]);
impl<T: Copy + Default, const N: usize> Default for Arr<T, N> { fn default() -> Self { Arr([T::default(); N]) } }
impl<T: Copy + Default, const N: usize> std::ops::Index<usize> for Arr<T, N> { type Output = T; fn index(&self, i: usize) -> &T { &self.0[i] } }
impl<T: Copy + Default, const N: usize> std::ops::IndexMut<usize> for Arr<T, N> { fn index_mut(&mut self, i: usize) -> &mut T { &mut self.0[i] } }
#[derive(Clone, Default)]
pub struct Enemy {
    pub kind: K, pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub r: f32, pub hp: f32, pub max_hp: f32, pub spd: f32, pub dmg: f32, pub xp: f32, pub score: f32,
    pub col: u8, pub ang: f32, pub t: f32, pub st: f32, pub state: i32, pub flash: f32, pub slow: f32, pub freeze: f32, pub elite: bool, pub dead: bool, pub uid: u32,
    pub orb_cd: f32, pub dash_hit: u32, pub chain_mark: u32, pub scale: f32, pub next: i32, pub hist: Arr<f32, 64>, pub hh: usize, pub hn: usize, pub phase: f32,
    pub p1: f32, pub p2: f32, pub p3: f32, pub spawn_t: f32, pub lvl: i32, pub tx: f32, pub ty: f32, pub sh: f32, pub burn: f32, pub burn_t: f32, pub burn_acc: f32,
    pub hx: f32, pub hy: f32, pub th_t: f32, pub txt: i32, pub a_t: f32 /* часы анимации */, pub tier: u8, pub tt: f32, pub tt2: f32, pub inv_t: f32,
    pub aff: u8 /* свойство элиты */, pub ash: f32 /* панцирь */, pub aff_t: f32,
}
#[derive(Clone, Default)] pub struct PBul { pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub dmg: f32, pub pierce: i32, pub bounce: i32, pub life: f32, pub crit: bool, pub last_uid: u32, pub hom_t: f32, pub tgt: i32, pub tgt_uid: u32, pub split: bool, pub r: f32, pub boom: f32, pub form: u8 /* форма атаки искры */, pub t: f32 }
#[derive(Clone, Default)] pub struct EBul { pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub r: f32, pub dmg: f32, pub life: f32, pub col: u8, pub spin: f32, pub acc: f32, pub grazed: bool }
#[derive(Clone, Default)] pub struct Part { pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub life: f32, pub max: f32, pub size: f32, pub col: u8, pub drag: f32 }
#[derive(Clone, Default)] pub struct Ring { pub x: f32, pub y: f32, pub r0: f32, pub r1: f32, pub life: f32, pub max: f32, pub col: u8, pub w: f32 }
#[derive(Clone, Default)] pub struct Text { pub x: f32, pub y: f32, pub vy: f32, pub life: f32, pub max: f32, pub s: String, pub crit: bool, pub col: u32, pub big: bool, pub owner: u32, pub val: f32 }
#[derive(Clone, Default)] pub struct Bolt { pub pts: [f32; 16], pub life: f32, pub col: u8 }
#[derive(Clone, Default)] pub struct Pick { pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub kind: u8, pub val: f32, pub mag: bool, pub t: f32 }
#[derive(Clone, Default)] pub struct Mine { pub x: f32, pub y: f32, pub t: f32, pub r: f32, pub dmg: f32, pub inst: bool, pub freeze: bool }
#[derive(Clone, Default)] pub struct Ghost { pub on: bool, pub kind: K, pub bare: bool, pub tier: u8, pub x: f32, pub y: f32, pub a: f32, pub s: f32, pub t: f32 }

/// Пул с удалением перестановкой (как Pool в веб-версии)
pub struct Pool<T: Clone + Default> { pub items: Vec<T>, pub n: usize }
impl<T: Clone + Default> Pool<T> {
    pub fn new(cap: usize) -> Self { Pool { items: vec![T::default(); cap], n: 0 } }
    pub fn spawn(&mut self) -> Option<usize> { if self.n >= self.items.len() { return None; } let i = self.n; self.n += 1; self.items[i] = T::default(); Some(i) }
    pub fn kill(&mut self, i: usize) { if i >= self.n { return; } self.n -= 1; self.items.swap(i, self.n); }
    pub fn clear(&mut self) { self.n = 0; }
    pub fn cap(&self) -> usize { self.items.len() }
    pub fn iter(&self) -> impl Iterator<Item = &T> { self.items[..self.n].iter() }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum State { Intro, Title, Play, Pause, LevelUp, Revive, Over, Ending, Menu }

#[derive(Default, Clone)]
pub struct Player {
    pub x: f32, pub y: f32, pub vx: f32, pub vy: f32, pub r: f32, pub hp: f32, pub max_hp: f32, pub ang: f32, pub inv: f32, pub dash_t: f32, pub dash_cd: f32,
    pub fire_t: f32, pub flare: f32, pub level: u32, pub xp: f32, pub xp_next: f32, pub up: Arr<u8, { u::COUNT }>, pub nova_t: f32, pub mine_t: f32, pub trail_t: f32,
    pub skin: usize, pub pal: u8, pub dead: bool, pub shield: i32, pub shield_t: f32, pub beat_t: f32, pub hb: f32, pub shot_n: u32,
    pub harp_t: f32, pub beam_t: f32, pub aura_t: f32, pub tw_t: f32, pub tw_x: f32, pub tw_y: f32, pub vort_t: f32, pub static_c: u32,
    pub beam_tg: i32, pub beam_tg2: i32, pub ink_t: f32, pub ink_x: f32, pub ink_y: f32, pub ink_d: f32, pub ink_q: bool, pub a_t: f32,
    pub salvo_n: u32, pub seek_t: f32, pub vac_t: f32, pub thun_t: f32, pub was_dash: bool, pub mark_uid: u32, pub mark_t: f32,
    pub form: u8 /* индекс искры: своя форма снарядов */,
}
#[derive(Default, Clone)]
pub struct Stats {
    pub dmg: f32, pub rate: f32, pub multi: u32, pub pierce: i32, pub bounce: i32, pub crit: f32, pub crit_mul: f32, pub chain_ch: f32, pub chain_n: u32,
    pub orb_n: u32, pub orb_dmg: f32, pub nova_lv: u32, pub nova_cd: f32, pub nova_r: f32, pub mine_lv: u32, pub mine_cd: f32, pub frost: u32, pub homing: u32,
    pub speed: f32, pub magnet: f32, pub armor_pct: f32, pub armor: f32, pub regen: f32, pub dash_cd: f32, pub dash_dmg: f32, pub flare_mul: f32, pub burn: f32,
    pub wildfire: bool, pub siphon_ch: f32, pub leech: bool, pub echo_ch: f32, pub barrier_max: i32, pub barrier_cd: f32, pub aegis: bool, pub over: u32,
    pub harpoon_lv: u32, pub harpoon_cd: f32, pub harpoon_dmg: f32, pub beam_lv: u32, pub beam_dps: f32, pub beam_r: f32, pub aura_lv: u32, pub aura_r: f32, pub aura_dps: f32,
    pub twin_lv: u32, pub twin_cd: f32, pub twin_dmg: f32, pub static_lv: u32, pub static_n: u32, pub static_k: u32, pub rage: f32, pub ink_lv: u32, pub vortex_lv: u32,
    pub thorns: f32, pub xp_mul: f32, pub bspd: f32, pub range: f32,
}
#[derive(Clone, Copy, Default)] pub struct Chal { pub need: u32, pub t: f32, pub got: u32 }
#[derive(Clone, Copy, Default)] pub struct Decor { pub k: usize /* индекс в DECOR_KEYS */, pub x: f32, pub y: f32, pub s: f32, pub fr: f32, pub r: f32, pub sw: f32, pub p: f32, pub a: f32, pub lt: f32 }
pub const DECOR_KEYS: [&str; 12] = ["d_kelp", "d_anemone", "d_coral", "d_coral2", "d_rock", "d_shell", "d_vent", "d_pillar", "d_ribs", "d_skull", "d_ice", "d_shroom"];
/// Разряды и лучи Королевы
#[derive(Clone, Copy, Default)] pub struct Qz { pub n: usize, pub t: f32, pub left: i32, pub xs: [f32; 12], pub ys: [f32; 12], pub rn: usize, pub ra: f32, pub rt: f32 }
pub const QZ_R: f32 = 68.0; pub const RAY_SPD: f32 = 700.0; pub const RAY_T: f32 = 0.55; pub const KING_SPD: f32 = 640.0; pub const KING_T: f32 = 0.6; pub const KING_SLAM: f32 = 150.0;
#[derive(Clone, Copy, PartialEq)] pub enum RunMode { Normal, Daily }

pub struct Game {
    pub s: Save, pub rng: Rng,
    pub state: State, pub t: f32, pub run_t: f32, pub zone: u32, pub zone_t: f32, pub score: f64, pub combo: u32, pub combo_t: f32, pub max_combo: u32, pub mult: f32,
    pub kills: u32, pub run_pearls: u32, pub boss: i32 /* uid босса или -1 */, pub boss_clear_t: f32, pub bosses_killed: u32, pub shake: f32, pub hit_stop: f32, pub flash: f32, pub hurt_flash: f32,
    pub banner: Banner, pub level_pending: u32, pub level_delay: f32, pub dying: f32, pub no_hit: bool, pub synergies: u32, pub rerolls: u32, pub ad_rerolls: u32, pub revived: bool,
    pub cam_x: f32, pub cam_y: f32, pub uid: u32, pub spawn_acc: f32, pub pack_t: f32, pub dmg_scale: f32, pub hp_scale: f32, pub orb_a: f32, pub chain_id: u32, pub dash_id: u32,
    pub pull_t: f32, pub pull_x: f32, pub pull_y: f32, pub combo_milestone: u32, pub victory: bool, pub endless: bool, pub ending_t: f32, pub ad_revived: bool, pub ad_doubled: bool,
    pub last_earned: u32, pub ev_t: f32, pub chal: Option<Chal>, pub last_ev: u8, pub chests: u32, pub lv_t: f32, pub hard: bool, pub daily: bool, pub muts: [bool; 8], pub crystals: u32, pub crystals_last: u32,
    pub start_best: u32, pub rec_shown: bool, pub god: bool, pub quality: u8, pub max_part: usize,
    pub p: Player, pub st: Stats,
    pub en: Pool<Enemy>, pub pb: Pool<PBul>, pub eb: Pool<EBul>, pub parts: Pool<Part>, pub rings: Pool<Ring>, pub texts: Pool<Text>, pub bolts: Pool<Bolt>, pub picks: Pool<Pick>, pub mines: Pool<Mine>,
    pub ghosts: Vec<Ghost>, pub ghost_i: usize, pub trail: [f32; 24], pub trail_head: usize, pub orb: [f32; 20], pub tent: [f32; 6 * 11 * 2],
    pub grid_head: Vec<i32>, pub grid_cols: usize, pub qa: Vec<usize>, pub qb: Vec<usize>,
    pub decor: Vec<Decor>, pub decor_zone: usize, pub floor: Vec<(f32, f32, f32, u8, f32)>, pub qz: Qz,
    // ввод
    pub jx: f32, pub jy: f32, pub dash_q: bool, pub flare_q: bool,
    // события для звука, интерфейса и платформы
    pub sfx: Vec<Sfx>, pub toasts: Vec<Toast>, pub vib: Vec<u32>, pub want_levelup: bool, pub want_over: bool, pub want_ending: bool, pub dirty: bool, pub run_mode: RunMode,
    pub vw: f32, pub vh: f32, pub static_q: u32, pub tut: Tut, pub touch: bool,
    // реликвии
    pub relics: Vec<u8>, pub relic_pending: u32, pub want_relic: bool, pub rel_lives: u32, pub rel_kills: u32, pub rel_blood: f32, pub rel_blood_t: f32, pub rel_ward_t: f32, pub rel_storm_t: f32,
}
#[derive(Default, Clone, Copy)] pub struct Tut { pub on: bool, pub step: usize, pub v: f32, pub base: u32, pub ok: f32, pub t: f32, pub fin: f32 }
pub const TUT_NEED: [f32; 5] = [300., 3., 6., 1., 1.];

/// Опыт до следующего уровня: после 15-го уровни заметно дороже, чтобы к глубине не набиралось 70 уровней
pub fn xp_need(l: u32) -> f32 { let l = l as f32; let late = (l - 25.).max(0.); (6.0 + l * 4.0 + l * l * 0.55 + late * late * 0.5).floor() }

impl Game {
    pub fn new(s: Save) -> Game {
        let cols = ((cfg::ARENA_R * 2.0 / cfg::CELL).ceil() as usize) + 2;
        let mut g = Game {
            s, rng: Rng::new(0x9e3779b97f4a7c15 ^ (macroquad::miniquad::date::now() * 1000.0) as u64),
            state: State::Intro, t: 0., run_t: 0., zone: 1, zone_t: 0., score: 0., combo: 0, combo_t: 0., max_combo: 0, mult: 1., kills: 0, run_pearls: 0,
            boss: -1, boss_clear_t: 0., bosses_killed: 0, shake: 0., hit_stop: 0., flash: 0., hurt_flash: 0., banner: Banner { t: 0., dur: 0., text: String::new(), sub: String::new(), col: 0xffffff },
            level_pending: 0, level_delay: 0., dying: 0., no_hit: true, synergies: 0, rerolls: 0, ad_rerolls: 0, revived: false, cam_x: 0., cam_y: 0., uid: 1,
            spawn_acc: 0., pack_t: 14., dmg_scale: 1., hp_scale: 1., orb_a: 0., chain_id: 1, dash_id: 1, pull_t: 0., pull_x: 0., pull_y: 0., combo_milestone: 0,
            victory: false, endless: false, ending_t: 0., ad_revived: false, ad_doubled: false, last_earned: 0, ev_t: 20., chal: None, last_ev: 9, chests: 0, lv_t: -99.,
            hard: false, daily: false, muts: [false; 8], crystals: 0, crystals_last: 0, start_best: 0, rec_shown: false, god: false, quality: 1, max_part: cfg::MAX_PART_HI,
            p: Player { r: 13., hp: 100., max_hp: 100., ang: -PI / 2., level: 1, xp_next: 10., beam_tg: -1, beam_tg2: -1, ..Default::default() }, st: Stats::default(),
            en: Pool::new(cfg::MAX_ENEMIES), pb: Pool::new(cfg::MAX_PBUL), eb: Pool::new(cfg::MAX_EBUL), parts: Pool::new(cfg::MAX_PART_HI), rings: Pool::new(cfg::MAX_RING),
            texts: Pool::new(cfg::MAX_TEXT), bolts: Pool::new(cfg::MAX_BOLT), picks: Pool::new(cfg::MAX_PICK), mines: Pool::new(cfg::MAX_MINE),
            ghosts: vec![Ghost::default(); 48], ghost_i: 0, trail: [0.; 24], trail_head: 0, orb: [0.; 20], tent: [0.; 132],
            grid_head: vec![-1; cols * cols], grid_cols: cols, qa: Vec::with_capacity(320), qb: Vec::with_capacity(320),
            decor: vec![], decor_zone: 99, floor: vec![], qz: Qz::default(), jx: 0., jy: 0., dash_q: false, flare_q: false,
            sfx: vec![], toasts: vec![], vib: vec![], want_levelup: false, want_over: false, want_ending: false, dirty: false, run_mode: RunMode::Normal,
            vw: 200., vh: 400., static_q: 0, tut: Tut::default(), touch: true,
            relics: vec![], relic_pending: 0, want_relic: false, rel_lives: 0, rel_kills: 0, rel_blood: 0., rel_blood_t: 0., rel_ward_t: 0., rel_storm_t: 0.,
        };
        g.p.skin = data::SKINS.iter().position(|k| k.id == g.s.skin).unwrap_or(0); g.p.pal = data::SKINS[g.p.skin].pal;
        g.init_floor(); g.build_decor(0);
        g
    }
    #[inline] pub fn lv(&self, i: usize) -> u32 { self.p.up[i] as u32 }
    #[inline] pub fn tl(&self, id: &str) -> f32 { if self.s.tal(id) { 1.0 } else { 0.0 } }
    #[inline] pub fn mutf(&self, id: &str) -> bool { data::MUTS.iter().position(|m| *m == id).map(|i| self.muts[i]).unwrap_or(false) }
    pub fn boss_idx(&self) -> Option<usize> { if self.boss < 0 { return None; } (0..self.en.n).find(|&i| self.en.items[i].uid == self.boss as u32 && !self.en.items[i].dead) }
    pub fn snd(&mut self, s: Sfx) { self.sfx.push(s); }
    pub fn vibrate(&mut self, ms: u32) { if self.s.set.vibro { self.vib.push(ms); } }
    pub fn rand(&mut self) -> f32 { self.rng.next() }
    pub fn rr(&mut self, a: f32, b: f32) -> f32 { self.rng.range(a, b) }

    // ---------- характеристики ----------
    pub fn compute_stats(&mut self) {
        let chi = data::CHARS.iter().position(|x| x.id == self.s.ch).unwrap_or(0); let ch = &data::CHARS[chi]; self.p.form = chi as u8;
        let sh = |k: &str| self.s.shop_lv(k) as f32; let lv = |i: usize| self.p.up[i] as f32;
        let st = &mut self.st;
        st.dmg = 10. * (1. + 0.25 * lv(u::DMG)) * (1. + 0.03 * sh("dmg")) * if lv(u::HUNTER) > 0. { 1.4 } else { 1. } * ch.dmg;
        st.rate = 3.4 * (1. + 0.18 * lv(u::RATE)) * (1. + 0.02 * sh("rate")) * ch.rate;
        st.multi = 1 + lv(u::MULTI) as u32; st.pierce = (lv(u::PIERCE) + ch.pierce as f32) as i32; st.bounce = lv(u::BOUNCE) as i32 + if chi == 8 { 2 } else { 0 };
        st.crit = 0.05 + 0.1 * lv(u::CRIT) + 0.01 * sh("crit") + if chi == 9 { 0.1 } else { 0. }; st.crit_mul = if lv(u::CRIT) > 0. { 2.2 } else { 2. };
        st.chain_ch = if lv(u::CHAIN) > 0. { 0.14 + 0.08 * lv(u::CHAIN) } else { 0. }; st.chain_n = 1 + lv(u::CHAIN) as u32;
        st.orb_n = (lv(u::ORBIT) as u32 + ch.orb as u32).min(8); st.orb_dmg = st.dmg * 0.9;
        st.nova_lv = lv(u::NOVA) as u32; st.nova_cd = 4.4 - 0.5 * lv(u::NOVA); st.nova_r = (135. + 18. * lv(u::NOVA)) * if lv(u::SUPERNOVA) > 0. { 1.4 } else { 1. };
        st.mine_lv = lv(u::MINE) as u32; st.mine_cd = 3.2 - 0.45 * lv(u::MINE); st.frost = lv(u::FROST) as u32; st.homing = lv(u::HOMING) as u32;
        st.speed = 200. * (1. + 0.1 * lv(u::SPEED)) * (1. + 0.02 * sh("spd")) * ch.speed;
        st.magnet = 85. * (1. + 0.4 * lv(u::MAGNET)) * (1. + 0.08 * sh("mag"));
        st.armor_pct = 0.07 * lv(u::ARMOR) + 0.01 * sh("armor"); st.armor = ch.armor; st.regen = 0.5 * lv(u::REGEN) + 0.08 * sh("regen");
        st.dash_cd = (2.3 * (1. - 0.2 * lv(u::DASH)) * (1. - 0.03 * sh("dash")) * ch.dash_cd).max(1.0); st.dash_dmg = if lv(u::DASH) > 0. { st.dmg * 2.5 } else { 0. };
        st.flare_mul = 1. + 0.3 * lv(u::FLARE);
        st.burn = if lv(u::BURN) > 0. { st.dmg * (0.14 + 0.1 * lv(u::BURN)) * if lv(u::WILDFIRE) > 0. { 1.3 } else { 1. } } else { 0. };
        st.wildfire = lv(u::WILDFIRE) > 0.; st.siphon_ch = if lv(u::SIPHON) > 0. { 0.1 + 0.07 * lv(u::SIPHON) } else { 0. }; st.leech = lv(u::LEECH) > 0.;
        st.echo_ch = if lv(u::ECHO) > 0. { 0.12 + 0.1 * lv(u::ECHO) } else { 0. };
        st.barrier_max = if lv(u::BARRIER) > 0. { 1 + if lv(u::AEGIS) > 0. { 1 } else { 0 } } else { 0 }; st.barrier_cd = 9. - 1.4 * lv(u::BARRIER); st.aegis = lv(u::AEGIS) > 0.;
        st.over = if lv(u::OVERCHARGE) > 0. { 6 } else { 0 };
        st.harpoon_lv = lv(u::HARPOON) as u32; st.harpoon_cd = 3.4 - 0.6 * lv(u::HARPOON); st.harpoon_dmg = st.dmg * (5. + 3. * lv(u::HARPOON)) * if lv(u::SPEAR) > 0. { 1.3 } else { 1. };
        st.beam_lv = lv(u::BEAM) as u32; st.beam_dps = st.dmg * (1.1 + 0.7 * lv(u::BEAM)); st.beam_r = 300.;
        st.aura_lv = lv(u::AURA) as u32; st.aura_r = (95. + 15. * lv(u::AURA)) * if lv(u::MAELSTROM) > 0. { 1.4 } else { 1. }; st.aura_dps = st.dmg * (0.45 + 0.3 * lv(u::AURA));
        st.twin_lv = lv(u::TWIN) as u32; st.twin_cd = 0.9 - 0.12 * lv(u::TWIN); st.twin_dmg = st.dmg * (0.45 + 0.15 * lv(u::TWIN));
        st.static_lv = lv(u::STATIC) as u32; st.static_n = (14. - 3. * lv(u::STATIC)) as u32; st.static_k = ((2. + lv(u::STATIC)) * if lv(u::TEMPEST) > 0. { 2. } else { 1. }) as u32;
        st.rage = 0.12 * lv(u::RAGE); st.ink_lv = lv(u::INK) as u32; st.vortex_lv = lv(u::VORTEX) as u32;
        st.thorns = if lv(u::THORNS) > 0. { st.dmg * (2.5 + 1.5 * lv(u::THORNS)) } else { 0. };
        st.xp_mul = (1. + 0.03 * sh("xp")) * (1. + 0.1 * lv(u::GREED)); st.bspd = 640. * if lv(u::HUNTER) > 0. { 1.15 } else { 1. }; st.range = 540.;
        { let cl = self.p.up[u::CALIBER] as f32; self.st.dmg *= 1. + 0.12 * cl; self.st.rate *= 1. - 0.04 * cl; self.st.xp_mul *= 1. + 0.05 * self.p.up[u::FORTUNE] as f32; }
        let glass = self.mutf("glass");
        let st = &mut self.st;
        st.dmg *= (1. + 0.05 * if self.s.tal("t_dmg") { 1. } else { 0. }) * if glass { 1.5 } else { 1. };
        if chi == 7 && st.burn <= 0. { st.burn = st.dmg * 0.28; } // Уголёк — всё поджигает
        st.orb_dmg = st.dmg * 0.9;
        st.rate *= 1. + 0.06 * if self.s.tal("t_rate") { 1. } else { 0. }; st.crit += 0.05 * if self.s.tal("t_crit") { 1. } else { 0. };
        st.armor_pct += 0.05 * if self.s.tal("t_arm") { 1. } else { 0. }; st.regen += 0.3 * if self.s.tal("t_regen") { 1. } else { 0. };
        st.magnet *= 1. + 0.2 * if self.s.tal("t_mag") { 1. } else { 0. };
        st.xp_mul *= (1. + 0.08 * if self.s.tal("t_xp") { 1. } else { 0. }) * if self.muts[6] { 2. } else { 1. };
        if self.muts[5] { st.flare_mul *= 0.5; }
        let old = self.p.max_hp;
        self.p.max_hp = ((ch.hp + 6. * sh("hp") + 25. * lv(u::HP) + 15. * if self.s.tal("t_hp") { 1. } else { 0. }) * if glass { 0.5 } else { 1. }).round();
        if self.p.max_hp > old && self.state != State::Title { self.p.hp += self.p.max_hp - old; }
        self.p.hp = self.p.hp.min(self.p.max_hp);
        self.relic_stats();
    }

    // ---------- эффекты ----------
    pub fn part(&mut self, x: f32, y: f32, vx: f32, vy: f32, life: f32, size: f32, col: u8, drag: f32) {
        if self.parts.n >= self.max_part { return; }
        if let Some(i) = self.parts.spawn() { self.parts.items[i] = Part { x, y, vx, vy, life, max: life, size, col, drag }; }
    }
    pub fn burst(&mut self, x: f32, y: f32, n: u32, col: u8, spd: f32, size: f32, life: f32) {
        let n = if self.quality == 0 { (n as f32 * 0.45).ceil() as u32 } else { n };
        for _ in 0..n { let a = self.rand() * TAU; let s = spd * (0.25 + self.rand() * 0.85); let l = life * (0.6 + self.rand() * 0.6); let sz = size * (0.6 + self.rand() * 0.7);
            self.part(x, y, a.cos() * s, a.sin() * s, l, sz, col, 3.); }
    }
    pub fn ring(&mut self, x: f32, y: f32, r0: f32, r1: f32, life: f32, col: u8, w: f32) { if let Some(i) = self.rings.spawn() { self.rings.items[i] = Ring { x, y, r0, r1, life, max: life, col, w }; } }
    pub fn text(&mut self, x: f32, y: f32, s: String, col: u32, crit: bool, big: bool) -> usize {
        if self.texts.n >= self.texts.cap() { self.texts.kill(0); }
        let i = self.texts.spawn().unwrap(); let dx = self.rr(-6., 6.);
        self.texts.items[i] = Text { x: x + dx, y, vy: if big { -40. } else { -70. }, life: if big { 1.6 } else { 0.75 }, max: if big { 1.6 } else { 0.75 }, s, crit, col, big, owner: 0, val: 0. };
        i
    }
    pub fn bolt(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, col: u8) {
        let Some(i) = self.bolts.spawn() else { return };
        let (dx, dy) = (x1 - x0, y1 - y0); let (nx, ny) = (-dy, dx); let l = hypot(dx, dy).max(1.);
        let mut pts = [0f32; 16];
        for k in 0..8 { let tt = k as f32 / 7.; let j = if k == 0 || k == 7 { 0. } else { self.rr(-0.18, 0.18) * l.min(120.) / l };
            pts[k * 2] = x0 + dx * tt + nx * j; pts[k * 2 + 1] = y0 + dy * tt + ny * j; }
        self.bolts.items[i] = Bolt { pts, life: 0.18, col };
    }
    pub fn shake(&mut self, v: f32) { if self.s.set.shake { self.shake = self.shake.max(v); } }
    pub fn banner(&mut self, text: String, sub: String, col: u32, dur: f32) { self.banner = Banner { t: 0., dur, text, sub, col }; }
    pub fn toast(&mut self, title: String, sub: String) { self.toasts.push(Toast { title, sub, t: 0. }); }

    // ---------- сетка ----------
    #[inline] fn gc(&self, v: f32) -> usize { let c = ((v + cfg::ARENA_R) / cfg::CELL).floor() as i64; c.clamp(0, self.grid_cols as i64 - 1) as usize }
    pub fn grid_build(&mut self) {
        for h in self.grid_head.iter_mut() { *h = -1; }
        for i in 0..self.en.n { let (x, y, dead) = { let e = &self.en.items[i]; (e.x, e.y, e.dead) }; if dead { continue; }
            let k = self.gc(x) + self.gc(y) * self.grid_cols; self.en.items[i].next = self.grid_head[k]; self.grid_head[k] = i as i32; }
    }
    /// Индексы врагов в клетках, покрывающих круг. out — qa или qb
    pub fn grid_query(&self, x: f32, y: f32, rad: f32, out: &mut Vec<usize>) {
        out.clear(); let (x0, x1, y0, y1) = (self.gc(x - rad), self.gc(x + rad), self.gc(y - rad), self.gc(y + rad));
        for gy in y0..=y1 { for gx in x0..=x1 { let mut i = self.grid_head[gx + gy * self.grid_cols];
            while i != -1 && out.len() < 320 { out.push(i as usize); i = self.en.items[i as usize].next; } } }
    }
    pub fn qa(&mut self, x: f32, y: f32, rad: f32) -> Vec<usize> { let mut v = std::mem::take(&mut self.qa); self.grid_query(x, y, rad, &mut v); v }
    pub fn qb(&mut self, x: f32, y: f32, rad: f32) -> Vec<usize> { let mut v = std::mem::take(&mut self.qb); self.grid_query(x, y, rad, &mut v); v }
    pub fn qa_back(&mut self, v: Vec<usize>) { self.qa = v; }
    pub fn qb_back(&mut self, v: Vec<usize>) { self.qb = v; }

    // ---------- спавн ----------
    pub fn spawn_enemy(&mut self, kind: K, x: f32, y: f32, elite: bool) -> Option<usize> {
        let i = self.en.spawn()?;
        let d = kind.d(); let z = (self.zone - 1) as f32; let lt = (z - 6.).max(0.);
        let hp_mul = (1. + 0.26 * z + 0.03 * z * z + 0.045 * lt * lt) * if d.boss { self.hp_scale } else { 1. + 0.06 * self.lv(u::GREED) as f32 } * if self.hard { 1.3 } else { 1. };
        let uid = self.uid; self.uid += 1;
        let ang = (self.p.y - y).atan2(self.p.x - x); let t0 = self.rand() * 2.; let phase = self.rand() * TAU; let p3 = if self.rand() < 0.5 { 1. } else { -1. };
        let mut e = Enemy { kind, x, y, r: d.r, max_hp: if d.boss { d.hp * self.hp_scale * if self.hard { 1.3 } else { 1. } } else { d.hp * hp_mul },
            spd: d.spd * if d.boss { 1. } else { 1. + (z * 0.03).min(0.35) }, dmg: d.dmg * self.dmg_scale, xp: d.xp, score: d.score, col: d.col, ang, t: t0,
            uid, scale: 1., next: -1, phase, p3, spawn_t: 0.4, txt: -1, ..Default::default() };
        e.hp = e.max_hp;
        if elite { e.elite = true; e.max_hp *= 3.5; e.hp = e.max_hp; e.scale = 1.4; e.xp *= 4.; e.score *= 5.; e.dmg *= 1.3; }
        if kind == K::Crab { e.sh = e.max_hp * cfg::CRAB_SHIELD; }
        if !d.boss { if self.muts[0] { e.spd *= 1.3; } if self.muts[2] { e.max_hp *= 0.7; e.hp = e.max_hp; } if self.muts[6] { e.scale *= 1.25; e.r *= 1.2; e.max_hp *= 1.4; e.hp = e.max_hp; } }
        if !d.boss && self.relics.contains(&crate::content::R_DEAL) { e.max_hp *= 1.15; e.hp = e.max_hp; }
        self.en.items[i] = e; if elite { self.assign_affix(i); }
        if !self.s.seen.contains_key(kind.key()) { self.s.seen.insert(kind.key().into(), 1); self.dirty = true; }
        if kind == K::Crab && !self.s.crab_hint { self.s.crab_hint = true; self.dirty = true; self.banner(t("crabT"), t("crabS"), 0xff8a9a, 3.); }
        if matches!(kind, K::Ray | K::Lantern | K::Wisp | K::Spawner | K::Fry) { self.init_new_foe(i); }
        if !d.boss && !matches!(kind, K::Chest | K::Crystal) { let tr = self.roll_tier(); self.apply_tier(i, tr); }
        Some(i)
    }
    pub fn offscreen_point(&mut self) -> (f32, f32) {
        let (hw, hh) = (self.vw + 45., self.vh + 45.);
        for _ in 0..8 { let r = self.rand() * (hw + hh) * 2.; let (x, y);
            if r < hw * 2. { x = self.p.x - hw + r; y = self.p.y + if self.rand() < 0.5 { -hh } else { hh }; }
            else { y = self.p.y - hh + (r - hw * 2.); x = self.p.x + if self.rand() < 0.5 { -hw } else { hw }; }
            if x * x + y * y < (cfg::ARENA_R - 40.).powi(2) { return (x, y); } }
        let a = self.rand() * TAU; let rr = cfg::ARENA_R - 60.; (a.cos() * rr, a.sin() * rr)
    }
    pub fn count_kind(&self, k: K) -> usize { self.en.iter().filter(|e| !e.dead && e.kind == k).count() }
    pub fn pick_kind(&mut self) -> K {
        const PT: [K; 12] = [K::Drifter, K::Dart, K::Jelly, K::Urchin, K::Squid, K::Eel, K::Crab, K::Mender, K::Bomber, K::Ray, K::Spawner, K::Lantern];
        let z = self.zone as f32; let mut w = [0f32; 12];
        w[0] = 10.; w[1] = 2. + z * 0.8; w[2] = if z >= 2. { 2. + z * 0.4 } else { 0. }; w[3] = if z >= 3. { 2. } else { 0. };
        w[4] = if z >= 3. { 1.5 + z * 0.3 } else { 0. }; w[5] = if z >= 4. { 1.4 + z * 0.15 } else { 0. }; w[6] = if z >= 6. { 1.2 + z * 0.2 } else { 0. };
        w[7] = if z >= 4. { 0.9 + z * 0.12 } else { 0. }; w[8] = if z >= 5. { 1.2 + z * 0.18 } else { 0. };
        w[9] = if z >= 2. { 1.0 + z * 0.15 } else { 0. }; w[10] = if z >= 3. { 0.8 + z * 0.1 } else { 0. }; w[11] = if z >= 4. { 0.9 + z * 0.12 } else { 0. };
        if z >= 2. { if self.count_kind(K::Crab) >= cfg::CRAB_MAX { w[6] = 0.; } if self.count_kind(K::Ray) >= cfg::RAY_MAX { w[9] = 0.; }
            if self.count_kind(K::Spawner) >= cfg::SPAWNER_MAX { w[10] = 0.; } if self.count_kind(K::Lantern) >= cfg::LANTERN_MAX { w[11] = 0.; } }
        let tot: f32 = w.iter().sum(); let mut r = self.rand() * tot;
        for i in 0..12 { r -= w[i]; if r <= 0. { return PT[i]; } }
        K::Drifter
    }
    fn spawn_pack(&mut self) {
        let z = self.zone; let kind = self.rand();
        if kind < 0.4 { let n = (10 + z * 2).min(26); let rr = self.vw.max(self.vh) * 0.9;
            for i in 0..n { let a = i as f32 / n as f32 * TAU; let (x, y) = (self.p.x + a.cos() * rr, self.p.y + a.sin() * rr);
                if x * x + y * y < cfg::ARENA_R * cfg::ARENA_R { self.spawn_enemy(K::Drifter, x, y, false); } }
            self.banner(String::new(), t("pack"), 0x5fffb0, 1.5);
        } else if kind < 0.7 && z >= 2 { let a = self.rand() * TAU; let rr = hypot(self.vw, self.vh) + 30.; let n = (4 + z).min(10);
            for i in 0..n { let o = (i as f32 - n as f32 / 2.) * 34.; let x = self.p.x + a.cos() * rr - a.sin() * o; let y = self.p.y + a.sin() * rr + a.cos() * o;
                if x * x + y * y < cfg::ARENA_R * cfg::ARENA_R { self.spawn_enemy(K::Dart, x, y, false); } }
        } else { for _ in 0..3 { let (x, y) = self.offscreen_point(); self.spawn_enemy(if z >= 2 { K::Jelly } else { K::Drifter }, x, y, false); }
            if z >= 3 { let (x, y) = self.offscreen_point(); let k = self.pick_kind(); self.spawn_enemy(k, x, y, true); } }
    }
    fn update_director(&mut self, dt: f32) {
        if self.ending_t > 0. { self.ending_t -= dt; if self.ending_t <= 0. { self.want_ending = true; } return; }
        if self.boss >= 0 { if self.boss_idx().is_none() { self.boss = -1; } }
        else if self.boss_clear_t > 0. { self.boss_clear_t -= dt; if self.boss_clear_t <= 0. { self.next_zone(); } return; }
        else { self.zone_t += dt; if self.zone_t >= cfg::ZONE_TIME * if self.muts[7] { 0.5 } else { 1. } { self.next_zone(); } }
        let z = self.zone as f32;
        let mut rate = (2.3 + 0.55 * (z - 1.) + 0.35 * (z - 7.).max(0.)) * if self.hard { 1.2 } else { 1. } * if self.muts[2] { 1.5 } else { 1. } * (1. + self.zone_t / cfg::ZONE_TIME * 0.4);
        if self.boss >= 0 { rate *= 0.22; }
        let max_alive = (cfg::MAX_ENEMIES - 20).min(48 + self.zone as usize * 9);
        self.spawn_acc += rate * dt;
        while self.spawn_acc >= 1. { self.spawn_acc -= 1.; if self.en.n >= max_alive { continue; }
            let (x, y) = self.offscreen_point(); let k = self.pick_kind(); let el = z >= 3. && self.rand() < (0.03 + z * 0.004) * if self.muts[3] { 3. } else { 1. };
            self.spawn_enemy(k, x, y, el); }
        if self.boss < 0 { self.pack_t -= dt; if self.pack_t <= 0. { self.pack_t = self.rr(13., 18.); self.spawn_pack(); } }
        if self.boss < 0 && self.boss_clear_t <= 0. && self.chal.is_none() { self.ev_t -= dt; if self.ev_t <= 0. { self.ev_t = self.rr(26., 36.); self.start_run_event(); } }
        if let Some(mut ch) = self.chal { ch.t -= dt;
            if ch.got >= ch.need { let a = self.rand() * TAU; self.spawn_chest(self.p.x + a.cos() * 170., self.p.y + a.sin() * 170.); self.run_pearls += 5;
                self.banner(t("chalWin"), t("chalWinS"), 0x5fffb0, 2.2); self.snd(Sfx::Level); self.chal = None; }
            else if ch.t <= 0. { self.banner(t("chalFail"), String::new(), 0xff8a8a, 1.6); self.chal = None; } else { self.chal = Some(ch); } }
    }
    pub fn spawn_chest(&mut self, mut x: f32, mut y: f32) {
        let l = hypot(x, y); let m = cfg::ARENA_R - 90.; if l > m { x *= m / l; y *= m / l; }
        if let Some(i) = self.spawn_enemy(K::Chest, x, y, false) { let e = &mut self.en.items[i]; e.hx = x; e.hy = y; e.spawn_t = 0.3; self.ring(x, y, 10., 90., 0.5, c::GOLD, 4.); }
    }
    fn start_run_event(&mut self) {
        let kinds: Vec<u8> = (0..3).filter(|k| *k != self.last_ev).collect(); let k = kinds[(self.rand() * kinds.len() as f32) as usize % kinds.len()]; self.last_ev = k;
        if k == 0 { let a0 = self.rand() * TAU;
            for i in 0..8 { let a = a0 + i as f32 / 8. * TAU; let (mut x, mut y) = (self.p.x + a.cos() * 400., self.p.y + a.sin() * 400.); let l = hypot(x, y); let m = cfg::ARENA_R - 60.;
                if l > m { x *= m / l; y *= m / l; } if let Some(e) = self.spawn_enemy(K::Drifter, x, y, true) { self.en.items[e].spawn_t = 0.4; } }
            self.banner(t("goldB"), t("goldS"), 0xffd54f, 2.2); self.snd(Sfx::Pearl);
        } else if k == 1 { let a = self.rand() * TAU; self.spawn_chest(self.p.x + a.cos() * 280., self.p.y + a.sin() * 280.); self.banner(t("chestB"), t("chestS"), 0xffd54f, 2.2); }
        else { let need = 22 + self.zone * 3; self.chal = Some(Chal { need, t: 20., got: 0 }); self.banner(t("chalB"), tf("chalS", &[&need.to_string(), "20"]), 0x5fffb0, 2.4); self.snd(Sfx::Warn); }
    }
    pub fn next_zone(&mut self) {
        self.zone += 1; self.zone_t = 0.; self.quest_max("depth", self.zone * 100); self.build_decor((self.zone as usize - 1) % 15);
        { let z = (self.zone - 1) as f32; let late = (z - 6.).max(0.); self.dmg_scale = (1. + 0.1 * z + 0.006 * z * z + 0.02 * late * late) * if self.hard { 1.35 } else { 1. }; }
        let depth = self.zone * 100;
        if self.zone == 3 && self.no_hit { self.unlock("depth300"); }
        if self.zone >= 5 { self.unlock("depth500"); } if self.zone >= 11 { self.unlock("deep1100"); } if self.zone >= 20 { self.unlock("endless2000"); }
        if !self.rec_shown && self.start_best >= 200 && depth > self.start_best { self.rec_shown = true; let (x, y) = (self.p.x, self.p.y - 64.); self.text(x, y, t("newRec"), 0xffd54f, true, true); self.snd(Sfx::Level); self.ring(self.p.x, self.p.y, 10., 160., 0.6, c::GOLD, 5.); }
        self.s.best_depth = self.s.best_depth.max(depth);
        if self.zone % 5 == 0 { let k = boss_at(self.zone); self.start_boss(k, ((self.zone - 5) / 20) as f32); let tr = boss_tier(self.zone); if let Some(b) = self.boss_idx() { self.apply_tier(b, tr); if tr > 0 { self.banner(crate::tiers::boss_name(k, tr, i18n::is_en()).unwrap_or("").to_string(), format!("{} · {} {}", t("lord"), self.zone * 100, t("m")), 0xff4f8f, 3.4); } } }
        else if !self.try_guardian() { self.banner(format!("{} {}", depth, t("m")), i18n::zone((self.zone as usize - 1) % 15), 0x8fd8ff, 2.6); self.snd(Sfx::Nova); }
    }
    fn start_boss(&mut self, k: K, cyc: f32) {
        self.hp_scale = 1. + cyc * 1.3;
        let Some(i) = self.spawn_enemy(k, self.p.x, self.p.y - self.vh - 140., false) else { return };
        { let e = &mut self.en.items[i]; e.spawn_t = 0.; e.state = 0; e.st = 3.5; e.p1 = 0.8; if k == K::Boss3 { e.state = 3; e.st = 1.5; e.p1 = 0.; e.p3 = 1.; } }
        self.boss = self.en.items[i].uid as i32;
        let dx = self.rr(-40., 40.); self.drop_pick(self.p.x + dx, self.p.y + 60., 4, 30.);
        self.banner(i18n::boss(k.key()), format!("{} · {} {}", t("lord"), self.zone * 100, t("m")), 0xff4f8f, 3.4);
        self.snd(Sfx::Warn); self.vibrate(220); self.shake(10.);
    }

    // ---------- стрельба ----------
    pub fn nearest_enemy(&self, x: f32, y: f32, max_d: f32) -> i32 {
        let (mut best, mut bd) = (-1i32, max_d * max_d); let (mx, my) = (self.vw + 16., self.vh + 16.);
        for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead || e.spawn_t > 0.2 { continue; }
            if (e.x - self.cam_x).abs() > mx || (e.y - self.cam_y).abs() > my { continue; }
            let (dx, dy) = (e.x - x, e.y - y); let d = dx * dx + dy * dy; if d < bd { bd = d; best = i as i32; } }
        best
    }
    pub fn fire_pb(&mut self, x: f32, y: f32, a: f32, dmg: f32, split: bool) -> Option<usize> {
        let i = self.pb.spawn()?; let s = self.st.bspd; let crit = self.rand() < self.st.crit;
        let f = self.p.form; let r0 = 4. + 2. * self.lv(u::CALIBER) as f32;
        // форма атаки искры: (скорость, радиус, время жизни)
        let (ks, kr, life) = match f { 1 => (1.35, 0.8, 0.95), 2 => (0.72, 1.7, 1.5), 3 => (1.1, 0.9, 0.5), 4 => (0.85, 1.5, 1.2), 5 => (1.05, 1.0, 1.05), 6 => (1.0, 1.1, 1.3), 7 => (0.8, 1.4, 0.4), 8 => (0.95, 1.2, 1.4), 9 => (1.1, 1.1, 1.15), _ => (1., 1., 1.1) };
        self.pb.items[i] = PBul { x, y, vx: a.cos() * s * ks, vy: a.sin() * s * ks, dmg, pierce: self.st.pierce, bounce: self.st.bounce, life, crit, tgt: -1, split, r: r0 * kr, form: f, ..Default::default() };
        Some(i)
    }
    pub fn e_shoot(&mut self, x: f32, y: f32, a: f32, mut spd: f32, r: f32, dmg: f32, col: u8, spin: f32) -> Option<usize> {
        let i = self.eb.spawn()?; if self.muts[4] { spd *= 1.3; }
        self.eb.items[i] = EBul { x, y, vx: a.cos() * spd, vy: a.sin() * spd, r, dmg, life: 7., col, spin, acc: 0., grazed: false };
        Some(i)
    }

    // ---------- игрок ----------
    fn update_player(&mut self, dt: f32) {
        let (mx, my) = (self.jx, self.jy); let m = hypot(mx, my);
        if m > 0.15 { self.p.ang = my.atan2(mx); }
        if self.dash_q { self.dash_q = false;
            if self.p.dash_cd <= 0. && self.p.dash_t <= 0. { let a = if m > 0.15 { my.atan2(mx) } else { self.p.ang };
                self.p.vx = a.cos() * 900.; self.p.vy = a.sin() * 900.; self.p.dash_t = 0.17; self.p.dash_cd = self.st.dash_cd; self.dash_id += 1;
                if self.tut.on && self.tut.step == 3 { self.tut.v = 1.; }
                self.snd(Sfx::Dash); self.ring(self.p.x, self.p.y, 6., 50., 0.3, self.p.pal, 3.); self.vibrate(15);
                if self.lv(u::TIDE) > 0 { self.ring(self.p.x, self.p.y, 10., 120., 0.45, c::WHITE, 5.); } } }
        if self.p.dash_t > 0. { self.p.dash_t -= dt;
            let (ox, oy) = (self.rr(-5., 5.), self.rr(-5., 5.)); self.part(self.p.x + ox, self.p.y + oy, -self.p.vx * 0.1, -self.p.vy * 0.1, 0.35, 9., self.p.pal, 2.);
            if self.st.dash_dmg > 0. || self.lv(u::TIDE) > 0 {
                let q = self.qa(self.p.x, self.p.y, 100.);
                for &i in &q { let (dead, dh, r, sc, ex, ey) = { let e = &self.en.items[i]; (e.dead, e.dash_hit, e.r, e.scale, e.x, e.y) };
                    if dead || dh == self.dash_id { continue; } let rr = r * sc + self.p.r + 10.; let (dx, dy) = (ex - self.p.x, ey - self.p.y);
                    if dx * dx + dy * dy < rr * rr { self.en.items[i].dash_hit = self.dash_id; let dmg = self.st.dash_dmg.max(self.st.dmg * 1.5); self.damage_enemy(i, dmg, true, f32::NAN, self.p.vx * 0.3, self.p.vy * 0.3, Src::None); } }
                self.qa_back(q); }
            if self.lv(u::TIDE) > 0 { let mut i = self.eb.n; while i > 0 { i -= 1; let (bx, by) = (self.eb.items[i].x, self.eb.items[i].y);
                if (bx - self.p.x).powi(2) + (by - self.p.y).powi(2) < 70. * 70. { self.burst(bx, by, 3, c::WHITE, 90., 5., 0.3); self.eb.kill(i); self.score += 2.; } } }
        } else { let (tvx, tvy) = (mx * self.st.speed, my * self.st.speed); let a = 1. - (-dt * 12.).exp(); self.p.vx += (tvx - self.p.vx) * a; self.p.vy += (tvy - self.p.vy) * a; }
        if self.pull_t > 0. { self.pull_t -= dt; let (dx, dy) = (self.pull_x - self.p.x, self.pull_y - self.p.y); let d = hypot(dx, dy).max(1.); self.p.x += dx / d * 125. * dt; self.p.y += dy / d * 125. * dt; }
        self.p.x += self.p.vx * dt; self.p.y += self.p.vy * dt;
        let d = hypot(self.p.x, self.p.y); let lim = cfg::ARENA_R - self.p.r; if d > lim { self.p.x *= lim / d; self.p.y *= lim / d; }
        if self.p.inv > 0. { self.p.inv -= dt; } if self.p.dash_cd > 0. { self.p.dash_cd -= dt; }
        if self.p.hp < self.p.max_hp * 0.3 { self.p.beat_t -= dt; if self.p.beat_t <= 0. { self.p.beat_t = 0.9; self.snd(Sfx::Beat); } }
        if self.st.regen > 0. && self.p.hp < self.p.max_hp { self.p.hp = (self.p.hp + self.st.regen * dt).min(self.p.max_hp); }
        self.p.hb = (self.p.max_hp * cfg::HEAL_RATE * 2.).min(self.p.hb + self.p.max_hp * cfg::HEAL_RATE * dt);
        self.update_new_upg(dt); self.update_upg2(dt); self.update_upg3(dt);
        if self.st.barrier_max > 0 && self.p.shield < self.st.barrier_max { self.p.shield_t -= dt; if self.p.shield_t <= 0. { self.p.shield += 1; self.p.shield_t = self.st.barrier_cd; self.ring(self.p.x, self.p.y, self.p.r, self.p.r + 14., 0.4, c::WHITE, 3.); self.snd(Sfx::Graze); } }
        self.p.trail_t -= dt; if self.p.trail_t <= 0. { self.p.trail_t = 0.035; self.trail[self.trail_head * 2] = self.p.x; self.trail[self.trail_head * 2 + 1] = self.p.y; self.trail_head = (self.trail_head + 1) % 12; }
        // стрельба
        self.p.fire_t -= dt;
        if self.p.fire_t <= 0. {
            let tg = self.nearest_enemy(self.p.x, self.p.y, self.st.range);
            if tg >= 0 { self.p.fire_t += 1. / (self.st.rate * (1. + self.rel_blood) * (1. + (self.lv(u::FRENZY) as f32 * 0.04 * (self.combo as f32 / 10.)).min(0.4 * self.lv(u::FRENZY) as f32 / 3.))); if self.p.fire_t < 0. { self.p.fire_t = 0.; }
                let e = &self.en.items[tg as usize]; let a = (e.y - self.p.y).atan2(e.x - self.p.x); let n = self.st.multi; let sp = 0.15; let (px, py) = (self.p.x, self.p.y);
                let sp = match self.p.form { 3 => 0.26, 7 => 0.2 + self.rr(-0.08, 0.08), _ => sp };
                for i in 0..n { self.fire_pb(px + a.cos() * 14., py + a.sin() * 14., a + (i as f32 - (n - 1) as f32 / 2.) * sp, self.st.dmg, true); }
                // Шквал — дробь: ещё два коротких снаряда веером
                if self.p.form == 3 { for k in [-1f32, 1.] { let j = self.rr(-0.06, 0.06); self.fire_pb(px + a.cos() * 14., py + a.sin() * 14., a + k * (sp * (n as f32) * 0.5 + 0.2) + j, self.st.dmg * 0.6, false); } }
                if self.st.echo_ch > 0. && self.rand() < self.st.echo_ch { for i in 0..n { let j = self.rr(-0.05, 0.05); self.fire_pb(px + a.cos() * 14., py + a.sin() * 14., a + (i as f32 - (n - 1) as f32 / 2.) * sp + j, self.st.dmg * 0.8, true); } self.part(px, py, 0., 0., 0.2, 14., c::ICE, 1.); }
                if self.st.over > 0 { self.p.shot_n += 1; if self.p.shot_n % self.st.over == 0 { if let Some(hb) = self.fire_pb(px + a.cos() * 16., py + a.sin() * 16., a, self.st.dmg * 4., false) { self.pb.items[hb].pierce += 4; self.pb.items[hb].r = 7.; } self.snd(Sfx::Nova); self.ring(px, py, 6., 40., 0.25, c::GOLD, 4.); } }
                self.part(px + a.cos() * 18., py + a.sin() * 18., a.cos() * 60., a.sin() * 60., 0.12, 10., self.p.pal, 0.);
                self.snd(Sfx::Shoot); self.on_shot(px, py, a);
            } else { self.p.fire_t = 0.05; }
        }
        // споры-спутники
        if self.st.orb_n > 0 { self.orb_a += dt * 2.9; let n = self.st.orb_n;
            for i in 0..n as usize { let a = self.orb_a + i as f32 * TAU / n as f32; let (ox, oy) = (self.p.x + a.cos() * 64., self.p.y + a.sin() * 64.); self.orb[i * 2] = ox; self.orb[i * 2 + 1] = oy;
                let q = self.qa(ox, oy, 76.);
                for &j in &q { let (dead, cd, sp, r, sc, ex, ey) = { let e = &self.en.items[j]; (e.dead, e.orb_cd, e.spawn_t, e.r, e.scale, e.x, e.y) };
                    if dead || cd > self.t || sp > 0.2 { continue; } let rr = r * sc + 10.; let (dx, dy) = (ex - ox, ey - oy);
                    if dx * dx + dy * dy < rr * rr { self.en.items[j].orb_cd = self.t + 0.38; let cr = self.rand() < self.st.crit; let dm = self.st.orb_dmg * if cr { self.st.crit_mul } else { 1. };
                        self.damage_enemy(j, dm, cr, f32::NAN, dx * 2., dy * 2., Src::None); self.burst(ox, oy, 4, c::DRIFT, 120., 6., 0.3);
                        if self.lv(u::STORM) > 0 && !self.en.items[j].dead && self.rand() < 0.45 { let n = 2 + self.lv(u::CHAIN); self.chain_from(j, self.st.dmg * 0.8, n); }
                        break; } }
                self.qa_back(q); } }
        if self.st.nova_lv > 0 { self.p.nova_t -= dt; if self.p.nova_t <= 0. { self.p.nova_t = self.st.nova_cd; self.do_nova(); } }
        if self.st.mine_lv > 0 { self.p.mine_t -= dt; if self.p.mine_t <= 0. { self.p.mine_t = self.st.mine_cd;
            if let Some(m) = self.mines.spawn() { self.mines.items[m] = Mine { x: self.p.x, y: self.p.y, t: 0., r: 85. + 10. * self.st.mine_lv as f32, dmg: self.st.dmg * (2.6 + 0.4 * self.st.mine_lv as f32), inst: false, freeze: self.lv(u::ABYSSICE) > 0 }; } } }
        if self.flare_q { self.flare_q = false; if self.p.flare >= 100. { self.do_flare(false); } }
    }
    fn strongest_enemy(&self, max_d: f32) -> i32 {
        let (mut best, mut bh) = (-1i32, 0f32); let (mx, my) = (self.vw + 16., self.vh + 16.);
        for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead || e.spawn_t > 0.2 || e.kind == K::Crystal { continue; }
            if (e.x - self.cam_x).abs() > mx || (e.y - self.cam_y).abs() > my || hypot(e.x - self.p.x, e.y - self.p.y) > max_d { continue; }
            if e.hp > bh { bh = e.hp; best = i as i32; } }
        best
    }
    fn update_new_upg(&mut self, dt: f32) {
        if self.p.ink_q { self.p.ink_q = false; self.ink_cloud(); }
        if self.st.harpoon_lv > 0 { self.p.harp_t -= dt; if self.p.harp_t <= 0. { let tg = self.strongest_enemy(560.); self.p.harp_t = if tg >= 0 { self.st.harpoon_cd } else { 0.4 };
            if tg >= 0 { let e = &self.en.items[tg as usize]; let a = (e.y - self.p.y).atan2(e.x - self.p.x); let n = if self.lv(u::SPEAR) > 0 { 3 } else { 1 }; let (px, py) = (self.p.x, self.p.y);
                for k in 0..n { if let Some(b) = self.fire_pb(px + a.cos() * 16., py + a.sin() * 16., a + (k as f32 - (n - 1) as f32 / 2.) * 0.16, self.st.harpoon_dmg, false) {
                    let bb = &mut self.pb.items[b]; bb.pierce = 99; bb.bounce = 0; bb.r = 8.; bb.crit = true; bb.life = 1.4; } }
                self.snd(Sfx::Boom(false)); self.shake(2.); } } }
        self.p.beam_tg = -1; self.p.beam_tg2 = -1;
        if self.st.beam_lv > 0 { let tg = self.nearest_enemy(self.p.x, self.p.y, self.st.beam_r); self.p.beam_tg = tg;
            if tg >= 0 && self.lv(u::LIGHTHOUSE) > 0 { let (tx, ty) = (self.en.items[tg as usize].x, self.en.items[tg as usize].y); let (mut b2, mut bd) = (-1i32, 160. * 160.);
                for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead || i as i32 == tg || e.spawn_t > 0.2 { continue; } let q = (e.x - tx).powi(2) + (e.y - ty).powi(2); if q < bd { bd = q; b2 = i as i32; } }
                self.p.beam_tg2 = b2; }
            self.p.beam_t -= dt; if self.p.beam_t <= 0. { self.p.beam_t = 0.15;
                for (k, e) in [self.p.beam_tg, self.p.beam_tg2].into_iter().enumerate() { if e >= 0 && !self.en.items[e as usize].dead {
                    if self.lv(u::LIGHTHOUSE) > 0 { let s = &mut self.en.items[e as usize].slow; *s = s.max(0.5); }
                    let dm = self.st.beam_dps * 0.15 * if k == 1 { 0.6 } else { 1. }; self.damage_enemy(e as usize, dm, false, f32::NAN, 0., 0., Src::Chain); } } } }
        if self.st.aura_lv > 0 { self.p.aura_t -= dt; if self.p.aura_t <= 0. { self.p.aura_t = 0.25; let q = self.qa(self.p.x, self.p.y, self.st.aura_r + 30.);
            for &i in &q { let e = &self.en.items[i]; if e.dead || e.spawn_t > 0.2 { continue; } let (dx, dy) = (e.x - self.p.x, e.y - self.p.y); let d = hypot(dx, dy).max(1.);
                if d > self.st.aura_r + e.r * e.scale { continue; } let pull = if self.lv(u::MAELSTROM) > 0 && !e.kind.d().boss { -90. } else { 0. };
                self.damage_enemy(i, self.st.aura_dps * 0.25, false, f32::NAN, dx / d * pull, dy / d * pull, Src::Chain); }
            self.qa_back(q); } }
        if self.st.twin_lv > 0 { let a = self.p.vy.atan2(self.p.vx); let mv = hypot(self.p.vx, self.p.vy) > 20.; let aa = if mv { a } else { self.t };
            let (tx, ty) = (self.p.x - aa.cos() * 34., self.p.y - aa.sin() * 34.); let k = (dt * 7.).min(1.); self.p.tw_x += (tx - self.p.tw_x) * k; self.p.tw_y += (ty - self.p.tw_y) * k;
            if hypot(self.p.tw_x - self.p.x, self.p.tw_y - self.p.y) > 200. { self.p.tw_x = self.p.x; self.p.tw_y = self.p.y; }
            self.p.tw_t -= dt; if self.p.tw_t <= 0. { let tg = self.nearest_enemy(self.p.tw_x, self.p.tw_y, self.st.range); self.p.tw_t = if tg >= 0 { self.st.twin_cd } else { 0.1 };
                if tg >= 0 { let e = &self.en.items[tg as usize]; let ta = (e.y - self.p.tw_y).atan2(e.x - self.p.tw_x); let n = if self.lv(u::CHOIR) > 0 { 3 } else { 1 }; let (x, y) = (self.p.tw_x, self.p.tw_y);
                    for k in 0..n { self.fire_pb(x, y, ta + (k as f32 - (n - 1) as f32 / 2.) * 0.2, self.st.twin_dmg, false); } } } }
        if self.st.vortex_lv > 0 { self.p.vort_t -= dt; if self.p.vort_t <= 0. { self.p.vort_t = 26. - 8. * self.st.vortex_lv as f32; let mut n = 0;
            for i in 0..self.picks.n { let q = &mut self.picks.items[i]; if q.kind <= 2 && !q.mag { q.mag = true; q.t = 0.; n += 1; } }
            if n > 0 { self.ring(self.p.x, self.p.y, 20., 260., 0.6, c::ICE, 4.); self.snd(Sfx::Nova); } } }
        if self.p.ink_t > 0. { self.p.ink_t -= dt;
            if self.lv(u::KRAKEN) > 0 { self.p.ink_d -= dt; if self.p.ink_d <= 0. { self.p.ink_d = 0.25; let (ix, iy) = (self.p.ink_x, self.p.ink_y); let q = self.qa(ix, iy, 170.);
                for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } if hypot(e.x - ix, e.y - iy) < 170. { self.damage_enemy(i, self.st.dmg * 1.6, false, f32::NAN, 0., 0., Src::Chain); } }
                self.qa_back(q); } } }
        while self.static_q > 0 { self.static_q -= 1; self.static_strike(); }
    }
    fn ink_cloud(&mut self) {
        self.p.ink_x = self.p.x; self.p.ink_y = self.p.y; self.p.ink_t = if self.lv(u::KRAKEN) > 0 { 3. } else { 1.2 }; let r = 150. + 25. * self.st.ink_lv as f32;
        let mut i = self.eb.n; while i > 0 { i -= 1; if hypot(self.eb.items[i].x - self.p.x, self.eb.items[i].y - self.p.y) < r { self.eb.kill(i); } }
        let q = self.qa(self.p.x, self.p.y, r); for &i in &q { if !self.en.items[i].dead { let s = &mut self.en.items[i].slow; *s = s.max(2.2); } } self.qa_back(q);
        self.burst(self.p.x, self.p.y, 26, c::PURP, 240., 14., 0.9); self.ring(self.p.x, self.p.y, 10., r, 0.45, c::PURP, 6.);
    }
    fn static_strike(&mut self) {
        if self.state != State::Play { return; }
        let mut cand: Vec<usize> = (0..self.en.n).filter(|&i| { let e = &self.en.items[i]; !e.dead && e.spawn_t <= 0.2 && (e.x - self.cam_x).abs() < self.vw && (e.y - self.cam_y).abs() < self.vh }).collect();
        for _ in 0..self.st.static_k { if cand.is_empty() { break; } let k = (self.rand() * cand.len() as f32) as usize % cand.len(); let i = cand.swap_remove(k);
            let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); let ox = self.rr(-40., 40.); let top = self.cam_y - self.vh - 20.; self.bolt(ex + ox, top, ex, ey, c::GOLD); self.burst(ex, ey, 8, c::GOLD, 160., 6., 0.35);
            self.damage_enemy(i, self.st.dmg * 5., true, f32::NAN, 0., 0., Src::Static); }
        if self.st.static_k > 0 { self.snd(Sfx::Boom(false)); self.shake(3.); }
    }
    fn do_nova(&mut self) {
        let r = self.st.nova_r; let sup = self.lv(u::SUPERNOVA) > 0; let dmg = self.st.dmg * (1.4 + 0.45 * self.st.nova_lv as f32) * if sup { 2. } else { 1. };
        self.ring(self.p.x, self.p.y, 10., r, 0.45, if sup { c::GOLD } else { c::JELLY }, 6.); self.ring(self.p.x, self.p.y, 5., r * 0.7, 0.35, c::WHITE, 2.); self.snd(Sfx::Nova);
        for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead { continue; } let (dx, dy) = (e.x - self.p.x, e.y - self.p.y); let rr = r + e.r * e.scale;
            if dx * dx + dy * dy < rr * rr { let d = (dx * dx + dy * dy).sqrt().max(1.); let cr = sup && self.rand() < self.st.crit * 2.;
                self.damage_enemy(i, dmg * if cr { self.st.crit_mul } else { 1. }, cr, f32::NAN, dx / d * 260., dy / d * 260., if sup { Src::Nova } else { Src::None }); } }
        let mut i = self.eb.n; while i > 0 { i -= 1; let b = self.eb.items[i].clone(); if (b.x - self.p.x).powi(2) + (b.y - self.p.y).powi(2) < r * r { self.part(b.x, b.y, 0., 0., 0.3, 10., b.col, 0.); self.eb.kill(i); } }
    }
    pub fn do_flare(&mut self, free: bool) {
        if !free { self.quest_add("flare", 1); self.p.flare = 0.; self.s.flares += 1; if self.s.flares >= 10 { self.unlock("flare10"); } if self.tut.on && self.tut.step == 4 { self.tut.v = 1.; } }
        self.flash = 1.; self.hit_stop = 0.14; self.shake(24.); self.snd(Sfx::Flare); self.vibrate(90);
        self.ring(self.p.x, self.p.y, 20., 900., 0.9, c::GOLD, 14.); self.ring(self.p.x, self.p.y, 10., 600., 0.7, c::WHITE, 6.); self.burst(self.p.x, self.p.y, 40, c::GOLD, 600., 14., 0.9);
        let r = hypot(self.vw, self.vh) + 60.;
        for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead { continue; } let (dx, dy) = (e.x - self.p.x, e.y - self.p.y);
            if dx * dx + dy * dy < r * r { let d = (dx * dx + dy * dy).sqrt().max(1.); let dm = if e.kind.d().boss { 180. + self.st.dmg * 12. } else { 90. + self.st.dmg * 9. };
                self.damage_enemy(i, dm, true, f32::NAN, dx / d * 400., dy / d * 400., Src::None); } }
        for i in 0..self.eb.n { let b = self.eb.items[i].clone(); let (a, bb) = (self.rr(-40., 40.), self.rr(-40., 40.)); self.part(b.x, b.y, a, bb, 0.6, 12., c::GOLD, 2.); self.score += 3.; }
        self.eb.clear();
        if !free { self.banner(t("flareB"), String::new(), 0xffd54f, 1.1); }
    }

    // ---------- урон ----------
    pub fn damage_enemy(&mut self, i: usize, mut dmg: f32, crit: bool, from_ang: f32, kx: f32, ky: f32, src: Src) {
        if self.en.items[i].dead { return; }
        let kind = self.en.items[i].kind;
        if self.en.items[i].inv_t > 0. { dmg *= 0.15; } // щит жреца бездны
        dmg *= self.upg2_mul(i);
        if self.en.items[i].aff == crate::content::AFF_SHIELD { dmg = self.affix_absorb(i, dmg); }
        if kind == K::Crab && self.en.items[i].sh > 0. && !from_ang.is_nan() && ang_diff(self.en.items[i].ang, from_ang).abs() < 1.0 {
            let (ex, ey, ea, er) = { let e = &self.en.items[i]; (e.x, e.y, e.ang, e.r) };
            self.en.items[i].sh -= dmg; dmg *= 1. - cfg::CRAB_BLOCK; let (a, b) = (self.rr(-80., 80.), self.rr(-80., 80.)); self.part(ex + ea.cos() * er, ey + ea.sin() * er, a, b, 0.25, 7., c::WHITE, 2.);
            if self.en.items[i].sh <= 0. { let (fx, fy) = (ex + ea.cos() * er, ey + ea.sin() * er); self.burst(fx, fy, 14, c::WHITE, 200., 6., 0.45); self.ring(fx, fy, 4., 46., 0.3, c::WHITE, 3.); self.snd(Sfx::Clink); self.shake(2.5);
                if self.quality > 0 { self.text(ex, ey - er - 14., t("crabBreak"), 0xffd6dc, false, false); } }
            else if self.rand() < 0.5 { self.snd(Sfx::Clink); }
        }
        if kind == K::KingCrab && self.en.items[i].sh > 0. && !from_ang.is_nan() && ang_diff(self.en.items[i].ang, from_ang).abs() < 1.1 { dmg = self.king_shield(i, dmg); }
        if self.st.rage > 0. { dmg *= 1. + self.st.rage * if self.p.hp < self.p.max_hp * 0.4 { 2. } else { 1. }; }
        if kind == K::Boss3 && self.crystals > 0 { dmg *= 0.25; if self.rand() < 0.3 { self.snd(Sfx::Clink); } }
        let boss = kind.d().boss;
        { let frost = self.st.frost; let burn = self.st.burn; let e = &mut self.en.items[i]; e.hp -= dmg; e.flash = 0.07;
            if !boss { let kb = if e.elite { 0.3 } else { 1. }; e.vx += kx * kb; e.vy += ky * kb; }
            if frost > 0 && src != Src::Chain { e.slow = 0.6 + 0.5 * frost as f32; }
            if burn > 0. && src != Src::Burn && !boss { e.burn = burn; e.burn_t = 3.; } }
        if self.s.set.nums { self.dmg_text(i, dmg, crit); }
        self.snd(Sfx::Hit);
        if self.en.items[i].hp <= 0. { self.kill_enemy(i, src); } else { self.try_execute(i); }
    }
    fn dmg_text(&mut self, i: usize, dmg: f32, crit: bool) {
        let (uid, txt, ex, ey, er, sc) = { let e = &self.en.items[i]; (e.uid, e.txt, e.x, e.y, e.r, e.scale) };
        if txt >= 0 && (txt as usize) < self.texts.n { let tt = &mut self.texts.items[txt as usize];
            if tt.owner == uid && tt.life > tt.max * 0.35 { tt.val += dmg; tt.s = num_str(tt.val); tt.life = tt.life.max(tt.max * 0.7); if crit && !tt.crit { tt.crit = true; tt.col = 0xffd54f; } return; } }
        if !crit && self.texts.n >= 16 { return; }
        let n = self.text(ex, ey - er * sc - 4., num_str(dmg), if crit { 0xffd54f } else { 0xffffff }, crit, false);
        self.texts.items[n].owner = uid; self.texts.items[n].val = dmg; self.en.items[i].txt = n as i32;
    }
    pub fn chain_from(&mut self, e0: usize, dmg: f32, n: u32) {
        let (mut cx, mut cy) = (self.en.items[e0].x, self.en.items[e0].y); self.chain_id += 1; let id = self.chain_id; self.en.items[e0].chain_mark = id;
        for _ in 0..n { let q = self.qb(cx, cy, 200.); let (mut best, mut bd) = (usize::MAX, 200. * 200.);
            for &k in &q { let e = &self.en.items[k]; if e.dead || e.chain_mark == id { continue; } let d = (e.x - cx).powi(2) + (e.y - cy).powi(2); if d < bd { bd = d; best = k; } }
            self.qb_back(q); if best == usize::MAX { break; }
            let (bx, by) = (self.en.items[best].x, self.en.items[best].y); self.bolt(cx, cy, bx, by, c::ICE); self.en.items[best].chain_mark = id; cx = bx; cy = by;
            self.damage_enemy(best, dmg, false, f32::NAN, 0., 0., Src::Chain); }
    }
    fn ignite_near(&mut self, x: f32, y: f32) {
        let q = self.qb(x, y, 110.); let burn = self.st.burn.max(1.);
        for &i in &q { let e = &mut self.en.items[i]; if e.dead || e.kind.d().boss { continue; } e.burn = e.burn.max(burn); e.burn_t = e.burn_t.max(2.4); }
        self.qb_back(q);
    }
    fn add_ghost(&mut self, i: usize) { let e = &self.en.items[i]; let g = Ghost { on: true, kind: e.kind, tier: e.tier, bare: e.kind == K::Crab && e.sh <= 0., x: e.x, y: e.y, a: e.ang, s: e.scale, t: 0. }; self.ghosts[self.ghost_i] = g; self.ghost_i = (self.ghost_i + 1) % self.ghosts.len(); }
    pub fn kill_enemy(&mut self, i: usize, src: Src) {
        self.en.items[i].dead = true; self.kills += 1;
        let e = self.en.items[i].clone(); let boss = e.kind.d().boss;
        self.tier_death(&e); self.upg2_kill(&e); if e.aff > 0 && src != Src::Cleanup { self.affix_death(&e); } self.relic_kill(boss);
        self.combo += 1; self.combo_t = 2.6; if self.combo > self.max_combo { self.max_combo = self.combo; }
        self.mult = 1. + (self.combo as f32 * 0.05).min(9.); self.score += (e.score * self.mult).round() as f64;
        self.p.flare = (self.p.flare + if boss { 50. } else if e.elite { 6. } else { 0.9 } * self.st.flare_mul).min(100.);
        if (self.st.siphon_ch > 0. && self.rand() < self.st.siphon_ch) || self.st.leech { if self.p.hp < self.p.max_hp { let h = self.heal_p(self.p.max_hp * if self.st.leech { 0.008 } else { 0.012 } * if boss { 6. } else { 1. });
            if h >= 1. && self.rand() < 0.25 { let (x, y) = (self.p.x, self.p.y - 24.); self.text(x, y, format!("+{}", h.round()), 0x8affc0, false, false); } } }
        let sz = e.r * e.scale;
        if !boss && src != Src::Cleanup { self.add_ghost(i); }
        if self.st.static_lv > 0 && src != Src::Static { self.p.static_c += 1; if self.p.static_c >= self.st.static_n { self.p.static_c = 0; self.static_q += 1; } }
        self.burst(e.x, e.y, (8. + sz * 0.6).min(26.) as u32, e.col, 90. + sz * 6., 6. + sz * 0.3, 0.55); self.burst(e.x, e.y, 4, c::WHITE, 60., 5., 0.3);
        self.ring(e.x, e.y, sz * 0.5, sz * 2.4, 0.35, e.col, 2.5); self.shake(1.5 + sz * 0.06); self.snd(Sfx::Kill(self.combo));
        let mut xp = e.xp; while xp > 0. { let v = if xp >= 10. { 10. } else if xp >= 3. { 3. } else { 1. }; xp -= v; let (a, b) = (self.rr(-8., 8.), self.rr(-8., 8.)); self.drop_pick(e.x + a, e.y + b, if v >= 10. { 2 } else if v >= 3. { 1 } else { 0 }, v); }
        if e.elite { let n = self.rng.int(2, 4); for _ in 0..n { let (a, b) = (self.rr(-12., 12.), self.rr(-12., 12.)); self.drop_pick(e.x + a, e.y + b, 3, 1.); } } else if self.rand() < 0.012 { self.drop_pick(e.x, e.y, 3, 1.); }
        if self.rand() < 0.01 && self.p.hp < self.p.max_hp * 0.8 { self.drop_pick(e.x, e.y, 4, 25.); }
        if self.rand() < 0.004 { self.drop_pick(e.x, e.y, 5, 0.); }
        if e.kind == K::Urchin { for k in 0..3 { let a = k as f32 / 3. * TAU + self.rand(); if let Some(s) = self.spawn_enemy(K::Spikelet, e.x + a.cos() * 10., e.y + a.sin() * 10., false) { let ss = &mut self.en.items[s]; ss.spawn_t = 0.; ss.vx = a.cos() * 260.; ss.vy = a.sin() * 260.; } } }
        if e.kind == K::Bomber && src != Src::Cleanup { let n = 10 + self.zone; for k in 0..n { let j = self.rr(-0.1, 0.1); self.e_shoot(e.x, e.y, k as f32 * TAU / n as f32 + j, 150. + self.zone as f32 * 4., 5., 10. * self.dmg_scale, c::CORAL, 0.); }
            self.ring(e.x, e.y, 6., 70., 0.4, c::CORAL, 4.); self.burst(e.x, e.y, 16, c::CORAL, 220., 8., 0.5); self.snd(Sfx::Boom(false)); self.shake(6.); }
        if e.kind == K::Spawner && src != Src::Cleanup { self.spawn_fry(i, 4); }
        if src == Src::Nova && self.lv(u::SUPERNOVA) > 0 { if let Some(m) = self.mines.spawn() { self.mines.items[m] = Mine { x: e.x, y: e.y, t: 99., r: 60., dmg: self.st.dmg * 1.5, inst: true, freeze: false }; } }
        if e.kind == K::Chest { let n = 6 + self.zone.min(8); for _ in 0..n { let (a, b) = (self.rr(-26., 26.), self.rr(-26., 26.)); self.drop_pick(e.x + a, e.y + b, 3, 1.); }
            if self.rand() < 0.35 && self.relics.len() < crate::content::RELICS.len() { self.relic_pending += 1; } else { self.level_pending += 1; } self.level_delay = self.level_delay.max(0.5); self.chests += 1; self.quest_add("chest", 1);
            self.burst(e.x, e.y, 30, c::GOLD, 260., 9., 0.7); self.ring(e.x, e.y, 10., 140., 0.5, c::GOLD, 5.); self.snd(Sfx::Level); self.banner(t("chestOpen"), t("chestOpenS"), 0xffd54f, 2.2); }
        if let Some(ch) = self.chal.as_mut() { if e.kind != K::Chest { ch.got += 1; } }
        self.quest_add("kills", 1); if self.combo >= 10 { self.quest_max("combo", self.combo); }
        if self.combo >= 50 { self.unlock("combo50"); } if self.combo >= 150 { self.unlock("combo150"); }
        if self.kills == 100 { self.unlock("kill100"); } if self.kills == 500 { self.unlock("kill500"); }
        for m in [25u32, 50, 100, 150, 200, 300, 500] { if self.combo == m && self.combo_milestone < m { self.combo_milestone = m; let (x, y) = (self.p.x, self.p.y - 40.); self.text(x, y, format!("{}{}!", t("comboX"), m), 0xffd54f, true, true); self.snd(Sfx::Level); } }
        if boss { self.boss_death(i); }
    }
    fn boss_death(&mut self, i: usize) {
        let e = self.en.items[i].clone();
        self.quest_add("boss", 1); if e.tier > 0 { self.unlock("lord"); }
        self.boss = -1; self.bosses_killed += 1; self.boss_clear_t = 3.; self.level_delay = self.level_delay.max(1.6);
        self.hit_stop = 0.35; self.flash = 1.; self.shake(34.); self.vibrate(370); self.snd(Sfx::Boom(true));
        for k in 0..4 { self.ring(e.x, e.y, 20., 200. + k as f32 * 120., 0.6 + k as f32 * 0.2, if k % 2 == 1 { c::WHITE } else { e.col }, 8.); }
        self.burst(e.x, e.y, 90, e.col, 520., 16., 1.3); self.burst(e.x, e.y, 40, c::WHITE, 300., 10., 1.);
        for _ in 0..20 { let (a, b) = (self.rr(-60., 60.), self.rr(-60., 60.)); self.drop_pick(e.x + a, e.y + b, 3, 1.); }
        self.drop_pick(e.x, e.y, 4, 50.); self.drop_pick(e.x + 30., e.y, 5, 0.);
        self.eb.clear();
        match e.kind {
            K::Boss1 => { self.unlock("boss1"); let (a, b) = i18n::pair("bossDie", 0); self.banner(a, b, 0x3ff0ff, 3.); }
            K::Boss2 => { self.unlock("boss2"); let (a, b) = i18n::pair("bossDie", 1); self.banner(a, b, 0xff4fd8, 3.5); }
            K::KingCrab | K::Queen => self.guardian_death(i),
            K::Boss4 => { self.banner(t("leviathanDie"), t("leviathanDieS"), 0x49e0c0, 3.);
                if self.zone % 5 != 0 { self.unlock("guard"); self.spawn_chest(e.x, e.y); self.boss_clear_t = 0.; self.zone_t = self.zone_t.max(cfg::ZONE_TIME * 0.45); } }
            _ => { self.unlock("boss3");
                for k in 0..self.en.n { if !self.en.items[k].dead && self.en.items[k].kind == K::Crystal { self.kill_enemy(k, Src::None); } }
                if !self.endless && !self.victory { self.victory = true; self.boss_clear_t = 0.; self.ending_t = 2.6; self.level_delay = 99.; self.p.inv = 99.;
                    for k in 0..self.en.n { if self.en.items[k].dead || k == i { continue; } let o = self.en.items[k].clone(); self.burst(o.x, o.y, 6, o.col, 160., 8., 0.6); self.en.items[k].dead = true; }
                    self.banner(t("heartOut"), String::new(), 0xffd54f, 2.4);
                } else { let (a, b) = i18n::pair("bossDie", 2); self.banner(a, b, 0xffd54f, 3.); } }
        }
    }
    pub fn explode(&mut self, x: f32, y: f32, r: f32, dmg: f32, freeze: bool) {
        let col = if freeze { c::ICE } else { c::PURP };
        self.ring(x, y, 8., r, 0.4, col, 5.); self.burst(x, y, 16, col, 260., 10., 0.5); self.burst(x, y, 5, c::WHITE, 120., 8., 0.3); self.snd(Sfx::Boom(false)); self.shake(4.);
        let q = self.qb(x, y, r + 30.);
        for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } let (dx, dy) = (e.x - x, e.y - y); let rr = r + e.r * e.scale;
            if dx * dx + dy * dy < rr * rr { let d = (dx * dx + dy * dy).sqrt().max(1.); if freeze { self.en.items[i].freeze = 1.6; } self.damage_enemy(i, dmg, false, f32::NAN, dx / d * 200., dy / d * 200., Src::None); } }
        self.qb_back(q);
    }
    pub fn heal_p(&mut self, v: f32) -> f32 { let a = v.min(self.p.hb).min(self.p.max_hp - self.p.hp).max(0.); self.p.hb -= a; self.p.hp += a; a }
    pub fn hurt_player(&mut self, dmg: f32) {
        if self.p.inv > 0. || self.p.dash_t > 0. || self.state != State::Play || self.dying > 0. || self.god { return; }
        if self.p.shield > 0 { self.p.shield -= 1; self.p.inv = self.p.inv.max(1.); self.snd(Sfx::Clink); self.ring(self.p.x, self.p.y, self.p.r, self.p.r + 30., 0.4, c::WHITE, 5.); self.shake(8.); self.vibrate(25);
            if self.st.aegis { let q = self.qa(self.p.x, self.p.y, 150.); for &i in &q { if !self.en.items[i].dead { self.damage_enemy(i, self.st.dmg * 3., true, f32::NAN, 0., 0., Src::None); } } self.qa_back(q); }
            return; }
        if self.relic_dodge() { return; }
        let dmg = (dmg * (1. - self.st.armor_pct) - self.st.armor).round().max(1.);
        self.p.hp -= dmg; self.p.inv = 0.9 + 0.3 * self.lv(u::INK) as f32;
        self.no_hit = false; self.hurt_flash = 1.; self.shake(13.); self.hit_stop = 0.06;
        if self.combo >= 10 { let (x, y) = (self.p.x, self.p.y - 30.); self.text(x, y, t("comboLost"), 0xff8a8a, false, false); }
        self.combo = 0; self.mult = 1.; self.combo_milestone = 0;
        self.snd(Sfx::Hurt); self.vibrate(55);
        if self.st.ink_lv > 0 { self.p.ink_q = true; }
        self.burst(self.p.x, self.p.y, 14, c::CRAB, 200., 8., 0.5);
        let (x, y) = (self.p.x, self.p.y - 20.); self.text(x, y, format!("-{}", dmg), 0xff5f6f, true, false);
        self.relic_hurt();
        if self.p.hp <= 0. {
            if self.relic_save() {}
            else if self.s.shop_lv("revive") > 0 && !self.revived { self.revived = true; self.p.hp = self.p.max_hp * 0.5; self.p.inv = 2.5; self.do_flare(true); self.banner(t("revive"), t("reviveS"), 0x4fff9a, 2.2); }
            else { self.p.hp = 0.; self.start_dying(); }
        }
    }
    pub fn start_dying(&mut self) {
        self.dying = 1.7; self.p.dead = true; self.jx = 0.; self.jy = 0.; self.dash_q = false; self.flare_q = false;
        self.snd(Sfx::Boom(true)); self.shake(30.); self.flash = 0.8; self.vibrate(390);
        self.burst(self.p.x, self.p.y, 70, self.p.pal, 420., 14., 1.4); self.burst(self.p.x, self.p.y, 30, c::WHITE, 220., 10., 1.); self.ring(self.p.x, self.p.y, 10., 320., 1., self.p.pal, 8.);
    }

    // ---------- подбор ----------
    pub fn drop_pick(&mut self, x: f32, y: f32, kind: u8, val: f32) {
        if self.picks.n >= self.picks.cap() { if kind <= 2 { let k = (self.rand() * self.picks.n as f32) as usize % self.picks.n; if self.picks.items[k].kind <= 2 { self.picks.items[k].val += val; } } return; }
        let i = self.picks.spawn().unwrap(); let a = self.rand() * TAU; let s = self.rr(30., 110.);
        self.picks.items[i] = Pick { x, y, vx: a.cos() * s, vy: a.sin() * s, kind, val, mag: false, t: 0. };
    }
    fn update_picks(&mut self, dt: f32) {
        let mr2 = self.st.magnet * self.st.magnet; let mut i = self.picks.n;
        while i > 0 { i -= 1;
            let (px, py, pr, dead) = (self.p.x, self.p.y, self.p.r, self.p.dead);
            let p = &mut self.picks.items[i]; p.t += dt;
            let (dx, dy) = (px - p.x, py - p.y); let d2 = dx * dx + dy * dy;
            if !p.mag && d2 < mr2 && !dead { p.mag = true; p.t = 0.; }
            if p.mag && !dead { let d = d2.sqrt().max(1.); let sp = 260. + p.t * 1300.; p.vx = dx / d * sp; p.vy = dy / d * sp;
                if d < pr + 10. { let pk = p.clone(); self.collect(&pk); self.picks.kill(i); continue; } }
            else { let f = (-dt * 3.).exp(); p.vx *= f; p.vy *= f; if p.kind <= 2 && p.t > 0.6 && d2 < 700. * 700. { let d = d2.sqrt().max(1.); p.x += dx / d * 38. * dt; p.y += dy / d * 38. * dt; } }
            p.x += p.vx * dt; p.y += p.vy * dt;
            if p.kind >= 3 && p.t > 22. { self.picks.kill(i); }
        }
    }
    fn collect(&mut self, p: &Pick) {
        let (x, y) = (self.p.x, self.p.y - 26.);
        match p.kind { 0..=2 => { self.add_xp(p.val); let f = self.p.level as f32 + (self.p.xp / self.p.xp_next) * 14.; self.snd(Sfx::Pick(f)); if self.tut.on && self.tut.step == 2 { self.tut.v += 1.; } }
            3 => { self.run_pearls += 1; self.quest_add("pearls", 1); self.snd(Sfx::Pearl); self.text(x, y, t("pearl1"), 0xffd6f5, false, false); }
            4 => { self.p.hp = (self.p.hp + p.val).min(self.p.max_hp); self.snd(Sfx::Pearl); self.text(x, y, format!("+{}", p.val), 0x4fff9a, true, false); self.ring(self.p.x, self.p.y, 5., 60., 0.4, c::EMER, 3.); }
            _ => { for k in 0..self.picks.n { if self.picks.items[k].kind <= 2 { self.picks.items[k].mag = true; self.picks.items[k].t = 0.; } }
                self.snd(Sfx::Level); self.ring(self.p.x, self.p.y, 5., 260., 0.6, c::ICE, 4.); self.text(x, y, t("magnetB"), 0x8fd8ff, true, false); } }
    }
    pub fn add_xp(&mut self, v: f32) {
        self.p.xp += v * self.st.xp_mul;
        while self.p.xp >= self.p.xp_next { self.p.xp -= self.p.xp_next; self.p.level += 1; self.p.xp_next = xp_need(self.p.level); self.level_pending += 1; self.level_delay = self.level_delay.max(0.3);
            self.ring(self.p.x, self.p.y, 10., 140., 0.5, c::GOLD, 5.); self.burst(self.p.x, self.p.y, 20, c::GOLD, 260., 8., 0.6); if self.p.level >= 20 { self.unlock("lvl20"); } }
    }

    // ---------- достижения и задания ----------
    pub fn unlock(&mut self, id: &str) {
        if self.s.ach.contains_key(id) || !i18n::ach_ids().iter().any(|x| x == id) { return; } let r = i18n::ach_reward(id);
        self.s.ach.insert(id.into(), 1); self.s.pearls += r; self.dirty = true; self.snd(Sfx::Ach);
        let (name, _) = i18n::ach(id); self.toast(tf("achReward", &[&r.to_string()]), name);
    }
    pub fn quest_add(&mut self, id: &str, n: u32) { let mut hit = vec![]; for (k, q) in self.s.daily.quests.iter_mut().enumerate() { if q.id == id && !q.done { q.p = (q.p + n).min(q.need); if q.p >= q.need { q.done = true; hit.push(k); } } } for k in hit { self.quest_hit(k); } }
    pub fn quest_max(&mut self, id: &str, v: u32) { let mut hit = vec![]; for (k, q) in self.s.daily.quests.iter_mut().enumerate() { if q.id == id && !q.done { q.p = q.p.max(v.min(q.need)); if q.p >= q.need { q.done = true; hit.push(k); } } } for k in hit { self.quest_hit(k); } }
    fn quest_hit(&mut self, k: usize) { self.dirty = true; self.snd(Sfx::Ach); let q = &self.s.daily.quests[k]; let name = i18n::quest(&q.id, q.need); self.toast(t("qDoneT"), name); }

    // ---------- эффекты, пули, мины ----------
    fn update_fx(&mut self, dt: f32) {
        let mut i = self.parts.n; while i > 0 { i -= 1; let p = &mut self.parts.items[i]; p.life -= dt; if p.life <= 0. { self.parts.kill(i); continue; }
            if p.drag > 0. { let f = (-dt * p.drag).exp(); p.vx *= f; p.vy *= f; } p.x += p.vx * dt; p.y += p.vy * dt; }
        let mut i = self.rings.n; while i > 0 { i -= 1; self.rings.items[i].life -= dt; if self.rings.items[i].life <= 0. { self.rings.kill(i); } }
        let mut i = self.texts.n; while i > 0 { i -= 1; let tt = &mut self.texts.items[i]; tt.life -= dt; if tt.life <= 0. { self.texts.kill(i); continue; } tt.y += tt.vy * dt; tt.vy *= (-dt * 3.).exp(); }
        let mut i = self.bolts.n; while i > 0 { i -= 1; self.bolts.items[i].life -= dt; if self.bolts.items[i].life <= 0. { self.bolts.kill(i); } }
        for g in self.ghosts.iter_mut() { if g.on { g.t += dt; if g.t >= 0.2 { g.on = false; } } }
    }
    fn update_mines(&mut self, dt: f32) {
        let mut i = self.mines.n;
        while i > 0 { i -= 1; self.mines.items[i].t += dt; let m = self.mines.items[i].clone(); let mut boom = m.inst || m.t > 7.;
            if !boom && m.t > 0.4 { let q = self.qa(m.x, m.y, 100.); for &k in &q { let e = &self.en.items[k]; if e.dead { continue; } let rr = 34. + e.r * e.scale; if (e.x - m.x).powi(2) + (e.y - m.y).powi(2) < rr * rr { boom = true; break; } } self.qa_back(q); }
            if boom { self.mines.kill(i); self.explode(m.x, m.y, m.r, m.dmg, m.freeze); if i > self.mines.n { i = self.mines.n; } } }
    }
    fn update_pbullets(&mut self, dt: f32) {
        let r2 = cfg::ARENA_R * cfg::ARENA_R; let mut i = self.pb.n;
        while i > 0 { i -= 1; if i >= self.pb.n { continue; }
            self.pb.items[i].life -= dt;
            if self.st.homing > 0 || self.pb.items[i].boom > 0. { self.pb.items[i].hom_t -= dt;
                if self.pb.items[i].hom_t <= 0. { self.pb.items[i].hom_t = 0.12; let (bx, by, lu) = (self.pb.items[i].x, self.pb.items[i].y, self.pb.items[i].last_uid); let q = self.qb(bx, by, 230.);
                    let mut bd = 230. * 230.; let (mut tg, mut tu) = (-1i32, 0u32);
                    for &k in &q { let e = &self.en.items[k]; if e.dead || e.uid == lu { continue; } let dd = (e.x - bx).powi(2) + (e.y - by).powi(2); if dd < bd { bd = dd; tg = k as i32; tu = e.uid; } }
                    self.qb_back(q); self.pb.items[i].tgt = tg; if tg >= 0 { self.pb.items[i].tgt_uid = tu; } }
                let tg = self.pb.items[i].tgt;
                if tg >= 0 { let ok = (tg as usize) < self.en.n && self.en.items[tg as usize].uid == self.pb.items[i].tgt_uid && !self.en.items[tg as usize].dead;
                    if ok { let (ex, ey) = (self.en.items[tg as usize].x, self.en.items[tg as usize].y); let b = &mut self.pb.items[i]; let a = b.vy.atan2(b.vx); let ta = (ey - b.y).atan2(ex - b.x); let s = hypot(b.vx, b.vy);
                        let lim = if b.boom > 0. { 7. } else { 3. + self.st.homing as f32 * 2.5 } * dt; let na = a + clamp(ang_diff(a, ta), -lim, lim); b.vx = na.cos() * s; b.vy = na.sin() * s; } else { self.pb.items[i].tgt = -1; } } }
            if self.lv(u::HUNTER) > 0 { let b = &mut self.pb.items[i]; let f = 1. + dt * 0.9; if b.vx * b.vx + b.vy * b.vy < 1400. * 1400. { b.vx *= f; b.vy *= f; } }
            { let b = &mut self.pb.items[i]; b.t += dt;
                match b.form {
                    5 => { let s = hypot(b.vx, b.vy).max(1.); let (nx, ny) = (-b.vy / s, b.vx / s); let w = (b.t * 34.).cos() * 34. * 9. * dt; b.x += nx * w; b.y += ny * w; } // Буря — зигзаг
                    2 => { let f = 1. - dt * 0.35; b.vx *= f; b.vy *= f; } // Панцирь — тяжёлые шары тормозят
                    _ => {} }
                b.x += b.vx * dt; b.y += b.vy * dt; }
            if self.pb.items[i].form == 6 && self.pb.items[i].tgt < 0 && self.st.homing == 0 { // Призрак — лёгкое самонаведение
                let (bx, by) = (self.pb.items[i].x, self.pb.items[i].y); let tg = self.nearest_enemy(bx, by, 170.);
                if tg >= 0 { let (ex, ey) = (self.en.items[tg as usize].x, self.en.items[tg as usize].y); let b = &mut self.pb.items[i]; let a = b.vy.atan2(b.vx); let ta = (ey - by).atan2(ex - bx); let s = hypot(b.vx, b.vy);
                    let na = a + clamp(ang_diff(a, ta), -3. * dt, 3. * dt); b.vx = na.cos() * s; b.vy = na.sin() * s; } }
            let b = self.pb.items[i].clone();
            if b.life <= 0. || b.x * b.x + b.y * b.y > r2 { self.pb.kill(i); continue; }
            let q = self.qa(b.x, b.y, 72.);
            let mut hit = usize::MAX;
            for &k in &q { let e = &self.en.items[k]; if e.dead || e.uid == b.last_uid || e.spawn_t > 0.25 { continue; } let rr = e.r * e.scale + b.r; if (e.x - b.x).powi(2) + (e.y - b.y).powi(2) > rr * rr { continue; } hit = k; break; }
            self.qa_back(q);
            if hit == usize::MAX { continue; }
            let k = hit; let s = hypot(b.vx, b.vy).max(1.);
            if b.boom > 0. { self.pb.kill(i); self.missile_boom(b.x, b.y, b.boom, b.dmg); continue; }
            let dm = b.dmg * if b.crit { self.st.crit_mul } else { 1. };
            self.damage_enemy(k, dm, b.crit, (-b.vy).atan2(-b.vx), b.vx / s * 70., b.vy / s * 70., Src::None);
            let (r1, r2b) = (self.rr(-50., 50.), self.rr(-50., 50.)); self.part(b.x, b.y, -b.vx * 0.15 + r1, -b.vy * 0.15 + r2b, 0.2, 8., self.p.pal, 2.);
            if self.st.chain_ch > 0. && self.rand() < self.st.chain_ch { self.chain_from(k, b.dmg * 0.6, self.st.chain_n); }
            if i >= self.pb.n { continue; }
            let euid = self.en.items[k].uid; self.pb.items[i].last_uid = euid;
            if self.pb.items[i].split && self.lv(u::PRISM) > 0 { self.pb.items[i].split = false; let a = b.vy.atan2(b.vx);
                for q in [-1f32, 1.] { if let Some(nb) = self.fire_pb(b.x, b.y, a + q * 0.45, b.dmg * 0.6, false) { let n = &mut self.pb.items[nb]; n.last_uid = euid; n.pierce = 0; n.bounce = 0; n.life = 0.5; } } }
            if self.pb.items[i].bounce > 0 { self.pb.items[i].bounce -= 1; let q = self.qb(b.x, b.y, 300.); let (mut best, mut bd) = (usize::MAX, 300. * 300.);
                for &o in &q { let e = &self.en.items[o]; if e.dead || o == k { continue; } let od = (e.x - b.x).powi(2) + (e.y - b.y).powi(2); if od < bd { bd = od; best = o; } } self.qb_back(q);
                if best != usize::MAX { let (ox, oy) = (self.en.items[best].x, self.en.items[best].y); let bb = &mut self.pb.items[i]; let a = (oy - bb.y).atan2(ox - bb.x); bb.vx = a.cos() * s; bb.vy = a.sin() * s; bb.life = bb.life.max(0.6); }
                else if self.pb.items[i].pierce > 0 { self.pb.items[i].pierce -= 1; } else { self.pb.kill(i); } }
            else if self.pb.items[i].pierce > 0 { self.pb.items[i].pierce -= 1; } else { self.pb.kill(i); }
        }
    }
    fn update_ebullets(&mut self, dt: f32) {
        let r2 = (cfg::ARENA_R + 50.).powi(2); let mut i = self.eb.n;
        while i > 0 { i -= 1; if i >= self.eb.n { continue; }
            { let (px, py) = (self.p.x, self.p.y); let b = &mut self.eb.items[i]; b.life -= dt;
                if b.acc > 0. && b.life > 3. { let a = b.vy.atan2(b.vx); let ta = (py - b.y).atan2(px - b.x); let s = hypot(b.vx, b.vy); let na = a + clamp(ang_diff(a, ta), -b.acc * dt, b.acc * dt); b.vx = na.cos() * s; b.vy = na.sin() * s; }
                if b.spin != 0. { let a = b.spin * dt; let (cc, ss) = (a.cos(), a.sin()); let vx = b.vx; b.vx = vx * cc - b.vy * ss; b.vy = vx * ss + b.vy * cc; }
                b.x += b.vx * dt; b.y += b.vy * dt; }
            let b = self.eb.items[i].clone();
            if b.life <= 0. || b.x * b.x + b.y * b.y > r2 { self.eb.kill(i); continue; }
            if self.p.dead { continue; }
            let (dx, dy) = (self.p.x - b.x, self.p.y - b.y); let d2 = dx * dx + dy * dy; let rr = b.r + self.p.r * 0.7;
            if d2 < rr * rr { if self.p.inv <= 0. && self.p.dash_t <= 0. { let n0 = self.eb.n; self.hurt_player(b.dmg); if self.eb.n != n0 { break; } self.eb.kill(i); } continue; }
            if !b.grazed { let gr = rr + 24.; if d2 < gr * gr { self.eb.items[i].grazed = true; self.p.flare = (self.p.flare + 1.6 * self.st.flare_mul).min(100.); self.score += 5.;
                let (a, bb) = (self.rr(-30., 30.), self.rr(-30., 30.)); self.part(b.x, b.y, a, bb, 0.3, 6., c::GOLD, 2.); self.snd(Sfx::Graze); } }
        }
    }
    fn separate(&mut self) {
        for i in 0..self.en.n { let (dead, kind, x, y, r, sc) = { let e = &self.en.items[i]; (e.dead, e.kind, e.x, e.y, e.r, e.scale) };
            if dead || kind.d().boss || kind == K::Crystal { continue; }
            let q = self.qa(x, y, 50.); let mut cnt = 0; let (mut ex, mut ey) = (x, y);
            for &k in &q { if cnt >= 6 { break; } if k == i { continue; } let o = &self.en.items[k]; if o.dead { continue; }
                let (dx, dy) = (ex - o.x, ey - o.y); let rr = (r * sc + o.r * o.scale) * 0.9; let d2 = dx * dx + dy * dy;
                if d2 < rr * rr && d2 > 0.01 { let d = d2.sqrt(); let push = (rr - d) * 0.5 / d; ex += dx * push; ey += dy * push; cnt += 1; } }
            self.qa_back(q); self.en.items[i].x = ex; self.en.items[i].y = ey; }
    }
    fn sweep_dead(&mut self) { let mut i = self.en.n; while i > 0 { i -= 1; if self.en.items[i].dead { self.en.kill(i); } } }

    /// Один шаг симуляции забега
    pub fn update_run(&mut self, dt: f32, real_dt: f32) {
        self.t += dt; self.run_t += dt;
        if self.combo_t > 0. { self.combo_t -= dt; if self.combo_t <= 0. { self.combo = 0; self.mult = 1.; self.combo_milestone = 0; } }
        if !self.p.dead { self.update_player(dt); }
        if self.tut.on { self.update_tut(dt); }
        self.update_director(dt);
        self.update_enemies(dt);
        self.grid_build(); self.separate();
        self.update_pbullets(dt); self.update_ebullets(dt); self.update_mines(dt);
        if !self.p.dead { self.update_picks(dt); }
        self.update_fx(dt); self.sweep_dead();
        // камера плавно следует за игроком
        let (tx, ty) = (self.p.x + self.p.vx * 0.12, self.p.y + self.p.vy * 0.12); let a = 1. - (-real_dt * 6.).exp();
        self.cam_x += (tx - self.cam_x) * a; self.cam_y += (ty - self.cam_y) * a;
        self.relic_tick(dt);
        if self.relic_pending > 0 && !self.p.dead && self.dying <= 0. { let bn = &self.banner; let busy = !bn.text.is_empty() && bn.t < bn.dur - 0.5;
            if self.level_delay <= 0. && !busy && self.boss_clear_t <= 1.5 { self.want_relic = true; } else if self.level_pending == 0 { self.level_delay -= real_dt; } }
        if self.level_pending > 0 && !self.p.dead && self.dying <= 0. { self.level_delay -= real_dt; let bn = &self.banner;
            let busy = !bn.text.is_empty() && bn.t < bn.dur - 0.5 && self.level_delay > -2.5;
            if self.level_delay <= 0. && !busy && self.run_t - self.lv_t >= cfg::LV_GAP { self.want_levelup = true; } }
    }
    pub fn update_fx_only(&mut self, dt: f32) { self.update_fx(dt); }

    // ---------- обучение ----------
    pub fn tut_progress(&self) -> f32 { (if self.tut.step == 1 { (self.kills - self.tut.base) as f32 } else { self.tut.v } / TUT_NEED[self.tut.step]).min(1.) }
    fn update_tut(&mut self, dt: f32) {
        if self.p.dead { return; }
        if self.zone >= 3 || self.boss >= 0 { self.tut.on = false; self.s.tut = true; self.dirty = true; return; } // глубже обучение не мешает
        if self.tut.fin > 0. { self.tut.fin -= dt; if self.tut.fin <= 0. { self.tut.on = false; } return; }
        self.tut.t += dt;
        if self.tut.step == 0 { self.tut.v += hypot(self.p.vx, self.p.vy) * dt; }
        if self.tut.step == 4 && self.p.flare < 100. { self.p.flare = 100.; }
        if self.tut.ok > 0. { self.tut.ok -= dt; if self.tut.ok <= 0. { self.tut_next(); } return; }
        if self.tut_progress() >= 1. { self.tut.ok = 0.6; self.snd(Sfx::PickCard); }
    }
    fn tut_next(&mut self) {
        self.tut.step += 1; self.tut.v = 0.; self.tut.t = 0.; self.tut.base = self.kills;
        if self.tut.step >= 5 { self.tut.step = 4; self.tut.fin = 3.4; self.s.tut = true; self.dirty = true; self.snd(Sfx::Level); }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)] pub enum Src { None, Chain, Burn, Nova, Static, Cleanup }
/// Ярус владыки: в бесконечном спуске боссы возвращаются новыми
pub fn boss_tier(z: u32) -> u8 { if z <= 20 { 0 } else if z <= 40 { 1 } else { 2 } }
pub fn boss_at(z: u32) -> K { let n = z / 5; if n <= 3 { [K::Boss1, K::Boss2, K::Boss3][(n - 1) as usize] } else { [K::Boss4, K::Boss1, K::Boss2, K::Boss3][((n - 4) % 4) as usize] } }
pub fn num_str(v: f32) -> String { let n = v.round() as i64; if n >= 10000 { format!("{:.1}k", n as f32 / 1000.) } else { n.to_string() } }
