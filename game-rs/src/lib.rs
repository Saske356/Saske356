//! «Свет Бездны» на Rust (macroquad): игра целиком — мир, существа, интерфейс, звук, реклама.
pub mod data; pub mod i18n; pub mod save; pub mod game; pub mod enemies; pub mod gfx; pub mod render; pub mod ui; pub mod audio; pub mod platform; pub mod flow;
pub mod app; pub mod hud; pub mod screens;
use macroquad::prelude::*;

pub fn conf() -> Conf {
    let env = |k: &str, d: i32| std::env::var(k).ok().and_then(|v| v.parse().ok()).unwrap_or(d);
    Conf { window_title: "Light of the Abyss".into(), high_dpi: true, window_width: env("SVET_W", 390), window_height: env("SVET_H", 844), sample_count: 1,
        platform: macroquad::miniquad::conf::Platform { swap_interval: Some(1), ..Default::default() }, ..Default::default() }
}

pub async fn run() {
    let mut app = app::App::new().await;
    loop { app.frame().await; next_frame().await; }
}

#[cfg(target_os = "android")]
#[no_mangle]
pub extern "C" fn quad_main() { macroquad::Window::from_config(conf(), run()); }
