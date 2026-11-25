//! Приложение: главный цикл, состояния, реклама, сохранение, музыка, джойстик.
use crate::audio::Audio;
use crate::data::{cfg, U_HEAL};
use crate::game::*;
use crate::gfx::Gfx;
use crate::i18n::{self, t, tf};
use crate::platform::{self, Ev};
use crate::render::{self, Rd};
use crate::save::Save;
use crate::ui::Ui;
use macroquad::prelude::*;

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Scr { None, Title, How, Level, Pause, Revive, Over, Shop, Ach, Set, Quest, Best, End, Modes, Wheel, Map, Rate, Card, Xfer, Try }

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum AdCb { Revive, Double, Reroll, Gift, Inter(Next), Boost, RelicReroll, Quest(usize), Wheel, Pet2(usize), Shards }
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Next { Again, Menu }

pub struct Intro { pub t: f32, pub dur: f32, pub full: bool, pub ig: f32, pub revealed: bool }
pub struct End { pub t: f32, pub show: f32, pub shown: bool, pub first: bool }
#[derive(Default)] pub struct Joy { pub id: Option<u64>, pub ox: f32, pub oy: f32, pub jx: f32, pub jy: f32 }
pub struct Ads { pub place: String, pub cb: Option<AdCb>, pub wd: f64, pub wd_len: f64, pub last: f64, pub t0: f64, pub over_n: u32, pub back_t: f64 }
/// Колесо удачи: угол, скорость вращения, выпавший сектор
#[derive(Default, Clone, Copy)] pub struct WheelSt { pub ang: f32, pub spin: f32, pub from: f32, pub to: f32, pub prize: usize, pub shown: f32 }
pub struct Toast { pub title: String, pub sub: String, pub t: f32 }

pub struct App {
    pub gx: Gfx, pub scaler: crate::gfx::Scaler, pub bloom: Option<crate::gfx::Bloom>, pub rd: Rd, pub g: Game, pub ui: Ui, pub au: Audio,
    pub scr: Scr, pub scr_t: f32, pub back_to: Scr, pub intro: Intro, pub end: End, pub joy: Joy, pub ads: Ads,
    pub cards: Vec<usize>, pub cards_t: f32, pub relic_mode: bool, pub path_mode: bool, pub best_sel: Option<(usize, u8)>, pub wheel: WheelSt, pub map_pick: u8, pub modes_h: f32, pub prof: [f64; 3], pub fps_cap: u32, pub slow120: u32, pub warmed: bool, pub share_cap: Option<Rect>, pub rate_pending: bool, pub rem_done: bool, pub relic_rerolled: bool, pub earned: u32, pub rec: bool, pub over_t: f32, pub revive_n: f32,
    pub shop_tab: u8, pub toasts: Vec<Toast>, pub save_t: f32, pub safe: [f32; 4], pub now: f64, pub was_paused: bool,
    pub try_real: Option<Box<Game>> /* 4.8: примерка — настоящая игра отложена, на экране песочница */, pub try_req: Option<(u8, usize)>, pub try_kind: (u8, usize), pub xfer: Option<crate::save::Save> /* 4.8: найденный в коде прогресс, ждёт подтверждения */, pub xfer_msg: String, pub glow_auto_off: bool, pub banner_on: bool, pub glow_slow: f32, pub test: Vec<(f64, String)>, pub bot: bool, pub shot: Option<String>, pub fps_acc: f32, pub fps_n: u32, pub fps: f32, pub slow_t: f32, pub q_auto: u8, pub last_land: bool, pub orient_set: u8, pub fps_set: u32,
}

pub const GIFT_R: u32 = 30; pub const GIFT_MAX: u32 = 8; pub const BOOST_MAX: u32 = 5;

fn track_for(g: &Game) -> Option<usize> {
    match g.state {
        State::Title | State::Intro | State::Menu => Some(0),
        State::Ending => Some(9),
        State::Over => if g.victory { Some(0) } else { Some(8) },
        _ => {
            if g.victory && g.ending_t > 0. { return Some(9); }
            if let Some(b) = g.boss_idx() { use crate::data::K; return Some(match g.en.items[b].kind { K::Boss1 | K::KingCrab => 5, K::Boss2 | K::Queen => 6, _ => 7 }); }
            let z = g.zone; if g.hard { return Some(if z <= 10 { 3 } else { 4 }); } // 4.7: в Кошмаре — тёмные темы глубин
            Some(if z <= 5 { 1 } else if z <= 10 { 2 } else if z <= 15 { 3 } else { 4 })
        }
    }
}

