//! Phone / menu: jobs and GPS, car dealership (360 models), wardrobe (400 skins),
//! paint shop, casino and settings.

use bevy::prelude::*;
use rand::Rng;

use crate::character::Skins;
use crate::city::{CityMap, Place, SharedMeshes};
use crate::hud::{fmt_money, Notify};
use crate::input::Controls;
use crate::jobs::{JobCommand, JobKind, JobState};
use crate::player::{Player, PlayerState};
use crate::scene::{Clock, Quality};
use crate::traffic::NpcRng;
use crate::util::*;
use crate::vehicles::{spawn_vehicle, BodyClass, Catalog, Driven, Livery, Vehicle, VehicleAssets};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Tab {
    Jobs,
    Cars,
    Skins,
    Paint,
    Casino,
    Settings,
}

impl Tab {
    const ALL: [Tab; 6] = [Tab::Jobs, Tab::Cars, Tab::Skins, Tab::Paint, Tab::Casino, Tab::Settings];
    fn title(self) -> &'static str {
        match self {
            Tab::Jobs => "Работы",
            Tab::Cars => "Автосалон",
            Tab::Skins => "Гардероб",
            Tab::Paint => "Покраска",
            Tab::Casino => "Казино",
            Tab::Settings => "Настройки",
        }
    }
}

#[derive(Resource)]
pub struct UiState {
    pub open: bool,
    pub tab: Tab,
    pub car: usize,
    pub skin: usize,
    pub paint: usize,
    pub casino: String,
}

impl Default for UiState {
    fn default() -> Self {
        Self { open: false, tab: Tab::Jobs, car: 0, skin: 0, paint: 0, casino: "Сделайте ставку".into() }
    }
}

#[derive(Resource, Default)]
pub struct Waypoint(pub Option<Vec3>);

#[derive(Component, Clone, Copy)]
enum MenuAction {
    Close,
    Tab(Tab),
    Gps(Place),
    ClearGps,
    QuitJob,
    Car(i32),
    CarClass,
    CarBuy,
    Skin(i32),
    SkinBuy,
    Paint(i32),
    PaintApply,
    Slots(i64),
    Roulette(bool),
    Quality,
    TimeSpeed,
    Exit,
}

#[derive(Component)]
struct MenuRoot;

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<UiState>()
            .init_resource::<Waypoint>()
            .add_systems(Update, (toggle, clicks, rebuild).chain().in_set(crate::GameSet::Menu));
    }
}

fn toggle(mut controls: ResMut<Controls>, mut ui: ResMut<UiState>, keys: Res<ButtonInput<KeyCode>>) {
    if controls.menu {
        ui.open = !ui.open;
    }
    if controls.phone {
        if ui.open && ui.tab == Tab::Jobs {
            ui.open = false;
        } else {
            ui.open = true;
            ui.tab = Tab::Jobs;
        }
    }
    if keys.just_pressed(KeyCode::Escape) && ui.open {
        ui.open = false;
    }
    if controls.ui_blocked != ui.open {
        controls.ui_blocked = ui.open;
    }
}

