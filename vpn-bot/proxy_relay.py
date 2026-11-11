"""Локальный ретранслятор для авто-стран.

Xray для каждой авто-страны подключается сюда (SOCKS5 на 127.0.0.1, логин = код страны),
а ретранслятор сам выбирает живой публичный прокси и пересылает данные через него.
Поэтому замена упавшего прокси не требует перезапуска Xray и не рвёт чужие подключения:
если прокси не отвечает, это же подключение сразу уходит через запасной.
"""

import asyncio
import hmac
import logging

from public_proxies import ProxyDown, TunnelRefused, open_tunnel

log = logging.getLogger("vpn-bot.relay")


class Relay:
    FAIL_LIMIT = 2      # столько отказов подряд — и прокси уступает место запасному
    TRIES = 3           # сколько прокси пробуем на одно подключение
    HANDSHAKE_TIMEOUT = 10.0
    LINGER = 15.0       # сколько ждём вторую сторону после закрытия первой

    def __init__(self, port: int, password: str, host: str = "127.0.0.1", on_demote=None,
                 connect_timeout: float = 6.0):
        self.host, self.port, self.password = host, port, password
        self.on_demote = on_demote
        self.connect_timeout = connect_timeout
        self.routes: dict[str, list[str]] = {}
        self.fails: dict[str, int] = {}
        self.active: dict[str, int] = {}
        self._server: asyncio.base_events.Server | None = None
        self._conns: set[asyncio.Task] = set()

    @property
    def running(self) -> bool:
        return self._server is not None

    async def start(self) -> bool:
        try:
            self._server = await asyncio.start_server(self._accept, self.host, self.port)
        except OSError as e:
            log.error("Ретранслятор авто-стран не запустился на порту %d: %s", self.port, e)
            return False
        if not self.port:
            self.port = self._server.sockets[0].getsockname()[1]
        log.info("Ретранслятор авто-стран слушает %s:%d", self.host, self.port)
        return True

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for t in list(self._conns):
            t.cancel()
        await asyncio.gather(*self._conns, return_exceptions=True)

    def set_route(self, code: str, urls: list[str]) -> None:
        self.routes[code] = list(urls)

    def drop_route(self, code: str) -> None:
        self.routes.pop(code, None)

    # ---------- подключение от Xray ----------

    async def _accept(self, reader, writer) -> None:
        task = asyncio.current_task()
        self._conns.add(task)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass
        except Exception:
            log.exception("ошибка ретранслятора")
        finally:
            self._conns.discard(task)
            writer.close()

    async def _handshake(self, reader, writer) -> tuple[str, str, int] | None:
        ver, nmethods = await reader.readexactly(2)
        methods = await reader.readexactly(nmethods)
        if ver != 5 or 2 not in methods:
            writer.write(b"\x05\xff")
            return None
        writer.write(b"\x05\x02")
        if (await reader.readexactly(1))[0] != 1:
            return None
        user = (await reader.readexactly((await reader.readexactly(1))[0])).decode(errors="replace")
        pwd = (await reader.readexactly((await reader.readexactly(1))[0])).decode(errors="replace")
        if not hmac.compare_digest(pwd.encode(), self.password.encode()) or user not in self.routes:
            writer.write(b"\x01\x01")
            return None
        writer.write(b"\x01\x00")
        ver, cmd, _, atyp = await reader.readexactly(4)
        if atyp == 1:
            host = ".".join(str(b) for b in await reader.readexactly(4))
        elif atyp == 4:
            raw = await reader.readexactly(16)
            host = ":".join(raw[i:i + 2].hex() for i in range(0, 16, 2))
        elif atyp == 3:
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode(errors="replace")
        else:
            return None
        port = int.from_bytes(await reader.readexactly(2), "big")
        if cmd != 1:  # только TCP: публичные прокси UDP не пересылают
            writer.write(b"\x05\x07\x00\x01" + bytes(6))
            return None
        return user, host, port

    async def _serve(self, reader, writer) -> None:
        req = await asyncio.wait_for(self._handshake(reader, writer), self.HANDSHAKE_TIMEOUT)
        if not req:
            await writer.drain()
            return
        code, host, port = req
        sock, refused = None, False
        for url in list(self.routes.get(code, []))[:self.TRIES]:
            try:
                sock = await open_tunnel(url, host, port, self.connect_timeout)
                self.fails.pop(url, None)
                break
            except TunnelRefused:
                refused = True  # прокси жив, просто не дошёл до этого адреса
            except ProxyDown:
                self._failed(code, url)
            except ValueError:
                continue
        if sock is None:
            writer.write((b"\x05\x05" if refused else b"\x05\x01") + b"\x00\x01" + bytes(6))
            await writer.drain()
            return
        try:
            up_reader, up_writer = await asyncio.open_connection(sock=sock)
        except BaseException:
            sock.close()
            raise
        writer.write(b"\x05\x00\x00\x01" + bytes(6))
        self.active[code] = self.active.get(code, 0) + 1
        try:
            await self._pipe_both(reader, writer, up_reader, up_writer)
        finally:
            self.active[code] -= 1
            up_writer.close()

    def _failed(self, code: str, url: str) -> None:
        self.fails[url] = self.fails.get(url, 0) + 1
        if self.fails[url] < self.FAIL_LIMIT:
            return
        self.fails.pop(url, None)
        route = self.routes.get(code, [])
        if url in route and len(route) > 1:
            route.remove(url)
            route.append(url)
        log.warning("авто-страна %s: прокси %s не отвечает, переключаюсь на запасной", code, url)
        if self.on_demote:
            try:
                self.on_demote(code, url)
            except Exception:
                log.exception("on_demote")

    @staticmethod
    async def _pipe(reader, writer) -> None:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()

    async def _pipe_both(self, c_reader, c_writer, u_reader, u_writer) -> None:
        tasks = [asyncio.create_task(self._pipe(c_reader, u_writer)),
                 asyncio.create_task(self._pipe(u_reader, c_writer))]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if pending and not any(t.exception() for t in done):
                await asyncio.wait(pending, timeout=self.LINGER)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
