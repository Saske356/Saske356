//! Графика: текстуры, свечение (аддитивное смешивание), живая анимация спрайтов
//! деформацией сетки (вычисляется на лету, без запекания), текст Roboto и фигуры интерфейса.
use macroquad::prelude::*;
use macroquad::miniquad::{BlendFactor, BlendState, BlendValue, Equation, PipelineParams, TextureWrap};
use serde_json::Value;
use std::collections::HashMap;

pub fn hex(c: u32) -> Color { Color::from_rgba((c >> 16) as u8, (c >> 8 & 255) as u8, (c & 255) as u8, 255) }
pub fn hexa(c: u32, a: f32) -> Color { let mut k = hex(c); k.a = a; k }
pub fn pal(i: u8) -> u32 { crate::data::PAL_HEX[i as usize % crate::data::PAL_HEX.len()] }

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Anim { Swim, Fin, Tent, Jelly, JellyV, Crab, Pulse, Flap, Orb }
impl Anim {
    pub fn parse(s: &str) -> Option<Anim> { Some(match s { "swim" => Anim::Swim, "fin" => Anim::Fin, "tent" => Anim::Tent, "jelly" => Anim::Jelly, "jellyV" => Anim::JellyV,
        "crab" => Anim::Crab, "pulse" => Anim::Pulse, "flap" => Anim::Flap, "orb" => Anim::Orb, _ => return None }) }
    /// Циклов в секунду
    pub fn freq(self) -> f32 { match self { Anim::Swim => 1.7, Anim::Fin => 1.1, Anim::Tent => 1.15, Anim::Jelly | Anim::JellyV => 0.7, Anim::Crab => 2.6, Anim::Pulse => 0.8, Anim::Flap => 1.3, Anim::Orb => 1.6 } }
}
pub struct Spr { pub tex: Texture2D, pub h: f32, pub fl: bool, pub anim: Option<Anim>, pub hinge: Option<(f32, f32)> }

pub struct Gfx {
    pub spr: HashMap<String, Spr>, pub glow: Vec<Texture2D>, pub soft: Vec<Texture2D>, pub bul: Vec<Texture2D>, pub icon: HashMap<String, Texture2D>, pub ground: Vec<Texture2D>, pub caustic: Option<Texture2D>, pub shade: Texture2D, pub tint: Color,
    pub font_b: Font, pub font_k: Font, pub font_m: Font, pub add: Material, pub wmat: Material, pub wadd: Material, pub vign: Texture2D, pub hurt: Texture2D, pub white: Texture2D,
    /// Физических пикселей на логический пиксель (как devicePixelRatio)
    pub px: f32, pub w: f32, pub h: f32, pub ws: f32, pub ox: f32, pub oy: f32, pub safe_t: f32, pub safe_b: f32,
    pub sqx: f32, pub sqy: f32, pub jaw: f32, pub jrot: f32, pub defer_white: bool, pub white_q: Vec<(Texture2D, f32, f32, f32, f32, bool, f32, f32, Option<Anim>, f32, f32, f32, Option<(f32, f32, f32)>)>, pub additive: bool, pub mat: u8 /* 0 обычный, 1 свет, 2 белый силуэт, 3 белый свет */,
}

const VS: &str = r#"#version 100
attribute vec3 position; attribute vec2 texcoord; attribute vec4 color0;
varying lowp vec2 uv; varying lowp vec4 color;
uniform mat4 Model; uniform mat4 Projection;
void main() { gl_Position = Projection * Model * vec4(position, 1); color = color0 / 255.0; uv = texcoord; }"#;
const FS: &str = r#"#version 100
varying lowp vec4 color; varying lowp vec2 uv; uniform sampler2D Texture;
void main() { gl_FragColor = color * texture2D(Texture, uv); }"#;
const FSW: &str = r#"#version 100
varying lowp vec4 color; varying lowp vec2 uv; uniform sampler2D Texture;
void main() { gl_FragColor = vec4(color.rgb, color.a * texture2D(Texture, uv).a); }"#;

fn radial_tex(n: u16, stops: &[(f32, [f32; 4])]) -> Texture2D {
    let mut px = vec![0u8; n as usize * n as usize * 4]; let c = n as f32 / 2.;
    for y in 0..n { for x in 0..n { let d = (((x as f32 + 0.5 - c).powi(2) + (y as f32 + 0.5 - c).powi(2)).sqrt() / c).min(1.);
        let mut col = stops[0].1; for w in stops.windows(2) { if d >= w[0].0 && d <= w[1].0 { let t = (d - w[0].0) / (w[1].0 - w[0].0).max(1e-4); for k in 0..4 { col[k] = w[0].1[k] + (w[1].1[k] - w[0].1[k]) * t; } } }
        if d >= stops[stops.len() - 1].0 { col = stops[stops.len() - 1].1; }
        let i = (y as usize * n as usize + x as usize) * 4; for k in 0..4 { px[i + k] = (col[k] * 255.) as u8; } } }
    let t = Texture2D::from_rgba8(n, n, &px); t.set_filter(FilterMode::Linear); t
}

