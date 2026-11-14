"""Премиальный бот для продажи подписки на VPN за Telegram Stars.

Запуск:  python bot.py   (настройки в .env, см. .env.example)
"""

import asyncio
import base64
import datetime
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import time
import types

import qrcode
from urllib.parse import unquote
from telegram import (BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
                      LabeledPrice, MenuButtonWebApp, Update, WebAppInfo)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          Defaults, MessageHandler, PreCheckoutQueryHandler, filters)

import config
import make_banner
import masking
import payments as paymod
import public_proxies
import webshare
from android_app import AppRelease
from auto_proxy import AutoProxy
from db import DAY, DB
from devices import DeviceGuard
from vpn import get_provider

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("vpn-bot")

db = DB(config.DB_PATH)
public_proxies.MAX_MS = int(os.environ.get("AUTO_PROXY_MAX_MS", "1500"))
vpn = get_provider()
auto_mgr = AutoProxy(vpn) if hasattr(vpn, "auto") else None
# Проверка раз в 2 минуты: предупреждение после 3 замеров подряд с превышением (~6 мин),
# отключение — если превышение держится ещё 5 замеров (~10 мин).
guard = DeviceGuard(config.DEVICE_LIMIT, warn_after=3, block_after=5, block_minutes=config.DEVICE_BLOCK_MINUTES)
# Оплата картой (ЮKassa) и криптой (Crypto Pay): ключи задаёт админ командой /pay
pay_cfg = paymod.Settings(os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "payments.json"))
# Своё приложение для Android: только у настоящего VPN (у демо нет подписки для него)
_has_app = bool(config.APP_REPO and hasattr(vpn, "app_link"))
# Бот раздаёт новое приложение Arise (arise-app/, выпуски arise-new-0.1.N). Старое (сборка v2rayNG,
# выпуски v1.0.N) больше не раздаётся, но сервер держит его APK: у кого оно стоит, обновляются изнутри.
legacy_app = AppRelease(config.APP_REPO, config.APP_DIR) if _has_app else None
# Новое приложение (arise-app/): предварительные версии arise-new-0.1.N. Бот его не рассылает,
# но приложение обновляется изнутри через сервер подписок.
android_app = AppRelease(config.APP_REPO, os.path.join(config.APP_DIR, "new"), asset="AriseNew-arm64-v8a.apk",
                         old_assets=(), prefix="arise-new-") if _has_app else None
if android_app:
    vpn.app_releases = {"aurora": legacy_app, "arise": android_app}


def is_admin_sub(sid: int) -> bool:
    """Подписка принадлежит админу: в приложении Arise ей доступны настройки чата."""
    sub = db.get_sub(sid)
    return bool(sub and sub["user_id"] in config.ADMIN_IDS)


def admin_stats() -> dict:
    """Сводка для админа в приложении Arise: подписки, люди, онлайн, деньги."""
    st = db.stats()
    online = guard.last if guard.last_at and time.time() - guard.last_at < 900 else {}
    return {"subs": st["subs"], "people": st["active"], "users_all": st["users"], "new_today": st["new_today"],
            "online": sum(online.values()), "stars_today": st["stars_today"], "stars": st["stars"],
            "rub": st["rub"], "auto": st["auto"]}


if hasattr(vpn, "chat"):
    vpn.chat.is_admin = is_admin_sub
    vpn.chat.stats = admin_stats

    def chat_admin_note(text: str) -> None:
        """Действие из админ-панели приложения — сообщением админам (бот работает в том же цикле)."""
        if STATE.get("bot"):
            asyncio.get_running_loop().create_task(
                send_admins(STATE["bot"], f"👑 Админ-панель приложения: {esc(text)}"))
    vpn.chat.on_admin = chat_admin_note
esc = html.escape

CONFETTI = "5046509860389126442"   # встроенный эффект Telegram «🎉»
MONTH = 2592000                    # Telegram Stars списывает подписку раз в 30 дней
STATE: dict = {"username": ""}     # заполняется при запуске
STARTED = time.time()
KIND_NAMES = {"buy": "покупка", "ext": "продление", "auto": "автопродление",
              "renew": "автосписание", "gift": "подарок"}


def B(text: str, data: str | None = None, url: str | None = None,
      webapp: str | None = None) -> InlineKeyboardButton:
    if webapp:
        return InlineKeyboardButton(text, web_app=WebAppInfo(webapp))
    return InlineKeyboardButton(text, url=url) if url else InlineKeyboardButton(text, callback_data=data)


def KB(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows])


BACK = B("‹ Главное меню", "menu")


# ---------------------------------------------------------------- форматирование

