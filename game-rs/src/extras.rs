//! 4.1: питомцы, события выходных, мастерство искр, колесо удачи.
use crate::data::{c, K, TAU};
use crate::game::boss_at;
use crate::game::*;
use crate::i18n;

// ---------------- питомцы ----------------
pub struct PetDef { pub id: &'static str, pub spr: &'static str, pub cost: u32, pub col: u8, pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str) }
pub static PETS: [PetDef; 3] = [
    PetDef { id: "fry", spr: "fry", cost: 600, col: c::EMER, ru: ("Малёк", "Собирает опыт и жемчуг издалека и бросается на врагов"), en: ("Fry", "Pulls in XP and pearls from afar and lunges at foes") },
    PetDef { id: "wisp", spr: "wisp", cost: 1200, col: c::AMBER, ru: ("Огонёк", "Стреляет огненными искрами по ближайшему врагу"), en: ("Wisp", "Shoots fiery sparks at the nearest foe") },
    PetDef { id: "jelly", spr: "jelly", cost: 2000, col: c::JELLY, ru: ("Медузка", "Лечит и время от времени дарит щит на один удар"), en: ("Jellyling", "Heals you and now and then grants a one-hit shield") },
];
pub const PET_MAX: u8 = 5;
pub fn pet_txt(i: usize) -> (&'static str, &'static str) { if i18n::is_en() { PETS[i].en } else { PETS[i].ru } }
/// Цена: покупка — cost, каждый следующий уровень — дороже
pub fn pet_cost(i: usize, lvl: u8) -> u32 { if lvl == 0 { PETS[i].cost } else { (PETS[i].cost as f32 * 0.6 * (lvl as f32 + 1.).powf(1.4)).round() as u32 } }

// ---------------- события выходных ----------------
pub struct EventDef { pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str), pub col: u32 }
pub static EVENTS: [EventDef; 4] = [
    EventDef { ru: ("Ночь медуз", "Медузы повсюду · жемчуг ×2"), en: ("Jelly Night", "Jellies everywhere · pearls ×2"), col: 0xd59bff },
    EventDef { ru: ("Нашествие крабов", "Крабы со всех сторон · жемчуг ×1.5, опыт +30%"), en: ("Crab Invasion", "Crabs from every side · pearls ×1.5, +30% XP"), col: 0xff8a6a },
    EventDef { ru: ("Золотая лихорадка", "Жемчужницы чаще · жемчуг ×2"), en: ("Gold Rush", "More pearl oysters · pearls ×2"), col: 0xffd54f },
    EventDef { ru: ("Буря элит", "Элиты втрое чаще, с каждой — 2 жемчужины"), en: ("Elite Storm", "Elites three times as often, each drops 2 pearls"), col: 0x7fe8ff },
];
/// Событие сегодня: только по субботам и воскресеньям, каждую неделю — следующее
pub fn event_today() -> Option<usize> {
    let now = macroquad::miniquad::date::now() as i64;
    let (wday, yday) = unsafe { let tt = now as libc::time_t; let mut tm: libc::tm = std::mem::zeroed(); libc::localtime_r(&tt, &mut tm); (tm.tm_wday, tm.tm_yday) };
    if std::env::var("SVET_EVENT").is_ok() { return std::env::var("SVET_EVENT").ok().and_then(|v| v.parse().ok()); }
    if wday == 0 || wday == 6 { Some(((yday / 7) as usize) % EVENTS.len()) } else { None }
}
pub fn event_txt(i: usize) -> (&'static str, &'static str) { if i18n::is_en() { EVENTS[i].en } else { EVENTS[i].ru } }
pub const EV_JELLY: u8 = 1; pub const EV_CRAB: u8 = 2; pub const EV_GOLD: u8 = 3; pub const EV_ELITE: u8 = 4;

// ---------------- мастерство искр ----------------
/// Очки мастерства = сумма достигнутых зон забегов этой искрой. Уровень n требует 15·n(n+1)/2 очков (макс. 10).
pub fn mastery_lvl(pts: u32) -> u8 { let mut l = 0u32; while l < 10 && pts >= 15 * (l + 1) * (l + 2) / 2 { l += 1; } l as u8 }
pub fn mastery_next(l: u8) -> u32 { let l = l as u32; 15 * (l + 1) * (l + 2) / 2 }
pub fn mastery_desc(l: u8) -> String {
    let en = i18n::is_en();
    let mut v = vec![if en { format!("+{}% damage", l as u32 * 2) } else { format!("+{}% к урону", l as u32 * 2) }];
    if l >= 5 { v.push(if en { "second attack".into() } else { "вторая атака".into() }); }
    if l >= 8 { v.push(if en { "+10% fire rate".into() } else { "+10% скорострельности".into() }); }
    if l >= 10 { v.push(if en { "+1 projectile".into() } else { "+1 снаряд".into() }); }
    v.join(", ")
}

