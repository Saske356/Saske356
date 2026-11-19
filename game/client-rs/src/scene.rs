//! Мир на экране: свет и небо, карта из кэша (cache/brmap) или наш город, камера.

use bevy::gltf::{Gltf, GltfMesh};
use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::pbr::{CascadeShadowConfigBuilder, DistanceFog, FogFalloff};
use bevy::prelude::*;
use bevy::render::mesh::{Indices, VertexAttributeValues};
use novo_world as world;

use crate::state::{lerp_angle, Collider, Game, Launch, MapGrid};

#[derive(Component)]
pub struct MainCamera;
#[derive(Component)]
pub struct Sun;
#[derive(Resource)]
pub struct MapAsset(pub Handle<Gltf>);
/// Материалы окон нашего города — ночью светятся.
#[derive(Resource, Default)]
pub struct NightMats(pub Vec<Handle<StandardMaterial>>);

pub fn setup(
    mut commands: Commands,
    launch: Res<Launch>,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
) {
    commands.spawn((
        Camera3d::default(),
        Transform::from_xyz(300.0, 40.0, 300.0).looking_at(Vec3::new(328.0, 0.0, 328.0), Vec3::Y),
        DistanceFog { color: Color::srgb(0.62, 0.76, 0.88), falloff: FogFalloff::Linear { start: 160.0, end: 620.0 }, ..default() },
        MainCamera,
    ));
    commands.spawn((
        DirectionalLight { illuminance: 9000.0, shadows_enabled: launch.quality_shadows, ..default() },
        Transform::from_xyz(150.0, 250.0, 80.0).looking_at(Vec3::ZERO, Vec3::Y),
        CascadeShadowConfigBuilder { num_cascades: 2, maximum_distance: 140.0, first_cascade_far_bound: 40.0, ..default() }.build(),
        Sun,
    ));
    commands.insert_resource(AmbientLight { color: Color::srgb(0.85, 0.9, 1.0), brightness: 900.0, ..default() });

    let map_path = launch.map.as_ref().map(|m| format!("cache/brmap/{m}.glb"));
    if let Some(p) = map_path.filter(|p| launch.game_dir.join(p).exists()) {
        // внешняя карта: сцена + сетка столкновений (строится, когда файл загрузится)
        commands.spawn(SceneRoot(assets.load(GltfAssetLabel::Scene(0).from_asset(p.clone()))));
        commands.insert_resource(MapAsset(assets.load(p)));
        commands.insert_resource(Collider::Loading);
        commands.spawn((Mesh3d(meshes.add(Plane3d::default().mesh().size(4000.0, 4000.0))),
            MeshMaterial3d(mats.add(StandardMaterial { base_color: Color::srgb(0.3, 0.42, 0.25), perceptual_roughness: 1.0, ..default() })),
            Transform::from_xyz(328.0, -0.3, 328.0)));
    } else {
        let night = build_city(&mut commands, &mut meshes, &mut mats);
        commands.insert_resource(night);
        commands.insert_resource(Collider::City(world::generate_city().boxes));
    }
}

