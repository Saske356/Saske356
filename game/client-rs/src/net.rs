//! Сеть: отдельный поток держит WebSocket, разбирает JSON и передаёт события в игру.
//! Игровой кадр никогда не ждёт сеть.

use std::io::ErrorKind;
use std::net::TcpStream;
use std::time::Duration;

use bevy::prelude::*;
use crossbeam_channel::{unbounded, Receiver, Sender};
use serde_json::{json, Value};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket};

pub enum NetEvent {
    Connected,
    /// Любое сообщение сервера (welcome, snap, chat, notify, profile, job, entered, exited, error).
    Msg(Value),
    Closed(String),
}

#[derive(Resource)]
pub struct Net {
    tx: Sender<String>,
    pub rx: Receiver<NetEvent>,
}

impl Net {
    pub fn send(&self, v: Value) {
        let _ = self.tx.send(v.to_string());
    }
}

/// `http://host:port`, `host:port` или `ws://host:port/ws` → адрес WebSocket.
pub fn ws_url(server: &str) -> String {
    let s = server.trim().trim_end_matches('/');
    let base = s.strip_prefix("http://").or_else(|| s.strip_prefix("ws://")).unwrap_or(s);
    let base = base.trim_end_matches("/ws");
    format!("ws://{base}/ws")
}

pub fn connect(server: &str, name: &str, pass: &str) -> Net {
    let (out_tx, out_rx) = unbounded::<String>();
    let (in_tx, in_rx) = unbounded::<NetEvent>();
    let url = ws_url(server);
    let login = json!({ "t": "login", "name": name, "pass": pass }).to_string();
    std::thread::Builder::new()
        .name("net".into())
        .spawn(move || {
            let reason = match run(&url, &login, &out_rx, &in_tx) {
                Ok(()) => "Соединение закрыто".to_string(),
                Err(e) => e,
            };
            let _ = in_tx.send(NetEvent::Closed(reason));
        })
        .expect("сетевой поток");
    Net { tx: out_tx, rx: in_rx }
}

fn run(url: &str, login: &str, out: &Receiver<String>, inc: &Sender<NetEvent>) -> Result<(), String> {
    let (mut ws, _) = tungstenite::connect(url).map_err(|e| format!("Нет связи с сервером {url}: {e}"))?;
    set_timeout(&mut ws);
    ws.send(Message::text(login)).map_err(|e| e.to_string())?;
    let _ = inc.send(NetEvent::Connected);
    loop {
        // всё, что игра хочет отправить
        let mut wrote = false;
        while let Ok(m) = out.try_recv() {
            ws.write(Message::text(m)).map_err(|e| e.to_string())?;
            wrote = true;
        }
        if wrote {
            ws.flush().map_err(|e| e.to_string())?;
        }
        // входящие (короткое ожидание, чтобы не крутить процессор)
        match ws.read() {
            Ok(Message::Text(t)) => {
                if let Ok(v) = serde_json::from_str::<Value>(t.as_str()) {
                    if inc.send(NetEvent::Msg(v)).is_err() {
                        return Ok(()); // игра закрылась
                    }
                }
            }
            Ok(Message::Close(_)) => return Ok(()),
            Ok(_) => {}
            Err(tungstenite::Error::Io(e)) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {}
            Err(e) => return Err(format!("Связь прервалась: {e}")),
        }
    }
}

fn set_timeout(ws: &mut WebSocket<MaybeTlsStream<TcpStream>>) {
    if let MaybeTlsStream::Plain(s) = ws.get_mut() {
        let _ = s.set_read_timeout(Some(Duration::from_millis(4)));
        let _ = s.set_nodelay(true);
    }
}
