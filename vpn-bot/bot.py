"""Премиальный бот для продажи подписки на VPN за Telegram Stars.

Запуск:  python bot.py   (настройки в .env, см. .env.example)
"""

import asyncio
import datetime
import html
import io
import logging
import time

import qrcode
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
                      LabeledPrice, Update)
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

CONFETTI = "5046509860389126442"  # встроенный эффект Telegram «🎉»


def B(text: str, data: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=url) if url else InlineKeyboardButton(text, callback_data=data)


def KB(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows])


BACK = B("‹ Главное меню", "menu")


# ---------------------------------------------------------------- оформление

def fmt_date(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y")


def is_active(row) -> bool:
    return bool(row) and row["expires_at"] > time.time()


def days_left(row) -> int:
    return max(0, int((row["expires_at"] - time.time() + DAY - 1) // DAY))


def plural_days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} дня"
    return f"{n} дней"


def bullets(items) -> str:
    return "\n".join(f"◆ {x}" for x in items)


def status_line(row) -> str:
    if is_active(row):
        return (f"◆ Статус: <b>Premium</b>\n"
                f"◆ Действует до <b>{fmt_date(row['expires_at'])}</b> · ещё {plural_days(days_left(row))}")
    return "◇ Статус: <i>доступ не активирован</i>"


def demo_note() -> str:
    return ("\n\n<i>Демо-режим: сервер ещё не подключён, ключ пока не работает.</i>"
            if vpn.is_demo else "")


def can_trial(row) -> bool:
    return (config.TRIAL_DAYS > 0 and not row["trial_used"] and row["paid_stars"] == 0
            and not is_active(row))


def main_text(row) -> str:
    name = esc(row["first_name"] or "Гость")
    return (f"<b>{name}, добро пожаловать.</b>\n"
            f"<i>{esc(config.TAGLINE)}.</i>\n\n"
            f"<blockquote>{bullets(esc(f) for f in config.FEATURES)}</blockquote>\n\n"
            f"{status_line(row)}")


def main_kb(row) -> InlineKeyboardMarkup:
    rows = [[B("◆ Продлить доступ" if is_active(row) else "◆ Оформить доступ", "plans")]]
    if can_trial(row):
        rows.append([B(f"✦ {plural_days(config.TRIAL_DAYS).capitalize()} бесплатно", "trial")])
    rows += [
        [B("🗝 Мой ключ", "key"), B("📲 Подключение", "howto")],
        [B("👤 Профиль", "profile"), B(f"🎁 +{config.REF_BONUS_DAYS} дней за друга", "ref")],
        [B("🎟 Промокод", "promo"), B("🛎 Консьерж", "support")],
    ]
    return InlineKeyboardMarkup(rows)


def plan_discount(days: int, price: int) -> int:
    base = config.PLANS["m1"][2] if "m1" in config.PLANS else price
    full = base * days / 30
    return max(0, round((1 - price / full) * 100)) if full else 0


def plan_mark(key: str) -> str:
    keys = list(config.PLANS)
    return "👑" if key == keys[-1] else ("◇" if key == keys[0] else "◆")


def plans_text() -> str:
    lines = []
    for k, (name, days, price) in config.PLANS.items():
        d = plan_discount(days, price)
        tail = f" · <i>выгода {d}%</i>" if d >= 3 else ""
        lines.append(f"{plan_mark(k)} <b>{esc(name)}</b> · {price} ⭐{tail}")
    return ("<b>Выберите тариф</b>\n"
            "<i>Чем дольше срок, тем выгоднее.</i>\n\n"
            f"<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "◆ Оплата звёздами Telegram прямо в чате\n"
            "◆ Продление добавляется к текущему сроку")


def plans_kb() -> InlineKeyboardMarkup:
    rows = [[B(f"{plan_mark(k)} {name} — {price} ⭐", f"buy:{k}")]
            for k, (name, days, price) in config.PLANS.items()]
    rows.append([BACK])
    return InlineKeyboardMarkup(rows)


APPS = {
    "android": ("🤖 Android", "v2rayNG или Hiddify", "из Google Play"),
    "ios": ("🍏 iPhone и iPad", "Streisand, V2Box или Hiddify", "из App Store"),
    "windows": ("🪟 Windows", "Hiddify или v2rayN", "с официального сайта"),
    "mac": ("💻 macOS", "Hiddify или V2Box", "из App Store"),
}


def howto_text(platform: str) -> str:
    title, apps, store = APPS[platform]
    return (f"<b>{title}</b>\n\n"
            f"<blockquote>1. Установите {esc(apps)} {esc(store)}.\n"
            "2. Откройте «🗝 Мой ключ» и нажмите на ключ: он скопируется.\n"
            "3. В приложении нажмите «+», затем «Импорт из буфера обмена».\n"
            "4. Нажмите кнопку подключения ▶️</blockquote>\n\n"
            "Готово. Если что-то не получилось, консьерж поможет.")


def key_block(row) -> str:
    return (f"<code>{esc(row['vpn_key'])}</code>\n\n"
            "<i>Нажмите на ключ, чтобы скопировать.</i>\n"
            f"◆ Действует до <b>{fmt_date(row['expires_at'])}</b>" + demo_note())


def key_kb() -> InlineKeyboardMarkup:
    return KB([B("📷 QR-код", "qr"), B("📲 Подключение", "howto")], [BACK])


# ---------------------------------------------------------------- показ экрана

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


async def grant(user_id: int, days: int):
    """Добавляет дни и выдаёт или продлевает ключ."""
    exp = db.extend(user_id, days)
    key = await vpn.issue(user_id, exp)
    db.set_key(user_id, key, True)
    return db.get_user(user_id)


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for admin in config.ADMIN_IDS:
        try:
            await context.bot.send_message(admin, text)
        except TelegramError:
            pass


# ---------------------------------------------------------------- команды

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    ref = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref = int(context.args[0][4:])
        except ValueError:
            ref = None
    row, is_new = db.touch_user(u.id, u.username, u.first_name, ref)
    if is_new and row["referrer_id"]:
        try:
            await context.bot.send_message(
                row["referrer_id"],
                f"🎁 По вашей ссылке присоединился новый гость. Когда он оформит доступ, "
                f"вы получите <b>+{plural_days(config.REF_BONUS_DAYS)}</b>.")
        except TelegramError:
            pass
    context.user_data.clear()
    await show(update, context, main_text(row), main_kb(row))


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"<b>Условия {esc(config.BRAND)}</b>\n\n"
        "1. Подписка даёт доступ к VPN на оплаченный срок.\n"
        "2. Запрещено использовать сервис для незаконной деятельности, спама и атак.\n"
        f"3. Если VPN не заработал, мы вернём звёзды в течение {plural_days(config.REFUND_DAYS)} "
        "после оплаты: напишите консьержу.\n"
        "4. Мы не храним историю ваших посещений.\n"
        "5. Об изменениях условий мы сообщим в боте.")


async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = f"@{esc(config.SUPPORT)}" if config.SUPPORT else "администратору бота"
    await update.message.reply_text(
        "<b>Вопросы по оплате</b>\n\n"
        f"Напишите {contact} и укажите дату оплаты и тариф. Возврат возможен в течение "
        f"{plural_days(config.REFUND_DAYS)}, если VPN не заработал.")


# ---------------------------------------------------------------- кнопки

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    data = q.data or ""
    row = current_user(update)
    uid = row["id"]

    if data == "trial":
        if not can_trial(row):
            await q.answer("Пробный период уже использован", show_alert=True)
            return
        db.mark_trial(uid)
        row = await grant(uid, config.TRIAL_DAYS)
        await q.answer("✦ Пробный период активирован")
        await show(update, context,
                   f"<b>Пробный доступ на {plural_days(config.TRIAL_DAYS)} активирован</b>\n\n"
                   "Ваш персональный ключ:\n" + key_block(row),
                   key_kb(), banner="welcome")
        await notify_admins(context, f"✦ Пробный период: {esc(row['first_name'] or '')} (<code>{uid}</code>)")
        return

    if data.startswith("buy:"):
        plan = data[4:]
        if plan not in config.PLANS:
            await q.answer("Тариф не найден, откройте меню заново", show_alert=True)
            return
        name, days, price = config.PLANS[plan]
        await q.answer("Счёт ниже 👇")
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=f"{config.BRAND} · {name}",
            description=f"Персональный доступ к VPN на {plural_days(days)}. "
                        "Ключ придёт сразу после оплаты.",
            payload=f"plan:{plan}:{days}:{price}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(name, price)],
        )
        return

    if data == "qr":
        if not is_active(row) or not row["vpn_key"]:
            await q.answer("Сначала оформите доступ", show_alert=True)
            return
        await q.answer()
        img = qrcode.make(row["vpn_key"], border=2, box_size=10)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await context.bot.send_photo(update.effective_chat.id, buf,
                                     caption="📷 Отсканируйте код в приложении VPN." + demo_note())
        return

    if data in ("adm:stats", "adm:bc"):
        await q.answer("Обновлено" if data == "adm:stats" and uid in config.ADMIN_IDS else None)
        if uid not in config.ADMIN_IDS:
            return
        if data == "adm:stats":
            await show(update, context, admin_text(), admin_kb())
        else:
            context.user_data["await"] = "broadcast"
            await show(update, context,
                       "<b>Рассылка</b>\n\nОтправьте сообщение, и я перешлю его всем гостям. "
                       "Можно с картинкой и форматированием.",
                       KB([B("‹ Отмена", "adm:stats")]))
        return

    await q.answer()
    context.user_data.pop("await", None)

    if data == "menu":
        await show(update, context, main_text(row), main_kb(row))
    elif data == "plans":
        await show(update, context, plans_text(), plans_kb(), banner="plans")
    elif data == "key":
        if not is_active(row):
            kb = [[B("◆ Оформить доступ", "plans")]]
            if can_trial(row):
                kb.append([B("✦ Попробовать бесплатно", "trial")])
            kb.append([BACK])
            await show(update, context,
                       "<b>Ключа пока нет</b>\n\nОформите доступ или возьмите пробный период, "
                       "и ваш персональный ключ появится здесь.",
                       InlineKeyboardMarkup(kb), banner="key")
            return
        if not row["vpn_key"] or not row["key_active"]:
            db.set_key(uid, await vpn.issue(uid, row["expires_at"]), True)
            row = db.get_user(uid)
        await show(update, context, "<b>Ваш персональный ключ</b>\n\n" + key_block(row),
                   key_kb(), banner="key")
    elif data == "howto":
        await show(update, context,
                   "<b>Подключение за минуту</b>\n<i>Выберите устройство, и я покажу шаги.</i>",
                   KB([B(APPS["android"][0], "how:android"), B(APPS["ios"][0], "how:ios")],
                      [B(APPS["windows"][0], "how:windows"), B(APPS["mac"][0], "how:mac")],
                      [BACK]), banner="howto")
    elif data.startswith("how:") and data[4:] in APPS:
        await show(update, context, howto_text(data[4:]),
                   KB([B("🗝 Мой ключ", "key"), B("‹ Устройства", "howto")], [BACK]), banner="howto")
    elif data == "profile":
        await show(update, context,
                   "<b>Профиль</b>\n\n"
                   f"<blockquote>◆ ID: <code>{uid}</code>\n"
                   f"◆ С нами с {fmt_date(row['joined_at'])}\n"
                   f"◆ Оплачено: {row['paid_stars']} ⭐\n"
                   f"◆ Приглашено друзей: {db.referral_count(uid)}</blockquote>\n\n"
                   + status_line(row),
                   KB([B("◆ Продлить доступ" if is_active(row) else "◆ Оформить доступ", "plans")],
                      [BACK]), banner="profile")
    elif data == "ref":
        link = f"https://t.me/{context.bot.username}?start=ref_{uid}"
        share = ("https://t.me/share/url?url=" + link.replace(":", "%3A").replace("/", "%2F")
                 + "&text=" + f"Приглашаю в {config.BRAND}: быстрый приватный VPN".replace(" ", "%20"))
        await show(update, context,
                   "<b>Привилегия для друзей</b>\n\n"
                   f"За каждого друга, который оформит доступ, вы получаете "
                   f"<b>+{plural_days(config.REF_BONUS_DAYS)}</b>. Без ограничений.\n\n"
                   f"◆ Ваша ссылка:\n<code>{link}</code>\n\n"
                   f"◆ Приглашено: <b>{db.referral_count(uid)}</b>",
                   KB([B("📤 Отправить приглашение", url=share)], [BACK]), banner="ref")
    elif data == "promo":
        context.user_data["await"] = "promo"
        await show(update, context, "<b>Промокод</b>\n\nОтправьте промокод одним сообщением.",
                   KB([B("‹ Отмена", "menu")]))
    elif data == "support":
        rows = []
        if config.SUPPORT:
            rows.append([B("🛎 Написать консьержу", url=f"https://t.me/{config.SUPPORT}")])
        rows.append([BACK])
        contact = f"@{esc(config.SUPPORT)}" if config.SUPPORT else "контакт скоро появится"
        await show(update, context,
                   "<b>Консьерж</b>\n<i>Поможем подключиться и ответим на вопросы.</i>\n\n"
                   f"◆ Связь: {contact}\n\n"
                   "<blockquote>Не подключается? Проверьте, что ключ скопирован целиком и "
                   "доступ активен.\n"
                   f"Возврат звёзд в течение {plural_days(config.REFUND_DAYS)}, если VPN не заработал."
                   "</blockquote>\n\nУсловия: /terms",
                   InlineKeyboardMarkup(rows), banner="support")


