//! Automated screenshots for development: `SVETLY_SHOT=out.png` renders a
//! scene (`SVETLY_SCENE`, `SVETLY_HOUR`) and quits.

use bevy::prelude::*;
use bevy::render::view::screenshot::{save_to_disk, Screenshot};

use crate::city::{CityMap, Place, SharedMeshes};
use crate::jobs::{JobCommand, JobKind};
use crate::menu::{Tab, UiState};
use crate::player::PlayerState;
use crate::scene::{CameraRig, Clock};
use crate::vehicles::{spawn_vehicle, BodyClass, Catalog, Driven, Livery, VehicleAssets};

pub struct DebugPlugin;

impl Plugin for DebugPlugin {
    fn build(&self, app: &mut App) {
        if std::env::var("SVETLY_SHOT").is_ok() {
            app.add_systems(Update, shot);
        }
    }
}

fn env_f(name: &str, d: f32) -> f32 {
    std::env::var(name).ok().and_then(|v| v.parse().ok()).unwrap_or(d)
}

#[allow(clippy::too_many_arguments)]
fn shot(
    mut commands: Commands,
    mut frame: Local<u32>,
    mut clock: ResMut<Clock>,
    mut rig: ResMut<CameraRig>,
    mut ui: ResMut<UiState>,
    mut state: ResMut<PlayerState>,
    mut jobs: EventWriter<JobCommand>,
    map: Res<CityMap>,
    catalog: Res<Catalog>,
    shared: Res<SharedMeshes>,
    mut va: ResMut<VehicleAssets>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut player: Query<&mut Transform, With<crate::player::Player>>,
    mut vis: Query<&mut Visibility, With<crate::player::Player>>,
    mut exit: EventWriter<AppExit>,
) {
    *frame += 1;
    let scene = std::env::var("SVETLY_SCENE").unwrap_or_default();
    let frames = env_f("SVETLY_FRAMES", 90.0) as u32;
    if *frame == 2 {
        clock.hours = env_f("SVETLY_HOUR", 16.5);
        clock.speed = 0.0;
        rig.yaw = env_f("SVETLY_YAW", 0.6);
        rig.pitch = env_f("SVETLY_PITCH", 0.3);
        rig.dist = env_f("SVETLY_DIST", 7.5);
        match scene.as_str() {
            "drive" | "cars" => {
                let site = &map.sites[&Place::Government];
                let n = if scene == "cars" { 6 } else { 1 };
                for k in 0..n {
                    let class = [BodyClass::Sport, BodyClass::Suv, BodyClass::Sedan, BodyClass::Pickup, BodyClass::Hatch, BodyClass::Coupe][k];
                    let spec = catalog.first_of(class) + k * 3;
                    let p = site.curb + Vec3::new(-18.0 + k as f32 * 7.0, 0.0, 0.0);
                    let e = spawn_vehicle(&mut commands, &mut va, &mut mats, &shared, &catalog, spec, 4 + k * 5, Livery::None, p, site.curb_yaw);
                    if k == 0 && scene == "drive" {
                        commands.entity(e).insert(Driven);
                        state.vehicle = Some(e);
                        if let Ok(mut v) = vis.single_mut() {
                            *v = Visibility::Hidden;
                        }
                    }
                }
                if scene == "cars" {
                    if let Ok(mut t) = player.single_mut() {
                        t.translation = site.curb + Vec3::new(-4.0, 0.0, 6.0);
                    }
                }
            }
            "job" => {
                jobs.write(JobCommand::Join(JobKind::Firefighter));
            }
            "menu" => {
                ui.open = true;
                ui.tab = match std::env::var("SVETLY_TAB").as_deref() {
                    Ok("cars") => Tab::Cars,
                    Ok("skins") => Tab::Skins,
                    Ok("casino") => Tab::Casino,
                    _ => Tab::Jobs,
                };
            }
            _ => {}
        }
    }
    if *frame == frames {
        let path = std::env::var("SVETLY_SHOT").unwrap();
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
    }
    if *frame == frames + 15 {
        exit.write(AppExit::Success);
    }
}
