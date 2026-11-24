//! Поведение врагов, боссов и стражей, расстановка мира (перенос из веб-версии один к одному).
use crate::data::{c, cfg, decor_role, decor_sway, K, DECOR_THEMES, PI, TAU};
use crate::game::*;
use crate::i18n::{self, t};

fn steer(e: &mut Enemy, dvx: f32, dvy: f32, k: f32, dt: f32) { let a = 1. - (-dt * k).exp(); e.vx += (dvx - e.vx) * a; e.vy += (dvy - e.vy) * a; }

impl Game {
    pub fn update_enemies(&mut self, dt: f32) {
        let r2 = (cfg::ARENA_R - 10.).powi(2);
        self.crystals_last = self.crystals; self.crystals = 0;
        let mut i = 0;
        while i < self.en.n {
            if self.en.items[i].dead { i += 1; continue; }
            { let e = &mut self.en.items[i]; if e.spawn_t > 0. { e.spawn_t -= dt; } if e.flash > 0. { e.flash -= dt; } if e.slow > 0. { e.slow -= dt; } }
            // горение
            if self.en.items[i].burn_t > 0. { let q = self.quality; let e = &mut self.en.items[i]; e.burn_t -= dt; e.burn_acc += dt;
                if e.burn_acc >= 0.3 { let bd = e.burn * e.burn_acc; e.burn_acc = 0.; e.hp -= bd; e.flash = e.flash.max(0.04); let (x, y, r) = (e.x, e.y, e.r);
                    if q > 0 && self.rng.next() < 0.5 { let (a, b, cc) = (self.rr(-6., 6.), self.rr(-20., 20.), self.rr(-60., -20.)); self.part(x + a, y - r * 0.4, b, cc, 0.4, 6., c::AMBER, 2.); }
                    if self.en.items[i].hp <= 0. { let wf = self.st.wildfire && self.en.items[i].burn > 0.; self.kill_enemy(i, Src::Burn); if wf { self.ignite_near_pub(x, y); } i += 1; continue; } } }
            let fz = self.en.items[i].freeze > 0.; if fz { self.en.items[i].freeze -= dt; }
            let (ex, ey, spd, slow) = { let e = &self.en.items[i]; (e.x, e.y, e.spd, e.slow) };
            let sp = if fz { 0. } else { spd * if slow > 0. { 0.6 } else { 1. } };
            let (dx, dy) = (self.p.x - ex, self.p.y - ey); let d = (dx * dx + dy * dy).sqrt().max(1.); let (ux, uy) = (dx / d, dy / d);
            self.en.items[i].t += dt;
            let kind = self.en.items[i].kind; let gt = self.t;
            match kind {
                K::Drifter | K::Spikelet => { let e = &mut self.en.items[i]; let w = (gt * 3. + e.phase).sin() * 0.45; steer(e, (ux - uy * w) * sp, (uy + ux * w) * sp, if kind == K::Spikelet { 2. } else { 3. }, dt); e.ang = e.vy.atan2(e.vx); }
                K::Dart => { let q = self.quality; let mut trail = false; { let e = &mut self.en.items[i];
                    if e.state == 0 { steer(e, ux * sp, uy * sp, 2., dt); e.ang = e.vy.atan2(e.vx); e.st -= dt; if d < 320. && e.st <= 0. && !fz { e.state = 1; e.st = 0.7; } }
                    else if e.state == 1 { steer(e, 0., 0., 6., dt); if e.st > 0.25 { e.ang += ang_diff(e.ang, dy.atan2(dx)) * (dt * 10.).min(1.); } e.st -= dt; if e.st <= 0. { e.state = 2; e.st = 0.5; e.vx = e.ang.cos() * 640.; e.vy = e.ang.sin() * 640.; } }
                    else if e.state == 2 { e.st -= dt; trail = q > 0; if e.st <= 0. { e.state = 3; e.st = 0.9; } }
                    else { steer(e, 0., 0., 2.5, dt); e.st -= dt; if e.st <= 0. { e.state = 0; e.st = 0.6; } } }
                    if trail && self.rng.next() < 0.5 { let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.part(x, y, 0., 0., 0.25, 7., c::DART, 0.); } }
                K::Jelly => { let shoot; { let e = &mut self.en.items[i]; steer(e, ux * sp, uy * sp, 1., dt); if e.vx * e.vx + e.vy * e.vy > 4. { let ta = e.vy.atan2(e.vx); e.ang += ang_diff(e.ang, ta) * (dt * 2.5).min(1.); } shoot = e.t >= 3.3 && !fz && d < 700.; if shoot { e.t = 0.; e.p1 += 0.35; } }
                    if shoot { let (x, y, p1) = (self.en.items[i].x, self.en.items[i].y, self.en.items[i].p1); let n = if self.zone >= 6 { 12 } else { 8 };
                        for k in 0..n { self.e_shoot(x, y, p1 + k as f32 * TAU / n as f32, 115. + self.zone as f32 * 3., 5., 9. * self.dmg_scale, c::JELLY, 0.); }
                        self.ring(x, y, 5., 40., 0.3, c::JELLY, 2.); self.snd(Sfx::Shot2); } }
                K::Urchin => { let e = &mut self.en.items[i]; steer(e, ux * sp, uy * sp, 1.5, dt); e.ang += dt * 2. * e.p3; }
                K::Squid => { let mut fire = false; { let e = &mut self.en.items[i];
                    let rad = if d < 240. { -1. } else if d > 340. { 1. } else { 0. }; e.p2 += dt; if e.p2 > 3. { e.p2 = 0.; e.p3 = -e.p3; }
                    steer(e, (ux * rad - uy * e.p3 * 0.7) * sp, (uy * rad + ux * e.p3 * 0.7) * sp, 2., dt); e.ang += ang_diff(e.ang, dy.atan2(dx)) * (dt * 6.).min(1.);
                    if e.state == 0 { e.p1 += dt; if e.p1 > 2.6 && d < 560. && !fz { e.state = 1; e.st = 0.55; e.p1 = 0.; } }
                    else { e.st -= dt; if e.st <= 0. { e.state = 0; e.t = 0.; fire = true; } } }
                    if fire { let (x, y) = (self.en.items[i].x, self.en.items[i].y); let a = dy.atan2(dx); let n = if self.zone >= 7 { 3 } else { 1 };
                        for k in 0..n { self.e_shoot(x + a.cos() * 16., y + a.sin() * 16., a + (k as f32 - (n - 1) as f32 / 2.) * 0.22, 330., 5., 10. * self.dmg_scale, c::SQUID, 0.); } self.snd(Sfx::Shot2); } }
                K::Eel => { let mut hit = 0f32; { let (px, py, pr, pd) = (self.p.x, self.p.y, self.p.r, self.p.dead); let e = &mut self.en.items[i];
                    let (pxx, pyy) = (-uy, ux); let w = (gt * 4. + e.phase).sin() * 0.9; let (vx, vy) = (ux + pxx * w, uy + pyy * w); let l = hypot(vx, vy).max(1.);
                    steer(e, vx / l * sp, vy / l * sp, 2.5, dt); e.ang = e.vy.atan2(e.vx);
                    let (hx, hy) = (e.hist[e.hh * 2], e.hist[e.hh * 2 + 1]);
                    if e.hn == 0 || (e.x - hx).powi(2) + (e.y - hy).powi(2) > 25. { e.hh = (e.hh + 1) % 32; e.hist[e.hh * 2] = e.x; e.hist[e.hh * 2 + 1] = e.y; if e.hn < 32 { e.hn += 1; } }
                    if !pd { for s in 1..=8usize { let k = s * 3; if k >= e.hn { break; } let j = (e.hh + 32 - k) % 32; let (sx, sy) = (px - e.hist[j * 2], py - e.hist[j * 2 + 1]); let rr = pr + 9. * e.scale - s as f32 * 0.4;
                        if sx * sx + sy * sy < rr * rr { hit = e.dmg * 0.8; break; } } } }
                    if hit > 0. { self.hurt_player(hit); } }
                K::Crab => { let e = &mut self.en.items[i]; if !fz { e.ang += clamp(ang_diff(e.ang, dy.atan2(dx)), -1.3 * dt, 1.3 * dt); } let a = e.ang; steer(e, a.cos() * sp, a.sin() * sp, 2., dt); }
                K::Chest => { let q = self.quality; let e = &mut self.en.items[i]; e.vx = 0.; e.vy = 0.; e.x = e.hx; e.y = e.hy; e.ang = (e.t * 2.).sin() * 0.15; let (x, y) = (e.x, e.y);
                    if q > 0 && self.rng.next() < 0.12 { let (a, b) = (self.rr(-22., 22.), self.rr(-22., 22.)); self.part(x + a, y + b, 0., -30., 0.6, 5., c::GOLD, 0.5); } }
                K::Mender => { let heal; { let e = &mut self.en.items[i]; let rad = if d < 220. { -1. } else if d > 320. { 0.6 } else { 0. }; steer(e, (ux * rad - uy * 0.45) * sp, (uy * rad + ux * 0.45) * sp, 1.4, dt); e.ang += dt * 0.8; e.p1 += dt; heal = e.p1 > 2.8 && !fz; if heal { e.p1 = 0.; } }
                    if heal { let (x, y) = (self.en.items[i].x, self.en.items[i].y); let q = self.qb(x, y, 160.); let mut healed = 0;
                        for &k in &q { if k == i { continue; } let (dead, kk, hp, mh, ox, oy) = { let o = &self.en.items[k]; (o.dead, o.kind, o.hp, o.max_hp, o.x, o.y) };
                            if dead || kk.d().boss || kk == K::Chest { continue; }
                            if hp < mh { let o = &mut self.en.items[k]; o.hp = (o.hp + o.max_hp * 0.3).min(o.max_hp); o.flash = o.flash.max(0.05); if self.quality > 0 && healed < 4 { self.bolt(x, y, ox, oy, c::EMER); } healed += 1; } }
                        self.qb_back(q); if healed > 0 { self.ring(x, y, 8., 160., 0.4, c::EMER, 2.); self.snd(Sfx::Shot2); } } }
                K::Bomber => { let q = self.quality; let e = &mut self.en.items[i]; steer(e, ux * sp, uy * sp, 2.6, dt); e.ang = e.vy.atan2(e.vx); let (x, y, r) = (e.x, e.y, e.r);
                    if q > 0 && self.rng.next() < 0.3 { self.part(x - ux * r, y - uy * r, 0., 0., 0.3, 6., c::CORAL, 1.); } }
                K::Boss1 => self.update_boss1(i, dt, d, ux, uy),
                K::Boss2 => self.update_boss2(i, dt, d, ux, uy),
                K::Boss3 => self.update_boss3(i, dt, d, ux, uy),
                K::Boss4 => self.update_boss4(i, dt, d, ux, uy),
                K::Ray | K::Lantern | K::Wisp | K::Spawner | K::Fry => { if self.update_new_foe(i, dt, d, ux, uy, sp, fz) { i += 1; continue; } }
                K::KingCrab => self.update_king(i, dt, d, ux, uy),
                K::Queen => self.update_queen(i, dt, d, ux, uy),
                K::Crystal => { match self.boss_idx() { Some(b) if self.en.items[b].kind == K::Boss3 => { self.crystals += 1; let (bx, by, bh, bm) = { let bb = &self.en.items[b]; (bb.x, bb.y, bb.hp, bb.max_hp) };
                        let e = &mut self.en.items[i]; e.ang += dt * if bh < bm * 0.5 { 1.6 } else { 1.1 }; e.vx = 0.; e.vy = 0.; e.x = bx + e.ang.cos() * 115.; e.y = by + e.ang.sin() * 115.; }
                    _ => { self.en.items[i].dead = true; let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.burst(x, y, 10, c::GOLD, 150., 7., 0.4); } } }
            }
            if self.en.items[i].dead { i += 1; continue; }
            if self.en.items[i].tier > 0 { self.tier_extra(i, dt, d, ux, uy, fz); if self.en.items[i].inv_t > 0. { self.en.items[i].inv_t -= dt; } }
            { let e = &mut self.en.items[i]; e.x += e.vx * dt; e.y += e.vy * dt;
                if e.x * e.x + e.y * e.y > r2 { let l = (e.x * e.x + e.y * e.y).sqrt(); let f = (cfg::ARENA_R - 10.) / l; e.x *= f; e.y *= f; e.vx *= -0.3; e.vy *= -0.3; } }
            // контакт с игроком
            let (sp_t, dmg, r, sc) = { let e = &self.en.items[i]; (e.spawn_t, e.dmg, e.r, e.scale) };
            if !self.p.dead && sp_t <= 0. && dmg > 0. { let rr = r * sc * 0.85 + self.p.r; if d < rr {
                if self.st.thorns > 0. && self.en.items[i].th_t < self.t { self.en.items[i].th_t = self.t + 0.5; self.damage_enemy(i, self.st.thorns, false, f32::NAN, -ux * 260., -uy * 260., Src::None);
                    let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.burst(x, y, 6, c::AMBER, 140., 5., 0.3); if self.en.items[i].dead { i += 1; continue; } }
                self.hurt_player(dmg); if !kind.d().boss { let e = &mut self.en.items[i]; e.vx -= ux * 200.; e.vy -= uy * 200.; } } }
            i += 1;
        }
    }
    pub fn ignite_near_pub(&mut self, x: f32, y: f32) { let q = self.qb(x, y, 110.); let burn = self.st.burn.max(1.);
        for &i in &q { let e = &mut self.en.items[i]; if e.dead || e.kind.d().boss { continue; } e.burn = e.burn.max(burn); e.burn_t = e.burn_t.max(2.4); } self.qb_back(q); }

