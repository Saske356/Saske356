//! Игровой цикл: сообщения сервера, управление (ходьба, вождение, полёт), чужие игроки и машины.

use bevy::input::keyboard::{Key, KeyboardInput};
use bevy::prelude::*;
use novo_world as world;
use serde_json::{json, Value};

use crate::models::{animate_ped, spawn_car, spawn_ped, CarAssets, CarModel, PedRig};
use crate::net::{Net, NetEvent};
use crate::state::*;

#[derive(Component)]
pub struct LocalPed;
#[derive(Component)]
pub struct RemotePed(pub i64);
#[derive(Component)]
pub struct RemoteCar(pub i64);

fn f(v: &Value, i: usize) -> f32 {
    v.get(i).and_then(|x| x.as_f64()).unwrap_or(0.0) as f32
}
fn n(v: &Value, i: usize) -> i64 {
    v.get(i).and_then(|x| x.as_f64()).map(|x| x as i64).unwrap_or(-1)
}
fn kind_color(kind: &str) -> Color {
    match kind {
        "ok" => Color::srgb(0.55, 0.85, 0.55),
        "warn" => Color::srgb(1.0, 0.75, 0.35),
        _ => Color::srgb(0.6, 0.85, 1.0),
    }
}
fn parse_color(s: &str) -> Color {
    Srgba::hex(s.trim_start_matches('#')).map(Color::from).unwrap_or(Color::WHITE)
}

/// Сообщения сервера.
#[allow(clippy::too_many_arguments)]
pub fn net_receive(
    mut commands: Commands,
    net: Res<Net>,
    mut game: ResMut<Game>,
    collider: Res<Collider>,
    mut cars: ResMut<CarAssets>,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    local: Query<Entity, With<LocalPed>>,
) {
    while let Ok(ev) = net.rx.try_recv() {
        let m = match ev {
            NetEvent::Connected => { game.status = "Вход…".into(); continue; }
            NetEvent::Closed(why) => {
                game.connected = false;
                game.status = why.clone();
                game.chat(why, Color::srgb(1.0, 0.5, 0.5));
                continue;
            }
            NetEvent::Msg(m) => m,
        };
        let t = m.get("t").and_then(|x| x.as_str()).unwrap_or("");
        match t {
            "error" => {
                let text = m["text"].as_str().unwrap_or("Ошибка").to_string();
                game.status = text.clone();
                game.chat(text, Color::srgb(1.0, 0.5, 0.5));
            }
            "welcome" => {
                game.connected = true;
                game.status.clear();
                game.my_id = m["id"].as_i64().unwrap_or(0);
                game.name = m["name"].as_str().unwrap_or("").to_string();
                let (x, z) = (m["x"].as_f64().unwrap_or(0.0) as f32, m["z"].as_f64().unwrap_or(0.0) as f32);
                // на внешней карте точку спавна выбирает клиент (сервер про карту не знает)
                if !matches!(*collider, Collider::Map(_)) || game.pos == Vec3::ZERO {
                    game.pos = Vec3::new(x, collider.ground(x, z, 50.0), z);
                }
                game.ry = m["ry"].as_f64().unwrap_or(0.0) as f32;
                game.cam_yaw = game.ry;
                game.time = m["time"].as_f64().unwrap_or(540.0) as f32;
                apply_profile(&mut game, &m["profile"]);
                let name = game.name.clone();
                game.chat(format!("Добро пожаловать в ONIKS RP, {name}!"), Color::srgb(1.0, 0.84, 0.31));
                game.chat("WASD — ходьба/руль, Shift — бег, Пробел — ручник, мышь — камера, F — машина, T — чат, /ahelp — админка",
                    Color::srgb(1.0, 0.84, 0.31));
                if local.is_empty() {
                    let e = spawn_ped(&mut commands, &mut meshes, &mut mats, name_color(&name), game.pos);
                    commands.entity(e).insert(LocalPed);
                }
            }
            "profile" => apply_profile(&mut game, &m["profile"]),
            "chat" => game.chat(m["text"].as_str().unwrap_or(""), parse_color(m["color"].as_str().unwrap_or("#ffffff"))),
            "notify" => {
                let text = m["text"].as_str().unwrap_or("").to_string();
                game.toast = Some((text.clone(), 4.0));
                game.chat(text, kind_color(m["kind"].as_str().unwrap_or("")));
            }
            "job" => {
                let j = &m["job"];
                game.job_target = j["target"].as_array().map(|a| Vec2::new(a[0].as_f64().unwrap_or(0.0) as f32, a[1].as_f64().unwrap_or(0.0) as f32));
                game.job_label = j["label"].as_str().unwrap_or("").to_string();
            }
            "teleport" => {
                let (x, z) = (m["x"].as_f64().unwrap_or(0.0) as f32, m["z"].as_f64().unwrap_or(0.0) as f32);
                let y = collider.ground(x, z, 200.0);
                if let Some(c) = game.car.as_mut() { c.x = x; c.z = z; c.spd = 0.0; }
                game.pos = Vec3::new(x, y, z);
            }
            "fly" => game.fly = m["on"].as_bool().unwrap_or(false),
            "entered" => {
                let vid = m["vid"].as_i64().unwrap_or(-1);
                if let Some(v) = game.vehicles.get(&vid) {
                    let model = v.model.clone();
                    game.veh = vid;
                    game.car = Some(CarPhys {
                        model, x: m["x"].as_f64().unwrap_or(0.0) as f32, z: m["z"].as_f64().unwrap_or(0.0) as f32,
                        ry: m["ry"].as_f64().unwrap_or(0.0) as f32, spd: 0.0, steer: 0.0,
                    });
                    game.cam_yaw = game.car.as_ref().unwrap().ry;
                }
            }
            "exited" => {
                game.veh = -1;
                game.car = None;
                let (x, z) = (m["x"].as_f64().unwrap_or(0.0) as f32, m["z"].as_f64().unwrap_or(0.0) as f32);
                let y = collider.ground(x, z, game.pos.y + 2.0);
                game.pos = Vec3::new(x, y, z);
            }
            "snap" => apply_snap(&mut commands, &mut game, &m, &collider, &mut cars, &assets, &mut meshes, &mut mats),
            _ => {}
        }
    }
}

