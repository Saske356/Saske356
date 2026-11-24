//! Detailed procedural sports car: lofted body, opening doors, glass canopy,
//! mid-engine under glass, full interior with working gauges and steering wheel,
//! multi-part wheels with brake discs and calipers, plus arcade driving physics.
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

use bevy::prelude::*;

use crate::mats::{car_paint, tail_mat, Mats, Slot};
use crate::mesh::{loft, Mb};
use crate::people::{spawn_human, Look, PeopleAssets, Pose};
use crate::util::*;

pub const WB_F: f32 = -1.36;
pub const WB_R: f32 = 1.30;
pub const WHEELBASE: f32 = WB_R - WB_F;
pub const WR: f32 = 0.335;
pub const TRACK: f32 = 0.80;
const AR: f32 = 0.40;
const CAB0: f32 = -0.62;
const CAB1: f32 = 1.06;
const ROOF0: f32 = -0.06;
const ROOF1: f32 = 0.70;
const DOOR0: f32 = -0.56;
const DOOR1: f32 = 0.74;
const ENG0: f32 = 1.12;
const ENG1: f32 = 1.72;
const ZF: f32 = -2.28;
const ZR: f32 = 2.27;
pub const SEAT_X: f32 = -0.38;
pub const EYE: Vec3 = Vec3::new(SEAT_X, 1.06, 0.20);
pub const DOOR_HINGE_Y: f32 = 0.55;

const HW: &[(f32, f32)] = &[
    (-2.28, 0.66),
    (-2.20, 0.84),
    (-2.0, 0.925),
    (-1.6, 0.965),
    (-1.3, 0.975),
    (-0.9, 0.955),
    (-0.3, 0.945),
    (0.4, 0.95),
    (1.0, 0.975),
    (1.4, 0.99),
    (1.8, 0.975),
    (2.1, 0.93),
    (2.27, 0.84),
];
const YT: &[(f32, f32)] = &[
    (-2.28, 0.44),
    (-2.2, 0.56),
    (-2.0, 0.64),
    (-1.6, 0.73),
    (-1.3, 0.78),
    (-0.9, 0.81),
    (-0.62, 0.83),
    (0.0, 0.86),
    (0.8, 0.89),
    (1.4, 0.915),
    (1.9, 0.925),
    (2.15, 0.91),
    (2.27, 0.82),
];
const YB: &[(f32, f32)] = &[(-2.28, 0.28), (-2.18, 0.17), (-2.0, 0.135), (1.9, 0.135), (2.12, 0.20), (2.27, 0.34)];
const GHT: &[(f32, f32)] = &[
    (-0.62, 0.83),
    (-0.35, 1.02),
    (-0.06, 1.215),
    (0.2, 1.25),
    (0.5, 1.24),
    (0.72, 1.20),
    (0.9, 1.07),
    (1.06, 0.905),
];

fn cr(t: &[(f32, f32)], z: f32) -> f32 {
    let n = t.len();
    if z <= t[0].0 {
        return t[0].1;
    }
    if z >= t[n - 1].0 {
        return t[n - 1].1;
    }
    let mut i = 0;
    while i + 1 < n && t[i + 1].0 < z {
        i += 1;
    }
    let p0 = if i == 0 { t[0].1 } else { t[i - 1].1 };
    let p1 = t[i].1;
    let p2 = t[i + 1].1;
    let p3 = if i + 2 < n { t[i + 2].1 } else { t[n - 1].1 };
    let u = (z - t[i].0) / (t[i + 1].0 - t[i].0);
    0.5 * ((2.0 * p1)
        + (-p0 + p2) * u
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * u * u
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * u * u * u)
}

fn hw(z: f32) -> f32 {
    cr(HW, z)
}
fn yt(z: f32) -> f32 {
    cr(YT, z)
}
fn yb(z: f32) -> f32 {
    let mut y = cr(YB, z);
    for a in [WB_F, WB_R] {
        let d = (z - a).abs();
        if d < AR {
            y = y.max(WR + (AR * AR - d * d).sqrt() * 0.98);
        }
    }
    y
}
fn ght(z: f32) -> f32 {
    cr(GHT, z).max(yt(z))
}
const N_TOP: f32 = 3.0;
const N_BOT: f32 = 7.0;
fn sp(v: f32, e: f32) -> f32 {
    v.signum() * v.abs().powf(e)
}
/// Outer surface x at (z, y) for the lower body.
fn body_x(z: f32, y: f32) -> f32 {
    let (t, b) = (yt(z), yb(z));
    let yc = (t + b) * 0.5;
    let hh = ((t - b) * 0.5).max(0.005);
    let s = ((y - yc) / hh).clamp(-1.0, 1.0);
    let n = if s >= 0.0 { N_TOP } else { N_BOT };
    hw(z) * (1.0 - s.abs().powf(n)).max(0.0).powf(1.0 / n)
}
/// Top surface y at (z, x).
fn body_y(z: f32, x: f32) -> f32 {
    let (t, b) = (yt(z), yb(z));
    let yc = (t + b) * 0.5;
    let hh = ((t - b) * 0.5).max(0.005);
    let c = (x / hw(z)).clamp(-1.0, 1.0);
    yc + hh * (1.0 - c.abs().powf(N_TOP)).max(0.0).powf(1.0 / N_TOP)
}
fn surf_rot(z: f32, x: f32) -> Quat {
    let e = 0.02;
    let dydz = (body_y(z + e, x) - body_y(z - e, x)) / (2.0 * e);
    let dydx = (body_y(z, x + e) - body_y(z, x - e)) / (2.0 * e);
    let n = Vec3::new(-dydx, 1.0, -dydz).normalize();
    Quat::from_rotation_arc(Vec3::Y, n)
}

fn body_ring(z: f32, m: usize) -> Vec<Vec3> {
    let (w, t, b) = (hw(z), yt(z), yb(z));
    let yc = (t + b) * 0.5;
    let hh = ((t - b) * 0.5).max(0.005);
    (0..m)
        .map(|j| {
            let th = j as f32 / m as f32 * TAU;
            let (s, c) = th.sin_cos();
            let n = if s >= 0.0 { N_TOP } else { N_BOT };
            Vec3::new(w * sp(c, 2.0 / n), yc + hh * sp(s, 2.0 / n), z)
        })
        .collect()
}

const GK: usize = 24;
const GW: f32 = 0.80; // canopy base as a fraction of body half-width
fn gh_point(z: f32, th: f32) -> Vec3 {
    let w = hw(z) * GW;
    let b = body_y(z, w) - 0.006;
    let t = ght(z);
    let (s, c) = th.sin_cos();
    let x0 = sp(c, 2.0 / 5.0);
    let y0 = sp(s.max(0.0), 2.0 / 5.0);
    let tum = 1.0 - 0.22 * y0;
    Vec3::new(x0 * w * tum, b + (t - b) * y0, z)
}
fn gh_ring(z: f32) -> Vec<Vec3> {
    (0..=GK).map(|j| gh_point(z, PI * j as f32 / GK as f32)).collect()
}

fn stations(a: f32, b: f32, n: usize, extra: &[f32]) -> Vec<f32> {
    let mut v: Vec<f32> = (0..=n).map(|i| a + (b - a) * i as f32 / n as f32).collect();
    for e in extra {
        if *e >= a && *e <= b {
            v.push(*e);
        }
    }
    v.sort_by(|x, y| x.partial_cmp(y).unwrap());
    let mut out: Vec<f32> = Vec::new();
    for z in v {
        if out.last().map_or(true, |l| (z - *l).abs() > 0.0015) {
            out.push(z);
        } else if extra.iter().any(|e| (*e - z).abs() < 1e-6) {
            *out.last_mut().unwrap() = z;
        }
    }
    out
}

type Parts = HashMap<Slot, Mb>;
fn pm<'a>(p: &'a mut Parts, s: Slot) -> &'a mut Mb {
    p.entry(s).or_default()
}

