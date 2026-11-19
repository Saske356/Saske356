//! Константы и таблицы игры (перенесены из веб-версии один к одному).
#![allow(dead_code)]

pub const TAU: f32 = std::f32::consts::TAU;
pub const PI: f32 = std::f32::consts::PI;

pub mod cfg {
    pub const ARENA_R: f32 = 1250.0;
    pub const MAX_ENEMIES: usize = 170;
    pub const CRAB_MAX: usize = 6;
    pub const RAY_MAX: usize = 5;
    pub const SPAWNER_MAX: usize = 3;
    pub const LANTERN_MAX: usize = 4;
    pub const WISP_MAX: usize = 8;
    pub const CRAB_SHIELD: f32 = 0.6;
    pub const CRAB_BLOCK: f32 = 0.65;
    pub const INTER_GAP: f64 = 240.0;
    pub const LV_GAP: f32 = 11.0;
    pub const MAX_EBUL: usize = 520;
    pub const MAX_PBUL: usize = 380;
    pub const MAX_PART_HI: usize = 650;
    pub const MAX_PART_LO: usize = 220;
    pub const MAX_PICK: usize = 300;
    pub const MAX_TEXT: usize = 64;
    pub const MAX_RING: usize = 48;
    pub const MAX_BOLT: usize = 40;
    pub const MAX_MINE: usize = 40;
    pub const ZONE_TIME: f32 = 66.0;
    pub const HEAL_RATE: f32 = 0.03;
    pub const CELL: f32 = 96.0;
    pub const JOY_R: f32 = 58.0;
}

/// Палитра: индекс -> цвет (как в веб-версии, плюс оттенки обликов)
pub const PAL_HEX: [u32; 31] = [
    0x5fffb0, 0xff9a3c, 0xff4fd8, 0xffe14f, 0x7dff4f, 0xa97bff, 0xff4f5f, 0x3ff0ff, 0xffffff, 0xffd54f, 0x8fd8ff, 0xff6a3d, 0xc04fff,
    0xffb340, 0xc77dff, 0x4fff9a, 0xff6f91, 0xeaf2ff, 0xfff0b0,
    0x7657ff, 0x55f4d1, 0xffcf55, 0xa5ff42, 0xff65c8, 0x9b8cff, 0x48d9ff, 0xdce8ff, 0xff7048, 0x2879ff, 0x38e6a1, 0xf5a7ff,
];
pub mod c {
    pub const DRIFT: u8 = 0; pub const DART: u8 = 1; pub const JELLY: u8 = 2; pub const URCH: u8 = 3; pub const EEL: u8 = 4;
    pub const SQUID: u8 = 5; pub const CRAB: u8 = 6; pub const CYAN: u8 = 7; pub const WHITE: u8 = 8; pub const GOLD: u8 = 9;
    pub const ICE: u8 = 10; pub const FIRE: u8 = 11; pub const PURP: u8 = 12; pub const AMBER: u8 = 13; pub const AMETH: u8 = 14;
    pub const EMER: u8 = 15; pub const CORAL: u8 = 16; pub const GHOST: u8 = 17; pub const DAWN: u8 = 18;
}

/// Типы существ
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
#[repr(u8)]
pub enum K { #[default] Drifter, Dart, Jelly, Urchin, Spikelet, Eel, Squid, Crab, Mender, Bomber, Chest, Boss1, Boss2, Boss3, Boss4, Crystal,
    Ray, Lantern, Wisp, Spawner, Fry, KingCrab, Queen }
pub const K_ALL: [K; 23] = [K::Drifter, K::Dart, K::Jelly, K::Urchin, K::Spikelet, K::Eel, K::Squid, K::Crab, K::Mender, K::Bomber, K::Chest,
    K::Boss1, K::Boss2, K::Boss3, K::Boss4, K::Crystal, K::Ray, K::Lantern, K::Wisp, K::Spawner, K::Fry, K::KingCrab, K::Queen];

