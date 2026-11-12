"""Купленные прокси списком: Webshare и любые сервисы, которые отдают список по ссылке.

Ссылка на скачивание списка (в Webshare: Proxy List → Download → ссылка) хранится только на
сервере, в vpn.json. Бот скачивает список, проверяет каждый прокси настоящим HTTPS-запросом,
узнаёт страну по тому, откуда прокси выходит в интернет, и в каждой стране оставляет самые
быстрые. Раз в несколько часов проверка повторяется: умерший прокси заменяется живым.

Форматы строк: host:port:логин:пароль, логин:пароль@host:port, host:port, а также полные
адреса socks5://… и http://…. Без схемы считается SOCKS5.
"""

import asyncio
import re
import urllib.request
from urllib.parse import quote, urlparse

import public_proxies as pp

MAX_LIST = 300       # больше строк из списка не берём
CONCURRENCY = 10


def parse(text: str, scheme: str = "socks5") -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "://" in line:
            u = urlparse(line)
            if u.scheme in ("socks5", "socks", "http") and u.hostname and u.port:
                out.append(line)
            continue
        if "@" in line:
            cred, _, addr = line.rpartition("@")
            host, _, port = addr.rpartition(":")
            user, _, pwd = cred.partition(":")
        else:
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, pwd = parts
            elif len(parts) == 2:
                (host, port), user, pwd = parts, "", ""
            else:
                continue
        if not host or not port.isdigit():
            continue
        auth = f"{quote(user, safe='')}:{quote(pwd, safe='')}@" if user else ""
        out.append(f"{scheme}://{auth}{host}:{int(port)}")
    return list(dict.fromkeys(out))[:MAX_LIST]


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


async def fetch(url: str) -> list[str]:
    """Скачивает список. Ошибка сервиса (например, недействительный ключ) — ValueError с его текстом."""
    try:
        text = await asyncio.to_thread(_download, url)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        msg = re.search(r'"message"\s*:\s*"([^"]+)"', body)
        raise ValueError(f"сервис ответил {e.code}: {msg.group(1) if msg else body}") from None
    except OSError as e:
        raise ValueError(f"список не скачался: {e}") from None
    urls = parse(text)
    if not urls:
        raise ValueError("в ответе нет ни одного прокси")
    return urls


async def scan(urls: list[str]) -> list[tuple[str, str, int]]:
    """Проверяет прокси. Возвращает рабочие: (адрес, страна выхода, мс), быстрые первыми."""
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(u):
        async with sem:
            res = await pp.probe(u) or await pp.probe(u)
            return (u, res.country, res.ms) if res else None
    found = [r for r in await asyncio.gather(*(one(u) for u in urls)) if r]
    return sorted(found, key=lambda r: r[2])


def by_country(found: list[tuple[str, str, int]], limit: int = 20) -> dict[str, list[tuple[str, int]]]:
    """Страна -> её прокси, самые быстрые первыми. Стран не больше limit: сначала те, где прокси быстрее."""
    out: dict[str, list[tuple[str, int]]] = {}
    for url, cc, ms in found:
        if len(cc) == 2 and cc.isalpha():
            out.setdefault(cc.lower(), []).append((url, ms))
    best = sorted(out, key=lambda c: out[c][0][1])[:limit]
    return {cc: out[cc] for cc in best}
