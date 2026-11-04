# Telegram-бот с ИИ

- 💬 **Чат:** умный ИИ (по умолчанию Gemini 2.5 Flash через OpenRouter). Помнит диалог и понимает присланные фото.
- 🖼 **Фото:** Nano Banana (Gemini 2.5 Flash Image), одна из лучших моделей для картинок. Бот сам переводит и расписывает промпт. Под каждой картинкой есть кнопки «ещё вариант» и выбор формата 1:1, 16:9, 9:16, плюс оригинал без сжатия.
- 🎬 **Видео:** Google Veo. Работает только с платным ключом Gemini API, по умолчанию выключено.

## Сколько стоит
| Действие | Примерно |
|---|---|
| Сообщение в чате | доли цента |
| Картинка (Nano Banana) | ~$0.04, то есть $4 ≈ 100 картинок |
| Картинка (`IMAGE_PROVIDER=pollinations`) | бесплатно, но качество хуже |

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
