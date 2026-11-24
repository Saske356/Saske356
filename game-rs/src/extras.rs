//! 4.1: питомцы, события выходных, мастерство искр, колесо удачи.
use crate::data::{c, K, TAU};
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
