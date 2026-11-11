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

import public_proxies
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
                 restart_cmd: tuple = ("systemctl", "restart", "xray"),
                 auto_enabled: bool = False, auto_countries: tuple = (), auto_max: int = 8,
                 relay_port: int = 20808):
        self.state_path, self.config_path, self.xray_bin = state_path, config_path, xray_bin
        self.host, self.port, self.env_sni = public_host, port, sni
        self.private_key, self.public_key, self.short_id = private_key, public_key, short_id
        self.sub_port, self.brand, self.restart_cmd = sub_port, brand, restart_cmd
        self.relay_port = relay_port
        self.state = self._load(default_location, auto_enabled, list(auto_countries), auto_max)
        self._pending: asyncio.Task | None = None
        self._server: asyncio.base_events.Server | None = None
        self.on_problem = None      # async-функция(текст): бот подставляет сюда оповещение админов
        self.last_error = ""        # текст последней проблемы, пусто — всё в порядке
        self.last_apply = 0.0       # когда конфиг последний раз успешно применён
        self.auto_rejected = False  # Xray принял конфиг только без авто-стран

    # ---------- состояние ----------

    def _load(self, default_location: str, auto_enabled: bool, auto_countries: list, auto_max: int) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        st.setdefault("secret", secrets.token_hex(16))
        st.setdefault("users", {})
        st.setdefault("locations", [{"code": "main", "name": default_location, "proxy": ""}])
        st.setdefault("bridges", [])
        # Настройки авто-стран берутся из окружения только при первом запуске,
        # дальше ими управляет команда /autoproxy.
        st.setdefault("auto", {"enabled": bool(auto_enabled),
                               "countries": [c.lower() for c in auto_countries],
                               "max": int(auto_max)})
        st["auto"].setdefault("notify", True)
        st["auto"].setdefault("exclude", [])
        # Сайт маскировки: пока его не меняли из бота, действует значение из .env.
        m = st.setdefault("masking", {})
        for key, value in (("site", ""), ("prev", []), ("auto", True), ("every", 0), ("changed", 0)):
            m.setdefault(key, value)
        for loc in st["locations"]:
            if loc.get("auto"):
                loc.setdefault("country", loc["code"])
                loc.setdefault("pool", [loc["proxy"]] if loc.get("proxy") else [])
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

    # ---------- авто-страны: публичные прокси ----------

    @property
    def auto(self) -> dict:
        return self.state["auto"]

    @property
    def relay_password(self) -> str:
        return hmac.new(self.state["secret"].encode(), b"relay", hashlib.sha256).hexdigest()[:24]

    def set_auto(self, *, enabled=None, countries=None, max=None, notify=None, exclude=None) -> None:
        if exclude is not None:
            self.auto["exclude"] = [str(c).lower() for c in exclude]
        if enabled is not None:
            self.auto["enabled"] = bool(enabled)
        if countries is not None:
            self.auto["countries"] = [str(c).lower() for c in countries]
        if max is not None:
            self.auto["max"] = int(max)
        if notify is not None:
            self.auto["notify"] = bool(notify)
        self._save()

    def auto_locations(self) -> list[dict]:
        return [l for l in self.locations if l.get("auto")]

    def manual_codes(self) -> set:
        return {l["code"] for l in self.locations if not l.get("auto")}

    def set_auto_location(self, code: str, name: str, pool: list[str], ms: int | None = None,
                          apply: bool = True) -> str:
        """Задаёт авто-стране список прокси: первый рабочий, остальные запасные.
        Возвращает "added", "swapped", "kept" или "" (код занят страной, добавленной вручную).
        Xray перезапускается только при появлении новой страны: смена прокси идёт через ретранслятор."""
        code = code.lower()
        if not CODE_RE.match(code):
            raise ValueError("код страны: латиница и цифры, до 8 символов")
        if not pool:
            raise ValueError("нужен хотя бы один прокси")
        for url in pool:
            public_proxies.split_proxy(url)
        loc = next((l for l in self.locations if l["code"] == code), None)
        if loc and not loc.get("auto"):
            return ""
        if loc is None:
            self.state["locations"].append({
                "code": code, "name": name.strip(), "proxy": pool[0], "auto": True, "country": code,
                "pool": list(pool), "down": False, "since": time.time(), "swaps": 0, "ms": ms})
            self._save()
            if apply:
                self.schedule_apply()
            return "added"
        result = "kept"
        if loc["proxy"] != pool[0]:
            loc["swaps"] = loc.get("swaps", 0) + 1
            loc["since"] = time.time()
            result = "swapped"
        loc.update(proxy=pool[0], pool=list(pool), down=False, ms=ms)
        loc.pop("down_since", None)
        self._save()
        return result

    def rotate_auto_upstream(self, code: str, url: str) -> list[str]:
        """Прокси перестал отвечать: он уходит в конец списка, рабочим становится следующий."""
        loc = next((l for l in self.auto_locations() if l["code"] == code), None)
        if not loc:
            return []
        pool = loc.setdefault("pool", [])
        if url in pool and len(pool) > 1:
            pool.remove(url)
            pool.append(url)
            if loc["proxy"] != pool[0]:
                loc.update(proxy=pool[0], since=time.time(), ms=None, swaps=loc.get("swaps", 0) + 1)
            self._save()
        return list(pool)

    def set_auto_down(self, code: str, down: bool) -> None:
        for loc in self.auto_locations():
            if loc["code"] == code and bool(loc.get("down")) != down:
                loc["down"] = down
                if down:
                    loc["down_since"] = time.time()
                else:
                    loc.pop("down_since", None)
                self._save()

    def clear_auto_locations(self) -> int:
        """Удаляет все авто-страны. Страны, добавленные вручную, и мосты остаются."""
        n = len(self.auto_locations())
        if not n:
            return 0
        self.state["locations"] = [l for l in self.locations if not l.get("auto")]
        if not self.locations:
            self.state["locations"] = [{"code": "main", "name": "🌍 Основной", "proxy": ""}]
        self._save()
        self.schedule_apply()
        return n

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

    def remove_location(self, code: str, apply: bool = True) -> bool:
        keep = [l for l in self.locations if l["code"] != code.lower()]
        if len(keep) == len(self.locations) or not keep:
            return False
        self.state["locations"] = keep
        self._save()
        if apply:
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

    async def check_proxies(self) -> list[tuple[dict, bool]]:
        """Проверяет прокси стран, добавленных вручную: через каждый открывается настоящее
        HTTPS-подключение, так что ловится и истёкший логин, а не только закрытый порт.
        Нерабочие страны прячутся из подписки. Возвращает изменения: (страна, работает_ли)."""
        manual = [l for l in self.locations if l["proxy"] and not l.get("auto")]
        if not manual or not await public_proxies.direct_ok():
            return []  # сервер сам не дошёл до проверочного сайта: прокси тут ни при чём

        async def alive(loc):
            return bool(await public_proxies.probe(loc["proxy"]) or await public_proxies.probe(loc["proxy"]))

        changes = []
        for loc, ok in zip(manual, await asyncio.gather(*(alive(l) for l in manual))):
            if bool(loc.get("down")) == ok:
                loc["down"] = not ok
                changes.append((loc, ok))
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
               for loc in self.locations
               if not loc.get("down") and not (loc.get("auto") and self.auto_rejected)]
        direct = self.user_uuid(user_id, self.direct_location()["code"])
        out += [self._link(direct, b["host"], b["port"], b["sni"] or self.sni, b["name"]) for b in self.bridges]
        return out

    # ---------- сайт маскировки ----------

    @property
    def masking(self) -> dict:
        return self.state["masking"]

    @property
    def sni(self) -> str:
        return self.masking["site"] or self.env_sni

    def set_masking(self, *, auto=None, every=None) -> None:
        if auto is not None:
            self.masking["auto"] = bool(auto)
        if every is not None:
            self.masking["every"] = max(0, int(every))
        self._save()

    def grace_names(self) -> list[str]:
        """Прежние сайты, ключи с которыми ещё принимаются, пока клиенты обновляют подписку."""
        now = time.time()
        return [p["name"] for p in self.masking["prev"] if p["until"] > now and p["name"] != self.sni]

    async def site_flagged(self, site: str) -> bool | None:
        """Предупреждает ли Xray, что под этот сайт маскироваться рискованно.
        None — проверить не удалось или Xray не принимает конфиг с этим сайтом."""
        if not os.path.exists(self.xray_bin):
            return None
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".site.json"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.build_config(site=site), f)
            code, out = await self._run(self.xray_bin, "run", "-test", "-c", tmp)
        except OSError:
            return None
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return None if code != 0 else "increase the likelihood" in out

    async def change_sni(self, site: str, grace: bool = False) -> bool:
        """Меняет сайт маскировки и сразу применяет конфиг. Если Xray его не принял,
        возвращает прежний сайт. grace: сутки принимать и ключи с прежним сайтом."""
        old = self.sni
        if site == old:
            return True
        backup = json.loads(json.dumps(self.masking))
        # Без grace новый сайт не отвечает на чужие имена, так что прежние ключи не сработают вовсе.
        keep = [p for p in self.masking["prev"] if p["name"] not in (old, site)][:2]
        self.masking["prev"] = [{"name": old, "until": time.time() + 86400}] + keep if grace else []
        self.masking["site"], self.masking["changed"] = site, time.time()
        self._save()
        if await self.apply():
            return True
        self.state["masking"] = backup
        self._save()
        return False

    def server_names(self) -> list[str]:
        names = [self.sni] + [n for n in self.grace_names()]
        for b in self.bridges:
            if b["sni"] and b["sni"] not in names:
                names.append(b["sni"])
        return names

    def relay_outbound(self, code: str) -> dict:
        """Авто-страна выходит через локальный ретранслятор: он сам выбирает живой прокси."""
        return {"protocol": "socks", "settings": {"servers": [{
            "address": "127.0.0.1", "port": self.relay_port,
            "users": [{"user": code, "pass": self.relay_password}]}]}}

    def build_config(self, with_auto: bool = True, site: str | None = None) -> dict:
        locations = [l for l in self.locations if with_auto or not l.get("auto")]
        now = time.time()
        active = [int(u) for u, exp in self.state["users"].items() if exp > now]
        clients, by_loc = [], {}
        for uid in active:
            for loc in locations:
                email = f"u{uid}.{loc['code']}"
                clients.append({"id": self.user_uuid(uid, loc["code"]), "flow": "xtls-rprx-vision",
                                "email": email})
                by_loc.setdefault(loc["code"], []).append(email)

        outbounds = [{"tag": "direct", "protocol": "freedom"},
                     {"tag": "block", "protocol": "blackhole"}]
        rules = [{"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
                 {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}]
        for loc in locations:
            if not loc["proxy"]:
                continue
            users = by_loc.get(loc["code"])
            if loc.get("auto"):
                outbounds.append({"tag": f"out-{loc['code']}", **self.relay_outbound(loc["code"])})
                if users:
                    # Публичные прокси UDP не пересылают: запросы DNS уходят с самого сервера,
                    # остальной UDP отклоняется, и приложения сразу переходят на TCP.
                    rules.append({"type": "field", "user": users, "network": "udp", "port": "53",
                                  "outboundTag": "direct"})
                    rules.append({"type": "field", "user": users, "network": "udp",
                                  "outboundTag": "block"})
            else:
                outbounds.append({"tag": f"out-{loc['code']}", **parse_proxy(loc["proxy"])})
            if users:
                rules.append({"type": "field", "user": users, "outboundTag": f"out-{loc['code']}"})

        return {
            "log": {"loglevel": "warning", "access": "none"},
            "inbounds": [{
                "tag": "in", "listen": "0.0.0.0", "port": self.port, "protocol": "vless",
                "settings": {"clients": clients, "decryption": "none"},
                "streamSettings": {
                    "network": "tcp", "security": "reality",
                    "realitySettings": {"show": False, "dest": f"{site or self.sni}:443", "xver": 0,
                                        "serverNames": [site] if site else self.server_names(), "privateKey": self.private_key,
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
        """Пишет новый конфиг, проверяет его самим Xray и только потом перезапускает.
        Если Xray не принимает конфиг с авто-странами, применяется конфиг без них:
        основная страна, купленные прокси и новые клиенты не должны от них зависеть."""
        # Xray определяет формат по расширению, поэтому временный файл тоже .json
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".next.json"
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        if not os.path.exists(self.xray_bin):
            await self._problem(f"Xray не найден: {self.xray_bin}. Конфиг не применён.")
            return False
        has_auto = bool(self.auto_locations())
        rejected = ""
        for with_auto in ((True, False) if has_auto else (True,)):
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.build_config(with_auto), ensure_ascii=False, indent=1))
            os.chmod(tmp, 0o644)
            code, out = await self._run(self.xray_bin, "run", "-test", "-c", tmp)
            if code == 0:
                break
            rejected = rejected or out[-700:].strip()
            log.error("Xray отклонил конфиг%s:\n%s", " с авто-странами" if with_auto and has_auto else "",
                      out[-1500:])
        else:
            await self._problem("Xray отклонил конфиг, оставляю прежний:\n" + rejected)
            return False
        os.replace(tmp, self.config_path)
        code, out = await self._run(*self.restart_cmd)
        if code != 0:
            await self._problem("Не удалось перезапустить Xray: " + out[-500:].strip())
            return False
        self.last_apply = time.time()
        self.auto_rejected = has_auto and not with_auto
        log.info("Xray обновлён: %d клиентов, стран: %d", len(self.state["users"]), len(self.locations))
        if self.auto_rejected:
            await self._problem("Xray не принял настройки авто-стран, поэтому они отключены и скрыты "
                                "из подписки. Остальные страны работают.\n" + rejected)
        else:
            self.last_error = ""
        return True

    async def xray_running(self) -> bool:
        try:
            code, _ = await self._run("systemctl", "is-active", "--quiet", "xray")
        except OSError:
            return False
        return code == 0

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
            "profile-update-interval": "1",
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
        auto_enabled=e.get("AUTO_PROXY", "0") == "1",
        auto_countries=[c.strip().lower() for c in e.get("AUTO_PROXY_COUNTRIES", "").replace(" ", "").split(",") if c.strip()],
        auto_max=int(e.get("AUTO_PROXY_MAX", "8")),
        relay_port=int(e.get("AUTO_RELAY_PORT", "20808")),
    )
