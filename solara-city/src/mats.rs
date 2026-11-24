//! Materials and procedurally generated textures (with full mip chains).
use bevy::asset::RenderAssetUsages;
use bevy::image::{ImageAddressMode, ImageFilterMode, ImageSampler, ImageSamplerDescriptor};
use bevy::prelude::*;
use bevy::render::render_resource::{
    Extent3d, TextureDimension, TextureFormat, TextureViewDescriptor, TextureViewDimension,
};

use crate::util::Rng;

pub const SUN_DIR: Vec3 = Vec3::new(0.62, 0.13, -0.77); // direction *towards* the sun

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Slot {
    Paint,
    Tail,
    Chrome,
    BlackGloss,
    BlackMatte,
    Rubber,
    Rim,
    RimDark,
    Glass,
    Lens,
    HeadLed,
    OrangeLed,
    Reverse,
    Carbon,
    Leather,
    LeatherRed,
    Fabric,
    Alu,
    Carpet,
    Screen,
    GaugeFace,
    Tick,
    Needle,
    Plate,
    PlateText,
    Engine,
    EngineRed,
    Caliper,
    Disc,
    Mirror,
}

#[derive(Resource, Clone)]
pub struct Mats {
    pub asphalt: Handle<StandardMaterial>,
    pub sidewalk: Handle<StandardMaterial>,
    pub curb: Handle<StandardMaterial>,
    pub grass: Handle<StandardMaterial>,
    pub sand: Handle<StandardMaterial>,
    pub water: Handle<StandardMaterial>,
    pub white_line: Handle<StandardMaterial>,
    pub yellow_line: Handle<StandardMaterial>,
    pub concrete: Handle<StandardMaterial>,
    pub roof: Handle<StandardMaterial>,
    pub metal: Handle<StandardMaterial>,
    pub walls: Vec<Handle<StandardMaterial>>,
    pub shop: Handle<StandardMaterial>,
    pub palm_trunk: Handle<StandardMaterial>,
    pub palm_leaf: Handle<StandardMaterial>,
    pub coconut: Handle<StandardMaterial>,
    pub soil: Handle<StandardMaterial>,
    pub lamp_pole: Handle<StandardMaterial>,
    pub lamp_glow: Handle<StandardMaterial>,
    pub wood: Handle<StandardMaterial>,
    pub beacon: Handle<StandardMaterial>,
    pub tl_housing: Handle<StandardMaterial>,
    /// [axis][0=red,1=yellow,2=green]
    pub tl: [[Handle<StandardMaterial>; 3]; 2],
    pub sky: Handle<StandardMaterial>,
    pub sun: Handle<StandardMaterial>,
    pub cloud: Handle<StandardMaterial>,
    pub mountain: Handle<StandardMaterial>,
    pub fountain_water: Handle<StandardMaterial>,
    // car
    pub car: Vec<(Slot, Handle<StandardMaterial>)>,
    // people
    pub skin: Vec<Handle<StandardMaterial>>,
    pub shirts: Vec<Handle<StandardMaterial>>,
    pub pants: Vec<Handle<StandardMaterial>>,
    pub hair: Vec<Handle<StandardMaterial>>,
    pub shoes: Handle<StandardMaterial>,
    pub eyes: Handle<StandardMaterial>,
    pub env_diffuse: Handle<Image>,
    pub env_specular: Handle<Image>,
}

impl Mats {
    pub fn slot(&self, s: Slot) -> Handle<StandardMaterial> {
        self.car
            .iter()
            .find(|(k, _)| *k == s)
            .map(|(_, h)| h.clone())
            .unwrap_or_else(|| self.car[0].1.clone())
    }
}

fn srgb(r: u8, g: u8, b: u8) -> Color {
    Color::srgb_u8(r, g, b)
}

pub fn pbr(color: Color, rough: f32, metal: f32) -> StandardMaterial {
    StandardMaterial { base_color: color, perceptual_roughness: rough, metallic: metal, ..default() }
}

