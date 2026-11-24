//! Игровой интерфейс поверх мира: полоски, счёт, комбо, босс, стрелки, баннер, кнопки, джойстик, обучение,
//! а также заставка-интро, финал истории и всплывающие сообщения.
use crate::app::*;
use crate::data::{c, cfg, ET, K, PAL_HEX};
use crate::game::*;
use crate::gfx::*;
use crate::i18n::{self, t, tf};
use crate::ui::{self, with_alpha};
use macroquad::prelude::*;

fn pal(i: u8) -> Color { hex(PAL_HEX[i as usize]) }
fn ease_out(t: f32) -> f32 { 1. - (1. - t).powi(3) }
fn clamp01(v: f32) -> f32 { v.clamp(0., 1.) }

pub struct HudRects { pub pause: Rect, pub mute: Rect, pub dash: (f32, f32, f32), pub flare: (f32, f32, f32) }
pub fn rects(a: &App) -> HudRects {
    let (w, h) = (a.gx.w, a.gx.h); let (st, sb, sr) = (a.safe[0], a.safe[1], a.safe[3]);
    HudRects { pause: Rect::new(w - 10. - sr - 46., 10. + st, 46., 46.), mute: Rect::new(w - 64. - sr - 46., 10. + st, 46., 46.),
        dash: (w - 16. - sr - 44., h - 26. - sb - 44., 44.), flare: (w - 118. - sr - 36., h - 36. - sb - 36., 36.) }
}

/// Ввод в забеге: кнопки срабатывают сразу при касании; остальные касания — плавающий джойстик
pub fn input(a: &mut App) {
    let r = rects(a);
    let circ = |c: (f32, f32, f32)| Rect::new(c.0 - c.2 - 6., c.1 - c.2 - 6., c.2 * 2. + 12., c.2 * 2. + 12.);
    if a.ui.press(r.pause) || a.ui.keys_pause { a.click(); a.pause(); return; }
    if a.ui.press(r.mute) { let m = !a.g.s.set.sound && !a.g.s.set.music; a.g.s.set.sound = m; a.g.s.set.music = m; a.g.dirty = true; a.click(); }
    if a.ui.press(circ(r.dash)) || a.ui.keys_dash { a.g.dash_q = true; }
    if a.ui.press(circ(r.flare)) || a.ui.keys_flare { a.g.flare_q = true; }
    // джойстик
    let j = &mut a.joy;
    if j.id.is_none() { if let Some(d) = a.ui.downs.iter_mut().find(|d| !d.used) { d.used = true; j.id = Some(d.id); j.ox = d.x; j.oy = d.y; j.jx = 0.; j.jy = 0.; } }
    if let Some(id) = j.id {
        match a.ui.ptrs.iter().find(|p| p.id == id) {
            Some(p) => { let (mut dx, mut dy) = (p.x - j.ox, p.y - j.oy); let d = (dx * dx + dy * dy).sqrt(); let rr = cfg::JOY_R;
                if d > rr { j.ox = p.x - dx / d * rr; j.oy = p.y - dy / d * rr; dx = dx / d * rr; dy = dy / d * rr; } // база «плывёт» за пальцем
                if d < 5. { j.jx = 0.; j.jy = 0.; } else { j.jx = dx / rr; j.jy = dy / rr; if d / rr > 0.98 { let l = (dx * dx + dy * dy).sqrt(); j.jx = dx / l; j.jy = dy / l; } } }
            None => { j.id = None; j.jx = 0.; j.jy = 0.; }
        }
    }
    let (kx, ky) = (a.ui.kx, a.ui.ky); if a.bot { return; }
    if kx != 0. || ky != 0. { let l = (kx * kx + ky * ky).sqrt(); a.g.jx = kx / l; a.g.jy = ky / l; a.g.touch = false; } else { a.g.jx = a.joy.jx; a.g.jy = a.joy.jy; if a.joy.id.is_some() { a.g.touch = true; } }
}

fn arrow(gx: &mut Gfx, x: f32, y: f32, a: f32, col: Color) {
    let p = gx.px; let (ca, sa) = (a.cos(), a.sin()); let pt = |lx: f32, ly: f32| vec2((x + lx * ca - ly * sa) * p, (y + lx * sa + ly * ca) * p);
    gx.set_add(false); draw_triangle(pt(16., 0.), pt(-10., -12.), pt(-4., 0.), col); draw_triangle(pt(16., 0.), pt(-4., 0.), pt(-10., 12.), col);
}

