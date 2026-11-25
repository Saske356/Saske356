//! Связь с системой: реклама, вибрация, музыка, ориентация, файлы, отступы экрана.
//! На Android — вызовы методов MainActivity через JNI, на компьютере — заглушки и файлы рядом с игрой.

/// События от системы
pub enum Ev { Ad(String, bool), MusicDone(usize), Save(String) }

#[cfg(target_os = "android")]
mod imp {
    use super::Ev;
    use macroquad::miniquad::native::android::{attach_jni_env, ndk_sys, ACTIVITY};
    use std::ffi::{CStr, CString};

    /// Вызов метода активности в отдельном кадре локальных ссылок (поток игры живёт вечно — ссылки не должны копиться)
    unsafe fn with<R>(f: impl FnOnce(*mut ndk_sys::JNIEnv) -> R) -> R {
        let env = attach_jni_env();
        (**env).PushLocalFrame.unwrap()(env, 16);
        let r = f(env);
        if (**env).ExceptionCheck.unwrap()(env) != 0 { (**env).ExceptionClear.unwrap()(env); }
        (**env).PopLocalFrame.unwrap()(env, std::ptr::null_mut());
        r
    }
    unsafe fn mid(env: *mut ndk_sys::JNIEnv, name: &str, sig: &str) -> ndk_sys::jmethodID {
        let cls = (**env).GetObjectClass.unwrap()(env, ACTIVITY);
        let n = CString::new(name).unwrap(); let s = CString::new(sig).unwrap();
        (**env).GetMethodID.unwrap()(env, cls, n.as_ptr(), s.as_ptr())
    }
    unsafe fn jstr(env: *mut ndk_sys::JNIEnv, s: &str) -> ndk_sys::jstring { let c = CString::new(s).unwrap_or_default(); (**env).NewStringUTF.unwrap()(env, c.as_ptr()) }
    unsafe fn rstr(env: *mut ndk_sys::JNIEnv, o: ndk_sys::jobject) -> String {
        if o.is_null() { return String::new(); }
        let p = (**env).GetStringUTFChars.unwrap()(env, o, std::ptr::null_mut()); if p.is_null() { return String::new(); }
        let s = CStr::from_ptr(p).to_string_lossy().into_owned(); (**env).ReleaseStringUTFChars.unwrap()(env, o, p); s
    }
    fn call_v(name: &str, sig: &str, args: impl FnOnce(*mut ndk_sys::JNIEnv, ndk_sys::jmethodID)) { unsafe { with(|env| { let m = mid(env, name, sig); if !m.is_null() { args(env, m) } }) } }
    fn call_s(name: &str) -> String { unsafe { with(|env| { let m = mid(env, name, "()Ljava/lang/String;"); if m.is_null() { return String::new(); } let o = (**env).CallObjectMethod.unwrap()(env, ACTIVITY, m); rstr(env, o) }) } }
    fn call_b(name: &str, sig: &str, arg: Option<i32>) -> bool { unsafe { with(|env| { let m = mid(env, name, sig); if m.is_null() { return false; }
        (match arg { Some(a) => (**env).CallBooleanMethod.unwrap()(env, ACTIVITY, m, a), None => (**env).CallBooleanMethod.unwrap()(env, ACTIVITY, m) }) != 0 }) } }

