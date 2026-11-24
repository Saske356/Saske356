//! Procedural city: road grid with markings, sidewalks, skyscrapers, palms,
//! street lamps, traffic lights, park blocks, coast and distant scenery.
//! Everything static is merged per block and per material.
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, TAU};

use bevy::pbr::NotShadowCaster;
use bevy::prelude::*;
use bevy::render::mesh::VertexAttributeValues;

use crate::mats::{sky_color, Mats, SUN_DIR};
use crate::mesh::Mb;
use crate::util::*;

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum K {
    Wall(u8),
    Shop,
    Roof,
    Concrete,
    Metal,
    Trunk,
    Leaf,
    Coconut,
    Soil,
    Pole,
    Glow,
    Grass,
    Wood,
    Beacon,
    Fountain,
    TlHousing,
    Tl(u8, u8),
    Sidewalk,
    Curb,
    White,
    Yellow,
    Asphalt,
    Sand,
    Sea,
    Mountain,
}

fn mat_of(k: K, m: &Mats) -> Handle<StandardMaterial> {
    match k {
        K::Wall(s) => m.walls[s as usize % m.walls.len()].clone(),
        K::Shop => m.shop.clone(),
        K::Roof => m.roof.clone(),
        K::Concrete => m.concrete.clone(),
        K::Metal => m.metal.clone(),
        K::Trunk => m.palm_trunk.clone(),
        K::Leaf => m.palm_leaf.clone(),
        K::Coconut => m.coconut.clone(),
        K::Soil => m.soil.clone(),
        K::Pole => m.lamp_pole.clone(),
        K::Glow => m.lamp_glow.clone(),
        K::Grass => m.grass.clone(),
        K::Wood => m.wood.clone(),
        K::Beacon => m.beacon.clone(),
        K::Fountain => m.fountain_water.clone(),
        K::TlHousing => m.tl_housing.clone(),
        K::Tl(a, c) => m.tl[a as usize][c as usize].clone(),
        K::Sidewalk => m.sidewalk.clone(),
        K::Curb => m.curb.clone(),
        K::White => m.white_line.clone(),
        K::Yellow => m.yellow_line.clone(),
        K::Asphalt => m.asphalt.clone(),
        K::Sand => m.sand.clone(),
        K::Sea => m.water.clone(),
        K::Mountain => m.mountain.clone(),
    }
}

#[derive(Default)]
struct Batch(HashMap<K, Mb>);
impl Batch {
    fn g(&mut self, k: K) -> &mut Mb {
        self.0.entry(k).or_default()
    }
    fn spawn(self, commands: &mut Commands, meshes: &mut Assets<Mesh>, mats: &Mats, cast_shadows: bool) {
        for (k, mb) in self.0 {
            if mb.is_empty() {
                continue;
            }
            let mut e = commands.spawn((Mesh3d(meshes.add(mb.build())), MeshMaterial3d(mat_of(k, mats))));
            let flat = matches!(
                k,
                K::White | K::Yellow | K::Asphalt | K::Sand | K::Sea | K::Grass | K::Sidewalk | K::Fountain | K::Mountain
            );
            if !cast_shadows || flat {
                e.insert(NotShadowCaster);
            }
        }
    }
}

fn v3(p: Vec2, y: f32) -> Vec3 {
    Vec3::new(p.x, y, p.y)
}

const FACADE_TILE: Vec2 = Vec2::new(24.0, 27.2);
const SHOP_TILE: Vec2 = Vec2::new(8.0, 4.5);

