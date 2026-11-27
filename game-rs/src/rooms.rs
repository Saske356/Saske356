//! 4.7: тайные комнаты. Иногда в зоне появляется портал (art: assets/spr/portal.png); вплыл — 25 с испытания:
//! обычные враги исчезают, дно меняется на золотой грот (ground/g15), новые не приходят, таймер зоны стоит.
//! 0 — Жемчужная россыпь (собери сколько успеешь), 1 — Танец с иглами (продержись без урона → сундук и осколок),
//! 2 — Гонка за светом (собери все большие огни → 2 карты улучшений).
use crate::data::{c, cfg, K, TAU};
use crate::game::*;
use crate::i18n;

pub const ROOM_T: f32 = 25.;
fn txt(k: u8) -> (&'static str, &'static str) {
    let en = i18n::is_en();
    match (k, en) { (0, false) => ("ЖЕМЧУЖНАЯ РОССЫПЬ", "Собери сколько успеешь!"), (0, true) => ("PEARL HOARD", "Grab as many as you can!"),
        (1, false) => ("ТАНЕЦ С ИГЛАМИ", "Продержись без единого удара"), (1, true) => ("NEEDLE DANCE", "Survive without a single hit"),
        (_, false) => ("ГОНКА ЗА СВЕТОМ", "Собери все большие огни"), (_, true) => ("CHASE THE LIGHT", "Collect all the big lights") }
}
/// 4.9.6: табличка комнаты в интерфейсе: название и цель с прогрессом
pub fn room_hud(g: &Game) -> (String, String) {
    let en = i18n::is_en(); let (a, _) = txt(g.room_k); let s = g.room_t.ceil() as i32;
    let goal = match (g.room_k, en) { (0, false) => format!("Собрано жемчуга: {} · {s} с", g.room_got), (0, true) => format!("Pearls: {} · {s} s", g.room_got),
        (1, false) => format!("Не попадись иглам · {s} с · награда: сундук"), (1, true) => format!("Don't get hit · {s} s · reward: chest"),
        (_, false) => format!("Огни: {}/{} · {s} с · награда: 2 улучшения", g.room_got, g.room_need), (_, true) => format!("Lights: {}/{} · {s} s · reward: 2 upgrades", g.room_got, g.room_need) };
    (a.to_string(), goal)
}
impl Game {
    pub fn rooms_tick(&mut self, dt: f32) {
        if self.run_mode != RunMode::Normal && self.run_mode != RunMode::Daily { return; }
        if self.room_t > 0. { self.room_tick(dt); return; }
        // портал: шанс один раз за зону, не в зонах владык и не в начале
        if let Some((x, y, l)) = self.portal { let l = l - dt; if l <= 0. || self.boss >= 0 { self.portal = None; } else {
                self.portal = Some((x, y, l)); if (self.p.x - x).powi(2) + (self.p.y - y).powi(2) < 48. * 48. { self.portal = None; self.room_enter(); } } return; }
        if self.boss < 0 && self.zone >= 3 && self.zone % 5 != 0 && self.portal_zone != self.zone && self.zone_t > 18. {
            self.portal_zone = self.zone; if self.rand() < 0.4 { let a = self.rand() * TAU; let (mut x, mut y) = (self.p.x + a.cos() * 260., self.p.y + a.sin() * 260.);
                let l = (x * x + y * y).sqrt(); let m = cfg::ARENA_R - 120.; if l > m { x *= m / l; y *= m / l; }
                self.portal = Some((x, y, 22.)); self.snd(Sfx::Level); let en = i18n::is_en();
                self.banner(if en { "SECRET PORTAL".into() } else { "ТАЙНЫЙ ПОРТАЛ".into() }, if en { "Swim in — a challenge with a reward awaits".into() } else { "Вплыви — внутри испытание с наградой".into() }, 0xffd54f, 2.6); } }
    }
    fn room_enter(&mut self) {
        let k = (self.rand() * 3.) as u8 % 3; self.room_k = k; self.room_t = ROOM_T; self.room_hit = false; self.room_got = 0; self.room_acc = 0.;
        for i in 0..self.en.n { let e = &mut self.en.items[i]; if !e.dead && !e.kind.d().boss { e.dead = true; } } self.eb.n = 0; self.inks.clear();
        self.flash = 1.; self.ring(self.p.x, self.p.y, 10., 400., 0.7, c::GOLD, 8.); self.snd(Sfx::Ach);
        let (a, b) = txt(k); self.banner(a.into(), b.into(), 0xffd54f, 2.6);
        let (px, py) = (self.p.x, self.p.y);
        match k {
            0 => for _ in 0..46 { let a = self.rand() * TAU; let r = self.rr(90., 520.); let (x, y) = (px + a.cos() * r, py + a.sin() * r); if x * x + y * y < (cfg::ARENA_R - 60.).powi(2) { self.drop_pick(x, y, 3, 1.); } },
            2 => { self.room_need = 0; for q in 0..10 { let a = q as f32 / 10. * TAU + self.rand() * 0.3; let r = self.rr(260., 520.); let (x, y) = (px + a.cos() * r, py + a.sin() * r);
                    if x * x + y * y < (cfg::ARENA_R - 60.).powi(2) { self.drop_pick(x, y, 2, 10.); self.room_need += 1; } } }
            _ => {}
        }
    }
    fn room_tick(&mut self, dt: f32) {
        self.room_t -= dt; self.room_acc += dt;
        if self.room_k == 1 { // иглы со всех сторон, всё чаще
            let every = (1.3 - (ROOM_T - self.room_t) * 0.03).max(0.55);
            while self.room_acc > every { self.room_acc -= every; let a = self.rand() * TAU; let (x, y) = (self.p.x + a.cos() * 420., self.p.y + a.sin() * 420.);
                if let Some(i) = self.spawn_enemy(K::Dart, x, y, false) { self.en.items[i].spawn_t = 0.2; } }
            if self.room_hit { self.room_end(false); return; } }
        if self.room_k == 2 && self.room_got >= self.room_need && self.room_need > 0 { self.room_end(true); return; }
        if self.room_t <= 0. { self.room_end(self.room_k != 2); }
    }
    fn room_end(&mut self, ok: bool) {
        self.room_t = 0.; let en = i18n::is_en();
        for i in 0..self.en.n { let e = &mut self.en.items[i]; if !e.dead && e.kind == K::Dart { e.dead = true; } } self.eb.n = 0;
        let (x, y) = (self.p.x, self.p.y); self.ring(x, y, 10., 300., 0.6, c::GOLD, 6.); self.flash = self.flash.max(0.5);
        match (self.room_k, ok) {
            (0, _) => { let n = self.room_got; self.banner(if en { "HOARD COLLECTED".into() } else { "РОССЫПЬ СОБРАНА".into() }, if en { format!("+{n} pearls") } else { format!("+{n} жемчуга") }, 0xffd54f, 2.4); }
            (1, true) => { self.spawn_chest(x, y - 90.); if self.run_mode == RunMode::Normal && !self.god { self.s.shards += 1; self.run_shards += 1; self.dirty = true; }
                self.banner(if en { "FLAWLESS!".into() } else { "БЕЗ ЕДИНОГО УДАРА!".into() }, if en { "A chest and a light shard".into() } else { "Сундук и осколок света".into() }, 0xffd54f, 2.6); }
            (2, true) => { self.level_pending += 2; self.lv_t = -99.; self.level_delay = 0.6; self.banner(if en { "ALL LIGHTS CAUGHT".into() } else { "ВСЕ ОГНИ СОБРАНЫ".into() }, if en { "Two upgrade cards".into() } else { "Две карты улучшений".into() }, 0xffd54f, 2.6); }
            _ => self.banner(if en { "CHALLENGE FAILED".into() } else { "ИСПЫТАНИЕ ПРОВАЛЕНО".into() }, if en { "Next time!".into() } else { "В следующий раз!".into() }, 0xff8a9a, 2.),
        }
    }
}