pub fn hud(a: &mut App) {
    let st = a.g.state;
    if !matches!(st, State::Play | State::Pause | State::LevelUp) { return; }
    let (w, h) = (a.gx.w, a.gx.h); let top = a.safe[0] + 8.; let l = a.safe[2] + 12.; let tm = a.g.t;
    let gx = &mut a.gx; let g = &a.g;
    // опыт
    gx.rect(0., a.safe[0], w, 5., Color::new(1., 1., 1., 0.08)); gx.rect(0., a.safe[0], w * (g.p.xp / g.p.xp_next).min(1.), 5., pal(c::ICE));
    // здоровье
    let hw = 156f32.min(w * 0.38); let hp = (g.p.hp / g.p.max_hp).max(0.);
    // стеклянная плашка под левым блоком — всё читается на любом дне
    { let ph = if g.boss < 0 { 88. } else { 52. }; crate::ui::rrect_grad(gx, l - 7., top + 1., hw + 14., ph, 12., Color::new(0.02, 0.06, 0.14, 0.42), Color::new(0.02, 0.04, 0.10, 0.22)); }
    gx.rrect(l, top + 8., hw, 15., 7., Color::new(10. / 255., 20. / 255., 40. / 255., 0.7)); gx.rrect_line(l, top + 8., hw, 15., 7., 1.5, Color::new(1., 120. / 255., 150. / 255., 0.6));
    if hp > 0. { gx.rrect(l + 2., top + 10., ((hw - 4.) * hp).max(6.), 11., 5., hex(if hp < 0.3 { 0xff3b5c } else { 0xff6f91 })); }
    gx.text(&format!("{} / {}", g.p.hp.ceil().max(0.), g.p.max_hp), l + hw / 2., top + 16., 11., WHITE, 1, 1);
    let lvs = format!("{} {}", t("lv"), g.p.level); let w0 = gx.text(&lvs, l, top + 38., 14., pal(c::GOLD), 0, 1);
    if g.level_pending > 0 && st == State::Play { gx.text(&format!(" +{}", g.level_pending), l + w0, top + 38., 13., with_alpha(pal(c::GOLD), 0.75 + 0.25 * (tm * 6.).sin()), 0, 1); }
    gx.text(&format!("{} {}", g.zone * 100, t("m")), l + 52., top + 38., 14., hex(0x8fd8ff), 0, 1);
    if g.endless { gx.text("∞", l + 104., top + 38., 13., pal(c::GOLD), 0, 1); }
    if g.boss < 0 {
        gx.rect(l, top + 49., hw, 3., Color::new(1., 1., 1., 0.1)); gx.rect(l, top + 49., hw * (g.zone_t / cfg::ZONE_TIME).min(1.), 3., hex(0x8fd8ff));
        let zl = format!("{}{}", if g.hard { "☠ " } else if g.daily { "☀ " } else { "" }, i18n::zone((g.zone as usize).saturating_sub(1).min(14)).to_uppercase());
        gx.text(&zl, l, top + 64., 11., Color::new(200. / 255., 232. / 255., 245. / 255., 0.85), 0, 1);
        if g.boss_clear_t <= 0. { let rem = (cfg::ZONE_TIME * if g.mutf("rush") { 0.5 } else { 1. } - g.zone_t).ceil().max(0.);
            gx.text(&tf("nextDepth", &[&((g.zone + 1) * 100).to_string(), &(rem as i32).to_string()]), l, top + 79., 11., Color::new(143. / 255., 216. / 255., 1., 0.9), 0, 1); }
    }
    // реликвии — ряд значков под левым блоком
    if !g.relics.is_empty() { let y0 = top + if g.boss < 0 { 96. } else { 60. }; let p = gx.px;
        for (k, &r) in g.relics.iter().enumerate() { let x = l + 11. + (k % 8) as f32 * 24.; let y = y0 + 11. + (k / 8) as f32 * 24.; let d = &crate::content::RELICS[r as usize];
            gx.glow_scr(true, d.col, x * p, y * p, 16. * p, 0.35); gx.circle(x, y, 10.5, Color::new(0.08, 0.05, 0.14, 0.85)); gx.ring(x, y, 10.5, 1.2, Color::new(1., 0.8, 0.35, 0.85));
            if let Some(tx) = gx.icon.get(d.icon).cloned() { gx.tex_ui(&tx, x - 8., y - 8., 16., 16., WHITE); } } }
    // счёт и комбо
    let cx = w / 2. + 20.; let sc = i18n::fmt_num(g.score as i64);
    let ss = (26. * (120. / gx.text_w(&sc, 26., 2).max(1.)).min(1.)).max(15.); gx.text(&sc, cx, top + 21.5, ss, Color::new(63. / 255., 240. / 255., 1., 0.25), 1, 2); gx.text(&sc, cx, top + 20., ss, WHITE, 1, 2);
    if g.combo >= 2 { let k = g.combo_t / 2.6; let pop = 1. + (g.combo_t - 2.4).max(0.) * 2.;
        gx.text(&format!("×{:.1}", g.mult), cx - 38., top + 47., (17. * pop).round(), pal(c::GOLD), 1, 2);
        gx.text(&format!("{} {}", t("comboW"), g.combo), cx + 26., top + 47., 12., Color::new(1., 1., 1., 0.85), 1, 1);
        gx.rect(cx - 60., top + 60., 120., 3., Color::new(1., 213. / 255., 79. / 255., 0.3)); gx.rect(cx - 60., top + 60., 120. * k, 3., pal(c::GOLD)); }
    if let Some(ch) = g.chal { let y = top + 78.; gx.text(&tf("chalHud", &[&ch.got.min(ch.need).to_string(), &ch.need.to_string(), &(ch.t.ceil() as i32).to_string()]), w / 2., y, 14., hex(0x5fffb0), 1, 2);
        gx.rect(w / 2. - 70., y + 7., 140., 3., Color::new(95. / 255., 1., 176. / 255., 0.25)); gx.rect(w / 2. - 70., y + 7., 140. * (ch.got as f32 / ch.need as f32).min(1.), 3., hex(0x5fffb0)); }
    // босс
    if let Some(bi) = g.boss_idx() { let b = &g.en.items[bi];
        let bw = w - 40. - a.safe[2] - a.safe[3]; let bx = 20. + a.safe[2]; let by = top + 80.;
        let name = crate::tiers::boss_name(b.kind, b.tier, i18n::is_en()).filter(|_| b.tier > 0).map(|s| s.to_string()).unwrap_or_else(|| i18n::boss(ET[b.kind as usize].key));
        gx.text(&name, w / 2., by - 9., 13., hex(0xff9ac0), 1, 2);
        gx.rrect(bx, by, bw, 10., 5., Color::new(30. / 255., 0., 20. / 255., 0.75)); gx.rrect_line(bx, by, bw, 10., 5., 1.5, Color::new(1., 80. / 255., 150. / 255., 0.7));
        let f = (b.hp / b.max_hp).max(0.); if f > 0. { gx.rrect(bx + 2., by + 2., ((bw - 4.) * f).max(4.), 6., 3., hex(if f < 0.5 { 0xff3b6b } else { 0xff4fd8 })); }
        let (dx, dy) = (b.x - g.cam_x, b.y - g.cam_y);
        if dx.abs() > g.vw || dy.abs() > g.vh { let an = dy.atan2(dx); let m = 34.; let sx = (w / 2. + an.cos() * w).clamp(m, w - m); let sy = (h / 2. + an.sin() * h).clamp(m + top + 90., h - m - 120.);
            arrow(gx, sx, sy, an, with_alpha(hex(0xff4f8f), 0.6 + 0.4 * (tm * 8.).sin())); }
    }
    // стрелки к сундукам
    for i in 0..g.en.n { let e = &g.en.items[i]; if e.dead || e.kind != K::Chest { continue; } let (dx, dy) = (e.x - g.cam_x, e.y - g.cam_y);
        if dx.abs() <= g.vw - 10. && dy.abs() <= g.vh - 10. { continue; }
        let an = dy.atan2(dx); let m = 34.; let sx = (w / 2. + an.cos() * w).clamp(m, w - m); let sy = (h / 2. + an.sin() * h).clamp(m + top + 90., h - m - 120.);
        let p = gx.px; gx.glow_scr(true, c::GOLD, sx * p, sy * p, 22. * p, 0.5); arrow(gx, sx, sy, an, with_alpha(pal(c::GOLD), 0.65 + 0.35 * (tm * 7.).sin())); }
    // баннер
    let bn = &g.banner;
    if bn.t < bn.dur {
        let tt = bn.t; let al = if tt < 0.25 { tt / 0.25 } else if tt > bn.dur - 0.5 { ((bn.dur - tt) / 0.5).max(0.) } else { 1. };
        let s = if tt < 0.4 { 0.6 + 0.4 * ease_out(tt / 0.4) + (tt / 0.4 * std::f32::consts::PI).sin() * 0.12 } else { 1. };
        let (bx, by) = (w / 2., h * 0.3);
        if !bn.text.is_empty() { let n = bn.text.chars().count() as f32; let fs = if n > 12. { 34f32.min(w / n * 1.55) } else { 44. } * s;
            let p = gx.px; let tw = gx.text_w(&bn.text, fs, 2);
            gx.set_add(true); let bc = hex(bn.col);
            for k in 0..2 { let gg = gx.soft[c::WHITE as usize].clone(); let ww = tw * (1.2 + k as f32 * 0.3); draw_texture_ex(&gg, (bx - ww / 2.) * p, (by - fs) * p, Color::new(bc.r, bc.g, bc.b, 0.35 * al), DrawTextureParams { dest_size: Some(vec2(ww * p, fs * 2. * p)), ..Default::default() }); }
            gx.text(&bn.text, bx, by, fs, Color::new(1., 1., 1., al), 1, 2); }
        if !bn.sub.is_empty() { let mw = w - 28.; let mut fs = 16. * s; let tw = gx.text_w(&bn.sub, fs, 1); if tw > mw { fs = (16. * mw / tw).floor().max(11.); }
            gx.text_sh(&bn.sub, bx, by + if bn.text.is_empty() { 0. } else { 34. * s }, fs, with_alpha(hex(bn.col), al), 1, 1); }
    }
    // кнопки
    let r = rects(a); let gx = &mut a.gx; let g = &a.g;
    for (rc, is_pause) in [(r.pause, true), (r.mute, false)] {
        gx.rrect(rc.x, rc.y, rc.w, rc.h, 14., Color::new(10. / 255., 30. / 255., 50. / 255., 0.55));
        let off = !g.s.set.sound && !g.s.set.music;
        gx.rrect_line(rc.x, rc.y, rc.w, rc.h, 14., 2., if !is_pause && off { Color::new(1., 120. / 255., 150. / 255., 0.55) } else { Color::new(120. / 255., 245. / 255., 1., 0.5) });
        let (cx, cy) = (rc.x + rc.w / 2., rc.y + rc.h / 2.); let k = hex(0xccffff);
        if is_pause { gx.rrect(cx - 8., cy - 8., 5., 16., 2., k); gx.rrect(cx + 3., cy - 8., 5., 16., 2., k); }
        else { let p = gx.px; gx.set_add(false); draw_rectangle((cx - 9.) * p, (cy - 3.) * p, 4. * p, 6. * p, k);
            draw_triangle(vec2((cx - 5.) * p, (cy - 3.) * p), vec2((cx + 1.) * p, (cy - 8.) * p), vec2((cx + 1.) * p, (cy + 8.) * p), k); draw_triangle(vec2((cx - 5.) * p, (cy - 3.) * p), vec2((cx + 1.) * p, (cy + 8.) * p), vec2((cx - 5.) * p, (cy + 3.) * p), k);
            if off { let rr = hex(0xff8fa8); gx.set_add(false); draw_line((cx + 4.) * p, (cy - 4.) * p, (cx + 10.) * p, (cy + 4.) * p, 2.4 * p, rr); draw_line((cx + 10.) * p, (cy - 4.) * p, (cx + 4.) * p, (cy + 4.) * p, 2.4 * p, rr); }
            else { gx.arc(cx + 3., cy, 5., -0.8, 0.8, 2., k); gx.arc(cx + 3., cy, 9., -0.8, 0.8, 2., k); } }
    }
    let hl = if g.tut.on && g.tut.fin <= 0. && g.tut.ok <= 0. { match g.tut.step { 3 => 1, 4 => 2, _ => 0 } } else { 0 };
    // рывок
    { let (x, y, rr) = r.dash; let p = gx.px; let pulse = if hl == 1 { 0.5 + 0.5 * (tm * 8.).sin() } else { 0. };
        gx.glow_scr(true, c::CYAN, x * p, y * p, (rr + 18.) * p, 0.35 + 0.4 * pulse);
        gx.circle(x, y, rr, Color::new(10. / 255., 40. / 255., 70. / 255., 0.55)); gx.circle(x, y, rr * 0.55, Color::new(63. / 255., 240. / 255., 1., 0.18));
        let cd = if g.st.dash_cd > 0. { (g.p.dash_cd.max(0.) / g.st.dash_cd).min(1.) } else { 0. };
        if cd > 0. { gx.set_add(false); let n = 40; let (cx, cy) = (x * p, y * p); let a0 = -std::f32::consts::FRAC_PI_2;
            for i in 0..n { let t0 = a0 + std::f32::consts::TAU * cd * i as f32 / n as f32; let t1 = a0 + std::f32::consts::TAU * cd * (i + 1) as f32 / n as f32;
                draw_triangle(vec2(cx, cy), vec2(cx + t0.cos() * (rr + 3.) * p, cy + t0.sin() * (rr + 3.) * p), vec2(cx + t1.cos() * (rr + 3.) * p, cy + t1.sin() * (rr + 3.) * p), Color::new(0., 0., 0., 0.6)); } }
        gx.ring(x, y, rr, 3., Color::new(120. / 255., 245. / 255., 1., 0.9));
        let k = hex(0xbbffff); for dx in [-7., 3.] { gx.set_add(false); draw_line((x + dx - 4.) * p, (y - 10.) * p, (x + dx + 3.) * p, (y - 3.) * p, 3. * p, k); draw_line((x + dx + 3.) * p, (y - 3.) * p, (x + dx - 4.) * p, (y + 4.) * p, 3. * p, k); }
        gx.text(&t("dashBtn"), x, y + 15., 11., WHITE, 1, 1); }
    // вспышка
    { let (x, y, rr) = r.flare; let p = gx.px; let fk = g.p.flare.floor() / 100.; let ready = g.p.flare >= 100.;
        if ready || hl == 2 { gx.glow_scr(true, c::GOLD, x * p, y * p, (rr + 24.) * p, 0.5 + 0.4 * (tm * 9.).sin()); }
        gx.circle(x, y, rr, Color::new(40. / 255., 20. / 255., 10. / 255., 0.55)); gx.circle(x, y, rr * 0.55, Color::new(1., 213. / 255., 79. / 255., 0.14));
        gx.arc(x, y, rr + 5., 0., std::f32::consts::TAU, 4., Color::new(1., 1., 1., 0.08));
        if fk > 0. { gx.arc(x, y, rr + 5., -std::f32::consts::FRAC_PI_2, -std::f32::consts::FRAC_PI_2 + std::f32::consts::TAU * fk, 4., pal(c::GOLD)); }
        gx.ring(x, y, rr, 3., if ready || hl == 2 { pal(c::GOLD) } else { Color::new(1., 213. / 255., 79. / 255., 0.35) });
        let k = pal(c::GOLD); gx.set_add(false); let s = 10.; let pts = [(0., -s), (0.26 * s, -0.3 * s), (s, 0.), (0.26 * s, 0.22 * s), (0., s), (-0.22 * s, 0.22 * s), (-s, 0.), (-0.22 * s, -0.3 * s)];
        for i in 0..8 { let (a0, a1) = (pts[i], pts[(i + 1) % 8]); draw_triangle(vec2(x * p, (y - 5.) * p), vec2((x + a0.0) * p, (y - 5. + a0.1) * p), vec2((x + a1.0) * p, (y - 5. + a1.1) * p), k); }
        gx.text(&t("flareBtn"), x, y + 13., 9., WHITE, 1, 1); }
    // джойстик
    if a.joy.id.is_some() && st == State::Play { let j = &a.joy; let gx = &mut a.gx;
        gx.circle(j.ox, j.oy, cfg::JOY_R, Color::new(60. / 255., 200. / 255., 1., 0.07 * 0.9)); gx.ring(j.ox, j.oy, cfg::JOY_R, 2., Color::new(150. / 255., 240. / 255., 1., 0.35 * 0.9));
        gx.circle(j.ox + j.jx * cfg::JOY_R, j.oy + j.jy * cfg::JOY_R, 22., Color::new(170. / 255., 245. / 255., 1., 0.45 * 0.9)); }
    if a.g.tut.on && a.g.boss < 0 { tutorial(a); }
}

