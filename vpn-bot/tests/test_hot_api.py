"""Ключи без перезапуска Xray, трафик, устройства и Hysteria2: python3 -m unittest discover -s tests

Вместо настоящего Xray подставляется заглушка на Python. Она хранит пользователей в файле
и, как настоящий Xray, перестаёт читать флаги на первом обычном аргументе.
"""

import asyncio, base64, json, os, sys, tempfile, time, unittest
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
                key = c["email"] if inb["tag"] == "in" else inb["tag"] + ":" + c["email"]  # у входа свой список
                if key in st["users"]:
                    print("User already exists")
                else:
                    st["users"].append(key); n += 1
    save(); print(f"Added {n} user(s) in total.")
elif cmd == "rmu":
    if not flags.get("tag"): print("no tag"); sys.exit(1)
    n = 0
    for e in pos:
        key = e if flags["tag"] == "in" else flags["tag"] + ":" + e
        if key in st["users"]: st["users"].remove(key); n += 1
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

    def make(self, hy2=None, **kw):
        return xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin=self.bin, public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇸🇪 Швеция", restart_cmd=("sh", "-c", f"echo x >> {self.restarts}"),
            hy2=hy2, **kw)

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


class XhttpAndCountries(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.stats = await FakeHysteriaStats().start()
        cert = os.path.join(self.d, "server.crt")
        with open(cert, "w") as f:
            f.write(CERT)
        self.units = os.path.join(self.d, "units.log")
        sysctl = os.path.join(self.d, "systemctl")
        with open(sysctl, "w") as f:
            f.write(f'#!/bin/sh\necho "$@" >> {self.units}\n')
        os.chmod(sysctl, 0o755)
        self.hydir = os.path.join(self.d, "hy")
        self.v = self.make(
            hy2={"port": 443, "cert_path": cert, "sni": "www.example.com", "auth_port": 0,
                 "stats_port": self.stats.port, "stats_secret": "statsec"},
            hy2_extra={"ports": range(30000, 30003), "dir": self.hydir, "unit": "hysteria-loc@",
                       "systemctl": (sysctl,)},
            xhttp_port=8443, hy2_first=True)

    async def asyncTearDown(self):
        self.stats.server.close()

    def unit_log(self) -> list[str]:
        if not os.path.exists(self.units):
            return []
        with open(self.units) as f:
            return f.read().split("\n")[:-1]

    async def test_xhttp_inbound_and_hot_keys_in_both(self):
        await self.started()
        cfg = self.v.build_config()
        xh = next(i for i in cfg["inbounds"] if i["tag"] == "in-xh")
        self.assertEqual((xh["port"], xh["streamSettings"]["network"], xh["streamSettings"]["security"]),
                         (8443, "xhttp", "reality"))
        self.assertTrue(all("flow" not in c for c in xh["settings"]["clients"]), "Vision с XHTTP не работает")
        self.assertEqual(xh["streamSettings"]["xhttpSettings"]["path"], self.v.xhttp_path)
        await self.v.issue(2, time.time() + 3600)
        self.assertEqual(self.n_restarts(), 1, "ключ попал в оба входа без перезапуска")
        self.assertIn("u2.main", self.fake()["users"])
        self.assertIn("in-xh:u2.main", self.fake()["users"])
        await self.v.revoke(2)
        self.assertFalse([u for u in self.fake()["users"] if "u2." in u])
        self.assertFalse(self.v._apply_pending())

    async def test_every_country_gets_hysteria_and_hysteria_goes_first(self):
        self.v.add_location("nl", "🇳🇱 Нидерланды", "socks5://u:p@1.2.3.4:1080")
        self.v.add_location("us", "🇺🇸 США", "http://5.6.7.8:3128")
        self.v.set_auto_location("de", "🇩🇪 Германия", ["socks5://9.9.9.9:1080"], apply=False)
        await self.v._pending
        self.assertEqual(self.v.hy2.locs, {"nl": 30000, "us": 30001, "de": 30002})
        with open(os.path.join(self.hydir, "loc-nl.yaml")) as f:
            nl = f.read()
        self.assertIn('addr: "1.2.3.4:1080"', nl)
        self.assertIn('username: "u"', nl)
        with open(os.path.join(self.hydir, "loc-de.yaml")) as f:
            de = f.read()
        self.assertIn(f'addr: "127.0.0.1:{self.v.relay_port}"', de, "авто-страна идёт через ретранслятор")
        self.assertIn('"reject(all, udp)"', de)
        with open(os.path.join(self.hydir, "loc-us.yaml")) as f:
            self.assertIn("type: http", f.read())
        self.assertIn("restart hysteria-loc@nl", self.unit_log())

        await self.v.issue(1, time.time() + 3600)
        links = self.v.links(1)
        schemes = [urlparse(l).scheme for l in links]
        self.assertEqual(schemes[:4], ["hysteria2"] * 4, "Hysteria2 первым")
        ports = [urlparse(l).port for l in links[:4]]
        self.assertEqual(ports, [443, 30000, 30001, 30002])
        xh = [l for l in links if "type=xhttp" in l]
        self.assertEqual(len(xh), 4)
        self.assertEqual(urlparse(xh[0]).port, 8443)
        self.assertEqual(parse_qs(urlparse(xh[0]).query)["path"], [self.v.xhttp_path])

        # повторное применение без изменений не перезапускает серверы стран
        n = len(self.unit_log())
        await self.v.apply()
        self.assertEqual(len(self.unit_log()), n)
        # страна удалена: её сервер остановлен, порт освобождён
        self.v.remove_location("nl")
        await self.v._pending
        self.assertIn("disable --now hysteria-loc@nl", self.unit_log())
        self.assertFalse(os.path.exists(os.path.join(self.hydir, "loc-nl.yaml")))
        self.assertNotIn("nl", self.v.hy2.locs)
        # статистика собирается и с серверов стран
        self.assertEqual(self.v.hy2.stats_ports(), [self.stats.port, self.stats.port + 2, self.stats.port + 3])


class SubscriptionTls(Base):
    async def test_https_subscription_and_redirect_from_http(self):
        import shutil, ssl, subprocess
        if not shutil.which("openssl"):
            self.skipTest("нет openssl")
        cert, key = os.path.join(self.d, "c.pem"), os.path.join(self.d, "k.pem")
        subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "2",
                        "-keyout", key, "-out", cert, "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
        self.v = self.make(sub_tls={"host": "localhost", "port": 0, "cert": cert, "key": key})
        await self.started()
        await self.v.start_sub_server("127.0.0.1")
        tls_port = self.v._tls_server.sockets[0].getsockname()[1]
        plain_port = self.v._server.sockets[0].getsockname()[1]
        self.v.sub_tls["port"] = tls_port
        url = self.v.sub_url(1)
        self.assertTrue(url.startswith(f"https://localhost:{tls_port}/sub/1/"))
        path = urlparse(url).path

        r, w = await asyncio.open_connection("127.0.0.1", plain_port)
        w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode()); await w.drain()
        head = (await r.read()).decode(); w.close()
        self.assertTrue(head.startswith("HTTP/1.1 301"), head)
        self.assertIn(f"Location: {url}", head)
        self.assertNotIn("vless", head, "по HTTP ключи больше не отдаются")

        ctx = ssl.create_default_context(cafile=cert)
        r, w = await asyncio.open_connection("127.0.0.1", tls_port, ssl=ctx, server_hostname="localhost")
        w.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()); await w.drain()
        data = await r.read(); w.close()
        head, _, body = data.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.1 200"), head)
        import base64
        self.assertIn("vless://", base64.b64decode(body).decode())
        self.v._server.close(); self.v._tls_server.close()

    async def test_broken_certificate_keeps_plain_http(self):
        self.v = self.make(sub_tls={"host": "localhost", "port": 0, "cert": "/nonexistent", "key": "/nonexistent"})
        await self.v.start_sub_server("127.0.0.1")
        self.assertIsNone(self.v.sub_tls)
        self.assertTrue(self.v.sub_url(1).startswith("http://203.0.113.7:"))
        self.v._server.close()


