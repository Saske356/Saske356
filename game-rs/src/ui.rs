//! Ввод (касания и мышь) и интерфейс в стиле веб-версии: неоновые кнопки, карточки, прокручиваемые списки.
//! Всё в логических пикселях (как CSS px): физические = логические × gx.px.
use crate::gfx::*;
use macroquad::prelude::*;
use std::collections::HashMap;

#[derive(Clone, Copy, Debug)]
pub struct Ptr { pub id: u64, pub x: f32, pub y: f32, pub sx: f32, pub sy: f32, pub moved: f32, pub used: bool, pub scroll: bool, pub t: f32 }
#[derive(Default, Clone, Copy)]
pub struct Scroll { pub off: f32, pub vel: f32, pub max: f32, pub drag: Option<(u64, f32)> }

#[derive(Clone, Copy, PartialEq)]
pub enum St { Cyan, Pink, Gold, Dim }

const MOUSE: u64 = u64::MAX;

pub struct Ui {
    pub ptrs: Vec<Ptr>, pub downs: Vec<Ptr>, pub ups: Vec<Ptr>, touch_seen: bool, mouse_down: bool,
    pub scrolls: HashMap<u32, Scroll>, pub clip: Option<Rect>, pub alpha: f32, pub lock: f32, pub back: bool, pub any_click: bool, pub wheel: f32,
    pub keys_dash: bool, pub keys_flare: bool, pub keys_pause: bool, pub kx: f32, pub ky: f32, pub key_num: Option<usize>,
}
impl Ui {
    pub fn new() -> Ui { Ui { ptrs: vec![], downs: vec![], ups: vec![], touch_seen: false, mouse_down: false, scrolls: HashMap::new(), clip: None, alpha: 1., lock: 0., back: false,
        any_click: false, wheel: 0., keys_dash: false, keys_flare: false, keys_pause: false, kx: 0., ky: 0., key_num: None } }
    /// Собирает события ввода за кадр
    pub fn begin(&mut self, px: f32, dt: f32) {
        self.downs.clear(); self.ups.clear(); self.any_click = false; self.clip = None; self.alpha = 1.;
        if self.lock > 0. { self.lock -= dt; }
        for p in self.ptrs.iter_mut() { p.t += dt; }
        let ts = touches();
        if !ts.is_empty() { self.touch_seen = true; }
        if self.touch_seen {
            // macroquad хранит одно событие на палец за кадр: «нажал» второго пальца перетирается его «двигаю»,
            // а быстрый тап приходит сразу как «отпустил». Восстанавливаем пропущенные нажатия.
            let ids: Vec<u64> = ts.iter().map(|t| t.id).collect();
            self.ptrs.retain(|p| ids.contains(&p.id)); // палец пропал без «отпустил»
            for t in ts { let (x, y) = (t.position.x / px, t.position.y / px);
                let known = self.ptrs.iter().any(|q| q.id == t.id);
                match t.phase {
                    TouchPhase::Started | TouchPhase::Moved | TouchPhase::Stationary if !known => { let p = Ptr { id: t.id, x, y, sx: x, sy: y, moved: 0., used: false, scroll: false, t: 0. }; self.ptrs.push(p); self.downs.push(p); }
                    TouchPhase::Started => { if let Some(p) = self.ptrs.iter_mut().find(|q| q.id == t.id) { *p = Ptr { id: t.id, x, y, sx: x, sy: y, moved: 0., used: false, scroll: false, t: 0. }; self.downs.push(*p); } }
                    TouchPhase::Moved | TouchPhase::Stationary => if let Some(p) = self.ptrs.iter_mut().find(|q| q.id == t.id) { p.moved = p.moved.max(((x - p.sx).powi(2) + (y - p.sy).powi(2)).sqrt()); p.x = x; p.y = y; },
                    TouchPhase::Ended | TouchPhase::Cancelled => {
                        if let Some(i) = self.ptrs.iter().position(|q| q.id == t.id) { let mut p = self.ptrs.remove(i); p.x = x; p.y = y; self.ups.push(p); }
                        else { let p = Ptr { id: t.id, x, y, sx: x, sy: y, moved: 0., used: false, scroll: false, t: 0. }; self.downs.push(p); self.ups.push(p); } }
                } }
        } else {
            let (mx, my) = mouse_position(); let (x, y) = (mx / px, my / px); let d = is_mouse_button_down(MouseButton::Left);
            if d && !self.mouse_down { let p = Ptr { id: MOUSE, x, y, sx: x, sy: y, moved: 0., used: false, scroll: false, t: 0. }; self.ptrs.push(p); self.downs.push(p); }
            if let Some(p) = self.ptrs.iter_mut().find(|q| q.id == MOUSE) { p.moved = p.moved.max(((x - p.sx).powi(2) + (y - p.sy).powi(2)).sqrt()); p.x = x; p.y = y; }
            if !d && self.mouse_down { if let Some(i) = self.ptrs.iter().position(|q| q.id == MOUSE) { let mut p = self.ptrs.remove(i); p.x = x; p.y = y; self.ups.push(p); } }
            self.mouse_down = d;
        }
        self.wheel = mouse_wheel().1;
        self.back = is_key_pressed(KeyCode::Escape) || is_key_pressed(KeyCode::Back);
        self.keys_dash = is_key_pressed(KeyCode::Space) || is_key_pressed(KeyCode::LeftShift) || is_key_pressed(KeyCode::RightShift);
        self.keys_flare = is_key_pressed(KeyCode::E) || is_key_pressed(KeyCode::Q) || is_key_pressed(KeyCode::Enter);
        self.keys_pause = is_key_pressed(KeyCode::P);
        let k = |a: KeyCode, b: KeyCode| (is_key_down(a) || is_key_down(b)) as i32 as f32;
        self.kx = k(KeyCode::D, KeyCode::Right) - k(KeyCode::A, KeyCode::Left); self.ky = k(KeyCode::S, KeyCode::Down) - k(KeyCode::W, KeyCode::Up);
        self.key_num = [KeyCode::Key1, KeyCode::Key2, KeyCode::Key3, KeyCode::Key4].iter().position(|k| is_key_pressed(*k));
    }
    pub fn reset(&mut self) { for p in self.ptrs.iter_mut() { p.used = true; } }
    fn in_clip(&self, x: f32, y: f32) -> bool { self.clip.map(|c| c.contains(vec2(x, y))).unwrap_or(true) }
    /// Нажатие пришлось в прямоугольник в этом кадре (для игровых кнопок: срабатывают сразу)
    pub fn press(&mut self, r: Rect) -> bool {
        if self.lock > 0. { return false; }
        let mut hit = false;
        for d in self.downs.iter_mut() { if !d.used && r.contains(vec2(d.x, d.y)) { d.used = true; hit = true; let id = d.id; if let Some(p) = self.ptrs.iter_mut().find(|p| p.id == id) { p.used = true; } } }
        hit
    }
    /// Касание началось и закончилось внутри прямоугольника, без прокрутки
    pub fn tap(&mut self, r: Rect) -> bool {
        if self.lock > 0. { return false; }
        for u in self.ups.iter_mut() {
            if u.used || u.scroll || u.moved > 18. { continue; }
            if r.contains(vec2(u.sx, u.sy)) && r.contains(vec2(u.x, u.y)) && self.clip.map(|c| c.contains(vec2(u.x, u.y))).unwrap_or(true) { u.used = true; self.any_click = true; return true; }
        }
        false
    }
    pub fn held(&self, r: Rect) -> bool { self.ptrs.iter().any(|p| !p.used && !p.scroll && r.contains(vec2(p.sx, p.sy)) && r.contains(vec2(p.x, p.y)) && self.in_clip(p.x, p.y)) }
    /// Касание где угодно (для пропуска заставок)
    pub fn tap_any(&mut self) -> bool { if self.lock > 0. { return false; } let mut h = false; for d in self.downs.iter_mut() { if !d.used { d.used = true; h = true; } } h }

