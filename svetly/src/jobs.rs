//! Jobs and factions. Each job has a headquarters, a uniform, a service vehicle,
//! ranks, and a mission generator built from a few step types (drive to, stay,
//! follow, catch), so adding a new profession is one more `match` arm.

use std::collections::{HashMap, VecDeque};

use bevy::prelude::*;
use rand::seq::SliceRandom;
use rand::Rng;

use crate::character::{build_body, ColorMats, Rig, Skins};
use crate::city::{CityMap, Place, SharedMeshes, BEACH_END, CURB, HALF};
use crate::hud::Notify;
use crate::input::Controls;
use crate::menu::{Tab, UiState};
use crate::player::{Player, PlayerState};
use crate::traffic::{NpcRng, Pursuer, TrafficAi};
use crate::util::*;
use crate::vehicles::{spawn_vehicle, BodyClass, Catalog, Driven, Livery, VehicleAssets};

#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum JobKind {
    Taxi,
    Courier,
    BusDriver,
    Trucker,
    CashTransport,
    Firefighter,
    Medic,
    TrafficPolice,
    Fsb,
    Journalist,
    Diver,
    Opg,
    Government,
    Mechanic,
    Garbage,
}

impl JobKind {
    pub const ALL: [JobKind; 15] = [
        JobKind::Taxi,
        JobKind::Courier,
        JobKind::BusDriver,
        JobKind::Trucker,
        JobKind::CashTransport,
        JobKind::Firefighter,
        JobKind::Medic,
        JobKind::TrafficPolice,
        JobKind::Fsb,
        JobKind::Journalist,
        JobKind::Diver,
        JobKind::Opg,
        JobKind::Government,
        JobKind::Mechanic,
        JobKind::Garbage,
    ];

    pub fn title(self) -> &'static str {
        match self {
            JobKind::Taxi => "Таксист",
            JobKind::Courier => "Курьер",
            JobKind::BusDriver => "Водитель автобуса",
            JobKind::Trucker => "Дальнобойщик",
            JobKind::CashTransport => "Инкассатор",
            JobKind::Firefighter => "Пожарный",
            JobKind::Medic => "Врач скорой помощи",
            JobKind::TrafficPolice => "Инспектор ГИБДД",
            JobKind::Fsb => "Оперативник ФСБ",
            JobKind::Journalist => "Журналист",
            JobKind::Diver => "Водолаз",
            JobKind::Opg => "ОПГ",
            JobKind::Government => "Сотрудник мэрии",
            JobKind::Mechanic => "Механик",
            JobKind::Garbage => "Мусорщик",
        }
    }

    pub fn about(self) -> &'static str {
        match self {
            JobKind::Taxi => "Забирайте пассажиров и везите по адресу",
            JobKind::Courier => "Развозите посылки по городу",
            JobKind::BusDriver => "Маршрут с остановками",
            JobKind::Trucker => "Грузы со склада на терминал",
            JobKind::CashTransport => "Объезд банкоматов на броневике",
            JobKind::Firefighter => "Выезды на пожары",
            JobKind::Medic => "Помощь пострадавшим и доставка в больницу",
            JobKind::TrafficPolice => "Догоняйте нарушителей",
            JobKind::Fsb => "Скрытое наблюдение за объектом",
            JobKind::Journalist => "Репортажи с места событий",
            JobKind::Diver => "Подъём находок со дна залива",
            JobKind::Opg => "Перевозка груза, уход от погони",
            JobKind::Government => "Документы по городским ведомствам",
            JobKind::Mechanic => "Ремонт сломанных машин",
            JobKind::Garbage => "Вывоз мусора",
        }
    }

    pub fn hq(self) -> Place {
        match self {
            JobKind::Taxi => Place::TaxiPark,
            JobKind::Courier => Place::PostOffice,
            JobKind::BusDriver => Place::BusDepot,
            JobKind::Trucker => Place::TruckDepot,
            JobKind::CashTransport => Place::Bank,
            JobKind::Firefighter => Place::FireStation,
            JobKind::Medic => Place::Hospital,
            JobKind::TrafficPolice => Place::TrafficPolice,
            JobKind::Fsb => Place::Fsb,
            JobKind::Journalist => Place::NewsAgency,
            JobKind::Diver => Place::DiveCenter,
            JobKind::Opg => Place::OpgGarage,
            JobKind::Government => Place::Government,
            JobKind::Mechanic => Place::AutoService,
            JobKind::Garbage => Place::WasteYard,
        }
    }

    fn vehicle(self) -> (BodyClass, Livery, usize) {
        match self {
            JobKind::Taxi => (BodyClass::Sedan, Livery::Taxi, 3),
            JobKind::Courier => (BodyClass::Van, Livery::Courier, 1),
            JobKind::BusDriver => (BodyClass::Bus, Livery::Bus, 0),
            JobKind::Trucker => (BodyClass::Truck, Livery::Cargo, 2),
            JobKind::CashTransport => (BodyClass::Van, Livery::Cash, 5),
            JobKind::Firefighter => (BodyClass::Truck, Livery::Fire, 0),
            JobKind::Medic => (BodyClass::Van, Livery::Ambulance, 3),
            JobKind::TrafficPolice => (BodyClass::Sedan, Livery::Police, 7),
            JobKind::Fsb => (BodyClass::Sedan, Livery::Fsb, 11),
            JobKind::Journalist => (BodyClass::Van, Livery::News, 7),
            JobKind::Diver => (BodyClass::Pickup, Livery::Dive, 2),
            JobKind::Opg => (BodyClass::Suv, Livery::Gov, 4),
            JobKind::Government => (BodyClass::Sedan, Livery::Gov, 20),
            JobKind::Mechanic => (BodyClass::Pickup, Livery::Service, 6),
            JobKind::Garbage => (BodyClass::Truck, Livery::Garbage, 5),
        }
    }

    pub fn ranks(self) -> [&'static str; 5] {
        match self {
            JobKind::Opg => ["Шнырь", "Боец", "Бригадир", "Смотрящий", "Авторитет"],
            JobKind::Fsb => ["Лейтенант", "Ст. лейтенант", "Капитан", "Майор", "Полковник"],
            JobKind::TrafficPolice => ["Сержант", "Ст. сержант", "Лейтенант", "Капитан", "Майор"],
            JobKind::Firefighter => ["Пожарный", "Ст. пожарный", "Командир отделения", "Нач. караула", "Нач. части"],
            JobKind::Medic => ["Санитар", "Фельдшер", "Врач", "Ст. врач", "Главврач"],
            JobKind::Government => ["Специалист", "Ведущий спец.", "Начальник отдела", "Зам. мэра", "Мэр"],
            JobKind::Journalist => ["Стажёр", "Корреспондент", "Репортёр", "Ведущий", "Главред"],
            _ => ["Стажёр", "Сотрудник", "Опытный", "Старший", "Мастер"],
        }
    }

    pub fn color(self) -> Color {
        self.hq().color()
    }
}