fn palm(b: &mut Batch, base: Vec3, h: f32, rng: &mut Rng) {
    let lean = Vec2::from_angle(rng.range(0.0, TAU)) * rng.range(0.3, 1.8);
    let segs = 8;
    let mut prev = base;
    for k in 1..=segs {
        let t = k as f32 / segs as f32;
        let t0 = (k - 1) as f32 / segs as f32;
        let p = base + Vec3::new(lean.x * t * t, h * t, lean.y * t * t);
        b.g(K::Trunk).cyl_seg(prev, p, 0.25 - 0.1 * t0, 0.25 - 0.1 * t, 9);
        prev = p;
    }
    let top = prev;
    b.g(K::Trunk).sphere(top, Vec3::new(0.24, 0.32, 0.24), Quat::IDENTITY, 6);
    let n = 9 + rng.int(4);
    for f in 0..n {
        let ang = f as f32 / n as f32 * TAU + rng.range(-0.2, 0.2);
        let dir = Vec3::new(ang.cos(), 0.0, ang.sin());
        let side = Vec3::new(-dir.z, 0.0, dir.x);
        let len = rng.range(2.8, 4.0);
        let rise = rng.range(0.2, 0.9);
        let steps = 8;
        let mut rows: Vec<[Vec3; 3]> = Vec::new();
        for k in 0..=steps {
            let s = k as f32 / steps as f32;
            let p = top + dir * (len * s) + Vec3::Y * (rise * 2.0 * s - (rise + 1.7) * s * s);
            let w = 0.55 * (std::f32::consts::PI * s.powf(0.8)).sin() + 0.03;
            rows.push([p + side * w - Vec3::Y * 0.16 * w, p + Vec3::Y * 0.03, p - side * w - Vec3::Y * 0.16 * w]);
        }
        let leaf = b.g(K::Leaf);
        for k in 0..steps {
            let a = rows[k];
            let c = rows[k + 1];
            leaf.quad_uv(a[0], a[1], c[1], c[0], [Vec2::ZERO; 4]);
            leaf.quad_uv(a[1], a[2], c[2], c[1], [Vec2::ZERO; 4]);
        }
    }
    for k in 0..3 {
        let a = k as f32 * 2.1;
        b.g(K::Coconut).sphere(top + Vec3::new(a.cos() * 0.2, -0.28, a.sin() * 0.2), Vec3::splat(0.11), Quat::IDENTITY, 6);
    }
}

fn street_lamp(b: &mut Batch, pos: Vec2, to_road: Vec2) {
    let base = v3(pos, CURB);
    let d = v3(to_road, 0.0).normalize();
    let top = base + Vec3::Y * 7.2;
    b.g(K::Pole).cyl_seg(base, top, 0.09, 0.06, 10);
    b.g(K::Pole).cyl(base + Vec3::Y * 0.4, 0.14, 0.8, 10, Quat::IDENTITY);
    let end = top + d * 1.9 + Vec3::Y * 0.15;
    b.g(K::Pole).seg(top, end, 0.07, 0.07);
    let rot = Quat::from_rotation_arc(Vec3::X, d);
    b.g(K::Pole).cuboid(end + d * 0.2 - Vec3::Y * 0.05, Vec3::new(0.7, 0.12, 0.3), rot);
    b.g(K::Glow).cuboid(end + d * 0.2 - Vec3::Y * 0.12, Vec3::new(0.6, 0.03, 0.22), rot);
}

fn bench(b: &mut Batch, pos: Vec2, along_x: bool) {
    let rot = if along_x { Quat::IDENTITY } else { Quat::from_rotation_y(FRAC_PI_2) };
    let c = v3(pos, CURB);
    b.g(K::Wood).cuboid(c + Vec3::Y * 0.45, Vec3::new(1.8, 0.06, 0.45), rot);
    b.g(K::Wood).cuboid(c + Vec3::Y * 0.75 + rot * Vec3::new(0.0, 0.0, 0.22), Vec3::new(1.8, 0.35, 0.05), rot);
    for sx in [-0.8f32, 0.8] {
        b.g(K::Pole).cuboid(c + rot * Vec3::new(sx, 0.22, 0.0), Vec3::new(0.06, 0.45, 0.45), rot);
    }
}

fn add_box_building(b: &mut Batch, mn: Vec2, mx: Vec2, y0: f32, y1: f32, style: u8, shops: bool) {
    let mut wall_bottom = y0;
    if shops && y1 - y0 > 8.0 {
        b.g(K::Shop).box_uv(v3(mn, 0.0), v3(mx, 4.5), SHOP_TILE, false);
        // awning ledge
        b.g(K::Concrete).box_uv(v3(mn - Vec2::splat(0.6), 4.5), v3(mx + Vec2::splat(0.6), 4.85), Vec2::splat(6.0), true);
        wall_bottom = 4.85;
    }
    b.g(K::Wall(style)).box_uv(v3(mn, wall_bottom), v3(mx, y1), FACADE_TILE, false);
    b.g(K::Roof).ground(mn, mx, y1, 6.0);
    // parapet
    let t = 0.35;
    let ph = 1.0;
    let e = 0.15;
    let c = b.g(K::Concrete);
    c.box_uv(v3(Vec2::new(mn.x - e, mn.y - e), y1), v3(Vec2::new(mx.x + e, mn.y - e + t), y1 + ph), Vec2::splat(6.0), true);
    c.box_uv(v3(Vec2::new(mn.x - e, mx.y + e - t), y1), v3(Vec2::new(mx.x + e, mx.y + e), y1 + ph), Vec2::splat(6.0), true);
    c.box_uv(v3(Vec2::new(mn.x - e, mn.y - e), y1), v3(Vec2::new(mn.x - e + t, mx.y + e), y1 + ph), Vec2::splat(6.0), true);
    c.box_uv(v3(Vec2::new(mx.x + e - t, mn.y - e), y1), v3(Vec2::new(mx.x + e, mx.y + e), y1 + ph), Vec2::splat(6.0), true);
}