// ---------------- колесо удачи ----------------
/// Призы: (тип, количество, вес). Тип 0 — жемчуг, 1 — реликвия на старт следующего забега, 2 — перевыбор на следующий забег
pub static WHEEL: [(u8, u32, f32); 8] = [(0, 20, 3.), (0, 40, 2.5), (1, 1, 0.8), (0, 80, 1.6), (2, 1, 1.4), (0, 30, 2.8), (0, 150, 0.6), (0, 60, 2.)];
pub const WHEEL_AD_MAX: u32 = 3;
pub fn wheel_label(k: usize) -> String {
    let (t, n, _) = WHEEL[k]; let en = i18n::is_en();
    match t { 0 => format!("{n}"), 1 => if en { "Relic".into() } else { "Реликвия".into() }, _ => if en { "Reroll".into() } else { "Перевыбор".into() } }
}

impl Game {
    // ---------- питомец ----------
    pub fn pet_idx(&self) -> Option<usize> { PETS.iter().position(|p| p.id == self.s.pet).filter(|&i| self.s.pets.get(PETS[i].id).copied().unwrap_or(0) > 0) }
    pub fn pet_lvl(&self) -> u8 { self.pet_idx().map(|i| self.s.pets.get(PETS[i].id).copied().unwrap_or(0)).unwrap_or(0) }
    pub fn buy_pet(&mut self, i: usize) -> bool {
        let l = self.s.pets.get(PETS[i].id).copied().unwrap_or(0); if l >= PET_MAX { return false; }
        let cost = pet_cost(i, l); if self.s.pearls < cost { return false; }
        self.s.pearls -= cost; self.s.pets.insert(PETS[i].id.into(), l + 1); if l == 0 { self.s.pet = PETS[i].id.into(); }
        self.snd(Sfx::Ach); self.dirty = true; true
    }
    pub fn pick_pet(&mut self, i: usize) { if self.s.pets.get(PETS[i].id).copied().unwrap_or(0) > 0 { self.s.pet = if self.s.pet == PETS[i].id { String::new() } else { PETS[i].id.into() }; self.snd(Sfx::Click); self.dirty = true; } }
    /// бонусы питомца к статам — в конце compute_stats
    pub fn pet_stats(&mut self) {
        let l = self.pet_lvl() as f32; if l <= 0. { return; }
        match self.pet_idx() { Some(0) => self.st.magnet *= 1. + 0.15 * l, Some(2) => self.st.regen += 0.3 * l, _ => {} }
    }
    /// каждый кадр: питомец плывёт за искрой и действует
    pub fn pet_tick(&mut self, dt: f32) {
        let Some(pi) = self.pet_idx() else { return }; let l = self.pet_lvl() as f32;
        // плывёт за плечом, с запаздыванием
        let a = self.p.ang + 2.4 + (self.t * 1.3).sin() * 0.4; let (tx, ty) = (self.p.x + a.cos() * 46., self.p.y + a.sin() * 46.);
        if self.pet.dash > 0. { self.pet.dash -= dt; let k = 1. - (-dt * 10.).exp(); self.pet.x += (self.pet.tx - self.pet.x) * k; self.pet.y += (self.pet.ty - self.pet.y) * k; }
        else { let k = 1. - (-dt * 4.).exp(); let (ox, oy) = (self.pet.x, self.pet.y); self.pet.x += (tx - self.pet.x) * k; self.pet.y += (ty - self.pet.y) * k;
            let (vx, vy) = (self.pet.x - ox, self.pet.y - oy); if vx * vx + vy * vy > 0.01 { self.pet.ang = vy.atan2(vx); } }
        self.pet.t -= dt;
        match pi {
            0 => if self.pet.t <= 0. { self.pet.t = 5. - 0.5 * l; let tg = self.nearest_enemy(self.pet.x, self.pet.y, 320.);
                if tg >= 0 { let i = tg as usize; let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); self.pet.tx = ex; self.pet.ty = ey; self.pet.dash = 0.35; self.pet.ang = (ey - self.pet.y).atan2(ex - self.pet.x);
                    self.damage_enemy(i, self.st.dmg * (2. + l), false, f32::NAN, 0., 0., Src::None); self.ring(ex, ey, 4., 40., 0.25, c::EMER, 3.); } },
            1 => if self.pet.t <= 0. { self.pet.t = 1.05 - 0.1 * l; let tg = self.nearest_enemy(self.pet.x, self.pet.y, 480.);
                if tg >= 0 { let (ex, ey) = (self.en.items[tg as usize].x, self.en.items[tg as usize].y); let a = (ey - self.pet.y).atan2(ex - self.pet.x); let (px, py) = (self.pet.x, self.pet.y);
                    if let Some(b) = self.fire_pb(px, py, a, self.st.dmg * (0.35 + 0.08 * l), false) { let bb = &mut self.pb.items[b]; bb.form = 7; bb.life = 0.8; bb.pierce = 0; bb.bounce = 0; } } },
            _ => if self.pet.t <= 0. { self.pet.t = 14. - 1.5 * l; if self.p.shield < 2 { self.p.shield += 1; let (x, y) = (self.p.x, self.p.y); self.ring(x, y, self.p.r, self.p.r + 24., 0.4, c::JELLY, 4.); self.snd(Sfx::Graze); } },
        }
    }

    // ---------- события ----------
    pub fn event_on(&self) -> u8 { if self.run_mode == RunMode::Normal { self.event } else { 0 } }
    /// замена вида врага во время события
    pub fn event_kind(&mut self, k: K) -> K {
        match self.event_on() { EV_JELLY if self.rand() < 0.55 => K::Jelly, EV_CRAB if self.zone >= 2 && self.rand() < 0.4 && self.count_kind(K::Crab) < 10 => K::Crab, _ => k }
    }
    pub fn event_pearl_mul(&self) -> f32 { match self.event_on() { EV_JELLY | EV_GOLD => 2., EV_CRAB => 1.5, _ => 1. } }

    // ---------- мастерство ----------
    pub fn mastery(&self) -> u8 { mastery_lvl(self.s.mastery.get(&self.s.ch).copied().unwrap_or(0)) }
    pub fn mastery_stats(&mut self) {
        let l = self.mastery() as f32; self.st.dmg *= 1. + 0.02 * l; if l >= 8. { self.st.rate *= 1.1; } if l >= 10. { self.st.multi += 1; }
        self.st.orb_dmg = self.st.dmg * 0.9;
    }
    /// вторая атака (мастерство 5+): каждый 5-й залп — кольцо из 8 снарядов своей формы
    pub fn mastery_shot(&mut self, px: f32, py: f32) {
        if self.mastery() < 5 { return; } self.p.mast_n += 1; if self.p.mast_n % 5 != 0 { return; }
        let o = self.rand() * TAU; for k in 0..8 { self.fire_pb(px, py, o + k as f32 * TAU / 8., self.st.dmg * 0.6, false); }
        self.ring(px, py, 6., 50., 0.25, self.p.pal, 3.);
    }
    /// конец забега: очки мастерства текущей искре
    pub fn mastery_gain(&mut self) -> Option<u8> {
        if self.god { return None; }
        let before = self.mastery(); let e = self.s.mastery.entry(self.s.ch.clone()).or_insert(0); *e += self.zone; let after = self.mastery();
        if after > before { Some(after) } else { None }
    }
}


