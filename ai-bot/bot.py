"""Telegram-бот с ИИ: чат, генерация фото и видео через OpenRouter, с экономией баланса.

Запуск:  python bot.py   (настройки — в файле .env, см. .env.example)
"""
import base64
import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

import ai
import budget
import config
import images

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

BTN_CHAT, BTN_PHOTO, BTN_VIDEO, BTN_RESET, BTN_BAL = "💬 Чат", "🖼 Фото", "🎬 Видео", "🧹 Сброс", "💰 Баланс"
MENU = ReplyKeyboardMarkup([[BTN_CHAT, BTN_PHOTO, BTN_VIDEO], [BTN_BAL, BTN_RESET]], resize_keyboard=True)

HELP = (
    "Я бот с искусственным интеллектом.\n\n"
    f"{BTN_CHAT} — просто пиши, я отвечу. Можно присылать фото с вопросом.\n"
    f"{BTN_PHOTO} — опиши картинку, нарисую. Персонажей (Асуна, Наруто...) узнаю по имени.\n"
    f"{BTN_VIDEO} — опиши сцену, сделаю видео. Перед генерацией покажу цену.\n"
    f"{BTN_BAL} — сколько потрачено и сколько осталось.\n\n"
    "/model — модель картинок, /vmodel — модель видео, /reset — забыть диалог, /id — ваш id"
)


# ---------- помощники ----------

def allowed(update: Update) -> bool:
    return not config.ALLOWED_USERS or (update.effective_user and update.effective_user.id in config.ALLOWED_USERS)


async def deny(update: Update) -> None:
    await update.effective_message.reply_text(
        f"Доступ закрыт. Ваш id: {update.effective_user.id} — владелец может добавить его в ALLOWED_USERS."
    )


async def send_long(update: Update, text: str) -> None:
    for i in range(0, len(text), 4000):
        await update.effective_message.reply_text(text[i:i + 4000])


async def over_limit(update: Update, estimate: float) -> bool:
    if budget.can_spend(estimate):
        return False
    await update.effective_message.reply_text(
        f"⛔ Дневной лимит {budget.fmt(config.DAILY_LIMIT_USD)} исчерпан "
        f"(сегодня потрачено {budget.fmt(budget.spent_today())}). Завтра лимит обнулится."
    )
    return True


def image_model(context: ContextTypes.DEFAULT_TYPE) -> str:
    m = context.user_data.get("image_model", config.IMAGE_MODEL)
    return m if m in config.IMAGE_MODELS else next(iter(config.IMAGE_MODELS))


def video_model(context: ContextTypes.DEFAULT_TYPE) -> str:
    m = context.user_data.get("video_model", config.VIDEO_MODEL)
    return m if m in config.VIDEO_MODELS else "google/veo-3.1-lite"


def picker(options: dict, current: str, prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(("✅ " if mid == current else "") + val[0], callback_data=f"{prefix}:{mid}")]
        for mid, val in options.items()
    ])


def image_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Ещё вариант", callback_data="img:again")],
        [InlineKeyboardButton("⬛ 1:1", callback_data="img:1:1"),
         InlineKeyboardButton("🖥 16:9", callback_data="img:16:9"),
         InlineKeyboardButton("📱 9:16", callback_data="img:9:16")],
    ])


# ---------- команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    context.user_data["mode"] = "chat"
    await update.message.reply_text(HELP, reply_markup=MENU)


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ваш Telegram id: {update.effective_user.id}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["history"] = []
    await update.message.reply_text("История очищена 🧹", reply_markup=MENU)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    left = await budget.balance()
    lim = config.DAILY_LIMIT_USD
    text = f"💰 Сегодня потрачено: {budget.fmt(budget.spent_today())}"
    if lim > 0:
        text += f" из {budget.fmt(lim)} (дневной лимит)"
    if left is not None:
        text += f"\n🏦 Осталось на OpenRouter: ${left:.2f}"
        img = config.IMAGE_MODELS[image_model(context)][1]
        vid = config.VIDEO_MODELS[video_model(context)][2]
        if img:
            text += f"\n≈ {int(left / img)} картинок или ≈ {int(left / vid)} видео на текущих моделях"
    await update.message.reply_text(text)


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    await update.message.reply_text("Модель для картинок:",
                                    reply_markup=picker(config.IMAGE_MODELS, image_model(context), "model"))


async def cmd_vmodel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    await update.message.reply_text("Модель для видео (цена за один ролик):",
                                    reply_markup=picker(config.VIDEO_MODELS, video_model(context), "vmodel"))