pub fn emissive(color: Color, e: LinearRgba) -> StandardMaterial {
    StandardMaterial { base_color: color, emissive: e, perceptual_roughness: 0.4, ..default() }
}

pub fn car_paint(color: Color) -> StandardMaterial {
    StandardMaterial {
        base_color: color,
        perceptual_roughness: 0.32,
        metallic: 0.55,
        reflectance: 0.6,
        clearcoat: 1.0,
        clearcoat_perceptual_roughness: 0.04,
        double_sided: true,
        cull_mode: None,
        ..default()
    }
}

pub fn tail_mat(level: f32) -> StandardMaterial {
    StandardMaterial {
        base_color: srgb(120, 5, 8),
        emissive: LinearRgba::rgb(4.0 * level, 0.08 * level, 0.08 * level),
        perceptual_roughness: 0.2,
        ..default()
    }
}

/// Build an image with a full box-filtered mip chain.
pub fn make_tex(images: &mut Assets<Image>, w: u32, h: u32, f: impl Fn(u32, u32) -> [u8; 4]) -> Handle<Image> {
    let mut base = vec![0u8; (w * h * 4) as usize];
    for y in 0..h {
        for x in 0..w {
            let c = f(x, y);
            let i = ((y * w + x) * 4) as usize;
            base[i..i + 4].copy_from_slice(&c);
        }
    }
    let mut data = base.clone();
    let (mut cw, mut ch) = (w, h);
    let mut cur = base;
    let mut count = 1;
    while cw > 1 || ch > 1 {
        let nw = (cw / 2).max(1);
        let nh = (ch / 2).max(1);
        let mut next = vec![0u8; (nw * nh * 4) as usize];
        for y in 0..nh {
            for x in 0..nw {
                for c in 0..4 {
                    let mut s = 0u32;
                    for dy in 0..2 {
                        for dx in 0..2 {
                            let sx = (x * 2 + dx).min(cw - 1);
                            let sy = (y * 2 + dy).min(ch - 1);
                            s += cur[((sy * cw + sx) * 4 + c) as usize] as u32;
                        }
                    }
                    next[((y * nw + x) * 4 + c) as usize] = (s / 4) as u8;
                }
            }
        }
        data.extend_from_slice(&next);
        cur = next;
        cw = nw;
        ch = nh;
        count += 1;
    }
    let mut img = Image::new_fill(
        Extent3d { width: w, height: h, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &[0, 0, 0, 255],
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::RENDER_WORLD,
    );
    img.data = Some(data);
    img.texture_descriptor.mip_level_count = count;
    img.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        anisotropy_clamp: 8,
        ..default()
    });
    images.add(img)
}

fn hash2(x: u32, y: u32, s: u32) -> f32 {
    let mut h = x.wrapping_mul(374761393) ^ y.wrapping_mul(668265263) ^ s.wrapping_mul(2246822519);
    h = (h ^ (h >> 13)).wrapping_mul(1274126177);
    h ^= h >> 16;
    (h & 0xffff) as f32 / 65535.0
}

/// Tileable value noise on a `period`-cell lattice.
fn vnoise(x: f32, y: f32, period: u32, seed: u32) -> f32 {
    let xi = x.floor() as i32;
    let yi = y.floor() as i32;
    let fx = x - xi as f32;
    let fy = y - yi as f32;
    let p = period as i32;
    let g = |a: i32, b: i32| hash2(a.rem_euclid(p) as u32, b.rem_euclid(p) as u32, seed);
    let sx = fx * fx * (3.0 - 2.0 * fx);
    let sy = fy * fy * (3.0 - 2.0 * fy);
    let a = g(xi, yi) + (g(xi + 1, yi) - g(xi, yi)) * sx;
    let b = g(xi, yi + 1) + (g(xi + 1, yi + 1) - g(xi, yi + 1)) * sx;
    a + (b - a) * sy
}