#[derive(Resource, Clone)]
pub struct CarModel {
    pub body: Vec<(Handle<Mesh>, Slot)>,
    pub doors: [Vec<(Handle<Mesh>, Slot)>; 2],
    pub hinges: [Vec3; 2],
    pub wheel_spin: Vec<(Handle<Mesh>, Slot)>,
    pub wheel_fixed: Vec<(Handle<Mesh>, Slot)>,
    pub steering: Vec<(Handle<Mesh>, Slot)>,
    pub steering_pos: Vec3,
    pub steering_tilt: Quat,
    pub needle: Handle<Mesh>,
    pub gauges: [Vec3; 2],
}

fn to_handles(p: Parts, meshes: &mut Assets<Mesh>) -> Vec<(Handle<Mesh>, Slot)> {
    let mut v: Vec<(Handle<Mesh>, Slot)> = p
        .into_iter()
        .filter(|(_, mb)| !mb.is_empty())
        .map(|(s, mb)| (meshes.add(mb.build()), s))
        .collect();
    v.sort_by_key(|(_, s)| *s as u32);
    v
}

pub fn build_car_model(meshes: &mut Assets<Mesh>) -> CarModel {
    let mut body: Parts = HashMap::new();
    let mut door: [Parts; 2] = [HashMap::new(), HashMap::new()]; // 0 = left (x<0), 1 = right
    let side_idx = |x: f32| if x < 0.0 { 0 } else { 1 };
    let in_door = |z: f32| z > DOOR0 && z < DOOR1;

    // ---------- lower body shell ----------
    let mut extra = vec![DOOR0, DOOR1, CAB0, CAB1, ENG0, ENG1];
    for a in [WB_F, WB_R] {
        for d in [-AR - 0.004, -AR + 0.004, AR - 0.004, AR + 0.004] {
            extra.push(a + d);
        }
    }
    let zs = stations(ZF, ZR, 84, &extra);
    let rings: Vec<Vec<Vec3>> = zs.iter().map(|z| body_ring(*z, 40)).collect();
    loft(&rings, true, |p, n| {
        let c = (p[0] + p[1] + p[2] + p[3]) * 0.25;
        let nn = (n[0] + n[1] + n[2] + n[3]).normalize_or_zero();
        let uv = [Vec2::ZERO; 4];
        // cabin opening and engine glass
        if c.z > CAB0 && c.z < CAB1 && nn.y > 0.55 && c.x.abs() < hw(c.z) * (GW - 0.02) {
            return;
        }
        if c.z > ENG0 && c.z < ENG1 && nn.y > 0.6 && c.x.abs() < 0.5 {
            return;
        }
        if in_door(c.z) && nn.x.abs() > 0.5 && c.y > yb(c.z) + 0.07 {
            pm(&mut door[side_idx(c.x)], Slot::Paint).quad_n(p, n, uv);
        } else {
            pm(&mut body, Slot::Paint).quad_n(p, n, uv);
        }
    });
    // nose / tail caps
    for (z, hint) in [(zs[0], -Vec3::Z), (*zs.last().unwrap(), Vec3::Z)] {
        let r = body_ring(z, 40);
        let c = r.iter().copied().sum::<Vec3>() / r.len() as f32;
        pm(&mut body, Slot::Paint).fan(c, &r, hint);
    }

    // ---------- glass canopy, roof, headliner ----------
    let gzs = stations(CAB0, CAB1, 40, &[ROOF0, ROOF1, DOOR0, DOOR1]);
    let grings: Vec<Vec<Vec3>> = gzs.iter().map(|z| gh_ring(*z)).collect();
    loft(&grings, false, |p, n| {
        let c = (p[0] + p[1] + p[2] + p[3]) * 0.25;
        let nn = (n[0] + n[1] + n[2] + n[3]).normalize_or_zero();
        let uv = [Vec2::ZERO; 4];
        if nn.y > 0.8 && c.z > ROOF0 && c.z < ROOF1 {
            let off = |v: [Vec3; 4], d: f32| [v[0] + n[0] * d, v[1] + n[1] * d, v[2] + n[2] * d, v[3] + n[3] * d];
            pm(&mut body, Slot::BlackGloss).quad_n(off(p, 0.006), n, uv);
            let inv = [-n[0], -n[1], -n[2], -n[3]];
            pm(&mut body, Slot::Fabric).quad_n(off(p, -0.035), inv, uv);
        } else if nn.x.abs() > 0.45 && in_door(c.z) {
            pm(&mut door[side_idx(c.x)], Slot::Glass).quad_n(p, n, uv);
        } else {
            pm(&mut body, Slot::Glass).quad_n(p, n, uv);
        }
    });
    // pillars / canopy frame along the shoulder line, B-pillars, beltline chrome
    for side in [0.25 * PI, 0.75 * PI] {
        let pts: Vec<Vec3> = gzs.iter().map(|z| gh_point(*z, side)).collect();
        for w in pts.windows(2) {
            let o = Vec3::new(if side < FRAC_PI_2 { 0.006 } else { -0.006 }, 0.006, 0.0);
            pm(&mut body, Slot::BlackGloss).seg(w[0] + o, w[1] + o, 0.055, 0.035);
        }
        // B pillar
        let mut prev = gh_point(DOOR1 + 0.01, if side < FRAC_PI_2 { 0.0 } else { PI });
        for k in 1..=6 {
            let th = if side < FRAC_PI_2 { side * k as f32 / 6.0 } else { PI - (PI - side) * k as f32 / 6.0 };
            let q = gh_point(DOOR1 + 0.01, th);
            pm(&mut body, Slot::BlackGloss).seg(prev, q, 0.05, 0.07);
            prev = q;
        }
        // beltline chrome
        let base_th = if side < FRAC_PI_2 { 0.0 } else { PI };
        let bpts: Vec<Vec3> = gzs.iter().map(|z| gh_point(*z, base_th)).collect();
        for w in bpts.windows(2) {
            let mid = (w[0] + w[1]) * 0.5;
            let o = Vec3::new(mid.x.signum() * 0.01, 0.004, 0.0);
            let target = if in_door(mid.z) { pm(&mut door[side_idx(mid.x)], Slot::Chrome) } else { pm(&mut body, Slot::Chrome) };
            target.seg(w[0] + o, w[1] + o, 0.018, 0.018);
        }
    }

    // ---------- wheel arch liners ----------
    for a in [WB_F, WB_R] {
        for sx in [-1.0f32, 1.0] {
            let x0 = sx * (TRACK - 0.2);
            let x1 = sx * (hw(a) - 0.015);
            let segs = 16;
            for k in 0..segs {
                let t0 = PI * k as f32 / segs as f32;
                let t1 = PI * (k + 1) as f32 / segs as f32;
                let r = AR - 0.01;
                let p = |t: f32, x: f32| Vec3::new(x, WR + t.sin() * r, a - t.cos() * r);
                let nrm = |t: f32| Vec3::new(0.0, -t.sin(), t.cos());
                pm(&mut body, Slot::BlackMatte).quad_n(
                    [p(t0, x0), p(t0, x1), p(t1, x1), p(t1, x0)],
                    [nrm(t0), nrm(t0), nrm(t1), nrm(t1)],
                    [Vec2::ZERO; 4],
                );
            }
        }
    }

    // ---------- front end ----------
    {
        let b = &mut body;
        // headlights: housing, glass, DRL strip, twin projectors
        for sx in [-1.0f32, 1.0] {
            let z = -1.98;
            let x = sx * 0.6;
            let y = body_y(z, x);
            let rot = surf_rot(z, x) * Quat::from_rotation_y(sx * 0.28);
            let up = rot * Vec3::Y;
            pm(b, Slot::BlackGloss).cuboid(Vec3::new(x, y - 0.012, z), Vec3::new(0.36, 0.05, 0.24), rot);
            pm(b, Slot::Lens).cuboid(Vec3::new(x, y + 0.006, z) + up * 0.004, Vec3::new(0.37, 0.02, 0.25), rot);
            pm(b, Slot::HeadLed).cuboid(
                Vec3::new(x, y + 0.01, z) + rot * Vec3::new(0.0, 0.0, -0.1),
                Vec3::new(0.32, 0.012, 0.018),
                rot,
            );
            for k in [-0.07f32, 0.07] {
                let c = Vec3::new(x, y, z) + rot * Vec3::new(k, 0.0, 0.03);
                pm(b, Slot::Chrome).sphere(c, Vec3::splat(0.035), rot, 8);
                pm(b, Slot::HeadLed).sphere(c + up * 0.012, Vec3::new(0.025, 0.01, 0.025), rot, 6);
            }
            // turn signal
            pm(b, Slot::OrangeLed).cuboid(
                Vec3::new(x + sx * 0.16, y - 0.005, z + 0.06),
                Vec3::new(0.04, 0.012, 0.08),
                rot,
            );
        }
        // central intake with slats, side intakes, splitter
        let zf = -2.24;
        pm(b, Slot::BlackMatte).bx(Vec3::new(0.0, 0.27, zf + 0.06), Vec3::new(0.9, 0.15, 0.14));
        for k in 0..4 {
            pm(b, Slot::BlackGloss).bx(Vec3::new(0.0, 0.215 + k as f32 * 0.035, zf - 0.005), Vec3::new(0.88, 0.008, 0.02));
        }
        for sx in [-1.0f32, 1.0] {
            pm(b, Slot::BlackMatte).cuboid(
                Vec3::new(sx * 0.66, 0.25, -2.14),
                Vec3::new(0.26, 0.13, 0.12),
                Quat::from_rotation_y(sx * 0.5),
            );
            // fog light
            pm(b, Slot::HeadLed).cuboid(Vec3::new(sx * 0.66, 0.25, -2.205), Vec3::new(0.08, 0.025, 0.01), Quat::from_rotation_y(sx * 0.5));
        }
        pm(b, Slot::Carbon).bx(Vec3::new(0.0, 0.135, -2.17), Vec3::new(1.62, 0.025, 0.24));
        // front plate
        pm(b, Slot::Plate).bx(Vec3::new(0.0, 0.40, -2.285), Vec3::new(0.5, 0.11, 0.012));
        // badge
        pm(b, Slot::Chrome).cyl(Vec3::new(0.0, 0.53, -2.235), 0.04, 0.01, 16, Quat::from_rotation_x(FRAC_PI_2 + 0.9));
        // hood vents
        for sx in [-1.0f32, 1.0] {
            let z = -1.35;
            let x = sx * 0.28;
            let rot = surf_rot(z, x);
            let y = body_y(z, x);
            pm(b, Slot::BlackMatte).cuboid(Vec3::new(x, y + 0.001, z), Vec3::new(0.24, 0.012, 0.32), rot);
            for k in 0..5 {
                pm(b, Slot::Carbon).cuboid(
                    Vec3::new(x, y + 0.006, z - 0.12 + k as f32 * 0.06),
                    Vec3::new(0.22, 0.01, 0.012),
                    rot,
                );
            }
        }
        // wipers
        for (x, a) in [(-0.35f32, 0.12f32), (0.25, 0.05)] {
            let z = CAB0 + 0.05;
            let y = yt(z) + 0.03;
            pm(b, Slot::BlackMatte).cuboid(Vec3::new(x, y, z), Vec3::new(0.62, 0.012, 0.02), Quat::from_rotation_y(a));
        }
    }

    // ---------- sides ----------
    for sx in [-1.0f32, 1.0] {
        let b = &mut body;
        // side skirts
        let pts: Vec<Vec3> = (0..=12)
            .map(|k| {
                let z = WB_F + AR + 0.02 + (WB_R - AR - 0.02 - (WB_F + AR + 0.02)) * k as f32 / 12.0;
                Vec3::new(sx * (body_x(z, 0.2) + 0.01), 0.17, z)
            })
            .collect();
        for w in pts.windows(2) {
            pm(b, Slot::Carbon).seg(w[0], w[1], 0.05, 0.07);
        }
        // side air intake behind the door
        let z = 0.95;
        let y = 0.62;
        pm(b, Slot::BlackMatte).cuboid(
            Vec3::new(sx * (body_x(z, y) - 0.005), y, z),
            Vec3::new(0.03, 0.2, 0.34),
            Quat::from_rotation_z(sx * 0.15),
        );
        for k in 0..4 {
            pm(b, Slot::Carbon).cuboid(
                Vec3::new(sx * (body_x(z, y) + 0.004), y - 0.07 + k as f32 * 0.045, z),
                Vec3::new(0.01, 0.008, 0.3),
                Quat::IDENTITY,
            );
        }
        // fuel cap (right side only)
        if sx > 0.0 {
            pm(b, Slot::Alu).cyl(Vec3::new(body_x(1.6, 0.8) + 0.004, 0.8, 1.6), 0.06, 0.01, 20, Quat::from_rotation_z(FRAC_PI_2));
        }
        // side marker lights
        pm(b, Slot::OrangeLed).bx(Vec3::new(sx * (body_x(-1.95, 0.5) + 0.002), 0.5, -1.95), Vec3::new(0.01, 0.03, 0.08));
    }

    // ---------- rear ----------
    {
        let b = &mut body;
        let z = ZR - 0.02;
        for sx in [-1.0f32, 1.0] {
            // taillight housings and LED bars
            pm(b, Slot::BlackGloss).cuboid(Vec3::new(sx * 0.52, 0.74, z), Vec3::new(0.56, 0.1, 0.06), Quat::from_rotation_y(-sx * 0.12));
            pm(b, Slot::Tail).cuboid(Vec3::new(sx * 0.52, 0.76, z + 0.02), Vec3::new(0.52, 0.028, 0.04), Quat::from_rotation_y(-sx * 0.12));
            pm(b, Slot::Tail).cuboid(Vec3::new(sx * 0.68, 0.715, z + 0.02), Vec3::new(0.18, 0.028, 0.04), Quat::from_rotation_y(-sx * 0.12));
            pm(b, Slot::Reverse).bx(Vec3::new(sx * 0.32, 0.715, z + 0.035), Vec3::new(0.08, 0.02, 0.02));
            pm(b, Slot::OrangeLed).bx(Vec3::new(sx * 0.42, 0.715, z + 0.035), Vec3::new(0.08, 0.02, 0.02));
            // exhaust tips
            for k in [0.12f32, 0.27] {
                let c = Vec3::new(sx * k, 0.27, ZR + 0.01);
                pm(b, Slot::Chrome).cyl(c, 0.045, 0.12, 20, Quat::from_rotation_x(FRAC_PI_2));
                pm(b, Slot::BlackMatte).cyl(c + Vec3::Z * 0.005, 0.036, 0.12, 16, Quat::from_rotation_x(FRAC_PI_2));
            }
            // spoiler stands & end plates
            pm(b, Slot::Carbon).cuboid(Vec3::new(sx * 0.55, yt(2.0) + 0.08, 2.0), Vec3::new(0.03, 0.16, 0.12), Quat::from_rotation_x(-0.2));
            pm(b, Slot::Carbon).bx(Vec3::new(sx * 0.78, yt(2.05) + 0.17, 2.05), Vec3::new(0.012, 0.09, 0.26));
        }
        // centre brake light
        pm(b, Slot::Tail).bx(Vec3::new(0.0, yt(2.2) + 0.005, 2.2), Vec3::new(0.3, 0.01, 0.02));
        // wing
        pm(b, Slot::Carbon).cuboid(Vec3::new(0.0, yt(2.05) + 0.17, 2.05), Vec3::new(1.56, 0.025, 0.24), Quat::from_rotation_x(0.08));
        // diffuser with fins
        pm(b, Slot::Carbon).bx(Vec3::new(0.0, 0.2, 2.1), Vec3::new(1.5, 0.12, 0.34));
        for k in -3..=3 {
            if k == 0 {
                continue;
            }
            pm(b, Slot::Carbon).bx(Vec3::new(k as f32 * 0.2, 0.16, 2.18), Vec3::new(0.012, 0.12, 0.25));
        }
        // rear plate, badge letters
        pm(b, Slot::Plate).bx(Vec3::new(0.0, 0.47, ZR + 0.005), Vec3::new(0.5, 0.11, 0.012));
        for k in 0..6 {
            pm(b, Slot::Chrome).bx(Vec3::new(-0.15 + k as f32 * 0.06, 0.62, ZR + 0.004), Vec3::new(0.035, 0.03, 0.006));
        }
        // shark fin antenna
        pm(b, Slot::BlackGloss).sphere(Vec3::new(0.0, ght(0.6) + 0.01, 0.6), Vec3::new(0.03, 0.04, 0.09), Quat::IDENTITY, 8);
    }

    // ---------- engine bay under glass ----------
    {
        let b = &mut body;
        let ez = (ENG0 + ENG1) * 0.5;
        pm(b, Slot::BlackMatte).bx(Vec3::new(0.0, 0.45, ez), Vec3::new(1.0, 0.02, ENG1 - ENG0));
        pm(b, Slot::Engine).bx(Vec3::new(0.0, 0.6, ez), Vec3::new(0.62, 0.26, 0.5));
        for sx in [-1.0f32, 1.0] {
            pm(b, Slot::EngineRed).bx(Vec3::new(sx * 0.2, 0.76, ez), Vec3::new(0.14, 0.06, 0.48));
            for k in 0..4 {
                let z = ez - 0.18 + k as f32 * 0.12;
                pm(b, Slot::Chrome).cyl_seg(Vec3::new(sx * 0.12, 0.78, z), Vec3::new(sx * 0.03, 0.86, z), 0.022, 0.022, 10);
                pm(b, Slot::BlackMatte).cyl(Vec3::new(sx * 0.27, 0.8, z), 0.015, 0.05, 8, Quat::IDENTITY);
            }
        }
        pm(b, Slot::Chrome).cyl(Vec3::new(0.0, 0.86, ez), 0.07, 0.5, 20, Quat::from_rotation_x(FRAC_PI_2));
        pm(b, Slot::BlackGloss).cyl(Vec3::new(0.0, 0.86, ez - 0.27), 0.075, 0.04, 20, Quat::from_rotation_x(FRAC_PI_2));
        pm(b, Slot::Glass).bx(Vec3::new(0.0, body_y(ez, 0.0) - 0.004, ez), Vec3::new(1.02, 0.008, ENG1 - ENG0 + 0.02));
        // louvres over glass
        for k in 0..6 {
            let z = ENG0 + 0.05 + k as f32 * 0.1;
            pm(b, Slot::BlackGloss).bx(Vec3::new(0.0, body_y(z, 0.0) + 0.006, z), Vec3::new(1.0, 0.01, 0.025));
        }
    }

    // ---------- interior ----------
    {
        let b = &mut body;
        // floor & tunnel
        pm(b, Slot::Carpet).bx(Vec3::new(0.0, 0.18, -0.2), Vec3::new(1.78, 0.04, 1.8));
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.34, -0.2), Vec3::new(0.26, 0.28, 1.4));
        pm(b, Slot::Carbon).bx(Vec3::new(0.0, 0.485, -0.15), Vec3::new(0.24, 0.012, 0.9));
        // gear selector, buttons, cupholders, armrest
        pm(b, Slot::Alu).cyl(Vec3::new(0.0, 0.53, -0.1), 0.012, 0.08, 10, Quat::from_rotation_x(-0.2));
        pm(b, Slot::Leather).sphere(Vec3::new(0.0, 0.575, -0.11), Vec3::new(0.035, 0.03, 0.05), Quat::IDENTITY, 10);
        for k in 0..4 {
            pm(b, Slot::Alu).bx(Vec3::new(-0.06 + k as f32 * 0.04, 0.495, -0.32), Vec3::new(0.025, 0.012, 0.02));
        }
        for z in [0.08f32, 0.17] {
            pm(b, Slot::BlackMatte).cyl(Vec3::new(0.0, 0.49, z), 0.038, 0.012, 16, Quat::IDENTITY);
        }
        pm(b, Slot::LeatherRed).bx(Vec3::new(0.0, 0.52, 0.42), Vec3::new(0.22, 0.06, 0.3));
        // dashboard
        let iw = |z: f32, y: f32| 2.0 * (body_x(z, y) - 0.04);
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.56, -0.78), Vec3::new(iw(-0.6, 0.73), 0.34, 0.42));
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.76, -0.66), Vec3::new(iw(-0.6, 0.8), 0.08, 0.2));
        pm(b, Slot::Leather).cuboid(Vec3::new(0.0, 0.79, -0.56), Vec3::new(iw(-0.56, 0.83), 0.08, 0.2), Quat::from_rotation_x(0.25));
        pm(b, Slot::LeatherRed).bx(Vec3::new(0.0, 0.72, -0.465), Vec3::new(iw(-0.47, 0.73) - 0.04, 0.025, 0.012));
        pm(b, Slot::Carbon).bx(Vec3::new(0.35, 0.65, -0.48), Vec3::new(0.5, 0.1, 0.012));
        // instrument binnacle
        pm(b, Slot::Leather).cuboid(Vec3::new(SEAT_X, 0.905, -0.5), Vec3::new(0.48, 0.03, 0.2), Quat::from_rotation_x(-0.15));
        pm(b, Slot::BlackGloss).bx(Vec3::new(SEAT_X, 0.82, -0.47), Vec3::new(0.46, 0.17, 0.03));
        // gauge faces with chrome bezels and ticks
        let gauges = [Vec3::new(SEAT_X - 0.1, 0.825, -0.452), Vec3::new(SEAT_X + 0.1, 0.825, -0.452)];
        for g in gauges {
            pm(b, Slot::GaugeFace).cyl(g, 0.072, 0.01, 32, Quat::from_rotation_x(FRAC_PI_2));
            pm(b, Slot::Chrome).torus(g + Vec3::Z * 0.004, 0.074, 0.005, Quat::from_rotation_x(FRAC_PI_2), Vec3::ONE);
            for k in 0..=12 {
                let a = 135f32.to_radians() - 270f32.to_radians() * k as f32 / 12.0;
                let dir = Vec3::new(-a.sin(), a.cos(), 0.0);
                let long = if k % 2 == 0 { 0.014 } else { 0.008 };
                pm(b, Slot::Tick).cuboid(
                    g + dir * (0.06 - long * 0.5) + Vec3::Z * 0.006,
                    Vec3::new(0.0035, long, 0.002),
                    Quat::from_rotation_z(a),
                );
            }
            pm(b, Slot::BlackGloss).cyl(g + Vec3::Z * 0.008, 0.008, 0.006, 12, Quat::from_rotation_x(FRAC_PI_2));
        }
        // centre screen
        pm(b, Slot::BlackGloss).cuboid(Vec3::new(0.02, 0.75, -0.5), Vec3::new(0.27, 0.17, 0.015), Quat::from_rotation_x(-0.3));
        pm(b, Slot::Screen).cuboid(Vec3::new(0.02, 0.752, -0.4925), Vec3::new(0.25, 0.15, 0.003), Quat::from_rotation_x(-0.3));
        // vents
        for x in [-0.72f32, -0.1, 0.12, 0.72] {
            pm(b, Slot::BlackMatte).bx(Vec3::new(x, 0.70, -0.565), Vec3::new(0.13, 0.06, 0.02));
            for k in 0..3 {
                pm(b, Slot::Alu).bx(Vec3::new(x, 0.68 + k as f32 * 0.02, -0.555), Vec3::new(0.12, 0.005, 0.01));
            }
        }
        // steering column
        pm(b, Slot::BlackMatte).cyl_seg(Vec3::new(SEAT_X, 0.66, -0.62), Vec3::new(SEAT_X, 0.79, -0.2), 0.045, 0.035, 16);
        // paddle shifters
        for sx in [-1.0f32, 1.0] {
            pm(b, Slot::Alu).cuboid(Vec3::new(SEAT_X + sx * 0.12, 0.83, -0.21), Vec3::new(0.06, 0.08, 0.006), Quat::from_rotation_x(-0.45));
        }
        // pedals
        for (k, x) in [-0.48f32, -0.39, -0.31].iter().enumerate() {
            let w = if k == 2 { 0.05 } else { 0.07 };
            pm(b, Slot::Alu).cuboid(Vec3::new(*x, 0.27, -0.98), Vec3::new(w, 0.1, 0.012), Quat::from_rotation_x(0.5));
            pm(b, Slot::BlackMatte).seg(Vec3::new(*x, 0.31, -0.99), Vec3::new(*x, 0.45, -0.94), 0.012, 0.012);
        }
        // seats
        for sx in [SEAT_X, -SEAT_X] {
            let base = Vec3::new(sx, 0.24, 0.24);
            pm(b, Slot::Leather).bx(base, Vec3::new(0.5, 0.1, 0.5));
            for bs in [-1.0f32, 1.0] {
                pm(b, Slot::Leather).cuboid(base + Vec3::new(bs * 0.215, 0.06, 0.0), Vec3::new(0.08, 0.09, 0.48), Quat::from_rotation_z(bs * 0.2));
            }
            pm(b, Slot::LeatherRed).bx(base + Vec3::new(0.0, 0.051, 0.0), Vec3::new(0.3, 0.004, 0.42));
            for k in 0..5 {
                pm(b, Slot::Leather).bx(base + Vec3::new(0.0, 0.054, -0.16 + k as f32 * 0.08), Vec3::new(0.3, 0.004, 0.008));
            }
            // seat rails
            for bs in [-1.0f32, 1.0] {
                pm(b, Slot::Alu).bx(Vec3::new(sx + bs * 0.18, 0.19, 0.24), Vec3::new(0.02, 0.02, 0.5));
            }
            // backrest
            let piv = Vec3::new(sx, 0.29, 0.47);
            let r = Quat::from_rotation_x(0.24);
            pm(b, Slot::Leather).cuboid(piv + r * Vec3::new(0.0, 0.36, 0.0), Vec3::new(0.5, 0.72, 0.1), r);
            for bs in [-1.0f32, 1.0] {
                pm(b, Slot::Leather).cuboid(
                    piv + r * Vec3::new(bs * 0.23, 0.3, -0.06),
                    Vec3::new(0.08, 0.56, 0.12),
                    r * Quat::from_rotation_y(-bs * 0.35),
                );
            }
            pm(b, Slot::LeatherRed).cuboid(piv + r * Vec3::new(0.0, 0.32, -0.051), Vec3::new(0.28, 0.48, 0.004), r);
            for k in 0..6 {
                pm(b, Slot::Leather).cuboid(piv + r * Vec3::new(0.0, 0.12 + k as f32 * 0.08, -0.054), Vec3::new(0.28, 0.008, 0.004), r);
            }
            // headrest opening & logo
            pm(b, Slot::BlackMatte).cuboid(piv + r * Vec3::new(0.0, 0.6, -0.052), Vec3::new(0.1, 0.05, 0.004), r);
            // seat belt across from B-pillar
            let top = Vec3::new(sx.signum() * 0.55, 1.05, 0.66);
            let bot = Vec3::new(sx - sx.signum() * 0.24, 0.36, 0.34);
            pm(b, Slot::BlackMatte).seg(top, top + (bot - top) * 0.15, 0.045, 0.006);
            pm(b, Slot::Chrome).bx(Vec3::new(sx - sx.signum() * 0.27, 0.34, 0.32), Vec3::new(0.03, 0.06, 0.03));
        }
        // bulkhead & rear shelf, rear speakers
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.42, 0.7), Vec3::new(iw(0.7, 0.62), 0.44, 0.04));
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.75, 0.7), Vec3::new(iw(0.7, 0.86), 0.24, 0.04));
        pm(b, Slot::Leather).bx(Vec3::new(0.0, 0.86, 0.9), Vec3::new(iw(0.9, 0.88), 0.02, 0.36));
        for sx in [-0.55f32, 0.55] {
            pm(b, Slot::Alu).cyl(Vec3::new(sx, 0.872, 0.9), 0.06, 0.006, 20, Quat::IDENTITY);
            pm(b, Slot::BlackMatte).cyl(Vec3::new(sx, 0.875, 0.9), 0.05, 0.006, 20, Quat::IDENTITY);
        }
        // inner side trims behind doors
        for sx in [-1.0f32, 1.0] {
            pm(b, Slot::Leather).bx(Vec3::new(sx * (body_x(0.9, 0.62) - 0.05), 0.45, 0.9), Vec3::new(0.03, 0.36, 0.32));
            pm(b, Slot::Leather).bx(Vec3::new(sx * (body_x(0.9, 0.85) - 0.05), 0.74, 0.9), Vec3::new(0.03, 0.22, 0.32));
        }
        // rear-view mirror, sun visors, dome light
        let my = ght(-0.1) - 0.1;
        pm(b, Slot::BlackMatte).seg(Vec3::new(0.0, ght(-0.12) - 0.035, -0.12), Vec3::new(0.0, my, -0.1), 0.015, 0.015);
        pm(b, Slot::BlackMatte).bx(Vec3::new(0.0, my - 0.02, -0.09), Vec3::new(0.24, 0.06, 0.03));
        pm(b, Slot::Mirror).bx(Vec3::new(0.0, my - 0.02, -0.074), Vec3::new(0.22, 0.05, 0.003));
        for sx in [-0.3f32, 0.3] {
            pm(b, Slot::Fabric).cuboid(Vec3::new(sx, ght(0.0) - 0.06, 0.0), Vec3::new(0.28, 0.012, 0.16), Quat::from_rotation_x(0.12));
        }
        pm(b, Slot::HeadLed).bx(Vec3::new(0.0, ght(0.3) - 0.04, 0.3), Vec3::new(0.08, 0.005, 0.04));
    }

    // ---------- doors (extra parts) ----------
    for (si, sx) in [(0usize, -1.0f32), (1, 1.0)] {
        let d = &mut door[si];
        let zc = (DOOR0 + DOOR1) * 0.5;
        let xin = sx * (body_x(zc, 0.62) - 0.06);
        let xup = sx * (body_x(zc, 0.84) - 0.05);
        pm(d, Slot::Leather).bx(Vec3::new(xin, 0.44, zc), Vec3::new(0.04, 0.4, DOOR1 - DOOR0 - 0.04));
        pm(d, Slot::Leather).bx(Vec3::new(xup, 0.73, zc), Vec3::new(0.04, 0.2, DOOR1 - DOOR0 - 0.04));
        pm(d, Slot::Leather).bx(Vec3::new((xin + xup) * 0.5, 0.635, zc), Vec3::new((xin - xup).abs() + 0.04, 0.03, DOOR1 - DOOR0 - 0.04));
        pm(d, Slot::LeatherRed).bx(Vec3::new(xin - sx * 0.021, 0.52, zc + 0.05), Vec3::new(0.004, 0.12, 0.8));
        pm(d, Slot::Leather).bx(Vec3::new(xin - sx * 0.05, 0.6, zc + 0.12), Vec3::new(0.07, 0.04, 0.5));
        pm(d, Slot::Chrome).bx(Vec3::new(xup - sx * 0.025, 0.74, DOOR0 + 0.25), Vec3::new(0.015, 0.025, 0.13));
        pm(d, Slot::Alu).cyl(Vec3::new(xin - sx * 0.022, 0.36, DOOR0 + 0.25), 0.07, 0.006, 24, Quat::from_rotation_z(FRAC_PI_2));
        pm(d, Slot::BlackMatte).cyl(Vec3::new(xin - sx * 0.026, 0.36, DOOR0 + 0.25), 0.06, 0.006, 24, Quat::from_rotation_z(FRAC_PI_2));
        for k in 0..2 {
            pm(d, Slot::Alu).bx(Vec3::new(xin - sx * 0.07, 0.625, zc - 0.02 + k as f32 * 0.04), Vec3::new(0.02, 0.006, 0.025));
        }
        // outer door handle (flush)
        let hz = 0.5;
        let hy = yt(hz) - 0.09;
        pm(d, Slot::Chrome).bx(Vec3::new(sx * (body_x(hz, hy) + 0.003), hy, hz), Vec3::new(0.01, 0.022, 0.16));
        // mirror: stalk, housing, glass, indicator
        let mz = DOOR0 + 0.14;
        let my = yt(mz) + 0.01;
        let base = Vec3::new(sx * (body_x(mz, my - 0.03) - 0.02), my, mz);
        let head = Vec3::new(sx * (hw(mz) + 0.13), my + 0.11, mz + 0.03);
        pm(d, Slot::Carbon).seg(base, head, 0.03, 0.02);
        pm(d, Slot::Paint).sphere(head, Vec3::new(0.105, 0.06, 0.08), Quat::from_rotation_y(sx * 0.1), 10);
        pm(d, Slot::Mirror).cuboid(head + Vec3::new(0.0, 0.0, 0.07), Vec3::new(0.17, 0.085, 0.004), Quat::from_rotation_y(sx * 0.1));
        pm(d, Slot::OrangeLed).bx(head + Vec3::new(sx * 0.04, -0.03, -0.05), Vec3::new(0.09, 0.008, 0.01));
    }

    // door meshes are expressed relative to their hinge
    let hinges = [
        Vec3::new(-body_x(DOOR0, DOOR_HINGE_Y), DOOR_HINGE_Y, DOOR0),
        Vec3::new(body_x(DOOR0, DOOR_HINGE_Y), DOOR_HINGE_Y, DOOR0),
    ];
    let [mut dl, mut dr] = door;
    for (p, h) in [(&mut dl, hinges[0]), (&mut dr, hinges[1])] {
        for mb in p.values_mut() {
            mb.translate(-h);
        }
    }

    // ---------- wheel (outboard face towards +X) ----------
    let mut spin: Parts = HashMap::new();
    let mut fixed: Parts = HashMap::new();
    {
        let ax = Quat::from_rotation_z(FRAC_PI_2); // cylinder axis Y -> X
        pm(&mut spin, Slot::Rubber).torus(Vec3::ZERO, 0.245, 0.09, ax, Vec3::new(1.0, 1.35, 1.0));
        pm(&mut spin, Slot::Rubber).cyl(Vec3::ZERO, 0.32, 0.2, 40, ax);
        pm(&mut spin, Slot::RimDark).cyl(Vec3::new(-0.01, 0.0, 0.0), 0.236, 0.19, 32, ax);
        pm(&mut spin, Slot::Rim).torus(Vec3::new(0.095, 0.0, 0.0), 0.232, 0.012, ax, Vec3::ONE);
        for k in 0..5 {
            let a = k as f32 / 5.0 * TAU;
            for off in [-0.13f32, 0.13] {
                let ang = a + off;
                let dir = Vec3::new(0.0, ang.cos(), ang.sin());
                let rot = Quat::from_rotation_x(ang);
                pm(&mut spin, Slot::Rim).cuboid(dir * 0.14 + Vec3::X * 0.085 - dir * 0.0, Vec3::new(0.03, 0.19, 0.026), rot);
            }
            // lug nuts
            let d2 = Vec3::new(0.0, (a + 0.63).cos(), (a + 0.63).sin());
            pm(&mut spin, Slot::Chrome).cyl(d2 * 0.04 + Vec3::X * 0.1, 0.008, 0.02, 8, ax);
        }
        pm(&mut spin, Slot::Rim).cyl(Vec3::X * 0.09, 0.06, 0.03, 24, ax);
        pm(&mut spin, Slot::BlackGloss).cyl(Vec3::X * 0.107, 0.025, 0.008, 16, ax);
        pm(&mut spin, Slot::Disc).cyl(Vec3::new(-0.02, 0.0, 0.0), 0.19, 0.028, 32, ax);
        for k in 0..12 {
            let a = k as f32 / 12.0 * TAU;
            pm(&mut spin, Slot::BlackMatte).bx(Vec3::new(-0.005, a.cos() * 0.15, a.sin() * 0.15), Vec3::new(0.002, 0.01, 0.01));
        }
        // caliper sits at rear-top of the disc and does not spin
        pm(&mut fixed, Slot::Caliper).cuboid(Vec3::new(0.0, 0.11, 0.12), Vec3::new(0.06, 0.13, 0.08), Quat::from_rotation_x(-0.75));
        pm(&mut fixed, Slot::Chrome).cuboid(Vec3::new(0.032, 0.11, 0.12), Vec3::new(0.004, 0.03, 0.02), Quat::from_rotation_x(-0.75));
    }

    // ---------- steering wheel (local: axis Y towards driver) ----------
    let mut steer: Parts = HashMap::new();
    {
        pm(&mut steer, Slot::Leather).torus(Vec3::ZERO, 0.175, 0.021, Quat::IDENTITY, Vec3::ONE);
        pm(&mut steer, Slot::LeatherRed).torus(Vec3::new(0.0, 0.0, -0.175), 0.022, 0.012, Quat::from_rotation_x(FRAC_PI_2), Vec3::new(1.0, 1.0, 1.0));
        for dir in [Vec3::NEG_X, Vec3::X, Vec3::Z] {
            pm(&mut steer, Slot::Alu).seg(dir * 0.04, dir * 0.165, 0.035, 0.012);
        }
        pm(&mut steer, Slot::Leather).cyl(Vec3::ZERO, 0.055, 0.04, 24, Quat::IDENTITY);
        pm(&mut steer, Slot::Chrome).cyl(Vec3::Y * 0.022, 0.02, 0.004, 16, Quat::IDENTITY);
        for sx in [-1.0f32, 1.0] {
            pm(&mut steer, Slot::BlackGloss).bx(Vec3::new(sx * 0.075, 0.015, 0.01), Vec3::new(0.035, 0.01, 0.03));
        }
    }

    let mut needle = Mb::default();
    needle.bx(Vec3::new(0.0, 0.026, 0.0), Vec3::new(0.004, 0.058, 0.003));
    needle.cyl(Vec3::ZERO, 0.006, 0.004, 10, Quat::from_rotation_x(FRAC_PI_2));

    CarModel {
        body: to_handles(body, meshes),
        doors: [to_handles(dl, meshes), to_handles(dr, meshes)],
        hinges,
        wheel_spin: to_handles(spin, meshes),
        wheel_fixed: to_handles(fixed, meshes),
        steering: to_handles(steer, meshes),
        steering_pos: Vec3::new(SEAT_X, 0.80, -0.19),
        steering_tilt: Quat::from_rotation_x(FRAC_PI_2 - 0.42),
        needle: meshes.add(needle.build()),
        gauges: [Vec3::new(SEAT_X - 0.1, 0.825, -0.444), Vec3::new(SEAT_X + 0.1, 0.825, -0.444)],
    }
}