class JsonSubscription(Hy2):
    async def get(self, path, agent):
        r, w = await asyncio.open_connection("127.0.0.1", self.v._server.sockets[0].getsockname()[1])
        w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nUser-Agent: {agent}\r\n\r\n".encode()); await w.drain()
        data = await r.read(); w.close()
        head, _, body = data.partition(b"\r\n\r\n")
        return head.decode(), body

    async def test_v2rayng_and_happ_get_configs_others_get_links(self):
        self.v.json_sub = True
        self.v.hy2.hop_ports = "20000-29999"
        await self.started({1: time.time() + 3600})
        await self.v.start_sub_server("127.0.0.1")
        path = urlparse(self.v.sub_url(1)).path
        head, body = await self.get(path, "v2rayNG/1.10.20")
        self.assertIn("application/json", head)
        cfgs = json.loads(body)
        self.assertEqual([c["remarks"] for c in cfgs], ["🇸🇪 Швеция", "🇸🇪 Швеция ⚡ Hysteria2"])
        hy = cfgs[1]["outbounds"][0]
        self.assertEqual((hy["protocol"], hy["settings"]["port"], hy["streamSettings"]["hysteriaSettings"]["auth"]),
                         ("hysteria", 443, self.v.hy2.password(1)))
        tls = hy["streamSettings"]["tlsSettings"]
        self.assertEqual((tls["alpn"], tls["pinnedPeerCertSha256"]), (["h3"], self.v.hy2.pin))
        self.assertNotIn("allowInsecure", json.dumps(cfgs), "в новом Xray этого поля нет, конфиг бы не открылся")
        vl = cfgs[0]["outbounds"][0]
        self.assertEqual(vl["streamSettings"]["realitySettings"]["publicKey"], "PUB")
        rules = cfgs[0]["routing"]["rules"]
        self.assertTrue(any("geoip:ru" in r.get("ip", []) and r["outboundTag"] == "direct" for r in rules))
        self.assertTrue(any("regexp:\\.ru$" in r.get("domain", []) and r["outboundTag"] == "direct" for r in rules))
        self.assertEqual(rules[-1]["outboundTag"], "proxy")
        self.assertEqual(cfgs[0]["inbounds"][0]["port"], 10808)
        _, body = await self.get(path, "Happ/3.5")
        self.assertIsInstance(json.loads(body), list)
        for agent, p in (("HiddifyNext/2.5", path), ("v2rayNG/1.10.20", path + "?format=links")):
            head, body = await self.get(p, agent)
            links = base64.b64decode(body).decode().splitlines()
            self.assertTrue(links[0].startswith("vless://") or links[0].startswith("hysteria2://"), agent)
            hy_link = next(l for l in links if l.startswith("hysteria2://"))
            self.assertIn("mport=20000-29999", hy_link, "смена портов в ссылке")
        self.v.json_sub = False
        _, body = await self.get(path, "v2rayNG/1.10.20")
        self.assertTrue(base64.b64decode(body))
        self.v._server.close()


