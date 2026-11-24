//! Articulated low-poly people: player, pedestrians and seated drivers.
use bevy::prelude::*;

use crate::mats::Mats;
use crate::util::*;

#[derive(Resource, Clone)]
pub struct PeopleAssets {
    torso: Handle<Mesh>,
    pelvis: Handle<Mesh>,
    neck: Handle<Mesh>,
    head: Handle<Mesh>,
    thigh: Handle<Mesh>,
    shin: Handle<Mesh>,
    shoe: Handle<Mesh>,
    upper_arm: Handle<Mesh>,
    forearm: Handle<Mesh>,
    hand: Handle<Mesh>,
}

pub fn build_people_assets(meshes: &mut Assets<Mesh>) -> PeopleAssets {
    PeopleAssets {
        torso: meshes.add(Capsule3d::new(0.16, 0.32).mesh().rings(4).latitudes(10).longitudes(14).build()),
        pelvis: meshes.add(Cuboid::new(0.32, 0.16, 0.2)),
        neck: meshes.add(Cylinder::new(0.05, 0.12).mesh().resolution(10).build()),
        head: meshes.add(Sphere::new(1.0).mesh().uv(16, 10)),
        thigh: meshes.add(Capsule3d::new(0.075, 0.3).mesh().latitudes(8).longitudes(10).build()),
        shin: meshes.add(Capsule3d::new(0.062, 0.33).mesh().latitudes(8).longitudes(10).build()),
        shoe: meshes.add(Cuboid::new(0.1, 0.07, 0.25)),
        upper_arm: meshes.add(Capsule3d::new(0.052, 0.18).mesh().latitudes(8).longitudes(10).build()),
        forearm: meshes.add(Capsule3d::new(0.045, 0.17).mesh().latitudes(8).longitudes(10).build()),
        hand: meshes.add(Sphere::new(0.05).mesh().uv(10, 6)),
    }
}

#[derive(Clone, Copy, Default)]
pub struct Look {
    pub skin: usize,
    pub shirt: usize,
    pub pants: usize,
    pub hair: usize,
}

impl Look {
    pub fn random(rng: &mut Rng) -> Self {
        Self { skin: rng.int(4) as usize, shirt: rng.int(8) as usize, pants: rng.int(5) as usize, hair: rng.int(4) as usize }
    }
}

#[derive(Clone, Copy, PartialEq)]
pub enum Pose {
    Walk,
    Seated,
}

#[derive(Component)]
pub struct Humanoid {
    pub phase: f32,
    pub speed: f32,
    pub pose: Pose,
}

#[derive(Clone, Copy, PartialEq)]
pub enum LimbKind {
    Arm(f32),
    Forearm(f32),
    Leg(f32),
    Shin(f32),
}

#[derive(Component)]
pub struct Limb {
    pub owner: Entity,
    pub kind: LimbKind,
}

#[derive(Component)]
pub struct Head;

#[derive(Component)]
pub struct Ped {
    pub block: IVec2,
    pub s: f32,
    pub dir: f32,
    pub speed: f32,
    pub lane: f32,
}

pub fn spawn_human(
    commands: &mut Commands,
    pa: &PeopleAssets,
    mats: &Mats,
    look: Look,
    tf: Transform,
    pose: Pose,
    parent: Option<Entity>,
) -> Entity {
    let skin = mats.skin[look.skin % mats.skin.len()].clone();
    let shirt = mats.shirts[look.shirt % mats.shirts.len()].clone();
    let pants = mats.pants[look.pants % mats.pants.len()].clone();
    let hair = mats.hair[look.hair % mats.hair.len()].clone();
    let root = commands.spawn((tf, Visibility::default(), Humanoid { phase: 0.0, speed: 0.0, pose })).id();
    if let Some(p) = parent {
        commands.entity(root).insert(ChildOf(p));
    }
    let part = |c: &mut Commands, mesh: &Handle<Mesh>, mat: &Handle<StandardMaterial>, t: Transform, parent: Entity| {
        c.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(mat.clone()), t, ChildOf(parent))).id()
    };
    part(commands, &pa.torso, &shirt, Transform::from_xyz(0.0, 1.2, 0.0).with_scale(Vec3::new(1.15, 1.0, 0.7)), root);
    part(commands, &pa.pelvis, &pants, Transform::from_xyz(0.0, 0.96, 0.0), root);
    part(commands, &pa.neck, &skin, Transform::from_xyz(0.0, 1.53, 0.0), root);
    let head = commands.spawn((Transform::from_xyz(0.0, 1.66, 0.0), Visibility::default(), Head, ChildOf(root))).id();
    part(commands, &pa.head, &skin, Transform::from_scale(Vec3::new(0.105, 0.12, 0.11)), head);
    part(commands, &pa.head, &hair, Transform::from_xyz(0.0, 0.04, 0.015).with_scale(Vec3::new(0.112, 0.1, 0.115)), head);
    for sx in [-0.04f32, 0.04] {
        part(commands, &pa.head, &mats.eyes, Transform::from_xyz(sx, 0.01, -0.1).with_scale(Vec3::splat(0.014)), head);
    }
    part(commands, &pa.head, &skin, Transform::from_xyz(0.0, -0.01, -0.11).with_scale(Vec3::new(0.018, 0.025, 0.02)), head);
    for side in [-1.0f32, 1.0] {
        // leg: thigh pivot at hip, shin pivot at knee
        let leg = commands
            .spawn((
                Transform::from_xyz(side * 0.09, 0.92, 0.0),
                Visibility::default(),
                Limb { owner: root, kind: LimbKind::Leg(side) },
                ChildOf(root),
            ))
            .id();
        part(commands, &pa.thigh, &pants, Transform::from_xyz(0.0, -0.21, 0.0), leg);
        let shin = commands
            .spawn((
                Transform::from_xyz(0.0, -0.42, 0.0),
                Visibility::default(),
                Limb { owner: root, kind: LimbKind::Shin(side) },
                ChildOf(leg),
            ))
            .id();
        part(commands, &pa.shin, &pants, Transform::from_xyz(0.0, -0.22, 0.0), shin);
        part(commands, &pa.shoe, &mats.shoes, Transform::from_xyz(0.0, -0.465, -0.04), shin);
        // arm
        let arm = commands
            .spawn((
                Transform::from_xyz(side * 0.225, 1.44, 0.0),
                Visibility::default(),
                Limb { owner: root, kind: LimbKind::Arm(side) },
                ChildOf(root),
            ))
            .id();
        part(commands, &pa.upper_arm, &shirt, Transform::from_xyz(0.0, -0.14, 0.0), arm);
        let fore = commands
            .spawn((
                Transform::from_xyz(0.0, -0.28, 0.0),
                Visibility::default(),
                Limb { owner: root, kind: LimbKind::Forearm(side) },
                ChildOf(arm),
            ))
            .id();
        part(commands, &pa.forearm, &skin, Transform::from_xyz(0.0, -0.13, 0.0), fore);
        part(commands, &pa.hand, &skin, Transform::from_xyz(0.0, -0.29, 0.0), fore);
    }
    root
}

