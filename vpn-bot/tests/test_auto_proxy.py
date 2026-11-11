"""Тесты авто-стран на локальных тестовых прокси: python3 -m unittest discover -s tests

Настоящих публичных прокси и сети тесты не трогают. Вместо этого на 127.0.0.1 поднимаются
SOCKS5- и HTTP-прокси и HTTPS-сайт, который сообщает «страну» подключения.
"""

import asyncio
import base64
import logging
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import public_proxies as pp  # noqa: E402
from auto_proxy import AutoProxy  # noqa: E402
from proxy_relay import Relay  # noqa: E402
from xray_provider import XrayProvider  # noqa: E402

CERT_DIR = None


def make_cert(name: str) -> tuple[str, str]:
    cert, key = os.path.join(CERT_DIR, name + ".crt"), os.path.join(CERT_DIR, name + ".key")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                    "-out", cert, "-days", "2", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
    return cert, key


def setUpModule():
    global CERT_DIR
    if not shutil.which("openssl"):
        raise unittest.SkipTest("нужен openssl")
    logging.disable(logging.CRITICAL)  # обрывы связи в тестах устроены нарочно
    CERT_DIR = tempfile.mkdtemp()
    make_cert("good")
    make_cert("other")


def tearDownModule():
    shutil.rmtree(CERT_DIR, ignore_errors=True)


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        writer.write_eof()
    except (ConnectionError, OSError):
        writer.close()


