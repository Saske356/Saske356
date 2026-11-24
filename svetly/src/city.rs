//! Procedural coastal city "Port Svetly": road grid, districts, buildings with
//! lit windows, parks, beach, pier and water. Static geometry is merged per
//! chunk and per material so a phone draws the whole city in a few hundred calls.

use std::collections::HashMap;

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};

use crate::util::*;

pub const N: i32 = 12;
pub const BLOCK: f32 = 64.0;
pub const ROAD: f32 = 14.0;
pub const HALF: f32 = N as f32 * BLOCK * 0.5;
pub const SIDEWALK: f32 = 3.5;
pub const CURB: f32 = 0.15;
pub const LANE: f32 = 3.5;
pub const BEACH_END: f32 = HALF + 48.0;
pub const WATER_LEVEL: f32 = -0.45;
pub const WORLD_LIMIT: f32 = HALF + 36.0;
pub const SEA_LIMIT: f32 = HALF + 260.0;
pub const MAP_EXT: f32 = 480.0;
const CHUNK: i32 = 4;

/// Places with a building of their own on the map.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Place {
    TaxiPark,
    PostOffice,
    BusDepot,
    TruckDepot,
    Bank,
    FireStation,
    Hospital,
    TrafficPolice,
    Fsb,
    NewsAgency,
    DiveCenter,
    OpgGarage,
    Government,
    AutoService,
    WasteYard,
    Casino,
    CarShop,
    Clothes,
}

impl Place {
    pub const ALL: [Place; 18] = [
        Place::TaxiPark,
        Place::PostOffice,
        Place::BusDepot,
        Place::TruckDepot,
        Place::Bank,
        Place::FireStation,
        Place::Hospital,
        Place::TrafficPolice,
        Place::Fsb,
        Place::NewsAgency,
        Place::DiveCenter,
        Place::OpgGarage,
        Place::Government,
        Place::AutoService,
        Place::WasteYard,
        Place::Casino,
        Place::CarShop,
        Place::Clothes,
    ];

