//! 4.9.1: суперспособности искр. У каждой — своя механика, которой нет среди улучшений забега, своя графика в мире,
//! своя иконка и цвет на кнопке. Заряд как у прежней «Вспышки» (убийства, пули впритирку). У каждой есть защитная часть.
use crate::data::{c, CHARS, PAL_HEX, PI, TAU};
use crate::gfx::hex;
use crate::game::*;
use crate::gfx::Gfx;
use crate::i18n;
use macroquad::prelude::*;

pub struct AbDef { pub ru: (&'static str, &'static str, &'static str), pub en: (&'static str, &'static str, &'static str), pub col: u8 }
/// (имя на кнопку, полное имя, описание) — по порядку CHARS
pub static ABILITIES: [AbDef; 14] = [
    AbDef { ru: ("ВСПЫШКА", "Вспышка", "сжигает всё на экране и стирает все пули"), en: ("FLARE", "Flare", "burns everything on screen and erases all bullets"), col: c::GOLD },
    AbDef { ru: ("ПРОКОЛ", "Пронзающий бросок", "три молниеносных броска сквозь самых сильных врагов: в бросках тебя не задеть, всё на пути пробито"), en: ("PIERCE", "Piercing lunge", "three lightning lunges through the strongest foes: untouchable while lunging, everything in the way is pierced"), col: c::EMER },
    AbDef { ru: ("ЗЕРКАЛО", "Зеркальный панцирь", "5 с урон по тебе −85%, а вражеские пули отражаются обратно во врагов"), en: ("MIRROR", "Mirror shell", "5 s of −85% damage taken, and enemy bullets bounce back into foes"), col: c::AMBER },
    AbDef { ru: ("ВОЛНА", "Ударная волна", "огромная волна веером сметает врагов и пули перед тобой"), en: ("BLAST", "Shockwave", "a huge fan-shaped wave sweeps foes and bullets away in front of you"), col: c::FIRE },
    AbDef { ru: ("КРЕПОСТЬ", "Крепость", "6 с купол: пули внутрь не проходят, враги внутри горят и выталкиваются, ты лечишься"), en: ("FORT", "Fortress", "a 6 s dome: bullets can't get in, foes inside burn and are pushed out, you heal inside"), col: c::CORAL },
    AbDef { ru: ("ШТОРМ", "Шторм", "все враги на экране оглушены на 3 с и бьются током, владыки — замедлены"), en: ("STUN", "Tempest", "every foe on screen is stunned for 3 s and shocked, lords are slowed"), col: c::ICE },
    AbDef { ru: ("ТЕНЬ", "Тень", "3,5 с тебя не задеть, ты быстрее и ранишь всех, сквозь кого плывёшь"), en: ("SHADE", "Shade", "for 3.5 s you can't be hit, move faster and hurt everyone you pass through"), col: c::GHOST },
    AbDef { ru: ("ФЕНИКС", "Феникс", "4 с за тобой горит огненный след: враги в нём горят, ты получаешь вдвое меньше урона"), en: ("PHOENIX", "Phoenix", "for 4 s you leave a trail of fire that burns foes, and take half damage"), col: c::CRAB },
    AbDef { ru: ("ЦУНАМИ", "Цунами", "волна отбрасывает всех врагов, замедляет их на 4 с и смывает все пули"), en: ("TSUNAMI", "Tsunami", "a wave hurls all foes away, slows them for 4 s and washes away all bullets"), col: c::DRIFT },
    AbDef { ru: ("СОЗВЕЗД.", "Созвездие", "6 звёзд вокруг соединяются лучами на 4 с: лучи жгут врагов и стирают пули"), en: ("STARS", "Constellation", "6 stars around you link with beams for 4 s: beams burn foes and erase bullets"), col: c::GOLD },
    AbDef { ru: ("ЧАКРА", "Чакра", "5 с вокруг тебя кружит огромный бумеранг, рвёт врагов и сбивает пули"), en: ("CHAKRA", "Chakra", "for 5 s a giant boomerang circles you, shredding foes and knocking down bullets"), col: c::AMBER },
    AbDef { ru: ("ЖНЕЦ", "Жнец", "призрачная коса дважды обходит круг: слабых (меньше 30% здоровья) срезает, остальных ранит, пули стирает"), en: ("REAPER", "Reaper", "a spectral scythe sweeps the circle twice: weak foes (under 30%) are cut down, the rest are hurt, bullets erased"), col: c::AMETH },
    AbDef { ru: ("СТАЯ", "Стая-хранитель", "7 с вокруг тебя кружат 6 рыб-стражей: ловят пули и кусают врагов; лечит 15%"), en: ("GUARD", "Guardian shoal", "for 7 s six guardian fish circle you, catching bullets and biting foes; heals 15%"), col: c::EMER },
    AbDef { ru: ("ВЗРЫВ", "Детонация", "через миг огромный взрыв вокруг тебя, и все твои мины взрываются вдвое шире; тебя не задеть"), en: ("BOOM", "Detonation", "a moment later a huge blast around you, and all your mines explode twice as wide; you're untouchable"), col: c::FIRE },
];
pub fn ab_idx(ch: &str) -> usize { CHARS.iter().position(|x| x.id == ch).unwrap_or(0).min(ABILITIES.len() - 1) }
pub fn ab_txt(i: usize) -> (&'static str, &'static str, &'static str) { if i18n::is_en() { ABILITIES[i].en } else { ABILITIES[i].ru } }
pub fn ab_col(i: usize) -> Color { hex(PAL_HEX[ABILITIES[i].col as usize]) }
/// Строка для карточки искры в магазине
pub fn ab_line(i: usize) -> String { let (_, n, d) = ab_txt(i); if i18n::is_en() { format!("Super: {n} — {d}.") } else { format!("Суперспособность «{n}»: {d}.") } }

const FORT_R: f32 = 170.; const REAP_R: f32 = 390.; const CHAKRA_R: f32 = 150.; const GUARD_R: f32 = 66.;

impl Game {
    fn ab_dmg(&self, boss: bool) -> f32 { if boss { 180. + self.st.dmg * 12. } else { 90. + self.st.dmg * 9. } }
    fn ab_clear(&mut self, r: f32) { let (px, py) = (self.p.x, self.p.y); self.ab_clear_at(px, py, r); }
    fn ab_clear_at(&mut self, x: f32, y: f32, r: f32) {
        let mut i = self.eb.n;
        while i > 0 { i -= 1; let b = &self.eb.items[i]; if (b.x - x).powi(2) + (b.y - y).powi(2) < r * r { let (bx, by) = (b.x, b.y); self.part(bx, by, 0., 0., 0.35, 8., c::WHITE, 2.); self.eb.kill(i); self.score += 3.; } }
    }
    fn on_screen(&self) -> Vec<usize> { (0..self.en.n).filter(|&i| { let e = &self.en.items[i]; !e.dead && e.spawn_t <= 0.2 && (e.x - self.cam_x).abs() < self.vw + 20. && (e.y - self.cam_y).abs() < self.vh + 20. }).collect() }
    /// урон всем врагам в круге (раз в тик), с долей от базового урона суперспособности
    fn ab_zone(&mut self, x: f32, y: f32, r: f32, k: f32, push: f32) {
        let q = self.qa(x, y, r + 40.);
        for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } let (dx, dy) = (e.x - x, e.y - y); let rr = r + e.r * e.scale; if dx * dx + dy * dy > rr * rr { continue; }
            let boss = e.kind.d().boss; let d = (dx * dx + dy * dy).sqrt().max(1.); let dmg = self.ab_dmg(boss) * k; let im = if boss { push * 0.2 } else { push };
            self.damage_enemy(i, dmg, false, f32::NAN, dx / d * im, dy / d * im, Src::None); }
        self.qa_back(q);
    }
    /// урон врагам у отрезка (лучи, броски)
    fn ab_seg(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, w: f32, k: f32) {
        let (mx, my) = ((x0 + x1) / 2., (y0 + y1) / 2.); let half = hypot(x1 - x0, y1 - y0) / 2. + w; let q = self.qa(mx, my, half + 40.);
        for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } let d = seg_dist(e.x, e.y, x0, y0, x1, y1); if d > w + e.r * e.scale { continue; }
            let boss = e.kind.d().boss; let dmg = self.ab_dmg(boss) * k; self.damage_enemy(i, dmg, true, f32::NAN, 0., 0., Src::None); }
        self.qa_back(q);
    }
    /// Суперспособность искры (кнопка снизу справа)
    pub fn do_ability(&mut self) {
        let k = ab_idx(&self.s.ch.clone()); if k == 0 { self.do_flare(false); return; }
        self.quest_add("flare", 1); self.p.flare = 0.; self.s.flares += 1; if self.s.flares >= 10 { self.unlock("flare10"); } if self.tut.on && self.tut.step == 4 { self.tut.v = 1.; }
        let col = ABILITIES[k].col; let (px, py) = (self.p.x, self.p.y);
        self.flash = self.flash.max(0.35); self.hit_stop = 0.1; self.shake(12.); self.snd(Sfx::Flare); self.vibrate(70);
        self.ring(px, py, 6., 140., 0.45, col, 6.); self.burst(px, py, 22, col, 300., 10., 0.6);
        // при первом применении — пояснение, что делает суперспособность
        let first = self.s.hints.get(&format!("ab{k}")).copied().unwrap_or(0) == 0; if first { self.s.hints.insert(format!("ab{k}"), 1); self.dirty = true; }
        let sub = if first { ab_txt(k).2.to_string() } else { String::new() }; self.banner(ab_txt(k).1.to_uppercase(), sub, PAL_HEX[col as usize], if first { 2.6 } else { 1.1 });
        self.ab_kind = k as u8; self.ab_acc = 0.; self.ab_k = 0; self.ab_x = px; self.ab_y = py; self.ab_hit.clear(); self.ab_pts.clear(); self.ab_seg.clear();
        let tg = self.nearest_enemy(px, py, 900.); self.ab_a = if tg >= 0 { let e = &self.en.items[tg as usize]; (e.y - py).atan2(e.x - px) } else { self.p.ang };
        match k {
            1 => { self.ab_t = 1.2; self.ab_clear(200.); self.p.inv = self.p.inv.max(1.3); }
            2 => { self.ab_t = 5.; self.ab_clear(120.); }
            3 => { self.ab_t = 0.75; self.ab_clear(120.); }
            4 => { self.ab_t = 6.; self.ab_clear_at(px, py, FORT_R); }
            5 => { self.ab_t = 3.; self.ab_clear(240.); for i in self.on_screen() { let e = &mut self.en.items[i]; if e.kind.d().boss { e.slow = 3.; } else { e.freeze = 3.; } } }
            6 => { self.ab_t = 3.5; self.p.inv = self.p.inv.max(3.5); self.ab_clear(160.); }
            7 => { self.ab_t = 4.; self.ab_clear(200.); self.ab_fire.clear(); }
            8 => { self.ab_t = 0.9; self.eb.clear(); let dm = self.ab_dmg(false) * 0.5;
                for i in self.on_screen() { let (dx, dy) = (self.en.items[i].x - px, self.en.items[i].y - py); let d = (dx * dx + dy * dy).sqrt().max(1.); let boss = self.en.items[i].kind.d().boss;
                    self.en.items[i].slow = 4.; let dmg = if boss { self.ab_dmg(true) * 0.5 } else { dm }; let im = if boss { 250. } else { 1100. }; self.damage_enemy(i, dmg, false, f32::NAN, dx / d * im, dy / d * im, Src::None); } }
            9 => { self.ab_t = 4.; self.ab_clear(220.); let o = self.rand() * TAU; for q in 0..6 { let a = o + q as f32 * TAU / 6.; self.ab_pts.push((px + a.cos() * 210., py + a.sin() * 210.)); } }
            10 => { self.ab_t = 5.; self.ab_clear(120.); }
            11 => { self.ab_t = 1.3; self.ab_clear(120.); }
            12 => { self.ab_t = 7.; self.ab_clear(160.); self.p.hp = (self.p.hp + self.p.max_hp * 0.15).min(self.p.max_hp); }
            _ => { self.ab_t = 0.7; self.p.inv = self.p.inv.max(1.); self.ab_clear(160.); }
        }
    }
    /// Длящиеся суперспособности (каждый кадр)
    pub fn ability_tick(&mut self, dt: f32) {
        // 4.9.6: суперспособность зарядилась — звук, вибрация, искорки вокруг кнопки видны и так
        let full = self.p.flare >= 100.; if full && !self.ab_ready { self.snd(Sfx::Ach); self.vibrate(35); let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 70., 0.4, ABILITIES[ab_idx(&self.s.ch.clone())].col, 4.); } self.ab_ready = full;
        for s in self.ab_seg.iter_mut() { s.4 -= dt; } self.ab_seg.retain(|s| s.4 > 0.);
        if !self.ab_fire.is_empty() { for f in self.ab_fire.iter_mut() { f.2 -= dt; } self.ab_fire.retain(|f| f.2 > 0.); self.ab_fire_t -= dt;
            if self.ab_fire_t <= 0. { self.ab_fire_t = 0.2; let fs = self.ab_fire.clone(); let burn = self.st.dmg * 1.2;
                for (x, y, _) in fs.iter().step_by(2) { let q = self.qa(*x, *y, 60.); for &i in &q { let e = &self.en.items[i]; if e.dead { continue; } if (e.x - x).powi(2) + (e.y - y).powi(2) > (30. + e.r * e.scale).powi(2) { continue; }
                    let boss = e.kind.d().boss; if !boss { let e = &mut self.en.items[i]; e.burn = e.burn.max(burn); e.burn_t = e.burn_t.max(2.5); } let dmg = self.ab_dmg(boss) * 0.05; self.damage_enemy(i, dmg, false, f32::NAN, 0., 0., Src::Burn); } self.qa_back(q); } } }
        if self.ab_t <= 0. { return; }
        self.ab_t -= dt; self.ab_acc += dt; let (px, py) = (self.p.x, self.p.y);
        match self.ab_kind {
            // Игла: три броска к сильнейшим целям (0.16 с бросок + 0.2 с пауза)
            1 => { let ph = self.ab_acc; let step = (ph / 0.36) as u32;
                if step < 3 && step >= self.ab_k { self.ab_k = step + 1;
                    let mut best = -1i32; let mut bh = -1.; for i in self.on_screen() { let e = &self.en.items[i]; if self.ab_hit.contains(&e.uid) { continue; } let h = e.hp + if e.kind.d().boss { 1e5 } else { 0. }; if h > bh { bh = h; best = i as i32; } }
                    let (tx, ty) = if best >= 0 { let e = &self.en.items[best as usize]; self.ab_hit.push(e.uid); (e.x, e.y) } else { (px + self.ab_a.cos() * 300., py + self.ab_a.sin() * 300.) };
                    let a = (ty - py).atan2(tx - px); let d = hypot(tx - px, ty - py) + 90.; let (ex, ey) = (px + a.cos() * d, py + a.sin() * d);
                    let lim = crate::data::cfg::ARENA_R - 30.; let (ex, ey) = { let l = hypot(ex, ey); if l > lim { (ex / l * lim, ey / l * lim) } else { (ex, ey) } };
                    self.ab_seg(px, py, ex, ey, 34., 0.9); self.ab_seg.push((px, py, ex, ey, 0.5)); self.ab_clear_at((px + ex) / 2., (py + ey) / 2., hypot(ex - px, ey - py) / 2.);
                    self.p.x = ex; self.p.y = ey; self.p.vx = a.cos() * 300.; self.p.vy = a.sin() * 300.; self.p.ang = a; self.p.inv = self.p.inv.max(0.4);
                    self.snd(Sfx::Dash); self.shake(8.); self.burst(ex, ey, 14, c::EMER, 260., 8., 0.4); } }
            // Панцирь: пули у тела отражаются обратно
            2 => { let mut i = self.eb.n; while i > 0 { i -= 1; let b = self.eb.items[i].clone(); if (b.x - px).powi(2) + (b.y - py).powi(2) < 52. * 52. {
                        self.eb.kill(i); let a = b.vy.atan2(b.vx) + PI; if let Some(j) = self.fire_pb(b.x, b.y, a, self.st.dmg * 2., false) { self.pb.items[j].pierce = 2; } self.part(b.x, b.y, 0., 0., 0.25, 10., c::AMBER, 1.); } } }
            // Шквал: фронт волны уходит веером вперёд
            3 => { let d0 = 900. * ((self.ab_acc - dt) / 0.75).clamp(0., 1.); let d1 = 900. * (self.ab_acc / 0.75).min(1.); let a = self.ab_a; let (ox, oy) = (self.ab_x, self.ab_y);
                for i in self.on_screen() { let e = &self.en.items[i]; if self.ab_hit.contains(&e.uid) { continue; } let (dx, dy) = (e.x - ox, e.y - oy); let d = hypot(dx, dy);
                    if d >= d0 - e.r && d <= d1 + e.r && ang_diff(a, dy.atan2(dx)).abs() < 0.62 { let (uid, boss) = (e.uid, e.kind.d().boss); self.ab_hit.push(uid); let dmg = self.ab_dmg(boss) * 1.1; let im = if boss { 200. } else { 900. };
                        self.damage_enemy(i, dmg, true, f32::NAN, a.cos() * im, a.sin() * im, Src::None); } }
                let mut i = self.eb.n; while i > 0 { i -= 1; let b = &self.eb.items[i]; let (dx, dy) = (b.x - ox, b.y - oy); let d = hypot(dx, dy); if d <= d1 + 10. && ang_diff(a, dy.atan2(dx)).abs() < 0.62 { self.eb.kill(i); } } }
            // Страж: купол на месте каста
            4 => { let (fx, fy) = (self.ab_x, self.ab_y); let mut i = self.eb.n;
                while i > 0 { i -= 1; let b = &self.eb.items[i]; let d2 = (b.x - fx).powi(2) + (b.y - fy).powi(2); if d2 < FORT_R * FORT_R { let (bx, by) = (b.x, b.y); self.eb.kill(i); self.part(bx, by, 0., 0., 0.3, 10., c::CORAL, 1.); } }
                if self.ab_acc >= 0.25 { self.ab_acc = 0.; self.ab_zone(fx, fy, FORT_R, 0.12, 380.);
                    if (px - fx).powi(2) + (py - fy).powi(2) < FORT_R * FORT_R { self.p.hp = (self.p.hp + self.p.max_hp * 0.01).min(self.p.max_hp); } } }
            // Буря: ток по всем оглушённым
            5 => if self.ab_acc >= 0.3 { self.ab_acc = 0.; let v = self.on_screen(); let mut n = 0;
                for i in v { let e = &self.en.items[i]; if e.freeze <= 0. && e.slow <= 0. { continue; } let (ex, ey, boss) = (e.x, e.y, e.kind.d().boss);
                    if n < 8 { self.bolt(px, py, ex, ey, c::ICE); } n += 1; let dmg = self.ab_dmg(boss) * 0.16; self.damage_enemy(i, dmg, false, f32::NAN, 0., 0., Src::None); }
                if n > 0 { self.snd(Sfx::Hit); } }
            // Призрак: урон касанием
            6 => { self.p.inv = self.p.inv.max(self.ab_t.max(0.)); if self.ab_acc >= 0.1 { self.ab_acc = 0.; self.ab_zone(px, py, 30., 0.25, 0.); } }
            // Уголёк: огненный след
            7 => if self.ab_acc >= 0.06 { self.ab_acc = 0.; if self.ab_fire.len() < 90 { self.ab_fire.push((px, py, 3.)); } }
            // Звёздочка: лучи созвездия
            9 => { let pts = self.ab_pts.clone(); let n = pts.len(); if n == 6 {
                    let segs: Vec<(usize, usize)> = (0..6).map(|i| (i, (i + 2) % 6)).collect();
                    for &(a, b) in &segs { let (x0, y0) = pts[a]; let (x1, y1) = pts[b]; let mut j = self.eb.n; while j > 0 { j -= 1; let e = &self.eb.items[j]; if seg_dist(e.x, e.y, x0, y0, x1, y1) < 12. { self.eb.kill(j); } } }
                    if self.ab_acc >= 0.2 { self.ab_acc = 0.; for &(a, b) in &segs { let (x0, y0) = pts[a]; let (x1, y1) = pts[b]; self.ab_seg(x0, y0, x1, y1, 16., 0.12); } } } }
            // Бумеранг: огромная чакра вокруг
            10 => { self.ab_a += dt * 4.2; let (cx, cy) = (px + self.ab_a.cos() * CHAKRA_R, py + self.ab_a.sin() * CHAKRA_R); self.ab_clear_at(cx, cy, 64.);
                if self.ab_acc >= 0.12 { self.ab_acc = 0.; self.ab_zone(cx, cy, 58., 0.22, 300.); } }
            // Коса: призрачная коса обходит круг дважды
            11 => { let prev = self.ab_a; let sweep = TAU * 2. / 1.3; self.ab_a += dt * sweep;
                if (self.ab_a - prev).abs() > 0. && ((self.ab_a / TAU) as i32) != ((prev / TAU) as i32) { self.ab_hit.clear(); }
                let (a0, a1) = (prev, self.ab_a);
                for i in self.on_screen() { let e = &self.en.items[i]; if self.ab_hit.contains(&e.uid) { continue; } let (dx, dy) = (e.x - px, e.y - py); let d = hypot(dx, dy); if d > REAP_R + e.r || d < 20. { continue; }
                    let ea = dy.atan2(dx); let rel = (ea - a0).rem_euclid(TAU); if rel > (a1 - a0) + 0.08 { continue; }
                    let (uid, boss, weak, hp) = (e.uid, e.kind.d().boss, !e.kind.d().boss && e.hp < e.max_hp * 0.3, e.hp); self.ab_hit.push(uid);
                    let dmg = if weak { hp + 1e6 } else { self.ab_dmg(boss) * 0.8 }; self.damage_enemy(i, dmg, true, f32::NAN, dx / d.max(1.) * 260., dy / d.max(1.) * 260., Src::None); }
                let mut j = self.eb.n; while j > 0 { j -= 1; let b = &self.eb.items[j]; let (dx, dy) = (b.x - px, b.y - py); if hypot(dx, dy) > REAP_R { continue; } let rel = (dy.atan2(dx) - a0).rem_euclid(TAU); if rel <= (a1 - a0) + 0.08 { self.eb.kill(j); } } }
            // Матерь: стражи кружат вокруг
            12 => { self.ab_a += dt * 3.; for q in 0..6 { let a = self.ab_a + q as f32 * TAU / 6.; let (gx, gy) = (px + a.cos() * GUARD_R, py + a.sin() * GUARD_R); self.ab_clear_at(gx, gy, 24.); }
                if self.ab_acc >= 0.2 { self.ab_acc = 0.; for q in 0..6 { let a = self.ab_a + q as f32 * TAU / 6.; let (gx, gy) = (px + a.cos() * GUARD_R, py + a.sin() * GUARD_R); self.ab_zone(gx, gy, 26., 0.15, 260.); } } }
            // Минёр: отсчёт и большой взрыв
            13 => { self.p.inv = self.p.inv.max(0.3); if self.ab_t <= 0. { let (bx, by) = (px, py);
                    for m in 0..self.mines.n { let mm = &mut self.mines.items[m]; mm.inst = true; mm.r *= 2.; }
                    self.ab_clear(320.); self.ab_zone(bx, by, 280., 1.4, 900.); self.flash = self.flash.max(0.6); self.shake(26.); self.snd(Sfx::Boom(true)); self.vibrate(110);
                    self.ring(bx, by, 10., 300., 0.6, c::FIRE, 14.); self.ring(bx, by, 10., 220., 0.5, c::GOLD, 8.); self.burst(bx, by, 50, c::FIRE, 520., 14., 0.8); } }
            _ => {}
        }
    }
}
fn seg_dist(px: f32, py: f32, x0: f32, y0: f32, x1: f32, y1: f32) -> f32 {
    let (dx, dy) = (x1 - x0, y1 - y0); let l2 = (dx * dx + dy * dy).max(1e-3); let t = (((px - x0) * dx + (py - y0) * dy) / l2).clamp(0., 1.);
    hypot(px - (x0 + dx * t), py - (y0 + dy * t))
}
fn wa(c: Color, a: f32) -> Color { Color::new(c.r, c.g, c.b, c.a * a) }

