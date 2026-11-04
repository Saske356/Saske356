"""Бот для продажи подписки на VPN за Telegram Stars.

Запуск:  python bot.py   (настройки в .env, см. .env.example)
"""

import asyncio
import datetime
import html
import io
import logging
import time

import qrcode
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update)
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


def B(text: str, data: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=url) if url else InlineKeyboardButton(text, callback_data=data)


def KB(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows])


BACK = B("‹ В меню", "menu")


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


def status_line(row) -> str:
    if is_active(row):
        return (f"🟢 Подписка активна до <b>{fmt_date(row['expires_at'])}</b>\n"
                f"Осталось: <b>{plural_days(days_left(row))}</b>")
    return "⚪️ Подписки пока нет. Подключение займёт минуту."


def demo_note() -> str:
    return ("\n\n<i>⚠️ Демо-режим: сервер ещё не подключён, ключ пока не работает.</i>"
            if vpn.is_demo else "")


def main_text(row) -> str:
    feats = "\n".join(esc(f) for f in config.FEATURES)
    name = esc(row["first_name"] or "друг")
    return (f"<b>🛡 {esc(config.BRAND)}</b>\n"
            f"<i>{esc(config.TAGLINE)}</i>\n\n"
            f"Привет, {name}!\n"
            f"<blockquote>{feats}</blockquote>\n\n"
            f"{status_line(row)}")


def main_kb(row) -> InlineKeyboardMarkup:
    rows = [[B("🚀 Продлить подписку" if is_active(row) else "🚀 Купить подписку", "plans")]]
    if not row["trial_used"] and not is_active(row) and row["paid_stars"] == 0 and config.TRIAL_DAYS > 0:
        rows.append([B(f"🎁 {plural_days(config.TRIAL_DAYS).capitalize()} бесплатно", "trial")])
    rows += [
        [B("🔑 Мой ключ", "key"), B("📲 Как подключить", "howto")],
        [B("👤 Профиль", "profile"), B(f"👥 +{config.REF_BONUS_DAYS} дн. за друга", "ref")],
        [B("🎟 Промокод", "promo"), B("💬 Поддержка", "support")],
    ]
    return InlineKeyboardMarkup(rows)


def plan_discount(days: int, price: int) -> int:
    base = config.PLANS["m1"][2] if "m1" in config.PLANS else price
    full = base * days / 30
    return max(0, round((1 - price / full) * 100)) if full else 0


def plans_text() -> str:
    lines = []
    for _, (name, days, price) in config.PLANS.items():
        d = plan_discount(days, price)
        per_month = price / (days / 30)
        tail = f"  <b>−{d}%</b>" if d >= 3 else ""
        lines.append(f"• {name}: <b>{price} ⭐</b>  <i>({per_month:.0f} ⭐/мес)</i>{tail}")
    return ("<b>🚀 Выбери тариф</b>\n\n"
            f"<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
            "Оплата звёздами Telegram ⭐ прямо в чате.\n"
            "Продление добавляется к оставшимся дням, ничего не сгорает.")


def plans_kb() -> InlineKeyboardMarkup:
    keys = list(config.PLANS)
    rows = []
    for k in keys:
        name, days, price = config.PLANS[k]
        badge = " 👑" if k == keys[-1] else (" 🔥" if len(keys) > 2 and k == keys[1] else "")
        rows.append([B(f"{name} · {price} ⭐{badge}", f"buy:{k}")])
    rows.append([BACK])
    return InlineKeyboardMarkup(rows)


APPS = {
    "android": ("🤖 Android", "v2rayNG или Hiddify", "Google Play"),
    "ios": ("🍏 iPhone и iPad", "Streisand, V2Box или Hiddify", "App Store"),
    "windows": ("🪟 Windows", "Hiddify или v2rayN", "с их официальных сайтов"),
    "mac": ("💻 macOS", "Hiddify или V2Box", "App Store"),
}