    /// Прокручиваемая область: возвращает смещение содержимого
    pub fn scroll(&mut self, id: u32, r: Rect, content_h: f32, dt: f32) -> f32 {
        let mut s = self.scrolls.get(&id).copied().unwrap_or_default(); s.max = (content_h - r.h).max(0.);
        if let Some((pid, ly)) = s.drag {
            if let Some(p) = self.ptrs.iter().find(|p| p.id == pid) { let dy = p.y - ly; s.off -= dy; s.vel = -dy / dt.max(1e-3); s.drag = Some((pid, p.y)); }
            else { s.drag = None; }
        } else {
            for p in self.ptrs.iter_mut() { if !p.used && !p.scroll && r.contains(vec2(p.sx, p.sy)) && (p.y - p.sy).abs() > 10. { p.scroll = true; s.drag = Some((p.id, p.y)); break; } }
            if s.drag.is_none() { s.off += s.vel * dt; s.vel *= (-dt * 4.).exp(); if s.vel.abs() < 5. { s.vel = 0.; } }
        }
        let (mx, my) = mouse_position(); if self.wheel != 0. && r.contains(vec2(mx, my) / screen_dpi_scale().max(1.)) { s.off -= self.wheel.signum() * 60.; }
        if s.off < 0. { s.off = if s.drag.is_some() { s.off * 0.5 } else { s.off * (1. - (dt * 14.).min(1.)) }; if s.drag.is_none() { s.vel = 0.; } }
        if s.off > s.max { let o = s.off - s.max; s.off = s.max + if s.drag.is_some() { o * 0.5 } else { o * (1. - (dt * 14.).min(1.)) }; if s.drag.is_none() { s.vel = 0.; } }
        self.scrolls.insert(id, s); s.off
    }
    pub fn scroll_reset(&mut self, id: u32) { self.scrolls.remove(&id); }
    pub fn clip_on(&mut self, gx: &Gfx, r: Rect) { self.clip = Some(r); let p = gx.px; unsafe { get_internal_gl().quad_gl.scissor(Some(((r.x * p) as i32, (r.y * p) as i32, (r.w * p) as i32, (r.h * p) as i32))); } }
    pub fn clip_off(&mut self) { self.clip = None; unsafe { get_internal_gl().quad_gl.scissor(None); } }