// ---------------- Уровни Бездны (вознесение) ----------------
pub const ABYSS_MAX: u8 = 20;
/// Проклятие, добавляемое на уровне n (1..=20); действуют все уровни до выбранного включительно
pub fn abyss_curse(n: u8) -> (&'static str, &'static str) {
    match n {
        1 => ("Враги на 10% крепче", "Foes 10% tougher"), 2 => ("Враги бьют на 10% сильнее", "Foes hit 10% harder"),
        3 => ("Лечение от убийств −30%", "Healing from kills −30%"), 4 => ("Элиты в 1.5 раза чаще", "Elites 1.5× more often"),
        5 => ("Владыки на 25% крепче", "Lords 25% tougher"), 6 => ("Враги на 10% быстрее", "Foes 10% faster"),
        7 => ("Пули врагов на 15% быстрее", "Enemy bullets 15% faster"), 8 => ("Жемчужницы реже", "Fewer pearl oysters"),
        9 => ("Враги ещё на 15% крепче", "Foes another 15% tougher"), 10 => ("Владыки сразу в облике бездны", "Lords start in abyss form"),
        11 => ("Здоровье на старте −15%", "Starting health −15%"), 12 => ("Рывок перезаряжается на 25% дольше", "Dash recharges 25% slower"),
        13 => ("Враги ещё на 10% сильнее", "Foes another 10% stronger"), 14 => ("Улучшений на выбор на одно меньше", "One fewer upgrade choice"),
        15 => ("Владыки ещё на 25% крепче", "Lords another 25% tougher"), 16 => ("Все элиты с особыми свойствами", "Every elite has a trait"),
        17 => ("Лечение от убийств ещё −30%", "Healing from kills another −30%"), 18 => ("Враги ещё на 15% крепче", "Foes another 15% tougher"),
        19 => ("Враги ещё на 15% сильнее", "Foes another 15% stronger"), _ => ("Истинная Бездна: всё вместе", "True Abyss: everything at once"),
    }
}
pub fn abyss_txt(n: u8) -> &'static str { let c = abyss_curse(n); if i18n::is_en() { c.1 } else { c.0 } }
/// Награда за первую победу на уровне n
pub fn abyss_reward(n: u8) -> u32 { 150 + 75 * n as u32 }

