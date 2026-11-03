# 🤖 Прикольный Telegram-бот

Весёлый бот-развлекатель: шутки, факты, игры и предсказания.

## Что умеет

| Команда | Что делает |
|---|---|
| `/start`, `/menu` | Меню с кнопками |
| `/joke` | Случайная шутка 😂 |
| `/fact` | Интересный факт 🧠 |
| `/ball <вопрос>` | Магический шар отвечает на вопрос 🎱 |
| `/predict` | Предсказание на сегодня (одно на день) 🔮 |
| `/compliment` | Комплимент 💖 |
| `/coin` | Подбросить монетку 🪙 |
| `/dice` | Бросить кубик 🎲 |
| `/casino` | Однорукий бандит 🎰 |
| `/rps` | Камень, ножницы, бумага со счётом ✊ |
| `/guess` | Игра «угадай число от 1 до 100» 🔢 |
| `/choose пицца или суши` | Бот выберет за тебя 🤔 |

Ещё бот отвечает на «привет», «как дела», а на любой вопрос со знаком `?` отвечает как магический шар.

## Шаг 1. Получи токен бота

1. Открой в Telegram **@BotFather**.
2. Отправь `/newbot`.
3. Придумай имя и username (он должен заканчиваться на `bot`).
4. BotFather пришлёт **токен**, похожий на `1234567890:AAH...`. Никому его не показывай!

## Шаг 2. Запусти бота на Android (Termux)

1. Установи **Termux** из [F-Droid](https://f-droid.org/packages/com.termux/). Версия из Google Play устарела.
2. Открой Termux и по очереди выполни:

```bash
pkg update -y
pkg install -y python git
git clone https://github.com/saske356/saske356.git
cd saske356/fun-bot
pip install -r requirements.txt
export BOT_TOKEN="СЮДА_ТВОЙ_ТОКЕН"
python bot.py
```

3. Когда появится надпись «Бот запущен!», открой своего бота в Telegram и нажми **Start**.

Бот работает, пока открыт Termux. Чтобы Android не выключал его в фоне, потяни шторку уведомлений и нажми у Termux **Acquire wakelock**.

Чтобы остановить бота, нажми `Ctrl` + `C` (клавиша `CTRL` есть на панели над клавиатурой Termux).

### Повторный запуск

```bash
cd saske356/fun-bot
git pull
export BOT_TOKEN="СЮДА_ТВОЙ_ТОКЕН"
python bot.py
```

## Запуск на компьютере

```bash
pip install -r requirements.txt
export BOT_TOKEN="СЮДА_ТВОЙ_ТОКЕН"   # в Windows: set BOT_TOKEN=СЮДА_ТВОЙ_ТОКЕН
python bot.py
```

## Как добавить свои шутки

Открой `bot.py` и допиши строки в списки `JOKES`, `FACTS`, `PREDICTIONS`, `COMPLIMENTS` или `BALL_ANSWERS`.
