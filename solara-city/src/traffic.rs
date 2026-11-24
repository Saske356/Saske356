//! AI traffic: cars follow lanes on the road grid, turn at intersections,
//! obey traffic lights and keep distance to whatever is ahead.
use bevy::prelude::*;

use crate::car::{Car, PlayerDriven, WHEELBASE};
use crate::mats::Mats;
use crate::util::*;

#[derive(Resource, Default)]
pub struct Lights {
    pub t: f32,
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Light {
    Red,
    Yellow,
    Green,
}

const CYCLE: f32 = 34.0;
impl Lights {
    pub fn state(&self, axis: usize) -> Light {
        let t = (self.t + if axis == 1 { CYCLE * 0.5 } else { 0.0 }) % CYCLE;
        if t < 13.5 {
            Light::Green
        } else if t < 16.5 {
            Light::Yellow
        } else {
            Light::Red
        }
    }
}

pub fn dvec(d: u8) -> Vec2 {
    match d % 4 {
        0 => Vec2::X,
        1 => Vec2::Y,
        2 => Vec2::NEG_X,
        _ => Vec2::NEG_Y,
    }
}
fn rvec(d: u8) -> Vec2 {
    let v = dvec(d);
    Vec2::new(-v.y, v.x)
}
fn valid(n: IVec2) -> bool {
    n.x >= 0 && n.y >= 0 && n.x <= N && n.y <= N
}
fn npos(n: IVec2) -> Vec2 {
    n.as_vec2() * S
}
const STOP: f32 = ROAD * 0.5 + 4.9;

fn lane_pt(n: IVec2, d: u8, lane: u8, dist: f32) -> Vec2 {
    npos(n) + dvec(d) * dist + rvec(d) * LANES[lane as usize]
}

fn bez(p: &[Vec2; 3], t: f32) -> (Vec2, Vec2) {
    let u = 1.0 - t;
    let pos = p[0] * u * u + p[1] * 2.0 * u * t + p[2] * t * t;
    let tan = (p[1] - p[0]) * 2.0 * u + (p[2] - p[1]) * 2.0 * t;
    (pos, tan.normalize_or_zero())
}
fn bez_len(p: &[Vec2; 3]) -> f32 {
    let mut l = 0.0;
    let mut prev = p[0];
    for k in 1..=12 {
        let (q, _) = bez(p, k as f32 / 12.0);
        l += q.distance(prev);
        prev = q;
    }
    l.max(0.01)
}

#[derive(Component)]
pub struct Ai {
    pub b: IVec2,
    pub d: u8,
    pub lane: u8,
    pub turning: bool,
    pub d2: u8,
    pub lane2: u8,
    pub p: [Vec2; 3],
    pub len: f32,
    pub s: f32,
    pub vmax: f32,
}

impl Ai {
    pub fn on_segment(a: IVec2, d: u8, lane: u8, frac: f32, vmax: f32) -> Self {
        let b = a + dvec(d).as_ivec2();
        let p0 = lane_pt(a, d, lane, ROAD * 0.5);
        let p2 = lane_pt(b, d, lane, -STOP);
        let p = [p0, (p0 + p2) * 0.5, p2];
        let len = bez_len(&p);
        Self { b, d, lane, turning: false, d2: d, lane2: lane, p, len, s: len * frac, vmax }
    }
}

pub fn spawn_points(rng: &mut Rng, count: usize) -> Vec<(Ai, Vec2, f32)> {
    let mut out: Vec<(Ai, Vec2, f32)> = Vec::new();
    let mut tries = 0;
    while out.len() < count && tries < count * 30 {
        tries += 1;
        let a = IVec2::new(rng.int(N as u32 + 1) as i32, rng.int(N as u32 + 1) as i32);
        let d = rng.int(4) as u8;
        if !valid(a + dvec(d).as_ivec2()) {
            continue;
        }
        let lane = rng.int(2) as u8;
        let ai = Ai::on_segment(a, d, lane, rng.range(0.0, 0.85), rng.range(10.0, 15.0));
        let (pos, tan) = bez(&ai.p, ai.s / ai.len);
        if out.iter().any(|(_, p, _)| p.distance(pos) < 12.0) {
            continue;
        }
        out.push((ai, pos, yaw_from_dir(tan)));
    }
    out
}

pub fn update_lights(time: Res<Time>, mut lights: ResMut<Lights>, mats: Res<Mats>, mut materials: ResMut<Assets<StandardMaterial>>) {
    let prev = [lights.state(0), lights.state(1)];
    lights.t += time.delta_secs();
    let now = [lights.state(0), lights.state(1)];
    if prev == now && lights.t > 0.1 {
        return;
    }
    let emissive = [
        LinearRgba::rgb(14.0, 0.6, 0.4),
        LinearRgba::rgb(12.0, 7.0, 0.5),
        LinearRgba::rgb(0.5, 12.0, 4.0),
    ];
    for axis in 0..2 {
        let on = match now[axis] {
            Light::Red => 0,
            Light::Yellow => 1,
            Light::Green => 2,
        };
        for c in 0..3 {
            if let Some(m) = materials.get_mut(&mats.tl[axis][c]) {
                m.emissive = if c == on { emissive[c] } else { LinearRgba::BLACK };
            }
        }
    }
}

pub fn drive_ai(
    time: Res<Time>,
    lights: Res<Lights>,
    mut rng: Local<Option<Rng>>,
    mut ai_q: Query<(Entity, &mut Ai, &mut Car, &mut Transform), Without<PlayerDriven>>,
    player_car: Query<&Car, (With<PlayerDriven>, Without<Ai>)>,
    player: Query<&Transform, (With<crate::player::Player>, Without<Car>)>,
) {
    let rng = rng.get_or_insert_with(|| Rng::new(99));
    let dt = time.delta_secs().min(0.05);
    // snapshot of everything that can block a lane
    let mut obstacles: Vec<(Entity, Vec2)> = ai_q.iter().map(|(e, _, c, _)| (e, c.pos)).collect();
    for c in &player_car {
        obstacles.push((Entity::PLACEHOLDER, c.pos));
    }
    for t in &player {
        obstacles.push((Entity::PLACEHOLDER, t.translation.xz()));
    }
    for (me, mut ai, mut car, mut tf) in &mut ai_q {
        let (pos, tan) = bez(&ai.p, (ai.s / ai.len).clamp(0.0, 1.0));
        let mut target = ai.vmax;
        if !ai.turning {
            let remaining = ai.len - ai.s;
            if remaining < 22.0 {
                target = target.min(if ai.d2 == ai.d { ai.vmax } else { 8.0 }.max(6.0 + remaining * 0.4));
            }
            let st = lights.state((ai.d % 2) as usize);
            let committed = st == Light::Yellow && remaining < 1.5 + car.speed * 0.35;
            if st != Light::Green && !committed {
                target = target.min((2.0 * 5.5 * (remaining - 0.4).max(0.0)).sqrt());
            }
        } else if ai.d2 != ai.d {
            target = target.min(7.5);
        }
        for (e, op) in &obstacles {
            if *e == me {
                continue;
            }
            let rel = *op - pos;
            let ahead = rel.dot(tan);
            let lat = rel.perp_dot(tan).abs();
            if ahead > 0.0 && ahead < 20.0 && lat < 2.2 {
                target = target.min(((ahead - 6.0).max(0.0)) * 1.4);
            }
        }
        let before = car.speed;
        if car.speed < target {
            car.speed = (car.speed + 3.5 * dt).min(target);
        } else {
            car.speed = (car.speed - 9.0 * dt).max(target);
        }
        car.braking = car.speed < before - 0.01 || (car.speed < 0.2 && target < 0.5);
        ai.s += car.speed * dt;
        if ai.s >= ai.len {
            let carry = ai.s - ai.len;
            if !ai.turning {
                // choose where to go at the intersection
                let opts = [(ai.d, 0.5f32), ((ai.d + 3) % 4, 0.25), ((ai.d + 1) % 4, 0.25)];
                let mut choice = ai.d;
                let total: f32 = opts.iter().filter(|(d, _)| valid(ai.b + dvec(*d).as_ivec2())).map(|(_, w)| w).sum();
                let mut r = rng.f() * total;
                for (d, w) in opts {
                    if !valid(ai.b + dvec(d).as_ivec2()) {
                        continue;
                    }
                    choice = d;
                    if r < w {
                        break;
                    }
                    r -= w;
                }
                if !valid(ai.b + dvec(choice).as_ivec2()) {
                    choice = (ai.d + 2) % 4; // dead end: U-turn
                }
                ai.d2 = choice;
                ai.lane2 = if choice == (ai.d + 1) % 4 {
                    1
                } else if choice == (ai.d + 3) % 4 {
                    0
                } else {
                    ai.lane
                };
                let p0 = ai.p[2];
                let p2 = lane_pt(ai.b, ai.d2, ai.lane2, ROAD * 0.5);
                let p1 = if ai.d2 == ai.d || ai.d2 == (ai.d + 2) % 4 {
                    if ai.d2 == ai.d { (p0 + p2) * 0.5 } else { npos(ai.b) }
                } else {
                    p0 + dvec(ai.d) * (p2 - p0).dot(dvec(ai.d))
                };
                ai.p = [p0, p1, p2];
                ai.turning = true;
            } else {
                let a = ai.b;
                ai.d = ai.d2;
                ai.lane = ai.lane2;
                ai.b = a + dvec(ai.d).as_ivec2();
                let p0 = ai.p[2];
                let p2 = lane_pt(ai.b, ai.d, ai.lane, -STOP);
                ai.p = [p0, (p0 + p2) * 0.5, p2];
                ai.turning = false;
                ai.d2 = ai.d;
            }
            ai.len = bez_len(&ai.p);
            ai.s = carry;
        }
        let (np, nt) = bez(&ai.p, (ai.s / ai.len).clamp(0.0, 1.0));
        let new_yaw = yaw_from_dir(if nt == Vec2::ZERO { tan } else { nt });
        let dyaw = angle_wrap(new_yaw - car.yaw);
        let yaw_rate = dyaw / dt.max(1e-4);
        car.steer = if car.speed > 0.5 { (yaw_rate * WHEELBASE / car.speed).atan().clamp(-0.6, 0.6) } else { car.steer * 0.9 };
        car.roll += ((-car.speed * yaw_rate * 0.004).clamp(-0.04, 0.04) - car.roll) * (5.0 * dt).min(1.0);
        car.pitch += ((((car.speed - before) / dt.max(1e-4)) * 0.003).clamp(-0.03, 0.02) - car.pitch) * (5.0 * dt).min(1.0);
        car.yaw = new_yaw;
        car.pos = np;
        car.vel = nt * car.speed;
        car.rpm = 900.0 + (car.speed / 15.0) * 3000.0;
        car.gear = 1 + (car.speed / 6.0) as i32;
        tf.translation = Vec3::new(np.x, 0.0, np.y);
        tf.rotation = Quat::from_rotation_y(new_yaw);
    }
}
