"""Превращает исходники v2rayNG в Aurora VPN: python3 customize.py <папка v2rayNG>.

Меняется только оформление и настройки по умолчанию, ядро и логика v2rayNG остаются как есть.
Каждая правка проверяет, что нужный кусок нашёлся: если v2rayNG поменяет код, сборка упадёт
сразу с понятной ошибкой, а не соберёт приложение с половиной правок.

v2rayNG распространяется по GPL-3.0, поэтому и эти правки, и сама сборка открыты в этом репозитории.
"""

import glob
import os
import re
import sys

import make_icon

APP_ID = "io.github.saske356.aurora"
APP_NAME = "Aurora VPN"
SCHEME = "aurora"  # ссылка aurora://install-sub?url=... добавляет подписку одним касанием
REPO = "Saske356/Saske356"
# Проверка пинга: обычный HTTP без TLS — замер не включает лишнее рукопожатие TLS до Google,
# цифра ближе к реальной задержке до сервера, и замер быстрее.
DELAY_URL = "http://cp.cloudflare.com/generate_204"
DELAY_URL2 = "http://www.gstatic.com/generate_204"


def edit(path: str, pairs: list[tuple[str, str]], count_ok=lambda n: n >= 1) -> None:
    with open(path, encoding="utf-8") as f:
        s = f.read()
    for old, new in pairs:
        n = s.count(old) if not isinstance(old, re.Pattern) else len(old.findall(s))
        if not count_ok(n):
            sys.exit(f"customize: в {path} не найдено: {old!r}")
        s = old.sub(new, s) if isinstance(old, re.Pattern) else s.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


def main(root: str) -> None:
    app = os.path.join(root, "V2rayNG", "app")
    src = os.path.join(app, "src", "main")
    kt = os.path.join(src, "java", "com", "v2ray", "ang")
    code = os.environ.get("AURORA_VERSION_CODE", "1")
    name = os.environ.get("AURORA_VERSION_NAME", "1.0." + code)

    # Своё имя пакета: ставится рядом с обычным v2rayNG и не путается с ним. Пространство имён
    # в коде (com.v2ray.ang) не трогаем — на него завязаны JNI-библиотеки туннеля.
    ndk = os.environ.get("AURORA_NDK_VERSION", "")
    edit(os.path.join(app, "build.gradle.kts"), [
        ('applicationId = "com.v2ray.ang"', f'applicationId = "{APP_ID}"'),
        (re.compile(r"versionCode = \d+"), f"versionCode = {code}"),
        (re.compile(r'versionName = "[^"]*"'), f'versionName = "{name}"'),
        ('"v2rayNG_${variant.versionName}', '"AuroraVPN_${variant.versionName}'),
        ("compileSdk = ", (f'ndkVersion = "{ndk}"\n    ' if ndk else "") + "compileSdk = "),
    ])

    for p in glob.glob(os.path.join(src, "res", "values*", "strings.xml")):
        edit(p, [("v2rayNG", APP_NAME)], count_ok=lambda n: True)
    edit(os.path.join(src, "res", "values", "strings.xml"), [(f">{APP_NAME}<", f">{APP_NAME}<")])

    edit(os.path.join(src, "AndroidManifest.xml"), [
        ('<data android:scheme="v2rayng" />', f'<data android:scheme="{SCHEME}" />'),
    ])

    edit(os.path.join(kt, "AppConfig.kt"), [
        ('"$GITHUB_URL/2dust/v2rayNG"', f'"$GITHUB_URL/{REPO}"'),
        ('"https://api.github.com/repos/2dust/v2rayNG/releases"', f'"https://api.github.com/repos/{REPO}/releases"'),
        ('DELAY_TEST_URL = "https://www.gstatic.com/generate_204"', f'DELAY_TEST_URL = "{DELAY_URL}"'),
        ('DELAY_TEST_URL2 = "https://www.google.com/generate_204"', f'DELAY_TEST_URL2 = "{DELAY_URL2}"'),
        # «Лучший сервер» в приложении перепроверяет пинг раз в минуту, а не раз в 3 минуты
        ('OBSERVATORY_LEAST_PING_INTERVAL = "3m"', 'OBSERVATORY_LEAST_PING_INTERVAL = "1m"'),
    ])

    # Рекламный пункт меню v2rayNG ведёт на чужой сайт — убираем.
    edit(os.path.join(kt, "ui", "main", "MainDrawer.kt"), [
        ("    MainDestination.Promotion,\n", ""),
    ])

    # Бот узнаёт своё приложение по User-Agent и отдаёт ему конфиги с настройками под скорость.
    # «v2rayNG» в строке остаётся: по нему бот понимает, что приложение умеет JSON-конфиги.
    edit(os.path.join(kt, "util", "HttpUtil.kt"), [
        ('"v2rayNG/${BuildConfig.VERSION_NAME}"', '"AuroraVPN/${BuildConfig.VERSION_NAME} v2rayNG/${BuildConfig.VERSION_NAME}"'),
    ])

    # По умолчанию: после обновления подписки сразу замерить пинг и поставить быстрые сверху.
    for key in ("PREF_AUTO_TEST_AFTER_UPDATE_SUBSCRIPTION", "PREF_AUTO_SORT_AFTER_TEST"):
        pat = re.compile(r"((?:decodeSettingsBool|rememberMmkvBool)\(AppConfig\." + key + r", )false\)")
        files = [p for p in glob.glob(os.path.join(kt, "**", "*.kt"), recursive=True)
                 if pat.search(open(p, encoding="utf-8").read())]
        if not files:
            sys.exit(f"customize: не найдена настройка {key}")
        for p in files:
            edit(p, [(pat, r"\1true)")])

    make_icon.main(os.path.join(src, "res"))
    print(f"customize: {APP_NAME} {name} ({code}), пакет {APP_ID}")


if __name__ == "__main__":
    main(sys.argv[1])