    pub fn title(self) -> &'static str {
        match self {
            Place::TaxiPark => "Таксопарк «Светлячок»",
            Place::PostOffice => "Служба доставки",
            Place::BusDepot => "Автобусный парк",
            Place::TruckDepot => "Грузовой терминал",
            Place::Bank => "Банк «Причал»",
            Place::FireStation => "Пожарная часть №1",
            Place::Hospital => "Городская больница",
            Place::TrafficPolice => "ГИБДД",
            Place::Fsb => "Управление ФСБ",
            Place::NewsAgency => "Телеканал «Волна»",
            Place::DiveCenter => "Водолазная станция",
            Place::OpgGarage => "Гараж на окраине",
            Place::Government => "Мэрия",
            Place::AutoService => "Автосервис",
            Place::WasteYard => "Спецавтобаза",
            Place::Casino => "Казино «Маяк»",
            Place::CarShop => "Автосалон",
            Place::Clothes => "Магазин одежды",
        }
    }

    pub fn color(self) -> Color {
        srgb(match self {
            Place::TaxiPark => 0xffc21a,
            Place::PostOffice => 0xff7a1a,
            Place::BusDepot => 0x2fb35a,
            Place::TruckDepot => 0x9a6a3a,
            Place::Bank => 0x1fb8a0,
            Place::FireStation => 0xe8352b,
            Place::Hospital => 0xf2f2f2,
            Place::TrafficPolice => 0x2f6bff,
            Place::Fsb => 0x5a6a7a,
            Place::NewsAgency => 0xc04dff,
            Place::DiveCenter => 0x22c8ff,
            Place::OpgGarage => 0x8a1f1f,
            Place::Government => 0xd8b24a,
            Place::AutoService => 0xa0a0a0,
            Place::WasteYard => 0x6a8a2a,
            Place::Casino => 0xff3d9a,
            Place::CarShop => 0x3dffb4,
            Place::Clothes => 0xff8ad1,
        })
    }

    /// Lot (column, row) where the place stands.
    fn lot(self) -> (i32, i32) {
        match self {
            Place::TaxiPark => (4, 7),
            Place::PostOffice => (7, 4),
            Place::BusDepot => (2, 2),
            Place::TruckDepot => (10, 1),
            Place::Bank => (6, 6),
            Place::FireStation => (3, 5),
            Place::Hospital => (8, 8),
            Place::TrafficPolice => (5, 3),
            Place::Fsb => (6, 4),
            Place::NewsAgency => (7, 7),
            Place::DiveCenter => (11, 6),
            Place::OpgGarage => (0, 10),
            Place::Government => (5, 5),
            Place::AutoService => (2, 8),
            Place::WasteYard => (1, 0),
            Place::Casino => (11, 9),
            Place::CarShop => (9, 5),
            Place::Clothes => (4, 4),
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum LotKind {
    Downtown,
    Midrise,
    Houses,
    Park,
    Beachfront,
    Special(Place),
}

#[derive(Clone, Debug)]
pub struct Lot {
    pub i: i32,
    pub j: i32,
    pub rect: Rect2,
    pub kind: LotKind,
}

#[derive(Clone, Debug)]
pub struct Site {
    pub place: Place,
    /// Where the player walks in (on the sidewalk, in front of the door).
    pub door: Vec3,
    /// A spot on the road next to the door for parking job vehicles.
    pub curb: Vec3,
    pub curb_yaw: f32,
}

#[derive(Resource)]
pub struct CityMap {
    pub lots: Vec<Lot>,
    pub colliders: Vec<Rect2>,
    grid: HashMap<(i32, i32), Vec<usize>>,
    pub sites: HashMap<Place, Site>,
    pub minimap: Handle<Image>,
    pub building_spots: Vec<(Vec3, f32)>,
    pub dive_spots: Vec<Vec3>,
    pub pier: Rect2,
}

const GRID_CELL: f32 = 32.0;

impl CityMap {
    fn add_collider(&mut self, r: Rect2) {
        let idx = self.colliders.len();
        self.colliders.push(r);
        let (x0, y0) = ((r.min.x / GRID_CELL).floor() as i32, (r.min.y / GRID_CELL).floor() as i32);
        let (x1, y1) = ((r.max.x / GRID_CELL).floor() as i32, (r.max.y / GRID_CELL).floor() as i32);
        for x in x0..=x1 {
            for y in y0..=y1 {
                self.grid.entry((x, y)).or_default().push(idx);
            }
        }
    }

    /// Total push needed to move a circle out of every building it overlaps.
    pub fn collide(&self, p: Vec2, r: f32) -> Option<Vec2> {
        let cx = (p.x / GRID_CELL).floor() as i32;
        let cy = (p.y / GRID_CELL).floor() as i32;
        let mut total = Vec2::ZERO;
        let mut hit = false;
        let mut seen: [usize; 32] = [usize::MAX; 32];
        let mut n = 0;
        for x in cx - 1..=cx + 1 {
            for y in cy - 1..=cy + 1 {
                if let Some(list) = self.grid.get(&(x, y)) {
                    for &i in list {
                        if seen[..n].contains(&i) {
                            continue;
                        }
                        if n < 32 {
                            seen[n] = i;
                            n += 1;
                        }
                        if let Some(push) = self.colliders[i].push_circle(p + total, r) {
                            total += push;
                            hit = true;
                        }
                    }
                }
            }
        }
        let mut out = p + total;
        // Invisible world borders; the sea stays open to the east.
        out.y = out.y.clamp(-WORLD_LIMIT, WORLD_LIMIT);
        out.x = out.x.clamp(-WORLD_LIMIT, SEA_LIMIT);
        if out != p + total {
            hit = true;
        }
        hit.then_some(out - p)
    }

    pub fn ground_height(&self, p: Vec2) -> f32 {
        if p.x > BEACH_END {
            return -6.0;
        }
        if self.pier.contains(p) {
            return 0.6;
        }
        if lot_at(p).is_some() {
            CURB
        } else {
            0.0
        }
    }

    pub fn in_water(&self, p: Vec2) -> bool {
        p.x > BEACH_END && !self.pier.contains(p)
    }

    /// A random point on a sidewalk right next to the road, facing the road.
    pub fn random_curb_point(&self, rng: &mut (impl Rng + ?Sized)) -> (Vec3, Vec3) {
        loop {
            let lot = &self.lots[rng.gen_range(0..self.lots.len())];
            if matches!(lot.kind, LotKind::Beachfront) {
                continue;
            }
            let side = rng.gen_range(0..4);
            let t = rng.gen_range(0.2..0.8);
            let r = lot.rect;
            let (p, road_dir) = match side {
                0 => (Vec2::new(r.min.x + 1.2, r.min.y + (r.max.y - r.min.y) * t), Vec2::NEG_X),
                1 => (Vec2::new(r.max.x - 1.2, r.min.y + (r.max.y - r.min.y) * t), Vec2::X),
                2 => (Vec2::new(r.min.x + (r.max.x - r.min.x) * t, r.min.y + 1.2), Vec2::NEG_Y),
                _ => (Vec2::new(r.min.x + (r.max.x - r.min.x) * t, r.max.y - 1.2), Vec2::Y),
            };
            let road = p + road_dir * (1.2 + LANE * 1.4);
            if road.x.abs() > HALF + 2.0 || road.y.abs() > HALF + 2.0 {
                continue;
            }
            return (Vec3::new(p.x, CURB, p.y), Vec3::new(road.x, 0.0, road.y));
        }
    }
}

pub fn road_coord(i: i32) -> f32 {
    -HALF + i as f32 * BLOCK
}

fn lot_rect(i: i32, j: i32) -> Rect2 {
    let x0 = road_coord(i) + ROAD * 0.5;
    let z0 = road_coord(j) + ROAD * 0.5;
    Rect2::new(Vec2::new(x0, z0), Vec2::new(x0 + BLOCK - ROAD, z0 + BLOCK - ROAD))
}

pub fn lot_at(p: Vec2) -> Option<(i32, i32)> {
    let i = ((p.x + HALF) / BLOCK).floor() as i32;
    let j = ((p.y + HALF) / BLOCK).floor() as i32;
    if !(0..N).contains(&i) || !(0..N).contains(&j) {
        return None;
    }
    lot_rect(i, j).contains(p).then_some((i, j))
}

/// Materials whose glow follows the time of day.
#[derive(Resource, Default)]
pub struct NightGlow {
    pub windows: Vec<(Handle<StandardMaterial>, LinearRgba)>,
    pub lamps: Vec<(Handle<StandardMaterial>, LinearRgba)>,
}

#[derive(Resource, Clone)]
pub struct SharedMeshes {
    pub cube: Handle<Mesh>,
    pub cylinder: Handle<Mesh>,
    pub sphere: Handle<Mesh>,
    pub capsule: Handle<Mesh>,
    pub ring: Handle<Mesh>,
}

pub struct CityPlugin;

impl Plugin for CityPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<NightGlow>()
            .add_systems(PreStartup, (setup_shared_meshes, build_city).chain());
    }
}

fn setup_shared_meshes(mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>) {
    commands.insert_resource(SharedMeshes {
        cube: meshes.add(Cuboid::new(1.0, 1.0, 1.0)),
        cylinder: meshes.add(Cylinder::new(0.5, 1.0).mesh().resolution(14)),
        sphere: meshes.add(Sphere::new(0.5).mesh().ico(2).unwrap()),
        capsule: meshes.add(Capsule3d::new(0.5, 1.0).mesh().rings(2).latitudes(8).longitudes(10)),
        ring: meshes.add(Annulus::new(0.85, 1.0).mesh().resolution(32)),
    });
}

// ---------------------------------------------------------------- textures --

#[derive(Clone, Copy)]
enum Facade {
    Glass,
    Panel,
    Brick,
    Modern,
    Stucco,
}

const CELL: u32 = 32;
const CELLS: u32 = 8;

