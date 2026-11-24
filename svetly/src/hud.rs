//! Heads-up display: minimap, money and clock, speedometer, job panel,
//! interaction prompt, wanted stars and pop-up notifications.

use bevy::prelude::*;

use crate::city::{CityMap, MAP_EXT};
use crate::input::Controls;
use crate::jobs::{rank_of, JobState, Prompt, Target2};
use crate::menu::Waypoint;
use crate::player::{Player, PlayerState};
use crate::scene::{CameraRig, Clock, Quality};
use crate::util::*;
use crate::vehicles::{Catalog, Vehicle};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum NoteKind {
    Info,
    Good,
    Warn,
    Money,
}

#[derive(Event, Clone)]
pub struct Notify {
    pub text: String,
    pub kind: NoteKind,
}

impl Notify {
    pub fn info(t: impl Into<String>) -> Self {
        Self { text: t.into(), kind: NoteKind::Info }
    }
    pub fn good(t: impl Into<String>) -> Self {
        Self { text: t.into(), kind: NoteKind::Good }
    }
    pub fn warn(t: impl Into<String>) -> Self {
        Self { text: t.into(), kind: NoteKind::Warn }
    }
    pub fn money(t: impl Into<String>) -> Self {
        Self { text: t.into(), kind: NoteKind::Money }
    }
}

#[derive(Component)]
struct NoteStack;
#[derive(Component)]
struct Note {
    age: f32,
}
#[derive(Component)]
struct MapImage;
#[derive(Component)]
struct MapTarget;
#[derive(Component)]
struct MapWaypoint;
#[derive(Component)]
struct MapPlayer;
#[derive(Component)]
struct TopRight;
#[derive(Component)]
struct JobPanel;
#[derive(Component)]
struct PromptText;
#[derive(Component)]
struct PromptBox;
#[derive(Component)]
struct Speedo;
#[derive(Component)]
struct SpeedoText;
#[derive(Component)]
struct SpeedoBar;
#[derive(Component)]
struct SpeedoName;
#[derive(Component)]
struct HelpText;

const MAP_SIZE: f32 = 190.0;
const MAP_VIEW: f32 = 320.0;

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.add_event::<Notify>()
            .add_systems(Startup, spawn_hud)
            .add_systems(Update, (show_notes, update_minimap, update_texts, update_speedo).in_set(crate::GameSet::Hud));
    }
}

fn panel_bg() -> BackgroundColor {
    BackgroundColor(Color::srgba(0.04, 0.05, 0.08, 0.62))
}

