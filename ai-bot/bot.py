"""Telegram-бот с ИИ: чат (Gemini), генерация фото (FLUX / Gemini) и видео (Google Veo).

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
import config
import images

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

BTN_CHAT, BTN_PHOTO, BTN_VIDEO, BTN_RESET = "💬 Чат", "🖼 Фото", "🎬 Видео", "🧹 Сброс"
MENU = ReplyKeyboardMarkup([[BTN_CHAT, BTN_PHOTO, BTN_VIDEO], [BTN_RESET]], resize_keyboard=True)

HELP = (
    "Я бот с искусственным интеллектом.\n\n"
    f"{BTN_CHAT} — просто пиши, я отвечу. Можно присылать фото с вопросом.\n"
    f"{BTN_PHOTO} — опиши картинку, я нарисую (в высоком качестве, промпт улучшу сам).\n"
    f"{BTN_VIDEO} — опиши сцену, я сделаю видео.\n"
    f"{BTN_RESET} — забыть историю диалога.\n\n"
    "Команды: /photo текст, /video текст, /model — выбор модели картинок, /reset, /id"
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


def get_mode(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("mode", "chat")


def image_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Ещё вариант", callback_data="img:again")],
        [InlineKeyboardButton("⬛ 1:1", callback_data="img:1:1"),
         InlineKeyboardButton("🖥 16:9", callback_data="img:16:9"),
         InlineKeyboardButton("📱 9:16", callback_data="img:9:16")],
    ])


def model_buttons(current: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(("✅ " if mid == current else "") + label, callback_data=f"model:{mid}")]
            for mid, label in config.IMAGE_MODELS.items()]
    return InlineKeyboardMarkup(rows)


def user_model(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("image_model", config.IMAGE_MODEL)


# ---------- команды ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    context.user_data["mode"] = "chat"
    await update.message.reply_text(HELP, reply_markup=MENU)


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return await deny(update)
    await update.message.reply_text("Выбери модель для картинок:", reply_markup=model_buttons(user_model(context)))


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    mid = q.data.removeprefix("model:")
    if mid in config.IMAGE_MODELS:
        context.user_data["image_model"] = mid
    await q.answer("Готово")
    await q.edit_message_text(f"Модель картинок: {config.IMAGE_MODELS.get(mid, mid)}",
                              reply_markup=model_buttons(user_model(context)))


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ваш Telegram id: {update.effective_user.id}")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["history"] = []
    await update.message.reply_text("История очищена 🧹", reply_markup=MENU)


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    context.user_data["mode"] = mode
    texts = {
        "chat": "Режим чата. Пиши что угодно 💬",
        "photo": "Режим фото. Опиши, что нарисовать 🖼\nНапример: «кот-самурай под дождём в неоновом Токио»",
        "video": "Режим видео. Опиши сцену 🎬\nНапример: «дрон пролетает над заснеженными горами на рассвете»",
    }
    if mode == "video" and not config.VIDEO_ENABLED:
        texts["video"] += (
            "\n\n⚠️ Видео сейчас выключено: качественное видео (Google Veo) работает "
            "только с платным ключом Gemini API. Владелец бота может включить его в .env."
        )
    await update.message.reply_text(texts[mode], reply_markup=MENU)


# ---------- чат ----------

async def do_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, image_b64: str | None = None) -> None:
    if not ai.has_chat():
        return await update.effective_message.reply_text("⚠️ Владелец не указал ключ ИИ в .env.")
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
    # Картинки в истории много весят — после ответа оставляем только текст.
    for m in history:
        m.pop("image_b64", None)
    await send_long(update, answer)


# ---------- фото ----------

async def do_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, idea: str, aspect: str = "1:1") -> None:
    if context.user_data.get("busy"):
        return await update.effective_message.reply_text("Подожди, ещё рисую предыдущее ⏳")
    context.user_data["busy"] = True
    status = await update.effective_message.reply_text("🎨 Улучшаю промпт и рисую... (10–40 сек)")
    try:
        await update.effective_chat.send_action(ChatAction.UPLOAD_PHOTO)
        prompt = await ai.enhance_prompt(idea, "image")
        data = await images.generate_image(prompt, aspect, user_model(context))
        context.user_data["last_image"] = {"idea": idea, "prompt": prompt, "aspect": aspect}
        await update.effective_message.reply_photo(
            photo=io.BytesIO(data), caption=f"🖼 {idea[:900]}", reply_markup=image_buttons(),
        )
        # Оригинал без сжатия Telegram — для максимального качества.
        await update.effective_message.reply_document(
            document=io.BytesIO(data), filename="image.jpg", caption="Оригинал без сжатия",
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
    await do_photo(update, context, last["idea"], aspect)


# ---------- видео ----------

async def do_video(update: Update, context: ContextTypes.DEFAULT_TYPE, idea: str) -> None:
    if not config.VIDEO_ENABLED:
        return await update.effective_message.reply_text(
            "⚠️ Видео выключено. Нужен платный тариф Gemini API (Google Veo). "
            "Включите VIDEO_ENABLED=1 в .env, когда он будет."
        )
    if context.user_data.get("busy"):
        return await update.effective_message.reply_text("Подожди, ещё делаю предыдущее ⏳")
    context.user_data["busy"] = True
    status = await update.effective_message.reply_text("🎬 Генерирую видео... это 1–6 минут.")

    async def progress(sec: int) -> None:
        try:
            await status.edit_text(f"🎬 Генерирую видео... прошло {sec} сек.")
        except Exception:
            pass

    try:
        prompt = await ai.enhance_prompt(idea, "video")
        data = await ai.veo_video(prompt, on_progress=progress)
        await update.effective_chat.send_action(ChatAction.UPLOAD_VIDEO)
        await update.effective_message.reply_video(video=io.BytesIO(data), caption=f"🎬 {idea[:900]}",
                                                   supports_streaming=True)
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
    if text == BTN_CHAT:
        return await set_mode(update, context, "chat")
    if text == BTN_PHOTO:
        return await set_mode(update, context, "photo")
    if text == BTN_VIDEO:
        return await set_mode(update, context, "video")
    if text == BTN_RESET:
        return await reset(update, context)

    mode = get_mode(context)
    if mode == "photo":
        await do_photo(update, context, text)
    elif mode == "video":
        await do_video(update, context, text)
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
    await do_video(update, context, idea)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error: %s", context.error)


def main() -> None:
    if not config.TELEGRAM_TOKEN:
        raise SystemExit("Нет TELEGRAM_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    if not ai.has_chat():
        log.warning("Нет ключа ИИ (OPENROUTER_API_KEY или GEMINI_API_KEY) — чат работать не будет.")
    if not config.ALLOWED_USERS:
        log.warning("ALLOWED_USERS пуст — ботом может пользоваться кто угодно и тратить ваш баланс!")
    log.info("Чат: %s (%s), фото: %s, видео: %s", config.AI_PROVIDER, config.CHAT_MODEL,
             config.IMAGE_PROVIDER, "вкл" if config.VIDEO_ENABLED else "выкл")

    app = Application.builder().token(config.TELEGRAM_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("photo", cmd_photo))
    app.add_handler(CommandHandler("video", cmd_video))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CallbackQueryHandler(image_callback, pattern=r"^img:"))
    app.add_handler(CallbackQueryHandler(model_callback, pattern=r"^model:"))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    log.info("Бот запущен. Остановить: Ctrl+C")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
