//! The player: walking, running, swimming, getting in and out of any vehicle.

use bevy::prelude::*;

use crate::character::{build_body, uniform, ColorMats, Rig, Skins};
use crate::city::{CityMap, Place, SharedMeshes, WATER_LEVEL};
use crate::hud::Notify;
use crate::input::Controls;
use crate::jobs::JobState;
use crate::scene::CameraRig;
use crate::traffic::TrafficAi;
use crate::util::*;
use crate::vehicles::{Catalog, Driven, Vehicle};

#[derive(Component)]
pub struct Player {
    pub yaw: f32,
}

#[derive(Resource)]
pub struct PlayerState {
    pub vehicle: Option<Entity>,
    pub money: i64,
    pub skin: usize,
    pub owned_skins: Vec<usize>,
    pub owned_cars: Vec<usize>,
    pub swimming: bool,
    pub uniform_on: Option<crate::jobs::JobKind>,
    /// Bumped whenever the body must be rebuilt (skin or uniform change).
    pub body_rev: u32,
}

impl Default for PlayerState {
    fn default() -> Self {
        Self {
            vehicle: None,
            money: 25_000,
            skin: 0,
            owned_skins: vec![0],
            owned_cars: Vec::new(),
            swimming: false,
            uniform_on: None,
            body_rev: 1,
        }
    }
}

pub struct PlayerPlugin;

impl Plugin for PlayerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PlayerState>()
            .add_systems(Startup, spawn_player)
            .add_systems(
                Update,
                (enter_exit, walk, rebuild_body, ride_along)
                    .chain()
                    .in_set(crate::GameSet::Player),
            );
    }
}

fn spawn_player(mut commands: Commands, map: Res<CityMap>) {
    let start = map.sites[&Place::Government].door + Vec3::new(3.0, 0.0, 4.0);
    commands.spawn((
        Name::new("Player"),
        Player { yaw: 0.0 },
        Rig::default(),
        Transform::from_translation(start),
        Visibility::default(),
    ));
}

#[allow(clippy::too_many_arguments)]
fn rebuild_body(
    mut commands: Commands,
    state: Res<PlayerState>,
    skins: Res<Skins>,
    shared: Res<SharedMeshes>,
    mut cm: ResMut<ColorMats>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    player: Query<(Entity, Option<&Children>), With<Player>>,
    mut built: Local<u32>,
) {
    if *built == state.body_rev {
        return;
    }
    let Ok((e, children)) = player.single() else { return };
    *built = state.body_rev;
    if let Some(ch) = children {
        for c in ch.iter() {
            commands.entity(c).despawn();
        }
    }
    let base = &skins.list[state.skin];
    let skin = match state.uniform_on {
        Some(job) => uniform(job, base),
        None => base.clone(),
    };
    build_body(&mut commands, e, &skin, &shared, &mut cm, &mut mats);
    let _ = skin.height;
}

