//! 4.9: у каждой искры своя особая способность вместо общей «Вспышки». Заряжается так же (убийства, пули впритирку),
//! кнопка та же. У каждой есть защитная часть (стирает пули рядом, щит или неуязвимость) — это по-прежнему «спасательная» кнопка.
use crate::data::{c, u, CHARS, TAU};
use crate::game::*;
use crate::i18n;

pub struct AbDef { pub ru: (&'static str, &'static str, &'static str), pub en: (&'static str, &'static str, &'static str), pub col: u8 }
/// (короткое имя на кнопку, полное имя, описание) — по порядку CHARS
pub static ABILITIES: [AbDef; 14] = [
    AbDef { ru: ("ВСПЫШКА", "Вспышка", "сжигает всё на экране и стирает все пули"), en: ("FLARE", "Flare", "burns everything on screen and erases all bullets"), col: c::GOLD },
    AbDef { ru: ("ЛИВЕНЬ", "Ливень игл", "2,5 с иглы веером летят во все стороны, пули рядом стираются"), en: ("NEEDLES", "Needle storm", "for 2.5 s needles fly in every direction, nearby bullets vanish"), col: c::EMER },
    AbDef { ru: ("ПАНЦИРЬ", "Каменный панцирь", "5 с урон по тебе −85%, пули о панцирь разбиваются, враги рядом отлетают"), en: ("SHELL", "Stone shell", "5 s of −85% damage taken, bullets shatter on you, nearby foes are knocked back"), col: c::AMBER },
    AbDef { ru: ("КАРТЕЧЬ", "Залп картечи", "три мощных залпа дробью в ближайших врагов, пули рядом стираются"), en: ("BUCKSHOT", "Buckshot", "three massive shotgun blasts at the nearest foes, nearby bullets vanish"), col: c::FIRE },
    AbDef { ru: ("ОПЛОТ", "Оплот", "лечит 30% здоровья, даёт 3 щита, отбрасывает врагов и стирает все пули"), en: ("BASTION", "Bastion", "heals 30%, grants 3 shields, knocks foes back and erases all bullets"), col: c::CORAL },
    AbDef { ru: ("ГРОЗА", "Гроза", "2,5 с молнии бьют врагов на экране и перескакивают на соседей"), en: ("STORM", "Thunderstorm", "for 2.5 s lightning strikes foes on screen and jumps to neighbours"), col: c::ICE },
    AbDef { ru: ("ТЕНЬ", "Тень", "3,5 с тебя не задеть, ты быстрее и ранишь всех, сквозь кого плывёшь"), en: ("SHADE", "Shade", "for 3.5 s you can't be hit, move faster and hurt everyone you pass through"), col: c::GHOST },
    AbDef { ru: ("ПЛАМЯ", "Огненные кольца", "три кольца огня поджигают всех на экране и стирают пули"), en: ("FIRE", "Fire rings", "three rings of fire set everyone on screen ablaze and erase bullets"), col: c::CRAB },
    AbDef { ru: ("ЦУНАМИ", "Цунами", "волна отбрасывает всех врагов, замедляет их на 4 с и смывает все пули"), en: ("TSUNAMI", "Tsunami", "a wave hurls all foes away, slows them for 4 s and washes away all bullets"), col: c::DRIFT },
    AbDef { ru: ("ЗВЁЗДЫ", "Звездопад", "2 с звёзды падают на врагов и взрываются"), en: ("STARS", "Starfall", "for 2 s stars rain down on foes and explode"), col: c::GOLD },
    AbDef { ru: ("ВИХРЬ", "Вихрь бумерангов", "16 бумерангов разлетаются во все стороны и возвращаются"), en: ("WHIRL", "Boomerang whirl", "16 boomerangs fly out in all directions and return"), col: c::AMBER },
    AbDef { ru: ("ЖАТВА", "Великая жатва", "огромная коса: слабых врагов (меньше 30% здоровья) срезает сразу, остальных ранит"), en: ("REAP", "Great reaping", "a huge scythe: weak foes (under 30% health) are cut down, the rest are hurt"), col: c::AMETH },
    AbDef { ru: ("НЕРЕСТ", "Нерест", "выпускает 18 мальков и лечит 15% здоровья"), en: ("SPAWN", "Spawning", "releases 18 fry and heals 15% health"), col: c::EMER },
    AbDef { ru: ("МИНЫ", "Минное поле", "вокруг тебя появляются 14 мин, пули рядом стираются"), en: ("MINES", "Minefield", "14 mines appear around you, nearby bullets vanish"), col: c::FIRE },
];
pub fn ab_idx(ch: &str) -> usize { CHARS.iter().position(|x| x.id == ch).unwrap_or(0).min(ABILITIES.len() - 1) }
pub fn ab_txt(i: usize) -> (&'static str, &'static str, &'static str) { if i18n::is_en() { ABILITIES[i].en } else { ABILITIES[i].ru } }
/// Строка для карточки искры в магазине
pub fn ab_line(i: usize) -> String { let (_, n, d) = ab_txt(i); if i18n::is_en() { format!("Special: {n} — {d}.") } else { format!("Особое: {n} — {d}.") } }

impl Game {
    fn ab_dmg(&self, boss: bool) -> f32 { if boss { 180. + self.st.dmg * 12. } else { 90. + self.st.dmg * 9. } }
    fn ab_clear(&mut self, r: f32) {
        let (px, py) = (self.p.x, self.p.y); let mut i = self.eb.n;
        while i > 0 { i -= 1; let b = &self.eb.items[i]; if (b.x - px).powi(2) + (b.y - py).powi(2) < r * r { let (x, y) = (b.x, b.y); self.part(x, y, 0., 0., 0.4, 9., c::WHITE, 2.); self.eb.kill(i); self.score += 3.; } }
    }
    fn on_screen(&self) -> Vec<usize> { (0..self.en.n).filter(|&i| { let e = &self.en.items[i]; !e.dead && e.spawn_t <= 0.2 && (e.x - self.cam_x).abs() < self.vw + 20. && (e.y - self.cam_y).abs() < self.vh + 20. }).collect() }
    /// Особая способность искры (кнопка «Вспышка»)
    pub fn do_ability(&mut self) {
        let k = ab_idx(&self.s.ch.clone()); if k == 0 { self.do_flare(false); return; }
        // общее: расход заряда, задания/достижения, обучение
        self.quest_add("flare", 1); self.p.flare = 0.; self.s.flares += 1; if self.s.flares >= 10 { self.unlock("flare10"); } if self.tut.on && self.tut.step == 4 { self.tut.v = 1.; }
        let col = ABILITIES[k].col; let (px, py) = (self.p.x, self.p.y);
        self.flash = 0.45; self.hit_stop = 0.08; self.shake(14.); self.snd(Sfx::Flare); self.vibrate(70);
        self.ring(px, py, 10., 260., 0.5, col, 8.); self.burst(px, py, 24, col, 360., 10., 0.6);
        self.banner(ab_txt(k).1.to_uppercase(), String::new(), crate::data::PAL_HEX[col as usize], 1.1);
        self.ab_kind = k as u8; self.ab_acc = 0.; self.ab_k = 0;
        match k {
            1 => { self.ab_t = 2.5; self.ab_clear(220.); }
            2 => { self.ab_t = 5.; self.ab_clear(280.); self.ab_push(240., 0.6, 700.); }
            3 => { self.ab_t = 0.62; self.ab_clear(240.); }
            4 => { self.ab_t = 0.; self.p.hp = (self.p.hp + self.p.max_hp * 0.3).min(self.p.max_hp); self.p.shield = (self.p.shield + 3).min(6); self.eb.clear(); self.ab_push(300., 0.5, 800.);
                self.ring(px, py, 10., 300., 0.6, c::WHITE, 6.); }
            5 => { self.ab_t = 2.5; self.ab_clear(220.); }
            6 => { self.ab_t = 3.5; self.p.inv = self.p.inv.max(3.5); self.ab_clear(160.); }
            7 => { self.ab_t = 0.75; self.eb.clear(); }
            8 => { self.ab_t = 0.; self.eb.clear(); let dm = self.ab_dmg(false) * 0.5;
                for i in self.on_screen() { let (dx, dy) = (self.en.items[i].x - px, self.en.items[i].y - py); let d = (dx * dx + dy * dy).sqrt().max(1.); let boss = self.en.items[i].kind.d().boss;
                    self.en.items[i].slow = 4.; let dmg = if boss { self.ab_dmg(true) * 0.5 } else { dm }; self.damage_enemy(i, dmg, false, f32::NAN, dx / d * if boss { 250. } else { 1100. }, dy / d * if boss { 250. } else { 1100. }, Src::None); }
                for q in 0..3 { self.ring(px, py, 20. + q as f32 * 30., 900., 0.8 + q as f32 * 0.15, c::DRIFT, 12.); } }
            9 => { self.ab_t = 2.; self.ab_clear(220.); }
            10 => { self.ab_t = 0.; self.ab_clear(260.); for q in 0..16 { let a = q as f32 * TAU / 16.; self.fire_pb(px, py, a, self.st.dmg * 2.5, false); } }
            11 => { self.ab_t = 0.8; self.ab_clear(430.);
                let (dm, db) = (self.ab_dmg(false) * 0.9, self.ab_dmg(true) * 0.9);
                for i in self.on_screen() { let e = &self.en.items[i]; let (dx, dy) = (e.x - px, e.y - py); if dx * dx + dy * dy > 430. * 430. { continue; }
                    let boss = e.kind.d().boss; let weak = !boss && e.hp < e.max_hp * 0.3; let d = (dx * dx + dy * dy).sqrt().max(1.);
                    let dmg = if weak { e.hp + 1e6 } else if boss { db } else { dm }; self.damage_enemy(i, dmg, true, f32::NAN, dx / d * 300., dy / d * 300., Src::None); }
                for q in 0..12 { let a = q as f32 * TAU / 12.; self.fire_pb(px, py, a, self.st.dmg * 1.5, false); } }
            12 => { self.ab_t = 0.; self.ab_clear(220.); self.p.hp = (self.p.hp + self.p.max_hp * 0.15).min(self.p.max_hp);
                for q in 0..18 { let a = q as f32 * TAU / 18.; self.fire_pb(px + a.cos() * 16., py + a.sin() * 16., a, self.st.dmg * 1.6, false); } }
            _ => { self.ab_t = 0.; self.ab_clear(240.); let dm = self.st.dmg * 6.;
                for q in 0..14 { let a = q as f32 * TAU / 14. + self.rand() * 0.2; let r = if q % 2 == 0 { 95. } else { 165. };
                    if let Some(m) = self.mines.spawn() { self.mines.items[m] = Mine { x: px + a.cos() * r, y: py + a.sin() * r, t: 0.2, r: 90., dmg: dm, inst: false, freeze: false }; } } }
        }
    }
    fn ab_push(&mut self, r: f32, k: f32, imp: f32) {
        let (px, py) = (self.p.x, self.p.y); let q = self.qa(px, py, r);
        for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } let (dx, dy) = (e.x - px, e.y - py); let d = (dx * dx + dy * dy).sqrt().max(1.); if d > r { continue; }
            let boss = e.kind.d().boss; let dmg = self.ab_dmg(boss) * k; let im = if boss { imp * 0.25 } else { imp }; self.damage_enemy(i, dmg, false, f32::NAN, dx / d * im, dy / d * im, Src::None); }
        self.qa_back(q);
    }
    /// Длящиеся способности
    pub fn ability_tick(&mut self, dt: f32) {
        if self.ab_t <= 0. { return; }
        self.ab_t -= dt; self.ab_acc += dt; let (px, py) = (self.p.x, self.p.y); let col = ABILITIES[self.ab_kind as usize].col;
        match self.ab_kind {
            1 => while self.ab_acc >= 0.035 { self.ab_acc -= 0.035; self.ab_k += 1; let a = self.ab_k as f32 * 0.47;
                for s in [0., std::f32::consts::PI] { self.fire_pb(px, py, a + s, self.st.dmg * 1.2, false); } }
            2 => { self.ab_clear(46.); if self.ab_acc >= 0.35 { self.ab_acc = 0.; self.ring(px, py, self.p.r + 4., self.p.r + 26., 0.35, c::AMBER, 4.); } }
            3 => if (self.ab_k == 0 && self.ab_acc >= 0.) || (self.ab_k == 1 && self.ab_acc >= 0.25) || (self.ab_k == 2 && self.ab_acc >= 0.5) { self.ab_k += 1;
                let tg = self.nearest_enemy(px, py, 900.); let a = if tg >= 0 { let e = &self.en.items[tg as usize]; (e.y - py).atan2(e.x - px) } else { self.p.ang };
                for q in 0..26 { let j = self.rr(-0.5, 0.5); let a2 = a + j; let _ = q; self.fire_pb(px, py, a2, self.st.dmg * 2.2, false); }
                self.shake(9.); self.snd(Sfx::Boom(false)); self.ring(px + a.cos() * 30., py + a.sin() * 30., 6., 70., 0.25, c::FIRE, 4.); }
            5 => while self.ab_acc >= 0.12 { self.ab_acc -= 0.12; let v = self.on_screen(); if v.is_empty() { break; }
                let i = v[(self.rand() * v.len() as f32) as usize % v.len()]; let (ex, ey, boss) = { let e = &self.en.items[i]; (e.x, e.y, e.kind.d().boss) };
                let jx = self.rr(-40., 40.); self.bolt(ex + jx, ey - 320., ex, ey, c::ICE); let dmg = self.ab_dmg(boss) * 0.5; self.damage_enemy(i, dmg, true, f32::NAN, 0., 0., Src::None); self.snd(Sfx::Hit);
                let q = self.qb(ex, ey, 130.); let mut n = 0; for &j in &q { if n >= 2 { break; } if j == i || self.en.items[j].dead { continue; } let (jx, jy) = (self.en.items[j].x, self.en.items[j].y); self.bolt(ex, ey, jx, jy, c::ICE); self.damage_enemy(j, dmg * 0.5, false, f32::NAN, 0., 0., Src::None); n += 1; } self.qb_back(q); }
            6 => { self.p.inv = self.p.inv.max(self.ab_t.max(0.)); if self.ab_acc >= 0.1 { self.ab_acc = 0.; let q = self.qa(px, py, 46.); let dm = self.ab_dmg(false) * 0.25;
                    for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } if (e.x - px).powi(2) + (e.y - py).powi(2) < (30. + e.r * e.scale).powi(2) { let b = e.kind.d().boss; self.damage_enemy(i, if b { dm * 1.5 } else { dm }, false, f32::NAN, 0., 0., Src::None); } } self.qa_back(q);
                    let (vx, vy) = (self.rr(-30., 30.), self.rr(-30., 30.)); self.part(px, py, vx, vy, 0.5, 12., c::GHOST, 2.); } }
            7 => if (self.ab_k == 0) || (self.ab_k == 1 && self.ab_acc >= 0.35) || (self.ab_k == 2 && self.ab_acc >= 0.7) { self.ab_k += 1;
                self.ring(px, py, 20., self.vw.max(self.vh) * 1.2, 0.7, c::FIRE, 14.); self.eb.clear(); let burn = self.st.dmg * 1.5; let dm = self.ab_dmg(false) * 0.3;
                for i in self.on_screen() { let boss = self.en.items[i].kind.d().boss; if !boss { let e = &mut self.en.items[i]; e.burn = e.burn.max(burn); e.burn_t = e.burn_t.max(4.); }
                    let dmg = if boss { self.ab_dmg(true) * 0.25 } else { dm }; self.damage_enemy(i, dmg, false, f32::NAN, 0., 0., Src::None); } }
            9 => while self.ab_acc >= 0.08 { self.ab_acc -= 0.08; let v = self.on_screen(); if v.is_empty() { break; }
                let i = v[(self.rand() * v.len() as f32) as usize % v.len()]; let (ex, ey, boss) = { let e = &self.en.items[i]; (e.x, e.y, e.kind.d().boss) };
                self.part(ex - 60., ey - 200., 300., 1000., 0.2, 14., c::GOLD, 0.); self.explode(ex, ey, 70., self.ab_dmg(boss) * 0.45, false); self.ring(ex, ey, 4., 60., 0.3, c::GOLD, 4.); }
            11 => if self.ab_acc >= 0.1 { self.ab_acc = 0.; let a = self.t * 9.; for q in 0..3 { let r = 140. + q as f32 * 120.; self.part(px + a.cos() * r, py + a.sin() * r, -a.sin() * 300., a.cos() * 300., 0.35, 16., c::AMETH, 2.); } }
            _ => {}
        }
        let _ = col;
    }
}