fn apply_profile(game: &mut Game, p: &Value) {
    game.money = p["money"].as_i64().unwrap_or(game.money);
    game.level = p["level"].as_i64().unwrap_or(game.level);
    game.admin = p["admin"].as_i64().unwrap_or(0);
    game.license = p["license"].as_bool().unwrap_or(false);
}

#[allow(clippy::too_many_arguments)]
fn apply_snap(
    commands: &mut Commands, game: &mut Game, m: &Value, collider: &Collider, cars: &mut CarAssets, assets: &AssetServer,
    meshes: &mut Assets<Mesh>, mats: &mut Assets<StandardMaterial>,
) {
    game.time = m["time"].as_f64().unwrap_or(game.time as f64) as f32;
    game.online = m["n"].as_i64().unwrap_or(1);
    let v2 = m["f"].as_i64() == Some(2);
    let mut seen = Vec::new();
    for e in m["p"].as_array().into_iter().flatten() {
        // v2: [id,x,y,z,ry,anim,veh(,ник)]; v1: [id,ник,x,y,z,ry,anim,veh]
        let (id, name, x, y, z, ry, anim, veh) = if v2 {
            let id = n(e, 0);
            if let Some(nm) = e.get(7).and_then(|x| x.as_str()) { game.name_cache.insert(id, nm.to_string()); }
            (id, game.name_cache.get(&id).cloned().unwrap_or_else(|| format!("Игрок_{id}")), f(e, 1), f(e, 2), f(e, 3), f(e, 4), n(e, 5), n(e, 6))
        } else {
            (n(e, 0), e[1].as_str().unwrap_or("").to_string(), f(e, 2), f(e, 3), f(e, 4), f(e, 5), n(e, 6), n(e, 7))
        };
        if id == game.my_id {
            continue;
        }
        seen.push(id);
        let target = Vec3::new(x, y, z);
        if let Some(p) = game.players.get_mut(&id) {
            p.target = target; p.ry = ry; p.anim = anim; p.veh = veh;
        } else {
            let ent = spawn_ped(commands, meshes, mats, name_color(&name), target);
            commands.entity(ent).insert(RemotePed(id));
            game.players.insert(id, RemoteP { entity: ent, name, target, ry, anim, veh });
        }
    }
    let gone: Vec<i64> = game.players.keys().copied().filter(|id| !seen.contains(id)).collect();
    for id in gone {
        if let Some(p) = game.players.remove(&id) { commands.entity(p.entity).despawn(); }
    }
    let mut seen_v = Vec::new();
    for e in m["v"].as_array().into_iter().flatten() {
        let id = n(e, 0);
        let (x, z, ry, spd, driver, st) = if v2 {
            if let Some(model) = e.get(6).and_then(|x| x.as_str()) {
                game.veh_cache.insert(id, VehStatic {
                    model: model.to_string(), color: n(e, 7) as u32, owner: n(e, 8),
                    plate: e.get(9).and_then(|x| x.as_str()).unwrap_or("").to_string(),
                    skin: e.get(10).and_then(|x| x.as_str()).map(String::from),
                });
            }
            let Some(st) = game.veh_cache.get(&id).cloned() else { continue };
            (f(e, 1), f(e, 2), f(e, 3), f(e, 4), n(e, 5), st)
        } else {
            let st = VehStatic { model: e[1].as_str().unwrap_or("kroha").to_string(), color: n(e, 2) as u32, owner: n(e, 8),
                plate: e[9].as_str().unwrap_or("").to_string(), skin: e.get(10).and_then(|x| x.as_str()).map(String::from) };
            (f(e, 3), f(e, 4), f(e, 5), f(e, 6), n(e, 7), st)
        };
        seen_v.push(id);
        let target = Vec3::new(x, collider.ground(x, z, 50.0), z);
        let rebuild = game.vehicles.get(&id).is_some_and(|v| v.color != st.color);
        if rebuild {
            if let Some(v) = game.vehicles.remove(&id) { commands.entity(v.entity).despawn(); }
        }
        if let Some(v) = game.vehicles.get_mut(&id) {
            v.target = target; v.ry = ry; v.spd = spd; v.driver = driver;
        } else {
            let ent = spawn_car(commands, cars, assets, meshes, mats, &st.model, st.skin.as_deref(), st.color, target, ry);
            commands.entity(ent).insert(RemoteCar(id));
            game.vehicles.insert(id, RemoteV {
                entity: ent, model: st.model, skin: st.skin, color: st.color, owner: st.owner, driver, plate: st.plate, target, ry, spd,
            });
        }
    }
    let gone: Vec<i64> = game.vehicles.keys().copied().filter(|id| !seen_v.contains(id)).collect();
    for id in gone {
        if let Some(v) = game.vehicles.remove(&id) { commands.entity(v.entity).despawn(); }
    }
}

