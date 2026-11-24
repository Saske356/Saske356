use bevy::prelude::*;

/// City layout constants (metres).
pub const N: i32 = 6; // blocks per side
pub const BLOCK: f32 = 52.0;
pub const ROAD: f32 = 14.0;
pub const S: f32 = BLOCK + ROAD; // grid pitch between road centre lines
pub const CURB: f32 = 0.18; // sidewalk height
pub const LANES: [f32; 2] = [1.75, 5.25]; // lane centre offsets from road centre
pub const START_BLOCK: IVec2 = IVec2::new(2, 3);

pub fn city_max() -> f32 {
    N as f32 * S
}

pub fn block_min(i: i32, j: i32) -> Vec2 {
    Vec2::new(i as f32 * S + ROAD * 0.5, j as f32 * S + ROAD * 0.5)
}

pub fn block_center(i: i32, j: i32) -> Vec2 {
    block_min(i, j) + Vec2::splat(BLOCK * 0.5)
}

/// Which block (if any) a point on the ground plane belongs to.
pub fn block_at(p: Vec2) -> Option<IVec2> {
    let i = (p.x / S).floor() as i32;
    let j = (p.y / S).floor() as i32;
    if !(0..N).contains(&i) || !(0..N).contains(&j) {
        return None;
    }
    let lx = p.x - i as f32 * S;
    let lz = p.y - j as f32 * S;
    let lo = ROAD * 0.5;
    let hi = S - ROAD * 0.5;
    if lx > lo && lx < hi && lz > lo && lz < hi {
        Some(IVec2::new(i, j))
    } else {
        None
    }
}

pub fn ground_h(p: Vec2) -> f32 {
    let m = city_max();
    // coastal promenade east of the city
    if p.x > m + ROAD * 0.5 && p.x < m + ROAD * 0.5 + 7.0 && p.y > -ROAD * 0.5 && p.y < m + ROAD * 0.5 {
        return CURB;
    }
    if block_at(p).is_some() {
        CURB
    } else {
        0.0
    }
}

/// Small deterministic xorshift RNG (no external crates, works on wasm).
#[derive(Clone)]
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Self(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    pub fn next_u32(&mut self) -> u32 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        (x >> 32) as u32
    }
    pub fn f(&mut self) -> f32 {
        self.next_u32() as f32 / 4_294_967_296.0
    }
    pub fn range(&mut self, a: f32, b: f32) -> f32 {
        a + (b - a) * self.f()
    }
    pub fn int(&mut self, n: u32) -> u32 {
        if n == 0 {
            0
        } else {
            self.next_u32() % n
        }
    }
    pub fn chance(&mut self, p: f32) -> bool {
        self.f() < p
    }
}

/// Static collision geometry (XZ plane).
#[derive(Resource, Default)]
pub struct Colliders {
    pub rects: Vec<(Vec2, Vec2)>,
    pub circles: Vec<(Vec2, f32)>,
}

impl Colliders {
    /// Push a circle out of all static geometry. Returns accumulated push and last normal.
    pub fn resolve(&self, p: Vec2, r: f32) -> Option<(Vec2, Vec2)> {
        let mut push = Vec2::ZERO;
        let mut normal = Vec2::ZERO;
        let mut hit = false;
        let q = p;
        for (mn, mx) in &self.rects {
            let cp = (q + push).clamp(*mn, *mx);
            let d = q + push - cp;
            let l2 = d.length_squared();
            if l2 < r * r {
                if l2 > 1e-8 {
                    let l = l2.sqrt();
                    let n = d / l;
                    push += n * (r - l);
                    normal = n;
                } else {
                    // centre inside rect: push along smallest axis
                    let c = q + push;
                    let dl = c.x - mn.x;
                    let dr = mx.x - c.x;
                    let db = c.y - mn.y;
                    let dt = mx.y - c.y;
                    let m = dl.min(dr).min(db).min(dt);
                    let n = if m == dl {
                        Vec2::NEG_X
                    } else if m == dr {
                        Vec2::X
                    } else if m == db {
                        Vec2::NEG_Y
                    } else {
                        Vec2::Y
                    };
                    push += n * (m + r);
                    normal = n;
                }
                hit = true;
            }
        }
        for (c, cr) in &self.circles {
            let d = q + push - *c;
            let rr = r + cr;
            let l2 = d.length_squared();
            if l2 < rr * rr && l2 > 1e-8 {
                let l = l2.sqrt();
                let n = d / l;
                push += n * (rr - l);
                normal = n;
                hit = true;
            }
        }
        if hit {
            Some((push, normal))
        } else {
            None
        }
    }
}

pub fn yaw_fwd(yaw: f32) -> Vec2 {
    Vec2::new(-yaw.sin(), -yaw.cos())
}
pub fn yaw_right(yaw: f32) -> Vec2 {
    Vec2::new(yaw.cos(), -yaw.sin())
}
pub fn yaw_from_dir(d: Vec2) -> f32 {
    (-d.x).atan2(-d.y)
}
pub fn angle_wrap(a: f32) -> f32 {
    let mut a = a % std::f32::consts::TAU;
    if a > std::f32::consts::PI {
        a -= std::f32::consts::TAU;
    }
    if a < -std::f32::consts::PI {
        a += std::f32::consts::TAU;
    }
    a
}
