//! One set of controls for keyboard/mouse and for touch screens (virtual stick
//! on the left, action buttons on the right, drag to look around).

use std::collections::HashMap;

use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::prelude::*;
use bevy::window::PrimaryWindow;

#[derive(Resource, Default)]
pub struct Controls {
    /// On foot: x = strafe right, y = forward.
    pub walk: Vec2,
    pub run: bool,
    /// In a vehicle: x = steer right, y = throttle (negative brakes / reverses).
    pub drive: Vec2,
    pub handbrake: bool,
    pub enter: bool,
    pub action: bool,
    pub menu: bool,
    pub phone: bool,
    pub quality: bool,
    /// Camera orbit delta in radians (yaw, pitch) for this frame.
    pub look: Vec2,
    pub zoom: f32,
    pub touch_mode: bool,
    pub ui_blocked: bool,
}

#[derive(Component, Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum TouchButton {
    Enter,
    Action,
    Brake,
    Run,
    Menu,
    Phone,
}

#[derive(Component)]
struct StickBase;
#[derive(Component)]
struct StickKnob;
#[derive(Component)]
pub struct TouchUi;

#[derive(Default)]
struct StickState {
    id: Option<u64>,
    origin: Vec2,
    value: Vec2,
    look_id: Option<u64>,
    last_look: Vec2,
}

const STICK_R: f32 = 70.0;

pub struct InputPlugin;

impl Plugin for InputPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Controls>()
            .add_systems(Startup, spawn_touch_ui)
            .add_systems(PreUpdate, gather.after(bevy::input::InputSystem))
            .add_systems(Update, (show_touch_ui, move_knob));
    }
}

fn spawn_touch_ui(mut commands: Commands) {
    let button = |parent: &mut ChildSpawnerCommands, label: &str, kind: TouchButton, size: f32, color: Color| {
        parent
            .spawn((
                Button,
                kind,
                Node {
                    width: Val::Px(size),
                    height: Val::Px(size),
                    margin: UiRect::all(Val::Px(6.0)),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    border: UiRect::all(Val::Px(2.0)),
                    ..default()
                },
                BorderRadius::MAX,
                BorderColor(Color::srgba(1.0, 1.0, 1.0, 0.35)),
                BackgroundColor(color),
            ))
            .with_children(|b| {
                b.spawn((
                    Text::new(label),
                    TextFont { font_size: 15.0, ..default() },
                    TextColor(Color::WHITE),
                    TextLayout::new_with_justify(JustifyText::Center),
                ));
            });
    };
    // Action buttons, bottom right.
    commands
        .spawn((
            TouchUi,
            Node {
                position_type: PositionType::Absolute,
                right: Val::Px(16.0),
                bottom: Val::Px(16.0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::End,
                ..default()
            },
            Visibility::Hidden,
        ))
        .with_children(|p| {
            p.spawn(Node { flex_direction: FlexDirection::Row, ..default() }).with_children(|r| {
                button(r, "Меню", TouchButton::Menu, 62.0, Color::srgba(0.1, 0.1, 0.14, 0.55));
                button(r, "Телефон", TouchButton::Phone, 62.0, Color::srgba(0.1, 0.1, 0.14, 0.55));
            });
            p.spawn(Node { flex_direction: FlexDirection::Row, ..default() }).with_children(|r| {
                button(r, "Бег", TouchButton::Run, 74.0, Color::srgba(0.1, 0.1, 0.14, 0.55));
                button(r, "Действие", TouchButton::Action, 74.0, Color::srgba(0.15, 0.45, 0.85, 0.6));
            });
            p.spawn(Node { flex_direction: FlexDirection::Row, ..default() }).with_children(|r| {
                button(r, "Тормоз", TouchButton::Brake, 84.0, Color::srgba(0.75, 0.15, 0.15, 0.6));
                button(r, "Сесть\nВыйти", TouchButton::Enter, 84.0, Color::srgba(0.1, 0.6, 0.35, 0.6));
            });
        });
    // Virtual stick (positioned where the thumb lands).
    commands
        .spawn((
            TouchUi,
            StickBase,
            Node {
                position_type: PositionType::Absolute,
                width: Val::Px(STICK_R * 2.0),
                height: Val::Px(STICK_R * 2.0),
                left: Val::Px(40.0),
                bottom: Val::Px(40.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                border: UiRect::all(Val::Px(2.0)),
                ..default()
            },
            BorderRadius::MAX,
            BorderColor(Color::srgba(1.0, 1.0, 1.0, 0.3)),
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.25)),
            Visibility::Hidden,
        ))
        .with_children(|p| {
            p.spawn((
                StickKnob,
                Node { width: Val::Px(56.0), height: Val::Px(56.0), ..default() },
                BorderRadius::MAX,
                BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.55)),
            ));
        });
}

