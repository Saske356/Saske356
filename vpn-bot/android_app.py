"""Свежий APK приложения Arise VPN из Releases репозитория (собирает .github/workflows/android.yml).

Файл скачивается на сервер один раз на версию и раздаётся гостям через Telegram: так он доходит,
даже если у гостя не открывается GitHub. Версия проверяется не чаще раза в CHECK_EVERY секунд.
"""

import asyncio
import json
import logging
import os
import time
import urllib.request

log = logging.getLogger(__name__)

ASSET = "AriseVPN-arm64-v8a.apk"  # подходит почти всем телефонам последних лет
OLD_ASSETS = ("AuroraVPN-arm64-v8a.apk",)  # прежнее название: релизы до переименования
CHECK_EVERY = 3600
CHECK_EMPTY = 300  # пока приложения ещё нет (идёт первая сборка) — проверяем чаще
MAX_SIZE = 49 * 1024 * 1024  # Telegram-бот отправляет файлы до 50 МБ


def version_code(version: str) -> int:
    """Номер сборки из версии: «1.0.14» → 14, «0.1.7» → 7 (versionCode = номер запуска CI)."""
    tail = (version or "").rsplit(".", 1)[-1]
    return int(tail) if tail.isdigit() else 0


class AppRelease:
    """asset — имя файла в релизе; prefix — брать не «последний» релиз, а самый свежий с тегом,
    начинающимся с prefix (новое приложение выкладывается предварительными версиями arise-new-…)."""

    def __init__(self, repo: str, folder: str, fetch=None, asset: str = ASSET,
                 old_assets: tuple = OLD_ASSETS, prefix: str = ""):
        self.repo = repo
        self.folder = folder
        self.asset, self.old_assets, self.prefix = asset, tuple(old_assets), prefix
        self._fetch = fetch or self._http
        self.url = ""  # ссылка на файл в GitHub (запасная для обновления изнутри приложения)
        self._checked = 0.0
        self._lock = asyncio.Lock()
        self.version = ""
        self.path = ""

    @staticmethod
    def _http(url: str, limit: int) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "aurora-bot",
                                                   "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(limit + 1)
        if len(data) > limit:
            raise ValueError("слишком большой файл")
        return data

    def _local(self) -> tuple[str, str]:
        """Уже скачанная версия: (версия, путь) или пустые строки."""
        try:
            with open(os.path.join(self.folder, "version")) as f:
                ver = f.read().strip()
        except OSError:
            return "", ""
        path = os.path.join(self.folder, self.asset)
        try:
            with open(os.path.join(self.folder, "url")) as f:
                self.url = f.read().strip()
        except OSError:
            pass
        return (ver, path) if ver and os.path.exists(path) else ("", "")

    def cached(self) -> tuple[str, str] | None:
        """Уже скачанная версия без обращения к сети: для раздачи обновлений приложениям."""
        if not self.path:
            self.version, self.path = self._local()
        return (self.version, self.path) if self.path else None

    async def latest(self) -> tuple[str, str] | None:
        """(версия, путь к APK) или None, если приложения пока нет и скачать не вышло."""
        async with self._lock:
            if not self.path:
                self.version, self.path = self._local()
            if time.time() - self._checked >= (CHECK_EVERY if self.path else CHECK_EMPTY):
                self._checked = time.time()
                try:
                    await self._update()
                except Exception as e:  # сеть, GitHub, диск — остаёмся на скачанной версии
                    log.warning("приложение: не удалось проверить новую версию: %s", e)
            return (self.version, self.path) if self.path else None

    async def _update(self) -> None:
        if self.prefix:
            api = f"https://api.github.com/repos/{self.repo}/releases?per_page=30"
            rels = json.loads(await asyncio.to_thread(self._fetch, api, 4 << 20))
            rels = [r for r in rels if str(r.get("tag_name") or "").startswith(self.prefix) and not r.get("draft")]
            rel = max(rels, key=lambda r: version_code(str(r["tag_name"])[len(self.prefix):]), default={})
            ver = str(rel.get("tag_name") or "")[len(self.prefix):]
        else:
            api = f"https://api.github.com/repos/{self.repo}/releases/latest"
            rel = json.loads(await asyncio.to_thread(self._fetch, api, 1 << 20))
            ver = str(rel.get("tag_name") or "").lstrip("v")
        url = next((a.get("browser_download_url") for a in rel.get("assets") or []
                    if a.get("name") in (self.asset, *self.old_assets)), None)
        if not ver or not url or ver == self.version:
            return
        data = await asyncio.to_thread(self._fetch, url, MAX_SIZE)
        if not data.startswith(b"PK"):
            raise ValueError("скачанный файл не похож на APK")
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, self.asset)
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
        with open(os.path.join(self.folder, "version"), "w") as f:
            f.write(ver)
        with open(os.path.join(self.folder, "url"), "w") as f:
            f.write(url)
        self.version, self.path, self.url = ver, path, url
        log.info("приложение: скачана версия %s (%d КБ)", ver, len(data) // 1024)
