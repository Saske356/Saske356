//! Общее состояние клиента: игрок, камера, чат, известные сущности, столкновения с миром.

use std::collections::HashMap;

use bevy::prelude::*;
use novo_world as world;

/// Физика машины, которой управляем сами.
#[derive(Clone)]
pub struct CarPhys {
    pub model: String,
    pub x: f32,
    pub z: f32,
    pub ry: f32,
    pub spd: f32,
    pub steer: f32,
}

#[derive(Clone)]
pub struct RemoteP {
    pub entity: Entity,
    pub name: String,
    pub target: Vec3,
    pub ry: f32,
    pub anim: i64,
    pub veh: i64,
}

#[derive(Clone)]
pub struct RemoteV {
    pub entity: Entity,
    pub model: String,
    pub skin: Option<String>,
    pub color: u32,
    pub owner: i64,
    pub driver: i64,
    pub plate: String,
    pub target: Vec3,
    pub ry: f32,
    pub spd: f32,
}

#[derive(Clone)]
pub struct VehStatic {
    pub model: String,
    pub color: u32,
    pub owner: i64,
    pub plate: String,
    pub skin: Option<String>,
}

#[derive(Resource, Default)]
pub struct Game {
    pub connected: bool,
    pub status: String,
    pub my_id: i64,
    pub name: String,
    pub money: i64,
    pub level: i64,
    pub admin: i64,
    pub license: bool,
    pub time: f32,
    pub online: i64,
    pub pos: Vec3,
    pub ry: f32,
    pub anim: i64,
    pub veh: i64,
    pub car: Option<CarPhys>,
    pub fly: bool,
    pub cam_yaw: f32,
    pub cam_pitch: f32,
    pub cam_dist: f32,
    pub last_drag: f32,
    pub chat: Vec<(String, Color)>,
    pub toast: Option<(String, f32)>,
    pub typing: Option<String>,
    pub players: HashMap<i64, RemoteP>,
    pub vehicles: HashMap<i64, RemoteV>,
    pub name_cache: HashMap<i64, String>,
    pub veh_cache: HashMap<i64, VehStatic>,
    pub send_timer: f32,
    pub job_target: Option<Vec2>,
    pub job_label: String,
    pub cp_timer: f32,
}

impl Game {
    pub fn new() -> Self {
        Game { veh: -1, my_id: -1, cam_pitch: 0.32, cam_dist: 6.0, time: 540.0, status: "Подключение…".into(), ..default() }
    }
    pub fn chat(&mut self, text: impl Into<String>, color: Color) {
        self.chat.push((text.into(), color));
        if self.chat.len() > 60 {
            self.chat.remove(0);
        }
    }
}

/// Столкновения и высота земли.
#[derive(Resource)]
pub enum Collider {
    /// Наш город (генератор из world-rs).
    City(Vec<world::Obstacle>),
    /// Карта из .glb: треугольники, разложенные по сетке.
    Map(MapGrid),
    /// Карта ещё грузится.
    Loading,
}

const CELL: f32 = 4.0;

pub struct MapGrid {
    tris: Vec<[f32; 9]>,
    grid: HashMap<(i32, i32), Vec<u32>>,
}

impl MapGrid {
    pub fn new(tris: Vec<[f32; 9]>) -> Self {
        let mut grid: HashMap<(i32, i32), Vec<u32>> = HashMap::new();
        for (i, t) in tris.iter().enumerate() {
            let x0 = (t[0].min(t[3]).min(t[6]) / CELL).floor() as i32;
            let x1 = (t[0].max(t[3]).max(t[6]) / CELL).floor() as i32;
            let z0 = (t[2].min(t[5]).min(t[8]) / CELL).floor() as i32;
            let z1 = (t[2].max(t[5]).max(t[8]) / CELL).floor() as i32;
            if (x1 - x0 + 1) * (z1 - z0 + 1) > 4000 {
                continue; // огромные подложки
            }
            for x in x0..=x1 {
                for z in z0..=z1 {
                    grid.entry((x, z)).or_default().push(i as u32);
                }
            }
        }
        MapGrid { tris, grid }
    }

