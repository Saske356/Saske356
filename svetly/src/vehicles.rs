//! Vehicles: a catalogue of 360 generated models across ten body classes,
//! paints and service liveries, model assembly from parts, and arcade physics.

use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, PI};

use bevy::prelude::*;
use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};

use crate::city::{CityMap, NightGlow, SharedMeshes, WATER_LEVEL};
use crate::input::Controls;
use crate::util::*;

#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum BodyClass {
    Sedan,
    Hatch,
    Wagon,
    Coupe,
    Sport,
    Suv,
    Pickup,
    Van,
    Truck,
    Bus,
}

impl BodyClass {
    pub const ALL: [BodyClass; 10] = [
        BodyClass::Sedan,
        BodyClass::Hatch,
        BodyClass::Wagon,
        BodyClass::Coupe,
        BodyClass::Sport,
        BodyClass::Suv,
        BodyClass::Pickup,
        BodyClass::Van,
        BodyClass::Truck,
        BodyClass::Bus,
    ];
    pub fn title(self) -> &'static str {
        match self {
            BodyClass::Sedan => "Седан",
            BodyClass::Hatch => "Хэтчбек",
            BodyClass::Wagon => "Универсал",
            BodyClass::Coupe => "Купе",
            BodyClass::Sport => "Спорткар",
            BodyClass::Suv => "Внедорожник",
            BodyClass::Pickup => "Пикап",
            BodyClass::Van => "Фургон",
            BodyClass::Truck => "Грузовик",
            BodyClass::Bus => "Автобус",
        }
    }
}

#[derive(Clone, Debug)]
pub struct VehicleSpec {
    pub id: usize,
    pub name: String,
    pub class: BodyClass,
    pub length: f32,
    pub width: f32,
    pub body_h: f32,
    pub cabin_h: f32,
    pub cabin_len: f32,
    pub cabin_off: f32,
    pub clearance: f32,
    pub wheel_r: f32,
    pub wheelbase: f32,
    pub spoiler: bool,
    pub roof_rack: bool,
    pub max_speed: f32,
    pub accel: f32,
    pub grip: f32,
    pub steer: f32,
    pub price: u32,
}

impl VehicleSpec {
    pub fn kmh(&self) -> u32 {
        (self.max_speed * 3.6).round() as u32
    }
    pub fn radius(&self) -> f32 {
        self.width * 0.55
    }
}

const BRANDS: [&str; 12] = [
    "Борей", "Зарево", "Кайра", "Нордис", "Ольхон", "Тавра", "Велес", "Сирин", "Радон", "Альтаир", "Ирбис", "Стерх",
];
const MODELS: [&str; 30] = [
    "Стриж", "Ирис", "Кречет", "Вихрь", "Мираж", "Аргон", "Полюс", "Квант", "Лидер", "Скиф", "Прима", "Фрегат",
    "Гранит", "Тайга", "Пилигрим", "Орион", "Дельта", "Сигма", "Комета", "Метеор", "Атлас", "Рубеж", "Форпост",
    "Титан", "Бриз", "Шторм", "Эфир", "Неон", "Пульс", "Рысь",
];
const TRIMS: [&str; 12] = ["", " Люкс", " GT", " 2.0", " Турбо", " Комфорт", " Спорт", " 4x4", " Классик", " Про", " RS", " Макс"];

#[derive(Resource)]
pub struct Catalog {
    pub specs: Vec<VehicleSpec>,
}

