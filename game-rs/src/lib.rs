//! «Свет Бездны» на Rust (macroquad). Прототип движка: проверка скорости на телефоне.
use macroquad::prelude::*;

pub fn conf() -> Conf {
    Conf { window_title: "Light of the Abyss".into(), high_dpi: true, window_width: 390, window_height: 844, sample_count: 1, ..Default::default() }
}

struct Foe { p: Vec2, v: Vec2, k: usize, ph: f32 }

async fn tex(path: &str) -> Texture2D {
    let t = load_texture(path).await.unwrap_or_else(|_| Texture2D::from_rgba8(1, 1, &[255, 255, 255, 255]));
    t.set_filter(FilterMode::Linear); t
}

pub async fn run() {
    let names = ["jelly", "drifter", "dart", "squid", "crab"];
    let mut texs = Vec::new();
    for n in names { texs.push(tex(&format!("art/{n}.png")).await); }
    let lumen = tex("art/lumen.png").await;
    let mut foes: Vec<Foe> = (0..400).map(|i| Foe { p: vec2(rand::gen_range(-800., 800.), rand::gen_range(-800., 800.)), v: Vec2::ZERO, k: i % 5, ph: rand::gen_range(0., 6.28) }).collect();
    let mut me = Vec2::ZERO; let mut touch0: Option<(Vec2, Vec2)> = None; let mut t = 0.0f32;
    let (mut fps_acc, mut fps_n, mut fps_show) = (0.0f32, 0, 0.0f32);
    loop {
        let dt = get_frame_time().min(0.05); t += dt;
        fps_acc += dt; fps_n += 1; if fps_acc > 0.5 { fps_show = fps_n as f32 / fps_acc; fps_acc = 0.0; fps_n = 0; }
        // управление: тянем пальцем в любом месте экрана
        let tp: Option<Vec2> = touches().first().map(|t| t.position).or_else(|| if is_mouse_button_down(MouseButton::Left) { Some(mouse_position().into()) } else { None });
        match (tp, touch0) {
            (Some(p), None) => touch0 = Some((p, me)),
            (Some(p), Some((p0, m0))) => { let tgt = m0 + (p - p0) * 1.6; me += (tgt - me) * (dt * 10.0).min(1.0); }
            (None, _) => touch0 = None,
        }
        for f in foes.iter_mut() { let d = me - f.p; let l = d.length().max(1.0); f.v += d / l * 60.0 * dt; f.v *= 0.98; f.p += f.v * dt; f.ph += dt * 3.0; }
        let (w, h) = (screen_width(), screen_height()); let sc = (w.min(h) / 450.0).clamp(0.8, 2.5);
        let cam = me;
        clear_background(Color::from_hex(0x04203a));
        for f in &foes { let s = (f.p - cam) * sc + vec2(w / 2., h / 2.); if s.x < -80. || s.y < -80. || s.x > w + 80. || s.y > h + 80. { continue; }
            let size = 56.0 * sc * (1.0 + 0.06 * f.ph.sin()); let a = f.v.y.atan2(f.v.x);
            let flip = f.v.x < 0.0;
            draw_texture_ex(&texs[f.k], s.x - size / 2., s.y - size / 2., WHITE, DrawTextureParams { dest_size: Some(vec2(size, size)), rotation: if flip { a + std::f32::consts::PI } else { a }, flip_x: flip, ..Default::default() }); }
        let ls = 60.0 * sc; draw_texture_ex(&lumen, w / 2. - ls / 2., h / 2. - ls / 2., WHITE, DrawTextureParams { dest_size: Some(vec2(ls, ls)), ..Default::default() });
        draw_rectangle(10., 10., 330. * sc / 1.5, 60., Color::new(0., 0., 0., 0.5));
        draw_text(&format!("FPS {:.0}  creatures {}", fps_show, foes.len()), 20., 52., 40. * sc / 1.5, WHITE);
        next_frame().await;
    }
}

#[cfg(target_os = "android")]
#[no_mangle]
pub extern "C" fn quad_main() { macroquad::Window::from_config(conf(), run()); }