async def picker_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    kind, mid = q.data.split(":", 1)
    options = config.IMAGE_MODELS if kind == "model" else config.VIDEO_MODELS
    if mid in options:
        context.user_data["image_model" if kind == "model" else "video_model"] = mid
    await q.answer("Готово")
    current = image_model(context) if kind == "model" else video_model(context)
    await q.edit_message_text(f"Выбрано: {options[current][0]}", reply_markup=picker(options, current, kind))


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    context.user_data["mode"] = mode
    texts = {
        "chat": "Режим чата. Пиши что угодно 💬",
        "photo": f"Режим фото 🖼 Модель: {config.IMAGE_MODELS[image_model(context)][0]}\n"
                 "Опиши, что нарисовать. Например: «Асуна в зимнем лесу»\nСменить модель: /model",
        "video": f"Режим видео 🎬 Модель: {config.VIDEO_MODELS[video_model(context)][0]}\n"
                 "Опиши сцену. Например: «дракон пролетает над ночным городом»\nСменить модель: /vmodel",
    }
    if mode == "video" and not config.VIDEO_ENABLED:
        texts["video"] = "⚠️ Видео выключено владельцем бота."
    await update.message.reply_text(texts[mode], reply_markup=MENU)


# ---------- чат ----------

async def do_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, image_b64: str | None = None) -> None:
    if not ai.has_chat():
        return await update.effective_message.reply_text("⚠️ Владелец не указал ключ ИИ в .env.")
    if await over_limit(update, 0.002):
        return
    history = context.user_data.setdefault("history", [])
    msg = {"role": "user", "text": text}
    if image_b64:
        msg["image_b64"] = image_b64
    history.append(msg)
    del history[:-config.HISTORY_LIMIT]
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        answer = await ai.chat(history)
    except ai.AIError as e:
        history.pop()
        return await update.effective_message.reply_text(f"⚠️ {e}")
    except Exception:
        history.pop()
        log.exception("chat error")
        return await update.effective_message.reply_text("⚠️ ИИ не ответил, попробуйте ещё раз.")
    history.append({"role": "assistant", "text": answer})
    for m in history:  # картинки в истории дорогие — после ответа оставляем только текст
        m.pop("image_b64", None)
    await send_long(update, answer)


# ---------- фото ----------

async def do_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, idea: str, aspect: str = "1:1",
                   prompt: str | None = None) -> None:
    model = image_model(context)
    if await over_limit(update, config.IMAGE_MODELS[model][1]):
        return
    if context.user_data.get("busy"):
        return await update.effective_message.reply_text("Подожди, ещё делаю предыдущее ⏳")
    context.user_data["busy"] = True
    status = await update.effective_message.reply_text("🎨 Рисую... (10–40 сек)")
    try:
        await update.effective_chat.send_action(ChatAction.UPLOAD_PHOTO)
        before = budget.spent_today()
        prompt = prompt or await ai.enhance_prompt(idea, "image")
        data = await images.generate_image(prompt, aspect, model)
        cost = budget.spent_today() - before
        context.user_data["last_image"] = {"idea": idea, "prompt": prompt, "aspect": aspect}
        await update.effective_message.reply_photo(
            photo=io.BytesIO(data), caption=f"🖼 {idea[:800]}\n💰 {budget.fmt(cost)}", reply_markup=image_buttons(),
        )
        await update.effective_message.reply_document(
            document=io.BytesIO(data), filename="image.png", caption="Оригинал без сжатия",
        )
        await status.delete()
    except Exception as e:
        log.exception("image error")
        await status.edit_text(f"⚠️ Не получилось: {e}")
    finally:
        context.user_data["busy"] = False


async def image_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    last = context.user_data.get("last_image")
    if not last:
        return await q.message.reply_text("Сначала опиши картинку.")
    action = q.data.removeprefix("img:")
    aspect = last["aspect"] if action == "again" else action
    # Повтор — с уже готовым промптом, без лишнего запроса на улучшение.
    await do_photo(update, context, last["idea"], aspect, prompt=last["prompt"])


# ---------- видео ----------

async def ask_video(update: Update, context: ContextTypes.DEFAULT_TYPE, idea: str) -> None:
    """Сначала показываем цену — видео дорогое, случайно не потратим."""
    if not config.VIDEO_ENABLED:
        return await update.effective_message.reply_text("⚠️ Видео выключено владельцем бота.")
    label, _, price = config.VIDEO_MODELS[video_model(context)]
    context.user_data["pending_video"] = idea
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"▶️ Сделать (~${price:.2f})", callback_data="vid:go:16:9"),
         InlineKeyboardButton("📱 Вертикальное", callback_data="vid:go:9:16")],
        [InlineKeyboardButton("⚙️ Сменить модель", callback_data="vid:models"),
         InlineKeyboardButton("✖️ Отмена", callback_data="vid:cancel")],
    ])
    await update.effective_message.reply_text(f"🎬 {idea[:500]}\n\nМодель: {label}", reply_markup=kb)