    pub fn triangles(&self) -> usize {
        self.tris.len()
    }

    fn heights(&self, x: f32, z: f32, out: &mut Vec<f32>) {
        out.clear();
        let Some(list) = self.grid.get(&((x / CELL).floor() as i32, (z / CELL).floor() as i32)) else { return };
        for &i in list {
            let t = &self.tris[i as usize];
            let d = (t[5] - t[8]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[2] - t[8]);
            if d.abs() < 1e-9 {
                continue;
            }
            let l1 = ((t[5] - t[8]) * (x - t[6]) + (t[6] - t[3]) * (z - t[8])) / d;
            let l2 = ((t[8] - t[2]) * (x - t[6]) + (t[0] - t[6]) * (z - t[8])) / d;
            let l3 = 1.0 - l1 - l2;
            if l1 < -1e-4 || l2 < -1e-4 || l3 < -1e-4 {
                continue;
            }
            out.push(l1 * t[1] + l2 * t[4] + l3 * t[7]);
        }
    }

    pub fn ground(&self, x: f32, z: f32, y: f32, step: f32) -> f32 {
        let mut hs = Vec::new();
        self.heights(x, z, &mut hs);
        // самая высокая поверхность, на которую можно шагнуть; если её нет — минус бесконечность
        hs.into_iter().filter(|h| *h <= y + step).fold(f32::NEG_INFINITY, f32::max)
    }

    pub fn lowest(&self, x: f32, z: f32) -> Option<f32> {
        let mut hs = Vec::new();
        self.heights(x, z, &mut hs);
        hs.into_iter().reduce(f32::min)
    }

    pub fn blocked(&self, x: f32, z: f32, y: f32, step: f32) -> bool {
        let mut hs = Vec::new();
        self.heights(x, z, &mut hs);
        hs.into_iter().any(|h| h > y + step && h < y + 40.0)
    }
}

impl Collider {
    pub fn ground(&self, x: f32, z: f32, y: f32) -> f32 {
        match self {
            Collider::City(_) => world::ground_height(x as f64, z as f64) as f32,
            Collider::Map(m) => {
                let g = m.ground(x, z, y, 1.2);
                if g.is_finite() && g > -99.0 { g } else { 0.0 }
            }
            Collider::Loading => y,
        }
    }

    /// Ход из (ox, oz) в (nx, nz): возвращает итоговую точку и было ли столкновение.
    pub fn step(&self, ox: f32, oz: f32, nx: f32, nz: f32, y: f32, radius: f32) -> (f32, f32, bool) {
        match self {
            Collider::City(boxes) => {
                let (x, z, hit) = world::collide_circle(nx as f64, nz as f64, radius as f64, boxes);
                (x as f32, z as f32, hit)
            }
            Collider::Map(m) => {
                if !m.blocked(nx, nz, y, 1.2) {
                    (nx, nz, false)
                } else if !m.blocked(nx, oz, y, 1.2) {
                    (nx, oz, true)
                } else if !m.blocked(ox, nz, y, 1.2) {
                    (ox, nz, true)
                } else {
                    (ox, oz, true)
                }
            }
            Collider::Loading => (nx, nz, false),
        }
    }
}

/// Пути и режим запуска.
#[derive(Resource, Clone)]
pub struct Launch {
    pub game_dir: std::path::PathBuf,
    pub map: Option<String>,
    pub offline: bool,
    pub quality_shadows: bool,
}

pub const SIZE: f32 = world::SIZE as f32;

pub fn hex_color(c: u32) -> Color {
    Color::srgb_u8((c >> 16) as u8, (c >> 8) as u8, c as u8)
}

pub fn lerp_angle(a: f32, b: f32, t: f32) -> f32 {
    let d = ((b - a + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU)) - std::f32::consts::PI;
    a + d * t
}

pub fn name_color(name: &str) -> Color {
    let mut h: u32 = 0;
    for c in name.chars() {
        h = h.wrapping_mul(31).wrapping_add(c as u32);
    }
    Color::hsl((h % 360) as f32, 0.55, 0.5)
}
