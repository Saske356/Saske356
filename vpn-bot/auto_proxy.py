"""Авто-страны: бот сам находит публичные прокси, добавляет из них страны и меняет при отвале.

У каждой авто-страны есть рабочий прокси и до двух запасных. Ретранслятор (proxy_relay.py)
переключается на запасной сразу, как только рабочий перестал отвечать, а этот модуль
раз в несколько минут перепроверяет все прокси, убирает мёртвые и добирает новые.

У каждого прокси копится репутация: прошёл проверку — плюс, не прошёл или умер в работе —
минус. Кандидаты с плохой историей пробуются последними, так что со временем страны держатся
на самых стабильных прокси. Если запасной заметно быстрее рабочего, он становится рабочим.
"""

import asyncio
import logging
import time

import public_proxies as pp
from proxy_relay import Relay

log = logging.getLogger("vpn-bot.auto")

POOL_SIZE = 3            # рабочий прокси + запасные на каждую страну
BAD_DEAD = 6 * 3600      # сколько не возвращаемся к прокси, который умер в работе
BAD_CANDIDATE = 1800     # сколько не перепроверяем кандидата, не прошедшего проверку
EXTRA_ATTEMPTS = 5       # сколько лишних стран пробуем за цикл в режиме подбора
PROBE_BUDGET = 60        # сколько новых прокси можно проверить за один цикл
PER_COUNTRY = 12         # и сколько из них на одну страну
HIDE_LIMIT = 6 * 3600    # при подборе страна без прокси столько ждёт, потом уступает место другой
SLOW_MS = 1500           # рабочий прокси медленнее этого и вдвое медленнее запасного уступает ему
REP_LIMIT = 5000         # сколько прокси помнить в репутации

# В режиме подбора страны берутся в этом порядке, затем остальные по числу прокси.
PREFERRED = ["nl", "de", "us", "gb", "fr", "fi", "se", "ch", "jp", "sg", "ca", "tr",
             "it", "es", "at", "no", "dk", "cz", "kz", "ae", "hk", "kr", "au", "br"]


