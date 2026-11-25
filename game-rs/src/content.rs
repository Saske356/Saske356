//! Контент 3.5: особые элитные враги (свойства) и реликвии — сильные предметы на весь забег.
use crate::data::{c, K, TAU};
use crate::game::Sfx;
use crate::game::*;
use crate::i18n;

// ---------------- свойства элиты ----------------
pub const AFF_SHIELD: u8 = 1; // Панцирь: пузырь поглощает урон
pub const AFF_SPLIT: u8 = 2; // Делящийся: при гибели распадается на двоих
pub const AFF_VOLATILE: u8 = 3; // Взрывной: при гибели — кольцо пуль
pub const AFF_VAMP: u8 = 4; // Вампир: лечит соседей
pub const AFF_BLINK: u8 = 5; // Призрак: перемещается к игроку
pub const AFF_RAGE: u8 = 6; // Яростный: на половине здоровья ускоряется
pub const AFF_N: u8 = 6;

pub fn aff_name(a: u8) -> &'static str {
    let en = i18n::is_en();
    match (a, en) {
        (AFF_SHIELD, false) => "Панцирный", (AFF_SHIELD, true) => "Shielded",
        (AFF_SPLIT, false) => "Делящийся", (AFF_SPLIT, true) => "Splitting",
        (AFF_VOLATILE, false) => "Взрывной", (AFF_VOLATILE, true) => "Volatile",
        (AFF_VAMP, false) => "Вампир", (AFF_VAMP, true) => "Vampiric",
        (AFF_BLINK, false) => "Призрачный", (AFF_BLINK, true) => "Blinking",
        (AFF_RAGE, false) => "Яростный", (AFF_RAGE, true) => "Berserk",
        _ => "",
    }
}
pub fn aff_col(a: u8) -> u32 { match a { AFF_SHIELD => 0x8fe8ff, AFF_SPLIT => 0x7dff9a, AFF_VOLATILE => 0xff9a3c, AFF_VAMP => 0xff4f6f, AFF_BLINK => 0xc59bff, AFF_RAGE => 0xff5a3c, _ => 0xffd54f } }
pub fn aff_pal(a: u8) -> u8 { match a { AFF_SHIELD => c::ICE, AFF_SPLIT => c::EMER, AFF_VOLATILE => c::DART, AFF_VAMP => c::CRAB, AFF_BLINK => c::AMETH, AFF_RAGE => c::FIRE, _ => c::GOLD } }

