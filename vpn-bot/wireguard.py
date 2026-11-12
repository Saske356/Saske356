"""WireGuard: подключение по UDP через обычные приложения WireGuard.

Админ включает его кнопкой в /admin. У каждой подписки свой ключ и свой адрес во внутренней
сети. Ключи добавляются в работающий интерфейс командой wg set без перезапуска, раз в 5 минут
бот сверяет их с подписками. Трафик и время последнего подключения берутся из wg show dump.

Обычный WireGuard операторы узнают по первому пакету, поэтому он может не пройти там, где
Hysteria проходит. Тот же код подходит и для AmneziaWG: другая утилита (awg) и параметры
маскировки в params.
"""

import asyncio
import ipaddress
import logging
import time

log = logging.getLogger("vpn-bot.wg")

ONLINE_WINDOW = 180  # подключение считается активным, если рукопожатие было не раньше этого


class WireGuard:
    def __init__(self, *, host: str, port: int, server_public_key: str, state: dict, save, params: str = "",
                 iface: str = "wg0", net: str = "10.67.0.0/16", dns: str = "1.1.1.1, 8.8.8.8",
                 wg_bin: str = "wg"):
        self.host, self.port, self.server_pub = host, port, server_public_key
        self.params = [p.strip() for p in params.split(",") if "=" in p]
        self.iface, self.net, self.dns, self.bin = iface, ipaddress.ip_network(net), dns, wg_bin
        self.state = state            # подписка -> {"priv", "pub", "ip"}; хранится в vpn.json
        self.save = save
        self._last: dict[str, tuple[int, int]] = {}  # ключ -> (получено, отдано) при прошлом замере
        self.lock = asyncio.Lock()

    async def _run(self, *args, data: bytes | None = None) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.bin, *args, stdin=asyncio.subprocess.PIPE if data is not None else None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(data), 15)
            return proc.returncode, out.decode(errors="replace").strip()
        except (OSError, asyncio.TimeoutError) as e:
            return 1, str(e)

    def _free_ip(self) -> str | None:
        used = {v["ip"] for v in self.state.values()}
        server = str(next(self.net.hosts()))  # первый адрес у самого сервера
        for ip in self.net.hosts():
            ip = str(ip)
            if ip != server and ip not in used:
                return ip
        return None

    async def keys(self, sid: int) -> dict | None:
        """Ключ подписки: создаётся один раз и хранится, чтобы файл настроек у гостя не устаревал."""
        key = str(sid)
        if key in self.state:
            return self.state[key]
        code, priv = await self._run("genkey")
        if code != 0 or not priv:
            log.warning("WireGuard: ключ не создан: %s", priv)
            return None
        code, pub = await self._run("pubkey", data=priv.encode() + b"\n")
        ip = self._free_ip()
        if code != 0 or not pub or not ip:
            log.warning("WireGuard: ключ не создан: %s", pub)
            return None
        self.state[key] = {"priv": priv, "pub": pub, "ip": ip}
        self.save()
        return self.state[key]

    async def add(self, sid: int) -> bool:
        k = await self.keys(sid)
        if not k:
            return False
        code, out = await self._run("set", self.iface, "peer", k["pub"], "allowed-ips", f"{k['ip']}/32")
        if code != 0:
            log.warning("WireGuard: ключ %s не добавлен: %s", sid, out)
        return code == 0

    async def remove(self, sid: int) -> None:
        k = self.state.get(str(sid))
        if k:
            await self._run("set", self.iface, "peer", k["pub"], "remove")

    async def sync(self, active: list[int]) -> None:
        """На интерфейсе ровно ключи активных подписок. Безопасно повторять: после перезапуска
        интерфейса ключи возвращаются сами."""
        async with self.lock:
            code, out = await self._run("show", self.iface, "peers")
            if code != 0:
                return
            present = set(out.split())
            want = {}
            for sid in active:
                k = await self.keys(sid)
                if k:
                    want[k["pub"]] = sid
            for pub in present - set(want):
                await self._run("set", self.iface, "peer", pub, "remove")
            for pub, sid in want.items():
                if pub not in present:
                    await self.add(sid)

    async def _dump(self) -> list[list[str]] | None:
        code, out = await self._run("show", self.iface, "dump")
        if code != 0:
            return None
        return [line.split("\t") for line in out.splitlines()[1:] if line.count("\t") >= 7]

    def _sid_by_pub(self) -> dict[str, int]:
        return {v["pub"]: int(k) for k, v in self.state.items()}

    async def traffic(self) -> dict[int, tuple[int, int]]:
        """Трафик с прошлого замера: {подписка: (отдано, получено)} с точки зрения гостя."""
        rows = await self._dump()
        if rows is None:
            return {}
        by_pub, out = self._sid_by_pub(), {}
        for r in rows:
            pub, rx, tx = r[0], int(r[5] or 0), int(r[6] or 0)
            prev_rx, prev_tx = self._last.get(pub, (0, 0))
            if rx < prev_rx or tx < prev_tx:  # интерфейс перезапускался, счётчики с нуля
                prev_rx = prev_tx = 0
            self._last[pub] = (rx, tx)
            sid = by_pub.get(pub)
            if sid is not None and (rx - prev_rx or tx - prev_tx):
                out[sid] = (rx - prev_rx, tx - prev_tx)  # получено сервером = отдано гостем
        return out

    async def online(self) -> dict[int, int] | None:
        rows = await self._dump()
        if rows is None:
            return None
        by_pub, now = self._sid_by_pub(), time.time()
        return {by_pub[r[0]]: 1 for r in rows
                if r[0] in by_pub and r[4].isdigit() and now - int(r[4]) < ONLINE_WINDOW}

    def client_config(self, sid: int, name: str = "VPN") -> str | None:
        k = self.state.get(str(sid))
        if not k:
            return None
        lines = ["[Interface]", f"# {name}", f"PrivateKey = {k['priv']}", f"Address = {k['ip']}/32",
                 f"DNS = {self.dns}"]
        lines += [p.replace("=", " = ", 1) for p in self.params]
        lines += ["", "[Peer]", f"PublicKey = {self.server_pub}", f"Endpoint = {self.host}:{self.port}",
                  "AllowedIPs = 0.0.0.0/0", "PersistentKeepalive = 25", ""]
        return "\n".join(lines)
