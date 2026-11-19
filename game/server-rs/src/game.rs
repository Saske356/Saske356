//! Состояние мира и игровая логика: игроки, транспорт, работы, чат, экономика.
//! Протокол сообщений совпадает с прежним сервером на Node.js.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fmt::Write as _;
use std::time::Instant;

use axum::extract::ws::Utf8Bytes;
use rand::Rng;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use tokio::sync::mpsc;

use novo_world::{self as world, Places};

pub type Tx = mpsc::Sender<Utf8Bytes>;

/// Номера игроков и машин — небольшие целые; стандартный SipHash для них избыточен.
#[derive(Default)]
pub struct IdHasher(u64);
impl std::hash::Hasher for IdHasher {
    fn finish(&self) -> u64 {
        self.0
    }
    fn write(&mut self, bytes: &[u8]) {
        for b in bytes {
            self.0 = (self.0 << 8 | *b as u64).wrapping_mul(0x9e37_79b9_7f4a_7c15);
        }
    }
    fn write_i64(&mut self, v: i64) {
        self.0 = (v as u64).wrapping_mul(0x9e37_79b9_7f4a_7c15);
    }
}
pub type IdSet = HashSet<i64, std::hash::BuildHasherDefault<IdHasher>>;

/// Радиус, в котором игрок получает других игроков и транспорт в снимках мира.
/// Миникарта показывает ~130 м, ники видны с 35 м — 150 м хватает с запасом.
const VIEW_RADIUS: f64 = 150.0;

// ---------- профиль (players.json) ----------
#[derive(Serialize, Deserialize, Clone)]
pub struct CarRec {
    pub model: String,
    pub color: i64,
}

#[derive(Serialize, Deserialize, Clone, Default)]
pub struct Stats {
    #[serde(default)]
    pub deliveries: i64,
    #[serde(default)]
    pub stops: i64,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct Profile {
    pub name: String,
    pub salt: String,
    pub hash: String,
    #[serde(default)]
    pub money: i64,
    #[serde(default = "one")]
    pub level: i64,
    #[serde(default)]
    pub exp: i64,
    #[serde(default)]
    pub license: bool,
    #[serde(default)]
    pub cars: Vec<CarRec>,
    #[serde(default)]
    pub pos: Option<[f64; 2]>,
    #[serde(default)]
    pub created: i64,
    #[serde(default)]
    pub stats: Stats,
    /// Уровень админки 0–5 (5 — владелец).
    #[serde(default)]
    pub admin: i64,
    /// Поля, о которых этот сервер не знает, сохраняются как есть.
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}
fn one() -> i64 {
    1
}

// ---------- игроки, транспорт, работы ----------
#[derive(Clone, Copy, PartialEq)]
pub enum Kind {
    Own,
    Rent,
    Job,
    Admin,
}

pub struct Vehicle {
    pub id: i64,
    pub model: &'static str,
    pub color: i64,
    pub x: f64,
    pub z: f64,
    pub ry: f64,
    pub spd: f64,
    pub driver: i64,
    pub owner: i64,
    pub kind: Kind,
    pub plate: String,
    /// Модель из кэша (cache/cars), если машина создана админом не из стандартных классов.
    pub skin: Option<String>,
}

#[derive(Clone, Copy, PartialEq)]
pub enum JobType {
    Courier,
    Bus,
}

pub struct Job {
    pub kind: JobType,
    pub target: [f64; 2],
    pub label: String,
    pub info: String,
    pub packages: i64,
    pub from: [f64; 2],
    pub vid: i64,
    pub idx: usize,
}

pub struct Player {
    pub id: i64,
    pub key: String,
    pub name: String,
    pub tx: Tx,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub ry: f64,
    pub anim: i64,
    pub veh: i64,
    pub job: Option<Job>,
    pub online: u64,
    pub chat_t: u64,
    pub cp_t: u64,
    pub spawn_t: u64,
    pub fly: bool,
    /// Кого этот игрок уже «знает»: ник и неизменные данные машин шлём только один раз.
    pub known_p: IdSet,
    pub known_v: IdSet,
}

pub struct Config {
    pub name: String,
    pub color: String,
    pub max_players: usize,
    pub version: String,
    /// Ники (в нижнем регистре), которые при входе получают админку 5 уровня.
    pub admins: Vec<String>,
    /// Офлайн-сервер внутри клиента: любой вошедший — владелец.
    pub owner_all: bool,
}

pub struct Game {
    pub players: BTreeMap<i64, Player>,
    pub vehicles: BTreeMap<i64, Vehicle>,
    pub db: HashMap<String, Profile>,
    pub dirty: bool,
    pub cfg: Config,
    next_vid: i64,
    deliveries: Vec<[f64; 2]>,
    route: Vec<[f64; 2]>,
    places: Places,
    start: Instant,
    time_offset: f64,
}

// ---------- мелочи ----------
fn r2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}
fn dist(ax: f64, az: f64, bx: f64, bz: f64) -> f64 {
    (ax - bx).hypot(az - bz)
}
fn now_ms(start: Instant) -> u64 {
    start.elapsed().as_millis() as u64 + 1_000_000 // +запас, чтобы первые «кулдауны» не срабатывали
}
/// Деньги как у toLocaleString('ru-RU'): $12 345 (неразрывный пробел).
pub fn money(n: i64) -> String {
    let s = n.abs().to_string();
    let mut out = String::new();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push('\u{a0}');
        }
        out.push(ch);
    }
    format!("{}${}", if n < 0 { "-" } else { "" }, out)
}
fn num(v: &Value, key: &str) -> Option<f64> {
    v.get(key).and_then(|x| x.as_f64()).filter(|x| x.is_finite())
}
/// Аналог `x | 0` из JS для чисел.
fn int(v: &Value, key: &str) -> i64 {
    num(v, key).map(|x| x.trunc() as i64).unwrap_or(0)
}
fn plate() -> String {
    const L: [char; 12] = ['А', 'В', 'Е', 'К', 'М', 'Н', 'О', 'Р', 'С', 'Т', 'У', 'Х'];
    let mut r = rand::thread_rng();
    let mut s = String::new();
    s.push(L[r.gen_range(0..12)]);
    let _ = write!(s, "{}", r.gen_range(100..1000));
    s.push(L[r.gen_range(0..12)]);
    s.push(L[r.gen_range(0..12)]);
    s
}