# ---------------------------------------------------------------- оплата

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    try:
        _, plan, days, price = q.invoice_payload.split(":")
        days, price = int(days), int(price)
    except ValueError:
        await q.answer(ok=False, error_message="Счёт устарел. Откройте меню и выберите тариф заново.")
        return
    current = config.PLANS.get(plan)
    if q.currency != "XTR" or not current or current[1] != days or current[2] != price \
            or q.total_amount != price:
        await q.answer(ok=False, error_message="Тариф изменился. Откройте меню и выберите тариф заново.")
        return
    await q.answer(ok=True)


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    u = update.effective_user
    row = current_user(update)
    _, plan, days, _price = sp.invoice_payload.split(":")
    days = int(days)
    first_payment = db.payments_count(u.id) == 0
    if not db.add_payment(u.id, plan, sp.total_amount, days, sp.telegram_payment_charge_id):
        return  # Telegram прислал тот же платёж повторно
    row = await grant(u.id, days)

    if first_payment and row["referrer_id"]:
        ref_row = await grant(row["referrer_id"], config.REF_BONUS_DAYS)
        try:
            await context.bot.send_message(
                ref_row["id"],
                f"🎁 Ваш друг оформил доступ. Вам начислено <b>+{plural_days(config.REF_BONUS_DAYS)}</b>.\n"
                f"◆ Доступ действует до <b>{fmt_date(ref_row['expires_at'])}</b>.")
        except TelegramError:
            pass

    name = config.PLANS.get(plan, (plan,))[0]
    await show(update, context,
               "<b>Оплата прошла. Благодарим за доверие.</b>\n\n"
               f"◆ Тариф: <b>{esc(name)}</b>\n"
               f"◆ Действует до <b>{fmt_date(row['expires_at'])}</b>\n\n"
               f"Ваш персональный ключ:\n<code>{esc(row['vpn_key'])}</code>\n\n"
               "<i>Нажмите на ключ, чтобы скопировать.</i>" + demo_note(),
               KB([B("📲 Подключение", "howto"), B("📷 QR-код", "qr")], [BACK]),
               banner="welcome", effect=CONFETTI)
    who = f"@{esc(u.username)}" if u.username else esc(u.first_name or str(u.id))
    await notify_admins(context, f"💰 Оплата: {who} · {esc(name)} · {sp.total_amount} ⭐\n"
                                 f"charge: <code>{esc(sp.telegram_payment_charge_id)}</code>")