// ---------------- реликвии ----------------
pub struct RelicDef { pub icon: &'static str, pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str), pub col: u8 }
pub const R_GLASS: u8 = 0; pub const R_TIDE: u8 = 1; pub const R_CROWN: u8 = 2; pub const R_FANG: u8 = 3; pub const R_STORM: u8 = 4; pub const R_MIRROR: u8 = 5;
pub const R_LENS: u8 = 6; pub const R_HEART: u8 = 7; pub const R_COMPASS: u8 = 8; pub const R_BLOOD: u8 = 9; pub const R_EYE: u8 = 10; pub const R_WARD: u8 = 11;
pub const R_EMBER: u8 = 12; pub const R_STAR: u8 = 13; pub const R_HEAVY: u8 = 14; pub const R_DEAL: u8 = 15;
pub static RELICS: [RelicDef; 16] = [
    RelicDef { icon: "overcharge", ru: ("Стеклянное сердце", "+40% урона, но −25% здоровья"), en: ("Glass Heart", "+40% damage, but −25% health"), col: c::CRAB },
    RelicDef { icon: "tide", ru: ("Ракушка прилива", "+15% скорости, рывок восстанавливается на 25% быстрее"), en: ("Tide Shell", "+15% speed, dash recharges 25% faster"), col: c::ICE },
    RelicDef { icon: "greed", ru: ("Жемчужная корона", "+50% жемчуга за этот забег"), en: ("Pearl Crown", "+50% pearls this run"), col: c::GOLD },
    RelicDef { icon: "leech", ru: ("Клык левиафана", "Каждое 20-е убийство лечит 8% здоровья"), en: ("Leviathan Fang", "Every 20th kill heals 8% health"), col: c::CORAL },
    RelicDef { icon: "thunder", ru: ("Око бури", "Каждые 5 с молнии бьют трёх врагов (×2.5 урона)"), en: ("Storm Eye", "Every 5 s lightning hits three foes (×2.5 dmg)"), col: c::GOLD },
    RelicDef { icon: "barrier", ru: ("Зеркальная чешуя", "18% шанс полностью избежать удара"), en: ("Mirror Scale", "18% chance to dodge a hit completely"), col: c::WHITE },
    RelicDef { icon: "multi", ru: ("Линза глубин", "+1 снаряд в залпе, −8% урона"), en: ("Deep Lens", "+1 projectile per volley, −8% damage"), col: c::CYAN },
    RelicDef { icon: "heal", ru: ("Второе сердце", "Один раз воскрешает с половиной здоровья"), en: ("Second Heart", "Revives you once with half health"), col: c::EMER },
    RelicDef { icon: "magnet", ru: ("Компас глубин", "Радиус сбора ×1.6, +12% опыта"), en: ("Deep Compass", "Pickup radius ×1.6, +12% XP"), col: c::ICE },
    RelicDef { icon: "frenzy", ru: ("Кровь бездны", "Каждое убийство +1.5% скорострельности на 4 с (до +36%)"), en: ("Abyss Blood", "Each kill +1.5% fire rate for 4 s (up to +36%)"), col: c::FIRE },
    RelicDef { icon: "crit", ru: ("Кристалл ока", "+12% шанс крита, криты бьют ×2.7"), en: ("Eye Crystal", "+12% crit chance, crits deal ×2.7"), col: c::GOLD },
    RelicDef { icon: "aegis", ru: ("Оберег медузы", "Щит на один удар, восстанавливается каждые 12 с"), en: ("Jelly Ward", "A one-hit shield, restores every 12 s"), col: c::JELLY },
    RelicDef { icon: "burn", ru: ("Тлеющий уголь", "Все попадания поджигают врагов"), en: ("Smouldering Coal", "Every hit sets foes on fire"), col: c::AMBER },
    RelicDef { icon: "supernova", ru: ("Сердце звезды", "Когда тебя ранят — взрыв света вокруг (×8 урона)"), en: ("Star Heart", "When hurt — a burst of light around you (×8 dmg)"), col: c::GOLD },
    RelicDef { icon: "caliber", ru: ("Тяжёлый свет", "+30% урона, −10% скорострельности"), en: ("Heavy Light", "+30% damage, −10% fire rate"), col: c::WHITE },
    RelicDef { icon: "fortune", ru: ("Сделка с бездной", "+35% опыта, но враги на 15% крепче"), en: ("Abyss Pact", "+35% XP, but foes have 15% more health"), col: c::PURP },
];
pub fn relic_txt(id: u8) -> (&'static str, &'static str) { let r = &RELICS[id as usize]; if i18n::is_en() { r.en } else { r.ru } }

/// Форма атаки искры (подпись в магазине)
pub fn char_attack(i: usize) -> &'static str {
    let en = i18n::is_en();
    match (i, en) { (1, false) => "Атака: быстрые иглы", (1, true) => "Attack: swift needles", (2, false) => "Атака: тяжёлые шары", (2, true) => "Attack: heavy orbs",
        (3, false) => "Атака: дробь веером", (3, true) => "Attack: spread shot", (4, false) => "Атака: световые полумесяцы", (4, true) => "Attack: light crescents",
        (5, false) => "Атака: молнии-зигзаги", (5, true) => "Attack: zigzag bolts", (6, false) => "Атака: призрачные снаряды с наведением", (6, true) => "Attack: homing ghost shots", (7, false) => "Атака: струя пламени, всё поджигает", (7, true) => "Attack: flame stream that ignites",
        (8, false) => "Атака: капли, отскакивают от врагов", (8, true) => "Attack: bouncing droplets", (9, false) => "Атака: вращающиеся звёзды, +10% крита", (9, true) => "Attack: spinning stars, +10% crit",
        (_, false) => "Атака: лучи света", (_, true) => "Attack: light bolts" }
}