impl Catalog {
    pub fn generate() -> Self {
        let mut rng = SmallRng::seed_from_u64(777);
        let mut specs = Vec::with_capacity(360);
        let mut used = std::collections::HashSet::new();
        for (ci, class) in BodyClass::ALL.iter().enumerate() {
            for k in 0..36 {
                let j = |a: f32, b: f32, rng: &mut SmallRng| rng.gen_range(a..b);
                let (len, wid, bh, ch, cl, coff, clr, wr, vmax, acc, grip, price) = match class {
                    BodyClass::Sedan => (j(4.3, 4.9, &mut rng), j(1.75, 1.9, &mut rng), j(0.62, 0.72, &mut rng), j(0.55, 0.66, &mut rng), j(0.42, 0.5, &mut rng), j(-0.08, 0.0, &mut rng), 0.18, j(0.32, 0.36, &mut rng), j(46.0, 58.0, &mut rng), j(6.0, 8.5, &mut rng), j(0.8, 0.95, &mut rng), 18_000),
                    BodyClass::Hatch => (j(3.7, 4.2, &mut rng), j(1.65, 1.8, &mut rng), j(0.62, 0.7, &mut rng), j(0.6, 0.7, &mut rng), j(0.55, 0.62, &mut rng), j(-0.18, -0.1, &mut rng), 0.17, j(0.3, 0.34, &mut rng), j(42.0, 52.0, &mut rng), j(6.0, 8.0, &mut rng), j(0.85, 0.98, &mut rng), 11_000),
                    BodyClass::Wagon => (j(4.5, 5.0, &mut rng), j(1.78, 1.9, &mut rng), j(0.64, 0.72, &mut rng), j(0.58, 0.66, &mut rng), j(0.6, 0.68, &mut rng), j(-0.2, -0.14, &mut rng), 0.19, j(0.33, 0.36, &mut rng), j(44.0, 54.0, &mut rng), j(5.5, 7.5, &mut rng), j(0.8, 0.9, &mut rng), 16_000),
                    BodyClass::Coupe => (j(4.2, 4.7, &mut rng), j(1.8, 1.92, &mut rng), j(0.56, 0.64, &mut rng), j(0.46, 0.54, &mut rng), j(0.36, 0.42, &mut rng), j(-0.1, -0.02, &mut rng), 0.14, j(0.33, 0.37, &mut rng), j(55.0, 68.0, &mut rng), j(8.5, 11.0, &mut rng), j(0.9, 1.0, &mut rng), 42_000),
                    BodyClass::Sport => (j(4.3, 4.7, &mut rng), j(1.9, 2.02, &mut rng), j(0.5, 0.56, &mut rng), j(0.38, 0.46, &mut rng), j(0.32, 0.38, &mut rng), j(-0.06, 0.04, &mut rng), 0.11, j(0.34, 0.38, &mut rng), j(72.0, 92.0, &mut rng), j(11.0, 15.0, &mut rng), j(0.95, 1.1, &mut rng), 160_000),
                    BodyClass::Suv => (j(4.6, 5.1, &mut rng), j(1.9, 2.05, &mut rng), j(0.85, 0.98, &mut rng), j(0.66, 0.78, &mut rng), j(0.6, 0.68, &mut rng), j(-0.16, -0.08, &mut rng), 0.3, j(0.4, 0.45, &mut rng), j(44.0, 58.0, &mut rng), j(6.5, 9.0, &mut rng), j(0.75, 0.88, &mut rng), 48_000),
                    BodyClass::Pickup => (j(5.0, 5.6, &mut rng), j(1.9, 2.05, &mut rng), j(0.85, 0.98, &mut rng), j(0.68, 0.78, &mut rng), j(0.32, 0.4, &mut rng), j(0.08, 0.16, &mut rng), 0.32, j(0.4, 0.46, &mut rng), j(42.0, 54.0, &mut rng), j(6.0, 8.0, &mut rng), j(0.72, 0.85, &mut rng), 34_000),
                    BodyClass::Van => (j(4.9, 5.8, &mut rng), j(1.95, 2.1, &mut rng), j(0.9, 1.05, &mut rng), j(1.0, 1.25, &mut rng), j(0.8, 0.86, &mut rng), j(-0.08, -0.04, &mut rng), 0.22, j(0.36, 0.4, &mut rng), j(36.0, 44.0, &mut rng), j(4.5, 6.0, &mut rng), j(0.7, 0.8, &mut rng), 26_000),
                    BodyClass::Truck => (j(7.5, 9.0, &mut rng), j(2.35, 2.5, &mut rng), j(1.1, 1.3, &mut rng), j(1.2, 1.4, &mut rng), j(0.2, 0.24, &mut rng), j(0.36, 0.4, &mut rng), 0.45, j(0.5, 0.56, &mut rng), j(28.0, 36.0, &mut rng), j(3.0, 4.2, &mut rng), j(0.6, 0.7, &mut rng), 70_000),
                    BodyClass::Bus => (j(10.5, 12.0, &mut rng), j(2.5, 2.55, &mut rng), j(1.0, 1.1, &mut rng), j(1.5, 1.7, &mut rng), j(0.94, 0.97, &mut rng), 0.0, 0.3, j(0.5, 0.55, &mut rng), j(24.0, 30.0, &mut rng), j(2.5, 3.4, &mut rng), j(0.6, 0.7, &mut rng), 90_000),
                };
                let mut name;
                loop {
                    let brand = BRANDS[(ci * 5 + k + rng.gen_range(0..12)) % BRANDS.len()];
                    let model = MODELS[rng.gen_range(0..MODELS.len())];
                    let trim = TRIMS[rng.gen_range(0..TRIMS.len())];
                    name = format!("{brand} {model}{trim}");
                    if used.insert(name.clone()) {
                        break;
                    }
                }
                let quality = vmax / 50.0 * acc / 7.0;
                specs.push(VehicleSpec {
                    id: specs.len(),
                    name,
                    class: *class,
                    length: len,
                    width: wid,
                    body_h: bh,
                    cabin_h: ch,
                    cabin_len: cl,
                    cabin_off: coff,
                    clearance: clr,
                    wheel_r: wr,
                    wheelbase: len * if matches!(class, BodyClass::Bus) { 0.62 } else { 0.6 },
                    spoiler: matches!(class, BodyClass::Sport | BodyClass::Coupe) && rng.gen_bool(0.55),
                    roof_rack: matches!(class, BodyClass::Suv | BodyClass::Wagon) && rng.gen_bool(0.4),
                    max_speed: vmax,
                    accel: acc,
                    grip,
                    steer: if matches!(class, BodyClass::Bus | BodyClass::Truck) { 0.55 } else { 0.62 },
                    price: ((price as f32 * quality * rng.gen_range(0.85..1.2)) / 100.0).round() as u32 * 100,
                });
            }
        }
        Catalog { specs }
    }

    pub fn first_of(&self, class: BodyClass) -> usize {
        self.specs.iter().position(|s| s.class == class).unwrap_or(0)
    }

    pub fn random_civil(&self, rng: &mut impl Rng) -> usize {
        loop {
            let i = rng.gen_range(0..self.specs.len());
            let c = self.specs[i].class;
            let ok = match c {
                BodyClass::Bus | BodyClass::Truck => rng.gen_bool(0.15),
                BodyClass::Sport => rng.gen_bool(0.35),
                _ => true,
            };
            if ok {
                return i;
            }
        }
    }
}

// ------------------------------------------------------------------ paints --

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Finish {
    Gloss,
    Metallic,
    Matte,
    Pearl,
    Chrome,
}

#[derive(Clone, Debug)]
pub struct Paint {
    pub name: String,
    pub color: Color,
    pub finish: Finish,
    pub stripe: Option<Color>,
}

