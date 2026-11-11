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
import secrets
import shutil
import sqlite3
import tempfile
import time

import qrcode
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
                      LabeledPrice, MenuButtonWebApp, Update, WebAppInfo)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          Defaults, MessageHandler, PreCheckoutQueryHandler, filters)

import config
import make_banner
from db import DAY, DB
from vpn import get_provider

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("vpn-bot")

db = DB(config.DB_PATH)
vpn = get_provider()
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


def plural_dev(n: int) -> str:
    return plural(n, "устройство", "устройства", "устройств")


def bullets(items) -> str:
    return "\n".join(f"◆ {x}" for x in items)


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
    return [l["name"] for l in getattr(vpn, "locations", [])]


def channel_link() -> str:
    return f"https://t.me/{config.CHANNEL.lstrip('@')}"


def share_url(link: str, text: str = "") -> str:
    from urllib.parse import quote
    return f"https://t.me/share/url?url={quote(link, safe='')}" + (f"&text={quote(text)}" if text else "")


# ---------------------------------------------------------------- экраны

def main_text(row) -> str:
    name = esc(row["first_name"] or "Гость")
    feats = list(config.FEATURES)
    if len(location_names()) > 1:
        feats.append("Страны: " + ", ".join(location_names()))
    return (f"<b>{name}, добро пожаловать.</b>\n"
            f"<i>{esc(config.TAGLINE)}.</i>\n\n"
            f"<blockquote>{bullets(esc(f) for f in feats)}</blockquote>\n\n"
            f"{status_line(row['id'])}")


