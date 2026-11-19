//! Новые улучшения забега: Залп, Самонаводки, Калибр, Добивание, Иней, Ударная волна, Метка охотника,
//! Ловец удачи и их синергии — Ураган, Бомбардировка, Жнец, Метель.
use crate::data::{c, u, K, TAU};
use crate::game::*;

impl Game {
    /// После каждого выстрела
    pub fn on_shot(&mut self, px: f32, py: f32, a: f32) {
        let l = self.lv(u::SALVO); if l == 0 { return; }
        self.p.salvo_n += 1; let every = 8 - l.min(3) as u32; // 7, 6, 5
        if self.p.salvo_n % every != 0 { return; }
        let hur = self.lv(u::HURRICANE) > 0; let n = if hur { 16 } else { 8 };
        for k in 0..n { if let Some(b) = self.fire_pb(px, py, a + k as f32 * TAU / n as f32, self.st.dmg * 0.7, false) { if hur { self.pb.items[b].pierce += 2; } } }
        self.ring(px, py, 6., 60., 0.3, self.p.pal, 3.);
    }
    /// Каждый кадр забега
    pub fn update_upg2(&mut self, dt: f32) {
        // ракеты
        let sl = self.lv(u::SEEKER);
        if sl > 0 { self.p.seek_t -= dt; if self.p.seek_t <= 0. { let tg = self.nearest_enemy(self.p.x, self.p.y, 600.); self.p.seek_t = if tg >= 0 { 3.4 - 0.5 * sl as f32 } else { 0.5 };
            if tg >= 0 { let bomb = self.lv(u::BOMBARD) > 0; let n = sl + if bomb { 2 } else { 0 }; let (px, py) = (self.p.x, self.p.y);
                let e = &self.en.items[tg as usize]; let a0 = (e.y - py).atan2(e.x - px);
                for k in 0..n { let a = a0 + (k as f32 - (n - 1) as f32 / 2.) * 0.5 + std::f32::consts::PI * 0.0;
                    if let Some(b) = self.fire_pb(px, py, a, self.st.dmg * (2.2 + 0.4 * sl as f32), false) { let bb = &mut self.pb.items[b]; bb.boom = if bomb { 95. } else { 62. }; bb.r = 6.; bb.life = 2.2; bb.pierce = 0; bb.bounce = 0;
                        let s = 380.; bb.vx = a.cos() * s; bb.vy = a.sin() * s; bb.tgt = -1; } }
                self.snd(Sfx::Shot2); } } }
        // ударная волна в конце рывка
        let dl = self.lv(u::DASHNOVA);
        if dl > 0 { let dashing = self.p.dash_t > 0.; if self.p.was_dash && !dashing { let r = 110. + 30. * dl as f32; let dm = self.st.dmg * (2. + dl as f32); let (x, y) = (self.p.x, self.p.y);
                self.ring(x, y, 10., r, 0.4, c::JELLY, 5.); self.snd(Sfx::Nova);
                let q = self.qa(x, y, r + 40.); for &i in &q { let (dead, ex, ey, er) = { let e = &self.en.items[i]; (e.dead, e.x, e.y, e.r * e.scale) };
                    if dead { continue; } let (dx, dy) = (ex - x, ey - y); let d = hypot(dx, dy); if d < r + er { let dd = d.max(1.); self.damage_enemy(i, dm, false, f32::NAN, dx / dd * 300., dy / dd * 300., Src::Nova); } } self.qa_back(q);
                let mut i = self.eb.n; while i > 0 { i -= 1; let b = &self.eb.items[i]; if (b.x - x).powi(2) + (b.y - y).powi(2) < r * r { self.eb.kill(i); } } }
            self.p.was_dash = dashing; }
        // метка охотника: самый крепкий враг на экране
        if self.lv(u::MARK) > 0 { self.p.mark_t -= dt;
            let alive = (0..self.en.n).any(|i| self.en.items[i].uid == self.p.mark_uid && !self.en.items[i].dead);
            if self.p.mark_t <= 0. || !alive { self.p.mark_t = 4.; let mut best = (0u32, 0f32);
                for i in 0..self.en.n { let e = &self.en.items[i]; if e.dead || e.kind == K::Crystal || e.spawn_t > 0.2 { continue; }
                    if (e.x - self.cam_x).abs() > self.vw || (e.y - self.cam_y).abs() > self.vh { continue; } if e.hp > best.1 { best = (e.uid, e.hp); } }
                self.p.mark_uid = best.0; } }
    }
    /// Множитель урона по врагу от новых улучшений
    pub fn upg2_mul(&mut self, i: usize) -> f32 {
        let e = &self.en.items[i]; let mut m = 1.;
        let cl = self.lv(u::CHILL); if cl > 0 && (e.slow > 0. || e.freeze > 0.) { m *= 1. + 0.2 * cl as f32; }
        let ml = self.lv(u::MARK); if ml > 0 && e.uid == self.p.mark_uid && self.p.mark_uid != 0 { m *= 1.25 + 0.1 * ml as f32; }
        if self.lv(u::BLIZZARD) > 0 && e.slow > 0. && e.freeze <= 0. && !e.kind.d().boss && self.rng.next() < 0.12 { self.en.items[i].freeze = 0.6; }
        m
    }
    /// После удара: добивание
    pub fn try_execute(&mut self, i: usize) {
        let l = self.lv(u::EXECUTE); if l == 0 { return; }
        let e = &self.en.items[i]; if e.dead || e.hp <= 0. || e.kind.d().boss || e.kind == K::Chest { return; }
        let reaper = self.lv(u::REAPER) > 0; let th = 0.08 + 0.04 * l as f32 + if reaper { 0.08 } else { 0. };
        if e.hp < e.max_hp * th { let (x, y) = (e.x, e.y); self.en.items[i].hp = 0.; self.burst(x, y, 8, c::CORAL, 160., 6., 0.35);
            if reaper { self.chain_from(i, self.st.dmg * 1.2, 2); }
            self.kill_enemy(i, Src::None); }
    }
    /// Удача: шанс дополнительной жемчужины
    pub fn upg2_kill(&mut self, e: &Enemy) {
        let l = self.lv(u::FORTUNE); if l == 0 || e.kind.d().boss { return; }
        if self.rng.next() < 0.008 * l as f32 * if e.elite { 6. } else { 1. } { self.drop_pick(e.x, e.y, 3, 1.); }
    }
    /// Ракета долетела: взрыв
    pub fn missile_boom(&mut self, x: f32, y: f32, r: f32, dmg: f32) {
        self.explode(x, y, r, dmg, false);
        if self.lv(u::BOMBARD) > 0 { let q = self.qb(x, y, r); let burn = self.st.burn.max(self.st.dmg * 0.25); for &i in &q { let e = &mut self.en.items[i]; if !e.dead && !e.kind.d().boss { e.burn = e.burn.max(burn); e.burn_t = 3.; } } self.qb_back(q); }
    }
}