pub fn paints() -> Vec<Paint> {
    let base: [(&str, u32); 26] = [
        ("Белый", 0xf2f2f0),
        ("Чёрный", 0x101114),
        ("Серебро", 0xb8bcc2),
        ("Графит", 0x45484e),
        ("Красный", 0xc4161c),
        ("Вишня", 0x6a0f1e),
        ("Синий", 0x1d4fb8),
        ("Ночное небо", 0x101c3a),
        ("Бирюза", 0x1a9c9a),
        ("Изумруд", 0x0f6b3e),
        ("Хаки", 0x6b6a45),
        ("Песок", 0xc9b48a),
        ("Оранжевый", 0xf06a10),
        ("Жёлтый", 0xf2c21a),
        ("Лайм", 0x8fd11a),
        ("Фиолетовый", 0x5a2a9a),
        ("Розовый", 0xf06aa8),
        ("Бронза", 0x8a5a2a),
        ("Небесный", 0x7ab8e8),
        ("Мокрый асфальт", 0x2e3238),
        ("Слоновая кость", 0xe8dcc0),
        ("Бордо", 0x4a0f18),
        ("Мята", 0x9fe0c4),
        ("Кофе", 0x4a3426),
        ("Сталь", 0x6a7a8a),
        ("Золото", 0xc8a040),
    ];
    let mut out = Vec::new();
    for (name, c) in base {
        out.push(Paint { name: format!("{name} глянец"), color: srgb(c), finish: Finish::Gloss, stripe: None });
    }
    for (name, c) in base.iter().step_by(2) {
        out.push(Paint { name: format!("{name} металлик"), color: srgb(*c), finish: Finish::Metallic, stripe: None });
    }
    for (name, c) in base.iter().skip(1).step_by(3) {
        out.push(Paint { name: format!("{name} мат"), color: srgb(*c), finish: Finish::Matte, stripe: None });
    }
    for (name, c) in base.iter().step_by(4) {
        out.push(Paint { name: format!("{name} перламутр"), color: srgb(*c), finish: Finish::Pearl, stripe: None });
    }
    out.push(Paint { name: "Хром".into(), color: srgb(0xd8dde2), finish: Finish::Chrome, stripe: None });
    out.push(Paint { name: "Золотой хром".into(), color: srgb(0xd8b060), finish: Finish::Chrome, stripe: None });
    let stripes = [(0xf2f2f0, 0x101114), (0x101114, 0xc4161c), (0x1d4fb8, 0xf2f2f0), (0xf2c21a, 0x101114), (0xc4161c, 0xf2f2f0), (0x0f6b3e, 0xc8a040), (0x5a2a9a, 0x3dffb4), (0xf06a10, 0x101114)];
    for (a, s) in stripes {
        out.push(Paint { name: "Гоночные полосы".into(), color: srgb(a), finish: Finish::Gloss, stripe: Some(srgb(s)) });
    }
    out
}

/// Service liveries for job vehicles.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash, Default)]
pub enum Livery {
    #[default]
    None,
    Taxi,
    Police,
    Fire,
    Ambulance,
    Bus,
    Cash,
    News,
    Courier,
    Gov,
    Fsb,
    Garbage,
    Service,
    Dive,
    Cargo,
}

impl Livery {
    fn colors(self) -> Option<(Color, Option<Color>)> {
        Some(match self {
            Livery::None => return None,
            Livery::Taxi => (srgb(0xf2c21a), Some(srgb(0x101114))),
            Livery::Police => (srgb(0xf2f2f0), Some(srgb(0x1d4fb8))),
            Livery::Fire => (srgb(0xc4161c), Some(srgb(0xf2f2f0))),
            Livery::Ambulance => (srgb(0xf2f2f0), Some(srgb(0xd0202a))),
            Livery::Bus => (srgb(0xf2f2f0), Some(srgb(0x2fb35a))),
            Livery::Cash => (srgb(0x2a4a3a), Some(srgb(0xc8a040))),
            Livery::News => (srgb(0x5a2a9a), Some(srgb(0xf2f2f0))),
            Livery::Courier => (srgb(0xf06a10), Some(srgb(0xf2f2f0))),
            Livery::Gov => (srgb(0x101114), None),
            Livery::Fsb => (srgb(0x2e3238), None),
            Livery::Garbage => (srgb(0x6a8a2a), Some(srgb(0xf2c21a))),
            Livery::Service => (srgb(0x6a7a8a), Some(srgb(0xf06a10))),
            Livery::Dive => (srgb(0x22a8e8), Some(srgb(0xf2f2f0))),
            Livery::Cargo => (srgb(0x9a6a3a), Some(srgb(0xf2f2f0))),
        })
    }
    fn beacons(self) -> Option<(Color, Color)> {
        match self {
            Livery::Police | Livery::Fsb => Some((srgb(0x1d4fff), srgb(0xff2020))),
            Livery::Fire | Livery::Ambulance => Some((srgb(0xff2020), srgb(0x1d4fff))),
            Livery::Service | Livery::Garbage | Livery::Cash => Some((srgb(0xff9a10), srgb(0xff9a10))),
            _ => None,
        }
    }
}

// ------------------------------------------------------------- components --

#[derive(Component)]
pub struct Vehicle {
    pub spec: usize,
    pub paint: usize,
    pub livery: Livery,
    pub speed: f32,
    pub vel: Vec2,
    pub yaw: f32,
    pub steer: f32,
    pub radius: f32,
    pub half_len: f32,
    pub sinking: f32,
}

/// The car the player is driving.
#[derive(Component)]
pub struct Driven;

