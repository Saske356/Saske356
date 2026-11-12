"""Модуль VPN (Xray) и разбор ключей в установщике: python3 -m unittest discover -s tests

Вместо настоящего Xray подставляется заглушка, которая, как и он, принимает только файлы .json.
"""

import asyncio, base64, json, os, re, stat, subprocess, sys, tempfile, time, unittest
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
    assert rules["out-nl"]["user"] == ["regexp:^u[0-9]+\\.nl$"]  # новые клиенты попадают сами
    assert rules["out-us"]["user"] == ["regexp:^u[0-9]+\\.us$"]
    assert "direct" not in rules  # основная страна идёт по умолчанию напрямую
    assert any(r.get("protocol") == ["bittorrent"] for r in cfg["routing"]["rules"])
    assert cfg["log"]["access"] == "none"

    # ссылки
    links = v.links(10)
    assert len(links) == 6  # 3 страны и запасной вариант XHTTP для каждой
    x = urlparse(links[3]); xq = parse_qs(x.query)
    assert xq["type"] == ["xhttp"] and xq["path"] == [v.xhttp_path] and "flow" not in xq
    assert x.port == 443 and unquote(x.fragment) == "🇸🇪 Швеция · запасной"
    names = [ib["tag"] for ib in cfg["inbounds"]]
    assert names == ["in", "in-x"] and inb["settings"]["fallbacks"] == [{"dest": xp.XHTTP_SOCKET}]
    xin = cfg["inbounds"][1]
    assert xin["listen"] == xp.XHTTP_SOCKET and "flow" not in xin["settings"]["clients"][0]
    assert cfg["api"]["listen"] == "127.0.0.1:10085"
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
    assert got == v.links(10) and len(got) == 4  # nl и основной (us удалили), у каждой запасной
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
    assert len(ls) == 6, ls  # основной и два моста, у каждого запасной
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
    assert await al.apply() is True, "только клиенты не менялись: перезапуск и проверка не нужны"
    al.state["locations"].append({"code": "nl", "name": "NL", "proxy": "socks5://1.2.3.4:1080"})
    assert await al.apply() is False and al.on_problem.await_count == 2
    al.on_problem = AsyncMock(side_effect=RuntimeError("telegram down"))
    al.last_error = ""
    assert await al.apply() is False, "сбой оповещения не роняет применение"
    al.xray_bin = "/nonexistent/xray"; al.on_problem = AsyncMock()
    assert await al.apply() is False and "не найден" in al.on_problem.await_args.args[0]


def api_xray(log_path, api_ok=True):
    """Заглушка Xray, которая понимает и проверку конфига, и вызовы API adu/rmu."""
    p = os.path.join(T, "xray_api" + ("" if api_ok else "_down"))
    with open(p, "w") as f:
        f.write(f"""#!/usr/bin/env python3
import json, sys
a = sys.argv[1:]
open({log_path!r}, "a").write(" ".join(a[:2]) + "\\n")
if a[0] == "run":
    json.load(open(a[3])); sys.exit(0)
if not {api_ok!r}:
    print("failed to dial 127.0.0.1:10085"); sys.exit(1)
assert a[2].startswith("--server=127.0.0.1:"), a
if a[1] == "adu":
    n = sum(len(ib["settings"]["clients"]) for ib in json.load(open(a[3]))["inbounds"])
    print(f"Added {{n}} user(s) in total.")
elif a[1] == "rmu":
    print(f"Removed {{len(a) - 4}} user(s) in total.")
""")
    os.chmod(p, 0o755)
    return p