/// Мягкое тёмное пятно (тень под существами)
fn shade_tex() -> Texture2D {
    let n = 64u16; let mut px = vec![0u8; n as usize * n as usize * 4];
    for y in 0..n { for x in 0..n { let d = (((x as f32 + 0.5) / n as f32 * 2. - 1.).powi(2) + ((y as f32 + 0.5) / n as f32 * 2. - 1.).powi(2)).sqrt().min(1.);
        let i = (y as usize * n as usize + x as usize) * 4; px[i] = 2; px[i + 1] = 4; px[i + 2] = 12; px[i + 3] = ((1. - d * d).max(0.).powf(1.4) * 255.) as u8; } }
    let t = Texture2D::from_rgba8(n, n, &px); t.set_filter(FilterMode::Linear); t
}
async fn tex(path: &str) -> Texture2D {
    match load_texture(path).await { Ok(t) => { t.set_filter(FilterMode::Linear); t }, Err(_) => Texture2D::from_rgba8(1, 1, &[255, 255, 255, 0]) }
}

impl Gfx {
    pub async fn load(manifest: &str, progress: &mut dyn FnMut(f32)) -> Gfx {
        let man: Value = serde_json::from_str(manifest).unwrap_or(Value::Null);
        let font = |b: &[u8]| { let mut f = load_ttf_font_from_bytes(b).expect("font"); f.set_filter(FilterMode::Linear); f };
        let font_b = font(include_bytes!("../assets/fonts/Roboto-Bold.ttf"));
        let font_k = font(include_bytes!("../assets/fonts/Roboto-Black.ttf"));
        let font_m = font(include_bytes!("../assets/fonts/Roboto-Medium.ttf"));
        let add = load_material(ShaderSource::Glsl { vertex: VS, fragment: FS }, MaterialParams {
            pipeline_params: PipelineParams { color_blend: Some(BlendState::new(Equation::Add, BlendFactor::Value(BlendValue::SourceAlpha), BlendFactor::One)), ..Default::default() },
            ..Default::default() }).expect("additive material");
        let wmat = load_material(ShaderSource::Glsl { vertex: VS, fragment: FSW }, MaterialParams {
            pipeline_params: PipelineParams { color_blend: Some(BlendState::new(Equation::Add, BlendFactor::Value(BlendValue::SourceAlpha), BlendFactor::OneMinusValue(BlendValue::SourceAlpha))), ..Default::default() },
            ..Default::default() }).expect("white material");
        let wadd = load_material(ShaderSource::Glsl { vertex: VS, fragment: FSW }, MaterialParams {
            pipeline_params: PipelineParams { color_blend: Some(BlendState::new(Equation::Add, BlendFactor::Value(BlendValue::SourceAlpha), BlendFactor::One)), ..Default::default() },
            ..Default::default() }).expect("white add material");
        let mut g = Gfx { spr: HashMap::new(), glow: vec![], soft: vec![], bul: vec![], icon: HashMap::new(), ground: vec![], caustic: None, shade: shade_tex(), tint: WHITE, font_b, font_k, font_m, add, wmat, wadd,
            vign: radial_tex(128, &[(0.0, [0., 0., 0.03, 0.]), (0.62, [0., 0., 0.03, 0.]), (1.0, [0., 0., 0.03, 0.78])]),
            hurt: radial_tex(128, &[(0.0, [1., 0., 0.16, 0.]), (0.62, [1., 0., 0.16, 0.]), (1.0, [1., 0.08, 0.24, 0.85])]),
            white: Texture2D::from_rgba8(1, 1, &[255, 255, 255, 255]), px: 1., w: 390., h: 844., ws: 1., ox: 0., oy: 0., safe_t: 0., safe_b: 0., sqx: 1., sqy: 1., jaw: 0., jrot: 0., defer_white: false, white_q: vec![], additive: false, mat: 0 };
        let meta = man["meta"].as_object().cloned().unwrap_or_default();
        let npal = crate::data::PAL_HEX.len();
        let total = (meta.len() + npal * 3 + 50 + 15) as f32; let mut done = 0f32;
        for (k, m) in meta.iter() {
            let t = tex(&format!("spr/{k}.png")).await;
            let anim = m["anim"].as_str().and_then(Anim::parse);
            let hinge = m["hinge"].as_array().map(|a| (a[0].as_f64().unwrap_or(0.5) as f32, a[1].as_f64().unwrap_or(0.5) as f32));
            g.spr.insert(k.clone(), Spr { tex: t, h: m["h"].as_f64().unwrap_or(20.) as f32, fl: m["fl"].as_bool().unwrap_or(false), anim, hinge });
            done += 1.; progress(done / total);
        }
        for i in 0..npal { g.glow.push(tex(&format!("fx/glow{i}.png")).await); g.soft.push(tex(&format!("fx/soft{i}.png")).await); g.bul.push(tex(&format!("fx/bul{i}.png")).await); done += 3.; progress(done / total); }
        for u in crate::data::UPG.iter() { g.icon.insert(u.id.into(), tex(&format!("icon/{}.png", u.id)).await); done += 1.; progress(done / total); }
        g.icon.insert("heal".into(), tex("icon/heal.png").await);
        for z in 0..15 { let t = tex(&format!("ground/g{z}.png")).await;
            unsafe { let ctx = get_internal_gl().quad_context; ctx.texture_set_wrap(t.raw_miniquad_id(), TextureWrap::Repeat, TextureWrap::Repeat); }
            g.ground.push(t); done += 1.; progress(done / total); }
        { let t = tex("fx/caustic.png").await; if t.width() > 2. { unsafe { let ctx = get_internal_gl().quad_context; ctx.texture_set_wrap(t.raw_miniquad_id(), TextureWrap::Repeat, TextureWrap::Repeat); } g.caustic = Some(t); } }
        g
    }
    /// Размеры экрана и масштаб мира, как resize() в веб-версии
    pub fn frame(&mut self, px: f32, cam_x: f32, cam_y: f32, shx: f32, shy: f32) -> (f32, f32) {
        self.px = px.max(0.5); self.w = screen_width() / self.px; self.h = screen_height() / self.px;
        let vs = (self.w.min(self.h) / 450.).clamp(0.8, 1.8); self.ws = vs * self.px;
        self.ox = self.px * self.w / 2. - (cam_x + shx) * self.ws; self.oy = self.px * self.h / 2. - (cam_y + shy) * self.ws;
        (self.w / 2. / vs, self.h / 2. / vs)
    }
    #[inline] pub fn sx(&self, x: f32) -> f32 { self.ox + x * self.ws }
    #[inline] pub fn sy(&self, y: f32) -> f32 { self.oy + y * self.ws }
    pub fn set_add(&mut self, on: bool) { self.set_mat(on as u8); }
    pub fn set_mat(&mut self, m: u8) { if m == self.mat { return; } self.mat = m; self.additive = m & 1 == 1;
        match m { 0 => gl_use_default_material(), 1 => gl_use_material(&self.add), 2 => gl_use_material(&self.wmat), _ => gl_use_material(&self.wadd) } }