# ---------------------------------------------------------------- сообщения

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    row = current_user(update)
    mode = context.user_data.pop("await", None)

    if mode == "broadcast" and row["id"] in config.ADMIN_IDS:
        await msg.reply_text("Рассылка началась…")
        ok = fail = 0
        for uid in db.all_user_ids():
            try:
                await context.bot.copy_message(uid, msg.chat_id, msg.message_id)
                ok += 1
            except (Forbidden, BadRequest):
                fail += 1
            await asyncio.sleep(0.05)
        await msg.reply_text(f"Готово. Доставлено: {ok}, не доставлено: {fail}.")
        return

    if mode == "promo" and msg.text:
        await redeem(update, context, msg.text)
        return

    await show(update, context, main_text(row), main_kb(row))


async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    uid = update.effective_user.id
    status, days = db.redeem_promo(code, uid)
    if status != "ok":
        reason = {"not_found": "Такого промокода нет.", "used_up": "У этого промокода закончились активации.",
                  "already": "Вы уже использовали этот промокод."}[status]
        await show(update, context, f"<b>Промокод не принят</b>\n\n{reason}",
                   KB([B("🎟 Ввести другой", "promo"), BACK]))
        return
    row = await grant(uid, days)
    await show(update, context,
               f"<b>Промокод принят</b>\n\n◆ Начислено <b>+{plural_days(days)}</b>\n"
               f"◆ Доступ действует до <b>{fmt_date(row['expires_at'])}</b>",
               KB([B("🗝 Мой ключ", "key"), BACK]), banner="welcome")


