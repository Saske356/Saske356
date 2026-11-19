//! Ход игры вне кадра забега: старт, выбор улучшений, итог, финал, ежедневные задания, магазин.
//! Перенесено из startRun/rollChoices/takeUpgrade/gameOver/dailyCheck веб-версии.
use crate::data::{self, c, u, K, CHARS, MUTS, SHOP, SKINS, TALENTS, UPG, U_HEAL};
use crate::game::*;
use crate::i18n::{self, t, tf};
use crate::save::Quest;

/// Локальная дата (как в браузере): год, месяц (1–12), день
pub fn local_date(offset_days: i64) -> (i32, u32, u32) {
    let now = macroquad::miniquad::date::now() as i64 + offset_days * 86400;
    unsafe { let tt = now as libc::time_t; let mut tm: libc::tm = std::mem::zeroed(); libc::localtime_r(&tt, &mut tm); (tm.tm_year + 1900, (tm.tm_mon + 1) as u32, tm.tm_mday as u32) }
}
pub fn day_str(offset_days: i64) -> String { let (y, m, d) = local_date(offset_days); format!("{y}-{m}-{d}") }

/// Два правила испытания дня (одинаковые у всех игроков в этот день)
pub fn daily_muts() -> [usize; 2] {
    let day = day_str(0); let mut seed: u32 = 7; for ch in day.bytes() { seed = seed.wrapping_mul(131).wrapping_add(ch as u32); }
    let mut rnd = || { seed = seed.wrapping_mul(1103515245).wrapping_add(12345); seed as f64 / 4294967296. };
    let a = (rnd() * MUTS.len() as f64) as usize; let mut b = (rnd() * (MUTS.len() - 1) as f64) as usize; if b >= a { b += 1; } [a, b]
}
const QDEF_ORDER: [&str; 8] = ["kills", "depth", "pearls", "boss", "chest", "flare", "runs", "combo"];

pub enum DailyMsg { Login(u32, u32) }

impl Game {
    /// Новые сутки: задания, награда за вход. Возвращает сообщение для всплывашки
    pub fn daily_check(&mut self) -> Option<DailyMsg> {
        let today = day_str(0); let yest = day_str(-1); let mut msg = None;
        let qdef = i18n::qdef();
        let d = &mut self.s.daily;
        if d.day != today || d.quests.len() != 3 {
            let mut seed: u32 = 0; for ch in today.bytes() { seed = seed.wrapping_mul(31).wrapping_add(ch as u32); }
            let mut rnd = || { seed = seed.wrapping_mul(1664525).wrapping_add(1013904223); seed as f64 / 4294967296. };
            let mut pick: Vec<&str> = vec![];
            while pick.len() < 3 { let id = QDEF_ORDER[(rnd() * 8.) as usize % 8]; if !pick.contains(&id) { pick.push(id); } }
            d.quests = pick.iter().map(|id| { let tier = (rnd() * 3.) as usize % 3; let q = qdef.iter().find(|q| q.0 == *id).unwrap();
                Quest { id: id.to_string(), need: q.1[tier], r: q.2[tier], p: 0, done: false, got: false } }).collect();
            d.day = today.clone(); d.gift = 0; d.ch_best = 0; d.ch_done = false;
        }
        if d.last != today {
            d.streak = if d.last == yest { d.streak + 1 } else { 1 }; d.last = today;
            let r = 15 * d.streak.min(7); self.s.pearls += r; msg = Some(DailyMsg::Login(d.streak, r));
        }
        self.dirty = true; msg
    }
    pub fn quests_ready(&self) -> usize { self.s.daily.quests.iter().filter(|q| q.done && !q.got).count() }

