"""Все настройки бота. Меняются через переменные окружения или файл .env."""

import os


def _load_env_file(path: str = ".env") -> None:
    """Подхватывает переменные из файла .env, если он есть рядом с ботом."""
    here = os.path.dirname(os.path.abspath(__file__))
    full = os.path.join(here, path)
    if not os.path.exists(full):
        return
    with open(full, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
BRAND = os.environ.get("BRAND", "Aurora VPN")
TAGLINE = os.environ.get("TAGLINE", "Свободный интернет без тормозов")
SUPPORT = os.environ.get("SUPPORT_USERNAME", "").lstrip("@")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db"))

TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "1"))
REF_BONUS_DAYS = int(os.environ.get("REF_BONUS_DAYS", "7"))
REFUND_DAYS = int(os.environ.get("REFUND_DAYS", "3"))

# Преимущества на главной. Пиши только то, что правда про твой сервер.
FEATURES = [
    "⚡ Высокая скорость, без рекламы",
    "🔒 Протокол VLESS Reality",
    "📱 Android, iPhone, Windows, macOS",
    "🕶 Не храним историю посещений",
]

# Тарифы: ключ -> (название, дней, цена в звёздах)
PLANS = {
    "m1": ("1 месяц", 30, 99),
    "m3": ("3 месяца", 90, 269),
    "m6": ("6 месяцев", 180, 499),
    "m12": ("12 месяцев", 365, 899),
}