fn tutorial(a: &mut App) {
    let g = &a.g; let tu = g.tut; let fin = tu.fin > 0.; let ok = tu.ok > 0.;
    let (tx0, tx1) = i18n::tut(tu.step, g.touch);
    let mut al = if fin { (tu.fin / 0.6).min(1.) } else if ok { 1. } else { (tu.t / 0.35).min(1.) };
    al *= clamp01((g.run_t - 0.5) / 0.5); if al <= 0. { return; }
    let w = a.gx.w; let pw = (w - 32.).min(350.); let ph = 60.; let x = (w - pw) / 2.; let y = a.safe[0] + 96.; let gold = ok || fin; let bn = &g.banner;
    if bn.t < bn.dur && y + ph + 16. > a.gx.h * 0.3 - 42. { al *= clamp01((bn.t - bn.dur + 0.4) / 0.4); } if al <= 0. { return; }
    let gx = &mut a.gx;
    gx.rrect(x, y, pw, ph, 14., if gold { Color::new(46. / 255., 34. / 255., 6. / 255., 0.82 * al) } else { Color::new(6. / 255., 24. / 255., 44. / 255., 0.8 * al) });
    gx.rrect_line(x, y, pw, ph, 14., 1.5, if gold { Color::new(1., 213. / 255., 79. / 255., 0.95 * al) } else { Color::new(120. / 255., 245. / 255., 1., (0.45 + 0.25 * (g.t * 5.).sin()) * al) });
    gx.text(&if fin { t("tutFin") } else if ok { t("tutDone") } else { tx0 }, w / 2., y + 21., if pw < 330. { 14. } else { 15. }, with_alpha(if gold { hex(0xffe9a0) } else { WHITE }, al), 1, 1);
    gx.text(&if fin { t("tutFinS") } else { tx1 }, w / 2., y + 40., 12., with_alpha(if gold { hex(0xffd54f) } else { hex(0x9fdfff) }, al), 1, 0);
    if !fin { let pr = if ok { 1. } else { g.tut_progress() }; gx.rect(x + 14., y + ph - 7., pw - 28., 3., Color::new(1., 1., 1., 0.12 * al)); gx.rect(x + 14., y + ph - 7., (pw - 28.) * pr, 3., with_alpha(pal(if gold { c::GOLD } else { c::CYAN }), al)); }
    for i in 0..5 { let col = if i < tu.step || (i == tu.step && (ok || fin)) { pal(c::GOLD) } else if i == tu.step { hex(0xccffff) } else { Color::new(1., 1., 1., 0.25) };
        gx.circle(w / 2. + (i as f32 - 2.) * 14., y + ph + 10., 3., with_alpha(col, al)); }
}