FAKE_AWG = r'''#!/usr/bin/env python3
import base64, hashlib, json, os, sys, time
ST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "awg-state.json")
st = json.load(open(ST)) if os.path.exists(ST) else {"peers": {}, "down": False}
def save(): json.dump(st, open(ST, "w"))
a = sys.argv[1:]
if a == ["genkey"]:
    print(base64.b64encode(os.urandom(32)).decode())
elif a == ["pubkey"]:
    print(base64.b64encode(hashlib.sha256(sys.stdin.read().strip().encode()).digest()).decode())
elif st["down"]:
    print("Unable to access interface"); sys.exit(1)
elif a[0] == "set" and a[3:5] and a[4] == "remove":
    st["peers"].pop(a[3], None); save()
elif a[0] == "set":
    st["peers"][a[3]] = {"ip": a[5], "rx": 0, "tx": 0, "hs": 0}; save()
elif a[1:] == ["awg0", "peers"]:
    print("\n".join(st["peers"]))
elif a[1:] == ["awg0", "dump"]:
    print("priv\tpub\t51820\toff")
    for k, p in st["peers"].items():
        print("\t".join([k, "(none)", "1.2.3.4:5", p["ip"], str(p["hs"]), str(p["rx"]), str(p["tx"]), "25"]))
'''


