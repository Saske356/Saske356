//! City life: traffic that follows lanes and turns at junctions, pedestrians on
//! the sidewalks, and police cars that chase the player when wanted.

use bevy::prelude::*;
use rand::rngs::SmallRng;
use rand::{Rng, SeedableRng};

use crate::character::{build_body, ColorMats, Rig, Skins};
use crate::city::{road_coord, CityMap, LotKind, SharedMeshes, N};
use crate::player::{Player, PlayerState};
use crate::scene::Quality;
use crate::util::*;
use crate::vehicles::{spawn_vehicle, Catalog, Driven, Livery, Vehicle, VehicleAssets};

const TRAFFIC_OFF: f32 = 1.9;

#[derive(Component)]
pub struct TrafficAi {
    from: IVec2,
    to: IVec2,
    cruise: f32,
    /// Set for cars a job is interested in (speeders, surveillance targets).
    pub marked: bool,
}

#[derive(Component)]
pub struct Ped {
    lot: usize,
    t: f32,
    speed: f32,
    dir: f32,
    knocked: f32,
}

/// Police car chasing the player.
#[derive(Component)]
pub struct Pursuer {
    pub close_time: f32,
}

#[derive(Resource)]
pub struct NpcRng(pub SmallRng);

pub struct TrafficPlugin;

impl Plugin for TrafficPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(NpcRng(SmallRng::seed_from_u64(99)))
            .add_systems(Update, (populate_traffic, drive_traffic, populate_peds, walk_peds, chase).in_set(crate::GameSet::Npc));
    }
}

fn node(n: IVec2) -> Vec2 {
    Vec2::new(road_coord(n.x), road_coord(n.y))
}

fn lane_point(from: IVec2, to: IVec2) -> Vec2 {
    let d = (node(to) - node(from)).normalize();
    let right = Vec2::new(-d.y, d.x);
    node(to) + right * TRAFFIC_OFF - d * 3.0
}

fn neighbors(n: IVec2) -> impl Iterator<Item = IVec2> {
    [IVec2::X, IVec2::NEG_X, IVec2::Y, IVec2::NEG_Y]
        .into_iter()
        .map(move |d| n + d)
        .filter(|m| m.x >= 0 && m.y >= 0 && m.x <= N && m.y <= N)
}

#[allow(clippy::too_many_arguments)]
fn populate_traffic(
    mut commands: Commands,
    mut rng: ResMut<NpcRng>,
    quality: Res<Quality>,
    catalog: Res<Catalog>,
    shared: Res<SharedMeshes>,
    mut va: ResMut<VehicleAssets>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    player: Query<&Transform, With<Player>>,
    cars: Query<(Entity, &Transform), With<TrafficAi>>,
) {
    let Ok(pt) = player.single() else { return };
    let pp = xz(pt.translation);
    let mut count = 0;
    for (e, t) in &cars {
        if (xz(t.translation) - pp).length() > 320.0 {
            commands.entity(e).despawn();
        } else {
            count += 1;
        }
    }
    let rng = &mut rng.0;
    let mut spawned = 0;
    while count < quality.traffic() && spawned < 3 {
        let from = IVec2::new(rng.gen_range(0..=N), rng.gen_range(0..=N));
        let options: Vec<IVec2> = neighbors(from).collect();
        let to = options[rng.gen_range(0..options.len())];
        let t = rng.gen_range(0.1..0.7);
        let d = (node(to) - node(from)).normalize();
        let right = Vec2::new(-d.y, d.x);
        let p = node(from).lerp(node(to), t) + right * TRAFFIC_OFF;
        let dist = (p - pp).length();
        if !(70.0..260.0).contains(&dist) {
            spawned += 1;
            continue;
        }
        if cars.iter().any(|(_, ct)| (xz(ct.translation) - p).length() < 12.0) {
            spawned += 1;
            continue;
        }
        let spec = catalog.random_civil(rng);
        let livery = if rng.gen_bool(0.08) {
            Livery::Taxi
        } else if rng.gen_bool(0.04) {
            Livery::Police
        } else {
            Livery::None
        };
        let paint = rng.gen_range(0..va.paints.len());
        let yaw = yaw_of(d);
        let e = spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, spec, paint, livery, Vec3::new(p.x, 0.0, p.y), yaw);
        let cruise = rng.gen_range(9.0..15.0);
        commands.entity(e).insert(TrafficAi { from, to, cruise, marked: false });
        count += 1;
        spawned += 1;
    }
}