async def video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")  # vid:go:16:9 | vid:models | vid:cancel
    if parts[1] == "cancel":
        context.user_data.pop("pending_video", None)
        return await q.edit_message_text("Отменено.")
    if parts[1] == "models":
        return await q.message.reply_text("Модель для видео:",
                                          reply_markup=picker(config.VIDEO_MODELS, video_model(context), "vmodel"))
    idea = context.user_data.pop("pending_video", None)
    if not idea:
        return await q.edit_message_text("Опиши видео ещё раз.")
    await q.edit_message_reply_markup(None)
    aspect = f"{parts[2]}:{parts[3]}" if len(parts) > 3 else "16:9"
    await do_video(update, context, idea, aspect)


async def do_video(update: Update, context: ContextTypes.DEFAULT_TYPE, idea: str, aspect: str = "16:9") -> None:
    model = video_model(context)
    label, params, price = config.VIDEO_MODELS[model]
    if await over_limit(update, price):
        return
    if context.user_data.get("busy"):
        return await update.effective_message.reply_text("Подожди, ещё делаю предыдущее ⏳")
    context.user_data["busy"] = True
    status = await update.effective_message.reply_text("🎬 Генерирую видео... обычно 1–4 минуты.")

    async def progress(sec: int) -> None:
        try:
            await status.edit_text(f"🎬 Генерирую видео... прошло {sec} сек.")
        except Exception:
            pass

    try:
        prompt = await ai.enhance_prompt(idea, "video")
        if config.VIDEO_PROVIDER == "openrouter":
            data, cost = await ai.openrouter_video(prompt, model, params, aspect, on_progress=progress)
        else:
            data, cost = await ai.veo_video(prompt, aspect, on_progress=progress), 0.0
        await update.effective_chat.send_action(ChatAction.UPLOAD_VIDEO)
        await update.effective_message.reply_video(
            video=io.BytesIO(data), caption=f"🎬 {idea[:800]}\n💰 {budget.fmt(cost or price)}",
            supports_streaming=True,
        )
        await status.delete()
    except Exception as e:
        log.exception("video error")
        await status.edit_text(f"⚠️ Не получилось: {e}")
    finally:
        context.user_data["busy"] = False


# ---------- маршрутизация сообщений ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    text = update.message.text.strip()
    buttons = {BTN_CHAT: "chat", BTN_PHOTO: "photo", BTN_VIDEO: "video"}
    if text in buttons:
        return await set_mode(update, context, buttons[text])
    if text == BTN_RESET:
        return await reset(update, context)
    if text == BTN_BAL:
        return await cmd_balance(update, context)

    mode = context.user_data.get("mode", "chat")
    if mode == "photo":
        await do_photo(update, context, text)
    elif mode == "video":
        await ask_video(update, context, text)
    else:
        await do_chat(update, context, text)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фото с вопросом — ИИ смотрит на картинку."""
    if not allowed(update):
        return await deny(update)
    file = await update.message.photo[-1].get_file()
    raw = await file.download_as_bytearray()
    await do_chat(update, context, update.message.caption or "Что на этом фото?",
                  base64.b64encode(bytes(raw)).decode())


async def cmd_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    idea = " ".join(context.args)
    if not idea:
        return await set_mode(update, context, "photo")
    await do_photo(update, context, idea)


async def cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    idea = " ".join(context.args)
    if not idea:
        return await set_mode(update, context, "video")
    await ask_video(update, context, idea)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error: %s", context.error)


def main() -> None:
    if not config.TELEGRAM_TOKEN:
        raise SystemExit("Нет TELEGRAM_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    if not ai.has_chat():
        log.warning("Нет ключа ИИ (OPENROUTER_API_KEY или GEMINI_API_KEY) — чат работать не будет.")
    if not config.ALLOWED_USERS:
        log.warning("ALLOWED_USERS пуст — ботом может пользоваться кто угодно и тратить ваш баланс!")
    log.info("Чат: %s (%s), фото: %s, видео: %s (%s), лимит в день: $%s", config.AI_PROVIDER, config.CHAT_MODEL,
             config.IMAGE_MODEL, config.VIDEO_PROVIDER, config.VIDEO_MODEL, config.DAILY_LIMIT_USD)

    app = Application.builder().token(config.TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("vmodel", cmd_vmodel))
    app.add_handler(CommandHandler("photo", cmd_photo))
    app.add_handler(CommandHandler("video", cmd_video))
    app.add_handler(CallbackQueryHandler(image_callback, pattern=r"^img:"))
    app.add_handler(CallbackQueryHandler(video_callback, pattern=r"^vid:"))
    app.add_handler(CallbackQueryHandler(picker_callback, pattern=r"^v?model:"))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    log.info("Бот запущен. Остановить: Ctrl+C")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