def fmt_date(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y")


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def plural_days(n: int) -> str:
    return plural(n, "день", "дня", "дней")


def plural_hours(n: int) -> str:
    return plural_days(n // 24) if n % 24 == 0 else plural(n, "час", "часа", "часов")


def plural_dev(n: int) -> str:
    return plural(n, "устройство", "устройства", "устройств")


def bullets(items) -> str:
    return "\n".join(f"◆ {x}" for x in items)


def fmt_bytes(n: float) -> str:
    n = float(n or 0)
    if n >= 2**30:
        return f"{n / 2**30:.1f} ГБ"
    return f"{n / 2**20:.0f} МБ"


# ---------------------------------------------------------------- цены и персональные скидки

def offer_pct(uid: int | None) -> int:
    o = db.get_offer(uid) if uid else None
    return o["percent"] if o else 0


def price(uid: int | None, plan: str, dev: int, once: bool = True) -> int:
    """Цена для этого гостя. Персональная скидка действует только на разовую оплату:
    автопродление списывало бы сниженную цену каждый месяц."""
    full = config.plan_price(plan, dev)
    pct = offer_pct(uid) if once and plan != "test" else 0
    return max(1, round(full * (100 - pct) / 100)) if pct else full


def price_tag(uid: int | None, plan: str, dev: int) -> str:
    """«89 ⭐» или «89 ⭐ вместо 99» при скидке."""
    p, full = price(uid, plan, dev), config.plan_price(plan, dev)
    return f"{p} ⭐" + (f" вместо {full}" if p != full else "")


def offer_line(uid: int | None) -> str:
    o = db.get_offer(uid) if uid else None
    if not o:
        return ""
    return (f"\n🎁 <b>Ваша скидка {o['percent']}%</b> на разовую оплату, до "
            f"{datetime.datetime.fromtimestamp(o['until']).strftime('%d.%m %H:%M')}")


def sub_active(sub) -> bool:
    return bool(sub) and sub["expires_at"] > time.time()


def days_left(sub) -> int:
    return max(0, int((sub["expires_at"] - time.time() + DAY - 1) // DAY))


def user_active(user_id: int) -> bool:
    return bool(db.active_subs(user_id))


def status_line(user_id: int) -> str:
    act = db.active_subs(user_id)
    if not act:
        return "◇ Статус: <i>доступ не активирован</i>"
    if len(act) == 1:
        s = act[0]
        return (f"◆ Статус: <b>Premium</b>\n"
                f"◆ Действует до <b>{fmt_date(s['expires_at'])}</b> · ещё {plural_days(days_left(s))}")
    return (f"◆ Статус: <b>Premium</b> · подписок: {len(act)}\n"
            f"◆ Самая долгая до <b>{fmt_date(act[0]['expires_at'])}</b>")


def demo_note() -> str:
    return ("\n\n<i>Демо-режим: сервер ещё не подключён, ключ пока не работает.</i>"
            if vpn.is_demo else "")


def can_trial(row) -> bool:
    return (config.TRIAL_DAYS > 0 and not row["trial_used"] and row["paid_stars"] == 0
            and not db.user_subs(row["id"]))


def ref_condition() -> str:
    return "запустит бота по вашей ссылке" if config.REF_ON_JOIN else "оформит доступ"


def location_names() -> list[str]:
    if not getattr(vpn, "xray_enabled", True):
        # Без Xray гостю доступны страна сервера и страны, у которых есть свой сервер Hysteria.
        return [l["name"] for l in vpn.locations
                if l is vpn.direct_location() or (vpn.hy2_loc_port(l) and not l.get("down"))]
    return [l["name"] for l in getattr(vpn, "locations", [])]


def channel_link() -> str:
    return f"https://t.me/{config.CHANNEL.lstrip('@')}"


def share_url(link: str, text: str = "") -> str:
    from urllib.parse import quote
    return f"https://t.me/share/url?url={quote(link, safe='')}" + (f"&text={quote(text)}" if text else "")


# ---------------------------------------------------------------- экраны

def main_text(row) -> str:
    name = esc(row["first_name"] or "Гость")
    feats = list(config.FEATURES)  # список стран не показываем: он длинный и меняется
    return (f"<b>{name}, добро пожаловать.</b>\n"
            f"<i>{esc(config.TAGLINE)}.</i>\n\n"
            f"<blockquote>{bullets(esc(f) for f in feats)}</blockquote>\n\n"
            f"{status_line(row['id'])}")


def main_kb(row) -> InlineKeyboardMarkup:
    uid = row["id"]
    pct = offer_pct(uid)
    label = "◆ Продлить доступ" if user_active(uid) else "◆ Оформить доступ"
    rows = [[B(label + (f" · −{pct}%" if pct else ""), "plans")]]
    if miniapp_base():
        rows.append([B("✨ Открыть приложение", webapp=miniapp_url(row))])
    if can_trial(row):
        rows.append([B(f"✦ {plural_days(config.TRIAL_DAYS).capitalize()} бесплатно", "trial")])
    rows += [
        [B("🗝 Мои подписки", "subs"), B("📲 Подключение", "howto")],
        *([[B(f"📱 Приложение {config.BRAND} для Android", "apk")]] if android_app else []),
        [B("👤 Профиль", "profile"), B(f"🎁 +{plural_days(config.REF_BONUS_DAYS)} за друга", "ref")],
        [B("🎀 Подарить доступ", "gift"), B("🎟 Промокод", "promo")],
    ]
    if config.CHANNEL and not row["channel_bonus"]:
        rows.append([B(f"📣 +{plural_days(config.CHANNEL_BONUS_DAYS)} за подписку на канал", "ch")])
    rows.append([B("🛎 Консьерж", "support")])
    return InlineKeyboardMarkup(rows)


def plan_discount(days: int, price: int) -> int:
    base = config.PLANS["m1"][2] if "m1" in config.PLANS else price
    full = base * days / 30
    return max(0, round((1 - price / full) * 100)) if full else 0


def plan_mark(key: str) -> str:
    keys = list(config.PLANS)
    return "👑" if key == keys[-1] else ("◇" if key == keys[0] else "◆")


def find_plan(plan: str, user_id: int):
    """Тариф по ключу. Тестовый тариф существует только для админов."""
    if plan == "test":
        return config.TEST_PLAN if user_id in config.ADMIN_IDS else None
    return config.PLANS.get(plan)


def plans_text(target=None, uid: int | None = None) -> str:
    uid = target["user_id"] if target else uid
    lines = []
    for k, (name, days, base) in config.PLANS.items():
        d = plan_discount(days, base)
        tail = f" · <i>выгода {d}%</i>" if d >= 3 else ""
        lines.append(f"{plan_mark(k)} <b>{esc(name)}</b> · от {price_tag(uid, k, min(config.DEVICE_OPTIONS))}{tail}")
    head = (f"<b>Продление «{esc(target['name'])}»</b>\n<i>{plural_dev(target['devices'])}. "
            "Выберите срок.</i>" if target else
            "<b>Выберите тариф</b>\n<i>Чем дольше срок, тем выгоднее.</i>")
    auto = ("\n◆ На месяц можно включить автопродление" if config.AUTO_RENEW and
            any(d == 30 for _, d, _ in config.PLANS.values()) else "")
    return (f"{head}\n\n<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "◆ Цена зависит от числа устройств\n"
            "◆ Оплата звёздами Telegram прямо в чате" + auto + offer_line(uid))


def plans_kb(target=None, uid: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for k, (name, days, base) in config.PLANS.items():
        if target:
            p = price(target["user_id"], k, target["devices"])
            rows.append([B(f"{plan_mark(k)} {name} — {p} ⭐", f"bt:{k}:{target['id']}")])
        else:
            p = price(uid, k, min(config.DEVICE_OPTIONS))
            rows.append([B(f"{plan_mark(k)} {name} — от {p} ⭐", f"buy:{k}")])
    rows.append([B("‹ Подписка", f"sub:{target['id']}") if target else BACK])
    return InlineKeyboardMarkup(rows)


def devices_text(plan: str, gift: bool, uid: int | None = None) -> str:
    name = config.PLANS[plan][0]
    what = "Подарок" if gift else "Новая подписка"
    who_pays = None if gift else uid
    lines = [f"◆ {plural_dev(n)} · {price_tag(who_pays, plan, n)}" for n in config.DEVICE_OPTIONS]
    return (f"<b>{what} · {esc(name)}</b>\n<i>Сколько устройств подключить?</i>\n\n"
            f"<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "Одна подписка работает на выбранном числе устройств одновременно."
            + ("" if gift else offer_line(uid)))


def devices_kb(plan: str, gift: bool, uid: int | None = None) -> InlineKeyboardMarkup:
    pref = "bg" if gift else "bn"
    rows = [[B(f"{plural_dev(n)} — {price(None if gift else uid, plan, n)} ⭐", f"{pref}:{plan}:{n}")]
            for n in config.DEVICE_OPTIONS]
    rows.append([B("‹ Тарифы", "gift" if gift else "plans")])
    return InlineKeyboardMarkup(rows)


def upgrade_base() -> str:
    """Тариф, по которому считается доплата за устройства: месячный, а если его нет — первый."""
    return next((k for k, (_, d, _) in config.PLANS.items() if d == 30), next(iter(config.PLANS)))


def upgrade_price(sub, devices: int, now: float | None = None) -> int:
    """Доплата за переход на большее число устройств до конца срока подписки:
    разница цены тарифа за оставшиеся дни, не меньше 1 звезды."""
    plan = upgrade_base()
    days = config.PLANS[plan][1]
    per_day = (config.plan_price(plan, devices) - config.plan_price(plan, sub["devices"])) / days
    left = max(0.0, sub["expires_at"] - (now or time.time())) / DAY
    return max(1, int(per_day * left + 0.999))


def can_upgrade(s) -> bool:
    # С автопродлением нельзя: ежемесячное списание осталось бы по старой цене.
    return bool(sub_active(s) and not s["auto_active"] and any(n > s["devices"] for n in config.DEVICE_OPTIONS))


def upgrade_text(s) -> str:
    lines = [f"◆ {plural_dev(n)} · доплата {upgrade_price(s, n)} ⭐" for n in config.DEVICE_OPTIONS
             if n > s["devices"]]
    return (f"<b>Устройства в «{esc(s['name'])}»</b>\n<i>Сейчас: {plural_dev(s['devices'])}, "
            f"ещё {plural_days(days_left(s))}.</i>\n\n<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "Доплата только за оставшиеся дни. Ключ остаётся тем же, новые устройства подключаются сразу.")


def upgrade_kb(s) -> InlineKeyboardMarkup:
    rows = [[B(f"{plural_dev(n)} — {upgrade_price(s, n)} ⭐", f"upd:{s['id']}:{n}")]
            for n in config.DEVICE_OPTIONS if n > s["devices"]]
    rows.append([B("‹ Подписка", f"sub:{s['id']}")])
    return InlineKeyboardMarkup(rows)


APPS = {
    "android": ("🤖 Android", "Happ или v2rayNG", "из Google Play"),
    "ios": ("🍏 iPhone и iPad", "Happ или Streisand", "из App Store"),
    "windows": ("🪟 Windows", "Happ или Hiddify", "с официального сайта"),
    "mac": ("💻 macOS", "Happ или Hiddify", "из App Store"),
    "tv": ("📺 Телевизор", "Happ", "из Google Play на телевизоре (Android TV)"),
}
# Где скачать приложения: кнопки под инструкцией
APP_LINKS = {
    "android": [("Happ", "https://play.google.com/store/apps/details?id=com.happproxy"),
                ("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest")],
    "ios": [("Happ", "https://apps.apple.com/app/happ-proxy-utility/id6504287215"),
            ("Streisand", "https://apps.apple.com/app/streisand/id6450534064")],
    "windows": [("Happ", "https://www.happ.su/"),
                ("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest")],
    "mac": [("Happ", "https://apps.apple.com/app/happ-proxy-utility/id6504287215"),
            ("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest")],
    "tv": [("Happ", "https://play.google.com/store/apps/details?id=com.happproxy")],
}

AFTER = ("\n\n<b>Какой сервер выбрать</b>\n"
         "◆ <b>🚀 Лучший сервер</b> — сам выбирает самое быстрое подключение. Начните с него.\n"
         "◆ <b>Страна</b> — если нужен сайт или сервис конкретной страны.\n"
         "◆ <b>🎮 Игры</b> — для игр: без блокировки рекламы, российские серверы напрямую.\n\n"
         "Банки, Госуслуги и российские сайты сами идут мимо VPN — их не нужно выключать.")


def howto_text(platform: str) -> str:
    title, apps, store = APPS[platform]
    one_click = "нажмите «📲 Подключить в один клик», затем кнопку своего приложения"
    if platform == "android" and android_app:
        return (f"<b>{title}</b>\n\n"
                f"<b>Лучше всего — наше приложение {esc(config.BRAND)}</b>: настроено под наши серверы, "
                "само выбирает быстрый, держит соединение и быстрее открывает страницы.\n"
                "<blockquote>1. Нажмите «📥 Скачать приложение» ниже и установите файл "
                "(телефон спросит разрешение на установку — разрешите).\n"
                f"2. Откройте «🗝 Мои подписки», выберите подписку и {one_click}.\n"
                "3. Нажмите большую кнопку подключения.</blockquote>\n"
                "<i>Google Play может предупредить, что приложение не из магазина: нажмите «Всё равно "
                "установить». Чтобы не спрашивал: Google Play → значок профиля → «Play Защита» → ⚙️ → "
                "выключить проверку приложений.</i>\n\n"
                f"<b>Или {esc(apps)}</b> {esc(store)}: те же шаги, только на втором шаге выберите своё "
                "приложение." + AFTER)
    return (f"<b>{title}</b>\n\n"
            f"<blockquote>1. Установите {esc(apps)} {esc(store)} — кнопки ниже.\n"
            f"2. Откройте «🗝 Мои подписки», выберите подписку и {one_click}.\n"
            "   Не открылось? Нажмите на ссылку подписки (она скопируется), в приложении «+» → "
            "«Из буфера обмена».\n"
            "3. Выберите «🚀 Лучший сервер» и включите VPN.</blockquote>"
            + ("\n\nНа телевизоре проще всего открыть этого бота в Telegram для ТВ и нажать "
               "«📲 Подключить в один клик». Или в Happ на телевизоре «+» → ввести ссылку подписки вручную."
               if platform == "tv" else "")
            + AFTER)


def fix_text() -> str:
    steps = ["Обновите подписку в приложении: потяните список вниз или нажмите «Обновить».",
             "Отключитесь и подключитесь заново.",
             "Выберите «🚀 Лучший сервер»: он сам переключится на рабочее подключение."]
    if len(location_names()) > 1:
        steps.append("Выберите другую страну в списке.")
    if getattr(vpn, "hy2", None) and getattr(vpn, "xray_enabled", False):
        steps.append("Выберите в списке пункт с пометкой «· Hysteria», а если не помогло, «· Hysteria 2»: "
                     "они идут по UDP и проходят там, где обычное подключение режется.")
    if getattr(vpn, "bs_on", None) and vpn.bs_on():
        steps.append("На мобильном интернете ничего не открывается? Похоже на белые списки: выберите "
                     "«· обход БС», потом «· обход БС 2» и «3» — у операторов разные списки.")
    if getattr(vpn, "xhttp_on", False):
        steps.append("Выберите в списке тот же сервер с пометкой «· запасной»: "
                     "у него другой вид подключения, который оператор режет реже.")
    bridges = [b["name"] for b in (vpn.visible_bridges() if hasattr(vpn, "visible_bridges") else [])]
    if bridges:
        steps.append(f"Если мобильный интернет ограничен (белые списки), выберите «{bridges[0]}».")
    steps += ["Переключитесь между Wi-Fi и мобильным интернетом: так станет ясно, в какой сети проблема.",
              "Проверьте в «Мои подписки», что срок не закончился.",
              "Удалите профиль в приложении и добавьте ключ заново."]
    body = "\n".join(f"{i}. {esc(t)}" for i, t in enumerate(steps, 1))
    return ("<b>VPN не работает?</b>\n<i>Попробуйте по порядку, обычно хватает первых шагов.</i>\n\n"
            f"<blockquote>{body}</blockquote>\n\n"
            "Не помогло? Напишите консьержу: укажите устройство, оператора и что именно не открывается.")


def sub_line(s) -> str:
    st = f"до {fmt_date(s['expires_at'])}" if sub_active(s) else "<i>истекла</i>"
    auto = " · 🔁" if s["auto_active"] and sub_active(s) else ""
    mark = "◆" if sub_active(s) else "◇"
    return f"{mark} <b>{esc(s['name'])}</b> · {plural_dev(s['devices'])} · {st}{auto}"


def subs_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    subs = db.user_subs(user_id)[-8:]
    if not subs:
        row = db.get_user(user_id)
        kb = [[B("◆ Оформить доступ", "plans")]]
        if can_trial(row):
            kb.append([B("✦ Попробовать бесплатно", "trial")])
        kb.append([BACK])
        return ("<b>Мои подписки</b>\n\nПодписок пока нет. Оформите доступ или возьмите пробный период, "
                "и ваш персональный ключ появится здесь.", InlineKeyboardMarkup(kb))
    text = ("<b>Мои подписки</b>\n<i>Нажмите на подписку, чтобы открыть ключ.</i>\n\n"
            + "\n".join(sub_line(s) for s in subs))
    rows = [[B(f"{'🗝' if sub_active(s) else '◇'} {s['name']}", f"sub:{s['id']}")] for s in subs]
    rows.append([B("➕ Новая подписка", "plans"), BACK])
    return text, InlineKeyboardMarkup(rows)


def sub_text(s) -> str:
    head = f"<b>{esc(s['name'])}</b>\n<i>{plural_dev(s['devices'])}</i>\n\n"
    if not sub_active(s):
        return head + "◇ Срок подписки закончился. Продлите, и ключ снова заработает."
    many = len(location_names()) > 1 or bool(getattr(vpn, "hy2", None))
    auto = "\n◆ Автопродление включено: звёзды спишутся сами раз в месяц" if s["auto_active"] else ""
    used = (s["up_bytes"] or 0) + (s["down_bytes"] or 0)
    traffic = f"\n◆ Трафик: {fmt_bytes(used)}" if not vpn.is_demo and used else ""
    paused = ("\n⛔ <b>Временно отключена</b>: подключено больше устройств, чем в подписке"
              if getattr(vpn, "is_suspended", None) and vpn.is_suspended(s["id"]) else "")
    return (head + f"<code>{esc(s['vpn_key'] or '')}</code>\n\n"
            + ("<i>Нажмите на ссылку, чтобы скопировать. В ней сразу все страны и способы подключения.</i>\n"
               if many else "<i>Нажмите на ключ, чтобы скопировать.</i>\n")
            + f"◆ Действует до <b>{fmt_date(s['expires_at'])}</b> · ещё {plural_days(days_left(s))}"
            + traffic + auto + paused + demo_note())


def sub_kb(s) -> InlineKeyboardMarkup:
    rows = []
    if sub_active(s):
        if hasattr(vpn, "app_link"):
            rows.append([B("📲 Подключить в один клик", url=vpn.app_link(s["id"]))])
        rows.append([B("📖 Инструкция", "howto")])
    rows.append([B("◆ Продлить", f"ext:{s['id']}"), B("✏️ Переименовать", f"ren:{s['id']}")])
    if sub_active(s) and hasattr(vpn, "reset_key"):
        # одна кнопка: внутри и список устройств, и «➕ Добавить устройства»
        rows.append([B("📱 Устройства" + (" · ➕ добавить" if can_upgrade(s) else ""), f"dev:{s['id']}")])
    elif can_upgrade(s):
        rows.append([B("➕ Добавить устройства", f"up:{s['id']}")])
    if s["auto_active"] and sub_active(s):
        rows.append([B("🔁 Отключить автопродление", f"noauto:{s['id']}")])
    if sub_active(s):
        rows.append([B("🛠 Не работает?", "fix")])
    rows.append([B("‹ Мои подписки", "subs")])
    return InlineKeyboardMarkup(rows)


def miniapp_base() -> str:
    """Своё мини-приложение с сервера подписок, иначе адрес из MINIAPP_URL (GitHub Pages)."""
    own = vpn.miniapp_url() if hasattr(vpn, "miniapp_url") else ""
    return own or config.MINIAPP_URL


def miniapp_url(row) -> str:
    """Адрес мини-приложения с данными этого гостя после #d=."""
    plans = [{"id": k, "name": n, "days": d, "price": pr, "disc": plan_discount(d, pr),
              "rub": pay_cfg.rub(config.plan_price(k, 1)) if pay_cfg.any_on() else 0}
             for k, (n, d, pr) in config.PLANS.items()]
    subs = []
    for s in db.user_subs(row["id"])[-8:]:
        act = sub_active(s)
        subs.append({"n": s["name"], "d": s["devices"], "e": int(s["expires_at"]) if act else 0,
                     "k": (s["vpn_key"] or "") if act else "", "a": bool(s["auto_active"] and act),
                     "al": vpn.app_link(s["id"]) if act and android_app else "",
                     "up": bool(act and can_upgrade(s))})
    data = {
        "b": config.BRAND, "tg": config.TAGLINE, "n": row["first_name"] or "",
        "e": max((s["e"] for s in subs), default=0),
        "subs": subs, "tr": can_trial(row), "td": config.TRIAL_DAYS, "dm": vpn.is_demo,
        "bu": STATE["username"], "s": config.SUPPORT,
        "rf": f"https://t.me/{STATE['username']}?start=ref_{row['id']}" if STATE["username"] else "",
        "rb": config.REF_BONUS_DAYS, "rj": config.REF_ON_JOIN,
        "rc": db.referral_count(row["id"]), "p": plans, "loc": location_names(),
        # способы оплаты: s — звёзды, y — карта/СБП (ЮKassa), c — крипта
        "pm": "s" + ("y" if pay_cfg.yookassa else "") + ("c" if pay_cfg.crypto else ""),
        "app": bool(android_app),
    }
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return miniapp_base() + "#d=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def refresh_menu(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Кнопка «Приложение» в меню чата гостя со свежими данными."""
    if not miniapp_base():
        return
    row = db.get_user(user_id)
    if not row:
        return
    try:
        await context.bot.set_chat_menu_button(
            chat_id=user_id, menu_button=MenuButtonWebApp("Приложение", WebAppInfo(miniapp_url(row))))
    except TelegramError as e:
        log.warning("кнопка меню для %s: %s", user_id, e)


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
               kb: InlineKeyboardMarkup, banner: str = "main", effect: str | None = None) -> None:
    """Экран бота: баннер раздела + текст + кнопки. Если можно, меняет текущее
    сообщение на месте, чтобы чат оставался чистым."""
    bd = context.bot_data
    ids, uids = bd.setdefault("banner_ids", {}), bd.setdefault("banner_uids", {})
    q = update.callback_query

    def remember(msg) -> None:
        if msg is not True and getattr(msg, "photo", None):
            ids[banner] = msg.photo[-1].file_id
            uids[msg.photo[-1].file_unique_id] = banner

    if q and q.message and q.message.photo and q.message.photo[-1].file_unique_id in uids:
        try:
            if uids[q.message.photo[-1].file_unique_id] == banner:
                await q.edit_message_caption(caption=text, reply_markup=kb)
            else:
                media = InputMediaPhoto(ids.get(banner) or bd["banners"][banner], caption=text,
                                        parse_mode=ParseMode.HTML)
                remember(await q.edit_message_media(media=media, reply_markup=kb))
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            log.warning("не удалось изменить экран, отправляю новый: %s", e)

    photo = ids.get(banner) or bd["banners"][banner]
    chat = update.effective_chat.id
    try:
        msg = await context.bot.send_photo(chat, photo, caption=text, reply_markup=kb,
                                           message_effect_id=effect)
    except BadRequest:
        if not effect:
            raise
        msg = await context.bot.send_photo(chat, photo, caption=text, reply_markup=kb)
    remember(msg)


def current_user(update: Update):
    u = update.effective_user
    row, _ = db.touch_user(u.id, u.username, u.first_name)
    return row


async def issue_key(sub_id: int):
    sub = db.get_sub(sub_id)
    db.set_key(sub_id, await vpn.issue(sub_id, sub["expires_at"], sub["devices"]), True)
    return db.get_sub(sub_id)


async def grant_days(user_id: int, days: int):
    """Бонусные дни: в основную подписку гостя, а если подписок нет — в новую."""
    sub = db.primary_sub(user_id) or db.create_sub(user_id, 1)
    db.extend_sub(sub["id"], days)
    return await issue_key(sub["id"])


async def send_admins(bot, text: str) -> None:
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except TelegramError:
            pass


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    await send_admins(context.bot, text)


def who(user) -> str:
    """@ник или имя: для строки из базы и для объекта Telegram."""
    if isinstance(user, (dict, sqlite3.Row)):
        uname, first, uid = user["username"], user["first_name"], user["id"]
    else:
        uname, first, uid = user.username, user.first_name, user.id
    return f"@{esc(uname)}" if uname else esc(first or str(uid))


# ---------------------------------------------------------------- команды

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    arg = context.args[0] if context.args else ""
    ref = None
    if arg.startswith("ref_"):
        try:
            ref = int(arg[4:])
        except ValueError:
            ref = None
    row, is_new = db.touch_user(u.id, u.username, u.first_name, ref)
    if is_new and row["referrer_id"]:
        if config.REF_ON_JOIN:
            sub = await grant_days(row["referrer_id"], config.REF_BONUS_DAYS)
            await refresh_menu(context, row["referrer_id"])
            note = (f"🎁 По вашей ссылке присоединился друг. Вам начислено "
                    f"<b>+{plural_days(config.REF_BONUS_DAYS)}</b>.\n"
                    f"◆ «{esc(sub['name'])}» действует до <b>{fmt_date(sub['expires_at'])}</b>.")
        else:
            note = (f"🎁 По вашей ссылке присоединился друг. Когда он оформит доступ, "
                    f"вы получите <b>+{plural_days(config.REF_BONUS_DAYS)}</b>.")
        try:
            await context.bot.send_message(row["referrer_id"], note)
        except TelegramError:
            pass
    context.user_data.clear()
    await refresh_menu(context, u.id)

    if arg == "trial":  # из мини-приложения
        if can_trial(row):
            await do_trial(update, context, row)
            return
        await update.message.reply_text("Пробный период уже использован.")
    elif arg == "terms":
        await terms(update, context)
        return
    elif arg == "plans":
        await show(update, context, plans_text(uid=u.id), plans_kb(uid=u.id), banner="plans")
        return
    elif arg.startswith("buy_") and arg[4:] in config.PLANS:
        await choose_target(update, context, arg[4:])
        return
    elif arg.startswith("gift_"):
        await redeem(update, context, arg[5:])
        return
    elif arg.startswith("promo_"):  # ссылка-промокод из /addpromo
        await redeem(update, context, arg[6:])
        return
    elif arg == "app" and android_app:  # «Скачать приложение» в мини-приложении
        await send_app(update, context)
        return
    elif arg == "renew":  # кнопка «Продлить · устройства» в приложении Arise VPN
        subs = db.user_subs(u.id)
        active = [x for x in subs if sub_active(x)]
        if len(subs) == 1 or len(active) == 1:
            s = (active or subs)[0]
            await show(update, context, sub_text(s), sub_kb(s), banner="key")
        else:
            text, kb = subs_view(u.id)
            await show(update, context, text, kb, banner="key")
        return
    await show(update, context, main_text(row), main_kb(row))


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"<b>Условия {esc(config.BRAND)}</b>\n\n"
        "1. Подписка даёт доступ к VPN на оплаченный срок и выбранное число устройств.\n"
        "2. Автопродление можно отключить в любой момент в разделе «Мои подписки» "
        "или в настройках Telegram.\n"
        "3. Запрещено использовать сервис для незаконной деятельности, спама и атак.\n"
        f"4. Если VPN не заработал, мы вернём звёзды в течение {plural_days(config.REFUND_DAYS)} "
        "после оплаты: напишите консьержу.\n"
        "5. Мы не храним историю ваших посещений.\n"
        "6. Об изменениях условий мы сообщим в боте.")


async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Вопросы по оплате</b>\n\n"
        "Напишите консьержу, когда и какой тариф оплатили. Возврат возможен "
        f"в течение {plural_days(config.REFUND_DAYS)}, если VPN не заработал.",
        reply_markup=KB([B("🛎 Написать консьержу", "tk")]))


async def do_trial(update: Update, context: ContextTypes.DEFAULT_TYPE, row) -> None:
    uid = row["id"]
    db.mark_trial(uid)
    sub = db.create_sub(uid, 1, "Пробный ключ", trial=True)
    db.extend_sub(sub["id"], config.TRIAL_DAYS)
    sub = await issue_key(sub["id"])
    await refresh_menu(context, uid)
    body = sub_text(sub).split("\n\n", 1)[1]
    await show(update, context, f"<b>Пробный доступ на {plural_days(config.TRIAL_DAYS)} активирован</b>\n\n"
               + body, sub_kb(sub), banner="welcome")
    await notify_admins(context, f"✦ Пробный период: {who(row)} (<code>{uid}</code>)")


# ---------------------------------------------------------------- покупка

async def choose_target(update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str) -> None:
    """Куда покупаем: продлить одну из подписок, новая подписка или подарок."""
    uid = update.effective_user.id
    subs = db.user_subs(uid)[-6:]
    if not subs:
        await show(update, context, devices_text(plan, False, uid), devices_kb(plan, False, uid), banner="plans")
        return
    name = config.PLANS[plan][0]
    rows = [[B(f"◆ Продлить «{s['name']}» · {price(uid, plan, s['devices'])} ⭐",
               f"bt:{plan}:{s['id']}")] for s in subs]
    rows.append([B("➕ Новая подписка", f"bd:{plan}"), B("🎀 В подарок", f"gd:{plan}")])
    rows.append([B("‹ Тарифы", "plans")])
    await show(update, context,
               f"<b>{esc(name)}</b>\n<i>Продлить подписку или оформить новую?</i>\n\n"
               "Продление добавляется к оставшимся дням, ничего не сгорает.",
               InlineKeyboardMarkup(rows), banner="plans")


async def choose_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, plan: str,
                         dev: int, sub_id: int) -> None:
    """Для тарифа на месяц предлагаем автопродление, остальное сразу в оплату."""
    name, days, _ = config.PLANS[plan]
    uid = update.effective_user.id
    full, once = config.plan_price(plan, dev), price(uid, plan, dev)
    if config.AUTO_RENEW and days == 30:
        await show(update, context,
                   f"<b>{esc(name)} · {plural_dev(dev)}</b>\n<i>Как удобнее оплачивать?</i>\n\n"
                   "<blockquote>🔁 С автопродлением: звёзды спишутся сами раз в месяц, "
                   "доступ не прервётся. Отключить можно в любой момент.\n"
                   "⚡ Разово: оплата на один месяц.</blockquote>" + offer_line(uid),
                   KB([B(f"🔁 Автопродление — {full} ⭐/мес", f"pa:{kind}:{plan}:{dev}:{sub_id}")],
                      [B(f"⚡ Разово — {once} ⭐", f"po:{kind}:{plan}:{dev}:{sub_id}")],
                      [B("‹ Тарифы", "plans")]), banner="plans")
        return
    await send_order(update, context, kind, plan, dev, sub_id, auto=False)


def rub_price(uid, plan: str, dev: int) -> int:
    """Цена в рублях: та же цена в звёздах (со скидкой гостя, если есть), переведённая по курсу /pay."""
    return pay_cfg.rub(price(uid, plan, dev, once=True))


def parse_rub_payload(payload: str):
    """Счёт ЮKassa: r1:код:тариф:дней:рубли:звёзды:устройства:подписка."""
    try:
        v, code, plan, days, rub, stars, dev, sub_id = payload.split(":")
        if v != "r1" or code not in ("b", "e", "g", "u"):  # u — доплата за устройства
            return None
        return code, plan, int(days), int(rub), int(stars), int(dev), int(sub_id)
    except ValueError:
        return None


async def send_order(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, plan: str,
                     dev: int, sub_id: int, auto: bool, stars_only: bool = False) -> None:
    """kind: n — новая подписка, e — продление, g — подарок.
    Разовая оплата при включённых ЮKassa или крипте сначала спрашивает способ оплаты."""
    name, days, _ = config.PLANS[plan]
    uid = update.effective_user.id
    if not auto and not stars_only and pay_cfg.any_on():
        who_pays = None if kind == "g" else uid
        stars, rub = price(who_pays, plan, dev, once=True), rub_price(who_pays, plan, dev)
        tail = f"{kind}:{plan}:{dev}:{sub_id}"
        rows = [[B(f"⭐ Звёздами Telegram — {stars} ⭐", f"pm:s:{tail}")]]
        if pay_cfg.yookassa:
            rows.append([B(f"💳 Картой или СБП — {rub} ₽", f"pm:y:{tail}")])
        if pay_cfg.crypto:
            rows.append([B(f"🪙 Криптой (USDT, TON, BTC) — {rub} ₽", f"pm:c:{tail}")])
        rows.append([B("‹ Тарифы", "plans")])
        await show(update, context,
                   f"<b>{esc(name)} · {plural_dev(dev)}</b>\n<i>Как удобнее оплатить?</i>\n\n"
                   "<blockquote>⭐ Звёзды — прямо в Telegram\n"
                   + ("💳 Карта или СБП — через ЮKassa\n" if pay_cfg.yookassa else "")
                   + ("🪙 Крипта — через @CryptoBot, по курсу на момент оплаты\n" if pay_cfg.crypto else "")
                   + "</blockquote>\nДоступ выдаётся сразу после оплаты любым способом.",
                   InlineKeyboardMarkup(rows), banner="plans")
        return
    amount = price(None if kind == "g" else uid, plan, dev, once=not auto)
    code = {"n": "a" if auto else "b", "e": "x" if auto else "e", "g": "g"}[kind]
    token = secrets.token_hex(6) if auto else "-"
    payload = f"v2:{code}:{plan}:{days}:{amount}:{dev}:{sub_id}:{token}"
    if kind == "g":
        title = f"{config.BRAND} · подарок"
        desc = (f"Подарочный доступ на {plural_days(days)}, {plural_dev(dev)}. "
                "После оплаты придёт подарочная ссылка.")
    else:
        title = f"{config.BRAND} · {name}"
        desc = (f"Персональный доступ к VPN на {plural_days(days)}, {plural_dev(dev)}. "
                + ("Продлевается автоматически каждый месяц." if auto else "Ключ придёт сразу после оплаты."))
    prices = [LabeledPrice(name, amount)]
    chat = update.effective_chat.id
    if auto:
        link = await context.bot.create_invoice_link(
            title=title, description=desc, payload=payload, provider_token="", currency="XTR",
            prices=prices, subscription_period=MONTH)
        await context.bot.send_message(
            chat, f"🔁 <b>Подписка с автопродлением</b>\n\n{amount} ⭐ в месяц, {plural_dev(dev)}. "
                  "Отключить можно в любой момент в «Мои подписки».",
            reply_markup=KB([B(f"Оформить · {amount} ⭐/мес", url=link)]))
        return
    await context.bot.send_invoice(chat_id=chat, title=title, description=desc, payload=payload,
                                   provider_token="", currency="XTR", prices=prices)


def order_title(kind: str, plan: str, dev: int) -> tuple[str, str]:
    name, days, _ = config.PLANS[plan]
    if kind == "g":
        return (f"{config.BRAND} · подарок", f"Подарочный доступ на {plural_days(days)}, {plural_dev(dev)}. "
                                             "После оплаты придёт подарочная ссылка.")
    return f"{config.BRAND} · {name}", f"Персональный доступ к VPN на {plural_days(days)}, {plural_dev(dev)}."


async def send_rub_order(update: Update, context: ContextTypes.DEFAULT_TYPE, method: str, kind: str, plan: str,
                         dev: int, sub_id: int) -> None:
    """Счёт в рублях: ЮKassa (счёт Telegram) или Crypto Pay (ссылка на оплату в @CryptoBot)."""
    uid = update.effective_user.id
    name, days, _ = config.PLANS[plan]
    who_pays = None if kind == "g" else uid
    stars, rub = price(who_pays, plan, dev, once=True), rub_price(who_pays, plan, dev)
    code = {"n": "b", "e": "e", "g": "g"}[kind]
    payload = f"r1:{code}:{plan}:{days}:{rub}:{stars}:{dev}:{sub_id}"
    title, desc = order_title(kind, plan, dev)
    await send_rub_invoice(update, context, method, title, desc, name, rub, payload)


async def send_rub_invoice(update, context: ContextTypes.DEFAULT_TYPE, method: str, title: str, desc: str,
                           name: str, rub: int, payload: str) -> None:
    """Счёт в рублях по готовому payload: y — ЮKassa, c — Crypto Pay."""
    uid = update.effective_user.id
    chat = update.effective_chat.id
    if method == "y":
        extra = {}
        if pay_cfg.receipt:  # чек по 54-ФЗ: ЮKassa просит почту и состав покупки
            extra = dict(need_email=True, send_email_to_provider=True, provider_data=json.dumps({"receipt": {
                "items": [{"description": title[:128], "quantity": "1.00",
                           "amount": {"value": f"{rub}.00", "currency": "RUB"}, "vat_code": 1,
                           "payment_mode": "full_payment", "payment_subject": "service"}]}}))
        await context.bot.send_invoice(chat_id=chat, title=title, description=desc, payload=payload,
                                       provider_token=pay_cfg.yookassa, currency="RUB",
                                       prices=[LabeledPrice(name, rub * 100)], **extra)
        return
    cp = paymod.CryptoPay(pay_cfg.crypto, pay_cfg.crypto_test)
    try:
        inv = await cp.create(rub, f"{title}. {desc}", payload)
    except Exception as e:
        log.warning("крипта: счёт не создан: %s", e)
        await context.bot.send_message(chat, "Не получилось создать счёт в крипте. Попробуйте ещё раз "
                                             "через минуту или выберите другой способ оплаты.")
        return
    db.add_crypto_invoice(int(inv["invoice_id"]), uid, payload, rub)
    await context.bot.send_message(
        chat, f"🪙 <b>Счёт на {rub} ₽</b>\n\nОплатите в @CryptoBot любой монетой: USDT, TON, BTC и другие, "
              "по курсу на момент оплаты. Счёт действует час. Доступ придёт сюда сам, как только "
              "оплата пройдёт (обычно меньше минуты).",
        reply_markup=KB([B(f"Оплатить {rub} ₽", url=paymod.invoice_url(inv))]))


def chat_stub(uid: int):
    """Заглушка update для экрана после оплаты в крипте: события от Telegram нет, есть только чат гостя."""
    return types.SimpleNamespace(callback_query=None, effective_chat=types.SimpleNamespace(id=uid),
                                 effective_user=types.SimpleNamespace(id=uid))


async def crypto_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 20 секунд спрашивает Crypto Pay об открытых счетах и выдаёт доступ по оплаченным."""
    if not pay_cfg.crypto:
        return
    pending = db.active_crypto_invoices()
    if not pending:
        return
    cp = paymod.CryptoPay(pay_cfg.crypto, pay_cfg.crypto_test)
    try:
        items = {int(i["invoice_id"]): i for i in await cp.invoices([r["invoice_id"] for r in pending])}
    except Exception as e:
        log.warning("крипта: проверка счетов не удалась: %s", e)
        return
    for r in pending:
        inv = items.get(r["invoice_id"])
        status = (inv or {}).get("status", "")
        if status == "paid":
            db.set_crypto_status(r["invoice_id"], "paid")
            p = parse_rub_payload(r["payload"])
            urow = db.get_user(r["user_id"])
            if not p or not urow:
                await notify_admins(context, f"⚠️ Оплачен счёт в крипте #{r['invoice_id']}, но выдать доступ "
                                             "не вышло. Проверьте его в @CryptoBot.")
                continue
            code, plan, days, rub, stars, dev, sub_id = p
            asset = f"{inv.get('paid_amount') or ''} {inv.get('paid_asset') or ''}".strip()
            try:
                await fulfill(chat_stub(r["user_id"]), context, urow, code, plan, days, dev, sub_id,
                              f"cp:{r['invoice_id']}", stars, method="crypto",
                              money=f"{rub} ₽" + (f" ({asset})" if asset else ""))
            except Exception:
                log.exception("крипта: выдача доступа по счёту %s", r["invoice_id"])
                granted = db.payment_seen(f"cp:{r['invoice_id']}")
                await notify_admins(context, (
                    f"ℹ️ Счёт в крипте #{r['invoice_id']} оплачен, доступ выдан, но сообщение гостю не "
                    "дошло (возможно, он остановил бота)." if granted else
                    f"⚠️ Счёт в крипте #{r['invoice_id']} оплачен, но доступ не выдан из-за ошибки. "
                    "Выдайте вручную: /grant."))
        elif status == "expired" or (inv is None and time.time() - r["created_at"] > 2 * paymod.CRYPTO_TTL):
            db.set_crypto_status(r["invoice_id"], "expired")


def parse_payload(payload: str):
    try:
        v, code, plan, days, price, dev, sub_id, token = payload.split(":")
        if v != "v2" or code not in ("b", "e", "x", "a", "g", "u"):
            return None
        return code, plan, int(days), int(price), int(dev), int(sub_id), token
    except ValueError:
        return None


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    stale = "Счёт устарел. Откройте меню и выберите тариф заново."
    r = parse_rub_payload(q.invoice_payload)
    if r and r[0] == "u":  # доплата за устройства картой: та же подписка, сумма не ниже текущей
        code, plan, days, rub, stars, dev, sub_id = r
        sub = db.get_sub(sub_id)
        ok = bool(pay_cfg.yookassa and sub and sub["user_id"] == q.from_user.id and q.currency == "RUB"
                  and q.total_amount == rub * 100 and plan == f"up{sub['devices']}" and can_upgrade(sub)
                  and dev in config.DEVICE_OPTIONS and dev > sub["devices"]
                  and rub >= pay_cfg.rub(upgrade_price(sub, dev)))
        await q.answer(ok=ok, error_message=None if ok else stale)
        return
    if r:  # ЮKassa: сумма в копейках, цена та же, что показали гостю
        code, plan, days, rub, stars, dev, sub_id = r
        who_pays = None if code == "g" else q.from_user.id
        ok = bool(pay_cfg.yookassa and q.currency == "RUB" and plan in config.PLANS
                  and config.PLANS[plan][1] == days and dev in config.DEVICE_OPTIONS
                  and q.total_amount == rub * 100
                  and rub in (rub_price(who_pays, plan, dev), pay_cfg.rub(config.plan_price(plan, dev)))
                  and stars in (price(who_pays, plan, dev, once=True), config.plan_price(plan, dev)))
        if ok and code == "e":
            sub = db.get_sub(sub_id)
            ok = bool(sub) and sub["user_id"] == q.from_user.id and sub["devices"] == dev
        await q.answer(ok=ok, error_message=None if ok else stale)
        return
    p = parse_payload(q.invoice_payload)
    if not p:
        await q.answer(ok=False, error_message=stale)
        return
    code, plan, days, amount, dev, sub_id, _ = p
    if code == "u":  # доплата за устройства: подписка та же, число устройств не менялось, сумма не ниже текущей
        sub = db.get_sub(sub_id)
        ok = bool(sub and sub["user_id"] == q.from_user.id and q.currency == "XTR" and q.total_amount == amount
                  and plan == f"up{sub['devices']}" and can_upgrade(sub) and dev in config.DEVICE_OPTIONS
                  and dev > sub["devices"] and amount >= upgrade_price(sub, dev))
        await q.answer(ok=ok, error_message=None if ok else stale)
        return
    current = find_plan(plan, q.from_user.id)
    ok = bool(current and q.currency == "XTR" and current[1] == days and q.total_amount == amount
              and (dev in config.DEVICE_OPTIONS or plan == "test"))
    if ok:
        # Полная цена, или цена со скидкой этого гостя — только для разовой оплаты себе.
        ok = amount == config.plan_price(plan, dev) or (code in ("b", "e")
                                                         and amount == price(q.from_user.id, plan, dev))
    if ok and code in ("e", "x"):
        sub = db.get_sub(sub_id)
        ok = bool(sub) and sub["user_id"] == q.from_user.id and sub["devices"] == dev
    if ok and code in ("a", "x"):
        ok = days == 30
    if not ok:
        await q.answer(ok=False, error_message=stale)
        return
    await q.answer(ok=True)


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    u = update.effective_user
    row = current_user(update)
    charge = sp.telegram_payment_charge_id
    r = parse_rub_payload(sp.invoice_payload)
    if r:  # оплата картой через ЮKassa (счёт Telegram в рублях)
        code, plan, days, rub, stars, dev, sub_id = r
        await fulfill(update, context, row, code, plan, days, dev, sub_id, "yk:" + charge, stars,
                      method="yookassa", money=f"{rub} ₽")
        return
    p = parse_payload(sp.invoice_payload)
    if not p:
        log.error("оплата с непонятным счётом: %s", sp.invoice_payload)
        await notify_admins(context, f"⚠️ Оплата с непонятным счётом от {who(u)}: "
                                     f"<code>{esc(charge)}</code>. Проверьте /payments.")
        return
    code, plan, days, _price, dev, sub_id, token = p

    # очередное автосписание
    if sp.is_recurring and not sp.is_first_recurring:
        sub = db.sub_by_token(token)
        if not sub or not db.add_payment(u.id, plan, sp.total_amount, days, charge, "renew", sub["id"], dev):
            return
        db.extend_sub(sub["id"], days)
        sub = await issue_key(sub["id"])
        await refresh_menu(context, u.id)
        try:
            await context.bot.send_message(u.id, f"🔁 «{esc(sub['name'])}» продлена автоматически до "
                                                 f"<b>{fmt_date(sub['expires_at'])}</b>.")
        except TelegramError:
            pass
        await notify_admins(context, f"🔁 Автосписание: {who(u)} · {sp.total_amount} ⭐\n"
                                     f"charge: <code>{esc(charge)}</code>")
        return

    if code == "u":
        sub = db.get_sub(sub_id)
        if not sub or sub["user_id"] != u.id:
            log.error("доплата за устройства без подписки: %s", sp.invoice_payload)
            return
        await grant_upgrade(update, context, row, sub, plan, dev, charge, sp.total_amount)
        return

    await fulfill(update, context, row, code, plan, days, dev, sub_id, charge, sp.total_amount, token=token)


async def grant_upgrade(update, context: ContextTypes.DEFAULT_TYPE, u, sub, plan: str, dev: int, charge: str,
                        stars: int, method: str = "stars", money: str | None = None) -> None:
    """Доплата за устройства прошла (звёзды, карта или крипта): больше устройств в той же подписке."""
    if not db.add_payment(u["id"], plan, stars, 0, charge, "upgrade", sub["id"], dev, method=method, money=money):
        return  # тот же платёж повторно
    db.set_payment_target(charge, sub["id"])
    db.run("UPDATE subscriptions SET devices=? WHERE id=?", max(dev, sub["devices"]), sub["id"])
    sub = await issue_key(sub["id"])
    await refresh_menu(context, u["id"])
    await show(update, context,
               f"<b>Готово: {plural_dev(sub['devices'])}</b>\n\n"
               f"◆ «{esc(sub['name'])}» до <b>{fmt_date(sub['expires_at'])}</b>\n"
               "Ключ тот же, новые устройства можно подключать сразу.",
               KB([B("📲 Подключение", "howto"), B("🗝 Подписка", f"sub:{sub['id']}")], [BACK]),
               banner="welcome", effect=CONFETTI)
    await notify_admins(context, f"➕ Устройства: {who(u)} · «{esc(sub['name'])}» → "
                                 f"{plural_dev(sub['devices'])} · {money or f'{stars} ⭐'}\n"
                                 f"charge: <code>{esc(charge)}</code>")


async def fulfill(update, context: ContextTypes.DEFAULT_TYPE, u, code: str, plan: str, days: int, dev: int,
                  sub_id: int, charge: str, amount: int, token: str = "-", method: str = "stars",
                  money: str | None = None) -> None:
    """Оплата прошла: новая подписка, продление или подарок. Общая часть для звёзд, ЮKassa и крипты.
    u — строка гостя из базы; amount — цена в звёздах (для рублей — цена тарифа в звёздах);
    update нужен только для экрана (у крипты это заглушка с чатом гостя)."""
    if code == "u":  # доплата за устройства картой или криптой
        sub = db.get_sub(sub_id)
        if sub and sub["user_id"] == u["id"]:
            await grant_upgrade(update, context, u, sub, plan, dev, charge, amount, method, money)
        else:
            log.error("доплата за устройства без подписки: %s %s", sub_id, charge)
        return
    row = u
    name = (find_plan(plan, u["id"]) or (plan,))[0]
    paid_text = money or f"{amount} ⭐"
    first_payment = db.payments_count(u["id"]) == 0
    kind = {"b": "buy", "a": "auto", "e": "ext", "x": "auto", "g": "gift"}[code]
    try:
        full = config.plan_price(plan, dev)
    except KeyError:  # тариф убрали из настроек после выставления счёта
        full = amount
    discounted = code in ("b", "e") and amount < full
    if not db.add_payment(u["id"], plan, amount, days, charge, kind, None, dev,
                          full_price=full if discounted else None, method=method, money=money):
        return  # Telegram прислал тот же платёж повторно
    if discounted:
        db.use_offer(u["id"])

    if code == "g":
        gift = db.create_gift(u["id"], days, dev)
        db.set_payment_target(charge, None, gift)
        link = f"https://t.me/{STATE['username'] or context.bot.username}?start=gift_{gift}"
        await show(update, context,
                   "<b>Подарок готов</b>\n\n"
                   f"◆ {plural_days(days)}, {plural_dev(dev)}\n"
                   f"◆ Код: <code>{gift}</code>\n\n"
                   f"Отправьте другу ссылку, по ней подарок активируется в один шаг:\n<code>{link}</code>",
                   KB([B("📤 Отправить подарок", url=share_url(link, f"Дарю доступ к {config.BRAND} 🎀"))],
                      [BACK]), banner="welcome", effect=CONFETTI)
        await notify_admins(context, f"🎀 Подарок: {who(u)} · {esc(name)} · {paid_text}\n"
                                     f"charge: <code>{esc(charge)}</code>")
        return

    sub = db.get_sub(sub_id) if code in ("e", "x") else None
    if not sub or sub["user_id"] != u["id"]:
        sub = db.create_sub(u["id"], dev)
    db.extend_sub(sub["id"], days)
    db.run("UPDATE subscriptions SET trial=0 WHERE id=?", sub["id"])  # оплаченная — уже не пробная
    if code in ("a", "x"):
        db.set_auto(sub["id"], token, charge, True)
    db.set_payment_target(charge, sub["id"])
    sub = await issue_key(sub["id"])
    await refresh_menu(context, u["id"])

    if first_payment and row["referrer_id"] and not config.REF_ON_JOIN:
        rsub = await grant_days(row["referrer_id"], config.REF_BONUS_DAYS)
        await refresh_menu(context, row["referrer_id"])
        try:
            await context.bot.send_message(
                row["referrer_id"],
                f"🎁 Ваш друг оформил доступ. Вам начислено <b>+{plural_days(config.REF_BONUS_DAYS)}</b>.\n"
                f"◆ «{esc(rsub['name'])}» действует до <b>{fmt_date(rsub['expires_at'])}</b>.")
        except TelegramError:
            pass

    auto_note = "\n◆ Автопродление включено" if code in ("a", "x") else ""
    await show(update, context,
               "<b>Оплата прошла. Благодарим за доверие.</b>\n\n"
               f"◆ {esc(sub['name'])}: {esc(name)}, {plural_dev(sub['devices'])}\n"
               f"◆ Действует до <b>{fmt_date(sub['expires_at'])}</b>{auto_note}\n\n"
               f"Ваш персональный ключ:\n<code>{esc(sub['vpn_key'])}</code>\n\n"
               "<i>Нажмите на ключ, чтобы скопировать.</i>" + demo_note(),
               KB([B("📲 Подключение", "howto"), B("📷 QR-код", f"qr:{sub['id']}")], [BACK]),
               banner="welcome", effect=CONFETTI)
    auto_mark = " · 🔁" if code in ("a", "x") else ""
    await notify_admins(context, f"💰 Оплата: {who(u)} · {esc(name)} · {plural_dev(dev)} · "
                                 f"{paid_text}{auto_mark}\ncharge: <code>{esc(charge)}</code>")


# ---------------------------------------------------------------- кнопки

async def own_sub(q, uid: int, sid: str):
    try:
        sub = db.get_sub(int(sid))
    except ValueError:
        sub = None
    if not sub or sub["user_id"] != uid:
        await q.answer("Подписка не найдена", show_alert=True)
        return None
    return sub


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    data = q.data or ""
    row = current_user(update)
    uid = row["id"]
    parts = data.split(":")

    if parts[0] == "adm":
        await admin_button(update, context, row, parts)
        return

    if data == "trial":
        if not can_trial(row):
            await q.answer("Пробный период уже использован", show_alert=True)
            return
        await q.answer("✦ Пробный период активирован")
        await do_trial(update, context, row)
        return

    # ---- покупка
    if parts[0] in ("buy", "bd", "gd") and len(parts) == 2 and parts[1] in config.PLANS:
        await q.answer()
        if parts[0] == "buy":
            await choose_target(update, context, parts[1])
        else:
            gift = parts[0] == "gd"
            await show(update, context, devices_text(parts[1], gift, uid), devices_kb(parts[1], gift, uid),
                       banner="plans")
        return
    if parts[0] in ("bn", "bg") and len(parts) == 3 and parts[1] in config.PLANS:
        dev = int(parts[2]) if parts[2].isdigit() else 0
        if dev not in config.DEVICE_OPTIONS:
            await q.answer("Откройте тарифы заново", show_alert=True)
            return
        await q.answer("Счёт ниже 👇" if parts[0] == "bg" else None)
        if parts[0] == "bg":
            await send_order(update, context, "g", parts[1], dev, 0, auto=False)
        else:
            await choose_payment(update, context, "n", parts[1], dev, 0)
        return
    if parts[0] == "bt" and len(parts) == 3 and parts[1] in config.PLANS:
        sub = await own_sub(q, uid, parts[2])
        if not sub:
            return
        await q.answer()
        await choose_payment(update, context, "e", parts[1], sub["devices"], sub["id"])
        return
    if parts[0] == "pm" and len(parts) == 6 and parts[1] in ("s", "y", "c") and parts[2] in ("n", "e", "g") \
            and parts[3] in config.PLANS and parts[4].isdigit() and parts[5].isdigit():
        method, kind, plan, dev, sid = parts[1], parts[2], parts[3], int(parts[4]), int(parts[5])
        if kind == "e":
            sub = await own_sub(q, uid, parts[5])
            if not sub:
                return
            dev = sub["devices"]
        if dev not in config.DEVICE_OPTIONS or (method == "y" and not pay_cfg.yookassa) \
                or (method == "c" and not pay_cfg.crypto):
            await q.answer("Откройте тарифы заново", show_alert=True)
            return
        await q.answer("Счёт ниже 👇" if method != "c" else "Создаю счёт…")
        if method == "s":
            await send_order(update, context, kind, plan, dev, sid, auto=False, stars_only=True)
        else:
            await send_rub_order(update, context, method, kind, plan, dev, sid)
        return
    if parts[0] == "up" and len(parts) == 2:
        sub = await own_sub(q, uid, parts[1])
        if not sub:
            return
        if not can_upgrade(sub):
            await q.answer("С автопродлением устройства меняются при новой подписке" if sub["auto_active"]
                           else "Добавить устройства сейчас нельзя", show_alert=True)
            return
        await q.answer()
        await show(update, context, upgrade_text(sub), upgrade_kb(sub), banner="plans")
        return
    if parts[0] == "upd" and len(parts) in (3, 4) and parts[2].isdigit():
        sub = await own_sub(q, uid, parts[1])
        if not sub:
            return
        n = int(parts[2])
        if not can_upgrade(sub) or n not in config.DEVICE_OPTIONS or n <= sub["devices"]:
            await q.answer("Откройте подписку заново", show_alert=True)
            return
        amount = upgrade_price(sub, n)
        method = parts[3] if len(parts) == 4 else ""
        if pay_cfg.any_on() and method not in ("s", "y", "c"):  # сначала — чем платить
            await q.answer()
            rub = pay_cfg.rub(amount)
            rows = [[B(f"⭐ Звёздами Telegram — {amount} ⭐", f"upd:{sub['id']}:{n}:s")]]
            if pay_cfg.yookassa:
                rows.append([B(f"💳 Картой или СБП — {rub} ₽", f"upd:{sub['id']}:{n}:y")])
            if pay_cfg.crypto:
                rows.append([B(f"🪙 Криптой (USDT, TON, BTC) — {rub} ₽", f"upd:{sub['id']}:{n}:c")])
            rows.append([B("‹ Устройства", f"up:{sub['id']}")])
            await show(update, context, f"<b>{plural_dev(sub['devices'])} → {plural_dev(n)}</b>\n"
                                        f"<i>«{esc(sub['name'])}» до {fmt_date(sub['expires_at'])}. "
                                        "Как удобнее оплатить?</i>", InlineKeyboardMarkup(rows), banner="plans")
            return
        if method in ("y", "c") and not (pay_cfg.yookassa if method == "y" else pay_cfg.crypto):
            await q.answer("Этот способ оплаты сейчас выключен", show_alert=True)
            return
        await q.answer("Счёт ниже 👇" if method != "c" else "Создаю счёт…")
        title = f"{config.BRAND} · устройства"
        desc = (f"«{sub['name']}»: {plural_dev(sub['devices'])} → {plural_dev(n)} до "
                f"{fmt_date(sub['expires_at'])}.")
        if method in ("y", "c"):
            rub = pay_cfg.rub(amount)
            payload = f"r1:u:up{sub['devices']}:0:{rub}:{amount}:{n}:{sub['id']}"
            await send_rub_invoice(update, context, method, title, desc, "Устройства", rub, payload)
            return
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id, title=title, description=desc,
            payload=f"v2:u:up{sub['devices']}:0:{amount}:{n}:{sub['id']}:-", provider_token="",
            currency="XTR", prices=[LabeledPrice("Устройства", amount)])
        return
    if parts[0] in ("pa", "po") and len(parts) == 5 and parts[2] in config.PLANS:
        kind, plan = parts[1], parts[2]
        if kind not in ("n", "e") or not parts[3].isdigit() or not parts[4].isdigit():
            await q.answer("Откройте тарифы заново", show_alert=True)
            return
        dev, sid = int(parts[3]), int(parts[4])
        if kind == "e":
            sub = await own_sub(q, uid, parts[4])
            if not sub:
                return
            dev = sub["devices"]
        if dev not in config.DEVICE_OPTIONS:
            await q.answer("Откройте тарифы заново", show_alert=True)
            return
        await q.answer("Счёт ниже 👇")
        await send_order(update, context, kind, plan, dev, sid, auto=parts[0] == "pa")
        return

    # ---- подписки
    if parts[0] == "devdel" and len(parts) == 3:
        sub = await own_sub(q, uid, parts[1])
        if not sub:
            return
        gone = hasattr(vpn, "forget_device") and vpn.forget_device(sub["id"], parts[2])
        await q.answer("Устройство удалено: место освободилось" if gone else "Уже удалено")
        await show(update, context, devices_view(db.get_sub(sub["id"])), devices_manage_kb(db.get_sub(sub["id"])),
                   banner="key")
        return
    if parts[0] in ("dev", "devr", "devrok") and len(parts) == 2:
        sub = await own_sub(q, uid, parts[1])
        if not sub:
            return
        if not sub_active(sub) or not hasattr(vpn, "reset_key"):
            await q.answer("Подписка неактивна", show_alert=True)
            return
        if parts[0] == "devrok":
            last = context.bot_data.setdefault("dev_resets", {}).get(sub["id"], 0)
            if time.time() - last < DEV_RESET_EVERY:
                await q.answer("Сбрасывать можно раз в 10 минут", show_alert=True)
                return
            context.bot_data["dev_resets"][sub["id"]] = time.time()
            await q.answer("Готово")
            db.set_key(sub["id"], await vpn.reset_key(sub["id"]), True)
            guard.forget(sub["id"])
            if getattr(vpn, "is_suspended", None) and vpn.is_suspended(sub["id"]):
                await vpn.resume(sub["id"])
            sub = db.get_sub(sub["id"])
            await show(update, context, "✅ <b>Все устройства отключены.</b>\n\nСтарая ссылка больше не работает. "
                                        "Добавьте новую в приложение на тех устройствах, где VPN нужен:\n\n"
                                        + sub_text(sub), sub_kb(sub), banner="key")
            return
        await q.answer()
        if parts[0] == "devr":
            await show(update, context, f"<b>Сбросить устройства «{esc(sub['name'])}»?</b>\n\n"
                                        "Все телефоны и компьютеры с этой подпиской сразу отключатся, а ссылка "
                                        "подписки сменится. Новую ссылку нужно будет добавить заново на своих "
                                        "устройствах.\n\nПригодится, если ссылку кто-то узнал или телефон потерялся.",
                       KB([B("🔄 Да, сбросить", f"devrok:{sub['id']}"), B("‹ Отмена", f"dev:{sub['id']}")]),
                       banner="key")
            return
        await show(update, context, devices_view(sub), devices_manage_kb(sub), banner="key")
        return
    if parts[0] in ("sub", "qr", "raw", "ren", "ext", "noauto", "noautook") and len(parts) == 2:
        sub = await own_sub(q, uid, parts[1])
        if not sub:
            return
        if parts[0] == "raw":
            if not sub_active(sub) or not hasattr(vpn, "links"):
                await q.answer("Подписка неактивна", show_alert=True)
                return
            await q.answer()
            if not sub["key_active"]:
                sub = await issue_key(sub["id"])
            parts_out = [f"🔑 <b>Ключи «{esc(sub['name'])}» без подписки</b>\n<i>Если приложение не может "
                         "обновить подписку, скопируйте нужный ключ и добавьте его в приложение через «+» → "
                         "«Из буфера». Такие ключи не обновляются сами: после смены настроек сервера "
                         "возьмите их здесь заново.</i>"]
            for link in vpn.links(sub["id"]):
                item = f"<b>{esc(unquote(link.rsplit('#', 1)[-1]))}</b>\n<code>{esc(link)}</code>"
                if len(parts_out[-1]) + len(item) > 3800:
                    parts_out.append(item)
                else:
                    parts_out[-1] += "\n\n" + item
            for chunk in parts_out:
                await context.bot.send_message(update.effective_chat.id, chunk)
            return
        if parts[0] == "qr":
            if not sub_active(sub) or not sub["vpn_key"]:
                await q.answer("Подписка неактивна", show_alert=True)
                return
            await q.answer()
            img = qrcode.make(sub["vpn_key"], border=2, box_size=10)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            await context.bot.send_photo(update.effective_chat.id, buf,
                                         caption=f"📷 «{esc(sub['name'])}»: отсканируйте код в приложении VPN."
                                                 + demo_note())
            return
        await q.answer()
        context.user_data.pop("await", None)
        if parts[0] == "sub":
            if sub_active(sub) and (not sub["vpn_key"] or not sub["key_active"]):
                sub = await issue_key(sub["id"])
            await show(update, context, sub_text(sub), sub_kb(sub), banner="key")
        elif parts[0] == "ren":
            context.user_data["await"] = f"rename:{sub['id']}"
            await show(update, context, f"<b>Новое название</b>\n\nОтправьте название для «{esc(sub['name'])}» "
                                        "одним сообщением, до 24 символов. Например: «Телефон» или «Ноутбук».",
                       KB([B("‹ Отмена", f"sub:{sub['id']}")]), banner="key")
        elif parts[0] == "ext":
            await show(update, context, plans_text(sub), plans_kb(sub), banner="plans")
        elif parts[0] == "noauto":
            await show(update, context, f"<b>Отключить автопродление «{esc(sub['name'])}»?</b>\n\n"
                                        f"Подписка доработает до {fmt_date(sub['expires_at'])}, "
                                        "после этого звёзды больше списываться не будут.",
                       KB([B("Да, отключить", f"noautook:{sub['id']}"), B("Оставить", f"sub:{sub['id']}")]),
                       banner="key")
        else:
            await cancel_auto(context, sub)
            sub = db.get_sub(sub["id"])
            await show(update, context, sub_text(sub) + "\n\n◇ Автопродление отключено.", sub_kb(sub),
                       banner="key")
        return

    await q.answer()
    context.user_data.pop("await", None)

    if data == "menu":
        await show(update, context, main_text(row), main_kb(row))
    elif data == "plans":
        await show(update, context, plans_text(uid=uid), plans_kb(uid=uid), banner="plans")
    elif data == "gift":
        rows = [[B(f"{plan_mark(k)} {n} — от {pr} ⭐", f"gd:{k}")] for k, (n, d, pr) in config.PLANS.items()]
        rows.append([BACK])
        await show(update, context,
                   "<b>Подарить доступ</b>\n<i>Сделайте приятное другу.</i>\n\n"
                   "Выберите срок и число устройств, оплатите, и бот пришлёт подарочную ссылку. "
                   "Друг откроет её и сразу получит свою подписку.",
                   InlineKeyboardMarkup(rows), banner="ref")
    elif data == "subs":
        text, kb = subs_view(uid)
        await show(update, context, text, kb, banner="key")
    elif data == "howto":
        await show(update, context,
                   "<b>Подключение за минуту</b>\n<i>Выберите устройство, и я покажу шаги.</i>",
                   KB([B(APPS["android"][0], "how:android"), B(APPS["ios"][0], "how:ios")],
                      [B(APPS["windows"][0], "how:windows"), B(APPS["mac"][0], "how:mac")],
                      [B(APPS["tv"][0], "how:tv"), B("🛠 Не работает?", "fix")],
                      [BACK]), banner="howto")
    elif data.startswith("how:") and data[4:] in APPS:
        rows = [[B(f"⬇️ {n}", url=u) for n, u in APP_LINKS[data[4:]]],
                [B("🗝 Мои подписки", "subs"), B("‹ Устройства", "howto")], [BACK]]
        if data == "how:android" and android_app:
            rows.insert(0, [B("📥 Скачать приложение", "apk")])
        await show(update, context, howto_text(data[4:]), KB(*rows), banner="howto")
    elif data == "apk":
        await send_app(update, context)
    elif data == "profile":
        act = db.active_subs(uid)
        await show(update, context,
                   "<b>Профиль</b>\n\n"
                   f"<blockquote>◆ ID: <code>{uid}</code>\n"
                   f"◆ С нами с {fmt_date(row['joined_at'])}\n"
                   f"◆ Подписок: {len(db.user_subs(uid))}, активных: {len(act)}\n"
                   f"◆ Оплачено: {row['paid_stars']} ⭐\n"
                   f"◆ Приглашено друзей: {db.referral_count(uid)}</blockquote>\n\n"
                   + status_line(uid),
                   KB([B("🗝 Мои подписки", "subs"), B("◆ Тарифы", "plans")], [BACK]), banner="profile")
    elif data == "ref":
        link = f"https://t.me/{context.bot.username}?start=ref_{uid}"
        await show(update, context,
                   "<b>Привилегия для друзей</b>\n\n"
                   f"За каждого друга, который {ref_condition()}, вы получаете "
                   f"<b>+{plural_days(config.REF_BONUS_DAYS)}</b>. Без ограничений.\n\n"
                   f"◆ Ваша ссылка:\n<code>{link}</code>\n\n"
                   f"◆ Приглашено: <b>{db.referral_count(uid)}</b>",
                   KB([B("📤 Отправить приглашение",
                         url=share_url(link, f"Приглашаю в {config.BRAND}: быстрый приватный VPN"))],
                      [B("🎀 Подарить доступ", "gift")], [BACK]), banner="ref")
    elif data == "promo":
        context.user_data["await"] = "promo"
        await show(update, context, "<b>Промокод или подарок</b>\n\nОтправьте промокод или подарочный код "
                                    "одним сообщением.", KB([B("‹ Отмена", "menu")]))
    elif data == "ch" and config.CHANNEL:
        await show(update, context,
                   "<b>Бонус за подписку</b>\n\n"
                   "Подпишитесь на наш канал с новостями и акциями и получите "
                   f"<b>+{plural_days(config.CHANNEL_BONUS_DAYS)}</b> доступа.",
                   KB([B("📣 Открыть канал", url=channel_link())],
                      [B("✅ Я подписался", "chk")], [BACK]), banner="ref")
    elif data == "chk" and config.CHANNEL:
        await check_channel(update, context, row)
    elif data == "support":
        rows = [[B("🛠 VPN не работает?", "fix")], [B("✍️ Написать консьержу", "tk")]]
        if config.CHANNEL:
            rows.append([B("📣 Канал с новостями", url=channel_link())])
        rows.append([BACK])
        await show(update, context,
                   "<b>Консьерж</b>\n<i>Поможем подключиться и ответим на вопросы.</i>\n\n"
                   "<blockquote>Не подключается? Проверьте, что ключ скопирован целиком и "
                   "подписка активна.\n"
                   f"Возврат звёзд в течение {plural_days(config.REFUND_DAYS)}, если VPN не заработал."
                   "</blockquote>\n\nУсловия: /terms",
                   InlineKeyboardMarkup(rows), banner="support")
    elif data == "fix":
        await show(update, context, fix_text(),
                   KB([B("🗝 Мои подписки", "subs"), B("✍️ Консьержу", "tk")], [BACK]), banner="support")
    elif data == "tk":
        context.user_data["await"] = "ticket"
        await show(update, context,
                   "<b>Сообщение консьержу</b>\n\nОпишите вопрос одним сообщением. Можно приложить скриншот. "
                   "Ответ придёт сюда, в чат с ботом.",
                   KB([B("‹ Отмена", "support")]), banner="support")


async def check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, row) -> None:
    uid = row["id"]
    if row["channel_bonus"]:
        await context.bot.send_message(uid, "Бонус за подписку уже получен.")
        return
    try:
        member = await context.bot.get_chat_member(config.CHANNEL, uid)
        subscribed = member.status in ("member", "administrator", "creator")
    except TelegramError as e:
        log.warning("проверка канала: %s", e)
        await context.bot.send_message(uid, "Не получилось проверить подписку. Попробуйте чуть позже.")
        return
    if not subscribed:
        await context.bot.send_message(uid, "Подписка на канал пока не видна. Подпишитесь и нажмите "
                                            "«✅ Я подписался» ещё раз.")
        return
    db.mark_channel_bonus(uid)
    sub = await grant_days(uid, config.CHANNEL_BONUS_DAYS)
    await refresh_menu(context, uid)
    await show(update, context,
               f"<b>Спасибо за подписку</b>\n\nНачислено <b>+{plural_days(config.CHANNEL_BONUS_DAYS)}</b>.\n"
               f"◆ «{esc(sub['name'])}» действует до <b>{fmt_date(sub['expires_at'])}</b>",
               KB([B("🗝 Мои подписки", "subs"), BACK]), banner="welcome")


async def cancel_auto(context: ContextTypes.DEFAULT_TYPE, sub) -> None:
    if not sub["auto_active"]:
        return
    try:
        await context.bot.edit_user_star_subscription(sub["user_id"], sub["auto_charge_id"], True)
    except TelegramError as e:
        log.warning("отмена автопродления %s: %s", sub["id"], e)
    db.set_auto(sub["id"], sub["auto_token"], sub["auto_charge_id"], False)
    await refresh_menu(context, sub["user_id"])


# ---------------------------------------------------------------- сообщения

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    row = current_user(update)
    uid = row["id"]

    # ответ админа на тикет
    if uid in config.ADMIN_IDS and msg.reply_to_message:
        target = db.ticket_user(msg.chat_id, msg.reply_to_message.message_id)
        if target:
            try:
                await context.bot.send_message(target, "🛎 <b>Ответ консьержа</b>")
                await context.bot.copy_message(target, msg.chat_id, msg.message_id,
                                               reply_markup=KB([B("✍️ Ответить", "tk")]))
                await msg.reply_text("✅ Ответ отправлен гостю.")
            except TelegramError as e:
                await msg.reply_text(f"Не удалось отправить: {esc(str(e))}")
            return

    mode = context.user_data.pop("await", None)

    if mode == "broadcast" and uid in config.ADMIN_IDS:
        task = STATE.get("broadcast")
        if task and not task.done():
            await msg.reply_text("Предыдущая рассылка ещё идёт. Дождитесь отчёта о ней.")
            return
        await msg.reply_text("Рассылка началась. Бот в это время отвечает гостям как обычно, "
                             "отчёт придёт сюда.")
        STATE["broadcast"] = asyncio.get_running_loop().create_task(
            broadcast(context.bot, uid, msg.chat_id, msg.message_id))
        return

    if mode == "promo" and msg.text:
        await redeem(update, context, msg.text)
        return

    if mode == "ticket":
        await send_ticket(update, context, row)
        return

    if mode and mode.startswith("rename:") and msg.text:
        sub = db.get_sub(int(mode.split(":")[1]))
        if sub and sub["user_id"] == uid:
            name = " ".join(msg.text.split())[:24] or sub["name"]
            db.rename_sub(sub["id"], name)
            sub = db.get_sub(sub["id"])
            await refresh_menu(context, uid)
            await show(update, context, sub_text(sub), sub_kb(sub), banner="key")
            return

    await show(update, context, main_text(row), main_kb(row))


def retry_seconds(e: RetryAfter) -> float:
    ra = e.retry_after
    return ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra)


async def broadcast(bot, admin_chat: int, from_chat: int, message_id: int) -> tuple[int, int]:
    """Рассылка в фоне: около 25 сообщений в секунду, как разрешает Telegram. Если Telegram
    просит подождать, бот ждёт и отправляет то же сообщение ещё раз, а не теряет его."""
    targets = db.all_user_ids()
    ok = fail = 0
    progress = None
    try:
        progress = await bot.send_message(admin_chat, f"📢 Рассылка: 0 из {len(targets)}")
    except TelegramError:
        pass
    for i, target in enumerate(targets, 1):
        for attempt in range(4):
            try:
                await bot.copy_message(target, from_chat, message_id)
                ok += 1
                break
            except RetryAfter as e:
                await asyncio.sleep(retry_seconds(e) + 1)
            except (Forbidden, BadRequest):
                fail += 1  # гость удалил чат или заблокировал бота
                break
            except TelegramError:
                if attempt == 3:
                    fail += 1
                else:
                    await asyncio.sleep(2 * (attempt + 1))
        await asyncio.sleep(0.04)
        if progress and i % 200 == 0:
            try:
                await progress.edit_text(f"📢 Рассылка: {i} из {len(targets)}")
            except TelegramError:
                pass
    try:
        await bot.send_message(admin_chat, f"📢 Рассылка готова. Доставлено: {ok}, не доставлено: {fail}.")
    except TelegramError:
        pass
    return ok, fail


async def send_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, row) -> None:
    msg = update.message
    act = db.active_subs(row["id"])
    info = (f"🛎 <b>Обращение</b> от {who(row)} (<code>{row['id']}</code>)\n"
            f"Активных подписок: {len(act)}, оплачено: {row['paid_stars']} ⭐\n"
            "<i>Ответьте на это сообщение или на сообщение гостя, чтобы ответить ему.</i>")
    delivered = 0
    for admin_id in config.ADMIN_IDS:
        try:
            head = await context.bot.send_message(admin_id, info)
            copy = await context.bot.copy_message(admin_id, msg.chat_id, msg.message_id)
            db.add_ticket(admin_id, head.message_id, row["id"])
            db.add_ticket(admin_id, copy.message_id, row["id"])
            delivered += 1
        except TelegramError as e:
            log.warning("тикет админу %s: %s", admin_id, e)
    text = ("<b>Сообщение передано консьержу</b>\n\nОтвет придёт сюда, в чат с ботом." if delivered
            else "<b>Не получилось передать сообщение</b>\n\nПопробуйте чуть позже.")
    await show(update, context, text, KB([B("✍️ Дописать", "tk"), BACK]), banner="support")


CODE_TRIES, CODE_WINDOW = 5, 600  # неверных кодов за 10 минут — дальше пауза (против перебора)


def code_blocked(context, uid: int) -> int:
    """Сколько секунд гостю ждать, прежде чем вводить коды снова (0 — можно)."""
    now = time.time()
    tries = [t for t in context.bot_data.setdefault("code_fails", {}).get(uid, []) if now - t < CODE_WINDOW]
    context.bot_data["code_fails"][uid] = tries
    return int(CODE_WINDOW - (now - tries[0])) + 1 if len(tries) >= CODE_TRIES else 0


def code_failed(context, uid: int) -> None:
    context.bot_data.setdefault("code_fails", {}).setdefault(uid, []).append(time.time())


async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    uid = update.effective_user.id
    current_user(update)
    code = code.strip()
    wait = code_blocked(context, uid)
    if wait:
        await show(update, context, "<b>Слишком много неверных кодов</b>\n\n"
                                    f"Попробуйте снова через {max(1, wait // 60)} мин.", KB([BACK]))
        return
    if code.upper().startswith("GIFT-"):
        status, sub = db.redeem_gift(code, uid)
        if status == "not_found":
            code_failed(context, uid)
        if status != "ok":
            reason = {"not_found": "Такого подарочного кода нет.", "used": "Этот подарок уже активирован.",
                      "void": "Этот подарок отменён."}[status]
            await show(update, context, f"<b>Подарок не активирован</b>\n\n{reason}",
                       KB([B("🎟 Ввести другой код", "promo"), BACK]))
            return
        sub = await issue_key(sub["id"])
        await refresh_menu(context, uid)
        g = db.get_gift(code)
        if g["buyer_id"] != uid:
            try:
                await context.bot.send_message(g["buyer_id"], "🎀 Ваш подарок активирован. Спасибо, что делитесь!")
            except TelegramError:
                pass
        await show(update, context,
                   f"<b>Вам подарили доступ</b>\n\n◆ {plural_days(g['days'])}, {plural_dev(g['devices'])}\n"
                   f"◆ «{esc(sub['name'])}» действует до <b>{fmt_date(sub['expires_at'])}</b>",
                   KB([B("🗝 Открыть ключ", f"sub:{sub['id']}")], [BACK]), banner="welcome", effect=CONFETTI)
        return
    status, days = db.redeem_promo(code, uid)
    if status == "not_found":
        code_failed(context, uid)
    if status != "ok":
        reason = {"not_found": "Такого промокода нет.", "used_up": "У этого промокода закончились активации.",
                  "already": "Вы уже использовали этот промокод."}[status]
        await show(update, context, f"<b>Промокод не принят</b>\n\n{reason}",
                   KB([B("🎟 Ввести другой", "promo"), BACK]))
        return
    promo = db.get_promo(code)
    if promo and promo["percent"] > 0:
        db.set_offer(uid, promo["percent"], promo["hours"], reason=f"promo {promo['code']}")
        o = db.get_offer(uid)
        if o and o["percent"] > promo["percent"]:
            note = f"У вас уже есть скидка больше — {o['percent']}%, она и останется."
        else:
            note = "Скидка уже учтена в ценах тарифов."
        await refresh_menu(context, uid)
        await show(update, context,
                   f"<b>Промокод принят</b>\n\n🎁 Скидка <b>{promo['percent']}%</b> на оплату подписки "
                   f"(разово) — действует {plural_hours(promo['hours'])}.\n{note}",
                   KB([B("◆ Выбрать тариф", "plans")], [BACK]), banner="plans", effect=CONFETTI)
        return
    sub = await grant_days(uid, days)
    await refresh_menu(context, uid)
    await show(update, context,
               f"<b>Промокод принят</b>\n\n◆ Начислено <b>+{plural_days(days)}</b>\n"
               f"◆ «{esc(sub['name'])}» действует до <b>{fmt_date(sub['expires_at'])}</b>",
               KB([B("🗝 Мои подписки", "subs"), BACK]), banner="welcome")


async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    if not context.args:
        context.user_data["await"] = "promo"
        await update.message.reply_text("🎟 Отправьте промокод или подарочный код одним сообщением.")
        return
    await redeem(update, context, context.args[0])


# ---------------------------------------------------------------- админка

# Команды админа: меню «/» у админов (setup_profile) и экран «📋 Все команды»
ADMIN_COMMANDS = [
    ("admin", "Админ-панель: статистика и рассылка"),
    ("locations", "Страны и мосты"),
    ("addloc", "Добавить страну: /addloc код Название | прокси"),
    ("delloc", "Убрать страну: /delloc код"),
    ("webshare", "Купленные прокси (Webshare)"),
    ("autoproxy", "Бесплатные авто-страны"),
    ("addbridge", "Добавить мост: /addbridge код Название | IP | ru"),
    ("delbridge", "Убрать мост: /delbridge код"),
    ("bridgesite", "Сайт маскировки мостов"),
    ("sni", "Сайт маскировки"),
    ("bs", "Обход белых списков без моста"),
    ("pay", "Оплата картой (ЮKassa) и криптой"),
    ("payments", "Платежи и возвраты: /payments id или @ник"),
    ("give", "Начислить дни: /give id дней"),
    ("addpromo", "Промокод: /addpromo КОД 7|20% активаций"),
    ("promos", "Все промокоды"),
    ("chat", "Чат в приложении: вкл/выкл"),
    ("security", "Проверка безопасности сервера"),
    ("delpromo", "Удалить промокод"),
    ("refund", "Возврат звёзд: /refund charge_id"),
    ("testpay", "Тестовая оплата"),
    ("server", "Состояние сервера"),
    ("update", "Обновить сервер сейчас"),
    ("backup", "Резервная копия"),
    ("traffic", "Трафик и устройства"),
    ("funnel", "Воронка продаж"),
]
# Кнопки админ-панели, которые просто запускают команду без параметров
ADMIN_BUTTONS = {"loc": "locations", "auto": "autoproxy", "ws": "webshare", "pay": "pay",
                 "sni": "sni", "bs": "bridgesite", "wl": "bs", "upd": "update", "sec": "security"}


def commands_text() -> str:
    return ("<b>Все команды админа</b>\n<i>Они же в меню «/» рядом с полем ввода.</i>\n\n"
            + "\n".join(f"/{c} — {esc(d)}" for c, d in ADMIN_COMMANDS)
            + "\n\nТикеты: ответьте на сообщение гостя, и ответ уйдёт ему.")


def cmd_stub(update, context):
    """update для запуска команды кнопкой: ответы команды приходят новым сообщением в этот чат."""
    chat = update.effective_chat

    async def reply_text(text, **kw):
        return await context.bot.send_message(chat.id, text, **kw)

    async def delete():
        return True
    msg = types.SimpleNamespace(reply_text=reply_text, delete=delete, text="", chat_id=chat.id)
    return types.SimpleNamespace(effective_user=update.effective_user, effective_chat=chat,
                                 callback_query=None, message=msg)


def admin_text() -> str:
    s = db.stats()
    return ("<b>Админ-панель</b>\n\n"
            f"<blockquote>◆ Гостей: <b>{s['users']}</b> (+{s['new_today']} за сутки)\n"
            f"◆ С активным доступом: <b>{s['active']}</b> · подписок: {s['subs']}\n"
            f"◆ С автопродлением: {s['auto']}\n"
            f"◆ Брали пробный период: {s['trials']}\n"
            f"◆ Оплат: {s['payments']}\n"
            f"◆ Выручка: <b>{s['stars']} ⭐</b> (+{s['stars_today']} за сутки)"
            + (f"\n◆ Рублями (карта, крипта): <b>{s['rub']} ₽</b>" if s.get("rub") else "") + "</blockquote>\n\n"
            "Разделы — кнопками ниже, все команды — в меню «/» рядом с полем ввода и по кнопке "
            "«📋 Все команды».")


def admin_kb() -> InlineKeyboardMarkup:
    return KB([B("💳 Платежи", "adm:pays"), B("📢 Рассылка", "adm:bc")],
              [B("📈 Воронка", "adm:fun"), B("📊 Трафик", "adm:trf")],
              [B("🖥 Сервер", "adm:srv"), B("💾 Резервная копия", "adm:bak")],
              [B("🌍 Страны и мосты", "adm:run:loc"), B("🤖 Авто-страны", "adm:run:auto")],
              [B("🛒 Купленные прокси", "adm:run:ws"), B("💰 Карта и крипта", "adm:run:pay")],
              [B("🎭 Маскировка", "adm:run:sni"), B("🌉 Сайт мостов", "adm:run:bs")],
              [B("🛡 Обход белых списков", "adm:run:wl"), B("🔐 Безопасность", "adm:run:sec")],
              [B("⬆️ Обновить сервер", "adm:run:upd"), B("📋 Все команды", "adm:cmds")],
              *([[B("🧩 Happ/v2rayNG: JSON-конфиги · выключить" if vpn.json_sub
                    else "🧩 Happ/v2rayNG: обычные ссылки · включить JSON", "adm:json")]]
                if hasattr(vpn, "json_sub") else []),
              [B("🔄 Обновить", "adm:stats"), BACK])


def pct(part: int, whole: int) -> str:
    return f"{round(part * 100 / whole)}%" if whole else "—"


def funnel_text() -> str:
    def block(f) -> str:
        return (f"◆ Запустили бота: <b>{f['users']}</b>\n"
                f"◆ Взяли пробный: {f['trial']} ({pct(f['trial'], f['users'])})\n"
                f"◆ Оплатили: <b>{f['paid']}</b> ({pct(f['paid'], f['users'])})\n"
                f"◆ Из пробного в оплату: {pct(f['trial_paid'], f['trial'])} "
                f"({f['trial_paid']} из {f['trial']})\n"
                f"◆ Платили 2 раза и больше: {f['repeat']} ({pct(f['repeat'], f['paid'])} от оплативших)\n"
                f"◆ Оплат по персональной скидке: {f['offers_used']}")
    return ("<b>Воронка продаж</b>\n\n<b>За всё время</b>\n<blockquote>" + block(db.funnel()) + "</blockquote>\n\n"
            "<b>Гости за 30 дней</b>\n<blockquote>" + block(db.funnel(time.time() - 30 * DAY)) + "</blockquote>\n\n"
            "<i>Где процент резко падает, там гости и уходят.</i>")


def traffic_text() -> str:
    lines = [f"◆ Всего через VPN: <b>{fmt_bytes(db.total_traffic())}</b>"]
    mode = {"block": "предупреждение, потом отключение на "
                     f"{config.DEVICE_BLOCK_MINUTES} мин", "warn": "только предупреждение",
            "off": "не проверяется"}[guard.mode]
    lines.append(f"◆ Лимит устройств: {mode}")
    if guard.last_at:
        online = sum(1 for n in guard.last.values() if n)
        lines.append(f"◆ Онлайн подписок: {online} (замер {_ago(guard.last_at)} назад)")
    if guard.blocked:
        lines.append(f"◆ Отключены за превышение: {len(guard.blocked)}")
    head = "<b>Трафик и устройства</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
    top = []
    for s in db.top_traffic(10):
        used = (s["up_bytes"] or 0) + (s["down_bytes"] or 0)
        if not used:
            continue
        who_ = f"@{esc(s['username'])}" if s["username"] else esc(s["first_name"] or str(s["user_id"]))
        dev = guard.last.get(s["id"])
        line = (f"◆ {who_} · {esc(s['name'])} · {fmt_bytes(used)}"
                + (f" · онлайн {dev} из {s['devices']}" if dev else ""))
        if len(head) + len("<b>Больше всех</b>\n") + sum(len(t) + 1 for t in top) + len(line) > 1000:
            break  # подпись к картинке в Telegram не длиннее 1024 символов
        top.append(line)
    return head + ("<b>Больше всех</b>\n" + "\n".join(top) if top else "<i>Трафика пока нет.</i>")


def fmt_span(sec: float) -> str:
    sec = int(sec)
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return f"{d} д {h} ч" if d else (f"{h} ч {m} мин" if h else f"{m} мин")


def fmt_gb(n: float) -> str:
    return f"{n / 2**30:.1f} ГБ"


async def port_open(port: int) -> bool:
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)
        w.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def server_text() -> str:
    """Состояние сервера, бота и VPN одним экраном, чтобы не заходить по SSH."""
    lines = [f"◆ Бот работает {fmt_span(time.time() - STARTED)}"]
    if vpn.is_demo:
        lines.append("◇ VPN: демо-режим, сервер не подключён")
    else:
        vpn_ok, sub_ok = await port_open(vpn.port), await port_open(vpn.sub_port)
        if vpn.xray_enabled:
            lines.append(f"{'✅' if vpn_ok else '❌'} VPN (порт {vpn.port}): "
                         + ("принимает подключения" if vpn_ok else "не отвечает"))
        else:
            lines.append("◇ Xray выключен (XRAY_ENABLED=0): VPN идёт только через Hysteria")
        if vpn.sub_domain:
            lines.append(("✅" if vpn.sub_https else "❌") + f" Подписка по HTTPS: {esc(vpn.sub_domain)}"
                         + ("" if vpn.sub_https else ", не запустилась, ссылки идут по HTTP"))
        lines.append(f"{'✅' if sub_ok else '❌'} Подписки (порт {vpn.sub_port}): "
                     + ("раздаются" if sub_ok else "не раздаются"))
        if getattr(vpn, "guard", None):
            g = vpn.guard
            lines.append(f"🛡 Защита подписок: отброшено соединений {g.dropped}, адресов в бане {g.bans()}")
        if vpn.last_error:
            lines.append("❌ Последняя ошибка VPN:\n<code>" + esc(vpn.last_error[:300]) + "</code>")
        elif vpn.last_apply:
            lines.append(f"◆ Настройки VPN применены {fmt_span(time.time() - vpn.last_apply)} назад")
        if vpn.xray_enabled:
            lines.append(f"◆ Перезапусков Xray: {vpn.restarts}, изменений клиентов без перезапуска: "
                         f"{vpn.hot_updates}")
        if vpn.hy2:
            hy_ok, online = await vpn.hy2_running(), await vpn.hy2_online()
            lines.append(f"{'✅' if hy_ok else '❌'} Hysteria (UDP): " + ("работает" if hy_ok else "не запущена")
                         + (f", сейчас подключено: {online}" if online is not None else "")
                         + f", входов с запуска бота: {vpn.hy2_logins}")
        if vpn.xhttp_enabled:
            lines.append("◆ Запасной вход XHTTP: " + ("отключён, Xray его не принял" if vpn.xhttp_off
                                                     else "работает"))
        hidden = sum(1 for l in vpn.locations if l.get("down"))
        lines.append(f"◆ Стран: {len(vpn.locations)}" + (f" (скрыто: {hidden})" if hidden else "")
                     + f", мостов: {len(vpn.bridges)}")
    try:
        load = os.getloadavg()[0]
        lines.append(f"◆ Нагрузка: {load:.2f} на {os.cpu_count() or 1} яд.")
    except OSError:
        pass
    try:
        with open("/proc/meminfo") as f:
            mem = {k: int(v.split()[0]) * 1024 for k, v in (line.split(":", 1) for line in f)}
        used = mem["MemTotal"] - mem["MemAvailable"]
        lines.append(f"◆ Память: {fmt_gb(used)} из {fmt_gb(mem['MemTotal'])}")
    except (OSError, KeyError, ValueError):
        pass
    du = shutil.disk_usage("/")
    lines.append(f"◆ Диск: {fmt_gb(du.used)} из {fmt_gb(du.total)}")
    st = db.stats()
    lines.append(f"◆ Гостей: {st['users']}, активных подписок: {st['subs']}")
    return "<b>Сервер</b>\n\n<blockquote>" + "\n".join(lines) + "</blockquote>"


def make_backup() -> list[tuple[str, bytes]]:
    """Согласованная копия базы и настроек VPN (секрет, страны, мосты)."""
    files = []
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        dst = sqlite3.connect(tmp.name)
        db.conn.backup(dst)
        dst.close()
        with open(tmp.name, "rb") as f:
            files.append(("bot.db", f.read()))
    finally:
        os.unlink(tmp.name)
    state = getattr(vpn, "state_path", None)
    if state and os.path.exists(state):
        with open(state, "rb") as f:
            files.append(("vpn.json", f.read()))
    return files


async def _run(*cmd, data: bytes | None = None, env: dict | None = None, timeout: float = 300) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, **(env or {})})
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 1, b"timeout"
    return proc.returncode, out


async def pack_backup(files: list[tuple[str, bytes]], stamp: str) -> tuple[str, bytes]:
    """Один архив с базой и настройками VPN. С паролем (BACKUP_PASSWORD) он шифруется AES-256:
    расшифровать можно командой openssl, которая есть на любом сервере."""
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o600
            tar.addfile(info, io.BytesIO(data))
    name, blob = f"aurora-{stamp}.tar.gz", buf.getvalue()
    if config.BACKUP_PASSWORD:
        code, out = await _run("openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
                               "-pass", "env:AURORA_BACKUP_PASSWORD", data=blob,
                               env={"AURORA_BACKUP_PASSWORD": config.BACKUP_PASSWORD})
        if code != 0:
            raise RuntimeError("openssl не зашифровал копию: " + out.decode(errors="replace")[-300:])
        name, blob = name + ".enc", out
    return name, blob


DECRYPT_HINT = ("openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in ФАЙЛ.tar.gz.enc | tar xz")


async def send_backup(bot, chat_id: int) -> int:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    files = make_backup()
    if config.BACKUP_PASSWORD:
        name, blob = await pack_backup(files, stamp)
        await bot.send_document(
            chat_id, document=io.BytesIO(blob), filename=name,
            caption=("💾 <b>Резервная копия</b> от " + stamp + ", зашифрована паролем из BACKUP_PASSWORD.\n"
                     f"Расшифровать: <code>{esc(DECRYPT_HINT)}</code>\nКак восстановить, написано в README."))
        return 1
    for i, (name, data) in enumerate(files):
        await bot.send_document(
            chat_id, document=io.BytesIO(data), filename=f"aurora-{stamp}-{name}",
            caption=("💾 <b>Резервная копия</b> от " + stamp + ".\nХраните файлы у себя и никому не "
                     "пересылайте: в них данные гостей. Как восстановить, написано в README.") if i == 0 else None)
    return len(files)


async def store_backup() -> list[str]:
    """Копия на диске сервера и, если задан BACKUP_RCLONE, в облаке. Возвращает список проблем."""
    problems = []
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    name, blob = await pack_backup(make_backup(), stamp)
    os.makedirs(config.BACKUP_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(config.BACKUP_DIR, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(blob)
    keep = max(1, config.BACKUP_KEEP)
    old = sorted(f for f in os.listdir(config.BACKUP_DIR) if f.startswith("aurora-") and ".tar.gz" in f)
    for f in old[:-keep]:
        os.unlink(os.path.join(config.BACKUP_DIR, f))
    if config.BACKUP_RCLONE:
        if not config.BACKUP_PASSWORD:
            problems.append("копия уходит в облако без шифрования: задайте BACKUP_PASSWORD в .env")
        remote = config.BACKUP_RCLONE.rstrip("/")
        try:
            code, out = await _run("rclone", "copyto", path, f"{remote}/{name}")
            if code != 0:
                problems.append("rclone не отправил копию: " + out.decode(errors="replace")[-300:])
            else:
                await _run("rclone", "delete", remote, "--min-age", f"{keep}d", "--include", "aurora-*")
        except OSError as e:
            problems.append(f"rclone не установлен: {e}")
    return problems


async def backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if db.stats()["users"] == 0:
        return
    try:
        problems = await store_backup()
    except Exception as e:
        log.exception("резервная копия на диск")
        problems = [f"копия на сервере не сохранилась: {e}"]
    for admin_id in config.ADMIN_IDS:
        try:
            await send_backup(context.bot, admin_id)
        except Exception as e:
            log.warning("резервная копия админу %s: %s", admin_id, e)
    if problems:
        await send_admins(context.bot, "⚠️ <b>Резервная копия</b>\n\n" + "\n".join(esc(p) for p in problems))


def who_paid(p) -> str:
    return f"@{esc(p['username'])}" if p["username"] else esc(p["first_name"] or str(p["user_id"]))


def payments_view(user_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    pays = db.list_payments(user_id, limit=8)
    title = "<b>Платежи</b>" if user_id is None else f"<b>Платежи гостя</b> <code>{user_id}</code>"
    if not pays:
        return title + "\n\nПлатежей пока нет.", KB([B("‹ Админ-панель", "adm:stats")])
    lines, buttons = [], []
    for p in pays:
        name = (config.TEST_PLAN if p["plan"] == "test" else config.PLANS.get(
            p["plan"], ("Устройства" if str(p["plan"]).startswith("up") else p["plan"],)))[0]
        mark = "↩️ возвращён" if p["refunded"] else "✅"
        lines.append(f"<b>#{p['id']}</b> · {fmt_date(p['created_at'])} · {who_paid(p)}\n"
                     f"{esc(name)} · {KIND_NAMES.get(p['kind'], p['kind'])} · {p['stars']} ⭐ · {mark}")
        if not p["refunded"]:
            buttons.append(B(f"↩️ Вернуть #{p['id']}", f"adm:rf:{p['id']}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([B("🔄 Обновить", "adm:pays"), B("‹ Админ-панель", "adm:stats")])
    text = title + "\n\n" + "\n\n".join(lines) + "\n\n<i>Последние 8. Поиск: /payments id или @ник</i>"
    return text, InlineKeyboardMarkup(rows)


async def do_refund(context: ContextTypes.DEFAULT_TYPE, charge: str) -> str:
    """Возвращает звёзды по платежу. Отдаёт текст результата для админа."""
    p = db.get_payment(charge)
    if not p:
        return "Платёж не найден."
    if p["refunded"]:
        return "Этот платёж уже возвращён."
    method = p["method"] if "method" in p.keys() else "stars"
    if method == "stars":
        try:
            await context.bot.refund_star_payment(p["user_id"], charge)
        except TelegramError as e:
            return f"Telegram не принял возврат: {esc(str(e))}"
    sub = db.mark_refunded(charge)
    if sub and p["kind"] == "upgrade" and str(p["plan"]).startswith("up") and str(p["plan"])[2:].isdigit():
        db.run("UPDATE subscriptions SET devices=? WHERE id=?", int(str(p["plan"])[2:]), sub["id"])
        sub = db.get_sub(sub["id"])
        if sub_active(sub):
            sub = await issue_key(sub["id"])
    if sub:
        if p["kind"] in ("auto", "renew") and sub["auto_active"]:
            await cancel_auto(context, sub)
            sub = db.get_sub(sub["id"])
        if not sub_active(sub) and sub["key_active"]:
            await vpn.revoke(sub["id"])
            db.set_key(sub["id"], sub["vpn_key"], False)
        await refresh_menu(context, sub["user_id"])
    if method != "stars":  # деньги возвращаются в кабинете ЮKassa или в @CryptoBot, бот снимает доступ
        where = "в личном кабинете ЮKassa" if method == "yookassa" else "в @CryptoBot (Crypto Pay → Счета)"
        return (f"Оплаченные дни списаны. Деньги ({esc(p['money'] or '')}) верните вручную {where}: "
                "бот сам вернуть их не может.")
    try:
        await context.bot.send_message(p["user_id"], f"↩️ Вам возвращено {p['stars']} ⭐.")
    except TelegramError:
        pass
    return f"Возвращено {p['stars']} ⭐, оплаченные дни списаны."


async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE, row, parts: list[str]) -> None:
    q = update.callback_query
    if row["id"] not in config.ADMIN_IDS:
        await q.answer()
        return
    act = parts[1] if len(parts) > 1 else ""
    if act in ("sec", "secfix"):
        await q.answer("Проверяю…")
        if act == "secfix":
            audit, _, _ = security_audit()
            n = audit.fix_perms()
            await context.bot.send_message(update.effective_chat.id, f"🔧 Исправлено файлов: {n}.")
        text, found = await run_security()
        context.bot_data["sec_seen"] = sorted(found)
        await context.bot.send_message(update.effective_chat.id, text[:4000],
                                       reply_markup=KB([B("🔧 Исправить права файлов", "adm:secfix"),
                                                        B("🔄 Проверить снова", "adm:sec")]))
        return
    if act in ("rf", "rfok") and len(parts) == 3 and parts[2].isdigit():
        p = db.get_payment_by_id(int(parts[2]))
        if not p:
            await q.answer("Платёж не найден", show_alert=True)
            return
        if act == "rf":
            await q.answer()
            await show(update, context,
                       f"<b>Вернуть платёж #{p['id']}?</b>\n\n"
                       f"◆ Гость: {who_paid(p)} (<code>{p['user_id']}</code>)\n"
                       f"◆ Сумма: <b>{p['stars']} ⭐</b> · {KIND_NAMES.get(p['kind'], p['kind'])}\n"
                       f"◆ Дата: {fmt_date(p['created_at'])}\n\n"
                       "Звёзды вернутся гостю, оплаченные дни спишутся, автопродление отключится.",
                       KB([B("↩️ Да, вернуть", f"adm:rfok:{p['id']}"), B("Отмена", "adm:pays")]))
            return
        result = await do_refund(context, p["charge_id"])
        await q.answer(result[:190], show_alert=True)
        text, kb = payments_view()
        await show(update, context, text, kb)
        return
    if act == "cmds":
        await q.answer()
        await context.bot.send_message(update.effective_chat.id, commands_text(),
                                       reply_markup=KB([B("‹ Админ-панель", "adm:stats")]))
        return
    if act == "run" and len(parts) == 3 and parts[2] in ADMIN_BUTTONS:
        await q.answer()
        fn = {"locations": locations, "autoproxy": autoproxy, "webshare": webshare_cmd, "pay": pay_cmd,
              "sni": sni_cmd, "bridgesite": bridgesite_cmd, "bs": bs_cmd,
              "update": update_cmd}[ADMIN_BUTTONS[parts[2]]]
        saved_args = context.args
        context.args = []
        try:
            await fn(cmd_stub(update, context), context)
        finally:
            context.args = saved_args
        return
    if act == "bak":
        await q.answer("Отправляю копию 👇")
        await send_backup(context.bot, row["id"])
        return
    await q.answer("Обновлено" if act in ("stats", "pays", "srv", "fun", "trf") else None)
    if act == "json" and hasattr(vpn, "json_sub"):
        vpn.state["json_sub"] = not vpn.json_sub
        vpn._save()
        await q.answer("Happ и v2rayNG получают готовые JSON-конфиги: в приложении видно только страну"
                       if vpn.json_sub else "Happ и v2rayNG снова получают обычные ссылки", show_alert=True)
        await show(update, context, admin_text(), admin_kb())
        return
    if act == "fun":
        await show(update, context, funnel_text(), KB([B("🔄 Обновить", "adm:fun"), B("‹ Админ-панель", "adm:stats")]))
    elif act == "trf":
        await show(update, context, traffic_text(), KB([B("🔄 Обновить", "adm:trf"), B("‹ Админ-панель", "adm:stats")]))
    elif act == "srv":
        await show(update, context, await server_text(),
                   KB([B("🔄 Обновить", "adm:srv"), B("‹ Админ-панель", "adm:stats")]))
    elif act == "stats":
        await show(update, context, admin_text(), admin_kb())
    elif act == "pays":
        text, kb = payments_view()
        await show(update, context, text, kb)
    elif act == "bc":
        context.user_data["await"] = "broadcast"
        await show(update, context,
                   "<b>Рассылка</b>\n\nОтправьте сообщение, и я перешлю его всем гостям. "
                   "Можно с картинкой и форматированием.",
                   KB([B("‹ Отмена", "adm:stats")]))


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id not in config.ADMIN_IDS:
            return
        await func(update, context)
    return wrapper


@admin_only
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    await show(update, context, admin_text(), admin_kb())


@admin_only
async def server(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    await show(update, context, await server_text(),
               KB([B("🔄 Обновить", "adm:srv"), B("‹ Админ-панель", "adm:stats")]))


def code_version() -> tuple[str, str]:
    """(коммит, его заголовок) кода, который сейчас запущен, или пустые строки без git."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(["git", "-C", root, "log", "-1", "--format=%H%n%s"], capture_output=True,
                             text=True, timeout=10).stdout.split("\n", 1)
    except (OSError, subprocess.SubprocessError):
        return "", ""
    return (out[0].strip(), out[1].strip()) if len(out) == 2 and out[0].strip() else ("", "")


async def remote_version() -> tuple[str, str] | None:
    """(коммит, ветка) обновления, которое поставит сервер; ("", "") — нового нет; None — узнать не вышло.
    Спрашивает тот же скрипт, что и таймер: он сам выбирает свежую ветку-продолжение."""
    try:
        proc = await asyncio.create_subprocess_exec("/usr/local/bin/aurora-update", "check",
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), 60)
    except (OSError, asyncio.TimeoutError):
        return None
    parts = out.decode().split()
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")


