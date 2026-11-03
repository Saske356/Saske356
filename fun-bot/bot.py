"""Прикольный Telegram-бот: игры, шутки, предсказания и немного магии.

Запуск:
    export BOT_TOKEN="токен_от_BotFather"
    python bot.py
"""

import datetime
import hashlib
import html
import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("fun-bot")

# ---------------------------------------------------------------------------
# Контент
# ---------------------------------------------------------------------------

JOKES = [
    "Программист ставит на тумбочку два стакана: с водой — если захочет пить, "
    "и пустой — если не захочет.",
    "— Почему программисты путают Хэллоуин и Рождество?\n— Потому что 31 OCT = 25 DEC.",
    "Мой код работает, и я понятия не имею почему. Мой код не работает, "
    "и я тоже понятия не имею почему.",
    "Кот смотрит на меня так, будто это я живу у него в квартире. "
    "Что, в общем-то, правда.",
    "Решил начать новую жизнь с понедельника. Понедельник оказался не готов.",
    "— Доктор, я всё время думаю, что я телефон.\n— Ничего, сейчас разберёмся. "
    "Только не садитесь на зарядку посреди приёма.",
    "Будильник — это устройство, которое разбивает сон на «ещё 5 минут».",
    "Если долго смотреть в холодильник, холодильник ничего нового не покажет. "
    "Проверено 47 раз.",
    "Я не ленивый. Я в режиме энергосбережения.",
    "Wi-Fi пропал на 5 минут — и я познакомился со своей семьёй. "
    "Вроде нормальные люди.",
    "— Сколько нужно программистов, чтобы вкрутить лампочку?\n"
    "— Ни одного, это проблема железа.",
    "Диета — это когда ешь то же самое, но с чувством вины.",
]

BALL_ANSWERS = [
    "🟢 Бесспорно!",
    "🟢 Звёзды говорят «да».",
    "🟢 Даже не сомневайся.",
    "🟢 Скорее всего, да.",
    "🟢 Знаки указывают на «да».",
    "🟡 Спроси попозже, я занят.",
    "🟡 Сейчас лучше не говорить…",
    "🟡 Сконцентрируйся и спроси ещё раз.",
    "🟡 Туманно. Как утро понедельника.",
    "🔴 Даже не думай.",
    "🔴 Мой ответ — нет.",
    "🔴 Кот сказал, что нет.",
    "🔴 Весьма сомнительно.",
]

COMPLIMENTS = [
    "Ты как обновление без багов — редкость и радость! ✨",
    "С тобой даже понедельник становится терпимым. 🌞",
    "У тебя отличный вкус — ты же написал(а) именно мне. 😎",
    "Если бы ты был(а) кодом, ты бы компилировался(ась) с первого раза. 💻",
    "Твоя улыбка заряжает лучше, чем 100% батареи. 🔋",
    "Ты — главный персонаж, а не NPC. 🎮",
    "Тебе бы супергеройский плащ — подходит идеально. 🦸",
    "Котики одобряют тебя. Все. Единогласно. 🐱",
]

PREDICTIONS = [
    "Сегодня тебя ждёт неожиданная вкусняшка. 🍩",
    "Сегодня отличный день, чтобы начать что-то новое. 🚀",
    "Кто-то думает о тебе прямо сейчас. 👀",
    "Сегодня удача на твоей стороне — рискни (немножко). 🍀",
    "Не открывай чат, в котором 99+ сообщений. Просто поверь. 🙈",
    "Сегодня ты найдёшь то, что давно потерял(а). 🔎",
    "День котика: будь мягким(ой), но с когтями. 🐾",
    "Тебя ждёт хорошая новость до конца дня. 📬",
    "Сегодня твоя суперсила — убеждение. Используй с умом. 🧠",
    "Лучшее, что можно сделать сегодня, — лечь спать пораньше. 😴",
    "Сегодня ты рассмешишь кого-то до слёз. 😂",
    "Звёзды советуют выпить воды. Звёзды заботятся о тебе. 💧",
]