// ======================= runtime =======================

#[derive(Component)]
pub struct Car {
    pub vel: Vec2,
    pub yaw: f32,
    pub pos: Vec2,
    pub y: f32,
    pub speed: f32, // signed longitudinal
    pub steer: f32,
    pub wheel_rot: f32,
    pub rpm: f32,
    pub gear: i32,
    pub braking: bool,
    pub roll: f32,
    pub pitch: f32,
    pub tail: Handle<StandardMaterial>,
    pub brake_glow: f32,
}

#[derive(Component)]
pub struct PlayerDriven;
#[derive(Component)]
pub struct BodyRoot(pub Entity);
#[derive(Component)]
pub struct WheelSteer {
    pub car: Entity,
    pub front: bool,
}
#[derive(Component)]
pub struct WheelSpin {
    pub car: Entity,
    pub mirror: bool,
}
#[derive(Component)]
pub struct SteeringWheel {
    pub car: Entity,
    pub base: Quat,
}
#[derive(Component)]
pub struct Needle {
    pub car: Entity,
    pub rpm: bool,
}
#[derive(Component)]
pub struct Door {
    pub car: Entity,
    pub side: f32,
    pub open: f32,
    pub target: f32,
}
#[derive(Component)]
pub struct DriverSeat(pub Entity);
#[derive(Component)]
pub struct Headlight;