VERSION_FILE = os.path.join(os.path.dirname(config.DB_PATH), ".running_version")


async def announce_update(bot) -> None:
    """После автообновления пишет админам, что сервер обновился и на что."""
    sha, title = code_version()
    if not sha:
        return
    try:
        with open(VERSION_FILE) as f:
            old = f.read().strip()
    except OSError:
        old = ""
    if old == sha:
        return
    with open(VERSION_FILE, "w") as f:
        f.write(sha)
    if old and bot_code_changed(old, sha):
        await send_admins(bot, f"🔄 Сервер обновился сам: <b>{esc(title)}</b>\n<code>{sha[:7]}</code>")


def bot_code_changed(old: str, new: str) -> bool:
    """Менялся ли код сервера (vpn-bot/) между версиями. Правки приложения и заметок — нет.
    Если git не ответил (старая версия стёрта и т. п.), считаем, что менялся."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(["git", "-C", root, "diff", "--quiet", old, new, "--", "vpn-bot"],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    return r.returncode != 0


@admin_only
async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обновить сервер сейчас, не дожидаясь проверки раз в 10 минут."""
    current_user(update)
    if not os.path.exists("/etc/systemd/system/aurora-update.service"):
        await update.effective_chat.send_message(
            "Автообновление ещё не настроено: один раз запустите установщик из Termius.")
        return
    sha, title = code_version()
    remote = await remote_version()
    if remote == ("", ""):
        await update.effective_chat.send_message(
            f"✅ Уже стоит последняя версия: <b>{esc(title)}</b> <code>{sha[:7]}</code>\n"
            "Новых изменений нет. Как только они появятся, сервер обновится сам в течение 10 минут.")
        return
    proc = await asyncio.create_subprocess_exec("systemctl", "start", "--no-block", "aurora-update.service",
                                                stdout=asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode:
        await update.effective_chat.send_message(f"Не удалось запустить обновление: {esc(err.decode()[-300:])}")
        return
    await update.effective_chat.send_message(
        f"🔄 Есть новая версия <code>{(remote[0] if remote else '?')[:7]}</code>"
        + (f" в ветке <code>{esc(remote[1])}</code>" if remote else "")
        + f" (сейчас <code>{sha[:7] or '?'}</code>). "
        "Ставлю: это займёт пару минут. Если менялся код сервера, бот перезапустится и напишет «Сервер обновился сам».")


@admin_only
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_backup(context.bot, update.effective_user.id)


@admin_only
async def funnel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    await show(update, context, funnel_text(), KB([B("🔄 Обновить", "adm:fun"), B("‹ Админ-панель", "adm:stats")]))


@admin_only
async def traffic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    await show(update, context, traffic_text(), KB([B("🔄 Обновить", "adm:trf"), B("‹ Админ-панель", "adm:stats")]))


@admin_only
async def payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    user_id = None
    if context.args:
        found = db.find_user(context.args[0])
        if not found:
            await update.message.reply_text("Гость не найден. Укажите ID или @ник.")
            return
        user_id = found["id"]
    text, kb = payments_view(user_id)
    await show(update, context, text, kb)


@admin_only
async def refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Формат: /refund <code>charge_id</code>. Проще через /payments: "
                                        "там кнопка возврата.")
        return
    await update.message.reply_text(await do_refund(context, context.args[0]))


