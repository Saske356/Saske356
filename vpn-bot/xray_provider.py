"""Настоящий VPN на Xray: один вход VLESS Reality на 443 и выход через прокси других стран.

Каждый клиент получает отдельный ключ под каждую страну. Сервер по ключу понимает,
через какую страну выпустить трафик: напрямую (страна самого сервера) или через прокси.
Клиенту выдаётся одна ссылка-подписка, в приложении она превращается в список стран.

Клиенты добавляются и убираются через API Xray на лету: выдача и отключение доступа не
перезапускают Xray и не рвут подключения остальных. Перезапуск нужен только при смене
стран, мостов или сайта маскировки.

Рядом с Xray работает Hysteria2 (UDP, QUIC) на порту 443/udp. Он идёт первым в подписке:
когда оператор режет TCP-подключения к зарубежным серверам, UDP часто проходит. Пароли клиентов
Hysteria проверяет у бота (start_hy2_auth), поэтому её никогда не нужно перезапускать.

На том же порту 443 работает запасной вход XHTTP: если оператор режет обычное подключение,
у клиента в подписке есть вариант «· запасной» с другим видом трафика.
"""

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from urllib.parse import parse_qs, quote, unquote, urlparse

import client_config
from chat_relay import ChatRelay
import public_proxies
from guard import RateGuard
from vpn import VpnProvider

log = logging.getLogger("vpn-bot.xray")

CODE_RE = re.compile(r"^[a-z0-9]{1,8}$")
EMAIL_RE = re.compile(r"u(\d+)\.")  # имя ключа в Xray: u<подписка>.<страна>
XHTTP_SOCKET = "@aurora-xhttp"   # вход XHTTP за основным входом, наружу не открыт
API_CHUNK = 150                  # сколько клиентов за один вызов API


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


HY2_ID_RE = re.compile(r"u(\d+)(v\d+)?")
HY2_VARIANTS = 200  # сколько вариантов пароля обрывать при отключении (пунктов на один сервер меньше)


def hy2_id(uid: int, variant: int = -1) -> str:
    """Имя клиента в статистике Hysteria: u5 — пароль без варианта (ссылки и старые подписки),
    u5v2 — пункт с вариантом 2 (JSON-подписка этой версии)."""
    return f"u{uid}v{variant}" if variant >= 0 else f"u{uid}"


# Вход по Hysteria за последние 4 минуты — устройство ещё в сети. Окно короче, чем проверок до
# предупреждения (3 по 2 мин): переход телефона с Wi-Fi на мобильную сеть не сочтётся вторым устройством.
HY2_NET_WINDOW = 240
# Устройство по номеру (HWID: его шлёт Happ, наши приложения, заголовок x-hwid), которое не обновляло
# подписку столько времени, освобождает место — например, старый телефон.
HWID_TTL = 7 * 86400
LIMIT_NAME = "⛔ Превышен лимит устройств"


