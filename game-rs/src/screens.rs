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
    if a.scr != Scr::Title && a.scr != Scr::Try { let light = matches!(a.scr, Scr::Level | Scr::Pause | Scr::Revive); let tm = a.g.t; menu_backdrop(&mut a.gx, tm, al, light); }
    match a.scr {
        Scr::Title => { if a.rate_pending { a.rate_pending = false; a.show(Scr::Rate); } title(a) } Scr::How => how(a), Scr::Level => level(a), Scr::Pause => pause(a), Scr::Revive => revive(a), Scr::Over => over(a),
        Scr::Shop => shop(a), Scr::Ach => ach(a), Scr::Set => settings(a), Scr::Quest => quests(a), Scr::Best => best(a), Scr::Modes => modes(a), Scr::Wheel => wheel(a), Scr::Map => ocean_map(a), Scr::Rate => rate(a), Scr::Card => card(a), Scr::Xfer => xfer(a), Scr::Try => try_scr(a), Scr::End => end(a), Scr::None => {}
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
    // ---- колесо удачи (кнопка под рекордом) и событие выходных ----
    { let free = a.g.s.daily.wheel == 0; let (wx, wy) = (bx + 26., tp + 62.); let p = a.gx.px;
      a.gx.glow_scr(true, c::GOLD, wx * p, wy * p, 30. * p, if free { 0.5 + 0.3 * (tm * 4.).sin() } else { 0.2 } * al);
      a.gx.circle(wx, wy, 22., Color::new(0.2, 0.12, 0.02, 0.85 * al)); a.gx.ring(wx, wy, 22., 2., with_alpha(hex(0xffd54f), al));
      if let Some(tx) = a.gx.icon.get("fortune").cloned() { a.gx.tex_ui(&tx, wx - 15., wy - 15., 30., 30., Color::new(1., 1., 1., al)); }
      if free { a.gx.circle(wx + 15., wy - 15., 6., with_alpha(hex(0xff4f6f), al)); }
      if a.ui.tap(Rect::new(wx - 26., wy - 26., 52., 52.)) { a.click(); a.show(Scr::Wheel); return; }
      if let Some(ev) = crate::extras::event_today() { let (n, d) = crate::extras::event_txt(ev); let col = hex(crate::extras::EVENTS[ev].col);
          a.gx.text(&format!("★ {}", n), bx + 58., wy - 8., 14., with_alpha(col, al), 0, 2); a.gx.text(d, bx + 58., wy + 10., 11., Color::new(1., 1., 1., 0.8 * al), 0, 0); } }
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
    // регион (карта океана) — плашка над «Играть»
    { let en = i18n::is_en(); let ri = a.g.s.region as usize; let nm = crate::extras::region_txt(ri).0; let l = format!("{}{}: {} ›", if a.g.s.set.hard && a.g.s.wins > 0 { "☠ " } else { "" }, if en { "Region" } else { "Регион" }, nm); let tw = a.gx.text_w(&l, 13., 1) + 24.;
      let r = Rect::new(bx + bw / 2. - tw / 2., y - 34., tw, 26.); ui::rrect_grad(&mut a.gx, r.x, r.y, r.w, r.h, 13., Color::new(0.03, 0.1, 0.2, 0.7 * al), Color::new(0.02, 0.06, 0.14, 0.6 * al));
      a.gx.rrect_line(r.x, r.y, r.w, r.h, 13., 1., with_alpha(hex(crate::extras::REGIONS[ri].col), 0.7 * al)); a.gx.text(&l, r.x + r.w / 2., r.y + 13., 13., Color::new(1., 1., 1., al), 1, 1);
      if a.ui.tap(r) { a.click(); a.map_pick = a.g.s.region; a.show(Scr::Map); return; } }
    // «Играть» и рядом — забег с улучшением на старте за рекламу (до 5 в день)
    let boost_left = BOOST_MAX.saturating_sub(a.g.s.daily.boost); let boost = boost_left > 0 && a.g.s.runs >= 1 && a.ad_ready();
    let pw = if boost { bw * 0.6 } else { bw };
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, pw, bh_play), &t("play"), St::Cyan, if sm { 24. } else { 28. }, true) { a.click(); a.g.s.seen_how = true; a.start_run(RunMode::Normal); return; }
    if boost { let l = format!("▶ {}\n{} ({})", if i18n::is_en() { "Play" } else { "Играть" }, if i18n::is_en() { "with an upgrade" } else { "с улучшением" }, boost_left);
        if a.ui.btn(&mut a.gx, Rect::new(bx + pw + gap, y, bw - pw - gap, bh_play), &l, St::Gold, 17., true) { a.click(); a.ad_show("boost", AdCb::Boost); return; } }
    y += bh_play + gap;
    let muts = crate::flow::daily_muts(); let mn: Vec<String> = muts.iter().map(|&i| i18n::mutator(data::MUTS[i]).0).collect(); let d = a.g.s.daily.clone();
    let qd = d.quests.iter().filter(|q| q.done).count(); let qr = a.g.quests_ready();
    let en = i18n::is_en(); let n = if gift { 3. } else { 2. }; let tw_ = (bw - gap * (n - 1.)) / n;
    let _ = &mn; let daily_l = format!("{}\n{}{}", if en { "Modes" } else { "Режимы" }, if en { "daily · time · more" } else { "испытание · на время…" }, if d.ch_done { " ✓" } else { "" });
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, tw_, tile_h), &daily_l, St::Gold, 16., true) { a.click(); a.ui.scroll_reset(5); a.show(Scr::Modes); return; }
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
    let mut links: Vec<(String, u8)> = vec![]; // 4.8.1: Кошмар включается только в «Режимах» (ссылка внизу убрана)
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
    let mut links: Vec<(String, u8)> = vec![]; // 4.8.1: Кошмар включается только в «Режимах» (ссылка внизу убрана)
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
    let rm = a.relic_mode || a.path_mode; let pm = a.path_mode;
    let infos: Vec<(String, String, bool, u8, u8, u8)> = a.cards.iter().map(|&i| if pm { let (n, d) = crate::content::path_txt(i as u8); (n.to_string(), d.to_string(), true, 0, 1, crate::content::PATHS[i - 1].col) } else if i >= crate::content::EVO_BASE && i != U_HEAL { let (n, d) = crate::content::evo_txt(i - crate::content::EVO_BASE); (n.to_string(), d.to_string(), true, 0, 1, c::GOLD) } else if rm { let (n, d) = crate::content::relic_txt(i as u8); (n.to_string(), d.to_string(), true, 0, 1, crate::content::RELICS[i].col) } else if i == U_HEAL { ("Чистый свет".to_string(), "Восстановить 50% здоровья и +1000 очков".to_string(), false, 0, 1, c::EMER) }
        else { let fm = a.g.p.form; let nm = crate::upgtxt::name_f(i, fm); let d = crate::upgtxt::card_f(i, a.g.p.up[i] + 1, fm); (nm, d, UPG[i].syn.is_some(), a.g.p.up[i], UPG[i].max, UPG[i].col) }).collect();
    let heal_en = i18n::is_en();
    let hs: Vec<f32> = infos.iter().map(|inf| { let dw = if land { cwid - 24. } else { cwid - 28. - 68. }; let dh = a.gx.wrap(&inf.1, dw, 13.5, 0).len() as f32 * 17.;
        if land { 12. + 56. + 8. + if inf.2 && !rm { 18. } else { 0. } + 24. + dh + 12. } else { (24. + if inf.2 && !rm { 18. } else { 0. } + 22. + dh).max(80.) } }).collect();
    let gap = if sm { 9. } else { 12. };
    let total: f32 = if land { hs.iter().cloned().fold(0., f32::max) } else { hs.iter().sum::<f32>() + gap * (n as f32 - 1.) };
    let head = 28. + 14. + 24. + 14.; let foot = 12. + 44. + 50.;
    if !land { y = ((h - head - total - foot) / 2.).max(tp) + 14.; }
    if pm { ui::h2c(&mut a.gx, if i18n::is_en() { "CHOOSE A PATH" } else { "РАЗВИЛКА" }, w / 2., y + 14., if land { 21. } else { 30. }, al, c::ICE, hex(0xd8f6ff)); }
    else if rm { ui::h2c(&mut a.gx, if i18n::is_en() { "RELIC" } else { "РЕЛИКВИЯ" }, w / 2., y + 14., if land { 21. } else { 30. }, al, c::GOLD, hex(0xffe9a8)); }
    else { h2(&mut a.gx, &format!("{}{}", t("lvlUp"), a.g.p.level), w / 2., y + 14., if land { 21. } else { 28. }, al); }
    y += if land { 34. } else { 42. };
    let sub = if pm { if i18n::is_en() { "How will you descend to the next lord?".to_string() } else { "Каким путём плыть до следующего владыки?".to_string() } }
        else if rm { if i18n::is_en() { "A powerful artifact for the whole run — pick one".to_string() } else { "Сильный предмет на весь забег — выбери один".to_string() } }
        else if !rm && infos.iter().any(|i| i.2) && a.g.s.hints.get("syn").copied().unwrap_or(0) < 1 { if a.cards_t < 0.1 { a.g.s.hints.insert("syn".into(), 0); } if a.cards_t > 3. { a.g.s.hints.insert("syn".into(), 1); a.g.dirty = true; }
            if i18n::is_en() { "Gold card — a synergy: a powerful combo of two upgrades".to_string() } else { "Золотая карта — синергия: сильное сочетание двух улучшений".to_string() } }
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
        let icon_key = if pm { crate::content::PATHS[a.cards[k] - 1].icon.to_string() } else if a.cards[k] >= crate::content::EVO_BASE && a.cards[k] != U_HEAL { crate::content::EVOS[a.cards[k] - crate::content::EVO_BASE].icon.to_string() } else if rm { crate::content::RELICS[a.cards[k]].icon.to_string() } else if a.cards[k] == U_HEAL { "heal".to_string() } else { UPG[a.cards[k]].id.to_string() };
        let ic = gx.icon.get(&icon_key).cloned();
        let name = if rm { inf.0.clone() } else if a.cards[k] == U_HEAL && heal_en { "Pure Light".to_string() } else { inf.0.clone() };
        let desc = if rm { inf.1.clone() } else if a.cards[k] == U_HEAL && heal_en { "Restore 50% health and +1000 points".to_string() } else { inf.1.clone() };
        if land {
            let mut yy = r2.y + 12.; if let Some(t_) = ic { gx.tex_ui(&t_, r2.x + r2.w / 2. - 28., yy, 56., 56., Color::new(1., 1., 1., ca)); } yy += 64.;
            if syn && !rm { if a.cards[k] >= crate::content::EVO_BASE && a.cards[k] != U_HEAL { tag_l(gx, r2.x + r2.w / 2., yy + 6., ca, if i18n::is_en() { "EVOLUTION" } else { "ЭВОЛЮЦИЯ" }); } else { tag(gx, r2.x + r2.w / 2., yy + 6., ca); } yy += 18.; }
            gx.text(&name, r2.x + r2.w / 2., yy + 8., 17., Color::new(1., 1., 1., ca), 1, 2); yy += 18.;
            if max > 1 { let pw = max as f32 * 10.; pips(gx, r2.x + r2.w / 2. - pw / 2., yy + 4., lvl + 1, max, ca); } yy += 12.;
            gx.text_wrap(&desc, r2.x + r2.w / 2., yy + 8., r2.w - 24., 13., 17., Color::new(1., 1., 1., 0.85 * ca), 1, 0);
        } else {
            let p = gx.px; gx.glow_scr(true, colr, (r2.x + 14. + 28.) * p, (r2.y + r2.h / 2.) * p, 36. * p, 0.25 * ca);
            if let Some(t_) = ic { gx.tex_ui(&t_, r2.x + 14., r2.y + r2.h / 2. - 28., 56., 56., Color::new(1., 1., 1., ca)); }
            let tx = r2.x + 14. + 56. + 12.; let mut yy = r2.y + 14.;
            if syn && !rm { if a.cards[k] >= crate::content::EVO_BASE && a.cards[k] != U_HEAL { tag_l(gx, tx + 38., yy + 6., ca, if i18n::is_en() { "EVOLUTION" } else { "ЭВОЛЮЦИЯ" }); } else { tag(gx, tx + 34., yy + 6., ca); } yy += 18.; }
            let nw = gx.text(&name, tx, yy + 8., 18., Color::new(1., 1., 1., ca), 0, 2);
            if max > 1 { pips(gx, tx + nw + 8., yy + 9., lvl + 1, max, ca); }
            yy += 22.; gx.text_wrap(&desc, tx, yy + 8., r2.w - (tx - r2.x) - 12., 13.5, 17., Color::new(1., 1., 1., 0.85 * ca), 0, 0);
        }
        if appear >= 1. && a.ui.tap(r) { chosen = Some(k); }
    }
    if let Some(k) = chosen { if a.ui.lock <= 0. { a.take_card(k); return; } }
    let by = if land { y + total + 12. } else { y + total + 12. };
    if pm { return; }
    if rm { if !a.relic_rerolled && a.ad_ready() { let by = y + total + 12.; let l = if i18n::is_en() { "▶ Other relics".to_string() } else { "▶ Другие реликвии".to_string() };
            let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(w / 2. - bw / 2., by, bw, 44.), &l, St::Gold, 16., true) { a.click(); a.ad_show("relic", AdCb::RelicReroll); } }
        return; }
    let mut bx_ = w / 2.; let rr = a.g.rerolls; let can_ad = rr == 0 && a.g.ad_rerolls < 2 && a.ad_ready();
    if rr > 0 { let l = tf("reroll2", &[&rr.to_string()]); let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(bx_ - bw / 2., by, bw, 44.), &l, St::Cyan, 16., true) { a.click(); a.g.rerolls -= 1; a.roll_cards(); } bx_ += 0.; }
    else if can_ad { let l = t("adReroll"); let bw = a.gx.text_w(&l, 16., 2) + 30.; if a.ui.btn(&mut a.gx, Rect::new(bx_ - bw / 2., by, bw, 44.), &l, St::Gold, 16., true) { a.click(); a.ad_show("reroll", AdCb::Reroll); } }
}
fn tag(gx: &mut Gfx, cx: f32, cy: f32, al: f32) { tag_l(gx, cx, cy, al, &t("synergy")) }
fn tag_l(gx: &mut Gfx, cx: f32, cy: f32, al: f32, s: &str) { let s = s.to_string(); let w = gx.text_w(&s, 10., 2) + 14.; gx.rrect(cx - w / 2., cy - 8., w, 16., 6., with_alpha(pal(c::GOLD), al)); gx.text(&s, cx, cy, 10., Color::new(32. / 255., 20. / 255., 0., al), 1, 2); }