@admin_only
async def testpay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    name, days, price = config.TEST_PLAN
    await update.message.reply_text(
        f"Тестовый счёт на {price} ⭐. После оплаты придёт уведомление, вернуть звёзды можно в /payments.")
    await context.bot.send_invoice(chat_id=update.effective_chat.id, title=f"{config.BRAND} · {name}",
                                   description="Проверка оплаты и возврата.",
                                   payload=f"v2:b:test:{days}:{price}:1:0:-", provider_token="",
                                   currency="XTR", prices=[LabeledPrice(name, price)])


@admin_only
async def give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        uid, days = int(context.args[0]), int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Формат: /give <code>id</code> <code>дней</code>")
        return
    if not db.get_user(uid):
        await update.message.reply_text("Такого гостя нет в боте.")
        return
    sub = await grant_days(uid, days)
    await refresh_menu(context, uid)
    await update.message.reply_text(f"Начислено {plural_days(days)} в «{esc(sub['name'])}». "
                                    f"Доступ до {fmt_date(sub['expires_at'])}.")
    try:
        await context.bot.send_message(uid, f"🎁 Вам начислено <b>+{plural_days(days)}</b> доступа.")
    except TelegramError:
        pass


PROMO_HELP = ("<b>Промокоды</b>\n\n"
              "/addpromo <code>КОД 7 100</code> — +7 дней, 100 активаций\n"
              "/addpromo <code>КОД 20% 100</code> — скидка 20% на разовую оплату, 100 активаций, "
              "действует 72 часа после ввода\n"
              "/addpromo <code>КОД 30% 50 24</code> — скидка 30%, 50 активаций, 24 часа\n"
              "/promos — все промокоды, /delpromo <code>КОД</code> — удалить\n\n"
              "Гость вводит код в меню «🎟 Промокод» или ссылкой "
              "<code>t.me/бот?start=promo_КОД</code>.")