    fn update_boss1(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let _ = d; let face = uy.atan2(ux); let (px, py) = (self.p.x, self.p.y); let dsc = self.dmg_scale;
        let mut shots: Vec<(f32, f32, f32, f32, f32, f32, u8, f32)> = vec![]; let mut actions = 0u8;
        { let e = &mut self.en.items[i]; let enr = e.hp < e.max_hp * 0.5; e.st -= dt;
            if e.state == 0 { let a = (e.y - py).atan2(e.x - px) + 0.9; let (tx, ty) = (px + a.cos() * 300., py + a.sin() * 300.); let (vx, vy) = (tx - e.x, ty - e.y); let l = hypot(vx, vy).max(1.); let s = e.spd.min(l * 2.);
                steer(e, vx / l * s, vy / l * s, 2., dt); e.ang += ang_diff(e.ang, face) * (dt * 4.).min(1.); e.p1 -= dt;
                if e.p1 <= 0. { e.p1 = if enr { 0.09 } else { 0.14 }; e.p2 += 0.33; let n = if enr { 3 } else { 2 };
                    for k in 0..n { shots.push((e.x, e.y, e.p2 + k as f32 * TAU / n as f32, 165., 6., 9. * dsc, c::CYAN, if enr { 0.25 } else { 0. })); } }
                if e.st <= 0. { e.phase = (e.phase as i32 + 1) as f32; let ph = e.phase as i32 % 3; e.state = if ph == 1 { 1 } else if ph == 2 { 2 } else { 3 };
                    e.st = if e.state == 1 { 3. } else if e.state == 2 { if enr { 4.2 } else { 2.9 } } else { 1. }; e.p1 = 0.; e.p3 = 0.; }
            } else if e.state == 1 { steer(e, 0., 0., 3., dt); e.ang += ang_diff(e.ang, face) * (dt * 3.).min(1.);
                if e.st < 1.9 { actions |= 1; e.p1 -= dt; if e.p1 <= 0. { e.p1 = if enr { 0.35 } else { 0.5 }; for k in -2..=2 { shots.push((e.x, e.y, face + k as f32 * 0.2, 210., 6., 9. * dsc, c::GOLD, 0.)); } actions |= 2; } }
                if e.st <= 0. { e.state = 0; e.st = 3.5; e.p1 = 0.5; }
            } else if e.state == 2 { e.p3 += dt; let cyc = e.p3 % 1.6;
                if cyc < 0.95 { steer(e, -ux * 60., -uy * 60., 4., dt); e.ang += ang_diff(e.ang, face) * (dt * 8.).min(1.); e.p1 = 0.; }
                else { if e.p1 == 0. { e.p1 = 1.; e.vx = e.ang.cos() * 760.; e.vy = e.ang.sin() * 760.; actions |= 4; } actions |= 8; }
                if e.st <= 0. { e.state = 0; e.st = 3.5; e.p1 = 0.4; }
            } else { steer(e, 0., 0., 3., dt); if e.p3 == 0. { e.p3 = 1.; actions |= 16; } if e.st <= 0. { e.state = 0; e.st = 4.; e.p1 = 0.5; } } }
        let (ex, ey, ang, enr) = { let e = &self.en.items[i]; (e.x, e.y, e.ang, e.hp < e.max_hp * 0.5) };
        if actions & 1 != 0 { self.pull_t = 0.1; self.pull_x = ex + ang.cos() * 80.; self.pull_y = ey + ang.sin() * 80.; }
        for s in shots { self.e_shoot(s.0, s.1, s.2, s.3, s.4, s.5, s.6, s.7); }
        if actions & 2 != 0 { self.snd(Sfx::Shot2); }
        if actions & 4 != 0 { self.shake(6.); self.snd(Sfx::Dash); }
        if actions & 8 != 0 && self.rand() < 0.6 { self.part(ex, ey, 0., 0., 0.4, 20., c::CYAN, 0.); }
        if actions & 16 != 0 { let n = if enr { 8 } else { 6 }; for k in 0..n { let a = k as f32 / n as f32 * TAU; if let Some(s) = self.spawn_enemy(K::Drifter, ex + a.cos() * 90., ey + a.sin() * 90., false) { self.en.items[s].spawn_t = 0.3; } } self.ring(ex, ey, 20., 160., 0.5, c::DRIFT, 4.); }
    }
    fn update_boss2(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let face = uy.atan2(ux); let dsc = self.dmg_scale; let gt = self.t; let flip = self.rand() < dt * 0.15;
        let (enr, state, l);
        { let e = &mut self.en.items[i]; enr = e.hp < e.max_hp * 0.5; e.st -= dt; let keep = if enr { 300. } else { 260. }; let rad = if d < keep - 30. { -1. } else if d > keep + 30. { 1. } else { 0. };
            let s = e.spd; steer(e, (ux * rad - uy * 0.35) * s, (uy * rad + ux * 0.35) * s, 1.2, dt); e.ang += dt * if enr { 0.9 } else { 0.55 } * e.p3; if flip { e.p3 = -e.p3; } state = e.state; l = if enr { 250. } else { 195. }; }
        let (ex, ey, er, ea) = { let e = &self.en.items[i]; (e.x, e.y, e.r, e.ang) };
        let mut hits = 0;
        for k in 0..6 { let base = ea + k as f32 * TAU / 6.;
            for j in 0..=10 { let dist = er * 0.75 + j as f32 * (l / 10.); let a = base + (gt * 2.4 + j as f32 * 0.45 + k as f32).sin() * 0.28 * (j as f32 / 10.);
                let idx = (k * 11 + j) * 2; self.tent[idx] = ex + a.cos() * dist; self.tent[idx + 1] = ey + a.sin() * dist;
                if j >= 2 && !self.p.dead { let (sx, sy) = (self.p.x - self.tent[idx], self.p.y - self.tent[idx + 1]); let rr = self.p.r + 12. - j as f32 * 0.6; if sx * sx + sy * sy < rr * rr { hits += 1; } } } }
        if hits > 0 { self.hurt_player(14. * dsc); }
        let (mut p1, mut p2) = (self.en.items[i].p1, self.en.items[i].p2);
        match state {
            0 => { p1 -= dt; if p1 <= 0. { p1 = if enr { 0.55 } else { 0.8 }; p2 += 0.5; let n = if enr { 30 } else { 24 }; for k in 0..n { if k % 6 == 0 { continue; } self.e_shoot(ex, ey, p2 + k as f32 * TAU / n as f32, 130., 7., 12. * dsc, c::PURP, 0.); } self.ring(ex, ey, 30., 120., 0.4, c::PURP, 4.); self.snd(Sfx::Shot2); } }
            1 => { p1 -= dt; if p1 <= 0. { p1 = 0.11; p2 += if enr { 0.21 } else { 0.17 }; let n = if enr { 6 } else { 4 }; for k in 0..n { self.e_shoot(ex, ey, p2 + k as f32 * TAU / n as f32, 150., 6., 11. * dsc, c::JELLY, if enr { -0.2 } else { 0. }); } } }
            2 => { p1 -= dt; if p1 <= 0. { p1 = if enr { 0.4 } else { 0.6 }; for k in -3..=3 { self.e_shoot(ex, ey, face + k as f32 * 0.13, 240., 6., 12. * dsc, c::GOLD, 0.); } self.snd(Sfx::Shot2); } }
            _ => { if self.en.items[i].p3 != 2. && p1 == 0. { p1 = 1.; for _ in 0..if enr { 4 } else { 3 } { let a = self.rr(0., TAU); if let Some(s) = self.spawn_enemy(K::Jelly, ex + a.cos() * 120., ey + a.sin() * 120., false) { self.en.items[s].spawn_t = 0.3; } } self.ring(ex, ey, 30., 200., 0.6, c::JELLY, 5.); } }
        }
        let e = &mut self.en.items[i]; e.p1 = p1; e.p2 = p2;
        if e.st <= 0. { e.state = (e.state + 1) % 4; e.st = [4., 3.6, 3., 1.2][e.state as usize]; e.p1 = if e.state == 3 { 0. } else { 0.3 }; }
    }
    fn update_boss3(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let dsc = self.dmg_scale; let (px, py) = (self.p.x, self.p.y);
        let enr; let state;
        { let e = &mut self.en.items[i]; enr = e.hp < e.max_hp * 0.5; e.st -= dt; state = e.state;
            if e.state != 2 { let rad = if d < 250. { -1. } else if d > 330. { 1. } else { 0. }; let s = e.spd; steer(e, (ux * rad + uy * 0.3) * s, (uy * rad - ux * 0.3) * s, 1.2, dt); } }
        let (ex, ey) = (self.en.items[i].x, self.en.items[i].y);
        let (mut p1, mut p2, mut p3) = (self.en.items[i].p1, self.en.items[i].p2, self.en.items[i].p3);
        match state {
            0 => { p1 -= dt; if p1 <= 0. { p1 = 0.07; p2 += if enr { 0.11 } else { 0.085 } * p3; let n = if enr { 4 } else { 3 }; for k in 0..n { self.e_shoot(ex, ey, p2 + k as f32 * TAU / n as f32, 250., 6., 12. * dsc, c::CRAB, 0.); } } }
            1 => { if self.en.items[i].st < 2.2 && p1 == 0. { p1 = 1.; let n = if enr { 16 } else { 12 }; for k in 0..n { if let Some(b) = self.e_shoot(ex, ey, k as f32 / n as f32 * TAU, 125., 8., 13. * dsc, c::PURP, 0.) { self.eb.items[b].acc = 1.1; self.eb.items[b].life = 6.; } }
                self.ring(ex, ey, 20., 260., 0.7, c::PURP, 8.); self.shake(8.); self.snd(Sfx::Boom(false)); } }
            2 => { if p1 == 0. { p1 = 1.; self.burst(ex, ey, 30, c::CRAB, 300., 10., 0.5); let a = self.rr(0., TAU); let nx = clamp(px + a.cos() * 290., -cfg::ARENA_R + 100., cfg::ARENA_R - 100.); let ny = clamp(py + a.sin() * 290., -cfg::ARENA_R + 100., cfg::ARENA_R - 100.);
                    { let e = &mut self.en.items[i]; e.x = nx; e.y = ny; e.vx = 0.; e.vy = 0.; } self.ring(nx, ny, 120., 10., 0.4, c::CRAB, 6.); self.flash = self.flash.max(0.35); self.snd(Sfx::Nova); p2 = 0.5; }
                p2 -= dt; let (ex, ey) = (self.en.items[i].x, self.en.items[i].y);
                if p2 <= 0. { p2 = if enr { 0.5 } else { 0.7 }; p3 = -p3; let off = self.rand() * TAU; for k in 0..28 { if k % 7 == 0 { continue; } self.e_shoot(ex, ey, off + k as f32 * TAU / 28., 150., 6., 12. * dsc, c::GOLD, 0.); } self.ring(ex, ey, 30., 140., 0.4, c::GOLD, 4.); self.snd(Sfx::Shot2); } }
            _ => { if p1 == 0. { p1 = 1.; let need = (if enr { 6 } else { 4 }) - self.crystals_last as i32; let hpc = 70. * self.hp_scale * (1. + self.zone as f32 * 0.08);
                for k in 0..need.max(0) { if let Some(cc) = self.spawn_enemy(K::Crystal, ex, ey, false) { let cr = &mut self.en.items[cc]; cr.ang = k as f32 / (need.max(1)) as f32 * TAU; cr.spawn_t = 0.4; cr.hp = hpc; cr.max_hp = hpc; } }
                self.ring(ex, ey, 10., 130., 0.5, c::GOLD, 5.); } }
        }
        let rnd = self.rand();
        let e = &mut self.en.items[i]; e.p1 = p1; e.p2 = p2; e.p3 = p3;
        if e.st <= 0. { e.state = (e.state + 1) % 4; e.st = [4., 3.4, 2.6, 1.][e.state as usize]; e.p1 = if e.state == 0 { 0.3 } else { 0. }; if e.state == 0 { e.p3 = if rnd < 0.5 { 1. } else { -1. }; } }
    }
    fn update_boss4(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let face = uy.atan2(ux); let dsc = self.dmg_scale; let (px, py) = (self.p.x, self.p.y);
        let enr; let state;
        { let e = &mut self.en.items[i]; enr = e.hp < e.max_hp * 0.5; e.st -= dt; state = e.state; }
        match state {
            0 => { let (shoot, ex, ey, va); { let e = &mut self.en.items[i]; let a = (e.y - py).atan2(e.x - px) + 1.1; let (tx, ty) = (px + a.cos() * 280., py + a.sin() * 280.); let (vx, vy) = (tx - e.x, ty - e.y); let l = hypot(vx, vy).max(1.); let s = (e.spd * 1.25).min(l * 2.2);
                    steer(e, vx / l * s, vy / l * s, 2.4, dt); e.ang += ang_diff(e.ang, e.vy.atan2(e.vx)) * (dt * 6.).min(1.); e.p1 -= dt; shoot = e.p1 <= 0.; if shoot { e.p1 = if enr { 0.12 } else { 0.18 }; } ex = e.x; ey = e.y; va = e.vy.atan2(e.vx); }
                if shoot { let j = self.rr(-0.3, 0.3); self.e_shoot(ex, ey, va + PI + j, 150., 6., 11. * dsc, c::EEL, 0.); if enr { let j2 = self.rr(-0.2, 0.2); self.e_shoot(ex, ey, face + j2, 200., 6., 11. * dsc, c::ICE, 0.); } } }
            1 => { let (dash, trail, ex, ey, ang); { let e = &mut self.en.items[i]; e.p3 += dt; let cyc = e.p3 % 1.7; let mut ds = false; let mut tr = false;
                    if cyc < 1.0 { steer(e, -ux * 70., -uy * 70., 4., dt); e.ang += ang_diff(e.ang, face) * (dt * 7.).min(1.); e.p1 = 0.; }
                    else { if e.p1 == 0. { e.p1 = 1.; e.vx = e.ang.cos() * 820.; e.vy = e.ang.sin() * 820.; ds = true; } tr = true; } dash = ds; trail = tr; ex = e.x; ey = e.y; ang = e.ang; }
                if dash { self.shake(7.); self.snd(Sfx::Dash); for k in -2..=2 { self.e_shoot(ex, ey, ang + k as f32 * 0.18, 230., 6., 11. * dsc, c::EEL, 0.); } }
                if trail && self.rand() < 0.6 { self.part(ex, ey, 0., 0., 0.4, 22., c::EEL, 0.); } }
            2 => { let (ex, ey, p2, shoot); { let e = &mut self.en.items[i]; let rad = if d < 240. { -1. } else if d > 320. { 1. } else { 0. }; let s = e.spd; steer(e, ux * rad * s, uy * rad * s, 1.5, dt); e.p1 -= dt; shoot = e.p1 <= 0.; if shoot { e.p1 = if enr { 0.1 } else { 0.14 }; e.p2 += if enr { 0.26 } else { 0.2 }; } ex = e.x; ey = e.y; p2 = e.p2; }
                if shoot { let n = if enr { 5 } else { 3 }; for k in 0..n { self.e_shoot(ex, ey, p2 + k as f32 * TAU / n as f32, 155., 6., 11. * dsc, c::ICE, if enr { -0.15 } else { 0. }); } } }
            _ => { let (go, ex, ey); { let e = &mut self.en.items[i]; steer(e, 0., 0., 3., dt); go = e.p3 != 9. && e.p1 == 0.; if go { e.p1 = 1.; e.p3 = 9.; } ex = e.x; ey = e.y; }
                if go { let n = if enr { 5 } else { 3 }; for _ in 0..n { let a = self.rr(0., TAU); let k = if self.rand() < 0.5 { K::Dart } else { K::Bomber }; if let Some(s) = self.spawn_enemy(k, ex + a.cos() * 110., ey + a.sin() * 110., false) { self.en.items[s].spawn_t = 0.3; } } self.ring(ex, ey, 30., 200., 0.6, c::EEL, 5.); } }
        }
        let e = &mut self.en.items[i];
        if e.st <= 0. { e.state = (e.state + 1) % 4; e.st = [4.2, 3.4, 3.4, 1.4][e.state as usize]; e.p1 = if e.state == 1 { 0. } else { 0.3 }; e.p3 = 0.; }
    }