def howto_text(platform: str) -> str:
    title, apps, store = APPS[platform]
    return (f"<b>{title}</b>\n\n"
            f"<blockquote>1. Установи {esc(apps)} ({esc(store)}).\n"
            "2. Открой в боте «🔑 Мой ключ» и нажми на ключ: он скопируется.\n"
            "3. В приложении нажми «+» и выбери «Импорт из буфера обмена».\n"
            "4. Нажми кнопку подключения ▶️</blockquote>\n\n"
            "Готово, интернет работает через VPN. Если что-то не так, пиши в поддержку.")


def key_text(row) -> str:
    return ("<b>🔑 Твой ключ</b>\n\n"
            f"<code>{esc(row['vpn_key'])}</code>\n\n"
            "<i>Нажми на ключ, и он скопируется.</i>\n"
            f"Действует до <b>{fmt_date(row['expires_at'])}</b>" + demo_note())


def key_kb() -> InlineKeyboardMarkup:
    return KB([B("📷 QR-код", "qr"), B("📲 Как подключить", "howto")], [BACK])


# ---------------------------------------------------------------- показ «карточки»

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
               kb: InlineKeyboardMarkup) -> None:
    """Показывает экран бота: баннер + текст + кнопки. Если можно, редактирует
    текущее сообщение, чтобы в чате не копилась лента."""
    q = update.callback_query
    banner_uid = context.bot_data.get("banner_uid")
    if q and q.message and q.message.photo and q.message.photo[-1].file_unique_id == banner_uid:
        try:
            await q.edit_message_caption(caption=text, reply_markup=kb)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            log.warning("edit failed, sending new card: %s", e)
    photo = context.bot_data.get("banner_id") or context.bot_data["banner_bytes"]
    msg = await context.bot.send_photo(update.effective_chat.id, photo, caption=text, reply_markup=kb)
    if "banner_id" not in context.bot_data:
        context.bot_data["banner_id"] = msg.photo[-1].file_id
        context.bot_data["banner_uid"] = msg.photo[-1].file_unique_id


def current_user(update: Update):
    u = update.effective_user
    row, _ = db.touch_user(u.id, u.username, u.first_name)
    return row


async def grant(user_id: int, days: int):
    """Добавляет дни и выдаёт/продлевает ключ. Возвращает обновлённую строку."""
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
                f"👥 По твоей ссылке пришёл новый пользователь. Когда он оформит подписку, "
                f"тебе начислится +{config.REF_BONUS_DAYS} дн.")
        except TelegramError:
            pass
    context.user_data.clear()
    await show(update, context, main_text(row), main_kb(row))


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"<b>📄 Условия {esc(config.BRAND)}</b>\n\n"
        "1. Подписка даёт доступ к VPN на оплаченный срок.\n"
        "2. Запрещено использовать сервис для незаконной деятельности, спама и атак.\n"
        f"3. Если VPN не заработал, вернём звёзды в течение {plural_days(config.REFUND_DAYS)} после оплаты: "
        "напиши в поддержку.\n"
        "4. Мы не храним историю твоих посещений.\n"
        "5. Условия могут меняться, об изменениях сообщим в боте.")


async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = f"@{esc(config.SUPPORT)}" if config.SUPPORT else "администратору бота"
    await update.message.reply_text(
        "<b>💳 Вопросы по оплате</b>\n\n"
        f"Напиши {contact}: укажи дату оплаты и тариф. Возврат возможен в течение "
        f"{plural_days(config.REFUND_DAYS)}, если VPN не заработал.")