fn send_raw(p: &Player, s: Utf8Bytes) {
    // медленному клиенту лишние сообщения не копим — отбрасываем
    let _ = p.tx.try_send(s);
}
fn send(p: &Player, v: Value) {
    send_raw(p, Utf8Bytes::from(v.to_string()));
}
fn notify(p: &Player, text: &str, kind: &str) {
    send(p, json!({ "t": "notify", "text": text, "kind": kind }));
}

const HELP: [&str; 6] = [
    "Текст без команды — сказать вслух (20 м)",
    "/s текст — крикнуть, /w текст — шёпотом",
    "/me действие, /do описание, /try действие (удачно/неудачно)",
    "/b текст — локальный OOC, /o текст — общий OOC",
    "/pay [id] [сумма] — передать деньги, /id [ник] — найти игрока",
    "/time — время, /help — эта справка",
];

impl Game {
    pub fn new(cfg: Config, db: HashMap<String, Profile>) -> Self {
        Game {
            players: BTreeMap::new(),
            vehicles: BTreeMap::new(),
            db,
            dirty: false,
            cfg,
            next_vid: 1,
            deliveries: world::deliveries(),
            route: world::bus_route(),
            places: world::places(),
            start: Instant::now(),
            time_offset: 0.0,
        }
    }

    pub fn game_time(&self) -> f64 {
        ((9.0 * 60.0 + self.start.elapsed().as_millis() as f64 / 2000.0 + self.time_offset) % 1440.0 + 1440.0) % 1440.0
    }

    fn now(&self) -> u64 {
        now_ms(self.start)
    }

    fn pub_profile(prof: &Profile) -> Value {
        json!({ "money": prof.money, "level": prof.level, "exp": prof.exp, "license": prof.license,
                "cars": prof.cars, "stats": prof.stats, "admin": prof.admin })
    }

    fn send_profile(&mut self, pid: i64) {
        if let Some(p) = self.players.get(&pid) {
            if let Some(prof) = self.db.get(&p.key) {
                send(p, json!({ "t": "profile", "profile": Self::pub_profile(prof) }));
            }
        }
        self.dirty = true;
    }

    fn send_job(&self, pid: i64) {
        let Some(p) = self.players.get(&pid) else { return };
        let job = p.job.as_ref().map(|j| {
            json!({ "type": if j.kind == JobType::Bus { "bus" } else { "courier" },
                    "target": j.target, "label": j.label, "info": j.info })
        });
        send(p, json!({ "t": "job", "job": job }));
    }

    fn add_money(&mut self, pid: i64, n: i64) {
        if let Some(prof) = self.players.get(&pid).and_then(|p| self.db.get_mut(&p.key)) {
            prof.money = (prof.money + n).max(0);
        }
    }

    fn prof(&self, pid: i64) -> Option<&Profile> {
        self.players.get(&pid).and_then(|p| self.db.get(&p.key))
    }
    fn prof_mut(&mut self, pid: i64) -> Option<&mut Profile> {
        let key = self.players.get(&pid)?.key.clone();
        self.db.get_mut(&key)
    }

    fn spawn_vehicle(&mut self, model: &'static str, color: i64, pos: [f64; 3], owner: i64, kind: Kind) -> i64 {
        self.spawn_vehicle_skin(model, color, pos, owner, kind, None)
    }
    fn spawn_vehicle_skin(&mut self, model: &'static str, color: i64, pos: [f64; 3], owner: i64, kind: Kind, skin: Option<String>) -> i64 {
        let id = self.next_vid;
        self.next_vid += 1;
        self.vehicles.insert(id, Vehicle {
            id, model, color, x: pos[0], z: pos[1], ry: pos[2], spd: 0.0, driver: -1, owner, kind, plate: plate(), skin,
        });
        id
    }

    fn remove_vehicle(&mut self, vid: i64) {
        let Some(v) = self.vehicles.remove(&vid) else { return };
        if v.driver >= 0 {
            if let Some(d) = self.players.get_mut(&v.driver) {
                d.veh = -1;
                send(d, json!({ "t": "exited", "x": v.x, "z": v.z }));
            }
        }
    }

    fn remove_vehicles_of(&mut self, pid: i64, kind: Option<Kind>) {
        let ids: Vec<i64> = self.vehicles.values()
            .filter(|v| v.owner == pid && kind.map_or(true, |k| v.kind == k))
            .map(|v| v.id).collect();
        for id in ids {
            self.remove_vehicle(id);
        }
    }

    pub fn broadcast(&self, v: Value, except: Option<i64>) {
        let s = Utf8Bytes::from(v.to_string());
        for p in self.players.values() {
            if Some(p.id) != except {
                send_raw(p, s.clone());
            }
        }
    }

    fn local(&self, pid: i64, radius: f64, text: String, color: &str, bubble: Option<String>) {
        let Some(p) = self.players.get(&pid) else { return };
        let mut v = json!({ "t": "chat", "text": text, "color": color });
        if let Some(b) = bubble {
            v["from"] = json!(pid);
            v["bubble"] = json!(b);
        }
        let s = Utf8Bytes::from(v.to_string());
        for q in self.players.values() {
            if dist(p.x, p.z, q.x, q.z) <= radius {
                send_raw(q, s.clone());
            }
        }
    }