pub struct EtDef { pub key: &'static str, pub r: f32, pub hp: f32, pub spd: f32, pub dmg: f32, pub xp: f32, pub score: f32, pub col: u8, pub boss: bool, pub guard: bool }
const fn et(key: &'static str, r: f32, hp: f32, spd: f32, dmg: f32, xp: f32, score: f32, col: u8, boss: bool, guard: bool) -> EtDef {
    EtDef { key, r, hp, spd, dmg, xp, score, col, boss, guard } }
pub static ET: [EtDef; 23] = [
    et("drifter", 11., 10., 80., 8., 1., 10., c::DRIFT, false, false),
    et("dart", 12., 14., 70., 14., 2., 20., c::DART, false, false),
    et("jelly", 18., 32., 38., 10., 3., 30., c::JELLY, false, false),
    et("urchin", 17., 42., 52., 12., 3., 30., c::URCH, false, false),
    et("spikelet", 8., 6., 140., 6., 1., 5., c::URCH, false, false),
    et("eel", 13., 55., 118., 12., 5., 50., c::EEL, false, false),
    et("squid", 15., 26., 95., 8., 3., 30., c::SQUID, false, false),
    et("crab", 22., 100., 44., 18., 6., 60., c::CRAB, false, false),
    et("mender", 16., 60., 48., 8., 5., 70., c::EMER, false, false),
    et("bomber", 16., 30., 88., 18., 4., 45., c::CORAL, false, false),
    et("chest", 20., 90., 0., 0., 4., 300., c::GOLD, false, false),
    et("boss1", 56., 3200., 150., 18., 90., 5000., c::CYAN, true, false),
    et("boss2", 64., 9500., 70., 20., 140., 10000., c::PURP, true, false),
    et("boss3", 58., 17000., 60., 24., 200., 20000., c::CRAB, true, false),
    et("boss4", 60., 15000., 135., 26., 260., 26000., c::EEL, true, false),
    et("crystal", 12., 70., 0., 12., 2., 100., c::GOLD, false, false),
    et("ray", 15., 34., 100., 16., 3., 35., c::ICE, false, false),
    et("lantern", 16., 46., 60., 10., 5., 60., c::AMBER, false, false),
    et("wisp", 7., 8., 125., 13., 0., 5., c::AMBER, false, false),
    et("spawner", 21., 85., 30., 12., 6., 70., c::EEL, false, false),
    et("fry", 7., 5., 150., 6., 1., 5., c::EEL, false, false),
    et("kingcrab", 46., 1500., 72., 20., 60., 3000., c::GOLD, true, true),
    et("queen", 50., 4300., 55., 18., 100., 7000., c::ICE, true, true),
];
impl K { pub fn d(self) -> &'static EtDef { &ET[self as usize] } pub fn key(self) -> &'static str { ET[self as usize].key } }

/// Улучшения забега (порядок = индекс в P.up)
pub struct UpgDef { pub id: &'static str, pub max: u8, pub col: u8, pub syn: Option<(usize, u8, usize, u8)> }
macro_rules! upgs { ($( $name:ident = $id:literal, $max:expr, $col:expr $(, syn($a:ident,$la:expr,$b:ident,$lb:expr))? );* $(;)?) => {
    #[allow(non_snake_case)] pub mod u { upgs!(@idx 0usize; $($name)*); }
    pub static UPG: &[UpgDef] = &[ $( UpgDef { id: $id, max: $max, col: $col, syn: upgs!(@syn $( $a,$la,$b,$lb )?) } ),* ];
};
(@idx $n:expr; $first:ident $($rest:ident)*) => { pub const $first: usize = $n; upgs!(@idx $n + 1usize; $($rest)*); };
(@idx $n:expr;) => { pub const COUNT: usize = $n; };
(@syn) => { None };
(@syn $a:ident,$la:expr,$b:ident,$lb:expr) => { Some((u::$a, $la, u::$b, $lb)) };
}
upgs! {
    DMG = "dmg", 6, c::CYAN; RATE = "rate", 6, c::ICE; MULTI = "multi", 4, c::CYAN; PIERCE = "pierce", 4, c::WHITE;
    BOUNCE = "bounce", 3, c::ICE; CRIT = "crit", 5, c::GOLD; CHAIN = "chain", 4, c::ICE; ORBIT = "orbit", 5, c::DRIFT;
    NOVA = "nova", 4, c::JELLY; MINE = "mine", 4, c::PURP; FROST = "frost", 3, c::ICE; HOMING = "homing", 3, c::EMER;
    HP = "hp", 5, c::CORAL; REGEN = "regen", 4, c::EMER; SPEED = "speed", 4, c::CYAN; MAGNET = "magnet", 4, c::ICE;
    ARMOR = "armor", 4, c::AMBER; DASH = "dash", 3, c::CYAN; FLARE = "flare", 3, c::GOLD; BURN = "burn", 4, c::AMBER;
    SIPHON = "siphon", 3, c::CORAL; ECHO = "echo", 3, c::ICE; BARRIER = "barrier", 3, c::WHITE; OVERCHARGE = "overcharge", 3, c::GOLD;
    HARPOON = "harpoon", 3, c::AMBER; BEAM = "beam", 4, c::ICE; AURA = "aura", 4, c::PURP; TWIN = "twin", 3, c::CYAN;
    STATIC = "static", 3, c::GOLD; RAGE = "rage", 3, c::CORAL; INK = "ink", 2, c::PURP; VORTEX = "vortex", 2, c::ICE;
    THORNS = "thorns", 3, c::AMBER; GREED = "greed", 3, c::GOLD;
    SALVO = "salvo", 3, c::CYAN; SEEKER = "seeker", 3, c::FIRE; CALIBER = "caliber", 3, c::WHITE; EXECUTE = "execute", 3, c::CORAL;
    CHILL = "chill", 2, c::ICE; DASHNOVA = "dashnova", 2, c::JELLY; MARK = "mark", 3, c::CRAB; FORTUNE = "fortune", 3, c::GOLD;
    STORM = "storm", 1, c::GOLD, syn(ORBIT, 2, CHAIN, 2); SUPERNOVA = "supernova", 1, c::GOLD, syn(NOVA, 2, CRIT, 2);
    PRISM = "prism", 1, c::GOLD, syn(MULTI, 2, BOUNCE, 1); ABYSSICE = "abyssice", 1, c::GOLD, syn(FROST, 1, MINE, 2);
    HUNTER = "hunter", 1, c::GOLD, syn(HOMING, 1, PIERCE, 2); TIDE = "tide", 1, c::GOLD, syn(DASH, 2, SPEED, 2);
    WILDFIRE = "wildfire", 1, c::GOLD, syn(BURN, 2, NOVA, 1); AEGIS = "aegis", 1, c::GOLD, syn(BARRIER, 1, ARMOR, 2);
    LEECH = "leech", 1, c::GOLD, syn(SIPHON, 1, REGEN, 1); SPEAR = "spear", 1, c::GOLD, syn(HARPOON, 2, PIERCE, 2);
    LIGHTHOUSE = "lighthouse", 1, c::GOLD, syn(BEAM, 2, FROST, 1); MAELSTROM = "maelstrom", 1, c::GOLD, syn(AURA, 2, VORTEX, 1);
    CHOIR = "choir", 1, c::GOLD, syn(TWIN, 2, MULTI, 2); TEMPEST = "tempest", 1, c::GOLD, syn(STATIC, 2, CHAIN, 1);
    KRAKEN = "kraken", 1, c::GOLD, syn(INK, 1, THORNS, 2);
    HURRICANE = "hurricane", 1, c::GOLD, syn(SALVO, 2, MULTI, 2); BOMBARD = "bombard", 1, c::GOLD, syn(SEEKER, 2, NOVA, 1);
    REAPER = "reaper", 1, c::GOLD, syn(EXECUTE, 2, CRIT, 2); BLIZZARD = "blizzard", 1, c::GOLD, syn(CHILL, 1, FROST, 2);
}
/// Особая карта «Чистый свет», когда улучшения кончились
pub const U_HEAL: usize = usize::MAX;

pub struct CharDef { pub id: &'static str, pub cost: u32, pub hp: f32, pub speed: f32, pub rate: f32, pub dmg: f32, pub pierce: u8, pub orb: u8, pub armor: f32, pub dash_cd: f32, pub col: u8 }
pub static CHARS: [CharDef; 7] = [
    CharDef { id: "lumen", cost: 0, hp: 100., speed: 1., rate: 1., dmg: 1., pierce: 0, orb: 0, armor: 0., dash_cd: 1., col: c::CYAN },
    CharDef { id: "needle", cost: 250, hp: 70., speed: 1.15, rate: 1.2, dmg: 1., pierce: 1, orb: 0, armor: 0., dash_cd: 0.65, col: c::EMER },
    CharDef { id: "shell", cost: 400, hp: 160., speed: 0.88, rate: 0.9, dmg: 1.1, pierce: 0, orb: 2, armor: 2., dash_cd: 1.2, col: c::AMBER },
    CharDef { id: "squall", cost: 500, hp: 60., speed: 1.08, rate: 1., dmg: 1.3, pierce: 1, orb: 0, armor: 0., dash_cd: 0.8, col: c::FIRE },
    CharDef { id: "warden", cost: 800, hp: 230., speed: 0.82, rate: 0.85, dmg: 1., pierce: 0, orb: 1, armor: 4., dash_cd: 1.3, col: c::CORAL },
    CharDef { id: "storm", cost: 950, hp: 80., speed: 1.1, rate: 1.5, dmg: 0.78, pierce: 0, orb: 0, armor: 0., dash_cd: 0.9, col: c::ICE },
    CharDef { id: "phantom", cost: 1200, hp: 85., speed: 1.25, rate: 1., dmg: 1.15, pierce: 2, orb: 0, armor: 0., dash_cd: 0.45, col: c::GHOST },
];

pub struct SkinDef { pub id: &'static str, pub pal: u8, pub cost: u32, pub win: bool }
pub static SKINS: [SkinDef; 21] = [
    SkinDef { id: "azure", pal: c::CYAN, cost: 0, win: false }, SkinDef { id: "amber", pal: c::AMBER, cost: 80, win: false },
    SkinDef { id: "amethyst", pal: c::AMETH, cost: 120, win: false }, SkinDef { id: "emerald", pal: c::EMER, cost: 160, win: false },
    SkinDef { id: "coral", pal: c::CORAL, cost: 200, win: false }, SkinDef { id: "ghost", pal: c::GHOST, cost: 350, win: false },
    SkinDef { id: "ember", pal: c::FIRE, cost: 260, win: false }, SkinDef { id: "frost", pal: c::ICE, cost: 300, win: false },
    SkinDef { id: "dawn", pal: c::DAWN, cost: 0, win: true },
    SkinDef { id: "void", pal: 19, cost: 420, win: false }, SkinDef { id: "aurora", pal: 20, cost: 460, win: false },
    SkinDef { id: "solar", pal: 21, cost: 500, win: false }, SkinDef { id: "venom", pal: 22, cost: 540, win: false },
    SkinDef { id: "royal", pal: 23, cost: 580, win: false }, SkinDef { id: "nebula", pal: 24, cost: 620, win: false },
    SkinDef { id: "cyber", pal: 25, cost: 660, win: false }, SkinDef { id: "lunar", pal: 26, cost: 700, win: false },
    SkinDef { id: "inferno", pal: 27, cost: 740, win: false }, SkinDef { id: "abyss", pal: 28, cost: 780, win: false },
    SkinDef { id: "jade", pal: 29, cost: 820, win: false }, SkinDef { id: "prism", pal: 30, cost: 900, win: false },
];

pub struct ShopDef { pub id: &'static str, pub max: u8, pub base: f32 }
pub static SHOP: [ShopDef; 8] = [
    ShopDef { id: "hp", max: 5, base: 30. }, ShopDef { id: "dmg", max: 5, base: 40. }, ShopDef { id: "spd", max: 4, base: 30. },
    ShopDef { id: "mag", max: 4, base: 25. }, ShopDef { id: "xp", max: 4, base: 35. }, ShopDef { id: "reroll", max: 3, base: 70. },
    ShopDef { id: "flare", max: 1, base: 150. }, ShopDef { id: "revive", max: 1, base: 400. },
];
pub fn shop_cost(i: usize, lvl: u8) -> u32 { (SHOP[i].base * ((lvl as f32 + 1.0).powf(1.55))).round() as u32 }

pub struct TalDef { pub id: &'static str, pub br: u8, pub cost: u32 }
pub static TALENTS: [TalDef; 12] = [
    TalDef { id: "t_dmg", br: 0, cost: 150 }, TalDef { id: "t_rate", br: 0, cost: 350 }, TalDef { id: "t_crit", br: 0, cost: 700 }, TalDef { id: "t_first", br: 0, cost: 1300 },
    TalDef { id: "t_hp", br: 1, cost: 150 }, TalDef { id: "t_arm", br: 1, cost: 350 }, TalDef { id: "t_regen", br: 1, cost: 700 }, TalDef { id: "t_ward", br: 1, cost: 1300 },
    TalDef { id: "t_pearl", br: 2, cost: 150 }, TalDef { id: "t_xp", br: 2, cost: 350 }, TalDef { id: "t_mag", br: 2, cost: 700 }, TalDef { id: "t_four", br: 2, cost: 1300 },
];
pub static MUTS: [&str; 8] = ["swift", "glass", "swarm", "elite", "hail", "dim", "giant", "rush"];

pub const ZONE_COLS: [u32; 15] = [0x031b38, 0x06264b, 0x032d45, 0x071a42, 0x160f3d, 0x25103e, 0x101b50, 0x062c50, 0x190b3d, 0x280b42, 0x0c1748, 0x080d2e, 0x052f35, 0x25103a, 0x070821];
pub const ZONE_ACCENTS: [u32; 15] = [0x42eaff, 0xff55df, 0x42ffe0, 0x4c9dff, 0xb36cff, 0xffb45e, 0x777bff, 0x42dfff, 0xff4fae, 0xe95cff, 0x8a9dff, 0x6aaeff, 0x48ffbd, 0xff6f9e, 0xd77aff];

/// Декор: темы зон и роли объектов
pub static DECOR_THEMES: [&[&str]; 15] = [
    &["d_kelp", "d_kelp", "d_rock", "d_shell"], &["d_anemone", "d_coral", "d_kelp", "d_shell"], &["d_coral", "d_coral2", "d_coral2", "d_shell", "d_rock"],
    &["d_rock", "d_rock", "d_vent", "d_kelp"], &["d_pillar", "d_pillar", "d_rock", "d_shroom"], &["d_ribs", "d_skull", "d_rock", "d_ribs"],
    &["d_shroom", "d_shroom", "d_anemone", "d_pillar"], &["d_ice", "d_ice", "d_vent", "d_rock"], &["d_rock", "d_vent", "d_skull", "d_vent"],
    &["d_coral", "d_anemone", "d_pillar", "d_coral2"], &["d_pillar", "d_ice", "d_pillar", "d_rock"], &["d_skull", "d_ribs", "d_shroom", "d_rock"],
    &["d_kelp", "d_shroom", "d_rock", "d_kelp"], &["d_vent", "d_coral2", "d_rock", "d_vent"], &["d_pillar", "d_ice", "d_skull", "d_vent"],
];
pub fn decor_role(k: &str) -> u8 { match k { "d_rock" | "d_pillar" | "d_skull" | "d_ribs" | "d_coral" | "d_ice" | "d_vent" => 2, "d_shell" => 0, _ => 1 } }
pub fn decor_sway(k: &str) -> f32 { match k { "d_kelp" => 0.22, "d_anemone" => 0.16, "d_shroom" => 0.06, "d_coral" => 0.04, "d_coral2" => 0.08, _ => 0.0 } }