# ---------------------------------------------------------------- кнопки

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    data = q.data or ""
    row = current_user(update)
    uid = row["id"]

    if data == "trial":
        if row["trial_used"] or row["paid_stars"] > 0 or is_active(row):
            await q.answer("Пробный период уже использован", show_alert=True)
            return
        db.mark_trial(uid)
        row = await grant(uid, config.TRIAL_DAYS)
        await q.answer("🎁 Пробный период активирован!")
        await show(update, context,
                   f"<b>🎁 Пробный период на {plural_days(config.TRIAL_DAYS)}</b>\n\n" + key_text(row)[len("<b>🔑 Твой ключ</b>\n\n"):],
                   key_kb())
        await notify_admins(context, f"🎁 Пробный период: {esc(row['first_name'] or '')} (<code>{uid}</code>)")
        return

    if data.startswith("buy:"):
        plan = data[4:]
        if plan not in config.PLANS:
            await q.answer("Тариф не найден, открой меню заново", show_alert=True)
            return
        name, days, price = config.PLANS[plan]
        await q.answer("Счёт ниже 👇")
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=f"{config.BRAND} · {name}",
            description=f"Доступ к VPN на {plural_days(days)}. Ключ придёт сразу после оплаты.",
            payload=f"plan:{plan}:{days}:{price}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(name, price)],
        )
        return

    if data == "qr":
        if not is_active(row) or not row["vpn_key"]:
            await q.answer("Сначала оформи подписку", show_alert=True)
            return
        await q.answer()
        img = qrcode.make(row["vpn_key"], border=2, box_size=10)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await context.bot.send_photo(update.effective_chat.id, buf,
                                     caption="📷 Отсканируй код в приложении VPN." + demo_note())
        return

    if data == "adm:stats":
        if uid not in config.ADMIN_IDS:
            await q.answer()
            return
        await q.answer("Обновлено")
        await show(update, context, admin_text(), admin_kb())
        return

    if data == "adm:bc":
        if uid not in config.ADMIN_IDS:
            await q.answer()
            return
        context.user_data["await"] = "broadcast"
        await q.answer()
        await show(update, context,
                   "<b>📢 Рассылка</b>\n\nОтправь сообщение, и я перешлю его всем пользователям. "
                   "Можно с картинкой и форматированием.",
                   KB([B("‹ Отмена", "adm:stats")]))
        return

    await q.answer()
    context.user_data.pop("await", None)

    if data == "menu":
        await show(update, context, main_text(row), main_kb(row))
    elif data == "plans":
        await show(update, context, plans_text(), plans_kb())
    elif data == "key":
        if not is_active(row):
            kb = [[B("🚀 Купить подписку", "plans")]]
            if not row["trial_used"] and row["paid_stars"] == 0 and config.TRIAL_DAYS > 0:
                kb.append([B("🎁 Попробовать бесплатно", "trial")])
            kb.append([BACK])
            await show(update, context,
                       "<b>🔑 Ключа пока нет</b>\n\nОформи подписку или возьми пробный период, "
                       "и ключ появится здесь.", InlineKeyboardMarkup(kb))
            return
        if not row["vpn_key"] or not row["key_active"]:
            key = await vpn.issue(uid, row["expires_at"])
            db.set_key(uid, key, True)
            row = db.get_user(uid)
        await show(update, context, key_text(row), key_kb())
    elif data == "howto":
        await show(update, context,
                   "<b>📲 Как подключить</b>\n\nВыбери своё устройство, покажу по шагам:",
                   KB([B(APPS["android"][0], "how:android"), B(APPS["ios"][0], "how:ios")],
                      [B(APPS["windows"][0], "how:windows"), B(APPS["mac"][0], "how:mac")],
                      [BACK]))
    elif data.startswith("how:") and data[4:] in APPS:
        await show(update, context, howto_text(data[4:]),
                   KB([B("🔑 Мой ключ", "key"), B("‹ Устройства", "howto")], [BACK]))
    elif data == "profile":
        await show(update, context,
                   "<b>👤 Профиль</b>\n\n"
                   f"<blockquote>ID: <code>{uid}</code>\n"
                   f"С нами с {fmt_date(row['joined_at'])}\n"
                   f"Оплачено: {row['paid_stars']} ⭐\n"
                   f"Приглашено друзей: {db.referral_count(uid)}</blockquote>\n\n"
                   + status_line(row),
                   KB([B("🚀 Продлить" if is_active(row) else "🚀 Купить", "plans"), BACK]))
    elif data == "ref":
        link = f"https://t.me/{context.bot.username}?start=ref_{uid}"
        share = ("https://t.me/share/url?url=" + link.replace(":", "%3A").replace("/", "%2F")
                 + "&text=" + "Быстрый VPN, которым пользуюсь сам 🛡".replace(" ", "%20"))
        await show(update, context,
                   "<b>👥 Приглашай друзей</b>\n\n"
                   f"Когда друг впервые оплатит подписку, тебе начислится <b>+{plural_days(config.REF_BONUS_DAYS)}</b> бесплатно. "
                   "Количество друзей не ограничено.\n\n"
                   f"Твоя ссылка:\n<code>{link}</code>\n\n"
                   f"Приглашено: <b>{db.referral_count(uid)}</b>",
                   KB([B("📤 Поделиться", url=share)], [BACK]))
    elif data == "promo":
        context.user_data["await"] = "promo"
        await show(update, context,
                   "<b>🎟 Промокод</b>\n\nОтправь промокод одним сообщением.",
                   KB([B("‹ Отмена", "menu")]))
    elif data == "support":
        rows = []
        if config.SUPPORT:
            rows.append([B("✉️ Написать в поддержку", url=f"https://t.me/{config.SUPPORT}")])
        rows.append([BACK])
        contact = f"@{esc(config.SUPPORT)}" if config.SUPPORT else "скоро появится здесь"
        await show(update, context,
                   "<b>💬 Поддержка</b>\n\n"
                   f"Контакт: {contact}\n\n"
                   "<blockquote>Не подключается? Сначала проверь, что ключ скопирован целиком и "
                   "подписка активна.\n"
                   f"Возврат звёзд: в течение {plural_days(config.REFUND_DAYS)}, если VPN не заработал.</blockquote>\n\n"
                   "Условия: /terms",
                   InlineKeyboardMarkup(rows))