    // ---------- вход и выход ----------
    pub fn can_join(&self, key: &str) -> Result<(), &'static str> {
        if self.players.len() >= self.cfg.max_players {
            return Err("Сервер переполнен, попробуйте позже");
        }
        if self.players.values().any(|p| p.key == key) {
            return Err("Этот персонаж уже в игре");
        }
        Ok(())
    }

    pub fn join(&mut self, key: String, tx: Tx, is_new: bool) -> i64 {
        let mut id = 0;
        while self.players.contains_key(&id) {
            id += 1;
        }
        let own = self.cfg.owner_all || self.cfg.admins.iter().any(|a| a == &key);
        if own {
            if let Some(pr) = self.db.get_mut(&key) {
                pr.admin = 5;
            }
        }
        let prof = &self.db[&key];
        let pos = prof.pos.unwrap_or(self.places.spawn.pos);
        let p = Player {
            id, key: key.clone(), name: prof.name.clone(), tx, x: pos[0], y: world::ground_height(pos[0], pos[1]), z: pos[1],
            ry: std::f64::consts::PI, anim: 0, veh: -1, job: None, online: 0, chat_t: 0, cp_t: 0, spawn_t: 0, fly: false,
            known_p: IdSet::default(), known_v: IdSet::default(),
        };
        send(&p, json!({ "t": "welcome", "id": id, "name": p.name, "x": p.x, "z": p.z, "ry": p.ry, "isNew": is_new,
                         "profile": Self::pub_profile(prof), "time": self.game_time() }));
        println!("+ {} [{}] ({} онлайн)", p.name, id, self.players.len() + 1);
        let text = format!("{} [{}] зашёл в Новоград", p.name, id);
        // номер мог принадлежать вышедшему игроку — пусть все получат новый ник
        for q in self.players.values_mut() {
            q.known_p.remove(&id);
        }
        self.players.insert(id, p);
        self.broadcast(json!({ "t": "chat", "text": text, "color": "#8f9aa6" }), Some(id));
        id
    }

    pub fn leave(&mut self, pid: i64) {
        let Some((x, z, key, name)) = self.players.get(&pid).map(|p| (p.x, p.z, p.key.clone(), p.name.clone())) else { return };
        if let Some(prof) = self.db.get_mut(&key) {
            prof.pos = Some([r2(x), r2(z)]);
        }
        self.remove_vehicles_of(pid, None);
        self.players.remove(&pid);
        self.dirty = true;
        self.broadcast(json!({ "t": "chat", "text": format!("{} [{}] покинул сервер", name, pid), "color": "#8f9aa6" }), None);
        println!("- {} [{}] ({} онлайн)", name, pid, self.players.len());
    }

    /// Перед сохранением на диск запоминаем позиции всех, кто в игре.
    pub fn store_positions(&mut self) {
        for p in self.players.values() {
            if let Some(prof) = self.db.get_mut(&p.key) {
                prof.pos = Some([r2(p.x), r2(p.z)]);
            }
        }
    }

    // ---------- входящие сообщения ----------
    pub fn handle(&mut self, pid: i64, t: &str, m: &Value) {
        match t {
            "state" => self.on_state(pid, m),
            "chat" => {
                let text = m.get("text").map(|v| match v {
                    Value::String(s) => s.clone(),
                    Value::Null => String::new(),
                    other => other.to_string(),
                }).unwrap_or_default();
                self.on_chat(pid, &text)
            }
            "act" => self.on_act(pid, m),
            "cp" => self.on_checkpoint(pid),
            "enter" => self.on_enter(pid, m),
            "exit" => self.on_exit(pid),
            _ => {}
        }
    }

    fn on_state(&mut self, pid: i64, m: &Value) {
        let Some(p) = self.players.get_mut(&pid) else { return };
        p.x = num(m, "x").unwrap_or(p.x).clamp(0.0, world::SIZE);
        p.z = num(m, "z").unwrap_or(p.z).clamp(0.0, world::SIZE);
        p.y = num(m, "y").unwrap_or(p.y);
        p.ry = num(m, "ry").unwrap_or(p.ry);
        p.anim = int(m, "anim") & 3;
        let (x, z, veh) = (p.x, p.z, p.veh);
        if veh >= 0 {
            if let Some(v) = self.vehicles.get_mut(&veh) {
                if v.driver == pid {
                    v.x = x;
                    v.z = z;
                    v.ry = num(m, "vry").unwrap_or(v.ry);
                    v.spd = num(m, "spd").unwrap_or(0.0);
                }
            }
        }
    }

    fn on_chat(&mut self, pid: i64, raw: &str) {
        let text: String = raw.chars().filter(|c| !c.is_control()).collect::<String>().trim().chars().take(140).collect();
        if text.is_empty() {
            return;
        }
        let now = self.now();
        let Some(p) = self.players.get_mut(&pid) else { return };
        if now - p.chat_t < 700 {
            return notify(p, "Не так быстро", "warn");
        }
        p.chat_t = now;
        let (name, x, z) = (p.name.clone(), p.x, p.z);
        if !text.starts_with('/') {
            return self.local(pid, 20.0, format!("{} говорит: {}", name, text), "#ffffff", Some(text.clone()));
        }
        let body = &text[1..];
        let mut parts = body.split(' ');
        let cmd = parts.next().unwrap_or("").to_lowercase();
        let rest: Vec<&str> = parts.collect();
        let arg = rest.join(" ").trim().to_string();
        let p = &self.players[&pid];
        if matches!(cmd.as_str(), "me" | "do" | "try" | "s" | "w" | "b" | "o") && arg.is_empty() {
            return notify(p, &format!("Использование: /{} [текст]", cmd), "warn");
        }
        match cmd.as_str() {
            "me" => self.local(pid, 25.0, format!("{} {}", name, arg), "#c2a2da", None),
            "do" => self.local(pid, 25.0, format!("{} (( {} ))", arg, name), "#c2a2da", None),
            "try" => {
                let ok = rand::random::<bool>();
                self.local(pid, 25.0, format!("{} {} | {}", name, arg, if ok { "Удачно" } else { "Неудачно" }),
                    if ok { "#8bd48b" } else { "#e57373" }, None)
            }
            "s" => self.local(pid, 50.0, format!("{} кричит: {}!", name, arg), "#ffffff", Some(format!("{}!", arg))),
            "w" => self.local(pid, 4.0, format!("{} шепчет: {}", name, arg), "#9e9e9e", None),
            "b" => self.local(pid, 25.0, format!("(( {} [{}]: {} ))", name, pid, arg), "#b0bec5", None),
            "o" => self.broadcast(json!({ "t": "chat", "text": format!("(( OOC {} [{}]: {} ))", name, pid, arg), "color": "#80cbc4" }), None),
            "time" => notify(p, &format!("Время в Новограде: {}", world::format_time(self.game_time())), "info"),
            "help" => {
                for h in HELP {
                    send(p, json!({ "t": "chat", "text": h, "color": "#ffd54f" }));
                }
            }
            "id" => {
                let q = arg.to_lowercase();
                let found: Vec<String> = self.players.values().filter(|o| o.key.contains(&q)).take(8)
                    .map(|o| format!("{} [{}]", o.name, o.id)).collect();
                let text = if found.is_empty() { "Никого не найдено".to_string() } else { found.join(", ") };
                send(p, json!({ "t": "chat", "text": text, "color": "#ffd54f" }));
            }
            "pay" => {
                let target = rest.first().and_then(|s| s.parse::<i64>().ok()).filter(|id| *id != pid);
                let sum = rest.get(1).and_then(|s| s.parse::<f64>().ok()).map(|s| s.floor()).unwrap_or(0.0);
                let Some(q) = target.and_then(|id| self.players.get(&id)) else {
                    return notify(p, "Использование: /pay [id] [сумма]", "warn");
                };
                if !(sum > 0.0) || sum > 100000.0 {
                    return notify(p, "Сумма от $1 до $100 000", "warn");
                }
                let sum = sum as i64;
                if sum > self.prof(pid).map_or(0, |pr| pr.money) {
                    return notify(p, "Недостаточно денег", "warn");
                }
                if dist(x, z, q.x, q.z) > 6.0 {
                    return notify(p, "Игрок слишком далеко", "warn");
                }
                let (qid, qname) = (q.id, q.name.clone());
                self.add_money(pid, -sum);
                self.add_money(qid, sum);
                self.send_profile(pid);
                self.send_profile(qid);
                self.local(pid, 25.0, format!("{} передал {} — {}", name, money(sum), qname), "#c2a2da", None);
            }
            _ => {
                if !self.admin_command(pid, &cmd, &rest, &arg) {
                    notify(&self.players[&pid], "Неизвестная команда. /help — список команд", "warn");
                }
            }
        }
    }

    fn near(&self, pid: i64, pos: [f64; 2], r: f64) -> bool {
        let p = &self.players[&pid];
        dist(p.x, p.z, pos[0], pos[1]) <= r + if p.veh >= 0 { 4.0 } else { 0.0 }
    }

    fn pick_delivery(&self, fx: f64, fz: f64) -> [f64; 2] {
        let mut rng = rand::thread_rng();
        let mut best = self.deliveries[0];
        for _ in 0..30 {
            let d = self.deliveries[rng.gen_range(0..self.deliveries.len())];
            best = d;
            let k = dist(fx, fz, d[0], d[1]);
            if k > 70.0 && k < 380.0 {
                break;
            }
        }
        best
    }

    fn courier_next(&mut self, pid: i64) {
        let (x, z) = { let p = &self.players[&pid]; (p.x, p.z) };
        let target = self.pick_delivery(x, z);
        let depot = self.places.courier.pos;
        let Some(j) = self.players.get_mut(&pid).and_then(|p| p.job.as_mut()) else { return };
        if j.packages > 0 {
            j.target = target;
            j.label = "Доставьте посылку".into();
            j.info = format!("Посылок в сумке: {}", j.packages);
        } else {
            j.target = depot;
            j.label = "Вернитесь на склад".into();
            j.info = "Посылки закончились — загрузите новые".into();
        }
    }

    fn bus_next(&mut self, pid: i64) {
        let n = self.route.len();
        let route = &self.route;
        let Some(j) = self.players.get_mut(&pid).and_then(|p| p.job.as_mut()) else { return };
        j.target = route[j.idx];
        j.label = format!("Остановка {} из {}", j.idx + 1, n);
        j.info = "Довезите пассажиров по маршруту".into();
    }

    fn on_act(&mut self, pid: i64, m: &Value) {
        let a = m.get("a").and_then(|v| v.as_str()).unwrap_or("");
        let err = |g: &Game, t: &str| notify(&g.players[&pid], t, "warn");
        let ok = |g: &Game, t: &str| notify(&g.players[&pid], t, "ok");
        let Some(prof) = self.prof(pid) else { return };
        let (money_now, license, ncars) = (prof.money, prof.license, prof.cars.len());
        let pl = self.places;
        match a {
            "license" => {
                if !self.near(pid, pl.school.pos, 5.0) { return err(self, "Подойдите к автошколе"); }
                if license { return err(self, "У вас уже есть права"); }
                if money_now < world::PRICE_LICENSE { return err(self, "Недостаточно денег"); }
                self.add_money(pid, -world::PRICE_LICENSE);
                if let Some(pr) = self.prof_mut(pid) { pr.license = true; }
                ok(self, "Поздравляем! Вы получили водительские права категории B");
                self.send_profile(pid);
            }
            "rent" => {
                if !self.near(pid, pl.rent.pos, 5.0) { return err(self, "Подойдите к пункту аренды"); }
                if !license { return err(self, "Нужны водительские права — их выдают в автошколе"); }
                if money_now < world::PRICE_RENT { return err(self, "Недостаточно денег"); }
                let spawn = pl.rent.car_spawn;
                self.add_money(pid, -world::PRICE_RENT);
                self.remove_vehicles_of(pid, Some(Kind::Rent));
                let color = world::CAR_COLORS[rand::thread_rng().gen_range(0..6)];
                self.spawn_vehicle("kroha", color, spawn, pid, Kind::Rent);
                ok(self, "Транспорт арендован. Подойдите к нему и нажмите F");
                self.send_profile(pid);
            }
            "buy" => {
                let model = m.get("model").and_then(|v| v.as_str()).unwrap_or("");
                let ci = int(m, "color");
                if !self.near(pid, pl.dealer.pos, 5.0) { return err(self, "Подойдите к автосалону"); }
                let car = world::car(model).filter(|c| !c.job);
                let (Some(car), true) = (car, (0..8).contains(&ci)) else { return err(self, "Такой модели нет") };
                if !license { return err(self, "Без прав машину не продадут — сначала в автошколу"); }
                if ncars >= 5 { return err(self, "В гараже максимум 5 машин"); }
                if money_now < car.price { return err(self, "Недостаточно денег"); }
                let color = world::CAR_COLORS[ci as usize];
                let spawn = pl.dealer.car_spawn;
                self.add_money(pid, -car.price);
                if let Some(pr) = self.prof_mut(pid) { pr.cars.push(CarRec { model: car.id.into(), color }); }
                self.remove_vehicles_of(pid, Some(Kind::Own));
                self.spawn_vehicle(car.id, color, spawn, pid, Kind::Own);
                ok(self, &format!("Вы купили «{}» за {}! Машина ждёт у салона", car.name, money(car.price)));
                self.send_profile(pid);
            }
            "spawncar" => {
                let idx = int(m, "idx");
                let Some(rec) = self.prof(pid).and_then(|pr| usize::try_from(idx).ok().and_then(|i| pr.cars.get(i))).cloned() else {
                    return err(self, "Нет такой машины");
                };
                let Some(car) = world::car(&rec.model) else { return err(self, "Нет такой машины") };
                let now = self.now();
                let p = self.players.get_mut(&pid).unwrap();
                if now - p.spawn_t < 8000 { return err(self, "Подождите немного"); }
                p.spawn_t = now;
                let lane = world::nearest_lane(p.x, p.z);
                self.remove_vehicles_of(pid, Some(Kind::Own));
                self.spawn_vehicle(car.id, rec.color, [lane.x, lane.z, lane.ry], pid, Kind::Own);
                ok(self, &format!("«{}» доставлен на ближайшую дорогу", car.name));
            }
            "despawn" => {
                self.remove_vehicles_of(pid, Some(Kind::Own));
                self.remove_vehicles_of(pid, Some(Kind::Rent));
                notify(&self.players[&pid], "Ваш транспорт убран", "info");
            }
            "job" => {
                if self.players[&pid].job.is_some() { return err(self, "Сначала завершите текущую работу"); }
                match m.get("job").and_then(|v| v.as_str()) {
                    Some("courier") => {
                        if !self.near(pid, pl.courier.pos, 5.0) { return err(self, "Подойдите к складу"); }
                        let from = pl.courier.pos;
                        self.players.get_mut(&pid).unwrap().job = Some(Job {
                            kind: JobType::Courier, target: [0.0; 2], label: String::new(), info: String::new(),
                            packages: 5, from, vid: -1, idx: 0,
                        });
                        self.courier_next(pid);
                        ok(self, "Вы курьер! В сумке 5 посылок — адрес отмечен на карте");
                    }
                    Some("bus") => {
                        if !self.near(pid, pl.bus.pos, 5.0) { return err(self, "Подойдите к автопарку"); }
                        if !license { return err(self, "Нужны водительские права"); }
                        let spawn = pl.bus.car_spawn;
                        let vid = self.spawn_vehicle("bus", 0xf0b429, spawn, pid, Kind::Job);
                        self.players.get_mut(&pid).unwrap().job = Some(Job {
                            kind: JobType::Bus, target: [0.0; 2], label: String::new(), info: String::new(),
                            packages: 0, from: [0.0; 2], vid, idx: 0,
                        });
                        self.bus_next(pid);
                        ok(self, "Автобус ждёт рядом с парком. Садитесь (F) и езжайте по остановкам");
                    }
                    _ => return,
                }
                self.send_job(pid);
            }
            "quitjob" => {
                if self.players[&pid].job.is_none() { return; }
                self.players.get_mut(&pid).unwrap().job = None;
                self.remove_vehicles_of(pid, Some(Kind::Job));
                notify(&self.players[&pid], "Вы завершили работу", "info");
                self.send_job(pid);
            }
            _ => {}
        }
    }

    fn on_checkpoint(&mut self, pid: i64) {
        let now = self.now();
        let Some(p) = self.players.get_mut(&pid) else { return };
        let (x, z, veh) = (p.x, p.z, p.veh);
        let Some(j) = p.job.as_ref() else { return };
        if now - p.cp_t < 800 { return; }
        p.cp_t = now;
        let (kind, target, from, packages, jvid) = (j.kind, j.target, j.from, j.packages, j.vid);
        let radius = if kind == JobType::Bus { 10.0 } else { 7.0 };
        if dist(x, z, target[0], target[1]) > radius { return; }
        match kind {
            JobType::Courier => {
                if packages > 0 {
                    let pay = (60.0 + dist(from[0], from[1], x, z) * 0.5).round().min(260.0) as i64;
                    if let Some(pr) = self.prof_mut(pid) { pr.stats.deliveries += 1; }
                    self.add_money(pid, pay);
                    notify(&self.players[&pid], &format!("Посылка доставлена: +{}", money(pay)), "ok");
                } else {
                    notify(&self.players[&pid], "Загружено 5 новых посылок", "ok");
                }
                if let Some(j) = self.players.get_mut(&pid).unwrap().job.as_mut() {
                    j.packages = if packages > 0 { packages - 1 } else { 5 };
                    j.from = [x, z];
                }
                self.courier_next(pid);
            }
            JobType::Bus => {
                if veh != jvid {
                    return notify(&self.players[&pid], "Нужно быть за рулём рабочего автобуса", "warn");
                }
                if let Some(pr) = self.prof_mut(pid) { pr.stats.stops += 1; }
                self.add_money(pid, 70);
                let n = self.route.len();
                let j = self.players.get_mut(&pid).unwrap().job.as_mut().unwrap();
                j.idx += 1;
                if j.idx >= n {
                    j.idx = 0;
                    self.add_money(pid, 350);
                    notify(&self.players[&pid], "Маршрут пройден! Премия +$350, начинаем новый круг", "ok");
                } else {
                    notify(&self.players[&pid], "Остановка: +$70", "ok");
                }
                self.bus_next(pid);
            }
        }
        self.send_job(pid);
        self.send_profile(pid);
    }

    fn on_enter(&mut self, pid: i64, m: &Value) {
        let Some(vid) = num(m, "vid").map(|v| v as i64) else { return };
        let Some(p) = self.players.get(&pid) else { return };
        let Some(v) = self.vehicles.get(&vid) else { return };
        if p.veh >= 0 { return; }
        if v.driver >= 0 { return notify(p, "Место водителя занято", "warn"); }
        if v.owner != pid { return notify(p, "Транспорт закрыт", "warn"); }
        let len = world::car(v.model).map_or(4.0, |c| c.len);
        if dist(p.x, p.z, v.x, v.z) > len / 2.0 + 4.0 { return; }
        let msg = json!({ "t": "entered", "vid": vid, "x": v.x, "z": v.z, "ry": v.ry });
        self.vehicles.get_mut(&vid).unwrap().driver = pid;
        let p = self.players.get_mut(&pid).unwrap();
        p.veh = vid;
        send(p, msg);
    }

    fn on_exit(&mut self, pid: i64) {
        let Some(p) = self.players.get_mut(&pid) else { return };
        let vid = p.veh;
        p.veh = -1;
        let Some(v) = self.vehicles.get_mut(&vid) else { return };
        v.driver = -1;
        v.spd = 0.0;
        let off = world::car(v.model).map_or(1.0, |c| c.wid) / 2.0 + 0.8;
        p.x = v.x + v.ry.cos() * off;
        p.z = v.z - v.ry.sin() * off;
        send(p, json!({ "t": "exited", "x": p.x, "z": p.z }));
    }

    // ---------- таймеры ----------
    /// Снимок мира. Каждый игрок получает только тех, кто в радиусе VIEW_RADIUS.
    /// Формат (v2): игрок [id,x,y,z,ry,anim,veh(,ник)], машина [id,x,z,ry,spd,driver(,модель,цвет,владелец,номер)] —
    /// хвост в скобках только при первом появлении у получателя.
    pub fn snapshots(&mut self) {
        if self.players.is_empty() {
            return;
        }
        let pe: Vec<SnapEntry> = self.players.values().map(|p| SnapEntry {
            id: p.id, x: p.x, z: p.z, owner: -1,
            short: format!("[{},{},{},{},{},{},{}", p.id, r2(p.x), r2(p.y), r2(p.z), r2(p.ry), p.anim, p.veh),
            tail: format!(",{}]", serde_json::to_string(&p.name).unwrap()),
        }).collect();
        let ve: Vec<SnapEntry> = self.vehicles.values().map(|v| SnapEntry {
            id: v.id, x: v.x, z: v.z, owner: v.owner,
            short: format!("[{},{},{},{},{},{}", v.id, r2(v.x), r2(v.z), r2(v.ry), r2(v.spd), v.driver),
            tail: format!(",\"{}\",{},{},{},{}]", v.model, v.color, v.owner, serde_json::to_string(&v.plate).unwrap(),
                          serde_json::to_string(&v.skin).unwrap()),
        }).collect();
        let ctx = SnapCtx {
            head: format!("{{\"t\":\"snap\",\"f\":2,\"time\":{},\"n\":{},\"p\":[", self.game_time(), self.players.len()),
            gp: Grid::new(&pe),
            gv: Grid::new(&ve),
            pe,
            ve,
        };
        let mut list: Vec<&mut Player> = self.players.values_mut().collect();
        // много игроков — раскладываем сборку снимков по ядрам процессора
        let threads = if list.len() < 200 { 1 } else { std::thread::available_parallelism().map_or(1, |n| n.get()).min(8) };
        if threads == 1 {
            let mut buf = String::new();
            for p in list { ctx.send_to(p, &mut buf); }
        } else {
            let chunk = list.len().div_ceil(threads);
            let ctx = &ctx;
            std::thread::scope(|sc| {
                for part in list.chunks_mut(chunk) {
                    sc.spawn(move || {
                        let mut buf = String::new();
                        for p in part.iter_mut() { ctx.send_to(p, &mut buf); }
                    });
                }
            });
        }
    }

    /// PayDay каждые 10 минут в игре.
    pub fn tick_second(&mut self) {
        let due: Vec<i64> = self.players.values_mut().filter_map(|p| {
            p.online += 1;
            (p.online % 600 == 0).then_some(p.id)
        }).collect();
        for pid in due {
            self.payday(pid);
        }
    }

    fn payday(&mut self, pid: i64) {
        let Some(pr) = self.prof_mut(pid) else { return };
        let pay = 150 + pr.level * 50;
        pr.money += pay;
        pr.exp += 1;
        let mut text = format!("PayDay! Зарплата {}, +1 опыт", money(pay));
        if pr.exp >= pr.level * 3 {
            pr.exp = 0;
            pr.level += 1;
            let _ = write!(text, ". Новый уровень: {}!", pr.level);
        }
        notify(&self.players[&pid], &text, "ok");
        self.send_profile(pid);
    }
}

