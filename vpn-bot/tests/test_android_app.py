import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import android_app  # noqa: E402

APK = b"PK\x03\x04" + b"x" * 100


class AppReleaseTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.calls = []
        self.tag = "v1.0.5"
        self.fail = False

        def fetch(url, limit):
            self.calls.append(url)
            if self.fail:
                raise OSError("нет сети")
            if url.endswith("/releases/latest"):
                return json.dumps({"tag_name": self.tag, "assets": [
                    {"name": "AuroraVPN-armeabi-v7a.apk", "browser_download_url": "https://x/v7a"},
                    {"name": android_app.ASSET, "browser_download_url": "https://x/" + self.tag}]}).encode()
            return APK + self.tag.encode()
        self.app = android_app.AppRelease("o/r", self.d, fetch=fetch)

    async def test_downloads_once_per_version_and_survives_outage(self):
        ver, path = await self.app.latest()
        self.assertEqual(ver, "1.0.5")
        with open(path, "rb") as f:
            self.assertTrue(f.read().startswith(b"PK"))
        self.assertEqual(self.calls, ["https://api.github.com/repos/o/r/releases/latest", "https://x/v1.0.5"])
        await self.app.latest()
        self.assertEqual(len(self.calls), 2, "версию проверяем не чаще раза в час")
        self.app._checked = 0
        await self.app.latest()
        self.assertEqual(len(self.calls), 3, "та же версия — файл не качаем заново")
        self.app._checked, self.tag = 0, "v1.0.6"
        self.assertEqual((await self.app.latest())[0], "1.0.6")
        self.app._checked, self.fail = 0, True
        self.assertEqual((await self.app.latest())[0], "1.0.6", "GitHub недоступен — отдаём скачанное")
        # после перезапуска бота версия берётся с диска
        again = android_app.AppRelease("o/r", self.d, fetch=lambda u, n: (_ for _ in ()).throw(OSError()))
        self.assertEqual((await again.latest())[0], "1.0.6")

    async def test_nothing_yet(self):
        self.fail = True
        self.assertIsNone(await self.app.latest())

    async def test_rejects_non_apk(self):
        self.app._fetch = lambda u, n: (json.dumps({"tag_name": "v2", "assets": [
            {"name": android_app.ASSET, "browser_download_url": "https://x/a"}]}).encode()
            if u.endswith("latest") else b"<html>")
        self.assertIsNone(await self.app.latest())
        self.assertFalse(os.path.exists(os.path.join(self.d, android_app.ASSET)))


class PrereleaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_takes_newest_tag_with_prefix(self):
        d = tempfile.mkdtemp()
        rels = [{"tag_name": "v1.0.20", "assets": []},
                {"tag_name": "arise-new-0.1.9", "assets": [{"name": "AriseNew-arm64-v8a.apk",
                                                             "browser_download_url": "https://x/9"}]},
                {"tag_name": "arise-new-0.1.12", "assets": [{"name": "AriseNew-arm64-v8a.apk",
                                                              "browser_download_url": "https://x/12"}]},
                {"tag_name": "arise-new-0.1.13", "draft": True, "assets": []}]

        def fetch(url, limit):
            return json.dumps(rels).encode() if "/releases?" in url else APK
        app = android_app.AppRelease("o/r", d, fetch=fetch, asset="AriseNew-arm64-v8a.apk",
                                     old_assets=(), prefix="arise-new-")
        ver, path = await app.latest()
        self.assertEqual((ver, os.path.basename(path), app.url), ("0.1.12", "AriseNew-arm64-v8a.apk", "https://x/12"))
        self.assertEqual(android_app.version_code(ver), 12)
        self.assertEqual(android_app.AppRelease("o/r", d, asset="AriseNew-arm64-v8a.apk").cached()[0], "0.1.12")


class SecretsMatch(unittest.TestCase):
    def test_app_and_bot_share_the_subscription_key(self):
        import re
        import client_config
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "android", "customize.py"), encoding="utf-8") as f:
            m = re.search(r'^SUB_SECRET = "([0-9a-f]+)"', f.read(), re.M)
        self.assertTrue(m)
        self.assertEqual(m.group(1), client_config.SUB_SECRET, "ключ подписки в приложении и в боте разный")


if __name__ == "__main__":
    unittest.main()
