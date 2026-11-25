//! 4.5: новые враги — Наутилус, Рак-отшельник, Конёк-снайпер, Каракатица, Рыба-шар.
//! Картинки: art_src/new45 → tools/newfoes.py (+ _t1/_t2) → rig.py (части). Отрисовка — render::foe45.
use crate::data::{c, K, TAU};
use crate::game::*;
use std::f32::consts::{FRAC_PI_2, PI};

pub const SEAHORSE_T: f32 = 1.05; // прицеливание конька
pub fn is_new(k: K) -> bool { matches!(k, K::Nautilus | K::Hermit | K::Seahorse | K::Cuttle | K::Puffer) }
fn steer(e: &mut Enemy, dvx: f32, dvy: f32, k: f32, dt: f32) { let a = 1. - (-dt * k).exp(); e.vx += (dvx - e.vx) * a; e.vy += (dvy - e.vy) * a; }

impl Game {
    pub fn init_foe45(&mut self, i: usize) {
        let ph = self.rr(0., TAU); let a = self.rr(1.5, 3.);
        let e = &mut self.en.items[i]; e.p1 = a; e.p3 = ph; e.state = 0; e.st = 0.;
        if e.kind == K::Cuttle { e.st = 1.5; }
    }
    /// true — враг убран (дальше по кадру не идти)
    pub fn update_foe45(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32, sp: f32, fz: bool) -> bool {
        let kind = self.en.items[i].kind; let tier = self.en.items[i].tier as f32; let dsc = self.dmg_scale; let (ex, ey) = (self.en.items[i].x, self.en.items[i].y); let face = uy.atan2(ux);
        match kind {
            // Наутилус: подплывает по спирали, раз в несколько секунд крутится и выпускает спираль чернил. Раковина сзади держит 70% урона.
            K::Nautilus => {
                let (spin, fire) = { let e = &mut self.en.items[i]; e.p1 -= dt; let mut fire = false;
                    if e.state == 0 { let orb = if d > 260. { 0.55 } else { 1.0 }; let (tx, ty) = (ux - uy * orb, uy + ux * orb); let l = (tx * tx + ty * ty).sqrt().max(0.01);
                        steer(e, tx / l * sp, ty / l * sp, 1.6, dt); e.ang += ang_diff(e.ang, face) * (dt * 3.).min(1.);
                        if e.p1 <= 0. && d < 520. && !fz { e.state = 1; e.st = 1.4; e.p2 = 0.; } }
                    else { steer(e, 0., 0., 3., dt); e.ang += dt * 6.5; e.st -= dt; e.p2 += dt; if e.p2 >= 0.11 - 0.02 * tier { e.p2 = 0.; fire = true; } if e.st <= 0. { e.state = 0; e.p1 = self.rng.next() * 1.5 + 3.2; } }
                    (e.state == 1, fire) };
                if spin && fire { let a = self.en.items[i].ang + PI; for k in 0..2 { self.e_shoot(ex, ey, a + k as f32 * PI, 130. + self.zone as f32 * 2. + 25. * tier, 6., 9. * dsc, c::PURP, 0.6); } }
            }
            // Рак-отшельник: идёт к тебе; если ты ближе 170 — прячется (почти неуязвим), отплывёшь дальше 250 — вылезает и стреляет залпом
            K::Hermit => {
                let (shoot, emerge) = { let e = &mut self.en.items[i]; let mut s = false; let mut em = false;
                    match e.state { 0 => { steer(e, ux * sp, uy * sp, 2., dt); e.ang += ang_diff(e.ang, face) * (dt * 2.5).min(1.); e.p1 -= dt;
                            if d < 170. && !fz { e.state = 1; e.st = 1.2; } else if e.p1 <= 0. && d < 600. { e.p1 = 2.2; s = true; } }
                        _ => { steer(e, 0., 0., 6., dt); e.st -= dt; if e.st <= 0. && d > 250. { e.state = 0; e.p1 = 0.35; em = true; } } }
                    (s, em) };
                if emerge { self.ring(ex, ey, 6., 46., 0.3, c::CORAL, 3.); }
                if shoot { let m = if tier > 0. { 2 } else { 1 }; for k in -m..=m { self.e_shoot(ex, ey, face + k as f32 * 0.2, 230., 6., 11. * dsc, c::CORAL, 0.); } self.snd(Sfx::Shot2); }
            }
            // Конёк-снайпер: держится на 380–480, целится 1 с (тонкая линия, последние 0.25 с — не двигается), стреляет быстрым лучом
            K::Seahorse => {
                let fire = { let e = &mut self.en.items[i]; let mut f = false;
                    let rad = if d < 360. { -1. } else if d > 480. { 1. } else { 0. };
                    match e.state { 0 => { steer(e, (ux * rad - uy * 0.35) * sp, (uy * rad + ux * 0.35) * sp, 1.8, dt); e.ang += ang_diff(e.ang, face) * (dt * 4.).min(1.); e.p1 -= dt;
                            if e.p1 <= 0. && d < 620. && !fz { e.state = 1; e.st = SEAHORSE_T - 0.2 * tier; } }
                        1 => { steer(e, 0., 0., 5., dt); e.st -= dt; if e.st > 0.25 { e.ang += ang_diff(e.ang, face) * (dt * 9.).min(1.); } if e.st <= 0. { e.state = 2; e.st = 0.5; f = true; } }
                        _ => { steer(e, -ux * sp * 0.6, -uy * sp * 0.6, 2., dt); e.st -= dt; if e.st <= 0. { e.state = 0; e.p1 = 2.4 + self.rng.next() * 1.2; } } }
                    f };
                if fire { let (a, r) = (self.en.items[i].ang, self.en.items[i].r); let (tx, ty) = (ex + a.cos() * r * 2.3, ey + a.sin() * r * 2.3);
                    if let Some(b) = self.e_shoot(tx, ty, a, 760., 7., 16. * dsc, c::GOLD, 0.) { self.eb.items[b].life = 1.6; }
                    self.ring(tx, ty, 4., 30., 0.2, c::GOLD, 3.); self.snd(Sfx::Shot2); self.en.items[i].vx -= a.cos() * 160.; self.en.items[i].vy -= a.sin() * 160.; }
            }
            // Каракатица: почти невидимой подкрадывается, вспыхивает (0.45 с) и бросается; потом видна, отходит и оставляет чернила
            K::Cuttle => {
                let (ink, lunge) = { let e = &mut self.en.items[i]; let mut ink = false; let mut lg = false; e.st -= dt;
                    match e.state { 0 => { steer(e, ux * sp * 1.1, uy * sp * 1.1, 2., dt); e.ang += ang_diff(e.ang, face) * (dt * 4.).min(1.); if d < 150. && e.st <= 0. && !fz { e.state = 1; e.st = 0.45; } }
                        1 => { steer(e, 0., 0., 6., dt); e.ang += ang_diff(e.ang, face) * (dt * 8.).min(1.); if e.st <= 0. { e.state = 2; e.st = 0.35; e.vx = e.ang.cos() * (560. + 70. * tier); e.vy = e.ang.sin() * (560. + 70. * tier); lg = true; } }
                        2 => { if e.st <= 0. { e.state = 3; e.st = 2.6; e.p2 = 0.; } }
                        _ => { steer(e, -ux * sp * 0.9, -uy * sp * 0.9, 1.6, dt); e.ang += ang_diff(e.ang, face + PI) * (dt * 3.).min(1.); e.p2 -= dt; if e.p2 <= 0. { e.p2 = 0.7; ink = true; } if e.st <= 0. { e.state = 0; e.st = 2.; } } }
                    (ink, lg) };
                if lunge { self.snd(Sfx::Dash); }
                if ink && self.inks.len() < 10 + 4 * tier as usize { self.inks.push((ex, ey, 5.)); }
            }
            // Рыба-шар: дрейфует к тебе; попадание раздувает её (крупнее, медленнее, касание больнее); раздутая при гибели — кольцо игл
            K::Puffer => {
                let e = &mut self.en.items[i]; let infl = e.p2 > 0.; if infl { e.p2 -= dt; }
                let w = (self.t * 1.3 + e.p3).sin() * 0.4; let s = sp * if infl { 0.35 } else { 1. };
                steer(e, (ux - uy * w) * s, (uy + ux * w) * s, 1.2, dt); e.ang += ang_diff(e.ang, face) * (dt * 2.).min(1.);
                let k = if infl { 1.75 } else { 1. }; let base = e.kind.d().r; e.r += (base * k - e.r) * (1. - (-dt * 9.).exp());
            }
            _ => {}
        }
        false
    }
    /// Урон по новым врагам: раковина наутилуса, спрятавшийся рак, раздувание рыбы-шара, каракатица проявляется
    pub fn foe45_hit(&mut self, i: usize, dmg: f32, from_ang: f32) -> f32 {
        let (k, ang, state) = { let e = &self.en.items[i]; (e.kind, e.ang, e.state) };
        match k {
            K::Nautilus if !from_ang.is_nan() && ang_diff(ang + PI, from_ang).abs() < 1.25 => { if self.rand() < 0.3 { self.snd(Sfx::Clink); } let (x, y) = (self.en.items[i].x, self.en.items[i].y); if self.rand() < 0.3 { self.part(x, y, 0., 0., 0.15, 6., c::GOLD, 0.); } dmg * 0.3 }
            K::Hermit if state == 1 => { if self.rand() < 0.3 { self.snd(Sfx::Clink); } dmg * if self.en.items[i].tier > 0 { 0.06 } else { 0.1 } }
            K::Puffer => { let e = &mut self.en.items[i]; if e.p2 <= 0. { e.dmg *= 1.4; } e.p2 = 3.; dmg }
            K::Cuttle if state == 0 => { let e = &mut self.en.items[i]; e.state = 3; e.st = 2.; e.p2 = 0.2; dmg * 1.25 } // засветилась — урон больше
            _ => dmg,
        }
    }
    pub fn foe45_death(&mut self, e: &Enemy) {
        if e.kind == K::Puffer && e.p2 > 0. { let n = 10 + self.zone.min(8); let o = self.rand() * TAU;
            for k in 0..n { self.e_shoot(e.x, e.y, o + k as f32 * TAU / n as f32, 170., 5., 9. * self.dmg_scale, c::URCH, 0.); }
            if e.tier > 0 { for k in 0..n { self.e_shoot(e.x, e.y, o + (k as f32 + 0.5) * TAU / n as f32, 120., 5., 9. * self.dmg_scale, c::URCH, 0.); } }
            self.ring(e.x, e.y, 6., 70., 0.35, c::URCH, 4.); self.snd(Sfx::Boom(false)); }
        if e.kind == K::Hermit { self.burst(e.x, e.y, 10, c::AMETH, 180., 7., 0.5); }
    }
    /// Чернила каракатицы: лужи 5 с, внутри игрок плывёт вдвое медленнее
    pub fn inks_tick(&mut self, dt: f32) {
        for k in self.inks.iter_mut() { k.2 -= dt; } self.inks.retain(|k| k.2 > 0.);
        let (px, py) = (self.p.x, self.p.y); self.p_ink = self.inks.iter().any(|&(x, y, t)| (x - px).powi(2) + (y - py).powi(2) < (58. * (t / 5.).min(1.).max(0.4)).powi(2));
    }
    /// Расставить новичков по глубине (в pick_kind): вес вида k на зоне z
    pub fn foe45_weight(&self, k: K, z: f32) -> f32 {
        match k { K::Puffer => if z >= 3. { 1.0 + z * 0.1 } else { 0. }, K::Nautilus => if z >= 4. { 0.8 + z * 0.1 } else { 0. },
            K::Hermit => if z >= 5. { 0.8 + z * 0.1 } else { 0. }, K::Seahorse => if z >= 6. && self.count_kind(K::Seahorse) < 3 { 0.7 + z * 0.08 } else { 0. },
            K::Cuttle => if z >= 7. && self.count_kind(K::Cuttle) < 4 { 0.7 + z * 0.08 } else { 0. }, _ => 0. }
    }
}
pub const FOE45: [K; 5] = [K::Puffer, K::Nautilus, K::Hermit, K::Seahorse, K::Cuttle];
#[allow(dead_code)] const _UNUSED: f32 = FRAC_PI_2;