#[derive(Component)]
pub struct Wheel {
    pub front: bool,
    pub radius: f32,
    pub spin: f32,
    pub left: bool,
}

#[derive(Component)]
pub struct Beacon {
    pub phase: f32,
}

#[derive(Component)]
pub struct Headlight;

#[derive(Resource)]
pub struct VehicleAssets {
    pub glass: Handle<StandardMaterial>,
    pub tire: Handle<StandardMaterial>,
    pub rim: Handle<StandardMaterial>,
    pub trim: Handle<StandardMaterial>,
    pub head: Handle<StandardMaterial>,
    pub tail: Handle<StandardMaterial>,
    pub interior: Handle<StandardMaterial>,
    pub beacon_mats: HashMap<u32, Handle<StandardMaterial>>,
    pub paint_mats: HashMap<(usize, u8), Handle<StandardMaterial>>,
    pub paints: Vec<Paint>,
    pub wheel_mesh: Handle<Mesh>,
}

impl VehicleAssets {
    fn paint_mat(&mut self, mats: &mut Assets<StandardMaterial>, paint: usize, livery: Livery, secondary: bool) -> Handle<StandardMaterial> {
        let key = (if livery == Livery::None { paint } else { 10_000 + livery as usize }, secondary as u8);
        if let Some(h) = self.paint_mats.get(&key) {
            return h.clone();
        }
        let p = &self.paints[paint.min(self.paints.len() - 1)];
        let (color, finish) = match livery.colors() {
            Some((main, second)) => (if secondary { second.unwrap_or(main) } else { main }, Finish::Gloss),
            None => (if secondary { p.stripe.unwrap_or(p.color) } else { p.color }, p.finish),
        };
        let m = match finish {
            Finish::Gloss => StandardMaterial { base_color: color, metallic: 0.1, perceptual_roughness: 0.22, clearcoat: 1.0, clearcoat_perceptual_roughness: 0.05, ..default() },
            Finish::Metallic => StandardMaterial { base_color: color, metallic: 0.75, perceptual_roughness: 0.3, clearcoat: 1.0, clearcoat_perceptual_roughness: 0.04, ..default() },
            Finish::Matte => StandardMaterial { base_color: color, metallic: 0.05, perceptual_roughness: 0.75, ..default() },
            Finish::Pearl => StandardMaterial { base_color: color, metallic: 0.45, perceptual_roughness: 0.18, clearcoat: 1.0, clearcoat_perceptual_roughness: 0.02, reflectance: 0.8, ..default() },
            Finish::Chrome => StandardMaterial { base_color: color, metallic: 1.0, perceptual_roughness: 0.06, ..default() },
        };
        let h = mats.add(m);
        self.paint_mats.insert(key, h.clone());
        h
    }

    fn beacon(&mut self, mats: &mut Assets<StandardMaterial>, color: Color) -> Handle<StandardMaterial> {
        let s = color.to_srgba();
        let key = ((s.red * 255.0) as u32) << 16 | ((s.green * 255.0) as u32) << 8 | (s.blue * 255.0) as u32;
        self.beacon_mats
            .entry(key)
            .or_insert_with(|| {
                let l = color.to_linear();
                mats.add(StandardMaterial { base_color: color, emissive: LinearRgba::rgb(l.red * 30.0, l.green * 30.0, l.blue * 30.0), ..default() })
            })
            .clone()
    }
}

pub struct VehiclePlugin;

impl Plugin for VehiclePlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Catalog::generate())
            .add_systems(PreStartup, setup_assets)
            .add_systems(
                Update,
                (drive_player_car, collide_vehicles, place_vehicles, animate_wheels, flash_beacons)
                    .chain()
                    .in_set(crate::GameSet::Physics),
            );
    }
}

fn setup_assets(
    mut commands: Commands,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut glow: ResMut<NightGlow>,
) {
    let head = mats.add(StandardMaterial { base_color: Color::srgb(1.0, 0.98, 0.9), emissive: LinearRgba::rgb(2.0, 2.0, 1.8), ..default() });
    glow.lamps.push((head.clone(), LinearRgba::rgb(40.0, 38.0, 32.0)));
    let tail = mats.add(StandardMaterial { base_color: Color::srgb(0.8, 0.05, 0.05), emissive: LinearRgba::rgb(1.5, 0.05, 0.05), ..default() });
    glow.lamps.push((tail.clone(), LinearRgba::rgb(14.0, 0.3, 0.3)));
    commands.insert_resource(VehicleAssets {
        glass: mats.add(StandardMaterial {
            base_color: Color::srgb(0.015, 0.02, 0.03),
            perceptual_roughness: 0.08,
            metallic: 0.0,
            reflectance: 0.45,
            ..default()
        }),
        tire: mats.add(StandardMaterial { base_color: Color::srgb(0.05, 0.05, 0.055), perceptual_roughness: 0.9, ..default() }),
        rim: mats.add(StandardMaterial { base_color: Color::srgb(0.75, 0.77, 0.8), metallic: 1.0, perceptual_roughness: 0.25, ..default() }),
        trim: mats.add(StandardMaterial { base_color: Color::srgb(0.06, 0.06, 0.07), perceptual_roughness: 0.6, ..default() }),
        interior: mats.add(StandardMaterial { base_color: Color::srgb(0.12, 0.1, 0.09), perceptual_roughness: 0.9, ..default() }),
        head,
        tail,
        beacon_mats: HashMap::new(),
        paint_mats: HashMap::new(),
        paints: paints(),
        wheel_mesh: meshes.add(Cylinder::new(1.0, 1.0).mesh().resolution(16)),
    });
}

