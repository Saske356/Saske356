//! Модели: персонаж из простых фигур и машины из cache/cars/*.glb (с перекраской и колёсами).

use std::collections::HashMap;

use bevy::gltf::Gltf;
use bevy::prelude::*;
use novo_world as world;

use crate::state::{hex_color, Launch};

/// Сведения о моделях машин из cache/cars/cars.json.
#[derive(Clone, Copy, Default)]
pub struct CarInfo {
    pub len: f32,
    pub bottom: f32,
    pub wheel: f32,
}

#[derive(Resource, Default)]
pub struct CarAssets {
    pub info: HashMap<String, CarInfo>,
    pub gltf: HashMap<String, Handle<Gltf>>,
    pub paint: HashMap<(AssetId<StandardMaterial>, u32), Handle<StandardMaterial>>,
}

/// Модель по умолчанию для класса машины (как SKINS в JS).
pub fn default_skin(model: &str) -> &'static str {
    match model {
        "kroha" => "granta",
        "vektor" => "vesta",
        "taiga" => "patriota",
        "bars" => "bmwmkf",
        "bus" => "bus",
        _ => "granta",
    }
}

pub fn load_car_index(launch: &Launch) -> HashMap<String, CarInfo> {
    let mut out = HashMap::new();
    let Ok(text) = std::fs::read_to_string(launch.game_dir.join("cache/cars/cars.json")) else { return out };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else { return out };
    if let Some(obj) = v.as_object() {
        for (k, i) in obj {
            let f = |n: &str| i.get(n).and_then(|x| x.as_f64()).unwrap_or(0.0) as f32;
            out.insert(k.clone(), CarInfo { len: f("len"), bottom: f("bottom"), wheel: f("wheel") });
        }
    }
    out
}

/// Корень машины: модель ещё может грузиться — тогда настройка (краска, колёса) произойдёт позже.
#[derive(Component)]
pub struct CarModel {
    pub skin: Option<String>,
    pub color: u32,
    pub ready: bool,
    pub wheels: Vec<(Entity, Quat)>,
    pub wheel_r: f32,
    pub spin: f32,
}

/// Создаёт машину: детальная модель из кэша, если есть, иначе коробка.
pub fn spawn_car(
    commands: &mut Commands,
    cars: &mut CarAssets,
    assets: &AssetServer,
    meshes: &mut Assets<Mesh>,
    mats: &mut Assets<StandardMaterial>,
    model: &str,
    skin: Option<&str>,
    color: u32,
    pos: Vec3,
    ry: f32,
) -> Entity {
    let class = world::car(model).unwrap_or(&world::CARS[0]);
    let skin = skin.map(String::from).unwrap_or_else(|| default_skin(model).to_string());
    let root = commands
        .spawn((Transform::from_translation(pos).with_rotation(Quat::from_rotation_y(ry)), Visibility::default()))
        .id();
    if let Some(info) = cars.info.get(&skin).copied().filter(|i| i.len > 0.1) {
        let h = cars.gltf.entry(skin.clone()).or_insert_with(|| assets.load(format!("cache/cars/{skin}.glb"))).clone();
        let k = class.len as f32 / info.len;
        let scene = assets.load(GltfAssetLabel::Scene(0).from_asset(format!("cache/cars/{skin}.glb")));
        let child = commands
            .spawn((SceneRoot(scene), Transform::from_xyz(0.0, -info.bottom * k, 0.0).with_scale(Vec3::splat(k))))
            .id();
        let _ = h;
        commands.entity(root).add_child(child);
        commands.entity(root).insert(CarModel { skin: Some(skin), color, ready: false, wheels: vec![], wheel_r: info.wheel * k, spin: 0.0 });
    } else {
        // коробка: кузов + кабина
        let (l, w, h) = (class.len as f32, class.wid as f32, class.hgt as f32);
        let paint = mats.add(StandardMaterial { base_color: hex_color(color), perceptual_roughness: 0.4, metallic: 0.3, ..default() });
        let glass = mats.add(StandardMaterial { base_color: Color::srgb(0.1, 0.13, 0.17), perceptual_roughness: 0.1, ..default() });
        let body = commands.spawn((Mesh3d(meshes.add(Cuboid::new(w, h * 0.47, l))), MeshMaterial3d(paint.clone()),
            Transform::from_xyz(0.0, 0.3 + h * 0.235, 0.0))).id();
        let cab = commands.spawn((Mesh3d(meshes.add(Cuboid::new(w * 0.86, h * 0.45, l * 0.5))), MeshMaterial3d(glass),
            Transform::from_xyz(0.0, 0.3 + h * 0.47 + h * 0.2, -0.15))).id();
        commands.entity(root).add_children(&[body, cab]);
        commands.entity(root).insert(CarModel { skin: None, color, ready: true, wheels: vec![], wheel_r: 0.35, spin: 0.0 });
    }
    root
}