fn rooftop(b: &mut Batch, mn: Vec2, mx: Vec2, y: f32, tall: bool, rng: &mut Rng) {
    let size = mx - mn;
    if size.x < 6.0 || size.y < 6.0 {
        return;
    }
    for _ in 0..(1 + rng.int(3)) {
        let p = Vec2::new(rng.range(mn.x + 2.0, mx.x - 2.0), rng.range(mn.y + 2.0, mx.y - 2.0));
        b.g(K::Metal).bx(v3(p, y + 0.6), Vec3::new(1.8, 1.2, 1.2));
        b.g(K::Pole).cyl(v3(p, y + 1.25), 0.4, 0.1, 12, Quat::IDENTITY);
    }
    if rng.chance(0.6) {
        let p = Vec2::new(rng.range(mn.x + 2.5, mx.x - 2.5), rng.range(mn.y + 2.5, mx.y - 2.5));
        b.g(K::Concrete).box_uv(v3(p - Vec2::splat(1.6), y), v3(p + Vec2::splat(1.6), y + 3.0), Vec2::splat(6.0), true);
    }
    if rng.chance(0.4) {
        let p = Vec2::new(rng.range(mn.x + 2.0, mx.x - 2.0), rng.range(mn.y + 2.0, mx.y - 2.0));
        b.g(K::Wood).cyl(v3(p, y + 2.5), 1.2, 2.4, 14, Quat::IDENTITY);
        b.g(K::Metal).cyl_seg(v3(p, y + 3.7), v3(p, y + 4.3), 1.25, 0.1, 14);
        for a in 0..4 {
            let o = Vec2::from_angle(a as f32 * FRAC_PI_2 + 0.78) * 0.9;
            b.g(K::Metal).seg(v3(p + o, y), v3(p + o, y + 1.3), 0.08, 0.08);
        }
    }
    if tall {
        let p = (mn + mx) * 0.5;
        b.g(K::Pole).cyl_seg(v3(p, y), v3(p, y + 14.0), 0.18, 0.05, 8);
        b.g(K::Beacon).sphere(v3(p, y + 14.2), Vec3::splat(0.25), Quat::IDENTITY, 6);
    }
}

fn floors(h: f32) -> f32 {
    ((h / 3.4).round() * 3.4).max(10.2)
}

fn lot(b: &mut Batch, col: &mut Colliders, mn: Vec2, mx: Vec2, hmax: f32, rng: &mut Rng) {
    let h = floors(hmax * rng.range(0.45, 1.0));
    let style = rng.int(6) as u8;
    let size = mx - mn;
    let kind = rng.f();
    let squarish = (size.x / size.y).max(size.y / size.x) < 1.35;
    if squarish && kind < 0.22 && size.x > 14.0 {
        // round tower
        let c = (mn + mx) * 0.5;
        let r = size.x.min(size.y) * 0.5 - 0.5;
        b.g(K::Shop).cyl_uv(v3(c, 0.0), r, 4.5, 32, SHOP_TILE, false);
        b.g(K::Concrete).cyl_uv(v3(c, 4.5), r + 0.5, 0.4, 32, Vec2::splat(6.0), true);
        b.g(K::Wall(style)).cyl_uv(v3(c, 4.9), r, h - 4.9, 32, FACADE_TILE, false);
        b.g(K::Concrete).cyl_uv(v3(c, h), r + 0.25, 0.9, 32, Vec2::splat(6.0), true);
        b.g(K::Wall(style)).cyl_uv(v3(c, h + 0.9), r * 0.55, 4.5, 24, FACADE_TILE, true);
        // decorative fins
        for k in 0..8 {
            let a = k as f32 / 8.0 * TAU;
            let p = c + Vec2::from_angle(a) * (r + 0.15);
            b.g(K::Concrete).cuboid(v3(p, (4.9 + h) * 0.5), Vec3::new(0.3, h - 4.9, 0.3), Quat::IDENTITY);
        }
        if h > 60.0 {
            rooftop(b, c - Vec2::splat(0.5), c + Vec2::splat(0.5), h + 5.4, true, rng);
        }
        col.circles.push((c, r + 0.3));
        return;
    }
    if kind < 0.55 && h > 30.0 {
        // stepped tower: podium + inset tower
        let h1 = floors(h * rng.range(0.3, 0.55));
        add_box_building(b, mn, mx, CURB, h1, (style + 1) % 6, true);
        let inset = Vec2::new(rng.range(2.5, size.x * 0.25), rng.range(2.5, size.y * 0.25));
        let tmn = mn + inset;
        let tmx = mx - inset;
        add_box_building(b, tmn, tmx, h1 + 1.0, h, style, false);
        rooftop(b, tmn, tmx, h, h > 80.0, rng);
        rooftop(b, mn, Vec2::new(tmn.x, mx.y), h1, false, rng);
    } else {
        add_box_building(b, mn, mx, CURB, h, style, true);
        rooftop(b, mn, mx, h, h > 80.0, rng);
    }
    col.rects.push((mn, mx));
}