fn pause(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let w = a.gx.w; let al = a.ui.alpha; let (bx, bw) = col(a);
    let ups: Vec<String> = UPG.iter().enumerate().filter(|(i, _)| a.g.p.up[*i] > 0).map(|(i, u)| { let n = crate::upgtxt::name_f(i, a.g.p.form); let _ = u.id; if u.max > 1 { format!("{n} {}", a.g.p.up[i]) } else { n } }).collect();
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
    let sh2 = a.g.run_shards > 0 && !a.g.shards_x2 && a.ad_ready() && !land; // 4.7: ×2 осколков света за рекламу
    let cell_h = if land { 40. } else if sm { 46. } else { 56. };
    let sw = if land { (w - 40.).min(520.) } else { (w - 32.).min(340.) }; let cols = if land { 3 } else { 2 };
    let stats_h = ((cells.len() + cols - 1) / cols) as f32 * (cell_h + 8.) - 8.;
    let q_h = if land { 0. } else { quests.len() as f32 * 19. + 8. };
    let bh = if sm { 56. } else { 68. };
    let total = 40. + 22. + if land { 40. } else { 62. } + 26. + stats_h + 12. + q_h + if dbl { 60. } else { 0. } + if sh2 { 52. } else { 0. } + bh + 8. + 54. + if land { 0. } else { 44. };
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
    if sh2 { let l = if i18n::is_en() { format!("▶ ×2 light shards (+{})", a.g.run_shards) } else { format!("▶ ×2 осколков света (+{})", a.g.run_shards) };
        if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 44.), &l, St::Gold, 15., true) { a.click(); a.ad_show("shards", AdCb::Shards); } y += 52.; }
    if land { let hw_ = (bw - 8.) / 2.; let bx2 = (w - bw * 1.6) / 2.; let bwl = bw * 1.6;
        if a.ui.btn(&mut a.gx, Rect::new(bx2, y, bwl * 0.5 - 4., 48.), &t("again"), St::Cyan, 20., true) { a.click(); a.between(Next::Again); return; }
        if a.ui.btn(&mut a.gx, Rect::new(bx2 + bwl * 0.5 + 4., y, bwl * 0.25 - 6., 48.), &t("overShop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Over; a.ui.scroll_reset(1); a.show(Scr::Shop); return; }
        if a.ui.btn(&mut a.gx, Rect::new(bx2 + bwl * 0.75 + 2., y, bwl * 0.25 - 2., 48.), &t("overMenu"), St::Cyan, 15., true) { a.click(); a.between(Next::Menu); }
        let _ = hw_; return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh), &t("again"), St::Cyan, if sm { 22. } else { 26. }, true) { a.click(); a.between(Next::Again); return; } y += bh + 8.;
    let hw_ = (bw - 8.) / 2.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, hw_, 54.), &t("overShop"), St::Pink, 15., true) { a.click(); a.back_to = Scr::Over; a.ui.scroll_reset(1); a.show(Scr::Shop); return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx + hw_ + 8., y, hw_, 54.), &t("overMenu"), St::Cyan, 15., true) { a.click(); a.between(Next::Menu); return; }
    y += 62.; if a.g.zone >= 2 && a.ui.btn(&mut a.gx, Rect::new(bx + bw * 0.2, y, bw * 0.6, 36.), if i18n::is_en() { "Share record" } else { "Поделиться рекордом" }, St::Gold, 14., true) { a.click(); a.show(Scr::Card); }
}

// ---------------- 4.3: карточка рекорда, просьба об оценке ----------------
/// Где на экране лежит карточка (её же снимает share_capture)
pub fn card_rect(a: &App) -> Rect { let (w, h) = (a.gx.w, a.gx.h); let cw = (w - 32.).min(360.).min((h - 200.) / 1.25); let ch = cw * 1.25; Rect::new((w - cw) / 2., (top(a) + 10.).max((h - ch - 140.) / 2.), cw, ch) }
fn record_card(a: &mut App, r: Rect) {
    let en = i18n::is_en(); let p = a.gx.px; let tm = a.g.t; let (cx, al) = (r.x + r.w / 2., 1.);
    let g = &a.g; let depth = g.zone * 100; let best = g.s.best_depth.max(depth); let zn = i18n::zone((g.zone as usize).saturating_sub(1) % 30).to_string();
    let skin = &SKINS[g.p.skin.min(SKINS.len() - 1)]; let (score, kills, ab, reg) = (g.score as i64, g.kills, g.abyss, g.region as usize);
    ui::rrect_grad(&mut a.gx, r.x, r.y, r.w, r.h, 22., Color::new(0.03, 0.2, 0.36, 1.), Color::new(0.12, 0.03, 0.22, 1.));
    // лучи и искорки
    for i in 0..5 { let x = r.x + r.w * (0.15 + i as f32 * 0.18); a.gx.glow_scr(true, c::CYAN, x * p, (r.y + 10.) * p, r.w * 0.22 * p, 0.12); }
    for i in 0..26 { let fx = (i as f32 * 0.6180339).fract(); let fy = (i as f32 * 0.4142135 + 0.3).fract(); let rr = 1.2 + (i % 3) as f32;
        a.gx.glow_scr(false, [c::ICE, c::JELLY, c::GOLD][i % 3], (r.x + 12. + fx * (r.w - 24.)) * p, (r.y + 12. + fy * (r.h - 24.)) * p, rr * 2.2 * p, 0.55); }
    ui::h2c(&mut a.gx, if en { "LIGHT OF THE ABYSS" } else { "СВЕТ БЕЗДНЫ" }, cx, r.y + 34., r.w * 0.085, al, c::ICE, hex(0xe6f8ff));
    // герой
    let hy = r.y + r.h * 0.36; a.gx.glow_scr(true, skin.pal, cx * p, hy * p, r.w * 0.42 * p, 0.7); a.gx.glow_scr(false, c::WHITE, cx * p, hy * p, 16. * p, 0.7);
    let key = format!("pl_{}", skin.id); let ph = a.gx.spr_anim(&key).map(|an| tm * an.freq() * std::f32::consts::TAU).unwrap_or(0.);
    a.gx.spr_screen(&key, cx * p, hy * p, -0.25, r.w / 75. * p, al, false, ph, true);
    // глубина
    let dy = r.y + r.h * 0.62; let ds = format!("{} {}", i18n::fmt_num(depth as i64), t("m"));
    a.gx.glow_scr(true, c::CYAN, cx * p, dy * p, r.w * 0.3 * p, 0.35); a.gx.text(&ds, cx, dy, r.w * 0.15, Color::new(1., 1., 1., al), 1, 2);
    a.gx.text(&zn, cx, dy + r.w * 0.1, 14., with_alpha(hex(0x9fdfff), al), 1, 1);
    let mut line = format!("{} {}  ·  {} {}", if en { "score" } else { "очки" }, i18n::fmt_num(score), kills, if en { "foes" } else { "врагов" });
    if ab > 0 { line += &format!("  ·  {} {ab}", if en { "Abyss" } else { "Бездна" }); }
    a.gx.text(&line, cx, dy + r.w * 0.1 + 22., 12.5, Color::new(1., 1., 1., 0.85), 1, 0);
    if reg > 0 { a.gx.text(crate::extras::region_txt(reg).0, cx, dy + r.w * 0.1 + 40., 12.5, with_alpha(hex(crate::extras::REGIONS[reg].col), 0.95), 1, 1); }
    let rec = if depth >= best { if en { "★ NEW RECORD ★".to_string() } else { "★ НОВЫЙ РЕКОРД ★".to_string() } } else if en { format!("record: {best} m") } else { format!("рекорд: {best} м") };
    let tw = a.gx.text_w(&rec, 13., 2) + 22.; let ry = r.y + r.h - 64.; a.gx.rrect(cx - tw / 2., ry - 12., tw, 24., 10., if depth >= best { pal(c::GOLD) } else { Color::new(1., 1., 1., 0.15) });
    a.gx.text(&rec, cx, ry, 13., if depth >= best { Color::new(0.13, 0.08, 0., 1.) } else { WHITE }, 1, 2);
    a.gx.text(if en { "Can you dive deeper?  ·  RuStore" } else { "Сможешь глубже?  ·  RuStore" }, cx, r.y + r.h - 24., 13., with_alpha(hex(0xffe08a), 0.95), 1, 1);
    a.gx.rrect_line(r.x, r.y, r.w, r.h, 22., 2., Color::new(0.6, 0.9, 1., 0.6));
}
fn card(a: &mut App) {
    let r = card_rect(a); let al = a.ui.alpha; record_card(a, r); let (bx, bw) = col(a); let en = i18n::is_en();
    let y = r.y + r.h + 18.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 54.), if en { "Share" } else { "Поделиться" }, St::Gold, 20., true) { a.click(); a.share_cap = Some(r); }
    if a.ui.btn(&mut a.gx, Rect::new(bx, y + 62., bw, 46.), &t("back"), St::Cyan, 17., true) { a.click(); a.show(Scr::Over); }
    let _ = al;
}
fn rate(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let (bx, bw) = col(a); let tm = a.g.t; let p = a.gx.px;
    a.gx.rrect(0., 0., w, h, 0., Color::new(0., 0.02, 0.06, 0.55 * al));
    let ph = 330.; let y0 = (h - ph) / 2.; panel(&mut a.gx, Rect::new(bx - 8., y0, bw + 16., ph), 20., Color::new(0.03, 0.1, 0.2, 0.95), Color::new(1., 0.84, 0.4, 0.6), al);
    ui::h2c(&mut a.gx, if en { "Enjoying the game?" } else { "Нравится игра?" }, w / 2., y0 + 36., 24., al, c::GOLD, hex(0xfff1c2));
    for i in 0..5 { let x = w / 2. + (i as f32 - 2.) * 40.; let y = y0 + 88. + (tm * 3. + i as f32 * 0.6).sin() * 3.;
        a.gx.glow_scr(true, c::GOLD, x * p, y * p, 30. * p, 0.5 * al); a.gx.text("★", x, y, 34., with_alpha(hex(0xffd54f), al), 1, 2); }
    a.gx.text_wrap(if en { "Rate Light of the Abyss in RuStore — it really helps the game grow and get new bosses and regions!" } else { "Поставь оценку «Свету Бездны» в RuStore — это очень помогает игре расти, а нам — делать новых владык и регионы!" },
        w / 2., y0 + 124., bw - 20., 14.5, 20., Color::new(1., 1., 1., 0.9 * al), 1, 0);
    let by = y0 + ph - 132.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, by, bw, 54.), if en { "Rate ★★★★★" } else { "Оценить ★★★★★" }, St::Gold, 19., true) { a.click(); a.g.s.rate = 2; a.g.dirty = true; crate::platform::rate_app(); a.show(Scr::Title); return; }
    let hw = (bw - 8.) / 2.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, by + 62., hw, 44.), if en { "Later" } else { "Позже" }, St::Cyan, 15., true) { a.click(); let s = &mut a.g.s; if s.rate == 0 { s.rate = 1; s.rate_at = s.runs + 10; } else { s.rate = 2; } a.g.dirty = true; a.show(Scr::Title); return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx + hw + 8., by + 62., hw, 44.), if en { "Don't ask" } else { "Не спрашивать" }, St::Pink, 14., true) { a.click(); a.g.s.rate = 2; a.g.dirty = true; a.show(Scr::Title); }
}