    // ---------- виджеты ----------
    /// Неоновая кнопка. Возвращает true при нажатии
    pub fn btn(&mut self, gx: &mut Gfx, r: Rect, label: &str, st: St, size: f32, on: bool) -> bool {
        let held = on && self.held(r); let k = if held { 0.95 } else { 1. };
        let rr = Rect::new(r.x + r.w * (1. - k) / 2., r.y + r.h * (1. - k) / 2., r.w * k, r.h * k);
        draw_btn(gx, rr, st, if on { self.alpha } else { self.alpha * 0.38 }, held);
        let col = match st { St::Gold => hex(0xfff6d6), _ => hex(0xeaffff) };
        let lines: Vec<&str> = label.split('\n').collect();
        let lh = size * 1.12; let y0 = rr.y + rr.h / 2. - (lines.len() as f32 - 1.) * lh / 2.;
        for (i, l) in lines.iter().enumerate() { let s = if i == 0 { size } else { size * 0.6 }; let w = gx.text_w(l, s, 2); let s = if w > rr.w - 14. { s * (rr.w - 14.) / w } else { s };
            gx.text(l, rr.x + rr.w / 2., y0 + i as f32 * lh, s, with_alpha(col, if i == 0 { 1. } else { 0.8 } * self.alpha * if on { 1. } else { 0.5 }), 1, if i == 0 { 2 } else { 0 }); }
        on && self.tap(r)
    }
    /// Текстовая ссылка (подчёркнутая)
    pub fn link(&mut self, gx: &mut Gfx, cx: f32, cy: f32, label: &str, size: f32) -> bool {
        let w = gx.text_w(label, size, 0); let r = Rect::new(cx - w / 2. - 10., cy - size, w + 20., size * 2.);
        let a = if self.held(r) { 0.9 } else { 0.6 } * self.alpha; let c = Color::new(0.8, 1., 1., a);
        gx.text(label, cx, cy, size, c, 1, 0); gx.rect(cx - w / 2., cy + size * 0.62, w, 1., c);
        self.tap(r)
    }
}