    pub fn start_run(&mut self, mode: RunMode) {
        for p in [&mut self.en.n, &mut self.pb.n, &mut self.eb.n, &mut self.parts.n, &mut self.rings.n, &mut self.texts.n, &mut self.bolts.n, &mut self.picks.n, &mut self.mines.n] { *p = 0; }
        for g in self.ghosts.iter_mut() { g.on = false; }
        self.t = 0.; self.run_t = 0.; self.zone = 1; self.zone_t = 0.; self.score = 0.; self.combo = 0; self.combo_t = 0.; self.max_combo = 0; self.mult = 1.; self.kills = 0; self.run_pearls = 0;
        self.boss = -1; self.boss_clear_t = 0.; self.bosses_killed = 0; self.shake = 0.; self.hit_stop = 0.; self.flash = 0.; self.hurt_flash = 0.; self.level_pending = 0; self.level_delay = 0.;
        self.dying = 0.; self.no_hit = true; self.synergies = 0; self.revived = false; self.cam_x = 0.; self.cam_y = 0.; self.spawn_acc = 0.; self.pack_t = 9.; self.dmg_scale = 1.; self.hp_scale = 1.;
        self.pull_t = 0.; self.combo_milestone = 0; self.victory = false; self.run_mode = mode; self.daily = mode == RunMode::Daily;
        self.hard = self.s.set.hard && self.s.wins > 0 && !self.daily; self.muts = [false; 8];
        if self.daily { for i in daily_muts() { self.muts[i] = true; } }
        self.endless = false; self.ending_t = 0.; self.ad_revived = false; self.ad_doubled = false; self.ad_rerolls = 0; self.last_earned = 0; self.ev_t = 20.; self.chal = None; self.last_ev = 9; self.chests = 0; self.lv_t = -99.;
        self.want_levelup = false; self.want_ending = false; self.want_over = false; self.crystals = 0; self.qz = Qz::default();
        if self.hard { self.dmg_scale = 1.35; }
        self.rerolls = self.s.shop_lv("reroll") as u32; self.build_decor(0); self.start_best = self.s.best_depth; self.rec_shown = false;
        let skin = SKINS.iter().position(|k| k.id == self.s.skin).unwrap_or(0);
        self.p = Player { r: 13., ang: -std::f32::consts::FRAC_PI_2, inv: 1.5, fire_t: 0.3, flare: if self.s.shop_lv("flare") > 0 { 50. } else { 0. }, level: 1, xp_next: xp_need(1),
            nova_t: 2., mine_t: 1.5, harp_t: 2., tw_t: 1., vort_t: 20., beam_tg: -1, beam_tg2: -1, skin, pal: SKINS[skin].pal, ..Default::default() };
        self.trail = [0.; 24];
        self.state = State::Play;
        self.compute_stats(); self.p.hp = self.p.max_hp;
        if self.s.tal("t_first") { let pool = [u::DMG, u::RATE, u::MULTI, u::PIERCE, u::CRIT]; let k = pool[(self.rand() * 5.) as usize % 5]; self.p.up[k] = 1; self.compute_stats(); self.p.hp = self.p.max_hp; }
        if self.s.tal("t_ward") { self.p.shield = self.p.shield.max(1); }
        self.banner(format!("100 {}", t("m")), i18n::zone(0), 0x8fd8ff, 2.6);
        self.tut = Tut { on: !self.s.tut, ..Default::default() };
        for _ in 0..6 { let (x, y) = self.offscreen_point(); self.spawn_enemy(K::Drifter, x, y, false); }
        if self.daily { let m = daily_muts(); let names: Vec<String> = m.iter().map(|&i| i18n::mutator(MUTS[i]).0).collect(); self.banner(t("dailyT"), names.join(" + "), 0xffd54f, 3.); }
    }

