"""Ключи без перезапуска Xray, трафик, устройства и Hysteria2: python3 -m unittest discover -s tests

Вместо настоящего Xray подставляется заглушка на Python. Она хранит пользователей в файле
и, как настоящий Xray, перестаёт читать флаги на первом обычном аргументе.
"""

import asyncio, json, os, sys, tempfile, time, unittest
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xray_provider as xp  # noqa: E402
from devices import DeviceGuard  # noqa: E402
from hysteria import cert_pin  # noqa: E402

FAKE_XRAY = r'''#!/usr/bin/env python3
import json, os, sys
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xray-state.json")
st = json.load(open(STATE)) if os.path.exists(STATE) else {"users": [], "traffic": {}, "online": {}, "calls": []}
def save(): json.dump(st, open(STATE, "w"))
a = sys.argv[1:]
if a[:2] == ["run", "-test"]:
    json.load(open(a[3])); sys.exit(0)
if a[0] != "api":
    sys.exit(2)
cmd, rest = a[1], a[2:]
flags, pos = {}, []
for i, x in enumerate(rest):          # как flag в Go: флаги только до первого обычного аргумента
    if x.startswith("-") and not pos:
        k, _, v = x.lstrip("-").partition("=")
        flags[k] = v or True
    else:
        pos = rest[i:]; break
st["calls"].append(cmd); save()
if flags.get("server") != "127.0.0.1:10085" or st.get("down"):
    print("failed to dial"); sys.exit(1)
for p in pos:
    if p.startswith("-"):
        print("bad positional", p); sys.exit(3)
if cmd == "adu":
    n = 0
    for f in pos:
        for inb in json.load(open(f))["inbounds"]:
            for c in inb["settings"]["clients"]:
                if c["email"] in st["users"]:
                    print("User already exists")
                else:
                    st["users"].append(c["email"]); n += 1
    save(); print(f"Added {n} user(s) in total.")
elif cmd == "rmu":
    if flags.get("tag") != "in": print("no tag"); sys.exit(1)
    n = 0
    for e in pos:
        if e in st["users"]: st["users"].remove(e); n += 1
    save(); print(f"Removed {n} user(s) in total.")
elif cmd == "statsquery":
    out = [{"name": f"user>>>{e}>>>traffic>>>{d}", "value": v}
           for e, t in st["traffic"].items() for d, v in t.items()]
    if "reset" in flags: st["traffic"] = {}; save()
    print(json.dumps({"stat": out}))
elif cmd == "statsonlineiplist" and "all" in flags:
    if st.get("old"): print("flag provided but not defined: -all"); sys.exit(2)
    print(json.dumps({"users": [{"email": e, "ips": [{"ip": ip, "last_seen": 1} for ip in ips]}
                                for e, ips in st["online"].items()]}))
elif cmd == "statsgetallonlineusers":
    print(json.dumps({"users": [f"user>>>{e}>>>online" for e in st["online"]]}))
elif cmd == "statsonlineiplist":
    print(json.dumps({"name": "x", "ips": {ip: 1 for ip in st["online"].get(flags["email"], [])}}))
else:
    sys.exit(4)
'''


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.d = tempfile.mkdtemp()
        self.bin = os.path.join(self.d, "xray")
        with open(self.bin, "w") as f:
            f.write(FAKE_XRAY)
        os.chmod(self.bin, 0o755)
        self.restarts = os.path.join(self.d, "restarts")
        self.v = self.make()

    def make(self, hy2=None):
        return xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin=self.bin, public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇸🇪 Швеция", restart_cmd=("sh", "-c", f"echo x >> {self.restarts}"),
            hy2=hy2)

    def fake(self) -> dict:
        with open(os.path.join(self.d, "xray-state.json")) as f:
            return json.load(f)

    def set_fake(self, **kw) -> None:
        st = self.fake() if os.path.exists(os.path.join(self.d, "xray-state.json")) else \
            {"users": [], "traffic": {}, "online": {}, "calls": []}
        st.update(kw)
        with open(os.path.join(self.d, "xray-state.json"), "w") as f:
            json.dump(st, f)

    def n_restarts(self) -> int:
        if not os.path.exists(self.restarts):
            return 0
        with open(self.restarts) as f:
            return len(f.read().split())

    async def started(self, active=None):
        """Бот запустился: применил конфиг целиком один раз. Заглушка знает тех, кто в конфиге."""
        await self.v.sync(active or {1: time.time() + 3600})
        with open(self.v.config_path) as f:
            emails = [c["email"] for c in json.load(f)["inbounds"][0]["settings"]["clients"]]
        self.set_fake(users=emails)
        return self.n_restarts()