/// Когда сцена машины загрузилась: перекрашиваем кузов (материалы paint1/paint2) и находим колёса.
pub fn setup_car_models(
    mut cars_q: Query<(Entity, &mut CarModel)>,
    children: Query<&Children>,
    names: Query<&Name>,
    mut mat_q: Query<&mut MeshMaterial3d<StandardMaterial>>,
    transforms: Query<&Transform, Without<CarModel>>,
    mut cars: ResMut<CarAssets>,
    gltfs: Res<Assets<Gltf>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
) {
    for (e, mut car) in &mut cars_q {
        if car.ready {
            continue;
        }
        let Some(skin) = car.skin.clone() else { car.ready = true; continue };
        let Some(gltf) = cars.gltf.get(&skin).and_then(|h| gltfs.get(h)) else { continue };
        let paint: Vec<AssetId<StandardMaterial>> = ["paint1", "paint2"].iter()
            .filter_map(|n| gltf.named_materials.get(*n).map(|h| h.id())).collect();
        let desc: Vec<Entity> = children.iter_descendants(e).collect();
        if !desc.iter().any(|d| mat_q.get(*d).is_ok()) {
            continue; // сцена ещё не развернулась
        }
        let color = car.color;
        for d in &desc {
            if let Ok(mut m) = mat_q.get_mut(*d) {
                let id = m.0.id();
                if paint.contains(&id) {
                    let h = cars.paint.entry((id, color)).or_insert_with(|| {
                        let mut base = mats.get(id).cloned().unwrap_or_default();
                        base.base_color = hex_color(color);
                        mats.add(base)
                    }).clone();
                    m.0 = h;
                }
            }
            if let Ok(n) = names.get(*d) {
                if n.as_str().starts_with("wheel_") {
                    let base = transforms.get(*d).map(|t| t.rotation).unwrap_or_default();
                    car.wheels.push((*d, base));
                }
            }
        }
        car.ready = true;
    }
}

/// Персонаж: торс, голова, ноги и руки на шарнирах (для анимации ходьбы).
#[derive(Component)]
pub struct PedRig {
    pub legs: [Entity; 2],
    pub arms: [Entity; 2],
    pub phase: f32,
}

pub fn spawn_ped(commands: &mut Commands, meshes: &mut Assets<Mesh>, mats: &mut Assets<StandardMaterial>, shirt: Color, pos: Vec3) -> Entity {
    let skin = mats.add(StandardMaterial { base_color: Color::srgb_u8(224, 180, 140), perceptual_roughness: 0.8, ..default() });
    let shirt = mats.add(StandardMaterial { base_color: shirt, perceptual_roughness: 0.9, ..default() });
    let pants = mats.add(StandardMaterial { base_color: Color::srgb_u8(43, 58, 85), perceptual_roughness: 0.9, ..default() });
    let hair = mats.add(StandardMaterial { base_color: Color::srgb_u8(42, 28, 18), ..default() });
    let leg = meshes.add(Cuboid::new(0.22, 0.86, 0.24));
    let arm = meshes.add(Cuboid::new(0.16, 0.64, 0.18));
    let root = commands.spawn((Transform::from_translation(pos), Visibility::default())).id();
    let mut limb = |m: Handle<Mesh>, mat: Handle<StandardMaterial>, at: Vec3, len: f32| {
        // шарнир на верхнем конце: сама деталь опущена на половину длины
        let pivot = commands.spawn((Transform::from_translation(at), Visibility::default())).id();
        let part = commands.spawn((Mesh3d(m), MeshMaterial3d(mat), Transform::from_xyz(0.0, -len / 2.0, 0.0))).id();
        commands.entity(pivot).add_child(part);
        pivot
    };
    let l0 = limb(leg.clone(), pants.clone(), Vec3::new(-0.13, 0.9, 0.0), 0.86);
    let l1 = limb(leg, pants, Vec3::new(0.13, 0.9, 0.0), 0.86);
    let a0 = limb(arm.clone(), shirt.clone(), Vec3::new(-0.37, 1.52, 0.0), 0.64);
    let a1 = limb(arm, shirt.clone(), Vec3::new(0.37, 1.52, 0.0), 0.64);
    let torso = commands.spawn((Mesh3d(meshes.add(Cuboid::new(0.56, 0.66, 0.3))), MeshMaterial3d(shirt), Transform::from_xyz(0.0, 1.23, 0.0))).id();
    let head = commands.spawn((Mesh3d(meshes.add(Cuboid::new(0.3, 0.32, 0.3))), MeshMaterial3d(skin), Transform::from_xyz(0.0, 1.75, 0.0))).id();
    let hairc = commands.spawn((Mesh3d(meshes.add(Cuboid::new(0.32, 0.1, 0.32))), MeshMaterial3d(hair), Transform::from_xyz(0.0, 1.93, 0.0))).id();
    commands.entity(root).add_children(&[l0, l1, a0, a1, torso, head, hairc]);
    commands.entity(root).insert(PedRig { legs: [l0, l1], arms: [a0, a1], phase: 0.0 });
    root
}

/// Анимация ходьбы: anim 0 — стоит, 1 — идёт, 2 — бежит.
pub fn animate_ped(rig: &mut PedRig, anim: i64, dt: f32, tq: &mut Query<&mut Transform, Without<PedRig>>) {
    let a = if anim > 0 {
        rig.phase += dt * if anim == 2 { 12.0 } else { 8.0 };
        rig.phase.sin() * if anim == 2 { 0.9 } else { 0.55 }
    } else {
        rig.phase = 0.0;
        0.0
    };
    let k = 1.0 - (-dt * 15.0).exp();
    let set = |e: Entity, target: f32, tq: &mut Query<&mut Transform, Without<PedRig>>| {
        if let Ok(mut t) = tq.get_mut(e) {
            let (cur, _, _) = t.rotation.to_euler(EulerRot::XYZ);
            t.rotation = Quat::from_rotation_x(cur + (target - cur) * k);
        }
    };
    set(rig.legs[0], a, tq);
    set(rig.legs[1], -a, tq);
    set(rig.arms[0], -a * 0.8, tq);
    set(rig.arms[1], a * 0.8, tq);
}