# ---------------------------------------------------------------- оплата

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.pre_checkout_query
    try:
        _, plan, days, price = q.invoice_payload.split(":")
        days, price = int(days), int(price)
    except ValueError:
        await q.answer(ok=False, error_message="Счёт устарел. Открой меню и выбери тариф заново.")
        return
    current = config.PLANS.get(plan)
    if q.currency != "XTR" or not current or current[1] != days or current[2] != price \
            or q.total_amount != price:
        await q.answer(ok=False, error_message="Тариф изменился. Открой меню и выбери тариф заново.")
        return
    await q.answer(ok=True)


async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    u = update.effective_user
    row = current_user(update)
    _, plan, days, price = sp.invoice_payload.split(":")
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
                f"🎉 Твой друг оформил подписку! Тебе начислено <b>+{plural_days(config.REF_BONUS_DAYS)}</b>.\n"
                f"Подписка активна до <b>{fmt_date(ref_row['expires_at'])}</b>.")
        except TelegramError:
            pass

    name = config.PLANS.get(plan, (plan,))[0]
    await show(update, context,
               "<b>🎉 Оплата прошла, спасибо!</b>\n\n"
               f"Тариф: {esc(name)}\n"
               f"Подписка активна до <b>{fmt_date(row['expires_at'])}</b>\n\n"
               f"Твой ключ:\n<code>{esc(row['vpn_key'])}</code>\n\n"
               "<i>Нажми на ключ, чтобы скопировать, и открой «Как подключить».</i>" + demo_note(),
               KB([B("📲 Как подключить", "howto"), B("📷 QR-код", "qr")], [BACK]))
    who = f"@{esc(u.username)}" if u.username else esc(u.first_name or str(u.id))
    await notify_admins(context, f"💰 Оплата: {who} · {esc(name)} · {sp.total_amount} ⭐\n"
                                 f"charge: <code>{esc(sp.telegram_payment_charge_id)}</code>")


# ---------------------------------------------------------------- сообщения

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    row = current_user(update)
    mode = context.user_data.pop("await", None)

    if mode == "broadcast" and row["id"] in config.ADMIN_IDS:
        await msg.reply_text("📢 Рассылка началась…")
        ok = fail = 0
        for uid in db.all_user_ids():
            try:
                await context.bot.copy_message(uid, msg.chat_id, msg.message_id)
                ok += 1
            except (Forbidden, BadRequest):
                fail += 1
            await asyncio.sleep(0.05)
        await msg.reply_text(f"✅ Готово. Доставлено: {ok}, не доставлено: {fail}.")
        return

    if mode == "promo" and msg.text:
        await redeem(update, context, msg.text)
        return

    await show(update, context, main_text(row), main_kb(row))


