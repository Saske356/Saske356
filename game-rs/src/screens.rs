//! Экраны меню в стиле веб-версии. Вертикальная и горизонтальная раскладки.
use crate::app::*;
use crate::data::{self, c, CHARS, ET, PAL_HEX, SHOP, SKINS, TALENTS, UPG, U_HEAL};
use crate::game::*;
use crate::gfx::*;
use crate::i18n::{self, t, tf};
use crate::ui::{self, h2, panel, pbar, pearl, pips, with_alpha, St};
use macroquad::prelude::*;

fn pal(i: u8) -> Color { hex(PAL_HEX[i as usize % PAL_HEX.len()]) }
fn vol_l(on: bool, v: u8) -> String { if !on || v == 0 { t("off") } else { format!("{}%", v as u32 * 10) } }
fn vol_next(on: bool, v: u8) -> u8 { if !on || v == 0 { 10 } else if v > 8 { 8 } else if v > 2 { v - 2 } else { 0 } }
fn on_off(v: bool) -> String { if v { t("on") } else { t("off") } }

pub fn draw(a: &mut App) {
    if a.scr == Scr::None { return; }
    let al = (a.scr_t / 0.28).min(1.); a.ui.alpha = al;
    if a.scr != Scr::Title { let light = matches!(a.scr, Scr::Level | Scr::Pause | Scr::Revive); let tm = a.g.t; menu_backdrop(&mut a.gx, tm, al, light); }
    match a.scr {
        Scr::Title => title(a), Scr::How => how(a), Scr::Level => level(a), Scr::Pause => pause(a), Scr::Revive => revive(a), Scr::Over => over(a),
        Scr::Shop => shop(a), Scr::Ach => ach(a), Scr::Set => settings(a), Scr::Quest => quests(a), Scr::Best => best(a), Scr::End => end(a), Scr::None => {}
    }
    a.ui.alpha = 1.;
}

/// Живой цветной фон меню: бирюза сверху, фиолет снизу, плывущие пятна света, лучи и искорки.
/// light — поверх забега (выбор улучшения, пауза): прозрачнее, чтобы был виден мир.
fn menu_backdrop(gx: &mut Gfx, tm: f32, al: f32, light: bool) {
    let (w, h, p) = (gx.w, gx.h, gx.px); let k = if light { 0.82 } else { 1. } * al;
    let cs = [Color::new(0.02, 0.20, 0.30, 0.80 * k), Color::new(0.03, 0.09, 0.24, 0.82 * k), Color::new(0.16, 0.05, 0.26, 0.86 * k)];
    gx.set_add(false);
    for (i, y0) in [0., 0.5].iter().enumerate() { let (a, b) = (cs[i], cs[i + 1]); let (ya, yb) = (h * y0 * p, h * (y0 + 0.5) * p);
        draw_mesh(&Mesh { vertices: vec![Vertex::new(0., ya, 0., 0., 0., a), Vertex::new(w * p, ya, 0., 0., 0., a), Vertex::new(w * p, yb, 0., 0., 0., b), Vertex::new(0., yb, 0., 0., 0., b)], indices: vec![0, 1, 2, 0, 2, 3], texture: None }); }
    // пятна цветного света
    gx.glow_scr(true, c::CYAN, (w * 0.25 + (tm * 0.13).sin() * w * 0.18) * p, (h * 0.12 + (tm * 0.09).cos() * 50.) * p, w.max(h) * 0.55 * p, 0.30 * al);
    gx.glow_scr(true, c::AMETH, (w * 0.8 + (tm * 0.11 + 2.).sin() * w * 0.15) * p, (h * 0.85 + (tm * 0.07).sin() * 60.) * p, w.max(h) * 0.5 * p, 0.26 * al);
    gx.glow_scr(true, c::CORAL, (w * 0.15 + (tm * 0.08 + 4.).sin() * w * 0.1) * p, (h * 0.62) * p, w * 0.6 * p, 0.12 * al);
    if light { return; }
    // лучи сверху
    gx.set_add(true);
    for i in 0..5 { let fi = i as f32; let x = w * (0.1 + fi * 0.22) + (tm * 0.15 + fi * 1.3).sin() * 26.; let wd = 30. + (i * 17 % 5) as f32 * 9.;
        let a0 = (0.05 + 0.035 * (tm * 0.5 + fi * 2.1).sin()).max(0.) * al; let c0 = Color::new(0.6, 0.95, 1., a0); let c1 = Color::new(0.6, 0.95, 1., 0.);
        let _ = c1; soft_ray(x * p, (x + wd) * p, 0., (x - 140.) * p, (x + wd - 140.) * p, h * 0.75 * p, Color::new(c0.r, c0.g, c0.b, c0.a * 1.6)); }
    // искорки-планктон
    for i in 0..28 { let fi = i as f32; let sp = 10. + (i * 7 % 5) as f32 * 6.; let y = h + 10. - ((tm * sp + fi * 131.) % (h + 20.)); let x = ((fi * 0.618 + 0.21) % 1.) * w + (tm * 0.7 + fi).sin() * 12.;
        gx.glow_scr(false, [c::ICE, c::JELLY, c::GOLD, c::EMER][i % 4], x * p, y * p, (2.5 + (i % 3) as f32) * p, (0.5 + 0.3 * (tm * 2. + fi).sin()) * al); }
}

/// Колонка кнопок шириной до 320
fn col(a: &App) -> (f32, f32) { let w = (a.gx.w - 32. - a.safe[2] - a.safe[3]).min(320.); ((a.gx.w - w) / 2., w) }
fn top(a: &App) -> f32 { a.safe[0] + if a.gx.h < 460. { 8. } else { 18. } }
fn bottom(a: &App) -> f32 { a.gx.h - a.safe[1] - if a.gx.h < 460. { 8. } else { 18. } }
fn small(a: &App) -> bool { a.gx.h < 640. }

fn logo(gx: &mut Gfx, cx: f32, y: f32, k: f32, al: f32, tm: f32) {
    let fl = (tm * std::f32::consts::FRAC_PI_2).sin() * -4. - 4.; let y = y + fl; let p = gx.px;
    let (s1, s2) = (64. * k, 52. * k);
    for (s, txt, y0, glow, col) in [(s1, t("logo1"), y + s1 * 0.46, c::CYAN, WHITE), (s2, t("logo2"), y + s1 * 0.92 + s2 * 0.46, c::JELLY, hex(0xffe9ff))] {
        let w = gx.text_w(&txt, s, 2) + txt.chars().count() as f32 * (if glow == c::CYAN { 6. } else { 9. }) * k;
        gx.glow_scr(true, glow, cx * p, y0 * p, w * 0.75 * p, 0.55 * al);
        let tg = gx.glow[glow as usize].clone(); gx.set_add(true);
        draw_texture_ex(&tg, (cx - w * 0.6) * p, (y0 - s * 0.7) * p, Color::new(1., 1., 1., 0.45 * al), DrawTextureParams { dest_size: Some(vec2(w * 1.2 * p, s * 1.4 * p)), ..Default::default() });
        spaced(gx, &txt, cx, y0, s, if glow == c::CYAN { 6. } else { 9. } * k, col, al, glow);
    }
}

/// Сцена главного экрана: свет с поверхности, веер лучей, пузырьки и плывущая искра со шлейфом
fn title_scene(gx: &mut Gfx, tm: f32, w: f32, h: f32, hero_c: (f32, f32), hero_r: (f32, f32), skin: &str, pal_i: u8, al: f32) {
    let p = gx.px; gx.set_add(true);
    // тёплые и цветные пятна света — сцена живая, а не тёмная
    gx.glow_scr(true, c::AMETH, (w * 0.85 + (tm * 0.11).sin() * w * 0.1) * p, h * 0.7 * p, w.max(h) * 0.45 * p, 0.28 * al);
    gx.glow_scr(true, c::CORAL, (w * 0.1 + (tm * 0.09 + 1.).sin() * w * 0.1) * p, h * 0.55 * p, w * 0.7 * p, 0.16 * al);
    gx.glow_scr(true, c::CYAN, w * 0.5 * p, h * 0.32 * p, w * 0.9 * p, 0.22 * al);
    gx.set_add(true);
    // свет сверху
    let top = Color::new(0.35, 0.85, 1., 0.30 * al); let bot = Color::new(0.35, 0.85, 1., 0.);
    draw_mesh(&Mesh { vertices: vec![Vertex::new(0., 0., 0., 0., 0., top), Vertex::new(w * p, 0., 0., 0., 0., top), Vertex::new(w * p, h * 0.5 * p, 0., 0., 0., bot), Vertex::new(0., h * 0.5 * p, 0., 0., 0., bot)], indices: vec![0, 1, 2, 0, 2, 3], texture: None });
    // «северное сияние» — цветные волнистые ленты в верхней половине
    for (bi, (cr, cg, cb)) in [(0.25f32, 0.95f32, 1f32), (1., 0.35, 0.85), (1., 0.8, 0.3)].iter().enumerate() {
        let n = 40; let base = h * (0.12 + bi as f32 * 0.1); let amp = 28. + bi as f32 * 12.; let thick = 46. + bi as f32 * 10.; let mut v = vec![]; let mut idx = vec![];
        for q in 0..=n { let x = q as f32 / n as f32 * w; let y = base + (x * 0.012 + tm * (0.35 + bi as f32 * 0.12) + bi as f32 * 2.).sin() * amp + (x * 0.031 - tm * 0.5).sin() * 9.;
            let a = 0.22 * al * (0.6 + 0.4 * (x * 0.02 + tm * 0.8 + bi as f32).sin());
            v.push(Vertex::new(x * p, (y - thick) * p, 0., 0., 0., Color::new(*cr, *cg, *cb, 0.))); v.push(Vertex::new(x * p, y * p, 0., 0., 0., Color::new(*cr, *cg, *cb, a))); v.push(Vertex::new(x * p, (y + thick * 0.6) * p, 0., 0., 0., Color::new(*cr, *cg, *cb, 0.)));
            if q > 0 { let b0 = ((q - 1) * 3) as u16; let b1 = (q * 3) as u16; idx.extend_from_slice(&[b0, b1, b0 + 1, b1, b1 + 1, b0 + 1, b0 + 1, b1 + 1, b0 + 2, b1 + 1, b1 + 2, b0 + 2]); } }
        draw_mesh(&Mesh { vertices: v, indices: idx, texture: None }); }
    // веер лучей от поверхности
    for i in 0..7 { let a = -0.55 + i as f32 * 0.18 + (tm * 0.21 + i as f32 * 1.7).sin() * 0.05; let len = h * 1.05; let wd = 0.035 + 0.02 * ((i * 37) % 5) as f32 / 5.;
        let (ox, oy) = (w * 0.5 + (tm * 0.13).sin() * 30., -h * 0.08); let k = 0.07 + 0.05 * (tm * 0.7 + i as f32 * 2.3).sin().max(0.);
        let c0 = Color::new(0.6, 0.95, 1., k * al); let c1 = Color::new(0.6, 0.95, 1., 0.);
        let (s0, s1) = ((a - wd).sin(), (a + wd).sin()); let (q0, q1) = ((a - wd).cos(), (a + wd).cos());
        let _ = c1; soft_ray((ox - 6.) * p, (ox + 6.) * p, oy * p, (ox + s0 * len) * p, (ox + s1 * len) * p, (oy + q0 * len) * p, c0); }
    // пузырьки
    for i in 0..34 { let fi = i as f32; let sp = 18. + (i * 13 % 7) as f32 * 7.; let y = h + 20. - ((tm * sp + fi * 97.) % (h + 40.)); let x = ((fi * 0.618 + 0.13) % 1.) * w + (tm * 0.9 + fi).sin() * 10.;
        let r = 1.5 + (i % 4) as f32 * 1.1; gx.ring(x, y, r, 1., Color::new(0.75, 0.95, 1., 0.45 * al)); gx.glow_scr(false, [c::ICE, c::JELLY, c::GOLD, c::EMER][i % 4], (x - r * 0.4) * p, (y - r * 0.4) * p, r * 1.2 * p, 0.5 * al); }
    // искра-герой плывёт восьмёркой, за ней шлейф
    let pos = |t: f32| (hero_c.0 + (t * 0.42).sin() * hero_r.0, hero_c.1 + (t * 0.84).sin() * hero_r.1);
    for k in (1..16).rev() { let (x, y) = pos(tm - k as f32 * 0.07); gx.glow_scr(true, pal_i, x * p, y * p, (26. - k as f32 * 1.3) * p, (1. - k as f32 / 16.) * 0.5 * al); }
    let (x, y) = pos(tm); let (x2, y2) = pos(tm + 0.02); let ang = (y2 - y).atan2(x2 - x);
    gx.glow_scr(true, pal_i, x * p, y * p, 70. * p, 0.55 * al); gx.glow_scr(false, c::WHITE, x * p, y * p, 14. * p, 0.8 * al);
    let key = format!("pl_{skin}"); let ph = gx.spr_anim(&key).map(|a| tm * a.freq() * 1.6 * std::f32::consts::TAU).unwrap_or(0.);
    gx.spr_screen(&key, x * p, y * p, ang, 2.5 * p, al, false, ph, true);
}
/// Блик, пробегающий по логотипу
fn logo_shine(gx: &mut Gfx, cx: f32, y: f32, k: f32, tm: f32, al: f32) {
    let ph = (tm % 4.5) / 1.4; if ph > 1. { return; } let p = gx.px; let w = 300. * k; let x = cx - w * 0.6 + ph * w * 1.2;
    let tg = gx.soft[c::WHITE as usize].clone(); gx.set_add(true);
    draw_texture_ex(&tg, (x - 30. * k) * p, (y - 10.) * p, Color::new(1., 1., 1., 0.35 * al * (ph * std::f32::consts::PI).sin()), DrawTextureParams { dest_size: Some(vec2(60. * k * p, 140. * k * p)), rotation: 0.35, ..Default::default() });
    for i in 0..10 { let fi = i as f32; let a = tm * 0.6 + fi * 0.628; let rr = 130. * k + (tm * 1.3 + fi).sin() * 12.; let (sx, sy) = (cx + a.cos() * rr * 1.1, y + 58. * k + a.sin() * rr * 0.45);
        gx.glow_scr(false, if i % 2 == 0 { c::CYAN } else { c::JELLY }, sx * p, sy * p, (3. + (i % 3) as f32) * p, (0.5 + 0.5 * (tm * 3. + fi).sin()) * al); }
}