impl App {
    pub async fn new() -> App {
        // экран загрузки
        clear_background(Color::from_rgba(2, 8, 20, 255)); next_frame().await;
        let data = load_string("data.json").await.unwrap_or_default();
        let manifest = load_string("manifest.json").await.unwrap_or_default();
        // сохранение: файл, иначе перенос из прежней (HTML) версии
        let mut s = platform::read_save().map(|j| Save::from_json(&j));
        if s.is_none() {
            platform::migrate(); let t0 = get_time();
            while get_time() - t0 < 2.5 { let mut got = None; for e in platform::poll() { if let Ev::Save(j) = e { got = Some(j); } }
                if let Some(j) = got { if !j.trim().is_empty() { let mut sv = Save::from_json(&j); sv.migrated = true; platform::write_save(&sv.to_json()); s = Some(sv); } break; }
                if cfg!(not(target_os = "android")) { break; }
                clear_background(Color::from_rgba(2, 8, 20, 255)); next_frame().await; }
        }
        let s = s.unwrap_or_default();
        i18n::init(&data, s.set.lang == "en");
        let gx = Gfx::load(&manifest, &mut |_| {}).await;
        let mut au = Audio::new(platform::NATIVE_MUSIC).await; au.sound_on = s.set.sound; au.music_on = s.set.music;
        let mut g = Game::new(s);
        g.quality = match g.s.set.quality.as_str() { "low" => 0, _ => 2 };
        let full = !g.s.seen_intro;
        let now = get_time();
        let mut app = App { gx, scaler: crate::gfx::Scaler::new(), bloom: None, rd: Rd::new(), g, ui: Ui::new(), au, scr: Scr::None, scr_t: 0., back_to: Scr::Title,
            intro: Intro { t: 0., dur: if full { 5.8 } else { 1.5 }, full, ig: if full { 3.7 } else { 0.08 }, revealed: false }, end: End { t: 0., show: 7.4, shown: false, first: false },
            joy: Joy::default(), ads: Ads { place: String::new(), cb: None, wd: 0., wd_len: 0., last: -1e9, t0: now, over_n: 0, back_t: 0. }, cards: vec![], cards_t: 0., relic_mode: false, path_mode: false, best_sel: None, wheel: WheelSt::default(), map_pick: 0, modes_h: 600., prof: [0.; 3], fps_cap: 0, slow120: 0, warmed: false, share_cap: None, rate_pending: false, rem_done: false, relic_rerolled: false, earned: 0, rec: false, over_t: 0., revive_n: 0.,
            shop_tab: 0, toasts: vec![], save_t: 0., safe: [0.; 4], now, was_paused: false, try_real: None, try_req: None, try_kind: (0, 0), xfer: None, xfer_msg: String::new(), glow_auto_off: false, banner_on: false, glow_slow: 0., test: std::env::var("SVET_TEST").unwrap_or_default().split(';').filter_map(|c| c.split_once(':').map(|(t, c)| (t.trim().parse().unwrap_or(0.), c.trim().to_string()))).collect(), bot: false, shot: None, fps_acc: 0., fps_n: 0, fps: 60., slow_t: 0., q_auto: 2, last_land: false, orient_set: 99, fps_set: 0 };
        app.g.state = State::Intro;
        if let Some(crate::flow::DailyMsg::Login(d, r)) = app.g.daily_check() { app.toast_later(tf("loginT", &[&d.to_string()]), format!("+{r} {}", t("pearlsGen"))); }
        app.persist();
        app
    }
    fn toast_later(&mut self, title: String, sub: String) { self.toasts.push(Toast { title, sub, t: -1.8 }); }
    /// 4.8: перенос прогресса — код в буфер обмена / разбор кода из буфера
    pub fn xfer_copy(&mut self) { let en = crate::i18n::is_en(); let code = self.g.s.export_code(); macroquad::miniquad::window::clipboard_set(&code);
        self.xfer_msg = if en { format!("Copied ({} characters). Now paste it into a chat with yourself.", code.len()) } else { format!("Скопировано ({} символов). Теперь вставь его в чат с самим собой.", code.len()) }; }
    pub fn xfer_paste(&mut self) { let en = crate::i18n::is_en(); let clip = macroquad::miniquad::window::clipboard_get().unwrap_or_default();
        match crate::save::Save::import_code(&clip, &self.g.s.set) {
            Ok(n) => { self.xfer = Some(n); self.xfer_msg.clear(); }
            Err(e) => { self.xfer_msg = match (e, en) { ("nocode", true) => "No code in the clipboard — copy the whole code first.".into(), ("nocode", false) => "В буфере обмена нет кода — сначала скопируй код целиком.".into(),
                (_, true) => "The code is damaged — copy it whole, from SB1- to the end.".into(), _ => "Код повреждён — скопируй его целиком, от SB1- до конца.".into() }; } } }
    pub fn toast(&mut self, title: String, sub: String) { self.toasts.push(Toast { title, sub, t: 0. }); }
    pub fn persist(&mut self) { let j = match &self.try_real { Some(r) => r.s.to_json(), None => self.g.s.to_json() }; platform::write_save(&j); self.g.dirty = false; self.save_t = 0.; }
    /// 4.8: примерка — песочница с копией сохранения: искра сама плавает и стреляет, враги гибнут с выбранным эффектом.
    /// Ничего из песочницы не сохраняется; «Назад» возвращает настоящую игру.
    pub fn try_on(&mut self, kind: u8, i: usize) {
        if self.try_real.is_some() { return; }
        let mut s = self.g.s.clone(); s.runs = s.runs.max(999); s.tut = true;
        match kind { 0 => { let id = crate::data::SKINS[i].id; s.skin = id.into(); s.skins.insert(id.into(), 1); }
            1 => { s.trail = i as u8; s.trails.insert(i.to_string(), 1); } 2 => { s.death = i as u8; s.deaths.insert(i.to_string(), 1); } _ => { s.shot = i as u8; s.shots.insert(i.to_string(), 1); } }
        let mut pg = Game::new(s); pg.quality = self.g.quality; pg.start_run(RunMode::Normal); pg.god = true; pg.touch = true;
        self.try_real = Some(Box::new(std::mem::replace(&mut self.g, pg))); self.try_kind = (kind, i); self.joy = Joy::default(); self.show(Scr::Try);
    }
    pub fn try_off(&mut self) { if let Some(r) = self.try_real.take() { self.g = *r; } self.joy = Joy::default(); self.show(Scr::Shop); }
    /// Купить/надеть то, что примеряешь (после возврата в настоящую игру)
    pub fn try_buy(&mut self) { let (k, i) = self.try_kind; self.try_off(); match k { 0 => { self.g.pick_skin(i); } 1 => { self.g.buy_fx(0, i); } 2 => { self.g.buy_fx(1, i); } _ => { self.g.buy_fx(2, i); } } self.persist(); }
    pub fn show(&mut self, s: Scr) { if s != self.scr { self.scr = s; self.scr_t = 0.; self.ui.lock = 0.12; self.ui.reset(); } }
    pub fn click(&mut self) { self.au.play(Sfx::Click); }
    pub fn landscape(&self) -> bool { self.gx.w > self.gx.h * 1.15 }