    // ---------- спрайты ----------
    /// Спрайт в мире. ph — фаза анимации (радианы), white — вспышка попадания
    pub fn spr_world(&mut self, key: &str, x: f32, y: f32, ang: f32, sc: f32, alpha: f32, white: bool, ph: f32, force_fl: bool) {
        let (sx, sy) = (self.sx(x), self.sy(y)); let ws = self.ws; self.spr_screen(key, sx, sy, ang, sc * ws, alpha, white, ph, force_fl);
    }
    /// Спрайт в экранных (физических) пикселях; k — пикселей на мировую единицу
    pub fn spr_screen(&mut self, key: &str, sx: f32, sy: f32, ang: f32, k: f32, alpha: f32, white: bool, ph: f32, force_fl: bool) {
        let Some(s) = self.spr.get(key) else { return };
        let half = s.h * k; let flip = (s.fl || force_fl) && ang.cos() < 0.; let (sqx, sqy) = (self.sqx, self.sqy);
        let tex = s.tex.clone(); let anim = s.anim;
        let jaw = self.jaw; let hg = s.hinge.map(|(hu, hv)| (hu, hv, self.jrot));
        if self.defer_white { // тело сейчас, белую вспышку — одним проходом потом (меньше переключений шейдера)
            let tn = self.tint; self.set_mat(0); draw_warp_h(&tex, sx, sy, half, ang, flip, sqx, sqy, anim, ph, Color::new(tn.r, tn.g, tn.b, alpha), jaw, hg);
            if white { self.white_q.push((tex, sx, sy, half, ang, flip, sqx, sqy, anim, ph, alpha, jaw, hg)); } return; }
        let was = self.mat;
        self.set_mat(if white { 2 } else { 0 });
        let tn = if white { WHITE } else { self.tint };
        draw_warp_h(&tex, sx, sy, half, ang, flip, sqx, sqy, anim, ph, Color::new(tn.r, tn.g, tn.b, alpha), jaw, hg);
        self.set_mat(was);
    }
    /// Босс с настоящей пастью: глотка, нижняя челюсть на шарнире (поворот jrot, + раскрывает), тело.
    /// Если нарезки нет — обычный спрайт.
    pub fn spr_jaw(&mut self, key: &str, x: f32, y: f32, ang: f32, sc: f32, white: bool, ph: f32, jrot: f32) { self.spr_jaw_a(key, x, y, ang, sc, 1., white, ph, jrot) }
    /// То же с прозрачностью. Подвижная часть (_jaw) — челюсть или клешня; глотка (_mouth) — если есть
    pub fn spr_jaw_a(&mut self, key: &str, x: f32, y: f32, ang: f32, sc: f32, alpha: f32, white: bool, ph: f32, jrot: f32) {
        let body = format!("{key}_body");
        if !self.spr.contains_key(&body) { self.spr_world(key, x, y, ang, sc, alpha, white, ph, false); return; }
        self.jaw = 0.;
        let mouth = format!("{key}_mouth"); if self.spr.contains_key(&mouth) { self.spr_world(&mouth, x, y, ang, sc, alpha, false, ph, false); }
        self.jrot = jrot; self.spr_world(&format!("{key}_jaw"), x, y, ang, sc, alpha, white, ph, false); self.jrot = 0.;
        self.spr_world(&body, x, y, ang, sc, alpha, white, ph, false);
    }
    /// Белый светящийся силуэт (вспышка гибели)
    pub fn spr_ghost(&mut self, key: &str, x: f32, y: f32, ang: f32, sc: f32, alpha: f32) {
        let Some(s) = self.spr.get(key) else { return }; let half = s.h * sc * self.ws; let flip = s.fl && ang.cos() < 0.; let tex = s.tex.clone();
        let (sx, sy) = (self.sx(x), self.sy(y)); self.set_mat(3); draw_warp(&tex, sx, sy, half, ang, flip, 1., 1., None, 0., Color::new(1., 1., 1., alpha));
    }
    /// Нарисовать отложенные вспышки попаданий (полупрозрачный белый — не «призраки»)
    pub fn flush_white(&mut self) {
        let q = std::mem::take(&mut self.white_q); if q.is_empty() { return; } self.set_mat(2);
        for (t, sx, sy, half, ang, flip, sqx, sqy, an, ph, a, jaw, hg) in q.iter() { draw_warp_h(t, *sx, *sy, *half, *ang, *flip, *sqx, *sqy, *an, *ph, Color::new(1., 1., 1., 0.3 * a), *jaw, *hg); }
        self.white_q = q; self.white_q.clear(); self.set_mat(0);
    }
    pub fn spr_half(&self, key: &str) -> f32 { self.spr.get(key).map(|s| s.h).unwrap_or(20.) }
    pub fn spr_anim(&self, key: &str) -> Option<Anim> { self.spr.get(key).and_then(|s| s.anim) }

