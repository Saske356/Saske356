"""Тесты сайта маскировки: python3 -m unittest discover -s tests

Сеть не используется: сайты изображают локальные TLS-серверы, Xray — подставной скрипт.
"""

import asyncio
import logging
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import masking  # noqa: E402
from xray_provider import XrayProvider  # noqa: E402

DIR = None


def setUpModule():
    global DIR
    if not shutil.which("openssl"):
        raise unittest.SkipTest("нужен openssl")
    logging.disable(logging.CRITICAL)
    DIR = tempfile.mkdtemp()
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", DIR + "/key",
                    "-out", DIR + "/crt", "-days", "2", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)


def tearDownModule():
    shutil.rmtree(DIR, ignore_errors=True)


async def site(alpn=("h2", "http/1.1"), only_names=None, tls12=False):
    """Локальный «сайт». only_names: отвечать только на эти имена, как делают некоторые сайты."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(DIR + "/crt", DIR + "/key")
    ctx.set_alpn_protocols(list(alpn))
    if tls12:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if only_names is not None:
        ctx.sni_callback = lambda sock, name, _ctx: None if name in only_names else ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

    async def handle(reader, writer):
        writer.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    return server, server.sockets[0].getsockname()[1]


class SiteCheckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._saved = (masking.PORT, masking._ctx)
        masking._ctx = ssl.create_default_context(cafile=DIR + "/crt")
        masking._ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        masking._ctx.set_alpn_protocols(["h2", "http/1.1"])
        self.servers = []

    async def asyncTearDown(self):
        masking.PORT, masking._ctx = self._saved
        for s in self.servers:
            s.close()

    async def start(self, **kw):
        server, port = await site(**kw)
        self.servers.append(server)
        masking.PORT = port
        return server

    async def test_good_site_passes(self):
        await self.start()
        self.assertIsNotNone(await masking.check("localhost"))
        self.assertEqual([h for h, _ in await masking.ranked(["localhost", "localhost"])], ["localhost"])

    async def test_site_without_http2_or_tls13_fails(self):
        await self.start(alpn=("http/1.1",))
        self.assertIsNone(await masking.check("localhost"))
        await self.start(tls12=True)
        self.assertIsNone(await masking.check("localhost"))

    async def test_unreachable_or_wrong_certificate_fails(self):
        server = await self.start()
        self.assertIsNone(await masking.check("127.0.0.1"))  # сертификат выписан на другое имя
        server.close()
        await asyncio.sleep(0.05)
        self.assertIsNone(await masking.check("localhost", timeout=1))

    async def test_tolerates_foreign_name_only_when_site_answers(self):
        await self.start()
        self.assertTrue(await masking.tolerates("localhost", "www.microsoft.com"))
        await self.start(only_names={"localhost"})
        self.assertFalse(await masking.tolerates("localhost", "www.microsoft.com"))
        self.assertTrue(await masking.tolerates("localhost", "localhost"))

    def test_site_names(self):
        self.assertTrue(masking.valid_name("www.example.com"))
        for bad in ("", "next", "http://x.com", "a..com", "x.com;rm", "-a.com", "пример.рф"):
            self.assertFalse(masking.valid_name(bad), bad)
        self.assertTrue(all(masking.valid_name(s) for s in masking.SITES))
        self.assertFalse([s for s in masking.SITES if "microsoft" in s or "apple" in s])


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.xray = os.path.join(self.dir, "xray")
        self.fake_xray("exit 0")
        self.vpn = XrayProvider(
            state_path=self.dir + "/vpn.json", config_path=self.dir + "/config.json", xray_bin=self.xray,
            public_host="198.51.100.1", port=443, sni="www.microsoft.com", private_key="priv",
            public_key="pub", short_id="ab", sub_port=0, restart_cmd=("true",))
        self.vpn.state["users"]["7"] = 4102444800.0

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake_xray(self, body: str):
        with open(self.xray, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(self.xray, 0o755)

    def reality(self):
        return self.vpn.build_config()["inbounds"][0]["streamSettings"]["realitySettings"]

    async def test_site_from_env_until_changed_then_saved(self):
        self.assertEqual(self.vpn.sni, "www.microsoft.com")
        self.assertTrue(await self.vpn.change_sni("www.x-kom.pl", grace=True))
        self.assertEqual(self.vpn.sni, "www.x-kom.pl")
        rs = self.reality()
        self.assertEqual(rs["dest"], "www.x-kom.pl:443")
        self.assertEqual(rs["serverNames"], ["www.x-kom.pl", "www.microsoft.com"])  # старые ключи ещё сутки
        self.assertIn("sni=www.x-kom.pl&", self.vpn.links(7)[0])
        with open(self.vpn.config_path) as f:
            self.assertIn('"www.x-kom.pl:443"', f.read())
        again = XrayProvider(state_path=self.vpn.state_path, config_path="x.json", xray_bin="/nonexistent",
                             public_host="h", port=443, sni="www.microsoft.com", private_key="a",
                             public_key="b", short_id="c", sub_port=0)
        self.assertEqual(again.sni, "www.x-kom.pl")

    async def test_old_keys_stop_after_grace_or_without_it(self):
        await self.vpn.change_sni("www.x-kom.pl", grace=False)
        self.assertEqual(self.reality()["serverNames"], ["www.x-kom.pl"])
        await self.vpn.change_sni("www.morele.net", grace=True)
        self.assertEqual(self.reality()["serverNames"], ["www.morele.net", "www.x-kom.pl"])
        self.vpn.masking["prev"][0]["until"] -= 2 * 86400
        self.assertEqual(self.reality()["serverNames"], ["www.morele.net"])

    async def test_rejected_site_is_rolled_back(self):
        self.fake_xray('grep -q "www.bad.pl" "$4" && { echo "infra/conf: bad"; exit 23; }\nexit 0')
        self.assertFalse(await self.vpn.change_sni("www.bad.pl", grace=True))
        self.assertEqual(self.vpn.sni, "www.microsoft.com")
        self.assertEqual(self.vpn.masking["prev"], [])
        self.assertEqual(self.reality()["serverNames"], ["www.microsoft.com"])

    async def test_xray_warning_about_risky_site_is_detected(self):
        self.fake_xray('grep -q "www.apple.com:443" "$4" && echo \'[Warning] REALITY: Choosing "www.apple.com" '
                       'as the target will increase the likelihood of your server IP being blocked\'\n'
                       'grep -q "www.bad.pl" "$4" && exit 23\nexit 0')
        self.assertTrue(await self.vpn.site_flagged("www.apple.com"))
        self.assertFalse(await self.vpn.site_flagged("www.x-kom.pl"))
        self.assertIsNone(await self.vpn.site_flagged("www.bad.pl"))
        self.assertEqual(self.vpn.sni, "www.microsoft.com")  # проверка ничего не меняет
        self.assertFalse(os.path.exists(self.dir + "/config.site.json"))

    async def test_settings_and_fast_subscription_refresh(self):
        self.assertEqual((self.vpn.masking["auto"], self.vpn.masking["every"]), (True, 0))
        self.vpn.set_masking(auto=False, every=24)
        self.assertEqual((self.vpn.masking["auto"], self.vpn.masking["every"]), (False, 24))
        _, headers = self.vpn.subscription(7)
        self.assertEqual(headers["profile-update-interval"], "1")


if __name__ == "__main__":
    unittest.main()
