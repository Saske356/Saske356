# Telegram-бот с ИИ

- 💬 **Чат:** умный ИИ (по умолчанию Gemini 2.5 Flash через OpenRouter). Помнит диалог и понимает присланные фото.
- 🖼 **Фото:** Nano Banana (Gemini 2.5 Flash Image), одна из лучших моделей для картинок. Бот сам переводит и расписывает промпт. Под каждой картинкой есть кнопки «ещё вариант» и выбор формата 1:1, 16:9, 9:16, плюс оригинал без сжатия.
- 🎬 **Видео:** через OpenRouter: Grok Lite, Veo 3.1 Lite, Kling 3.0, Veo 3.1 Fast. Модель меняется командой `/vmodel`. Перед генерацией бот показывает цену и ждёт подтверждения.
- 💰 **Экономия:** промпты улучшает дешёвая модель, кнопка «ещё вариант» не тратит запрос на повторное улучшение, история диалога ограничена. Есть дневной лимит трат (`DAILY_LIMIT_USD`, по умолчанию $1) и кнопка «Баланс».

## Сколько стоит
| Действие | Примерно |
|---|---|
| Сообщение в чате | доли цента |
| Картинка (Nano Banana) | ~$0.04, то есть $4 ≈ 100 картинок |
| Картинка (Nano Banana Pro) | ~$0.14 |
| Картинка (бесплатная FLUX в /model) | $0 |
| Видео Grok Lite, 3 сек 480p | ~$0.06 |
| Видео Veo 3.1 Lite, 4 сек 720p со звуком | ~$0.20 |
| Видео Veo 3.1 Fast, 4 сек 720p со звуком | ~$0.40 |

Точные цены смотрите на openrouter.ai/models.

## Ключи
1. **Telegram:** напишите [@BotFather](https://t.me/BotFather) команду `/newbot` и скопируйте токен.
2. **OpenRouter:** создайте ключ на [openrouter.ai/keys](https://openrouter.ai/keys) кнопкой Create Key. Можно поставить лимит трат, например $3.

## Запуск в Termux
```bash
pkg install -y python git
git clone -b claude/termux-setup-0ulp7o https://github.com/saske356/saske356
cd saske356/ai-bot
pip install -r requirements.txt
cp .env.example .env
nano .env        # вставить ключи, Ctrl+O, Enter, Ctrl+X
python bot.py
```
Потом напишите боту `/id` и впишите свой id в `ALLOWED_USERS` в `.env`. Без этого чужие люди смогут тратить ваш баланс. После этого перезапустите бота: Ctrl+C, затем `python bot.py`.

Бот работает, пока открыт Termux. Чтобы Android его не усыплял: `termux-wake-lock`.

⚠️ Файл `.env` никому не показывайте и не загружайте в GitHub (он уже в `.gitignore`).