impl Game {
    #[inline] pub fn rel(&self, id: u8) -> bool { self.relics.contains(&id) }

    // ---------- элита ----------
    /// Выдать элитному врагу случайное свойство (с 3-й зоны; не боссам, не золотому косяку)
    pub fn assign_affix(&mut self, i: usize) {
        let (kind, elite) = { let e = &self.en.items[i]; (e.kind, e.elite) };
        if !elite || (self.zone < 3 && self.abyss < 16) || kind.d().boss || matches!(kind, K::Drifter | K::Chest | K::Crystal | K::Wisp | K::Fry | K::Spikelet) { return; }
        let a = 1 + (self.rand() * AFF_N as f32) as u8 % AFF_N;
        let e = &mut self.en.items[i]; e.aff = a; e.aff_t = 1.5 + (e.phase % 1.) * 2.;
        if a == AFF_SHIELD { e.ash = e.max_hp * 0.45; }
    }
    /// Поглощение урона панцирем; возвращает остаток урона
    pub fn affix_absorb(&mut self, i: usize, dmg: f32) -> f32 {
        let e = &mut self.en.items[i]; if e.aff != AFF_SHIELD || e.ash <= 0. { return dmg; }
        let take = dmg.min(e.ash); e.ash -= take; let (x, y, r) = (e.x, e.y, e.r * e.scale);
        if e.ash <= 0. { self.burst(x, y, 14, c::ICE, 220., 6., 0.45); self.ring(x, y, r, r * 2.6, 0.35, c::ICE, 4.); self.snd(Sfx::Clink); self.shake(3.); }
        else if self.rand() < 0.35 { self.snd(Sfx::Clink); }
        dmg - take
    }
    /// Каждый кадр, для элиты со свойством
    pub fn update_affix(&mut self, i: usize, dt: f32) {
        let (a, x, y) = { let e = &self.en.items[i]; (e.aff, e.x, e.y) }; if a == 0 { return; }
        self.en.items[i].aff_t -= dt;
        match a {
            // 4.4: вампир лечит слабее и не больше трёх соседей — толпа вампиров больше не «бессмертна»
            AFF_VAMP => if self.en.items[i].aff_t <= 0. { self.en.items[i].aff_t = 2.; let q = self.qb(x, y, 170.); let mut n = 0;
                for &k in &q { if k == i || n >= 3 { continue; } let o = &self.en.items[k]; if o.dead || o.kind.d().boss || o.hp >= o.max_hp || o.heal_t > 0. { continue; }
                    let (ox, oy) = (o.x, o.y); let o = &mut self.en.items[k]; o.hp = (o.hp + o.max_hp * 0.03).min(o.max_hp); o.heal_t = 1.5; if n < 3 && self.quality > 0 { self.bolt(x, y, ox, oy, c::CRAB); } n += 1; }
                self.qb_back(q); { let e = &mut self.en.items[i]; e.hp = (e.hp + e.max_hp * 0.01).min(e.max_hp); }
                if n > 0 { self.ring(x, y, 8., 190., 0.4, c::CRAB, 2.); } },
            AFF_BLINK => if self.en.items[i].aff_t <= 0. { self.en.items[i].aff_t = 3.6;
                let d = hypot(self.p.x - x, self.p.y - y); if d > 120. && d < 900. { let a0 = self.rand() * TAU; let rr = self.rr(150., 220.);
                    let (mut nx, mut ny) = (self.p.x + a0.cos() * rr, self.p.y + a0.sin() * rr); let l = hypot(nx, ny); let m = crate::data::cfg::ARENA_R - 40.; if l > m { nx *= m / l; ny *= m / l; }
                    self.burst(x, y, 12, c::AMETH, 160., 6., 0.4); self.ring(x, y, 6., 50., 0.3, c::AMETH, 3.);
                    let e = &mut self.en.items[i]; e.x = nx; e.y = ny; e.vx = 0.; e.vy = 0.; e.spawn_t = 0.25; self.ring(nx, ny, 50., 6., 0.3, c::AMETH, 3.); } },
            AFF_RAGE => { let e = &mut self.en.items[i]; if e.hp < e.max_hp * 0.5 && e.aff_t > -100. { e.aff_t = -1000.; e.spd *= 1.7; e.dmg *= 1.3;
                    let (x, y, r) = (e.x, e.y, e.r * e.scale); self.ring(x, y, r, r * 3., 0.4, c::FIRE, 4.); self.burst(x, y, 10, c::FIRE, 180., 7., 0.4); self.snd(Sfx::Warn); }
                else if e.aff_t < -100. && self.quality > 0 && self.rng.next() < 0.25 { let (x, y) = (e.x, e.y); let (a, b) = (self.rr(-10., 10.), self.rr(-10., 10.)); self.part(x + a, y + b, 0., -40., 0.3, 5., c::FIRE, 1.); } }
            _ => {}
        }
    }
    /// Гибель элиты со свойством
    pub fn affix_death(&mut self, e: &Enemy) {
        match e.aff {
            AFF_SPLIT => for k in 0..2 { let a = e.ang + std::f32::consts::FRAC_PI_2 + k as f32 * std::f32::consts::PI; let (x, y) = (e.x + a.cos() * 14., e.y + a.sin() * 14.);
                if let Some(j) = self.spawn_enemy(e.kind, x, y, false) { let s = &mut self.en.items[j]; s.max_hp = e.max_hp * 0.22; s.hp = s.max_hp; s.scale = 0.85; s.xp = (e.xp * 0.15).max(1.); s.spawn_t = 0.15; s.vx = a.cos() * 220.; s.vy = a.sin() * 220.; s.tier = e.tier; } },
            AFF_VOLATILE => { let n = 12 + self.zone.min(10); for k in 0..n { let j = self.rr(-0.08, 0.08); self.e_shoot(e.x, e.y, k as f32 * TAU / n as f32 + j, 140. + self.zone as f32 * 4., 5., 9. * self.dmg_scale, c::DART, 0.); }
                self.ring(e.x, e.y, 6., 90., 0.45, c::DART, 5.); self.burst(e.x, e.y, 18, c::DART, 240., 8., 0.5); self.snd(Sfx::Boom(false)); self.shake(7.); }
            _ => {}
        }
    }