fn sidewalk_block(b: &mut Batch, mn: Vec2, mx: Vec2) {
    b.g(K::Sidewalk).box_uv(v3(mn, -0.05), v3(mx, CURB), Vec2::splat(4.0), true);
    let t = 0.3;
    let y = CURB + 0.004;
    let c = b.g(K::Curb);
    c.box_uv(v3(mn, -0.05), v3(Vec2::new(mx.x, mn.y + t), y), Vec2::splat(2.0), true);
    c.box_uv(v3(Vec2::new(mn.x, mx.y - t), -0.05), v3(mx, y), Vec2::splat(2.0), true);
    c.box_uv(v3(mn, -0.05), v3(Vec2::new(mn.x + t, mx.y), y), Vec2::splat(2.0), true);
    c.box_uv(v3(Vec2::new(mx.x - t, mn.y), -0.05), v3(mx, y), Vec2::splat(2.0), true);
}

fn edge_furniture(b: &mut Batch, col: &mut Colliders, mn: Vec2, mx: Vec2, rng: &mut Rng) {
    // lamps and palms along the four edges
    let edges = [
        (Vec2::new(mn.x, mn.y), Vec2::X, Vec2::NEG_Y),
        (Vec2::new(mx.x, mx.y), Vec2::NEG_X, Vec2::Y),
        (Vec2::new(mn.x, mx.y), Vec2::NEG_Y, Vec2::NEG_X),
        (Vec2::new(mx.x, mn.y), Vec2::Y, Vec2::X),
    ];
    let len = mx.x - mn.x;
    for (start, along, out) in edges {
        for t in [9.0f32, 26.0, 43.0] {
            if t >= len - 2.0 {
                continue;
            }
            let p = start + along * t - out * 0.7;
            street_lamp(b, p, out);
            col.circles.push((p, 0.15));
        }
        for t in [17.5f32, 34.5] {
            if t >= len - 2.0 {
                continue;
            }
            let p = start + along * t - out * 1.3;
            b.g(K::Soil).bx(v3(p, CURB + 0.01), Vec3::new(1.3, 0.02, 1.3));
            b.g(K::Curb).box_uv(v3(p - Vec2::splat(0.7), CURB - 0.02), v3(p + Vec2::splat(0.7), CURB + 0.06), Vec2::splat(2.0), false);
            palm(b, v3(p, CURB), rng.range(7.5, 11.0), rng);
            col.circles.push((p, 0.3));
        }
    }
}

