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

    async def test_not_installed(self):
        self.v.wg = None
        ok, err = await self.v.set_wg(True)
        self.assertFalse(ok)
        self.assertIn("установщик", err)


if __name__ == "__main__":
    unittest.main()