fn spawn_hud(mut commands: Commands, map: Res<CityMap>) {
    let scale = MAP_SIZE * (2.0 * MAP_EXT / MAP_VIEW);
    // Minimap, top-left.
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(14.0),
                top: Val::Px(14.0),
                width: Val::Px(MAP_SIZE),
                height: Val::Px(MAP_SIZE),
                overflow: Overflow::clip(),
                border: UiRect::all(Val::Px(2.0)),
                ..default()
            },
            BorderColor(Color::srgba(1.0, 1.0, 1.0, 0.5)),
            BorderRadius::all(Val::Px(14.0)),
            BackgroundColor(Color::srgb(0.1, 0.12, 0.15)),
        ))
        .with_children(|m| {
            m.spawn((
                MapImage,
                ImageNode::new(map.minimap.clone()),
                Node { position_type: PositionType::Absolute, width: Val::Px(scale), height: Val::Px(scale), ..default() },
            ))
            .with_children(|img| {
                for site in map.sites.values() {
                    let p = (xz(site.door) + Vec2::splat(MAP_EXT)) / (2.0 * MAP_EXT) * scale;
                    img.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: Val::Px(p.x - 5.0),
                            top: Val::Px(p.y - 5.0),
                            width: Val::Px(10.0),
                            height: Val::Px(10.0),
                            border: UiRect::all(Val::Px(1.5)),
                            ..default()
                        },
                        BorderColor(Color::WHITE),
                        BorderRadius::all(Val::Px(3.0)),
                        BackgroundColor(site.place.color()),
                    ));
                }
            });
            for (marker, color, size) in [(0u8, Color::srgb(1.0, 0.85, 0.15), 14.0), (1u8, Color::srgb(0.85, 0.4, 1.0), 12.0)] {
                let mut e = m.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        width: Val::Px(size),
                        height: Val::Px(size),
                        border: UiRect::all(Val::Px(2.0)),
                        ..default()
                    },
                    BorderColor(Color::BLACK),
                    BorderRadius::MAX,
                    BackgroundColor(color),
                    Visibility::Hidden,
                ));
                if marker == 0 {
                    e.insert(MapTarget);
                } else {
                    e.insert(MapWaypoint);
                }
            }
            m.spawn((
                MapPlayer,
                Node {
                    position_type: PositionType::Absolute,
                    left: Val::Px(MAP_SIZE * 0.5 - 7.0),
                    top: Val::Px(MAP_SIZE * 0.5 - 7.0),
                    width: Val::Px(14.0),
                    height: Val::Px(14.0),
                    border: UiRect::all(Val::Px(2.5)),
                    ..default()
                },
                BorderColor(Color::srgb(0.1, 0.4, 1.0)),
                BorderRadius::MAX,
                BackgroundColor(Color::WHITE),
            ));
        });

    // Job panel below the map.
    commands.spawn((
        JobPanel,
        Text::new(""),
        TextFont { font_size: 15.0, ..default() },
        TextColor(Color::WHITE),
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(14.0),
            top: Val::Px(MAP_SIZE + 24.0),
            max_width: Val::Px(330.0),
            padding: UiRect::all(Val::Px(8.0)),
            ..default()
        },
        panel_bg(),
        BorderRadius::all(Val::Px(10.0)),
    ));

    // Clock, money, wanted, top-right.
    commands.spawn((
        TopRight,
        Text::new(""),
        TextFont { font_size: 22.0, ..default() },
        TextColor(Color::WHITE),
        TextLayout::new_with_justify(JustifyText::Right),
        Node { position_type: PositionType::Absolute, right: Val::Px(16.0), top: Val::Px(12.0), padding: UiRect::all(Val::Px(8.0)), ..default() },
        panel_bg(),
        BorderRadius::all(Val::Px(10.0)),
    ));

    // Notifications, top-centre.
    commands.spawn((
        NoteStack,
        Node {
            position_type: PositionType::Absolute,
            top: Val::Px(14.0),
            left: Val::Percent(50.0),
            margin: UiRect::left(Val::Px(-210.0)),
            width: Val::Px(420.0),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: Val::Px(6.0),
            ..default()
        },
    ));

    // Prompt, bottom-centre.
    commands
        .spawn((
            PromptBox,
            Node {
                position_type: PositionType::Absolute,
                bottom: Val::Px(150.0),
                left: Val::Percent(50.0),
                margin: UiRect::left(Val::Px(-200.0)),
                width: Val::Px(400.0),
                justify_content: JustifyContent::Center,
                padding: UiRect::all(Val::Px(10.0)),
                ..default()
            },
            panel_bg(),
            BorderRadius::all(Val::Px(12.0)),
            Visibility::Hidden,
        ))
        .with_children(|p| {
            p.spawn((
                PromptText,
                Text::new(""),
                TextFont { font_size: 17.0, ..default() },
                TextColor(Color::WHITE),
                TextLayout::new_with_justify(JustifyText::Center),
            ));
        });

    // Speedometer, bottom-centre.
    commands
        .spawn((
            Speedo,
            Node {
                position_type: PositionType::Absolute,
                bottom: Val::Px(18.0),
                left: Val::Percent(50.0),
                margin: UiRect::left(Val::Px(-120.0)),
                width: Val::Px(240.0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                padding: UiRect::all(Val::Px(8.0)),
                ..default()
            },
            panel_bg(),
            BorderRadius::all(Val::Px(14.0)),
            Visibility::Hidden,
        ))
        .with_children(|s| {
            s.spawn((SpeedoText, Text::new("0"), TextFont { font_size: 40.0, ..default() }, TextColor(Color::WHITE)));
            s.spawn((
                Node { width: Val::Px(210.0), height: Val::Px(8.0), margin: UiRect::vertical(Val::Px(4.0)), ..default() },
                BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.15)),
                BorderRadius::all(Val::Px(4.0)),
            ))
            .with_children(|b| {
                b.spawn((
                    SpeedoBar,
                    Node { width: Val::Percent(0.0), height: Val::Percent(100.0), ..default() },
                    BackgroundColor(Color::srgb(0.2, 0.8, 1.0)),
                    BorderRadius::all(Val::Px(4.0)),
                ));
            });
            s.spawn((SpeedoName, Text::new(""), TextFont { font_size: 13.0, ..default() }, TextColor(Color::srgba(1.0, 1.0, 1.0, 0.8))));
        });

    commands.spawn((
        HelpText,
        Text::new("WASD — движение · Shift — бег · F — сесть/выйти · E — действие · Пробел — ручник\nTab — меню · P — телефон (работы) · ПКМ — камера · колесо — зум · F2 — графика"),
        TextFont { font_size: 12.0, ..default() },
        TextColor(Color::srgba(1.0, 1.0, 1.0, 0.7)),
        Node { position_type: PositionType::Absolute, left: Val::Px(14.0), bottom: Val::Px(10.0), ..default() },
    ));
}

