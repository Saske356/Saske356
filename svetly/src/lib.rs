//! Port Svetly — an original open-world city game written in Rust with Bevy.

use bevy::prelude::*;
use bevy::window::{PresentMode, WindowMode};

pub mod character;
pub mod city;
pub mod debug;
pub mod hud;
pub mod input;
pub mod jobs;
pub mod menu;
pub mod player;
pub mod scene;
pub mod traffic;
pub mod util;
pub mod vehicles;

/// Frame order: input → menus → player → jobs → NPCs → physics → visuals → HUD.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub enum GameSet {
    Menu,
    Player,
    Jobs,
    Npc,
    Physics,
    Visuals,
    Hud,
}

pub fn app() -> App {
    let mut app = App::new();
    let android = cfg!(target_os = "android");
    app.add_plugins(
        DefaultPlugins
            .set(WindowPlugin {
                primary_window: Some(Window {
                    title: "Порт-Светлый".into(),
                    resolution: (1280.0_f32, 720.0_f32).into(),
                    present_mode: PresentMode::AutoVsync,
                    mode: if android { WindowMode::BorderlessFullscreen(MonitorSelection::Primary) } else { WindowMode::Windowed },
                    resizable: true,
                    ..default()
                }),
                ..default()
            })
            .set(bevy::log::LogPlugin { level: bevy::log::Level::WARN, filter: "wgpu=error,naga=warn".into(), ..default() }),
    )
    .configure_sets(
        Update,
        (GameSet::Menu, GameSet::Player, GameSet::Jobs, GameSet::Npc, GameSet::Physics, GameSet::Visuals, GameSet::Hud).chain(),
    )
    .add_plugins((
        city::CityPlugin,
        scene::ScenePlugin,
        input::InputPlugin,
        vehicles::VehiclePlugin,
        character::CharacterPlugin,
        player::PlayerPlugin,
        traffic::TrafficPlugin,
        jobs::JobsPlugin,
        hud::HudPlugin,
        menu::MenuPlugin,
        debug::DebugPlugin,
    ))
    .add_systems(PreStartup, install_font)
    .add_systems(Startup, welcome);
    app
}

/// Replaces Bevy's built-in font (Latin only) with PT Sans, which covers Cyrillic and ₽.
fn install_font(mut fonts: ResMut<Assets<Font>>) {
    let bytes = include_bytes!("../assets/fonts/PT_Sans-Web-Regular.ttf");
    let font = Font::try_from_bytes(bytes.to_vec()).expect("bundled font");
    let _ = fonts.insert(AssetId::default(), font);
}

fn welcome(mut notes: EventWriter<hud::Notify>) {
    notes.write(hud::Notify::good("Добро пожаловать в Порт-Светлый!"));
    notes.write(hud::Notify::info("Откройте телефон (P), чтобы выбрать работу"));
}

pub fn run() {
    app().run();
}

#[bevy_main]
fn main() {
    run();
}
