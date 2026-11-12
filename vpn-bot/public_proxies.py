"""Бесплатные публичные прокси из открытых источников: сбор, туннель и проверка.

Проверка прокси настоящая: через него открывается туннель до HTTPS-сайта, проверяется
сертификат (прокси, который подменяет шифрование, не проходит) и читается страна,
из которой сайт видит подключение. Затем проверяется, что прокси пускает и на порт 80. Так отсеиваются мёртвые прокси, «пустышки» без
поддержки туннелей и прокси, которые выходят в интернет не из заявленной страны.
Новые прокси дополнительно проходят замер скорости: медленные и с большой задержкой
отбрасываются, потому что через них VPN «работает через раз».

Публичные прокси нестабильны, и их владельцы видят, к каким адресам идут подключения.
Это бесплатный запасной вариант, а не замена платным прокси.
"""

import asyncio
import base64
import ipaddress
import json
import logging
import random
import re
import socket
import ssl
import time
import urllib.request
from typing import NamedTuple
from urllib.parse import unquote, urlparse

log = logging.getLogger("vpn-bot.pubproxy")

ALLOWED = ("socks5", "http")

SOURCES = [
    ("proxifly", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.json"),
    ("proxyscrape", "https://api.proxyscrape.com/v4/free-proxy-list/get"
                    "?request=display_proxies&proxy_format=protocolipport&format=json"),
    ("geonode", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1"
                "&sort_by=lastChecked&sort_type=desc"),
    # Список, который сам проверяет прокси и пишет страну выхода и время ответа.
    ("monosans", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json"),
]

CACHE_TTL = 900
MAX_PER_COUNTRY = 150
_cache = {"at": 0.0, "pool": {}}

# Сайт для проверки: отвечает текстом со строкой loc=XX — страной, из которой пришли.
CHECK_HOST = "www.cloudflare.com"
CHECK_PORT = 443
CHECK_HTTP_PORT = 80
CHECK_PATH = "/cdn-cgi/trace"
# Замер скорости: скачивание через прокси SPEED_BYTES байт. Медленнее MIN_KBPS — не берём.
SPEED_HOST = "speed.cloudflare.com"
SPEED_PORT = 443
SPEED_PATH = "/__down?bytes={n}"
SPEED_BYTES = 262144
SPEED_TIMEOUT = 12.0
MIN_KBPS = 80          # КБ/с: ниже этого сайты и видео грузятся с перебоями
MAX_MS = 3500          # полная проверка дольше этого — прокси слишком далеко или перегружен
SPEEDS: dict[str, int] = {}   # последний замер скорости прокси, КБ/с
_ssl_ctx: ssl.SSLContext | None = None

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
    "ge": "Грузия", "am": "Армения", "cy": "Кипр", "mt": "Мальта", "cn": "Китай",
}


def flag(cc: str) -> str:
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🏳"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)


def country_name(cc: str) -> str:
    cc = (cc or "").lower()
    return f"{flag(cc)} {RU_NAMES.get(cc, cc.upper())}"


# ---------- сбор списков ----------

def _add(pool: dict, cc, proto, ip, port, uptime=None) -> None:
    """Запоминает прокси с оценкой: чем выше доля успешных проверок у источника и чем больше
    источников его знают, тем раньше мы его попробуем. Так нужно меньше попыток."""
    proto, cc = (proto or "").lower(), (cc or "").lower()
    if proto not in ALLOWED or len(cc) != 2 or not cc.isalpha() or not ip or not str(port).isdigit():
        return
    try:
        quality = min(max(float(uptime or 0), 0.0), 100.0) / 100
    except (TypeError, ValueError):
        quality = 0.0
    urls = pool.setdefault(cc, {})
    url = f"{proto}://{ip}:{int(port)}"
    urls[url] = urls.get(url, 0.0) + 1 + quality


def _parse_proxifly(data, pool) -> None:
    for p in data:
        _add(pool, (p.get("geolocation") or {}).get("country"), p.get("protocol"), p.get("ip"), p.get("port"))


def _parse_proxyscrape(data, pool) -> None:
    for p in data.get("proxies", []):
        if p.get("alive") is False:
            continue
        _add(pool, (p.get("ip_data") or {}).get("countryCode"), p.get("protocol"), p.get("ip"), p.get("port"),
             p.get("uptime"))


def _parse_geonode(data, pool) -> None:
    for p in data.get("data", []):
        for proto in p.get("protocols") or []:
            _add(pool, p.get("country"), proto, p.get("ip"), p.get("port"), p.get("upTime"))


def _parse_monosans(data, pool) -> None:
    for p in data if isinstance(data, list) else []:
        if p.get("username"):
            continue  # прокси с логином из открытого списка нам не подходят
        country = ((p.get("geolocation") or {}).get("country") or {}).get("iso_code")
        try:  # время ответа в секундах при проверке самим списком: быстрые раньше
            quality = max(0.0, 1.0 - float(p.get("timeout") or 5) / 5) * 100
        except (TypeError, ValueError):
            quality = 0.0
        _add(pool, country, p.get("protocol"), p.get("host"), p.get("port"), quality)


PARSERS = {"proxifly": _parse_proxifly, "proxyscrape": _parse_proxyscrape, "geonode": _parse_geonode,
           "monosans": _parse_monosans}


def _fetch_json(url: str, timeout: float = 25.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _collect() -> dict[str, list[str]]:
    pool: dict[str, dict] = {}
    for name, url in SOURCES:
        try:
            PARSERS[name](_fetch_json(url), pool)
        except Exception as e:
            log.warning("источник прокси %s недоступен: %s", name, e)
    out = {}
    for cc, urls in pool.items():
        lst = list(urls)
        random.shuffle(lst)                      # при равной оценке порядок случайный
        lst.sort(key=lambda u: -urls[u])
        out[cc] = lst[:MAX_PER_COUNTRY]
    log.info("публичные прокси: %d стран, %d адресов", len(out), sum(len(v) for v in out.values()))
    return out


async def fetch_pool(force: bool = False) -> dict[str, list[str]]:
    """{код_страны: [url, ...]}. При сбое всех источников возвращает прошлый список."""
    now = time.time()
    if not force and _cache["pool"] and now - _cache["at"] < CACHE_TTL:
        return _cache["pool"]
    pool = await asyncio.to_thread(_collect)
    if pool:
        _cache["pool"], _cache["at"] = pool, now
    return _cache["pool"]


# ---------- туннель через прокси ----------

class ProxyDown(Exception):
    """Сам прокси недоступен, не отвечает или не принял логин."""


class TunnelRefused(Exception):
    """Прокси жив, но не открыл подключение к запрошенному адресу."""


def split_proxy(url: str) -> tuple[str, str, int, str, str]:
    u = urlparse(url.strip())
    scheme = "socks5" if u.scheme in ("socks5", "socks") else u.scheme
    if scheme not in ALLOWED or not u.hostname or not u.port:
        raise ValueError(f"непонятный адрес прокси: {url}")
    return scheme, u.hostname, u.port, unquote(u.username or ""), unquote(u.password or "")


async def _recv_exact(loop, sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = await loop.sock_recv(sock, n - len(buf))
        if not chunk:
            raise ProxyDown("прокси закрыл соединение")
        buf += chunk
    return buf


async def _socks5_greet(loop, sock, user: str, pwd: str) -> None:
    await loop.sock_sendall(sock, b"\x05\x02\x00\x02" if user else b"\x05\x01\x00")
    ver, method = await _recv_exact(loop, sock, 2)
    if ver != 5 or method not in (0, 2) or (method == 2 and not user):
        raise ProxyDown("прокси не говорит по SOCKS5 или требует логин")
    if method == 2:
        u, p = user.encode(), pwd.encode()
        await loop.sock_sendall(sock, b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        if (await _recv_exact(loop, sock, 2))[1] != 0:
            raise ProxyDown("прокси не принял логин")


async def _socks5_connect(loop, sock, host: str, port: int) -> None:
    try:
        ip = ipaddress.ip_address(host)
        addr = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
    except ValueError:
        name = host.encode("idna")
        addr = b"\x03" + bytes([len(name)]) + name
    await loop.sock_sendall(sock, b"\x05\x01\x00" + addr + port.to_bytes(2, "big"))
    rep = await _recv_exact(loop, sock, 4)
    if rep[0] != 5 or rep[1] != 0:
        raise TunnelRefused(f"SOCKS5 отказ {rep[1]}")
    if rep[3] == 1:
        await _recv_exact(loop, sock, 6)
    elif rep[3] == 4:
        await _recv_exact(loop, sock, 18)
    elif rep[3] == 3:
        await _recv_exact(loop, sock, (await _recv_exact(loop, sock, 1))[0] + 2)
    else:
        raise ProxyDown("непонятный ответ SOCKS5")


async def _http_connect(loop, sock, host: str, port: int, user: str, pwd: str) -> None:
    target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    req = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
    if user:
        req += "Proxy-Authorization: Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode() + "\r\n"
    await loop.sock_sendall(sock, (req + "\r\n").encode())
    # Читаем по байту: после заголовков сразу идут данные туннеля, лишнего забирать нельзя.
    buf = b""
    while not buf.endswith(b"\r\n\r\n"):
        if len(buf) > 8192:
            raise ProxyDown("слишком длинный ответ прокси")
        buf += await _recv_exact(loop, sock, 1)
    m = re.match(rb"HTTP/\d\.\d (\d{3})", buf)
    if not m:
        raise ProxyDown("прокси ответил не по HTTP")
    code = int(m.group(1))
    if code == 407:
        raise ProxyDown("прокси не принял логин")
    if code != 200:
        raise TunnelRefused(f"HTTP {code}")


async def open_tunnel(url: str, host: str, port: int, timeout: float = 6.0) -> socket.socket:
    """Открывает через прокси подключение к host:port. Возвращает готовый сокет.
    ProxyDown — виноват прокси, TunnelRefused — прокси жив, но до адреса не дошёл."""
    scheme, phost, pport, user, pwd = split_proxy(url)
    loop = asyncio.get_running_loop()
    sock = None
    try:
        try:
            info = (await asyncio.wait_for(
                loop.getaddrinfo(phost, pport, type=socket.SOCK_STREAM), timeout))[0]
            sock = socket.socket(info[0], socket.SOCK_STREAM)
            sock.setblocking(False)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            await asyncio.wait_for(loop.sock_connect(sock, info[4]), timeout)
            if scheme == "socks5":
                await asyncio.wait_for(_socks5_greet(loop, sock, user, pwd), timeout)
        except (OSError, asyncio.TimeoutError) as e:
            raise ProxyDown(str(e) or "прокси не отвечает") from None
        try:
            step = (_socks5_connect(loop, sock, host, port) if scheme == "socks5"
                    else _http_connect(loop, sock, host, port, user, pwd))
            await asyncio.wait_for(step, timeout * 2)
        except asyncio.TimeoutError:
            raise TunnelRefused("прокси не дождался ответа от адреса") from None
        except OSError as e:
            raise ProxyDown(str(e)) from None
        return sock
    except BaseException:
        if sock is not None:
            sock.close()
        raise


# ---------- проверка ----------

class Probe(NamedTuple):
    country: str  # код страны, из которой прокси выходит в интернет
    ms: int       # время полного запроса через прокси


def _ctx() -> ssl.SSLContext:
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


_TRACE_REQ = (f"GET {CHECK_PATH} HTTP/1.1\r\nHost: {{host}}\r\nUser-Agent: curl/8.5.0\r\n"
              "Accept: */*\r\nConnection: close\r\n\r\n")


async def _read_trace(reader, writer, timeout: float) -> str | None:
    writer.write(_TRACE_REQ.format(host=CHECK_HOST).encode())
    await writer.drain()
    data = b""
    while len(data) < 16384:
        chunk = await asyncio.wait_for(reader.read(4096), timeout)
        if not chunk:
            break
        data += chunk
        if re.search(rb"\nloc=\w+\s", data):
            break
    if not data.startswith(b"HTTP/1.1 200") and not data.startswith(b"HTTP/1.0 200"):
        return None
    m = re.search(rb"\nloc=([A-Za-z0-9]{2})\s", data)
    return m.group(1).decode().lower() if m else None


async def _close(writer) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass


async def _probe(url: str, timeout: float) -> Probe | None:
    t0 = time.monotonic()
    sock = await open_tunnel(url, CHECK_HOST, CHECK_PORT, timeout)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(sock=sock, ssl=_ctx(), server_hostname=CHECK_HOST), timeout)
    except BaseException:
        sock.close()
        raise
    try:
        country = await _read_trace(reader, writer, timeout)
    finally:
        await _close(writer)
    ms = int((time.monotonic() - t0) * 1000)
    if not country or not await _plain_ok(url, timeout):
        return None
    return Probe(country, ms)


async def _plain_ok(url: str, timeout: float) -> bool:
    """Многие HTTP-прокси пускают только на порт 443. Через такой не откроются обычные сайты
    и часть приложений, поэтому прокси должен открывать подключение и на порт 80."""
    sock = await open_tunnel(url, CHECK_HOST, CHECK_HTTP_PORT, timeout)
    try:
        reader, writer = await asyncio.open_connection(sock=sock)
    except BaseException:
        sock.close()
        raise
    try:
        writer.write(f"GET / HTTP/1.1\r\nHost: {CHECK_HOST}\r\nUser-Agent: curl/8.5.0\r\n"
                     "Connection: close\r\n\r\n".encode())
        await writer.drain()
        return (await asyncio.wait_for(reader.readline(), timeout)).startswith(b"HTTP/")
    finally:
        await _close(writer)


async def _speed(url: str, timeout: float) -> int | None:
    sock = await open_tunnel(url, SPEED_HOST, SPEED_PORT, timeout)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(sock=sock, ssl=_ctx(), server_hostname=SPEED_HOST), timeout)
    except BaseException:
        sock.close()
        raise
    try:
        path = SPEED_PATH.format(n=SPEED_BYTES)
        writer.write(f"GET {path} HTTP/1.1\r\nHost: {SPEED_HOST}\r\nUser-Agent: curl/8.5.0\r\n"
                     "Accept: */*\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        if not re.match(rb"HTTP/1\.[01] 200", head):
            return None
        t0, got = time.monotonic(), 0
        while got < SPEED_BYTES:
            chunk = await asyncio.wait_for(reader.read(65536), timeout)
            if not chunk:
                break
            got += len(chunk)
        took = max(time.monotonic() - t0, 0.001)
        return int(got / 1024 / took) if got >= SPEED_BYTES * 0.9 else None
    finally:
        await _close(writer)


async def speed(url: str, timeout: float = 6.0) -> int | None:
    """Скорость скачивания через прокси в КБ/с. None — замер не удался. Никогда не бросает."""
    try:
        kbps = await asyncio.wait_for(_speed(url, timeout), SPEED_TIMEOUT)
    except Exception:
        kbps = None
    if kbps is not None:
        SPEEDS[url] = kbps
    return kbps


async def probe(url: str, timeout: float = 6.0) -> Probe | None:
    """Полная проверка прокси. None — не работает. Никогда не бросает."""
    try:
        return await asyncio.wait_for(_probe(url, timeout), timeout * 4)
    except Exception:
        return None


async def direct_ok(timeout: float = 8.0) -> bool:
    """Доступен ли проверочный сайт с самого сервера. Если нет, выводы о прокси делать нельзя."""
    async def go():
        reader, writer = await asyncio.open_connection(
            CHECK_HOST, CHECK_PORT, ssl=_ctx(), server_hostname=CHECK_HOST)
        try:
            return bool(await _read_trace(reader, writer, timeout))
        finally:
            await _close(writer)
    for _ in range(2):
        try:
            if await asyncio.wait_for(go(), timeout):
                return True
        except Exception:
            pass
    return False


async def pick_working(urls, country: str, need: int = 1, *, timeout: float = 6.0,
                       concurrency: int = 6, tries: int = 12,
                       failed: set | None = None, strays: dict | None = None) -> list[tuple[str, int]]:
    """Ищет среди кандидатов прокси, которые работают и выходят из нужной страны.
    Возвращает до need штук (url, мс), самые быстрые первыми. В failed попадают непрошедшие.
    strays: рабочий и быстрый прокси, который выходит из другой страны (списки часто ошибаются
    со страной), не выбрасывается, а попадает сюда: {страна: [(url, мс), ...]}."""
    urls = list(urls)[:tries]
    if not urls or need < 1:
        return []
    sem = asyncio.Semaphore(concurrency)

    async def check(u):
        async with sem:
            res = await probe(u, timeout)
            # Второе подключение заодно подтверждает, что прокси не случайно ответил один раз.
            if res and res.ms <= MAX_MS and (res.country == country or strays is not None):
                kbps = await speed(u, timeout)
                if kbps is None or kbps < MIN_KBPS:
                    log.info("прокси %s отброшен: скорость %s КБ/с", u, kbps)
                    res = None
            return u, res

    good = []
    tasks = [asyncio.create_task(check(u)) for u in urls]
    try:
        for fut in asyncio.as_completed(tasks):
            u, res = await fut
            if res and res.country == country and res.ms <= MAX_MS:
                good.append((u, res.ms))
                if len(good) > need:  # один запасной, чтобы было из чего выбрать быстрый
                    break
            elif res and res.ms <= MAX_MS and strays is not None:
                strays.setdefault(res.country, []).append((u, res.ms))
            elif failed is not None:
                failed.add(u)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    good.sort(key=lambda x: x[1])
    return good[:need]