    // ---------- реклама ----------
    pub fn ad_ready(&self) -> bool { self.ads.cb.is_none() && platform::ad_ready(0) }
    pub fn ad_show(&mut self, place: &str, cb: AdCb) -> bool {
        if self.ads.cb.is_some() || !platform::ad_ready(0) { self.ad_result(cb, false); return false; }
        self.ads.cb = Some(cb); self.ads.place = place.to_string(); self.ads.wd = self.now; self.ads.wd_len = 90.; platform::ad_show(0, place); true
    }
    /// Межстраничная реклама между забегами — бережно: не новичкам, не чаще раза в 4 мин, после каждой второй гибели
    pub fn between(&mut self, next: Next) {
        self.ads.over_n += 1;
        // межстраничная: после забега от минуты, не чаще раза в 3 минуты, не новичкам
        let ok = self.ads.cb.is_none() && self.g.s.runs >= 2 && self.g.run_t >= 60. && self.now - self.ads.last >= 180.
            && self.now - self.ads.t0 >= 60. && platform::ad_ready(1);
        if !ok { self.do_next(next); return; }
        self.ads.cb = Some(AdCb::Inter(next)); self.ads.place = "inter".into(); self.ads.wd = self.now; self.ads.wd_len = 35.; platform::ad_show(1, "inter");
    }
    fn do_next(&mut self, n: Next) { match n { Next::Again => self.start_run(self.g.run_mode), Next::Menu => self.to_title() } }
    fn ad_result(&mut self, cb: AdCb, ok: bool) {
        if ok { self.ads.last = self.now; }
        match cb {
            AdCb::Inter(n) => self.do_next(n),
            AdCb::Revive => { if self.g.state != State::Revive { return; }
                // не досмотрено или сбой — не заканчиваем забег, даём попробовать ещё раз
                if !ok { self.revive_n = self.revive_n.max(5.); self.toasts.push(Toast { title: if crate::i18n::is_en() { "Ad unavailable".into() } else { "Реклама не сработала".into() }, sub: if crate::i18n::is_en() { "Try again".into() } else { "Попробуй ещё раз".into() }, t: 0. }); return; }
                self.g.revive_ad(); self.show(Scr::None); }
            AdCb::Double => { if !ok || self.g.ad_doubled || self.g.state != State::Over { return; } self.g.ad_doubled = true; let e = self.g.last_earned; self.g.s.pearls += e; self.g.s.total_pearls += e as u64;
                self.persist(); self.au.play(Sfx::PickCard); platform::vibrate(30); }
            AdCb::Reroll => { if ok && self.g.ad_rerolls < 2 { self.g.ad_rerolls += 1; self.roll_cards(); } }
            // забег с улучшением на старте (до 5 в день)
            AdCb::Boost => { if !ok || self.g.s.daily.boost >= BOOST_MAX { return; } self.g.s.daily.boost += 1; self.persist(); self.start_run(RunMode::Normal);
                self.g.level_pending += 1; self.g.lv_t = -99.; self.g.level_delay = 0.8; }
            // другие три реликвии
            AdCb::RelicReroll => { if !ok || !self.relic_mode { return; } self.relic_rerolled = true; let c = self.g.roll_relics(); if !c.is_empty() { self.cards = c; self.cards_t = 0.; self.ui.lock = 0.4; } }
            // награда за задание ×2
            AdCb::Quest(k) => { if !ok { return; } let r = self.g.s.daily.quests.get(k).filter(|q| q.done && !q.got).map(|q| q.r);
                if let Some(r) = r { self.g.s.pearls += r; self.g.claim_quest(k); self.persist(); self.toast(t("giftT"), format!("+{} {}", r * 2, t("pearlsGen"))); } }
            // 4.7: второй питомец на следующий забег / ×2 осколков света за забег
            AdCb::Pet2(k) => { if !ok { return; } self.g.s.tok_pet2 = crate::extras::PETS[k].id.into(); self.g.dirty = true; self.persist(); let en = i18n::is_en();
                self.toast(if en { "Second pet".into() } else { "Второй питомец".into() }, format!("{} — {}", crate::extras::pet_txt(k).0, if en { "joins your next run" } else { "поплывёт с тобой в следующем забеге" })); }
            AdCb::Shards => { if !ok || self.g.shards_x2 { return; } self.g.shards_x2 = true; self.g.s.shards += self.g.run_shards; self.g.dirty = true; self.persist(); self.au.play(Sfx::Ach); }
            AdCb::Wheel => { if !ok || self.g.s.daily.wheel_ad >= crate::extras::WHEEL_AD_MAX { return; } self.g.s.daily.wheel_ad += 1; self.wheel_start(); }
            AdCb::Gift => { if !ok || self.g.s.daily.gift >= GIFT_MAX { return; } self.g.s.daily.gift += 1; self.g.s.pearls += GIFT_R; self.g.s.total_pearls += GIFT_R as u64; self.persist();
                self.au.play(Sfx::PickCard); platform::vibrate(30); self.toast(t("giftT"), format!("+{GIFT_R} {}", t("pearlsGen"))); }
        }
    }
    fn ads_tick(&mut self, events: &mut Vec<Ev>) {
        for e in events.drain(..) { match e {
            Ev::Ad(p, ok) => {
                // только ответ на ТЕКУЩИЙ показ (запоздавший ответ межстраничной рекламы раньше «съедал» возрождение)
                if self.ads.cb.is_some() && p == self.ads.place { let cb = self.ads.cb.take().unwrap(); self.ad_result(cb, ok); }
                // награда пришла после того, как сторож уже сдался, — всё равно воскрешаем
                else if ok && p == "revive" && self.g.state == State::Revive { self.ad_result(AdCb::Revive, true); } }
            Ev::MusicDone(i) => self.au.track_done(i), Ev::Save(_) => {} } }
        // страховка: реклама не ответила — игра не должна висеть
        if let Some(cb) = self.ads.cb { if self.now - self.ads.wd > self.ads.wd_len || (self.ads.back_t > 0. && self.now - self.ads.back_t > 10.) { self.ads.cb = None; self.ads.back_t = 0.; self.ad_result(cb, false); } }
    }