#[allow(clippy::too_many_arguments)]
fn clicks(
    mut commands: Commands,
    q: Query<(&Interaction, &MenuAction), Changed<Interaction>>,
    mut ui: ResMut<UiState>,
    mut waypoint: ResMut<Waypoint>,
    mut state: ResMut<PlayerState>,
    (mut quality, mut clock, mut rng): (ResMut<Quality>, ResMut<Clock>, ResMut<NpcRng>),
    (mut jobcmd, mut notes, mut exit): (EventWriter<JobCommand>, EventWriter<Notify>, EventWriter<AppExit>),
    (jobs, map, catalog, skins, shared): (Res<JobState>, Res<CityMap>, Res<Catalog>, Res<Skins>, Res<SharedMeshes>),
    mut va: ResMut<VehicleAssets>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    player: Query<&Transform, With<Player>>,
    vehicles: Query<(&Vehicle, &Transform)>,
) {
    let n_cars = catalog.specs.len() as i32;
    let n_skins = skins.list.len() as i32;
    let n_paints = va.paints.len() as i32;
    for (i, action) in &q {
        if *i != Interaction::Pressed {
            continue;
        }
        match *action {
            MenuAction::Close => ui.open = false,
            MenuAction::Tab(t) => ui.tab = t,
            MenuAction::Gps(p) => {
                waypoint.0 = Some(map.sites[&p].door);
                notes.write(Notify::info(format!("Метка GPS: {}", p.title())));
                ui.open = false;
            }
            MenuAction::ClearGps => waypoint.0 = None,
            MenuAction::QuitJob => {
                jobcmd.write(JobCommand::Quit);
                ui.open = false;
            }
            MenuAction::Car(d) => ui.car = (ui.car as i32 + d).rem_euclid(n_cars) as usize,
            MenuAction::CarClass => {
                let cur = catalog.specs[ui.car].class;
                let idx = BodyClass::ALL.iter().position(|c| *c == cur).unwrap_or(0);
                ui.car = catalog.first_of(BodyClass::ALL[(idx + 1) % BodyClass::ALL.len()]);
            }
            MenuAction::CarBuy => {
                let spec = &catalog.specs[ui.car];
                let owned = state.owned_cars.contains(&ui.car);
                if !owned {
                    if state.money < spec.price as i64 {
                        notes.write(Notify::warn("Недостаточно денег"));
                        continue;
                    }
                    state.money -= spec.price as i64;
                    state.owned_cars.push(ui.car);
                    notes.write(Notify::money(format!("Куплено: {} за {} ₽", spec.name, fmt_money(spec.price as i64))));
                }
                if let Ok(pt) = player.single() {
                    let p = xz(pt.translation) + Vec2::new(3.5, 3.5);
                    let paint = rng.0.gen_range(0..n_paints as usize);
                    spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, ui.car, paint, Livery::None, Vec3::new(p.x, 0.2, p.y), 0.0);
                    notes.write(Notify::info(format!("{} подан рядом с вами", spec.name)));
                }
                ui.open = false;
            }
            MenuAction::Skin(d) => ui.skin = (ui.skin as i32 + d).rem_euclid(n_skins) as usize,
            MenuAction::SkinBuy => {
                let price = skins.list[ui.skin].price as i64;
                if !state.owned_skins.contains(&ui.skin) {
                    if state.money < price {
                        notes.write(Notify::warn("Недостаточно денег"));
                        continue;
                    }
                    state.money -= price;
                    state.owned_skins.push(ui.skin);
                    notes.write(Notify::money(format!("-{price} ₽ · {}", skins.list[ui.skin].name)));
                }
                state.skin = ui.skin;
                state.body_rev += 1;
                if state.uniform_on.is_some() {
                    notes.write(Notify::info("Скин надет. На смене вы в униформе."));
                }
            }
            MenuAction::Paint(d) => ui.paint = (ui.paint as i32 + d).rem_euclid(n_paints) as usize,
            MenuAction::PaintApply => {
                let Some(car) = state.vehicle else {
                    notes.write(Notify::warn("Сядьте в машину, чтобы покрасить её"));
                    continue;
                };
                if jobs.vehicle == Some(car) {
                    notes.write(Notify::warn("Служебный транспорт красить нельзя"));
                    continue;
                }
                if state.money < 500 {
                    notes.write(Notify::warn("Покраска стоит 500 ₽"));
                    continue;
                }
                let Ok((v, t)) = vehicles.get(car) else { continue };
                state.money -= 500;
                let new = spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, v.spec, ui.paint, Livery::None, t.translation, v.yaw);
                commands.entity(new).insert(Driven);
                commands.entity(car).despawn();
                state.vehicle = Some(new);
                notes.write(Notify::money(format!("-500 ₽ · Цвет: {}", va.paints[ui.paint].name)));
            }
            MenuAction::Slots(bet) => {
                if state.money < bet {
                    ui.casino = "Недостаточно денег для ставки".into();
                    continue;
                }
                state.money -= bet;
                const SYM: [&str; 5] = ["ВИШНЯ", "ЛИМОН", "КОЛОКОЛ", "BAR", "СЕМЬ"];
                let roll: Vec<usize> = (0..3)
                    .map(|_| {
                        let r = rng.0.gen_range(0..100);
                        match r {
                            0..=29 => 0,
                            30..=54 => 1,
                            55..=74 => 2,
                            75..=91 => 3,
                            _ => 4,
                        }
                    })
                    .collect();
                let win = if roll[0] == roll[1] && roll[1] == roll[2] {
                    bet * [6, 8, 12, 20, 50][roll[0]]
                } else if roll[0] == roll[1] || roll[1] == roll[2] {
                    bet * 3 / 2
                } else {
                    0
                };
                state.money += win;
                let line = roll.iter().map(|&i| SYM[i]).collect::<Vec<_>>().join(" | ");
                ui.casino = if win > 0 { format!("[ {line} ]\nВыигрыш: {} ₽", fmt_money(win)) } else { format!("[ {line} ]\nНе повезло") };
            }
            MenuAction::Roulette(red) => {
                let bet = 1000;
                if state.money < bet {
                    ui.casino = "Недостаточно денег для ставки".into();
                    continue;
                }
                state.money -= bet;
                let n = rng.0.gen_range(0..37);
                const REDS: [i32; 18] = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
                let is_red = REDS.contains(&n);
                let color = if n == 0 { "зеро" } else if is_red { "красное" } else { "чёрное" };
                let won = n != 0 && is_red == red;
                if won {
                    state.money += bet * 2;
                }
                ui.casino = format!("Выпало {n} ({color})\n{}", if won { "Выигрыш: 2 000 ₽" } else { "Ставка проиграна" });
            }
            MenuAction::Quality => {
                quality.level = (quality.level + 1) % 3;
            }
            MenuAction::TimeSpeed => {
                clock.speed = if clock.speed == 0.0 { 1.0 / 50.0 } else if clock.speed < 0.1 { 0.2 } else { 0.0 };
            }
            MenuAction::Exit => {
                exit.write(AppExit::Success);
            }
        }
    }
}