fn fbm(x: f32, y: f32, size: u32, seed: u32) -> f32 {
    let mut v = 0.0;
    let mut amp = 0.5;
    let mut per = 4u32;
    for o in 0..4 {
        let sc = per as f32 / size as f32;
        v += vnoise(x * sc, y * sc, per, seed + o) * amp;
        amp *= 0.5;
        per *= 2;
    }
    v
}

fn shade(c: [f32; 3], k: f32) -> [u8; 4] {
    [
        (c[0] * k).clamp(0.0, 255.0) as u8,
        (c[1] * k).clamp(0.0, 255.0) as u8,
        (c[2] * k).clamp(0.0, 255.0) as u8,
        255,
    ]
}

/// Sky colour (linear) for a world direction.
pub fn sky_color(dir: Vec3) -> Vec3 {
    let d = dir.normalize_or_zero();
    let sun = SUN_DIR.normalize();
    let s = d.dot(sun).max(0.0);
    let zenith = Vec3::new(0.06, 0.12, 0.34);
    let horizon = Vec3::new(1.0, 0.50, 0.30);
    let mid = Vec3::new(0.55, 0.38, 0.50);
    let c = if d.y >= 0.0 {
        let t = d.y.powf(0.5);
        let base = if t < 0.35 { horizon.lerp(mid, t / 0.35) } else { mid.lerp(zenith, (t - 0.35) / 0.65) };
        base + Vec3::new(1.0, 0.55, 0.25) * (s.powf(6.0) * 0.6 + s.powf(48.0) * 1.5) * (1.0 - t * 0.6)
    } else {
        let t = (-d.y).powf(0.35);
        horizon.lerp(Vec3::new(0.16, 0.12, 0.12), t) * 0.7
    };
    c
}

fn to_srgb_u8(v: f32) -> u8 {
    let v = v.clamp(0.0, 1.0);
    let s = if v <= 0.0031308 { v * 12.92 } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 };
    (s * 255.0 + 0.5) as u8
}

/// Procedural cubemap of the sunset sky, with a mip chain blurred towards the average colour.
fn make_env(images: &mut Assets<Image>, size: u32, mips: u32, blur_base: f32) -> Handle<Image> {
    let avg = Vec3::new(0.42, 0.33, 0.36);
    let mut data = Vec::new();
    for face in 0..6 {
        for mip in 0..mips {
            let s = (size >> mip).max(1);
            let blur = (blur_base + (1.0 - blur_base) * mip as f32 / (mips.max(2) - 1) as f32).min(1.0);
            for y in 0..s {
                for x in 0..s {
                    let sc = 2.0 * (x as f32 + 0.5) / s as f32 - 1.0;
                    let tc = 2.0 * (y as f32 + 0.5) / s as f32 - 1.0;
                    let d = match face {
                        0 => Vec3::new(1.0, -tc, -sc),
                        1 => Vec3::new(-1.0, -tc, sc),
                        2 => Vec3::new(sc, 1.0, tc),
                        3 => Vec3::new(sc, -1.0, -tc),
                        4 => Vec3::new(sc, -tc, 1.0),
                        _ => Vec3::new(-sc, -tc, -1.0),
                    };
                    // bevy samples cubemaps with z flipped
                    let world = Vec3::new(d.x, d.y, -d.z);
                    let c = sky_color(world).lerp(avg, blur * 0.85);
                    data.extend_from_slice(&[to_srgb_u8(c.x), to_srgb_u8(c.y), to_srgb_u8(c.z), 255]);
                }
            }
        }
    }
    let mut img = Image::new_fill(
        Extent3d { width: size, height: size, depth_or_array_layers: 6 },
        TextureDimension::D2,
        &[0, 0, 0, 255],
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::RENDER_WORLD,
    );
    img.data = Some(data);
    img.texture_descriptor.mip_level_count = mips;
    img.texture_view_descriptor = Some(TextureViewDescriptor {
        dimension: Some(TextureViewDimension::Cube),
        ..default()
    });
    img.sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        ..default()
    });
    images.add(img)
}