    pub fn ad_ready(kind: i32) -> bool { call_b("adReady", "(I)Z", Some(kind)) }
    pub fn ad_show(kind: i32, place: &str) { call_v("adShow", "(ILjava/lang/String;)V", |env, m| unsafe { let s = jstr(env, place); (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, kind, s); }) }
    pub fn vibrate(ms: u32) { call_v("vibrate", "(I)V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, ms as i32); }) }
    pub fn music(i: usize, op: i32, v: f32) { call_v("musicCmd", "(IIF)V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, i as i32, op, v as f64); }) }
    pub fn set_orient(o: u8) { call_v("setOrient", "(I)V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, o as i32); }) }
    pub fn quit() { call_v("quit", "()V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m); }) }
    pub fn migrate() { call_v("migrate", "()V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m); }) }
    pub fn paused() -> bool { call_b("isPaused", "()Z", None) }
    pub fn set_banner(on: bool) { call_v("setBanner", "(Z)V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, on as u32); }) }
    pub fn banner_h() -> f32 { unsafe { with(|env| { let m = mid(env, "bannerHeight", "()F"); if m.is_null() { return 0.; } (**env).CallFloatMethod.unwrap()(env, ACTIVITY, m) }) } }
    pub fn density() -> f32 { unsafe { with(|env| { let m = mid(env, "density", "()F"); if m.is_null() { return 2.5; } (**env).CallFloatMethod.unwrap()(env, ACTIVITY, m) }) } }
    pub fn set_fps(f: u32) { call_v("setFps", "(I)V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, f as i32); }) }
    pub fn files_dir() -> String { call_s("filesDir") }
    pub fn set_reminders(plan: &str, ch: &str) { call_v("setReminders", "(Ljava/lang/String;Ljava/lang/String;)V", |env, m| unsafe { let a = jstr(env, plan); let b = jstr(env, ch); (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, a, b); }) }
    pub fn ask_notify() { call_v("askNotify", "()V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m); }) }
    pub fn rate_app() { call_v("rateApp", "()V", |env, m| unsafe { (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m); }) }
    pub fn share_record(text: &str, title: &str) { call_v("shareRecord", "(Ljava/lang/String;Ljava/lang/String;)V", |env, m| unsafe { let a = jstr(env, text); let b = jstr(env, title); (**env).CallVoidMethod.unwrap()(env, ACTIVITY, m, a, b); }) }
    pub fn insets() -> [f32; 4] { let s = call_s("insets"); let v: Vec<f32> = s.split(',').filter_map(|x| x.trim().parse().ok()).collect(); if v.len() == 4 { [v[0], v[1], v[2], v[3]] } else { [0.; 4] } }
    pub fn poll() -> Vec<Ev> {
        let mut out = vec![];
        loop { let s = call_s("adPoll"); if s.is_empty() { break; } if let Some((p, ok)) = s.rsplit_once(':') { out.push(Ev::Ad(p.to_string(), ok == "1")); } }
        loop { let s = call_s("eventPoll"); if s.is_empty() { break; }
            if let Some(r) = s.strip_prefix("music:") { if let Ok(i) = r.parse() { out.push(Ev::MusicDone(i)); } }
            else if let Some(r) = s.strip_prefix("save:") { out.push(Ev::Save(r.to_string())); } }
        out
    }
    pub const NATIVE_MUSIC: bool = true;
}

#[cfg(not(target_os = "android"))]
mod imp {
    use super::Ev;
    use std::sync::Mutex;
    static ADS: Mutex<Vec<(String, f64)>> = Mutex::new(Vec::new());
    /// На компьютере реклама имитируется только при SVET_FAKE_ADS=1 (для проверки интерфейса)
    fn fake() -> bool { std::env::var("SVET_FAKE_ADS").map(|v| v == "1").unwrap_or(false) }
    pub fn ad_ready(_kind: i32) -> bool { fake() }
    pub fn ad_show(kind: i32, place: &str) { let p = if kind == 0 { place.to_string() } else { "inter".into() }; ADS.lock().unwrap().push((p, macroquad::time::get_time() + 1.)); }
    pub fn vibrate(_ms: u32) {}
    pub fn music(_i: usize, _op: i32, _v: f32) {}
    pub fn set_orient(_o: u8) {}
    pub fn quit() { std::process::exit(0); }
    pub fn migrate() {}
    pub fn paused() -> bool { false }
    static BANNER: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    pub fn set_banner(on: bool) { BANNER.store(on, std::sync::atomic::Ordering::Relaxed); }
    /// на ПК баннер имитируется полосой 60 dp при SVET_FAKE_ADS=1
    pub fn banner_h() -> f32 { if fake() && BANNER.load(std::sync::atomic::Ordering::Relaxed) { 60. * density() } else { 0. } }
    pub fn density() -> f32 { std::env::var("SVET_DPI").ok().and_then(|v| v.parse().ok()).unwrap_or(macroquad::window::screen_dpi_scale().max(1.)) }
    pub fn set_fps(_f: u32) {}
    pub fn files_dir() -> String { std::env::var("SVET_DATA").unwrap_or_else(|_| ".".into()) }
    pub fn set_reminders(plan: &str, _ch: &str) { if std::env::var("SVET_REMIND").is_ok() { eprintln!("reminders:\n{plan}"); } }
    pub fn ask_notify() { eprintln!("ask_notify"); }
    pub fn rate_app() { eprintln!("rate_app"); }
    pub fn share_record(text: &str, _title: &str) { eprintln!("share: {text}"); }
    pub fn insets() -> [f32; 4] { [0.; 4] }
    pub fn poll() -> Vec<Ev> {
        let now = macroquad::time::get_time(); let mut a = ADS.lock().unwrap(); let mut out = vec![];
        a.retain(|(p, t)| if *t <= now { out.push(Ev::Ad(p.clone(), fake())); false } else { true }); out
    }
    pub const NATIVE_MUSIC: bool = false;
}
pub use imp::*;

/// Сохранение в файл с атомарной заменой (сбой посреди записи не портит прогресс)
/// Запись сохранения в фоновом потоке: запись на флеш-память бывает медленной (десятки мс) и давала фризы.
/// Последнее состояние кладётся в ячейку; поток пишет самое свежее и засыпает.
static SAVE_SLOT: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);
static SAVE_CV: std::sync::Condvar = std::sync::Condvar::new();
static SAVE_THREAD: std::sync::Once = std::sync::Once::new();
pub fn write_save(json: &str) {
    SAVE_THREAD.call_once(|| { std::thread::spawn(|| loop {
        let job = { let mut g = SAVE_SLOT.lock().unwrap(); while g.is_none() { g = SAVE_CV.wait(g).unwrap(); } g.take() };
        if let Some(j) = job { write_save_now(&j); } }); });
    *SAVE_SLOT.lock().unwrap() = Some(json.to_string()); SAVE_CV.notify_one();
}
pub fn write_save_now(json: &str) {
    let dir = files_dir(); let path = format!("{dir}/save.json"); let tmp = format!("{dir}/save.json.tmp");
    if std::fs::write(&tmp, json).is_ok() { let _ = std::fs::rename(&tmp, &path); }
}
pub fn read_save() -> Option<String> { std::fs::read_to_string(format!("{}/save.json", files_dir())).ok().filter(|s| !s.trim().is_empty()) }