@admin_only
async def addpromo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    a = context.args or []
    try:
        code, amount, uses = a[0], a[1], int(a[2])
        hours = int(a[3]) if len(a) > 3 else 72
        percent = int(amount.rstrip("%")) if amount.endswith("%") else 0
        days = 0 if percent else int(amount)
    except (IndexError, ValueError):
        await update.message.reply_text(PROMO_HELP)
        return
    if code.upper().startswith("GIFT-"):
        await update.message.reply_text("Промокод не может начинаться с GIFT-: так начинаются подарочные коды.")
        return
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", code) or uses < 1 or not (0 < percent < 100 or days > 0) \
            or not 1 <= hours <= 24 * 90:
        await update.message.reply_text("Код — латиница и цифры; скидка от 1 до 99%; дней и активаций больше 0.\n\n"
                                        + PROMO_HELP)
        return
    db.add_promo(code, days, uses, percent, hours)
    what = f"скидка {percent}% на {plural_hours(hours)}" if percent else f"+{plural_days(days)}"
    link = f"https://t.me/{STATE['username'] or context.bot.username}?start=promo_{code.upper()}"
    await update.message.reply_text(
        f"Промокод <code>{esc(code.upper())}</code>: {what}, активаций: {uses}.\n\nСсылка для гостей: {link}")