/// Графика суперспособностей в мире (поверх существ, под интерфейсом)
pub fn draw_world(gx: &mut Gfx, g: &Game) {
    let t = g.t; let (px, py) = (g.p.x, g.p.y);
    for s in &g.ab_seg { let k = (s.4 / 0.5).clamp(0., 1.); gx.line_world(s.0, s.1, s.2, s.3, 22. * k, wa(hex(0x7dffb0), 0.35 * k), true); gx.line_world(s.0, s.1, s.2, s.3, 6. * k, wa(WHITE, 0.9 * k), true); }
    for f in &g.ab_fire { let k = (f.2 / 3.).clamp(0., 1.); let fl = 0.8 + 0.2 * (t * 14. + f.0 * 0.1).sin(); gx.glow_world(true, c::FIRE, f.0, f.1, 34. * fl, 0.55 * k); gx.glow_world(false, c::GOLD, f.0, f.1, 12. * fl, 0.7 * k); }
    if g.ab_t <= 0. { return; }
    let k = g.ab_kind as usize; let col = ab_col(k); let cu = ABILITIES[k].col;
    match k {
        2 => { let r = 40. + 2. * (t * 6.).sin(); for q in 0..6 { let a0 = t * 1.5 + q as f32 * TAU / 6.; let a1 = a0 + TAU / 6.; gx.line_world(px + a0.cos() * r, py + a0.sin() * r, px + a1.cos() * r, py + a1.sin() * r, 4., wa(col, 0.9), true); }
            gx.glow_world(true, cu, px, py, 60., 0.35); }
        3 => { let d = 900. * (g.ab_acc / 0.75).min(1.); let a = g.ab_a; let al = 1. - (g.ab_acc / 0.75).min(1.) * 0.6;
            for w in 0..3 { let rr = (d - w as f32 * 26.).max(10.); gx.arc_world(g.ab_x, g.ab_y, rr, a - 0.62, a + 0.62, 14. - w as f32 * 4., wa(if w == 0 { WHITE } else { col }, al * (0.9 - w as f32 * 0.25)), true); } }
        4 => { let (fx, fy) = (g.ab_x, g.ab_y); let al = (g.ab_t / 0.5).min(1.); gx.circle_world(fx, fy, FORT_R, wa(col, 0.08 * al), true);
            gx.arc_world(fx, fy, FORT_R, 0., TAU, 5., wa(col, 0.85 * al), true); gx.dashed_arc_world(fx, fy, FORT_R - 10., t * 0.8, 3., 14., 10., wa(WHITE, 0.5 * al));
            for q in 0..6 { let a = q as f32 * TAU / 6. + t * 0.3; gx.line_world(fx + a.cos() * 30., fy + a.sin() * 30., fx + a.cos() * FORT_R, fy + a.sin() * FORT_R, 2., wa(col, 0.25 * al), true); } }
        5 => { for i in 0..g.en.n { let e = &g.en.items[i]; if e.dead || e.freeze <= 0. { continue; } let a = t * 5. + i as f32;
                for q in 0..3 { let aa = a + q as f32 * TAU / 3.; let r = e.r * e.scale + 8.; gx.glow_world(false, c::ICE, e.x + aa.cos() * r, e.y + aa.sin() * r * 0.6 - e.r * 0.8, 4., 0.9); } } }
        6 => { for q in 1..6 { let j = (g.trail_head + 12 - q * 2) % 12; gx.glow_world(true, c::GHOST, g.trail[j * 2], g.trail[j * 2 + 1], 26. - q as f32 * 3., 0.35 - q as f32 * 0.05); } }
        7 => { gx.glow_world(true, c::FIRE, px, py, 70. + 8. * (t * 10.).sin(), 0.5); }
        9 => { let pts = &g.ab_pts; if pts.len() == 6 { let al = (g.ab_t / 0.4).min(1.);
                for i in 0..6 { let (x0, y0) = pts[i]; let (x1, y1) = pts[(i + 2) % 6]; gx.line_world(x0, y0, x1, y1, 10., wa(col, 0.25 * al), true); gx.line_world(x0, y0, x1, y1, 3., wa(WHITE, 0.85 * al), true); }
                for &(x, y) in pts { gx.glow_world(true, c::GOLD, x, y, 30. + 6. * (t * 6.).sin(), 0.8 * al); gx.glow_world(false, c::WHITE, x, y, 8., al); } } }
        10 => { let (cx, cy) = (px + g.ab_a.cos() * CHAKRA_R, py + g.ab_a.sin() * CHAKRA_R); let spin = t * 18.;
            gx.glow_world(true, cu, cx, cy, 70., 0.5); for q in 0..4 { let a = spin + q as f32 * TAU / 4.; gx.arc_world(cx + a.cos() * 18., cy + a.sin() * 18., 40., a + 0.4, a + 2.0, 9., wa(col, 0.95), true); }
            gx.circle_world(cx, cy, 10., wa(WHITE, 0.9), true); gx.arc_world(px, py, CHAKRA_R, 0., TAU, 1.5, wa(col, 0.2), true); }
        11 => { let a = g.ab_a; let tail = 1.2; for q in 0..10 { let aa = a - tail * q as f32 / 10.; let al = 0.5 * (1. - q as f32 / 10.); gx.line_world(px + aa.cos() * 70., py + aa.sin() * 70., px + aa.cos() * REAP_R, py + aa.sin() * REAP_R, 10., wa(col, al), true); }
            gx.line_world(px + a.cos() * 60., py + a.sin() * 60., px + a.cos() * REAP_R, py + a.sin() * REAP_R, 6., wa(WHITE, 0.95), true);
            gx.arc_world(px, py, REAP_R, a - 0.35, a + 0.05, 12., wa(col, 0.9), true); gx.arc_world(px, py, REAP_R - 16., a - 0.3, a, 6., wa(WHITE, 0.8), true); }
        12 => { for q in 0..6 { let a = g.ab_a + q as f32 * TAU / 6.; let (fx, fy) = (px + a.cos() * GUARD_R, py + a.sin() * GUARD_R); gx.glow_world(true, c::EMER, fx, fy, 20., 0.5); gx.spr_world("fry", fx, fy, a + PI / 2., 2.1, 1., false, t * 9. + q as f32, false); } }
        13 => { let kk = 1. - (g.ab_t / 0.7).clamp(0., 1.); gx.arc_world(px, py, 280., 0., TAU, 3. + 6. * kk, wa(col, 0.4 + 0.5 * kk), true); gx.circle_world(px, py, 280. * kk, wa(col, 0.12), true);
            gx.glow_world(true, c::FIRE, px, py, 60. + 60. * kk, 0.6); }
        _ => {}
    }
    gx.set_add(false);
}

