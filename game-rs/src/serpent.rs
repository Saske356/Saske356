//! 4.5: Левиафан — настоящий морской змей. Голова плывёт по плавным дугам (скорость поворота ограничена),
//! тело — лента текстуры, изогнутая вдоль следа головы (`Game::serp`). Попасть и удариться можно о любое место тела.
//! Картинка: art_src/tools/serpent.py → assets/spr/serp*.png. Отрисовка — render::serpent.
use crate::data::{c, cfg, K, TAU};
use crate::game::*;

/// Длина змея (мировые единицы) и шаг следа
pub const SERP_L: f32 = 660.;
const STEP: f32 = 7.;
/// Где на картинке «центр головы» (e.x, e.y): доля длины от хвоста (0) к носу (1)
pub const U_HEAD: f32 = 0.9;
/// Жёсткая часть головы (не гнётся): доля длины позади центра головы
const HEAD_RIGID: f32 = 0.12;

fn steer_ang(a: f32, to: f32, max: f32) -> f32 { a + ang_diff(a, to).clamp(-max, max) }

impl Game {
    /// Точка и направление на расстоянии s позади центра головы (s<0 — вперёд, к носу)
    pub fn serp_at(&self, i: usize, s: f32) -> (f32, f32, f32) {
        let e = &self.en.items[i]; let (ca, sa) = (e.ang.cos(), e.ang.sin());
        let straight = (e.x - ca * s, e.y - sa * s, e.ang);
        let rigid = SERP_L * HEAD_RIGID;
        if s <= rigid * 0.5 || self.serp.len() < 2 { return straight; }
        // по следу: идём по ломаной от головы
        let (mut px, mut py) = (e.x, e.y); let mut left = s; let mut ang = e.ang;
        for &(qx, qy) in self.serp.iter() {
            let (dx, dy) = (qx - px, qy - py); let d = (dx * dx + dy * dy).sqrt();
            if d < 1e-3 { continue; }
            if d >= left { let k = left / d; px += dx * k; py += dy * k; ang = (-dy).atan2(-dx); left = 0.; break; }
            left -= d; px = qx; py = qy; ang = (-dy).atan2(-dx);
        }
        if left > 0. { px -= ang.cos() * left; py -= ang.sin() * left; }
        // мягкий переход от жёсткой головы к телу
        if s < rigid { let k = ((s - rigid * 0.5) / (rigid * 0.5)).clamp(0., 1.); let k = k * k * (3. - 2. * k);
            return (straight.0 + (px - straight.0) * k, straight.1 + (py - straight.1) * k, straight.2 + ang_diff(straight.2, ang) * k); }
        (px, py, ang)
    }
    /// Узлы тела для попаданий: (x, y, радиус). Голова — крупнее, к хвосту тоньше.
    pub fn serp_nodes(&self, i: usize) -> Vec<(f32, f32, f32)> {
        let n = 18; let total = SERP_L * U_HEAD; let mut v = Vec::with_capacity(n);
        for k in 0..n { let f = k as f32 / (n - 1) as f32; let s = f * total * 0.97; let (x, y, _) = self.serp_at(i, s);
            let r = if f < 0.08 { 46. } else if f < 0.2 { 34. } else { 30. - 16. * ((f - 0.2) / 0.8) }; v.push((x, y, r)); }
        v
    }
    /// Узлы тела, посчитанные раз за кадр (пули, прицел, касание)
    pub fn serp_nodes_c(&self, i: usize) -> Vec<(f32, f32, f32)> { if self.serp_cache.is_empty() { self.serp_nodes(i) } else { self.serp_cache.clone() } }
    pub fn serp_idx(&self) -> Option<usize> { (0..self.en.n).find(|&i| { let e = &self.en.items[i]; !e.dead && e.kind == K::Boss4 }) }
    /// Пуля игрока попала в тело змея? → индекс змея
    pub fn serp_hit(&self, x: f32, y: f32, r: f32, last_uid: u32) -> Option<usize> {
        let i = self.serp_idx()?; let e = &self.en.items[i]; if e.uid == last_uid || e.spawn_t > 0.25 { return None; }
        if (e.x - x).abs() > SERP_L + 80. || (e.y - y).abs() > SERP_L + 80. { return None; }
        let c = if self.serp_cache.is_empty() { self.serp_nodes(i) } else { Vec::new() }; let nodes = if c.is_empty() { &self.serp_cache } else { &c };
        nodes.iter().any(|&(nx, ny, nr)| (nx - x).powi(2) + (ny - y).powi(2) < (nr + r).powi(2)).then_some(i)
    }
    /// Ближайшая к точке часть тела (для прицела)
    pub fn serp_aim(&self, i: usize, x: f32, y: f32) -> (f32, f32) {
        let c = if self.serp_cache.is_empty() { self.serp_nodes(i) } else { Vec::new() }; let nodes = if c.is_empty() { &self.serp_cache } else { &c };
        nodes.iter().map(|&(nx, ny, _)| (nx, ny)).min_by(|a, b| ((a.0 - x).powi(2) + (a.1 - y).powi(2)).total_cmp(&((b.0 - x).powi(2) + (b.1 - y).powi(2)))).unwrap_or((x, y))
    }
    fn serp_trail(&mut self, i: usize) {
        let (x, y, ang) = { let e = &self.en.items[i]; (e.x, e.y, e.ang) };
        let need = (SERP_L * 1.05 / STEP) as usize + 4;
        let far = self.serp.first().map(|&(qx, qy)| (qx - x).powi(2) + (qy - y).powi(2) > 160. * 160.).unwrap_or(true);
        if far || self.serp.len() < 2 { self.serp.clear(); for k in 1..need { let s = k as f32 * STEP; self.serp.push((x - ang.cos() * s, y - ang.sin() * s)); } return; }
        let (qx, qy) = self.serp[0]; let d = ((x - qx).powi(2) + (y - qy).powi(2)).sqrt();
        if d >= STEP { let n = (d / STEP) as usize; for k in 1..=n.min(8) { let f = k as f32 * STEP / d; self.serp.insert(0, (qx + (x - qx) * f, qy + (y - qy) * f)); } }
        self.serp.truncate(need);
    }

