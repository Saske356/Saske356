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