fn facade_textures(kind: Facade, seed: u32) -> (Image, Image) {
    let size = CELL * CELLS;
    let lit = |cx: u32, cy: u32| -> Option<[u8; 3]> {
        let h = hash2(cx as i32, cy as i32, seed + 17);
        if h < 0.38 {
            let t = hash2(cx as i32, cy as i32, seed + 99);
            Some(if t < 0.7 { [255, 214, 150] } else if t < 0.9 { [220, 235, 255] } else { [255, 170, 110] })
        } else {
            None
        }
    };
    // (window x0, x1, y0, y1) inside a cell.
    let win = match kind {
        Facade::Glass => (2, 30, 3, 29),
        Facade::Panel => (9, 23, 8, 24),
        Facade::Brick => (10, 22, 7, 24),
        Facade::Modern => (5, 27, 6, 25),
        Facade::Stucco => (11, 21, 9, 22),
    };
    let in_win = |x: u32, y: u32| x >= win.0 && x < win.1 && y >= win.2 && y < win.3;
    let base = make_texture(size, |x, y| {
        let cx = x / CELL;
        let (lx, ly) = (x % CELL, y % CELL);
        let n = value_noise(x as f32 * 0.15, y as f32 * 0.15, seed);
        let fine = hash2(x as i32, y as i32, seed);
        if in_win(lx, ly) {
            let refl = 0.55 + 0.45 * value_noise(x as f32 * 0.03 + cx as f32, y as f32 * 0.05, seed + 5);
            let sky = (ly as f32 - win.2 as f32) / (win.3 - win.2) as f32;
            let r = (40.0 + 50.0 * refl * (1.0 - sky)) as u8;
            let g = (55.0 + 65.0 * refl * (1.0 - sky)) as u8;
            let b = (75.0 + 85.0 * refl) as u8;
            if matches!(kind, Facade::Glass) && (lx == win.0 || ly == win.2) {
                return [70, 80, 90, 255];
            }
            return [r, g, b, 255];
        }
        // Frames around windows.
        let fx = lx + 1 >= win.0 && lx <= win.1 && ly + 1 >= win.2 && ly <= win.3;
        match kind {
            Facade::Glass => {
                let v = (150.0 + 30.0 * n) as u8;
                [v, v + 5, v + 12, 255]
            }
            Facade::Panel => {
                if fx {
                    return [235, 235, 230, 255];
                }
                let seam = lx == 0 || ly == 0;
                let v = if seam { 150.0 } else { 205.0 + 25.0 * n - 10.0 * fine } as u8;
                [v, v, (v as f32 * 0.96) as u8, 255]
            }
            Facade::Brick => {
                if fx {
                    return [230, 225, 215, 255];
                }
                let row = y / 4;
                let off = if row % 2 == 0 { 0 } else { 4 };
                let mortar = y % 4 == 0 || (x + off) % 8 == 0;
                if mortar {
                    [190, 180, 170, 255]
                } else {
                    let v = 0.75 + 0.25 * hash2(((x + off) / 8) as i32, row as i32, seed) + 0.1 * n;
                    [(170.0 * v) as u8, (80.0 * v) as u8, (60.0 * v) as u8, 255]
                }
            }
            Facade::Modern => {
                if fx {
                    return [60, 60, 66, 255];
                }
                let v = (225.0 + 20.0 * n) as u8;
                [v, v, v, 255]
            }
            Facade::Stucco => {
                if fx {
                    return [245, 240, 230, 255];
                }
                let v = (215.0 + 30.0 * n + 10.0 * fine) as u8;
                [v, v, (v as f32 * 0.93) as u8, 255]
            }
        }
    });
    let glow = make_texture(size, |x, y| {
        let (cx, cy) = (x / CELL, y / CELL);
        let (lx, ly) = (x % CELL, y % CELL);
        if in_win(lx, ly) {
            if let Some(c) = lit(cx, cy) {
                let fade = 0.75 + 0.25 * (1.0 - (ly as f32 - win.2 as f32) / (win.3 - win.2) as f32);
                return [(c[0] as f32 * fade) as u8, (c[1] as f32 * fade) as u8, (c[2] as f32 * fade) as u8, 255];
            }
        }
        [0, 0, 0, 255]
    });
    (base, glow)
}

fn noise_texture(seed: u32, base: [f32; 3], var: f32, scale: f32, extra: impl Fn(u32, u32, f32) -> f32) -> Image {
    make_texture(256, |x, y| {
        let n = value_noise(x as f32 * scale, y as f32 * scale, seed) * 0.6
            + value_noise(x as f32 * scale * 4.0, y as f32 * scale * 4.0, seed + 1) * 0.3
            + hash2(x as i32, y as i32, seed + 2) * 0.1;
        let k = 1.0 + (n - 0.5) * var + extra(x, y, n);
        [
            (base[0] * k).clamp(0.0, 255.0) as u8,
            (base[1] * k).clamp(0.0, 255.0) as u8,
            (base[2] * k).clamp(0.0, 255.0) as u8,
            255,
        ]
    })
}

// ------------------------------------------------------------------- build --

struct Buckets {
    map: HashMap<(i32, usize), GeoBuilder>,
}

impl Buckets {
    fn get(&mut self, chunk: i32, mat: usize) -> &mut GeoBuilder {
        self.map.entry((chunk, mat)).or_default()
    }
}

fn chunk_of(p: Vec2) -> i32 {
    let i = (((p.x + HALF) / BLOCK) as i32 / CHUNK).clamp(-1, N / CHUNK + 2);
    let j = (((p.y + HALF) / BLOCK) as i32 / CHUNK).clamp(-1, N / CHUNK + 2);
    i * 16 + j
}