    // ---------- новые враги ----------
    pub fn init_new_foe(&mut self, i: usize) {
        let kind = self.en.items[i].kind; let (a, b) = (self.rr(1.6, 3.), self.rr(3., 5.));
        { let e = &mut self.en.items[i]; e.lvl = 0; e.tx = 0.; e.ty = 0.;
            match kind { K::Ray | K::Lantern => e.p1 = a, K::Spawner => e.p1 = b, K::Wisp => { e.st = 6.5; e.max_hp = (self.st.dmg * 1.6).max(6.); e.hp = e.max_hp; e.spawn_t = 0.15; }, K::Fry => e.spawn_t = 0.2, _ => {} } }
        if let Some((h0, h1)) = i18n::foe(kind.key()) { if !self.s.foe_seen.contains_key(kind.key()) && self.boss < 0 { self.s.foe_seen.insert(kind.key().into(), 1); self.dirty = true; self.banner(h0, h1, crate::data::PAL_HEX[kind.d().col as usize], 3.); } }
    }
    fn fizzle(&mut self, i: usize) { self.en.items[i].dead = true; let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.burst(x, y, 8, c::AMBER, 120., 6., 0.35); self.ring(x, y, 3., 26., 0.25, c::AMBER, 2.); }
    pub fn spawn_fry(&mut self, i: usize, n: usize) {
        let (ex, ey, ea, er, es) = { let e = &self.en.items[i]; (e.x, e.y, e.ang, e.r, e.scale) };
        for k in 0..n { if self.en.n >= cfg::MAX_ENEMIES - 12 { break; } let a = ea + (k as f32 - (n - 1) as f32 / 2.) * 0.9 + self.rr(-0.2, 0.2);
            if let Some(f) = self.spawn_enemy(K::Fry, ex + a.cos() * er * es * 0.6, ey + a.sin() * er * es * 0.6, false) { let ff = &mut self.en.items[f]; ff.vx = a.cos() * 230.; ff.vy = a.sin() * 230.; ff.ang = a; } }
        self.ring(ex, ey, er * 0.6, er * 2., 0.35, c::EEL, 3.); self.snd(Sfx::Shot2);
    }
    fn update_new_foe(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32, sp: f32, fz: bool) -> bool {
        let kind = self.en.items[i].kind; let gt = self.t; let q = self.quality;
        match kind {
            K::Ray => { let (a, b) = (self.rr(2.8, 4.2), self.rng.next()); let mut trail = false;
                { let e = &mut self.en.items[i];
                    if e.state == 0 { let rad = if d < 200. { -0.6 } else if d > 300. { 0.8 } else { 0.1 }; let (tx, ty) = (ux * rad - uy * e.p3, uy * rad + ux * e.p3); let l = hypot(tx, ty).max(1.);
                        steer(e, tx / l * sp, ty / l * sp, 1.6, dt); if !fz { e.ang = e.vy.atan2(e.vx); } e.p1 -= dt; e.p2 += dt; if e.p2 > 4. { e.p2 = 0.; e.p3 = -e.p3; }
                        if e.p1 <= 0. && d < 520. && !fz { e.state = 1; e.st = 0.8; } }
                    else if e.state == 1 { steer(e, 0., 0., 5., dt); if e.st > 0.3 { e.ang += ang_diff(e.ang, uy.atan2(ux)) * (dt * 9.).min(1.); } e.st -= dt; if e.st <= 0. { e.state = 2; e.st = RAY_T; } }
                    else if e.state == 2 { e.st -= dt; if !fz { e.vx = e.ang.cos() * RAY_SPD; e.vy = e.ang.sin() * RAY_SPD; } trail = q > 0 && b < 0.5; if e.st <= 0. { e.state = 3; e.st = 0.9; } }
                    else { steer(e, 0., 0., 2.5, dt); e.st -= dt; if e.st <= 0. { e.state = 0; e.p1 = a; } } }
                if trail { let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.part(x, y, 0., 0., 0.3, 8., c::ICE, 0.); } }
            K::Lantern => { let a = self.rr(3.8, 4.8); let mut fire = false;
                { let e = &mut self.en.items[i]; let rad = if d < 280. { -1. } else if d > 380. { 0.8 } else { 0. }; steer(e, (ux * rad - uy * e.p3 * 0.5) * sp, (uy * rad + ux * e.p3 * 0.5) * sp, 1.5, dt);
                    if !fz { e.ang += ang_diff(e.ang, uy.atan2(ux)) * (dt * 4.).min(1.); }
                    if e.state == 0 { e.p1 -= dt; if e.p1 <= 0. && d < 620. && !fz { e.state = 1; e.st = 0.8; } } else { e.st -= dt; if e.st <= 0. { e.state = 0; e.p1 = a; fire = true; } } }
                if fire && self.count_kind(K::Wisp) < cfg::WISP_MAX { let (ex, ey, ea, er, es, el) = { let e = &self.en.items[i]; (e.x, e.y, e.ang, e.r, e.scale, e.elite) }; let l = er * 1.3 * es; let (fx, fy) = (ex + ea.cos() * l, ey + ea.sin() * l);
                    if let Some(w) = self.spawn_enemy(K::Wisp, fx, fy, false) { let ww = &mut self.en.items[w]; ww.ang = ea; ww.vx = ea.cos() * 60.; ww.vy = ea.sin() * 60.; if el { ww.dmg *= 1.3; } }
                    self.ring(fx, fy, 4., 34., 0.3, c::AMBER, 2.); self.snd(Sfx::Shot2); } }
            K::Wisp => { let pr = self.p.r; let pd = self.p.dead; let tr = self.rng.next() < 0.4;
                let (st, sp_t, dmg, r, x, y, vx, vy) = { let e = &mut self.en.items[i]; e.st -= dt; let s = if fz { 0. } else { (if e.slow > 0. { 0.6 } else { 1. }) * e.spd * (0.45 + (6.5 - e.st)).min(1.) };
                    e.ang += clamp(ang_diff(e.ang, uy.atan2(ux)), -1.7 * dt, 1.7 * dt); e.vx = e.ang.cos() * s; e.vy = e.ang.sin() * s; (e.st, e.spawn_t, e.dmg, e.r, e.x, e.y, e.vx, e.vy) };
                if q > 0 && tr { self.part(x, y, -vx * 0.2, -vy * 0.2, 0.35, 6., c::AMBER, 1.); }
                if !pd && sp_t <= 0. && d < r + pr { self.hurt_player(dmg); self.fizzle(i); return true; }
                if st <= 0. { self.fizzle(i); return true; } }
            K::Spawner => { let a = self.rr(5.5, 7.); let mut fire = false;
                { let e = &mut self.en.items[i]; steer(e, ux * sp, uy * sp, 1., dt); if !fz { e.ang += ang_diff(e.ang, uy.atan2(ux)) * (dt * 1.5).min(1.); }
                    if e.state == 0 { e.p1 -= dt; if e.p1 <= 0. && d < 650. && !fz { e.state = 1; e.st = 0.9; } } else { e.st -= dt; if e.st <= 0. { e.state = 0; e.p1 = a; fire = true; } } }
                if fire { self.spawn_fry(i, 3); } }
            K::Fry => { let e = &mut self.en.items[i]; let w = (gt * 5. + e.phase).sin() * 0.6; steer(e, (ux - uy * w) * sp, (uy + ux * w) * sp, 2.2, dt); e.ang = e.vy.atan2(e.vx); }
            _ => {}
        }
        false
    }

