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
TAGLINE = os.environ.get("TAGLINE", "Приватный доступ к свободному интернету")
SUPPORT = os.environ.get("SUPPORT_USERNAME", "").lstrip("@")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db"))

TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "1"))
REF_BONUS_DAYS = int(os.environ.get("REF_BONUS_DAYS", "3"))
# 1 — бонус сразу, как друг запустил бота по ссылке; 0 — только после его первой оплаты
REF_ON_JOIN = os.environ.get("REF_ON_JOIN", "1") == "1"
REFUND_DAYS = int(os.environ.get("REFUND_DAYS", "3"))

# Преимущества на главной. Пиши только то, что правда про твой сервер.
FEATURES = [
    "Высокая скорость без рекламы",
    "Протокол VLESS Reality",
    "Android, iPhone, Windows и macOS",
    "Без хранения истории посещений",
]

# Адрес мини-приложения (GitHub Pages). Пусто — кнопка приложения не показывается.
MINIAPP_URL = os.environ.get("MINIAPP_URL", "").strip()

# Обновлять ли при запуске имя, описание и меню команд бота
SET_PROFILE = os.environ.get("SET_PROFILE", "1") == "1"

# Тарифы: ключ -> (название, дней, цена в звёздах)
PLANS = {
    "m1": ("Месяц", 30, 99),
    "m3": ("3 месяца", 90, 269),
    "m6": ("Полгода", 180, 499),
    "m12": ("Год", 365, 899),
}

# Устройства в подписке: число -> во сколько раз дороже базовой цены тарифа
DEVICE_OPTIONS = {1: 1.0, 2: 1.5, 3: 2.0, 5: 3.0}

# Автопродление: Telegram Stars умеет списывать оплату раз в 30 дней, поэтому только для тарифа на месяц
AUTO_RENEW = os.environ.get("AUTO_RENEW", "1") == "1"

# Авто-прокси: бот сам берёт бесплатные публичные прокси, добавляет из них страны
# и подменяет прокси при отвале. Управляется в боте командой /autoproxy.
# Эти значения — только стартовые: при первом запуске они попадают в состояние на
# диске, дальше настройка живёт там и меняется командами /autoproxy.
# ВНИМАНИЕ: публичные прокси нестабильны и небезопасны (через них идёт трафик клиентов).
# Это бесплатный запасной вариант, а не замена платным прокси страны. По умолчанию выключено.
AUTO_PROXY = os.environ.get("AUTO_PROXY", "0") == "1"
# Список стран ISO-кодами через запятую (например nl,de,us). Пусто — режим подбора: бот сам
# выберет страны, где сейчас больше всего живых прокси (не больше AUTO_PROXY_MAX).
AUTO_PROXY_COUNTRIES = [c.strip().lower() for c in os.environ.get("AUTO_PROXY_COUNTRIES", "").replace(" ", "").split(",") if c.strip()]
AUTO_PROXY_MAX = int(os.environ.get("AUTO_PROXY_MAX", "8"))

# Новостной канал (например @aurora_news). Бот должен быть в нём админом, чтобы проверять подписку.
CHANNEL = os.environ.get("CHANNEL", "").strip()
CHANNEL_BONUS_DAYS = int(os.environ.get("CHANNEL_BONUS_DAYS", "1"))

# Скрытый тариф для проверки оплаты и возврата. Доступен только админам: /testpay
TEST_PLAN = ("Тестовая оплата", 1, int(os.environ.get("TEST_PLAN_STARS", "5")))


def plan_price(plan_key: str, devices: int) -> int:
    """Цена тарифа с учётом числа устройств."""
    base = TEST_PLAN[2] if plan_key == "test" else PLANS[plan_key][2]
    return max(1, round(base * DEVICE_OPTIONS.get(devices, 1.0)))