pub fn spawn_car(
    commands: &mut Commands,
    model: &CarModel,
    mats: &Mats,
    materials: &mut Assets<StandardMaterial>,
    people: &PeopleAssets,
    color: Color,
    pos: Vec2,
    yaw: f32,
    driver: Option<Look>,
) -> Entity {
    let paint = materials.add(car_paint(color));
    let tail = materials.add(tail_mat(0.4));
    let res = |s: Slot| match s {
        Slot::Paint => paint.clone(),
        Slot::Tail => tail.clone(),
        o => mats.slot(o),
    };
    let root = commands
        .spawn((
            Transform::from_xyz(pos.x, 0.0, pos.y).with_rotation(Quat::from_rotation_y(yaw)),
            Visibility::default(),
            Car {
                vel: Vec2::ZERO,
                yaw,
                pos,
                y: 0.0,
                speed: 0.0,
                steer: 0.0,
                wheel_rot: 0.0,
                rpm: 900.0,
                gear: 1,
                braking: false,
                roll: 0.0,
                pitch: 0.0,
                tail: tail.clone(),
                brake_glow: 0.4,
            },
        ))
        .id();
    let body = commands
        .spawn((Transform::default(), Visibility::default(), BodyRoot(root), ChildOf(root)))
        .id();
    for (m, s) in &model.body {
        commands.spawn((Mesh3d(m.clone()), MeshMaterial3d(res(*s)), ChildOf(body)));
    }
    for (i, side) in [(0usize, -1.0f32), (1, 1.0)] {
        let d = commands
            .spawn((
                Transform::from_translation(model.hinges[i]),
                Visibility::default(),
                Door { car: root, side, open: 0.0, target: 0.0 },
                ChildOf(body),
            ))
            .id();
        for (m, s) in &model.doors[i] {
            commands.spawn((Mesh3d(m.clone()), MeshMaterial3d(res(*s)), ChildOf(d)));
        }
    }
    // wheels
    for (z, front) in [(WB_F, true), (WB_R, false)] {
        for sx in [-1.0f32, 1.0] {
            let pivot = commands
                .spawn((
                    Transform::from_xyz(sx * TRACK, WR, z),
                    Visibility::default(),
                    WheelSteer { car: root, front },
                    ChildOf(root),
                ))
                .id();
            let mirror = sx < 0.0;
            let mrot = if mirror { Quat::from_rotation_y(PI) } else { Quat::IDENTITY };
            let fixed = commands.spawn((Transform::from_rotation(mrot), Visibility::default(), ChildOf(pivot))).id();
            for (m, s) in &model.wheel_fixed {
                commands.spawn((Mesh3d(m.clone()), MeshMaterial3d(res(*s)), ChildOf(fixed)));
            }
            let sp = commands
                .spawn((Transform::from_rotation(mrot), Visibility::default(), WheelSpin { car: root, mirror }, ChildOf(pivot)))
                .id();
            for (m, s) in &model.wheel_spin {
                commands.spawn((Mesh3d(m.clone()), MeshMaterial3d(res(*s)), ChildOf(sp)));
            }
        }
    }
    // steering wheel
    let sw = commands
        .spawn((
            Transform::from_translation(model.steering_pos).with_rotation(model.steering_tilt),
            Visibility::default(),
            SteeringWheel { car: root, base: model.steering_tilt },
            ChildOf(body),
        ))
        .id();
    for (m, s) in &model.steering {
        commands.spawn((Mesh3d(m.clone()), MeshMaterial3d(res(*s)), ChildOf(sw)));
    }
    for (i, g) in model.gauges.iter().enumerate() {
        commands.spawn((
            Mesh3d(model.needle.clone()),
            MeshMaterial3d(mats.slot(Slot::Needle)),
            Transform::from_translation(*g),
            Needle { car: root, rpm: i == 1 },
            ChildOf(body),
        ));
    }
    // seated driver (visible for AI cars, toggled for the player)
    let look = driver.unwrap_or_default();
    let human = spawn_human(
        commands,
        people,
        mats,
        look,
        Transform::from_xyz(SEAT_X, 0.30 - 0.92, 0.30),
        Pose::Seated,
        Some(body),
    );
    commands.entity(human).insert((DriverSeat(root), if driver.is_some() { Visibility::Inherited } else { Visibility::Hidden }));
    root
}

