//! ONIKS RP — игровой сервер на Rust.
//! Раздаёт клиент и игровой кэш, ведёт мультиплеер по WebSocket. Совместим с прежним
//! сервером на Node.js: тот же протокол, тот же формат players.json и паролей (scrypt).

pub mod game;
pub use novo_world as world;


use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime};

use axum::extract::ws::{Message, Utf8Bytes, WebSocket, WebSocketUpgrade};
use axum::extract::State;
use axum::http::{header, HeaderValue};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio::sync::mpsc;
use tower_http::services::ServeDir;
use tower_http::set_header::SetResponseHeaderLayer;

use game::{Config, Game, Profile};

struct App {
    pub game: Mutex<Game>,
    /// scrypt берёт 16 МБ памяти на вход — ограничиваем число одновременных проверок паролей.
    hashing: tokio::sync::Semaphore,
    /// Папка игры со статикой (public/, shared/, cache/). Нет — сервер только для игры по WebSocket.
    game_dir: Option<PathBuf>,
    db_file: PathBuf,
    manifest: Mutex<(SystemTime, String, HashMap<PathBuf, (SystemTime, u64, String)>)>,
}
type Shared = Arc<App>;

pub fn env(key: &str, default: &str) -> String {
    std::env::var(key).ok().filter(|v| !v.is_empty()).unwrap_or_else(|| default.to_string())
}

/// Папка игры: GAME_DIR, иначе текущая (если в ней есть public/), иначе родительская.
pub fn find_game_dir() -> PathBuf {
    if let Ok(d) = std::env::var("GAME_DIR") {
        return PathBuf::from(d);
    }
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    if cwd.join("public").is_dir() { cwd } else { cwd.join("..") }
}

// ---------- база игроков ----------
fn load_db(file: &Path) -> HashMap<String, Profile> {
    match std::fs::read_to_string(file) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|e| {
            eprintln!("Не удалось прочитать {}: {e}. Сервер не запущен, чтобы не потерять аккаунты.", file.display());
            std::process::exit(1);
        }),
        Err(_) => HashMap::new(),
    }
}

fn save_db(app: &App) {
    let text = {
        let mut g = app.game.lock().unwrap();
        g.store_positions();
        g.dirty = false;
        serde_json::to_string(&g.db).unwrap()
    };
    let tmp = app.db_file.with_extension("json.tmp");
    if let Some(dir) = app.db_file.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Err(e) = std::fs::write(&tmp, text).and_then(|_| std::fs::rename(&tmp, &app.db_file)) {
        eprintln!("Ошибка сохранения базы: {e}");
    }
}

