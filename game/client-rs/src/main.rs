//! ONIKS RP — клиент на Rust (Bevy).
//!
//!   oniks-client                       — «Сервер 1» офлайн: сервер запускается внутри клиента
//!   oniks-client --map district1       — офлайн на карте из cache/brmap/district1.glb
//!   oniks-client --server 1.2.3.4:3000 — игра по сети
//!   --name Ivan_Petrov --pass 1234     — персонаж (по умолчанию Linar_Safin)
//!   --low                              — без теней (слабые устройства)
//! Для проверок: --cmd "/spcar supra" (команда после входа), --enter (сесть в машину),
//! --forward 3 (ехать/идти вперёд N секунд), --screenshot файл.png --at 8 (снимок и выход).

mod hud;
mod models;
mod net;
mod play;
mod scene;
mod state;

use std::path::PathBuf;

use bevy::diagnostic::FrameTimeDiagnosticsPlugin;
use bevy::prelude::*;
use bevy::render::view::screenshot::{save_to_disk, Screenshot};
use bevy::window::PresentMode;

use state::{Game, Launch};

#[derive(Resource, Default)]
pub struct Debug {
    pub cmds: Vec<String>,
    pub enter: bool,
    pub forward: f32,
    pub forward_until: f32,
    pub press_f: bool,
    pub screenshot: Option<(String, f32)>,
    started: Option<f32>,
    stage: u8,
    shot_frame: u32,
}

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

/// Папка игры: где лежат cache/ (модели, карта). ONIKS_GAME_DIR, иначе ищем рядом.
fn find_game_dir() -> PathBuf {
    if let Ok(d) = std::env::var("ONIKS_GAME_DIR") {
        return PathBuf::from(d);
    }
    let mut cands = vec![std::env::current_dir().unwrap_or_default()];
    if let Ok(exe) = std::env::current_exe() {
        for a in exe.ancestors().skip(1).take(4) {
            cands.push(a.to_path_buf());
        }
    }
    for c in cands.clone() {
        for d in [c.clone(), c.join(".."), c.join("game")] {
            if d.join("cache").is_dir() || d.join("public").is_dir() {
                return d.canonicalize().unwrap_or(d);
            }
        }
    }
    cands[0].clone()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let game_dir = find_game_dir();
    let server = arg(&args, "--server");
    let name = arg(&args, "--name").unwrap_or_else(|| "Linar_Safin".into());
    let pass = arg(&args, "--pass").unwrap_or_else(|| "offline".into());
    let map = arg(&args, "--map");
    let low = args.iter().any(|a| a == "--low");

    // офлайн: свой сервер в фоновом потоке, база — в data-local
    let addr = match &server {
        Some(s) => s.clone(),
        None => {
            let data = game_dir.join(if map.is_some() { "data-local-map" } else { "data-local" });
            let port = oniks_server::start_local(data).expect("не удалось запустить офлайн-сервер");
            format!("127.0.0.1:{port}")
        }
    };
    let net = net::connect(&addr, &name, &pass);
    let debug = Debug {
        cmds: args.windows(2).filter(|w| w[0] == "--cmd").map(|w| w[1].clone()).collect(),
        enter: args.iter().any(|a| a == "--enter"),
        forward: arg(&args, "--forward").and_then(|s| s.parse().ok()).unwrap_or(0.0),
        screenshot: arg(&args, "--screenshot").map(|p| (p, arg(&args, "--at").and_then(|s| s.parse().ok()).unwrap_or(8.0))),
        ..default()
    };

    App::new()
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "ONIKS RP".into(),
                        resolution: (1280.0_f32, 720.0_f32).into(),
                        present_mode: PresentMode::AutoVsync,
                        ..default()
                    }),
                    ..default()
                })
                .set(AssetPlugin { file_path: game_dir.to_string_lossy().into_owned(), ..default() }),
        )
        .add_plugins(FrameTimeDiagnosticsPlugin::default())
        .insert_resource(Launch { game_dir: game_dir.clone(), map, offline: server.is_none(), quality_shadows: !low })
        .insert_resource(Game::new())
        .insert_resource(net)
        .insert_resource(debug)
        .insert_resource(models::CarAssets { info: models::load_car_index(&Launch {
            game_dir, map: None, offline: true, quality_shadows: true }), ..default() })
        .add_systems(Startup, (scene::setup, hud::setup_hud))
        .add_systems(Update, (
            scene::build_map_collider,
            play::net_receive,
            play::chat_input,
            play::local_control,
            models::setup_car_models,
            play::interpolate,
            scene::update_camera,
            scene::update_sky,
            hud::update_hud,
            debug_driver,
        ).chain())
        .run();
}

/// Сценарий для автоматических проверок: команды, посадка, движение, скриншот.
fn debug_driver(
    mut commands: Commands,
    time: Res<Time>,
    mut dbg: ResMut<Debug>,
    game: Res<Game>,
    net: Res<net::Net>,
    mut exit: EventWriter<AppExit>,
) {
    let now = time.elapsed_secs();
    if !game.connected {
        return;
    }
    let t0 = *dbg.started.get_or_insert(now);
    if dbg.stage == 0 && now - t0 > 2.0 {
        for c in dbg.cmds.clone() {
            net.send(serde_json::json!({ "t": "chat", "text": c }));
        }
        dbg.stage = 1;
    }
    if dbg.stage == 1 && now - t0 > 4.0 {
        if dbg.enter {
            dbg.press_f = true;
        }
        dbg.stage = 2;
    }
    if dbg.stage == 2 && now - t0 > 5.0 {
        if dbg.forward > 0.0 {
            dbg.forward_until = now + dbg.forward;
        }
        dbg.stage = 3;
    }
    if let Some((path, at)) = dbg.screenshot.clone() {
        if dbg.stage == 3 && now - t0 > at {
            commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
            dbg.stage = 4;
        } else if dbg.stage == 4 {
            dbg.shot_frame += 1;
            if dbg.shot_frame > 30 {
                info!("снимок готов: x={:.1} z={:.1} y={:.1} машина={} деньги={}", game.pos.x, game.pos.z, game.pos.y, game.veh, game.money);
                exit.write(AppExit::Success);
            }
        }
    }
}
