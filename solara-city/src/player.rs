//! On-foot player controller and getting in/out of cars.
use bevy::prelude::*;

use crate::camera::Rig;
use crate::car::{car_circles, spawn_headlights, BodyRoot, Car, Door, DriverSeat, Headlight, PlayerDriven};
use crate::people::Humanoid;
use crate::traffic::Ai;
use crate::util::*;

#[derive(Component)]
pub struct Player {
    pub vy: f32,
    pub grounded: bool,
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Mode {
    Foot,
    Entering,
    Driving,
    Exiting,
}

#[derive(Resource)]
pub struct Game {
    pub mode: Mode,
    pub car: Option<Entity>,
    pub timer: f32,
    pub near: Option<Entity>,
    pub headlights: bool,
    pub from: Vec2,
    pub start_car: Option<Entity>,
}

impl Default for Game {
    fn default() -> Self {
        Self { mode: Mode::Foot, car: None, timer: 0.0, near: None, headlights: true, from: Vec2::ZERO, start_car: None }
    }
}

fn door_spot(c: &Car) -> Vec2 {
    c.pos - yaw_right(c.yaw) * 1.55 + yaw_fwd(c.yaw) * 0.05
}

#[allow(clippy::too_many_arguments)]
pub fn player_control(
    mut commands: Commands,
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    rig: Res<Rig>,
    mut game: ResMut<Game>,
    colliders: Res<Colliders>,
    mut player: Query<(&mut Transform, &mut Player, &mut Humanoid, &mut Visibility), Without<Car>>,
    mut cars: Query<(Entity, &mut Car, Option<&Ai>), Without<Player>>,
    bodies: Query<(Entity, &BodyRoot)>,
    mut doors: Query<&mut Door>,
    mut drivers: Query<(&DriverSeat, &mut Visibility), Without<Player>>,
    lights: Query<Entity, With<Headlight>>,
) {
    let dt = time.delta_secs().min(0.05);
    let Ok((mut tf, mut pl, mut hum, mut vis)) = player.single_mut() else { return };
    let set_door = |doors: &mut Query<&mut Door>, car: Entity, left_only: bool, target: f32| {
        for mut d in doors.iter_mut() {
            if d.car == car && (!left_only || d.side < 0.0) {
                d.target = target;
            }
        }
    };
    let body_of = |car: Entity| bodies.iter().find(|(_, b)| b.0 == car).map(|(e, _)| e);

    if keys.just_pressed(KeyCode::KeyH) {
        game.headlights = !game.headlights;
        if game.mode == Mode::Driving {
            if game.headlights {
                if let Some(b) = game.car.and_then(body_of) {
                    spawn_headlights(&mut commands, b);
                }
            } else {
                for e in &lights {
                    commands.entity(e).despawn();
                }
            }
        }
    }

    match game.mode {
        Mode::Foot => {
            let fwd = yaw_fwd(rig.yaw);
            let right = yaw_right(rig.yaw);
            let mut dir = Vec2::ZERO;
            if keys.pressed(KeyCode::KeyW) || keys.pressed(KeyCode::ArrowUp) {
                dir += fwd;
            }
            if keys.pressed(KeyCode::KeyS) || keys.pressed(KeyCode::ArrowDown) {
                dir -= fwd;
            }
            if keys.pressed(KeyCode::KeyD) || keys.pressed(KeyCode::ArrowRight) {
                dir += right;
            }
            if keys.pressed(KeyCode::KeyA) || keys.pressed(KeyCode::ArrowLeft) {
                dir -= right;
            }
            let run = keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight);
            let speed = if run { 6.5 } else { 2.2 };
            let mut pos = tf.translation.xz();
            if dir != Vec2::ZERO {
                dir = dir.normalize();
                pos += dir * speed * dt;
                let target = Quat::from_rotation_y(yaw_from_dir(dir));
                tf.rotation = tf.rotation.slerp(target, (12.0 * dt).min(1.0));
                hum.speed = speed;
            } else {
                hum.speed = 0.0;
                hum.phase *= 0.9;
            }
            if let Some((push, _)) = colliders.resolve(pos, 0.35) {
                pos += push;
            }
            let mut nearest: Option<(Entity, f32)> = None;
            for (e, c, _) in &cars {
                for cc in car_circles(c.pos, c.yaw) {
                    let d = pos - cc;
                    let l = d.length();
                    if l < 1.3 && l > 1e-4 {
                        pos += d / l * (1.3 - l);
                    }
                }
                let dist = pos.distance(door_spot(&c)).min(pos.distance(c.pos) - 1.0);
                if dist < 2.6 && nearest.map_or(true, |(_, d)| dist < d) {
                    nearest = Some((e, dist));
                }
            }
            let m = city_max();
            pos = pos.clamp(Vec2::splat(-80.0), Vec2::new(m + 120.0, m + 80.0));
            game.near = nearest.map(|(e, _)| e);

            let gh = ground_h(pos);
            if keys.just_pressed(KeyCode::Space) && pl.grounded {
                pl.vy = 5.2;
                pl.grounded = false;
            }
            pl.vy -= 15.0 * dt;
            let mut y = tf.translation.y + pl.vy * dt;
            if y <= gh {
                y = if gh - y < 0.3 || pl.grounded { gh } else { y.max(gh) };
                pl.vy = 0.0;
                pl.grounded = true;
            } else if y - gh > 0.05 {
                pl.grounded = false;
            }
            tf.translation = Vec3::new(pos.x, y, pos.y);

            if keys.just_pressed(KeyCode::KeyF) {
                if let Some(e) = game.near {
                    if let Ok((_, mut c, ai)) = cars.get_mut(e) {
                        if ai.is_some() {
                            commands.entity(e).remove::<Ai>();
                        }
                        c.speed = 0.0;
                        c.vel = Vec2::ZERO;
                        c.braking = true;
                    }
                    set_door(&mut doors, e, true, 1.0);
                    game.mode = Mode::Entering;
                    game.car = Some(e);
                    game.timer = 0.0;
                    game.from = pos;
                    game.near = None;
                }
            }
            if keys.just_pressed(KeyCode::KeyG) {
                if let Some(e) = game.near {
                    let open = doors.iter().any(|d| d.car == e && d.target > 0.5);
                    set_door(&mut doors, e, false, if open { 0.0 } else { 1.0 });
                }
            }
        }
        Mode::Entering => {
            game.timer += dt;
            let Some(e) = game.car else { game.mode = Mode::Foot; return };
            let Ok((_, c, _)) = cars.get(e) else { game.mode = Mode::Foot; return };
            let spot = door_spot(&c);
            let k = (game.timer / 0.45).min(1.0);
            let p = game.from.lerp(spot, k);
            tf.translation = Vec3::new(p.x, ground_h(p), p.y);
            let to_car = (c.pos - p).normalize_or_zero();
            if to_car != Vec2::ZERO {
                tf.rotation = Quat::from_rotation_y(yaw_from_dir(to_car));
            }
            hum.speed = 1.8;
            if game.timer > 0.75 {
                *vis = Visibility::Hidden;
                for (d, mut v) in &mut drivers {
                    if d.0 == e {
                        *v = Visibility::Inherited;
                    }
                }
                set_door(&mut doors, e, false, 0.0);
                commands.entity(e).insert(PlayerDriven);
                if game.headlights {
                    if let Some(b) = body_of(e) {
                        spawn_headlights(&mut commands, b);
                    }
                }
                game.mode = Mode::Driving;
            }
        }
        Mode::Driving => {
            let Some(e) = game.car else { game.mode = Mode::Foot; return };
            let Ok((_, c, _)) = cars.get(e) else { game.mode = Mode::Foot; return };
            tf.translation = Vec3::new(c.pos.x, c.y, c.pos.y);
            if keys.just_pressed(KeyCode::KeyG) && c.speed.abs() < 1.0 {
                let open = doors.iter().any(|d| d.car == e && d.target > 0.5);
                set_door(&mut doors, e, false, if open { 0.0 } else { 1.0 });
            }
            if keys.just_pressed(KeyCode::KeyF) && c.speed.abs() < 3.0 {
                game.mode = Mode::Exiting;
                game.timer = 0.0;
                set_door(&mut doors, e, true, 1.0);
                commands.entity(e).remove::<PlayerDriven>();
                if let Ok((_, mut c, _)) = cars.get_mut(e) {
                    c.speed = 0.0;
                    c.vel = Vec2::ZERO;
                    c.braking = true;
                    c.steer = 0.0;
                }
            }
        }
        Mode::Exiting => {
            game.timer += dt;
            let Some(e) = game.car else { game.mode = Mode::Foot; return };
            let Ok((_, c, _)) = cars.get(e) else { game.mode = Mode::Foot; return };
            if game.timer > 0.35 && *vis == Visibility::Hidden {
                *vis = Visibility::Inherited;
                for (d, mut v) in &mut drivers {
                    if d.0 == e {
                        *v = Visibility::Hidden;
                    }
                }
                for l in &lights {
                    commands.entity(l).despawn();
                }
            }
            let spot = door_spot(&c);
            let out = spot - yaw_right(c.yaw) * 0.9;
            let k = ((game.timer - 0.35) / 0.4).clamp(0.0, 1.0);
            let p = spot.lerp(out, k);
            tf.translation = Vec3::new(p.x, ground_h(p), p.y);
            tf.rotation = Quat::from_rotation_y(yaw_from_dir(-yaw_right(c.yaw)));
            hum.speed = if k < 1.0 { 1.5 } else { 0.0 };
            if game.timer > 0.85 {
                set_door(&mut doors, e, false, 0.0);
                game.mode = Mode::Foot;
                game.car = None;
            }
        }
    }
}