pub fn animate_humans(time: Res<Time>, mut hum: Query<&mut Humanoid>, mut limbs: Query<(&Limb, &mut Transform)>) {
    let dt = time.delta_secs();
    for mut h in &mut hum {
        if h.pose == Pose::Walk {
            h.phase += dt * h.speed * 2.9;
        }
    }
    for (l, mut tf) in &mut limbs {
        let Ok(h) = hum.get(l.owner) else { continue };
        let amp = (h.speed / 1.6).min(1.6);
        let p = h.phase;
        let (rx, rz) = match (h.pose, l.kind) {
            (Pose::Seated, LimbKind::Leg(_)) => (1.5, 0.0),
            (Pose::Seated, LimbKind::Shin(_)) => (-0.2, 0.0),
            (Pose::Seated, LimbKind::Arm(s)) => (1.0, s * 0.1),
            (Pose::Seated, LimbKind::Forearm(_)) => (0.9, 0.0),
            (Pose::Walk, LimbKind::Leg(s)) => ((p + if s < 0.0 { 0.0 } else { std::f32::consts::PI }).sin() * 0.45 * amp, 0.0),
            (Pose::Walk, LimbKind::Shin(s)) => {
                let ph = p + if s < 0.0 { 0.0 } else { std::f32::consts::PI };
                (-((ph - 1.2).sin().max(0.0)) * 0.9 * amp, 0.0)
            }
            (Pose::Walk, LimbKind::Arm(s)) => {
                (-(p + if s < 0.0 { 0.0 } else { std::f32::consts::PI }).sin() * 0.4 * amp, s * 0.06)
            }
            (Pose::Walk, LimbKind::Forearm(_)) => (0.2 + 0.35 * amp.min(1.0), 0.0),
        };
        tf.rotation = Quat::from_rotation_z(rz) * Quat::from_rotation_x(rx);
    }
}

pub fn ped_point(block: IVec2, s: f32, lane: f32) -> (Vec2, Vec2) {
    let mn = block_min(block.x, block.y);
    let inset = 2.3 + lane;
    let x0 = mn.x + inset;
    let z0 = mn.y + inset;
    let l = BLOCK - inset * 2.0;
    let per = l * 4.0;
    let s = s.rem_euclid(per);
    let seg = (s / l) as i32;
    let t = s - seg as f32 * l;
    match seg {
        0 => (Vec2::new(x0 + t, z0), Vec2::X),
        1 => (Vec2::new(x0 + l, z0 + t), Vec2::Y),
        2 => (Vec2::new(x0 + l - t, z0 + l), Vec2::NEG_X),
        _ => (Vec2::new(x0, z0 + l - t), Vec2::NEG_Y),
    }
}

pub fn spawn_peds(commands: &mut Commands, pa: &PeopleAssets, mats: &Mats, rng: &mut Rng, count: usize) {
    for _ in 0..count {
        let block = IVec2::new(rng.int(N as u32) as i32, rng.int(N as u32) as i32);
        let s = rng.range(0.0, 200.0);
        let lane = rng.range(-0.6, 0.6);
        let dir = if rng.chance(0.5) { 1.0 } else { -1.0 };
        let speed = rng.range(1.1, 1.7);
        let (p, d) = ped_point(block, s, lane);
        let e = spawn_human(
            commands,
            pa,
            mats,
            Look::random(rng),
            Transform::from_xyz(p.x, CURB, p.y).with_rotation(Quat::from_rotation_y(yaw_from_dir(d * dir))),
            Pose::Walk,
            None,
        );
        commands.entity(e).insert(Ped { block, s, dir, speed, lane });
    }
}

pub fn move_peds(time: Res<Time>, mut q: Query<(&mut Ped, &mut Humanoid, &mut Transform)>) {
    let dt = time.delta_secs().min(0.05);
    for (mut ped, mut h, mut tf) in &mut q {
        ped.s += ped.dir * ped.speed * dt;
        let (p, d) = ped_point(ped.block, ped.s, ped.lane);
        tf.translation = Vec3::new(p.x, CURB, p.y);
        let target = Quat::from_rotation_y(yaw_from_dir(d * ped.dir));
        tf.rotation = tf.rotation.slerp(target, (8.0 * dt).min(1.0));
        h.speed = ped.speed;
    }
}
