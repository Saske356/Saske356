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
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))

# Фото: "openrouter" (Nano Banana — топ качество, ~$0.04 за картинку),
#       "pollinations" (бесплатно, качество среднее), "gemini" (ключ Gemini на платном тарифе)
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openrouter" if OPENROUTER_API_KEY else "pollinations")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "google/gemini-2.5-flash-image")
IMAGE_MODEL_GEMINI = os.getenv("IMAGE_MODEL_GEMINI", "gemini-2.5-flash-image")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "flux")
POLLINATIONS_TOKEN = os.getenv("POLLINATIONS_TOKEN", "")  # необязательно: убирает лимиты/логотип

# Видео: Google Veo. Работает только на платном тарифе Gemini API.
VIDEO_ENABLED = _bool("VIDEO_ENABLED", False)
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "veo-3.0-generate-001")

# Через запятую: id пользователей Telegram, которым можно пользоваться ботом.
# Пусто — можно всем (тогда ваш бесплатный лимит могут съесть чужие люди).
ALLOWED_USERS = {int(x) for x in os.getenv("ALLOWED_USERS", "").replace(" ", "").split(",") if x}

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты — дружелюбный и умный ассистент в Telegram. Отвечай на языке пользователя, "
    "по делу и без лишней воды. Не используй сложную Markdown-разметку.",
)