    // ---------- переходы ----------
    pub fn start_run(&mut self, mode: RunMode) {
        self.g.start_run(mode); self.show(Scr::None); self.joy = Joy::default(); self.g.touch = true;
    }
    /// Снимок карточки рекорда (область экрана r) → files/share/record.png → системное «Поделиться»
    fn share_capture(&mut self, r: Rect) {
        let img = get_screen_data(); let (iw, ih) = (img.width as i32, img.height as i32); let p = self.gx.px;
        let x0 = ((r.x * p) as i32).clamp(0, iw - 1); let x1 = (((r.x + r.w) * p) as i32).clamp(x0 + 1, iw); let y0 = ((r.y * p) as i32).clamp(0, ih - 1); let y1 = (((r.y + r.h) * p) as i32).clamp(y0 + 1, ih);
        let (cw, chh) = ((x1 - x0) as usize, (y1 - y0) as usize); let mut out = Vec::with_capacity(cw * chh * 4);
        // данные экрана идут снизу вверх (так их отдаёт OpenGL) — берём строки в том же порядке, export_png сам перевернёт
        for row in (ih - y1)..(ih - y0) { let st = (row as usize * iw as usize + x0 as usize) * 4; out.extend_from_slice(&img.bytes[st..st + cw * 4]); }
        for px in out.chunks_mut(4) { px[3] = 255; }
        let dir = format!("{}/share", platform::files_dir()); let _ = std::fs::create_dir_all(&dir);
        Image { bytes: out, width: cw as u16, height: chh as u16 }.export_png(&format!("{dir}/record.png"));
        let en = i18n::is_en(); let d = self.g.zone * 100;
        let txt = if en { format!("I dove {d} m deep in Light of the Abyss! Can you go deeper? https://apps.rustore.ru/app/com.svetbezdny.game") }
                  else { format!("Я нырнул на {d} м в «Свет Бездны»! Сможешь глубже? https://apps.rustore.ru/app/com.svetbezdny.game") };
        platform::share_record(&txt, if en { "Share record" } else { "Поделиться рекордом" });
    }
    pub fn to_title(&mut self) { self.g.state = State::Title; self.show(Scr::Title); }
    pub fn pause(&mut self) { if self.g.state != State::Play || self.g.dying > 0. || self.try_real.is_some() { return; } self.g.state = State::Pause; self.joy = Joy::default(); self.show(Scr::Pause); self.persist(); }
    pub fn resume(&mut self) { self.g.state = State::Play; self.show(Scr::None); self.joy = Joy::default(); }
    pub fn roll_cards(&mut self) { self.cards = self.g.roll_choices(); self.cards_t = 0.; self.ui.lock = 0.48; }
    pub fn open_level_up(&mut self) { self.relic_mode = false; self.path_mode = false; self.g.open_level_up(); self.joy = Joy::default(); self.roll_cards(); self.show(Scr::Level); self.ui.lock = 0.48; }
    /// Выбор реликвии (после босса или из жемчужницы)
    pub fn open_relic(&mut self) {
        self.g.want_relic = false; self.g.relic_pending = self.g.relic_pending.saturating_sub(1);
        let c = self.g.roll_relics(); if c.is_empty() { return; }
        self.g.state = State::LevelUp; self.g.snd(Sfx::Ach); self.joy = Joy::default(); self.relic_mode = true; self.path_mode = false; self.relic_rerolled = false;
        self.cards = c; self.cards_t = 0.; self.show(Scr::Level); self.ui.lock = 0.6;
    }
    /// Запустить вращение: приз выбирается сразу (по весам), колесо докручивается к нему
    pub fn wheel_start(&mut self) {
        let tot: f32 = crate::extras::WHEEL.iter().map(|w| w.2).sum(); let mut r = self.g.rand() * tot; let mut k = 0;
        for (i, w) in crate::extras::WHEEL.iter().enumerate() { r -= w.2; if r <= 0. { k = i; break; } }
        let n = crate::extras::WHEEL.len() as f32; let seg = std::f32::consts::TAU / n;
        // сектор k под стрелкой (сверху): угол колеса = -(k+0.5)·seg − π/2, плюс 5 полных оборотов
        let target = -(k as f32 + 0.5) * seg - std::f32::consts::FRAC_PI_2; let base = self.wheel.ang - self.wheel.ang.rem_euclid(std::f32::consts::TAU);
        self.wheel = WheelSt { ang: self.wheel.ang, spin: 3.6, from: self.wheel.ang, to: base + std::f32::consts::TAU * 6. + target.rem_euclid(std::f32::consts::TAU), prize: k, shown: 0. };
        self.au.play(Sfx::Level);
    }
    pub fn wheel_award(&mut self) {
        let (ty, n, _) = crate::extras::WHEEL[self.wheel.prize]; let en = crate::i18n::is_en();
        match ty { 0 => { self.g.s.pearls += n; self.g.s.total_pearls += n as u64; self.toast(if en { "Wheel of fortune".into() } else { "Колесо удачи".into() }, format!("+{n} {}", t("pearlsGen"))); }
            1 => { self.g.s.tok_relic += 1; self.toast(if en { "Wheel of fortune".into() } else { "Колесо удачи".into() }, if en { "An upgrade at the start of your next run".into() } else { "Улучшение на старте следующего забега".into() }); }
            _ => { self.g.s.tok_reroll += 1; self.toast(if en { "Wheel of fortune".into() } else { "Колесо удачи".into() }, if en { "+1 reroll in your next run".into() } else { "+1 перевыбор в следующем забеге".into() }); } }
        self.au.play(Sfx::Ach); platform::vibrate(40); self.persist();
    }
    /// Развилка путей после босса
    pub fn open_path(&mut self) {
        self.g.want_path = false; self.g.path_pending = false;
        let c = self.g.roll_paths(); self.g.state = State::LevelUp; self.g.snd(Sfx::Level); self.joy = Joy::default();
        self.relic_mode = false; self.path_mode = true; self.cards = c; self.cards_t = 0.; self.show(Scr::Level); self.ui.lock = 0.6;
    }
    pub fn take_card(&mut self, k: usize) {
        let Some(&i) = self.cards.get(k) else { return };
        if self.path_mode { self.path_mode = false; self.g.take_path(i); self.g.state = State::Play; self.show(Scr::None); self.joy = Joy::default(); return; }
        if self.relic_mode { self.relic_mode = false; self.g.take_relic(i); self.g.state = State::Play; self.show(Scr::None); self.joy = Joy::default(); return; }
        if self.g.take_upgrade(i) { self.roll_cards(); } else { self.show(Scr::None); self.joy = Joy::default(); }
        let _ = U_HEAL;
    }
    pub fn game_over(&mut self) {
        if std::env::var("SVET_LOG").is_ok() { eprintln!("RUNEND depth={} lvl={} t={:.0} kills={} hard={} char={}", self.g.zone * 100, self.g.p.level, self.g.run_t, self.g.kills, self.g.hard, self.g.s.ch); }
        let (e, rec) = self.g.game_over(); self.earned = e; self.rec = rec; self.over_t = 0.; self.joy = Joy::default(); self.show(Scr::Over);
        // 4.3: просьба об оценке — после третьего забега, когда пройден первый владыка (и ещё раз через 10 забегов, если «позже»)
        { let s = &mut self.g.s; if !self.bot && ((s.rate == 0 && s.runs >= 3 && s.best_depth >= 500) || (s.rate == 1 && s.runs >= s.rate_at)) { self.rate_pending = true; } }
        // напоминания: разрешение спрашиваем один раз, после второго забега (на Android 13+ это системное окно)
        if !self.bot && !self.g.s.notif_asked && self.g.s.runs >= 2 && self.g.s.set.notify { self.g.s.notif_asked = true; platform::ask_notify(); }
        crate::extras::sync_reminders(&self.g.s); self.persist();
    }
    fn offer_revive(&mut self) -> bool {
        if self.g.ad_revived || self.g.victory || self.bot { return false; }
        self.g.state = State::Revive; self.joy = Joy::default(); self.revive_n = 5.; self.show(Scr::Revive); true
    }