    // ---------- свечение ----------
    pub fn glow_world(&mut self, soft: bool, col: u8, x: f32, y: f32, r: f32, a: f32) { let (sx, sy, rr) = (self.sx(x), self.sy(y), r * self.ws); self.glow_scr(soft, col, sx, sy, rr, a); }
    pub fn glow_scr(&mut self, soft: bool, col: u8, sx: f32, sy: f32, r: f32, a: f32) {
        if r <= 0.1 || a <= 0.003 { return; }
        let t = if soft { &self.soft[col as usize % self.soft.len()] } else { &self.glow[col as usize % self.glow.len()] }.clone();
        self.set_add(true);
        draw_texture_ex(&t, sx - r, sy - r, Color::new(1., 1., 1., a.min(1.)), DrawTextureParams { dest_size: Some(vec2(r * 2., r * 2.)), ..Default::default() });
    }
    /// Растянутое свечение (снаряд): длина l, толщина w, вдоль угла ang
    pub fn glow_stretch(&mut self, col: u8, x: f32, y: f32, ang: f32, ox: f32, l: f32, w: f32, a: f32) {
        let t = self.glow[col as usize % self.glow.len()].clone(); self.set_add(true);
        let (sx, sy) = (self.sx(x), self.sy(y)); let (lw, ww) = (l * self.ws, w * self.ws); let off = ox * self.ws;
        let (cx, cy) = (sx + ang.cos() * (off + lw / 2.), sy + ang.sin() * (off + lw / 2.));
        draw_texture_ex(&t, cx - lw / 2., cy - ww / 2., Color::new(1., 1., 1., a), DrawTextureParams { dest_size: Some(vec2(lw, ww)), rotation: ang, ..Default::default() });
    }
    pub fn bul_world(&mut self, col: u8, x: f32, y: f32, r: f32) { let t = self.bul[col as usize % self.bul.len()].clone(); self.set_add(false);
        let (sx, sy, rr) = (self.sx(x), self.sy(y), r * self.ws); draw_texture_ex(&t, sx - rr, sy - rr, WHITE, DrawTextureParams { dest_size: Some(vec2(rr * 2., rr * 2.)), ..Default::default() }); }

    // ---------- фигуры в мире ----------
    pub fn circle_world(&mut self, x: f32, y: f32, r: f32, c: Color, add: bool) { self.set_add(add); draw_circle(self.sx(x), self.sy(y), r * self.ws, c); }
    pub fn arc_world(&mut self, x: f32, y: f32, r: f32, a0: f32, a1: f32, w: f32, c: Color, add: bool) {
        self.set_add(add); let (sx, sy, rr, ww) = (self.sx(x), self.sy(y), r * self.ws, (w * self.ws).max(1.));
        let n = (((a1 - a0).abs() * rr / 6.).ceil() as usize).clamp(8, 160);
        for i in 0..n { let t0 = a0 + (a1 - a0) * i as f32 / n as f32; let t1 = a0 + (a1 - a0) * (i + 1) as f32 / n as f32;
            draw_line(sx + t0.cos() * rr, sy + t0.sin() * rr, sx + t1.cos() * rr, sy + t1.sin() * rr, ww, c); }
    }
    pub fn dashed_arc_world(&mut self, x: f32, y: f32, r: f32, off: f32, w: f32, dash: f32, gap: f32, c: Color) {
        let circ = std::f32::consts::TAU * r; let n = (circ / (dash + gap)).floor().max(1.) as usize; let step = std::f32::consts::TAU / n as f32;
        for i in 0..n { let a = off + i as f32 * step; self.arc_world(x, y, r, a, a + step * dash / (dash + gap), w, c, false); }
    }
    pub fn line_world(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, w: f32, c: Color, add: bool) { self.set_add(add); draw_line(self.sx(x0), self.sy(y0), self.sx(x1), self.sy(y1), (w * self.ws).max(1.), c); }
    pub fn dashed_line_world(&mut self, x0: f32, y0: f32, x1: f32, y1: f32, w: f32, dash: f32, gap: f32, c: Color) {
        let l = ((x1 - x0).powi(2) + (y1 - y0).powi(2)).sqrt().max(1.); let (dx, dy) = ((x1 - x0) / l, (y1 - y0) / l); let mut t = 0.;
        while t < l { let e = (t + dash).min(l); self.line_world(x0 + dx * t, y0 + dy * t, x0 + dx * e, y0 + dy * e, w, c, false); t += dash + gap; }
    }
    /// Повёрнутый прямоугольник в мире: от точки (x,y) вдоль ang, смещение x0, длина l, ширина w
    pub fn rect_rot_world(&mut self, x: f32, y: f32, ang: f32, x0: f32, l: f32, w: f32, c: Color, outline: Option<(f32, Color)>) {
        self.set_add(false); let (ca, sa) = (ang.cos(), ang.sin()); let p = |lx: f32, ly: f32| vec2(self.sx(x + lx * ca - ly * sa), self.sy(y + lx * sa + ly * ca));
        let (a, b, cc, d) = (p(x0, -w / 2.), p(x0 + l, -w / 2.), p(x0 + l, w / 2.), p(x0, w / 2.));
        draw_triangle(a, b, cc, c); draw_triangle(a, cc, d, c);
        if let Some((lw, lc)) = outline { let lw = (lw * self.ws).max(1.); for (p0, p1) in [(a, b), (b, cc), (cc, d), (d, a)] { draw_line(p0.x, p0.y, p1.x, p1.y, lw, lc); } }
    }
    pub fn tri_world(&mut self, a: (f32, f32), b: (f32, f32), cpt: (f32, f32), col: Color) { self.set_add(false); draw_triangle(vec2(self.sx(a.0), self.sy(a.1)), vec2(self.sx(b.0), self.sy(b.1)), vec2(self.sx(cpt.0), self.sy(cpt.1)), col); }