    // ---------- реликвии ----------
    /// Три реликвии на выбор (которых ещё нет)
    pub fn roll_relics(&mut self) -> Vec<usize> {
        let mut pool: Vec<u8> = (0..RELICS.len() as u8).filter(|r| !self.rel(*r)).collect(); let mut out = vec![];
        while out.len() < 3 && !pool.is_empty() { let k = (self.rand() * pool.len() as f32) as usize % pool.len(); out.push(pool.remove(k) as usize); }
        out
    }
    pub fn take_relic(&mut self, id: usize) {
        let id = id as u8; if self.rel(id) { return; } self.relics.push(id);
        if id == R_HEART { self.rel_lives += 1; } if id == R_WARD { self.p.shield = self.p.shield.max(1); }
        self.compute_stats(); self.snd(Sfx::Ach);
        let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 160., 0.6, c::GOLD, 6.); self.burst(x, y, 24, c::GOLD, 240., 8., 0.6);
        self.banner(if i18n::is_en() { "RELIC".into() } else { "РЕЛИКВИЯ".into() }, relic_txt(id).0.into(), 0xffc35a, 2.2);
    }
    /// Множители реликвий — в конце compute_stats
    pub fn relic_stats(&mut self) {
        let st = &mut self.st;
        if self.relics.contains(&R_GLASS) { st.dmg *= 1.4; }
        if self.relics.contains(&R_TIDE) { st.speed *= 1.15; st.dash_cd *= 0.75; }
        if self.relics.contains(&R_LENS) { st.multi += 1; st.dmg *= 0.92; }
        if self.relics.contains(&R_COMPASS) { st.magnet *= 1.6; st.xp_mul *= 1.12; }
        if self.relics.contains(&R_EYE) { st.crit += 0.12; st.crit_mul = st.crit_mul.max(2.7); }
        if self.relics.contains(&R_EMBER) && st.burn <= 0. { st.burn = st.dmg * 0.2; }
        if self.relics.contains(&R_HEAVY) { st.dmg *= 1.3; st.rate *= 0.9; }
        if self.relics.contains(&R_DEAL) { st.xp_mul *= 1.35; }
        match self.path { P_DANGER => st.xp_mul *= 1.3, P_CALM => st.xp_mul *= 0.8, P_HEAL => st.regen += 1., _ => {} }
        st.orb_dmg = st.dmg * 0.9;
        self.evo_stats(); if self.abyss >= 12 { self.st.dash_cd *= 1.25; } self.mastery_stats(); self.pet_stats(); if self.event_on() == crate::extras::EV_CRAB { self.st.xp_mul *= 1.3; }
        { let st = &mut self.st; match self.run_mode {
            crate::game::RunMode::Dash => { st.dash_cd = 0.38; st.dash_dmg = st.dmg * 9.; }
            crate::game::RunMode::NoUp => { let n = self.p.level.saturating_sub(1) as f32; st.dmg *= 1. + 0.08 * n; st.rate *= 1. + 0.03 * n; st.speed *= 1. + 0.01 * n.min(30.); }
            _ => {} } }
        let st = &mut self.st; let _ = st;
        if self.relics.contains(&R_GLASS) { self.p.max_hp = (self.p.max_hp * 0.75).round(); self.p.hp = self.p.hp.min(self.p.max_hp); }
    }
    /// Каждый кадр забега
    pub fn relic_tick(&mut self, dt: f32) {
        if self.relics.is_empty() { return; }
        if self.rel_blood > 0. { self.rel_blood_t -= dt; if self.rel_blood_t <= 0. { self.rel_blood = 0.; } }
        if self.rel(R_WARD) && self.p.shield <= 0 { self.rel_ward_t += dt; if self.rel_ward_t >= 12. { self.rel_ward_t = 0.; self.p.shield = 1; let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 60., 0.4, c::JELLY, 4.); } }
        if self.rel(R_STORM) { self.rel_storm_t += dt; if self.rel_storm_t >= 5. { self.rel_storm_t = 0.;
            let (cx, cy, vw, vh) = (self.cam_x, self.cam_y, self.vw, self.vh);
            let vis: Vec<usize> = (0..self.en.n).filter(|&i| { let e = &self.en.items[i]; !e.dead && e.kind != K::Crystal && (e.x - cx).abs() < vw && (e.y - cy).abs() < vh }).collect();
            if !vis.is_empty() { for _ in 0..3 { let i = vis[(self.rng.next() * vis.len() as f32) as usize % vis.len()]; if self.en.items[i].dead { continue; } let (x, y) = (self.en.items[i].x, self.en.items[i].y);
                    let ox = self.rr(-40., 40.); self.bolt(x + ox, y - 260., x, y, c::GOLD); self.ring(x, y, 4., 44., 0.25, c::GOLD, 3.); self.damage_enemy(i, self.st.dmg * 2.5, true, f32::NAN, 0., 0., Src::Static); }
                self.snd(Sfx::Boom(false)); } } }
    }
    pub fn relic_kill(&mut self, boss: bool) {
        if self.rel(R_FANG) { self.rel_kills += 1; if self.rel_kills >= 20 { self.rel_kills = 0; let h = (self.p.max_hp * 0.08).min(self.p.max_hp - self.p.hp); if h > 0. { self.p.hp += h; let (x, y) = (self.p.x, self.p.y - 26.); self.text(x, y, format!("+{}", h.round()), 0x8affc0, false, false); } } }
        if self.rel(R_BLOOD) { self.rel_blood = (self.rel_blood + 0.015).min(0.36); self.rel_blood_t = 4.; }
        
    }
    /// Перед уроном игроку: true — удар отражён
    pub fn relic_dodge(&mut self) -> bool {
        if self.rel(R_MIRROR) && self.rand() < 0.18 { let (x, y) = (self.p.x, self.p.y); self.p.inv = self.p.inv.max(0.35);
            self.text(x, y - 26., if i18n::is_en() { "Dodge".into() } else { "Уклон".into() }, 0xeaf2ff, false, false); self.ring(x, y, self.p.r, self.p.r + 26., 0.3, c::WHITE, 3.); self.snd(Sfx::Clink); return true; }
        false
    }
    /// После получения урона
    pub fn relic_hurt(&mut self) {
        if self.rel(R_STAR) { let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 190., 0.45, c::GOLD, 6.); self.burst(x, y, 20, c::GOLD, 260., 8., 0.5);
            let q = self.qa(x, y, 210.); let dm = self.st.dmg * 8.; for &i in &q { if !self.en.items[i].dead { let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); let (dx, dy) = (ex - x, ey - y); let d = hypot(dx, dy).max(1.); if d < 200. { self.damage_enemy(i, dm, true, f32::NAN, dx / d * 320., dy / d * 320., Src::Nova); } } } self.qa_back(q); }
    }
    /// Смерть: true — спасён вторым сердцем
    pub fn relic_save(&mut self) -> bool {
        if self.rel_lives > 0 { self.rel_lives -= 1; self.p.hp = self.p.max_hp * 0.5; self.p.inv = 2.5; self.do_flare(true);
            self.banner(relic_txt(R_HEART).0.to_uppercase(), if i18n::is_en() { "Rise again".into() } else { "Свет ещё горит".into() }, 0x4fff9a, 2.2); return true; }
        false
    }
}

