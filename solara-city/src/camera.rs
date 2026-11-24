//! Camera rig: third-person on foot, chase / interior / hood / orbit while driving.
use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::prelude::*;
use bevy::window::{CursorGrabMode, PrimaryWindow};

use crate::car::{Car, DriverSeat, EYE};
use crate::people::{Head, Humanoid};
use crate::player::{Game, Mode, Player};
use crate::util::*;

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum CarCam {
    Chase,
    Interior,
    Hood,
    Orbit,
}

impl CarCam {
    pub fn label(&self) -> &'static str {
        match self {
            CarCam::Chase => "сзади",
            CarCam::Interior => "из салона",
            CarCam::Hood => "с капота",
            CarCam::Orbit => "облёт",
        }
    }
}

#[derive(Resource)]
pub struct Rig {
    pub yaw: f32,
    pub pitch: f32,
    pub dist: f32,
    pub car_cam: CarCam,
    pub off_yaw: f32,
    pub off_pitch: f32,
    pub look_yaw: f32,
    pub look_pitch: f32,
    pub orbit: f32,
    pub idle: f32,
    pub chase_yaw: f32,
    pub chase_dist: f32,
    pub pos: Vec3,
    pub fov: f32,
    pub showcase: bool,
}

impl Default for Rig {
    fn default() -> Self {
        Self {
            yaw: 2.4,
            pitch: -0.18,
            dist: 4.6,
            car_cam: CarCam::Chase,
            off_yaw: 0.0,
            off_pitch: 0.0,
            look_yaw: 0.0,
            look_pitch: 0.0,
            orbit: 0.0,
            idle: 0.0,
            chase_yaw: 0.0,
            chase_dist: 6.8,
            pos: Vec3::ZERO,
            fov: 62.0,
            showcase: true,
        }
    }
}