class TraceSite:
    """HTTPS-сайт, который отвечает как cloudflare.com/cdn-cgi/trace."""

    def __init__(self, country: str, cert: str = "good"):
        self.country, self.cert = country, cert

    async def start(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.path.join(CERT_DIR, self.cert + ".crt"), os.path.join(CERT_DIR, self.cert + ".key"))
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=ctx)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def _handle(self, reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            body = f"fl=1\nh=localhost\nip=203.0.113.9\nloc={self.country.upper()}\ntls=TLSv1.3\n".encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n"
                         + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()

    def close(self):
        self.server.close()


class FakeProxy:
    """Тестовый прокси. mode: ok, blackhole (молчит), refuse (не открывает туннель), mitm."""

    def __init__(self, kind: str, country: str, auth=None, mode: str = "ok", delay: float = 0.0):
        self.kind, self.country, self.auth, self.mode, self.delay = kind, country, auth, mode, delay
        self.tunnels = 0
        self.writers = set()

    async def start(self):
        self.site = await TraceSite(self.country, "other" if self.mode == "mitm" else "good").start()
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    @property
    def url(self) -> str:
        cred = f"{self.auth[0]}:{self.auth[1]}@" if self.auth else ""
        return f"{self.kind}://{cred}127.0.0.1:{self.port}"

    def kill(self):
        self.server.close()
        self.site.close()
        for w in list(self.writers):
            w.close()

    async def _handle(self, reader, writer):
        self.writers.add(writer)
        try:
            if self.mode == "blackhole":
                await asyncio.sleep(3600)
            target = await (self._socks5(reader, writer) if self.kind == "socks5" else self._http(reader, writer))
            if not target:
                return
            host, port = target
            if (host, port) == (pp.CHECK_HOST, pp.CHECK_PORT):
                host, port = "127.0.0.1", self.site.port  # «выход в интернет» из страны прокси
            await asyncio.sleep(self.delay)
            up_reader, up_writer = await asyncio.open_connection(host, port)
            self.writers.add(up_writer)
            writer.write(b"\x05\x00\x00\x01" + bytes(6) if self.kind == "socks5"
                         else b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.tunnels += 1
            try:
                await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
            finally:
                self.writers.discard(up_writer)
                up_writer.close()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            self.writers.discard(writer)
            writer.close()

    async def _socks5(self, reader, writer):
        _, n = await reader.readexactly(2)
        methods = await reader.readexactly(n)
        if self.auth:
            if 2 not in methods:
                writer.write(b"\x05\xff")
                return None
            writer.write(b"\x05\x02")
            await reader.readexactly(1)
            user = await reader.readexactly((await reader.readexactly(1))[0])
            pwd = await reader.readexactly((await reader.readexactly(1))[0])
            if (user.decode(), pwd.decode()) != self.auth:
                writer.write(b"\x01\x01")
                return None
            writer.write(b"\x01\x00")
        else:
            writer.write(b"\x05\x00")
        _, _, _, atyp = await reader.readexactly(4)
        if atyp == 3:
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
        else:
            host = ".".join(str(b) for b in await reader.readexactly(4))
        port = int.from_bytes(await reader.readexactly(2), "big")
        if self.mode == "refuse":
            writer.write(b"\x05\x05\x00\x01" + bytes(6))
            return None
        return host, port

    async def _http(self, reader, writer):
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        host, _, port = head.split()[1].rpartition(":")
        if self.auth:
            want = "Basic " + base64.b64encode(f"{self.auth[0]}:{self.auth[1]}".encode()).decode()
            if f"Proxy-Authorization: {want}" not in head:
                writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                return None
        if self.mode == "refuse":
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return None
        return host, int(port)


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.things = []
        self.direct = await TraceSite("pl").start()
        self.things.append(self.direct)
        self._saved = (pp.CHECK_HOST, pp.CHECK_PORT, pp._ssl_ctx)
        pp.CHECK_HOST, pp.CHECK_PORT = "localhost", self.direct.port
        pp._ssl_ctx = ssl.create_default_context(cafile=os.path.join(CERT_DIR, "good.crt"))

    async def asyncTearDown(self):
        pp.CHECK_HOST, pp.CHECK_PORT, pp._ssl_ctx = self._saved
        for t in self.things:
            t.kill() if isinstance(t, FakeProxy) else t.close()
        await asyncio.sleep(0)

    async def proxy(self, kind="socks5", country="nl", **kw) -> FakeProxy:
        p = await FakeProxy(kind, country, **kw).start()
        self.things.append(p)
        return p


class ProbeTests(Base):
    async def test_socks5_and_http_report_exit_country(self):
        for kind in ("socks5", "http"):
            p = await self.proxy(kind, "nl")
            res = await pp.probe(p.url)
            self.assertIsNotNone(res, kind)
            self.assertEqual(res.country, "nl")
            self.assertEqual(p.tunnels, 1)

    async def test_login_and_password(self):
        for kind in ("socks5", "http"):
            p = await self.proxy(kind, "de", auth=("user", "p@ss"))
            self.assertEqual((await pp.probe(f"{kind}://user:p%40ss@127.0.0.1:{p.port}")).country, "de")
            self.assertIsNone(await pp.probe(f"{kind}://user:wrong@127.0.0.1:{p.port}"), kind)
            self.assertIsNone(await pp.probe(f"{kind}://127.0.0.1:{p.port}"), kind)

    async def test_broken_proxies_fail(self):
        dead = await self.proxy()
        dead.kill()
        self.assertIsNone(await pp.probe(dead.url))
        for kind in ("socks5", "http"):
            self.assertIsNone(await pp.probe((await self.proxy(kind, mode="refuse")).url), kind)
            self.assertIsNone(await pp.probe((await self.proxy(kind, mode="blackhole")).url, timeout=0.3), kind)

    async def test_proxy_that_replaces_certificate_fails(self):
        for kind in ("socks5", "http"):
            self.assertIsNone(await pp.probe((await self.proxy(kind, mode="mitm")).url), kind)

    async def test_direct_ok(self):
        self.assertTrue(await pp.direct_ok())
        self.direct.close()
        await asyncio.sleep(0.05)
        self.assertFalse(await pp.direct_ok(timeout=1))

    async def test_pick_working_filters_country_and_prefers_fast(self):
        slow = await self.proxy("socks5", "nl", delay=0.3)
        fast = await self.proxy("http", "nl")
        other = await self.proxy("socks5", "de")
        dead = await self.proxy("socks5", "nl")
        dead.kill()
        failed = set()
        found = await pp.pick_working([slow.url, dead.url, other.url, fast.url], "nl", need=2, failed=failed)
        self.assertEqual([u for u, _ in found], [fast.url, slow.url])
        self.assertEqual(failed, {dead.url, other.url})
        self.assertEqual(await pp.pick_working([other.url], "nl"), [])


class RelayTests(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.demoted = []
        self.relay = Relay(0, "secret", on_demote=lambda code, url: self.demoted.append((code, url)),
                           connect_timeout=1.0)
        self.assertTrue(await self.relay.start())

    async def asyncTearDown(self):
        await self.relay.stop()
        await super().asyncTearDown()

    def via(self, code="nl", pwd="secret") -> str:
        return f"socks5://{code}:{pwd}@127.0.0.1:{self.relay.port}"

    async def test_traffic_goes_through_upstream(self):
        for kind in ("socks5", "http"):
            p = await self.proxy(kind, "nl")
            self.relay.set_route("nl", [p.url])
            self.assertEqual((await pp.probe(self.via())).country, "nl")
            self.assertEqual(p.tunnels, 1)

    async def test_rejects_wrong_password_and_unknown_country(self):
        p = await self.proxy()
        self.relay.set_route("nl", [p.url])
        self.assertIsNone(await pp.probe(self.via(pwd="nope")))
        self.assertIsNone(await pp.probe(self.via(code="us")))
        self.assertEqual(p.tunnels, 0)

    async def test_fails_over_to_backup_within_same_connection(self):
        dead, good = await self.proxy(), await self.proxy("http")
        dead.kill()
        self.relay.set_route("nl", [dead.url, good.url])
        self.assertEqual((await pp.probe(self.via())).country, "nl")  # первое же подключение прошло
        self.assertEqual(self.demoted, [])
        self.assertIsNotNone(await pp.probe(self.via()))
        self.assertEqual(self.demoted, [("nl", dead.url)])
        self.assertEqual(self.relay.routes["nl"], [good.url, dead.url])

    async def test_refused_target_does_not_blame_proxy(self):
        p = await self.proxy(mode="refuse")
        self.relay.set_route("nl", [p.url])
        for _ in range(3):
            self.assertIsNone(await pp.probe(self.via()))
        self.assertEqual(self.demoted, [])

    async def test_reply_arrives_after_client_finished_sending(self):
        async def count(reader, writer):
            n = 0
            while data := await reader.read(65536):
                n += len(data)
            writer.write(str(n).encode())
            await writer.drain()
            writer.close()
        server = await asyncio.start_server(count, "127.0.0.1", 0)
        for kind in ("socks5", "http"):
            p = await self.proxy(kind)
            self.relay.set_route("nl", [p.url])
            sock = await pp.open_tunnel(self.via(), "127.0.0.1", server.sockets[0].getsockname()[1])
            reader, writer = await asyncio.open_connection(sock=sock)
            writer.write(b"x" * 200_000)
            writer.write_eof()
            self.assertEqual(await asyncio.wait_for(reader.read(), 10), b"200000", kind)
            writer.close()
        server.close()

    async def test_large_payload_both_ways(self):
        async def echo(reader, writer):
            await pipe(reader, writer)
            writer.close()
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        p = await self.proxy("http")
        self.relay.set_route("nl", [p.url])
        sock = await pp.open_tunnel(self.via(), "127.0.0.1", port)
        reader, writer = await asyncio.open_connection(sock=sock)
        payload = os.urandom(3_000_000)
        writer.write(payload)
        got = await asyncio.wait_for(reader.readexactly(len(payload)), 20)
        self.assertEqual(got, payload)
        writer.close()
        server.close()

    async def test_udp_is_declined(self):
        p = await self.proxy()
        self.relay.set_route("nl", [p.url])
        reader, writer = await asyncio.open_connection("127.0.0.1", self.relay.port)
        writer.write(b"\x05\x01\x02")
        self.assertEqual(await reader.readexactly(2), b"\x05\x02")
        writer.write(b"\x01\x02nl\x06secret")
        self.assertEqual(await reader.readexactly(2), b"\x01\x00")
        writer.write(b"\x05\x03\x00\x01" + bytes(6))  # UDP ASSOCIATE
        self.assertEqual((await reader.readexactly(2))[1], 7)
        writer.close()


class ManagerTests(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.dir = tempfile.mkdtemp()
        self.pool = {}
        self._fetch = pp.fetch_pool

        async def fake_pool(force=False):
            return self.pool
        pp.fetch_pool = fake_pool

    async def asyncTearDown(self):
        pp.fetch_pool = self._fetch
        if getattr(self, "mgr", None):
            await self.mgr.relay.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        await super().asyncTearDown()

    async def manager(self, countries=(), maxn=8) -> AutoProxy:
        self.vpn = XrayProvider(
            state_path=os.path.join(self.dir, "vpn.json"), config_path=os.path.join(self.dir, "config.json"),
            xray_bin="/nonexistent", public_host="198.51.100.1", port=443, sni="www.microsoft.com",
            private_key="priv", public_key="pub", short_id="ab", sub_port=0,
            auto_enabled=True, auto_countries=countries, auto_max=maxn, relay_port=0)
        self.applies = 0

        def count(delay=2.0):
            self.applies += 1
        self.vpn.schedule_apply = count
        self.vpn.state["users"]["7"] = 4102444800.0
        self.notes = []

        async def notify(text):
            self.notes.append(text)
        self.mgr = AutoProxy(self.vpn, notify)
        self.assertTrue(await self.mgr.start())
        self.vpn.relay_port = self.mgr.relay.port
        return self.mgr

    def loc(self, code):
        return next((l for l in self.vpn.locations if l["code"] == code), None)

    async def through(self, code):
        """Подключение так, как его сделает Xray: через ретранслятор с логином страны."""
        ob = self.vpn.relay_outbound(code)["settings"]["servers"][0]
        u = ob["users"][0]
        return await pp.probe(f"socks5://{u['user']}:{u['pass']}@{ob['address']}:{ob['port']}")

    async def test_adds_countries_with_backups_and_builds_config(self):
        nl = [await self.proxy("socks5", "nl"), await self.proxy("http", "nl"), await self.proxy("socks5", "nl")]
        de = [await self.proxy("http", "de")]
        liar = await self.proxy("socks5", "de")  # в списке записан как nl, а выходит из de
        self.pool = {"nl": [liar.url] + [p.url for p in nl], "de": [de[0].url]}
        mgr = await self.manager(countries=("nl", "de"))
        report = await mgr.refresh()
        self.assertIn("Добавлены", report)
        self.assertEqual(sorted(self.loc("nl")["pool"]), sorted(p.url for p in nl))
        self.assertEqual(self.loc("de")["pool"], [de[0].url])
        self.assertEqual(self.applies, 2)

        cfg = self.vpn.build_config()
        out = {o["tag"]: o for o in cfg["outbounds"]}
        server = out["out-nl"]["settings"]["servers"][0]
        self.assertEqual((out["out-nl"]["protocol"], server["address"], server["users"][0]["user"]),
                         ("socks", "127.0.0.1", "nl"))
        nl_rules = [r for r in cfg["routing"]["rules"] if r.get("user") == ["u7.nl"]]
        self.assertEqual([(r.get("network"), r.get("port"), r["outboundTag"]) for r in nl_rules],
                         [("udp", "53", "direct"), ("udp", None, "block"), (None, None, "out-nl")])
        self.assertEqual(len(self.vpn.links(7)), 3)
        self.assertEqual((await self.through("nl")).country, "nl")
        self.assertEqual((await self.through("de")).country, "de")

    async def test_dead_proxy_is_replaced_without_xray_restart(self):
        a, b, c, d = [await self.proxy("socks5", "nl") for _ in range(4)]
        self.pool = {"nl": [a.url, b.url, c.url]}
        mgr = await self.manager(countries=("nl",))
        await mgr.refresh()
        active = self.loc("nl")["proxy"]
        applies = self.applies
        next(p for p in (a, b, c) if p.url == active).kill()

        self.assertEqual((await self.through("nl")).country, "nl")  # ушло через запасной сразу
        self.pool = {"nl": [a.url, b.url, c.url, d.url]}
        report = await mgr.refresh()
        self.assertIn("Прокси заменён", report)
        loc = self.loc("nl")
        self.assertNotEqual(loc["proxy"], active)
        self.assertNotIn(active, loc["pool"])
        self.assertEqual(len(loc["pool"]), 3)
        self.assertEqual(loc["swaps"], 1)
        self.assertEqual(self.applies, applies)
        self.assertEqual(await mgr.refresh(), "")  # всё живо: тишина

    async def test_relay_failover_is_saved_and_reported(self):
        a, b = await self.proxy("socks5", "nl"), await self.proxy("http", "nl")
        self.pool = {"nl": [a.url, b.url]}
        mgr = await self.manager(countries=("nl",))
        await mgr.refresh()
        self.vpn.set_auto(enabled=False)  # чтобы фоновая проверка не вмешалась в тест
        first = self.loc("nl")["proxy"]
        (a if a.url == first else b).kill()
        for _ in range(Relay.FAIL_LIMIT):
            self.assertIsNotNone(await self.through("nl"))
        self.assertNotEqual(self.loc("nl")["proxy"], first)
        self.assertEqual(self.loc("nl")["pool"][-1], first)
        self.assertIn("Прокси заменён", await mgr.refresh())

    async def test_country_hidden_when_no_proxies_and_returns_later(self):
        a = await self.proxy("socks5", "nl")
        self.pool = {"nl": [a.url]}
        mgr = await self.manager(countries=("nl",))
        await mgr.refresh()
        a.kill()
        self.assertIn("скрыты", await mgr.refresh())
        self.assertTrue(self.loc("nl")["down"])
        self.assertEqual(len(self.vpn.links(7)), 1)
        self.assertEqual(await mgr.refresh(), "")
        b = await self.proxy("http", "nl")
        self.pool = {"nl": [b.url]}
        self.assertIn("Снова работают", await mgr.refresh())
        self.assertFalse(self.loc("nl")["down"])
        self.assertEqual((await self.through("nl")).country, "nl")

    async def test_discovery_respects_limit_order_and_exclusions(self):
        px = {cc: await self.proxy("socks5", cc) for cc in ("bd", "us", "nl", "de", "pl")}
        self.pool = {cc: [p.url] for cc, p in px.items()}
        mgr = await self.manager(maxn=2)
        self.vpn.add_location("pl", "🇵🇱 Купленная", "socks5://127.0.0.1:9")
        self.vpn.set_auto(exclude=["de"])
        await mgr.refresh()
        self.assertEqual([l["code"] for l in self.vpn.auto_locations()], ["nl", "us"])
        self.assertFalse(self.loc("pl").get("auto"))

        self.pool.pop("nl")  # страна пропала из списков, но её прокси жив: остаётся
        self.assertEqual(await mgr.refresh(), "")
        self.assertEqual([l["code"] for l in self.vpn.auto_locations()], ["nl", "us"])

        px["nl"].kill()  # при подборе страна без прокси уступает место другой
        report = await mgr.refresh()
        self.assertIn("убраны", report)
        self.assertEqual(sorted(l["code"] for l in self.vpn.auto_locations()), ["bd", "us"])

    async def test_no_changes_when_server_itself_is_offline(self):
        a = await self.proxy("socks5", "nl")
        self.pool = {"nl": [a.url]}
        mgr = await self.manager(countries=("nl",))
        await mgr.refresh()
        self.direct.close()
        a.kill()
        await asyncio.sleep(0.05)
        self.assertEqual(await mgr.refresh(), "")
        self.assertFalse(self.loc("nl").get("down"))
        self.assertTrue(mgr.last_note)

    async def test_changing_country_list_removes_old_ones(self):
        nl, de = await self.proxy("socks5", "nl"), await self.proxy("socks5", "de")
        self.pool = {"nl": [nl.url], "de": [de.url]}
        mgr = await self.manager(countries=("nl",))
        await mgr.refresh()
        self.vpn.set_auto(countries=["de"])
        report = await mgr.refresh()
        self.assertIn("Убраны", report)
        self.assertEqual([l["code"] for l in self.vpn.auto_locations()], ["de"])
        self.assertNotIn("nl", mgr.relay.routes)

    async def test_tick_notifies_only_when_enabled(self):
        nl = await self.proxy("socks5", "nl")
        self.pool = {"nl": [nl.url]}
        mgr = await self.manager(countries=("nl",))
        self.vpn.set_auto(enabled=False)
        await mgr.tick()
        self.assertEqual((self.notes, self.vpn.auto_locations()), ([], []))
        self.vpn.set_auto(enabled=True, notify=False)
        await mgr.tick()
        self.assertEqual((self.notes, len(self.vpn.auto_locations())), ([], 1))

    async def test_manual_proxy_check_catches_expired_login(self):
        await self.manager()
        good = await self.proxy("socks5", "fr", auth=("u", "p"))
        self.vpn.add_location("fr", "🇫🇷 Франция", f"socks5://u:p@127.0.0.1:{good.port}")
        self.vpn.add_location("it", "🇮🇹 Италия", f"socks5://u:old@127.0.0.1:{good.port}")
        changes = await self.vpn.check_proxies()
        self.assertEqual([(l["code"], ok) for l, ok in changes], [("it", False)])
        self.loc("it")["proxy"] = f"socks5://u:p@127.0.0.1:{good.port}"
        self.assertEqual([(l["code"], ok) for l, ok in await self.vpn.check_proxies()], [("it", True)])

    async def test_state_from_previous_version_is_upgraded(self):
        await self.manager()
        self.vpn.state["locations"].append({"code": "nl", "name": "🇳🇱 Нидерланды", "proxy": "http://127.0.0.1:9",
                                            "auto": True, "country": "nl", "down": False})
        self.vpn._save()
        again = XrayProvider(state_path=self.vpn.state_path, config_path="x.json", xray_bin="/nonexistent",
                             public_host="h", port=443, sni="s", private_key="a", public_key="b",
                             short_id="c", sub_port=0)
        loc = next(l for l in again.locations if l["code"] == "nl")
        self.assertEqual(loc["pool"], ["http://127.0.0.1:9"])
        self.assertTrue(again.auto["enabled"])
        self.assertEqual(again.auto["exclude"], [])


if __name__ == "__main__":
    unittest.main()