    /// Карты на выбор: синергии весят больше, уже взятые — чуть больше новых
    pub fn roll_choices(&mut self) -> Vec<usize> {
        let mut pool: Vec<(usize, f32)> = vec![];
        for (i, up) in UPG.iter().enumerate() { let l = self.p.up[i]; if l >= up.max { continue; }
            match up.syn { Some((a, la, b, lb)) => if self.p.up[a] >= la && self.p.up[b] >= lb { pool.push((i, 5.)); }, None => pool.push((i, if l > 0 { 1.3 } else { 1. })) } }
        let n = if self.s.tal("t_four") { 4 } else { 3 }; let mut out = vec![];
        while out.len() < n && !pool.is_empty() { let tot: f32 = pool.iter().map(|p| p.1).sum(); let mut r = self.rand() * tot; let mut k = 0;
            while k < pool.len() - 1 { r -= pool[k].1; if r <= 0. { break; } k += 1; } out.push(pool[k].0); pool.remove(k); }
        if out.is_empty() { out.push(U_HEAL); }
        out
    }
    /// Взять улучшение. true — есть ещё выборы
    pub fn take_upgrade(&mut self, i: usize) -> bool {
        self.snd(Sfx::PickCard);
        let syn = i != U_HEAL && UPG[i].syn.is_some();
        if i == U_HEAL { self.p.hp = (self.p.hp + self.p.max_hp * 0.5).min(self.p.max_hp); self.score += 1000.; }
        else { self.p.up[i] += 1; if i == u::HP { self.p.hp += self.p.max_hp * 0.15; }
            if syn { self.synergies += 1; self.unlock("syn"); if self.synergies >= 3 { self.unlock("syn3"); } self.banner(t("synergy"), i18n::upg(UPG[i].id).0, 0xffd54f, 2.2); } }
        self.compute_stats();
        let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 120., 0.5, if syn { c::GOLD } else { c::CYAN }, 5.);
        if self.level_pending > 0 { self.level_pending -= 1; true } else { self.state = State::Play; self.lv_t = self.run_t; false }
    }
    pub fn open_level_up(&mut self) { self.state = State::LevelUp; self.level_pending = self.level_pending.saturating_sub(1); self.want_levelup = false; self.snd(Sfx::Level); self.vibrate(25); }

    /// Итог забега: жемчуг, рекорды, награды. Возвращает (заработано, новый рекорд)
    pub fn game_over(&mut self) -> (u32, bool) {
        self.quest_add("runs", 1);
        self.state = State::Over;
        let earned = ((self.run_pearls as f32 + (self.score / 1500.).floor() as f32 + (self.zone as f32 - 1.) * 2. + self.bosses_killed as f32 * 15.)
            * (1. + 0.25 * self.lv(u::GREED) as f32) * if self.hard { 1.5 } else { 1. } * (1. + 0.1 * self.tl("t_pearl")) * if self.daily { 2. } else { 1. }).round() as u32;
        self.last_earned = earned;
        if self.daily { let z = self.zone; let d = &mut self.s.daily; d.ch_best = d.ch_best.max(z * 100);
            if z >= 5 && !d.ch_done { d.ch_done = true; self.s.pearls += 150; self.toast(t("dailyWin"), format!("+150 {}", t("pearlsGen"))); } }
        let s = &mut self.s;
        s.pearls += earned; s.total_pearls += earned as u64; s.runs += 1; s.total_kills += self.kills as u64;
        let rec = self.score as u64 > s.best; if rec { s.best = self.score as u64; }
        s.best_depth = s.best_depth.max(self.zone * 100); s.best_kills = s.best_kills.max(self.kills); s.best_combo = s.best_combo.max(self.max_combo);
        s.best_level = s.best_level.max(self.p.level); s.best_syn = s.best_syn.max(self.synergies);
        self.unlock("first"); if self.s.total_kills >= 5000 { self.unlock("kill5k"); } if self.s.total_pearls >= 300 { self.unlock("rich"); }
        self.dirty = true; (earned, rec && self.score > 0.)
    }
    /// Победа над Сердцем Бездны: всё, что лежит, собирается само
    pub fn start_ending(&mut self) -> bool {
        self.state = State::Ending; self.snd(Sfx::Flare); self.vibrate(120); self.eb.n = 0; self.want_ending = false;
        for i in 0..self.picks.n { let pk = self.picks.items[i].clone(); if pk.kind <= 2 { self.add_xp(pk.val); } else if pk.kind == 3 { self.run_pearls += 1; } }
        self.picks.n = 0;
        self.s.wins += 1; let first = !self.s.skins.contains_key("dawn"); self.s.skins.insert("dawn".into(), 1); self.dirty = true; first
    }
    pub fn continue_endless(&mut self) {
        self.state = State::Play; self.endless = true; self.p.inv = 2.5; self.p.hp = self.p.max_hp; self.level_delay = 1.5; self.ending_t = 0.; self.boss_clear_t = 0.;
        self.next_zone(); let z = self.zone; self.banner(t("endlessB"), format!("{} {} · {}", z * 100, t("m"), t("endlessBs")), 0xffd54f, 3.);
    }
    pub fn revive_ad(&mut self) {
        self.ad_revived = true; self.dying = 0.; self.p.dead = false; self.p.hp = (self.p.max_hp * 0.6).ceil(); self.p.inv = 3.; self.state = State::Play;
        self.do_flare(true); self.banner(t("secondChance"), t("secondChanceS"), 0xffd54a, 2.2);
    }
    /// Сдаться: искра гаснет, как при гибели
    pub fn give_up(&mut self) { self.state = State::Play; self.p.hp = 0.; self.start_dying(); }

    // ---------- магазин ----------
    pub fn buy_shop(&mut self, i: usize) -> bool { let l = self.s.shop_lv(SHOP[i].id); let cost = data::shop_cost(i, l);
        if l < SHOP[i].max && self.s.pearls >= cost { self.s.pearls -= cost; self.s.shop.insert(SHOP[i].id.into(), l + 1); self.snd(Sfx::Pearl); self.dirty = true; true } else { false } }
    pub fn pick_char(&mut self, i: usize) -> bool { let c = &CHARS[i];
        if !self.s.chars.contains_key(c.id) { if self.s.pearls < c.cost { return false; } self.s.pearls -= c.cost; self.s.chars.insert(c.id.into(), 1); self.snd(Sfx::Ach); } else { self.snd(Sfx::Click); }
        self.s.ch = c.id.into(); self.dirty = true; true }
    pub fn pick_skin(&mut self, i: usize) -> bool { let k = &SKINS[i];
        if !self.s.skins.contains_key(k.id) { if k.win || self.s.pearls < k.cost { return false; } self.s.pearls -= k.cost; self.s.skins.insert(k.id.into(), 1); self.snd(Sfx::Ach); } else { self.snd(Sfx::Click); }
        self.s.skin = k.id.into(); self.p.skin = i; self.p.pal = k.pal; self.dirty = true; true }
    pub fn tal_open(&self, i: usize) -> bool { let br = TALENTS[i].br; let first = TALENTS.iter().position(|x| x.br == br).unwrap(); i == first || self.s.tal(TALENTS[i - 1].id) }
    pub fn buy_tal(&mut self, i: usize) -> bool { let tl = &TALENTS[i];
        if !self.s.tal(tl.id) && self.tal_open(i) && self.s.pearls >= tl.cost { self.s.pearls -= tl.cost; self.s.tal.insert(tl.id.into(), 1); self.snd(Sfx::Ach); self.dirty = true; true } else { false } }
    pub fn claim_quest(&mut self, k: usize) { if let Some(q) = self.s.daily.quests.get_mut(k) { if q.done && !q.got { q.got = true; let r = q.r; self.s.pearls += r; self.snd(Sfx::Pearl); self.vibrate(25); self.dirty = true; } } }

    /// Прогресс накопительных наград: (текущее, цель)
    pub fn ach_progress(&self, id: &str) -> Option<(u64, u64)> {
        let s = &self.s;
        Some(match id { "kill100" => (s.best_kills as u64, 100), "kill500" => (s.best_kills as u64, 500), "kill5k" => (s.total_kills, 5000), "combo50" => (s.best_combo as u64, 50),
            "combo150" => (s.best_combo as u64, 150), "depth500" => (s.best_depth as u64, 500), "lvl20" => (s.best_level as u64, 20), "flare10" => (s.flares as u64, 10),
            "rich" => (s.total_pearls, 300), "syn3" => (s.best_syn as u64, 3), _ => return None })
    }
    pub fn mode_tf(&self) -> String { tf("pauseInfo", &[&(self.zone * 100).to_string(), &self.p.level.to_string(), &i18n::fmt_num(self.score as i64)]) }
}
