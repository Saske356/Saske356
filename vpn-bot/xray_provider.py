"""Настоящий VPN на Xray: один вход VLESS Reality на 443 и выход через прокси других стран.

Каждый клиент получает отдельный ключ под каждую страну. Сервер по ключу понимает,
через какую страну выпустить трафик: напрямую (страна самого сервера) или через прокси.
Клиенту выдаётся одна ссылка-подписка, в приложении она превращается в список стран.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from urllib.parse import quote, unquote, urlparse

from vpn import VpnProvider

log = logging.getLogger("vpn-bot.xray")

CODE_RE = re.compile(r"^[a-z0-9]{1,8}$")


def parse_proxy(url: str) -> dict:
    """socks5://логин:пароль@хост:порт или http://... -> исходящее подключение Xray."""
    u = urlparse(url.strip())
    if u.scheme not in ("socks5", "socks", "http") or not u.hostname or not u.port:
        raise ValueError("нужен адрес вида socks5://логин:пароль@ip:порт или http://логин:пароль@ip:порт")
    server = {"address": u.hostname, "port": u.port}
    if u.username:
        server["users"] = [{"user": unquote(u.username), "pass": unquote(u.password or "")}]
    return {"protocol": "socks" if u.scheme.startswith("socks") else "http",
            "settings": {"servers": [server]}}