async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    uid = update.effective_user.id
    status, days = db.redeem_promo(code, uid)
    if status != "ok":
        reason = {"not_found": "Такого промокода нет.", "used_up": "Промокод закончился.",
                  "already": "Ты уже использовал этот промокод."}[status]
        await show(update, context, f"<b>🎟 Не получилось</b>\n\n{reason}",
                   KB([B("🎟 Ввести другой", "promo"), BACK]))
        return
    row = await grant(uid, days)
    await show(update, context,
               f"<b>🎟 Промокод принят!</b>\n\nНачислено <b>+{plural_days(days)}</b>.\n"
               f"Подписка активна до <b>{fmt_date(row['expires_at'])}</b>.",
               KB([B("🔑 Мой ключ", "key"), BACK]))


async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user(update)
    if not context.args:
        context.user_data["await"] = "promo"
        await update.message.reply_text("🎟 Отправь промокод одним сообщением.")
        return
    await redeem(update, context, context.args[0])


# ---------------------------------------------------------------- админка

def admin_text() -> str:
    s = db.stats()
    return ("<b>🛠 Админ-панель</b>\n\n"
            f"<blockquote>👥 Пользователей: <b>{s['users']}</b> (+{s['new_today']} за сутки)\n"
            f"🟢 Активных подписок: <b>{s['active']}</b>\n"
            f"🎁 Брали пробный период: {s['trials']}\n"
            f"💳 Оплат: {s['payments']}\n"
            f"⭐ Выручка: <b>{s['stars']}</b> (+{s['stars_today']} за сутки)</blockquote>\n\n"
            "<b>Команды</b>\n"
            "/give <code>id</code> <code>дней</code>: выдать дни\n"
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
        await update.message.reply_text("Такого пользователя нет в боте.")
        return
    row = await grant(uid, days)
    await update.message.reply_text(f"✅ Выдано {plural_days(days)}. Подписка до {fmt_date(row['expires_at'])}.")
    try:
        await context.bot.send_message(uid, f"🎁 Тебе начислено <b>+{plural_days(days)}</b> подписки!")
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
        f"✅ Промокод <code>{esc(code.upper())}</code>: +{plural_days(days)}, активаций: {uses}.")


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
    await update.message.reply_text(f"✅ Возвращено {p['stars']} ⭐, срок подписки уменьшен.")


# ---------------------------------------------------------------- фоновые задачи

async def lifecycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for row in db.expiring_soon(DAY):
        try:
            await context.bot.send_message(
                row["id"],
                f"⏳ Подписка закончится <b>{fmt_date(row['expires_at'])}</b>.\n"
                "Продли заранее, чтобы VPN не отключился.",
                reply_markup=KB([B("🚀 Продлить", "plans")]))
        except TelegramError:
            pass
        db.mark_reminded(row["id"], row["expires_at"])

    for row in db.expired_with_key():
        await vpn.revoke(row["id"])
        db.set_key(row["id"], row["vpn_key"], False)
        try:
            await context.bot.send_message(
                row["id"], "🔴 Подписка закончилась, VPN отключён. Продли, чтобы снова пользоваться.",
                reply_markup=KB([B("🚀 Продлить", "plans")]))
        except TelegramError:
            pass


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка при обработке обновления", exc_info=context.error)


# ---------------------------------------------------------------- запуск

def build_app(token: str) -> Application:
    app = (Application.builder().token(token)
           .defaults(Defaults(parse_mode=ParseMode.HTML)).build())
    with open(make_banner.ensure(), "rb") as f:
        app.bot_data["banner_bytes"] = f.read()

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
        raise SystemExit("Нет BOT_TOKEN. Создай файл .env по образцу .env.example.")
    if vpn.is_demo:
        log.warning("VPN-сервер не подключён: бот выдаёт демо-ключи.")
    app = build_app(config.BOT_TOKEN)
    log.info("%s запущен", config.BRAND)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