/// Building façade texture: 8x8 window cells, 32px each. Returns (albedo, emissive).
fn facade(images: &mut Assets<Image>, style: u32, seed: u32) -> (Handle<Image>, Handle<Image>) {
    let (wall, glass, frame_w, band, win_h): ([f32; 3], [f32; 3], u32, u32, u32) = match style {
        0 => ([46.0, 60.0, 74.0], [70.0, 120.0, 160.0], 2, 4, 24), // blue glass tower
        1 => ([205.0, 186.0, 156.0], [66.0, 86.0, 106.0], 6, 9, 17), // beige office
        2 => ([226.0, 223.0, 214.0], [58.0, 78.0, 98.0], 7, 8, 18), // white residential
        3 => ([168.0, 96.0, 74.0], [52.0, 60.0, 70.0], 9, 10, 14), // terracotta
        4 => ([34.0, 33.0, 38.0], [120.0, 100.0, 70.0], 2, 5, 22), // dark gold glass
        _ => ([60.0, 118.0, 122.0], [90.0, 160.0, 168.0], 1, 3, 26), // teal curtain wall
    };
    let size = 256u32;
    let cell = 32u32;
    let lit = move |cx: u32, cy: u32| hash2(cx, cy, seed * 7 + 3) < 0.16;
    let albedo = make_tex(images, size, size, |x, y| {
        let cx = x / cell;
        let cy = y / cell;
        let lx = x % cell;
        let ly = y % cell;
        let n = fbm(x as f32, y as f32, size, seed) * 0.25 + 0.875;
        let top = band;
        let in_win = lx >= frame_w && lx < cell - frame_w && ly >= top && ly < top + win_h;
        if in_win {
            let grad = 1.15 - (ly - top) as f32 / win_h as f32 * 0.45;
            let shade_v = 0.8 + hash2(cx, cy, seed) * 0.4;
            // vertical mullion in wide windows
            if style != 5 && (lx == cell / 2 || lx == cell / 2 - 1) && frame_w < 4 {
                return shade(wall, 0.9 * n);
            }
            if lit(cx, cy) {
                return shade([230.0, 190.0, 130.0], 1.0);
            }
            shade(glass, grad * shade_v)
        } else {
            // sill shadow under each window
            let k = if ly == top + win_h || ly == top + win_h + 1 { 0.7 } else { 1.0 };
            shade(wall, n * k)
        }
    });
    let emis = make_tex(images, size, size, |x, y| {
        let cx = x / cell;
        let cy = y / cell;
        let lx = x % cell;
        let ly = y % cell;
        let in_win = lx >= frame_w && lx < cell - frame_w && ly >= band && ly < band + win_h;
        if in_win && lit(cx, cy) {
            let w = 0.75 + hash2(cx, cy, seed + 9) * 0.25;
            shade([255.0, 196.0, 120.0], w)
        } else {
            [0, 0, 0, 255]
        }
    });
    (albedo, emis)
}