    // ---------- интерфейс (логические пиксели) ----------
    pub fn font(&self, w: u8) -> &Font { match w { 0 => &self.font_m, 1 => &self.font_b, _ => &self.font_k } }
    /// Текст: align 0 — слева, 1 — по центру, 2 — справа; y — середина строки. Возвращает ширину
    pub fn text(&mut self, s: &str, x: f32, y: f32, size: f32, c: Color, align: u8, weight: u8) -> f32 { self.text_m(s, x, y, size, c, align, weight, false) }
    pub fn text_add(&mut self, s: &str, x: f32, y: f32, size: f32, c: Color, align: u8, weight: u8) -> f32 { self.text_m(s, x, y, size, c, align, weight, true) }
    pub fn text_m(&mut self, s: &str, x: f32, y: f32, size: f32, c: Color, align: u8, weight: u8, add: bool) -> f32 {
        if s.is_empty() { return 0.; } self.set_add(add);
        let (fs, k) = font_bucket(size * self.px); let font = self.font(weight).clone();
        let m = measure_text(s, Some(&font), fs, k); let w = m.width;
        let x0 = x * self.px - match align { 1 => w / 2., 2 => w, _ => 0. };
        draw_text_ex(s, x0, y * self.px + size * self.px * 0.36, TextParams { font: Some(&font), font_size: fs, font_scale: k, color: c, ..Default::default() });
        w / self.px
    }
    pub fn text_w(&self, s: &str, size: f32, weight: u8) -> f32 { let (fs, k) = font_bucket(size * self.px); measure_text(s, Some(self.font(weight)), fs, k).width / self.px }
    /// Текст с тенью (как HUD веб-версии)
    pub fn text_sh(&mut self, s: &str, x: f32, y: f32, size: f32, c: Color, align: u8, weight: u8) -> f32 { self.text(s, x + 1.5, y + 1.5, size, Color::new(0., 0., 0., 0.55 * c.a), align, weight); self.text(s, x, y, size, c, align, weight) }
    /// Текст в несколько строк по ширине. Возвращает высоту
    pub fn text_wrap(&mut self, s: &str, x: f32, y: f32, maxw: f32, size: f32, lh: f32, c: Color, align: u8, weight: u8) -> f32 {
        let lines = self.wrap(s, maxw, size, weight); for (i, l) in lines.iter().enumerate() { self.text(l, x, y + i as f32 * lh, size, c, align, weight); } lines.len() as f32 * lh
    }
    pub fn wrap(&self, s: &str, maxw: f32, size: f32, weight: u8) -> Vec<String> {
        let mut out = vec![];
        for para in s.split('\n') { let mut cur = String::new();
            for word in para.split(' ') { let cand = if cur.is_empty() { word.to_string() } else { format!("{cur} {word}") };
                if self.text_w(&cand, size, weight) > maxw && !cur.is_empty() { out.push(std::mem::take(&mut cur)); cur = word.to_string(); } else { cur = cand; } }
            out.push(cur); }
        out
    }
    pub fn rect(&mut self, x: f32, y: f32, w: f32, h: f32, c: Color) { self.set_add(false); draw_rectangle(x * self.px, y * self.px, w * self.px, h * self.px, c); }
    pub fn rrect(&mut self, x: f32, y: f32, w: f32, h: f32, r: f32, c: Color) {
        self.set_add(false); let p = self.px; let (x, y, w, h, r) = (x * p, y * p, w * p, h * p, (r * p).min(w / 2.).min(h / 2.).max(0.));
        draw_rectangle(x + r, y, w - 2. * r, h, c); draw_rectangle(x, y + r, r, h - 2. * r, c); draw_rectangle(x + w - r, y + r, r, h - 2. * r, c);
        for (cx, cy) in [(x + r, y + r), (x + w - r, y + r), (x + r, y + h - r), (x + w - r, y + h - r)] { draw_circle(cx, cy, r, c); }
    }
    pub fn rrect_line(&mut self, x: f32, y: f32, w: f32, h: f32, r: f32, lw: f32, c: Color) {
        self.set_add(false); let p = self.px; let (x, y, w, h, r, lw) = (x * p, y * p, w * p, h * p, (r * p).min(w / 2.).min(h / 2.), lw * p);
        draw_line(x + r, y, x + w - r, y, lw, c); draw_line(x + r, y + h, x + w - r, y + h, lw, c); draw_line(x, y + r, x, y + h - r, lw, c); draw_line(x + w, y + r, x + w, y + h - r, lw, c);
        let arc = |cx: f32, cy: f32, a0: f32| { let n = 8; for i in 0..n { let t0 = a0 + std::f32::consts::FRAC_PI_2 * i as f32 / n as f32; let t1 = a0 + std::f32::consts::FRAC_PI_2 * (i + 1) as f32 / n as f32;
            draw_line(cx + t0.cos() * r, cy + t0.sin() * r, cx + t1.cos() * r, cy + t1.sin() * r, lw, c); } };
        arc(x + w - r, y + r, -std::f32::consts::FRAC_PI_2); arc(x + w - r, y + h - r, 0.); arc(x + r, y + h - r, std::f32::consts::FRAC_PI_2); arc(x + r, y + r, std::f32::consts::PI);
    }
    /// Неоновая рамка: несколько обводок убывающей яркости вокруг скруглённого прямоугольника
    pub fn neon(&mut self, x: f32, y: f32, w: f32, h: f32, r: f32, c: Color, glow: f32) {
        for k in (1..=3).rev() { let o = k as f32 * 2.2; self.rrect_line(x - o, y - o, w + o * 2., h + o * 2., r + o, 2.2, Color::new(c.r, c.g, c.b, c.a * glow * 0.16 / k as f32)); }
        self.rrect_line(x, y, w, h, r, 1.6, c);
    }
    pub fn circle(&mut self, x: f32, y: f32, r: f32, c: Color) { self.set_add(false); draw_circle(x * self.px, y * self.px, r * self.px, c); }
    pub fn ring(&mut self, x: f32, y: f32, r: f32, w: f32, c: Color) { self.set_add(false); draw_circle_lines(x * self.px, y * self.px, r * self.px, w * self.px, c); }
    pub fn arc(&mut self, x: f32, y: f32, r: f32, a0: f32, a1: f32, w: f32, c: Color) {
        self.set_add(false); let p = self.px; let n = (((a1 - a0).abs() * r * p / 5.).ceil() as usize).clamp(6, 200);
        for i in 0..n { let t0 = a0 + (a1 - a0) * i as f32 / n as f32; let t1 = a0 + (a1 - a0) * (i + 1) as f32 / n as f32;
            draw_line((x + t0.cos() * r) * p, (y + t0.sin() * r) * p, (x + t1.cos() * r) * p, (y + t1.sin() * r) * p, w * p, c); }
    }
    pub fn tex_ui(&mut self, t: &Texture2D, x: f32, y: f32, w: f32, h: f32, c: Color) { self.set_add(false); let p = self.px; draw_texture_ex(t, x * p, y * p, c, DrawTextureParams { dest_size: Some(vec2(w * p, h * p)), ..Default::default() }); }
    pub fn tex_full(&mut self, t: &Texture2D, c: Color) { self.set_add(false); draw_texture_ex(t, 0., 0., c, DrawTextureParams { dest_size: Some(vec2(screen_width(), screen_height())), ..Default::default() }); }
    pub fn fill_screen(&mut self, c: Color, add: bool) { self.set_add(add); draw_rectangle(0., 0., screen_width(), screen_height(), c); }
}

