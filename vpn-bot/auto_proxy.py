"""Авто-страны: бот сам находит публичные прокси, добавляет из них страны и меняет при отвале.

У каждой авто-страны есть рабочий прокси и до двух запасных. Ретранслятор (proxy_relay.py)
переключается на запасной сразу, как только рабочий перестал отвечать, а этот модуль
раз в несколько минут перепроверяет все прокси, убирает мёртвые и добирает новые.

У каждого прокси копится репутация: прошёл проверку — плюс, не прошёл или умер в работе —
минус. Кандидаты с плохой историей пробуются последними, так что со временем страны держатся
на самых стабильных прокси. Если запасной заметно быстрее рабочего, он становится рабочим.
"""

import asyncio
import json
import logging
import os
import time

import public_proxies as pp
from proxy_relay import Relay

log = logging.getLogger("vpn-bot.auto")

POOL_SIZE = 3            # рабочий прокси + запасные на каждую страну
BAD_DEAD = 6 * 3600      # сколько не возвращаемся к прокси, который умер в работе
BAD_CANDIDATE = 1800     # сколько не перепроверяем кандидата, не прошедшего проверку
EXTRA_ATTEMPTS = 5       # сколько лишних стран пробуем за цикл в режиме подбора
PROBE_BUDGET = 150       # сколько новых прокси можно проверить за один цикл
PER_COUNTRY = 12         # и сколько из них на одну страну
PARALLEL = 4             # сколько стран ищется одновременно (по 6 проверок у каждой)
SPARE_TTL = 3600         # сколько помнить рабочий прокси, найденный «не в своей» стране
HIDE_LIMIT = 6 * 3600    # при подборе страна без прокси столько ждёт, потом уступает место другой
SLOW_MS = 1500           # рабочий прокси медленнее этого и вдвое медленнее запасного уступает ему
REP_LIMIT = 5000         # сколько прокси помнить в репутации
MISSES_TO_HIDE = 2       # страна прячется после стольких проверок подряд без живых прокси

# В режиме подбора берутся только эти страны (пользователь просил оставить хорошие), в этом порядке.
# Россию, Китай, Иран и подобные не берём: через них VPN бессмыслен или медленный.
PREFERRED = ["nl", "de", "us", "gb", "fr", "fi", "se", "ch", "jp", "sg", "ca", "tr",
             "it", "es", "at", "no", "dk", "cz", "pl", "kz", "ae", "hk", "kr", "au",
             "be", "ie", "pt", "ro", "hu", "lv", "lt", "ee", "bg", "rs", "ge", "am", "il", "tw", "br"]
