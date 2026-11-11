"""Сайты маскировки Reality: проверка с сервера и выбор.

Reality выдаёт VPN-подключение за обращение к обычному сайту. Имя этого сайта видно
в первом пакете, поэтому по нему оператор может обрывать подключения. Сайт должен
отвечать с сервера по TLS 1.3 и HTTP/2 с настоящим сертификатом: без этого Reality
не работает вовсе.
"""

import asyncio
import re
import ssl
import time

# Крупные сайты с TLS 1.3 и HTTP/2. Самых известных в мире (Microsoft, Apple и подобных)
# здесь нет намеренно: их адреса наперечёт, чужой сервер под таким именем заметен сразу,
# и Xray сам предупреждает, что это повышает риск блокировки.
SITES = [
    "www.x-kom.pl", "www.morele.net", "www.ceneo.pl", "www.olx.pl", "allegro.pl", "www.onet.pl",
    "www.wp.pl", "www.interia.pl", "www.empik.com", "www.mediaexpert.pl", "www.nvidia.com",
    "www.amd.com", "www.asus.com", "www.logitech.com", "www.cisco.com", "www.oracle.com",
    "www.sony.com", "www.ikea.com", "www.booking.com", "addons.mozilla.org", "www.speedtest.net",
    "www.lovelive-anime.jp",
]

SITE_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
PORT = 443
_ctx: ssl.SSLContext | None = None


def valid_name(site: str) -> bool:
    return bool(SITE_RE.match(site or ""))


def _context() -> ssl.SSLContext:
    global _ctx
    if _ctx is None:
        _ctx = ssl.create_default_context()
        _ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        _ctx.set_alpn_protocols(["h2", "http/1.1"])
    return _ctx


async def _handshake(host: str, timeout: float) -> float | None:
    t0 = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, PORT, ssl=_context(), server_hostname=host), timeout)
    except Exception:
        return None
    tls = writer.get_extra_info("ssl_object")
    good = tls is not None and tls.version() == "TLSv1.3" and tls.selected_alpn_protocol() == "h2"
    writer.close()
    return (time.monotonic() - t0) * 1000 if good else None


async def check(host: str, timeout: float = 6.0) -> float | None:
    """Подходит ли сайт для маскировки. Возвращает время ответа в мс или None. Не бросает."""
    best = None
    for _ in range(2):
        ms = await _handshake(host, timeout)
        if ms is None:
            return None
        best = ms if best is None else min(best, ms)
    return best


async def ranked(hosts) -> list[tuple[str, float]]:
    """Подходящие сайты из списка, самые быстрые с сервера первыми."""
    hosts = list(dict.fromkeys(hosts))
    sem = asyncio.Semaphore(6)

    async def one(host):
        async with sem:
            return host, await check(host)

    results = await asyncio.gather(*(one(h) for h in hosts))
    return sorted(((h, ms) for h, ms in results if ms is not None), key=lambda r: r[1])


async def tolerates(target: str, name: str, timeout: float = 6.0) -> bool:
    """Отвечает ли сайт target на подключение, в котором назван другой сайт name.
    Если да, после смены сайта маскировки можно ещё сутки принимать ключи с прежним именем."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target, PORT, ssl=ctx, server_hostname=name), timeout)
    except Exception:
        return False
    writer.close()
    return True