    /// Поведение: 0 — охота (дуги вокруг игрока, плевки из пасти), 1 — два броска с замахом,
    /// 2 — «чешуйчатый залп» (пули из боков по всей длине), 3 — свита. Ниже половины здоровья — злее.
    pub fn update_serpent(&mut self, i: usize, dt: f32) {
        let (px, py) = (self.p.x, self.p.y); let dsc = self.dmg_scale; let t = self.t;
        let (enr, state) = { let e = &mut self.en.items[i]; e.st -= dt; (e.hp < e.max_hp * 0.5, e.state) };
        let (ex, ey, ang) = { let e = &self.en.items[i]; (e.x, e.y, e.ang) };
        let to_p = (py - ey).atan2(px - ex); let dp = ((px - ex).powi(2) + (py - ey).powi(2)).sqrt();
        // держаться в арене: у края — разворот к центру
        let edge = (ex * ex + ey * ey).sqrt() > cfg::ARENA_R - 220.; let home = (-ey).atan2(-ex);
        let base = self.en.items[i].spd * if enr { 1.2 } else { 1. };
        let (mut speed, mut want, mut turn): (f32, f32, f32) = (base * 1.6, to_p, 1.6);
        match state {
            0 | 2 => { // кружит вокруг игрока по дуге, с волнистым ходом
                let orbit = { let e = &mut self.en.items[i]; e.p2 += dt * if state == 2 { 0.45 } else { 0.6 }; e.p2 };
                let r = if state == 2 { 330. } else { 270. }; let (tx, ty) = (px + (orbit + self.en.items[i].phase).cos() * r, py + (orbit + self.en.items[i].phase).sin() * r);
                want = (ty - ey).atan2(tx - ex) + (t * 2.6 + self.en.items[i].phase).sin() * 0.55; speed = base * if state == 2 { 1.25 } else { 1.7 }; turn = 2.0;
                let shoot = { let e = &mut self.en.items[i]; e.p1 -= dt; let s = e.p1 <= 0.; if s { e.p1 = if state == 2 { if enr { 0.42 } else { 0.58 } } else if enr { 1.15 } else { 1.6 }; } s };
                if shoot && state == 0 { // плевок веером из пасти
                    let (mx, my, _) = self.serp_at(i, -SERP_L * 0.06); let n = if enr { 7 } else { 5 };
                    for k in 0..n { self.e_shoot(mx, my, to_p + (k as f32 - (n - 1) as f32 / 2.) * 0.16, 210., 6., 11. * dsc, c::EEL, 0.); }
                    self.en.items[i].mouth = 0.45; self.snd(Sfx::Shot2); }
                if shoot && state == 2 { // пули из боков по всей длине, в обе стороны — стенки, между которыми надо проскочить
                    let nodes = 7; let ph = (t * 1.3) as i32 % 2;
                    for k in 0..nodes { if (k as i32 + ph) % 2 == 1 { continue; } let s = SERP_L * (0.18 + 0.68 * k as f32 / (nodes - 1) as f32); let (bx, by, ba) = self.serp_at(i, s);
                        for side in [-1f32, 1.] { self.e_shoot(bx, by, ba + side * std::f32::consts::FRAC_PI_2, 120. + if enr { 30. } else { 0. }, 6., 10. * dsc, c::ICE, 0.); } }
                    self.snd(Sfx::Shot2); }
            }
            1 => { // бросок: замах (медленно разворачивается к игроку, пасть раскрывается, видна линия) → рывок сквозь игрока
                let cyc = { let e = &mut self.en.items[i]; e.p3 += dt; e.p3 % 1.9 };
                if cyc < 1.05 { speed = base * 0.45; turn = 4.5; want = to_p; self.en.items[i].p1 = 0.; self.en.items[i].mouth = 1.; }
                else { if self.en.items[i].p1 == 0. { self.en.items[i].p1 = 1.; self.shake(8.); self.snd(Sfx::Dash); self.vibrate(40);
                        for k in -2..=2 { self.e_shoot(ex, ey, ang + k as f32 * 0.2, 240., 6., 11. * dsc, c::EEL, 0.); } }
                    speed = base * if enr { 5.6 } else { 4.8 }; turn = 0.35; want = to_p; self.en.items[i].mouth = 0.6;
                    if self.quality > 0 && self.rand() < 0.7 { self.part(ex, ey, 0., 0., 0.4, 26., c::EEL, 0.); } }
            }
            _ => { // свита
                speed = base * 0.6; want = to_p + 1.2;
                let go = { let e = &mut self.en.items[i]; let g = e.p3 != 9.; if g { e.p3 = 9.; } g };
                if go { let n = if enr { 5 } else { 3 }; for _ in 0..n { let a = self.rr(0., TAU); let k = if self.rand() < 0.5 { K::Dart } else { K::Bomber };
                        if let Some(s) = self.spawn_enemy(k, ex + a.cos() * 120., ey + a.sin() * 120., false) { self.en.items[s].spawn_t = 0.3; } }
                    self.ring(ex, ey, 20., 200., 0.5, c::EEL, 5.); self.snd(Sfx::Warn); }
            }
        }
        if edge { want = home; turn = turn.max(2.4); }
        if dp > 900. && state != 1 { want = to_p; turn = turn.max(2.2); speed = speed.max(base * 2.2); }
        { let e = &mut self.en.items[i]; e.ang = steer_ang(e.ang, want, turn * dt); let v = (e.vx * e.vx + e.vy * e.vy).sqrt(); let v = v + (speed - v) * (1. - (-dt * 3.).exp());
          e.vx = e.ang.cos() * v; e.vy = e.ang.sin() * v; if e.mouth > 0. { e.mouth -= dt; } }
        // касание тела ранит (голову проверяет общий код)
        if !self.p.dead && self.p.inv <= 0. { let pr = self.p.r; let dmg = self.en.items[i].dmg * 0.6;
            let hit = self.serp_nodes_c(i).iter().skip(3).any(|&(nx, ny, nr)| (nx - px).powi(2) + (ny - py).powi(2) < (nr * 0.8 + pr).powi(2));
            if hit { self.hurt_player(dmg); } }
        let e = &mut self.en.items[i];
        if e.st <= 0. { e.state = (e.state + 1) % 4; e.st = [5.0, 3.8, 3.6, 1.2][e.state as usize]; e.p1 = if e.state == 1 { 0. } else { 0.4 }; e.p3 = 0.; }
        self.serp_trail(i); self.serp_cache = self.serp_nodes(i);
    }
    /// Гибель змея — взрывы вдоль всего тела
    pub fn serp_death(&mut self, i: usize) {
        let nodes = self.serp_nodes(i);
        for (k, &(x, y, r)) in nodes.iter().enumerate() { if k % 2 == 0 { self.burst(x, y, 10, c::EEL, 200. + r * 3., 9., 0.7); self.ring(x, y, r * 0.5, r * 2.4, 0.5, c::ICE, 3.); } }
        self.serp.clear(); self.serp_cache.clear();
    }
}