fn btn(p: &mut ChildSpawnerCommands, label: impl Into<String>, action: MenuAction, accent: bool) {
    p.spawn((
        Button,
        action,
        Node {
            padding: UiRect::axes(Val::Px(14.0), Val::Px(9.0)),
            margin: UiRect::all(Val::Px(4.0)),
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(if accent { Color::srgb(0.16, 0.48, 0.95) } else { Color::srgba(1.0, 1.0, 1.0, 0.1) }),
        BorderRadius::all(Val::Px(10.0)),
    ))
    .with_children(|b| {
        b.spawn((Text::new(label), TextFont { font_size: 16.0, ..default() }, TextColor(Color::WHITE)));
    });
}

fn label(p: &mut ChildSpawnerCommands, text: impl Into<String>, size: f32, color: Color) {
    p.spawn((Text::new(text), TextFont { font_size: size, ..default() }, TextColor(color), Node { margin: UiRect::vertical(Val::Px(3.0)), ..default() }));
}

fn row(p: &mut ChildSpawnerCommands, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn(Node { flex_direction: FlexDirection::Row, flex_wrap: FlexWrap::Wrap, align_items: AlignItems::Center, ..default() }).with_children(f);
}

fn bar(p: &mut ChildSpawnerCommands, name: &str, f: f32, color: Color) {
    row(p, |r| {
        r.spawn((Text::new(name), TextFont { font_size: 14.0, ..default() }, TextColor(Color::srgba(1.0, 1.0, 1.0, 0.75)), Node { width: Val::Px(130.0), ..default() }));
        r.spawn((Node { width: Val::Px(220.0), height: Val::Px(8.0), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.12)), BorderRadius::all(Val::Px(4.0))))
            .with_children(|b| {
                b.spawn((Node { width: Val::Percent(f.clamp(0.02, 1.0) * 100.0), height: Val::Percent(100.0), ..default() }, BackgroundColor(color), BorderRadius::all(Val::Px(4.0))));
            });
    });
}