class HotKeys(Base):
    async def test_new_extended_and_revoked_keys_without_restart(self):
        self.v.add_location("nl", "🇳🇱 Нидерланды", "socks5://u:p@1.2.3.4:1080")
        await asyncio.sleep(0)
        if self.v._pending:
            self.v._pending.cancel()
        base = await self.started()
        self.assertEqual(base, 1)
        await self.v.issue(2, time.time() + 3600, devices=2)
        self.assertEqual(self.n_restarts(), base, "новый ключ без перезапуска Xray")
        self.assertEqual(sorted(self.fake()["users"]), ["u1.main", "u1.nl", "u2.main", "u2.nl"])
        self.assertEqual(self.v.state["devices"]["2"], 2)
        calls = len(self.fake()["calls"])
        await self.v.issue(2, time.time() + 7200)  # продление: Xray не трогаем вовсе
        self.assertEqual(len(self.fake()["calls"]), calls)
        await self.v.revoke(1)
        self.assertEqual(sorted(self.fake()["users"]), ["u2.main", "u2.nl"])
        self.assertEqual(self.n_restarts(), base)
        self.assertFalse(self.v._apply_pending(), "полный перезапуск не запланирован")
        # маршрут страны по шаблону: ключ, добавленный на ходу, выходит через свою страну
        cfg = self.v.build_config()
        rule = next(r for r in cfg["routing"]["rules"] if r.get("outboundTag") == "out-nl")
        self.assertIn("regexp:^u[0-9]+\\.nl$", rule["user"])

    async def test_falls_back_to_full_apply_when_api_is_down(self):
        await self.started()
        self.set_fake(down=True)
        await self.v.issue(5, time.time() + 3600)
        self.assertTrue(self.v._pending, "API не ответил: конфиг применится целиком")
        await self.v._pending
        with open(self.v.config_path) as f:
            self.assertIn("u5.main", f.read())
        self.assertEqual(self.n_restarts(), 2)

    async def test_before_first_apply_nothing_is_sent_to_api(self):
        await self.v.issue(5, time.time() + 3600)
        self.assertTrue(self.v._pending)
        self.v._pending.cancel()
        self.assertFalse(os.path.exists(os.path.join(self.d, "xray-state.json")))

    async def test_traffic_and_online_devices(self):
        self.v.add_location("nl", "🇳🇱 Нидерланды", "socks5://u:p@1.2.3.4:1080")
        await self.started({1: time.time() + 3600, 2: time.time() + 3600})
        self.set_fake(traffic={"u1.main": {"uplink": 100, "downlink": 1000}, "u1.nl": {"downlink": 5},
                               "u2.main": {"uplink": 7}},
                      online={"u1.main": ["10.0.0.1", "10.0.0.2"], "u1.nl": ["10.0.0.2", "10.0.0.3"],
                              "u2.main": ["10.0.0.9"]})
        self.assertEqual(await self.v.traffic(), {1: (100, 1005), 2: (7, 0)})
        self.assertEqual(await self.v.traffic(), {}, "счётчики сбрасываются после чтения")
        self.assertEqual(await self.v.online(), {1: 3, 2: 1})
        self.set_fake(old=True)  # Xray постарше: без -all, адреса по каждому ключу
        self.assertEqual(await self.v.online(), {1: 3, 2: 1})
        self.set_fake(down=True)
        self.assertIsNone(await self.v.online())

    async def test_suspend_and_resume(self):
        await self.started({1: time.time() + 3600, 2: time.time() + 3600})
        await self.v.suspend(1, 600)
        self.assertEqual(self.fake()["users"], ["u2.main"])
        self.assertFalse(self.v.allowed(1))
        self.assertTrue(self.v.is_suspended(1))
        self.assertNotIn("u1.main", json.dumps(self.v.build_config()), "и после перезапуска не вернётся")
        self.assertIsNotNone(self.v.subscription(1), "подписка в приложении остаётся")
        await self.v.resume(1)
        self.assertEqual(sorted(self.fake()["users"]), ["u1.main", "u2.main"])
        self.assertTrue(self.v.allowed(1))
        self.assertEqual(self.n_restarts(), 1)

    async def test_keys_issued_at_the_same_time_all_arrive(self):
        await self.started()
        await asyncio.gather(*(self.v.issue(i, time.time() + 3600) for i in range(10, 16)))
        self.assertEqual(sorted(self.fake()["users"]), sorted(["u1.main"] + [f"u{i}.main" for i in range(10, 16)]))
        self.assertFalse(self.v._apply_pending())

    async def test_suspension_ends_after_bot_restart(self):
        await self.started({1: time.time() + 3600})
        await self.v.suspend(1, 600)
        v2 = self.make()  # бот перезапустился: про отключение помнит только сервер
        v2.last_apply, v2.live = time.time(), set()
        self.assertEqual(v2.due_resume(), [])
        v2.state["suspended"]["1"] = time.time() - 1
        self.assertEqual(v2.due_resume(), [1])
        await v2.resume(1)
        self.assertIn("u1.main", self.fake()["users"])
        self.assertEqual(v2.due_resume(), [])

    async def test_subscription_reports_traffic(self):
        await self.started()
        self.v.usage = lambda sid: (123, 456)
        _, headers = self.v.subscription(1)
        self.assertIn("upload=123; download=456", headers["subscription-userinfo"])