def device_net(addr: str) -> str:
    """Сеть устройства по адресу «ip:порт»: /24 для IPv4, /56 для IPv6 — у мобильного оператора
    один телефон может выходить с разных адресов одного пула."""
    import ipaddress
    host = addr.strip()
    if host.startswith("["):
        host = host[1:].partition("]")[0]
    elif host.count(":") == 1:
        host = host.partition(":")[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return ""
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    plen = 24 if ip.version == 4 else 56
    return str(ipaddress.ip_network(f"{ip}/{plen}", strict=False))


class XrayProvider(VpnProvider):
    is_demo = False

    def __init__(self, *, state_path: str, config_path: str, xray_bin: str, public_host: str,
                 port: int, sni: str, private_key: str, public_key: str, short_id: str,
                 sub_port: int, brand: str = "VPN", default_location: str = "🌍 Основной",
                 restart_cmd: tuple = ("systemctl", "restart", "xray"),
                 auto_enabled: bool = False, auto_countries: tuple = (), auto_max: int = 15,
                 relay_port: int = 20808, api_port: int = 10085, bridge_port: int = 8444,
                 xhttp: bool = True, sub_base: str = "", hy2: dict | None = None, hy2_auth_port: int = 20809,
                 hy2_locs: dict | None = None, json_sub: bool = True,
                 xray_enabled: bool = True, sub_domain: str = "", sub_tls_port: int = 443,
                 sub_cert: str = "", sub_key: str = ""):
        self.state_path, self.config_path, self.xray_bin = state_path, config_path, xray_bin
        # Зашифрованный чат приложения Arise: только шифр, хранится рядом с vpn.json (chat_relay.py)
        self.chat = ChatRelay(os.path.join(os.path.dirname(state_path) or ".", "chat.json"))
        self.host, self.port, self.env_sni = public_host, port, sni
        self.private_key, self.public_key, self.short_id = private_key, public_key, short_id
        self.sub_port, self.brand, self.restart_cmd = sub_port, brand, restart_cmd
        self.relay_port, self.api_port, self.bridge_port = relay_port, api_port, bridge_port
        # XRAY_ENABLED=0: Xray не используется вовсе, VPN идёт только через Hysteria
        self.xray_enabled = xray_enabled
        self.xhttp_enabled = xhttp and xray_enabled
        # Подписка по HTTPS на своём домене: https://домен/КОРОТКИЙ_ТОКЕН
        self.sub_domain = sub_domain.strip().lower()
        self.sub_tls_port, self.sub_cert, self.sub_key = sub_tls_port, sub_cert, sub_key
        self._tls_server: asyncio.base_events.Server | None = None
        self.sub_https: bool | None = None  # HTTPS-раздача: None — ещё не запускали, False — не поднялась
        self._short: dict[str, int] = {}
        # Приложения для обновления изнутри: {"aurora": AppRelease, "arise": AppRelease} (ставит бот)
        self.app_releases: dict = {}
        # Hysteria2: {"port", "sni", "pin", "obfs", "obfs_port", "stats_ports", "stats_secret"}.
        # port — обычный вариант (похож на HTTP/3), obfs_port — с обфускацией (похож на случайный UDP).
        self.hy2 = hy2 if hy2 and (hy2.get("port") or hy2.get("obfs_port")) else None
        self.hy2_auth_port = hy2_auth_port
        self._hy2_server: asyncio.base_events.Server | None = None
        self.hy2_logins = 0          # успешных входов через Hysteria с запуска бота
        # Hysteria сама сообщает только число подключений, а у одного телефона их бывает много:
        # «Лучший сервер» держит по подключению к каждой стране, приложения проверяют пинг.
        # Поэтому запоминаем, из каких сетей был вход (подписка -> сеть -> когда), и считаем их.
        self._hy2_nets: dict[int, dict[str, float]] = {}
        self.support_url = ""  # ссылка на бота, бот ставит её при запуске
        self.guard = RateGuard()  # защита раздачи подписок от флуда и перебора ссылок
        self.usage = None            # функция(подписка) -> (отдано, получено): бот берёт из базы
        # Hysteria для стран через прокси: {"ports": диапазон UDP, "dir": папка конфигов,
        # "stats_base": первый порт статистики, "systemctl": команда}. У каждой страны своя служба
        # aurora-hy2@loc-КОД на своём порту: Hysteria выбирает выход по адресу, а не по клиенту.
        self.hy2_locs = hy2_locs if self.hy2 and self.hy2.get("port") and hy2_locs else None
        self.json_default = json_sub
        self.sub_base = sub_base.strip().rstrip("/")
        self.state = self._load(default_location, auto_enabled, list(auto_countries), auto_max)
        self._pending: asyncio.Task | None = None
        self._server: asyncio.base_events.Server | None = None
        self.on_problem = None      # async-функция(текст): бот подставляет сюда оповещение админов
        self.last_error = ""        # текст последней проблемы, пусто — всё в порядке
        self.last_apply = 0.0       # когда конфиг последний раз успешно применён
        self.auto_rejected = False  # Xray принял конфиг только без авто-стран
        self.xhttp_off = False      # Xray не принял запасной вход XHTTP (слишком старая версия)
        # Что сейчас загружено в работающий Xray: клиенты по входам и «форма» конфига без клиентов.
        # Если форма не изменилась, клиенты меняются через API без перезапуска.
        self._live: dict | None = None
        self._live_shape = ""
        self._live_flags = (True, True)
        self.restarts = 0           # перезапусков Xray с запуска бота
        self.hot_updates = 0        # изменений клиентов без перезапуска

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
        st.setdefault("bridge_site", "")  # российский сайт маскировки для мостов «ru»
        st.setdefault("devices", {})     # подписка -> сколько устройств оплачено
        st.setdefault("hy2_ports", {})   # страна -> UDP-порт её сервера Hysteria
        st.setdefault("suspended", {})   # подписка -> до какого времени отключена за превышение
        # Настройки авто-стран берутся из окружения только при первом запуске,
        # дальше ими управляет команда /autoproxy.
        st.setdefault("auto", {"enabled": bool(auto_enabled),
                               "countries": [c.lower() for c in auto_countries],
                               "max": int(auto_max)})
        st["auto"].setdefault("notify", True)
        st["auto"].setdefault("exclude", [])
        # 13.11: бесплатных стран по умолчанию до 15 (было 8), 14.11: до 25;
        # заданное админом число не трогаем
        if not st["auto"].get("max15"):
            if int(st["auto"].get("max") or 8) == 8:
                st["auto"]["max"] = 15
            st["auto"]["max15"] = True
        if not st["auto"].get("max25"):
            if int(st["auto"].get("max") or 15) == 15:
                st["auto"]["max"] = 25
            st["auto"]["max25"] = True
        # 14.11: пункты «обход БС» убраны (не помогали); вернуть — /bs on
        if not st.get("bs_off1"):
            st["bs_on"], st["bs_off1"] = False, True
        # Сайт маскировки: пока его не меняли из бота, действует значение из .env.
        m = st.setdefault("masking", {})
        for key, value in (("site", ""), ("prev", []), ("auto", True), ("every", 0), ("changed", 0)):
            m.setdefault(key, value)
        for loc in st["locations"]:
            if not loc.get("auto"):
                # прежние версии прятали свои страны админа при сбое прокси — больше не прячем
                if loc.pop("down", None):
                    loc["failing"] = True
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

    def _kid(self, user_id: int) -> str:
        """Основа ключей подписки. После «Сбросить устройства» (reset_key) к ней добавляется
        номер поколения: ссылка подписки и пароли меняются, старые устройства теряют доступ."""
        gen = int(self.state.get("gen", {}).get(str(user_id), 0))
        return f"{user_id}g{gen}" if gen else str(user_id)

    def user_uuid(self, user_id: int, code: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.state['secret']}:{self._kid(user_id)}:{code}"))

    def sub_token(self, user_id: int) -> str:
        return hmac.new(self.state["secret"].encode(), self._kid(user_id).encode(), hashlib.sha256).hexdigest()[:24]

    async def reset_key(self, user_id: int) -> str:
        """Новые ссылка и пароли подписки: все подключённые устройства отключаются, и подключиться
        снова можно только по новой ссылке. Возвращает новую ссылку."""
        gens = self.state.setdefault("gen", {})
        gens[str(user_id)] = int(gens.get(str(user_id), 0)) + 1
        self.state.get("hwids", {}).pop(str(user_id), None)  # все устройства — заново
        self._short = {}
        self._hy2_nets.pop(user_id, None)
        self._save()
        self.schedule_apply()
        if self.hy2:
            await self.hy2_kick(user_id)
        return self.sub_url(user_id)

    B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

    def short_token(self, user_id: int) -> str:
        """16 символов из букв и цифр, по ним нельзя угадать ни номер, ни чужую подписку."""
        n = int.from_bytes(hmac.new(self.state["secret"].encode(), f"sub16:{self._kid(user_id)}".encode(),
                                    hashlib.sha256).digest(), "big")
        out = ""
        for _ in range(16):
            n, r = divmod(n, 62)
            out += self.B62[r]
        return out

    def _by_short(self, token: str) -> int | None:
        uid = self._short.get(token)
        if uid is None or str(uid) not in self.state["users"]:
            self._short = {self.short_token(int(u)): int(u) for u in self.state["users"]}
            uid = self._short.get(token)
        return uid

    def sub_url(self, user_id: int) -> str:
        if self.sub_domain and self.sub_cert and self.sub_https is not False:
            port = "" if self.sub_tls_port == 443 else f":{self.sub_tls_port}"
            return f"https://{self.sub_domain}{port}/{self.short_token(user_id)}"
        # SUB_URL: свой адрес раздачи, например домен за Cloudflare, если оператор режет порт подписки
        base = self.sub_base or f"http://{self.host}:{self.sub_port}"
        return f"{base}/sub/{user_id}/{self.sub_token(user_id)}"

    @property
    def xhttp_path(self) -> str:
        return "/" + hmac.new(self.state["secret"].encode(), b"xhttp", hashlib.sha256).hexdigest()[:12]

    @property
    def xhttp_on(self) -> bool:
        return self.xray_enabled and self.xhttp_enabled and not self.xhttp_off

    # ---------- интерфейс для бота ----------

    async def issue(self, user_id: int, expires_at: float, devices: int | None = None) -> str:
        self.state["users"][str(user_id)] = expires_at
        if devices:
            self.state["devices"][str(user_id)] = int(devices)
        self._save()
        self.schedule_apply()
        return self.sub_url(user_id)

    async def revoke(self, user_id: int) -> None:
        if self.state["users"].pop(str(user_id), None) is not None:
            self.state["devices"].pop(str(user_id), None)
            self.state["suspended"].pop(str(user_id), None)
            self._save()
            self.schedule_apply()
            if self.hy2:
                await self.hy2_kick(user_id)

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

    # ---------- лимит устройств: временное отключение подписки ----------

    def is_suspended(self, sid: int) -> bool:
        return self.state["suspended"].get(str(sid), 0) > time.time()

    def allowed(self, sid: int) -> bool:
        """Пускать ли подписку: срок не истёк и она не отключена за превышение устройств."""
        return self.state["users"].get(str(sid), 0) > time.time() and not self.is_suspended(sid)

    async def suspend(self, sid: int, seconds: float) -> None:
        """Отключает подписку на время: Xray убирает её ключи без перезапуска (через API),
        Hysteria перестаёт принимать пароль и разрывает открытые подключения."""
        self.state["suspended"][str(sid)] = time.time() + seconds
        self._save()
        self.schedule_apply()
        if self.hy2:
            await self.hy2_kick(sid)

    def due_resume(self) -> list[int]:
        """Подписки, у которых отключение закончилось: их пора вернуть."""
        now = time.time()
        return [int(k) for k, t in self.state["suspended"].items() if t <= now]

    async def resume(self, sid: int) -> None:
        if self.state["suspended"].pop(str(sid), None) is not None:
            self._save()
            self.schedule_apply()

    # ---------- трафик и устройства онлайн ----------

    @staticmethod
    def _json(out: str):
        start = out.find("{")
        try:
            return json.loads(out[start:]) if start >= 0 else None
        except ValueError:
            return None

    def _xray_stats_ready(self) -> bool:
        return self.xray_enabled and self._live is not None and os.path.exists(self.xray_bin)

    async def _hy2_all(self, path: str) -> list[dict]:
        out = []
        for port in self._stats_ports():
            try:
                data = await asyncio.to_thread(self._hy2_stats, port, "GET", path)
            except Exception:
                continue
            if isinstance(data, dict):
                out.append(data)
        return out

    async def traffic(self) -> dict[int, tuple[int, int]]:
        """Трафик по подпискам с прошлого вызова: {подписка: (отдано, получено)}, Xray и Hysteria вместе."""
        out: dict[int, list[int]] = {}
        if self._xray_stats_ready():
            code, text = await self._api("statsquery", "-pattern=user>>>", "-reset")
            data = self._json(text) if code == 0 else None
            for st in (data or {}).get("stat") or []:
                parts = str(st.get("name", "")).split(">>>")
                m = EMAIL_RE.match(parts[1]) if len(parts) == 4 and parts[2] == "traffic" else None
                if m:
                    pair = out.setdefault(int(m.group(1)), [0, 0])
                    pair[0 if parts[3] == "uplink" else 1] += int(st.get("value") or 0)
        for data in await self._hy2_all("/traffic?clear=1"):
            for ident, v in data.items():
                m = HY2_ID_RE.fullmatch(str(ident))
                if m and isinstance(v, dict):
                    pair = out.setdefault(int(m.group(1)), [0, 0])
                    pair[0] += int(v.get("tx") or 0)
                    pair[1] += int(v.get("rx") or 0)
        return {k: (v[0], v[1]) for k, v in out.items() if v[0] or v[1]}

    async def online(self) -> dict[int, int] | None:
        """Сколько устройств подключено к каждой подписке сейчас. None — узнать не удалось.
        Устройство — отдельная сеть (адреса из одной /24 — один телефон за NAT оператора):
        для Xray это адреса подключений, для Hysteria — адреса входов за последние HY2_NET_WINDOW
        секунд, но не больше, чем подключений, и не меньше, чем соединений на одном пункте одного
        сервера (у каждого пункта свой вариант пароля, см. hy2_entries)."""
        nets: dict[int, set] = {}
        got = False
        if self._xray_stats_ready():
            code, text = await self._api("statsonlineiplist", "-all")
            data = self._json(text) if code == 0 else None
            if data is not None:
                got = True
                ips: dict[int, set] = {}
                for u in data.get("users") or []:
                    m = EMAIL_RE.match(str(u.get("email", "")))
                    if m:
                        ips.setdefault(int(m.group(1)), set()).update(
                            str(e.get("ip")) for e in u.get("ips") or [] if e.get("ip"))
                nets = {sid: {device_net(ip) or ip for ip in v} for sid, v in ips.items()}
        if self.hy2:
            answers = await self._hy2_all("/online")
            got = got or bool(answers)
            conns: dict[int, int] = {}   # подписка -> соединений всего
            same: dict[int, int] = {}    # подписка -> больше всего соединений на одном пункте одного сервера
            for data in answers:
                for ident, n in data.items():
                    m = HY2_ID_RE.fullmatch(str(ident))
                    if m:
                        uid, n = int(m.group(1)), int(n or 0)
                        conns[uid] = conns.get(uid, 0) + n
                        # Без варианта (старая подписка) все пункты на одном пароле — по ним не судим
                        if m.group(2):
                            same[uid] = max(same.get(uid, 0), n)
            now = time.time()
            for uid in list(self._hy2_nets):
                fresh = {k: t for k, t in self._hy2_nets[uid].items() if now - t < HY2_NET_WINDOW}
                if fresh:
                    self._hy2_nets[uid] = fresh
                else:
                    del self._hy2_nets[uid]
            for uid, n in conns.items():
                if n <= 0:
                    continue
                # Разные сети за последние минуты (не больше числа соединений) — и соединения одного
                # пункта: два телефона в одном Wi-Fi видны как одна сеть, но как два соединения.
                recent = [k for k, _ in sorted(self._hy2_nets.get(uid, {}).items(), key=lambda kv: -kv[1])[:n]]
                hy = set(recent)
                for i in range(len(hy), max(1, same.get(uid, 1))):
                    hy.add(f"hy2#{i}")  # адрес входа неизвестен (бот перезапускался) или одна сеть на двоих
                nets.setdefault(uid, set()).update(hy)
        return {sid: len(v) for sid, v in nets.items()} if got else None

    def add_location(self, code: str, name: str, proxy: str) -> None:
        code = code.lower()
        if not CODE_RE.match(code):
            raise ValueError("код страны: латиница и цифры, до 8 символов, например nl или us2")
        parse_proxy(proxy)  # проверка формата
        self.state["locations"] = [l for l in self.locations if l["code"] != code]
        self.state["locations"].append({"code": code, "name": name.strip(), "proxy": proxy.strip()})
        self._save()
        self.schedule_apply()

    def set_paid_location(self, code: str, name: str, pool: list[str], ms: int | None = None,
                          src: str = "webshare") -> str:
        """Страна из купленного списка (Webshare и т. п.): рабочий прокси и запасные.
        Возвращает added, swapped, kept или "" (код занят страной, добавленной вручную).
        Пока рабочий прокси жив, ничего не перезапускается; авто-страна с тем же кодом заменяется."""
        code = code.lower()
        if not CODE_RE.match(code) or not pool:
            raise ValueError("нужен код страны и хотя бы один прокси")
        for url in pool:
            parse_proxy(url)
        loc = next((l for l in self.locations if l["code"] == code), None)
        if loc and not loc.get("auto") and loc.get("src") != src:
            return ""
        if loc and loc.get("src") == src:
            loc.update(pool=list(pool), ms=ms)
            if loc["proxy"] in pool and not loc.get("down"):
                self._save()
                return "kept"
            loc.update(proxy=pool[0], down=False)
            self._save()
            self.schedule_apply()
            return "swapped"
        self.state["locations"] = [l for l in self.locations if l["code"] != code]
        # tcp_only: купленные списки обычно не обещают UDP, поэтому Hysteria этой страны
        # отправляет DNS с сервера, а остальной UDP отклоняет.
        self.state["locations"].append({"code": code, "name": name.strip(), "proxy": pool[0], "pool": list(pool),
                                        "src": src, "tcp_only": True, "ms": ms})
        self._save()
        self.schedule_apply()
        return "added"

    def paid_locations(self, src: str = "webshare") -> list[dict]:
        return [l for l in self.locations if l.get("src") == src]

    def remove_location(self, code: str, apply: bool = True) -> bool:
        keep = [l for l in self.locations if l["code"] != code.lower()]
        if len(keep) == len(self.locations) or not keep:
            return False
        self.state["locations"] = keep
        self._save()
        if apply:
            self.schedule_apply()
        return True

    def add_bridge(self, code: str, name: str, address: str, sni: str = "", ru: bool = False) -> None:
        """Мост: российский сервер, который пересылает порт 443 на этот сервер.
        ru: мост пересылает на отдельный вход с российским сайтом маскировки (порт BRIDGE_PORT).
        Так подключение к мосту выглядит как обращение к сайту из белого списка."""
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
                                      "port": int(port or 443), "sni": "" if ru else sni, "ru": bool(ru)})
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

    # ---------- мосты для белых списков ----------

    def ru_bridges(self) -> list[dict]:
        return [b for b in self.bridges if b.get("ru")]

    @property
    def bridge_site(self) -> str:
        return self.state.get("bridge_site", "")

    def set_bridge_site(self, site: str) -> None:
        if site != self.bridge_site:
            self.state["bridge_site"] = site
            self._save()
            self.schedule_apply()

    async def check_bridges(self) -> list[tuple[dict, bool]]:
        """Отвечает ли каждый мост: настоящее TLS-подключение через мост до этого сервера.
        Возвращает изменения (мост, работает_ли)."""
        import ssl

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE

        async def alive(b) -> bool:
            sni = self.bridge_site if b.get("ru") else (b["sni"] or self.sni)
            for _ in range(2):
                try:
                    _, w = await asyncio.wait_for(asyncio.open_connection(
                        b["host"], b["port"], ssl=ctx, server_hostname=sni or None), 8)
                    w.close()
                    return True
                except Exception:
                    await asyncio.sleep(1)
            return False

        # Без Xray вход для мостов (TCP) никто не слушает, а Hysteria через мост так не проверить.
        if not self.bridges or not self.xray_enabled:
            return []
        changes = []
        for b, ok in zip(list(self.bridges), await asyncio.gather(*(alive(b) for b in self.bridges))):
            if bool(b.get("down")) == ok:
                b["down"] = not ok
                changes.append((b, ok))
        if changes:
            self._save()
        return changes

    async def check_proxies(self) -> list[tuple[dict, bool]]:
        """Проверяет прокси стран, добавленных вручную: через каждый открывается настоящее
        HTTPS-подключение, так что ловится и истёкший логин, а не только закрытый порт.
        Свои страны админа (купленные и /addloc) из подписки не прячутся никогда (просьба владельца):
        бот только меняет прокси на живой запасной и сообщает админу. Возвращает изменения: (страна, работает_ли)."""
        manual = [l for l in self.locations if l["proxy"] and not l.get("auto")]
        if not manual or not await public_proxies.direct_ok():
            return []  # сервер сам не дошёл до проверочного сайта: прокси тут ни при чём

        async def alive(loc):
            return bool(await public_proxies.probe(loc["proxy"]) or await public_proxies.probe(loc["proxy"]))

        changes = []
        for loc, ok in zip(manual, await asyncio.gather(*(alive(l) for l in manual))):
            if not ok and len(loc.get("pool") or []) > 1:
                # Купленный список: сразу берём живой запасной из той же страны.
                for backup in [u for u in loc["pool"] if u != loc["proxy"]]:
                    if await alive({"proxy": backup}):
                        loc["pool"].remove(backup)
                        loc["pool"].insert(0, backup)
                        loc["proxy"], ok = backup, True
                        self.schedule_apply()
                        break
            if bool(loc.get("failing")) == ok:
                loc["failing"] = not ok
                changes.append((loc, ok))
        if changes:
            self._save()
        return changes

    # ---------- конфиг Xray ----------

    def _link(self, uid: str, host: str, port: int, sni: str, name: str, xhttp: bool = False) -> str:
        if xhttp:
            q = (f"encryption=none&security=reality&sni={sni}&fp=chrome&pbk={self.public_key}"
                 f"&sid={self.short_id}&type=xhttp&path={quote(self.xhttp_path, safe='')}&mode=auto")
        else:
            q = (f"encryption=none&flow=xtls-rprx-vision&security=reality&sni={sni}"
                 f"&fp=chrome&pbk={self.public_key}&sid={self.short_id}&type=tcp")
        return f"vless://{uid}@{host}:{port}?{q}#{quote(name)}"

    def _bridge_sni(self, b: dict) -> str:
        return self.bridge_site if b.get("ru") else (b["sni"] or self.sni)

    def visible_bridges(self) -> list[dict]:
        """Мост «ru» появляется в подписке, когда для него выбран сайт маскировки."""
        return [b for b in self.bridges if not b.get("ru") or self.bridge_site]

    # ---------- Hysteria2 ----------

    def hy2_password(self, user_id: int) -> str:
        token = hmac.new(self.state["secret"].encode(), f"hy2:{self._kid(user_id)}".encode(),
                         hashlib.sha256).hexdigest()[:20]
        return f"{user_id}.{token}"

    def hy2_check(self, password: str) -> int | None:
        """Пароль клиента Hysteria -> номер подписки, если доступ активен."""
        got = self.hy2_check_variant(password)
        return got[0] if got else None

    def hy2_check_variant(self, password: str) -> tuple[int, int] | None:
        """Пароль -> (подписка, вариант пункта). Вариант -1 — пароль без приписки (ссылки, старые подписки)."""
        parts = (password or "").split(".")
        variant = -1
        if len(parts) == 3 and parts[2].isdigit() and len(parts[2]) <= 3:
            variant = int(parts[2])
            password = ".".join(parts[:2])
        elif len(parts) != 2:
            return None
        uid = parts[0]
        if not uid.isdigit() or not hmac.compare_digest(self.hy2_password(int(uid)), password):
            return None
        return (int(uid), variant) if self.allowed(int(uid)) else None

    def _hy2_link(self, user_id: int, host: str, port: int, sni: str, name: str, obfs: bool = False) -> str:
        h = self.hy2
        q = f"sni={sni}&insecure=1"
        if h.get("pin"):
            q += f"&pinSHA256={h['pin']}"
        if obfs:
            q += f"&obfs=salamander&obfs-password={quote(h['obfs'], safe='')}"
        return f"hysteria2://{self.hy2_password(user_id)}@{host}:{port}/?{q}#{quote(name)}"

    def _stats_ports(self) -> list[int]:
        """Порты статистики всех серверов Hysteria: основных и серверов стран."""
        ports = list((self.hy2 or {}).get("stats_ports") or [])
        if self.hy2_locs:
            ports += [self._loc_stats_port(p) for p in sorted(self.state["hy2_ports"].values())]
        return ports

    def _loc_stats_port(self, port: int) -> int:
        return self.hy2_locs["stats_base"] + (port - self.hy2_locs["ports"].start)

    def hy2_loc_port(self, loc: dict) -> int | None:
        """UDP-порт сервера Hysteria этой страны. None — у страны его нет."""
        if not self.hy2_locs or not loc.get("proxy"):
            return None
        return self.state["hy2_ports"].get(loc["code"])

    def _hy2_loc_config(self, loc: dict, port: int) -> str:
        """Конфиг сервера Hysteria для страны: тот же сертификат и та же проверка паролей,
        а трафик выходит через прокси страны. JSON — частный случай YAML, Hysteria его читает."""
        d = self.hy2_locs["dir"]
        udp_ok = False
        if loc.get("auto"):
            # Авто-страна идёт через ретранслятор: он сам выбирает живой прокси, поэтому
            # замена прокси не перезапускает этот сервер.
            out = {"type": "socks5", "socks5": {"addr": f"127.0.0.1:{self.relay_port}",
                                               "username": loc["code"], "password": self.relay_password}}
        else:
            u = urlparse(loc["proxy"].strip())
            if u.scheme in ("socks5", "socks"):
                out = {"type": "socks5", "socks5": {"addr": f"{u.hostname}:{u.port}"}}
                if u.username:
                    out["socks5"].update(username=unquote(u.username), password=unquote(u.password or ""))
                udp_ok = not loc.get("tcp_only")
            else:
                out = {"type": "http", "http": {"url": loc["proxy"].strip()}}
        private = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
                   "100.64.0.0/10", "fc00::/7", "fe80::/10", "::1/128"]
        acl = [f"reject({c})" for c in private]
        if not udp_ok:
            # Публичные и HTTP-прокси UDP не пересылают: запросы DNS уходят с сервера,
            # остальной UDP отклоняется, и приложения сразу переходят на TCP.
            acl += ["direct(all, udp/53)", "reject(all, udp)"]
        cfg = {
            "listen": f":{port}",
            "tls": {"cert": f"{d}/hy2.crt", "key": f"{d}/hy2.key", "sniGuard": "disable"},
            "auth": {"type": "http", "http": {"url": f"http://127.0.0.1:{self.hy2_auth_port}/hy2auth"}},
            "trafficStats": {"listen": f"127.0.0.1:{self._loc_stats_port(port)}",
                             "secret": self.hy2.get("stats_secret", "")},
            "masquerade": {"type": "proxy", "proxy": {"url": f"https://{self.hy2.get('sni') or self.sni}/",
                                                      "rewriteHost": True}},
            "outbounds": [{"name": "out", **out}, {"name": "direct", "type": "direct"}],
            "acl": {"inline": acl + ["out(all)"]},
        }
        return json.dumps(cfg, indent=1, ensure_ascii=False)

    async def sync_hy2_locs(self) -> None:
        """У каждой страны с прокси — свой сервер Hysteria. Перезапускается только сервер той
        страны, у которой поменялись настройки; остальные и основная Hysteria не трогаются."""
        if not self.hy2_locs:
            return
        cfg, ports = self.hy2_locs, self.state["hy2_ports"]
        wanted = {l["code"]: l for l in self.locations if l.get("proxy")}
        changed = False
        for code in [c for c in ports if c not in wanted]:
            await self._run(*cfg["systemctl"], "disable", "--now", f"aurora-hy2@loc-{code}")
            path = os.path.join(cfg["dir"], f"hy2-loc-{code}.yaml")
            if os.path.exists(path):
                os.unlink(path)
            ports.pop(code)
            changed = True
        for code, loc in wanted.items():
            if code not in ports:
                free = next((p for p in cfg["ports"] if p not in ports.values()), None)
                if free is None:
                    log.warning("Hysteria: кончились порты %s, страна %s остаётся без Hysteria", cfg["ports"], code)
                    continue
                ports[code] = free
                changed = True
            text = self._hy2_loc_config(loc, ports[code])
            path = os.path.join(cfg["dir"], f"hy2-loc-{code}.yaml")
            try:
                with open(path, encoding="utf-8") as f:
                    if f.read() == text:
                        continue
            except OSError:
                pass
            try:
                os.makedirs(cfg["dir"], exist_ok=True)
                fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(path + ".tmp", path)
                unit = f"aurora-hy2@loc-{code}"
                await self._run(*cfg["systemctl"], "enable", unit)
                rc, out = await self._run(*cfg["systemctl"], "restart", unit)
            except OSError as e:
                rc, out = 1, str(e)
            if rc != 0:
                await self._problem(f"Hysteria для «{loc['name']}» не запустилась: {out[-300:].strip()}")
        if changed:
            self._save()

    @property
    def hy2_sni(self) -> str:
        """Сайт, под который маскируется Hysteria в ссылках. Бот меняет его раз в день."""
        return self.state.get("hy2_sni") or (self.hy2 or {}).get("sni") or self.sni

    # ---------- обход белых списков по имени сайта ----------

    BS_DEFAULT = "vk.com"
    # Ещё сайты для запасных пунктов «обход БС 2/3»: операторы держат в белых списках разные
    # наборы, и какой-то из них может пройти, когда первый не проходит.
    BS_EXTRA = ("ya.ru", "www.gosuslugi.ru")
    BS_MAX = 3

    @property
    def bs_site(self) -> str:
        return self.state.get("bs_site") or self.bridge_site or self.BS_DEFAULT

    @property
    def bs_sites(self) -> list[str]:
        """Сайты пунктов «обход БС»: первый — основной (/bs site), дальше запасные."""
        extra = self.state.get("bs_extra")
        if extra is None:
            extra = list(self.BS_EXTRA)
        return list(dict.fromkeys([self.bs_site, *extra]))[:self.BS_MAX]

    def bs_on(self) -> bool:
        """Пункт «· обход БС» в подписке: включён по умолчанию, но только если сервер Hysteria
        принимает любое имя сайта (иначе он отклонил бы подключение с российским именем)."""
        # 14.11 по умолчанию выключено: пользователь проверил — при белых списках не помогает
        return bool(self.hy2 and self.state.get("bs_on", False) and self.hy2_sni_rotatable())

    def set_bs(self, on: bool | None = None, site: str | None = None,
               sites: list[str] | None = None) -> None:
        """site — только основной сайт; sites — весь список (первый основной, остальные запасные)."""
        if on is not None:
            self.state["bs_on"] = bool(on)
        if site is not None:
            self.state["bs_site"] = site
        if sites:
            self.state["bs_site"], self.state["bs_extra"] = sites[0], list(sites[1:self.BS_MAX])
        self._save()

    def hy2_sni_rotatable(self) -> bool:
        """Менять сайт можно, только если сервер Hysteria принимает любое имя (sniGuard: disable):
        иначе ссылки с новым сайтом он бы отклонил. Такой конфиг пишет установщик этой версии."""
        path = os.path.join((self.hy2_locs or {}).get("dir", "/etc/aurora"), "hy2-plain.yaml")
        try:
            with open(path, encoding="utf-8") as f:
                return '"sniGuard": "disable"' in f.read()
        except OSError:
            return False

    def set_hy2_sni(self, site: str) -> str:
        """Новый сайт в ссылках Hysteria. Ничего не перезапускает: прежние ссылки тоже работают,
        приложения заберут новую подписку сами при ближайшем обновлении."""
        old = self.hy2_sni
        self.state["hy2_sni"], self.state["hy2_sni_changed"] = site, time.time()
        self._save()
        return old

    def hy2_entries(self, user_id: int) -> list[dict]:
        """Подключения Hysteria гостя по порядку: из них собираются и ссылки, и JSON-конфиги."""
        if not self.hy2:
            return []
        h, main = self.hy2, self.direct_location()["name"]
        sni = self.hy2_sni
        # Без Xray в подписке только Hysteria: приписка к названию не нужна, просто «Польша».
        tag = " · Hysteria" if self.xray_enabled else ""
        auth, pin = self.hy2_password(user_id), h.get("pin", "")

        # У каждого пункта, ведущего на тот же сервер Hysteria, свой вариант пароля («….1», «….2»):
        # «Лучший сервер» держит по соединению на каждый пункт, и без вариантов один телефон
        # выглядел бы как несколько устройств. С вариантами сервер считает соединения по каждому
        # пункту отдельно, и два соединения одного пункта — это точно два устройства.
        used: dict[int, int] = {}

        def e(host, port, site, name, obfs="", server_port=None):
            key = server_port or port
            k = used.get(key, 0)
            used[key] = k + 1
            return {"kind": "hy2", "name": name, "host": host, "port": port, "sni": site,
                    "auth": f"{auth}.{k}", "pin": pin, "obfs": obfs}
        out = []
        if h.get("port"):
            out.append(e(self.host, h["port"], sni, f"{main}{tag}"))
            # Обход белых списков без моста: то же подключение, но представляется российским сайтом
            # из белого списка. Помогает, если оператор пропускает по имени сайта, а не только по адресу.
            if self.bs_on():
                for i, site in enumerate(self.bs_sites):
                    out.append(e(self.host, h["port"], site, f"{main} · обход БС" + (f" {i + 1}" if i else "")))
        if h.get("obfs_port") and h.get("obfs"):
            out.append(e(self.host, h["obfs_port"], sni, f"{main} · Hysteria 2", h["obfs"]))
        # Страны через прокси: у каждой свой порт Hysteria, пароль тот же.
        def tg(host, port, site):
            """Telegram из стран через прокси — через основной сервер (см. client_config.TG_IPS)."""
            if not h.get("port"):
                return None
            x = e(host, port, site, "", server_port=h["port"])
            return {"host": x["host"], "port": x["port"], "auth": x["auth"], "sni": x["sni"]}

        for loc in self.locations:
            port = self.hy2_loc_port(loc)
            if port and not loc.get("down"):
                out.append({**e(self.host, port, sni, f"{loc['name']}{tag}"), "tg": tg(self.host, h.get("port"), sni)})
        # Мост «ru» пересылает и UDP 443: Hysteria через мост маскируется под российский сайт.
        # Порты стран (30000–30049) мост тоже пересылает, поэтому при белых списках через мост
        # доступны и страны: «🇩🇪 Германия · 🇷🇺 Обход».
        if h.get("port") and self.bridge_site:
            for b in self.visible_bridges():
                if not b.get("ru"):
                    continue
                out.append(e(b["host"], b["port"], self.bridge_site, f"{b['name']}{tag}", server_port=h["port"]))
                for loc in self.locations:
                    port = self.hy2_loc_port(loc)
                    if port and not loc.get("down"):
                        out.append({**e(b["host"], port, self.bridge_site, f"{loc['name']} · {b['name']}"),
                                    "tg": tg(b["host"], b["port"], self.bridge_site)})
        return out

    def hy2_links(self, user_id: int) -> list[str]:
        return [self._hy2_link(user_id, x["host"], x["port"], x["sni"], x["name"], obfs=bool(x["obfs"]))
                for x in self.hy2_entries(user_id)]

    def json_entries(self, user_id: int) -> list[dict]:
        """Подключения для JSON-конфигов: Hysteria и, если Xray включён, Reality по странам."""
        out = self.hy2_entries(user_id)
        if self.xray_enabled:
            out += [{"kind": "reality", "name": l["name"], "uid": self.user_uuid(user_id, l["code"]),
                     "host": self.host, "port": self.port, "sni": self.sni, "pbk": self.public_key,
                     "sid": self.short_id}
                    for l in self.locations if not l.get("down") and not (l.get("auto") and self.auto_rejected)]
        return out

    async def _hy2_auth(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Hysteria спрашивает при каждом подключении: POST {"addr", "auth", "tx"} -> {"ok", "id"}."""
        ok, uid = False, None
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            m = re.search(rb"(?i)\r\ncontent-length:\s*(\d+)", head)
            n = min(int(m.group(1)), 4096) if m else 0
            body = json.loads(await asyncio.wait_for(reader.readexactly(n), 5) or b"{}")
            got = self.hy2_check_variant(str(body.get("auth", "")))
            ok = got is not None
            uid, variant = got if got else (None, -1)
            if ok:
                net = device_net(str(body.get("addr", "")))
                if net:
                    self._hy2_nets.setdefault(uid, {})[net] = time.time()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                ConnectionError, ValueError, AttributeError):
            pass
        if ok:
            self.hy2_logins += 1
        data = json.dumps({"ok": ok, "id": hy2_id(uid, variant) if ok else ""}).encode()
        try:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                         + f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def start_hy2_auth(self) -> bool:
        if not self.hy2:
            return False
        try:
            self._hy2_server = await asyncio.start_server(self._hy2_auth, "127.0.0.1", self.hy2_auth_port)
        except OSError as e:
            await self._problem(f"Проверка паролей Hysteria не запустилась на порту {self.hy2_auth_port}: {e}")
            return False
        log.info("Пароли Hysteria проверяются на 127.0.0.1:%d", self.hy2_auth_port)
        return True

    def _hy2_stats(self, port: int, method: str, path: str, body=None):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": (self.hy2 or {}).get("stats_secret", ""),
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
        return json.loads(data) if data.strip() else {}

    async def hy2_kick(self, user_id: int) -> None:
        """Обрывает уже открытые сессии Hysteria у клиента, которому отключили доступ."""
        for port in self._stats_ports():
            try:
                await asyncio.to_thread(self._hy2_stats, port, "POST", "/kick",
                                        [hy2_id(user_id, k) for k in range(-1, HY2_VARIANTS)])
            except Exception as e:
                log.warning("Hysteria: не удалось отключить u%s: %s", user_id, e)

    async def hy2_online(self) -> int | None:
        total, seen = 0, False
        for port in self._stats_ports():
            try:
                data = await asyncio.to_thread(self._hy2_stats, port, "GET", "/online")
            except Exception:
                continue
            seen = True
            total += sum(int(v) for v in (data or {}).values())
        return total if seen else None

    async def hy2_running(self) -> bool:
        units = [u for u, key in (("aurora-hy2@plain", "port"), ("aurora-hy2@obfs", "obfs_port"))
                 if (self.hy2 or {}).get(key)]
        try:
            for unit in units:
                code, _ = await self._run("systemctl", "is-active", "--quiet", unit)
                if code != 0:
                    return False
        except OSError:
            return False
        return bool(units)

    def links(self, user_id: int) -> list[str]:
        shown = [l for l in self.locations if not l.get("down") and not (l.get("auto") and self.auto_rejected)]
        # Hysteria первой: приложения проверяют пинг сверху вниз, и она чаще проходит.
        out = self.hy2_links(user_id)
        if not self.xray_enabled:
            return out
        out += [self._link(self.user_uuid(user_id, loc["code"]), self.host, self.port, self.sni, loc["name"])
               for loc in shown]
        direct = self.user_uuid(user_id, self.direct_location()["code"])
        bridges = self.visible_bridges()
        out += [self._link(direct, b["host"], b["port"], self._bridge_sni(b), b["name"]) for b in bridges]
        if self.xhttp_on:
            # Запасной вид подключения для своих стран и мостов. Авто-странам он не нужен:
            # их публичные прокси и так медленные, а список в приложении не должен разрастаться.
            out += [self._link(self.user_uuid(user_id, loc["code"]), self.host, self.port, self.sni,
                               loc["name"] + " · запасной", xhttp=True)
                    for loc in shown if not loc.get("auto")]
            out += [self._link(direct, b["host"], b["port"], self._bridge_sni(b), b["name"] + " · запасной",
                               xhttp=True) for b in bridges]
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

    def _reality(self, site: str, names: list[str]) -> dict:
        return {"show": False, "dest": f"{site}:443", "xver": 0, "serverNames": names,
                "privateKey": self.private_key, "shortIds": [self.short_id]}

    def build_config(self, with_auto: bool = True, site: str | None = None, with_xhttp: bool | None = None) -> dict:
        if with_xhttp is None:
            with_xhttp = self.xhttp_on
        locations = [l for l in self.locations if with_auto or not l.get("auto")]
        direct_code = self.direct_location()["code"]
        now = time.time()
        active = [int(u) for u, exp in self.state["users"].items() if exp > now and not self.is_suspended(int(u))]
        clients, x_clients, b_clients = [], [], []
        for uid in active:
            for loc in locations:
                email, cid = f"u{uid}.{loc['code']}", self.user_uuid(uid, loc["code"])
                c = {"id": cid, "flow": "xtls-rprx-vision", "email": email}
                clients.append(c)
                if not loc.get("auto"):
                    x_clients.append({"id": cid, "email": email})  # XHTTP не работает с flow
                if loc["code"] == direct_code:
                    b_clients.append(dict(c))

        outbounds = [{"tag": "direct", "protocol": "freedom"},
                     {"tag": "block", "protocol": "blackhole"}]
        rules = [{"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
                 {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}]
        for loc in locations:
            if not loc["proxy"]:
                continue
            # Правило по шаблону имени клиента, а не по списку: новые клиенты попадают в свою
            # страну сразу, и при выдаче доступа правила менять не нужно.
            users = [f"regexp:^u[0-9]+\\.{loc['code']}$"]
            if loc.get("auto"):
                outbounds.append({"tag": f"out-{loc['code']}", **self.relay_outbound(loc["code"])})
                # Публичные прокси UDP не пересылают: запросы DNS уходят с самого сервера,
                # остальной UDP отклоняется, и приложения сразу переходят на TCP.
                rules.append({"type": "field", "user": users, "network": "udp", "port": "53",
                              "outboundTag": "direct"})
                rules.append({"type": "field", "user": users, "network": "udp", "outboundTag": "block"})
            else:
                outbounds.append({"tag": f"out-{loc['code']}", **parse_proxy(loc["proxy"])})
            rules.append({"type": "field", "user": users, "outboundTag": f"out-{loc['code']}"})

        sniffing = {"enabled": True, "destOverride": ["http", "tls", "quic"]}
        fallback = [{"dest": XHTTP_SOCKET}] if with_xhttp else []
        main_in = {
            "tag": "in", "listen": "0.0.0.0", "port": self.port, "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "streamSettings": {"network": "tcp", "security": "reality",
                               "realitySettings": self._reality(site or self.sni,
                                                                [site] if site else self.server_names())},
            "sniffing": sniffing,
        }
        if fallback:
            main_in["settings"]["fallbacks"] = fallback
        inbounds = [main_in]
        if self.ru_bridges() and self.bridge_site and not site:
            b_in = {
                "tag": "in-b", "listen": "0.0.0.0", "port": self.bridge_port, "protocol": "vless",
                "settings": {"clients": b_clients, "decryption": "none"},
                "streamSettings": {"network": "tcp", "security": "reality",
                                   "realitySettings": self._reality(self.bridge_site, [self.bridge_site])},
                "sniffing": sniffing,
            }
            if fallback:
                b_in["settings"]["fallbacks"] = fallback
            inbounds.append(b_in)
        if with_xhttp:
            inbounds.append({
                "tag": "in-x", "listen": XHTTP_SOCKET, "protocol": "vless",
                "settings": {"clients": x_clients, "decryption": "none"},
                "streamSettings": {"network": "xhttp", "xhttpSettings": {"path": self.xhttp_path}},
                "sniffing": sniffing,
            })
        return {
            "log": {"loglevel": "warning", "access": "none"},
            "api": {"tag": "api", "listen": f"127.0.0.1:{self.api_port}",
                    "services": ["HandlerService", "StatsService"]},
            # Счётчики по ключам: трафик подписок и адреса, с которых они подключены (лимит устройств).
            "stats": {},
            "policy": {"levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True,
                                        "statsUserOnline": True}}},
            "inbounds": inbounds,
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

    # ---------- изменения клиентов без перезапуска ----------

    @staticmethod
    def _shape(cfg: dict) -> str:
        """Конфиг без списков клиентов: если он не изменился, перезапуск не нужен."""
        c = copy.deepcopy(cfg)
        for ib in c["inbounds"]:
            ib["settings"].pop("clients", None)
        return json.dumps(c, sort_keys=True)

    @staticmethod
    def _clients(cfg: dict) -> dict[str, dict[str, dict]]:
        return {ib["tag"]: {c["email"]: c for c in ib["settings"].get("clients", [])}
                for ib in cfg["inbounds"] if "clients" in ib["settings"]}

    async def _api(self, cmd: str, *args) -> tuple[int, str]:
        return await self._run(self.xray_bin, "api", cmd, f"--server=127.0.0.1:{self.api_port}", *args)

    async def _hot_update(self, cfg: dict) -> bool:
        """Добавляет и убирает клиентов в работающем Xray. False — нужен обычный перезапуск."""
        if self._live is None or self._shape(cfg) != self._live_shape:
            return False
        want = self._clients(cfg)
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".users.json"
        changed = False
        try:
            for tag, clients in want.items():
                have = self._live.get(tag, {})
                gone = [e for e, c in have.items() if clients.get(e) != c]
                new = [c for e, c in clients.items() if have.get(e) != c]
                for i in range(0, len(gone), API_CHUNK):
                    code, out = await self._api("rmu", f"-tag={tag}", *gone[i:i + API_CHUNK])
                    if code != 0:
                        log.warning("API Xray не убрал клиентов: %s", out[-300:])
                        return False
                for i in range(0, len(new), API_CHUNK):
                    part = new[i:i + API_CHUNK]
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump({"inbounds": [{"tag": tag, "port": 1, "protocol": "vless",
                                                 "settings": {"clients": part, "decryption": "none"}}]}, f)
                    code, out = await self._api("adu", tmp)
                    m = re.search(r"Added (\d+) user", out)
                    if code != 0 or not m or int(m.group(1)) != len(part):
                        log.warning("API Xray не добавил клиентов: %s", out[-300:])
                        return False
                changed = changed or bool(gone or new)
                self._live[tag] = dict(clients)
        except OSError as e:
            log.warning("API Xray недоступен: %s", e)
            return False
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        # Файл конфига тоже обновляем: после перезагрузки сервера Xray поднимется с теми же клиентами.
        nxt = base + ".next.json"
        with open(nxt, "w", encoding="utf-8") as f:
            f.write(json.dumps(cfg, ensure_ascii=False, indent=1))
        os.chmod(nxt, 0o644)
        os.replace(nxt, self.config_path)
        if changed:
            self.hot_updates += 1
            log.info("Xray: клиенты обновлены без перезапуска (%d)", len(self.state["users"]))
        return True

    async def apply(self) -> bool:
        """Применяет состояние: сначала Xray, затем серверы Hysteria для стран."""
        ok = await self._apply_xray()
        try:
            await self.sync_hy2_locs()
        except Exception:
            log.exception("Hysteria для стран: сбой")
        return ok

    async def _apply_xray(self) -> bool:
        """Применяет состояние к Xray. Если поменялись только клиенты, они меняются через API
        на лету. Иначе новый конфиг проверяется самим Xray и только потом Xray перезапускается.
        Если Xray не принимает запасной вход или авто-страны, применяется конфиг без них:
        основная страна, купленные прокси и новые клиенты не должны от них зависеть."""
        # Xray определяет формат по расширению, поэтому временный файл тоже .json
        if not self.xray_enabled:  # VPN только через Hysteria: ей перезапуск не нужен никогда
            self.last_apply, self.last_error = time.time(), ""
            return True
        base = self.config_path[:-5] if self.config_path.endswith(".json") else self.config_path
        tmp = base + ".next.json"
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        if not os.path.exists(self.xray_bin):
            await self._problem(f"Xray не найден: {self.xray_bin}. Конфиг не применён.")
            return False
        has_auto = bool(self.auto_locations())
        if self._live is not None:
            flags = (self._live_flags[0] or not has_auto, self._live_flags[1] and self.xhttp_enabled)
            if await self._hot_update(self.build_config(flags[0], with_xhttp=flags[1])):
                self.last_apply = time.time()
                self.auto_rejected = has_auto and not flags[0]
                if not self.auto_rejected and not self.xhttp_off:
                    self.last_error = ""
                return True
        variants = [(a, x) for a in ((True, False) if has_auto else (True,))
                    for x in ((True, False) if self.xhttp_enabled else (False,))]
        rejected = {}
        for with_auto, with_xhttp in variants:
            cfg = self.build_config(with_auto, with_xhttp=with_xhttp)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(cfg, ensure_ascii=False, indent=1))
            os.chmod(tmp, 0o644)
            code, out = await self._run(self.xray_bin, "run", "-test", "-c", tmp)
            if code == 0:
                break
            rejected.setdefault((with_auto, with_xhttp), out[-700:].strip())
            log.error("Xray отклонил конфиг (авто-страны: %s, запасной вход: %s):\n%s",
                      with_auto and has_auto, with_xhttp, out[-1500:])
        else:
            first = next(iter(rejected.values()), "")
            await self._problem("Xray отклонил конфиг, оставляю прежний:\n" + first)
            return False
        os.replace(tmp, self.config_path)
        code, out = await self._run(*self.restart_cmd)
        if code != 0:
            self._live = None
            await self._problem("Не удалось перезапустить Xray: " + out[-500:].strip())
            return False
        self.restarts += 1
        self._live, self._live_shape = self._clients(cfg), self._shape(cfg)
        self._live_flags = (with_auto, with_xhttp)
        self.last_apply = time.time()
        self.auto_rejected = has_auto and not with_auto
        self.xhttp_off = self.xhttp_enabled and not with_xhttp
        log.info("Xray перезапущен: %d клиентов, стран: %d", len(self.state["users"]), len(self.locations))
        problems = []
        if self.xhttp_off:
            problems.append("Xray не принял запасной вход XHTTP, поэтому он отключён. Основное подключение "
                            "работает. Обновите Xray: запустите установщик ещё раз.\n"
                            + rejected.get((with_auto, True), ""))
        if self.auto_rejected:
            problems.append("Xray не принял настройки авто-стран, поэтому они отключены и скрыты "
                            "из подписки. Остальные страны работают.\n"
                            + rejected.get((True, with_xhttp), ""))
        if problems:
            await self._problem("\n\n".join(problems))
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

    @property
    def json_sub(self) -> bool:
        """Отдавать ли Happ и v2rayNG готовые JSON-конфиги. Переключается из /admin."""
        return bool(self.state.get("json_sub", self.json_default))

    # ---------- устройства по номеру (HWID) ----------

    def device_seen(self, user_id: int, hwid: str, model: str = "", os_: str = "") -> bool:
        """Устройство обновляет подписку. True — пускаем; False — оплаченные места заняты другими
        устройствами, и это получает вместо стран заглушку «Превышен лимит устройств»."""
        hwid = (hwid or "").strip()[:128]
        if not hwid:
            return True  # приложение не сообщает номер (v2rayNG) — проверка по подключениям (devices.py)
        now = time.time()
        mine = self.state.setdefault("hwids", {}).setdefault(str(user_id), {})
        for h in [h for h, d in mine.items() if now - d.get("t", 0) > HWID_TTL]:
            del mine[h]
        if hwid in mine:
            if now - mine[hwid].get("t", 0) > 3600:  # не пишем файл на каждое обновление
                mine[hwid]["t"] = now
                self._save()
            return True
        limit = int(self.state["devices"].get(str(user_id)) or 0)
        if limit and len(mine) >= limit:
            return False
        mine[hwid] = {"t": now, "m": (model or "").strip()[:60], "os": (os_ or "").strip()[:30]}
        self._save()
        return True

    def device_list(self, user_id: int) -> list[dict]:
        """Устройства подписки, свежие сверху: [{"id": короткий номер, "m": модель, "os", "t"}]."""
        mine = self.state.get("hwids", {}).get(str(user_id), {})
        out = [{"id": hashlib.sha1(h.encode()).hexdigest()[:8], **d} for h, d in mine.items()]
        return sorted(out, key=lambda d: -d.get("t", 0))

    def forget_device(self, user_id: int, short_id: str) -> bool:
        mine = self.state.get("hwids", {}).get(str(user_id), {})
        for h in list(mine):
            if hashlib.sha1(h.encode()).hexdigest()[:8] == short_id:
                del mine[h]
                self._save()
                return True
        return False

    def _limit_body(self, as_json: bool) -> bytes:
        """Вместо стран — неработающий пункт с объяснением (как у крупных VPN)."""
        if as_json:
            cfgs = [client_config._base(LIMIT_NAME, [{"tag": "proxy", "protocol": "blackhole"}], {"rules": []}),
                    client_config._base("👉 Освободите место в боте: подписка → 📱 Устройства",
                                        [{"tag": "proxy", "protocol": "blackhole"}], {"rules": []})]
            return json.dumps(cfgs, ensure_ascii=False).encode()
        links = [f"hysteria2://limit@127.0.0.1:1/?insecure=1#{quote(LIMIT_NAME)}",
                 f"hysteria2://limit@127.0.0.1:1/?insecure=1#{quote('👉 Освободите место в боте')}"]
        return base64.b64encode("\n".join(links).encode())

    def subscription(self, user_id: int, as_json: bool = False, tuned: bool = False,
                     enc_path: str = "", over_limit: bool = False) -> tuple[bytes, dict] | None:
        """Подписка. as_json — готовые конфиги Xray для Happ и v2rayNG: в приложении видно только
        название страны, а адрес и пароль спрятаны внутри конфига; российские сайты идут напрямую.
        over_limit — устройство сверх оплаченных: вместо стран заглушка."""
        exp = self.state["users"].get(str(user_id))
        if not exp or exp <= time.time():
            return None
        if over_limit:
            body = self._limit_body(as_json)
        elif as_json:
            body = json.dumps(client_config.configs(self.json_entries(user_id), tuned=tuned),
                              ensure_ascii=False).encode()
        else:
            body = base64.b64encode("\n".join(self.links(user_id)).encode())
        if enc_path:  # своё приложение: тело зашифровано, адресов и паролей в ответе не видно
            body = client_config.encrypt_sub(body, enc_path)
        # Название подписки с числом устройств: «Arise VPN · 2 устройства» (приложение Arise
        # показывает это рядом со сроком и кнопкой «Продлить»)
        n = int(self.state["devices"].get(str(user_id)) or 1)
        word = "устройство" if n % 10 == 1 and n % 100 != 11 else (
            "устройства" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "устройств")
        title = base64.b64encode((f"{self.brand} · превышен лимит устройств" if over_limit
                                  else f"{self.brand} · {n} {word}").encode()).decode()
        up = down = 0
        if self.usage:
            try:
                up, down = self.usage(user_id)
            except Exception:
                log.exception("трафик для подписки %s", user_id)
        headers = {
            "Content-Type": ("application/json" if as_json and not enc_path else "text/plain") + "; charset=utf-8",
            "profile-title": f"base64:{title}",
            "subscription-userinfo": f"upload={int(up)}; download={int(down)}; total=0; expire={int(exp)}",
            "profile-update-interval": "1",
        }
        if self.support_url:
            # кнопки «Поддержка» и «Сайт» в карточке подписки (Aurora, v2rayNG, Happ) ведут в бота
            headers["support-url"] = self.support_url
            headers["profile-web-page-url"] = self.support_url
        return body, headers

    MINIAPP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "index.html")

    def miniapp_url(self) -> str:
        """Мини-приложение Telegram с нашего сервера (нужен HTTPS на своём домене). GitHub Pages
        (*.github.io) в России часто режут — Telegram показывал «ERR_CONNECTION_CLOSED»."""
        if self.sub_domain and self.sub_cert and self.sub_https is not False and os.path.exists(self.MINIAPP_FILE):
            port = "" if self.sub_tls_port == 443 else f":{self.sub_tls_port}"
            return f"https://{self.sub_domain}{port}/m/"
        return ""

    def app_link(self, user_id: int) -> str:
        """Ссылка на страницу, которая одним касанием добавляет подписку в приложение Arise VPN."""
        return self.sub_url(user_id) + "/app"

    def app_deeplink(self, user_id: int) -> str:
        # aurora://install-sub — обработчик ссылок v2rayNG: добавляет подписку и сразу её обновляет
        return f"aurora://install-sub?url={quote(self.sub_url(user_id), safe='')}#{quote(self.brand)}"

    def app_page(self, user_id: int) -> str:
        """Страница «Подключить в один клик». Telegram не открывает в кнопках ссылки приложений
        (aurora://, happ://), поэтому кнопка в боте ведёт сюда, а здесь — кнопки под каждое приложение.
        Сама страница ничего не открывает: иначе подписка импортировалась бы дважды."""
        import html as _html
        url = self.sub_url(user_id)
        q, name = quote(url, safe=""), quote(self.brand)
        brand = _html.escape(self.brand)
        # (название, ссылка, для каких систем: a — Android, i — iPhone/Mac, w — Windows, * — все)
        apps = [
            (self.brand, self.app_deeplink(user_id), "a", True),
            ("Happ", f"happ://add/{url}", "*", False),
            ("Hiddify", f"hiddify://import/{url}#{name}", "*", False),
            ("v2rayNG", f"v2rayng://install-sub?url={q}#{name}", "a", False),
            ("Streisand", f"streisand://import/{url}#{name}", "i", False),
        ]
        buttons = "".join(
            f"<a class='b{' main' if main else ''}' data-os='{os_}' href='{_html.escape(link)}'>"
            f"Добавить в {_html.escape(title)}</a>" for title, link, os_, main in apps)
        return ("<!doctype html><html lang=ru><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>{brand}</title><style>"
                ":root{color-scheme:dark}"
                "body{margin:0;min-height:100vh;background:radial-gradient(120% 60% at 50% 0,#12224a 0,#05070d 60%);"
                "color:#e3ecff;font:16px/1.5 system-ui,sans-serif}"
                "main{padding:28px 18px 40px;max-width:440px;margin:0 auto}"
                "h1{font-size:26px;color:#7aaeff;margin:0 0 4px;text-align:center}"
                ".lead{color:#97a3bd;text-align:center;margin:0 0 22px}"
                "a.b{display:block;margin:10px 0;padding:15px;border-radius:14px;background:#111a2e;"
                "border:1px solid #23314f;color:#e3ecff;font-weight:600;text-decoration:none;text-align:center}"
                "a.main{background:#7aaeff;color:#03050b;border-color:#7aaeff}"
                "button{width:100%;margin:10px 0;padding:14px;border-radius:14px;border:1px dashed #3a4c74;"
                "background:transparent;color:#97a3bd;font:inherit;cursor:pointer}"
                "h2{font-size:15px;color:#7aaeff;margin:26px 0 6px}ol{padding-left:20px;margin:0;color:#c3cde2}"
                "li{margin:6px 0}small{color:#6f7b95}a{color:#7aaeff}"
                f"</style></head><body><main><h1>{brand}</h1>"
                "<p class=lead>Подключение в одно касание</p>"
                f"{buttons}"
                "<button id=copy>📋 Скопировать ссылку подписки</button>"
                "<h2>Как это работает</h2><ol>"
                "<li>Если приложения ещё нет — установите его (ссылки ниже).</li>"
                "<li>Нажмите «Добавить в …» с названием своего приложения: подписка добавится сама.</li>"
                "<li>В приложении выберите «🚀 Лучший сервер» и включите VPN.</li></ol>"
                "<h2>Где взять приложение</h2><ol>"
                "<li>Android: наше приложение присылает бот (кнопка «📥 Скачать приложение»), "
                "или Happ / v2rayNG из Google Play.</li>"
                "<li>iPhone, iPad, Mac: Happ или Streisand из App Store.</li>"
                "<li>Windows: <a href='https://www.happ.su/'>Happ</a> или "
                "<a href='https://github.com/hiddify/hiddify-app/releases/latest'>Hiddify</a>.</li></ol>"
                "<p><small>Кнопка не сработала? Скопируйте ссылку и в приложении нажмите «+» → "
                "«Из буфера обмена».</small></p>"
                "</main><script>"
                "var u=navigator.userAgent,os=/android/i.test(u)?'a':/iphone|ipad|mac/i.test(u)?'i':/windows/i.test(u)?'w':'';"
                "if(os)document.querySelectorAll('a.b').forEach(function(a){var o=a.dataset.os;"
                "if(o!=='*'&&o.indexOf(os)<0)a.style.display='none'});"
                f"var link={json.dumps(url)};"
                "document.getElementById('copy').onclick=function(){var b=this;"
                "(navigator.clipboard?navigator.clipboard.writeText(link):Promise.reject()).then(function(){"
                "b.textContent='✅ Скопировано'},function(){prompt('Скопируйте ссылку:',link)})};"
                "</script></body></html>")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        ip = str(peer[0]) if isinstance(peer, tuple) and peer else ""
        if not self.guard.enter(ip):  # флуд или адрес в бане: молча закрываем
            writer.close()
            return
        try:
            await self._serve(reader, writer, ip)
        finally:
            self.guard.leave(ip)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, ip: str) -> None:
        status, body, headers = "404 Not Found", b"not found", {"Content-Type": "text/plain"}
        file_path = ""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10  # на весь запрос 10 с: медленные «атаки по строчке» не держат соединения

        def left() -> float:
            return max(0.05, deadline - loop.time())
        try:
            line = await asyncio.wait_for(reader.readline(), left())
            agent = ""
            clen = 0  # длина тела POST (чат)
            dev: dict[str, str] = {}  # номер и модель устройства (Happ и наши приложения их шлют)
            for _ in range(50):  # заголовки запроса: User-Agent и сведения об устройстве
                h = await asyncio.wait_for(reader.readline(), left())
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode(errors="replace").partition(":")
                k = k.strip().lower()
                if k == "user-agent":
                    agent = v.strip()
                elif k in ("x-hwid", "x-device-model", "x-device-os"):
                    dev[k] = v.strip()
                elif k == "content-length" and v.strip().isdigit():
                    clen = int(v.strip())
            parts = line.decode(errors="replace").split()
            path, _, query = (parts[1] if len(parts) >= 2 else "").partition("?")
            fmt = parse_qs(query).get("format", [""])[0]
            as_json = fmt == "json" or (fmt != "links" and self.json_sub and client_config.wants_json(agent))
            uid = None
            app_page = path.endswith("/app")  # страница «Открыть в Arise VPN» для этой подписки
            if app_page:
                path = path[:-4]
            chat = ""  # /chat/<действие> — зашифрованный чат приложения
            if "/chat/" in path:
                path, _, chat = path.partition("/chat/")
            update = ""  # /update — какая версия приложения последняя, /apk — сам файл
            for tail in ("/update", "/apk"):
                if path.endswith(tail):
                    update, path = tail, path[:-len(tail)]
            m = re.fullmatch(r"/sub/(\d+)/([0-9a-f]{24})", path)
            if m and hmac.compare_digest(m.group(2), self.sub_token(int(m.group(1)))):
                uid = int(m.group(1))
            m = re.fullmatch(r"/([0-9A-Za-z]{16})", path)
            if m:
                uid = self._by_short(m.group(1))
            if fmt not in ("links", "json") and client_config.is_browser(agent):
                app_page = True  # в браузере — страница вместо ключей
            if parts and parts[0] in ("GET", "POST") and uid is not None and chat:
                body_in = b""
                if parts[0] == "POST":
                    if clen > 64 * 1024:
                        raise ValueError("слишком большое тело")
                    body_in = await asyncio.wait_for(reader.readexactly(clen), left()) if clen else b""
                if self.state["users"].get(str(uid), 0) > time.time():
                    code, answer = self.chat.handle(uid, chat, parts[0], parse_qs(query), body_in)
                else:
                    code, answer = 403, {"error": "subscription expired"}
                status = {200: "200 OK", 400: "400 Bad Request", 403: "403 Forbidden", 404: "404 Not Found",
                          409: "409 Conflict", 429: "429 Too Many Requests", 507: "507 Insufficient Storage"
                          }.get(code, f"{code} Error")
                body = json.dumps(answer).encode()
                headers = {"Content-Type": "application/json", "Cache-Control": "no-store"}
                if code == 404:
                    status = "200 OK"  # «нет такого кода» — не повод банить адрес (guard считает 404)
                    body = json.dumps({**answer, "status": 404}).encode()
            elif parts and parts[0] == "GET" and uid is not None and update:
                status, body, headers, file_path = self._app_update(uid, update, parse_qs(query))
            elif parts and parts[0] == "GET" and uid is not None and app_page:
                status, body = "200 OK", self.app_page(uid).encode()
                headers = {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
            elif parts and parts[0] == "GET" and uid is not None:
                tuned = as_json and client_config.is_aurora(agent)
                ok = self.device_seen(uid, dev.get("x-hwid", ""), dev.get("x-device-model", ""),
                                      dev.get("x-device-os", ""))
                res = self.subscription(uid, as_json=as_json, tuned=tuned, over_limit=not ok,
                                        enc_path=path if tuned and client_config.wants_encrypted(agent) else "")
                if res:
                    status, (body, headers) = "200 OK", res
                else:
                    status, body = "403 Forbidden", b"subscription expired"
            elif path in ("/m", "/m/") and parts and parts[0] == "GET" and os.path.exists(self.MINIAPP_FILE):
                status, headers, file_path = "200 OK", {"Content-Type": "text/html; charset=utf-8",
                                                        "Cache-Control": "no-cache"}, self.MINIAPP_FILE
            elif path == "/" and parts and parts[0] in ("GET", "HEAD"):
                # корень выглядит как обычная страница, а не как VPN
                status, body = "200 OK", (f"<!doctype html><title>{self.brand}</title>"
                                          f"<h1>{self.brand}</h1>").encode()
                headers = {"Content-Type": "text/html; charset=utf-8"}
        except (asyncio.TimeoutError, ConnectionError, UnicodeError, OSError, ValueError,
                asyncio.IncompleteReadError):
            pass
        if status.startswith("404"):
            self.guard.fail(ip)  # неверная ссылка или сканер: за перебор — бан на час
        size = len(body)
        if file_path:
            try:
                size = os.path.getsize(file_path)
            except OSError:
                file_path, status, body, size = "", "404 Not Found", b"not found", 9
        head = f"HTTP/1.1 {status}\r\nContent-Length: {size}\r\nConnection: close\r\n"
        head += "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        try:
            writer.write(head.encode() + b"\r\n" + (b"" if file_path else body))
            await writer.drain()
            if file_path:  # APK — частями, чтобы не держать весь файл в памяти
                with open(file_path, "rb") as f:
                    while chunk := f.read(256 * 1024):
                        writer.write(chunk)
                        await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    def _app_update(self, uid: int, what: str, query: dict) -> tuple[str, bytes, dict, str]:
        """Обновление приложения изнутри: /update — JSON с последней версией, /apk — файл.
        Файл идёт с нашего сервера по адресу подписки: так он доходит, даже если GitHub не открывается."""
        app = (query.get("app") or ["aurora"])[0]
        rel = self.app_releases.get(app)
        got = rel.cached() if rel else None
        if what == "/apk":
            if not got:
                return "503 Service Unavailable", b"no app yet", {"Content-Type": "text/plain"}, ""
            return "200 OK", b"", {"Content-Type": "application/vnd.android.package-archive",
                                   "Content-Disposition": f"attachment; filename={os.path.basename(got[1])}",
                                   "Cache-Control": "no-store"}, got[1]
        info = {"app": app, "version": "", "code": 0}
        if got:
            from android_app import version_code
            try:
                size = os.path.getsize(got[1])
            except OSError:
                size = 0
            info.update(version=got[0], code=version_code(got[0]), size=size,
                        url=f"{self.sub_url(uid)}/apk?app={app}", mirror=getattr(rel, "url", ""))
        return "200 OK", json.dumps(info).encode(), {"Content-Type": "application/json",
                                                      "Cache-Control": "no-store"}, ""

    async def start_sub_server(self, host: str = "0.0.0.0") -> None:
        self._server = await asyncio.start_server(self._handle, host, self.sub_port)
        log.info("Подписки раздаются на порту %d", self.sub_port)
        if self.sub_domain and self.sub_cert:
            await self.start_https(host)

    async def start_https(self, host: str = "0.0.0.0") -> bool:
        """HTTPS-раздача на своём домене с сертификатом Let's Encrypt."""
        import ssl
        try:
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(self.sub_cert, self.sub_key)
            self._tls_server = await asyncio.start_server(self._handle, host, self.sub_tls_port, ssl=ctx,
                                                          ssl_handshake_timeout=10)
        except (OSError, ssl.SSLError) as e:
            self.sub_https = False
            await self._problem(f"Подписка по HTTPS на {self.sub_domain}:{self.sub_tls_port} не запустилась: {e}. "
                                "Клиенты получают ссылки по HTTP.")
            return False
        self.sub_https = True
        log.info("Подписки раздаются по HTTPS: %s:%d", self.sub_domain, self.sub_tls_port)
        return True


def hy2_locs_from_env(e) -> dict | None:
    """UDP-порты серверов Hysteria для стран через прокси, например 30000-30049. 0 — выключено."""
    m = re.fullmatch(r"(\d+)-(\d+)", e.get("HY2_LOC_PORTS", "30000-30049").strip())
    if not m or int(m.group(1)) > int(m.group(2)):
        return None
    return {"ports": range(int(m.group(1)), int(m.group(2)) + 1), "dir": e.get("HY2_DIR", "/etc/aurora"),
            "stats_base": int(e.get("HY2_LOC_STATS_BASE", "20830")), "systemctl": ("systemctl",)}


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
        brand=e.get("BRAND", "Arise VPN"), default_location=e.get("DEFAULT_LOCATION_NAME", "🌍 Основной"),
        auto_enabled=e.get("AUTO_PROXY", "0") == "1",
        auto_countries=[c.strip().lower() for c in e.get("AUTO_PROXY_COUNTRIES", "").replace(" ", "").split(",") if c.strip()],
        auto_max=int(e.get("AUTO_PROXY_MAX", "15")),
        relay_port=int(e.get("AUTO_RELAY_PORT", "20808")),
        api_port=int(e.get("XRAY_API_PORT", "10085")),
        bridge_port=int(e.get("BRIDGE_PORT", "8444")),
        xhttp=e.get("XHTTP", "1") == "1",
        sub_base=e.get("SUB_URL", ""),
        hy2={"port": int(e.get("HY2_PORT") or 0), "sni": e.get("HY2_SNI", ""), "pin": e.get("HY2_PIN", ""),
             # Второй вариант Hysteria (с обфускацией) выключен, пока не задано HY2_OBFS_ON=1:
             # в подписке остаётся одна Hysteria.
             "obfs": e.get("HY2_OBFS", ""),
             "obfs_port": int(e.get("HY2_OBFS_PORT") or 0) if e.get("HY2_OBFS_ON", "0") == "1" else 0,
             "stats_ports": [int(p) for p in e.get("HY2_STATS_PORTS", "").split(",") if p.strip().isdigit()],
             "stats_secret": e.get("HY2_STATS_SECRET", "")} if e.get("HY2_PORT") or e.get("HY2_OBFS_PORT") else None,
        hy2_auth_port=int(e.get("HY2_AUTH_PORT", "20809")),
        hy2_locs=hy2_locs_from_env(e),
        json_sub=e.get("SUB_JSON", "1") == "1",
        xray_enabled=e.get("XRAY_ENABLED", "1") == "1",
        sub_domain=e.get("SUB_DOMAIN", ""),
        sub_tls_port=int(e.get("SUB_TLS_PORT") or (443 if e.get("XRAY_ENABLED", "1") == "0" else 2053)),
        sub_cert=e.get("SUB_CERT", ""), sub_key=e.get("SUB_KEY", ""),
    )