/// scrypt с параметрами Node.js по умолчанию (N=16384, r=8, p=1, 32 байта); соль — hex-строка как текст.
fn hash_pass(pass: &str, salt: &str) -> String {
    let params = scrypt::Params::new(14, 8, 1, 32).unwrap();
    let mut out = [0u8; 32];
    scrypt::scrypt(pass.as_bytes(), salt.as_bytes(), &params, &mut out).unwrap();
    hex::encode(out)
}
fn same(a: &str, b: &str) -> bool {
    a.len() == b.len() && a.bytes().zip(b.bytes()).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn valid_name(name: &str) -> bool {
    let Some((a, b)) = name.split_once('_') else { return false };
    let part = |s: &str| {
        let mut c = s.chars();
        matches!(c.next(), Some(f) if f.is_ascii_uppercase()) && (2..=16).contains(&s.len()) && c.all(|x| x.is_ascii_lowercase())
    };
    part(a) && part(b)
}

async fn login(app: &Shared, m: &Value, tx: &game::Tx) -> Result<i64, String> {
    let name = m.get("name").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
    let pass = m.get("pass").and_then(|v| v.as_str()).unwrap_or("").to_string();
    if !valid_name(&name) {
        return Err("Ник должен быть в формате Имя_Фамилия латиницей, например Ivan_Petrov".into());
    }
    let plen = pass.encode_utf16().count();
    if !(4..=64).contains(&plen) {
        return Err("Пароль должен быть от 4 до 64 символов".into());
    }
    let key = name.to_lowercase();
    let existing = {
        let g = app.game.lock().unwrap();
        g.can_join(&key).map_err(String::from)?;
        g.db.get(&key).map(|p| (p.salt.clone(), p.hash.clone()))
    };
    // scrypt — тяжёлая операция, считаем вне игрового цикла
    let salt = existing.as_ref().map(|e| e.0.clone()).unwrap_or_else(|| hex::encode(rand::random::<[u8; 16]>()));
    let (p2, s2) = (pass.clone(), salt.clone());
    let permit = app.hashing.acquire().await.map_err(|_| "Ошибка сервера".to_string())?;
    let hash = tokio::task::spawn_blocking(move || hash_pass(&p2, &s2)).await.map_err(|_| "Ошибка сервера".to_string())?;
    drop(permit);
    let mut g = app.game.lock().unwrap();
    g.can_join(&key).map_err(String::from)?;
    let is_new = match &existing {
        Some((_, h)) => {
            if !same(&hash, h) {
                return Err("Неверный пароль".into());
            }
            false
        }
        None => {
            if g.db.contains_key(&key) {
                return Err("Попробуйте ещё раз".into());
            }
            let created = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map_or(0, |d| d.as_millis() as i64);
            g.db.insert(key.clone(), Profile {
                name: name.clone(), salt, hash, money: 2000, level: 1, exp: 0, license: false, cars: vec![], pos: None,
                created, stats: Default::default(), extra: Default::default(),
            });
            g.dirty = true;
            true
        }
    };
    Ok(g.join(key, tx.clone(), is_new))
}

// ---------- WebSocket ----------
async fn ws_route(ws: WebSocketUpgrade, State(app): State<Shared>) -> Response {
    // сообщения у нас маленькие — огромные буферы по умолчанию (128 КБ) не нужны
    ws.max_message_size(8192).read_buffer_size(4096).write_buffer_size(16 * 1024).on_upgrade(move |s| client(s, app))
}

async fn client(socket: WebSocket, app: Shared) {
    let (mut sink, mut stream) = socket.split();
    let (tx, mut rx) = mpsc::channel::<Utf8Bytes>(256);
    let writer = tokio::spawn(async move {
        // всё, что накопилось в очереди, отправляем одним системным вызовом
        while let Some(m) = rx.recv().await {
            if sink.feed(Message::Text(m)).await.is_err() {
                return;
            }
            while let Ok(m) = rx.try_recv() {
                if sink.feed(Message::Text(m)).await.is_err() {
                    return;
                }
            }
            if sink.flush().await.is_err() {
                return;
            }
        }
    });
    let mut pid: Option<i64> = None;
    while let Some(Ok(msg)) = stream.next().await {
        let text = match msg {
            Message::Text(t) => t,
            Message::Close(_) => break,
            _ => continue,
        };
        let Ok(m) = serde_json::from_str::<Value>(text.as_str()) else { continue };
        let Some(t) = m.get("t").and_then(|v| v.as_str()) else { continue };
        match pid {
            None => {
                if t == "login" {
                    match login(&app, &m, &tx).await {
                        Ok(id) => pid = Some(id),
                        Err(e) => { let _ = tx.try_send(Utf8Bytes::from(json!({ "t": "error", "text": e }).to_string())); }
                    }
                }
            }
            Some(id) => app.game.lock().unwrap().handle(id, t, &m),
        }
    }
    if let Some(id) = pid {
        app.game.lock().unwrap().leave(id);
    }
    writer.abort();
}

// ---------- API ----------
async fn status(State(app): State<Shared>) -> impl IntoResponse {
    let news: Value = app.game_dir.as_ref().and_then(|d| std::fs::read_to_string(d.join("news.json")).ok())
        .and_then(|s| serde_json::from_str(&s).ok()).unwrap_or(json!([]));
    let g = app.game.lock().unwrap();
    let body = json!({ "name": g.cfg.name, "color": g.cfg.color, "online": g.players.len(), "max": g.cfg.max_players,
                       "version": g.cfg.version, "news": news });
    ([(header::CONTENT_TYPE, "application/json; charset=utf-8")], body.to_string())
}

fn walk(dir: &Path, prefix: &str, out: &mut Vec<(String, PathBuf)>) {
    let Ok(rd) = std::fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let name = e.file_name().to_string_lossy().to_string();
        if name.starts_with('.') {
            continue;
        }
        let p = e.path();
        if p.is_dir() {
            walk(&p, &format!("{prefix}{name}/"), out);
        } else if p.is_file() {
            out.push((format!("{prefix}{name}"), p));
        }
    }
}

/// Список файлов игрового кэша: «version X», затем «sha256 размер /путь».
fn build_manifest(app: &App) -> String {
    let mut lock = app.manifest.lock().unwrap();
    let (at, text, hashes) = &mut *lock;
    if at.elapsed().map_or(false, |e| e < Duration::from_secs(5)) && !text.is_empty() {
        return text.clone();
    }
    let Some(gd) = app.game_dir.as_ref() else { return String::new() };
    let mut files = Vec::new();
    walk(&gd.join("public"), "/", &mut files);
    walk(&gd.join("shared"), "/shared/", &mut files);
    walk(&gd.join("cache"), "/cache/", &mut files);
    files.push(("/vendor/three.module.js".into(), gd.join("node_modules/three/build/three.module.js")));
    files.sort();
    let version = app.game.lock().unwrap().cfg.version.clone();
    let mut out = format!("version {version}\n");
    for (p, full) in files {
        if p.contains(char::is_whitespace) {
            continue;
        }
        let Ok(meta) = std::fs::metadata(&full) else { continue };
        let mtime = meta.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let sha = match hashes.get(&full) {
            Some((m, s, h)) if *m == mtime && *s == meta.len() => h.clone(),
            _ => {
                let Ok(bytes) = std::fs::read(&full) else { continue };
                let h = hex::encode(Sha256::digest(&bytes));
                hashes.insert(full.clone(), (mtime, meta.len(), h.clone()));
                h
            }
        };
        out.push_str(&format!("{sha} {} {p}\n", meta.len()));
    }
    *at = SystemTime::now();
    *text = out.clone();
    out
}