#[allow(clippy::too_many_arguments)]
fn rebuild(
    mut commands: Commands,
    ui: Res<UiState>,
    state: Res<PlayerState>,
    jobs: Res<JobState>,
    catalog: Res<Catalog>,
    skins: Res<Skins>,
    va: Res<VehicleAssets>,
    quality: Res<Quality>,
    clock: Res<Clock>,
    waypoint: Res<Waypoint>,
    root: Query<Entity, With<MenuRoot>>,
) {
    if !(ui.is_changed() || (ui.open && (state.is_changed() || jobs.is_changed()))) {
        return;
    }
    for e in &root {
        commands.entity(e).despawn();
    }
    if !ui.open {
        return;
    }
    let white = Color::WHITE;
    let dim = Color::srgba(1.0, 1.0, 1.0, 0.7);
    commands
        .spawn((
            MenuRoot,
            Node {
                position_type: PositionType::Absolute,
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.45)),
            GlobalZIndex(10),
        ))
        .with_children(|bg| {
            bg.spawn((
                Node {
                    width: Val::Percent(92.0),
                    max_width: Val::Px(760.0),
                    max_height: Val::Percent(92.0),
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::all(Val::Px(16.0)),
                    overflow: Overflow::scroll_y(),
                    ..default()
                },
                BackgroundColor(Color::srgba(0.05, 0.06, 0.1, 0.96)),
                BorderRadius::all(Val::Px(18.0)),
            ))
            .with_children(|p| {
                row(p, |r| {
                    r.spawn((Text::new("Порт-Светлый"), TextFont { font_size: 22.0, ..default() }, TextColor(white), Node { margin: UiRect::right(Val::Px(12.0)), ..default() }));
                    r.spawn((Text::new(format!("{} ₽", fmt_money(state.money))), TextFont { font_size: 18.0, ..default() }, TextColor(Color::srgb(0.5, 1.0, 0.6))));
                    r.spawn(Node { flex_grow: 1.0, ..default() });
                    btn(r, "Закрыть ×", MenuAction::Close, false);
                });
                row(p, |r| {
                    for t in Tab::ALL {
                        btn(r, t.title(), MenuAction::Tab(t), t == ui.tab);
                    }
                });
                p.spawn((Node { height: Val::Px(1.0), margin: UiRect::vertical(Val::Px(8.0)), ..default() }, BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.15))));

                match ui.tab {
                    Tab::Jobs => {
                        if let Some(j) = jobs.job {
                            row(p, |r| {
                                label(r, format!("Сейчас: {} · за смену {} ₽  ", j.title(), fmt_money(jobs.shift_earned)), 16.0, white);
                                btn(r, "Завершить смену", MenuAction::QuitJob, true);
                            });
                        }
                        label(p, "Работы и фракции (GPS проложит путь к штабу, устроиться — у входа):", 14.0, dim);
                        for j in JobKind::ALL {
                            row(p, |r| {
                                r.spawn((Node { width: Val::Px(14.0), height: Val::Px(14.0), margin: UiRect::right(Val::Px(8.0)), ..default() }, BackgroundColor(j.color()), BorderRadius::MAX));
                                let rank = j.ranks()[jobs.rank(j)];
                                r.spawn((
                                    Text::new(format!("{} — {}\n{}", j.title(), rank, j.about())),
                                    TextFont { font_size: 14.0, ..default() },
                                    TextColor(white),
                                    Node { width: Val::Px(420.0), ..default() },
                                ));
                                btn(r, "GPS", MenuAction::Gps(j.hq()), false);
                            });
                        }
                        label(p, "Заведения:", 14.0, dim);
                        row(p, |r| {
                            for pl in [Place::Casino, Place::CarShop, Place::Clothes] {
                                btn(r, pl.title(), MenuAction::Gps(pl), false);
                            }
                            if waypoint.0.is_some() {
                                btn(r, "Убрать метку", MenuAction::ClearGps, false);
                            }
                        });
                    }
                    Tab::Cars => {
                        let s = &catalog.specs[ui.car];
                        label(p, format!("Модель {} из {}", ui.car + 1, catalog.specs.len()), 13.0, dim);
                        label(p, s.name.clone(), 26.0, white);
                        label(p, format!("{} · до {} км/ч · {} ₽", s.class.title(), s.kmh(), fmt_money(s.price as i64)), 16.0, dim);
                        bar(p, "Скорость", s.max_speed / 92.0, Color::srgb(0.3, 0.8, 1.0));
                        bar(p, "Разгон", s.accel / 15.0, Color::srgb(1.0, 0.6, 0.2));
                        bar(p, "Управляемость", s.grip / 1.1, Color::srgb(0.4, 1.0, 0.5));
                        bar(p, "Размер", s.length / 12.0, Color::srgb(0.8, 0.6, 1.0));
                        row(p, |r| {
                            btn(r, "«10", MenuAction::Car(-10), false);
                            btn(r, "‹", MenuAction::Car(-1), false);
                            btn(r, "›", MenuAction::Car(1), false);
                            btn(r, "10»", MenuAction::Car(10), false);
                            btn(r, format!("Класс: {}", s.class.title()), MenuAction::CarClass, false);
                        });
                        let owned = state.owned_cars.contains(&ui.car);
                        row(p, |r| {
                            btn(r, if owned { "Вызвать к себе".to_string() } else { format!("Купить за {} ₽", fmt_money(s.price as i64)) }, MenuAction::CarBuy, true);
                        });
                        label(p, format!("В гараже: {} машин", state.owned_cars.len()), 13.0, dim);
                    }
                    Tab::Skins => {
                        let s = &skins.list[ui.skin];
                        label(p, format!("Скин {} из {}", ui.skin + 1, skins.list.len()), 13.0, dim);
                        label(p, s.name.clone(), 24.0, white);
                        row(p, |r| {
                            for c in [s.skin, s.hair, s.head_color, s.shirt, s.jacket.unwrap_or(s.shirt), s.pants, s.shoes] {
                                r.spawn((Node { width: Val::Px(30.0), height: Val::Px(30.0), margin: UiRect::all(Val::Px(3.0)), ..default() }, BackgroundColor(c), BorderRadius::all(Val::Px(6.0))));
                            }
                        });
                        label(p, format!("Головной убор: {:?} · рост {:.0} см · очки: {}", s.head, 175.0 * s.height, if s.glasses { "да" } else { "нет" }), 14.0, dim);
                        row(p, |r| {
                            btn(r, "«10", MenuAction::Skin(-10), false);
                            btn(r, "‹", MenuAction::Skin(-1), false);
                            btn(r, "›", MenuAction::Skin(1), false);
                            btn(r, "10»", MenuAction::Skin(10), false);
                        });
                        let owned = state.owned_skins.contains(&ui.skin);
                        let worn = state.skin == ui.skin;
                        row(p, |r| {
                            let text = if worn { "Надето".to_string() } else if owned { "Надеть".to_string() } else { format!("Купить за {} ₽", fmt_money(s.price as i64)) };
                            btn(r, text, MenuAction::SkinBuy, !worn);
                        });
                        label(p, format!("Куплено скинов: {}", state.owned_skins.len()), 13.0, dim);
                    }
                    Tab::Paint => {
                        let paint = &va.paints[ui.paint];
                        label(p, format!("Покраска {} из {}", ui.paint + 1, va.paints.len()), 13.0, dim);
                        row(p, |r| {
                            r.spawn((Node { width: Val::Px(60.0), height: Val::Px(36.0), margin: UiRect::right(Val::Px(10.0)), ..default() }, BackgroundColor(paint.color), BorderRadius::all(Val::Px(8.0))));
                            if let Some(s) = paint.stripe {
                                r.spawn((Node { width: Val::Px(20.0), height: Val::Px(36.0), margin: UiRect::right(Val::Px(10.0)), ..default() }, BackgroundColor(s), BorderRadius::all(Val::Px(6.0))));
                            }
                            label(r, format!("{} · {:?}", paint.name, paint.finish), 20.0, white);
                        });
                        row(p, |r| {
                            btn(r, "‹", MenuAction::Paint(-1), false);
                            btn(r, "›", MenuAction::Paint(1), false);
                            btn(r, "Покрасить (500 ₽)", MenuAction::PaintApply, true);
                        });
                        label(p, "Красится машина, в которой вы сидите.", 13.0, dim);
                    }
                    Tab::Casino => {
                        label(p, "Казино «Маяк»", 24.0, Color::srgb(1.0, 0.4, 0.7));
                        label(p, ui.casino.clone(), 20.0, white);
                        label(p, "Слоты:", 14.0, dim);
                        row(p, |r| {
                            for bet in [100, 1000, 5000] {
                                btn(r, format!("Крутить {} ₽", fmt_money(bet)), MenuAction::Slots(bet), false);
                            }
                        });
                        label(p, "Рулетка (ставка 1 000 ₽):", 14.0, dim);
                        row(p, |r| {
                            btn(r, "На красное", MenuAction::Roulette(true), false);
                            btn(r, "На чёрное", MenuAction::Roulette(false), false);
                        });
                        label(p, "Играйте с умом: казино всегда в плюсе.", 12.0, dim);
                    }
                    Tab::Settings => {
                        row(p, |r| {
                            label(r, format!("Графика: {}  ", quality.name()), 16.0, white);
                            btn(r, "Сменить", MenuAction::Quality, false);
                        });
                        row(p, |r| {
                            let sp = if clock.speed == 0.0 { "пауза" } else if clock.speed > 0.1 { "быстро" } else { "обычно" };
                            label(r, format!("Время: {} ({})  ", clock.text(), sp), 16.0, white);
                            btn(r, "Сменить скорость", MenuAction::TimeSpeed, false);
                        });
                        if !cfg!(target_os = "android") {
                            btn(p, "Выйти из игры", MenuAction::Exit, false);
                        }
                        label(p, "Порт-Светлый — своя игра на Rust и Bevy. Весь город, машины и люди генерируются кодом.", 12.0, dim);
                    }
                }
            });
        });
    let _ = Place::ALL;
}