fn fade2(t: f32, a: f32, b: f32, f: f32) -> f32 { clamp01((t - a) / f) * clamp01((b - t) / f) }
pub fn intro(a: &mut App) {
    let it = &a.intro; let (t, ig, full) = (it.t, it.ig, it.full); let k = t - ig; let (w, h) = (a.gx.w, a.gx.h); let gx = &mut a.gx; let p = gx.px;
    let dark = if k < 0. { 1. } else { (1. - k / (it.dur - ig - 0.3).max(0.6)).max(0.) };
    if dark > 0. && k >= 0. { gx.fill_screen(Color::new(0., 2. / 255., 7. / 255., dark), false); }
    let sx = w / 2.; let sy0 = h * 0.56; let y = if k < 0. { sy0 } else { sy0 + (h * 0.2 - sy0) * ease_out((k / 1.4).min(1.)) };
    if full && k < 0. {
        let fs = (21f32).min(w / 17.).round(); let c0 = hex(0xbfefff);
        gx.text(&t_("introDark"), sx, h * 0.36, fs, with_alpha(c0, fade2(t, 0.45, 2.3, 0.5)), 1, 0);
        gx.text(&t_("introSpark"), sx, h * 0.42, fs, with_alpha(c0, fade2(t, 1.9, ig + 0.15, 0.5)), 1, 0);
        gx.text(&t_("skip"), sx, h - a.safe[1] - 28., 12., with_alpha(hex(0x7fb8c8), 0.45 * t.min(1.)), 1, 0);
    }
    if k < 0. {
        let grow = if full { clamp01((t - 1.2) / (ig - 1.2)) } else { 1. }; let beat = (t * 4.4).sin().max(0.).powi(10);
        let fl = 0.7 + 0.3 * (t * 23.).sin() * (t * 7.3).sin(); let r = 3. + grow * 12. + beat * (3. + grow * 9.); let al = (t * 1.4).min(1.) * fl;
        gx.glow_scr(true, c::CYAN, sx * p, y * p, r * 5. * p, al); gx.glow_scr(false, c::CYAN, sx * p, y * p, r * 1.7 * p, al); gx.glow_scr(false, c::WHITE, sx * p, y * p, r * 0.8 * p, al);
    } else {
        let f = (1. - k / 0.45).max(0.); if f > 0. { gx.fill_screen(Color::new(0x9f as f32 / 255., 0xf4 as f32 / 255., 1., f * 0.75), true); }
        let dd = (w * w + h * h).sqrt();
        for i in 0..3 { let kk = k - i as f32 * 0.16; if !(0. ..=1.7).contains(&kk) { continue; }
            gx.set_add(true); let col = with_alpha(pal(if i == 1 { c::JELLY } else { c::CYAN }), (1. - kk / 1.7) * 0.85);
            let rr = 10. + ease_out(kk / 1.7) * dd * 0.75; let n = 120; for s in 0..n { let a0 = s as f32 / n as f32 * std::f32::consts::TAU; let a1 = (s + 1) as f32 / n as f32 * std::f32::consts::TAU;
                draw_line((sx + a0.cos() * rr) * p, (sy0 + a0.sin() * rr) * p, (sx + a1.cos() * rr) * p, (sy0 + a1.sin() * rr) * p, (7. - i as f32 * 2.) * p, col); } }
        let pk = (k / 2.).min(1.);
        if pk < 1. { for i in 0..40 { let an = i as f32 * 2.39996; let d = (90. + ((i * 53) % 7) as f32 * 60.) * ease_out(pk) * 1.7;
            gx.glow_scr(false, if i % 3 > 0 { c::CYAN } else { c::JELLY }, (sx + an.cos() * d) * p, (sy0 + an.sin() * d) * p, (4. + (i % 4) as f32 * 2.5) * p, 1. - pk); } }
        let sa = 1. - clamp01((k - 0.6) / 1.1); if sa > 0. { gx.glow_scr(true, c::CYAN, sx * p, y * p, 120. * p, sa); gx.glow_scr(false, c::WHITE, sx * p, y * p, 26. * p, sa); }
    }
    gx.set_add(false);
}
fn t_(k: &str) -> String { t(k) }