async fn manifest(State(app): State<Shared>) -> impl IntoResponse {
    let text = tokio::task::spawn_blocking(move || build_manifest(&app)).await.unwrap_or_default();
    ([(header::CONTENT_TYPE, "text/plain; charset=utf-8")], text)
}

pub struct Options {
    pub data_dir: PathBuf,
    pub game_dir: Option<PathBuf>,
    pub name: String,
    pub color: String,
    pub max_players: usize,
    pub version: String,
}

/// Запускает сервер на готовом сокете и работает до `shutdown`; перед выходом сохраняет базу.
pub async fn serve(opts: Options, listener: tokio::net::TcpListener, shutdown: impl std::future::Future<Output = ()> + Send + 'static) {
    let db_file = opts.data_dir.join("players.json");
    let color = opts.color;
    let cfg = Config {
        name: opts.name,
        color: if color.len() == 7 && color.starts_with('#') && color[1..].chars().all(|c| c.is_ascii_hexdigit()) { color } else { "#ff8a3d".into() },
        max_players: opts.max_players,
        version: opts.version,
    };
    let game_dir = opts.game_dir.filter(|d| d.join("public").is_dir());
    let app: Shared = Arc::new(App {
        game: Mutex::new(Game::new(cfg, load_db(&db_file))),
        hashing: tokio::sync::Semaphore::new(std::thread::available_parallelism().map_or(2, |n| n.get())),
        game_dir: game_dir.clone(),
        db_file,
        manifest: Mutex::new((SystemTime::UNIX_EPOCH, String::new(), HashMap::new())),
    });

    // снимки мира 15 раз в секунду
    let a = app.clone();
    tokio::spawn(async move {
        let mut iv = tokio::time::interval(Duration::from_millis(66));
        iv.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            iv.tick().await;
            a.game.lock().unwrap().snapshots();
        }
    });
    // PayDay и сохранение базы
    let a = app.clone();
    tokio::spawn(async move {
        let mut iv = tokio::time::interval(Duration::from_secs(1));
        let mut n = 0u64;
        loop {
            iv.tick().await;
            a.game.lock().unwrap().tick_second();
            n += 1;
            if n % 2 == 0 && a.game.lock().unwrap().dirty {
                let a2 = a.clone();
                let _ = tokio::task::spawn_blocking(move || save_db(&a2)).await;
            }
        }
    });

    let cors = SetResponseHeaderLayer::overriding(header::ACCESS_CONTROL_ALLOW_ORIGIN, HeaderValue::from_static("*"));
    let nocache = SetResponseHeaderLayer::overriding(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    let mut router = Router::new()
        .route("/ws", get(ws_route))
        .route("/api/status", get(status))
        .route("/api/manifest", get(manifest));
    if let Some(gd) = &game_dir {
        router = router
            .nest_service("/shared", ServeDir::new(gd.join("shared")))
            .nest_service("/vendor", ServeDir::new(gd.join("node_modules/three/build")))
            .nest_service("/cache", ServeDir::new(gd.join("cache")))
            .fallback_service(ServeDir::new(gd.join("public")));
    }
    let router = router.layer(cors).layer(nocache).with_state(app.clone());
    let a = app.clone();
    let _ = axum::serve(listener, router)
        .with_graceful_shutdown(async move {
            shutdown.await;
            save_db(&a);
        })
        .await;
}

/// Одиночная игра: сервер в фоновом потоке на 127.0.0.1, свободный порт. Возвращает порт.
pub fn start_local(data_dir: PathBuf) -> std::io::Result<u16> {
    let std_listener = std::net::TcpListener::bind(("127.0.0.1", 0))?;
    std_listener.set_nonblocking(true)?;
    let port = std_listener.local_addr()?.port();
    std::thread::Builder::new().name("local-server".into()).spawn(move || {
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().expect("tokio");
        rt.block_on(async move {
            let listener = tokio::net::TcpListener::from_std(std_listener).expect("сокет");
            let opts = Options {
                data_dir, game_dir: None, name: "Одиночная игра".into(), color: "#5ccf7a".into(), max_players: 4,
                version: env!("CARGO_PKG_VERSION").into(),
            };
            serve(opts, listener, std::future::pending()).await;
        });
    })?;
    Ok(port)
}
