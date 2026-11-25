//! Ярусы глубины. С 600 м обычные твари сменяются «багровыми» (ярус 1), с 1100 м — тварями «бездны» (ярус 2):
//! другой облик, крепче, больнее и с новыми атаками. Боссы и стражи на ярусах — новые владыки со своими приёмами.
use crate::data::{c, K, TAU};
use crate::game::*;

/// Палитра свечения яруса
pub fn tier_col(base: u8, tier: u8) -> u8 { match tier { 1 => c::CRAB, 2 => c::AMETH, _ => base } }

impl Game {
    /// Какой ярус у обычной твари на текущей глубине
    pub fn roll_tier(&mut self) -> u8 {
        let z = self.zone; let r = self.rand();
        let p2 = match z { 0..=10 => 0., 11 => 0.5, 12 => 0.85, _ => 1. };
        let p1 = match z { 0..=5 => 0., 6 => 0.5, 7 => 0.85, _ => 1. };
        if r < p2 { 2 } else if r < p1 { 1 } else { 0 }
    }
    /// Применить ярус к только что созданному существу
    pub fn apply_tier(&mut self, i: usize, tier: u8) {
        if tier == 0 { return; }
        let e = &mut self.en.items[i]; let boss = e.kind.d().boss; e.tier = tier;
        let (hp, dm, xp) = if boss { if tier == 1 { (1.25, 1.15, 1.4) } else { (1.5, 1.3, 1.8) } } else if tier == 1 { (1.15, 1.1, 1.3) } else { (1.35, 1.2, 1.6) };
        e.max_hp *= hp; e.hp = e.max_hp; e.dmg *= dm; e.xp *= xp; e.score *= xp; e.spd *= if tier == 1 { 1.06 } else { 1.12 };
        if e.kind == K::Crab { e.sh = e.max_hp * crate::data::cfg::CRAB_SHIELD; }
        e.col = tier_col(e.col, tier); e.tt = 1. + self.rng.next() * 2.;
        let st = if boss && e.kind != K::Boss4 { 1 } else { tier }; let key = format!("{}_t{}", e.kind.key(), st); if !self.s.seen.contains_key(&key) { self.s.seen.insert(key, 1); self.dirty = true; }
    }

