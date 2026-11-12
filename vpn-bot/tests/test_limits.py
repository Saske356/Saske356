"""Лимит устройств, трафик и временное отключение подписки: python3 -m unittest discover -s tests

Xray и Hysteria заменены заглушками: ответы API Xray подставляются напрямую, а статистику
Hysteria отдаёт маленький HTTP-сервер с тем же заголовком Authorization.
"""

import asyncio, json, os, sys, tempfile, time, unittest
from unittest.mock import AsyncMock
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xray_provider as xp  # noqa: E402
from devices import DeviceGuard  # noqa: E402


class FakeHysteriaStats:
    def __init__(self, secret="statsec"):
        self.secret, self.traffic, self.online, self.kicked = secret, {}, {}, []

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def handle(self, reader, writer):
        line = (await reader.readline()).decode()
        headers = {}
        while (h := await reader.readline()) not in (b"\r\n", b""):
            k, _, v = h.decode().partition(":")
            headers[k.strip().lower()] = v.strip()
        body = await reader.readexactly(int(headers.get("content-length", 0)))
        method, path = line.split()[:2]
        status, out = "200 OK", b""
        if headers.get("authorization") != self.secret:
            status = "401 Unauthorized"
        elif method == "GET" and path.startswith("/traffic"):
            out = json.dumps(self.traffic).encode()
            if "clear=1" in path:
                self.traffic = {}
        elif method == "GET" and path == "/online":
            out = json.dumps(self.online).encode()
        elif method == "POST" and path == "/kick":
            self.kicked += json.loads(body)
        writer.write(f"HTTP/1.1 {status}\r\nContent-Length: {len(out)}\r\nConnection: close\r\n\r\n".encode() + out)
        await writer.drain()
        writer.close()


