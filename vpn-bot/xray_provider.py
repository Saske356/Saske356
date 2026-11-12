"""Настоящий VPN на Xray: один вход VLESS Reality на 443 и выход через прокси других стран.

Каждый клиент получает отдельный ключ под каждую страну. Сервер по ключу понимает,
через какую страну выпустить трафик: напрямую (страна самого сервера) или через прокси.
Клиенту выдаётся одна ссылка-подписка, в приложении она превращается в список стран.

Клиенты добавляются и убираются через API Xray на лету: выдача и отключение доступа не
перезапускают Xray и не рвут подключения остальных. Перезапуск нужен только при смене
стран, мостов или сайта маскировки.

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
from urllib.parse import quote, unquote, urlparse

import public_proxies
from vpn import VpnProvider

log = logging.getLogger("vpn-bot.xray")

CODE_RE = re.compile(r"^[a-z0-9]{1,8}$")
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


class XrayProvider(VpnProvider):
    is_demo = False

    def __init__(self, *, state_path: str, config_path: str, xray_bin: str, public_host: str,
                 port: int, sni: str, private_key: str, public_key: str, short_id: str,
                 sub_port: int, brand: str = "VPN", default_location: str = "🌍 Основной",
                 restart_cmd: tuple = ("systemctl", "restart", "xray"),
                 auto_enabled: bool = False, auto_countries: tuple = (), auto_max: int = 8,
                 relay_port: int = 20808, api_port: int = 10085, bridge_port: int = 8444,
                 xhttp: bool = True, sub_base: str = ""):
        self.state_path, self.config_path, self.xray_bin = state_path, config_path, xray_bin
        self.host, self.port, self.env_sni = public_host, port, sni
        self.private_key, self.public_key, self.short_id = private_key, public_key, short_id
        self.sub_port, self.brand, self.restart_cmd = sub_port, brand, restart_cmd
        self.relay_port, self.api_port, self.bridge_port = relay_port, api_port, bridge_port
        self.xhttp_enabled = xhttp
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
        # SUB_URL: свой адрес раздачи, например домен за Cloudflare, если оператор режет порт подписки
        base = self.sub_base or f"http://{self.host}:{self.sub_port}"
        return f"{base}/sub/{user_id}/{self.sub_token(user_id)}"

    @property
    def xhttp_path(self) -> str:
        return "/" + hmac.new(self.state["secret"].encode(), b"xhttp", hashlib.sha256).hexdigest()[:12]

    @property
    def xhttp_on(self) -> bool:
        return self.xhttp_enabled and not self.xhttp_off

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

        if not self.bridges:
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

    def links(self, user_id: int) -> list[str]:
        shown = [l for l in self.locations if not l.get("down") and not (l.get("auto") and self.auto_rejected)]
        out = [self._link(self.user_uuid(user_id, loc["code"]), self.host, self.port, self.sni, loc["name"])
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
        active = [int(u) for u, exp in self.state["users"].items() if exp > now]
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
            "api": {"tag": "api", "listen": f"127.0.0.1:{self.api_port}", "services": ["HandlerService"]},
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
        """Применяет состояние к Xray. Если поменялись только клиенты, они меняются через API
        на лету. Иначе новый конфиг проверяется самим Xray и только потом Xray перезапускается.
        Если Xray не принимает запасной вход или авто-страны, применяется конфиг без них:
        основная страна, купленные прокси и новые клиенты не должны от них зависеть."""
        # Xray определяет формат по расширению, поэтому временный файл тоже .json
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
        api_port=int(e.get("XRAY_API_PORT", "10085")),
        bridge_port=int(e.get("BRIDGE_PORT", "8444")),
        xhttp=e.get("XHTTP", "1") == "1",
        sub_base=e.get("SUB_URL", ""),
    )