pub fn spawn_headlights(commands: &mut Commands, body: Entity) {
    for sx in [-0.6f32, 0.6] {
        commands.spawn((
            SpotLight {
                color: Color::srgb(1.0, 0.95, 0.85),
                intensity: 600_000.0,
                range: 70.0,
                radius: 0.05,
                inner_angle: 0.25,
                outer_angle: 0.55,
                shadows_enabled: false,
                ..default()
            },
            Transform::from_xyz(sx, 0.62, -2.1).looking_to(Vec3::new(sx * 0.05, -0.12, -1.0), Vec3::Y),
            Headlight,
            ChildOf(body),
        ));
    }
}

// --------- player car physics ---------

pub struct Obstacle {
    pub p: Vec2,
    pub r: f32,
}

pub fn car_circles(pos: Vec2, yaw: f32) -> [Vec2; 3] {
    let f = yaw_fwd(yaw);
    [pos + f * 1.45, pos, pos - f * 1.45]
}

pub fn drive_player_car(
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    colliders: Res<Colliders>,
    mut q: Query<(Entity, &mut Car, &mut Transform), With<PlayerDriven>>,
    others: Query<(Entity, &Car), Without<PlayerDriven>>,
    peds: Query<&Transform, (With<crate::people::Ped>, Without<Car>, Without<PlayerDriven>)>,
) {
    let dt = time.delta_secs().min(0.05);
    let Ok((me, mut car, mut tf)) = q.single_mut() else {
        return;
    };
    let fwd = yaw_fwd(car.yaw);
    let right = yaw_right(car.yaw);
    let mut vf = car.vel.dot(fwd);
    let mut vr = car.vel.dot(right);
    let up = keys.pressed(KeyCode::KeyW) || keys.pressed(KeyCode::ArrowUp);
    let down = keys.pressed(KeyCode::KeyS) || keys.pressed(KeyCode::ArrowDown);
    let left = keys.pressed(KeyCode::KeyA) || keys.pressed(KeyCode::ArrowLeft);
    let rightk = keys.pressed(KeyCode::KeyD) || keys.pressed(KeyCode::ArrowRight);
    let hb = keys.pressed(KeyCode::Space);
    let prev_vf = vf;
    let mut braking = false;

    if up {
        if vf < -0.5 {
            vf += 16.0 * dt;
            braking = true;
        } else {
            let k = (vf / 76.0).clamp(0.0, 1.0);
            vf += 10.5 * (1.0 - k * k) * dt;
        }
    }
    if down {
        if vf > 0.5 {
            vf -= 18.0 * dt;
            braking = true;
        } else {
            vf = (vf - 6.0 * dt).max(-14.0);
        }
    }
    if !up && !down {
        vf -= vf.signum() * (0.6 + vf.abs() * 0.04) * dt;
        if vf.abs() < 0.1 {
            vf = 0.0;
        }
    }
    vf -= vf * vf.abs() * 0.0009 * dt;
    if hb {
        vf -= vf.signum() * 6.0 * dt;
        braking = true;
    }

    let steer_in = (left as i32 - rightk as i32) as f32;
    let max_steer = 0.55 - 0.42 * (vf.abs() / 55.0).min(1.0);
    let target = steer_in * max_steer;
    let rate = if steer_in == 0.0 { 3.5 } else { 2.6 };
    car.steer += (target - car.steer).clamp(-rate * dt, rate * dt);

    let mut yaw_rate = vf / WHEELBASE * car.steer.tan();
    if hb && vf.abs() > 5.0 {
        yaw_rate *= 1.45;
    }
    car.yaw += yaw_rate * dt;
    let grip = if hb { 1.2 } else { 7.5 };
    vr *= (-grip * dt).exp();
    // keep a bit of slide when turning hard at speed (drift feel)
    vr += -yaw_rate * vf * 0.018 * dt * if hb { 3.0 } else { 1.0 };

    let nf = yaw_fwd(car.yaw);
    let nr = yaw_right(car.yaw);
    car.vel = nf * vf + nr * vr;
    let v = car.vel;
    car.pos += v * dt;

    // keep in world bounds
    let m = city_max();
    car.pos = car.pos.clamp(Vec2::splat(-60.0), Vec2::new(m + 50.0, m + 60.0));

    // collisions: static world, then other cars and pedestrians
    let mut dyn_obs: Vec<Obstacle> = Vec::new();
    for (e, c) in &others {
        if e == me {
            continue;
        }
        for p in car_circles(c.pos, c.yaw) {
            dyn_obs.push(Obstacle { p, r: 0.95 });
        }
    }
    for t in &peds {
        dyn_obs.push(Obstacle { p: t.translation.xz(), r: 0.35 });
    }
    let mut hit_n = Vec2::ZERO;
    for _ in 0..2 {
        for c in car_circles(car.pos, car.yaw) {
            if let Some((push, n)) = colliders.resolve(c, 0.95) {
                car.pos += push;
                hit_n = n;
            }
            for o in &dyn_obs {
                let d = c - o.p;
                let rr = 0.95 + o.r;
                let l = d.length();
                if l < rr && l > 1e-4 {
                    let n = d / l;
                    car.pos += n * (rr - l);
                    hit_n = n;
                }
            }
        }
    }
    if hit_n != Vec2::ZERO {
        let vn = car.vel.dot(hit_n);
        if vn < 0.0 {
            car.vel -= hit_n * vn * 1.25;
            car.vel *= 0.85;
        }
    }

    let vf_now = car.vel.dot(nf);
    car.speed = vf_now;
    car.braking = braking;
    let along = (vf_now - prev_vf) / dt.max(1e-4);
    let lat = vf_now * yaw_rate;
    car.pitch += ((along * 0.004).clamp(-0.05, 0.04) - car.pitch) * (6.0 * dt).min(1.0);
    car.roll += ((-lat * 0.0045).clamp(-0.06, 0.06) - car.roll) * (6.0 * dt).min(1.0);

    // automatic gearbox
    let gears = [0.0f32, 13.0, 23.0, 33.0, 44.0, 55.0, 66.0, 999.0];
    let s = vf_now.abs();
    let mut g = 1;
    while g < 7 && s > gears[g] {
        g += 1;
    }
    car.gear = if vf_now < -0.5 { -1 } else { g as i32 };
    let lo = gears[g - 1];
    let hi = gears[g].min(80.0);
    let frac = ((s - lo) / (hi - lo)).clamp(0.0, 1.0);
    let target_rpm = if g == 1 { 900.0 + frac * 6200.0 } else { 3800.0 + frac * 3300.0 };
    let target_rpm = if up && s < 1.0 { 2600.0 } else { target_rpm };
    car.rpm += (target_rpm - car.rpm) * (8.0 * dt).min(1.0);

    let gh = ground_h(car.pos);
    car.y += (gh - car.y) * (12.0 * dt).min(1.0);
    tf.translation = Vec3::new(car.pos.x, car.y, car.pos.y);
    tf.rotation = Quat::from_rotation_y(car.yaw);
}