// ---------- сборка снимков ----------
struct SnapEntry {
    id: i64,
    x: f64,
    z: f64,
    owner: i64,
    short: String,
    tail: String,
}

/// Сетка по городу: клетка CELL_M метров, у каждой — список записей внутри.
const CELL_M: f64 = 75.0;
const GRID_N: usize = (world::SIZE / CELL_M) as usize + 1;

struct Grid(Vec<Vec<usize>>);

impl Grid {
    fn cell(v: f64) -> usize {
        ((v / CELL_M).floor().max(0.0) as usize).min(GRID_N - 1)
    }
    fn new(items: &[SnapEntry]) -> Grid {
        let mut g = vec![Vec::new(); GRID_N * GRID_N];
        for (i, e) in items.iter().enumerate() {
            g[Self::cell(e.z) * GRID_N + Self::cell(e.x)].push(i);
        }
        Grid(g)
    }
    /// Индексы записей в клетках, задевающих круг радиуса VIEW_RADIUS вокруг точки.
    fn around(&self, x: f64, z: f64, mut f: impl FnMut(usize)) {
        let (x0, x1) = (Self::cell(x - VIEW_RADIUS), Self::cell(x + VIEW_RADIUS));
        let (z0, z1) = (Self::cell(z - VIEW_RADIUS), Self::cell(z + VIEW_RADIUS));
        for cz in z0..=z1 {
            for cx in x0..=x1 {
                for &i in &self.0[cz * GRID_N + cx] {
                    f(i);
                }
            }
        }
    }
}

