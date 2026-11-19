//! Мир Новограда — порт `shared/world.js`. Генератор города совпадает с клиентским
//! бит в бит (тот же mulberry32 и тот же порядок вызовов), поэтому адреса доставки
//! на сервере и у игроков одинаковые.

use std::f64::consts::PI;

pub const GRID: i32 = 8;
pub const BLOCK: f64 = 64.0;
pub const ROAD: f64 = 16.0;
pub const CELL: f64 = BLOCK + ROAD;
pub const SIZE: f64 = GRID as f64 * CELL + ROAD;
pub const SIDEWALK: f64 = 4.0;
pub const LANE: f64 = 4.0;
pub const CURB: f64 = 0.15;
const SEED: u32 = 20261119;

pub fn road_center(i: i32) -> f64 {
    i as f64 * CELL + ROAD / 2.0
}

#[derive(Clone, Copy)]
pub struct Rect {
    pub x0: f64,
    pub z0: f64,
    pub x1: f64,
    pub z1: f64,
}

pub fn block_rect(bx: i32, bz: i32) -> Rect {
    let x0 = bx as f64 * CELL + ROAD;
    let z0 = bz as f64 * CELL + ROAD;
    Rect { x0, z0, x1: x0 + BLOCK, z1: z0 + BLOCK }
}

pub fn ground_height(x: f64, z: f64) -> f64 {
    let inside = |v: f64| {
        let i = (v / CELL).floor();
        i >= 0.0 && i < GRID as f64 && v - i * CELL >= ROAD
    };
    if inside(x) && inside(z) { CURB } else { 0.0 }
}

// ---------- транспорт ----------
pub struct Car {
    pub id: &'static str,
    pub name: &'static str,
    pub price: i64,
    pub len: f64,
    pub wid: f64,
    pub job: bool,
}

pub const CARS: &[Car] = &[
    Car { id: "kroha", name: "Кроха", price: 3000, len: 3.6, wid: 1.7, job: false },
    Car { id: "vektor", name: "Вектор", price: 9000, len: 4.5, wid: 1.85, job: false },
    Car { id: "taiga", name: "Тайга", price: 22000, len: 4.8, wid: 2.0, job: false },
    Car { id: "bars", name: "Барс", price: 45000, len: 4.4, wid: 1.9, job: false },
    Car { id: "bus", name: "Автобус", price: 0, len: 11.0, wid: 2.5, job: true },
];

pub fn car(id: &str) -> Option<&'static Car> {
    CARS.iter().find(|c| c.id == id)
}

pub const CAR_COLORS: [i64; 8] = [0xd94f3d, 0x2f6fd6, 0xf2f2f2, 0x1d1d1f, 0x3aa65b, 0xf0b429, 0x8e8e93, 0x7a3fd1];
pub const PRICE_RENT: i64 = 100;
pub const PRICE_LICENSE: i64 = 400;

// ---------- места ----------
#[derive(Clone, Copy)]
pub struct Place {
    pub pos: [f64; 2],
    pub car_spawn: [f64; 3],
}

#[derive(Clone, Copy)]
pub struct Places {
    pub spawn: Place,
    pub rent: Place,
    pub school: Place,
    pub dealer: Place,
    pub courier: Place,
    pub bus: Place,
}

pub fn places() -> Places {
    let sp = block_rect(3, 3);
    let sc = block_rect(2, 3);
    let dl = block_rect(5, 2);
    let cr = block_rect(1, 5);
    let bp = block_rect(6, 6);
    let none = [0.0; 3];
    Places {
        spawn: Place { pos: [sp.x0 + 32.0, sp.z0 + 46.0], car_spawn: none },
        rent: Place { pos: [sp.x0 + 10.0, sp.z0 + 3.0], car_spawn: [sp.x0 + 10.0, sp.z0 - LANE, PI / 2.0] },
        school: Place { pos: [sc.x0 + 32.0, sc.z0 + 3.0], car_spawn: none },
        dealer: Place { pos: [dl.x0 + 32.0, dl.z0 + 3.0], car_spawn: [dl.x0 + 32.0, dl.z0 - LANE, PI / 2.0] },
        courier: Place { pos: [cr.x0 + 32.0, cr.z0 + 3.0], car_spawn: none },
        bus: Place { pos: [bp.x1 - 3.0, bp.z0 + 20.0], car_spawn: [road_center(7) - LANE, bp.z0 + 20.0, 0.0] },
    }
}

/// Блоки, занятые особыми местами (там генератор не строит обычные дома).
fn special_block(bx: i32, bz: i32) -> Option<&'static str> {
    match (bx, bz) {
        (3, 3) => Some("spawn"),
        (2, 3) => Some("school"),
        (5, 2) => Some("dealer"),
        (1, 5) => Some("courier"),
        (6, 6) => Some("bus"),
        _ => None,
    }
}