pub fn ending(a: &mut App, dt: f32) {
    let tt = a.end.t; let (w, h) = (a.gx.w, a.gx.h); let dd = (w * w + h * h).sqrt();
    let vs = a.gx.ws / a.gx.px; let (px_, py_) = (w / 2. + (a.g.p.x - a.g.cam_x) * vs, h / 2. + (a.g.p.y - a.g.cam_y) * vs);
    let p = a.gx.px;
    { let gx = &mut a.gx;
        if tt < 4.15 { gx.glow_scr(true, c::GOLD, px_ * p, py_ * p, (40. + ease_out((tt / 2.2).min(1.)) * dd * 1.1) * p, 0.85 * (1. - clamp01((tt - 2.5) / 1.65))); }
        for i in 0..4 { let kk = tt - i as f32 * 0.4; if !(0. ..=2.6).contains(&kk) { continue; } let rr = 20. + ease_out(kk / 2.6) * dd;
            gx.arc(px_, py_, rr, 0., std::f32::consts::TAU, 8. - i as f32 * 1.5, with_alpha(pal(if i % 2 > 0 { c::WHITE } else { c::GOLD }), (1. - kk / 2.6) * 0.75)); }
    }
    let wv = clamp01((tt - 1.1) / 3.);
    if wv > 0. {
        let gx = &mut a.gx; gx.set_add(false);
        let stops = [(0., 0x9af7ff), (0.35, 0x2aa6d4), (0.75, 0x0b4f86), (1., 0x06305a)]; let mut v = vec![]; let mut idx = vec![];
        for (i, (s, col)) in stops.iter().enumerate() { let c0 = with_alpha(hex(*col), wv); v.push(Vertex::new(0., s * h * p, 0., 0., 0., c0)); v.push(Vertex::new(w * p, s * h * p, 0., 0., 0., c0));
            if i > 0 { let b = (i as u16 - 1) * 2; idx.extend_from_slice(&[b, b + 1, b + 3, b, b + 3, b + 2]); } }
        draw_mesh(&Mesh { vertices: v, indices: idx, texture: None });
        gx.set_add(true);
        for i in 0..5 { let x = (0.08 + i as f32 * 0.22) * w + (tt * 0.4 + i as f32 * 1.7).sin() * 30.; let rw = 30. + (i % 3) as f32 * 22.; let col = Color::new(1., 1., 230. / 255., 0.16 * wv * 0.5);
            draw_triangle(vec2((x - rw * 0.3) * p, 0.), vec2((x + rw * 0.3) * p, 0.), vec2((x + rw + 70.) * p, h * p), col); draw_triangle(vec2((x - rw * 0.3) * p, 0.), vec2((x + rw + 70.) * p, h * p), vec2((x - rw + 70.) * p, h * p), col); }
        let t = a.g.t; render_demo(a, t, dt, wv); crate::screens::end_scene(&mut a.gx, tt, w, h, h * 0.62, wv * 0.8);
        let gx = &mut a.gx;
        for i in 0..44 { let x = ((i as f32 * 0.618) % 1.) * w + (tt * 0.8 + i as f32).sin() * 14.; let y = h + 20. - ((tt * (26. + (i % 4) as f32 * 14.) + i as f32 * 97.) % (h + 40.));
            gx.glow_scr(false, if i % 3 > 0 { c::ICE } else { c::GOLD }, x * p, y * p, (3. + (i % 3) as f32 * 2.5) * p, wv * 0.8); }
    }
    let gx = &mut a.gx; let pal_ = a.g.p.pal;
    gx.glow_scr(true, pal_, px_ * p, py_ * p, (70. + 10. * (tt * 3.).sin()) * p, 0.9); gx.glow_scr(false, c::WHITE, px_ * p, py_ * p, 22. * p, 0.9);
    let out = if a.end.shown { (1. - (tt - a.end.show) / 0.5).max(0.) } else { 1. };
    if out > 0. {
        let al = out * clamp01((tt - 1.4) / 0.8); gx.set_add(false);
        let sh = a.rd.shadow.clone(); draw_texture_ex(&sh, -w * 0.15 * p, (h * 0.2 - 110.) * p, Color::new(0.6, 1., 1., al), DrawTextureParams { dest_size: Some(vec2(w * 1.3 * p, 360. * p)), ..Default::default() });
        let fs = 22f32.min(w / 16.).round();
        for (i, (t0, line)) in i18n::story().iter().enumerate() { let aa = clamp01((tt - t0) / 0.8) * out; if aa <= 0. { continue; }
            gx.text_sh(line, w / 2., h * 0.2 + i as f32 * 36. + if i > 0 { 14. } else { 0. } + (1. - aa) * 10., fs, with_alpha(hex(if i == 0 { 0xffe27a } else { 0xfffbe8 }), aa), 1, 1); }
        if !a.end.shown && tt > 2. { gx.text(&t("cont"), w / 2., h - a.safe[1] - 28., 12., Color::new(232. / 255., 251. / 255., 1., 0.55), 1, 0); }
    }
}
fn render_demo(a: &mut App, t: f32, dt: f32, am: f32) { crate::render::title_demo(&mut a.gx, &mut a.rd, t, dt, am); }