async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    if not context.args:
        context.user_data["await"] = "promo"
        await update.message.reply_text("🎟 Отправьте промокод одним сообщением.")
        return
    await redeem(update, context, context.args[0])


# ---------------------------------------------------------------- админка

def admin_text() -> str:
    s = db.stats()
    return ("<b>Админ-панель</b>\n\n"
            f"<blockquote>◆ Гостей: <b>{s['users']}</b> (+{s['new_today']} за сутки)\n"
            f"◆ Активных подписок: <b>{s['active']}</b>\n"
            f"◆ Брали пробный период: {s['trials']}\n"
            f"◆ Оплат: {s['payments']}\n"
            f"◆ Выручка: <b>{s['stars']} ⭐</b> (+{s['stars_today']} за сутки)</blockquote>\n\n"
            "<b>Команды</b>\n"
            "/give <code>id</code> <code>дней</code>: начислить дни\n"
            "/addpromo <code>КОД</code> <code>дней</code> <code>активаций</code>\n"
            "/refund <code>charge_id</code>: вернуть звёзды")


def admin_kb() -> InlineKeyboardMarkup:
    return KB([B("🔄 Обновить", "adm:stats"), B("📢 Рассылка", "adm:bc")], [BACK])


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
async def give(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        uid, days = int(context.args[0]), int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Формат: /give <code>id</code> <code>дней</code>")
        return
    if not db.get_user(uid):
        await update.message.reply_text("Такого гостя нет в боте.")
        return
    row = await grant(uid, days)
    await update.message.reply_text(f"Начислено {plural_days(days)}. Доступ до {fmt_date(row['expires_at'])}.")
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
    db.add_promo(code, days, uses)
    await update.message.reply_text(
        f"Промокод <code>{esc(code.upper())}</code>: +{plural_days(days)}, активаций: {uses}.")


@admin_only
async def refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Формат: /refund <code>charge_id</code> (он есть в уведомлении об оплате)")
        return
    charge = context.args[0]
    p = db.get_payment(charge)
    if not p:
        await update.message.reply_text("Платёж не найден.")
        return
    if p["refunded"]:
        await update.message.reply_text("Этот платёж уже возвращён.")
        return
    try:
        await context.bot.refund_star_payment(p["user_id"], charge)
    except TelegramError as e:
        await update.message.reply_text(f"Telegram не принял возврат: {esc(str(e))}")
        return
    db.mark_refunded(charge)
    row = db.get_user(p["user_id"])
    if not is_active(row) and row["key_active"]:
        await vpn.revoke(row["id"])
        db.set_key(row["id"], row["vpn_key"], False)
    await update.message.reply_text(f"Возвращено {p['stars']} ⭐, срок доступа уменьшен.")


# ---------------------------------------------------------------- фоновые задачи

async def lifecycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for row in db.expiring_soon(DAY):
        try:
            await context.bot.send_message(
                row["id"],
                f"⏳ Ваш доступ закончится <b>{fmt_date(row['expires_at'])}</b>.\n"
                "Продлите заранее, чтобы VPN не отключился.",
                reply_markup=KB([B("◆ Продлить доступ", "plans")]))
        except TelegramError:
            pass
        db.mark_reminded(row["id"], row["expires_at"])

    for row in db.expired_with_key():
        await vpn.revoke(row["id"])
        db.set_key(row["id"], row["vpn_key"], False)
        try:
            await context.bot.send_message(
                row["id"], "Срок доступа закончился, VPN отключён. Продлите, чтобы снова пользоваться.",
                reply_markup=KB([B("◆ Продлить доступ", "plans")]))
        except TelegramError:
            pass


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке обновления", exc_info=context.error)


# ---------------------------------------------------------------- профиль бота

async def setup_profile(app: Application) -> None:
    """Имя, описание до /start и меню команд — бот ставит себе сам."""
    if not config.SET_PROFILE:
        return
    bot = app.bot
    steps = [
        lambda: bot.set_my_commands([
            BotCommand("start", "Главное меню"),
            BotCommand("promo", "Ввести промокод"),
            BotCommand("terms", "Условия"),
            BotCommand("paysupport", "Вопросы по оплате"),
        ]),
        lambda: bot.set_my_short_description(f"{config.BRAND} · {config.TAGLINE}"[:120]),
        lambda: bot.set_my_description(
            (f"{config.BRAND}\n{config.TAGLINE}.\n\n" + bullets(config.FEATURES)
             + f"\n\n✦ Пробный период бесплатно\n✦ Оплата звёздами Telegram\n\n"
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


# ---------------------------------------------------------------- запуск

def build_app(token: str) -> Application:
    app = (Application.builder().token(token)
           .defaults(Defaults(parse_mode=ParseMode.HTML))
           .post_init(setup_profile).build())
    banners = {}
    for name, path in make_banner.ensure().items():
        with open(path, "rb") as f:
            banners[name] = f.read()
    app.bot_data["banners"] = banners

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("terms", terms))
    app.add_handler(CommandHandler("paysupport", paysupport))
    app.add_handler(CommandHandler("promo", promo_cmd))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(CommandHandler("addpromo", addpromo))
    app.add_handler(CommandHandler("refund", refund))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, paid))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(lifecycle_job, interval=3600, first=30)
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