/// Праздничная сцена финала: вращающиеся золотые лучи, падающие искры, «Заря» кружит над итогами
pub fn end_scene(gx: &mut Gfx, tm: f32, w: f32, h: f32, cy: f32, al: f32) {
    let p = gx.px; gx.set_add(true); let (cx, cy) = (w / 2., cy);
    for i in 0..12 { let a = tm * 0.15 + i as f32 * std::f32::consts::TAU / 12.; let wd = 0.09; let len = (w * w + h * h).sqrt();
        let c0 = Color::new(1., 0.85, 0.45, 0.16 * al); let c1 = Color::new(1., 0.85, 0.45, 0.);
        draw_mesh(&Mesh { vertices: vec![Vertex::new(cx * p, cy * p, 0., 0., 0., c0), Vertex::new((cx + (a - wd).cos() * len) * p, (cy + (a - wd).sin() * len) * p, 0., 0., 0., c1), Vertex::new((cx + (a + wd).cos() * len) * p, (cy + (a + wd).sin() * len) * p, 0., 0., 0., c1)], indices: vec![0, 1, 2], texture: None }); }
    gx.glow_scr(true, c::GOLD, cx * p, cy * p, w.min(h) * 0.5 * p, 0.45 * al);
    for i in 0..60 { let fi = i as f32; let sp = 30. + (i * 17 % 9) as f32 * 9.; let y = ((tm * sp + fi * 71.) % (h + 40.)) - 20.; let x = ((fi * 0.618 + 0.31) % 1.) * w + (tm * 1.3 + fi).sin() * 18.;
        gx.glow_scr(false, [c::GOLD, c::DAWN, c::WHITE, c::CORAL, c::ICE][i % 5], x * p, y * p, (2.5 + (i % 3) as f32 * 1.5) * p, (0.55 + 0.45 * (tm * 4. + fi).sin()) * al); }
    let (hx, hy) = (cx + (tm * 0.9).cos() * 70., cy - 8. + (tm * 0.9).sin() * 18.); let ang = (tm * 0.9).cos().atan2(-(tm * 0.9).sin() * 3.9) + std::f32::consts::PI;
    for k in (1..14).rev() { let t2 = tm - k as f32 * 0.06; gx.glow_scr(true, c::DAWN, (cx + (t2 * 0.9).cos() * 70.) * p, (cy - 8. + (t2 * 0.9).sin() * 18.) * p, (22. - k as f32 * 1.2) * p, (1. - k as f32 / 14.) * 0.5 * al); }
    gx.glow_scr(true, c::DAWN, hx * p, hy * p, 60. * p, 0.6 * al);
    let ph = gx.spr_anim("pl_dawn").map(|a| tm * a.freq() * 1.5 * std::f32::consts::TAU).unwrap_or(0.); let _ = ang;
    let dir = -(tm * 0.9).sin(); gx.spr_screen("pl_dawn", hx * p, hy * p, if dir < 0. { std::f32::consts::PI } else { 0. }, 2.2 * p, al, false, ph, true);
}
/// Текст с разрядкой (letter-spacing) и неоновым ореолом
fn spaced(gx: &mut Gfx, s: &str, cx: f32, cy: f32, size: f32, sp: f32, col: Color, al: f32, glow: u8) {
    let chars: Vec<String> = s.chars().map(|c| c.to_string()).collect(); let ws: Vec<f32> = chars.iter().map(|c| gx.text_w(c, size, 2)).collect();
    let total: f32 = ws.iter().sum::<f32>() + sp * (chars.len() as f32 - 1.); let mut x = cx - total / 2.; let gc = pal(glow);
    for (ch, w) in chars.iter().zip(ws.iter()) {
        for (dx, dy) in [(-2., 0.), (2., 0.), (0., -2.), (0., 2.)] { gx.text_add(ch, x + dx, cy + dy, size, Color::new(gc.r, gc.g, gc.b, 0.3 * al), 0, 2); }
        gx.text(ch, x, cy, size, with_alpha(col, al), 0, 2); x += w + sp;
    }
}

