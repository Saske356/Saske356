"""Hysteria2: второй, быстрый способ подключения рядом с Xray.

Hysteria2 работает по UDP (QUIC) на том же порту 443, что и Xray по TCP, поэтому они не мешают
друг другу. На плохой мобильной связи с потерями пакетов он заметно быстрее и с меньшим пингом.
Мобильные операторы иногда режут UDP: тогда приложение остаётся на Reality.

Сервер Hysteria (отдельная служба hysteria-server) не хранит список пользователей: при каждом
подключении он спрашивает бота по HTTP на 127.0.0.1, пускать ли этот ключ. Поэтому выдача
и отключение доступа ничего не перезапускают. Трафик, число подключений и отключение
нарушителей берутся из встроенного API статистики Hysteria.

Другие страны: Hysteria выбирает выход по адресу назначения, а не по пользователю, поэтому
у каждой дополнительной страны свой сервер Hysteria на своём UDP-порту (служба
hysteria-loc@код). Он выпускает трафик через прокси этой страны. Ключи у всех общие.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import ssl
from urllib.parse import quote, unquote, urlparse

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
                 stats_secret: str = "", obfs_password: str = "", hop_ports: str = ""):
        self.host, self.port, self.secret = host, port, secret
        self.is_allowed = is_allowed          # функция(sub_id) -> bool: активна ли подписка
        self.cert_path, self.sni = cert_path, sni
        self.auth_port, self.stats_port, self.stats_secret = auth_port, stats_port, stats_secret
        self.obfs_password = obfs_password
        # Смена портов: сервер принимает и на диапазоне UDP-портов (их перенаправляет файрвол),
        # приложение само прыгает между ними. Один порт оператору заблокировать проще.
        self.hop_ports = hop_ports if re.fullmatch(r"\d+-\d+", hop_ports or "") else ""
        self.locs: dict[str, int] = {}    # серверы других стран: код страны -> UDP-порт
        self.extra_ports: range | None = None
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

    def loc_stats_port(self, port: int) -> int:
        """Порт статистики сервера страны: следом за основным, по номеру в диапазоне портов."""
        return self.stats_port + 1 + (port - self.extra_ports.start)

    def stats_ports(self) -> list[int]:
        ports = [self.stats_port]
        if self.extra_ports:
            ports += [self.loc_stats_port(p) for p in sorted(self.locs.values())]
        return ports

    def link(self, sid: int, name: str, port: int | None = None, hop: str = "") -> str:
        q = f"sni={quote(self.sni)}&insecure=1"
        if hop:
            q += f"&mport={hop}"
        if self.pin:
            q += f"&pinSHA256={self.pin}"
        if self.obfs_password:
            q += f"&obfs=salamander&obfs-password={quote(self.obfs_password)}"
        return f"hysteria2://{self.password(sid)}@{self.host}:{port or self.port}/?{q}#{quote(name)}"

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

    async def _api(self, method: str, path: str, body=None, timeout: float = 5.0, port: int | None = None):
        """Запрос к API статистики. None — сервер Hysteria не ответил."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port or self.stats_port), timeout)
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

    async def _all(self, method: str, path: str, body=None) -> list:
        """Тот же запрос ко всем серверам Hysteria: основному и серверам других стран."""
        res = await asyncio.gather(*(self._api(method, path, body, port=p) for p in self.stats_ports()))
        return [r for r in res if isinstance(r, (dict, list))]

    async def traffic(self, clear: bool = True) -> dict[int, tuple[int, int]] | None:
        """Трафик по подпискам с прошлого запроса: {номер: (отдано, получено)}."""
        answers = await self._all("GET", "/traffic?clear=1" if clear else "/traffic")
        if not answers:
            return None
        out: dict[int, tuple[int, int]] = {}
        for res in answers:
            for ident, v in (res.items() if isinstance(res, dict) else []):
                m = ID_RE.match(str(ident))
                if m and isinstance(v, dict):
                    up, down = out.get(int(m.group(1)), (0, 0))
                    out[int(m.group(1))] = (up + int(v.get("tx") or 0), down + int(v.get("rx") or 0))
        return out

    async def online(self) -> dict[int, int] | None:
        """Сколько подключений сейчас у каждой подписки: обычно одно на устройство."""
        answers = await self._all("GET", "/online")
        if not answers:
            return None
        out: dict[int, int] = {}
        for res in answers:
            for ident, n in (res.items() if isinstance(res, dict) else []):
                m = ID_RE.match(str(ident))
                if m:
                    out[int(m.group(1))] = out.get(int(m.group(1)), 0) + int(n or 0)
        return out

    async def kick(self, sids) -> bool:
        ids = [f"u{s}" for s in sids]
        if not ids:
            return True
        return bool(await self._all("POST", "/kick", ids))

    # ---------- серверы других стран ----------

    def location_config(self, port: int, proxy: str, relay: tuple[int, str, str] | None = None) -> str:
        """Конфиг сервера Hysteria для страны. relay: (порт, логин, пароль) ретранслятора авто-стран,
        иначе трафик идёт через купленный прокси proxy."""
        q = json.dumps
        if relay:
            out = ["  - name: out", "    type: socks5", "    socks5:",
                   f"      addr: {q(f'127.0.0.1:{relay[0]}')}",
                   f"      username: {q(relay[1])}", f"      password: {q(relay[2])}"]
            udp_ok = False  # ретранслятор и публичные прокси UDP не пересылают
        else:
            u = urlparse(proxy.strip())
            if u.scheme in ("socks5", "socks"):
                out = ["  - name: out", "    type: socks5", "    socks5:",
                       f"      addr: {q(f'{u.hostname}:{u.port}')}"]
                if u.username:
                    out += [f"      username: {q(unquote(u.username))}",
                            f"      password: {q(unquote(u.password or ''))}"]
                udp_ok = True
            else:
                out = ["  - name: out", "    type: http", "    http:", f"      url: {q(proxy.strip())}"]
                udp_ok = False  # HTTP-прокси UDP не умеет
        acl = ["reject(10.0.0.0/8)", "reject(172.16.0.0/12)", "reject(192.168.0.0/16)",
               "reject(127.0.0.0/8)", "reject(169.254.0.0/16)"]
        if not udp_ok:
            # Запросы DNS уходят с сервера, остальной UDP отклоняется: приложения переходят на TCP.
            acl += ["direct(all, udp/53)", "reject(all, udp)"]
        acl += ["out(all)"]
        lines = [
            "# Создано ботом Aurora VPN: сервер Hysteria2 для одной страны. Не правьте вручную.",
            f"listen: :{port}",
            "tls:", f"  cert: {q(self.cert_path)}", f"  key: {q(self.cert_path[:-4] + '.key')}",
            "  sniGuard: disable",
            "auth:", "  type: http", "  http:", f"    url: {q(f'http://127.0.0.1:{self.auth_port}/auth')}",
            "masquerade:", "  type: proxy", "  proxy:", f"    url: {q(f'https://{self.sni}/')}",
            "    rewriteHost: true",
            "trafficStats:", f"  listen: {q(f'127.0.0.1:{self.loc_stats_port(port)}')}",
            f"  secret: {q(self.stats_secret)}",
            "outbounds:", *out, "  - name: direct", "    type: direct",
            "acl:", "  inline:", *[f"    - {q(r)}" for r in acl],
        ]
        if self.obfs_password:
            lines += ["obfs:", "  type: salamander", "  salamander:", f"    password: {q(self.obfs_password)}"]
        return "\n".join(lines) + "\n"


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