/// 4.8: примерка — поверх песочницы: что примеряем и кнопки «Купить/Надеть» и «Назад»
fn try_scr(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let (bx, bw) = col(a); let tp = top(a);
    let Some(real) = a.try_real.as_ref() else { return; }; let rs = &real.s; let (k, i) = a.try_kind;
    let (nm, own, sel, cost, win) = match k {
        0 => { let sk = &SKINS[i]; (i18n::skin(sk.id), rs.skins.contains_key(sk.id), rs.skin == sk.id, sk.cost, sk.win) }
        1 => (crate::extras::trail_txt(i).0.to_string(), i == 0 || rs.trails.contains_key(&i.to_string()), rs.trail as usize == i, crate::extras::TRAILS[i].cost, false),
        2 => (crate::extras::death_txt(i).0.to_string(), i == 0 || rs.deaths.contains_key(&i.to_string()), rs.death as usize == i, crate::extras::DEATHS[i].cost, false),
        _ => (crate::extras::shot_txt(i).0.to_string(), i == 0 || rs.shots.contains_key(&i.to_string()), rs.shot as usize == i, crate::extras::SHOTS[i].cost, false) };
    let pearls = rs.pearls;
    let pw = (a.gx.text_w(&nm, 20., 2) + 60.).max(220.).min(w - 32.); let py = tp + 8.;
    panel(&mut a.gx, Rect::new(w / 2. - pw / 2., py, pw, 62.), 18., Color::new(0.02, 0.07, 0.15, 0.82), Color::new(1., 0.84, 0.31, 0.7), al);
    a.gx.text(if en { "TRY-ON" } else { "ПРИМЕРКА" }, w / 2., py + 18., 12., with_alpha(hex(0xffd54f), al), 1, 2);
    a.gx.text(&nm, w / 2., py + 42., 20., Color::new(1., 1., 1., al), 1, 2);
    let by = h - 128.; let hw = (bw - 8.) / 2.;
    if sel { a.ui.btn(&mut a.gx, Rect::new(bx, by, hw, 54.), if en { "Worn" } else { "Надето" }, St::Gold, 16., false); }
    else if own { if a.ui.btn(&mut a.gx, Rect::new(bx, by, hw, 54.), if en { "Wear" } else { "Надеть" }, St::Gold, 17., true) { a.click(); a.try_buy(); return; } }
    else if win { a.ui.btn(&mut a.gx, Rect::new(bx, by, hw, 54.), if en { "For a feat" } else { "За подвиг" }, St::Gold, 15., false); }
    else if price_btn(a, Rect::new(bx, by, hw, 54.), &cost.to_string(), true, pearls >= cost, St::Gold) { a.try_buy(); return; }
    if a.ui.btn(&mut a.gx, Rect::new(bx + hw + 8., by, hw, 54.), &t("back"), St::Pink, 17., true) { a.click(); a.try_off(); }
}