class XrayProvider(VpnProvider):
    is_demo = False

    def __init__(self, *, state_path: str, config_path: str, xray_bin: str, public_host: str,
                 port: int, sni: str, private_key: str, public_key: str, short_id: str,
                 sub_port: int, brand: str = "VPN", default_location: str = "🌍 Основной",
                 restart_cmd: tuple = ("systemctl", "restart", "xray")):
        self.state_path, self.config_path, self.xray_bin = state_path, config_path, xray_bin
        self.host, self.port, self.sni = public_host, port, sni
        self.private_key, self.public_key, self.short_id = private_key, public_key, short_id
        self.sub_port, self.brand, self.restart_cmd = sub_port, brand, restart_cmd
        self.state = self._load(default_location)
        self._pending: asyncio.Task | None = None
        self._server: asyncio.base_events.Server | None = None
        self.on_problem = None      # async-функция(текст): бот подставляет сюда оповещение админов
        self.last_error = ""        # текст последней проблемы, пусто — всё в порядке
        self.last_apply = 0.0       # когда конфиг последний раз успешно применён

    # ---------- состояние ----------

    def _load(self, default_location: str) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        st.setdefault("secret", secrets.token_hex(16))
        st.setdefault("users", {})
        st.setdefault("locations", [{"code": "main", "name": default_location, "proxy": ""}])
        st.setdefault("bridges", [])
        return st

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    @property
    def locations(self) -> list[dict]:
        return self.state["locations"]

    @property
    def bridges(self) -> list[dict]:
        return self.state["bridges"]

    def direct_location(self) -> dict:
        """Страна самого сервера (без прокси): через неё выходит трафик мостов."""
        return next((l for l in self.locations if not l["proxy"]), self.locations[0])

    def user_uuid(self, user_id: int, code: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.state['secret']}:{user_id}:{code}"))

    def sub_token(self, user_id: int) -> str:
        return hmac.new(self.state["secret"].encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[:24]

    def sub_url(self, user_id: int) -> str:
        return f"http://{self.host}:{self.sub_port}/sub/{user_id}/{self.sub_token(user_id)}"

    # ---------- интерфейс для бота ----------

    async def issue(self, user_id: int, expires_at: float) -> str:
        self.state["users"][str(user_id)] = expires_at
        self._save()
        self.schedule_apply()
        return self.sub_url(user_id)

    async def revoke(self, user_id: int) -> None:
        if self.state["users"].pop(str(user_id), None) is not None:
            self._save()
            self.schedule_apply()

    async def sync(self, active: dict[int, float]) -> None:
        """При запуске бота: сервер получает ровно тех, у кого доступ активен."""
        self.state["users"] = {str(k): v for k, v in active.items()}
        self._save()
        await self.apply()

    def add_location(self, code: str, name: str, proxy: str) -> None:
        code = code.lower()
        if not CODE_RE.match(code):
            raise ValueError("код страны: латиница и цифры, до 8 символов, например nl или us2")
        parse_proxy(proxy)  # проверка формата
        self.state["locations"] = [l for l in self.locations if l["code"] != code]
        self.state["locations"].append({"code": code, "name": name.strip(), "proxy": proxy.strip()})
        self._save()
        self.schedule_apply()

    def remove_location(self, code: str) -> bool:
        keep = [l for l in self.locations if l["code"] != code.lower()]
        if len(keep) == len(self.locations) or not keep:
            return False
        self.state["locations"] = keep
        self._save()
        self.schedule_apply()
        return True

    def add_bridge(self, code: str, name: str, address: str, sni: str = "") -> None:
        """Мост: российский сервер, который пересылает порт 443 на этот сервер."""
        code = code.lower()
        if not CODE_RE.match(code):
            raise ValueError("код моста: латиница и цифры, до 8 символов, например ru1")
        host, _, port = address.strip().partition(":")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", host or "") or (port and not port.isdigit()):
            raise ValueError("адрес моста: IP или домен, можно с портом, например 1.2.3.4 или 1.2.3.4:443")
        sni = sni.strip().lower()
        if sni and not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", sni):
            raise ValueError("маскировка: домен сайта, например vk.com")
        self.state["bridges"] = [b for b in self.bridges if b["code"] != code]
        self.state["bridges"].append({"code": code, "name": name.strip(), "host": host,
                                      "port": int(port or 443), "sni": sni})
        self._save()
        self.schedule_apply()  # новый домен маскировки должен попасть в конфиг

    def remove_bridge(self, code: str) -> bool:
        keep = [b for b in self.bridges if b["code"] != code.lower()]
        if len(keep) == len(self.bridges):
            return False
        self.state["bridges"] = keep
        self._save()
        self.schedule_apply()
        return True

    async def check_proxies(self, timeout: float = 6.0) -> list[tuple[dict, bool]]:
        """Проверяет, отвечают ли прокси стран. Нерабочие страны прячутся из подписки.
        Возвращает список изменившихся стран: (страна, работает_ли_теперь)."""
        changes = []
        for loc in self.locations:
            if not loc["proxy"]:
                continue
            ob = parse_proxy(loc["proxy"])["settings"]["servers"][0]
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(ob["address"], ob["port"]), timeout)
                w.close()
                alive = True
            except (OSError, asyncio.TimeoutError):
                alive = False
            if bool(loc.get("down")) == alive:
                loc["down"] = not alive
                changes.append((loc, alive))
        if changes:
            self._save()
        return changes

    # ---------- конфиг Xray ----------

    def _link(self, uid: str, host: str, port: int, sni: str, name: str) -> str:
        q = (f"encryption=none&flow=xtls-rprx-vision&security=reality&sni={sni}"
             f"&fp=chrome&pbk={self.public_key}&sid={self.short_id}&type=tcp")
        return f"vless://{uid}@{host}:{port}?{q}#{quote(name)}"

    def links(self, user_id: int) -> list[str]:
        out = [self._link(self.user_uuid(user_id, loc["code"]), self.host, self.port, self.sni, loc["name"])
               for loc in self.locations if not loc.get("down")]
        direct = self.user_uuid(user_id, self.direct_location()["code"])
        out += [self._link(direct, b["host"], b["port"], b["sni"] or self.sni, b["name"]) for b in self.bridges]
        return out

    def server_names(self) -> list[str]:
        names = [self.sni]
        for b in self.bridges:
            if b["sni"] and b["sni"] not in names:
                names.append(b["sni"])
        return names

    def build_config(self) -> dict:
        now = time.time()
        active = [int(u) for u, exp in self.state["users"].items() if exp > now]
        clients, by_loc = [], {}
        for uid in active:
            for loc in self.locations:
                email = f"u{uid}.{loc['code']}"
                clients.append({"id": self.user_uuid(uid, loc["code"]), "flow": "xtls-rprx-vision",
                                "email": email})
                by_loc.setdefault(loc["code"], []).append(email)

        outbounds = [{"tag": "direct", "protocol": "freedom"},
                     {"tag": "block", "protocol": "blackhole"}]
        rules = [{"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
                 {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}]
        for loc in self.locations:
            if not loc["proxy"]:
                continue
            outbounds.append({"tag": f"out-{loc['code']}", **parse_proxy(loc["proxy"])})
            if by_loc.get(loc["code"]):
                rules.append({"type": "field", "user": by_loc[loc["code"]],
                              "outboundTag": f"out-{loc['code']}"})

        return {
            "log": {"loglevel": "warning", "access": "none"},
            "inbounds": [{
                "tag": "in", "listen": "0.0.0.0", "port": self.port, "protocol": "vless",
                "settings": {"clients": clients, "decryption": "none"},
                "streamSettings": {
                    "network": "tcp", "security": "reality",
                    "realitySettings": {"show": False, "dest": f"{self.sni}:443", "xver": 0,
                                        "serverNames": self.server_names(), "privateKey": self.private_key,
                                        "shortIds": [self.short_id]},
                },
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }],
            "outbounds": outbounds,
            "routing": {"domainStrategy": "AsIs", "rules": rules},
        }

    def schedule_apply(self, delay: float = 2.0) -> None:
        """Несколько изменений подряд применяются одним перезапуском."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._pending = loop.create_task(self._delayed_apply(delay))

    async def _delayed_apply(self, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.apply()

    async def _run(self, *cmd) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return proc.returncode, out.decode(errors="replace")

    async def _problem(self, text: str) -> None:
        """Запоминает проблему и один раз сообщает о ней (повтор той же ошибки не шлём)."""
        log.error(text)
        repeated = text == self.last_error
        self.last_error = text
        if self.on_problem and not repeated:
            try:
                await self.on_problem(text)
            except Exception as e:  # оповещение не должно ронять применение конфига
                log.warning("не удалось сообщить о проблеме: %s", e)

    async def apply(self) -> bool:
        """Пишет новый конфиг, проверяет его самим Xray и только потом перезапускает."""
        cfg = json.dumps(self.build_config(), ensure_ascii=False, indent=1)
        # Xray определяет формат по расширению, поэтому временный файл тоже .json
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".next.json"
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(cfg)
        os.chmod(tmp, 0o644)
        if not os.path.exists(self.xray_bin):
            await self._problem(f"Xray не найден: {self.xray_bin}. Конфиг не применён.")
            return False
        code, out = await self._run(self.xray_bin, "run", "-test", "-c", tmp)
        if code != 0:
            await self._problem("Xray отклонил конфиг, оставляю прежний:\n" + out[-700:].strip())
            return False
        os.replace(tmp, self.config_path)
        code, out = await self._run(*self.restart_cmd)
        if code != 0:
            await self._problem("Не удалось перезапустить Xray: " + out[-500:].strip())
            return False
        self.last_error, self.last_apply = "", time.time()
        log.info("Xray обновлён: %d клиентов, стран: %d", len(self.state["users"]), len(self.locations))
        return True

    # ---------- раздача подписки ----------

    def subscription(self, user_id: int) -> tuple[bytes, dict] | None:
        exp = self.state["users"].get(str(user_id))
        if not exp or exp <= time.time():
            return None
        body = base64.b64encode("\n".join(self.links(user_id)).encode())
        title = base64.b64encode(self.brand.encode()).decode()
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "profile-title": f"base64:{title}",
            "subscription-userinfo": f"upload=0; download=0; total=0; expire={int(exp)}",
            "profile-update-interval": "12",
        }
        return body, headers

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, body, headers = "404 Not Found", b"not found", {"Content-Type": "text/plain"}
        try:
            line = await asyncio.wait_for(reader.readline(), 10)
            for _ in range(50):  # пропускаем заголовки запроса
                h = await asyncio.wait_for(reader.readline(), 10)
                if h in (b"\r\n", b"\n", b""):
                    break
            parts = line.decode(errors="replace").split()
            m = re.fullmatch(r"/sub/(\d+)/([0-9a-f]{24})", parts[1]) if len(parts) >= 2 else None
            if m and parts[0] == "GET" and hmac.compare_digest(m.group(2), self.sub_token(int(m.group(1)))):
                res = self.subscription(int(m.group(1)))
                if res:
                    status, (body, headers) = "200 OK", res
                else:
                    status, body = "403 Forbidden", b"subscription expired"
        except (asyncio.TimeoutError, ConnectionError, UnicodeError):
            pass
        head = f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n"
        head += "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        try:
            writer.write(head.encode() + b"\r\n" + body)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def start_sub_server(self, host: str = "0.0.0.0") -> None:
        self._server = await asyncio.start_server(self._handle, host, self.sub_port)
        log.info("Подписки раздаются на порту %d", self.sub_port)


def from_env() -> XrayProvider:
    e = os.environ
    need = ["PUBLIC_HOST", "REALITY_PRIVATE_KEY", "REALITY_PUBLIC_KEY", "REALITY_SHORT_ID"]
    missing = [k for k in need if not e.get(k)]
    if missing:
        raise SystemExit("Для VPN_MODE=xray не хватает настроек: " + ", ".join(missing))
    return XrayProvider(
        state_path=e.get("VPN_STATE", "/var/lib/aurora/vpn.json"),
        config_path=e.get("XRAY_CONFIG", "/usr/local/etc/xray/config.json"),
        xray_bin=e.get("XRAY_BIN", "/usr/local/bin/xray"),
        public_host=e["PUBLIC_HOST"], port=int(e.get("VPN_PORT", "443")),
        sni=e.get("REALITY_SNI", "www.microsoft.com"),
        private_key=e["REALITY_PRIVATE_KEY"], public_key=e["REALITY_PUBLIC_KEY"],
        short_id=e["REALITY_SHORT_ID"], sub_port=int(e.get("SUB_PORT", "2096")),
        brand=e.get("BRAND", "VPN"), default_location=e.get("DEFAULT_LOCATION_NAME", "🌍 Основной"),
    )
