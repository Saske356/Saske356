"""Бесплатные публичные прокси из открытых источников.

Качает списки прокси с нескольких открытых источников, группирует по странам
и умеет проверять, что прокси реально пропускает трафик (а не просто принимает
соединение). Этим пользуется авто-режим в боте: он сам добавляет страны из
публичных прокси и подменяет упавший прокси на живой.

Важно: публичные прокси нестабильны и небезопасны — через них идёт трафик
клиентов. Это запасной/бесплатный вариант, а не замена платным прокси страны.
Поэтому авто-режим по умолчанию выключен (AUTO_PROXY=0).
"""

import asyncio
import json
import logging
import random
import time
import urllib.request
from urllib.parse import urlparse

log = logging.getLogger("vpn-bot.pubproxy")

# Xray-выход умеет socks5 и http, поэтому берём только их (socks4/https пропускаем).
ALLOWED = ("socks5", "http")

# Открытые источники. Каждый парсер устойчив к сбоям: если источник недоступен
# или сменил формат, он просто пропускается, а остальные работают.
SOURCES = [
    ("proxifly", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"),
    ("proxyscrape", "https://api.proxyscrape.com/v4/free-proxy-list/get"
                    "?request=display_proxies&proxy_format=protocolipport&format=json"),
    ("geonode", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1"
                "&sort_by=lastChecked&sort_type=desc"),
]

CACHE_TTL = 300          # секунд: как часто реально ходим за списками
MAX_PER_COUNTRY = 120    # сколько кандидатов на страну держим в пуле
_cache = {"at": 0.0, "pool": {}}

RU_NAMES = {
    "us": "США", "gb": "Британия", "uk": "Британия", "de": "Германия", "nl": "Нидерланды",
    "fr": "Франция", "ca": "Канада", "jp": "Япония", "sg": "Сингапур", "fi": "Финляндия",
    "se": "Швеция", "no": "Норвегия", "pl": "Польша", "es": "Испания", "it": "Италия",
    "ch": "Швейцария", "at": "Австрия", "be": "Бельгия", "ie": "Ирландия", "pt": "Португалия",
    "cz": "Чехия", "ro": "Румыния", "hu": "Венгрия", "gr": "Греция", "dk": "Дания",
    "bg": "Болгария", "sk": "Словакия", "ua": "Украина", "tr": "Турция", "in": "Индия",
    "id": "Индонезия", "br": "Бразилия", "mx": "Мексика", "ar": "Аргентина", "cl": "Чили",
    "co": "Колумбия", "au": "Австралия", "nz": "Новая Зеландия", "kr": "Корея", "hk": "Гонконг",
    "tw": "Тайвань", "th": "Таиланд", "vn": "Вьетнам", "my": "Малайзия", "ph": "Филиппины",
    "za": "ЮАР", "ae": "ОАЭ", "il": "Израиль", "kz": "Казахстан", "md": "Молдова",
    "lv": "Латвия", "lt": "Литва", "ee": "Эстония", "rs": "Сербия", "hr": "Хорватия",
    "si": "Словения", "is": "Исландия", "lu": "Люксембург", "ec": "Эквадор", "pe": "Перу",
    "bd": "Бангладеш", "pk": "Пакистан", "eg": "Египет", "ng": "Нигерия", "ru": "Россия",
}


def flag(cc: str) -> str:
    """Эмодзи-флаг из ISO-кода страны (nl -> 🇳🇱)."""
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🏳"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)


def country_name(cc: str) -> str:
    """Название страны для подписки: «🇳🇱 Нидерланды» (для неизвестных — код)."""
    cc = (cc or "").lower()
    return f"{flag(cc)} {RU_NAMES.get(cc, cc.upper())}"


def _valid(cc, ip, port) -> bool:
    return (isinstance(cc, str) and len(cc) == 2 and cc.isalpha()
            and bool(ip) and bool(port) and str(port).isdigit())


def _add(pool: dict, cc, proto, ip, port) -> None:
    proto = (proto or "").lower()
    cc = (cc or "").lower()
    if proto not in ALLOWED or not _valid(cc, ip, port):
        return
    pool.setdefault(cc, set()).add(f"{proto}://{ip}:{int(port)}")


def _parse_proxifly(data, pool) -> None:
    for p in data:
        geo = p.get("geolocation") or {}
        _add(pool, geo.get("country"), p.get("protocol"), p.get("ip"), p.get("port"))


def _parse_proxyscrape(data, pool) -> None:
    for p in data.get("proxies", []):
        _add(pool, (p.get("ip_data") or {}).get("countryCode"),
             p.get("protocol"), p.get("ip"), p.get("port"))


def _parse_geonode(data, pool) -> None:
    for p in data.get("data", []):
        for proto in p.get("protocols") or []:
            _add(pool, p.get("country"), proto, p.get("ip"), p.get("port"))


PARSERS = {"proxifly": _parse_proxifly, "proxyscrape": _parse_proxyscrape, "geonode": _parse_geonode}


def _fetch_json(url: str, timeout: float = 25.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (vpn-bot)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _collect() -> dict[str, list[str]]:
    """Качает все источники и собирает {код_страны: [url прокси, ...]}. Блокирующая."""
    pool: dict[str, set] = {}
    for name, url in SOURCES:
        try:
            data = _fetch_json(url)
            PARSERS[name](data, pool)
        except Exception as e:  # источник недоступен или сменил формат — не роняем остальные
            log.warning("источник прокси %s недоступен: %s", name, e)
    out = {}
    for cc, urls in pool.items():
        lst = list(urls)
        random.shuffle(lst)
        out[cc] = lst[:MAX_PER_COUNTRY]
    log.info("публичные прокси: %d стран, всего %d адресов",
             len(out), sum(len(v) for v in out.values()))
    return out


async def fetch_pool(force: bool = False) -> dict[str, list[str]]:
    """{код_страны: [url, ...]} из всех источников. Кэшируется на CACHE_TTL секунд."""
    now = time.time()
    if not force and _cache["pool"] and now - _cache["at"] < CACHE_TTL:
        return _cache["pool"]
    pool = await asyncio.to_thread(_collect)
    if pool:
        _cache["pool"], _cache["at"] = pool, now
    return _cache["pool"]


# ---------- проверка, что прокси реально работает ----------
# Через прокси ходим на http://www.gstatic.com/generate_204 — он отвечает 204 без тела.
# Это ловит и мёртвые прокси, и «пустышки», которые принимают соединение, но не пересылают.

_CHK_HOST = b"www.gstatic.com"
_CHK_REQ = (b"GET /generate_204 HTTP/1.1\r\nHost: www.gstatic.com\r\n"
            b"User-Agent: curl/8\r\nConnection: close\r\n\r\n")


async def _close(writer) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


async def _read_status_ok(reader, timeout) -> bool:
    line = await asyncio.wait_for(reader.readline(), timeout)
    return b" 204" in line or b" 200" in line


async def _check_socks5(host, port, timeout) -> bool:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    try:
        writer.write(b"\x05\x01\x00")              # greeting: без аутентификации
        await writer.drain()
        if await asyncio.wait_for(reader.readexactly(2), timeout) != b"\x05\x00":
            return False
        req = b"\x05\x01\x00\x03" + bytes([len(_CHK_HOST)]) + _CHK_HOST + (80).to_bytes(2, "big")
        writer.write(req)                           # CONNECT www.gstatic.com:80
        await writer.drain()
        rep = await asyncio.wait_for(reader.readexactly(4), timeout)
        if rep[1] != 0x00:                          # 0 — успех
            return False
        atyp = rep[3]
        if atyp == 0x01:
            await asyncio.wait_for(reader.readexactly(4 + 2), timeout)
        elif atyp == 0x04:
            await asyncio.wait_for(reader.readexactly(16 + 2), timeout)
        elif atyp == 0x03:
            ln = await asyncio.wait_for(reader.readexactly(1), timeout)
            await asyncio.wait_for(reader.readexactly(ln[0] + 2), timeout)
        writer.write(_CHK_REQ)
        await writer.drain()
        return await _read_status_ok(reader, timeout)
    finally:
        await _close(writer)


async def _check_http(host, port, timeout) -> bool:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    try:
        writer.write(b"GET http://www.gstatic.com/generate_204 HTTP/1.1\r\n"
                     b"Host: www.gstatic.com\r\nUser-Agent: curl/8\r\n"
                     b"Proxy-Connection: close\r\nConnection: close\r\n\r\n")
        await writer.drain()
        return await _read_status_ok(reader, timeout)
    finally:
        await _close(writer)


async def validate(url: str, timeout: float = 6.0) -> bool:
    """True, если прокси доступен и пропускает HTTP-трафик. Никогда не бросает."""
    try:
        u = urlparse(url)
        if not u.hostname or not u.port:
            return False
        if u.scheme == "socks5":
            return await asyncio.wait_for(_check_socks5(u.hostname, u.port, timeout), timeout * 3)
        if u.scheme == "http":
            return await asyncio.wait_for(_check_http(u.hostname, u.port, timeout), timeout * 2)
        return False
    except Exception:
        return False


async def first_working(urls, timeout: float = 6.0, concurrency: int = 20, tries: int = 50) -> str | None:
    """Проверяет кандидатов (параллельно, с ограничением) и возвращает первый рабочий."""
    urls = list(urls)[:tries]
    if not urls:
        return None
    sem = asyncio.Semaphore(concurrency)

    async def check(u):
        async with sem:
            return u if await validate(u, timeout) else None

    tasks = [asyncio.create_task(check(u)) for u in urls]
    try:
        for fut in asyncio.as_completed(tasks):
            res = await fut
            if res:
                return res
        return None
    finally:
        for t in tasks:
            t.cancel()
