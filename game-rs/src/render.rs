//! Отрисовка мира: фон зоны, плиточное дно, декорации, существа (с живой анимацией), боссы, игрок, эффекты.
//! Перенесено из renderBackground/renderWorld веб-версии.
use crate::data::{c, cfg, ET, K, SKINS, TAU, PAL_HEX, ZONE_COLS};
use crate::game::*;
use crate::gfx::*;
use macroquad::prelude::*;

pub const XPC: [u8; 3] = [c::ICE, c::EMER, c::GOLD];
pub const XPS: [f32; 3] = [3.6, 5., 6.8];
const RAYS: [[f32; 3]; 5] = [[0.1, 70., 0.], [0.32, 110., 1.3], [0.55, 60., 2.1], [0.74, 130., 3.7], [0.92, 80., 5.2]];
const SNOW_N: [usize; 3] = [40, 28, 16];
const SNOW_F: [f32; 3] = [0.15, 0.35, 0.65];
const SNOW_S: [f32; 3] = [5., 9., 15.];

pub struct Demo { pub k: &'static str, pub x: f32, pub y: f32, pub s: f32, pub sp: f32, pub p: f32 }
/// Состояние отрисовки, не относящееся к логике игры
pub struct Rd { pub snow: [Vec<(f32, f32)>; 3], pub demo: Vec<Demo>, pub shadow: Texture2D }
impl Rd {
    pub fn new() -> Rd {
        let r = || rand::gen_range(0f32, 1.);
        let snow = [(0..SNOW_N[0]).map(|_| (r(), r())).collect(), (0..SNOW_N[1]).map(|_| (r(), r())).collect(), (0..SNOW_N[2]).map(|_| (r(), r())).collect()];
        let kinds = ["jelly", "drifter", "squid", "jelly", "dart", "bomber", "drifter", "urchin", "jelly_t1", "squid_t2", "drifter_t1", "ray", "lantern", "jelly_t2", "dart_t2", "eel"];
        let demo = kinds.iter().map(|k| Demo { k, x: r(), y: r(), s: rand::gen_range(0.8, 1.5), sp: rand::gen_range(8., 22.), p: r() * TAU }).collect();
        // мягкая тень у основания декораций
        let n = 64u16; let mut px = vec![0u8; n as usize * n as usize * 4];
        for y in 0..n { for x in 0..n { let d = (((x as f32 + 0.5) / n as f32 * 2. - 1.).powi(2) + ((y as f32 + 0.5) / n as f32 * 2. - 1.).powi(2)).sqrt().min(1.);
            let i = (y as usize * n as usize + x as usize) * 4; px[i + 2] = 8; px[i + 3] = ((1. - d) * 0.6 * 255.) as u8; } }
        let shadow = Texture2D::from_rgba8(n, n, &px); shadow.set_filter(FilterMode::Linear);
        Rd { snow, demo, shadow }
    }
}

fn spr_key(k: K, sh: f32, tier: u8) -> String {
    let b = match k { K::Crab if sh <= 0. => "crab_bare", K::KingCrab if sh <= 0. => "kingcrab_bare", _ => ET[k as usize].key };
    tkey(b, tier)
}
/// Облик по ярусу глубины
pub fn tkey(b: &str, tier: u8) -> String { if tier > 0 { format!("{b}_t{tier}") } else { b.to_string() } }
#[inline] fn modf(a: f32, b: f32) -> f32 { ((a % b) + b) % b }
fn ease_out(t: f32) -> f32 { 1. - (1. - t).powi(3) }
pub fn low_hp(g: &Game) -> bool { !g.p.dead && g.p.hp < g.p.max_hp * 0.3 && matches!(g.state, State::Play | State::Pause | State::LevelUp) }

/// Фон: цвет зоны, дно-плитка, декорации, лучи света с поверхности, морской снег
pub fn background(gx: &mut Gfx, rd: &mut Rd, g: &mut Game, dt: f32, show_decor: bool) {
    let hi = g.quality >= 1;
    let zi = if g.state == State::Title || g.state == State::Intro { 0 } else { (g.zone as usize).saturating_sub(1).min(ZONE_COLS.len() - 1) };
    clear_background(hex(ZONE_COLS[zi]));
    // дно: плитка 512 пикселей, 1 пиксель = 0.9 единицы мира
    if let Some(t) = gx.ground.get(zi).cloned() {
        gx.set_add(false);
        // плитка дна: ширина 560 единиц мира, высота — по пропорциям картинки
        let (sw, sh) = (screen_width(), screen_height()); let tile = 560.; let tile_h = tile * t.height() / t.width().max(1.);
        let wx = |sx: f32| (sx - gx.ox) / gx.ws; let wy = |sy: f32| (sy - gx.oy) / gx.ws;
        let v = |sx: f32, sy: f32| Vertex::new(sx, sy, 0., wx(sx) / tile, wy(sy) / tile_h, WHITE);
        draw_mesh(&Mesh { vertices: vec![v(0., 0.), v(sw, 0.), v(sw, sh), v(0., sh)], indices: vec![0, 1, 2, 0, 2, 3], texture: Some(t) });
    }
    // бегущие блики света по дну (каустика): два слоя с разным масштабом и сносом
    if let Some(ct) = gx.caustic.clone() {
        let (sw, sh) = (screen_width(), screen_height()); let depth = if g.state == State::Title || g.state == State::Intro { 0. } else { (g.zone as f32 - 1.) / 14. };
        let acc = hex(crate::data::ZONE_ACCENTS[zi]); let base = (0.06 - depth * 0.03) * if g.boss >= 0 { 0.6 } else { 1. };
        let layers: &[(f32, f32, f32, f32)] = if hi { &[(210., 9., 4., 1.0), (310., -6., 7., 0.75)] } else { &[(240., 8., 5., 1.0)] };
        gx.set_add(true);
        for &(tile, vx, vy, k) in layers {
            let (ox, oy) = (g.t * vx, g.t * vy); let a = base * k;
            let col = Color::new(0.55 + acc.r * 0.45, 0.55 + acc.g * 0.45, 0.55 + acc.b * 0.45, a);
            let wx = |sx: f32| (sx - gx.ox) / gx.ws; let wy = |sy: f32| (sy - gx.oy) / gx.ws;
            let v = |sx: f32, sy: f32| Vertex::new(sx, sy, 0., (wx(sx) + ox) / tile, (wy(sy) + oy) / tile, col);
            draw_mesh(&Mesh { vertices: vec![v(0., 0.), v(sw, 0.), v(sw, sh), v(0., sh)], indices: vec![0, 1, 2, 0, 2, 3], texture: Some(ct.clone()) });
        }
        gx.set_add(false);
    }
    if g.boss >= 0 { gx.fill_screen(Color::new(40. / 255., 0., 30. / 255., 0.32), false); }
    if show_decor { decor(gx, rd, g, dt); }
    // лучи
    let ray_a = (0.42 - if g.state == State::Title { 0. } else { (g.zone as f32 - 1.) * 0.025 }).max(0.1) * if g.boss >= 0 { 0.5 } else { 1. };
    let (w, h) = (gx.w, gx.h); let twr = w * 1.6; let p = gx.px; gx.set_add(true);
    for i in 0..(if hi { 5 } else { 3 }) {
        let r = RAYS[i]; let x = modf(r[0] * twr - g.cam_x * 0.05 * (gx.ws / p), twr) - w * 0.3; let swy = (g.t * 0.3 + r[2]).sin() * 40.; let rw = r[1];
        let ww = rw * 1.1; let col = Color::new(170. / 255., 240. / 255., 1., 0.2 * ray_a);
        soft_ray((x - ww * 0.35) * p, (x + ww * 0.35) * p, 0., (x - ww + swy + 60.) * p, (x + ww + swy + 60.) * p, h * 0.9 * p, col);
    }
    // морской снег: три слоя параллакса
    let (tw, th) = (w + 60., h + 60.); let vs = gx.ws / p;
    for l in 0..3 { if !hi && l == 2 { continue; }
        let a = [0.35, 0.5, 0.35][l]; let sz = SNOW_S[l]; let f = SNOW_F[l];
        for (i, &(sx, sy)) in rd.snow[l].iter().enumerate() {
            let x = modf(sx * tw - g.cam_x * f * vs + (g.t * 0.5 + i as f32 * 2.).sin() * 8., tw) - 30.;
            let y = modf(sy * th - g.cam_y * f * vs - g.t * (6. + l as f32 * 6.), th) - 30.;
            gx.glow_scr(l == 2, c::ICE, x * p, y * p, sz / 2. * p, a);
        } }
    gx.set_add(false);
}

fn decor(gx: &mut Gfx, rd: &mut Rd, g: &mut Game, dt: f32) {
    let (vw, vh) = (g.vw, g.vh); let (cx, cy) = (g.cam_x, g.cam_y);
    let (x0, x1, y0, y1) = (cx - vw - 60., cx + vw + 60., cy - vh - 60., cy + vh + 60.);
    let hi = g.quality >= 1; let shadow = rd.shadow.clone();
    let mut vents: Vec<(f32, f32)> = vec![];
    for i in 0..g.decor.len() {
        let d = &mut g.decor[i]; if d.a < 1. { d.a = (d.a + dt * 0.8).min(1.); }
        let key = DECOR_KEYS[d.k]; let half = gx.spr_half(key); let ext = half * d.s;
        if d.x + ext < x0 || d.x - ext > x1 || d.y + ext < y0 || d.y - ext > y1 { continue; }
        let sw = if d.sw > 0. { (g.t * 0.9 + d.p).sin() * d.sw * 0.5 } else { 0. };
        let dw = half * 2.; let k = d.s * gx.ws;
        // тень у основания (в местных координатах: -0.42dw..0.42dw по x, 0.3dw..0.5dw по y)
        let (sx, sy) = (gx.sx(d.x), gx.sy(d.y)); gx.set_add(false);
        draw_texture_ex(&shadow, sx - dw * 0.42 * k, sy + dw * 0.3 * k, Color::new(1., 1., 1., d.a), DrawTextureParams { dest_size: Some(vec2(dw * 0.84 * k, dw * 0.2 * k)), ..Default::default() });
        let (sqx, sqy) = (gx.sqx, gx.sqy); gx.sqx = 1.; gx.sqy = 1.;
        gx.tint = Color::new(0.78, 0.82, 0.92, 1.); gx.spr_screen(key, sx, sy, sw, k, d.a, false, 0., false); gx.tint = WHITE;
        gx.sqx = sqx; gx.sqy = sqy;
        if key == "d_vent" && hi && g.state == State::Play && g.t - d.lt > 0.22 { d.lt = g.t; vents.push((d.x, d.y - dw * d.s * 0.3)); }
    }
    for (x, y) in vents { let (a, b, l, s) = (g.rr(-6., 6.), g.rr(-15., 15.), g.rr(0.8, 1.4), g.rr(4., 8.)); let vy = g.rr(-70., -40.); g.part(x + a, y, b, vy, l, s, c::ICE, 0.5); }
}

/// Мир: светящееся дно, граница арены, мины, добыча, враги, игрок, снаряды, частицы, цифры
pub fn world(gx: &mut Gfx, g: &mut Game, rdt: f32) {
    let hi = g.quality >= 1; let t = g.t;
    let (x0, x1, y0, y1) = (g.cam_x - g.vw - 80., g.cam_x + g.vw + 80., g.cam_y - g.vh - 80., g.cam_y + g.vh + 80.);
    let in_view = |x: f32, y: f32, m: f32| x > x0 - m && x < x1 + m && y > y0 - m && y < y1 + m;
    for f in g.floor.iter() { if !in_view(f.0, f.1, f.2) { continue; } gx.glow_world(true, f.3, f.0, f.1, f.2, 0.07 + 0.04 * (t * 0.8 + f.4).sin()); }
    // за пределами арены — тьма, граница — светящееся кольцо
    let r = cfg::ARENA_R;
    if hypot(g.cam_x, g.cam_y) + hypot(g.vw, g.vh) > r - 20. {
        // мягкий край: тьма нарастает за 260 единиц до границы, тонкая светящаяся кромка
        gx.set_add(false); let n = 160; let (cx, cy) = (gx.sx(0.), gx.sy(0.));
        let rings = [(r - 260., 0.0f32), (r - 90., 0.35), (r, 0.62), (r + 260., 0.86), (r + 4000., 0.9)];
        let mut v = Vec::with_capacity((n + 1) * rings.len()); let mut idx = Vec::with_capacity(n * 6 * (rings.len() - 1));
        for i in 0..=n { let a = i as f32 / n as f32 * TAU; let (ca, sa) = (a.cos(), a.sin());
            for &(rr, al) in rings.iter() { let rs = rr * gx.ws; v.push(Vertex::new(cx + ca * rs, cy + sa * rs, 0., 0., 0., Color::new(0., 0.01, 0.04, al))); } }
        let m = rings.len() as u16;
        for i in 0..n as u16 { for j in 0..m - 1 { let a = i * m + j; let b = a + m; idx.extend_from_slice(&[a, b, a + 1, a + 1, b, b + 1]); } }
        draw_mesh(&Mesh { vertices: v, indices: idx, texture: None });
        let cy_ = hex(PAL_HEX[c::CYAN as usize]);
        gx.arc_world(0., 0., r, 0., TAU, 18., with_a(cy_, 0.035), true);
        gx.arc_world(0., 0., r, 0., TAU, 1.5, with_a(cy_, 0.12 + 0.05 * (t * 2.).sin()), true);
    }
    // мины
    for i in 0..g.mines.n { let m = g.mines.items[i].clone(); if m.inst { continue; }
        gx.glow_world(true, if m.freeze { c::ICE } else { c::PURP }, m.x, m.y, 26., 0.6 + 0.3 * (t * 10. + i as f32).sin());
        gx.circle_world(m.x, m.y, 8., hex(0x12051f), false);
        gx.circle_world(m.x, m.y, 3., if m.t > 0.4 && (t * 6.) as i32 % 2 == 1 { WHITE } else { hex(PAL_HEX[c::PURP as usize]) }, false); }
    // добыча
    for i in 0..g.picks.n { let p = g.picks.items[i].clone(); if !in_view(p.x, p.y, 20.) { continue; }
        if p.kind >= 3 && p.t > 19. && (t * 8.) as i32 % 2 == 1 { continue; }
        match p.kind { 0..=2 => gx.glow_world(true, XPC[p.kind as usize], p.x, p.y, XPS[p.kind as usize] * 3.2, 1.),
            3 => { gx.glow_world(true, c::CORAL, p.x, p.y, 22., 1.); gx.glow_world(false, c::WHITE, p.x, p.y, 10. + (t * 6. + i as f32).sin() * 2., 1.); }
            4 => { gx.glow_world(true, c::EMER, p.x, p.y, 26., 1.); let k = hex(0xd8ffe8); gx.rect_rot_world(p.x, p.y, 0., -7., 14., 5., k, None); gx.rect_rot_world(p.x, p.y, 0., -2.5, 5., 14., k, None);
                gx.rect_rot_world(p.x, p.y - 4.5, 0., -2.5, 5., 5., k, None); gx.rect_rot_world(p.x, p.y + 4.5, 0., -2.5, 5., 5., k, None); }
            _ => { gx.glow_world(true, c::ICE, p.x, p.y, 26., 1.); gx.arc_world(p.x, p.y, 8., t * 4., t * 4. + 4.5, 3., hex(0xbbffff), false); } }
    }
    // искры опыта — ромбики
    for i in 0..g.picks.n { let p = &g.picks.items[i]; if p.kind > 2 || !in_view(p.x, p.y, 10.) { continue; }
        let q = XPS[p.kind as usize] * (0.85 + 0.15 * (t * 3. + i as f32).sin()); let col = hex(PAL_HEX[XPC[p.kind as usize] as usize]);
        let (a, b, cc, d) = ((p.x, p.y - q * 1.3), (p.x + q, p.y), (p.x, p.y + q * 1.3), (p.x - q, p.y));
        gx.tri_world(a, b, cc, col); gx.tri_world(a, cc, d, col);
        let wl = Color::new(1., 1., 1., 0.8); for (u, v) in [(a, b), (b, cc), (cc, d), (d, a)] { gx.line_world(u.0, u.1, v.0, v.1, 1., wl, false); } }
    // враги: свечение
    if hi { for i in 0..g.en.n { let e = &g.en.items[i]; if e.dead || !in_view(e.x, e.y, e.r * 3.) { continue; }
        gx.glow_world(true, if e.elite { c::GOLD } else { e.col }, e.x, e.y, e.r * e.scale * if e.elite { 3.4 } else { 2.6 } * (1. + 0.06 * (t * 2.2 + e.phase).sin()), 0.4 + 0.1 * (t * 2.2 + e.phase).sin()); } } // свечение существ дышит
    // телеграфы атак
    for i in 0..g.en.n { let e = g.en.items[i].clone(); if e.dead || !in_view(e.x, e.y, 300.) { continue; } telegraph(gx, g, &e); }
    // мягкие тени под существами — отделяют их от дна
    { let sh = gx.shade.clone(); gx.set_add(false);
      for i in 0..g.en.n { let e = &g.en.items[i]; if e.dead || !in_view(e.x, e.y, e.r * 2.) { continue; } let (rx, ry) = (e.r * e.scale * 1.25, e.r * e.scale * 0.8);
        let (sx, sy) = (gx.sx(e.x + e.r * 0.25), gx.sy(e.y + e.r * 0.55)); let a = if ET[e.kind as usize].boss { 0.55 } else { 0.45 };
        draw_texture_ex(&sh, sx - rx * gx.ws, sy - ry * gx.ws, Color::new(1., 1., 1., a), DrawTextureParams { dest_size: Some(vec2(rx * 2. * gx.ws, ry * 2. * gx.ws)), ..Default::default() }); } }
    // враги: тела (вспышки попаданий — одним проходом после)
    gx.defer_white = true;
    for i in 0..g.en.n {
        if g.en.items[i].dead { continue; }
        let (ex, ey, er, kind) = { let e = &g.en.items[i]; (e.x, e.y, e.r, e.kind) };
        if !in_view(ex, ey, er * 3. + match kind { K::Boss2 => 260., K::Eel => 140., _ => 0. }) { continue; }
        { let e = &mut g.en.items[i]; let v = hypot(e.vx, e.vy); let k = (v / e.spd.max(20.).max(if e.spd > 0. { 0. } else { 60. })).min(1.8);
            e.a_t += rdt * (0.55 + 0.85 * k); let st = (k - 1.).max(0.) * 0.12; let hit = if e.flash > 0. { 0.14 } else { 0. }; gx.sqx = 1. + st - hit; gx.sqy = 1. - st * 0.7 + hit; }
        let e = g.en.items[i].clone();
        let mut sc = e.scale; let mut alpha = 1.;
        if e.spawn_t > 0. { let q = 1. - e.spawn_t / 0.4; sc *= if q < 0.7 { q / 0.7 * 1.15 } else { 1.15 - (q - 0.7) / 0.3 * 0.15 }; alpha = (q * 1.6).min(1.); }
        let wht = e.flash > 0.; let key_s = spr_key(e.kind, e.sh, e.tier); let key = key_s.as_str();
        let ph = |gx: &Gfx, k: &str| gx.spr_anim(k).map(|a| e.a_t * a.freq() * TAU + e.phase).unwrap_or(0.);
        match e.kind {
            K::Jelly => { let ch = if e.t > 2.6 { (e.t - 2.6) / 0.7 } else { 0. }; let pul = 1. + (t * 4. + e.phase).sin() * 0.06 + ch * 0.15;
                let p = ph(gx, key); gx.spr_world(key, e.x, e.y, e.ang, sc * pul, alpha, wht, p, true);
                if ch > 0. { let (lx, ly) = local(&e, 0., -4.); gx.glow_world(false, c::JELLY, lx, ly, 20. + ch * 14., ch * 0.8); } }
            K::Eel => {
                for s in (1..=8).rev() { let k = s * 3; if k >= e.hn { continue; } let j = ((e.hh as i32 - k as i32) % 32 + 32) as usize % 32; let j2 = (j + 2) % 32;
                    let sa = (e.hist[j2 * 2 + 1] - e.hist[j * 2 + 1]).atan2(e.hist[j2 * 2] - e.hist[j * 2]);
                    gx.spr_world(&tkey("eelseg", e.tier), e.hist[j * 2], e.hist[j * 2 + 1], sa, sc * (1. - s as f32 * 0.06), alpha, false, 0., false); }
                let p = ph(gx, key); let jr = 0.12 + 0.16 * (t * 5.5 + e.phase).sin().max(-0.6); gx.spr_jaw_a(key, e.x, e.y, e.ang, sc, alpha, wht, p, jr); }
            K::Squid => { let p = ph(gx, key); gx.spr_world(key, e.x, e.y, e.ang, sc, alpha, wht, p, false);
                if e.state == 1 { let k = 1. - e.st / 0.55; let (lx, ly) = local(&e, 22., 0.); gx.glow_world(false, c::SQUID, lx, ly, 10. + k * 16., k); } }
            K::Boss1 => boss1(gx, g, &e, sc, wht),
            K::Boss2 => boss2(gx, g, &e, sc, wht),
            K::Boss3 => boss3(gx, g, &e, sc, wht),
            K::Boss4 => boss4(gx, g, &e, sc, wht),
            K::KingCrab => king(gx, g, &e, sc, wht),
            K::Queen => queen(gx, g, &e, sc, wht),
            K::Wisp => { gx.glow_world(true, c::AMBER, e.x, e.y, 30., 0.7 + 0.3 * (t * 14. + e.phase).sin());
                gx.spr_world(key, e.x, e.y, e.ang, sc, if e.st < 1. { e.st.max(0.2) } else { 1. }, wht, 0., false); }
            K::Spawner => { let ch = if e.state == 1 { 1. - e.st / 0.9 } else { 0. }; let pul = 1. + (t * 3. + e.phase).sin() * 0.04 + ch * 0.16; let p = ph(gx, key);
                gx.spr_world(key, e.x, e.y + (t * 1.7 + e.phase).sin() * 1.4, e.ang, sc * pul, alpha, wht, p, false);
                if ch > 0. { gx.glow_world(false, c::EEL, e.x, e.y, e.r * (0.8 + ch * 0.6), ch * 0.7); } }
            K::Lantern => { let ch = if e.state == 1 { 1. - e.st / 0.8 } else { 0. }; let p = ph(gx, key); let yy = e.y + (t * 1.7 + e.phase).sin() * 1.4;
                let jr = if ch > 0. { 0.1 + 0.3 * ch } else { 0.06 + 0.08 * (t * 2.4 + e.phase).sin() }; gx.spr_jaw_a(key, e.x, yy, e.ang, sc, alpha, wht, p, jr);
                let (lx, ly) = (e.x + e.ang.cos() * e.r * 1.25 + e.ang.sin() * e.r * 0.05, yy + e.ang.sin() * e.r * 1.25 - e.ang.cos() * e.r * 0.05);
                gx.glow_world(false, c::AMBER, lx, ly, 8. + ch * 16. + (t * 7.).sin() * 1.5, 0.55 + 0.45 * ch); }
            K::Crystal => gx.spr_world(key, e.x, e.y, t * 2., sc, alpha, wht, ph(gx, key), false),
            K::Crab => { let p = ph(gx, key); let jr = 0.13 * (t * 4.2 + e.phase).sin() + 0.04; let wob = (t * 2.1 + e.phase).sin() * 0.05;
                gx.spr_jaw_a(key, e.x, e.y, e.ang + wob, sc, alpha, wht, p, jr); }
            _ => { let breathe = 1. + (t * if e.elite { 3.1 } else { 2.35 } + e.phase).sin() * if e.elite { 0.045 } else { 0.025 };
                let drift = (t * 1.7 + e.phase).sin() * 1.4; let wob = (t * 2.1 + e.phase).sin() * 0.07; let p = ph(gx, key);
                gx.spr_world(key, e.x, e.y + drift, e.ang + wob, sc * breathe, alpha, wht, p, false); }
        }
        gx.sqx = 1.; gx.sqy = 1.; gx.jaw = 0.;
        if g.p.mark_uid != 0 && e.uid == g.p.mark_uid { let rr = e.r * e.scale * 1.6 + 6.; let col = with_a(hex(PAL_HEX[c::CRAB as usize]), 0.75 + 0.25 * (t * 6.).sin());
            for q in 0..4 { let a0 = t * 1.5 + q as f32 * std::f32::consts::FRAC_PI_2; gx.arc_world(e.x, e.y, rr, a0, a0 + 0.9, 2.5, col, true); } }
        if e.elite { gx.arc_world(e.x, e.y, e.r * e.scale * 1.35, t * 2., t * 2. + 4.6, 2., with_a(hex(PAL_HEX[c::GOLD as usize]), 0.8), false); }
        if e.aff > 0 { use crate::content::*; let rr = e.r * e.scale; let ac = hex(aff_col(e.aff)); let pi = aff_pal(e.aff);
            match e.aff {
                AFF_SHIELD if e.ash > 0. => { let k = (e.ash / (e.max_hp * 0.45)).clamp(0., 1.); gx.circle_world(e.x, e.y, rr * 1.5, with_a(ac, 0.10 + 0.08 * k), true);
                    gx.arc_world(e.x, e.y, rr * 1.5, 0., TAU, 2.5, with_a(ac, 0.35 + 0.4 * k), true); gx.arc_world(e.x, e.y, rr * 1.5, -t * 1.5, -t * 1.5 + 1.2, 4., with_a(WHITE, 0.5 * k), true); }
                AFF_VAMP => gx.glow_world(true, pi, e.x, e.y, rr * 3.2, 0.35 + 0.15 * (t * 4.).sin()),
                AFF_RAGE => if e.aff_t < -100. { gx.glow_world(true, pi, e.x, e.y, rr * 3.4, 0.5 + 0.3 * (t * 12.).sin()); } else { gx.glow_world(true, pi, e.x, e.y, rr * 2.4, 0.2); },
                AFF_BLINK => { gx.glow_world(true, pi, e.x, e.y, rr * 2.8, 0.3 + 0.2 * (t * 3. + e.phase).sin()); }
                AFF_VOLATILE => { let k = 0.5 + 0.5 * (t * 7.).sin(); gx.glow_world(false, pi, e.x, e.y, rr * (1.6 + 0.4 * k), 0.35 * k + 0.15); }
                AFF_SPLIT => { gx.arc_world(e.x, e.y, rr * 1.2, t * 3., t * 3. + 1.4, 2.5, with_a(ac, 0.8), true); gx.arc_world(e.x, e.y, rr * 1.2, t * 3. + 3.14, t * 3. + 4.54, 2.5, with_a(ac, 0.8), true); }
                _ => {}
            }
            let (sx, sy) = (gx.sx(e.x), gx.sy(e.y - rr - 20.)); let p = gx.px; gx.text(aff_name(e.aff), sx / p, sy / p, 10., with_a(ac, 0.95), 1, 2);
        }
        if (e.elite || e.hp < e.max_hp * 0.72) && !ET[e.kind as usize].boss && e.kind != K::Chest {
            let bw = (e.r * e.scale * 2.1).max(22.); let by = e.y - e.r * e.scale - 9.; let a = if e.elite { 0.92 } else { 0.68 };
            gx.rect_rot_world(e.x - bw / 2., by + 1.75, 0., 0., bw, 3.5, Color::new(0., 0., 8. / 255., 0.72 * a), None);
            gx.rect_rot_world(e.x - bw / 2., by + 1.75, 0., 0., bw * (e.hp / e.max_hp).clamp(0., 1.), 3.5, with_a(if e.elite { hex(PAL_HEX[c::GOLD as usize]) } else { hex(0xff779b) }, a), None);
        }
    }
    gx.defer_white = false; gx.flush_white();
    for i in 0..g.en.n { let e = &g.en.items[i]; if e.dead || !in_view(e.x, e.y, e.r * 3.) { continue; }
        if e.freeze > 0. { gx.glow_world(true, c::ICE, e.x, e.y, e.r * e.scale * 2., 0.7); } else if e.slow > 0. && hi { gx.glow_world(true, c::ICE, e.x, e.y, e.r * e.scale * 1.6, 0.35); } }
    // гибель: белые силуэты
    for gh in g.ghosts.iter() { if !gh.on { continue; } let k = gh.t / 0.2; if k >= 1. { continue; }
        let key = spr_key(gh.kind, if gh.bare { 0. } else { 1. }, gh.tier); gx.spr_ghost(&key, gh.x, gh.y, gh.a, gh.s * (1. + k * 0.6), (1. - k) * (1. - k) * 0.3); }
    new_upg(gx, g);
    if !g.p.dead { player(gx, g, rdt); }
    // снаряды игрока
    let pc = g.p.pal; let ac = crate::data::SKIN_ACC.get(g.p.skin).copied().unwrap_or(c::WHITE);
    for i in 0..g.pb.n { let b = &g.pb.items[i]; if !in_view(b.x, b.y, 10.) { continue; } let a = b.vy.atan2(b.vx);
        if b.boom > 0. { gx.glow_stretch(c::FIRE, b.x, b.y, a, -30., 40., 16., 0.7); gx.glow_world(true, c::FIRE, b.x, b.y, 16., 0.9); gx.glow_world(false, c::WHITE, b.x, b.y, 6., 1.); continue; }
        let k = b.r / 4.;
        match b.form {
            1 => { gx.glow_stretch(pc, b.x, b.y, a, -40., 52., 8., 0.6); gx.glow_stretch(ac, b.x, b.y, a, -16., 28., 5., 1.); gx.glow_stretch(c::WHITE, b.x, b.y, a, -2., 14., 3.5, 1.); } // игла
            2 => { gx.glow_world(true, pc, b.x, b.y, 15. * k, 0.8); gx.glow_world(false, ac, b.x, b.y, 8. * k, 1.); gx.glow_world(false, c::WHITE, b.x, b.y, 4. * k, 1.); } // шар
            3 => { gx.glow_stretch(pc, b.x, b.y, a, -12., 18., 12., 0.7); gx.glow_world(false, ac, b.x, b.y, 6. * k, 1.); gx.glow_world(false, c::WHITE, b.x, b.y, 3., 1.); } // дробь
            4 => { let (nx, ny) = (-a.sin(), a.cos()); for q in -2..=2 { let o = q as f32 * 5. * k; let bk = (q as f32).abs() * 3.;
                    gx.glow_world(false, if q == 0 { c::WHITE } else { ac }, b.x + nx * o - a.cos() * bk, b.y + ny * o - a.sin() * bk, (5. - (q as f32).abs()) * k, 1.); }
                   gx.glow_world(true, pc, b.x, b.y, 14. * k, 0.6); } // полумесяц
            5 => { gx.glow_world(true, pc, b.x, b.y, 12., 0.6); gx.glow_stretch(ac, b.x, b.y, a + (b.t * 34.).sin() * 0.7, -8., 16., 5., 1.); gx.glow_world(false, c::WHITE, b.x, b.y, 3.5, 1.); } // молния
            6 => { for q in 1..4 { let d = q as f32 * 9.; gx.glow_world(true, pc, b.x - a.cos() * d, b.y - a.sin() * d, (9. - q as f32 * 2.) * k, 0.35 / q as f32); }
                   gx.glow_world(true, pc, b.x, b.y, 12. * k, 0.7); gx.glow_world(false, ac, b.x, b.y, 5. * k, 1.); } // призрак
            7 => { let g_ = 1. + b.t * 3.; gx.glow_world(true, c::FIRE, b.x, b.y, 13. * k * g_, 0.6); gx.glow_world(true, pc, b.x, b.y, 8. * k * g_, 0.8); gx.glow_world(false, c::GOLD, b.x, b.y, 4. * k, 1.); } // пламя
            8 => { gx.glow_stretch(pc, b.x, b.y, a, -14., 22., 13. * k, 0.6); gx.glow_world(false, ac, b.x, b.y, 6. * k, 1.); gx.glow_world(false, c::WHITE, b.x - a.sin() * 1.5, b.y + a.cos() * 1.5, 2.5, 1.); } // капля
            9 => { let sa = b.t * 16.; gx.glow_world(true, pc, b.x, b.y, 12. * k, 0.6); for q in 0..2 { let aa = sa + q as f32 * std::f32::consts::FRAC_PI_2; gx.glow_stretch(ac, b.x, b.y, aa, -9. * k, 18. * k, 4., 1.); }
                   gx.glow_world(false, c::WHITE, b.x, b.y, 3.5, 1.); } // звезда
            _ => { gx.glow_stretch(pc, b.x, b.y, a, -24., 34., 14., 0.52); gx.glow_stretch(ac, b.x, b.y, a, -10., 22., 12., 1.); gx.glow_stretch(c::WHITE, b.x, b.y, a, 0., 10., 7., 1.); }
        }
        if b.crit { gx.glow_world(false, c::GOLD, b.x, b.y, 11., 1.); } }
    // частицы
    for i in 0..g.parts.n { let p = &g.parts.items[i]; if !in_view(p.x, p.y, 20.) { continue; } let k = p.life / p.max; let s = p.size * (0.35 + 0.65 * k); gx.glow_world(false, p.col, p.x, p.y, s, k); }
    // молнии
    for i in 0..g.bolts.n { let b = g.bolts.items[i].clone(); let a = (b.life / 0.18).min(1.); let ic = hex(PAL_HEX[c::ICE as usize]);
        for k in 0..7 { gx.line_world(b.pts[k * 2], b.pts[k * 2 + 1], b.pts[k * 2 + 2], b.pts[k * 2 + 3], 7., with_a(ic, a * 0.35), true); }
        for k in 0..7 { gx.line_world(b.pts[k * 2], b.pts[k * 2 + 1], b.pts[k * 2 + 2], b.pts[k * 2 + 3], 2., Color::new(1., 1., 1., a), true); } }
    // кольца-волны
    for i in 0..g.rings.n { let r = g.rings.items[i].clone(); let k = r.life / r.max; let rr = r.r0 + (r.r1 - r.r0) * ease_out(1. - k);
        gx.arc_world(r.x, r.y, rr, 0., TAU, r.w * k + 0.6, with_a(hex(PAL_HEX[r.col as usize]), k), true); }
    // вражеские пули — поверх всего
    for i in 0..g.eb.n { let b = &g.eb.items[i]; if !in_view(b.x, b.y, 10.) { continue; } gx.bul_world(b.col, b.x, b.y, b.r * 2.3); }
    // цифры урона
    for i in 0..g.texts.n { let tx = g.texts.items[i].clone(); let k = tx.life / tx.max; let a = (k * 2.5).min(1.);
        let size = if tx.big { 26. } else if tx.crit { 18. } else { 13. }; let vs = gx.ws / gx.px;
        let (sx, sy) = (gx.sx(tx.x) / gx.px, gx.sy(tx.y) / gx.px);
        gx.text(&tx.s, sx + 1.5 * vs, sy + 1.5 * vs, size * vs, Color::new(0., 0., 0., 0.55 * a), 1, 2);
        gx.text(&tx.s, sx, sy, size * vs, with_a(hex(tx.col), a), 1, 2); }
    gx.set_add(false);
}

pub fn with_a(mut c: Color, a: f32) -> Color { c.a = a; c }
/// Точка в местных координатах существа (с учётом поворота)
fn local(e: &Enemy, lx: f32, ly: f32) -> (f32, f32) { let (ca, sa) = (e.ang.cos(), e.ang.sin()); (e.x + lx * ca - ly * sa, e.y + lx * sa + ly * ca) }

fn telegraph(gx: &mut Gfx, g: &Game, e: &Enemy) {
    let t = g.t;
    match e.kind {
        K::Dart if e.state == 1 => { let a = 0.2 + 0.6 * (1. - e.st / 0.7); let (x0, y0) = local(e, e.r, 0.); let (x1, y1) = local(e, 330., 0.);
            gx.dashed_line_world(x0, y0, x1, y1, 2., 10., 8., with_a(hex(PAL_HEX[c::DART as usize]), a)); }
        K::Boss1 if e.state == 2 && (e.p3 % 1.6) < 0.95 => { let a = 0.12 + 0.3 * ((e.p3 % 1.6) / 0.95); gx.rect_rot_world(e.x, e.y, e.ang, e.r * 0.5, 560., e.r * 1.6, with_a(hex(0xff3b6b), a), None); }
        K::Ray if e.state == 1 => { let k = 1. - e.st / 0.8; let ld = RAY_SPD * RAY_T + 20.; let ic = hex(PAL_HEX[c::ICE as usize]);
            gx.rect_rot_world(e.x, e.y, e.ang, e.r * 0.6, ld - e.r * 0.6, e.r * 1.5, with_a(ic, 0.1 + 0.3 * k), None);
            let (x0, y0) = local(e, e.r, 0.); let (x1, y1) = local(e, ld, 0.); gx.dashed_line_world(x0, y0, x1, y1, 2., 10., 8., with_a(if e.st < 0.3 { WHITE } else { ic }, 0.35 + 0.5 * k));
            gx.tri_world(local(e, ld + 14., 0.), local(e, ld - 4., -10.), local(e, ld - 4., 10.), with_a(ic, 0.35 + 0.5 * k)); }
        K::Lantern if e.state == 1 => { let k = 1. - e.st / 0.8; gx.arc_world(e.x, e.y, e.r * e.scale * (2.6 - 1.4 * k), 0., TAU, 2., with_a(hex(PAL_HEX[c::AMBER as usize]), 0.25 + 0.5 * k), false); }
        K::Spawner if e.state == 1 => { let k = 1. - e.st / 0.9; gx.dashed_arc_world(e.x, e.y, e.r * e.scale * (1.3 + 0.5 * k), t * 2., 2., 5., 6., with_a(hex(PAL_HEX[c::EEL as usize]), 0.25 + 0.5 * k)); }
        _ => {}
    }
}

fn anim_ph(gx: &Gfx, key: &str, e: &Enemy) -> f32 { gx.spr_anim(key).map(|a| e.a_t * a.freq() * TAU + e.phase).unwrap_or(0.) }

/// Угол нижней челюсти: в покое медленно «дышит», в атаке щёлкает (широко раскрыть — резко захлопнуть),
/// от попадания чуть вздрагивает. Плюс — раскрыта, минус — сжата.
fn jaw_anim(t: f32, attack: bool, hit: bool) -> f32 {
    if attack { let p = (t * 2.6).fract(); return if p < 0.55 { -0.06 + 0.42 * (p / 0.55).powf(0.7) } else { 0.36 - 0.5 * ((p - 0.55) / 0.45).min(1.).powf(0.35) }; }
    let breath = 0.07 + 0.09 * (t * 1.7).sin() + 0.05 * (t * 0.63).sin();
    breath + if hit { 0.08 } else { 0. }
}
fn boss1(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t; let lure = e.state == 1; let lt = if lure { ((3. - e.st) / 1.1).min(1.) } else { 0. };
    let bob = (t * 3.).sin() * 6.; let flip = e.ang.cos() < 0.;
    let (lx, ly) = local(e, e.r * 1.55, (-e.r * 1.15 + bob) * if flip { -1. } else { 1. });
    let jr = jaw_anim(t + e.phase, e.state == 1 || e.state == 2, wht); let tk = tkey("boss1", e.tier); gx.spr_jaw(&tk, e.x, e.y, e.ang, sc, wht, anim_ph(gx, &tk, e), jr);
    gx.glow_world(false, if lure { c::GOLD } else { c::CYAN }, lx, ly, 18. + lt * 50. + (t * 8.).sin() * 3., 1.);
    if lure && e.st < 1.9 { gx.glow_world(true, c::GOLD, lx, ly, 160., 0.25 + 0.15 * (t * 20.).sin()); }
}
fn boss2(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t; let pc = hex(PAL_HEX[c::PURP as usize]); let jc = hex(PAL_HEX[c::JELLY as usize]);
    for i in 0..6 { for j in 0..10 { let k = (i * 11 + j) * 2; let (ax, ay, bx, by) = (g.tent[k], g.tent[k + 1], g.tent[k + 2], g.tent[k + 3]);
            gx.line_world(ax, ay, bx, by, 22., with_a(pc, 0.3), true); gx.circle_world(bx, by, 11. * 1., with_a(pc, 0.0), true); }
        for j in 0..10 { let k = (i * 11 + j) * 2; gx.line_world(g.tent[k], g.tent[k + 1], g.tent[k + 2], g.tent[k + 3], 7., with_a(jc, 0.9), true); }
        for j in (2..=10).step_by(2) { let k = (i * 11 + j) * 2; gx.glow_world(false, c::JELLY, g.tent[k], g.tent[k + 1], 13. - j as f32 * 0.5, 1.); } }
    let pul = 1. + (t * 2.).sin() * 0.03;
    let tk = tkey("boss2", e.tier); gx.spr_world(&tk, e.x, e.y, 0., sc * pul, 1., wht, anim_ph(gx, &tk, e), false);
    let a = (g.p.y - e.y).atan2(g.p.x - e.x); let k = sc * pul;
    gx.set_add(false); let ws = gx.ws;
    draw_ellipse(gx.sx(e.x + a.cos() * 10. * k), gx.sy(e.y + a.sin() * 8. * k), 7. * k * ws, 17. * k * ws, 0., hex(0x1a0026));
    gx.circle_world(e.x + (a.cos() * 10. - 3.) * k, e.y + (a.sin() * 8. - 6.) * k, 2.5 * k, WHITE, false);
}
fn boss3(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t; let gc = hex(PAL_HEX[c::GOLD as usize]); let la = 0.35 + 0.2 * (t * 9.).sin();
    for i in 0..g.en.n { let cr = &g.en.items[i]; if cr.dead || cr.kind != K::Crystal { continue; } gx.line_world(e.x, e.y, cr.x, cr.y, 2., with_a(gc, la), true); }
    let ph = (t * 1.3) % 1.; let beat = (1. - ph * 6.).max(0.) + (1. - (ph - 0.22).abs() * 6.).max(0.) * 0.7;
    gx.glow_world(true, c::CRAB, e.x, e.y, e.r * (2.6 + beat * 0.8), 0.5 + beat * 0.5);
    if g.crystals > 0 { gx.arc_world(e.x, e.y, e.r * 1.25, 0., TAU, 3., with_a(gc, 0.25), true); }
    let tk = tkey("boss3", e.tier); gx.spr_world(&tk, e.x, e.y, t * 0.3, sc * (1. + beat * 0.07), 1., wht, 0., false);
    if e.state == 1 && e.st > 2.2 { gx.circle_world(e.x, e.y, e.r * 0.9, Color::new(0., 0., 0., ((3.4 - e.st) / 1.2).min(1.) * 0.6), false); }
}
fn boss4(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t; let a = e.ang; let (nx, ny) = (-a.sin(), a.cos());
    for k in 0..4 { let kf = k as f32; let phase = t * 4.2 - kf * 0.72; let bx = e.x - a.cos() * (e.r * (0.85 + kf * 0.5)); let by = e.y - a.sin() * (e.r * (0.85 + kf * 0.5));
        let sw = phase.sin() * (12. + kf * 5.); gx.glow_world(true, c::EEL, bx + nx * sw, by + ny * sw, e.r * (0.95 - kf * 0.12), (1. - kf / 4.) * 0.23); }
    gx.glow_world(true, c::EEL, e.x, e.y, e.r * 2.2, 0.48 + 0.18 * (t * 7.).sin());
    let lunge = e.state == 1 && (e.p3 % 1.7) > 1.; let pulse = 1. + (t * 5.2).sin() * 0.025 + if lunge { 0.045 } else { 0. };
    let jr = jaw_anim(t * 1.1 + e.phase, lunge, wht); let tk = tkey("boss4", e.tier); gx.spr_jaw(&tk, e.x, e.y, e.ang + (t * 2.4).sin() * 0.035, sc * pulse, wht, anim_ph(gx, &tk, e), jr);
    let flip = if e.ang.cos() < 0. { -1. } else { 1. };
    for k in 0..4 { let kf = k as f32; let (gx_, gy) = local(e, -e.r * (0.52 + kf * 0.12) * sc, e.r * (0.22 + kf * 0.08) * sc * flip); gx.glow_world(false, c::ICE, gx_, gy, 4.5, 0.38 + 0.22 * (t * 6. + kf * 0.8).sin()); }
}
fn king(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t;
    if e.state == 1 { let k = 1. - e.st / 0.9; let ld = KING_SPD * KING_T + 40.;
        gx.rect_rot_world(e.x, e.y, e.ang, e.r * 0.5, ld, e.r * 1.6, with_a(hex(0xffb340), 0.12 + 0.3 * k), Some((2.5, with_a(if e.st < 0.3 { WHITE } else { hex(0xffd54f) }, 0.5 + 0.4 * k)))); }
    else if e.state == 3 { let k = 1. - e.st / 0.9; gx.circle_world(e.x, e.y, KING_SLAM * k, with_a(hex(0xffb340), 0.1 + 0.25 * k), false);
        gx.arc_world(e.x, e.y, KING_SLAM, 0., TAU, 3., with_a(hex(0xffd54f), 0.5 + 0.4 * k), false); }
    let key_s = tkey(if e.sh <= 0. { "kingcrab_bare" } else { "kingcrab" }, e.tier); let key = key_s.as_str();
    let pul = 1. + (t * 2.2).sin() * 0.02 + if e.state == 3 { (1. - e.st / 0.9) * 0.08 } else { 0. } + if e.state == 6 { (t * 30.).sin() * 0.02 } else { 0. };
    let jr = if e.state == 3 { -0.15 } else { 0.11 * (t * 3.1 + e.phase).sin() + 0.05 }; gx.spr_jaw(key, e.x, e.y, e.ang, sc * pul, wht, anim_ph(gx, key, e), jr);
    if e.sh > 0. && e.tx > 0. { gx.arc_world(e.x, e.y, e.r * 1.15, e.ang - 0.95, e.ang + 0.95, 4., with_a(hex(0xfff0b0), 0.25 + 0.6 * (e.sh / e.tx)), true); }
}
fn queen(gx: &mut Gfx, g: &Game, e: &Enemy, sc: f32, wht: bool) {
    let t = g.t; let ic = hex(PAL_HEX[c::ICE as usize]); let qz = g.qz;
    if qz.n > 0 && qz.t > 0. { let k = 1. - qz.t;
        for i in 0..qz.n { let (x, y) = (qz.xs[i], qz.ys[i]);
            gx.circle_world(x, y, QZ_R * (0.3 + 0.7 * k), with_a(ic, 0.16 + 0.3 * k), false); gx.circle_world(x, y, QZ_R, with_a(ic, 0.12), false);
            gx.dashed_arc_world(x, y, QZ_R, t * 3., 4., 8., 6., with_a(if qz.t < 0.3 { WHITE } else { ic }, 0.7 + 0.3 * k)); } }
    if qz.rt > 0. { let k = 1. - qz.rt / 0.8; let col = with_a(if qz.rt < 0.25 { WHITE } else { hex(PAL_HEX[c::CYAN as usize]) }, 0.25 + 0.55 * k);
        for i in 0..qz.rn { let a = qz.ra + i as f32 * TAU / qz.rn as f32; gx.line_world(e.x + a.cos() * e.r, e.y + a.sin() * e.r, e.x + a.cos() * 620., e.y + a.sin() * 620., 1.5 + 2. * k, col, false); } }
    gx.glow_world(true, c::ICE, e.x, e.y, e.r * 2.6, 0.4 + 0.2 * (t * 5.).sin());
    let pul = 1. + (t * 2.6).sin() * 0.05;
    let qa = if g.p.x < e.x { std::f32::consts::PI } else { 0. }; let tk = tkey("queen", e.tier); gx.spr_world(&tk, e.x, e.y, qa, sc * pul, 1., wht, anim_ph(gx, &tk, e), false);
}

fn new_upg(gx: &mut Gfx, g: &Game) {
    if g.p.dead { return; } let t = g.t; let p = &g.p; let st = &g.st;
    if p.ink_t > 0. { gx.glow_world(true, c::PURP, p.ink_x, p.ink_y, 190., p.ink_t.min(1.) * if g.lv(crate::data::u::KRAKEN) > 0 { 0.5 } else { 0.35 }); }
    if st.aura_lv > 0 { let pu = 0.5 + 0.5 * (t * 3.).sin(); gx.glow_world(true, c::PURP, p.x, p.y, st.aura_r * 1.15, 0.07 + 0.05 * pu);
        gx.arc_world(p.x, p.y, st.aura_r, 0., TAU, 1.5, with_a(hex(PAL_HEX[c::PURP as usize]), 0.25 + 0.15 * pu), true); }
    let beam = |gx: &mut Gfx, x0: f32, y0: f32, i: i32, w: f32| { if i < 0 || i as usize >= g.en.n { return; } let e = &g.en.items[i as usize]; if e.dead { return; }
        gx.line_world(x0, y0, e.x, e.y, 9. * w, with_a(hex(PAL_HEX[c::ICE as usize]), 0.3), true); gx.line_world(x0, y0, e.x, e.y, 2.5 * w, with_a(hex(0xeaffff), 0.95), true);
        gx.glow_world(false, c::ICE, e.x, e.y, 14. * w, 0.8); };
    if st.beam_lv > 0 { beam(gx, p.x, p.y, p.beam_tg, 1. + 0.1 * st.beam_lv as f32);
        if p.beam_tg >= 0 && (p.beam_tg as usize) < g.en.n { let e = &g.en.items[p.beam_tg as usize]; beam(gx, e.x, e.y, p.beam_tg2, 0.7); } }
    if st.twin_lv > 0 { gx.glow_world(true, p.pal, p.tw_x, p.tw_y, 22., 0.8); gx.glow_world(false, c::WHITE, p.tw_x, p.tw_y, 7., 1.); }
}

fn player(gx: &mut Gfx, g: &mut Game, rdt: f32) {
    let t = g.t; let pal = g.p.pal; let pc = hex(PAL_HEX[pal as usize]);
    for k in 1..12 { let j = (g.trail_head + 12 - k) % 12; gx.glow_world(true, pal, g.trail[j * 2], g.trail[j * 2 + 1], 16. * (1. - k as f32 / 14.), (1. - k as f32 / 12.) * 0.55); }
    gx.glow_world(true, pal, g.p.x, g.p.y, if g.p.dash_t > 0. { 70. } else { 46. }, 0.55 + 0.15 * (t * 5.).sin());
    let skin = SKINS[g.p.skin].id; let key = format!("pl_{skin}");
    if !(g.p.inv > 0. && (t * 16.) as i32 % 2 == 1) {
        let v = hypot(g.p.vx, g.p.vy); let k = (v / g.st.speed.max(60.)).min(1.6); g.p.a_t += rdt * (0.5 + 1.1 * k);
        gx.sqx = if g.p.dash_t > 0. { 1.22 } else { 1. + 0.05 * k }; gx.sqy = if g.p.dash_t > 0. { 0.84 } else { 1. - 0.03 * k };
        if g.p.inv > 0.75 { gx.sqx *= 0.9; gx.sqy *= 1.1; }
        let ph = gx.spr_anim(&key).map(|a| g.p.a_t * a.freq() * TAU).unwrap_or(0.);
        gx.spr_world(&key, g.p.x, g.p.y, g.p.ang + (t * 3.).sin() * 0.05, 1., 1., false, ph, false);
        gx.sqx = 1.; gx.sqy = 1.;
    }
    let (px, py) = (g.p.x, g.p.y);
    // орнамент редких обликов
    let orn = match skin { "void" => "void", "aurora" => "ribbon", "solar" | "royal" => "crown", "venom" => "spikes", "nebula" => "orbit", "cyber" => "hex", "lunar" => "moon",
        "inferno" => "flame", "abyss" => "shards", "jade" => "leaf", "prism" => "prism", _ => "" };
    let oa = t * if orn == "orbit" { 1.35 } else { 2.1 };
    if orn == "orbit" || orn == "hex" || orn == "prism" {
        for k in 0..3 { let a = oa + k as f32 * TAU / 3.; let rr = if orn == "orbit" { 28. } else { 24. }; let (x, y) = (px + a.cos() * rr, py + a.sin() * rr);
            gx.arc_world(x, y, if orn == "hex" { 5. } else { 3.5 }, a, a + std::f32::consts::PI * 1.55, 1.5, with_a(pc, 0.75), true);
            gx.glow_world(false, pal, x, y, if orn == "prism" { 7. } else { 4. }, 0.75); }
    } else if !orn.is_empty() {
        for k in 0..4 { let a = oa + k as f32 * TAU / 4.; let rr = if orn == "crown" { 24. } else { 30. }; let (x, y) = (px + a.cos() * rr, py + a.sin() * rr);
            gx.glow_world(false, pal, x, y, if orn == "flame" { 7. } else { 5. }, 0.72);
            gx.line_world(px + a.cos() * 15., py + a.sin() * 15., x, y, 1.2, with_a(pc, 0.8), true); }
    }
    for k in 0..3 { let a = t * 3. + k as f32 * TAU / 3.; gx.glow_world(false, pal, px + a.cos() * 21., py + a.sin() * 21., 5., 1.); }
    for i in 0..g.st.orb_n as usize { gx.glow_world(false, c::DRIFT, g.orb[i * 2], g.orb[i * 2 + 1], 16., 1.); gx.glow_world(false, c::WHITE, g.orb[i * 2], g.orb[i * 2 + 1], 6., 1.); }
    if g.st.orb_n > 0 { gx.arc_world(px, py, 64., 0., TAU, 1.5, with_a(hex(PAL_HEX[c::DRIFT as usize]), 0.12), false); }
    for k in 0..g.p.shield.max(0) { gx.arc_world(px, py, g.p.r + 12. + k as f32 * 5., 0., TAU, 2., Color::new(1., 1., 1., 0.4 + 0.2 * (t * 4. + k as f32).sin()), false); }
    if g.pull_t > 0. { gx.dashed_line_world(px, py, g.pull_x, g.pull_y, 2., 6., 10., with_a(hex(PAL_HEX[c::GOLD as usize]), 0.5)); }
}

/// Плывущие силуэты существ на титульном экране
pub fn title_demo(gx: &mut Gfx, rd: &mut Rd, t: f32, dt: f32, am: f32) {
    let (w, h, p) = (gx.w, gx.h, gx.px);
    for d in rd.demo.iter_mut() {
        d.y -= d.sp * dt / h; if d.y < -0.1 { d.y = 1.1; d.x = rand::gen_range(0., 1.); }
        let x = d.x * w + (t * 0.4 + d.p).sin() * 30.; let y = d.y * h; let a = -std::f32::consts::FRAC_PI_2 + (t * 0.7 + d.p).sin() * 0.4;
        let ph = gx.spr_anim(d.k).map(|an| t * an.freq() * TAU + d.p).unwrap_or(0.);
        gx.spr_screen(d.k, x * p, y * p, a, d.s * p, 0.72 * am, false, ph, true);
    }
    gx.glow_scr(true, c::CYAN, w / 2. * p, h * 0.22 * p, w.min(h) * 0.55 * p, (0.5 + 0.2 * (t * 2.).sin()) * am);
}

/// Виньетка и красная пульсация при малом здоровье
pub fn overlay(gx: &mut Gfx, g: &Game) {
    let v = gx.vign.clone(); gx.tex_full(&v, WHITE);
    let lh = low_hp(g);
    if g.hurt_flash > 0. || lh { let a = (g.hurt_flash * 0.7).max(if lh { 0.16 + 0.1 * (g.t * 6.).sin() } else { 0. }).min(0.7); let h = gx.hurt.clone(); gx.tex_full(&h, Color::new(1., 1., 1., a)); }
    if g.flash > 0. { gx.fill_screen(Color::new(1., 0.95, 0.8, g.flash * 0.6), true); }
}