/// Ввод с клавиатуры для чата: T — открыть, Enter — отправить, Esc — закрыть.
pub fn chat_input(mut events: EventReader<KeyboardInput>, keys: Res<ButtonInput<KeyCode>>, mut game: ResMut<Game>, net: Res<Net>) {
    if game.typing.is_none() {
        if keys.just_pressed(KeyCode::KeyT) || keys.just_pressed(KeyCode::Enter) {
            game.typing = Some(String::new());
            events.clear();
        } else if keys.just_pressed(KeyCode::Slash) {
            game.typing = Some("/".into());
            events.clear();
        }
        return;
    }
    for e in events.read() {
        if !e.state.is_pressed() {
            continue;
        }
        match &e.logical_key {
            Key::Enter => {
                let text = game.typing.take().unwrap_or_default();
                if !text.trim().is_empty() {
                    net.send(json!({ "t": "chat", "text": text }));
                }
                return;
            }
            Key::Escape => { game.typing = None; return; }
            Key::Backspace => { if let Some(t) = game.typing.as_mut() { t.pop(); } }
            Key::Space => { if let Some(t) = game.typing.as_mut() { t.push(' '); } }
            Key::Character(c) => { if let Some(t) = game.typing.as_mut() { if t.chars().count() < 140 { t.push_str(c); } } }
            _ => {}
        }
    }
}