impl Game {
    #[inline] pub fn ab(&self, n: u8) -> bool { self.abyss >= n }
    pub fn abyss_hp(&self) -> f32 { let mut k = 1.; if self.ab(1) { k *= 1.1; } if self.ab(9) { k *= 1.15; } if self.ab(18) { k *= 1.15; } k }
    pub fn abyss_dmg(&self) -> f32 { let mut k = 1.; if self.ab(2) { k *= 1.1; } if self.ab(13) { k *= 1.1; } if self.ab(19) { k *= 1.15; } k }
    pub fn abyss_boss(&self) -> f32 { let mut k = 1.; if self.ab(5) { k *= 1.25; } if self.ab(15) { k *= 1.25; } k }
    pub fn abyss_heal(&self) -> f32 { let mut k = 1.; if self.ab(3) { k *= 0.7; } if self.ab(17) { k *= 0.7; } k }
}

// ---------------- опасности зон ----------------
pub const HZ_CURRENT: u8 = 1; pub const HZ_GEYSER: u8 = 2; pub const HZ_DARK: u8 = 3; pub const HZ_CRYSTAL: u8 = 4;
/// Опасность зоны (по номеру зоны 1..): течения, гейзеры, тьма, взрывные кристаллы
pub fn hazard_of(zone: u32) -> u8 { match (zone.max(1) - 1) % 15 { 3 | 11 => HZ_CURRENT, 7 | 8 | 13 => HZ_GEYSER, 10 | 14 => HZ_DARK, 2 | 9 => HZ_CRYSTAL, _ => 0 } }
pub fn hazard_txt(h: u8) -> &'static str { let en = i18n::is_en(); match h {
    HZ_CURRENT => if en { "Currents carry you" } else { "Течения сносят" }, HZ_GEYSER => if en { "Geysers erupt — watch the circles" } else { "Гейзеры — следи за кругами" },
    HZ_DARK => if en { "Darkness — only your light shines" } else { "Тьма — светишь только ты" }, HZ_CRYSTAL => if en { "Shoot the crystals — they explode" } else { "Стреляй в кристаллы — они взрываются" }, _ => "" } }
#[derive(Clone, Copy, Default)] pub struct Geyser { pub x: f32, pub y: f32, pub t: f32 }
#[derive(Clone, Copy, Default)] pub struct BoomCrystal { pub x: f32, pub y: f32, pub hp: f32, pub ph: f32 }