/// Builds a complete vehicle entity from its catalogue entry.
#[allow(clippy::too_many_arguments)]
pub fn spawn_vehicle(
    commands: &mut Commands,
    va: &mut VehicleAssets,
    mats: &mut Assets<StandardMaterial>,
    shared: &SharedMeshes,
    catalog: &Catalog,
    spec_id: usize,
    paint: usize,
    livery: Livery,
    pos: Vec3,
    yaw: f32,
) -> Entity {
    let s = catalog.specs[spec_id].clone();
    let body = va.paint_mat(mats, paint, livery, false);
    let second = va.paint_mat(mats, paint, livery, true);
    let cube = shared.cube.clone();
    let l = s.length;
    let w = s.width;
    let base_y = s.clearance + s.body_h * 0.5;
    let top_y = s.clearance + s.body_h;

    let root = commands
        .spawn((
            Name::new(s.name.clone()),
            Transform::from_translation(pos).with_rotation(Quat::from_rotation_y(yaw)),
            Visibility::default(),
            Vehicle {
                spec: spec_id,
                paint,
                livery,
                speed: 0.0,
                vel: Vec2::ZERO,
                yaw,
                steer: 0.0,
                radius: s.radius(),
                half_len: l * 0.5,
                sinking: 0.0,
            },
        ))
        .id();

    let mut parts: Vec<(Handle<Mesh>, Handle<StandardMaterial>, Transform)> = Vec::new();
    let mut slabs: Vec<(Handle<StandardMaterial>, Transform)> = Vec::new();
    let mut boxp = |mat: &Handle<StandardMaterial>, c: Vec3, size: Vec3| {
        parts.push((cube.clone(), mat.clone(), Transform::from_translation(c).with_scale(size)));
    };

    match s.class {
        BodyClass::Truck => {
            // Cab at the front (-Z is forward), cargo box behind.
            let cab_len = 2.2;
            let cab_z = -l * 0.5 + cab_len * 0.5;
            boxp(&body, Vec3::new(0.0, base_y + 0.1, cab_z), Vec3::new(w, s.body_h + 0.2, cab_len));
            boxp(&body, Vec3::new(0.0, top_y + s.cabin_h * 0.5, cab_z + 0.15), Vec3::new(w - 0.05, s.cabin_h, cab_len - 0.3));
            boxp(&va.glass, Vec3::new(0.0, top_y + s.cabin_h * 0.55, cab_z - cab_len * 0.5 + 0.12), Vec3::new(w - 0.2, s.cabin_h * 0.7, 0.06));
            boxp(&va.glass, Vec3::new(0.0, top_y + s.cabin_h * 0.6, cab_z + 0.15), Vec3::new(w + 0.02, s.cabin_h * 0.5, cab_len * 0.6));
            let cargo_len = l - cab_len - 0.3;
            let cargo_z = l * 0.5 - cargo_len * 0.5;
            boxp(&va.trim, Vec3::new(0.0, s.clearance + 0.25, cargo_z), Vec3::new(w * 0.8, 0.3, cargo_len));
            boxp(&second, Vec3::new(0.0, s.clearance + 0.4 + 1.4, cargo_z), Vec3::new(w + 0.05, 2.8, cargo_len));
        }
        BodyClass::Bus => {
            boxp(&body, Vec3::new(0.0, base_y, 0.0), Vec3::new(w, s.body_h, l));
            boxp(&va.glass, Vec3::new(0.0, top_y + s.cabin_h * 0.45, 0.0), Vec3::new(w + 0.02, s.cabin_h * 0.7, l * 0.94));
            boxp(&body, Vec3::new(0.0, top_y + s.cabin_h * 0.5, 0.0), Vec3::new(w - 0.04, s.cabin_h, l - 0.04));
            boxp(&second, Vec3::new(0.0, top_y - 0.05, 0.0), Vec3::new(w + 0.03, 0.22, l + 0.02));
            boxp(&body, Vec3::new(0.0, top_y + s.cabin_h + 0.12, 0.0), Vec3::new(w - 0.2, 0.25, l * 0.4));
        }
        _ => {
            // Lower body.
            boxp(&body, Vec3::new(0.0, base_y, 0.0), Vec3::new(w, s.body_h, l));
            // Hood slope and trunk deck for car-like bodies.
            let cabin_l = l * s.cabin_len;
            let cabin_z = s.cabin_off * l;
            let low = matches!(s.class, BodyClass::Sport | BodyClass::Coupe);
            if low {
                boxp(&body, Vec3::new(0.0, top_y - 0.06, -l * 0.36), Vec3::new(w * 0.98, 0.14, l * 0.28));
            }
            // Cabin: glass shell with painted roof and pillars.
            let cabin_y = top_y + s.cabin_h * 0.5;
            let taper = if matches!(s.class, BodyClass::Van | BodyClass::Suv) { 0.04 } else { 0.12 };
            let sloped = !matches!(s.class, BodyClass::Van | BodyClass::Suv);
            let cw = w - taper * 2.0;
            if sloped {
                // Sloped windscreen and rear glass give a car-like silhouette.
                let rake_f = if low { 0.62 } else { 0.42 };
                let rake_r = match s.class {
                    BodyClass::Hatch | BodyClass::Wagon => 0.12,
                    BodyClass::Pickup => 0.08,
                    _ => if low { 0.5 } else { 0.34 },
                };
                let z0 = cabin_z - cabin_l * 0.5;
                let z1 = cabin_z + cabin_l * 0.5;
                let roof_f = z0 + cabin_l * rake_f * 0.5;
                let roof_r = z1 - cabin_l * rake_r * 0.5;
                let roof_y = top_y + s.cabin_h;
                boxp(&va.glass, Vec3::new(0.0, cabin_y, (roof_f + roof_r) * 0.5), Vec3::new(cw, s.cabin_h, roof_r - roof_f));
                boxp(&body, Vec3::new(0.0, roof_y + 0.03, (roof_f + roof_r) * 0.5), Vec3::new(cw - 0.02, 0.07, roof_r - roof_f + 0.04));
                for (a, b) in [(Vec2::new(z0, top_y), Vec2::new(roof_f, roof_y)), (Vec2::new(z1, top_y), Vec2::new(roof_r, roof_y))] {
                    let mid = (a + b) * 0.5;
                    let d = b - a;
                    let len = d.length();
                    let ang = (-d.y).atan2(d.x);
                    let rot = Quat::from_rotation_x(ang);
                    slabs.push((va.glass.clone(), Transform::from_xyz(0.0, mid.y, mid.x).with_rotation(rot).with_scale(Vec3::new(cw, 0.06, len + 0.02))));
                    // Wedge under the slab fills the side.
                    let side_h = (b.y - a.y) * 0.5;
                    slabs.push((va.glass.clone(), Transform::from_xyz(0.0, a.y + side_h * 0.5, mid.x).with_scale(Vec3::new(cw - 0.01, side_h, d.x.abs()))));
                }
                for side in [-1.0, 1.0] {
                    boxp(&body, Vec3::new(side * (cw * 0.5 + 0.005), cabin_y, (roof_f + roof_r) * 0.5), Vec3::new(0.06, s.cabin_h, 0.09));
                }
            } else {
                boxp(&va.glass, Vec3::new(0.0, cabin_y, cabin_z), Vec3::new(cw, s.cabin_h, cabin_l));
                boxp(&body, Vec3::new(0.0, top_y + s.cabin_h + 0.03, cabin_z + cabin_l * 0.04), Vec3::new(cw - 0.04, 0.07, cabin_l * 0.86));
                for side in [-1.0, 1.0] {
                    boxp(&body, Vec3::new(side * (w * 0.5 - taper - 0.02), cabin_y, cabin_z - cabin_l * 0.5 + 0.06), Vec3::new(0.08, s.cabin_h, 0.1));
                    boxp(&body, Vec3::new(side * (w * 0.5 - taper - 0.02), cabin_y, cabin_z + cabin_l * 0.5 - 0.06), Vec3::new(0.08, s.cabin_h, 0.14));
                    boxp(&body, Vec3::new(side * (w * 0.5 - taper - 0.02), cabin_y, cabin_z), Vec3::new(0.09, s.cabin_h, 0.08));
                }
            }
            for side in [-1.0, 1.0] {
                // Side mirrors.
                boxp(&body, Vec3::new(side * (w * 0.5 + 0.08), top_y + 0.12, cabin_z - cabin_l * 0.5 + 0.15), Vec3::new(0.16, 0.1, 0.12));
            }
            if s.class == BodyClass::Pickup {
                let bed_z = cabin_z + cabin_l * 0.5 + (l * 0.5 - cabin_z - cabin_l * 0.5) * 0.5;
                let bed_l = l * 0.5 - cabin_z - cabin_l * 0.5 - 0.1;
                boxp(&va.trim, Vec3::new(0.0, top_y - 0.02, bed_z), Vec3::new(w - 0.2, 0.06, bed_l));
                for side in [-1.0, 1.0] {
                    boxp(&body, Vec3::new(side * (w * 0.5 - 0.05), top_y + 0.18, bed_z), Vec3::new(0.1, 0.36, bed_l));
                }
                boxp(&body, Vec3::new(0.0, top_y + 0.18, l * 0.5 - 0.05), Vec3::new(w, 0.36, 0.1));
            }
            if let Some(_) = va.paints.get(paint).and_then(|p| p.stripe).filter(|_| livery == Livery::None) {
                boxp(&second, Vec3::new(-0.22, top_y + 0.005, 0.0), Vec3::new(0.22, 0.02, l * 0.99));
                boxp(&second, Vec3::new(0.22, top_y + 0.005, 0.0), Vec3::new(0.22, 0.02, l * 0.99));
                boxp(&second, Vec3::new(0.0, top_y + s.cabin_h + 0.07, cabin_z), Vec3::new(0.5, 0.02, cabin_l * 0.8));
            }
            if livery != Livery::None && livery.colors().and_then(|c| c.1).is_some() {
                // Side band.
                boxp(&second, Vec3::new(0.0, base_y + 0.05, 0.0), Vec3::new(w + 0.02, s.body_h * 0.3, l * 0.9));
            }
            if s.spoiler {
                boxp(&va.trim, Vec3::new(0.0, top_y + 0.28, l * 0.5 - 0.2), Vec3::new(w * 0.9, 0.05, 0.3));
                for side in [-1.0, 1.0] {
                    boxp(&va.trim, Vec3::new(side * w * 0.35, top_y + 0.14, l * 0.5 - 0.2), Vec3::new(0.06, 0.26, 0.12));
                }
            }
            if s.roof_rack {
                for side in [-1.0, 1.0] {
                    boxp(&va.trim, Vec3::new(side * (w * 0.5 - taper - 0.12), top_y + s.cabin_h + 0.12, cabin_z), Vec3::new(0.05, 0.06, cabin_l * 0.8));
                }
            }
            match livery {
                Livery::Taxi => boxp(&va.beacon(mats, srgb(0xffd23a)), Vec3::new(0.0, top_y + s.cabin_h + 0.18, cabin_z), Vec3::new(0.55, 0.2, 0.22)),
                Livery::News => {
                    boxp(&va.rim, Vec3::new(0.0, top_y + s.cabin_h + 0.25, cabin_z + 0.3), Vec3::new(0.8, 0.06, 0.8));
                    boxp(&va.trim, Vec3::new(0.0, top_y + s.cabin_h + 0.1, cabin_z + 0.3), Vec3::new(0.1, 0.25, 0.1));
                }
                _ => {}
            }
        }
    }
    // Bumpers, grille and lights.
    let lamp_y = s.clearance + s.body_h * 0.68;
    boxp(&va.trim, Vec3::new(0.0, s.clearance + 0.12, -l * 0.5 - 0.04), Vec3::new(w * 1.01, 0.22, 0.12));
    boxp(&va.trim, Vec3::new(0.0, s.clearance + 0.12, l * 0.5 + 0.04), Vec3::new(w * 1.01, 0.22, 0.12));
    boxp(&va.trim, Vec3::new(0.0, lamp_y - 0.08, -l * 0.5 - 0.01), Vec3::new(w * 0.4, s.body_h * 0.3, 0.04));
    for side in [-1.0, 1.0] {
        boxp(&va.head, Vec3::new(side * w * 0.36, lamp_y, -l * 0.5 - 0.01), Vec3::new(w * 0.2, 0.11, 0.04));
        boxp(&va.tail, Vec3::new(side * w * 0.38, lamp_y, l * 0.5 + 0.01), Vec3::new(w * 0.18, 0.1, 0.04));
    }
    // Light bar for emergency services.
    if let Some((a, c)) = livery.beacons() {
        let ma = va.beacon(mats, a);
        let mc = va.beacon(mats, c);
        let y = match s.class {
            BodyClass::Truck => top_y + s.cabin_h + 0.08,
            BodyClass::Bus => top_y + s.cabin_h + 0.1,
            _ => top_y + s.cabin_h + 0.13,
        };
        let z = match s.class {
            BodyClass::Truck => -l * 0.5 + 1.2,
            BodyClass::Bus => -l * 0.4,
            _ => s.cabin_off * l,
        };
        for (side, m, ph) in [(-1.0, ma, 0.0), (1.0, mc, PI)] {
            let e = commands
                .spawn((
                    Mesh3d(cube.clone()),
                    MeshMaterial3d(m),
                    Transform::from_xyz(side * 0.28, y, z).with_scale(Vec3::new(0.5, 0.14, 0.22)),
                    Beacon { phase: ph },
                ))
                .id();
            commands.entity(root).add_child(e);
        }
    }

    for (mat, t) in slabs {
        let e = commands.spawn((Mesh3d(cube.clone()), MeshMaterial3d(mat), t)).id();
        commands.entity(root).add_child(e);
    }
    for (mesh, mat, t) in parts {
        let e = commands.spawn((Mesh3d(mesh), MeshMaterial3d(mat), t)).id();
        commands.entity(root).add_child(e);
    }

    // Wheels: tire + rim, pivoting for steering.
    let axle_f = -s.wheelbase * 0.5;
    let axle_r = s.wheelbase * 0.5;
    let mut axles = vec![(axle_f, true)];
    if matches!(s.class, BodyClass::Truck) {
        axles.push((axle_r - 1.3, false));
    }
    axles.push((axle_r, false));
    for (z, front) in axles {
        for side in [-1.0f32, 1.0] {
            let tire_w = if matches!(s.class, BodyClass::Sport) { 0.3 } else { 0.24 };
            let wheel = commands
                .spawn((
                    Transform::from_xyz(side * (w * 0.5 - tire_w * 0.4), s.wheel_r, z),
                    Visibility::default(),
                    Wheel { front, radius: s.wheel_r, spin: 0.0, left: side < 0.0 },
                ))
                .with_children(|c| {
                    c.spawn((
                        Mesh3d(va.wheel_mesh.clone()),
                        MeshMaterial3d(va.tire.clone()),
                        Transform::from_rotation(Quat::from_rotation_z(FRAC_PI_2)).with_scale(Vec3::new(s.wheel_r, tire_w, s.wheel_r)),
                    ));
                    c.spawn((
                        Mesh3d(va.wheel_mesh.clone()),
                        MeshMaterial3d(va.rim.clone()),
                        Transform::from_xyz(side * 0.02, 0.0, 0.0)
                            .with_rotation(Quat::from_rotation_z(FRAC_PI_2))
                            .with_scale(Vec3::new(s.wheel_r * 0.62, tire_w + 0.01, s.wheel_r * 0.62)),
                    ));
                    // Spoke so rotation is visible.
                    c.spawn((
                        Mesh3d(cube.clone()),
                        MeshMaterial3d(va.trim.clone()),
                        Transform::from_xyz(side * (tire_w * 0.5 + 0.01), 0.0, 0.0).with_scale(Vec3::new(0.02, s.wheel_r * 1.1, 0.08)),
                    ));
                })
                .id();
            commands.entity(root).add_child(wheel);
        }
    }
    root
}