/// Наш город из генератора world-rs (тот же, что в JS-клиенте и на сервере).
fn build_city(commands: &mut Commands, meshes: &mut Assets<Mesh>, mats: &mut Assets<StandardMaterial>) -> NightMats {
    let city = world::generate_city();
    let s = world::SIZE as f32;
    let mat = |mats: &mut Assets<StandardMaterial>, c: Color, r: f32| mats.add(StandardMaterial { base_color: c, perceptual_roughness: r, ..default() });
    commands.spawn((Mesh3d(meshes.add(Plane3d::default().mesh().size(4000.0, 4000.0))), MeshMaterial3d(mat(mats, Color::srgb(0.3, 0.45, 0.22), 1.0)),
        Transform::from_xyz(s / 2.0, -0.06, s / 2.0)));
    commands.spawn((Mesh3d(meshes.add(Plane3d::default().mesh().size(s, s))), MeshMaterial3d(mat(mats, Color::srgb(0.23, 0.24, 0.26), 0.9)),
        Transform::from_xyz(s / 2.0, 0.0, s / 2.0)));
    let walk = meshes.add(Cuboid::new(world::BLOCK as f32, world::CURB as f32, world::BLOCK as f32));
    let walk_m = mat(mats, Color::srgb(0.6, 0.61, 0.62), 0.9);
    let park_m = mat(mats, Color::srgb(0.36, 0.54, 0.25), 1.0);
    for bz in 0..world::GRID {
        for bx in 0..world::GRID {
            let b = world::block_rect(bx, bz);
            commands.spawn((Mesh3d(walk.clone()), MeshMaterial3d(walk_m.clone()),
                Transform::from_xyz(b.x0 as f32 + 32.0, world::CURB as f32 / 2.0, b.z0 as f32 + 32.0)));
        }
    }
    for p in &city.parks {
        commands.spawn((Mesh3d(meshes.add(Plane3d::default().mesh().size(56.0, 56.0))), MeshMaterial3d(park_m.clone()),
            Transform::from_xyz(p.x0 as f32 + 32.0, world::CURB as f32 + 0.02, p.z0 as f32 + 32.0)));
    }
    let mut night = NightMats::default();
    let mut by_color = std::collections::HashMap::new();
    for b in &city.buildings {
        let (w, d, h) = ((b.r.x1 - b.r.x0) as f32, (b.r.z1 - b.r.z0) as f32, b.h as f32);
        let m = by_color.entry(b.color).or_insert_with(|| {
            let h = mats.add(StandardMaterial { base_color: crate::state::hex_color(b.color), perceptual_roughness: 0.85, emissive: LinearRgba::BLACK, ..default() });
            night.0.push(h.clone());
            h
        }).clone();
        commands.spawn((Mesh3d(meshes.add(Cuboid::new(w, h, d))), MeshMaterial3d(m),
            Transform::from_xyz(b.r.x0 as f32 + w / 2.0, world::CURB as f32 + h / 2.0, b.r.z0 as f32 + d / 2.0)));
    }
    let trunk = meshes.add(Cylinder::new(0.18, 2.2));
    let crown = meshes.add(Sphere::new(1.5).mesh().ico(1).unwrap());
    let trunk_m = mat(mats, Color::srgb(0.42, 0.29, 0.18), 1.0);
    let crown_m = mat(mats, Color::srgb(0.25, 0.49, 0.2), 1.0);
    for t in &city.trees {
        let (x, z) = (t[0] as f32, t[1] as f32);
        let y = world::ground_height(t[0], t[1]) as f32;
        commands.spawn((Mesh3d(trunk.clone()), MeshMaterial3d(trunk_m.clone()), Transform::from_xyz(x, y + 1.1, z)));
        commands.spawn((Mesh3d(crown.clone()), MeshMaterial3d(crown_m.clone()), Transform::from_xyz(x, y + 3.1, z)));
    }
    night
}

/// Когда карта загрузилась — собираем треугольники для высоты земли и стен.
pub fn build_map_collider(
    mut commands: Commands,
    map: Option<Res<MapAsset>>,
    collider: Res<Collider>,
    gltfs: Res<Assets<Gltf>>,
    gmeshes: Res<Assets<GltfMesh>>,
    meshes: Res<Assets<Mesh>>,
    mats: Res<Assets<StandardMaterial>>,
    mut game: ResMut<Game>,
) {
    if !matches!(*collider, Collider::Loading) {
        return;
    }
    let Some(map) = map else { return };
    let Some(gltf) = gltfs.get(&map.0) else { return };
    let mut tris = Vec::new();
    for gm in &gltf.meshes {
        let Some(gm) = gmeshes.get(gm) else { return };
        for p in &gm.primitives {
            // листва и провода (прозрачные) ходьбе не мешают
            if let Some(m) = p.material.as_ref().and_then(|h| mats.get(h)) {
                if !matches!(m.alpha_mode, AlphaMode::Opaque) {
                    continue;
                }
            }
            let Some(mesh) = meshes.get(&p.mesh) else { return };
            let Some(VertexAttributeValues::Float32x3(pos)) = mesh.attribute(Mesh::ATTRIBUTE_POSITION) else { continue };
            let idx: Vec<usize> = match mesh.indices() {
                Some(Indices::U16(v)) => v.iter().map(|&i| i as usize).collect(),
                Some(Indices::U32(v)) => v.iter().map(|&i| i as usize).collect(),
                None => (0..pos.len()).collect(),
            };
            for t in idx.chunks_exact(3) {
                let (a, b, c) = (pos[t[0]], pos[t[1]], pos[t[2]]);
                tris.push([a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]]);
            }
        }
    }
    let grid = MapGrid::new(tris);
    info!("карта: {} треугольников для столкновений", grid.triangles());
    // спавн: ближайшая к центру точка на земле без препятствий
    'search: for r in (0..200).step_by(4) {
        for k in 0..16 {
            let a = k as f32 / 16.0 * std::f32::consts::TAU;
            let (x, z) = (328.0 + a.cos() * r as f32, 328.0 + a.sin() * r as f32);
            if let Some(g) = grid.lowest(x, z) {
                if !grid.blocked(x, z, g, 1.2) {
                    game.pos = Vec3::new(x, g, z);
                    break 'search;
                }
            }
        }
    }
    commands.insert_resource(Collider::Map(grid));
}