def security_audit():
    """Проверка безопасности этой машины: файлы с секретами и порты, которые мы открываем сами."""
    import security
    data = os.path.dirname(os.path.abspath(config.DB_PATH))
    files = [config.DB_PATH, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), pay_cfg.path]
    expected: set[int] = set()
    if hasattr(vpn, "state_path"):
        sdir = os.path.dirname(vpn.state_path)
        files += [vpn.state_path, os.path.join(sdir, "chat.json"), os.path.join(sdir, "auto_cache.json")]
        expected |= {p for p in (getattr(vpn, "port", 0), getattr(vpn, "sub_port", 0), getattr(vpn, "sub_tls_port", 0),
                                 getattr(vpn, "bridge_port", 0)) if p}
        hy = getattr(vpn, "hy2", None) or {}
        expected |= {p for p in (hy.get("port"), hy.get("obfs_port")) if p}
        expected |= set(vpn.state.get("hy2_ports", {}).values())
        expected |= set(range(30000, 30050))
    files = [f for f in dict.fromkeys(files) if f and os.path.exists(f)]
    return security.Audit(files, expected), security, data


async def run_security() -> tuple[str, set[str]]:
    audit, sec, _ = security_audit()
    results = await asyncio.to_thread(audit.check)
    return sec.report(results), sec.problems(results)


@admin_only
async def security_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка безопасности сервера: SSH, файрвол, перебор паролей, порты, права файлов, обновления."""
    if vpn.is_demo:
        await update.message.reply_text("Проверка работает на настоящем сервере.")
        return
    msg = await update.message.reply_text("🔐 Проверяю сервер… (до минуты)")
    text, found = await run_security()
    context.bot_data["sec_seen"] = sorted(found)
    kb = KB([B("🔧 Исправить права файлов", "adm:secfix"), B("🔄 Проверить снова", "adm:sec")])
    try:
        await msg.edit_text(text[:4000], reply_markup=kb)
    except TelegramError:
        await update.message.reply_text(text[:4000], reply_markup=kb)


async def security_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в сутки: если появились новые проблемы безопасности — сообщить админам."""
    if vpn.is_demo:
        return
    text, found = await run_security()
    seen = set(context.bot_data.get("sec_seen", []))
    if found - seen:
        await send_admins(context.bot, "🔐 <b>Новые проблемы безопасности сервера</b>\n\n" + text[:3500])
    context.bot_data["sec_seen"] = sorted(found)


@admin_only
async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Зашифрованный чат приложения Arise: включить, выключить, сколько людей."""
    chat = getattr(vpn, "chat", None)
    if not chat:
        await update.message.reply_text("Чат работает только с настоящим VPN-сервером.")
        return
    args = [a.lower() for a in context.args or []]
    if args[:1] in (["on"], ["off"]):
        chat.data["enabled"] = args[0] == "on"
        chat._save()
    users = len(chat.data["users"])
    queued = sum(len(b) for b in chat.data["boxes"].values())
    await update.message.reply_text(
        f"<b>💬 Чат в приложении Arise</b>\n\n◆ {'✅ включён' if chat.data['enabled'] else '◇ выключен'}\n"
        f"◆ Пользователей: {users}\n◆ Писем ждут получателей: {queued}\n\n"
        "Сервер хранит только шифр: прочитать переписку нельзя ни здесь, ни на сервере.\n\n"
        "/chat on, /chat off — включить или выключить. То же можно сделать в приложении: "
        "у твоей подписки там раздел «Админ».")


@admin_only
async def promos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.list_promos()
    if not rows:
        await update.message.reply_text("Промокодов нет.\n\n" + PROMO_HELP)
        return
    lines = [f"<code>{esc(r['code'])}</code> · "
             + (f"−{r['percent']}% на {plural_hours(r['hours'])}" if r["percent"] else f"+{plural_days(r['days'])}")
             + f" · использовано {r['used']}, осталось {max(0, r['uses_left'])}" for r in rows]
    await update.message.reply_text("<b>Промокоды</b>\n\n" + "\n".join(lines[:60]) + "\n\n/delpromo КОД — удалить")


@admin_only
async def delpromo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Формат: /delpromo <code>КОД</code>")
        return
    ok = db.del_promo(context.args[0])
    await update.message.reply_text("Промокод удалён." if ok else "Такого промокода нет.")


def xray_warning() -> str:
    """Предупреждение, если Xray не принял последний конфиг."""
    err = getattr(vpn, "last_error", "")
    return f"⚠️ {esc(err)}\n\n" if err else ""


def locations_text() -> str:
    lines = []
    for l in getattr(vpn, "locations", []):
        how = "через прокси" if l["proxy"] else "напрямую с сервера"
        tag = " · 🤖 авто" if l.get("auto") else ""
        state = (" · ❌ прокси не отвечает, скрыта" if l.get("down") else
                 " · ⚠️ прокси не отвечает" if l.get("failing") else "")
        hy_port = vpn.hy2_loc_port(l) if hasattr(vpn, "hy2_loc_port") else None
        hy = f" · Hysteria UDP {hy_port}" if hy_port else ""
        lines.append(f"◆ <code>{esc(l['code'])}</code> · {esc(l['name'])} · <i>{how}</i>{tag}{hy}{state}")
    def bridge_line(b):
        if b.get("ru"):
            mask = (f" · белые списки, маскировка {esc(vpn.bridge_site)}" if vpn.bridge_site
                    else " · белые списки, сайт маскировки не выбран: /bridgesite next")
        else:
            mask = f" · маскировка {esc(b['sni'])}" if b["sni"] else ""
        state = " · ❌ не отвечает" if b.get("down") else ""
        return f"◆ <code>{esc(b['code'])}</code> · {esc(b['name'])} · {esc(b['host'])}:{b['port']}{mask}{state}"
    bridges = [bridge_line(b) for b in getattr(vpn, "bridges", [])]
    off = ("ℹ️ Xray выключен: все страны работают только через Hysteria (UDP). Подключение по TCP "
           "включается так: XRAY_ENABLED=1 в .env и перезапуск бота.\n\n"
           if not getattr(vpn, "xray_enabled", True) else "")
    return (xray_warning() + off + "<b>Страны</b>\n\n" + "\n".join(lines) + "\n\n"
            "Добавить: /addloc <code>код</code> <code>Название</code> | <code>socks5://логин:пароль@ip:порт</code>\n"
            "Удалить: /delloc <code>код</code>\n\n"
            "<b>Мосты для обхода</b>\n\n" + ("\n".join(bridges) if bridges else "<i>пока нет</i>") + "\n\n"
            "Добавить: /addbridge <code>код</code> <code>Название</code> | <code>IP моста</code> | <code>ru</code>\n"
            "Пример: <code>/addbridge ru1 🇷🇺 Обход | 1.2.3.4 | ru</code>\n"
            "Поле <code>ru</code> для моста, поставленного установщиком этой версии: он маскируется "
            "под российский сайт и проходит белые списки. Сайт: /bridgesite\n"
            "Удалить: /delbridge <code>код</code>")


@admin_only
async def locations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "locations"):
        await update.message.reply_text("Страны настраиваются, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    await update.message.reply_text(locations_text())


@admin_only
async def addloc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "add_location"):
        await update.message.reply_text("Страны настраиваются, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    text = update.message.text.split(maxsplit=1)
    try:
        head, proxy = text[1].split("|", 1)
        code, name = head.strip().split(maxsplit=1)
        vpn.add_location(code, name, proxy)
    except (IndexError, ValueError) as e:
        hint = f"\n\nОшибка: {esc(str(e))}" if isinstance(e, ValueError) and str(e) else ""
        await update.message.reply_text(
            "Формат: /addloc <code>код</code> <code>Название</code> | <code>socks5://логин:пароль@ip:порт</code>" + hint)
        return
    await update.message.reply_text(
        "Страна добавлена. Через пару секунд Xray перезапустится, и она появится у всех клиентов "
        "после обновления подписки.\n\n" + locations_text())


@admin_only
async def addbridge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "add_bridge"):
        await update.message.reply_text("Мосты настраиваются, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    fmt = ("Формат: /addbridge <code>код</code> <code>Название</code> | <code>IP моста</code> | <code>ru</code>\n"
           "Третье поле <code>ru</code> — для моста от установщика этой версии (обход белых списков). "
           "Для старого моста вместо него можно указать сайт маскировки: <code>| vk.com</code>")
    try:
        parts = [p.strip() for p in update.message.text.split(maxsplit=1)[1].split("|")]
        code, name = parts[0].split(maxsplit=1)
        extra = parts[2].lower() if len(parts) > 2 else ""
        ru = extra == "ru"
        vpn.add_bridge(code, name, parts[1], "" if ru else extra, ru=ru)
    except (IndexError, ValueError) as e:
        hint = f"\n\nОшибка: {esc(str(e))}" if isinstance(e, ValueError) and str(e) else ""
        await update.message.reply_text(fmt + hint)
        return
    if ru and not vpn.bridge_site:
        await update.message.reply_text("Мост добавлен. Подбираю для него российский сайт маскировки, "
                                        "результат пришлю сообщением.")
        context.application.create_task(_bridge_site_report(context.bot, update.effective_chat.id))
        return
    await update.message.reply_text("Мост добавлен. Он появится у всех клиентов после обновления подписки.\n\n"
                                    + locations_text())


async def pick_bridge_site(avoid=()) -> str | None:
    """Российский сайт для мостов, который отвечает с сервера и который Xray принимает."""
    for host, _ in await masking.ranked(h for h in masking.RU_SITES if h not in avoid):
        # Без Xray мост работает только через Hysteria: ей хватает, что сайт отвечает.
        if not getattr(vpn, "xray_enabled", True) or await vpn.site_flagged(host) is not None:
            return host
    return None


async def switch_bridge_site(reason: str, site: str | None = None) -> str:
    async with mask_lock:
        old = vpn.bridge_site
        if site:
            if await masking.check(site) is None:
                return f"Сайт {site} не подходит: с сервера он не отвечает по TLS 1.3 и HTTP/2."
            new = site
        else:
            new = await pick_bridge_site({old} if old else ()) or await pick_bridge_site()
            if not new:
                return "Ни один российский сайт из списка сейчас не отвечает с сервера. Мосты «ru» пока скрыты."
        if new == old:
            return f"Сайт маскировки мостов уже {old}."
        vpn.set_bridge_site(new)
        MASK["bridge_fails"] = 0
        return (f"🌉 Сайт маскировки мостов: {old or 'не был выбран'} → {new}\nПричина: {reason}.\n\n"
                "Клиенты получат новые ключи мостов при обновлении подписки.")


async def _bridge_site_report(bot, chat_id: int, site: str | None = None) -> None:
    try:
        text = esc(await switch_bridge_site("новый мост" if not site else "команда администратора", site))
        await _send_report(bot, chat_id, text + "\n\n" + locations_text())
    except Exception as e:
        await _report_failure(bot, chat_id, "Подбор сайта для мостов не удался", e)


@admin_only
async def bridgesite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "bridge_site"):
        await update.message.reply_text("Мосты настраиваются, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    arg = (context.args[0].lower() if context.args else "")
    if arg == "next" or masking.valid_name(arg):
        await update.message.reply_text("Проверяю сайт с сервера. Результат пришлю сообщением.")
        context.application.create_task(
            _bridge_site_report(context.bot, update.effective_chat.id, None if arg == "next" else arg))
        return
    await update.message.reply_text(
        "<b>Сайт маскировки мостов</b>\n\n"
        f"Сейчас: <code>{esc(vpn.bridge_site or 'не выбран')}</code>\n\n"
        "Мосты «ru» выдают себя за российский сайт: при белых списках оператор пропускает только "
        "сайты из списка. Раз в 10 минут бот проверяет сайт и при сбое ставит другой.\n\n"
        "/bridgesite next: подобрать другой\n/bridgesite vk.com: поставить этот")


@admin_only
async def delbridge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "remove_bridge") or not context.args:
        await update.message.reply_text("Формат: /delbridge <code>код</code>")
        return
    ok = vpn.remove_bridge(context.args[0])
    await update.message.reply_text(("Удалено.\n\n" if ok else "Такого моста нет.\n\n") + locations_text())


async def proxy_health_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 10 минут проверяет прокси стран и сообщает админам об изменениях."""
    if not hasattr(vpn, "check_proxies"):
        return
    if hasattr(vpn, "check_bridges"):
        for b, alive in await vpn.check_bridges():
            await notify_admins(context, (f"✅ Мост «{esc(b['name'])}» снова отвечает." if alive else
                                          f"❌ Мост «{esc(b['name'])}» ({esc(b['host'])}) не отвечает. Проверьте, "
                                          "что сервер моста включён: <code>systemctl status nftables</code>."))
    for loc, alive in await vpn.check_proxies():
        await notify_admins(context, (f"✅ Прокси «{esc(loc['name'])}» снова работает."
                                      if alive else
                                      f"❌ Прокси «{esc(loc['name'])}» не отвечает. Страна остаётся в подписке, "
                                      "но через неё сейчас не открываются сайты. Проверьте прокси у продавца."))


@admin_only
async def delloc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "remove_location") or not context.args:
        await update.message.reply_text("Формат: /delloc <code>код</code>")
        return
    code = context.args[0].lower()
    was_auto = any(l["code"] == code for l in vpn.auto_locations())
    ok = vpn.remove_location(code)
    note = ""
    if ok and was_auto:  # иначе бот добавил бы страну обратно при следующей проверке
        cfg = vpn.auto
        vpn.set_auto(countries=[c for c in cfg.get("countries", []) if c != code],
                     exclude=list(dict.fromkeys(cfg.get("exclude", []) + [code])))
        auto_mgr.sync_routes()
        note = f"Бот больше не будет добавлять эту страну сам. Вернуть: /autoproxy include {esc(code)}\n\n"
    await update.message.reply_text(("Удалено.\n\n" if ok else "Такой страны нет, или она последняя.\n\n")
                                    + note + locations_text())


# ---------------------------------------------------------------- авто-страны (публичные прокси)