impl Game {
    pub fn hazard(&self) -> u8 { if self.boss >= 0 || self.run_mode == RunMode::Dash { 0 } else { self.region_hazard(hazard_of(self.zone)) } }
    /// направление течения медленно поворачивается
    pub fn current_dir(&self) -> (f32, f32) { let a = self.t * 0.07 + self.zone as f32; (a.cos(), a.sin()) }
    pub fn hazard_tick(&mut self, dt: f32) {
        let h = self.hazard();
        if h != HZ_GEYSER { self.geysers.clear(); }
        if h != HZ_CRYSTAL { self.bcr.clear(); }
        match h {
            HZ_CURRENT => { let (cx, cy) = self.current_dir(); self.p.x += cx * 55. * dt; self.p.y += cy * 55. * dt;
                for i in 0..self.eb.n { let b = &mut self.eb.items[i]; b.x += cx * 30. * dt; b.y += cy * 30. * dt; }
                if self.quality > 0 && self.rand() < dt * 18. { let (x, y) = (self.cam_x + self.rr(-self.vw, self.vw), self.cam_y + self.rr(-self.vh, self.vh)); self.part(x, y, cx * 160., cy * 160., 0.9, 5., c::ICE, 0.); } }
            HZ_GEYSER => { self.hz_t -= dt;
                if self.hz_t <= 0. { self.hz_t = self.rr(1.6, 2.6); let (a, d) = (self.rand() * TAU, self.rr(40., 220.)); let (x, y) = (self.p.x + a.cos() * d, self.p.y + a.sin() * d); self.geysers.push(Geyser { x, y, t: 1.3 }); }
                let mut k = 0; while k < self.geysers.len() { self.geysers[k].t -= dt; let g = self.geysers[k];
                    if g.t <= 0. { let r = 75.; self.ring(g.x, g.y, 10., r, 0.45, c::FIRE, 6.); self.burst(g.x, g.y, 18, c::FIRE, 260., 9., 0.6); self.snd(Sfx::Boom(false)); self.shake(4.);
                        if (self.p.x - g.x).powi(2) + (self.p.y - g.y).powi(2) < (r + self.p.r).powi(2) { self.hurt_player(16. * self.dmg_scale); }
                        let q = self.qa(g.x, g.y, r + 40.); for &i in &q { if !self.en.items[i].dead { let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); if (ex - g.x).powi(2) + (ey - g.y).powi(2) < r * r { self.damage_enemy(i, self.st.dmg * 4., false, f32::NAN, 0., -200., Src::None); } } } self.qa_back(q);
                        self.geysers.swap_remove(k); } else { k += 1; } } }
            HZ_CRYSTAL => { while self.bcr.len() < 4 { let (a, d) = (self.rand() * TAU, self.rr(220., 420.)); let (x, y) = (self.p.x + a.cos() * d, self.p.y + a.sin() * d); if x * x + y * y > (crate::data::cfg::ARENA_R - 80.).powi(2) { continue; } let ph = self.rand() * TAU; self.bcr.push(BoomCrystal { x, y, hp: 3., ph }); }
                let mut k = 0; while k < self.bcr.len() { let cr = self.bcr[k]; let mut hit = false;
                    let mut j = self.pb.n; while j > 0 { j -= 1; let b = &self.pb.items[j]; if (b.x - cr.x).powi(2) + (b.y - cr.y).powi(2) < 22. * 22. { self.pb.kill(j); hit = true; break; } }
                    if hit { self.bcr[k].hp -= 1.; if self.bcr[k].hp <= 0. { let r = 130.; self.ring(cr.x, cr.y, 10., r, 0.5, c::ICE, 7.); self.burst(cr.x, cr.y, 26, c::ICE, 320., 9., 0.7); self.snd(Sfx::Boom(false)); self.shake(5.);
                            let q = self.qa(cr.x, cr.y, r + 40.); for &i in &q { if !self.en.items[i].dead { let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); let (dx, dy) = (ex - cr.x, ey - cr.y); let d = (dx * dx + dy * dy).sqrt(); if d < r { let dd = d.max(1.); self.damage_enemy(i, self.st.dmg * 8., true, f32::NAN, dx / dd * 300., dy / dd * 300., Src::Nova); } } } self.qa_back(q);
                            self.bcr.swap_remove(k); continue; } }
                    k += 1; } }
            _ => {}
        }
    }
}

// ---------------- карта океана: регионы ----------------
pub struct RegionDef { pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str), pub cost: u32, pub col: u32,
    pub grounds: &'static [usize], pub bosses: [K; 6], pub foes: [K; 3], pub hazard: u8, pub pearl: f32, pub pos: (f32, f32) }
pub static REGIONS: [RegionDef; 4] = [
    RegionDef { ru: ("Бездна", "Основной спуск: все зоны и владыки"), en: ("The Abyss", "The main descent: every zone and lord"), cost: 0, col: 0x5fe9ff,
        grounds: &[], bosses: [K::Boss1, K::Boss2, K::Boss4, K::Boss5, K::Boss6, K::Boss3], foes: [K::Drifter, K::Drifter, K::Drifter], hazard: 0, pearl: 1., pos: (0.5, 0.62) },
    RegionDef { ru: ("Коралловое море", "Медузы, кальмары и иглы среди кораллов · жемчуг ×1.2"), en: ("Coral Sea", "Jellies, squids and needlefish among corals · pearls ×1.2"), cost: 8, col: 0xff8ad8,
        grounds: &[1, 2, 0, 6, 12, 1, 2, 9], bosses: [K::Boss2, K::Boss7, K::Boss1, K::Boss5, K::Boss2, K::Boss3], foes: [K::Jelly, K::Squid, K::Dart], hazard: HZ_CRYSTAL, pearl: 1.2, pos: (0.24, 0.3) },
    RegionDef { ru: ("Ледяной шельф", "Скаты, крабы и ежи, течения во льдах · жемчуг ×1.35"), en: ("Ice Shelf", "Rays, crabs and urchins, currents in the ice · pearls ×1.35"), cost: 20, col: 0x9fe6ff,
        grounds: &[7, 10, 3, 7, 11, 10], bosses: [K::Boss6, K::Boss4, K::Boss7, K::Boss6, K::Boss8, K::Boss3], foes: [K::Ray, K::Crab, K::Urchin], hazard: HZ_CURRENT, pearl: 1.35, pos: (0.76, 0.28) },
    RegionDef { ru: ("Вулканический разлом", "Бомберы и фонарщики, гейзеры в лаве · жемчуг ×1.5"), en: ("Volcanic Rift", "Bombers and lanternfish, geysers in lava · pearls ×1.5"), cost: 40, col: 0xff8a40,
        grounds: &[8, 13, 14, 5, 8, 13], bosses: [K::Boss5, K::Boss1, K::Boss8, K::Boss4, K::Boss5, K::Boss3], foes: [K::Bomber, K::Lantern, K::Urchin], hazard: HZ_GEYSER, pearl: 1.5, pos: (0.5, 0.86) },
];
pub fn region_txt(i: usize) -> (&'static str, &'static str) { if i18n::is_en() { REGIONS[i].en } else { REGIONS[i].ru } }