    // ---------- кадр ----------
    pub async fn frame(&mut self) {
        let raw = get_frame_time(); let rdt = raw.clamp(0., 0.05); self.now = get_time();
        let px = platform::density();
        let (vw, vh) = self.gx.frame(px, self.g.cam_x, self.g.cam_y, 0., 0.); self.g.vw = vw; self.g.vh = vh;
        let ins = platform::insets(); self.safe = [ins[0] / px, ins[1] / px, ins[2] / px, ins[3] / px];
        // баннер — только в меню вне забега; кнопки поднимаются над ним
        let menu = matches!(self.g.state, State::Title | State::Menu) && matches!(self.scr, Scr::Title | Scr::Shop | Scr::Ach | Scr::Quest | Scr::Best | Scr::Set | Scr::How | Scr::Modes | Scr::Map | Scr::Xfer);
        if menu != self.banner_on { self.banner_on = menu; platform::set_banner(menu); }
        if menu { let bh = platform::banner_h() / px; if bh > 0. { self.safe[1] = self.safe[1].max(bh + 4.); } }
        self.gx.safe_t = self.safe[0]; self.gx.safe_b = self.safe[1];
        // настройки, которые применяет система
        if self.orient_set != self.g.s.set.orient { self.orient_set = self.g.s.set.orient; platform::set_orient(self.orient_set); }
        { let want = if self.fps_cap > 0 { self.fps_cap.min(self.g.s.set.fps) } else { self.g.s.set.fps }; if self.fps_set != want { self.fps_set = want; platform::set_fps(want); } }
        let land = self.landscape(); if land != self.last_land { self.last_land = land; if self.g.state == State::Play { self.pause(); } } // поворот посреди забега — пауза
        self.ui.begin(px, rdt);
        let mut evs = platform::poll(); self.ads_tick(&mut evs);
        // свернули приложение
        let paused = platform::paused();
        if paused && !self.was_paused { if self.g.state == State::Play { self.pause(); } self.persist(); }
        if !paused && self.was_paused && self.ads.cb.is_some() { self.ads.back_t = self.now; }
        self.was_paused = paused;
        if self.ui.back { self.back(); }
        if !self.test.is_empty() || self.bot || self.try_real.is_some() { self.test_tick(); }

        // ---- логика ----
        let t0 = std::time::Instant::now();
        // тесты: SVET_SPEED=k — k шагов логики за кадр (бот проходит глубины быстрее)
        static STEPS: std::sync::OnceLock<u32> = std::sync::OnceLock::new(); let steps = *STEPS.get_or_init(|| std::env::var("SVET_SPEED").ok().and_then(|v| v.parse::<u32>().ok()).unwrap_or(1).max(1));
        let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| for _ in 0..steps { self.update(rdt); }));
        if res.is_err() { self.fault("update"); }
        self.prof[0] += t0.elapsed().as_secs_f64();
        // события игры
        for s in std::mem::take(&mut self.g.sfx) { self.au.play(s); }
        for v in std::mem::take(&mut self.g.vib) { platform::vibrate(v); }
        for tt in std::mem::take(&mut self.g.toasts) { self.toast(tt.title, tt.sub); }
        // во время забега — не чаще раза в 20 с (и при паузе/сворачивании/конце забега), в меню — сразу
        if self.g.dirty { self.save_t += rdt; if self.save_t > if self.g.state == State::Play { 20. } else { 0.6 } { self.persist(); } }
        self.au.sound_on = self.g.s.set.sound; self.au.music_on = self.g.s.set.music; self.au.vol_sfx = self.g.s.set.vsfx as f32 / 10.; self.au.vol_mus = (self.g.s.set.vmus as f32 / 10.).powf(1.5);
        let tr = track_for(&self.g);
        // 4.8: музыка владыки нагнетается по фазам: быстрее и громче
        { let boss = self.g.state == State::Play && self.g.boss_idx().is_some(); let ph = if boss { self.g.boss_ph } else { 0 };
          let (r, b) = match ph { 0 => (1., 1.), 1 => (1.05, 1.08), _ => (1.1, 1.18) }; self.au.boost += (b - self.au.boost) * (1. - (-rdt * 2.).exp());
          if let Some(t) = tr { self.au.set_rate(t, r); } }
        self.au.tick(tr, rdt, paused).await;
        for (i, op, v) in std::mem::take(&mut self.au.cmds) { platform::music(i, op, v); }

        // ---- отрисовка ----
        let sh = self.g.shake; let (shx, shy) = if sh > 0.3 { (rand::gen_range(-1f32, 1.) * sh, rand::gen_range(-1f32, 1.) * sh) } else { (0., 0.) };
        self.gx.frame(px, self.g.cam_x, self.g.cam_y, shx, shy);
        let t1 = std::time::Instant::now();
        let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.draw(rdt)));
        self.prof[1] += t1.elapsed().as_secs_f64(); self.prof[2] += 1.;
        if res.is_err() { self.fault("draw"); gl_use_default_material(); }
        if !self.rem_done && self.now > 2. { self.rem_done = true; crate::extras::sync_reminders(&self.g.s); }
        if let Some(r) = self.share_cap.take() { self.share_capture(r); }
        if let Some(p) = self.shot.take() { let img = get_screen_data(); let (w, h) = (img.width as usize, img.height as usize);
            let mut img = img; for px in img.bytes.chunks_mut(4) { px[3] = 255; } img.export_png(&p); let _ = (w, h); }
        // частота кадров и автоподстройка качества
        self.fps_acc += raw; self.fps_n += 1; if self.fps_acc >= 1. { let avg = self.fps_acc / self.fps_n as f32; self.fps = 1. / avg; self.fps_acc = 0.; self.fps_n = 0;
            if self.g.s.set.quality == "auto" && self.g.state == State::Play { if avg > 0.024 { self.slow_t += 1.; if self.slow_t >= 3. && self.q_auto > 0 { self.q_auto -= 1; self.slow_t = 0.; } } else { self.slow_t = 0.; } }
            self.g.quality = match self.g.s.set.quality.as_str() { "low" => 0, "high" => 2, _ => self.q_auto };
            self.g.max_part = match self.g.quality { 2 => cfg::MAX_PART_HI, 1 => 420, _ => cfg::MAX_PART_LO }; }
    }
    /// Автотест: команды по времени из SVET_TEST ("2:play;5:shot a.png;...")
    fn test_tick(&mut self) {
        let now = self.now;
        while let Some(i) = self.test.iter().position(|(t, _)| *t <= now) {
            let (_, cmd) = self.test.remove(i); let mut it = cmd.split_whitespace(); let c = it.next().unwrap_or(""); let arg = it.next().unwrap_or("");
            let n: f32 = arg.parse().unwrap_or(1.);
            match c {
                "play" => self.start_run(RunMode::Normal), "daily" => self.start_run(RunMode::Daily),
                "title" => { self.g.state = State::Title; self.intro.revealed = true; self.show(Scr::Title); }
                "shop" => { self.back_to = Scr::Title; self.shop_tab = n as u8; self.show(Scr::Shop); } "ach" => self.show(Scr::Ach), "set" => { self.back_to = Scr::Title; self.show(Scr::Set); } "xfer" => { self.back_to = Scr::Title; self.show(Scr::Xfer); } "clip" => { macroquad::miniquad::window::clipboard_set(&std::fs::read_to_string(arg).unwrap_or_default()); } "xcopy" => { self.xfer_copy(); let _ = std::fs::write(arg, macroquad::miniquad::window::clipboard_get().unwrap_or_default()); } "xpaste" => { self.xfer_paste(); } "try" => { let k: u8 = arg.parse().unwrap_or(0); let i = it.next().and_then(|v| v.parse().ok()).unwrap_or(0); self.try_on(k, i); } "tryoff" => self.try_off(), "wear" => { self.g.wear_outfit(n as usize); } "outfit" => { let k: usize = arg.parse().unwrap_or(0); self.g.s.outfits[k] = crate::extras::outfit_of(&self.g.s); }
                "quest" => self.show(Scr::Quest), "best" => self.show(Scr::Best), "how" => self.show(Scr::How),
                "xp" => self.g.add_xp(n), "zone" => { self.g.zone = n as u32 - 1; self.g.zone_t = cfg::ZONE_TIME; }
                "god" => self.g.god = true, "bot" => self.bot = true, "pause" => self.pause(), "over" => self.game_over(), "lvl" => self.open_level_up(),
                "pearls" => { self.g.s.pearls += n as u32; } "seen" => { for e in crate::data::ET.iter() { self.g.s.seen.insert(e.key.into(), 1); } }
                "ending" => { self.g.zone = 15; self.g.victory = true; self.end.first = self.g.start_ending(); self.end.t = 0.; self.end.shown = false; self.show(Scr::None); }
                "endt" => { self.end.t = n; } "skin" => { let k = n as usize % crate::data::SKINS.len(); self.g.s.skins.insert(crate::data::SKINS[k].id.into(), 1); self.g.pick_skin(k); }
                "spawn" => { let k = crate::data::K_ALL[n as usize % crate::data::K_ALL.len()]; let (x, y) = (self.g.p.x + 160., self.g.p.y - 60.); if let Some(i) = self.g.spawn_enemy(k, x, y, false) { if crate::data::ET[k as usize].boss { self.g.boss = self.g.en.items[i].uid as i32; } } }
                "lang" => { self.g.s.set.lang = arg.into(); i18n::set_en(arg == "en"); }
                "shot" => { self.shot = Some(arg.to_string()); }
                "char" => { let k = n as usize % crate::data::CHARS.len(); self.g.s.ch = crate::data::CHARS[k].id.into(); self.g.compute_stats(); }
                "die" => { self.g.give_up(); }
                "tap" => { if self.scr == Scr::Revive { self.ad_show("revive", AdCb::Revive); } }
                "boost" => { self.ad_show("boost", AdCb::Boost); } "relicad" => { self.ad_show("relic", AdCb::RelicReroll); }
                "addrel" => { let r = n as u8; if !self.g.relics.contains(&r) { self.g.relics.push(r); self.g.compute_stats(); } }
                "modes" => { self.show(Scr::Modes); } "mode" => { let m = [RunMode::Daily, RunMode::Time, RunMode::NoUp, RunMode::Dash][n as usize % 4]; self.start_run(m); }
                "bestsel" => { self.show(Scr::Best); self.best_sel = Some((n as usize % crate::data::K_ALL.len(), 0)); }
                "wheel" => { self.show(Scr::Wheel); } "spin" => { self.wheel_start(); } "shop4" => { self.shop_tab = 4; self.show(Scr::Shop); } "pet" => { let k = n as usize % crate::extras::PETS.len(); self.g.s.pets.insert(crate::extras::PETS[k].id.into(), 3); self.g.s.pet = crate::extras::PETS[k].id.into(); self.g.compute_stats(); }
                "abyss" => { self.g.s.abyss_max = (n as u8).min(20); self.g.s.abyss_sel = (n as u8).min(20); }
                "card" => { self.show(Scr::Card); } "share" => { self.share_cap = Some(crate::screens::card_rect(self)); } "rate" => { self.show(Scr::Rate); } "remind" => { std::env::set_var("SVET_REMIND", "1"); crate::extras::sync_reminders(&self.g.s); }
                "trail" => { let i = n as usize % crate::extras::TRAILS.len(); self.g.s.trails.insert(i.to_string(), 1); self.g.s.trail = i as u8; } "death" => { let i = n as usize % crate::extras::DEATHS.len(); self.g.s.deaths.insert(i.to_string(), 1); self.g.s.death = i as u8; } "scroll" => { self.ui.scroll_set(1, n); }
                "cards" => { self.cards = arg.split(',').filter_map(|id| crate::data::UPG.iter().position(|u| u.id == id)).collect(); self.cards_t = 0.; }
                "wins" => { self.g.s.wins = n as u32; }
                "prof" => { let n = self.prof[2].max(1.); eprintln!("prof update {:.2} ms, draw(cpu) {:.2} ms, frames {}", self.prof[0] / n * 1000., self.prof[1] / n * 1000., n); self.prof = [0.; 3]; }
                "shotc" => { let i = n as usize % crate::extras::SHOTS.len(); self.g.s.shots.insert(i.to_string(), 1); self.g.s.shot = i as u8; }
                "rev" => { self.g.rev_cd = 0.; self.g.rev = 0; let k = n as u8; if k > 0 { self.g.rev = k; self.g.rev_t = 25.; } }
                "portal" => { self.g.portal_zone = 0; self.g.zone_t = 30.; } "room" => { self.g.portal = Some((self.g.p.x + 20., self.g.p.y, 20.)); self.g.room_k = n as u8; }
                "pet2" => { let k = n as usize % crate::extras::PETS.len(); self.g.s.tok_pet2 = crate::extras::PETS[k].id.into(); }
                "adpet2" => { let k = n as usize % crate::extras::PETS.len(); self.ad_show("pet2", AdCb::Pet2(k)); }
                "map" => { self.map_pick = n as u8 % 4; self.show(Scr::Map); } "region" => { let i = n as u8 % 4; self.g.s.regions.insert(i.to_string(), 1); self.g.s.region = i; } "shards" => { self.g.s.shards = n as u32; }
                "path" => { self.g.path_pending = true; }
                "relic" => { self.g.relic_pending += 1; self.g.level_delay = 0.; }
                "elite" => { let k = crate::data::K_ALL[n as usize % crate::data::K_ALL.len()]; for q in 0..6 { let (x, y) = (self.g.p.x - 150. + q as f32 * 60., self.g.p.y - 200.); if let Some(i) = self.g.spawn_enemy(k, x, y, true) { self.g.en.items[i].aff = 1 + q as u8; if q == 0 { self.g.en.items[i].ash = self.g.en.items[i].max_hp * 0.45; } } } }
                "kinds" => { let mut m: std::collections::BTreeMap<String, u32> = Default::default(); for e in self.g.en.iter().filter(|e| !e.dead) { *m.entry(format!("{}{}", e.kind.key(), if e.elite { "*" } else { "" })).or_default() += 1; } eprintln!("kinds {:?}", m); }
                "fps" => { eprintln!("fps {:.1} enemies {} parts {} ebul {} zone {} hz {} boss {}", self.fps, self.g.en.n, self.g.parts.n, self.g.eb.n, self.g.zone, self.g.hazard(), self.g.boss); }
                "up" => { if let Some(i) = crate::data::UPG.iter().position(|u| u.id == arg) { self.g.p.up[i] = it.next().and_then(|v| v.parse().ok()).unwrap_or(1); self.g.compute_stats(); } }
                "quit" => std::process::exit(0),
                _ => {}
            }
        }
        if (self.bot || self.try_real.is_some()) && self.g.state == State::Play { // бот (и примерка): держится подальше от ближайших врагов, кружит по арене
            let (px, py) = (self.g.p.x, self.g.p.y); let (mut fx, mut fy) = (0f32, 0f32);
            for i in 0..self.g.en.n { let e = &self.g.en.items[i]; if e.dead { continue; } let (dx, dy) = (px - e.x, py - e.y); let d2 = (dx * dx + dy * dy).max(100.); if d2 < 300. * 300. { fx += dx / d2 * 900.; fy += dy / d2 * 900.; } }
            for i in 0..self.g.eb.n { let b = &self.g.eb.items[i]; let (dx, dy) = (px - b.x, py - b.y); let d2 = (dx * dx + dy * dy).max(50.); if d2 < 120. * 120. { fx += dx / d2 * 1500.; fy += dy / d2 * 1500.; } }
            let a = self.now as f32 * 0.4; fx += -py * 0.0015 + a.cos() * 0.4; fy += px * 0.0015 + a.sin() * 0.4; let l = (fx * fx + fy * fy).sqrt().max(1e-3); self.g.jx = fx / l; self.g.jy = fy / l;
            if self.g.p.flare >= 100. && self.try_real.is_none() { self.g.flare_q = true; } if self.g.p.dash_cd <= 0. && fx * fx + fy * fy > 30. { self.g.dash_q = true; }
        }
        if self.bot && self.scr == Scr::Level && self.ui.lock <= 0. && self.cards_t > 0.6 { self.take_card(0); }
        if self.bot && self.g.state == State::Revive { self.game_over(); }
    }
    fn fault(&mut self, where_: &str) {
        let g = &mut self.g;
        for p in [&mut g.en.n, &mut g.pb.n, &mut g.eb.n, &mut g.parts.n, &mut g.rings.n, &mut g.texts.n, &mut g.bolts.n, &mut g.picks.n, &mut g.mines.n] { let _ = p; }
        g.en.n = g.en.n.min(g.en.cap()); g.pb.n = g.pb.n.min(g.pb.cap()); g.eb.n = g.eb.n.min(g.eb.cap()); g.parts.n = g.parts.n.min(g.parts.cap());
        g.rings.n = g.rings.n.min(g.rings.cap()); g.texts.n = g.texts.n.min(g.texts.cap()); g.bolts.n = g.bolts.n.min(g.bolts.cap()); g.picks.n = g.picks.n.min(g.picks.cap()); g.mines.n = g.mines.n.min(g.mines.cap());
        let msg = format!("{where_} @{}m", g.zone * 100); if std::env::var("SVET_LOG").is_ok() { eprintln!("FAULT {msg}"); } g.s.err_log.insert(0, msg); g.s.err_log.truncate(5); g.dirty = true;
    }

    fn back(&mut self) {
        match self.scr {
            Scr::None => match self.g.state { State::Play => self.pause(), State::Intro => self.skip_intro(), State::Ending => self.skip_ending(), _ => {} },
            Scr::Pause => self.resume(),
            Scr::Title => { platform::write_save_now(&self.g.s.to_json()); platform::quit(); }
            Scr::Shop | Scr::Set => { let b = self.back_to; self.show(b); }
            Scr::Xfer => { self.xfer = None; self.show(Scr::Set); }
            Scr::Try => self.try_off(),
            Scr::Best if self.best_sel.is_some() => self.best_sel = None,
            Scr::Ach | Scr::Quest | Scr::Best | Scr::How | Scr::Modes => self.show(Scr::Title),
            Scr::Wheel => { if self.wheel.spin <= 0. { self.show(Scr::Title); } }
            Scr::Map | Scr::Rate => self.show(Scr::Title),
            Scr::Card => self.show(Scr::Over),
            Scr::Over => self.between(Next::Menu),
            Scr::Revive => { if self.ads.cb.is_none() { self.game_over(); } }
            _ => {}
        }
        self.click();
    }
    pub fn skip_intro(&mut self) { if self.intro.full && self.intro.t < self.intro.ig - 0.05 { self.intro.t = self.intro.ig - 0.05; } else { self.end_intro(); } }
    fn reveal_title(&mut self) { if self.intro.revealed { return; } self.intro.revealed = true; if !self.g.s.seen_intro { self.g.s.seen_intro = true; self.persist(); } self.show(Scr::Title); }
    fn end_intro(&mut self) { self.reveal_title(); if self.g.state == State::Intro { self.g.state = State::Title; } }
    pub fn skip_ending(&mut self) { if !self.end.shown && self.end.t < self.end.show - 0.3 { self.end.t = self.end.show - 0.3; } }

    fn update(&mut self, rdt: f32) {
        if let Some((k, i)) = self.try_req.take() { self.try_on(k, i); }
        if self.wheel.spin > 0. { self.wheel.spin -= rdt; let k = 1. - (self.wheel.spin / 3.6).max(0.); let e = 1. - (1. - k).powi(4); self.wheel.ang = self.wheel.from + (self.wheel.to - self.wheel.from) * e;
            if self.wheel.spin <= 0. { self.wheel.ang = self.wheel.to; self.wheel.shown = 2.5; self.wheel_award(); } }
        if self.wheel.shown > 0. { self.wheel.shown -= rdt; }
        let g = &mut self.g; self.scr_t += rdt; self.cards_t += rdt;
        for tt in self.toasts.iter_mut() { tt.t += rdt; } self.toasts.retain(|t| t.t < 3.4);
        match g.state {
            State::Play => {
                // ввод: игровые кнопки, затем джойстик
                if self.try_real.is_none() { crate::hud::input(self); } else { let g = &mut self.g; g.want_levelup = false; g.want_path = false; g.want_relic = false; g.toasts.clear(); g.want_ending = false; g.zone_t = 0.;
                    // витрина: вокруг всегда 7–8 слабых врагов, чтобы было видно выстрелы и гибель
                    let alive = (0..g.en.n).filter(|&i| !g.en.items[i].dead).count();
                    if alive < 8 && g.rand() < 0.08 { let a = g.rand() * std::f32::consts::TAU; let d = 230. + g.rand() * 120.; let (x, y) = (g.p.x + a.cos() * d, g.p.y + a.sin() * d);
                        let ks = [crate::data::K::Drifter, crate::data::K::Jelly, crate::data::K::Dart]; let k = ks[(g.rand() * 3.) as usize % 3];
                        if let Some(i) = g.spawn_enemy(k, x, y, false) { let e = &mut g.en.items[i]; e.hp = e.hp.min(14.); e.max_hp = e.hp; e.dmg = 0.; } } }
                let g = &mut self.g;
                let mut dt = rdt;
                if g.hit_stop > 0. { g.hit_stop -= rdt; dt = rdt * 0.06; }
                if g.dying > 0. { g.dying -= rdt; dt = rdt * 0.35; if g.dying <= 0. { g.update_run(dt, rdt); if !self.offer_revive() { self.game_over(); } return; } }
                let g = &mut self.g;
                if g.state == State::Play { g.update_run(dt, rdt); }
                if self.try_real.is_some() { let g = &mut self.g; g.want_levelup = false; g.want_path = false; g.want_relic = false; g.want_ending = false; g.p.xp = 0.; g.boss = -1; } // 4.8.1: в примерке без уровней
                let g = &mut self.g;
                if g.want_over && g.state == State::Play { self.game_over(); return; }
                if g.want_levelup && g.run_mode == RunMode::NoUp && g.state == State::Play { g.level_noup(); }
                let g = &mut self.g;
                if g.want_relic && g.state == State::Play && g.dying <= 0. { self.open_relic(); }
                else if g.want_path && g.state == State::Play && g.dying <= 0. { self.open_path(); }
                else if g.want_levelup && g.state == State::Play && g.dying <= 0. { self.open_level_up(); }
                else if g.want_ending && g.state == State::Play { self.end.first = self.g.start_ending(); self.end.t = 0.; self.end.shown = false; self.joy = Joy::default(); self.show(Scr::None); self.persist(); }
            }
            State::Intro => { g.t += rdt; g.cam_x = (g.t * 0.045).sin() * 420.; g.cam_y = (g.t * 0.031 + 1.3).sin() * 380.;
                self.intro.t += rdt; if self.ui.tap_any() { self.skip_intro(); }
                if self.intro.t >= self.intro.ig + if self.intro.full { 0.55 } else { 0.05 } { self.reveal_title(); }
                if self.intro.t >= self.intro.dur { self.end_intro(); } }
            State::Title | State::Menu => { g.t += rdt; g.cam_x = (g.t * 0.045).sin() * 420.; g.cam_y = (g.t * 0.031 + 1.3).sin() * 380.; }
            State::Ending => { g.t += rdt; self.end.t += rdt; g.update_fx_only(rdt); if !self.end.shown { if self.ui.tap_any() { self.skip_ending(); } if self.end.t >= self.end.show { self.end.shown = true; self.au.play(Sfx::Ach); self.show(Scr::End); } } }
            State::Over => { g.t += rdt; g.update_fx_only(rdt); self.over_t += rdt; }
            State::Revive => { g.t += rdt; if self.ads.cb.is_none() { self.revive_n -= rdt; if self.revive_n <= 0. { self.game_over(); } } }
            State::Pause | State::LevelUp => {}
        }
        let g = &mut self.g;
        g.banner.t += rdt;
        if g.shake > 0. { g.shake *= (-rdt * 9.).exp(); if g.shake < 0.3 { g.shake = 0.; } }
        if g.flash > 0. { g.flash -= rdt * 2.4; } if g.hurt_flash > 0. { g.hurt_flash -= rdt * 2.5; }
    }

    fn draw(&mut self, rdt: f32) {
        let st = self.g.state;
        let intro_dark = st == State::Intro && self.intro.t < self.intro.ig;
        let end_lit = st == State::Ending && self.end.t > 4.15;
        // 3.8: полноэкранная подсветка (рендер в текстуру + размытие) лагала на телефонах — выключена навсегда.
        // «Свечение» в настройках теперь просто усиливает собственный свет существ и снарядов (почти бесплатно).
        let use_bloom = false; self.gx.glow_boost = if self.g.s.set.fx { 1.35 } else { 1. }; self.gx.clock = self.now as f32; self.gx.anim_parts = self.g.quality >= 1;
        if use_bloom { if let Some(b) = self.bloom.as_mut() { b.begin(&mut self.gx); } }
        // 4.6: мир — в уменьшенном разрешении (бюджет пикселей по качеству), интерфейс — потом, чётко
        // 4.6.1: только при «Графика: низкая». На высокой выигрыш съедало полноэкранное копирование и запись/чтение текстуры
        // (мобильные GPU) — стало хуже, чем без него (фризы).
        if self.g.s.set.quality == "low" { self.scaler.begin(&mut self.gx, 0.7e6); }
        if intro_dark { clear_background(Color::from_rgba(0, 2, 7, 255)); }
        else if !end_lit { render::background(&mut self.gx, &mut self.rd, &mut self.g, rdt, !(st == State::Intro && self.intro.t <= self.intro.ig)); }
        else { clear_background(Color::from_rgba(6, 48, 90, 255)); }
        if intro_dark || end_lit {}
        else if matches!(st, State::Title | State::Intro | State::Menu) { let t = self.g.t; render::title_demo(&mut self.gx, &mut self.rd, t, rdt, 1.); }
        else { render::world(&mut self.gx, &mut self.g, rdt); }
        if st == State::Ending { crate::hud::ending(self, rdt); }
        if use_bloom { if let Some(b) = self.bloom.as_mut() { b.end(&mut self.gx, 0.85); } }
        if !intro_dark { render::overlay(&mut self.gx, &self.g); }
        self.scaler.end(&mut self.gx);
        if !intro_dark && self.try_real.is_none() { crate::hud::hud(self); }
        if st == State::Intro { crate::hud::intro(self); }
        crate::screens::draw(self);
        crate::hud::toasts(self);
        if !self.warmed && self.now > 1.5 { self.warmed = true; self.gx.prewarm(); }
        self.gx.set_add(false);
    }
}
