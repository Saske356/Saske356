//! Сохранение прогресса. Формат JSON совместим с веб-версией (ключ svet_bezdny_save_v1):
//! так прогресс переносится из старого приложения без потерь. Чтение терпимо к повреждениям.
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;

#[derive(Clone, Debug)]
pub struct Quest { pub id: String, pub need: u32, pub r: u32, pub p: u32, pub done: bool, pub got: bool }

#[derive(Clone, Debug, Default)]
pub struct Daily { pub day: String, pub quests: Vec<Quest>, pub streak: u32, pub last: String, pub gift: u32, pub ch_best: u32, pub ch_done: bool }

#[derive(Clone, Debug)]
pub struct Settings { pub sound: bool, pub music: bool, pub vibro: bool, pub quality: String, pub nums: bool, pub shake: bool, pub lang: String,
    pub fps: u32, pub fx: bool, pub hard: bool, pub orient: u8 /* 0 — вертикаль, 1 — горизонталь, 2 — авто */ }

#[derive(Clone, Debug)]
pub struct Save {
    pub pearls: u32, pub best: u64, pub best_depth: u32, pub total_kills: u64, pub total_pearls: u64, pub runs: u32, pub flares: u32,
    pub shop: BTreeMap<String, u8>, pub tal: BTreeMap<String, u8>, pub chars: BTreeMap<String, u8>, pub ch: String,
    pub skins: BTreeMap<String, u8>, pub skin: String, pub ach: BTreeMap<String, u8>, pub seen_how: bool, pub seen_intro: bool,
    pub foe_seen: BTreeMap<String, u8>, pub seen: BTreeMap<String, u8>, pub tut: bool, pub wins: u32, pub daily: Daily,
    pub best_kills: u32, pub best_combo: u32, pub best_level: u32, pub best_syn: u32, pub crab_hint: bool, pub set: Settings,
    pub err_log: Vec<String>, pub migrated: bool,
}

pub fn default_lang() -> String { "ru".into() }

impl Default for Save {
    fn default() -> Self {
        let mut chars = BTreeMap::new(); chars.insert("lumen".into(), 1);
        let mut skins = BTreeMap::new(); skins.insert("azure".into(), 1);
        Save { pearls: 0, best: 0, best_depth: 0, total_kills: 0, total_pearls: 0, runs: 0, flares: 0, shop: BTreeMap::new(), tal: BTreeMap::new(),
            chars, ch: "lumen".into(), skins, skin: "azure".into(), ach: BTreeMap::new(), seen_how: false, seen_intro: false, foe_seen: BTreeMap::new(),
            seen: BTreeMap::new(), tut: false, wins: 0, daily: Daily::default(), best_kills: 0, best_combo: 0, best_level: 0, best_syn: 0, crab_hint: false,
            set: Settings { sound: true, music: true, vibro: true, quality: "auto".into(), nums: true, shake: true, lang: default_lang(), fps: 120, fx: false, hard: false, orient: 0 },
            err_log: vec![], migrated: false }
    }
}

fn num(v: &Value, k: &str) -> Option<f64> { v.get(k).and_then(|x| x.as_f64().or_else(|| x.as_str().and_then(|s| s.parse().ok()))).filter(|x| x.is_finite() && *x >= 0.0) }
fn flag(v: &Value, k: &str, d: bool) -> bool { match v.get(k) { Some(Value::Bool(b)) => *b, Some(Value::Number(n)) => n.as_f64().unwrap_or(1.0) != 0.0, Some(Value::String(s)) => s != "0", _ => d } }
fn s(v: &Value, k: &str) -> Option<String> { v.get(k).and_then(|x| x.as_str()).map(|x| x.to_string()) }
fn map(v: &Value, k: &str) -> BTreeMap<String, u8> {
    let mut m = BTreeMap::new();
    if let Some(Value::Object(o)) = v.get(k) { for (kk, vv) in o { let n = vv.as_f64().unwrap_or(if vv.as_bool() == Some(true) { 1.0 } else { 0.0 }); if n.is_finite() && n > 0.0 { m.insert(kk.clone(), n.min(255.0) as u8); } } }
    m
}
fn mapv(m: &BTreeMap<String, u8>) -> Value { let mut o = Map::new(); for (k, v) in m { o.insert(k.clone(), json!(v)); } Value::Object(o) }