fn build_city(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
    mut glow: ResMut<NightGlow>,
    shared: Res<SharedMeshes>,
) {
    let mut rng = SmallRng::seed_from_u64(1337);

    // ---------------------------------------------------- material palette
    let mut mats: Vec<Handle<StandardMaterial>> = Vec::new();
    let mut add_mat = |m: StandardMaterial, mats: &mut Vec<Handle<StandardMaterial>>| {
        mats.push(materials.add(m));
        mats.len() - 1
    };

    let asphalt_tex = images.add(noise_texture(3, [62.0, 64.0, 68.0], 0.35, 0.05, |_, _, _| 0.0));
    let sidewalk_tex = images.add(noise_texture(4, [168.0, 165.0, 158.0], 0.18, 0.08, |x, y, _| {
        if x % 64 < 2 || y % 64 < 2 { -0.25 } else { 0.0 }
    }));
    let grass_tex = images.add(noise_texture(5, [78.0, 122.0, 58.0], 0.45, 0.04, |_, _, _| 0.0));
    let sand_tex = images.add(noise_texture(6, [214.0, 196.0, 150.0], 0.2, 0.06, |_, _, _| 0.0));
    let plaza_tex = images.add(noise_texture(7, [190.0, 182.0, 170.0], 0.15, 0.1, |x, y, _| {
        if (x / 32 + y / 32) % 2 == 0 { -0.08 } else { 0.0 }
    }));
    let roof_tex = images.add(noise_texture(8, [96.0, 96.0, 100.0], 0.3, 0.07, |_, _, _| 0.0));

    let m_asphalt = add_mat(
        StandardMaterial {
            base_color_texture: Some(asphalt_tex),
            perceptual_roughness: 0.92,
            reflectance: 0.3,
            ..default()
        },
        &mut mats,
    );
    let m_sidewalk = add_mat(
        StandardMaterial { base_color_texture: Some(sidewalk_tex), perceptual_roughness: 0.9, ..default() },
        &mut mats,
    );
    let m_grass = add_mat(
        StandardMaterial { base_color_texture: Some(grass_tex), perceptual_roughness: 1.0, reflectance: 0.2, ..default() },
        &mut mats,
    );
    let m_sand = add_mat(
        StandardMaterial { base_color_texture: Some(sand_tex), perceptual_roughness: 1.0, ..default() },
        &mut mats,
    );
    let m_plaza = add_mat(
        StandardMaterial { base_color_texture: Some(plaza_tex), perceptual_roughness: 0.8, ..default() },
        &mut mats,
    );
    let m_roof = add_mat(
        StandardMaterial { base_color_texture: Some(roof_tex), perceptual_roughness: 0.95, ..default() },
        &mut mats,
    );
    let m_white_paint = add_mat(
        StandardMaterial { base_color: Color::srgb(0.92, 0.92, 0.9), perceptual_roughness: 0.6, ..default() },
        &mut mats,
    );
    let m_yellow_paint = add_mat(
        StandardMaterial { base_color: Color::srgb(0.95, 0.75, 0.15), perceptual_roughness: 0.6, ..default() },
        &mut mats,
    );
    let m_metal = add_mat(
        StandardMaterial { base_color: Color::srgb(0.22, 0.23, 0.25), metallic: 0.8, perceptual_roughness: 0.4, ..default() },
        &mut mats,
    );
    let m_wood = add_mat(
        StandardMaterial { base_color: Color::srgb(0.45, 0.32, 0.2), perceptual_roughness: 0.85, ..default() },
        &mut mats,
    );
    let lamp_glow = LinearRgba::rgb(14.0, 10.0, 6.0);
    let m_lamp = add_mat(
        StandardMaterial { base_color: Color::srgb(1.0, 0.95, 0.85), emissive: LinearRgba::BLACK, ..default() },
        &mut mats,
    );
    glow.lamps.push((mats[m_lamp].clone(), lamp_glow));

    // Facade materials: (facade, tints)
    let facade_sets: [(Facade, &[u32], f32, f32); 5] = [
        (Facade::Glass, &[0x9fb6c8, 0x8fa39a, 0xb8c2d6, 0x7f93a8], 0.12, 0.5),
        (Facade::Panel, &[0xffffff, 0xe8e2d0, 0xd6e0e8, 0xf0d8c8], 0.85, 0.0),
        (Facade::Brick, &[0xffffff, 0xd8c0b0, 0xc8a890], 0.9, 0.0),
        (Facade::Modern, &[0xffffff, 0xf2e3c4, 0xc9e6dc, 0xe8c8c8, 0xc8d4f0], 0.7, 0.0),
        (Facade::Stucco, &[0xffffff, 0xf6e7b8, 0xe6c3a0, 0xc8e0c0, 0xe8d0e8, 0xbfd8e8], 0.9, 0.0),
    ];
    let mut facade_mats: Vec<Vec<usize>> = Vec::new();
    for (si, (kind, tints, rough, metal)) in facade_sets.iter().enumerate() {
        let (base, em) = facade_textures(*kind, 100 + si as u32 * 31);
        let base = images.add(base);
        let em = images.add(em);
        let mut list = Vec::new();
        for &t in tints.iter() {
            let h = materials.add(StandardMaterial {
                base_color: srgb(t),
                base_color_texture: Some(base.clone()),
                emissive_texture: Some(em.clone()),
                emissive: LinearRgba::BLACK,
                perceptual_roughness: *rough,
                metallic: *metal,
                reflectance: if matches!(kind, Facade::Glass) { 0.7 } else { 0.4 },
                ..default()
            });
            glow.windows.push((h.clone(), LinearRgba::rgb(2.4, 2.4, 2.4)));
            mats.push(h);
            list.push(mats.len() - 1);
        }
        facade_mats.push(list);
    }
    let facade_uv = [Vec2::new(3.4, 3.6), Vec2::new(3.2, 2.9), Vec2::new(3.0, 3.1), Vec2::new(3.6, 3.3), Vec2::new(2.8, 3.0)];

    let mut place_mats: HashMap<Place, usize> = HashMap::new();
    for p in Place::ALL {
        let c = p.color().to_linear();
        let h = materials.add(StandardMaterial {
            base_color: p.color(),
            emissive: LinearRgba::rgb(c.red * 1.5, c.green * 1.5, c.blue * 1.5),
            perceptual_roughness: 0.4,
            ..default()
        });
        mats.push(h);
        place_mats.insert(p, mats.len() - 1);
    }

    let mut b = Buckets { map: HashMap::new() };
    let mut map = CityMap {
        lots: Vec::new(),
        colliders: Vec::new(),
        grid: HashMap::new(),
        sites: HashMap::new(),
        minimap: Handle::default(),
        building_spots: Vec::new(),
        dive_spots: Vec::new(),
        pier: Rect2::new(Vec2::new(BEACH_END - 4.0, 50.0), Vec2::new(BEACH_END + 70.0, 60.0)),
    };

    // ------------------------------------------------------------- ground
    {
        let g = b.get(99, m_grass);
        g.ground_quad(Vec2::new(-HALF - 140.0, -HALF - 140.0), Vec2::new(HALF + 8.0, HALF + 140.0), -0.02, 12.0);
        let s = b.get(99, m_sand);
        s.ground_quad(Vec2::new(HALF + 7.0, -HALF - 140.0), Vec2::new(BEACH_END, HALF + 140.0), -0.01, 10.0);
        // Shore drop into the sea and the sea bed.
        s.face(
            Vec3::new(BEACH_END, -3.0, 0.0),
            Vec3::NEG_Z * (HALF + 140.0),
            Vec3::Y * 3.0,
            Vec2::ZERO,
            Vec2::new(60.0, 1.0),
        );
        s.ground_quad(Vec2::new(BEACH_END, -HALF - 400.0), Vec2::new(HALF + 900.0, HALF + 400.0), -6.0, 14.0);
    }
    // Roads: one strip per grid line, overlapping at intersections.
    for i in 0..=N {
        let c = road_coord(i);
        let len_min = -HALF - ROAD * 0.5;
        let len_max = HALF + ROAD * 0.5;
        for k in 0..N {
            let a = road_coord(k) - ROAD * 0.5;
            let e = road_coord(k + 1) + ROAD * 0.5;
            let chunk_x = chunk_of(Vec2::new(c, (a + e) * 0.5));
            b.get(chunk_x, m_asphalt).ground_quad(Vec2::new(c - ROAD * 0.5, a), Vec2::new(c + ROAD * 0.5, e), 0.0, 9.0);
            let chunk_z = chunk_of(Vec2::new((a + e) * 0.5, c));
            b.get(chunk_z, m_asphalt).ground_quad(Vec2::new(a, c - ROAD * 0.5), Vec2::new(e, c + ROAD * 0.5), 0.0, 9.0);
        }
        let _ = (len_min, len_max);
    }
    // Lane markings between intersections.
    for i in 0..=N {
        for k in 0..N {
            let c = road_coord(i);
            let a = road_coord(k) + ROAD * 0.5;
            let e = road_coord(k + 1) - ROAD * 0.5;
            for vertical in [true, false] {
                let to = |along: f32, across: f32| if vertical { Vec2::new(c + across, along) } else { Vec2::new(along, c + across) };
                let chunk = chunk_of(to((a + e) * 0.5, 0.0));
                let rect = |p0: Vec2, p1: Vec2| (p0.min(p1), p0.max(p1));
                // Double yellow centre line.
                for off in [-0.18, 0.18] {
                    let (mn, mx) = rect(to(a + 4.5, off - 0.06), to(e - 4.5, off + 0.06));
                    b.get(chunk, m_yellow_paint).ground_quad(mn, mx, 0.012, 4.0);
                }
                // Dashed lane separators.
                for side in [-LANE, LANE] {
                    let mut t = a + 6.0;
                    while t + 3.0 < e - 6.0 {
                        let (mn, mx) = rect(to(t, side - 0.07), to(t + 3.0, side + 0.07));
                        b.get(chunk, m_white_paint).ground_quad(mn, mx, 0.012, 4.0);
                        t += 7.0;
                    }
                }
                // Zebra crossings and stop lines at both ends.
                for (start, dir) in [(a, 1.0f32), (e, -1.0f32)] {
                    let mut s = -ROAD * 0.5 + 0.8;
                    while s < ROAD * 0.5 - 0.8 {
                        let (mn, mx) = rect(to(start + dir * 0.6, s), to(start + dir * 3.4, s + 0.55));
                        b.get(chunk, m_white_paint).ground_quad(mn, mx, 0.012, 4.0);
                        s += 1.1;
                    }
                    let (mn, mx) = rect(to(start + dir * 4.0, 0.0), to(start + dir * 4.35, dir * ROAD * 0.5 - dir * 0.4));
                    b.get(chunk, m_white_paint).ground_quad(mn, mx, 0.012, 4.0);
                }
            }
        }
    }

    // --------------------------------------------------------------- lots
    let special_at: HashMap<(i32, i32), Place> = Place::ALL.iter().map(|p| (p.lot(), *p)).collect();
    let mut trees: Vec<(Vec3, f32, bool)> = Vec::new();
    let mut lamps: Vec<(Vec3, f32)> = Vec::new();
    let mut bins: Vec<Vec3> = Vec::new();

    for i in 0..N {
        for j in 0..N {
            let rect = lot_rect(i, j);
            let cx = i as f32 - (N as f32 - 1.0) * 0.5;
            let cz = j as f32 - (N as f32 - 1.0) * 0.5;
            let d = (cx * cx + cz * cz).sqrt();
            let kind = if let Some(p) = special_at.get(&(i, j)) {
                LotKind::Special(*p)
            } else if i == N - 1 {
                if rng.gen_bool(0.5) { LotKind::Beachfront } else { LotKind::Park }
            } else if d < 2.3 {
                LotKind::Downtown
            } else if rng.gen_bool(0.1) {
                LotKind::Park
            } else if d < 4.6 {
                LotKind::Midrise
            } else {
                LotKind::Houses
            };
            map.lots.push(Lot { i, j, rect, kind });
            let chunk = chunk_of(rect.center());

            // Raised lot with curb.
            let lot_c = rect.center();
            let lot_size = rect.max - rect.min;
            {
                let m = b.get(chunk, m_sidewalk);
                m.box_walls(Vec3::new(lot_c.x, CURB * 0.5, lot_c.y), Vec3::new(lot_size.x, CURB, lot_size.y), Vec2::splat(3.0), 0.0);
                // Sidewalk ring (4 strips).
                let inner_min = rect.min + Vec2::splat(SIDEWALK);
                let inner_max = rect.max - Vec2::splat(SIDEWALK);
                m.ground_quad(rect.min, Vec2::new(rect.max.x, inner_min.y), CURB, 3.2);
                m.ground_quad(Vec2::new(rect.min.x, inner_max.y), rect.max, CURB, 3.2);
                m.ground_quad(Vec2::new(rect.min.x, inner_min.y), Vec2::new(inner_min.x, inner_max.y), CURB, 3.2);
                m.ground_quad(Vec2::new(inner_max.x, inner_min.y), Vec2::new(rect.max.x, inner_max.y), CURB, 3.2);
            }
            let inner = Rect2::new(rect.min + Vec2::splat(SIDEWALK), rect.max - Vec2::splat(SIDEWALK));
            let inner_mat = match kind {
                LotKind::Park | LotKind::Houses => m_grass,
                LotKind::Beachfront => m_sand,
                _ => m_plaza,
            };
            b.get(chunk, inner_mat).ground_quad(inner.min, inner.max, CURB + 0.005, 6.0);

            // Street lamps along the curb.
            for t in [0.15, 0.5, 0.85] {
                let lx = rect.min.x + lot_size.x * t;
                let lz = rect.min.y + lot_size.y * t;
                lamps.push((Vec3::new(lx, CURB, rect.min.y + 0.6), 0.0));
                lamps.push((Vec3::new(lx, CURB, rect.max.y - 0.6), std::f32::consts::PI));
                lamps.push((Vec3::new(rect.min.x + 0.6, CURB, lz), std::f32::consts::FRAC_PI_2));
                lamps.push((Vec3::new(rect.max.x - 0.6, CURB, lz), -std::f32::consts::FRAC_PI_2));
            }
            if rng.gen_bool(0.5) {
                bins.push(Vec3::new(rect.min.x + 2.0, CURB, rect.min.y + 1.6));
            }

            let building = |b: &mut Buckets, map: &mut CityMap, rng: &mut SmallRng, foot: Rect2, h: f32, facade: usize| {
                let size = foot.max - foot.min;
                let c = foot.center();
                let mat = facade_mats[facade][rng.gen_range(0..facade_mats[facade].len())];
                let center = Vec3::new(c.x, CURB + h * 0.5, c.y);
                let full = Vec3::new(size.x, h, size.y);
                b.get(chunk, mat).box_walls(center, full, facade_uv[facade] * CELLS as f32, rng.gen_range(0.0..8.0));
                let roof = b.get(chunk, m_roof);
                roof.box_top(center, full, 6.0);
                // Parapet and roof equipment.
                let top = CURB + h;
                roof.box_walls(Vec3::new(c.x, top + 0.4, c.y), Vec3::new(size.x + 0.3, 0.8, size.y + 0.3), Vec2::splat(4.0), 0.0);
                roof.box_top(Vec3::new(c.x, top + 0.4, c.y), Vec3::new(size.x + 0.3, 0.8, size.y + 0.3), 6.0);
                for _ in 0..rng.gen_range(1..4) {
                    let s = Vec3::new(rng.gen_range(1.5..4.0), rng.gen_range(1.0..2.5), rng.gen_range(1.5..4.0));
                    let p = Vec3::new(
                        c.x + rng.gen_range(-0.3..0.3) * size.x,
                        top + 0.8 + s.y * 0.5,
                        c.y + rng.gen_range(-0.3..0.3) * size.y,
                    );
                    roof.solid_box(p, s, 3.0);
                }
                map.add_collider(Rect2::new(foot.min - Vec2::splat(0.1), foot.max + Vec2::splat(0.1)));
                map.building_spots.push((Vec3::new(c.x, CURB, c.y), size.x.min(size.y) * 0.5));
            };

            match kind {
                LotKind::Downtown => {
                    let count = rng.gen_range(1..=2);
                    for k in 0..count {
                        let (mn, mx) = if count == 1 {
                            (inner.min + Vec2::splat(2.0), inner.max - Vec2::splat(2.0))
                        } else if k == 0 {
                            (inner.min + Vec2::splat(1.5), Vec2::new(inner.center().x - 1.5, inner.max.y - 1.5))
                        } else {
                            (Vec2::new(inner.center().x + 1.5, inner.min.y + 1.5), inner.max - Vec2::splat(1.5))
                        };
                        let shrink = rng.gen_range(0.0..3.0);
                        let foot = Rect2::new(mn + Vec2::splat(shrink), mx - Vec2::splat(shrink));
                        let h = rng.gen_range(42.0..118.0) * (1.25 - d * 0.12);
                        let facade = if rng.gen_bool(0.75) { 0 } else { 3 };
                        building(&mut b, &mut map, &mut rng, foot, h, facade);
                        // Setback crown on tall towers.
                        if h > 70.0 {
                            let c = foot.center();
                            let s = (foot.max - foot.min) * 0.6;
                            let ch = rng.gen_range(8.0..20.0);
                            let mat = facade_mats[0][rng.gen_range(0..facade_mats[0].len())];
                            let center = Vec3::new(c.x, CURB + h + 0.8 + ch * 0.5, c.y);
                            b.get(chunk, mat).box_walls(center, Vec3::new(s.x, ch, s.y), facade_uv[0] * CELLS as f32, 1.0);
                            b.get(chunk, m_roof).box_top(center, Vec3::new(s.x, ch, s.y), 6.0);
                            b.get(chunk, m_metal).solid_box(center + Vec3::Y * (ch * 0.5 + 4.0), Vec3::new(0.3, 8.0, 0.3), 2.0);
                        }
                    }
                }
                LotKind::Midrise => {
                    let split_x = rng.gen_bool(0.5);
                    let parts = rng.gen_range(1..=3);
                    for k in 0..parts {
                        let t0 = k as f32 / parts as f32;
                        let t1 = (k + 1) as f32 / parts as f32;
                        let sz = inner.max - inner.min;
                        let (mn, mx) = if split_x {
                            (Vec2::new(inner.min.x + sz.x * t0 + 1.2, inner.min.y + 1.5), Vec2::new(inner.min.x + sz.x * t1 - 1.2, inner.max.y - 1.5))
                        } else {
                            (Vec2::new(inner.min.x + 1.5, inner.min.y + sz.y * t0 + 1.2), Vec2::new(inner.max.x - 1.5, inner.min.y + sz.y * t1 - 1.2))
                        };
                        let facade = [1, 1, 2, 3][rng.gen_range(0..4)];
                        let h = rng.gen_range(11.0..36.0);
                        building(&mut b, &mut map, &mut rng, Rect2::new(mn, mx), h, facade);
                    }
                }
                LotKind::Houses => {
                    let sz = inner.max - inner.min;
                    for qx in 0..2 {
                        for qz in 0..2 {
                            let cell_min = inner.min + Vec2::new(sz.x * qx as f32 * 0.5, sz.y * qz as f32 * 0.5);
                            let cell_size = sz * 0.5;
                            let w = rng.gen_range(8.0..13.0);
                            let dpt = rng.gen_range(8.0..12.0);
                            let c = cell_min + cell_size * 0.5;
                            let foot = Rect2::new(c - Vec2::new(w, dpt) * 0.5, c + Vec2::new(w, dpt) * 0.5);
                            let h = rng.gen_range(4.0..9.5);
                            building(&mut b, &mut map, &mut rng, foot, h, 4);
                            trees.push((Vec3::new(cell_min.x + 2.5, CURB, cell_min.y + 2.5), rng.gen_range(0.8..1.3), false));
                        }
                    }
                }
                LotKind::Park => {
                    for _ in 0..rng.gen_range(10..18) {
                        let p = Vec2::new(rng.gen_range(inner.min.x + 2.0..inner.max.x - 2.0), rng.gen_range(inner.min.y + 2.0..inner.max.y - 2.0));
                        trees.push((Vec3::new(p.x, CURB, p.y), rng.gen_range(0.8..1.5), false));
                    }
                    // Paths and benches.
                    let c = inner.center();
                    b.get(chunk, m_plaza).ground_quad(Vec2::new(inner.min.x, c.y - 1.5), Vec2::new(inner.max.x, c.y + 1.5), CURB + 0.01, 4.0);
                    b.get(chunk, m_plaza).ground_quad(Vec2::new(c.x - 1.5, inner.min.y), Vec2::new(c.x + 1.5, inner.max.y), CURB + 0.01, 4.0);
                    for k in 0..4 {
                        let a = k as f32 * std::f32::consts::FRAC_PI_2;
                        let p = c + Vec2::new(a.cos(), a.sin()) * 8.0;
                        b.get(chunk, m_wood).solid_box(Vec3::new(p.x, CURB + 0.45, p.y), Vec3::new(1.8, 0.12, 0.6), 2.0);
                    }
                    b.get(chunk, m_white_paint).solid_box(Vec3::new(c.x, CURB + 0.5, c.y), Vec3::new(4.0, 1.0, 4.0), 2.0);
                    map.add_collider(Rect2::new(c - Vec2::splat(2.0), c + Vec2::splat(2.0)));
                }
                LotKind::Beachfront => {
                    for _ in 0..rng.gen_range(5..9) {
                        let p = Vec2::new(rng.gen_range(inner.min.x + 2.0..inner.max.x - 2.0), rng.gen_range(inner.min.y + 2.0..inner.max.y - 2.0));
                        trees.push((Vec3::new(p.x, CURB, p.y), rng.gen_range(0.9..1.3), true));
                    }
                    let c = inner.center();
                    b.get(chunk, m_wood).solid_box(Vec3::new(c.x, CURB + 1.4, c.y), Vec3::new(8.0, 2.8, 5.0), 2.0);
                    b.get(chunk, m_roof).solid_box(Vec3::new(c.x, CURB + 3.0, c.y), Vec3::new(9.5, 0.3, 6.5), 3.0);
                    map.add_collider(Rect2::new(c - Vec2::new(4.0, 2.5), c + Vec2::new(4.0, 2.5)));
                }
                LotKind::Special(place) => {
                    // Main building set back from the street, with a sign band and canopy.
                    let foot = Rect2::new(inner.min + Vec2::new(4.0, 4.0), inner.max - Vec2::new(4.0, 9.0));
                    let h = match place {
                        Place::Government | Place::Fsb | Place::Bank | Place::Hospital => rng.gen_range(22.0..34.0),
                        Place::Casino => 26.0,
                        Place::OpgGarage | Place::WasteYard | Place::TruckDepot | Place::BusDepot | Place::AutoService => 8.0,
                        _ => rng.gen_range(10.0..16.0),
                    };
                    let facade = match place {
                        Place::Casino | Place::Bank | Place::CarShop | Place::NewsAgency | Place::Fsb => 0,
                        Place::Government | Place::Hospital => 1,
                        Place::OpgGarage | Place::FireStation | Place::WasteYard => 2,
                        _ => 3,
                    };
                    building(&mut b, &mut map, &mut rng, foot, h, facade);
                    let pm = place_mats[&place];
                    let c = foot.center();
                    let fs = foot.max - foot.min;
                    b.get(chunk, pm).box_walls(
                        Vec3::new(c.x, CURB + h * 0.5 + 0.8, c.y),
                        Vec3::new(fs.x + 0.25, 1.2, fs.y + 0.25),
                        Vec2::splat(4.0),
                        0.0,
                    );
                    // Entrance canopy facing +Z street.
                    let door = Vec2::new(c.x, foot.max.y + 0.5);
                    b.get(chunk, pm).solid_box(Vec3::new(door.x, CURB + 3.4, door.y + 1.2), Vec3::new(6.0, 0.3, 3.0), 2.0);
                    b.get(chunk, m_metal).solid_box(Vec3::new(door.x - 2.8, CURB + 1.7, door.y + 2.5), Vec3::new(0.2, 3.4, 0.2), 1.0);
                    b.get(chunk, m_metal).solid_box(Vec3::new(door.x + 2.8, CURB + 1.7, door.y + 2.5), Vec3::new(0.2, 3.4, 0.2), 1.0);
                    let door_pos = Vec3::new(door.x, CURB, door.y + 2.0);
                    let curb = Vec3::new(door.x + 6.0, 0.0, rect.max.y + LANE * 1.4);
                    map.sites.insert(place, Site { place, door: door_pos, curb, curb_yaw: -std::f32::consts::FRAC_PI_2 });
                    // A couple of trees in front.
                    trees.push((Vec3::new(inner.min.x + 3.0, CURB, inner.max.y - 3.0), 1.0, false));
                    trees.push((Vec3::new(inner.max.x - 3.0, CURB, inner.max.y - 3.0), 1.0, false));
                }
            }
        }
    }

    // Pier for the diving station.
    {
        let pier = map.pier;
        let c = pier.center();
        let sz = pier.max - pier.min;
        b.get(99, m_wood).solid_box(Vec3::new(c.x, 0.3, c.y), Vec3::new(sz.x, 0.6, sz.y), 2.0);
        let mut x = pier.min.x + 4.0;
        while x < pier.max.x {
            for z in [pier.min.y + 0.4, pier.max.y - 0.4] {
                b.get(99, m_wood).solid_box(Vec3::new(x, -2.5, z), Vec3::new(0.4, 6.0, 0.4), 2.0);
            }
            x += 6.0;
        }
        for k in 0..12 {
            let a = k as f32 * 0.55;
            map.dive_spots.push(Vec3::new(BEACH_END + 30.0 + (k as f32 * 13.0) % 120.0, -5.4, -260.0 + k as f32 * 46.0 + a.sin() * 10.0));
        }
    }

    // Street lamp geometry (merged poles, glowing heads).
    for (p, yaw) in &lamps {
        let chunk = chunk_of(xz(*p));
        let arm_dir = Quat::from_rotation_y(*yaw) * Vec3::Z;
        b.get(chunk, m_metal).solid_box(*p + Vec3::Y * 3.6, Vec3::new(0.16, 7.2, 0.16), 1.0);
        let arm_c = *p + Vec3::Y * 7.1 - arm_dir * 0.9;
        let arm_size = if arm_dir.x.abs() > 0.5 { Vec3::new(1.8, 0.12, 0.12) } else { Vec3::new(0.12, 0.12, 1.8) };
        b.get(chunk, m_metal).solid_box(arm_c, arm_size, 1.0);
        let head = *p + Vec3::Y * 6.95 - arm_dir * 1.7;
        b.get(chunk, m_lamp).solid_box(head, Vec3::new(0.5, 0.12, 0.5), 1.0);
    }
    for p in &bins {
        let chunk = chunk_of(xz(*p));
        b.get(chunk, m_metal).solid_box(*p + Vec3::Y * 0.5, Vec3::new(0.7, 1.0, 0.7), 1.0);
    }

    // Spawn merged meshes.
    let city_root = commands.spawn((Name::new("City"), Transform::default(), Visibility::default())).id();
    for ((_, mat), builder) in b.map {
        if builder.is_empty() {
            continue;
        }
        let mesh = meshes.add(builder.build());
        let child = commands.spawn((Mesh3d(mesh), MeshMaterial3d(mats[mat].clone()))).id();
        commands.entity(city_root).add_child(child);
    }

    // Trees and palms (instanced: same mesh + material for all).
    let trunk_mat = materials.add(StandardMaterial { base_color: srgb(0x5a4030), perceptual_roughness: 0.95, ..default() });
    let leaf_mats = [0x3f7a2e, 0x4f8a34, 0x356b2a, 0x5f9a3a].map(|c| {
        materials.add(StandardMaterial { base_color: srgb(c), perceptual_roughness: 0.9, ..default() })
    });
    let palm_leaf = materials.add(StandardMaterial { base_color: srgb(0x4c9a3c), perceptual_roughness: 0.8, ..default() });
    for (k, (p, s, palm)) in trees.iter().enumerate() {
        let s = *s;
        if *palm {
            let lean = Quat::from_rotation_z(0.12 * (k as f32).sin()) * Quat::from_rotation_x(0.1 * (k as f32 * 1.7).cos());
            let tree = commands
                .spawn((Transform::from_translation(*p).with_rotation(lean), Visibility::default()))
                .with_children(|c| {
                    c.spawn((
                        Mesh3d(shared.cylinder.clone()),
                        MeshMaterial3d(trunk_mat.clone()),
                        Transform::from_xyz(0.0, 4.5 * s, 0.0).with_scale(Vec3::new(0.35, 9.0 * s, 0.35)),
                    ));
                    for f in 0..6 {
                        let a = f as f32 * std::f32::consts::TAU / 6.0;
                        c.spawn((
                            Mesh3d(shared.sphere.clone()),
                            MeshMaterial3d(palm_leaf.clone()),
                            Transform::from_xyz(a.cos() * 1.6, 8.8 * s, a.sin() * 1.6)
                                .with_rotation(Quat::from_rotation_y(-a) * Quat::from_rotation_z(-0.35))
                                .with_scale(Vec3::new(3.6, 0.18, 0.9)),
                        ));
                    }
                })
                .id();
            commands.entity(city_root).add_child(tree);
        } else {
            let leaf = leaf_mats[k % leaf_mats.len()].clone();
            let tree = commands
                .spawn((Transform::from_translation(*p), Visibility::default()))
                .with_children(|c| {
                    c.spawn((
                        Mesh3d(shared.cylinder.clone()),
                        MeshMaterial3d(trunk_mat.clone()),
                        Transform::from_xyz(0.0, 1.6 * s, 0.0).with_scale(Vec3::new(0.32, 3.2 * s, 0.32)),
                    ));
                    c.spawn((
                        Mesh3d(shared.sphere.clone()),
                        MeshMaterial3d(leaf.clone()),
                        Transform::from_xyz(0.0, 4.4 * s, 0.0).with_scale(Vec3::new(3.8, 3.4, 3.8) * s),
                    ));
                    c.spawn((
                        Mesh3d(shared.sphere.clone()),
                        MeshMaterial3d(leaf),
                        Transform::from_xyz(0.6 * s, 5.6 * s, 0.3 * s).with_scale(Vec3::new(2.6, 2.4, 2.6) * s),
                    ));
                })
                .id();
            commands.entity(city_root).add_child(tree);
        }
        map.add_collider(Rect2::new(xz(*p) - Vec2::splat(0.3), xz(*p) + Vec2::splat(0.3)));
    }

    // Sea surface.
    let water = materials.add(StandardMaterial {
        base_color: Color::srgba(0.05, 0.28, 0.38, 0.82),
        perceptual_roughness: 0.06,
        reflectance: 0.6,
        alpha_mode: AlphaMode::Blend,
        ..default()
    });
    let mut wb = GeoBuilder::default();
    wb.ground_quad(Vec2::new(HALF + 7.0, -HALF - 1200.0), Vec2::new(HALF + 2400.0, HALF + 1200.0), WATER_LEVEL, 20.0);
    commands.spawn((Name::new("Sea"), Mesh3d(meshes.add(wb.build())), MeshMaterial3d(water)));

    // Minimap image.
    map.minimap = images.add(render_minimap(&map));
    commands.insert_resource(map);
}

