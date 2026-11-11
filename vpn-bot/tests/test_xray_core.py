"""Модуль VPN (Xray) и разбор ключей в установщике: python3 -m unittest discover -s tests

Вместо настоящего Xray подставляется заглушка, которая, как и он, принимает только файлы .json.
"""

import asyncio, base64, json, os, stat, subprocess, sys, tempfile, time, unittest
from urllib.parse import urlparse, parse_qs, unquote
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xray_provider as xp

T = tempfile.mkdtemp()


def fake_xray(ok=True):
    p = os.path.join(T, "xray_ok" if ok else "xray_bad")
    with open(p, "w") as f:
        f.write("#!/bin/sh\n" + ('case "$4" in *.json) ;; *) echo "Failed to get format of $4"; exit 1;; esac\n'
                                  "python3 -c \"import json,sys; json.load(open(sys.argv[1]))\" \"$4\"\n" if ok else "echo 'invalid config'; exit 1\n"))
    os.chmod(p, 0o755)
    return p


def make(ok=True, name="p"):
    return xp.XrayProvider(
        state_path=os.path.join(T, name, "state.json"), config_path=os.path.join(T, name, "config.json"),
        xray_bin=fake_xray(ok), public_host="203.0.113.7", port=443, sni="www.microsoft.com",
        private_key="PRIV", public_key="PUBKEY", short_id="a1b2c3d4e5f60718", sub_port=0,
        brand="Aurora VPN", default_location="🇸🇪 Швеция", restart_cmd=("true",))


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def main():
    # прокси
    o = xp.parse_proxy("socks5://us%40er:p%3Ass@1.2.3.4:1080")
    assert o["protocol"] == "socks" and o["settings"]["servers"][0]["users"][0] == {"user": "us@er", "pass": "p:ss"}
    assert xp.parse_proxy("http://5.6.7.8:3128")["protocol"] == "http"
    for bad in ["ftp://x:1", "socks5://nohost", "1.2.3.4:1080"]:
        try: xp.parse_proxy(bad); raise AssertionError(bad)
        except ValueError: pass

    v = make()
    now = time.time()
    url = await v.issue(10, now + 86400)
    assert url == f"http://203.0.113.7:0/sub/10/{v.sub_token(10)}"
    await v.issue(11, now + 86400)
    v.state["users"]["12"] = now - 5  # истёк
    v.add_location("nl", "🇳🇱 Нидерланды", "socks5://u:p@1.2.3.4:1080")
    v.add_location("us", "🇺🇸 США", "http://u:p@5.6.7.8:3128")
    for bad in [("NL-1!", "x", "socks5://u:p@1.1.1.1:1"), ("de", "x", "nonsense")]:
        try: v.add_location(*bad); raise AssertionError(bad)
        except ValueError: pass

    cfg = v.build_config()
    inb = cfg["inbounds"][0]
    assert inb["port"] == 443 and inb["streamSettings"]["security"] == "reality"
    assert inb["streamSettings"]["realitySettings"]["serverNames"] == ["www.microsoft.com"]
    clients = inb["settings"]["clients"]
    assert len(clients) == 2 * 3, len(clients)  # 2 активных × 3 страны, истёкший не попал
    assert len({c["id"] for c in clients}) == 6 and all(c["flow"] == "xtls-rprx-vision" for c in clients)
    tags = [ob["tag"] for ob in cfg["outbounds"]]
    assert tags[0] == "direct" and "out-nl" in tags and "out-us" in tags
    rules = {r.get("outboundTag"): r for r in cfg["routing"]["rules"] if "user" in r}
    assert sorted(rules["out-nl"]["user"]) == ["regexp:^u[0-9]+\\.nl$", "u10.nl", "u11.nl"]
    assert sorted(rules["out-us"]["user"]) == ["regexp:^u[0-9]+\\.us$", "u10.us", "u11.us"]
    # API для ключей без перезапуска: только на 127.0.0.1 и первым правилом
    api_in = next(i for i in cfg["inbounds"] if i["tag"] == "api")
    assert api_in["listen"] == "127.0.0.1" and cfg["routing"]["rules"][0]["inboundTag"] == ["api"]
    assert cfg["policy"]["levels"]["0"]["statsUserOnline"] and "StatsService" in cfg["api"]["services"]
    assert "direct" not in rules  # основная страна идёт по умолчанию напрямую
    assert any(r.get("protocol") == ["bittorrent"] for r in cfg["routing"]["rules"])
    assert cfg["log"]["access"] == "none"

    # ссылки
    links = v.links(10)
    assert len(links) == 3
    u = urlparse(links[1]); q = parse_qs(u.query)
    assert u.scheme == "vless" and u.hostname == "203.0.113.7" and u.port == 443
    assert q["security"] == ["reality"] and q["pbk"] == ["PUBKEY"] and q["sid"] == ["a1b2c3d4e5f60718"]
    assert q["flow"] == ["xtls-rprx-vision"] and unquote(u.fragment) == "🇳🇱 Нидерланды"
    assert u.username == v.user_uuid(10, "nl")
    ids_in_cfg = {c["id"] for c in clients}
    assert all(urlparse(l).username in ids_in_cfg for l in links)

    # применение конфига
    assert await v.apply() is True
    on_disk = read_json(v.config_path)
    assert len(on_disk["inbounds"][0]["settings"]["clients"]) == 6
    bad = make(ok=False, name="bad")
    await bad.issue(1, now + 100)
    with open(bad.config_path, "w") as f: f.write('{"old": true}')
    assert await bad.apply() is False
    assert read_json(bad.config_path) == {"old": True}, "битый конфиг не должен заменить рабочий"

    # отзыв и синхронизация
    await v.revoke(11)
    assert "11" not in v.state["users"]
    await v.sync({10: now + 100, 20: now + 200})
    assert set(v.state["users"]) == {"10", "20"}
    st = read_json(v.state_path); assert st["secret"] == v.state["secret"]
    v2 = make(name="p")  # перезапуск бота: секрет и страны сохраняются, ключи те же
    assert v2.user_uuid(10, "nl") == v.user_uuid(10, "nl") and len(v2.locations) == 3
    assert v.remove_location("us") and not v.remove_location("zz")
    one = make(name="single"); assert not one.remove_location("main")

    # сервер подписок
    await v.start_sub_server("127.0.0.1")
    port = v._server.sockets[0].getsockname()[1]

    async def get(path):
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\nUser-Agent: Hiddify\r\n\r\n".encode()); await w.drain()
        data = await r.read(); w.close()
        head, _, body = data.partition(b"\r\n\r\n")
        return head.decode(), body

    head, body = await get(f"/sub/10/{v.sub_token(10)}")
    assert head.startswith("HTTP/1.1 200"), head
    got = base64.b64decode(body).decode().splitlines()
    assert got == v.links(10) and len(got) == 2  # nl и основной (us удалили)
    assert f"expire={int(now + 100)}" in head and "profile-title: base64:" in head
    head, _ = await get(f"/sub/10/{'0' * 24}"); assert head.startswith("HTTP/1.1 404")
    head, _ = await get("/etc/passwd"); assert head.startswith("HTTP/1.1 404")
    v.state["users"]["10"] = now - 1
    head, _ = await get(f"/sub/10/{v.sub_token(10)}"); assert head.startswith("HTTP/1.1 403")

    # отложенное применение склеивает несколько изменений
    v.apply = AsyncMock(return_value=True)
    for i in range(5):
        await v.issue(100 + i, now + 100)
    await asyncio.sleep(2.3)
    assert v.apply.await_count == 1, v.apply.await_count
    # мосты для обхода
    b = make(name="bridges")
    await b.issue(7, now + 1000)
    b.add_bridge("ru1", "🇷🇺 Обход", "198.51.100.9")
    b.add_bridge("ru2", "🇷🇺 Обход 2", "198.51.100.10:8443", "vk.com")
    for bad in [("RU 1", "x", "1.1.1.1"), ("ru3", "x", "1.1.1.1:abc"), ("ru4", "x", "1.1.1.1", "не домен")]:
        try: b.add_bridge(*bad); raise AssertionError(bad)
        except ValueError: pass
    ls = b.links(7)
    assert len(ls) == 3, ls
    u1, u2 = urlparse(ls[1]), urlparse(ls[2])
    assert u1.hostname == "198.51.100.9" and u1.port == 443 and parse_qs(u1.query)["sni"] == ["www.microsoft.com"]
    assert u2.port == 8443 and parse_qs(u2.query)["sni"] == ["vk.com"]
    assert u1.username == b.user_uuid(7, "main"), "мост выходит через страну сервера"
    assert b.build_config()["inbounds"][0]["streamSettings"]["realitySettings"]["serverNames"] == \
        ["www.microsoft.com", "vk.com"]
    assert b.remove_bridge("ru2") and not b.remove_bridge("zz")
    assert b.server_names() == ["www.microsoft.com"]

    # тревога при сбое: один раз на одну и ту же ошибку, сброс после успеха
    al = make(ok=False, name="alert")
    al.on_problem = AsyncMock()
    await al.issue(9, now + 1000)
    assert await al.apply() is False and await al.apply() is False
    assert al.on_problem.await_count == 1 and "отклонил" in al.on_problem.await_args.args[0]
    assert "отклонил" in al.last_error and al.last_apply == 0
    al.xray_bin = fake_xray(True)
    assert await al.apply() is True and al.last_error == "" and al.last_apply > 0
    al.xray_bin = fake_xray(False)
    assert await al.apply() is False and al.on_problem.await_count == 2
    al.on_problem = AsyncMock(side_effect=RuntimeError("telegram down"))
    al.last_error = ""
    assert await al.apply() is False, "сбой оповещения не роняет применение"
    al.xray_bin = "/nonexistent/xray"; al.on_problem = AsyncMock()
    assert await al.apply() is False and "не найден" in al.on_problem.await_args.args[0]


class XrayProvider(unittest.IsolatedAsyncioTestCase):
    async def test_provider(self):
        await main()


class InstallerKeys(unittest.TestCase):
    def test_x25519_output_formats(self):
        """Старый и новый формат вывода `xray x25519`."""
        awk_priv = "awk -F': *' 'tolower($1) ~ /private/ {print $2; exit}'"
        awk_pub = "awk -F': *' 'tolower($1) ~ /public|password/ {print $2; exit}'"
        for out, pk, pb in [("Private key: AAA\nPublic key: BBB\n", "AAA", "BBB"),
                            ("PrivateKey: CCC\nPassword: DDD\nHash32: EEE\n", "CCC", "DDD")]:
            a = subprocess.run(["bash", "-c", f"printf '%s\\n' \"$K\" | {awk_priv}"], env={"K": out}, capture_output=True, text=True).stdout.strip()
            b = subprocess.run(["bash", "-c", f"printf '%s\\n' \"$K\" | {awk_pub}"], env={"K": out}, capture_output=True, text=True).stdout.strip()
            assert (a, b) == (pk, pb), (a, b)


if __name__ == "__main__":
    unittest.main()