/// Иконка суперспособности (экранные координаты в логических пикселях): на кнопке и в магазине
pub fn draw_icon(gx: &mut Gfx, k: usize, x: f32, y: f32, s: f32, col: Color) {
    let p = gx.px; gx.set_add(false);
    let ln = |a: (f32, f32), b: (f32, f32), w: f32| draw_line((x + a.0 * s) * p, (y + a.1 * s) * p, (x + b.0 * s) * p, (y + b.1 * s) * p, w * p, col);
    let ring = |cx: f32, cy: f32, r: f32, w: f32| draw_circle_lines((x + cx * s) * p, (y + cy * s) * p, r * s * p, w * p, col);
    let dot = |cx: f32, cy: f32, r: f32| draw_circle((x + cx * s) * p, (y + cy * s) * p, r * s * p, col);
    let arc = |r: f32, a0: f32, a1: f32, w: f32| { let n = 14; for i in 0..n { let (t0, t1) = (a0 + (a1 - a0) * i as f32 / n as f32, a0 + (a1 - a0) * (i + 1) as f32 / n as f32);
        draw_line((x + t0.cos() * r * s) * p, (y + t0.sin() * r * s) * p, (x + t1.cos() * r * s) * p, (y + t1.sin() * r * s) * p, w * p, col); } };
    match k {
        0 => { let pts = [(0., -1.), (0.26, -0.3), (1., 0.), (0.26, 0.22), (0., 1.), (-0.22, 0.22), (-1., 0.), (-0.22, -0.3)];
            for i in 0..8 { let (a0, a1) = (pts[i], pts[(i + 1) % 8]); draw_triangle(vec2(x * p, y * p), vec2((x + a0.0 * s) * p, (y + a0.1 * s) * p), vec2((x + a1.0 * s) * p, (y + a1.1 * s) * p), col); } }
        1 => { ln((-0.9, 0.9), (0.7, -0.7), 3.); draw_triangle(vec2((x + 1. * s) * p, (y - 1. * s) * p), vec2((x + 0.35 * s) * p, (y - 0.75 * s) * p), vec2((x + 0.75 * s) * p, (y - 0.35 * s) * p), col);
            ln((-0.9, 0.3), (-0.3, -0.3), 2.); ln((-0.3, 0.9), (0.3, 0.3), 2.); }
        2 => { for i in 0..6 { let a0 = i as f32 * TAU / 6. - PI / 2.; let a1 = a0 + TAU / 6.; ln((a0.cos() * 0.95, a0.sin() * 0.95), (a1.cos() * 0.95, a1.sin() * 0.95), 3.); } ln((-0.35, 0.35), (0.4, -0.4), 2.5); ln((0.4, -0.4), (0.4, 0.05), 2.5); ln((0.4, -0.4), (-0.05, -0.4), 2.5); }
        3 => { for w in 0..3 { arc(0.4 + w as f32 * 0.3, -0.7, 0.7, 2.6); } dot(-0.75, 0., 0.18); }
        4 => { arc(0.9, PI, TAU, 3.); ln((-0.95, 0.15), (0.95, 0.15), 3.); ln((-0.45, -0.75), (-0.45, 0.15), 2.); ln((0.45, -0.75), (0.45, 0.15), 2.); ln((0., -0.9), (0., 0.15), 2.); }
        5 => { ln((0.25, -1.), (-0.35, 0.05), 3.); ln((-0.35, 0.05), (0.25, 0.05), 3.); ln((0.25, 0.05), (-0.25, 1.), 3.); ring(0., 0., 0.95, 1.5); }
        6 => { arc(0.6, PI, TAU, 3.); ln((-0.6, 0.), (-0.6, 0.8), 3.); ln((0.6, 0.), (0.6, 0.8), 3.); ln((-0.6, 0.8), (-0.3, 0.55), 2.5); ln((-0.3, 0.55), (0., 0.8), 2.5); ln((0., 0.8), (0.3, 0.55), 2.5); ln((0.3, 0.55), (0.6, 0.8), 2.5);
            dot(-0.22, -0.15, 0.12); dot(0.22, -0.15, 0.12); }
        7 => { ln((0., -1.), (0.55, 0.1), 3.); ln((0.55, 0.1), (0.3, 0.85), 3.); ln((0.3, 0.85), (-0.3, 0.85), 3.); ln((-0.3, 0.85), (-0.55, 0.1), 3.); ln((-0.55, 0.1), (-0.2, -0.35), 3.); ln((-0.2, -0.35), (0., -1.), 3.);
            ln((0., 0.75), (0., 0.1), 2.); }
        8 => { for w in 0..2 { let yy = -0.2 + w as f32 * 0.55; let n = 8; for i in 0..n { let (a, b) = (i as f32 / n as f32, (i + 1) as f32 / n as f32); ln((-1. + 2. * a, yy + (a * TAU).sin() * 0.22), (-1. + 2. * b, yy + (b * TAU).sin() * 0.22), 3.); } } }
        9 => { let pts: Vec<(f32, f32)> = (0..6).map(|i| { let a = i as f32 * TAU / 6. - PI / 2.; (a.cos() * 0.9, a.sin() * 0.9) }).collect(); for i in 0..6 { ln(pts[i], pts[(i + 2) % 6], 1.8); } for &q in &pts { dot(q.0, q.1, 0.16); } }
        10 => { for q in 0..4 { let a = q as f32 * TAU / 4.; let (cx, cy) = (a.cos() * 0.25, a.sin() * 0.25); let n = 6; for i in 0..n { let (t0, t1) = (a + 0.3 + 1.4 * i as f32 / n as f32, a + 0.3 + 1.4 * (i + 1) as f32 / n as f32); ln((cx + t0.cos() * 0.65, cy + t0.sin() * 0.65), (cx + t1.cos() * 0.65, cy + t1.sin() * 0.65), 3.); } } dot(0., 0., 0.18); }
        11 => { ln((-0.6, 1.), (0.15, -0.6), 3.); arc(0.75, -PI * 0.95, -PI * 0.2, 3.5); let a = -PI * 0.2; ln((0.15, -0.6), (a.cos() * 0.75, a.sin() * 0.75), 2.); }
        12 => { for q in 0..3 { let a = q as f32 * TAU / 3. - PI / 2.; let (cx, cy) = (a.cos() * 0.55, a.sin() * 0.55); dot(cx, cy, 0.22); ln((cx, cy), (cx - a.sin() * 0.45, cy + a.cos() * 0.45), 2.5); } ring(0., 0., 0.95, 1.5); }
        _ => { ring(0., 0.15, 0.7, 3.); ln((0.45, -0.4), (0.75, -0.85), 2.5); dot(0.8, -0.92, 0.16); ln((-0.25, 0.), (0.25, 0.3), 2.); ln((0.25, 0.), (-0.25, 0.3), 2.); }
    }
}