FACTS = [
    "🐙 У осьминога три сердца и голубая кровь.",
    "🍯 Мёд не портится — его находили съедобным в египетских гробницах.",
    "🐌 Улитка может спать до трёх лет.",
    "🦒 У жирафа столько же шейных позвонков, сколько у человека — семь.",
    "🍌 Банан с ботанической точки зрения — ягода, а клубника — нет.",
    "🐝 Пчёлы умеют узнавать человеческие лица.",
    "⚡ Молния в 5 раз горячее поверхности Солнца.",
    "🦈 Акулы существуют дольше, чем деревья.",
    "🐧 Пингвины дарят друг другу камушки, когда ухаживают.",
    "🌍 На Земле деревьев больше, чем звёзд в Млечном Пути.",
]

RPS = {
    "rock": ("🪨", "Камень"),
    "scissors": ("✂️", "Ножницы"),
    "paper": ("📄", "Бумага"),
}
RPS_BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}

MAIN_MENU = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("😂 Шутка", callback_data="menu:joke"),
            InlineKeyboardButton("🧠 Факт", callback_data="menu:fact"),
        ],
        [
            InlineKeyboardButton("✊ Камень-ножницы", callback_data="menu:rps"),
            InlineKeyboardButton("🔢 Угадай число", callback_data="menu:guess"),
        ],
        [
            InlineKeyboardButton("🔮 Предсказание", callback_data="menu:predict"),
            InlineKeyboardButton("💖 Комплимент", callback_data="menu:compliment"),
        ],
        [
            InlineKeyboardButton("🪙 Монетка", callback_data="menu:coin"),
            InlineKeyboardButton("🎰 Казино", callback_data="menu:casino"),
        ],
    ]
)

HELP_TEXT = (
    "Вот что я умею:\n\n"
    "/menu — меню с кнопками\n"
    "/joke — случайная шутка\n"
    "/fact — интересный факт\n"
    "/ball <вопрос> — магический шар ответит на вопрос\n"
    "/predict — предсказание на сегодня\n"
    "/compliment — комплимент\n"
    "/coin — подбросить монетку\n"
    "/dice — бросить кубик 🎲\n"
    "/casino — однорукий бандит 🎰\n"
    "/rps — камень, ножницы, бумага\n"
    "/guess — игра «угадай число»\n"
    "/choose a или b или c — помогу выбрать\n"
    "/help — эта подсказка"
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def daily_prediction(user_id: int) -> str:
    """Одно и то же предсказание для пользователя в течение дня."""
    today = datetime.date.today().isoformat()
    digest = hashlib.sha256(f"{user_id}:{today}".encode()).hexdigest()
    return PREDICTIONS[int(digest, 16) % len(PREDICTIONS)]


def rps_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{emoji} {name}", callback_data=f"rps:{key}")
                for key, (emoji, name) in RPS.items()
            ]
        ]
    )


def coin_text() -> str:
    if random.randint(1, 100) == 1:
        return "🪙 …монетка встала на ребро! Это знак. Какой — не знаю. 😳"
    return random.choice(["🦅 Орёл!", "🔢 Решка!"])


def start_guess(user_data: dict) -> str:
    user_data["guess_number"] = random.randint(1, 100)
    user_data["guess_tries"] = 0
    return (
        "🔢 Я загадал число от 1 до 100. Попробуй угадать!\n"
        "Просто напиши число в чат."
    )


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"Привет, {name}! 👋\n"
        "Я весёлый бот: шучу, играю, предсказываю будущее (почти точно).\n\n"
        "Выбирай, что хочешь, или жми /help.",
        reply_markup=MAIN_MENU,
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Что будем делать? 😏", reply_markup=MAIN_MENU)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(JOKES))


async def fact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(FACTS))


async def ball(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "🎱 Задай вопрос, например:\n/ball Стоит ли мне съесть ещё пиццу?"
        )
        return
    await update.message.reply_text(f"🎱 {random.choice(BALL_ANSWERS)}")


async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔮 Твоё предсказание на сегодня:\n\n"
        + daily_prediction(update.effective_user.id)
    )


async def compliment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(random.choice(COMPLIMENTS))


async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(coin_text())


async def dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_dice(emoji="🎲")


async def casino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_dice(emoji="🎰")


async def rps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбирай! 👇", reply_markup=rps_keyboard())


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(start_guess(context.user_data))