pub fn with_alpha(mut c: Color, a: f32) -> Color { c.a *= a; c }

/// Скруглённый прямоугольник с вертикальным градиентом (веер треугольников от центра)
pub fn rrect_grad(gx: &mut Gfx, x: f32, y: f32, w: f32, h: f32, r: f32, top: Color, bot: Color) {
    gx.set_add(false); let p = gx.px; let (x, y, w, h) = (x * p, y * p, w * p, h * p); let r = (r * p).min(w / 2.).min(h / 2.).max(0.);
    let col = |yy: f32| { let t = ((yy - y) / h).clamp(0., 1.); Color::new(top.r + (bot.r - top.r) * t, top.g + (bot.g - top.g) * t, top.b + (bot.b - top.b) * t, top.a + (bot.a - top.a) * t) };
    let mut v = vec![Vertex::new(x + w / 2., y + h / 2., 0., 0., 0., col(y + h / 2.))];
    let n = 6; let corners = [(x + w - r, y + r, -std::f32::consts::FRAC_PI_2), (x + w - r, y + h - r, 0.), (x + r, y + h - r, std::f32::consts::FRAC_PI_2), (x + r, y + r, std::f32::consts::PI)];
    for (cx, cy, a0) in corners { for i in 0..=n { let a = a0 + std::f32::consts::FRAC_PI_2 * i as f32 / n as f32; let (px_, py_) = (cx + a.cos() * r, cy + a.sin() * r); v.push(Vertex::new(px_, py_, 0., 0., 0., col(py_))); } }
    let m = v.len() as u16 - 1; let mut idx = Vec::with_capacity(m as usize * 3);
    for i in 1..=m { idx.extend_from_slice(&[0, i, if i == m { 1 } else { i + 1 }]); }
    draw_mesh(&Mesh { vertices: v, indices: idx, texture: None });
}