async def auto_proxy_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 5 минут перепроверяет авто-страны, меняет умершие прокси и добирает страны."""
    if auto_mgr:
        await auto_mgr.tick()


def _ago(ts: float) -> str:
    sec = max(0, int(time.time() - ts))
    if sec < 3600:
        return f"{max(1, sec // 60)} мин"
    if sec < 86400:
        return f"{sec // 3600} ч"
    return f"{sec // 86400} дн"


def auto_status_text() -> str:
    cfg = vpn.auto
    countries = cfg.get("countries") or []
    where = ", ".join(c.upper() for c in countries) if countries else f"подбор, до {cfg.get('max', 8)} стран"
    lines = [f"Статус: {'включены ✅' if cfg.get('enabled') else 'выключены ⛔'}",
             f"Страны: {esc(where)}",
             f"Сообщения о заменах: {'включены' if cfg.get('notify', True) else 'выключены'}"]
    if cfg.get("exclude"):
        lines.append("Не добавлять: " + ", ".join(c.upper() for c in cfg["exclude"]))
    if not auto_mgr.relay.running:
        lines.append(f"⚠️ Ретранслятор не запущен: порт {vpn.relay_port} занят. Авто-страны не работают, "
                     "поменяйте AUTO_RELAY_PORT в .env и перезапустите бота.")
    if auto_mgr.last_note:
        lines.append(f"ℹ️ Последняя проверка: {esc(auto_mgr.last_note)}")
    rows = []
    for l in vpn.auto_locations():
        if l.get("down"):
            rows.append(f"◆ {esc(l['name'])} · ❌ нет живых прокси, скрыта")
            continue
        host = l["proxy"].split("://", 1)[-1]
        speed = f" · {l['ms']} мс" if l.get("ms") else ""
        if public_proxies.SPEEDS.get(l["proxy"]):
            speed += f" · {public_proxies.SPEEDS[l['proxy']]} КБ/с"
        rows.append(f"◆ {esc(l['name'])} · <code>{esc(host)}</code>{speed} · запасных {len(l.get('pool', [])) - 1}"
                    f" · замен {l.get('swaps', 0)} · без замены {_ago(l.get('since', time.time()))}")
    return (xray_warning() + "<b>Авто-страны из публичных прокси</b>\n\n" + "\n".join(lines) + "\n\n"
            + ("\n".join(rows) if rows else "<i>Стран пока нет.</i>") + "\n\n"
            "Бот сам берёт бесплатные прокси из открытых списков, проверяет их и добавляет страны. "
            "Когда прокси перестаёт отвечать, подключения сразу идут через запасной, без перезапуска VPN.\n"
            "⚠️ Публичные прокси медленные и живут недолго, а их владельцы видят, к каким адресам идут "
            "подключения. Для платящих клиентов надёжнее купленные прокси (/addloc).\n\n"
            "<b>Команды</b>\n"
            "/autoproxy on: включить\n"
            "/autoproxy off: выключить и убрать авто-страны\n"
            "/autoproxy now: проверить и обновить сейчас\n"
            "/autoproxy test: проверить каждую страну так, как подключается клиент\n"
            "/autoproxy countries nl de us: держать эти страны\n"
            "/autoproxy countries auto: бот подбирает страны сам\n"
            "/autoproxy max 8: сколько стран держать при подборе\n"
            "/autoproxy notify off: не присылать сообщения о заменах\n"
            "/autoproxy include nl: снова разрешить страну, убранную через /delloc")


async def _send_report(bot, chat_id: int, text: str) -> None:
    """Отчёт должен дойти в любом случае: если Telegram не принял оформление, уходит простой текст."""
    try:
        await bot.send_message(chat_id, text)
    except TelegramError as e:
        log.exception("отчёт не отправлен с оформлением")
        plain = html.unescape(re.sub(r"<[^>]+>", "", text))[:3500]
        await bot.send_message(chat_id, f"{plain}\n\n(оформление убрано: {e})", parse_mode=None)


async def _report_failure(bot, chat_id: int, what: str, e: Exception) -> None:
    log.exception("авто-страны: %s", what)
    try:
        await bot.send_message(chat_id, f"{what}: {type(e).__name__}: {e}"[:1000], parse_mode=None)
    except TelegramError:
        pass


async def _auto_refresh_and_report(bot, chat_id: int) -> None:
    """Проверка идёт в фоне, чтобы бот в это время отвечал остальным."""
    try:
        msg = await auto_mgr.refresh()
        if not msg:
            msg = (f"⚠️ Проверка не выполнена: {esc(auto_mgr.last_note)}." if auto_mgr.last_note
                   else "Готово, изменений нет.")
        await _send_report(bot, chat_id, msg + "\n\n" + locations_text())
    except Exception as e:
        await _report_failure(bot, chat_id, "Проверка прокси не удалась", e)


async def _auto_selftest_and_report(bot, chat_id: int) -> None:
    try:
        lines = ["<b>Проверка авто-стран</b>", ""]
        lines.append("Xray: " + ("работает" if await vpn.xray_running() else "❌ не запущен"))
        if vpn.last_error:
            lines.append(f"⚠️ {esc(vpn.last_error)}")
        lines.append("Ретранслятор: " + ("работает" if auto_mgr.relay.running
                                          else f"❌ не запущен, порт {vpn.relay_port} занят"))
        lines.append("Выход в интернет с сервера: " + ("есть" if await public_proxies.direct_ok()
                                                        else "❌ проверочный сайт недоступен"))
        results = await auto_mgr.selftest()
        lines.append("")
        for loc, res in results:
            if res is None:
                lines.append(f"❌ {esc(loc['name'])}: подключение через прокси не проходит")
            elif res.country != loc["code"]:
                lines.append(f"⚠️ {esc(loc['name'])}: прокси выходит из {res.country.upper()}, {res.ms} мс")
            else:
                lines.append(f"✅ {esc(loc['name'])}: работает, {res.ms} мс")
        if not results:
            lines.append("<i>Авто-стран пока нет.</i>")
        elif all(r for _, r in results) and not vpn.last_error:
            lines.append("\nСо стороны сервера всё работает. Если страна не открывается в приложении, "
                         "обновите в нём подписку и проверьте основную страну: она идёт без прокси.")
        await _send_report(bot, chat_id, "\n".join(lines))
    except Exception as e:
        await _report_failure(bot, chat_id, "Проверка стран не удалась", e)


@admin_only
async def autoproxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not auto_mgr:
        await update.message.reply_text("Авто-страны работают, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    args = [a.lower() for a in context.args]
    sub = args[0] if args else ""
    reply = update.message.reply_text
    run = lambda: context.application.create_task(
        _auto_refresh_and_report(context.bot, update.effective_chat.id))
    if sub in ("on", "вкл"):
        vpn.set_auto(enabled=True)
        await reply("Авто-страны включены. Ищу рабочие прокси, это займёт несколько минут. "
                    "Результат пришлю сообщением.")
        run()
    elif sub in ("off", "выкл"):
        vpn.set_auto(enabled=False)
        n = vpn.clear_auto_locations()
        auto_mgr.sync_routes()
        await reply("Авто-страны выключены." + (f" Убрано стран: {n}, у клиентов они пропадут после "
                                                 "обновления подписки." if n else ""))
    elif sub == "now":
        await reply("Проверяю прокси. Результат пришлю сообщением.")
        run()
    elif sub == "test":
        await reply("Проверяю каждую страну. Результат пришлю сообщением.")
        context.application.create_task(_auto_selftest_and_report(context.bot, update.effective_chat.id))
    elif sub == "countries":
        codes = args[1:]
        if not codes or codes[0] in ("auto", "any", "подбор"):
            vpn.set_auto(countries=[])
            await reply("Теперь бот подбирает страны сам. Обновить сейчас: /autoproxy now")
            return
        bad = [c for c in codes if not (len(c) == 2 and c.isalpha() and c.isascii())]
        if bad:
            await reply(f"Нужны коды стран из двух латинских букв, например: nl de us. Непонятно: {esc(' '.join(bad))}")
            return
        codes = list(dict.fromkeys(codes))
        vpn.set_auto(countries=codes, exclude=[c for c in vpn.auto.get("exclude", []) if c not in codes])
        taken = [c.upper() for c in codes if c in vpn.manual_codes()]
        await reply("Страны заданы: " + ", ".join(c.upper() for c in codes) + "."
                    + (f"\nКод {', '.join(taken)} уже занят страной, добавленной вручную: её бот не трогает."
                       if taken else "")
                    + "\nОбновить сейчас: /autoproxy now")
    elif sub == "max" and len(args) > 1 and args[1].isdigit() and 1 <= int(args[1]) <= 30:
        vpn.set_auto(max=int(args[1]))
        await reply(f"При подборе держу до {int(args[1])} стран.")
    elif sub == "notify" and len(args) > 1 and args[1] in ("on", "off"):
        vpn.set_auto(notify=args[1] == "on")
        await reply("Сообщения о заменах прокси " + ("включены." if args[1] == "on" else "выключены."))
    elif sub == "include" and len(args) > 1:
        vpn.set_auto(exclude=[c for c in vpn.auto.get("exclude", []) if c not in args[1:]])
        await reply("Готово. Обновить сейчас: /autoproxy now")
    else:
        await reply(auto_status_text())


# ---------------------------------------------------------------- сайт маскировки

MASK = {"fails": 0, "bridge_fails": 0}
mask_lock = asyncio.Lock()


async def pick_masking_site(avoid=()) -> str | None:
    """Самый быстрый с сервера сайт из списка, о котором Xray не предупреждает."""
    for host, _ in await masking.ranked(h for h in masking.SITES if h not in avoid):
        if await vpn.site_flagged(host) is False:
            return host
    return None


async def switch_masking(reason: str, site: str | None = None) -> str:
    """Меняет сайт маскировки и возвращает сообщение для админа."""
    async with mask_lock:
        old = vpn.sni
        note = ""
        if site:
            if await masking.check(site) is None:
                return (f"Сайт {site} не подходит: с сервера он не отвечает по TLS 1.3 и HTTP/2. "
                        f"Остался {old}.")
            flagged = await vpn.site_flagged(site)
            if flagged is None:
                return f"Xray не принимает конфиг с сайтом {site}. Остался {old}."
            if flagged:
                note = "\n⚠️ Xray предупреждает: под этот сайт маскироваться рискованно, сервер проще распознать."
            new = site
        else:
            recent = {old} | {p["name"] for p in vpn.masking["prev"]}
            new = await pick_masking_site(recent) or await pick_masking_site({old})
            if not new:
                return (f"Подходящий сайт маскировки не нашёлся: с сервера не отвечает ни один из списка. "
                        f"Остался {old}.")
        if new == old:
            return f"Сайт маскировки уже {old}."
        grace = await masking.tolerates(new, old)
        if not await vpn.change_sni(new, grace=grace):
            return f"Xray не принял конфиг с сайтом {new}. Остался {old}."
        MASK["fails"] = 0
        keys = ("Ключи с прежним сайтом принимаются ещё сутки." if grace
                else "Ключи с прежним сайтом больше не работают.")
        return (f"🎭 Сайт маскировки изменён: {old} → {new}\nПричина: {reason}.{note}\n\n{keys} "
                "Подписка на сервере уже новая, приложения заберут её сами при обновлении (раз в час).")


# ---------------------------------------------------------------- сайт маскировки Hysteria

HY2_SNI_EVERY = float(os.environ.get("HY2_SNI_EVERY", "24"))  # часов между сменами, 0 — не менять


def hy2_every() -> float:
    return float(vpn.state.get("hy2_sni_every", HY2_SNI_EVERY))


async def rotate_hy2_sni(reason: str, site: str | None = None) -> str:
    """Меняет сайт в ссылках Hysteria. Сервер принимает любое имя, поэтому прежние ссылки
    продолжают работать, а гостям ничего делать не нужно. Отчёт — только для админов."""
    if not getattr(vpn, "hy2", None):
        return "Hysteria не настроена."
    if not vpn.hy2_sni_rotatable():
        return ("Сайт Hysteria пока менять нельзя: сервер принимает только прежнее имя. "
                "Запустите установщик этой версии ещё раз, после этого смена заработает.")
    old = vpn.hy2_sni
    if not site:
        recent = set(vpn.state.get("hy2_sni_prev", [])) | {old}
        ranked = await masking.ranked(h for h in masking.SITES if h not in recent)
        if not ranked:
            ranked = await masking.ranked(h for h in masking.SITES if h != old)
        if not ranked:
            return f"Подходящий сайт не нашёлся: с сервера не отвечает ни один из списка. Остался {old}."
        import random
        site = random.choice(ranked[:5])[0]  # из пяти самых быстрых, чтобы смены не шли по кругу
    elif await masking.check(site) is None:
        return f"Сайт {site} не подходит: с сервера он не отвечает по TLS 1.3 и HTTP/2. Остался {old}."
    if site == old:
        return f"Сайт Hysteria уже {old}."
    vpn.set_hy2_sni(site)
    vpn.state["hy2_sni_prev"] = ([old] + [x for x in vpn.state.get("hy2_sni_prev", []) if x != old])[:5]
    vpn._save()
    return (f"🎭 Hysteria: сайт маскировки {old} → {site}\nПричина: {reason}.\n\n"
            "Ничего не перезапускалось, прежние ссылки работают. Приложения заберут новую подписку "
            "сами при обновлении, гостям ничего не отправлялось.")


async def hy2_sni_job(bot) -> None:
    every = hy2_every()
    if not every or not getattr(vpn, "hy2", None) or not vpn.hy2_sni_rotatable():
        return
    last = vpn.state.get("hy2_sni_changed")
    if not last:
        vpn.state["hy2_sni_changed"] = time.time()  # отсчёт с первого запуска
        vpn._save()
        return
    if time.time() - last >= every * 3600:
        await send_admins(bot, esc(await rotate_hy2_sni("плановая смена")))




async def masking_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 10 минут: если сайт маскировки перестал отвечать с сервера, бот ставит другой.
    Плановая смена раз в N часов включается командой /sni every."""
    if not hasattr(vpn, "masking"):
        return
    try:
        await hy2_sni_job(context.bot)
    except Exception:
        log.exception("сайт Hysteria: сбой смены")
    try:
        await bridge_site_job(context.bot)
    except Exception:
        log.exception("сайт мостов: сбой проверки")
    # Сайт маскировки Reality нужен только Xray; без Xray он ни на что не влияет.
    if not vpn.masking.get("auto", True) or not getattr(vpn, "xray_enabled", True):
        return
    try:
        m = vpn.masking
        if await masking.check(vpn.sni) is not None:
            MASK["fails"] = 0
        elif await public_proxies.direct_ok():  # сайт молчит, а интернет у сервера есть
            MASK["fails"] += 1
        reason = None
        if MASK["fails"] >= 3:
            reason = f"{vpn.sni} перестал отвечать с сервера"
        elif m.get("every"):
            if not m.get("changed"):
                m["changed"] = time.time()
                vpn.set_masking()
            elif time.time() - m["changed"] > m["every"] * 3600:
                reason = "плановая смена"
        if reason:
            await send_admins(context.bot, esc(await switch_masking(reason)))
    except Exception:
        log.exception("сайт маскировки: сбой проверки")


async def bridge_site_job(bot) -> None:
    """Сайт маскировки мостов «ru»: нужен и Reality, и Hysteria через мост (даже без Xray)."""
    if not vpn.ru_bridges():
        return
    site = vpn.bridge_site
    if site and await masking.check(site) is not None:
        MASK["bridge_fails"] = 0
    elif not site or await public_proxies.direct_ok():
        MASK["bridge_fails"] += 1
    if MASK["bridge_fails"] >= (1 if not site else 3):
        await send_admins(bot, esc(await switch_bridge_site(
            f"{site} перестал отвечать с сервера" if site else "сайт не был выбран")))


def masking_status_text() -> str:
    m = vpn.masking
    since = f", с {fmt_date(m['changed'])}" if m.get("changed") and m.get("site") else ", из настроек сервера"
    lines = [f"Сейчас: <code>{esc(vpn.sni)}</code>{since}",
             f"Замена при сбое: {'включена' if m.get('auto', True) else 'выключена'}",
             "Плановая смена: " + (f"раз в {m['every']} ч" if m.get("every") else "выключена")]
    if vpn.grace_names():
        lines.append("Ещё принимаются ключи с: " + ", ".join(esc(n) for n in vpn.grace_names()))
    return (xray_warning() + "<b>Сайт маскировки</b>\n\n" + "\n".join(lines) + "\n\n"
            "VPN выдаёт себя за обращение к обычному сайту, и его имя видно оператору. Раз в 10 минут бот "
            "проверяет, что сайт отвечает с сервера, и если нет, ставит другой из своего списка.\n"
            "В списке нет Microsoft, Apple и других самых известных сайтов: их адреса наперечёт, чужой "
            "сервер под таким именем заметен сразу, и Xray сам об этом предупреждает.\n"
            "После смены клиентам нужна обновлённая подписка: приложения обновляют её сами раз в час.\n\n"
            "<b>Команды</b>\n"
            "/sni next: подобрать и поставить другой сайт сейчас\n"
            "/sni list: какие сайты подходят с этого сервера\n"
            "/sni www.example.com: поставить этот сайт\n"
            "/sni every 24: менять сайт каждые 24 часа, /sni every off: не менять по расписанию\n"
            "/sni auto off: не менять сайт при сбое")


async def _masking_report(bot, chat_id: int, action: str, site: str | None = None) -> None:
    """Проверка сайтов занимает время, поэтому идёт в фоне, а итог приходит сообщением."""
    try:
        if action == "list":
            good = []
            for host, ms in await masking.ranked(masking.SITES):
                if await vpn.site_flagged(host) is False:
                    good.append(f"◆ <code>{esc(host)}</code> · {ms:.0f} мс")
            text = ("<b>Подходят с этого сервера</b>\n\n" + "\n".join(good[:12]) if good
                    else "Ни один сайт из списка сейчас не подходит.")
        else:
            text = esc(await switch_masking("команда администратора", site))
        await _send_report(bot, chat_id, text)
    except Exception as e:
        await _report_failure(bot, chat_id, "Смена сайта маскировки не удалась", e)