struct SnapCtx {
    head: String,
    pe: Vec<SnapEntry>,
    ve: Vec<SnapEntry>,
    gp: Grid,
    gv: Grid,
}

impl SnapCtx {
    fn send_to(&self, p: &mut Player, buf: &mut String) {
        let r2v = VIEW_RADIUS * VIEW_RADIUS;
        let (px, pz) = (p.x, p.z);
        buf.clear();
        buf.push_str(&self.head);
        let mut first = true;
        let known = &mut p.known_p;
        self.gp.around(px, pz, |i| {
            let e = &self.pe[i];
            if e.id == p.id || (e.x - px).powi(2) + (e.z - pz).powi(2) > r2v {
                return;
            }
            if !first { buf.push(','); }
            first = false;
            buf.push_str(&e.short);
            if known.insert(e.id) { buf.push_str(&e.tail); } else { buf.push(']'); }
        });
        buf.push_str("],\"v\":[");
        first = true;
        let known = &mut p.known_v;
        let pid = p.id;
        let mut add = |e: &SnapEntry, buf: &mut String, first: &mut bool| {
            if !*first { buf.push(','); }
            *first = false;
            buf.push_str(&e.short);
            if known.insert(e.id) { buf.push_str(&e.tail); } else { buf.push(']'); }
        };
        self.gv.around(px, pz, |i| {
            let e = &self.ve[i];
            if (e.x - px).powi(2) + (e.z - pz).powi(2) <= r2v {
                add(e, buf, &mut first);
            }
        });
        // свои машины — всегда, даже если далеко
        for e in &self.ve {
            if e.owner == pid && (e.x - px).powi(2) + (e.z - pz).powi(2) > r2v {
                add(e, buf, &mut first);
            }
        }
        buf.push_str("]}");
        if p.tx.try_send(Utf8Bytes::from(buf.as_str().to_owned())).is_err() {
            // снимок выброшен (клиент не успевает) — ники и данные машин пришлём заново
            p.known_p.clear();
            p.known_v.clear();
        }
    }
}

