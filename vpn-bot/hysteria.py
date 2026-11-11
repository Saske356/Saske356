"""Hysteria2: второй, быстрый способ подключения рядом с Xray.

Hysteria2 работает по UDP (QUIC) на том же порту 443, что и Xray по TCP, поэтому они не мешают
друг другу. На плохой мобильной связи с потерями пакетов он заметно быстрее и с меньшим пингом.
Мобильные операторы иногда режут UDP: тогда приложение остаётся на Reality.

Сервер Hysteria (отдельная служба hysteria-server) не хранит список пользователей: при каждом
подключении он спрашивает бота по HTTP на 127.0.0.1, пускать ли этот ключ. Поэтому выдача
и отключение доступа ничего не перезапускают. Трафик, число подключений и отключение
нарушителей берутся из встроенного API статистики Hysteria.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import ssl
from urllib.parse import quote

log = logging.getLogger("vpn-bot.hy2")

ID_RE = re.compile(r"^u(\d+)$")


def cert_pin(path: str) -> str:
    """SHA-256 сертификата сервера: клиент сверяет его вместо проверки через центр сертификации."""
    try:
        with open(path, encoding="ascii") as f:
            der = ssl.PEM_cert_to_DER_cert(f.read())
    except (OSError, ValueError):
        return ""
    return hashlib.sha256(der).hexdigest()


class Hysteria:
    def __init__(self, *, host: str, port: int, secret: str, is_allowed, cert_path: str = "",
                 sni: str = "", auth_port: int = 20809, stats_port: int = 20810,
                 stats_secret: str = "", obfs_password: str = ""):
        self.host, self.port, self.secret = host, port, secret
        self.is_allowed = is_allowed          # функция(sub_id) -> bool: активна ли подписка
        self.cert_path, self.sni = cert_path, sni
        self.auth_port, self.stats_port, self.stats_secret = auth_port, stats_port, stats_secret
        self.obfs_password = obfs_password
        self._pin: str | None = None
        self._server: asyncio.base_events.Server | None = None

    # ---------- ключи ----------

    def password(self, sid: int) -> str:
        """Пароль клиента: номер подписки и подпись. Без двоеточия: в ссылке оно делит логин и пароль."""
        sig = hmac.new(self.secret.encode(), f"hy2:{sid}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"{sid}.{sig}"

    def check(self, auth: str) -> int | None:
        sid, _, sig = (auth or "").partition(".")
        if not sid.isdigit() or not sig:
            return None
        if not hmac.compare_digest(self.password(int(sid)).encode(), auth.encode()):
            return None
        return int(sid)

    @property
    def pin(self) -> str:
        if self._pin is None:
            self._pin = cert_pin(self.cert_path) if self.cert_path else ""
        return self._pin

    def link(self, sid: int, name: str) -> str:
        q = f"sni={quote(self.sni)}&insecure=1"
        if self.pin:
            q += f"&pinSHA256={self.pin}"
        if self.obfs_password:
            q += f"&obfs=salamander&obfs-password={quote(self.obfs_password)}"
        return f"hysteria2://{self.password(sid)}@{self.host}:{self.port}/?{q}#{quote(name)}"

    # ---------- проверка ключа по запросу сервера Hysteria ----------

    async def _handle_auth(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        ok, ident = False, ""
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
            length = 0
            for _ in range(50):
                h = await asyncio.wait_for(reader.readline(), 5)
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode(errors="replace").partition(":")
                if k.strip().lower() == "content-length" and v.strip().isdigit():
                    length = min(int(v.strip()), 8192)
            if line.split()[:1] == [b"POST"] and length:
                body = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
                sid = self.check(str(body.get("auth", "")))
                if sid is not None and self.is_allowed(sid):
                    ok, ident = True, f"u{sid}"
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, ValueError,
                UnicodeError, AttributeError):
            pass
        except Exception:
            log.exception("hysteria: ошибка проверки ключа")
        data = json.dumps({"ok": ok, "id": ident}).encode()
        try:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                         + f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def start_auth(self) -> bool:
        try:
            self._server = await asyncio.start_server(self._handle_auth, "127.0.0.1", self.auth_port)
        except OSError as e:
            log.error("Проверка ключей Hysteria не запустилась на порту %d: %s", self.auth_port, e)
            return False
        if not self.auth_port:
            self.auth_port = self._server.sockets[0].getsockname()[1]
        log.info("Hysteria2: ключи проверяются на 127.0.0.1:%d", self.auth_port)
        return True

    # ---------- API статистики сервера Hysteria ----------

    async def _api(self, method: str, path: str, body=None, timeout: float = 5.0):
        """Запрос к API статистики. None — сервер Hysteria не ответил."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.stats_port), timeout)
        except (OSError, asyncio.TimeoutError):
            return None
        try:
            data = json.dumps(body).encode() if body is not None else b""
            head = (f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n"
                    f"Authorization: {self.stats_secret}\r\nContent-Length: {len(data)}\r\n")
            if body is not None:
                head += "Content-Type: application/json\r\n"
            writer.write(head.encode() + b"\r\n" + data)
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(), timeout)
        except (OSError, asyncio.TimeoutError):
            return None
        finally:
            writer.close()
        head, _, payload = raw.partition(b"\r\n\r\n")
        if not head.startswith(b"HTTP/1.1 200") and not head.startswith(b"HTTP/1.0 200"):
            return None
        if b"chunked" in head.lower():
            payload = _dechunk(payload)
        try:
            return json.loads(payload) if payload.strip() else {}
        except ValueError:
            return None

    async def traffic(self, clear: bool = True) -> dict[int, tuple[int, int]] | None:
        """Трафик по подпискам с прошлого запроса: {номер: (отдано, получено)}."""
        res = await self._api("GET", "/traffic?clear=1" if clear else "/traffic")
        if not isinstance(res, dict):
            return None
        out = {}
        for ident, v in res.items():
            m = ID_RE.match(str(ident))
            if m and isinstance(v, dict):
                out[int(m.group(1))] = (int(v.get("tx") or 0), int(v.get("rx") or 0))
        return out

    async def online(self) -> dict[int, int] | None:
        """Сколько подключений сейчас у каждой подписки: обычно одно на устройство."""
        res = await self._api("GET", "/online")
        if not isinstance(res, dict):
            return None
        out = {}
        for ident, n in res.items():
            m = ID_RE.match(str(ident))
            if m:
                out[int(m.group(1))] = int(n or 0)
        return out

    async def kick(self, sids) -> bool:
        ids = [f"u{s}" for s in sids]
        if not ids:
            return True
        return await self._api("POST", "/kick", ids) is not None


def _dechunk(data: bytes) -> bytes:
    out = b""
    while data:
        size, _, rest = data.partition(b"\r\n")
        try:
            n = int(size.split(b";")[0], 16)
        except ValueError:
            break
        if n == 0:
            break
        out += rest[:n]
        data = rest[n + 2:]
    return out