class Provider(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.d = tempfile.mkdtemp()
        self.stats = await FakeHysteriaStats().start()
        self.v = xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin="/nonexistent", public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇵🇱 Польша", restart_cmd=("true",),
            hy2={"port": 443, "sni": "www.example.com", "pin": "", "obfs": "", "obfs_port": 0,
                 "stats_ports": [self.stats.port], "stats_secret": "statsec"})
        self.v.apply = AsyncMock(return_value=True)
        now = time.time()
        await self.v.sync({1: now + 3600, 2: now + 3600}, {1: 1, 2: 3})

    async def asyncTearDown(self):
        self.stats.server.close()
        if self.v._pending:
            self.v._pending.cancel()

    async def test_suspended_subscription_is_locked_out_and_comes_back(self):
        self.assertEqual(self.v.state["devices"], {"1": 1, "2": 3})
        self.assertEqual(self.v.hy2_check(self.v.hy2_password(1)), 1)
        await self.v.suspend(1, 600)
        self.assertIsNone(self.v.hy2_check(self.v.hy2_password(1)), "Hysteria больше не принимает пароль")
        self.assertEqual(self.stats.kicked, ["u1"], "открытые подключения разорваны")
        emails = [c["email"] for c in self.v.build_config()["inbounds"][0]["settings"]["clients"]]
        self.assertFalse([e for e in emails if e.startswith("u1.")], "ключей Xray тоже нет")
        self.assertTrue([e for e in emails if e.startswith("u2.")])
        self.assertTrue(self.v.is_suspended(1) and not self.v.allowed(1) and self.v.allowed(2))
        self.assertIsNotNone(self.v.subscription(1), "подписка в приложении остаётся")
        self.assertEqual(self.v.due_resume(), [])
        self.v.state["suspended"]["1"] = time.time() - 1   # время вышло, а бот перезапускался
        self.assertEqual(self.v.due_resume(), [1])
        await self.v.resume(1)
        self.assertEqual(self.v.hy2_check(self.v.hy2_password(1)), 1)
        self.assertEqual(self.v.due_resume(), [])

    async def test_revoke_and_restart_forget_suspension(self):
        await self.v.suspend(1, 600)
        await self.v.revoke(1)
        self.assertEqual((self.v.state["suspended"], self.v.state["devices"]), ({}, {"2": 3}))
        await self.v.suspend(2, -1)
        await self.v.sync({2: time.time() + 3600}, {2: 3})
        self.assertEqual(self.v.state["suspended"], {}, "истёкшее отключение при запуске не переносится")

    async def test_traffic_and_online_from_hysteria_and_xray(self):
        self.stats.traffic = {"u1": {"tx": 10, "rx": 20}, "u2": {"tx": 1, "rx": 2}, "junk": {"tx": 9}}
        self.stats.online = {"u1": 2}
        self.assertEqual(await self.v.traffic(), {1: (10, 20), 2: (1, 2)})
        self.assertEqual(self.stats.traffic, {}, "счётчики сбрасываются после чтения")
        self.assertEqual(await self.v.online(), {1: 1}, "адреса входа неизвестны — одно устройство")
        # Один телефон: «Лучший сервер» и проверки пинга дают 9 подключений из одной сети оператора
        self.stats.online = {"u1": 9}
        for port in (1111, 2222, 3333):
            self.v._hy2_nets.setdefault(1, {})[xp.device_net(f"100.64.7.{port % 200}:{port}")] = time.time()
        self.assertEqual(await self.v.online(), {1: 1}, "9 подключений из одной сети — одно устройство")
        self.v._hy2_nets[1][xp.device_net("[2a00:1fa0:4f2:1::5]:443")] = time.time()
        self.v._hy2_nets[1][xp.device_net("203.0.113.9:7")] = time.time() - xp.HY2_NET_WINDOW - 1
        self.assertEqual(await self.v.online(), {1: 2}, "вторая сеть — второе устройство, старый вход забыт")
        self.stats.online = {"u1": 1}
        self.assertEqual(await self.v.online(), {1: 1}, "устройств не больше, чем подключений")
        self.v._hy2_nets.clear()
        self.stats.online = {"u1": 2}
        # вместе с Xray: трафик по ключам всех стран и разные адреса складываются
        self.v._live = {}
        with open(os.path.join(self.d, "xray"), "w") as f:
            f.write("#!/bin/sh\n")
        self.v.xray_bin = os.path.join(self.d, "xray")
        answers = {
            "statsquery": {"stat": [{"name": "user>>>u1.main>>>traffic>>>uplink", "value": 100},
                                    {"name": "user>>>u1.nl>>>traffic>>>downlink", "value": 1000},
                                    {"name": "inbound>>>in>>>traffic>>>uplink", "value": 5}]},
            "statsonlineiplist": {"users": [{"email": "u1.main", "ips": [{"ip": "10.0.0.1"}, {"ip": "10.0.1.2"}]},
                                            {"email": "u1.nl", "ips": [{"ip": "10.0.0.2"}]},
                                            {"email": "u2.main", "ips": [{"ip": "10.0.0.9"}]}]},
        }
        seen = []

        async def api(cmd, *args):
            seen.append((cmd, args))
            return 0, json.dumps(answers[cmd])
        self.v._api = api
        self.stats.traffic = {"u1": {"tx": 1, "rx": 1}}
        self.assertEqual(await self.v.traffic(), {1: (101, 1001)})
        # Xray: сети 10.0.0.0/24 и 10.0.1.0/24, плюс Hysteria без известного адреса
        self.assertEqual(await self.v.online(), {1: 3, 2: 1})
        self.assertIn(("statsquery", ("-pattern=user>>>", "-reset")), seen)

    def test_device_net(self):
        self.assertEqual(xp.device_net("1.2.3.4:5"), "1.2.3.0/24")
        self.assertEqual(xp.device_net("[2a00:1fa0:4f2:1::5]:443"), "2a00:1fa0:4f2::/56")
        self.assertEqual(xp.device_net("[::ffff:1.2.3.4]:5"), "1.2.3.0/24")
        self.assertEqual(xp.device_net("10.0.0.9"), "10.0.0.0/24")
        self.assertEqual(xp.device_net("мусор"), "")

    async def test_no_data_means_no_decision(self):
        self.stats.secret = "other"   # Hysteria не отвечает, Xray не запущен
        self.assertIsNone(await self.v.online())
        self.assertEqual(await self.v.traffic(), {})

    async def test_config_collects_stats_and_subscription_reports_usage(self):
        cfg = self.v.build_config()
        self.assertIn("StatsService", cfg["api"]["services"])
        self.assertTrue(cfg["policy"]["levels"]["0"]["statsUserOnline"])
        self.v.usage = lambda sid: (123, 456)
        _, headers = self.v.subscription(1)
        self.assertIn("upload=123; download=456", headers["subscription-userinfo"])