// ---------------- развилка путей (после каждого босса) ----------------
pub struct PathDef { pub icon: &'static str, pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str), pub col: u8 }
pub const P_DANGER: u8 = 1; pub const P_TREASURE: u8 = 2; pub const P_HEAL: u8 = 3; pub const P_FORGE: u8 = 4; pub const P_HUNT: u8 = 5; pub const P_RELIC: u8 = 6; pub const P_CALM: u8 = 7;
/// индекс = id - 1
pub static PATHS: [PathDef; 7] = [
    PathDef { icon: "rage", ru: ("Опасный путь", "Враги на 40% крепче и бьют сильнее, но жемчуг падает вдвое чаще и опыта +30%"), en: ("Perilous Path", "Foes 40% tougher and stronger, but pearls drop twice as often and +30% XP"), col: c::CRAB },
    PathDef { icon: "greed", ru: ("Сокровищница", "В каждой зоне — жемчужница, но врагов на 20% больше"), en: ("Treasury", "A pearl oyster in every zone, but 20% more foes"), col: c::GOLD },
    PathDef { icon: "heal", ru: ("Тихий источник", "Сразу полное здоровье и +1 здоровья в секунду до следующего босса"), en: ("Quiet Spring", "Full health now and +1 health per second until the next boss"), col: c::EMER },
    PathDef { icon: "overcharge", ru: ("Кузница света", "Сразу улучшение на выбор, без ожидания"), en: ("Light Forge", "Pick an upgrade right away"), col: c::ICE },
    PathDef { icon: "hunter", ru: ("Охота на элиту", "Элиты втрое чаще, с каждой — 2 жемчужины"), en: ("Elite Hunt", "Elites three times as often, each drops 2 pearls"), col: c::AMBER },
    PathDef { icon: "prism", ru: ("Тропа мастера", "До следующего владыки — 4 карты на выбор вместо 3, но враги на 25% крепче"), en: ("Master's Trail", "Until the next lord — 4 cards to choose from instead of 3, but foes are 25% tougher"), col: c::PURP },
    PathDef { icon: "tide", ru: ("Тихие воды", "Врагов на 30% меньше и они слабее, но опыта на 20% меньше"), en: ("Calm Waters", "30% fewer and weaker foes, but 20% less XP"), col: c::CYAN },
];
pub fn path_txt(id: u8) -> (&'static str, &'static str) { let p = &PATHS[(id as usize).saturating_sub(1).min(PATHS.len() - 1)]; if i18n::is_en() { p.en } else { p.ru } }

impl Game {
    /// три пути на выбор (id 1..=7)
    pub fn roll_paths(&mut self) -> Vec<usize> {
        let mut pool: Vec<usize> = (1..=PATHS.len()).collect(); let mut out = vec![];
        while out.len() < 3 && !pool.is_empty() { let k = (self.rand() * pool.len() as f32) as usize % pool.len(); out.push(pool.remove(k)); }
        out
    }
    pub fn take_path(&mut self, id: usize) {
        let id = id as u8; self.path = id; self.snd(Sfx::Ach);
        match id { P_HEAL => { self.p.hp = self.p.max_hp; } P_FORGE => { self.level_pending += 1; self.level_delay = 0.6; self.lv_t = -99.; }
            P_TREASURE => { let a = self.rand() * TAU; self.spawn_chest(self.p.x + a.cos() * 260., self.p.y + a.sin() * 260.); } _ => {} }
        self.compute_stats();
        let (x, y) = (self.p.x, self.p.y); let col = PATHS[id as usize - 1].col; self.ring(x, y, 10., 180., 0.6, col, 6.);
        self.banner(if i18n::is_en() { "PATH CHOSEN".into() } else { "ПУТЬ ВЫБРАН".into() }, path_txt(id).0.into(), 0x8fe8ff, 2.);
    }
    /// множитель здоровья врагов от пути
    pub fn path_hp(&self) -> f32 { match self.path { P_DANGER => 1.4, P_RELIC => 1.25, P_CALM => 0.85, _ => 1. } }
    pub fn path_dmg(&self) -> f32 { match self.path { P_DANGER => 1.3, P_CALM => 0.85, _ => 1. } }
    pub fn path_spawn(&self) -> f32 { match self.path { P_TREASURE => 1.2, P_CALM => 0.7, _ => 1. } }
}

// ---------------- эволюции оружия ----------------
/// 4.4: улучшение на максимуме + второе улучшение (need, need_lv) → в выборе появляется золотая «Эволюция». Реликвий больше нет.
pub struct EvoDef { pub upg: usize, pub need: usize, pub need_lv: u8, pub icon: &'static str, pub ru: (&'static str, &'static str), pub en: (&'static str, &'static str) }
pub const EVO_BASE: usize = usize::MAX - 100;
pub const EV_NOVA: u16 = 1; pub const EV_ORBIT: u16 = 2; pub const EV_HARPOON: u16 = 4; pub const EV_BEAM: u16 = 8; pub const EV_FROST: u16 = 16; pub const EV_BURN: u16 = 32; pub const EV_RATE: u16 = 64;
pub static EVOS: [EvoDef; 7] = [
    EvoDef { upg: crate::data::u::NOVA, need: crate::data::u::DASHNOVA, need_lv: 1, icon: "supernova", ru: ("Солнечный венец", "Импульс вдвое чаще, шире в 1.5 раза и бьёт в 2.5 раза сильнее"), en: ("Solar Crown", "Pulse twice as often, 1.5× wider and 2.5× stronger") },
    EvoDef { upg: crate::data::u::ORBIT, need: crate::data::u::STATIC, need_lv: 1, icon: "storm", ru: ("Грозовой хоровод", "8 спор-спутников, урон спутников ×2.5"), en: ("Thunder Ring", "8 orbiting spores, orbit damage ×2.5") },
    EvoDef { upg: crate::data::u::HARPOON, need: crate::data::u::EXECUTE, need_lv: 1, icon: "spear", ru: ("Гарпун Левиафана", "Гарпун вдвое чаще и вдвое сильнее"), en: ("Leviathan Harpoon", "Harpoon twice as often and twice as strong") },
    EvoDef { upg: crate::data::u::BEAM, need: crate::data::u::MULTI, need_lv: 2, icon: "lighthouse", ru: ("Чёрное солнце", "Луч жжёт в 2.5 раза сильнее и достаёт дальше"), en: ("Black Sun", "The beam burns 2.5× stronger and reaches farther") },
    EvoDef { upg: crate::data::u::FROST, need: crate::data::u::CRIT, need_lv: 2, icon: "abyssice", ru: ("Ледяной взор", "+25% к шансу крита, по замедленным врагам урон +50%"), en: ("Frozen Gaze", "+25% crit chance, +50% damage to slowed foes") },
    EvoDef { upg: crate::data::u::BURN, need: crate::data::u::AURA, need_lv: 1, icon: "wildfire", ru: ("Пламя глубин", "Горение втрое сильнее и перекидывается на соседей"), en: ("Deep Flame", "Burning is 3× stronger and spreads to neighbours") },
    EvoDef { upg: crate::data::u::RATE, need: crate::data::u::FRENZY, need_lv: 1, icon: "frenzy", ru: ("Буря света", "Скорострельность ×1.4 и +1 снаряд в залпе"), en: ("Light Storm", "Fire rate ×1.4 and +1 projectile per volley") },
];
pub fn evo_txt(k: usize) -> (&'static str, &'static str) { let e = &EVOS[k]; if i18n::is_en() { e.en } else { e.ru } }

impl Game {
    #[inline] pub fn evo(&self, bit: u16) -> bool { self.p.evo & bit != 0 }
    /// Эволюции, доступные прямо сейчас (индексы в EVOS)
    pub fn evo_ready(&self) -> Vec<usize> {
        (0..EVOS.len()).filter(|&k| { let e = &EVOS[k]; self.p.evo & (1 << k) == 0 && self.p.up[e.upg] >= crate::data::UPG[e.upg].max && self.p.up[e.need] >= e.need_lv }).collect()
    }
    pub fn take_evo(&mut self, k: usize) {
        self.p.evo |= 1 << k; self.compute_stats(); self.snd(Sfx::Ach); self.vibrate(60);
        let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 220., 0.7, c::GOLD, 8.); self.burst(x, y, 40, c::GOLD, 320., 10., 0.8); self.flash = self.flash.max(0.4);
        self.banner(if i18n::is_en() { "EVOLUTION!".into() } else { "ЭВОЛЮЦИЯ!".into() }, evo_txt(k).0.into(), 0xffd54f, 2.6);
    }
    /// Множители эволюций — в конце compute_stats
    pub fn evo_stats(&mut self) {
        let ev = self.p.evo; let st = &mut self.st;
        if ev & EV_NOVA != 0 { st.nova_cd *= 0.5; st.nova_r *= 1.5; }
        if ev & EV_ORBIT != 0 { st.orb_n = 8; st.orb_dmg *= 2.5; }
        if ev & EV_HARPOON != 0 { st.harpoon_cd *= 0.5; st.harpoon_dmg *= 2.; }
        if ev & EV_BEAM != 0 { st.beam_dps *= 2.5; st.beam_r *= 1.4; }
        if ev & EV_FROST != 0 { st.crit += 0.25; }
        if ev & EV_BURN != 0 { st.burn = st.burn.max(st.dmg * 0.2) * 3.; st.wildfire = true; }
        if ev & EV_RATE != 0 { st.rate *= 1.4; st.multi += 1; }
    }
}