/// Управление своим персонажем или машиной.
#[allow(clippy::too_many_arguments)]
pub fn local_control(
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    mut game: ResMut<Game>,
    collider: Res<Collider>,
    net: Res<Net>,
    mut ped: Query<(&mut Transform, &mut Visibility, &mut PedRig), With<LocalPed>>,
    mut limbs: Query<&mut Transform, Without<PedRig>>,
    mut debug: ResMut<crate::Debug>,
) {
    let dt = time.delta_secs().min(0.05);
    if !game.connected {
        return;
    }
    let typing = game.typing.is_some();
    let k = |c: KeyCode| !typing && keys.pressed(c);
    let auto = debug.forward_until > time.elapsed_secs();
    let ix = (k(KeyCode::KeyD) || k(KeyCode::ArrowRight)) as i32 as f32 - (k(KeyCode::KeyA) || k(KeyCode::ArrowLeft)) as i32 as f32;
    let iy = (k(KeyCode::KeyW) || k(KeyCode::ArrowUp) || auto) as i32 as f32 - (k(KeyCode::KeyS) || k(KeyCode::ArrowDown)) as i32 as f32;
    let sprint = k(KeyCode::ShiftLeft) || k(KeyCode::ShiftRight);
    let brake = k(KeyCode::Space);

    if !typing && (keys.just_pressed(KeyCode::KeyF) || std::mem::take(&mut debug.press_f)) {
        toggle_vehicle(&mut game, &net);
    }

    if let Some(mut c) = game.car.clone() {
        drive(&mut c, ix, iy, brake, dt, &collider, &game);
        game.pos = Vec3::new(c.x, collider.ground(c.x, c.z, game.pos.y), c.z);
        game.ry = c.ry;
        game.anim = 0;
        let (vid, pos) = (game.veh, game.pos);
        if let Some(v) = game.vehicles.get_mut(&vid) {
            v.target = pos; v.ry = c.ry; v.spd = c.spd;
        }
        game.car = Some(c);
        if let Ok((_, mut vis, _)) = ped.single_mut() { *vis = Visibility::Hidden; }
    } else {
        let (fx, fz) = (game.cam_yaw.sin(), game.cam_yaw.cos());
        let mut d = Vec2::new(fx * iy - fz * ix, fz * iy + fx * ix);
        let len = d.length();
        if game.fly {
            let speed = if sprint { 60.0 } else { 22.0 };
            let up = k(KeyCode::Space) as i32 as f32 - (k(KeyCode::KeyC) || k(KeyCode::ControlLeft)) as i32 as f32;
            let dy = up + iy * -(game.cam_pitch - 0.32) * 1.6;
            game.pos.x = (game.pos.x + d.x * speed * dt).clamp(1.0, SIZE - 1.0);
            game.pos.z = (game.pos.z + d.y * speed * dt).clamp(1.0, SIZE - 1.0);
            let g = collider.ground(game.pos.x, game.pos.z, game.pos.y);
            game.pos.y = (game.pos.y + dy * speed * dt).clamp(g, 400.0);
            if len > 0.05 { game.ry = lerp_angle(game.ry, d.x.atan2(d.y), 1.0 - (-dt * 8.0).exp()); }
            game.anim = 0;
        } else {
            let speed = if sprint { 8.5 } else { 4.5 };
            if len > 0.05 {
                d *= len.min(1.0) / len;
                let (ox, oz) = (game.pos.x, game.pos.z);
                let (nx, nz) = (ox + d.x * speed * dt, oz + d.y * speed * dt);
                let (x, z, _) = collider.step(ox, oz, nx, nz, game.pos.y, 0.35);
                game.pos.x = x.clamp(1.0, SIZE - 1.0);
                game.pos.z = z.clamp(1.0, SIZE - 1.0);
                game.ry = lerp_angle(game.ry, d.x.atan2(d.y), 1.0 - (-dt * 12.0).exp());
                game.anim = if sprint { 2 } else { 1 };
            } else {
                game.anim = 0;
            }
            let g = collider.ground(game.pos.x, game.pos.z, game.pos.y);
            game.pos.y += (g - game.pos.y) * (dt * 15.0).min(1.0);
        }
        if let Ok((mut t, mut vis, mut rig)) = ped.single_mut() {
            *vis = Visibility::Inherited;
            t.translation = game.pos;
            t.rotation = Quat::from_rotation_y(game.ry);
            animate_ped(&mut rig, game.anim, dt, &mut limbs);
        }
    }

    // отправка состояния 15 раз в секунду
    game.send_timer -= dt;
    if game.send_timer <= 0.0 {
        game.send_timer = 0.066;
        let (vry, spd) = game.car.as_ref().map_or((0.0, 0.0), |c| (c.ry, c.spd));
        net.send(json!({ "t": "state", "x": game.pos.x, "y": game.pos.y, "z": game.pos.z, "ry": game.ry, "anim": game.anim,
                         "vry": vry, "spd": spd }));
    }
    // чекпоинты работ
    game.cp_timer -= dt;
    if let Some(t) = game.job_target {
        if game.cp_timer <= 0.0 && Vec2::new(game.pos.x, game.pos.z).distance(t) < 6.0 {
            game.cp_timer = 1.0;
            net.send(json!({ "t": "cp" }));
        }
    }
}

