//! People: 400 generated skins, job uniforms, a jointed body built from simple
//! shapes, and a walk cycle.

use std::collections::HashMap;

use bevy::prelude::*;
use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};

use crate::city::SharedMeshes;
use crate::util::srgb;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Headwear {
    None,
    Short,
    Long,
    Bun,
    Cap,
    Beanie,
    Hat,
    Helmet,
    Ushanka,
}

#[derive(Clone, Debug)]
pub struct Skin {
    pub name: String,
    pub skin: Color,
    pub hair: Color,
    pub head: Headwear,
    pub head_color: Color,
    pub shirt: Color,
    pub jacket: Option<Color>,
    pub pants: Color,
    pub shoes: Color,
    pub height: f32,
    pub build: f32,
    pub glasses: bool,
    pub beard: bool,
    pub vest: Option<Color>,
    pub price: u32,
}

const SKIN_TONES: [u32; 7] = [0xf3d2b8, 0xe8bc98, 0xd9a47a, 0xc08860, 0x9a6a46, 0x74492e, 0x4e3020];
const HAIR: [u32; 8] = [0x1a1412, 0x3a2618, 0x6a4424, 0x9a6a3a, 0xd8b070, 0xb84a20, 0x8a8a8a, 0xe8e0d0];
const CLOTH: [u32; 32] = [
    0x101114, 0xf2f2f0, 0x1d3f7a, 0x2a5aa8, 0x7ab8e8, 0xc4161c, 0x6a0f1e, 0x2e6b3a, 0x6b6a45, 0xc9b48a, 0xf06a10,
    0xf2c21a, 0x5a2a9a, 0xf06aa8, 0x45484e, 0x8a8f98, 0x1a9c9a, 0x4a3426, 0x8a5a2a, 0xe8dcc0, 0x22262e, 0x3a4a5a,
    0x9fe0c4, 0xd84a4a, 0x2a2a6a, 0xa8c8e8, 0xe8a8a8, 0x6a8a2a, 0xffffff, 0x303030, 0x0f4b6e, 0xb8b8b0,
];
const FIRST: [&str; 20] = [
    "Артём", "Мира", "Глеб", "Ника", "Тимур", "Ева", "Савва", "Лиза", "Ярослав", "Вера", "Марк", "Злата", "Лев",
    "Алиса", "Рустам", "Дана", "Егор", "Камила", "Влад", "Ульяна",
];
const STYLE: [&str; 16] = [
    "Уличный", "Деловой", "Спортивный", "Ночной", "Курортный", "Байкер", "Студент", "Рыбак", "Турист", "Гонщик",
    "Рэпер", "Модница", "Хипстер", "Работяга", "Ретро", "Северный",
];

#[derive(Resource)]
pub struct Skins {
    pub list: Vec<Skin>,
}

impl Skins {
    pub fn generate() -> Self {
        let mut rng = SmallRng::seed_from_u64(4242);
        let mut list = Vec::with_capacity(400);
        let heads = [
            Headwear::None,
            Headwear::Short,
            Headwear::Short,
            Headwear::Long,
            Headwear::Bun,
            Headwear::Cap,
            Headwear::Beanie,
            Headwear::Hat,
            Headwear::Ushanka,
        ];
        for i in 0..400 {
            let c = |rng: &mut SmallRng| srgb(CLOTH[rng.gen_range(0..CLOTH.len())]);
            let style = STYLE[i % STYLE.len()];
            let head = heads[rng.gen_range(0..heads.len())];
            let beard = rng.gen_bool(0.22);
            let formal = style == "Деловой";
            let shirt = c(&mut rng);
            let skin = Skin {
                name: format!("{style} — {}", FIRST[(i / STYLE.len()) % FIRST.len()]),
                skin: srgb(SKIN_TONES[rng.gen_range(0..SKIN_TONES.len())]),
                hair: srgb(HAIR[rng.gen_range(0..HAIR.len())]),
                head,
                head_color: c(&mut rng),
                shirt,
                jacket: if formal || rng.gen_bool(0.4) { Some(c(&mut rng)) } else { None },
                pants: if formal { srgb(0x22262e) } else { c(&mut rng) },
                shoes: if rng.gen_bool(0.5) { srgb(0x101114) } else { c(&mut rng) },
                height: rng.gen_range(0.92..1.08),
                build: rng.gen_range(0.85..1.2),
                glasses: rng.gen_bool(0.18),
                beard,
                vest: None,
                price: 500 + (rng.gen_range(0..40) * 250),
            };
            list.push(skin);
        }
        Skins { list }
    }
}