// ---------- админка (как в shared/core.js) ----------
const ADMIN_CMDS: &[(&str, i64, &str)] = &[
    ("ahelp", 1, "список админ-команд"), ("apanel", 1, "админ-панель"), ("a", 1, "[текст] — чат администрации"),
    ("admins", 1, "админы онлайн"), ("fly", 1, "полёт вкл/выкл"), ("tp", 1, "[x] [z] — телепорт"),
    ("tpp", 1, "[место] — к месту города"), ("spawn", 1, "на площадь"), ("goto", 1, "[id] — к игроку"),
    ("gethere", 2, "[id] — игрока к себе"), ("spcar", 2, "[модель] [цвет 0-7] — машина рядом"),
    ("dvall", 2, "убрать мои админ-машины"), ("color", 2, "[0-7] — перекрасить машину"), ("givelic", 2, "[id] — права"),
    ("settime", 2, "[час] — время суток"), ("givecash", 3, "[id] [сумма] или [сумма]"), ("setmoney", 4, "[id] [сумма]"),
    ("setlevel", 4, "[id] [уровень]"), ("payday", 4, "PayDay всем"), ("setadmin", 5, "[id] [0-5]"),
];

fn class_of(skin: &str) -> &'static str {
    match skin {
        "granta" | "grantaf" | "logan" | "kiar" => "kroha",
        "vesta" | "vestasw" | "focus" | "kiakf" => "vektor",
        "patriota" | "patriotf" | "patriotp" | "lexuslx" | "mercesg" => "taiga",
        "bus" => "bus",
        _ => "bars",
    }
}