class FakeHysteriaStats:
    """API статистики сервера Hysteria: /traffic, /online, /kick с заголовком Authorization."""

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
        writer.write(f"HTTP/1.1 {status}\r\nContent-Length: {len(out)}\r\n\r\n".encode() + out)
        await writer.drain()
        writer.close()


CERT = """-----BEGIN CERTIFICATE-----
MIIBfTCCASOgAwIBAgIUJ0a6+3zsW4rS6wP4wOe0K3m3VjIwCgYIKoZIzj0EAwIw
FDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI0MDEwMTAwMDAwMFoXDTM0MDEwMTAw
MDAwMFowFDESMBAGA1UEAwwJbG9jYWxob3N0MFkwEwYHKoZIzj0CAQYIKoZIzj0D
AQcDQgAEGv2lsXyIu3v3+0MxIz8zQ0b9Jb8nI2s7zG5kJ7qWm7mJ0m3G0V7r5k3S
o3n2q8v3eWb7b3V3+o3xX6kq1Kq1n6NTMFEwHQYDVR0OBBYEFAAAAAAAAAAAAAAA
AAAAAAAAAAAAMB8GA1UdIwQYMBaAFAAAAAAAAAAAAAAAAAAAAAAAAAAAMA8GA1Ud
EwEB/wQFMAMBAf8wCgYIKoZIzj0EAwIDSAAwRQIgAQIDBAUGBwgJCgsMDQ4PEBES
ExQVFhcYGRobHB0eHyACIQCAgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2e
nw==
-----END CERTIFICATE-----
"""