/// Кольцевой маршрут автобуса по дорогам 1 и 7.
pub fn bus_route() -> Vec<[f64; 2]> {
    let rc = road_center;
    let mid = |a: i32| a as f64 * CELL + ROAD / 2.0 + CELL / 2.0;
    let mut all = Vec::new();
    for a in 1..=6 { all.push([mid(a), rc(1) + LANE]); }
    for a in 1..=6 { all.push([rc(7) - LANE, mid(a)]); }
    for a in (1..=6).rev() { all.push([mid(a), rc(7) - LANE]); }
    for a in (1..=6).rev() { all.push([rc(1) + LANE, mid(a)]); }
    let stops: Vec<[f64; 2]> = all.into_iter().step_by(2).collect();
    let mut route = stops[6..].to_vec();
    route.extend_from_slice(&stops[..6]);
    route
}

/// Math.round из JS: .5 округляется вверх.
fn js_round(v: f64) -> f64 {
    (v + 0.5).floor()
}

pub struct Lane {
    pub x: f64,
    pub z: f64,
    pub ry: f64,
}

pub fn nearest_lane(x: f64, z: f64) -> Lane {
    let clamp_i = |v: f64| (js_round((v - ROAD / 2.0) / CELL)).clamp(0.0, GRID as f64) as i32;
    let ix = clamp_i(x);
    let iz = clamp_i(z);
    let dx = (x - road_center(ix)).abs();
    let dz = (z - road_center(iz)).abs();
    let lim = |v: f64| v.clamp(ROAD, SIZE - ROAD);
    if dx < dz {
        Lane { x: road_center(ix) - LANE, z: lim(z), ry: 0.0 }
    } else {
        Lane { x: lim(x), z: road_center(iz) + LANE, ry: PI / 2.0 }
    }
}

// ---------- генерация города ----------
struct Mulberry32(u32);

impl Mulberry32 {
    fn next(&mut self) -> f64 {
        self.0 = self.0.wrapping_add(0x6d2b79f5);
        let a = self.0;
        let mut t = (a ^ (a >> 15)).wrapping_mul(1 | a);
        t = t.wrapping_add((t ^ (t >> 7)).wrapping_mul(61 | t)) ^ t;
        (t ^ (t >> 14)) as f64 / 4294967296.0
    }
}

/// Адреса доставки — у входа в каждое обычное здание (как в клиентском генераторе).
pub fn deliveries() -> Vec<[f64; 2]> {
    let mut r = Mulberry32(SEED);
    let mut out = Vec::new();
    for bz in 0..GRID {
        for bx in 0..GRID {
            let b = block_rect(bx, bz);
            if special_block(bx, bz).is_some() {
                continue; // особые блоки не тратят случайные числа
            }
            let center = 1.0 - ((bx as f64 - 3.5).hypot(bz as f64 - 3.5) / 5.0).min(1.0);
            let roll = r.next();
            let mut local: Vec<Rect> = Vec::new();
            if roll < 0.1 {
                for _ in 0..10 {
                    let _x = r.next();
                    let _z = r.next();
                }
            } else if roll < 0.32 {
                let ins = 8.0 + r.next() * 6.0;
                let _h = 14.0 + r.next() * 16.0 + center * 45.0;
                let _color = r.next();
                local.push(Rect { x0: b.x0 + ins, z0: b.z0 + ins, x1: b.x1 - ins, z1: b.z1 - ins });
            } else {
                for i in 0..2 {
                    for j in 0..2 {
                        let lx = b.x0 + SIDEWALK + i as f64 * 28.0;
                        let lz = b.z0 + SIDEWALK + j as f64 * 28.0;
                        if r.next() < 0.1 {
                            continue; // дерево на пустом участке
                        }
                        let ins = 1.0 + r.next() * 3.0;
                        let _h1 = r.next();
                        let _h2 = r.next();
                        let _color = r.next();
                        local.push(Rect { x0: lx + ins, z0: lz + ins, x1: lx + 28.0 - ins, z1: lz + 28.0 - ins });
                    }
                }
            }
            for _ in 0..16 {
                let _tree = r.next(); // деревья вдоль тротуаров
            }
            for h in &local {
                let cx = (h.x0 + h.x1) / 2.0;
                let cz = (h.z0 + h.z1) / 2.0;
                let d = [cx - b.x0, b.x1 - cx, cz - b.z0, b.z1 - cz];
                let m = d.iter().cloned().fold(f64::INFINITY, f64::min);
                out.push(if m == d[0] {
                    [b.x0 + 2.5, cz]
                } else if m == d[1] {
                    [b.x1 - 2.5, cz]
                } else if m == d[2] {
                    [cx, b.z0 + 2.5]
                } else {
                    [cx, b.z1 - 2.5]
                });
            }
        }
    }
    out
}

pub fn format_time(min: f64) -> String {
    let h = (min / 60.0).floor() as i64 % 24;
    let m = (min % 60.0).floor() as i64;
    format!("{:02}:{:02}", h, m)
}
