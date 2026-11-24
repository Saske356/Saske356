//! Solara City — an original open-world sunset city with detailed cars.
//! Rust + Bevy, everything (geometry, textures, sky) generated in code.
mod camera;
mod car;
mod city;
mod hud;
mod mats;
mod mesh;
mod people;
mod player;
mod traffic;
mod util;

use bevy::core_pipeline::bloom::Bloom;
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::diagnostic::FrameTimeDiagnosticsPlugin;
use bevy::pbr::{CascadeShadowConfigBuilder, DirectionalLightShadowMap, DistanceFog, FogFalloff};
use bevy::prelude::*;

use crate::mats::SUN_DIR;
use crate::people::{Look, Pose};
use crate::util::*;

fn main() {
    App::new()
        .insert_resource(ClearColor(Color::srgb(0.55, 0.42, 0.45)))
        .insert_resource(DirectionalLightShadowMap { size: 2048 })
        .insert_resource(AmbientLight { color: Color::srgb(0.8, 0.78, 0.9), brightness: 90.0, ..default() })
        .add_plugins((
            DefaultPlugins.set(WindowPlugin {
                primary_window: Some(Window {
                    title: "Solara City".into(),
                    canvas: Some("#game".into()),
                    fit_canvas_to_parent: true,
                    prevent_default_event_handling: true,
                    ..default()
                }),
                ..default()
            }),
            FrameTimeDiagnosticsPlugin::default(),
        ))
        .init_resource::<player::Game>()
        .init_resource::<camera::Rig>()
        .init_resource::<traffic::Lights>()
        .add_systems(Startup, setup)
        .add_systems(
            Update,
            (
                camera::camera_input,
                player::player_control,
                car::drive_player_car,
                traffic::drive_ai,
                traffic::update_lights,
                people::move_peds,
                car::animate_cars,
                people::animate_humans,
                camera::camera_follow,
                hud::update_hud,
            )
                .chain(),
        )
        .run();
}

#[allow(clippy::too_many_arguments)]
fn setup(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
    mut fonts: ResMut<Assets<Font>>,
    mut game: ResMut<player::Game>,
) {
    let mut rng = Rng::new(20261124);
    let mats = mats::build_mats(&mut materials, &mut images);
    let people_assets = people::build_people_assets(&mut meshes);
    let model = car::build_car_model(&mut meshes);

    let out = city::build_city(&mut commands, &mut meshes, &mats, &mut rng);

    // the player's red car on the showroom turntable
    let (cpos, cyaw) = out.start_car;
    let my_car = car::spawn_car(
        &mut commands,
        &model,
        &mats,
        &mut materials,
        &people_assets,
        Color::srgb_u8(205, 14, 18),
        cpos,
        cyaw,
        None,
    );
    commands.entity(my_car).insert(Transform::from_xyz(cpos.x, CURB + 0.14, cpos.y).with_rotation(Quat::from_rotation_y(cyaw)));
    game.start_car = Some(my_car);

    // traffic
    for (ai, pos, yaw) in traffic::spawn_points(&mut rng, 30) {
        let color = mats::random_paint(&mut rng);
        let look = Look::random(&mut rng);
        let e = car::spawn_car(&mut commands, &model, &mats, &mut materials, &people_assets, color, pos, yaw, Some(look));
        commands.entity(e).insert(ai);
    }
    // a few parked cars along the coast
    for k in 0..4 {
        let color = mats::random_paint(&mut rng);
        let p = Vec2::new(city_max() + ROAD * 0.5 + 3.5, 40.0 + k as f32 * 70.0);
        let e = car::spawn_car(&mut commands, &model, &mats, &mut materials, &people_assets, color, p, 0.0, None);
        commands.entity(e).insert(Transform::from_xyz(p.x, CURB, p.y));
    }

    people::spawn_peds(&mut commands, &people_assets, &mats, &mut rng, 70);

    // player starts next to the driver's door of the red car
    let _ = out.start_player;
    let sp = cpos - yaw_right(cyaw) * 2.4 + yaw_fwd(cyaw) * 0.3;
    let pl = people::spawn_human(
        &mut commands,
        &people_assets,
        &mats,
        Look { skin: 1, shirt: 0, pants: 0, hair: 0 },
        Transform::from_xyz(sp.x, CURB, sp.y).with_rotation(Quat::from_rotation_y(cyaw - std::f32::consts::FRAC_PI_2)),
        Pose::Walk,
        None,
    );
    commands.entity(pl).insert(player::Player { vy: 0.0, grounded: true });

    // sun
    commands.spawn((
        DirectionalLight {
            color: Color::srgb(1.0, 0.76, 0.52),
            illuminance: 9_000.0,
            shadows_enabled: true,
            ..default()
        },
        Transform::from_translation(SUN_DIR * 100.0).looking_at(Vec3::ZERO, Vec3::Y),
        CascadeShadowConfigBuilder {
            num_cascades: 1,
            minimum_distance: 0.1,
            first_cascade_far_bound: 110.0,
            maximum_distance: 110.0,
            overlap_proportion: 0.2,
        }
        .build(),
    ));

    // camera
    commands.spawn((
        Camera3d::default(),
        Camera { hdr: true, ..default() },
        Tonemapping::AcesFitted,
        Bloom { intensity: 0.12, ..Bloom::NATURAL },
        Projection::Perspective(PerspectiveProjection { fov: 62f32.to_radians(), near: 0.05, far: 8000.0, ..default() }),
        DistanceFog {
            color: Color::srgba(0.86, 0.6, 0.52, 1.0),
            directional_light_color: Color::srgba(1.0, 0.72, 0.42, 0.55),
            directional_light_exponent: 16.0,
            falloff: FogFalloff::Exponential { density: 0.0012 },
        },
        EnvironmentMapLight {
            diffuse_map: mats.env_diffuse.clone(),
            specular_map: mats.env_specular.clone(),
            intensity: 1400.0,
            rotation: Quat::IDENTITY,
            affects_lightmapped_mesh_diffuse: true,
        },
        Transform::from_xyz(cpos.x + 6.0, 2.0, cpos.y + 6.0).looking_at(Vec3::new(cpos.x, 0.7, cpos.y), Vec3::Y),
    ));

    let font = fonts.add(Font::try_from_bytes(include_bytes!("../assets/fonts/DejaVuSans-Bold.ttf").to_vec()).expect("font"));
    hud::spawn_hud(&mut commands, font);

    commands.insert_resource(out.colliders);
    commands.insert_resource(model);
    commands.insert_resource(people_assets);
    commands.insert_resource(mats);
}