/// Буквы растеризуются только в нескольких размерах и масштабируются: иначе атлас шрифта
/// разрастается с каждым новым размером и на телефоне превышает предел текстуры (чёрные плашки вместо текста)
pub fn font_bucket(px: f32) -> (u16, f32) {
    const B: [f32; 6] = [20., 32., 48., 72., 108., 160.];
    let b = B.iter().copied().find(|&b| b >= px * 0.95).unwrap_or(160.); (b as u16, px.max(1.) / b)
}
/// Рисует текстуру сеткой и деформирует её по виду анимации (хвост, щупальца, купол, ножки…).
/// half — половина размера в пикселях, (sqx,sqy) — сжатие вдоль/поперёк тела.
pub fn draw_warp(t: &Texture2D, sx: f32, sy: f32, half: f32, ang: f32, flip: bool, sqx: f32, sqy: f32, anim: Option<Anim>, ph: f32, col: Color) { draw_warp_j(t, sx, sy, half, ang, flip, sqx, sqy, anim, ph, col, 0.) }
/// То же, плюс jaw — раскрытие пасти (у боссов вида сбоку: нижняя челюсть у головы отходит вниз)
pub fn draw_warp_j(t: &Texture2D, sx: f32, sy: f32, half: f32, ang: f32, flip: bool, sqx: f32, sqy: f32, anim: Option<Anim>, ph: f32, col: Color, jaw: f32) { draw_warp_h(t, sx, sy, half, ang, flip, sqx, sqy, anim, ph, col, jaw, None) }
/// То же, плюс поворот картинки вокруг шарнира (hu, hv) на угол r — для нижней челюсти
pub fn draw_warp_h(t: &Texture2D, sx: f32, sy: f32, half: f32, ang: f32, flip: bool, sqx: f32, sqy: f32, anim: Option<Anim>, ph: f32, col: Color, jaw: f32, hinge: Option<(f32, f32, f32)>) {
    let (ca, sa) = (ang.cos(), ang.sin());
    let hinge = hinge.filter(|h| h.2.abs() > 0.002);
    let anim = if (jaw > 0.01 || hinge.is_some()) && anim.is_none() { Some(Anim::Fin) } else { anim };
    let Some(an) = anim else {
        draw_texture_ex(t, sx - half * sqx, sy - half * sqy, col, DrawTextureParams { dest_size: Some(vec2(half * 2. * sqx, half * 2. * sqy)), rotation: ang, flip_y: flip, ..Default::default() });
        return;
    };
    // простые виды — одно преобразование всей картинки
    let (mut kx, mut ky, mut rot) = (1f32, 1f32, 0f32);
    match an { Anim::Pulse => { kx = 1. + 0.07 * ph.sin(); ky = 1. + 0.07 * (ph + 1.1).sin(); rot = (ph * 0.5).sin() * 0.06; }
        Anim::Flap => { ky = 1. - 0.22 * ph.sin(); } Anim::Orb => { kx = 1. + 0.035 * ph.sin(); ky = 2. - kx; } _ => {} }
    if matches!(an, Anim::Pulse | Anim::Flap | Anim::Orb) && jaw <= 0.01 && hinge.is_none() {
        draw_texture_ex(t, sx - half * sqx * kx, sy - half * sqy * ky, col, DrawTextureParams { dest_size: Some(vec2(half * 2. * sqx * kx, half * 2. * sqy * ky)), rotation: ang + rot, flip_y: flip, ..Default::default() });
        return;
    }
    // мелким на экране существам хватает грубой сетки — втрое меньше вершин
    let (NX, NY) = if half < 45. { (8usize, 5usize) } else if half < 110. { (12, 8) } else { (16, 10) };
    let mut verts: Vec<Vertex> = Vec::with_capacity((NX + 1) * (NY + 1)); let mut idx: Vec<u16> = Vec::with_capacity(NX * NY * 6);
    let c8 = [(col.r * 255.) as u8, (col.g * 255.) as u8, (col.b * 255.) as u8, (col.a * 255.) as u8];
    for j in 0..=NY { let v = j as f32 / NY as f32;
        for i in 0..=NX { let u = i as f32 / NX as f32;
            // смещение в долях картинки (du по x, dv по y)
            let (mut du, mut dv) = (0f32, 0f32);
            match an {
                // хвост сильнее изгибается, а края (плавники сверху и снизу) трепещут своей волной
                Anim::Swim => { let tt = (1. - u).powf(1.5); dv = (ph - u * 5.2).sin() * 0.14 * tt; let ed = ((v - 0.5).abs() * 2.).powi(2);
                    dv += (ph * 1.9 - u * 9. + v * 3.).sin() * 0.035 * ed * (0.4 + 0.6 * tt); du = (ph - u * 5.2).cos() * 0.025 * tt; }
                Anim::Fin => { let tt = (1. - u).powf(2.); dv = (ph - u * 4.).sin() * 0.1 * tt; let ed = ((v - 0.5).abs() * 2.).powi(2);
                    dv += (ph * 2.2 - u * 10.).sin() * 0.03 * ed; }
                Anim::Tent => { let tt = ((0.58 - u) / 0.58).max(0.); dv = (ph - u * 9.).sin() * 0.16 * tt * tt; let syk = 1. - 0.03 * ph.sin() * (1. - tt); dv += (v - 0.5) * (syk - 1.); }
                Anim::Jelly => { let bell = if u > 0.5 { (u - 0.5) / 0.5 } else { 0. }; let tt = ((0.62 - u) / 0.62).max(0.);
                    let syk = 1. + 0.14 * ph.sin() * bell - 0.07 * (ph - 1.3).sin() * tt; du = (u - 0.75) * 0.06 * ph.sin() * bell; dv = (ph - u * 10.).sin() * 0.13 * tt + (v - 0.5) * (syk - 1.); }
                Anim::JellyV => { let bell = if v < 0.42 { 1. } else { (1. - (v - 0.42) / 0.16).max(0.) }; let tt = ((v - 0.42) / 0.5).clamp(0., 1.);
                    let wk = 1. + 0.1 * ph.sin() * bell - 0.05 * (ph - 1.3).sin() * tt; du = (u - 0.5) * (wk - 1.) + (ph - v * 9.).sin() * 0.06 * tt * tt; }
                Anim::Crab => { let leg = (((v - 0.5).abs() - 0.12) * 4.).clamp(0., 1.); du = leg * (ph + if v < 0.5 { 0. } else { std::f32::consts::PI } + v * 5.).sin() * 0.032; }
                _ => {}
            }
            if jaw > 0.01 && u > 0.62 { let k = ((u - 0.62) / 0.38).min(1.); if v > 0.5 { dv += jaw * 0.16 * k * ((v - 0.5) * 2.).min(1.); } else { dv -= jaw * 0.04 * k * ((0.5 - v) * 2.).min(1.); } }
            if let Some((hu, hv, r)) = hinge { let (x, y) = (u + du - hu, v + dv - hv); let (c, s_) = (r.cos(), r.sin()); du = hu + x * c - y * s_ - u; dv = hv + x * s_ + y * c - v; }
            let lx = ((u + du) * 2. - 1.) * half * sqx; let mut ly = ((v + dv) * 2. - 1.) * half * sqy; if flip { ly = -ly; }
            verts.push(Vertex::new(sx + lx * ca - ly * sa, sy + lx * sa + ly * ca, 0., u, v, Color::from_rgba(c8[0], c8[1], c8[2], c8[3])));
        } }
    for j in 0..NY { for i in 0..NX { let a = (j * (NX + 1) + i) as u16; let b = a + 1; let c = a + (NX + 1) as u16; let d = c + 1; idx.extend_from_slice(&[a, b, c, b, d, c]); } }
    draw_mesh(&Mesh { vertices: verts, indices: idx, texture: Some(t.clone()) });
}