pub fn rank_of(xp: u32) -> usize {
    [0, 5, 15, 30, 50].iter().rposition(|&t| xp >= t).unwrap_or(0)
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Need {
    Any,
    JobVehicle,
    OnFoot,
    Swimming,
}

#[derive(Clone, Copy, Debug)]
enum Target {
    Point(Vec3),
    Follow(Entity),
}

#[derive(Clone, Copy, Debug)]
enum Kind {
    Reach,
    Hold(f32),
    /// Stay between `min` and `max` metres for `secs`.
    Tail { min: f32, max: f32, secs: f32 },
}

#[derive(Clone, Debug)]
enum Effect {
    Despawn(Entity),
    Unmark(Entity),
    Wanted(u8),
    ClearWanted,
}

#[derive(Clone, Debug)]
struct Step {
    label: String,
    target: Target,
    radius: f32,
    need: Need,
    kind: Kind,
    progress: f32,
    effects: Vec<Effect>,
}

impl Step {
    fn new(label: impl Into<String>, target: Target, radius: f32, need: Need, kind: Kind) -> Self {
        Self { label: label.into(), target, radius, need, kind, progress: 0.0, effects: Vec::new() }
    }
    fn then(mut self, e: Effect) -> Self {
        self.effects.push(e);
        self
    }
}

#[derive(Clone, Debug)]
struct Mission {
    title: String,
    steps: VecDeque<Step>,
    total: usize,
    reward: i64,
    spawned: Vec<Entity>,
}

#[derive(Resource, Default)]
pub struct JobState {
    pub job: Option<JobKind>,
    pub vehicle: Option<Entity>,
    mission: Option<Mission>,
    pub xp: HashMap<JobKind, u32>,
    pub wanted: u8,
    pub shift_earned: i64,
    next_in: f32,
    tail_close: f32,
}

impl JobState {
    pub fn rank(&self, job: JobKind) -> usize {
        rank_of(*self.xp.get(&job).unwrap_or(&0))
    }
    pub fn mission_text(&self) -> Option<(String, String)> {
        let m = self.mission.as_ref()?;
        let step = m.steps.front()?;
        let done = m.total - m.steps.len();
        let mut line = format!("{} ({}/{})", step.label, done + 1, m.total);
        match step.kind {
            Kind::Hold(s) if step.progress > 0.0 => line += &format!(" — {:.0}%", step.progress / s * 100.0),
            Kind::Tail { secs, .. } => line += &format!(" — {:.0} с", (secs - step.progress).max(0.0)),
            _ => {}
        }
        Some((m.title.clone(), line))
    }
    pub fn target(&self) -> Option<Target2> {
        let step = self.mission.as_ref()?.steps.front()?;
        Some(match step.target {
            Target::Point(p) => Target2::Point(p),
            Target::Follow(e) => Target2::Entity(e),
        })
    }
}

/// Public view of the current target for the HUD.
#[derive(Clone, Copy)]
pub enum Target2 {
    Point(Vec3),
    Entity(Entity),
}

/// What pressing "Действие" will do right now.
#[derive(Resource, Default)]
pub struct Prompt {
    pub text: Option<String>,
    action: Option<PromptAction>,
}

#[derive(Clone, Copy)]
enum PromptAction {
    Join(JobKind),
    Quit,
    Open(Tab),
}

#[derive(Component)]
struct MissionMarker;
#[derive(Component)]
struct Flame;
#[derive(Component)]
pub struct MarkedCar;

pub struct JobsPlugin;

impl Plugin for JobsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<JobState>()
            .init_resource::<Prompt>()
            .add_event::<JobCommand>()
            .add_systems(Startup, spawn_site_markers)
            .add_systems(
                Update,
                (prompts, handle_commands, run_mission, wanted_level, move_marker, flicker_flames)
                    .chain()
                    .in_set(crate::GameSet::Jobs),
            );
    }
}