/// Всплывающие сообщения: награды, задания, подарки
pub fn toasts(a: &mut App) {
    let w = a.gx.w; let menu = a.scr != Scr::None; let mut y = if menu { a.safe[0] + 10. } else { a.gx.h - a.safe[1] - 10. - 54. };
    let list: Vec<(String, String, f32)> = a.toasts.iter().filter(|t| t.t >= 0.).map(|t| (t.title.clone(), t.sub.clone(), t.t)).collect();
    for (title, sub, tt) in list.iter().take(3) {
        let al = clamp01(tt / 0.25) * clamp01((3.2 - tt) / 0.4); if al <= 0. { continue; }
        let land = a.gx.w > a.gx.h * 1.15; let gx = &mut a.gx; let tw = gx.text_w(title, 11., 2).max(gx.text_w(sub, 13., 1)) + 32.; let bw = tw.min(w - 24.).max(160.); let x = if land && menu { 12. + a.safe[2] } else { (w - bw) / 2. }; let tcx = x + bw / 2.; let dy = (1. - clamp01(tt / 0.25)) * 12.;
        ui::rrect_grad(gx, x, y + dy, bw, 46., 14., Color::new(80. / 255., 60. / 255., 10. / 255., 0.95 * al), Color::new(40. / 255., 15. / 255., 50. / 255., 0.95 * al));
        gx.rrect_line(x, y + dy, bw, 46., 14., 2., with_alpha(pal(c::GOLD), al));
        gx.text(title, tcx, y + dy + 15., 11., with_alpha(pal(c::GOLD), al), 1, 2); gx.text(sub, tcx, y + dy + 31., 13., Color::new(1., 1., 1., al), 1, 1);
        y += if menu { 54. } else { -54. };
    }
}
