//! Интерфейс: чат, деньги/время/уровень/FPS, спидометр, уведомления, строка ввода.

use bevy::diagnostic::{DiagnosticsStore, FrameTimeDiagnosticsPlugin};
use bevy::prelude::*;
use novo_world as world;

use crate::state::Game;

#[derive(Component)]
pub struct ChatText;
#[derive(Component)]
pub struct StatsText;
#[derive(Component)]
pub struct SpeedText;
#[derive(Component)]
pub struct ToastText;
#[derive(Component)]
pub struct InputText;
#[derive(Component)]
pub struct StatusText;

#[derive(Resource)]
pub struct Fonts {
    pub regular: Handle<Font>,
    pub bold: Handle<Font>,
}

pub fn setup_hud(mut commands: Commands, mut fonts: ResMut<Assets<Font>>) {
    let regular = fonts.add(Font::try_from_bytes(include_bytes!("../assets/fonts/Montserrat-Medium.ttf").to_vec()).expect("шрифт"));
    let bold = fonts.add(Font::try_from_bytes(include_bytes!("../assets/fonts/Montserrat-ExtraBold.ttf").to_vec()).expect("шрифт"));
    let shadow = TextShadow { offset: Vec2::new(1.5, 1.5), color: Color::srgba(0.0, 0.0, 0.0, 0.85) };
    let font = |f: &Handle<Font>, s: f32| TextFont { font: f.clone(), font_size: s, ..default() };
    let abs = |top: Option<f32>, left: Option<f32>, right: Option<f32>, bottom: Option<f32>| Node {
        position_type: PositionType::Absolute,
        top: top.map_or(Val::Auto, Val::Px), left: left.map_or(Val::Auto, Val::Px),
        right: right.map_or(Val::Auto, Val::Px), bottom: bottom.map_or(Val::Auto, Val::Px),
        ..default()
    };
    commands.spawn((Text::new(""), font(&regular, 15.0), TextColor(Color::WHITE), shadow, abs(Some(12.0), Some(14.0), None, None), ChatText));
    commands.spawn((Text::new(""), font(&bold, 22.0), TextColor(Color::WHITE), shadow, TextLayout::new_with_justify(JustifyText::Right),
        abs(Some(12.0), None, Some(16.0), None), StatsText));
    commands.spawn((Text::new(""), font(&bold, 44.0), TextColor(Color::WHITE), shadow, TextLayout::new_with_justify(JustifyText::Right),
        abs(None, None, Some(20.0), Some(16.0)), SpeedText));
    commands.spawn((Text::new(""), font(&regular, 17.0), TextColor(Color::WHITE), shadow, abs(None, Some(14.0), None, Some(60.0)), ToastText));
    commands.spawn((Text::new(""), font(&regular, 17.0), TextColor(Color::srgb(1.0, 0.9, 0.6)), shadow, abs(None, Some(14.0), None, Some(24.0)), InputText));
    commands.spawn((Text::new(""), font(&bold, 26.0), TextColor(Color::WHITE), shadow, abs(Some(300.0), Some(40.0), None, None), StatusText));
    commands.insert_resource(Fonts { regular, bold });
}

fn money(n: i64) -> String {
    let s = n.abs().to_string();
    let mut out = String::new();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(' ');
        }
        out.push(ch);
    }
    format!("{}${out}", if n < 0 { "-" } else { "" })
}

#[allow(clippy::type_complexity)]
pub fn update_hud(
    time: Res<Time>,
    mut game: ResMut<Game>,
    diag: Res<DiagnosticsStore>,
    mut texts: ParamSet<(
        Query<&mut Text, With<ChatText>>,
        Query<&mut Text, With<StatsText>>,
        Query<&mut Text, With<SpeedText>>,
        Query<&mut Text, With<ToastText>>,
        Query<&mut Text, With<InputText>>,
        Query<&mut Text, With<StatusText>>,
    )>,
) {
    let fps = diag.get(&FrameTimeDiagnosticsPlugin::FPS).and_then(|d| d.smoothed()).unwrap_or(0.0);
    if let Ok(mut t) = texts.p0().single_mut() {
        let lines: Vec<&str> = game.chat.iter().rev().take(9).map(|(s, _)| s.as_str()).collect();
        t.0 = lines.into_iter().rev().collect::<Vec<_>>().join("\n");
    }
    if let Ok(mut t) = texts.p1().single_mut() {
        let adm = if game.admin > 0 { format!(" · админ {}", game.admin) } else { String::new() };
        t.0 = format!("{}\n{}\nУр. {}{} · Онлайн: {}\n{:.0} FPS", world::format_time(game.time as f64), money(game.money), game.level, adm, game.online, fps);
    }
    if let Ok(mut t) = texts.p2().single_mut() {
        t.0 = game.car.as_ref().map(|c| format!("{:.0} км/ч", c.spd.abs() * 3.6)).unwrap_or_default();
    }
    let dt = time.delta_secs();
    let toast = match game.toast.as_mut() {
        Some((s, left)) => { *left -= dt; if *left > 0.0 { s.clone() } else { String::new() } }
        None => String::new(),
    };
    if toast.is_empty() { game.toast = None; }
    if let Ok(mut t) = texts.p3().single_mut() {
        let job = if game.job_label.is_empty() { String::new() } else { format!("Работа: {}\n", game.job_label) };
        t.0 = format!("{job}{toast}");
    }
    if let Ok(mut t) = texts.p4().single_mut() {
        t.0 = game.typing.as_ref().map(|s| format!("> {s}_")).unwrap_or_default();
    }
    if let Ok(mut t) = texts.p5().single_mut() {
        t.0 = if game.connected { String::new() } else { game.status.clone() };
    }
}