// ---------- подсветка (bloom) ----------
const FS_BRIGHT: &str = r#"#version 100
precision mediump float;
varying lowp vec4 color; varying lowp vec2 uv; uniform sampler2D Texture; uniform vec2 px;
void main() {
    vec3 s = texture2D(Texture, uv + vec2(-px.x, -px.y)).rgb + texture2D(Texture, uv + vec2(px.x, -px.y)).rgb
           + texture2D(Texture, uv + vec2(-px.x, px.y)).rgb + texture2D(Texture, uv + vec2(px.x, px.y)).rgb;
    s *= 0.25; float l = max(s.r, max(s.g, s.b)); float k = smoothstep(0.42, 0.95, l);
    gl_FragColor = vec4(s * k, 1.0);
}"#;
const FS_BLUR: &str = r#"#version 100
precision mediump float;
varying lowp vec4 color; varying lowp vec2 uv; uniform sampler2D Texture; uniform vec2 dir;
void main() {
    vec3 s = texture2D(Texture, uv).rgb * 0.227;
    s += (texture2D(Texture, uv + dir * 1.385).rgb + texture2D(Texture, uv - dir * 1.385).rgb) * 0.316;
    s += (texture2D(Texture, uv + dir * 3.231).rgb + texture2D(Texture, uv - dir * 3.231).rgb) * 0.070;
    gl_FragColor = vec4(s, 1.0);
}"#;