impl Game {
    fn admin_level(&self, pid: i64) -> i64 {
        self.prof(pid).map_or(0, |p| p.admin)
    }

    fn target(&self, pid: i64, arg: Option<&&str>) -> Option<i64> {
        match arg.copied() {
            None | Some("") | Some("me") => Some(pid),
            Some(s) => s.parse::<i64>().ok().filter(|id| self.players.contains_key(id)),
        }
    }

    fn teleport(&mut self, pid: i64, x: f64, z: f64) {
        if let Some(p) = self.players.get_mut(&pid) {
            p.x = x.clamp(0.0, world::SIZE);
            p.z = z.clamp(0.0, world::SIZE);
            send(p, json!({ "t": "teleport", "x": p.x, "z": p.z }));
        }
    }

    fn admin_chat(&self, text: &str) {
        for q in self.players.values() {
            if self.db.get(&q.key).map_or(0, |p| p.admin) > 0 {
                send(q, json!({ "t": "chat", "text": text, "color": "#ff8a65" }));
            }
        }
    }

    /// true — команда админская (выполнена или отказано в доступе).
    fn admin_command(&mut self, pid: i64, cmd: &str, rest: &[&str], arg: &str) -> bool {
        let Some(&(_, need, _)) = ADMIN_CMDS.iter().find(|c| c.0 == cmd) else { return false };
        let lvl = self.admin_level(pid);
        let a: Vec<&str> = rest.iter().copied().filter(|s| !s.is_empty()).collect();
        let warn = |g: &Game, t: &str| notify(&g.players[&pid], t, "warn");
        if lvl < need {
            warn(self, "Нет доступа");
            return true;
        }
        let (px, pz, pry, name) = { let p = &self.players[&pid]; (p.x, p.z, p.ry, p.name.clone()) };
        match cmd {
            "ahelp" => {
                for (c, l, d) in ADMIN_CMDS {
                    if *l <= lvl {
                        send(&self.players[&pid], json!({ "t": "chat", "text": format!("[{l}] /{c} — {d}"), "color": "#ff8a65" }));
                    }
                }
            }
            "apanel" => send(&self.players[&pid], json!({ "t": "apanel" })),
            "a" => if !arg.is_empty() { self.admin_chat(&format!("[A] {name} [{pid}]: {arg}")) },
            "admins" => {
                let list: Vec<String> = self.players.values()
                    .filter_map(|q| self.db.get(&q.key).filter(|p| p.admin > 0).map(|p| format!("{} [{}] — {} ур.", q.name, q.id, p.admin)))
                    .collect();
                let text = format!("Администрация онлайн: {}", if list.is_empty() { "никого".into() } else { list.join(", ") });
                send(&self.players[&pid], json!({ "t": "chat", "text": text, "color": "#ff8a65" }));
            }
            "fly" => {
                let p = self.players.get_mut(&pid).unwrap();
                p.fly = !p.fly;
                let on = p.fly;
                send(p, json!({ "t": "fly", "on": on }));
                notify(p, if on { "Полёт включён" } else { "Полёт выключен" }, "ok");
            }
            "tp" => {
                let (x, z) = (a.first().and_then(|s| s.parse::<f64>().ok()), a.get(1).and_then(|s| s.parse::<f64>().ok()));
                match (x, z) { (Some(x), Some(z)) => self.teleport(pid, x, z), _ => warn(self, "Использование: /tp [x] [z]") }
            }
            "tpp" | "spawn" => {
                let pl = self.places;
                let pos = match if cmd == "spawn" { "spawn" } else { a.first().copied().unwrap_or("") } {
                    "spawn" => Some(pl.spawn.pos), "rent" => Some(pl.rent.pos), "school" => Some(pl.school.pos),
                    "dealer" => Some(pl.dealer.pos), "courier" => Some(pl.courier.pos), "bus" => Some(pl.bus.pos), _ => None,
                };
                match pos { Some(p) => self.teleport(pid, p[0], p[1] + 2.0), None => warn(self, "Места: spawn, rent, school, dealer, courier, bus") }
            }
            "goto" => match self.target(pid, a.first()).filter(|&t| t != pid) {
                Some(t) => { let (x, z) = (self.players[&t].x, self.players[&t].z); self.teleport(pid, x + 1.5, z) }
                None => warn(self, "Нет такого игрока"),
            },
            "gethere" => match self.target(pid, a.first()).filter(|&t| t != pid) {
                Some(t) => { self.teleport(t, px + 1.5, pz); notify(&self.players[&t], &format!("Вас телепортировал администратор {name}"), "info") }
                None => warn(self, "Нет такого игрока"),
            },
            "spcar" => {
                let skin: String = a.first().unwrap_or(&"").to_lowercase().chars().filter(|c| c.is_ascii_alphanumeric() || *c == '_').collect();
                if skin.is_empty() { warn(self, "Использование: /spcar [модель]"); return true; }
                let (model, skin_opt) = match world::car(&skin) { Some(c) => (c.id, None), None => (class_of(&skin), Some(skin.clone())) };
                let ci = a.get(1).and_then(|s| s.parse::<usize>().ok()).filter(|&c| c < 8).unwrap_or_else(|| rand::thread_rng().gen_range(0..8));
                let mine: Vec<i64> = self.vehicles.values().filter(|v| v.owner == pid && v.kind == Kind::Admin).map(|v| v.id).collect();
                if mine.len() >= 10 { self.remove_vehicle(mine[0]); }
                let len = world::car(model).map_or(4.5, |c| c.len);
                let d = len / 2.0 + 2.5;
                let x = (px + pry.sin() * d).clamp(1.0, world::SIZE - 1.0);
                let z = (pz + pry.cos() * d).clamp(1.0, world::SIZE - 1.0);
                self.spawn_vehicle_skin(model, world::CAR_COLORS[ci], [x, z, pry], pid, Kind::Admin, skin_opt);
                notify(&self.players[&pid], &format!("Машина {skin} создана — подойдите и нажмите F"), "ok");
            }
            "dvall" => { self.remove_vehicles_of(pid, Some(Kind::Admin)); notify(&self.players[&pid], "Админ-машины убраны", "info") }
            "color" => {
                let vid = self.players[&pid].veh;
                let c = world::CAR_COLORS[a.first().and_then(|s| s.parse::<usize>().ok()).unwrap_or(0) & 7];
                match self.vehicles.get_mut(&vid) { Some(v) => v.color = c, None => warn(self, "Сядьте в машину") }
            }
            "givelic" => if let Some(t) = self.target(pid, a.first()) {
                if let Some(p) = self.prof_mut(t) { p.license = true; }
                self.send_profile(t);
                notify(&self.players[&t], "Вам выданы водительские права", "ok");
            },
            "settime" => match a.first().and_then(|s| s.parse::<f64>().ok()).filter(|h| (0.0..24.0).contains(h)) {
                Some(h) => {
                    self.time_offset += h.floor() * 60.0 - self.game_time().floor();
                    self.broadcast(json!({ "t": "chat", "text": format!("Администратор {name} установил время {:02}:00", h as i64), "color": "#ff8a65" }), None);
                }
                None => warn(self, "Использование: /settime [0-23]"),
            },
            "givecash" => {
                let (t, sum) = if a.len() < 2 { (Some(pid), a.first()) } else { (self.target(pid, a.first()), a.get(1)) };
                match (t, sum.and_then(|s| s.parse::<f64>().ok()).map(|v| v.floor() as i64).filter(|v| *v != 0 && v.abs() <= 1_000_000_000)) {
                    (Some(t), Some(sum)) => {
                        self.add_money(t, sum);
                        self.send_profile(t);
                        notify(&self.players[&t], &format!("Администратор выдал вам {}", money(sum)), "ok");
                    }
                    _ => warn(self, "Использование: /givecash [id] [сумма]"),
                }
            }
            "setmoney" => if let (Some(t), Some(v)) = (self.target(pid, a.first()), a.get(1).and_then(|s| s.parse::<i64>().ok()).filter(|v| *v >= 0)) {
                if let Some(p) = self.prof_mut(t) { p.money = v; }
                self.send_profile(t);
            },
            "setlevel" => if let (Some(t), Some(v)) = (self.target(pid, a.first()), a.get(1).and_then(|s| s.parse::<i64>().ok()).filter(|v| (1..=999).contains(v))) {
                if let Some(p) = self.prof_mut(t) { p.level = v; p.exp = 0; }
                self.send_profile(t);
            },
            "payday" => { let ids: Vec<i64> = self.players.keys().copied().collect(); for id in ids { self.payday(id); } }
            "setadmin" => match (self.target(pid, a.first()), a.get(1).and_then(|s| s.parse::<i64>().ok()).filter(|v| (0..=5).contains(v))) {
                (Some(t), Some(l)) => {
                    if let Some(p) = self.prof_mut(t) { p.admin = l; }
                    self.send_profile(t);
                    let tn = self.players[&t].name.clone();
                    self.admin_chat(&format!("{name} выдал {tn} админку {l} уровня"));
                }
                _ => warn(self, "Использование: /setadmin [id] [0-5]"),
            },
            _ => {}
        }
        true
    }
}
