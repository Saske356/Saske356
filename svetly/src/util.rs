//! Small helpers shared by every module: a mesh builder that merges many boxes
//! into one draw call, procedural textures with mipmaps, and simple 2D collision.

use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageFilterMode, ImageSampler, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::render::mesh::{Indices, PrimitiveTopology};
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

/// Accumulates quads and boxes into a single mesh. The city is built from a
/// handful of these per chunk, which keeps draw calls low on phones.
#[derive(Default)]
pub struct GeoBuilder {
    pos: Vec<[f32; 3]>,
    nrm: Vec<[f32; 3]>,
    uv: Vec<[f32; 2]>,
    idx: Vec<u32>,
}

impl GeoBuilder {
    pub fn is_empty(&self) -> bool {
        self.idx.is_empty()
    }

    /// A rectangle centred on `c`, spanning `u` (right) and `v` (up) half-axes.
    /// `u × v` must point along the face normal. UVs are given per corner.
    pub fn face(&mut self, c: Vec3, u: Vec3, v: Vec3, uv0: Vec2, uv1: Vec2) {
        let n = u.cross(v).normalize_or_zero();
        let b = self.pos.len() as u32;
        let corners = [c - u - v, c + u - v, c + u + v, c - u + v];
        let uvs = [
            [uv0.x, uv1.y],
            [uv1.x, uv1.y],
            [uv1.x, uv0.y],
            [uv0.x, uv0.y],
        ];
        for i in 0..4 {
            self.pos.push(corners[i].to_array());
            self.nrm.push(n.to_array());
            self.uv.push(uvs[i]);
        }
        self.idx.extend([b, b + 1, b + 2, b, b + 2, b + 3]);
    }

    /// Flat horizontal quad (facing up) with world-scaled UVs.
    pub fn ground_quad(&mut self, min: Vec2, max: Vec2, y: f32, uv_scale: f32) {
        let c = Vec3::new((min.x + max.x) * 0.5, y, (min.y + max.y) * 0.5);
        let hx = (max.x - min.x) * 0.5;
        let hz = (max.y - min.y) * 0.5;
        self.face(
            c,
            Vec3::X * hx,
            Vec3::NEG_Z * hz,
            Vec2::new(min.x, min.y) / uv_scale,
            Vec2::new(max.x, max.y) / uv_scale,
        );
    }

    /// Walls of a box with UVs in world units divided by `uv_size`
    /// (so a window texture tiles once per floor/bay regardless of size).
    pub fn box_walls(&mut self, center: Vec3, size: Vec3, uv_size: Vec2, uv_off: f32) {
        let h = size * 0.5;
        let vy = Vec3::Y * h.y;
        let v0 = 0.0;
        let v1 = size.y / uv_size.y;
        let sides = [
            (Vec3::X * h.x, Vec3::NEG_Z * h.z, size.z),
            (Vec3::NEG_X * h.x, Vec3::Z * h.z, size.z),
            (Vec3::Z * h.z, Vec3::X * h.x, size.x),
            (Vec3::NEG_Z * h.z, Vec3::NEG_X * h.x, size.x),
        ];
        for (i, (off, u, len)) in sides.into_iter().enumerate() {
            let u0 = uv_off + i as f32 * 0.37;
            self.face(
                center + off,
                u,
                vy,
                Vec2::new(u0, v1),
                Vec2::new(u0 + len / uv_size.x, v0),
            );
        }
    }

    pub fn box_top(&mut self, center: Vec3, size: Vec3, uv_scale: f32) {
        let h = size * 0.5;
        let c = center + Vec3::Y * h.y;
        self.face(
            c,
            Vec3::X * h.x,
            Vec3::NEG_Z * h.z,
            Vec2::new(c.x - h.x, c.z - h.z) / uv_scale,
            Vec2::new(c.x + h.x, c.z + h.z) / uv_scale,
        );
    }

    /// A full closed box (without the bottom) using simple world UVs.
    pub fn solid_box(&mut self, center: Vec3, size: Vec3, uv_scale: f32) {
        self.box_walls(center, size, Vec2::splat(uv_scale), 0.0);
        self.box_top(center, size, uv_scale);
    }

    pub fn build(self) -> Mesh {
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::RENDER_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.pos)
            .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.nrm)
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uv)
            .with_inserted_indices(Indices::U32(self.idx))
    }
}