pub fn camera_input(
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    buttons: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    game: Res<Game>,
    mut rig: ResMut<Rig>,
    mut windows: Query<&mut Window, With<PrimaryWindow>>,
) {
    let dt = time.delta_secs();
    let mut locked = false;
    if let Ok(mut w) = windows.single_mut() {
        if buttons.just_pressed(MouseButton::Left) {
            w.cursor_options.grab_mode = CursorGrabMode::Locked;
            w.cursor_options.visible = false;
        }
        if keys.just_pressed(KeyCode::Escape) {
            w.cursor_options.grab_mode = CursorGrabMode::None;
            w.cursor_options.visible = true;
        }
        locked = w.cursor_options.grab_mode != CursorGrabMode::None;
    }
    let dragging = buttons.pressed(MouseButton::Right) || buttons.pressed(MouseButton::Left);
    let mut d = if locked || dragging { motion.delta } else { Vec2::ZERO };
    // keyboard look as a fallback (arrows / Q,E when driving)
    if game.mode != Mode::Foot {
        if keys.pressed(KeyCode::KeyQ) {
            d.x -= 500.0 * dt;
        }
        if keys.pressed(KeyCode::KeyE) {
            d.x += 500.0 * dt;
        }
    }
    let s = 0.0028;
    let driving = game.mode == Mode::Driving || game.mode == Mode::Entering;
    if keys.just_pressed(KeyCode::KeyC) && driving {
        rig.car_cam = match rig.car_cam {
            CarCam::Chase => CarCam::Interior,
            CarCam::Interior => CarCam::Hood,
            CarCam::Hood => CarCam::Chase,
            CarCam::Orbit => CarCam::Chase,
        };
        rig.look_yaw = 0.0;
        rig.look_pitch = 0.0;
    }
    if keys.just_pressed(KeyCode::KeyV) {
        if driving {
            rig.car_cam = if rig.car_cam == CarCam::Orbit { CarCam::Chase } else { CarCam::Orbit };
        } else {
            rig.showcase = !rig.showcase;
        }
    }
    let moving = [KeyCode::KeyW, KeyCode::KeyA, KeyCode::KeyS, KeyCode::KeyD, KeyCode::ArrowUp, KeyCode::ArrowDown]
        .iter()
        .any(|k| keys.pressed(*k));
    if rig.showcase && (moving || keys.just_pressed(KeyCode::KeyF)) {
        rig.showcase = false;
        rig.yaw = rig.orbit;
    }
    if d != Vec2::ZERO {
        rig.idle = 0.0;
        if rig.showcase && game.mode == Mode::Foot {
            // dragging during the intro orbits instead of cancelling it
            rig.orbit -= d.x * 0.0028;
            d = Vec2::ZERO;
        }
    } else {
        rig.idle += dt;
    }
    let zoom = scroll.delta.y;
    if !driving || rig.car_cam == CarCam::Orbit || game.mode == Mode::Exiting {
        if game.mode == Mode::Foot && !rig.showcase {
            rig.yaw -= d.x * s;
            rig.pitch = (rig.pitch - d.y * s).clamp(-1.2, 0.5);
            rig.dist = (rig.dist - zoom * 0.4).clamp(2.0, 12.0);
        } else {
            rig.orbit -= d.x * s;
            rig.off_pitch = (rig.off_pitch - d.y * s).clamp(-1.0, 0.4);
            rig.chase_dist = (rig.chase_dist - zoom * 0.5).clamp(3.5, 18.0);
        }
    } else {
        match rig.car_cam {
            CarCam::Chase => {
                rig.off_yaw -= d.x * s;
                rig.off_pitch = (rig.off_pitch - d.y * s).clamp(-0.9, 0.35);
                rig.chase_dist = (rig.chase_dist - zoom * 0.5).clamp(3.5, 18.0);
                if rig.idle > 1.5 {
                    let k = (2.5 * dt).min(1.0);
                    rig.off_yaw = angle_wrap(rig.off_yaw) * (1.0 - k);
                    rig.off_pitch *= 1.0 - k;
                }
            }
            CarCam::Interior | CarCam::Hood => {
                rig.look_yaw = (rig.look_yaw - d.x * s).clamp(-2.4, 2.4);
                rig.look_pitch = (rig.look_pitch - d.y * s).clamp(-1.0, 0.8);
            }
            CarCam::Orbit => {}
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn camera_follow(
    time: Res<Time>,
    game: Res<Game>,
    mut rig: ResMut<Rig>,
    mut cam: Query<(&mut Transform, &mut Projection), (With<Camera3d>, Without<Player>, Without<Car>)>,
    player: Query<&Transform, (With<Player>, Without<Camera3d>)>,
    cars: Query<(&Car, &Transform), (Without<Camera3d>, Without<Player>)>,
    seats: Query<(Entity, &DriverSeat), With<Humanoid>>,
    mut heads: Query<(&ChildOf, &mut Visibility), With<Head>>,
) {
    let dt = time.delta_secs().min(0.05);
    let Ok((mut ctf, mut proj)) = cam.single_mut() else { return };
    let Ok(ptf) = player.single() else { return };
    let mut fov_target = 62.0;
    let car = game.car.and_then(|e| cars.get(e).ok());
    let mut hide_head_of: Option<Entity> = None;
    let in_car_view = matches!(game.mode, Mode::Driving | Mode::Entering) && car.is_some();

    if in_car_view {
        let (c, tf) = car.unwrap();
        let body_rot = Quat::from_rotation_x(c.pitch) * Quat::from_rotation_z(c.roll);
        let car_rot = tf.rotation;
        let base = tf.translation;
        match rig.car_cam {
            CarCam::Chase => {
                let k = (3.5 * dt).min(1.0);
                let target_yaw = c.yaw + if c.speed < -2.0 { std::f32::consts::PI } else { 0.0 };
                rig.chase_yaw += angle_wrap(target_yaw - rig.chase_yaw) * k;
                let yaw = rig.chase_yaw + rig.off_yaw;
                let pitch = -0.2 + rig.off_pitch;
                let speed_k = (c.speed.abs() / 60.0).min(1.0);
                let dist = rig.chase_dist + speed_k * 1.5;
                let off = Quat::from_euler(EulerRot::YXZ, yaw, pitch, 0.0) * Vec3::new(0.0, 0.0, dist);
                let desired = base + Vec3::Y * 1.2 + off;
                let pk = (10.0 * dt).min(1.0);
                rig.pos = if rig.pos == Vec3::ZERO { desired } else { rig.pos.lerp(desired, pk) };
                rig.pos.y = rig.pos.y.max(base.y + 0.35);
                let look = base + Vec3::Y * 0.9 + Vec3::new(yaw_fwd(c.yaw).x, 0.0, yaw_fwd(c.yaw).y) * 1.5;
                *ctf = Transform::from_translation(rig.pos).looking_at(look, Vec3::Y);
                fov_target = 62.0 + speed_k * 16.0;
            }
            CarCam::Interior => {
                let eye = base + car_rot * (body_rot * EYE);
                let rot = car_rot * body_rot * Quat::from_euler(EulerRot::YXZ, rig.look_yaw, rig.look_pitch - 0.12, 0.0);
                *ctf = Transform::from_translation(eye).with_rotation(rot);
                rig.pos = eye;
                fov_target = 74.0;
                hide_head_of = seats.iter().find(|(_, s)| s.0 == game.car.unwrap()).map(|(e, _)| e);
            }
            CarCam::Hood => {
                let eye = base + car_rot * (body_rot * Vec3::new(0.0, 1.0, -1.1));
                let rot = car_rot * body_rot * Quat::from_euler(EulerRot::YXZ, rig.look_yaw, rig.look_pitch - 0.06, 0.0);
                *ctf = Transform::from_translation(eye).with_rotation(rot);
                rig.pos = eye;
                fov_target = 70.0 + (c.speed.abs() / 60.0).min(1.0) * 10.0;
            }
            CarCam::Orbit => {
                if rig.idle > 0.5 {
                    rig.orbit += dt * 0.25;
                }
                let center = base + Vec3::Y * 0.7;
                let off = Quat::from_euler(EulerRot::YXZ, rig.orbit, -0.25 + rig.off_pitch, 0.0) * Vec3::new(0.0, 0.0, rig.chase_dist.max(4.5));
                rig.pos = center + off;
                *ctf = Transform::from_translation(rig.pos).looking_at(center, Vec3::Y);
                fov_target = 50.0;
            }
        }
    } else if game.mode == Mode::Foot && rig.showcase {
        // intro: slow orbit around the nearest/starting car
        let center = car
            .map(|(_, t)| t.translation)
            .or_else(|| game.near.or(game.start_car).and_then(|e| cars.get(e).ok()).map(|(_, t)| t.translation))
            .unwrap_or(ptf.translation)
            + Vec3::Y * 0.7;
        rig.orbit += dt * 0.22;
        let off = Quat::from_euler(EulerRot::YXZ, rig.orbit, -0.22 + rig.off_pitch, 0.0) * Vec3::new(0.0, 0.0, rig.chase_dist.max(5.5));
        rig.pos = center + off;
        *ctf = Transform::from_translation(rig.pos).looking_at(center, Vec3::Y);
        fov_target = 48.0;
    } else {
        let target = ptf.translation + Vec3::Y * 1.55;
        let off = Quat::from_euler(EulerRot::YXZ, rig.yaw, rig.pitch, 0.0) * Vec3::new(0.0, 0.0, rig.dist);
        let right = Quat::from_rotation_y(rig.yaw) * Vec3::X * 0.45;
        let desired = target + off + right;
        let pk = (14.0 * dt).min(1.0);
        rig.pos = if rig.pos.distance(desired) > 20.0 { desired } else { rig.pos.lerp(desired, pk) };
        rig.pos.y = rig.pos.y.max(ground_h(rig.pos.xz()) + 0.25);
        *ctf = Transform::from_translation(rig.pos).looking_at(target + right, Vec3::Y);
        // keep the chase camera aligned for the moment we sit down
        rig.chase_yaw = car.map(|(c, _)| c.yaw).unwrap_or(rig.yaw);
    }

    rig.fov += (fov_target - rig.fov) * (4.0 * dt).min(1.0);
    if let Projection::Perspective(p) = proj.as_mut() {
        p.fov = rig.fov.to_radians();
    }
    for (parent, mut v) in &mut heads {
        let hide = hide_head_of == Some(parent.parent());
        let want = if hide { Visibility::Hidden } else { Visibility::Inherited };
        if *v != want {
            *v = want;
        }
    }
}