impl Game {
    pub fn region_on(&self) -> usize { if self.run_mode == RunMode::Normal { (self.region as usize).min(REGIONS.len() - 1) } else { 0 } }
    /// фон зоны с учётом региона
    pub fn ground_idx(&self, zi: usize) -> usize { let r = &REGIONS[self.region_on()]; if r.grounds.is_empty() { zi } else { r.grounds[zi % r.grounds.len()] } }
    /// владыка зоны (5, 10, … 30) с учётом региона; дальше — общий круг
    pub fn boss_for(&self, z: u32) -> K { let r = self.region_on(); let n = z / 5; if r > 0 && n >= 1 && n <= 6 { REGIONS[r].bosses[(n - 1) as usize] } else { boss_at(z) } }
    /// подмена вида врага под регион (35%)
    pub fn region_kind(&mut self, k: K) -> K { let r = self.region_on(); if r == 0 || self.rand() > 0.35 { return k; } let f = REGIONS[r].foes; f[(self.rand() * 3.) as usize % 3] }
    pub fn region_hazard(&self, base: u8) -> u8 { let r = self.region_on(); if base == 0 && r > 0 && self.zone % 2 == 0 { REGIONS[r].hazard } else { base } }
}

// ---------------- 4.3: напоминания ----------------
/// Местное время «через d дней в hh:mm» → unix-секунды (mktime сам переносит через конец месяца)
fn local_at(now: i64, d: i32, hh: i32, mm: i32) -> (i64, i32) {
    unsafe { let tt = now as libc::time_t; let mut tm: libc::tm = std::mem::zeroed(); libc::localtime_r(&tt, &mut tm);
        tm.tm_mday += d; tm.tm_hour = hh; tm.tm_min = mm; tm.tm_sec = 0; tm.tm_isdst = -1; let t = libc::mktime(&mut tm) as i64; (t, tm.tm_yday) }
}
/// План локальных напоминаний: не больше трёх, каждое перезаписывается при следующем заходе в игру.
/// 1) завтра в 18:30 — колесо удачи и награда за вход; 2) ближайшая суббота 11:00 — событие выходных; 3) через 3 дня в 19:00 — «Люмен скучает».
/// Если игрок заходит каждый день, напоминания всё время сдвигаются вперёд и не приходят.
pub fn reminder_plan(s: &crate::save::Save) -> String {
    if !s.set.notify { return String::new(); }
    let en = i18n::is_en(); let now = macroquad::miniquad::date::now() as i64; let mut v = vec![];
    let (t1, _) = local_at(now, 1, 18, 30);
    v.push((t1, if en { "The Wheel of Fortune is ready".to_string() } else { "Колесо удачи готово".to_string() },
        if en { "Your daily reward and a free spin are waiting. The abyss never sleeps!".to_string() } else { "Ежедневная награда и бесплатное вращение ждут. Бездна не дремлет!".to_string() }));
    let wday = unsafe { let tt = now as libc::time_t; let mut tm: libc::tm = std::mem::zeroed(); libc::localtime_r(&tt, &mut tm); tm.tm_wday };
    let mut dd = (6 - wday + 7) % 7; if dd == 0 { dd = 7; }
    let (t2, yd) = local_at(now, dd, 11, 0); let ev = ((yd / 7) as usize) % EVENTS.len(); let (n, d) = event_txt(ev);
    if t2 - now > 6 * 3600 { v.push((t2, if en { format!("Weekend event: {n}") } else { format!("Выходные в Бездне: {n}") }, d.to_string())); }
    let (t3, _) = local_at(now, 3, 19, 0);
    v.push((t3, if en { "Lumen misses you".to_string() } else { "Люмен скучает".to_string() },
        if en { format!("The ocean is growing dark again… Come back and dive deeper than {} m!", s.best_depth) } else { format!("Океан снова темнеет… Вернись и нырни глубже своего рекорда — {} м!", s.best_depth) }));
    v.sort_by_key(|x| x.0);
    v.iter().map(|(t, a, b)| format!("{t}|{}|{}", a.replace(['|', '\n'], " "), b.replace(['|', '\n'], " "))).collect::<Vec<_>>().join("\n")
}
pub fn sync_reminders(s: &crate::save::Save) { crate::platform::set_reminders(&reminder_plan(s), if i18n::is_en() { "Reminders" } else { "Напоминания" }); }