class AmneziaWG(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        awg = os.path.join(self.d, "awg")
        with open(awg, "w") as f:
            f.write(FAKE_AWG)
        os.chmod(awg, 0o755)
        self.v = self.make(awg={"port": 51820, "server_public_key": "SERVERPUB=", "awg_bin": awg,
                                "params": "Jc=4,Jmin=40,Jmax=70,S1=33,S2=77,H1=101,H2=202,H3=303,H4=404"})

    def peers(self) -> dict:
        with open(os.path.join(self.d, "awg-state.json")) as f:
            return json.load(f)["peers"]

    def set_peers(self, **kw):
        path = os.path.join(self.d, "awg-state.json")
        st = json.load(open(path))
        for pub, vals in kw.items():
            st["peers"][pub].update(vals)
        json.dump(st, open(path, "w"))

    async def test_keys_follow_subscriptions_and_config_file(self):
        await self.started({1: time.time() + 3600, 2: time.time() + 3600})
        self.assertEqual(sorted(p["ip"] for p in self.peers().values()), ["10.66.0.2/32", "10.66.0.3/32"])
        k1 = self.v.awg.state["1"]
        conf = await self.v.awg_config(1, "Телефон")
        self.assertIn(f"PrivateKey = {k1['priv']}", conf)
        self.assertIn("Address = 10.66.0.2/32", conf)
        self.assertIn("Endpoint = 203.0.113.7:51820", conf)
        self.assertIn("PublicKey = SERVERPUB=", conf)
        for line in ("Jc = 4", "S1 = 33", "H4 = 404", "AllowedIPs = 0.0.0.0/0"):
            self.assertIn(line, conf)
        await self.v.issue(3, time.time() + 3600)
        self.assertIn(self.v.awg.state["3"]["pub"], self.peers())
        await self.v.suspend(1, 600)
        self.assertNotIn(k1["pub"], self.peers(), "отключённая подписка без ключа")
        self.assertIsNone(await self.v.awg_config(1, "x"))
        await self.v.resume(1)
        self.assertIn(k1["pub"], self.peers())
        await self.v.revoke(2)
        self.assertNotIn(self.v.awg.state["2"]["pub"], self.peers())
        # интерфейс перезапустили, ключи пропали: синхронизация их возвращает, лишних не оставляет
        json.dump({"peers": {"stranger=": {"ip": "10.66.9.9/32", "rx": 0, "tx": 0, "hs": 0}}, "down": False},
                  open(os.path.join(self.d, "awg-state.json"), "w"))
        await self.v.sync_awg()
        self.assertEqual(set(self.peers()), {self.v.awg.state["1"]["pub"], self.v.awg.state["3"]["pub"]})
        # ключ не меняется: файл у гостя остаётся рабочим
        self.assertEqual(self.v.awg.state["1"], k1)

    async def test_traffic_and_online(self):
        await self.started({1: time.time() + 3600})
        pub = self.v.awg.state["1"]["pub"]
        self.set_peers(**{pub: {"rx": 1000, "tx": 5000, "hs": int(time.time()) - 10}})
        self.assertEqual(await self.v.awg.traffic(), {1: (1000, 5000)})
        self.set_peers(**{pub: {"rx": 1500, "tx": 5000}})
        self.assertEqual(await self.v.awg.traffic(), {1: (500, 0)})
        self.assertEqual(await self.v.awg.online(), {1: 1})
        self.set_peers(**{pub: {"hs": int(time.time()) - 1000}})
        self.assertEqual(await self.v.awg.online(), {})


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