pub struct Bloom { pub scene: RenderTarget, pub a: RenderTarget, pub b: RenderTarget, pub bright: Material, pub blur: Material, pub w: u32, pub h: u32, pub on: bool }
impl Bloom {
    pub fn new() -> Option<Bloom> {
        let mk = |fs: &str, u: &str| load_material(ShaderSource::Glsl { vertex: VS, fragment: fs }, MaterialParams { uniforms: vec![UniformDesc::new(u, UniformType::Float2)], ..Default::default() }).ok();
        let bright = mk(FS_BRIGHT, "px")?; let blur = mk(FS_BLUR, "dir")?;
        let rt = |w: u32, h: u32| { let r = render_target(w.max(1), h.max(1)); r.texture.set_filter(FilterMode::Linear); r };
        Some(Bloom { scene: rt(1, 1), a: rt(1, 1), b: rt(1, 1), bright, blur, w: 0, h: 0, on: false })
    }
    fn ensure(&mut self) {
        let (w, h) = (screen_width() as u32, screen_height() as u32);
        if w == self.w && h == self.h { return; } self.w = w; self.h = h;
        let rt = |w: u32, h: u32| { let r = render_target(w.max(1), h.max(1)); r.texture.set_filter(FilterMode::Linear); r };
        self.scene = rt(w, h); self.a = rt(w / 6, h / 6); self.b = rt(w / 6, h / 6);
    }
    fn cam(rt: &RenderTarget, w: f32, h: f32) -> Camera2D { let mut c = Camera2D::from_display_rect(Rect::new(0., 0., w, h)); c.render_target = Some(rt.clone()); c.zoom.y = -c.zoom.y; c }
    /// Начать рисовать мир в текстуру
    pub fn begin(&mut self, gx: &mut Gfx) { self.ensure(); gx.set_mat(0); set_camera(&Self::cam(&self.scene, screen_width(), screen_height())); }
    /// Выделить яркое, размыть и наложить на экран
    pub fn end(&mut self, gx: &mut Gfx, strength: f32) {
        gx.set_mat(0);
        let (sw, sh) = (screen_width(), screen_height()); let (qw, qh) = ((self.w / 6).max(1) as f32, (self.h / 6).max(1) as f32);
        let full = |t: &Texture2D, w: f32, h: f32, c: Color| draw_texture_ex(t, 0., 0., c, DrawTextureParams { dest_size: Some(vec2(w, h)), ..Default::default() });
        set_camera(&Self::cam(&self.a, qw, qh)); clear_background(BLACK);
        self.bright.set_uniform("px", vec2(2.5 / sw, 2.5 / sh)); gl_use_material(&self.bright); full(&self.scene.texture, qw, qh, WHITE);
        for _ in 0..1 {
            set_camera(&Self::cam(&self.b, qw, qh)); self.blur.set_uniform("dir", vec2(1. / qw, 0.)); gl_use_material(&self.blur); full(&self.a.texture, qw, qh, WHITE);
            set_camera(&Self::cam(&self.a, qw, qh)); self.blur.set_uniform("dir", vec2(0., 1. / qh)); gl_use_material(&self.blur); full(&self.b.texture, qw, qh, WHITE);
        }
        gl_use_default_material(); set_default_camera();
        full(&self.scene.texture, sw, sh, WHITE);
        gl_use_material(&gx.add); full(&self.a.texture, sw, sh, Color::new(1., 1., 1., strength)); gl_use_default_material(); gx.mat = 0; gx.additive = false;
    }
}
