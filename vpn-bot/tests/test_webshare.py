"""Купленные прокси списком (Webshare): python3 -m unittest discover -s tests

В сеть тест не ходит: скачивание и проверка прокси подменены.
"""

import asyncio, json, os, sys, tempfile, time, unittest
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import public_proxies as pp  # noqa: E402
import webshare  # noqa: E402
import xray_provider as xp  # noqa: E402


class Parse(unittest.TestCase):
    def test_formats(self):
        text = ("p.webshare.io:80:user-1:pa:ss\n"          # пароль с двоеточием не разбирается как 4 поля
                "1.2.3.4:6000:user-2:pass2\n"
                "user3:p@ss3@5.6.7.8:7000\n"
                "9.9.9.9:1080\n"
                "http://u:p@8.8.8.8:3128\n"
                "# комментарий\n\nмусор\n1.2.3.4:6000:user-2:pass2\n")
        self.assertEqual(webshare.parse(text), [
            "socks5://user-2:pass2@1.2.3.4:6000",
            "socks5://user3:p%40ss3@5.6.7.8:7000",
            "socks5://9.9.9.9:1080",
            "http://u:p@8.8.8.8:3128",
        ])

    def test_by_country_keeps_fastest_and_limits(self):
        found = [("a", "de", 100), ("b", "de", 300), ("c", "us", 900), ("d", "nl", 200), ("e", "??", 1)]
        self.assertEqual(webshare.by_country(found, limit=2), {"de": [("a", 100), ("b", 300)], "nl": [("d", 200)]})


class Scan(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_to_http_and_sorts_by_speed(self):
        saved = pp.probe
        answers = {"socks5://a:b@1.1.1.1:80": None, "http://a:b@1.1.1.1:80": pp.Probe("de", 300),
                   "socks5://a:b@2.2.2.2:80": pp.Probe("nl", 100), "socks5://a:b@3.3.3.3:80": None,
                   "http://a:b@3.3.3.3:80": None}
        pp.probe = AsyncMock(side_effect=lambda url, *a, **k: answers[url])
        try:
            found = await webshare.scan(["socks5://a:b@1.1.1.1:80", "socks5://a:b@2.2.2.2:80", "socks5://a:b@3.3.3.3:80"])
        finally:
            pp.probe = saved
        self.assertEqual(found, [("socks5://a:b@2.2.2.2:80", "nl", 100), ("http://a:b@1.1.1.1:80", "de", 300)])


class Provider(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.d = tempfile.mkdtemp()
        self.v = xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin="/nonexistent", public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Arise VPN",
            default_location="🇵🇱 Польша", restart_cmd=("true",), xray_enabled=False,
            hy2={"port": 443, "sni": "www.example.com", "pin": "", "obfs": "", "obfs_port": 0,
                 "stats_ports": [], "stats_secret": "s"},
            hy2_locs={"ports": range(30000, 30010), "dir": os.path.join(self.d, "hy"), "stats_base": 20830,
                      "systemctl": ("true",)})
        self.v.schedule_apply = lambda delay=2.0: None

    async def test_added_kept_swapped_and_manual_untouched(self):
        a, b, c = "socks5://u:p@1.1.1.1:1", "socks5://u:p@2.2.2.2:1", "socks5://u:p@3.3.3.3:1"
        self.assertEqual(self.v.set_paid_location("de", "🇩🇪 Германия", [a, b], ms=100), "added")
        loc = self.v.paid_locations()[0]
        self.assertEqual((loc["proxy"], loc["pool"], loc["tcp_only"]), (a, [a, b], True))
        self.assertEqual(self.v.set_paid_location("de", "🇩🇪 Германия", [b, a], ms=90), "kept",
                         "рабочий жив — не трогаем, чтобы не перезапускать")
        self.assertEqual(self.v.paid_locations()[0]["proxy"], a)
        self.assertEqual(self.v.set_paid_location("de", "🇩🇪 Германия", [b, c]), "swapped")
        self.assertEqual(self.v.paid_locations()[0]["proxy"], b)
        self.v.add_location("us", "🇺🇸 США", "socks5://mine:x@4.4.4.4:1")
        self.assertEqual(self.v.set_paid_location("us", "🇺🇸 США", [c]), "", "свою страну через /addloc не трогаем")
        self.v.set_auto_location("nl", "🇳🇱 Нидерланды", ["socks5://9.9.9.9:1080"], apply=False)
        self.assertEqual(self.v.set_paid_location("nl", "🇳🇱 Нидерланды", [c]), "added", "авто-страна уступает купленной")
        self.assertFalse(next(l for l in self.v.locations if l["code"] == "nl").get("auto"))

    async def test_hysteria_of_paid_country_sends_only_tcp(self):
        self.v.set_paid_location("de", "🇩🇪 Германия", ["socks5://u:p@1.1.1.1:1"])
        loc = self.v.paid_locations()[0]
        acl = json.loads(self.v._hy2_loc_config(loc, 30000))["acl"]["inline"]
        self.assertIn("direct(all, udp/53)", acl)
        self.assertIn("reject(all, udp)", acl)

    async def test_dead_proxy_switches_to_backup_at_once(self):
        a, b = "socks5://u:p@1.1.1.1:1", "socks5://u:p@2.2.2.2:1"
        self.v.set_paid_location("de", "🇩🇪 Германия", [a, b])
        saved = pp.direct_ok, pp.probe
        pp.direct_ok = AsyncMock(return_value=True)
        pp.probe = AsyncMock(side_effect=lambda url, *a_, **k: None if url == a else pp.Probe("de", 50))
        try:
            changes = await self.v.check_proxies()
        finally:
            pp.direct_ok, pp.probe = saved
        loc = self.v.paid_locations()[0]
        self.assertEqual((loc["proxy"], bool(loc.get("down")), changes), (b, False, []),
                         "страна не скрылась: сразу взят живой запасной")


if __name__ == "__main__":
    unittest.main()
