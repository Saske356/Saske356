//! 4.4: описания улучшений забега с точными цифрами — что даст СЛЕДУЮЩИЙ уровень и сколько будет всего.
//! Цифры берутся из тех же формул, что в compute_stats / upg2.rs: поменял формулу — поправь и тут.
//! Синергии: описание + рецепт («Сочетание: A ур.2 + B ур.2») собирается из UPG[..].syn.
use crate::data::UPG;
use crate::i18n;

/// Улучшения, которые больше не выпадают (дубли): Водоворот = Вакуум, Жадность = Ловец удачи
pub const OFF: [&str; 2] = ["vortex", "greed"];

fn f(x: f32) -> String { let r = (x * 10.).round() / 10.; if (r - r.round()).abs() < 0.01 { format!("{}", r.round() as i32) } else { format!("{r:.1}").replace('.', if i18n::is_en() { "." } else { "," }) } }
fn pct(x: f32) -> String { f(x * 100.) }

/// Описание улучшения id на уровне n (n — уровень, который получишь, взяв карту)
pub fn desc(id: &str, n: u8) -> String {
    let en = i18n::is_en(); let l = n as f32;
    let s = |ru: String, e: String| if en { e } else { ru };
    match id {
        "dmg" => s(format!("Урон снарядов +25% (всего +{}%)", pct(0.25 * l)), format!("Projectile damage +25% (total +{}%)", pct(0.25 * l))),
        "rate" => s(format!("Скорострельность +18% (всего +{}%)", pct(0.18 * l)), format!("Fire rate +18% (total +{}%)", pct(0.18 * l))),
        "multi" => s(format!("+1 снаряд в залпе (будет {})", 1 + n), format!("+1 projectile per volley (total {})", 1 + n)),
        "pierce" => s(format!("Снаряд пробивает врага насквозь и летит дальше (пробивает {})", n), format!("Projectiles pass through foes (pierce {})", n)),
        "bounce" => s(format!("После попадания снаряд отскакивает к ближайшему врагу (отскоков: {})", n), format!("After a hit the projectile bounces to the nearest foe ({} bounces)", n)),
        "crit" => s(format!("Шанс крита {}%, крит бьёт ×2,2", pct(0.05 + 0.1 * l)), format!("{}% crit chance, crits deal ×2.2", pct(0.05 + 0.1 * l))),
        "chain" => s(format!("С шансом {}% попадание бьёт молнией ещё {} врагов рядом (60% урона)", pct(0.14 + 0.08 * l), 1 + n), format!("{}% chance a hit arcs lightning to {} more foes (60% damage)", pct(0.14 + 0.08 * l), 1 + n)),
        "orbit" => s(format!("Вокруг тебя кружат споры: {} шт., каждая бьёт на 90% урона", n), format!("Spores orbit you: {} of them, each deals 90% damage", n)),
        "nova" => s(format!("Каждые {} с — волна света радиусом {}: {}% урона всем и стирает вражеские пули", f(4.4 - 0.5 * l), f(135. + 18. * l), pct(1.4 + 0.45 * l)),
                    format!("Every {} s — a light wave of radius {}: {}% damage to all and erases enemy bullets", f(4.4 - 0.5 * l), f(135. + 18. * l), pct(1.4 + 0.45 * l))),
        "mine" => s(format!("Каждые {} с оставляешь мину: взрыв радиусом {} на {}% урона, когда рядом враг", f(3.2 - 0.45 * l), f(85. + 10. * l), pct(2.6 + 0.4 * l)),
                    format!("Every {} s you drop a mine: a blast of radius {} for {}% damage when a foe is near", f(3.2 - 0.45 * l), f(85. + 10. * l), pct(2.6 + 0.4 * l))),
        "frost" => s(format!("Попадание замедляет врага на 40% на {} с", f(0.6 + 0.5 * l)), format!("Hits slow foes by 40% for {} s", f(0.6 + 0.5 * l))),
        "homing" => s(format!("Снаряды доворачивают к ближайшей цели (сила {}/3)", n), format!("Projectiles curve toward the nearest target (strength {}/3)", n)),
        "hp" => s(format!("+25 к здоровью (всего +{}) и сразу лечит 15%", 25 * n as u32), format!("+25 max health (total +{}) and heals 15% now", 25 * n as u32)),
        "regen" => s(format!("Восстанавливаешь {} здоровья в секунду", f(0.5 * l)), format!("Regenerate {} health per second", f(0.5 * l))),
        "speed" => s(format!("Скорость +10% (всего +{}%)", pct(0.1 * l)), format!("Speed +10% (total +{}%)", pct(0.1 * l))),
        "magnet" => s(format!("Радиус сбора опыта и жемчуга +40% (всего +{}%)", pct(0.4 * l)), format!("Pickup radius +40% (total +{}%)", pct(0.4 * l))),
        "armor" => s(format!("Каждый удар по тебе слабее на {}%", pct(0.07 * l)), format!("Every hit you take is {}% weaker", pct(0.07 * l))),
        "dash" => s(format!("Рывок перезаряжается на {}% быстрее и ранит врагов на пути (250% урона)", pct(0.2 * l)), format!("Dash recharges {}% faster and hurts foes in its path (250% damage)", pct(0.2 * l))),
        "flare" => s(format!("Вспышка заряжается на {}% быстрее", pct(0.3 * l)), format!("Flare charges {}% faster", pct(0.3 * l))),
        "burn" => s(format!("Попадание поджигает врага на 3 с: {}% урона в секунду (кроме владык)", pct(0.14 + 0.1 * l)), format!("Hits set foes on fire for 3 s: {}% damage per second (not lords)", pct(0.14 + 0.1 * l))),
        "siphon" => s(format!("С шансом {}% убийство лечит 1,2% здоровья (владыка — 7%)", pct(0.1 + 0.07 * l)), format!("{}% chance a kill heals 1.2% health (a lord — 7%)", pct(0.1 + 0.07 * l))),
        "echo" => s(format!("С шансом {}% залп тут же повторяется (80% урона)", pct(0.12 + 0.1 * l)), format!("{}% chance a volley repeats at once (80% damage)", pct(0.12 + 0.1 * l))),
        "barrier" => s(format!("Щит гасит один удар целиком и возвращается через {} с", f(9. - 1.4 * l)), format!("A shield blocks one hit completely and returns after {} s", f(9. - 1.4 * l))),
        "overcharge" => s(format!("Каждый {}-й выстрел — тяжёлый снаряд: {}% урона, пробивает 4 врагов", 7 - n as u32, pct(3. + l)), format!("Every {}th shot is a heavy round: {}% damage, pierces 4 foes", 7 - n as u32, pct(3. + l))),
        "harpoon" => s(format!("Каждые {} с гарпун летит в самого крепкого врага: {}% урона, пробивает всех на пути", f(3.4 - 0.6 * l), pct(5. + 3. * l)),
                       format!("Every {} s a harpoon flies at the toughest foe: {}% damage, pierces everything", f(3.4 - 0.6 * l), pct(5. + 3. * l))),
        "beam" => s(format!("Луч без остановки жжёт ближайшего врага (до 300): {}% урона в секунду", pct(1.1 + 0.7 * l)), format!("A beam constantly burns the nearest foe (range 300): {}% damage per second", pct(1.1 + 0.7 * l))),
        "aura" => s(format!("Враги ближе {} к тебе получают {}% урона в секунду", f(95. + 15. * l), pct(0.45 + 0.3 * l)), format!("Foes within {} take {}% damage per second", f(95. + 15. * l), pct(0.45 + 0.3 * l))),
        "twin" => s(format!("Искра-близнец рядом стреляет раз в {} с на {}% урона", f(0.9 - 0.12 * l), pct(0.45 + 0.15 * l)), format!("A twin spark shoots every {} s for {}% damage", f(0.9 - 0.12 * l), pct(0.45 + 0.15 * l))),
        "static" => s(format!("Каждые {} убийств — разряд: молнии бьют {} врагов на экране", 14 - 3 * n as u32, 2 + n), format!("Every {} kills — a discharge: lightning hits {} foes on screen", 14 - 3 * n as u32, 2 + n)),
        "rage" => s(format!("Урон +{}%, а при здоровье ниже 40% — +{}%", pct(0.12 * l), pct(0.24 * l)), format!("Damage +{}%, and +{}% below 40% health", pct(0.12 * l), pct(0.24 * l))),
        "ink" => s(format!("Когда тебя ранят — чернильное облако радиусом {}: стирает пули и замедляет врагов. Неуязвимость после удара +{} с", f(150. + 25. * l), f(0.3 * l)),
                   format!("When hurt — an ink cloud of radius {}: erases bullets and slows foes. +{} s invulnerability after a hit", f(150. + 25. * l), f(0.3 * l))),
        "thorns" => s(format!("Враг, коснувшийся тебя, получает {}% урона и отлетает", pct(2.5 + 1.5 * l)), format!("A foe touching you takes {}% damage and is knocked back", pct(2.5 + 1.5 * l))),
        "salvo" => s(format!("Каждый {}-й выстрел — кольцо из 8 снарядов вокруг тебя (70% урона)", 8 - n.min(3) as u32), format!("Every {}th shot — a ring of 8 projectiles around you (70% damage)", 8 - n.min(3) as u32)),
        "seeker" => s(format!("Каждые {} с: {} ракет(ы) летят в ближайшего врага и взрываются ({}% урона)", f(3.4 - 0.5 * l), n, pct(2.2 + 0.4 * l)),
                      format!("Every {} s: {} rocket(s) fly at the nearest foe and explode ({}% damage)", f(3.4 - 0.5 * l), n, pct(2.2 + 0.4 * l))),
        "caliber" => s(format!("Снаряды крупнее, урон +{}%, но стрельба на {}% реже", pct(0.12 * l), pct(0.04 * l)), format!("Bigger projectiles, damage +{}%, but fire rate −{}%", pct(0.12 * l), pct(0.04 * l))),
        "execute" => s(format!("Враг, у которого осталось меньше {}% здоровья, погибает сразу (кроме владык)", pct(0.08 + 0.04 * l)), format!("A foe below {}% health dies at once (not lords)", pct(0.08 + 0.04 * l))),
        "chill" => s(format!("Замедленные и замороженные враги получают +{}% урона. Пара к «Холоду бездны»", pct(0.2 * l)), format!("Slowed and frozen foes take +{}% damage. Pairs with Abyssal Chill", pct(0.2 * l))),
        "dashnova" => s(format!("В конце рывка — волна радиусом {}: {}% урона, стирает пули", f(110. + 30. * l), pct(2. + l)), format!("At the end of a dash — a wave of radius {}: {}% damage, erases bullets", f(110. + 30. * l), pct(2. + l))),
        "mark" => s(format!("Самый крепкий враг на экране помечен и получает +{}% урона", pct(0.25 + 0.1 * l)), format!("The toughest foe on screen is marked and takes +{}% damage", pct(0.25 + 0.1 * l))),
        "fortune" => s(format!("Шанс {}% на лишнюю жемчужину с врага (с элиты ×6) и опыт +{}%", f(0.8 * l), pct(0.05 * l)), format!("{}% chance of an extra pearl per foe (×6 from elites) and +{}% XP", f(0.8 * l), pct(0.05 * l))),
        "frenzy" => s(format!("Каждые 10 комбо — скорострельность +{}% (до +{}%)", pct(0.04 * l), pct(0.4 * l / 3.)), format!("Every 10 combo — fire rate +{}% (up to +{}%)", pct(0.04 * l), pct(0.4 * l / 3.))),
        "shards" => s(format!("Убитый враг разлетается {} осколками света (50% урона)", 1 + n), format!("A slain foe bursts into {} light shards (50% damage)", 1 + n)),
        "vacuum" => s(format!("Каждые {} с весь опыт на экране летит к тебе", f(11. - 3. * l)), format!("Every {} s all XP on screen flies to you", f(11. - 3. * l))),
        "thunder" => s(format!("Каждые {} с: {} молнии бьют случайных врагов на экране (300% урона)", f(4.2 - 0.6 * l), 1 + n), format!("Every {} s: {} lightning bolts strike random foes on screen (300% damage)", f(4.2 - 0.6 * l), 1 + n)),
        "vortex" | "greed" => i18n::upg(id).1,
        // ---- синергии ----
        "storm" => s("Споры-спутники бьют цепными молниями по соседям".into(), "Orbiting spores arc chain lightning to nearby foes".into()),
        "supernova" => s("Волна «Импульса» ×2 урона и на 40% шире; убитые ею враги взрываются".into(), "Pulse waves deal ×2 damage and are 40% wider; foes they kill explode".into()),
        "prism" => s("Снаряд при попадании раскалывается на два".into(), "Projectiles split in two on hit".into()),
        "abyssice" => s("Мины замораживают всех в радиусе взрыва".into(), "Mines freeze everything in the blast".into()),
        "hunter" => s("Урон +40%, снаряды летят на 15% быстрее".into(), "Damage +40%, projectiles fly 15% faster".into()),
        "tide" => s("Рывок стирает вражеские пули и оставляет волну".into(), "Dash erases enemy bullets and leaves a wave".into()),
        "wildfire" => s("Горение на 30% сильнее, горящие враги при гибели поджигают соседей".into(), "Burning is 30% stronger; burning foes ignite neighbours on death".into()),
        "aegis" => s("Второй заряд щита, а погашенный удар бьёт в ответ".into(), "A second shield charge, and a blocked hit strikes back".into()),
        "leech" => s("Каждое убийство лечит 0,8% здоровья (владыка — 5%)".into(), "Every kill heals 0.8% health (a lord — 5%)".into()),
        "spear" => s("Гарпуны летят тройкой и бьют на 30% сильнее".into(), "Harpoons fly in threes and hit 30% harder".into()),
        "lighthouse" => s("Луч замедляет и перескакивает на вторую цель".into(), "The beam slows and jumps to a second target".into()),
        "maelstrom" => s("Давление глубин на 40% шире и затягивает врагов к тебе".into(), "Deep Pressure is 40% wider and pulls foes in".into()),
        "choir" => s("Близнец стреляет веером из трёх снарядов".into(), "The twin fires a fan of three".into()),
        "tempest" => s("Разряд бьёт вдвое больше врагов".into(), "Discharge hits twice as many foes".into()),
        "kraken" => s("Чернильное облако держится 3 с и душит врагов внутри".into(), "The ink cloud lasts 3 s and chokes foes inside".into()),
        "hurricane" => s("Кольцо «Залпа» — 16 снарядов, каждый пробивает 2 врагов".into(), "Salvo rings have 16 projectiles, each piercing 2 foes".into()),
        "bombard" => s("+2 ракеты, взрывы шире и поджигают".into(), "+2 rockets, wider blasts that set foes on fire".into()),
        "reaper" => s("Добивание срабатывает на 8% раньше, и каждое бьёт молнией двух соседей".into(), "Execute triggers 8% earlier, and each one arcs lightning to two neighbours".into()),
        "blizzard" => s("Удар по замедленному врагу с шансом 12% замораживает его".into(), "Hitting a slowed foe has a 12% chance to freeze it".into()),
        "stormlord" => s("Молнии Грома перескакивают ещё на 3 врагов".into(), "Thunder bolts jump to 3 more foes".into()),
        "shardstorm" => s("+2 осколка, осколки пробивают 2 врагов".into(), "+2 shards, shards pierce 2 foes".into()),
        _ => i18n::upg(id).1,
    }
}