class CountryHysteria(unittest.IsolatedAsyncioTestCase):
    """У каждой страны через прокси свой сервер Hysteria, и в подписке одна Hysteria на страну."""

    async def asyncSetUp(self):
        self.d = tempfile.mkdtemp()
        self.log = os.path.join(self.d, "units.log")
        sysctl = os.path.join(self.d, "systemctl")
        with open(sysctl, "w") as f:
            f.write(f'#!/bin/sh\necho "$@" >> {self.log}\n')
        os.chmod(sysctl, 0o755)
        self.hydir = os.path.join(self.d, "aurora")
        self.v = xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin="/nonexistent", public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇵🇱 Польша", restart_cmd=("true",), xray_enabled=False,
            hy2={"port": 443, "sni": "www.example.com", "pin": "ab" * 32, "obfs": "secret", "obfs_port": 0,
                 "stats_ports": [20810], "stats_secret": "statsec"},
            hy2_locs={"ports": range(30000, 30002), "dir": self.hydir, "stats_base": 20830,
                      "systemctl": (sysctl,)})
        await self.v.sync({1: time.time() + 3600})

    def units(self) -> list[str]:
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return f.read().splitlines()

    def conf(self, code: str) -> dict:
        with open(os.path.join(self.hydir, f"hy2-loc-{code}.yaml")) as f:
            return json.load(f)

    async def test_countries_get_their_own_server_and_link(self):
        self.assertEqual([l.split("#")[0].split("@")[1].split("/")[0] for l in self.v.links(1)],
                         ["203.0.113.7:443"], "без стран в подписке одна Hysteria")
        self.v.add_location("de", "🇩🇪 Германия", "socks5://u%40x:p@1.2.3.4:1080")
        await self.v._pending
        self.v.set_auto_location("nl", "🇳🇱 Нидерланды", ["socks5://9.9.9.9:1080"], apply=False)
        await self.v.apply()
        self.assertEqual(self.v.state["hy2_ports"], {"de": 30000, "nl": 30001})
        de, nl = self.conf("de"), self.conf("nl")
        self.assertEqual((de["listen"], de["outbounds"][0]["socks5"]),
                         (":30000", {"addr": "1.2.3.4:1080", "username": "u@x", "password": "p"}))
        self.assertEqual(de["acl"]["inline"][-1], "out(all)")
        self.assertNotIn("reject(all, udp)", de["acl"]["inline"], "купленный SOCKS5 умеет UDP")
        self.assertEqual(nl["outbounds"][0]["socks5"],
                         {"addr": f"127.0.0.1:{self.v.relay_port}", "username": "nl", "password": self.v.relay_password})
        self.assertIn("reject(all, udp)", nl["acl"]["inline"])
        self.assertEqual(de["auth"]["http"]["url"], f"http://127.0.0.1:{self.v.hy2_auth_port}/hy2auth")
        self.assertEqual((de["trafficStats"]["listen"], nl["trafficStats"]["listen"]),
                         ("127.0.0.1:20830", "127.0.0.1:20831"))
        self.assertIn("restart aurora-hy2@loc-de", self.units())
        self.assertEqual(self.v._stats_ports(), [20810, 20830, 20831], "трафик и лимит считаются со всех серверов")

        links = self.v.links(1)
        self.assertEqual(len(links), 3, "Xray выключен: по одной Hysteria на страну, второго варианта нет")
        self.assertTrue(all(l.startswith("hysteria2://") for l in links))
        self.assertEqual([l.split("@")[1].split("/")[0] for l in links],
                         ["203.0.113.7:443", "203.0.113.7:30000", "203.0.113.7:30001"])
        self.assertFalse(any("obfs" in l for l in links))

        n = len(self.units())
        await self.v.apply()
        self.assertEqual(len(self.units()), n, "без изменений серверы стран не перезапускаются")
        self.v.set_auto_down("nl", True)
        self.assertEqual(len(self.v.links(1)), 2, "страна без живых прокси скрыта")
        self.v.add_location("fr", "🇫🇷 Франция", "http://5.5.5.5:3128")
        await self.v._pending
        self.assertNotIn("fr", self.v.state["hy2_ports"], "порты кончились: страна без Hysteria, остальное работает")
        self.v.remove_location("de")
        await self.v._pending
        self.assertIn("disable --now aurora-hy2@loc-de", self.units())
        self.assertFalse(os.path.exists(os.path.join(self.hydir, "hy2-loc-de.yaml")))
        self.assertEqual(self.v.state["hy2_ports"]["fr"], 30000, "освободившийся порт достался следующей стране")
        self.assertEqual(self.conf("fr")["outbounds"][0], {"name": "out", "type": "http", "http": {"url": "http://5.5.5.5:3128"}})

    async def test_names_without_suffix_and_site_rotation(self):
        from urllib.parse import parse_qs, unquote, urlparse
        self.v.add_location("de", "🇩🇪 Германия", "socks5://u:p@1.2.3.4:1080")
        await self.v._pending
        links = self.v.links(1)
        self.assertEqual([unquote(l.rsplit("#", 1)[1]) for l in links], ["🇵🇱 Польша", "🇩🇪 Германия"],
                         "только Hysteria: просто название страны")
        self.assertEqual(parse_qs(urlparse(links[0]).query)["sni"], ["www.example.com"])
        self.assertFalse(self.v.hy2_sni_rotatable(), "сервер без sniGuard: менять сайт нельзя")
        os.makedirs(self.hydir, exist_ok=True)
        with open(os.path.join(self.hydir, "hy2-plain.yaml"), "w") as f:
            json.dump({"tls": {"sniGuard": "disable"}}, f, indent=1)
        self.assertTrue(self.v.hy2_sni_rotatable())
        n = len(self.units())
        self.assertEqual(self.v.set_hy2_sni("www.wp.pl"), "www.example.com")
        self.assertTrue(all(parse_qs(urlparse(l).query)["sni"] == ["www.wp.pl"] for l in self.v.links(1)))
        await self.v.apply()
        self.assertEqual(len(self.units()), n, "смена сайта ничего не перезапускает")
        self.assertEqual(self.conf("de")["tls"]["sniGuard"], "disable")
        self.v.xray_enabled = True
        self.assertTrue(unquote(self.v.links(1)[0].rsplit("#", 1)[1]).endswith("· Hysteria"),
                        "с Xray приписка нужна, чтобы отличать от TCP")

    async def test_happ_gets_json_with_country_names_only(self):
        import base64
        self.v.add_location("de", "🇩🇪 Германия", "socks5://u:p@1.2.3.4:1080")
        await self.v._pending
        await self.v.start_sub_server("127.0.0.1")
        port = self.v._server.sockets[0].getsockname()[1]
        path = "/sub/1/" + self.v.sub_token(1)

        async def get(p, agent):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(f"GET {p} HTTP/1.1\r\nHost: x\r\nUser-Agent: {agent}\r\n\r\n".encode()); await w.drain()
            data = await r.read(); w.close()
            return data.partition(b"\r\n\r\n")
        head, _, body = await get(path, "Happ/3.7.0")
        self.assertIn(b"application/json", head)
        cfgs = json.loads(body)
        self.assertEqual([c["remarks"] for c in cfgs], ["🚀 Лучший сервер", "🇵🇱 Польша", "🇩🇪 Германия"])
        best = cfgs[0]
        self.assertEqual([o["tag"] for o in best["outbounds"]], ["p0", "p1", "direct", "block"])
        self.assertEqual(best["routing"]["balancers"][0]["strategy"]["type"], "leastPing")
        self.assertEqual(best["routing"]["rules"][-1], {"type": "field", "network": "tcp,udp", "balancerTag": "best"})
        self.assertEqual(best["observatory"]["subjectSelector"], ["p"])
        self.assertFalse(any(o["tag"].startswith("p") for o in best["outbounds"][2:]),
                         "direct и block не попадают в автовыбор")
        cfgs = cfgs[1:]
        out = cfgs[1]["outbounds"][0]
        self.assertEqual((out["protocol"], out["settings"]["port"], out["streamSettings"]["hysteriaSettings"]["auth"]),
                         ("hysteria", 30000, self.v.hy2_password(1)))
        tls = out["streamSettings"]["tlsSettings"]
        self.assertEqual((tls["serverName"], tls["alpn"], tls["pinnedPeerCertSha256"]), ("www.example.com", ["h3"], "ab" * 32))
        self.assertNotIn("allowInsecure", json.dumps(cfgs))
        rules = cfgs[0]["routing"]["rules"]
        self.assertTrue(any("geoip:ru" in r.get("ip", []) and r["outboundTag"] == "direct" for r in rules),
                        "российские сайты напрямую")
        _, _, body = await get(path, "v2rayNG/1.10.30")
        self.assertIsInstance(json.loads(body), list)
        for p, agent in ((path, "HiddifyNext/2.5"), (path + "?format=links", "Happ/3.7.0")):
            _, _, body = await get(p, agent)
            self.assertTrue(base64.b64decode(body).decode().startswith("hysteria2://"), agent)
        self.v.state["json_sub"] = False  # выключено в /admin
        _, _, body = await get(path, "Happ/3.7.0")
        self.assertTrue(base64.b64decode(body).decode().startswith("hysteria2://"))
        self.v._server.close()

    async def test_own_app_gets_tuned_configs_and_one_tap_page(self):
        import base64
        self.v.add_location("de", "🇩🇪 Германия", "socks5://u:p@1.2.3.4:1080")
        await self.v._pending
        await self.v.start_sub_server("127.0.0.1")
        port = self.v._server.sockets[0].getsockname()[1]
        path = "/sub/1/" + self.v.sub_token(1)

        async def get(p, agent):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(f"GET {p} HTTP/1.1\r\nHost: x\r\nUser-Agent: {agent}\r\n\r\n".encode()); await w.drain()
            data = await r.read(); w.close()
            return data.partition(b"\r\n\r\n")

        def quic(cfgs):
            return [o["streamSettings"].get("finalmask", {}).get("quicParams")
                    for c in cfgs for o in c["outbounds"] if o["protocol"] == "hysteria"]

        _, _, body = await get(path, "AuroraVPN/1.0.5 v2rayNG/1.0.5")
        cfgs = json.loads(body)
        self.assertEqual([c["remarks"] for c in cfgs],
                         ["🚀 Лучший сервер", "🇵🇱 Польша", "🇵🇱 Польша · белые списки", "🇵🇱 Польша · эконом",
                          "🇩🇪 Германия"])
        turbo = {"keepAlivePeriod": 10, "maxIdleTimeout": 60, "congestion": "brutal",
                 "brutalUp": "20 mbps", "brutalDown": "100 mbps"}
        self.assertEqual([q["brutalDown"] for q in quic([cfgs[2]])], ["10 mbps"], "белые списки — турбо 10")
        self.assertEqual(quic([cfgs[3]]), [{"keepAlivePeriod": 10, "maxIdleTimeout": 60}], "эконом — обычный BBR")
        self.assertEqual(len(cfgs[0]["outbounds"]), 4, "запасные пункты не входят в «Лучший сервер»")
        cfgs = [cfgs[0], cfgs[1], cfgs[4]]
        self.assertTrue(quic(cfgs) and all(q == turbo for q in quic(cfgs)), "турбо везде, и в «Лучшем сервере»")
        self.assertEqual({c["routing"]["domainStrategy"] for c in cfgs}, {"AsIs"}, "без лишних DNS-запросов")
        # обфускация и настройки QUIC уживаются в одном finalmask
        obfs = [o for c in cfgs for o in c["outbounds"] if o["protocol"] == "hysteria"
                and o["streamSettings"].get("finalmask", {}).get("udp")]
        self.assertTrue(all("quicParams" in o["streamSettings"]["finalmask"] for o in obfs))
        for agent in ("Happ/3.7.0", "v2rayNG/1.10.30"):
            _, _, body = await get(path, agent)
            self.assertEqual(set(map(str, quic(json.loads(body)))), {"None"}, f"{agent}: без quicParams")
            self.assertEqual({c["routing"]["domainStrategy"] for c in json.loads(body)}, {"IPIfNonMatch"},
                             f"{agent}: маршрутизация прежняя")

        # новое приложение «(enc1)»: подписка зашифрована, без адресов и паролей открытым текстом
        import hashlib
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        cc = __import__("client_config")
        head, _, body = await get(path, "AuroraVPN/1.0.9 (enc1) v2rayNG/1.0.9")
        self.assertTrue(body.startswith(b"aurora1:"))
        self.assertNotIn(b"203.0.113.7", body)
        self.assertNotIn(self.v.hy2_password(1).encode(), body)
        raw = base64.b64decode(body[len(b"aurora1:"):])
        key = hashlib.sha256((cc.SUB_SECRET + path).encode()).digest()  # как в AuroraCrypto.kt
        plain = json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], None))
        self.assertEqual([c["remarks"] for c in plain], [c["remarks"] for c in cfgs[:1]] +
                         ["🇵🇱 Польша", "🇵🇱 Польша · белые списки", "🇵🇱 Польша · эконом", "🇩🇪 Германия"])
        _, _, again = await get(path, "AuroraVPN/1.0.9 (enc1) v2rayNG/1.0.9")
        self.assertNotEqual(again, body, "каждый раз новый nonce")
        # короткая ссылка: ключ от её пути
        short = "/" + self.v.short_token(1)
        _, _, body = await get(short, "AuroraVPN/1.0.9 (enc1) v2rayNG/1.0.9")
        raw = base64.b64decode(body[len(b"aurora1:"):])
        AESGCM(hashlib.sha256((cc.SUB_SECRET + short).encode()).digest()).decrypt(raw[:12], raw[12:], None)
        # старое приложение без «(enc1)» получает обычный JSON
        _, _, body = await get(path, "AuroraVPN/1.0.4 v2rayNG/1.0.4")
        self.assertTrue(body.startswith(b"["))

        self.v.support_url = "https://t.me/aurora_bot"
        head, _, _ = await get(path, "AuroraVPN/1.0.5 v2rayNG/1.0.5")
        self.assertIn(b"support-url: https://t.me/aurora_bot", head)
        head, _, body = await get(path + "/app", "Mozilla/5.0")
        self.assertIn(b"text/html", head)
        page = body.decode()
        self.assertIn("aurora://install-sub?url=" + quote(self.v.sub_url(1), safe=""), page)
        self.assertEqual(self.v.app_link(1), self.v.sub_url(1) + "/app")
        # подписка, открытая в браузере, — та же страница, ключей в ней нет
        chrome = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36"
        head, _, body = await get(path, chrome)
        self.assertIn(b"text/html", head)
        self.assertNotIn(b"hysteria", body.lower())
        self.assertNotIn(self.v.hy2_password(1).encode(), body)
        _, _, body = await get(path + "?format=links", chrome)
        self.assertTrue(base64.b64decode(body).decode().startswith("hysteria2://"), "ключи явно — по ?format=links")
        for app in ("Happ/3.7.0", "HiddifyNext/2.5 (android) like ClashMeta", "Streisand/1.6", "okhttp/4.12.0"):
            head, _, _ = await get(path, app)
            self.assertNotIn(b"text/html", head, app)
        _, _, body = await get("/sub/1/" + "0" * 24 + "/app", "Mozilla/5.0")
        self.assertNotIn(b"aurora://", body, "чужой токен — без страницы")
        self.v._server.close()

    async def test_no_mkcp_left(self):
        # mKCP убран: Happ не собирал его конфиг и вместе с ним терял «Лучший сервер»
        self.assertFalse([l for l in self.v.links(1) if "type=kcp" in l])
        cfgs = __import__("client_config").configs(self.v.json_entries(1))
        self.assertEqual([c["remarks"] for c in cfgs], ["🇵🇱 Польша"], "одно подключение — без «Лучшего сервера»")
        self.assertNotIn('"kcp"', json.dumps(cfgs))

    async def test_second_hysteria_only_when_asked(self):
        e = {"HY2_PORT": "443", "HY2_OBFS_PORT": "8443", "HY2_OBFS": "pw", "PUBLIC_HOST": "1.2.3.4",
             "REALITY_PRIVATE_KEY": "a", "REALITY_PUBLIC_KEY": "b", "REALITY_SHORT_ID": "c",
             "VPN_STATE": os.path.join(self.d, "s2.json"), "XRAY_CONFIG": os.path.join(self.d, "c2.json")}
        old = dict(os.environ)
        try:
            os.environ.update(e)
            self.assertEqual(xp.from_env().hy2["obfs_port"], 0)
            os.environ["HY2_OBFS_ON"] = "1"
            self.assertEqual(xp.from_env().hy2["obfs_port"], 8443)
        finally:
            os.environ.clear(); os.environ.update(old)


