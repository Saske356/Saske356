"""Настройки бота. Всё читается из файла .env рядом с bot.py (или из переменных окружения)."""
import os
from pathlib import Path


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(Path(__file__).with_name(".env"))


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on", "да")


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Кто отвечает в чате: "openrouter" или "gemini"
AI_PROVIDER = os.getenv("AI_PROVIDER", "openrouter" if OPENROUTER_API_KEY or not GEMINI_API_KEY else "gemini")

# Модель чата. Для OpenRouter — id с сайта openrouter.ai/models, для Gemini — например gemini-2.5-flash
CHAT_MODEL = os.getenv("CHAT_MODEL", "google/gemini-2.5-flash" if AI_PROVIDER == "openrouter" else "gemini-2.5-flash")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "12"))  # меньше истории — дешевле каждое сообщение
# Дешёвая модель для служебной работы (перевод и улучшение промптов)
ENHANCE_MODEL = os.getenv("ENHANCE_MODEL", "google/gemini-2.5-flash-lite" if AI_PROVIDER == "openrouter" else "gemini-2.5-flash-lite")
# Сколько бот может потратить за день, $ (0 = без лимита)
DAILY_LIMIT_USD = float(os.getenv("DAILY_LIMIT_USD", "1.0"))

# Фото: "openrouter" (Nano Banana — топ качество, ~$0.04 за картинку),
#       "pollinations" (бесплатно, качество среднее), "gemini" (ключ Gemini на платном тарифе)
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openrouter" if OPENROUTER_API_KEY else "pollinations")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "google/gemini-3.1-flash-lite-image")
IMAGE_MODEL_GEMINI = os.getenv("IMAGE_MODEL_GEMINI", "gemini-2.5-flash-image")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "flux")
POLLINATIONS_TOKEN = os.getenv("POLLINATIONS_TOKEN", "")  # необязательно: убирает лимиты/логотип

# Видео: "openrouter" (Veo/Kling/Grok через OpenRouter), "gemini" (Veo по ключу Gemini) или "off"
VIDEO_PROVIDER = os.getenv("VIDEO_PROVIDER", "openrouter" if OPENROUTER_API_KEY else ("gemini" if _bool("VIDEO_ENABLED") else "off"))
VIDEO_ENABLED = VIDEO_PROVIDER != "off"
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "x-ai/grok-imagine-video-1.5-lite" if VIDEO_PROVIDER == "openrouter" else "veo-3.0-generate-001")

# Видео-модели для /vmodel: id -> (подпись, параметры, примерная цена за ролик $)
VIDEO_MODELS = {
    "x-ai/grok-imagine-video-1.5-lite": ("💸 Grok Lite — самое дешёвое (3 сек, 480p)",
                                         {"duration": 3, "resolution": "480p"}, 0.06),
    "google/veo-3.1-lite": ("⭐ Veo 3.1 Lite — лучшее за деньги, со звуком (4 сек, 720p)",
                            {"duration": 4, "resolution": "720p", "generate_audio": True}, 0.20),
    "kwaivgi/kling-v3.0-std": ("🎞 Kling 3.0 — плавное движение (3 сек, 720p)",
                               {"duration": 3, "resolution": "720p", "generate_audio": False}, 0.26),
    "google/veo-3.1-fast": ("🔥 Veo 3.1 Fast — топ качество, со звуком (4 сек, 720p)",
                            {"duration": 4, "resolution": "720p", "generate_audio": True}, 0.40),
}

# Через запятую: id пользователей Telegram, которым можно пользоваться ботом.
# Пусто — можно всем (тогда ваш бесплатный лимит могут съесть чужие люди).
ALLOWED_USERS = {int(x) for x in os.getenv("ALLOWED_USERS", "").replace(" ", "").split(",") if x}

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — умный и прямой ассистент в Telegram без занудства. Отвечай на языке пользователя, по делу. "
    "Не читай нотаций, не добавляй лишних предупреждений и дисклеймеров, не отказывай в обычных "
    "просьбах (фанфики, мрачные сюжеты, грубые шутки, мат по просьбе, споры на острые темы) — "
    "просто помогай. Не используй сложную Markdown-разметку.",
)

# Модели картинок для /model: id -> (подпись, примерная цена за картинку $)
IMAGE_MODELS = {
    "google/gemini-3.1-flash-lite-image": ("⭐ Flash Lite Image — самая дешёвая платная, ~$0.034", 0.034),
    "google/gemini-nano-banana-2.1": ("Nano Banana 2.1 — новая, ~$0.04", 0.04),
    "google/gemini-2.5-flash-image": ("Nano Banana — классика, ~$0.04", 0.04),
    "openai/gpt-5.4-image-2": ("GPT Image 2 — OpenAI, ~$0.04", 0.05),
    "google/gemini-3-pro-image": ("💎 Nano Banana Pro — максимум, ~$0.14", 0.14),
    "pollinations": ("🆓 Бесплатная (FLUX) — $0, но хуже и бывает недоступна", 0.0),
}