/// Uniforms for every job (returned on top of the player's face/hair).
pub fn uniform(job: crate::jobs::JobKind, base: &Skin) -> Skin {
    use crate::jobs::JobKind as J;
    let mut s = base.clone();
    s.jacket = None;
    s.vest = None;
    let (shirt, pants, jacket, head, head_color, vest): (u32, u32, Option<u32>, Headwear, u32, Option<u32>) = match job {
        J::Taxi => (0xf2c21a, 0x22262e, None, Headwear::Cap, 0x101114, None),
        J::Courier => (0xf06a10, 0x303030, None, Headwear::Cap, 0xf06a10, None),
        J::BusDriver => (0xa8c8e8, 0x22262e, Some(0x2e6b3a), base.head, 0x2e6b3a, None),
        J::Trucker => (0x3a4a5a, 0x1d3f7a, None, Headwear::Cap, 0x9a6a3a, None),
        J::CashTransport => (0x2a4a3a, 0x2a4a3a, None, Headwear::Helmet, 0x2a4a3a, Some(0x303030)),
        J::Firefighter => (0x2a2a2a, 0x2a2a2a, Some(0x3a3020), Headwear::Helmet, 0xc4161c, Some(0xf2c21a)),
        J::Medic => (0xf2f2f0, 0xf2f2f0, None, base.head, 0xf2f2f0, Some(0xd0202a)),
        J::TrafficPolice => (0xa8c8e8, 0x1d3f7a, Some(0x1d3f7a), Headwear::Cap, 0x1d3f7a, Some(0xc8f020)),
        J::Fsb => (0xf2f2f0, 0x101114, Some(0x101114), base.head, 0x101114, None),
        J::Journalist => (0xe8dcc0, 0x3a4a5a, Some(0x5a2a9a), base.head, 0x5a2a9a, None),
        J::Diver => (0x101114, 0x101114, None, Headwear::Beanie, 0x22a8e8, Some(0x22a8e8)),
        J::Opg => (0x101114, 0x22262e, Some(0x303030), Headwear::Beanie, 0x101114, None),
        J::Government => (0xf2f2f0, 0x22262e, Some(0x22262e), base.head, 0x22262e, None),
        J::Mechanic => (0x3a4a5a, 0x1d3f7a, None, Headwear::Cap, 0x1d3f7a, None),
        J::Garbage => (0xf06a10, 0x6a8a2a, None, Headwear::Cap, 0x6a8a2a, Some(0xc8f020)),
    };
    s.shirt = srgb(shirt);
    s.pants = srgb(pants);
    s.jacket = jacket.map(srgb);
    s.head = if matches!(head, Headwear::None | Headwear::Short | Headwear::Long | Headwear::Bun) { base.head } else { head };
    s.head_color = srgb(head_color);
    s.vest = vest.map(srgb);
    s.shoes = srgb(0x101114);
    s
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum LimbKind {
    LeftLeg,
    RightLeg,
    LeftArm,
    RightArm,
}

#[derive(Component)]
pub struct Limb(pub LimbKind);

/// Root of a person; `speed` drives the walk cycle.
#[derive(Component, Default)]
pub struct Rig {
    pub phase: f32,
    pub speed: f32,
    pub swimming: bool,
}

#[derive(Resource, Default)]
pub struct ColorMats(HashMap<u32, Handle<StandardMaterial>>);

impl ColorMats {
    pub fn get(&mut self, mats: &mut Assets<StandardMaterial>, c: Color, rough: f32) -> Handle<StandardMaterial> {
        let s = c.to_srgba();
        let key = ((s.red * 255.0) as u32) << 24 | ((s.green * 255.0) as u32) << 16 | ((s.blue * 255.0) as u32) << 8 | (rough * 100.0) as u32;
        self.0
            .entry(key)
            .or_insert_with(|| mats.add(StandardMaterial { base_color: c, perceptual_roughness: rough, ..default() }))
            .clone()
    }
}

/// Spawns body parts as children of `root` (whose origin is at the feet).
pub fn build_body(
    commands: &mut Commands,
    root: Entity,
    skin: &Skin,
    shared: &SharedMeshes,
    cm: &mut ColorMats,
    mats: &mut Assets<StandardMaterial>,
) {
    let cube = shared.cube.clone();
    let cap = shared.capsule.clone();
    let sph = shared.sphere.clone();
    let b = skin.build;
    let m_skin = cm.get(mats, skin.skin, 0.7);
    let m_shirt = cm.get(mats, skin.shirt, 0.85);
    let m_top = cm.get(mats, skin.jacket.unwrap_or(skin.shirt), 0.8);
    let m_pants = cm.get(mats, skin.pants, 0.9);
    let m_shoes = cm.get(mats, skin.shoes, 0.5);
    let m_hair = cm.get(mats, skin.hair, 0.8);
    let m_hat = cm.get(mats, skin.head_color, 0.7);
    let m_dark = cm.get(mats, Color::srgb(0.04, 0.04, 0.05), 0.2);

    let mut kids: Vec<Entity> = Vec::new();
    let part = |commands: &mut Commands, mesh: &Handle<Mesh>, mat: &Handle<StandardMaterial>, t: Transform| {
        commands.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(mat.clone()), t)).id()
    };

    // Torso (shirt), jacket shell, vest.
    kids.push(part(commands, &cube, &m_shirt, Transform::from_xyz(0.0, 1.22, 0.0).with_scale(Vec3::new(0.46 * b, 0.58, 0.24 * b))));
    if skin.jacket.is_some() {
        for side in [-1.0, 1.0] {
            kids.push(part(commands, &cube, &m_top, Transform::from_xyz(side * 0.15 * b, 1.22, 0.0).with_scale(Vec3::new(0.18 * b, 0.6, 0.26 * b))));
        }
        kids.push(part(commands, &cube, &m_top, Transform::from_xyz(0.0, 1.22, 0.02).with_scale(Vec3::new(0.48 * b, 0.6, 0.22 * b))));
    }
    if let Some(v) = skin.vest {
        let m = cm.get(mats, v, 0.6);
        kids.push(part(commands, &cube, &m, Transform::from_xyz(0.0, 1.2, 0.0).with_scale(Vec3::new(0.5 * b, 0.42, 0.28 * b))));
    }
    // Hips.
    kids.push(part(commands, &cube, &m_pants, Transform::from_xyz(0.0, 0.9, 0.0).with_scale(Vec3::new(0.42 * b, 0.16, 0.22 * b))));
    // Neck and head.
    kids.push(part(commands, &cube, &m_skin, Transform::from_xyz(0.0, 1.56, 0.0).with_scale(Vec3::new(0.12, 0.1, 0.12))));
    kids.push(part(commands, &sph, &m_skin, Transform::from_xyz(0.0, 1.72, 0.0).with_scale(Vec3::new(0.24, 0.28, 0.26))));
    // Eyes.
    for side in [-1.0, 1.0] {
        kids.push(part(commands, &sph, &m_dark, Transform::from_xyz(side * 0.05, 1.74, -0.12).with_scale(Vec3::splat(0.035))));
    }
    if skin.glasses {
        kids.push(part(commands, &cube, &m_dark, Transform::from_xyz(0.0, 1.745, -0.125).with_scale(Vec3::new(0.2, 0.05, 0.02))));
    }
    if skin.beard {
        kids.push(part(commands, &sph, &m_hair, Transform::from_xyz(0.0, 1.63, -0.07).with_scale(Vec3::new(0.2, 0.12, 0.14))));
    }
    match skin.head {
        Headwear::None => {}
        Headwear::Short => kids.push(part(commands, &sph, &m_hair, Transform::from_xyz(0.0, 1.79, 0.02).with_scale(Vec3::new(0.26, 0.2, 0.27)))),
        Headwear::Long => {
            kids.push(part(commands, &sph, &m_hair, Transform::from_xyz(0.0, 1.78, 0.03).with_scale(Vec3::new(0.27, 0.22, 0.28))));
            kids.push(part(commands, &cube, &m_hair, Transform::from_xyz(0.0, 1.6, 0.1).with_scale(Vec3::new(0.26, 0.34, 0.08))));
        }
        Headwear::Bun => {
            kids.push(part(commands, &sph, &m_hair, Transform::from_xyz(0.0, 1.79, 0.02).with_scale(Vec3::new(0.26, 0.2, 0.27))));
            kids.push(part(commands, &sph, &m_hair, Transform::from_xyz(0.0, 1.86, 0.11).with_scale(Vec3::splat(0.12))));
        }
        Headwear::Cap => {
            kids.push(part(commands, &sph, &m_hat, Transform::from_xyz(0.0, 1.81, 0.01).with_scale(Vec3::new(0.27, 0.16, 0.28))));
            kids.push(part(commands, &cube, &m_hat, Transform::from_xyz(0.0, 1.8, -0.15).with_scale(Vec3::new(0.2, 0.02, 0.12))));
        }
        Headwear::Beanie => kids.push(part(commands, &sph, &m_hat, Transform::from_xyz(0.0, 1.82, 0.01).with_scale(Vec3::new(0.27, 0.22, 0.28)))),
        Headwear::Hat => {
            kids.push(part(commands, &cube, &m_hat, Transform::from_xyz(0.0, 1.83, 0.0).with_scale(Vec3::new(0.42, 0.02, 0.42))));
            kids.push(part(commands, &cube, &m_hat, Transform::from_xyz(0.0, 1.9, 0.0).with_scale(Vec3::new(0.24, 0.14, 0.24))));
        }
        Headwear::Helmet => kids.push(part(commands, &sph, &m_hat, Transform::from_xyz(0.0, 1.8, 0.0).with_scale(Vec3::new(0.3, 0.26, 0.32)))),
        Headwear::Ushanka => {
            kids.push(part(commands, &sph, &m_hat, Transform::from_xyz(0.0, 1.82, 0.0).with_scale(Vec3::new(0.32, 0.24, 0.32))));
            for side in [-1.0, 1.0] {
                kids.push(part(commands, &cube, &m_hat, Transform::from_xyz(side * 0.14, 1.68, 0.0).with_scale(Vec3::new(0.05, 0.16, 0.16))));
            }
        }
    }

    // Limbs pivot at hip/shoulder so the walk cycle can swing them.
    let limbs = [
        (LimbKind::LeftLeg, Vec3::new(-0.11 * b, 0.86, 0.0), &m_pants, 0.74, 0.15),
        (LimbKind::RightLeg, Vec3::new(0.11 * b, 0.86, 0.0), &m_pants, 0.74, 0.15),
        (LimbKind::LeftArm, Vec3::new(-0.3 * b, 1.46, 0.0), &m_top, 0.62, 0.11),
        (LimbKind::RightArm, Vec3::new(0.3 * b, 1.46, 0.0), &m_top, 0.62, 0.11),
    ];
    for (kind, pivot, mat, len, thick) in limbs {
        let is_leg = matches!(kind, LimbKind::LeftLeg | LimbKind::RightLeg);
        let limb = commands
            .spawn((Transform::from_translation(pivot), Visibility::default(), Limb(kind)))
            .with_children(|c| {
                c.spawn((
                    Mesh3d(cap.clone()),
                    MeshMaterial3d((*mat).clone()),
                    Transform::from_xyz(0.0, -len * 0.5, 0.0).with_scale(Vec3::new(thick * b, len * 0.5, thick * b)),
                ));
                if is_leg {
                    c.spawn((
                        Mesh3d(cube.clone()),
                        MeshMaterial3d(m_shoes.clone()),
                        Transform::from_xyz(0.0, -len - 0.07, -0.05).with_scale(Vec3::new(0.14, 0.1, 0.28)),
                    ));
                } else {
                    c.spawn((
                        Mesh3d(sph.clone()),
                        MeshMaterial3d(m_skin.clone()),
                        Transform::from_xyz(0.0, -len - 0.04, 0.0).with_scale(Vec3::splat(0.11)),
                    ));
                }
            })
            .id();
        kids.push(limb);
    }
    commands.entity(root).add_children(&kids);
}

