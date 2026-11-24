//! Звук. Эффекты синтезируются при запуске (те же осцилляторы и фильтры, что WebAudio в веб-версии)
//! и играются микшером macroquad. Саундтрек (OGG) на Android играет системный MediaPlayer потоково
//! (через мост в MainActivity), на компьютере — микшер macroquad. Кроссфейд между треками по состоянию игры.
use crate::game::Sfx;
use macroquad::audio::{load_sound_from_bytes, play_sound, set_sound_volume, stop_sound, PlaySoundParams, Sound};
use std::collections::HashMap;

const SR: f32 = 44100.;

#[derive(Clone, Copy)] enum Wave { Sine, Tri, Saw, Sq }
#[derive(Clone, Copy)] enum Flt { Lp, Hp, Bp }

struct Buf(Vec<f32>);
impl Buf {
    fn new(dur: f32) -> Buf { Buf(vec![0.; (dur * SR) as usize + 64]) }
    fn ensure(&mut self, n: usize) { if self.0.len() < n { self.0.resize(n, 0.); } }
    /// Тон: частота от f0 к f1 (экспоненциально), атака 6 мс, экспоненциальное затухание к dur
    fn tone(&mut self, w: Wave, f0: f32, f1: f32, dur: f32, vol: f32, t0: f32) {
        let n = (dur * SR) as usize; let s0 = (t0 * SR) as usize; self.ensure(s0 + n + 8); let mut ph = 0f32;
        for i in 0..n { let t = i as f32 / SR; let k = t / dur;
            let f = if (f1 - f0).abs() < 0.01 { f0 } else { f0 * (f1.max(20.) / f0).powf(k) }; ph += f / SR; ph -= ph.floor();
            let v = match w { Wave::Sine => (ph * std::f32::consts::TAU).sin(), Wave::Tri => 1. - 4. * (ph - 0.5).abs(), Wave::Saw => 2. * ph - 1., Wave::Sq => if ph < 0.5 { 1. } else { -1. } };
            let env = if t < 0.006 { 0.0001 * (vol / 0.0001).powf(t / 0.006) } else { vol * (0.0001 / vol).powf(((t - 0.006) / (dur - 0.006)).min(1.)) };
            self.0[s0 + i] += v * env; }
    }
    /// Шум через фильтр с изменяемой частотой среза
    fn noise(&mut self, dur: f32, vol: f32, ft: Flt, f0: f32, f1: f32, q: f32, t0: f32, seed: &mut u32) {
        let n = (dur * SR) as usize; let s0 = (t0 * SR) as usize; self.ensure(s0 + n + 8);
        let (mut x1, mut x2, mut y1, mut y2) = (0f32, 0f32, 0f32, 0f32);
        for i in 0..n { let t = i as f32 / SR; let k = t / dur;
            *seed ^= *seed << 13; *seed ^= *seed >> 17; *seed ^= *seed << 5; let x = (*seed as f32 / u32::MAX as f32) * 2. - 1.;
            let f = if f1 > 0. { f0 * (f1 / f0).powf(k) } else { f0 }.min(SR * 0.45);
            let w0 = std::f32::consts::TAU * f / SR; let (cw, sw) = (w0.cos(), w0.sin()); let al = sw / (2. * q.max(0.1));
            let (b0, b1, b2) = match ft { Flt::Lp => ((1. - cw) / 2., 1. - cw, (1. - cw) / 2.), Flt::Hp => ((1. + cw) / 2., -(1. + cw), (1. + cw) / 2.), Flt::Bp => (al, 0., -al) };
            let (a0, a1, a2) = (1. + al, -2. * cw, 1. - al);
            let y = (b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0; x2 = x1; x1 = x; y2 = y1; y1 = y;
            let env = if t < 0.01 { 0.0001 * (vol / 0.0001).powf(t / 0.01) } else { vol * (0.0001 / vol).powf(((t - 0.01) / (dur - 0.01)).min(1.)) };
            self.0[s0 + i] += y * env; }
    }
    fn wav(&self) -> Vec<u8> {
        let n = self.0.len(); let mut out = Vec::with_capacity(44 + n * 2);
        let w32 = |o: &mut Vec<u8>, v: u32| o.extend_from_slice(&v.to_le_bytes()); let w16 = |o: &mut Vec<u8>, v: u16| o.extend_from_slice(&v.to_le_bytes());
        out.extend_from_slice(b"RIFF"); w32(&mut out, 36 + n as u32 * 2); out.extend_from_slice(b"WAVEfmt "); w32(&mut out, 16); w16(&mut out, 1); w16(&mut out, 1);
        w32(&mut out, SR as u32); w32(&mut out, SR as u32 * 2); w16(&mut out, 2); w16(&mut out, 16); out.extend_from_slice(b"data"); w32(&mut out, n as u32 * 2);
        for &s in &self.0 { let v = (s.tanh() * 32000.) as i16; out.extend_from_slice(&v.to_le_bytes()); }
        out
    }
}

#[derive(Hash, PartialEq, Eq, Clone, Copy, Debug)]
enum Key { Shoot(u8), Hit, Clink, Kill(u8), Boom(bool), Pick(u8), Pearl, Level, PickCard, Hurt, Dash, Nova, Flare, Warn, Click, Ach, Graze, Beat, Shot2 }

fn synth(k: Key, seed: &mut u32) -> Buf {
    let mut b = Buf::new(0.2);
    let mt = |s: f32, base: f32| base * 2f32.powf(s / 12.);
    match k {
        Key::Shoot(v) => b.tone(Wave::Sq, 900. + v as f32 * 30., 380., 0.055, 0.028, 0.),
        Key::Hit => b.noise(0.05, 0.07, Flt::Bp, 2600., 900., 2., 0., seed),
        Key::Clink => b.tone(Wave::Tri, 2400., 1800., 0.07, 0.05, 0.),
        Key::Kill(c) => { let f = 300. * 2f32.powf(c as f32 / 12.); b.tone(Wave::Tri, f * 2., f, 0.12, 0.08, 0.); b.noise(0.12, 0.08, Flt::Lp, 3000., 300., 1., 0., seed); }
        Key::Boom(big) => { b.noise(if big { 1.1 } else { 0.35 }, if big { 0.55 } else { 0.2 }, Flt::Lp, if big { 2200. } else { 2600. }, 60., 0.8, 0., seed);
            b.tone(Wave::Sine, if big { 110. } else { 170. }, 35., if big { 0.8 } else { 0.28 }, if big { 0.6 } else { 0.25 }, 0.); }
        Key::Pick(c) => { let f = 880. * 2f32.powf(c as f32 / 15.); b.tone(Wave::Sine, f, f * 1.4, 0.07, 0.05, 0.); }
        Key::Pearl => { b.tone(Wave::Tri, 1300., 2000., 0.15, 0.08, 0.); b.tone(Wave::Sine, 2600., 3200., 0.2, 0.04, 0.05); }
        Key::Level => for (i, s) in [0., 4., 7., 12., 16., 19.].iter().enumerate() { let f = mt(*s, 523.); b.tone(Wave::Tri, f, f, 0.25, 0.09, i as f32 * 0.055); },
        Key::PickCard => { b.tone(Wave::Sine, 660., 1320., 0.18, 0.1, 0.); b.noise(0.3, 0.06, Flt::Hp, 3000., 8000., 1., 0., seed); }
        Key::Hurt => { b.tone(Wave::Saw, 240., 55., 0.3, 0.16, 0.); b.noise(0.25, 0.18, Flt::Lp, 1400., 150., 1., 0., seed); }
        Key::Dash => b.noise(0.28, 0.2, Flt::Bp, 500., 3200., 1.2, 0., seed),
        Key::Nova => { b.tone(Wave::Sine, 300., 900., 0.25, 0.1, 0.); b.noise(0.3, 0.08, Flt::Bp, 900., 4000., 1., 0., seed); }
        Key::Flare => { b.noise(1.6, 0.5, Flt::Hp, 400., 6000., 0.7, 0., seed); b.tone(Wave::Saw, 80., 640., 0.9, 0.18, 0.); b.tone(Wave::Sine, 60., 30., 1.4, 0.5, 0.05);
            for (i, s) in [0., 7., 12., 19.].iter().enumerate() { let f = mt(*s, 440.); b.tone(Wave::Tri, f, f, 0.8, 0.06, 0.1 + i as f32 * 0.07); } }
        Key::Warn => for i in 0..3 { b.tone(Wave::Saw, 220., 440., 0.45, 0.14, i as f32 * 0.6); b.tone(Wave::Saw, 223., 445., 0.45, 0.1, i as f32 * 0.6); },
        Key::Click => b.tone(Wave::Sine, 720., 980., 0.06, 0.06, 0.),
        Key::Ach => for (i, s) in [0., 5., 9., 12.].iter().enumerate() { let f = mt(*s, 660.); b.tone(Wave::Sq, f, f, 0.18, 0.04, i as f32 * 0.09); },
        Key::Graze => b.tone(Wave::Sine, 2200., 2900., 0.04, 0.025, 0.),
        Key::Beat => { b.tone(Wave::Sine, 70., 45., 0.16, 0.22, 0.); b.tone(Wave::Sine, 65., 40., 0.14, 0.16, 0.17); }
        Key::Shot2 => b.tone(Wave::Sine, 500., 260., 0.1, 0.04, 0.),
    }
    // общий уровень как у веб-версии (master 0.85 × sfx 0.9), с запасом от перегруза микшера
    for s in b.0.iter_mut() { *s *= 0.85 * 0.9 * 1.6; }
    b
}

pub const TRACKS: [&str; 10] = ["menu", "zone1", "zone2", "zone3", "zone4", "boss1", "boss2", "boss3", "gameover", "victory"];

pub struct Audio {
    sfx: HashMap<Key, Sound>, last: HashMap<u8, f64>, pub sound_on: bool, pub music_on: bool, pub vol_sfx: f32, pub vol_mus: f32, last_mus: f32,
    /// уровень каждого трека в кроссфейде 0..1
    vol: [f32; 10], playing: [bool; 10], done_once: [bool; 10], pub want: Option<usize>, desk: HashMap<usize, Sound>, pub native_music: bool, t: f64,
    pub cmds: Vec<(usize, i32, f32)> /* для платформы: (трек, 1 старт/0 громкость/-1 стоп, громкость) */,
}

impl Audio {
    pub async fn new(native_music: bool) -> Audio {
        let mut a = Audio { sfx: HashMap::new(), last: HashMap::new(), sound_on: true, music_on: true, vol_sfx: 1., vol_mus: 1., last_mus: 1., vol: [0.; 10], playing: [false; 10], done_once: [false; 10], want: None,
            desk: HashMap::new(), native_music, t: 0., cmds: vec![] };
        let mut keys = vec![Key::Hit, Key::Clink, Key::Boom(true), Key::Boom(false), Key::Pearl, Key::Level, Key::PickCard, Key::Hurt, Key::Dash, Key::Nova, Key::Flare, Key::Warn, Key::Click, Key::Ach, Key::Graze, Key::Beat, Key::Shot2];
        for i in 0..4 { keys.push(Key::Shoot(i)); } for i in 0..12 { keys.push(Key::Kill(i)); } for i in 0..15 { keys.push(Key::Pick(i)); }
        let mut seed = 0x1234567u32;
        for k in keys { let b = synth(k, &mut seed); if let Ok(s) = load_sound_from_bytes(&b.wav()).await { a.sfx.insert(k, s); } }
        a
    }
    fn thr(&mut self, id: u8, ms: f64) -> bool { let now = macroquad::time::get_time() * 1000.; let l = self.last.get(&id).copied().unwrap_or(-1e9); if now - l < ms { return false; } self.last.insert(id, now); true }
    pub fn play(&mut self, e: Sfx) {
        if !self.sound_on || self.vol_sfx <= 0.01 { return; }
        let (k, th): (Key, Option<(u8, f64)>) = match e {
            Sfx::Shoot => (Key::Shoot(macroquad::rand::gen_range(0u8, 4)), Some((0, 75.))), Sfx::Hit => (Key::Hit, Some((1, 45.))), Sfx::Clink => (Key::Clink, Some((2, 70.))),
            Sfx::Kill(c) => (Key::Kill((c.min(36) % 12) as u8), Some((3, 40.))), Sfx::Boom(b) => (Key::Boom(b), if b { None } else { Some((4, 60.)) }),
            Sfx::Pick(c) => (Key::Pick(((c as i32).rem_euclid(15)) as u8), Some((5, 30.))), Sfx::Pearl => (Key::Pearl, None), Sfx::Level => (Key::Level, None),
            Sfx::PickCard => (Key::PickCard, None), Sfx::Hurt => (Key::Hurt, None), Sfx::Dash => (Key::Dash, None), Sfx::Nova => (Key::Nova, None),
            Sfx::Flare => (Key::Flare, None), Sfx::Warn => (Key::Warn, None), Sfx::Click => (Key::Click, Some((6, 40.))), Sfx::Ach => (Key::Ach, None),
            Sfx::Graze => (Key::Graze, Some((7, 90.))), Sfx::Beat => (Key::Beat, None), Sfx::Shot2 => (Key::Shot2, Some((8, 110.))),
        };
        if let Some((id, ms)) = th { if !self.thr(id, ms) { return; } }
        if let Some(s) = self.sfx.get(&k) { play_sound(s, PlaySoundParams { looped: false, volume: self.vol_sfx }); }
    }
    pub fn once(i: usize) -> bool { i >= 8 }
    /// Кроссфейд: вызывается каждый кадр с нужным треком (None — тишина)
    pub async fn tick(&mut self, want: Option<usize>, dt: f32, paused: bool) {
        let want = if self.music_on { want } else { None };
        if want != self.want { if let Some(w) = want { if Self::once(w) || self.vol[w] <= 0.01 { self.done_once[w] = false; if self.playing[w] { self.stop(w); } } } self.want = want; }
        let step = dt / 1.5; let vm = self.vol_mus; let vm_changed = (vm - self.last_mus).abs() > 1e-3; self.last_mus = vm;
        for i in 0..10 {
            let target = if Some(i) == self.want && !paused { 1. } else { 0. };
            let v0 = self.vol[i]; self.vol[i] = if target > v0 { (v0 + step).min(target) } else { (v0 - step).max(target) };
            let gain = self.vol[i] * self.vol[i] * 0.6 * vm;
            if self.vol[i] > 0. && !self.playing[i] && !(Self::once(i) && self.done_once[i]) { self.start(i).await; }
            if self.playing[i] { if self.vol[i] <= 0. { self.stop(i); } else if vm_changed || (self.vol[i] - v0).abs() > 1e-5 { self.set_vol(i, gain); } }
        }
        self.t += dt as f64;
    }
    pub fn track_done(&mut self, i: usize) { self.done_once[i] = true; self.playing[i] = false; }
    async fn start(&mut self, i: usize) {
        self.playing[i] = true; let v = self.vol[i] * self.vol[i] * 0.6 * self.vol_mus;
        if self.native_music { self.cmds.push((i, 1, v)); return; }
        if !self.desk.contains_key(&i) { if let Ok(s) = macroquad::audio::load_sound(&format!("audio/{}.ogg", TRACKS[i])).await { self.desk.insert(i, s); } }
        if let Some(s) = self.desk.get(&i) { play_sound(s, PlaySoundParams { looped: !Self::once(i), volume: v }); }
        if Self::once(i) { self.done_once[i] = true; }
    }
    fn stop(&mut self, i: usize) {
        self.playing[i] = false;
        if self.native_music { self.cmds.push((i, -1, 0.)); return; }
        if let Some(s) = self.desk.get(&i) { stop_sound(s); }
    }
    fn set_vol(&mut self, i: usize, v: f32) { if self.native_music { self.cmds.push((i, 0, v)); } else if let Some(s) = self.desk.get(&i) { set_sound_volume(s, v); } }
}