// ----------------------------------------------------------------- physics --

fn drive_player_car(
    time: Res<Time>,
    controls: Res<Controls>,
    catalog: Res<Catalog>,
    map: Res<CityMap>,
    mut q: Query<&mut Vehicle, With<Driven>>,
) {
    let dt = time.delta_secs().min(0.05);
    for mut v in &mut q {
        if v.sinking > 0.0 {
            v.speed = 0.0;
            v.vel = Vec2::ZERO;
            continue;
        }
        let s = &catalog.specs[v.spec];
        let throttle = controls.drive.y;
        let fwd = forward_of(v.yaw);
        let right = Vec2::new(-fwd.y, fwd.x);
        let mut speed = v.vel.dot(fwd);

        if throttle > 0.05 {
            if speed < -0.5 {
                speed += s.accel * 2.2 * throttle * dt;
            } else {
                let fall = 1.0 - (speed / s.max_speed).clamp(0.0, 1.0).powi(2);
                speed += s.accel * throttle * fall.max(0.05) * dt;
            }
        } else if throttle < -0.05 {
            if speed > 0.5 {
                speed += s.accel * 2.6 * throttle * dt;
            } else {
                speed = (speed + s.accel * 0.7 * throttle * dt).max(-s.max_speed * 0.28);
            }
        } else {
            speed -= speed * 0.35 * dt + speed.signum() * 0.6 * dt;
            if speed.abs() < 0.2 {
                speed = 0.0;
            }
        }
        if controls.handbrake {
            speed -= speed.signum() * (6.0 * dt).min(speed.abs());
        }

        // Steering gets gentler at speed.
        let target_steer = controls.drive.x * s.steer * (1.0 - (speed.abs() / s.max_speed) * 0.55);
        v.steer += (target_steer - v.steer) * (8.0 * dt).min(1.0);
        let yaw_rate = speed / s.wheelbase * v.steer.tan();
        v.yaw -= yaw_rate * dt;

        // Lateral grip; the handbrake lets the rear slide.
        let lateral = v.vel.dot(right);
        let grip = if controls.handbrake { 1.2 } else { 9.0 * s.grip };
        let new_lat = lateral * (1.0 - (grip * dt).min(1.0));
        let fwd = forward_of(v.yaw);
        let right = Vec2::new(-fwd.y, fwd.x);
        v.vel = fwd * speed + right * new_lat;
        v.speed = speed;
        let _ = &map;
    }
}