/// 4.8: перенос прогресса на другой телефон кодом через буфер обмена (без серверов)
fn xfer(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let (bx, bw) = col(a);
    a.gx.rrect(0., 0., w, h, 0., Color::new(0., 0.02, 0.06, 0.55 * al));
    let land = a.landscape(); let (bx, bw) = if land { let ww = (w - 48.).min(560.); ((w - ww) / 2., ww) } else { (bx, bw) };
    let ph = if land { (bottom(a) - top(a)).min(360.) } else { 470. }; let y0 = ((h - ph) / 2.).max(top(a)); panel(&mut a.gx, Rect::new(bx - 8., y0, bw + 16., ph), 20., Color::new(0.03, 0.1, 0.2, 0.95), Color::new(0.37, 0.91, 1., 0.6), al);
    ui::h2c(&mut a.gx, if en { "Transfer progress" } else { "Перенос прогресса" }, w / 2., y0 + 34., 24., al, c::CYAN, hex(0xe6f8ff));
    if let Some(n) = a.xfer.clone() {
        // подтверждение: что найдено в коде
        let txt = if en { format!("Code found: {} pearls, record {}, sparks {}, skins {}, runs {}.\n\nReplace the progress on THIS phone with it? Current progress will be lost (a backup copy stays in the game folder).", n.pearls, n.best, n.chars.len(), n.skins.len(), n.runs) }
            else { format!("В коде: {} жемчуга, рекорд {}, искр {}, обликов {}, забегов {}.\n\nЗаменить им прогресс на ЭТОМ телефоне? Текущий прогресс пропадёт (резервная копия останется в папке игры).", n.pearls, n.best, n.chars.len(), n.skins.len(), n.runs) };
        a.gx.text_wrap(&txt, w / 2., y0 + 80., bw - 20., 15., 21., Color::new(1., 1., 1., 0.92 * al), 1, 0);
        let by = y0 + ph - 132.;
        if a.ui.btn(&mut a.gx, Rect::new(bx, by, bw, 54.), if en { "Replace" } else { "Заменить" }, St::Gold, 19., true) { a.click();
            if let Some(cur) = crate::platform::read_save() { let _ = std::fs::write(format!("{}/save_backup.json", crate::platform::files_dir()), cur); }
            a.g.s = n; i18n::set_en(a.g.s.set.lang == "en"); a.g.dirty = true; a.persist(); a.xfer = None;
            a.toast(if en { "Progress transferred".into() } else { "Прогресс перенесён".into() }, if en { "Welcome back!".into() } else { "С возвращением!".into() }); a.show(Scr::Title); return; }
        if a.ui.btn(&mut a.gx, Rect::new(bx, by + 62., bw, 44.), &t("back"), St::Pink, 16., true) { a.click(); a.xfer = None; }
        return;
    }
    a.gx.text_wrap(if en { "Moving to a new phone? Copy the code, send it to yourself (messenger, notes) and paste it on the new phone. The code holds all progress: pearls, sparks, skins, upgrades, pets." }
        else { "Новый телефон? Скопируй код, перешли его себе (в мессенджер, заметки) и вставь на новом телефоне. В коде весь прогресс: жемчуг, искры, облики, улучшения, питомцы." },
        w / 2., y0 + 72., bw - 20., 14.5, 20., Color::new(1., 1., 1., 0.88 * al), 1, 0);
    let by = if land { y0 + 150. } else { y0 + 210. }; let hw = if land { (bw - 8.) / 2. } else { bw };
    if a.ui.btn(&mut a.gx, Rect::new(bx, by, hw, 54.), if en { "Copy my code" } else { "Скопировать мой код" }, St::Gold, 18., true) { a.click();
        a.xfer_copy(); }
    if a.ui.btn(&mut a.gx, if land { Rect::new(bx + hw + 8., by, hw, 54.) } else { Rect::new(bx, by + 64., bw, 54.) }, if en { "Paste code from old phone" } else { "Вставить код со старого телефона" }, St::Cyan, if land { 14. } else { 16. }, true) { a.click();
        a.xfer_paste(); }
    if !a.xfer_msg.is_empty() { a.gx.text_wrap(&a.xfer_msg, w / 2., by + if land { 72. } else { 134. }, bw - 20., 13.5, 18., with_alpha(hex(0xffe08a), al), 1, 0); }
    if a.ui.btn(&mut a.gx, Rect::new(bx, y0 + ph - 60., bw, 46.), &t("back"), St::Pink, 17., true) { a.click(); a.show(Scr::Set); }
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
/// 4.8: значок «▶ примерить» на миниатюре; касание миниатюры — примерка (kind: 0 облик, 1 шлейф, 2 гибель, 3 выстрелы)
fn try_badge(a: &mut App, x: f32, y: f32, h: f32, al: f32, kind: u8, i: usize) {
    let (bx, by) = (x + 48., y + h - 13.); a.gx.circle(bx, by, 8., Color::new(1., 0.84, 0.31, 0.9 * al)); a.gx.text("▶", bx + 0.8, by + 0.5, 9., Color::new(0.05, 0.1, 0.2, al), 1, 2);
    if a.ui.tap(Rect::new(x, y, 58., h)) { a.click(); a.try_req = Some((kind, i)); }
}
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
    let tabs = [t("tabUp"), t("tabChars"), t("tabSkins"), t("tabTal"), if i18n::is_en() { "Pets".to_string() } else { "Питомцы".to_string() }]; let tw_ = (f.w - 24.) / 5.;
    for (i, l) in tabs.iter().enumerate() { let r = Rect::new(f.x + i as f32 * (tw_ + 6.), wy + 18., tw_, 40.);
        let sel = a.shop_tab as usize == i; let a0 = a.ui.alpha; if !sel { a.ui.alpha = a0 * 0.6; }
        if a.ui.btn(&mut a.gx, r, l, St::Cyan, 12.5, true) && !sel { a.click(); a.shop_tab = i as u8; a.ui.scroll_reset(1); } a.ui.alpha = a0; }
    let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0);
    // содержимое: собираем высоты
    let tab = a.shop_tab;
    let iw = f.w; let bw = 100.;
    struct It { kind: u8, i: usize, h: f32 }
    let mut items: Vec<It> = vec![];
    let dsw = |a: &App, s: &str, sw: bool| a.gx.wrap(s, iw - 24. - bw - 10. - if sw { 46. } else { 0. }, 12.5, 0).len() as f32 * 16.;
    match tab {
        0 => for i in 0..SHOP.len() { let d = i18n::shop(SHOP[i].id).1; items.push(It { kind: 0, i, h: (30. + dsw(a, &d, true) + 12.).max(64.) }); },
        1 => for i in 0..CHARS.len() { let (_, d) = i18n::chr(CHARS[i].id); let d = d + " "; let _m = 0; let d = d + &tf("healthW", &[&CHARS[i].hp.to_string()]) + " " + crate::content::char_attack(i) + ". " + &crate::abilities::ab_line(crate::abilities::ab_idx(CHARS[i].id)); items.push(It { kind: 1, i, h: (30. + dsw(a, &d, true) + 12.).max(64.) + 18. }); },
        2 => { items.push(It { kind: 11, i: 0, h: 172. }); for i in 0..SKINS.len() { items.push(It { kind: 2, i, h: 64. }); }
            items.push(It { kind: 6, i: 0, h: 34. }); for i in 0..crate::extras::TRAILS.len() { items.push(It { kind: 7, i, h: 64. }); }
            items.push(It { kind: 6, i: 1, h: 34. }); for i in 0..crate::extras::DEATHS.len() { items.push(It { kind: 8, i, h: 64. }); }
            items.push(It { kind: 6, i: 2, h: 34. }); for i in 0..crate::extras::SHOTS.len() { items.push(It { kind: 9, i, h: 64. }); } },
        4 => { if crate::extras::PETS.iter().filter(|p| a.g.s.pets.get(p.id).copied().unwrap_or(0) > 0).count() >= 2 { items.push(It { kind: 10, i: 0, h: 70. }); }
            for i in 0..crate::extras::PETS.len() { let d = crate::extras::pet_txt(i).1; items.push(It { kind: 5, i, h: (30. + dsw(a, d, true) + 30.).max(80.) }); } },
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
            1 => { let ch = &CHARS[it.i]; let own = a.g.s.chars.contains_key(ch.id); let sel = a.g.s.ch == ch.id; let (nm, d) = i18n::chr(ch.id); let d = d + &tf("healthW", &[&ch.hp.to_string()]) + " " + crate::content::char_attack(it.i) + ". " + &crate::abilities::ab_line(crate::abilities::ab_idx(ch.id));
                item_card(&mut a.gx, r, pal(ch.col), sel, al);
                { let sk = if let Some(s) = data::char_skin(ch.id) { s } else { match ch.col { c::EMER => "emerald", c::AMBER => "amber", c::FIRE => "ember", c::CORAL => "coral", c::ICE => "frost", c::GHOST => "ghost", c::CRAB => "inferno", c::DRIFT => "jade", c::GOLD => "solar", _ => "azure"  }};
                  let p = a.gx.px; let key = format!("pl_{sk}"); let (cx, cy) = (f.x + 30., y + it.h / 2.); a.gx.glow_scr(true, ch.col, cx * p, cy * p, 32. * p, 0.6 * al);
                  let ph = a.gx.spr_anim(&key).map(|an| a.g.t * 0.5 * an.freq() * std::f32::consts::TAU + it.i as f32).unwrap_or(0.);
                  crate::gfx::set_calm(0.5); a.gx.spr_screen(&key, cx * p, cy * p, -0.3, 1.0 * p, al, false, ph, false); crate::gfx::set_calm(1.); }
                a.gx.text(&nm, f.x + 58., y + 20., 16., Color::new(1., 1., 1., al), 0, 1); a.gx.text_wrap(&d, f.x + 58., y + 40., iw - 24. - bw - 10. - 46., 12.5, 16., Color::new(1., 1., 1., 0.75 * al), 0, 0);
                { let pts = a.g.s.mastery.get(ch.id).copied().unwrap_or(0); let ml = crate::extras::mastery_lvl(pts); let nx = crate::extras::mastery_next(ml);
                  let lbl = if i18n::is_en() { format!("Mastery {ml}/10") } else { format!("Мастерство {ml}/10") }; let my = y + it.h - 14.;
                  a.gx.text(&lbl, f.x + 58., my, 11.5, with_alpha(hex(0xffe08a), al), 0, 1); let k = if ml >= 10 { 1. } else { pts as f32 / nx as f32 };
                  pbar(&mut a.gx, f.x + 58. + 96., my - 3., (iw - 24. - bw - 10. - 46. - 100.).max(30.), 5., k, hex(0xffd54f), al); }
                if sel { a.ui.btn(&mut a.gx, br, &t("chosen"), St::Cyan, 15., false); } else if own { if a.ui.btn(&mut a.gx, br, &t("choose"), St::Cyan, 15., true) { a.g.pick_char(it.i); } }
                else if price_btn(a, br, &ch.cost.to_string(), true, a.g.s.pearls >= ch.cost, St::Cyan) { a.g.pick_char(it.i); } }
            2 => { let sk = &SKINS[it.i]; let own = a.g.s.skins.contains_key(sk.id); let sel = a.g.s.skin == sk.id;
                item_card(&mut a.gx, r, if sk.win { hex(0xffd54f) } else { pal(sk.pal) }, sel, al);
                // облик: живая модель искры
                let p = a.gx.px; let key = format!("pl_{}", sk.id); a.gx.glow_scr(true, sk.pal, (f.x + 30.) * p, (y + 32.) * p, 30. * p, 0.6 * al);
                let ph = a.gx.spr_anim(&key).map(|an| a.g.t * 0.5 * an.freq() * std::f32::consts::TAU + it.i as f32).unwrap_or(0.);
                crate::gfx::set_calm(0.5); a.gx.spr_screen(&key, (f.x + 30.) * p, (y + 32.) * p, -0.3, 0.75 * p, al, false, ph, false); crate::gfx::set_calm(1.);
                try_badge(a, f.x, y, it.h, al, 0, it.i);
                a.gx.text(&i18n::skin(sk.id), f.x + 58., y + 22., 16., Color::new(1., 1., 1., al), 0, 1);
                let sub = if data::live_skin(sk.id) && sk.id != "keeper" { if i18n::is_en() { "✦ Living: shimmering glow".to_string() } else { "✦ Живой: свечение переливается".to_string() } } else if sk.id == "keeper" { if i18n::is_en() { "Discover the whole bestiary".to_string() } else { "Открой весь бестиарий".to_string() } } else if sk.win { t("skinWin") } else { t("skinColor") };
                a.gx.text(&sub, f.x + 58., y + 42., 12., Color::new(1., 1., 1., 0.75 * al), 0, 0);
                if sel { a.ui.btn(&mut a.gx, br, &t("worn"), St::Cyan, 15., false); } else if own { if a.ui.btn(&mut a.gx, br, &t("wear"), St::Cyan, 15., true) { a.g.pick_skin(it.i); } }
                else if sk.win { let wl = if sk.id == "keeper" { if i18n::is_en() { "Bestiary".to_string() } else { "Бестиарий".to_string() } } else { t("winBtn") }; a.ui.btn(&mut a.gx, br, &wl, St::Gold, 15., false); }
                else if price_btn(a, br, &sk.cost.to_string(), true, a.g.s.pearls >= sk.cost, St::Cyan) { a.g.pick_skin(it.i); } }
            11 => { let en = i18n::is_en(); let acc = hex(0xffd54f); item_card(&mut a.gx, r, acc, false, al);
                a.gx.text(if en { "OUTFITS" } else { "НАРЯДЫ" }, f.x + 16., y + 20., 16., with_alpha(acc, al), 0, 2);
                let (ti, n) = crate::extras::theme_best(&a.g.s); let tn = crate::extras::theme_name(ti);
                let st = if n == 4 { if en { format!("✦ «{tn}» set complete: special glow and +1 light shard at every 10th depth") } else { format!("✦ Комплект «{tn}» собран: особое сияние и +1 осколок света на каждой 10-й глубине") } }
                    else if en { format!("Set «{tn}»: {n}/4. Skin, trail, death effect and shots of one theme give a glow and bonus shards") } else { format!("Комплект «{tn}»: {n}/4. Облик, шлейф, гибель и выстрелы одной темы — сияние и бонусные осколки") };
                a.gx.text_wrap(&st, f.x + 16., y + 40., iw - 32., 12., 15., Color::new(1., 1., 1., 0.85 * al), 0, 0);
                let gap = 8.; let sw = (iw - 32. - gap * 2.) / 3.; let cur = crate::extras::outfit_of(&a.g.s);
                for k in 0..3 { let x = f.x + 16. + k as f32 * (sw + gap); let bx_ = Rect::new(x, y + 76., sw, 54.); let o = a.g.s.outfits[k].clone(); let on = !o.is_empty() && o == cur;
                    panel(&mut a.gx, bx_, 12., Color::new(0.02, 0.08, 0.16, 0.85), if on { with_alpha(acc, 0.95) } else { Color::new(0.5, 0.8, 1., 0.35) }, al);
                    if o.is_empty() { a.gx.text(if en { "empty" } else { "пусто" }, x + sw / 2., y + 103., 13., Color::new(1., 1., 1., 0.5 * al), 1, 0); }
                    else { let v: Vec<&str> = o.split('|').collect(); let key = format!("pl_{}", v[0]); let p = a.gx.px; let tr: u8 = v.get(1).and_then(|q| q.parse().ok()).unwrap_or(0);
                        let pal_ = SKINS.iter().find(|q| q.id == v[0]).map(|q| q.pal).unwrap_or(c::CYAN);
                        for q in 1..6 { let col = crate::extras::trail_col(tr, pal_, q, a.g.t); a.gx.glow_scr(true, col, (x + sw / 2. - 14. - q as f32 * 7.) * p, (y + 103.) * p, (9. - q as f32) * p, (1. - q as f32 / 7.) * 0.8 * al); }
                        crate::gfx::set_calm(0.5); a.gx.spr_screen(&key, (x + sw / 2. + 6.) * p, (y + 103.) * p, 0., 0.85 * p, al, false, 0., false); crate::gfx::set_calm(1.);
                        if a.ui.tap(bx_) { a.click(); a.g.wear_outfit(k); } }
                    if a.ui.btn(&mut a.gx, Rect::new(x, y + 136., sw, 28.), if o.is_empty() { if en { "Save" } else { "Запомнить" } } else if en { "Overwrite" } else { "Заменить" }, St::Cyan, 12., true) {
                        a.click(); a.g.s.outfits[k] = cur.clone(); a.g.dirty = true; a.toast(if en { "Outfit saved".into() } else { "Наряд запомнен".into() }, if en { "Tap it to put it on".into() } else { "Нажми на него, чтобы надеть".into() }); } } }
            10 => { let en = i18n::is_en(); let cur = a.g.s.pet.clone();
                // 4.8.4: кого взять вторым — выбирается касанием карточки (по кругу среди своих питомцев, кроме основного)
                let owned: Vec<usize> = (0..crate::extras::PETS.len()).filter(|&k| crate::extras::PETS[k].id != cur && a.g.s.pets.get(crate::extras::PETS[k].id).copied().unwrap_or(0) > 0).collect();
                let tok = crate::extras::PETS.iter().position(|p| p.id == a.g.s.tok_pet2);
                let cand = tok.filter(|k| owned.contains(k)).or(a.pet2_pick.filter(|k| owned.contains(k))).or_else(|| owned.iter().copied().max_by_key(|&k| a.g.s.pets.get(crate::extras::PETS[k].id).copied().unwrap_or(0)));
                if owned.len() > 1 && a.ui.tap(Rect::new(f.x, y, iw - bw - 24., it.h)) { a.click(); let i0 = cand.and_then(|c| owned.iter().position(|&k| k == c)).unwrap_or(0); let nk = owned[(i0 + 1) % owned.len()];
                    a.pet2_pick = Some(nk); if !a.g.s.tok_pet2.is_empty() { a.g.s.tok_pet2 = crate::extras::PETS[nk].id.into(); a.g.dirty = true; } }
                let cand = if owned.len() > 1 { a.pet2_pick.filter(|k| owned.contains(k)).or(cand) } else { cand };
                let cand = if !a.g.s.tok_pet2.is_empty() { crate::extras::PETS.iter().position(|p| p.id == a.g.s.tok_pet2) } else { cand };
                item_card(&mut a.gx, r, hex(0xffd54f), !a.g.s.tok_pet2.is_empty(), al);
                if let Some(k) = cand { let pd = &crate::extras::PETS[k]; let p = a.gx.px; let (cx, cy) = (f.x + 34., y + it.h / 2.); a.gx.glow_scr(true, pd.col, cx * p, cy * p, 30. * p, 0.6 * al);
                    let half = a.gx.spr_half(pd.spr); crate::gfx::set_calm(0.6); a.gx.spr_screen(pd.spr, cx * p, cy * p, 0., 26. / half * p, al, false, 0., false); crate::gfx::set_calm(1.); }
                else { icon_tile(&mut a.gx, "heal", f.x + 34., y + it.h / 2., hex(0xffd54f), c::GOLD, al); }
                a.gx.text(if en { "Second pet" } else { "Второй питомец" }, f.x + 64., y + 20., 16., Color::new(1., 1., 1., al), 0, 1);
                let more = owned.len() > 1; let hint = if !more { "" } else if en { " · tap to change" } else { " · нажми, чтобы сменить" };
                let d = if !a.g.s.tok_pet2.is_empty() { let nm = cand.map(|k| crate::extras::pet_txt(k).0).unwrap_or(""); if en { format!("✓ {nm} joins your next run{hint}") } else { format!("✓ {nm} поплывёт с тобой в следующем забеге{hint}") } }
                    else if let Some(k) = cand { if en { format!("{} joins the next run as well{hint}", crate::extras::pet_txt(k).0) } else { format!("{} поплывёт вместе в следующем забеге{hint}", crate::extras::pet_txt(k).0) } } else { String::new() };
                a.gx.text_wrap(&d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * al), 0, 0);
                if a.g.s.tok_pet2.is_empty() { if let Some(k) = cand { let rdy = a.ad_ready(); if a.ui.btn(&mut a.gx, br, "▶", St::Gold, 18., rdy) { a.click(); a.ad_show("pet2", AdCb::Pet2(k)); } } }
                else { a.ui.btn(&mut a.gx, br, "✓", St::Gold, 18., false); } }
            5 => { let pd = &crate::extras::PETS[it.i]; let lvl = a.g.s.pets.get(pd.id).copied().unwrap_or(0); let act = a.g.s.pet == pd.id && lvl > 0; let (nm, d) = crate::extras::pet_txt(it.i);
                item_card(&mut a.gx, r, pal(pd.col), act, al);
                { let p = a.gx.px; let (cx, cy) = (f.x + 34., y + it.h / 2.); a.gx.glow_scr(true, pd.col, cx * p, cy * p, 32. * p, 0.6 * al);
                  let half = a.gx.spr_half(pd.spr); let ph = a.gx.spr_anim(pd.spr).map(|an| a.g.t * 0.6 * an.freq() * std::f32::consts::TAU).unwrap_or(0.);
                  crate::gfx::set_calm(0.6); a.gx.spr_screen(pd.spr, cx * p, cy * p, 0., 28. / half * p, al, false, ph, false); crate::gfx::set_calm(1.); }
                let nw = a.gx.text(&nm, f.x + 64., y + 20., 16., Color::new(1., 1., 1., al), 0, 1); if lvl > 0 { pips(&mut a.gx, f.x + 64. + nw + 8., y + 21., lvl, crate::extras::PET_MAX, al); }
                a.gx.text_wrap(d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * al), 0, 0);
                let b2 = Rect::new(br.x, br.y + 24., br.w, 34.); let b1 = Rect::new(br.x, br.y - 16., br.w, 34.);
                if lvl == 0 { if price_btn(a, br, &crate::extras::pet_cost(it.i, 0).to_string(), true, a.g.s.pearls >= crate::extras::pet_cost(it.i, 0), St::Cyan) { a.g.buy_pet(it.i); } }
                else { if a.ui.btn(&mut a.gx, b1, if act { if i18n::is_en() { "Active" } else { "С тобой" } } else if i18n::is_en() { "Take" } else { "Взять" }, if act { St::Gold } else { St::Cyan }, 13., true) { a.g.pick_pet(it.i); }
                    if lvl >= crate::extras::PET_MAX { a.ui.btn(&mut a.gx, b2, &t("max"), St::Cyan, 13., false); }
                    else { let c_ = crate::extras::pet_cost(it.i, lvl); if price_btn(a, b2, &c_.to_string(), true, a.g.s.pearls >= c_, St::Cyan) { a.g.buy_pet(it.i); } } } }
            3 => { let tl = &TALENTS[it.i]; let own = a.g.s.tal(tl.id); let open = a.g.tal_open(it.i); let (nm, d) = i18n::talent(it.i);
                let aa = if !open && !own { al * 0.6 } else { al }; let (acc, pi) = branch_col(tl.br); item_card(&mut a.gx, r, acc, own, aa); icon_tile(&mut a.gx, tal_icon(tl.id), f.x + 34., y + it.h / 2., acc, pi, aa);
                a.gx.text(&format!("{}{}", if open || own { "" } else { "✗ " }, nm), f.x + 64., y + 20., 16., Color::new(1., 1., 1., aa), 0, 1);
                a.gx.text_wrap(&d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * aa), 0, 0);
                if own { a.ui.btn(&mut a.gx, br, &t("talOwn"), St::Cyan, 15., false); } else if price_btn(a, br, &tl.cost.to_string(), true, open && a.g.s.pearls >= tl.cost, St::Cyan) { a.g.buy_tal(it.i); } }
            6 => { let en = i18n::is_en(); let s_ = match it.i { 0 => if en { "TRAILS" } else { "ШЛЕЙФЫ" }, 1 => if en { "ENEMY DEATH EFFECTS" } else { "ЭФФЕКТЫ ГИБЕЛИ ВРАГОВ" }, _ => if en { "PROJECTILE COLOR" } else { "ЦВЕТ ВЫСТРЕЛОВ" } }; let tw = a.gx.text_w(s_, 14., 2); let acc = hex(0xffd54f);
                a.gx.rrect(f.x + 8., y + 17., iw / 2. - tw / 2. - 20., 2., 1., with_alpha(acc, 0.5 * al)); a.gx.rrect(f.x + iw / 2. + tw / 2. + 12., y + 17., iw / 2. - tw / 2. - 20., 2., 1., with_alpha(acc, 0.5 * al));
                a.gx.text(s_, f.x + iw / 2., y + 18., 14., with_alpha(acc, al), 1, 2); }
            7 | 8 => { let death = it.kind == 8; try_badge(a, f.x, y, it.h, al, if death { 2 } else { 1 }, it.i); let d_ = if death { &crate::extras::DEATHS[it.i] } else { &crate::extras::TRAILS[it.i] }; let (nm, d) = if death { crate::extras::death_txt(it.i) } else { crate::extras::trail_txt(it.i) };
                let key = it.i.to_string(); let own = it.i == 0 || if death { a.g.s.deaths.contains_key(&key) } else { a.g.s.trails.contains_key(&key) }; let sel = (if death { a.g.s.death } else { a.g.s.trail }) as usize == it.i;
                item_card(&mut a.gx, r, pal(d_.col), sel, al);
                { let p = a.gx.px; let (cx, cy) = (f.x + 32., y + it.h / 2.); let tm = a.g.t;
                  if death { let ph = (tm * 0.9 + it.i as f32 * 0.37).fract(); let n = 8; for k in 0..n { let an = k as f32 / n as f32 * std::f32::consts::TAU; let rr = if it.i == 4 { 22. * (1. - ph) } else { 4. + 20. * ph };
                      let col = match it.i { 1 => [c::FIRE, c::GOLD, c::EMER, c::CYAN, c::ICE, c::AMETH, c::CORAL, c::AMBER][k], 3 | 8 => c::GOLD, 4 => c::PURP, 2 | 5 => c::ICE, 6 => c::CORAL, 7 => c::CYAN, _ => c::WHITE };
                      a.gx.glow_scr(false, col, (cx + an.cos() * rr) * p, (cy + an.sin() * rr - if it.i == 2 { ph * 8. } else { 0. }) * p, 5. * p, (1. - ph * 0.7) * al); } }
                  else { for k in 0..9 { let x = cx + 20. - k as f32 * 6.; let yy = cy + (tm * 4. - k as f32 * 0.6).sin() * 5.; let col = crate::extras::trail_col(it.i as u8, c::CYAN, k + 1, tm);
                      a.gx.glow_scr(true, col, x * p, yy * p, (11. - k as f32) * p, (1. - k as f32 / 10.) * 0.8 * al); }
                    a.gx.glow_scr(false, c::WHITE, (cx + 22.) * p, (cy + (tm * 4.).sin() * 5.) * p, 5. * p, al); } }
                a.gx.text(nm, f.x + 64., y + 20., 16., Color::new(1., 1., 1., al), 0, 1);
                a.gx.text_wrap(d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * al), 0, 0);
                if sel { a.ui.btn(&mut a.gx, br, if i18n::is_en() { "Active" } else { "Выбран" }, St::Gold, 14., false); }
                else if own { if a.ui.btn(&mut a.gx, br, if i18n::is_en() { "Use" } else { "Выбрать" }, St::Cyan, 15., true) { a.click(); a.g.buy_fx(death as u8, it.i); } }
                else if price_btn(a, br, &d_.cost.to_string(), true, a.g.s.pearls >= d_.cost, St::Cyan) { a.g.buy_fx(death as u8, it.i); } }
            9 => { try_badge(a, f.x, y, it.h, al, 3, it.i); let d_ = &crate::extras::SHOTS[it.i]; let (nm, d) = crate::extras::shot_txt(it.i); let key = it.i.to_string(); let own = it.i == 0 || a.g.s.shots.contains_key(&key); let sel = a.g.s.shot as usize == it.i;
                item_card(&mut a.gx, r, pal(d_.col), sel, al);
                { let p = a.gx.px; let (cx, cy) = (f.x + 32., y + it.h / 2.); let tm = a.g.t;
                  for k in 0..3 { let (pc, ac) = crate::extras::shot_cols(it.i as u8, k, tm).unwrap_or((c::CYAN, c::WHITE)); let x = cx - 14. + k as f32 * 14. + ((tm * 3.).fract() * 14.); let yy = cy + (k as f32 - 1.) * 4.;
                      a.gx.glow_scr(true, pc, x * p, yy * p, 10. * p, 0.7 * al); a.gx.glow_scr(false, ac, x * p, yy * p, 4.5 * p, al); } }
                a.gx.text(nm, f.x + 64., y + 20., 16., Color::new(1., 1., 1., al), 0, 1);
                a.gx.text_wrap(d, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.8 * al), 0, 0);
                if sel { a.ui.btn(&mut a.gx, br, if i18n::is_en() { "Active" } else { "Выбран" }, St::Gold, 14., false); }
                else if own { if a.ui.btn(&mut a.gx, br, if i18n::is_en() { "Use" } else { "Выбрать" }, St::Cyan, 15., true) { a.click(); a.g.buy_fx(2, it.i); } }
                else if price_btn(a, br, &d_.cost.to_string(), true, a.g.s.pearls >= d_.cost, St::Cyan) { a.g.buy_fx(2, it.i); } }
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
        let ik = ach_icon(id);
        if done { let p = gx.px; gx.glow_scr(true, c::GOLD, ix * p, iy * p, 28. * p, 0.6 * aa); gx.circle(ix, iy, 18., Color::new(0.30, 0.20, 0.04, 0.95 * aa)); gx.ring(ix, iy, 18., 2., with_alpha(pal(c::GOLD), aa));
            if let Some(tx) = gx.icon.get(ik).cloned() { gx.tex_ui(&tx, ix - 14., iy - 14., 28., 28., Color::new(1., 1., 1., aa)); } }
        else { gx.circle(ix, iy, 17., Color::new(0.05, 0.08, 0.14, 0.8 * aa)); gx.ring(ix, iy, 17., 1.5, Color::new(1., 1., 1., 0.22 * aa));
            if let Some(tx) = gx.icon.get(ik).cloned() { gx.tex_ui(&tx, ix - 12., iy - 12., 24., 24., Color::new(0.35, 0.4, 0.5, 0.55 * aa)); } }
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

