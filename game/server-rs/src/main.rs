//! ONIKS RP — игровой сервер на Rust. Настройки — переменные окружения (см. README).

use std::path::PathBuf;

use oniks_server::{env, find_game_dir, serve, world, Options};
use serde_json::{json, Value};

#[global_allocator]
static ALLOC: mimalloc::MiMalloc = mimalloc::MiMalloc;

#[tokio::main(flavor = "current_thread")]
async fn main() {
    if std::env::args().any(|a| a == "--dump-world") {
        // для проверки совпадения с клиентским генератором
        let c = world::generate_city();
        let b: Vec<Value> = c.buildings.iter().map(|b| json!([b.r.x0, b.r.z0, b.r.x1, b.r.z1, b.h, b.color])).collect();
        let o: Vec<Value> = c.boxes.iter().map(|o| json!([o.r.x0, o.r.z0, o.r.x1, o.r.z1])).collect();
        println!("{}", json!({ "deliveries": c.deliveries, "route": world::bus_route(), "buildings": b, "trees": c.trees,
                               "parks": c.parks.len(), "decor": c.decor.len(), "boxes": o }));
        return;
    }
    let game_dir = find_game_dir();
    if !game_dir.join("public").is_dir() {
        eprintln!("Не найдена папка игры (нет {}/public). Укажите GAME_DIR.", game_dir.display());
        std::process::exit(1);
    }
    let port: u16 = env("PORT", "3000").parse().unwrap_or(3000);
    let data_dir = std::env::var("DATA_DIR").map(PathBuf::from).unwrap_or_else(|_| game_dir.join("data"));
    let version = std::fs::read_to_string(game_dir.join("package.json")).ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .and_then(|v| v.get("version").and_then(|x| x.as_str()).map(String::from))
        .unwrap_or_else(|| "0.0.0".into());
    let opts = Options {
        data_dir,
        game_dir: Some(game_dir),
        name: env("SERVER_NAME", "ONIKS #1"),
        color: env("SERVER_COLOR", "#ff8a3d"),
        max_players: env("MAX_PLAYERS", "100").parse().unwrap_or(100),
        version,
        admins: env("ADMINS", "Linar_Safin").split(',').map(String::from).collect(),
        owner_all: false,
    };
    let listener = tokio::net::TcpListener::bind(("0.0.0.0", port)).await.unwrap_or_else(|e| {
        eprintln!("Не удалось открыть порт {port}: {e}");
        std::process::exit(1);
    });
    println!("ONIKS RP (Rust) запущен: http://localhost:{port}");
    let shutdown = async {
        let ctrl_c = tokio::signal::ctrl_c();
        #[cfg(unix)]
        {
            let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).unwrap();
            tokio::select! { _ = ctrl_c => {}, _ = term.recv() => {} }
        }
        #[cfg(not(unix))]
        let _ = ctrl_c.await;
    };
    serve(opts, listener, shutdown).await;
    println!("База сохранена, сервер остановлен");
}