fn show_notes(
    mut commands: Commands,
    time: Res<Time>,
    mut events: EventReader<Notify>,
    stack: Query<Entity, With<NoteStack>>,
    mut notes: Query<(Entity, &mut Note, &mut BackgroundColor, &Children)>,
    mut texts: Query<&mut TextColor>,
) {
    let Ok(stack) = stack.single() else { return };
    for ev in events.read() {
        let color = match ev.kind {
            NoteKind::Info => Color::srgba(0.08, 0.1, 0.16, 0.85),
            NoteKind::Good => Color::srgba(0.08, 0.4, 0.2, 0.88),
            NoteKind::Warn => Color::srgba(0.55, 0.12, 0.1, 0.88),
            NoteKind::Money => Color::srgba(0.1, 0.42, 0.12, 0.9),
        };
        let note = commands
            .spawn((
                Note { age: 0.0 },
                Node { padding: UiRect::axes(Val::Px(14.0), Val::Px(8.0)), ..default() },
                BackgroundColor(color),
                BorderRadius::all(Val::Px(10.0)),
            ))
            .with_children(|n| {
                n.spawn((
                    Text::new(ev.text.clone()),
                    TextFont { font_size: if ev.kind == NoteKind::Money { 20.0 } else { 16.0 }, ..default() },
                    TextColor(Color::WHITE),
                    TextLayout::new_with_justify(JustifyText::Center),
                ));
            })
            .id();
        commands.entity(stack).add_child(note);
    }
    let dt = time.delta_secs();
    let count = notes.iter().count();
    for (i, (e, mut n, mut bg, children)) in notes.iter_mut().enumerate() {
        n.age += dt * if count > 4 && i == 0 { 3.0 } else { 1.0 };
        let life = 4.5;
        if n.age > life {
            commands.entity(e).despawn();
            continue;
        }
        let a = ((life - n.age) / 0.6).clamp(0.0, 1.0);
        bg.0.set_alpha(0.88 * a);
        for c in children.iter() {
            if let Ok(mut tc) = texts.get_mut(c) {
                tc.0.set_alpha(a);
            }
        }
    }
}

fn world_to_map(p: Vec3, center: Vec2) -> Vec2 {
    (xz(p) - center) / MAP_VIEW * MAP_SIZE + Vec2::splat(MAP_SIZE * 0.5)
}