/// Главный экран (вертикальный), 3.7: плашки рекорда и жемчуга, арт Люмена, логотип, «Играть», три плитки, нижний ряд
fn title_portrait(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let tm = a.g.t; let tp = top(a); let sm = small(a); let p = a.gx.px;
    let (bx, bw) = col(a); let cx = w / 2.;
    // фон: свет, лучи, пузырьки (герой — на арте, поэтому его искру уводим за экран)
    { let skin = a.g.s.skin.clone(); title_scene(&mut a.gx, tm, w, h, (-400., -400.), (0., 0.), &skin, c::CYAN, al); }
    // ---- верхние плашки ----
    let s = &a.g.s; let rec = format!("★ {}  ·  {} {}", i18n::fmt_num(s.best as i64), s.best_depth, t("m")); let pearls_s = i18n::fmt_num(s.pearls as i64);
    { let gx = &mut a.gx; let y0 = tp; let ph = 30.;
      let rw = gx.text_w(&rec, 13., 1) + 24.; ui::rrect_grad(gx, bx, y0, rw, ph, 15., Color::new(0.02, 0.08, 0.16, 0.55 * al), Color::new(0.02, 0.05, 0.12, 0.45 * al));
      gx.rrect_line(bx, y0, rw, ph, 15., 1., Color::new(1., 0.84, 0.4, 0.45 * al)); gx.text(&rec, bx + 12., y0 + ph / 2., 13., with_alpha(hex(0xffe08a), al), 0, 1);
      let pw = gx.text_w(&pearls_s, 15., 2) + 44.; let px0 = bx + bw - pw; ui::rrect_grad(gx, px0, y0, pw, ph, 15., Color::new(0.10, 0.04, 0.16, 0.6 * al), Color::new(0.06, 0.02, 0.12, 0.5 * al));
      gx.rrect_line(px0, y0, pw, ph, 15., 1., Color::new(1., 0.6, 0.95, 0.5 * al)); pearl(gx, px0 + 16., y0 + ph / 2., 6.5, al); gx.text(&pearls_s, px0 + 30., y0 + ph / 2., 15., Color::new(1., 0.93, 1., al), 0, 2); }
    // ---- нижний блок (снизу вверх) ----
    let gift_left = GIFT_MAX.saturating_sub(a.g.s.daily.gift); let gift = gift_left > 0 && a.ad_ready();
    let (bh_play, tile_h, row_h) = if sm { (58., 66., 46.) } else { (68., 78., 52.) }; let gap = if sm { 8. } else { 10. };
    let block = bh_play + gap + tile_h + gap + row_h + gap + 28.; let yb = bottom(a) - block;
    // ---- арт и логотип в свободной середине ----
    let top_free = tp + 40.; let logo_k = if sm { 0.62 } else if h > 720. { 0.86 } else { 0.72 }; let logo_h = 118. * logo_k;
    let avail = (yb - 12.) - top_free; let art = (avail - logo_h - 6.).min(bw * 1.05).max(90.);
    { let gx = &mut a.gx; let ay = top_free + (avail - logo_h - art) * 0.5; let bob = (tm * 1.1).sin() * 5.; let pul = 1. + (tm * 0.9).sin() * 0.012;
      gx.glow_scr(true, c::CYAN, cx * p, (ay + art / 2.) * p, art * 0.75 * p, 0.45 * al); gx.glow_scr(true, c::GOLD, cx * p, (ay + art * 0.55) * p, art * 0.3 * p, 0.25 * al);
      if let Some(t_) = gx.keyart.clone() { let s_ = art * pul; gx.tex_ui(&t_, cx - s_ / 2., ay + bob + (art - s_) / 2., s_, s_, Color::new(1., 1., 1., al)); }
      let ly = ay + art - logo_h * 0.18; logo(gx, cx, ly, logo_k, al, tm); logo_shine(gx, cx, ly, logo_k, tm, al); }
    // ---- кнопки ----
    let mut y = yb;
    // «Играть» и рядом — забег с реликвией за рекламу (до 5 в день)
    let boost_left = BOOST_MAX.saturating_sub(a.g.s.daily.boost); let boost = boost_left > 0 && a.g.s.runs >= 1 && a.ad_ready();
    let pw = if boost { bw * 0.6 } else { bw };
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, pw, bh_play), &t("play"), St::Cyan, if sm { 24. } else { 28. }, true) { a.click(); a.g.s.seen_how = true; a.start_run(RunMode::Normal); return; }
    if boost { let l = format!("▶ {}\n{} ({})", if i18n::is_en() { "Play" } else { "Играть" }, if i18n::is_en() { "with a relic" } else { "с реликвией" }, boost_left);
        if a.ui.btn(&mut a.gx, Rect::new(bx + pw + gap, y, bw - pw - gap, bh_play), &l, St::Gold, 17., true) { a.click(); a.ad_show("boost", AdCb::Boost); return; } }
    y += bh_play + gap;
    let muts = crate::flow::daily_muts(); let mn: Vec<String> = muts.iter().map(|&i| i18n::mutator(data::MUTS[i]).0).collect(); let d = a.g.s.daily.clone();
    let qd = d.quests.iter().filter(|q| q.done).count(); let qr = a.g.quests_ready();
    let en = i18n::is_en(); let n = if gift { 3. } else { 2. }; let tw_ = (bw - gap * (n - 1.)) / n;
    let daily_l = format!("☀ {}{}\n{}", if en { "Daily" } else { "Испытание" }, if d.ch_done { " ✓" } else { "" }, mn.join(" + "));
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, tw_, tile_h), &daily_l, St::Gold, 15., true) { a.click(); a.start_run(RunMode::Daily); return; }
    let q_l = format!("{}\n{}/{}{}", t("quests"), qd, d.quests.len(), if qr > 0 { format!(" · {}", t("claim")) } else { String::new() });
    if a.ui.btn(&mut a.gx, Rect::new(bx + tw_ + gap, y, tw_, tile_h), &q_l, if qr > 0 { St::Gold } else { St::Cyan }, 15., true) { a.click(); a.ui.scroll_reset(3); a.show(Scr::Quest); }
    if gift { let g_l = format!("▶ +{}\n{} ({})", GIFT_R, if en { "for an ad" } else { "за рекламу" }, gift_left);
        if a.ui.btn(&mut a.gx, Rect::new(bx + (tw_ + gap) * 2., y, tw_, tile_h), &g_l, St::Pink, 15., true) { a.click(); a.ad_show("gift", AdCb::Gift); } }
    y += tile_h + gap;
    let rw = (bw - gap * 2.) / 3.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, rw, row_h), &t("shop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Title; a.ui.scroll_reset(1); a.show(Scr::Shop); }
    if a.ui.btn(&mut a.gx, Rect::new(bx + rw + gap, y, rw, row_h), &t("ach"), St::Gold, 15., true) { a.click(); a.ui.scroll_reset(2); a.show(Scr::Ach); }
    if a.ui.btn(&mut a.gx, Rect::new(bx + (rw + gap) * 2., y, rw, row_h), &t("settings"), St::Cyan, 15., true) { a.click(); a.back_to = Scr::Title; a.show(Scr::Set); }
    y += row_h + gap + 12.;
    let mut links: Vec<(String, u8)> = vec![]; if a.g.s.wins > 0 { links.push((if a.g.s.set.hard { t("hardOn") } else { t("hardOff") }, 0)); }
    links.push((t("howLink"), 1)); links.push((t("bestL"), 2));
    let ws: Vec<f32> = links.iter().map(|l| a.gx.text_w(&l.0, 12., 0) + 20.).collect(); let tot: f32 = ws.iter().sum(); let mut x = cx - tot / 2.;
    for (i, (l, id)) in links.iter().enumerate() { let lx = x + ws[i] / 2.; x += ws[i];
        if a.ui.link(&mut a.gx, lx, y, l, 12.) { a.click(); match id { 0 => { a.g.s.set.hard = !a.g.s.set.hard; a.g.dirty = true; } 1 => a.show(Scr::How), _ => { a.ui.scroll_reset(4); a.show(Scr::Best); } } } }
}

fn title(a: &mut App) {
    if !a.landscape() { title_portrait(a); return; }
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let tm = a.g.t; let land = a.landscape(); let (_, cw) = col(a);
    let g = &a.g; let s = &g.s;
    let stats1 = format!("{}: {} · {}: {} {}", t("record"), i18n::fmt_num(s.best as i64), t("depthW"), s.best_depth, t("m"));
    let ch = CHARS.iter().position(|c| c.id == s.ch).unwrap_or(0);
    let stats2 = format!("{} {} · {}: {}", s.pearls, t("pearlsW"), t("spark"), i18n::chr(CHARS[ch].id).0);
    let stats3 = if s.wins > 0 { format!("{}{}", t("winsLine"), s.wins) } else { String::new() };
    let gift_left = GIFT_MAX.saturating_sub(s.daily.gift); let gift = gift_left > 0 && a.ad_ready();
    let qd = s.daily.quests.iter().filter(|q| q.done).count(); let qr = g.quests_ready();
    // высота блока кнопок
    let (bh_play, bh_daily, bh_q, bh_gift, bh_row) = if sm { (56., 48., 44., 40., 46.) } else { (68., 50., 46., 42., 54.) };
    let links_h = 30.; let gap = 8.;
    let stats_h = if stats3.is_empty() { 42. } else { 62. };
    let block = stats_h + bh_play + bh_daily + bh_q + if gift { bh_gift + gap } else { 0. } + bh_row + links_h + gap * 5.;
    let (bx, bw, mut y);
    if land { bw = (w * 0.46).min(360.); bx = w * 0.52 + (w * 0.48 - bw) / 2. - a.safe[3] / 2.; y = ((h - block) / 2.).max(tp); }
    else { bw = cw; bx = (w - bw) / 2.; y = bottom(a) - block; }
    // живая сцена: свет, лучи, пузырьки, искра
    { let skin = a.g.s.skin.clone(); let pi = SKINS.iter().find(|k| k.id == skin).map(|k| k.pal).unwrap_or(c::CYAN);
        let (hc, hr) = if land { ((w * 0.26, h * 0.78), (w * 0.17, 26.)) } else { { let he = tp + h * 0.05 + 210.; ((w * 0.5, ((he + y) / 2.).max(he - 20.)), (w * 0.3, ((y - he) * 0.25).clamp(8., 40.))) } };
        title_scene(&mut a.gx, tm, w, h, hc, hr, &skin, pi, al);
        // затемнение под кнопками — текст читается на любом фоне
        let p = a.gx.px; a.gx.set_add(false); let c0 = Color::new(0., 0.02, 0.06, 0.); let c1 = Color::new(0.03, 0.02, 0.10, 0.42 * al);
        let (x0, x1, y0) = if land { (w * 0.5, w, 0.) } else { (0., w, y - 30.) };
        draw_mesh(&Mesh { vertices: vec![Vertex::new(x0 * p, y0 * p, 0., 0., 0., if land { c1 } else { c0 }), Vertex::new(x1 * p, y0 * p, 0., 0., 0., if land { c1 } else { c0 }), Vertex::new(x1 * p, h * p, 0., 0., 0., c1), Vertex::new(x0 * p, h * p, 0., 0., 0., c1)], indices: vec![0, 1, 2, 0, 2, 3], texture: None }); }
    // логотип и история
    { let gx = &mut a.gx;
        if land { let k = (h / 420.).clamp(0.55, 0.85); let lx = w * 0.26 + a.safe[2] / 2.; let ly = (h * 0.5 - 100. * k).max(tp); logo(gx, lx, ly, k, al, tm); logo_shine(gx, lx, ly, k, tm, al);
            if h > 380. { gx.text_wrap(&t("hook"), lx, ly + 116. * k + 26., (w * 0.44).min(360.), 13., 18., Color::new(1., 1., 1., 0.88 * al), 1, 0); } }
        else { let k = if w < 350. { 0.84 } else if sm { 0.8 } else { 1. }; let ly = tp + h * if sm { 0.02 } else { 0.05 }; logo(gx, w / 2., ly, k, al, tm); logo_shine(gx, w / 2., ly, k, tm, al);
            let hy = ly + 116. * k + 18.; let lines = gx.wrap(&t("hook"), 330f32.min(w - 32.), 15., 0); let hh = lines.len() as f32 * 21.75;
            if hy + hh + 10. < y { for (i, l) in lines.iter().enumerate() { gx.text_sh(l, w / 2., hy + 10. + i as f32 * 21.75, if sm { 13.5 } else { 15. }, Color::new(1., 1., 1., 0.88 * al), 1, 0); } } }
    }
    let cx = bx + bw / 2.;
    { let gx = &mut a.gx; let gold = pal(c::GOLD);
        let parts = [(stats1, gold), (stats2, Color::new(1., 1., 1., 0.85)), (stats3, gold)];
        for (i, (sline, col)) in parts.iter().enumerate() { if sline.is_empty() { continue; } let yy = y + 10. + i as f32 * 20.;
            if i == 1 { let tw = gx.text_w(sline, 13., 0); pearl(gx, cx - tw / 2. - 9., yy, 5., al); }
            gx.text(sline, cx, yy, 13., with_alpha(*col, 0.92 * al), 1, if i == 1 { 0 } else { 1 }); } }
    y += stats_h + gap;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh_play), &t("play"), St::Cyan, if sm { 22. } else { 26. }, true) { a.click(); a.g.s.seen_how = true; a.start_run(RunMode::Normal); return; }
    y += bh_play + gap;
    let muts = crate::flow::daily_muts(); let mn: Vec<String> = muts.iter().map(|&i| i18n::mutator(data::MUTS[i]).0).collect(); let d = &a.g.s.daily;
    let dl = format!("☀ {}{}\n{}{}", t("dailyB"), if d.ch_done { " ✓" } else { "" }, mn.join(" + "), if d.ch_best > 0 { format!(" · {} {} {}", t("best"), d.ch_best, t("m")) } else { format!(" · {}", t("dailyX2")) });
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh_daily), &dl, St::Gold, 15., true) { a.click(); a.start_run(RunMode::Daily); return; }
    y += bh_daily + gap;
    let ql = format!("{} · {}/{}{}", t("quests"), qd, a.g.s.daily.quests.len(), if qr > 0 { format!("  ● {}", t("claim")) } else { String::new() });
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh_q), &ql, if qr > 0 { St::Gold } else { St::Cyan }, 16., true) { a.click(); a.ui.scroll_reset(3); a.show(Scr::Quest); }
    y += bh_q + gap;
    if gift { if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh_gift), &tf("adGift", &[&GIFT_R.to_string(), &gift_left.to_string()]), St::Gold, 14., true) { a.click(); a.ad_show("gift", AdCb::Gift); } y += bh_gift + gap; }
    let rw = (bw - 16.) / 3.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, rw, bh_row), &t("shop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Title; a.ui.scroll_reset(1); a.show(Scr::Shop); }
    if a.ui.btn(&mut a.gx, Rect::new(bx + rw + 8., y, rw, bh_row), &t("ach"), St::Gold, 15., true) { a.click(); a.ui.scroll_reset(2); a.show(Scr::Ach); }
    if a.ui.btn(&mut a.gx, Rect::new(bx + (rw + 8.) * 2., y, rw, bh_row), &t("settings"), St::Cyan, 15., true) { a.click(); a.back_to = Scr::Title; a.show(Scr::Set); }
    y += bh_row + gap + 10.;
    let mut links: Vec<(String, u8)> = vec![]; if a.g.s.wins > 0 { links.push((if a.g.s.set.hard { t("hardOn") } else { t("hardOff") }, 0)); }
    links.push((t("howLink"), 1)); links.push((t("bestL"), 2));
    let ws: Vec<f32> = links.iter().map(|l| a.gx.text_w(&l.0, 12., 0) + 20.).collect(); let tot: f32 = ws.iter().sum(); let mut x = cx - tot / 2.;
    for (i, (l, id)) in links.iter().enumerate() { let lx = x + ws[i] / 2.; x += ws[i];
        if a.ui.link(&mut a.gx, lx, y, l, 12.) { a.click(); match id { 0 => { a.g.s.set.hard = !a.g.s.set.hard; a.g.dirty = true; } 1 => a.show(Scr::How), _ => { a.ui.scroll_reset(4); a.show(Scr::Best); } } } }
}