pub fn style_cols(st: St) -> (Color, Color, Color) {
    match st {
        St::Cyan => (Color::new(0.20, 0.78, 1., 0.55), Color::new(0.06, 0.24, 0.52, 0.70), Color::new(0.55, 0.96, 1., 0.95)),
        St::Pink => (Color::new(1., 0.36, 0.80, 0.55), Color::new(0.40, 0.08, 0.42, 0.70), Color::new(1., 0.60, 0.90, 0.95)),
        St::Gold => (Color::new(1., 0.78, 0.25, 0.55), Color::new(0.50, 0.26, 0.04, 0.70), Color::new(1., 0.86, 0.42, 1.)),
        St::Dim => (Color::new(63. / 255., 240. / 255., 1., 0.10), Color::new(20. / 255., 60. / 255., 110. / 255., 0.25), Color::new(120. / 255., 245. / 255., 1., 0.45)),
    }
}
pub fn draw_btn(gx: &mut Gfx, r: Rect, st: St, a: f32, held: bool) {
    let (top, bot, bord) = style_cols(st); let rad = (r.h * 0.28).min(16.);
    // свечение вокруг (box-shadow)
    let g = if held { 0.7 } else { 0.38 };
    for k in (1..=4).rev() { let o = k as f32 * 2.5; gx.rrect_line(r.x - o, r.y - o, r.w + o * 2., r.h + o * 2., rad + o, 2.6, Color::new(bord.r, bord.g, bord.b, a * g * 0.14 / k as f32)); }
    rrect_grad(gx, r.x, r.y, r.w, r.h, rad, with_alpha(Color::new(2. / 255., 8. / 255., 20. / 255., 0.55), a), with_alpha(Color::new(2. / 255., 8. / 255., 20. / 255., 0.55), a));
    rrect_grad(gx, r.x, r.y, r.w, r.h, rad, with_alpha(top, a * if held { 1.4 } else { 1. }), with_alpha(bot, a));
    // глянцевый блик по верхней половине
    rrect_grad(gx, r.x + 3., r.y + 2., r.w - 6., r.h * 0.46, (rad - 2.).max(1.), Color::new(1., 1., 1., 0.20 * a), Color::new(1., 1., 1., 0.02 * a));
    // внутреннее свечение у краёв
    gx.rrect_line(r.x + 3., r.y + 3., r.w - 6., r.h - 6., (rad - 3.).max(1.), 3., with_alpha(Color::new(bord.r, bord.g, bord.b, 0.1), a));
    gx.rrect_line(r.x, r.y, r.w, r.h, rad, 2., with_alpha(bord, a));
}
/// Полупрозрачная панель (элемент списка)
pub fn panel(gx: &mut Gfx, r: Rect, rad: f32, fill: Color, border: Color, a: f32) {
    rrect_grad(gx, r.x, r.y, r.w, r.h, rad, with_alpha(fill, a), with_alpha(fill, a)); gx.rrect_line(r.x, r.y, r.w, r.h, rad, 1., with_alpha(border, a));
}
/// Значок жемчужины
pub fn pearl(gx: &mut Gfx, x: f32, y: f32, r: f32, a: f32) {
    let p = gx.px; gx.glow_scr(true, crate::data::c::CORAL, x * p, y * p, r * 2.2 * p, 0.35 * a); gx.set_add(false);
    gx.circle(x, y, r, Color::new(0.79, 0.63, 1., a)); gx.circle(x - r * 0.12, y - r * 0.12, r * 0.75, Color::new(1., 0.84, 0.96, a)); gx.circle(x - r * 0.3, y - r * 0.3, r * 0.35, Color::new(1., 1., 1., a));
}
/// Заголовок экрана с неоновым свечением
pub fn h2(gx: &mut Gfx, s: &str, cx: f32, cy: f32, size: f32, a: f32) { h2c(gx, s, cx, cy, size, a, crate::data::c::CYAN, WHITE) }
pub fn h2c(gx: &mut Gfx, s: &str, cx: f32, cy: f32, size: f32, a: f32, glow: u8, col: Color) {
    let gc = hex(crate::data::PAL_HEX[glow as usize]);
    let w = gx.text_w(s, size, 2); let p = gx.px; let size = if w > gx.w - 24. { size * (gx.w - 24.) / w } else { size }; let w = w.min(gx.w - 24.);
    let t = gx.glow[glow as usize].clone(); gx.set_add(true);
    draw_texture_ex(&t, (cx - w * 0.7) * p, (cy - size * 1.1) * p, Color::new(1., 1., 1., 0.35 * a), DrawTextureParams { dest_size: Some(vec2(w * 1.4 * p, size * 2.2 * p)), ..Default::default() });
    for (dx, dy) in [(-1.2, 0.), (1.2, 0.), (0., -1.2), (0., 1.2)] { gx.set_add(true); gx.text_add(s, cx + dx, cy + dy, size, Color::new(gc.r, gc.g, gc.b, 0.35 * a), 1, 2); }
    gx.text(s, cx, cy, size, Color::new(col.r, col.g, col.b, a), 1, 2);
}
/// Полоса прогресса
pub fn pbar(gx: &mut Gfx, x: f32, y: f32, w: f32, h: f32, k: f32, col: Color, a: f32) {
    gx.rrect(x, y, w, h, h / 2., Color::new(1., 1., 1., 0.1 * a)); if k > 0. { gx.rrect(x, y, (w * k.min(1.)).max(h), h, h / 2., with_alpha(col, a)); }
}
/// Метки уровня улучшения
pub fn pips(gx: &mut Gfx, x: f32, y: f32, n: u8, max: u8, a: f32) -> f32 {
    for k in 0..max { let c = if k < n { Color::new(0.25, 0.94, 1., a) } else { Color::new(1., 1., 1., 0.18 * a) }; gx.rrect(x + k as f32 * 10., y - 3.5, 7., 7., 2., c); }
    max as f32 * 10.
}