    /// Дополнительные приёмы тварей с ярусом
    pub fn tier_extra(&mut self, i: usize, dt: f32, d: f32, ux: f32, uy: f32, fz: bool) {
        let (kind, tier, x, y) = { let e = &self.en.items[i]; (e.kind, e.tier, e.x, e.y) };
        if fz { return; }
        let dsc = self.dmg_scale; let face = uy.atan2(ux); let col = tier_col(0, tier);
        let fire = { let e = &mut self.en.items[i]; e.tt -= dt; if e.tt <= 0. { true } else { false } };
        let mut next = 0f32;
        match kind {
            // рыбы-рывки: короткий бросок к искре
            K::Drifter | K::Fry => if fire { next = if tier == 2 { 1.8 } else { 2.6 };
                if d < 420. { let e = &mut self.en.items[i]; e.vx = ux * e.spd * 3.2; e.vy = uy * e.spd * 3.2; if self.quality > 0 { self.part(x, y, 0., 0., 0.3, 8., col, 0.); } } },
            // игла: после броска веер иголок
            K::Dart => { let st = self.en.items[i].state; if st == 2 && self.en.items[i].tt > 0. { self.en.items[i].tt = -1.; let a = self.en.items[i].ang; let n = if tier == 2 { 5 } else { 3 };
                    for k in 0..n { self.e_shoot(x, y, a + (k as f32 - (n - 1) as f32 / 2.) * 0.32, 260., 4.5, 8. * dsc, col, 0.); } }
                if st == 0 { self.en.items[i].tt = 1.; } }
            // медуза: закрученные кольца и прицельный разряд
            K::Jelly => if fire { next = if tier == 2 { 2.2 } else { 3. }; if d < 600. { let n = if tier == 2 { 10 } else { 7 }; let o = self.rand() * TAU;
                for k in 0..n { self.e_shoot(x, y, o + k as f32 * TAU / n as f32, 95., 5., 8. * dsc, col, if tier == 2 { 0.7 } else { 0.45 }); } self.snd(Sfx::Shot2); } },
            // ёж: выстреливает шипы во все стороны
            K::Urchin => if fire { next = if tier == 2 { 2.4 } else { 3.4 }; if d < 520. { let n = if tier == 2 { 8 } else { 6 }; let o = self.en.items[i].ang;
                for k in 0..n { self.e_shoot(x, y, o + k as f32 * TAU / n as f32, 180., 4., 8. * dsc, col, 0.); } } },
            // кальмар: самонаводящийся сгусток
            K::Squid => if fire { next = if tier == 2 { 2.6 } else { 3.6 }; if d < 560. { if let Some(b) = self.e_shoot(x, y, face, 150., 7., 11. * dsc, col, 0.) { self.eb.items[b].acc = if tier == 2 { 2.2 } else { 1.4 }; } } },
            // угорь: хвост оставляет жгучие искры
            K::Eel => if fire { next = if tier == 2 { 0.35 } else { 0.6 }; if let Some(b) = self.e_shoot(x, y, self.en.items[i].ang + std::f32::consts::PI, 20., 5., 7. * dsc, col, 0.) { self.eb.items[b].life = 2.5; } },
            // краб: щит восстанавливается, удар клешнёй — волна
            K::Crab => { let (sh, mh) = (self.en.items[i].sh, self.en.items[i].max_hp); if sh <= 0. && self.en.items[i].tt < -6. { self.en.items[i].sh = mh * 0.3; self.en.items[i].tt = 0.; self.ring(x, y, 5., 40., 0.3, col, 3.); }
                if sh > 0. && fire { next = 3.2; if d < 200. { let n = if tier == 2 { 12 } else { 8 }; for k in 0..n { self.e_shoot(x, y, face + (k as f32 - n as f32 / 2.) * 0.12, 200., 5., 9. * dsc, col, 0.); } self.shake(3.); } } }
            // целитель: заодно даёт соседям щит
            K::Mender => if fire { next = 4.; let q = self.qb(x, y, 170.); for &k in &q { let o = &mut self.en.items[k]; if !o.dead && !o.kind.d().boss && k != i { o.hp = (o.hp + o.max_hp * 0.15).min(o.max_hp); } } self.qb_back(q); self.ring(x, y, 8., 170., 0.4, col, 2.); },
            // бомбер: по пути сеет мины-пули
            K::Bomber => if fire { next = if tier == 2 { 0.9 } else { 1.4 }; if let Some(b) = self.e_shoot(x, y, 0., 0., 6., 10. * dsc, col, 0.) { self.eb.items[b].life = 4.; } },
            // скат: рывок оставляет полосу пуль по бокам
            K::Ray => if self.en.items[i].state == 2 && fire { next = 0.08; let a = self.en.items[i].ang; for s in [-1f32, 1.] { self.e_shoot(x, y, a + s * std::f32::consts::FRAC_PI_2, 70., 4.5, 8. * dsc, col, 0.); } },
            // фонарщик: залп огоньков-брызг
            K::Lantern => if fire { next = 3.; if d < 600. { for k in -1..=1 { self.e_shoot(x, y, face + k as f32 * 0.25, 170., 5., 9. * dsc, col, 0.); } } },
            K::Spawner => if fire { next = 5.; if d < 600. { let n = if tier == 2 { 3 } else { 2 }; for _ in 0..n { let a = self.rand() * TAU; self.spawn_enemy(K::Fry, x + a.cos() * 26., y + a.sin() * 26., false); } } },
            K::Boss1 | K::Boss2 | K::Boss3 | K::Boss4 | K::KingCrab | K::Queen => { if fire { next = self.boss_tier_attack(i, d, face); } }
            _ => {}
        }
        if next > 0. { self.en.items[i].tt = next; }
        let _ = ux;
    }

