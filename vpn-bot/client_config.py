"""Готовые конфиги Xray для приложений v2rayNG и Happ.

Вместо голых ссылок такие приложения получают полный конфиг на каждый сервер. В нём:
- российские сайты и адреса идут напрямую, мимо VPN: Госуслуги, банки и налоговая не видят
  зарубежный IP, а пинг до них минимальный;
- DNS через HTTPS: оператор не видит, какие сайты открываются, и не подменяет ответы;
- реклама и трекеры отсекаются;
- локальные адреса (роутер, принтер) идут напрямую.

Hysteria2 описан встроенным в Xray протоколом hysteria, сертификат сервера сверяется
по отпечатку (pinnedPeerCertSha256).
"""

import re

JSON_AGENTS = re.compile(r"v2rayng|happ|aurora", re.I)
# Своё приложение Aurora VPN (сборка v2rayNG из android/): в нём ядро Xray всегда свежее.
AURORA_AGENT = re.compile(r"aurora", re.I)
# Настройки QUIC для Hysteria только для своего приложения. В Xray у клиента Hysteria сигналы
# «на связи» по умолчанию выключены: стоит минуту ничего не открывать, и соединение тихо
# умирает (а мобильный оператор ещё раньше забывает UDP-сопоставление), тогда следующая
# страница ждёт нового рукопожатия. keepAlive раз в 10 с держит соединение тёплым.
# Happ эти поля не отдаём: в нём ядро старее, и рисковать его подпиской незачем.
# Маскировку QUIC под Chrome (есть в Xray с v26.9.9, включена по умолчанию) не трогаем: именно она
# проходит мобильных операторов — поэтому v2rayNG со свежим ядром работает там, где Happ молчит.
AURORA_QUIC = {"keepAlivePeriod": 10, "maxIdleTimeout": 60}
# Турбо (Brutal) — во всех подключениях своего приложения. Обычный режим (BBR) при потерях пакетов
# сбавляет скорость, а на мобильном при глушилках потери большие: замер при белых списках — 1.6 Мбит/с.
# Brutal держит заявленную скорость и досылает потерянное (с потолком 100 Мбит/с было 92 на Wi-Fi).
# Сервер шлёт к гостю со скоростью brutalDown (её клиент сообщает серверу при подключении).
# Потолок 150 Мбит/с — по просьбе пользователя, у всех подключений одинаковый. Запасные пункты
# «· белые списки» (Brutal 10) и «· эконом» (BBR) убраны: по замерам они ничего не давали.
TURBO_QUIC = {"congestion": "brutal", "brutalUp": "20 mbps", "brutalDown": "150 mbps"}

# Российские домены: зона .ru, .su, .рф и крупные сервисы на других зонах.
RU_DOMAINS = [
    "regexp:\\.ru$", "regexp:\\.su$", "regexp:\\.xn--p1ai$", "regexp:\\.by$",
    "domain:yandex.net", "domain:yandex.com", "domain:yastatic.net", "domain:vk.com", "domain:vk.me",
    "domain:userapi.com", "domain:vkuser.net", "domain:mycdn.me", "domain:ok.me", "domain:max.ru",
    "domain:sberbank.com", "domain:tinkoff.com", "domain:tbank.com", "domain:avito.st",
    "domain:wildberries.kz", "domain:ozon.travel", "domain:gosuslugi.com",
]
# Telegram (адреса с core.telegram.org/resources/cidr.txt и его домены). Из стран через прокси он идёт
# через основной сервер: бесплатные прокси часто не пропускают его соединения, и Telegram висит
# на «Соединение…», хотя сайты открываются.
TG_IPS = ["91.108.56.0/22", "91.108.4.0/22", "91.108.8.0/22", "91.108.16.0/22", "91.108.12.0/22",
          "149.154.160.0/20", "91.105.192.0/23", "91.108.20.0/22", "185.76.151.0/24",
          "2001:b28:f23d::/48", "2001:b28:f23f::/48", "2001:67c:4e8::/48", "2001:b28:f23c::/48", "2a0a:f280::/32"]
TG_DOMAINS = ["domain:telegram.org", "domain:t.me", "domain:telegram.me", "domain:telegra.ph",
              "domain:telesco.pe", "domain:tdesktop.com", "domain:cdn-telegram.org", "domain:telegram-cdn.org"]
# DNS Яндекса для российских имён — обычный (UDP 53), напрямую (адрес в правилах «direct»).
# Был DoH по адресу https://77.88.8.8: сертификат Яндекса выдан на имя, а не на этот адрес,
# и российские имена могли не находиться — Яндекс не открывался, а Google через VPN работал.
RU_DNS = "77.88.8.8"
DNS = ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]


