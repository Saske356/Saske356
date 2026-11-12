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

JSON_AGENTS = re.compile(r"v2rayng|happ", re.I)

# Российские домены: зона .ru, .su, .рф и крупные сервисы на других зонах.
RU_DOMAINS = [
    "regexp:\\.ru$", "regexp:\\.su$", "regexp:\\.xn--p1ai$", "regexp:\\.by$",
    "domain:yandex.net", "domain:yandex.com", "domain:yastatic.net", "domain:vk.com", "domain:vk.me",
    "domain:userapi.com", "domain:vkuser.net", "domain:mycdn.me", "domain:ok.me", "domain:max.ru",
    "domain:sberbank.com", "domain:tinkoff.com", "domain:tbank.com", "domain:avito.st",
    "domain:wildberries.kz", "domain:ozon.travel", "domain:gosuslugi.com",
]
RU_DNS = "https://77.88.8.8/dns-query"
DNS = ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]


def wants_json(agent: str) -> bool:
    return bool(JSON_AGENTS.search(agent or ""))


def outbound(e: dict) -> dict:
    """Исходящее подключение к серверу VPN по записи из XrayProvider.entries()."""
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


def _routing(server_ips: list[str], final: dict) -> dict:
    """Правила: сам сервер, реклама, российские сайты и локальная сеть — мимо VPN, остальное — final."""
    server = [{"type": "field", "ip": server_ips, "outboundTag": "direct"}] if server_ips else []
    return {
        "domainStrategy": "IPIfNonMatch",
        "rules": [
            *server,
            {"type": "field", "domain": ["geosite:category-ads-all"], "outboundTag": "block"},
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


def best(entries: list[dict], name: str = "🚀 Лучший сервер") -> dict:
    """Один конфиг со всеми подключениями: Xray в приложении раз в минуту замеряет каждое
    и ведёт трафик через самое быстрое из живых. Упавшее подключение выпадает само."""
    outs = []
    for i, e in enumerate(entries):
        o = outbound(e)
        o["tag"] = f"p{i}"
        outs.append(o)
    cfg = _base(name, outs, _routing(sorted({ip for e in entries for ip in _ip(e["host"])}),
                                     {"balancerTag": "best"}))
    cfg["routing"]["balancers"] = [{"tag": "best", "selector": ["p"], "strategy": {"type": "leastPing"},
                                    "fallbackTag": "p0"}]
    cfg["observatory"] = {"subjectSelector": ["p"], "probeURL": "https://www.google.com/generate_204",
                          "probeInterval": "1m", "enableConcurrency": True}
    return cfg


def config(e: dict) -> dict:
    return _base(e["name"], [outbound(e)], _routing(_ip(e["host"]), {"outboundTag": "proxy"}))


def configs(entries: list[dict], with_best: bool = True) -> list[dict]:
    """Конфиги подписки: первым «Лучший сервер» (если подключений больше одного), затем страны."""
    out = [config(e) for e in entries]
    return ([best(entries)] if with_best and len(entries) > 1 else []) + out