fn collide_vehicles(
    time: Res<Time>,
    map: Res<CityMap>,
    mut driven: Query<(Entity, &mut Vehicle, &mut Transform), With<Driven>>,
    others: Query<(Entity, &Vehicle, &Transform), Without<Driven>>,
) {
    let dt = time.delta_secs().min(0.05);
    for (e, mut v, mut t) in &mut driven {
        let mut p = xz(t.translation) + v.vel * dt;
        // Two circles along the body handle long vehicles.
        let fwd = forward_of(v.yaw);
        let r = v.radius;
        let span = (v.half_len - r).max(0.0);
        let mut hit = false;
        for k in [-1.0, 0.0, 1.0] {
            let c = p + fwd * span * k;
            if let Some(push) = map.collide(c, r) {
                p += push;
                hit = true;
                let n = push.normalize_or_zero();
                let into = v.vel.dot(n);
                if into < 0.0 {
                    v.vel -= n * into * 1.3;
                }
            }
        }
        for (oe, o, ot) in &others {
            if oe == e {
                continue;
            }
            let op = xz(ot.translation);
            let ofwd = forward_of(o.yaw);
            let ospan = (o.half_len - o.radius).max(0.0);
            for k in [-1.0, 0.0, 1.0] {
                for ok in [-1.0, 0.0, 1.0] {
                    let a = p + fwd * span * k;
                    let b = op + ofwd * ospan * ok;
                    let d = a - b;
                    let min = r + o.radius;
                    if d.length_squared() < min * min && d.length_squared() > 1e-4 {
                        let len = d.length();
                        let n = d / len;
                        p += n * (min - len);
                        let into = v.vel.dot(n);
                        if into < 0.0 {
                            v.vel -= n * into * 1.5;
                        }
                        hit = true;
                    }
                }
            }
        }
        if hit {
            v.vel *= 0.97;
        }
        t.translation.x = p.x;
        t.translation.z = p.y;
    }
}