fn how(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, _h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let land = a.landscape();
    let mut y = tp + 30.; h2(&mut a.gx, &t("howTitle"), w / 2., y, 28., al); y += 36.;
    let tw = (w - 40.).min(400.); let x0 = (w - tw) / 2.;
    let paras: Vec<String> = (1..=5).map(|i| t(&format!("how{i}"))).collect();
    if land { let cw2 = ((w - 60.) / 2.).min(380.); let xs = [w / 2. - cw2 - 10., w / 2. + 10.]; let mut ys = [y, y];
        for (i, p) in paras.iter().enumerate() { let c_ = if i < 3 { 0 } else { 1 }; let gx = &mut a.gx; num(gx, xs[c_], ys[c_], i + 1, al);
            ys[c_] += gx.text_wrap(p, xs[c_] + 34., ys[c_] + 10., cw2 - 34., 13., 17., Color::new(1., 1., 1., al), 0, 0) + 6.; }
        y = ys[0].max(ys[1]); }
    else { for (i, p) in paras.iter().enumerate() { let gx = &mut a.gx; num(gx, x0, y, i + 1, al); y += gx.text_wrap(p, x0 + 34., y + 10., tw - 34., if sm { 13.5 } else { 15. }, if sm { 18. } else { 21. }, Color::new(1., 1., 1., al), 0, 0) + 11.; } }
    let (bx, bw) = col(a); let by = (y + 10.).min(bottom(a) - 68.);
    if a.ui.btn(&mut a.gx, Rect::new(bx, by, bw, if sm { 56. } else { 68. }), &t("howOk"), St::Cyan, if sm { 22. } else { 26. }, true) { a.click(); a.g.s.seen_how = true; a.start_run(RunMode::Normal); }
}
fn num(gx: &mut Gfx, x: f32, y: f32, n: usize, al: f32) { let p = gx.px; gx.glow_scr(true, c::CYAN, (x + 12.) * p, (y + 12.) * p, 16. * p, 0.4 * al); gx.ring(x + 12., y + 12., 11., 2., with_alpha(pal(c::CYAN), al)); gx.text(&n.to_string(), x + 12., y + 12., 12., Color::new(1., 1., 1., al), 1, 2); }

// ---------- выбор улучшения ----------
fn level(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let land = a.landscape();
    let n = a.cards.len(); let mut y = if land { tp + 22. } else { 0. };
    // высоты карт
    let cwid = if land { ((w - 40.) / n as f32 - 12.).min(240.) } else { (w - 32.).min(420.) };
    let rm = a.relic_mode;
    let infos: Vec<(String, String, bool, u8, u8, u8)> = a.cards.iter().map(|&i| if rm { let (n, d) = crate::content::relic_txt(i as u8); (n.to_string(), d.to_string(), true, 0, 1, crate::content::RELICS[i].col) } else if i == U_HEAL { ("Чистый свет".to_string(), "Восстановить 50% здоровья и +1000 очков".to_string(), false, 0, 1, c::EMER) }
        else { let (nm, d) = i18n::upg(UPG[i].id); (nm, d, UPG[i].syn.is_some(), a.g.p.up[i], UPG[i].max, UPG[i].col) }).collect();
    let heal_en = i18n::is_en();
    let hs: Vec<f32> = infos.iter().map(|inf| { let dw = if land { cwid - 24. } else { cwid - 28. - 68. }; let dh = a.gx.wrap(&inf.1, dw, 13.5, 0).len() as f32 * 17.;
        if land { 12. + 56. + 8. + if inf.2 && !rm { 18. } else { 0. } + 24. + dh + 12. } else { (24. + if inf.2 && !rm { 18. } else { 0. } + 22. + dh).max(80.) } }).collect();
    let gap = if sm { 9. } else { 12. };
    let total: f32 = if land { hs.iter().cloned().fold(0., f32::max) } else { hs.iter().sum::<f32>() + gap * (n as f32 - 1.) };
    let head = 28. + 14. + 24. + 14.; let foot = 12. + 44. + 50.;
    if !land { y = ((h - head - total - foot) / 2.).max(tp) + 14.; }
    if rm { ui::h2c(&mut a.gx, if i18n::is_en() { "RELIC" } else { "РЕЛИКВИЯ" }, w / 2., y + 14., if land { 21. } else { 30. }, al, c::GOLD, hex(0xffe9a8)); }
    else { h2(&mut a.gx, &format!("{}{}", t("lvlUp"), a.g.p.level), w / 2., y + 14., if land { 21. } else { 28. }, al); }
    y += if land { 34. } else { 42. };
    let sub = if rm { if i18n::is_en() { "A powerful artifact for the whole run — pick one".to_string() } else { "Сильный предмет на весь забег — выбери один".to_string() } }
        else if a.g.level_pending > 0 { tf("lvSubMore", &[&a.g.level_pending.to_string()]) } else { t("lvSub") };
    a.gx.text(&sub, w / 2., y, 14., Color::new(1., 1., 1., 0.75 * al), 1, 0); y += 24.;
    let x0 = if land { (w - (cwid + 12.) * n as f32 + 12.) / 2. } else { (w - cwid) / 2. };
    let mut chosen = a.ui.key_num.filter(|&k| k < n);
    for (k, inf) in infos.iter().enumerate() {
        let appear = ((a.cards_t - 0.06 - k as f32 * 0.09) / 0.32).clamp(0., 1.); let e = 1. - (1. - appear).powi(3); let oy = (1. - e) * 24.;
        let (cx, cy, ch) = if land { (x0 + k as f32 * (cwid + 12.), y, total) } else { let yy = y + hs[..k].iter().sum::<f32>() + gap * k as f32; (x0, yy, hs[k]) };
        let r = Rect::new(cx, cy + oy, cwid, ch); let ca = appear * al; let held = a.ui.held(r) && a.ui.lock <= 0.; let sc = if held { 0.96 } else { 1. };
        let r2 = Rect::new(r.x + r.w * (1. - sc) / 2., r.y + r.h * (1. - sc) / 2., r.w * sc, r.h * sc);
        let gx = &mut a.gx; let (syn, lvl, max, colr) = (inf.2, inf.3, inf.4, inf.5);
        let ac = pal(colr);
        let (c1, c2, bord) = if syn { (Color::new(110. / 255., 80. / 255., 10. / 255., 0.9), Color::new(40. / 255., 15. / 255., 50. / 255., 0.92), pal(c::GOLD)) }
            else { (Color::new(ac.r * 0.34 + 0.04, ac.g * 0.34 + 0.06, ac.b * 0.34 + 0.12, 0.88), Color::new(ac.r * 0.1 + 0.02, ac.g * 0.1 + 0.03, ac.b * 0.1 + 0.09, 0.92), Color::new(ac.r, ac.g, ac.b, 0.7)) };
        for q in (1..=3).rev() { let o = q as f32 * 3.; gx.rrect_line(r2.x - o, r2.y - o, r2.w + o * 2., r2.h + o * 2., 18. + o, 3., with_alpha(bord, ca * if syn { 0.2 } else { 0.1 } / q as f32)); }
        ui::rrect_grad(gx, r2.x, r2.y, r2.w, r2.h, 18., with_alpha(c1, ca), with_alpha(c2, ca)); gx.rrect_line(r2.x, r2.y, r2.w, r2.h, 18., 2., with_alpha(bord, ca));
        let icon_key = if rm { crate::content::RELICS[a.cards[k]].icon.to_string() } else if a.cards[k] == U_HEAL { "heal".to_string() } else { UPG[a.cards[k]].id.to_string() };
        let ic = gx.icon.get(&icon_key).cloned();
        let name = if rm { inf.0.clone() } else if a.cards[k] == U_HEAL && heal_en { "Pure Light".to_string() } else { inf.0.clone() };
        let desc = if rm { inf.1.clone() } else if a.cards[k] == U_HEAL && heal_en { "Restore 50% health and +1000 points".to_string() } else { inf.1.clone() };
        if land {
            let mut yy = r2.y + 12.; if let Some(t_) = ic { gx.tex_ui(&t_, r2.x + r2.w / 2. - 28., yy, 56., 56., Color::new(1., 1., 1., ca)); } yy += 64.;
            if syn && !rm { tag(gx, r2.x + r2.w / 2., yy + 6., ca); yy += 18.; }
            gx.text(&name, r2.x + r2.w / 2., yy + 8., 17., Color::new(1., 1., 1., ca), 1, 2); yy += 18.;
            if max > 1 { let pw = max as f32 * 10.; pips(gx, r2.x + r2.w / 2. - pw / 2., yy + 4., lvl + 1, max, ca); } yy += 12.;
            gx.text_wrap(&desc, r2.x + r2.w / 2., yy + 8., r2.w - 24., 13., 17., Color::new(1., 1., 1., 0.85 * ca), 1, 0);
        } else {
            let p = gx.px; gx.glow_scr(true, colr, (r2.x + 14. + 28.) * p, (r2.y + r2.h / 2.) * p, 36. * p, 0.25 * ca);
            if let Some(t_) = ic { gx.tex_ui(&t_, r2.x + 14., r2.y + r2.h / 2. - 28., 56., 56., Color::new(1., 1., 1., ca)); }
            let tx = r2.x + 14. + 56. + 12.; let mut yy = r2.y + 14.;
            if syn && !rm { tag(gx, tx + 34., yy + 6., ca); yy += 18.; }
            let nw = gx.text(&name, tx, yy + 8., 18., Color::new(1., 1., 1., ca), 0, 2);
            if max > 1 { pips(gx, tx + nw + 8., yy + 9., lvl + 1, max, ca); }
            yy += 22.; gx.text_wrap(&desc, tx, yy + 8., r2.w - (tx - r2.x) - 12., 13.5, 17., Color::new(1., 1., 1., 0.85 * ca), 0, 0);
        }
        if appear >= 1. && a.ui.tap(r) { chosen = Some(k); }
    }
    if let Some(k) = chosen { if a.ui.lock <= 0. { a.take_card(k); return; } }
    let by = if land { y + total + 12. } else { y + total + 12. };
    if rm { if !a.relic_rerolled && a.ad_ready() { let by = y + total + 12.; let l = if i18n::is_en() { "▶ Other relics".to_string() } else { "▶ Другие реликвии".to_string() };
            let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(w / 2. - bw / 2., by, bw, 44.), &l, St::Gold, 16., true) { a.click(); a.ad_show("relic", AdCb::RelicReroll); } }
        return; }
    let mut bx_ = w / 2.; let rr = a.g.rerolls; let can_ad = rr == 0 && a.g.ad_rerolls < 2 && a.ad_ready();
    if rr > 0 { let l = tf("reroll2", &[&rr.to_string()]); let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(bx_ - bw / 2., by, bw, 44.), &l, St::Cyan, 16., true) { a.click(); a.g.rerolls -= 1; a.roll_cards(); } bx_ += 0.; }
    else if can_ad { let l = t("adReroll"); let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(bx_ - bw / 2., by, bw, 44.), &l, St::Gold, 16., true) { a.click(); a.ad_show("reroll", AdCb::Reroll); } }
}
fn tag(gx: &mut Gfx, cx: f32, cy: f32, al: f32) { let s = t("synergy"); let w = gx.text_w(&s, 10., 2) + 14.; gx.rrect(cx - w / 2., cy - 8., w, 16., 6., with_alpha(pal(c::GOLD), al)); gx.text(&s, cx, cy, 10., Color::new(32. / 255., 20. / 255., 0., al), 1, 2); }