#[allow(clippy::too_many_arguments)]
fn enter_exit(
    mut commands: Commands,
    mut controls: ResMut<Controls>,
    mut state: ResMut<PlayerState>,
    catalog: Res<Catalog>,
    map: Res<CityMap>,
    jobs: Res<JobState>,
    mut player: Query<(&mut Transform, &mut Visibility, &mut Player), Without<Vehicle>>,
    mut vehicles: Query<(Entity, &mut Vehicle, &Transform, Option<&TrafficAi>)>,
    mut notes: EventWriter<Notify>,
) {
    let Ok((mut pt, mut vis, mut pl)) = player.single_mut() else { return };

    // A car sinking in the sea throws the driver out.
    if let Some(car) = state.vehicle {
        if let Ok((_, v, vt, _)) = vehicles.get(car) {
            if v.sinking > 1.2 {
                commands.entity(car).remove::<Driven>();
                state.vehicle = None;
                *vis = Visibility::Inherited;
                pt.translation = vt.translation + Vec3::Y * 0.5;
                notes.write(Notify::warn("Машина ушла под воду. Плывите к берегу!"));
                return;
            }
        } else {
            state.vehicle = None;
            *vis = Visibility::Inherited;
        }
    }

    if !controls.enter || controls.ui_blocked {
        return;
    }
    controls.enter = false;

    if let Some(car) = state.vehicle.take() {
        if let Ok((_, mut v, vt, _)) = vehicles.get_mut(car) {
            let s = &catalog.specs[v.spec];
            let fwd = forward_of(v.yaw);
            let left = Vec2::new(fwd.y, -fwd.x);
            let mut p = xz(vt.translation) + left * (s.width * 0.5 + 0.8);
            if let Some(push) = map.collide(p, 0.4) {
                p += push;
            }
            pt.translation = Vec3::new(p.x, map.ground_height(p), p.y);
            pl.yaw = v.yaw;
            v.speed = 0.0;
            v.vel = Vec2::ZERO;
            v.steer = 0.0;
        }
        commands.entity(car).remove::<Driven>();
        *vis = Visibility::Inherited;
        return;
    }

    let p = xz(pt.translation);
    let mut best: Option<(Entity, f32)> = None;
    for (e, v, vt, _) in &vehicles {
        if v.sinking > 0.0 {
            continue;
        }
        let d = (xz(vt.translation) - p).length() - v.half_len.min(3.0);
        if d < 3.0 && best.is_none_or(|(_, bd)| d < bd) {
            best = Some((e, d));
        }
    }
    let Some((car, _)) = best else {
        notes.write(Notify::info("Рядом нет машины"));
        return;
    };
    let Ok((_, mut v, _, ai)) = vehicles.get_mut(car) else { return };
    if ai.is_some() {
        commands.entity(car).remove::<TrafficAi>();
        v.vel = forward_of(v.yaw) * v.speed;
    }
    commands.entity(car).insert(Driven);
    state.vehicle = Some(car);
    *vis = Visibility::Hidden;
    let name = &catalog.specs[v.spec].name;
    if jobs.vehicle == Some(car) {
        notes.write(Notify::info(format!("Служебный транспорт: {name}")));
    } else {
        notes.write(Notify::info(format!("{name} · {} · до {} км/ч", catalog.specs[v.spec].class.title(), catalog.specs[v.spec].kmh())));
    }
}

#[allow(clippy::too_many_arguments)]
fn walk(
    time: Res<Time>,
    controls: Res<Controls>,
    rig: Res<CameraRig>,
    map: Res<CityMap>,
    mut state: ResMut<PlayerState>,
    mut player: Query<(&mut Transform, &mut Player, &mut Rig)>,
) {
    if state.vehicle.is_some() {
        return;
    }
    let dt = time.delta_secs().min(0.05);
    let Ok((mut t, mut pl, mut body)) = player.single_mut() else { return };
    let input = if controls.ui_blocked { Vec2::ZERO } else { controls.walk };
    let p = xz(t.translation);
    let swimming = map.in_water(p);
    state.swimming = swimming;
    let speed = if swimming {
        2.2
    } else if controls.run {
        7.0
    } else {
        3.4
    };
    let cam_fwd = forward_of(rig.yaw);
    let cam_right = Vec2::new(-cam_fwd.y, cam_fwd.x);
    let dir = cam_fwd * input.y + cam_right * input.x;
    let mut np = p + dir * speed * dt;
    if let Some(push) = map.collide(np, 0.35) {
        np += push;
    }
    if dir.length_squared() > 0.01 {
        let target = yaw_of(dir);
        pl.yaw += angle_diff(pl.yaw, target) * (12.0 * dt).min(1.0);
    }
    let ground = if swimming { WATER_LEVEL - 1.25 } else { map.ground_height(np) };
    t.translation = Vec3::new(np.x, t.translation.y + (ground - t.translation.y) * (14.0 * dt).min(1.0), np.y);
    t.rotation = Quat::from_rotation_y(pl.yaw);
    if swimming {
        t.rotation *= Quat::from_rotation_x(-0.9);
    }
    body.speed = (dir.length() * speed).min(8.0);
    body.swimming = swimming;
}

fn ride_along(
    state: Res<PlayerState>,
    vehicles: Query<&Transform, (With<Vehicle>, Without<Player>)>,
    mut player: Query<&mut Transform, With<Player>>,
) {
    let Some(car) = state.vehicle else { return };
    let (Ok(vt), Ok(mut pt)) = (vehicles.get(car), player.single_mut()) else { return };
    pt.translation = vt.translation;
}