fn place_vehicles(time: Res<Time>, map: Res<CityMap>, mut q: Query<(&mut Vehicle, &mut Transform)>) {
    let dt = time.delta_secs().min(0.05);
    for (mut v, mut t) in &mut q {
        let p = xz(t.translation);
        let ground = if map.in_water(p) {
            v.sinking += dt;
            (WATER_LEVEL - 0.6 - v.sinking * 0.8).max(-5.5)
        } else {
            map.ground_height(p)
        };
        t.translation.y += (ground - t.translation.y) * (12.0 * dt).min(1.0);
        // Slight body roll and pitch from steering and acceleration.
        let roll = (v.steer * v.speed * 0.006).clamp(-0.06, 0.06);
        t.rotation = Quat::from_rotation_y(v.yaw) * Quat::from_rotation_z(roll);
    }
}

fn animate_wheels(
    time: Res<Time>,
    vehicles: Query<&Vehicle>,
    mut wheels: Query<(&mut Wheel, &mut Transform, &ChildOf)>,
) {
    let dt = time.delta_secs().min(0.05);
    for (mut w, mut t, parent) in &mut wheels {
        let Ok(v) = vehicles.get(parent.parent()) else { continue };
        w.spin -= v.speed / w.radius * dt;
        let steer = if w.front { v.steer } else { 0.0 };
        let _ = w.left;
        t.rotation = Quat::from_rotation_y(-steer) * Quat::from_rotation_x(w.spin);
    }
}

fn flash_beacons(time: Res<Time>, mut q: Query<(&Beacon, &mut Transform)>) {
    let t = time.elapsed_secs();
    for (b, mut tr) in &mut q {
        let on = ((t * 9.0 + b.phase).sin() > 0.0) as u8 as f32;
        tr.scale.y = 0.06 + 0.1 * on;
    }
}
