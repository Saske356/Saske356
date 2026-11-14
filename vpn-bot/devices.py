"""Лимит устройств: сколько устройств на самом деле подключено к подписке и что с этим делать.

Сервер видит адреса, с которых сейчас подключены ключи подписки (Xray), и число подключений
Hysteria2. Разные адреса почти всегда означают разные устройства. Обратное неверно: несколько
устройств за одним роутером или за мостом видны как одно, поэтому проверка только мягче, чем есть.

Чтобы не наказать человека за случайность (телефон переключился с Wi-Fi на мобильную сеть и
старый адрес ещё не пропал), решение принимается только после нескольких проверок подряд:
сначала гость получает предупреждение, а если превышение продолжается, подписка отключается
на время и затем включается сама.
"""

import time

WARN_MEMORY = 86400  # сколько помним предупреждение: повторное нарушение за сутки сразу ведёт к отключению


class DeviceGuard:
    def __init__(self, mode: str = "block", warn_after: int = 2, block_after: int = 3,
                 block_minutes: int = 30):
        self.mode = mode if mode in ("block", "warn", "off") else "block"
        self.warn_after, self.block_after = max(1, warn_after), max(1, block_after)
        self.block_seconds = max(60, block_minutes * 60)
        self.over: dict[int, int] = {}       # подписка -> проверок подряд с превышением
        self.warned: dict[int, float] = {}   # подписка -> когда предупредили
        self.blocked: dict[int, float] = {}  # подписка -> до какого времени отключена
        self.last: dict[int, int] = {}       # последний замер: подписка -> устройств
        self.last_at = 0.0

    def check(self, seen: dict[int, int], allowed: dict[int, int],
              now: float | None = None) -> list[tuple[str, int, int, int]]:
        """Один замер. seen: подписка -> устройств сейчас, allowed: подписка -> оплачено.
        Возвращает действия (warn или block, подписка, устройств, оплачено)."""
        now = time.time() if now is None else now
        self.last, self.last_at = dict(seen), now
        actions = []
        if self.mode == "off":
            return actions
        self.warned = {s: t for s, t in self.warned.items() if now - t < WARN_MEMORY}
        for sid, limit in allowed.items():
            if sid in self.blocked:
                continue
            n = seen.get(sid, 0)
            if n <= max(1, limit):
                self.over.pop(sid, None)
                continue
            self.over[sid] = self.over.get(sid, 0) + 1
            if sid not in self.warned:
                if self.over[sid] >= self.warn_after:
                    self.warned[sid] = now
                    self.over[sid] = 0
                    actions.append(("warn", sid, n, limit))
            elif self.mode == "block" and self.over[sid] >= self.block_after:
                self.over.pop(sid, None)
                self.blocked[sid] = now + self.block_seconds
                actions.append(("block", sid, n, limit))
        for sid in list(self.over):  # подписка закончилась или удалена
            if sid not in allowed:
                self.over.pop(sid)
        return actions

    def forget(self, sid: int) -> None:
        """После сброса устройств подписки: начать отсчёт заново."""
        for d in (self.over, self.warned, self.blocked, self.last):
            d.pop(sid, None)

    def due_unblock(self, now: float | None = None) -> list[int]:
        now = time.time() if now is None else now
        due = [s for s, t in self.blocked.items() if t <= now]
        for s in due:
            self.blocked.pop(s)
        return due
