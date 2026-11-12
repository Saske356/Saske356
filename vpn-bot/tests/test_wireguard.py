"""WireGuard: ключи по подпискам, включение из админки: python3 -m unittest discover -s tests

Вместо утилиты wg — заглушка на Python, которая хранит ключи интерфейса в файле.
"""

import asyncio, json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xray_provider as xp  # noqa: E402

FAKE_WG = r'''#!/usr/bin/env python3
import base64, hashlib, json, os, sys, time
ST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wg-state.json")
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
elif a[1:] == ["wg0", "peers"]:
    print("\n".join(st["peers"]))
elif a[1:] == ["wg0", "dump"]:
    print("priv\tpub\t51820\toff")
    for k, p in st["peers"].items():
        print("\t".join([k, "(none)", "1.2.3.4:5", p["ip"], str(p["hs"]), str(p["rx"]), str(p["tx"]), "25"]))
'''


class WireGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.d = tempfile.mkdtemp()
        wg = os.path.join(self.d, "wg")
        with open(wg, "w") as f:
            f.write(FAKE_WG)
        os.chmod(wg, 0o755)
        self.v = xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn.json"), config_path=os.path.join(self.d, "config.json"),
            xray_bin="/nonexistent", public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇵🇱 Польша", restart_cmd=("true",), xray_enabled=False,
            wg={"port": 51820, "server_public_key": "SERVERPUB=", "wg_bin": wg})
        self.units = []
        real = self.v._run

        async def run(*cmd):
            if cmd[0] == "systemctl":
                self.units.append(" ".join(cmd[1:]))
                return 0, ""
            return await real(*cmd)
        self.v._run = run
        await self.v.sync({1: time.time() + 3600, 2: time.time() + 3600})

    def peers(self) -> dict:
        path = os.path.join(self.d, "wg-state.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)["peers"]

    async def test_off_by_default_then_toggled_from_admin(self):
        self.assertFalse(self.v.wg_on)
        self.assertIsNone(await self.v.wg_config(1, "x"), "выключен — файла нет")
        self.assertEqual(self.peers(), {}, "выключенный WireGuard ключи не трогает")
        ok, _ = await self.v.set_wg(True)
        self.assertTrue(ok and self.v.wg_on)
        self.assertIn("enable --now wg-quick@wg0", self.units)
        self.assertEqual(sorted(p["ip"] for p in self.peers().values()), ["10.67.0.2/32", "10.67.0.3/32"])
        conf = await self.v.wg_config(1, "Телефон")
        k1 = self.v.wg.state["1"]
        for line in (f"PrivateKey = {k1['priv']}", "Address = 10.67.0.2/32", "Endpoint = 203.0.113.7:51820",
                     "PublicKey = SERVERPUB=", "AllowedIPs = 0.0.0.0/0"):
            self.assertIn(line, conf)
        self.assertNotIn("Jc", conf, "обычный WireGuard без параметров маскировки")
        await self.v.issue(3, time.time() + 3600)
        self.assertIn(self.v.wg.state["3"]["pub"], self.peers())
        await self.v.suspend(1, 600)
        self.assertNotIn(k1["pub"], self.peers())
        await self.v.resume(1)
        self.assertIn(k1["pub"], self.peers())
        await self.v.revoke(2)
        self.assertNotIn(self.v.wg.state["2"]["pub"], self.peers())
        ok, _ = await self.v.set_wg(False)
        self.assertFalse(self.v.wg_on)
        self.assertIn("disable --now wg-quick@wg0", self.units)
        self.assertEqual(self.v.wg.state["1"], k1, "ключ сохраняется: после включения файл у гостя рабочий")

    async def test_happ_gets_wireguard_as_xray_config(self):
        self.assertIsNone(await self.v.wg_subscription(1), "выключен — подписки нет")
        await self.v.set_wg(True)
        await self.v.start_sub_server("127.0.0.1")
        port = self.v._server.sockets[0].getsockname()[1]
        url = self.v.wg_sub_url(1)
        self.assertTrue(url.endswith("/wg"))
        path = url.split(f":{self.v.sub_port}", 1)[-1] if "/sub/" in url else url
        path = path[path.index("/sub/"):]
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nUser-Agent: Happ/3.5\r\n\r\n".encode()); await w.drain()
        data = await r.read(); w.close()
        head, _, body = data.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.1 200"), head)
        cfg = json.loads(body)[0]
        out = cfg["outbounds"][0]
        k = self.v.wg.state["1"]
        self.assertEqual((out["protocol"], out["settings"]["secretKey"], out["settings"]["address"]),
                         ("wireguard", k["priv"], ["10.67.0.2/32"]))
        peer = out["settings"]["peers"][0]
        self.assertEqual((peer["publicKey"], peer["endpoint"]), ("SERVERPUB=", "203.0.113.7:51820"))
        self.assertEqual(cfg["remarks"], "🇵🇱 Польша · WireGuard")
        self.assertIn(k["pub"], self.peers(), "ключ есть на сервере")
        # основная подписка по тому же адресу без /wg не изменилась
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(f"GET {path[:-3]} HTTP/1.1\r\nHost: x\r\n\r\n".encode()); await w.drain()
        data = await r.read(); w.close()
        self.assertNotIn(b"wireguard", data)
        await self.v.set_wg(False)
        self.assertIsNone(await self.v.wg_subscription(1))
        self.v._server.close()

    async def test_amneziawg_next_to_wireguard(self):
        awg = os.path.join(self.d, "awgdir")
        os.makedirs(awg)
        with open(os.path.join(awg, "awg"), "w") as f:
            f.write(FAKE_WG.replace("wg-state.json", "awg-state.json").replace('"wg0"', '"awg0"'))
        os.chmod(os.path.join(awg, "awg"), 0o755)
        v = xp.XrayProvider(
            state_path=os.path.join(self.d, "vpn2.json"), config_path=os.path.join(self.d, "config2.json"),
            xray_bin="/nonexistent", public_host="203.0.113.7", port=443, sni="www.example.com",
            private_key="PRIV", public_key="PUB", short_id="00ff", sub_port=0, brand="Aurora VPN",
            default_location="🇵🇱 Польша", restart_cmd=("true",), xray_enabled=False,
            wg={"port": 51820, "server_public_key": "SERVERPUB=", "wg_bin": os.path.join(self.d, "wg")},
            awg={"port": 51821, "server_public_key": "AWGPUB=", "wg_bin": os.path.join(awg, "awg"),
                 "iface": "awg0", "net": "10.66.0.0/16", "unit": "awg-quick@awg0",
                 "params": "Jc=4,Jmin=40,Jmax=70,S1=33,S2=77,H1=101,H2=202,H3=303,H4=404"})
        units = []
        real = v._run

        async def run(*cmd):
            if cmd[0] == "systemctl":
                units.append(" ".join(cmd[1:]))
                return 0, ""
            return await real(*cmd)
        v._run = run
        await v.sync({1: time.time() + 3600})
        ok, _ = await v.set_tunnel("awg", True)
        self.assertTrue(ok and v.awg_on and not v.wg_on, "каждый включается отдельно")
        self.assertIn("enable --now awg-quick@awg0", units)
        conf = await v.tunnel_config("awg", 1, "Телефон")
        for line in ("Address = 10.66.0.2/32", "Endpoint = 203.0.113.7:51821", "PublicKey = AWGPUB=",
                     "Jc = 4", "S1 = 33", "H4 = 404"):
            self.assertIn(line, conf)
        self.assertIsNone(await v.tunnel_config("wg", 1, "x"), "обычный WireGuard выключен")
        with open(os.path.join(awg, "awg-state.json")) as f:
            self.assertIn(v.awg.state["1"]["pub"], json.load(f)["peers"])
        await v.set_tunnel("wg", True)
        self.assertEqual(sorted(t.iface for t in v.tunnels_on()), ["awg0", "wg0"])
        await v.revoke(1)
        with open(os.path.join(awg, "awg-state.json")) as f:
            self.assertEqual(json.load(f)["peers"], {}, "отзыв убирает ключ из обоих")

    async def test_not_installed(self):
        self.v.tunnels.clear()
        ok, err = await self.v.set_wg(True)
        self.assertFalse(ok)
        self.assertIn("установщик", err)


if __name__ == "__main__":
    unittest.main()