// ---------------- 4.3: шлейфы и эффекты гибели (за жемчуг, только внешний вид) ----------------
pub struct FxDef { pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str), pub cost: u32, pub col: u8 }
pub static TRAILS: [FxDef; 7] = [
    FxDef { ru: ("Свечение", "Обычный след твоего цвета"), en: ("Glow", "The usual trail in your color"), cost: 0, col: c::CYAN },
    FxDef { ru: ("Пузыри", "За тобой поднимаются пузырьки"), en: ("Bubbles", "Bubbles rise behind you"), cost: 400, col: c::ICE },
    FxDef { ru: ("Звёздная пыль", "Золотые искорки мерцают в следе"), en: ("Stardust", "Golden sparkles twinkle in your wake"), cost: 600, col: c::GOLD },
    FxDef { ru: ("Радуга", "След переливается всеми цветами"), en: ("Rainbow", "The trail shimmers in every color"), cost: 800, col: c::EMER },
    FxDef { ru: ("Пламя", "Огненный хвост и искры"), en: ("Flame", "A fiery tail with embers"), cost: 1000, col: c::FIRE },
    FxDef { ru: ("Молнии", "Разряды пробегают по следу"), en: ("Lightning", "Sparks of electricity run along the trail"), cost: 1300, col: c::CYAN },
    FxDef { ru: ("Тень", "Клубы фиолетовой тьмы"), en: ("Shadow", "Wisps of violet darkness"), cost: 1600, col: c::PURP },
];
pub static DEATHS: [FxDef; 6] = [
    FxDef { ru: ("Вспышка", "Обычная гибель врагов"), en: ("Flash", "The usual enemy death"), cost: 0, col: c::WHITE },
    FxDef { ru: ("Фейерверк", "Враги разлетаются разноцветным салютом"), en: ("Fireworks", "Foes burst into colorful fireworks"), cost: 500, col: c::CORAL },
    FxDef { ru: ("Пузыри", "Враги лопаются облаком пузырей"), en: ("Bubbles", "Foes pop into a cloud of bubbles"), cost: 700, col: c::ICE },
    FxDef { ru: ("Звездопад", "Золотые звёзды разлетаются кольцом"), en: ("Starfall", "Golden stars scatter in a ring"), cost: 900, col: c::GOLD },
    FxDef { ru: ("Чёрная дыра", "Враг схлопывается в точку"), en: ("Black hole", "The foe collapses into a point"), cost: 1200, col: c::PURP },
    FxDef { ru: ("Кристаллы", "Враг рассыпается ледяными осколками"), en: ("Crystals", "The foe shatters into ice shards"), cost: 1500, col: c::ICE },
];
pub fn trail_txt(i: usize) -> (&'static str, &'static str) { if i18n::is_en() { TRAILS[i].en } else { TRAILS[i].ru } }
pub fn death_txt(i: usize) -> (&'static str, &'static str) { if i18n::is_en() { DEATHS[i].en } else { DEATHS[i].ru } }
const RAINBOW: [u8; 7] = [c::FIRE, c::AMBER, c::GOLD, c::EMER, c::CYAN, c::ICE, c::AMETH];
/// Цвет точки следа k (0 — у игрока)
pub fn trail_col(kind: u8, pal: u8, k: usize, t: f32) -> u8 {
    match kind { 2 => if k % 2 == 0 { c::GOLD } else { pal }, 3 => RAINBOW[(k + (t * 10.) as usize) % 7], 4 => if k < 4 { c::GOLD } else if k < 8 { c::AMBER } else { c::FIRE }, 5 => c::ICE, 6 => c::PURP, _ => pal }
}
impl Game {
    /// Частицы шлейфа (раз в 35 мс, пока игрок движется)
    pub fn trail_fx(&mut self) {
        let k = self.s.trail; if k == 0 || self.quality == 0 { return; }
        let (x, y) = (self.p.x, self.p.y); let v = (self.p.vx * self.p.vx + self.p.vy * self.p.vy).sqrt(); if v < 20. { return; }
        let (bx, by) = (-self.p.vx / v, -self.p.vy / v);
        match k {
            1 => if self.rand() < 0.5 { self.pj(x, y, 8., bx * 20., -60., 10., 15., 1.1, 8., c::ICE, 0.6); },
            2 => { let col = if self.rand() < 0.5 { c::GOLD } else { c::WHITE }; self.pj(x, y, 10., 0., 0., 15., 15., 0.8, 6., col, 1.); },
            3 => { let col = RAINBOW[(self.t * 10.) as usize % 7]; self.part(x, y, bx * 30., by * 30., 0.7, 10., col, 2.); },
            4 => { for _ in 0..2 { let col = if self.rand() < 0.4 { c::GOLD } else { c::FIRE }; self.pj(x, y, 6., bx * 60., by * 60. - 25., 20., 0., 0.55, 11., col, 2.5); } },
            5 => if self.rand() < 0.12 { let l = self.rr(40., 70.); let (j1, j2) = (self.rr(-15., 15.), self.rr(-15., 15.)); self.bolt(x, y, x + bx * l + j1, y + by * l + j2, c::ICE); },
            _ => { self.pj(x, y, 8., bx * 15., by * 15. - 8., 0., 0., 1.0, 14., c::PURP, 1.2); },
        }
    }
    /// Эффект гибели врага поверх обычного
    pub fn death_fx(&mut self, x: f32, y: f32, sz: f32) {
        let k = self.s.death; if k == 0 { return; }
        let n = if self.quality == 0 { 6 } else { 12 };
        match k {
            1 => { for i in 0..n { let a = i as f32 / n as f32 * TAU; let s = 140. + sz * 4.; self.part(x, y, a.cos() * s, a.sin() * s, 0.75, 8., RAINBOW[i % 7], 2.2); } self.ring(x, y, sz * 0.3, sz * 2.8, 0.4, c::GOLD, 2.); },
            2 => { for _ in 0..n { let sz2 = 4. + self.rr(0., 5.); self.pj(x, y, sz, 0., -80., 30., 30., 1.0, sz2 * 1.5, c::ICE, 0.8); } },
            3 => { for i in 0..8 { let a = i as f32 / 8. * TAU; self.part(x, y, a.cos() * 110., a.sin() * 110., 0.85, 12., c::GOLD, 3.); } self.burst(x, y, 6, c::WHITE, 50., 4., 0.4); },
            4 => { self.ring(x, y, sz * 3., 2., 0.35, c::PURP, 4.); self.ring(x, y, sz * 2., 1., 0.25, c::AMETH, 2.5); for i in 0..n { let a = i as f32 / n as f32 * TAU; let r = sz * 2.2; self.part(x + a.cos() * r, y + a.sin() * r, -a.cos() * r * 2.6, -a.sin() * r * 2.6, 0.38, 8., c::PURP, 0.); } },
            _ => { for _ in 0..n { let a = self.rand() * TAU; let s = 80. + self.rand() * 120.; let col = if self.rand() < 0.5 { c::ICE } else { c::WHITE }; self.part(x, y, a.cos() * s, a.sin() * s, 0.7, 9., col, 3.5); } self.ring(x, y, sz * 0.4, sz * 2., 0.3, c::ICE, 3.); },
        }
    }
    /// частица с разбросом: позиция ±j, скорость (vx±dvx, vy±dvy)
    fn pj(&mut self, x: f32, y: f32, j: f32, vx: f32, vy: f32, dvx: f32, dvy: f32, life: f32, size: f32, col: u8, drag: f32) {
        let (a, b, c_, d) = (self.rr(-j, j), self.rr(-j, j), self.rr(-dvx, dvx), self.rr(-dvy, dvy)); self.part(x + a, y + b, vx + c_, vy + d, life, size, col, drag); }
    pub fn buy_fx(&mut self, death: bool, i: usize) -> bool {
        let (cost, key) = (if death { DEATHS[i].cost } else { TRAILS[i].cost }, i.to_string());
        let owned = i == 0 || if death { self.s.deaths.contains_key(&key) } else { self.s.trails.contains_key(&key) };
        if !owned { if self.s.pearls < cost { return false; } self.s.pearls -= cost; if death { self.s.deaths.insert(key, 1); } else { self.s.trails.insert(key, 1); } self.snd(crate::game::Sfx::Ach); }
        if death { self.s.death = i as u8; } else { self.s.trail = i as u8; } self.dirty = true; true
    }
}