/// Requests from menus (phone) to the job system.
#[derive(Event, Clone, Copy)]
pub enum JobCommand {
    Join(JobKind),
    Quit,
}

fn spawn_site_markers(
    mut commands: Commands,
    map: Res<CityMap>,
    shared: Res<SharedMeshes>,
    mut mats: ResMut<Assets<StandardMaterial>>,
) {
    for site in map.sites.values() {
        let c = site.place.color().to_linear();
        let m = mats.add(StandardMaterial {
            base_color: site.place.color().with_alpha(0.5),
            emissive: LinearRgba::rgb(c.red * 6.0, c.green * 6.0, c.blue * 6.0),
            alpha_mode: AlphaMode::Add,
            unlit: true,
            ..default()
        });
        commands.spawn((
            Mesh3d(shared.ring.clone()),
            MeshMaterial3d(m.clone()),
            Transform::from_translation(site.door + Vec3::Y * 0.03)
                .with_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2))
                .with_scale(Vec3::splat(1.4)),
        ));
        commands.spawn((
            Mesh3d(shared.cylinder.clone()),
            MeshMaterial3d(m),
            Transform::from_translation(site.door + Vec3::Y * 1.0).with_scale(Vec3::new(0.25, 2.0, 0.25)),
        ));
    }
    let m = mats.add(StandardMaterial {
        base_color: Color::srgba(1.0, 0.85, 0.2, 0.35),
        emissive: LinearRgba::rgb(8.0, 6.0, 1.0),
        alpha_mode: AlphaMode::Add,
        unlit: true,
        ..default()
    });
    commands
        .spawn((MissionMarker, Transform::default(), Visibility::Hidden))
        .with_children(|c| {
            c.spawn((Mesh3d(shared.cylinder.clone()), MeshMaterial3d(m.clone()), Transform::from_xyz(0.0, 30.0, 0.0).with_scale(Vec3::new(1.2, 60.0, 1.2))));
            c.spawn((
                Mesh3d(shared.ring.clone()),
                MeshMaterial3d(m),
                Transform::from_xyz(0.0, 0.25, 0.0).with_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2)).with_scale(Vec3::splat(4.0)),
            ));
        });
}