#[allow(clippy::too_many_arguments)]
fn drive_traffic(
    time: Res<Time>,
    mut rng: ResMut<NpcRng>,
    player: Query<&Transform, (With<Player>, Without<TrafficAi>)>,
    state: Res<PlayerState>,
    driven: Query<&Transform, (With<Driven>, Without<TrafficAi>)>,
    mut cars: Query<(Entity, &mut TrafficAi, &mut Vehicle, &mut Transform)>,
) {
    let dt = time.delta_secs().min(0.05);
    let obstacles: Vec<(Entity, Vec2)> = cars.iter().map(|(e, _, _, t)| (e, xz(t.translation))).collect();
    let mut extra: Vec<Vec2> = Vec::new();
    if let Ok(t) = player.single() {
        if state.vehicle.is_none() {
            extra.push(xz(t.translation));
        }
    }
    for t in &driven {
        extra.push(xz(t.translation));
    }
    for (e, mut ai, mut v, mut t) in &mut cars {
        let p = xz(t.translation);
        let target = lane_point(ai.from, ai.to);
        if (target - p).length() < 4.0 {
            let back = ai.from;
            let cur = ai.to;
            let options: Vec<IVec2> = neighbors(cur).filter(|n| *n != back).collect();
            let straight = cur + (cur - back);
            ai.from = cur;
            ai.to = if options.contains(&straight) && rng.0.gen_bool(0.55) {
                straight
            } else if options.is_empty() {
                back
            } else {
                options[rng.0.gen_range(0..options.len())]
            };
        }
        let target = lane_point(ai.from, ai.to);
        let to_target = target - p;
        let want_yaw = yaw_of(to_target);
        let diff = angle_diff(v.yaw, want_yaw);
        let fwd = forward_of(v.yaw);
        // Slow for turns and for anything ahead.
        let mut desired = ai.cruise * (1.0 - (diff.abs() / 1.2).min(0.7));
        for &(oe, op) in &obstacles {
            if oe == e {
                continue;
            }
            let d = op - p;
            let ahead = d.dot(fwd);
            let side = (d - fwd * ahead).length();
            if ahead > 0.0 && ahead < 14.0 && side < 2.4 {
                desired = desired.min((ahead - 6.0).max(0.0) * 1.2);
            }
        }
        for &op in &extra {
            let d = op - p;
            let ahead = d.dot(fwd);
            let side = (d - fwd * ahead).length();
            if ahead > 0.0 && ahead < 12.0 && side < 2.6 {
                desired = desired.min((ahead - 5.0).max(0.0));
            }
        }
        let accel = if desired > v.speed { 4.0 } else { 9.0 };
        v.speed += (desired - v.speed).clamp(-accel * dt, accel * dt);
        let turn_rate = 1.8 * (v.speed / 6.0).clamp(0.2, 1.0);
        v.yaw += diff.clamp(-turn_rate * dt, turn_rate * dt);
        v.steer = (diff * 1.5).clamp(-0.5, 0.5) * -1.0;
        let np = p + forward_of(v.yaw) * v.speed * dt;
        v.vel = forward_of(v.yaw) * v.speed;
        t.translation.x = np.x;
        t.translation.z = np.y;
    }
}

#[allow(clippy::too_many_arguments)]
fn populate_peds(
    mut commands: Commands,
    mut rng: ResMut<NpcRng>,
    quality: Res<Quality>,
    map: Res<CityMap>,
    skins: Res<Skins>,
    shared: Res<SharedMeshes>,
    mut cm: ResMut<ColorMats>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    player: Query<&Transform, With<Player>>,
    peds: Query<(Entity, &Transform), With<Ped>>,
) {
    let Ok(pt) = player.single() else { return };
    let pp = xz(pt.translation);
    let mut count = 0;
    for (e, t) in &peds {
        if (xz(t.translation) - pp).length() > 180.0 {
            commands.entity(e).despawn();
        } else {
            count += 1;
        }
    }
    let rng = &mut rng.0;
    let mut tries = 0;
    while count < quality.peds() && tries < 4 {
        tries += 1;
        let lot = rng.gen_range(0..map.lots.len());
        let l = &map.lots[lot];
        if matches!(l.kind, LotKind::Beachfront) && rng.gen_bool(0.5) {
            continue;
        }
        let d = (l.rect.center() - pp).length();
        if !(30.0..150.0).contains(&d) {
            continue;
        }
        let skin = skins.list[rng.gen_range(0..skins.list.len())].clone();
        let e = commands
            .spawn((
                Ped { lot, t: rng.gen_range(0.0..1.0), speed: rng.gen_range(1.1..1.8), dir: if rng.gen_bool(0.5) { 1.0 } else { -1.0 }, knocked: 0.0 },
                Rig::default(),
                Transform::from_xyz(l.rect.min.x, 0.15, l.rect.min.y).with_scale(Vec3::splat(skin.height)),
                Visibility::default(),
            ))
            .id();
        build_body(&mut commands, e, &skin, &shared, &mut cm, &mut mats);
        count += 1;
    }
}