class AutoProxy:
    def __init__(self, vpn, notify=None):
        self.vpn = vpn
        self.notify = notify  # async-функция (текст): сообщение админам
        self.relay = Relay(vpn.relay_port, vpn.relay_password, on_demote=self._on_demote)
        self.lock = asyncio.Lock()
        self.bad: dict[str, float] = {}
        self.rep: dict[str, float] = {}   # репутация прокси: больше — надёжнее
        self.failover: set[str] = set()
        self._kick: asyncio.Task | None = None
        self.last_run = 0.0
        self.budget = PROBE_BUDGET
        self.last_note = ""

    async def start(self) -> bool:
        ok = await self.relay.start()
        self.sync_routes()
        return ok

    def sync_routes(self) -> None:
        """Маршруты ретранслятора повторяют сохранённые авто-страны."""
        pools = {l["code"]: l.get("pool") or [] for l in self.vpn.auto_locations()}
        for code in list(self.relay.routes):
            if code not in pools:
                self.relay.drop_route(code)
        for code, pool in pools.items():
            self.relay.set_route(code, pool)

    # ---------- переключение на запасной прямо во время работы ----------

    def _on_demote(self, code: str, url: str) -> None:
        pool = self.vpn.rotate_auto_upstream(code, url)
        if pool:
            self.relay.set_route(code, pool)
        self.bad[url] = time.time() + BAD_DEAD
        self._score(url, -3)
        self.failover.add(code)
        if self.vpn.auto.get("enabled") and (self._kick is None or self._kick.done()):
            self._kick = asyncio.get_running_loop().create_task(self._kick_soon())

    async def _kick_soon(self) -> None:
        await asyncio.sleep(3)
        await self.tick()

    # ---------- основной цикл ----------

    async def tick(self) -> None:
        """Плановая проверка. Ничего не бросает."""
        if not self.vpn.auto.get("enabled"):
            return
        try:
            msg = await self.refresh()
        except Exception:
            log.exception("авто-страны: сбой проверки")
            return
        if msg and self.notify and self.vpn.auto.get("notify", True):
            try:
                await self.notify(msg)
            except Exception:
                log.exception("авто-страны: не удалось отправить сообщение")

    def _score(self, url: str, delta: float) -> None:
        self.rep[url] = max(-10.0, min(10.0, self.rep.get(url, 0.0) + delta))
        if len(self.rep) > REP_LIMIT:  # забываем самых «нейтральных»
            for u, _ in sorted(self.rep.items(), key=lambda kv: abs(kv[1]))[:len(self.rep) - REP_LIMIT]:
                self.rep.pop(u, None)

    def _candidates(self, pool: dict, cc: str, exclude=()) -> list[str]:
        now = time.time()
        skip = set(exclude)
        urls = [u for u in pool.get(cc, []) if u not in skip and self.bad.get(u, 0) < now]
        # Порядок из списков сохраняется, но проверенные нами хорошие идут раньше, плохие позже.
        return sorted(urls, key=lambda u: -self.rep.get(u, 0.0))

    async def _find(self, pool: dict, cc: str, need: int, exclude=()) -> list[tuple[str, int]]:
        # Проверка идёт понемногу: сотни подключений к чужим адресам подряд хостинг может
        # принять за сканирование сети и ограничить сервер.
        tries = min(PER_COUNTRY, self.budget)
        if tries <= 0:
            return []
        urls = self._candidates(pool, cc, exclude)[:tries]
        self.budget -= len(urls)
        failed: set[str] = set()
        found = await pp.pick_working(urls, cc, need, tries=tries, failed=failed)
        until = time.time() + BAD_CANDIDATE
        for u in failed:
            self.bad[u] = until
            self._score(u, -1)
        for u, _ in found:
            self._score(u, 1)
        return found

    async def _alive(self, urls: list[str], cc: str) -> list[tuple[str, int]]:
        async def one(u):
            res = await pp.probe(u) or await pp.probe(u)
            ok = bool(res and res.country == cc)
            self._score(u, 0.5 if ok else -2)
            return (u, res.ms) if ok else None
        return [r for r in await asyncio.gather(*(one(u) for u in urls)) if r]

    def _targets(self, pool: dict) -> tuple[list[str], bool]:
        """Какие страны держать: заданный список или подбор. Второе значение — режим подбора."""
        cfg, manual = self.vpn.auto, self.vpn.manual_codes()
        skip = manual | set(cfg.get("exclude") or [])
        wanted = [c for c in cfg.get("countries") or [] if c not in skip]
        if wanted:
            return wanted, False
        ranked = sorted((c for c in pool if c not in skip),
                        key=lambda c: (PREFERRED.index(c) if c in PREFERRED else len(PREFERRED),
                                       -len(pool[c])))
        # Уже добавленные страны идут первыми: пока их прокси живы, набор стран не меняется.
        current = [l["code"] for l in self.vpn.auto_locations() if l["code"] not in skip]
        return list(dict.fromkeys(current + ranked)), True

    async def refresh(self) -> str:
        """Перепроверяет авто-страны, меняет умершие прокси, добавляет недостающие страны.
        Возвращает отчёт об изменениях или пустую строку."""
        async with self.lock:
            return await self._refresh()

    async def _refresh(self) -> str:
        vpn, nm = self.vpn, pp.country_name
        self.last_run = time.time()
        self.budget = PROBE_BUDGET
        if not await pp.direct_ok():
            self.last_note = "сервер сам не дошёл до проверочного сайта, проверка пропущена"
            log.warning("авто-страны: %s", self.last_note)
            return ""
        try:
            pool = await pp.fetch_pool()
        except Exception as e:
            log.warning("авто-страны: списки прокси не получены: %s", e)
            pool = {}
        self.last_note = "" if pool else "открытые списки прокси сейчас недоступны"
        now = time.time()
        self.bad = {u: t for u, t in self.bad.items() if t > now}

        targets, discovery = self._targets(pool)
        maxn = max(1, int(vpn.auto.get("max") or 8))
        added, swapped, lost, back, removed = [], [], [], [], []
        swapped += [c for c in self.failover if any(l["code"] == c for l in vpn.auto_locations())]
        self.failover.clear()

        # 1) страны, которые больше не нужны
        current = vpn.auto_locations()
        keep = set(targets)
        extra = [l["code"] for l in current if l["code"] not in keep]
        if discovery:
            ok_codes = [l["code"] for l in current if l["code"] in keep]
            extra += ok_codes[maxn:]
        for cc in extra:
            if vpn.remove_location(cc, apply=False):
                removed.append(cc)

        # 2) перепроверка прокси у оставшихся стран
        for loc in list(vpn.auto_locations()):
            cc, was_active, was_down = loc["code"], loc["proxy"], bool(loc.get("down"))
            known = list(loc.get("pool") or [])
            alive = await self._alive(known, cc)
            alive_urls = {u for u, _ in alive}
            for u in known:
                if u not in alive_urls:
                    self.bad[u] = now + BAD_DEAD
            if len(alive) < POOL_SIZE:
                alive += await self._find(pool, cc, POOL_SIZE - len(alive), exclude=known)
            if alive:
                best = min(alive, key=lambda x: x[1])
                slow = alive[0][1] > SLOW_MS and alive[0][1] > 2 * best[1]
                if alive[0][0] != was_active or slow:  # рабочий умер или тормозит: берём самый быстрый
                    alive.sort(key=lambda x: x[1])
                res = vpn.set_auto_location(cc, nm(cc), [u for u, _ in alive], ms=alive[0][1])
                if was_down:
                    back.append(cc)
                elif res == "swapped" and cc not in swapped:
                    swapped.append(cc)
            elif not was_down:
                # Страна только прячется из подписки: это не требует перезапуска Xray.
                vpn.set_auto_down(cc, True)
                lost.append(cc)
            elif discovery and now - loc.get("down_since", now) > HIDE_LIMIT:
                if vpn.remove_location(cc, apply=False):
                    removed.append(cc)

        # 3) недостающие страны
        have = {l["code"] for l in vpn.auto_locations()}
        attempts = 0
        for cc in targets:
            if cc in have:
                continue
            if discovery:
                if len(have) >= maxn or attempts >= maxn - len(have) + EXTRA_ATTEMPTS:
                    break
                attempts += 1
            found = await self._find(pool, cc, POOL_SIZE)
            if found and vpn.set_auto_location(cc, nm(cc), [u for u, _ in found], ms=found[0][1], apply=False):
                added.append(cc)
                have.add(cc)

        swapped = [c for c in swapped if c not in lost and c not in removed]
        self.sync_routes()
        if added or removed:
            vpn.schedule_apply()  # один перезапуск Xray на весь цикл и только при смене набора стран
        parts = []
        if added:
            parts.append("➕ Добавлены: " + ", ".join(nm(c) for c in added))
        if swapped:
            parts.append("🔁 Прокси заменён: " + ", ".join(nm(c) for c in swapped))
        if back:
            parts.append("✅ Снова работают: " + ", ".join(nm(c) for c in back))
        if lost:
            parts.append("⚠️ Нет живых прокси, скрыты до появления: " + ", ".join(nm(c) for c in lost))
        if removed:
            parts.append("➖ Убраны: " + ", ".join(nm(c) for c in removed))
        return "🤖 Авто-страны\n" + "\n".join(parts) if parts else ""

    async def selftest(self) -> list[tuple[dict, pp.Probe | None]]:
        """Проходит путь настоящего клиента: ретранслятор, прокси, сайт. По одной записи на страну."""
        async def one(loc):
            server = self.vpn.relay_outbound(loc["code"])["settings"]["servers"][0]
            user = server["users"][0]
            url = f"socks5://{user['user']}:{user['pass']}@{server['address']}:{self.relay.port}"
            return loc, await pp.probe(url) or await pp.probe(url)
        return list(await asyncio.gather(*(one(l) for l in self.vpn.auto_locations())))