# Браузер: адрес подписки открыли по ссылке. Ему показываем страницу «Открыть в приложении»,
# а не ключи — так адрес сервера не светится, если ссылку переслали или открыли случайно.
# Приложения представляются своим именем; если в строке есть любое из них — это приложение.
APP_AGENTS = re.compile(r"happ|v2ray|aurora|hiddify|streisand|sing-?box|clash|neko|v2box|shadowrocket|"
                        r"karing|foxray|stash|surge|quantumult|loon|throne|okhttp|xray|mihomo|flclash", re.I)


def is_browser(agent: str) -> bool:
    agent = agent or ""
    return agent.startswith("Mozilla/") and not APP_AGENTS.search(agent)


# Шифрование подписки для своего приложения. Приложение с поддержкой пишет в User-Agent «(enc1)»,
# и тогда вместо JSON приходит «aurora1:» + base64(nonce 12 байт + AES-256-GCM). Ключ —
# SHA-256(SUB_SECRET + путь ссылки подписки), тот же код стоит в приложении (android/customize.py).
# Это маскировка, а не секрет: код открыт, и тот, у кого есть сама ссылка, её расшифрует. Зато
# в ответе нет ни адресов, ни паролей открытым текстом: ни прокси, ни сканер, ни случайный
# человек по ссылке не увидят сервер.
SUB_SECRET = "06c56043502cab251d01ad69c59ab1ea3885c20bd2590fca"
ENC_PREFIX = "aurora1:"


def wants_encrypted(agent: str) -> bool:
    return is_aurora(agent) and "(enc1)" in (agent or "")


def encrypt_sub(body: bytes, path: str) -> bytes:
    import base64
    import hashlib
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = hashlib.sha256((SUB_SECRET + path).encode()).digest()
    nonce = os.urandom(12)
    return ENC_PREFIX.encode() + base64.b64encode(nonce + AESGCM(key).encrypt(nonce, body, None))


def wants_json(agent: str) -> bool:
    return bool(JSON_AGENTS.search(agent or ""))


def is_aurora(agent: str) -> bool:
    return bool(AURORA_AGENT.search(agent or ""))


def outbound(e: dict, tuned: bool = False) -> dict:
    """Исходящее подключение к серверу VPN по записи из XrayProvider.entries().
    tuned — для своего приложения: с настройками QUIC под скорость (AURORA_QUIC)."""
    if e["kind"] == "hy2":
        stream = {
            "network": "hysteria",
            "hysteriaSettings": {"version": 2, "auth": e["auth"]},
            "security": "tls",
            "tlsSettings": {"serverName": e["sni"], "alpn": ["h3"]},
        }
        if e.get("pin"):
            stream["tlsSettings"]["pinnedPeerCertSha256"] = e["pin"]
        if e.get("obfs"):
            stream["finalmask"] = {"udp": [{"type": "salamander", "settings": {"password": e["obfs"]}}]}
        if tuned:
            q = dict(AURORA_QUIC)
            mode = e.get("mode", TURBO_QUIC)
            if mode:
                q.update(mode)
            stream.setdefault("finalmask", {})["quicParams"] = q
        return {"tag": "proxy", "protocol": "hysteria",
                "settings": {"version": 2, "address": e["host"], "port": e["port"]},
                "streamSettings": stream}
    user = {"id": e["uid"], "encryption": "none"}
    if e["kind"] == "reality":
        user["flow"] = "xtls-rprx-vision"
    stream = {
        "network": "tcp" if e["kind"] == "reality" else "xhttp",
        "security": "reality",
        "realitySettings": {"serverName": e["sni"], "fingerprint": "chrome", "publicKey": e["pbk"],
                            "shortId": e["sid"]},
    }
    if e["kind"] == "xhttp":
        stream["xhttpSettings"] = {"path": e["path"], "mode": "auto"}
    return {"tag": "proxy", "protocol": "vless",
            "settings": {"vnext": [{"address": e["host"], "port": e["port"], "users": [user]}]},
            "streamSettings": stream}