UNKNOWN_BUDGET = 60      # сколько прокси без страны проверять за цикл: страна узнаётся по выходу


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
        # Рабочие прокси, которые списки записали не в ту страну: {страна: {url: (мс, до)}}.
        self.spare: dict[str, dict[str, tuple[int, float]]] = {}
        self.rot = 0  # сдвиг очереди стран: каждый цикл первыми пробуются другие
        self.misses: dict[str, int] = {}  # страна -> проверок подряд без живых прокси
        # Что бот знает о прокси, хранится на диске: после обновления и перезапуска бота
        # он не начинает с нуля и не прячет страны из-за одной неудачной проверки.
        state = getattr(vpn, "state_path", "")
        self.cache_path = os.path.join(os.path.dirname(state) or ".", "auto_cache.json") if state else ""
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                d = json.load(f)
            now = time.time()
            self.rep = {str(u): float(v) for u, v in (d.get("rep") or {}).items()}
            self.bad = {str(u): float(t) for u, t in (d.get("bad") or {}).items() if float(t) > now}
            self.spare = {cc: {u: (int(v[0]), float(v[1])) for u, v in urls.items() if float(v[1]) > now}
                          for cc, urls in (d.get("spare") or {}).items()}
            self.misses = {str(c): int(n) for c, n in (d.get("misses") or {}).items()}
            self.rot = int(d.get("rot") or 0)
        except (OSError, ValueError, TypeError, AttributeError, IndexError) as e:
            log.warning("авто-страны: кэш прокси не прочитан: %s", e)

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        data = {"rep": self.rep, "bad": self.bad, "misses": self.misses, "rot": self.rot,
                "spare": {cc: {u: list(v) for u, v in urls.items()} for cc, urls in self.spare.items()}}
        try:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.cache_path)
        except OSError as e:
            log.warning("авто-страны: кэш прокси не сохранён: %s", e)

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

    async def _scan_unknown(self, pool: dict) -> None:
        now = time.time()
        urls = [u for u in pool.get(pp.UNKNOWN, []) if self.bad.get(u, 0) < now]
        if not urls:
            return
        k = (self.rot * UNKNOWN_BUDGET) % len(urls)
        batch = (urls[k:] + urls[:k])[:UNKNOWN_BUDGET]
        failed: set[str] = set()
        strays: dict = {}
        await pp.pick_working(batch, pp.UNKNOWN, 1, tries=len(batch), concurrency=8, failed=failed, strays=strays)
        until = now + BAD_CANDIDATE * 4  # мёртвые из котла долго не перепроверяем
        for u in failed:
            self.bad[u] = until
        self._keep_strays(strays)

    def _keep_strays(self, strays: dict) -> None:
        until = time.time() + SPARE_TTL
        for cc, found in strays.items():
            if len(cc) != 2 or not cc.isalpha() or cc in ("xx", "t1"):
                continue  # служебные коды Cloudflare (Tor, неизвестно) — не страна
            for u, ms in found:
                self.spare.setdefault(cc, {})[u] = (ms, until)
                self._score(u, 1)

    async def _find(self, pool: dict, cc: str, need: int, exclude=()) -> list[tuple[str, int]]:
        # Сначала рабочие прокси этой страны, найденные при поиске других стран: их достаточно
        # быстро перепроверить. Потом новые кандидаты из списков.
        now, skip = time.time(), set(exclude)
        spare = [u for u, (_, t) in sorted(self.spare.get(cc, {}).items(), key=lambda kv: kv[1][0])
                 if t > now and u not in skip and self.bad.get(u, 0) < now]
        self.spare.pop(cc, None)
        found = await self._alive(spare[:need + 1], cc) if spare else []
        if len(found) >= need:
            return sorted(found, key=lambda x: x[1])[:need]
        # Проверка идёт понемногу: сотни подключений к чужим адресам подряд хостинг может
        # принять за сканирование сети и ограничить сервер.
        tries = min(PER_COUNTRY, self.budget)
        if tries <= 0:
            return found
        urls = self._candidates(pool, cc, skip | set(spare))[:tries]
        self.budget -= len(urls)
        failed: set[str] = set()
        strays: dict = {}
        found += await pp.pick_working(urls, cc, need - len(found), tries=tries, failed=failed, strays=strays)
        until = time.time() + BAD_CANDIDATE
        for u in failed:
            self.bad[u] = until
            self._score(u, -1)
        for u, _ in found:
            self._score(u, 1)
        self._keep_strays(strays)
        return sorted(found, key=lambda x: x[1])

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
        ranked = sorted((c for c in PREFERRED if c not in skip), key=PREFERRED.index)
        # Уже добавленные страны идут первыми: пока их прокси живы, набор стран не меняется.
        current = [l["code"] for l in self.vpn.auto_locations() if l["code"] not in skip]
        return list(dict.fromkeys(current + ranked)), True

    async def refresh(self) -> str:
        """Перепроверяет авто-страны, меняет умершие прокси, добавляет недостающие страны.
        Возвращает отчёт об изменениях или пустую строку."""
        async with self.lock:
            try:
                return await self._refresh()
            finally:
                self._save_cache()

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
        self.spare = {cc: kept for cc, urls in self.spare.items()
                      if (kept := {u: v for u, v in urls.items() if v[1] > now and self.bad.get(u, 0) < now})}

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
                self.misses.pop(cc, None)
                best = min(alive, key=lambda x: x[1])
                kb = lambda u: pp.SPEEDS.get(u, 0)
                fastest = max(alive, key=lambda x: kb(x[0]))
                slow = (alive[0][1] > SLOW_MS and alive[0][1] > 2 * best[1]) or \
                       (kb(alive[0][0]) and kb(fastest[0]) > 2 * kb(alive[0][0]))
                if alive[0][0] != was_active or slow:
                    # рабочий умер или тормозит: берём самый быстрый по скорости, при равной — по задержке
                    alive.sort(key=lambda x: (-(kb(x[0]) // 200), x[1]))
                res = vpn.set_auto_location(cc, nm(cc), [u for u, _ in alive], ms=alive[0][1])
                if was_down:
                    back.append(cc)
                elif res == "swapped" and cc not in swapped:
                    swapped.append(cc)
            elif not was_down:
                # Одна неудачная проверка — ещё не повод: бесплатные прокси моргают, а сразу после
                # перезапуска бота сеть может быть не готова. Прячем со второй подряд.
                self.misses[cc] = self.misses.get(cc, 0) + 1
                if self.misses[cc] >= MISSES_TO_HIDE:
                    # Страна только прячется из подписки: это не требует перезапуска Xray.
                    vpn.set_auto_down(cc, True)
                    lost.append(cc)
            elif discovery and now - loc.get("down_since", now) > HIDE_LIMIT:
                if vpn.remove_location(cc, apply=False):
                    removed.append(cc)

        # 2б) котёл прокси без страны: проверяем понемногу, рабочие и быстрые достаются стране выхода
        await self._scan_unknown(pool)

        # 3) недостающие страны. Раньше каждый цикл весь лимит проверок съедали одни и те же
        # первые страны очереди, и до остальных дело не доходило. Теперь: сначала страны, для
        # которых уже есть найденные прокси, остальные — со сдвигом, который растёт каждый цикл;
        # несколько стран ищутся одновременно.
        have = {l["code"] for l in vpn.auto_locations()}
        missing = [cc for cc in targets if cc not in have]
        if discovery:
            skip = vpn.manual_codes() | set(vpn.auto.get("exclude") or [])
            missing += [cc for cc in self.spare if cc in PREFERRED and cc not in have and cc not in skip
                        and cc not in missing]
        ready = [cc for cc in missing if self.spare.get(cc)]
        rest = [cc for cc in missing if cc not in ready]
        if rest:
            k = self.rot % len(rest)
            rest = rest[k:] + rest[:k]
        self.rot += max(1, PROBE_BUDGET // PER_COUNTRY)
        queue = ready + rest
        if discovery:
            queue = queue[:max(0, maxn - len(have)) + EXTRA_ATTEMPTS] if len(have) < maxn else []
        sem = asyncio.Semaphore(PARALLEL)

        async def search(cc):
            async with sem:
                return cc, await self._find(pool, cc, POOL_SIZE)
        for cc, found in await asyncio.gather(*(search(cc) for cc in queue)):
            if discovery and len(have) >= maxn:
                break
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