    // ---------- стражи ----------
    pub fn guardian_for(z: u32) -> Option<(K, i32)> {
        if z == 3 { return Some((K::KingCrab, 0)); } if z == 8 { return Some((K::Queen, 0)); } if z == 13 { return Some((K::Boss4, 0)); }
        if z > 15 && z % 5 == 3 { let k = (z - 18) / 5; return Some((if k % 2 == 1 { K::KingCrab } else { K::Queen }, 1 + (k / 2) as i32)); }
        None
    }
    pub fn try_guardian(&mut self) -> bool {
        let Some((kind, lvl)) = Self::guardian_for(self.zone) else { return false };
        let nz = self.zone + 2; let cyc = ((nz as i32 - 5) / 20) as f32;
        self.hp_scale = 0.42 * boss_at(nz).d().hp * (1. + cyc * 1.3) / kind.d().hp;
        let Some(i) = self.spawn_enemy(kind, self.p.x, self.p.y - self.vh * 0.7, false) else { return false };
        { let e = &mut self.en.items[i]; e.spawn_t = 0.; e.state = 0; e.st = 2.4; e.lvl = lvl; e.p1 = 0.8; e.phase = 0.; e.ty = 0.;
            if kind == K::KingCrab { e.sh = e.max_hp * 0.2; e.tx = e.sh; e.ang = PI / 2.; } else { e.ang = 0.; } }
        self.qz = Qz::default(); self.boss = self.en.items[i].uid as i32;
        // ярус стража: 1300 м — Ледяной Левиафан, дальше стражи возвращаются в облике бездны
        let tr = if self.zone == 13 { 1 } else if self.zone > 15 { if self.zone > 30 { 2 } else { 1 } } else { 0 }; self.apply_tier(i, tr);
        if kind == K::Boss4 { let e = &mut self.en.items[i]; e.st = 3.5; e.p1 = 0.8; e.lvl = 0; }
        let dx = self.rr(-40., 40.); self.drop_pick(self.p.x + dx, self.p.y + 60., 4, 30.);
        let nm = crate::tiers::boss_name(kind, tr, i18n::is_en()).map(|s| s.to_string()).filter(|_| tr > 0).unwrap_or_else(|| i18n::boss(kind.key()));
        self.banner(nm, format!("{} · {} {}", t("guard"), self.zone * 100, t("m")), if kind == K::KingCrab { 0xffd54f } else { 0x8fd8ff }, 3.2);
        self.snd(Sfx::Warn); self.vibrate(160); self.shake(8.);
        true
    }
    pub fn guardian_death(&mut self, i: usize) {
        self.unlock("guard"); let k = if self.en.items[i].kind == K::KingCrab { 0 } else { 1 }; let (a, b) = i18n::pair("guardDie", k); self.banner(a, b, if k == 1 { 0x8fd8ff } else { 0xffd54f }, 3.);
        let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.spawn_chest(x, y);
        self.boss_clear_t = 0.; self.zone_t = self.zone_t.max(cfg::ZONE_TIME * 0.45);
    }
    pub fn king_shield(&mut self, i: usize, dmg: f32) -> f32 {
        let (ex, ey, ea, er) = { let e = &self.en.items[i]; (e.x, e.y, e.ang, e.r) };
        self.en.items[i].sh -= dmg; let (a, b) = (self.rr(-90., 90.), self.rr(-90., 90.)); self.part(ex + ea.cos() * er, ey + ea.sin() * er, a, b, 0.3, 8., c::WHITE, 2.);
        if self.rand() < 0.35 { self.snd(Sfx::Clink); }
        if self.en.items[i].sh <= 0. { let (fx, fy) = (ex + ea.cos() * er, ey + ea.sin() * er);
            self.burst(fx, fy, 26, c::GOLD, 260., 9., 0.6); self.burst(fx, fy, 10, c::WHITE, 200., 7., 0.4); self.ring(fx, fy, 6., 110., 0.4, c::GOLD, 5.); self.shake(9.); self.snd(Sfx::Boom(false));
            self.text(ex, ey - er - 22., t("kingShield"), 0xffe9a0, true, false); let e = &mut self.en.items[i]; e.state = 6; e.st = 1.4; e.vx = 0.; e.vy = 0.; }
        dmg * 0.35
    }
    fn king_wave(&mut self, i: usize, n: u32, spd: f32, off: f32) { let (x, y) = (self.en.items[i].x, self.en.items[i].y); for k in 0..n { if k % 7 == 0 { continue; } self.e_shoot(x, y, off + k as f32 * TAU / n as f32, spd, 7., 11. * self.dmg_scale, c::GOLD, 0.); } }
    fn update_king(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let face = uy.atan2(ux); let (enr, l, state) = { let e = &mut self.en.items[i]; e.st -= dt; (e.hp < e.max_hp * 0.5 || e.sh <= 0., e.lvl, e.state) };
        match state {
            0 => { let e = &mut self.en.items[i]; e.ang += clamp(ang_diff(e.ang, face), -1.1 * dt, 1.1 * dt); let s = e.spd * if enr { 1.25 } else { 1. }; let a = e.ang; steer(e, a.cos() * s, a.sin() * s, 2., dt);
                if e.st <= 0. { e.phase += 1.; let ph = e.phase as i32 % 3; if ph == 1 { e.state = 1; e.st = 0.9; e.p2 = if enr || l > 0 { 2. } else { 1. }; } else if ph == 2 { e.state = 3; e.st = 0.9; } else { e.state = 5; e.st = 1.2; e.p1 = 0.; } } }
            1 => { let go = { let e = &mut self.en.items[i]; steer(e, 0., 0., 5., dt); if e.st > 0.3 { e.ang += ang_diff(e.ang, face) * (dt * 8.).min(1.); } let g = e.st <= 0.; if g { e.state = 2; e.st = KING_T; } g }; if go { self.shake(5.); self.snd(Sfx::Dash); } }
            2 => { let (x, y, end) = { let e = &mut self.en.items[i]; e.vx = e.ang.cos() * KING_SPD; e.vy = e.ang.sin() * KING_SPD; let r = cfg::ARENA_R - 70.; (e.x, e.y, e.st <= 0. || e.x * e.x + e.y * e.y > r * r) };
                if self.rand() < 0.6 { self.part(x, y, 0., 0., 0.4, 18., c::GOLD, 0.); }
                if end { let off = self.rr(0., TAU); self.king_wave(i, 14 + 2 * l as u32, 150., off); self.ring(x, y, 10., 120., 0.4, c::GOLD, 5.); self.shake(6.); self.snd(Sfx::Boom(false));
                    let e = &mut self.en.items[i]; e.vx *= 0.2; e.vy *= 0.2; e.p2 -= 1.; if e.p2 > 0. { e.state = 1; e.st = 0.75; } else { e.state = 0; e.st = if enr { 2.2 } else { 3. }; } } }
            3 => { let go = { let e = &mut self.en.items[i]; steer(e, 0., 0., 4., dt); e.st <= 0. };
                if go { let o = self.rr(0., TAU); self.king_wave(i, 22, 165., o); let (x, y, dm) = (self.en.items[i].x, self.en.items[i].y, self.en.items[i].dmg); self.ring(x, y, 20., KING_SLAM + 40., 0.5, c::GOLD, 8.); self.shake(10.); self.snd(Sfx::Boom(false));
                    if !self.p.dead && d < KING_SLAM + self.p.r { self.hurt_player(dm); }
                    let e = &mut self.en.items[i]; if enr || l > 0 { e.state = 4; e.st = 0.45; e.p1 = o; } else { e.state = 0; e.st = 3.; } } }
            4 => { let go = { let e = &mut self.en.items[i]; steer(e, 0., 0., 4., dt); e.st <= 0. }; if go { let o = self.en.items[i].p1 + TAU / 40.; self.king_wave(i, 20, 120., o); let (x, y) = (self.en.items[i].x, self.en.items[i].y); self.ring(x, y, 20., 160., 0.4, c::GOLD, 5.); let e = &mut self.en.items[i]; e.state = 0; e.st = 2.6; } }
            5 => { let summon = { let e = &mut self.en.items[i]; steer(e, 0., 0., 4., dt); let s = e.p1 == 0. && e.st < 0.7; if s { e.p1 = 1.; } s };
                if summon { let n = (((if enr { 2 } else { 1 }) + l) as usize).min(cfg::CRAB_MAX.saturating_sub(self.count_kind(K::Crab))); let (x, y, ea) = (self.en.items[i].x, self.en.items[i].y, self.en.items[i].ang);
                    for k in 0..n { let a = ea + PI + (k as f32 - (n as f32 - 1.) / 2.) * 0.9; if let Some(cc) = self.spawn_enemy(K::Crab, x + a.cos() * 110., y + a.sin() * 110., false) { self.en.items[cc].spawn_t = 0.4; self.en.items[cc].ang = a; } }
                    self.ring(x, y, 20., 170., 0.5, c::CRAB, 5.); self.snd(Sfx::Shot2); }
                let e = &mut self.en.items[i]; if e.st <= 0. { e.state = 0; e.st = 3.; } }
            _ => { let e = &mut self.en.items[i]; steer(e, 0., 0., 3., dt); if e.st <= 0. { e.state = 0; e.st = 1.5; } }
        }
    }
    fn queen_zaps(&mut self, i: usize) {
        let (ex, ey, dm) = (self.en.items[i].x, self.en.items[i].y, self.en.items[i].dmg);
        for k in 0..self.qz.n { let (x, y) = (self.qz.xs[k], self.qz.ys[k]); self.bolt(ex, ey, x, y, c::ICE); self.ring(x, y, 10., QZ_R + 10., 0.3, c::ICE, 5.); self.burst(x, y, 10, c::ICE, 200., 7., 0.4);
            if !self.p.dead && hypot(self.p.x - x, self.p.y - y) < QZ_R + self.p.r * 0.5 { self.hurt_player(dm * 1.1); } }
        self.qz.n = 0; self.shake(5.); self.snd(Sfx::Boom(false));
    }
    fn update_queen(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32) {
        let dsc = self.dmg_scale; let flip = self.rand() < dt * 0.12;
        let (enr, l, state, ex, ey, er) = { let e = &mut self.en.items[i]; e.st -= dt; (e.hp < e.max_hp * 0.5, e.lvl, e.state, e.x, e.y, e.r) };
        if enr && self.en.items[i].ty == 0. { self.en.items[i].ty = 1.; self.text(ex, ey - er - 24., t("guardRage"), 0xbfe6ff, true, false); self.ring(ex, ey, 20., 240., 0.6, c::ICE, 7.); self.flash = self.flash.max(0.3); }
        { let e = &mut self.en.items[i]; let keep = 290.; let rad = if d < keep - 40. { -1. } else if d > keep + 40. { 1. } else { 0. }; let s = e.spd; let p3 = e.p3; steer(e, (ux * rad - uy * 0.4 * p3) * s, (uy * rad + ux * 0.4 * p3) * s, 1.1, dt); e.ang = 0.; if flip { e.p3 = -e.p3; } }
        let (ex, ey) = (self.en.items[i].x, self.en.items[i].y);
        match state {
            0 => { let (mut p1, mut p2) = (self.en.items[i].p1, self.en.items[i].p2); p1 -= dt;
                if p1 <= 0. { p1 = if enr { 0.85 } else { 1.05 }; p2 += 0.37; let n = if enr { 20 } else { 18 }; for k in 0..n { if k % 6 == 0 { continue; } self.e_shoot(ex, ey, p2 + k as f32 * TAU / n as f32, 120., 7., 11. * dsc, c::ICE, if enr { 0.12 } else { 0. }); } self.ring(ex, ey, 30., 110., 0.4, c::ICE, 4.); self.snd(Sfx::Shot2); }
                self.en.items[i].p1 = p1; self.en.items[i].p2 = p2; }
            1 => { if self.qz.t <= 0. && self.qz.left > 0 { self.qz.left -= 1; self.qz.n = (((if enr { 5 } else { 3 }) + l) as usize).min(12); self.qz.t = 1.;
                    self.qz.xs[0] = self.p.x + self.p.vx * 0.25; self.qz.ys[0] = self.p.y + self.p.vy * 0.25;
                    for k in 1..self.qz.n { let a = self.rr(0., TAU); let rr = self.rr(110., 240.); self.qz.xs[k] = self.p.x + a.cos() * rr; self.qz.ys[k] = self.p.y + a.sin() * rr; } self.snd(Sfx::Nova); }
                if self.qz.t > 0. { self.qz.t -= dt; if self.qz.t <= 0. { self.queen_zaps(i); } } }
            2 => { if self.en.items[i].p1 == 0. { self.en.items[i].p1 = 1.; let n = ((((if enr { 3 } else { 2 }) + l) as usize)).min(7usize.saturating_sub(self.count_kind(K::Jelly)));
                for _ in 0..n { let a = self.rr(0., TAU); if let Some(s) = self.spawn_enemy(K::Jelly, ex + a.cos() * 120., ey + a.sin() * 120., false) { self.en.items[s].spawn_t = 0.3; } } self.ring(ex, ey, 30., 200., 0.6, c::JELLY, 5.); } }
            _ => { if self.qz.rn == 0 { self.qz.rn = if enr { 10 } else { 8 }; self.qz.ra = self.rr(0., TAU); self.qz.rt = 0.8; }
                if self.qz.rt > 0. { self.qz.rt -= dt; if self.qz.rt <= 0. { for k in 0..self.qz.rn { let a = self.qz.ra + k as f32 * TAU / self.qz.rn as f32; for j in 0..3 { self.e_shoot(ex + a.cos() * er * 0.6, ey + a.sin() * er * 0.6, a, 200. + j as f32 * 55., 6., 11. * dsc, c::CYAN, 0.); } }
                    self.ring(ex, ey, 20., 140., 0.4, c::CYAN, 5.); self.snd(Sfx::Shot2); } } }
        }
        let e = &mut self.en.items[i];
        if e.st <= 0. && self.qz.t <= 0. && self.qz.rt <= 0. { e.phase += 1.; let ord = [0, 1, 0, 3, 0, 2]; let s = ord[e.phase as usize % 6]; e.state = s;
            e.st = [3.6, if enr || l > 0 { 2.6 } else { 1.4 }, 1.4, 1.6][s as usize]; e.p1 = if s == 0 { 0.4 } else { 0. }; self.qz.left = if s == 1 { if enr || l > 0 { 2 } else { 1 } } else { 0 }; self.qz.rn = 0; self.qz.rt = 0.; }
    }