fn toggle_vehicle(game: &mut Game, net: &Net) {
    if let Some(c) = &game.car {
        if c.spd.abs() > 4.0 {
            game.toast = Some(("Сначала остановитесь".into(), 2.5));
        } else {
            net.send(json!({ "t": "exit" }));
        }
        return;
    }
    let me = game.pos;
    let best = game.vehicles.iter()
        .filter(|(_, v)| v.driver < 0)
        .map(|(id, v)| {
            let d = world::car_circles(v.target.x as f64, v.target.z as f64, v.ry as f64, &v.model).into_iter()
                .map(|(x, z, r)| (x as f32 - me.x).hypot(z as f32 - me.z) - r as f32).fold(f32::INFINITY, f32::min);
            (*id, d, v.owner)
        })
        .min_by(|a, b| a.1.total_cmp(&b.1));
    match best {
        Some((id, d, owner)) if d < 3.5 => {
            if owner != game.my_id {
                game.toast = Some(("Транспорт закрыт — это чужая машина".into(), 2.5));
            } else {
                net.send(json!({ "t": "enter", "vid": id }));
            }
        }
        _ => game.toast = Some(("Рядом нет транспорта".into(), 2.5)),
    }
}

/// Аркадная физика машины (как в JS-клиенте) + столкновения со зданиями и другими машинами.
fn drive(c: &mut CarPhys, ix: f32, iy: f32, brake: bool, dt: f32, collider: &Collider, game: &Game) {
    let m = world::car(&c.model).unwrap_or(&world::CARS[0]);
    let (max, acc) = (m.max_speed as f32, m.accel as f32);
    if iy > 0.0 {
        if c.spd < -0.5 { c.spd += 22.0 * dt } else { c.spd += acc * iy * dt * (1.0 - c.spd / max).max(0.0) }
    } else if iy < 0.0 {
        if c.spd > 0.5 { c.spd -= 22.0 * dt * -iy } else { c.spd = (c.spd - acc * 0.6 * dt).max(-8.0) }
    } else {
        c.spd -= c.spd.signum() * c.spd.abs().min(2.5 * dt);
    }
    if brake {
        c.spd *= (1.0 - 3.0 * dt).max(0.0);
    }
    c.steer += (ix - c.steer) * (dt * 7.0).min(1.0);
    let ang = -c.steer * 0.55 * (1.0 - (c.spd.abs() / (max * 1.3)).min(0.65));
    c.ry += c.spd * ang.tan() / (m.len as f32 * 0.6) * dt;
    let (ox, oz) = (c.x, c.z);
    c.x += c.ry.sin() * c.spd * dt;
    c.z += c.ry.cos() * c.spd * dt;
    let mut hit = false;
    for (x, z, r) in world::car_circles(c.x as f64, c.z as f64, c.ry as f64, &c.model) {
        let (x, z, r) = (x as f32, z as f32, r as f32);
        let (nx, nz, h) = collider.step(x - (c.x - ox), z - (c.z - oz), x, z, game.pos.y, r);
        if h {
            c.x += nx - x;
            c.z += nz - z;
            hit = true;
        }
        // другие машины
        for (vid, v) in &game.vehicles {
            if *vid == game.veh { continue; }
            for (vx, vz, vr) in world::car_circles(v.target.x as f64, v.target.z as f64, v.ry as f64, &v.model) {
                let (dx, dz) = (c.x - vx as f32, c.z - vz as f32);
                let d = dx.hypot(dz);
                let mm = r + vr as f32;
                if d < mm && d > 1e-4 {
                    c.x += dx / d * (mm - d);
                    c.z += dz / d * (mm - d);
                    hit = true;
                }
            }
        }
    }
    if hit {
        c.spd = if c.spd.abs() > 5.0 { c.spd * -0.25 } else { c.spd * 0.6 };
    }
    c.x = c.x.clamp(1.0, SIZE - 1.0);
    c.z = c.z.clamp(1.0, SIZE - 1.0);
}