/// Режимы: испытание дня, на время, без улучшений, только рывок
/// Значок награды
fn ach_icon(id: &str) -> &'static str { match id { "first" => "flare", "kill100" => "dmg", "kill500" => "reaper", "kill5k" => "supernova", "kill20k" => "tempest", "combo50" => "chain", "combo150" => "storm",
    "depth300" => "barrier", "depth500" => "speed", "deep1100" => "vortex", "endless2000" => "maelstrom", "boss1" => "hunter", "boss2" => "kraken", "boss3" => "lighthouse", "guard" => "aegis",
    "syn" => "prism", "syn3" => "choir", "lvl20" => "echo", "flare10" => "nova", "rich" => "greed", "lord" => "overcharge", _ => "multi" } }
/// Карточка существа (бестиарий): большая живая модель, описание и характеристики
fn best_card(a: &mut App, i: usize, tr: u8) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let p = a.gx.px; let tm = a.g.t;
    a.gx.fill_screen(Color::new(0.01, 0.03, 0.08, 0.78 * al), false);
    let (bx, bw) = col(a); let ch = (h * 0.78).min(640.); let cy0 = (h - ch) / 2.; let r = Rect::new(bx - 8., cy0, bw + 16., ch);
    let d = &ET[i]; let k = crate::data::K_ALL[i]; let acc = crate::tiers::tier_col(d.col, tr);
    item_card(&mut a.gx, r, pal(acc), d.boss, al);
    // модель
    let key_s = crate::render::tkey(d.key, tr); let key = key_s.as_str(); let half = a.gx.spr_half(key); let sz = (bw * 0.42).min(ch * 0.26); let kk = sz / half;
    let (mx, my) = (w / 2., cy0 + 30. + sz); a.gx.glow_scr(true, acc, mx * p, my * p, sz * 1.5 * p, 0.55 * al);
    let ph = a.gx.spr_anim(key).map(|an| tm * an.freq() * std::f32::consts::TAU).unwrap_or(0.);
    let jaw = if a.gx.spr.contains_key(&format!("{key}_body")) { 0.1 + 0.18 * (tm * 1.6).sin().max(-0.3) } else { 0. };
    if k == crate::data::K::Boss4 { // 4.5: змей — волнистая лента во всю ширину карточки
        let skey = crate::render::tkey("serp", tr); let (sw, sh) = a.gx.spr.get(&skey).map(|s| (s.tex.width(), s.tex.height())).unwrap_or((4.8, 1.)); let len = bw * 0.96; let hw = len / (sw / sh) * 0.5;
        let n = 30; let pts: Vec<(f32, f32, f32, f32)> = (0..=n).map(|q| { let u = 1. - q as f32 / n as f32; let x = w / 2. + (u - 0.5) * len; let ph = u * 7. - tm * 2.2;
            let yv = my + ph.sin() * 16. * (1. - u * 0.8); let a_ = (ph.cos() * 16. * 7. / len * (1. - u * 0.8)).atan(); (x * p, yv * p, -a_, u) }).collect();
        let (hu, hv) = a.gx.spr.get(&skey).and_then(|s| s.hinge).unwrap_or((0.884, 0.496)); let ph = hu * 7. - tm * 2.2;
        let (hx, hy) = (w / 2. + (hu - 0.5) * len, my + ph.sin() * 16. * (1. - hu * 0.8) + (hv - 0.5) * 2. * hw); let ha = -(ph.cos() * 16. * 7. / len * (1. - hu * 0.8)).atan();
        if let Some(jt) = a.gx.spr.get(&format!("{skey}_jaw")).map(|s| s.tex.clone()) { a.gx.set_mat(0); let open = 0.12 + 0.12 * (tm * 1.6).sin();
            draw_texture_ex(&jt, (hx - hu * len) * p, (hy - hv * 2. * hw) * p, Color::new(1., 1., 1., al), DrawTextureParams { dest_size: Some(vec2(len * p, 2. * hw * p)), rotation: ha + open, pivot: Some(vec2(hx * p, hy * p)), ..Default::default() }); }
        a.gx.strip_px(&skey, &pts, hw * p, false, Color::new(1., 1., 1., al), false); }
    else if jaw != 0. { let half_b = a.gx.spr_half(&format!("{key}_body")); let kb = sz / half_b; a.gx.jaw = 0.;
        let mouth = format!("{key}_mouth"); if a.gx.spr.contains_key(&mouth) { a.gx.spr_screen(&mouth, mx * p, my * p, 0., kb * p, al, false, ph, false); }
        a.gx.jrot = jaw; a.gx.spr_screen(&format!("{key}_jaw"), mx * p, my * p, 0., kb * p, al, false, ph, false); a.gx.jrot = 0.;
        a.gx.spr_screen(&format!("{key}_body"), mx * p, my * p, 0., kb * p, al, false, ph, false); }
    else { a.gx.spr_screen(key, mx * p, my * p, 0., kk * p, al, false, ph, false); }
    // имя и описание
    let mut y = my + sz + 22.;
    let nm = if tr > 0 { if d.boss { crate::tiers::boss_name(k, tr, en).unwrap_or("").to_string() } else { crate::tiers::foe_name(k, tr, en).unwrap_or("").to_string() } }
        else if d.boss { i18n::boss(d.key) } else { let n = i18n::best(d.key).0; if n.is_empty() { d.key.to_string() } else { n } };
    ui::h2c(&mut a.gx, &nm, w / 2., y, 22., al, acc, WHITE); y += 26.;
    y += a.gx.text_wrap(&i18n::best(d.key).1, w / 2., y, bw - 20., 14., 19., Color::new(1., 1., 1., 0.85 * al), 1, 0) + 14.;
    // характеристики: полоски относительно самых сильных в своей группе
    let tierk = [1., 1.6, 2.4][tr as usize];
    let (mhp, mdmg, mspd) = if d.boss { (17000., 28., 150.) } else { (100., 18., 150.) };
    let rows = [(if en { "Health" } else { "Здоровье" }, (d.hp * tierk / mhp).min(1.), hex(0xff6f91)), (if en { "Damage" } else { "Урон" }, (d.dmg * tierk / mdmg).min(1.), hex(0xffb340)),
        (if en { "Speed" } else { "Скорость" }, (d.spd / mspd).min(1.), hex(0x5fe9ff))];
    for (l, v, c_) in rows.iter() { a.gx.text(l, bx + 12., y + 6., 14., Color::new(1., 1., 1., 0.8 * al), 0, 1); pbar(&mut a.gx, bx + 110., y + 1., bw - 130., 9., v.max(0.05), *c_, al); y += 26.; }
    // где встречается
    let mut where_ = String::new();
    if d.boss { for z in 1..=30u32 { if z % 5 == 0 && crate::game::boss_at(z) == k { where_ = format!("{} {} {}", if en { "Lord of" } else { "Владыка" }, z * 100, t("m")); break; }
            if let Some((g, _)) = crate::game::Game::guardian_for(z) { if g == k { where_ = format!("{} {} {}", if en { "Guardian of" } else { "Страж" }, z * 100, t("m")); break; } } } }
    else if tr == 1 { where_ = if en { "600 m and deeper".into() } else { "600 м и глубже".into() }; } else if tr == 2 { where_ = if en { "1100 m and deeper".into() } else { "1100 м и глубже".into() }; }
    if !where_.is_empty() { a.gx.text(&where_, w / 2., y + 8., 15., with_alpha(hex(0xffe08a), al), 1, 2); }
    a.gx.text(if en { "Tap to close" } else { "Нажми, чтобы закрыть" }, w / 2., cy0 + ch - 18., 12., Color::new(1., 1., 1., 0.5 * al), 1, 0);
    if a.ui.tap_any() { a.best_sel = None; }
}
/// Колесо удачи: раз в день бесплатно, ещё 3 раза — за рекламу
fn wheel(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let p = a.gx.px; let tp = top(a);
    ui::h2c(&mut a.gx, if en { "WHEEL OF FORTUNE" } else { "КОЛЕСО УДАЧИ" }, w / 2., tp + 22., 28., al, c::GOLD, hex(0xfff2c0));
    let n = crate::extras::WHEEL.len(); let seg = std::f32::consts::TAU / n as f32; let rr = (w * 0.42).min(h * 0.28); let (cx, cy) = (w / 2., tp + 70. + rr);
    a.gx.glow_scr(true, c::GOLD, cx * p, cy * p, rr * 1.5 * p, 0.35 * al);
    let cols = [hex(0x2a7fd4), hex(0x8a3fd0), hex(0xd0a030), hex(0x2aa79b), hex(0xd04a7a), hex(0x3f6fd0), hex(0xe0b040), hex(0x7a3fb0)];
    a.gx.set_add(false);
    for k in 0..n { let a0 = a.wheel.ang + k as f32 * seg; let a1 = a0 + seg; let mut v = vec![Vertex::new(cx * p, cy * p, 0., 0., 0., with_alpha(cols[k], al))]; let mut idx = vec![];
        for q in 0..=12 { let aa = a0 + (a1 - a0) * q as f32 / 12.; let c2 = Color::new(cols[k].r * 0.75, cols[k].g * 0.75, cols[k].b * 0.75, al); v.push(Vertex::new((cx + aa.cos() * rr) * p, (cy + aa.sin() * rr) * p, 0., 0., 0., c2)); if q > 0 { idx.extend_from_slice(&[0, q as u16, q as u16 + 1]); } }
        draw_mesh(&Mesh { vertices: v, indices: idx, texture: None });
        let am = a0 + seg / 2.; let (lx, ly) = (cx + am.cos() * rr * 0.64, cy + am.sin() * rr * 0.64); let (ty, _, _) = crate::extras::WHEEL[k];
        if ty == 0 { pearl(&mut a.gx, lx, ly - 11., 6., al); } a.gx.text(&crate::extras::wheel_label(k), lx, ly + if ty == 0 { 6. } else { 0. }, if ty == 0 { 17. } else { 12. }, Color::new(1., 1., 1., al), 1, 2); }
    for k in 0..n { let aa = a.wheel.ang + k as f32 * seg; draw_line(cx * p, cy * p, (cx + aa.cos() * rr) * p, (cy + aa.sin() * rr) * p, 2. * p, Color::new(1., 1., 1., 0.35 * al)); }
    a.gx.ring(cx, cy, rr, 4., with_alpha(hex(0xffd54f), al)); a.gx.circle(cx, cy, rr * 0.16, with_alpha(hex(0x1a1030), al)); a.gx.ring(cx, cy, rr * 0.16, 3., with_alpha(hex(0xffd54f), al));
    // стрелка сверху
    a.gx.set_add(false); let (ax, ay) = (cx, cy - rr - 6.); draw_triangle(vec2((ax - 14.) * p, (ay - 18.) * p), vec2((ax + 14.) * p, (ay - 18.) * p), vec2(ax * p, (ay + 12.) * p), with_alpha(hex(0xff4f6f), al));
    let mut y = cy + rr + 30.;
    if a.wheel.shown > 0. { let (ty, nn, _) = crate::extras::WHEEL[a.wheel.prize]; let s_ = match ty { 0 => format!("+{nn} {}", t("pearlsGen")), 1 => if en { "An upgrade for the next run!".into() } else { "Улучшение на старте следующего забега!".into() }, _ => if en { "+1 reroll next run!".into() } else { "+1 перевыбор в следующем забеге!".into() } };
        ui::h2c(&mut a.gx, &s_, w / 2., y, 22., al, c::GOLD, hex(0xfff2c0)); }
    y += 34.; let (bx, bw) = col(a); let d = &a.g.s.daily; let free = d.wheel == 0; let ads_left = crate::extras::WHEEL_AD_MAX.saturating_sub(d.wheel_ad); let busy = a.wheel.spin > 0.;
    if free { if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 60.), if en { "Spin — free" } else { "Крутить бесплатно" }, St::Gold, 20., !busy) { a.click(); a.g.s.daily.wheel = 1; a.g.dirty = true; a.wheel_start(); } }
    else { let ready = a.ad_ready() && ads_left > 0; let l = if ads_left == 0 { if en { "Come back tomorrow".to_string() } else { "Приходи завтра".to_string() } } else { format!("▶ {} ({ads_left})", if en { "Spin again" } else { "Ещё раз" }) };
        if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, 60.), &l, St::Gold, 19., ready && !busy) { a.click(); a.ad_show("wheel", AdCb::Wheel); } }
    y += 70.; let _ = y;
    let by = bottom(a) - 56.; if a.ui.btn(&mut a.gx, Rect::new(bx, by, bw, 56.), &t("back"), St::Cyan, 20., !busy) { a.click(); a.show(Scr::Title); }
}
/// Карта океана: регионы, открываются осколками света (дают владыки)
fn ocean_map(a: &mut App) {
    let (w, h) = (a.gx.w, a.gx.h); let al = a.ui.alpha; let en = i18n::is_en(); let p = a.gx.px; let tp = top(a); let tm = a.g.t;
    ui::h2c(&mut a.gx, if en { "OCEAN MAP" } else { "КАРТА ОКЕАНА" }, w / 2., tp + 22., 28., al, c::ICE, hex(0xe6f8ff));
    let sh = format!("✦ {} {}", a.g.s.shards, if en { "light shards" } else { "осколков света" }); a.gx.text(&sh, w / 2., tp + 52., 15., with_alpha(hex(0xffe08a), al), 1, 2);
    // 4.8.1: в горизонтали карта слева, описание и кнопки справа (раньше всё наезжало на «Назад»)
    let land = a.landscape(); let (cbx, cbw) = col(a);
    let (bx, bw) = if land { let mw = (w * 0.42).min(340.); (w * 0.27 - mw / 2., mw) } else { (cbx, cbw) };
    let (dbx, dbw) = if land { let dw = (w * 0.4).min(320.); (w * 0.73 - dw / 2., dw) } else { (cbx, cbw) }; let dcx = dbx + dbw / 2.;
    let my0 = tp + 72.; let mh = if land { (bottom(a) - my0 - 30.).max(120.) } else { (h * 0.45).min(bw * 1.15) }; let rects: Vec<(f32, f32)> = crate::extras::REGIONS.iter().map(|r| (bx + r.pos.0 * bw, my0 + r.pos.1 * mh)).collect();
    // фон карты
    ui::rrect_grad(&mut a.gx, bx - 6., my0 - 6., bw + 12., mh + 12., 18., Color::new(0.03, 0.14, 0.26, 0.85 * al), Color::new(0.02, 0.05, 0.14, 0.9 * al));
    for i in 1..rects.len() { let (x0, y0) = rects[0]; let (x1, y1) = rects[i]; gx_dash(&mut a.gx, x0, y0, x1, y1, Color::new(0.7, 0.9, 1., 0.25 * al)); }
    let sel = a.g.s.region as usize;
    for (i, &(x, y)) in rects.iter().enumerate() { let r = &crate::extras::REGIONS[i]; let open = i == 0 || a.g.s.regions.contains_key(&i.to_string()); let col = hex(r.col);
        let pc = match i { 1 => c::CORAL, 2 => c::ICE, 3 => c::FIRE, _ => c::CYAN };
        a.gx.glow_scr(true, pc, x * p, y * p, if i == sel { 70. } else { 46. } * p, if open { 0.55 + 0.15 * (tm * 2. + i as f32).sin() } else { 0.15 } * al);
        a.gx.circle(x, y, 24., Color::new(col.r * 0.25, col.g * 0.25, col.b * 0.3, 0.95 * al)); a.gx.ring(x, y, 24., if i == sel { 4. } else { 2. }, with_alpha(if open { col } else { hex(0x667788) }, al));
        if !open { a.gx.text(&format!("✦{}", r.cost), x, y, 13., with_alpha(hex(0xffe08a), al), 1, 2); } else { a.gx.circle(x, y, 7., with_alpha(col, al)); }
        a.gx.text(crate::extras::region_txt(i).0, x, y + 38., 13., Color::new(1., 1., 1., if open { al } else { 0.6 * al }), 1, 2);
        if a.ui.tap(Rect::new(x - 40., y - 40., 80., 90.)) { a.click(); a.map_pick = i as u8; } }
    // описание выбранного на карте
    let pk = a.map_pick as usize; let r = &crate::extras::REGIONS[pk]; let open = pk == 0 || a.g.s.regions.contains_key(&pk.to_string());
    let mut y = if land { my0 + 10. } else { my0 + mh + 22. }; ui::h2c(&mut a.gx, crate::extras::region_txt(pk).0, dcx, y, 22., al, c::ICE, hex(r.col)); y += 24.;
    y += a.gx.text_wrap(crate::extras::region_txt(pk).1, dcx, y, dbw - 10., 14., 19., Color::new(1., 1., 1., 0.85 * al), 1, 0) + 12.;
    { let hz = if r.hazard > 0 { crate::extras::hazard_txt(r.hazard) } else if en { "all hazards" } else { "все опасности" };
      let l = hz.to_string(); a.gx.text(&l, dcx, y, 13., with_alpha(hex(0xffe08a), 0.9 * al), 1, 0); y += 26.; }
    if open { let chosen = sel == pk; if a.ui.btn(&mut a.gx, Rect::new(dbx, y, dbw, 54.), if chosen { if en { "Selected" } else { "Выбран" } } else if en { "Dive here" } else { "Нырять здесь" }, St::Gold, 19., !chosen) { a.click(); a.g.s.region = pk as u8; a.g.dirty = true; } }
    else { let ok = a.g.s.shards >= r.cost; if a.ui.btn(&mut a.gx, Rect::new(dbx, y, dbw, 54.), &format!("{} ✦{}", if en { "Unlock for" } else { "Открыть за" }, r.cost), St::Gold, 18., ok) { a.click(); a.g.s.shards -= r.cost; a.g.s.regions.insert(pk.to_string(), 1); a.g.s.region = pk as u8; a.g.dirty = true; a.au.play(crate::game::Sfx::Ach); } }
    let _ = y; let by = bottom(a) - 56.; if a.ui.btn(&mut a.gx, Rect::new(dbx, by, dbw, 56.), &t("back"), St::Cyan, 20., true) { a.click(); a.show(Scr::Title); }
    if !open && a.g.s.shards < r.cost { a.gx.text(if en { "Shards are earned by defeating lords" } else { "Осколки дают владыки: 1 за каждого, 3 за Сердце Бездны" }, dcx, by - 16., 12., Color::new(1., 1., 1., 0.6 * al), 1, 0); }
}
fn gx_dash(gx: &mut Gfx, x0: f32, y0: f32, x1: f32, y1: f32, c_: Color) { let p = gx.px; let n = 14; for i in 0..n { if i % 2 == 1 { continue; } let (a, b) = (i as f32 / n as f32, (i + 1) as f32 / n as f32);
    draw_line((x0 + (x1 - x0) * a) * p, (y0 + (y1 - y0) * a) * p, (x0 + (x1 - x0) * b) * p, (y0 + (y1 - y0) * b) * p, 2. * p, c_); } }