fn traffic_lights(b: &mut Batch, col: &mut Colliders) {
    let dirs = [Vec2::X, Vec2::Y, Vec2::NEG_X, Vec2::NEG_Y];
    for k in 0..=N {
        for l in 0..=N {
            let c = Vec2::new(k as f32 * S, l as f32 * S);
            for (di, d) in dirs.iter().enumerate() {
                let from = IVec2::new(k, l) - d.as_ivec2();
                if from.x < 0 || from.y < 0 || from.x > N || from.y > N {
                    continue;
                }
                let axis = (di % 2) as u8;
                let r = Vec2::new(-d.y, d.x);
                let corner = c - *d * (ROAD * 0.5 + 0.9) + r * (ROAD * 0.5 + 0.9);
                let base = v3(corner, CURB);
                b.g(K::Pole).cyl_seg(base, base + Vec3::Y * 6.4, 0.12, 0.09, 10);
                b.g(K::Pole).cyl(base + Vec3::Y * 0.3, 0.2, 0.6, 10, Quat::IDENTITY);
                let arm_end = v3(c + r * 1.2 - *d * (ROAD * 0.5 + 0.9), 6.1);
                b.g(K::Pole).seg(base + Vec3::Y * 6.1, arm_end, 0.1, 0.1);
                b.g(K::Pole).seg(base + Vec3::Y * 5.0, base + Vec3::Y * 6.1 + (arm_end - base - Vec3::Y * 6.1) * 0.35, 0.05, 0.05);
                col.circles.push((corner, 0.2));
                let facing = -v3(*d, 0.0);
                let rot = Quat::from_rotation_arc(Vec3::Z, facing);
                let mut heads = vec![];
                for off in LANES {
                    heads.push(v3(c + r * off - *d * (ROAD * 0.5 + 0.9), 5.35));
                }
                heads.push(base + Vec3::Y * 3.1 + facing * 0.2);
                for h in heads {
                    b.g(K::TlHousing).cuboid(h, Vec3::new(0.38, 1.05, 0.28), rot);
                    b.g(K::TlHousing).cuboid(h - facing * 0.02, Vec3::new(0.55, 1.2, 0.04), rot);
                    for (ci, dy) in [(0u8, 0.32f32), (1, 0.0), (2, -0.32)] {
                        let lp = h + Vec3::Y * dy + facing * 0.15;
                        b.g(K::Tl(axis, ci)).cyl(lp, 0.11, 0.04, 14, rot * Quat::from_rotation_x(FRAC_PI_2));
                        b.g(K::TlHousing).cuboid(lp + Vec3::Y * 0.12 + facing * 0.08, Vec3::new(0.28, 0.02, 0.18), rot);
                    }
                }
            }
        }
    }
}

fn markings(b: &mut Batch) {
    // `along` = 0 for roads running along X (centre z = l*S), 1 for roads along Z
    for along in 0..2 {
        for l in 0..=N {
            let c = l as f32 * S;
            for i in 0..N {
                let a0 = i as f32 * S + ROAD * 0.5;
                let a1 = (i + 1) as f32 * S - ROAD * 0.5;
                let mut rect = |s0: f32, s1: f32, t0: f32, t1: f32, k: K| {
                    let (mn, mx) = if along == 0 {
                        (Vec2::new(s0, c + t0), Vec2::new(s1, c + t1))
                    } else {
                        (Vec2::new(c + t0, s0), Vec2::new(c + t1, s1))
                    };
                    b.g(k).ground(mn, mx, 0.012, 1.0);
                };
                let s0 = a0 + 4.6;
                let s1 = a1 - 4.6;
                rect(s0, s1, -0.22, -0.1, K::Yellow);
                rect(s0, s1, 0.1, 0.22, K::Yellow);
                rect(a0, a1, -6.75, -6.6, K::White);
                rect(a0, a1, 6.6, 6.75, K::White);
                let mut x = s0 + 1.0;
                while x + 3.0 < s1 {
                    rect(x, x + 3.0, -3.55, -3.45, K::White);
                    rect(x, x + 3.0, 3.45, 3.55, K::White);
                    x += 7.0;
                }
                // stop lines: +dir traffic (right side, t>0) stops near a1; -dir near a0
                rect(a1 - 4.9, a1 - 4.45, 0.25, 6.6, K::White);
                rect(a0 + 4.45, a0 + 4.9, -6.6, -0.25, K::White);
                // zebra crossings
                for (z0, z1) in [(a0 + 0.8, a0 + 4.0), (a1 - 4.0, a1 - 0.8)] {
                    let mut t = -6.4;
                    while t < 6.4 {
                        rect(z0, z1, t, t + 0.6, K::White);
                        t += 1.2;
                    }
                }
                // arrows (simple bars) in lanes before the stop line
                for lane in LANES {
                    rect(a1 - 11.0, a1 - 8.0, lane - 0.08, lane + 0.08, K::White);
                    rect(a0 + 8.0, a0 + 11.0, -lane - 0.08, -lane + 0.08, K::White);
                }
            }
        }
    }
}

