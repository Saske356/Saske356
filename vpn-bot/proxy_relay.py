"""Локальный ретранслятор для авто-стран.

Xray для каждой авто-страны подключается сюда (SOCKS5 на 127.0.0.1, логин = код страны),
а ретранслятор сам выбирает живой публичный прокси и пересылает данные через него.
Поэтому замена упавшего прокси не требует перезапуска Xray и не рвёт чужие подключения:
если прокси не отвечает, это же подключение сразу уходит через запасной.

Подключение идёт наперегонки: если рабочий прокси не ответил за обычное для него время,
параллельно запускается запасной, и побеждает тот, кто ответил первым. Так зависший прокси
не стоит клиенту секунд ожидания. По реальным подключениям ретранслятор считает скорость
каждого прокси и делает рабочим тот запасной, который стабильно заметно быстрее.
"""

import asyncio
import hmac
import logging
import time

from public_proxies import ProxyDown, TunnelRefused, open_tunnel

log = logging.getLogger("vpn-bot.relay")


class Relay:
    FAIL_LIMIT = 2      # столько отказов подряд — и прокси уступает место запасному
    TRIES = 3           # сколько прокси пробуем на одно подключение
    HANDSHAKE_TIMEOUT = 10.0
    LINGER = 15.0       # сколько ждём вторую сторону после закрытия первой
    RACE_MIN, RACE_MAX, RACE_DEFAULT = 0.4, 2.5, 1.2  # через сколько секунд запускать запасной
    PROMOTE_SAMPLES = 3      # столько замеров нужно, чтобы сравнивать скорость
    PROMOTE_RATIO = 0.6      # запасной должен быть хотя бы на 40% быстрее рабочего
    PROMOTE_MIN_GAIN = 250   # и выигрывать не меньше этих миллисекунд

    def __init__(self, port: int, password: str, host: str = "127.0.0.1", on_demote=None,
                 connect_timeout: float = 6.0, on_promote=None):
        self.host, self.port, self.password = host, port, password
        self.on_demote, self.on_promote = on_demote, on_promote
        self.connect_timeout = connect_timeout
        self.routes: dict[str, list[str]] = {}
        self.fails: dict[str, int] = {}
        self.active: dict[str, int] = {}
        self.latency: dict[str, float] = {}   # прокси -> скользящее среднее времени подключения, мс
        self.samples: dict[str, int] = {}
        self.races = 0                         # сколько раз запасной запускался параллельно
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
        sock, refused = await self._connect(code, host, port)
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

    # ---------- подключение наперегонки ----------

    def _race_delay(self, url: str) -> float:
        """Сколько ждать рабочий прокси, прежде чем параллельно запустить запасной."""
        ms = self.latency.get(url)
        if ms is None:
            return self.RACE_DEFAULT
        return min(self.RACE_MAX, max(self.RACE_MIN, ms * 2.0 / 1000))

    async def _open(self, url: str, host: str, port: int):
        t0 = time.monotonic()
        sock = await open_tunnel(url, host, port, self.connect_timeout)
        return sock, (time.monotonic() - t0) * 1000

    def _record(self, url: str, ms: float) -> None:
        old = self.latency.get(url)
        self.latency[url] = ms if old is None else old * 0.7 + ms * 0.3
        self.samples[url] = self.samples.get(url, 0) + 1

    async def _connect(self, code: str, host: str, port: int):
        """Открывает туннель через прокси страны. Возвращает (сокет или None, был_ли_отказ_адреса)."""
        urls = list(self.routes.get(code, []))[:self.TRIES]
        pending: dict[asyncio.Task, tuple[str, float]] = {}
        refused, nxt, winner = False, 0, None

        def launch() -> None:
            nonlocal nxt
            url = urls[nxt]
            nxt += 1
            pending[asyncio.create_task(self._open(url, host, port))] = (url, time.monotonic())

        if not urls:
            return None, False
        launch()
        try:
            while pending and winner is None:
                delay = self._race_delay(urls[nxt - 1]) if nxt < len(urls) else None
                done, _ = await asyncio.wait(pending, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
                if not done:  # рабочий задумался: запускаем запасной, не бросая рабочий
                    self.races += 1
                    launch()
                    continue
                for t in done:
                    url, _ = pending.pop(t)
                    try:
                        sock, ms = t.result()
                    except TunnelRefused:
                        refused = True  # прокси жив, просто не дошёл до этого адреса
                        continue
                    except ProxyDown:
                        self._failed(code, url)
                        continue
                    except ValueError:
                        continue
                    self.fails.pop(url, None)
                    self._record(url, ms)
                    if winner is None:
                        winner = sock
                    else:
                        sock.close()
                if winner is None and not pending and nxt < len(urls):
                    launch()
        finally:
            for t in pending:
                t.cancel()
            if pending:
                now = time.monotonic()
                results = await asyncio.gather(*pending, return_exceptions=True)
                for (url, t0), res in zip(pending.values(), results):
                    if isinstance(res, tuple):  # успел подключиться, но опоздал
                        res[0].close()
                        self._record(url, res[1])
                    elif winner is not None and isinstance(res, asyncio.CancelledError):
                        # Проиграл гонку: его время не меньше, чем он успел проработать.
                        self._record(url, (now - t0) * 1000)
        if winner is not None:
            self._maybe_promote(code)
        return winner, refused

    def _maybe_promote(self, code: str) -> None:
        """Запасной стабильно быстрее рабочего — он становится рабочим."""
        route = self.routes.get(code) or []
        if len(route) < 2:
            return
        cur = route[0]
        cur_ms = self.latency.get(cur)
        if cur_ms is None or self.samples.get(cur, 0) < self.PROMOTE_SAMPLES:
            return
        best = min((u for u in route[1:] if self.samples.get(u, 0) >= self.PROMOTE_SAMPLES and u in self.latency),
                   key=lambda u: self.latency[u], default=None)
        if best is None:
            return
        best_ms = self.latency[best]
        if best_ms > cur_ms * self.PROMOTE_RATIO or cur_ms - best_ms < self.PROMOTE_MIN_GAIN:
            return
        route.remove(best)
        route.insert(0, best)
        log.info("авто-страна %s: прокси %s быстрее (%.0f мс против %.0f), он теперь рабочий",
                 code, best, best_ms, cur_ms)
        if self.on_promote:
            try:
                self.on_promote(code, list(route))
            except Exception:
                log.exception("on_promote")

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