@admin_only
async def sni_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "masking"):
        await update.message.reply_text("Сайт маскировки настраивается, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    args = [a.lower() for a in context.args]
    sub = args[0] if args else ""
    reply = update.message.reply_text
    if not getattr(vpn, "xray_enabled", True) and getattr(vpn, "hy2", None):
        await hy2_sni_cmd(update, context, args)
        return
    run = lambda action, site=None: context.application.create_task(
        _masking_report(context.bot, update.effective_chat.id, action, site))
    if sub == "next":
        await reply("Подбираю сайт и переключаю сервер. Результат пришлю сообщением.")
        run("switch")
    elif sub == "list":
        await reply("Проверяю сайты с сервера. Результат пришлю сообщением.")
        run("list")
    elif sub == "auto" and len(args) > 1 and args[1] in ("on", "off"):
        vpn.set_masking(auto=args[1] == "on")
        await reply("Замена сайта при сбое " + ("включена." if args[1] == "on"
                                                 else "выключена. Плановая смена тоже не работает."))
    elif sub == "every" and len(args) > 1 and (args[1] == "off" or (args[1].isdigit() and 1 <= int(args[1]) <= 720)):
        hours = 0 if args[1] == "off" else int(args[1])
        vpn.masking["changed"] = time.time()
        vpn.set_masking(every=hours)
        await reply(f"Сайт маскировки будет меняться каждые {hours} ч." if hours
                    else "Плановая смена сайта выключена.")
    elif masking.valid_name(sub):
        await reply(f"Проверяю {esc(sub)} и переключаю сервер. Результат пришлю сообщением.")
        run("switch", sub)
    else:
        await reply(masking_status_text())


async def hy2_sni_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    """/sni без Xray: сайт, под который маскируется Hysteria."""
    reply, chat = update.message.reply_text, update.effective_chat.id
    sub = args[0] if args else ""

    async def run(site=None) -> None:
        try:
            await _send_report(context.bot, chat, esc(await rotate_hy2_sni("команда администратора", site)))
        except Exception as e:
            await _report_failure(context.bot, chat, "Смена сайта Hysteria не удалась", e)
    if sub == "next":
        await reply("Подбираю сайт. Результат пришлю сообщением.")
        context.application.create_task(run())
    elif sub == "every" and len(args) > 1 and (args[1] == "off" or (args[1].isdigit() and 1 <= int(args[1]) <= 720)):
        vpn.state["hy2_sni_every"] = 0 if args[1] == "off" else int(args[1])
        vpn.state["hy2_sni_changed"] = time.time()
        vpn._save()
        await reply(f"Сайт Hysteria будет меняться каждые {args[1]} ч." if args[1] != "off"
                    else "Плановая смена сайта Hysteria выключена.")
    elif masking.valid_name(sub):
        await reply(f"Проверяю {esc(sub)}. Результат пришлю сообщением.")
        context.application.create_task(run(sub))
    else:
        every = hy2_every()
        last = vpn.state.get("hy2_sni_changed")
        lines = [f"Сейчас: <code>{esc(vpn.hy2_sni)}</code>" + (f", с {fmt_date(last)}" if last else ""),
                 "Плановая смена: " + (f"раз в {every:g} ч" if every else "выключена")]
        if not vpn.hy2_sni_rotatable():
            lines.append("⚠️ Смена пока недоступна: запустите установщик этой версии ещё раз.")
        await reply("<b>Сайт маскировки Hysteria</b>\n\n" + "\n".join(lines) + "\n\n"
                    "Hysteria выдаёт себя за обращение к обычному сайту, и его имя видно оператору. "
                    "Бот меняет сайт по расписанию. Сервер принимает любое имя, поэтому прежние ссылки "
                    "работают и после смены, а гостям ничего не приходит: приложения заберут новую "
                    "подписку сами. Сообщение о смене получают только админы.\n\n"
                    "<b>Команды</b>\n"
                    "/sni next: сменить сейчас\n"
                    "/sni www.example.com: поставить этот сайт\n"
                    "/sni every 24: менять каждые 24 часа, /sni every off: не менять")


# ---------------------------------------------------------------- купленные прокси списком (Webshare)

WS_LOCK = asyncio.Lock()
WEBSHARE_MAX = int(os.environ.get("WEBSHARE_MAX", "20"))  # сколько стран держать из списка


def ws_cfg() -> dict:
    return vpn.state.setdefault("webshare", {})


async def webshare_refresh() -> str:
    """Скачивает список, проверяет прокси и обновляет страны. Возвращает отчёт для админа."""
    async with WS_LOCK:
        cfg = ws_cfg()
        if not cfg.get("url") and not cfg.get("list"):
            return "Ссылка на список не задана: /webshare ссылка"
        try:
            urls = list(cfg["list"]) if cfg.get("list") else await webshare.fetch(cfg["url"])
        except ValueError as e:
            cfg["error"] = str(e)
            vpn._save()
            return f"⚠️ Список не получен: {e}. Проверьте ссылку в личном кабинете и задайте её заново."
        if not await public_proxies.direct_ok():
            return "⚠️ Сервер сам не вышел в интернет, проверка отложена."
        groups = webshare.by_country(await webshare.scan(urls), WEBSHARE_MAX)
        added, swapped, taken = [], [], []
        for cc, items in groups.items():
            res = vpn.set_paid_location(cc, public_proxies.country_name(cc), [u for u, _ in items[:3]],
                                        ms=items[0][1])
            {"added": added, "swapped": swapped, "": taken}.get(res, []).append(cc)
        hidden, now = [], time.time()
        if groups:  # ничего не нашли — скорее сбой проверки
            # Свои страны админа не прячутся и не удаляются сами (просьба владельца): страна, которой
            # нет в этой проверке, остаётся в подписке со своими прокси, админ получает отчёт.
            # Убрать: /delloc код или /webshare off.
            for loc in vpn.paid_locations():
                if loc["code"] in groups:
                    loc.pop("missing_since", None)
                else:
                    loc.setdefault("missing_since", now)
                    hidden.append(loc["code"])
        if auto_mgr:
            auto_mgr.sync_routes()
        cfg.update(last=time.time(), total=len(urls), error="",
                   working=sum(len(v) for v in groups.values()))
        vpn._save()
        nm = public_proxies.country_name
        lines = [f"🛒 <b>Купленные прокси</b>: в списке {len(urls)}, работают {cfg['working']}, "
                 f"стран {len(groups)}"]
        if groups:
            lines.append(", ".join(f"{nm(c)} {groups[c][0][1]} мс" for c in groups))
        if added:
            lines.append("➕ Добавлены: " + ", ".join(nm(c) for c in added))
        if swapped:
            lines.append("🔁 Прокси заменён: " + ", ".join(nm(c) for c in swapped))
        if hidden:
            lines.append("⚠️ Не ответили в эту проверку (остаются в подписке): " + ", ".join(nm(c) for c in hidden))
        if taken:
            lines.append("Не тронуты, код занят страной, добавленной через /addloc: "
                         + ", ".join(c.upper() for c in taken))
        if not groups:
            lines.append("⚠️ Ни один прокси из списка не прошёл проверку: проверьте, что тариф активен.")
        return "\n".join(lines)


async def webshare_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 3 часа: умершие прокси меняются на живые из списка, новые страны добавляются."""
    if not hasattr(vpn, "set_paid_location") or not (ws_cfg().get("url") or ws_cfg().get("list")):
        return
    try:
        report = await webshare_refresh()
    except Exception:
        log.exception("купленные прокси: сбой")
        return
    if "➕" in report or "🔁" in report or "➖" in report or "⚠️" in report:
        await send_admins(context.bot, report)


def pay_text() -> str:
    on, off = "✅ включена", "◇ выключена"
    ex = ", ".join(f"{config.PLANS[k][0]} {pay_cfg.rub(config.plan_price(k, 1))} ₽" for k in config.PLANS)
    return ("<b>Оплата картой и криптой</b>\n\n"
            f"◆ ЮKassa (карта, СБП): {on if pay_cfg.yookassa else off}"
            + (" · чеки 54-ФЗ" if pay_cfg.receipt else "") + "\n"
            f"◆ Крипта (@CryptoBot): {on if pay_cfg.crypto else off}" + (" · тестовая сеть" if pay_cfg.crypto_test else "")
            + f"\n◆ Курс: 1 ⭐ = {pay_cfg.rate:g} ₽ → {ex}\n\n"
            "Звёзды работают всегда. Когда включён хотя бы один способ, гость при разовой оплате выбирает, "
            "чем платить. Автопродление и доплата за устройства — только звёздами.\n\n"
            "<b>Как подключить ЮKassa</b>\n"
            "1. Магазин в ЮKassa (самозанятый, ИП или ООО).\n"
            "2. @BotFather → /mybots → этот бот → Payments → ЮKassa → подключить, получить токен.\n"
            "3. /pay yookassa <code>токен</code>\n\n"
            "<b>Как подключить крипту</b>\n"
            "1. @CryptoBot → Crypto Pay → Create App → скопировать API Token.\n"
            "2. /pay crypto <code>токен</code> (для проверки в тестовой сети: @CryptoTestnetBot и "
            "/pay crypto <code>токен</code> test)\n\n"
            "<b>Команды</b>\n"
            "/pay rate 1.5: курс рубля к звезде\n"
            "/pay receipt on|off: передавать данные для чека в ЮKassa\n"
            "/pay yookassa off, /pay crypto off: выключить\n\n"
            "Сообщение с токеном бот сразу удаляет, токен хранится только на сервере.")


def bs_text() -> str:
    if not getattr(vpn, "hy2", None):
        return "Обход белых списков работает через Hysteria, а она на сервере не включена."
    ok = vpn.hy2_sni_rotatable()
    state = ("✅ включён" if vpn.bs_on() else "◇ выключен") if ok else \
        "⚠️ недоступен: сервер Hysteria проверяет имя сайта. Обновите сервер установщиком этой версии."
    return ("<b>Обход белых списков без моста</b>\n\n"
            f"◆ Пункты «{esc(vpn.direct_location()['name'])} · обход БС» в подписке: {state}\n"
            "◆ Представляются сайтами: " + ", ".join(f"<code>{esc(x)}</code>" for x in vpn.bs_sites) + "\n\n"
            "Это то же подключение к серверу, но для оператора оно выглядит как обращение к российскому "
            "сайту из белого списка. Поможет, если оператор при белых списках пропускает по имени сайта. "
            "Если он пропускает только по адресам серверов, поможет только мост в РФ (/addbridge).\n\n"
            "Пунктов несколько, с разными сайтами: у операторов разные белые списки, и если "
            "не проходит один, может пройти другой.\n\n"
            "/bs on, /bs off: включить или выключить пункты\n"
            "/bs site vk.com ya.ru ozon.ru: сайты, до 3 (лучше из белого списка: "
            + ", ".join(masking.RU_SITES[:6]) + ")\n\n"
            "Новый пункт появится у гостей при обновлении подписки (приложения обновляют её сами).")


@admin_only
async def bs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = [a.lower() for a in context.args or []]
    if hasattr(vpn, "set_bs"):
        if args[:1] in (["on"], ["off"]):
            vpn.set_bs(on=args[0] == "on")
        elif len(args) >= 2 and args[0] == "site":
            sites = list(dict.fromkeys(a.removeprefix("https://").strip("/") for a in args[1:]))
            if not all(masking.valid_name(x) for x in sites):
                await update.message.reply_text("Нужны имена сайтов, например <code>/bs site vk.com ya.ru</code>")
                return
            vpn.set_bs(sites=sites)
    await update.message.reply_text(bs_text() if hasattr(vpn, "set_bs") else
                                    "Обход настраивается, когда подключён настоящий VPN.")


@admin_only
async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    reply = update.message.reply_text
    what = args[0].lower() if args else ""
    if what in ("yookassa", "ykassa", "юкасса", "crypto", "крипта") and len(args) >= 2:
        key = "yookassa" if what in ("yookassa", "ykassa", "юкасса") else "crypto"
        token = args[1].strip()
        if token.lower() == "off":
            pay_cfg.set(**{key: None})
            await reply(("ЮKassa" if key == "yookassa" else "Оплата криптой") + " выключена.\n\n" + pay_text())
            return
        try:  # в сообщении секрет: не оставляем его в чате
            await update.message.delete()
        except TelegramError:
            pass
        if key == "crypto":
            test = len(args) > 2 and args[2].lower() == "test"
            try:
                me = await paymod.CryptoPay(token, test).me()
            except Exception as e:
                await reply(f"Crypto Pay не принял токен: {esc(str(e))}. Проверьте его в @CryptoBot → Crypto Pay.")
                return
            pay_cfg.set(crypto=token, crypto_test=test or None)
            await reply(f"🪙 Оплата криптой включена: приложение «{esc(str(me.get('name', '')))}».\n\n" + pay_text())
            return
        if ":" not in token:
            await reply("Это не похоже на токен ЮKassa из @BotFather (вида <code>123456:LIVE:…</code>).")
            return
        pay_cfg.set(yookassa=token)
        note = " Это <b>тестовый</b> токен: деньги не списываются." if ":TEST:" in token.upper() else ""
        await reply("💳 Оплата картой через ЮKassa включена." + note + "\n\n" + pay_text())
        return
    if what == "rate" and len(args) == 2:
        try:
            rate = float(args[1].replace(",", "."))
            if not 0.1 <= rate <= 100:
                raise ValueError
        except ValueError:
            await reply("Курс — число, например /pay rate 1.5")
            return
        pay_cfg.set(rate=rate)
        await reply(pay_text())
        return
    if what == "receipt" and len(args) == 2 and args[1].lower() in ("on", "off"):
        pay_cfg.set(receipt=True if args[1].lower() == "on" else None)
        await reply(pay_text())
        return
    await reply(pay_text())


@admin_only
async def webshare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "set_paid_location"):
        await update.message.reply_text("Купленные прокси работают, когда подключён настоящий VPN (VPN_MODE=xray).")
        return
    arg = context.args[0] if context.args else ""
    reply, chat = update.message.reply_text, update.effective_chat.id
    pasted = webshare.parse((update.message.text or "").split(maxsplit=1)[1]
                            if len((update.message.text or "").split(maxsplit=1)) > 1 else "")

    async def run(note: str) -> None:
        await reply(note)
        try:
            await _send_report(context.bot, chat, await webshare_refresh())
        except Exception as e:
            await _report_failure(context.bot, chat, "Проверка купленных прокси не удалась", e)
    if pasted and not arg.startswith("http"):
        # Список вставлен прямо в сообщение: host:port:логин:пароль по строке на прокси.
        vpn.state["webshare"] = {"list": pasted}
        vpn._save()
        try:  # в списке логины и пароли: не оставляем их в чате
            await update.message.delete()
        except TelegramError:
            pass
        context.application.create_task(run(f"Список из {len(pasted)} прокси сохранён только на сервере, "
                                            "сообщение с ним удалено. Проверяю прокси и определяю страны."))
    elif arg.startswith("http"):
        vpn.state["webshare"] = {}
        ws_cfg()["url"] = arg.strip()
        vpn._save()
        try:  # в ссылке ключ доступа к списку: не оставляем его в чате
            await update.message.delete()
        except TelegramError:
            pass
        context.application.create_task(run("Ссылка сохранена только на сервере, сообщение с ней удалено. "
                                            "Проверяю прокси, это займёт минуту."))
    elif arg == "now":
        context.application.create_task(run("Проверяю прокси из списка."))
    elif arg == "off":
        n = [l["code"] for l in vpn.paid_locations() if vpn.remove_location(l["code"])]
        vpn.state["webshare"] = {}
        vpn._save()
        await reply("Список отключён" + (f", убрано стран: {len(n)}." if n else "."))
    else:
        cfg = ws_cfg()
        locs = vpn.paid_locations()
        src = "Список задан" if cfg.get("list") else "Ссылка задана"
        state = (f"{src}, последняя проверка {_ago(cfg['last'])} назад: в списке {cfg.get('total', 0)}, "
                 f"работают {cfg.get('working', 0)}" if cfg.get("last") else
                 f"{src}, проверка ещё не проходила" if cfg.get("url") or cfg.get("list") else "Список не задан")
        rows = [f"◆ {esc(l['name'])} · {l.get('ms') or '?'} мс · запасных {max(0, len(l.get('pool', [])) - 1)}"
                + (" · ❌ не отвечает" if l.get("down") or l.get("failing") else "") for l in locs]
        await reply("<b>Купленные прокси списком</b>\n\n" + esc(state)
                    + (f"\n⚠️ {esc(cfg['error'])}" if cfg.get("error") else "") + "\n\n"
                    + ("\n".join(rows) if rows else "<i>Стран пока нет.</i>") + "\n\n"
                    "Бот скачивает список по ссылке, проверяет каждый прокси, определяет страну по реальному "
                    "выходу в интернет и держит в каждой стране самый быстрый плюс два запасных. "
                    "Раз в 3 часа проверка повторяется. У каждой страны есть и Hysteria, и TCP.\n\n"
                    "<b>Команды</b>\n"
                    "/webshare <code>ссылка</code>: задать список (в Webshare: Proxy List → Download → "
                    "скопировать ссылку)\n"
                    "/webshare и ниже строки <code>host:порт:логин:пароль</code>: вставить список прямо в сообщение\n"
                    "/webshare now: проверить сейчас\n"
                    "/webshare off: убрать эти страны и забыть ссылку")


# ---------------------------------------------------------------- фоновые задачи

def buy_kb(sub=None) -> InlineKeyboardMarkup:
    """Кнопки покупки в напоминаниях: продление этой подписки или сразу тарифы."""
    rows = [[B("◆ Продлить", f"ext:{sub['id']}")]] if sub else []
    keys = list(config.PLANS)[:2]
    rows.append([B(f"{config.PLANS[k][0]}", f"buy:{k}") for k in keys])
    rows.append([B("◆ Все тарифы", "plans")])
    return InlineKeyboardMarkup(rows)


async def tell(bot, uid: int, text: str, kb=None) -> bool:
    try:
        await bot.send_message(uid, text, reply_markup=kb)
        return True
    except TelegramError:
        return False


async def lifecycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for s in db.expiring_soon(DAY):
        if s["trial"]:
            # Пробный период короткий: напоминаем за несколько часов, а не за сутки.
            left = s["expires_at"] - time.time()
            if left > config.TRIAL_REMIND_HOURS * 3600:
                continue
            db.mark_reminded(s["id"], s["expires_at"])
            hours = max(1, round(left / 3600))
            await tell(context.bot, s["user_id"],
                       f"✦ Пробный доступ закончится через {plural(hours, 'час', 'часа', 'часов')}.\n"
                       "Понравилось? Оформите подписку, и VPN продолжит работать без перерыва: "
                       "ключ останется тем же.", buy_kb(s))
            continue
        db.mark_reminded(s["id"], s["expires_at"])
        if s["auto_active"]:
            continue  # продлится само
        try:
            await context.bot.send_message(
                s["user_id"],
                f"⏳ «{esc(s['name'])}» закончится <b>{fmt_date(s['expires_at'])}</b>.\n"
                "Продлите заранее, чтобы VPN не отключился.",
                reply_markup=KB([B("◆ Продлить", f"ext:{s['id']}")]))
        except TelegramError:
            pass

    for s in db.expired_with_key():
        await vpn.revoke(s["id"])
        db.set_key(s["id"], s["vpn_key"], False)
        await refresh_menu(context, s["user_id"])
        row = db.get_user(s["user_id"])
        if s["trial"] and row and row["paid_stars"] == 0 and not db.active_subs(s["user_id"]):
            note = ""
            if config.TRIAL_OFFER > 0:
                db.set_offer(s["user_id"], config.TRIAL_OFFER, config.OFFER_HOURS, "trial")
                note = (f"\n\n🎁 Для вас скидка <b>{config.TRIAL_OFFER}%</b> на первую оплату, "
                        f"действует {plural(config.OFFER_HOURS, 'час', 'часа', 'часов')}.")
            await tell(context.bot, s["user_id"],
                       "Пробный период закончился, VPN отключён.\n"
                       "Оформите подписку, и он снова заработает с тем же ключом." + note, buy_kb(s))
            continue
        await tell(context.bot, s["user_id"],
                   f"Срок «{esc(s['name'])}» закончился, VPN отключён. Продлите, чтобы снова пользоваться.",
                   KB([B("◆ Продлить", f"ext:{s['id']}")]))

    await winback_job(context)


async def winback_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Через несколько дней после окончания всех подписок гость получает персональную скидку.
    Этапы идут от позднего к раннему: кто ушёл давно, получает одно, последнее, предложение."""
    steps = sorted(config.WINBACK)
    for stage in range(len(steps), 0, -1):
        days, percent = steps[stage - 1]
        for r in db.winback_due(days, 30, stage):
            uid = r["user_id"]
            db.mark_winback(uid, r["last_exp"], stage)
            db.set_offer(uid, percent, config.OFFER_HOURS, f"winback{stage}")
            last = stage == len(steps) and stage > 1
            await tell(context.bot, uid,
                       ("🎁 <b>Последнее предложение</b>\n\n" if last else "🎁 <b>Мы скучаем</b>\n\n")
                       + f"Вернитесь в {esc(config.BRAND)} со скидкой <b>{percent}%</b> на любой тариф. "
                       f"Скидка действует {plural(config.OFFER_HOURS, 'час', 'часа', 'часов')}, "
                       "ключ останется прежним.", buy_kb())


async def traffic_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 10 минут: трафик с сервера в базу. Его видят гость, админ и приложение VPN."""
    if vpn.is_demo or not hasattr(vpn, "traffic"):
        return
    try:
        deltas = await vpn.traffic()
    except Exception:
        log.exception("трафик: сбой")
        return
    if deltas:
        db.add_traffic(deltas)


DEV_RESET_EVERY = 600


def devices_view(sub) -> str:
    """Экран «Устройства» подписки: сколько оплачено, сколько подключено сейчас и что можно сделать."""
    now_n = guard.last.get(sub["id"])
    checked = guard.last_at
    if not checked or time.time() - checked > 900:
        online = "<i>проверяется, загляните через пару минут</i>"
    else:
        n = now_n or 0
        mark = "⚠️" if n > sub["devices"] else "✅"
        online = f"{mark} <b>{n}</b> (проверено в {time.strftime('%H:%M', time.localtime(checked))})"
    paused = ""
    if getattr(vpn, "is_suspended", None) and vpn.is_suspended(sub["id"]):
        paused = "\n⛔ <b>Подписка временно отключена</b>: устройств было больше, чем оплачено.\n"
    rule = {"block": "Если устройств дольше нескольких минут больше, чем оплачено, бот сначала предупредит, "
                     f"а потом отключит подписку на {config.DEVICE_BLOCK_MINUTES} мин.",
            "warn": "Если устройств больше, чем оплачено, бот пришлёт предупреждение.",
            "off": "Сейчас число устройств не ограничивается."}[guard.mode]
    known = vpn.device_list(sub["id"]) if hasattr(vpn, "device_list") else []
    lines = ""
    for i, d in enumerate(known, 1):
        ago = max(0, int(time.time() - d.get("t", 0)))
        when = "сейчас" if ago < 3600 else (f"{ago // 3600} ч назад" if ago < 86400 else f"{ago // 86400} дн назад")
        lines += f"{i}. {esc(d.get('m') or 'Устройство')} {esc(d.get('os') or '')} · {when}\n"
    listed = (f"\n<b>Устройства с местом в подписке ({len(known)} из {sub['devices']})</b>\n{lines}"
              "<i>Новое устройство сверх оплаченных получит вместо стран «⛔ Превышен лимит устройств». "
              "Чтобы освободить место, удалите ненужное кнопкой 🗑. Устройство, которое неделю не "
              "обновляло подписку, освобождает место само.</i>\n" if known else "")
    return (f"<b>📱 Устройства «{esc(sub['name'])}»</b>\n\n"
            f"◆ Оплачено: <b>{sub['devices']}</b>\n"
            f"◆ Подключено сейчас: {online}\n{paused}{listed}\n"
            "Устройство — это телефон, компьютер или телевизор, на котором включён VPN с этой подпиской. "
            f"{rule}\n\n"
            "<b>Что можно сделать</b>\n"
            "➕ <b>Добавить</b> — доплатить за ещё устройства до конца срока.\n"
            "🔄 <b>Сбросить</b> — отключить все устройства и получить новую ссылку (если ссылку кто-то узнал "
            "или телефон потерялся).")


def devices_manage_kb(sub) -> InlineKeyboardMarkup:
    known = vpn.device_list(sub["id"]) if hasattr(vpn, "device_list") else []
    rows = [[B(f"🗑 {i}. {(d.get('m') or 'Устройство')[:20]}", f"devdel:{sub['id']}:{d['id']}")]
            for i, d in enumerate(known, 1)]
    rows.append([B("🔄 Обновить", f"dev:{sub['id']}"), B("🔄 Сбросить все", f"devr:{sub['id']}")])
    if can_upgrade(sub):
        rows.append([B("➕ Добавить устройства", f"up:{sub['id']}")])
    rows.append([B("‹ К подписке", f"sub:{sub['id']}")])
    return InlineKeyboardMarkup(rows)


def dev_word(n: int) -> str:
    return plural(n, "устройство", "устройства", "устройств")


async def app_release_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Свежие APK обоих приложений на сервере: из них приложения обновляются изнутри."""
    for rel in (legacy_app, android_app):
        if rel:
            await rel.latest()


async def devices_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Раз в 2 минуты сверяет, сколько устройств подключено, с оплаченным числом."""
    if vpn.is_demo or not hasattr(vpn, "online") or guard.mode == "off":
        return
    # Отключение закончилось: по памяти бота или по сохранённому на сервере (после перезапуска бота).
    for sid in sorted(set(guard.due_unblock()) | set(vpn.due_resume())):
        await vpn.resume(sid)
        sub = db.get_sub(sid)
        if sub and sub_active(sub):
            await tell(context.bot, sub["user_id"], f"✅ «{esc(sub['name'])}» снова работает.")
    try:
        seen = await vpn.online()
    except Exception:
        log.exception("устройства: сбой")
        return
    if seen is None:
        return
    for action, sid, n, limit in guard.check(seen, db.active_devices()):
        sub = db.get_sub(sid)
        if not sub:
            continue
        row = db.get_user(sub["user_id"])
        if action == "warn":
            await tell(context.bot, sub["user_id"],
                       f"⚠️ К «{esc(sub['name'])}» сейчас подключено {dev_word(n)}, а в подписке "
                       f"{dev_word(limit)}.\nОтключите лишние устройства или оформите ещё одну подписку. "
                       + ("Если превышение продолжится, подписка отключится на "
                          f"{config.DEVICE_BLOCK_MINUTES} мин." if guard.mode == "block" else ""),
                       KB([B("➕ Ещё подписка", "plans")], [B("🛎 Консьерж", "tk")]))
        else:
            await vpn.suspend(sid, guard.block_seconds)
            await tell(context.bot, sub["user_id"],
                       f"⛔ «{esc(sub['name'])}» отключена на {config.DEVICE_BLOCK_MINUTES} мин: подключено "
                       f"{dev_word(n)} при оплаченных {limit}. Потом она включится сама.",
                       KB([B("➕ Ещё подписка", "plans")], [B("🛎 Консьерж", "tk")]))
            await send_admins(context.bot, f"⛔ Превышение устройств: {who(row) if row else sub['user_id']} · "
                                           f"«{esc(sub['name'])}» · {n} из {limit}. Отключена на "
                                           f"{config.DEVICE_BLOCK_MINUTES} мин.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке обновления", exc_info=context.error)


# ---------------------------------------------------------------- запуск

async def setup_profile(app: Application) -> None:
    """Запуск VPN-части, затем имя, описание до /start и меню команд бота."""
    bot = app.bot
    STATE["bot"] = bot
    try:
        STATE["username"] = (await bot.get_me()).username or ""
    except TelegramError as e:
        log.warning("get_me: %s", e)
    if hasattr(vpn, "on_problem"):
        async def alert(text: str) -> None:
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, "⚠️ <b>Проблема с VPN</b>\n\n<code>"
                                           + esc(text[:3000]) + "</code>\n\nПодробности: /server")
                except TelegramError:
                    pass
        vpn.on_problem = alert
    try:
        await announce_update(bot)
    except Exception:
        log.exception("версия кода")
    if hasattr(vpn, "support_url") and bot.username:
        vpn.support_url = f"https://t.me/{bot.username}"
    if hasattr(vpn, "sync"):
        active = db.all_active_subs()
        vpn.usage = db.sub_traffic
        await vpn.sync(active, db.active_devices())
        for sid in active:  # ключи из демо-режима меняются на настоящие
            db.set_key(sid, vpn.sub_url(sid), True)
        await vpn.start_sub_server()
        await vpn.start_hy2_auth()
    if auto_mgr:
        auto_mgr.notify = lambda text: send_admins(bot, text)
        await auto_mgr.start()
    # У админов в меню «/» все команды, чтобы их не искать; гости видят только свои.
    guest_cmds = [BotCommand("start", "Главное меню"), BotCommand("promo", "Промокод или подарок"),
                  *([BotCommand("app", "Приложение для Android")] if android_app else [])]
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.set_my_commands(guest_cmds + [BotCommand(c, d[:256]) for c, d in ADMIN_COMMANDS],
                                      scope=BotCommandScopeChat(admin_id))
        except TelegramError as e:
            log.warning("меню команд админа %s: %s", admin_id, e)
    if not config.SET_PROFILE:
        return
    steps = [
        lambda: bot.set_my_commands([
            BotCommand("start", "Главное меню"),
            BotCommand("promo", "Промокод или подарок"),
            *([BotCommand("app", "Приложение для Android")] if android_app else []),
            BotCommand("terms", "Условия"),
            BotCommand("paysupport", "Вопросы по оплате"),
        ]),
        lambda: bot.set_my_short_description(f"{config.BRAND} · {config.TAGLINE}"[:120]),
        lambda: bot.set_my_description(
            (f"{config.BRAND}\n{config.TAGLINE}.\n\n" + bullets(config.FEATURES)
             + "\n\n✦ Пробный период бесплатно\n✦ Оплата звёздами Telegram\n\n"
               "Нажмите «Запустить», чтобы получить доступ.")[:512]),
    ]
    for step in steps:
        try:
            await step()
        except TelegramError as e:
            log.warning("профиль бота: %s", e)
    try:
        if (await bot.get_my_name()).name != config.BRAND:
            await bot.set_my_name(config.BRAND)
    except TelegramError as e:
        log.warning("имя бота: %s", e)


async def send_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Присылает APK приложения файлом. Telegram запоминает файл: повторно он уходит мгновенно."""
    q = update.callback_query
    if not android_app:
        if q:
            await q.answer("Приложение пока недоступно", show_alert=True)
        return
    if q:
        await q.answer("Готовлю файл…")
    chat = update.effective_chat.id
    got = await android_app.latest()
    if not got:
        await context.bot.send_message(chat, "Приложение ещё собирается. Загляните чуть позже, а пока "
                                             "подключитесь через Happ или v2rayNG.")
        return
    ver, path = got
    cache = context.bot_data.setdefault("apk_file", {})
    caption = (f"<b>{esc(config.BRAND)} {esc(ver)}</b> для Android\n"
               "Откройте файл и установите. Потом в «🗝 Мои подписки» нажмите «📲 Подключить в один клик».")
    try:
        if ver in cache:
            await context.bot.send_document(chat, cache[ver], caption=caption)
            return
    except TelegramError:
        cache.pop(ver, None)
    with open(path, "rb") as f:
        msg = await context.bot.send_document(chat, f, filename=f"{config.BRAND.replace(' ', '')}-{ver}.apk", caption=caption,
                                              read_timeout=180, write_timeout=180)
    if msg.document:
        cache[ver] = msg.document.file_id


async def app_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_app(update, context)


def build_app(token: str) -> Application:
    app = (Application.builder().token(token)
           .defaults(Defaults(parse_mode=ParseMode.HTML))
           .post_init(setup_profile).build())
    banners = {}
    for name, path in make_banner.ensure().items():
        with open(path, "rb") as f:
            banners[name] = f.read()
    app.bot_data["banners"] = banners

    for cmd, fn in [("start", start), ("terms", terms), ("paysupport", paysupport), ("promo", promo_cmd),
                    ("admin", admin), ("give", give), ("addpromo", addpromo), ("promos", promos_cmd), ("chat", chat_cmd), ("security", security_cmd), ("delpromo", delpromo), ("refund", refund),
                    ("testpay", testpay), ("payments", payments), ("locations", locations),
                    ("addloc", addloc), ("delloc", delloc), ("addbridge", addbridge),
                    ("delbridge", delbridge), ("server", server), ("backup", backup),
                    ("autoproxy", autoproxy), ("sni", sni_cmd), ("bridgesite", bridgesite_cmd),
                    ("funnel", funnel), ("traffic", traffic), ("webshare", webshare_cmd), ("pay", pay_cmd), ("bs", bs_cmd),
                    ("app", app_cmd), ("update", update_cmd)]:
        app.add_handler(CommandHandler(cmd, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, paid))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(lifecycle_job, interval=3600, first=30)
    app.job_queue.run_repeating(proxy_health_job, interval=600, first=60)
    if config.BACKUP_DAILY:
        app.job_queue.run_repeating(backup_job, interval=86400, first=3600)
    app.job_queue.run_repeating(auto_proxy_job, interval=300, first=45)
    app.job_queue.run_repeating(masking_job, interval=600, first=150)
    app.job_queue.run_repeating(webshare_job, interval=3 * 3600, first=200)
    app.job_queue.run_repeating(crypto_job, interval=20, first=15)
    app.job_queue.run_repeating(traffic_job, interval=600, first=90)
    app.job_queue.run_repeating(devices_job, interval=120, first=90)
    if android_app:
        app.job_queue.run_repeating(app_release_job, interval=1800, first=60)
    app.job_queue.run_repeating(security_job, interval=86400, first=600)
    return app


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("Нет BOT_TOKEN. Создайте файл .env по образцу .env.example.")
    if vpn.is_demo:
        log.warning("VPN-сервер не подключён: бот выдаёт демо-ключи.")
    app = build_app(config.BOT_TOKEN)
    log.info("%s запущен", config.BRAND)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