/// Wheels, steering wheel, gauges, body roll, brake lights, doors — for every car.
pub fn animate_cars(
    time: Res<Time>,
    mut cars: Query<&mut Car>,
    mut bodies: Query<(&BodyRoot, &mut Transform), (Without<WheelSteer>, Without<WheelSpin>)>,
    mut steers: Query<(&WheelSteer, &mut Transform), (Without<BodyRoot>, Without<WheelSpin>)>,
    mut spins: Query<(&WheelSpin, &mut Transform), (Without<BodyRoot>, Without<WheelSteer>)>,
    mut sws: Query<(&SteeringWheel, &mut Transform), (Without<BodyRoot>, Without<WheelSteer>, Without<WheelSpin>)>,
    mut needles: Query<
        (&Needle, &mut Transform),
        (Without<BodyRoot>, Without<WheelSteer>, Without<WheelSpin>, Without<SteeringWheel>),
    >,
    mut doors: Query<
        (&mut Door, &mut Transform),
        (Without<BodyRoot>, Without<WheelSteer>, Without<WheelSpin>, Without<SteeringWheel>, Without<Needle>),
    >,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let dt = time.delta_secs().min(0.05);
    let t = time.elapsed_secs();
    for mut car in &mut cars {
        let s = car.speed;
        car.wheel_rot = (car.wheel_rot + s / WR * dt) % TAU;
        let target = if car.braking { 1.0 } else { 0.35 };
        if (car.brake_glow - target).abs() > 0.01 {
            car.brake_glow += (target - car.brake_glow) * (12.0 * dt).min(1.0);
            if let Some(m) = materials.get_mut(&car.tail) {
                let k = car.brake_glow;
                m.emissive = LinearRgba::rgb(9.0 * k, 0.15 * k, 0.12 * k);
            }
        }
    }
    for (b, mut tf) in &mut bodies {
        if let Ok(car) = cars.get(b.0) {
            let bob = (t * 9.0 + b.0.index() as f32).sin() * 0.002 * (car.speed.abs() / 20.0).min(1.0);
            tf.translation.y = bob;
            tf.rotation = Quat::from_rotation_x(car.pitch) * Quat::from_rotation_z(car.roll);
        }
    }
    for (w, mut tf) in &mut steers {
        if let Ok(car) = cars.get(w.car) {
            tf.rotation = if w.front { Quat::from_rotation_y(car.steer) } else { Quat::IDENTITY };
        }
    }
    for (w, mut tf) in &mut spins {
        if let Ok(car) = cars.get(w.car) {
            let base = if w.mirror { Quat::from_rotation_y(PI) } else { Quat::IDENTITY };
            let a = if w.mirror { car.wheel_rot } else { -car.wheel_rot };
            tf.rotation = base * Quat::from_rotation_x(a);
        }
    }
    for (s, mut tf) in &mut sws {
        if let Ok(car) = cars.get(s.car) {
            tf.rotation = s.base * Quat::from_rotation_y(car.steer * 6.5);
        }
    }
    for (n, mut tf) in &mut needles {
        if let Ok(car) = cars.get(n.car) {
            let frac = if n.rpm { (car.rpm / 8000.0).clamp(0.0, 1.0) } else { (car.speed.abs() * 3.6 / 320.0).clamp(0.0, 1.0) };
            let a = 135f32.to_radians() - 270f32.to_radians() * frac;
            tf.rotation = Quat::from_rotation_z(a);
        }
    }
    for (mut d, mut tf) in &mut doors {
        let speed = 2.4;
        let diff = d.target - d.open;
        d.open += diff.clamp(-speed * dt, speed * dt);
        let e = d.open * d.open * (3.0 - 2.0 * d.open);
        tf.rotation = Quat::from_rotation_y(d.side * e * 1.1);
    }
}