def main_kb(row) -> InlineKeyboardMarkup:
    uid = row["id"]
    rows = [[B("◆ Продлить доступ" if user_active(uid) else "◆ Оформить доступ", "plans")]]
    if config.MINIAPP_URL:
        rows.append([B("✨ Открыть приложение", webapp=miniapp_url(row))])
    if can_trial(row):
        rows.append([B(f"✦ {plural_days(config.TRIAL_DAYS).capitalize()} бесплатно", "trial")])
    rows += [
        [B("🗝 Мои подписки", "subs"), B("📲 Подключение", "howto")],
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


def plans_text(target=None) -> str:
    lines = []
    for k, (name, days, price) in config.PLANS.items():
        d = plan_discount(days, price)
        tail = f" · <i>выгода {d}%</i>" if d >= 3 else ""
        lines.append(f"{plan_mark(k)} <b>{esc(name)}</b> · от {price} ⭐{tail}")
    head = (f"<b>Продление «{esc(target['name'])}»</b>\n<i>{plural_dev(target['devices'])}. "
            "Выберите срок.</i>" if target else
            "<b>Выберите тариф</b>\n<i>Чем дольше срок, тем выгоднее.</i>")
    auto = ("\n◆ На месяц можно включить автопродление" if config.AUTO_RENEW and
            any(d == 30 for _, d, _ in config.PLANS.values()) else "")
    return (f"{head}\n\n<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "◆ Цена зависит от числа устройств\n"
            "◆ Оплата звёздами Telegram прямо в чате" + auto)


def plans_kb(target=None) -> InlineKeyboardMarkup:
    rows = []
    for k, (name, days, price) in config.PLANS.items():
        if target:
            p = config.plan_price(k, target["devices"])
            rows.append([B(f"{plan_mark(k)} {name} — {p} ⭐", f"bt:{k}:{target['id']}")])
        else:
            rows.append([B(f"{plan_mark(k)} {name} — от {price} ⭐", f"buy:{k}")])
    rows.append([B("‹ Подписка", f"sub:{target['id']}") if target else BACK])
    return InlineKeyboardMarkup(rows)


def devices_text(plan: str, gift: bool) -> str:
    name = config.PLANS[plan][0]
    what = "Подарок" if gift else "Новая подписка"
    lines = [f"◆ {plural_dev(n)} · {config.plan_price(plan, n)} ⭐" for n in config.DEVICE_OPTIONS]
    return (f"<b>{what} · {esc(name)}</b>\n<i>Сколько устройств подключить?</i>\n\n"
            f"<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "Одна подписка работает на выбранном числе устройств одновременно.")


def devices_kb(plan: str, gift: bool) -> InlineKeyboardMarkup:
    pref = "bg" if gift else "bn"
    rows = [[B(f"{plural_dev(n)} — {config.plan_price(plan, n)} ⭐", f"{pref}:{plan}:{n}")]
            for n in config.DEVICE_OPTIONS]
    rows.append([B("‹ Тарифы", "gift" if gift else "plans")])
    return InlineKeyboardMarkup(rows)


APPS = {
    "android": ("🤖 Android", "Hiddify, Happ или v2rayNG", "из Google Play"),
    "ios": ("🍏 iPhone и iPad", "Hiddify, Happ или Streisand", "из App Store"),
    "windows": ("🪟 Windows", "Hiddify или Happ", "с официального сайта"),
    "mac": ("💻 macOS", "Hiddify или Happ", "из App Store"),
}


def howto_text(platform: str) -> str:
    title, apps, store = APPS[platform]
    return (f"<b>{title}</b>\n\n"
            f"<blockquote>1. Установите {esc(apps)} {esc(store)}.\n"
            "2. Откройте «🗝 Мои подписки», выберите подписку и нажмите на ключ: он скопируется.\n"
            "3. В приложении нажмите «+», затем «Добавить из буфера обмена».\n"
            "4. Выберите страну и нажмите кнопку подключения ▶️</blockquote>\n\n"
            "Готово. Если что-то не получилось, консьерж поможет.")


def fix_text() -> str:
    steps = ["Обновите подписку в приложении: потяните список вниз или нажмите «Обновить».",
             "Отключитесь и подключитесь заново."]
    if len(location_names()) > 1:
        steps.append("Выберите другую страну в списке.")
    bridges = [b["name"] for b in getattr(vpn, "bridges", [])]
    if bridges:
        steps.append(f"Если мобильный интернет ограничен, выберите «{bridges[0]}».")
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
    many = len(location_names()) > 1
    auto = "\n◆ Автопродление включено: звёзды спишутся сами раз в месяц" if s["auto_active"] else ""
    return (head + f"<code>{esc(s['vpn_key'] or '')}</code>\n\n"
            + ("<i>Нажмите на ссылку, чтобы скопировать. В ней сразу все страны.</i>\n" if many
               else "<i>Нажмите на ключ, чтобы скопировать.</i>\n")
            + f"◆ Действует до <b>{fmt_date(s['expires_at'])}</b> · ещё {plural_days(days_left(s))}"
            + auto + demo_note())


def sub_kb(s) -> InlineKeyboardMarkup:
    rows = []
    if sub_active(s):
        rows.append([B("📷 QR-код", f"qr:{s['id']}"), B("📲 Подключение", "howto")])
    rows.append([B("◆ Продлить", f"ext:{s['id']}"), B("✏️ Переименовать", f"ren:{s['id']}")])
    if s["auto_active"] and sub_active(s):
        rows.append([B("🔁 Отключить автопродление", f"noauto:{s['id']}")])
    if sub_active(s):
        rows.append([B("🛠 Не работает?", "fix")])
    rows.append([B("‹ Мои подписки", "subs")])
    return InlineKeyboardMarkup(rows)


def miniapp_url(row) -> str:
    """Адрес мини-приложения с данными этого гостя после #d=."""
    plans = [{"id": k, "name": n, "days": d, "price": pr, "disc": plan_discount(d, pr)}
             for k, (n, d, pr) in config.PLANS.items()]
    subs = []
    for s in db.user_subs(row["id"])[-8:]:
        act = sub_active(s)
        subs.append({"n": s["name"], "d": s["devices"], "e": int(s["expires_at"]) if act else 0,
                     "k": (s["vpn_key"] or "") if act else "", "a": bool(s["auto_active"] and act)})
    data = {
        "b": config.BRAND, "tg": config.TAGLINE, "n": row["first_name"] or "",
        "e": max((s["e"] for s in subs), default=0),
        "subs": subs, "tr": can_trial(row), "td": config.TRIAL_DAYS, "dm": vpn.is_demo,
        "bu": STATE["username"], "s": config.SUPPORT,
        "rf": f"https://t.me/{STATE['username']}?start=ref_{row['id']}" if STATE["username"] else "",
        "rb": config.REF_BONUS_DAYS, "rj": config.REF_ON_JOIN,
        "rc": db.referral_count(row["id"]), "p": plans, "loc": location_names(),
    }
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return config.MINIAPP_URL + "#d=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def refresh_menu(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Кнопка «Приложение» в меню чата гостя со свежими данными."""
    if not config.MINIAPP_URL:
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
    db.set_key(sub_id, await vpn.issue(sub_id, sub["expires_at"]), True)
    return db.get_sub(sub_id)


async def grant_days(user_id: int, days: int):
    """Бонусные дни: в основную подписку гостя, а если подписок нет — в новую."""
    sub = db.primary_sub(user_id) or db.create_sub(user_id, 1)
    db.extend_sub(sub["id"], days)
    return await issue_key(sub["id"])


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except TelegramError:
            pass


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
        await show(update, context, plans_text(), plans_kb(), banner="plans")
        return
    elif arg.startswith("buy_") and arg[4:] in config.PLANS:
        await choose_target(update, context, arg[4:])
        return
    elif arg.startswith("gift_"):
        await redeem(update, context, arg[5:])
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
    sub = db.create_sub(uid, 1, "Пробный ключ")
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
        await show(update, context, devices_text(plan, False), devices_kb(plan, False), banner="plans")
        return
    name = config.PLANS[plan][0]
    rows = [[B(f"◆ Продлить «{s['name']}» · {config.plan_price(plan, s['devices'])} ⭐",
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
    price = config.plan_price(plan, dev)
    if config.AUTO_RENEW and days == 30:
        await show(update, context,
                   f"<b>{esc(name)} · {plural_dev(dev)}</b>\n<i>Как удобнее оплачивать?</i>\n\n"
                   "<blockquote>🔁 С автопродлением: звёзды спишутся сами раз в месяц, "
                   "доступ не прервётся. Отключить можно в любой момент.\n"
                   "⚡ Разово: оплата на один месяц.</blockquote>",
                   KB([B(f"🔁 Автопродление — {price} ⭐/мес", f"pa:{kind}:{plan}:{dev}:{sub_id}")],
                      [B(f"⚡ Разово — {price} ⭐", f"po:{kind}:{plan}:{dev}:{sub_id}")],
                      [B("‹ Тарифы", "plans")]), banner="plans")
        return
    await send_order(update, context, kind, plan, dev, sub_id, auto=False)


async def send_order(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, plan: str,
                     dev: int, sub_id: int, auto: bool) -> None:
    """kind: n — новая подписка, e — продление, g — подарок."""
    name, days, _ = config.PLANS[plan]
    price = config.plan_price(plan, dev)
    code = {"n": "a" if auto else "b", "e": "x" if auto else "e", "g": "g"}[kind]
    token = secrets.token_hex(6) if auto else "-"
    payload = f"v2:{code}:{plan}:{days}:{price}:{dev}:{sub_id}:{token}"
    if kind == "g":
        title = f"{config.BRAND} · подарок"
        desc = (f"Подарочный доступ на {plural_days(days)}, {plural_dev(dev)}. "
                "После оплаты придёт подарочная ссылка.")
    else:
        title = f"{config.BRAND} · {name}"
        desc = (f"Персональный доступ к VPN на {plural_days(days)}, {plural_dev(dev)}. "
                + ("Продлевается автоматически каждый месяц." if auto else "Ключ придёт сразу после оплаты."))
    prices = [LabeledPrice(name, price)]
    chat = update.effective_chat.id
    if auto:
        link = await context.bot.create_invoice_link(
            title=title, description=desc, payload=payload, provider_token="", currency="XTR",
            prices=prices, subscription_period=MONTH)
        await context.bot.send_message(
            chat, f"🔁 <b>Подписка с автопродлением</b>\n\n{price} ⭐ в месяц, {plural_dev(dev)}. "
                  "Отключить можно в любой момент в «Мои подписки».",
            reply_markup=KB([B(f"Оформить · {price} ⭐/мес", url=link)]))
        return
    await context.bot.send_invoice(chat_id=chat, title=title, description=desc, payload=payload,
                                   provider_token="", currency="XTR", prices=prices)


def parse_payload(payload: str):
    try:
        v, code, plan, days, price, dev, sub_id, token = payload.split(":")
        if v != "v2" or code not in ("b", "e", "x", "a", "g"):
            return None
        return code, plan, int(days), int(price), int(dev), int(sub_id), token
    except ValueError:
        return None


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    p = parse_payload(q.invoice_payload)
    stale = "Счёт устарел. Откройте меню и выберите тариф заново."
    if not p:
        await q.answer(ok=False, error_message=stale)
        return
    code, plan, days, price, dev, sub_id, _ = p
    current = find_plan(plan, q.from_user.id)
    ok = bool(current and q.currency == "XTR" and current[1] == days and q.total_amount == price
              and (dev in config.DEVICE_OPTIONS or plan == "test")
              and price == config.plan_price(plan, dev))
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
    p = parse_payload(sp.invoice_payload)
    if not p:
        log.error("оплата с непонятным счётом: %s", sp.invoice_payload)
        await notify_admins(context, f"⚠️ Оплата с непонятным счётом от {who(u)}: "
                                     f"<code>{esc(charge)}</code>. Проверьте /payments.")
        return
    code, plan, days, _price, dev, sub_id, token = p
    name = (find_plan(plan, u.id) or (plan,))[0]

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

    first_payment = db.payments_count(u.id) == 0
    kind = {"b": "buy", "a": "auto", "e": "ext", "x": "auto", "g": "gift"}[code]
    if not db.add_payment(u.id, plan, sp.total_amount, days, charge, kind, None, dev):
        return  # Telegram прислал тот же платёж повторно

    if code == "g":
        gift = db.create_gift(u.id, days, dev)
        db.set_payment_target(charge, None, gift)
        link = f"https://t.me/{STATE['username'] or context.bot.username}?start=gift_{gift}"
        await show(update, context,
                   "<b>Подарок готов</b>\n\n"
                   f"◆ {plural_days(days)}, {plural_dev(dev)}\n"
                   f"◆ Код: <code>{gift}</code>\n\n"
                   f"Отправьте другу ссылку, по ней подарок активируется в один шаг:\n<code>{link}</code>",
                   KB([B("📤 Отправить подарок", url=share_url(link, f"Дарю доступ к {config.BRAND} 🎀"))],
                      [BACK]), banner="welcome", effect=CONFETTI)
        await notify_admins(context, f"🎀 Подарок: {who(u)} · {esc(name)} · {sp.total_amount} ⭐\n"
                                     f"charge: <code>{esc(charge)}</code>")
        return

    sub = db.get_sub(sub_id) if code in ("e", "x") else None
    if not sub or sub["user_id"] != u.id:
        sub = db.create_sub(u.id, dev)
    db.extend_sub(sub["id"], days)
    if code in ("a", "x"):
        db.set_auto(sub["id"], token, charge, True)
    db.set_payment_target(charge, sub["id"])
    sub = await issue_key(sub["id"])
    await refresh_menu(context, u.id)

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
                                 f"{sp.total_amount} ⭐{auto_mark}\ncharge: <code>{esc(charge)}</code>")


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
            await show(update, context, devices_text(parts[1], gift), devices_kb(parts[1], gift),
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
    if parts[0] in ("sub", "qr", "ren", "ext", "noauto", "noautook") and len(parts) == 2:
        sub = await own_sub(q, uid, parts[1])
        if not sub:
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
        await show(update, context, plans_text(), plans_kb(), banner="plans")
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
                      [BACK]), banner="howto")
    elif data.startswith("how:") and data[4:] in APPS:
        await show(update, context, howto_text(data[4:]),
                   KB([B("🗝 Мои подписки", "subs"), B("‹ Устройства", "howto")], [BACK]), banner="howto")
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
        await msg.reply_text("Рассылка началась…")
        ok = fail = 0
        for target in db.all_user_ids():
            try:
                await context.bot.copy_message(target, msg.chat_id, msg.message_id)
                ok += 1
            except (Forbidden, BadRequest):
                fail += 1
            await asyncio.sleep(0.05)
        await msg.reply_text(f"Готово. Доставлено: {ok}, не доставлено: {fail}.")
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


async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    uid = update.effective_user.id
    current_user(update)
    code = code.strip()
    if code.upper().startswith("GIFT-"):
        status, sub = db.redeem_gift(code, uid)
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
    if status != "ok":
        reason = {"not_found": "Такого промокода нет.", "used_up": "У этого промокода закончились активации.",
                  "already": "Вы уже использовали этот промокод."}[status]
        await show(update, context, f"<b>Промокод не принят</b>\n\n{reason}",
                   KB([B("🎟 Ввести другой", "promo"), BACK]))
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

def admin_text() -> str:
    s = db.stats()
    return ("<b>Админ-панель</b>\n\n"
            f"<blockquote>◆ Гостей: <b>{s['users']}</b> (+{s['new_today']} за сутки)\n"
            f"◆ С активным доступом: <b>{s['active']}</b> · подписок: {s['subs']}\n"
            f"◆ С автопродлением: {s['auto']}\n"
            f"◆ Брали пробный период: {s['trials']}\n"
            f"◆ Оплат: {s['payments']}\n"
            f"◆ Выручка: <b>{s['stars']} ⭐</b> (+{s['stars_today']} за сутки)</blockquote>\n\n"
            "<b>Команды</b>\n"
            "/give <code>id</code> <code>дней</code>: начислить дни\n"
            "/addpromo <code>КОД</code> <code>дней</code> <code>активаций</code>\n"
            "/payments <code>id</code> или <code>@ник</code>: платежи гостя\n"
            "/locations: страны и мосты для обхода\n"
            "/server: состояние сервера, /backup: резервная копия\n"
            f"/testpay: тестовая оплата на {config.TEST_PLAN[2]} ⭐\n"
            "Тикеты: ответьте на сообщение гостя, и ответ уйдёт ему")


def admin_kb() -> InlineKeyboardMarkup:
    return KB([B("💳 Платежи", "adm:pays"), B("📢 Рассылка", "adm:bc")],
              [B("🖥 Сервер", "adm:srv"), B("💾 Резервная копия", "adm:bak")],
              [B("🔄 Обновить", "adm:stats"), BACK])


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
        lines.append(f"{'✅' if vpn_ok else '❌'} VPN (порт {vpn.port}): "
                     + ("принимает подключения" if vpn_ok else "не отвечает"))
        lines.append(f"{'✅' if sub_ok else '❌'} Подписки (порт {vpn.sub_port}): "
                     + ("раздаются" if sub_ok else "не раздаются"))
        if vpn.last_error:
            lines.append("❌ Последняя ошибка VPN:\n<code>" + esc(vpn.last_error[:300]) + "</code>")
        elif vpn.last_apply:
            lines.append(f"◆ Настройки VPN применены {fmt_span(time.time() - vpn.last_apply)} назад")
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


async def send_backup(bot, chat_id: int) -> int:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    files = make_backup()
    for i, (name, data) in enumerate(files):
        await bot.send_document(
            chat_id, document=io.BytesIO(data), filename=f"aurora-{stamp}-{name}",
            caption=("💾 <b>Резервная копия</b> от " + stamp + ".\nХраните файлы у себя и никому не "
                     "пересылайте: в них данные гостей. Как восстановить, написано в README.") if i == 0 else None)
    return len(files)


async def backup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if db.stats()["users"] == 0:
        return
    for admin_id in config.ADMIN_IDS:
        try:
            await send_backup(context.bot, admin_id)
        except TelegramError as e:
            log.warning("резервная копия админу %s: %s", admin_id, e)


def who_paid(p) -> str:
    return f"@{esc(p['username'])}" if p["username"] else esc(p["first_name"] or str(p["user_id"]))


def payments_view(user_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    pays = db.list_payments(user_id, limit=8)
    title = "<b>Платежи</b>" if user_id is None else f"<b>Платежи гостя</b> <code>{user_id}</code>"
    if not pays:
        return title + "\n\nПлатежей пока нет.", KB([B("‹ Админ-панель", "adm:stats")])
    lines, buttons = [], []
    for p in pays:
        name = (config.TEST_PLAN if p["plan"] == "test" else config.PLANS.get(p["plan"], (p["plan"],)))[0]
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
    try:
        await context.bot.refund_star_payment(p["user_id"], charge)
    except TelegramError as e:
        return f"Telegram не принял возврат: {esc(str(e))}"
    sub = db.mark_refunded(charge)
    if sub:
        if p["kind"] in ("auto", "renew") and sub["auto_active"]:
            await cancel_auto(context, sub)
            sub = db.get_sub(sub["id"])
        if not sub_active(sub) and sub["key_active"]:
            await vpn.revoke(sub["id"])
            db.set_key(sub["id"], sub["vpn_key"], False)
        await refresh_menu(context, sub["user_id"])
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
    if act == "bak":
        await q.answer("Отправляю копию 👇")
        await send_backup(context.bot, row["id"])
        return
    await q.answer("Обновлено" if act in ("stats", "pays", "srv") else None)
    if act == "srv":
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


@admin_only
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_backup(context.bot, update.effective_user.id)


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


@admin_only
async def addpromo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        code, days, uses = context.args[0], int(context.args[1]), int(context.args[2])
    except (IndexError, ValueError):
        await update.message.reply_text("Формат: /addpromo <code>КОД</code> <code>дней</code> <code>активаций</code>")
        return
    if code.upper().startswith("GIFT-"):
        await update.message.reply_text("Промокод не может начинаться с GIFT-: так начинаются подарочные коды.")
        return
    db.add_promo(code, days, uses)
    await update.message.reply_text(
        f"Промокод <code>{esc(code.upper())}</code>: +{plural_days(days)}, активаций: {uses}.")


def locations_text() -> str:
    lines = []
    for l in getattr(vpn, "locations", []):
        how = "через прокси" if l["proxy"] else "напрямую с сервера"
        state = " · ❌ прокси не отвечает, скрыта" if l.get("down") else ""
        lines.append(f"◆ <code>{esc(l['code'])}</code> · {esc(l['name'])} · <i>{how}</i>{state}")
    bridges = [f"◆ <code>{esc(b['code'])}</code> · {esc(b['name'])} · {esc(b['host'])}:{b['port']}"
               + (f" · маскировка {esc(b['sni'])}" if b["sni"] else "")
               for b in getattr(vpn, "bridges", [])]
    return ("<b>Страны</b>\n\n" + "\n".join(lines) + "\n\n"
            "Добавить: /addloc <code>код</code> <code>Название</code> | <code>socks5://логин:пароль@ip:порт</code>\n"
            "Удалить: /delloc <code>код</code>\n\n"
            "<b>Мосты для обхода</b>\n\n" + ("\n".join(bridges) if bridges else "<i>пока нет</i>") + "\n\n"
            "Добавить: /addbridge <code>код</code> <code>Название</code> | <code>IP моста</code>\n"
            "Пример: <code>/addbridge ru1 🇷🇺 Обход | 1.2.3.4</code>\n"
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
    fmt = ("Формат: /addbridge <code>код</code> <code>Название</code> | <code>IP моста</code>\n"
           "Можно указать сайт для маскировки третьим полем: <code>| vk.com</code>")
    try:
        parts = [p.strip() for p in update.message.text.split(maxsplit=1)[1].split("|")]
        code, name = parts[0].split(maxsplit=1)
        vpn.add_bridge(code, name, parts[1], parts[2] if len(parts) > 2 else "")
    except (IndexError, ValueError) as e:
        hint = f"\n\nОшибка: {esc(str(e))}" if isinstance(e, ValueError) and str(e) else ""
        await update.message.reply_text(fmt + hint)
        return
    await update.message.reply_text("Мост добавлен. Он появится у всех клиентов после обновления подписки.\n\n"
                                    + locations_text())


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
    for loc, alive in await vpn.check_proxies():
        await notify_admins(context, (f"✅ Прокси «{esc(loc['name'])}» снова работает, страна вернулась в подписку."
                                      if alive else
                                      f"❌ Прокси «{esc(loc['name'])}» не отвечает. Страна скрыта из подписки, "
                                      "пока прокси не оживёт. Проверьте его у продавца."))


@admin_only
async def delloc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not hasattr(vpn, "remove_location") or not context.args:
        await update.message.reply_text("Формат: /delloc <code>код</code>")
        return
    ok = vpn.remove_location(context.args[0])
    await update.message.reply_text(("Удалено.\n\n" if ok else "Такой страны нет, или она последняя.\n\n")
                                    + locations_text())


# ---------------------------------------------------------------- фоновые задачи

async def lifecycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for s in db.expiring_soon(DAY):
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
        try:
            await context.bot.send_message(
                s["user_id"], f"Срок «{esc(s['name'])}» закончился, VPN отключён. "
                              "Продлите, чтобы снова пользоваться.",
                reply_markup=KB([B("◆ Продлить", f"ext:{s['id']}")]))
        except TelegramError:
            pass


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке обновления", exc_info=context.error)


# ---------------------------------------------------------------- запуск

async def setup_profile(app: Application) -> None:
    """Запуск VPN-части, затем имя, описание до /start и меню команд бота."""
    bot = app.bot
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
    if hasattr(vpn, "sync"):
        active = db.all_active_subs()
        await vpn.sync(active)
        for sid in active:  # ключи из демо-режима меняются на настоящие
            db.set_key(sid, vpn.sub_url(sid), True)
        await vpn.start_sub_server()
    if not config.SET_PROFILE:
        return
    steps = [
        lambda: bot.set_my_commands([
            BotCommand("start", "Главное меню"),
            BotCommand("promo", "Промокод или подарок"),
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
                    ("admin", admin), ("give", give), ("addpromo", addpromo), ("refund", refund),
                    ("testpay", testpay), ("payments", payments), ("locations", locations),
                    ("addloc", addloc), ("delloc", delloc), ("addbridge", addbridge),
                    ("delbridge", delbridge), ("server", server), ("backup", backup)]:
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
