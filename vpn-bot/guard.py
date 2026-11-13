"""Защита раздачи подписок от флуда и перебора ссылок.

- С одного адреса — не больше PER_MIN запросов в минуту и PER_IP одновременных соединений.
- Всего — не больше TOTAL одновременных соединений: флуд не съедает память и не роняет бота.
- Неверные запросы (несуществующая ссылка, сканеры) считаются: FAIL_LIMIT за FAIL_WINDOW секунд —
  адрес молча отбрасывается на BAN секунд. Гости с рабочей ссылкой неверных запросов не делают,
  поэтому их это не задевает, а подобрать чужую ссылку перебором не выйдет.
Адреса самого сервера (127.0.0.1) не ограничиваются. Мобильные операторы выпускают многих
абонентов через один адрес, поэтому лимиты взяты с большим запасом.

Объёмный DDoS (гигабиты мусора в канал) так не остановить: это делает защита хостинга.
"""

import time

PER_MIN = 60
PER_IP = 8
TOTAL = 300
FAIL_LIMIT = 30
FAIL_WINDOW = 600
BAN = 3600
MAX_TRACKED = 20000


class RateGuard:
    def __init__(self, exempt=("127.0.0.1", "::1", "::ffff:127.0.0.1"), clock=time.monotonic):
        self.exempt = set(exempt)
        self.clock = clock
        self.hits: dict[str, list[float]] = {}
        self.fails: dict[str, list[float]] = {}
        self.banned: dict[str, float] = {}
        self.active: dict[str, int] = {}
        self.total = 0
        self.dropped = 0  # сколько соединений отброшено (для /server)

    def enter(self, ip: str) -> bool:
        """Можно ли обслужить соединение с этого адреса. True — нужно потом вызвать leave()."""
        now = self.clock()
        if ip in self.exempt:
            self.total += 1
            return True
        if self.banned.get(ip, 0) > now or self.total >= TOTAL or self.active.get(ip, 0) >= PER_IP:
            self.dropped += 1
            return False
        recent = [t for t in self.hits.get(ip, ()) if now - t < 60]
        if len(recent) >= PER_MIN:
            self.hits[ip] = recent
            self.dropped += 1
            return False
        recent.append(now)
        self.hits[ip] = recent
        self.active[ip] = self.active.get(ip, 0) + 1
        self.total += 1
        if len(self.hits) > MAX_TRACKED:
            self._prune(now)
        return True

    def leave(self, ip: str) -> None:
        self.total = max(0, self.total - 1)
        if ip in self.exempt:
            return
        n = self.active.get(ip, 0) - 1
        if n > 0:
            self.active[ip] = n
        else:
            self.active.pop(ip, None)

    def fail(self, ip: str) -> None:
        """Неверный запрос: несуществующая ссылка или непонятный путь."""
        if ip in self.exempt:
            return
        now = self.clock()
        recent = [t for t in self.fails.get(ip, ()) if now - t < FAIL_WINDOW] + [now]
        self.fails[ip] = recent
        if len(recent) >= FAIL_LIMIT:
            self.banned[ip] = now + BAN
            self.fails.pop(ip, None)

    def bans(self) -> int:
        now = self.clock()
        return sum(1 for t in self.banned.values() if t > now)

    def _prune(self, now: float) -> None:
        self.hits = {ip: ts for ip, ts in self.hits.items() if ts and now - ts[-1] < 60}
        self.fails = {ip: ts for ip, ts in self.fails.items() if ts and now - ts[-1] < FAIL_WINDOW}
        self.banned = {ip: t for ip, t in self.banned.items() if t > now}