pub struct CharacterPlugin;

impl Plugin for CharacterPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Skins::generate())
            .init_resource::<ColorMats>()
            .add_systems(Update, animate_rigs.in_set(crate::GameSet::Visuals));
    }
}

fn animate_rigs(time: Res<Time>, mut rigs: Query<(&mut Rig, &Children)>, mut limbs: Query<(&Limb, &mut Transform)>) {
    let dt = time.delta_secs();
    for (mut rig, children) in &mut rigs {
        let s = rig.speed;
        rig.phase += dt * (2.0 + s * 1.6);
        let amp = (s / 4.0).clamp(0.0, 1.0) * 0.75;
        let swim = rig.swimming;
        for c in children.iter() {
            if let Ok((limb, mut t)) = limbs.get_mut(c) {
                let ph = rig.phase;
                let a = if swim {
                    match limb.0 {
                        LimbKind::LeftArm => -2.6 + (ph * 1.2).sin() * 1.2,
                        LimbKind::RightArm => -2.6 - (ph * 1.2).sin() * 1.2,
                        LimbKind::LeftLeg => (ph * 2.0).sin() * 0.4,
                        LimbKind::RightLeg => -(ph * 2.0).sin() * 0.4,
                    }
                } else {
                    match limb.0 {
                        LimbKind::LeftLeg => ph.sin() * amp,
                        LimbKind::RightLeg => -ph.sin() * amp,
                        LimbKind::LeftArm => -ph.sin() * amp * 0.8,
                        LimbKind::RightArm => ph.sin() * amp * 0.8,
                    }
                };
                t.rotation = Quat::from_rotation_x(a);
            }
        }
    }
}