fn pause(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let w = a.gx.w; let al = a.ui.alpha; let (bx, bw) = col(a);
    let ups: Vec<String> = UPG.iter().enumerate().filter(|(i, _)| a.g.p.up[*i] > 0).map(|(i, u)| { let n = i18n::upg(u.id).0; if u.max > 1 { format!("{n} {}", a.g.p.up[i]) } else { n } }).collect();
    let info = a.g.mode_tf(); let upl = ups.join(" · ");
    let uh = if upl.is_empty() { 0. } else { a.gx.wrap(&upl, w - 40., 13., 0).len() as f32 * 18. + 14. };
    let bh = if sm { 56. } else { 68. }; let total = 36. + 24. + uh + 14. + bh + 8. + 56. + 8. + 56.;
    let mut y = ((a.gx.h - total) / 2.).max(tp);
    h2(&mut a.gx, &t("pause"), w / 2., y + 14., 28., al); y += 42.;
    a.gx.text(&info, w / 2., y, 14., Color::new(1., 1., 1., 0.75 * al), 1, 0); y += 22.;
    if !upl.is_empty() { y += a.gx.text_wrap(&upl, w / 2., y + 6., w - 40., 13., 18., Color::new(1., 1., 1., 0.6 * al), 1, 0) + 10.; }
    y += 6.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh), &t("resume"), St::Cyan, if sm { 22. } else { 26. }, true) { a.click(); a.resume(); return; } y += bh + 8.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 56.), &t("settings"), St::Cyan, 20., true) { a.click(); a.back_to = Scr::Pause; a.show(Scr::Set); return; } y += 64.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 56.), &t("quit"), St::Pink, 20., true) { a.click(); a.show(Scr::None); a.g.give_up(); }
}

fn revive(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let (bx, bw) = col(a);
    let mut y = (h * 0.5 - 170.).max(tp);
    h2(&mut a.gx, &t("reviveTitle"), w / 2., y + 14., 28., al); y += 44.;
    y += a.gx.text_wrap(&t("reviveSub"), w / 2., y, w - 40., 14., 19., Color::new(1., 1., 1., 0.75 * al), 1, 0) + 10.;
    let n = a.revive_n.ceil().max(0.) as i32; let p = a.gx.px; a.gx.glow_scr(true, c::CYAN, w / 2. * p, (y + 30.) * p, 60. * p, 0.5 * al);
    a.gx.text(&n.to_string(), w / 2., y + 30., 54., Color::new(1., 1., 1., al), 1, 2); y += 76.;
    let ready = a.ad_ready(); let lbl = if ready || a.ads.cb.is_some() { t("adRevive") } else if i18n::is_en() { "Ad is loading…".to_string() } else { "Реклама загружается…".to_string() };
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 68.), &lbl, St::Gold, 19., ready) { a.click(); a.ad_show("revive", AdCb::Revive); } y += 76.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 56.), &t("noRevive"), St::Cyan, 18., a.ads.cb.is_none()) { a.click(); a.game_over(); }
}

fn stat_cells(gx: &mut Gfx, x: f32, y: f32, w: f32, cols: usize, cells: &[(String, String, bool)], al: f32, cell_h: f32) -> f32 {
    let gap = 8.; let cw = (w - gap * (cols as f32 - 1.)) / cols as f32; let rows = (cells.len() + cols - 1) / cols;
    for (i, (v, l, pearl_)) in cells.iter().enumerate() { let (cx, cy) = (x + (i % cols) as f32 * (cw + gap), y + (i / cols) as f32 * (cell_h + gap));
        panel(gx, Rect::new(cx, cy, cw, cell_h), 12., Color::new(12. / 255., 32. / 255., 60. / 255., 0.75), Color::new(120. / 255., 245. / 255., 1., 0.25), al);
        let vy = cy + cell_h * 0.4; let vs = if cell_h < 44. { 15. } else { 20. };
        if *pearl_ { let tw = gx.text_w(v, vs, 2); pearl(gx, cx + cw / 2. - tw / 2. - 8., vy, 5.5, al); gx.text(v, cx + cw / 2. + 4., vy, vs, Color::new(1., 1., 1., al), 1, 2); }
        else { gx.text(v, cx + cw / 2., vy, vs, Color::new(1., 1., 1., al), 1, 2); }
        gx.text(l, cx + cw / 2., cy + cell_h * 0.78, 11., Color::new(1., 1., 1., 0.7 * al), 1, 1); }
    rows as f32 * (cell_h + gap) - gap
}
fn time_str(t: f32) -> String { let m = (t / 60.).floor() as i32; let s = (t % 60.).floor() as i32; format!("{m}:{s:02}") }

fn over(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let land = a.landscape(); let (bx, bw) = col(a);
    let g = &a.g; let earned = a.earned; let doubled = g.ad_doubled;
    let cells = vec![(format!("{} {}", g.zone * 100, t("m")), t("depth"), false), (time_str(g.run_t), t("time"), false), (i18n::fmt_num(g.kills as i64), t("foes"), false),
        (g.max_combo.to_string(), t("maxCombo"), false), (g.p.level.to_string(), t("level"), false), (format!("+{}", if doubled { earned * 2 } else { earned }), if doubled { t("pearlsX2") } else { t("pearlsL") }, true)];
    let quests: Vec<(String, String, bool)> = g.s.daily.quests.iter().map(|q| (format!("{} {}", if q.done { "✓" } else { "•" }, i18n::quest(&q.id, q.need)),
        if q.done { if q.got { t("claimed") } else { format!("{}!", t("claim")) } } else { format!("{} / {}", i18n::fmt_num(q.p as i64), i18n::fmt_num(q.need as i64)) }, q.done)).collect();
    let dbl = earned > 0 && !doubled && a.ad_ready();
    let cell_h = if land { 40. } else if sm { 46. } else { 56. };
    let sw = if land { (w - 40.).min(520.) } else { (w - 32.).min(340.) }; let cols = if land { 3 } else { 2 };
    let stats_h = ((cells.len() + cols - 1) / cols) as f32 * (cell_h + 8.) - 8.;
    let q_h = if land { 0. } else { quests.len() as f32 * 19. + 8. };
    let bh = if sm { 56. } else { 68. };
    let total = 40. + 22. + if land { 40. } else { 62. } + 26. + stats_h + 12. + q_h + if dbl { 60. } else { 0. } + bh + 8. + 54.;
    let mut y = ((h - total) / 2.).max(tp);
    h2(&mut a.gx, &if a.g.victory { t("overWin") } else { t("overLose") }, w / 2., y + 14., if land { 21. } else { 28. }, al); y += if land { 30. } else { 40. };
    let sub = format!("{} {} · {}", a.g.zone * 100, t("m"), i18n::zone((a.g.zone as usize).saturating_sub(1) % 30)); a.gx.text(&sub, w / 2., y, 14., Color::new(1., 1., 1., 0.75 * al), 1, 0); y += 22.;
    let k = (a.over_t / 0.9).min(1.); let sc = (a.g.score as f32 * (1. - (1. - k).powi(3))) as i64;
    let bs = if land { 34. } else if sm { 44. } else { 54. }; let p = a.gx.px;
    a.gx.glow_scr(true, c::CYAN, w / 2. * p, (y + bs * 0.55) * p, bs * 1.6 * p, 0.45 * al); a.gx.text(&i18n::fmt_num(sc), w / 2., y + bs * 0.55, bs, Color::new(1., 1., 1., al), 1, 2); y += bs * 1.15;
    if (a.rec && a.g.score > 0.) || a.g.victory { let l = if a.g.victory && !a.rec { t("recWin") } else { t("recBadge") }; let tw = a.gx.text_w(&l, 13., 2) + 20.;
        a.gx.rrect(w / 2. - tw / 2., y, tw, 22., 8., with_alpha(pal(c::GOLD), al)); a.gx.text(&l, w / 2., y + 11., 13., Color::new(32. / 255., 20. / 255., 0., al), 1, 2); }
    y += 28.;
    y += stat_cells(&mut a.gx, (w - sw) / 2., y, sw, cols, &cells, al, cell_h) + 12.;
    if !land { let qx = (w - 340f32.min(w - 32.)) / 2.; let qw = 340f32.min(w - 32.);
        for (l, r, done) in &quests { a.gx.text(l, qx, y + 8., 12.5, Color::new(1., 1., 1., 0.92 * al), 0, 0); a.gx.text(r, qx + qw, y + 8., 12.5, with_alpha(if *done { pal(c::GOLD) } else { hex(0x9fdfff) }, al), 2, 1); y += 19.; }
        y += 8.; }
    if dbl { if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 52.), &t("adDouble"), St::Gold, 17., true) { a.click(); a.ad_show("double", AdCb::Double); } y += 60.; }
    if land { let hw_ = (bw - 8.) / 2.; let bx2 = (w - bw * 1.6) / 2.; let bwl = bw * 1.6;
        if a.ui.btn(&mut a.gx, Rect::new(bx2, y, bwl * 0.5 - 4., 48.), &t("again"), St::Cyan, 20., true) { a.click(); a.between(Next::Again); return; }
        if a.ui.btn(&mut a.gx, Rect::new(bx2 + bwl * 0.5 + 4., y, bwl * 0.25 - 6., 48.), &t("overShop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Over; a.ui.scroll_reset(1); a.show(Scr::Shop); return; }
        if a.ui.btn(&mut a.gx, Rect::new(bx2 + bwl * 0.75 + 2., y, bwl * 0.25 - 2., 48.), &t("overMenu"), St::Cyan, 15., true) { a.click(); a.between(Next::Menu); }
        let _ = hw_; return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh), &t("again"), St::Cyan, if sm { 22. } else { 26. }, true) { a.click(); a.between(Next::Again); return; } y += bh + 8.;
    let hw_ = (bw - 8.) / 2.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, hw_, 54.), &t("overShop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Over; a.ui.scroll_reset(1); a.show(Scr::Shop); return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx + hw_ + 8., y, hw_, 54.), &t("overMenu"), St::Cyan, 15., true) { a.click(); a.between(Next::Menu); }
}