#[allow(clippy::too_many_arguments)]
fn gather(
    mut c: ResMut<Controls>,
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    touches: Res<Touches>,
    window: Query<&Window, With<PrimaryWindow>>,
    buttons: Query<(&TouchButton, &Interaction)>,
    mut stick: Local<StickState>,
    mut prev: Local<HashMap<TouchButton, bool>>,
) {
    let size = window.single().map(|w| Vec2::new(w.width(), w.height())).unwrap_or(Vec2::new(1280.0, 720.0));
    if cfg!(target_os = "android") || touches.iter().next().is_some() {
        c.touch_mode = true;
    }

    // Keyboard.
    let axis = |neg: &[KeyCode], pos: &[KeyCode]| -> f32 {
        let n = neg.iter().any(|k| keys.pressed(*k)) as i32 as f32;
        let p = pos.iter().any(|k| keys.pressed(*k)) as i32 as f32;
        p - n
    };
    let x = axis(&[KeyCode::KeyA, KeyCode::ArrowLeft], &[KeyCode::KeyD, KeyCode::ArrowRight]);
    let y = axis(&[KeyCode::KeyS, KeyCode::ArrowDown], &[KeyCode::KeyW, KeyCode::ArrowUp]);
    let mut walk = Vec2::new(x, y);
    let mut look = Vec2::ZERO;
    if mouse.pressed(MouseButton::Right) || mouse.pressed(MouseButton::Middle) {
        look += motion.delta * 0.005;
    }
    c.zoom = -scroll.delta.y;

    // Touch: left stick and look-drag.
    for t in touches.iter_just_pressed() {
        let p = t.position();
        if stick.id.is_none() && p.x < size.x * 0.42 && p.y > size.y * 0.3 {
            stick.id = Some(t.id());
            stick.origin = p;
        } else if stick.look_id.is_none() && p.x >= size.x * 0.42 && p.y < size.y * 0.55 {
            stick.look_id = Some(t.id());
            stick.last_look = p;
        }
    }
    if let Some(id) = stick.id {
        match touches.get_pressed(id) {
            Some(t) => {
                let d = t.position() - stick.origin;
                let v = d.clamp_length_max(STICK_R) / STICK_R;
                stick.value = Vec2::new(v.x, -v.y);
            }
            None => {
                stick.id = None;
                stick.value = Vec2::ZERO;
            }
        }
    }
    if let Some(id) = stick.look_id {
        match touches.get_pressed(id) {
            Some(t) => {
                look += (t.position() - stick.last_look) * 0.006;
                stick.last_look = t.position();
            }
            None => stick.look_id = None,
        }
    }
    if stick.value.length_squared() > 0.0 {
        walk = stick.value;
    }

    // Buttons (both touch and mouse clicks).
    let mut held: HashMap<TouchButton, bool> = HashMap::new();
    for (b, i) in &buttons {
        if *i == Interaction::Pressed {
            held.insert(*b, true);
        }
    }
    let is_held = |b: TouchButton| held.get(&b).copied().unwrap_or(false);
    let mut edge = |b: TouchButton| {
        let now = is_held(b);
        let was = prev.insert(b, now).unwrap_or(false);
        now && !was
    };
    c.enter = keys.just_pressed(KeyCode::KeyF) || keys.just_pressed(KeyCode::Enter) || edge(TouchButton::Enter);
    c.action = keys.just_pressed(KeyCode::KeyE) || edge(TouchButton::Action);
    c.menu = keys.just_pressed(KeyCode::Tab) || keys.just_pressed(KeyCode::KeyM) || edge(TouchButton::Menu);
    c.phone = keys.just_pressed(KeyCode::KeyP) || keys.just_pressed(KeyCode::KeyJ) || edge(TouchButton::Phone);
    c.quality = keys.just_pressed(KeyCode::F2);
    c.run = keys.pressed(KeyCode::ShiftLeft) || is_held(TouchButton::Run) || walk.length() > 0.95 && c.touch_mode;
    c.handbrake = keys.pressed(KeyCode::Space) || is_held(TouchButton::Brake);
    c.walk = walk.clamp_length_max(1.0);
    c.drive = Vec2::new(walk.x, walk.y);
    if is_held(TouchButton::Brake) && c.drive.y > 0.0 {
        c.drive.y = 0.0;
    }
    c.look = look;
}

fn show_touch_ui(c: Res<Controls>, mut q: Query<&mut Visibility, With<TouchUi>>) {
    if !c.is_changed() {
        return;
    }
    let vis = if c.touch_mode && !c.ui_blocked { Visibility::Inherited } else { Visibility::Hidden };
    for mut v in &mut q {
        if *v != vis {
            *v = vis;
        }
    }
}

fn move_knob(c: Res<Controls>, mut knob: Query<&mut Node, With<StickKnob>>) {
    if let Ok(mut n) = knob.single_mut() {
        let v = if c.touch_mode { c.walk } else { Vec2::ZERO };
        n.left = Val::Px(v.x * STICK_R * 0.7);
        n.top = Val::Px(-v.y * STICK_R * 0.7);
    }
}