pub struct CityOut {
    pub colliders: Colliders,
    pub start_car: (Vec2, f32),
    pub start_player: Vec2,
}

pub fn build_city(commands: &mut Commands, meshes: &mut Assets<Mesh>, mats: &Mats, rng: &mut Rng) -> CityOut {
    let mut col = Colliders::default();
    let m = city_max();
    let mid = Vec2::splat(m * 0.5);
    let mut global = Batch::default();

    // ground layers
    global.g(K::Asphalt).ground(Vec2::splat(-ROAD * 0.5), Vec2::splat(m + ROAD * 0.5), 0.0, 8.0);
    let coast_x = m + ROAD * 0.5 + 7.0;
    global.g(K::Grass).ground(Vec2::new(-2000.0, -2000.0), Vec2::new(coast_x, -ROAD * 0.5), -0.03, 6.0);
    global.g(K::Grass).ground(Vec2::new(-2000.0, m + ROAD * 0.5), Vec2::new(coast_x, 2000.0), -0.03, 6.0);
    global.g(K::Grass).ground(Vec2::new(-2000.0, -ROAD * 0.5), Vec2::new(-ROAD * 0.5, m + ROAD * 0.5), -0.03, 6.0);
    global.g(K::Sand).ground(Vec2::new(coast_x, -2000.0), Vec2::new(coast_x + 75.0, 2000.0), 0.0, 6.0);
    global.g(K::Sea).ground(Vec2::new(coast_x + 55.0, -3000.0), Vec2::new(4000.0, 3000.0), 0.06, 50.0);
    // promenade along the coast
    let pmn = Vec2::new(m + ROAD * 0.5, -ROAD * 0.5);
    let pmx = Vec2::new(coast_x, m + ROAD * 0.5);
    sidewalk_block(&mut global, pmn, pmx);
    let mut z = pmn.y + 6.0;
    while z < pmx.y - 3.0 {
        let p = Vec2::new(coast_x - 1.5, z);
        palm(&mut global, v3(p, CURB), rng.range(8.0, 12.0), rng);
        col.circles.push((p, 0.3));
        if (z as i32 / 12) % 2 == 0 {
            street_lamp(&mut global, Vec2::new(pmn.x + 0.8, z + 6.0), Vec2::NEG_X);
            col.circles.push((Vec2::new(pmn.x + 0.8, z + 6.0), 0.15));
        }
        z += 12.0;
    }
    // beach palms & loungers
    for _ in 0..40 {
        let p = Vec2::new(rng.range(coast_x + 4.0, coast_x + 45.0), rng.range(-200.0, m + 200.0));
        palm(&mut global, v3(p, 0.0), rng.range(6.0, 12.0), rng);
    }
    for _ in 0..30 {
        let p = Vec2::new(rng.range(coast_x + 8.0, coast_x + 45.0), rng.range(-50.0, m + 50.0));
        global.g(K::Wood).cuboid(v3(p, 0.25), Vec3::new(0.7, 0.1, 1.9), Quat::IDENTITY);
        let c = [K::Wall(2), K::Wall(3), K::Wall(5)][rng.int(3) as usize];
        global.g(K::Pole).cyl(v3(p + Vec2::new(1.0, 0.0), 1.2), 0.03, 2.4, 6, Quat::IDENTITY);
        global.g(c).cyl_seg(v3(p + Vec2::new(1.0, 0.0), 2.3), v3(p + Vec2::new(1.0, 0.0), 2.8), 1.3, 0.05, 12);
    }

    markings(&mut global);
    traffic_lights(&mut global, &mut col);

    let mut start_car = (block_center(START_BLOCK.x, START_BLOCK.y), 0.6f32);
    let mut start_player = start_car.0 + Vec2::new(-3.5, 2.5);

    for i in 0..N {
        for j in 0..N {
            let mut b = Batch::default();
            let mn = block_min(i, j);
            let mx = mn + Vec2::splat(BLOCK);
            let center = (mn + mx) * 0.5;
            let d = (center.distance(mid) / (m * 0.55)).min(1.0);
            let hmax = 130.0 - 100.0 * d;
            sidewalk_block(&mut b, mn, mx);
            edge_furniture(&mut b, &mut col, mn, mx, rng);
            let inner_mn = mn + Vec2::splat(4.5);
            let inner_mx = mx - Vec2::splat(4.5);
            if IVec2::new(i, j) == START_BLOCK {
                // showroom plaza: turntable for the car, planters, benches
                b.g(K::Concrete).cyl_uv(v3(center, CURB), 4.2, 0.12, 40, Vec2::splat(4.0), true);
                b.g(K::Metal).cyl_uv(v3(center, CURB), 3.9, 0.14, 40, Vec2::splat(4.0), true);
                for k in 0..32 {
                    let a = k as f32 / 32.0 * TAU;
                    b.g(K::Glow).bx(v3(center + Vec2::from_angle(a) * 4.05, CURB + 0.1), Vec3::new(0.25, 0.04, 0.25));
                }
                for (dx, dz) in [(-1.0f32, -1.0f32), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)] {
                    let p = center + Vec2::new(dx, dz) * 13.0;
                    b.g(K::Concrete).box_uv(v3(p - Vec2::splat(1.4), CURB), v3(p + Vec2::splat(1.4), CURB + 0.7), Vec2::splat(4.0), true);
                    b.g(K::Soil).bx(v3(p, CURB + 0.71), Vec3::new(2.4, 0.02, 2.4));
                    palm(&mut b, v3(p, CURB + 0.7), rng.range(8.0, 11.0), rng);
                    col.rects.push((p - Vec2::splat(1.4), p + Vec2::splat(1.4)));
                    bench(&mut b, p + Vec2::new(0.0, -dz * 3.0), true);
                }
                // a glass tower on the back half of the plaza
                lot(&mut b, &mut col, Vec2::new(inner_mn.x, inner_mx.y - 12.0), Vec2::new(inner_mn.x + 12.0, inner_mx.y), 90.0, rng);
                start_car = (center, 0.6);
                start_player = center + Vec2::new(-4.0, 3.0);
            } else if rng.chance(0.13) {
                // park
                b.g(K::Grass).box_uv(v3(inner_mn - Vec2::splat(0.5), -0.05), v3(inner_mx + Vec2::splat(0.5), CURB + 0.03), Vec2::splat(6.0), true);
                // paths
                b.g(K::Sidewalk).box_uv(v3(Vec2::new(center.x - 1.5, inner_mn.y - 0.5), -0.05), v3(Vec2::new(center.x + 1.5, inner_mx.y + 0.5), CURB + 0.05), Vec2::splat(4.0), true);
                b.g(K::Sidewalk).box_uv(v3(Vec2::new(inner_mn.x - 0.5, center.y - 1.5), -0.05), v3(Vec2::new(inner_mx.x + 0.5, center.y + 1.5), CURB + 0.05), Vec2::splat(4.0), true);
                // fountain
                b.g(K::Concrete).cyl_uv(v3(center, CURB), 4.0, 0.6, 40, Vec2::splat(4.0), false);
                b.g(K::Fountain).cyl_uv(v3(center, CURB), 3.8, 0.5, 40, Vec2::splat(4.0), true);
                b.g(K::Concrete).cyl_uv(v3(center, CURB), 0.5, 2.2, 16, Vec2::splat(4.0), true);
                b.g(K::Concrete).cyl_uv(v3(center, CURB + 2.2), 1.4, 0.25, 24, Vec2::splat(4.0), true);
                col.circles.push((center, 4.0));
                for _ in 0..(8 + rng.int(6)) {
                    let p = Vec2::new(rng.range(inner_mn.x + 1.0, inner_mx.x - 1.0), rng.range(inner_mn.y + 1.0, inner_mx.y - 1.0));
                    if (p.x - center.x).abs() < 3.0 || (p.y - center.y).abs() < 3.0 {
                        continue;
                    }
                    palm(&mut b, v3(p, CURB), rng.range(7.0, 13.0), rng);
                    col.circles.push((p, 0.3));
                }
                for k in 0..4 {
                    let a = k as f32 * FRAC_PI_2;
                    bench(&mut b, center + Vec2::from_angle(a) * 7.0 + Vec2::from_angle(a + FRAC_PI_2) * 2.6, k % 2 == 1);
                }
            } else {
                let layout = rng.int(3);
                let gap = 3.0;
                let mut lots: Vec<(Vec2, Vec2)> = Vec::new();
                match layout {
                    0 => lots.push((inner_mn, inner_mx)),
                    1 => {
                        let split = rng.range(0.4, 0.6);
                        if rng.chance(0.5) {
                            let sx = inner_mn.x + (inner_mx.x - inner_mn.x) * split;
                            lots.push((inner_mn, Vec2::new(sx - gap * 0.5, inner_mx.y)));
                            lots.push((Vec2::new(sx + gap * 0.5, inner_mn.y), inner_mx));
                        } else {
                            let sz = inner_mn.y + (inner_mx.y - inner_mn.y) * split;
                            lots.push((inner_mn, Vec2::new(inner_mx.x, sz - gap * 0.5)));
                            lots.push((Vec2::new(inner_mn.x, sz + gap * 0.5), inner_mx));
                        }
                    }
                    _ => {
                        let c = (inner_mn + inner_mx) * 0.5;
                        lots.push((inner_mn, c - Vec2::splat(gap * 0.5)));
                        lots.push((Vec2::new(c.x + gap * 0.5, inner_mn.y), Vec2::new(inner_mx.x, c.y - gap * 0.5)));
                        lots.push((Vec2::new(inner_mn.x, c.y + gap * 0.5), Vec2::new(c.x - gap * 0.5, inner_mx.y)));
                        lots.push((c + Vec2::splat(gap * 0.5), inner_mx));
                    }
                }
                for (a, bb) in lots {
                    let m0 = Vec2::new(rng.range(0.0, 1.5), rng.range(0.0, 1.5));
                    let m1 = Vec2::new(rng.range(0.0, 1.5), rng.range(0.0, 1.5));
                    lot(&mut b, &mut col, a + m0, bb - m1, hmax, rng);
                }
            }
            b.spawn(commands, meshes, mats, true);
        }
    }
    global.spawn(commands, meshes, mats, true);

    // distant mountains
    let mut mtn = Batch::default();
    for k in 0..22 {
        let a = TAU * (0.25 + 0.75 * k as f32 / 22.0) + rng.range(-0.05, 0.05);
        let dir = Vec2::new(a.cos(), a.sin());
        if dir.x > 0.3 {
            continue; // keep the ocean horizon open
        }
        let p = mid + dir * rng.range(900.0, 1300.0);
        let h = rng.range(120.0, 260.0);
        let r = rng.range(220.0, 420.0);
        let mesh = Mesh::from(Cone { radius: r, height: h }.mesh().resolution(10));
        mtn.g(K::Mountain).add_mesh(&mesh, Transform::from_translation(v3(p, h * 0.5 - 10.0)));
    }
    mtn.spawn(commands, meshes, mats, false);

    // sky dome with vertex colours, sun disc, clouds
    let mut sky = Sphere::new(3000.0).mesh().uv(64, 32);
    if let Some(VertexAttributeValues::Float32x3(p)) = sky.attribute(Mesh::ATTRIBUTE_POSITION) {
        let cols: Vec<[f32; 4]> = p
            .iter()
            .map(|v| {
                let c = sky_color(Vec3::from(*v));
                [c.x, c.y, c.z, 1.0]
            })
            .collect();
        sky.insert_attribute(Mesh::ATTRIBUTE_COLOR, cols);
    }
    commands.spawn((Mesh3d(meshes.add(sky)), MeshMaterial3d(mats.sky.clone()), Transform::from_translation(v3(mid, 0.0)), NotShadowCaster));
    commands.spawn((
        Mesh3d(meshes.add(Sphere::new(60.0).mesh().uv(24, 12))),
        MeshMaterial3d(mats.sun.clone()),
        Transform::from_translation(v3(mid, 0.0) + SUN_DIR.normalize() * 2800.0),
        NotShadowCaster,
    ));
    let mut clouds = Mb::default();
    for _ in 0..26 {
        let a = rng.range(0.0, TAU);
        let base = mid + Vec2::from_angle(a) * rng.range(500.0, 1800.0);
        let y = rng.range(260.0, 520.0);
        for _ in 0..4 {
            let o = Vec2::new(rng.range(-80.0, 80.0), rng.range(-40.0, 40.0));
            clouds.sphere(v3(base + o, y + rng.range(-10.0, 10.0)), Vec3::new(rng.range(60.0, 140.0), rng.range(8.0, 16.0), rng.range(30.0, 70.0)), Quat::from_rotation_y(a), 8);
        }
    }
    commands.spawn((Mesh3d(meshes.add(clouds.build())), MeshMaterial3d(mats.cloud.clone()), NotShadowCaster));

    CityOut { colliders: col, start_car, start_player }
}
