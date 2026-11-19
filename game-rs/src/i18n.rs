//! Тексты RU/EN из assets/data.json (выгружены из веб-версии конвертером tools/export_data.js).
use serde_json::Value;
use std::cell::RefCell;

thread_local! { static L: RefCell<Option<Lang>> = const { RefCell::new(None) }; }

pub struct Lang { pub data: Value, pub en: bool }

pub fn init(json: &str, en: bool) { let data: Value = serde_json::from_str(json).expect("data.json"); L.with(|l| *l.borrow_mut() = Some(Lang { data, en })); }
pub fn set_en(en: bool) { L.with(|l| if let Some(x) = l.borrow_mut().as_mut() { x.en = en; }); }
pub fn is_en() -> bool { L.with(|l| l.borrow().as_ref().map(|x| x.en).unwrap_or(false)) }
fn with<R>(f: impl FnOnce(&Lang) -> R) -> R { L.with(|l| f(l.borrow().as_ref().expect("i18n init"))) }

/// HTML из веб-версии → обычный текст: <br> — перенос строки, остальные теги убираются
pub fn clean(s: &str) -> String {
    let s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("&nbsp;", " ");
    let mut out = String::with_capacity(s.len()); let mut tag = false;
    for ch in s.chars() { match ch { '<' => tag = true, '>' => tag = false, _ if !tag => out.push(ch), _ => {} } }
    out
}
fn ui_val(k: &str) -> Option<Value> { with(|l| { let src = if l.en { &l.data["EN"]["ui"] } else { &l.data["RU"]["ui"] }; src.get(k).cloned() }) }
/// Строка интерфейса
pub fn t(k: &str) -> String {
    match ui_val(k) { Some(Value::String(s)) => clean(&s), Some(Value::Object(o)) => o.get("tpl").and_then(|v| v.as_str()).map(clean).unwrap_or_default(), _ => k.to_string() }
}
/// Строка-шаблон с подстановками {0},{1},{2}
pub fn tf(k: &str, args: &[&str]) -> String {
    let mut s = t(k); for (i, a) in args.iter().enumerate() { s = s.replace(&format!("{{{i}}}"), a); } s
}
/// Пара строк из вложенного массива (например bossDie[i], guardDie[i])
pub fn pair(k: &str, i: usize) -> (String, String) {
    match ui_val(k) { Some(Value::Array(a)) => a.get(i).and_then(|v| v.as_array()).map(|p| (clean(p[0].as_str().unwrap_or("")), clean(p.get(1).and_then(|x| x.as_str()).unwrap_or("")))).unwrap_or_default(), _ => Default::default() }
}
/// Подсказка о новом враге: (заголовок, пояснение)
pub fn foe(kind: &str) -> Option<(String, String)> {
    match ui_val("foe") { Some(Value::Object(o)) => o.get(kind).and_then(|v| v.as_array()).map(|p| (clean(p[0].as_str().unwrap_or("")), clean(p[1].as_str().unwrap_or("")))), _ => None }
}
fn table_pair(tbl: &str, id: &str) -> (String, String) {
    with(|l| { let v = if l.en { &l.data["EN"][tbl][id] } else { &l.data["RU_DATA"][tbl][id] };
        match v { Value::Array(a) => (clean(a.first().and_then(|x| x.as_str()).unwrap_or(id)), clean(a.get(1).and_then(|x| x.as_str()).unwrap_or(""))),
            Value::String(s) => (clean(s), String::new()), _ => (id.to_string(), String::new()) } })
}
pub fn upg(id: &str) -> (String, String) { table_pair("upg", id) }
pub fn chr(id: &str) -> (String, String) { table_pair("chars", id) }
pub fn skin(id: &str) -> String { table_pair("skins", id).0 }
pub fn shop(id: &str) -> (String, String) { table_pair("shop", id) }
pub fn ach(id: &str) -> (String, String) { table_pair("ach", id) }
pub fn boss(id: &str) -> String { table_pair("boss", id).0 }
pub fn zone(i: usize) -> String { with(|l| { let a = if l.en { &l.data["EN"]["zones"] } else { &l.data["RU_DATA"]["zones"] }; a.as_array().map(|v| v[i % v.len()].as_str().unwrap_or("").to_string()).unwrap_or_default() }) }
pub fn ach_reward(id: &str) -> u32 { with(|l| l.data["ACH"].as_array().and_then(|a| a.iter().find(|x| x["id"] == id)).and_then(|x| x["r"].as_u64()).unwrap_or(0) as u32) }
pub fn ach_ids() -> Vec<String> { with(|l| l.data["ACH_IDS"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default()) }
pub fn story() -> Vec<(f32, String)> { match ui_val("story") { Some(Value::Array(a)) => a.iter().filter_map(|p| p.as_array().map(|p| (p[0].as_f64().unwrap_or(0.) as f32, clean(p[1].as_str().unwrap_or(""))))).collect(), _ => vec![] } }
/// Обучение: шаги (на телефоне — версии для пальца)
pub fn tut(i: usize, touch: bool) -> (String, String) {
    let en = is_en();
    let touch_t = [["Drag anywhere on the screen", "Веди пальцем в любом месте экрана"], ["", ""], ["", ""], ["Now tap “DASH”", "Теперь нажми «РЫВОК»"], ["Flare is charged — hit it!", "Вспышка заряжена — жми!"]];
    let (a, b) = with(|l| { let v = if l.en { &l.data["EN"]["tut"][i] } else { &l.data["RUTUT"][i] }; (v[0].as_str().unwrap_or("").to_string(), v[1].as_str().unwrap_or("").to_string()) });
    let tt = touch_t[i][if en { 0 } else { 1 }];
    (if touch && !tt.is_empty() { tt.to_string() } else { a }, b)
}
pub fn talent(i: usize) -> (String, String) { with(|l| { let v = &l.data["TALENTS"][i]; if l.en { (v["en"][0].as_str().unwrap_or("").into(), v["en"][1].as_str().unwrap_or("").into()) } else { (v["name"].as_str().unwrap_or("").into(), v["d"].as_str().unwrap_or("").into()) } }) }
pub fn tal_branch(i: usize) -> String { with(|l| l.data["TAL_BR"][i][if l.en { 1 } else { 0 }].as_str().unwrap_or("").to_string()) }
pub fn mutator(id: &str) -> (String, String) { with(|l| { let v = l.data["MUTS"].as_array().and_then(|a| a.iter().find(|x| x["id"] == id)).cloned().unwrap_or(Value::Null);
    if l.en { (v["en"][0].as_str().unwrap_or("").into(), v["en"][1].as_str().unwrap_or("").into()) } else { (v["name"].as_str().unwrap_or("").into(), v["d"].as_str().unwrap_or("").into()) } }) }
pub fn best(kind: &str) -> (String, String) {
    with(|l| { let i = if l.en { 1 } else { 0 }; let n = l.data["BEST_N"][kind][i].as_str().map(|s| s.to_string()); let d = l.data["BEST"][kind][i].as_str().unwrap_or("").to_string(); (n.unwrap_or_default(), d) })
}
/// Название ежедневного задания
pub fn quest(id: &str, n: u32) -> String {
    let en = is_en();
    match (id, en) {
        ("kills", true) => format!("Defeat {n} enemies"), ("kills", false) => format!("Победи {n} врагов"),
        ("depth", true) => format!("Reach {n} m"), ("depth", false) => format!("Достигни {n} м"),
        ("pearls", true) => format!("Collect {n} pearls"), ("pearls", false) => format!("Собери {n} жемчужин"),
        ("boss", true) => if n > 1 { format!("Defeat a boss ×{n}") } else { "Defeat a boss".into() }, ("boss", false) => if n > 1 { format!("Победи босса ×{n}") } else { "Победи босса".into() },
        ("chest", true) => format!("Open {n} chests"), ("chest", false) => format!("Открой {n} сундуков"),
        ("flare", true) => format!("Use Flare {n} times"), ("flare", false) => format!("Используй Вспышку {n} раз"),
        ("runs", true) => format!("Play {n} runs"), ("runs", false) => format!("Сыграй {n} заплывов"),
        ("combo", true) => format!("Reach a combo of {n}"), _ => format!("Набери комбо {n}"),
    }
}
/// Таблица ежедневных заданий: (id, need[3], reward[3], max-тип)
pub fn qdef() -> Vec<(String, [u32; 3], [u32; 3], bool)> {
    with(|l| l.data["QDEF"].as_object().map(|o| o.iter().map(|(k, v)| {
        let a = |key: &str| { let x = v[key].as_array().unwrap(); [x[0].as_u64().unwrap() as u32, x[1].as_u64().unwrap() as u32, x[2].as_u64().unwrap() as u32] };
        (k.clone(), a("need"), a("r"), v.get("max").is_some()) }).collect()).unwrap_or_default())
}
/// Число с пробелами-разделителями тысяч: 12 345
pub fn fmt_num(n: i64) -> String { let s = n.abs().to_string(); let mut out = String::new(); for (i, ch) in s.chars().enumerate() { if i > 0 && (s.len() - i) % 3 == 0 { out.push('\u{2009}'); } out.push(ch); } if n < 0 { format!("-{out}") } else { out } }