class Hy2(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.stats = await FakeHysteriaStats().start()
        cert = os.path.join(self.d, "server.crt")
        with open(cert, "w") as f:
            f.write(CERT)
        self.v = self.make(hy2={"port": 443, "cert_path": cert, "sni": "www.example.com", "auth_port": 0,
                                "stats_port": self.stats.port, "stats_secret": "statsec"})
        self.assertTrue(await self.v.hy2.start_auth())

    async def asyncTearDown(self):
        self.v.hy2._server.close()
        self.stats.server.close()

    async def auth(self, auth: str) -> dict:
        r, w = await asyncio.open_connection("127.0.0.1", self.v.hy2.auth_port)
        body = json.dumps({"addr": "198.51.100.1:5555", "auth": auth, "tx": 0}).encode()
        w.write(b"POST /auth HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        await w.drain()
        data = await r.read()
        w.close()
        self.assertTrue(data.startswith(b"HTTP/1.1 200"))
        return json.loads(data.partition(b"\r\n\r\n")[2])

    async def test_link_sits_next_to_main_country_and_auth_follows_subscription(self):
        await self.started({1: time.time() + 3600})
        self.v.add_location("nl", "🇳🇱 Нидерланды", "socks5://u:p@1.2.3.4:1080")
        links = self.v.links(1)
        self.assertEqual([urlparse(l).scheme for l in links], ["vless", "hysteria2", "vless"])
        u = urlparse(links[1]); q = parse_qs(u.query)
        self.assertEqual((u.hostname, u.port, u.username), ("203.0.113.7", 443, self.v.hy2.password(1)))
        self.assertNotIn(":", u.username, "в пароле нет двоеточия: иначе приложения делят его на логин")
        self.assertEqual((q["insecure"], q["sni"], q["pinSHA256"]), (["1"], ["www.example.com"], [cert_pin(self.v.hy2.cert_path)]))
        self.assertEqual(len(q["pinSHA256"][0]), 64)
        self.assertIn("Hysteria2", unquote(u.fragment))

        self.assertEqual(await self.auth(self.v.hy2.password(1)), {"ok": True, "id": "u1"})
        self.assertFalse((await self.auth(self.v.hy2.password(1)[:-1] + "0"))["ok"])
        self.assertFalse((await self.auth(self.v.hy2.password(2)))["ok"], "подписки нет")
        self.assertFalse((await self.auth("garbage"))["ok"])
        await self.v.suspend(1, 600)
        self.assertFalse((await self.auth(self.v.hy2.password(1)))["ok"], "отключена за превышение")
        self.assertEqual(self.stats.kicked, ["u1"], "текущие подключения Hysteria разорваны")
        await self.v.resume(1)
        self.assertTrue((await self.auth(self.v.hy2.password(1)))["ok"])
        await self.v.revoke(1)
        self.assertFalse((await self.auth(self.v.hy2.password(1)))["ok"])

    async def test_traffic_and_devices_include_hysteria(self):
        await self.started({1: time.time() + 3600, 2: time.time() + 3600})
        self.set_fake(traffic={"u1.main": {"uplink": 10, "downlink": 20}}, online={"u1.main": ["10.0.0.1"]})
        self.stats.traffic = {"u1": {"tx": 1, "rx": 2}, "u2": {"tx": 3, "rx": 4}, "junk": {"tx": 9}}
        self.stats.online = {"u1": 2, "u2": 1}
        self.assertEqual(await self.v.traffic(), {1: (11, 22), 2: (3, 4)})
        self.assertEqual(self.stats.traffic, {}, "статистика Hysteria сбрасывается после чтения")
        self.assertEqual(await self.v.online(), {1: 3, 2: 1})

    async def test_wrong_stats_secret_means_no_data(self):
        self.v.hy2.stats_secret = "nope"
        self.assertIsNone(await self.v.hy2.traffic())
        self.assertIsNone(await self.v.hy2.online())


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