pub fn build_mats(materials: &mut Assets<StandardMaterial>, images: &mut Assets<Image>) -> Mats {
    let mut m = |s: StandardMaterial| materials.add(s);

    let asphalt_tex = make_tex(images, 256, 256, |x, y| {
        let n = fbm(x as f32, y as f32, 256, 11);
        let speck = if hash2(x, y, 5) > 0.93 { 1.25 } else { 1.0 };
        let patch = vnoise(x as f32 / 64.0, y as f32 / 64.0, 4, 77) * 0.18 + 0.91;
        shade([62.0, 62.0, 66.0], (0.78 + n * 0.4) * speck * patch)
    });
    let sidewalk_tex = make_tex(images, 256, 256, |x, y| {
        let n = fbm(x as f32, y as f32, 256, 21);
        let joint = x % 64 < 2 || y % 64 < 2;
        let tile_tint = 0.94 + hash2(x / 64, y / 64, 3) * 0.1;
        if joint {
            shade([120.0, 116.0, 110.0], 1.0)
        } else {
            shade([188.0, 182.0, 170.0], (0.88 + n * 0.25) * tile_tint)
        }
    });
    let grass_tex = make_tex(images, 256, 256, |x, y| {
        let n = fbm(x as f32, y as f32, 256, 31);
        let b = hash2(x, y, 8) * 0.2;
        shade([70.0, 112.0, 46.0], 0.7 + n * 0.5 + b)
    });
    let sand_tex = make_tex(images, 256, 256, |x, y| {
        let n = fbm(x as f32, y as f32, 256, 41);
        shade([226.0, 204.0, 160.0], 0.86 + n * 0.25 + hash2(x, y, 4) * 0.06)
    });
    let concrete_tex = make_tex(images, 128, 128, |x, y| {
        let n = fbm(x as f32, y as f32, 128, 51);
        shade([168.0, 164.0, 158.0], 0.85 + n * 0.3)
    });
    let trunk_tex = make_tex(images, 64, 64, |x, y| {
        let ring = ((y as f32 / 64.0 * std::f32::consts::TAU * 4.0).sin() * 0.5 + 0.5).powf(3.0);
        let n = fbm(x as f32, y as f32, 64, 61);
        shade([128.0, 104.0, 78.0], 0.75 + n * 0.3 - ring * 0.25)
    });

    let mut walls = Vec::new();
    for style in 0..6u32 {
        let (alb, em) = facade(images, style, style + 1);
        walls.push(m(StandardMaterial {
            base_color_texture: Some(alb),
            emissive_texture: Some(em),
            emissive: LinearRgba::rgb(2.2, 1.8, 1.3),
            perceptual_roughness: if style == 0 || style == 4 || style == 5 { 0.22 } else { 0.6 },
            metallic: if style == 0 || style == 4 || style == 5 { 0.35 } else { 0.0 },
            reflectance: 0.5,
            ..default()
        }));
    }
    let shop_tex = make_tex(images, 128, 128, |x, y| {
        // shop fronts: big windows with awning band
        let lx = x % 64;
        if y >= 110 {
            let stripe = (x / 8) % 2 == 0;
            if stripe { shade([200.0, 60.0, 50.0], 1.0) } else { shade([235.0, 230.0, 220.0], 1.0) }
        } else if lx < 4 || y < 6 {
            shade([60.0, 58.0, 56.0], 1.0)
        } else {
            let g = 1.2 - (y as f32 / 128.0) * 0.3;
            shade([60.0, 92.0, 110.0], g)
        }
    });
    let shop_em = make_tex(images, 128, 128, |x, y| {
        let lx = x % 64;
        if y >= 6 && y < 110 && lx >= 4 && hash2(x / 64, 0, 9) > 0.3 {
            shade([255.0, 220.0, 170.0], 0.35)
        } else {
            [0, 0, 0, 255]
        }
    });

    let screen_tex = make_tex(images, 128, 80, |x, y| {
        // navigation screen: dark map with roads and a route
        let road = x % 24 < 2 || y % 20 < 2;
        let route = (y >= 39 && y <= 42 && x > 20 && x < 90) || (x >= 88 && x <= 91 && y < 42 && y > 8);
        let car = (x as i32 - 22).abs() < 4 && (y as i32 - 40).abs() < 4;
        if car {
            [255, 255, 255, 255]
        } else if route {
            [60, 170, 255, 255]
        } else if road {
            [90, 96, 110, 255]
        } else if y < 10 {
            [30, 34, 44, 255]
        } else {
            [16, 20, 30, 255]
        }
    });
    let plate_tex = make_tex(images, 128, 32, |x, y| {
        // stylised plate: white with dark glyph blocks and blue band
        if x < 12 {
            return [30, 60, 170, 255];
        }
        let gx = (x - 16) % 14;
        let glyph = x > 16 && x < 120 && gx < 10 && y > 7 && y < 25 && hash2((x - 16) / 14, y / 3, 17) > 0.35;
        if glyph { [20, 20, 24, 255] } else { [236, 236, 232, 255] }
    });

    let tl_lamp = |on: bool, col: Color, e: LinearRgba| StandardMaterial {
        base_color: col,
        emissive: if on { e } else { LinearRgba::BLACK },
        perceptual_roughness: 0.3,
        ..default()
    };

    let env_specular = make_env(images, 64, 7, 0.0);
    let env_diffuse = make_env(images, 16, 1, 0.75);

    let mats = Mats {
        asphalt: m(StandardMaterial {
            base_color_texture: Some(asphalt_tex),
            perceptual_roughness: 0.88,
            ..default()
        }),
        sidewalk: m(StandardMaterial {
            base_color_texture: Some(sidewalk_tex),
            perceptual_roughness: 0.8,
            ..default()
        }),
        curb: m(pbr(srgb(206, 204, 198), 0.7, 0.0)),
        grass: m(StandardMaterial { base_color_texture: Some(grass_tex), perceptual_roughness: 0.95, ..default() }),
        sand: m(StandardMaterial { base_color_texture: Some(sand_tex), perceptual_roughness: 0.95, ..default() }),
        water: m(StandardMaterial {
            base_color: Color::srgb(0.03, 0.22, 0.28),
            perceptual_roughness: 0.06,
            reflectance: 0.9,
            ..default()
        }),
        white_line: m(pbr(srgb(236, 236, 230), 0.6, 0.0)),
        yellow_line: m(pbr(srgb(238, 190, 40), 0.6, 0.0)),
        concrete: m(StandardMaterial { base_color_texture: Some(concrete_tex.clone()), perceptual_roughness: 0.85, ..default() }),
        roof: m(StandardMaterial {
            base_color: srgb(120, 118, 114),
            base_color_texture: Some(concrete_tex),
            perceptual_roughness: 0.9,
            ..default()
        }),
        metal: m(pbr(srgb(150, 154, 160), 0.4, 0.8)),
        walls,
        shop: m(StandardMaterial {
            base_color_texture: Some(shop_tex),
            emissive_texture: Some(shop_em),
            emissive: LinearRgba::rgb(3.0, 2.6, 2.0),
            perceptual_roughness: 0.3,
            ..default()
        }),
        palm_trunk: m(StandardMaterial { base_color_texture: Some(trunk_tex), perceptual_roughness: 0.9, ..default() }),
        palm_leaf: m(StandardMaterial {
            base_color: srgb(58, 112, 40),
            perceptual_roughness: 0.65,
            double_sided: true,
            cull_mode: None,
            ..default()
        }),
        coconut: m(pbr(srgb(86, 64, 34), 0.7, 0.0)),
        soil: m(pbr(srgb(70, 52, 38), 0.95, 0.0)),
        lamp_pole: m(pbr(srgb(48, 52, 56), 0.45, 0.7)),
        lamp_glow: m(emissive(srgb(255, 230, 190), LinearRgba::rgb(9.0, 7.0, 4.5))),
        wood: m(pbr(srgb(122, 84, 52), 0.75, 0.0)),
        beacon: m(emissive(srgb(255, 30, 30), LinearRgba::rgb(14.0, 0.5, 0.5))),
        tl_housing: m(pbr(srgb(30, 32, 30), 0.5, 0.3)),
        tl: [
            [
                m(tl_lamp(false, srgb(90, 10, 10), LinearRgba::rgb(14.0, 0.6, 0.4))),
                m(tl_lamp(false, srgb(90, 70, 10), LinearRgba::rgb(12.0, 7.0, 0.5))),
                m(tl_lamp(false, srgb(10, 80, 40), LinearRgba::rgb(0.5, 12.0, 4.0))),
            ],
            [
                m(tl_lamp(false, srgb(90, 10, 10), LinearRgba::rgb(14.0, 0.6, 0.4))),
                m(tl_lamp(false, srgb(90, 70, 10), LinearRgba::rgb(12.0, 7.0, 0.5))),
                m(tl_lamp(false, srgb(10, 80, 40), LinearRgba::rgb(0.5, 12.0, 4.0))),
            ],
        ],
        sky: m(StandardMaterial {
            base_color: Color::WHITE,
            unlit: true,
            fog_enabled: false,
            cull_mode: None,
            ..default()
        }),
        sun: m(StandardMaterial {
            base_color: Color::LinearRgba(LinearRgba::rgb(40.0, 22.0, 9.0)),
            unlit: true,
            fog_enabled: false,
            ..default()
        }),
        cloud: m(StandardMaterial {
            base_color: Color::LinearRgba(LinearRgba::rgb(1.25, 0.62, 0.55)),
            unlit: true,
            fog_enabled: false,
            ..default()
        }),
        mountain: m(pbr(srgb(84, 70, 96), 0.95, 0.0)),
        fountain_water: m(StandardMaterial {
            base_color: Color::srgba(0.2, 0.5, 0.6, 0.75),
            alpha_mode: AlphaMode::Blend,
            perceptual_roughness: 0.05,
            reflectance: 0.8,
            ..default()
        }),
        car: vec![
            (Slot::Paint, m(car_paint(srgb(200, 20, 20)))),
            (Slot::Tail, m(tail_mat(0.4))),
            (Slot::Chrome, m(pbr(srgb(235, 235, 240), 0.08, 1.0))),
            (Slot::BlackGloss, m(StandardMaterial {
                base_color: srgb(10, 10, 12),
                perceptual_roughness: 0.15,
                clearcoat: 1.0,
                clearcoat_perceptual_roughness: 0.05,
                ..default()
            })),
            (Slot::BlackMatte, m(StandardMaterial {
                base_color: srgb(18, 18, 20),
                perceptual_roughness: 0.8,
                double_sided: true,
                cull_mode: None,
                ..default()
            })),
            (Slot::Rubber, m(pbr(srgb(22, 22, 24), 0.85, 0.0))),
            (Slot::Rim, m(pbr(srgb(200, 202, 208), 0.22, 1.0))),
            (Slot::RimDark, m(pbr(srgb(50, 52, 58), 0.35, 0.9))),
            (Slot::Glass, m(StandardMaterial {
                base_color: Color::srgba(0.05, 0.07, 0.09, 0.42),
                alpha_mode: AlphaMode::Blend,
                perceptual_roughness: 0.04,
                reflectance: 1.0,
                metallic: 0.0,
                ..default()
            })),
            (Slot::Lens, m(StandardMaterial {
                base_color: Color::srgba(0.8, 0.85, 0.9, 0.25),
                alpha_mode: AlphaMode::Blend,
                perceptual_roughness: 0.02,
                reflectance: 1.0,
                ..default()
            })),
            (Slot::HeadLed, m(emissive(Color::WHITE, LinearRgba::rgb(18.0, 18.0, 20.0)))),
            (Slot::OrangeLed, m(emissive(srgb(255, 140, 20), LinearRgba::rgb(6.0, 2.5, 0.2)))),
            (Slot::Reverse, m(emissive(Color::WHITE, LinearRgba::rgb(0.6, 0.6, 0.6)))),
            (Slot::Carbon, m(StandardMaterial {
                base_color: srgb(26, 27, 30),
                perceptual_roughness: 0.25,
                metallic: 0.3,
                clearcoat: 1.0,
                clearcoat_perceptual_roughness: 0.05,
                ..default()
            })),
            (Slot::Leather, m(pbr(srgb(30, 28, 28), 0.55, 0.0))),
            (Slot::LeatherRed, m(pbr(srgb(150, 22, 26), 0.5, 0.0))),
            (Slot::Fabric, m(StandardMaterial {
                base_color: srgb(52, 52, 56),
                perceptual_roughness: 0.95,
                double_sided: true,
                cull_mode: None,
                ..default()
            })),
            (Slot::Alu, m(pbr(srgb(190, 192, 196), 0.3, 1.0))),
            (Slot::Carpet, m(pbr(srgb(24, 24, 26), 1.0, 0.0))),
            (Slot::Screen, m(StandardMaterial {
                base_color: Color::BLACK,
                emissive_texture: Some(screen_tex),
                emissive: LinearRgba::rgb(2.0, 2.0, 2.0),
                perceptual_roughness: 0.05,
                ..default()
            })),
            (Slot::GaugeFace, m(emissive(srgb(10, 10, 14), LinearRgba::rgb(0.05, 0.08, 0.15)))),
            (Slot::Tick, m(emissive(Color::WHITE, LinearRgba::rgb(3.0, 3.0, 3.2)))),
            (Slot::Needle, m(emissive(srgb(255, 40, 20), LinearRgba::rgb(9.0, 0.8, 0.2)))),
            (Slot::Plate, m(StandardMaterial { base_color_texture: Some(plate_tex), perceptual_roughness: 0.4, ..default() })),
            (Slot::PlateText, m(pbr(srgb(20, 20, 24), 0.5, 0.0))),
            (Slot::Engine, m(pbr(srgb(60, 62, 66), 0.45, 0.8))),
            (Slot::EngineRed, m(pbr(srgb(170, 20, 20), 0.3, 0.2))),
            (Slot::Caliper, m(pbr(srgb(210, 170, 20), 0.35, 0.2))),
            (Slot::Disc, m(pbr(srgb(120, 120, 124), 0.5, 0.9))),
            (Slot::Mirror, m(pbr(srgb(240, 240, 245), 0.02, 1.0))),
        ],
        skin: vec![
            m(pbr(srgb(236, 196, 164), 0.6, 0.0)),
            m(pbr(srgb(198, 150, 112), 0.6, 0.0)),
            m(pbr(srgb(142, 98, 66), 0.6, 0.0)),
            m(pbr(srgb(92, 62, 44), 0.6, 0.0)),
        ],
        shirts: [
            (230, 230, 226),
            (40, 44, 52),
            (180, 40, 46),
            (40, 110, 170),
            (230, 170, 40),
            (60, 140, 90),
            (240, 120, 160),
            (110, 90, 160),
        ]
        .iter()
        .map(|c| m(pbr(srgb(c.0, c.1, c.2), 0.8, 0.0)))
        .collect(),
        pants: [(40, 50, 80), (30, 30, 34), (120, 110, 90), (90, 96, 104), (200, 196, 180)]
            .iter()
            .map(|c| m(pbr(srgb(c.0, c.1, c.2), 0.85, 0.0)))
            .collect(),
        hair: [(30, 22, 18), (90, 60, 30), (200, 170, 110), (14, 12, 12)]
            .iter()
            .map(|c| m(pbr(srgb(c.0, c.1, c.2), 0.7, 0.0)))
            .collect(),
        shoes: m(pbr(srgb(240, 240, 240), 0.6, 0.0)),
        eyes: m(pbr(srgb(20, 20, 20), 0.3, 0.0)),
        env_diffuse,
        env_specular,
    };
    mats
}

pub fn random_paint(rng: &mut Rng) -> Color {
    let cols = [
        (230, 230, 232),
        (20, 20, 22),
        (150, 152, 158),
        (30, 60, 150),
        (200, 20, 20),
        (230, 190, 20),
        (230, 100, 20),
        (20, 110, 70),
        (70, 72, 78),
        (110, 20, 40),
        (60, 150, 200),
    ];
    let c = cols[rng.int(cols.len() as u32) as usize];
    srgb(c.0, c.1, c.2)
}