impl Save {
    /// Разбор JSON (своего или из веб-версии). Неверные поля просто остаются по умолчанию.
    pub fn from_json(text: &str) -> Save {
        let mut d = Save::default();
        let Ok(o) = serde_json::from_str::<Value>(text) else { return d };
        if !o.is_object() { return d; }
        macro_rules! n { ($f:ident, $k:literal, $t:ty) => { if let Some(x) = num(&o, $k) { d.$f = x.floor() as $t; } } }
        n!(pearls, "pearls", u32); n!(best, "best", u64); n!(best_depth, "bestDepth", u32); n!(total_kills, "totalKills", u64); n!(total_pearls, "totalPearls", u64);
        n!(runs, "runs", u32); n!(flares, "flares", u32); n!(wins, "wins", u32); n!(best_kills, "bestKills", u32); n!(best_combo, "bestCombo", u32);
        n!(best_level, "bestLevel", u32); n!(best_syn, "bestSyn", u32);
        for (k, dst) in [("shop", &mut d.shop), ("tal", &mut d.tal), ("chars", &mut d.chars), ("skins", &mut d.skins), ("ach", &mut d.ach), ("foeSeen", &mut d.foe_seen), ("seen", &mut d.seen)] {
            let m = map(&o, k); for (kk, vv) in m { dst.insert(kk, vv); } }
        if let Some(x) = s(&o, "char") { d.ch = x; } if let Some(x) = s(&o, "skin") { d.skin = x; }
        d.seen_how = flag(&o, "seenHow", false); d.seen_intro = flag(&o, "seenIntro", false); d.tut = flag(&o, "tut", false); d.crab_hint = flag(&o, "crabHint", false);
        d.migrated = flag(&o, "migrated", false);
        if let Some(da) = o.get("daily") {
            d.daily.day = s(da, "day").unwrap_or_default(); d.daily.last = s(da, "last").unwrap_or_default();
            d.daily.streak = num(da, "streak").unwrap_or(0.) as u32; d.daily.gift = num(da, "gift").unwrap_or(0.) as u32;
            d.daily.ch_best = num(da, "chBest").unwrap_or(0.) as u32; d.daily.ch_done = flag(da, "chDone", false);
            if let Some(Value::Array(q)) = da.get("quests") { for x in q { if let Some(id) = s(x, "id") {
                d.daily.quests.push(Quest { id, need: num(x, "need").unwrap_or(1.) as u32, r: num(x, "r").unwrap_or(0.) as u32, p: num(x, "p").unwrap_or(0.) as u32, done: flag(x, "done", false), got: flag(x, "got", false) }); } } }
        }
        if let Some(st) = o.get("set") {
            let t = &mut d.set;
            t.sound = flag(st, "sound", true); t.music = flag(st, "music", true); t.vibro = flag(st, "vibro", true); t.nums = flag(st, "nums", true); t.shake = flag(st, "shake", true);
            if let Some(q) = s(st, "quality") { if ["auto", "high", "low"].contains(&q.as_str()) { t.quality = q; } }
            if let Some(l) = s(st, "lang") { if l == "ru" || l == "en" { t.lang = l; } }
            t.fps = if num(st, "fps") == Some(60.0) { 60 } else { 120 };
            t.fx = flag(st, "bloom", false); // подсветка — новая тяжёлая настройка, по умолчанию выключена t.hard = flag(st, "hard", false); t.orient = num(st, "orient").unwrap_or(0.).min(2.) as u8;
        }
        if let Some(Value::Array(a)) = o.get("errLog") { d.err_log = a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).take(5).collect(); }
        // проверки, как в веб-версии
        d.chars.insert("lumen".into(), 1); d.skins.insert("azure".into(), 1);
        if !crate::data::CHARS.iter().any(|c| c.id == d.ch) || !d.chars.contains_key(&d.ch) { d.ch = "lumen".into(); }
        if !crate::data::SKINS.iter().any(|c| c.id == d.skin) || !d.skins.contains_key(&d.skin) { d.skin = "azure".into(); }
        for (k, v) in d.shop.iter_mut() { if let Some(it) = crate::data::SHOP.iter().find(|s| s.id == k) { *v = (*v).min(it.max); } }
        d
    }
    pub fn to_json(&self) -> String {
        let q: Vec<Value> = self.daily.quests.iter().map(|q| json!({"id": q.id, "need": q.need, "r": q.r, "p": q.p, "done": q.done as u8, "got": q.got as u8})).collect();
        let t = &self.set;
        json!({
            "pearls": self.pearls, "best": self.best, "bestDepth": self.best_depth, "totalKills": self.total_kills, "totalPearls": self.total_pearls,
            "runs": self.runs, "flares": self.flares, "shop": mapv(&self.shop), "tal": mapv(&self.tal), "chars": mapv(&self.chars), "char": self.ch,
            "skins": mapv(&self.skins), "skin": self.skin, "ach": mapv(&self.ach), "seenHow": self.seen_how as u8, "seenIntro": self.seen_intro as u8,
            "foeSeen": mapv(&self.foe_seen), "seen": mapv(&self.seen), "tut": self.tut as u8, "wins": self.wins, "crabHint": self.crab_hint as u8, "migrated": self.migrated as u8,
            "daily": {"day": self.daily.day, "quests": q, "streak": self.daily.streak, "last": self.daily.last, "gift": self.daily.gift, "chBest": self.daily.ch_best, "chDone": self.daily.ch_done as u8},
            "bestKills": self.best_kills, "bestCombo": self.best_combo, "bestLevel": self.best_level, "bestSyn": self.best_syn,
            "set": {"sound": t.sound as u8, "music": t.music as u8, "vibro": t.vibro as u8, "quality": t.quality, "nums": t.nums as u8, "shake": t.shake as u8, "qv": 1,
                "lang": t.lang, "fps": t.fps, "bloom": t.fx as u8, "hard": t.hard as u8, "orient": t.orient},
            "errLog": self.err_log,
        }).to_string()
    }
    pub fn lv(&self, m: &BTreeMap<String, u8>, k: &str) -> u8 { *m.get(k).unwrap_or(&0) }
    pub fn shop_lv(&self, k: &str) -> u8 { *self.shop.get(k).unwrap_or(&0) }
    pub fn tal(&self, k: &str) -> bool { self.tal.get(k).copied().unwrap_or(0) > 0 }
}
