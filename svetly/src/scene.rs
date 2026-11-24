//! Camera, sun and moon, day/night cycle, fog and graphics quality presets.

use std::f32::consts::PI;

use bevy::core_pipeline::bloom::Bloom;
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::pbr::{CascadeShadowConfigBuilder, DistanceFog, FogFalloff};
use bevy::prelude::*;
use bevy::render::view::Msaa;

use crate::city::{CityMap, NightGlow};
use crate::input::Controls;
use crate::player::{Player, PlayerState};
use crate::util::*;
use crate::vehicles::Vehicle;

#[derive(Resource)]
pub struct Quality {
    pub level: u8,
}

impl Quality {
    pub fn name(&self) -> &'static str {
        ["Низкая", "Средняя", "Высокая"][self.level as usize]
    }
    pub fn traffic(&self) -> usize {
        [18, 30, 44][self.level as usize]
    }
    pub fn peds(&self) -> usize {
        [16, 30, 48][self.level as usize]
    }
}

#[derive(Resource)]
pub struct Clock {
    /// Hours since midnight.
    pub hours: f32,
    pub day: u32,
    /// Game hours per real second.
    pub speed: f32,
}

impl Clock {
    pub fn night_factor(&self) -> f32 {
        let e = self.sun_elevation();
        (1.0 - (e + 0.05) / 0.25).clamp(0.0, 1.0)
    }
    pub fn sun_elevation(&self) -> f32 {
        ((self.hours - 6.0) / 12.0 * PI).sin()
    }
    pub fn text(&self) -> String {
        let h = self.hours.floor() as u32 % 24;
        let m = ((self.hours.fract()) * 60.0).floor() as u32;
        format!("{h:02}:{m:02}")
    }
}

#[derive(Component)]
pub struct MainCamera;
#[derive(Component)]
struct Sun;
#[derive(Component)]
struct Moon;
#[derive(Component)]
pub struct CarLight;

#[derive(Resource)]
pub struct CameraRig {
    pub yaw: f32,
    pub pitch: f32,
    pub dist: f32,
    idle: f32,
    smoothed_target: Vec3,
}

pub struct ScenePlugin;

impl Plugin for ScenePlugin {
    fn build(&self, app: &mut App) {
        let level = if cfg!(target_os = "android") { 0 } else { 2 };
        app.insert_resource(Quality { level })
            .insert_resource(Clock { hours: 16.5, day: 1, speed: 1.0 / 50.0 })
            .insert_resource(ClearColor(srgb(0x8fb8e0)))
            .insert_resource(AmbientLight { color: Color::WHITE, brightness: 400.0, ..default() })
            .insert_resource(CameraRig { yaw: 1.3, pitch: 0.32, dist: 7.5, idle: 0.0, smoothed_target: Vec3::ZERO })
            .add_systems(Startup, setup_scene)
            .add_systems(Update, (tick_clock, apply_quality, car_light).in_set(crate::GameSet::Visuals))
            .add_systems(PostUpdate, follow_camera.before(TransformSystem::TransformPropagate));
    }
}

