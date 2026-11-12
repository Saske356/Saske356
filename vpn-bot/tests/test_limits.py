"""Лимит устройств, трафик и временное отключение подписки: python3 -m unittest discover -s tests

Xray и Hysteria заменены заглушками: ответы API Xray подставляются напрямую, а статистику
Hysteria отдаёт маленький HTTP-сервер с тем же заголовком Authorization.
"""

import asyncio, json, os, sys, tempfile, time, unittest
from unittest.mock import AsyncMock

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
        self.assertEqual(await self.v.online(), {1: 2})
        # вместе с Xray: трафик по ключам всех стран и разные адреса складываются
        self.v._live = {}
        with open(os.path.join(self.d, "xray"), "w") as f:
            f.write("#!/bin/sh\n")
        self.v.xray_bin = os.path.join(self.d, "xray")
        answers = {
            "statsquery": {"stat": [{"name": "user>>>u1.main>>>traffic>>>uplink", "value": 100},
                                    {"name": "user>>>u1.nl>>>traffic>>>downlink", "value": 1000},
                                    {"name": "inbound>>>in>>>traffic>>>uplink", "value": 5}]},
            "statsonlineiplist": {"users": [{"email": "u1.main", "ips": [{"ip": "10.0.0.1"}, {"ip": "10.0.0.2"}]},
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
        self.assertEqual(await self.v.online(), {1: 4, 2: 1})
        self.assertIn(("statsquery", ("-pattern=user>>>", "-reset")), seen)

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