async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args)
    options = [o.strip() for o in text.replace(",", " или ").split(" или ")]
    options = [o for o in options if o]
    if len(options) < 2:
        await update.message.reply_text(
            "🤔 Дай мне хотя бы два варианта, например:\n"
            "/choose пицца или суши или шаурма"
        )
        return
    await update.message.reply_text(
        f"🤔 Хмм… Я выбираю: <b>{html.escape(random.choice(options))}</b>!",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Кнопки и текст
# ---------------------------------------------------------------------------


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    kind, _, value = query.data.partition(":")
    chat = query.message.chat

    if kind == "menu":
        if value == "joke":
            await chat.send_message(random.choice(JOKES))
        elif value == "fact":
            await chat.send_message(random.choice(FACTS))
        elif value == "rps":
            await chat.send_message("Выбирай! 👇", reply_markup=rps_keyboard())
        elif value == "guess":
            await chat.send_message(start_guess(context.user_data))
        elif value == "predict":
            await chat.send_message(
                "🔮 Твоё предсказание на сегодня:\n\n"
                + daily_prediction(query.from_user.id)
            )
        elif value == "compliment":
            await chat.send_message(random.choice(COMPLIMENTS))
        elif value == "coin":
            await chat.send_message(coin_text())
        elif value == "casino":
            await chat.send_dice(emoji="🎰")
        return

    if kind == "rps" and value in RPS:
        bot_move = random.choice(list(RPS))
        score = context.user_data.setdefault("rps_score", {"you": 0, "bot": 0})
        if value == bot_move:
            result = "🤝 Ничья!"
        elif RPS_BEATS[value] == bot_move:
            result = "🎉 Ты победил(а)!"
            score["you"] += 1
        else:
            result = "😈 Я победил!"
            score["bot"] += 1
        await query.edit_message_text(
            f"Ты: {RPS[value][0]} {RPS[value][1]}\n"
            f"Я: {RPS[bot_move][0]} {RPS[bot_move][1]}\n\n"
            f"{result}\n"
            f"Счёт — ты {score['you']} : {score['bot']} я\n\n"
            "Ещё разок? 👇",
            reply_markup=rps_keyboard(),
        )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    secret = context.user_data.get("guess_number")

    if secret is not None:
        if not text.lstrip("-").isdigit():
            await update.message.reply_text("Напиши число от 1 до 100 🙂")
            return
        number = int(text)
        context.user_data["guess_tries"] += 1
        tries = context.user_data["guess_tries"]
        if number < secret:
            await update.message.reply_text("⬆️ Больше!")
        elif number > secret:
            await update.message.reply_text("⬇️ Меньше!")
        else:
            context.user_data.pop("guess_number")
            await update.message.reply_text(
                f"🎉 Угадал(а)! Это {secret}. Попыток: {tries}.\n"
                "Сыграем ещё? /guess"
            )
        return

    lower = text.lower()
    if any(w in lower for w in ("привет", "здравствуй", "хай", "салют")):
        await update.message.reply_text("Привет-привет! 👋 Жми /menu")
    elif "как дела" in lower:
        await update.message.reply_text(
            "У меня всё отлично, я же бот — у меня не бывает понедельников. 😎"
        )
    elif "спасибо" in lower:
        await update.message.reply_text("Всегда пожалуйста! 💖")
    elif lower.endswith("?"):
        await update.message.reply_text(f"🎱 {random.choice(BALL_ANSWERS)}")
    else:
        await update.message.reply_text(
            random.choice(
                [
                    "Интересно… 🤔 А давай лучше сыграем? /menu",
                    "Я пока не настолько умный, но могу пошутить: /joke",
                    "Записал. Никому не скажу. 🤐",
                    "Ого! А вот тебе факт взамен: " + random.choice(FACTS),
                ]
            )
        )


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Не найден токен! Сначала выполни:\n"
            '  export BOT_TOKEN="токен_от_BotFather"'
        )

    app = Application.builder().token(token).build()

    commands = {
        "start": start,
        "menu": menu,
        "help": help_cmd,
        "joke": joke,
        "fact": fact,
        "ball": ball,
        "predict": predict,
        "compliment": compliment,
        "coin": coin,
        "dice": dice,
        "casino": casino,
        "rps": rps,
        "guess": guess,
        "choose": choose,
    }
    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Бот запущен! Нажми Ctrl+C, чтобы остановить.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