#[allow(clippy::type_complexity)]
fn update_minimap(
    jobs: Res<JobState>,
    waypoint: Res<Waypoint>,
    player: Query<&Transform, With<Player>>,
    transforms: Query<&Transform, Without<Player>>,
    mut img: Query<&mut Node, (With<MapImage>, Without<MapTarget>, Without<MapWaypoint>)>,
    mut target: Query<(&mut Node, &mut Visibility), (With<MapTarget>, Without<MapImage>, Without<MapWaypoint>)>,
    mut wp: Query<(&mut Node, &mut Visibility), (With<MapWaypoint>, Without<MapImage>, Without<MapTarget>)>,
) {
    let Ok(pt) = player.single() else { return };
    let c = xz(pt.translation);
    let scale = MAP_SIZE * (2.0 * MAP_EXT / MAP_VIEW);
    if let Ok(mut n) = img.single_mut() {
        let off = (c + Vec2::splat(MAP_EXT)) / (2.0 * MAP_EXT) * scale;
        n.left = Val::Px(MAP_SIZE * 0.5 - off.x);
        n.top = Val::Px(MAP_SIZE * 0.5 - off.y);
    }
    let place = |p: Option<Vec3>, node: &mut Node, vis: &mut Visibility, size: f32| match p {
        Some(p) => {
            let mut m = world_to_map(p, c) - Vec2::splat(MAP_SIZE * 0.5);
            let lim = MAP_SIZE * 0.5 - 9.0;
            if m.x.abs() > lim || m.y.abs() > lim {
                m *= lim / m.x.abs().max(m.y.abs());
            }
            let m = m + Vec2::splat(MAP_SIZE * 0.5);
            node.left = Val::Px(m.x - size * 0.5);
            node.top = Val::Px(m.y - size * 0.5);
            *vis = Visibility::Inherited;
        }
        None => *vis = Visibility::Hidden,
    };
    let tp = match jobs.target() {
        Some(Target2::Point(p)) => Some(p),
        Some(Target2::Entity(e)) => transforms.get(e).ok().map(|t| t.translation),
        None => None,
    };
    if let Ok((mut n, mut v)) = target.single_mut() {
        place(tp, &mut n, &mut v, 14.0);
    }
    if let Ok((mut n, mut v)) = wp.single_mut() {
        place(waypoint.0, &mut n, &mut v, 12.0);
    }
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_texts(
    clock: Res<Clock>,
    state: Res<PlayerState>,
    jobs: Res<JobState>,
    prompt: Res<Prompt>,
    quality: Res<Quality>,
    controls: Res<Controls>,
    waypoint: Res<Waypoint>,
    map: Res<CityMap>,
    _rig: Res<CameraRig>,
    player: Query<&Transform, With<Player>>,
    transforms: Query<&Transform, Without<Player>>,
    mut top: Query<&mut Text, (With<TopRight>, Without<JobPanel>, Without<PromptText>)>,
    mut panel: Query<(&mut Text, &mut Visibility), (With<JobPanel>, Without<TopRight>, Without<PromptText>, Without<PromptBox>)>,
    mut ptext: Query<&mut Text, (With<PromptText>, Without<TopRight>, Without<JobPanel>)>,
    mut pbox: Query<&mut Visibility, (With<PromptBox>, Without<JobPanel>, Without<HelpText>)>,
    mut help: Query<&mut Visibility, (With<HelpText>, Without<PromptBox>, Without<JobPanel>)>,
) {
    let Ok(pt) = player.single() else { return };
    if let Ok(mut t) = top.single_mut() {
        let stars = if jobs.wanted > 0 { format!("\nРОЗЫСК {}", "• ".repeat(jobs.wanted as usize)) } else { String::new() };
        t.0 = format!("{}  ·  День {}\n{} ₽{}", clock.text(), clock.day, fmt_money(state.money), stars);
    }
    if let Ok((mut t, mut vis)) = panel.single_mut() {
        let mut s = String::new();
        if let Some(job) = jobs.job {
            let xp = *jobs.xp.get(&job).unwrap_or(&0);
            s += &format!("{} · {}\n", job.title(), job.ranks()[rank_of(xp)]);
            if let Some((title, line)) = jobs.mission_text() {
                s += &format!("{title}\n› {line}");
                let tp = match jobs.target() {
                    Some(Target2::Point(p)) => Some(p),
                    Some(Target2::Entity(e)) => transforms.get(e).ok().map(|t| t.translation),
                    None => None,
                };
                if let Some(tp) = tp {
                    s += &format!("\nДо цели: {:.0} м", (xz(tp) - xz(pt.translation)).length());
                }
            } else {
                s += "Ожидайте задание…";
            }
            s += &format!("\nЗа смену: {} ₽", fmt_money(jobs.shift_earned));
        } else if let Some(wp) = waypoint.0 {
            s += &format!("Метка GPS: {:.0} м", (xz(wp) - xz(pt.translation)).length());
        } else {
            s += "Без работы. Найдите цветные метки на карте\nили откройте телефон (P), чтобы выбрать работу.";
        }
        if state.swimming {
            s += "\nВы плывёте";
        }
        let _ = (&quality, &map);
        t.0 = s;
        *vis = if controls.ui_blocked { Visibility::Hidden } else { Visibility::Inherited };
    }
    let show_prompt = prompt.text.is_some() && !controls.ui_blocked;
    if let Ok(mut v) = pbox.single_mut() {
        *v = if show_prompt { Visibility::Inherited } else { Visibility::Hidden };
    }
    if let (Some(text), Ok(mut t)) = (&prompt.text, ptext.single_mut()) {
        let key = if controls.touch_mode { "«Действие»" } else { "E" };
        t.0 = format!("{text}\n[{key}]");
    }
    if let Ok(mut v) = help.single_mut() {
        *v = if controls.touch_mode || controls.ui_blocked { Visibility::Hidden } else { Visibility::Inherited };
    }
}

pub fn fmt_money(v: i64) -> String {
    let s = v.abs().to_string();
    let mut out = String::new();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(' ');
        }
        out.push(ch);
    }
    if v < 0 {
        format!("-{out}")
    } else {
        out
    }
}