fn prompts(
    map: Res<CityMap>,
    jobs: Res<JobState>,
    state: Res<PlayerState>,
    player: Query<&Transform, With<Player>>,
    mut prompt: ResMut<Prompt>,
    mut controls: ResMut<Controls>,
    mut ui: ResMut<UiState>,
    mut cmds: EventWriter<JobCommand>,
) {
    prompt.text = None;
    prompt.action = None;
    if state.vehicle.is_some() {
        return;
    }
    let Ok(pt) = player.single() else { return };
    for site in map.sites.values() {
        if (xz(site.door) - xz(pt.translation)).length() > 2.6 {
            continue;
        }
        let place = site.place;
        let (text, action) = match place {
            Place::Casino => ("Войти в казино".to_string(), PromptAction::Open(Tab::Casino)),
            Place::CarShop => ("Автосалон: 360 моделей".to_string(), PromptAction::Open(Tab::Cars)),
            Place::Clothes => ("Магазин одежды: 400 скинов".to_string(), PromptAction::Open(Tab::Skins)),
            _ => {
                let job = JobKind::ALL.into_iter().find(|j| j.hq() == place).unwrap();
                match jobs.job {
                    Some(j) if j == job => (format!("Завершить смену: {}", job.title()), PromptAction::Quit),
                    Some(other) => (format!("Сначала завершите смену ({})", other.title()), PromptAction::Open(Tab::Jobs)),
                    None => {
                        let r = jobs.rank(job);
                        (format!("Устроиться: {} · ранг «{}»", job.title(), job.ranks()[r]), PromptAction::Join(job))
                    }
                }
            }
        };
        prompt.text = Some(format!("{}\n{}", place.title(), text));
        prompt.action = Some(action);
    }
    if controls.action && !controls.ui_blocked {
        if let Some(a) = prompt.action {
            controls.action = false;
            match a {
                PromptAction::Join(j) => {
                    cmds.write(JobCommand::Join(j));
                }
                PromptAction::Quit => {
                    cmds.write(JobCommand::Quit);
                }
                PromptAction::Open(tab) => {
                    ui.open = true;
                    ui.tab = tab;
                }
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn handle_commands(
    mut commands: Commands,
    mut events: EventReader<JobCommand>,
    mut jobs: ResMut<JobState>,
    mut state: ResMut<PlayerState>,
    map: Res<CityMap>,
    catalog: Res<Catalog>,
    shared: Res<SharedMeshes>,
    mut va: ResMut<VehicleAssets>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut notes: EventWriter<Notify>,
    mut player_vis: Query<&mut Visibility, With<Player>>,
) {
    for ev in events.read() {
        match *ev {
            JobCommand::Join(job) => {
                if jobs.job.is_some() {
                    notes.write(Notify::warn("Сначала завершите текущую смену"));
                    continue;
                }
                let site = &map.sites[&job.hq()];
                let (class, livery, offset) = job.vehicle();
                let spec = (catalog.first_of(class) + offset).min(catalog.specs.len() - 1);
                let car = spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, spec, 1, livery, site.curb, site.curb_yaw);
                jobs.job = Some(job);
                jobs.vehicle = Some(car);
                jobs.next_in = 0.5;
                jobs.shift_earned = 0;
                state.uniform_on = Some(job);
                state.body_rev += 1;
                let r = jobs.rank(job);
                notes.write(Notify::good(format!("Вы на смене: {} · {}", job.title(), job.ranks()[r])));
                notes.write(Notify::info(format!("Служебный {} ждёт у входа (F — сесть)", catalog.specs[spec].name)));
            }
            JobCommand::Quit => {
                let Some(job) = jobs.job.take() else { continue };
                if let Some(m) = jobs.mission.take() {
                    for e in m.spawned {
                        commands.entity(e).try_despawn();
                    }
                }
                if let Some(car) = jobs.vehicle.take() {
                    if state.vehicle == Some(car) {
                        state.vehicle = None;
                        if let Ok(mut v) = player_vis.single_mut() {
                            *v = Visibility::Inherited;
                        }
                    }
                    commands.entity(car).try_despawn();
                }
                jobs.wanted = 0;
                state.uniform_on = None;
                state.body_rev += 1;
                notes.write(Notify::info(format!("Смена «{}» окончена. Заработано: {} ₽", job.title(), jobs.shift_earned)));
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn new_mission(
    job: JobKind,
    commands: &mut Commands,
    rng: &mut impl Rng,
    map: &CityMap,
    from: Vec3,
    skins: &Skins,
    shared: &SharedMeshes,
    cm: &mut ColorMats,
    mats: &mut Assets<StandardMaterial>,
    traffic: &Query<(Entity, &Transform), With<TrafficAi>>,
) -> Mission {
    let mut spawned = Vec::new();
    let mut steps = Vec::new();
    let far_curb = |rng: &mut dyn rand::RngCore, min: f32| -> (Vec3, Vec3) {
        let mut best = map.random_curb_point(rng);
        for _ in 0..30 {
            let c = map.random_curb_point(rng);
            if (xz(c.1) - xz(from)).length() > min {
                return c;
            }
            best = c;
        }
        best
    };
    let mut spawn_person = |commands: &mut Commands, rng: &mut dyn rand::RngCore, at: Vec3, lying: bool, mats: &mut Assets<StandardMaterial>| -> Entity {
        let skin = &skins.list[rng.gen_range(0..skins.list.len())];
        let mut t = Transform::from_translation(at).with_rotation(Quat::from_rotation_y(rng.gen_range(0.0..6.28)));
        if lying {
            t.rotation *= Quat::from_rotation_x(-1.5);
            t.translation.y += 0.2;
        }
        let e = commands.spawn((t, Visibility::default(), Rig::default())).id();
        build_body(commands, e, skin, shared, cm, mats);
        e
    };
    let site = |p: Place| map.sites[&p].curb;
    let door = |p: Place| map.sites[&p].door;
    let title;
    let mut reward: i64;

    match job {
        JobKind::Taxi => {
            let (walk, road) = far_curb(rng, 80.0);
            let ped = spawn_person(commands, rng, walk, false, mats);
            spawned.push(ped);
            let (_, dest) = far_curb(rng, 250.0);
            let dist = (xz(dest) - xz(road)).length();
            steps.push(Step::new("Заберите пассажира", Target::Point(road), 7.0, Need::JobVehicle, Kind::Hold(1.0)).then(Effect::Despawn(ped)));
            steps.push(Step::new("Отвезите пассажира по адресу", Target::Point(dest), 7.0, Need::JobVehicle, Kind::Hold(1.0)));
            title = "Заказ такси".to_string();
            reward = 250 + (dist * 1.6) as i64;
        }
        JobKind::Courier => {
            for k in 0..3 {
                let (_, road) = far_curb(rng, 120.0);
                steps.push(Step::new(format!("Доставьте посылку №{}", k + 1), Target::Point(road), 7.0, Need::JobVehicle, Kind::Hold(1.5)));
            }
            title = "Доставка посылок".into();
            reward = 900;
        }
        JobKind::BusDriver => {
            let mut stops: Vec<Vec3> = (0..6).map(|_| map.random_curb_point(rng).1).collect();
            stops.sort_by(|a, b| a.x.atan2(a.z).partial_cmp(&b.x.atan2(b.z)).unwrap());
            for (k, s) in stops.into_iter().enumerate() {
                steps.push(Step::new(format!("Остановка {}", k + 1), Target::Point(s), 9.0, Need::JobVehicle, Kind::Hold(3.0)));
            }
            steps.push(Step::new("Вернитесь в парк", Target::Point(site(Place::BusDepot)), 10.0, Need::JobVehicle, Kind::Reach));
            title = "Городской маршрут".into();
            reward = 1400;
        }
        JobKind::Trucker => {
            steps.push(Step::new("Погрузка на складе", Target::Point(site(Place::TruckDepot)), 10.0, Need::JobVehicle, Kind::Hold(4.0)));
            let port = Vec3::new(HALF - 4.0, 0.0, rng.gen_range(-HALF + 20.0..HALF - 20.0));
            let mut dest = far_curb(rng, 400.0).1;
            if rng.gen_bool(0.5) {
                dest = port;
            }
            steps.push(Step::new("Доставьте груз", Target::Point(dest), 10.0, Need::JobVehicle, Kind::Hold(4.0)));
            steps.push(Step::new("Вернитесь на терминал", Target::Point(site(Place::TruckDepot)), 10.0, Need::JobVehicle, Kind::Reach));
            title = "Рейс".into();
            reward = 1800;
        }
        JobKind::CashTransport => {
            steps.push(Step::new("Получите кассеты в банке", Target::Point(site(Place::Bank)), 8.0, Need::JobVehicle, Kind::Hold(3.0)));
            for k in 0..3 {
                let (_, road) = far_curb(rng, 100.0);
                steps.push(Step::new(format!("Зарядите банкомат {}", k + 1), Target::Point(road), 7.0, Need::JobVehicle, Kind::Hold(4.0)));
            }
            steps.push(Step::new("Сдайте выручку в банк", Target::Point(site(Place::Bank)), 8.0, Need::JobVehicle, Kind::Hold(2.0)));
            title = "Инкассация".into();
            reward = 2000;
        }
        JobKind::Firefighter => {
            let (pos, half) = loop {
                let s = map.building_spots[rng.gen_range(0..map.building_spots.len())];
                if (xz(s.0) - xz(from)).length() > 120.0 {
                    break s;
                }
            };
            let fire = commands.spawn((Transform::from_translation(pos), Visibility::default())).id();
            commands.entity(fire).with_children(|c| {
                for k in 0..8 {
                    let a = k as f32 * 0.8;
                    c.spawn((
                        Flame,
                        Mesh3d(shared.sphere.clone()),
                        MeshMaterial3d(mats.add(StandardMaterial {
                            base_color: Color::srgb(1.0, 0.5, 0.1),
                            emissive: LinearRgba::rgb(30.0, 9.0, 1.0),
                            unlit: true,
                            ..default()
                        })),
                        Transform::from_xyz(a.cos() * half * 0.6, 3.0 + (k % 3) as f32 * 2.0, a.sin() * half * 0.6).with_scale(Vec3::splat(2.5)),
                    ));
                }
                c.spawn((PointLight { intensity: 4.0e7, range: 50.0, color: Color::srgb(1.0, 0.5, 0.15), ..default() }, Transform::from_xyz(0.0, 6.0, 0.0)));
            });
            spawned.push(fire);
            steps.push(Step::new("Выезд на пожар", Target::Point(pos), half + 16.0, Need::JobVehicle, Kind::Reach));
            steps.push(Step::new("Тушите огонь (оставайтесь рядом)", Target::Point(pos), half + 14.0, Need::Any, Kind::Hold(8.0)).then(Effect::Despawn(fire)));
            steps.push(Step::new("Вернитесь в часть", Target::Point(site(Place::FireStation)), 10.0, Need::JobVehicle, Kind::Reach));
            title = "Пожар".into();
            reward = 1900;
        }
        JobKind::Medic => {
            let (walk, road) = far_curb(rng, 120.0);
            let ped = spawn_person(commands, rng, walk, true, mats);
            spawned.push(ped);
            steps.push(Step::new("Вызов: пострадавший", Target::Point(road), 9.0, Need::JobVehicle, Kind::Reach));
            steps.push(Step::new("Окажите помощь", Target::Point(walk), 3.0, Need::OnFoot, Kind::Hold(3.0)).then(Effect::Despawn(ped)));
            steps.push(Step::new("Везите в больницу", Target::Point(site(Place::Hospital)), 9.0, Need::JobVehicle, Kind::Hold(1.0)));
            title = "Срочный вызов".into();
            reward = 1600;
        }
        JobKind::TrafficPolice | JobKind::Fsb => {
            let mut cands: Vec<(Entity, f32)> = traffic.iter().map(|(e, t)| (e, (xz(t.translation) - xz(from)).length())).filter(|(_, d)| *d > 25.0 && *d < 200.0).collect();
            cands.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
            if let Some(&(car, _)) = cands.first() {
                commands.entity(car).insert(MarkedCar);
                if job == JobKind::TrafficPolice {
                    steps.push(
                        Step::new("Догоните нарушителя и держитесь рядом", Target::Follow(car), 10.0, Need::JobVehicle, Kind::Hold(3.0))
                            .then(Effect::Unmark(car)),
                    );
                    title = "Нарушитель ПДД".into();
                    reward = 1300;
                } else {
                    steps.push(
                        Step::new("Наблюдение: держите дистанцию 10–60 м", Target::Follow(car), 60.0, Need::Any, Kind::Tail { min: 10.0, max: 70.0, secs: 30.0 })
                            .then(Effect::Unmark(car)),
                    );
                    steps.push(Step::new("Доложите в управление", Target::Point(door(Place::Fsb)), 3.0, Need::OnFoot, Kind::Hold(1.0)));
                    title = "Операция «Тень»".into();
                    reward = 2600;
                }
            } else {
                for k in 0..3 {
                    let (_, road) = far_curb(rng, 100.0);
                    steps.push(Step::new(format!("Патрулирование: точка {}", k + 1), Target::Point(road), 9.0, Need::JobVehicle, Kind::Reach));
                }
                title = "Патруль".into();
                reward = 900;
            }
        }
        JobKind::Journalist => {
            let (walk, road) = far_curb(rng, 150.0);
            for k in 0..4 {
                let a = k as f32 * 1.6;
                spawned.push(spawn_person(commands, rng, walk + Vec3::new(a.cos() * 2.5, 0.0, a.sin() * 2.5), false, mats));
            }
            steps.push(Step::new("Происшествие в городе", Target::Point(road), 12.0, Need::Any, Kind::Reach));
            steps.push(Step::new("Снимайте репортаж (пешком)", Target::Point(walk), 10.0, Need::OnFoot, Kind::Hold(4.0)));
            steps.push(Step::new("Сдайте материал в редакцию", Target::Point(door(Place::NewsAgency)), 3.0, Need::OnFoot, Kind::Hold(1.0)));
            title = "Репортаж".into();
            reward = 1500;
        }
        JobKind::Diver => {
            let mut spots = map.dive_spots.clone();
            spots.shuffle(rng);
            for (k, s) in spots.into_iter().take(3).enumerate() {
                let chest = commands
                    .spawn((
                        Mesh3d(shared.cube.clone()),
                        MeshMaterial3d(mats.add(StandardMaterial { base_color: srgb(0xc8a040), emissive: LinearRgba::rgb(3.0, 2.0, 0.4), metallic: 0.8, ..default() })),
                        Transform::from_translation(s).with_scale(Vec3::new(1.2, 0.8, 0.8)),
                    ))
                    .id();
                spawned.push(chest);
                steps.push(Step::new(format!("Поднимите находку {}", k + 1), Target::Point(s), 5.0, Need::Swimming, Kind::Hold(3.0)).then(Effect::Despawn(chest)));
            }
            steps.push(Step::new("Сдайте находки на станции", Target::Point(door(Place::DiveCenter)), 3.0, Need::OnFoot, Kind::Hold(1.0)));
            title = "Погружение".into();
            reward = 2200;
        }
        JobKind::Opg => {
            let (_, road) = far_curb(rng, 250.0);
            steps.push(Step::new("Заберите груз у поставщика", Target::Point(road), 8.0, Need::Any, Kind::Hold(3.0)).then(Effect::Wanted(2)));
            steps.push(Step::new("Уйдите от погони и доставьте груз в гараж", Target::Point(site(Place::OpgGarage)), 9.0, Need::Any, Kind::Hold(2.0)).then(Effect::ClearWanted));
            title = "Дело на окраине".into();
            reward = 4500;
        }
        JobKind::Government => {
            let mut places = vec![Place::Bank, Place::Hospital, Place::TrafficPolice, Place::NewsAgency, Place::FireStation, Place::BusDepot];
            places.shuffle(rng);
            for p in places.into_iter().take(3) {
                steps.push(Step::new(format!("Документы: {}", p.title()), Target::Point(door(p)), 3.0, Need::OnFoot, Kind::Hold(2.0)));
            }
            steps.push(Step::new("Отчёт в мэрии", Target::Point(door(Place::Government)), 3.0, Need::OnFoot, Kind::Hold(1.0)));
            title = "Поручение мэра".into();
            reward = 1800;
        }
        JobKind::Mechanic => {
            let (walk, road) = far_curb(rng, 120.0);
            let _ = walk;
            steps.push(Step::new("Вызов: сломанная машина", Target::Point(road), 9.0, Need::JobVehicle, Kind::Reach));
            steps.push(Step::new("Почините машину (пешком рядом)", Target::Point(road), 5.0, Need::OnFoot, Kind::Hold(5.0)));
            title = "Техпомощь".into();
            reward = 1200;
        }
        JobKind::Garbage => {
            for k in 0..4 {
                let (_, road) = far_curb(rng, 80.0);
                steps.push(Step::new(format!("Заберите мусор: точка {}", k + 1), Target::Point(road), 8.0, Need::JobVehicle, Kind::Hold(2.5)));
            }
            steps.push(Step::new("Выгрузка на базе", Target::Point(site(Place::WasteYard)), 10.0, Need::JobVehicle, Kind::Hold(3.0)));
            title = "Вывоз мусора".into();
            reward = 1400;
        }
    }
    let _ = (BEACH_END, CURB);
    let total = steps.len();
    reward = reward.max(100);
    Mission { title, steps: steps.into(), total, reward, spawned }
}

#[allow(clippy::too_many_arguments)]
fn run_mission(
    mut commands: Commands,
    time: Res<Time>,
    mut jobs: ResMut<JobState>,
    mut state: ResMut<PlayerState>,
    map: Res<CityMap>,
    skins: Res<Skins>,
    shared: Res<SharedMeshes>,
    mut cm: ResMut<ColorMats>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut rng: ResMut<NpcRng>,
    player: Query<&Transform, With<Player>>,
    transforms: Query<&Transform, Without<Player>>,
    traffic: Query<(Entity, &Transform), With<TrafficAi>>,
    mut notes: EventWriter<Notify>,
) {
    let dt = time.delta_secs().min(0.05);
    let Some(job) = jobs.job else { return };
    let Ok(pt) = player.single() else { return };
    let ppos = pt.translation;

    if jobs.mission.is_none() {
        jobs.next_in -= dt;
        if jobs.next_in > 0.0 {
            return;
        }
        let m = new_mission(job, &mut commands, &mut rng.0, &map, ppos, &skins, &shared, &mut cm, &mut mats, &traffic);
        notes.write(Notify::info(format!("Новое задание: {}", m.title)));
        jobs.mission = Some(m);
        jobs.tail_close = 0.0;
        return;
    }

    let in_job_vehicle = state.vehicle.is_some() && state.vehicle == jobs.vehicle;
    let on_foot = state.vehicle.is_none();
    let swimming = state.swimming;
    let mut fail: Option<String> = None;
    let mut finished_step = false;
    {
        let mut tail_close = jobs.tail_close;
        let m = jobs.mission.as_mut().unwrap();
        let Some(step) = m.steps.front_mut() else { return };
        let target = match step.target {
            Target::Point(p) => Some(p),
            Target::Follow(e) => transforms.get(e).ok().map(|t| t.translation),
        };
        match target {
            None => fail = Some("Объект пропал из виду".into()),
            Some(tp) => {
                let dist = (xz(tp) - xz(ppos)).length();
                let need_ok = match step.need {
                    Need::Any => true,
                    Need::JobVehicle => in_job_vehicle,
                    Need::OnFoot => on_foot,
                    Need::Swimming => swimming,
                };
                match step.kind {
                    Kind::Reach => {
                        if dist < step.radius && need_ok {
                            finished_step = true;
                        }
                    }
                    Kind::Hold(secs) => {
                        if dist < step.radius && need_ok {
                            step.progress += dt;
                            if step.progress >= secs {
                                finished_step = true;
                            }
                        } else {
                            step.progress = (step.progress - dt * 0.5).max(0.0);
                        }
                    }
                    Kind::Tail { min, max, secs } => {
                        if dist < min {
                            tail_close += dt;
                            if tail_close > 2.5 {
                                fail = Some("Вас раскрыли — слишком близко".into());
                            }
                        } else {
                            tail_close = (tail_close - dt).max(0.0);
                        }
                        if dist > max * 1.6 && step.progress > 2.0 {
                            fail = Some("Объект потерян".into());
                        }
                        if dist <= max {
                            step.progress += dt;
                            if step.progress >= secs {
                                finished_step = true;
                            }
                        }
                    }
                }
                if !need_ok && dist < step.radius && !matches!(step.kind, Kind::Tail { .. }) {
                    // Hint once in a while handled by the HUD line.
                }
            }
        }
        jobs.tail_close = tail_close;
    }

    if let Some(reason) = fail {
        let m = jobs.mission.take().unwrap();
        for e in m.spawned {
            commands.entity(e).try_despawn();
        }
        for s in m.steps {
            for eff in s.effects {
                if let Effect::Unmark(e) = eff {
                    if let Ok(mut ec) = commands.get_entity(e) {
                        ec.remove::<MarkedCar>();
                    }
                }
            }
        }
        jobs.wanted = 0;
        jobs.next_in = 4.0;
        notes.write(Notify::warn(format!("Задание провалено: {reason}")));
        return;
    }

    if finished_step {
        let m = jobs.mission.as_mut().unwrap();
        let step = m.steps.pop_front().unwrap();
        for eff in step.effects {
            match eff {
                Effect::Despawn(e) => {
                    commands.entity(e).try_despawn();
                }
                Effect::Unmark(e) => {
                    if let Ok(mut ec) = commands.get_entity(e) {
                        ec.remove::<MarkedCar>();
                    }
                }
                Effect::Wanted(n) => {
                    jobs_wanted_set(&mut notes, n);
                    jobs.wanted = n;
                }
                Effect::ClearWanted => jobs.wanted = 0,
            }
        }
        let m = jobs.mission.as_ref().unwrap();
        if m.steps.is_empty() {
            let m = jobs.mission.take().unwrap();
            for e in m.spawned {
                commands.entity(e).try_despawn();
            }
            let xp = jobs.xp.entry(job).or_insert(0);
            let before = rank_of(*xp);
            *xp += 1;
            let after = rank_of(*xp);
            let pay = (m.reward as f32 * (1.0 + 0.25 * before as f32)) as i64;
            state.money += pay;
            jobs.shift_earned += pay;
            notes.write(Notify::money(format!("+{pay} ₽ · {}", m.title)));
            if after > before {
                notes.write(Notify::good(format!("Повышение! Новый ранг: {}", job.ranks()[after])));
            }
            jobs.next_in = 3.0;
        } else {
            notes.write(Notify::info(m.steps.front().unwrap().label.clone()));
        }
    }
}

fn jobs_wanted_set(notes: &mut EventWriter<Notify>, n: u8) {
    notes.write(Notify::warn(format!("Розыск: {}", "• ".repeat(n as usize))));
}

#[allow(clippy::too_many_arguments)]
fn wanted_level(
    mut commands: Commands,
    mut jobs: ResMut<JobState>,
    mut state: ResMut<PlayerState>,
    mut rng: ResMut<NpcRng>,
    catalog: Res<Catalog>,
    shared: Res<SharedMeshes>,
    mut va: ResMut<VehicleAssets>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    player: Query<&Transform, With<Player>>,
    cops: Query<(Entity, &Pursuer, &Transform)>,
    mut notes: EventWriter<Notify>,
) {
    let Ok(pt) = player.single() else { return };
    let want = jobs.wanted as usize;
    let count = cops.iter().count();
    if want == 0 {
        for (e, _, _) in &cops {
            commands.entity(e).despawn();
        }
        return;
    }
    let busted = cops.iter().any(|(_, p, _)| p.close_time > 3.5);
    if busted {
        let fine = 2000.min(state.money.max(0));
        state.money -= fine;
        jobs.wanted = 0;
        if let Some(m) = jobs.mission.take() {
            for e in m.spawned {
                commands.entity(e).try_despawn();
            }
        }
        jobs.next_in = 5.0;
        notes.write(Notify::warn(format!("Вас задержали! Штраф {fine} ₽, груз конфискован")));
        return;
    }
    for (e, _, t) in &cops {
        if (t.translation - pt.translation).length() > 400.0 {
            commands.entity(e).despawn();
        }
    }
    if count < want {
        let a: f32 = rng.0.gen_range(0.0..std::f32::consts::TAU);
        let p = xz(pt.translation) + Vec2::new(a.cos(), a.sin()) * 90.0;
        let p = Vec2::new(p.x.clamp(-HALF, HALF), p.y.clamp(-HALF, HALF));
        let spec = catalog.first_of(BodyClass::Sedan) + 7;
        let e = spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, spec, 0, Livery::Police, Vec3::new(p.x, 0.0, p.y), 0.0);
        commands.entity(e).insert(Pursuer { close_time: 0.0 });
    }
    let _ = Driven;
}

fn move_marker(
    jobs: Res<JobState>,
    transforms: Query<&Transform, Without<MissionMarker>>,
    mut marker: Query<(&mut Transform, &mut Visibility), With<MissionMarker>>,
) {
    let Ok((mut t, mut vis)) = marker.single_mut() else { return };
    let pos = match jobs.target() {
        Some(Target2::Point(p)) => Some(p),
        Some(Target2::Entity(e)) => transforms.get(e).ok().map(|t| t.translation),
        None => None,
    };
    match pos {
        Some(p) => {
            t.translation = Vec3::new(p.x, p.y.max(-5.5), p.z);
            *vis = Visibility::Inherited;
        }
        None => *vis = Visibility::Hidden,
    }
}

fn flicker_flames(time: Res<Time>, mut q: Query<&mut Transform, With<Flame>>) {
    let t = time.elapsed_secs();
    for (i, mut tr) in q.iter_mut().enumerate() {
        let s = 2.2 + (t * 9.0 + i as f32 * 1.3).sin() * 0.5 + (t * 23.0 + i as f32).sin() * 0.2;
        tr.scale = Vec3::new(s, s * 1.6, s);
    }
}