    // ---------- мир: рифы, поляны, стена по краю ----------
    pub fn build_decor(&mut self, zi: usize) {
        self.decor_zone = zi; self.decor.clear();
        let th: Vec<usize> = DECOR_THEMES[zi % 15].iter().map(|k| DECOR_KEYS.iter().position(|x| x == k).unwrap()).collect();
        let r = cfg::ARENA_R;
        let size = |k: usize| -> f32 { match decor_role(DECOR_KEYS[k]) { 2 => 150., 1 => 105., _ => 55. } };
        let pick = |g: &mut Game, role: u8| -> usize { let l: Vec<usize> = th.iter().copied().filter(|&k| decor_role(DECOR_KEYS[k]) == role).collect();
            if !l.is_empty() { return l[(g.rand() * l.len() as f32) as usize % l.len()]; } th[(g.rand() * th.len() as f32) as usize % th.len()] };
        let foot = |k: usize, s: f32| size(k) * s * 0.36;
        let free = |dec: &Vec<Decor>, x: f32, y: f32, rr: f32, pad: f32| dec.iter().all(|d| { let m = (d.fr + rr) * pad; (d.x - x).powi(2) + (d.y - y).powi(2) >= m * m });
        let mut centers: Vec<(f32, f32)> = vec![];
        for _ in 0..600 { if centers.len() >= 17 { break; } let a = self.rand() * TAU; let rr = self.rand().sqrt() * (r - 220.); let (x, y) = (a.cos() * rr, a.sin() * rr);
            if hypot(x, y) > 260. && centers.iter().all(|c| hypot(c.0 - x, c.1 - y) > 360.) { centers.push((x, y)); } }
        let add = |g: &mut Game, k: usize, x: f32, y: f32, s: f32| { let (rr, p) = (g.rand() * TAU, g.rand() * TAU); g.decor.push(Decor { k, x, y, s, fr: foot(k, s), r: rr, sw: decor_sway(DECOR_KEYS[k]), p, a: 0., lt: 0. }); };
        for (cx, cy) in centers { let k = pick(self, 2); let s = self.rr(1.05, 1.4); add(self, k, cx, cy, s);
            let n = self.rng.int(2, 5); let mut placed = 0;
            for _ in 0..50 { if placed >= n { break; } let role = if placed < 3 { 1 } else { 0 }; let k = pick(self, role); let sc = if role == 1 { self.rr(0.75, 1.05) } else { self.rr(0.55, 0.8) };
                let a = self.rand() * TAU; let dd = self.rr(70., 160.); let (x, y) = (cx + a.cos() * dd, cy + a.sin() * dd);
                if free(&self.decor, x, y, foot(k, sc), 0.85) { add(self, k, x, y, sc); placed += 1; } } }
        let mut placed = 0;
        for _ in 0..300 { if placed >= 24 { break; } let a = self.rand() * TAU; let rr = self.rand().sqrt() * (r - 120.); let (x, y) = (a.cos() * rr, a.sin() * rr); let k = pick(self, 0); let sc = self.rr(0.5, 0.72);
            if hypot(x, y) > 200. && free(&self.decor, x, y, foot(k, sc), 2.2) { add(self, k, x, y, sc); placed += 1; } }
        let mut a = 0.;
        while a < TAU { let k = if self.rand() < 0.65 { pick(self, 2) } else { pick(self, 1) }; let rr = r + self.rr(15., 75.); let s = self.rr(1.1, 1.6); add(self, k, a.cos() * rr, a.sin() * rr, s); a += 175. / r * self.rr(0.8, 1.25); }
        self.decor.sort_by(|p, q| p.y.partial_cmp(&q.y).unwrap());
    }
    pub fn init_floor(&mut self) {
        self.floor.clear();
        for i in 0..55 { let a = self.rand() * TAU; let r = self.rand().sqrt() * (cfg::ARENA_R - 30.); let s = self.rr(60., 160.); let p = self.rand() * TAU;
            self.floor.push((a.cos() * r, a.sin() * r, s, if i % 3 > 0 { c::ICE } else { c::CYAN }, p)); }
    }
}