class Guard(unittest.TestCase):
    def test_warn_then_block_then_unblock(self):
        g = DeviceGuard("block", warn_after=2, block_after=3, block_minutes=30)
        allowed = {1: 1, 2: 3}
        self.assertEqual(g.check({1: 2, 2: 3}, allowed, now=0), [])
        self.assertEqual(g.check({1: 2, 2: 3}, allowed, now=300), [("warn", 1, 2, 1)])
        self.assertEqual(g.check({1: 2}, allowed, now=600), [])
        self.assertEqual(g.check({1: 2}, allowed, now=900), [])
        self.assertEqual(g.check({1: 3}, allowed, now=1200), [("block", 1, 3, 1)])
        self.assertEqual(g.check({1: 5}, allowed, now=1500), [], "отключённую не считаем")
        self.assertEqual(g.due_unblock(now=1200 + 1799), [])
        self.assertEqual(g.due_unblock(now=1200 + 1800), [1])

    def test_a_good_check_resets_the_streak(self):
        g = DeviceGuard("block", warn_after=2)
        g.check({1: 2}, {1: 1}, now=0)
        g.check({1: 1}, {1: 1}, now=300)  # телефон сменил сеть, старый адрес пропал
        self.assertEqual(g.check({1: 2}, {1: 1}, now=600), [])

    def test_warn_mode_never_blocks_and_off_does_nothing(self):
        g = DeviceGuard("warn", warn_after=1, block_after=1)
        acts = [a for t in range(10) for a in g.check({1: 4}, {1: 1}, now=t * 300)]
        self.assertEqual([a[0] for a in acts], ["warn"])
        self.assertEqual(DeviceGuard("off").check({1: 9}, {1: 1}), [])


if __name__ == "__main__":
    unittest.main()