pub const MINIMAP_PX: u32 = 256;

fn render_minimap(map: &CityMap) -> Image {
    let mut data = Vec::with_capacity((MINIMAP_PX * MINIMAP_PX * 4) as usize);
    for py in 0..MINIMAP_PX {
        for px in 0..MINIMAP_PX {
            let p = Vec2::new(
                -MAP_EXT + (px as f32 + 0.5) / MINIMAP_PX as f32 * MAP_EXT * 2.0,
                -MAP_EXT + (py as f32 + 0.5) / MINIMAP_PX as f32 * MAP_EXT * 2.0,
            );
            let c: [u8; 3] = if p.x > BEACH_END {
                [28, 88, 120]
            } else if p.x > HALF + 7.0 {
                [196, 180, 132]
            } else if p.x.abs() > HALF + 7.0 || p.y.abs() > HALF + 7.0 {
                [58, 86, 52]
            } else if let Some((i, j)) = lot_at(p) {
                let lot = &map.lots[(i * N + j) as usize];
                match lot.kind {
                    LotKind::Park | LotKind::Houses => [70, 104, 62],
                    LotKind::Beachfront => [190, 176, 130],
                    LotKind::Special(pl) => {
                        let s = pl.color().to_srgba();
                        [(s.red * 200.0) as u8, (s.green * 200.0) as u8, (s.blue * 200.0) as u8]
                    }
                    _ => [92, 96, 104],
                }
            } else {
                [40, 42, 48]
            };
            let covered = map.colliders.iter().any(|r| r.contains(p) && (r.max.x - r.min.x) > 2.0);
            let c = if covered { c.map(|v| v.saturating_add(26)) } else { c };
            data.extend_from_slice(&[c[0], c[1], c[2], 235]);
        }
    }
    Image::new(
        Extent3d { width: MINIMAP_PX, height: MINIMAP_PX, depth_or_array_layers: 1 },
        TextureDimension::D2,
        data,
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::RENDER_WORLD,
    )
}