/// Builds a repeating sRGB texture with a full mip chain (no shimmering at a distance).
pub fn make_texture(size: u32, mut pixel: impl FnMut(u32, u32) -> [u8; 4]) -> Image {
    let mut levels: Vec<Vec<u8>> = Vec::new();
    let mut base = Vec::with_capacity((size * size * 4) as usize);
    for y in 0..size {
        for x in 0..size {
            base.extend_from_slice(&pixel(x, y));
        }
    }
    levels.push(base);
    let mut s = size;
    while s > 1 {
        let prev = levels.last().unwrap();
        let ns = s / 2;
        let mut next = Vec::with_capacity((ns * ns * 4) as usize);
        for y in 0..ns {
            for x in 0..ns {
                for ch in 0..4 {
                    let mut acc = 0u32;
                    for (dx, dy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
                        let i = (((y * 2 + dy) * s + (x * 2 + dx)) * 4 + ch) as usize;
                        acc += prev[i] as u32;
                    }
                    next.push((acc / 4) as u8);
                }
            }
        }
        levels.push(next);
        s = ns;
    }
    let mip_count = levels.len() as u32;
    let mut image = Image::new(
        Extent3d { width: size, height: size, depth_or_array_layers: 1 },
        TextureDimension::D2,
        levels[0].clone(),
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::RENDER_WORLD,
    );
    image.data = Some(levels.concat());
    image.texture_descriptor.mip_level_count = mip_count;
    image.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        anisotropy_clamp: 8,
        ..default()
    });
    image
}

/// Cheap deterministic hash noise in 0..1.
pub fn hash2(x: i32, y: i32, seed: u32) -> f32 {
    let mut h = (x as u32).wrapping_mul(374761393)
        ^ (y as u32).wrapping_mul(668265263)
        ^ seed.wrapping_mul(2246822519);
    h = (h ^ (h >> 13)).wrapping_mul(1274126177);
    h ^= h >> 16;
    (h & 0xffff) as f32 / 65535.0
}

/// Smooth value noise for textures.
pub fn value_noise(x: f32, y: f32, seed: u32) -> f32 {
    let xi = x.floor() as i32;
    let yi = y.floor() as i32;
    let fx = x - xi as f32;
    let fy = y - yi as f32;
    let sx = fx * fx * (3.0 - 2.0 * fx);
    let sy = fy * fy * (3.0 - 2.0 * fy);
    let a = hash2(xi, yi, seed);
    let b = hash2(xi + 1, yi, seed);
    let c = hash2(xi, yi + 1, seed);
    let d = hash2(xi + 1, yi + 1, seed);
    let ab = a + (b - a) * sx;
    let cd = c + (d - c) * sx;
    ab + (cd - ab) * sy
}

/// Axis-aligned rectangle on the XZ plane, used for building collision.
#[derive(Clone, Copy, Debug)]
pub struct Rect2 {
    pub min: Vec2,
    pub max: Vec2,
}

impl Rect2 {
    pub fn new(min: Vec2, max: Vec2) -> Self {
        Self { min, max }
    }
    pub fn contains(&self, p: Vec2) -> bool {
        p.x >= self.min.x && p.x <= self.max.x && p.y >= self.min.y && p.y <= self.max.y
    }
    pub fn center(&self) -> Vec2 {
        (self.min + self.max) * 0.5
    }
    /// Pushes a circle out of the rectangle. Returns the push vector if overlapping.
    pub fn push_circle(&self, p: Vec2, r: f32) -> Option<Vec2> {
        let closest = p.clamp(self.min, self.max);
        let d = p - closest;
        let dist2 = d.length_squared();
        if dist2 > r * r {
            return None;
        }
        if dist2 > 1e-6 {
            let dist = dist2.sqrt();
            return Some(d / dist * (r - dist));
        }
        // Centre inside: push out along the shortest axis.
        let left = p.x - self.min.x;
        let right = self.max.x - p.x;
        let down = p.y - self.min.y;
        let up = self.max.y - p.y;
        let m = left.min(right).min(down).min(up);
        Some(if m == left {
            Vec2::new(-(left + r), 0.0)
        } else if m == right {
            Vec2::new(right + r, 0.0)
        } else if m == down {
            Vec2::new(0.0, -(down + r))
        } else {
            Vec2::new(0.0, up + r)
        })
    }
}

pub fn xz(v: Vec3) -> Vec2 {
    Vec2::new(v.x, v.z)
}

/// Yaw angle (around Y) that makes an entity's -Z point along `dir`.
pub fn yaw_of(dir: Vec2) -> f32 {
    (-dir.x).atan2(-dir.y)
}

pub fn forward_of(yaw: f32) -> Vec2 {
    Vec2::new(-yaw.sin(), -yaw.cos())
}

pub fn angle_diff(a: f32, b: f32) -> f32 {
    let mut d = (b - a) % std::f32::consts::TAU;
    if d > std::f32::consts::PI {
        d -= std::f32::consts::TAU;
    } else if d < -std::f32::consts::PI {
        d += std::f32::consts::TAU;
    }
    d
}

pub fn srgb(hex: u32) -> Color {
    Color::srgb_u8((hex >> 16) as u8, (hex >> 8) as u8, hex as u8)
}