/// Рецепт синергии для карты: «Сочетание: Споры-спутники 2 + Цепная искра 2»
pub fn recipe(i: usize) -> Option<String> {
    let (a, la, b, lb) = UPG[i].syn?;
    let (na, nb) = (i18n::upg(UPG[a].id).0, i18n::upg(UPG[b].id).0);
    Some(format!("{}: {na} {la} + {nb} {lb}", if i18n::is_en() { "Combo" } else { "Сочетание" }))
}
/// Полный текст карты: описание + рецепт у синергии
pub fn card(i: usize, n: u8) -> String {
    let mut d = desc(UPG[i].id, n); if let Some(r) = recipe(i) { d = format!("{d}\n{r}"); }
    // подсказка об эволюции: базовое улучшение на максимуме + второе улучшение
    if let Some(e) = crate::content::EVOS.iter().find(|e| e.upg == i) { let (en, nm) = (i18n::is_en(), i18n::upg(UPG[e.need].id).0);
        d = format!("{d}\n{}", if en { format!("Evolution: max level + {nm} {}", e.need_lv) } else { format!("Эволюция: макс. уровень + {nm} {}", e.need_lv) }); }
    d
}

// ---------- 4.8.5: улучшения под особые искры ----------
// Бумеранг (10), Коса (11), Призыватель (12), Минёр (13) стреляют не обычными снарядами: часть общих улучшений
// для них бессмысленна (выпадать не должна), а часть работает иначе — со своим названием и описанием.
pub const F_BOOM: u8 = 10; pub const F_SCYTHE: u8 = 11; pub const F_SUMMON: u8 = 12; pub const F_MINER: u8 = 13;
/// Улучшение не выпадает этой искре
pub fn form_skip(form: u8, id: &str) -> bool {
    // 4.9.2: то, что искре не нужно или дублирует её атаку/суперспособность
    match form {
        1 => matches!(id, "caliber"),                       // Игла: быстрые тонкие иглы — крупный медленный снаряд противоречит
        6 => matches!(id, "homing"),                        // Призрак: снаряды и так доворачивают
        7 => matches!(id, "burn"),                          // Уголёк: и так всё поджигает
        F_BOOM | F_MINER => matches!(id, "pierce" | "bounce" | "homing" | "overcharge"),
        F_SCYTHE => matches!(id, "pierce" | "bounce" | "homing" | "overcharge" | "execute"), // казнь — у суперспособности «Жнец»
        F_SUMMON => matches!(id, "bounce" | "homing" | "overcharge"),
        _ => false }
}
/// Своё название улучшения для особой искры
pub fn form_name(form: u8, id: &str) -> Option<&'static str> {
    let en = i18n::is_en();
    let (ru, e) = match (form, id) {
        (f, "flare") if f != 0 => ("Суперзаряд", "Super charge"),
        (F_SCYTHE, "multi") => ("Ещё лезвие", "Extra blade"), (F_SCYTHE, "caliber") => ("Длинные косы", "Long scythes"), (F_SCYTHE, "rate") => ("Быстрый взмах", "Quick swing"),
        (F_SCYTHE, "dmg") => ("Острые лезвия", "Keen blades"), (F_SCYTHE, "salvo") => ("Круговой взмах", "Full circle"), (F_SCYTHE, "overcharge") => ("Жатва", "Harvest"), (F_SCYTHE, "echo") => ("Второй взмах", "Double swing"),
        (F_BOOM, "multi") => ("Ещё бумеранг", "Extra boomerang"), (F_BOOM, "caliber") => ("Тяжёлые бумеранги", "Heavy boomerangs"), (F_BOOM, "rate") => ("Быстрый бросок", "Quick throw"),
        (F_BOOM, "dmg") => ("Острые кромки", "Sharp edges"), (F_BOOM, "salvo") => ("Звезда бумерангов", "Boomerang star"), (F_BOOM, "echo") => ("Двойной бросок", "Double throw"),
        (F_SUMMON, "multi") => ("Стайка", "Shoal"), (F_SUMMON, "caliber") => ("Крупные мальки", "Big fry"), (F_SUMMON, "rate") => ("Нерест", "Spawning"),
        (F_SUMMON, "dmg") => ("Зубастые мальки", "Toothy fry"), (F_SUMMON, "pierce") => ("Сквозь строй", "Through the ranks"), (F_SUMMON, "salvo") => ("Выводок", "Brood"), (F_SUMMON, "echo") => ("Двойня", "Twins"),
        (F_MINER, "multi") => ("Россыпь мин", "Mine spread"), (F_MINER, "caliber") => ("Мощные мины", "Heavy mines"), (F_MINER, "rate") => ("Быстрый минёр", "Quick sapper"),
        (F_MINER, "dmg") => ("Усиленный заряд", "Bigger charge"), (F_MINER, "salvo") => ("Минное кольцо", "Mine ring"), (F_MINER, "echo") => ("Вторая закладка", "Second charge"),
        _ => return None };
    Some(if en { e } else { ru })
}
/// Своё описание (None — общее)
pub fn form_desc(form: u8, id: &str, n: u8) -> Option<String> {
    let en = i18n::is_en(); let l = n as f32; let s = |ru: String, e: String| Some(if en { e } else { ru });
    match (form, id) {
        (f, "flare") if f != 0 => s(format!("Суперспособность заряжается на {}% быстрее", pct(0.3 * l)), format!("Your super ability charges {}% faster", pct(0.3 * l))),
        (F_SCYTHE, "multi") => s(format!("+1 лезвие (будет {}): косы расходятся по кругу равномерно, закрывая тебя со всех сторон", 1 + n), format!("+1 blade (total {}): blades spread evenly in a circle around you", 1 + n)),
        (F_SCYTHE, "caliber") => s(format!("Косы раскручиваются дальше (+{}% радиуса) и шире, урон +{}%, но взмахи на {}% реже", pct(0.18 * l), pct(0.12 * l), pct(0.04 * l)), format!("Blades spin out farther (+{}% reach) and wider, damage +{}%, swings {}% rarer", pct(0.18 * l), pct(0.12 * l), pct(0.04 * l))),
        (F_SCYTHE, "rate") => s(format!("Новые косы запускаются на 18% чаще (всего +{}%)", pct(0.18 * l)), format!("New blades launch 18% more often (total +{}%)", pct(0.18 * l))),
        (F_SCYTHE, "dmg") => s(format!("Урон кос +25% (всего +{}%)", pct(0.25 * l)), format!("Blade damage +25% (total +{}%)", pct(0.25 * l))),
        (F_SCYTHE, "salvo") => s(format!("Каждый {}-й взмах — 8 кос сразу раскручиваются во все стороны (70% урона)", 8 - n.min(3) as u32), format!("Every {}th swing — 8 blades spin out in all directions (70% damage)", 8 - n.min(3) as u32)),
        (F_SCYTHE, "overcharge") => s(format!("Каждый {}-й взмах — огромная коса: {}% урона", 7 - n as u32, pct(3. + l)), format!("Every {}th swing is a huge scythe: {}% damage", 7 - n as u32, pct(3. + l))),
        (F_SCYTHE, "echo") => s(format!("С шансом {}% взмах тут же повторяется (80% урона)", pct(0.12 + 0.1 * l)), format!("{}% chance a swing repeats at once (80% damage)", pct(0.12 + 0.1 * l))),
        (F_BOOM, "multi") => s(format!("+1 бумеранг за бросок (будет {}), летят веером", 1 + n), format!("+1 boomerang per throw (total {}), thrown in a fan", 1 + n)),
        (F_BOOM, "caliber") => s(format!("Бумеранги крупнее и бьют на {}% сильнее, но бросок на {}% реже", pct(0.12 * l), pct(0.04 * l)), format!("Bigger boomerangs, damage +{}%, throws {}% rarer", pct(0.12 * l), pct(0.04 * l))),
        (F_BOOM, "rate") => s(format!("Броски на 18% чаще (всего +{}%)", pct(0.18 * l)), format!("Throws 18% more often (total +{}%)", pct(0.18 * l))),
        (F_BOOM, "dmg") => s(format!("Урон бумерангов +25% (всего +{}%) — и туда, и обратно", pct(0.25 * l)), format!("Boomerang damage +25% (total +{}%) — both ways", pct(0.25 * l))),
        (F_BOOM, "salvo") => s(format!("Каждый {}-й бросок — 8 бумерангов во все стороны (70% урона)", 8 - n.min(3) as u32), format!("Every {}th throw — 8 boomerangs in all directions (70% damage)", 8 - n.min(3) as u32)),
        (F_BOOM, "echo") => s(format!("С шансом {}% бросок тут же повторяется (80% урона)", pct(0.12 + 0.1 * l)), format!("{}% chance a throw repeats at once (80% damage)", pct(0.12 + 0.1 * l))),
        (F_SUMMON, "multi") => s(format!("+1 малёк за раз (будет {})", 1 + n), format!("+1 fry at a time (total {})", 1 + n)),
        (F_SUMMON, "caliber") => s(format!("Мальки крупнее и кусают на {}% сильнее, но рождаются на {}% реже", pct(0.12 * l), pct(0.04 * l)), format!("Bigger fry, bite +{}% harder, spawn {}% rarer", pct(0.12 * l), pct(0.04 * l))),
        (F_SUMMON, "rate") => s(format!("Мальки рождаются на 18% чаще (всего +{}%)", pct(0.18 * l)), format!("Fry spawn 18% more often (total +{}%)", pct(0.18 * l))),
        (F_SUMMON, "dmg") => s(format!("Укус мальков +25% (всего +{}%)", pct(0.25 * l)), format!("Fry bite +25% (total +{}%)", pct(0.25 * l))),
        (F_SUMMON, "pierce") => s(format!("Малёк прокусывает врага и плывёт к следующему ({} раз)", n), format!("A fry bites through and swims on to the next foe ({} times)", n)),
        (F_SUMMON, "salvo") => s(format!("Каждый {}-й раз — выводок из 8 мальков во все стороны (70% урона)", 8 - n.min(3) as u32), format!("Every {}th time — a brood of 8 fry in all directions (70% damage)", 8 - n.min(3) as u32)),
        (F_SUMMON, "echo") => s(format!("С шансом {}% рождается ещё столько же мальков (80% урона)", pct(0.12 + 0.1 * l)), format!("{}% chance as many fry spawn again (80% damage)", pct(0.12 + 0.1 * l))),
        (F_MINER, "multi") => s(format!("+1 мина за раз (будет {}), разлетаются веером", 1 + n), format!("+1 mine at a time (total {}), spread in a fan", 1 + n)),
        (F_MINER, "caliber") => s(format!("Радиус взрыва мин +{}%, урон +{}%, но мины ставятся на {}% реже", pct(0.15 * l), pct(0.12 * l), pct(0.04 * l)), format!("Mine blast radius +{}%, damage +{}%, mines {}% rarer", pct(0.15 * l), pct(0.12 * l), pct(0.04 * l))),
        (F_MINER, "rate") => s(format!("Мины ставятся на 18% чаще (всего +{}%)", pct(0.18 * l)), format!("Mines are laid 18% more often (total +{}%)", pct(0.18 * l))),
        (F_MINER, "dmg") => s(format!("Взрыв мин +25% (всего +{}%)", pct(0.25 * l)), format!("Mine blast +25% (total +{}%)", pct(0.25 * l))),
        (F_MINER, "salvo") => s(format!("Каждый {}-й раз — кольцо из 8 мин вокруг тебя (70% урона)", 8 - n.min(3) as u32), format!("Every {}th time — a ring of 8 mines around you (70% damage)", 8 - n.min(3) as u32)),
        (F_MINER, "echo") => s(format!("С шансом {}% мины ставятся дважды (80% урона)", pct(0.12 + 0.1 * l)), format!("{}% chance mines are laid twice (80% damage)", pct(0.12 + 0.1 * l))),
        (F_SCYTHE, "hurricane") => s("«Круговой взмах» выпускает 16 кос сразу".into(), "«Full circle» releases 16 blades at once".into()),
        (F_BOOM, "hurricane") => s("«Звезда бумерангов» — 16 бумерангов сразу".into(), "«Boomerang star» throws 16 at once".into()),
        (F_SUMMON, "hurricane") => s("«Выводок» — 16 мальков сразу, каждый прокусывает 2 врагов".into(), "«Brood» releases 16 fry, each biting through 2 foes".into()),
        (F_MINER, "hurricane") => s("«Минное кольцо» — 16 мин сразу".into(), "«Mine ring» lays 16 mines at once".into()),
        (F_SCYTHE, "choir") => s("Близнец запускает сразу три косы".into(), "The twin launches three blades at once".into()),
        (F_BOOM, "choir") => s("Близнец бросает веер из трёх бумерангов".into(), "The twin throws a fan of three boomerangs".into()),
        (F_SUMMON, "choir") => s("Близнец выпускает сразу трёх мальков".into(), "The twin releases three fry at once".into()),
        (F_MINER, "choir") => s("Близнец ставит сразу три мины".into(), "The twin lays three mines at once".into()),
        _ => None }
}
/// Название карты с учётом искры
pub fn name_f(i: usize, form: u8) -> String { form_name(form, UPG[i].id).map(|s| s.to_string()).unwrap_or_else(|| i18n::upg(UPG[i].id).0) }
/// Текст карты с учётом искры: своё описание, а в рецептах и подсказках эволюции — свои названия
pub fn card_f(i: usize, n: u8, form: u8) -> String {
    let mut d = form_desc(form, UPG[i].id, n).unwrap_or_else(|| desc(UPG[i].id, n));
    if let Some((a, la, b, lb)) = UPG[i].syn { d = format!("{d}\n{}: {} {la} + {} {lb}", if i18n::is_en() { "Combo" } else { "Сочетание" }, name_f(a, form), name_f(b, form)); }
    if let Some(e) = crate::content::EVOS.iter().find(|e| e.upg == i) { let nm = name_f(e.need, form);
        d = format!("{d}\n{}", if i18n::is_en() { format!("Evolution: max level + {nm} {}", e.need_lv) } else { format!("Эволюция: макс. уровень + {nm} {}", e.need_lv) }); }
    d
}