fn end(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let (bx, bw) = col(a); let land = a.landscape(); let g = &a.g;
    let cells = vec![(i18n::fmt_num(g.score as i64), t("score"), false), (time_str(g.run_t), t("time"), false), (i18n::fmt_num(g.kills as i64), t("foes"), false),
        (g.p.level.to_string(), t("level"), false), (g.max_combo.to_string(), t("maxCombo"), false), (g.synergies.to_string(), t("syn"), false)];
    let cols = if land { 3 } else { 2 }; let cell_h = if land { 40. } else { 52. }; let sw = if land { (w - 40.).min(520.) } else { (w - 32.).min(340.) };
    let sh = ((cells.len() + cols - 1) / cols) as f32 * (cell_h + 8.) - 8.;
    let total = 40. + 44. + sh + 12. + if land { 0. } else { 70. } + 74. + 64. + if land { 0. } else { 70. };
    let mut y = ((h - total) / 2.).max(tp) + if land { 0. } else { 70. };
    end_scene(&mut a.gx, a.g.t, w, h, y - 30., al);
    ui::h2c(&mut a.gx, &t("endTitle"), w / 2., y + 14., if land { 22. } else { 34. }, al, c::GOLD, hex(0xfff3c4)); y += 42.;
    y += a.gx.text_wrap(&tf("endSub", &[&(a.g.zone * 100).to_string()]), w / 2., y, w - 40., 14., 19., Color::new(1., 1., 1., 0.75 * al), 1, 0) + 6.;
    y += stat_cells(&mut a.gx, (w - sw) / 2., y, sw, cols, &cells, al, cell_h) + 12.;
    if !land { let bxw = (w - 32.).min(340.); let ux = (w - bxw) / 2.; let gx = &mut a.gx;
        panel(gx, Rect::new(ux, y, bxw, 60.), 16., Color::new(60. / 255., 44. / 255., 8. / 255., 0.6), with_alpha(pal(c::GOLD), 0.7), al);
        let p = gx.px; gx.glow_scr(true, c::DAWN, (ux + 30.) * p, (y + 30.) * p, 22. * p, 0.8 * al); gx.circle(ux + 30., y + 30., 9., Color::new(1., 1., 0.95, al));
        gx.text(&if a.end.first { t("unlockWin") } else { tf("winN", &[&a.g.s.wins.to_string()]) }, ux + 52., y + 18., 11., with_alpha(pal(c::GOLD), al), 0, 2);
        gx.text_wrap(&if a.end.first { t("unlockWinD") } else { t("unlockOwnD") }, ux + 52., y + 36., bxw - 64., 12., 15., Color::new(1., 1., 1., 0.85 * al), 0, 0); y += 70.; }
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 66.), &format!("{}\n{}", t("endless"), t("endlessSub")), St::Gold, 19., true) { a.click(); a.g.continue_endless(); a.show(Scr::None); return; } y += 74.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 54.), &t("endFinish"), St::Cyan, 18., true) { a.click(); a.game_over(); }
}

// ---------- списки ----------
struct ListFrame { y0: f32, y1: f32, x: f32, w: f32 }
/// Заголовок, подзаголовок и кнопка «Назад»; возвращает область списка
fn list_frame(a: &mut App, title: &str, extra_h: f32) -> (ListFrame, bool) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let w = a.gx.w; let al = a.ui.alpha; let y = tp;
    h2(&mut a.gx, title, w / 2., y + 16., if _gh < 460. { 21. } else { 28. }, al);
    let lw = (w - 32. - a.safe[2] - a.safe[3]).min(520.); let (bx, bw) = col(a);
    let by = bottom(a) - 56.;
    let back = a.ui.btn(&mut a.gx, Rect::new(bx, by, bw, 56.), &t("back"), St::Cyan, 20., true);
    (ListFrame { y0: y + 40. + extra_h, y1: by - 10., x: (w - lw) / 2., w: lw }, back)
}
fn item_panel(gx: &mut Gfx, r: Rect, done: bool, al: f32) { item_card(gx, r, hex(0x5fe9ff), done, al); }
/// Карточка списка с цветом категории: светлый верх, тёмный низ, цветная полоска слева
fn item_card(gx: &mut Gfx, r: Rect, acc: Color, done: bool, al: f32) {
    let acc = if done { hex(0xffd54f) } else { acc };
    let top = Color::new(acc.r * 0.32 + 0.03, acc.g * 0.32 + 0.05, acc.b * 0.32 + 0.10, 0.78);
    let bot = Color::new(acc.r * 0.10 + 0.02, acc.g * 0.10 + 0.03, acc.b * 0.10 + 0.08, 0.86);
    ui::rrect_grad(gx, r.x, r.y, r.w, r.h, 14., with_alpha(top, al), with_alpha(bot, al));
    gx.rrect_line(r.x, r.y, r.w, r.h, 14., 1.5, with_alpha(Color::new(acc.r, acc.g, acc.b, if done { 0.8 } else { 0.45 }), al));
    gx.rrect(r.x + 1., r.y + 10., 4., r.h - 20., 2., with_alpha(acc, 0.9 * al));
}
/// Значок в круглой цветной плашке
fn icon_tile(gx: &mut Gfx, key: &str, cx: f32, cy: f32, acc: Color, pal_i: u8, al: f32) {
    let p = gx.px; gx.glow_scr(true, pal_i, cx * p, cy * p, 34. * p, 0.35 * al);
    gx.circle(cx, cy, 21., Color::new(acc.r * 0.25, acc.g * 0.25, acc.b * 0.3 + 0.05, 0.9 * al)); gx.ring(cx, cy, 21., 1.5, with_alpha(acc, 0.7 * al));
    if let Some(t_) = gx.icon.get(key).cloned() { gx.tex_ui(&t_, cx - 17., cy - 17., 34., 34., Color::new(1., 1., 1., al)); }
}
fn shop_icon(id: &str) -> &'static str { match id { "hp" => "hp", "dmg" => "dmg", "spd" => "speed", "mag" => "magnet", "xp" => "fortune", "reroll" => "prism", "flare" => "flare", "rate" => "rate", "crit" => "crit", "armor" => "armor", "regen" => "regen", "dash" => "dash", "luck" => "greed", _ => "heal" } }
fn tal_icon(id: &str) -> &'static str { match id { "t_dmg" => "dmg", "t_rate" => "rate", "t_crit" => "crit", "t_first" => "salvo", "t_hp" => "hp", "t_arm" => "armor", "t_regen" => "regen", "t_ward" => "aegis",
    "t_pearl" => "greed", "t_xp" => "echo", "t_mag" => "magnet", _ => "multi" } }
fn branch_col(br: u8) -> (Color, u8) { match br { 0 => (hex(0xff7a5c), c::FIRE), 1 => (hex(0x4fffb0), c::EMER), _ => (hex(0xffd54f), c::GOLD) } }
/// Кнопка цены: жемчужина и число
fn price_btn(a: &mut App, r: Rect, label: &str, pearl_: bool, on: bool, st: St) -> bool {
    let hit = a.ui.btn(&mut a.gx, r, if pearl_ { "" } else { label }, st, 15., on);
    if pearl_ { let al = a.ui.alpha * if on { 1. } else { 0.5 }; let tw = a.gx.text_w(label, 15., 2); let cx = r.x + r.w / 2. + 6.; pearl(&mut a.gx, cx - tw / 2. - 10., r.y + r.h / 2., 5.5, al);
        a.gx.text(label, cx, r.y + r.h / 2., 15., Color::new(234. / 255., 1., 1., al), 1, 2); }
    hit
}