#[allow(clippy::type_complexity)]
fn update_speedo(
    state: Res<PlayerState>,
    catalog: Res<Catalog>,
    controls: Res<Controls>,
    vehicles: Query<&Vehicle>,
    mut speedo: Query<(&mut Visibility, &mut Node), With<Speedo>>,
    mut text: Query<&mut Text, (With<SpeedoText>, Without<SpeedoName>)>,
    mut name: Query<&mut Text, (With<SpeedoName>, Without<SpeedoText>)>,
    mut bar: Query<(&mut Node, &mut BackgroundColor), (With<SpeedoBar>, Without<Speedo>)>,
) {
    let Ok((mut vis, mut node)) = speedo.single_mut() else { return };
    let Some(v) = state.vehicle.and_then(|e| vehicles.get(e).ok()) else {
        *vis = Visibility::Hidden;
        return;
    };
    *vis = if controls.ui_blocked { Visibility::Hidden } else { Visibility::Inherited };
    node.bottom = Val::Px(if controls.touch_mode { 12.0 } else { 34.0 });
    let s = &catalog.specs[v.spec];
    let kmh = (v.vel.length() * 3.6).round();
    if let Ok(mut t) = text.single_mut() {
        t.0 = format!("{kmh:.0} км/ч");
    }
    if let Ok(mut t) = name.single_mut() {
        t.0 = format!("{} · {}", s.name, s.class.title());
    }
    if let Ok((mut n, mut c)) = bar.single_mut() {
        let f = (kmh / (s.max_speed * 3.6)).clamp(0.0, 1.0);
        n.width = Val::Percent(f * 100.0);
        c.0 = Color::srgb(0.2 + 0.8 * f, 0.8 - 0.5 * f, 1.0 - 0.8 * f);
    }
}
