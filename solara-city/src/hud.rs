//! HUD: speedometer, gear, rev bar, minimap, prompts and controls.
use bevy::diagnostic::{DiagnosticsStore, FrameTimeDiagnosticsPlugin};
use bevy::prelude::*;

use crate::camera::Rig;
use crate::car::Car;
use crate::player::{Game, Mode, Player};
use crate::traffic::Ai;
use crate::util::*;

#[derive(Component)]
pub struct SpeedText;
#[derive(Component)]
pub struct GearText;
#[derive(Component)]
pub struct RpmBar;
#[derive(Component)]
pub struct Speedo;
#[derive(Component)]
pub struct HelpText;
#[derive(Component)]
pub struct PromptText;
#[derive(Component)]
pub struct CamText;
#[derive(Component)]
pub struct FpsText;
#[derive(Component)]
pub struct MapPlayer;
#[derive(Component)]
pub struct MapCar(pub usize);

const MAP: f32 = 190.0;
fn map_xy(p: Vec2) -> Vec2 {
    let lo = -12.0;
    let hi = city_max() + 60.0;
    (p - Vec2::splat(lo)) / (hi - lo) * MAP
}

pub fn spawn_hud(commands: &mut Commands, font: Handle<Font>) {
    let tf = |size: f32| TextFont { font: font.clone(), font_size: size, ..default() };
    let panel = Color::srgba(0.04, 0.05, 0.08, 0.62);

    // title
    commands.spawn((
        Text::new("SOLARA CITY"),
        tf(20.0),
        TextColor(Color::srgb(1.0, 0.82, 0.55)),
        Node { position_type: PositionType::Absolute, left: Val::Px(18.0), top: Val::Px(14.0), ..default() },
    ));
    commands.spawn((
        Text::new(""),
        tf(12.0),
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.6)),
        FpsText,
        Node { position_type: PositionType::Absolute, left: Val::Px(18.0), top: Val::Px(40.0), ..default() },
    ));

    // speedometer
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                right: Val::Px(18.0),
                bottom: Val::Px(18.0),
                width: Val::Px(190.0),
                padding: UiRect::all(Val::Px(12.0)),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::FlexEnd,
                row_gap: Val::Px(4.0),
                ..default()
            },
            BackgroundColor(panel),
            BorderRadius::all(Val::Px(12.0)),
            Visibility::Hidden,
            Speedo,
        ))
        .with_children(|p| {
            p.spawn((Text::new("0"), tf(52.0), TextColor(Color::WHITE), SpeedText));
            p.spawn((Text::new("км/ч   D1"), tf(14.0), TextColor(Color::srgb(1.0, 0.8, 0.5)), GearText));
            p.spawn((
                Node { width: Val::Percent(100.0), height: Val::Px(6.0), ..default() },
                BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.12)),
                BorderRadius::all(Val::Px(3.0)),
            ))
            .with_children(|b| {
                b.spawn((
                    Node { width: Val::Percent(10.0), height: Val::Percent(100.0), ..default() },
                    BackgroundColor(Color::srgb(1.0, 0.35, 0.2)),
                    BorderRadius::all(Val::Px(3.0)),
                    RpmBar,
                ));
            });
        });

    // camera label
    commands.spawn((
        Text::new(""),
        tf(13.0),
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.75)),
        CamText,
        Node { position_type: PositionType::Absolute, right: Val::Px(24.0), bottom: Val::Px(150.0), ..default() },
    ));

    // help
    commands.spawn((
        Text::new(""),
        tf(13.0),
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.85)),
        HelpText,
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(18.0),
            bottom: Val::Px(18.0),
            max_width: Val::Px(560.0),
            padding: UiRect::axes(Val::Px(10.0), Val::Px(8.0)),
            ..default()
        },
        BackgroundColor(panel),
        BorderRadius::all(Val::Px(8.0)),
    ));

    // prompt
    commands
        .spawn(Node {
            position_type: PositionType::Absolute,
            width: Val::Percent(100.0),
            bottom: Val::Px(110.0),
            justify_content: JustifyContent::Center,
            ..default()
        })
        .with_children(|p| {
            p.spawn((
                Text::new(""),
                tf(18.0),
                TextColor(Color::WHITE),
                PromptText,
                Node { padding: UiRect::axes(Val::Px(14.0), Val::Px(8.0)), ..default() },
                BackgroundColor(Color::NONE),
                BorderRadius::all(Val::Px(8.0)),
            ));
        });

    // minimap
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                right: Val::Px(18.0),
                top: Val::Px(14.0),
                width: Val::Px(MAP),
                height: Val::Px(MAP),
                overflow: Overflow::clip(),
                ..default()
            },
            BackgroundColor(Color::srgba(0.16, 0.24, 0.14, 0.78)),
            BorderRadius::all(Val::Px(10.0)),
        ))
        .with_children(|p| {
            let road = Color::srgba(0.22, 0.22, 0.25, 0.95);
            let sea0 = map_xy(Vec2::new(city_max() + 45.0, 0.0)).x;
            p.spawn((
                Node { position_type: PositionType::Absolute, left: Val::Px(sea0), top: Val::Px(0.0), width: Val::Px(MAP), height: Val::Px(MAP), ..default() },
                BackgroundColor(Color::srgb(0.1, 0.35, 0.45)),
            ));
            for i in 0..N {
                for j in 0..N {
                    let a = map_xy(block_min(i, j));
                    let b = map_xy(block_min(i, j) + Vec2::splat(BLOCK));
                    p.spawn((
                        Node { position_type: PositionType::Absolute, left: Val::Px(a.x), top: Val::Px(a.y), width: Val::Px(b.x - a.x), height: Val::Px(b.y - a.y), ..default() },
                        BackgroundColor(Color::srgba(0.55, 0.52, 0.48, 0.9)),
                    ));
                }
            }
            for k in 0..=N {
                let c = k as f32 * S;
                let a = map_xy(Vec2::new(-ROAD * 0.5, c - ROAD * 0.5));
                let b = map_xy(Vec2::new(city_max() + ROAD * 0.5, c + ROAD * 0.5));
                p.spawn((
                    Node { position_type: PositionType::Absolute, left: Val::Px(a.x), top: Val::Px(a.y), width: Val::Px(b.x - a.x), height: Val::Px((b.y - a.y).max(2.0)), ..default() },
                    BackgroundColor(road),
                ));
                let a = map_xy(Vec2::new(c - ROAD * 0.5, -ROAD * 0.5));
                let b = map_xy(Vec2::new(c + ROAD * 0.5, city_max() + ROAD * 0.5));
                p.spawn((
                    Node { position_type: PositionType::Absolute, left: Val::Px(a.x), top: Val::Px(a.y), width: Val::Px((b.x - a.x).max(2.0)), height: Val::Px(b.y - a.y), ..default() },
                    BackgroundColor(road),
                ));
            }
            for i in 0..40 {
                p.spawn((
                    Node { position_type: PositionType::Absolute, width: Val::Px(4.0), height: Val::Px(4.0), ..default() },
                    BackgroundColor(Color::srgb(0.95, 0.95, 0.95)),
                    BorderRadius::all(Val::Px(2.0)),
                    Visibility::Hidden,
                    MapCar(i),
                ));
            }
            p.spawn((
                Node { position_type: PositionType::Absolute, width: Val::Px(10.0), height: Val::Px(10.0), border: UiRect::all(Val::Px(2.0)), ..default() },
                BackgroundColor(Color::srgb(1.0, 0.3, 0.2)),
                BorderColor(Color::WHITE),
                BorderRadius::all(Val::Px(5.0)),
                MapPlayer,
            ));
        });
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn update_hud(
    game: Res<Game>,
    rig: Res<Rig>,
    diagnostics: Res<DiagnosticsStore>,
    cars: Query<&Car>,
    ai_cars: Query<&Car, With<Ai>>,
    player: Query<&Transform, With<Player>>,
    mut texts: ParamSet<(
        Query<&mut Text, With<SpeedText>>,
        Query<&mut Text, With<GearText>>,
        Query<&mut Text, With<HelpText>>,
        Query<(&mut Text, &mut BackgroundColor), With<PromptText>>,
        Query<&mut Text, With<CamText>>,
        Query<&mut Text, With<FpsText>>,
    )>,
    mut speedo: Query<&mut Visibility, (With<Speedo>, Without<MapCar>)>,
    mut rpm: Query<&mut Node, (With<RpmBar>, Without<MapPlayer>, Without<MapCar>)>,
    mut map_p: Query<&mut Node, (With<MapPlayer>, Without<RpmBar>, Without<MapCar>)>,
    mut map_c: Query<(&MapCar, &mut Node, &mut Visibility), (Without<RpmBar>, Without<MapPlayer>, Without<Speedo>)>,
) {
    let driving = game.mode == Mode::Driving;
    let car = game.car.and_then(|e| cars.get(e).ok());
    if let Ok(mut v) = speedo.single_mut() {
        *v = if driving { Visibility::Inherited } else { Visibility::Hidden };
    }
    if let Some(c) = car {
        if let Ok(mut t) = texts.p0().single_mut() {
            t.0 = format!("{:.0}", c.speed.abs() * 3.6);
        }
        if let Ok(mut t) = texts.p1().single_mut() {
            let g = if c.gear < 0 { "R".to_string() } else if c.speed.abs() < 0.3 { "N".to_string() } else { format!("D{}", c.gear) };
            t.0 = format!("км/ч   {g}   {:.0} об/мин", c.rpm);
        }
        if let Ok(mut n) = rpm.single_mut() {
            n.width = Val::Percent((c.rpm / 8000.0 * 100.0).clamp(4.0, 100.0));
        }
    }
    if let Ok(mut t) = texts.p2().single_mut() {
        t.0 = match game.mode {
            Mode::Driving => "W/S — газ / тормоз · A/D — руль · Пробел — ручник\nC — камера (сзади / салон / капот) · V — облёт · H — фары · G — двери · F — выйти\nМышь — осмотреться · колесо — дистанция".to_string(),
            _ if rig.showcase => "WASD — идти, чтобы начать · мышь (зажать) — вращать камеру · V — облёт".to_string(),
            _ => "WASD — идти · Shift — бег · Пробел — прыжок · мышь — камера (клик = захват, Esc — отпустить)\nF у машины — сесть (можно в любую) · G — открыть двери".to_string(),
        };
    }
    if let Ok((mut t, mut bg)) = texts.p3().single_mut() {
        let msg = if game.mode == Mode::Foot && game.near.is_some() {
            "F — сесть в машину   ·   G — двери"
        } else if driving && car.map_or(false, |c| c.speed.abs() > 3.0) {
            ""
        } else {
            ""
        };
        t.0 = msg.to_string();
        bg.0 = if msg.is_empty() { Color::NONE } else { Color::srgba(0.04, 0.05, 0.08, 0.7) };
    }
    if let Ok(mut t) = texts.p4().single_mut() {
        t.0 = if driving { format!("Камера: {}", rig.car_cam.label()) } else { String::new() };
    }
    if let Ok(mut t) = texts.p5().single_mut() {
        if let Some(fps) = diagnostics.get(&FrameTimeDiagnosticsPlugin::FPS).and_then(|d| d.smoothed()) {
            t.0 = format!("{fps:.0} FPS");
        }
    }
    let ppos = car.map(|c| c.pos).or_else(|| player.single().ok().map(|t| t.translation.xz()));
    if let (Some(p), Ok(mut n)) = (ppos, map_p.single_mut()) {
        let m = map_xy(p);
        n.left = Val::Px(m.x - 5.0);
        n.top = Val::Px(m.y - 5.0);
    }
    let positions: Vec<Vec2> = ai_cars.iter().map(|c| c.pos).collect();
    for (mc, mut n, mut v) in &mut map_c {
        if let Some(p) = positions.get(mc.0) {
            let m = map_xy(*p);
            n.left = Val::Px(m.x - 2.0);
            n.top = Val::Px(m.y - 2.0);
            *v = Visibility::Inherited;
        } else {
            *v = Visibility::Hidden;
        }
    }
}