fn shop(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    let (f, back) = list_frame(a, &t("shopTitle"), 70.);
    if back { a.click(); let b = a.back_to; a.show(b); return; }
    // кошелёк и вкладки
    let wy = tp + 50.; let ws = format!("{} {}", a.g.s.pearls, t("pearlsGen")); let tw = a.gx.text_w(&ws, 18., 1);
    pearl(&mut a.gx, w / 2. - tw / 2. - 10., wy, 7., al); a.gx.text(&ws, w / 2. + 6., wy, 18., with_alpha(hex(0xffe9fb), al), 1, 1);
    let tabs = [t("tabUp"), t("tabChars"), t("tabSkins"), t("tabTal")]; let tw_ = (f.w - 18.) / 4.;
    for (i, l) in tabs.iter().enumerate() { let r = Rect::new(f.x + i as f32 * (tw_ + 6.), wy + 18., tw_, 40.);
        let sel = a.shop_tab as usize == i; let a0 = a.ui.alpha; if !sel { a.ui.alpha = a0 * 0.6; }
        if a.ui.btn(&mut a.gx, r, l, St::Cyan, 14., true) && !sel { a.click(); a.shop_tab = i as u8; a.ui.scroll_reset(1); } a.ui.alpha = a0; }
    let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0);
    // содержимое: собираем высоты
    let tab = a.shop_tab;
    let iw = f.w; let bw = 100.;
    struct It { kind: u8, i: usize, h: f32 }
    let mut items: Vec<It> = vec![];
    let dsw = |a: &App, s: &str, sw: bool| a.gx.wrap(s, iw - 24. - bw - 10. - if sw { 46. } else { 0. }, 12.5, 0).len() as f32 * 16.;
    match tab {
        0 => for i in 0..SHOP.len() { let d = i18n::shop(SHOP[i].id).1; items.push(It { kind: 0, i, h: (30. + dsw(a, &d, true) + 12.).max(64.) }); },
        1 => for i in 0..CHARS.len() { let (_, d) = i18n::chr(CHARS[i].id); let d = d + &tf("healthW", &[&CHARS[i].hp.to_string()]) + " " + crate::content::char_attack(i) + "."; items.push(It { kind: 1, i, h: (30. + dsw(a, &d, true) + 12.).max(64.) }); },
        2 => for i in 0..SKINS.len() { items.push(It { kind: 2, i, h: 64. }); },
        _ => for br in 0..3 { items.push(It { kind: 4, i: br, h: 34. }); for (i, tl) in TALENTS.iter().enumerate() { if tl.br as usize != br { continue; } let d = i18n::talent(i).1; items.push(It { kind: 3, i, h: (30. + dsw(a, &d, true) + 12.).max(64.) }); } },
    }
    let content: f32 = items.iter().map(|i| i.h + 9.).sum();
    let off = a.ui.scroll(1, area, content, get_frame_time()); a.ui.clip_on(&a.gx, area);
    let mut y = f.y0 - off;
    for it in items.iter() {
        if y + it.h < f.y0 || y > f.y1 { y += it.h + 9.; continue; }
        let r = Rect::new(f.x, y, iw, it.h); let br = Rect::new(f.x + iw - 12. - bw, y + it.h / 2. - 22., bw, 44.);
        match it.kind {
            0 => { let s = &SHOP[it.i]; let l = a.g.s.shop_lv(s.id); let mx = l >= s.max; let cost = data::shop_cost(it.i, l); let (nm, d) = i18n::shop(s.id);
                let acc = hex(0x5fe9ff); item_card(&mut a.gx, r, acc, mx, al); icon_tile(&mut a.gx, shop_icon(s.id), f.x + 34., y + it.h / 2., acc, c::CYAN, al);
                let nw = a.gx.text(&nm, f.x + 64., y + 20., 16., Color::new(1., 1., 1., al), 0, 1);
                if s.max <= 6 { pips(&mut a.gx, f.x + 64. + nw + 8., y + 21., l, s.max, al); } else { let lx = f.x + 64. + nw + 10.; a.gx.text(&format!("{l}/{}", s.max), lx, y + 21., 12., with_alpha(hex(0x8fe8ff), al), 0, 1); pbar(&mut a.gx, lx + 38., y + 18., 48., 5., l as f32 / s.max as f32, hex(0x5fe9ff), al); }
                a.gx.text_wrap(&d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * al), 0, 0);
                if mx { a.ui.btn(&mut a.gx, br, &t("max"), St::Cyan, 15., false); } else if price_btn(a, br, &cost.to_string(), true, a.g.s.pearls >= cost, St::Cyan) { a.g.buy_shop(it.i); } }
            1 => { let ch = &CHARS[it.i]; let own = a.g.s.chars.contains_key(ch.id); let sel = a.g.s.ch == ch.id; let (nm, d) = i18n::chr(ch.id); let d = d + &tf("healthW", &[&ch.hp.to_string()]) + " " + crate::content::char_attack(it.i) + ".";
                item_card(&mut a.gx, r, pal(ch.col), sel, al);
                { let sk = match ch.col { c::EMER => "emerald", c::AMBER => "amber", c::FIRE => "ember", c::CORAL => "coral", c::ICE => "frost", c::GHOST => "ghost", c::CRAB => "inferno", c::DRIFT => "jade", c::GOLD => "solar", _ => "azure" };
                  let p = a.gx.px; let key = format!("pl_{sk}"); let (cx, cy) = (f.x + 30., y + it.h / 2.); a.gx.glow_scr(true, ch.col, cx * p, cy * p, 32. * p, 0.6 * al);
                  let ph = a.gx.spr_anim(&key).map(|an| a.g.t * an.freq() * std::f32::consts::TAU + it.i as f32).unwrap_or(0.);
                  a.gx.spr_screen(&key, cx * p, cy * p, -0.3, 1.2 * p, al, false, ph, false); }
                a.gx.text(&nm, f.x + 58., y + 20., 16., Color::new(1., 1., 1., al), 0, 1); a.gx.text_wrap(&d, f.x + 58., y + 40., iw - 24. - bw - 10. - 46., 12.5, 16., Color::new(1., 1., 1., 0.75 * al), 0, 0);
                if sel { a.ui.btn(&mut a.gx, br, &t("chosen"), St::Cyan, 15., false); } else if own { if a.ui.btn(&mut a.gx, br, &t("choose"), St::Cyan, 15., true) { a.g.pick_char(it.i); } }
                else if price_btn(a, br, &ch.cost.to_string(), true, a.g.s.pearls >= ch.cost, St::Cyan) { a.g.pick_char(it.i); } }
            2 => { let sk = &SKINS[it.i]; let own = a.g.s.skins.contains_key(sk.id); let sel = a.g.s.skin == sk.id;
                item_card(&mut a.gx, r, if sk.win { hex(0xffd54f) } else { pal(sk.pal) }, sel, al);
                // облик: живая модель искры
                let p = a.gx.px; let key = format!("pl_{}", sk.id); a.gx.glow_scr(true, sk.pal, (f.x + 30.) * p, (y + 32.) * p, 30. * p, 0.6 * al);
                let ph = a.gx.spr_anim(&key).map(|an| a.g.t * an.freq() * std::f32::consts::TAU + it.i as f32).unwrap_or(0.);
                a.gx.spr_screen(&key, (f.x + 30.) * p, (y + 32.) * p, -0.3, 0.75 * p, al, false, ph, false);
                a.gx.text(&i18n::skin(sk.id), f.x + 58., y + 22., 16., Color::new(1., 1., 1., al), 0, 1);
                a.gx.text(&if sk.win { t("skinWin") } else { t("skinColor") }, f.x + 58., y + 42., 12., Color::new(1., 1., 1., 0.75 * al), 0, 0);
                if sel { a.ui.btn(&mut a.gx, br, &t("worn"), St::Cyan, 15., false); } else if own { if a.ui.btn(&mut a.gx, br, &t("wear"), St::Cyan, 15., true) { a.g.pick_skin(it.i); } }
                else if sk.win { a.ui.btn(&mut a.gx, br, &t("winBtn"), St::Gold, 15., false); }
                else if price_btn(a, br, &sk.cost.to_string(), true, a.g.s.pearls >= sk.cost, St::Cyan) { a.g.pick_skin(it.i); } }
            3 => { let tl = &TALENTS[it.i]; let own = a.g.s.tal(tl.id); let open = a.g.tal_open(it.i); let (nm, d) = i18n::talent(it.i);
                let aa = if !open && !own { al * 0.6 } else { al }; let (acc, pi) = branch_col(tl.br); item_card(&mut a.gx, r, acc, own, aa); icon_tile(&mut a.gx, tal_icon(tl.id), f.x + 34., y + it.h / 2., acc, pi, aa);
                a.gx.text(&format!("{}{}", if open || own { "" } else { "✗ " }, nm), f.x + 64., y + 20., 16., Color::new(1., 1., 1., aa), 0, 1);
                a.gx.text_wrap(&d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * aa), 0, 0);
                if own { a.ui.btn(&mut a.gx, br, &t("talOwn"), St::Cyan, 15., false); } else if price_btn(a, br, &tl.cost.to_string(), true, open && a.g.s.pearls >= tl.cost, St::Cyan) { a.g.buy_tal(it.i); } }
            _ => { let (acc, _) = branch_col(it.i as u8); let s_ = i18n::tal_branch(it.i).to_uppercase(); let tw = a.gx.text_w(&s_, 14., 2);
                a.gx.rrect(f.x + 8., y + 17., iw / 2. - tw / 2. - 20., 2., 1., with_alpha(acc, 0.5 * al)); a.gx.rrect(f.x + iw / 2. + tw / 2. + 12., y + 17., iw / 2. - tw / 2. - 20., 2., 1., with_alpha(acc, 0.5 * al));
                a.gx.text(&s_, f.x + iw / 2., y + 18., 14., with_alpha(acc, al), 1, 2); }
        }
        y += it.h + 9.;
    }
    a.ui.clip_off();
}

fn ach(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    let (f, back) = list_frame(a, &t("achTitle"), 44.);
    if back { a.click(); a.show(Scr::Title); return; }
    let ids = i18n::ach_ids(); let n = ids.iter().filter(|i| a.g.s.ach.contains_key(*i)).count();
    let got: u32 = ids.iter().filter(|i| a.g.s.ach.contains_key(*i)).map(|i| i18n::ach_reward(i)).sum(); let all: u32 = ids.iter().map(|i| i18n::ach_reward(i)).sum();
    let hy = tp + 48.; let head = format!("{}{} / {}", i18n::clean(&tf("achHead", &[&n.to_string(), &ids.len().to_string()])), got, all);
    a.gx.text(&head, w / 2., hy, 13., Color::new(1., 1., 1., 0.85 * al), 1, 1); pbar(&mut a.gx, f.x, hy + 14., f.w, 6., n as f32 / ids.len() as f32, pal(c::CYAN), al);
    let mut list = ids.clone(); list.sort_by_key(|i| if a.g.s.ach.contains_key(i) { 0 } else { 1 });
    let iw = f.w; let hs: Vec<f32> = list.iter().map(|id| { let (_, d) = i18n::ach(id); let dh = a.gx.wrap(&d, iw - 24. - 44. - 70., 12.5, 0).len() as f32 * 16.; (30. + dh + 12. + if a.g.ach_progress(id).is_some() { 22. } else { 0. }).max(60.) }).collect();
    let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0); let content: f32 = hs.iter().map(|h| h + 9.).sum();
    let off = a.ui.scroll(2, area, content, get_frame_time()); a.ui.clip_on(&a.gx, area);
    let mut y = f.y0 - off;
    for (k, id) in list.iter().enumerate() { let h = hs[k]; if y + h < f.y0 || y > f.y1 { y += h + 9.; continue; }
        let done = a.g.s.ach.contains_key(id); let aa = if done { al } else { al * 0.78 }; let (nm, d) = i18n::ach(id); let r = Rect::new(f.x, y, iw, h); let gx = &mut a.gx;
        item_panel(gx, r, done, aa);
        let (ix, iy) = (f.x + 12. + 17., y + 28.);
        if done { let p = gx.px; gx.glow_scr(true, c::GOLD, ix * p, iy * p, 26. * p, 0.6 * aa); gx.circle(ix, iy, 17., with_alpha(pal(c::GOLD), aa)); gx.text("★", ix, iy, 17., Color::new(58. / 255., 38. / 255., 0., aa), 1, 2); }
        else { gx.ring(ix, iy, 16., 2., Color::new(1., 1., 1., 0.25 * aa)); gx.rrect(ix - 6., iy - 2., 12., 9., 2., Color::new(1., 1., 1., 0.45 * aa)); gx.arc(ix, iy - 3., 4.5, std::f32::consts::PI, std::f32::consts::TAU, 2., Color::new(1., 1., 1., 0.45 * aa)); }
        let tx = f.x + 12. + 44.; gx.text(&nm, tx, y + 18., 16., if done { Color::new(1., 1., 1., aa) } else { with_alpha(hex(0xbbccdd), aa) }, 0, 1);
        let dh = gx.text_wrap(&d, tx, y + 37., iw - 24. - 44. - 70., 12.5, 16., Color::new(1., 1., 1., 0.75 * aa), 0, 0);
        if let Some((cur, mx)) = a.g.ach_progress(id) { let v = if done { mx } else { cur.min(mx) }; let gx = &mut a.gx;
            pbar(gx, tx, y + 32. + dh, iw - 24. - 44. - 70., 6., v as f32 / mx as f32, if done { pal(c::GOLD) } else { pal(c::CYAN) }, aa);
            if !done { gx.text(&format!("{} / {}", i18n::fmt_num(v as i64), i18n::fmt_num(mx as i64)), tx, y + 46. + dh, 11., Color::new(1., 1., 1., 0.7 * aa), 0, 0); } }
        let rw = i18n::ach_reward(id).to_string(); let gx = &mut a.gx; let rx = f.x + iw - 14.; let tw = gx.text_w(&rw, 15., 2);
        pearl(gx, rx - tw - 10., y + h / 2., 5.5, aa); gx.text(&rw, rx, y + h / 2., 15., Color::new(1., 1., 1., aa), 2, 2);
        y += h + 9.; }
    a.ui.clip_off();
}