class XrayProvider(unittest.IsolatedAsyncioTestCase):
    async def test_provider(self):
        await main()

    async def test_clients_change_without_restart(self):
        log_path = os.path.join(T, "api.log")
        open(log_path, "w").close()
        v = make(name="hot")
        v.xray_bin = api_xray(log_path)
        calls = lambda: open(log_path).read().split()
        now = time.time()
        await v.issue(1, now + 1000)
        assert await v.apply() and v.restarts == 1 and calls() == ["run", "-test"]
        open(log_path, "w").close()
        await v.issue(2, now + 1000)
        assert await v.apply() and v.restarts == 1 and v.hot_updates == 1
        assert calls() == ["api", "adu", "api", "adu"], calls()  # основной вход и запасной
        on_disk = read_json(v.config_path)
        assert {c["email"] for c in on_disk["inbounds"][0]["settings"]["clients"]} == {"u1.main", "u2.main"}
        open(log_path, "w").close()
        await v.issue(2, now + 5000)  # продление: в Xray ничего не меняется
        assert await v.apply() and calls() == [] and v.restarts == 1
        await v.revoke(1)
        assert await v.apply() and calls() == ["api", "rmu", "api", "rmu"] and v.restarts == 1
        v.add_location("nl", "NL", "socks5://1.2.3.4:1080")  # новая страна: нужен перезапуск
        assert await v.apply() and v.restarts == 2
        # Xray упал или API не отвечает: бот просто перезапускает его с новым конфигом
        v.xray_bin = api_xray(log_path, api_ok=False)
        await v.issue(3, now + 1000)
        assert await v.apply() and v.restarts == 3
        assert "u3.nl" in json.dumps(read_json(v.config_path))
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()

    async def test_hysteria(self):
        v = make(name="hy2")
        v.hy2 = {"port": 443, "obfs_port": 8443, "sni": "www.nvidia.com", "pin": "ab" * 32, "obfs": "o/p",
                 "stats_ports": [], "stats_secret": ""}
        v.hy2_auth_port = 0
        now = time.time()
        await v.issue(5, now + 1000)
        v.state["users"]["6"] = now - 1
        ls = v.links(5)
        assert ls[0].startswith("hysteria2://") and ls[1].startswith("hysteria2://"), "Hysteria идёт первой"
        u = urlparse(ls[0]); q = parse_qs(u.query)
        assert u.username == v.hy2_password(5) and u.password is None
        assert (u.hostname, u.port, q["sni"], q["insecure"]) == ("203.0.113.7", 443, ["www.nvidia.com"], ["1"])
        assert "obfs" not in q and q["pinSHA256"] == ["ab" * 32]
        q2 = parse_qs(urlparse(ls[1]).query)
        assert urlparse(ls[1]).port == 8443 and q2["obfs"] == ["salamander"] and q2["obfs-password"] == ["o/p"]
        assert v.hy2_check(v.hy2_password(5)) == 5
        assert v.hy2_check(v.hy2_password(6)) is None, "истёкший доступ"
        assert v.hy2_check("5.000") is None and v.hy2_check("") is None and v.hy2_check("x.y") is None
        # мост «ru» пересылает UDP: в подписке появляется Hysteria через мост с российским сайтом
        v.add_bridge("ru1", "🇷🇺 Обход", "198.51.100.40", ru=True)
        v.set_bridge_site("vk.com")
        hy = [l for l in v.links(5) if l.startswith("hysteria2://")]
        assert len(hy) == 3 and "198.51.100.40:443" in hy[2] and "sni=vk.com" in hy[2]

        # проверка пароля так, как её делает Hysteria
        assert await v.start_hy2_auth()
        port = v._hy2_server.sockets[0].getsockname()[1]

        async def ask(auth):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            body = json.dumps({"addr": "1.2.3.4:5", "auth": auth, "tx": 0}).encode()
            w.write(b"POST /hy2auth HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            await w.drain()
            data = await r.read(); w.close()
            assert data.startswith(b"HTTP/1.1 200")
            return json.loads(data.partition(b"\r\n\r\n")[2])
        assert await ask(v.hy2_password(5)) == {"ok": True, "id": "u5"}
        assert (await ask(v.hy2_password(6)))["ok"] is False
        assert (await ask("nonsense"))["ok"] is False
        assert v.hy2_logins == 1
        await v.revoke(5)
        assert (await ask(v.hy2_password(5)))["ok"] is False, "после отключения пароль не принимается"
        v._hy2_server.close()
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()

    async def test_https_subscription_and_hysteria_only(self):
        d = tempfile.mkdtemp()
        cert, key = os.path.join(d, "c.pem"), os.path.join(d, "k.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                        "-days", "2", "-subj", "/CN=sub.example.com", "-addext", "subjectAltName=DNS:sub.example.com"],
                       check=True, capture_output=True)
        v = make(name="https")
        v.xray_enabled = v.xhttp_enabled = False
        v.hy2 = {"port": 443, "sni": "www.nvidia.com", "pin": "", "obfs": "", "stats_ports": []}
        v.sub_domain, v.sub_tls_port, v.sub_cert, v.sub_key = "sub.example.com", 0, cert, key
        now = time.time()
        old = v.sub_url(9)
        await v.issue(9, now + 1000)
        assert await v.apply() and v.restarts == 0, "без Xray перезапускать нечего"
        assert [l.split("://")[0] for l in v.links(9)] == ["hysteria2"], "в подписке только Hysteria"
        await v.start_sub_server("127.0.0.1")
        assert v.sub_https
        port = v._tls_server.sockets[0].getsockname()[1]
        v.sub_tls_port = 443
        url = v.sub_url(9)
        assert re.fullmatch(r"https://sub\.example\.com/[0-9A-Za-z]{16}", url), url
        assert url != old and v.short_token(9) != v.short_token(10)
        import ssl
        ctx = ssl.create_default_context(cafile=cert)

        async def get(path, tls=True):
            r, w = await asyncio.open_connection(
                "127.0.0.1", port if tls else v._server.sockets[0].getsockname()[1],
                ssl=ctx if tls else None, server_hostname="sub.example.com" if tls else None)
            w.write(f"GET {path} HTTP/1.1\r\nHost: sub.example.com\r\n\r\n".encode()); await w.drain()
            data = await r.read(); w.close()
            return data.partition(b"\r\n\r\n")
        head, _, body = await get("/" + v.short_token(9))
        assert head.startswith(b"HTTP/1.1 200") and base64.b64decode(body).decode() == v.links(9)[0]
        head, _, _ = await get("/" + "A" * 16); assert head.startswith(b"HTTP/1.1 404")
        head, _, body = await get("/"); assert head.startswith(b"HTTP/1.1 200") and b"<h1>" in body
        head, _, _ = await get(f"/sub/9/{v.sub_token(9)}", tls=False)
        assert head.startswith(b"HTTP/1.1 200"), "старые ссылки продолжают работать"
        await v.revoke(9)
        head, _, _ = await get("/" + v.short_token(9)); assert head.startswith(b"HTTP/1.1 404")
        # сертификат не найден: бот раздаёт по HTTP и не обещает HTTPS в ссылках
        w = make(name="https2")
        w.sub_domain, w.sub_tls_port, w.sub_cert, w.sub_key = "sub.example.com", 0, "/nope.pem", "/nope.pem"
        assert not await w.start_https("127.0.0.1") and w.sub_url(1).startswith("http://203.0.113.7")
        for srv in (v._server, v._tls_server):
            srv.close()
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()

    async def test_bridge_for_whitelists_and_sub_url(self):
        v = make(name="rubridge")
        now = time.time()
        await v.issue(4, now + 1000)
        v.add_bridge("ru1", "🇷🇺 Обход", "198.51.100.20", ru=True)
        assert [ib["tag"] for ib in v.build_config()["inbounds"]] == ["in", "in-x"], "без сайта вход не нужен"
        assert len(v.links(4)) == 2, "мост без сайта маскировки не показывается"
        v.set_bridge_site("vk.com")
        cfg = v.build_config()
        b_in = next(ib for ib in cfg["inbounds"] if ib["tag"] == "in-b")
        rs = b_in["streamSettings"]["realitySettings"]
        assert b_in["port"] == 8444 and rs["serverNames"] == ["vk.com"] and rs["dest"] == "vk.com:443"
        assert [c["email"] for c in b_in["settings"]["clients"]] == ["u4.main"]
        assert "vk.com" not in cfg["inbounds"][0]["streamSettings"]["realitySettings"]["serverNames"]
        ls = v.links(4)
        assert len(ls) == 4
        u = urlparse(ls[1]); q = parse_qs(u.query)
        assert (u.hostname, u.port, q["sni"]) == ("198.51.100.20", 443, ["vk.com"])
        assert u.username == v.user_uuid(4, "main")
        v.sub_base = "https://sub.example.com/"
        v.sub_base = v.sub_base.rstrip("/")
        assert v.sub_url(4) == f"https://sub.example.com/sub/4/{v.sub_token(4)}"
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task():
                t.cancel()


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
