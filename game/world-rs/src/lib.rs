//! Мир Новограда — порт `shared/world.js`, общий для сервера и клиента. Генератор города совпадает с клиентским
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
    pub hgt: f64,
    /// максимальная скорость, м/с
    pub max_speed: f64,
    /// ускорение, м/с²
    pub accel: f64,
    pub job: bool,
}

pub const CARS: &[Car] = &[
    Car { id: "kroha", name: "Кроха", price: 3000, len: 4.3, wid: 1.75, hgt: 1.5, max_speed: 30.0, accel: 8.0, job: false },
    Car { id: "vektor", name: "Вектор", price: 9000, len: 4.45, wid: 1.8, hgt: 1.5, max_speed: 40.0, accel: 10.0, job: false },
    Car { id: "taiga", name: "Тайга", price: 22000, len: 4.6, wid: 1.95, hgt: 1.95, max_speed: 42.0, accel: 11.0, job: false },
    Car { id: "bars", name: "Барс", price: 45000, len: 4.9, wid: 1.95, hgt: 1.35, max_speed: 58.0, accel: 16.0, job: false },
    Car { id: "bus", name: "Автобус", price: 0, len: 11.0, wid: 2.5, hgt: 3.1, max_speed: 22.0, accel: 5.0, job: true },
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

pub const PALETTE: [u32; 10] = [0xc9b79c, 0xa7b1bd, 0xd6c7a1, 0x9fa8a3, 0xb98b73, 0xe0dcd2, 0x8c9aa8, 0xc4a484, 0x7d8b99, 0xd8b4a0];

pub struct Building {
    pub r: Rect,
    pub h: f64,
    pub color: u32,
    pub sign: Option<&'static str>,
}

pub struct Decor {
    pub model: &'static str,
    pub color: u32,
    pub x: f64,
    pub z: f64,
    pub ry: f64,
}

/// Препятствие для коллизий. `fountain` — фонтан на площади (рисуется отдельно).
#[derive(Clone, Copy)]
pub struct Obstacle {
    pub r: Rect,
    pub tree: bool,
    pub fountain: bool,
}

#[derive(Default)]
pub struct City {
    pub buildings: Vec<Building>,
    pub parks: Vec<Rect>,
    pub trees: Vec<[f64; 2]>,
    pub deliveries: Vec<[f64; 2]>,
    pub decor: Vec<Decor>,
    pub boxes: Vec<Obstacle>,
}

impl City {
    fn add_building(&mut self, b: Building) -> Rect {
        let r = b.r;
        self.boxes.push(Obstacle { r, tree: false, fountain: false });
        self.buildings.push(b);
        r
    }
    fn add_tree(&mut self, x: f64, z: f64) {
        self.trees.push([x, z]);
        self.boxes.push(Obstacle { r: Rect { x0: x - 0.35, z0: z - 0.35, x1: x + 0.35, z1: z + 0.35 }, tree: true, fountain: false });
    }
    fn add_decor_car(&mut self, model: &'static str, color: u32, x: f64, z: f64, ry: f64) {
        self.decor.push(Decor { model, color, x, z, ry });
        let m = car(model).unwrap();
        let h = m.len.max(m.wid) * 0.45;
        let along = ry.sin().abs() > 0.7;
        let (hx, hz) = if along { (m.len / 2.0, m.wid / 2.0) } else { (m.wid / 2.0, m.len / 2.0) };
        let (ex, ez) = (h.min(hx + 0.2), h.min(hz + 0.2));
        self.boxes.push(Obstacle { r: Rect { x0: x - ex, z0: z - ez, x1: x + ex, z1: z + ez }, tree: false, fountain: false });
    }
}

/// Генератор города — бит в бит как `generateCity()` в `shared/world.js`.
pub fn generate_city() -> City {
    let mut r = Mulberry32(SEED);
    let mut c = City::default();
    let pick = |r: &mut Mulberry32| PALETTE[(r.next() * PALETTE.len() as f64).floor() as usize];
    for bz in 0..GRID {
        for bx in 0..GRID {
            let b = block_rect(bx, bz);
            if let Some(id) = special_block(bx, bz) {
                build_special(&mut c, id, b);
                continue;
            }
            let center = 1.0 - ((bx as f64 - 3.5).hypot(bz as f64 - 3.5) / 5.0).min(1.0);
            let roll = r.next();
            let mut local: Vec<Rect> = Vec::new();
            if roll < 0.1 {
                c.parks.push(b);
                for _ in 0..10 {
                    let x = b.x0 + 8.0 + r.next() * 48.0;
                    let z = b.z0 + 8.0 + r.next() * 48.0;
                    c.add_tree(x, z);
                }
            } else if roll < 0.32 {
                let ins = 8.0 + r.next() * 6.0;
                let h = 14.0 + r.next() * 16.0 + center * 45.0;
                let color = pick(&mut r);
                local.push(c.add_building(Building { r: Rect { x0: b.x0 + ins, z0: b.z0 + ins, x1: b.x1 - ins, z1: b.z1 - ins }, h, color, sign: None }));
            } else {
                for i in 0..2 {
                    for j in 0..2 {
                        let lx = b.x0 + SIDEWALK + i as f64 * 28.0;
                        let lz = b.z0 + SIDEWALK + j as f64 * 28.0;
                        if r.next() < 0.1 {
                            c.add_tree(lx + 14.0, lz + 14.0);
                            continue;
                        }
                        let ins = 1.0 + r.next() * 3.0;
                        let h = 6.0 + r.next() * 12.0 + center * r.next() * 35.0;
                        let color = pick(&mut r);
                        local.push(c.add_building(Building {
                            r: Rect { x0: lx + ins, z0: lz + ins, x1: lx + 28.0 - ins, z1: lz + 28.0 - ins }, h, color, sign: None,
                        }));
                    }
                }
            }
            for t in [10.0, 26.0, 38.0, 54.0] {
                if r.next() < 0.3 { c.add_tree(b.x0 + t, b.z0 + 1.6); }
                if r.next() < 0.3 { c.add_tree(b.x0 + t, b.z1 - 1.6); }
                if r.next() < 0.3 { c.add_tree(b.x0 + 1.6, b.z0 + t); }
                if r.next() < 0.3 { c.add_tree(b.x1 - 1.6, b.z0 + t); }
            }
            for h in &local {
                let cx = (h.x0 + h.x1) / 2.0;
                let cz = (h.z0 + h.z1) / 2.0;
                let d = [cx - b.x0, b.x1 - cx, cz - b.z0, b.z1 - cz];
                let m = d.iter().cloned().fold(f64::INFINITY, f64::min);
                c.deliveries.push(if m == d[0] {
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
    c
}

fn build_special(c: &mut City, id: &str, b: Rect) {
    let rect = |x0: f64, z0: f64, x1: f64, z1: f64| Rect { x0, z0, x1, z1 };
    match id {
        "spawn" => {
            c.parks.push(b);
            c.boxes.push(Obstacle { r: rect(b.x0 + 27.5, b.z0 + 27.5, b.x0 + 36.5, b.z0 + 36.5), tree: false, fountain: true });
            for a in 0..12 {
                let ang = (a as f64 / 12.0) * PI * 2.0;
                c.add_tree(b.x0 + 32.0 + ang.cos() * 22.0, b.z0 + 32.0 + ang.sin() * 22.0);
            }
        }
        "school" => {
            c.add_building(Building { r: rect(b.x0 + 10.0, b.z0 + 26.0, b.x1 - 10.0, b.z1 - 8.0), h: 12.0, color: 0xe8d7a8, sign: Some("АВТОШКОЛА") });
            c.add_decor_car("kroha", 0xf0b429, b.x0 + 14.0, b.z0 + 16.0, 0.3);
        }
        "dealer" => {
            c.add_building(Building { r: rect(b.x0 + 6.0, b.z0 + 32.0, b.x1 - 6.0, b.z1 - 6.0), h: 9.0, color: 0xdfe6ee, sign: Some("АВТОСАЛОН") });
            c.add_decor_car("vektor", 0x2f6fd6, b.x0 + 14.0, b.z0 + 20.0, 0.6);
            c.add_decor_car("bars", 0xd94f3d, b.x0 + 32.0, b.z0 + 21.0, 0.0);
            c.add_decor_car("taiga", 0x3aa65b, b.x0 + 50.0, b.z0 + 20.0, -0.6);
        }
        "courier" => {
            c.add_building(Building { r: rect(b.x0 + 8.0, b.z0 + 22.0, b.x1 - 8.0, b.z1 - 6.0), h: 10.0, color: 0xb98b73, sign: Some("СКЛАД «ЭКСПРЕСС»") });
        }
        "bus" => {
            c.add_building(Building { r: rect(b.x0 + 4.0, b.z0 + 6.0, b.x0 + 26.0, b.z1 - 6.0), h: 9.0, color: 0x9fa8a3, sign: Some("АВТОПАРК") });
            c.add_decor_car("bus", 0xf0b429, b.x0 + 36.0, b.z0 + 34.0, 0.0);
            c.add_decor_car("bus", 0xf0b429, b.x0 + 46.0, b.z0 + 34.0, 0.0);
        }
        _ => {}
    }
}

/// Адреса доставки — у входа в каждое обычное здание.
pub fn deliveries() -> Vec<[f64; 2]> {
    generate_city().deliveries
}

/// Выталкивание окружности из прямоугольников (как `collideCircle` в JS).
pub fn collide_circle(mut x: f64, mut z: f64, r: f64, boxes: &[Obstacle]) -> (f64, f64, bool) {
    let mut hit = false;
    for o in boxes {
        let b = o.r;
        if x < b.x0 - r || x > b.x1 + r || z < b.z0 - r || z > b.z1 + r {
            continue;
        }
        let cx = x.clamp(b.x0, b.x1);
        let cz = z.clamp(b.z0, b.z1);
        let (dx, dz) = (x - cx, z - cz);
        let d2 = dx * dx + dz * dz;
        if d2 >= r * r {
            continue;
        }
        hit = true;
        if d2 > 1e-8 {
            let d = d2.sqrt();
            x = cx + dx / d * r;
            z = cz + dz / d * r;
        } else {
            let (l, rr, t, bb) = (x - b.x0, b.x1 - x, z - b.z0, b.z1 - z);
            let m = l.min(rr).min(t).min(bb);
            if m == l { x = b.x0 - r } else if m == rr { x = b.x1 + r } else if m == t { z = b.z0 - r } else { z = b.z1 + r }
        }
    }
    (x, z, hit)
}

/// Машина как набор окружностей вдоль кузова.
pub fn car_circles(x: f64, z: f64, ry: f64, model: &str) -> Vec<(f64, f64, f64)> {
    let m = car(model).unwrap_or(&CARS[0]);
    let n = ((m.len / m.wid).ceil() as usize).max(2);
    let r = m.wid / 2.0;
    let span = m.len - m.wid;
    let (s, c) = (ry.sin(), ry.cos());
    (0..n).map(|i| {
        let t = (i as f64 / (n - 1) as f64 - 0.5) * span;
        (x + s * t, z + c * t, r)
    }).collect()
}

pub fn format_time(min: f64) -> String {
    let h = (min / 60.0).floor() as i64 % 24;
    let m = (min % 60.0).floor() as i64;
    format!("{:02}:{:02}", h, m)
}