fn quests(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    let (f, back) = list_frame(a, &t("questsTitle"), 30.);
    if back { a.click(); a.show(Scr::Title); return; }
    let sk = a.g.s.daily.streak.max(1);
    let line = if i18n::is_en() { format!("Login streak: day {sk} · tomorrow +{} pearls", 15 * (sk + 1).min(7)) } else { format!("Вход подряд: день {sk} · завтра +{} жемчуга", 15 * (sk + 1).min(7)) };
    a.gx.text(&line, w / 2., tp + 48., 14., Color::new(1., 1., 1., 0.75 * al), 1, 0);
    let mut y = f.y0; let iw = f.w; let bw = 100.;
    for k in 0..a.g.s.daily.quests.len() { let q = a.g.s.daily.quests[k].clone(); let h = 72.; let r = Rect::new(f.x, y, iw, h);
        item_panel(&mut a.gx, r, q.got, if q.got { al * 0.8 } else { al });
        a.gx.text(&i18n::quest(&q.id, q.need), f.x + 12., y + 18., 16., Color::new(1., 1., 1., al), 0, 1);
        pbar(&mut a.gx, f.x + 12., y + 32., iw - 24. - bw - 10., 6., q.p as f32 / q.need as f32, if q.done { pal(c::GOLD) } else { pal(c::CYAN) }, al);
        let pv = format!("{} / {} · +{}", i18n::fmt_num(q.p as i64), i18n::fmt_num(q.need as i64), q.r); a.gx.text(&pv, f.x + 12., y + 54., 11., Color::new(1., 1., 1., 0.7 * al), 0, 0);
        let br = Rect::new(f.x + iw - 12. - bw, y + h / 2. - 22., bw, 44.);
        if q.got { a.ui.btn(&mut a.gx, br, &t("claimed"), St::Cyan, 15., false); }
        else if q.done && a.ad_ready() { let b1 = Rect::new(br.x - br.w * 0.35, br.y, br.w * 0.62, br.h); let b2 = Rect::new(br.x + br.w * 0.32, br.y, br.w * 0.68, br.h);
            if a.ui.btn(&mut a.gx, b1, &t("claim"), St::Cyan, 13., true) { a.g.claim_quest(k); }
            if a.ui.btn(&mut a.gx, b2, "▶ ×2", St::Gold, 15., true) { a.click(); a.ad_show("quest", AdCb::Quest(k)); } }
        else if a.ui.btn(&mut a.gx, br, &t("claim"), St::Gold, 15., q.done) { a.g.claim_quest(k); }
        y += h + 9.; }
}

fn best(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    let (f, back) = list_frame(a, &t("bestT"), 30.);
    if back { a.click(); a.show(Scr::Title); return; }
    let en = i18n::is_en();
    // (вид, ярус): обычные, затем багровые, затем твари бездны; боссы — со своими новыми обликами
    let mut keys: Vec<(usize, u8)> = vec![];
    for tr in 0..3u8 { for i in 0..ET.len() { let k = crate::data::K_ALL[i];
        let ok = if tr == 0 { ET[i].boss || !i18n::best(ET[i].key).1.is_empty() } else if ET[i].boss { crate::tiers::boss_name(k, tr, en).is_some() && !(tr == 2 && k != crate::data::K::Boss4 && keys.iter().any(|&(j, t2)| j == i && t2 == 1)) } else { crate::tiers::foe_name(k, tr, en).is_some() };
        if ok { keys.push((i, tr)); } } }
    let seen = |a: &App, i: usize, tr: u8| a.g.s.seen.contains_key(&crate::render::tkey(ET[i].key, tr));
    let n = keys.iter().filter(|&&(i, tr)| seen(a, i, tr)).count();
    a.gx.text(&tf("bestInfo", &[&n.to_string(), &keys.len().to_string()]), w / 2., tp + 48., 14., Color::new(1., 1., 1., 0.75 * al), 1, 0);
    let info = |i: usize, tr: u8| -> (String, String) { let k = crate::data::K_ALL[i]; let key = ET[i].key;
        if tr == 0 { let nm = if ET[i].boss { i18n::boss(key) } else { let n = i18n::best(key).0; if n.is_empty() { key.to_string() } else { n } }; (nm, i18n::best(key).1) }
        else if ET[i].boss { (crate::tiers::boss_name(k, tr, en).unwrap_or("").to_string(), if en { format!("A lord of the deep: new attacks. {}", i18n::best(key).1) } else { format!("Владыка глубин: новые приёмы. {}", i18n::best(key).1) }) }
        else { (crate::tiers::foe_name(k, tr, en).unwrap_or("").to_string(), format!("{} · {}", if tr == 1 { if en { "600 m+" } else { "600 м и глубже" } } else if en { "1100 m+" } else { "1100 м и глубже" }, crate::tiers::foe_desc(k, tr, en))) } };
    let iw = f.w; let hs: Vec<f32> = keys.iter().map(|&(i, tr)| { let d = if seen(a, i, tr) { info(i, tr).1 } else { t("bestLocked") };
        (30. + a.gx.wrap(&d, iw - 24. - 66., 12.5, 0).len() as f32 * 16. + 12.).max(70.) }).collect();
    let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0); let content: f32 = hs.iter().map(|h| h + 9.).sum();
    let off = a.ui.scroll(4, area, content, get_frame_time()); a.ui.clip_on(&a.gx, area);
    let mut y = f.y0 - off;
    for (k, &(i, tr)) in keys.iter().enumerate() { let h = hs[k]; if y + h < f.y0 || y > f.y1 { y += h + 9.; continue; }
        let key_s = crate::render::tkey(ET[i].key, tr); let key = key_s.as_str(); let ok = seen(a, i, tr); let r = Rect::new(f.x, y, iw, h); item_panel(&mut a.gx, r, ET[i].boss, al);
        let p = a.gx.px; let half = a.gx.spr_half(key); let k_ = 26. / half;
        let ph = a.gx.spr_anim(key).map(|an| a.g.t * an.freq() * std::f32::consts::TAU + k as f32).unwrap_or(0.);
        if ok { a.gx.glow_scr(true, crate::tiers::tier_col(ET[i].col, tr), (f.x + 40.) * p, (y + h / 2.) * p, 30. * p, 0.4 * al); a.gx.spr_screen(key, (f.x + 40.) * p, (y + h / 2.) * p, 0., k_ * p, al, false, ph, false); }
        else { let s = a.gx.spr.get(key).map(|s| s.tex.clone()); if let Some(tx) = s { a.gx.set_mat(2); draw_warp(&tx, (f.x + 40.) * p, (y + h / 2.) * p, 26. * p, 0., false, 1., 1., None, 0., Color::new(29. / 255., 68. / 255., 102. / 255., al)); a.gx.set_mat(0); } }
        let (nm, ds) = info(i, tr);
        a.gx.text(&if ok { nm } else { "???".into() }, f.x + 78., y + 20., 16., if tr == 1 { Color::new(1., 0.7, 0.7, al) } else if tr == 2 { Color::new(0.85, 0.75, 1., al) } else { Color::new(1., 1., 1., al) }, 0, 1);
        a.gx.text_wrap(&if ok { ds } else { t("bestLocked") }, f.x + 78., y + 40., iw - 24. - 66., 12.5, 16., Color::new(1., 1., 1., 0.75 * al), 0, 0);
        y += h + 9.; }
    a.ui.clip_off();
}

fn settings(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let land = a.landscape(); let s = &a.g.s.set;
    let orient = match s.orient { 1 => if i18n::is_en() { "LANDSCAPE" } else { "ГОРИЗОНТАЛЬНО" }, 2 => if i18n::is_en() { "AUTO" } else { "АВТО" }, _ => if i18n::is_en() { "PORTRAIT" } else { "ВЕРТИКАЛЬНО" } };
    let orient_l = if i18n::is_en() { "Orientation" } else { "Экран" };
    let rows: Vec<(String, u8)> = vec![
        (format!("{}: {}", t("sound"), vol_l(s.sound, s.vsfx)), 0), (format!("{}: {}", t("music"), vol_l(s.music, s.vmus)), 1), (format!("{}: {}", t("vibro"), on_off(s.vibro)), 2),
        (format!("{}: {}", t("graphics"), match s.quality.as_str() { "high" => t("gHigh"), "low" => t("gLow"), _ => t("gAuto") }), 3),
        (format!("{}: {}", t("nums"), on_off(s.nums)), 4), (format!("{}: {}", t("shake"), on_off(s.shake)), 5),
        (format!("{orient_l}: {orient}"), 8), (format!("{}: {}", if i18n::is_en() { "Glow" } else { "Подсветка" }, on_off(s.fx)), 9), (format!("{}: {}", t("lang"), if s.lang == "en" { "English" } else { "Русский" }), 6), (format!("{}: {}", t("fps"), s.fps), 7) ];
    let (bx, bw) = col(a); let bh = if sm { 46. } else { 50. }; let gap = if sm { 6. } else { 8. };
    let ncol = if land { 2 } else { 1 }; let cw = if land { ((w - 40.) / 2.).min(300.) } else { bw }; let x0 = if land { (w - cw * 2. - 12.) / 2. } else { bx };
    let nrow = (rows.len() + ncol - 1) / ncol; let total = 40. + nrow as f32 * (bh + gap) + 8. + bh;
    let mut y = ((h - total) / 2.).max(tp);
    h2(&mut a.gx, &t("setTitle"), w / 2., y + 14., if land { 21. } else { 28. }, al); y += 40.;
    let mut act = None;
    for (k, (l, id)) in rows.iter().enumerate() { let (cx, cy) = (x0 + (k % ncol) as f32 * (cw + 12.), y + (k / ncol) as f32 * (bh + gap));
        if a.ui.btn(&mut a.gx, Rect::new(cx, cy, cw, bh), l, St::Cyan, 17., true) { act = Some(*id); } }
    y += nrow as f32 * (bh + gap) + 4.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh), &t("back"), St::Pink, 18., true) { a.click(); let b = a.back_to; a.show(b); return; }
    if let Some(id) = act { a.click(); let s = &mut a.g.s.set;
        // громкость по кругу: 100 → 80 → 60 → 40 → 20 → выкл → 100
        match id { 0 => { s.vsfx = vol_next(s.sound, s.vsfx); s.sound = s.vsfx > 0; } 1 => { s.vmus = vol_next(s.music, s.vmus); s.music = s.vmus > 0; } 2 => { s.vibro = !s.vibro; if s.vibro { crate::platform::vibrate(30); } },
            3 => s.quality = match s.quality.as_str() { "auto" => "high".into(), "high" => "low".into(), _ => "auto".into() }, 4 => s.nums = !s.nums, 5 => s.shake = !s.shake,
            6 => { s.lang = if s.lang == "en" { "ru".into() } else { "en".into() }; i18n::set_en(s.lang == "en"); }, 7 => s.fps = if s.fps == 120 { 60 } else { 120 },
            9 => { s.fx = !s.fx; a.glow_auto_off = false; a.glow_slow = 0.; } _ => s.orient = (s.orient + 1) % 3 }
        a.g.dirty = true; a.persist(); }
}