    /// Приёмы новых владык (боссы и стражи на ярусах). Возвращает паузу до следующего приёма
    fn boss_tier_attack(&mut self, i: usize, d: f32, face: f32) -> f32 {
        let (kind, tier, x, y, enr) = { let e = &self.en.items[i]; (e.kind, e.tier, e.x, e.y, e.hp < e.max_hp * 0.5) };
        let dsc = self.dmg_scale; let col = tier_col(0, tier); let k = if enr { 0.7 } else { 1. }; let _ = d;
        let c2 = self.en.items[i].p3; self.en.items[i].tt2 += 1.; let step = self.en.items[i].tt2 as i32;
        match kind {
            // Огненный Левиафан / Змей бездны: огненное дыхание конусом и кольцо осколков
            K::Boss4 => { if step % 3 == 0 { let n = 14; let o = self.rand() * TAU; for q in 0..n { self.e_shoot(x, y, o + q as f32 * TAU / n as f32, 140., 6., 10. * dsc, if tier == 1 { c::FIRE } else { col }, 0.); } self.snd(Sfx::Shot2); }
                else { for q in -4..=4 { self.e_shoot(x, y, face + q as f32 * 0.09, 230. + (q as f32).abs() * 6., 5.5, 10. * dsc, if tier == 1 { c::FIRE } else { col }, 0.); } self.snd(Sfx::Shot2); } 2.2 * k }
            // Багровый удильщик: самонаводящиеся приманки
            K::Boss1 => { for q in 0..if enr { 4 } else { 3 } { if let Some(b) = self.e_shoot(x, y, face + (q as f32 - 1.) * 0.6, 120., 8., 12. * dsc, col, 0.) { self.eb.items[b].acc = 1.6; } } 2.6 * k }
            // Тёмная Матерь: двойная спираль
            K::Boss2 => { let o = c2 + step as f32 * 0.37; for q in 0..8 { self.e_shoot(x, y, o + q as f32 * TAU / 8., 130., 6., 11. * dsc, col, 0.35); self.e_shoot(x, y, -o + q as f32 * TAU / 8., 130., 6., 11. * dsc, col, -0.35); } 1.8 * k }
            // Чёрное Сердце: волна-«удар» с разрывом, который нужно найти
            K::Boss3 => { let n = 36; let gap = self.rand() * TAU; for q in 0..n { let a = q as f32 * TAU / n as f32; if super::tiers::ang_d(a, gap) < 0.45 { continue; } self.e_shoot(x, y, a, 120., 6., 12. * dsc, col, 0.); } self.snd(Sfx::Beat); self.shake(4.); 2.8 * k }
            // Король бездны: веер клешней
            K::KingCrab => { for q in -5..=5 { self.e_shoot(x, y, face + q as f32 * 0.14, 210., 6., 11. * dsc, col, 0.); } 2.4 * k }
            // Королева тьмы: кольцо медленных искр
            K::Queen => { let n = 18; let o = self.rand(); for q in 0..n { self.e_shoot(x, y, o + q as f32 * TAU / n as f32, 100., 6., 10. * dsc, col, 0.25); } 2.6 * k }
            _ => 3.,
        }
    }

    /// Гибель твари с ярусом
    pub fn tier_death(&mut self, e: &Enemy) {
        if e.tier == 0 { return; } let col = tier_col(0, e.tier); let dsc = self.dmg_scale;
        match e.kind {
            K::Drifter if e.tier == 2 => { for s in [-1f32, 1.] { let a = e.ang + s * 1.2; if let Some(f) = self.spawn_enemy(K::Fry, e.x + a.cos() * 10., e.y + a.sin() * 10., false) { let ff = &mut self.en.items[f]; ff.spawn_t = 0.; ff.vx = a.cos() * 200.; ff.vy = a.sin() * 200.; } } }
            K::Urchin | K::Bomber => { let n = if e.tier == 2 { 14 } else { 10 }; for k in 0..n { self.e_shoot(e.x, e.y, k as f32 * TAU / n as f32 + 0.2, 160., 5., 9. * dsc, col, 0.); } }
            K::Jelly if e.tier == 2 => { for k in 0..6 { self.e_shoot(e.x, e.y, k as f32 * TAU / 6., 80., 5., 8. * dsc, col, 0.6); } }
            _ => {}
        }
    }
}
pub fn ang_d(a: f32, b: f32) -> f32 { ang_diff(a, b).abs() }

