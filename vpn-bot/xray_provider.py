"""Настоящий VPN на Xray: один вход VLESS Reality на 443 и выход через прокси других стран.

Каждый клиент получает отдельный ключ под каждую страну. Сервер по ключу понимает,
через какую страну выпустить трафик: напрямую (страна самого сервера) или через прокси.
Клиенту выдаётся одна ссылка-подписка, в приложении она превращается в список стран.

Выдача и отключение ключей идут через API Xray на 127.0.0.1 без перезапуска, поэтому
подключения остальных клиентов не рвутся. Перезапуск нужен только при смене стран, мостов
или сайта маскировки. Если API не ответил, бот по-старому применяет конфиг целиком.
Через тот же API бот берёт трафик и адреса, с которых сейчас подключены ключи.
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
from hysteria import Hysteria
from vpn import VpnProvider

log = logging.getLogger("vpn-bot.xray")

CODE_RE = re.compile(r"^[a-z0-9]{1,8}$")
EMAIL_RE = re.compile(r"u(\d+)\.[a-z0-9]+")


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
                 relay_port: int = 20808, api_port: int = 10085, hy2: dict | None = None,
                 xhttp_port: int = 0, hy2_first: bool = False, hy2_extra: dict | None = None):
        self.state_path, self.config_path, self.xray_bin = state_path, config_path, xray_bin
        self.host, self.port, self.env_sni = public_host, port, sni
        self.private_key, self.public_key, self.short_id = private_key, public_key, short_id
        self.sub_port, self.brand, self.restart_cmd = sub_port, brand, restart_cmd
        self.relay_port, self.api_port = relay_port, api_port
        self.state = self._load(default_location, auto_enabled, list(auto_countries), auto_max)
        # Hysteria2 по UDP рядом с Reality: только для страны самого сервера.
        self.hy2 = Hysteria(host=public_host, secret=self.state["secret"], is_allowed=self.allowed,
                            **hy2) if hy2 else None
        # Серверы Hysteria для других стран: диапазон UDP-портов, папка конфигов, команда служб.
        self.hy2_extra = hy2_extra if self.hy2 and hy2_extra else None
        if self.hy2_extra:
            self.hy2.extra_ports = self.hy2_extra["ports"]
            self.hy2.locs = {c: p for c, p in self.state["hy2_ports"].items() if p in self.hy2_extra["ports"]}
        self.xhttp_port, self.hy2_first = xhttp_port, hy2_first
        self.live: set[str] = set()  # подписки, которые сейчас есть в запущенном Xray
        self._api_lock = asyncio.Lock()  # изменения через API по одному, чтобы не мешали друг другу
        self.usage = None            # функция(подписка) -> (отдано, получено): бот берёт из базы
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
        st.setdefault("devices", {})     # подписка -> сколько устройств оплачено
        st.setdefault("suspended", {})   # подписка -> до какого времени отключена за превышение
        st.setdefault("hy2_ports", {})   # страна -> UDP-порт её сервера Hysteria2
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

    def reorder_auto_pool(self, code: str, pool: list[str]) -> None:
        """Новый порядок прокси авто-страны (первый — рабочий) без перезапуска Xray."""
        loc = next((l for l in self.auto_locations() if l["code"] == code), None)
        if not loc or sorted(pool) != sorted(loc.get("pool") or []):
            return
        if loc["proxy"] != pool[0]:
            loc.update(proxy=pool[0], since=time.time(), ms=None)
        loc["pool"] = list(pool)
        self._save()

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

    def allowed(self, sid: int) -> bool:
        """Пускать ли подписку: срок не истёк и она не отключена за превышение устройств."""
        key = str(sid)
        return self.state["users"].get(key, 0) > time.time() and not self.is_suspended(sid)

    def is_suspended(self, sid: int) -> bool:
        return self.state["suspended"].get(str(sid), 0) > time.time()

    def _apply_pending(self) -> bool:
        return bool(self._pending and not self._pending.done())

    async def issue(self, user_id: int, expires_at: float, devices: int | None = None) -> str:
        key = str(user_id)
        self.state["users"][key] = expires_at
        if devices:
            self.state["devices"][key] = int(devices)
        self._save()
        # Ключ уже есть в Xray (продление) — ничего делать не нужно. Новый ключ добавляется
        # на ходу, а если API не ответил, конфиг применяется целиком.
        if key not in self.live and self.allowed(user_id) and not self._apply_pending():
            if not await self._hot_add([user_id]):
                self.schedule_apply()
        return self.sub_url(user_id)

    async def revoke(self, user_id: int) -> None:
        key = str(user_id)
        if self.state["users"].pop(key, None) is None:
            return
        self.state["devices"].pop(key, None)
        self.state["suspended"].pop(key, None)
        self._save()
        if self._apply_pending():
            pass  # ожидающее применение и так соберёт конфиг без этого ключа
        elif key in self.live:
            if not await self._hot_remove([user_id]):
                self.schedule_apply()
        elif not self.last_apply:
            self.schedule_apply()  # что сейчас в Xray, неизвестно: применяем целиком
        if self.hy2:
            await self.hy2.kick([user_id])

    async def sync(self, active: dict[int, float], devices: dict[int, int] | None = None) -> None:
        """При запуске бота: сервер получает ровно тех, у кого доступ активен."""
        self.state["users"] = {str(k): v for k, v in active.items()}
        if devices is not None:
            self.state["devices"] = {str(k): int(v) for k, v in devices.items() if k in active}
        now = time.time()
        self.state["suspended"] = {k: t for k, t in self.state["suspended"].items()
                                   if t > now and k in self.state["users"]}
        self._save()
        await self.apply()

    # ---------- отключение за превышение устройств ----------

    async def suspend(self, sid: int, seconds: float) -> None:
        """Временно отключает подписку: Xray убирает её ключи, Hysteria разрывает подключения."""
        self.state["suspended"][str(sid)] = time.time() + seconds
        self._save()
        if str(sid) in self.live and not await self._hot_remove([sid]):
            self.schedule_apply()
        if self.hy2:
            await self.hy2.kick([sid])

    def due_resume(self) -> list[int]:
        """Подписки, у которых закончилось отключение за превышение: их пора вернуть в Xray."""
        now = time.time()
        return [int(k) for k, t in self.state["suspended"].items() if t <= now]

    async def resume(self, sid: int) -> None:
        if self.state["suspended"].pop(str(sid), None) is None:
            return
        self._save()
        if self.allowed(sid) and str(sid) not in self.live and not await self._hot_add([sid]):
            self.schedule_apply()

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

    @property
    def xhttp_path(self) -> str:
        return "/" + hmac.new(self.state["secret"].encode(), b"xhttp", hashlib.sha256).hexdigest()[:16]

    def _xhttp_link(self, uid: str, name: str) -> str:
        q = (f"encryption=none&security=reality&sni={self.sni}&fp=chrome&pbk={self.public_key}"
             f"&sid={self.short_id}&type=xhttp&path={quote(self.xhttp_path, safe='')}&mode=auto")
        return f"vless://{uid}@{self.host}:{self.xhttp_port}?{q}#{quote(name)}"

    def _hy2_port(self, loc: dict) -> int | None:
        if not self.hy2:
            return None
        if loc is self.direct_location():
            return self.hy2.port
        return self.hy2.locs.get(loc["code"]) if self.hy2_extra else None

    def links(self, user_id: int) -> list[str]:
        direct_loc = self.direct_location()
        fast, out = [], []
        for loc in self.locations:
            if loc.get("down") or (loc.get("auto") and self.auto_rejected):
                continue
            uid = self.user_uuid(user_id, loc["code"])
            out.append(self._link(uid, self.host, self.port, self.sni, loc["name"]))
            if self.xhttp_port:
                out.append(self._xhttp_link(uid, f"{loc['name']} · XHTTP"))
            port = self._hy2_port(loc)
            if port:
                # По умолчанию Hysteria2 идёт первым: на сетях, где оператор замораживает TCP,
                # приложение сразу берёт рабочий способ. Иначе — сразу после своей страны.
                (fast if self.hy2_first else out).append(
                    self.hy2.link(user_id, f"{loc['name']} ⚡ Hysteria2", port))
        out = fast + out
        direct = self.user_uuid(user_id, direct_loc["code"])
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

    def _clients(self, sids, locations) -> list[dict]:
        return [{"id": self.user_uuid(uid, loc["code"]), "flow": "xtls-rprx-vision",
                 "email": f"u{uid}.{loc['code']}"}
                for uid in sids for loc in locations]

    def _inbound(self, clients: list[dict], site: str | None = None) -> dict:
        return {
            "tag": "in", "listen": "0.0.0.0", "port": self.port, "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "streamSettings": {
                "network": "tcp", "security": "reality",
                "realitySettings": {"show": False, "dest": f"{site or self.sni}:443", "xver": 0,
                                    "serverNames": [site] if site else self.server_names(),
                                    "privateKey": self.private_key, "shortIds": [self.short_id]},
            },
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
        }

    def _inbound_xh(self, clients: list[dict], site: str | None = None) -> dict:
        """VLESS через XHTTP на отдельном порту: трафик идёт как обычные HTTP-запросы, а не одним
        длинным потоком. Vision с XHTTP не работает, поэтому flow у ключей пустой."""
        inb = self._inbound([{k: v for k, v in c.items() if k != "flow"} for c in clients], site)
        inb.update(tag="in-xh", port=self.xhttp_port)
        inb["streamSettings"]["network"] = "xhttp"
        inb["streamSettings"]["xhttpSettings"] = {"path": self.xhttp_path, "mode": "auto"}
        return inb

    def _user_inbounds(self, clients: list[dict], site: str | None = None) -> list[dict]:
        inbs = [self._inbound(clients, site)]
        if self.xhttp_port:
            inbs.append(self._inbound_xh(clients, site))
        return inbs

    def active_sids(self) -> list[int]:
        now = time.time()
        return [int(u) for u, exp in self.state["users"].items() if exp > now and not self.is_suspended(int(u))]

    def build_config(self, with_auto: bool = True, site: str | None = None) -> dict:
        locations = [l for l in self.locations if with_auto or not l.get("auto")]
        active = self.active_sids()
        clients = self._clients(active, locations)

        def users_of(code: str) -> list[str]:
            # Явный список и шаблон: ключи, добавленные через API после запуска, тоже
            # попадают в свою страну. Старый Xray без шаблонов обходится явным списком.
            return [f"u{uid}.{code}" for uid in active] + [f"regexp:^u[0-9]+\\.{code}$"]

        outbounds = [{"tag": "direct", "protocol": "freedom"},
                     {"tag": "block", "protocol": "blackhole"}]
        rules = [{"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
                 {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}]
        inbounds = self._user_inbounds(clients, site)
        if self.api_port:
            # API только для самого сервера: им бот добавляет ключи и берёт статистику.
            inbounds.append({"tag": "api", "listen": "127.0.0.1", "port": self.api_port,
                             "protocol": "dokodemo-door", "settings": {"address": "127.0.0.1"}})
            outbounds.append({"tag": "api", "protocol": "freedom"})
            rules.insert(0, {"type": "field", "inboundTag": ["api"], "outboundTag": "api"})
        for loc in locations:
            if not loc["proxy"]:
                continue
            users = users_of(loc["code"])
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

        cfg = {
            "log": {"loglevel": "warning", "access": "none"},
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": {"domainStrategy": "AsIs", "rules": rules},
        }
        if self.api_port:
            cfg["api"] = {"tag": "api", "services": ["HandlerService", "StatsService"]}
            cfg["stats"] = {}
            cfg["policy"] = {"levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True,
                                              "statsUserOnline": True}}}
        return cfg

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
        self.live = {str(u) for u in self.active_sids()}
        await self.sync_hy2_locations()
        self.auto_rejected = has_auto and not with_auto
        log.info("Xray обновлён: %d клиентов, стран: %d", len(self.state["users"]), len(self.locations))
        if self.auto_rejected:
            await self._problem("Xray не принял настройки авто-стран, поэтому они отключены и скрыты "
                                "из подписки. Остальные страны работают.\n" + rejected)
        else:
            self.last_error = ""
        return True

    # ---------- API Xray: ключи без перезапуска, трафик и устройства ----------

    async def _xapi(self, cmd: str, *args) -> tuple[int, str]:
        # Флаги до имён и файлов: разбор флагов в Xray останавливается на первом обычном аргументе.
        try:
            return await asyncio.wait_for(
                self._run(self.xray_bin, "api", cmd, f"--server=127.0.0.1:{self.api_port}", *args), 15)
        except (OSError, asyncio.TimeoutError) as e:
            return 1, str(e)

    def _emails(self, sids) -> list[str]:
        return [f"u{s}.{l['code']}" for s in sids for l in self.locations]

    async def _hot_add(self, sids) -> bool:
        """Добавляет ключи в работающий Xray. False — не вышло, нужен полный перезапуск."""
        if not self.api_port or not self.last_apply or not os.path.exists(self.xray_bin):
            return False
        async with self._api_lock:
            return await self._hot_add_locked(sids)

    async def _hot_add_locked(self, sids) -> bool:
        locations = [l for l in self.locations if not (l.get("auto") and self.auto_rejected)]
        clients = self._clients(sids, locations)
        if not clients:
            return True
        inbounds = self._user_inbounds(clients)
        # Сначала убираем те же ключи: повторное добавление Xray считает ошибкой.
        for inb in inbounds:
            await self._xapi("rmu", f"-tag={inb['tag']}", *[c["email"] for c in clients])
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".users.json"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"inbounds": inbounds}, f)
            code, out = await self._xapi("adu", tmp)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        m = re.search(r"Added (\d+) user", out)
        if code != 0 or not m or int(m.group(1)) != len(clients) * len(inbounds):
            log.warning("API Xray не добавил ключи %s, применяю конфиг целиком: %s", sids, out[-300:])
            return False
        self.live.update(str(s) for s in sids)
        log.info("Xray: ключи %s добавлены без перезапуска", sids)
        return True

    async def _hot_remove(self, sids) -> bool:
        if not self.api_port or not self.last_apply or not os.path.exists(self.xray_bin):
            return False
        tags = ["in"] + (["in-xh"] if self.xhttp_port else [])
        async with self._api_lock:
            code, out = 0, ""
            for tag in tags:
                c, o = await self._xapi("rmu", f"-tag={tag}", *self._emails(sids))
                code, out = code or c, out + o
        if code != 0:
            log.warning("API Xray не убрал ключи %s, применяю конфиг целиком: %s", sids, out[-300:])
            return False
        self.live.difference_update(str(s) for s in sids)
        return True

    @staticmethod
    def _json(out: str):
        start = out.find("{")
        try:
            return json.loads(out[start:]) if start >= 0 else None
        except ValueError:
            return None

    async def traffic(self) -> dict[int, tuple[int, int]]:
        """Трафик по подпискам с прошлого вызова: {подписка: (отдано, получено)}, Xray и Hysteria вместе."""
        out: dict[int, list[int]] = {}
        if self.api_port and self.last_apply and os.path.exists(self.xray_bin):
            code, text = await self._xapi("statsquery", "-pattern=user>>>", "-reset")
            data = self._json(text) if code == 0 else None
            for st in (data or {}).get("stat") or []:
                parts = str(st.get("name", "")).split(">>>")
                m = EMAIL_RE.fullmatch(parts[1]) if len(parts) == 4 and parts[2] == "traffic" else None
                if m:
                    pair = out.setdefault(int(m.group(1)), [0, 0])
                    pair[0 if parts[3] == "uplink" else 1] += int(st.get("value") or 0)
        if self.hy2:
            for sid, (up, down) in (await self.hy2.traffic() or {}).items():
                pair = out.setdefault(sid, [0, 0])
                pair[0] += up
                pair[1] += down
        return {k: (v[0], v[1]) for k, v in out.items() if v[0] or v[1]}

    async def online(self) -> dict[int, int] | None:
        """Сколько устройств подключено к каждой подписке сейчас. None — узнать не удалось.
        Для Xray это число разных IP за всеми странами подписки, для Hysteria — число подключений."""
        ips: dict[int, set[str]] = {}
        got = False
        if self.api_port and self.last_apply and os.path.exists(self.xray_bin):
            code, text = await self._xapi("statsonlineiplist", "-all")
            data = self._json(text) if code == 0 else None
            if data is not None:
                got = True
                for u in data.get("users") or []:
                    m = EMAIL_RE.fullmatch(str(u.get("email", "")))
                    if m:
                        ips.setdefault(int(m.group(1)), set()).update(
                            str(e.get("ip")) for e in u.get("ips") or [] if e.get("ip"))
            else:  # Xray до версии с -all: список онлайн и адреса по каждому ключу
                code, text = await self._xapi("statsgetallonlineusers")
                data = self._json(text) if code == 0 else None
                if data is not None:
                    got = True
                    for name in data.get("users") or []:
                        m = EMAIL_RE.search(str(name))
                        if not m:
                            continue
                        c2, t2 = await self._xapi("statsonlineiplist", f"-email={m.group(0)}")
                        one = self._json(t2) if c2 == 0 else None
                        ips.setdefault(int(m.group(1)), set()).update((one or {}).get("ips") or {})
        counts = {sid: len(v) for sid, v in ips.items()}
        if self.hy2:
            hy = await self.hy2.online()
            if hy is not None:
                got = True
                for sid, n in hy.items():
                    counts[sid] = counts.get(sid, 0) + n
        return counts if got else None

    # ---------- серверы Hysteria2 для других стран ----------

    async def sync_hy2_locations(self) -> None:
        """Для каждой страны с прокси — свой сервер Hysteria2 на своём UDP-порту. Перезапускается
        только сервер той страны, у которой поменялись настройки; остальные не трогаются."""
        if not self.hy2_extra:
            return
        cfg = self.hy2_extra
        ports = self.state["hy2_ports"]
        wanted = {l["code"]: l for l in self.locations
                  if l["proxy"] and not (l.get("auto") and self.auto_rejected)}
        changed = False
        for code in [c for c in ports if c not in wanted]:
            await self._run(*cfg["systemctl"], "disable", "--now", f"{cfg['unit']}{code}")
            path = os.path.join(cfg["dir"], f"loc-{code}.yaml")
            if os.path.exists(path):
                os.unlink(path)
            ports.pop(code)
            changed = True
        for code, loc in wanted.items():
            if code not in ports:
                free = next((p for p in cfg["ports"] if p not in ports.values()), None)
                if free is None:
                    log.warning("Hysteria2: кончились порты %s, страна %s без Hysteria", cfg["ports"], code)
                    continue
                ports[code] = free
                changed = True
            relay = (self.relay_port, code, self.relay_password) if loc.get("auto") else None
            text = self.hy2.location_config(ports[code], loc["proxy"], relay)
            path = os.path.join(cfg["dir"], f"loc-{code}.yaml")
            try:
                with open(path, encoding="utf-8") as f:
                    same = f.read() == text
            except OSError:
                same = False
            if same:
                continue
            try:
                os.makedirs(cfg["dir"], exist_ok=True)
                fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                try:
                    import shutil
                    shutil.chown(path + ".tmp", group=cfg.get("group", "hysteria"))
                except (LookupError, OSError):
                    pass
                os.replace(path + ".tmp", path)
            except OSError as e:
                await self._problem(f"Hysteria2 для {loc['name']}: не записан конфиг: {e}")
                continue
            unit = f"{cfg['unit']}{code}"
            await self._run(*cfg["systemctl"], "enable", unit)
            code_, out = await self._run(*cfg["systemctl"], "restart", unit)
            if code_ != 0:
                await self._problem(f"Hysteria2 для {loc['name']} не запустился: {out[-300:].strip()}")
        if changed:
            self._save()
        self.hy2.locs = dict(ports)

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
        up = down = 0
        if self.usage:
            try:
                up, down = self.usage(user_id)
            except Exception:
                log.exception("трафик для подписки %s", user_id)
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "profile-title": f"base64:{title}",
            "subscription-userinfo": f"upload={int(up)}; download={int(down)}; total=0; expire={int(exp)}",
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


def hy2_from_env(e) -> dict | None:
    """Настройки Hysteria2 из .env. Установщик заполняет их сам, пусто — Hysteria2 выключен."""
    if not e.get("HY2_PORT") or e.get("HY2", "1") == "0":
        return None
    return {"port": int(e["HY2_PORT"]), "cert_path": e.get("HY2_CERT", "/etc/hysteria/server.crt"),
            "sni": e.get("HY2_SNI") or e.get("REALITY_SNI", "www.microsoft.com"),
            "auth_port": int(e.get("HY2_AUTH_PORT", "20809")),
            "stats_port": int(e.get("HY2_STATS_PORT", "20810")),
            "stats_secret": e.get("HY2_STATS_SECRET", ""), "obfs_password": e.get("HY2_OBFS_PASSWORD", "")}


def hy2_extra_from_env(e) -> dict | None:
    """Диапазон UDP-портов для серверов Hysteria2 других стран, например 30000-30049. 0 — выключено."""
    raw = e.get("HY2_EXTRA_PORTS", "30000-30049").strip()
    m = re.fullmatch(r"(\d+)-(\d+)", raw)
    if not m or int(m.group(1)) > int(m.group(2)):
        return None
    return {"ports": range(int(m.group(1)), int(m.group(2)) + 1),
            "dir": e.get("HY2_DIR", "/etc/hysteria"), "unit": "hysteria-loc@", "systemctl": ("systemctl",)}


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
        api_port=int(e.get("XRAY_API_PORT", "10085")),
        hy2=hy2_from_env(e),
        hy2_extra=hy2_extra_from_env(e),
        hy2_first=e.get("HY2_FIRST", "1") == "1",
        xhttp_port=int(e.get("XRAY_XHTTP_PORT", "8443")),
    )