/// День и ночь по игровому времени сервера.
pub fn update_sky(
    game: Res<Game>,
    mut sun: Query<(&mut DirectionalLight, &mut Transform), With<Sun>>,
    mut ambient: ResMut<AmbientLight>,
    mut clear: ResMut<ClearColor>,
    mut fog: Query<&mut DistanceFog, With<MainCamera>>,
    night: Option<Res<NightMats>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
) {
    let t = game.time / 1440.0;
    let ang = (t - 0.25) * std::f32::consts::TAU;
    let elev = ang.sin();
    let day = ((elev + 0.12) / 0.42).clamp(0.0, 1.0);
    let day = day * day * (3.0 - 2.0 * day);
    let dusk = (1.0 - elev.abs() / 0.25).max(0.0) * 0.6 * day;
    let sky_day = Vec3::new(0.56, 0.76, 0.92);
    let sky_night = Vec3::new(0.04, 0.07, 0.14);
    let sky_dusk = Vec3::new(0.88, 0.54, 0.35);
    let c = sky_night.lerp(sky_day, day).lerp(sky_dusk, dusk);
    let col = Color::srgb(c.x, c.y, c.z);
    clear.0 = col;
    if let Ok(mut f) = fog.single_mut() {
        f.color = col;
    }
    if let Ok((mut l, mut tr)) = sun.single_mut() {
        l.illuminance = 400.0 + 9600.0 * day;
        let p = game.pos + Vec3::new(ang.cos() * 150.0, elev.max(0.25) * 220.0, 70.0);
        *tr = Transform::from_translation(p).looking_at(game.pos, Vec3::Y);
    }
    ambient.brightness = 180.0 + 900.0 * day;
    if let Some(n) = night {
        let glow = (1.0 - day) * 0.6;
        for h in &n.0 {
            if let Some(m) = mats.get_mut(h) {
                let base = m.base_color.to_linear();
                m.emissive = LinearRgba::rgb(base.red * glow + 0.25 * glow, base.green * glow + 0.18 * glow, base.blue * glow * 0.5);
            }
        }
    }
}

/// Камера за игроком: мышь (зажать ЛКМ/ПКМ) — поворот, колесо — зум; в машине сама встаёт сзади.
pub fn update_camera(
    time: Res<Time>,
    motion: Res<AccumulatedMouseMotion>,
    scroll: Res<AccumulatedMouseScroll>,
    buttons: Res<ButtonInput<MouseButton>>,
    mut game: ResMut<Game>,
    mut cam: Query<&mut Transform, With<MainCamera>>,
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
    if buttons.pressed(MouseButton::Left) || buttons.pressed(MouseButton::Right) {
        if motion.delta != Vec2::ZERO {
            game.last_drag = now;
        }
        game.cam_yaw -= motion.delta.x * 0.006;
        game.cam_pitch = (game.cam_pitch + motion.delta.y * 0.004).clamp(-0.05, 1.25);
    }
    game.cam_dist = (game.cam_dist + scroll.delta.y * -0.8).clamp(3.0, 18.0);
    let mut target = game.pos + Vec3::Y * 1.6;
    let mut dist = game.cam_dist;
    if let Some(car) = game.car.clone() {
        let c = world::car(&car.model).unwrap_or(&world::CARS[0]);
        target = game.pos + Vec3::Y * (c.hgt as f32 + 0.4);
        dist = game.cam_dist + c.len as f32 * 0.9;
        if now - game.last_drag > 1.5 && car.spd.abs() > 1.0 {
            game.cam_yaw = lerp_angle(game.cam_yaw, car.ry, 1.0 - (-dt * 2.5).exp());
        }
    }
    let (cp, sp) = (game.cam_pitch.cos(), game.cam_pitch.sin());
    let f = Vec3::new(game.cam_yaw.sin(), 0.0, game.cam_yaw.cos());
    let mut p = target - f * dist * cp + Vec3::Y * dist * sp;
    p.y = p.y.max(target.y - 1.0).max(0.6);
    if let Ok(mut t) = cam.single_mut() {
        *t = Transform::from_translation(p).looking_at(target, Vec3::Y);
    }
}