def _routing(server_ips: list[str], final: dict, tuned: bool = False, ads: bool = True,
             tg: dict | None = None) -> dict:
    """Правила: сам сервер, реклама, российские сайты и локальная сеть — мимо VPN, остальное — final.
    tuned (своё приложение): AsIs — без DNS-запроса на каждый новый сайт. Трафик из VPN приходит
    с адресами, по ним и так работают правила geoip, а имя сайта даёт sniffing. С IPIfNonMatch
    Xray для каждого имени не из списка сначала спрашивает DNS — при белых списках этот запрос
    упирается в блокировку и страница ждёт секунды."""
    server = [{"type": "field", "ip": server_ips, "outboundTag": "direct"}] if server_ips else []
    if tg:
        server += [{"type": "field", "ip": TG_IPS, **tg}, {"type": "field", "domain": TG_DOMAINS, **tg}]
    return {
        "domainStrategy": "AsIs" if tuned else "IPIfNonMatch",
        "rules": [
            *server,
            *([{"type": "field", "domain": ["geosite:category-ads-all"], "outboundTag": "block"}] if ads else []),
            {"type": "field", "ip": ["77.88.8.8"], "outboundTag": "direct"},
            {"type": "field", "domain": RU_DOMAINS, "outboundTag": "direct"},
            {"type": "field", "ip": ["geoip:private", "geoip:ru"], "outboundTag": "direct"},
            {"type": "field", "network": "tcp,udp", **final},
        ],
    }


def _ip(host: str) -> list[str]:
    # В правило по IP можно вписать только адрес, а не домен.
    return [host] if re.fullmatch(r"[0-9.]+|[0-9a-fA-F:]+", host) else []


def _base(name: str, outbounds: list[dict], routing: dict) -> dict:
    return {
        "remarks": name,
        "log": {"loglevel": "warning"},
        "dns": {
            "servers": [
                {"address": RU_DNS, "domains": RU_DOMAINS, "skipFallback": True},
                *[{"address": a} for a in DNS],
            ],
            "queryStrategy": "UseIPv4",
        },
        "inbounds": [
            {"tag": "socks", "listen": "127.0.0.1", "port": 10808, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True},
             "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True}},
            {"tag": "http", "listen": "127.0.0.1", "port": 10809, "protocol": "http"},
        ],
        "outbounds": outbounds + [{"tag": "direct", "protocol": "freedom"},
                                  {"tag": "block", "protocol": "blackhole"}],
        "routing": routing,
    }


def best(entries: list[dict], name: str = "🚀 Лучший сервер", tuned: bool = False) -> dict:
    """Один конфиг с подключениями к нашему серверу (напрямую, «обход БС», мосты): Xray в приложении
    раз в минуту замеряет каждое и ведёт трафик через самое быстрое из живых. Упавшее выпадает само.
    Страны через прокси сюда не входят: бесплатные прокси медленные и нестабильные, а выбор «по пингу»
    перескакивал на них — скорость и пинг скакали, Telegram не грузился."""
    entries = [e for e in entries if not e.get("tg")] or entries
    outs = []
    for i, e in enumerate(entries):
        o = outbound(e, tuned)
        o["tag"] = f"p{i}"
        outs.append(o)
    cfg = _base(name, outs, _routing(sorted({ip for e in entries for ip in _ip(e["host"])}),
                                     {"balancerTag": "best"}, tuned))
    cfg["routing"]["balancers"] = [{"tag": "best", "selector": ["p"], "strategy": {"type": "leastPing"},
                                    "fallbackTag": "p0"}]
    cfg["observatory"] = {"subjectSelector": ["p"], "probeURL": "https://www.google.com/generate_204",
                          "probeInterval": "1m", "enableConcurrency": True}
    return cfg


GAME_NAME = "🎮 Игры"


def config(e: dict, tuned: bool = False) -> dict:
    outs = [outbound(e, tuned)]
    tg = None
    if e.get("tg"):  # страна через прокси: Telegram — через основной сервер
        o = outbound({**e, **e["tg"]}, tuned)
        o["tag"] = "tg"
        outs.append(o)
        tg = {"outboundTag": "tg"}
    return _base(e["name"], outs,
                 _routing(_ip(e["host"]), {"outboundTag": "proxy"}, tuned, ads=not e.get("game"), tg=tg))


def game_entry(entries: list[dict]) -> dict | None:
    """Игровое подключение: только напрямую через основной сервер (первое подключение), без
    бесплатных прокси стран — они медленные и почти не пропускают UDP, а игры идут по UDP.
    Российские игровые серверы и так идут мимо VPN (geoip:ru), пинг на них как без VPN.
    Реклама не режется: блокировка иногда ломает вход в игры и награды за рекламу."""
    if not entries:
        return None
    return {**entries[0], "name": GAME_NAME, "game": True}


def configs(entries: list[dict], with_best: bool = True, tuned: bool = False, game: bool = True) -> list[dict]:
    """Конфиги подписки: первым «Лучший сервер» (если подключений больше одного), «🎮 Игры», затем страны."""
    out = [config(e, tuned) for e in entries]
    g = game_entry(entries) if game and len(entries) > 1 else None  # с одной страной смысла нет
    head = [best(entries, tuned=tuned)] if with_best and len(entries) > 1 else []
    return head + ([config(g, tuned)] if g else []) + out