fn modes(a: &mut App) {
    let al = a.ui.alpha; let en = i18n::is_en();
    let (f, back) = list_frame(a, if en { "MODES" } else { "РЕЖИМЫ" }, 0.);
    if back { a.click(); a.show(Scr::Title); return; }
    let muts = crate::flow::daily_muts(); let mn: Vec<String> = muts.iter().map(|&i| i18n::mutator(data::MUTS[i]).0).collect(); let d = a.g.s.daily.clone();
    let rec = |k: &str| a.g.s.mode_best.get(k).copied().unwrap_or(0) as u32 * 100;
    let items: [(RunMode, &str, String, String, Color, &str); 4] = [
        (RunMode::Daily, "flare", if en { "Daily challenge".into() } else { "Испытание дня".into() },
            format!("{} · {}{}", mn.join(" + "), if en { "pearls ×2" } else { "жемчуг ×2" }, if d.ch_best > 0 { format!(" · {} {} {}", t("best"), d.ch_best, t("m")) } else { String::new() }), hex(0xffd54f), "daily"),
        (RunMode::Time, "rate", if en { "Time attack".into() } else { "На время".into() },
            if en { format!("10 minutes, zones twice as fast — dive as deep as you can. Best: {} m", rec("time")) } else { format!("10 минут, зоны вдвое быстрее — нырни как можно глубже. Лучшее: {} м", rec("time")) }, hex(0x5fe9ff), "time"),
        (RunMode::NoUp, "dmg", if en { "No upgrades".into() } else { "Без улучшений".into() },
            if en { format!("No cards: each level heals and makes you stronger. Best: {} m", rec("noup")) } else { format!("Никаких карт: каждый уровень лечит и усиливает. Лучшее: {} м", rec("noup")) }, hex(0xff7a5c), "noup"),
        (RunMode::Dash, "dash", if en { "Dash only".into() } else { "Только рывок".into() },
            if en { format!("You can't shoot — dash through foes, it recharges fast and hits hard. Best: {} m", rec("dash")) } else { format!("Стрелять нельзя — тарань врагов рывком, он быстрый и мощный. Лучшее: {} м", rec("dash")) }, hex(0xc59bff), "dash"),
    ];
    let iw = f.w; let bw = 96.;
    // 4.5: список прокручивается (в горизонтальном режиме не помещался)
    let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0); let off = a.ui.scroll(6, area, a.modes_h, get_frame_time()); a.ui.clip_on(&a.gx, area);
    let mut y = f.y0 + 4. - off;
    for (m, icon, nm, desc, acc, _k) in items.iter() {
        let dh = a.gx.wrap(desc, iw - 76. - bw - 10., 12.5, 0).len() as f32 * 16.; let h = (34. + dh + 12.).max(74.);
        let r = Rect::new(f.x, y, iw, h); item_card(&mut a.gx, r, *acc, false, al);
        let pc = if *m == RunMode::Daily { c::GOLD } else { c::CYAN }; icon_tile(&mut a.gx, icon, f.x + 34., y + h / 2., *acc, pc, al);
        a.gx.text(nm, f.x + 64., y + 20., 17., Color::new(1., 1., 1., al), 0, 2);
        a.gx.text_wrap(desc, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.82 * al), 0, 0);
        let br = Rect::new(f.x + iw - 12. - bw, y + h / 2. - 22., bw, 44.);
        if a.ui.btn(&mut a.gx, br, if en { "Play" } else { "Играть" }, St::Gold, 16., true) { a.click(); a.ui.clip_off(); a.start_run(*m); return; }
        y += h + 10.;
    }
    // ☠ Кошмар: переключатель для обычных забегов (после первой победы)
    { let won = a.g.s.wins > 0; let on = a.g.s.set.hard && won; let acc = hex(0xff4d5e);
      let desc = if !won { if en { "Unlocks after your first victory (3000 m). Foes are 30% tougher, hit 25% harder and there are 15% more of them — pearls ×1.5.".to_string() } else { "Откроется после первой победы (3000 м). Враги на 30% крепче, бьют на 25% сильнее, их на 15% больше — жемчуг ×1,5.".to_string() } }
          else if en { format!("For normal runs. Foes are 30% tougher, hit 25% harder and there are 15% more of them — pearls ×1.5. Now: {}", if on { "ON" } else { "off" }) }
          else { format!("Для обычных забегов. Враги на 30% крепче, бьют на 25% сильнее, их на 15% больше — жемчуг ×1,5. Сейчас: {}", if on { "ВКЛ" } else { "выкл" }) };
      let dh = a.gx.wrap(&desc, iw - 76. - bw - 10., 12.5, 0).len() as f32 * 16.; let h = (34. + dh + 12.).max(74.);
      let r = Rect::new(f.x, y, iw, h); item_card(&mut a.gx, r, acc, on, if won { al } else { al * 0.6 }); icon_tile(&mut a.gx, "rage", f.x + 34., y + h / 2., acc, c::FIRE, al);
      a.gx.text(if en { "☠ Nightmare" } else { "☠ Кошмар" }, f.x + 64., y + 20., 17., Color::new(1., 1., 1., al), 0, 2);
      a.gx.text_wrap(&desc, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.82 * al), 0, 0);
      let br = Rect::new(f.x + iw - 12. - bw, y + h / 2. - 22., bw, 44.);
      if a.ui.btn(&mut a.gx, br, if on { if en { "Turn off" } else { "Выключить" } } else if en { "Turn on" } else { "Включить" }, if on { St::Pink } else { St::Gold }, 15., won) { a.click(); a.g.s.set.hard = !on; a.g.dirty = true; }
      y += h + 10.; }
    // Уровни Бездны: открываются победой над Сердцем Бездны
    { let mx = a.g.s.abyss_max; let sel = a.g.s.abyss_sel.min(mx); let acc = hex(0xc77dff);
      let desc = if mx == 0 { if en { "Defeat the Heart of the Abyss (3000 m) to unlock. Each level adds a curse, pearls +10% per level.".to_string() } else { "Победи Сердце Бездны (3000 м), чтобы открыть. Каждый уровень добавляет проклятие, жемчуг +10% за уровень.".to_string() } }
          else if sel == 0 { if en { format!("Unlocked: {mx}/20. Choose a level — curses stack.") } else { format!("Открыто: {mx}/20. Выбери уровень — проклятия складываются.") } }
          else { format!("{} {} · {}: {} · {} +{}%", if en { "Level" } else { "Уровень" }, sel, if en { "new curse" } else { "новое" }, crate::extras::abyss_txt(sel), t("pearlsGen"), sel as u32 * 10) };
      let dh = a.gx.wrap(&desc, iw - 76. - bw - 10., 12.5, 0).len() as f32 * 16.; let h = (34. + dh + 50.).max(110.);
      let r = Rect::new(f.x, y, iw, h); item_card(&mut a.gx, r, acc, false, if mx == 0 { al * 0.6 } else { al }); icon_tile(&mut a.gx, "kraken", f.x + 34., y + 40., acc, c::AMETH, al);
      a.gx.text(if en { "Abyss levels" } else { "Уровни Бездны" }, f.x + 64., y + 20., 17., Color::new(1., 1., 1., al), 0, 2);
      a.gx.text_wrap(&desc, f.x + 64., y + 40., iw - 76. - bw - 10., 12.5, 16., Color::new(1., 1., 1., 0.82 * al), 0, 0);
      if mx > 0 { let by = y + h - 46.; let l = if sel == 0 { if en { "Off".to_string() } else { "Выкл".to_string() } } else { format!("{sel}") };
          if a.ui.btn(&mut a.gx, Rect::new(f.x + 64., by, 44., 38.), "‹", St::Cyan, 20., sel > 0) { a.click(); a.g.s.abyss_sel = sel - 1; a.g.dirty = true; }
          a.gx.text(&l, f.x + 64. + 74., by + 19., 18., with_alpha(acc, al), 1, 2);
          if a.ui.btn(&mut a.gx, Rect::new(f.x + 64. + 104., by, 44., 38.), "›", St::Cyan, 20., sel < mx) { a.click(); a.g.s.abyss_sel = sel + 1; a.g.dirty = true; }
          let br = Rect::new(f.x + iw - 12. - bw, y + h / 2. - 22., bw, 44.);
          if a.ui.btn(&mut a.gx, br, if en { "Play" } else { "Играть" }, St::Gold, 16., true) { a.click(); a.ui.clip_off(); a.start_run(RunMode::Normal); return; } }
      y += h + 10.; }
    a.modes_h = y + off - f.y0; a.ui.clip_off();
}
fn quests(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    let (f, back) = list_frame(a, &t("questsTitle"), 30.);
    if back { a.click(); a.show(Scr::Title); return; }
    let sk = a.g.s.daily.streak.max(1);
    let line = if i18n::is_en() { format!("Login streak: day {sk} · tomorrow +{} pearls", 15 * (sk + 1).min(7)) } else { format!("Вход подряд: день {sk} · завтра +{} жемчуга", 15 * (sk + 1).min(7)) };
    a.gx.text(&line, w / 2., tp + 48., 14., Color::new(1., 1., 1., 0.75 * al), 1, 0);
    // 4.8.1: список заданий прокручивается — в горизонтали третье задание наезжало на «Назад»
    let nq = a.g.s.daily.quests.len(); let area = Rect::new(f.x - 4., f.y0, f.w + 8., f.y1 - f.y0); let off = a.ui.scroll(7, area, nq as f32 * 81., get_frame_time()); a.ui.clip_on(&a.gx, area);
    let mut y = f.y0 - off; let iw = f.w; let bw = 100.;
    for k in 0..nq { let q = a.g.s.daily.quests[k].clone(); let h = 72.; let r = Rect::new(f.x, y, iw, h);
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
    a.ui.clip_off();
}

fn best(a: &mut App) {
    let sm = small(a); let tp = top(a); let _ = (sm, tp); let _gh = a.gx.h;
    let al = a.ui.alpha; let w = a.gx.w;
    if let Some((i, tr)) = a.best_sel { let (_f, back) = list_frame(a, &t("bestT"), 30.); if back { a.best_sel = None; } else { best_card(a, i, tr); } return; }
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
    // 4.7: бестиарий-коллекция — за каждые 5 открытых существ 60 жемчуга, за весь — облик «Хранитель глубин»
    { let got = (n / 5) as u32; if got > a.g.s.best_claim { let r = (got - a.g.s.best_claim) * 60; a.g.s.best_claim = got; a.g.s.pearls += r; a.g.dirty = true; a.au.play(crate::game::Sfx::Ach);
            a.toast(if en { "Bestiary".into() } else { "Бестиарий".into() }, if en { format!("+{r} pearls for new creatures") } else { format!("+{r} жемчуга за новых существ") }); }
      if n >= keys.len() && !a.g.s.skins.contains_key("keeper") { a.g.s.skins.insert("keeper".into(), 1); a.g.dirty = true; a.au.play(crate::game::Sfx::Ach);
            a.toast(if en { "Bestiary complete!".into() } else { "Бестиарий собран!".into() }, if en { "Skin: Keeper of the Deep".into() } else { "Облик «Хранитель глубин»".into() }); }
      let nxt = ((n / 5) + 1) * 5; let l = if n >= keys.len() { if en { "All creatures found — the Keeper skin is yours".to_string() } else { "Все существа найдены — облик «Хранитель глубин» твой".to_string() } }
          else if en { format!("Next reward at {}: +60 pearls · all {}: Keeper skin", nxt.min(keys.len()), keys.len()) } else { format!("Награда на {}: +60 жемчуга · все {}: облик «Хранитель»", nxt.min(keys.len()), keys.len()) };
      a.gx.text(&l, w / 2., tp + 66., 12., with_alpha(hex(0xffe08a), 0.9 * al), 1, 0); }
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
        if ok && r.y >= f.y0 - 2. && r.y + r.h <= f.y1 + 2. && a.ui.tap(r) { a.click(); a.best_sel = Some((i, tr)); a.ui.lock = 0.25; }
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
        (format!("{orient_l}: {orient}"), 8), (format!("{}: {}", if i18n::is_en() { "Reminders" } else { "Напоминания" }, on_off(s.notify)), 10), (format!("{}: {}", if i18n::is_en() { "Glow" } else { "Подсветка" }, on_off(s.fx)), 9), (format!("{}: {}", t("lang"), if s.lang == "en" { "English" } else { "Русский" }), 6), (format!("{}: {}", t("fps"), s.fps), 7) ];
    let mut rows = rows; rows.push((if i18n::is_en() { "Transfer progress".to_string() } else { "Перенос прогресса".to_string() }, 11));
    // 4.8.1: настройки помещаются между верхом и баннером: в вертикали — две колонки, высота кнопок по месту
    let (bx, bw) = col(a); let gap = if sm { 6. } else { 8. }; let avail = bottom(a) - tp;
    let ncol = 2;
    let cw = if ncol == 1 { bw } else if land { ((w - 40.) / 2.).min(300.) } else { ((w - 32. - a.safe[2] - a.safe[3]) / 2. - 4.).min(210.) };
    let x0 = if ncol == 1 { bx } else { (w - cw * 2. - 8.) / 2. }; let fs = if ncol == 2 && !land { 14. } else { 17. };
    let nrow = (rows.len() + ncol - 1) / ncol; let bh = ((avail - 40. - 12. - nrow as f32 * gap) / (nrow as f32 + 1.)).clamp(36., 52.);
    let total = 40. + nrow as f32 * (bh + gap) + 8. + bh;
    let mut y = (tp + (avail - total) / 2.).max(tp);
    h2(&mut a.gx, &t("setTitle"), w / 2., y + 14., if land { 21. } else { 28. }, al); y += 40.;
    let mut act = None;
    for (k, (l, id)) in rows.iter().enumerate() { let (cx, cy) = (x0 + (k % ncol) as f32 * (cw + 8.), y + (k / ncol) as f32 * (bh + gap));
        if a.ui.btn(&mut a.gx, Rect::new(cx, cy, cw, bh), l, St::Cyan, fs, true) { act = Some(*id); } }
    y += nrow as f32 * (bh + gap) + 4.;
    if a.ui.btn(&mut a.gx, Rect::new(bx, y, bw, bh), &t("back"), St::Pink, 18., true) { a.click(); let b = a.back_to; a.show(b); return; }
    if act == Some(11) { a.click(); a.xfer = None; a.xfer_msg.clear(); a.show(Scr::Xfer); return; }
    if let Some(id) = act { a.click(); let s = &mut a.g.s.set;
        // громкость по кругу: 100 → 80 → 60 → 40 → 20 → выкл → 100
        match id { 0 => { s.vsfx = vol_next(s.sound, s.vsfx); s.sound = s.vsfx > 0; } 1 => { s.vmus = vol_next(s.music, s.vmus); s.music = s.vmus > 0; } 2 => { s.vibro = !s.vibro; if s.vibro { crate::platform::vibrate(30); } },
            3 => s.quality = match s.quality.as_str() { "auto" => "high".into(), "high" => "low".into(), _ => "auto".into() }, 4 => s.nums = !s.nums, 5 => s.shake = !s.shake,
            6 => { s.lang = if s.lang == "en" { "ru".into() } else { "en".into() }; i18n::set_en(s.lang == "en"); }, 7 => s.fps = if s.fps == 120 { 60 } else { 120 },
            9 => { s.fx = !s.fx; a.glow_auto_off = false; a.glow_slow = 0.; } 10 => { s.notify = !s.notify; if s.notify { crate::platform::ask_notify(); } crate::extras::sync_reminders(&a.g.s); } _ => s.orient = (s.orient + 1) % 3 }
        a.g.dirty = true; a.persist(); }
}