fn perimeter_point(r: Rect2, t: f32) -> (Vec2, Vec2) {
    let r = Rect2::new(r.min + Vec2::splat(1.4), r.max - Vec2::splat(1.4));
    let w = r.max.x - r.min.x;
    let h = r.max.y - r.min.y;
    let per = 2.0 * (w + h);
    let mut s = t.rem_euclid(1.0) * per;
    if s < w {
        return (Vec2::new(r.min.x + s, r.min.y), Vec2::X);
    }
    s -= w;
    if s < h {
        return (Vec2::new(r.max.x, r.min.y + s), Vec2::Y);
    }
    s -= h;
    if s < w {
        return (Vec2::new(r.max.x - s, r.max.y), Vec2::NEG_X);
    }
    s -= w;
    (Vec2::new(r.min.x, r.max.y - s), Vec2::NEG_Y)
}

fn walk_peds(
    mut commands: Commands,
    time: Res<Time>,
    map: Res<CityMap>,
    driven: Query<(&Transform, &Vehicle), (With<Driven>, Without<Ped>)>,
    mut peds: Query<(Entity, &mut Ped, &mut Transform, &mut Rig)>,
) {
    let dt = time.delta_secs().min(0.05);
    let car = driven.iter().next().map(|(t, v)| (xz(t.translation), v.speed.abs(), v.radius + 0.5));
    for (e, mut ped, mut t, mut rig) in &mut peds {
        if ped.knocked > 0.0 {
            ped.knocked -= dt;
            t.translation.y = (t.translation.y - dt * 2.0).max(0.2);
            if ped.knocked <= 0.0 {
                commands.entity(e).despawn();
            }
            continue;
        }
        let lot = &map.lots[ped.lot];
        let w = lot.rect.max.x - lot.rect.min.x;
        let per = 4.0 * w;
        ped.t += ped.dir * ped.speed * dt / per;
        let (p, d) = perimeter_point(lot.rect, ped.t);
        let d = d * ped.dir;
        t.translation.x = p.x;
        t.translation.z = p.y;
        t.translation.y = 0.15;
        t.rotation = Quat::from_rotation_y(yaw_of(d));
        rig.speed = ped.speed;
        if let Some((cp, speed, r)) = car {
            if speed > 4.0 && (cp - p).length() < r {
                ped.knocked = 4.0;
                let away = (p - cp).normalize_or_zero();
                t.translation += Vec3::new(away.x, 1.0, away.y) * 1.5;
                t.rotation = Quat::from_rotation_y(yaw_of(away)) * Quat::from_rotation_x(-1.5);
                rig.speed = 0.0;
            }
        }
    }
}

fn chase(
    time: Res<Time>,
    map: Res<CityMap>,
    player: Query<&Transform, (With<Player>, Without<Pursuer>)>,
    mut cops: Query<(&mut Pursuer, &mut Vehicle, &mut Transform)>,
) {
    let dt = time.delta_secs().min(0.05);
    let Ok(pt) = player.single() else { return };
    let target = xz(pt.translation);
    for (mut cop, mut v, mut t) in &mut cops {
        let p = xz(t.translation);
        let to = target - p;
        let dist = to.length();
        let diff = angle_diff(v.yaw, yaw_of(to));
        let desired = if dist < 7.0 { 3.0 } else { 27.0 * (1.0 - (diff.abs() / 2.0).min(0.6)) };
        v.speed += (desired - v.speed).clamp(-14.0 * dt, 7.0 * dt);
        v.yaw += diff.clamp(-2.2 * dt, 2.2 * dt);
        v.steer = -(diff * 1.5).clamp(-0.5, 0.5);
        let mut np = p + forward_of(v.yaw) * v.speed * dt;
        if let Some(push) = map.collide(np, v.radius) {
            np += push;
            v.speed *= 0.9;
        }
        v.vel = forward_of(v.yaw) * v.speed;
        t.translation.x = np.x;
        t.translation.z = np.y;
        if dist < 8.0 {
            cop.close_time += dt;
        } else {
            cop.close_time = (cop.close_time - dt * 0.5).max(0.0);
        }
    }
}