/// Плавное движение чужих игроков и машин к последним координатам с сервера + колёса.
pub fn interpolate(
    time: Res<Time>,
    game: Res<Game>,
    mut peds: Query<(&RemotePed, &mut Transform, &mut Visibility, &mut PedRig)>,
    mut cars_t: Query<(&RemoteCar, &mut Transform, &mut CarModel), Without<RemotePed>>,
    mut limbs: Query<&mut Transform, (Without<PedRig>, Without<RemoteCar>, Without<RemotePed>, Without<CarModel>)>,
) {
    let dt = time.delta_secs().min(0.05);
    let k = 1.0 - (-dt * 12.0).exp();
    for (rp, mut t, mut vis, mut rig) in &mut peds {
        let Some(p) = game.players.get(&rp.0) else { continue };
        t.translation = t.translation.lerp(p.target, k);
        let (y, _, _) = t.rotation.to_euler(EulerRot::YXZ);
        t.rotation = Quat::from_rotation_y(lerp_angle(y, p.ry, k));
        *vis = if p.veh >= 0 { Visibility::Hidden } else { Visibility::Inherited };
        let anim = p.anim;
        animate_ped_q(&mut rig, anim, dt, &mut limbs);
    }
    for (rc, mut t, mut car) in &mut cars_t {
        let Some(v) = game.vehicles.get(&rc.0) else { continue };
        if rc.0 == game.veh {
            t.translation = v.target;
            t.rotation = Quat::from_rotation_y(v.ry);
        } else {
            t.translation = t.translation.lerp(v.target, k);
            let (y, _, _) = t.rotation.to_euler(EulerRot::YXZ);
            t.rotation = Quat::from_rotation_y(lerp_angle(y, v.ry, k));
        }
        if car.wheel_r > 0.01 {
            car.spin += v.spd * dt / car.wheel_r;
        }
        let spin = car.spin;
        for (w, base) in car.wheels.clone() {
            if let Ok(mut wt) = limbs.get_mut(w) {
                wt.rotation = Quat::from_rotation_x(spin) * base;
            }
        }
    }
}

fn animate_ped_q(rig: &mut PedRig, anim: i64, dt: f32, tq: &mut Query<&mut Transform, (Without<PedRig>, Without<RemoteCar>, Without<RemotePed>, Without<CarModel>)>) {
    let a = if anim > 0 {
        rig.phase += dt * if anim == 2 { 12.0 } else { 8.0 };
        rig.phase.sin() * if anim == 2 { 0.9 } else { 0.55 }
    } else {
        rig.phase = 0.0;
        0.0
    };
    let k = 1.0 - (-dt * 15.0).exp();
    for (e, target) in [(rig.legs[0], a), (rig.legs[1], -a), (rig.arms[0], -a * 0.8), (rig.arms[1], a * 0.8)] {
        if let Ok(mut t) = tq.get_mut(e) {
            let (cur, _, _) = t.rotation.to_euler(EulerRot::XYZ);
            t.rotation = Quat::from_rotation_x(cur + (target - cur) * k);
        }
    }
}