/// Имена новых владык по ярусу
pub fn boss_name(k: K, tier: u8, en: bool) -> Option<&'static str> {
    Some(match (k, tier, en) {
        (K::Boss4, 1, false) => "ОГНЕННЫЙ ЛЕВИАФАН", (K::Boss4, 1, true) => "THE FIRE LEVIATHAN",
        (K::Boss4, 2, false) => "ЗМЕЙ БЕЗДНЫ", (K::Boss4, 2, true) => "THE ABYSS SERPENT",
        (K::Boss1, _, false) => "БАГРОВЫЙ УДИЛЬЩИК", (K::Boss1, _, true) => "THE CRIMSON ANGLER",
        (K::Boss2, _, false) => "ТЁМНАЯ МАТЕРЬ", (K::Boss2, _, true) => "THE DARK MOTHER",
        (K::Boss3, _, false) => "ЧЁРНОЕ СЕРДЦЕ", (K::Boss3, _, true) => "THE BLACK HEART",
        (K::KingCrab, _, false) => "КОРОЛЬ БЕЗДНЫ", (K::KingCrab, _, true) => "THE ABYSS KING",
        (K::Queen, _, false) => "КОРОЛЕВА ТЬМЫ", (K::Queen, _, true) => "THE QUEEN OF DARK",
        _ => return None })
}
/// Имена тварей ярусов (бестиарий)
pub fn foe_name(k: K, tier: u8, en: bool) -> Option<&'static str> {
    let ru1 = |k: K| match k { K::Drifter => "Багровый плавунец", K::Dart => "Огненная игла", K::Jelly => "Жгучая медуза", K::Urchin => "Огненный ёж", K::Spikelet => "Горячий шип",
        K::Eel => "Жгучий угорь", K::Squid => "Кровавый кальмар", K::Crab => "Багровый краб", K::Mender => "Хранитель", K::Bomber => "Вулкан", K::Ray => "Огненный скат",
        K::Lantern => "Факельщик", K::Wisp => "Уголёк", K::Spawner => "Кровавый пузырник", K::Fry => "Искромалёк", K::Nautilus => "Кровавый наутилус", K::Hermit => "Огненный отшельник", K::Seahorse => "Огненный снайпер", K::Cuttle => "Багровая каракатица", K::Puffer => "Огненный шар", _ => "" };
    let ru2 = |k: K| match k { K::Drifter => "Пустотник", K::Dart => "Призрачная игла", K::Jelly => "Медуза бездны", K::Urchin => "Звёздный ёж", K::Spikelet => "Осколок звезды",
        K::Eel => "Угорь бездны", K::Squid => "Кальмар-тень", K::Crab => "Краб бездны", K::Mender => "Жрец бездны", K::Bomber => "Сверхновая", K::Ray => "Скат-призрак",
        K::Lantern => "Маяк бездны", K::Wisp => "Блуждающий огонь", K::Spawner => "Матка бездны", K::Fry => "Теневой малёк", K::Nautilus => "Наутилус бездны", K::Hermit => "Отшельник бездны", K::Seahorse => "Теневой снайпер", K::Cuttle => "Призрачная каракатица", K::Puffer => "Шар бездны", _ => "" };
    let en1 = |k: K| match k { K::Drifter => "Crimson Drifter", K::Dart => "Fire Needle", K::Jelly => "Burning Jelly", K::Urchin => "Fire Urchin", K::Spikelet => "Hot Spike",
        K::Eel => "Burning Eel", K::Squid => "Blood Squid", K::Crab => "Crimson Crab", K::Mender => "Keeper", K::Bomber => "Volcano", K::Ray => "Fire Ray",
        K::Lantern => "Torchbearer", K::Wisp => "Ember", K::Spawner => "Blood Spawner", K::Fry => "Spark Fry", K::Nautilus => "Blood Nautilus", K::Hermit => "Fire Hermit", K::Seahorse => "Fire Sniper", K::Cuttle => "Crimson Cuttlefish", K::Puffer => "Fire Puffer", _ => "" };
    let en2 = |k: K| match k { K::Drifter => "Voidling", K::Dart => "Ghost Needle", K::Jelly => "Abyss Jelly", K::Urchin => "Star Urchin", K::Spikelet => "Star Shard",
        K::Eel => "Abyss Eel", K::Squid => "Shadow Squid", K::Crab => "Abyss Crab", K::Mender => "Abyss Priest", K::Bomber => "Supernova", K::Ray => "Ghost Ray",
        K::Lantern => "Abyss Beacon", K::Wisp => "Will-o'-wisp", K::Spawner => "Abyss Brood", K::Fry => "Shadow Fry", K::Nautilus => "Abyss Nautilus", K::Hermit => "Abyss Hermit", K::Seahorse => "Shadow Sniper", K::Cuttle => "Phantom Cuttlefish", K::Puffer => "Abyss Puffer", _ => "" };
    let s = match (tier, en) { (1, false) => ru1(k), (1, true) => en1(k), (2, false) => ru2(k), (2, true) => en2(k), _ => "" };
    if s.is_empty() { None } else { Some(s) }
}
/// Чем опасна тварь яруса (бестиарий)
pub fn foe_desc(k: K, tier: u8, en: bool) -> &'static str {
    match (k, en) {
        (K::Drifter, false) => if tier == 2 { "Рывками бросается на свет, погибая — распадается на мальков." } else { "Время от времени делает резкий рывок к тебе." },
        (K::Drifter, true) => if tier == 2 { "Lunges at the light; splits into fry on death." } else { "Every so often lunges straight at you." },
        (K::Dart, false) => "После броска разбрасывает веер игл.", (K::Dart, true) => "Throws a fan of needles after each lunge.",
        (K::Jelly, false) => "Выпускает закрученные кольца искр.", (K::Jelly, true) => "Releases twisting rings of sparks.",
        (K::Urchin, false) => "Стреляет шипами во все стороны и взрывается.", (K::Urchin, true) => "Shoots spikes all around and explodes.",
        (K::Squid, false) => "Плюётся самонаводящимися сгустками.", (K::Squid, true) => "Spits homing blobs.",
        (K::Eel, false) => "Хвост оставляет жгучие искры.", (K::Eel, true) => "Its tail leaves burning sparks.",
        (K::Crab, false) => "Щит отрастает заново, вблизи бьёт волной.", (K::Crab, true) => "Its shield regrows; slams a wave up close.",
        (K::Mender, false) => "Подлечивает соседей чаще. Убивай первым!", (K::Mender, true) => "Heals neighbors more often. Kill it first!",
        (K::Bomber, false) => "Сеет за собой мины.", (K::Bomber, true) => "Drops mines behind it.",
        (K::Ray, false) => "Рывок оставляет полосу пуль.", (K::Ray, true) => "Its charge leaves a stripe of bullets.",
        (K::Lantern, false) => "Залп из трёх огней.", (K::Lantern, true) => "Fires volleys of three flames.",
        (K::Spawner, false) => "Выпускает свирепых мальков.", (K::Spawner, true) => "Releases fierce fry.",
        (K::Nautilus, false) => "Спираль чернил гуще и быстрее.", (K::Nautilus, true) => "A thicker, faster ink spiral.",
        (K::Hermit, false) => "Раковина крепче, залп из пяти.", (K::Hermit, true) => "A tougher shell and a five-shot volley.",
        (K::Seahorse, false) => "Целится быстрее.", (K::Seahorse, true) => "Aims faster.",
        (K::Cuttle, false) => "Бросок длиннее, чернил больше.", (K::Cuttle, true) => "A longer lunge and more ink.",
        (K::Puffer, false) => "Иглы летят двойным кольцом.", (K::Puffer, true) => "Spines fly in a double ring.",
        (_, false) => "Обитатель глубин, сильнее родичей сверху.", (_, true) => "A deep dweller, stronger than its kin above.",
    }
}