fn setup_scene(mut commands: Commands, quality: Res<Quality>) {
    commands.spawn((
        MainCamera,
        Camera3d::default(),
        Camera { hdr: true, ..default() },
        Projection::Perspective(PerspectiveProjection { fov: 62f32.to_radians(), far: 1600.0, ..default() }),
        Tonemapping::TonyMcMapface,
        Bloom::NATURAL,
        DistanceFog {
            color: srgb(0x9fbad6),
            directional_light_color: Color::srgba(1.0, 0.85, 0.6, 0.4),
            directional_light_exponent: 24.0,
            falloff: FogFalloff::from_visibility_colors(900.0, srgb(0x8aa6c4), srgb(0xc8d8e8)),
        },
        Msaa::Sample4,
        Transform::from_xyz(0.0, 30.0, 60.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    let shadows = quality.level > 0;
    commands.spawn((
        Sun,
        DirectionalLight { illuminance: 9000.0, shadows_enabled: shadows, color: Color::srgb(1.0, 0.95, 0.88), ..default() },
        CascadeShadowConfigBuilder { num_cascades: 3, first_cascade_far_bound: 22.0, maximum_distance: 240.0, ..default() }.build(),
        Transform::default(),
    ));
    commands.spawn((
        Moon,
        DirectionalLight { illuminance: 0.0, shadows_enabled: false, color: Color::srgb(0.6, 0.7, 1.0), ..default() },
        Transform::from_rotation(Quat::from_euler(EulerRot::YXZ, 0.8, -0.9, 0.0)),
    ));
}

fn tick_clock(
    time: Res<Time>,
    mut clock: ResMut<Clock>,
    mut sun: Query<(&mut DirectionalLight, &mut Transform), (With<Sun>, Without<Moon>)>,
    mut moon: Query<&mut DirectionalLight, (With<Moon>, Without<Sun>)>,
    mut clear: ResMut<ClearColor>,
    mut ambient: ResMut<AmbientLight>,
    mut fog: Query<&mut DistanceFog>,
    glow: Res<NightGlow>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut last_glow: Local<f32>,
) {
    clock.hours += time.delta_secs() * clock.speed;
    if clock.hours >= 24.0 {
        clock.hours -= 24.0;
        clock.day += 1;
    }
    let elev = clock.sun_elevation();
    let night = clock.night_factor();
    let dusk = (1.0 - (elev.abs() / 0.35)).clamp(0.0, 1.0);
    let az = (clock.hours - 6.0) / 12.0 * PI;

    if let Ok((mut l, mut t)) = sun.single_mut() {
        let dir = Vec3::new(-az.cos(), -elev.max(0.04), -0.35).normalize();
        *t = Transform::default().looking_to(dir, Vec3::Y);
        l.illuminance = 9500.0 * elev.max(0.0).powf(0.6) * (1.0 - night);
        let warm = dusk;
        l.color = Color::srgb(1.0, 0.95 - 0.3 * warm, 0.88 - 0.5 * warm);
    }
    if let Ok(mut m) = moon.single_mut() {
        m.illuminance = 220.0 * night;
    }

    let day_sky = Vec3::new(0.50, 0.70, 0.90);
    let dusk_sky = Vec3::new(0.95, 0.55, 0.35);
    let night_sky = Vec3::new(0.02, 0.03, 0.07);
    let mut sky = day_sky.lerp(dusk_sky, dusk * 0.8);
    sky = sky.lerp(night_sky, night);
    clear.0 = Color::srgb(sky.x, sky.y, sky.z);
    ambient.brightness = 60.0 + 500.0 * (1.0 - night);
    ambient.color = Color::srgb(0.8 + 0.2 * sky.x, 0.85 + 0.15 * sky.y, 1.0);
    if let Ok(mut f) = fog.single_mut() {
        let fc = sky * 0.9 + Vec3::splat(0.05) * (1.0 - night);
        f.color = Color::srgb(fc.x, fc.y, fc.z);
        f.directional_light_color = Color::srgba(1.0, 0.7, 0.4, 0.5 * dusk);
    }

    // Window and lamp glow, updated only when it changes noticeably.
    let g = night;
    if (g - *last_glow).abs() > 0.02 || (g == 0.0 && *last_glow != 0.0) || (g == 1.0 && *last_glow != 1.0) {
        *last_glow = g;
        for (h, c) in glow.windows.iter().chain(glow.lamps.iter()) {
            if let Some(m) = mats.get_mut(h) {
                m.emissive = *c * (0.03 + g);
            }
        }
    }
}

fn apply_quality(
    mut controls: ResMut<Controls>,
    mut quality: ResMut<Quality>,
    mut commands: Commands,
    mut cam: Query<(Entity, &mut Camera), With<MainCamera>>,
    mut sun: Query<&mut DirectionalLight, With<Sun>>,
    mut notes: EventWriter<crate::hud::Notify>,
) {
    if controls.quality {
        controls.quality = false;
        quality.level = (quality.level + 1) % 3;
        notes.write(crate::hud::Notify::info(format!("Графика: {}", quality.name())));
    }
    if !quality.is_changed() {
        return;
    }
    let Ok((cam, mut camera)) = cam.single_mut() else { return };
    // HDR (needed for bloom) costs memory bandwidth on phones; off at low quality.
    camera.hdr = quality.level > 0;
    let mut e = commands.entity(cam);
    match quality.level {
        0 => {
            e.remove::<Bloom>().insert(Msaa::Off);
        }
        1 => {
            e.insert((Bloom::NATURAL, Msaa::Sample2));
        }
        _ => {
            e.insert((Bloom::NATURAL, Msaa::Sample4));
        }
    }
    if let Ok(mut s) = sun.single_mut() {
        s.shadows_enabled = quality.level > 0;
    }
}

fn car_light(
    mut commands: Commands,
    clock: Res<Clock>,
    state: Res<PlayerState>,
    lights: Query<(Entity, &ChildOf), With<CarLight>>,
) {
    let want = state.vehicle.filter(|_| clock.night_factor() > 0.3);
    let mut have = false;
    for (e, parent) in &lights {
        if Some(parent.parent()) == want {
            have = true;
        } else {
            commands.entity(e).despawn();
        }
    }
    if let (Some(car), false) = (want, have) {
        let light = commands
            .spawn((
                CarLight,
                SpotLight {
                    intensity: 900_000.0,
                    range: 60.0,
                    outer_angle: 0.55,
                    inner_angle: 0.3,
                    shadows_enabled: false,
                    color: Color::srgb(1.0, 0.95, 0.85),
                    ..default()
                },
                Transform::from_xyz(0.0, 0.8, -2.0).looking_to(Vec3::new(0.0, -0.12, -1.0), Vec3::Y),
            ))
            .id();
        commands.entity(car).add_child(light);
    }
}

#[allow(clippy::too_many_arguments)]
fn follow_camera(
    time: Res<Time>,
    controls: Res<Controls>,
    state: Res<PlayerState>,
    map: Res<CityMap>,
    mut rig: ResMut<CameraRig>,
    player: Query<&Transform, (With<Player>, Without<MainCamera>)>,
    vehicles: Query<(&Transform, &Vehicle), Without<MainCamera>>,
    catalog: Res<crate::vehicles::Catalog>,
    mut cam: Query<&mut Transform, With<MainCamera>>,
) {
    let dt = time.delta_secs().min(0.05);
    let Ok(mut cam_t) = cam.single_mut() else { return };
    let (target, follow_yaw, moving, dist, height) = if let Some((t, v)) = state.vehicle.and_then(|e| vehicles.get(e).ok()) {
        let s = &catalog.specs[v.spec];
        let size = s.length.max(4.0);
        (t.translation + Vec3::Y * 1.2, Some(v.yaw), v.speed.abs() > 2.0, size * 1.35 + 2.5, 1.0)
    } else if let Ok(t) = player.single() {
        (t.translation + Vec3::Y * 1.5, None, false, 5.0, 0.0)
    } else {
        return;
    };

    if !controls.ui_blocked {
        rig.yaw -= controls.look.x;
        rig.pitch = (rig.pitch + controls.look.y).clamp(-0.15, 1.2);
        rig.dist = (rig.dist + controls.zoom * 0.8).clamp(3.0, 30.0);
    }
    if controls.look.length_squared() > 0.0 {
        rig.idle = 0.0;
    } else {
        rig.idle += dt;
    }
    if let (Some(yaw), true) = (follow_yaw, moving && rig.idle > 1.2) {
        let d = angle_diff(rig.yaw, yaw);
        rig.yaw += d * (2.5 * dt).min(1.0);
        rig.pitch += (0.22 - rig.pitch) * (1.5 * dt).min(1.0);
    }
    let want_dist = if follow_yaw.is_some() { dist.max(rig.dist * 0.6) } else { rig.dist.min(12.0).max(dist * 0.7) };

    rig.smoothed_target = if rig.smoothed_target == Vec3::ZERO { target } else { rig.smoothed_target.lerp(target, (14.0 * dt).min(1.0)) };
    let tgt = rig.smoothed_target;
    let dir = Quat::from_euler(EulerRot::YXZ, rig.yaw, -rig.pitch, 0.0) * Vec3::Z;
    // Pull the camera in front of walls.
    let mut d = want_dist;
    let mut s = 1.5;
    while s < want_dist {
        let p = tgt + dir * s;
        if p.y < 40.0 && map.collide(xz(p), 0.4).is_some() {
            d = (s - 0.8).max(1.5);
            break;
        }
        s += 1.0;
    }
    let mut pos = tgt + dir * d + Vec3::Y * height;
    pos.y = pos.y.max(map.ground_height(xz(pos)) + 0.4);
    cam_t.translation = pos;
    cam_t.look_at(tgt + Vec3::Y * 0.3, Vec3::Y);
}
